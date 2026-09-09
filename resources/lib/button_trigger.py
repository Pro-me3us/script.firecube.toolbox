import xbmc
import xbmcgui
import subprocess
from pathlib import Path

PRODUCT_PATH = Path("/media/product")
ENV_TXT = PRODUCT_PATH / "env.txt"

DEVICE_TREE_ID_PATH = "/proc/device-tree/amlogic-dt-id"

# Maps a board's amlogic-dt-id value to the partition device node that
# holds its env.txt (uboot environment) file.
BOARD_PARTITION_MAP = {
    "g12brevb_raven_2g": "/dev/product",
    "t7_gazelle_pvt": "/dev/vendor_boot",
}

BUTTON_KEYS = [
    ("Volume Up", "btn-volup"),
    ("Action", "btn-action"),
    ("Volume Down", "btn-voldown"),
]

BOOT_TARGETS = {
    "FireOS": "run storeboot",
    "CoreELEC": "run coreelec",
    "USB Boot": "run usb_boot",
    "Clear": ""
}

def notify(msg):
    xbmcgui.Dialog().notification("Cube Button Triggers", msg, xbmcgui.NOTIFICATION_INFO, 4000)

def log(msg):
    xbmc.log(f"[Cube Button Triggers] {msg}", level=getattr(xbmc, "LOGNOTICE", xbmc.LOGINFO))

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

def get_cube_button_triggers():
    try:
        mount_product()
        if not ENV_TXT.exists():
            notify("env.txt not found")
            return

        lines = ENV_TXT.read_text().splitlines()
        using_old_menu = any(line.startswith("trigger_menu=") for line in lines)

        if not using_old_menu:
            notify("This option only available with old boot menu.")
            return

        kv = {line.split("=")[0]: line.split("=")[1] for line in lines if "=" in line}
        selected = 0

        while True:
            menu = []
            for label, key in BUTTON_KEYS:
                current = kv.get(key, "")
                for name, cmd in BOOT_TARGETS.items():
                    if cmd == current:
                        menu.append(f"{label} - {name}")
                        break
                else:
                    menu.append(f"{label} - unset")

            sel = xbmcgui.Dialog().select("Set Cube Button Boot Triggers", menu, preselect=selected)
            if sel == -1:
                break
            selected = sel

            label, key = BUTTON_KEYS[sel]
            opts = list(BOOT_TARGETS.keys())
            current_val = kv.get(key, "")
            current_index = next((i for i, name in enumerate(opts) if BOOT_TARGETS[name] == current_val), 0)
            method_sel = xbmcgui.Dialog().select(f"Set {label} Action", opts, preselect=current_index)
            if method_sel == -1:
                continue

            selected_value = BOOT_TARGETS[opts[method_sel]]
            updated = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={selected_value}"
                    updated = True
                    break
            if not updated:
                lines += [f"{key}={selected_value}"]

            ENV_TXT.write_text("\n".join(lines) + "\n")
            notify(f"Updated {key} to {opts[method_sel]}")

    except Exception as e:
        notify(f"Error: {e}")
    finally:
        unmount_product()
