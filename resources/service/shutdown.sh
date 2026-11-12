#!/bin/sh

LED=/storage/.kodi/addons/service.firecube_lightbar

set_gpio()
{
  offset="$1"
  value="$2"
  name="$3"

  for chip in /sys/class/gpio/gpiochip*; do
    [ "$(cat "$chip/label" 2>/dev/null)" = periphs-banks ] && [ "$(cat "$chip/ngpio" 2>/dev/null)" = 157 ] || continue

    gpio=$(($(cat "$chip/base") + offset))

    echo "$gpio" > /sys/class/gpio/export &&
      echo "$value" > /sys/class/gpio/gpio${gpio}/direction
    echo "$gpio" > /sys/class/gpio/unexport

    echo "<6>gazelle-power: Set $name $value (gpio=$gpio)" > /dev/kmsg
    break
  done
}

ethtool -s eth0 wol d
python "$LED/led.py" -b 50 -c ff0000
sleep 0.5
python "$LED/led.py" -b 0 -c 000000
