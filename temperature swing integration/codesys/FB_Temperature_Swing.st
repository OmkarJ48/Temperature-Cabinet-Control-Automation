FUNCTION_BLOCK FB_Temperature_Swing
VAR_INPUT
	xStart					: BOOL;
	iStep                   : INT;
END_VAR
VAR_OUTPUT
	xDone					: BOOL;
END_VAR
VAR
	// Pressure establishment (Step 3)
	fbApplyPressure			: FB_Apply_Test_Pressure;
	rTargetPressure			: LREAL;

	// Rate calculation (Step 6/7) — NEW, no existing FB does this for temperature
	rMonitorValue			: LREAL;
	rMonitorValue_60sAgo	: LREAL;
	rCurrentRate			: LREAL;
	iConsecutivePassWindows	: INT;
	RateWindowTimer			: TON;

	// Setpoint reach / target range tracking (Step 6)
	xSetpointReached		: BOOL;
	rTargetRangeMin			: LREAL;
	rTargetRangeMax			: LREAL;

	// Timers
	DelayTimer				: TON;
END_VAR

// Main state machine
CASE iStep OF

	//=========================================================
	// 0: IDLE
	//=========================================================
	// Does: wait for operator start via Start Dialog.
	// Reuse: GVL.sPrompt pattern + xStart check, same as FB_Hold step 0.
	// Next: xStart TRUE -> 1 (DELAYED_START).
	// Unsure: nothing at this state.
	0:
		GVL.sPrompt := 'Program: Temperature Swing. Press the Start button to begin.';
		IF xStart THEN
			iStep := 1;
		END_IF

	//=========================================================
	// 1: DELAYED_START
	//=========================================================
	// Does: wait out any configured delayed-start time before the test begins.
	// Reuse: intend to reuse PR2's existing "Delayed Start Time" timer/pattern.
	// Next: delay elapsed (or no delay configured) -> 2 (STARTUP_AND_CSV_BEGIN).
	// Unsure: haven't seen PR2's delayed-start source yet, so this is a
	// placeholder DelayTimer only — needs the real FB/variable name confirmed.
	1:
		DelayTimer(IN := TRUE, PT := T#0S);   // placeholder PT, see note above
		IF DelayTimer.Q THEN
			DelayTimer(IN := FALSE);
			iStep := 2;
		END_IF

	//=========================================================
	// 2: STARTUP_AND_CSV_BEGIN
	//=========================================================
	// Does: normal program startup (reset run data), open CSV logging.
	// Reuse: FB_Hold step 1 startup pattern; Historical_CSV / FB_CSV_Handler /
	// FB_Buffer_Data for the CSV open call.
	// Next: startup + CSV open both confirmed -> 3 (ESTABLISH_PRESSURE), or
	// skip straight to 4 (CABINET_CONFIGURE_AND_START) if pressure mode = 0.
	// Unsure: exact FB_CSV_Handler call signature for opening a log file —
	// haven't seen that code yet.
	2:
		xDone := FALSE;
		IF GVL.iTempSwing_PressureMode = 0 THEN
			iStep := 4;
		ELSE
			iStep := 3;
		END_IF

	//=========================================================
	// 3: ESTABLISH_PRESSURE
	//=========================================================
	// Does: bring chamber to target pressure (skipped entirely at step 2 if
	// pressure mode = 0).
	// Reuse: FB_Apply_Test_Pressure, unmodified, same block Hold/PR2 use.
	// Next: fbApplyPressure.xDone -> 4 (CABINET_CONFIGURE_AND_START).
	// Unsure: FB_Apply_Test_Pressure's exact timeout/error output — assumed
	// ~300 s from the design doc but not confirmed against the FB itself.
	3:
		rTargetPressure := GVL.iTestPressure * (GVL.iTempSwing_PressureMode / 100);
		fbApplyPressure(xStart := TRUE, rTarget := rTargetPressure);
		IF fbApplyPressure.xDone THEN
			iStep := 4;
		END_IF

	//=========================================================
	// 4: CABINET_CONFIGURE_AND_START
	//=========================================================
	// Does: configure and start the temperature cabinet.
	// Reuse: unknown — haven't seen the existing cabinet on/off code yet.
	// Next: cabinet confirms running/ready -> 5 (SEND_SETPOINT).
	// Unsure: this is the biggest gap — need the existing cabinet start
	// FB/variable from the parent setpoint-control work before this state
	// can be more than a stub.
	4:
		// TODO: call existing cabinet start/enable logic here
		iStep := 5;

	//=========================================================
	// 5: SEND_SETPOINT
	//=========================================================
	// Does: write the operator setpoint (positive or negative) to the cabinet.
	// Reuse: this repo's existing setpoint write path.
	// Next: setpoint write confirmed -> 6 (RAMP_AND_SUPERVISE).
	// Unsure: how setpoint write is acknowledged (single-shot write vs. a
	// confirm/echo flag) — not yet confirmed.
	5:
		// TODO: write GVL.rTempSwing_SetpointCommand to cabinet
		iStep := 6;

	//=========================================================
	// 6: RAMP_AND_SUPERVISE
	//=========================================================
	// Does: cabinet ramps toward setpoint at its natural rate; sample the
	// selected monitor channel at 1 Hz for the rate calc; if pressurised,
	// supervise the 50-100% band in parallel.
	// Reuse: FB_Hold's TON-sampling pattern, adapted to a 60 s window;
	// direct doUpstream/doDownstream writes (same pattern FB_Apply_Test_Pressure
	// uses) for band supervision.
	// New: the rate calculation itself — FB_Stability_Check is pressure-only,
	// confirmed by inspection, so this can't be reused directly for temperature.
	// Next: setpoint reached or passed in the commanded direction -> 7 (STABILISING).
	// Unsure: exact "reached or passed" comparison needs a heating/cooling
	// sign check, and I haven't confirmed which channel holds the live
	// setpoint-tracking value vs. the five selectable monitor channels.
	6:
		rMonitorValue := GVL.alrChannelReading[GVL.iTempSwing_MonitorChannel + 18];
		// TODO: 60 s rolling buffer + rate calc (rCurrentRate)
		// TODO: pressure band supervision if GVL.iTempSwing_PressureMode <> 0
		IF xSetpointReached THEN
			iStep := 7;
		END_IF

	//=========================================================
	// 7: STABILISING
	//=========================================================
	// Does: check |rate| < 0.5 degC/min for 2 consecutive 60 s windows.
	// Reuse: conceptually similar to FB_Stability_Check's windowing idea, but
	// must be built new — same reasoning as step 6.
	// Next: 2 consecutive passing windows -> 8 (COMPLETE).
	// Unsure: whether pressure band supervision should keep running here too
	// — assumed yes, not yet confirmed with the design doc's wording.
	7:
		// TODO: 2-window debounce check on rCurrentRate
		IF iConsecutivePassWindows >= 2 THEN
			iStep := 8;
		END_IF

	//=========================================================
	// 8: COMPLETE
	//=========================================================
	// Does: close CSV, leave cabinet running at setpoint (no auto-vent,
	// no auto-shutoff), wait for operator to stop/save.
	// Reuse: FB_Hold step 8/9 "await save then stop" pattern.
	// Next: GVL.xSave or GVL.xTempSwing_Stop -> xDone TRUE, iStep := 0.
	// Unsure: which flag ProgramSelecter expects here — xSave (like FB_Hold)
	// or a Temperature-Swing-specific stop flag — needs confirming.
	8:
		GVL.sPrompt := 'Stabilised. Test complete — press End to finish.';
		IF GVL.xSave THEN
			xDone := TRUE;
			iStep := 0;
		END_IF

	//=========================================================
	// 9: ERROR
	//=========================================================
	// Does: handle pressure-establishment failure/timeout (any other fault
	// is already caught centrally by ProgramSelecter's E-stop gate before
	// this FB ever runs).
	// Reuse: FB_Hold step 10 overpressure-handling pattern, adapted.
	// Next: operator acknowledges -> xDone TRUE, iStep := 0.
	// Unsure: what fbApplyPressure exposes on failure — no error/timeout
	// output confirmed yet, so this state can't be filled in properly until
	// that's checked.
	9:
		GVL.sPrompt := 'Temperature Swing error — see message and press Stop.';
		// TODO: fault acknowledgement / reset path

END_CASE
