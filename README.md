# Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
Develop a safe and reliable method of allowing an operator to change the setpoint of the selected temperature cabinet from a CODESYS HMI. The cabinet keeps its own closed-loop control at all times — CODESYS provides supervisory setpoint control only, never a replacement control loop.

Owner: Omkar Joshi (OJ) — Oliver Valvetek / Oliver Mechatronics / Oliver R&D
Status: Phase 1 — Investigation (hardware audit + comms path confirmed; physical inspection pending)


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


Key finding: none of DLS008's EtherCAT I/O terminals can reach the F4S

Investigated whether the Raspberry Pi + EK1100 + EL1409 + EL2869 + EL3314 + ELM3148 combination can communicate with the Watlow F4S over Modbus or any other protocol, by checking each device's official Beckhoff documentation directly (not inference):

ModuleFunctionComms capabilityEK1100EtherCAT Bus CouplerPassive — bridges EtherCAT (upstream) to E-bus (downstream) only. No serial ports. Beckhoff's own coupler family comparison table lists a different product, the EK9000, as the one with native Modbus TCP/UDP gateway capability — the EK1100 itself has none.EL140916-ch digital inputE-bus powered digital input onlyEL286916-ch digital outputE-bus powered digital output onlyEL33144-ch thermocouple inputE-bus powered analog input onlyELM31488-ch 24-bit analog inputE-bus powered analog input only

None of these five modules has an RS-232, RS-485, or any serial interface — they only ever talk E-bus (Beckhoff's internal 5 V terminal bus) to the coupler, which only ever talks EtherCAT upstream. There is no path through this hardware set for Modbus RTU (or any other protocol) to reach an external RS-485/RS-232 device like the F4S.

This confirms scope point 4 (additional hardware) is required — it is not optional.

Note: even Beckhoff's own EK9000 (Modbus TCP/UDP-capable coupler) wouldn't fully solve this on its own — it speaks Modbus TCP, while the F4S only exposes Modbus RTU over EIA-232/485 (no Ethernet option on this model). It would still need a TCP↔RTU gateway downstream, which is more hardware and cost than the option below for no functional benefit.


Recommended path: USB-to-RS485 adapter, direct to the Raspberry Pi


Bypass the EtherCAT/Beckhoff chain entirely. Plug a small USB-to-RS485 adapter into a Raspberry Pi 5 USB port (the panel already has an external USB 2.0 feedthrough — no enclosure modification needed).
Do not add a Beckhoff EL6001/EL6021 serial terminal to the rack — even if fitted, it cannot be used as a CODESYS COM port under a non-TwinCAT runtime (Beckhoff's own datasheet ties COM-port emulation to the TwinCAT Virtual Serial COM Driver; confirmed dead end).
Configure the adapter as a CODESYS Modbus Serial Master (/dev/ttyUSB0), matching the F4S's front-panel Setup → Communications settings (baud 9600/19200, address, parity — read off the unit, not assumed).
Wire 3-wire RS-485: adapter D+/A ↔ F4S T+/R+, D-/B ↔ F4S T-/R-, GND ↔ F4S COM.


Candidate Modbus register map (F4S, static/manual setpoint mode — not profile mode)

RegisterFunctionAccess100Input 1 Value (actual chamber temperature)Read (FC03/FC04)300Set Point 1 (static setpoint)Read/Write (FC06)4122Set Point 1, Current Profile Status (active setpoint while a profile runs)Read only — not used; profiling is out of scope

One implied decimal place (e.g. 1005 = 100.5). Exact slave address, baud, parity, and rear-terminal numbering must still be confirmed by physical inspection — treat the above as the starting point for bench testing, not as final values.


Scope status

In-scope itemStatusNew CODESYS sandbox projectNot yet createdIntegrate DLS008 hardwareHardware audited and documented (this README); EtherCAT scan/config pendingInvestigate remote setpoint capabilityDone — controller confirmed as Watlow F4S, Modbus RTU native, candidate register map identifiedIdentify additional hardware/wiring/settingsDone — USB-to-RS485 adapter confirmed as the only viable addition; EtherCAT-terminal and EL6021 routes ruled out with documentary evidenceBasic HMI inputNot startedSend setpoint to cabinetNot started — blocked on physical inspection + adapter procurementConfirm acceptanceNot startedValidation + fault indicationNot startedDocumentationIn progress (this file + linked findings)


Open items before Phase 2 (🔵 TL checkpoint)


Physically inspect the F4S: confirm slave address, baud rate, parity, and rear comms terminal numbering.
Confirm which of the two Raspberry Pi 5 units is the CODESYS/EtherCAT master, and which is free to host the USB-RS485 adapter.
Confirm the 5 V/5 A (30 W) Pi power rail is adequate for two Raspberry Pi 5 units running simultaneously under load — official full-load guidance for a single Pi 5 is 5 V/5 A; worth a quick power-budget check now that two units share one supply.
TL sign-off on the USB-RS485 adapter purchase (~£15–£40) before ordering.
Confirm the F4S is in static/manual setpoint mode (not running an internal profile) before any register-300 write testing.



Repository contents


Kickoff document — objective, scope, definition of done
Development plan — phased approach, equipment findings, hardware decision tree
Equipment datasheets (CP1/DLS008 panel, ELM3148, EK1100, EL1409, EL2869, EL3314, Watlow F4S, power supplies, MCB)
This README — living project status summary
