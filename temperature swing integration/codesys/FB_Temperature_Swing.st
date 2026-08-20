FUNCTION_BLOCK FB_Temperature_Swing
// ============================================================================
// DRAFT V2 — structure only, states not yet implemented.
// Confirmed against real project code (FB_Hold, FB_Apply_Test_Pressure,
// FB_Pressure_Release, FB_EStop, FB_CSV_Handler):
//   - Isolate convention: TRUE = closed, FALSE = open ("Normally Open").
//   - FB_Apply_Test_Pressure has no inputs, fills via doUpstream, closes once
//     at the high alarm — it never re-opens, so it cannot relieve pressure
//     that keeps rising afterwards (e.g. from heating). No existing FB does
//     that either; the vent logic below is new, built on the same bang-bang
//     convention as FB_Apply_Test_Pressure / FB_Pressure_Release.
//   - CSV recording starts/stops automatically off GVL.xStart / GVL.xSave
//     (FB_CSV_Handler.IDLE) — nothing to trigger explicitly here.
//   - Monitor channel: reuse GVL.iMainChannelIndex directly, same as FB_Hold.
//   - Hold period: INT minutes, converted with DINT_TO_TIME(*60000), same as
//     FB_Hold's iHoldPeriod — not TIME, not REAL.
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
	fbTarget				: FB_Temperature_Target;    // ramp direction / reached helper
	rMonitorValue			: LREAL;
	rCurrentRate			: LREAL;
	RateWindowTimer			: TON;                      // 30 s rate window
	HoldTimer				: TON;
END_VAR

// ============================================================================
// CONTINUOUS — runs every scan from state 1 onward, independent of state
// ============================================================================
IF GVL.iTestPressure > 0 AND iStep >= 1 THEN
	// Fill: existing FB, closes doUpstream once at the high alarm.
	fbApplyPressure();

	// Relieve: NEW logic, not an existing FB. Same bang-bang convention —
	// open downstream while over the high alarm (thermal expansion venting),
	// close once back in band. Modelled on FB_Pressure_Release's pattern but
	// against the upper alarm instead of a low one.
	IF GVL.alrChannelReading[1] > GVL.aiAlarms[1] THEN
		GVL.doDownstream := FALSE; // open, vent excess
	ELSE
		GVL.doDownstream := TRUE;  // closed, hold
	END_IF
END_IF

// Monitor channel + rate, sampled continuously.
rMonitorValue := GVL.alrChannelReading[GVL.iMainChannelIndex];
// TODO: 30 s rate window calculation -> rCurrentRate (°C/min)

// ============================================================================
// STATE MACHINE
// ============================================================================
CASE iStep OF

	// 0: IDLE
	// Wait for operator Start.
	// Next: xStart TRUE → 1.
	// Reuse: GVL.sPrompt + xStart (FB_Hold step 0).
	0:
		GVL.sPrompt := 'Program: Temperature Swing. Press Start to begin.';
		// TODO: Transition on xStart

	// 1: STARTUP
	// Reset run data. If Test Pressure = 0, set vent-safe default
	// (Upstream closed, Downstream open).
	// Next: Test Pressure = 0 → 3, otherwise → 2.
	// Reuse: FB_Hold / FUN_Program_Startup pattern.
	1:
		xDone := FALSE;
		// TODO: Reset run data, set isolate defaults based on iTestPressure

	// 2: ESTABLISH_PRESSURE
	// Wait for chamber to reach alarm pressure before heating starts.
	// Next: fbApplyPressure.xDone → 3.
	// Reuse: FB_Apply_Test_Pressure.
	2:
		// TODO: Transition on fbApplyPressure.xDone

	// 3: CABINET_START
	// Start the temperature cabinet.
	// Next: start command issued → 4.
	// Reuse: GVL_HMI.xStartPulse relay path (EL2869 → Omron CPM1A).
	3:
		// TODO: Trigger cabinet startup, then move to state 4

	// 4: SEND_SETPOINT
	// Write operator setpoint to cabinet, arm fbTarget for ramp direction.
	// Next: write confirmed → 5.
	// Reuse: Modbus TCP gateway (regs 0,1,3,4); existing write/read-back pattern.
	4:
		fbTarget(xArm := TRUE, rSetpoint := GVL.rTemperatureSwing_Setpoint,
			rActual := rMonitorValue);
		// TODO: Modbus write to reg 0, pulse reg 1, wait for read-back on reg 3,
		//       check status on reg 4. Timeout 10s → state 9. Failure → state 9.

	// 5: RAMP
	// Cabinet ramps at its own natural rate. Pressure fill/relieve runs
	// continuously. Monitor channel shown white.
	// Next: fbTarget.xReached → 6.
	// Reuse: FB_Temperature_Target.
	5:
		GVL.sPrompt := 'Ramping to setpoint.';
		fbTarget(xArm := TRUE, rSetpoint := GVL.rTemperatureSwing_Setpoint,
			rActual := rMonitorValue);
		// TODO: Transition on fbTarget.xReached

	// 6: STABILISE
	// Wait for first 30 s window with |rate| < 0.5 °C/min.
	// Monitor channel shown orange.
	// Next: first passing window → 7.
	// Reuse: Rate calculated continuously above.
	6:
		GVL.sPrompt := 'Stabilising: waiting for rate below 0.5 degC/min.';
		// TODO: Check rCurrentRate every 30s window. Transition on first window < 0.5.

	// 7: HOLD
	// Hold at setpoint for the configured hold period.
	// Next: hold timer elapsed → 8.
	// Reuse: FB_Hold timer pattern (INT minutes via DINT_TO_TIME(*60000)).
	7:
		GVL.sPrompt := 'Holding at setpoint.';
		// TODO: Start/check hold timer, transition on elapsed.

	// 8: COMPLETE
	// Leave cabinet running, wait for save. CSV closes automatically.
	// Next: GVL.xSave → xDone, iStep := 0.
	// Reuse: FB_Hold save-then-stop pattern.
	8:
		GVL.sPrompt := 'Test complete — press End to finish.';
		// TODO: Transition on GVL.xSave, set xDone.

	// 9: ERROR
	// Hold the rig, wait for operator acknowledgement.
	// Next: acknowledged → xDone, iStep := 0.
	// Reuse: FB_Hold error pattern. E-stop handled centrally by ProgramSelecter.
	9:
		GVL.sPrompt := 'Temperature Swing error — press Stop.';
		// TODO: Transition on operator Stop (xStart FALSE), set xDone.

END_CASE
