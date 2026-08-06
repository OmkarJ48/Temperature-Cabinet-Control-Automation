# F4S Modbus TCP↔RTU Gateway (Python / RTU side)

**Status: ✅ Proven working end-to-end on hardware.** Reads, writes-with-confirmation,
and range-validation all verified over real Modbus TCP against a real Watlow F4S.
CODESYS integration is proven too — see
[`../codesys modbus proof of concept and test logs/`](<../codesys modbus proof of concept and test logs/>).

This folder owns **one leg only**: the gateway process, its RTU link to the F4S,
and the scripts that exercise that leg standalone. It was previously named
`codesys-python-tcp-integration/python-gateway/`; the rename to
`python modbus proof of concept and test logs/` reflects what it actually is now that all CODESYS
material lives in its own package.

This is the canonical, only copy of the gateway. Any other `python-gateway/`
folder in older clones or branches is stale — delete it.

> **Signedness (fixed 2026-07-27).** Setpoints and temperatures are **signed**
> ×10 integers in two's complement. The gateway previously range-checked the
> raw *unsigned* word against `0..2000`, so every negative setpoint (−1.0 °C
> arrives as `65526`) was rejected as out-of-range. It now converts to signed
> before validating, against `SP_MIN_X10 = -400 .. SP_MAX_X10 = 2000`, which is
> what this README always claimed. See
> [Range investigation](<../codesys modbus proof of concept and test logs/docs/RANGE_INVESTIGATION.md>).

## Daily Startup Runbook (Read This First)

Two starting conditions, depending on whether the USB-to-RS232 adapter is
still plugged into the Pi from last time. Work through the one that matches
reality, then move on to [CODESYS Integration](#codesys-integration-after-t1-t4-passing).

### Condition A — Adapter already plugged in (normal day)

Use this when the adapter has been sitting in the Pi's USB port since the
last session (the gateway runs as a systemd service, so it also survives Pi
reboots on its own).

1. Visually confirm the USB-to-RS232 adapter is still seated in the Pi and
   the DB9 wiring is still landed on the F4S terminal block (Tx white → 14,
   Rx red → 15, GND black → 16). No physical action needed if it looks fine.
2. On your laptop: launch VS Code.
3. **File → Open Recent** → pick the Remote-SSH workspace for `10.1.6.17`.
4. Enter the SSH password when prompted; wait for VS Code to finish
   attaching to the remote.
5. Open an integrated terminal (``Ctrl+` ``) — you're now on the Pi.
6. Sync the repo:
   ```bash
   cd ~/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
   git fetch origin Omkar_Temperature_Cabinet_Setpoint_Control
   git pull origin Omkar_Temperature_Cabinet_Setpoint_Control
   ```
7. Open this README (`python modbus proof of concept and test logs/README.md`)
   in the VS Code editor so the commands below are one click away.
8. Confirm the serial symlink is present:
   ```bash
   ls -la /dev/ttyWatlowF4S
   ```
9. Confirm the gateway service is already running (`Restart=always` +
   `enable`d, so it should have survived any reboot):
   ```bash
   sudo systemctl status f4s-gateway
   sudo journalctl -u f4s-gateway -n 20
   ```
   Look for `active (running)` and recent `Temp:`/`SP:` log lines. If it's
   not running: `sudo systemctl start f4s-gateway`, then re-check status.
10. Run the full TCP verification — `mbpoll` one-liners or
    `python3 test_rtu_write.py` — see
    [Verify the TCP side](#verify-the-tcp-side--do-this-before-touching-codesys) below.
11. **Visually confirm on the F4S front panel** that the setpoint written in
    step 10 actually shows up (SP1 updates, displayed temperature ramps
    toward it).
12. Only once steps 9–11 all pass, move on to
    [CODESYS Integration](#codesys-integration-after-t1-t4-passing).

### Condition B — Adapter was unplugged (re-plugging it in)

Use this any time the adapter was physically removed (moved benches,
someone unplugged it, new Pi, etc.). This repeats the hardware bring-up
from `linux modbus proof of concept and test logs/README.md` before trusting the gateway again —
don't skip straight to starting the service.

1. Plug the USB-to-RS232 adapter into the Pi.
2. SSH in the same way as Condition A (steps 2–7 above: VS Code → Open
   Recent → SSH to `10.1.6.17` → password → sync repo → open this README).
3. Confirm the OS sees the adapter and note which device node it landed on:
   ```bash
   dmesg | tail -n 20
   # look for: usb ...: pl2303 converter now attached to ttyUSBx
   ```
4. Confirm `/dev/ttyWatlowF4S` resolved to that node. The symlink is
   udev-rule-based, keyed on the adapter's USB ID, so it should auto-attach
   regardless of which `ttyUSBx` number the kernel assigns this time:
   ```bash
   ls -la /dev/ttyWatlowF4S
   ```
   If it's missing or dangling, don't just point the gateway at
   `/dev/ttyUSBx` directly — fix the udev rule/symlink first so future
   replugs keep working unattended.
5. Confirm permissions (`dialout` group) are still correct:
   ```bash
   "./linux modbus proof of concept and test logs/scripts/check-serial-permissions.sh" /dev/ttyWatlowF4S
   ```
6. Physically double-check the DB9 wiring is still seated at the F4S
   terminal block (Tx white → 14, Rx red → 15, GND black → 16) — reseating
   the adapter sometimes tugs the terminal block loose.
7. Baseline the RTU link directly with `mbpoll` *before* trusting the
   gateway, exactly as in `linux modbus proof of concept and test logs/README.md` Part 3:
   ```bash
   mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyWatlowF4S
   # expect a live temperature value matching the F4S front panel
   ```
8. Restart the gateway service so it picks up the fresh serial connection
   immediately instead of waiting on its own restart backoff:
   ```bash
   sudo systemctl restart f4s-gateway
   sudo systemctl status f4s-gateway
   ```
9. Continue from Condition A, step 10 onward — TCP verification → front
   panel confirmation → CODESYS.

**If the adapter re-enumerates while the gateway is already running**
(service was fine, then suddenly `Input/output error` / stuck
`RTU comms timeout` in the logs with no wiring changes) — don't start a
second manual gateway process to "check". Kill any manually-started
`python3 f4s_gateway.py`, then jump straight to step 8 above
(`sudo systemctl restart f4s-gateway`) and step 3 (`ls -la
/dev/ttyWatlowF4S`). See
[troubleshooting #8](#8-gateway-stuck-in-permanent-rtu-comms-timeout-after-the-adapter-re-enumerates)
for the full story.

---

## What this is

A Python process that sits between CODESYS (Modbus TCP master) and a Watlow
F4S temperature cabinet (Modbus RTU slave over `/dev/ttyWatlowF4S`). It is
the **only** process allowed to touch the serial port, and it re-exposes the
cabinet as a 5-register Modbus TCP slave that CODESYS talks to over the
network.

```
CODESYS (TCP master) ──TCP:502──> [this gateway] ──RTU──> Watlow F4S
```

## Register map (Modbus TCP, unit id 1, all values ×10 integers)

| Reg | Name | Direction | Meaning |
|---|---|---|---|
| 0 | `REG_REQ_SP` | CODESYS → gateway | Requested setpoint, e.g. `265` = 26.5°C |
| 1 | `REG_TRIGGER` | CODESYS → gateway | Write `1` to apply; gateway clears to `0` when done |
| 2 | `REG_TEMP` | gateway → CODESYS | Current chamber temperature |
| 3 | `REG_SP_READ` | gateway → CODESYS | Confirmed setpoint (read back from F4S) |
| 4 | `REG_STATUS` | gateway → CODESYS | `0`=OK `2`=WRITE_FAILED `3`=NOT_ACCEPTED `4`=RANGE `5`=COMMS |

Valid setpoint range enforced by the gateway: **-40–200°C (-400–2000 raw,
signed)**. Values are interpreted as signed 16-bit two's complement in both
directions — `65526` on the wire is `-1.0 °C`, not `6552.6 °C`.

The gateway range is **not** the only limit in the chain. The F4S has its own
setpoint low/high limit parameters that no code change can widen; if in-range
writes are refused at the top or bottom, measure the device with
`probe_f4s_limits.py`.

F4S-side RTU registers used: `100` = temperature, `300` = setpoint, slave
address `1`, 19200 baud 8N1.

## Files

- `f4s_gateway.py` — the gateway (RTU cyclic thread + Modbus TCP server)
- `test_rtu_write.py` — **proven 3-test baseline**: read / write-confirm / range-reject.
  Do not modify; regressions here mean the core path broke.
- `test_range_sweep.py` — full −40…200 °C qualification over TCP, including the
  negative setpoints the old unsigned check rejected. Separate from the baseline
  on purpose.
- `probe_f4s_limits.py` — reads the **F4S's own** setpoint limits over RTU.
  Read-only by default; `--sweep --yes` binary-searches the range the device
  actually accepts. Run with the gateway stopped.
- `requirements.txt` — pinned dependencies (see below — **do not casually bump pymodbus**)

## Quick Start

**Always navigate to the gateway folder first:**

```bash
cd "python modbus proof of concept and test logs"
```

All commands below assume you are in this directory.

## Install

From the python modbus proof of concept and test logs directory:

```bash
pip3 install -r requirements.txt --break-system-packages
ls -la /dev/ttyWatlowF4S   # confirm the udev symlink exists
```

`requirements.txt` pins `pymodbus==3.12.1`. This is deliberate, not
arbitrary — see the troubleshooting history below for why 3.13+ silently
breaks the whole gateway.

## Run

From the python modbus proof of concept and test logs directory:

Port 502 needs root, or grant the bind capability once and run as a normal user:

```bash
# option 1: run as root (from python-gateway directory)
sudo python3 f4s_gateway.py

# option 2 (better): grant bind capability, run as user (from python-gateway directory)
sudo setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))
python3 f4s_gateway.py
```

Expected startup log:
```
=== F4S Gateway Starting ===
RTU connected: /dev/ttyWatlowF4S @ 19200
Cyclic task started (period=1.0s)
Starting TCP server on 0.0.0.0:502
TCP server ready on 0.0.0.0:502
```
Followed by `Temp: NN.N°C` / `SP: NN.N°C` debug lines every second — this
confirms the RTU side is alive before you even touch TCP.

Logs are written to `~/.f4s_gateway/f4s_gateway.log`.

## Run permanently (systemd)

**Do not set `User=root` in the service file.** `pip3 install --break-system-packages`
installs into *your user's* site-packages, not root's — a service running as
root will silently resolve a different (unpinned) pymodbus install and fail
with `'ModbusDeviceContext' object has no attribute 'getValues'` even though
everything worked when you ran it manually. Grant the port-502 bind
capability instead and run as your normal user, same as the manual `Run`
step above:

```bash
sudo setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))
sudo nano /etc/systemd/system/f4s-gateway.service
```

```ini
[Unit]
Description=F4S Modbus TCP<->RTU Gateway
After=network.target

[Service]
ExecStart=/usr/bin/python3 "/path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/python modbus proof of concept and test logs/f4s_gateway.py"
Restart=always
User=YOUR_USERNAME
WorkingDirectory="/path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/python modbus proof of concept and test logs"

[Install]
WantedBy=multi-user.target
```

Replace `/path/to/...` with the actual clone path on your machine, and
`YOUR_USERNAME` with the account that ran `pip3 install -r requirements.txt`
(the same one that must already be in the `dialout` group for serial
access).

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now f4s-gateway
sudo systemctl status f4s-gateway
```

## Verify the TCP side — do this before touching CODESYS

From the gateway host or any machine on the network (replace `10.1.6.17`
with the gateway's IP):

```bash
# read temperature (reg2)
mbpoll -m tcp -a 1 -t 4 -r 2 -c 1 -1 -0 10.1.6.17

# request 26.5°C -> reg0 = 265, then apply -> reg1 = 1
mbpoll -m tcp -a 1 -t 4 -r 0 -0 10.1.6.17 265
mbpoll -m tcp -a 1 -t 4 -r 1 -0 10.1.6.17 1

# read back confirmed setpoint (reg3) and status (reg4)
mbpoll -m tcp -a 1 -t 4 -r 3 -c 1 -1 -0 10.1.6.17     # expect 265
mbpoll -m tcp -a 1 -t 4 -r 4 -c 1 -1 -0 10.1.6.17     # expect 0 (OK)
```

Or run the bundled test script, which does all of the above plus an
out-of-range rejection test:

```bash
python3 test_rtu_write.py
```

The F4S must be on its main run page for a write to be accepted — same rule
as for direct serial access. If these all pass, the gateway is proven
correct **independent of CODESYS** — any problem found after this point is
in the CODESYS-side Modbus TCP master configuration, not here.

---

## Troubleshooting history — how we got here

Documented so nobody has to re-derive this. Every one of these was hit, in
this order, while bringing the gateway up.

### 1. Serial port showing 8E1 instead of 8N1
`mbpoll` defaulted to even parity. Fixed by adding `-P none` to the mbpoll
command line when baselining RTU communication before the gateway existed.
Confirmed working reads (24.3°C, 25.0°C) once parity was set to none.

### 2. `ModbusSparseDataBlock` "does not support item assignment"
Early attempt used a shadow array (`tcp_regs`) synced into the datastore
with `hr_block[i] = tcp_regs[i]`. `ModbusSparseDataBlock` doesn't support
`__setitem__`. Silencing the exception "fixed" the crash but broke sync
silently — the real fix was architectural (see #4).

### 3. TCP reads always 0.0°C, write trigger never cleared
Root cause: the shadow array and the real datastore were two different
objects, synced only one direction. TCP client writes landed in the
datastore; the cyclic task checked the shadow array and never saw them.
This is what led to eliminating the shadow array entirely.

### 4. `setValues`/`getValues` missing, then `simdata[i] =` "worked" but didn't
After removing the shadow array, direct calls to `hr_block.setValues()`
raised `AttributeError`. Introspecting the installed pymodbus showed
`ModbusSparseDataBlock` only exposes a `.simdata` list attribute — no
`setValues`/`getValues` at all. Assigning `hr_block.simdata[i] = value`
"worked" in isolation (a standalone Python REPL test read the value back
correctly) but **still failed once wired into the real gateway** — TCP
reads stayed at 0.0°C and the trigger never cleared.

### 5. The real root cause, found by reading pymodbus's own source

This took an actual walk through `pymodbus/datastore/sparse.py` and
`context.py` (pymodbus 3.14.0) plus a controlled bisect across pymodbus
versions 3.9.2 → 3.14.0. Two independent bugs were stacked:

**5a. `ModbusDeviceContext` deepcopies the datablock once, at construction.**
In pymodbus ≥3.13.0, `ModbusSparseDataBlock`/`ModbusDeviceContext` became
thin deprecated shims around the newer SimData/SimDevice engine.
`ModbusDeviceContext.__init__` does:
```python
hr_simdata = deepcopy(hr.simdata)
self.simdevice = SimDevice(0, simdata=(..., hr_simdata, ...))
```
This copy happens **once**, when the server context is built. Any register
written afterward — e.g. from the RTU cyclic thread, which runs in a loop
forever — writes into a dead copy the live TCP server never looks at again.
This is why TCP reads were permanently stuck at the value present at
startup (0), no matter what the cyclic task did.

Confirmed by bisection: `ModbusSparseDataBlock.setValues()` is a real, live,
mutable method through pymodbus 3.12.x, and becomes a stub with no effect
starting at 3.13.0.

**Fix: pin `pymodbus==3.12.1`** (`requirements.txt`) — the last release
where the datastore is held by reference, not deep-copied.

**5b. Address off-by-one between direct block access and protocol access.**
Independent of 5a, and would have caused failures even after downgrading:
`ModbusDeviceContext.getValues(func_code, address, count)` /
`.setValues(...)` add a **`+1`** address offset before delegating to the
raw block — this is pymodbus's normal protocol-facing convention (Modbus
addressing is famously off-by-one in places). Code that pokes the raw
`ModbusSparseDataBlock` directly (as `hr_block.setValues(2, ...)`, no
offset) writes to a different slot than a real TCP request for address 2
resolves to (which becomes `getValues(3, 2, 1)` → block address `3`
internally). Confirmed with a controlled reproduction: writing register 2
directly on the raw block, then reading register 2 over real TCP, returned
0 — because the TCP layer was actually reading offset 3.

**Fix: never touch the raw block from application code.** All register
access — from the RTU cyclic task and anything else — goes through the
same accessor the TCP server itself uses:
```python
device.setValues(3, address, [value])   # 3 = Modbus function code for holding registers
device.getValues(3, address, count)
```
This is what `f4s_gateway.py` does today. `device` (the `ModbusDeviceContext`)
is built once at module scope, before any thread starts, and is the single
shared object both the cyclic thread and the TCP server operate on.

### 6. Verification method

Before trusting this on real hardware again, the fix was proven with a
fully simulated end-to-end test: a mocked RTU backend plus the real
pymodbus 3.12.1 TCP client/server, covering:
- live temperature/setpoint reads reflecting the "RTU" side
- write-with-confirmation: trigger clears, status goes to `0` (OK), confirmed
  setpoint updates on the next poll cycle
- range rejection: an out-of-range write is rejected with status `4`
  (RANGE) and the setpoint is left unchanged

All three passed. The same behavior was then reproduced on the actual
Raspberry Pi against the real F4S (see the log excerpt below) — reads
track the real cabinet temperature, a write to 28.0°C and then 26.5°C both
confirm and clear the trigger, and the log shows the RTU write / read-back
/ status sequence exactly as designed.

```
DEBUG - Temp: 24.8°C
DEBUG - SP: 25.0°C
...
INFO - RTU write: reg300 = 280
INFO - Setpoint write confirmed: 280
INFO - Write SUCCESS: 28.0°C
...
DEBUG - SP: 28.0°C
```

### 7. `AttributeError: 'ModbusDeviceContext' object has no attribute 'getValues'` — only under systemd

Everything passed manually (T1–T4, this file's earlier verification steps),
then the exact same code failed immediately after being wrapped in a
systemd unit with `User=root`, throwing this `AttributeError` on every
cyclic loop iteration, sometimes paired with `[Errno 5] Input/output error`
on the RTU reads.

**Root cause:** `pip3 install -r requirements.txt --break-system-packages`
installs into the invoking *user's* site-packages
(`~/.local/lib/pythonX.Y/site-packages`), not root's. `User=root` in the
service file means systemd's Python resolves a completely different,
unpinned pymodbus install — one where `ModbusDeviceContext` doesn't expose
`getValues` the way 3.12.1 does. `setValues` happened to still resolve
(present under a different name/shim in whichever version root saw), which
made the symptom look asymmetric and confusing. The accompanying I/O errors
were a secondary effect of a leftover manually-started gateway process
still holding `/dev/ttyWatlowF4S` open while the systemd-managed one also
tried to use it.

**Fix:** never run the service as `User=root`. Grant the port-502 bind
capability to `python3` with `setcap` and run the service as the same
non-root user that installed the pinned dependencies (see
[Run permanently (systemd)](#run-permanently-systemd) above). Confirm the
mismatch directly if this recurs:
```bash
sudo python3 -c "import pymodbus; print(pymodbus.__version__, pymodbus.__file__)"
python3 -c "import pymodbus; print(pymodbus.__version__, pymodbus.__file__)"
```
If these print different paths/versions, that's the bug.

### 8. Gateway stuck in permanent `RTU comms timeout` after the adapter re-enumerates

The systemd-managed gateway was running cleanly (`Temp:`/`SP:` logging every
second), then every RTU read started failing with
`[Errno 5] Input/output error`, followed by continuous
`WARNING - RTU comms timeout` — with the physical wiring untouched and the
F4S powered the whole time. Starting a second `python3 f4s_gateway.py` by
hand to "check" made it worse: `[Errno 98] address already in use` on port
502, because two gateway processes were now running at once.

**Root cause:** the USB-to-RS232 adapter re-enumerated (kernel reassigned
it from `/dev/ttyUSB1` to `/dev/ttyUSB0` — confirmed by comparing
`ls -la /dev/ttyWatlowF4S` before and after). `f4s_gateway.py` opens the
serial port once at startup and never reopens it; `read_rtu_reg`/
`write_rtu_reg` catch the resulting I/O error, log it, and just retry the
same dead file descriptor forever — there is no reconnect logic. The
process never crashes (so `Restart=always` never fires), it just spins
uselessly. A second, manually-started instance can still open the *new*
node fine, which is why the two processes disagreed with each other:
the old one was stuck, the new one worked but couldn't bind TCP because
the old one already held port 502.

**Fix — get back to exactly one instance, pointed at the current device
node:**
1. Kill every manually-started `python3 f4s_gateway.py`. Systemd is the
   only thing that should ever run this script:
   ```bash
   pkill -9 -f "python3 f4s_gateway.py"
   ```
2. `sudo systemctl restart f4s-gateway` — this makes the systemd instance
   reopen `/dev/ttyWatlowF4S` fresh, picking up whatever `ttyUSBx` it
   currently points to.
3. `sudo journalctl -u f4s-gateway -n 20 -f` and confirm clean `Temp:`/
   `SP:` lines with no `Input/output error` or `comms timeout` before
   doing anything else.

This is the same failure mode [Condition B in the Daily Startup
Runbook](#condition-b--adapter-was-unplugged-re-plugging-it-in) exists to
prevent for a cold start; this is the same recovery, applied mid-session
when the re-enumeration happens while the service is already running.

**Permanent fix — implemented.** `f4s_gateway.py` now supervises the RTU
link and reopens the port by itself; the manual restart above is only a
fallback if the automatic recovery is ever seen to fail. What it does:

- **Classifies failures.** An `OSError` (errno 5 `Input/output error`,
  including pyserial's `SerialException`) means the file descriptor is dead
  and the port is reopened immediately. A protocol-level failure
  (`isError()`: timeout, bad CRC, exception response) leaves the fd valid,
  so it only increments a counter — reopening on every unanswered poll
  would thrash the port.
- **Threshold backstop.** `RECONNECT_FAIL_THRESHOLD` (3) consecutive
  failures force a reopen even when the port dies without raising.
- **Reopen re-resolves the node.** `connect_rtu()` closes the stale client,
  builds a fresh one, and opens `/dev/ttyWatlowF4S` — the *symlink*, not a
  fixed `ttyUSBx` — so it lands on whatever node the adapter now owns.
- **Backoff.** Retry delay doubles per attempt to `RECONNECT_BACKOFF_MAX`
  (10 s) and is reset only by a genuinely successful read, so a truly
  unplugged cable settles into one quiet retry every 10 s while recovery
  after a re-enumeration is near-instant.
- **Status 5 now clears itself.** Previously `REG_STATUS` was latched to
  `5` (COMMS) and the *only* path back to `0` was a successful write — so
  once it tripped it stayed tripped, and `PLC_PRG` sat in `FAULTED` long
  after comms had recovered. The health check now clears a `5` on the first
  successful read. A real `WRITE_FAILED`/`NOT_ACCEPTED`/`RANGE` code is
  never overwritten.
- **A missing adapter at boot is no longer fatal.** The gateway serves TCP
  regardless, so CODESYS sees status `5` instead of a refused connection,
  and heals the moment the adapter appears.

Net behaviour: **status 5 appears only while the adapter is physically
absent**, and clears on its own within a poll or two of it returning.

Verify after a re-enumeration (or by unplugging the adapter and plugging it
back in):
```bash
sudo journalctl -u f4s-gateway -f
# expect: RTU read I/O error @ reg100: [Errno 5] Input/output error
#         RTU comms timeout — status -> 5 (COMMS)
#         Reopening /dev/ttyWatlowF4S (consecutive failures=3, port_dead=True)
#         /dev/ttyWatlowF4S reopened — awaiting first successful read
#         RTU comms recovered — status 5 -> 0 (OK)
```
If you instead see the reopen line repeating with a growing delay and no
recovery, the adapter genuinely is not enumerating — check the cable and
`ls -la /dev/ttyWatlowF4S`.

## Full T1–T5 Test Plan

### Prerequisites

#### 1. Environment Setup
```bash
python3 --version  # Should be Python 3.10+
pip3 install -r requirements.txt --break-system-packages
pip3 list | grep pymodbus  # Expected: pymodbus 3.12.1
```

**IMPORTANT: pymodbus MUST be pinned to 3.12.1.** Starting in pymodbus 3.13.0,
`ModbusSparseDataBlock`/`ModbusDeviceContext` became deprecated shims around
the new SimData/SimDevice API: `ModbusDeviceContext.__init__` now does a
one-time `deepcopy()` of the datablock into an internal store, so any
register writes made after construction (e.g. from the RTU cyclic thread)
never reach the live TCP-facing storage — TCP reads stay stuck at 0 and
writes never get seen. pymodbus 3.12.1 is the last release where these
classes store the datablock by reference, so runtime mutation actually
works. Do not upgrade past 3.12.1 without re-validating this end-to-end.

#### 2. Verify Serial Port
```bash
ls -la /dev/ttyWatlowF4S
# Expected: /dev/ttyWatlowF4S -> ttyUSB0
```

#### 3. Verify RTU Communication Baseline
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 /dev/ttyWatlowF4S
# Expected: Register 100 value (current temperature x10, e.g., 215 = 21.5°C)

mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 /dev/ttyWatlowF4S
# Expected: Register 300 value (current setpoint x10, e.g., 265 = 26.5°C)
```

---

### T1: Gateway Startup & RTU Layer Verification

**Objective:** Confirm RTU connection works and cyclic polling is active

**Steps:**
1. Terminal 1: Navigate to python modbus proof of concept and test logs folder and start the gateway
   ```bash
   cd "Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/python modbus proof of concept and test logs"
   python3 f4s_gateway.py
   ```
   
   **Expected output:**
   ```
   === F4S Gateway Starting ===
   RTU connected: /dev/ttyWatlowF4S @ 19200
   Cyclic task started (period=1.0s)
   Starting TCP server on 0.0.0.0:502
   TCP server ready on 0.0.0.0:502
   ```

2. Terminal 2: Monitor the log
   ```bash
   tail -f ~/.f4s_gateway/f4s_gateway.log
   ```
   
   **Expected:** See "Temp:" and "SP:" messages every 1 second

**Pass Criteria:**
- ✅ RTU connected successfully
- ✅ Cyclic task started
- ✅ TCP server listening on :502
- ✅ Logs show temperature and setpoint updates every 1s
- ✅ No errors in the log

---

### T2: TCP Register Read (No Write)

**Objective:** Verify TCP clients can read RTU values from gateway

**Steps:**
1. With gateway running (from T1), in Terminal 3:
   ```bash
   python3 -c "
   from pymodbus.client import ModbusTcpClient
   client = ModbusTcpClient(host='localhost', port=502)
   client.connect()
   
   # Read 5 holding registers (indices 0-4)
   result = client.read_holding_registers(address=0, count=5, device_id=1)
   
   print('Holding Registers (0-4):')
   for i, val in enumerate(result.registers):
       print(f'  Reg[{i}]: {val}')
   
   client.close()
   "
   ```
   
   **Expected output:**
   ```
   Holding Registers (0-4):
     Reg[0]: 0         # REG_REQ_SP (requested setpoint, not yet written)
     Reg[1]: 0         # REG_TRIGGER (trigger, not yet set)
     Reg[2]: 225       # REG_TEMP (current temperature = 22.5°C)
     Reg[3]: 250       # REG_SP_READ (current setpoint = 25.0°C)
     Reg[4]: 0         # REG_STATUS (OK)
   ```

**Pass Criteria:**
- ✅ TCP read succeeds (no connection errors)
- ✅ Reg[2] (temperature) shows a non-zero value matching F4S
- ✅ Reg[3] (setpoint) shows a non-zero value matching F4S
- ✅ Reg[4] (status) is 0 (OK)
- ✅ Values match what RTU reads show in the log

---

### T3: TCP Register Write (Setpoint Trigger)

**Objective:** Verify write-trigger mechanism and confirmation

**Steps:**
1. With gateway running, in Terminal 3: Navigate to python modbus proof of concept and test logs folder and run the test
   ```bash
   cd "Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/python modbus proof of concept and test logs"
   python3 test_rtu_write.py
   ```
   
   **Expected output:**
   ```
   F4S RTU Write Test via Modbus TCP
   NOTE: Gateway must be running (python3 f4s_gateway.py)
         Connecting to TCP server on localhost:502...
   ✅ Connected to gateway!
   
   ============================================================
   TEST: Write setpoint 28.0°C
   ============================================================
   
   Before write:
     Current temp:      22.5°C
     Current setpoint:  25.0°C
     Status:            0
   
   Setting write trigger:
     Writing REG_REQ_SP (0):  280 = 28.0°C
     Writing REG_TRIGGER (1):   1 (request sent)
   
   Waiting for gateway to process write...
   
   After write:
     REG_TRIGGER (1):   0 (cleared=True)
     REG_STATUS (4):    0 (0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS)
     Current setpoint:  28.0°C (read from F4S)
     Current temp:      22.5°C
   
   ✅ SUCCESS: Setpoint write confirmed!
   ```

2. Check the log for write operations:
   ```bash
   tail -50 ~/.f4s_gateway/f4s_gateway.log | grep -E "(Write|write|Setpoint)"
   ```
   
   **Expected:**
   ```
   INFO - RTU write: reg300 = 280
   INFO - Setpoint write confirmed: 280
   INFO - Write SUCCESS: 28.0°C
   ```

**Pass Criteria:**
- ✅ Write trigger accepted
- ✅ Trigger cleared after processing
- ✅ Status = 0 (OK)
- ✅ Read-back shows new setpoint
- ✅ Log shows RTU write and confirmation

---

### T4: Range Validation (Out-of-Range Write)

**Objective:** Verify range check (-40-200°C = -400-2000 x10)

**Steps:**
1. With gateway running, write an out-of-range value:
   ```bash
   python3 -c "
   from pymodbus.client import ModbusTcpClient
   client = ModbusTcpClient(host='localhost', port=502)
   client.connect()
   
   # Write out-of-range: 250°C = 2500 x10 (valid range: 0-2000)
   client.write_register(address=0, value=2500, device_id=1)
   client.write_register(address=1, value=1, device_id=1)
   
   import time
   time.sleep(1)  # Wait for gateway to process
   
   # Read status
   result = client.read_holding_registers(address=4, count=1, device_id=1)
   status = result.registers[0]
   
   print(f'Status after out-of-range write: {status}')
   print(f'  0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS')
   
   client.close()
   "
   ```
   
   **Expected:**
   ```
   Status after out-of-range write: 4
     0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS
   ```

2. Check the log:
   ```bash
   tail -20 ~/.f4s_gateway/f4s_gateway.log | grep -i range
   ```
   
   **Expected:**
   ```
   WARNING - Out of range: 250.0°C
   ```

**Pass Criteria:**
- ✅ Status = 4 (RANGE error)
- ✅ Log shows range validation warning
- ✅ F4S setpoint unchanged (remains at previous value)

---

### T5: Communications Timeout (Optional, Advanced)

**Objective:** Verify comms health check

**Steps:**
1. With gateway running, manually disconnect the F4S serial cable
2. Wait 5+ seconds (the timeout threshold)
3. Read status:
   ```bash
   python3 -c "
   from pymodbus.client import ModbusTcpClient
   client = ModbusTcpClient(host='localhost', port=502)
   client.connect()
   
   result = client.read_holding_registers(address=4, count=1, device_id=1)
   status = result.registers[0]
   
   print(f'Status after comms timeout: {status}')
   print(f'  0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS')
   
   client.close()
   "
   ```
   
   **Expected:**
   ```
   Status after comms timeout: 5
     0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS
   ```

4. Reconnect the serial cable and wait 1s for recovery

**Pass Criteria:**
- ✅ Status = 5 (COMMS timeout)
- ✅ Recovers after cable reconnected
- ✅ No crashes, graceful degradation

---

## CODESYS Integration

**Moved.** Everything CODESYS-side — device tree, Modbus TCP master/slave
setup, channel table, I/O mapping, GVL definitions, watch-window procedure —
now lives in its own package:

> **[`../codesys modbus proof of concept and test logs/README.md`](<../codesys modbus proof of concept and test logs/README.md>)**

This folder is now the **Python/RTU side only**: the gateway service, its RTU
link to the Watlow F4S, and the scripts that test that leg in isolation. The
split reflects the actual architecture — the gateway owns the serial port and
CODESYS never touches it.

---

## Systemd Service Setup

See [Run permanently (systemd)](#run-permanently-systemd) above for the
unit file and setup steps. **Do not use `User=root`** — see
[troubleshooting #7](#7-attributeerror-modbusdevicecontext-object-has-no-attribute-getvalues--only-under-systemd)
for why that breaks the gateway even though the code is correct.

Verify status and logs:

```bash
sudo systemctl status f4s-gateway
sudo journalctl -u f4s-gateway -f
```

---

## What's Left Before Full Deployment

Nothing on the Python side. The gateway is proven independent of CODESYS
via the `mbpoll`/`test_rtu_write.py` verification above (T1-T4). The next step is
configuring the CODESYS Modbus TCP master to point at this gateway's IP:502
and map the 5 registers per the table at the top of this file — that work
is documented in the CODESYS Integration section above.
