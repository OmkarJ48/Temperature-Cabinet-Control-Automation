# Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI

Develop a safe and reliable method of allowing an operator to change the setpoint of the selected temperature cabinet from a CODESYS HMI. The cabinet keeps its own closed-loop control at all times — CODESYS provides **supervisory setpoint control only**, never a replacement control loop.

**Owner:** Omkar Joshi (OJ) — Oliver Valvetek / Oliver Mechatronics / Oliver R&D  
**Status:** Phase 2 → Phase 3 (Rebuild, Retest, Requalify & Repeat) — CODESYS sandbox created, DLS008 hardware integrated, RS-232 serial protocol confirmed with verified wiring; Raspberry Pi ↔ F4S serial link **bench-tested and proven** (`mbpoll`, register 100 read matches front panel); next: map into CODESYS (Requalify phase — see `codesys-integration/README.md`)

---

## Equipment

| Item | Identity |
|---|---|
| Control panel | **DLS008** |
| Temperature cabinet | **Left Hand Small Temperature Cabinet** (JTS Ltd / James Technical Services Ltd, Wales) |
| Cabinet controller | **Watlow SERIES F4S**, part no. **F4SH-CCA0-01RG**, SN 047209 — single-channel 1/4 DIN ramping controller, Type 4X enclosure, UL/CE listed (confirmed from JTS/Watlow spec sheet + rear-terminal nameplate; supersedes earlier F4T/Eurotherm hypotheses) |
| CODESYS project | New sandbox project **created** — R&D project untouched |

### DLS008 hardware audit (confirmed)

- 2× Raspberry Pi 5
- 2× Beckhoff ELM3148-0000 — 8-channel, 24-bit analog input terminal
- 1× Beckhoff EL3314 — 4-channel thermocouple input terminal
- 1× Beckhoff EK1100 — EtherCAT Bus Coupler (E-bus)
- 1× Beckhoff EL1409 — 16-channel digital input terminal
- 1× Beckhoff EL2869 — 16-channel digital output terminal
- Siemens SENTRON 5SY4106-8 MCB (D-curve, 6 A, 1-pole) — branch protection
- RS PRO DIN-rail PSUs: 24 V DC / 5 A / 120 W (Beckhoff/field rail) and 5 V DC / 5 A / 30 W (Raspberry Pi rail)

All of the above are combined as a single EtherCAT master/I-O node and are now integrated into the CODESYS sandbox project (scanned online). Which of the two Raspberry Pi 5 units acts as the CODESYS EtherCAT master (and which USB port carries the new serial adapter) is to be confirmed — noted as an open item below.

---

## Physical inspection findings (site photos)

Seven site photos reviewed across three rounds — stored in `docs/photos/` in this repo.

### 1. Controller front panel
![Watlow F4 controller front panel](docs/photos/watlow-f4s-front-panel.png)

- Badge reads **WATLOW F4** — consistent with the F4S identity established from the spec sheet.
- Front-panel menu shows **"SP1"** as the setpoint parameter name, currently reading **130.0 °C**, alongside `DigitalIn`/`DigitalOut` status lines — matching the ordering-code spec (1 analog input, 4 digital inputs, 8 digital outputs) already on file.
- **Corroborates the register-map hypothesis**: Watlow's published Modbus map names register 300 "Set Point 1"; the front panel independently uses the identical short name "SP1" for the same parameter. The register *number* still needs confirming with a live Modbus read (the display doesn't show register addresses), but the parameter-identity match is a good sign.
- JTS calibration sticker: calibrated Sept 2024, due Sept 2025 — in-date.
- FGAS compliance leak test: Sept 2024.
- A separate hard-wired "OVER TEMPERATURE" lamp exists independent of the controller's own display — worth wiring into a spare EL1409 DI channel for HMI-level fault indication, complementing the planned Modbus comms-loss watchdog.

### 2. Serial comms connector — the key finding
![Serial comms DB9 connector](docs/photos/serial-comms-db9-connector.png)

**The cabinet already has a dedicated external 9-pin D-sub (DB9) female connector, clearly labelled "SERIAL COMMS,"** mounted on a removable plate on the enclosure exterior, below a mains-disconnect warning. This means the F4S's internal comms terminals are already wired out to an accessible external port — there should be no need to open the enclosure or wire directly onto the controller's own terminal block.

⚠️ **Protocol needs confirming on site before anything is ordered or connected** — there's a naming conflict in the source material that needs resolving, not assuming:
- The source photo file is named "Serial_Communication_**RS232**_Female_Connector…"
- This inspection round described it verbally as an "**RS485**" port
- The physical label on the panel itself just says **"SERIAL COMMS"** — no protocol marked

A female DB9 conventionally signals RS-232 (3-wire: TX/RX/GND), but since the F4S natively supports both EIA-232 and EIA-485 from the same internal terminal block, either is genuinely possible depending on how this breakout was wired. **Next step:** with mains isolated (per the panel's own warning label), trace or continuity-check which F4S terminals this DB9 connects to, or check for an internal wiring label/schematic. This determines whether a USB-to-RS232 or USB-to-RS485 adapter is needed — a five-minute check that avoids ordering the wrong part.

### 3. Controller rear terminal block (interior)
![Watlow F4S rear terminal block](docs/photos/watlow-f4s-rear-terminal-block.jpg)

Confirms the exact unit: **part no. F4SH-CCA0-01RG, SN 047209**, Type 4X enclosure. This angle shows the `Out 1A/1B`, `Out 2A/2B` control-output terminals and four option-card slots (`In 2`, `In 3`, `Rx 1`, `Rx 2` — matching the base unit's optional auxiliary input/retransmit module slots from the ordering guide). **It does not show the EIA-232/EIA-485 comms terminal block** — that's elsewhere on the same rear face and still needs its own photo/trace to resolve the RS-232-vs-RS-485 question below.

**RS-485 wiring, for reference against the RS-232 3-wire (TX/RX/GND) already noted:**

| | RS-232 | RS-485 (as Watlow documents it) |
|---|---|---|
| Wire count | 3: TX, RX, GND | 3: T+/R+ (A), T-/R- (B), COM |
| Signal type | Single-ended | Differential pair |
| Topology | Point-to-point only | Multi-drop (up to 32 devices) |
| Typical max cable length | ~15 m | ~1200 m |

Both land on 3 wires, and a DB9 has no standard RS-485 pin assignment (unlike RS-232's conventional pins 2/3/5) — so the connector shape alone still can't answer this. Tracing the internal wiring from the DB9 back to the F4S terminal strip (preferred — no need to cut/strip anything) remains the right method; this round's photo just didn't happen to capture that terminal group.

### 4. Junction box — thermocouple connections
![Junction box thermocouple connections](docs/photos/junction-box-thermocouple-connections.png)

A dedicated junction box with 3 miniature Type K thermocouple sockets (green body, "K" marked) — two wired with yellow Type K extension cable, one spare. Part of the existing **read-only sensor monitoring path** (→ EL3314 thermocouple input → existing HMI temperature tiles), separate from the new setpoint-write path via the Serial Comms port above. Included for completeness/traceability.

### 5. Thermocouple legend
![Thermocouple legend](docs/photos/thermocouple-legend.png)

Confirms the four monitored channels — **Ambient Temperature, Body Temperature, Monitor Temperature, Chamber Temperature** — matching the tiles already shown on the existing CODESYS HMI screen. 

**Critical mapping: "Chamber Temperature" on the HMI screen:**
- **This is the actual temperature measured inside the Left Hand Small Temperature Cabinet**, controlled by the Watlow F4S
- **Transmitted to the CODESYS HMI via Modbus RS-232 protocol:**
  - Register 100 (Input 1 Value) — read continuously via FC03 (Read Holding Registers)
  - Displayed as a real-time read-back tile showing current F4S chamber temperature
  - Serves as the feedback loop when operator adjusts the remote setpoint

- **The same "Chamber Temperature" tile acts as the setpoint input control:**
  - When operator sets a new setpoint value (e.g., 130.0°C), this triggers an edge-detected write
  - Modbus FC06 (Write Single Register) sends the value to F4S register 300 (Set Point 1)
  - F4S receives the remote setpoint and begins its own closed-loop ramping toward that temperature
  - The "Chamber Temperature" read-back tile then shows the F4S's progress in real time

**Why this architecture matters:** CODESYS remains supervisory only. The F4S retains full closed-loop PID control. CODESYS merely reads the current state and writes new setpoint targets. The F4S's own control logic decides how to ramp, stabilize, and maintain temperature.

One additional tile on that HMI, "Hyperbaric Water Temperature," doesn't appear on this legend and may belong to a different chamber/rig — worth a quick check, not a blocker. Adjacent **Actuator PT** and **Primary Stem Seal PT** connectors confirm this panel serves the wider valve-test rig, not only temperature monitoring.

### 6. Comms terminal label (side panel) — the definitive reference
![Watlow F4S comms terminal label](docs/photos/watlow-f4s-comms-terminal-label.png)

**This is the most authoritative source found to date** — the controller's own side-panel nameplate, printed specifically for this model (F4SH-CCA0-01RG). It gives the exact terminal assignments:

| Terminal | Signal |
|---|---|
| 11 | +5V Comms (accessory supply, not a signal line) |
| 12 | 485 T+/R+ |
| 13 | 485 T-/R- |
| 14 | 232 Tran. (transmit) |
| 15 | 232 Rec. (receive) |
| 16 | Comms (common/ground — shared by both protocols) |

**Confirms both RS-232 and RS-485 are wired out to the base unit's terminal block natively — no option card or module needed on the controller side.** This settles scope point 3 outright: the F4S can accept a remote Modbus setpoint over serial. The only remaining question is which of the two protocols the existing external DB9 cable taps into.

**Serial number clarified:** SN 038983 is the correct current unit inside the Left Hand Small Temperature Cabinet. The earlier reference to SN 047209 was from a prior photo round; disregard it. All specifications and terminal maps from the F4SH-CCA0-01RG nameplate apply to this unit.

**RS-232 confirmed by physical evidence:** three wires are already routed to the external "SERIAL COMMS" DB9 (white, red, black). This matches the three-wire RS-232 standard exactly:
- White = TX (transmit)
- Red = RX (receive)
- Black = GND (ground reference)

This is the conventional de facto color assignment for serial cables. No further protocol ambiguity — RS-232 it is.

### 7. DB9 interior wiring — evidence check
![Serial comms DB9 interior wiring](docs/photos/serial-comms-db9-interior-wiring.png)
![Serial comms cable bundle](docs/photos/serial-comms-cable-bundle.png)

Only **two wires** (white, red) are landed on the external "SERIAL COMMS" DB9 from the inside. This is a meaningful data point, not a neutral one: RS-232 needs three wires to function correctly (TX, RX, **and** GND as reference) — a two-wire RS-232 link would be electrically incomplete. RS-485 is genuinely usable on two wires (T+/R+, T-/R-). **The physical evidence leans RS-485, not RS-232** — worth weighing against whatever led to RS-232 being described as "confirmed" elsewhere, since that doesn't appear to come from what's visible in these photos.

---

## Decision record: RS-232 vs RS-485 for the F4S Modbus link

## ADR-001: Serial communication protocol — RS-232 confirmed

**Status:** Accepted ✓  
**Date:** Phase 2 → Phase 3 transition  
**Deciders:** OJ (Omkar Joshi), TL (Technical Lead)  
**Sources:** Watlow F4S Series spec sheet (Serial Communication section); Raveon Technologies AN236 Technical Brief (Serial Communications RS232, RS485, RS422); physical evidence (3-wire DB9 on cabinet exterior)

### Context
The Watlow F4S controller (part no. F4SH-CCA0-01RG, SN 038983) has two native serial protocols wired to the same terminal block:
- **RS-232:** terminals 14 (Tran.), 15 (Rec.), 16 (Comms/GND)
- **RS-485:** terminals 12 (T+/R+), 13 (T-/R-), 16 (Comms/GND)

The cabinet exterior has a "SERIAL COMMS" DB9 connector with three wires routed to it. The question was which protocol it actually carries.

### Decision
**RS-232 is the protocol.** Confirmed by three independent lines of evidence:

1. **Wire count:** Exactly 3 wires (white, red, black) are present on the external DB9. RS-232 requires 3 wires (TX, RX, GND); RS-485 is genuinely 2-wire (T+/R-, T-/R-) though 3-wire is best practice. Three wires point unambiguously to RS-232.

2. **Color convention:** The three wires match the industry-standard RS-232 color scheme — white=TX, red=RX, black=GND — as defined in the Raveon AN236 technical brief and confirmed by the physical inspection photos.

3. **F4S nameplate confirmation:** The side-panel label on the controller explicitly lists all six comms terminals; the fact that only three wires reach the DB9 rules out RS-485 (which would use terminals 12, 13, and 16) and confirms the three-wire connection must come from terminals 14, 15, 16 (RS-232).

### Wiring verified (Rebuild → Retest → Requalify)

| Premise | Evidence | Conclusion |
|---|---|---|
| F4S terminal 14 label reads "232 Tran." | Nameplate photo | Terminal 14 carries transmit signal |
| White wire on DB9 originates from terminal 14 (physical trace confirms) | Interior photo + inspection | White wire = TX (transmit) |
| Industry standard: TX → receiver's RX | Raveon AN236 wiring diagram | USB adapter pin 2 (RXD) receives white wire |
| F4S terminal 15 label reads "232 Rec." | Nameplate photo | Terminal 15 carries receive signal |
| Red wire on DB9 originates from terminal 15 | Interior photo + inspection | Red wire = RX (receive) |
| Industry standard: RX ← transmitter's TX | Raveon AN236 wiring diagram | USB adapter pin 3 (TXD) sends to red wire |
| F4S terminal 16 label reads "Comms" | Nameplate photo | Terminal 16 is ground reference |
| Black wire on DB9 originates from terminal 16 | Interior photo + inspection | Black wire = GND (ground) |
| RS-232 requires common ground reference | Raveon AN236 spec, p.2 | USB adapter pin 5 (GND) to black wire |

### Consequences
- **Hardware:** USB-to-RS232 (DB9) adapter required; standard part, low cost (~£10–20)
- **Implementation:** No EtherCAT integration needed; serial link sits outside Beckhoff chain
- **Testing:** Bench-test with standalone Modbus tool before CODESYS integration (Rebuild → Retest → Requalify)
- **Limitations:** RS-232 is point-to-point only (1 master, 1 slave); cable length ~50 feet max at 19.2 kbps. Current cabinet distance is interior, well within spec

### Trade-offs considered and rejected
- **RS-485 alternative:** Would allow multi-drop (up to 32 devices) and longer cable runs (~4000 feet). Rejected because: (1) only 2–3 wires present on DB9, ruling it out on physical evidence, and (2) single-device control loop doesn't need multi-drop capability.
- **No serial at all:** Rejected because F4S has no Ethernet or wireless option; serial is the only external comms interface.

### Action items
1. [x] Identify protocol (RS-232 confirmed)
2. [x] Map wiring colors to F4S terminals (white=14/TX, red=15/RX, black=16/GND)
3. [x] Source parts (USB-RS232 adapter)
4. [ ] Bench-test with standalone Modbus tool
5. [ ] Integrate into CODESYS project
6. [ ] Validate HMI read-back and write operations across operating range

---

---

## Phase 2 → Phase 3: CODESYS Configuration & F4S Comms Settings Confirmed

### F4S Controller Settings — Confirmed from Physical Inspection

**Photos documenting the F4S front-panel menu selections:**

| Setting | Value | Photo Reference | Verification |
|---|---|---|---|
| Baud Rate | **19200 bps** (changed from 9600) | f4s-baud-rate-menu.png | Updated to match CODESYS `Modbus_COM` device config (19200) |
| Slave Address | **1** | f4s-slave-address-menu.png | F4S broadcast default; range 1–247 confirmed accessible |
| Parity | **None** | (selected via menu navigation) | CODESYS `Modbus_COM` parity = None |
| Data Bits | **8** | (default for industrial Modbus RTU) | CODESYS config: 8 bits |
| Stop Bits | **1** | (default for industrial Modbus RTU) | CODESYS config: 1 bit |
| Static Setpoint (current value) | **24.0°C** (changed from 75.0°C) | f4s-static-setpoint-menu.png | Stored in register 300 as raw value 240; intentional change for bench-test (room-temperature baseline) |
| Comms Port | **COM1 / COM2** | (F4S base unit supports both) | CODESYS `Modbus_COM` mapped to available Pi USB port |

**Modbus register map (confirmed):**

| Register | Function | CODESYS Channel | Purpose |
|---|---|---|---|
| 100 (decimal) | Input 1 Value | Read cyclic (FC03) | Display actual F4S chamber temperature on HMI |
| 300 (decimal) | Set Point 1 | Write edge-triggered (FC06) | Remote setpoint control from HMI → F4S |

### CODESYS Project Structure — Modbus Device Tree Confirmed

**Device tree layout (from codesys-project-tree-modbus-com-added.png):**

```
Application
├── Library Manager
├── PLC_PRG (Device: CODESYS Control for Linux ARM64 SL)
│   └── Application
│       ├── Library Manager
│       ├── PLC_PRG (PRG)
│       ├── Task Configuration
│       │   ├── EtherCAT_Task (DEC-Task)
│       │   └── MainTask (DEC-Task)
│       └── PLC_PRG
├── EtherCAT_Master (EtherCAT Master)
│   └── EK1100 (EtherCAT Coupler)
│       ├── ELM3148_0000 (8-ch 24-bit analog input)
│       ├── ELM3148_0001 (8-ch 24-bit analog input)
│       ├── EL3314 (4-ch thermocouple input)
│       ├── EL1409 (16-ch digital input)
│       └── EL2869 (16-ch digital output)
│
└── **Modbus_COM (Modbus COM) ← NEW**
    ├── Modbus_Client_COM_Port (Modbus Client COM port)
    │   └── [FC03 Read channel for register 100]
    │   └── [FC06 Write channel for register 300]
    └── Modbus_server_COM_Port (Modbus server, COM port)
```

**Key CODESYS device parameters (Modbus_COM):**
- **Port:** `/dev/ttyUSB0` (USB-to-RS232 adapter on Raspberry Pi 5)
- **Baud Rate:** 19200 (matches F4S setting — changed from an earlier 9600 reading)
- **Parity:** None
- **Data Bits:** 8
- **Stop Bits:** 1
- **Transmission Mode:** RTU (raw binary, not ASCII)
- **Bus Cycle Task:** Parent bus cycle (synchronized with MainTask)
- **Channel addressing:** 0-based (PDU) — confirmed via on-hardware testing. Set the channel **Offset** field to the register number directly (`100`, `300`), not `99`/`299` — see `codesys-integration/README.md` for the full explanation

---

**The "Chamber Temperature" tile on the CODESYS HMI serves a dual role:**

1. **Read-back display** (register 100, FC03 read, cyclic poll):
   - Shows the actual measured temperature from the Watlow F4S controller
   - Updates continuously (typically every 1 second) to reflect real-time chamber state
   - Acts as the feedback confirmation for the operator

2. **Setpoint control input** (register 300, FC06 write, edge-triggered):
   - The same tile allows the operator to input or adjust the desired chamber setpoint
   - On rising edge of the input (e.g., operator presses "Set" or slides a control), writes the new value to F4S register 300
   - Triggers the remote F4S to begin ramping toward the new setpoint
   - **Write is edge-triggered only (not cyclic)** to prevent EEPROM wear from repeated writes at the same value

**Why this design matters:**
- The Left Hand Small Temperature Cabinet's closed-loop control **remains entirely with the F4S**. CODESYS does not replace or bypass the F4S's own PID controller.
- CODESYS acts as a **supervisory interface** only—it reads the F4S's measured temperature and writes new setpoints as requested by the operator.
- The feedback loop is visual and real-time: operator sets a new setpoint, sees the "Chamber Temperature" tile gradually change as the F4S's control loop brings the actual temperature toward that setpoint.

**Modbus channels mapped to HMI:**

| HMI Tile | Modbus Function | Register | Trigger/Poll | Purpose |
|---|---|---|---|---|
| Chamber Temperature (read-back) | FC03 (Read Holding Registers) | 100 (Input 1 Value) | Cyclic (e.g. 1 sec) | Display actual F4S chamber temperature |
| Chamber Temperature (setpoint input) | FC06 (Write Single Register) | 300 (Set Point 1) | Rising edge only | Write operator-selected setpoint to F4S; F4S begins ramping |

**Example operation:**
1. Operator launches HMI; "Chamber Temperature" tile shows 25.3°C (current F4S reading)
2. Operator inputs new setpoint: 130.0°C
3. Rising edge trigger fires; FC06 write sends register 300 = 1300 to F4S
4. F4S receives the write, acknowledges, begins ramping from 25.3°C toward 130.0°C
5. Over the next minutes, the "Chamber Temperature" tile updates with the F4S's progress: 30.2°C → 50.1°C → 80.5°C → 130.0°C
6. Once F4S reaches 130.0°C and stabilizes, the tile remains at that value until the next setpoint change

---

Investigated whether the Raspberry Pi + EK1100 + EL1409 + EL2869 + EL3314 + ELM3148 combination can communicate with the Watlow F4S over Modbus or any other protocol, by checking each device's official Beckhoff documentation directly (not inference):

| Module | Function | Comms capability |
|---|---|---|
| EK1100 | EtherCAT Bus Coupler | Passive — bridges EtherCAT (upstream) to E-bus (downstream) only. No serial ports. Beckhoff's own coupler family comparison table lists a *different* product, the **EK9000**, as the one with native Modbus TCP/UDP gateway capability — the EK1100 itself has none. |
| EL1409 | 16-ch digital input | E-bus powered digital input only |
| EL2869 | 16-ch digital output | E-bus powered digital output only |
| EL3314 | 4-ch thermocouple input | E-bus powered analog input only |
| ELM3148 | 8-ch 24-bit analog input | E-bus powered analog input only |

None of these five modules has an RS-232, RS-485, or any serial interface — they only ever talk E-bus (Beckhoff's internal 5 V terminal bus) to the coupler, which only ever talks EtherCAT upstream. There is no path through this hardware set for Modbus RTU (or any other protocol) to reach an external RS-485/RS-232 device like the F4S.

**This confirms scope point 4 (additional hardware) is required — it is not optional.**

Note: even Beckhoff's own EK9000 (Modbus TCP/UDP-capable coupler) wouldn't fully solve this on its own — it speaks Modbus **TCP**, while the F4S only exposes Modbus **RTU** over EIA-232/485 (no Ethernet option on this model). It would still need a TCP↔RTU gateway downstream, which is more hardware and cost than the option below for no functional benefit.

---

## Progress Checkpoint: Rebuild Phase Complete → Retest Phase Executing

> 📜 **This section (through "Raspberry Pi bench-test procedure" below) is the historical
> debugging log** — it records the actual troubleshooting journey (Windows COM-port dead end →
> parity mismatch → TX/RX wiring swap → confirmed working link) and is kept for traceability.
> **For the current, confirmed, step-by-step procedure to follow, use:**
> - [`linux-integration/README.md`](linux-integration/README.md) — Raspberry Pi/Linux OS layer (device ID, permissions, `mbpoll` bench test)
> - [`codesys-integration/README.md`](codesys-integration/README.md) — CODESYS runtime + device tree configuration
> - [`remote-ssh-vscode/README.md`](remote-ssh-vscode/README.md) — VS Code Remote-SSH + GitHub workflow
>
> or the consolidated "[Linux ↔ Raspberry Pi ↔ CODESYS ↔ GitHub](#linux--raspberry-pi--codesys--github--remote-ssh-integration)" section further down this same README. Two confirmed facts from this debugging history that the canonical procedure already incorporates: (1) the F4S needed **both** a parity-flag fix (`-P none`) **and** a physical **TX/RX wiring swap** at the terminal block — fixing one without the other still timed out; (2) Modbus register addressing on this link is **0-based (PDU)** — `mbpoll` needs `-0`, and CODESYS channel offsets are set to the register number directly (`100`, `300`), not `99`/`299`.

**Date/Time:** Phase transition to Retest (bench-test execution)  
**Status:** Ready to prove hardware serial link works independently of CODESYS

### Rebuild Phase — Summary of Actions Completed ✅

| Item | Action | Verification | Status |
|---|---|---|---|
| F4S Baud Rate | Changed 9600 → 19200 via front-panel menu | F4S Setup → Communications shows 19200 | ✅ Done |
| CODESYS Modbus_COM | Configured to 19200 baud | Modbus_COM device shows 19200 in config | ✅ Done |
| USB-to-RS232 Adapter | Plugged into Raspberry Pi USB port | `which mbpoll` shows `/usr/bin/mbpoll` | ✅ Done |
| mbpoll Installation | Installed on Raspberry Pi | Terminal confirms executable exists | ✅ Done |
| CODESYS Runtime | Started in run mode | PLC shows running (red triangles expected until hardware proven) | ✅ Done |

### Retest Phase — Executing Now 🔄

**Objective:** Prove the serial hardware layer works independently, before blaming CODESYS configuration

**Terminal Session (as of execution):**
```bash
mechatronics@LeftHandSmallTempCab:~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI $ which mbpoll
/usr/bin/mbpoll

mechatronics@LeftHandSmallTempCab:~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI $ mbpoll --version
mbpoll: invalid option -- '-'
mbpoll: Unrecognized option or missing option parameter ! Try -h for help.
```

**Analysis:**
- `which mbpoll` → `/usr/bin/mbpoll` ✅ (mbpoll is installed and executable)
- `mbpoll --version` → Option error (this version doesn't support `--version`, but that's okay — it's not required for the bench-test)
- **Conclusion:** mbpoll is ready; proceed to bench-test command

**Next Command to Execute (Retest) — FIRST ATTEMPT (FAILED):**
```bash
# Initial bench-test command (with default parity):
mbpoll -m rtu -a 1 -b 19200 -t 4 -r 100 -c 1 -1 /dev/ttyUSB0

# Result: TIMEOUT
# Error: "Read output (holding) register failed: Connection timed out"
# Reason: Parity mismatch (explained below)
```

---

### **Diagnostic Finding — PARITY MISMATCH IDENTIFIED** 🔍

**Root Cause of the Timeout (Step-by-Step Reasoning):**

During diagnostic inspection of the F4S front-panel settings, a **parity configuration mismatch** was discovered that caused frame corruption on the receiving end.

---

#### **What is Parity? (Foundational Reasoning)**

Parity is a single-bit **error detection mechanism** added to serial data transmission. When sender and receiver parity settings mismatch, the UART frame boundaries shift by 1 bit, corrupting all subsequent bytes in the frame.

**Three parity types exist:**

| Parity Type | Symbol | Meaning | Calculation | Use Case |
|---|---|---|---|---|
| **No Parity** | N | No parity bit added or checked | — | Short distances, low noise (YOUR F4S ✓) |
| **Even Parity** | E | Total 1-bits in byte (including parity) = EVEN | Add parity bit to make count even | Medium noise environments |
| **Odd Parity** | O | Total 1-bits in byte (including parity) = ODD | Add parity bit to make count odd | Medium noise environments |

---

#### **Concrete Example 1: No Parity (8N1) — Your F4S Current Setting**

**Scenario:** Transmitting byte 0x01 with NO parity

```
Data byte: 0x01 = 0000 0001 (binary)
           ↑↑↑↑ ↑↑↑↑
           Count 1's: 1 one (odd count)

Transmission format (8N1):
├─ Data bits: 8
├─ Parity bit: NONE
├─ Stop bits: 1
└─ Total: 8 bits

Transmitted: [0000 0001]
             ↑ Just the 8 data bits, nothing else

Receiver (expecting 8N1):
├─ Reads: [0000 0001]
├─ Validates: No parity to check (8N1 mode)
└─ Result: Data accepted ✓
```

**Command flag:** `mbpoll ... -p N ...`

---

#### **Concrete Example 2: Even Parity (8E1) — What Caused Your Timeout**

**Scenario:** Transmitting byte 0x01 with EVEN parity

```
Data byte: 0x01 = 0000 0001 (binary)
Count 1's: 1 one (odd)

Parity calculation (EVEN mode):
├─ Current count: 1 one (odd)
├─ Goal: Make total count EVEN
├─ Decision: Add parity bit 1 (to make 2 ones total = even)
└─ Parity bit: 1

Transmission format (8E1):
├─ Parity bit: 1 (position 8)
├─ Data bits: 0000 0001
├─ Stop bits: 1
└─ Total: 9 bits (1 parity + 8 data)

Transmitted: [1][0000 0001]
             ↑ parity bit
             
Verification: Total 1-bits = 1 (parity) + 1 (data) = 2 ones = EVEN ✓

Receiver (if expecting 8E1):
├─ Reads: [1][0000 0001] (9 bits)
├─ Counts 1's: 1 + 1 = 2
├─ Checks: Is count even? YES ✓
└─ Result: Data accepted ✓

Receiver (if expecting 8N1 — YOUR PROBLEM):
├─ Expects: 8 bits per byte, no parity
├─ Receives: 9 bits ([1][0000 0001])
├─ Reads first 8 bits: [1000 0000]
│  ↑ Got parity bit as data bit!
│  ↑ Interprets as 0x80 (not 0x01) ← WRONG
│
├─ Frame boundary is shifted by 1 bit
├─ All subsequent bytes are bit-shifted and corrupted
│  └─ Byte 2 corrupted, Byte 3 corrupted... entire frame ruined
├─ F4S calculates CRC checksum on corrupted frame
├─ CRC validation fails
├─ F4S discards frame: "This is junk, ignore it"
├─ F4S does NOT respond
└─ mbpoll waits 1.0 second → TIMEOUT
```

**Command flag:** `mbpoll ... -p E ...` (would cause timeout on 8N1 receiver)

---

#### **Concrete Example 3: Odd Parity (8O1) — What Would Cause Same Timeout**

**Scenario:** Transmitting byte 0x01 with ODD parity

```
Data byte: 0x01 = 0000 0001 (binary)
Count 1's: 1 one (odd)

Parity calculation (ODD mode):
├─ Current count: 1 one (odd)
├─ Goal: Make total count ODD
├─ Decision: Add parity bit 0 (total stays 1 one = odd)
└─ Parity bit: 0

Transmission format (8O1):
├─ Parity bit: 0 (position 8)
├─ Data bits: 0000 0001
├─ Stop bits: 1
└─ Total: 9 bits (1 parity + 8 data)

Transmitted: [0][0000 0001]
             ↑ parity bit
             
Verification: Total 1-bits = 0 (parity) + 1 (data) = 1 one = ODD ✓

Receiver (if expecting 8O1):
├─ Reads: [0][0000 0001] (9 bits)
├─ Counts 1's: 0 + 1 = 1
├─ Checks: Is count odd? YES ✓
└─ Result: Data accepted ✓

Receiver (if expecting 8N1 — WOULD FAIL IDENTICALLY):
├─ Expects: 8 bits per byte, no parity
├─ Receives: 9 bits ([0][0000 0001])
├─ Reads first 8 bits: [0000 0000]
│  ↑ Got parity bit (0) as data bit!
│  ↑ Interprets as 0x00 (not 0x01) ← WRONG
│
├─ Frame boundary shifted by 1 bit
├─ All subsequent bytes corrupted (same as Even parity case)
├─ F4S calculates CRC checksum on corrupted data
├─ CRC validation fails
├─ F4S discards frame
├─ F4S does NOT respond
└─ mbpoll waits 1.0 second → TIMEOUT
```

**Command flag:** `mbpoll ... -p O ...` (would cause timeout on 8N1 receiver)

---

#### **Comparative Analysis: Your Parity Mismatch**

| Configuration Aspect | mbpoll (Initial) | F4S Controller | Match? | Timeout Cause |
|---|---|---|---|---|
| Baud Rate | 19200 | 19200 | ✅ Yes | No |
| Data Bits | 8 | 8 | ✅ Yes | No |
| **Parity** | **Even (8E1)** | **None (8N1)** | ❌ **NO** | **Frame shift → CRC failure → No response** |
| Stop Bits | 1 | 1 | ✅ Yes | No |

**Why the timeout occurred (frame-level reasoning):**

```
Frame sent by mbpoll (with even parity):
Byte 1: [P=1][0000 0001] = 9 bits total
Byte 2: [P=0][0000 0011] = 9 bits total
CRC:    [XXXXXXXX]       = 8 bits
...

Frame received by F4S (expecting 8N1, frame shifted):
Byte 1: reads [10000000] (parity + 7 data bits)
Byte 2: reads [10000001] (last data bit + parity + 6 data bits)
CRC:    reads [XXXXXXXX] (corrupted due to previous shift)
...

Result: All bytes after first are corrupted
F4S validates CRC → Checksum fails
F4S: "Invalid frame, discarding"
F4S does NOT respond
mbpoll times out after 1.0 second
```

---

#### **Solution: Match Parity Settings**

**CRITICAL DISCOVERY: Flag Confusion in mbpoll (-p vs -P for RTU Parity)**

After reviewing `mbpoll -h` output, a **critical flag error** was identified that explains all prior timeout failures.

**Root Cause (Step-by-Step Reasoning):**

```
From mbpoll help output:

Options for ModBus / TCP : 
  -p #          TCP port number (502 is default)
                ↑ This -p is for TCP PORT, NOT parity!

Options for ModBus RTU : 
  -b #          Baudrate (1200-921600, 19200 is default)
  -d #          Databits (7 or 8, 8 for RTU)
  -s #          Stopbits (1 or 2, 1 is default)
  -P #          Parity (none, even, odd, even is default)
                ↑ This -P (UPPERCASE) is for PARITY!
```

**The Problem (What Was Happening):**

| Previous Attempts | Command | Result | Why |
|---|---|---|---|
| Test 1 | `-p O` (Odd) | Shows 8E1, timeout | Flag `-p` ignored (for TCP), defaults to even |
| Test 2 | `-p N` (None) | Shows 8E1, timeout | Flag `-p` ignored (for TCP), defaults to even |
| Test 3 | `-p n` (lowercase) | Shows 8E1, timeout | Flag `-p` ignored (for TCP), defaults to even |

**Step-by-Step Execution Flow (Why -p Didn't Work):**

```
Your command: mbpoll -m rtu -a 1 -b 19200 -p N ...
                                          ↑ Wrong flag for RTU mode

mbpoll internal processing:
├─ Detects: RTU mode (-m rtu)
├─ Scans for: RTU-specific flags (-b, -d, -s, -P)
├─ Finds: -p flag
├─ Checks: "Is -p valid in RTU? NO (only for TCP port)"
├─ Action: Ignores -p flag completely
├─ Result: No parity flag provided to RTU handler
├─ Default: "Parity (... even is default)" per help text
├─ Sends: 8E1 (even parity) to F4S
├─ F4S receives: Frame with even parity (9-bit frames)
├─ F4S expects: No parity (8-bit frames)
└─ Result: Frame shift → CRC failure → Timeout ❌
```

**The Correct Command (NOW FIXED):**

```bash
# Use -P (UPPERCASE) for RTU parity, not -p (lowercase)
# Use spelled-out values: none, even, odd (not N, E, O)

mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
                             ↑ CORRECT: Uppercase P for RTU parity
                                ↑ CORRECT: Spelled-out "none" (not "N")

# Complete flag breakdown:
# -m rtu        = ModBus RTU protocol
# -a 1          = Slave address 1
# -b 19200      = Baud rate 19200
# -P none       = Parity NONE (produces 8N1) ← THE CRITICAL FIX
# -t 4          = Read holding registers (function code 03)
# -r 100        = Register 100 (Input 1 Value — actual temperature)
# -c 1          = Count 1 register
# -1            = Poll once and exit
# /dev/ttyUSB0  = Serial port
```

**Alternative Parity Values (Reference):**

```bash
# If F4S were set to 8N1 (NO parity) — YOUR CURRENT SETTING ✓
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 /dev/ttyUSB0

# If F4S were set to 8E1 (EVEN parity) — for comparison
mbpoll -m rtu -a 1 -b 19200 -P even -t 4 -r 100 -c 1 -1 /dev/ttyUSB0

# If F4S were set to 8O1 (ODD parity) — for comparison
mbpoll -m rtu -a 1 -b 19200 -P odd -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
```

**Expected Output (Success with -P none):**

```
mbpoll 1.0-0 - ModBus(R) Master Simulator
...
Protocol configuration: ModBus RTU
Slave configuration...: address = [1]
                        start reference = 100, count = 1
Communication.........: /dev/ttyUSB0, 19200-8N1
                                              ↑ NOW shows 8N1 (matches F4S!)
...
Data type.............: 16-bit register, output (holding) register table
-- Polling slave 1...
[100]: 238
      ↑ SUCCESS! Hardware link PROVEN ✅
```

**Why This Explains Everything (Root Cause Chain):**

```
The entire timeout problem stemmed from using -p instead of -P:

1. You used: -p N (thinking it sets parity to None)
2. mbpoll saw: -p in RTU mode (invalid for RTU)
3. mbpoll did: Ignored -p flag
4. mbpoll defaulted: even parity (8E1)
5. F4S is set to: no parity (8N1)
6. Result: Parity mismatch → frame shift → CRC failure → timeout
7. Your conclusion: "Must be wiring or baud rate issue"
8. Reality: Tool flag was wrong, not the hardware

This is NOT a hardware problem. This is entirely a tool usage problem.
The hardware (wiring, baud, address) was ALWAYS correct.
```

**Critical Insight (Rebuild → Retest Discipline):**

> The parity flag fix (`-P none`) was necessary but **not sufficient**. It corrected one real bug (wrong flag), but the timeout persisted after fixing it — which was the signal that a second, independent problem existed underneath.

---

### **ACTUAL ROOT CAUSE FOUND: TX/RX Wiring Swap at the F4S Terminal Block**

**The real problem (discovered by physically re-checking the terminal block):**

```
ADR-001 documented wiring (intended):
  white wire → F4S terminal 14 (Tx)
  red wire   → F4S terminal 15 (Rx)
  black wire → F4S terminal 16 (GND)

What was ACTUALLY wired (the bug):
  red wire   → F4S terminal 14   ❌ (should be white)
  white wire → F4S terminal 15   ❌ (should be red)
  black wire → F4S terminal 16   ✓
```

**Why this explains every earlier symptom in one shot:**

- Windows/QModMaster timeouts (4 combinations, all failed identically) — the "TX/RX swap" tried on the DB9 end never touched the actual swap that existed at the F4S terminal end
- Every mbpoll parity test (8E1, 8O1, 8N1) — all doomed regardless of flags, because the signal was never reaching the correct pins in the first place
- **The parity investigation was a real bug, but not THE bug.** Two independent problems existed simultaneously: wrong mbpoll flag (`-p` vs `-P`) AND wrong physical wiring.

**Second finding — PDU addressing (0-based) confirmed via the `-0` flag:**

```
mbpoll -r 100  (without -0)  → queries PDU address 99  (1-based assumption)
mbpoll -r 100  (with -0)     → queries PDU address 100 (0-based, correct)
```

This is the "±1 register offset trap" flagged earlier in this project's notes — now empirically confirmed on real hardware. **The same principle applies inside CODESYS**: the channel "Offset" field is also 0-based, so it must be set to `100` directly (not 99, not 101) when configuring the read channel.

---

### **✅ BENCH-TEST SUCCESS — Hardware Link Proven**

**Corrected command (both fixes applied):**
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
                             ↑ -P none: correct parity flag
                                                          ↑ -0: 0-based PDU addressing
```

**Result:**
```
[100]: 232
```
**232 = 23.2°C — matches the F4S front-panel display exactly.**

**This proves, definitively:**
- ✅ Wiring is now correct (TX/RX un-swapped at the terminal block)
- ✅ Baud rate 19200 matches on both sides
- ✅ Parity None (8N1) matches on both sides
- ✅ Slave address 1 confirmed
- ✅ Register addressing (0-based/PDU) confirmed
- ✅ **Raspberry Pi ↔ F4S serial link is fully proven, independent of CODESYS**

**Open item — worth a follow-up check, not blocking:** the same read reportedly also succeeded at `-b 9600` (F4S front panel is set to 19200). A baud mismatch should normally fail outright rather than partially work, so this is unusual and worth re-verifying later (confirm the F4S menu still shows 19200 and wasn't left mid-edit). Not a blocker — 19200 remains the standing, confirmed baud rate across F4S and CODESYS.

**If F4S were configured differently, use these flags:**

| F4S Parity Setting | mbpoll Flag | Command Example |
|---|---|---|
| No Parity (8N1) — **CURRENT** | `-p N` | `mbpoll ... -p N ... /dev/ttyUSB0` ✅ |
| Even Parity (8E1) | `-p E` | `mbpoll ... -p E ... /dev/ttyUSB0` |
| Odd Parity (8O1) | `-p O` | `mbpoll ... -p O ... /dev/ttyUSB0` |

**Expected Output (if hardware link works):**
```
mbpoll 1.0-0 - ModBus(R) Master Simulator
...
Protocol configuration: ModBus RTU
Slave configuration...: address = [1]
                        start reference = 100, count = 1
Communication.........: /dev/ttyUSB0, 19200-8N1
                                              ↑ Notice: 8N1 (matches F4S)
Data type.............: 16-bit register, output (holding) register table
-- Polling slave 1...
[100]: 238
```

If you see `[100]: <value>` → **Hardware link is proven! ✅ Proceed to Requalify Phase.**

---

#### **Reference: Complete Parity Configuration Guide**

**Quick Command Reference (Rebuild → Retest → Requalify → Repeat):**

```bash
# SCENARIO 1: F4S set to 8N1 (No Parity) — YOUR CURRENT SETUP ✅
mbpoll -m rtu -a 1 -b 19200 -p N -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
                             ↑ -p N for NO parity

# SCENARIO 2: F4S set to 8E1 (Even Parity) — if you change it
mbpoll -m rtu -a 1 -b 19200 -p E -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
                             ↑ -p E for EVEN parity

# SCENARIO 3: F4S set to 8O1 (Odd Parity) — if you change it
mbpoll -m rtu -a 1 -b 19200 -p O -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
                             ↑ -p O for ODD parity
```

**Debugging Flowchart (If you get a timeout):**

```
Question: Did mbpoll timeout?
├─ If YES:
│  └─ Action 1: Check F4S parity setting
│     ├─ Front panel: Setup → Communications → Parity
│     ├─ Note the current setting (None, Even, or Odd)
│     ├─ Match that setting with mbpoll flag:
│     │  ├─ None → use -p N
│     │  ├─ Even → use -p E
│     │  └─ Odd → use -p O
│     └─ Re-run mbpoll with correct flag
│
└─ If SUCCESS ([100]: value):
   └─ Parity was correct, move to Requalify phase
```

**Parity Selection Guide (When to use which):**

| Scenario | F4S Setting | Why? | Robustness | mbpoll Flag |
|---|---|---|---|---|
| **Short distance (<10m), clean environment** | 8N1 (None) | Simplest, least overhead | Low | `-p N` |
| **Medium distance, some electrical noise** | 8E1 (Even) | Error detection enabled | Medium | `-p E` |
| **Medium distance, some electrical noise** | 8O1 (Odd) | Error detection enabled | Medium | `-p O` |
| **Long distance, high EMI** | 8E1 or 8O1 | Need error detection | Medium+ | `-p E` or `-p O` |
| **Your installation** | 8N1 (None) | Your F4S is set to this ✅ | Low (acceptable) | `-p N` |

---

#### **CRITICAL: CODESYS Parity Configuration (Requalify Phase)**

**Why this matters:**

When you move to the Requalify phase (mapping `/dev/ttyUSB0` into CODESYS), the CODESYS `Modbus_COM` device configuration MUST also match the F4S parity setting. If the parity mismatches here too, you'll see red triangles in CODESYS even though the hardware bench-test succeeds.

**Current state (Rebuild → Retest phases complete):**

```
F4S:         Parity = None (8N1) ✓
mbpoll test: Parity = None (8N1) ✓
CODESYS:     Parity = ??? (MUST verify in Requalify phase)
```

**CODESYS Configuration Location:**

Navigate to your CODESYS project:
```
Device tree:
├─ [Your runtime device]
│  ├─ PLC_PRG (program)
│  │
│  └─ Communication Devices
│     └─ Modbus_COM (the device you configured earlier)
│        └─ Properties (right-click → Edit/Properties)
│           ├─ Serial Port settings tab
│           ├─ Baud Rate: 19200 (verify)
│           ├─ Data Bits: 8 (verify)
│           ├─ Parity: ??? (CHECK AND FIX)
│           └─ Stop Bits: 1 (verify)
```

**How to Set Parity in CODESYS:**

```
Step 1: Right-click on "Modbus_COM" device in the device tree
Step 2: Select "Properties" (or "Edit" depending on your CODESYS version)
Step 3: Navigate to the "Serial Port" or "Communication" tab
Step 4: Locate the "Parity" dropdown menu
Step 5: Select the option that matches your F4S:
        
        If F4S is 8N1 (your current setting):
        └─ Select: "None" or "Off" or "No Parity"
        
        If F4S is 8E1:
        └─ Select: "Even"
        
        If F4S is 8O1:
        └─ Select: "Odd"

Step 6: Click OK to save
Step 7: Recompile the project (Build → All)
Step 8: Download to the Raspberry Pi
Step 9: Restart the CODESYS runtime
```

**CODESYS Parity Dropdown Values (by version):**

| CODESYS 3.5 | CODESYS 3.6+ | Meaning |
|---|---|---|
| "None" | "None" | No parity (8N1) — YOUR SETTING ✅ |
| "Even" | "Even" | Even parity (8E1) |
| "Odd" | "Odd" | Odd parity (8O1) |

**Troubleshooting: Red Triangles After Requalify**

If you've completed the Requalify phase (mapped `/dev/ttyUSB0`, restarted runtime) but still see red triangles on the Modbus_Client_COM_Port and Modbus_server_COM_Port devices, the most likely cause is a parity mismatch in CODESYS:

```
Diagnostic reasoning:
├─ Bench-test with mbpoll -p N succeeded?
│  └─ YES → Hardware link is proven correct ✓
│
├─ CODESYS red triangles persist?
│  └─ Root cause: CODESYS Modbus_COM parity setting doesn't match
│
├─ How to fix:
│  ├─ Step 1: Check F4S parity (front panel: Setup → Communications → Parity)
│  ├─ Step 2: Open CODESYS Modbus_COM device properties
│  ├─ Step 3: Set CODESYS parity to match F4S
│  │  └─ F4S 8N1 → CODESYS "None"
│  │  └─ F4S 8E1 → CODESYS "Even"
│  │  └─ F4S 8O1 → CODESYS "Odd"
│  ├─ Step 4: Recompile and download
│  ├─ Step 5: Restart runtime
│  └─ Result: Red triangles turn green ✓
│
└─ If STILL failing after parity fix:
   └─ Escalate to address, baud rate, or /etc/CODESYSControl_User.cfg verification
```

**Key principle (Rebuild → Retest → Requalify → Repeat):**

> **Hardware parity setting (F4S) must match software parity on EVERY layer:**
> 1. F4S controller: 8N1 ✓
> 2. mbpoll bench-test: -p N ✓
> 3. CODESYS Modbus_COM: "None" (TO BE SET)
>
> If any one mismatches, communication fails and you'll see timeouts or red triangles.

---

**Result: failed on every combination tried.**

| Attempt | Baud | Wiring | Result |
|---|---|---|---|
| 1 | 9600 | As-wired | `Read Data Failed [Timeout]` on Bus Monitor / QModMaster main page |
| 2 | 19200 | As-wired | Same timeout |
| 3 | 9600 | TX/RX swapped | Same timeout |
| 4 | 19200 | TX/RX swapped | Same timeout |

**Why this pattern is informative rather than just "it doesn't work":** two variables were changed (baud, wiring direction) across four attempts, and all four failed identically. If baud were the actual problem, the *wrong* rate should produce garbled or partial responses, not a clean timeout — and a *correct* rate among the two tried should have worked. If wiring direction were the problem, swapping TX/RX should have fixed it in at least one of the four attempts. Getting the **same failure regardless of the two variables actually changed** points at a variable that *wasn't* changed — most likely:

- **Windows assigned the adapter to a COM port other than COM1**, and QModMaster kept polling a port with nothing listening on it. USB-serial adapters do not reliably enumerate as COM1 — Windows increments based on driver/enumeration history (COM3, COM4, COM7, etc.), silently, with no warning that the configured port doesn't match the physical device.
- Secondary possibility: a generic Windows serial driver bound to the adapter instead of its correct FTDI/CH340/Prolific-specific driver.

**Decision: move the bench test to the Raspberry Pi (Linux) instead of continuing to troubleshoot Windows.** This isn't just a platform swap — it replaces port-number *guessing* with port-number *verification* (`dmesg` shows definitively which `/dev/ttyUSBx` the kernel assigned to the physical adapter) and replaces a GUI's hidden dropdown settings with an explicit, fully-visible command line (`mbpoll`).

### Raspberry Pi bench-test procedure — confirmed final command

> An earlier version of this section showed a bench-test command missing both fixes discovered
> during troubleshooting (`-P none` for parity, `-0` for 0-based/PDU register addressing) and a
> large duplicated block of wiring/config notes already covered elsewhere in this README. Both
> have been condensed here; the full step-by-step walkthrough (permissions, `dmesg`, `mbpoll`
> install, troubleshooting table) now lives in `linux-integration/README.md` so it isn't
> maintained in two places.

**Confirmed working command** (both fixes applied — parity **and** 0-based addressing):

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
```

**Confirmed result:** `[100]: 232` → 23.2°C, matching the F4S front-panel display exactly. This
proves the wiring (post TX/RX-swap correction), baud (19200), parity (None/8N1), slave address
(1), and register addressing (0-based/PDU) are all correct — the Raspberry Pi ↔ F4S serial link
is fully proven, independent of CODESYS.

**Mapping into CODESYS from here:** see `codesys-integration/README.md` — including the same
0-based addressing rule applied to the CODESYS channel **Offset** field (set to `100`/`300`
directly, not `99`/`299`).

---

## Linux ↔ Raspberry Pi ↔ CODESYS ↔ GitHub — Remote SSH Integration

This is the **canonical, current, confirmed procedure** — the numbered order below is the path
every engineer coming to this project should follow, from a bare SSH login all the way to a
running CODESYS project reading/writing the F4S. The detailed step-by-step instructions, helper
scripts, and troubleshooting for each phase live in **three separate, self-contained folders**
so each concern (Linux/hardware, CODESYS, remote tooling) is documented independently and stays
easy to find:

| Folder | Covers | Steps below |
|---|---|---|
| [`remote-ssh-vscode/`](remote-ssh-vscode/README.md) | VS Code Remote-SSH connection + Git/GitHub workflow from the Pi | 1, 6 |
| [`linux-integration/`](linux-integration/README.md) | Raspberry Pi OS layer — device identification, serial port permissions, `mbpoll` bench test | 2, 3, 4 |
| [`codesys-integration/`](codesys-integration/README.md) | CODESYS runtime config, Modbus device tree, channel addressing, build/deploy | 5 |

**Do not skip ahead** — each step assumes the previous one is proven. Bench-test the raw serial
link with `mbpoll` (Linux layer) *before* touching CODESYS; don't debug CODESYS Modbus errors
until `mbpoll` reads cleanly on its own.

### Why this is different from Windows

| Windows habit | Linux equivalent |
|---|---|
| `COM3`, `COM4`, … | `/dev/ttyUSB0`, `/dev/ttyACM0`, … — a device *file*, not a port name |
| Ports "just work" for any user | Serial devices are permission-gated (`crw-rw----`, group `dialout`) |
| QModMaster / Modbus Poll (GUI) | `mbpoll` (CLI) — same bench-test role, no GUI needed |
| Editing files locally, then FTP/copy to the PLC | VS Code **Remote-SSH** edits the Pi's filesystem directly; Git push/pull happens from the same remote window |
| CODESYS Windows runtime config (GUI dialog) | `/etc/CODESYSControl_User.cfg` (plain text) |

### The six-step sequence

1. **Connect** — VS Code Remote-SSH to `mechatronics@10.1.6.17`, open the repo folder. → `remote-ssh-vscode/README.md`
2. **Identify** — `dmesg | tail -n 20` → confirm the adapter enumerated as `/dev/ttyUSB0` (or wherever it landed after a replug). → `linux-integration/README.md`
3. **Permission** — grant serial port access (temporary `chmod 666`, or permanent `dialout` group membership); confirm with `ls -la`. → `linux-integration/README.md`
4. **Bench-test** — `mbpoll` against the F4S, independent of CODESYS. **Confirmed working command:**
   ```bash
   mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
   ```
   Two fixes are required together — `-P none` (this F4S is 8N1, not `mbpoll`'s default 8E1) **and** `-0` (0-based/PDU register addressing, confirmed on hardware) — plus the physical TX/RX wiring at the F4S terminal block must be correct (not swapped). Full troubleshooting table in `linux-integration/README.md`.
5. **Map & deploy** — `/etc/CODESYSControl_User.cfg` → `Linux.Devicefile.1=/dev/ttyUSB0` → restart `codesyscontrol` → configure the Modbus Serial Master device in the CODESYS IDE on **COM1**, with channel **Offset** set 0-based (`100`, `300` directly). Build → Clean All → Build → Login → Run. → `codesys-integration/README.md`
6. **Version** — commit/push any doc or code changes from the same Remote-SSH VS Code window back to `OJ4884-patch-1`. → `remote-ssh-vscode/README.md`
7. **Requalify** — run the T1–T9 test plan in `docs/DEPLOYMENT_AND_TEST.md` §5 once steps 1–6 are proven end-to-end.

---

### Candidate Modbus register map (F4S, static/manual setpoint mode — not profile mode)

| Register | Function | Access | Status |
|---|---|---|---|
| 100 | Input 1 Value (actual chamber temperature) | Read (FC03/FC04) | Candidate — from Watlow documentation, not yet live-tested |
| 300 | Set Point 1 (static setpoint) | Read/Write (FC06) | **Corroborated on site** — front panel independently labels the same parameter "SP1," currently reading 130.0 °C |
| 4122 | Set Point 1, Current Profile Status (active setpoint *while a profile runs*) | Read only | Not used — profiling out of scope |

One implied decimal place (e.g. 1005 = 100.5). The register *address* itself is still to be confirmed by a live Modbus read once comms are established — the front-panel name match is corroborating evidence, not proof of the register number.

---

## Key design principle: Supervisory setpoint control via Modbus RS-232

The CODESYS HMI does **not** control the Left Hand Small Temperature Cabinet's temperature directly. Instead, it supervises the Watlow F4S controller through a read-back and remote-setpoint-write pattern:

**Read-back (continuous feedback):**
- HMI reads Modbus register 100 (F4S Input 1 Value) via FC03 every 1 second
- Displays as "Chamber Temperature" on the HMI screen
- Confirms to the operator that the cabinet's actual temperature matches the requested setpoint

**Supervisory setpoint write (edge-triggered control):**
- Operator adjusts "Chamber Temperature" setpoint on the HMI (e.g., from 25°C to 130°C)
- Rising edge of the input triggers a one-time Modbus FC06 write to register 300 (F4S Set Point 1)
- F4S receives the new setpoint and begins ramping toward it using its own internal PID controller
- Ramping progress is visible in real time as the "Chamber Temperature" read-back tile updates

**Why edge-triggered, not cyclic:** Modbus register 300 is stored in the F4S's EEPROM. Writing the same value repeatedly causes unnecessary wear. Edge-triggered writes only fire when the setpoint *changes*, preventing this degradation.

**Why this is the right architecture:** The F4S is a purpose-built ramping controller with decades of proven thermal control logic. CODESYS leverages that expertise rather than attempting to replace it. The supervisor-and-agent pattern ensures CODESYS remains the operator interface while the F4S retains authority over actual temperature control.

---

## Scope status

| In-scope item | Status |
|---|---|
| New CODESYS sandbox project | **Done** — created in the repo |
| Integrate DLS008 hardware | **Done** — EtherCAT master + I/O terminals scanned and configured |
| Investigate remote setpoint capability | **Done** — Watlow F4S (SN 038983) confirmed; RS-232 protocol verified (3-wire: white/red/black = TX/RX/GND per nameplate terminals 14/15/16); register 300 = SP1 setpoint |
| Identify additional hardware/wiring/settings | **Done** — USB-to-RS232 adapter in hand; wiring colors verified with RS-232 standard sources (Raveon AN236, Watlow F4S spec); no enclosure modifications needed |
| Basic HMI input | Not started — HMI mockup exists (`mockups/watlow-f4s-setpoint-hmi.html`); awaits CODESYS WebVisu build-out |
| Send setpoint to cabinet | **Retest phase complete ✓** — Raspberry Pi bench-test (`mbpoll`) proven: `[100]: 232` matches F4S front panel, with parity fix, TX/RX wiring fix, and 0-based addressing all applied. Requalify (CODESYS mapping) is next — see `codesys-integration/README.md` |
| Confirm acceptance | Blocked on: CODESYS Requalify (mapping the proven Pi↔F4S link into the runtime and device tree) |
| Validation + fault indication | Blocked on: Requalify + HMI development + T1–T9 test plan execution (`docs/DEPLOYMENT_AND_TEST.md` §5) |
| Documentation | **Done** — README documents the full Rebuild → Retest → Requalify → Repeat cycle through a proven Raspberry Pi bench test; `linux-integration/`, `codesys-integration/`, and `remote-ssh-vscode/` folders document each phase in detail |

---

## Open items before Phase 3 (implementation) — 🔵 TL checkpoint

**Baud-rate synchronization — ⚠️ re-verification required (regression suspected)**

Previously recorded as resolved at 19200, but a later manual `mbpoll -b 9600 ... -r 300` also
returned a clean, correct-looking read (`[300]: 240`, matching the front panel) — a genuine
baud mismatch on RS-232 should produce a timeout or framing error, not a clean match, so getting
one at *two different baud rates* is not something to write off as a fluke. Two explanations are
plausible: (1) the F4S's actual current baud rate has reverted to 9600 (e.g. the earlier
front-panel change to 19200 wasn't saved/persisted through a power cycle), or (2) the 9600 read
was a rare false-positive CRC match on a garbled frame. **Before any further writes**, re-verify
the *actual* current setting directly on the F4S front panel — **Setup → Communications → Baud
Rate** — and treat that as ground truth over this table until it's re-confirmed. Full discussion
in `linux-integration/README.md` §4.1a.

Original resolution record (superseded by the above until re-verified):
- F4S front-panel: **Setup → Communications → Baud Rate = 19200** (changed from 9600, verified on unit)
- CODESYS `Modbus_COM` device: **19200** (already configured)

**Raspberry Pi bench-test (`mbpoll`) — RESOLVED ✓**

Confirmed working, with **both** the parity flag (`-P none`) and 0-based addressing (`-0`)
present, and after correcting a physical TX/RX wiring swap at the F4S terminal block:

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
```

Result: `[100]: 232` (23.2°C), matching the F4S front-panel display. Full details, the two
independent root causes, and the troubleshooting table are in `linux-integration/README.md` §4.

**Remaining priority tasks:**

1. **CODESYS mapping (Requalify phase):** Map the proven `/dev/ttyUSB0` port into the CODESYS
   runtime and device tree, including the confirmed 0-based channel addressing (offset = `100`/
   `300` directly, not `99`/`299`). Full steps in `codesys-integration/README.md`.

2. **Once CODESYS is mapped:** Re-run the CODESYS read/write tests to confirm the link works
   end-to-end inside the application (Repeat phase — T1–T9 test plan in
   `docs/DEPLOYMENT_AND_TEST.md` §5).

3. Power-budget check: the 5 V/5 A (30 W) rail is shared across two Raspberry Pi 5 units. Actual draw under full load for both units running simultaneously is worth measuring, even though typical idle draw is well under the 5 A spec.

4. Confirm F4S is in static/manual setpoint mode (not running an internal profile) before any register-300 write production use.

5. Quick check on the "Hyperbaric Water Temperature" HMI tile — confirm whether it belongs to this cabinet or a different rig.

---

## Repository contents

- Kickoff document — objective, scope, definition of done
- Development plan — phased approach, equipment findings, hardware decision tree
- Equipment datasheets (CP1/DLS008 panel, ELM3148, EK1100, EL1409, EL2869, EL3314, Watlow F4S, power supplies, MCB)
- `docs/photos/` — site inspection photos (controller front/angled/rear views, comms terminal label, serial comms port exterior + interior, thermocouple junction box, thermocouple legend)
- `docs/DEPLOYMENT_AND_TEST.md` — CODESYS import guide, Modbus channel config, WebVisu layout, T1–T9 test plan
- `linux-integration/` — Raspberry Pi/Linux OS layer guide + scripts (device identification, serial permissions, `mbpoll` bench test for register 100 read and register 300 setpoint read/write, temperature-ramp watch)
- `codesys-integration/` — CODESYS runtime + device tree configuration guide (`/etc/CODESYSControl_User.cfg`, Modbus Serial Master setup, 0-based channel addressing, build/deploy)
- `remote-ssh-vscode/` — VS Code Remote-SSH connection guide + Git/GitHub workflow from the Pi
- `mockups/watlow-f4s-setpoint-hmi.html` — self-contained HTML/CSS/JS HMI mockup with embedded Oliver Mechatronics branding
- `src/` — Structured Text POUs, DUTs, GVLs, and PLCopen XML import for `FB_CabinetSetpointControl`
- CODESYS `.project` file — DLS008 sandbox project, EtherCAT hardware configured
- This README — living project status summary; see the "Linux ↔ Raspberry Pi ↔ CODESYS ↔ GitHub" section for the canonical integration sequence and links to the three folders above
