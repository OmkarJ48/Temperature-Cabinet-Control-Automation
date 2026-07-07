#!/usr/bin/env bash
# Grant read/write access to the USB-to-RS232 adapter for bench testing and CODESYS.
# Usage: ./grant-serial-permissions.sh [/dev/ttyUSB0]
set -euo pipefail

DEVICE="${1:-/dev/ttyUSB0}"

if [ ! -e "$DEVICE" ]; then
  echo "ERROR: $DEVICE not found. Run 'dmesg | tail -n 20' after plugging in the adapter" >&2
  echo "to confirm which /dev/ttyUSB* node it was assigned." >&2
  exit 1
fi

sudo chmod 666 "$DEVICE"
ls -l "$DEVICE"

echo
echo "Permissions granted for this session/boot only."
echo "For a permanent fix, add your user to the 'dialout' group instead:"
echo "  sudo usermod -aG dialout \$USER   (then re-open the SSH session)"
