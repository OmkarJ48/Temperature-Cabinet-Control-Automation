# F4S Gateway Testing Guide

## Prerequisites

### 1. Environment Setup
```bash
# On Raspberry Pi 10.1.6.17 or target deployment system
python3 --version  # Should be Python 3.10+
pip3 install pymodbus==3.14.0
```

### 2. Verify Dependencies
```bash
pip3 list | grep pymodbus
# Expected: pymodbus 3.14.0
```

### 3. Check Serial Port
```bash
# Verify Watlow F4S is connected to /dev/ttyWatlowF4S
ls -la /dev/ttyWatlowF4S
# Expected: /dev/ttyWatlowF4S -> ttyUSB0
```

### 4. Verify RTU Communication Baseline
```bash
# Use mbpoll to test RTU connection before Python gateway
# This ensures F4S is reachable before adding gateway complexity
mbpoll -m rtu -a 1 -b 19200 -t 4:uint16 -c 1 /dev/ttyWatlowF4S 100
# Expected: Register 100 value (current temperature x10)

mbpoll -m rtu -a 1 -b 19200 -t 4:uint16 -c 1 /dev/ttyWatlowF4S 300
# Expected: Register 300 value (current setpoint x10)
```

---

## Test Plan (T1-T5)

### T1: Gateway Startup & RTU Layer Verification

**Objective:** Confirm RTU connection works and cyclic polling is active

**Steps:**
1. Terminal 1: Start the gateway
   ```bash
   cd python-gateway
   python3 f4s_gateway.py
   ```
   
   **Expected output:**
   ```
   2026-07-20 12:00:00,123 - INFO - === F4S Gateway Starting ===
   2026-07-20 12:00:00,124 - INFO - RTU connected: /dev/ttyWatlowF4S @ 19200
   2026-07-20 12:00:00,125 - INFO - Cyclic task started (period=1.0s)
   2026-07-20 12:00:00,126 - INFO - TCP server datastore initialized (holding registers 0-9)
   2026-07-20 12:00:00,127 - INFO - Starting TCP server on 0.0.0.0:502
   2026-07-20 12:00:01,128 - INFO - TCP server ready on 0.0.0.0:502
   ```

2. Terminal 2: Monitor the log
   ```bash
   tail -f ~/.f4s_gateway/f4s_gateway.log
   ```
   
   **Expected:** See "Temp:" and "SP:" messages every 1 second
   ```
   2026-07-20 12:00:02,050 - DEBUG - Temp: 22.5°C
   2026-07-20 12:00:02,051 - DEBUG - SP: 25.0°C
   2026-07-20 12:00:03,052 - DEBUG - Temp: 22.5°C
   2026-07-20 12:00:03,053 - DEBUG - SP: 25.0°C
   ```

**Pass Criteria:**
- ✅ RTU connected successfully
- ✅ Cyclic task started
- ✅ TCP server listening on :502
- ✅ Logs show temperature and setpoint updates every 1s
- ✅ No errors in the log

---

### T2: TCP Register Read (No Write)

**Objective:** Verify TCP clients can read RTU values from gateway

**Steps:**
1. With gateway running (from T1), in Terminal 3:
   ```bash
   python3 -c "
   from pymodbus.client import ModbusTcpClient
   client = ModbusTcpClient(host='localhost', port=502)
   client.connect()
   
   # Read 5 holding registers (indices 0-4)
   result = client.read_holding_registers(address=0, count=5, device_id=1)
   
   print('Holding Registers (0-4):')
   for i, val in enumerate(result.registers):
       print(f'  Reg[{i}]: {val}')
   
   client.close()
   "
   ```
   
   **Expected output:**
   ```
   Holding Registers (0-4):
     Reg[0]: 0         # REG_REQ_SP (requested setpoint, not yet written)
     Reg[1]: 0         # REG_TRIGGER (trigger, not yet set)
     Reg[2]: 225       # REG_TEMP (current temperature = 22.5°C)
     Reg[3]: 250       # REG_SP_READ (current setpoint = 25.0°C)
     Reg[4]: 0         # REG_STATUS (OK)
   ```

**Pass Criteria:**
- ✅ TCP read succeeds (no connection errors)
- ✅ Reg[2] (temperature) shows a non-zero value matching F4S
- ✅ Reg[3] (setpoint) shows a non-zero value matching F4S
- ✅ Reg[4] (status) is 0 (OK)
- ✅ Values match what RTU reads show in the log

---

### T3: TCP Register Write (Setpoint Trigger)

**Objective:** Verify write-trigger mechanism and confirmation

**Steps:**
1. With gateway running, in Terminal 3:
   ```bash
   cd python-gateway
   python3 test_rtu_write.py
   ```
   
   **Expected output:**
   ```
   F4S RTU Write Test via Modbus TCP
   NOTE: Gateway must be running (python3 f4s_gateway.py)
         Connecting to TCP server on localhost:502...
   ✅ Connected to gateway!
   
   ============================================================
   TEST: Write setpoint 28.0°C
   ============================================================
   
   Before write:
     Current temp:      22.5°C
     Current setpoint:  25.0°C
     Status:            0
   
   Setting write trigger:
     Writing REG_REQ_SP (0):  280 = 28.0°C
     Writing REG_TRIGGER (1):   1 (request sent)
   
   Waiting for gateway to process write...
   
   After write:
     REG_TRIGGER (1):   0 (cleared=True)
     REG_STATUS (4):    0 (0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS)
     Current setpoint:  28.0°C (read from F4S)
     Current temp:      22.5°C
   
   ✅ SUCCESS: Setpoint write confirmed!
   ```

2. Check the log for write operations:
   ```bash
   tail -50 ~/.f4s_gateway/f4s_gateway.log | grep -E "(Write|write|Setpoint)"
   ```
   
   **Expected:**
   ```
   2026-07-20 12:00:30,100 - INFO - RTU write: reg300 = 280
   2026-07-20 12:00:30,200 - INFO - Setpoint write confirmed: 280
   2026-07-20 12:00:30,201 - INFO - Write SUCCESS: 28.0°C
   ```

**Pass Criteria:**
- ✅ Write trigger accepted
- ✅ Trigger cleared after processing
- ✅ Status = 0 (OK)
- ✅ Read-back shows new setpoint
- ✅ Log shows RTU write and confirmation

---

### T4: Range Validation (Out-of-Range Write)

**Objective:** Verify range check (0-200°C = 0-2000 x10)

**Steps:**
1. With gateway running, write an out-of-range value:
   ```bash
   python3 -c "
   from pymodbus.client import ModbusTcpClient
   client = ModbusTcpClient(host='localhost', port=502)
   client.connect()
   
   # Write out-of-range: 250°C = 2500 x10 (valid range: 0-2000)
   client.write_register(address=0, value=2500, device_id=1)
   client.write_register(address=1, value=1, device_id=1)
   
   import time
   time.sleep(1)  # Wait for gateway to process
   
   # Read status
   result = client.read_holding_registers(address=4, count=1, device_id=1)
   status = result.registers[0]
   
   print(f'Status after out-of-range write: {status}')
   print(f'  0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS')
   
   client.close()
   "
   ```
   
   **Expected:**
   ```
   Status after out-of-range write: 4
     0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS
   ```

2. Check the log:
   ```bash
   tail -20 ~/.f4s_gateway/f4s_gateway.log | grep -i range
   ```
   
   **Expected:**
   ```
   2026-07-20 12:00:45,300 - WARNING - Out of range: 250.0°C
   ```

**Pass Criteria:**
- ✅ Status = 4 (RANGE error)
- ✅ Log shows range validation warning
- ✅ F4S setpoint unchanged (remains at previous value)

---

### T5: Communications Timeout (Optional, Advanced)

**Objective:** Verify comms health check

**Steps:**
1. With gateway running, manually disconnect the F4S serial cable
2. Wait 5+ seconds (the timeout threshold)
3. Read status:
   ```bash
   python3 -c "
   from pymodbus.client import ModbusTcpClient
   client = ModbusTcpClient(host='localhost', port=502)
   client.connect()
   
   result = client.read_holding_registers(address=4, count=1, device_id=1)
   status = result.registers[0]
   
   print(f'Status after comms timeout: {status}')
   print(f'  0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS')
   
   client.close()
   "
   ```
   
   **Expected:**
   ```
   Status after comms timeout: 5
     0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS
   ```

4. Reconnect the serial cable and wait 1s for recovery

**Pass Criteria:**
- ✅ Status = 5 (COMMS timeout)
- ✅ Recovers after cable reconnected
- ✅ No crashes, graceful degradation

---

## Troubleshooting

### Gateway won't start
```bash
# Check if port 502 is already in use
lsof -i :502
# If occupied, either kill the process or use a different port (edit SERIAL_PORT in gateway)
```

### RTU reads return zeros
```bash
# Verify serial connection with mbpoll first
mbpoll -m rtu -a 1 -b 19200 -t 4:uint16 -c 1 /dev/ttyWatlowF4S 100

# Check log for errors
tail -f ~/.f4s_gateway/f4s_gateway.log | grep -i error
```

### TCP reads return zeros
```bash
# Verify the sync loop is updating hr_block
# Uncomment debug logging in f4s_gateway.py line 250-253:
#   logger.debug(f"Sync: hr_block[{i}] = {tcp_regs[i]}")

# Watch the log for sync messages
tail -f ~/.f4s_gateway/f4s_gateway.log | grep "Sync"
```

### Write trigger doesn't clear
```bash
# Check if there's an exception in the cyclic task
tail -100 ~/.f4s_gateway/f4s_gateway.log | grep -i exception

# Verify the F4S is accepting writes with mbpoll:
mbpoll -m rtu -a 1 -b 19200 -t 6:uint16 /dev/ttyWatlowF4S 300 280
```

---

## Integration with CODESYS

Once T1-T4 pass, the gateway is ready for CODESYS integration:

1. Add Modbus TCP master device in CODESYS (point to localhost:502)
2. Create 5 channels:
   - REG_REQ_SP (0, write, temperature request)
   - REG_TRIGGER (1, write, apply trigger)
   - REG_TEMP (2, read, current temperature)
   - REG_SP_READ (3, read, confirmed setpoint)
   - REG_STATUS (4, read, status code)
3. Map channels to GVL_Modbus variables
4. Copy PLC_PRG_TCP_Retargeted.st into the sandbox project
5. Run CODESYS test with the same T1-T5 scenarios

---

## Logs & Diagnostics

All gateway logs are written to: `~/.f4s_gateway/f4s_gateway.log`

**Key log patterns:**
- `RTU connected` → RTU layer ready
- `Cyclic task started` → Polling loop active
- `TCP server ready` → Server listening
- `Temp:` and `SP:` (DEBUG) → RTU reads happening
- `RTU write: reg` → Write in progress
- `Setpoint write confirmed` → Read-back successful
- `RTU comms timeout` → 5s without response from F4S
- `Exception` → Error in cyclic task or TCP server

---

## Next Steps

After T1-T5 tests pass:
1. Commit test results to the git branch
2. Configure systemd service unit for autonomous startup
3. Integrate with CODESYS sandbox project
4. Run full end-to-end tests with CODESYS as TCP master
5. Verify setpoint changes persist to F4S across power cycles
