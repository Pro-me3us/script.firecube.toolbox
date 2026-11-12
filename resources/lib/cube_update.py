import subprocess
import os
import xbmcgui
import xbmc
import xbmcaddon
import gzip
import struct
import time
import re
import calendar
from pathlib import Path
from shutil import copy2

RAVEN_DEVICE_ID = "g12brevb_raven_2g"
GAZELLE_DEVICE_ID = "t7_gazelle_pvt"

# Gazelle (3rd gen): uncompressed U-Boot image written into the "logo" partition
GAZELLE_UPDATE_NAME = "bl33.bin.gazl"
GAZELLE_LOGO_OFFSET = 0x10000
GAZELLE_LOGO_DEVICE = "/dev/logo"
GAZELLE_SCAN_MAX = int(1.6 * 1024 * 1024)  # bl33 is up to ~1.6MB


# --------------------------------------------------------------------------
# Common helpers
# --------------------------------------------------------------------------

def get_device_id():
    try:
        with open("/proc/device-tree/amlogic-dt-id", "rb") as f:
            data = f.read()
        return data.split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
    except OSError:
        return None


def _update_dir(addon_path=None):
    if addon_path is None:
        addon_path = xbmcaddon.Addon().getAddonInfo('path')
    return os.path.join(addon_path, "resources", "update")


def _notify(title, message, icon=xbmcgui.NOTIFICATION_ERROR, ms=5000):
    xbmcgui.Dialog().notification(title, message, icon, ms)


# --------------------------------------------------------------------------
# Raven (2nd gen) helpers - unchanged behaviour
# --------------------------------------------------------------------------

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
            misc_sum.strip() != "b716b751d77b308c8b487ebd22c5c447"
        )
    except Exception as e:
        _notify("Cube Update Check Failed", str(e))
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
        _notify("DTB Copy Failed", str(e))

def _copy_boot_menu_files(addon_path):
    try:
        src_dir = Path(addon_path) / "resources" / "update" / "boot_menu"
        dst_dir = Path("/media/product/boot_menu")
        dst_dir.mkdir(parents=True, exist_ok=True)
        for file in src_dir.glob("*"):
            if file.is_file():
                copy2(file, dst_dir / file.name)
    except Exception as e:
        _notify("Boot Menu Copy Failed", str(e))

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
        _notify("env.txt Setup Failed", str(e))


# --------------------------------------------------------------------------
# Gazelle (3rd gen) helpers
# --------------------------------------------------------------------------

def _gazelle_update_path(addon_path=None):
    return os.path.join(_update_dir(addon_path), GAZELLE_UPDATE_NAME)

_UBOOT_RE = re.compile(
    rb"U-Boot [0-9.]+ \(([A-Z][a-z]{2}) +(\d{1,2}) (\d{4}) - "
    rb"(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})\)"
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _parse_uboot_build(data):
    """Find 'U-Boot 2019.01 (Oct 04 2026 - 23:17:57 -0400)' anywhere in `data`.
    Returns (utc_epoch, display_string) or None. Position-independent, so it
    keeps working if the string moves between builds."""
    m = _UBOOT_RE.search(data)
    if not m:
        return None
    mon, day, year, hh, mm, ss, sign, tzh, tzm = [g.decode() for g in m.groups()]
    month = _MONTHS.get(mon)
    if not month:
        return None
    local = calendar.timegm((int(year), month, int(day), int(hh), int(mm), int(ss)))
    offset = (int(tzh) * 3600 + int(tzm) * 60) * (1 if sign == "+" else -1)
    display = f"{year}-{month:02d}-{int(day):02d} {hh}:{mm}:{ss} {sign}{tzh}{tzm}"
    return local - offset, display


def _read_logo_region(length, exact=True):
    """Read up to `length` bytes of the logo partition at the bl33 offset.
    With exact=True, returns None unless the full length was read."""
    try:
        with open(GAZELLE_LOGO_DEVICE, "rb") as f:
            f.seek(GAZELLE_LOGO_OFFSET)
            data = f.read(length)
        if exact and len(data) != length:
            return None
        return data
    except Exception:
        return None


def _gazelle_update_pending(addon_path=None):
    """True if the bundled bl33 is newer than the one in the logo partition."""
    path = _gazelle_update_path(addon_path)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            new_data = f.read()
    except OSError:
        return False
    if not new_data:
        return False

    cur_blob = _read_logo_region(GAZELLE_SCAN_MAX, exact=False)
    if not cur_blob:
        return False  # can't read the partition - don't offer an update we can't verify

    new_info = _parse_uboot_build(new_data)
    cur_info = _parse_uboot_build(cur_blob)
    if new_info and cur_info:
        return new_info[0] > cur_info[0]

    # No usable timestamp on one side: fall back to a byte comparison
    return cur_blob[:len(new_data)] != new_data


def _write_logo_region(data, dev=GAZELLE_LOGO_DEVICE):
    """Equivalent of: dd if=bl33.bin.gazl of=/dev/logo bs=1 seek=$((0x10000))
    (without truncating the partition, and with a read-back verification)."""
    # "r+b" = write in place, never truncate
    with open(dev, "r+b") as f:
        f.seek(GAZELLE_LOGO_OFFSET)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    subprocess.run(["sync"], check=False)

    # Verify
    readback = _read_logo_region(len(data))
    if readback != data:
        raise RuntimeError("Verification failed after write")

def _apply_gazelle_update(addon_path):
    src = _gazelle_update_path(addon_path)
    if not os.path.exists(src):
        _notify("Cube Update", f"{GAZELLE_UPDATE_NAME} not found")
        return False

    if not os.path.exists(GAZELLE_LOGO_DEVICE):
        _notify("Cube Update", "logo partition not found")
        return False

    with open(src, "rb") as f:
        new_data = f.read()
    if not new_data:
        _notify("Cube Update", f"{GAZELLE_UPDATE_NAME} is empty")
        return False

    new_info = _parse_uboot_build(new_data)
    cur_blob = _read_logo_region(GAZELLE_SCAN_MAX, exact=False)
    cur_info = _parse_uboot_build(cur_blob) if cur_blob else None

    message = (
        "Proceed with Cube update?\n\n"
        f"Current: {cur_info[1] if cur_info else 'Unknown'}\n"
        f"Update: {new_info[1] if new_info else 'Unknown'}\n\n"
        "Do not power off during the update."
    )
    if not xbmcgui.Dialog().yesno("Confirm Cube Update", message):
        return False

    _write_logo_region(new_data)
    _notify("Cube Update", "Update applied successfully", xbmcgui.NOTIFICATION_INFO)
    return True


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def is_update_pending(device_id=None, addon_path=None):
    """Device-aware check used by the main menu."""
    device_id = device_id or get_device_id()

    if device_id == RAVEN_DEVICE_ID:
        gz = os.path.join(_update_dir(addon_path), "misc.img.gz")
        if not os.path.exists(gz):
            return False
        update_ts = _read_gz_misc_timestamp(gz)
        current_ts = _read_misc_timestamp("/dev/misc")
        return bool(update_ts and current_ts and update_ts > current_ts)

    if device_id == GAZELLE_DEVICE_ID:
        return _gazelle_update_pending(addon_path)

    return False


def _apply_raven_update(addon_path):
    img_gz_path = os.path.join(addon_path, "resources", "update", "misc.img.gz")

    if not os.path.exists(img_gz_path):
        _notify("Cube Update", "misc.img.gz not found")
        return False

    current_ts = _read_misc_timestamp("/dev/misc")
    update_ts = _read_gz_misc_timestamp(img_gz_path)

    message = f"Proceed with Cube update?\n\nCurrent: {current_ts or 'Unknown'}\nUpdate: {update_ts or 'Unknown'}"
    if not xbmcgui.Dialog().yesno("Confirm Cube Update", message):
        return False

    with open("/dev/misc", "wb") as misc:
        subprocess.run(["gzip", "-dc", img_gz_path], stdout=misc, check=True)
    _copy_dtb(addon_path)
    _ensure_env(addon_path)
    _copy_boot_menu_files(addon_path)

    _notify("Cube Update", "Update applied successfully", xbmcgui.NOTIFICATION_INFO)
    return True


def apply_update():
    try:
        addon_path = xbmcaddon.Addon().getAddonInfo('path')
        device_id = get_device_id()

        if device_id == RAVEN_DEVICE_ID:
            return _apply_raven_update(addon_path)
        if device_id == GAZELLE_DEVICE_ID:
            return _apply_gazelle_update(addon_path)

        _notify("Cube Update", f"Unsupported device: {device_id or 'Unknown'}")
    except Exception as e:
        _notify("Cube Update Failed", str(e))

    return False
