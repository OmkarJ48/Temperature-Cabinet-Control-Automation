# Raspberry Pi (Modbus Master) ↔ CODESYS ↔ Watlow F4S (Modbus Slave)

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Applies to:** CODESYS runtime on the Raspberry Pi hosting the DLS008 sandbox project, reached over SSH at **10.1.6.17**
**Target:** Watlow F4S (SN 038983), Modbus RTU over the USB-to-RS232 adapter on `/dev/ttyUSB0`
**Covers:** Step 5 of the integration sequence in the root `README.md`

This folder covers CODESYS itself — runtime configuration, the Modbus device tree, driver
timing, and the write channel. It assumes the serial link has **already been proven
independently with `mbpoll`** (see `linux-integration/README.md` §4, including both the register
100 read and the register 300 read/write) — do not start here if that hasn't passed yet.
Debugging a CODESYS Modbus error before the raw link is proven means debugging two unknowns at
once.

**Roles in this link:** the Raspberry Pi's CODESYS runtime is the **Modbus master** (it initiates
every request); the Watlow F4S is the **Modbus slave** (it only ever responds). There is exactly
one master and one slave on this RS-232 link — CODESYS does not act as a slave to anything here.

For importing the actual ST program (`FB_CabinetSetpointControl`, `PLC_PRG`) into the sandbox
project, see `docs/DEPLOYMENT_AND_TEST.md` — this folder is about the *transport* layer
underneath that code, not the application logic itself.

---

## Register map (recap — full detail in `linux-integration/README.md` §4.1/§4.1a/§4.1b)

| Register | Name | Access | Why |
|---|---|---|---|
| **100** | Input 1 Value (actual chamber temperature) | **Read-only** (FC03) | Live sensor measurement — Watlow's own Modbus map defines no write path for it. Writing it would only make the display lie without changing the physical temperature; never build a write channel against register 100. |
| **300** | Set Point 1 / "SP1" (static setpoint) | **Read/Write** (FC03 read, FC06 write) | The only register that actually influences chamber temperature — the F4S ramps register 100 toward whatever is written here, via its own closed-loop PID. |

Both carry **one implied decimal place** (`500` raw = `50.0°C`), confirmed identically on both
registers via `mbpoll`.

---

## Step 1: Release the port before touching CODESYS config

`/dev/ttyUSB0` can only be held open by **one process at a time**. Before editing any CODESYS
configuration, make sure nothing is still holding the port from bench-testing:

```bash
sudo lsof /dev/ttyUSB0        # or: sudo fuser -v /dev/ttyUSB0
```

Kill/close anything listed (typically a leftover `mbpoll` session), then stop the runtime
cleanly so the steps below start from a known state:

```bash
sudo systemctl stop codesyscontrol
```

(It's fine if this reports the service was already stopped — the point is ensuring it isn't
holding the port while you edit its config in Steps 2–3 below.)

---

## Step 2: Configure Linux udev permissions (permanent, survives reboot)

`sudo chmod 666` (from `linux-integration/README.md` §3) is a **temporary** fix that resets on
every replug/reboot. To stop CODESYS hitting Read/Write lock ("red triangle") errors after every
reboot, add a udev rule so the kernel grants the permission automatically, every time:

```bash
sudo nano /etc/udev/rules.d/99-usb-serial.rules
```

Add:

```
KERNEL=="ttyUSB[0-9]*", MODE="0666"
```

Reload:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

> This grants world read/write on any `ttyUSB*` node, which is a broader (less strict) grant
> than the `dialout`-group approach in `linux-integration/README.md` §3 Option B. Either is fine
> for this single-purpose sandbox Pi; the udev rule is simpler to reason about for an
> **unattended runtime service** (CODESYS) specifically, since it doesn't depend on which user
> account the `codesyscontrol` service happens to run as.

---

## Step 3: Map the port to CODESYS SysCom, with the baud rate locked

```bash
sudo nano /etc/CODESYSControl_User.cfg
```

Add (or confirm) at the bottom:

```ini
[SysCom]
Linux.Devicefile.1=/dev/ttyUSB0
portnum.1=1
baudrate.1=19200
```

A ready-to-copy version of this snippet is at
[`codesyscontrol-user-snippet.cfg`](codesyscontrol-user-snippet.cfg).

`baudrate.1=19200` locks the runtime-level baud so it can't silently drift from the confirmed
setting (see `linux-integration/README.md` §4.1a for why this line matters — a manual `mbpoll`
test at the wrong baud rate has already produced one false-positive read on this hardware, so
don't leave this to the IDE-side setting alone).

Start the runtime (it was stopped in Step 1):

```bash
sudo systemctl start codesyscontrol
```

If this errors with "unit not found," confirm the actual service name first:

```bash
systemctl list-units | grep -i codesys
```

---

## Step 4: CODESYS Modbus driver configuration (IDE)

From your laptop, connected to this same Pi, in the CODESYS project's device tree:

```
Application
├── Modbus_COM (Modbus COM)
│   └── Modbus_Client_COM_Port   ← Master. Never add a Modbus_server_COM_Port here —
│       │                          a server (slave) device on this same port causes a
│       │                          port collision; the F4S is the only slave on this link.
│       ├── [FC03 Read channel  — register 100]
│       └── [FC06 Write channel — register 300, see Step 5]
```

Set the `Modbus_COM` device's serial port properties to match what's proven with `mbpoll`:

| Parameter | Confirmed value |
|---|---|
| Port | **COM1** (matches `portnum.1=1` in the `.cfg` above) |
| Baud Rate | **19200** |
| Parity | **None** |
| Data Bits | **8** |
| Stop Bits | **1** |
| Transmission Mode | **RTU** |
| Slave Address | **1** |

**Driver timing** — set these on `Modbus_Client_COM_Port` to mirror `mbpoll`'s own spacing and
avoid an internal buffer overrun (CODESYS Modbus error code 255, seen when the driver reuses the
line before the F4S has finished its turnaround):

| Parameter | Value |
|---|---|
| Response Timeout | **1000 ms** |
| Time between frames | **50 ms** |

**Task binding** — assign the Modbus Client's bus cycle to **`MainTask`** specifically, not a
secondary/background task. A starved background task is a common cause of intermittent,
hard-to-reproduce comms drops that look like a wiring problem but aren't.

### Channel addressing — 0-based, confirmed on hardware

`mbpoll` required the `-0` flag for correct reads (`linux-integration/README.md` §4.1), meaning
the register numbers used everywhere in this repo (100, 300) are the **raw PDU addresses**.
**Set the CODESYS channel Offset field directly to the register number** — `100` for the read
channel, `300` for the write channel — **not** `99`/`299`.

---

## Step 5: Modbus write channel (FC06) — the setpoint, and only the setpoint

Build the write channel to replicate exactly what was proven manually with
`mbpoll -m rtu -a 1 -b 19200 -P none -0 -r 300 /dev/ttyUSB0 <raw_value>`
(`linux-integration/README.md` §4.1b):

1. Under `Modbus_Client_COM_Port`, add a **write channel**, **Function Code 06**, **Offset
   `300`** (decimal; `16#012C` in hex, same register — 0-based/PDU per above).
2. Set the channel **Trigger to `Application`, not `Cyclic`.** A cyclic write would hammer
   register 300 (which lives in the F4S's EEPROM) on every bus cycle, causing exactly the
   unnecessary write-wear the edge-triggered design in `FB_CabinetSetpointControl.st` exists to
   avoid. Application-triggered means the write only fires when the ST program actually asks for
   one — the FB's own rising-edge logic controls *when*, this channel just provides *how*.
3. Map the channel to a local variable, e.g. `Application.PLC_PRG.Target_Watlow_Temp` (or wire it
   directly to the FB instance's write-coupling variable — see `iWriteSP_raw` /
   `xWriteTrigger` in `src/POUs/FB_CabinetSetpointControl.st`).
4. The HMI "Set" button pushes the operator's requested value into this variable and fires the
   trigger — reproducing the exact terminal write proven in `linux-integration/README.md` §4.1b,
   now driven from the WebVisu instead of a manual command.

**Never build an equivalent channel against register 100.** There is no scenario where writing
the process-value register is correct — see the register-map table above and
`linux-integration/README.md` §4.1b for the full reasoning.

### Confirming a write — three outcomes, and which ones CODESYS can catch automatically

The manual `mbpoll` testing in `linux-integration/README.md` §4.1b surfaced three distinct
outcomes that this write channel inherits:

| Outcome | Terminal/CODESYS signal | Detectable in software? |
|---|---|---|
| Write accepted, F4S changes | FC06 ack + register 300 read-back matches | **Yes** — this is exactly what `FB_CabinetSetpointControl.st`'s `CONFIRM` state checks (read register 300 back, compare to the requested value) |
| F4S on a Function/menu page, write acked but has no visible effect | FC06 ack — **identical to the success case** | **Not from the Modbus transaction alone.** The FB's read-back confirmation checks that the *register* holds the new value, not that the *front panel* is on the right page — if the F4S's own firmware still updates the register even while a menu is open, the FB will report `CONFIRMED` while the display doesn't visibly change until the operator returns to the Main Page. Treat an operator report of "confirmed but no visible change" as a front-panel-state issue, not a comms fault |
| Adapter disconnected | Timeout / no response, driver reports a comms error | **Yes** — this is what the FB's comms watchdog and `WRITE_FAILED`/timeout fault codes are for |

Build 2 of 3 outcomes should be caught automatically once this channel and the FB are both wired
up; the middle case is a physical-inspection item to note in the operator procedure, not
something the driver can detect over Modbus.

---

## Build, deploy, and clear the red triangles

```
Build → Clean All
Build → Build
(Login to the Pi's runtime)
Run
```

**Troubleshooting red triangles / driver errors after deploy:**

| Symptom | Likely cause | Fix |
|---|---|---|
| No data on **any** channel, but `mbpoll` proved the link independently | **Port already held open by another process** | Re-run Step 1 (`lsof`/`fuser`, then restart the runtime). Most common cause of "mbpoll works, CODESYS doesn't." |
| Red triangle on `Modbus_Client_COM_Port` immediately after login | Port mismatch — `.cfg` device file doesn't match the physical adapter | Re-check `ls /dev/ttyUSB*` on the Pi; re-confirm `Linux.Devicefile.1=/dev/ttyUSB0` |
| Red triangle persists, `mbpoll` bench-test passes standalone | Parity/baud/stop-bit mismatch in CODESYS `Modbus_COM` properties | Re-verify all serial parameters against Step 4 — CODESYS does not inherit `mbpoll`'s settings |
| Internal buffer error / Modbus error code 255 | Driver reusing the line before the F4S's turnaround completes | Confirm Response Timeout `1000 ms` / Time between frames `50 ms` per Step 4 |
| Read channel off by one register | Channel offset convention mismatch (1-based vs required 0-based) | Set Offset to the register number directly, per Step 4 |
| Write channel refused or has no effect, and register 300 read-back also doesn't move | F4S in profile/ramp mode, not static setpoint mode | Confirm F4S is in **static/manual setpoint mode** — a running profile owns SP1 |
| Write channel accepted, FB reports `CONFIRMED`, but front panel doesn't visibly change | F4S was on a Function/menu page, not the Main Page — see Step 5 table above | Visual check only; return the front panel to the Main Page |
| Everything green, but HMI shows the wrong tile updating | GVL/HMI tag mapping error, not a comms problem | Check `src/GVLs/GVL_HMI.gvl` and `src/POUs/PLC_PRG.st` wiring, not this folder |

---

## Order of operations reminder

This folder assumes:
1. The USB-to-RS232 adapter is plugged in and identified (`linux-integration/README.md`, Step 2).
2. Serial port permissions are granted (`linux-integration/README.md`, Step 3).
3. `mbpoll` has proven the raw Modbus link **independently of CODESYS** — both the register 100
   read and the register 300 read/write (`linux-integration/README.md`, Step 4).

Only then do this folder's Steps 1–5 apply. See the root `README.md`'s "Linux ↔ Raspberry Pi ↔
CODESYS ↔ GitHub" section for the full six-step sequence.
