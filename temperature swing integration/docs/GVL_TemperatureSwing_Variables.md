# GVL Variable Reference — Temperature Swing

All variables below are added to the project's Global Variable List (GVL) and
declared in [`codesys/GVL_TemperatureSwing.st`](../codesys/GVL_TemperatureSwing.st).
Naming follows the repo convention: `x`=BOOL, `i`=INT, `r`=REAL, `s`=STRING,
`t`=TIME.

## Program selection and control

| Variable | Type | Description |
|---|---|---|
| `xProgram_TemperatureSwing` | BOOL | TRUE when Temperature Swing selected in `_05_Automation` |
| `xTemperatureSwing_Start` | BOOL | Start Dialog confirmed, begin test |
| `xTemperatureSwing_Stop` | BOOL | Operator or safety abort |
| `xTemperatureSwing_Active` | BOOL | Test currently running |

## Operator input (Start Dialog)

| Variable | Type | Description |
|---|---|---|
| `rTemperatureSwing_Extreme` | REAL | Target extreme temperature, degC |
| `rTemperatureSwing_PressureMode` | REAL | 0 / 50 / 75 / 100 (percent of test pressure) |
| `rTemperatureSwing_HoldTime` | REAL | Hold duration at extreme, minutes |

## State machine

| Variable | Type | Description |
|---|---|---|
| `iTemperatureSwing_CurrentState` | INT | Current state (see `E_TemperatureSwingState` enum) |

## Temperature monitoring

| Variable | Type | Description |
|---|---|---|
| `rBodyTemp_Current` | REAL | Current Body Temperature reading, degC |
| `rBodyTemp_Previous_60s` | REAL | Body Temperature 60 s ago (for rate calc) |
| `rTemperatureSwing_Rate` | REAL | Calculated rate, degC/min |
| `xTemperatureSwing_RateCheckPassed` | BOOL | Latest rate check result |
| `iTemperatureSwing_ConsecutivePassWindows` | INT | Consecutive passing 60 s windows |
| `xTemperatureSwing_UsingFallbackChannel` | BOOL | TRUE if Monitor Temperature is being used instead of Body |

## Extreme / overshoot detection

| Variable | Type | Description |
|---|---|---|
| `xTemperatureSwing_ExtremeReached` | BOOL | Extreme reached/passed in commanded direction |
| `rTemperatureSwing_Overshoot` | REAL | Current overshoot past extreme, degC |
| `rTemperatureSwing_MaxOvershoot` | REAL | Max overshoot observed this cycle, degC |
| `xTemperatureSwing_OvershootExceeded` | BOOL | TRUE if overshoot > 11 degC (logged, non-aborting) |

## Pressure control

| Variable | Type | Description |
|---|---|---|
| `rTemperatureSwing_EstablishedPressure` | REAL | Target pressure once established, psi |
| `xTemperatureSwing_PressureReady` | BOOL | Pressure established and stable |
| `rTemperatureSwing_PressureError` | REAL | Current pressure minus target, psi |

## Timers

| Variable | Type | Description |
|---|---|---|
| `iTemperatureSwing_HoldTimer` | INT | Hold countdown, seconds |
| `tTemperatureSwing_RampStartTime` | TIME | Timestamp RAMP state entered |
| `tTemperatureSwing_CycleStartTime` | TIME | Timestamp cycle started |

## Logging

| Variable | Type | Description |
|---|---|---|
| `sTemperatureSwing_LogFile` | STRING(255) | CSV file path for this run |
| `xTemperatureSwing_LoggingActive` | BOOL | Logging in progress |
| `iTemperatureSwing_DataPoints` | INT | Data points written this run |

## Errors

| Variable | Type | Description |
|---|---|---|
| `xTemperatureSwing_Error` | BOOL | Test encountered an error |
| `sTemperatureSwing_ErrorMessage` | STRING(255) | Error description |
| `iTemperatureSwing_ErrorCode` | INT | Numeric error code |

---

## OPC UA Node ID convention

All variables are exposed under `ns=3;s="GVL"."<VariableName>"`. See
[`backend/config_temperature_swing.py`](../backend/config_temperature_swing.py)
for the full Python-side node map.
