# Raspberry Pi / Linux OS Layer — Serial Adapter, Permissions, `mbpoll` Bench Test

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Applies to:** Raspberry Pi hosting the CODESYS sandbox project for the **Left Hand Small Temperature Cabinet** (DLS008 panel), reached over SSH at **10.1.6.17**
**Target:** Watlow F4S (SN 038983), Modbus RTU over the USB-to-RS232 adapter on `/dev/ttyUSB0`
**Covers:** Steps 2, 3, and 4 of the integration sequence in the root `README.md`

This folder covers everything **below** CODESYS on the Linux side — identifying the serial
adapter, granting it permissions, and proving the raw Modbus link with `mbpoll` before CODESYS
is ever involved. It assumes you're already connected to the Pi (see `remote-ssh-vscode/`) and
hands off to `codesys-integration/` once the bench test below succeeds.

**Do not skip ahead to CODESYS if the bench test here hasn't passed.** A CODESYS Modbus error on
top of an unproven serial link is two unknowns at once — prove the link in isolation first.

---

## Step 2: Identify the serial adapter

Plug the USB-to-RS232 adapter into a free USB port on the active Pi, then:

```bash
dmesg | tail -n 20
```

Look for the attach line — on this hardware it's a Prolific PL2303-based adapter:

```
usb 1-2: pl2303 converter detected
usb 1-2: pl2303 converter now attached to ttyUSB0
```

The device file is **`/dev/ttyUSB0`**. This is what goes into both the `mbpoll` command and the
CODESYS Modbus device tree later — there is no separate "Linux COM port" name to translate.

**If the port gets disconnected and reconnected** (adapter unplugged/replugged, or the Pi
rebooted), the kernel can assign a **different** number — `/dev/ttyUSB1` instead of `/dev/ttyUSB0`
— if anything else claims `ttyUSB0` first. Never assume the old device file is still correct
after a reconnect. Check what's actually present:

```bash
ls /dev/ttyUSB*
```

If it lists `/dev/ttyUSB1` instead of `/dev/ttyUSB0`, use that new number for every command below
(`chmod`, `mbpoll`, and — if this recurs — the CODESYS runtime mapping in
`codesys-integration/`). Re-running `dmesg | tail -n 20` after any reconnect is the reliable way
to confirm which node the adapter actually landed on, rather than assuming.

---

## Step 3: Grant port permissions

Serial devices on Debian/Raspberry Pi OS are owned by `root:dialout` with group-only access by
default. Check what you're dealing with first:

```bash
ls -la /dev/ttyUSB0
```

Reading the permission bits (`crw-------` or `crw-rw----`):

| Bits | Meaning |
|---|---|
| `crw-------` | Owner (`root`) only — no group or other access at all |
| `crw-rw----` | Owner (`root`) and group (`dialout`) can read/write — this is the normal default |
| `crw-rw-rw-` | Everyone can read/write — this is what `chmod 666` produces |

If you see `crw-------` or `crw-rw----` and your user isn't in the `dialout` group, `mbpoll` (and
CODESYS) will fail to open the port with a permissions error, not a Modbus error — don't waste
time on baud/parity troubleshooting until this is confirmed.

**Option A — temporary fix (resets on every reboot or replug):**

```bash
sudo chmod 666 /dev/ttyUSB0
```

Fast for one bench-test session, but if the adapter is unplugged and replugged, or the Pi
reboots, this reverts and needs to be re-run.

**Option B — permanent fix (survives reboots and replugs):**

```bash
sudo usermod -a -G dialout $USER
# then log out and back in (or reboot) for the group membership to take effect
```

This is the standard Linux practice rather than a one-off workaround — once your user is in
`dialout`, every `/dev/ttyUSB*` device grants your user read/write automatically, permanently.

**CODESYS's own runtime process needs the same access.** If the runtime doesn't run as `root`,
add its service user to `dialout` too — otherwise the Modbus device in CODESYS will silently show
"no response" even though `mbpoll` works fine from your own shell.

Helper scripts:
- [`scripts/check-serial-permissions.sh`](scripts/check-serial-permissions.sh) — read-only check, no changes made
- [`scripts/grant-serial-permissions.sh`](scripts/grant-serial-permissions.sh) — check + apply the temporary `chmod 666` fix

---

## Step 4: Bench-test the link with `mbpoll` (before touching CODESYS)

Install once:

```bash
sudo apt-get update
sudo apt-get install mbpoll
```

### 4.1 Confirmed working command for this cabinet

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
```

| Flag | Meaning | Value used here |
|---|---|---|
| `-m rtu` | Modbus RTU (not ASCII/TCP) | — |
| `-a 1` | Slave address | `1` (F4S default) |
| `-b 19200` | Baud rate | **19200** — confirmed on the F4S front panel |
| `-P none` | Parity | **None** — critical: `mbpoll` defaults to Even (8E1), which times out against this 8N1 device |
| `-t 4` | Register type | 16-bit holding register (FC03 read / FC06 write family) |
| `-r 100` | Start register | `100` = Input 1 Value (actual chamber temp) |
| `-c 1` | Register count | `1` |
| `-1` | Poll once, then exit | — |
| `-0` | 0-based (PDU) addressing | **Required** — confirmed on this hardware; without it, `mbpoll` queries the wrong register (one off) |

**Confirmed result:**

```
[100]: 232
```

`232` = 23.2°C, matching the F4S front-panel display exactly.

A helper script wrapping this command is at
[`scripts/bench-test-modbus.sh`](scripts/bench-test-modbus.sh).

### 4.1a Read the static setpoint (register 300, SP1)

Register 100 above is the **read-only process value** (actual chamber temperature). The
**static setpoint** — labelled `SP1` on the F4S front panel, currently showing `24.0°C` in the
photo referenced for this section — lives in a **different** register: **300 (Set Point 1)**.
Same command, same flags, only the `-r` value changes:

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 -1 -0 /dev/ttyUSB0
```

Or with the helper script (register is the third positional argument):

```bash
./scripts/bench-test-modbus.sh /dev/ttyUSB0 19200 300
```

**Expected result**, matching the front-panel `SP1  24.0°C` reading:

```
[300]: 240
```

`240` is the raw register value — the F4S carries **one implied decimal place**, so `240 / 10 =
24.0°C`. This is the same convention as register 100 (`232` → `23.2°C`); no separate scaling
setting is needed on the Linux/`mbpoll` side, only in whatever displays the value afterward
(CODESYS scales it the same way once mapped).

If this read also succeeds (it will, since it's the identical link already proven for register
100 — same slave, same wiring, same parity/baud, just a different holding register), that
**conclusively proves the Linux ↔ F4S link can see the setpoint**, and any remaining failure to
see it in CODESYS is a CODESYS-side configuration problem, not a hardware/wiring problem — see
§4.4 below and `codesys-integration/README.md` §5.4.

### 4.2 Two independent fixes were needed — both matter

The working command above only succeeds because **two separate problems** were found and fixed;
either one alone still produced a timeout:

1. **Parity mismatch** — `mbpoll` defaults to Even parity (8E1) if `-P` isn't given. This F4S is
   configured 8N1 (no parity). Talking 8E1 to an 8N1 device is a framing mismatch — the F4S never
   recognizes a valid frame, so every request times out.
2. **Physical TX/RX wiring swap at the F4S terminal block** — the white/red wires were landed on
   the wrong terminals (swapped relative to the documented white=14/TX, red=15/RX assignment).
   Fixing the parity flag alone still timed out until this was corrected on site.

Neither the flag fix nor the wiring fix was sufficient by itself. If you hit a timeout on a
similar link in the future, don't stop investigating after fixing the first plausible cause —
check both software (parity/baud/addressing flags) and physical (wiring, connector seating)
independently.

### 4.3 Troubleshooting table

| Symptom | Likely cause | Check |
|---|---|---|
| Timeout, banner shows `19200-8E1` | Parity mismatch | Add `-P none` |
| Timeout even with `-P none` confirmed (`8N1` in banner) | Wrong baud rate | Verify on F4S front panel: **Setup → Communications → Baud Rate** (should read 19200) |
| Timeout persists at correct baud/parity | Permissions | Re-run the Step 3 checks (`ls -la /dev/ttyUSB0`, `chmod`/`dialout`) |
| Timeout persists, permissions confirmed OK | Wrong slave address | F4S defaults vary — 1, 247, or 255; read it off the front panel, don't assume `-a 1` |
| Timeout persists, everything above checked | Physical wiring swap at the F4S terminal block | Re-trace/re-check the DB9-to-terminal wiring against the nameplate (terminals 14/15/16); see root README ADR-001 for the documented color code |
| Read succeeds but the value looks off by one register | 0-based vs 1-based addressing | Confirm `-0` is present; without it `mbpoll` queries the wrong PDU address |
| Garbage/CRC error instead of a clean timeout | Adapter reassigned to a different `/dev/ttyUSB*` node after a replug | Re-run `dmesg \| tail` (Step 2) to confirm the current device file |
| Register 100 (read) works but register 300 write (FC06) is refused | F4S in profile/ramp mode, not static setpoint | Confirm F4S is in **static/manual setpoint mode** — a running profile owns SP1 |

---

## 4.4 `mbpoll` reads fine standalone, but CODESYS's Modbus master/slave shows nothing

This is a **different failure mode** from anything above — it means the raw serial link is
already proven (Steps 2–4 all passed), so don't re-check wiring/parity/baud again. The most
common cause at this exact point is much simpler and purely a Linux OS-level issue:

**A serial device file can only be held open by one process at a time.** `/dev/ttyUSB0` is not
shared — if `mbpoll` (or any other process) still has the port open, the CODESYS runtime's
attempt to open the same device for its own Modbus master will fail or silently get no data,
even though the exact same `mbpoll` command works perfectly when run on its own.

**Check what currently holds the port:**

```bash
sudo lsof /dev/ttyUSB0
# or, if lsof isn't installed:
sudo fuser -v /dev/ttyUSB0
```

If this lists a `mbpoll` process (or anything else), that process is blocking CODESYS from
acquiring the port. Kill it or let it finish, then restart the CODESYS runtime:

```bash
sudo systemctl restart codesyscontrol
```

**Practical rule going forward:** never run a manual `mbpoll` bench-test *while* CODESYS is
also trying to run its own Modbus master against the same device — they will fight over the
same port. Bench-test with `mbpoll` first to prove the link (Step 4), then **stop**, confirm
the port is free (`lsof`/`fuser` show nothing), and only then log into/run the CODESYS
application.

Other things to rule out at this stage, roughly in order of likelihood, are covered in
`codesys-integration/README.md` §5.4 (port-file mismatch in `/etc/CODESYSControl_User.cfg`,
serial parameters set independently inside the CODESYS `Modbus_COM` device, and the
Master/Slave device-tree hierarchy itself).

---

## Order of operations reminder

Once `mbpoll` reads cleanly and repeatably (run it two or three times, not just once — Rebuild →
Retest → Requalify → Repeat), proceed to `codesys-integration/README.md` to map this proven port
into the CODESYS runtime. See the root `README.md`'s "Linux ↔ Raspberry Pi ↔ CODESYS ↔ GitHub"
section for the full six-step sequence and how all three folders fit together.
