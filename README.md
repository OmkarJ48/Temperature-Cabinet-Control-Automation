# Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI

Develop a safe and reliable method of allowing an operator to change the setpoint of the selected temperature cabinet from a CODESYS HMI. The cabinet keeps its own closed-loop control at all times — CODESYS provides supervisory setpoint control only, never a replacement control loop.

Owner: Omkar Joshi (OJ) — Oliver Valvetek / Oliver Mechatronics / Oliver R&D
Status: Phase 1 — Investigation (hardware audit done; site photos reviewed — protocol confirmation on the comms port still outstanding)


Equipment

ItemIdentityControl panelDLS008Temperature cabinetLeft Hand Small Temperature Cabinet (JTS Ltd / James Technical Services Ltd, Wales)Cabinet controllerWatlow SERIES F4S — single-channel 1/4 DIN ramping controller (confirmed from JTS/Watlow spec sheet; supersedes earlier F4T/Eurotherm hypotheses)CODESYS projectNew sandbox project only (R&D project untouched)

DLS008 hardware audit (confirmed)


2× Raspberry Pi 5
2× Beckhoff ELM3148-0000 — 8-channel, 24-bit analog input terminal
1× Beckhoff EL3314 — 4-channel thermocouple input terminal
1× Beckhoff EK1100 — EtherCAT Bus Coupler (E-bus)
1× Beckhoff EL1409 — 16-channel digital input terminal
1× Beckhoff EL2869 — 16-channel digital output terminal
Siemens SENTRON 5SY4106-8 MCB (D-curve, 6 A, 1-pole) — branch protection
RS PRO DIN-rail PSUs: 24 V DC / 5 A / 120 W (Beckhoff/field rail) and 5 V DC / 5 A / 30 W (Raspberry Pi rail)


All of the above are combined as a single EtherCAT master/I-O node. Which of the two Raspberry Pi 5 units acts as the CODESYS EtherCAT master (and which USB port carries any new serial adapter) is to be confirmed on physical inspection — noted as an open item below.

Physical inspection findings (site photos)

Four site photos reviewed this round — stored in docs/photos/ in this repo.

1. Controller front panel
V:\Mechatronics\Omkar\Temperature Cabinet Setpoint Control\JTS Watlow F4S Din 14 DIN Single Channel Ramping Controller.png
Badge reads WATLOW F4 — consistent with the F4S identity established from the spec sheet.
Front-panel menu shows "SP1" as the setpoint parameter name, currently reading 130.0 °C, alongside DigitalIn/DigitalOut status lines — matching the ordering-code spec (1 analog input, 4 digital inputs, 8 digital outputs) already on file.
Corroborates the register-map hypothesis: Watlow's published Modbus map names register 300 "Set Point 1"; the front panel independently uses the identical short name "SP1" for the same parameter. The register number still needs confirming with a live Modbus read (the display doesn't show register addresses), but the parameter-identity match is a good sign.
JTS calibration sticker: calibrated Sept 2024, due Sept 2025 — in-date.
FGAS compliance leak test: Sept 2024.
A separate hard-wired "OVER TEMPERATURE" lamp exists independent of the controller's own display — worth wiring into a spare EL1409 DI channel for HMI-level fault indication, complementing the planned Modbus comms-loss watchdog.

2. Serial comms connector — the key finding
V:\Mechatronics\Omkar\Temperature Cabinet Setpoint Control\Serial Communication RS232 Female Connector Left Hand Small Cab.png
The cabinet already has a dedicated external 9-pin D-sub (DB9) female connector, clearly labelled "SERIAL COMMS," mounted on a removable plate on the enclosure exterior, below a mains-disconnect warning. This means the F4S's internal comms terminals are already wired out to an accessible external port — there should be no need to open the enclosure or wire directly onto the controller's own terminal block.

⚠️ Protocol needs confirming on site before anything is ordered or connected — there's a naming conflict in the source material that needs resolving, not assuming:


The source photo file is named "Serial_Communication_RS232_Female_Connector…"
This inspection round described it verbally as an "RS485" port
The physical label on the panel itself just says "SERIAL COMMS" — no protocol marked


A female DB9 conventionally signals RS-232 (3-wire: TX/RX/GND), but since the F4S natively supports both EIA-232 and EIA-485 from the same internal terminal block, either is genuinely possible depending on how this breakout was wired. Next step: with mains isolated (per the panel's own warning label), trace or continuity-check which F4S terminals this DB9 connects to, or check for an internal wiring label/schematic. This determines whether a USB-to-RS232 or USB-to-RS485 adapter is needed — a five-minute check that avoids ordering the wrong part.

3. Controller rear terminal block (interior)
V:\Mechatronics\Omkar\Temperature Cabinet Setpoint Control\PXL_20240205_104301036.jpg
Confirms the exact unit: part no. F4SH-CCA0-01RG, SN 047209, Type 4X enclosure. This angle shows the Out 1A/1B, Out 2A/2B control-output terminals and four option-card slots (In 2, In 3, Rx 1, Rx 2 — matching the base unit's optional auxiliary input/retransmit module slots from the ordering guide). It does not show the EIA-232/EIA-485 comms terminal block — that's elsewhere on the same rear face and still needs its own photo/trace to resolve the RS-232-vs-RS-485 question below.

RS-485 wiring, for reference against the RS-232 3-wire (TX/RX/GND) already noted:

RS-232RS-485 (as Watlow documents it)Wire count3: TX, RX, GND3: T+/R+ (A), T-/R- (B), COMSignal typeSingle-endedDifferential pairTopologyPoint-to-point onlyMulti-drop (up to 32 devices)Typical max cable length~15 m~1200 m

Both land on 3 wires, and a DB9 has no standard RS-485 pin assignment (unlike RS-232's conventional pins 2/3/5) — so the connector shape alone still can't answer this. Tracing the internal wiring from the DB9 back to the F4S terminal strip (preferred — no need to cut/strip anything) remains the right method; this round's photo just didn't happen to capture that terminal group.
4. Junction box — thermocouple connections
V:\Mechatronics\Omkar\Temperature Cabinet Setpoint Control\Junction Box Thermocouple Connections.png
A dedicated junction box with 3 miniature Type K thermocouple sockets (green body, "K" marked) — two wired with yellow Type K extension cable, one spare. Part of the existing read-only sensor monitoring path (→ EL3314 thermocouple input → existing HMI temperature tiles), separate from the new setpoint-write path via the Serial Comms port above. Included for completeness/traceability.

5.  Thermocouple legend
V:\Mechatronics\Omkar\Temperature Cabinet Setpoint Control\Thermocouple Legend.png
Confirms the four monitored channels — Ambient Temperature, Body Temperature, Monitor Temperature, Chamber Temperature — matching the tiles already shown on the existing CODESYS HMI screen. One tile on that HMI, "Hyperbaric Water Temperature," doesn't appear on this legend and may belong to a different chamber/rig — worth a quick check, not a blocker. Adjacent Actuator PT and Primary Stem Seal PT connectors confirm this panel serves the wider valve-test rig, not only temperature monitoring.

Investigated whether the Raspberry Pi + EK1100 + EL1409 + EL2869 + EL3314 + ELM3148 combination can communicate with the Watlow F4S over Modbus or any other protocol, by checking each device's official Beckhoff documentation directly (not inference):

ModuleFunctionComms capabilityEK1100EtherCAT Bus CouplerPassive — bridges EtherCAT (upstream) to E-bus (downstream) only. No serial ports. Beckhoff's own coupler family comparison table lists a different product, the EK9000, as the one with native Modbus TCP/UDP gateway capability — the EK1100 itself has none.EL140916-ch digital inputE-bus powered digital input onlyEL286916-ch digital outputE-bus powered digital output onlyEL33144-ch thermocouple inputE-bus powered analog input onlyELM31488-ch 24-bit analog inputE-bus powered analog input only

None of these five modules has an RS-232, RS-485, or any serial interface — they only ever talk E-bus (Beckhoff's internal 5 V terminal bus) to the coupler, which only ever talks EtherCAT upstream. There is no path through this hardware set for Modbus RTU (or any other protocol) to reach an external RS-485/RS-232 device like the F4S.

This confirms scope point 4 (additional hardware) is required — it is not optional.

Note: even Beckhoff's own EK9000 (Modbus TCP/UDP-capable coupler) wouldn't fully solve this on its own — it speaks Modbus TCP, while the F4S only exposes Modbus RTU over EIA-232/485 (no Ethernet option on this model). It would still need a TCP↔RTU gateway downstream, which is more hardware and cost than the option below for no functional benefit.

Recommended path: USB-to-serial adapter via the existing external port


Use the existing "SERIAL COMMS" DB9 port found during inspection (see photo above) rather than opening the enclosure — the wiring back to the F4S already exists, which removes a wiring step from the original plan.
Confirm the protocol first (RS-232 vs RS-485 — see caveat above) before ordering anything:

If RS-232 → a simple USB-to-RS232 (DB9) adapter cable.
If RS-485 → a USB-to-RS485 adapter wired to whichever DB9 pins the continuity check identifies (non-standard pinout, since RS-485 isn't a native DB9 signal set).



Either way, still bypass the EtherCAT/Beckhoff chain entirely — plug the adapter straight into a Raspberry Pi 5 USB port (the panel's external USB 2.0 feedthrough remains available for this).
Do not add a Beckhoff EL6001/EL6021 serial terminal to the rack — even if fitted, it cannot be used as a CODESYS COM port under a non-TwinCAT runtime (confirmed dead end, see findings above).
Configure the adapter as a CODESYS Modbus Serial Master (/dev/ttyUSB0), matching the F4S's front-panel Setup → Communications settings (baud 9600/19200, address, parity — read off the unit, not assumed).

Candidate Modbus register map (F4S, static/manual setpoint mode — not profile mode)

RegisterFunctionAccessStatus100Input 1 Value (actual chamber temperature)Read (FC03/FC04)Candidate — from Watlow documentation, not yet live-tested300Set Point 1 (static setpoint)Read/Write (FC06)Corroborated on site — front panel independently labels the same parameter "SP1," currently reading 130.0 °C4122Set Point 1, Current Profile Status (active setpoint while a profile runs)Read onlyNot used — profiling out of scope

One implied decimal place (e.g. 1005 = 100.5). The register address itself is still to be confirmed by a live Modbus read once comms are established — the front-panel name match is corroborating evidence, not proof of the register number.


Scope status

In-scope itemStatusNew CODESYS sandbox projectDone — created in the repoIntegrate DLS008 hardwareDone — EtherCAT master + I/O terminals scanned and configured in the sandbox projectInvestigate remote setpoint capabilityDone — controller confirmed as Watlow F4S, Modbus RTU native, candidate register map identifiedIdentify additional hardware/wiring/settingsIn progress — EtherCAT-terminal and EL6021 routes ruled out with documentary evidence; existing external "SERIAL COMMS" DB9 port found on site (removes a wiring step); protocol (RS-232 vs RS-485) still needs on-site confirmation before the adapter is orderedBasic HMI inputNot startedSend setpoint to cabinetNot started — blocked on physical inspection + adapter procurementConfirm acceptanceNot startedValidation + fault indicationNot startedDocumentationIn progress (this file + linked findings)


Open items before Phase 2 (🔵 TL checkpoint)


Priority: with mains isolated, continuity-check the "SERIAL COMMS" DB9 port back to the F4S terminal block to resolve whether it's wired RS-232 or RS-485 — this decides which adapter to buy. This round's rear-terminal photo confirmed the exact unit (F4SH-CCA0-01RG) but didn't happen to capture the comms terminal group itself — worth one more targeted photo of that specific block, or the trace.
Record F4S slave address, baud rate, and parity from the front-panel Setup → Communications menu (not yet photographed this round).
Confirm which Raspberry Pi is actually running the CODESYS sandbox project / acting as EtherCAT master — this, not USB availability, is what decides which Pi's USB port gets the serial adapter. A USB device plugged into the other Pi is invisible to a CODESYS runtime running on this one; they're separate computers. This round's description (Pi #2 has the Ethernet connection, Pi #1 uses HDMI instead) tentatively points to Pi #2 as the CODESYS/EtherCAT host, which would mean the adapter belongs on Pi #2's spare USB port — the opposite of "avoid the Ethernet Pi." Needs on-site confirmation before wiring, since a mistake here fails silently rather than obviously.
Power-budget check: the 5 V/5 A (30 W) rail is shared across two Raspberry Pi 5 units — official full-load guidance for a single Pi 5 is 5 V/5 A, so this is worth a real measurement rather than an assumption.
TL sign-off on the adapter purchase (RS-232 or RS-485, per item 1) before ordering.
Confirm the F4S is in static/manual setpoint mode (not running an internal profile) before any register-300 write testing.
Quick check on the "Hyperbaric Water Temperature" HMI tile, which doesn't appear on the thermocouple legend photographed this round — confirm whether it belongs to this cabinet or a different rig.





Repository contents


Kickoff document — objective, scope, definition of done
Development plan — phased approach, equipment findings, hardware decision tree
Equipment datasheets (CP1/DLS008 panel, ELM3148, EK1100, EL1409, EL2869, EL3314, Watlow F4S, power supplies, MCB)
docs/photos/ — site inspection photos (controller front panel, serial comms port, thermocouple junction box, thermocouple legend)
This README — living project status summary
