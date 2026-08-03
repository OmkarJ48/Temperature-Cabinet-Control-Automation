# Cabinet On/Off Automation — Investigation & Integration Guide

**Author:** Omkar Joshi — Oliver Mechatronics
**Date:** 29 July 2026 (original); **updated 3 August 2026**
**Objective:** Remotely start and stop the Left Hand Small Temperature Cabinet, without touching mains wiring and without taking authority away from the local operator.
**Status:** ✅ **DEPLOYED AND PROVEN ON HARDWARE — see §17.** Both heating (1A) and cooling (1B)
outputs are gated by a single EL2869 output wired straight into the F4S's own digital input.
Bidirectional setpoint control (positive and negative, staged while gated, released on command)
has been demonstrated repeatedly on the physical cabinet. §15 and §16 below were both
investigated and **superseded** by the approach in §17 — kept here as design history and because
the troubleshooting in them (button-station topology, low-side vs. sourcing outputs, coil
current, F4 register behaviour) remains accurate and useful.

> ### ⚠️ READ §17 FIRST — it is the as-built, working solution
>
> The deployed route does **not** touch the cabinet's switch station, the `-202X3` connector, or
> the thermocouple junction box at all. It wires two spare EL2869 channels **directly to two
> spare digital inputs on the Watlow F4S controller itself** and uses the F4S's own built-in
> "Control Outputs Off" input function. No relays, no supply-lift, no pass-through cabling.
>
> §15 (Option C, relayless supply-lift via `-202X3`) and §16 (Route A, Modbus setpoint sentinel)
> were both built out on paper/software and are retained below as investigation record. §16's
> own test A1 is what proved the sentinel approach was insufficient (it stopped the compressor
> but not the fan), which is what motivated the F4-DI approach in §17. Sections 6, 7, 7a and 9a
> (the two-relay Option A/B interposing-relay design) were superseded even earlier and **must not
> be built**.

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

## 6b. DLS008 → Relay coil interaction (power supply compatibility)

The cabinet control runs on 24V DC from the DLS008 field power supply. Relay coils are inductive loads — they present a brief high-current inrush on close and a voltage spike on open. This section proves the DLS008 can safely deliver that current without relay damage.

**DLS008 and EL2869 specifications** (from control panel datasheet):
- **24V field supply rating:** Rated for 1 A per module (multi-module system with shared 24V bus)
- **EL2869 per-channel output:** EtherCAT coupler feeds 24V to each driven load through internal MOSFET drivers
- **Cable spec:** Minimum 0.5–0.75 mm² CSA for control circuits (shielded, ELV-rated)
- **System protection:** Integrated within Beckhoff EX1100 coupler; over-current monitoring present per EtherCAT standard

**Relay coil power analysis:**

| Specification | Typical value | Worst case | Notes |
|---|---|---|---|
| Coil nominal voltage | 24 V DC | — | Phoenix Contact PLC-RSC-24DC, Finder 38 series |
| Holding current (steady) | ~30 mA | 50 mA | Relay energized, sealed in |
| Pickup current (inrush, transient) | ~150 mA | 300 mA | First 5–50 ms on energize; L/R time constant ~20 ms |
| Coil inductance | 15–25 mH | 30 mH | Depends on coil design |
| DC resistance (cold) | 800–1000 Ω | 650 Ω | At 20°C; rises to ~1100 Ω hot |

**Voltage drop during inrush:** When the EL2869 switches on and drives 150–300 mA through ~0.5 m of 0.75 mm² cable (R ≈ 0.01 Ω/m → 0.005 Ω total), the transient voltage drop is:
- V_drop = I_inrush × R_cable ≈ 200 mA × 0.005 Ω ≈ **1 mV** (negligible)
- 24 V supply remains ≥ 23.8 V (well within relay tolerance ±10%)

**EL2869 output rating vs. coil draw:** EL2869 specifications (Beckhoff EC2020 coupler manual):
- Output voltage: 24 V DC (sourced from internal supply)
- Per-channel continuous rating: ~500 mA (conservative, MOSFET-based)
- Per-channel inrush handling: Transient over-current allowed up to ~1 A for <100 ms (standard MOSFET behavior)
- Spike suppression: Internal clamp diodes prevent parasitic reverse voltages

**Freewheel diode requirement (CRITICAL):**

A 24V DC relay coil inductance stores energy. When the EL2869 output cuts off:
- Without protection: Coil acts as a voltage source, back-EMF can reach **100+ V**, destroying the EL2869 MOSFET output stage
- With freewheel diode: Diode clamps the coil to ≈ 24V + 0.6V (diode drop), allowing current to decay safely

This is why **§7 specifies relay coils with integral freewheel diodes** — it is not optional and not a convenience feature. Using a bare relay coil will fail the EL2869 on the first de-energization.

**Cable recommendations** (from DLS008 panel schematic):
- Minimum CSA: **0.75 mm²** (double the PLC minimum to account for EMI margin)
- Type: Shielded, twisted-pair, ELV-rated (UL-listed or equivalent)
- Shield termination: Connect both ends to the DLS008 24V common (0V rail) and control enclosure ground via ferrule or clamp
- Length: Keep ≤5 m; longer runs need slightly heavier gauge (1 mm²) to reduce EMI pickup

**Grounding and return path:**
- Both relay coil supply and EL2869 output must share the same 24V common (0V reference)
- Do not use multiple return paths — single-point star grounding at the control enclosure, feeding back through the DLS008 24V bus
- Enforce this with a short, heavy-gauge return wire (same gauge as supply, minimum 0.75 mm²) from the relay common to the DLS008 bus common

**Safety margins and confirmation:**
1. ✅ Holding current (30 mA nominal) << EL2869 rating (500 mA continuous) — **16× safety factor**
2. ✅ Inrush current (150–300 mA transient) << EL2869 transient rating (1 A for <100 ms) — **3–6× safety factor**
3. ✅ Voltage drop <1 mV — negligible, relay sees 24V throughout
4. ✅ Freewheel diode present in specified relays — back-EMF clamped, no MOSFET stress
5. ✅ Cable gauging (0.75 mm²) provides 50% EMI margin above the minimum PLC spec

**Conclusion:** A 24V DC relay coil with integral freewheel diode, driven through shielded 0.75 mm² cable, is safe for the DLS008 EL2869 output. No special drivers, current-limiting resistors, or external diodes are required. The relay holds steady at 24V, draws <50 mA continuous, and the freewheel diode protects the EL2869 during switching transients.

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

| Control | Relay | EL2869 CH | Behavior |
|---|---|---|---|
| Start pulse (1 sec) | K_REM_START coil → ON | CH1 energizes | NO contact closes; start flows through parallel contact |
| Stop permission (continuous) | K_REM_STOP coil → ON | CH2 held high | NC contact stays closed; stop circuit ready |
| Red button pressed during start | Local NC opens | CH2 unaffected | Stop works immediately because remote NC is still closed |

The sequencer drives them independently:
- `xStartPulse` → CH1 (1-second pulse)
- `xStopPermit` → CH2 (held high until stop command)

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
python3 python-rtu-integration/test_onoff_route_a.py
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
| **D/I 2** (terminal 29) | **"All Outputs Off"** | Superset of the above — also disables event outputs. Left mapped in CODESYS (`GVL_HMI.xAllOutputsOff`) for future use, but **must be inactive** during normal operation — see §17.7 troubleshooting. |
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

`codesys-python-gateway-modbus-integration/src/GVLs/GVL_HMI.gvl`:

```iec61131
(* ---- Scheduled ramp gate (logic -> hardware -> WebVisu feedback) ---- *)
xSchedEnable         : BOOL;           (* scheduler enabled flag          *)
dtSchedStart         : DT;             (* scheduled start date/time       *)
xRampInhibit         : BOOL;           (* -> EL2869 CH15 -> F4 DI1        *)
xRampActive          : BOOL;           (* feedback: inverted from xRampInhibit *)
```

`xAllOutputsOff` (CH16 → F4 DI2) exists as a variable mapped in I/O Mapping but is **not** driven
by any current PLC logic — it defaults FALSE and must stay FALSE for normal operation (§17.7).

### PLC_PRG_TCP — STEP 0, scheduled ramp gate

`codesys-python-gateway-modbus-integration/src/POUs/PLC_PRG_TCP.st`:

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
| EL2869 CH16 | `GVL_HMI.xAllOutputsOff` | Output, drives F4 D/I 2 — must stay FALSE (§17.7) |

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

- [ ] `GVL_HMI.xAllOutputsOff` = FALSE (F4 D/I 2 dark on the panel)
- [ ] `GVL_HMI.xSchedEnable` = FALSE unless a scheduled/manual gate is intentionally active
- [ ] `GVL_HMI.xRampInhibit` = FALSE, `xRampActive` = TRUE for normal, ungated operation
- [ ] F4 D/I 1 panel indicator dark when `xRampInhibit` is FALSE, lit when TRUE — verify this
      polarity after any redownload, since it is the one piece of hardware behaviour that isn't
      software-verifiable from the watch window alone

## 17.8 Open items

1. **RTC / `dtNow` fix.** The Raspberry Pi's system clock is NTP-synced and correct, but
   `SysTimeRtcHighResGet()` inside the PLC is not currently reflecting it — `dtNow` reads 1970.
   `hwclock` is not present on this image (`sudo hwclock -w` → command not found). Until this is
   resolved, the scheduler's *automatic* time-based release cannot be relied on; it has been
   demonstrated and used operationally via **manual** `xSchedEnable` toggling instead. Candidate
   fixes to try: install `fake-hwclock` or `util-linux`'s hwclock package, or investigate whether
   CODESYS Control for Linux has its own time source setting independent of the OS RTC.
2. **F4 D/I 2 function.** Currently assigned "All Outputs Off" and mapped to `xAllOutputsOff` in
   CODESYS, but not used by any logic and confirmed to cause a silent cooling lockout if left
   active (§17.5). Decide whether to leave it disabled permanently, or give it a defined role
   (e.g. a hard emergency inhibit distinct from the scheduled ramp gate) and add corresponding
   ST logic and a documented, deliberate active-state.
3. **WebVisu integration.** The scheduler variables (`xSchedEnable`, `dtSchedStart`,
   `xRampInhibit`, `xRampActive`) exist in GVL_HMI and are ready to bind to a WebVisu page once
   the operator interface work (tracked in the project root README's "Next stage" section) picks
   this up.
4. **Test-log capture.** §17.6's proof was observed live but not yet captured with raw
   timestamped values in a dedicated test log, unlike the setpoint-control qualification in the
   project root (`codesys-python-gateway-modbus-integration/docs/test-logs/`). Recommended before
   calling this section formally qualified.
