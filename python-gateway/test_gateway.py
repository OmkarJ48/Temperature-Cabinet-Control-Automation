#!/usr/bin/env python3
"""
Test script for F4S Modbus TCP<->RTU Gateway
Exercises: read, write-confirm, range-reject, comms status
"""

import time
import sys
from pymodbus.client import ModbusTcpClient

# Register indices (match f4s_gateway.py)
REG_REQ_SP = 0
REG_TRIGGER = 1
REG_TEMP = 2
REG_SP_READ = 3
REG_STATUS = 4

# Status codes
ST_OK = 0
ST_WRITE_FAILED = 2
ST_NOT_ACCEPTED = 3
ST_RANGE = 4
ST_COMMS = 5

STATUS_NAMES = {
    0: "OK",
    2: "WRITE_FAILED",
    3: "NOT_ACCEPTED",
    4: "RANGE",
    5: "COMMS"
}

def connect_gateway(host="localhost", port=502):
    """Connect to the gateway TCP server."""
    print(f"Connecting to gateway at {host}:{port}...")
    client = ModbusTcpClient(host=host, port=port)
    if not client.connect():
        print("❌ Failed to connect to gateway!")
        print("   Is the gateway running? (python3 f4s_gateway.py)")
        sys.exit(1)
    print("✅ Connected to gateway!\n")
    return client

def read_registers(client, start_addr, count):
    """Read holding registers."""
    result = client.read_holding_registers(address=start_addr, count=count, device_id=1)
    if result.isError():
        print(f"❌ Read error at address {start_addr}: {result}")
        return None
    return result.registers

def write_register(client, address, value):
    """Write a single holding register."""
    result = client.write_register(address=address, value=value, device_id=1)
    if result.isError():
        print(f"❌ Write error at address {address}: {result}")
        return False
    return True

def run_test_suite(host="localhost", port=502):
    """Run full T1-T4 test suite."""
    client = connect_gateway(host, port)

    try:
        # ===== T1: Read Gateway State (No Write) =====
        print("=" * 60)
        print("T1: Gateway State Read (No Write)")
        print("=" * 60)

        regs = read_registers(client, REG_REQ_SP, 5)
        if regs is None:
            return False

        print(f"Reg[0] REG_REQ_SP:   {regs[0]} (requested setpoint)")
        print(f"Reg[1] REG_TRIGGER:  {regs[1]} (apply trigger)")
        print(f"Reg[2] REG_TEMP:     {regs[2]} = {regs[2]/10.0:.1f}°C")
        print(f"Reg[3] REG_SP_READ:  {regs[3]} = {regs[3]/10.0:.1f}°C")
        print(f"Reg[4] REG_STATUS:   {regs[4]} ({STATUS_NAMES.get(regs[4], 'UNKNOWN')})")

        if regs[2] == 0 or regs[3] == 0:
            print("⚠️  WARNING: Temperature or setpoint reads are 0 (check F4S RTU connection)")
        else:
            print("✅ T1 PASS: Gateway reads are live\n")

        # ===== T2: Write Within Range =====
        print("=" * 60)
        print("T2: Write Setpoint Within Range (28.0°C)")
        print("=" * 60)

        new_sp_raw = 280  # 28.0°C
        print(f"Writing REG_REQ_SP(0): {new_sp_raw} = {new_sp_raw/10.0:.1f}°C")
        write_register(client, REG_REQ_SP, new_sp_raw)

        print(f"Writing REG_TRIGGER(1): 1")
        write_register(client, REG_TRIGGER, 1)

        print("Waiting for gateway to process write (2 seconds)...")
        time.sleep(2)

        # Check status
        regs = read_registers(client, REG_TRIGGER, 3)
        if regs is None:
            return False

        trigger_cleared = (regs[0] == 0)
        status = regs[2]

        print(f"After write:")
        print(f"  Reg[1] REG_TRIGGER:  {regs[0]} (cleared: {trigger_cleared})")
        print(f"  Reg[4] REG_STATUS:   {status} ({STATUS_NAMES.get(status, 'UNKNOWN')})")

        if trigger_cleared and status == ST_OK:
            print("✅ T2 PASS: Write confirmed successfully\n")
        elif status == ST_NOT_ACCEPTED:
            print("⚠️  Status = NOT_ACCEPTED: F4S may be in menu/profile mode (not on run page)")
            print("   This is expected if F4S is not in static setpoint mode.\n")
        else:
            print(f"❌ T2 FAIL: Unexpected status {status}\n")

        # ===== T3: Write Out-of-Range =====
        print("=" * 60)
        print("T3: Write Out-of-Range (250.0°C, exceeds 200°C max)")
        print("=" * 60)

        oob_sp_raw = 2500  # 250.0°C (out of range)
        print(f"Writing REG_REQ_SP(0): {oob_sp_raw} = {oob_sp_raw/10.0:.1f}°C")
        write_register(client, REG_REQ_SP, oob_sp_raw)

        print(f"Writing REG_TRIGGER(1): 1")
        write_register(client, REG_TRIGGER, 1)

        print("Waiting for gateway to validate (1 second)...")
        time.sleep(1)

        # Check status
        regs = read_registers(client, REG_STATUS, 1)
        if regs is None:
            return False

        status = regs[0]
        print(f"Reg[4] REG_STATUS: {status} ({STATUS_NAMES.get(status, 'UNKNOWN')})")

        if status == ST_RANGE:
            print("✅ T3 PASS: Out-of-range write rejected correctly\n")
        else:
            print(f"❌ T3 FAIL: Expected RANGE status (4), got {status}\n")

        # ===== T4: Write Lower Bound (Test -40°C Min) =====
        print("=" * 60)
        print("T4: Write at Lower Bound (-40.0°C minimum)")
        print("=" * 60)

        min_sp_raw = -400  # -40.0°C (note: raw values can be negative for temps < 0)
        # Some Modbus implementations may require unsigned, so test both
        print(f"Writing REG_REQ_SP(0): {min_sp_raw}")
        if write_register(client, REG_REQ_SP, min_sp_raw):
            print(f"Writing REG_TRIGGER(1): 1")
            write_register(client, REG_TRIGGER, 1)

            print("Waiting for gateway to process (2 seconds)...")
            time.sleep(2)

            regs = read_registers(client, REG_STATUS, 1)
            if regs:
                status = regs[0]
                print(f"Reg[4] REG_STATUS: {status} ({STATUS_NAMES.get(status, 'UNKNOWN')})")
                if status != ST_RANGE:
                    print("✅ T4 PASS: Lower bound accepted or processed\n")
                else:
                    print("⚠️  Lower bound (-40°C) treated as out-of-range (may indicate unsigned register handling)\n")

        # ===== Summary =====
        print("=" * 60)
        print("Test Suite Complete")
        print("=" * 60)
        print("\nNext Steps:")
        print("  1. If T2-T3 pass, the gateway is working correctly")
        print("  2. Monitor logs: tail -f ~/.f4s_gateway/f4s_gateway.log")
        print("  3. Check F4S front panel to confirm setpoint changes")
        print("  4. Proceed to CODESYS integration in sandbox project")

        return True

    finally:
        client.close()
        print("\nDisconnected from gateway.\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test F4S Gateway")
    parser.add_argument("--host", default="localhost", help="Gateway host (default: localhost)")
    parser.add_argument("--port", type=int, default=502, help="Gateway port (default: 502)")
    args = parser.parse_args()

    success = run_test_suite(args.host, args.port)
    sys.exit(0 if success else 1)
