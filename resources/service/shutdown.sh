#!/bin/sh

LED=/storage/.kodi/addons/service.firecube_lightbar

usb_boot()
{
  flash_dev=$(awk '$2=="/flash"{print $1}' /proc/mounts)

  case "$flash_dev" in
    /dev/sd*) return 0 ;;
    *) return 1 ;;
  esac
}

unmount_usb_storage()
{
  # Flush pending writes
  sync

  # Unmount filesystems backed by USB storage devices
  for mountpoint in $(awk '$1 ~ "^/dev/sd[a-z][0-9]*$" {print $2}' /proc/mounts); do
    [ -n "$mountpoint" ] || continue

    echo "<6>gazelle-usb-power: Unmounting USB storage $mountpoint" > /dev/kmsg

    if ! umount "$mountpoint"; then
      echo "<3>gazelle-usb-power: Failed to unmount USB storage $mountpoint" > /dev/kmsg
      return 1
    fi
  done

  return 0
}

# Only handle USB storage if CoreELEC is not booting from USB
if ! usb_boot; then

  # Only disable USB power if all USB storage can be unmounted
  if unmount_usb_storage; then

    # Disable USB power
    devmem 0xfe004188 32 $(( $(devmem 0xfe004188 32) & ~(1 << 16) ))
    devmem 0xfe004184 32 $(( $(devmem 0xfe004184 32) & ~(1 << 16) ))
    devmem 0xfe002040 32 $(( $(devmem 0xfe002040 32) & ~(1 << 8) ))

    echo "<6>gazelle-usb-power: USB power disabled" > /dev/kmsg
  else
    echo "<3>gazelle-usb-power: USB storage still mounted, leaving USB power on" > /dev/kmsg
  fi
else
  echo "<6>gazelle-usb-power: CoreELEC booted from USB, leaving USB storage and power on" > /dev/kmsg
fi

# Disable WOL
ethtool -s eth0 wol d

# Set LED bar red
python "$LED/led.py" -b 50 -c ff0000
sleep 0.5
python "$LED/led.py" -b 0 -c 000000
