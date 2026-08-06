#!/usr/bin/env bash
# Check and grant read/write access to the USB-to-RS232 adapter for bench testing and CODESYS.
# Usage: ./grant-serial-permissions.sh [/dev/ttyUSB0]
set -euo pipefail

DEVICE="${1:-/dev/ttyUSB0}"

if [ ! -e "$DEVICE" ]; then
  echo "ERROR: $DEVICE not found." >&2
  echo "Run 'dmesg | tail -n 20' after plugging in the adapter, or 'ls /dev/ttyUSB*'" >&2
  echo "to confirm which node it was actually assigned (it can change on replug)." >&2
  exit 1
fi

echo "Current permissions:"
ls -la "$DEVICE"
echo

sudo chmod 666 "$DEVICE"
echo "Permissions granted (temporary — resets on reboot or replug):"
ls -la "$DEVICE"

echo
echo "For a permanent fix that survives reboots/replugs, add your user to the 'dialout' group instead:"
echo "  sudo usermod -a -G dialout \$USER   (then log out and back in, or reboot)"
