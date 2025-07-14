#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/storage/downloads/emmc_install.log"

MODE=""

# Parse argument: --flash-only or --full
if [[ "$1" == "--flash-only" ]]; then
  MODE="flash"
elif [[ "$1" == "--full" ]]; then
  MODE="full"
else
  echo "Usage: $0 [--flash-only | --full]" > /dev/tty0
  exit 1
fi

echo "Stopping Kodi..."
systemctl stop kodi

# Enable output to TV screen after Kodi is stopped
echo 1 > /sys/class/vtconsole/vtcon1/bind
clear > /dev/tty0

# Disable consoleblank
echo -e "\033[9;0]" > /dev/tty0
echo 0 > /sys/class/graphics/fb0/blank

# Redirect all output to TV screen and log file
exec > >(tee -a /dev/tty0 "$LOG_FILE") 2>&1

echo ""
echo ""
echo "Kodi stopped"
echo ""
echo "Mounting data partition..."
mkdir -p /media/data
mount /dev/data /media/data
mkdir -p /media/data/coreelec_flash

if [[ "$MODE" == "full" ]]; then
  mkdir -p /media/data/coreelec_storage
fi

mount -o remount,rw /flash
cp "$SCRIPT_DIR/../update/dtb.img" /flash/

echo ""
echo "Syncing /flash to /data/coreelec_flash..."
rsync -ah --info=progress2 /flash/ /media/data/coreelec_flash/

if [[ "$MODE" == "full" ]]; then
  echo ""
  echo "Syncing /storage to /data/coreelec_storage..."
  rsync -ah --info=progress2 /storage/ /media/data/coreelec_storage/
fi

cp "$SCRIPT_DIR/ce_autoscript" /media/data/coreelec_flash/

sync
umount /media/data
mount -o remount,ro /flash
echo ""
echo "CoreELEC eMMC migration complete"
echo ""
echo "Shutdown CoreELEC unplug CE USB stick to boot to eMMC"
echo ""
echo "Returning to Kodi in 5 seconds..."
sleep 5
echo 0 > /sys/class/vtconsole/vtcon1/bind
systemctl start kodi
