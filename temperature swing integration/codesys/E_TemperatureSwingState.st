{attribute 'qualified_only'}
TYPE E_TemperatureSwingState :
(
    IDLE                := 0,
    START               := 1,
    RAMP                := 2,
    MONITOR_RATE         := 3,
    APPROACH_EXTREME     := 4,
    VERIFY_EXTREME        := 5,
    STABILISE            := 6,
    OVERSHOOT_CHECK       := 7,
    HOLD_EXTREME          := 8,
    RETURN                := 9,
    RETURN_STABILISE      := 10,
    CYCLE_COMPLETE         := 11
);
END_TYPE
