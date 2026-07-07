# CODESYS Runtime & Device Configuration

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Applies to:** CODESYS runtime on the Raspberry Pi hosting the DLS008 sandbox project, reached over SSH at **10.1.6.17**
**Target:** Watlow F4S (SN 038983), Modbus RTU over the USB-to-RS232 adapter on `/dev/ttyUSB0`
**Covers:** Step 5 of the integration sequence in the root `README.md`

This folder covers CODESYS itself — runtime configuration, the Modbus device tree, and channel
addressing. It assumes the serial link has **already been proven independently with `mbpoll`**
(see `linux-integration/README.md`) — do not start here if that hasn't passed yet. Debugging a
CODESYS Modbus error before the raw link is proven means debugging two unknowns at once.

For importing the actual ST program (`FB_CabinetSetpointControl`, `PLC_PRG`) into the sandbox
project, see `docs/DEPLOYMENT_AND_TEST.md` — this folder is about the *transport* layer
underneath that code, not the application logic itself.

---

## Step 5: Map the verified port into the CODESYS runtime

Once `mbpoll` reads cleanly and repeatably (run it two or three times, not just once — see the
Rebuild → Retest → Requalify → Repeat discipline in `docs/DEPLOYMENT_AND_TEST.md` §5):

### 5.1 Map the device file at the runtime level

```bash
sudo nano /etc/CODESYSControl_User.cfg
```

Add (or confirm) at the bottom:

```ini
[SysCom]
Linux.Devicefile.1=/dev/ttyUSB0
portnum.1=1
```

A ready-to-copy version of this snippet is at
[`codesyscontrol-user-snippet.cfg`](codesyscontrol-user-snippet.cfg).

Restart the runtime so it picks up the mapping:

```bash
sudo systemctl restart codesyscontrol
```

If this errors with "unit not found," confirm the actual service name first:

```bash
systemctl list-units | grep -i codesys
```

### 5.2 Configure the Modbus Serial Master device (CODESYS IDE)

From your laptop, connected to this same Pi, in the CODESYS project's device tree:

```
Application
├── Modbus_COM (Modbus COM)
│   ├── Modbus_Client_COM_Port
│   │   ├── [FC03 Read channel — register 100]
│   │   └── [FC06 Write channel — register 300]
│   └── Modbus_server_COM_Port
```

Set the `Modbus_COM` device's serial port properties to match what was confirmed on the F4S
front panel and proven with `mbpoll`:

| Parameter | Confirmed value |
|---|---|
| Port | **COM1** (matches `portnum.1=1` in the `.cfg` above — this is what links CODESYS's visible "COM1" to the real `/dev/ttyUSB0`) |
| Baud Rate | **19200** |
| Parity | **None** |
| Data Bits | **8** |
| Stop Bits | **1** |
| Transmission Mode | **RTU** |
| Slave Address | **1** |

**How to set/verify parity specifically** (a common source of red triangles even after
`mbpoll` succeeds, if this step is skipped):

1. Right-click **Modbus_COM** in the device tree → **Properties**/**Edit**.
2. Navigate to the **Serial Port** / **Communication** tab.
3. Set **Parity → None** (matches the F4S's 8N1 configuration).
4. Click OK, then **Build → Build**, download to the Pi, restart the runtime.

### 5.3 Channel addressing — 0-based, confirmed on hardware

The bench-test on `linux-integration/` proved that this link uses **0-based (PDU) register
addressing** — `mbpoll` required the `-0` flag for correct reads, meaning the register numbers
documented everywhere in this repo (100, 300) are the **raw PDU addresses**, not 1-based
(Modicon-convention) addresses that would need a `-1` offset.

**In CODESYS, set the channel Offset field directly to the register number** — `100` for the
read channel, `300` for the write channel — **not** `99`/`299`. If a channel is built expecting
1-based addressing by default, verify against a live read once mapped: the CODESYS-displayed
value must match the F4S front-panel display, and if it's consistently off by one register, the
offset convention is the first thing to check.

### 5.4 Build, deploy, and clear the red triangles

```
Build → Clean All
Build → Build
(Login to the Pi's runtime)
Run
```

**Troubleshooting red triangles after deploy:**

| Symptom | Likely cause | Fix |
|---|---|---|
| Red triangle on `Modbus_Client_COM_Port` immediately after login | Port mismatch — `/etc/CODESYSControl_User.cfg` device file doesn't match the physical adapter | Re-check `ls /dev/ttyUSB*` on the Pi; re-confirm `Linux.Devicefile.1=/dev/ttyUSB0` matches |
| Red triangle persists, `mbpoll` bench-test passes standalone | Parity/baud/stop-bit mismatch in the CODESYS `Modbus_COM` properties | Re-verify all serial parameters against §5.2 above — CODESYS does not inherit `mbpoll`'s settings, they're configured independently |
| Read channel shows a value, but off by one register (e.g. reads register 99's value under a "100" label) | Channel offset convention mismatch (1-based default vs required 0-based) | See §5.3 — set Offset to the register number directly |
| Write channel (register 300, FC06) refused or has no effect | F4S in profile/ramp mode, not static setpoint mode | Confirm F4S is in **static/manual setpoint mode** — see root README open items; a running profile owns SP1 |
| Everything green, but HMI shows the wrong tile updating | GVL/HMI tag mapping error, not a comms problem | Check `src/GVLs/GVL_HMI.gvl` and `src/POUs/PLC_PRG.st` wiring, not this folder |

---

## Order of operations reminder

This folder assumes:
1. The USB-to-RS232 adapter is plugged in and identified (`linux-integration/README.md`, Step 2).
2. Serial port permissions are granted (`linux-integration/README.md`, Step 3).
3. `mbpoll` has proven the raw Modbus link **independently of CODESYS** (`linux-integration/README.md`, Step 4).

Only then does this folder's Step 5 apply. See the root `README.md`'s "Linux ↔ Raspberry Pi ↔
CODESYS ↔ GitHub" section for the full six-step sequence.
