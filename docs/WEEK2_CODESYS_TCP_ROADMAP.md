# Week 2 Roadmap — CODESYS ↔ Python Gateway (Modbus TCP) PoC

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Window:** Monday 27 July → Friday 31 July 2026
**Goal:** Prove the full CODESYS → Python gateway → Watlow F4S setpoint-control
loop with **zero HMI** — everything operated and proven from the CODESYS
**watch window**, with live values visible and the Modbus TCP Slave device
green and stable.

This document follows the discipline of the "CODESYS Without HMI Only"
package (watch-window-only, Rebuild → Retest → Requalify → Repeat), adapted
to the **TCP gateway architecture** actually in use:

```
CODESYS (Windows IDE ──> Pi runtime)          Python gateway (Pi)        Cabinet
Modbus TCP Master ──> Modbus TCP Slave ──TCP──> f4s_gateway.py ──RTU──> Watlow F4S
        10.1.6.17:502, Unit ID 1              /dev serial, 19200        SP reg 300
```

> The Without-HMI package's serial device tree (Modbus_COM / COM2) does
> **not** apply here — the Python gateway owns the serial port. CODESYS
> never touches serial in this architecture. Everything CODESYS-side is TCP.

---

## 1. Where we finished on Friday 24 July

Proven and working:

- Gateway service (`f4s-gateway.service`) running on the Pi, RTU comms to
  the F4S good — `test_rtu_write.py` passed all three tests (28.0 °C write
  confirmed, 26.5 °C write confirmed, 250 °C correctly rejected).
- CODESYS project builds with **0 errors**; application downloads and runs
  on the Pi runtime (CODESYS Control for Linux ARM64 SL).
- Modbus TCP Slave `ComState = CONNECTED` — the TCP connection itself is
  healthy.
- Watch window shows all five `GVL_Modbus` variables (all reading 0).

Blocked on: **every Modbus transaction fails** — Error Counter = exactly
2 × Request Counter, diagnostic `GATEWAY TARGET FAILED TO RESPOND`, all
watch values stuck at 0, device status toggling green/red.

## 2. Root cause found (do this FIRST on Monday)

### Bug 1 — Unit ID mismatch (the blocker)

The gateway log recorded the smoking gun:

```
pymodbus.logging - ERROR - requested device id does not exist: 255
```

and the raw frames show CODESYS requesting with unit id `0xFF` (255) and
the gateway answering with exception `0x83` (FC03 + 0x80, "gateway target
failed to respond").

`f4s_gateway.py` line 72 serves **only Unit ID 1**:

```python
server_context = ModbusServerContext(devices={1: device}, single=False)
```

The CODESYS Modbus TCP Slave device is sending **Unit ID 255** (the default
when the field was left unset after the device was recreated). Every
request — read or write — is therefore rejected before it ever reaches a
register. This one setting explains the entire Friday failure: connected
socket, permanent exceptions, values frozen at 0.

**Fix (CODESYS IDE, ~5 min):**

1. Device tree → double-click **Modbus_TCP_Slave**.
2. **General** tab → look for a **Unit ID** field → set it to **1**.
3. If your version has no Unit ID on the General tab: open the
   **ModbusTCPSlave Parameters** tab, find the **UnitID** parameter
   (current value 255), set **Value = 1**, then **Write Parameters**.
4. Rebuild → Download → Start.

**Success check:** Status tab → Request Counter climbs, **Error Counter
freezes**, and `GVL_Modbus.wInput1Value` in the watch window shows a
non-zero temperature (x10 raw, e.g. `817` = 81.7 °C).

### Bug 2 — Trigger channel writes 0, not 1 (latent, would block writes)

The gateway fires a setpoint write only when TCP register 1 equals **1**
(`if trigger == 1` in the cyclic loop). A CODESYS rising-edge FC06 channel
works like this: when the mapped **trigger boolean** (row `%QX4.0`, mapped
to `GVL_Modbus.xWriteTrigger`) goes 0→1, the channel sends **the current
value of its mapped data WORD** (row `%QW3`). That data word is currently
**unmapped**, so the channel would write **0** to register 1 — and the
gateway would never fire. Writes would "succeed" and do nothing.

**Fix (~10 min):**

1. Add one variable to `GVL_Modbus` (IDE, and mirror to
   `src/GVLs/GVL_Modbus.gvl` afterwards so the repo stays true):

   ```
   (* Constant 1 sent to reg 1 by the rising-edge trigger channel *)
   wTriggerValue   : WORD := 1;
   ```

2. Modbus_TCP_Slave → **ModbusTCPSlave I/O Mapping** → expand
   **Holding Registers[1]** → map the **WORD data row** (`%QW3`,
   `Holding Registers[1][0]`) to `Application.GVL_Modbus.wTriggerValue`.
3. Leave the **BIT trigger row** (`%QX4.0`) mapped to
   `Application.GVL_Modbus.xWriteTrigger` exactly as it is.

Nothing in `PLC_PRG` changes — the state machine already pulses
`xWriteTrigger` for one scan; the channel now sends `1` on that edge, and
the **gateway clears register 1 back to 0 itself** after processing.

### Bug 3 — Channel 0 stuck on "Application" trigger (latent)

On Friday, channel 0 (Holding Registers[0], the requested-setpoint value)
was changed to trigger type **Application** while debugging. With nothing
in the application driving that channel, `wSetpoint1Write` would **never
be sent to the gateway** — the trigger would fire against a stale/zero
register 0.

**Fix (~2 min):** Modbus Server Channel tab → Edit channel
**Holding Registers[0]** → Trigger = **Cyclic, 1000 ms**.

> Cyclic FC06 on register 0 is safe **in this architecture**: register 0
> is RAM inside the Python gateway, not the F4S. The F4S setpoint register
> is only written when the gateway processes a trigger. (The "never write
> cyclically" EEPROM rule from the RTU packages applies to the F4S's own
> register 300, which the gateway already protects.)

---

## 3. Target configuration — single source of truth

If anything disagrees with this section, this section wins.

### Device tree

```
Device (CODESYS Control for Linux ARM64 SL)
└── Ethernet (Network interface: the adapter that reaches 10.1.6.17)
    └── Modbus_TCP_Master (Modbus TCP Client)
        └── Modbus_TCP_Slave (Modbus TCP Slave)
            General: IP 10.1.6.17 · Port 502 · Unit ID 1 · Response timeout 8000 ms
```

EtherCAT branch (EK1100 + EL modules) is unrelated to this PoC. Ignore its
red/yellow icons this week — do not chase them while proving Modbus.

### Channels (Modbus Server Channel tab)

| # | Name                 | Access type                    | Trigger            | READ offset | WRITE offset | Len | Maps to (I/O Mapping)          |
|---|----------------------|--------------------------------|--------------------|-------------|--------------|-----|--------------------------------|
| 0 | Holding Registers[0] | Write Single Register (FC06)   | **Cyclic 1000 ms** | —           | 16#0000      | 1   | `wSetpoint1Write` (WORD)       |
| 1 | Holding Registers[1] | Write Single Register (FC06)   | **Rising edge**    | —           | 16#0001      | 1   | data WORD → `wTriggerValue`, trigger BIT → `xWriteTrigger` |
| 2 | Holding Registers[2] | Read Holding Registers (FC03)  | Cyclic 1000 ms     | 16#0002     | —            | 1   | `wInput1Value` (WORD)          |
| 3 | Holding Registers[3] | Read Holding Registers (FC03)  | Cyclic 1000 ms     | 16#0003     | —            | 1   | `wSetpoint1Read` (WORD)        |
| 4 | Holding Registers[4] | Read Holding Registers (FC03)  | Cyclic 1000 ms     | 16#0004     | —            | 1   | `wStatus` (WORD)               |

Channel 4 was deleted on Friday while debugging — **re-add it after Bug 1
is fixed**. `PLC_PRG` uses `wStatus` to distinguish COMMS / WRITE_FAILED /
NOT_ACCEPTED / RANGE faults; without it the state machine is blind to
gateway-side failures (an unmapped `wStatus` reads 0 = "OK").

I/O-mapping rules that bit us this week:

- Always map the **element row** (`Holding Registers[n][0]`, type WORD),
  never the ARRAY row. A struck-through address (e.g. ~~%IW82~~) on the
  element row is **normal** — it means the parent array address is
  superseded. A struck-through address caused by **array-vs-scalar type
  mismatch** shows as a mapping that won't take a variable at all.
- **Always update variables = Enabled 1** (or "Enabled 2 / always in bus
  cycle task") on the I/O Mapping tab, and the Ethernet/Modbus master's
  **bus cycle task = MainTask** — never "unspecified".

### Gateway register map (for reference — proven by `test_rtu_write.py`)

| TCP reg | Direction (CODESYS view) | Meaning                          | Scaling |
|---------|--------------------------|----------------------------------|---------|
| 0       | write                    | Requested setpoint               | x10     |
| 1       | write (pulse of 1)       | Apply trigger (gateway clears)   | 0/1     |
| 2       | read                     | Chamber temperature              | x10     |
| 3       | read                     | Confirmed setpoint read-back     | x10     |
| 4       | read                     | Status: 0 OK · 2 WRITE_FAILED · 3 NOT_ACCEPTED · 4 RANGE · 5 COMMS | — |

### Watch window list (create once, save with the project)

```
PLC_PRG.rChamberTemp          PLC_PRG.eSetpointState
PLC_PRG.rReqSetpoint          PLC_PRG.eFaultCode
PLC_PRG.rConfirmedSetpoint    PLC_PRG.xStartWrite
GVL_Modbus.wInput1Value       GVL_Modbus.wSetpoint1Read
GVL_Modbus.wStatus            GVL_Modbus.wSetpoint1Write
GVL_Modbus.xWriteTrigger
```

---

## 4. Day-by-day plan

Each day ends with a **gate**. Do not move to the next day until the gate
passes — the Without-HMI package rule applies: any change ⇒ Rebuild →
Retest → Requalify → Repeat.

### Monday — kill the three bugs, see live values (gate: reads proven)

| Step | Action | Verify |
|------|--------|--------|
| M1 | Pi: `sudo systemctl status f4s-gateway` — restart if not fresh: `sudo systemctl restart f4s-gateway` | active (running), recent DEBUG read logs |
| M2 | Pi: `python3 test_rtu_write.py` (baseline sanity — gateway ↔ F4S leg) | 3/3 tests pass. If status=5 COMMS → restart gateway, retest |
| M3 | **Bug 1:** set Modbus_TCP_Slave **Unit ID = 1** (§2) | — |
| M4 | **Bug 3:** channel 0 trigger back to **Cyclic 1000 ms** | — |
| M5 | **Bug 2:** add `wTriggerValue : WORD := 1` to GVL_Modbus; map Holding Registers[1] data WORD to it | — |
| M6 | Re-add **channel 4** (FC03, offset 16#0004, cyclic 1000 ms) and map to `wStatus` | — |
| M7 | Build (0 errors) → Download → Start | RUN in status bar |
| M8 | Status tab: watch counters for 2 minutes | Requests climb, **errors frozen**, no green/red flicker |
| M9 | Watch window | `wInput1Value` ≈ live temp x10 and updating ~1 s; `wSetpoint1Read` = F4S SP1 x10; `wStatus` = 0 |

**Monday gate = T1 + T2 pass** (see §5). Commit a short log to
`docs/test-logs/2026-07-27_monday.md`.

If M8 still shows climbing errors after the Unit ID fix → go to §6
(Troubleshooting), symptom 1.

### Tuesday — prove the write path from the watch window (gate: T3 + T4)

1. Confirm the F4S front panel is on its **main run page** — the F4S
   silently rejects setpoint writes while its setpoint-edit menu is open
   (read-back shows the old value; the gateway then reports status 3
   NOT_ACCEPTED). Press EXIT/ESCAPE until the run page shows.
2. Watch window: set `PLC_PRG.rReqSetpoint := 26.5` (Prepared value → Ctrl+F7
   to write).
3. Set `PLC_PRG.xStartWrite := TRUE` and write it. The state machine runs
   IDLE → READY → WRITING → CONFIRM → IDLE.
4. Verify, in order:
   - `GVL_Modbus.wSetpoint1Write` = 265
   - `eSetpointState` returns to `IDLE`, `eFaultCode` = `NO_FAULT`
   - `rConfirmedSetpoint` = 26.5, **F4S front panel SP1 shows 26.5** in 1–2 s
5. Repeat with 28.0. Then T5: `rReqSetpoint := 250.0` → expect
   **no write issued**, `eFaultCode = RANGE_HIGH`, state `FAULTED`;
   recover with a fresh trigger after entering a valid value.
6. Gateway-side cross-check on the Pi:
   `sudo journalctl -u f4s-gateway -n 30` → expect
   `RTU write: reg300 = 265` and `Setpoint write confirmed`.

**Tuesday gate = T3, T4, T5 pass once.** Log it.

### Wednesday — full qualification, run 1 (gate: T1–T6 all pass)

Run the complete test plan in §5 top to bottom, recording raw values for
every step. T6 (menu-state silent rejection) is the most valuable test in
the plan — it proves the confirm logic catches real failures instead of
optimistically reporting success.

Also run the **stability soak**: leave the application online 2+ hours;
requests climb by thousands, errors stay frozen, no device flicker.

### Thursday — failure-mode drills, run 2 (gate: two consecutive clean runs)

1. Re-run T1–T6 (second consecutive clean run — PASS rule from the
   packages: two consecutive clean runs, no exceptions).
2. Failure drills (each must fault cleanly and recover without a runtime
   restart):
   - `sudo systemctl stop f4s-gateway` mid-operation → CODESYS device goes
     to error; watch values hold last value (Error Handling = "Keep last
     value") → `start` the service → device recovers, values resume.
   - Trigger a write while the gateway is down → state machine must land
     in `FAULTED` (timeout → NOT_ACCEPTED path), not hang.
   - Restart the CODESYS runtime (`sudo systemctl restart codesyscontrol`)
     → app auto-starts, comms resume.
3. Log everything.

### Friday — requalify, document, demo

1. Morning: full T1–T6 once more (post-drill requalification).
2. Update `codesys-python-tcp-integration/python-gateway/README.md`
   CODESYS section with the final proven settings (Unit ID 1, channel
   table, trigger data-word mapping) — the doc must match reality.
3. Write `docs/CODESYS_TCP_POC_RESULTS.md`: architecture diagram, final
   config tables, T1–T6 results (both runs), failure-drill results, open
   items (§7).
4. Commit + push everything to `Omkar_Temperature_Cabinet_Setpoint_Control`.
5. Demo from the watch window: live temp → set 26.5 → confirmed → range
   reject 250 → fault + recovery. That is the Definition of Done for the
   no-HMI phase.

---

## 5. Test plan (T1–T6, TCP-adapted)

PASS only after **two consecutive clean runs** (Wed + Thu).

| # | Test | Method | Pass criteria |
|---|------|--------|---------------|
| T1 | Temp read | Compare `rChamberTemp` to F4S front panel | Match ±0.1 °C, updates ~1 s |
| T2 | Setpoint read | Compare `rConfirmedSetpoint` to F4S SP1 | Exact match |
| T3 | Setpoint write | F4S on main page. `rReqSetpoint := 26.5`, toggle `xStartWrite` | F4S SP1 → 26.5 °C in 1–2 s |
| T4 | Write confirm | Watch after T3 | State `IDLE`, `eFaultCode = NO_FAULT`, `rConfirmedSetpoint = 26.5` |
| T5 | Range reject | `rReqSetpoint := 250.0`, toggle `xStartWrite` | **No write issued**, `eFaultCode = RANGE_HIGH`, state `FAULTED`; gateway log shows no RTU write |
| T6 | Menu-state silent reject | Open the F4S setpoint-edit screen, repeat T3 | Gateway status 3 → `eFaultCode = NOT_ACCEPTED`, state `FAULTED` — proves confirmation is real |

Recovery after every FAULTED test: set a valid `rReqSetpoint`, toggle
`xStartWrite` → state machine re-enters READY and clears the fault.

## 6. Troubleshooting decision tree

Everything below was either hit this week or is the next most likely trap.

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| 1 | Errors ≈ 2× requests, `GATEWAY TARGET FAILED TO RESPOND`, values 0 | Unit ID ≠ 1 (CODESYS default 255) | §2 Bug 1. Verify on the Pi: `sudo journalctl -u f4s-gateway -n 20` — if you see `requested device id does not exist: N`, CODESYS is sending unit N |
| 2 | Reads fine, write "succeeds" but F4S never changes, no fault | Trigger channel data word unmapped → writes 0 to reg 1 | §2 Bug 2 — map data WORD to `wTriggerValue` (=1) |
| 3 | `wSetpoint1Write` shown in watch but gateway reg 0 stays 0 | Channel 0 trigger left on "Application" | §2 Bug 3 — Cyclic 1000 ms |
| 4 | `test_rtu_write.py` fails, status = 5 (COMMS), temp frozen | Stale serial connection in gateway (USB re-enumeration) | `sudo systemctl restart f4s-gateway`, wait 5 s, retest. Happened twice this week — first reflex on any status-5 |
| 5 | CODESYS log: `Connect failed! (Socket-Error = 111)` | Gateway not listening (service down/restarting) | `sudo systemctl status f4s-gateway` → start it; CODESYS reconnects on its own |
| 6 | Watch window completely empty / no values | App not running, or monitoring not active | Status bar must say RUN; re-login (Alt+F8) if stale |
| 7 | `wStatus` reads 3 (NOT_ACCEPTED) on every write | F4S front panel sitting in setpoint-edit menu | EXIT to main run page (§4 Tuesday step 1) |
| 8 | Address struck through and mapping rejected | Mapped the ARRAY row or type mismatch (BOOL↔WORD) | Map the element row `[n][0]`; trigger boolean only on the BIT row |
| 9 | Everything green but values frozen | "Always update variables" off / bus cycle task unspecified | Enable it; set bus cycle task = MainTask; rebuild + download |
| 10 | Port 502 conflict / `ERROR_ADDR_IN_USE` on Pi | A second server bound to 502 (e.g. a CODESYS "Slave **Device**" acting as server) | Only the Python gateway owns 502. The CODESYS device must be the *client-side* "Modbus TCP Slave" under the Master |
| 11 | Device tree red after gateway restart, never recovers | TCP auto-reconnect stalled | Stop → Start the application; if persistent, power-cycle nothing — check `ping 10.1.6.17` first |

Escalation rule (from the dev package): if the master won't stabilise
after config + cabling are verified, capture evidence (Status tab counters,
`journalctl -u f4s-gateway`, wireshark/tcpdump on port 502 if needed)
**before** touching code.

## 7. Open items — decide with TL, do not improvise

1. **Gateway range check vs. F4S range.** The gateway validates
   0–2000 (0–200 °C) but the cabinet range is −40…200 °C and `PLC_PRG`
   allows −40. Negative setpoints (x10 two's-complement WORD) would be
   rejected by the gateway today. Needs a deliberate gateway change +
   retest — **only with explicit approval**.
2. **`test_rtu_write.py` 9-test expansion** (full −40…200 °C sweep) —
   prepared conceptually, waiting for cabinet access + approval. Do not
   change the proven baseline script before then.
3. **F4T cabinet (Ethernet-native)** — future phase, out of scope this week.
4. **Gateway resilience** — status-5 needed two manual service restarts
   this week. Candidate fix: serial reconnect/watchdog inside the gateway
   or systemd `Restart=` hardening. Needs approval.
5. **WebVisu/HMI phase** — returns only after this package's exit
   criteria (T1–T6 twice) are met, per the Without-HMI package.

## 8. Contingency — if Unit ID cannot be set in CODESYS

If your CODESYS version genuinely exposes no Unit ID field (General tab
and Parameters tab both), the fallback is a **one-line gateway change** to
serve both unit ids:

```python
server_context = ModbusServerContext(devices={1: device, 255: device}, single=False)
```

Workflow if needed: request the change → it gets committed to
`Omkar_Temperature_Cabinet_Setpoint_Control` → on the Pi:
`cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI && git pull
&& sudo systemctl restart f4s-gateway`. Do **not** hand-edit the file on
the Pi — the repo is the source of truth.

## 9. Daily log template (`docs/test-logs/2026-07-2X_day.md`)

```markdown
# <Day> <Date> — CODESYS TCP PoC log
## Gateway baseline
- systemctl status: ...        - test_rtu_write.py: PASS/FAIL (details)
## Changes made today
- ...
## Counters (after 10 min online)
- Requests: ...  Errors: ...  ComState: ...
## Tests run
- T1: PASS/FAIL (raw values: ...)
- ...
## Issues hit + fixes
- symptom → cause → fix (add new ones to roadmap §6)
## Carry-over for tomorrow
- ...
```

---

**Discipline: Rebuild → Retest → Requalify → Repeat. No step skipped.**
