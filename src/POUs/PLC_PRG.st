(*
    PROGRAM:  PLC_PRG
    Project:  Temperature Cabinet Setpoint Control from CODESYS HMI
    Author:   OJ (Omkar Joshi) - Oliver Mechatronics
    Language: IEC 61131-3 Structured Text (CODESYS 3.5, WebVisu)

    Cyclic entry point (MainTask). Instantiates the supervisory setpoint
    controller and wires it between the Modbus driver channels
    (GVL_Modbus) and the WebVisu tags (GVL_HMI).

    NOTE: replace the existing empty PLC_PRG body in the sandbox project
    with this. The Modbus Serial Master / Slave / channels are configured
    in the device tree per GVL_Modbus - this program does not open the
    port itself.
*)
PROGRAM PLC_PRG
VAR
    fbSetpoint : FB_CabinetSetpointControl;
END_VAR

(* ---- Drive the supervisory setpoint controller ---- *)
fbSetpoint(
    xEnable           := TRUE,

    (* Operator interface (WebVisu) *)
    rReqSetpoint      := GVL_HMI.rReqSetpoint,
    xSetButton        := GVL_HMI.xSetButton,
    xResetFault       := GVL_HMI.xResetFault,
    rMinSetpoint      := GVL_HMI.rMinSetpoint,
    rMaxSetpoint      := GVL_HMI.rMaxSetpoint,

    (* Live values from the Modbus driver *)
    iActualTemp_raw   := GVL_Modbus.iActualTemp_raw,
    iSetpointEcho_raw := GVL_Modbus.iSetpointEcho_raw,
    xCommsOk          := GVL_Modbus.xCommsOk,
    xWriteDone        := GVL_Modbus.xWriteDone,
    xWriteError       := GVL_Modbus.xWriteError,

    (* Cabinet hard-wired safety lamp (spare EL1409 DI) *)
    xOverTempLamp     := GVL_HMI.xOverTempLamp
    (* Tuning inputs (rScaleFactor, timeouts, tolerance) use FB defaults;
       override here only if the F4S is reconfigured. *)
);

(* ---- Publish results back to the driver and the HMI ---- *)
(* To Modbus write channel *)
GVL_Modbus.iWriteSP_raw     := fbSetpoint.iWriteSP_raw;
GVL_Modbus.xWriteTrigger    := fbSetpoint.xWriteTrigger;

(* To WebVisu *)
GVL_HMI.rActualTemp         := fbSetpoint.rActualTemp;
GVL_HMI.rConfirmedSetpoint  := fbSetpoint.rConfirmedSetpoint;
GVL_HMI.xSetpointConfirmed  := fbSetpoint.xSetpointConfirmed;
GVL_HMI.xFault              := fbSetpoint.xFault;
GVL_HMI.eActiveFault        := fbSetpoint.eFault;
GVL_HMI.sStatusText         := fbSetpoint.sStatusText;
