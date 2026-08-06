#!/usr/bin/env python3
"""
Probe the Watlow F4S's OWN setpoint limits — the third and final range gate.

WHY THIS EXISTS
---------------
Three independent layers clamp a setpoint on its way to the cabinet:

  1. PLC_PRG        rMinSetpoint / rMaxSetpoint   (-40 .. 200)   -- code
  2. f4s_gateway.py SP_MIN_X10 / SP_MAX_X10       (-400 .. 2000) -- code
  3. the F4S itself setpoint low/high limit params               -- DEVICE CONFIG

Layers 1 and 2 are fixed in this repo. Layer 3 cannot be fixed from code and
cannot be read from CODESYS: it lives in the controller's own setup menu and
is why a 125 degC request read back "accepted" over Modbus while the front
panel still showed a different value, and why ~100 degC behaved as a ceiling.

This script reads the F4S directly over RTU and reports what the device will
actually honour. Run it on the Pi with the gateway STOPPED (both want the
serial port):

    sudo systemctl stop f4s-gateway
    python3 probe_f4s_limits.py
    sudo systemctl start f4s-gateway

MODES
-----
  (default)   read-only register dump — completely safe, changes nothing
  --sweep     ALSO probes the accepted range by writing setpoints and reading
              them back. Writes touch the F4S setpoint, so the cabinet WILL
              move. Bounded to ~24 writes by binary search. Requires --yes.

The sweep is the authoritative answer: it reports the range the device
actually accepts, whatever its menu says.
"""
import argparse
import sys
import time

from pymodbus.client import ModbusSerialClient

SERIAL_PORT = "/dev/ttyWatlowF4S"
BAUD = 19200
SLAVE_ADDR = 1

F4S_REG_TEMP = 100
F4S_REG_SP = 300

# Registers worth dumping. The Watlow F4/F4S map is not fully public and
# varies by firmware, so this is a survey, not a claim: read them, then
# cross-check anything that looks like a limit against the front-panel menu
# (SETUP -> INPUT 1 / SETUP -> CONTROL) before trusting it.
SURVEY = [
    (100, "Input 1 process value (temperature)"),
    (300, "Set point 1 (target)"),
    (301, "Set point 1 (working/active)"),
    (302, "candidate: SP low limit"),
    (303, "candidate: SP high limit"),
    (304, "candidate"),
    (305, "candidate"),
    (306, "candidate"),
    (307, "candidate"),
    (308, "candidate"),
    (309, "candidate"),
    (310, "candidate"),
    (600, "candidate: input 1 range low"),
    (601, "candidate: input 1 range high"),
    (602, "candidate"),
    (603, "candidate"),
]

# Sweep bounds: never probe outside what the rest of the chain permits.
SWEEP_MIN_X10 = -400   # -40.0 degC
SWEEP_MAX_X10 = 2000   # 200.0 degC
SETTLE_S = 0.6         # give the F4S time to latch before reading back


def u16_to_i16(value):
    return value - 65536 if value >= 32768 else value


def i16_to_u16(value):
    return value + 65536 if value < 0 else value


def read_reg(client, addr):
    try:
        r = client.read_holding_registers(address=addr, count=1, device_id=SLAVE_ADDR)
        if r.isError() or not r.registers:
            return None
        return r.registers[0]
    except Exception:
        return None


def write_reg(client, addr, raw):
    try:
        r = client.write_register(address=addr, value=raw, device_id=SLAVE_ADDR)
        return not r.isError()
    except Exception:
        return False


def accepts(client, sp_x10):
    """True if the F4S latches sp_x10 as its setpoint.

    Read-back equality is the only trustworthy test: the F4S acknowledges the
    FC06 frame even when it silently clamps or ignores the value, so a
    successful write says nothing on its own.
    """
    raw = i16_to_u16(sp_x10)
    if not write_reg(client, F4S_REG_SP, raw):
        return False
    time.sleep(SETTLE_S)
    back = read_reg(client, F4S_REG_SP)
    return back is not None and u16_to_i16(back) == sp_x10


def find_edge(client, good, bad, label):
    """Binary-search the boundary between an accepted and a rejected setpoint.

    Returns the last value that was accepted. ~11 writes for the full
    -40..200 span at 0.1 degC resolution.
    """
    steps = 0
    while abs(bad - good) > 1:
        mid = (good + bad) // 2
        ok = accepts(client, mid)
        steps += 1
        print(f"    probe {mid/10.0:>7.1f} degC -> {'accepted' if ok else 'REJECTED'}")
        if ok:
            good = mid
        else:
            bad = mid
    print(f"  {label}: {good/10.0} degC  (searched in {steps} writes)")
    return good


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true",
                    help="probe the real accepted range by writing setpoints")
    ap.add_argument("--yes", action="store_true",
                    help="confirm that --sweep may move the cabinet setpoint")
    args = ap.parse_args()

    if args.sweep and not args.yes:
        print("--sweep writes real setpoints to the F4S and will move the cabinet.")
        print("Re-run with --sweep --yes once the cabinet is safe to disturb.")
        return 2

    client = ModbusSerialClient(port=SERIAL_PORT, baudrate=BAUD, timeout=1,
                               bytesize=8, stopbits=1, parity="N")
    if not client.connect():
        print(f"Could not open {SERIAL_PORT}.")
        print("Is f4s-gateway still running?  sudo systemctl stop f4s-gateway")
        return 1

    try:
        print(f"=== F4S register survey ({SERIAL_PORT} @ {BAUD}, device {SLAVE_ADDR}) ===\n")
        original = read_reg(client, F4S_REG_SP)
        if original is None:
            print("Could not read setpoint register 300 — check wiring/parity.")
            return 1

        for addr, note in SURVEY:
            raw = read_reg(client, addr)
            if raw is None:
                print(f"  reg {addr:>4}  --      (no response)          {note}")
            else:
                print(f"  reg {addr:>4}  {raw:>6}  = {u16_to_i16(raw)/10.0:>8.1f}   {note}")

        print(f"\nCurrent setpoint: {u16_to_i16(original)/10.0} degC")

        if not args.sweep:
            print("\nRead-only survey done. Nothing was written.")
            print("Run with --sweep --yes to measure the range the F4S truly accepts.")
            return 0

        print("\n=== Accepted-range sweep ===")
        print("Confirming the endpoints the rest of the chain now allows.\n")

        hi_ok = accepts(client, SWEEP_MAX_X10)
        print(f"  {SWEEP_MAX_X10/10.0} degC -> {'accepted' if hi_ok else 'REJECTED'}")
        if hi_ok:
            print(f"  upper limit: >= {SWEEP_MAX_X10/10.0} degC (no F4S ceiling in range)")
            upper = SWEEP_MAX_X10
        else:
            print("  searching for the real ceiling...")
            upper = find_edge(client, u16_to_i16(original), SWEEP_MAX_X10, "upper limit")

        lo_ok = accepts(client, SWEEP_MIN_X10)
        print(f"\n  {SWEEP_MIN_X10/10.0} degC -> {'accepted' if lo_ok else 'REJECTED'}")
        if lo_ok:
            print(f"  lower limit: <= {SWEEP_MIN_X10/10.0} degC (no F4S floor in range)")
            lower = SWEEP_MIN_X10
        else:
            print("  searching for the real floor...")
            lower = find_edge(client, u16_to_i16(original), SWEEP_MIN_X10, "lower limit")

        print(f"\n  Restoring original setpoint {u16_to_i16(original)/10.0} degC")
        write_reg(client, F4S_REG_SP, original)

        print("\n=== RESULT ===")
        print(f"  F4S accepts: {lower/10.0} .. {upper/10.0} degC")
        if lower > SWEEP_MIN_X10 or upper < SWEEP_MAX_X10:
            print("\n  This is NARROWER than the -40..200 the code allows.")
            print("  No code change can widen it — raise the setpoint low/high")
            print("  limits in the F4S front-panel setup menu, then re-run.")
        else:
            print("\n  Full -40..200 range confirmed end to end.")
        return 0

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
