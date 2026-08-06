(* =========================================================================
   Route A — cabinet on/off over Modbus only.

   No EL2869 channel, no interposing relay, no panel wiring. The gateway
   translates the command into the F4's documented "setpoint low limit minus
   one" OFF sentinel; this POU only decides *when* to ask.

   Paste the VAR block and body into PLC_PRG (or keep it as its own POU and
   call it from PLC_PRG). Requires the GVL additions listed at the bottom and
   two new Modbus TCP channels.
   ========================================================================= *)

VAR
    tonOffLock  : TON;        (* anti-short-cycle: minimum time OFF *)
    xStartOk    : BOOL;       (* lockout satisfied, or already running *)
END_VAR

VAR CONSTANT
    (* Compressors do not tolerate rapid restarts. The interlock is kept from
       the relay design — the actuation route changed, the mechanical
       constraint did not. *)
    tOFFLOCK : TIME := T#5M;
END_VAR


(* --- Minimum off-time timer -------------------------------------------- *)
(* Runs whenever the cabinet is observed OFF, so the lockout is measured
   against the controller's real state rather than against the command. A
   stop from the F4 keypad therefore also starts the clock. *)
tonOffLock(IN := (GVL_Modbus.wOnOffState = 1), PT := tOFFLOCK);
GVL_HMI.tOffLockRemain := tOFFLOCK - tonOffLock.ET;


(* --- Command arbitration ------------------------------------------------ *)
(* A cabinet that is already running has served no off-time, so tonOffLock.Q
   is FALSE there. Without the second term an ON command would never be
   reasserted while running, and a stop made at the F4 keypad would stick. *)
xStartOk := tonOffLock.Q OR (GVL_Modbus.wOnOffState = 2);

(* STOP is immediate and unconditional. START waits for the lockout.
   Anything that delays a stop is a defect, so the stop branch is first and
   has no gate on it. Inside the lockout window neither branch runs and
   wOnOffCmd holds its previous value; tOffLockRemain shows the operator why
   nothing happened. *)
IF NOT GVL_HMI.xCabinetOnCmd THEN
    GVL_Modbus.wOnOffCmd := 1;                    (* 1 = OFF *)
ELSIF xStartOk THEN
    GVL_Modbus.wOnOffCmd := 2;                    (* 2 = ON *)
END_IF


(* --- Feedback ----------------------------------------------------------- *)
(* wOnOffState is derived by the gateway from F4 register 300 as read back,
   not from the last command, so this is observation and not an echo. It is
   still only proof that the *controller output* is enabled — see README
   section 16 on what it does and does not prove about the fan. *)
GVL_HMI.xCabinetRunning := (GVL_Modbus.wOnOffState = 2);
GVL_HMI.xStopPermit     := TRUE;   (* Route A has no stop-permit output *)


(* =========================================================================
   GVL_Modbus — add:

       wOnOffCmd     : WORD;   (* 0 = none, 1 = off, 2 = on   -> gateway *)
       wOnOffState   : WORD;   (* 0 = unknown, 1 = off, 2 = on <- gateway *)
       wSpLowLimit   : WORD;   (* F4 setpoint low limit, signed x10        *)
       wProfileNow   : WORD;   (* running profile number, 0 = none         *)

   GVL_HMI — xStartPulse is no longer used by Route A. Leave it declared if
   the watch window references it; nothing writes it any more.

   Modbus TCP Slave channels to add (element row, type WORD, as with every
   existing channel in this project):

     # | Access                        | Trigger        | Offset  | Maps to
     5 | Write Single Register (FC06)  | Cyclic 1000 ms | 16#0005 | wOnOffCmd
     6 | Read Holding Registers (FC03) | Cyclic 1000 ms | 16#0006 | wOnOffState
     7 | Read Holding Registers (FC03) | Cyclic 1000 ms | 16#0007 | wSpLowLimit
     8 | Read Holding Registers (FC03) | Cyclic 1000 ms | 16#0008 | wProfileNow

   Channels 7 and 8 are diagnostics — the OFF sentinel the gateway derived,
   and whether a profile is running. Neither is required for on/off to work.

   Bus cycle task must be MainTask and "Always update variables" enabled,
   the same setting that channels 0-4 needed.
   ========================================================================= *)
