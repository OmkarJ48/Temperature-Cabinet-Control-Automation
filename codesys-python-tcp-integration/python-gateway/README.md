# F4S Modbus TCP↔RTU Gateway

**Status: ✅ Proven working end-to-end on hardware.** Reads, writes-with-confirmation,
and range-validation all verified over real Modbus TCP against a real Watlow F4S.
Next step is CODESYS integration (not started).

This is the canonical, only copy of the gateway. Any other `python-gateway/`
folder in older clones or branches is stale — delete it.

## What this is

A Python process that sits between CODESYS (Modbus TCP master) and a Watlow
F4S temperature cabinet (Modbus RTU slave over `/dev/ttyWatlowF4S`). It is
the **only** process allowed to touch the serial port, and it re-exposes the
cabinet as a 5-register Modbus TCP slave that CODESYS talks to over the
network.

```
CODESYS (TCP master) ──TCP:502──> [this gateway] ──RTU──> Watlow F4S
```

## Register map (Modbus TCP, unit id 1, all values ×10 integers)

| Reg | Name | Direction | Meaning |
|---|---|---|---|
| 0 | `REG_REQ_SP` | CODESYS → gateway | Requested setpoint, e.g. `265` = 26.5°C |
| 1 | `REG_TRIGGER` | CODESYS → gateway | Write `1` to apply; gateway clears to `0` when done |
| 2 | `REG_TEMP` | gateway → CODESYS | Current chamber temperature |
| 3 | `REG_SP_READ` | gateway → CODESYS | Confirmed setpoint (read back from F4S) |
| 4 | `REG_STATUS` | gateway → CODESYS | `0`=OK `2`=WRITE_FAILED `3`=NOT_ACCEPTED `4`=RANGE `5`=COMMS |

Valid setpoint range enforced by the gateway: **-40–200°C (-400–2000 raw)**.

F4S-side RTU registers used: `100` = temperature, `300` = setpoint, slave
address `1`, 19200 baud 8N1.

## Files

- `f4s_gateway.py` — the gateway (RTU cyclic thread + Modbus TCP server)
- `test_rtu_write.py` — TCP client script exercising read / write-confirm / range-reject
- `requirements.txt` — pinned dependencies (see below — **do not casually bump pymodbus**)

## Quick Start

**Always navigate to the python-gateway folder first:**

```bash
cd Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway
```

All commands below assume you are in this directory.

## Install

From the python-gateway directory:

```bash
pip3 install -r requirements.txt --break-system-packages
ls -la /dev/ttyWatlowF4S   # confirm the udev symlink exists
```

`requirements.txt` pins `pymodbus==3.12.1`. This is deliberate, not
arbitrary — see the troubleshooting history below for why 3.13+ silently
breaks the whole gateway.

## Run

From the python-gateway directory:

Port 502 needs root, or grant the bind capability once and run as a normal user:

```bash
# option 1: run as root (from python-gateway directory)
sudo python3 f4s_gateway.py

# option 2 (better): grant bind capability, run as user (from python-gateway directory)
sudo setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))
python3 f4s_gateway.py
```

Expected startup log:
```
=== F4S Gateway Starting ===
RTU connected: /dev/ttyWatlowF4S @ 19200
Cyclic task started (period=1.0s)
Starting TCP server on 0.0.0.0:502
TCP server ready on 0.0.0.0:502
```
Followed by `Temp: NN.N°C` / `SP: NN.N°C` debug lines every second — this
confirms the RTU side is alive before you even touch TCP.

Logs are written to `~/.f4s_gateway/f4s_gateway.log`.

## Run permanently (systemd)

```bash
sudo nano /etc/systemd/system/f4s-gateway.service
```

```ini
[Unit]
Description=F4S Modbus TCP<->RTU Gateway
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway/f4s_gateway.py
Restart=always
User=root
WorkingDirectory=/path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now f4s-gateway
sudo systemctl status f4s-gateway
```

Replace `/path/to/...` with the actual clone path on your machine.

## Verify the TCP side — do this before touching CODESYS

From the gateway host or any machine on the network (replace `10.1.6.17`
with the gateway's IP):

```bash
# read temperature (reg2)
mbpoll -m tcp -a 1 -t 4 -r 2 -c 1 -1 -0 10.1.6.17

# request 26.5°C -> reg0 = 265, then apply -> reg1 = 1
mbpoll -m tcp -a 1 -t 4 -r 0 -0 10.1.6.17 265
mbpoll -m tcp -a 1 -t 4 -r 1 -0 10.1.6.17 1

# read back confirmed setpoint (reg3) and status (reg4)
mbpoll -m tcp -a 1 -t 4 -r 3 -c 1 -1 -0 10.1.6.17     # expect 265
mbpoll -m tcp -a 1 -t 4 -r 4 -c 1 -1 -0 10.1.6.17     # expect 0 (OK)
```

Or run the bundled test script, which does all of the above plus an
out-of-range rejection test:

```bash
python3 test_rtu_write.py
```

The F4S must be on its main run page for a write to be accepted — same rule
as for direct serial access. If these all pass, the gateway is proven
correct **independent of CODESYS** — any problem found after this point is
in the CODESYS-side Modbus TCP master configuration, not here.

---

## Troubleshooting history — how we got here

Documented so nobody has to re-derive this. Every one of these was hit, in
this order, while bringing the gateway up.

### 1. Serial port showing 8E1 instead of 8N1
`mbpoll` defaulted to even parity. Fixed by adding `-P none` to the mbpoll
command line when baselining RTU communication before the gateway existed.
Confirmed working reads (24.3°C, 25.0°C) once parity was set to none.

### 2. `ModbusSparseDataBlock` "does not support item assignment"
Early attempt used a shadow array (`tcp_regs`) synced into the datastore
with `hr_block[i] = tcp_regs[i]`. `ModbusSparseDataBlock` doesn't support
`__setitem__`. Silencing the exception "fixed" the crash but broke sync
silently — the real fix was architectural (see #4).

### 3. TCP reads always 0.0°C, write trigger never cleared
Root cause: the shadow array and the real datastore were two different
objects, synced only one direction. TCP client writes landed in the
datastore; the cyclic task checked the shadow array and never saw them.
This is what led to eliminating the shadow array entirely.

### 4. `setValues`/`getValues` missing, then `simdata[i] =` "worked" but didn't
After removing the shadow array, direct calls to `hr_block.setValues()`
raised `AttributeError`. Introspecting the installed pymodbus showed
`ModbusSparseDataBlock` only exposes a `.simdata` list attribute — no
`setValues`/`getValues` at all. Assigning `hr_block.simdata[i] = value`
"worked" in isolation (a standalone Python REPL test read the value back
correctly) but **still failed once wired into the real gateway** — TCP
reads stayed at 0.0°C and the trigger never cleared.

### 5. The real root cause, found by reading pymodbus's own source

This took an actual walk through `pymodbus/datastore/sparse.py` and
`context.py` (pymodbus 3.14.0) plus a controlled bisect across pymodbus
versions 3.9.2 → 3.14.0. Two independent bugs were stacked:

**5a. `ModbusDeviceContext` deepcopies the datablock once, at construction.**
In pymodbus ≥3.13.0, `ModbusSparseDataBlock`/`ModbusDeviceContext` became
thin deprecated shims around the newer SimData/SimDevice engine.
`ModbusDeviceContext.__init__` does:
```python
hr_simdata = deepcopy(hr.simdata)
self.simdevice = SimDevice(0, simdata=(..., hr_simdata, ...))
```
This copy happens **once**, when the server context is built. Any register
written afterward — e.g. from the RTU cyclic thread, which runs in a loop
forever — writes into a dead copy the live TCP server never looks at again.
This is why TCP reads were permanently stuck at the value present at
startup (0), no matter what the cyclic task did.

Confirmed by bisection: `ModbusSparseDataBlock.setValues()` is a real, live,
mutable method through pymodbus 3.12.x, and becomes a stub with no effect
starting at 3.13.0.

**Fix: pin `pymodbus==3.12.1`** (`requirements.txt`) — the last release
where the datastore is held by reference, not deep-copied.

**5b. Address off-by-one between direct block access and protocol access.**
Independent of 5a, and would have caused failures even after downgrading:
`ModbusDeviceContext.getValues(func_code, address, count)` /
`.setValues(...)` add a **`+1`** address offset before delegating to the
raw block — this is pymodbus's normal protocol-facing convention (Modbus
addressing is famously off-by-one in places). Code that pokes the raw
`ModbusSparseDataBlock` directly (as `hr_block.setValues(2, ...)`, no
offset) writes to a different slot than a real TCP request for address 2
resolves to (which becomes `getValues(3, 2, 1)` → block address `3`
internally). Confirmed with a controlled reproduction: writing register 2
directly on the raw block, then reading register 2 over real TCP, returned
0 — because the TCP layer was actually reading offset 3.

**Fix: never touch the raw block from application code.** All register
access — from the RTU cyclic task and anything else — goes through the
same accessor the TCP server itself uses:
```python
device.setValues(3, address, [value])   # 3 = Modbus function code for holding registers
device.getValues(3, address, count)
```
This is what `f4s_gateway.py` does today. `device` (the `ModbusDeviceContext`)
is built once at module scope, before any thread starts, and is the single
shared object both the cyclic thread and the TCP server operate on.

### 6. Verification method

Before trusting this on real hardware again, the fix was proven with a
fully simulated end-to-end test: a mocked RTU backend plus the real
pymodbus 3.12.1 TCP client/server, covering:
- live temperature/setpoint reads reflecting the "RTU" side
- write-with-confirmation: trigger clears, status goes to `0` (OK), confirmed
  setpoint updates on the next poll cycle
- range rejection: an out-of-range write is rejected with status `4`
  (RANGE) and the setpoint is left unchanged

All three passed. The same behavior was then reproduced on the actual
Raspberry Pi against the real F4S (see the log excerpt below) — reads
track the real cabinet temperature, a write to 28.0°C and then 26.5°C both
confirm and clear the trigger, and the log shows the RTU write / read-back
/ status sequence exactly as designed.

```
DEBUG - Temp: 24.8°C
DEBUG - SP: 25.0°C
...
INFO - RTU write: reg300 = 280
INFO - Setpoint write confirmed: 280
INFO - Write SUCCESS: 28.0°C
...
DEBUG - SP: 28.0°C
```

## Full T1–T5 Test Plan

### Prerequisites

#### 1. Environment Setup
```bash
python3 --version  # Should be Python 3.10+
pip3 install -r requirements.txt --break-system-packages
pip3 list | grep pymodbus  # Expected: pymodbus 3.12.1
```

**IMPORTANT: pymodbus MUST be pinned to 3.12.1.** Starting in pymodbus 3.13.0,
`ModbusSparseDataBlock`/`ModbusDeviceContext` became deprecated shims around
the new SimData/SimDevice API: `ModbusDeviceContext.__init__` now does a
one-time `deepcopy()` of the datablock into an internal store, so any
register writes made after construction (e.g. from the RTU cyclic thread)
never reach the live TCP-facing storage — TCP reads stay stuck at 0 and
writes never get seen. pymodbus 3.12.1 is the last release where these
classes store the datablock by reference, so runtime mutation actually
works. Do not upgrade past 3.12.1 without re-validating this end-to-end.

#### 2. Verify Serial Port
```bash
ls -la /dev/ttyWatlowF4S
# Expected: /dev/ttyWatlowF4S -> ttyUSB0
```

#### 3. Verify RTU Communication Baseline
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 /dev/ttyWatlowF4S
# Expected: Register 100 value (current temperature x10, e.g., 215 = 21.5°C)

mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 /dev/ttyWatlowF4S
# Expected: Register 300 value (current setpoint x10, e.g., 265 = 26.5°C)
```

---

### T1: Gateway Startup & RTU Layer Verification

**Objective:** Confirm RTU connection works and cyclic polling is active

**Steps:**
1. Terminal 1: Navigate to python-gateway folder and start the gateway
   ```bash
   cd Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway
   python3 f4s_gateway.py
   ```
   
   **Expected output:**
   ```
   === F4S Gateway Starting ===
   RTU connected: /dev/ttyWatlowF4S @ 19200
   Cyclic task started (period=1.0s)
   Starting TCP server on 0.0.0.0:502
   TCP server ready on 0.0.0.0:502
   ```

2. Terminal 2: Monitor the log
   ```bash
   tail -f ~/.f4s_gateway/f4s_gateway.log
   ```
   
   **Expected:** See "Temp:" and "SP:" messages every 1 second

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
1. With gateway running, in Terminal 3: Navigate to python-gateway folder and run the test
   ```bash
   cd Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway
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
   INFO - RTU write: reg300 = 280
   INFO - Setpoint write confirmed: 280
   INFO - Write SUCCESS: 28.0°C
   ```

**Pass Criteria:**
- ✅ Write trigger accepted
- ✅ Trigger cleared after processing
- ✅ Status = 0 (OK)
- ✅ Read-back shows new setpoint
- ✅ Log shows RTU write and confirmation

---

### T4: Range Validation (Out-of-Range Write)

**Objective:** Verify range check (-40-200°C = -400-2000 x10)

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
   WARNING - Out of range: 250.0°C
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

## CODESYS Integration (After T1-T4 Passing)

Once T1–T4 tests pass, the gateway is ready for CODESYS integration:

### Step 1: Add Modbus TCP Master Device

In CODESYS IDE (on the sandbox project):

1. **Devices → Add Device**
2. **Select "Modbus_Master" (or "Modbus TCP Master")**
3. **Configuration:**
   - **Network adapter:** Your network (Ethernet that can reach gateway IP)
   - **IP address:** `10.1.6.17` (or your gateway's IP)
   - **Port:** `502`
   - **Slave ID:** `1`
   - **Cycle time:** e.g., `100 ms` (cyclic read interval)

### Step 2: Configure TCP Channels

Create 5 channels (one per register):

| Channel | Name | FC | Address | Length | Type | R/W |
|---------|------|----|---------| -------|------|-----|
| 1 | ReadTemp | 03 | 2 | 1 | WORD | Read |
| 2 | ReadSetpoint | 03 | 3 | 1 | WORD | Read |
| 3 | WriteSetpoint | 06 | 0 | 1 | WORD | Write |
| 4 | WriteTrigger | 06 | 1 | 1 | WORD | Write |
| 5 | ReadStatus | 03 | 4 | 1 | WORD | Read |

### Step 3: Map Channels to GVL_Modbus

**I/O Mapping:**
- Channel 1 (ReadTemp) → `GVL_Modbus.wReadTempValue`
- Channel 2 (ReadSetpoint) → `GVL_Modbus.wSetpoint1Read`
- Channel 3 (WriteSetpoint) → `GVL_Modbus.wSetpoint1Write`
- Channel 4 (WriteTrigger) → `GVL_Modbus.xWriteTrigger`
- Channel 5 (ReadStatus) → `GVL_Modbus.xModbusError` (reuse for status, or create new var)

### Step 4: Copy Retargeted PLC_PRG

In sandbox CODESYS project, replace your `PLC_PRG` with `PLC_PRG_TCP_Retargeted.st`.

The retargeted version:
- Reads from TCP registers (via mapped channels)
- Same state machine as serial version (IDLE → READY → WRITING → CONFIRM → IDLE/FAULTED)
- Edge-triggered write (one pulse per user request)
- Range validation (-40–200 °C)
- Status/fault code interpretation

---

## Systemd Service Setup

To run the gateway permanently on a Raspberry Pi or Linux system:

```bash
sudo nano /etc/systemd/system/f4s-gateway.service
```

Paste the following:

```ini
[Unit]
Description=F4S Modbus TCP<->RTU Gateway
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway/f4s_gateway.py
Restart=always
User=root
WorkingDirectory=/path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway

[Install]
WantedBy=multi-user.target
```

Replace `/path/to/...` with the actual clone path on your machine.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now f4s-gateway
sudo systemctl status f4s-gateway
```

Verify status and logs:

```bash
sudo systemctl status f4s-gateway
sudo journalctl -u f4s-gateway -f
```

---

## What's Left Before Full Deployment

Nothing on the Python side. The gateway is proven independent of CODESYS
via the `mbpoll`/`test_rtu_write.py` verification above (T1-T4). The next step is
configuring the CODESYS Modbus TCP master to point at this gateway's IP:502
and map the 5 registers per the table at the top of this file — that work
is documented in the CODESYS Integration section above.
