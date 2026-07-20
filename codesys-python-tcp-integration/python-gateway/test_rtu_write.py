#!/usr/bin/env python3
"""
Test script: Write setpoint to F4S via RTU gateway
Simulates CODESYS writing a new setpoint and reading back confirmation

USAGE (from the repository root, with gateway running in another terminal):
  cd codesys-python-tcp-integration/python-gateway
  python3 f4s_gateway.py   # Terminal 1
  python3 test_rtu_write.py  # Terminal 2 (after gateway has started)
"""
import sys
import time
import importlib.util

# Load f4s_gateway.py module directly
spec = importlib.util.spec_from_file_location("f4s_gateway", "f4s_gateway.py")
gateway_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway_module)

tcp_regs = gateway_module.tcp_regs
REG_REQ_SP = gateway_module.REG_REQ_SP
REG_TRIGGER = gateway_module.REG_TRIGGER
REG_TEMP = gateway_module.REG_TEMP
REG_SP_READ = gateway_module.REG_SP_READ
REG_STATUS = gateway_module.REG_STATUS

def test_write_setpoint(new_sp_x10):
    """
    Trigger a setpoint write and monitor for confirmation
    new_sp_x10: setpoint value x10 (e.g., 280 = 28.0°C)
    """
    print(f"\n{'='*60}")
    print(f"TEST: Write setpoint {new_sp_x10/10.0}°C")
    print(f"{'='*60}")

    # Read current state before write
    print(f"\nBefore write:")
    print(f"  Current temp:      {tcp_regs[REG_TEMP]/10.0}°C")
    print(f"  Current setpoint:  {tcp_regs[REG_SP_READ]/10.0}°C")
    print(f"  Status:            {tcp_regs[REG_STATUS]}")

    # Set up write request
    print(f"\nSetting write trigger:")
    tcp_regs[REG_REQ_SP] = new_sp_x10
    tcp_regs[REG_TRIGGER] = 1
    print(f"  REG_REQ_SP ({REG_REQ_SP}):  {tcp_regs[REG_REQ_SP]} = {tcp_regs[REG_REQ_SP]/10.0}°C")
    print(f"  REG_TRIGGER ({REG_TRIGGER}):   {tcp_regs[REG_TRIGGER]} (request sent)")

    # Wait for gateway to process write
    print(f"\nWaiting for gateway to process write...")
    for i in range(20):  # Wait up to 2 seconds
        time.sleep(0.1)
        if tcp_regs[REG_TRIGGER] == 0:  # Gateway clears trigger when done
            break

    # Read result
    print(f"\nAfter write:")
    print(f"  REG_TRIGGER ({REG_TRIGGER}):   {tcp_regs[REG_TRIGGER]} (cleared by gateway)")
    print(f"  REG_STATUS ({REG_STATUS}):    {tcp_regs[REG_STATUS]} (0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS)")
    print(f"  Current setpoint:  {tcp_regs[REG_SP_READ]/10.0}°C (read from F4S)")
    print(f"  Current temp:      {tcp_regs[REG_TEMP]/10.0}°C")

    # Check result
    if tcp_regs[REG_STATUS] == 0 and tcp_regs[REG_SP_READ] == new_sp_x10:
        print(f"\n✅ SUCCESS: Setpoint write confirmed!")
        return True
    elif tcp_regs[REG_STATUS] == 0:
        print(f"\n⚠️  Write accepted but read-back pending (check cabinet display)")
        return None
    else:
        status_codes = {2: "WRITE_FAILED", 3: "NOT_ACCEPTED", 4: "RANGE", 5: "COMMS"}
        status_msg = status_codes.get(tcp_regs[REG_STATUS], "UNKNOWN")
        print(f"\n❌ FAILED: {status_msg} (status={tcp_regs[REG_STATUS]})")
        return False

if __name__ == '__main__':
    print("F4S RTU Write Test")
    print("NOTE: Gateway must be running in another terminal (python3 python-gateway/f4s_gateway.py)")
    print("      This script shares tcp_regs array with the gateway")

    # Test 1: Write 28.0°C
    print("\n" + "="*60)
    test_write_setpoint(280)  # 28.0°C

    # Test 2: Write 26.5°C
    print("\n" + "="*60)
    time.sleep(1)
    test_write_setpoint(265)  # 26.5°C

    # Test 3: Write out-of-range (should be rejected)
    print("\n" + "="*60)
    time.sleep(1)
    print("TEST: Write out-of-range (250°C, should fail with RANGE error)")
    test_write_setpoint(2500)  # 250.0°C (out of 0-200 range)
