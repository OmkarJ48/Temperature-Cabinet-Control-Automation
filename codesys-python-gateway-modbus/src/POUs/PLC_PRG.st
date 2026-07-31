(*
    PROGRAM:  PLC_PRG
    Project:  Temperature Cabinet Setpoint Control from CODESYS HMI
    Author:   OJ (Omkar Joshi) - Oliver Mechatronics
    Language: IEC 61131-3 Structured Text (CODESYS 3.5, WebVisu)

    Cyclic entry point (MainTask). Instantiates the supervisory setpoint
    controller. Because FB_CabinetSetpointControl reads/writes GVL_Modbus
    and GVL_HMI directly in its body (see that FB's header note), this
    program only needs to pass through the operator-facing parameters
    and the safety interlock input.

    Matches the Project Development Package spec (Details A) and the
    build guide already in codesys-modbus-integration/README.md.

    TODO (flagged in the Project Development Package, not yet resolved):
    xOverTempDI below is wired to GVL_Modbus.xModbusError as a
    placeholder. REPLACE with the real mapped EL1409 digital-input
    channel (spare over-temperature lamp contact) in the EtherCAT I/O
    mapping before relying on this interlock.
*)
PROGRAM PLC_PRG
VAR
    fbSetpoint : FB_CabinetSetpointControl;
    dtNow : DT;
END_VAR

(* ---- Drive the supervisory setpoint controller ---- *)
fbSetpoint(
    rRequestedSetpoint := GVL_HMI.rReqSetpoint,
    xSetCommand        := GVL_HMI.xSetBtn,
    xReset             := GVL_HMI.xResetBtn,
    xOverTempDI        := GVL_Modbus.xModbusError,  (* REPLACE with mapped EL1409 DI channel *)
    rMinSetpoint       := -40.0,
    rMaxSetpoint       := 200.0
);

(* ---- Consume dialog button one-shots ---- *)
GVL_HMI.xSetBtn   := FALSE;
GVL_HMI.xResetBtn := FALSE;

(* ---- Scheduled ramp gate: EL2869 CH15 -> F4 DI1 ---- *)
dtNow := RtcGet();

IF GVL_HMI.xSchedEnable AND (dtNow < GVL_HMI.dtSchedStart) THEN
    GVL_HMI.xRampInhibit := TRUE;
ELSE
    GVL_HMI.xRampInhibit := FALSE;
END_IF

GVL_HMI.xRampActive := NOT GVL_HMI.xRampInhibit;
