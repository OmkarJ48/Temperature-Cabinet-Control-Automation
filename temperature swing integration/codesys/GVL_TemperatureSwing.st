{attribute 'qualified_only'}
VAR_GLOBAL
    // ========================================================================
    // TEMPERATURE SWING TEST VARIABLES
    // See docs/GVL_TemperatureSwing_Variables.md for the field-by-field reference
    // ========================================================================

    // --- Program selection and control ---
    xProgram_TemperatureSwing          : BOOL;
    xTemperatureSwing_Start            : BOOL;
    xTemperatureSwing_Stop             : BOOL;
    xTemperatureSwing_Active           : BOOL;

    // --- Operator input (Start Dialog) ---
    rTemperatureSwing_Extreme          : REAL;
    rTemperatureSwing_PressureMode     : REAL;   // 0 / 50 / 75 / 100
    rTemperatureSwing_HoldTime         : REAL;   // minutes

    // --- State machine ---
    iTemperatureSwing_CurrentState     : INT := 0; // see E_TemperatureSwingState

    // --- Temperature monitoring ---
    rBodyTemp_Current                  : REAL;
    rBodyTemp_Previous_60s             : REAL;
    rTemperatureSwing_Rate             : REAL;
    xTemperatureSwing_RateCheckPassed  : BOOL;
    iTemperatureSwing_ConsecutivePassWindows : INT;
    xTemperatureSwing_UsingFallbackChannel   : BOOL;

    // --- Extreme / overshoot detection ---
    xTemperatureSwing_ExtremeReached   : BOOL;
    rTemperatureSwing_Overshoot        : REAL;
    rTemperatureSwing_MaxOvershoot     : REAL;
    xTemperatureSwing_OvershootExceeded : BOOL;

    // --- Pressure control ---
    rTemperatureSwing_EstablishedPressure : REAL;
    xTemperatureSwing_PressureReady    : BOOL;
    rTemperatureSwing_PressureError    : REAL;

    // --- Timers ---
    iTemperatureSwing_HoldTimer        : INT;    // seconds
    tTemperatureSwing_RampStartTime    : TIME;
    tTemperatureSwing_CycleStartTime   : TIME;

    // --- Logging ---
    sTemperatureSwing_LogFile          : STRING(255);
    xTemperatureSwing_LoggingActive    : BOOL;
    iTemperatureSwing_DataPoints       : INT;

    // --- Errors ---
    xTemperatureSwing_Error            : BOOL;
    sTemperatureSwing_ErrorMessage     : STRING(255);
    iTemperatureSwing_ErrorCode        : INT;
END_VAR
