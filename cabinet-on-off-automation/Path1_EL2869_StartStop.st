(* =========================================================================
   Path 1 — physical on/off over EL2869 CH15/CH16, no relays (Option C).

   This is the §15 fallback: it stops BOTH the compressor and the fan by
   becoming the front-panel Start/Stop station's own 24 V supply, instead of
   trying to change anything inside the F4S. It is independent of Route A
   (RouteA_CabinetOnOff.st) — both read the same GVL_HMI.xCabinetOnCmd, so
   they can run side by side with no conflict: Route A stops the F4S's own
   control output, Path 1 cuts power to the whole station (fan included).

   Restored 31 July 2026. An earlier edit that removed Route A's lockout
   timer (per an on-site request scoped to Route A) also deleted this
   sequencer, because it shared PLC_PRG with Route A's arbitration block.
   That left xStartPulse undriven and xStopPermit hardcoded TRUE — CH15
   would never pulse and CH16 would never drop, so remote start/stop over
   EL2869 would silently do nothing on wiring landed the same day. The
   anti-short-cycle interlock here is NOT optional the way Route A's is: this
   path drives the real latching contactor directly (README §9 step 4,
   §15.2). Keep it.

   Paste into PLC_PRG as its own section, alongside Route A's section.
   Requires the GVL_HMI additions listed at the bottom, and CH15/CH16
   mapped to xStartPulse/xStopPermit in the EL2869 I/O Mapping tab
   (Always update variables = Enabled, bus cycle task = MainTask).
   ========================================================================= *)

VAR
    tonStartPulse : TON;              (* start pulse width          *)
    tonOffLock    : TON;              (* minimum off time           *)
    xCmdPrev      : BOOL;
    xRunLatch     : BOOL;             (* our view of latch state    *)
END_VAR

VAR CONSTANT
    tPULSE   : TIME := T#1S;          (* comfortably longer than latch pickup *)
    tOFFLOCK : TIME := T#5M;          (* compressor anti-short-cycle          *)
END_VAR


(* --- minimum off-time timer: runs whenever we are not running ----------- *)
tonOffLock(IN := NOT xRunLatch, PT := tOFFLOCK);
GVL_HMI.tOffLockRemain := tOFFLOCK - tonOffLock.ET;

(* --- STOP: break the series contact immediately, no interlock ----------- *)
(* Stopping is always allowed. Only starting is ever delayed. CH16 LOW
   drops the station's own supply -- Option C's remote-stop mechanism
   (README §15.4). *)
GVL_HMI.xStopPermit := GVL_HMI.xCabinetOnCmd;

IF NOT GVL_HMI.xCabinetOnCmd THEN
    xRunLatch := FALSE;
END_IF

(* --- START: rising edge, but only once the off-lock has expired --------- *)
IF GVL_HMI.xCabinetOnCmd AND NOT xCmdPrev AND tonOffLock.Q THEN
    tonStartPulse(IN := FALSE); (* reset *)
    tonStartPulse(IN := TRUE, PT := tPULSE);
    xRunLatch := TRUE;
END_IF
xCmdPrev := GVL_HMI.xCabinetOnCmd;

tonStartPulse(IN := xRunLatch AND GVL_HMI.xCabinetOnCmd, PT := tPULSE);
GVL_HMI.xStartPulse := tonStartPulse.IN AND NOT tonStartPulse.Q;


(* =========================================================================
   GVL_HMI — add (if not already present from an earlier Route A edit):

       xStartPulse    : BOOL;   (* -> EL2869 CH15, 1s pulse, parallels green button *)
       xStopPermit    : BOOL;   (* -> EL2869 CH16, TRUE = station supply live       *)
       tOffLockRemain : TIME;   (* anti-short-cycle countdown, this path only       *)

   EL2869 I/O Mapping — map two channels (README §15.3, confirmed against
   as-built drawing 7168-DWG-100 Rev B):

     CODESYS variable      | EL2869 output | -202X3 pin | Function
     xStartPulse           | CH15          | 36         | start pulse (via diode) -> wire 102
     xStopPermit           | CH16          | 37         | station supply -> wire 100
     (0 V return)           -              | 20, 29     | -> wire 101

   Before landing any wire, confirm on the meter (README §15.10 checkpoint 1)
   that the channel physically wired to pin 36 pulses ~1s and the one on
   pin 37 is steady while running -- swapping CH15/CH16 swaps a transient
   pulse for what must be a continuous supply, and Option C depends on
   that distinction.
   ========================================================================= *)
