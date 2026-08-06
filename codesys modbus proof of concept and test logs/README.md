# CODESYS ↔ Python Gateway Integration (Modbus TCP)

**Status: ✅ Proven on hardware from the watch window, no HMI.** Live temperature
reads, setpoint writes with read-back confirmation, range rejection, and clean
fault recovery all verified against the real Watlow F4S cabinet on 27 July 2026.

This package owns **everything CODESYS-side**: the device tree, the Modbus TCP
master/slave configuration, the channel table, the I/O mapping, the ST source,
and the watch-window operating procedure.

The Python gateway and its RTU link to the F4S live separately in
[`../python modbus proof of concept and test logs/`](<../python modbus proof of concept and test logs/>). That split is the
architecture: **the gateway owns the serial port and CODESYS never touches it.**

```
CODESYS (Windows IDE ──> Pi runtime)          Python gateway (Pi)        Cabinet
Modbus TCP Master ──> Modbus TCP Slave ──TCP──> f4s_gateway.py ──RTU──> Watlow F4S
        10.1.6.17:502, Unit ID 1              /dev serial, 19200        SP reg 300
```

> **Predecessor.** [`../codesys modbus com port investigation and troubleshooting log/`](<../codesys modbus com port investigation and troubleshooting log/>)
> documents the earlier RS-232 serial-direct approach, where CODESYS drove the
> F4S itself. That approach is **superseded** by this one and is kept only as an
> investigation record.

---

## Contents

| Path | What it is |
|---|---|
| `src/DUTs/` | `E_FaultCode`, `E_SetpointState` enumerations |
| `src/GVLs/` | `GVL_Modbus` (channel-mapped raw registers), `GVL_HMI` |
| `src/POUs/` | `PLC_PRG_TCP.st` — **the program actually running**; `PLC_PRG.st` is also present |
| `docs/test-logs/` | Daily hardware test logs |
| `WebVisu/codesys_hmi.html`, `src/HTML/codesys_hmi.html` | Operator HMI page (setpoint tile + write dialog) — see below |

---

## Proven configuration — single source of truth

If anything below disagrees with a screenshot or an older doc, **this wins**.

### Device tree

```
Device (CODESYS Control for Linux ARM64 SL)
└── Ethernet (adapter that reaches 10.1.6.17)
    └── Modbus_TCP_Master (Modbus TCP Client)
        └── Modbus_TCP_Slave (Modbus TCP Slave)
            IP 10.1.6.17 · Port 502 · Unit ID 1 · Response timeout 8000 ms
```

**Unit ID must be 1.** The CODESYS default is 255, and the gateway serves only
device id 1 — leaving it at 255 produces a *connected* socket where every single
transaction fails with `GATEWAY TARGET FAILED TO RESPOND` and an Error Counter
of exactly 2× the Request Counter.

The EtherCAT branch (EK1100 + EL modules) is unrelated to this integration.

### Channels (Modbus Server Channel tab)

| # | Name | Access type | Trigger | READ off | WRITE off | Maps to |
|---|---|---|---|---|---|---|
| 0 | Holding Registers[0] | Write Single Register (FC06) | Cyclic 1000 ms | — | 16#0000 | `wSetpoint1Write` |
| 1 | Holding Registers[1] | Write Single Register (FC06) | **Rising edge** | — | 16#0001 | data WORD → `wTriggerValue`, trigger BIT → `xWriteTrigger` |
| 2 | Holding Registers[2] | Read Holding Registers (FC03) | Cyclic 2000 ms | 16#0002 | — | `wInput1Value` |
| 3 | Holding Registers[3] | Read Holding Registers (FC03) | Cyclic 2000 ms | 16#0003 | — | `wSetpoint1Read` |
| 4 | Holding Registers[4] | Read Holding Registers (FC03) | Cyclic 2000 ms | 16#0004 | — | `wStatus` |

**Channel 1 needs both rows mapped.** A rising-edge FC06 channel sends the
current value of its mapped *data WORD* when the *trigger BIT* goes 0→1. Leave
the data word unmapped and it sends `0` — the gateway only fires on `1`, so
writes would silently succeed and do nothing. `wTriggerValue : WORD := 1`
exists purely to be that constant.

**Channel 4 is not optional.** Without it, `wStatus` reads 0 = "OK" and the
state machine is blind to every gateway-side failure.

### I/O mapping rules

- Map the **element row** (`Holding Registers[n][0]`, type WORD), never the
  ARRAY parent row. A struck-through address on the element row is **normal**.
- **Always update variables = Enabled 1** (or Enabled 2), and the master's bus
  cycle task = **MainTask**, never "unspecified". Otherwise everything shows
  green and the values never move.

### Gateway register map

| TCP reg | Direction | Meaning | Scaling |
|---|---|---|---|
| 0 | write | Requested setpoint | ×10, **signed** |
| 1 | write (pulse of 1) | Apply trigger (gateway clears it) | 0/1 |
| 2 | read | Chamber temperature | ×10, **signed** |
| 3 | read | Confirmed setpoint read-back | ×10, **signed** |
| 4 | read | Status: 0 OK · 2 WRITE_FAILED · 3 NOT_ACCEPTED · 4 RANGE · 5 COMMS | — |

> **Signed, not unsigned.** `WORD` is unsigned in IEC 61131-3, so PLC_PRG must
> use `WORD_TO_INT` on reads and `INT_TO_WORD(REAL_TO_INT(...))` on writes.
> Treating these as unsigned is what made the whole sub-zero half of the range
> unreachable. The fix is documented in the root README.

---

## Operating from the watch window (no HMI)

### Watch list

```
PLC_PRG.rChamberTemp          PLC_PRG.eSetpointState
PLC_PRG.rReqSetpoint          PLC_PRG.eFaultCode
PLC_PRG.rConfirmedSetpoint    PLC_PRG.xStartWrite
GVL_Modbus.wInput1Value       GVL_Modbus.wSetpoint1Read
GVL_Modbus.wStatus            GVL_Modbus.wSetpoint1Write
GVL_Modbus.xWriteTrigger
```

### Writing a setpoint

CODESYS uses **prepare-then-write** — typing in the Value column does nothing.

1. Confirm the F4S front panel is on its **main run page**. The F4S silently
   rejects setpoint writes while its setpoint-edit menu is open; the gateway
   reports status 3 and the state machine faults `NOT_ACCEPTED`.
2. `PLC_PRG.rReqSetpoint` → **Prepared value** column → type the target.
3. `PLC_PRG.xStartWrite` → **Prepared value** → `TRUE`.
4. **Ctrl+F7** (or right-click → *Write values*). Selecting both rows and
   writing once is cleaner — the rising edge then sees the setpoint already in
   place.
5. Watch `eSetpointState` run `IDLE → READY → WRITING → CONFIRM → IDLE`.

`xStartWrite` self-clears; you do not reset it manually.

### Verifying

| Check | Expected |
|---|---|
| `GVL_Modbus.wSetpoint1Write` | request ×10 (e.g. `265` for 26.5 °C) |
| `eSetpointState` | back to `IDLE` |
| `eFaultCode` | `NO_FAULT` |
| `rConfirmedSetpoint` | equals the request |
| **F4S front panel SP1** | equals the request, within 1–2 s |

The front panel check is not optional. Status 0 with a matching read-back has
been observed while the panel did **not** follow — this is why the confirmation
path exists.

Cross-check on the Pi:

```bash
sudo journalctl -u f4s-gateway -n 30
# expect: RTU write: reg300 = 265   /   Setpoint write confirmed
```

---

## WebVisu operator page

`WebVisu/codesys_hmi.html` (duplicated at `src/HTML/codesys_hmi.html`) is a
standalone browser page for operators who need setpoint control by keyboard
and mouse instead of the CODESYS watch window. It shows the setpoint as a
tile with a write dialog, range-gates entries to −40…200 °C client-side, and
mirrors the state machine (`IDLE` / `WRITING` / `CONFIRM` / `FAULTED`)
described above.

The page auto-selects a transport at load time (HTTP JSON, WebVisu
`postMessage`, or a bench simulator with no backend) — it does not assume any
one hosting setup. **Wiring it to this project's actual registers (reg0–4,
`GVL_Modbus`) still needs a binding contract document** (e.g.
`docs/HMI_BINDING.md`) that maps the page's expected fields to the Modbus
register map above; that contract does not exist in this repo yet and is an
open item, not something already wired up.

To use it locally: open the file directly in a browser (it falls back to the
bench simulator with no backend), or host it from the Pi alongside the
gateway once a real transport (HTTP endpoint or CODESYS WebVisu) is wired to
`f4s_gateway.py`.

---

## Full build guide — from an empty project

The remainder of this document is the step-by-step build guide, moved here
from the gateway README. Follow it when recreating the CODESYS side from
scratch; the configuration tables above are the authority on final values.

Once T1–T4 tests pass, the gateway is ready for CODESYS integration. This section
walks through configuring the CODESYS IDE to connect to the Python gateway on
10.1.6.17:502 and exchange setpoint/temperature data via Modbus TCP.

**Gateway connection path:** CODESYS IDE (Windows) ←TCP:1740→ CODESYS Control
runtime (Pi) ←TCP:502→ Python F4S Gateway (Pi) ←RTU→ Watlow F4S cabinet.

### Project Structure Overview

The completed CODESYS project tree should match this structure:

```
Temperature Cabinet Setpoint Control for CODESYS HMI (Project)
└── Device (CODESYS Control for Linux ARM64 SL)
    ├── PLC Logic
    │   ├── Application
    │   │   ├── E_FaultCode (ENUM)
    │   │   ├── E_SetpointState (ENUM)
    │   │   ├── GVL_Modbus (Global Variable List)
    │   │   ├── Library Manager
    │   │   └── PLC_PRG (Program)
    │   └── Task Configuration
    │       ├── EtherCAT_Task (IEC-Task) — optional, for EtherCAT I/O
    │       └── MainTask (IEC-Task)
    │           └── PLC_PRG
    ├── EtherCAT_Master (optional, for EtherCAT I/O modules)
    └── Ethernet (Ethernet Device)
        └── Modbus_TCP_Master (Modbus TCP Client)
            └── Modbus_TCP_Slave_Device (Modbus TCP Server / gateway proxy)
```

**Key elements:**
- **PLC Logic → Application:** Contains your DUTs (E_FaultCode, E_SetpointState),
  GVL_Modbus (channel-mapped variables), and PLC_PRG (main cyclic program).
- **Task Configuration → MainTask:** The cyclic entry point. Must call PLC_PRG
  and be the bus cycle task for the Modbus master (see Step 6 for cycle time).
- **Ethernet → Modbus_TCP_Master:** The Modbus TCP client that polls the gateway
  on 10.1.6.17:502 (see Step 2).
- **Modbus_TCP_Slave_Device:** Represents the Python gateway as a remote slave
  with 5 holding registers (see Step 3).

### PLC Settings Configuration

Before configuring devices, set the **PLC Settings** (right-click **Application**
or access via **Project → Project Settings → PLC → General**):

- **Update I/O while in stop:** ☐ (unchecked) — standard setting for this architecture
- **Behavior for outputs in stop:** `Keep current values` — ensures outputs
  maintain state when the program stops (safer for hardware)
- **Always update variables:** ☑ `Enabled 1 (use bus cycle task if not used in
  any task)` — CODESYS refreshes mapped GVL variables on every MainTask cycle,
  so application code always sees fresh Modbus reads and writes happen
  synchronously
- **Bus cycle task:** `MainTask` — confirms GVL I/O variables are synced on the
  MainTask cycle (the same cycle that runs the Modbus master and your PLC program)

These settings ensure the Modbus→GVL sync and PLC logic all run in lockstep on
the same 10 ms MainTask cycle.

### Pre-Configuration: Verify Network Connectivity

**Before adding devices in CODESYS, verify your Windows PC can reach the Pi.**

On your Windows development machine, open Command Prompt and run:

```bash
# Check your local network adapters
ipconfig

# Verify the Pi is reachable
ping 10.1.6.17
```

**Expected output for ipconfig:**
```
Ethernet adapter Ethernet 2:
   IPv4 Address . . . . . . . . : 10.1.6.100   (or any 10.1.6.x address)
   Subnet Mask . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . : 10.1.6.1
```

**Expected output for ping:**
```
Pinging 10.1.6.17 with 32 bytes of data:
Reply from 10.1.6.17: bytes=32 time=1ms TTL=63
...
Ping statistics: Sent=4, Received=4, Lost=0 (0% loss)
```

**If ping fails:**
- Your Windows PC is on a different network than the Pi (10.1.6.x)
- Connect to the network that has the Pi before proceeding
- Contact your network admin to identify the correct network

**Critical:** The Windows PC and Pi MUST be on the same network (10.1.6.0/24) for CODESYS to reach the runtime.

### GVL_Modbus Definition (Create Before Step 1)

Before adding any devices, create the **GVL_Modbus** global variable list in
**Application** with **exactly these variable names and types**. This is the
boundary between the Modbus driver and your PLC logic:

```iec61131
{attribute 'qualified_only'}
VAR_GLOBAL
    (* Reg 2: FC03 cyclic read -> actual chamber temperature raw (x10) *)
    wInput1Value    : WORD;

    (* Reg 3: FC03 cyclic read -> confirmed setpoint read-back raw (x10) *)
    wSetpoint1Read  : WORD;

    (* Reg 4: FC03 cyclic read -> gateway status code
       0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS *)
    wStatus         : WORD;

    (* Reg 0: FC06 write -> requested setpoint raw (x10) *)
    wSetpoint1Write : WORD;

    (* Reg 1: FC06 write (RISING_EDGE only) -> apply trigger pulse (0/1) *)
    xWriteTrigger   : BOOL;

    (* Master/slave diagnostic bits from the device IEC objects *)
    xModbusError    : BOOL;   (* Modbus master error flag *)
    xModbusDone     : BOOL;   (* last transaction completed *)
END_VAR
```

**Critical notes:**
- **Variable names are case-sensitive.** `wInput1Value` (not `wReadTempValue`),
  `wStatus` (not omitted), `wSetpoint1Read`, `wSetpoint1Write`, `xWriteTrigger`.
- **`wStatus` is essential:** `PLC_PRG_TCP.st` checks this register
  to detect faults (COMMS_TIMEOUT, WRITE_FAILED, NOT_ACCEPTED, RANGE). If
  `wStatus` is missing, the program will not compile.
- The **`{attribute 'qualified_only'}`** line at the top enforces qualified
  access (e.g., `GVL_Modbus.wInput1Value`), matching the style of the imported
  program logic.

**Mapping to Modbus registers (shown for reference; I/O Mapping tab wires these):**

| Variable | Modbus Register | Direction | Purpose |
|----------|-----------------|-----------|---------|
| `wInput1Value` | Reg 2 | Read (FC03) | Chamber temperature (°C × 10) |
| `wSetpoint1Read` | Reg 3 | Read (FC03) | Confirmed setpoint read-back (°C × 10) |
| `wStatus` | Reg 4 | Read (FC03) | Gateway status code (0=OK, 1=COMMS, 2=FAIL, 3=REJECT, 4=RANGE, 5=COMMS) |
| `wSetpoint1Write` | Reg 0 | Write (FC06) | Requested setpoint to write (°C × 10) |
| `xWriteTrigger` | Reg 1 | Write (FC06, rising edge) | Pulse to apply the write (0→1 triggers, gateway clears to 0) |

Once created and saved, proceed to **Step 1** to add the Ethernet device.

### Step 1: Add Ethernet Device

In CODESYS IDE, go to **Devices** tree and add an **Ethernet device**:

1. Right-click **Devices** → **Add Device** → select **Ethernet** (generic adapter)
2. A new "Ethernet" device appears under Devices
3. Click the Ethernet device and go to the **General** tab:
   - **Network interface:** Leave blank (auto-detected) OR click **Browse** to select your Windows LAN adapter
     - ⚠️ **Do NOT select 127.0.0.1 (localhost/lo)** — this is your PC's loopback, not the network to the Pi
     - Select the adapter that shows an IP in the 10.1.6.x range, or the Ethernet/WiFi adapter that physically connects to the Pi's network
     - If unsure, leave blank and let CODESYS auto-detect
   - **IP address:** `10.1.6.17` (the Pi's IP address)
   - **Subnet mask:** `255.255.255.0`
   - **Default gateway:** `0.0.0.0` (or leave blank)
   - **Adjust operating system settings:** ☐ (unchecked — do not modify Pi's network config from here)
4. Go to the **Bus Cycle Options** tab:
   - **Bus cycle task:** `MainTask`
   - Click **Recreate required tasks** (auto-generates the task if it doesn't exist)

### Step 2: Add Modbus TCP Master under Ethernet Device

1. Right-click the **Ethernet** device → **Add Device** → select **Modbus TCP Master**
2. Click the new **Modbus TCP Master** device and configure across its tabs:
   - **General** tab:
     - **Response timeout (ms):** `1000` (1 second, enough for the gateway's 1s cyclic RTU poll)
     - **Auto-reconnect:** ☑ **recommended** (optional, but enables automatic reconnection if the link drops)
       - Checked: CODESYS will automatically reconnect if the Pi restarts or connection is lost
       - Unchecked: Manual reconnection required after a connection loss
   - **Modbus TCP Client** tab (parameters):
     - Leave defaults; the actual target IP/port is set per-slave in Step 3, not here
   - **Modbus TCP Client IEC Objects** tab:
     - Leave the auto-generated status/error variables as-is — these are the
       diagnostic bits CODESYS exposes for the master itself (connection state,
       error code). You can map these to `GVL_Modbus.xModbusError` /
       `xModbusDone` later if you want master-level diagnostics distinct from
       the gateway's own `wStatus` register.
   - **Client Mapping / Bus Cycle** tab:
     - **Task:** `MainTask` (confirms the master polls on the same cyclic
       task as the rest of the logic)
   - **Log**, **Status**, **Information** tabs: informational only, same as
     the Ethernet device — nothing to configure here for Phase 1.

### Step 3: Add Modbus TCP Slave and Configure Channels

1. Right-click **Modbus TCP Master** → **Add Device** → select **Modbus TCP Slave**
   (this is the last device in the tree — it represents the Python gateway
   itself as a single remote Modbus slave, Unit ID 1)
2. On the **General** tab, under **Config Parameters**:
   - **IP address:** `10.1.6.17`
   - **Port:** `502` (the Python gateway's TCP port — **do not** use 1740 here,
     that's the CODESYS runtime gateway port, unrelated to this Modbus link)
   - **Slave ID / Unit ID:** `1`
   - **Watchdog:** ☐ leave unchecked for Phase 1 (optional comms-loss detection;
     revisit once basic reads/writes are proven)
3. Still on **General**, under **Configured Parameters** — this section configures the Modbus server behavior:
   - **Watchdog:** ☐ (unchecked for Phase 1) — optional comms-loss detection; revisit after basic reads/writes are proven
   - **Server port:** `502` (the Python gateway's TCP port)
   - **Holding registers:** ☑ **enabled**, **start address `0`**, **size `5`** (covers reg0–reg4, the entire register map)
   - **Input registers:** ☐ (unchecked), size `0` — not used
   - **Writeable:** ☑ **MUST be checked** — this allows CODESYS to WRITE to holding registers (reg0, reg1)
     - When checked: notation changes from %IW (input/read-only) to %QW (output/writable) ✓ This is correct
     - When unchecked: CODESYS can only read, not write — setpoint and trigger writes will fail
   - **Discrete Bit Areas:** ☐ (unchecked)
   - **Coils / Discrete Inputs:** both `0`

4. Still on **General**, under **Data Model** — set start addresses:
   - **Holding register:** `0` (start at register 0)
   - Other addresses: all `0` (not used)
   - **Holding-and input register data areas overlay:** ☐ (unchecked — we don't use input registers)

5. **Serial Gateway** section — ☐ **MUST be UNCHECKED**:
   - **Serial gateway active:** ☐ **UNCHECKED** (critical setting)
   - COM port and Baud rate fields become inactive/grayed out (this is correct)
   - **Why?** The Serial Gateway checkbox is for **transparent** Modbus TCP-to-serial relays that pass raw serial commands. Our Python gateway is NOT transparent — it's a standalone Modbus TCP slave that independently manages its own RTU link to the F4S at 19200 baud. CODESYS does not need to (and cannot) specify serial settings. Leaving it checked interferes with normal TCP communication.
5. Add **5 channels** under the Modbus TCP Slave (one per register):

| Channel | Name | Function Code | Address | Type | Access |
|---------|------|----------------|---------|------|--------|
| 1 | ReadTemp | FC03 (Read) | 2 | WORD | Read |
| 2 | ReadSetpoint | FC03 (Read) | 3 | WORD | Read |
| 3 | ReadStatus | FC03 (Read) | 4 | WORD | Read |
| 4 | WriteSetpoint | FC06 (Write) | 0 | WORD | Write |
| 5 | WriteTrigger | FC06 (Write) | 1 | WORD | Write (rising edge) |

**Register meanings (x10 scaled integers):**
- Reg 0: Requested setpoint (CODESYS → gateway)
- Reg 1: Apply trigger (CODESYS → gateway; pulse when ready)
- Reg 2: Chamber temperature (gateway → CODESYS)
- Reg 3: Confirmed setpoint (gateway → CODESYS)
- Reg 4: Status code (gateway → CODESYS; 0=OK, 2=WRITE_FAILED, 3=NOT_ACCEPTED, 4=RANGE, 5=COMMS)

### Step 4: Create I/O Mapping (Channels → GVL)

The **I/O Mapping** tab on the Modbus TCP Slave device links each Modbus channel
(read/write operation) to a `GVL_Modbus` variable. Both read and write operations
use the unified **Holding Registers** array — indices 0–4 correspond directly to
register addresses, and CODESYS automatically polls/writes based on each
channel's function code (FC03 read, FC06 write).

#### I/O Mapping Interface Overview

The I/O Mapping tab displays:
- **Holding Registers** array section with columns:
  - **Variable:** Name of the GVL_Modbus variable to map
  - **Mapping:** Icon/button to select or edit the mapping
  - **Address:** Register address (0–4; auto-derived from channel definition)
  - **Type:** Data type (always `WORD` for our register map)
  - **Unit:** Optional label (e.g., "°C×10", "status code")
  - **Description:** Optional comment
- **Settings** at the bottom:
  - ☑ **Always update variables:** enabled (set to `1`) — CODESYS refreshes
    mapped GVL variables on every cyclic scan, even if the value didn't change
  - **Bus cycle task:** set to `MainTask` (matches Step 2 and Step 6)

#### Mapping Procedure

For each of the 5 registers, create one I/O mapping by:

1. **Map to the WORD level, not individual bits:**
   - Look for rows labeled "**Holding Registers[0]**, "**Holding Registers[1]**", etc. (%QW1, %QW2, %QW3, %QW4, %QW5)
   - **Do NOT** map to "Bit0", "Bit1", etc. (those are for bit-level access, which we don't need)
   - Modbus registers are always 16-bit WORD values; we read/write the entire register, not individual bits

2. For each Holding Registers[i] row:
   - Click the **Mapping** icon (or right-click → "Map to existing variable")
   - Select **"Map to existing variable"** (do not create new variables — GVL_Modbus already exists)
   - Choose the corresponding `GVL_Modbus` variable (see mapping table below)
   - Verify **Type** is `WORD`
   - (Optional) Add **Unit** label for clarity (e.g., "°C×10" for temperature)

3. **Address strikethrough (before login):**
   - Before you log in to the PLC, addresses will show with strikethrough: ~~%QW1~~, ~~%QW2~~, etc.
   - This is normal — it means CODESYS has planned the mapping but hasn't confirmed it with the PLC device yet
   - After you download the program (Step 7), the strikethrough disappears as CODESYS confirms the mapping online

#### Mapping Table

| Register | Channel | Direction | Function Code | Variable | Address | Type | Unit | Description |
|----------|---------|-----------|----------------|----------|---------|------|------|-------------|
| 0 | WriteSetpoint | Write (CODESYS → gateway) | FC06 | `wSetpoint1Write` | 0 | WORD | °C×10 | Requested setpoint |
| 1 | WriteTrigger | Write (CODESYS → gateway, rising edge only) | FC06 | `xWriteTrigger` | 1 | WORD | (pulse) | Apply write pulse |
| 2 | ReadTemp | Read (gateway → CODESYS) | FC03 | `wInput1Value` | 2 | WORD | °C×10 | Chamber temperature |
| 3 | ReadSetpoint | Read (gateway → CODESYS) | FC03 | `wSetpoint1Read` | 3 | WORD | °C×10 | Confirmed setpoint read-back |
| 4 | ReadStatus | Read (gateway → CODESYS) | FC03 | `wStatus` | 4 | WORD | code | Gateway status (0=OK, 2=FAIL, 3=REJECTED, 4=RANGE, 5=COMMS) |

#### Key Points

- **Unified Holding Registers array:** Don't confuse this with separate "read"
  and "write" register arrays — CODESYS has one Holding Registers array [0–9],
  and each index can have both reads (FC03 to the gateway) and writes (FC06 to
  the gateway) depending on the channel direction. Indices 0–4 are our active
  registers; indices 5–9 are unused.
- **WORD type:** All registers are `WORD` (16-bit unsigned integer). Even
  `xWriteTrigger` (a logical "boolean" trigger) is mapped to a WORD register,
  because Modbus registers are always 16 bits. CODESYS automatically handles
  the bool↔WORD conversion.
- **Always update variables:** Ensure this is enabled (`1`). CODESYS refreshes
  the GVL variables on every MainTask cycle, so application code always sees
  the latest value.
- **Bus cycle task:** Confirm it's set to `MainTask`, the same task that runs
  the Modbus TCP Master and your PLC program. This ensures synchronized reads
  and writes across the entire link (master cyclic poll → update GVL → program
  logic reads/writes GVL → next cycle).

Once all 5 registers are mapped, proceed to Step 5.

### Step 5: Import or Create PLC Program

In your sandbox CODESYS project, replace or create the **PLC_PRG** program:

**Use the state machine from `src/POUs/PLC_PRG_TCP.st`:**
- Copy the full contents into your `PLC_PRG`
- This is self-contained: reads/writes GVL_Modbus only, no dependencies

The state machine handles:
- Edge-triggered write (one pulse per user request via `rReqSetpoint` + `xStartWrite`)
- Range validation (-40–200 °C, enforced on Pi side too)
- Timeout monitoring (300 scans ~ 3 seconds at 10 ms MainTask)
- Fault latching and recovery

### Step 6: Configure MainTask Cycle Time

**MainTask** (auto-created in Step 1) is the cyclic entry point:

1. Right-click **MainTask** in the PLC Logic tree → **Properties**
2. Set **Cycle time:** `10 ms` (matches the state machine timeout constants)
3. Confirm it calls `PLC_PRG` in order

### Step 7: Compile and Download

1. **Build → Generate Code** (F11) — expect 0 errors (no visu libs, clean logic)
2. **Online → Login** (Alt+F8) to the Pi runtime at 10.1.6.17:1740
   - If login fails, check Windows Firewall: allow TCP 1740 outbound to 10.1.6.17
3. Once logged in: **Download** to the PLC
4. **Debug → Start** (F5) to run the program

### Step 8: Live Test via Watch Window

With the program running:

1. Watch `PLC_PRG.rChamberTemp` — should track the cabinet's real temperature (reg2 / 10)
2. Watch `PLC_PRG.rConfirmedSetpoint` — should show the current confirmed SP (reg3 / 10)
3. Set `PLC_PRG.rReqSetpoint` to a new value (e.g., 26.5)
4. Force `PLC_PRG.xStartWrite := TRUE` (rising edge triggers the write)
5. Watch `PLC_PRG.eSetpointState` walk: IDLE → READY → WRITING → CONFIRM → IDLE
6. Confirm `PLC_PRG.rConfirmedSetpoint` snaps to your requested value
7. On any fault, `PLC_PRG.eFaultCode` shows the reason (COMMS_TIMEOUT=1, WRITE_FAILED=2, NOT_ACCEPTED=3, RANGE=4/5)

---

