# Stage 2: Temperature Swing Integration — Design Document

**Project:** Temperature Swing Integration (API 6A Compliance)
**Parent project:** ISO15848-1 Automated R&D Test Rig / DLS Temperature Cabinet Control
**Status:** Design complete, ready for implementation (Stage 3)

---

## 1. Purpose

Add an API 6A–compliant Temperature Swing test to the existing temperature cabinet
control system. The system already provides remote setpoint control and cabinet
on/off automation (see root `README.md`). This design adds the missing piece: an
automated ramp → stabilise → hold → return test cycle with rate-of-change and
overshoot enforcement, run and logged without operator intervention beyond the
initial start dialog.

---

## 2. Temperature Swing State Sequence

```
IDLE
  |
  v
START  (operator enters extreme temp, pressure mode, hold time in Start Dialog)
  |
  v
RAMP  (drive setpoint toward extreme; rate monitored continuously)
  |
  v
MONITOR_RATE  (confirm |rate| < 0.5 C/min for 2+ consecutive 60 s windows)
  |
  v
APPROACH_EXTREME  (within 2 C of target; slow, final approach)
  |
  v
VERIFY_EXTREME  (extreme reached/passed in the commanded direction)
  |
  v
STABILISE  (settle; overshoot being measured against +/-11 C limit)
  |
  v
OVERSHOOT_CHECK  (overshoot <= 11 C -> continue; > 11 C -> flag, do not abort)
  |
  v
HOLD_EXTREME  (hold for configured duration, default 10 min)
  |
  v
RETURN  (ramp back toward ambient/neutral; rate monitored again)
  |
  v
RETURN_STABILISE  (confirm return rate < 0.5 C/min)
  |
  v
CYCLE_COMPLETE  (log summary, release pressure if applied)
  |
  v
IDLE
```

**Safety exits (valid from any state):** STOP pressed, alarm raised, or unexpected
setpoint deviation -> transition directly to `IDLE`, log as aborted, close solenoids.

State encoding and transition table are implemented in
[`codesys/FB_Temperature_Swing.st`](../codesys/FB_Temperature_Swing.st).

---

## 3. Temperature-Rate Calculation

- **Sample rate:** 1 Hz into a 3600-sample rolling buffer (60-minute window).
- **Rate window:** every 60 s, `rate = (T_now - T_60s_ago) / 1 min`.
- **Pass condition:** `|rate| < 0.5 C/min`.
- **Debounce:** require 2 consecutive passing windows before advancing state,
  tolerate one isolated spike above threshold without failing the test.
- **Measurement channel:** Body Temperature primary; falls back to Monitor
  Temperature if Body Temperature channel is faulted (fallback is logged, not
  silent).

Implemented in `FB_Temperature_Swing.st` (`fRateOfChange` calculation block) and
mirrored for host-side display in `temperature_swing_manager.py`.

---

## 4. Pressure Establishment

Reuses the existing `FB_Apply_Test_Pressure` function block (already used by
other DLS programs — Holds, PR2 Dynamic Cycle).

| Selected mode | Target pressure |
|---|---|
| None | 0 psi |
| 50% | 0.50 x test pressure |
| 75% | 0.75 x test pressure |
| 100% | 1.00 x test pressure |

Sequence: write target -> call `FB_Apply_Test_Pressure` -> wait `xDone` (300 s
timeout) -> on success set `xTemperatureSwing_PressureReady` and proceed to
`RAMP`; on timeout/error, log and return to `IDLE` without starting the ramp.

---

## 5. Pressure Maintenance (50–100% Modes)

Closed-loop bang-bang control around the established target, reusing the
existing upstream/downstream solenoid pair:

- `error > +0.5 psi` -> open upstream, close downstream (increase pressure)
- `error < -0.5 psi` -> close upstream, open downstream (bleed pressure)
- `|error| <= 0.5 psi` -> both closed (hold)

Active throughout `RAMP`, `MONITOR_RATE`, `APPROACH_EXTREME`, `STABILISE`, and
`HOLD_EXTREME`. Logged every 10 s. Deviations beyond 1.0 psi are logged as a
warning but do not abort the test.

---

## 6. Existing Functions Reused

| Function / pattern | Source | Reused for |
|---|---|---|
| `FB_Apply_Test_Pressure` | Existing DLS pressure control | Pressure establishment (Section 4) |
| `FB_Stabilisation_Check` | Existing DLS stabilisation logic | Rate monitoring (Section 3) |
| Upstream/downstream solenoid pattern | Existing DLS pressure control | Pressure maintenance (Section 5) |
| Program-selection / Start Dialog pattern | `_05_Automation` visualisation | Temperature Swing dialog (Section 7) |
| CSV data-recorder pattern | Existing DLS data logger | Test result logging |
| Setpoint write path | This repo's setpoint-control work | Driving the cabinet extreme via Modbus |

---

## 7. HMI Changes

- New Start Dialog: extreme temperature, pressure mode, hold duration
  (`frontend/start_dialog_temperature_swing.html`).
- New Progress page: live state, rate, overshoot, pressure, hold countdown
  (`frontend/temperature_swing_progress.html`).
- `_12_Controls`: add pressure-mode/solenoid status indicator when swing active.
- `_04_Details`: add Temperature Swing section (state, rate PASS/FAIL, overshoot).
- Channel highlighting: Body Temperature blue (active), Chamber Pressure green
  (controlled), Monitor Temperature grey (fallback only).

---

## 8. OPC / CODESYS Variables

Full variable list: [`docs/GVL_TemperatureSwing_Variables.md`](GVL_TemperatureSwing_Variables.md)
Full OPC node map: [`backend/config_temperature_swing.py`](../backend/config_temperature_swing.py)

---

## 9. API 6A Compliance Mapping

| Requirement | Section | Where enforced |
|---|---|---|
| F.1.9 Temperature Testing (ramp/hold/return) | 2 | `FB_Temperature_Swing.st` state machine |
| F.1.10 Hold Periods / Stabilisation (<0.5 C/min) | 3 | `FB_Temperature_Swing.st` rate check |
| F.1.11 Pressure/Temperature Cycles | 4, 5 | `FB_Temperature_Swing.st` pressure blocks |
| Overshoot <= 11 C | 2, 3 | `OVERSHOOT_CHECK` state, logged not enforced-abort |

---

## 10. Deliverables in This Folder

| File | Purpose |
|---|---|
| `codesys/FB_Temperature_Swing.st` | State machine, rate calc, pressure control (Structured Text) |
| `codesys/GVL_TemperatureSwing.st` | New global variables |
| `backend/temperature_swing_manager.py` | Python OPC UA manager class |
| `backend/config_temperature_swing.py` | OPC node ID map |
| `backend/websocket_temperature_swing.py` | Real-time status broadcast to HMI |
| `frontend/start_dialog_temperature_swing.html` | Operator start dialog |
| `frontend/temperature_swing_progress.html` | Live progress display |
| `docs/GVL_TemperatureSwing_Variables.md` | Full variable reference |
| `docs/Test_Plan_Temperature_Swing.md` | Hardware test plan and acceptance criteria |
| `README.md` (this folder) | Folder overview and implementation checklist |

---

**Document version:** 1.0
**Status:** Ready for Stage 3 (implementation) — see checklist in folder `README.md`
