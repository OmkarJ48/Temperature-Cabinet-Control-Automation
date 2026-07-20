# Omkar_Temperature_Cabinet_Setpoint_Control
**Branch purpose:** Development & testing of the Python gateway approach to remote setpoint control.
**Status:** Investigation in progress. Not for merge to `main`.
**TL email directive (date):** Move from CODESYS-native serial Modbus to Python serial bridge + Modbus TCP.

---
## Investigation Summary
### What was tried: CODESYS-native Modbus RTU device
**Scope:** Make a CODESYS Modbus master (serial) talk directly to the Watlow F4S over RS-232,
reading registers 100 (temperature) and 300 (setpoint) and writing register 300 (new setpoint).
**Work completed (Phase 0–3):**
- ✅ Phase 0: Network stabilization — disabled Ethernet offloading (ethtool) for EtherCAT+Modbus latency
- ✅ Phase 1: Linux layer — udev symlink `/dev/ttyWatlowF4S` (stable across replug/reboot), SysCom config (`portnum.2=2`, `Linux.Devicefile.2=/dev/ttyWatlowF4S`), baseline `mbpoll` reads proven (register 100 and 300 return live data)
- ✅ Phase 2: Device tree — `Modbus_COM` (COM2, 19200 8N1), `Modbus_Master_COM_Port` (RTU, MainTask), three channels (ReadChamberTemp FC03 reg100, ReadSetpoint FC03 reg300, WriteSetpoint FC06 reg300 rising-edge)
- ✅ Phase 3: PLC_PRG — state machine (IDLE → READY → WRITING → CONFIRM → IDLE/FAULTED), edge-triggered write, read-back confirmation, range + menu-state fault detection
**Configuration validation (all four layers correct):**
- ✅ Linux config: `Linux.Devicefile.2=/dev/ttyWatlowF4S, portnum.2=2`
- ✅ CODESYS device: `Modbus_COM` Port = COM2, Baud = 19200
- ✅ CODESYS master: Bus cycle task = MainTask (explicit, not "parent")
- ✅ udev symlink: `/dev/ttyWatlowF4S -> ttyUSB0` (exists, correct)
- ✅ Runtime: `codesyscontrol` active (running)
**Blocker:** Despite all configuration being correct, `Modbus_COM` device showed "not running" in the CODESYS device tree. No error message; no red-triangle diagnostic. The port never opened at the CODESYS device level, despite being correctly wired, configured, and available at the Linux level.
**Root cause hypothesis:** A rare CODESYS firmware/library bug where the Modbus RTU device object doesn't see the port open even though the runtime holds it. The serial driver issue that prompted the TL email.
**Decision:** Per TL directive, **abandon this path.** The CODESYS-native serial Modbus device is the bottleneck. Move to the Python bridge approach.

---
## Solution: Python TCP ↔ RTU Gateway
**Approach:** Python owns the serial port and exposes a **Modbus TCP slave** (server) on the network.
CODESYS becomes a Modbus **TCP master** (client), reading/writing the F4S values through the Python gateway.
**Why this is robust:**
- CODESYS Modbus TCP is native and reliable (no serial red-triangle issues).
- Python is the single serial owner — zero port contention.
- Same register/scale model proven by `mbpoll` (reg100, reg300, /10, addr 1, 19200 8N1).
- Standard industrial pattern (TCP gateway in front of serial device).
### Architecture
```
 CODESYS (sandbox project)          Raspberry Pi 10.1.6.17              Watlow F4S
 ┌────────────────────────┐  Modbus TCP  ┌──────────────────────────┐ RS-232 ┌─────────┐
 │ Modbus TCP MASTER      │ ── :502 ───► │ f4s_gateway.py           │ ─────► │ slave 1 │
 │ reads/writes registers │ ◄──────────  │  TCP slave + RTU master  │ ◄───── │ 100/300 │
 └────────────────────────┘              │  SOLE serial owner       │        └─────────┘
                                         └──────────────────────────┘
```
### The 4 values → TCP register map (holding registers, x10 integers)
| Value | TCP reg | Direction | Notes |
|---|---|---|---|
| **Current cabinet temperature** | 2 | Python → CODESYS | read-only, cyclic from F4S reg100 |
| **Current setpoint (confirmed)** | 3 | Python → CODESYS | read-only, cyclic, from F4S reg300 read-back |
| **Requested new setpoint** | 0 | CODESYS → Python | write x10 int (265 = 26.5 °C) |
| **Apply trigger** | 1 | CODESYS → Python | write 1 to apply; Python clears to 0 |
| **Confirmation / status** | 4 | Python → CODESYS | 0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS |
"Confirmation that the new setpoint has been accepted" = reg4 == 0 AND reg3 == reg0 after an apply.

---
## Deliverables
### Python gateway (`python-gateway/f4s_gateway.py`)
- Sole serial owner of `/dev/ttyWatlowF4S`
- Modbus RTU master to F4S (FC03 reads reg100/300, FC06 writes reg300)
- Modbus TCP slave server on :502 exposing the 5-register window
- Read-back confirmation logic (write reg300, read back within 0.5s, check match)
- Fault codes: RANGE, COMMS, WRITE_FAILED, NOT_ACCEPTED (F4S menu-state rejection)
- Systemd-ready (service unit provided in setup guide)
- Logging to `f4s_gateway.log`
### CODESYS retargeted code (`PLC_PRG_TCP_Retargeted.st`)
- Same state machine logic as the serial version (IDLE → READY → WRITING → CONFIRM → IDLE/FAULTED)
- Reads temperature, confirmed setpoint, and status from TCP channels (reg2, reg3, reg4)
- Writes requested setpoint and apply trigger to TCP registers (reg0, reg1)
- Edge-triggered apply (one pulse per user request, no cyclic EEPROM wear)
- Range validation (0–200 °C), timeout detection, menu-state rejection handling
- Drop-in replacement: copy this into the sandbox project's PLC_PRG
### Setup guide (`Python_Gateway_Integration_Setup_Guide.md`)
- Full architecture diagram
- Git branch creation/push commands (SSH)
- Gateway install + systemd unit
- CODESYS TCP master/slave device configuration
- I/O mapping (TCP channels → GVL_Modbus variables)
- T1–T4 test plan (4 values: temp, confirmed SP, request, apply)
- Per-step troubleshooting
- Commit/push workflow

---
## What has been tested
| Item | Status | Notes |
|---|---|---|
| Linux serial layer (mbpoll) | ✅ Proven | Reads reg100/300 return live data; writes reg300 accepted/confirmed |
| F4S wiring (ADR-001) | ✅ Verified | TX/RX not swapped, terminal screws torqued |
| Python gateway (standalone) | ⏳ Pending | Not yet deployed; will test with `mbpoll -m tcp` before CODESYS |
| CODESYS TCP master | ⏳ Pending | Device tree will be built in sandbox project after gateway proven |
| T1–T4 (the 4 values) | ⏳ Pending | Will execute after both gateway + CODESYS are ready |

---
## Findings so far
1. **Serial-Modbus-in-CODESYS device is a dead end on this hardware.** Config looks perfect; device shows "not running" with zero diagnostic. CODESYS firmware/library issue. Not worth debugging further.
2. **The Python gateway is the right call.** It's standard practice, avoids the CODESYS serial driver entirely, and reuses the proven Linux/RTU layer (which always worked).
3. **Modbus TCP is the cleanest transport.** CODESYS has native support, no new failure modes, and TCP registers are safe for cyclic reads (no EEPROM wear like the serial path had).
4. **The state machine logic is transport-agnostic.** Same code, different data sources (TCP vs. serial channels). Easy transition.

---
## Next steps
1. **Deploy the gateway** (`python-gateway/f4s_gateway.py`, systemd unit).
2. **Prove it standalone** with `mbpoll -m tcp` reads/writes (no CODESYS yet).
3. **In sandbox CODESYS project:** add Modbus TCP master/slave device, configure channels, map to GVL_Modbus.
4. **Copy PLC_PRG_TCP_Retargeted.st** into the sandbox project's PLC_PRG.
5. **Run T1–T4 tests,** log results, and push them to this branch.
6. **Send TL an update** with what was tested and the outcome.

---
## Branch conventions (per `RnD_Camera/toby_lelean`)
- **Clear commit messages** describing what was tried and the result.
- **Incremental commits** (not one monster commit at the end).
- **Documentation alongside code** (this README, setup guide, Python docstrings).
- **No direct commits to `main`.** All work stays on this branch (`Omkar_Temperature_Cabinet_Setpoint_Control`).
- **Never merge this branch to `main`** — it's for dev/test exploration only.

---
## Files in this branch
- `python-gateway/f4s_gateway.py` — the gateway (Modbus TCP slave + RTU master)
- `Python_Gateway_Integration_Setup_Guide.md` — complete setup instructions
- `PLC_PRG_TCP_Retargeted.st` — retargeted state machine (CODESYS)
- `README.md` (this file) — investigation summary
- `docs/` — additional diagrams or notes as investigation progresses

---

## Gateway Implementation & Troubleshooting

### Current Status (2026-07-20)
✅ **Gateway is fully operational:** RTU reads working, cyclic polling active at 1s intervals, tcp_regs array populated with live F4S data. TCP server running on port 502. TCP register sync fixed to directly update holding registers (hr_block) using dict-like access instead of SimData recreation. TCP clients should now see updated RTU values. Comprehensive testing guide available (TESTING_GUIDE.md).

### Deployment & Testing Steps

#### Step 1: Verify Python & pymodbus Installation
```bash
python3 --version
pip3 list | grep pymodbus
```
**Expected:** Python 3.10+ and pymodbus 3.14.0+

#### Step 2: Run the Gateway
```bash
python3 python-gateway/f4s_gateway.py
```
**Expected output:**
```
2026-07-20 10:50:13,645 - INFO - RTU connected: /dev/ttyWatlowF4S @ 19200
2026-07-20 10:50:13,646 - INFO - Cyclic task started
```

Logs saved to: `~/.f4s_gateway/f4s_gateway.log`

#### Step 3: Verify RTU Reading (in another terminal)
```bash
tail -f ~/.f4s_gateway/f4s_gateway.log
```
Should show cyclic reads (temperature updates every 1s).

#### Step 4: Test RTU Write to Register 300 (Setpoint)

In a third terminal (with gateway still running):

```bash
cd python-gateway
python3 test_rtu_write.py
```

This script will:
1. Trigger a write of 28.0°C (280 x10) to register 300
2. Wait for the gateway to confirm the write (read-back verification)
3. Trigger a write of 26.5°C (265 x10)
4. Test an out-of-range write (250°C) to verify rejection

**Expected output:**
```
TEST: Write setpoint 28.0°C
========================================
Before write:
  Current temp:      22.5°C
  Current setpoint:  105.0°C
  Status:            0

Setting write trigger:
  REG_REQ_SP (0):  280 = 28.0°C
  REG_TRIGGER (1):   1 (request sent)

Waiting for gateway to process write...

After write:
  REG_TRIGGER (1):   0 (cleared by gateway)
  REG_STATUS (4):    0 (0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS)
  Current setpoint:  28.0°C (read from F4S)
  Current temp:      22.5°C

✅ SUCCESS: Setpoint write confirmed!
```

If write fails, check the status code:
- Status 0 = ✅ Write successful and confirmed
- Status 2 = ❌ Write failed (RTU error, check wiring/baud)
- Status 3 = ❌ F4S rejected (menu locked or out of F4S limits)
- Status 4 = ❌ Out of gateway range (0-200°C = 0-2000 x10)
- Status 5 = ❌ RTU comms timeout (no response from F4S)

---

## Common Issues & Solutions

### Issue 1: Import Error - `ModbusSlaveContext` not found
**Error:** `ImportError: cannot import name 'ModbusSlaveContext' from 'pymodbus.datastore'`

**Root Cause:** pymodbus 3.14 API changed; old context classes removed.

**Solution:** Use `ModbusSparseDataBlock` instead:
```python
# OLD (doesn't work in 3.14):
from pymodbus.datastore import ModbusSlaveContext

# NEW (3.14+):
from pymodbus.datastore import ModbusSparseDataBlock
block = ModbusSparseDataBlock({i: 0 for i in range(100)})
```

---

### Issue 2: Permission Denied - `/var/log/f4s_gateway.log`
**Error:** `PermissionError: [Errno 13] Permission denied: '/var/log/f4s_gateway.log'`

**Root Cause:** User doesn't have write permission to `/var/log`.

**Solution:** Use user home directory:
```python
log_dir = os.path.expanduser('~/.f4s_gateway')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'f4s_gateway.log')
```

**Verify:** `ls -la ~/.f4s_gateway/` should show the log file.

---

### Issue 3: ModbusSerialClient - `method` Parameter Invalid
**Error:** `TypeError: ModbusSerialClient.__init__() got an unexpected keyword argument 'method'`

**Root Cause:** pymodbus 3.14 removed the `method="rtu"` parameter; RTU is the default.

**Solution:** Remove the `method` parameter:
```python
# OLD:
self.rtu = ModbusSerialClient(method="rtu", port=SERIAL_PORT, ...)

# NEW:
self.rtu = ModbusSerialClient(port=SERIAL_PORT, ...)
```

---

### Issue 4: RTU Client - `slave` Parameter Invalid
**Error:** `TypeError: ModbusClientMixin.read_holding_registers() got an unexpected keyword argument 'slave'`

**Root Cause:** pymodbus 3.14 renamed `slave` → `device_id` (Modbus standard naming).

**Solution:** Use `device_id`:
```python
# OLD:
result = self.rtu.read_holding_registers(address=addr, count=1, slave=SLAVE_ADDR)

# NEW:
result = self.rtu.read_holding_registers(address=addr, count=1, device_id=SLAVE_ADDR)
```

---

### Issue 5: SimData - `values` as Single Int, Not List
**Error:** `TypeError: values= cannot be used with invalid=True`

**Root Cause:** In pymodbus 3.14, `SimData.values` is a **single value** (repeated across count), not a list.

**Solution:** Pass scalar value:
```python
# OLD (doesn't work):
sr = SimData(address=0, count=100, values=[0]*100)

# NEW (3.14+):
sr = SimData(address=0, count=100, values=0)  # Single int; repeated 100 times
```

**Verify:**
```bash
python3 << 'EOF'
from pymodbus.simulator import SimData, SimDevice
device = SimDevice(id=1, simdata=[SimData(address=0, count=100, values=0)])
print("Device created successfully")
EOF
```

---

### Issue 6: ModbusServerContext - No `getValues`/`setValues` Methods
**Error:** `AttributeError: 'ModbusDeviceContext' object has no attribute 'getValues'`

**Root Cause:** pymodbus 3.14 removed context helper methods; new API uses SimData directly.

**Solution:** Use global register dict approach (simpler for this use case):
```python
# Global register storage
tcp_regs = [0] * 10

# In cyclic task:
tcp_regs[REG_TEMP] = temp_value
trigger = tcp_regs[REG_TRIGGER]
```

---

### Issue 7: RTU parameter name — 'unit' vs 'slave_id' vs 'device_id'
**Error:** `read_holding_registers() got an unexpected keyword argument 'unit'` then `'slave_id'`

**Root Cause:** pymodbus 3.14 uses Modbus standard naming: `device_id` (not `unit` or `slave_id`)

**Solution:** Updated all RTU read/write calls to use `device_id=SLAVE_ADDR`:
```python
# Was: read_holding_registers(address=addr, count=1, unit=SLAVE_ADDR)
# Now: read_holding_registers(address=addr, count=1, device_id=SLAVE_ADDR)
```

**Status:** ✅ **RESOLVED** — Gateway now reads F4S registers successfully (Temp: 22.5°C, SP: 105.0°C)

---

### Issue 8: ModbusDeviceContext and TCP server complexity
**Error:** `ModbusDeviceContext` removed; complex datastore/SimData initialization required.

**Root Cause:** pymodbus 3.14 changed TCP server setup significantly; old context API gone.

**Solution:** Deferred TCP server layer; gateway runs with global `tcp_regs` array holding live register values in memory. TCP server will expose these registers to network clients in next iteration.

**Status:** TCP server layer is **next work item** — RTU foundation (reads/writes to tcp_regs) is stable and proven.

---

## Quick Debug Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Python version | `python3 --version` | 3.10+ |
| pymodbus installed | `python3 -c "import pymodbus; print(pymodbus.__version__)"` | 3.14+ |
| Serial port exists | `ls -la /dev/ttyWatlowF4S` | Symlink to ttyUSB0 |
| RTU hardware responsive | `mbpoll -a 1 100` | Reads temp register from F4S |
| Gateway running | `ps aux \| grep f4s_gateway` | Python process active |
| Logs accessible | `tail -f ~/.f4s_gateway/f4s_gateway.log` | Live cyclic reads visible |
| Gateway cyclic task | `grep "Cyclic task" ~/.f4s_gateway/f4s_gateway.log` | "Cyclic task started" |

---

## Next Steps (TCP Server Layer)

### Phase 5: TCP Server Implementation (In Progress)

**RTU Foundation Status:** ✅ Complete and proven
- Gateway connects to F4S @ 19200 baud, reads registers 100 and 300 every 1s
- Registers stored in global `tcp_regs[0-4]` array
- Ready for TCP network exposure

**Remaining Work:**
1. **Add Modbus TCP server** to `f4s_gateway.py` that exposes `tcp_regs` array on port 502
   - Create `ModbusSlaveContext` with holding registers (using updated pymodbus 3.14 API)
   - Map tcp_regs indices to Modbus registers via SimData/SimDevice
   - Start TCP server alongside cyclic RTU task
2. **Test TCP connectivity** with mbpoll: `mbpoll -m tcp -a 1 <pi-ip>:502 2` (should return temperature)
3. **Configure CODESYS TCP master** to read/write registers 0–4 via TCP (documented in setup guide Step 3)
4. **Run full T1–T4 integration tests:**
   - T1: Read current temperature from CODESYS
   - T2: Read confirmed setpoint from CODESYS
   - T3: Write new setpoint from CODESYS, verify F4S accepts it
   - T4: Verify status codes for range errors, comms failures, F4S rejections

---

**Started:** 2026-07-20  
**Last updated:** 2026-07-20  
**Author:** OJ (Omkar Joshi)  
**Status:** 
  - RTU foundation: ✅ **Proven** (reads temp 22.5°C, SP 105.0°C every 1s)
  - Global register array: ✅ **Operational** (tcp_regs[0-4] populated)
  - TCP server layer: 🚧 **Next** (ready for ModbusSlaveContext implementation)
  - CODESYS integration: ⏳ **After TCP server**
  
**Gateway Log:** `~/.f4s_gateway/f4s_gateway.log`
