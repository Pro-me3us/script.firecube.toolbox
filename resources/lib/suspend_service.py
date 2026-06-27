# resources/lib/suspend_service.py

import json
import os
import shutil
import subprocess

import xbmc
import xbmcaddon
import xbmcgui

__addon__ = xbmcaddon.Addon()

ADDON_PATH = __addon__.getAddonInfo("path")

SUSPEND_SERVICE_SRC = os.path.join(ADDON_PATH, "resources", "service", "systemd-suspend.service")
SUSPEND_SCRIPT_SRC = os.path.join(ADDON_PATH, "resources", "service", "suspend.sh")

SYSTEMD_DIR = "/storage/.config/system.d"
SUSPEND_SERVICE_DEST = os.path.join(SYSTEMD_DIR, "systemd-suspend.service")
SUSPEND_SCRIPT_DEST = os.path.join(SYSTEMD_DIR, "suspend.sh")
SUSPEND_SCRIPT_CMD = SUSPEND_SCRIPT_DEST

AUTOSTART_PATH = "/storage/.config/autostart.sh"

REMOTE_LINE = "#amlogic NEC remote * Amazon Alexa Voice Remote Enhanced"
REMOTE_SRC = os.path.join(ADDON_PATH, "resources", "service", "remote.conf")
REMOTE_PATHS = [
    "/storage/.config/remote.conf",
    "/storage/.config/remote2.conf",
    "/storage/.config/remote3.conf",
]

SHUTDOWN_MODE_MAP = {
    "Shutdown": 0,
    "Quit": 1,
    "Hibernate": 2,
    "Suspend": 3,
    "Reboot": 4,
    "Minimize": 5,
}

def get_suspend_mode():
    if not os.path.isfile(SUSPEND_SERVICE_DEST):
        return None
    try:
        with open(SUSPEND_SERVICE_DEST) as f:
            for line in f:
                line=line.strip()
                if line == f"ExecStart={SUSPEND_SCRIPT_CMD} pause":
                    return "pause"
                if line == f"ExecStart={SUSPEND_SCRIPT_CMD} restart":
                    return "restart"
    except Exception:
        pass
    return None

def show_suspend_menu():
    mode=get_suspend_mode()
    pre={"pause":0,"restart":1}.get(mode,2)
    sel=xbmcgui.Dialog().select("Suspend-to-Idle",[
        "Enable suspend service (Pause Kodi -- Slightly Faster)",
        "Enable suspend service (Restart Kodi -- Recommended)",
        "Disable suspend-to-idle service"],preselect=pre)
    if sel==0: enable_suspend_service("pause")
    elif sel==1: enable_suspend_service("restart")
    elif sel==2: disable_suspend_service()

def get_shutdown_state():
    cmd={"jsonrpc":"2.0","method":"Settings.GetSettingValue","params":{"setting":"powermanagement.shutdownstate"},"id":1}
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(cmd))).get("result",{}).get("value")
    except Exception:
        return None

def set_shutdown_state(mode):
    val=SHUTDOWN_MODE_MAP.get(mode)
    if val is None: return False
    cmd={"jsonrpc":"2.0","method":"Settings.SetSettingValue","params":{"setting":"powermanagement.shutdownstate","value":val},"id":1}
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(cmd))).get("result") is True
    except Exception:
        return False

def ensure_suspend_unmask_in_autostart():
    if not os.path.exists(AUTOSTART_PATH):
        with open(AUTOSTART_PATH,"w") as f:f.write("#!/bin/sh\n")
    with open(AUTOSTART_PATH) as f: lines=f.readlines()
    if "systemctl unmask suspend.target\n" not in lines:
        lines += ["# Make sure suspend is unmasked\n","systemctl unmask suspend.target\n"]
        with open(AUTOSTART_PATH,"w") as f:f.writelines(lines)

def remove_suspend_unmask_from_autostart():
    if not os.path.exists(AUTOSTART_PATH): return
    with open(AUTOSTART_PATH) as f: lines=f.readlines()
    lines=[l for l in lines if "suspend.target" not in l and "Make sure suspend is unmasked" not in l]
    with open(AUTOSTART_PATH,"w") as f:f.writelines(lines)

def ensure_remote_conf():
    for p in REMOTE_PATHS:
        if os.path.exists(p):
            with open(p) as f:
                if REMOTE_LINE in f.read():
                    return
    for p in REMOTE_PATHS:
        if not os.path.exists(p):
            shutil.copyfile(REMOTE_SRC,p); return
        with open(p) as f:
            if REMOTE_LINE not in f.read():
                shutil.copyfile(REMOTE_SRC,p); return

def update_execstart(mode):
    with open(SUSPEND_SERVICE_DEST) as f: lines=f.readlines()
    with open(SUSPEND_SERVICE_DEST,"w") as f:
        for line in lines:
            if line.startswith("ExecStart="):
                f.write(f"ExecStart={SUSPEND_SCRIPT_CMD} {mode}\n")
            else:
                f.write(line)

def enable_suspend_service(mode):
    os.makedirs(SYSTEMD_DIR,exist_ok=True)
    shutil.copyfile(SUSPEND_SERVICE_SRC,SUSPEND_SERVICE_DEST)
    shutil.copyfile(SUSPEND_SCRIPT_SRC,SUSPEND_SCRIPT_DEST)
    os.chmod(SUSPEND_SCRIPT_DEST,0o755)
    update_execstart(mode)
    subprocess.run(["systemctl","daemon-reexec"],check=True)
    subprocess.run(["systemctl","daemon-reload"],check=True)
    ensure_suspend_unmask_in_autostart()
    ensure_remote_conf()
    set_shutdown_state("Suspend")

def disable_suspend_service():
    for p in (SUSPEND_SERVICE_DEST,SUSPEND_SCRIPT_DEST):
        if os.path.exists(p): os.remove(p)
    subprocess.run(["systemctl","daemon-reexec"],check=True)
    subprocess.run(["systemctl","daemon-reload"],check=True)
    remove_suspend_unmask_from_autostart()
    set_shutdown_state("Quit")
