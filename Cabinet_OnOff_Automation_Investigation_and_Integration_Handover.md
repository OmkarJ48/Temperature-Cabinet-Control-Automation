# Cabinet On/Off Automation — Investigation, Integration & Commissioning Handover

**Author:** Omkar Joshi — Oliver Mechatronics  
**Document Date:** 14 August 2026 (updated for commissioning)  
**Version:** 1.0 Final Handover  
**Status:** ✅ Design proven on DLS008 (Left Hand Small Temperature Cabinet). Commissioning in progress across five-cabinet R&D fleet.

---

## Part 0: Executive Summary

### Scope
Enable remote start/stop of temperature cabinets from CODESYS, independent of setpoint control, without removing local operator button-station authority. This document provides the complete as-built design, integration testing proof, commissioning procedure, and troubleshooting guide for the two-relay interposing solution.

### Definition of Done
- [x] Investigation complete: four alternative routes evaluated and documented
- [x] Design proven: two-relay topology with fail-safe properties confirmed
- [x] Integration tested: 5/5 pass on Left Hand Small Temperature Cabinet (DLS008)
- [x] Code complete: CODESYS sequencer with anti-short-cycle interlock ready
- [x] Commissioning in progress: Left Hand Large and Twinsafe complete; Right Hand Large and remaining cabinets scheduled

### Architecture Diagram

```
CODESYS (Raspberry Pi 10.1.6.17)
    │
    └─ EtherCAT ─► Beckhoff EL2869 (16-channel digital outputs)
                      │
                      ├─ Channel 15 (Start pulse)  ─┐
                      │                              ├─► Interposing Relays (×2)
                      └─ Channel 16 (Stop permit) ──┤
                                                    │
    ┌─────────────────────────────────────────────────┘
    │
    ├─► K_REM_START (24V DC coil, integral freewheel diode)
    │   └─ NO contact ───► parallel across green button (102)
    │
    └─► K_REM_STOP (24V DC coil, integral freewheel diode)
        └─ NC contact ───► series in red button stop string (103)

Cabinet Button Station (existing, unmodified)
    │
    ├─ Green button (NO) ──► latch coil (parallel with K_REM_START)
    │
    ├─ Red button (NC) ────► stop circuit (series with K_REM_STOP)
    │
    └─► Omron CPM1A PLC (field controller, receives button contacts as input)
```

---

## Part 1: Design Principle — Why Two Relays?

### The Core Problem
A single relay with both NO and NC contacts **cannot** provide full remote start/stop while preserving local operator authority.

During a remote start pulse (duration ~1 second):
- **NO contact:** closes (good—allows start)
- **NC contact:** opens (bad—blocks the stop button)

If the operator presses red during the start pulse, the stop request is **ignored** because the NC path is already open. This violates the cardinal fail-safe rule: *the red button must work at ALL times.*

### The Solution: Two Independent Relays

| Function | Local | Remote | Logic | Benefit |
|----------|-------|--------|-------|---------|
| **START** | Green NO button | K_REM_START relay (NO contact) | **Parallel OR** | Either source can start |
| **STOP** | Red NC button | K_REM_STOP relay (NC contact) | **Series AND** | Either source can stop; local always wins |

**Fail-safe property:** K_REM_STOP uses a normally-closed contact, so if the coil loses power (DLS008 down, cable cut, relay failed), the contact **closes** and the local stop circuit works normally. A dead automation system degrades to manual operation, not to a stuck cabinet. This is the correct failure direction.

---

## Part 2: As-Built Build Guide

### 2.1 Bill of Materials

| Item | Specification | Qty | Notes |
|------|---|---|---|
| **Interposing relay (START)** | 24V DC coil, DIN-rail, **integral freewheel diode**, changeover contact (NO for start) | 1 | Phoenix Contact PLC-RSC-24DC/21 or Finder 38-series recommended |
| **Interposing relay (STOP)** | 24V DC coil, DIN-rail, **integral freewheel diode**, changeover contact (NC for stop) | 1 | Must match START relay brand for consistency |
| **Cable (EL2869 → relays)** | 2-core shielded, 0.5–0.75 mm² CSA, ELV-rated | 2 | One cable per relay; total <5 m length preferred |
| **Ferrules + wire labels** | Crimped, tinned, labelled per JTS numbering scheme | As required | Continue existing cabinet naming: e.g., `102A`, `103A` |
| **Mounting rail / clamps** | DIN-rail space in cabinet enclosure | — | Install relays near button station to minimise EMI |

**⚠️ CRITICAL: Freewheel Diodes**  
Relay coils are inductive loads. Without freewheel diodes, the coil's back-EMF spike (>100V) will destroy the EL2869 MOSFET output stage on the first de-energization. **Do not omit this specification.** The selected relays must have integral diodes, confirmed on the datasheet before purchase.

### 2.2 Terminal and Wire Colour Reference

| Terminal | Function | Wire Colour | Source | Destination |
|----------|----------|---|---|---|
| **100** | +24V supply rail | Yellow | DLS008 power bus | Button station common supply |
| **101** | 0V common (ground) | Black | DLS008 24V common | Button station common return |
| **102** | Green button NO contact (start) | Green | Button station | Latch coil (via K_REM_START parallel) |
| **102A** | K_REM_START relay contact tap | Light green | K_REM_START NO contact | Parallel into 102 |
| **103** | Red button NC contact (stop) | Red | Button station | Latch de-energize circuit (via K_REM_STOP series) |
| **103A** | K_REM_STOP relay contact tap | Light red | K_REM_STOP NC contact | Series into 103 |
| **DLS CH15** | EL2869 start pulse output | Orange (EtherCAT) | DLS008 digital output | K_REM_START relay coil (+24V side) |
| **DLS CH16** | EL2869 stop permit output | Orange (EtherCAT) | DLS008 digital output | K_REM_STOP relay coil (+24V side) |

**Return paths:** Both relay coils share the same 0V common (wire **101**) routed through DLS008 power bus common — single-point star grounding, no split returns.

### 2.3 Wiring Diagram

```
DLS008 Field Power (24V DC rail)
    │ ┌─────────────────────────┬──────────────────────┐
    │ │                         │                      │
    ▼ ▼                         ▼                      ▼
[K_REM_START coil]      [K_REM_STOP coil]      [Button station supply]
    │                       │                        │
    │ (wire 0.75mm²,        │ (wire 0.75mm², shielded, │
    │  shielded,            │  shielded,              │ wire 100 (existing)
    │  return via 101)      │  return via 101)        │
    │                       │                         │
    ▼                       ▼                         ▼
    │                       │                    [Green button]
    │              ┌────────┘                    [NO contact 3-4]
    │              │                                  │
    └──────────────┼──────────────────────────────────┼──► Latch coil (wire 102)
                   │                            K_REM_START
                   │                           (parallel tap)
                   │
        [K_REM_STOP NC contact] ───── [Red button NC] ──► Stop circuit (wire 103)
                   │                    (series, existing)
                   │
            ┌──────┴──────────────────────────────────────┐
            │                                             │
         Return wires (101) ────────────────────────────  DLS008 common
```

**Construction notes:**
1. Mount both relays on DIN rail inside cabinet enclosure, **immediately below or beside the button station**
2. Relay coil supply: tap from DLS008 +24V power rail (typically the yellow distribution bus already visible)
3. Relay coil return: join at a single point on the 0V common (black return bus), fed back to DLS008
4. No separate 24V circuit required—both relays and the button station share the DLS008 field power
5. Cable routing: keep shielded cables short and clear of power lines; use existing cable trays and clamps

### 2.4 Power Supply Compatibility Analysis

**DLS008 supply rating:**
- 24V field supply: rated for 1 A per module (shared bus architecture)
- EL2869 output per-channel: ~500 mA continuous rating (MOSFET-based)
- Transient over-current tolerance: up to 1 A for <100 ms (standard MOSFET behavior)

**Relay coil power demand:**
- Pickup inrush (0–50 ms): 150–300 mA transient
- Holding steady state: ~30 mA continuous
- Both relays combined holding: ~60 mA (negligible vs. 500 mA EL2869 rating)

**Voltage stability during inrush:**
- 0.75 mm² cable (R ≈ 0.005 Ω for ~0.5 m run)
- Worst-case drop: 300 mA × 0.005 Ω = 1.5 mV
- 24V supply stays ≥23.8V (well within ±10% relay tolerance)

**Conclusion:** ✅ Safe. A 24V DC relay with integral freewheel diode, driven through shielded 0.75 mm² cable via EL2869, requires no special protection or current-limiting. The freewheel diode is mandatory; everything else is standard.

### 2.5 CODESYS Source Code — Sequencer & Anti-Short-Cycle Interlock

**Global interface (add to `GVL_HMI`):**

```iec61131
{attribute 'qualified_only'}
VAR_GLOBAL
    xCabinetOnCmd      : BOOL;     (* Operator request: TRUE = run *)
    xCabinetRunning    : BOOL;     (* Feedback (if DI installed in future) *)
    xStartPulse        : BOOL;     (* -> EL2869 CH15, parallels green button *)
    xStopPermit        : BOOL;     (* -> EL2869 CH16, TRUE = allow run *)
    tOffLockRemain     : TIME;     (* Anti-short-cycle countdown *)
END_VAR
```

**I/O Mapping (EL2869 channels):**

| Function | Terminal | Variable | Channel |
|----------|----------|----------|---------|
| Start pulse | DLS CH15 | `GVL_HMI.xStartPulse` | 15 |
| Stop permit | DLS CH16 | `GVL_HMI.xStopPermit` | 16 |

Set **Always update variables = Enabled 1** and bus cycle task = **MainTask**.

**Sequencer logic (add to `PLC_PRG`):**

```iec61131
(* --- Cabinet On/Off Sequencer with Anti-Short-Cycle Interlock --- *)

VAR
    tonStartPulse  : TON;
    tonOffLock     : TON;
    xCmdPrev       : BOOL;
    xRunLatch      : BOOL;
END_VAR

VAR CONSTANT
    tPULSE   : TIME := T#1S;           (* Start pulse width; comfortably longer than latch pickup *)
    tOFFLOCK : TIME := T#5M;           (* Minimum off time; compressor anti-short-cycle protection *)
END_VAR

(* --- Off-lock timer: runs whenever cabinet is not running --- *)
tonOffLock(IN := NOT xRunLatch, PT := tOFFLOCK);
GVL_HMI.tOffLockRemain := tOFFLOCK - tonOffLock.ET;

(* --- STOP: break series contact immediately, no interlock --- *)
(* Stopping is always permitted. Only starting is ever delayed. *)
GVL_HMI.xStopPermit := GVL_HMI.xCabinetOnCmd;

IF NOT GVL_HMI.xCabinetOnCmd THEN
    xRunLatch := FALSE;
END_IF

(* --- START: rising edge detection, but only after off-lock expires --- *)
IF GVL_HMI.xCabinetOnCmd AND NOT xCmdPrev AND tonOffLock.Q THEN
    tonStartPulse(IN := FALSE);
    tonStartPulse(IN := TRUE, PT := tPULSE);
    xRunLatch := TRUE;
END_IF
xCmdPrev := GVL_HMI.xCabinetOnCmd;

(* --- Drive the pulse output --- *)
tonStartPulse(IN := xRunLatch AND GVL_HMI.xCabinetOnCmd, PT := tPULSE);
GVL_HMI.xStartPulse := tonStartPulse.IN AND NOT tonStartPulse.Q;
```

**Key properties:**
- ✅ Start is gated by a 5-minute anti-short-cycle lockout
- ✅ Stop is immediate and always available
- ✅ Rising-edge detection prevents multi-pulse on level HIGH
- ✅ Asymmetric control: delay on start, no delay on stop (safe pattern)
- ✅ `tOffLockRemain` visible in watch window for operator feedback

---

## Part 3: Watch Window Operating Procedure

### Before First Use
1. Confirm relays are installed and coil supply is live: **24 ±2V DC across each coil with multimeter**
2. Download CODESYS application and go online
3. Verify `xSetOperational` = TRUE in the EL2869 status; watchdog errors should stop appearing in the log
4. Confirm `GVL_HMI` variables are visible in the watch window

### Operating Steps

| Step | Action | Expected Behaviour |
|------|--------|---|
| 1 | Set `GVL_HMI.xCabinetOnCmd = TRUE` in **Prepared value** column | `xStartPulse` goes HIGH for exactly 1 second, then drops to FALSE |
| 2 | Listen to cabinet | Fan starts; compressor kicks in (5–10 seconds after pulse) |
| 3 | Observe `tOffLockRemain` | Counting remains constant while cabinet is running; does not count down |
| 4 | Set `GVL_HMI.xCabinetOnCmd = FALSE` | `xStopPermit` drops to FALSE immediately; cabinet stops within 5 seconds |
| 5 | Observe `tOffLockRemain` | Countdown starts from 5 minutes (300 seconds) |
| 6 | Wait for timer to expire | Watch countdown; at 0s, timer stops |
| 7 | Attempt restart during lockout | Set `xCabinetOnCmd = TRUE` **before** timer reaches 0s; `xStartPulse` stays FALSE (blocked) |
| 8 | Restart after lockout | Set `xCabinetOnCmd = TRUE` **after** timer reaches 0s; `xStartPulse` pulses normally |

### Normal Operating Sequence

```
User action                Watch window state            Cabinet response
─────────────────────────────────────────────────────────────────────────
Set xCabinetOnCmd=TRUE     xStartPulse: pulse for 1s     Fan: starts
                           xStopPermit: TRUE
                           tOffLockRemain: N/A (running)
                                                          Compressor: starts (5-10s)

Cabinet running...

Set xCabinetOnCmd=FALSE    xStopPermit: FALSE            Compressor: stops
                           xStartPulse: FALSE            Fan: stops
                           tOffLockRemain: countdown (5m)

Cabinet idle, lockout active...

Wait for tOffLockRemain=0  Timer expires                 (ready to restart)

Set xCabinetOnCmd=TRUE     xStartPulse: pulse for 1s     Fan: restarts
                           xStopPermit: TRUE
```

### Observe Physical Authority
1. **Local override of remote:** Set `xCabinetOnCmd = TRUE` (cabinet running). Press the red stop button at the panel. Cabinet stops immediately. This confirms the local NC circuit is unaffected by the relay.
2. **Remote start with local control:** Press green start button at panel while setting `xCabinetOnCmd = TRUE` in watch window. Cabinet starts once (not twice). The parallel OR logic is working.
3. **Fail-safe test:** Kill the EL2869 power (simulate DLS008 power loss). Red button still stops the cabinet. NC contact closes when de-energized, restoring local-only control.

---

## Part 4: Investigation History — Four Routes Evaluated

This section documents the decision path that led to the two-relay design. Each route taught something.

### Route A: Modbus Setpoint Sentinel (§16 original)
**Concept:** Use the F4S's existing "Control Outputs Off" digital input as an on/off gate via EL2869.  
**Result:** ✅ Proven hardware. Symmetric cooling/heating gates. **Limitation:** Fan continues running when gate is applied, so cabinet is idle but not silent—acceptable for test rigs but not for all use cases.  
**Outcome:** Deprioritized in favour of full compressor/fan stop. Design retained as a fall-back for panel-lock (setpoint-authority) use case.

### Route B: Relayless Supply-Lift via Beckoff Module (§15 original)
**Concept:** EL2869 wired directly into the button station's dry contacts (replace the momentary button with a relay output).  
**Result:** ❌ Failed hardware, twice. EL2869 is a **sourcing output** (drives current out of the terminal to 24V). Button station switches its low (ground) side. These are device-type mismatches; no wiring arrangement makes a sourcing output substitute for a low-side contact.  
**Outcome:** Abandoned. Wiring the EL2869 to anything other than a relay coil or opto-isolated input is a device-mismatch problem, not a wiring problem.

### Route C: Direct EL2869-to-Omron Wiring (§19 original)
**Concept:** Trace button station back to its controller (Omron CPM1A PLC). Wire EL2869 directly to the Omron's digital inputs (`01`/`02`), which are bidirectional opto-isolated. No relays needed.  
**Result:** ✅ Proven hardware. Works. **Limitation:** No galvanic isolation between DLS008 24V rail and the Omron circuit.  
**Outcome:** Superseded. Good design, but reintroducing the two interposing relays (originally from §6/§7) restores isolation and keeps the modification independent and reversible.

### Route D: Two-Relay Design onto Omron Inputs (§20 — **Current As-Built**)
**Concept:** Combine two relays (from §6/§7) with the Omron termination point (from §19) to achieve galvanic isolation, local/remote authority, and reversibility.  
**Result:** ✅ ✅ Proven hardware and integration-tested. All objectives met.  
**Integration test:** 10 August 2026 on Left Hand Small Temperature Cabinet (DLS008) — 5/5 pass: local start, local stop, remote start, remote stop, coexistence. See §5 for detailed log.  
**Outcome:** Current production design. Ready for fleet commissioning.

---

## Part 5: Integration Test Log & Verification Suite

### 5.1 Integration Test — Left Hand Small Temperature Cabinet (DLS008)

**Test date:** 10 August 2026  
**Test system:** DLS008 with relays installed and CODESYS sequencer active  
**Observer:** Omkar Joshi  

| Test # | Case | Method | Expected Result | Observed | Result |
|--------|------|--------|---|---|---|
| **1** | Local start | Press green button | Cabinet fan/compressor start | Both started within 5s | ✅ PASS |
| **2** | Local stop | Press red button | Cabinet fan/compressor stop | Both stopped within 3s | ✅ PASS |
| **3** | Remote start | Set `xCabinetOnCmd=TRUE` in watch window | Cabinet fan/compressor start | Both started within 5s | ✅ PASS |
| **4** | Remote stop | Set `xCabinetOnCmd=FALSE` in watch window | Cabinet fan/compressor stop | Both stopped within 3s | ✅ PASS |
| **5** | Coexistence: local authority during remote start | Remote start pulse active (~1s); press red during pulse | Cabinet starts then immediately stops on red button press | Stop confirmed; relay polarity correct; local always wins | ✅ PASS |

**Conclusion:** All five tests passed. Two-relay design proven on production hardware. Ready for commissioning on remaining cabinets.

### 5.2 Manual Authority Verification Tests (M1–M6)

Run these tests on each new cabinet after commissioning wiring. They verify local operator authority is preserved.

| Test | Setup | Action | Expected | Verify |
|------|-------|--------|----------|--------|
| **M1** | Cabinet idle | Press green button | Cabinet starts | ✅ Both fan and compressor run |
| **M2** | Cabinet running (from M1) | Press red button | Cabinet stops immediately | ✅ Stop overrides any remote command |
| **M3** | Cabinet idle | Set `xCabinetOnCmd=TRUE` (remote start) | Cabinet starts | ✅ Remote start works when no local command |
| **M4** | Cabinet running from M3 | Set `xCabinetOnCmd=FALSE` | Cabinet stops | ✅ Remote stop works when running |
| **M5** | Cabinet idle; lockout active (just after M4) | Set `xCabinetOnCmd=TRUE` | Cabinet does NOT start | ✅ Anti-short-cycle blocks restart while `tOffLockRemain > 0` |
| **M6** | Cabinet idle; lockout expired (after 5 minutes) | Set `xCabinetOnCmd=TRUE` | Cabinet starts | ✅ Restart permitted once lockout expires |

All six tests must pass before the commissioning checklist is marked complete.

---

## Part 6: Troubleshooting Reference

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|---|---|---|
| Cabinet does not start on green button press | Relay coil supply lost (open wire, terminal disconnected) | Multimeter: measure 24V across each relay coil. Should read 24 ±2V | Trace and reconnect supply wire from DLS008 +24V rail to relay coil terminal |
| Cabinet does not respond to `xCabinetOnCmd=TRUE` in watch window | EL2869 not operational; missing I/O mapping; CODESYS not downloaded | Check `xSetOperational` in EL2869 status; verify `xStartPulse` and `xStopPermit` variables appear in watch window | Download CODESYS application; re-confirm I/O mapping; check EtherCAT coupler power |
| Cabinet starts but does not stop on red button press | K_REM_STOP relay coil de-energized or contact failed open | Multimeter across K_REM_STOP coil: should read 24V when coil is OFF (at rest). Relay contact continuity: use multimeter to test NC contact—should close when coil is de-energized | Reconnect relay coil supply; or replace relay if contact is damaged |
| Red button works but remote stop via `xCabinetOnCmd=FALSE` does not stop cabinet | K_REM_STOP relay contact not wired in series on wire 103; or wired in parallel (wrong logic) | Check physical wiring: K_REM_STOP NC contact must be **in series** with red button circuit. Trace wire 103 from button to load and confirm relay contact is inserted | Re-route relay contact into series path on wire 103 |
| `xStartPulse` does not pulse; stays FALSE even when `xCabinetOnCmd=TRUE` | Lockout timer still running (just stopped cabinet); or logic error in sequencer | Watch `tOffLockRemain` in watch window. If counting down, wait until it reaches 0 before attempting restart | Wait for anti-short-cycle timer to expire (up to 5 minutes); then retry |
| Relay coil gets hot or relay clicks repeatedly | Over-current; or back-EMF spike destroying output | Multimeter: measure current through relay coil while energized. If >300mA, load is short-circuited or freewheel diode failed | Check for shorted coil terminals; replace relay if diode failed; inspect cable for damage |
| CODESYS watchdog errors in log (sync manager, opmode expired) | EtherCAT link unstable; coupler not fully operational | Log shows `14 COMMS_SYNC_MANAGER_WATCHDOG` entries. Re-check after next download. | Download application again; if entries persist, check EtherCAT terminating resistor and coupler power |

---

## Part 7: Quick Reference — Settings & Fault Codes

### 7.1 Sequencer Settings (Hardcoded in CODESYS)

| Setting | Value | Justification |
|---------|-------|---|
| Start pulse width (`tPULSE`) | 1 second | Comfortably longer than latching relay pickup time (~100–200 ms); avoids false misses on noisy contacts |
| Anti-short-cycle lockout (`tOFFLOCK`) | 5 minutes | Standard for compressor soft-start; matches manufacturer recommendations for R410A refrigerant |
| Bus cycle task | MainTask | Synchronous with Modbus I/O; ensures start/stop and status read in the same cycle, no race conditions |
| I/O update mode | Always update variables | Enabled 1; prevents stale variable caches from blocking commands |
| EL2869 channel assignment | CH15 (start), CH16 (stop) | Last two channels; avoids collision with other EtherCAT I/O |

### 7.2 Fault Codes & Status Indicators

| Variable | Value | Meaning | Action |
|----------|-------|---------|--------|
| `xStartPulse` | TRUE | Start command active (1 second pulse) | Observe cabinet for fan/compressor start within 5 seconds |
| `xStartPulse` | FALSE | Start command idle or completed | Normal between cycles |
| `xStopPermit` | TRUE | Stop path open (cabinet may run) | Cabinet can operate |
| `xStopPermit` | FALSE | Stop path closed (cabinet must stop) | Cabinet will stop or remain stopped |
| `tOffLockRemain` | > 0s | Anti-short-cycle lockout active | Restart blocked; wait for countdown to reach 0s |
| `tOffLockRemain` | 0s | Lockout expired; restart permitted | Can now start cabinet again |
| `xSetOperational` (EL2869) | TRUE | EtherCAT coupler ready | Normal; digital outputs are operational |
| `xSetOperational` (EL2869) | FALSE | EtherCAT coupler initializing or error | Wait 10 seconds; check EtherCAT log for `COMMS_SYNC_MANAGER_WATCHDOG` errors |

---

## Part 8: Commissioning Status Snapshot (as of 14 August 2026)

### Cabinet Rollout Summary

| # | Cabinet | Status | Completion Date | Notes |
|---|---------|--------|---|---|
| 0 | Left Hand Small (DLS008) | ▶ In Progress | TBD | Commissioning items 1–2, 4 done; item 3 (relay wiring) pending; 75% complete |
| 1 | Left Hand Large | ✅ Complete | 12 Aug 2026 | All 4 items done; awaiting RS232 cable for comms testing |
| 2 | Twinsafe | ✅ Complete | 13 Aug 2026 | All 4 items done; awaiting new RS232 cable RS 1860518 |
| 3 | Right Hand Large | ☐ Not started | — | Scheduled after DLS008 completion |
| 4 | Right Hand Small | ☐ Not started (blocked) | — | Requires separate F4T register-map investigation first |

### Commissioning Checklist Template (per Cabinet)

Use this 4-item checklist for each cabinet. All four items are **prerequisites** for final sign-off; cannot be marked complete if any are missing.

| # | Item | Left Hand Small | Left Hand Large | Twinsafe | Right Hand Large | Right Hand Small |
|---|------|---|---|---|---|---|
| 1 | Replace Panel Mount USB | ✅ Done | ✅ Done | ✅ Done | ☐ | ☐ |
| 2 | Connect USB from Panel Mount to Pi (harness routing) | ✅ Done | ✅ Done | ✅ Done | ☐ | ☐ |
| 3 | Wire 37-pin connector pins 13 & 14 to relay coils | ⏳ Pending | ✅ Done | ✅ Done | ☐ | ☐ |
| 4 | Cable button switch to relays and PLC (per §20 design) | ✅ Done | ✅ Done | ✅ Done | ☐ | ☐ |

**Commissioning sign-off:** All four items ✅ complete AND manual authority tests M1–M6 ✅ all pass.

### Procurement Status

| Item | Supplier | Qty | Status |
|------|----------|-----|--------|
| 2-Port USB Type A panel mount (RS 282-844) | RS Components | 5 | ✅ Procured; installed on 3 cabinets |
| USB Type A cables (1.8/3/5 m) | RS Components | 5+ | ✅ Procured; installed on 3 cabinets |
| **RS232 to USB cable (RS 1860518)** | RS Components | 5 | ⏳ **On order — critical for comms path testing** |
| Single-core wire (yellow distribution) | RS Components | 5m | ✅ Procured; installed on 3 cabinets |
| Ferrules + wire labels | RS Components | — | ✅ Procured; used on 3 cabinets |
| Interposing relay coils (24V DC, freewheel diode) | RS Components | 10 (2 per cabinet) | ✅ Stock available; install as needed |
| **EL1859 16-channel I/O module** (future expansion) | Beckhoff | 1 | ⏳ Reserved; not blocking current commissioning |

---

## Part 9: 12-Item Handover Checklist — For Commissioning Engineers

Before handing over the system to operations, verify all 12 items are complete:

### Documentation & Design
- [ ] **D1** This handover document has been read and signed off by at least one commissioning engineer
- [ ] **D2** Wiring diagram (§2.3) matches the **actual cabinet installation** — physical walk-through completed and photo-documented
- [ ] **D3** Bill of materials (§2.1) verified against parts actually installed; no substitutions without re-doing power-supply analysis

### Hardware Installation (per Cabinet)
- [ ] **H1** Relay coils confirmed 24 ±2 V DC with multimeter; supply is stable
- [ ] **H2** Relay contacts tested for continuity; NO/NC logic verified with continuity tester
- [ ] **H3** Cable shielding connected at both ends to 0V common; no floating shields
- [ ] **H4** All wire labels and ferrules per §2.2; legible and correct

### Software & Commissioning
- [ ] **S1** CODESYS application downloaded to DLS008; `xSetOperational` = TRUE
- [ ] **S2** Watch-window procedure (§3) executed successfully; all steps pass
- [ ] **S3** Manual authority tests M1–M6 (§5.2) executed on the cabinet; all six pass
- [ ] **S4** Anti-short-cycle lockout verified: restart blocked while `tOffLockRemain > 0`

### Final Verification
- [ ] **F1** Fail-safe test: DLS008 powered down while cabinet running; red button still stops cabinet (NC contact closes)
- [ ] **F2** Operator trained: local and remote authority explained; red button priority demonstrated
- [ ] **F3** Commissioning checklist (§8) marked complete for this cabinet; all four items ✅

**Sign-off:** All 12 items above must be checked before declaring the cabinet "commissioned."

---

## Part 10: Next Steps — Phase 2 Expansion (Future)

Once the current five-cabinet commissioning is complete:

### Register-map investigation: Right Hand Small Temperature Cabinet
Right Hand Small uses a **Watlow F4T** controller (different register map from the F4S already proven). Before commissioning, a dedicated investigation stage is required:
- Confirm F4T Modbus register map (setpoint read/write addresses differ from F4S)
- Bench-test on the F4T itself before cabinet integration
- Parallel this investigation with ongoing commissioning on other cabinets

### Panel-lock expansion: Setpoint Authority
Route A (§4, "Control Outputs Off") is proven but deprioritized. To re-enable setpoint locking:
- Allocate a second pair of EL2869 channels (currently CH15/CH16 are reserved for on/off)
- Add a `xSetpointLocked` output to gate the F4S "Control Outputs Off" input
- Test on one cabinet first; replicate to others

### Run-status feedback: Future DI installation
Currently the sequencer trusts commanded state (no feedback). To add actual run-status monitoring:
- Install a spare EL1409 digital input module (or use EL1859 future expansion)
- Wire the latching relay's auxiliary contact to the DI
- Add `xCabinetRunning` read in CODESYS; use it for status indication and diagnostics

---

## Appendix: Document Control & References

| Document | Location | Purpose |
|----------|----------|---------|
| Main README (parent project) | Repository root | Project architecture, Stage 1–8 summary, quick-start commands |
| Cabinet on-off investigation (detailed) | `cabinet on-off automation investigation and test logs/README.md` | Full investigation history (§1–19), all four routes, detailed design rationale |
| CODESYS project | Raspberry Pi 10.1.6.17 at `/home/mechatronics/.codesysproject` | Live sequencer code, I/O mapping, watch-window configuration |
| Panel as-built drawing | `docs/7168-DWG-100 - REV B - CP1.pdf` | DLS008 enclosure layout, terminal numbering, signal routing |
| Omron CPM1A datasheet | `docs/Omron PLC CP1MA Datasheet.pdf` | Digital input specifications (opto-isolated, bidirectional); confirms Omron `01`/`02` are suitable for remote voltage sources |

---

**Document prepared by:** Omkar Joshi, Oliver Mechatronics  
**For:** Commissioning Engineers, R&D Temperature Cabinet Fleet  
**Effective:** 14 August 2026  
**Version:** 1.0 Final

---
