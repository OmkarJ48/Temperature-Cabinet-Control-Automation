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

I've documented each state below with: what I need to implement, what existing code I can reuse, the condition that advances to the next state, and what I'm still unsure about.

### State 0: IDLE
**I need to:** Wait for the operator to start via the Start Dialog.  
**I can reuse:** `GVL.sPrompt` + `xStart` pattern (identical to FB_Hold step 0).  
**I move to state 1 when:** `xStart TRUE`  
**I'm unsure about:** Nothing — this is straightforward.

### State 1: DELAYED_START
**I need to:** Wait out any configured delayed-start time before the test begins.  
**I can reuse:** The existing delay-timer mechanism from PR2 or other programs (should already exist in the program-selector path).  
**I move to state 2 when:** The delay has elapsed (or none is configured).  
**I'm unsure about:** Which variable/FB actually owns this timer? The placeholder `DelayTimer(PT := T#0S)` needs the real source from PR2.

### State 2: STARTUP_AND_CSV_BEGIN
**I need to:** Reset run data, start CSV logging, and optionally set the zero-pressure solenoid state (Upstream closed, Downstream open).  
**I can reuse:** FB_Hold step 0/1 startup pattern; the existing CSV recording start call.  
**I move to state 3 or 4 when:** If `GVL.iTestPressure = 0`, skip to state 4; otherwise go to state 3.  
**I'm unsure about:** The exact CSV-start call signature and solenoid-set call signature.

### State 3: ESTABLISH_PRESSURE
**I need to:** Bring the chamber to the requested Test Pressure (skipped entirely if Test Pressure = 0).  
**I can reuse:** `FB_Apply_Test_Pressure` (proven in Hold/PR2 programs).  
**I move to state 4 when:** `fbApplyPressure.xDone` is true; I also compute the pressure-band limits at this point.  
**I'm unsure about:** Does `FB_Apply_Test_Pressure` expose timeout/error outputs (`xError`, `tTimeout`, enum)?

### State 4: CABINET_CONFIGURE_AND_START
**I need to:** Start the temperature cabinet.  
**I can reuse:** Relay-driven `xStartPulse` via EL2869 → Omron CPM1A (proven, commissioned).  
**I move to state 5 when:** The cabinet start command is sent (immediately; no wait currently).  
**I'm unsure about:** Should I wait for `GVL_HMI.xCabinetRunning` confirmation, or jump straight to state 5? The parent project notes that independent run feedback isn't yet wired.

### State 5: SEND_SETPOINT
**I need to:** Write the operator's temperature setpoint (positive or negative) to the cabinet.  
**I can reuse:** The existing Modbus TCP write/confirm sequence from the parent project (proven in PLC_PRG_TCP.st).  
**I move to state 6 when:** The setpoint write is confirmed via read-back match.  
**I'm unsure about:** Do all cabinet types (F4S vs F4T) use the same write/confirm mechanism? Do I need a timeout gate?

### State 6: RAMP_AND_SUPERVISE
**I need to:**
- Let the cabinet ramp toward the setpoint at its own natural rate (no artificial ramp control)
- Sample the selected monitor channel at 1 Hz
- If pressurised, supervise the 50–100% pressure band via solenoids
- Detect when the temperature reaches or passes the setpoint in the commanded direction

**I can reuse:** FB_Hold's TON-sampling pattern; direct `doUpstream`/`doDownstream` writes (same as `FB_Apply_Test_Pressure`).  
**I move to state 7 when:** The temperature has reached or passed the setpoint in the commanded direction.  
**I'm unsure about:**
- Which GVL index variable holds the selected channel? (I used placeholder `GVL.iTemperatureSwing_ChannelIndex`)
- How do I build the 60-second rolling buffer for the rate calculation?
- How do I compute `rCurrentRate` (°C/min) from that buffer?
- What's the exact logic for bang-bang pressure band supervision?

### State 7: STABILISING
**I need to:** Check if the rate of change is below 0.5 °C/min for 2 consecutive 60-second windows (per API 6A F.1.10).  
**I can reuse:** FB_Stability_Check's windowing concept (but it's pressure-only; I need to build this new for temperature rate).  
**I move to state 8 when:** I've detected 2 consecutive passing windows.  
**I'm unsure about:**
- How do I detect window transitions and track the 2-window debounce counter?
- Should pressure band supervision continue during stabilisation? (I'm assuming yes per spec, but haven't confirmed.)

### State 8: COMPLETE
**I need to:** Close CSV logging, leave the cabinet at the requested setpoint, and wait for the operator to save/stop.  
**I can reuse:** FB_Hold step 8/9 "await save then stop" pattern.  
**I move to state 0 when:** `GVL.xSave` is TRUE.  
**I'm unsure about:** Nothing — ambient-return behaviour (auto-shutoff at ambient) is explicitly out of scope per the kickoff doc.

### State 9: ERROR
**I need to:** Handle pressure-establishment failure/timeout (other faults are caught centrally by ProgramSelecter's E-stop).  
**I can reuse:** FB_Hold step 10 overpressure-handling pattern (adapted).  
**I move to state 0 when:** The operator acknowledges the error.  
**I'm unsure about:**
- What does `fbApplyPressure` expose on failure? (`xError`, `tTimeout`, enum `eFaultCode`?)
- Which state(s) should jump to ERROR? (Pressure timeout only, or also setpoint-write failures?)
- What flag should I check for acknowledgement? (`GVL.xSave` or a new flag?)

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
