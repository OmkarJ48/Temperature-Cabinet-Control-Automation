# Cabinet On/Off Automation: Investigation & Integration Guide

**Status:** Investigation complete, integration design ready, awaiting hardware confirmation  
**Author:** Omkar Joshi — Oliver Mechatronics  
**Date:** 28 July 2026  
**Objective:** Enable remote control of the Watlow F4S cabinet on/off switch via EL2869 digital output

---

## Discovery & Findings

### What the front switch actually does

The **front-panel on/off selector switch** (3-position: green I / white / red O) does NOT cut mains power to the cabinet or the F4S controller itself. Instead, it controls a **24V DC relay coil** that gates the compressor/fan contactor outputs.

**Evidence:**
- CODESYS Modbus TCP link to the gateway **stays active** when switch is flipped OFF
- F4S display remains lit, controller stays powered and responsive
- All 150 Modbus registers read identically before and after the switch flip
- Compressor/fan physically stops when switch goes OFF, but F4S remains online

**Conclusion:** The switch implements a **soft off** — outputs are disabled at the relay level, not at the mains level. This is the ideal scenario for remote automation.

---

## Architecture: The Relay Control Block

Inside the cabinet, a **3-relay control block** (DIN-rail mounted) gates the outputs:

| Relay | Label | Function | Control |
|---|---|---|---|
| Left | NO 3 | Compressor/fan contactor output | Always energized (from F4S output) |
| **Middle** | **X** | **ON/OFF gate relay** | **Controlled by the front switch** |
| Right | NC 1 | Safety/interlock | Static or condition-based |

**Middle relay coil circuit:**
- **Coil wires:** Blue (common) and yellow (switched)
- **Protection:** 100Ω resistor in series (load/protection resistor)
- **Voltage:** Expected 24V DC (to be confirmed with multimeter)
- **Current:** ~20–50 mA (based on resistor value)

**Control logic:**
```
Switch ON → Relay coil energized → Relay contacts close → Compressor gate enabled → Cabinet cools/heats
Switch OFF → Relay coil de-energized → Relay contacts open → Compressor gate disabled → Cabinet drifts
```

---

## Integration Approach: Three Options

### **Option A: Parallel Tap (Recommended — lowest invasiveness)**

Wire the EL2869 output in **parallel** to the relay coil alongside the physical switch.

**Architecture:**
```
┌─ Front switch ────────┐
│                       ├─→ Relay coil (24V, 20–50mA) → Compressor ON/OFF
└─ EL2869 OUT (remote) ─┘

Logic: Relay energizes if EITHER switch OR remote commands ON (OR gate)
```

**Pros:**
- No disconnections — existing switch stays fully functional
- Hardware fallback: if remote fails, manual switch still works
- Cleanest wiring (2-wire parallel tap)
- Non-invasive to cabinet certification/FGAS record

**Cons:**
- Switch and remote can "fight" if they disagree (e.g., switch ON but remote OFF)
  - Mitigation: implement software interlocks in Python/CODESYS (e.g., if manual switch disagrees with remote state for >10s, log a warning)

**Implementation complexity:** ~20 lines Python or CODESYS

---

### **Option B: Series Interposition (Medium invasiveness)**

De-wire the switch completely, interpose the EL2869 in series with it as the sole authority.

**Architecture:**
```
EL2869 is the PRIMARY authority. Physical switch is optional feedback/override.
Remote commands ON/OFF; local switch can request manual override via a separate input channel.
```

**Pros:**
- Remote has sole authority; no conflicts
- Can implement sophisticated logic (anti-short-cycle delay, maintenance interlocks, etc.)
- Cleaner state machine (one clear command source)

**Cons:**
- Requires breaking and re-routing the switch wires (higher risk of mistakes)
- If remote fails, cabinet cannot be turned on without re-wiring the switch back in
- More invasive testing required before deployment

**Implementation complexity:** ~40 lines Python/CODESYS + state machine logic

---

### **Option C: Hybrid with 24V Relay (Medium-high invasiveness)**

Add a small 24V intermediate relay that both switch and remote can energize independently (OR logic at the relay level, not in wiring).

**Pros:**
- Both inputs can turn ON independently; at least one getting to ON = cabinet ON
- Clean separation of concerns
- Relay provides electrical isolation

**Cons:**
- Extra DIN-rail component
- More wiring complexity
- Overkill for a binary signal

**Recommendation:** Skip this unless you need isolation for other reasons.

---

## Hardware Specification (to confirm)

**Critical — must measure before integration:**

```
Multimeter reading checklist (mains OFF, isolated):
- [ ] Relay coil voltage, switch ON: ______ V DC
- [ ] Relay coil voltage, switch OFF: ______ V DC
- [ ] Expected: 24V ON, 0V OFF
- [ ] Relay model/part number (visible on relay case): ____________
- [ ] Coil current rating: ______ mA (from datasheet)
```

**DLS008 EL2869 Available Output:**
- **Channel:** OUT 1, 2, 3, 4 (pick one spare, e.g., OUT 3)
- **Terminal block:** Pins 48–50 (DC+, DC−, Output)
- **Voltage:** 24V DC (DLS008 standard)
- **Current capability:** 2 A per channel (relay coil needs ~20–50 mA — well within spec)
- **Max frequency:** 100 kHz (relay response is slow, ~20 ms — no issue)

---

## Integration Paths

### **Path 1: Standalone Python + Systemd (fastest to MVP)**

Create `cabinet_on_off.py` as a systemd service that:
- Listens on a TCP socket or reads a config file
- Commands the EL2869 output via Beckhoff TwinCAT API or GPIO mapping
- Logs all state changes

**Pros:** Decoupled from CODESYS; independent operation; fast iteration  
**Cons:** Requires EL2869→Pi GPIO bridging logic (may not be straightforward)

### **Path 2: Integrate into CODESYS Gateway (recommended)**

Add a new Modbus register to the f4s_gateway.py:
- **Register 5:** ON/OFF command (read/write, 0 = OFF, 1 = ON)
- Wire this register to GVL_Modbus in CODESYS
- Map GVL_Modbus.xOnOff to the EL2869 output in I/O Mapping

**Pros:** Unified control with setpoint logic; single Modbus interface; matches existing architecture  
**Cons:** Requires CODESYS project modification; testing requires full runtime

### **Path 3: Both (recommended long-term)**

- Python handles low-level on/off via EL2869 (hardware interface)
- CODESYS interfaces through gateway Modbus (application logic)
- Python exposes a `/health` endpoint so CODESYS can confirm state

---

## Next Steps (Blocking)

1. **Voltage confirmation** (5 min):
   - Measure relay coil voltage with switch ON and OFF
   - Post multimeter readings

2. **Option choice** (decision):
   - Option A (parallel, recommended) or Option B (series)?
   - Any constraints on local vs. remote authority?

3. **Integration path** (architecture):
   - Python systemd + direct EL2869 command?
   - CODESYS gateway Modbus register (register 5)?
   - Both?

4. **Once approved:** Wiring diagram, pinout, and 15-line implementation code

---

## Reference Files

| File | Purpose |
|---|---|
| `on-off-control.py` (to be created) | Standalone Python service or CODESYS integration wrapper |
| `wiring-diagram.md` (to be created) | Exact terminal pinouts and cable routing |
| `testing-checklist.md` (to be created) | Step-by-step hardware verification before deployment |

---

## Safety Notes

- **Mains isolation required** for all wiring work (cabinet main breaker OFF)
- **24V DC is low-voltage, safe to work live** — but confirm with multimeter before assuming
- **Relay coil inrush current:** Beckhoff EL2869 solid-state relay can handle 20–50 mA comfortably
- **Compressor short-cycle protection:** If implementing remote command, **software must enforce a 5-minute minimum off-time** before allowing next ON command (refrigeration compressor damage risk)
- **Fallback mode:** Option A keeps manual switch active — ensures operator can always toggle locally if remote fails

---

## Cabinet Specifications (Reference)

| Item | Value |
|---|---|
| Cabinet | Left Hand Small Temperature Cabinet (JTS Ltd, Wales) |
| Controller | Watlow F4S, F4SH-CCA0-01RG, SN 038983 |
| Control voltage | 24V DC (DLS008 standard) |
| Compressor | Driven by F4S Out 1 relay, gated by middle relay (X) |
| Modbus | RTU over RS-232 @ 19200 8N1, gateway @ TCP:502 |
| Runtime | CODESYS Control for Linux ARM64 SL on Raspberry Pi 10.1.6.17 |

---

**Status:** Awaiting hardware confirmation. Once relay coil voltage and integration path are decided, proceed to wiring and code implementation.
