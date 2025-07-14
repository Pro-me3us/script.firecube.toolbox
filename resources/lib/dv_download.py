# File: resources/lib/dv_download.py
import os
import platform
import urllib.request
import shutil
import xbmc
import xbmcgui

DV_URLS = {
    "4.9": "https://github.com/Pro-me3us/SoC-BootROMs/raw/refs/heads/main/dv/dv.4.9",
    "5.15": "https://github.com/Pro-me3us/SoC-BootROMs/raw/refs/heads/main/dv/dv.5.15"
}

def enable_dolby_vision():
    kernel = platform.release()
    target = None
    if kernel.startswith("4.9"):
        target = DV_URLS["4.9"]
    elif kernel.startswith("5.15"):
        target = DV_URLS["5.15"]
    else:
        xbmc.log(f"[DolbyVision] Unsupported kernel: {kernel}", xbmc.LOGERROR)
        return

    try:
        tmp_path = "/storage/dovi_tmp.ko"
        final_path = "/storage/dovi.ko"
        xbmc.log("[DolbyVision] Downloading dovi.ko...", xbmc.LOGINFO)
        with urllib.request.urlopen(target) as response, open(tmp_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        os.rename(tmp_path, final_path)
        xbmc.executebuiltin('Notification("Dolby Vision", "dovi.ko added, reboot to enable", 5000)')
    except Exception as e:
        xbmc.log(f"[DolbyVision] Error: {e}", xbmc.LOGERROR)
