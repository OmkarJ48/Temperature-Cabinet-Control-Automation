#!/usr/bin/env bash
# Check current serial port permissions without changing anything.
# Usage: ./check-serial-permissions.sh [/dev/ttyUSB0]
#
# Reading the output:
#   crw-------  owner (root) only, no group/other access at all
#   crw-rw----  owner (root) + group (dialout) can read/write -- the normal default
#   crw-rw-rw-  everyone can read/write -- what 'chmod 666' produces
#
# If you see crw------- or crw-rw---- and your user isn't in the 'dialout' group,
# mbpoll and CODESYS will both fail with a permissions error, not a Modbus error.
# Fix with grant-serial-permissions.sh (temporary) or by joining the dialout group
# (permanent): sudo usermod -a -G dialout $USER
set -euo pipefail

DEVICE="${1:-/dev/ttyUSB0}"

if [ ! -e "$DEVICE" ]; then
  echo "ERROR: $DEVICE not found." >&2
  echo "Run 'dmesg | tail -n 20' or 'ls /dev/ttyUSB*' to find the current device node" >&2
  echo "-- it can be reassigned (e.g. to /dev/ttyUSB1) after an unplug/replug." >&2
  exit 1
fi

echo "Current permissions on $DEVICE:"
ls -la "$DEVICE"

echo
echo "Is your user in the 'dialout' group?"
groups | tr ' ' '\n' | grep -qx dialout && echo "  yes" || echo "  no -- run: sudo usermod -a -G dialout \$USER (then log out/in)"
