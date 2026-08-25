# EL1859 Integration — Cabinet Start/Stop onto a Dedicated DI/DO Terminal

**Target cabinet for first fit:** Left Hand Large Temperature Cabinet
**Module:** Beckhoff **EL1859** — EtherCAT digital combi terminal, 8× DI 24 V DC + 8× DO 24 V DC, 0.5 A per output
**Status:** **Fitted and wired.** EL1859 installed as Card 10 on the Left Hand Large DLS rail;
pins 13/14/15 re-landed per §3.3; carriage received and terminal in service. Test record in §5
to be completed and signed off against measured values.
**Author:** Omkar Joshi · **Reviewed by:** _________ · **Date:** 25 August 2026

---

## 0. Relay topology confirmed against DLS008's live PLC_PRG and the as-drawn schematic

Before finalising this design, the two-relay topology assumed below was checked against two
independent sources for the Left Hand Small cabinet (DLS008), the reference for "latest working,
tested" logic:

- **The as-drawn field wiring schematic** (button station → Relay 1/Relay 2 → Omron COM/01/02).
  Confirms terminal-for-terminal: Relay 1 common/NO tied to bus 100 and wire 102 → Omron `01`;
  Relay 2 common fed from the button's own NC2 output, NC contact → wire 103 → Omron `02`. This
  matches §20.5 of the commissioning README exactly, so the two-relay design — not the abandoned
  "Option C" direct-to-button-station route — is confirmed as what's physically wired and is what
  this document's Card 10 allocation (§3.2) is designed around.
- **The live PLC_PRG source.** One correction came out of this: the start pulse is
  **`tSTART_PULSE : TIME := T#5S`**, not the 1 second previously written in the commissioning
  README's quick reference. That value is now corrected throughout both documents. Confirmed with
  Jason — 5 s stands.

One loose end this did **not** resolve: PLC_PRG's own comment describes `xStopPermit` in
"Option C" terms ("the button station's own 24 V supply... no relay needed"), which doesn't match
either the schematic or the M1–M6 test record already in the README (which shows `xStopPermit :=
TRUE` energising Relay 2 to stop the cabinet). That comment is almost certainly stale text left
over from an earlier design iteration and not something this change touches — this document does
not alter start/stop logic, only which physical terminal drives the same two signals — but it's
worth someone correcting the comment in PLC_PRG itself so the next person reading the source isn't
misled the way this check nearly was.

---

## 1. Why this change

Cabinet start/stop previously ran on **EL2869 CH15 / CH16** (temporary allocation). Those two channels were allocated in
`IO_Schedule.xlsx` to `3 Way BV03` and `3 Way BV02`, and the 37-way pins the field wiring used were
allocated as **digital inputs**. The arrangement worked and was tested, but it was borrowed — the
IO Schedule itself labeled the two rows *"Temporary Temp Cab Start"* and *"Temporary Temp Cab Stop"*.

The EL1859 retrofit makes it permanent and schedule-legal:

- cabinet start/stop gets its **own card** with its own row block in the IO Schedule;
- **EL2869 CH15/CH16 are handed back** to the valve functions they are allocated to;
- the spare DI half of the same terminal provides **measured run feedback**, closing the standing
  risk that `xCabinetRunning` is only a commanded-state proxy and cannot detect a cabinet that
  failed to start.

One EL1859 per DLS. Each cabinet has its own DLS, so two DO and one DI per module — six DO and
seven DI spare for future expansion.

---

## 2. Finding from the panel drawing — read this before wiring

Checked against **7168-DWG-100 REV B (AS BUILTS, 17/10/25)**, sheets 216, 217 and 218, and against
the current `IO_Schedule.xlsx`.

**Every pin on the DI/DO 37-way (`-202X3`) is already wired to a card inside the panel. There are
no free pins.**

| `-202X3` pins | Wired internally to | Drawing sheet | Wire numbers |
|---|---|---|---|
| 2–9 | `-215K1` (EL1409) I1–I8 | 215 | 215xx |
| **11–18** | **`-215K1` (EL1409) I9–I16** | **216** | **21601–21608** |
| 21–28 | `-217K1` (EL2869) O1–O8 | 217 | 21701–21708 |
| 30–37 | `-217K1` (EL2869) O9–O16 | 218 | 21801–21808 |
| 1, 10, 19 | Positive (24 V) | — | — |
| **20, 29** | **Negative (0 V)** | — | — |

Which means, specifically:

> **`-202X3` pin 13 is factory-wired to EL1409 digital input I11 (wire 21603).**
> **`-202X3` pin 14 is factory-wired to EL1409 digital input I12 (wire 21604).**
> Both are shown as SPARE on drawing sheet 216.

The as-built cabinet start/stop uses pins 13 and 14 to drive the relay coils, with pin 20 as the
0 V return. So somewhere in the panel those two pins have been fed from EL2869 CH15/CH16 —
which the drawing shows landing on pins 34 and 35, not 13 and 14.

**⚠ Verify before touching anything: are wires 21603 and 21604 still connected to `-215K1` I11/I12,
or were they lifted when the temp-cab start/stop was wired in?** Open the panel and trace both.
The answer decides step 3.3 below and it must be recorded on this document. Do not assume either
way — this is exactly the kind of undocumented modification that bites the next person.

Electrically, an EL1409 input sitting on the same pin as a sourcing output is not a fault (a DI is
designed to read 24 V), so nothing has been damaged either way. It is a **documentation and
allocation** problem, not a damage problem.

---

## 3. The change

### 3.1 Principle

**Nothing on the field side moves.** The relays, the Omron CPM1A, the button station and the
37-way pin numbers all stay exactly as commissioned and tested. Only the *inside-panel end* of
pins 13, 14 and 15 is re-landed onto the new terminal.

That is deliberate: it means the M1–M6 manual authority results already recorded for this cabinet
stay valid by construction, and the re-test is a confirmation rather than a fresh qualification.

```
UNCHANGED ─────────────────────────────────────────────────────────────►
  -202X3 pin 13 ── Relay 1 coil + ── Relay 1 NO 14 ── wire 102 ── Omron 01  (START)
  -202X3 pin 14 ── Relay 2 coil + ── Relay 2 NC 22 ── wire 103 ── Omron 02  (STOP)
  -202X3 pin 20 ── both relay coil 0 V returns
  -202X3 pin 15 ── cabinet run latch auxiliary contact ── fed from pin 19 (24 V)

CHANGES ───────────────────────────────────────────────────────────────►
  pin 13 internal wire:  -215K1 I11  ──►  EL1859 DO 1
  pin 14 internal wire:  -215K1 I12  ──►  EL1859 DO 2
  pin 15 internal wire:  -215K1 I13  ──►  EL1859 DI 1
  EL2869 CH15 / CH16:    released back to 3 Way BV03 / 3 Way BV02
```

### 3.2 Channel allocation — new Card 10

Follows the same convention as every other card block in `IO_Schedule.xlsx`.

| Card | Ch | Description | Type | Default state | `-202X3` pin | CODESYS tag |
|---|---|---|---|---|---|---|
| 10 | DO 1 | Temp Cab Start (Relay 1 coil) | DO 24 V | Off | 13 | `DLS.GVL_HMI.xStartPulse` |
| 10 | DO 2 | Temp Cab Stop (Relay 2 coil) | DO 24 V | Off | 14 | `DLS.GVL_HMI.xStopPermit` |
| 10 | DO 3–8 | Spare | DO 24 V | Off | — | — |
| 10 | DI 1 | Temp Cab Run Feedback (latch aux contact) | DI 24 V | Open | 15 | `DLS.GVL_HMI.xCabinetRunFb` |
| 10 | DI 2–8 | Spare | DI 24 V | — | — | — |

Released by this change, back to their IO Schedule allocation:

| Card | Ch | Returns to |
|---|---|---|
| 4 (EL2869) | CH15 | `3 Way BV03` |
| 4 (EL2869) | CH16 | `3 Way BV02` |

### 3.3 Rail position

Fit the EL1859 **at the end of the existing terminal block, immediately before the end terminal /
bus end cap** — after Card 9 (EL2564), making it Card 10.

**It must not go anywhere else on the rail.** EtherCAT terminals are addressed by physical
position, so inserting mid-rail shifts every terminal after it and silently breaks the existing
I/O mapping for the whole DLS.

Expected new designator, following the sheet-number convention used on the drawing
(`-215K1` = EL1409, `-217K1` = EL2869): **`-219K1`**. Confirm with whoever maintains the drawing
before it is stencilled, so the REV C markup and the physical label agree.

---

## 4. Build procedure

Work in this order. Steps 1–3 and 8–10 are dead-panel work.

### Phase 0 — Before opening the panel

1. Tell R&D the Left Hand Large cabinet is out of *remote* service for the change. Local button
   control is unaffected throughout — the two-relay topology fails safe to manual.
2. In CODESYS: confirm `xCabinetOnCmd = FALSE`, no start pulse in flight, `tOffLockRemain = 0`,
   cabinet stopped.
3. Record the **E-bus current budget** before adding a terminal: EK1100 supplies 2000 mA; sum the
   E-bus current of the nine fitted terminals and confirm the EL1859's own consumption (per its
   datasheet) still fits. If it does not, an **EL9410** E-bus refresh terminal is needed in front
   of it. *Check this before the visit — it is the one thing that can stop the job dead.*

### Phase 1 — Fit the terminal (supply isolated)

4. **Isolate the DLS 24 V control supply at the Siemens MCB.** EtherCAT terminals are not hot-swap
   on the E-bus — never fit or remove one with the coupler powered.
   > Panel rating plate: 230 V, 1 A, 0.22 kW, 5 kA. The 24 V control supply is `-200G1`
   > (24 V DC 5 A) via fuse `-200F1`; treat the incomer as live until proven dead.
5. Remove the end cap, clip the EL1859 onto the rail after the EL2564, refit the end cap.
6. Re-power. Measure **24 V ±2 V across the EL1859's power contacts**. The 24 V/0 V power contacts
   are passed through by the terminals ahead of it, but *measure, do not assume* — if it reads
   0 V, a potential-feed terminal (**EL9100**) is needed in front of the EL1859 and the job stops
   here until one is available.

### Phase 2 — CODESYS, before any field wiring

7. Go online, **Scan for Devices** under the EK1100. The EL1859 must appear as the last terminal,
   position 10. If the scanned order does not match the physical rail, **stop** — resolve that
   before wiring anything. Add it to the project and set its bus cycle task to **MainTask**
   (an unspecified task is the known cause of values that never update).
8. **Dry test with no field wiring on the new terminal:** force `EL1859 DO 1` in the watch window
   and measure 24 V at its output point; release and confirm 0 V. Repeat for DO 2. This proves
   terminal, mapping and task cycle with zero risk to the cabinet, while start/stop is still on
   the EL2869.
   > Terminal point numbering differs between Beckhoff HD terminals — read the connection diagram
   > printed on the EL1859 housing (and its datasheet) for which physical point is DO 1 / DI 1.
   > Do not carry the EL2869's numbering across by assumption.

### Phase 3 — Re-land the wiring (supply isolated again)

9. Isolate the 24 V supply again.
10. Re-land three internal wires, one at a time, labelling each with a ferrule as it moves:

    | Wire | From | To |
    |---|---|---|
    | 21603 (pin 13) | `-215K1` I11 | **EL1859 DO 1** |
    | 21604 (pin 14) | `-215K1` I12 | **EL1859 DO 2** |
    | 21605 (pin 15) | `-215K1` I13 | **EL1859 DI 1** |

    If the pin 13/14 wires were found *already lifted* from `-215K1` (see §2), land whatever
    conductor is actually feeding those pins onto the EL1859 instead, and remove the redundant
    EL2869 CH15/CH16 conductors entirely — do not leave a disconnected live-capable tail in the
    panel.
11. Confirm `-202X3` **pin 20** still has continuity to the 0 V rail (relay coil return).
12. Land the cabinet run latch auxiliary contact in the cabinet panel: **pin 19 (24 V) → aux
    contact → pin 15**. Volt-free contact only; if the available contact is not volt-free, stop
    and re-scope this part rather than improvising.

### Phase 4 — CODESYS mapping

13. Re-map `xStartPulse` → EL1859 DO 1 and `xStopPermit` → EL1859 DO 2.
14. **Delete** the EL2869 CH15/CH16 mapping rows so nothing can still drive them, and re-map those
    two channels to `3 Way BV03` / `3 Way BV02` per the IO Schedule.
15. Map EL1859 DI 1 → `xCabinetRunFb` (new). Leave `xCabinetRunning` as-is for now — do not change
    the interlock logic in the same commit as the wiring change. Compare the two in the watch
    window first; switching the logic over to the measured signal is a **separate, later change**.
16. **No other logic changes.** Same FB, same 5 s start pulse (`tSTART_PULSE := T#5S`), same 5-minute anti-short-cycle
    lockout.

### Phase 5 — Prove it

17. Coil check: command start, measure **24 ±2 V across Relay 1 coil**; command stop, same across
    Relay 2. Relays must retain their integral freewheel diodes — the EL1859's outputs need that
    inductive-spike protection just as the EL2869's did.
18. Run the full **M1–M6 manual authority suite** (§20.7 of the commissioning README).
    **Acceptance criterion: behaviour identical to the EL2869 route. If anything differs, the
    mapping is wrong, not the wiring.**
19. Fail-safe drill **F1**: power the DLS down with the cabinet running → red button must still
    stop the cabinet.
20. Run-feedback check: start locally by hand, confirm `xCabinetRunFb` goes TRUE; stop, confirm it
    goes FALSE. Then the real test of why this channel exists — command a start with the cabinet
    isolated so it *cannot* start, and confirm `xCabinetRunFb` stays FALSE while `xCabinetRunning`
    goes TRUE. That difference is the failure the DI was added to catch.

### Phase 6 — Paperwork, in the same change

21. `IO_Schedule.xlsx`: add the **EL1859 (Card 10)** sheet; return card 4 CH15/CH16 to
    `3 Way BV03` / `3 Way BV02`; update 37-way rows 13, 14 and 15 from *DI Spare / Temporary* to
    their permanent names, types and CODESYS tags.
22. Mark up **7168-DWG-100 for REV C**: new terminal `-219K1` on the rail, pins 13/14/15 re-landed,
    EL2869 CH15/CH16 released. The current REV B does not show the temp-cab start/stop at all, so
    this is the change that puts it on the drawing for the first time.
23. Record the results below and update the commissioning README.

---

## 5. Test record — Left Hand Large Temperature Cabinet

| # | Check | Expected | Result | Notes |
|---|---|---|---|---|
| 0 | Wires 21603/21604 traced at `-215K1` | Finding recorded | ☐ | Connected / lifted: ________ |
| 1 | E-bus budget within 2000 mA | Pass | ☐ | Measured/calculated: ______ |
| 2 | EL1859 power contacts | 24 V ±2 V | ☐ | |
| 3 | Bus scan shows EL1859 at position 10 | Match | ☐ | |
| 4 | Dry test DO 1 / DO 2 | 24 V on, 0 V off | ☐ | |
| 5 | Pin 20 continuity to 0 V rail | Continuous | ☐ | |
| 6 | Relay 1 coil on start command | 24 V ±2 V | ☐ | |
| 7 | Relay 2 coil on stop command | 24 V ±2 V | ☐ | |
| 8 | M1 local start | Cabinet starts | ☐ | |
| 9 | M2 local stop | Cabinet stops | ☐ | |
| 10 | M3 remote start | Cabinet starts | ☐ | |
| 11 | M4 remote stop | Cabinet stops | ☐ | |
| 12 | M5 lockout blocks restart | Blocked | ☐ | |
| 13 | M6 restart after lockout | Starts | ☐ | |
| 14 | F1 DLS off, red button | Cabinet stops | ☐ | |
| 15 | Run feedback follows real state | TRUE only when running | ☐ | |
| 16 | Failed-start case | `xCabinetRunFb` FALSE | ☐ | |

**Signed off:** ________________  **Date:** __________

---

## 6. Open items

| # | Item | Owner | Note |
|---|---|---|---|
| 1 | Trace wires 21603/21604 at `-215K1` and record the finding | — | Blocks §3.3; do first |
| 2 | Confirm E-bus current budget; order EL9410 if short | — | Blocks Phase 1 |
| 3 | Confirm EL1859 terminal point numbering from the housing diagram | — | Blocks Phase 3 |
| 4 | Confirm new card designator `-219K1` with the drawing owner | — | Before labelling |
| 5 | Confirm the cabinet run latch aux contact is volt-free | — | Blocks §Phase 3 step 12 |
| 6 | Switch interlock logic from `xCabinetRunning` to `xCabinetRunFb` | — | **Separate change, after this one is proven** |
| 7 | Repeat on remaining cabinets once proven here | — | One EL1859 per DLS |

---

## 7. References

| Document | Relevance |
|---|---|
| `README.md` (this folder) | Two-relay as-built wiring, M1–M6 suite, per-cabinet status |
| `ROLLOUT-CHECKLIST.md` | JOB 4 and the open risks this change closes |
| `IO_Schedule.xlsx` | Card and 37-way pin allocation |
| `../docs/7168-DWG-100 - REV B - CP1.pdf` | Sheets 216/217/218 — `-202X3` pin-to-card map; sheet 200 — 24 V supply `-200G1`; sheet 106 — `-202X3` on the gland plate |
| `../docs/Omron PLC CP1MA Datasheet.pdf` | CPM1A input type — why a sourcing output works here |
| Beckhoff EL1859 documentation | Terminal point numbering, E-bus current, DI/DO ratings |
