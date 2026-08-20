{attribute 'qualified_only'}
VAR_GLOBAL
    // ========================================================================
    // TEMPERATURE SWING — new variables only.
    // Everything else (doUpstream, doDownstream, alrChannelReading, aiAlarms,
    // iMainChannelIndex, iTestPressure, sPrompt, xStart, xSave) already exists
    // in the main project GVL and is reused as-is — confirmed against
    // FB_Hold, FB_Apply_Test_Pressure, FB_Pressure_Release, FB_CSV_Handler.
    // ========================================================================

    // Operator input (Start Dialog, via Python frontend)
    rTemperatureSwing_Setpoint     : LREAL;    // target temperature, +/-
    iTemperatureSwing_HoldPeriod   : INT;      // minutes; same convention as iHoldPeriod (FB_Hold)
END_VAR
