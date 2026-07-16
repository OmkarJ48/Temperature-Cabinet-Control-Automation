# Deployment & Test Guide — Cabinet Setpoint Control (ST / CODESYS WebVisu)

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Applies to:** `src/` Structured Text POUs for the DLS008 sandbox project
**Target:** Watlow F4S (SN 038983), Modbus RTU / RS-232, via USB-to-RS232 on `/dev/ttyUSB0`

This is the hand-over companion to the README (the project bible). It tells the
next engineer exactly how to drop the ST code into the sandbox project, wire the
Modbus channels, and prove the four operator requirements.

---

## 1. What the code does (in-scope items 5–9)

| Requirement (Definition of Done) | Where it lives |
|---|---|
| Enter a new desired setpoint on the HMI | `GVL_HMI.rReqSetpoint` + gear pop-up |
| Send the new setpoint to the cabinet | `FB_CabinetSetpointControl` → FC06 write, reg 300, **edge-triggered** |
| Confirm the cabinet accepted it | `CONFIRM` state reads reg 300 back and compares → `xSetpointConfirmed` |
| Clear warning/fault on write-fail, comms-loss, not-accepted | `E_FaultCode` + `sStatusText` banner |

CODESYS stays **supervisory only** — the F4S runs its own PID loop. We write a
target and read state; we never close the thermal loop.

---

## 2. Import the ST into the sandbox project

Two ways to get this into the real `.project` — pick whichever suits how far
along the sandbox already is.

### Option A — PLCopen XML import (fastest, recommended)

`src/PLCopenXML/CabinetSetpointControl.xml` is a standard PLCopen TC6 XML
export containing both DUTs, both GVLs, `FB_CabinetSetpointControl`, and
`PLC_PRG` — ready to import directly into the existing sandbox `.project`:

1. Open the sandbox project in CODESYS.
2. **Project → Import PLCopen XML File...** → select `src/PLCopenXML/CabinetSetpointControl.xml`.
3. CODESYS creates the DUTs, GVLs, and POUs under **Application**. It will
   prompt if `PLC_PRG` already exists (it does, empty, in the sandbox) —
   choose **overwrite/merge** so the imported body replaces the empty stub.
4. Move the imported POUs into your preferred folder structure if desired —
   folder placement isn't part of the PLCopen interchange format, only the
   POUs/DUTs/GVLs themselves are.
5. Add the **Standard** library (for `R_TRIG` / `TON`) if not already referenced.
6. **Build** → expect 0 errors, 0 warnings.

A real CODESYS `.project` file is a proprietary binary/compiled format that
only the CODESYS IDE itself can write — it cannot be authored or validated
outside the IDE. This PLCopen XML is the legitimate, tool-supported bridge
from version-controlled text into that binary project.

### Option B — manual paste (if you prefer to see each POU as you create it)

The same code, split out per-POU as plain text so it diffs cleanly in Git:

1. **DUTs** → add two enumerations, paste bodies:
   - `E_SetpointState` ← `src/DUTs/E_SetpointState.dut`
   - `E_FaultCode` ← `src/DUTs/E_FaultCode.dut`
2. **GVLs** → add two global variable lists:
   - `GVL_Modbus` ← `src/GVLs/GVL_Modbus.gvl`
   - `GVL_HMI` ← `src/GVLs/GVL_HMI.gvl`
3. **POU (Function Block)** `FB_CabinetSetpointControl` ← `src/POUs/FB_CabinetSetpointControl.st`
4. **PLC_PRG** → replace the empty body with `src/POUs/PLC_PRG.st`
5. Ensure `PLC_PRG` is assigned to **MainTask** (already is in the sandbox).
6. Add the **Standard** library (for `R_TRIG` / `TON`) if not already referenced.
7. **Build** → expect 0 errors, 0 warnings.

---

## 3. Configure the Modbus Serial Master (device tree)

Under the Raspberry Pi CODESYS device → add **Modbus COM → Modbus_Master (RTU) →
Modbus_Slave**. Settings come straight off the F4 front panel (confirmed):

| Parameter | Value |
|---|---|
| Serial port | `/dev/ttyUSB0` |
| Baud rate | **19200** |
| Data / parity / stop | 8 / None / 1 (8N1) |
| Slave address | **1** |
| Transmission mode | RTU |

Create three channels and map them to `GVL_Modbus`:

| # | Access | FC | Register | Qty | Trigger | Map to |
|---|---|---|---|---|---|---|
| CH1 | Read | FC03 | 100 | 1 | cyclic ~1000 ms | `wInput1Value` |
| CH2 | Read | FC03 | 300 | 1 | cyclic ~1000 ms | `wSetpoint1Read` |
| CH3 | Write | FC06 | 300 | 1 | **rising edge** | `wSetpoint1Write`, trigger `xWriteTrigger` |

Map the master/slave diagnostic bits to `GVL_Modbus.xModbusError` (slave
`xError`) and `GVL_Modbus.xModbusDone` (last transaction done).

> CH3 must be **rising-edge**, never cyclic — not because reg 300 is
> EEPROM-backed (it isn't: the F4S/D spec sheet documents data retention via
> **battery-backed RAM**, not EEPROM — that caution belongs to a different
> Watlow product, the SD31). The real reason is simpler: write once per
> operator action, and the F4 only follows register 300 while it's in
> **static mode** (a running ramp/soak profile ignores writes to 300). The FB
> already gives you a one-shot trigger; do not also poll it.

---

## 4. WebVisu screen

- **Oliver Mechatronics logo** at the top of the screen.
- **Gear button** labelled *"Set the cabinet temperature setpoint"* → opens a
  pop-up dialog (`dlgSetpoint`) bound to `rReqSetpoint` (numeric entry, Min
  30.0 / Max 130.0), `xSetBtn` (SET), `xResetBtn` (RESET).
- **Chamber Temperature** tile ← `rChamberTemp` (live).
- **Confirmed setpoint** tile ← `rConfirmedSetpoint`.
- **Status banner** ← `sStatusText`; drive the background colour from
  `xFaultActive` (red on fault) and `xSetpointConfirmed` (green on accept).

---

## 5. Test plan — Rebuild → Retest → Requalify → Repeat

Run standalone first (ModRSsim / Modbus Poll on `/dev/ttyUSB0`) to prove the link,
then in CODESYS. Log every result with a timestamp.

| # | Test | Method | Pass criteria |
|---|---|---|---|
| T1 | Read-back accuracy | Compare `rChamberTemp` to F4 front panel | Match within 0.1 °C |
| T2 | Setpoint write | Set 30 °C on HMI, press SET | F4 SP1 shows 30.0 °C within 1–2 s (state: `IDLE`→`READY`→`WRITING`→`CONFIRM`→`IDLE`) |
| T3 | Acceptance confirm | Watch after T2 | `xSetpointConfirmed` = TRUE, banner "accepted" |
| T4 | Range validation | Set value below `rMinSetpoint` (30.0) or above `rMaxSetpoint` (130.0), press SET | No write; fault `RANGE_LOW` / `RANGE_HIGH`, banner red |
| T5 | Comms-loss fault | Unplug USB adapter | Within `tCommsTimeout` (3 s): fault `COMMS_TIMEOUT` |
| T6 | Write-fail / not-accepted | Wrong slave addr, or F4 in profile mode | Fault `WRITE_FAILED` or `NOT_ACCEPTED` |
| T7 | Over-temp | Trip the hard-wired lamp (spare EL1409 DI) | Fault `OVER_TEMP`, holds until cleared |
| T8 | Fault reset | Clear cause, press RESET | Returns to `IDLE`, no self-clear over live fault |
| T9 | Range sweep | Write 30 / 100 / 130 °C | Each confirmed; front panel tracks |

Mark a test PASS only after **two consecutive** clean runs; otherwise cycle back
through Rebuild/Retest/Requalify.

---

## 6. Open items carried from the README

- Confirm the F4S is in **static/manual setpoint mode** (not running a profile)
  before production reg-300 writes — a running profile owns SP1 and T6 will trip.
- Confirm which Raspberry Pi hosts the adapter (the USB device is tied to the
  physical Pi's OS, not the project).
- The "Hyperbaric Water Temperature" HMI tile likely belongs to a different rig —
  not a blocker for this deliverable.

---

## 7. Out of scope — standard integration outline (for later, not now)

Kept here so it exists when needed; **not** part of this deliverable:

1. Multi-cabinet support → move from RS-232 point-to-point to RS-485 multi-drop
   (F4S terminals 12/13/16), one slave address per cabinet.
2. Setpoint profiles / ramps authored from CODESYS → F4S profile registers
   (4000-range) instead of static reg 300.
3. Alarm history / trend logging and audit trail of setpoint changes.
4. Role-based access control on the setpoint pop-up.
5. Redundant comms / automatic Pi failover.

Each would follow the same Rebuild → Retest → Requalify → Repeat loop.
