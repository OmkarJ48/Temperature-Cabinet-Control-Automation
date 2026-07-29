# Cabinet On/Off Automation — Investigation & Integration Guide

**Author:** Omkar Joshi — Oliver Mechatronics
**Date:** 28 July 2026
**Objective:** Remotely start and stop the Left Hand Small Temperature Cabinet, without touching mains wiring and without taking authority away from the local operator.
**Status:** Investigation complete. Coil voltage confirmed 24 V / 0 V. Topology decided. **One open question blocks wiring** — see §4.

---

## 1. Investigation log — how the conclusion was reached

| # | Step | Command / action | Result | What it ruled in or out |
|---|---|---|---|---|
| 1 | Baseline the gateway | `journalctl -u f4s-gateway -n 10` | Active, polling cleanly | Control condition established — any later change is attributable to the switch |
| 2 | Poll RTU while switching | `mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -0 /dev/ttyWatlowF4S` | Reads OK, then I/O errors after OFF | **Inconclusive** — gateway still held the port, so errors were contention noise |
| 3 | Observe the CODESYS link | Watch Modbus TCP master while switching | **TCP never dropped** | Ruled out mains disconnect. If the F4S lost supply, RTU would die and status would go to 5 (COMMS) |
| 4 | Differential register scan | Gateway stopped; read 100–149, 150–199, 200–249 ON vs OFF; `diff` | **Zero difference** | Switch state is not reflected anywhere in the reachable register map |
| 5 | Physical observation | Flip switch, watch cabinet | Fan/compressor stop; F4S display stays lit | Switch acts downstream of the F4S, not on its supply |
| 6 | Wiring trace (photos) | Open panel, trace from button to F4S | Contact-block stack behind the button; F4S Out 1A/1B on terminals 39–44 | Located the actual control element |
| 7 | Coil voltage | Multimeter, switch ON vs OFF | **24 V DC / 0 V — confirmed** | Extra-low-voltage control circuit; safe to interface with a DLS008 output |

**Conclusion:** the front station is a **24 V DC control-circuit device**. It gates the compressor/fan path downstream of the F4S. The F4S controller, its Modbus interface and its register map are untouched by it — proven independently by steps 3 and 4.

---

## 2. Corrections to the first draft of this document

The first pass got three things wrong. Recorded here so the error doesn't propagate into the build.

### 2.1 It is not a "3-relay block" — it is the contact stack behind the pushbutton

The three modules photographed are the **contact blocks clipped to the rear of the illuminated twin pushbutton**, not DIN-rail relays:

| Block | Marking | What it is | Wires seen |
|---|---|---|---|
| Left | `NO 3` / `4` | Normally-open contact — the **green I (start)** button | 100 in, 102 out |
| Middle | `X1` / `X2` | **Lamp / LED block** — the white illuminated centre section | 069, 105 |
| Right | `NC 1` / `2` | Normally-closed contact — the **red O (stop)** button | 100 in, 103 out |

`X1`/`X2` is the universal terminal designation for a pilot lamp, not a coil. **The middle block is an indicator, not the control element** — tapping it would achieve nothing. The control elements are the NO block (start) and the NC block (stop).

Wire `100` feeds both blocks — a common 24 V supply rail. `102` leaves the start contact, `103` leaves the stop contact.

### 2.2 The EL2869 cannot be driven from Python

The earlier draft showed `RPi.GPIO.output(EL2869_PIN, ...)`. That is not possible. The EL2869 is a **Beckhoff EtherCAT terminal** on the EK1100 coupler — it is not Raspberry Pi GPIO and has no GPIO pin number. It is reachable only through an EtherCAT master, and **CODESYS is already the EtherCAT master on this system**. A second master cannot share the bus.

**Consequence: the output must be commanded by CODESYS.** Python can *request* a state, but CODESYS *actuates* it. Both integration paths in §8 and §9 respect this.

### 2.3 Terminal numbers 48–50 are the F4S, not the EL2869

`48/49/50` came from the F4S nameplate (`Rxmit1`, the 10 V / 20 mA retransmit output). They have nothing to do with the EL2869. Real EL2869 terminal points must be read off the terminal's own label and the CODESYS I/O mapping — they are not assumed anywhere in this document.

---

## 3. What the front station actually is

Wire numbering (`100` common in, `102` out of NO, `103` out of NC) is the textbook signature of a **start/stop station driving a latch (seal-in) circuit**:

```
        ┌──── 102 ────┐
 24 V   │  green I    │
 (100) ─┼── [NO 3-4] ─┴──► latch coil ──┐   (seal-in contact holds it)
        │                               │
        └── [NC 1-2] ── 103 ────────────┘
           red O  (breaking 103 drops the latch)
```

The latching relay or contactor itself is **elsewhere in the panel** — it was not in the photographed area. Its coil is energised by a momentary pulse on `102` and held by its own auxiliary contact; breaking `103` drops it out.

This matters because it determines the whole wiring design, which is why §5 is the blocker.

---

## 4. Register scan: switch state is NOT in the F4S map

**Finding (28 July 2026):** Differential scan of registers 100–249 ON vs OFF shows **no state-dependent changes**. Only register [101] drifts by 2–3 counts (timer/counter noise). Registers 150–249 are all `33536 (-32000)` sentinel (unread/unused).

**Consequence:** The auxiliary contact of the latching relay is not wired to an F4S input terminal. Remote feedback of actual run state requires physical wiring:
- Option 1: Wire auxiliary contact → spare EL1409 DI channel (recommended, proven)
- Option 2: Trust commanded state (simple, but no proof)

The cabinet-on-off sequencer cannot read back actual run status from Modbus. It relies on commanded state until a dedicated feedback channel is installed.

---

## 5. ✅ CONFIRMED: Momentary buttons

**Finding (29 July 2026):** Both green (I/start) and red (O/stop) buttons spring back immediately when released.

**This confirms §3 topology:** The front station drives a latching relay via momentary start/stop contacts:
- Green NO button (3-4) energizes the latch coil on closure
- Red NC button (1-2) de-energizes the latch on opening
- Auxiliary contact holds the coil energized until the NC contact breaks

**Wiring design consequence:** Use §7 hybrid topology:
- **EL2869 CH1** → parallel tap across green NO contact (start pulse)
- **EL2869 CH2** → series in the red NC stop string (stop permission)
- Both channels required for full remote control with local authority preserved

---

## 6. Topology — and why pure "Option A" cannot switch the cabinet off

You selected Option A (parallel tap). Taken literally it does not meet the objective, and the reason is worth stating plainly:

> A contact wired **in parallel** produces OR logic. Either source can close the circuit, so either source can turn the cabinet **on** — but neither can turn it **off** while the other is holding it on. A pure parallel tap gives you **remote start only**. Remote stop is impossible by construction.

The fix is not to abandon Option A — it is to recognise that a start/stop station has **two** control elements, and each needs the opposite treatment:

| Function | Local element | Remote element | Logic |
|---|---|---|---|
| **Start** | Green NO `3-4` | Contact **in parallel** | OR — either can start |
| **Stop** | Red NC `1-2` (wire `103`) | Contact **in series** | AND — either can stop |

This is standard motor-starter practice and it gives exactly the behaviour you want:

- Local operator keeps **full** authority — the red button always stops the cabinet, regardless of what CODESYS is doing.
- Remote gets **full** authority — it can start and stop independently.
- Nothing is disconnected. Both taps are additive and reversible: remove two wires and the panel is exactly as it was.

```
 24 V (100) ─┬─ [green NO 3-4] ─┬─── 102 ──► latch coil
             │                  │
             └─ [K_REM_START] ──┘        (parallel — remote start)

 latch string ── [red NC 1-2] ── [K_REM_STOP] ── 103 ──►
                                 (series — remote stop, NC contact)
```

**Fail-safe consequence:** `K_REM_STOP` uses a **normally-closed** contact, so if the interposing relay loses its coil supply — DLS008 powered down, EL2869 pulled, wire broken — the contact **closes** and the local circuit works normally. A dead automation system degrades to a manual cabinet, not a stuck one. This is the correct failure direction.

---

## 7. Bill of materials

| Item | Spec | Notes |
|---|---|---|
| Interposing relay ×2 | 24 V DC coil, DIN rail, **integral freewheel diode**, volt-free changeover contact | e.g. Phoenix Contact PLC-RSC-24DC/21 or Finder 38-series. One provides the NO for start, one the NC for stop |
| EL2869 channels ×2 | Spare digital outputs on the existing DLS008 terminal | **Verify per-channel current rating against the relay coil draw before ordering** — do not assume |
| Cable | 2-core, screened, 0.5–0.75 mm², ELV rated | DLS008 → cabinet control enclosure |
| Ferrules + wire numbers | Continue the existing JTS numbering scheme | Label as e.g. `102A`, `103A` so the tap is obvious to the next engineer |

Why interposing relays rather than wiring the EL2869 straight into the circuit: galvanic isolation between the DLS008 24 V rail and the JTS control circuit, no loading of a circuit that isn't ours, and a volt-free contact that behaves identically to the button it parallels. It also keeps the modification entirely reversible.

---

## 7a. Wiring diagram and terminal assignments

**Cabinet control enclosure — existing JTS circuit:**

```
    24 V supply (rail 100)
         │
         ├──────────────────────────┬─────────────────────────┐
         │                          │                         │
    [Green button]            [K_REM_START coil]        [Red button NC]
    NO contact 3-4            (interposing relay)        contact 1-2
         │                    ×1 (24V DC)                    │
         ├─── wire 102 ──────────►K_REM_START:1              │
         │                                                   │
         └─────────────────────────┬──────────────────────────┘
                                   │
                          [K_REM_STOP coil]
                          (interposing relay)
                          ×1 (24V DC)
                                   │
                          ├─── wire 103 ──────────────► stop circuit

    Return: wire 101 to 24 V common (0 V reference)
```

**Remote tap points (from EL2869 output relays):**

| Function | Local element | Remote (EL2869) | Wiring |
|---|---|---|---|
| **START** | Green NO 3-4 | K_REM_START NO contact | Parallel across local 102 |
| **STOP** | Red NC 1-2 | K_REM_STOP NC contact | Series in local 103 line |

**EL2869 channel assignment (confirm actual terminal numbers from DLS008 label):**

- **CH_START** (e.g. term XX.1) → drives K_REM_START coil → maps to `GVL_HMI.xStartPulse` in CODESYS
- **CH_STOP** (e.g. term YY.1) → drives K_REM_STOP coil → maps to `GVL_HMI.xStopPermit` in CODESYS

Both relays share the 24 V supply (DLS008 power rail) and 0 V common. No separate 24 V circuit required.

---

## 9. Path 1 — CODESYS-native (recommended first)

CODESYS owns the EtherCAT master, so it drives the EL2869 directly. Command source is the watch window now, WebVisu later.

### Step 1 — Declare the interface

Add to `GVL_HMI` (operator-facing, kept separate from `GVL_Modbus` so the driver boundary stays clean):

```iec61131
{attribute 'qualified_only'}
VAR_GLOBAL
    xCabinetOnCmd    : BOOL;   (* operator/remote request: TRUE = run *)
    xCabinetRunning  : BOOL;   (* feedback, if a DI is fitted *)
    xStartPulse      : BOOL;   (* -> EL2869 ch A, parallels green button *)
    xStopPermit      : BOOL;   (* -> EL2869 ch B, TRUE = allow run      *)
    tOffLockRemain   : TIME;   (* anti-short-cycle countdown           *)
END_VAR
```

### Step 2 — Map the outputs

In the EL2869's **I/O Mapping** tab, map two spare channels:

- `xStartPulse` → channel A
- `xStopPermit` → channel B

Record the actual terminal points from the terminal label and add them to §7a of this document. Set **Always update variables = Enabled 1** and bus cycle task = **MainTask**, matching the Modbus configuration already proven in this project.

### Step 3 — Decide the stop-state behaviour

PLC Settings currently has **Behavior for outputs in stop = Keep current values**.

**Recommendation: leave it as "Keep current values."** A CODESYS download or runtime restart then does *not* trip a cabinet that is mid-test — which matters directly for ISO 15848-1 runs that take hours. The red button remains the operator's guaranteed stop. Changing this to "Set to default" would make every code download an unplanned cabinet shutdown.

### Step 4 — Sequencer with anti-short-cycle interlock

**This interlock is mandatory, not optional.** Software can command off→on far faster than a hand can, and a refrigeration compressor restarted against head pressure will fail. The interlock lives in CODESYS because CODESYS is the last element before the coil.

```iec61131
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

(* --- minimum off-time timer: runs whenever we are not running --- *)
tonOffLock(IN := NOT xRunLatch, PT := tOFFLOCK);
GVL_HMI.tOffLockRemain := tOFFLOCK - tonOffLock.ET;

(* --- STOP: break the series contact immediately, no interlock --- *)
(* Stopping is always allowed. Only starting is ever delayed.       *)
GVL_HMI.xStopPermit := GVL_HMI.xCabinetOnCmd;

IF NOT GVL_HMI.xCabinetOnCmd THEN
    xRunLatch := FALSE;
END_IF

(* --- START: rising edge, but only once the off-lock has expired --- *)
IF GVL_HMI.xCabinetOnCmd AND NOT xCmdPrev AND tonOffLock.Q THEN
    tonStartPulse(IN := FALSE); (* reset *)
    tonStartPulse(IN := TRUE, PT := tPULSE);
    xRunLatch := TRUE;
END_IF
xCmdPrev := GVL_HMI.xCabinetOnCmd;

tonStartPulse(IN := xRunLatch AND GVL_HMI.xCabinetOnCmd, PT := tPULSE);
GVL_HMI.xStartPulse := tonStartPulse.IN AND NOT tonStartPulse.Q;
```

Note the asymmetry: **stop is instant, start is gated.** Never delay a stop.

### Step 5 — Operate from the watch window

Same prepare-then-write workflow as the setpoint work: set `GVL_HMI.xCabinetOnCmd` in the **Prepared value** column, `Ctrl+F7` to commit. Watch `xStartPulse` produce a 1 s pulse, and the cabinet fan start.

---

## 10. Path 2 — Python-originated command through the gateway

Extends the existing register map so a command can originate from Python (script, cron, test sequencer) while CODESYS still does the actuating. This is the path that eventually lets a test script run the cabinet unattended.

### Step 1 — Extend the gateway register map

Two new registers in `f4s_gateway.py`, following the existing pattern exactly:

| TCP reg | Direction | Meaning |
|---|---|---|
| 5 | write | On/off command: 0 = stop, 1 = run |
| 6 | read | On/off state echo: what the gateway currently believes was requested |

Register 5 is a plain holding register, **not** a self-clearing trigger like register 1 — it is a level, not an event. CODESYS reads it cyclically and treats it as the requested state.

### Step 2 — Add the CODESYS read channel

New channel on the Modbus TCP Slave:

| # | Access | Trigger | READ off | Maps to |
|---|---|---|---|---|
| 5 | Read Holding Registers (FC03) | Cyclic 1000 ms | `16#0005` | `GVL_Modbus.wOnOffCmd` |

Map the **element row**, type WORD, as with every other channel in this project.

### Step 3 — Feed it into the same sequencer

```iec61131
(* Python request OR local CODESYS request; the sequencer in Path 1
   still owns the interlock, so this adds a source, not a bypass. *)
GVL_HMI.xCabinetOnCmd := (GVL_Modbus.wOnOffCmd = 1) OR xLocalHmiRequest;
```

Path 2 deliberately does **not** get its own actuation route. Every command, wherever it comes from, funnels through the one sequencer that holds the anti-short-cycle interlock. One interlock, one place, no way around it.

### Step 4 — Command it from Python

```python
from pymodbus.client import ModbusTcpClient

def set_cabinet(run: bool, host="10.1.6.17"):
    """Request cabinet run/stop. CODESYS performs the actuation."""
    with ModbusTcpClient(host, port=502) as c:
        c.write_register(5, 1 if run else 0, device_id=1)

def cabinet_state(host="10.1.6.17") -> bool:
    with ModbusTcpClient(host, port=502) as c:
        return c.read_holding_registers(6, count=1, device_id=1).registers[0] == 1
```

A request is not a confirmation. Register 6 echoes what was *asked for*; proof that the cabinet actually started is the fan, or a DI fitted to the latch auxiliary contact.

---

## 11. Test plan

Run with the cabinet empty — no valve under test — until T8 passes.

| # | Test | Method | Pass criterion |
|---|---|---|---|
| T1 | Local start unaffected | Green button, automation powered but idle | Cabinet starts as before |
| T2 | Local stop unaffected | Red button while running | Cabinet stops immediately |
| T3 | Remote start | `xCabinetOnCmd := TRUE` | Fan starts within ~1 s; pulse is one-shot |
| T4 | Remote stop | `xCabinetOnCmd := FALSE` | Fan stops immediately |
| T5 | Local stop overrides remote | Remote commanding run, press red | Cabinet stops and **stays** stopped |
| T6 | Anti-short-cycle | Stop, then immediately command start | Start refused; `tOffLockRemain` counts down; start occurs only after it expires |
| T7 | Fail-safe | Pull the EL2869 / power down DLS008 while running | Local buttons still work; cabinet controllable manually |
| T8 | CODESYS restart | Download new code while cabinet running | Cabinet keeps running (per §9 step 3) |

---

## 12. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Remote start does nothing | Pulse too short for the latch to pick up | Increase `tPULSE` to 2 s; confirm relay actually closes with a meter |
| Cabinet starts then immediately stops | Latch not sealing in, or the stop string is open | Verify `xStopPermit` is TRUE *before* the start pulse, not after |
| Remote stop does nothing | Stop relay wired parallel instead of series, or an NO contact used where NC is required | Meter across the relay contact — must be **closed** when permitted, **open** to stop |
| Cabinet cannot be started at all after wiring | `K_REM_STOP` sitting open because CODESYS is stopped or the channel is unmapped | Confirm the NC contact closes with the coil de-energised — this is the fail-safe check from §6 |
| Start command accepted but nothing happens for minutes | Anti-short-cycle interlock active — working as designed | Watch `tOffLockRemain` |
| Everything green in CODESYS, output never changes | Bus cycle task "unspecified", or *Always update variables* disabled | Same failure mode as the Modbus work — set task = MainTask |
| Register 5 writes accepted, CODESYS never sees them | Channel 5 not added, or element row not mapped | Compare against the working channels 0–4 |
| Relay chatters | DO channel current below relay coil inrush, or missing freewheel diode | Check the EL2869 rating against the coil; use a relay with an integral diode |

---

## 13. Open items

1. **Momentary or maintained buttons?** (§5) — blocks the wiring design
2. **Where do wires `102` and `103` terminate?** — confirms the latch circuit
3. **EL2869 per-channel current rating** vs chosen relay coil — verify against the Beckhoff datasheet before ordering
4. **Is a run-feedback DI wanted?** A spare EL1409 channel on the latch auxiliary contact would turn `xCabinetRunning` from an assumption into a measurement. Recommended — without it, the system commands but never confirms, which is the exact weakness the setpoint work fixed with read-back
5. **JTS/DLS008 schematic** still not in the repo — would confirm §3 without a physical trace

---

## 14. Reference

| Item | Value |
|---|---|
| Cabinet | Left Hand Small Temperature Cabinet, JTS Ltd |
| Controller | Watlow F4S, F4SH-CCA0-01RG, SN 038983 |
| Control circuit | 24 V DC, confirmed by measurement 28 July 2026 |
| Front station | Illuminated twin pushbutton — NO `3-4` (start), lamp `X1-X2`, NC `1-2` (stop) |
| Wire numbers | `100` common feed, `102` start out, `103` stop out, `069`/`105` lamp |
| Output module | Beckhoff EL2869 on EK1100, EtherCAT — **driven by CODESYS only** |
| Runtime | CODESYS Control for Linux ARM64 SL, Raspberry Pi 10.1.6.17 |
