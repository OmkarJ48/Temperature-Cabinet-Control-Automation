FUNCTION_BLOCK FB_Temperature_Target
// ============================================================================
// DRAFT V2 — small reusable helper.
// Latches the ramp direction on arming, then reports when the temperature has
// reached or passed the setpoint in that direction. Keeps the heating/cooling
// comparison out of the main Temperature Swing state machine, and is reusable
// by any future program that ramps to a temperature.
// ============================================================================
VAR_INPUT
	xArm					: BOOL;     // TRUE from the setpoint write onwards
	rSetpoint				: LREAL;
	rActual					: LREAL;
END_VAR
VAR_OUTPUT
	xReached				: BOOL;
	xHeating				: BOOL;     // latched direction, for HMI/logging
END_VAR
VAR
	xArmed					: BOOL;
END_VAR

IF NOT xArm THEN
	xArmed   := FALSE;
	xReached := FALSE;
ELSE
	// Latch direction once, on the first scan after arming.
	IF NOT xArmed THEN
		xHeating := (rSetpoint > rActual);
		xArmed   := TRUE;
	END_IF

	IF xHeating THEN
		xReached := (rActual >= rSetpoint);
	ELSE
		xReached := (rActual <= rSetpoint);
	END_IF
END_IF
