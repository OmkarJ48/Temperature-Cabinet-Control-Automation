# Python Gateway Integration Setup Guide

**Purpose:** Complete setup instructions for deploying the Modbus TCP ↔ RTU gateway and integrating CODESYS with the Watlow F4S temperature cabinet via Python.

**Target:** Raspberry Pi (10.1.6.17) running CODESYS Control for Raspberry Pi

---

## Architecture Diagram

```
╔══════════════════════════╗         Network (TCP)         ╔═════════════════════════════════╗
║  CODESYS Project         ║                               ║  Raspberry Pi 10.1.6.17         ║
║  (sandbox environment)   ║◄─────────────502/TCP────────►║  f4s_gateway.py                 ║
║                          ║                               ║  (Modbus TCP Slave)             ║
║  Modbus TCP Master       ║                               ║  +                              ║
║  - Read temp             ║                               ║  Modbus RTU Master              ║
║  - Read confirmed SP     ║                               ║  (Serial master)                ║
║  - Write new SP          ║                               ║                                 ║
║  - Trigger apply         ║                               ║  ├─ Reg 0: Requested setpoint   ║
║                          ║                               ║  ├─ Reg 1: Apply trigger        ║
║  GVL_Modbus             ║                               ║  ├─ Reg 2: Current temp         ║
║  - wReadTempValue       ║                               ║  ├─ Reg 3: Current SP (read)    ║
║  - wSetpoint1Write      ║                               ║  ├─ Reg 4: Status               ║
║  - wSetpoint1Read       ║                               ║  └─ RS-232 ──────┐              ║
║  - xWriteTrigger        ║                               ║                  │              ║
║  - xModbusDone          ║                               ║                  │              ║
║  - xModbusError         ║                               ║                  ▼              ║
╚══════════════════════════╝                               ║  ┌─────────────────────────┐   ║
                                                           ║  │ Watlow F4S              │   ║
                                                           ║  │ RS-232 Slave            │   ║
                                                           ║  │ Slave addr: 1           │   ║
                                                           ║  │ Baud: 19200, 8N1       │   ║
                                                           ║  │ Reg 100: Temperature    │   ║
                                                           ║  │ Reg 300: Setpoint       │   ║
                                                           ║  └─────────────────────────┘   ║
                                                           ╚═════════════════════════════════╝
```

---

## Step 1: Deploy the Python Gateway on Raspberry Pi

### 1.1 Install Python dependencies

```bash
sudo apt-get update
sudo apt-get install python3 python3-pip
pip3 install pymodbus asyncio
```

### 1.2 Copy gateway file

Copy `f4s_gateway.py` to `/opt/f4s_gateway/`:

```bash
sudo mkdir -p /opt/f4s_gateway
sudo cp python-gateway/f4s_gateway.py /opt/f4s_gateway/
sudo chmod +x /opt/f4s_gateway/f4s_gateway.py
```

### 1.3 Create systemd service unit

Create `/etc/systemd/system/f4s-gateway.service`:

```ini
[Unit]
Description=Watlow F4S Modbus TCP↔RTU Gateway
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /opt/f4s_gateway/f4s_gateway.py
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable f4s-gateway.service
sudo systemctl start f4s-gateway.service
```

Verify status:

```bash
sudo systemctl status f4s-gateway.service
sudo journalctl -u f4s-gateway.service -f
```

---

## Step 2: Standalone Gateway Verification (Before CODESYS)

### 2.1 Test with mbpoll (TCP mode)

Install `mbpoll` on Raspberry Pi:

```bash
sudo apt-get install mbpoll
```

On the Raspberry Pi (or from a remote machine on the network):

**Read current temperature (reg 2):**
```bash
mbpoll -m tcp -a 1 -c 1 -t 3 10.1.6.17:502 2
```

**Read current setpoint (reg 3):**
```bash
mbpoll -m tcp -a 1 -c 1 -t 3 10.1.6.17:502 3
```

**Write requested setpoint (reg 0) — example: 26.5°C = 265 x10:**
```bash
mbpoll -m tcp -a 1 -t 3 10.1.6.17:502 0 265
```

**Trigger apply (reg 1):**
```bash
mbpoll -m tcp -a 1 -t 3 10.1.6.17:502 1 1
```

**Check status (reg 4):**
```bash
mbpoll -m tcp -a 1 -c 1 -t 3 10.1.6.17:502 4
```

**Expected behavior:**
- Reg 2 shows live temperature from F4S
- Reg 3 shows live setpoint from F4S
- Writing to reg 0 and triggering reg 1 causes the gateway to write to F4S
- Reg 4 returns 0 (STATUS_OK) on success, or a fault code on failure

---

## Step 3: Configure CODESYS (TCP Master)

### 3.1 Add Modbus TCP Master device

In CODESYS IDE (on the sandbox project):

1. **Devices → Add Device**
2. **Select "Modbus_Master" (or "Modbus TCP Master")**
3. **Configuration:**
   - **Network adapter:** Your network (Ethernet that can reach 10.1.6.17)
   - **IP address:** `10.1.6.17`
   - **Port:** `502`
   - **Slave ID:** `1`
   - **Cycle time:** e.g., `100 ms` (cyclic read interval)

### 3.2 Configure TCP channels

Create 5 channels (one per register):

| Channel | Name | FC | Address | Length | Type | R/W |
|---------|------|----|---------| -------|------|-----|
| 1 | ReadTemp | 03 | 2 | 1 | WORD | Read |
| 2 | ReadSetpoint | 03 | 3 | 1 | WORD | Read |
| 3 | WriteSetpoint | 06 | 0 | 1 | WORD | Write |
| 4 | WriteTrigger | 06 | 1 | 1 | WORD | Write |
| 5 | ReadStatus | 03 | 4 | 1 | WORD | Read |

### 3.3 Map channels to GVL_Modbus

**I/O Mapping:**
- Channel 1 (ReadTemp) → `GVL_Modbus.wReadTempValue`
- Channel 2 (ReadSetpoint) → `GVL_Modbus.wSetpoint1Read`
- Channel 3 (WriteSetpoint) → `GVL_Modbus.wSetpoint1Write`
- Channel 4 (WriteTrigger) → `GVL_Modbus.xWriteTrigger`
- Channel 5 (ReadStatus) → `GVL_Modbus.xModbusError` (reuse for status, or create new var)

---

## Step 4: Retarget PLC_PRG to TCP

### 4.1 Copy retargeted PLC_PRG

In sandbox CODESYS project, replace your `PLC_PRG` with `PLC_PRG_TCP_Retargeted.st`.

The retargeted version:
- Reads from TCP registers (via mapped channels)
- Same state machine as serial version (IDLE → READY → WRITING → CONFIRM → IDLE/FAULTED)
- Edge-triggered write (one pulse per user request)
- Range validation (0–200 °C)
- Status/fault code interpretation

### 4.2 Verify mappings

Ensure all GVL_Modbus variables are correctly I/O mapped in the device tree.

---

## Step 5: Test Plan (T1–T4)

### Test T1: Read Current Temperature

**Action:**
- Boot CODESYS runtime.
- Start the PLC program.
- Observe `GVL_Modbus.wReadTempValue` in the debug panel.

**Expected result:**
- `wReadTempValue` updates cyclically with the current F4S temperature (x10).
- E.g., if cabinet is at 25.0 °C, read 250.

**Troubleshooting:**
- If zero: Check IP/port/connectivity. Try `ping 10.1.6.17` and `mbpoll -m tcp` from the Pi.
- If stale: Check CODESYS device cycle time and Modbus TCP device "running" status.

---

### Test T2: Read Confirmed Setpoint

**Action:**
- In the HMI, note the current setpoint (should match F4S display).
- Observe `GVL_Modbus.wSetpoint1Read` in debug.

**Expected result:**
- `wSetpoint1Read` matches the F4S menu setpoint (x10).
- E.g., if F4S shows 30.0 °C, read 300.

**Troubleshooting:**
- Same as T1 — check connectivity and device status.

---

### Test T3: Write Requested Setpoint (Edge-Triggered)

**Action:**
1. In the HMI, enter a new setpoint (e.g., 28.0 °C = 280 x10).
2. Press "Apply".
3. Observe the F4S display and log file.

**Expected result:**
- PLC_PRG writes 280 to `GVL_Modbus.wSetpoint1Write` (mapped to TCP reg 0).
- PLC_PRG pulses `GVL_Modbus.xWriteTrigger` once (mapped to TCP reg 1).
- Gateway receives the pulse and writes 280 to F4S register 300.
- Gateway confirms the write (reads back within 0.5s).
- Gateway clears the trigger (reg 1 → 0).
- `wSetpoint1Read` eventually reflects the new value (within the next cycle).
- Gateway log shows: `Setpoint write: reg300 = 280` → `Setpoint write confirmed: reg300 = 280`.

**Troubleshooting:**
- If F4S doesn't update: Check the gateway log for WRITE_FAILED or NOT_ACCEPTED.
  - WRITE_FAILED = RTU error; check wiring, baud, slave address.
  - NOT_ACCEPTED = F4S rejected it (e.g., menu locked, out of range for F4S logic).
- If PLC never triggers: Check edge-triggered logic in PLC_PRG; ensure `xWriteTrigger` is a one-cycle pulse.

---

### Test T4: Status/Fault Reporting

**Action:**
1. Write an out-of-range setpoint (e.g., 250 °C = 2500 x10).
2. Press Apply.
3. Check the returned status code.

**Expected result:**
- Gateway rejects (status reg 4 = STATUS_RANGE_ERROR = 4).
- PLC_PRG transitions to FAULTED state, displays error on HMI.
- No write occurs to F4S.

**Repeat for:**
- Comms failure: Stop the gateway, trigger a write. Status should transition to STATUS_COMMS_ERROR (5) after ~5s of no RTU comms.
- F4S rejection (NOT_ACCEPTED): If the cabinet's menu locks the setpoint or refuses an update, gateway returns 3.

---

## Step 6: Commit and Push

Once tests T1–T4 pass:

```bash
git add -A
git commit -m "Add Python TCP gateway and CODESYS integration

- Deployed f4s_gateway.py (Modbus TCP slave + RTU master)
- Systemd service unit for auto-start
- Retargeted PLC_PRG for TCP (same state machine logic)
- Completed T1–T4 integration tests (temp, SP read, write, status)
- All tests passed. Ready for field trial.

Co-Authored-By: OJ (Omkar Joshi) <omkarjoshi2610@gmail.com>
"
git push origin Omkar_Temperature_Cabinet_Setpoint_Control
```

---

## Troubleshooting Quick Reference

| Problem | Check |
|---------|-------|
| Gateway doesn't start | `sudo systemctl status f4s-gateway.service` and `journalctl` |
| `mbpoll -m tcp` fails | Is the gateway running? `netstat -tlnp \| grep 502` |
| Reads are zero | IP/port correct? Test from Raspberry Pi first, then from CODESYS box |
| Reads are stale | CODESYS device "running"? Cycle time too long? Check device tree |
| Write doesn't trigger | Ensure `xWriteTrigger` is a 1-cycle pulse (not level-triggered) |
| Write fails (status=2) | Check RTU comms — `tail -f f4s_gateway.log` for RTU errors |
| Write rejected (status=3) | F4S menu may be locked. Check cabinet display and menu state |
| Out-of-range error (status=4) | Validate range 0–2000 (0–200 °C); gateway rejects outside this |
| Comms error (status=5) | No RTU reads in 5s. Check serial connection, F4S power, baud rate |

---

## Files in this branch

- `codesys-python-tcp-integration/README.md` — investigation summary and architecture
- `codesys-python-tcp-integration/python-gateway/f4s_gateway.py` — gateway code
- `codesys-python-tcp-integration/Python_Gateway_Integration_Setup_Guide.md` — this file
- `src/POUs/PLC_PRG_TCP_Retargeted.st` — retargeted CODESYS PLC program
- `src/GVLs/GVL_Modbus.gvl` — global variable list (I/O mapped)

---

**Author:** OJ (Omkar Joshi)
**Date:** [date of last update]
**Status:** Investigation in progress. Not for merge to `main`.
