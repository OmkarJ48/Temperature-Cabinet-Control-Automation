(*
    FUNCTION_BLOCK: FB_CabinetSetpointControl
    Project:  Temperature Cabinet Setpoint Control from CODESYS HMI
    Author:   OJ (Omkar Joshi) - Oliver Mechatronics
    Language: IEC 61131-3 Structured Text (CODESYS 3.5, WebVisu)

    ------------------------------------------------------------------
    ROLE
    Supervisory setpoint control for the Left Hand Small Temperature
    Cabinet (Watlow F4S, Modbus RTU / RS-232). CODESYS never runs the
    thermal loop - the F4S keeps its own closed-loop PID. This block:

      1. Takes a new desired setpoint from the HMI (GVL_HMI.rReqSetpoint).
      2. Validates it against safe limits.
      3. Writes it once (edge-triggered FC06) to register 300 (SP1).
      4. Confirms acceptance by reading register 300 back and comparing.
      5. Raises a clear, prioritised fault if the write fails, the link
         is lost, the value is refused, or the cabinet is over temperature.

    Matches the Project Development Package spec (Details A) and the
    build guide already in codesys-modbus-integration/README.md
    (Part 3, Part 4) and the T1-T9 test plan in the main README.

    SCALING
    F4S registers carry one implied decimal (raw 1300 == 130.0 degC).
    rScale defaults to 10.0; change it if the unit is reconfigured
    for a different resolution.

    NOTE (known follow-up item): this FB reads/writes GVL_Modbus and
    GVL_HMI directly in its body rather than exclusively through
    VAR_INPUT/VAR_OUTPUT. That is how the Project Development Package
    and the README build guide specify it, and it is what the T1-T9
    bench tests exercise - but it does mean this FB cannot be unit
    tested or reused against a second GVL_Modbus instance without
    editing the body. See PLC_PRG for the wired-up call, and note the
    xOverTempDI placeholder wiring there.
    ------------------------------------------------------------------
*)
FUNCTION_BLOCK FB_CabinetSetpointControl
VAR_INPUT
    rRequestedSetpoint  : REAL;                    (* deg C from HMI                    *)
    xSetCommand         : BOOL;                    (* HMI SET - rising edge applies      *)
    xReset              : BOOL;                    (* fault reset - rising edge clears   *)
    xOverTempDI         : BOOL;                    (* spare EL1409 DI, TRUE = over-temp  *)

    (* ---- configurable, default to confirmed values ---- *)
    rMinSetpoint        : REAL := 30.0;            (* Lower safe bound, degC              *)
    rMaxSetpoint        : REAL := 130.0;           (* Upper safe bound, degC              *)
    rScale              : REAL := 10.0;            (* eng <-> raw multiplier              *)
    rTolerance          : REAL := 0.1;             (* deg C read-back tolerance           *)
    tCommsTimeout       : TIME := T#3S;            (* watchdog                            *)
END_VAR
VAR_OUTPUT
    eState              : E_SetpointState;
    eFault              : E_FaultCode;
    xConfirmed          : BOOL;
    xFault              : BOOL;
    rActualTemp         : REAL;                    (* Live chamber temperature, degC      *)
    rConfirmedSetpoint  : REAL;                    (* Last accepted setpoint, degC        *)
END_VAR
VAR
    rtrigSet            : R_TRIG;                  (* Edge detect on SET command          *)
    rtrigReset          : R_TRIG;                  (* Edge detect on RESET command        *)
    tonWatchdog         : TON;                     (* Comms-loss debounce                 *)
    tonConfirmWait      : TON;                     (* Read-back confirm timeout           *)
    wTargetRaw          : WORD;                    (* Setpoint being written, raw x10     *)
    rReadBack           : REAL;                    (* Setpoint echo, engineering units    *)
END_VAR

(* ---- Edge detect ---- *)
rtrigSet(CLK := xSetCommand);
rtrigReset(CLK := xReset);

(* ---- Always-live scaling of the cyclic read ---- *)
rActualTemp          := WORD_TO_REAL(GVL_Modbus.wInput1Value) / rScale;
rReadBack             := WORD_TO_REAL(GVL_Modbus.wSetpoint1Read) / rScale;
GVL_HMI.rChamberTemp := rActualTemp;

(* ---- Comms watchdog: LEVEL signal, NOT an edge pulse (avoids R_TRIG->TON trap) ---- *)
tonWatchdog(IN := NOT GVL_Modbus.xModbusDone, PT := tCommsTimeout);

(* ---- Over-temp interlock (highest priority latch) ---- *)
IF xOverTempDI THEN
    eFault := E_FaultCode.OVER_TEMP;
    eState := E_SetpointState.FAULTED;
END_IF

(* ---- Comms loss latch (any state) ---- *)
IF tonWatchdog.Q OR GVL_Modbus.xModbusError THEN
    eFault := E_FaultCode.COMMS_TIMEOUT;
    eState := E_SetpointState.FAULTED;
END_IF

CASE eState OF

    E_SetpointState.IDLE:
        xConfirmed := TRUE;
        GVL_Modbus.xWriteTrigger := FALSE;
        IF rtrigSet.Q THEN
            eState := E_SetpointState.READY;
        END_IF

    E_SetpointState.READY:
        xConfirmed := FALSE;
        IF rRequestedSetpoint < rMinSetpoint THEN
            eFault := E_FaultCode.RANGE_LOW;
            eState := E_SetpointState.FAULTED;
        ELSIF rRequestedSetpoint > rMaxSetpoint THEN
            eFault := E_FaultCode.RANGE_HIGH;
            eState := E_SetpointState.FAULTED;
        ELSE
            wTargetRaw := REAL_TO_WORD(rRequestedSetpoint * rScale);
            GVL_Modbus.wSetpoint1Write := wTargetRaw;
            eState := E_SetpointState.WRITING;
        END_IF

    E_SetpointState.WRITING:
        GVL_Modbus.xWriteTrigger := TRUE;    (* one-shot rising edge fires FC06 *)
        eState := E_SetpointState.CONFIRM;

    E_SetpointState.CONFIRM:
        GVL_Modbus.xWriteTrigger := FALSE;   (* drop trigger to re-arm the edge *)
        tonConfirmWait(IN := TRUE, PT := tCommsTimeout);
        IF ABS(rReadBack - rRequestedSetpoint) <= rTolerance THEN
            rConfirmedSetpoint := rReadBack;
            GVL_HMI.rConfirmedSetpoint := rReadBack;
            tonConfirmWait(IN := FALSE);
            eState := E_SetpointState.IDLE;
        ELSIF tonConfirmWait.Q THEN
            eFault := E_FaultCode.NOT_ACCEPTED;
            eState := E_SetpointState.FAULTED;
        END_IF

    E_SetpointState.FAULTED:
        xConfirmed := FALSE;
        GVL_Modbus.xWriteTrigger := FALSE;
        (* Latched - clears only on reset edge AND only if condition is gone *)
        IF rtrigReset.Q
           AND NOT xOverTempDI
           AND NOT tonWatchdog.Q
           AND NOT GVL_Modbus.xModbusError THEN
            eFault := E_FaultCode.NO_FAULT;
            eState := E_SetpointState.IDLE;
        END_IF

END_CASE

xFault                      := (eState = E_SetpointState.FAULTED);
GVL_HMI.xSetpointConfirmed  := xConfirmed AND NOT xFault;
GVL_HMI.xFaultActive        := xFault;
GVL_HMI.eFaultCode          := eFault;
