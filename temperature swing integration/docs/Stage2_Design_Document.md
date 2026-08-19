# Stage 2: Temperature Swing Integration — Design Proposal

**Project:** Temperature Swing Integration (API 6A Compliance)
**Parent project:** ISO15848-1 Automated R&D Test Rig / DLS Temperature Cabinet Control
**Document version:** 2.0 — reconciled against the project kickoff document
**Supersedes:** v1.0 (pre-kickoff draft). See Section 12 for what changed and why.
**Status:** Design settled except one item — ambient-return tolerance awaiting TL sign-off (Section 11)

---

## 1. Purpose

Add an API 6A–compliant Temperature Swing test to the existing temperature cabinet
control system. The system already provides remote setpoint control and cabinet
on/off automation (see root `README.md`). This design adds the missing piece: an
automated **ramp → reach/pass setpoint → stabilise → complete** sequence with
rate-of-change measurement, target-range display, and CSV logging, run without
operator intervention beyond the initial Start Dialog.

**One execution per start.** No multi-cycle chaining, no automatic progression
from API 6A §17 → §18 → §19. The operator runs the program once per
direction/pressure combination.

---

## 2. Temperature Swing State Sequence

Order is taken directly from the kickoff document: delayed start → normal startup
and CSV begin → establish pressure → configure/start cabinet → send setpoint →
monitor/control → reach or pass → stabilise → complete.

```
IDLE
  │  operator starts via Start Dialog
  ▼
DELAYED_START                  ← skipped if no delayed start configured
  │  reuse existing delayed-start behaviour
  ▼
STARTUP_AND_CSV_BEGIN
  │  normal program startup; CSV recording opens here
  ▼
ESTABLISH_PRESSURE             ← skipped entirely if pressure mode = 0 psi
  │  FB_Apply_Test_Pressure → target band (50/75/100% of test pressure)
  ▼
CABINET_CONFIGURE_AND_START
  │  configure and start the temperature cabinet
  ▼
SEND_SETPOINT
  │  write operator setpoint (positive or negative) to the cabinet
  ▼
RAMP_AND_SUPERVISE
  │  cabinet drives toward setpoint at its natural rate
  │  rate measured and displayed; pressure band supervised if pressurised
  ▼
STABILISING
  │  |rate| < 0.5 °C/min for 2 consecutive 60 s windows
  ▼
COMPLETE
  │  CSV closed; cabinet left at setpoint (see Section 9)
  ▼
IDLE
```

**Safety exit (valid from any state):** STOP pressed or active alarm →
transition to `IDLE`, log as aborted. This is the existing pattern used by
PR2 and the Hold programs; no new fault-handling architecture is introduced.

**No HOLD state.** The kickoff document specifies "reach or pass the requested
temperature; wait for temperature stabilisation; complete the Temperature Swing."
There is no operator-set hold duration and no automatic return ramp in this
program.

State encoding and transition table are implemented in
[`codesys/FB_TemperatureSwing.st`](../codesys/FB_TemperatureSwing.st).

---

## 3. Temperature-Rate Calculation

Reuses the existing DLS stabilisation pattern rather than introducing a new
algorithm.

| Item | Value |
|---|---|
| Sample rate | 1 Hz into a 60-sample rolling buffer |
| Rate window | every 60 s: `rate = (T_now − T_60s_ago) / 60 s` |
| Pass condition | `|rate| < 0.5 °C/min` (API 6A F.1.10) |
| Debounce | 2 consecutive passing windows before declaring stabilised |
| Measurement channel | operator-selected in the Start Dialog (Section 7) |

**Measurement only, not control.** Per the agreed scope exclusion on artificial
temperature ramp-rate control, the heater/cooler output is **not** throttled to
enforce 0.5 °C/min. The cabinet ramps at its natural rate; software measures and
reports whether that rate satisfies API 6A. A ramp too fast for compliance is a
result to record, not a control loop to add.

Implemented in `FB_TemperatureSwing.st` (`rTempSwing_CurrentRate` calculation
block) and mirrored host-side for display in `temperature_swing_manager.py`.

---

## 4. Target Range and Overshoot

The 11 °C figure from API 6A defines the **acceptable target range displayed to
the operator**, not an abort trigger.

| Direction | Displayed target range |
|---|---|
| Heating | Setpoint to Setpoint + 11 °C |
| Cooling | Setpoint to Setpoint − 11 °C |

Reaching **or passing** the setpoint satisfies the reach condition; stabilisation
is then evaluated wherever the cabinet settles. Exceeding 11 °C past the setpoint
is recorded in the CSV and shown on the HMI, but **does not automatically abort
the test** — building extensive new fault-handling before basic functionality is
proven is explicitly out of scope.

---

## 5. Pressure Establishment

Reuses `FB_Apply_Test_Pressure` unmodified — the same block already used by the
Hold and PR2 Dynamic Cycle programs.

| Selected mode | Target |
|---|---|
| 0 psi | *state skipped entirely — see Section 6* |
| 50% | 0.50 × test pressure |
| 75% | 0.75 × test pressure |
| 100% | 1.00 × test pressure |

Sequence: write target → call `FB_Apply_Test_Pressure` → wait `xDone`
(≈300 s timeout) → on success set `xTempSwing_PressureReady` and advance to
`CABINET_CONFIGURE_AND_START`; on timeout or error, log and return to `IDLE`
without starting the ramp.

---

## 6. Pressure Behaviour During the Swing

### 6.1 Pressurised variants (50 / 75 / 100 %)

Supervision, not new control logic. The existing upstream/downstream bang-bang
solenoid pattern is reused as-is; Temperature Swing adds only a band check
running in parallel with the temperature ramp:

```
chamber_pressure < 50 % of test pressure   → flag LOW    (existing solenoid logic corrects)
chamber_pressure > 100 % of test pressure  → flag HIGH   (existing solenoid logic corrects)
otherwise                                  → IN BAND     (xTempSwing_PressureInBand)
```

This matches the Oliver Valvetek §17/18/19 wording — "maintaining pressure at
50 % to 100 % of test pressure." Existing tolerance behaviour (±0.5 psi
deadband, both solenoids closed when in band) is unchanged. Active throughout
`RAMP_AND_SUPERVISE` and `STABILISING`.

### 6.2 Zero-pressure variant (0 psi)

Fixed solenoid state, no supervision at all:

| Solenoid | State |
|---|---|
| Upstream | Closed |
| Downstream | Open |

`ESTABLISH_PRESSURE` is skipped, band supervision is skipped, and
pressure-maintenance logic is ignored for the duration of the swing. This is
simpler than the pressurised path, not a reduced version of it.

---

## 7. Start Dialog

New dialog, built on the existing Start Dialog pattern — an additional entry
point alongside the existing program selector, not a replacement page.

| Field | Behaviour |
|---|---|
| Test Pressure | existing control, reused |
| Test Section Number | existing control, reused |
| Test Name | existing control, reused |
| Delayed Start | existing control, reused |
| Readings per Second | existing control, reused |
| Cycles | present but **fixed to 1** — single execution only |
| Temperature Setpoint | single field accepting positive **and** negative values |
| Temperature Monitoring Channel | dropdown, five fixed options (below) |
| Pressure Mode | 0 % / 50 % / 75 % / 100 % of test pressure |

**Monitoring channel options** — a fixed generic list, consistent with the
existing "Select Main Channel" dropdown. The same five options appear regardless
of which cabinet is running the program; there is no cabinet-specific filtering:

1. Ambient Temperature
2. Body Temperature
3. Monitor Temperature
4. Chamber Temperature
5. Hyperbaric Water Temperature

---

## 8. Pressure Display Page (extended, not rebuilt)

The existing Pressure Display page is reused with four additions:

1. **Prompt bar** — state-driven operator guidance. During the ramp:
   `"Temperature ramp to {setpoint}°C. Target range: {setpoint}°C to {setpoint ± 11}°C."`
   Other states use the same bar ("Establishing pressure…", "Stabilising…",
   "Stabilised ✓").
2. **Channel highlighting** — the selected monitoring channel's card is
   **white** while the ramp is progressing, turning **orange** once the setpoint
   is reached or passed and the program is awaiting stabilisation.
3. **Rate readout** — current rate displayed beneath the channel value, e.g.
   `0.32 °C/min`, with pass/fail against 0.5 °C/min shown visually.
4. **Chamber Temperature card stays visible** as its own card at all times,
   regardless of which monitoring channel the operator selected.

No new HMI page architecture — this rides on the Pressure Display and Start
Dialog patterns already proven in PR2.

---

## 9. End-of-Test Behaviour

| Scenario | Behaviour |
|---|---|
| Pressurised test | **Never auto-vent.** Pressure release remains a deliberate technician action. |
| Normal hot/cold swing | Cabinet is left running at the setpoint, ready for the next test. |
| Ambient-return swing | Cabinet switches off only when the user stops the test, after the ambient condition is met. |

**Proposed ambient-detection method** (the kickoff document asks for a proposal
before implementation):

```
xAmbientConditionMet := ABS(rValveTemp - rAmbientTemp) <= rAmbientTolerance;
```

Proposed `rAmbientTolerance` = **5 °C**, matching thermal-equilibrium margins
used elsewhere in DLS. This is a new constant and is the one item still requiring
TL sign-off (Section 11). The full API 6A 4–50 °C range is deliberately **not**
used as the rule here.

---

## 10. Existing Functions and Patterns Reused

| Function / pattern | Source | Reused as-is? |
|---|---|---|
| `FB_Apply_Test_Pressure` | Existing DLS | Yes, unmodified |
| Upstream/downstream bang-bang solenoid control | Existing DLS (PR2 pattern) | Yes, unmodified |
| Stabilisation rate-window calculation | Existing DLS pattern | Yes, unmodified |
| Delayed-start behaviour | Existing (PR2 "Delayed Start Time") | Yes, directly |
| CSV recorder (`Historical_CSV`, `FB_CSV_Handler`, `FB_Buffer_Data`) | Existing DLS | Yes — Temperature Swing added as another data source, no new logging architecture |
| Start Dialog pattern | `_05_Automation` visualisation | Extended with new fields |
| Pressure Display page | Existing HMI | Extended per Section 8, not rebuilt |
| Setpoint write path | This repo's setpoint-control work | Drives the cabinet setpoint |
| Program selector | `ProgramSelecter` | Extend the list, don't restructure — slot convention under investigation (Section 11) |
| EL4078 analog output | Hardware I/O (ESI now installed) | Heating/cooling control signal path |
| EL2869 digital output | Hardware I/O | Solenoid control, existing channels |

Nothing here requires modifying PR2. Temperature Swing is a sibling program that
borrows PR2's function blocks, not PR2's program logic.

---

## 11. OPC / New CODESYS Variables

Append-only additions to the existing GVL — no restructuring, no new
persistent-variable categories:

```
rTempSwing_SetpointCommand   : LREAL   // operator entered, may be negative
iTempSwing_MonitorChannel    : INT     // 1..5, per Section 7
iTempSwing_PressureMode      : INT     // 0 / 50 / 75 / 100
xTempSwing_Start             : BOOL
xTempSwing_Stop              : BOOL
eTempSwing_State             : E_TemperatureSwingState   // new enum
rTempSwing_CurrentRate       : LREAL   // °C/min, read-only, display
xTempSwing_Stabilised        : BOOL
xTempSwing_PressureInBand    : BOOL
```

Full variable reference: [`GVL_TemperatureSwing_Variables.md`](GVL_TemperatureSwing_Variables.md)
Full OPC node map: [`../backend/config_temperature_swing.py`](../backend/config_temperature_swing.py)

Separately (not part of this design): the existing C0569 persistence warnings on
`rDownstreamDemandPercent` and similar are worth clearing while the GVL is open.

---

## 12. Open Items

| # | Item | Type | Owner |
|---|---|---|---|
| 1 | `rAmbientTolerance` = 5 °C for ambient-return detection (Section 9) | New constant — needs sign-off | TL |
| 2 | Program selector slot/ID convention for adding Temperature Swing | Investigation, not a question | Me — inspect `ProgramSelecter` in CODESYS and report |

Everything else previously listed as an open question is now settled directly
from the kickoff document (Section 13).

---

## 13. Reconciliation Against the Kickoff Document

What v1.0 of this document got wrong, and the source text that corrected it.

| # | v1.0 draft | Kickoff document | v2.0 |
|---|---|---|---|
| 1 | `HOLD_EXTREME` state with operator-set duration, followed by `RETURN` and `RETURN_STABILISE` | "reach or pass the requested temperature; wait for temperature stabilisation; complete the Temperature Swing" | HOLD and RETURN states removed entirely (Section 2) |
| 2 | Overshoot treated as a check state with abort semantics under discussion | "For heating: Setpoint to Setpoint + 11 °C. For cooling: Setpoint to Setpoint − 11 °C" — a displayed target range | Range display only, no auto-abort (Section 4) |
| 3 | Monitoring channel possibly cabinet-specific | Fixed list of five generic channels | Fixed list, no filtering (Section 7) |
| 4 | 0 psi treated as a reduced-supervision case | "Upstream closed; Downstream open… pressure-maintenance logic should be ignored for the duration of the swing" | Supervision skipped completely (Section 6.2) |
| 5 | Pressure established before normal program startup | Order: delayed start → normal startup + CSV begin → establish pressure | Sequence reordered (Section 2) |
| 6 | End-of-test behaviour unaddressed | Never auto-vent; leave at setpoint; ambient return only on user stop | Added as Section 9 |
| 7 | HMI changes described loosely | Exact prompt-bar text, white→orange highlighting, rate readout, Chamber card always visible | Specified exactly (Section 8) |
| 8 | Body Temperature primary with Monitor Temperature fallback | Operator selects the channel | Operator-selected, no silent fallback (Sections 3, 7) |

---

## 14. API 6A Compliance Mapping

| Requirement | Section | Where enforced |
|---|---|---|
| F.1.9 Temperature Testing | 2 | `FB_TemperatureSwing.st` state machine |
| F.1.10 Stabilisation (<0.5 °C/min) | 3 | `FB_TemperatureSwing.st` rate check, 2-window debounce |
| F.1.11 Pressure/Temperature Cycles (50–100 %) | 5, 6 | `FB_TemperatureSwing.st` pressure blocks |
| Overshoot ≤ 11 °C | 4 | Target-range display + CSV record (measured, not enforced) |

---

## 15. Scope Boundaries Carried Into This Design

- ❌ No changes to PR2 itself
- ❌ No auto-chaining of API 6A §17 → §18 → §19
- ❌ No chaining into pressure-hold programs
- ❌ No DB / Test Profile schema changes
- ❌ No new CSV architecture — append to the existing recorder
- ❌ No hardcoded universal cabinet limits — per-cabinet config unchanged
- ❌ No operator-configurable API limits — 0.5 °C/min and 11 °C stay fixed constants
- ❌ No artificial ramp-rate throttling — natural ramp, monitored not controlled
- ❌ No new fault-handling architecture before basic functionality is proven

---

## 16. Deliverables in This Folder

| File | Purpose |
|---|---|
| `codesys/FB_TemperatureSwing.st` | State machine, rate calculation, pressure supervision |
| `codesys/GVL_TemperatureSwing.st` | New global variables (Section 11) |
| `codesys/E_TemperatureSwingState.st` | State enum |
| `backend/temperature_swing_manager.py` | Python OPC UA manager |
| `backend/config_temperature_swing.py` | OPC node ID map |
| `backend/websocket_temperature_swing.py` | Real-time status broadcast to HMI |
| `frontend/start_dialog_temperature_swing.html` | Operator Start Dialog (Section 7) |
| `frontend/temperature_swing_progress.html` | Live progress display (Section 8) |
| `docs/GVL_TemperatureSwing_Variables.md` | Full variable reference |
| `docs/Test_Plan_Temperature_Swing.md` | Hardware test plan and acceptance criteria |

---

**Next:** Stage 3 — draft `FB_TemperatureSwing.st` against this corrected design.
Item 1 in Section 12 (ambient tolerance) blocks only the ambient-return path;
the main hot/cold swing can be drafted without it.

**Principle:** Rebuild → Retest → Requalify → Reattempt → Repeat
