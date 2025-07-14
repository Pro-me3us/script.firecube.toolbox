import subprocess
import os
import xbmcgui
import xbmcaddon
import gzip
import struct
import time

def is_update_available():
    try:
        boot_md5 = subprocess.check_output(
            ["dd", "if=/dev/bootloader", "bs=512", "skip=1"], stderr=subprocess.DEVNULL
        )
        boot_sum = subprocess.run(["md5sum"], input=boot_md5, capture_output=True).stdout.decode().split()[0]

        misc_md5 = subprocess.check_output(
            ["dd", "if=/dev/misc"], stderr=subprocess.DEVNULL
        )
        misc_sum = subprocess.run(["md5sum"], input=misc_md5, capture_output=True).stdout.decode().split()[0]

        return (
            boot_sum.strip() == "d231e9ea748bbf7bebd4d86904fe71cb" and
            misc_sum.strip() != "3592c7222692ddb3e17ac0f3a0010dfd"
        )
    except Exception as e:
        xbmcgui.Dialog().notification("Cube Update Check Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)
        return False

def _read_misc_timestamp(path, offset=0x1008):
    try:
        with open(path, 'rb') as f:
            f.seek(offset)
            raw = f.read(4)
            if len(raw) != 4:
                return None
            if raw == b"ootm":
                return "2023-04-08"
            ts = struct.unpack('>I', raw)[0]
            return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
    except Exception:
        return None

def _read_gz_misc_timestamp(gz_path, offset=0x1008):
    try:
        with gzip.open(gz_path, 'rb') as f:
            f.seek(offset)
            raw = f.read(4)
            if len(raw) != 4:
                return None
            if raw == b"ootm":
                return "2023-04-08"
            ts = struct.unpack('>I', raw)[0]
            return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
    except Exception:
        return None

def _remount_flash(rw=True):
    try:
        mode = "rw" if rw else "ro"
        subprocess.run(["mount", "-o", f"remount,{mode}", "/flash"], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def _kernel_is_49():
    try:
        uname = subprocess.check_output(["uname", "-r"]).decode().strip()
        return uname.startswith("4.9")
    except Exception:
        return False

def _copy_dtb(addon_path):
    try:
        if not _kernel_is_49():
            return

        dtb_src = os.path.join(addon_path, "resources", "update", "dtb.img")
        if not os.path.exists(dtb_src):
            return

        remounted = _remount_flash(True)
        subprocess.run(["cp", dtb_src, "/flash/dtb.img"], check=True)
        if remounted:
            _remount_flash(False)
    except Exception as e:
        xbmcgui.Dialog().notification("DTB Copy Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def _ensure_env(addon_path):
    try:
        os.makedirs("/media/product", exist_ok=True)
        subprocess.run(["mount", "/dev/product", "/media/product"], check=False)
        env_path = "/media/product/env.txt"
        if not os.path.exists(env_path):
            src = os.path.join(addon_path, "resources", "update", "env.txt")
            if os.path.exists(src):
                subprocess.run(["cp", src, env_path], check=True)
    except Exception as e:
        xbmcgui.Dialog().notification("env.txt Setup Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def apply_update():
    try:
        addon_path = xbmcaddon.Addon().getAddonInfo('path')
        img_gz_path = os.path.join(addon_path, "resources", "update", "misc.img.gz")

        if not os.path.exists(img_gz_path):
            xbmcgui.Dialog().notification("Cube Update", "misc.img.gz not found", xbmcgui.NOTIFICATION_ERROR, 5000)
            return

        current_ts = _read_misc_timestamp("/dev/misc")
        update_ts = _read_gz_misc_timestamp(img_gz_path)

        message = f"Proceed with Cube update?\n\nCurrent: {current_ts or 'Unknown'}\nUpdate: {update_ts or 'Unknown'}"
        confirm = xbmcgui.Dialog().yesno("Confirm Cube Update", message)
        if not confirm:
            return

        subprocess.run(["gzip", "-dc", img_gz_path], stdout=open("/dev/misc", "wb"), check=True)
        _copy_dtb(addon_path)
        _ensure_env(addon_path)

        xbmcgui.Dialog().notification("Cube Update", "Update applied successfully", xbmcgui.NOTIFICATION_INFO, 5000)
    except Exception as e:
        xbmcgui.Dialog().notification("Cube Update Failed", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)
