#!/usr/bin/env bash
# Watch the F4S's ACTUAL chamber temperature (register 100) ramp toward its setpoint
# (register 300) after write-setpoint.sh commits a new target. Read-only -- this script
# never writes to the cabinet.
#
# Usage: ./watch-temperature-ramp.sh [interval_seconds] [iterations] [device] [baud] [slave]
#   interval_seconds: 5 (default) -- seconds between polls
#   iterations:       12 (default) -- number of polls before exiting (12 x 5s = 1 minute)
#   device: /dev/ttyUSB0 (default)
#   baud:   19200 (default)
#   slave:  1 (default)
set -euo pipefail

INTERVAL="${1:-5}"
ITERATIONS="${2:-12}"
DEVICE="${3:-/dev/ttyUSB0}"
BAUD="${4:-19200}"
SLAVE="${5:-1}"

command -v mbpoll >/dev/null 2>&1 || {
  echo "mbpoll not installed. Run: sudo apt-get update && sudo apt-get install mbpoll" >&2
  exit 1
}

echo "Watching register 100 (actual) vs register 300 (setpoint) on $DEVICE."
echo "Polling every ${INTERVAL}s for $ITERATIONS iterations (Ctrl+C to stop early)."
echo

for ((i = 1; i <= ITERATIONS; i++)); do
  PV_RAW=$(mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -t 4 -r 100 -c 1 -1 -0 "$DEVICE" \
    | grep -oP '(?<=\[100\]:\s)-?[0-9]+' || echo "")
  SP_RAW=$(mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -t 4 -r 300 -c 1 -1 -0 "$DEVICE" \
    | grep -oP '(?<=\[300\]:\s)-?[0-9]+' || echo "")

  if [ -z "$PV_RAW" ] || [ -z "$SP_RAW" ]; then
    echo "[$i/$ITERATIONS] Read failed -- check the link (see README Step 4 troubleshooting table)."
  else
    PV_C=$(awk -v r="$PV_RAW" 'BEGIN{printf "%.1f", r/10}')
    SP_C=$(awk -v r="$SP_RAW" 'BEGIN{printf "%.1f", r/10}')
    echo "[$i/$ITERATIONS] Actual: ${PV_C}C  ->  Target: ${SP_C}C"
  fi

  [ "$i" -lt "$ITERATIONS" ] && sleep "$INTERVAL"
done
