import xbmcgui
import subprocess
from pathlib import Path
import os
import time

OLD_MENU_TRIGGERS = [
    ("FireOS", "irkey-alt-fireos", "irkey-fireos", "0xB54A7D02"),
    ("CoreELEC", "irkey-alt-coreelec", "irkey-coreelec", "0xBA457D02"),
    ("USB Boot", "irkey-alt-usbboot", "irkey-usbboot", "0xF20D7D02"),
    ("TWRP", "irkey-alt-recovery", "irkey-recovery", "0xB24D7D02"),
    ("Fastboot", "irkey-alt-fastboot", "irkey-fastboot", "0xB7487D02"),
    ("Amlogic Update", "irkey-alt-update", "irkey-update", "0xB6497D02"),
]

NEW_MENU_TRIGGERS = [
    ("Up", "irkey-alt-up", "irkey-up", "0xF30C7D02"),
    ("Down", "irkey-alt-down", "irkey-down", "0xE6197D02"),
    ("Select", "irkey-alt-ok", "irkey-ok", "0xB34C7D02"),
]

PRODUCT_PATH = Path("/media/product")
ENV_TXT = PRODUCT_PATH / "env.txt"

def notify(msg):
    xbmcgui.Dialog().notification("IR Boot Triggers", msg, xbmcgui.NOTIFICATION_INFO, 4000)

def mount_product():
    PRODUCT_PATH.mkdir(parents=True, exist_ok=True)
    subprocess.run(["mount", "/dev/product", str(PRODUCT_PATH)], check=False)

def unmount_product():
    subprocess.run(["umount", str(PRODUCT_PATH)], check=False)
    try:
        PRODUCT_PATH.rmdir()
    except Exception:
        pass
    return None

def detect_ir_code(timeout=15):
    debug_path = Path("/sys/class/remote/amremote/debug_enable")
    if not debug_path.exists():
        notify("amremote driver not loaded")
        return None
    try:
        debug_path.write_text("1")
        if debug_path.read_text().strip() != "1":
            notify("Failed to enable debug mode")
            return None
        subprocess.run(["dmesg", "--clear"], check=False)
        marker = f"IR_DETECTION_START_{int(time.time())}"
        with open("/dev/kmsg", "w") as kmsg:
            kmsg.write(marker + "\n")
        dlg = xbmcgui.DialogProgress()
        dlg.create("IR Detection", "Press a button on the remote to detect IR code")
        seen_codes = set()
        start_time = time.time()
        while not dlg.iscanceled() and time.time() - start_time < timeout:
            result = subprocess.run(["dmesg"], capture_output=True, text=True)
            lines = result.stdout.splitlines()
            for i, line in enumerate(lines):
                if marker in line:
                    for subsequent_line in lines[i+1:]:
                        if "framecode=" in subsequent_line:
                            parts = subsequent_line.split("framecode=")
                            if len(parts) > 1:
                                code = parts[1].strip().split()[0]
                                if code == "0x0" or code in seen_codes:
                                    continue
                                if code.startswith("0x") and len(code) == 10:
                                    seen_codes.add(code)
                                    dlg.close()
                                    notify(f"IR code detected: {code}")
                                    return code
            time.sleep(0.1)
            percent = int((time.time() - start_time) / timeout * 100)
            dlg.update(percent, "Waiting for IR input... Press a remote button")
        dlg.close()
        notify("IR detection cancelled or timeout.")
    finally:
        try:
            debug_path.write_text("0")
        except Exception:
            pass
    return None

def get_ir_boot_triggers():
    selected_trigger = 0
    first_loop = True
    while True:
        try:
            mount_product()
            if not ENV_TXT.exists():
                notify("env.txt not found")
                return

            lines = ENV_TXT.read_text().splitlines()
            kv = {line.split("=")[0]: line.split("=")[1] for line in lines if "=" in line}
            using_old_menu = "trigger_menu" in kv and kv["trigger_menu"] != "run menu_loop"
            auto_boot_menu = kv.get("trigger_menu") == "run menu_loop"
            current_timeout = kv.get("menu_timeout", "5")

            main_menu = [
                f"Menu Style: {'Old' if using_old_menu else 'New'} (toggle)"
            ]

            trigger_set = OLD_MENU_TRIGGERS if using_old_menu else NEW_MENU_TRIGGERS

            if not using_old_menu:
                main_menu.append(f"Show boot menu automatically: {'Yes (' + str(int(current_timeout) // 5) + 'sec timeout)' if auto_boot_menu else 'No'}")

            for label, key1, key2, default in trigger_set:
                val1 = kv.get(key1, "")
                val2 = kv.get(key2, "")
                val1_disp = f"0x{val1[2:].upper()}" if val1.lower().startswith("0x") else (val1 or "unset")
                val2_disp = f"0x{val2[2:].upper()}" if val2.lower().startswith("0x") else default
                main_menu.append(f"{label} - val1: {val1_disp} | val2: {val2_disp}")

            offset = 2 if not using_old_menu else 1
            sel = xbmcgui.Dialog().select("Set IR Boot Triggers", main_menu, preselect=selected_trigger + offset if not first_loop else 0)
            first_loop = False
            if sel == -1:
                break

            if sel == 0:
                if using_old_menu:
                    lines = [line for line in lines if not line.startswith("trigger_menu=")]
                    notify("Switched to New Boot Menu")
                else:
                    lines += ["trigger_menu="]
                    notify("Switched to Old IR Menu")
                ENV_TXT.write_text("\n".join(lines) + "\n")
                continue

            if not using_old_menu and sel == 1:
                auto_boot_menu = not auto_boot_menu
                lines = [line for line in lines if not line.startswith("trigger_menu=") and not line.startswith("irremote_update=")]
                if auto_boot_menu:
                    lines += ["trigger_menu=run menu_loop", "irremote_update="]
                    timeout_input = xbmcgui.Dialog().numeric(0, "Menu timeout (seconds)", str(int(current_timeout) // 5))
                    try:
                        timeout_val = int(timeout_input) * 5
                        lines = [line for line in lines if not line.startswith("menu_timeout=")]
                        lines += [f"menu_timeout={timeout_val}"]
                    except Exception:
                        notify("Invalid timeout value")
                ENV_TXT.write_text("\n".join(lines) + "\n")
                continue

            selected_trigger = sel - (2 if not using_old_menu else 1)
            label, key1, key2, default = trigger_set[selected_trigger]
            sub_opts = [
                f"Edit val1 ({key1}) - current: {kv.get(key1, 'unset')}",
                f"Edit val2 ({key2}) - current: {kv.get(key2, default)}"
            ]
            sub_sel = xbmcgui.Dialog().select(f"{label} IR Code", sub_opts)
            if sub_sel == -1:
                continue
            edit_key = key1 if sub_sel == 0 else key2
            current_val = kv.get(edit_key) if edit_key in kv else (default if sub_sel == 1 else "")
            method = xbmcgui.Dialog().select("Choose input method", ["Enter manually", "Detect from IR remote"])
            if method == -1:
                continue
            elif method == 1:
                ir_code = detect_ir_code()
                if not ir_code:
                    continue
                choice = ir_code
            else:
                choice = xbmcgui.Dialog().input(
                    f"Enter IR code for {edit_key}",
                    defaultt=current_val,
                    type=xbmcgui.INPUT_ALPHANUM
                ).strip()
            if not choice:
                lines = [line for line in lines if not line.startswith(f"{edit_key}=")]
                ENV_TXT.write_text("\n".join(lines) + "\n")
                notify(f"Deleted {edit_key}")
                continue
            if not choice.lower().startswith("0x") or len(choice) != 10:
                notify("Invalid code. Must be 0x followed by 8 hex digits.")
                continue
            formatted = "0x" + choice[2:].upper()
            updated = False
            for i, line in enumerate(lines):
                if line.startswith(f"{edit_key}="):
                    lines[i] = f"{edit_key}={formatted}"
                    updated = True
                    break
            if not updated:
                lines += [f"{edit_key}={formatted}"]
            ENV_TXT.write_text("\n".join(lines) + "\n")
            notify(f"Updated {edit_key} to {formatted}")
        except Exception as e:
            notify(f"Error: {e}")
            break
        finally:
            unmount_product()
