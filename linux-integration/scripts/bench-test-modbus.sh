#!/usr/bin/env bash
# Standalone Modbus RTU bench test for the Watlow F4S — read Reg 100 (Input 1 Value).
#
# This intentionally sets parity/data/stop bits explicitly (-P none -d 8 -s 1) rather
# than relying on mbpoll's defaults: mbpoll defaults to Even parity, which does not
# match this F4S's confirmed 8N1 configuration and will time out every request.
#
# Usage: ./bench-test-modbus.sh [device] [baud] [register] [slave]
#   device:   /dev/ttyUSB0 (default)
#   baud:     19200 (default) — confirmed F4S setting per root README; re-verify against
#             the front panel (Setup -> Communications -> Baud Rate) if this still times out
#   register: 100 (default) = Input 1 Value, read-only, FC03
#   slave:    1 (default) — confirm on F4S Setup -> Communications if this fails
set -euo pipefail

DEVICE="${1:-/dev/ttyUSB0}"
BAUD="${2:-19200}"
REGISTER="${3:-100}"
SLAVE="${4:-1}"

command -v mbpoll >/dev/null 2>&1 || {
  echo "mbpoll not installed. Run: sudo apt-get update && sudo apt-get install mbpoll" >&2
  exit 1
}

echo "Polling slave $SLAVE, register $REGISTER, ${BAUD}-8N1 on $DEVICE ..."
mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -s 1 -d 8 -t 4 -r "$REGISTER" -c 1 -1 "$DEVICE"
