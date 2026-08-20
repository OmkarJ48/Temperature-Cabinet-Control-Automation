{attribute 'qualified_only'}
FUNCTION_BLOCK FB_TemperatureSwing
(*
    Temperature Swing test state machine — API 6A F.1.9 / F.1.10 / F.1.11.

    Reuses FB_Apply_Test_Pressure for pressure establishment and the existing
    upstream/downstream solenoid pattern for pressure maintenance during the
    ramp/hold/return. See docs/Stage2_Design_Document.md for the full design
    and state diagram.
*)
VAR_INPUT
    xEnable             : BOOL;    // TRUE while xProgram_TemperatureSwing selected
END_VAR

VAR_OUTPUT
    xSolenoid_Upstream   : BOOL;
    xSolenoid_Downstream : BOOL;
END_VAR

VAR
    fbApplyPressure      : FB_Apply_Test_Pressure;
    fbStabilisationCheck : FB_Stabilisation_Check;
    tonRateWindow        : TON;    // 60 s rate-of-change window
    tonPressureTimeout   : TON;    // 300 s pressure establishment timeout
    tonHoldTimer         : TON;
    iRateSampleIndex     : INT;
    rRateBuffer          : ARRAY[0..59] OF REAL; // 1 Hz ring buffer, 60 s deep
END_VAR

// ============================================================================
// Safety exit — valid from any state
// ============================================================================
IF xTemperatureSwing_Stop OR GVL.xAlarm_Active THEN
    iTemperatureSwing_CurrentState := E_TemperatureSwingState.IDLE;
    xTemperatureSwing_Active := FALSE;
    xSolenoid_Upstream := FALSE;
    xSolenoid_Downstream := FALSE;
    tonHoldTimer(IN := FALSE);
    IF xTemperatureSwing_LoggingActive THEN
        sTemperatureSwing_ErrorMessage := 'Aborted by operator or alarm';
        F_LogTemperatureSwingRow(sTemperatureSwing_LogFile, 'ABORTED');
        xTemperatureSwing_LoggingActive := FALSE;
    END_IF;
    RETURN;
END_IF;

// ============================================================================
// Rate-of-change sampling (1 Hz), independent of state so it is always fresh
// ============================================================================
rRateBuffer[iRateSampleIndex] := rBodyTemp_Current;
iRateSampleIndex := (iRateSampleIndex + 1) MOD 60;
rBodyTemp_Previous_60s := rRateBuffer[iRateSampleIndex]; // oldest sample = 60 s ago

tonRateWindow(IN := xTemperatureSwing_Active, PT := T#60S);
IF tonRateWindow.Q THEN
    tonRateWindow(IN := FALSE);
    rTemperatureSwing_Rate := (rBodyTemp_Current - rBodyTemp_Previous_60s); // degC/min, window = 1 min
    IF ABS(rTemperatureSwing_Rate) < 0.5 THEN
        xTemperatureSwing_RateCheckPassed := TRUE;
        iTemperatureSwing_ConsecutivePassWindows := iTemperatureSwing_ConsecutivePassWindows + 1;
    ELSE
        xTemperatureSwing_RateCheckPassed := FALSE;
        iTemperatureSwing_ConsecutivePassWindows := 0;
    END_IF;
    F_LogTemperatureSwingRow(sTemperatureSwing_LogFile, 'RATE_SAMPLE');
END_IF;

// ============================================================================
// Pressure maintenance — active in RAMP..HOLD_EXTREME, closed-loop bang-bang
// ============================================================================
IF xTemperatureSwing_PressureReady AND xTemperatureSwing_Active THEN
    rTemperatureSwing_PressureError := rTemperatureSwing_EstablishedPressure - GVL.rChamberPressure_Current;
    IF rTemperatureSwing_PressureError > 0.5 THEN
        xSolenoid_Upstream := TRUE;
        xSolenoid_Downstream := FALSE;
    ELSIF rTemperatureSwing_PressureError < -0.5 THEN
        xSolenoid_Upstream := FALSE;
        xSolenoid_Downstream := TRUE;
    ELSE
        xSolenoid_Upstream := FALSE;
        xSolenoid_Downstream := FALSE;
    END_IF;
ELSE
    xSolenoid_Upstream := FALSE;
    xSolenoid_Downstream := FALSE;
END_IF;

// ============================================================================
// State machine
// ============================================================================
CASE iTemperatureSwing_CurrentState OF

    E_TemperatureSwingState.IDLE:
        xTemperatureSwing_Active := FALSE;
        IF xEnable AND xTemperatureSwing_Start THEN
            tTemperatureSwing_CycleStartTime := GVL.tSystemTime;
            sTemperatureSwing_LogFile := F_BuildTemperatureSwingLogPath(rTemperatureSwing_Extreme);
            xTemperatureSwing_LoggingActive := TRUE;
            iTemperatureSwing_DataPoints := 0;
            rTemperatureSwing_MaxOvershoot := 0.0;
            xTemperatureSwing_OvershootExceeded := FALSE;
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.START;
        END_IF;

    E_TemperatureSwingState.START:
        xTemperatureSwing_Active := TRUE;
        // Establish pressure before any ramp begins
        fbApplyPressure(
            rTargetPressure := (rTemperatureSwing_PressureMode / 100.0) * GVL.rTestProfile_Pressure,
            xStart          := TRUE);
        tonPressureTimeout(IN := TRUE, PT := T#300S);

        IF fbApplyPressure.xDone THEN
            fbApplyPressure(xStart := FALSE);
            tonPressureTimeout(IN := FALSE);
            rTemperatureSwing_EstablishedPressure := (rTemperatureSwing_PressureMode / 100.0) * GVL.rTestProfile_Pressure;
            xTemperatureSwing_PressureReady := TRUE;
            tTemperatureSwing_RampStartTime := GVL.tSystemTime;
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.RAMP;
        ELSIF fbApplyPressure.xError OR tonPressureTimeout.Q THEN
            xTemperatureSwing_Error := TRUE;
            sTemperatureSwing_ErrorMessage := 'Pressure establishment failed or timed out';
            iTemperatureSwing_ErrorCode := 1001;
            F_LogTemperatureSwingRow(sTemperatureSwing_LogFile, 'ERROR_PRESSURE');
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.IDLE;
        END_IF;

    E_TemperatureSwingState.RAMP:
        GVL.rCabinetSetpoint_Command := rTemperatureSwing_Extreme; // drives cabinet via existing setpoint-write path
        iTemperatureSwing_CurrentState := E_TemperatureSwingState.MONITOR_RATE;

    E_TemperatureSwingState.MONITOR_RATE:
        IF iTemperatureSwing_ConsecutivePassWindows >= 2 THEN
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.APPROACH_EXTREME;
        END_IF;

    E_TemperatureSwingState.APPROACH_EXTREME:
        IF ABS(rBodyTemp_Current - rTemperatureSwing_Extreme) <= 2.0 THEN
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.VERIFY_EXTREME;
        END_IF;

    E_TemperatureSwingState.VERIFY_EXTREME:
        IF (rTemperatureSwing_Extreme >= 0.0 AND rBodyTemp_Current >= rTemperatureSwing_Extreme) OR
           (rTemperatureSwing_Extreme <  0.0 AND rBodyTemp_Current <= rTemperatureSwing_Extreme) THEN
            xTemperatureSwing_ExtremeReached := TRUE;
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.STABILISE;
        END_IF;

    E_TemperatureSwingState.STABILISE:
        rTemperatureSwing_Overshoot := ABS(rBodyTemp_Current - rTemperatureSwing_Extreme);
        rTemperatureSwing_MaxOvershoot := MAX(rTemperatureSwing_MaxOvershoot, rTemperatureSwing_Overshoot);
        IF xTemperatureSwing_RateCheckPassed THEN
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.OVERSHOOT_CHECK;
        END_IF;

    E_TemperatureSwingState.OVERSHOOT_CHECK:
        IF rTemperatureSwing_MaxOvershoot > 11.0 THEN
            xTemperatureSwing_OvershootExceeded := TRUE; // logged, non-aborting per design
            F_LogTemperatureSwingRow(sTemperatureSwing_LogFile, 'OVERSHOOT_EXCEEDED');
        END_IF;
        iTemperatureSwing_HoldTimer := TO_INT(rTemperatureSwing_HoldTime * 60.0);
        tonHoldTimer(IN := TRUE, PT := TIME_OF_DAY_TO_TIME(T#0S) + TO_TIME(iTemperatureSwing_HoldTimer * 1000));
        iTemperatureSwing_CurrentState := E_TemperatureSwingState.HOLD_EXTREME;

    E_TemperatureSwingState.HOLD_EXTREME:
        IF iTemperatureSwing_HoldTimer > 0 THEN
            iTemperatureSwing_HoldTimer := iTemperatureSwing_HoldTimer - 1; // decremented on 1 s task cycle
        ELSE
            tonHoldTimer(IN := FALSE);
            iTemperatureSwing_ConsecutivePassWindows := 0; // require fresh confirmation on the return leg
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.RETURN;
        END_IF;

    E_TemperatureSwingState.RETURN:
        GVL.rCabinetSetpoint_Command := GVL.rAmbientTemperature_Reference;
        iTemperatureSwing_CurrentState := E_TemperatureSwingState.RETURN_STABILISE;

    E_TemperatureSwingState.RETURN_STABILISE:
        IF iTemperatureSwing_ConsecutivePassWindows >= 2 THEN
            iTemperatureSwing_CurrentState := E_TemperatureSwingState.CYCLE_COMPLETE;
        END_IF;

    E_TemperatureSwingState.CYCLE_COMPLETE:
        F_LogTemperatureSwingRow(sTemperatureSwing_LogFile, 'CYCLE_COMPLETE');
        xTemperatureSwing_LoggingActive := FALSE;
        xTemperatureSwing_PressureReady := FALSE;
        iTemperatureSwing_CurrentState := E_TemperatureSwingState.IDLE;

END_CASE
