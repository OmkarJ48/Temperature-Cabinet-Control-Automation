#!/usr/bin/env python3
"""
Test script: Write setpoint to F4S via Modbus TCP gateway
Simulates CODESYS writing a new setpoint and reading back confirmation

USAGE (from the python-gateway directory):
  python3 f4s_gateway.py   # Terminal 1
  python3 test_rtu_write.py  # Terminal 2 (after gateway has started)
"""
import sys
import time
from pymodbus.client import ModbusTcpClient

# Modbus TCP register indices
REG_REQ_SP = 0       # Requested setpoint (write)
REG_TRIGGER = 1      # Apply trigger (write)
REG_TEMP = 2         # Current temperature (read)
REG_SP_READ = 3      # Confirmed setpoint (read)
REG_STATUS = 4       # Status code (read)

def test_write_setpoint(client, new_sp_x10):
    """
    Trigger a setpoint write and monitor for confirmation
    new_sp_x10: setpoint value x10 (e.g., 280 = 28.0°C)
    """
    print(f"\n{'='*60}")
    print(f"TEST: Write setpoint {new_sp_x10/10.0}°C")
    print(f"{'='*60}")

    # Read current state before write
    print(f"\nBefore write:")
    temp_result = client.read_holding_registers(address=REG_TEMP, count=1, slave_id=1)
    sp_result = client.read_holding_registers(address=REG_SP_READ, count=1, slave_id=1)
    status_result = client.read_holding_registers(address=REG_STATUS, count=1, slave_id=1)

    if not temp_result.isError() and not sp_result.isError() and not status_result.isError():
        print(f"  Current temp:      {temp_result.registers[0]/10.0}°C")
        print(f"  Current setpoint:  {sp_result.registers[0]/10.0}°C")
        print(f"  Status:            {status_result.registers[0]}")
    else:
        print(f"  ❌ Failed to read registers (connection issue?)")
        return False

    # Write setpoint request and trigger
    print(f"\nSetting write trigger:")
    print(f"  Writing REG_REQ_SP ({REG_REQ_SP}):  {new_sp_x10} = {new_sp_x10/10.0}°C")
    client.write_register(address=REG_REQ_SP, value=new_sp_x10, slave_id=1)

    print(f"  Writing REG_TRIGGER ({REG_TRIGGER}):   1 (request sent)")
    client.write_register(address=REG_TRIGGER, value=1, slave_id=1)

    # Wait for gateway to process write
    print(f"\nWaiting for gateway to process write...")
    trigger_cleared = False
    for i in range(20):  # Wait up to 2 seconds
        time.sleep(0.1)
        trigger_result = client.read_holding_registers(address=REG_TRIGGER, count=1, slave_id=1)
        if not trigger_result.isError() and trigger_result.registers[0] == 0:
            trigger_cleared = True
            break

    # Read result
    print(f"\nAfter write:")
    trigger_result = client.read_holding_registers(address=REG_TRIGGER, count=1, slave_id=1)
    status_result = client.read_holding_registers(address=REG_STATUS, count=1, slave_id=1)
    sp_result = client.read_holding_registers(address=REG_SP_READ, count=1, slave_id=1)
    temp_result = client.read_holding_registers(address=REG_TEMP, count=1, slave_id=1)

    if not all([trigger_result.isError(), status_result.isError(), sp_result.isError(), temp_result.isError()]):
        trigger_val = 0 if trigger_result.isError() else trigger_result.registers[0]
        status_val = 0 if status_result.isError() else status_result.registers[0]
        sp_val = 0 if sp_result.isError() else sp_result.registers[0]
        temp_val = 0 if temp_result.isError() else temp_result.registers[0]

        print(f"  REG_TRIGGER ({REG_TRIGGER}):   {trigger_val} (cleared={trigger_cleared})")
        print(f"  REG_STATUS ({REG_STATUS}):    {status_val} (0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS)")
        print(f"  Current setpoint:  {sp_val/10.0}°C (read from F4S)")
        print(f"  Current temp:      {temp_val/10.0}°C")

        # Check result
        if status_val == 0 and sp_val == new_sp_x10 and trigger_cleared:
            print(f"\n✅ SUCCESS: Setpoint write confirmed!")
            return True
        elif status_val == 0 and trigger_cleared:
            print(f"\n⚠️  Write accepted but read-back pending (check cabinet display)")
            return None
        else:
            status_codes = {2: "WRITE_FAILED", 3: "NOT_ACCEPTED", 4: "RANGE", 5: "COMMS"}
            status_msg = status_codes.get(status_val, "UNKNOWN")
            print(f"\n❌ FAILED: {status_msg} (status={status_val})")
            return False
    else:
        print(f"  ❌ Failed to read response registers")
        return False

if __name__ == '__main__':
    print("F4S RTU Write Test via Modbus TCP")
    print("NOTE: Gateway must be running (python3 f4s_gateway.py)")
    print("      Connecting to TCP server on localhost:502...")

    # Connect to gateway TCP server
    client = ModbusTcpClient(host='localhost', port=502)
    if not client.connect():
        print("❌ Failed to connect to gateway on localhost:502")
        print("   Make sure the gateway is running: python3 f4s_gateway.py")
        sys.exit(1)

    print("✅ Connected to gateway!\n")

    try:
        # Test 1: Write 28.0°C
        print("="*60)
        test_write_setpoint(client, 280)  # 28.0°C

        # Test 2: Write 26.5°C
        print("\n" + "="*60)
        time.sleep(1)
        test_write_setpoint(client, 265)  # 26.5°C

        # Test 3: Write out-of-range (should be rejected)
        print("\n" + "="*60)
        time.sleep(1)
        print("TEST: Write out-of-range (250°C, should fail with RANGE error)")
        test_write_setpoint(client, 2500)  # 250.0°C (out of 0-200 range)

    finally:
        client.close()
        print("\n" + "="*60)
        print("Test complete. Gateway connection closed.")
