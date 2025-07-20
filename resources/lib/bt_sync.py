import xbmc
import xbmcaddon
import xbmcgui
import os
import shutil
import subprocess
from pathlib import Path
import configparser
import time

__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')

def log(msg):
    xbmc.log(f"[{__addonname__}] {msg}", level=xbmc.LOGNOTICE)

def notify(msg):
    xbmcgui.Dialog().notification(__addonname__, msg, xbmcgui.NOTIFICATION_INFO, 3000)

def parse_bt_config(bt_config_path):
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    config.read(bt_config_path)
    return config

def reverse_hex_bytes(hex_str):
    return ''.join(reversed([hex_str[i:i + 2] for i in range(0, len(hex_str), 2)]))

def hex_to_dec_reversed(hex_str):
    return int(reverse_hex_bytes(hex_str), 16)

def get_default_controller():
    try:
        output = subprocess.check_output(["bluetoothctl", "list"], text=True)
        for line in output.splitlines():
            if "[default]" in line:
                return line.split()[1].upper()
    except Exception:
        pass
    return None

def generate_bluez_info(remote_mac, pid_key, penc_key):
    identity_key = pid_key[:32].upper()
    ltk_key = penc_key[:32].upper()
    rand_hex = penc_key[32:48]
    ediv_hex = penc_key[48:52]
    rand_dec = hex_to_dec_reversed(rand_hex)
    ediv_dec = int(reverse_hex_bytes(ediv_hex), 16)

    return f"""[General]
Appearance=0x0180
AddressType=public
SupportedTechnologies=LE;
Trusted=true
Blocked=false
CablePairing=false
WakeAllowed=true
Services=00001800-0000-1000-8000-00805f9b34fb;00001801-0000-1000-8000-00805f9b34fb;0000180a-0000-1000-8000-00805f9b34fb;0000180f-0000-1000-8000-00805f9b34fb;00001812-0000-1000-8000-00805f9b34fb;00001813-0000-1000-8000-00805f9b34fb;5de20000-5e8d-11e6-8b77-86f30ca893d3;cfbfa000-762c-4912-a043-20e3ecde0a2d;fe151500-5e8d-11e6-8b77-86f30ca893d3;

[IdentityResolvingKey]
Key={identity_key}

[LongTermKey]
Key={ltk_key}
Authenticated=0
EncSize=16
EDiv={ediv_dec}
Rand={rand_dec}

[ConnectionParameters]
MinInterval=16
MaxInterval=16
Latency=49
Timeout=500
"""

def write_autostart_bt_mac(new_adapter_mac):
    dt_id_path = Path("/proc/device-tree/amlogic-dt-id")
    if not dt_id_path.exists():
        return
    dt_id = dt_id_path.read_bytes().split(b'\x00', 1)[0].decode()
    if dt_id != "g12brevb_raven_2g":
        return

    autostart_path = Path("/storage/.config/autostart.sh")
    bt_cmd = 'hcitool -i hci0 cmd 0x3F 0x1A ' + ' '.join(reversed(new_adapter_mac.split(':')))
    bt_block = [
        "# Set Bluetooth MAC address to match FireOS",
        "for i in $(seq 1 20); do",
        "    hciconfig hci0 > /dev/null 2>&1 && break",
        "    sleep 1",
        "done",
        bt_cmd,
        "hciconfig hci0 down",
        "hciconfig hci0 up",
        "systemctl restart bluetooth.service"
    ]
    wrapped_block = ["("] + bt_block + [")&"]

    if autostart_path.exists():
        content = autostart_path.read_text()
        if bt_cmd not in content:
            with autostart_path.open("a") as f:
                f.write('\n' + '\n'.join(wrapped_block) + '\n')
    else:
        autostart_path.parent.mkdir(parents=True, exist_ok=True)
        autostart_path.write_text("#!/bin/sh\n" + '\n'.join(wrapped_block) + '\n')
        autostart_path.chmod(0o755)

def modify_wifi_cfg():
    dt_id_path = Path("/proc/device-tree/amlogic-dt-id")
    if not dt_id_path.exists():
        return
    dt_id = dt_id_path.read_bytes().split(b'\x00', 1)[0].decode()
    if dt_id != "g12brevb_raven_2g":
        return

    dst_path = Path("/storage/.config/firmware/wifi.cfg")
    src_path = Path("/usr/lib/kernel-overlays/base/lib/firmware/wifi.cfg")

    if not dst_path.exists() and src_path.exists():
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src_path, dst_path)

    if dst_path.exists():
        lines = dst_path.read_text().splitlines()
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith("EfuseBufferModeCal"):
                lines[i] = "EfuseBufferModeCal 2"
                updated = True
                break
        if updated:
            dst_path.write_text('\n'.join(lines) + '\n')

def sync_firetv_remote():
    notify("Syncing Bluetooth remote...")

    try:
        Path("/media/data").mkdir(parents=True, exist_ok=True)
        subprocess.run(["mount", "/dev/data", "/media/data"], check=True)
    except subprocess.CalledProcessError:
        notify("Failed to mount /dev/data")
        return False

    default_ctrl_mac = get_default_controller()
    if not default_ctrl_mac:
        notify("No default Bluetooth controller found.")
        return False

    bt_config_path = "/media/data/misc/bluedroid/bt_config.conf"
    if not Path(bt_config_path).exists():
        notify("bt_config.conf not found")
        return False

    bt_config = parse_bt_config(bt_config_path)
    if 'Adapter' not in bt_config or 'Address' not in bt_config['Adapter']:
        notify("Invalid bt_config.conf")
        return False

    new_adapter_mac = bt_config['Adapter']['Address'].upper()
    write_autostart_bt_mac(new_adapter_mac)
    modify_wifi_cfg()

    old_cache_path = Path(f"/storage/.cache/bluetooth/{default_ctrl_mac}")
    new_cache_path = Path(f"/storage/.cache/bluetooth/{new_adapter_mac}")
    new_cache_path.mkdir(parents=True, exist_ok=True)

    if new_adapter_mac != default_ctrl_mac and old_cache_path.exists():
        for device_dir in old_cache_path.iterdir():
            if device_dir.is_dir():
                shutil.copytree(device_dir, new_cache_path / device_dir.name, dirs_exist_ok=True)

    imported_macs = []

    for section in bt_config.sections():
        if not section.startswith("[") and bt_config[section].get("Name") == "Amazon Fire TV Remote":
            remote_mac = section.upper()
            dest_path = new_cache_path / remote_mac
            dest_path.mkdir(parents=True, exist_ok=True)

            pid_key = bt_config[section].get("LE_KEY_PID", "")
            penc_key = bt_config[section].get("LE_KEY_PENC", "")

            if len(pid_key) < 32 or len(penc_key) < 52:
                continue

            info_text = generate_bluez_info(remote_mac, pid_key, penc_key)
            with open(dest_path / "info", "w") as f:
                f.write(info_text)

            imported_macs.append(remote_mac)

    subprocess.run(["umount", "/media/data"], check=False)

    # Apply MAC override immediately for g12brevb_raven_2g
    dt_id_path = Path("/proc/device-tree/amlogic-dt-id")
    if dt_id_path.exists():
        try:
            dt_id = dt_id_path.read_bytes().split(b'\x00', 1)[0].decode()
            if dt_id == "g12brevb_raven_2g":
                bt_cmd = ['hcitool', '-i', 'hci0', 'cmd', '0x3F', '0x1A'] + list(reversed(new_adapter_mac.split(':')))
                subprocess.run(bt_cmd, check=False)
        except Exception as e:
            log(f"Immediate BT MAC override failed: {e}")

    subprocess.run(["hciconfig", "hci0", "down"], check=False)
    subprocess.run(["hciconfig", "hci0", "up"], check=False)
    subprocess.run(["systemctl", "restart", "bluetooth.service"], check=False)

    if imported_macs:
        xbmcgui.Dialog().ok(__addonname__, f"Imported remotes:\n" + '\n'.join(imported_macs))
    else:
        notify("No remotes were imported.")

    return True

def show_multitool_menu():
    options = [
        "Sync FireOS Bluetooth Fire remotes with CoreELEC",
        "Cancel"
    ]
    choice = xbmcgui.Dialog().select("CoreELEC Multi-Tool", options)

    if choice == 0:
        sync_firetv_remote()

if __name__ == '__main__':
    show_multitool_menu()
