#!/usr/bin/env python3
"""
Range qualification sweep: prove -40..200 degC end to end over Modbus TCP.

This is the T7 expansion referenced in the Week-2 roadmap open items. It is a
SEPARATE script on purpose — test_rtu_write.py is the proven 3-test baseline
and stays untouched so a regression in the sweep can never be confused with a
regression in the baseline.

Exercises the same path CODESYS uses (TCP registers 0/1 -> gateway -> RTU),
including the negative setpoints that the old unsigned range check rejected.

USAGE (on the Pi, gateway running):
    python3 test_range_sweep.py            # in-range + boundary cases
    python3 test_range_sweep.py --quick    # endpoints and rejects only

Writes real setpoints — the cabinet will move. Restores the starting setpoint
on exit.
"""
import argparse
import sys
import time

from pymodbus.client import ModbusTcpClient

REG_REQ_SP = 0
REG_TRIGGER = 1
REG_TEMP = 2
REG_SP_READ = 3
REG_STATUS = 4

ST_NAMES = {0: "OK", 2: "WRITE_FAILED", 3: "NOT_ACCEPTED", 4: "RANGE", 5: "COMMS"}

# (setpoint_x10, should_be_accepted, why)
FULL_CASES = [
    (-400, True,  "lower bound, -40.0 degC"),
    (-155, True,  "negative, non-round"),
    (-10,  True,  "just below zero — the case that used to fault RANGE_HIGH"),
    (0,    True,  "zero"),
    (265,  True,  "known-good baseline"),
    (1250, True,  "mid-upper, previously suspect"),
    (2000, True,  "upper bound, 200.0 degC"),
    (2001, False, "one tick above max — must reject"),
    (-401, False, "one tick below min — must reject"),
    (2500, False, "far above max — must reject"),
]

QUICK_CASES = [
    (-400, True,  "lower bound"),
    (2000, True,  "upper bound"),
    (2001, False, "above max — must reject"),
    (-401, False, "below min — must reject"),
]


def u16_to_i16(v):
    return v - 65536 if v >= 32768 else v


def i16_to_u16(v):
    return v + 65536 if v < 0 else v


def read(client, reg):
    r = client.read_holding_registers(address=reg, count=1, device_id=1)
    return None if r.isError() else r.registers[0]


def apply_setpoint(client, sp_x10, timeout=8.0):
    """Drive one write through the gateway; return (status, readback_x10)."""
    client.write_register(address=REG_REQ_SP, value=i16_to_u16(sp_x10), device_id=1)
    client.write_register(address=REG_TRIGGER, value=1, device_id=1)

    # The gateway clears the trigger once it has processed the request. Poll
    # for that rather than sleeping a fixed interval, so a slow RTU confirm
    # doesn't get misread as a rejection.
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.1)
        if read(client, REG_TRIGGER) == 0:
            break
    else:
        return None, None

    # Wait for gateway's cyclic polling (1.0s period) to update the read-back
    # register. The F4S needs time to confirm the setpoint over RTU. Without
    # this delay, we read stale values from the previous cycle.
    time.sleep(1.5)

    status = read(client, REG_STATUS)
    raw = read(client, REG_SP_READ)
    return status, (None if raw is None else u16_to_i16(raw))


def run_case(client, sp_x10, expect_ok, why):
    status, readback = apply_setpoint(client, sp_x10)
    name = ST_NAMES.get(status, f"UNKNOWN({status})")

    if status is None:
        print(f"  {sp_x10/10.0:>7.1f} degC  TIMEOUT — gateway never cleared trigger   [{why}]")
        return False

    if expect_ok:
        # Accepted means status OK *and* the F4S echoed the value back. Status
        # alone is not proof: a silent clamp reports OK with a stale read-back.
        ok = (status == 0 and readback == sp_x10)
        got = f"status={name} readback={readback/10.0 if readback is not None else '--'}"
        print(f"  {sp_x10/10.0:>7.1f} degC  {'PASS' if ok else 'FAIL'}  expect accept, {got}   [{why}]")
        return ok

    ok = (status == 4)
    print(f"  {sp_x10/10.0:>7.1f} degC  {'PASS' if ok else 'FAIL'}  expect RANGE, got {name}   [{why}]")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="endpoints and rejects only")
    ap.add_argument("--host", default="localhost")
    args = ap.parse_args()

    cases = QUICK_CASES if args.quick else FULL_CASES

    client = ModbusTcpClient(host=args.host, port=502)
    if not client.connect():
        print(f"Could not connect to gateway at {args.host}:502")
        return 1

    try:
        original = read(client, REG_SP_READ)
        if original is None:
            print("Could not read current setpoint — is the RTU link up?")
            return 1
        original = u16_to_i16(original)
        print(f"Starting setpoint: {original/10.0} degC")
        print(f"Running {len(cases)} cases over -40..200 degC\n")

        results = []
        for sp, expect_ok, why in cases:
            results.append(run_case(client, sp, expect_ok, why))
            time.sleep(0.5)

        print(f"\n  Restoring {original/10.0} degC")
        apply_setpoint(client, original)

        passed = sum(results)
        print(f"\n{'='*60}")
        print(f"  {passed}/{len(results)} passed")
        if passed == len(results):
            print("  Full -40..200 degC range qualified end to end.")
            return 0
        print("  Range NOT fully qualified.")
        print("  If in-range writes failed at the top or bottom, the F4S's own")
        print("  setpoint limits are narrower than the code allows — run")
        print("  probe_f4s_limits.py --sweep --yes to measure them.")
        return 1

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
