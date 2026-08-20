# CODESYS — Temperature Swing

Structured Text source for the Temperature Swing test. These are source files
to be imported/merged into the main CODESYS project (`Device.export`) — they
are not a standalone project.

| File | Purpose |
|---|---|
| `GVL_TemperatureSwing.st` | New global variables (append to project GVL) |
| `E_TemperatureSwingState.st` | State enum from the original Stage 2 design (see note below) |
| `FB_Temperature_Swing.st` | **Current** state machine — Draft V2, `xStart`/`iStep` interface matching FB_Hold |
| `FB_Temperature_Target.st` | Small reusable helper: latches ramp direction, reports setpoint reached |
| `FB_TemperatureSwing.st` | Superseded — original enum-based design from Stage 2. Kept until V2 is signed off; to be deleted once confirmed unused. |

## Dependencies on existing project objects

Not included here — already exist in the main project:

- `FB_Apply_Test_Pressure` — **no inputs**, called every scan. Reads
  `GVL.alrChannelReading[1]` and `GVL.aiAlarms[1]`, drives `GVL.doUpstream`.
  Confirmed against the actual FB source TL supplied — the pressure band
  logic in V1 of this doc was wrong and has been removed.
- `GVL.sPrompt`, `GVL.xSave`, `GVL.iTestPressure` — existing global variables
- CSV recorder start trigger — reused pattern, exact call TBC (see open
  questions below)

## FB_Temperature_Swing — Draft V2

Per TL review (see commit history), V2 changes from V1:
1. Delayed-start state removed — handled by the Python frontend, not CODESYS.
2. `FB_Apply_Test_Pressure` call corrected to match the real FB (no inputs).
3. Pressure supervision (`fbApplyPressure()`) now runs every scan, outside
   the `CASE`, once a pressurised test is active — not tied to one state —
   so expanding gas vents continuously through ramp and stabilisation.
4. Stabilisation simplified to a single 30 s rate window; first window
   passing `< 0.5 °C/min` is accepted (was 2 consecutive 60 s windows).
5. Ramp-direction / setpoint-reached logic extracted into
   `FB_Temperature_Target` to keep the main state machine simple.

States below are the **proposed structure only** — not yet implemented
state-by-state. That happens next, one state at a time, once this structure
is agreed.

| # | State | Does | Moves on when | Reuses |
|---|---|---|---|---|
| 0 | IDLE | Wait for operator Start | `xStart` TRUE | `GVL.sPrompt` + `xStart` (FB_Hold step 0) |
| 1 | STARTUP | Reset run data, start CSV, set vent-safe solenoid default if Test Pressure = 0 | Always → 3 if Test Pressure = 0, else → 2 | FB_Hold startup pattern; existing CSV trigger |
| 2 | ESTABLISH_PRESSURE | Wait for chamber to reach alarm pressure | `fbApplyPressure.xDone` | `FB_Apply_Test_Pressure` (called continuously above the CASE) |
| 3 | CABINET_START | Start the temperature cabinet | Start commanded | `xStartPulse` relay path (EL2869 → Omron CPM1A) |
| 4 | SEND_SETPOINT | Write setpoint to cabinet, arm `FB_Temperature_Target` | Write confirmed | Existing Modbus TCP write/read-back |
| 5 | RAMP | Cabinet ramps at its own rate; pressure vents continuously; channel shown white on HMI | `fbTarget.xReached` | `FB_Temperature_Target` |
| 6 | STABILISE | Wait for first 30 s window with `\|rate\| < 0.5 °C/min`; channel shown orange | First passing window | Continuous rate sampling (above CASE) |
| 7 | HOLD | Hold at setpoint for operator-configured hold time | Hold timer elapsed | FB_Hold timer pattern |
| 8 | COMPLETE | Close CSV, leave cabinet running, wait for save | `GVL.xSave` | FB_Hold save-then-stop pattern |
| 9 | ERROR | Hold rig, wait for acknowledgement | Operator acknowledges | FB_Hold error pattern (E-stop handled centrally by ProgramSelecter) |

### Open questions (need answers from the RnD project before implementing)

- **Pressure arming point:** currently gated on `iStep >= 2`. Should it arm
  from state 1 instead, so venting covers the whole run including startup?
- **Hold time variable:** V2 code uses `GVL.tTemperatureSwing_HoldTime`
  (TIME). Current `GVL_TemperatureSwing.st` has `rTemperatureSwing_HoldTime`
  (REAL, minutes) — need to confirm which the Python frontend actually
  writes, and convert if it's the REAL/minutes one.
- **Monitor channel index:** `GVL.iTemperatureSwing_ChannelIndex` is still a
  placeholder. Need the real variable name and whether it's a raw array
  index or needs an offset (HMI discovery notes mentioned `+ 18`).
- **Venting direction:** `FB_Apply_Test_Pressure` only drives `doUpstream`
  off a single high alarm — it does not touch `doDownstream`. Need to
  confirm this alone is sufficient for venting expanding gas, or whether
  downstream needs separate handling during RAMP/STABILISE.
- **File cleanup:** `FB_TemperatureSwing.st` (no underscore, enum-based) is
  the original Stage 2 design and is superseded by `FB_Temperature_Swing.st`.
  Confirm it can be deleted once V2 is signed off.

## Import steps

1. Open `Device.export` in CODESYS.
2. Add `GVL_TemperatureSwing.st` variables to the project's main GVL.
3. Add `FB_Temperature_Swing.st` and `FB_Temperature_Target.st` as new POUs,
   instantiate in the automation task (`Automation (Core 3)`).
4. Wire the outputs/inputs once each state is implemented against the real
   project — see open questions above.
