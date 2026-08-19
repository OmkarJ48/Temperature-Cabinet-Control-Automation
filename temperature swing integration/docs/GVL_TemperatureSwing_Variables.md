# GVL Variable Reference — Temperature Swing

**Aligned to:** [`Stage2_Design_Document.md`](Stage2_Design_Document.md) v2.0
**Supersedes:** the v1.0 list (hold timer, hold duration, channel fallback — all removed, see bottom of this file).

All variables below are appended to the project's Global Variable List (GVL) and
declared in [`codesys/GVL_TemperatureSwing.st`](../codesys/GVL_TemperatureSwing.st).
Naming follows the repo convention: `x`=BOOL, `i`=INT, `r`=REAL/LREAL, `s`=STRING,
`t`=TIME, with the `TempSwing_` block prefix.

Append-only: no restructuring of the existing GVL, no new persistent-variable
categories.

---

## Core set (Design Document Section 11)

These nine are the minimum required for the program to run and display.

| Variable | Type | Description |
|---|---|---|
| `rTempSwing_SetpointCommand` | LREAL | Operator-entered setpoint, °C — may be negative |
| `iTempSwing_MonitorChannel` | INT | Selected monitoring channel, 1..5 (see below) |
| `iTempSwing_PressureMode` | INT | 0 / 50 / 75 / 100 (percent of test pressure) |
| `xTempSwing_Start` | BOOL | Start Dialog confirmed, begin test |
| `xTempSwing_Stop` | BOOL | Operator or safety abort |
| `eTempSwing_State` | E_TemperatureSwingState | Current state (see enum) |
| `rTempSwing_CurrentRate` | LREAL | Calculated rate, °C/min — read-only, display |
| `xTempSwing_Stabilised` | BOOL | 2 consecutive passing 60 s windows achieved |
| `xTempSwing_PressureInBand` | BOOL | Chamber pressure within 50–100 % band |

### `iTempSwing_MonitorChannel` encoding

Fixed generic list — the same five options on every cabinet, no filtering.

| Value | Channel |
|---|---|
| 1 | Ambient Temperature |
| 2 | Body Temperature |
| 3 | Monitor Temperature |
| 4 | Chamber Temperature |
| 5 | Hyperbaric Water Temperature |

---

## Program selection

| Variable | Type | Description |
|---|---|---|
| `xProgram_TemperatureSwing` | BOOL | TRUE when Temperature Swing selected in `_05_Automation` |
| `xTempSwing_Active` | BOOL | Test currently running |

---

## Rate calculation support

| Variable | Type | Description |
|---|---|---|
| `rTempSwing_MonitorValue` | LREAL | Live value of the selected monitoring channel, °C |
| `rTempSwing_Value_60s_Ago` | LREAL | Same channel 60 s ago (rate-window numerator) |
| `xTempSwing_RateCheckPassed` | BOOL | Latest 60 s window passed `\|rate\| < 0.5 °C/min` |
| `iTempSwing_ConsecutivePassWindows` | INT | Consecutive passing windows (stabilised at 2) |

No fallback-channel variable: the operator selects the channel and it is not
silently substituted.

---

## Setpoint reach and target range

| Variable | Type | Description |
|---|---|---|
| `xTempSwing_SetpointReached` | BOOL | Setpoint reached **or passed** in the commanded direction |
| `rTempSwing_TargetRangeMin` | LREAL | Displayed range lower bound, °C |
| `rTempSwing_TargetRangeMax` | LREAL | Displayed range upper bound, °C |
| `rTempSwing_Overshoot` | LREAL | Current excursion past setpoint, °C |
| `rTempSwing_MaxOvershoot` | LREAL | Max excursion observed this run, °C |
| `xTempSwing_OutsideTargetRange` | BOOL | Beyond the 11 °C bound — logged and displayed, **non-aborting** |

Target range is `Setpoint` → `Setpoint + 11 °C` when heating, `Setpoint` →
`Setpoint − 11 °C` when cooling.

---

## Pressure

| Variable | Type | Description |
|---|---|---|
| `rTempSwing_TargetPressure` | LREAL | Established target, psi (0 when mode = 0 %) |
| `xTempSwing_PressureReady` | BOOL | `FB_Apply_Test_Pressure` completed successfully |
| `rTempSwing_PressureError` | LREAL | Current pressure minus target, psi |
| `xTempSwing_ZeroPressureMode` | BOOL | TRUE when mode = 0 % — upstream closed, downstream open, all supervision skipped |

---

## Program selector

Confirmed by direct inspection of `ProgramSelecter.st` (Design Document
Section 10a): Temperature Swing runs as `FB_Temperature_Swing` at
`GVL.iProgram = 13`, the next open sequential slot after `Five_to_10_PR2`
(12) and before the reserved `Calibration` slot (99). A commented-out
placeholder for this exact FB name already exists in `ProgramSelecter.st`.

The FB must expose `xStart` (BOOL, IN), `iStep` (INT), and `xDone` (BOOL) to
match the call contract every other program FB satisfies — see Section 10a
of the design document for the exact call pattern.

---

## Ambient return (pending TL sign-off — Design Document Section 12)

| Variable | Type | Description |
|---|---|---|
| `rTempSwing_AmbientTolerance` | LREAL | Proposed **5.0** °C — not yet approved |
| `xTempSwing_AmbientConditionMet` | BOOL | `ABS(rValveTemp - rAmbientTemp) <= rTempSwing_AmbientTolerance` |

Do not implement until item 1 in Section 12 of the design document is signed off.

---

## Timers

| Variable | Type | Description |
|---|---|---|
| `tTempSwing_RampStartTime` | TIME | Timestamp `RAMP_AND_SUPERVISE` entered |
| `tTempSwing_RunStartTime` | TIME | Timestamp run started |

No hold timer — there is no hold state in this program.

---

## Logging

| Variable | Type | Description |
|---|---|---|
| `sTempSwing_LogFile` | STRING(255) | CSV file path for this run |
| `xTempSwing_LoggingActive` | BOOL | Logging in progress |
| `iTempSwing_DataPoints` | INT | Data points written this run |

Written through the existing `Historical_CSV` / `FB_CSV_Handler` /
`FB_Buffer_Data` recorder — no new logging architecture.

---

## Errors

| Variable | Type | Description |
|---|---|---|
| `xTempSwing_Error` | BOOL | Run encountered an error |
| `sTempSwing_ErrorMessage` | STRING(255) | Error description |
| `iTempSwing_ErrorCode` | INT | Numeric error code |

---

## Removed from v1.0

| Removed variable | Reason |
|---|---|
| `rTemperatureSwing_HoldTime` | No hold state — kickoff specifies ramp → stabilise → complete |
| `iTemperatureSwing_HoldTimer` | As above |
| `xTemperatureSwing_UsingFallbackChannel` | Operator selects the channel; no silent fallback |
| `rBodyTemp_Current` / `rBodyTemp_Previous_60s` | Replaced by channel-agnostic `rTempSwing_MonitorValue` / `rTempSwing_Value_60s_Ago` |

The `rTemperatureSwing_*` prefix from v1.0 is replaced throughout by
`rTempSwing_*` to match the design document. The drafted files in `codesys/`,
`backend/`, and `frontend/` still carry v1.0 names and must be re-drafted in
Stage 3 against this reference.

---

## OPC UA Node ID convention

All variables are exposed under `ns=3;s="GVL"."<VariableName>"`. See
[`backend/config_temperature_swing.py`](../backend/config_temperature_swing.py)
for the Python-side node map (also pending the Stage 3 re-draft).
