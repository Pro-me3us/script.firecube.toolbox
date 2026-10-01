# File: resources/lib/zram.py
import os
import re
import shutil
import subprocess

import xbmcaddon
import xbmcgui

TITLE = "ZRAM swap"
SERVICE_NAME = "zram.service"
ADDON_PATH = xbmcaddon.Addon().getAddonInfo('path')
SERVICE_SRC = os.path.join(ADDON_PATH, "resources", "service", SERVICE_NAME)
SERVICE_DST_DIR = "/storage/.config/system.d"
SERVICE_DST = os.path.join(SERVICE_DST_DIR, SERVICE_NAME)

DEFAULT_SIZE_MB = 1024
MIN_SIZE_MB = 128
MAX_SIZE_MB = 2048
MIN_MEM_LIMIT_MB = 64
MEM_LIMIT_SYS = "/sys/block/zram0/mem_limit"

DEFAULT_SWAPPINESS = 100
SWAPPINESS_PROC = "/proc/sys/vm/swappiness"

DISKSIZE_RE = re.compile(r"(echo\s+)(\d+)([MG])(\s*>\s*/sys/block/zram0/disksize)")
MEMLIMIT_RE = re.compile(r"(echo\s+)(\d+)([MG])(\s*>\s*/sys/block/zram0/mem_limit)")
SWAPPINESS_RE = re.compile(r"(echo\s+)(\d+)(\s*>\s*/proc/sys/vm/swappiness)")


def _systemctl(*args):
    return subprocess.call(
        ["systemctl", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def is_active():
    return _systemctl("is-active", "--quiet", SERVICE_NAME) == 0


def is_installed():
    return os.path.exists(SERVICE_DST)


def get_size_mb():
    """Read the configured zram size (MB) from the installed unit file."""
    try:
        with open(SERVICE_DST) as f:
            m = DISKSIZE_RE.search(f.read())
        if m:
            value = int(m.group(2))
            return value * 1024 if m.group(3) == "G" else value
    except (OSError, ValueError):
        pass
    return None


def _to_mb(m):
    value = int(m.group(2))
    return value * 1024 if m.group(3) == "G" else value


def get_mem_limit_mb():
    """Read the configured zram memory limit (MB) from the installed unit file."""
    try:
        with open(SERVICE_DST) as f:
            m = MEMLIMIT_RE.search(f.read())
        if m:
            return _to_mb(m)
    except (OSError, ValueError):
        pass
    return None


def _set_size_in_unit(size_mb):
    """Rewrite disksize in the installed unit, scaling mem_limit proportionally."""
    with open(SERVICE_DST) as f:
        text = f.read()

    old_size = DISKSIZE_RE.search(text)
    old_limit = MEMLIMIT_RE.search(text)
    if old_size and old_limit and _to_mb(old_size) > 0:
        ratio = _to_mb(old_limit) / _to_mb(old_size)
        mem_limit = round(size_mb * ratio)
    else:
        mem_limit = size_mb // 2
    mem_limit = max(MIN_MEM_LIMIT_MB, min(size_mb, mem_limit))

    text = DISKSIZE_RE.sub(lambda m: f"{m.group(1)}{size_mb}M{m.group(4)}", text)
    text = MEMLIMIT_RE.sub(lambda m: f"{m.group(1)}{mem_limit}M{m.group(4)}", text)
    with open(SERVICE_DST, "w") as f:
        f.write(text)


def _set_mem_limit_in_unit(limit_mb):
    with open(SERVICE_DST) as f:
        text = f.read()
    text, count = MEMLIMIT_RE.subn(lambda m: f"{m.group(1)}{limit_mb}M{m.group(4)}", text)
    if count == 0:
        raise OSError("mem_limit line not found in service file")
    with open(SERVICE_DST, "w") as f:
        f.write(text)


def set_mem_limit():
    size_mb = get_size_mb() or DEFAULT_SIZE_MB
    current = get_mem_limit_mb() or size_mb // 2
    value = xbmcgui.Dialog().numeric(
        0, f"ZRAM memory limit in MB ({MIN_MEM_LIMIT_MB}-{size_mb})", str(current)
    )
    if not value:
        return False

    try:
        limit_mb = int(value)
    except ValueError:
        return False

    if limit_mb < MIN_MEM_LIMIT_MB or limit_mb > size_mb:
        xbmcgui.Dialog().ok(
            TITLE, f"Memory limit must be between {MIN_MEM_LIMIT_MB} and {size_mb} MB (the ZRAM size)."
        )
        return False

    try:
        _set_mem_limit_in_unit(limit_mb)
        # Apply immediately without restarting the service (keeps swap contents)
        with open(MEM_LIMIT_SYS, "w") as f:
            f.write(f"{limit_mb}M")
    except OSError as e:
        xbmcgui.Dialog().ok(TITLE, f"Failed to set memory limit: {e}")
        return False

    _systemctl("daemon-reload")
    xbmcgui.Dialog().ok(TITLE, f"ZRAM memory limit set to {limit_mb} MB.")
    return True


def get_max_swappiness():
    """Kernels before 5.8 accept swappiness 0-100; 5.8 and newer accept 0-200."""
    m = re.match(r"(\d+)\.(\d+)", os.uname().release)
    if m and (int(m.group(1)), int(m.group(2))) >= (5, 8):
        return 200
    return 100


def get_swappiness():
    """Read the configured swappiness from the installed unit file."""
    try:
        with open(SERVICE_DST) as f:
            m = SWAPPINESS_RE.search(f.read())
        if m:
            return int(m.group(2))
    except (OSError, ValueError):
        pass
    try:
        with open(SWAPPINESS_PROC) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return DEFAULT_SWAPPINESS


def _set_swappiness_in_unit(value):
    with open(SERVICE_DST) as f:
        text = f.read()
    text, count = SWAPPINESS_RE.subn(lambda m: f"{m.group(1)}{value}{m.group(3)}", text)
    if count == 0:
        raise OSError("swappiness line not found in service file")
    with open(SERVICE_DST, "w") as f:
        f.write(text)


def set_swappiness():
    max_value = get_max_swappiness()
    value = xbmcgui.Dialog().numeric(
        0, f"ZRAM swappiness (0-{max_value})", str(get_swappiness())
    )
    if not value:
        return False

    try:
        swappiness = int(value)
    except ValueError:
        return False

    if swappiness < 0 or swappiness > max_value:
        xbmcgui.Dialog().ok(TITLE, f"Swappiness must be between 0 and {max_value} on this kernel.")
        return False

    try:
        _set_swappiness_in_unit(swappiness)
        # Apply immediately without restarting the service (keeps swap contents)
        with open(SWAPPINESS_PROC, "w") as f:
            f.write(str(swappiness))
    except OSError as e:
        xbmcgui.Dialog().ok(TITLE, f"Failed to set swappiness: {e}")
        return False

    _systemctl("daemon-reload")
    xbmcgui.Dialog().ok(TITLE, f"Swappiness set to {swappiness}.")
    return True


def enable_service():
    try:
        os.makedirs(SERVICE_DST_DIR, exist_ok=True)
        shutil.copyfile(SERVICE_SRC, SERVICE_DST)
        os.chmod(SERVICE_DST, 0o644)
        _set_size_in_unit(DEFAULT_SIZE_MB)
    except OSError as e:
        xbmcgui.Dialog().ok(TITLE, f"Failed to install {SERVICE_NAME}: {e}")
        return False

    _systemctl("daemon-reload")
    if _systemctl("enable", "--now", SERVICE_NAME) != 0:
        xbmcgui.Dialog().ok(
            TITLE,
            "Failed to start the ZRAM service. The kernel may not include zram support."
        )
        return False

    xbmcgui.Dialog().ok(TITLE, f"ZRAM swap enabled ({DEFAULT_SIZE_MB} MB).")
    return True


def disable_service():
    _systemctl("disable", "--now", SERVICE_NAME)
    try:
        if os.path.exists(SERVICE_DST):
            os.remove(SERVICE_DST)
    except OSError as e:
        xbmcgui.Dialog().ok(TITLE, f"ZRAM stopped, but {SERVICE_NAME} could not be deleted: {e}")
        return False

    _systemctl("daemon-reload")
    xbmcgui.Dialog().ok(TITLE, "ZRAM swap disabled and service removed.")
    return True


def set_size():
    current = get_size_mb() or DEFAULT_SIZE_MB
    value = xbmcgui.Dialog().numeric(
        0, f"ZRAM size in MB ({MIN_SIZE_MB}-{MAX_SIZE_MB})", str(current)
    )
    if not value:
        return False

    try:
        size_mb = int(value)
    except ValueError:
        return False

    if size_mb < MIN_SIZE_MB or size_mb > MAX_SIZE_MB:
        xbmcgui.Dialog().ok(TITLE, f"Size must be between {MIN_SIZE_MB} and {MAX_SIZE_MB} MB.")
        return False

    try:
        _set_size_in_unit(size_mb)
    except OSError as e:
        xbmcgui.Dialog().ok(TITLE, f"Failed to update {SERVICE_NAME}: {e}")
        return False

    _systemctl("daemon-reload")
    if _systemctl("restart", SERVICE_NAME) != 0:
        xbmcgui.Dialog().ok(TITLE, "Size saved, but the ZRAM service failed to restart.")
        return False

    xbmcgui.Dialog().ok(TITLE, f"ZRAM size set to {size_mb} MB.")
    return True


def show_zram_menu():
    while True:
        active = is_active()

        if active:
            options = [
                ("Disable ZRAM service (currently ACTIVE)", "disable"),
                (f"Set ZRAM size (currently {get_size_mb() or DEFAULT_SIZE_MB} MB)", "size"),
                (f"Set memory limit (currently {get_mem_limit_mb() or (get_size_mb() or DEFAULT_SIZE_MB) // 2} MB)", "memlimit"),
                (f"Set swappiness (currently {get_swappiness()}, max {get_max_swappiness()})", "swappiness"),
            ]
        else:
            options = [("Enable ZRAM service (currently inactive)", "enable")]

        sel = xbmcgui.Dialog().select(TITLE, [label for label, _ in options])
        if sel < 0:
            return

        action = options[sel][1]
        if action == "enable":
            enable_service()
        elif action == "disable":
            disable_service()
        elif action == "size":
            set_size()
        elif action == "memlimit":
            set_mem_limit()
        elif action == "swappiness":
            set_swappiness()
