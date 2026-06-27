#!/bin/bash
# /storage/.config/system.d/suspend.sh
#
# KODI_MODE controls how Kodi is handled across suspend:
#   restart — stop Kodi before sleep, restart on wake (clean state, slower resume)
#   pause   — SIGSTOP Kodi before sleep, SIGCONT on wake (faster resume)
################################################################################

KODI_MODE=pause
[[ "$1" == "pause" || "$1" == "restart" ]] && KODI_MODE="$1"

LED=/storage/.kodi/addons/service.firecube_lightbar
CPU0=/sys/devices/system/cpu/cpu0/cpufreq
CPU2=/sys/devices/system/cpu/cpu2/cpufreq
SAVED="/tmp/.usb_unbind_list"
GPIO_OFF_FILE="/tmp/.usb_gpio_off"
KERNEL5=false
uname -r | grep -q '^5\.' && KERNEL5=true
DT_ID=$(tr -d '\0' < /proc/device-tree/amlogic-dt-id 2>/dev/null)

# Log to kernel ring buffer
klog() {
    echo "<6>[suspend.sh][$1] $2" > /dev/kmsg
}

#### USB helpers ###############################################################

find_boot_usb_id() {
    local src disk path

    src=$(awk '$2 == "/flash" {print $1; exit}' /proc/mounts)
    [[ -z "$src" ]] && src=$(awk '$2 == "/" {print $1; exit}' /proc/mounts)
    [[ -z "$src" ]] && return 1

    # eMMC boot or USB boot path
    [[ "$src" == "/dev/data" ]] && { echo ""; return 0; }
    [[ "$src" == /dev/sd* ]]    || return 1

    disk="${src#/dev/}"       # /dev/sda1 → sda1
    disk="${disk%%[0-9]*}"    # sda1 → sda, sda → sda (no-op)

    path=$(readlink -f "/sys/class/block/$disk" 2>/dev/null) || return 1

    while [[ "$path" != "/" && "$path" != "/sys" ]]; do
        [[ -f "$path/idVendor" ]] && { basename "$path"; return 0; }
        path=$(dirname "$path")
    done
    return 1
}

unbind_usb_devices() {
    local boot_id="$1"

    [[ -n "$boot_id" ]] \
        && klog usb-sleep "pre-sleep: USB boot, protecting '$boot_id' and ancestor hubs" \
        || klog usb-sleep "pre-sleep: eMMC boot, unbinding all USB including hubs"
        
    # unmount any USB drives, unless it's being used to boot CE
    if [[ -z "$boot_id" ]]; then
        for mnt in $(awk '$1 ~ "^/dev/sd" {print $2}' /proc/mounts); do
            umount -l "$mnt" 2>/dev/null && klog usb-sleep "unmounted $mnt"
        done
    fi
    sync    

    : > "$SAVED"

    for dev in /sys/bus/usb/devices/*/; do
        local id cls
        id=$(basename "$dev")

        [[ "$id" == *:* ]]  && continue   # skip interface nodes
        [[ "$id" =~ ^usb ]] && continue   # skip root hub pseudo-devs

        if [[ -n "$boot_id" ]]; then
            cls=$(cat "$dev/bDeviceClass" 2>/dev/null)
            [[ "$cls" == "09" ]]        && continue   # skip hubs
            [[ "$id" == "$boot_id" ]]   && continue   # boot drive itself
            [[ "$id" == "$boot_id."* ]] && continue   # downstream of boot drive
            [[ "$boot_id" == "$id."* ]] && continue   # ancestor hub in boot path
        fi

        # Unbind all driver-bound interfaces of this device
        for iface in "$dev"*/; do
            local iface_id driver
            iface_id=$(basename "$iface")
            [[ "$iface_id" == *:* ]] || continue
            [[ -L "$iface/driver" ]]  || continue
            driver=$(basename "$(readlink "$iface/driver")")
            if echo "$iface_id" > "/sys/bus/usb/drivers/$driver/unbind" 2>/dev/null; then
                echo "$iface_id $driver" >> "$SAVED"
                klog usb-sleep "unbound $iface_id from $driver"
            fi
        done
    done
}

rebind_usb_devices() {
    [[ -f "$SAVED" ]] || return

    while IFS=' ' read -r iface_id driver; do
        [[ -z "$iface_id" || -z "$driver" ]] && continue
        if echo "$iface_id" > "/sys/bus/usb/drivers/$driver/bind" 2>/dev/null; then
            klog usb-sleep "rebound $iface_id to $driver"
        else
            klog usb-sleep "WARN: could not rebind $iface_id to $driver"
        fi
    done < "$SAVED"

    rm -f "$SAVED"
    klog usb-sleep "post-sleep rebind complete"
}

# GPIOH_4 controls USB port power (ffe09080.usb3phy)
#   PREG_PAD_GPIO3_O    = 0xff634400 + (0x01a * 4) = 0xff634468
#   PREG_PAD_GPIO3_EN_N = 0xff634400 + (0x019 * 4) = 0xff634464
#   PERIPHS_PIN_MUX_B   = 0xff634400 + (0x0bb * 4) = 0xff6346ec
usb_gpio_off() {
    devmem 0xff634468 32 $(( $(devmem 0xff634468 32) & ~(1 << 4) ))    # output LOW first
    devmem 0xff634464 32 $(( $(devmem 0xff634464 32) & ~(1 << 4) ))    # set as output
    devmem 0xff6346ec 32 $(( $(devmem 0xff6346ec 32) & ~(0xf << 16) )) # switch to GPIO mode
    klog suspend "USB port powered off via GPIOH_4"
}

usb_gpio_on() {
    devmem 0xff634468 32 $(( $(devmem 0xff634468 32) | (1 << 4) ))     # output HIGH
    klog suspend "USB port powered on via GPIOH_4"
}

wifi_recover() {
    local dev="sdio:0001:1"
    local driver="wlan"

    if [[ ! -e "/sys/bus/sdio/drivers/$driver/$dev" ]]; then
        klog suspend "WiFi recovery: $dev is not bound to $driver"
        return 1
    fi

    klog suspend "WiFi recovery: unbinding $dev from $driver"
    echo "$dev" > "/sys/bus/sdio/drivers/$driver/unbind" 2>/dev/null
    sleep 0.5

    klog suspend "WiFi recovery: binding $dev to $driver"
    echo "$dev" > "/sys/bus/sdio/drivers/$driver/bind" 2>/dev/null

    klog suspend "WiFi recovery: complete"
}
### Pre-suspend ################################################################

# Turn off TV
printf '\x20\x36' > /dev/aocec &

# LED suspend animation
systemd-run --no-block python "$LED/led.py" -n1 -b100 -f "$LED/resources/animations/active-end.animation"

systemctl mask suspend.target

# Disable wakeup sources
# echo disabled > /sys/devices/platform/bt-dev/power/wakeup
# echo disabled > /sys/devices/platform/ff80023c.aocec/power/wakeup
echo disabled > /sys/devices/platform/rtc/power/wakeup
# echo disabled > /sys/devices/platform/ff8000a8.rtc/power/wakeup
# echo disabled > /sys/devices/platform/rtc/input/input1/power/wakeup

# Detect boot device (USB or eMMC)
if ! BOOT_ID=$(find_boot_usb_id); then
    klog usb-sleep "ERROR: could not detect boot device -- skipping USB unbind"
else
    unbind_usb_devices "$BOOT_ID"

    # Power of USB port if not booting CE from USB drive
    if [[ -z "$BOOT_ID" && "$DT_ID" == "g12brevb_raven_2g" ]]; then
        usb_gpio_off
        touch "$GPIO_OFF_FILE"
    fi
fi

# Stop or pause Kodi
if [[ "$KODI_MODE" == restart ]]; then
    systemctl stop kodi
    echo 1 > /sys/class/graphics/fb0/blank
    echo 1 > /sys/class/graphics/fb0/force_free_mem
else
    sleep 3
    pkill -STOP kodi.bin
fi

# Bluetooth off
$KERNEL5 && bluetoothctl power off

# Save and throttle CPU state
min=$(cat $CPU0/scaling_min_freq)
max=$(cat $CPU0/scaling_max_freq)
gov0=$(cat $CPU0/scaling_governor)
gov1=$(cat $CPU2/scaling_governor)
echo 100000 > $CPU0/scaling_max_freq
echo 100000 > $CPU0/scaling_min_freq

# Take secondary CPUs offline
if $KERNEL5; then
    for cpu in cpu1 cpu2 cpu3 cpu4 cpu5; do
        echo 0 > /sys/devices/system/cpu/$cpu/online
    done
fi

### Suspend-to-idle (blocks here until wakeup) #################################

echo freeze > /sys/power/state

### Wakeup (everything below runs on wakeup) ###################################

# Bring secondary CPUs back online
if $KERNEL5; then
    for cpu in cpu1 cpu2 cpu3 cpu4 cpu5; do
        echo 1 > /sys/bus/cpu/devices/$cpu/online
    done
fi

# Restore CPU frequencies and toggle governor to restore full performance
echo $max > $CPU0/scaling_max_freq
echo $min > $CPU0/scaling_min_freq
{ echo ondemand > $CPU0/scaling_governor; sleep 0.75; echo performance > $CPU0/scaling_governor; sleep 0.75; echo $gov0 > $CPU0/scaling_governor; } &
{ echo ondemand > $CPU2/scaling_governor; sleep 0.75; echo performance > $CPU2/scaling_governor; sleep 0.75; echo $gov1 > $CPU2/scaling_governor; } &

# LED wakeup animation
systemd-run --no-block python "$LED/led.py" -n1 -b100 -f "$LED/resources/animations/active-thinking.animation"

# Turn on TV
printf '\x20\x04' > /dev/aocec &

# Bluetooth on
$KERNEL5 && bluetoothctl power on &

if [[ "$KODI_MODE" == pause ]]; then
    # Reload amremote
    remotecfg /storage/.config/remote.conf &

    # Re-initialise CEC stack
    { cec-client & sleep 5; kill -9 $!; } &
fi

# Restore USB port power if turned off, then rebind devices
if [[ -f "$GPIO_OFF_FILE" ]]; then
    usb_gpio_on
    rm -f "$GPIO_OFF_FILE"
    rm -f "$SAVED"   # udev handles driver binding after re-enumeration
    klog usb-sleep "USB port powered on -- devices will enumerate automatically"
else
    rebind_usb_devices &
fi

# WiFi health check, unbind/rebind WiFi SDIO if it doesn't respond
(
    sleep 1.5
    if dmesg | tail -n 400 | grep -q "halPrintMailbox:(INIT ERROR)"; then
        klog suspend "mt7668 WiFi error detected -- attempting recovery"
        wifi_recover
    else
        klog suspend "mt7668 WiFi healthy"
    fi
) &

# Resume or restart Kodi
if [[ "$KODI_MODE" == restart ]]; then
    echo 0 > /sys/class/graphics/fb0/blank
    systemctl restart kodi
else
    sleep 0.1
    pkill -CONT kodi.bin
    sleep 0.1
    # If Kodi is unresponsive after unpause, restart it
    [ $(stat -c %Y /storage/.kodi/temp/kodi.log) -eq $(kodi-send --action=/"Ping/" >/dev/null 2>&1; sleep 2; stat -c %Y /storage/.kodi/temp/kodi.log) ] && systemctl restart kodi
fi

systemctl unmask suspend.target
