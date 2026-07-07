#!/usr/bin/env bash
# Standalone Modbus RTU bench test for the Watlow F4S — read Reg 100 (Input 1 Value).
#
# Two independent fixes are required for this to succeed, confirmed on hardware:
#   1. -P none  — mbpoll defaults to Even parity, which does not match this F4S's
#                 confirmed 8N1 configuration and will time out every request.
#   2. -0       — 0-based (PDU) register addressing, confirmed on this hardware;
#                 without it, mbpoll queries the wrong register (one off).
# A third, physical fix (TX/RX wiring at the F4S terminal block was swapped and had
# to be corrected) is not something this script can detect or fix — if this still
# times out with both flags present, re-check the wiring against the nameplate
# (see root README ADR-001) before assuming it's a software/flag problem.
#
# Usage: ./bench-test-modbus.sh [device] [baud] [register] [slave]
#   device:   /dev/ttyUSB0 (default) — re-verify with 'ls /dev/ttyUSB*' if replugged
#   baud:     19200 (default) — confirmed F4S setting; re-verify against the front
#             panel (Setup -> Communications -> Baud Rate) if this still times out
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

echo "Polling slave $SLAVE, register $REGISTER (0-based/PDU), ${BAUD}-8N1 on $DEVICE ..."
mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -t 4 -r "$REGISTER" -c 1 -1 -0 "$DEVICE"
