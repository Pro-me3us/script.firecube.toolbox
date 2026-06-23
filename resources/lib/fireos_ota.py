# resources/lib/fireos_ota.py

import os
import shutil
import subprocess
import xbmc
import xbmcgui


def format_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            if unit == "B":
                return f"{num_bytes} {unit}"
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def clear():
    mountpoint = "/media/data"
    mounted = False

    try:
        os.makedirs(mountpoint, exist_ok=True)

        result = subprocess.call(
            ["mount", "/dev/data", mountpoint],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if result != 0:
            xbmcgui.Dialog().ok(
                "FireOS OTA",
                "Failed to mount the FireOS data partition."
            )
            return False

        mounted = True

        ota_dir = os.path.join(mountpoint, "ota_package")

        total_size = 0

        if not os.path.isdir(ota_dir):
            return False

        # Calculate size
        for root, dirs, files in os.walk(ota_dir):
            for name in files:
                path = os.path.join(root, name)
                try:
                    total_size += os.path.getsize(path)
                except OSError:
                    pass

        # Delete contents
        for entry in os.listdir(ota_dir):
            path = os.path.join(ota_dir, entry)

            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                xbmc.log(
                    f"[FireOS OTA] Failed removing {path}: {e}",
                    xbmc.LOGERROR
                )

        xbmc.executebuiltin(
            f'Notification("OTA Folder Cleared", '
            f'"Freed {format_size(total_size)}", 5000)'
        )

        return True

    finally:
        if mounted:
            subprocess.call(
                ["umount", "/dev/data"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
