# Raspberry Pi / Linux: Serial Communication with Watlow F4S Temperature Controller
## Complete Step-by-Step Modbus RTU Bench Test (Read + Write)

**For:** Anyone setting up the Left Hand Small Temperature Cabinet (JTS Ltd unit) with Modbus RTU control from a Raspberry Pi  
**Skill level assumed:** No prior Modbus experience required — all concepts explained from scratch  
**Hardware tested:** Watlow F4S (SN 038983), Prolific PL2303 USB-to-RS232 adapter, Raspberry Pi (Debian Trixie)

---

## Part 0: What is Modbus RTU? (Concepts First)

**Modbus RTU** is a simple **industrial communication protocol** — think of it like a standard "language" for talking to devices over a serial cable. Instead of inventing your own command format, you use Modbus's predefined commands so any device (F4S, other controllers, software) speaks the same way.

### Key concepts (explained plainly):

**Register:**
A "register" is a **numbered storage slot** inside the F4S controller, like a spreadsheet cell. Each register holds one number (0–65535). We care about:
- **Register 100** = the actual chamber temperature, read-only (you can't change it — it's what the sensor measures)
- **Register 300** = the setpoint (target temperature you want) — readable AND writable

**Function Code (FC):**
A "function code" is the **action** you want to perform:
- **FC03** = "read holding registers" — ask the F4S "what's in register 100?" or "what's in register 300?"
- **FC06** = "write single register" — tell the F4S "set register 300 to this new value"

**Baud Rate, Parity, Data Bits, Stop Bits:**
These are **serial port configuration settings** that control how fast and how reliably data moves through the cable:
- **Baud rate (19200)** = speed; 19200 symbols per second
- **Parity (None, 8N1)** = error-checking method; "None" means no parity, "8" means 8 data bits, "N" = no parity, "1" = 1 stop bit
- Both sender and receiver MUST be set to the same values, or they won't understand each other

**Slave Address:**
The F4S has an address (default: **1**) — like a house number. If you have multiple Modbus devices on the same cable, you address each one separately. With just one F4S, it's always **address 1**.

**0-Based vs 1-Based Addressing:**
Some tools count register numbers starting at 0; others start at 1. The Modbus **PDU (Protocol Data Unit)** — the actual frame sent over the wire — uses 0-based addressing. `mbpoll` normally uses 1-based (human-friendly), so the `-0` flag tells it "use 0-based PDU addressing instead" to match the F4S's internal numbering. This was a critical gotcha in earlier testing.

---

## Part 1: Hardware Setup (Before Any Commands)

### Step 1A: Plug in the USB-to-RS232 adapter

Plug the **Prolific PL2303-based USB adapter** into a free USB port on the Raspberry Pi. **Do not yet plug in the serial (DB9) connector** — verify the adapter first.

### Step 1B: Verify the adapter is recognized

```bash
dmesg | tail -n 20
```

Look for a line like:
```
usb 1-2: pl2303 converter now attached to ttyUSB0
```

This means the adapter appeared as **`/dev/ttyUSB0`** (a device file — think of it like a virtual port the OS exposes for you to use).

**Note:** If you ever unplug and re-plug this adapter, or reboot the Pi, the kernel might assign it a different number (e.g., `/dev/ttyUSB1` instead of `/ttyUSB0`). Always run `dmesg | tail` after any replug to confirm which device file it's on.

### Step 1C: Check and grant permissions

The OS restricts who can use serial ports for security reasons. Check the current permissions:

```bash
ls -la /dev/ttyUSB0
```

You'll see output like:
```
crw-rw---- 1 root dialout 188, 0 Jul  8 10:50 /dev/ttyUSB0
```

This means only `root` and members of the `dialout` group can use it. If your user isn't in `dialout`, add yourself:

```bash
sudo usermod -a -G dialout $USER
```

Then **log out and back in** (or reboot) for the group change to take effect. Verify:

```bash
groups
# You should see "dialout" in the output
```

### Step 1D: Physically wire the serial cable

The F4S has a **terminal block** (a row of screw-down connectors) on its back panel. Wire the DB9 connector from the USB adapter as follows:

| DB9 Pin | Color (ADR-001 standard) | F4S Terminal | Purpose |
|---|---|---|---|
| 3 (TXD) | White | 14 (Tx) | Transmit data FROM Pi TO F4S |
| 2 (RXD) | Red | 15 (Rx) | Receive data FROM F4S TO Pi |
| 5 (GND) | Black | 16 (GND) | Ground / Reference |

**Critical:** TX (white) goes to terminal **14**, RX (red) goes to terminal **15**. Swapping these stops everything — this was a real bug found during testing.

Tighten the terminal-block screws firmly. Loose wires = intermittent timeouts.

---

## Part 2: Install and Verify mbpoll (The Modbus Testing Tool)

**`mbpoll`** is a command-line tool that lets you send Modbus commands from the terminal. Think of it as a "Modbus telephone" — you pick it up, dial the F4S, and ask it questions.

### Step 2A: Install mbpoll

```bash
sudo apt-get update
sudo apt-get install mbpoll
```

Verify installation:

```bash
which mbpoll
# Should print: /usr/bin/mbpoll
```

### Step 2B: Understand the command structure

All mbpoll commands follow this pattern:

```bash
mbpoll -m rtu -a 1 -b 19200 -P none [action flags] /dev/ttyUSB0 [write value, if any]
```

**Flags explained (no prior knowledge assumed):**

| Flag | Full Name | What It Does | Our Value | Why |
|---|---|---|---|---|
| `-m rtu` | Mode RTU | Selects "RTU" format (the protocol style) | `rtu` | F4S uses RTU, not ASCII or TCP |
| `-a 1` | Address | Which device on the cable to talk to | `1` | F4S default address is 1 |
| `-b 19200` | Baud rate | Speed of communication | `19200` | Confirmed on F4S front panel: Setup → Communications → Baud Rate |
| `-P none` | Parity | Error-checking method | `none` | F4S uses 8N1 (no parity); **critical fix** from earlier testing |
| `-t 4` | Type | Register type to read/write | `4` | "4" = holding registers (the type we need) |
| `/dev/ttyUSB0` | Device | Which serial port to use | `/dev/ttyUSB0` | The adapter's device file |

For **reads** (FC03), add these:
| Flag | Meaning | Our Value | Why |
|---|---|---|---|
| `-r 100` | Register address | `100` or `300` | Register 100 = temperature, 300 = setpoint |
| `-c 1` | Count (how many registers) | `1` | Read just 1 register |
| `-1` | Poll once | — | "Poll once and exit" (don't loop) |
| `-0` | 0-based addressing | — | Use PDU (0-based) addressing, not 1-based |

For **writes** (FC06), do NOT include `-c` or `-1`. Instead, append the value:
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -0 /dev/ttyUSB0 265
#                                                               ↑ the value to write
```

---

## Part 3: First Test — Read the Actual Temperature (Register 100)

This is the simplest test: ask the F4S "what temperature do you measure right now?" It should reply with the same value shown on its front-panel display.

### Step 3A: Run the read command

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
```

### Step 3B: Interpret the output

On success, you'll see:

```
Protocol configuration: ModBus RTU
Slave configuration...: address = [1]
                        start reference = 100, count = 1
Communication.........: /dev/ttyUSB0, 19200-8N1
                        t/o 1.00 s, poll rate 1000 ms
Data type.............: 16-bit register, output (holding) register table
-- Polling slave 1...
[100]: 232
```

**Key line:** `[100]: 232`

This means register 100 contains the value **232**, which represents **23.2°C** (the F4S uses one implied decimal place — divide by 10 to get the real temperature).

**Compare to the F4S front panel** — it should display roughly 23.2°C. If they match, the read link works. ✅

### Step 3C: If it times out instead

If you see:

```
Read output (holding) register failed: Connection timed out
```

Check these in order:

1. **Parity mismatch** — if the output shows `19200-8E1` (Even parity) instead of `19200-8N1`, you're using the wrong flag. Use `-P none`.
2. **Permissions** — run `ls -la /dev/ttyUSB0` and confirm you're in the `dialout` group (from Part 1C).
3. **Physical wiring** — double-check that white is on terminal 14, red on 15, black on 16. Loose wires also cause timeouts.
4. **F4S power/mode** — confirm the F4S is powered on and in **run mode**, not a menu.

---

## Part 4: Second Test — Read the Static Setpoint (Register 300)

The setpoint is the **target temperature** you want the cabinet to reach. Register 300 holds this value and can be both read AND written.

### Step 4A: Read the current setpoint

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 -1 -0 /dev/ttyUSB0
```

### Step 4B: Interpret the output

On success:

```
[300]: 240
```

This means the setpoint is **240 in raw form = 24.0°C** (again, divide by 10).

**Compare to F4S front panel** — look for "SP1" or "Setpoint" label. Should show 24.0°C or similar.

---

## Part 5: The Critical Write Test (Register 300) — WITH F4S MENU STATE WARNING

**This is where most issues happen.** Writing a new setpoint involves **more than just sending a command** — the F4S's own menu state matters.

### ⚠️ CRITICAL PREREQUISITE: F4S Menu State

**The F4S ONLY accepts setpoint writes while it is on the MAIN RUN PAGE.**

If the F4S is:
- ✅ **On the main display showing temperature and "SP1" label** → writes succeed
- ❌ **Inside the setpoint-adjustment screen (e.g., entering a new value)** → writes are acknowledged but silently rejected (no error, but value doesn't change)
- ❌ **In Setup menu (Communications, Baud Rate, etc.)** → writes are definitely rejected

**Before you run the write command, visually confirm the F4S front panel is showing the main run screen, NOT editing anything.**

If you're unsure, press **ESCAPE** or **EXIT** multiple times until you see the temperature display and setpoint value clearly.

### Step 5A: Decide what new setpoint to write

For this test, let's write **26.5°C**. In raw register form: `26.5 × 10 = 265`.

### Step 5B: Run the write command

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -0 /dev/ttyUSB0 265
```

**Notice:** No `-c 1`, no `-1`. We just append the value `265` at the end.

### Step 5C: Check the output

**On success**, you'll see:

```
Written 1 references.
```

This tells you mbpoll **sent** the write and got an **acknowledgement** back. But acknowledgement ≠ acceptance — the F4S heard the command, but may have rejected it internally.

### Step 5D: Confirm the write actually worked (Read-back)

**This step is critical.** Immediately read register 300 again:

```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 -1 -0 /dev/ttyUSB0
```

Check the output:

| Scenario | Output | Meaning | What to do |
|---|---|---|---|
| **Write succeeded** | `[300]: 265` | Register 300 now holds 265 (26.5°C). F4S front panel should also show 26.5°C within a few seconds. | ✅ Success. Watch the F4S ramp toward 26.5°C. |
| **Write rejected silently** | `[300]: 240` (unchanged) | F4S acknowledged the frame but rejected the value. Most common cause: F4S was in menu/edit mode. | ❌ Exit any F4S menus to main page, retry the write. |
| **Communication lost** | `Connection timed out` | Cable unplugged, adapter disconnected, or F4S powered off mid-write. | ❌ Check physical connections, restart F4S, retry. |

### Step 5E: Verify visually on the F4S

Look at the F4S front panel:
- **SP1 should now show 26.5°C** (or whatever value you wrote)
- **The actual temperature display should slowly ramp toward 26.5°C** (the F4S's own control loop is working)

---

## Part 6: Complete Diagnostic Script (write-setpoint.sh)

Rather than typing the commands by hand each time, use the provided script:

```bash
./scripts/write-setpoint.sh 26.5
```

This script automates:
1. **Read current setpoint** (register 300)
2. **Skip the write if unchanged** (avoids unnecessary writes; register 300 is only followed while the F4S is in static mode, not cyclic-write-sensitive EEPROM — see EEPROM myth note below)
3. **Validate the requested value is 30–130°C** (same bounds as CODESYS logic)
4. **Convert to raw register value** (multiply by 10)
5. **Send the write (FC06)** via mbpoll
6. **Read back and confirm** the value actually changed
7. **Report SUCCESS or FAILURE** clearly

**Example run:**

```bash
$ ./scripts/write-setpoint.sh 28.0
Reading current setpoint (register 300)...
Current setpoint: 26.5C (raw 265)
Writing new setpoint: 28.0C (raw 280) to register 300...
Written 1 references.
CONFIRMED: setpoint now reads 28.0C (raw 280)
```

If it fails:

```bash
$ ./scripts/write-setpoint.sh 28.0
Reading current setpoint (register 300)...
Current setpoint: 26.5C (raw 265)
Writing new setpoint: 28.0C (raw 280) to register 300...
Written 1 references.
WARNING: read-back (265) does not match written value (280).
F4S may be in profile/ramp mode (SP1 owned by an active profile) -- confirm the
front panel is in static/manual setpoint mode and retry.
```

---

## Part 7: Troubleshooting Table (When Things Don't Work)

| Symptom | Most Likely Cause | Diagnosis | Fix |
|---|---|---|---|
| **Read (Reg 100 or 300): Timeout** | Parity mismatch OR permissions OR wiring | Check: `mbpoll` shows `8E1` instead of `8N1`? Are you in `dialout` group? Wires tight? | Add `-P none` to fix parity. Re-run Part 1C for permissions. Re-check wiring. |
| **Read succeeds, but value is off by one** | 0-based vs 1-based addressing | Without `-0` flag, mbpoll queries register 99/299 instead of 100/300 | Always use `-0` flag. |
| **Read shows stale/unchanging value** | F4S setpoint hasn't moved (normal for cold start) OR cable issue | Wait 10 seconds, read again. Check cable. | Temperature ramps over time — this is expected. |
| **Write: "Written 1 references" but read-back unchanged** | **F4S is in menu/edit mode** (most common) OR F4S in profile/ramp | Before writing, press ESCAPE on F4S to exit menus. Check front panel shows main page. | Exit menu. Return to main run page. Retry write. |
| **Write: Timeout** | Cable unplugged OR comms lost during write | Run read first to confirm comms. Replug cable if loose. | Verify physical connection. Run `dmesg \| tail` to see if adapter disconnected. |
| **Read-back shows different value than written** | F4S rejected the value (out of range, profile active, etc.) | Check range (0–200°C allowed). Check F4S isn't in profile/ramp. | Validate value is in range. Confirm F4S mode. |

---

## Part 8: Moving to CODESYS

Once you've successfully:
- ✅ Read register 100 (temperature) multiple times
- ✅ Read register 300 (setpoint) multiple times  
- ✅ Written register 300 (setpoint) and confirmed with read-back
- ✅ Watched the F4S ramp toward the new setpoint on the display

**The Linux/hardware layer is proven.** The Modbus RTU link is fully functional.

The next step is integrating this proven link into **CODESYS** so the HMI can trigger reads and writes instead of manual terminal commands. See the main project README for the CODESYS integration steps (Requalify and Repeat phases).

---

## Quick Reference: Command Summary

**Read actual temperature:**
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 100 -c 1 -1 -0 /dev/ttyUSB0
```

**Read setpoint:**
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 -1 -0 /dev/ttyUSB0
```

**Write setpoint (example: 26.5°C = raw 265):**
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -0 /dev/ttyUSB0 265
```

**Then immediately read back to confirm:**
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -t 4 -r 300 -c 1 -1 -0 /dev/ttyUSB0
```

**Or use the script:**
```bash
./scripts/write-setpoint.sh 26.5
```

---

## Notes for Future Reference

1. **F4S menu-state blocking writes** — this was the hidden gotcha. Writes succeed at the comms layer but fail at the application layer if the F4S is in menu mode. Always confirm the main page is showing.

2. **EEPROM myth, corrected** — register 300 is *not* documented as EEPROM-backed. The F4S/D spec sheet describes data retention via battery-backed RAM (7-year), which doesn't have EEPROM's limited write-cycle life; the "cyclic writes damage memory" caution belongs to a different Watlow product (the SD31). The script still skips writes if the value is unchanged, and CODESYS's `FB_CabinetSetpointControl` still uses edge-triggered writes — but the real reason is "write once per operator action, and register 300 is only followed while the F4S is in static mode," not EEPROM wear.

3. **One implied decimal** — both registers (100 and 300) divide by 10 to get the real temperature in °C. This is standard Watlow convention.

4. **Permissions and daemon access** — your user needs `dialout` group membership. The CODESYS runtime (if not running as root) also needs the same. This was the cause of earlier "mysteriously failing" Modbus comms on Linux even when `mbpoll` worked fine from the shell.
