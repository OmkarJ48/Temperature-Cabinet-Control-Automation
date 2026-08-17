# Commissioning of Temperature Cabinets — Cabinet On/Off Automation

**Status (17 August 2026):** RS232-to-USB cable (RS 1860518) arrived and connected across all cabinets.

- ✅ **Left Hand Large Temperature Cabinet**: Full commissioning complete
- ✅ **Twinsafe Temperature Cabinet**: Full commissioning complete  
- ▶ **Right Hand Large Temperature Cabinet**: Panel mount USB replaced; cable button switch to relays connection done; awaiting 37-pin connector wiring to pins 13, 14, and GND
- ▶ **Left Hand Small Temperature Cabinet (DLS008)**: Cable button switch to relays connection done; awaiting 37-pin connector wiring to pins 13, 14, and GND
- ⏳ **Right Hand Small Temperature Cabinet**: Requires separate F4T register-map investigation before commissioning

**Awaiting:** EL1859 digital input/output module and carriage for future I/O expansion (not blocking current commissioning).

---

## Commissioning Design — Two-Relay Architecture

The cabinet on/off automation uses a proven two-relay interposing design for fail-safe remote start/stop control:

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
| Red | Relay 1 terminal `14` (NO) | wire `102` → Omron terminal `01` | Start command — parallel with the local button's own `102` path, exactly the OR/parallel-start logic |
| Blue | `NC2` (local stop contact output) | Relay 2 terminal `21` (common) | Ties the local stop output into the same relay junction that also carries the remote stop source |
| Orange | Relay 2 terminal `22` (NC) | wire `103` → Omron terminal `02` | Stop command — lands on the same Omron input as the local button's `NC2` output |
| Red (bottom bus) | `NO4` (button station's physical `102` terminal) | field wire `102`, return via 0 V/ground rail (`Y`) | Physical wire-number continuity check |

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

---

## 20.2 Wiring — as tested, from the reference diagram

Two interposing relays, each a standard DIN-rail 2-changeover-contact relay (terminal numbering
`11`/`14`/`12` and `21`/`24`/`22` — commons `11`/`21`, NO `14`/`24`, NC `12`/`22`), one per
function:

**Relays must have integral freewheel diodes** to protect the EL2869 digital outputs from inductive spike.

---

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

## 20.4 Integration test — Left Hand Small Temperature Cabinet (DLS008)

**Result: ✅ PASS.** With both relays wired per the design and the local button station left
physically unmodified:

| Test | Action | Result |
|---|---|---|
| Local start | Green button pressed by hand | Cabinet started |
| Local stop | Red button pressed by hand while running | Cabinet stopped immediately |
| Remote start | `xStartPulse := TRUE` from CODESYS | Relay 1 energised, CH15 LED lit, cabinet started |
| Remote stop | `xStopPermit := TRUE` from CODESYS | Relay 2 energised, CH16 LED lit, cabinet stopped |
| Local/remote coexistence | Both button and relay wiring landed on the same `01`/`02` inputs simultaneously | No fault, no contention — confirms the OR behaviour |

This closes the open item — manual physical authority is now **confirmed by test**, because the 
two-relay topology keeps the local button's own contacts electrically intact and merely adds a 
parallel, isolated source at the same input.

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
| 4 | Button switch wired per two-relay design | ☐ |
| 5 | Relay coils confirmed 24 ±2V DC | ☐ |
| 6 | Manual authority tests M1–M6 all pass | ☐ |

---

## 20.11 12-item handover verification

- [ ] D1: Document read and understood
- [ ] D2: Wiring diagram matches physical installation
- [ ] D3: BOM verified against actual parts
- [ ] H1: Relay coils 24 ±2V DC; supply stable
- [ ] H2: Relay contacts tested; NO/NC logic correct
- [ ] H3: Cable shielding grounded at both ends
- [ ] H4: Wires labeled with ferrules; legible
- [ ] S1: CODESYS downloaded; `xSetOperational` = TRUE
- [ ] S2: Watch-window procedure executed
- [ ] S3: Manual authority tests M1–M6 passed
- [ ] F1: Fail-safe test: DLS008 off; red button still stops cabinet
- [ ] F2: Operator trained; red button priority confirmed

**Approved by:** ________________ **Date:** __________

---

## Cabinet rollout order and status

| # | Cabinet | Controller | Status |
|---|---|---|---|
| 0 | **Left Hand Small Temperature Cabinet (DLS008)** | Watlow F4S + Omron CPM1A | ▶ **In progress** — panel USB done, cable button switch to relays done; **awaiting 37-pin connector wiring** (items 3–4 of checklist remaining) |
| 1 | **Left Hand Large Temperature Cabinet** | *confirm on survey* | ✅ **Commissioning complete (12 August 2026)** — all 4 items done |
| 2 | **Twinsafe Temperature Cabinet** | *confirm on survey* | ✅ **Commissioning complete (13 August 2026)** — all 4 items done |
| 3 | **Right Hand Large Temperature Cabinet** | *confirm on survey* | ▶ **In progress** — panel mount USB replaced; cable button switch to relays connection done; **awaiting 37-pin connector wiring** |
| 4 | Right Hand Small Temperature Cabinet | **Watlow F4T — different controller, register map unproven** | ☐ Not started — needs a separate investigation stage before commissioning |

---

## Procurement status (17 August 2026)

| Item | Supplier | Status |
|---|---|---|
| 2-Port USB Type A panel mount (RS 282-844) | RS Components | ✅ Procured & fitted |
| USB Type A 1.8 m / 3 m / 5 m cables | RS Components | ✅ Procured & installed |
| **RS232 to USB A cable** (RS 1860518) | RS Components | ✅ **Arrived and connected across all cabinets** |
| Single-core wire (yellow) | RS Components | ✅ Procured & installed |
| XLR 4-way female/male connectors | RS Components | ✅ Procured |
| Cable tie mount | RS Components | ✅ Procured & used |
| **EL1859 16-channel Digital Input/Output module** | Beckhoff | ⏳ On order — future I/O expansion, not blocking current commissioning |
| Carriage (EL1859 order) | Beckhoff | ⏳ On order — future I/O expansion, not blocking current commissioning |

---

## Detailed status updates

### Left Hand Large Temperature Cabinet

**Status (12 August 2026):** ✅ **Commissioning complete.**

All four items of the commissioning checklist are done:
1. ✅ Panel mount USB mounted on enclosure
2. ✅ USB wiring harness routed from Raspberry Pi to panel mount
3. ✅ Relay wiring to pins 13 & 14 complete per two-relay design
4. ✅ Button wiring to PLC relays complete

Physical wiring harness uses:
- Yellow industry-grade wire (1.5 mm) for power distribution bus (clamped to rail with cable ties)
- Small-gauge black, green, and red wires (DLS pins 13 & 14 connections, same harness)
- All wires clamped and fastened to existing cabinet wire bundle using cable clamps

RS232 cable (RS 1860518) now arrived and installed for comms path validation.

---

### Twinsafe Temperature Cabinet

**Status (13 August 2026):** ✅ **Commissioning complete.**

All four items of the commissioning checklist are done:
1. ✅ Panel mount USB mounted on enclosure
2. ✅ USB wiring harness routed from Raspberry Pi to panel mount
3. ✅ Relay wiring to pins 13 & 14 complete per two-relay design
4. ✅ Button wiring to PLC relays complete

All physical wiring and connectivity identical to Left Hand Large Cabinet. RS232 cable (RS 1860518) now arrived and connected.

---

### Right Hand Large Temperature Cabinet

**Status (17 August 2026):** ▶ **In progress.**

- ✅ Panel mount USB replaced
- ✅ Cable button switch to relays connection done
- ⏳ **Awaiting:** 37-pin connector wiring to pins 13, 14, and GND of relays

Following the same 4-item commissioning process as Left Hand Large and Twinsafe Cabinets.

---

### Left Hand Small Temperature Cabinet (DLS008)

**Status (17 August 2026):** ▶ **In progress — ~75% complete.**

- ✅ Panel mount USB Type A to Type A connected
- ✅ Cable button switch to Omron CPM1A PLC wiring complete (per two-relay design)
- ⏳ **Awaiting:** 37-pin connector wiring to pins 13 & 14 (from DLS output to relay coils)

Once complete, will connect RS232 adapter cable and validate comms path.

---

## Next steps

1. **DLS008 & Right Hand Large:** Complete 37-pin connector wiring (pins 13, 14, GND to relays)
2. **All cabinets:** Run manual authority tests M1–M6 per the test suite
3. **Right Hand Small:** Conduct F4T register-map investigation (separate track from current commissioning)
4. **Future:** Install EL1859 module when hardware arrives (future I/O expansion project)
