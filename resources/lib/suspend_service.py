# resources/lib/suspend_service.py

import xbmc
import xbmcgui
import xbmcaddon
import json
import os
import shutil
import subprocess

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')

SUSPEND_SERVICE_SRC = os.path.join(
    __addon__.getAddonInfo('path'),
    "resources", "service", "systemd-suspend.service"
)
SUSPEND_SERVICE_DEST = "/storage/.config/system.d/systemd-suspend.service"
AUTOSTART_PATH = "/storage/.config/autostart.sh"
REMOTE_LINE = "#amlogic NEC remote * Amazon Alexa Voice Remote Enhanced"
REMOTE_SRC = os.path.join(__addon__.getAddonInfo('path'), "resources", "service", "remote.conf")
REMOTE_PATHS = [
    "/storage/.config/remote.conf",
    "/storage/.config/remote2.conf",
    "/storage/.config/remote3.conf"
]

SHUTDOWN_MODE_MAP = {
    "Shutdown": 0,
    "Quit": 1,
    "Hibernate": 2,
    "Suspend": 3,
    "Reboot": 4,
    "Minimize": 5
}

def show_suspend_menu():
    preselect = 0 if os.path.isfile(SUSPEND_SERVICE_DEST) else 1
    options = [
        "Enable suspend-to-idle service",
        "Disable suspend-to-idle service"
    ]
    sel = xbmcgui.Dialog().select("Suspend-to-Idle", options, preselect=preselect)
    if sel == -1:
        return
    if sel == 0:
        enable_suspend_service()
    elif sel == 1:
        disable_suspend_service()

def get_shutdown_state():
    command = {
        "jsonrpc": "2.0",
        "method": "Settings.GetSettingValue",
        "params": {"setting": "powermanagement.shutdownstate"},
        "id": 1
    }
    try:
        response = xbmc.executeJSONRPC(json.dumps(command))
        result = json.loads(response)
        return result.get("result", {}).get("value")
    except Exception as e:
        xbmc.log(f"[SuspendService] Failed to get shutdownstate: {e}", xbmc.LOGERROR)
        return None

def set_shutdown_state(mode):
    value = SHUTDOWN_MODE_MAP.get(mode)
    if value is None:
        xbmcgui.Dialog().notification("Suspend Service", f"Invalid mode: {mode}", xbmcgui.NOTIFICATION_ERROR, 5000)
        return False
    command = {
        "jsonrpc": "2.0",
        "method": "Settings.SetSettingValue",
        "params": {"setting": "powermanagement.shutdownstate", "value": value},
        "id": 1
    }
    try:
        response = xbmc.executeJSONRPC(json.dumps(command))
        result = json.loads(response)
        return result.get("result") is True
    except Exception as e:
        xbmcgui.Dialog().notification("Suspend Service", f"Error: {e}", xbmcgui.NOTIFICATION_ERROR, 5000)
        return False

def ensure_suspend_unmask_in_autostart():
    if not os.path.exists(AUTOSTART_PATH):
        with open(AUTOSTART_PATH, "w") as f:
            f.write("#!/bin/sh\n")
    with open(AUTOSTART_PATH, "r") as f:
        lines = f.readlines()
    if "systemctl unmask suspend.target\n" not in lines:
        lines.append("# Make sure suspend is unmasked\n")
        lines.append("systemctl unmask suspend.target\n")
        with open(AUTOSTART_PATH, "w") as f:
            f.writelines(lines)

def remove_suspend_unmask_from_autostart():
    if os.path.exists(AUTOSTART_PATH):
        with open(AUTOSTART_PATH, "r") as f:
            lines = f.readlines()
        lines = [line for line in lines if "suspend.target" not in line and "Make sure suspend is unmasked" not in line]
        with open(AUTOSTART_PATH, "w") as f:
            f.writelines(lines)

def ensure_remote_conf():
    for path in REMOTE_PATHS:
        if os.path.exists(path):
            with open(path, "r") as f:
                if REMOTE_LINE in f.read():
                    return
    # If none have the line, copy to first missing appropriate slot
    if not os.path.exists(REMOTE_PATHS[0]):
        shutil.copyfile(REMOTE_SRC, REMOTE_PATHS[0])
    elif REMOTE_LINE not in open(REMOTE_PATHS[0]).read():
        if not os.path.exists(REMOTE_PATHS[1]):
            shutil.copyfile(REMOTE_SRC, REMOTE_PATHS[1])
        elif REMOTE_LINE not in open(REMOTE_PATHS[1]).read():
            if not os.path.exists(REMOTE_PATHS[2]):
                shutil.copyfile(REMOTE_SRC, REMOTE_PATHS[2])

def enable_suspend_service():
    try:
        if os.path.exists(SUSPEND_SERVICE_SRC):
            os.makedirs(os.path.dirname(SUSPEND_SERVICE_DEST), exist_ok=True)
            shutil.copyfile(SUSPEND_SERVICE_SRC, SUSPEND_SERVICE_DEST)
            subprocess.run(["systemctl", "daemon-reexec"], check=True)
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            ensure_suspend_unmask_in_autostart()
            ensure_remote_conf()
        if set_shutdown_state("Suspend"):
            xbmcgui.Dialog().notification("Suspend-to-Idle", "S2idle Service enabled", xbmcgui.NOTIFICATION_INFO, 4000)
        else:
            xbmcgui.Dialog().notification("Suspend-to-Idle", "Failed to set Suspend state", xbmcgui.NOTIFICATION_ERROR, 5000)
    except Exception as e:
        xbmcgui.Dialog().notification("Enable Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def disable_suspend_service():
    try:
        if os.path.exists(SUSPEND_SERVICE_DEST):
            os.remove(SUSPEND_SERVICE_DEST)
            subprocess.run(["systemctl", "daemon-reexec"], check=True)
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            remove_suspend_unmask_from_autostart()
        if set_shutdown_state("Quit"):
            xbmcgui.Dialog().notification("Suspend-to-Idle", "S2idle Service disabled", xbmcgui.NOTIFICATION_INFO, 3000)
        else:
            xbmcgui.Dialog().notification("Suspend-to-Idle", "Failed to set Quit state", xbmcgui.NOTIFICATION_ERROR, 5000)
    except Exception as e:
        xbmcgui.Dialog().notification("Disable Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)
