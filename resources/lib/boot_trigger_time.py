import xbmc
import xbmcaddon
import xbmcgui
import subprocess
from pathlib import Path

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')

PRODUCT_PATH = Path("/media/product")
ENV_TXT = PRODUCT_PATH / "env.txt"

DEVICE_TREE_ID_PATH = "/proc/device-tree/amlogic-dt-id"

# Maps a board's amlogic-dt-id value to the partition device node that
# holds its env.txt (uboot environment) file.
BOARD_PARTITION_MAP = {
    "g12brevb_raven_2g": "/dev/product",
    "t7_gazelle_pvt": "/dev/vendor_boot",
}

def notify(msg):
    xbmcgui.Dialog().notification(__addonname__, msg, xbmcgui.NOTIFICATION_INFO, 3000)

def log(msg):
    xbmc.log(f"[{__addonname__}] {msg}", level=getattr(xbmc, "LOGNOTICE", xbmc.LOGINFO))

def get_dt_id():
    try:
        with open(DEVICE_TREE_ID_PATH, "rb") as f:
            data = f.read()
        # device-tree string properties are null-terminated; strip that
        # (and any surrounding whitespace) before comparing.
        return data.split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
    except Exception as e:
        log(f"Failed to read {DEVICE_TREE_ID_PATH}: {e}")
        return None

def get_boot_partition():
    dt_id = get_dt_id()
    if dt_id is None:
        log("Could not determine device-tree id; defaulting to /dev/product")
        return "/dev/product"

    partition = BOARD_PARTITION_MAP.get(dt_id)
    if partition is None:
        log(f"Unrecognized device-tree id '{dt_id}'; defaulting to /dev/product")
        return "/dev/product"

    log(f"Device-tree id '{dt_id}' resolved to partition '{partition}'")
    return partition

def mount_product():
    PRODUCT_PATH.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mount", get_boot_partition(), str(PRODUCT_PATH)], check=False)

def unmount_product():
    subprocess.run(["umount", str(PRODUCT_PATH)], check=False)
    try:
        PRODUCT_PATH.rmdir()
    except:
        pass

def set_boot_led_delay():
    current_delay = get_current_led_delay()
    seconds = xbmcgui.Dialog().numeric(0, "LED trigger delay (seconds)", str(current_delay))

    try:
        delay = int(seconds) * 5
        if delay < 0:
            raise ValueError("Negative")
    except Exception:
        notify("Invalid input. Must be a positive integer.")
        return

    try:
        mount_product()
    except:
        notify(f"Failed to mount {get_boot_partition()}")
        return

    if not ENV_TXT.exists():
        notify("env.txt not found")
        unmount_product()
        return

    lines_out = []
    found_key = False
    found_trigger_menu = False
    found_irremote_update = False

    with ENV_TXT.open("r") as f:
        lines = f.readlines()

    using_old_menu = any(line.startswith("trigger_menu=") for line in lines)
    key_to_set = "irkey-loop-count" if using_old_menu else "trigger_timeout"
    new_value = str(delay)

    for line in lines:
        if line.startswith("irkey-waittime="):
            continue  # remove
        elif line.startswith(f"{key_to_set}="):
            lines_out.append(f"{key_to_set}={new_value}\n")
            found_key = True
        elif line.startswith("trigger_menu="):
            found_trigger_menu = True
            if delay == 0:
                lines_out.append("trigger_menu=\n")
            else:
                lines_out.append(line)
        elif line.startswith("irremote_update="):
            found_irremote_update = True
            if delay == 0:
                lines_out.append("irremote_update=\n")
            elif using_old_menu:
                continue  # remove if not delay 0
        else:
            lines_out.append(line)

    if not found_key:
        lines_out.append(f"{key_to_set}={new_value}\n")

    if delay == 0:
        if not found_trigger_menu:
            lines_out.append("trigger_menu=\n")
        if not found_irremote_update:
            lines_out.append("irremote_update=\n")

    with ENV_TXT.open("w") as f:
        f.writelines(lines_out)

    unmount_product()
    notify(f"Boot LED delay set to {delay / 5:.0f} second(s)")

def get_current_led_delay():
    try:
        mount_product()
        if not ENV_TXT.exists():
            return 0
        with ENV_TXT.open("r") as f:
            lines = f.readlines()
        using_old_menu = any(line.startswith("trigger_menu=") for line in lines)
        for line in lines:
            if using_old_menu and line.startswith("irkey-loop-count="):
                return int(line.strip().split("=")[1]) // 5
            elif not using_old_menu and line.startswith("trigger_timeout="):
                return int(line.strip().split("=")[1]) // 5
        return 0
    except:
        return 0
    finally:
        unmount_product()
