# Omkar_Temperature_Cabinet_Setpoint_Control
**Branch purpose:** Development & testing of the Python gateway approach to remote setpoint control.
**Status:** Investigation in progress. Not for merge to `main`.
**TL email directive (date):** Move from CODESYS-native serial Modbus to Python serial bridge + Modbus TCP.

---
## Investigation Summary
### What was tried: CODESYS-native Modbus RTU device
**Scope:** Make a CODESYS Modbus master (serial) talk directly to the Watlow F4S over RS-232,
reading registers 100 (temperature) and 300 (setpoint) and writing register 300 (new setpoint).
**Work completed (Phase 0–3):**
- ✅ Phase 0: Network stabilization — disabled Ethernet offloading (ethtool) for EtherCAT+Modbus latency
- ✅ Phase 1: Linux layer — udev symlink `/dev/ttyWatlowF4S` (stable across replug/reboot), SysCom config (`portnum.2=2`, `Linux.Devicefile.2=/dev/ttyWatlowF4S`), baseline `mbpoll` reads proven (register 100 and 300 return live data)
- ✅ Phase 2: Device tree — `Modbus_COM` (COM2, 19200 8N1), `Modbus_Master_COM_Port` (RTU, MainTask), three channels (ReadChamberTemp FC03 reg100, ReadSetpoint FC03 reg300, WriteSetpoint FC06 reg300 rising-edge)
- ✅ Phase 3: PLC_PRG — state machine (IDLE → READY → WRITING → CONFIRM → IDLE/FAULTED), edge-triggered write, read-back confirmation, range + menu-state fault detection
**Configuration validation (all four layers correct):**
- ✅ Linux config: `Linux.Devicefile.2=/dev/ttyWatlowF4S, portnum.2=2`
- ✅ CODESYS device: `Modbus_COM` Port = COM2, Baud = 19200
- ✅ CODESYS master: Bus cycle task = MainTask (explicit, not "parent")
- ✅ udev symlink: `/dev/ttyWatlowF4S -> ttyUSB0` (exists, correct)
- ✅ Runtime: `codesyscontrol` active (running)
**Blocker:** Despite all configuration being correct, `Modbus_COM` device showed "not running" in the CODESYS device tree. No error message; no red-triangle diagnostic. The port never opened at the CODESYS device level, despite being correctly wired, configured, and available at the Linux level.
**Root cause hypothesis:** A rare CODESYS firmware/library bug where the Modbus RTU device object doesn't see the port open even though the runtime holds it. The serial driver issue that prompted the TL email.
**Decision:** Per TL directive, **abandon this path.** The CODESYS-native serial Modbus device is the bottleneck. Move to the Python bridge approach.

---
## Solution: Python TCP ↔ RTU Gateway
**Approach:** Python owns the serial port and exposes a **Modbus TCP slave** (server) on the network.
CODESYS becomes a Modbus **TCP master** (client), reading/writing the F4S values through the Python gateway.
**Why this is robust:**
- CODESYS Modbus TCP is native and reliable (no serial red-triangle issues).
- Python is the single serial owner — zero port contention.
- Same register/scale model proven by `mbpoll` (reg100, reg300, /10, addr 1, 19200 8N1).
- Standard industrial pattern (TCP gateway in front of serial device).
### Architecture
```
 CODESYS (sandbox project)          Raspberry Pi 10.1.6.17              Watlow F4S
 ┌────────────────────────┐  Modbus TCP  ┌──────────────────────────┐ RS-232 ┌─────────┐
 │ Modbus TCP MASTER      │ ── :502 ───► │ f4s_gateway.py           │ ─────► │ slave 1 │
 │ reads/writes registers │ ◄──────────  │  TCP slave + RTU master  │ ◄───── │ 100/300 │
 └────────────────────────┘              │  SOLE serial owner       │        └─────────┘
                                         └──────────────────────────┘
```
### The 4 values → TCP register map (holding registers, x10 integers)
| Value | TCP reg | Direction | Notes |
|---|---|---|---|
| **Current cabinet temperature** | 2 | Python → CODESYS | read-only, cyclic from F4S reg100 |
| **Current setpoint (confirmed)** | 3 | Python → CODESYS | read-only, cyclic, from F4S reg300 read-back |
| **Requested new setpoint** | 0 | CODESYS → Python | write x10 int (265 = 26.5 °C) |
| **Apply trigger** | 1 | CODESYS → Python | write 1 to apply; Python clears to 0 |
| **Confirmation / status** | 4 | Python → CODESYS | 0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS |
"Confirmation that the new setpoint has been accepted" = reg4 == 0 AND reg3 == reg0 after an apply.

---
## Deliverables
### Python gateway (`python-gateway/f4s_gateway.py`)
- Sole serial owner of `/dev/ttyWatlowF4S`
- Modbus RTU master to F4S (FC03 reads reg100/300, FC06 writes reg300)
- Modbus TCP slave server on :502 exposing the 5-register window
- Read-back confirmation logic (write reg300, read back within 0.5s, check match)
- Fault codes: RANGE, COMMS, WRITE_FAILED, NOT_ACCEPTED (F4S menu-state rejection)
- Systemd-ready (service unit provided in setup guide)
- Logging to `f4s_gateway.log`
### CODESYS retargeted code (`PLC_PRG_TCP_Retargeted.st`)
- Same state machine logic as the serial version (IDLE → READY → WRITING → CONFIRM → IDLE/FAULTED)
- Reads temperature, confirmed setpoint, and status from TCP channels (reg2, reg3, reg4)
- Writes requested setpoint and apply trigger to TCP registers (reg0, reg1)
- Edge-triggered apply (one pulse per user request, no cyclic EEPROM wear)
- Range validation (0–200 °C), timeout detection, menu-state rejection handling
- Drop-in replacement: copy this into the sandbox project's PLC_PRG
### Setup guide (`Python_Gateway_Integration_Setup_Guide.md`)
- Full architecture diagram
- Git branch creation/push commands (SSH)
- Gateway install + systemd unit
- CODESYS TCP master/slave device configuration
- I/O mapping (TCP channels → GVL_Modbus variables)
- T1–T4 test plan (4 values: temp, confirmed SP, request, apply)
- Per-step troubleshooting
- Commit/push workflow

---
## What has been tested
| Item | Status | Notes |
|---|---|---|
| Linux serial layer (mbpoll) | ✅ Proven | Reads reg100/300 return live data; writes reg300 accepted/confirmed |
| F4S wiring (ADR-001) | ✅ Verified | TX/RX not swapped, terminal screws torqued |
| Python gateway (standalone) | ⏳ Pending | Not yet deployed; will test with `mbpoll -m tcp` before CODESYS |
| CODESYS TCP master | ⏳ Pending | Device tree will be built in sandbox project after gateway proven |
| T1–T4 (the 4 values) | ⏳ Pending | Will execute after both gateway + CODESYS are ready |

---
## Findings so far
1. **Serial-Modbus-in-CODESYS device is a dead end on this hardware.** Config looks perfect; device shows "not running" with zero diagnostic. CODESYS firmware/library issue. Not worth debugging further.
2. **The Python gateway is the right call.** It's standard practice, avoids the CODESYS serial driver entirely, and reuses the proven Linux/RTU layer (which always worked).
3. **Modbus TCP is the cleanest transport.** CODESYS has native support, no new failure modes, and TCP registers are safe for cyclic reads (no EEPROM wear like the serial path had).
4. **The state machine logic is transport-agnostic.** Same code, different data sources (TCP vs. serial channels). Easy transition.

---
## Next steps
1. **Deploy the gateway** (`python-gateway/f4s_gateway.py`, systemd unit).
2. **Prove it standalone** with `mbpoll -m tcp` reads/writes (no CODESYS yet).
3. **In sandbox CODESYS project:** add Modbus TCP master/slave device, configure channels, map to GVL_Modbus.
4. **Copy PLC_PRG_TCP_Retargeted.st** into the sandbox project's PLC_PRG.
5. **Run T1–T4 tests,** log results, and push them to this branch.
6. **Send TL an update** with what was tested and the outcome.

---
## Branch conventions (per `RnD_Camera/toby_lelean`)
- **Clear commit messages** describing what was tried and the result.
- **Incremental commits** (not one monster commit at the end).
- **Documentation alongside code** (this README, setup guide, Python docstrings).
- **No direct commits to `main`.** All work stays on this branch (`Omkar_Temperature_Cabinet_Setpoint_Control`).
- **Never merge this branch to `main`** — it's for dev/test exploration only.

---
## Files in this branch
- `python-gateway/f4s_gateway.py` — the gateway (Modbus TCP slave + RTU master)
- `Python_Gateway_Integration_Setup_Guide.md` — complete setup instructions
- `PLC_PRG_TCP_Retargeted.st` — retargeted state machine (CODESYS)
- `README.md` (this file) — investigation summary
- `docs/` — additional diagrams or notes as investigation progresses

---
**Started:** [date]
**Last updated:** [date]
**Author:** OJ (Omkar Joshi)
**TL reference:** Email directive to move from serial-Modbus-in-CODESYS to Python gateway
