# resources/lib/cpu_overclock.py

import os
import platform
import xbmcgui
import subprocess
import xml.etree.ElementTree as ET

CONFIG_PATH = "/flash/config.ini"
SETTINGS_PATH = "/storage/.kodi/userdata/addon_data/service.coreelec.settings/oe_settings.xml"
AUTOSTART_PATH = "/storage/.config/autostart.sh"


# --------------------------------------------------
# Kernel detection (cached)
# --------------------------------------------------

def _use_cluster_format():
    try:
        kernel = platform.release().split("-")[0]
        major, minor = map(int, kernel.split(".")[:2])
        return (major, minor) >= (5, 15)
    except Exception:
        return False


USE_CLUSTER_FORMAT = _use_cluster_format()

STOCK_FREQ = {"a73": "2208", "a53": "1908"}


# --------------------------------------------------
# Helper: comment out conflicting config lines
# --------------------------------------------------

def _comment_out(lines, key):
    """
    Comment out any active config line containing key.
    """
    for i, line in enumerate(lines):
        stripped = line.strip()

        if key in stripped and not stripped.startswith("#"):
            lines[i] = "#" + line if not line.startswith("#") else line


# --------------------------------------------------
# Read frequency
# --------------------------------------------------

def _read_current_freq():
    try:
        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()

        freq = STOCK_FREQ.copy()

        if USE_CLUSTER_FORMAT:
            for line in lines:
                if "max_freq_cluster" in line and not line.strip().startswith("#"):
                    value = line.split("=", 1)[1].strip()

                    clusters = dict(item.split(":") for item in value.split(","))
                    freq["a53"] = clusters.get("0", STOCK_FREQ["a53"])
                    freq["a73"] = clusters.get("1", STOCK_FREQ["a73"])
                    break
        else:
            for line in lines:
                if line.strip().startswith("#"):
                    continue

                if "max_freq_a73" in line:
                    freq["a73"] = line.split("=")[1].strip("'\"\n")

                elif "max_freq_a53" in line:
                    freq["a53"] = line.split("=")[1].strip("'\"\n")

        return freq

    except Exception:
        return STOCK_FREQ.copy()


# --------------------------------------------------
# Governor read
# --------------------------------------------------

def _read_current_governor():
    try:
        tree = ET.parse(SETTINGS_PATH)
        node = tree.getroot().find("settings/hardware/cpu_governor")

        if node is not None and node.text in ("ondemand", "performance"):
            return node.text
    except Exception:
        pass

    return "ondemand"


# --------------------------------------------------
# Flash remount
# --------------------------------------------------

def _remount_flash(rw=True):
    try:
        mode = "rw" if rw else "ro"
        subprocess.run(["mount", "-o", f"remount,{mode}", "/flash"], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


# --------------------------------------------------
# Write frequency config (cluster + legacy safe)
# --------------------------------------------------

def _write_freq_setting(a73_val, a53_val):
    try:
        remounted = _remount_flash(True)

        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()

        # --------------------------------------------------
        # CLUSTER FORMAT (kernel >= 5.15)
        # --------------------------------------------------
        if USE_CLUSTER_FORMAT:

            # comment out legacy entries
            _comment_out(lines, "max_freq_a73")
            _comment_out(lines, "max_freq_a53")

            new_line = f"max_freq_cluster=0:{a53_val},1:{a73_val}\n"

            replaced = False
            for i, line in enumerate(lines):
                if "max_freq_cluster" in line and not line.strip().startswith("#"):
                    lines[i] = new_line
                    replaced = True
                    break

            if not replaced:
                lines.append(new_line)

        # --------------------------------------------------
        # LEGACY FORMAT (< 5.15)
        # --------------------------------------------------
        else:

            # comment out cluster entry if present
            _comment_out(lines, "max_freq_cluster")

            replacements = {
                "max_freq_a73": f"max_freq_a73='{a73_val}'\n",
                "max_freq_a53": f"max_freq_a53='{a53_val}'\n"
            }

            found = set()

            for i, line in enumerate(lines):
                for key, value in replacements.items():
                    if key in line and not line.strip().startswith("#"):
                        lines[i] = value
                        found.add(key)

            for key, value in replacements.items():
                if key not in found:
                    lines.append(value)

        with open(CONFIG_PATH, "w") as f:
            f.writelines(lines)

        if remounted:
            _remount_flash(False)

        xbmcgui.Dialog().notification(
            "CPU Overclock",
            f"A73: {a73_val}, A53: {a53_val}",
            xbmcgui.NOTIFICATION_INFO,
            4000
        )

    except Exception as e:
        xbmcgui.Dialog().notification(
            "Overclock Error",
            str(e),
            xbmcgui.NOTIFICATION_ERROR,
            5000
        )


# --------------------------------------------------
# Governor write
# --------------------------------------------------

def _set_governor(governor):
    try:
        tree = ET.parse(SETTINGS_PATH)
        root = tree.getroot()

        settings = root.find("settings")
        if settings is None:
            settings = ET.SubElement(root, "settings")

        hardware = settings.find("hardware")
        if hardware is None:
            hardware = ET.SubElement(settings, "hardware")

        cpu_node = hardware.find("cpu_governor")
        if cpu_node is None:
            cpu_node = ET.SubElement(hardware, "cpu_governor")

        cpu_node.text = governor

        tree.write(SETTINGS_PATH, encoding="utf-8", xml_declaration=True)

        # INTENTIONAL: stock-only autostart for ondemand
        if governor == "ondemand":
            _write_autostart_fixed()
        else:
            _remove_autostart_lines()

        xbmcgui.Dialog().notification(
            "CPU Governor",
            f"Set to {governor}",
            xbmcgui.NOTIFICATION_INFO,
            3000
        )

    except Exception as e:
        xbmcgui.Dialog().notification(
            "Governor Error",
            str(e),
            xbmcgui.NOTIFICATION_ERROR,
            5000
        )


# --------------------------------------------------
# Autostart (INTENTIONAL STOCK VALUES ONLY)
# --------------------------------------------------

def _write_autostart_fixed():
    try:
        fixed_lines = [
            "#!/bin/sh\n",
            f"echo {STOCK_FREQ['a53']}000 > /sys/bus/cpu/devices/cpu0/cpufreq/scaling_min_freq\n",
            f"echo {STOCK_FREQ['a73']}000 > /sys/bus/cpu/devices/cpu2/cpufreq/scaling_min_freq\n"
        ]

        if os.path.exists(AUTOSTART_PATH):
            with open(AUTOSTART_PATH, "r") as f:
                existing = f.readlines()
        else:
            existing = []

        if not existing:
            lines = fixed_lines
        else:
            lines = [l for l in existing if "cpu0" not in l and "cpu2" not in l]

            if not lines or not lines[0].startswith("#!/bin/sh"):
                lines.insert(0, "#!/bin/sh\n")

            lines += fixed_lines[1:]

        with open(AUTOSTART_PATH, "w") as f:
            f.writelines(lines)

    except Exception as e:
        xbmcgui.Dialog().notification(
            "Autostart Error",
            str(e),
            xbmcgui.NOTIFICATION_ERROR,
            5000
        )


def _remove_autostart_lines():
    try:
        if not os.path.exists(AUTOSTART_PATH):
            return

        with open(AUTOSTART_PATH, "r") as f:
            lines = f.readlines()

        lines = [l for l in lines if "cpu0" not in l and "cpu2" not in l]

        with open(AUTOSTART_PATH, "w") as f:
            f.writelines(lines)

    except Exception as e:
        xbmcgui.Dialog().notification(
            "Autostart Cleanup Error",
            str(e),
            xbmcgui.NOTIFICATION_ERROR,
            5000
        )


# --------------------------------------------------
# UI (Kodi-safe)
# --------------------------------------------------

def show_overclock_menu():
    freq = _read_current_freq()
    current_governor = _read_current_governor()

    a73_options = ["2208MHz (Stock)", "2304MHz (Overclock)", "2400MHz (Overclock)"]
    a53_options = ["1908MHz (Stock)", "2016MHz (Overclock)"]

    a73_values = ["2208", "2304", "2400"]
    a53_values = ["1908", "2016"]

    try:
        a73_index = a73_values.index(freq["a73"])
    except ValueError:
        a73_index = 0

    try:
        a53_index = a53_values.index(freq["a53"])
    except ValueError:
        a53_index = 0

    a73_sel = xbmcgui.Dialog().select(
        f"A73 Core Frequency (Current: {freq['a73']}MHz)",
        a73_options,
        preselect=a73_index
    )

    if a73_sel == -1:
        return

    a53_sel = xbmcgui.Dialog().select(
        f"A53 Core Frequency (Current: {freq['a53']}MHz)",
        a53_options,
        preselect=a53_index
    )

    if a53_sel == -1:
        return

    a73_val = a73_values[a73_sel]
    a53_val = a53_values[a53_sel]

    _write_freq_setting(a73_val, a53_val)

    if a73_val != "2208" or a53_val != "1908":
        gov_map = {0: "performance", 1: "ondemand"}
        gov_inv = {"performance": 0, "ondemand": 1}

        gov_sel = xbmcgui.Dialog().select(
            "CPU Governor",
            [
                "performance",
                "ondemand (only use overclock freq during heavy loads)"
            ],
            preselect=gov_inv.get(current_governor, 0)
        )

        if gov_sel != -1:
            _set_governor(gov_map[gov_sel])
    else:
        _set_governor("performance")
