# Linux ↔ Raspberry Pi ↔ CODESYS ↔ GitHub — Remote SSH Integration Guide

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Applies to:** Raspberry Pi hosting the CODESYS sandbox project for the **Left Hand Small Temperature Cabinet** (DLS008 panel), reached over SSH at **10.1.6.17**
**Target:** Watlow F4S (SN 038983), Modbus RTU over the USB-to-RS232 adapter on `/dev/ttyUSB0`

This is the companion guide to `docs/DEPLOYMENT_AND_TEST.md`. That document covers importing
the ST code into the CODESYS project itself; this one covers everything **below** CODESYS —
the Linux host, the serial hardware, and the GitHub workflow that ties the Pi back to this
repo. Read this first if you are new to doing PLC work from a Linux terminal instead of
Windows/COM ports.

---

## 0. Why this is different from Windows

| Windows habit | Linux equivalent | Where it shows up here |
|---|---|---|
| `COM3`, `COM4`, … | `/dev/ttyUSB0`, `/dev/ttyACM0`, … — a device *file*, not a port name | Step 2 |
| Ports "just work" for any user | Serial devices are permission-gated (`crw-rw----`, group `dialout`) | Step 3 |
| QModMaster / Modbus Poll (GUI) | `mbpoll` (CLI) — same bench-test role, no GUI needed | Step 4 |
| Editing files locally, then FTP/copy to the PLC | VS Code **Remote-SSH** edits the Pi's filesystem directly; Git push/pull happens from the same remote window | Step 6 |
| CODESYS Windows runtime config (GUI dialog) | `/etc/CODESYSControl_User.cfg` (plain text) | Step 5 |

---

## 1. Connect to the Pi from VS Code (Remote-SSH)

1. Install the **Remote - SSH** extension in VS Code (once, on your laptop).
2. `Ctrl+Shift+P` → **Remote-SSH: Connect to Host…** → enter:
   ```
   mechatronics@10.1.6.17
   ```
3. VS Code re-opens with its terminal, file explorer, and extensions all running **on the Pi**,
   not your laptop. Everything from here on (dmesg, apt-get, git, nano) executes on the Pi.
4. Open the folder `~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI` (or wherever
   the repo is cloned) via **File → Open Folder**. This is the same repo as
   `github.com/OJ4884/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI`, branch
   `OJ4884-patch-1` — VS Code's Source Control panel talks to GitHub exactly like it would
   locally, it's just physically running on the Pi.

---

## 2. Identify the serial adapter

Plug the USB-to-RS232 adapter into a free USB port on the active Pi, then:

```bash
dmesg | tail -n 20
```

Look for the attach line — on this hardware it's a Prolific PL2303-based adapter:

```
usb 1-2: pl2303 converter detected
usb 1-2: pl2303 converter now attached to ttyUSB0
```

`ttyUSB0` → the device file is **`/dev/ttyUSB0`**. This is what goes into both `mbpoll -1 …`
and the CODESYS Modbus device tree — there is no separate "Linux COM port" name to translate.

> Re-plugging the adapter (or a power cycle) can reassign it to `ttyUSB1` if something else
> claims `ttyUSB0` first. Always re-check `dmesg | tail` after a reconnect rather than assuming.

---

## 3. Grant port permissions

Serial devices on Debian/Raspberry Pi OS are owned by `root:dialout` with group-only access.
A one-off fix for bench testing:

```bash
sudo chmod 666 /dev/ttyUSB0
```

This does not survive a reboot or re-plug. The permanent fix is to add your user to the
`dialout` group once:

```bash
sudo usermod -aG dialout $USER
# then log out / re-open the SSH session for the group change to take effect
```

CODESYS's own runtime process needs the same access — if the runtime is not running as
`root`, add its service user to `dialout` too, otherwise the Modbus device in CODESYS will
silently show "no response" even though `mbpoll` works fine from your own shell.

---

## 4. Bench-test the link with `mbpoll` (before touching CODESYS)

Install once:

```bash
sudo apt-get update
sudo apt-get install mbpoll
```

### 4.1 Known-good command for this cabinet

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -s 1 -d 8 -t 4 -r 100 -c 1 -1 /dev/ttyUSB0
```

| Flag | Meaning | Value used here |
|---|---|---|
| `-m rtu` | Modbus RTU (not ASCII/TCP) | — |
| `-a 1` | Slave address | `1` (F4S default) |
| `-b 19200` | Baud rate | **19200** — see the baud-rate note below |
| `-P none` | Parity | **None** — do not rely on the mbpoll default |
| `-s 1` | Stop bits | `1` |
| `-d 8` | Data bits | `8` (8N1 overall) |
| `-t 4` | Register type | 16-bit holding register (FC03 read / FC06 write family) |
| `-r 100` | Start register | `100` = Input 1 Value (actual chamber temp) |
| `-c 1` | Register count | `1` |
| `-1` | Poll once, then exit | — |

### 4.2 Why the first attempt timed out

The very first run you did omitted `-P`, and the tool's own banner shows why it failed:

```
Communication.........: /dev/ttyUSB0,      19200-8E1
```

**`mbpoll` defaults to Even parity (8E1) when `-P` is not given.** The F4S in this project is
configured **8N1 (no parity)** — see `docs/DEPLOYMENT_AND_TEST.md` §3 and the confirmed F4S
comms settings in the root `README.md`. Talking 8E1 to an 8N1 device is a framing mismatch at
the wire-protocol level — the F4S never recognizes a valid frame, so every request just times
out. This is not a wiring or hardware fault; it is purely a missing `-P none`.

Your second attempt correctly added `-P none`, which the banner confirms (`19200-8N1`). If that
run still times out, work through the checklist below before suspecting the code:

| Symptom | Likely cause | Check |
|---|---|---|
| Timeout with default 8E1 shown in banner | Parity mismatch (see above) | Add `-P none` |
| Timeout even with `-P none` / `8N1` confirmed | Wrong baud rate | See §4.3 — README and DEPLOYMENT_AND_TEST disagree; confirm on the F4S front panel: **Setup → Communications → Baud Rate** |
| Timeout persists at correct baud/parity | Permissions | Re-check `ls -l /dev/ttyUSB0` — should be `crw-rw-rw-` after `chmod 666`, or your user in `dialout` |
| Timeout persists, permissions OK | Wrong slave address | F4S defaults vary: 1, 247, or 255 — read it off the front panel, don't assume `-a 1` |
| Garbage/CRC error instead of timeout | Wiring TX/RX swapped, or adapter on wrong `/dev/ttyUSB*` after a re-plug | Re-check `dmesg \| tail` for the current device node |
| Works for register 100 (read) but register 300 write (FC06) is refused | F4S in profile/ramp mode, not static setpoint mode | Confirm F4S is in **static/manual setpoint mode** — see root README "Recommended path" §, open item — a running profile owns SP1 |

### 4.3 Baud rate — resolved, but don't assume it stays that way

The root `README.md`'s original Phase 2→3 section recorded the F4S baud rate as **9600 bps**
from an earlier front-panel photo, while `docs/DEPLOYMENT_AND_TEST.md` and the live `mbpoll`
testing in this session used **19200**. This has since been resolved: the F4S front panel was
physically changed to **19200** to match the CODESYS `Modbus_COM` device config (see root
README, "Baud-rate synchronization — RESOLVED"). The 9600 figure in the earlier section is now
stale history, not a live discrepancy.

The lesson still applies going forward: if a bench test times out cleanly (no data, no CRC
error) even with parity fixed, re-read the baud rate off the F4S front panel
(`Setup → Communications → Baud Rate`) rather than trusting either document — a baud mismatch
produces the exact same "clean timeout" symptom as the parity mismatch in §4.2, and the two are
easy to conflate when debugging.

### 4.4 A note on the `-0` flag

`mbpoll -0` switches addressing from 1-based (Modicon convention, the default) to 0-based (raw
PDU convention) — it shifts every register reference down by one. Only add `-0` if you have
confirmed the F4S's documented register numbers (100, 300) are already 0-based PDU addresses
rather than the 1-based convention `mbpoll` assumes by default. Adding it speculatively when
troubleshooting a timeout will not fix a parity/baud/permission problem and will instead have
you silently reading/writing the *wrong* register (99 or 299) once the link is otherwise
working. Resolve parity, baud, and permissions first; only revisit `-0` if a *successful* read
returns a value that doesn't match the F4S front-panel display.

A helper script wrapping the known-good command is at
[`scripts/bench-test-modbus.sh`](scripts/bench-test-modbus.sh).

### Expected result

```
[100]: 1400
```

(or whatever raw value corresponds to the current front-panel temperature ×10). Once this
matches the F4S display within rounding, the OS + hardware layer is proven — everything above
this point is now CODESYS's problem, not Linux's.

---

## 5. Map the verified port into the CODESYS runtime

Once `mbpoll` reads cleanly and repeatably (run it two or three times, not just once — see the
Rebuild → Retest → Requalify → Repeat discipline in `docs/DEPLOYMENT_AND_TEST.md` §5):

```bash
sudo nano /etc/CODESYSControl_User.cfg
```

Add (or confirm) at the bottom:

```ini
[SysCom]
Linux.Devicefile.1=/dev/ttyUSB0
portnum.1=1
```

Restart the runtime so it picks up the mapping:

```bash
sudo systemctl restart codesyscontrol
```

A ready-to-copy version of this snippet is at
[`codesyscontrol-user-snippet.cfg`](codesyscontrol-user-snippet.cfg).

In the CODESYS IDE (on your laptop, connected to this same Pi), configure the Modbus Serial
Master device on **COM1** (matching `portnum.1=1`), with the baud/parity/slave settings
confirmed in Step 4 — not assumed from either doc until you've read them off the F4S panel.

---

## 6. GitHub workflow from the Pi (VS Code Remote-SSH)

Because VS Code's Remote-SSH session is running the Source Control panel *on the Pi*, working
with this repo from `10.1.6.17` is the same Git workflow as any other clone — there is nothing
Pi-specific about it beyond where the files physically live:

```bash
cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
git status
git fetch origin OJ4884-patch-1
git pull origin OJ4884-patch-1
```

Stage and commit new files (ST code, docs, this guide, etc.) the normal way, either via the
VS Code Source Control UI or:

```bash
git add <files>
git commit -m "…"
git push -u origin OJ4884-patch-1
```

If the repo isn't cloned yet on a fresh Pi:

```bash
git clone -b OJ4884-patch-1 https://github.com/OJ4884/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI.git
```

This is how the `.html`, `.md`, `.dut`, `.gvl`, `.xml`, and `.st` files already in this repo
arrived — authored/edited through this same Remote-SSH + GitHub path, on top of whatever empty
`README.md`/`.gitignore` scaffold was there originally.

---

## 7. End-to-end order of operations (summary)

1. **Connect** — VS Code Remote-SSH → `10.1.6.17`.
2. **Identify** — `dmesg | tail -n 20` → confirm `/dev/ttyUSB0`.
3. **Permission** — `chmod 666` (or `dialout` group membership).
4. **Bench-test** — `mbpoll` with explicit `-P none -s 1 -d 8`, matching the F4S's confirmed
   baud rate (**19200**, per the root README).
5. **Map** — `/etc/CODESYSControl_User.cfg` → `Linux.Devicefile.1=/dev/ttyUSB0` → restart
   `codesyscontrol`.
6. **Deploy** — open the sandbox project in CODESYS on your laptop, configure Modbus Serial
   Master on COM1, download to the Pi.
7. **Requalify** — run the T1–T9 test plan in `docs/DEPLOYMENT_AND_TEST.md` §5.
8. **Version** — commit/push any doc or code changes from the same Remote-SSH VS Code window
   back to `OJ4884-patch-1`.

---

## 8. Open items carried into this guide

- Confirm which of the two Raspberry Pi 5 units is the one actually running the CODESYS sandbox
  and hosting the adapter — the USB device and this whole guide are tied to that physical Pi's
  OS, not to the CODESYS project file.
- Confirm the F4S is in **static/manual setpoint mode** (not a running profile) before any
  production register-300 write — a running profile owns SP1 and will refuse/override writes.
