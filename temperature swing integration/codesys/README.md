# CODESYS — Temperature Swing

Structured Text source for the Temperature Swing test. These are source files
to be imported/merged into the main CODESYS project (`Device.export`) — they
are not a standalone project.

| File | Purpose |
|---|---|
| `GVL_TemperatureSwing.st` | New global variables only — everything else is reused from the main project GVL |
| `FB_Temperature_Swing.st` | State machine — Draft V2, `xStart`/`iStep` interface matching FB_Hold |
| `FB_Temperature_Target.st` | Small reusable helper: latches ramp direction, reports setpoint reached |

The earlier enum-based `FB_Temperature_Swing.st` / `E_TemperatureSwingState.st`
pair has been deleted — superseded by the files above, confirmed with TL.

## Dependencies on existing project objects

Confirmed by reading the real FBs (FB_Hold, FB_Apply_Test_Pressure,
FB_Pressure_Release, FB_EStop, FB_CSV_Handler) — nothing here is guessed:

- **Isolate convention:** `TRUE` = closed, `FALSE` = open ("Normally Open"),
  confirmed by `FB_EStop` forcing all isolates `TRUE` for the safe state.
- **`FB_Apply_Test_Pressure`** — no inputs, called every scan. Fills via
  `GVL.doUpstream` off `GVL.alrChannelReading[1]` vs `GVL.aiAlarms[1]`, closes
  once at the high alarm. It does **not** re-open if pressure keeps rising
  afterwards — there is no existing FB that relieves pressure caused by
  heating. See "Pressure supervision" below.
- **`FB_Pressure_Release` / `FB_Signature_Pressure_Release`** — same
  continuous no-input pattern, but bleed a channel **down** to a *low* alarm.
  Not directly reusable for venting an over-pressure caused by expansion.
- **`GVL.iMainChannelIndex`** — the monitor-channel variable, reused directly
  from `FB_Hold`. No new channel-index variable needed.
- **CSV recording** — `FB_CSV_Handler.IDLE` triggers off `GVL.xStart` and
  closes off `GVL.xSave` on its own. Nothing to call explicitly in this FB.
- **Hold period convention** — `FB_Hold` stores `iHoldPeriod : INT` (minutes)
  and builds the timer with `DINT_TO_TIME(iHoldPeriod * 60000)`. Reused here
  as `GVL.iTemperatureSwing_HoldPeriod`.

## FB_Temperature_Swing — Draft V2

Per TL review, V2 changes from V1:
1. Delayed-start state removed — handled by the Python frontend.
2. `FB_Apply_Test_Pressure` call corrected to match the real FB (no inputs).
3. Pressure fill/relieve now runs every scan from state 1 onward, not tied
   to one state, so expanding gas vents continuously through ramp and
   stabilisation. The relieve half (open `doDownstream` above the alarm) is
   **new** — no existing FB does this; see above.
4. Stabilisation simplified to a single 30 s rate window; first window
   passing `< 0.5 °C/min` is accepted (was 2 consecutive 60 s windows).
5. Ramp-direction / setpoint-reached logic extracted into
   `FB_Temperature_Target` to keep the main state machine simple.

States below are the **proposed structure only** — not yet implemented
state-by-state. That happens next, one state at a time.

| # | State | Does | Moves on when | Reuses |
|---|---|---|---|---|
| 0 | IDLE | Wait for operator Start | `xStart` TRUE | `GVL.sPrompt` + `xStart` (FB_Hold step 0) |
| 1 | STARTUP | Reset run data; if Test Pressure = 0, set vent-safe default (Upstream closed, Downstream open) | Test Pressure = 0 → 3, else → 2 | Isolate-default pattern (FUN_Program_Startup / FB_Hold) |
| 2 | ESTABLISH_PRESSURE | Wait for chamber to reach alarm pressure | `fbApplyPressure.xDone` | `FB_Apply_Test_Pressure` (running continuously above the CASE) |
| 3 | CABINET_START | Start the temperature cabinet | Start commanded | `xStartPulse` relay path (EL2869 → Omron CPM1A) |
| 4 | SEND_SETPOINT | Write setpoint to cabinet, arm `FB_Temperature_Target` | Write confirmed | Existing Modbus TCP write/read-back |
| 5 | RAMP | Cabinet ramps at its own rate; pressure fill/relieve continues; channel shown white | `fbTarget.xReached` | `FB_Temperature_Target` |
| 6 | STABILISE | Wait for first 30 s window with `\|rate\| < 0.5 °C/min`; channel shown orange | First passing window | Continuous rate sampling (above CASE) |
| 7 | HOLD | Hold at setpoint for `iTemperatureSwing_HoldPeriod` minutes | Hold timer elapsed | FB_Hold timer pattern (`DINT_TO_TIME(*60000)`) |
| 8 | COMPLETE | Leave cabinet running, wait for save; CSV closes automatically | `GVL.xSave` | FB_Hold save-then-stop pattern; `FB_CSV_Handler` |
| 9 | ERROR | Hold rig, wait for acknowledgement | Operator acknowledges | FB_Hold error pattern (E-stop handled centrally by `FB_EStop`/ProgramSelecter) |

### Still open

- **Rate calculation (state 6):** 30 s window structure is in place;
  `rCurrentRate` itself still needs the actual sampling/delta logic.
- **Pressure relieve logic:** the venting bang-bang above is new and untested
  against a real thermal-expansion scenario — worth a bench check once
  implemented, since it wasn't derived from an existing proven FB.
- **Cabinet start/setpoint write (states 3–4):** still TODO, need the exact
  Modbus register map and `xStartPulse` wiring confirmed against the parent
  Temperature Cabinet Control project.
- **Error triggers (state 9):** which failures route here (pressure timeout
  only, or also setpoint-write failure) still to be decided.

## Import steps

1. Open `Device.export` in CODESYS.
2. Add `GVL_TemperatureSwing.st` variables to the project's main GVL.
3. Add `FB_Temperature_Swing.st` and `FB_Temperature_Target.st` as new POUs,
   instantiate in the automation task (`Automation (Core 3)`).
4. Wire the outputs/inputs once each state is implemented against the real
   project — see "Still open" above.
