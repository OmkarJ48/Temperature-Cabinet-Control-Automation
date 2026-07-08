#!/usr/bin/env bash
# Write a new static setpoint (register 300, "SP1") to the Watlow F4S -- edge-triggered
# (only writes if the value actually changes) to avoid unnecessary EEPROM wear, mirroring
# the write -> confirm -> latch discipline in src/POUs/FB_CabinetSetpointControl.st.
#
# THIS SCRIPT CANNOT AND MUST NOT CHANGE REGISTER 100 (the actual chamber temperature).
# Register 100 is a read-only measurement taken from the F4S's own physical sensor -- it
# is not writable, and forcing a value into it would only make the display lie about the
# real chamber state without changing the physical temperature at all, defeating the
# supervisory-control safety model this repo documents (root README, "Key design
# principle"). To change the physical temperature, write the SETPOINT here (register 300)
# and let the F4S's own closed-loop PID ramp register 100 toward it -- then use
# watch-temperature-ramp.sh to observe that ramp.
#
# Usage: ./write-setpoint.sh <new_setpoint_degC> [device] [baud] [slave]
#   new_setpoint_degC: e.g. 26.5 -- validated against 0.0-200.0 degC, the same bounds as
#                      GVL_HMI.rMinSetpoint/rMaxSetpoint in the CODESYS application
#   device: /dev/ttyUSB0 (default) -- re-verify with 'ls /dev/ttyUSB*' if replugged
#   baud:   19200 (default) -- confirmed F4S setting
#   slave:  1 (default) -- confirm on F4S Setup -> Communications if this fails
set -euo pipefail

SETPOINT_C="${1:?Usage: $0 <new_setpoint_degC> [device] [baud] [slave]}"
DEVICE="${2:-/dev/ttyUSB0}"
BAUD="${3:-19200}"
SLAVE="${4:-1}"

REGISTER=300
MIN_C=0.0
MAX_C=200.0

command -v mbpoll >/dev/null 2>&1 || {
  echo "mbpoll not installed. Run: sudo apt-get update && sudo apt-get install mbpoll" >&2
  exit 1
}

# --- Validate input is a plain number ---
if ! [[ "$SETPOINT_C" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
  echo "ERROR: '$SETPOINT_C' is not a valid number (e.g. 26.5)." >&2
  exit 1
fi

# --- Range validation (mirrors GVL_HMI.rMinSetpoint/rMaxSetpoint in the CODESYS app) ---
if ! awk -v c="$SETPOINT_C" -v min="$MIN_C" -v max="$MAX_C" 'BEGIN{exit !(c>=min && c<=max)}'; then
  echo "ERROR: ${SETPOINT_C}C is outside the validated range ${MIN_C}-${MAX_C}C." >&2
  echo "Refusing to write -- if this range is wrong, update GVL_HMI.rMinSetpoint/rMaxSetpoint" >&2
  echo "(src/GVLs/GVL_HMI.gvl) and this script's MIN_C/MAX_C together, not just one of them." >&2
  exit 1
fi

# --- F4S stores the setpoint with one implied decimal place (24.0C is stored as 240) ---
RAW_VALUE=$(awk -v c="$SETPOINT_C" 'BEGIN{printf "%.0f", c*10}')

echo "Reading current setpoint (register $REGISTER) before writing..."
CURRENT_RAW=$(mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -t 4 -r "$REGISTER" -c 1 -1 -0 "$DEVICE" \
  | grep -oP "(?<=\[$REGISTER\]:\s)-?[0-9]+" || true)

if [ -z "$CURRENT_RAW" ]; then
  echo "ERROR: could not read the current setpoint -- aborting write without touching the cabinet." >&2
  echo "Re-run the Step 4 bench-test (README Step 4) to confirm the link is still up first." >&2
  exit 1
fi

CURRENT_C=$(awk -v r="$CURRENT_RAW" 'BEGIN{printf "%.1f", r/10}')
echo "Current setpoint:   ${CURRENT_RAW} (raw) = ${CURRENT_C}C"
echo "Requested setpoint:  ${RAW_VALUE} (raw) = ${SETPOINT_C}C"

if [ "$CURRENT_RAW" -eq "$RAW_VALUE" ]; then
  echo "Setpoint is already at the requested value -- skipping write (edge-triggered, avoids EEPROM wear)."
  exit 0
fi

echo "Writing new setpoint (FC06, single register)..."
mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -t 4 -r "$REGISTER" -0 "$DEVICE" "$RAW_VALUE"

sleep 1

echo "Confirming write (read-back)..."
CONFIRM_RAW=$(mbpoll -m rtu -a "$SLAVE" -b "$BAUD" -P none -t 4 -r "$REGISTER" -c 1 -1 -0 "$DEVICE" \
  | grep -oP "(?<=\[$REGISTER\]:\s)-?[0-9]+" || true)

if [ "$CONFIRM_RAW" == "$RAW_VALUE" ]; then
  CONFIRM_C=$(awk -v r="$CONFIRM_RAW" 'BEGIN{printf "%.1f", r/10}')
  echo "CONFIRMED: register $REGISTER now reads ${CONFIRM_RAW} (${CONFIRM_C}C)."
  echo "The F4S will now ramp the ACTUAL chamber temperature (register 100) toward this target"
  echo "using its own closed-loop control -- run watch-temperature-ramp.sh to observe progress."
else
  echo "WARNING: read-back (${CONFIRM_RAW:-none}) does not match the written value (${RAW_VALUE})." >&2
  echo "Likely cause: F4S is in profile/ramp mode, not static setpoint mode -- a running profile" >&2
  echo "owns SP1 and refuses external writes. Confirm on the F4S front panel and switch to" >&2
  echo "static/manual setpoint mode before retrying." >&2
  exit 1
fi
