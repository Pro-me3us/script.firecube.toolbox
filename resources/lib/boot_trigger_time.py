import xbmc
import xbmcaddon
import xbmcgui
import subprocess
from pathlib import Path

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')

def notify(msg):
    xbmcgui.Dialog().notification(__addonname__, msg, xbmcgui.NOTIFICATION_INFO, 3000)

def set_boot_led_delay():
    current_delay = get_current_led_delay()
    seconds = xbmcgui.Dialog().numeric(0, "LED trigger delay (seconds)", str(current_delay))

    try:
        delay = int(seconds)
        if delay < 0:
            raise ValueError("Negative")
    except Exception:
        notify("Invalid input. Must be a positive integer.")
        return

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

    lines_out = []
    found_count = False
    found_update = False

    with env_path.open("r") as f:
        for line in f:
            if line.startswith("irkey-loop-count="):
                lines_out.append(f"irkey-loop-count={delay}\n")
                found_count = True
            elif line.startswith("irremote_update="):
                if delay == 0:
                    lines_out.append("irremote_update=\n")
                found_update = True
                if delay != 0:
                    continue  # Remove line
            elif line.startswith("irkey-waittime="):
                continue  # Remove line
            else:
                lines_out.append(line)

    if not found_count:
        lines_out.append(f"irkey-loop-count={delay}\n")
    if delay == 0 and not found_update:
        lines_out.append("irremote_update=\n")

    with env_path.open("w") as f:
        f.writelines(lines_out)

    subprocess.run(["umount", "/media/product"], check=False)
    Path("/media/product").rmdir()

    notify(f"Boot LED delay set to {delay} second(s)")

def get_current_led_delay():
    try:
        Path("/media/product").mkdir(parents=True, exist_ok=True)
        subprocess.run(["mount", "/dev/product", "/media/product"], check=True)
        env_path = Path("/media/product/env.txt")
        if not env_path.exists():
            return 0

        with env_path.open("r") as f:
            for line in f:
                if line.startswith("irkey-loop-count="):
                    return int(line.strip().split("=")[1])
    except:
        return 0
    finally:
        subprocess.run(["umount", "/media/product"], check=False)
