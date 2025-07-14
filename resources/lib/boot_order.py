# resources/lib/boot_order.py

import xbmc
import xbmcaddon
import xbmcgui
import subprocess
from pathlib import Path

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')

def notify(msg):
    xbmcgui.Dialog().notification(__addonname__, msg, xbmcgui.NOTIFICATION_INFO, 3000)

def log(msg):
    xbmc.log(f"[{__addonname__}] {msg}", level=xbmc.LOGNOTICE)

def get_current_boot_order():
    try:
        Path("/media/product").mkdir(parents=True, exist_ok=True)
        subprocess.run(["mount", "/dev/product", "/media/product"], check=True)
        env_path = Path("/media/product/env.txt")
        if not env_path.exists():
            return 0

        with env_path.open("r") as f:
            lines = f.read()

        if "uboot_cmd2=run storeboot" in lines:
            return 2
        elif "uboot_cmd3=run coreelec" in lines:
            return 1
        elif "uboot_cmd2=run coreelec" in lines:
            return 3
        else:
            return 0
    except:
        return 0
    finally:
        subprocess.run(["umount", "/media/product"], check=False)

def set_boot_order(option):
    try:
        Path("/media/product").mkdir(parents=True, exist_ok=True)
        subprocess.run(["mount", "/dev/product", "/media/product"], check=True)
    except subprocess.CalledProcessError:
        notify("Failed to mount /dev/product")
        return

    env_path = Path("/media/product/env.txt")
    if not env_path.exists():
        notify("env.txt not found")
        subprocess.run(["umount", "/media/product"], check=False)
        return

    env_lines = []
    if option == 1:
        env_lines = ["uboot_cmd1=", "uboot_cmd2=", "uboot_cmd3="]
    elif option == 2:
        env_lines = ["uboot_cmd1=", "uboot_cmd2=", "uboot_cmd3=run coreelec"]
    elif option == 3:
        env_lines = ["uboot_cmd1=", "uboot_cmd2=run storeboot", "uboot_cmd3="]
    elif option == 4:
        env_lines = ["uboot_cmd1=", "uboot_cmd2=run coreelec", "uboot_cmd3="]
    else:
        notify("Invalid boot option selected")
        subprocess.run(["umount", "/media/product"], check=False)
        return

    lines_out = []
    with env_path.open("r") as f:
        for line in f:
            if line.startswith("uboot_cmd1="):
                lines_out.append(env_lines[0] + "\n")
            elif line.startswith("uboot_cmd2="):
                lines_out.append(env_lines[1] + "\n")
            elif line.startswith("uboot_cmd3="):
                lines_out.append(env_lines[2] + "\n")
            else:
                lines_out.append(line)

    with env_path.open("w") as f:
        f.writelines(lines_out)

    subprocess.run(["umount", "/media/product"], check=False)
    Path("/media/product").rmdir()
    notify(f"Boot order updated to option {option}")

def show_boot_order_menu():
    boot_options = [
        "1) USB Boot > FireOS",
        "2) USB Boot > CoreELEC",
        "3) Direct to FireOS",
        "4) Direct to CoreELEC"
    ]
    current = get_current_boot_order()
    sel = xbmcgui.Dialog().select("Select boot order", boot_options, preselect=current)
    if sel == -1:
        return
    if sel in range(4):
        set_boot_order(sel + 1)
