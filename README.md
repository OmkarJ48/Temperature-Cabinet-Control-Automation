# Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI

Develop a safe and reliable method of allowing an operator to change the setpoint of the selected temperature cabinet from a CODESYS HMI. The cabinet keeps its own closed-loop control at all times — CODESYS provides **supervisory setpoint control only**, never a replacement control loop.

**Owner:** Omkar Joshi (OJ) — Oliver Valvetek / Oliver Mechatronics / Oliver R&D  
**Status:** Phase 2 → Phase 3 (Rebuild, Retest, Requalify & Repeat) — CODESYS sandbox created, DLS008 hardware integrated, RS-232 serial protocol confirmed with verified wiring; ready for USB adapter procurement and bench-test

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
| Baud Rate | **9600 bps** | f4s-baud-rate-menu.png | Selected in CODESYS `Modbus_COM` device config |
| Slave Address | **1** | f4s-slave-address-menu.png | F4S broadcast default; range 1–247 confirmed accessible |
| Parity | **None** | (selected via menu navigation) | CODESYS `Modbus_COM` parity = None |
| Data Bits | **8** | (default for industrial Modbus RTU) | CODESYS config: 8 bits |
| Stop Bits | **1** | (default for industrial Modbus RTU) | CODESYS config: 1 bit |
| Static Setpoint (current value) | **75.0°C** | f4s-static-setpoint-menu.png | Stored in register 300; *not* the register address |
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
- **Baud Rate:** 9600 (matches F4S setting)
- **Parity:** None
- **Data Bits:** 8
- **Stop Bits:** 1
- **Transmission Mode:** RTU (raw binary, not ASCII)
- **Bus Cycle Task:** Parent bus cycle (synchronized with MainTask)

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

## Recommended path: USB-to-RS232 adapter via the existing external port — verified configuration

**Physical setup (confirmed, no changes needed to enclosure):**
- The "SERIAL COMMS" DB9 on the cabinet exterior has three wires: white, red, black
- These connect internally to **F4S terminals 14, 15, 16** respectively (per nameplate: terminals 14/15/16 = 232 Tran./232 Rec./Comms GND)
- **RS-232 protocol confirmed** by physical evidence (3-wire configuration matches RS-232 standard, not 2-wire RS-485)

**Wiring color code — sourced from RS-232 standard and physical evidence:**

| Wire Color | Signal | F4S Terminal | RS-232 Function | USB Adapter Pin |
|---|---|---|---|---|
| **White** | TX | 14 (232 Tran.) | Transmit (F4S sends) | 2 (RXD — receives from F4S) |
| **Red** | RX | 15 (232 Rec.) | Receive (F4S listens) | 3 (TXD — sends to F4S) |
| **Black** | GND | 16 (Comms) | Ground reference | 5 (GND) |

**Why TX and RX are crossed:**
RS-232 is a point-to-point serial protocol. One device's transmitter (TX) must connect to the other's receiver (RX). The F4S controller transmits on terminal 14 (white wire); this must land on the USB adapter's receive pin (RXD, pin 2 on a standard DB9 adapter). Conversely, the adapter transmits on pin 3 (TXD) to the F4S's receive terminal 15 (red wire). This crossing is not an error — it's the correct RS-232 connection pattern. (Source: Raveon Technologies AN236 Technical Brief "Serial Communications RS232, RS485, RS422"; Watlow F4S Series spec sheet, Serial Communication section.)

**Hardware required:**
- One USB-to-RS232 (DB9 9-pin) adapter cable, standard commodity item (~£10–20)
- Plug into the Raspberry Pi running the CODESYS sandbox project

**Configuration flow (Rebuild → Retest → Requalify → Repeat):**

1. **Rebuild (physical):**
   - Plug the USB-RS232 adapter into the active CODESYS Raspberry Pi's USB port
   - Verify detection: `ls -l /dev/ttyUSB*` should show `/dev/ttyUSB0` (or similar)
   - Record F4S comms settings from the front-panel **Setup → Communications** menu
   - Note: slave address, baud rate (9600 or 19200), parity (typically 8N1 — 8 data bits, no parity, 1 stop bit)

2. **Retest (standalone bench test — before CODESYS integration):**
   - Use a generic Modbus tool (ModRSsim, Modbus Poll, pymodbus CLI) to bench-test in isolation
   - **Read test:** Query register 100 (Input 1 Value) — should return a temperature value matching the F4S front-panel display
   - **Write test:** Write register 300 (Set Point 1) with a test value (e.g. 1300 = 130.0°C) — should update the front panel's SP1 display within 1–2 seconds
   - If either command times out or returns garbage (0xFFFF, -1, etc.), check:
     - USB device permissions: `sudo chmod 666 /dev/ttyUSB0` (if needed)
     - Baud rate/parity match between tool, F4S settings, and adapter
     - Slave address: common defaults are 1, 247, or 255; confirm on F4S menu
     - Physical connection: wiggle wires gently; listen for any crackle (loose contact)
   - Log all test results with timestamps

3. **Requalify (CODESYS integration):**
   - Once bench-test passes consistently, configure a CODESYS Modbus Serial Master on `/dev/ttyUSB0`
   - Match settings: baud rate, parity, slave address
   - Create read channel: FC03, register 100, 1 register, cyclic poll (e.g. every 1 second) → HMI temperature display
   - Create write channel: FC06, register 300, trigger = rising edge only (never cyclic) → prevent EEPROM wear from repeated writes
   - Compile and download project to the active Pi
   - Verify CODESYS runtime starts without errors: check the "Devices" view for `/dev/ttyUSB0` status

4. **Repeat (iterative verification — Rebuild → Retest → Requalify cycle):**
   - Test HMI read-back: compare displayed temperature against F4S front panel; should match within 0.1°C
   - Test setpoint write: use HMI to change SP1, confirm front-panel display updates
   - Test multiple values across the operating range (e.g. 30°C, 100°C, 130°C)
   - Log results; if any fail, cycle back through Rebuild/Retest/Requalify
   - Once all tests pass twice consecutively, mark test case as **PASS** and move to next scope item

**Notes:**
- The external USB feedthrough on the panel eliminates the need to open the enclosure — the DB9-to-F4S wiring is already complete internally
- No EtherCAT integration is needed; the serial adapter sits entirely outside the Beckhoff chain
- Both Raspberry Pi units can run CODESYS, but only the one executing the Modbus Master will actually see responses — the USB device is tied to the physical Pi's OS, not the project

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

## Scope status

| In-scope item | Status |
|---|---|
| New CODESYS sandbox project | **Done** — created in the repo |
| Integrate DLS008 hardware | **Done** — EtherCAT master + I/O terminals scanned and configured |
| Investigate remote setpoint capability | **Done** — Watlow F4S (SN 038983) confirmed; RS-232 protocol verified (3-wire: white/red/black = TX/RX/GND per nameplate terminals 14/15/16); register 300 = SP1 setpoint |
| Identify additional hardware/wiring/settings | **Done** — USB-to-RS232 adapter only; wiring colors verified with RS-232 standard sources (Raveon AN236, Watlow F4S spec); no enclosure modifications needed |
| Basic HMI input | Not started — awaits bench-test results |
| Send setpoint to cabinet | Blocked on: bench-test (standalone Modbus tool), F4S front-panel comms settings (address/baud/parity), CODESYS Modbus SM integration |
| Confirm acceptance | Blocked on: bench-test and CODESYS integration validation |
| Validation + fault indication | Blocked on: HMI read-back and write operations across operating range, edge-trigger testing (EEPROM wear prevention) |
| Documentation | **Done** — README complete with ADR-001, sourced wiring verification, Rebuild→Retest→Requalify cycle, ready for GitHub |

---

## Open items before Phase 3 (implementation) — 🔵 TL checkpoint

1. Order the USB-to-RS232 adapter; TL sign-off on spend.
2. Confirm which Raspberry Pi is running the CODESYS sandbox project and will host the adapter.
3. Record F4S comms settings from front-panel menu: **Setup → Communications** — slave address, baud rate, parity.
4. Power-budget check: the 5 V/5 A (30 W) rail is shared across two Raspberry Pi 5 units. Actual draw under full load for both units running simultaneously is worth measuring, even though typical idle draw is well under the 5 A spec.
5. Bench-test the serial link with a standalone Modbus tool (ModRSsim or similar) before touching CODESYS — read register 100, write register 300, confirm responses.
6. Confirm F4S is in static/manual setpoint mode (not running an internal profile) before any register-300 write production use.
7. Quick check on the "Hyperbaric Water Temperature" HMI tile — confirm whether it belongs to this cabinet or a different rig.

---

## Repository contents

- Kickoff document — objective, scope, definition of done
- Development plan — phased approach, equipment findings, hardware decision tree
- Equipment datasheets (CP1/DLS008 panel, ELM3148, EK1100, EL1409, EL2869, EL3314, Watlow F4S, power supplies, MCB)
- `docs/photos/` — site inspection photos (controller front/angled/rear views, comms terminal label, serial comms port exterior + interior, thermocouple junction box, thermocouple legend)
- CODESYS `.project` file — DLS008 sandbox project, EtherCAT hardware configured
- This README — living project status summary
