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

## FB_TemperatureSwing State Machine Breakdown

Each state below lists: what it does, what existing code it reuses, the condition that advances it, and any open questions.

### State 0: IDLE
**Does:** Wait for operator to start via Start Dialog.  
**Reuses:** `GVL.sPrompt` + `xStart` pattern (identical to FB_Hold step 0).  
**Next condition:** `xStart TRUE` → state 1  
**Unsure:** Nothing — straightforward.

### State 1: DELAYED_START
**Does:** Wait out configured delayed-start time before test begins.  
**Reuses:** Existing delay-timer from PR2 or other programs (should exist in program-selector path).  
**Next condition:** Delay elapsed (or none configured) → state 2  
**Unsure:** Which variable/FB owns the timer? Placeholder `DelayTimer(PT := T#0S)` needs real source from PR2.

### State 2: STARTUP_AND_CSV_BEGIN
**Does:** Reset run data, start CSV logging, optionally set zero-pressure solenoid state (Upstream closed, Downstream open).  
**Reuses:** FB_Hold step 0/1 startup pattern; existing CSV recording start call.  
**Next condition:** If `GVL.iTestPressure = 0` → state 4; else → state 3  
**Unsure:** Exact CSV-start call signature and solenoid-set call signature.

### State 3: ESTABLISH_PRESSURE
**Does:** Bring chamber to requested Test Pressure (skipped if Test Pressure = 0).  
**Reuses:** `FB_Apply_Test_Pressure` (proven in Hold/PR2).  
**Next condition:** `fbApplyPressure.xDone` → compute pressure-band limits, then state 4  
**Unsure:** Does `FB_Apply_Test_Pressure` expose timeout/error outputs (`xError`, `tTimeout`, enum)?

### State 4: CABINET_CONFIGURE_AND_START
**Does:** Start the temperature cabinet.  
**Reuses:** Relay-driven `xStartPulse` via EL2869 → Omron CPM1A (proven, commissioned).  
**Next condition:** Cabinet start commanded → state 5 (immediately; no wait)  
**Unsure:** Wait for `GVL_HMI.xCabinetRunning` confirmation, or jump straight? Parent project notes run feedback not yet wired.

### State 5: SEND_SETPOINT
**Does:** Write operator's temperature setpoint (positive or negative) to cabinet.  
**Reuses:** Existing Modbus TCP write/confirm sequence from parent project (proven in PLC_PRG_TCP.st).  
**Next condition:** Setpoint write confirmed (read-back match) → state 6  
**Unsure:** Same write/confirm for all cabinet types (F4S vs F4T)? Need timeout gate?

### State 6: RAMP_AND_SUPERVISE
**Does:**
- Cabinet ramps at own natural rate (no artificial ramp control)
- Sample selected monitor channel at 1 Hz
- If pressurised, supervise 50–100% pressure band via solenoids
- Detect when temperature reaches/passes setpoint in commanded direction

**Reuses:** FB_Hold's TON-sampling pattern; direct `doUpstream`/`doDownstream` writes (same as `FB_Apply_Test_Pressure`).  
**Next condition:** Temperature reached/passed setpoint in commanded direction → state 7  
**Unsure:**
- Which GVL index holds selected channel? (Placeholder: `GVL.iTemperatureSwing_ChannelIndex`)
- How to build 60-second rolling buffer for rate calc?
- How to compute `rCurrentRate` (°C/min) from buffer?
- Pressure band supervision bang-bang logic?

### State 7: STABILISING
**Does:** Check if rate of change is below 0.5 °C/min for 2 consecutive 60-second windows (per API 6A F.1.10).  
**Reuses:** FB_Stability_Check's windowing concept (but it's pressure-only; must build new for temperature rate).  
**Next condition:** 2 consecutive passing windows → state 8  
**Unsure:**
- How to detect window transitions and track 2-window debounce counter?
- Continue pressure band supervision during stabilisation? (Assumed yes, per spec.)

### State 8: COMPLETE
**Does:** Close CSV logging, leave cabinet at requested setpoint, wait for operator to save/stop.  
**Reuses:** FB_Hold step 8/9 "await save then stop" pattern.  
**Next condition:** `GVL.xSave TRUE` → set `xDone := TRUE`, reset `iStep := 0`  
**Unsure:** Nothing — ambient-return (auto-shutoff at ambient) explicitly out of scope per kickoff doc.

### State 9: ERROR
**Does:** Handle pressure-establishment failure/timeout (other faults caught centrally by ProgramSelecter's E-stop).  
**Reuses:** FB_Hold step 10 overpressure-handling pattern (adapted).  
**Next condition:** Operator acknowledges → set `xDone := TRUE`, reset `iStep := 0`  
**Unsure:**
- What does `fbApplyPressure` expose on failure? (`xError`, `tTimeout`, enum `eFaultCode`?)
- Which state(s) jump to ERROR? (Pressure timeout only, or also setpoint-write failures?)
- Acknowledgement flag? (`GVL.xSave` or new flag?)

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
