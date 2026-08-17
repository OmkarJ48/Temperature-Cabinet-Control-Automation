# CODESYS — Temperature Swing

Structured Text source for the Temperature Swing test. These are source files
to be imported/merged into the main CODESYS project (`Device.export`) — they
are not a standalone project.

| File | Purpose |
|---|---|
| `GVL_TemperatureSwing.st` | New global variables (append to project GVL) |
| `E_TemperatureSwingState.st` | State enum used by the state machine |
| `FB_TemperatureSwing.st` | Main function block: state machine, rate calc, pressure control |

## Dependencies on existing project objects

These are **not included here** — they already exist in the main project and
are called by `FB_TemperatureSwing`:

- `FB_Apply_Test_Pressure` — pressure establishment
- `FB_Stabilisation_Check` — referenced pattern for rate/stabilisation logic
- `GVL.xAlarm_Active`, `GVL.tSystemTime`, `GVL.rChamberPressure_Current`,
  `GVL.rCabinetSetpoint_Command`, `GVL.rAmbientTemperature_Reference`,
  `GVL.rTestProfile_Pressure` — existing global variables
- `F_LogTemperatureSwingRow`, `F_BuildTemperatureSwingLogPath` — logging
  helpers following the existing CSV data-recorder pattern; implement using
  the same helper style as the current data logger POU.

## Import steps

1. Open `Device.export` in CODESYS.
2. Add `GVL_TemperatureSwing.st` variables to the project's main GVL (or add
   as a new GVL object — either is compatible with the OPC node paths in
   `../backend/config_temperature_swing.py`, which assume the default `"GVL"`
   namespace; update the node map if you use a separate GVL name).
3. Add `E_TemperatureSwingState.st` as a new DUT (enum type).
4. Add `FB_TemperatureSwing.st` as a new POU (function block), instantiate it
   in the automation task (same task that runs the other program POUs —
   `Automation (Core 3)` in the existing task configuration).
5. Wire `xEnable` to `xProgram_TemperatureSwing`, and wire
   `xSolenoid_Upstream` / `xSolenoid_Downstream` outputs to the existing
   physical solenoid channels used by other pressurised programs.
6. Build and resolve the two missing dependencies noted above if they are
   named differently in your project — the design doc lists them as reused
   patterns, not guaranteed identical symbol names.
