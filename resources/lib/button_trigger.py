import xbmcgui
import subprocess
from pathlib import Path

PRODUCT_PATH = Path("/media/product")
ENV_TXT = PRODUCT_PATH / "env.txt"

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

def mount_product():
    PRODUCT_PATH.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mount", "/dev/product", str(PRODUCT_PATH)], check=False)

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