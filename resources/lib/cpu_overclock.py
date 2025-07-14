# resources/lib/cpu_overclock.py

import os
import xbmcgui
import subprocess
import xml.etree.ElementTree as ET

CONFIG_PATH = "/flash/config.ini"
SETTINGS_PATH = "/storage/.kodi/userdata/addon_data/service.coreelec.settings/oe_settings.xml"
AUTOSTART_PATH = "/storage/.config/autostart.sh"


def _read_current_freq():
    try:
        with open(CONFIG_PATH, 'r') as f:
            lines = f.readlines()
        freq = {"a73": None, "a53": None}
        for line in lines:
            if "max_freq_a73" in line:
                if line.strip().startswith("#"):
                    freq["a73"] = "2208"
                else:
                    freq["a73"] = line.strip().split('=')[1].strip("'\"\n")
            elif "max_freq_a53" in line:
                if line.strip().startswith("#"):
                    freq["a53"] = "1908"
                else:
                    freq["a53"] = line.strip().split('=')[1].strip("'\"\n")
        if freq["a73"] is None:
            freq["a73"] = "2208"
        if freq["a53"] is None:
            freq["a53"] = "1908"
        return freq
    except Exception:
        return {"a73": "2208", "a53": "1908"}  # Fallback to stock

def _read_current_governor():
    try:
        tree = ET.parse(SETTINGS_PATH)
        root = tree.getroot()
        node = root.find("settings/hardware/cpu_governor")
        if node is not None and node.text in ("ondemand", "performance"):
            return node.text
    except Exception:
        pass
    return "ondemand"

def _remount_flash(rw=True):
    try:
        mode = "rw" if rw else "ro"
        subprocess.run(["mount", "-o", f"remount,{mode}", "/flash"], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def _write_freq_setting(a73_val, a53_val):
    try:
        remounted = _remount_flash(True)

        with open(CONFIG_PATH, 'r') as f:
            lines = f.readlines()

        found_a73 = found_a53 = False
        for i in range(len(lines)):
            if "max_freq_a73" in lines[i]:
                lines[i] = f"max_freq_a73='{a73_val}'\n"
                found_a73 = True
            elif "max_freq_a53" in lines[i]:
                lines[i] = f"max_freq_a53='{a53_val}'\n"
                found_a53 = True

        if not found_a73:
            lines.append(f"max_freq_a73='{a73_val}'\n")
        if not found_a53:
            lines.append(f"max_freq_a53='{a53_val}'\n")

        with open(CONFIG_PATH, 'w') as f:
            f.writelines(lines)

        if remounted:
            _remount_flash(False)

        xbmcgui.Dialog().notification("CPU Overclock", f"A73: {a73_val}, A53: {a53_val}", xbmcgui.NOTIFICATION_INFO, 4000)

    except Exception as e:
        xbmcgui.Dialog().notification("Overclock Error", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

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

        if governor == "ondemand":
            _write_autostart_fixed()
        else:
            _remove_autostart_lines()

        xbmcgui.Dialog().notification("CPU Governor", f"Set to {governor}", xbmcgui.NOTIFICATION_INFO, 3000)
    except Exception as e:
        xbmcgui.Dialog().notification("Governor Error", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def _write_autostart_fixed():
    try:
        fixed_lines = [
            "#!/bin/sh\n",
            "echo 1908000 > /sys/bus/cpu/devices/cpu0/cpufreq/scaling_min_freq\n",
            "echo 2208000 > /sys/bus/cpu/devices/cpu2/cpufreq/scaling_min_freq\n"
        ]

        if os.path.exists(AUTOSTART_PATH):
            with open(AUTOSTART_PATH, 'r') as f:
                existing = f.readlines()
        else:
            existing = []

        if not existing:
            lines = fixed_lines
        else:
            lines = []
            for line in existing:
                if "cpu0" not in line and "cpu2" not in line:
                    lines.append(line)
            lines = [l if i != 0 else "#!/bin/sh\n" for i, l in enumerate(lines)]
            lines += fixed_lines[1:]

        with open(AUTOSTART_PATH, 'w') as f:
            f.writelines(lines)

    except Exception as e:
        xbmcgui.Dialog().notification("Autostart Error", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def _remove_autostart_lines():
    try:
        if not os.path.exists(AUTOSTART_PATH):
            return

        with open(AUTOSTART_PATH, 'r') as f:
            lines = f.readlines()

        lines = [line for line in lines if "cpu0" not in line and "cpu2" not in line]

        with open(AUTOSTART_PATH, 'w') as f:
            f.writelines(lines)

    except Exception as e:
        xbmcgui.Dialog().notification("Autostart Cleanup Error", str(e), xbmcgui.NOTIFICATION_ERROR, 5000)

def show_overclock_menu():
    freq = _read_current_freq()
    current_governor = _read_current_governor()

    a73_choices = ["2208MHz (Stock)", "2304MHz (Overclock)", "2400MHz (Overclock)"]
    a53_choices = ["1908MHz (Stock)", "2016MHz (Overclock)"]
    a73_map = {0: "2208", 1: "2304", 2: "2400"}
    a53_map = {0: "1908", 1: "2016"}
    a73_inv = {v: k for k, v in a73_map.items()}
    a53_inv = {v: k for k, v in a53_map.items()}

    a73_sel = xbmcgui.Dialog().select(
        f"A73 Core Frequency (Current: {freq['a73']}MHz)",
        a73_choices,
        preselect=a73_inv.get(freq["a73"], 0)
    )
    if a73_sel == -1:
        return

    a53_sel = xbmcgui.Dialog().select(
        f"A53 core Frequency (Current: {freq['a53']}MHz)",
        a53_choices,
        preselect=a53_inv.get(freq["a53"], 0)
    )
    if a53_sel == -1:
        return

    a73_val = a73_map[a73_sel]
    a53_val = a53_map[a53_sel]
    _write_freq_setting(a73_val, a53_val)

    if a73_val != "2208" or a53_val != "1908":
        gov_map = {0: "performance", 1: "ondemand"}
        gov_inv = {"performance": 0, "ondemand": 1}

        gov_sel = xbmcgui.Dialog().select(
            "CPU Governor",
            ["performance", "ondemand (only use overclock freq during heavy loads)"],
            preselect=gov_inv.get(current_governor, 0)
        )
        if gov_sel != -1:
            _set_governor(gov_map[gov_sel])
    else:
        _set_governor("performance")
