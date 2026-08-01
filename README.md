# Temperature Cabinet Setpoint Control from CODESYS HMI

Supervisory setpoint control of the **Left Hand Small Temperature Cabinet** (Watlow F4S controller)
from a CODESYS runtime on a Raspberry Pi, so an operator can change the cabinet setpoint from a
CODESYS HMI instead of walking to the cabinet front panel.

The cabinet keeps its own closed-loop PID control at all times. CODESYS never becomes the control
loop — it reads state and writes a target. That boundary is the whole design.

**Author:** Omkar Joshi — Oliver Valvetek / Oliver Mechatronics / Oliver R&D
**Working branch:** `Omkar_Temperature_Cabinet_Setpoint_Control` (all development; `main` is not used for this work)
**Status:** Modbus proof of concept **complete and qualified on hardware**. Next stage: CODESYS WebVisu HMI.

---

## The objective

Exchange four values between the working Python serial layer and CODESYS:

| # | Value | Direction | How it is carried |
|---|---|---|---|
| 1 | Current cabinet temperature | Cabinet → CODESYS | TCP reg 2, FC03 cyclic read |
| 2 | Current setpoint | Cabinet → CODESYS | TCP reg 3, FC03 cyclic read |
| 3 | Requested new setpoint | CODESYS → Cabinet | TCP reg 0, FC06 write |
| 4 | Confirmation the new setpoint was accepted | Cabinet → CODESYS | TCP reg 3 read-back + reg 4 status, evaluated by the CODESYS state machine |

**All four are proven end to end on the real cabinet.** Everything below is how I got there.

---

## Architecture as built

```
Windows CODESYS IDE
        │ (download / online)
        ▼
Raspberry Pi 10.1.6.17 ─ CODESYS Control for Linux ARM64 SL
        │
        │  Modbus TCP Master ──► Modbus TCP Slave, 10.1.6.17:502, Unit ID 1
        ▼
   f4s_gateway.py  (Python, systemd service f4s-gateway)
        │
        │  Modbus RTU, /dev/ttyWatlowF4S, 19200 8N1, slave 1
        ▼
   Watlow F4S  (F4SH-CCA0-01RG)  ─ reg 100 = temperature, reg 300 = Set Point 1
        │
        ▼
   Left Hand Small Temperature Cabinet
```

The single most important architectural decision: **the Python gateway owns the serial port and
CODESYS never touches it.** CODESYS talks Modbus TCP only. Everything that made the serial link
awkward — parity, port claiming, adapter re-enumeration, unit-ID quirks — is now solved once in
Python instead of being fought inside the PLC runtime.

---

## Equipment

| Item | Identity |
|---|---|
| Control panel | DLS008 |
| Temperature cabinet | Left Hand Small Temperature Cabinet (JTS Ltd / James Technical Services Ltd) |
| Cabinet controller | Watlow SERIES F4S, part no. **F4SH-CCA0-01RG**, SN 038983 — single-channel ¼ DIN ramping controller |
| Runtime host | Raspberry Pi 5 at **10.1.6.17** (`LeftHandSmallTempCab`) |
| Serial link | USB-to-RS232 adapter → external "SERIAL COMMS" DB9 on the cabinet |

**DLS008 hardware audit:** 2× Raspberry Pi 5; Beckhoff EK1100 EtherCAT coupler, 2× ELM3148-0000
(24-bit AI), EL3314 (thermocouple), EL1409 (16 DI), EL2869 (16 DO); Siemens SENTRON 5SY4106-8 MCB;
RS PRO DIN-rail PSUs (24 V / 5 A and 5 V / 5 A).

The EtherCAT branch is the existing read-only sensor monitoring path (thermocouples → EL3314 → HMI
temperature tiles). It is **unrelated** to the setpoint-write path documented here, and I deliberately
kept the two separate so neither can break the other.

---

## Repository layout

Each folder owns exactly one leg of the architecture, in the order I built them.

| Folder | Owns | Stage |
|---|---|---|
| [`remote-ssh-vscode/`](remote-ssh-vscode/) | VS Code Remote-SSH onto the Pi, and the GitHub workflow from there | 1 |
| [`linux-integration/`](linux-integration/) | Pi-side serial bring-up: adapter, permissions, udev symlink, `mbpoll` bench tests | 2 |
| [`codesys-modbus-integration/`](codesys-modbus-integration/) | ⚠️ **Superseded.** CODESYS-native Modbus RTU over the COM port. Kept as the physical-link investigation record | 3 |
| [`python-rtu-integration/`](python-rtu-integration/) | The Python gateway, its RTU link to the F4S, and standalone test scripts | 4 |
| [`codesys-python-gateway-modbus-integration/`](codesys-python-gateway-modbus-integration/) | CODESYS side of the gateway: device tree, channel table, I/O mapping, ST source, test logs | 5 |
| `docs/` | Project kick-off document | — |

---

# Development history

## Stage 1 — Remote SSH + VS Code onto the Pi

Everything in this repo was authored and pushed from a VS Code window running **on** the Pi, not on
my laptop. This was the first thing I set up, because without it every `dmesg`, `mbpoll` and `git`
command becomes a copy-paste exercise between two machines.

- VS Code **Remote - SSH** → `mechatronics@10.1.6.17`.
- Terminal, file explorer and extensions all execute on the Pi; the Source Control panel talks to
  GitHub exactly as a local clone would.
- Python work runs inside a venv (`source venv/bin/activate` first, every session), with
  `pymodbus` pinned to **3.12.1** — the version matters, see Stage 4.
- All commits go to `Omkar_Temperature_Cabinet_Setpoint_Control`.

Full procedure: [`remote-ssh-vscode/README.md`](remote-ssh-vscode/README.md).

---

## Stage 2 — Linux integration: proving the physical link

Before writing a single line of PLC code I proved the serial link from the Linux shell with
`mbpoll`. If the link cannot be read from a terminal, no amount of CODESYS configuration will help.

### Protocol determination

The cabinet already has an external DB9 labelled "SERIAL COMMS" on a removable plate, so the
enclosure never needed opening. The F4S side-panel nameplate gave the definitive terminal map:

| Terminal | Signal |
|---|---|
| 11 | +5 V comms (accessory supply) |
| 12 | 485 T+/R+ |
| 13 | 485 T−/R− |
| 14 | 232 Tran. (transmit) |
| 15 | 232 Rec. (receive) |
| 16 | Comms (common/ground, shared by both protocols) |

Both RS-232 and RS-485 are wired out natively — no option card needed. Tracing the DB9 back to
terminals 14/15/16 settled it: **RS-232**, three wires (TX / RX / GND), point-to-point. A
USB-to-RS232 adapter was all the hardware required.

RS-485 was considered and rejected: multi-drop and long cable runs are irrelevant for a single
controller a couple of metres away, and the wiring evidence pointed to 232 regardless.

### Bench test findings

Two real faults were found and fixed at this stage, both of which would have been almost invisible
from inside CODESYS:

**1. Parity mismatch.** The first `mbpoll` read timed out with `Connection timed out`. `mbpoll`
uses `-P` (uppercase) for RTU parity with spelled-out values, and the F4S was set to **8N1**:

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
```

**2. TX/RX swap at the F4S terminal block.** Even with correct parity the link stayed silent. The
actual root cause was the transmit and receive wires being crossed at the controller end. Once
corrected, register 100 returned live temperature immediately.

After that: read reg 100 (temperature), read reg 300 (Set Point 1), write reg 300 with FC06, and
verify the change on the cabinet's own front panel. **The hardware link was proven from the shell
before CODESYS was involved at all.**

> **F4S menu-state caveat.** The controller rejects remote writes while its front-panel menu is
> being edited. This is real device behaviour, not a bug, and it is why the design has an explicit
> "not accepted" path rather than assuming a write always lands.

A `udev` rule gives the adapter a stable name, `/dev/ttyWatlowF4S`, so the link survives the port
moving between `ttyUSB0` and `ttyUSB1`.

Full procedure: [`linux-integration/README.md`](linux-integration/README.md).

---

## Stage 3 — CODESYS Modbus over the COM port (superseded)

The obvious next step was to let CODESYS drive the serial port directly, using its built-in
`Modbus_COM` → Modbus Master → Modbus Slave device chain.

### What this stage produced

- **Network stabilisation.** The Pi's `macb` Ethernet driver was stalling on TX under load, which
  destabilised the online connection. Disabling offloading on the main port fixed it, made permanent
  via a startup rule:
  ```bash
  sudo ethtool -K <port> tso off gso off gro off tx off rx off
  ```
  This was mandatory groundwork and remains valid — it is what lets EtherCAT and Modbus coexist
  predictably on the same host.
- **SysCom mapping.** CODESYS reaches a Linux serial device through
  `/etc/CODESYSControl_User.cfg`:
  ```ini
  [SysCom]
  Linux.Devicefile.2=/dev/ttyUSB0
  portnum.2=2
  ```
  Port number **2** rather than 1 — port 1 collided with an existing entry and produced the classic
  failure signature: `Modbus_COM` showing a repeat icon with red triangles on master and slave.
- Full device-tree build: read channel on reg 100, write channel on reg 300, `GVL_Modbus`, the
  `E_SetpointState` / `E_FaultCode` enumerations, and I/O mapping.

### Why I moved away from it

Two processes cannot own one serial port. Any diagnostic use of `mbpoll` meant stopping the runtime,
and every serial-layer quirk had to be re-solved inside the PLC. The link worked, but it was
fragile to operate and awkward to debug.

**Decision: move the serial port into Python and give CODESYS a Modbus TCP endpoint instead.** That
change is what made the rest of the project straightforward.

This folder is retained as the investigation record, not as a live path:
[`codesys-modbus-integration/README.md`](codesys-modbus-integration/README.md).

---

## Stage 4 — Python RTU integration: the gateway

[`python-rtu-integration/f4s_gateway.py`](python-rtu-integration/f4s_gateway.py) is a Modbus
**TCP server** and Modbus **RTU client** in one process. It polls the F4S continuously over serial
and publishes everything into a five-register TCP image that CODESYS can read and write.

### Gateway TCP register map (unit id 1)

| Reg | Direction | Meaning | Scaling |
|---|---|---|---|
| 0 | write | Requested setpoint | ×10, **signed** |
| 1 | write (pulse of 1) | Apply trigger — the gateway clears it | 0/1 |
| 2 | read | Chamber temperature | ×10, **signed** |
| 3 | read | Confirmed setpoint read-back | ×10, **signed** |
| 4 | read | Status: 0 OK · 2 WRITE_FAILED · 3 NOT_ACCEPTED · 4 RANGE · 5 COMMS | — |

The gateway validates every request against **−400…2000** (−40…200 °C ×10) before touching the
serial port, writes reg 300 on the F4S, reads it back, and only then reports success.

### Problems solved at this stage

| Problem | Resolution |
|---|---|
| Serial opening as 8E1 instead of 8N1 | Parity set explicitly at client construction |
| `ModbusSparseDataBlock` "does not support item assignment" | Wrong API assumption; corrected against pymodbus source |
| TCP reads always 0.0 °C, trigger never cleared | Datastore writes were landing on a different object than the one being served |
| `setValues` / `getValues` missing | pymodbus 3.12 renamed the device-context API; pinned to **3.12.1** and used the real methods |
| `'ModbusDeviceContext' object has no attribute 'getValues'` **only under systemd** | The unit was running as `root`, which resolved a *different*, unpinned pymodbus. Fixed by running as my own user with `setcap 'cap_net_bind_service=+ep'` for the port-502 bind |
| Permanent `RTU comms timeout` after the USB adapter re-enumerated | Added link supervision: after 3 consecutive failures the port is marked dead, closed and reopened; status goes 5 (COMMS) → 0 (OK) automatically on recovery |

That last one matters operationally — unplugging the adapter no longer requires a service restart.

Runs as a systemd unit (`f4s-gateway`), enabled at boot. Standalone test scripts
(`test_rtu_write.py`, `test_range_sweep.py`, `probe_f4s_limits.py`) let me qualify the RTU leg
without CODESYS in the loop at all.

Full detail, including the T1–T5 plan: [`python-rtu-integration/README.md`](python-rtu-integration/README.md).

---

## Stage 5 — CODESYS ↔ Python gateway over Modbus TCP

### Device tree

```
Device (CODESYS Control for Linux ARM64 SL)
└── Ethernet (adapter reaching 10.1.6.17)
    └── Modbus_TCP_Master (Modbus TCP Client)
        └── Modbus_TCP_Slave — IP 10.1.6.17 · Port 502 · Unit ID 1 · Response timeout 8000 ms
```

> **Unit ID must be 1.** The CODESYS default is **255**, and the gateway serves device id 1 only.
> Left at 255 you get a *connected* socket where every transaction fails with
> `GATEWAY TARGET FAILED TO RESPOND`, and an Error Counter of exactly 2× the Request Counter.
> That signature cost me a full day and is the single best diagnostic clue in this project.

### Channel table

| # | Access type | Trigger | READ off | WRITE off | Maps to |
|---|---|---|---|---|---|
| 0 | Write Single Register (FC06) | Cyclic 1000 ms | — | 16#0000 | `wSetpoint1Write` |
| 1 | Write Single Register (FC06) | **Rising edge** | — | 16#0001 | data WORD → `wTriggerValue`, trigger BIT → `xWriteTrigger` |
| 2 | Read Holding Registers (FC03) | Cyclic 2000 ms | 16#0002 | — | `wInput1Value` |
| 3 | Read Holding Registers (FC03) | Cyclic 2000 ms | 16#0003 | — | `wSetpoint1Read` |
| 4 | Read Holding Registers (FC03) | Cyclic 2000 ms | 16#0004 | — | `wStatus` |

Three configuration rules that are easy to get wrong and produce a system that looks perfectly
healthy while doing nothing:

1. **Channel 1 needs both rows mapped.** A rising-edge FC06 channel sends the current value of its
   mapped *data WORD* when the *trigger BIT* goes 0→1. Leave the data word unmapped and it sends
   `0`; the gateway only fires on `1`, so writes succeed silently and change nothing.
   `wTriggerValue : WORD := 1` exists purely to be that constant.
2. **Channel 4 is not optional.** Without it `wStatus` reads 0 = "OK" permanently and the state
   machine is blind to every gateway-side failure.
3. **Map the element row** (`Holding Registers[n][0]`, type WORD), never the ARRAY parent. Set
   *Always update variables* = Enabled 1, and the master's bus cycle task = **MainTask**, never
   "unspecified".

### The signedness bug — and the fix

The system initially accepted only about **0.1…100 °C**. Negative setpoints and high temperatures
were rejected. The cause was three independent signedness faults in the same chain:

`WORD` is **unsigned** in IEC 61131-3, but these registers carry **signed 16-bit two's complement**
values. −1.0 °C arrives on the wire as `16#FFF6` (65526). Dividing that WORD directly gives 6552.6,
so every sub-zero value read as an absurd positive and every negative write was rejected as
out-of-range.

| Layer | Fix |
|---|---|
| CODESYS read | `rChamberTemp := WORD_TO_INT(GVL_Modbus.wInput1Value) / 10.0;` |
| CODESYS write | `GVL_Modbus.wSetpoint1Write := INT_TO_WORD(REAL_TO_INT(rReqSetpoint * 10.0));` |
| Fault direction | `IF rReqSetpoint < rMinSetpoint THEN eFaultCode := RANGE_LOW;` — previously reported RANGE_HIGH for low values |
| Gateway | Range check made signed, `−400…2000` |
| Timing | `dwMaxTimeout := 1000` (10 s at the 10 ms MainTask) — the old 3 s produced spurious timeouts on full-range moves |

Verified on all three layers independently and then integrated — 5 CODESYS watch-window cases
(−1.0, 0.0, −40.0 accepted; −41.0 → RANGE_LOW; 201.0 → RANGE_HIGH), 10 standalone Python cases, and
a device-level probe, all passing.

I also binary-searched the F4S itself with `probe_f4s_limits.py` to confirm the device genuinely
accepts −40…200 °C, so the software limits match the hardware rather than guessing.

### The setpoint state machine

[`src/POUs/PLC_PRG_TCP.st`](codesys-python-gateway-modbus-integration/src/POUs/PLC_PRG_TCP.st) is the program
actually running. It turns a raw register write into a supervised transaction:

```
IDLE ──(request validated)──► READY ──(FC06 edge)──► WRITING ──► CONFIRM ──┬──► IDLE
  ▲                                                                        │
  └──────────────────────── (reset) ──── FAULTED ◄──────────────────────────┘
```

| `E_SetpointState` | | `E_FaultCode` | |
|---|---|---|---|
| `IDLE` | 0 | `NO_FAULT` | 0 |
| `READY` | 10 | `COMMS_TIMEOUT` | 1 |
| `WRITING` | 20 | `WRITE_FAILED` | 2 |
| `CONFIRM` | 30 | `NOT_ACCEPTED` | 3 |
| `FAULTED` | 99 | `RANGE_LOW` | 4 |
| | | `RANGE_HIGH` | 5 |
| | | `OVER_TEMP` | 6 |

There are **three independent range gates** — PLC code (−40…200 °C), gateway (−400…2000 ×10), and
the F4S device itself. A bad value has to get past all three, and no single-layer mistake can
command the cabinet somewhere it should not go.

### Operating from the watch window

The PoC is driven entirely from the CODESYS watch window, no HMI required — deliberately, so the
control layer is proven before any operator interface sits on top of it. The workflow is
prepare-then-write: type the value into *Prepared value*, then `Ctrl+F7` to commit both
`rReqSetpoint` and `xStartWrite` in the same cycle.

Full build guide, watch list and procedure:
[`codesys-python-gateway-modbus-integration/README.md`](codesys-python-gateway-modbus-integration/README.md).

---

## Stage 6 — Qualification

Test plan T1–T6, run twice on separate days per the two-consecutive-clean-runs rule.

| Test | What it proves | Run 1 (Mon 27 Jul 2026) | Run 2 (Tue 28 Jul 2026) |
|---|---|---|---|
| T1 Temperature read | Objective value 1 | PASS | PASS |
| T2 Setpoint read | Objective value 2 | PASS | PASS |
| T3 Setpoint write | Objective value 3 | PASS | PASS |
| T4 Write confirm | Objective value 4 | PASS | PASS |
| T5 Range reject | Out-of-range refused, no write issued | PASS | PASS |
| T6 Menu-state reject | Device-refused write reported, not silently lost | PASS | PASS |

Run 2 was executed with no code changes and with the chamber in a different part of its cycle
(cooling through the mid-70s °C, against Run 1's 37–82 °C sweep), which also confirms the behaviour
is not temperature-dependent.

### Failure-mode drills

| Drill | Method | Result |
|---|---|---|
| 1 — Gateway stopped mid-write | Trigger a 28.0 °C write, then `systemctl stop f4s-gateway` while it is in flight | Faulted within 1–2 ms; cabinet setpoint unchanged (write aborted, not partially applied); recovered to IDLE / NO_FAULT ~40 ms after restart. **PASS** |
| 2 — Write attempted while gateway down | Stop the gateway first, then trigger a 30.0 °C write | Immediate fault on the first cycle, no false READY/WRITING; cabinet setpoint unchanged; auto-recovered to IDLE / NO_FAULT on restart with no manual retrigger. **PASS** |
| 3 — CODESYS runtime restart | Runtime stopped and restarted | Confirmed during handover review; not separately captured with evidence |

> **Worth knowing:** both drills fault as `NOT_ACCEPTED` rather than a dedicated comms-loss code.
> That is expected — `wStatus` is itself a cyclic FC03 read *from the gateway*, so when the gateway
> is unreachable that read simply stops refreshing and `wStatus` holds its last value instead of
> advancing to 5 (COMMS). It is the state machine's own confirm-timeout path that actually catches
> a dead gateway. Don't go looking for a COMMS-specific fault code in this build.

The important safety property in both drills: **the cabinet setpoint never changed during a fault.**
A failed write is a failed write, not a partial one.

Daily log: [`codesys-python-gateway-modbus-integration/docs/test-logs/2026-07-27_monday.md`](codesys-python-gateway-modbus-integration/docs/test-logs/2026-07-27_monday.md).

---

## Quick start

```bash
# On the Pi (via VS Code Remote-SSH to mechatronics@10.1.6.17)
cd ~/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
git checkout Omkar_Temperature_Cabinet_Setpoint_Control
source venv/bin/activate
pip3 install -r python-rtu-integration/requirements.txt   # pymodbus must be 3.12.1

# 1. Confirm the serial adapter and the F4S itself
ls -l /dev/ttyWatlowF4S
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 /dev/ttyWatlowF4S   # temperature
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 -1 /dev/ttyWatlowF4S   # setpoint

# 2. Start the gateway
sudo systemctl start f4s-gateway
systemctl status f4s-gateway
journalctl -u f4s-gateway -f

# 3. Prove the TCP side before opening CODESYS
mbpoll -m tcp -a 1 -t 4 -r 3 -c 2 -1 10.1.6.17          # reg 2,3 = temp, setpoint

# 4. CODESYS: go online, Unit ID = 1, watch GVL_Modbus + PLC_PRG
```

If step 3 fails, the problem is not in CODESYS — do not start changing the device tree.

---

## Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| Connected but every transaction fails; Error Counter = 2× Request Counter | Slave Unit ID left at 255 | Set Unit ID = 1 |
| Everything green, values never change | Bus cycle task "unspecified", or *Always update variables* disabled | Set task = MainTask, enable variable updates |
| Write appears to succeed, cabinet does not move | Channel 1 data WORD row unmapped, so trigger sends 0 | Map `wTriggerValue` to the data WORD row |
| Sub-zero setpoints rejected; temperatures read as huge positives | Signed values treated as unsigned WORD | `WORD_TO_INT` on read, `INT_TO_WORD(REAL_TO_INT(...))` on write |
| `mbpoll` times out on RTU | Parity mismatch, or TX/RX crossed | `-P none` for 8N1; verify terminals 14/15/16 |
| Gateway stuck in `RTU comms timeout` | USB adapter re-enumerated | Handled automatically by link supervision; check `/dev/ttyWatlowF4S` symlink exists |
| `getValues` AttributeError only under systemd | Service running as root, resolving a different pymodbus | Run as the user that installed the pinned version; `setcap` for the port-502 bind |
| `Modbus_COM` repeat icon, red triangles (Stage 3 only) | SysCom port number collision | Use `portnum.2=2` |

---

## Key engineering decisions

| Decision | Reasoning |
|---|---|
| Supervisory setpoint write only, never a control loop | The F4S PID is proven, calibrated and safety-relevant. Replacing it adds risk with no benefit |
| Python owns the serial port; CODESYS speaks TCP | One process per port. Makes the serial layer independently testable and debuggable while the runtime keeps running |
| Read-back confirmation instead of assuming FC06 success | A Modbus write ACK means the frame was received, not that the device accepted the value. The F4S can legitimately refuse |
| Three independent range gates | No single-layer mistake can command the cabinet out of range |
| Explicit fault enumeration surfaced to the HMI | The operator gets a reason, not a silent failure |
| Watch-window qualification before any HMI | Proves the control layer on its own, so HMI work debugs the HMI and nothing else |
| Stable `udev` symlink for the adapter | `ttyUSB0` is not a stable identity across replug or reboot |

---

## Next stage — CODESYS WebVisu HMI

The control layer is complete and qualified. The remaining work is the operator interface on top
of it, and nothing underneath should need to change.

- [ ] Build the WebVisu operator page: live temperature, current setpoint, requested setpoint entry, and an explicit accept/reject indication
- [ ] Bind visualisation elements to `GVL_HMI` rather than directly to `GVL_Modbus`, keeping the driver boundary intact
- [ ] Surface `E_FaultCode` as operator-readable text, not a raw enum value
- [ ] Enforce the −40…200 °C limits in the HMI as an input constraint, in addition to the three existing gates
- [ ] Interlock: no new write accepted while a write is in flight (`READY` / `WRITING` / `CONFIRM`)
- [ ] Comms-health indicator driven by the confirm-timeout path, since the gateway status register cannot report its own absence
- [ ] Operator test pass on the finished page, and capture Drill 3 (runtime restart) with evidence

A first-pass operator page already exists at
[`codesys-python-gateway-modbus-integration/WebVisu/codesys_hmi.html`](codesys-python-gateway-modbus-integration/WebVisu/codesys_hmi.html)
as a layout reference for that work.

---

## Document index

| Document | What it covers |
|---|---|
| [`codesys-python-gateway-modbus-integration/README.md`](codesys-python-gateway-modbus-integration/README.md) | CODESYS build guide, proven configuration, watch-window procedure |
| [`codesys-python-gateway-modbus-integration/docs/test-logs/`](codesys-python-gateway-modbus-integration/docs/test-logs/) | Daily hardware test logs |
| [`python-rtu-integration/README.md`](python-rtu-integration/README.md) | Gateway install, systemd, register map, RTU test plan, troubleshooting history |
| [`linux-integration/README.md`](linux-integration/README.md) | Modbus RTU concepts, serial bring-up, `mbpoll` bench test |
| [`codesys-modbus-integration/README.md`](codesys-modbus-integration/README.md) | Superseded serial-direct approach; network stabilisation and SysCom |
| [`remote-ssh-vscode/README.md`](remote-ssh-vscode/README.md) | Remote-SSH and Git workflow from the Pi |
| `docs/Project Kick-Off- Temperature Cabinet Setpoint Control.pdf` | Objective, scope, definition of done |

The detailed working notes that used to sit alongside these (range investigation, week-2 roadmap,
per-layer validation summaries) have been folded into this README, which is now the single
project record.
