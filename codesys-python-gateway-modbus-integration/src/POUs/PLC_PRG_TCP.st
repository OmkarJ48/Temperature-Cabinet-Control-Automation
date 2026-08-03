PROGRAM PLC_PRG
(* ======================================================================
   Retargeted for TCP register sources (Python gateway via Modbus TCP)
   ======================================================================
   Serial device abandoned. All reads/writes now come via the TCP slave
   device on the Modbus TCP master branch of the device tree.
   
   Proven register map (TCP holding registers, x10 integers):
     reg2 = chamber temperature (read-only, cyclic)
     reg3 = confirmed setpoint read-back (read-only, cyclic)
     reg4 = status/fault code (read-only, cyclic)
     reg0 = requested setpoint (write, cyclic or rising)
     reg1 = apply trigger (write, rising edge)
   
   I/O Mapping binds these to GVL_Modbus:
     reg2 -> wInput1Value (temperature)
     reg3 -> wSetpoint1Read (confirmed SP)
     reg4 -> wStatus (fault code: 0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS)
     reg0 -> wSetpoint1Write (requested SP, x10)
     reg1 -> xWriteTrigger (apply pulse, BOOL as WORD 0/1)
   
   The state machine logic is unchanged from the serial version. Only the
   data sources changed: TCP channels instead of serial channels.
   ====================================================================== *)

VAR
    rChamberTemp        : REAL;
    rReqSetpoint        : REAL := 26.5;           (* set in watch window or WebVisu *)
    rConfirmedSetpoint  : REAL;

    rMinSetpoint        : REAL := -40.0;
    rMaxSetpoint        : REAL := 200.0;

    eSetpointState      : E_SetpointState := E_SetpointState.IDLE;
    eFaultCode          : E_FaultCode := E_FaultCode.NO_FAULT;

    xStartWrite         : BOOL := FALSE;          (* rising-edge trigger for manual test *)
    xPrevStartWrite     : BOOL := FALSE;
    xWriteTriggered     : BOOL := FALSE;

    dwWriteTimeout      : DWORD := 0;
    (* Must exceed the WORST-CASE confirm chain, not the typical one:
         gateway poll period            1.0 s   (POLL_PERIOD)
       + gateway RTU confirm read-back  0.5 s   (READ_TIMEOUT)
       + CODESYS cyclic read of reg3    2.0 s   (channel 3 trigger interval)
       = 3.5 s worst case, against a 3.0 s timeout -> spurious NOT_ACCEPTED on
       a write the F4S had actually taken. Raised to 10 s so only a genuine
       failure trips it; the gateway's own status codes (2/3/5) still fault
       fast, so a real rejection is never delayed by this headroom. *)
    dwMaxTimeout        : DWORD := 1000;          (* ~10s at 10ms MainTask *)

    dtNow               : DT;                      (* current local time for schedule *)
    uliHighRes          : ULINT;                   (* high-resolution time, raw ms since epoch, UTC *)

    (* --- Cabinet power on/off (Option C, EL2869 CH15/CH16 -> button station) --- *)
    rtrigStopPermit     : R_TRIG;                  (* edge on xStopPermit rising -> fire start pulse *)
    tpStartPulse        : TP;                      (* ~1s one-shot pulse generator for CH15 *)
    tonOffLock          : TON;                     (* anti-short-cycle: min time OFF before restart *)
END_VAR

VAR CONSTANT
    tSTART_PULSE        : TIME := T#1S;            (* CH15 pulse width -- long enough for the
                                                        latch relay to pick up, per README §15.10
                                                        troubleshooting (raise to 2s if it won't catch) *)
    tOFFLOCK             : TIME := T#5M;            (* compressor minimum off-time, README §15 BOM *)
END_VAR

(* --- STEP 0: Scheduled cabinet power on/off - EL2869 CH15/CH16 -> button station ---
   CH16 (xStopPermit) is the button station's own 24V supply: HIGH = cabinet can run,
   LOW = station loses power and drops out (remote stop, no relay needed -- README §15.4).
   CH15 (xStartPulse) parallels the green NO contact with a diode: a rising edge on
   xStopPermit fires a one-shot pulse that "presses" the green button electronically.
   The red button remains a physical series break -- local stop always works regardless
   of DLS/CODESYS state (README §15.4 accepted trade-off). *)
SysTimeRtcHighResGet(uliHighRes);
dtNow := ULINT_TO_DT(uliHighRes / 1000 + DINT_TO_ULINT(GVL_HMI.diUtcOffsetSec));  (* ms -> s, then UTC -> local *)

GVL_HMI.xCabinetOnCmd := NOT (GVL_HMI.xSchedEnable AND (dtNow < GVL_HMI.dtSchedStart));

(* Anti-short-cycle: measured against the station's real de-energised time, not the
   command, so a stop made at the local red button also starts the clock. *)
tonOffLock(IN := NOT GVL_HMI.xStopPermit, PT := tOFFLOCK);
GVL_HMI.tOffLockRemain := tOFFLOCK - tonOffLock.ET;

(* Stop is immediate and unconditional. Start waits for the lockout to clear.
   Inside the lockout window neither branch runs and xStopPermit holds its
   previous value; tOffLockRemain shows the operator why nothing happened. *)
IF NOT GVL_HMI.xCabinetOnCmd THEN
    GVL_HMI.xStopPermit := FALSE;
ELSIF tonOffLock.Q THEN
    GVL_HMI.xStopPermit := TRUE;
END_IF

(* One-shot ~1s pulse on CH15 every time xStopPermit transitions LOW -> HIGH. *)
rtrigStopPermit(CLK := GVL_HMI.xStopPermit);
tpStartPulse(IN := rtrigStopPermit.Q, PT := tSTART_PULSE);
GVL_HMI.xStartPulse := tpStartPulse.Q;

GVL_HMI.xCabinetRunning := GVL_HMI.xStopPermit;  (* no independent run-feedback wired yet *)

(* --- STEP 1: Scale raw TCP values -> engineering units ---
   TCP registers carry x10 integers; we work in real degrees.
   All three reads come from the TCP channels (wInput1Value, wSetpoint1Read, wStatus).

   The registers carry SIGNED x10 integers in two's complement. WORD is an
   UNSIGNED type in IEC 61131-3, so dividing it directly turns -1.0 degC
   (raw 16#FFF6) into 6552.6 instead of -1.0. Every sub-zero temperature and
   every negative setpoint read-back was wrong, and the CONFIRM comparison
   below could never match one. WORD_TO_INT reinterprets the bit pattern as
   the signed value the F4S actually sent.
*)
rChamberTemp       := WORD_TO_INT(GVL_Modbus.wInput1Value)  / 10.0;
rConfirmedSetpoint := WORD_TO_INT(GVL_Modbus.wSetpoint1Read) / 10.0;

(* --- STEP 2: Detect rising edge on the manual test trigger ---
   When testing from watch window, toggle xStartWrite from FALSE to TRUE.
   In production (WebVisu or SCADA), the operator triggers via a button that
   sets a HMI variable, but the edge logic is the same.
*)
xWriteTriggered := (xStartWrite AND NOT xPrevStartWrite);
xPrevStartWrite := xStartWrite;

(* --- STEP 3: State machine (unchanged logic, TCP-based register sources) --- *)

CASE eSetpointState OF

    E_SetpointState.IDLE:
        (* Waiting for a write request. Hold the apply trigger low. *)
        GVL_Modbus.xWriteTrigger := FALSE;
        dwWriteTimeout := 0;
        
        IF xWriteTriggered THEN
            eSetpointState := E_SetpointState.READY;
        END_IF


    E_SetpointState.READY:
        (* Validate the requested setpoint against limits. *)
        IF rReqSetpoint < rMinSetpoint THEN
            eFaultCode := E_FaultCode.RANGE_LOW;
            eSetpointState := E_SetpointState.FAULTED;

        ELSIF rReqSetpoint > rMaxSetpoint THEN
            eFaultCode := E_FaultCode.RANGE_HIGH;
            eSetpointState := E_SetpointState.FAULTED;

        ELSE
            (* Valid range. Stage the request (x10 int) into the TCP write register.

               REAL_TO_DWORD is UNDEFINED for negative operands in IEC 61131-3
               -- it happened to produce the right bit pattern on this runtime,
               but that is luck, not contract, and it truncates instead of
               rounding (26.45 -> 264, not 265). REAL_TO_INT rounds and is
               defined across the whole -40..200 range; INT_TO_WORD then
               reinterprets the signed value as the two's-complement WORD the
               gateway expects on the wire. *)
            GVL_Modbus.wSetpoint1Write := INT_TO_WORD(REAL_TO_INT(rReqSetpoint * 10.0));
            eSetpointState := E_SetpointState.WRITING;
        END_IF


    E_SetpointState.WRITING:
        (* Pulse the apply trigger (one scan). The Python gateway services this
           by writing reg1=1 over RTU and then clearing it to 0 when done. *)
        GVL_Modbus.xWriteTrigger := TRUE;
        dwWriteTimeout := 0;
        eSetpointState := E_SetpointState.CONFIRM;


    E_SetpointState.CONFIRM:
        (* Drop the trigger immediately to re-arm the edge for the next request. *)
        GVL_Modbus.xWriteTrigger := FALSE;
        dwWriteTimeout := dwWriteTimeout + 1;

        (* Check for immediate comms failure (Python gateway lost). *)
        IF GVL_Modbus.wStatus = 5 THEN                  (* COMMS fault from gateway *)
            eFaultCode := E_FaultCode.COMMS_TIMEOUT;
            eSetpointState := E_SetpointState.FAULTED;

        (* Check for write-accepted confirmation: read-back matches request. *)
        ELSIF ABS(rConfirmedSetpoint - rReqSetpoint) < 0.1 THEN
            eFaultCode := E_FaultCode.NO_FAULT;
            eSetpointState := E_SetpointState.IDLE;

        (* Check for write-failed fault (Python couldn't write to F4S). *)
        ELSIF GVL_Modbus.wStatus = 2 THEN                (* WRITE_FAILED *)
            eFaultCode := E_FaultCode.WRITE_FAILED;
            eSetpointState := E_SetpointState.FAULTED;

        (* Check for not-accepted fault (F4S silent-rejected, e.g., menu mode). *)
        ELSIF GVL_Modbus.wStatus = 3 THEN                (* NOT_ACCEPTED *)
            eFaultCode := E_FaultCode.NOT_ACCEPTED;
            eSetpointState := E_SetpointState.FAULTED;

        (* Check for range/fault from Python side.
           The gateway reports a single RANGE code (4) without a direction, so
           resolve LOW vs HIGH from the request we actually sent. Reporting
           every gateway range reject as RANGE_HIGH sent the operator hunting
           for a ceiling problem when a -1.0 degC request had tripped the
           gateway's old unsigned 0..2000 check at the FLOOR. *)
        ELSIF GVL_Modbus.wStatus = 4 THEN                (* RANGE *)
            IF rReqSetpoint < rMinSetpoint THEN
                eFaultCode := E_FaultCode.RANGE_LOW;
            ELSE
                eFaultCode := E_FaultCode.RANGE_HIGH;
            END_IF
            eSetpointState := E_SetpointState.FAULTED;

        (* Timeout: Python didn't respond in time. *)
        ELSIF dwWriteTimeout > dwMaxTimeout THEN
            eFaultCode := E_FaultCode.NOT_ACCEPTED;      (* treated as F4S rejection *)
            eSetpointState := E_SetpointState.FAULTED;
        END_IF


    E_SetpointState.FAULTED:
        (* Latched fault state. User must acknowledge by re-triggering (watch window or HMI). *)
        GVL_Modbus.xWriteTrigger := FALSE;
        
        IF xWriteTriggered THEN
            eFaultCode := E_FaultCode.NO_FAULT;
            eSetpointState := E_SetpointState.READY;
        END_IF

END_CASE

(* --- STEP 4: Consume the manual test trigger (so it doesn't re-fire) ---
   In production, replace xStartWrite with the HMI/WebVisu button signal.
   The gateway's apply trigger (reg1) is cleared by the Python side after processing.
*)
xStartWrite := FALSE;
