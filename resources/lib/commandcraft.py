# File: resources/lib/commandcraft.py
import os
import json
import urllib.request
import subprocess
import xbmcgui

GITHUB_API = "https://api.github.com/repos/Pro-me3us/CommandCraft/releases"
APK_PREFIX = "raven-"
APK_DEST = "/media/data/local/tmp"
SERVICE_SCRIPT_PATH = "/media/data/adb/service.d/commandcraft.sh"
SERVICE_DIR = os.path.dirname(SERVICE_SCRIPT_PATH)
MOUNT_POINT = "/media/data"
DATA_DEVICE = "/dev/data"
DT_ID_PATH = "/proc/device-tree/amlogic-dt-id"


def run():
    if not os.path.exists(DT_ID_PATH):
        xbmcgui.Dialog().ok("CommandCraft", "DT ID not found on system.")
        return

    with open(DT_ID_PATH, "rb") as f:
        dt_id = f.read().decode("ascii", "ignore").strip().strip('\x00')

    if "g12brevb_raven_2g" not in dt_id:
        xbmcgui.Dialog().ok("CommandCraft", f"Unsupported device: {dt_id}")
        return

    try:
        with urllib.request.urlopen(GITHUB_API, timeout=10) as response:
            release = json.loads(response.read().decode())
    except Exception as e:
        xbmcgui.Dialog().ok("CommandCraft", f"Failed to fetch GitHub releases: {e}")
        return

    apk_url = None
    apk_name = None
    for r in release:
        if r.get("tag_name", "").startswith(APK_PREFIX):
            for asset in r.get("assets", []):
                if asset.get("name", "").endswith(".apk"):
                    apk_url = asset.get("browser_download_url")
                    apk_name = asset.get("name")
                    break
            if apk_url:
                break

    if not apk_url or not apk_name:
        xbmcgui.Dialog().ok("CommandCraft", "No matching APK found.")
        return

    os.makedirs(MOUNT_POINT, exist_ok=True)
    subprocess.run(["mount", DATA_DEVICE, MOUNT_POINT], check=False)

    os.makedirs(SERVICE_DIR, exist_ok=True)
    os.makedirs(APK_DEST, exist_ok=True)

    script_content = f"""#!/bin/sh
while [ "$(getprop sys.boot_completed)" != "1" ]; do
    sleep 1
done    
pm install -r /data/local/tmp/{apk_name}
rm /data/local/tmp/{apk_name}
rm /data/adb/service.d/commandcraft.sh
"""

    with open(SERVICE_SCRIPT_PATH, "w") as f:
        f.write(script_content)

    os.chmod(SERVICE_SCRIPT_PATH, 0o755)

    apk_path = os.path.join(APK_DEST, apk_name)
    try:
        with urllib.request.urlopen(apk_url, timeout=30) as response:
            with open(apk_path, "wb") as f:
                f.write(response.read())
    except Exception as e:
        xbmcgui.Dialog().ok("CommandCraft", f"APK download failed: {e}")
        return

    xbmcgui.Dialog().notification("CommandCraft", "CommandCraft installed to FireOS", xbmcgui.NOTIFICATION_INFO, 5000)

