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
	rRateWindowStart		: LREAL;                    // temperature at window start
	tScanCycle				: TIME := T#100MS;          // assumed scan time for rate calc
	SetpointWriteTimer		: TON;                      // Modbus write confirmation timeout
	xSetpointWriteArmed		: BOOL;                     // gate for one-time setpoint write
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

// Monitor channel + rate, sampled continuously so the value is already valid
// when the stabilisation state is entered.
rMonitorValue := GVL.alrChannelReading[GVL.iMainChannelIndex];

// Rate calculation: updated every 30 s window cycle in state 6.
// Rate = (delta over 30 s) / 0.5 min = delta * 2, in °C/min.
// Window start is captured when RateWindowTimer resets; rate is calculated
// when the next window completes (checked in state 6).
IF NOT RateWindowTimer.Q THEN
	// Window in progress: rate from previous complete window remains valid
	rCurrentRate := (rMonitorValue - rRateWindowStart) * 2.0; // delta * (1 min / 0.5 min)
ELSE
	// Window just completed: capture this reading for next window's calculation
	rRateWindowStart := rMonitorValue;
END_IF

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
	// Does: reset run data. If Test Pressure = 0, set the vent-safe default
	// (Upstream closed, Downstream open). CSV recording starts automatically
	// off GVL.xStart (FB_CSV_Handler) — nothing to call here.
	// Next: Test Pressure = 0 -> 3, otherwise -> 2.
	// Reuse: FB_Hold / FUN_Program_Startup pattern for isolate defaults.
	1:
		xDone := FALSE;
		xSetpointWriteArmed := FALSE;
		xWriteTrigger := FALSE;
		IF GVL.iTestPressure = 0 THEN
			GVL.doUpstream := TRUE;    // closed
			GVL.doDownstream := FALSE; // open — nothing to build, vent path clear
			iStep := 3;
		ELSE
			iStep := 2;
		END_IF

	// 2: ESTABLISH_PRESSURE
	// Does: wait for the chamber to reach the alarm pressure before heating
	// starts. Fill/relieve logic above is already running.
	// Next: fbApplyPressure.xDone -> 3.
	// Reuse: FB_Apply_Test_Pressure.
	2:
		IF fbApplyPressure.xDone THEN
			iStep := 3;
		END_IF

	// 3: CABINET_START
	// Does: start the temperature cabinet.
	// Next: start commanded -> 4.
	// Reuse: GVL_HMI.xStartPulse relay path (EL2869 -> Omron CPM1A).
	3:
		GVL_HMI.xStartPulse := TRUE;
		iStep := 4;

	// 4: SEND_SETPOINT
	// Does: write the operator setpoint to the cabinet and arm fbTarget with
	// the ramp direction.
	// Next: write confirmed -> 5.
	// Reuse: existing Modbus TCP setpoint write/read-back path (gateway regs 0,1,3,4).
	4:
		fbTarget(xArm := TRUE, rSetpoint := GVL.rTemperatureSwing_Setpoint,
			rActual := rMonitorValue);

		// Modbus TCP register map (from f4s_gateway.py):
		// Reg 0: write — Requested setpoint (×10, signed)
		// Reg 1: write — Apply trigger (pulse of 1; gateway clears it)
		// Reg 3: read — Confirmed setpoint read-back (×10, signed)
		// Reg 4: read — Status (0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS)

		// On first entry, arm the write and start the confirmation timeout
		IF NOT xSetpointWriteArmed THEN
			GVL_Modbus.wSetpoint1Write := INT_TO_WORD(REAL_TO_INT(GVL.rTemperatureSwing_Setpoint * 10.0));
			xWriteTrigger := TRUE;                      // pulse reg 1
			SetpointWriteTimer(IN := TRUE, PT := T#10S);
			xSetpointWriteArmed := TRUE;
		END_IF;

		// Wait for either confirmation (setpoint echoed back) or timeout
		IF SetpointWriteTimer.Q THEN
			// Timeout after 10 seconds
			SetpointWriteTimer(IN := FALSE);
			xSetpointWriteArmed := FALSE;
			iStep := 9;                                 // ERROR state
		ELSIF WORD_TO_INT(GVL_Modbus.wSetpoint1Read) = REAL_TO_INT(GVL.rTemperatureSwing_Setpoint * 10.0) THEN
			// Confirmation received: read-back matches requested value
			IF GVL_Modbus.wStatus = 0 THEN
				// Status OK, transition to RAMP
				SetpointWriteTimer(IN := FALSE);
				xSetpointWriteArmed := FALSE;
				iStep := 5;
			ELSIF GVL_Modbus.wStatus = 3 OR GVL_Modbus.wStatus = 4 THEN
				// Device rejected: NOT_ACCEPTED or RANGE
				SetpointWriteTimer(IN := FALSE);
				xSetpointWriteArmed := FALSE;
				iStep := 9;                             // ERROR state
			END_IF
		END_IF

	// 5: RAMP
	// Does: cabinet ramps at its own natural rate. Pressure fill/relieve runs
	// continuously above. Monitor channel shown white on the HMI.
	// Next: fbTarget.xReached -> 6.
	// Reuse: FB_Temperature_Target.
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
	// Reuse: rate already calculated continuously above.
	6:
		GVL.sPrompt := 'Stabilising: waiting for rate below 0.5 degC/min.';
		// On first entry to this state, capture the starting temperature for rate window
		IF RateWindowTimer.IN = FALSE THEN
			rRateWindowStart := rMonitorValue;
		END_IF;
		RateWindowTimer(IN := TRUE, PT := T#30S);
		IF RateWindowTimer.Q THEN
			RateWindowTimer(IN := FALSE);
			IF ABS(rCurrentRate) < 0.5 THEN
				iStep := 7;
			END_IF
		END_IF

	// 7: HOLD
	// Does: hold at setpoint for the operator-configured hold period.
	// Next: hold elapsed -> 8.
	// Reuse: FB_Hold timer pattern — INT minutes via DINT_TO_TIME(*60000).
	7:
		GVL.sPrompt := 'Holding at setpoint.';
		HoldTimer(IN := TRUE, PT := DINT_TO_TIME(GVL.iTemperatureSwing_HoldPeriod * 60000));
		IF HoldTimer.Q THEN
			HoldTimer(IN := FALSE);
			iStep := 8;
		END_IF

	// 8: COMPLETE
	// Does: leave the cabinet running at setpoint, wait for save. CSV closes
	// automatically off GVL.xSave (FB_CSV_Handler).
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
	// Reuse: FB_Hold overpressure-handling pattern. E-stop is already handled
	// centrally by ProgramSelecter / FB_EStop.
	9:
		GVL.sPrompt := 'Temperature Swing error — press Stop.';
		IF NOT xStart THEN
			xDone := TRUE;
			iStep := 0;
		END_IF

END_CASE
