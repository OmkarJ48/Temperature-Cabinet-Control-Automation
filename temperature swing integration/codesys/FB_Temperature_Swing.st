FUNCTION_BLOCK FB_Temperature_Swing
// ============================================================================
// DRAFT V2 — structure only, states not yet implemented.
// Changes from V1 (per TL review):
//   1. Delayed start removed — handled by the Python frontend.
//   2. FB_Apply_Test_Pressure corrected: it has no inputs and works off
//      GVL.aiAlarms[1]. It is a continuous bang-bang block, not a one-shot.
//   3. Pressure supervision now runs every scan, outside the CASE, so
//      expanding gas can vent during ramp and stabilisation.
//   4. Stabilisation simplified: single 30 s window, first valid
//      < 0.5 degC/min result is enough (was 2 x 60 s).
//   5. Temperature target detection moved into FB_Temperature_Target to keep
//      this state machine simple.
// ============================================================================
VAR_INPUT
	xStart					: BOOL;
	iStep					: INT;
END_VAR
VAR_OUTPUT
	xDone					: BOOL;
END_VAR
VAR
	fbApplyPressure			: FB_Apply_Test_Pressure;   // no inputs, call every scan
	fbTarget				: FB_Temperature_Target;    // new small helper FB
	rMonitorValue			: LREAL;
	rCurrentRate			: LREAL;
	RateWindowTimer			: TON;                      // 30 s rate window
	HoldTimer				: TON;
END_VAR

// ============================================================================
// CONTINUOUS — runs every scan, independent of state
// ============================================================================
// Pressure supervision. FB_Apply_Test_Pressure vents via doUpstream whenever
// upstream exceeds the alarm value, so gas expanding with temperature is
// relieved rather than allowed to build. Only armed once a pressurised test
// is actually running (iStep >= 2 and Test Pressure > 0).
IF GVL.iTestPressure > 0 AND iStep >= 2 THEN
	fbApplyPressure();
END_IF

// Monitor channel + rate, sampled continuously so the value is already valid
// when the stabilisation state is entered.
rMonitorValue := GVL.alrChannelReading[GVL.iTemperatureSwing_ChannelIndex];
// TODO: 30 s window rate calculation -> rCurrentRate (degC/min)

// ============================================================================
// STATE MACHINE
// ============================================================================
CASE iStep OF

	// 0: IDLE
	// Does: wait for operator Start.
	// Next: xStart -> 1.
	// Reuse: GVL.sPrompt + xStart, same as FB_Hold step 0.
	0:
		GVL.sPrompt := 'Program: Temperature Swing. Press Start to begin.';
		IF xStart THEN
			iStep := 1;
		END_IF

	// 1: STARTUP
	// Does: reset run data, start CSV recording. If Test Pressure = 0, set the
	// vent-safe default (Upstream closed, Downstream open).
	// Next: Test Pressure = 0 -> 3, otherwise -> 2.
	// Reuse: FB_Hold startup pattern; existing CSV recorder trigger.
	1:
		xDone := FALSE;
		// TODO: CSV start; zero-pressure solenoid default
		IF GVL.iTestPressure = 0 THEN
			iStep := 3;
		ELSE
			iStep := 2;
		END_IF

	// 2: ESTABLISH_PRESSURE
	// Does: bring the chamber up to the alarm pressure before heating starts.
	// Next: fbApplyPressure.xDone -> 3.
	// Reuse: FB_Apply_Test_Pressure (already being called continuously above).
	2:
		IF fbApplyPressure.xDone THEN
			iStep := 3;
		END_IF

	// 3: CABINET_START
	// Does: start the temperature cabinet.
	// Next: start commanded -> 4.
	// Reuse: GVL_HMI.xStartPulse relay path (EL2869 -> Omron CPM1A).
	3:
		// TODO: GVL_HMI.xStartPulse := TRUE
		iStep := 4;

	// 4: SEND_SETPOINT
	// Does: write the operator setpoint to the cabinet and latch the ramp
	// direction in fbTarget.
	// Next: write confirmed -> 5.
	// Reuse: existing Modbus TCP setpoint write/read-back path.
	4:
		fbTarget(xArm := TRUE, rSetpoint := GVL.rTemperatureSwing_Setpoint,
			rActual := rMonitorValue);
		// TODO: Modbus setpoint write + read-back confirm
		iStep := 5;

	// 5: RAMP
	// Does: cabinet ramps at its own natural rate. Pressure vents continuously
	// via the block above. Monitor channel shown white on the HMI.
	// Next: fbTarget.xReached -> 6.
	// Reuse: FB_Temperature_Target handles the heating/cooling comparison.
	5:
		GVL.sPrompt := 'Ramping to setpoint.';
		fbTarget(xArm := TRUE, rSetpoint := GVL.rTemperatureSwing_Setpoint,
			rActual := rMonitorValue);
		IF fbTarget.xReached THEN
			iStep := 6;
		END_IF

	// 6: STABILISE
	// Does: wait for the first 30 s window with |rate| < 0.5 degC/min.
	// Monitor channel shown orange on the HMI.
	// Next: first passing window -> 7.
	// Reuse: rate is already calculated continuously above.
	6:
		GVL.sPrompt := 'Stabilising: waiting for rate below 0.5 degC/min.';
		RateWindowTimer(IN := TRUE, PT := T#30S);
		IF RateWindowTimer.Q THEN
			RateWindowTimer(IN := FALSE);
			IF ABS(rCurrentRate) < 0.5 THEN
				iStep := 7;
			END_IF
		END_IF

	// 7: HOLD
	// Does: hold at setpoint for the operator-configured hold time.
	// Next: hold elapsed -> 8.
	// Reuse: FB_Hold timer pattern.
	7:
		GVL.sPrompt := 'Holding at setpoint.';
		HoldTimer(IN := TRUE, PT := GVL.tTemperatureSwing_HoldTime);
		IF HoldTimer.Q THEN
			HoldTimer(IN := FALSE);
			iStep := 8;
		END_IF

	// 8: COMPLETE
	// Does: close CSV, leave the cabinet running at setpoint, wait for save.
	// Next: GVL.xSave -> xDone, iStep := 0.
	// Reuse: FB_Hold save-then-stop pattern.
	8:
		GVL.sPrompt := 'Test complete — press End to finish.';
		IF GVL.xSave THEN
			xDone := TRUE;
			iStep := 0;
		END_IF

	// 9: ERROR
	// Does: hold the rig and wait for operator acknowledgement.
	// Next: acknowledged -> xDone, iStep := 0.
	// Reuse: FB_Hold error pattern. E-stop is already handled centrally by
	// ProgramSelecter.
	9:
		GVL.sPrompt := 'Temperature Swing error — press Stop.';
		// TODO: acknowledgement / reset path

END_CASE
