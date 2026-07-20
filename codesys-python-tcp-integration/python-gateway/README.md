# F4S Modbus TCP↔RTU Gateway

**Status: ✅ Proven working end-to-end on hardware.** Reads, writes-with-confirmation,
and range-validation all verified over real Modbus TCP against a real Watlow F4S.
Next step is CODESYS integration (not started).

This is the canonical, only copy of the gateway. Any other `python-gateway/`
folder in older clones or branches is stale — delete it.

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

Valid setpoint range enforced by the gateway: 0–200°C (0–2000 raw).

F4S-side RTU registers used: `100` = temperature, `300` = setpoint, slave
address `1`, 19200 baud 8N1.

## Files

- `f4s_gateway.py` — the gateway (RTU cyclic thread + Modbus TCP server)
- `test_rtu_write.py` — TCP client script exercising read / write-confirm / range-reject
- `requirements.txt` — pinned dependencies (see below — **do not casually bump pymodbus**)

## Install

```bash
cd codesys-python-tcp-integration/python-gateway
pip3 install -r requirements.txt --break-system-packages
ls -la /dev/ttyWatlowF4S   # confirm the udev symlink exists
```

`requirements.txt` pins `pymodbus==3.12.1`. This is deliberate, not
arbitrary — see the troubleshooting history below for why 3.13+ silently
breaks the whole gateway.

## Run

Port 502 needs root, or grant the bind capability once and run as a normal user:

```bash
# option 1: run as root
sudo python3 f4s_gateway.py

# option 2 (better): grant bind capability, run as user
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

```bash
sudo nano /etc/systemd/system/f4s-gateway.service
```

```ini
[Unit]
Description=F4S Modbus TCP<->RTU Gateway
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway/f4s_gateway.py
Restart=always
User=root
WorkingDirectory=/path/to/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/codesys-python-tcp-integration/python-gateway

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now f4s-gateway
sudo systemctl status f4s-gateway
```

Replace `/path/to/...` with the actual clone path on your machine.

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

## What's left before CODESYS

Nothing on the Python side. The gateway is proven independent of CODESYS
via the `mbpoll`/`test_rtu_write.py` verification above. The next step is
configuring the CODESYS Modbus TCP master to point at this gateway's IP:502
and map the 5 registers per the table at the top of this file — that work
has not started yet.
