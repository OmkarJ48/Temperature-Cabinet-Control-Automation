"""OPC UA node ID map for the Temperature Swing test.

Mirrors the GVL variables declared in
``codesys/GVL_TemperatureSwing.st`` — see ``docs/GVL_TemperatureSwing_Variables.md``
for the full field reference. Node IDs assume the variables live in the
project's default ``"GVL"`` namespace; update the strings below if the
CODESYS-side import used a differently named GVL object.
"""

OPC_NODES_TEMPERATURE_SWING = {
    # Program selection and control
    "temperature_swing_program_selected": 'ns=3;s="GVL"."xProgram_TemperatureSwing"',
    "temperature_swing_start": 'ns=3;s="GVL"."xTemperatureSwing_Start"',
    "temperature_swing_stop": 'ns=3;s="GVL"."xTemperatureSwing_Stop"',
    "temperature_swing_active": 'ns=3;s="GVL"."xTemperatureSwing_Active"',

    # Operator input
    "temperature_swing_extreme": 'ns=3;s="GVL"."rTemperatureSwing_Extreme"',
    "temperature_swing_pressure_mode": 'ns=3;s="GVL"."rTemperatureSwing_PressureMode"',
    "temperature_swing_hold_time": 'ns=3;s="GVL"."rTemperatureSwing_HoldTime"',

    # State machine
    "temperature_swing_state": 'ns=3;s="GVL"."iTemperatureSwing_CurrentState"',

    # Temperature monitoring
    "body_temp_current": 'ns=3;s="GVL"."rBodyTemp_Current"',
    "temperature_swing_rate": 'ns=3;s="GVL"."rTemperatureSwing_Rate"',
    "temperature_swing_rate_passed": 'ns=3;s="GVL"."xTemperatureSwing_RateCheckPassed"',
    "temperature_swing_using_fallback_channel": 'ns=3;s="GVL"."xTemperatureSwing_UsingFallbackChannel"',

    # Extreme / overshoot
    "temperature_swing_extreme_reached": 'ns=3;s="GVL"."xTemperatureSwing_ExtremeReached"',
    "temperature_swing_overshoot": 'ns=3;s="GVL"."rTemperatureSwing_Overshoot"',
    "temperature_swing_max_overshoot": 'ns=3;s="GVL"."rTemperatureSwing_MaxOvershoot"',
    "temperature_swing_overshoot_exceeded": 'ns=3;s="GVL"."xTemperatureSwing_OvershootExceeded"',

    # Pressure
    "temperature_swing_pressure_ready": 'ns=3;s="GVL"."xTemperatureSwing_PressureReady"',
    "temperature_swing_established_pressure": 'ns=3;s="GVL"."rTemperatureSwing_EstablishedPressure"',
    "temperature_swing_pressure_error": 'ns=3;s="GVL"."rTemperatureSwing_PressureError"',

    # Timers
    "temperature_swing_hold_timer": 'ns=3;s="GVL"."iTemperatureSwing_HoldTimer"',

    # Logging
    "temperature_swing_log_file": 'ns=3;s="GVL"."sTemperatureSwing_LogFile"',
    "temperature_swing_data_points": 'ns=3;s="GVL"."iTemperatureSwing_DataPoints"',

    # Errors
    "temperature_swing_error": 'ns=3;s="GVL"."xTemperatureSwing_Error"',
    "temperature_swing_error_message": 'ns=3;s="GVL"."sTemperatureSwing_ErrorMessage"',
    "temperature_swing_error_code": 'ns=3;s="GVL"."iTemperatureSwing_ErrorCode"',
}

# Rate check pass threshold, degC/min — must match FB_TemperatureSwing.st
RATE_THRESHOLD_C_PER_MIN = 0.5

# Overshoot ceiling, degC — must match FB_TemperatureSwing.st
OVERSHOOT_LIMIT_C = 11.0

# Pressure mode options exposed in the Start Dialog
PRESSURE_MODES = {"none": 0.0, "50": 50.0, "75": 75.0, "100": 100.0}
