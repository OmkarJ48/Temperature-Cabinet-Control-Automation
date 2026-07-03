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

      1. Takes a new desired setpoint from the HMI.
      2. Validates it against safe limits.
      3. Writes it once (edge-triggered FC06) to register 300 (SP1).
      4. Confirms acceptance by reading register 300 back and comparing.
      5. Raises a clear, prioritised fault if the write fails, the link
         is lost, the value is refused, or the cabinet is over temperature.

    Maps 1:1 to the seven Definition-of-Done criteria in the README.

    SCALING
    F4S registers carry one implied decimal (raw 1300 == 130.0 degC).
    ScaleFactor defaults to 10.0; change it if the unit is reconfigured
    for a different resolution.

    USAGE (see PLC_PRG for the wired-up call)
    ------------------------------------------------------------------
*)
FUNCTION_BLOCK FB_CabinetSetpointControl
VAR_INPUT
    xEnable         : BOOL;         (* Master enable; FALSE holds INIT      *)

    (* Operator interface *)
    rReqSetpoint    : REAL;         (* Requested setpoint from HMI, degC    *)
    xSetButton      : BOOL;         (* Momentary "SET" - rising edge applies *)
    xResetFault     : BOOL;         (* Momentary "RESET" - clears a fault    *)

    (* Validation limits *)
    rMinSetpoint    : REAL;         (* Lower safe bound, degC               *)
    rMaxSetpoint    : REAL;         (* Upper safe bound, degC               *)

    (* Live values from the Modbus driver (GVL_Modbus) *)
    iActualTemp_raw : INT;          (* Reg 100 read-back, raw x10           *)
    iSetpointEcho_raw : INT;        (* Reg 300 read-back, raw x10           *)
    xCommsOk        : BOOL;         (* Modbus master link healthy           *)
    xWriteDone      : BOOL;         (* Last FC06 write completed OK          *)
    xWriteError     : BOOL;         (* Last FC06 write errored              *)

    (* Cabinet hard-wired safety lamp (spare EL1409 DI) *)
    xOverTempLamp   : BOOL;         (* TRUE = OVER TEMPERATURE lamp lit     *)

    (* Tuning (sensible defaults supplied by PLC_PRG) *)
    rScaleFactor    : REAL := 10.0; (* Engineering<->raw scale               *)
    iAcceptTol_raw  : INT  := 1;    (* Read-back match tolerance, raw counts *)
    tCommsTimeout   : TIME := T#3S; (* Link down this long -> COMMS_LOSS     *)
    tWriteTimeout   : TIME := T#3S; (* Settle time before checking read-back *)
    tConfirmTimeout : TIME := T#5S; (* No matching echo in this time -> FAIL *)
END_VAR
VAR_OUTPUT
    rActualTemp        : REAL;      (* Live chamber temperature, degC        *)
    rConfirmedSetpoint : REAL;      (* Last accepted setpoint, degC          *)
    xSetpointConfirmed : BOOL;      (* Latched TRUE on accepted write        *)

    (* Modbus write coupling (map to GVL_Modbus) *)
    iWriteSP_raw       : INT;       (* Value to place in reg 300, raw x10    *)
    xWriteTrigger      : BOOL;      (* Rising edge fires the FC06 write      *)

    (* Fault surface for the HMI *)
    xFault             : BOOL;
    eFault             : E_FaultCode;
    sStatusText        : STRING(80);
    eState             : E_SetpointState;
END_VAR
VAR
    rTrigSet     : R_TRIG;          (* Edge detect on SET button            *)
    rTrigReset   : R_TRIG;          (* Edge detect on RESET button          *)
    tonComms     : TON;             (* Comms-loss debounce                  *)
    tonWrite     : TON;             (* Write acknowledge timeout            *)
    tonConfirm   : TON;             (* Read-back confirm timeout            *)

    iTargetRaw   : INT;             (* Setpoint being written, raw x10      *)
END_VAR

(* ============================================================= *)
(*  1. Always-on engineering conversions for the HMI tiles       *)
(* ============================================================= *)
rActualTemp := INT_TO_REAL(iActualTemp_raw) / rScaleFactor;

(* Edge detectors run every scan *)
rTrigSet(CLK := xSetButton);
rTrigReset(CLK := xResetFault);

(* ============================================================= *)
(*  2. Global safety / comms supervision (runs in every state)   *)
(*     These pre-empt the sequencer so a fault is never masked    *)
(*     by whatever step we happen to be in.                       *)
(* ============================================================= *)

(* Comms watchdog: xCommsOk must stay TRUE; tonComms fires on loss *)
tonComms(IN := (NOT xCommsOk) AND xEnable, PT := tCommsTimeout);

(* Over-temperature lamp is a hard fault regardless of state *)
IF xEnable AND xOverTempLamp THEN
    eFault := E_FaultCode.OVER_TEMP;
    eState := E_SetpointState.FAULT;
ELSIF tonComms.Q THEN
    eFault := E_FaultCode.COMMS_LOSS;
    eState := E_SetpointState.FAULT;
END_IF

(* ============================================================= *)
(*  3. Sequencer                                                 *)
(* ============================================================= *)
CASE eState OF

    E_SetpointState.INIT:
        (* Clear everything on power-up or while disabled *)
        xWriteTrigger      := FALSE;
        xSetpointConfirmed := FALSE;
        xFault             := FALSE;
        eFault             := E_FaultCode.NONE;
        tonWrite(IN := FALSE);
        tonConfirm(IN := FALSE);
        IF xEnable THEN
            eState := E_SetpointState.IDLE;
        END_IF

    E_SetpointState.IDLE:
        xWriteTrigger := FALSE;
        (* Operator pressed SET -> begin a supervised write *)
        IF rTrigSet.Q THEN
            eState := E_SetpointState.VALIDATE;
        END_IF

    E_SetpointState.VALIDATE:
        (* Reject anything outside the commissioned safe window before
           it ever reaches the cabinet. *)
        IF (rReqSetpoint < rMinSetpoint) OR (rReqSetpoint > rMaxSetpoint) THEN
            eFault := E_FaultCode.OUT_OF_RANGE;
            eState := E_SetpointState.FAULT;
        ELSE
            iTargetRaw   := REAL_TO_INT(rReqSetpoint * rScaleFactor);
            iWriteSP_raw := iTargetRaw;
            xSetpointConfirmed := FALSE;   (* new request -> unconfirm     *)
            eState := E_SetpointState.WRITE_REQ;
        END_IF

    E_SetpointState.WRITE_REQ:
        (* Pulse the FC06 trigger once; the Modbus channel latches the
           rising edge. Move straight to WRITE_WAIT. *)
        xWriteTrigger := TRUE;
        tonWrite(IN := FALSE);             (* reset timer edge            *)
        eState := E_SetpointState.WRITE_WAIT;

    E_SetpointState.WRITE_WAIT:
        (* Let the FC06 frame go out, then hand over to CONFIRM which
           proves acceptance from the register 300 echo. We do NOT rely on
           a driver "Done" level flag (not all Modbus channel configs expose
           one, and a latched Done from a previous write would be stale) -
           the echo is the driver-agnostic proof. xWriteError, when the
           driver does expose it, gives us a precise fast-fail. *)
        xWriteTrigger := FALSE;            (* one-shot: drop the trigger  *)
        tonWrite(IN := TRUE, PT := tWriteTimeout);
        IF xWriteError THEN
            eFault := E_FaultCode.WRITE_FAILED;
            eState := E_SetpointState.FAULT;
        ELSIF xWriteDone OR tonWrite.Q THEN
            (* Acked, or settle time elapsed - go prove it via read-back *)
            tonConfirm(IN := FALSE);
            eState := E_SetpointState.CONFIRM;
        END_IF

    E_SetpointState.CONFIRM:
        (* Proof of acceptance: the cabinet must echo SP1 (reg 300) back
           equal to what we commanded, within tolerance. This is the
           "confirm the cabinet accepted the setpoint" requirement. *)
        tonConfirm(IN := TRUE, PT := tConfirmTimeout);
        IF ABS(iSetpointEcho_raw - iTargetRaw) <= iAcceptTol_raw THEN
            rConfirmedSetpoint := INT_TO_REAL(iTargetRaw) / rScaleFactor;
            xSetpointConfirmed := TRUE;
            eState := E_SetpointState.CONFIRMED;
        ELSIF tonConfirm.Q THEN
            eFault := E_FaultCode.NOT_ACCEPTED;
            eState := E_SetpointState.FAULT;
        END_IF

    E_SetpointState.CONFIRMED:
        (* Accepted and latched. Return to IDLE for the next change. *)
        eState := E_SetpointState.IDLE;

    E_SetpointState.FAULT:
        xFault        := TRUE;
        xWriteTrigger := FALSE;
        (* Operator RESET clears the fault, but only once the underlying
           condition has gone (no self-clearing over a live fault). *)
        IF rTrigReset.Q
           AND NOT xOverTempLamp
           AND NOT tonComms.Q THEN
            xFault := FALSE;
            eFault := E_FaultCode.NONE;
            eState := E_SetpointState.IDLE;
        END_IF

END_CASE

(* Disable at any time forces a clean re-init next enable *)
IF NOT xEnable THEN
    eState := E_SetpointState.INIT;
END_IF

(* ============================================================= *)
(*  4. HMI status banner (single source of operator-facing text) *)
(* ============================================================= *)
CASE eFault OF
    E_FaultCode.COMMS_LOSS:   sStatusText := 'FAULT: Communication lost to cabinet (F4S)';
    E_FaultCode.WRITE_FAILED: sStatusText := 'FAULT: Setpoint write to cabinet failed';
    E_FaultCode.NOT_ACCEPTED: sStatusText := 'FAULT: Cabinet did not accept the setpoint';
    E_FaultCode.OUT_OF_RANGE: sStatusText := 'REJECTED: Setpoint outside safe limits';
    E_FaultCode.OVER_TEMP:    sStatusText := 'ALARM: Cabinet OVER TEMPERATURE';
ELSE
    IF eState = E_SetpointState.IDLE AND xSetpointConfirmed THEN
        sStatusText := 'OK: Setpoint accepted by cabinet';
    ELSIF eState = E_SetpointState.WRITE_REQ
       OR eState = E_SetpointState.WRITE_WAIT THEN
        sStatusText := 'Writing setpoint to cabinet...';
    ELSIF eState = E_SetpointState.CONFIRM THEN
        sStatusText := 'Confirming setpoint with cabinet...';
    ELSE
        sStatusText := 'Ready';
    END_IF
END_CASE
