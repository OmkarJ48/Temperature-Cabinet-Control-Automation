# CODESYS Modbus RTU Integration: Watlow F4S Cabinet Control
## Complete Setup Guide (Zero Prior Knowledge Assumed)

**For:** Engineers integrating Watlow F4S setpoint control into CODESYS running on Raspberry Pi  
**Prerequisites:** Linux/mbpoll side is proven working (see ../linux-integration-README-UPDATED.md)  
**Hardware:** CODESYS Control for Linux ARM64 SL runtime, Prolific PL2303 USB-RS232 adapter, Raspberry Pi (10.1.6.17)

---

## CRITICAL PREREQUISITE: Network Stabilization

Before starting CODESYS integration, the Raspberry Pi's ethernet driver must be stabilized. The kernel's packet-batching optimizations (`TSO`/`GSO`/`GRO`) can cause timing stalls that interfere with both EtherCAT and Modbus latency. This step is mandatory.

### Step 0A: Install ethtool (network diagnostics tool)

```bash
ssh mechatronics@LeftHandSmallTempCab
sudo apt-get update
sudo apt-get install ethtool -y
```

### Step 0B: Identify your main ethernet port

```bash
ip a
```

Look for a line starting with a number followed by a port name that has an IP address (10.1.x.x or similar). Example output:

```
2: internet_port: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    inet 10.1.6.17/24 scope global
```

In this case, your main port is **`internet_port`**. (On a standard Raspberry Pi it might be `eth0`, but on your Beckhoff-based controller with EtherCAT, it's `internet_port`.)

**Note the exact port name from your output and use it in the next step.**

### Step 0C: Disable offloading features

Replace `PORTNAME` with your actual port name (e.g., `internet_port`):

```bash
sudo ethtool -K PORTNAME tso off gso off gro off
```

For your system specifically:

```bash
sudo ethtool -K internet_port tso off gso off gro off
```

**What this does:**
- `tso off` = disable TCP Segmentation Offload (kernel will not batch TCP packets)
- `gso off` = disable Generic Segmentation Offload (no packet batching at all)
- `gro off` = disable Generic Receive Offload (no batch receiving)

**Result:** Packets are handled raw and immediately, reducing latency variance. Timing becomes predictable.

### Step 0D: Make the change permanent (survives reboot)

```bash
sudo nano /etc/network/if-up.d/disable-offloading
```

Paste this content (replace `internet_port` with your actual port name if different):

```bash
#!/bin/bash
# Disable packet offloading for industrial protocol latency predictability
# Required for EtherCAT + Modbus RTU coexistence on the same network port
ethtool -K internet_port tso off gso off gro off
```

Save (Ctrl+O, Enter, Ctrl+X), then make it executable:

```bash
sudo chmod +x /etc/network/if-up.d/disable-offloading
```

This script runs automatically whenever the network interface comes up (including after reboot).

### Step 0E: Verify the change

```bash
ethtool -k eth0 | grep -E "tcp-segmentation|generic-segmentation|generic-receive"
```

You should see:

```
tcp-segmentation-offload: off
generic-segmentation-offload: off
generic-receive-offload: off
```

All must show `off`. If any show `on`, the step failed — repeat Step 0C and check for typos.

---

## Part 1: Linux SysCom Configuration (The Serial Port Bridge)

CODESYS needs to know which Linux device file maps to which COM port number. This configuration lives in `/etc/CODESYSControl_User.cfg`.

### Step 1A: Edit the configuration file

```bash
sudo nano /etc/CODESYSControl_User.cfg
```

Look for the `[SysCom]` section. If it doesn't exist, add it at the bottom of the file. Set it to:

```ini
[SysCom]
Linux.Devicefile.2=/dev/ttyUSB0
portnum.2=2
```

**Why COM2 instead of COM1?** Earlier testing found that COM1 was reserved by the system. COM2 is free and unambiguously available.

**Explanation:**
- `Linux.Devicefile.2=/dev/ttyUSB0` = "map COM port 2 to the USB-RS232 adapter device file"
- `portnum.2=2` = "use index 2 as the port number" (CODESYS will refer to it as COM2)

Save (Ctrl+O, Enter, Ctrl+X).

### Step 1B: Verify the change

```bash
cat /etc/CODESYSControl_User.cfg | grep -A 2 "\[SysCom\]"
```

Should show:

```
[SysCom]
Linux.Devicefile.2=/dev/ttyUSB0
portnum.2=2
```

### Step 1C: Restart CODESYS runtime to load the new config

```bash
sudo systemctl restart codesyscontrol
sudo systemctl status codesyscontrol
```

Status should show `active (running)`.

---

## Part 2: CODESYS Device Tree Setup

Now you'll add the Modbus devices to your CODESYS project. This is done in the **IDE on your laptop**, not the Pi terminal.

### Step 2A: Add the Modbus_COM device (if not already present)

In your CODESYS IDE project tree:

```
Device (CODESYS Control for Linux ARM64 SL)
└─ (right-click) → Add Device → Fieldbuses → Serial → Modbus_COM
```

Name it **Modbus_COM**. Open its **General** tab and verify/set:

| Field | Value |
|---|---|
| Port | COM2 |
| Baud Rate | 19200 |
| Parity | None |
| Data Bits | 8 |
| Stop Bits | 1 |

**Why COM2?** It matches the Linux config `portnum.2=2` from Part 1.

### Step 2B: Add the Modbus Master device

Right-click **Modbus_COM** → **Add Device** → **Fieldbuses → Modbus → Modbus Master, COM Port**

Name it **Modbus_Master_COM_Port**. Open its **General** tab:

| Field | Value |
|---|---|
| Transmission Mode | RTU |
| Modbus bus cycle task | MainTask |
| Response Timeout | 1000 ms |

**Why MainTask?** The Modbus Master runs synchronously with your main PLC program, ensuring reads/writes happen at predictable intervals.

### Step 2C: Add the Modbus Slave device

Right-click **Modbus_Master_COM_Port** → **Add Device** → **Fieldbuses → Modbus → Modbus Slave, COM Port**

Name it **Modbus_Slave_COM_Port**. Open its **General** tab:

| Field | Value |
|---|---|
| Slave address | 1 |

This represents the **F4S controller itself** (address 1 on the Modbus network).

### Step 2D: Create the read channel (Register 100)

On the **Modbus_Slave_COM_Port**, navigate to the **Channels** tab and add a new channel:

| Field | Value |
|---|---|
| Name | ReadChamberTemp |
| Access Type | Read Holding Registers (FC03) |
| Offset | 100 |
| Length | 1 |
| Trigger | Cyclic |
| Error handling | Keep last value |

**Explanation:**
- **Offset 100** = read from register 100 (the actual chamber temperature)
- **Length 1** = read 1 register (not 100 registers — this was a bug in earlier testing)
- **Cyclic** = read every bus cycle (every ~10 ms by default)
- **Keep last value** = if a read fails, show the previous value instead of blanking to 0

### Step 2E: Create the write channel (Register 300)

Add another channel on the Slave:

| Field | Value |
|---|---|
| Name | WriteSetpoint |
| Access Type | Write Holding Registers (FC06) |
| Offset | 300 |
| Length | 1 |
| Trigger | Rising edge |
| Error handling | none |

**Explanation:**
- **Offset 300** = write to register 300 (the setpoint)
- **Rising edge** = trigger a write only when your PLC program sets a "write trigger" variable from 0→1 (prevents constant rewrites)
- **Error handling: none** = just report errors; don't auto-retry

---

## Part 3: Global Variable List (GVL_Modbus)

Your PLC program needs variables to hold the raw register values and trigger writes.

### Step 3A: Create E_SetpointState data type

In your project tree → **DataTypes** (right-click → Add Data Type):

```st
TYPE E_SetpointState :
(
    IDLE        := 0,
    READY       := 10,
    WRITING     := 20,
    CONFIRM     := 30,
    FAULTED     := 99
);
END_TYPE
```

### Step 3B: Create E_FaultCode data type

```st
TYPE E_FaultCode :
(
    NO_FAULT      := 0,
    COMMS_TIMEOUT := 1,
    WRITE_FAILED  := 2,
    NOT_ACCEPTED  := 3,
    RANGE_LOW     := 4,
    RANGE_HIGH    := 5,
    OVER_TEMP     := 6
);
END_TYPE
```

### Step 3C: Create GVL_Modbus

In your project tree → **GlobalVariableLists** (right-click → Add Global Variable List):

```st
{attribute 'qualified_only'}
VAR_GLOBAL
    // FC03 cyclic read, offset 100, length 1 → actual temp raw (x10)
    wInput1Value    : WORD;
    // FC03 read-back, offset 300, length 1 → SP1 raw read (x10)
    wSetpoint1Read  : WORD;
    // FC06 write single register, offset 300 → SP1 raw write (x10)
    wSetpoint1Write : WORD;
    // Rising-edge trigger for FC06 channel
    xWriteTrigger   : BOOL;
    // Diagnostic status
    xModbusError    : BOOL;
    xModbusDone     : BOOL;
END_VAR
```

---

## Part 4: I/O Mapping (Connect Channels to Variables)

This is where the Modbus channels physically connect to your GVL variables.

### Step 4A: Map the read channel

On the **Modbus_Slave_COM_Port** device, navigate to **I/O Mapping** tab.

Find the **ReadChamberTemp** channel's input variable (likely `%IW82` or similar). Expand the array tree (click the small arrow/triangle) to reveal individual indexed elements:

- `Holding registers[0]` ← map THIS to `Application.GVL_Modbus.wInput1Value`
- `Holding registers[1]` ← leave unmapped (unused padding)

On the `[0]` row, set the **PLC Variable** column to:

```
Application.GVL_Modbus.wInput1Value
```

### Step 4B: Map the write channel

Find the **WriteSetpoint** channel's output variable. Map its trigger to:

```
Application.GVL_Modbus.xWriteTrigger
```

Map its data output to:

```
Application.GVL_Modbus.wSetpoint1Write
```

---

## Part 5: Compile, Download, Verify

### Step 5A: Compile

```
Build → Rebuild All
```

Should show **0 errors**. If you see type-mismatch errors, check that you expanded the array and mapped only `[0]`, not the whole array.

### Step 5B: Download to Pi

Online menu → right-click the main device → **Download**

Accept the "application differs" prompt.

### Step 5C: Go online and verify green lights

In CODESYS, check the device tree:

```
Modbus_COM                      → GREEN light (not repeat icon)
  └─ Modbus_Master_COM_Port     → GREEN light (not red triangle)
      └─ Modbus_Slave_COM_Port  → GREEN light (not red triangle)
```

All must be GREEN. If any show red, see **Troubleshooting** section below.

### Step 5D: Watch the data

Open a **Watch window** (View → Add Watch) and add:

```
Application.GVL_Modbus.wInput1Value
```

It should update every ~1 second and show **232** (or whatever the current chamber temperature is, scaled by 10). If it shows 232, Requalify is COMPLETE. ✅

---

## Part 6: Testing Writes (Optional, but Recommended)

Once reads are working, test a write:

### Step 6A: In PLC_PRG (or your test program), add logic

```st
// Test write: when this trigger goes high, write 265 (26.5°C) to register 300
IF <some condition> THEN
    GVL_Modbus.wSetpoint1Write := 265;  // Set value
    GVL_Modbus.xWriteTrigger := TRUE;    // Trigger the write (rising edge)
ELSE
    GVL_Modbus.xWriteTrigger := FALSE;
END_IF
```

### Step 6B: Watch the setpoint variable

Add `wSetpoint1Read` to the watch window. When you trigger the write:
1. `wSetpoint1Write` gets the new value (265)
2. `xWriteTrigger` goes TRUE
3. FC06 write is sent
4. `wSetpoint1Read` updates to the new value (if successful) or stays at old value (if F4S rejected)

### Step 6C: Visually verify on F4S

The F4S front panel should show the new setpoint within 2–3 seconds.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **All devices show red triangles, no errors** | Application never restarted after download | Press F5 (Start) in CODESYS to start the app |
| **Modbus_COM shows repeat icon (⟳)** | Port conflict or config mismatch | Verify `/etc/CODESYSControl_User.cfg` shows `portnum.2=2`, not `portnum.1`. Restart runtime: `sudo systemctl restart codesyscontrol` |
| **Devices green but wInput1Value stays 0** | Read channel not mapped correctly | Check I/O Mapping: did you expand the array and map `[0]`, not the whole array? |
| **Write sends but value doesn't change on F4S** | F4S in menu mode OR write channel not triggering | Confirm F4S is on main run page (not in menu). Check that `xWriteTrigger` is actually going TRUE in your PLC program. |
| **Network lag, occasional stalls** | Offloading still enabled | Run `ethtool -k eth0 \| grep offload` and verify all show `off`. |

---

## Next Steps

Once `wInput1Value = 232` shows live in the watch window, the hardware integration is PROVEN. The next phases are:

1. **Repeat phase:** Test the HMI setpoint button and 9-case validation plan (see main README)
2. **Phase 4:** Final HMI refinement and integration testing
3. **GitHub push:** Commit all changes and documentation

---

## Quick Reference: Register Map

| Register | Name | Access | Raw ÷10 | Purpose |
|---|---|---|---|---|
| 100 | Input 1 Value | Read-only | Yes | Actual chamber temperature (°C) |
| 300 | Set Point 1 | Read+Write | Yes | Static setpoint (°C) |

**One implied decimal place:** register value 232 = 23.2°C.

---

## Notes for Future Engineers

1. **COM2 vs COM1:** Early testing found COM1 was reserved. COM2 is the working port.
2. **Network offloading:** EtherCAT + Modbus on the same network requires offloading disabled. This is non-negotiable for latency-sensitive protocols.
3. **F4S menu blocking:** The F4S silently rejects setpoint writes while in any menu (Setup, parameter adjustment, etc.). Always confirm main page before testing writes.
4. **Edge-triggered writes:** Using `xWriteTrigger` with rising-edge detection prevents the F4S from being hammered with duplicate writes, reducing EEPROM wear.
