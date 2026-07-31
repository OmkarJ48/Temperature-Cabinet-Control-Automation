(* =========================================================================
   Route A — cabinet on/off over Modbus only.

   No EL2869 channel, no interposing relay, no panel wiring. The gateway
   translates the command into the F4's documented "setpoint low limit minus
   one" OFF sentinel; this POU only decides *when* to ask.

   Paste the VAR block and body into PLC_PRG (or keep it as its own POU and
   call it from PLC_PRG). Requires the GVL additions listed at the bottom and
   two new Modbus TCP channels.

   No anti-short-cycle interlock here — removed 31 July 2026 by field
   decision so the cabinet responds instantly to xCabinetOnCmd from CODESYS.
   This trades away the compressor protection the mechanical/EL2869 path
   (Path1_EL2869_StartStop.st) still keeps; Test 3 in that day's field
   session rapid-cycled the real compressor five times with no minimum
   off-time to confirm the change took effect. If Route A ever becomes the
   only path commanding the compressor (i.e. Path 1 is not also wired), put
   a minimum off-time back before relying on this for daily use.
   ========================================================================= *)


(* --- Command arbitration ------------------------------------------------ *)
(* STOP is immediate and unconditional. START is immediate too — no lockout,
   no gate. See the header note above for the trade-off this makes. *)
IF NOT GVL_HMI.xCabinetOnCmd THEN
    GVL_Modbus.wOnOffCmd := 1;                    (* 1 = OFF *)
ELSE
    GVL_Modbus.wOnOffCmd := 2;                    (* 2 = ON *)
END_IF


(* --- Feedback ----------------------------------------------------------- *)
(* wOnOffState is derived by the gateway from F4 register 300 as read back,
   not from the last command, so this is observation and not an echo. It is
   still only proof that the *controller output* is enabled — see README
   section 16 on what it does and does not prove about the fan. *)
GVL_HMI.xCabinetRunning := (GVL_Modbus.wOnOffState = 2);

(* xStopPermit is NOT written here. It belongs to
   Path1_EL2869_StartStop.st, which drives EL2869 CH16 from it. If both
   sections write it, whichever runs later in the scan wins every cycle —
   if that happened to be this one, CH16 would be forced permanently HIGH
   and Path 1's remote stop would silently stop working. If Path 1 is not
   pasted into this PLC_PRG, xStopPermit is simply unused; do not "fix"
   that by writing TRUE here again. *)


(* =========================================================================
   GVL_Modbus — add:

       wOnOffCmd     : WORD;   (* 0 = none, 1 = off, 2 = on   -> gateway *)
       wOnOffState   : WORD;   (* 0 = unknown, 1 = off, 2 = on <- gateway *)
       wSpLowLimit   : WORD;   (* F4 setpoint low limit, signed x10        *)
       wProfileNow   : WORD;   (* running profile number, 0 = none         *)

   GVL_HMI — xStartPulse and xStopPermit are NOT Route A's. They belong to
   Path1_EL2869_StartStop.st (EL2869 CH15/CH16, README §15). Route A only
   ever touches wOnOffCmd, xCabinetRunning and xCabinetOnCmd (input). Do not
   add writes to xStartPulse/xStopPermit here even if both POUs are pasted
   into the same PLC_PRG — see the comment at the feedback block above.

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
