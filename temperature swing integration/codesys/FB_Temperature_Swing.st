FUNCTION_BLOCK FB_Temperature_Swing
VAR_INPUT
	xStart					: BOOL;
	iStep                   : INT;
END_VAR
VAR_OUTPUT
	xDone					: BOOL;
END_VAR
VAR
	// Pressure establishment (reuses FB_Apply_Test_Pressure, same as Hold/PR2)
	fbApplyPressure			: FB_Apply_Test_Pressure;
	rTargetPressure			: LREAL;
	rPressureLow			: LREAL;    // 50% band floor during supervision
	rPressureHigh			: LREAL;    // 100% band ceiling during supervision

	// Rate calculation — new, no existing FB does this for temperature
	// (FB_Stability_Check is pressure-only, confirmed by inspection)
	rMonitorValue			: LREAL;
	rMonitorValue_60sAgo	: LREAL;
	rCurrentRate			: LREAL;
	iConsecutivePassWindows	: INT;
	RateWindowTimer			: TON;

	// Setpoint reached/passed tracking
	xSetpointReached		: BOOL;
	xHeating				: BOOL;     // TRUE if setpoint > temp at start of ramp

	// Timers
	DelayTimer				: TON;
	HoldTimer				: TON;    // Hold duration countdown (state 8)
END_VAR

// Main state machine
CASE iStep OF

	//=========================================================
	// 0: IDLE
	//=========================================================
	// Does: wait for operator start via Start Dialog.
	// Reuse: GVL.sPrompt + xStart pattern, same as FB_Hold step 0.
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
	// Reuse: existing delayed-start behaviour used by other programs — Start
	// Dialog already has a Delayed Start field, so the timer/mechanism should
	// already exist somewhere in the program-selector path.
	// Next: delay elapsed (or none configured) -> 2 (STARTUP_AND_CSV_BEGIN).
	// Unsure: which existing FB/variable actually owns this timer — needs
	// locating in the program-selector code before this state can be filled in.
	1:
		DelayTimer(IN := TRUE, PT := T#0S);   // placeholder PT, see note above
		IF DelayTimer.Q THEN
			DelayTimer(IN := FALSE);
			iStep := 2;
		END_IF

	//=========================================================
	// 2: STARTUP_AND_CSV_BEGIN
	//=========================================================
	// Does: normal program startup (reset run data), begin existing CSV
	// recording. If Test Pressure = 0 psi, also set the zero-pressure default
	// solenoid state (Upstream closed, Downstream open) here so the test
	// article can't build pressure as temperature changes.
	// Reuse: FB_Hold step 0/1 startup pattern; existing CSV recording start,
	// triggered the same way other programs trigger it on Start.
	// Next: startup + CSV open both confirmed -> 3 (ESTABLISH_PRESSURE), or
	// straight to 4 (CABINET_CONFIGURE_AND_START) if Test Pressure = 0.
	// Unsure: exact CSV-start call/trigger used by other programs — haven't
	// located the specific line yet.
	2:
		xDone := FALSE;
		IF GVL.iTestPressure = 0 THEN
			// TODO: doUpstream := FALSE, doDownstream := TRUE (zero-pressure default)
			iStep := 4;
		ELSE
			iStep := 3;
		END_IF

	//=========================================================
	// 3: ESTABLISH_PRESSURE
	//=========================================================
	// Does: bring chamber to Test Pressure (skipped entirely at step 2 if
	// Test Pressure = 0).
	// Reuse: FB_Apply_Test_Pressure, unmodified — same block Hold/PR2 use,
	// and the same approach the existing 5 to 10% PR2 program uses.
	// Next: fbApplyPressure.xDone -> 4 (CABINET_CONFIGURE_AND_START).
	// Unsure: FB_Apply_Test_Pressure's timeout/error behaviour — need to
	// confirm what it exposes on failure so state 10 can react to it.
	3:
		fbApplyPressure(xStart := TRUE, rTarget := GVL.iTestPressure);
		IF fbApplyPressure.xDone THEN
			rPressureLow  := GVL.iTestPressure * 0.5;
			rPressureHigh := GVL.iTestPressure * 1.0;
			iStep := 4;
		END_IF

	//=========================================================
	// 4: CABINET_CONFIGURE_AND_START
	//=========================================================
	// Does: start the temperature cabinet.
	// Reuse: existing cabinet on/off control from the parent Temperature
	// Cabinet Control project (relay-driven xStartPulse via EL2869 -> Omron
	// CPM1A, proven and commissioned).
	// Next: cabinet start commanded -> 5 (SEND_SETPOINT).
	// Unsure: whether to wait for a run-confirmation before proceeding, or
	// move straight on — there's no independent run feedback wired back from
	// the Omron yet (parent project README notes this as open).
	4:
		// TODO: GVL_HMI.xStartPulse := TRUE (reuse existing cabinet start)
		iStep := 5;

	//=========================================================
	// 5: SEND_SETPOINT
	//=========================================================
	// Does: write the operator's temperature setpoint (positive or negative)
	// to the cabinet.
	// Reuse: this project's existing setpoint write path (the proven
	// Modbus TCP register write/confirm sequence from the parent project).
	// Next: setpoint write confirmed -> 6 (RAMP_AND_SUPERVISE).
	// Unsure: whether every cabinet on the fleet uses the same write/confirm
	// mechanism, or if this needs to branch per cabinet controller type.
	5:
		xHeating := (GVL.rTemperatureSwing_Setpoint > rMonitorValue);
		// TODO: write GVL.rTemperatureSwing_Setpoint to cabinet, same
		// pattern as existing setpoint-write path
		iStep := 6;

	//=========================================================
	// 6: RAMP_AND_SUPERVISE
	//=========================================================
	// Does: cabinet ramps toward setpoint at its own natural rate (no
	// artificial ramp-rate control, per spec); sample the selected monitor
	// channel at 1 Hz; if pressurised, supervise the 50-100% band in
	// parallel using the upstream/downstream solenoids.
	// Reuse: FB_Hold's TON-sampling pattern, adapted to build a 60 s window;
	// direct doUpstream/doDownstream writes, same pattern FB_Apply_Test_Pressure
	// uses, for band supervision.
	// Next: setpoint reached or passed in the commanded direction -> 7
	// (STABILISING). Highlight the monitor channel white while in this state.
	// Unsure: which of the 5 selectable channels the operator picked needs a
	// confirmed GVL index/lookup — using GVL.iTemperatureSwing_ChannelIndex
	// as a placeholder name below.
	6:
		rMonitorValue := GVL.alrChannelReading[GVL.iTemperatureSwing_ChannelIndex];
		GVL.sPrompt := CONCAT5(
			'Temperature ramp to ',
			REAL_TO_STRF(GVL.rTemperatureSwing_Setpoint, 1, '.'),
			' degC. Target range: ',
			REAL_TO_STRF(GVL.rTemperatureSwing_Setpoint, 1, '.'),
			' degC to ...'
		);
		// TODO: 1 Hz sample into 60 s rolling buffer, compute rCurrentRate
		// TODO: IF GVL.iTestPressure > 0, supervise doUpstream/doDownstream
		// between rPressureLow and rPressureHigh (bang-bang, same idea as
		// FB_Apply_Test_Pressure)

		IF xHeating THEN
			xSetpointReached := (rMonitorValue >= GVL.rTemperatureSwing_Setpoint);
		ELSE
			xSetpointReached := (rMonitorValue <= GVL.rTemperatureSwing_Setpoint);
		END_IF

		IF xSetpointReached THEN
			iStep := 7;
		END_IF

	//=========================================================
	// 7: STABILISING
	//=========================================================
	// Does: check |rate| < 0.5 degC/min for 2 consecutive 60 s windows, per
	// API 6A F.1.10. Highlight the monitor channel orange while in this state.
	// Reuse: conceptually similar to FB_Stability_Check's windowing idea, but
	// must be built new — same reasoning as step 6. Pressure band supervision
	// (if pressurised) is assumed to keep running through this state too.
	// Next: 2 consecutive passing windows -> 8 (HOLD).
	// Unsure: whether pressure supervision really should keep running here —
	// assumed yes (spec says "during the swing", stabilising is still part of
	// the swing) but not explicitly confirmed.
	7:
		GVL.sPrompt := 'Stabilising: waiting for rate of change below 0.5 degC/min.';
		// TODO: 2-window debounce check on rCurrentRate -> iConsecutivePassWindows
		// TODO: keep pressure band supervision running if GVL.iTestPressure > 0
		IF iConsecutivePassWindows >= 2 THEN
			iStep := 8;
		END_IF

	//=========================================================
	// 8: HOLD
	//=========================================================
	// Does: hold the cabinet at the requested setpoint for the configured hold
	// time (per API 6A — operator specifies hold duration in Start Dialog).
	// Reuse: FB_Hold's timer pattern for the hold duration countdown.
	// Next: hold time elapsed -> 9 (COMPLETE).
	// Unsure: should I continue rate monitoring during the hold, or is the test
	// considered "stabilised" once I exit state 7?
	8:
		HoldTimer(IN := TRUE, PT := GVL.rTemperatureSwing_HoldTime);
		GVL.sPrompt := CONCAT3('Holding at setpoint. Time remaining: ',
			REAL_TO_STRF(HoldTimer.ET / T#1S, 0, '.'), ' seconds.');
		// TODO: decide if rate monitoring should continue during hold
		IF HoldTimer.Q THEN
			HoldTimer(IN := FALSE);
			iStep := 9;
		END_IF

	//=========================================================
	// 9: COMPLETE
	//=========================================================
	// Does: close CSV, leave cabinet running at the requested setpoint (no
	// auto-vent, no auto-shutoff) and wait for the operator to stop/save.
	// Reuse: FB_Hold step 8/9 "await save then stop" pattern.
	// Next: GVL.xSave -> xDone TRUE, iStep := 0.
	// Unsure: ambient-return behaviour (switching the cabinet off once the
	// valve reaches ambient) is explicitly out of scope for this skeleton per
	// the kick-off doc — "a sensible ambient-detection method should be
	// proposed before implementation" — so it isn't handled here yet.
	9:
		GVL.sPrompt := 'Stabilised. Test complete — press End to finish.';
		IF GVL.xSave THEN
			xDone := TRUE;
			iStep := 0;
		END_IF

	//=========================================================
	// 10: ERROR
	//=========================================================
	// Does: handle pressure-establishment failure/timeout (any other fault is
	// already caught centrally by ProgramSelecter's E-stop gate before this
	// FB ever runs).
	// Reuse: FB_Hold's error-handling pattern, adapted.
	// Next: operator acknowledges -> xDone TRUE, iStep := 0.
	// Unsure: what fbApplyPressure exposes on failure — no error/timeout
	// output confirmed yet, so this state can't be filled in properly until
	// that's checked.
	10:
		GVL.sPrompt := 'Temperature Swing error — see message and press Stop.';
		// TODO: fault acknowledgement / reset path

END_CASE
