# resources/lib/change_wifi_mac.py

import shutil
import re
import os
import xbmcgui

WIFI_CFG_SRC = "/usr/lib/kernel-overlays/base/lib/firmware/wifi.cfg"
WIFI_CFG_DEST = "/storage/.config/firmware/wifi.cfg"
MMC_DEVICE = "/dev/mmcblk0boot1"

BEEFDEED_MARKER = b"beefdeed"

MAGIC_SEQUENCE = bytes.fromhex(
    "6D 61 63 5F 61 64 64 72 00 00 00 00 00 00 00 00 "
    "10 00 00 00 01 00 00 00 24 01 00 00"
)

def show_wifi_mac_menu():
    options = ["Use FireOS WiFi MAC", "Enter MAC address manually"]
    sel = xbmcgui.Dialog().select("Change WiFi MAC", options)
    if sel == -1:
        return
    if sel == 0:
        use_fireos_mac()
    elif sel == 1:
        enter_mac_manually()

def use_fireos_mac():
    try:
        if not os.path.exists(WIFI_CFG_DEST):
            shutil.copyfile(WIFI_CFG_SRC, WIFI_CFG_DEST)

        with open(MMC_DEVICE, "rb") as f:
            data = f.read()

        beef_index = data.find(BEEFDEED_MARKER)
        if beef_index == -1:
            raise ValueError("beefdeed marker not found in mmcblk0boot1")

        index = data.find(MAGIC_SEQUENCE, beef_index)
        if index == -1:
            raise ValueError("MAC address signature not found after beefdeed")

        mac_raw = data[index + len(MAGIC_SEQUENCE):index + len(MAGIC_SEQUENCE) + 12]
        mac_ascii = mac_raw.decode('ascii', errors='ignore').strip('\x00').strip()
        mac_colon = ':'.join(mac_ascii[i:i+2] for i in range(0, 12, 2)).lower()

        if not re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", mac_colon):
            raise ValueError(f"Extracted MAC '{mac_colon}' is not valid")

        _update_wifi_cfg(mac_colon)
        xbmcgui.Dialog().notification("WiFi MAC", f"MAC set to {mac_colon}", xbmcgui.NOTIFICATION_INFO, 5000)

    except Exception as e:
        xbmcgui.Dialog().notification("WiFi MAC Error", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def enter_mac_manually():
    current_mac = _read_current_mac() or "00:00:00:00:00:00"
    mac_input = xbmcgui.Dialog().input("Enter WiFi MAC", defaultt=current_mac, type=xbmcgui.INPUT_ALPHANUM)

    if re.fullmatch(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac_input.strip()):
        try:
            if not os.path.exists(WIFI_CFG_DEST):
                shutil.copyfile(WIFI_CFG_SRC, WIFI_CFG_DEST)
            _update_wifi_cfg(mac_input.strip().lower())
            xbmcgui.Dialog().notification("WiFi MAC", f"MAC set to {mac_input}", xbmcgui.NOTIFICATION_INFO, 5000)
        except Exception as e:
            xbmcgui.Dialog().notification("WiFi MAC Error", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)
    else:
        xbmcgui.Dialog().notification("Invalid MAC", "Format must be XX:XX:XX:XX:XX:XX", xbmcgui.NOTIFICATION_ERROR, 5000)

def _read_current_mac():
    if not os.path.exists(WIFI_CFG_DEST):
        return None

    try:
        with open(WIFI_CFG_DEST, "r") as f:
            override_enabled = False
            mac = None
            for line in f:
                if line.strip().startswith("MacOverride") and "1" in line:
                    override_enabled = True
                if line.strip().startswith("MacAddr"):
                    mac = line.strip().split()[1]
        return mac if override_enabled and mac else None
    except Exception:
        return None

def _update_wifi_cfg(mac_address):
    with open(WIFI_CFG_DEST, "r") as f:
        lines = f.readlines()

    found_override = False
    found_macaddr = False
    new_lines = []

    for line in lines:
        if line.strip().startswith("MacOverride"):
            new_lines.append("MacOverride 1\n")
            found_override = True
        elif line.strip().startswith("MacAddr"):
            new_lines.append(f"MacAddr {mac_address}\n")
            found_macaddr = True
        else:
            new_lines.append(line)

    if not found_override:
        new_lines.append("MacOverride 1\n")
    if not found_macaddr:
        new_lines.append(f"MacAddr {mac_address}\n")

    with open(WIFI_CFG_DEST, "w") as f:
        f.writelines(new_lines)
