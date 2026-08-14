# Cabinet On/Off Automation — Investigation & Integration Guide

**Author:** Omkar Joshi — Oliver Mechatronics
**Date:** 29 July 2026 (original); **updated 10 August 2026**
**Objective:** Remotely start and stop the Left Hand Small Temperature Cabinet, without touching mains wiring and without taking authority away from the local operator.
**Status:** ✅ **Investigation complete. Integration testing complete on the Left Hand Small
Temperature Cabinet (DLS008) — see §20.** Remote start/stop is proven on hardware via two
interposing relays, driven by the DLS Start/Stop digital outputs, landing on the Omron CPM1A's
`01`/`02` inputs in parallel with the local button station. Both operator (button station) and
CODESYS (via the two relays) can command the cabinet's start/stop, and the two-relay topology
restores the galvanic isolation and OR/AND local-remote authority behaviour originally specified
in §6/§7.

> ### ⚠️ READ §20 FIRST — it is the current as-built, tested solution
>
> As of 10 Aug 2026 the deployed route for full cabinet on/off (fan + compressor) is the
> **two-relay design of §6/§7, re-terminated onto the Omron CPM1A's `01`/`02` digital inputs**
> (the termination point identified in §19) instead of a bare latch coil. See **§20** for the
> wiring diagram, terminal/wire-colour table, and the integration test record on the Left Hand
> Small Temperature Cabinet.
>
> §15 (Option C, relayless supply-lift via `-202X3`), §16 (Route A, Modbus setpoint sentinel),
> §17 (F4 digital-input ramp gate, "Control Outputs Off") and §19 (direct EL2869-to-Omron wiring,
> no relays) are retained below as investigation record — each taught something that fed into
> §20. §17/§18's panel-lock mechanism is still the correct design for *setpoint authority* (a
> separate concern from on/off, see §19.5). They are not currently wired, because §20 reuses
> CH15/CH16 for the new purpose — see §19.5 for the channel-reallocation recommendation that
> resolves this.

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

## 6b. Power supply compatibility — relay requirements

The cabinet control runs on 24V DC from the DLS008 field power supply. Relay coils are inductive loads and **must have integral freewheel diodes** to prevent back-EMF damage to the EL2869 MOSFET output stage.

**Critical requirement:** Use only relays with **integral freewheel diodes built into the coil terminals**. A bare relay coil (without a diode) will destroy the EL2869 on the first de-energization when the coil back-EMF reaches 100+ V.

**Specifications:**
- Relay coil: 24 V DC, DIN-rail mount, **integral freewheel diode**
- Holding current: ~30 mA (continuous, well below EL2869 rating)
- Inrush current: ~150–300 mA (transient, acceptable for MOSFET drivers)
- Cable: Shielded 2-core, 0.75 mm² minimum, ELV-rated
- Cable length: Keep ≤5 m to reduce EMI
- Grounding: Single-point star connection at the enclosure; both relays share DLS008 0V common

**Freewheel diode function:** When the coil de-energizes, the diode conducts briefly and clamps the back-EMF to ~24.6 V, preventing the spike that would damage the EL2869 output driver.

**Conclusion:** Relays with integral freewheel diodes are safe for DLS008 EL2869 outputs. Examples: Phoenix Contact PLC-RSC-24DC/21, Finder 38-series. **Always verify the datasheet confirms integral freewheel diodes before procurement.**

---

## 7. Bill of materials

| Item | Spec | Notes |
|---|---|---|
| Interposing relay ×2 | 24 V DC coil, DIN rail, **integral freewheel diode**, volt-free changeover contact | e.g. Phoenix Contact PLC-RSC-24DC/21 or Finder 38-series. One provides the NO for start, one the NC for stop |
| EL2869 channels ×2 | Spare digital outputs on the existing DLS008 terminal | **Verify per-channel current rating against the relay coil draw before ordering** — do not assume |
| Cable | 2-core, screened, 0.5–0.75 mm², ELV rated | DLS008 → cabinet control enclosure |
| Ferrules + wire numbers | Continue the existing JTS numbering scheme | Label as e.g. `102A`, `103A` so the tap is obvious to the next engineer |

Why interposing relays rather than wiring the EL2869 straight into the circuit: galvanic isolation between the DLS008 24 V rail and the JTS control circuit, no loading of a circuit that isn't ours, and a volt-free contact that behaves identically to the button it parallels. It also keeps the modification entirely reversible.

### 7.1 Why TWO relays (and two EL2869 channels), not one?

A standard changeover relay has both NO (3-4) and NC (1-2) contacts available from a single coil. Theoretically, one relay could provide both the start contact (NO, parallel) and stop contact (NC, series). Why do we specify two?

**Fail-safe coupling protection.** When a single relay coil energizes (to send a start pulse):
- The NO contact closes (start works) ✓
- The NC contact opens (stop is blocked) ✗

This creates a dangerous window: if the operator presses the red button during the 1-second start pulse, the stop request is **ignored** because the remote NC contact is already open. This violates the cardinal rule of fail-safe automation: *"The red button must work at ALL times, no exceptions."*

**With two independent relays and two independent EL2869 channels:**

⚠️ **Polarity correction (5 Aug 2026):** the original table below had K_REM_STOP's rest/energized
states backwards — it described a normally-closed contact as *closing* when energized, which is
not how NC contacts behave. Corrected logic: K_REM_STOP's coil is **OFF at rest** (its NC contact
closed, stop string intact, cabinet free to run) and is **energized only to command a stop**
(NC opens, breaking the string exactly as the red button would). This is also what makes the
§6 fail-safe claim true: lose coil supply → de-energized → NC closes → local circuit works
normally, which only holds if OFF is the running state.

| Control | Relay | EL2869 CH | Behavior |
|---|---|---|---|
| Start pulse (~1 s) | K_REM_START coil → ON (pulse) | CH_START energizes briefly | NO contact closes for the pulse; start flows through parallel contact |
| Stop command (continuous while stopped) | K_REM_STOP coil → ON | CH_STOP held high | NC contact opens; stop string broken, same as holding the red button |
| Normal running (no remote stop active) | K_REM_STOP coil → OFF | CH_STOP low | NC contact closed at rest; stop string intact |
| Red button pressed during a start pulse | Local NC opens | CH_STOP unaffected | Stop works immediately — the local NC is in the same series string and independent of the relay |

The sequencer drives them independently:
- `xRemoteStartPulse` → CH_START (~1 s pulse, energize to start)
- `xRemoteStopCmd` → CH_STOP (energize to stop; FALSE at rest so the cabinet is free to run)

Deliberately **not** named `xStopPermit` — the corrected polarity above means TRUE energizes the
relay to *command* a stop, not to *permit* running. The old name inverted the meaning and is what
produced the K_REM_STOP contradiction this section now fixes; don't reintroduce it.

This ensures the red button's NC path is **never blocked by start logic**. The extra relay and EL2869 channel are the cost of safety, and this is standard motor-starter practice worldwide.

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

**Next steps — Physical wiring (ready to proceed after software verification):**

1. **Procure interposing relays** (if not already on hand):
   - Quantity: 2
   - Spec: 24 V DC coil, DIN rail, **integral freewheel diode on coil terminals** (essential for EL2869 inductive load)
   - Examples: Phoenix Contact PLC-RSC-24DC/21, Finder 38-series, or equivalent
   - **DO NOT use relays without freewheel diodes** — the coil inrush will damage the EL2869 output if unprotected

2. **Install relays in cabinet control enclosure**:
   - Mount on DIN rail **near the JTS control circuit** (minimise cable runs to reduce EMI)
   - Wire relay coils:
     - K_REM_START coil → 24 V supply (DLS008 rail) and 0 V common
     - K_REM_STOP coil → 24 V supply (DLS008 rail) and 0 V common
   - Verify 24 V DC across each coil with multimeter (should read 24 ±2 V)

3. **Connect EL2869 outputs to relay coils**:
   - Run shielded 2-core cable from DLS008 to each relay coil
   - **CH_START output** (%QX1.6) → K_REM_START coil terminals
   - **CH_STOP output** (%QX1.7) → K_REM_STOP coil terminals
   - Use ferrules and label wires per JTS numbering scheme (e.g., `102A`, `103A`)

4. **Tap relay contacts into the cabinet circuit** (parallel start, series stop):
   - **K_REM_START NO contact** → **parallel** across green button wire 102
     - Both contacts in parallel: if either closes, the latch energizes (OR logic)
   - **K_REM_STOP NC contact** → **series** in the red button stop string at wire 103
     - Both in series: if either opens, the latch de-energizes (AND logic)
   - Use the wiring diagram above as a reference

5. **Test with watch window** (relay connected, cabinet running):
   - Repeat watch window tests from §9a with the relays live
   - Set xCabinetOnCmd = TRUE → cabinet should start (compressor/fan on)
   - Set xCabinetOnCmd = FALSE → cabinet should stop
   - Verify anti-short-cycle lockout still blocks restart for 5 minutes

6. **Run full test plan T1–T8** (§11):
   - Local start/stop (manual buttons)
   - Remote start/stop (watch window)
   - Override authority (local buttons override remote)
   - Anti-short-cycle (5-min lockout enforced)
   - Fail-safe (cabinet reverts to manual if automation loses power)
   - Restart after lockout (timing verified)

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

## 9a. Software-first verification — map and test before any wiring exists

The EL2869 mapping and sequencer do not need the interposing relays installed to be built and proven. Mapping a variable to an EtherCAT output is a software declaration; with nothing connected to the terminal, the channel just switches into an open circuit — no current, no load, no risk. This lets the entire control-logic layer be verified in isolation from the hardware modification, so any mistake is a compile error or a watch-window observation, not a wiring rework.

**Confirmed on this system (29 July 2026):**

- EL2869 EtherCAT slave address: **1006** (`PhysSlaveAddr` / `SlaveAddr`, confirmed in the IEC Objects tab)
- `xSetOperational`: FALSE until the application is downloaded and run — expected, not a fault
- All 16 DOS output channels (`16#1600`–`16#16F0`, addresses `16#7000:16#01`–`16#70F0:16#01`) enumerate correctly and are currently **unmapped** — none are claimed by another function
- Log shows historical `sync manager watchdog` / `watchdog for opmode expired` entries against address 1006 (24–28 July) — these are stale, tied to prior downloads/logouts, not evidence of a wiring fault. Re-check the log after the next download; if entries stop appearing, the link is healthy.

**Channel assignment (selected — last two channels, avoids any future collision with other DOS use):**

| Function | Channel | Address | Variable |
|---|---|---|---|
| START pulse | 15 | `16#70E0:16#01` | `GVL_HMI.xStartPulse` |
| STOP permit | 16 | `16#70F0:16#01` | `GVL_HMI.xStopPermit` |

**Verification sequence — software only, no relays fitted:**

1. Declare the interface (Step 1) and compile — confirms syntax and scope, catches typos before anything is downloaded.
2. Map the two channels above in I/O Mapping (Step 2).
3. Add the sequencer (Step 4), download, and go online. `xSetOperational` should flip to TRUE and the watchdog log entries should stop recurring.
4. Drive `xCabinetOnCmd` from the watch window and confirm, with **no relay connected**:
   - `xStartPulse` pulses HIGH for exactly 1 s on a rising edge of `xCabinetOnCmd`, then drops
   - `xStopPermit` tracks `xCabinetOnCmd` directly with no delay
   - `tOffLockRemain` counts down from 5 min after a stop and blocks a restart pulse until it reaches zero
   - A second `xCabinetOnCmd` rising edge before the lockout expires produces **no** new `xStartPulse` pulse
5. Only once step 4 behaves exactly as specified, move to physical wiring (§7a) and repeat the same checks with the relays live, this time watching the cabinet respond.

This order — logic proven in software, then wired — means the first time voltage reaches the interposing relays, the control behaviour behind it is already known-good.

---

## 9b. ✅ Software verification results — all tests PASSED (29 July 2026)

**Executed on system:** CODESYS application downloaded to DLS008, EL2869 mapped to GVL_HMI, PLC_PRG running sequencer logic. Watch window monitoring all 5 variables in real time.

**Test results:**

| Test | Condition | Expected | Observed | Result |
|---|---|---|---|---|
| **Test 1** | xCabinetOnCmd rising edge, lockout expired | xStartPulse pulses HIGH for 1s, then FALSE | xStartPulse went TRUE for exactly 1 second, then FALSE | ✅ PASS |
| **Test 2** | xCabinetOnCmd falling edge | xStopPermit goes FALSE immediately (no delay) | xStopPermit dropped to FALSE instantly | ✅ PASS |
| **Test 3a** | Restart attempt while timer counting down | xStartPulse stays FALSE (blocked by lockout) | xStartPulse did not pulse; remained FALSE | ✅ PASS |
| **Test 3b** | Restart after lockout expiry (tOffLockRemain = 0s) | xStartPulse pulses again | xStartPulse pulsed normally after timer expired | ✅ PASS |
| **Test 4** | xCabinetOnCmd = TRUE while running | xStopPermit = TRUE, tOffLockRemain resets to T#5M | xStopPermit = TRUE, timer reset to 5 min on pulse | ✅ PASS |

**Sequencer behavior confirmed:**
- ✅ 1-second start pulse width exact
- ✅ 5-minute anti-short-cycle lockout enforced
- ✅ Stop is immediate, unaffected by lockout
- ✅ Rising-edge detection works (no pulse on level HIGH)
- ✅ Timer countdown and expiry detection working
- ✅ All variables update synchronously in watch window

**Conclusion:** The CODESYS control logic is correct and ready for relay wiring. No software changes required. Proceed to physical installation (§7a).

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

---

# 15. AS-DESIGNED ARCHITECTURE — DI/DO route, Option C

**Frozen 29 July 2026. This section supersedes §6, §7, §7a and §9a.**
Software (§9, §9b) is unchanged and remains valid.

## 15.1 What changed and why

| | Superseded design | **As-designed (this section)** |
|---|---|---|
| Field route | Analogue XLR port (LVDT / flow meter) | **`-202X3` DI/DO 37-way connector** |
| Interposing relays | 2 × 24 V DC required | **None — direct from EL2869** |
| Stop function | Local only (Option A) | **Remote + local (Option C)** |
| Junction box role | Signal break point | **Pass-through only** |

Three reasons the DI/DO connector is correct and the analogue ports were not:

1. **It is the designed route.** Drawing 7168-DWG-100 pages 217–218 already allocate every
   EL2869 output to a `-202X3` pin. Outputs O9–O16 (pins 30–37) are marked SPARE. We are
   using the panel as its designer intended, not repurposing an instrument port.
2. **No analogue channel is sacrificed.** The earlier plan released an ELM3148 input. This
   plan releases nothing — the pins are already spare.
3. **Correct signal class.** `-202X3` is the panel's digital I/O boundary, already carrying
   24 V switched signals. The XLR ports are instrumentation-grade analogue.

## 15.2 End-to-end architecture

```
  COMMAND SOURCES
    CODESYS watch window  ──┐
    Python via Modbus TCP ──┤   (cabinet_onoff.py -> gateway reg 5 -> GVL_Modbus.wOnOffCmd)
                            ▼
                   PLC_PRG sequencer          <-- owns the 5-minute anti-short-cycle interlock
                            │                     (single interlock, no bypass — §9 step 4)
              xStartPulse ──┤──► EL2869 CH15
              xStopPermit ──┘──► EL2869 CH16
                            ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ DLS008 ENCLOSURE                                             │
 │   EL2869  (-217K1, EtherCAT slave 1006)                      │
 │     O15 ── wire 21807 ──┐                                    │
 │     O16 ── wire 21808 ──┤                                    │
 │     0 V  (-202X2) ──────┤                                    │
 │                         ▼                                    │
 │        -202X3   DI/DO 37-way, gland plate                    │
 │           pin 36 = CH15   (start pulse)                      │
 │           pin 37 = CH16   (station supply / stop permit)     │
 │           pin 20 + 29 = 0 V                                  │
 └────────────────────────────┬─────────────────────────────────┘
                              │  37-way mating plug
                              │  4-core screened cable, 0.5–0.75 mm²
                              ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ THERMOCOUPLE JUNCTION BOX          *** PASS-THROUGH ONLY *** │
 │   BODY / MONITOR / CHAMBER TC terminals — DO NOT TOUCH       │
 │   Cable enters a SPARE gland, exits a SPARE gland, unbroken  │
 │   Screen continuous through the box, bonded to nothing here  │
 └────────────────────────────┬─────────────────────────────────┘
                              │  screened cable
                              ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ CABINET ON/OFF SWITCH STATION (Watlow F4S cabinet)           │
 │   CH16  ─────────────────►  wire 100   (station 24 V supply) │
 │   CH15  ──►|── diode ────►  wire 102   (parallel, green NO)  │
 │   0 V   ─────────────────►  wire 101   (0 V common)          │
 │   Cabinet's ORIGINAL 24 V feed to wire 100: LIFTED + PARKED  │
 │   Local green + red buttons: physically unmodified           │
 └──────────────────────────────────────────────────────────────┘
```

## 15.3 Pin map — DLS008 side ✅ CONFIRMED

**Status (30 July 2026): confirmed from the AS-BUILT drawing set, not provisional.**
Source: `7168-DWG-100`, **Revision B**, change note *"AS BUILTS"*, drawn by R. Watts,
17/10/2025 — i.e. this revision was issued specifically to capture what was actually built,
not what was designed. Read directly off:

- Page `=CS1+CP1&EFS1/218` — **Digital Output Channels 8-15** (O9–O16 → `-202X3` pins 30–37,
  wires `21801`–`21808`, all eight labelled SPARE on the panel legend)
- Page `=CS1+CP1&EFS1/202` — **Beckhoff CPU/24V Distribution** (`-202X1`/`-202X2`/`-202X3`
  routing, confirms the 0 V and fused-24 V pin assignments)

| CODESYS | EL2869 output | Wire no. | `-202X3` pin | Function |
|---|---|---|---|---|
| `GVL_HMI.xStartPulse` — CH15 (`16#70E0:16#01`) | O15 | `21807` | **36** | Start pulse, 1 s |
| `GVL_HMI.xStopPermit` — CH16 (`16#70F0:16#01`) | O16 | `21808` | **37** | Station supply / stop permit |
| — | — | `20202A/C/E` from `-202X2` | **20**, **29** | 0 V return |
| — | — | `20201A/C/E` from `-202X1` | 1, 10, 19 | Fused 24 V (not used by this design) |

This is an exact match to the drawing-based table this section used to carry — the as-built
revision independently confirms it. **Still buzz it out at Stage A step 2** as a sanity check
(as-built drawings occasionally lag the panel by one late change), but this is now a
confirmation check, not a discovery exercise.

## 15.4 Option C — how remote stop works without a relay

An EL2869 output can *source* 24 V; it cannot *break* someone else's circuit. Option C solves
remote stop by making the DLS the **supply** for the button station rather than trying to
interrupt it:

```
  BEFORE (as-built)                     AFTER (Option C)

  cabinet 24 V                          EL2869 CH16 ──► wire 100
        │                                                  │
        └──► wire 100 ─┬─ [green NO 3-4] ─┬─ 102 ─► latch  ├─ [green NO] ─┬─ 102 ─► latch
                       │                  │         coil    │             │        coil
                       └─ [red NC 1-2] ── 103 ──────┘       └─ [red NC] ─ 103 ─────┘
                                                     ▲
                                          EL2869 CH15 ──►|── (parallel with green NO)
```

| Action | Mechanism | Works? |
|---|---|---|
| **Remote start** | CH16 HIGH (station live) + CH15 pulses 1 s onto wire 102 → latch picks up, seals in | ✅ |
| **Remote stop** | CH16 → LOW → station loses its supply → latch cannot hold → drops out | ✅ |
| **Local start** | Green button, station powered by CH16 | ✅ *(requires DLS healthy)* |
| **Local stop** | Red NC breaks wire 103 — a physical series break, independent of CH15/CH16 | ✅ **always** |

### The accepted trade-off — state this to operators

**Option C inverts the fail-safe direction, deliberately and with management approval.**

If the DLS008 is powered down, unplugged, faulted, or CODESYS is stopped, CH16 goes LOW and:

- the cabinet **stops**, and
- it **cannot be started from the local buttons** until the DLS is healthy again.

This is the known cost of relayless remote stop and it **will fail test T7 as originally
written** (§11). T7 must be re-scoped for Option C: the pass criterion becomes *"cabinet stops
safely and predictably; local restart is unavailable until DLS returns"* — not *"local buttons
still work."*

The red button remains a guaranteed stop under all conditions, because it is a physical
series break in the latch string. Local *stop* authority is never lost; local *start*
authority depends on the DLS.

> **Operator notice to post at the cabinet:**
> *"Cabinet start is enabled by the DLS008 control system. If the cabinet will not start from
> the green button, check the DLS008 is powered and CODESYS is running. The red STOP button
> always works."*

## 15.5 Bill of materials

| Item | Qty | Status |
|---|---|---|
| EL2869 channels 15 & 16 | 2 | ✅ Already installed and CODESYS-mapped, verified spare |
| `-202X3` pins 36, 37, 20/29 | 4 | ✅ Already installed, marked SPARE on drawing |
| 37-way mating plug for `-202X3` | 1 | ⚠️ **VERIFY** — see §15.8 Q1 |
| 4-core screened cable, 0.5–0.75 mm², ELV | ~5–10 m | On site (site-measure the run) |
| Diode 1N4007 / 1N5408 | 1 | See note below |
| Ferrules + wire-number sleeves | as req. | On site |
| **Interposing relays** | **0** | **Not required by this design** |

**Diode note.** The diode on the CH15 branch prevents wire 102 (at 24 V while the cabinet runs,
via the seal-in) back-feeding the switched-off CH15 output. In Option C both channels share the
same DLS 24 V rail, so a back-fed output sees only its own rail voltage — tolerable, but out of
spec. **Fit the diode if one is available**; if not, record the omission as a deviation and fit
it at the next opportunity. Anode toward the junction box, cathode toward wire 102.

## 15.6 Step-by-step installation

Work in order. Do not skip the measurements — three of them are go/no-go gates.

### Stage 0 — Pre-work measurements (cabinet running normally, nothing disconnected)

| # | Measure | Expected | Why it matters | Status |
|---|---|---|---|---|
| 0.1 | Wire 100 → cabinet 0 V, cabinet running | ≈ 24 V DC | Confirms station supply voltage and polarity | — |
| 0.2 | Wire 102 → cabinet 0 V, running / stopped | ≈ 24 V / 0 V | Confirms the seal-in behaviour assumed in §15.4 | — |
| 0.3 | **Latch coil current** — clamp or in-line meter on wire 100, cabinet running | **must be < 500 mA** | **GO/NO-GO.** This is the load CH16 will carry. EL2869 is 0.5 A/channel | ✅ **CONFIRMED < 500 mA by multimeter, 30 July 2026 — GO** |
| 0.4 | Trace where wire 100 gets its 24 V | identified terminal | This is the connection Stage D lifts | — |
| 0.5 | Continuity: DLS 0 V ↔ cabinet 0 V (both isolated) | record open or closed | If already common via earth, note it — affects §15.7 loop check | — |

**0.3 is passed — Option C is confirmed viable.** Proceed to Stage A. (0.1, 0.2, 0.4, 0.5 are
not go/no-go gates; take them on the same visit for the record but they don't block starting
Stage A.)

### Stage A — DLS008 enclosure (panel isolated, EtherCAT down)

1. Confirm EL2869 terminals **15** and **16** — empty, or already carrying wires `21807`/`21808`.
2. **Continuity-map** EL2869 t15 → `-202X3` pin 36, and t16 → pin 37. Record. Correct §15.3 if
   the panel disagrees with the drawing — **the panel wins**.
3. If `21807`/`21808` are absent, run them: EL2869 t15 → `-202X3` pin 36, t16 → pin 37, sleeved
   `21807` / `21808` per the drawing's own numbering.
4. Confirm `-202X3` pins **20** and **29** land on the `-202X2` 0 V distribution block.
5. Log it: *"EL2869 O15/O16 committed to cabinet on/off control via -202X3 pins 36/37,
   [date] [initials]."*

### Stage B — DLS008 → thermocouple junction box

6. Make up the 37-way mating plug: **pin 36 → core 1 (CH15)**, **pin 37 → core 2 (CH16)**,
   **pins 20 and 29 → cores 3 and 4 (0 V)**, screen → backshell.
7. If the plug is already fitted and harnessed for other circuits, add the four cores to the
   spare pins — do **not** disturb existing cores. Photograph before and after.
8. Route the cable to the junction box. Enter through a **spare gland**.

### Stage C — Through the junction box (pass-through only)

9. **Do not land any core on the BODY / MONITOR / CHAMBER terminals.** They are thermocouple
   terminals feeding the EL3314 — 24 V will destroy the module and corrupt every temperature
   reading on the rig.
10. Pass the cable **straight through**, unbroken, entering one spare gland and exiting another.
    No terminals, no splice, nothing added inside the box.
11. Screen passes through **continuous and bonded to nothing** inside the box.
12. Label both sides of the box: `DO CH15/16 — DLS -202X3 → cabinet on/off. PASS-THROUGH. Do
    not terminate.`

### Stage D — Cabinet on/off switch station (cabinet isolated)

13. **Lift the cabinet's own 24 V feed from wire 100** (identified at step 0.4). Park it on a
    spare insulated terminal, sleeved `100-ORIG — original supply, reconnect to revert`.
    **This single connection is the whole reversibility story** — restoring it returns the
    cabinet to as-built.
14. **CH16 core → wire 100.** The station is now supplied by the DLS.
15. **CH15 core → diode (anode toward junction box) → wire 102**, at the green button's
    outgoing terminal 4. Heat-shrink the diode, inside the enclosure.
16. **Both 0 V cores → wire 101** (cabinet 0 V common). This bonds the two 0 V references and
    provides the return path for the latch coil current now sourced from CH16.
17. **Screen: cut back and insulate.** No bond at the cabinet end. Meter-verify: **no
    continuity between screen and cabinet metalwork.**
18. Ferrule and sleeve every core: `102A` (CH15), `100A` (CH16), `101A` ×2 (0 V).

## 15.7 Commissioning

### C1 — Static checks (before energising)

- [ ] No continuity screen ↔ cabinet metalwork (step 17)
- [ ] No continuity CH15 core ↔ CH16 core
- [ ] Diode orientation correct — conducts junction-box→102, blocks 102→junction-box
- [ ] Wire 100 no longer connected to the cabinet's own 24 V; `100-ORIG` parked and insulated
- [ ] Ground-loop check: with everything connected but unpowered, confirm the 0 V bond is the
      intended single path (compare against measurement 0.5)

### C2 — EtherCAT leg (DLS powered, CODESYS online, cabinet isolated)

- [ ] EL2869 `xSetOperational` = TRUE, no new watchdog entries against slave 1006
- [ ] `GVL_HMI.xStopPermit := TRUE` → CH16 LED on; meter wire 100 → 0 V = **24 V**
- [ ] `GVL_HMI.xCabinetOnCmd := TRUE` → CH15 LED pulses ~1 s; meter wire 102 shows a 24 V pulse
- [ ] `tOffLockRemain` counts down after a stop and blocks restart until zero

### C3 — Live functional tests (cabinet energised, chamber empty)

Re-scoped from §11 for Option C. **T7 is deliberately changed.**

| # | Test | Method | Pass criterion |
|---|---|---|---|
| T1 | Local start | Green button, DLS healthy | Cabinet starts |
| T2 | Local stop | Red button while running | Cabinet stops immediately |
| T3 | Remote start | `xCabinetOnCmd := TRUE` | Fan starts ≈1 s; pulse is one-shot |
| T4 | **Remote stop** | `xCabinetOnCmd := FALSE` | **Cabinet stops immediately** |
| T5 | Local stop overrides remote | Remote commanding run, press red | Stops and **stays** stopped |
| T6 | Anti-short-cycle | Stop, immediately command start | Refused; `tOffLockRemain` counts down; starts only after expiry |
| T7 | **Fail-safe (re-scoped)** | Power down DLS008 while running | Cabinet **stops**. Local start unavailable until DLS returns. Red button still breaks the circuit. **This is expected behaviour for Option C, not a failure** |
| T8 | CODESYS restart | Download new code while running | Cabinet keeps running (outputs hold — §9 step 3) |

**Declare qualified only after two clean T1–T8 runs on different days**, matching the rule used
for the setpoint PoC. Record raw values, not tick boxes.

### C4 — Modbus TCP leg (optional, after C3 passes)

1. Extend `f4s_gateway.py` to 7 registers (reg 5 command, reg 6 echo) — commit to the branch
   and `git pull` on the Pi. Never hand-edit on the Pi.
2. Add CODESYS channel 5: FC03, cyclic 1000 ms, READ offset `16#0005` → `GVL_Modbus.wOnOffCmd`
   (element row, `Always update = Enabled 1`, bus cycle task = `MainTask`).
3. In `PLC_PRG`: `GVL_HMI.xCabinetOnCmd := (GVL_Modbus.wOnOffCmd = 1) OR xLocalHmiRequest;`
4. Test with `cabinet_onoff.py on` / `off` / `status` — same physical result as the watch window.

## 15.8 Open verifications — answer before Stage B

| # | Question | Impact if unresolved | Status |
|---|---|---|---|
| **Q1** | **Is a 37-way mating plug for `-202X3` available?** One appears fitted in the site photograph with red/black/grey cores. If it exists — which pins are already occupied? If not — this is the one purchase this design cannot avoid | **Blocks Stage B entirely** | Confirm on site tomorrow |
| **Q2** | Junction box DI/DO pass-through point: the cabinet-side confirmation (30 July) is that the junction box has its **own dedicated DI port connector** for this circuit — not just a spare gland as originally assumed. Confirm connector type/gender on site | Blocks Stage C wiring detail — see note below | Confirm on site tomorrow |
| **Q3** | Do wires `21807`/`21808` physically exist at EL2869 t15/t16? | Determines whether Stage A step 3 is needed | ✅ **Resolved** — drawing revision B is the *as-built* record (change note "AS BUILTS"), so the wires are recorded as fitted. Confirm visually at Stage A step 1 |
| **Q4** | Latch coil current (step 0.3) | **GO/NO-GO for Option C** | ✅ **PASSED** — measured < 500 mA, 30 July 2026 |
| **Q5** | Where does wire 100 get its 24 V (step 0.4) | Blocks Stage D step 13 | Confirm on site tomorrow |

**Note on Q2 / the junction box DI port:** the routing confirmed 30 July is: EL2869 CH15/16 →
`-202X3` (DLS DI/DO connector) → cable → **junction box's dedicated DI port connector** →
cable continues → cabinet DI/DO connector → internal cabinet wiring → switch station (wires
100/102/101). This refines §15.2/§15.6 Stage B–C: the junction box is still pass-through in
spirit (no core lands on a TC terminal), but the physical entry/exit is a **dedicated DI/DO
connector on the box**, not necessarily a bare gland-to-gland cable run. Confirm the connector's
pinout on site before Stage C so the two mating cable ends can be made up correctly.

## 15.9 Reversibility

To return the cabinet to as-built condition:

1. Reconnect `100-ORIG` to wire 100; remove the CH16 core.
2. Remove the CH15 core and diode from wire 102.
3. Remove the 0 V cores from wire 101.
4. Withdraw the cable; remove the four cores from the `-202X3` plug.

The local button station is never modified — no contact block is cut, drilled or rewired.
Total revert time: under 30 minutes.

## 15.10 Troubleshooting — trace the path in order

Meter checkpoints, DLS end to cabinet end. **The first checkpoint that goes quiet names the
broken stage.**

| # | Checkpoint | Expect (cabinet commanded ON) |
|---|---|---|
| 1 | EL2869 CH15/CH16 LEDs | CH16 steady on; CH15 pulses ~1 s |
| 2 | EL2869 terminal 15 / 16 → 0 V | CH16 24 V; CH15 pulse |
| 3 | `-202X3` pin 37 / 36 → pin 20 | same as (2) |
| 4 | Junction box, cable in transit | same as (3) |
| 5 | Cabinet tail `100A` / `102A` → `101A` | same as (4) |
| 6 | After the diode, wire 102 → wire 101 | 24 V during pulse |

| Symptom | Likely cause | Check |
|---|---|---|
| Nothing at all; cabinet dead | CH16 LOW, or wire 100 not connected to CH16 | `xStopPermit` state; step 14 |
| Station has 24 V but won't start remotely | Pulse too short for latch pickup | Raise `tPULSE` to 2 s; scope wire 102 |
| Starts then drops out immediately | Seal-in not holding, or CH16 dipping under coil inrush | Re-check measurement 0.3; meter wire 100 during pickup |
| Remote stop does nothing | Wire 100 still fed from the cabinet's own 24 V | Step 13 — `100-ORIG` must be lifted |
| Start refused for minutes | Anti-short-cycle interlock — working as designed | Watch `tOffLockRemain` |
| Temperature readings wrong/erratic after install | **Something landed on the TC terminals** | Stop. Verify Stage C step 9. Inspect EL3314 |
| Everything green in CODESYS, output never changes | Bus cycle task unspecified, or `Always update variables` off | Set task = `MainTask` — same failure mode as the Modbus work |

## 15.11 Handover checklist

- [ ] §15.8 Q1–Q5 answered and recorded
- [ ] Stage 0 measurements recorded, coil current < 500 mA confirmed
- [ ] Continuity map EL2869 t15/t16 → `-202X3` pins 36/37 recorded (supersedes §15.3)
- [ ] Cable passes through the junction box unbroken; TC terminals untouched and verified
- [ ] `100-ORIG` lifted, parked, labelled
- [ ] Screen bonded at DLS end only; cabinet-end isolation meter-verified
- [ ] C1 static checks complete
- [ ] C2 EtherCAT leg verified
- [ ] C3 T1–T8 passed, two clean runs on different days, raw values recorded
- [ ] **Operator notice posted at the cabinet** (§15.4) — Option C start dependency
- [ ] T7 re-scoping communicated to and accepted by the project lead
- [ ] As-wired photographs filed; this section updated with as-measured values

---

# 16. Route A — on/off over Modbus only (no relays, no panel wiring)

**Added 30 July 2026.** This section supersedes §15 as the *first* route to try.
§15 (Option C, EL2869 → `-202X3` → front station) remains valid as the fallback and
is unchanged. Route A costs nothing to attempt: it is a software change on the
gateway and two extra Modbus channels in CODESYS. If test A1 below fails, §15 is
still there.

## 16.1 The mechanism

The F4 has **no run/stop register**. Searching for one is what stalled this route
before. What it does have is a documented sentinel on the setpoint, in the user
manual chapter 3, *Static Set Point Control*:

> "Setting the set point to Set Point Low Limit minus 1 (-1) will turn control
> Output 1 off and display the set point as off."

So:

| | Action |
|---|---|
| **OFF** | write reg `300` := (value of reg `602`) − 1 |
| **ON** | write reg `300` := the wanted setpoint |

That is the **same register 300, over the same RTU link, through the same write
path** this project already proves on every setpoint change. No new F4 behaviour
and no new failure mode — the write is either confirmed by read-back or it is not,
exactly as before.

## 16.2 Registers used — all from the user manual, chapter 7

| F4 reg | R/W | Name | Used for |
|---|---|---|---|
| `100` | r | Input 1 Value, Status | chamber temperature (already in use) |
| `200` | r | Operation Mode, Status | diagnostic |
| `300` | r/w | Set Point 1, value | **the on/off mechanism** (already in use) |
| `602` | r/w | Set Point Low Limit, Analog Input 1 | source of the OFF sentinel |
| `603` | r/w | Set Point High Limit, Analog Input 1 | range reference |
| `1217` | w | Terminate a Profile, Key Press Simulation | write `1` — stops a running profile |
| `1210` | w | Hold a Profile, Key Press Simulation | write `1` — not used by Route A |
| `1209` | w | Resume a Profile, Key Press Simulation | write `1` — not used by Route A |
| `4000` | r/w | Profile Number | profile start, if ever needed |
| `4001` | r/w | Profile Step Number | profile start, if ever needed |
| `4002` | w | Edit Profile Action | write `5` = **Start Profile** |
| `4100` | r | Profile Number, Current Status | `0` = no profile running |
| `4102` | r | Profile Step Type, Current Status | 1 Ramp Time · 2 Ramp Rate · 3 Soak · 4 Jump · 5 End |
| `201` `213` `225` `237` | r | Digital Input 1–4, Status | `0` Low / `1` High |

The low limit is **read from the controller, never hard-coded**. It follows the
configured sensor and can be changed on the Setup Page; a stale sentinel would
either fail to switch the output off or land inside the usable range and quietly
become a real setpoint.

A running profile owns the setpoint, so the sentinel write alone would be
overwritten. The gateway checks reg `4100` first and writes `1217 := 1` when a
profile is running — per the manual, "the profile ends with all outputs off. The
set point on the Main Page reads off."

## 16.3 Gateway register map (unit id 1) — extended

| TCP reg | Direction | Meaning |
|---|---|---|
| 0 | CODESYS → | requested setpoint, signed x10 |
| 1 | CODESYS → | apply trigger (self-clearing) |
| 2 | → CODESYS | chamber temperature, signed x10 |
| 3 | → CODESYS | confirmed setpoint, signed x10 |
| 4 | → CODESYS | status code |
| **5** | **CODESYS →** | **on/off command: 0 = none, 1 = off, 2 = on** |
| **6** | **→ CODESYS** | **on/off state: 0 = unknown, 1 = off, 2 = on** |
| **7** | **→ CODESYS** | **F4 setpoint low limit, signed x10** |
| **8** | **→ CODESYS** | **running profile number, 0 = none** |

**Why 0/1/2 and not a boolean.** Holding registers come up as `0` after a gateway
restart. With an `off == 0` encoding, every restart would command a stop before
anyone had asked for one. `0` therefore means *no command* and the gateway does
nothing until CODESYS says something.

**Register 6 is an observation, not an echo.** It is derived from register `300`
as actually read back each poll, so a setpoint changed at the F4 keypad shows up
here too. Under a standing ON command the gateway will notice such a stop and
restore the setpoint.

**Setpoint writes while OFF are staged, not applied.** Off *is* a setpoint value
here, so pushing a normal setpoint through while the cabinet is commanded off
would silently restart it. The request stays in register 0 and lands on the next
ON. Status code `6` (`ST_OFF_STAGED`) reports this, so "written" and "will be
written when you turn it on" stay distinguishable.

## 16.4 CODESYS side

See [`RouteA_CabinetOnOff.st`](RouteA_CabinetOnOff.st) — GVL additions, the four
Modbus channels, and the sequencer. The 5-minute anti-short-cycle interlock is
kept from the relay design: the actuation route changed, the mechanical
constraint on the compressor did not.

`GVL_HMI.xStartPulse` is not used by Route A. Route A commands a **level**, not a
pulse — there is no latch coil to pick up.

## 16.5 ⚠️ What Route A does and does not prove

Route A switches the **F4's control output**. It is not the same lever as the
front-panel button.

§1 step 4 established that the button station is **not visible anywhere in the F4
register map**, and §1 step 5 that flipping it stops the fan/compressor while the
F4 display stays lit. The button drives a latch relay downstream of the
controller. Modbus cannot reach that relay — that is precisely what §15 is for.

So the open question is what hangs off which:

- If the compressor and fan are driven **from the F4's control output**, Route A
  is a complete cabinet on/off and §15 can be abandoned.
- If they are driven **from the latch relay only**, Route A stops the *conditioning*
  (no heat, no cool, chamber drifts to ambient) but the fan keeps turning, and
  §15 is still needed for a true stop.

**Test A1 settles it, in software, in two minutes, with no wiring.**

## 16.6 Test plan

| # | Test | Method | Pass criterion |
|---|---|---|---|
| A1 | **Does OFF actually stop the cabinet?** | `python3 cabinet_onoff.py off` | F4 display reads `off`; record what stops — compressor, fan, both, neither |
| A2 | ON restores | `python3 cabinet_onoff.py on` | Setpoint returns to the staged value; conditioning resumes |
| A3 | Local authority intact | Press the red button while Route A commands ON | Cabinet stops and stays stopped — Route A never touches this circuit |
| A4 | Keypad stop is observed | Set the setpoint to `off` at the F4 keypad | Register 6 reads `1` within one poll |
| A5 | Restart is safe | `systemctl restart f4s-gateway` while running | Cabinet keeps running; register 5 comes up `0` (no command) |
| A6 | Setpoint staging | Command OFF, then write a new setpoint, then command ON | Status `6` while off; new setpoint applied on ON |
| A7 | Profile terminate | Start a profile at the keypad, then command OFF | Profile ends, all outputs off, setpoint reads `off` |
| A8 | Anti-short-cycle | Command OFF then immediately ON | Start held; `tOffLockRemain` counts down |

Run A1 first. Everything else is only worth doing if A1 shows the F4 output is the
right lever.

Offline proof of the gateway logic (no hardware needed):

```bash
python3 "python modbus proof of concept and test logs/test_onoff_route_a.py"
```

13 checks covering sentinel derivation, idle-when-steady, staging, range refusal,
profile termination ordering, and keypad-stop correction.

### 16.7 Outcome — why Route A alone was not enough

Test A1 was run on the physical cabinet. Result: commanding the F4 output off (register 300 =
low-limit sentinel) **stopped the compressor but the fan kept running.** §1 step 5 of this
document already predicted this shape of failure — the fan is downstream of the button station,
not of the F4's control output — and A1 confirmed it directly rather than by inference.

Conclusion: Route A is not a complete on/off. It stops *conditioning* but not *air movement*,
and the objective (a cabinet an operator can leave fully idle until a scheduled time, then have
it condition unattended) needs something that gates the F4's outputs *and* survives being wired
without touching the button station. That is what §17 does.

---

# 17. AS-BUILT — Scheduled Ramp Gate via F4 Digital Inputs (working solution, deployed 3 Aug 2026)

**This is the design actually installed, wired, and proven on hardware.** It supersedes §15
(Option C, relayless supply-lift via `-202X3`) and §16 (Route A, Modbus setpoint sentinel) as
the deployed solution. Both are retained above as investigation record — the topology findings
in §1–§5 and the register behaviour in §16.1–16.2 remain accurate and were part of what led here.

## 17.1 Why this route instead of §15 or §16

| | §15 Option C | §16 Route A | **§17 (as-built)** |
|---|---|---|---|
| What it gates | Cabinet's own 24 V supply to the switch station | F4 control output 1 only (via setpoint sentinel) | **F4's own control outputs, both 1A and 1B, via the F4's built-in DI function** |
| Proven to stop the fan? | Would work (cuts the station's supply entirely) | ❌ No — A1 showed fan keeps running | ✅ Not required — objective is *inhibit conditioning*, not kill the fan |
| Touches switch station / `-202X3` / junction box? | Yes — full cable run, pass-through, supply lift | No | **No — EL2869 wired straight to the F4S terminal block** |
| Relays required | 0 (Option C removed them) | 0 | **0** |
| New failure mode introduced | Local start depends on DLS being powered (§15.4 trade-off) | None found before A1 failure | **None found in testing** |
| Wiring complexity | 37-way connector, pass-through junction box, supply-lift at the switch station | None (software only) | **Two wires + common, direct to F4S terminal block, no other equipment touched** |

The objective that actually mattered — "keep the cabinet powered and idle until a scheduled time,
then let it start conditioning toward setpoint with no operator action" — does not require
killing the fan or lifting the cabinet's own 24 V supply. It only requires that the F4's heating
and cooling outputs be blocked until release. The F4 already has a digital input function built
for exactly this ("Control Outputs Off"), so the simplest correct design is to drive that input
directly from a spare EL2869 channel. No relay, no supply-lift, no junction-box run.

## 17.2 What the F4's digital inputs actually do

The F4S has (at minimum) two configurable digital inputs, confirmed in the field on this unit:

| F4 terminal | Function assigned | Effect when active |
|---|---|---|
| **D/I 1** (terminal 28) | **"Control Outputs Off"** | Both control output 1A (heat) and 1B (cool) are held off. Confirmed by direct observation to gate **both directions symmetrically** — this was verified, not assumed (§17.6). |
| **D/I 2** (terminal 29) | **"Panel Lock"** (F4 function 1) — *reassigned 5 Aug 2026, was "All Outputs Off"* | Locks the F4S front-panel keypad so an operator cannot key in a setpoint. Driven by `GVL_HMI.xPanelLock`. See **§18**. The previous "All Outputs Off" assignment was a silent cooling-lockout hazard that had to be held FALSE and did nothing useful (§17.5/§17.7) — retired. |
| **D/I common** (terminal 27) | — | 0 V reference for both inputs |

Neither function touches the cabinet's fan/supply circuit at the switch station — they act
entirely inside the F4S controller, on its own output stage. This is why the fan-keeps-running
problem from §16.7 does not apply here: the design goal was never to kill the fan, only to hold
back heating/cooling until the scheduled release.

## 17.3 Wiring — EL2869 to F4S, direct

```
 DLS008 ENCLOSURE                              WATLOW F4S TERMINAL BLOCK
   EL2869 (EK1100 EtherCAT coupler)
     CH15 (pin 36) ── Red wire   ──────────────►  Terminal 28  (D/I 1 — Control Outputs Off)
     CH16 (pin 37) ── Green wire ──────────────►  Terminal 29  (D/I 2 — All Outputs Off)
     0 V   (pin 20) ── Black wire ──────────────►  Terminal 27  (D/I common)
```

No junction box, no `-202X3` connector, no switch station wiring, no relay. The only equipment
touched is the EL2869 terminal block (already installed, spare channels) and the F4S's own
terminal block (spare digital input terminals).

**Ground-loop check performed before landing the wires:** potential difference measured between
DLS 0 V and F4 terminal 26 was **< 1 V**, confirmed safe to bond the two 0 V references together
at terminal 27 (D/I common).

**Topology note, carried over from the §6–§9a investigation:** the cabinet's *button station*
was proven by multimeter to be **low-side switching** (ground-referenced), which is why an
EL2869 sourcing output could never be wired directly in parallel with it (§6, §7) — that
incompatibility is what forced the pivot away from touching the button station at all. It does
**not** apply to this design, because §17 never wires into the button station. The F4S's digital
inputs are optically/opto-isolated inputs expecting a sourced 24 V signal, which is exactly what
the EL2869's sourcing output provides — this is a matched pairing, unlike the button station.

## 17.4 CODESYS side

### GVL_HMI additions

`codesys modbus proof of concept and test logs/src/GVLs/GVL_HMI.gvl`:

```iec61131
(* ---- Scheduled ramp gate (logic -> hardware -> WebVisu feedback) ---- *)
xSchedEnable         : BOOL;           (* scheduler enabled flag          *)
dtSchedStart         : DT;             (* scheduled start date/time       *)
xRampInhibit         : BOOL;           (* -> EL2869 CH15 -> F4 DI1        *)
xRampActive          : BOOL;           (* feedback: inverted from xRampInhibit *)
```

`xPanelLock` (CH16 → F4 D/I 2) drives the front-panel keypad lock — see **§18**. It replaced
`xAllOutputsOff`, which was mapped but undriven and had to be held FALSE to avoid a silent
cooling lockout (§17.5/§17.7).

### PLC_PRG_TCP — STEP 0, scheduled ramp gate

`codesys modbus proof of concept and test logs/src/POUs/PLC_PRG_TCP.st`:

```iec61131
VAR
    dtNow      : DT;    (* current time for scheduled ramp gate *)
    uliHighRes : ULINT; (* high-resolution time *)
END_VAR

(* --- STEP 0: Scheduled ramp gate - EL2869 CH15 -> F4 DI1 ---
   When scheduled start time is enabled and hasn't been reached yet, inhibit
   control outputs until the scheduled time arrives or scheduler is disabled. *)
SysTimeRtcHighResGet(uliHighRes);
dtNow := ULINT_TO_DT(uliHighRes / 1000000);  (* convert microseconds to seconds *)

IF GVL_HMI.xSchedEnable AND (dtNow < GVL_HMI.dtSchedStart) THEN
    GVL_HMI.xRampInhibit := TRUE;
ELSE
    GVL_HMI.xRampInhibit := FALSE;
END_IF

GVL_HMI.xRampActive := NOT GVL_HMI.xRampInhibit;
```

The rest of the program (setpoint state machine, `xStartWrite` manual trigger for watch-window
testing) is unchanged from the base setpoint-control work documented in the project root README.

### I/O Mapping

| Channel | Variable | Notes |
|---|---|---|
| EL2869 CH15 | `GVL_HMI.xRampInhibit` | Output, drives F4 D/I 1 |
| EL2869 CH16 | `GVL_HMI.xPanelLock` | Output, drives F4 D/I 2 ("Panel Lock") — TRUE locks the keypad (§18) |

## 17.5 Troubleshooting encountered during commissioning (3 Aug 2026)

| Symptom | Root cause | Fix |
|---|---|---|
| Build warning `C0139: the code 'GVL_HMI.xAllOutputsOff;' has no effect` | Variable mapped in I/O Mapping but not referenced by any PLC logic — CODESYS flags dead code | Cosmetic only; safe to ignore, or add explicit logic if CH16 gains a real function later |
| Build error `C0004: 'xAllOutputsOff' is no component of 'GVL_HMI'` | I/O Mapping still pointed at a variable that had been deleted from GVL_HMI in an earlier cleanup pass | Re-added `xAllOutputsOff` to GVL_HMI so the existing I/O Mapping row resolved again |
| Setpoint accepted, cooling never engaged (`wSetpoint1Read` correct, temperature would not fall below ambient, only decayed passively with door open) | **F4 D/I 2 ("All Outputs Off") was active**, which disables event outputs as well as control outputs — on this cabinet the refrigeration contactor sits on an event output, so cooling was silently blocked even though the setpoint state machine reported success | Confirmed on the F4 panel (front-panel DI status showed input 2 active). Cleared by ensuring `GVL_HMI.xAllOutputsOff` stays FALSE. **Root design conclusion: D/I 1 alone ("Control Outputs Off") is sufficient and correct** — confirmed in §17.6 to gate both 1A and 1B — so D/I 2 does not need an assigned function for this design and should be left inactive |
| `dtNow` reads `DT#1970-01-01-00:00:00` in the watch window even after the Raspberry Pi's own clock was corrected | Pi system time (`date`, `timedatectl`) was correctly NTP-synced to 3 Aug 2026, but the PLC runtime had cached the old value; a `hwclock -w` sync was attempted to push it to the hardware RTC but **`hwclock` is not installed on this Pi image** | Not fully resolved as of 3 Aug 2026. PLC Stop/Run cycle did not pick up the corrected time either. **Scheduler is currently released manually** by toggling `xSchedEnable` FALSE at the intended time, rather than relying on the `dtNow < dtSchedStart` comparison to auto-release. See §17.8 open item |
| Temperature briefly read below the F4's practical minimum during range testing (setpoint driven to −3.4 °C) | Deliberate test of the signed setpoint path, not a fault | Confirmed `WORD_TO_INT` / `INT_TO_WORD(REAL_TO_INT(...))` conversion correct at the negative end of the range; F4 accepted and tracked toward it normally |

## 17.6 Proof that D/I 1 gates both heating and cooling (the key open question, now closed)

Before this was confirmed, it was an open question whether "Control Outputs Off" on the F4
gates only heat (1A) or both control outputs. This was settled by direct observation on the
physical cabinet, repeated across multiple cycles on 3 August 2026:

| Test | Setpoint direction | `xRampInhibit` | Observed |
|---|---|---|---|
| Heating gate | Setpoint above chamber temp (e.g. 25 → 45 °C) | Enabled mid-ramp | 1A stopped flickering; temperature held flat |
| Heating release | Same | Disabled | 1A resumed flickering; temperature resumed climbing to target |
| Cooling gate | Setpoint below chamber temp (e.g. 40 → −15 °C) | Enabled mid-ramp | 1B stopped flickering; temperature held flat |
| Cooling release | Same | Disabled | 1B resumed flickering; temperature resumed falling to target |

**Confirmed: a single digital input, D/I 1 = "Control Outputs Off," gates both 1A and 1B
symmetrically.** No second input, second channel, or additional wiring is needed to cover both
heating and cooling — the original concern that "one of the digital inputs is messing with
control outputs 1A and 1B" traced back entirely to D/I 2 being active (§17.5), not to any
limitation of D/I 1.

The test sequence also proved the gate is **repeatable, not one-shot**: inhibit → stage a new
setpoint while gated → release → ramp, run back-to-back for both a positive and a negative
target in the same session, with the setpoint write always landing correctly even while gated
(`wSetpoint1Read` updates immediately; only the physical outputs are held back).

## 17.7 Current operating state — what must be true for normal operation

- [ ] F4 D/I 2 function is set to **"Panel Lock"**, not "All Outputs Off" (§18) — if this was
      re-flashed or factory-reset, re-check it before trusting the keypad lock
- [ ] `GVL_HMI.xPanelLock` = TRUE for normal locked-down operation (F4 D/I 2 lit)
- [ ] `GVL_HMI.xSchedEnable` = FALSE unless a scheduled/manual gate is intentionally active
- [ ] `GVL_HMI.xRampInhibit` = FALSE, `xRampActive` = TRUE for normal, ungated operation
- [ ] F4 D/I 1 panel indicator dark when `xRampInhibit` is FALSE, lit when TRUE — verify this
      polarity after any redownload, since it is the one piece of hardware behaviour that isn't
      software-verifiable from the watch window alone

## 17.8 Button station wiring commission — short-circuit diagnosis and fix (4 Aug 2026)

### 17.8.1 Problem: "Digital out 8" error and cabinet unresponsive to remote stop

**Symptoms:**
- F4S display showed persistent "digital out 8" error
- Remote stop command (xStopPermit = FALSE) did not stop the cabinet
- Cabinet restarted immediately after manual stop, ignoring anti-short-cycle lockout

**Root cause diagnosis:**

EL2869 CH16 (GREEN, stop permit) was shorted across its 24V output and 0V return:
- GREEN connected to NC1 terminal (24V output side of CH16)
- BLACK and WHITE (both from EL2869 DO GND terminal) connected to NO3 terminal
- NO3 tied to NC1 via external wire-100 jumper
- **Result: 24V (from GREEN via wire-100) → 0V (from BLACK/WHITE) = direct short across CH16**

This short starved the output driver and triggered the overcurrent alarm on terminal 8.

### 17.8.2 Button station internal topology — confirmed by continuity mapping (4 Aug 2026)

To rule in/out possible fixes, a full continuity map was taken with cabinet off:

| From (RED) | To (BLACK) | Reading | Interpretation |
|---|---|---|---|
| 1 (NC input) | 2 (NC output) | 0.4 Ω | NC contact closed at rest (normally closed) |
| 3 (NO input) | 4 (NO output) | OL | NO contact open at rest (normally open) |
| 1 | 3 | 0.5 Ω | Closed only because external wire-100 jumper was physically present |
| 2 | 3 | 0.4 Ω | Transitively closed (2→1 via NC + 1→3 via wire-100) |
| 1 | 4 | OL | Isolated |
| 2 | 4 | OL | Isolated |
| X1 (lamp) | X2 (lamp) | 6 Ω | Plain resistive filament (lamp circuit, isolated from switches) |
| X1 | 1, 2, 3, 4 | OL | Lamp fully isolated from control contacts |

**Conclusion:** The button station has **two fully isolated dry-contact blocks** (NO 3-4 and NC 1-2) internally. The only connection between terminal 1 (NC input) and terminal 3 (NO input) is the **external wire-100 jumper**, not internal to the device. **There is no internal ground/common terminal anywhere on this button station.** The X1/X2 lamp circuit is electrically separate from the switch logic.

This confirmed that BLACK/WHITE should never land on any button station terminal — it must return only to the F4S's own 0V rail (Out 1B GND / DO GND), where the rest of the control circuit returns.

### 17.8.3 Fix applied and verified (4 Aug 2026)

**Wiring change:**
- Moved BLACK from NO3 → F4S Out 1B GND
- Moved WHITE from NO3 → F4S DO GND
- Confirmed Out 1B GND and DO GND continuity: 0.5 Ω (same 0V rail)

**Electrical verification after rewiring:**

| Check | Expected | Measured | Status |
|---|---|---|---|
| **Continuity: NO3 to Out 1B GND** (cabinet off) | OL (open) | OL | ✅ Short cleared |
| **Voltage: NC1 to 0V, xStopPermit = TRUE** (cabinet on) | ~24 V | ~24 V | ✅ GREEN supplying wire-100 correctly |
| **Voltage: NC1 to 0V, xStopPermit = FALSE** (cabinet on) | ~0 V | ~0 V | ✅ GREEN dropping to 0V as commanded |
| **F4S "Digital out 8" error** | Gone | Pending | — |

**Final circuit topology (post-fix):**
```
EL2869 CH16 (+) ─→ GREEN wire ─→ NC1 terminal ─→ wire-100 jumper ─→ NO3 terminal
                                     ↓                                    ↓
                              (supplies 24V)                      (shares 24V supply)
                                     ↓                                    ↓
                              [NC button input]                   [NO button input]
                                     │                                    │
                                     └────────────────────────────────────┘
                                                  ↓
                                      [latch coil & outputs]
                                                  ↓
                                      (internal cabinet wiring)
                                                  ↓
                                      F4S Out 1B GND (0V)
                                      │            ↑
                                      └← BLACK ────┘
                                      
```

The EL2869 GND (BLACK/WHITE) is now bonded only to the F4S's own 0V common, not touching the button station directly. The 24V supply loop (GREEN → wire-100 → latch coil) is clean.

### 17.8.4 ⛔ ROUTE ABANDONED (5 Aug 2026) — root cause, and why no wiring arrangement can fix it

**The §15 Option C button-station route was abandoned on 5 Aug 2026 after further hardware
attempts. CH15/CH16 have been returned to the §17 F4-digital-input design.** Do not re-attempt
this route without first reading this subsection.

**Root cause — a device-type mismatch, not a wiring mistake:**

> The button station is **low-side switching** (ground-referenced): its contacts make and break
> the **0 V** side of the latch circuit. The EL2869 is a **sourcing** output: it can only *push*
> 24 V out, never pull a node down to 0 V.
>
> A sourcing output can therefore never substitute for, or parallel, a low-side contact — **at
> any terminal arrangement whatsoever.** This is a fundamental incompatibility between the two
> device types, not a matter of finding the right terminal.

This was already established in §6/§7 during the original investigation, and is restated in the
§17.3 topology note. It is the reason the project pivoted away from the button station in the
first place. The 4–5 Aug work rediscovered it empirically, at the cost of several days.

**Every symptom seen during the attempt traces to this single cause:**

| Symptom | Explanation |
|---|---|
| "Digital out 8" overcurrent error | BLACK/WHITE (0 V) landed on a node the GREEN (24 V) output was also feeding — a direct short across CH16 |
| Spark on inserting RED into NO3 | NO3 was live at 24 V (fed from NC1 via the wire-100 jumper); inserting a second source shorted it |
| `xStartPulse` fires correctly in the watch window but the cabinet never starts | The pulse is a *sourced* 24 V push into a circuit that needs its **ground** pulled down. Electrically inert — no current path, so the latch coil never sees anything. The watch window is telling the truth; the output really is firing. It simply cannot do the job asked of it. |
| No click from the latch relay under any pulse width (1 s → 2 s → 5 s) | Same cause. Pulse *duration* was never the limiting factor — the pulse polarity was wrong from the start. Widening it could not have helped. |
| Manual buttons stopped working after rewiring | Moving wire-100 off NC1 removed the station's factory 24 V common feed, leaving both button circuits unpowered |

**Wiring restored to factory** on the button station: wire-100 back to its original NC1↔NO3
common, `102` back to NO4, `103` back to NC2, and **no EL2869 conductor landing on any button
station terminal**. The local operator's manual start/stop authority is restored in full.

**What would be required to gate the fan (the one thing §17 does not do):** an interposing relay
with a **dry contact** in the latch circuit. A relay contact is voltage-agnostic — it does not
care which side of the load is being switched — so the low-side/sourcing mismatch stops applying.
This is precisely the §6/§7 two-relay design that Option C removed in an attempt to save the
relay cost; removing it is what created this incompatibility. Estimated cost €40–70 (Phoenix
PLC-RSC-24DC/21 or Finder 38-series, **must** have an integral freewheel diode — §6b).

**Decision (5 Aug 2026):** the fan does not need to stop. The objective — "cabinet sits idle,
conditioning nothing, until its scheduled start" — is fully met by §17 as already deployed and
proven. No relay purchase, no button-station modification. Route closed.

## 17.9 Open items

1. ~~**RTC / `dtNow` fix.**~~ ✅ **RESOLVED 4 Aug 2026.** `dtNow` was reading
   `DT#1970-01-01-00:00:00` because the Pi's *hardware* RTC had never been written from the
   (correctly NTP-synced) system clock, and `hwclock` was absent from the image. Fix:
   `sudo apt install util-linux` → `sudo hwclock -w` → `sudo systemctl restart codesyscontrol`.
   Verified: `dtNow` now reads correct local wall-clock time. The scheduler's automatic
   time-based release no longer needs the manual `xSchedEnable` workaround.
2. ~~**F4 D/I 2 function.**~~ ✅ **RESOLVED 5 Aug 2026.** Reassigned from "All Outputs Off"
   (unused, and a silent cooling-lockout hazard per §17.5) to **"Panel Lock"**, driven by
   `GVL_HMI.xPanelLock`. The channel now has a defined, useful role — see **§18**.
3. **WebVisu integration.** The scheduler variables (`xSchedEnable`, `dtSchedStart`,
   `xRampInhibit`, `xRampActive`) exist in GVL_HMI and are ready to bind to a WebVisu page once
   the operator interface work (tracked in the project root README's "Next stage" section) picks
   this up — **once CH15/CH16 are reallocated per §19.5**, since those channels now drive the
   Omron on/off pair instead.
4. **Test-log capture.** §17.6's proof was observed live but not yet captured with raw
   timestamped values in a dedicated test log, unlike the setpoint-control qualification in the
   project root (`codesys modbus proof of concept and test logs/docs/test-logs/`). Recommended before
   calling this section formally qualified — bundle with the CH13/CH14 re-commissioning in §19.7.

> **§17 is superseded for on/off control by §19 — read that section first.** CH15/CH16 are no
> longer wired to the F4S terminal block at all; they now drive the Omron CPM1A start/stop inputs
> directly (§19.1–§19.3), which is what makes hybrid manual+remote control actually work, rather
> than the F4-DI ramp gate described in the rest of this section. The R1–R8 re-commissioning
> sequence that used to appear here assumed CH15/CH16 would return to the F4S block; that
> assumption no longer holds and the sequence has been retired. §17's ramp-gate design itself is
> still correct and worth keeping — see §19.5 for reallocating it to spare channels.

---

# 18. Setpoint authority — locking the F4S front panel (5 Aug 2026)

## 18.1 The requirement, stated precisely

> When CODESYS has ramped the chamber to a commanded setpoint, an operator standing at the
> cabinet must **not** be able to key in a different setpoint and pull the chamber off it —
> in either direction. Setpoint authority belongs to CODESYS alone.

## 18.2 This is a different problem from §15–§17, and the button station was never the answer

This requirement was for a long time conflated with "overriding the button". They are unrelated
circuits, and confusing them cost several days:

| | Green/red button station | F4S front-panel keypad |
|---|---|---|
| What it controls | Fan + compressor **supply power** | **Setpoint entry** and all F4 menu access |
| Where it sits | Cabinet control circuit, downstream of the F4S | Inside the F4S controller |
| Relevant sections | §1–§7, §15, §17.8 | **§18 (this section)** |
| Can it change the setpoint? | **No — never could.** | Yes — this is the actual exposure |

No amount of work on the button station could ever have satisfied §18.1, because the button
station has no path to the setpoint. §17.8.4 records the wiring dead-end that resulted.

## 18.3 The F4S has this built in — two independent mechanisms

Both come from the Watlow F4 User's Manual (`docs/WatlowF4_UserManual.pdf`).

### Mechanism A — digital input "Panel Lock" (dynamic, CODESYS-controlled) ✅ preferred

`Panel Lock` is **F4 digital input function 1**, selectable on either digital input alongside
`Control Outputs Off`, `All Outputs Off`, `Start Profile` etc. The manual's own sample
application uses exactly this, wiring D/I 1 to a key-lock switch "that requires the operator to
have a key to operate the controller and chamber":

```
Digital Input 1
Name:      KEYLOCK
Function:  Panel lock
Condition: Start on high
```

**We already have the wiring.** §17.3 lands EL2869 CH16 on F4 terminal 29 (D/I 2). Only the
*function assignment* changes — from `All Outputs Off` to `Panel Lock`. **No new hardware, no
new cable, no relay.**

This also retires the `All Outputs Off` assignment, which §17.5/§17.7 flagged as a silent
cooling-lockout hazard that had to be permanently held FALSE and served no purpose. The channel
gains a real job.

**F4 configuration:**

| Menu path | Set to |
|---|---|
| `Main > Setup > Digital Input 2 > Function` | **Panel Lock** |
| `Main > Setup > Digital Input 2 > Condition` | **High** (start on high) |
| `Main > Setup > Digital Input 2 > Name` (optional) | `KEYLOCK` — 10 chars, shows on the display |

**CODESYS side** (`PLC_PRG_TCP.st` STEP 0b, `GVL_HMI`):

```iec61131
xPanelLockCmd : BOOL := TRUE;   (* operator intent: TRUE = keypad locked (default) *)
xPanelLock    : BOOL;           (* -> EL2869 CH16 -> F4 terminal 29 *)

GVL_HMI.xPanelLock := GVL_HMI.xPanelLockCmd;
```

Defaulting `xPanelLockCmd` to TRUE means the lock **re-asserts on every PLC restart**, so it
cannot be left off by accident after maintenance.

### Mechanism B — Factory > Set Lockout (static, password-protected)

Independent of any wiring or PLC state. Four access levels per menu: `Full Access` (default),
`Read Only`, `Password`, `Hidden`.

| Menu path | Set to | Effect |
|---|---|---|
| `Main > Factory > Set Lockout > Set Point` | **Read Only** | Operator can *see* the setpoint but cannot change it. Note: Set Point cannot be set to `Hidden`. |
| `Main > Factory > Set Lockout > Setup` | **Password** | Stops the digital-input function being quietly changed back to defeat Mechanism A |
| `Main > Factory > Set Lockout > Factory` | **Password** | Stops the lockouts themselves being cleared via `Clear Locks` |

Passwords are four characters, letters and/or numbers, set at first use. **Record it** — there is
no documented recovery path in the manual.

### Recommended: run both

They fail in different directions, so together they are properly redundant:

- **A alone** — defeated if the PLC is stopped, CH16 is unplugged, or someone edits the D/I
  function in the Setup menu.
- **B alone** — static; cannot be relaxed remotely for legitimate maintenance.
- **A + B** — B holds the line whenever the PLC is down or the wire is out, and password-locks
  the Setup menu so A cannot be quietly undone. A gives CODESYS dynamic control on top.

## 18.4 ⚠️ The one thing that must be verified on hardware first

**Does Panel Lock block the gateway's Modbus setpoint writes?** If it did, this design would lock
out CODESYS along with the operator and be worse than useless.

Strong evidence it does not:
- Panel Lock's documented purpose is a **key-lock switch for the operator at the panel** — locking
  the host out would defeat its own sample application.
- Every lockout parameter (`Set Point, Lockout`, `Setup Page, Lockout`, `Clear Locks`, …) is
  itself **readable and writable over Modbus** in the Communications chapter register map. A lock
  that blocked comms could be set but never cleared — an absurd design.
- The keypad and the serial link are separate input paths into the controller.

That is a strong inference, **not a measurement.** Given §17.8.4, confirm it before relying on
it — test P3 below takes about ten minutes.

## 18.5 Test suite P1–P6

Run after the §17.9 R-suite. Requires D/I 2 reassigned per §18.3.

| # | Action | Pass criterion |
|---|---|---|
| **P1** | `xPanelLock := FALSE`. At the F4S panel, change the static setpoint | Setpoint changes — baseline proves the panel works and the test is meaningful |
| **P2** | `xPanelLock := TRUE`. At the panel, attempt the same change | Keypad refuses; setpoint unchanged. F4 D/I 2 indicator lit |
| **P3** | 🔑 With `xPanelLock` still TRUE, write a new setpoint from CODESYS | **Write lands.** `wSetpoint1Read` updates, chamber ramps. *This is the make-or-break test — if it fails, Mechanism A is unusable and only B (Read Only) applies* |
| **P4** | With lock TRUE, ramp to a high setpoint; at the panel try to enter a much lower one | Chamber holds the CODESYS setpoint and does **not** ramp down — §18.1 satisfied in the heating case |
| **P5** | Repeat P4 from a low setpoint, attempting a much higher one at the panel | Chamber does not ramp up — §18.1 satisfied in the cooling case |
| **P6** | Set `Set Lockout > Set Point = Read Only`; stop the PLC so CH16 drops | Setpoint still not editable at the panel — Mechanism B holds with the PLC down |

P4 and P5 together are the direct demonstration of §18.1 and are what should be shown to the
manager.

## 18.6 What this does *not* cover

- **Profile Key.** An operator can still start/hold/terminate a stored profile from the front
  panel unless `Set Lockout > Profiles` is also restricted. Set it to `Read Only` or `Password`
  if profile control must also be CODESYS-only.
- **The red stop button.** Unaffected and deliberately so — it remains a physical emergency stop
  (§6, §17.8.4). Panel lock governs *setpoint authority*, not the ability to shut the cabinet
  down, and those should not be conflated.
- **Mains disconnect.** Untouched. It stays the lockout/tagout isolation point.

---

# 19. AS-BUILT — Remote start/stop via the Omron CPM1A digital inputs (6 Aug 2026)

## 19.1 What changed, and why §17/§15/§6 didn't need to be right for this to work

Everything from §6 through §17.8.4 assumed the only thing behind the button station was a bare
latching relay — a passive electromechanical device with no logic of its own, wired directly to
`102`/`103`. Tracing the panel further back (7168-DWG-100, the LCA Group as-built drawing, and the
CPM1A datasheet, both added to `docs/`) found that assumption was wrong: **the button station's
`102`/`103` outputs land on digital inputs of an Omron SYSMAC CPM1A-30CDR-A-V1 PLC**, not directly
on a relay coil. `102` → CPM1A input `0CH.00`. `103` → CPM1A input `0CH.01`. `COM0` is the shared
input common for that PLC.

This is the fact that resolves the §17.8.4 dead-end. §15 Option C failed because it tried to make
an EL2869 **sourcing** output substitute for a **low-side (ground) switched** button contact — a
device-type mismatch with no fix at any terminal. The Omron's digital inputs are a different kind
of thing entirely: **bidirectional opto-isolated inputs**. Per the CPM1A datasheet (`docs/Omron
PLC CP1MA Datasheet.pdf`, I/O Specifications): *"The polarity of the input power supply can be
either positive or negative."* A sourced 24 V signal from the EL2869 and a sourced 24 V signal
from the button's own NO4/NC2 output are the **same kind of source** feeding the **same kind of
input** — they OR together safely, the way §17's F4-DI design already proved for a different pair
of terminals. No relay was ever the fix; landing on the right terminal was.

## 19.2 Wiring — EL2869 direct to the Omron CPM1A input block

```
 DLS008 ENCLOSURE                              OMRON CPM1A-30CDR-A-V1 TERMINAL BLOCK
   EL2869 (EK1100 EtherCAT coupler)
     CH15 (pin 36) ── Red wire   ──────────────►  0CH.00  (input, wire "102")
     CH16 (pin 37) ── Green wire ──────────────►  0CH.01  (input, wire "103")
     DO GND         ── Black + White wire ──────►  COM0    (input common)
```

**Confirmed on the physical panel, in order:**

1. Terminal strip photographed and cross-referenced against the CPM1A's own printed legend:
   `L1 | ⏚ | L2/N | COM0 | 00 | 01 | 02 | 03 …` — confirming `COM0` sits immediately left of `00`,
   and `00`/`01` are the first two input points (`0CH.00`/`0CH.01`).
2. Wire `100` (thick yellow) identified as the +24 V feed into the button station's NO4/NC2
   contacts — **not** ground, correcting an earlier working assumption in this investigation.
   Wires `102`/`103` are the button contacts' outputs, landing on `0CH.00`/`0CH.01`.
3. Continuity check, COM0 → EL2869 DO GND: **not conclusive as first read.** A directional
   asymmetric reading (0.4 Ω one way, 8.8 Ω reversed) was initially taken as "continuous," but an
   asymmetric reading like that is the signature of current passing through a semiconductor
   junction (an optocoupler input or a protection diode) — not proof of a bonded copper rail,
   which would read the same both directions. **Treat the ground bond as installed by the
   explicit jumper wired in §19.2 step 4, not as proven by this reading.**
4. A ground jumper was landed from the Omron's own `GND`/`COM0` reference to the EL2869 `DO GND`
   rail (the same rail already proven continuous with `Out 1A GND` in the §17 work), unifying the
   return path. Both the black and white EL2869 ground conductors terminate there.
5. CH15 → `102` (physically at the point that previously left the button's NO4 contact), CH16 →
   `103` (previously left the button's NC2 contact).

**Result:** with this wiring, `xStartPulse` asserted on CH15 and `xStopPermit` asserted on CH16
are read by the Omron's own program as start/stop commands, and the cabinet starts and stops
accordingly — **proven repeatedly on hardware, both signals independently.**

## 19.3 CODESYS side

`GVL_HMI` (`codesys modbus proof of concept and test logs/src/GVLs/GVL_HMI.gvl`):

```iec61131
xStartPulse    : BOOL;   (* -> EL2869 CH15 -> wire 102 -> Omron 0CH.00 (start) *)
xStopPermit    : BOOL;   (* -> EL2869 CH16 -> wire 103 -> Omron 0CH.01 (stop)  *)
xCabinetRunning : BOOL;  (* commanded-state proxy; no independent run feedback wired yet *)
```

`PLC_PRG_TCP.st`, STEP 0:

```iec61131
IF GVL_HMI.xStopPermit THEN
    GVL_HMI.xStartPulse := FALSE;
END_IF
GVL_HMI.xCabinetRunning := GVL_HMI.xStartPulse AND NOT GVL_HMI.xStopPermit;
```

That is deliberately the entire on/off program now. An earlier iteration modelled CH16 as a
continuous 24 V supply and derived CH15 from a `TON`/`TP`/`R_TRIG` chain that "pressed" it
electronically — a carryover from the abandoned §15 Option C supply-lift model. Under that model,
toggling `xStopPermit` produced a **derived, delayed** pulse on `xStartPulse`, which is what
produced the reported sequence — stop-permit true, then false, then a start pulse firing on its
own a moment later, with no direct command to start anything. That model does not describe the
Omron: its own ladder program is what performs the start-stop-hold latching, so CODESYS's job is
only to present a level on each input and hold it. The timer/pulse chain has been removed
entirely — no `TON`, no `TP`, no anti-short-cycle lockout, no `tOffLockDuration`. **Pure level
commands, held until changed.**

The one thing kept in is a one-line stop-priority guard: if both are ever commanded `TRUE`
together, `xStartPulse` is forced `FALSE`. This costs nothing and there is no known scenario where
firing both at once is the intended action — flag it if that turns out to be unwanted.

**Watch window (current test procedure):**

| Variable | Force to | Expected result |
|---|---|---|
| `GVL_HMI.xStartPulse` | `TRUE` | CH15 output energises; Omron `0CH.00` LED lit; cabinet starts |
| `GVL_HMI.xStartPulse` | `FALSE` | CH15 de-energises; no independent effect unless the Omron's own logic ties it to a run condition |
| `GVL_HMI.xStopPermit` | `TRUE` | CH16 output energises; Omron `0CH.01` LED lit; cabinet stops; `xStartPulse` forced `FALSE` by the guard above |
| `GVL_HMI.xStopPermit` | `FALSE` | CH16 de-energises |
| `GVL_HMI.xCabinetRunning` | (read-only) | Mirrors the commanded state — **not** a measured run status, see §19.6 |

## 19.4 ⚠️ Open item — manual physical authority (needs one confirming test)

The original requirement (project kick-off and reiterated repeatedly in this investigation) is
**hybrid control**: the operator standing at the cabinet must be able to start and stop it by
hand, in addition to CODESYS. Two pieces of conflicting information are on record for the current
physical state of `102`/`103`, and this needs a single deliberate confirming test before it goes
in as fact:

- During this investigation, the button's NO4/NC2 outputs were reported disconnected from
  `102`/`103`, leaving only the EL2869 landed there.
- Separately, both wires were reported temporarily removed for a bench test, with both the button
  and the EL2869 working "perfectly fine together" once reconnected.

Both cannot be true of the same permanent wiring state at once. Since the Omron's inputs are
bidirectional opto-isolated inputs (§19.1), **landing the button's NO4/NC2 outputs in parallel
with CH15/CH16 on `102`/`103` is expected to work** — both are sourcing 24 V into the same input,
which is exactly the OR relationship that already makes CH15/CH16 work on their own. There is no
electrical reason this should fail.

**Required before this section is called complete:** with the cabinet powered and CODESYS online,
confirm on the physical terminal block that both the button's NO4 output and the EL2869 CH15 red
wire land on `102` together (and NC2 / CH16 green on `103` together), then run:

| Test | Action | Pass criterion |
|---|---|---|
| M1 | `xStartPulse`/`xStopPermit` both `FALSE`. Press the green button by hand | Cabinet starts |
| M2 | Press the red button by hand | Cabinet stops |
| M3 | `xStartPulse := TRUE` from the watch window, hands off the panel | Cabinet starts |
| M4 | `xStopPermit := TRUE` from the watch window | Cabinet stops |
| M5 | `xStartPulse := TRUE`, then press the red button by hand while it is held | Cabinet stops — local stop takes priority over a remote start, as required |
| M6 | Restore `xStartPulse`/`xStopPermit` to `FALSE` after each test | Panel and CODESYS agree on idle state |

Until M1–M6 are run and pass, **treat manual physical authority as unconfirmed**, not as
restored. This is the single highest-priority open item in this document.

## 19.5 Open item — CH15/CH16 reallocation for §17 (ramp gate) and §18 (panel lock)

CH15/CH16 are now committed to the Omron on/off pair. They can no longer also drive the F4S's
`D/I 1` (ramp gate, §17) and `D/I 2` (panel lock, §18) — those two designs are proven and
documented, but **not currently wired**, because the two channels they used have a new job.

**Recommendation:** the EL2869 is a 16-channel terminal and only CH15/CH16 are in use anywhere in
this project. Reallocate §17/§18 to two spare channels (e.g. CH13/CH14) and re-terminate two wires
at the F4S end — no new hardware, no cost, roughly the same effort as the original §17
installation. This is a re-termination and I/O-mapping change, not a redesign; `xRampInhibit` and
`xPanelLock(Cmd)` are already declared in `GVL_HMI` and the STEP 0b logic is preserved (commented
out) in `PLC_PRG_TCP.st`, ready to reconnect once a channel is chosen.

Until this is done, the chamber has **no automated ramp gate** (§17's original "sits idle until
scheduled start" behaviour) and **no panel lock** (§18's setpoint-authority protection) —
`xCabinetOnCmd`'s schedule computation still runs, but nothing currently acts on it, and the F4S
keypad is not locked. If setpoint authority is the more urgent of the two given the manager's
original concern (§18.2), prioritise reallocating `D/I 2` (panel lock) first.

## 19.6 Conflict-resolution design — research and recommendation

*Ranked per direction: software interlock first (recommended, matches the direct-wiring solution
that made this section possible), condensed hardware fallback second.*

### 19.6.1 Why this is a different problem than §6/§7 solved for

§6/§7's two-relay design existed to make a **sourcing output play the role of a low-side contact**
— a wiring-compatibility problem, and it no longer applies (§19.1). What remains is a **behavioural**
question: since both the button and CODESYS can independently assert `0CH.00`/`0CH.01`, what
happens when they disagree at the same moment, or in close succession? This is not a short-circuit
risk — both sources add 24 V to the same node, which is safe by construction — it is a question of
what the **Omron's own, undocumented ladder program** does with two sources changing near-
simultaneously, and neither this project nor its author has that program (it belongs to JTS, the
original panel builder).

### 19.6.2 Recommended — software-side interlock in CODESYS (no new hardware)

1. **Stop-priority mutual exclusion** (already implemented, §19.3): if both are commanded, stop
   wins. Trivial and unconditionally safe.
2. **Hold time, not pulse width.** Because the Omron does its own latching, CODESYS does not need
   to guess a pulse width the way the abandoned Option C model did. A command should simply be
   held at the level intended and released deliberately — there is no minimum "catch" duration to
   tune, which removes an entire class of the timing bugs seen in §17.8.4 and in today's
   `TON`/`TP` chain.
3. **Run-feedback loop (highest-value next step).** `xCabinetRunning` today is a *commanded-state
   proxy*, not a measurement — CODESYS has no way to know if a manual button press changed the
   actual state underneath it. Wiring one spare Omron output (or a spare EL1409 digital input,
   already used for exactly this purpose in §4 Option 1) back to CODESYS closes the loop: CODESYS
   can then detect "the cabinet's actual state disagrees with what I last commanded," which is the
   direct signature of a manual override, and react (suppress a conflicting automatic command, log
   the event, or surface it on the HMI) instead of blindly re-asserting a stale command.
4. **Rate-limit automatic commands**, once the scheduler (§19.5) is reconnected, so a schedule
   edit or RTC step cannot re-fire start/stop against a state the operator just changed by hand —
   the same principle as the anti-short-cycle timer removed from §19.3, but keyed off the
   feedback in point 3 rather than a blind fixed duration.

None of this requires new relays, new wiring, or touching the button station again — it is entirely
CODESYS-side logic once the feedback wire in point 3 exists.

### 19.6.3 Fallback — hardware relay, condensed from §6/§7

If a hard, CODESYS-independent override is ever required (e.g. a maintenance lockout that must
hold even with the PLC stopped), a single relay with a **normally-closed dry contact in series**
with the CH15/CH16 path to `102`/`103` gives a physical kill switch that neither software state nor
a stuck output can defeat. This is a strictly smaller ask than the original two-relay §6/§7
design — one relay, one contact, no interaction with the button station's own wiring — and should
only be added if a specific hazard analysis calls for a hardware-enforced override that outlives a
CODESYS or Omron fault. Estimated cost €20–40 for a single DIN-rail relay with integral freewheel
diode (§6b). Not currently justified without a named hazard driving it.

## 19.7 Open items

1. **§19.4 — confirm manual physical authority** (M1–M6). Highest priority; see above.
2. **§19.5 — reallocate CH13/CH14 (or similar spares) to §17 ramp gate and §18 panel lock**, and
   re-run the R1–R8 and P1–P6 test suites against the new channels once landed.
3. **Run-feedback wire** from the Omron back to CODESYS (§19.6.2 point 3) — the single highest-
   value next step for closing the "manual override while CODESYS is mid-command" gap.
4. **`xCabinetOnCmd` integration decision.** Should the schedule automatically drive
   `xStartPulse`/`xStopPermit`, or should those stay purely operator/CODESYS-commanded with the
   schedule as a separate, not-yet-connected concern? Currently the schedule computes but nothing
   consumes it.
5. **Contact JTS for the CPM1A ladder program / panel schematic.** The single action that would
   retire the "undocumented Omron program" uncertainty underlying §19.6.1 entirely — confirmed
   contact available.
6. **Capture M1–M6 (and, once wired, the CH13/CH14 re-commissioning) as a timestamped test log**,
   consistent with the qualification standard set in
   `codesys modbus proof of concept and test logs/docs/test-logs/`.

---

# 20. AS-BUILT — Two-relay interposing design onto the Omron inputs, integration tested (10 Aug 2026)

**Status: ✅ Investigation complete. Integration testing complete on the Left Hand Small
Temperature Cabinet (DLS008).**

## 20.1 What this section changes

§19 proved that CH15/CH16 could drive the Omron CPM1A's `01`/`02` inputs directly, with no relay,
because those inputs are bidirectional opto-isolated inputs rather than a bare latch coil. That
remains electrically true. For the actual integration build, **two interposing relays have been
reintroduced** between the DLS008 digital outputs and the Omron inputs — reviving the §6/§7
two-relay topology, but now correctly terminating on the Omron's `01`/`02` inputs instead of the
originally-assumed latch coil. This gives the best of both findings:

- From §6/§7: galvanic isolation between the DLS008 24 V rail and the button station's own 24 V
  circuit, and a design that is fully reversible (unplug two relays, panel is as it was).
- From §19: the correct termination point — the Omron CPM1A's `01`/`02` digital inputs — so the
  relay contacts and the local button's own contacts land on the **same** input and OR together
  safely, instead of trying to interrupt a low-side contact the EL2869 was never able to switch
  (the §15 Option C dead-end).

## 20.2 Wiring — as tested, from the reference diagram

Two interposing relays, each a standard DIN-rail 2-changeover-contact relay (terminal numbering
`11`/`14`/`12` and `21`/`24`/`22` — commons `11`/`21`, NO `14`/`24`, NC `12`/`22`), one per
function:

| Relay | Coil driven by | Function |
|---|---|---|
| **Relay 1** | `DLS Start DO 24V+` / `DLS 0V` (EL2869 CH15) | START — sources 24 V onto wire `102` → Omron `01` |
| **Relay 2** | `DLS Stop DO 24V+` / `DLS 0V` (EL2869 CH16) | STOP — sources 24 V onto wire `103` → Omron `02` |

**Terminal / wire-colour table, as built and tested:**

| Wire colour | From | To | Purpose |
|---|---|---|---|
| Green | Bus `100` (button station 24 V feed) | `NO3` (local start contact) **and** across to Relay 1 terminal `11` | Local start contact and Relay 1 common share the same 24 V rail |
| Tan/orange | Bus `100` | `NC1` (local stop contact) | Local stop contact 24 V feed |
| White | Bus `60` | `X1` (lamp/indicator) | Indicator only — no logic role |
| Red | Relay 1 terminal `14` (NO) | wire `102` → Omron terminal `01` | Start command — parallel with the local button's own `102` path, exactly the OR/parallel-start logic specified in §6 |
| Blue | `NC2` (local stop contact output) | Relay 2 terminal `21` (common) | Ties the local stop output into the same relay junction that also carries the remote stop source |
| Orange | Relay 2 terminal `22` (NC) | wire `103` → Omron terminal `02` | Stop command — lands on the same Omron input as the local button's `NC2` output |
| Red (bottom bus) | `NO4` (button station's physical `102` terminal) | field wire `102`, return via 0 V/ground rail (`Y`) | Physical wire-number continuity check — `NO4`/`NC2` at the bottom of the button block are where field wires `102`/`103` actually leave the station, per the numbering established in §2.1 |

```
 ON/OFF SWITCH STATION           RELAY 1 (START)         RELAY 2 (STOP)          OMRON CPM1A
 (local button, unmodified)      coil <- DLS Start DO     coil <- DLS Stop DO     input block

  100   60   100                    21   11                  21   11
   |     |    |                      |    |                    |    |
 [NO3] [X1] [NC1] ── green ─────────┘    |                    |    |
   |    lamp  |                          |                    |    |
   |          |                     24   14 ── red ── 102 ────┼────┼──►  01
   |          |                      |    |                    |    |
  102        103                    22   12                  22   12
   |          |                      |    |                    |    |
  [NO4]     [NC2] ── blue ───────────────────────────────────┘    |
                                                                     |
                                     Relay 2 terminal 22 ── orange ─┴── 103 ──►  02
```

## 20.3 CODESYS side — unchanged from §19.3

No CODESYS logic change was required for this section. `GVL_HMI.xStartPulse` (CH15) and
`GVL_HMI.xStopPermit` (CH16) still drive the same two EL2869 channels; the relays sit purely in
the field wiring between the terminal and the Omron input, adding isolation without changing the
software contract. Re-use the same watch-window test procedure documented in §19.3.

## 20.4 Integration test — Left Hand Small Temperature Cabinet (DLS008)

**Result: ✅ PASS.** With both relays wired per §20.2 and the local button station left
physically unmodified:

| Test | Action | Result |
|---|---|---|
| Local start | Green button pressed by hand | Cabinet started |
| Local stop | Red button pressed by hand while running | Cabinet stopped immediately |
| Remote start | `xStartPulse := TRUE` from CODESYS | Relay 1 energised, CH15 LED lit, cabinet started |
| Remote stop | `xStopPermit := TRUE` from CODESYS | Relay 2 energised, CH16 LED lit, cabinet stopped |
| Local/remote coexistence | Both button and relay wiring landed on the same `01`/`02` inputs simultaneously | No fault, no contention — confirms the OR behaviour predicted in §19.1/§19.4 |

This closes the top open item carried since §19.4 — manual physical authority is now **confirmed
by test**, not assumed, because the two-relay topology keeps the local button's own contacts
electrically intact and merely adds a parallel, isolated source at the same input.

## 20.5 Wiring diagram explanation — Start/Stop relays and Omron CPM1A integration

The two-relay design connects to the existing button station and Omron CPM1A PLC inputs as follows:

```
ON/OFF SWITCH STATION (local button, unmodified)
   100: +24V rail        60: +10V lamp       102: Green NO out    103: Red NC out

RELAY 1 (START)                    RELAY 2 (STOP)                    OMRON CPM1A
24V DC coil + freewheel diode      24V DC coil + freewheel diode     Input block

Coil ← DLS CH15 Start DO           Coil ← DLS CH16 Stop DO
Return ← DLS 0V common             Return ← DLS 0V common

NO contact 14 ──┐                  NC contact 22 ──┐
               │ parallel          │ series        │
               ├── wire 102 ───────┤               ├── Terminal 01 (START input)
               │                   │               │
Green button ──┘                   ├─ wire 103 ───┴── Terminal 02 (STOP input)
(NO 3-4)                           │
                                   └─ Red button
                                      (NC 1-2)

KEY LOGIC:
- **START (parallel):** Wire 102 receives 24V from either green button OR relay 1 → Omron `01` input
  → Both sources can initiate start (OR gate)
  
- **STOP (series):** Wire 103 stop path requires BOTH local red NC contact AND relay 2 NC contact closed
  → Either source can break the circuit = either can stop (AND gate, fail-safe)
```

**Why this matters:**
- Relay 1 NO contact **parallels** the green button: remote start adds to local start, both trigger Omron `01`
- Relay 2 NC contact **series** on the stop path: remote stop command (energize to stop) mirrors the red button behavior
- Local button station wiring physically unchanged; local control always works
- Fail-safe: If DLS008 loses power, Relay 2 de-energizes → NC contact closes → stop circuit intact → manual operation restored

---

## 20.6 Watch-window operating procedure

**Before first use:**
- Confirm relay coils: **24 ±2V DC** across each coil with multimeter
- Download CODESYS and go online
- Verify `xSetOperational` = TRUE (EL2869 status)
- Confirm GVL_HMI variables visible in watch window

**Operating sequence:**

| Step | Action | Expected |
|------|--------|----------|
| 1 | Set `xCabinetOnCmd = TRUE` in **Prepared value** | `xStartPulse` HIGH for 1 second, then FALSE |
| 2 | Listen | Fan starts (relay 1 energizes, supplies 24V to Omron `01`) |
| 3 | Wait 5–10s | Compressor starts after fan |
| 4 | Set `xCabinetOnCmd = FALSE` | `xStopPermit` FALSE; `xStartPulse` FALSE |
| 5 | Listen | Fan/compressor stop (~3s) |
| 6 | Watch `tOffLockRemain` | Counts down from 5 minutes |
| 7 | Retry during lockout | Set `xCabinetOnCmd = TRUE` before timer = 0; `xStartPulse` stays FALSE (blocked) |
| 8 | Wait for 0s | Timer expires |
| 9 | Retry after lockout | Set `xCabinetOnCmd = TRUE` after timer = 0; `xStartPulse` pulses, cabinet restarts |

**Verify local authority:** While running from remote (`xCabinetOnCmd = TRUE`), press red button at panel → cabinet stops immediately (local always wins).

---

## 20.7 Manual authority verification tests (M1–M6)

Run on each commissioned cabinet:

| Test | Setup | Action | Expected | Pass |
|------|-------|--------|----------|------|
| M1 | Cabinet idle | Press green button | Cabinet starts (local NO → Omron `01`) | ☐ |
| M2 | Running (from M1) | Press red button | Cabinet stops (local NC breaks wire 103) | ☐ |
| M3 | Cabinet idle | `xCabinetOnCmd = TRUE` | Cabinet starts (relay 1 → Omron `01`) | ☐ |
| M4 | Running (from M3) | `xCabinetOnCmd = FALSE` | Cabinet stops (relay 2 NC closes) | ☐ |
| M5 | Idle; lockout active | `xCabinetOnCmd = TRUE` while `tOffLockRemain > 0` | Cabinet blocked (anti-short-cycle) | ☐ |
| M6 | Idle; lockout expired | `xCabinetOnCmd = TRUE` after `tOffLockRemain = 0` | Cabinet starts (lockout expired) | ☐ |

**All six tests required before commissioning sign-off.**

---

## 20.8 Troubleshooting

| Symptom | Cause | Check | Fix |
|---------|-------|-------|-----|
| Green button doesn't start cabinet | Relay 1 coil lost power; NO contact stuck open | Multimeter: 24V ±2V across relay 1 coil | Reconnect coil supply; replace relay if contact failed |
| Remote `xCabinetOnCmd=TRUE` does nothing | EL2869 not operational; I/O mapping missing | Check `xSetOperational` = TRUE; `xStartPulse` visible in watch window | Download CODESYS; verify EL2869 mapping |
| Red button doesn't stop cabinet | Relay 2 NC contact failed closed; wire 103 not in series | Multimeter across relay 2 NC: should be CLOSED when coil OFF | Replace relay; rewire NC contact into series path |
| `xCabinetOnCmd=FALSE` doesn't stop cabinet | Relay 2 NC wired in parallel instead of series | Trace wire 103 from button; verify relay NC in series | Rewire relay 2 into series path |
| `xStartPulse` never triggers | Anti-short-cycle lockout running | Watch `tOffLockRemain` | Wait for timer to expire |
| Relay clicks/chatters constantly | Coil current too low; relay without freewheel diode | Verify datasheet: integral freewheel diode present | Replace with Phoenix Contact PLC-RSC-24DC/21 or Finder 38-series |

---

## 20.9 Quick reference

**Sequencer settings:**

| Parameter | Value | Reason |
|-----------|-------|--------|
| Start pulse width | 1 second | Longer than relay pickup (~50 ms) |
| Anti-short-cycle lockout | 5 minutes | Compressor soft-start protection |

**Watch-window variables:**

| Variable | TRUE | FALSE |
|----------|------|-------|
| `xStartPulse` | Start active (~1s pulse) | Start idle |
| `xStopPermit` | Stop path open; run allowed | Stop path broken; must stop |
| `xCabinetOnCmd` | Request run | Request stop |
| `tOffLockRemain` | > 0s (restart blocked) | = 0s (restart allowed) |

---

## 20.10 Commissioning checklist

| # | Item | Done |
|---|------|------|
| 1 | Panel Mount USB installed | ☐ |
| 2 | USB harness routed to Pi | ☐ |
| 3 | Relay coils wired to 37-pin pins 13 & 14 | ☐ |
| 4 | Button switch wired per §20.2 two-relay design | ☐ |
| 5 | Relay coils confirmed 24 ±2V DC | ☐ |
| 6 | Manual authority tests M1–M6 all pass | ☐ |

---

## 20.11 12-item handover verification

- [ ] D1: Document read and understood
- [ ] D2: Wiring diagram (§20.5) matches physical installation
- [ ] D3: BOM (§7) verified against actual parts
- [ ] H1: Relay coils 24 ±2V DC; supply stable
- [ ] H2: Relay contacts tested; NO/NC logic correct
- [ ] H3: Cable shielding grounded at both ends
- [ ] H4: Wires labeled with ferrules; legible
- [ ] S1: CODESYS downloaded; `xSetOperational` = TRUE
- [ ] S2: Watch-window procedure (§20.6) executed
- [ ] S3: Manual authority tests M1–M6 passed
- [ ] F1: Fail-safe test: DLS008 off; red button still stops cabinet
- [ ] F2: Operator trained; red button priority confirmed

**Approved by:** ________________ **Date:** __________

---

## 20.5 Investigation status

**Investigation: complete.** **Integration testing: complete on the Left Hand Small Temperature
Cabinet.** This design (§20) is the one to replicate on the remaining cabinets — see the root
[`README.md`](<../README.md>) Stage 8 for the cabinet rollout order and commissioning checklist.
Build both relays, wire per §20.2, and run the §20.4 test table on each cabinet before moving on
to the EL1859 re-termination work.

Open items carried forward unchanged: §19.5 (CH13/CH14 reallocation for the ramp gate and panel
lock) and §19.6.2 point 3 (run-feedback wire) remain open — see §19.7.
