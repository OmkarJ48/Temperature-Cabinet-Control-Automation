# Setpoint Range Investigation — why −40…200 °C behaved like 0.1…100 °C

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Date:** 27 July 2026
**Trigger:** Watch-window testing showed the documented −40…200 °C range
behaving, in practice, as roughly 0.1…100 °C.

---

## 1. Observed symptoms

Four distinct behaviours were seen from the CODESYS watch window, all of which
looked like "the range is wrong" but have **three different root causes**.

| # | What was done | What was observed | Layer at fault |
|---|---|---|---|
| A | `rReqSetpoint := -1.0`, trigger | `eFaultCode = RANGE_HIGH`, `FAULTED`, `wSetpoint1Write = 65526` | Gateway (2) |
| B | `rReqSetpoint := 125.0`, trigger | Watch showed accepted (`IDLE`, `NO_FAULT`, readback 1250) but **front panel did not follow** | F4S device (3) |
| C | `rReqSetpoint := 100.0`, trigger | Behaved as a ceiling | F4S device (3) |
| D | `rReqSetpoint := 99.0`, trigger | `NOT_ACCEPTED`, readback stuck at `1000` | Confirm timeout (1c) |

The key insight: **a setpoint passes through three independent range gates**,
and each one fails differently. Fixing one does not fix the others.

```
  watch window
       │
       ▼
  ┌─────────────────────────────────────────┐
  │ GATE 1  PLC_PRG                         │  rMinSetpoint / rMaxSetpoint
  │         rReqSetpoint validated          │  −40.0 … 200.0        ← code
  └─────────────────────────────────────────┘
       │  scaled ×10 into a WORD
       ▼
  ┌─────────────────────────────────────────┐
  │ GATE 2  f4s_gateway.py                  │  SP_MIN_X10 / SP_MAX_X10
  │         sp_req validated                │  −400 … 2000          ← code
  └─────────────────────────────────────────┘
       │  FC06 over RTU to register 300
       ▼
  ┌─────────────────────────────────────────┐
  │ GATE 3  the Watlow F4S itself           │  setpoint low/high limit
  │         device setup parameters         │  ??? ← DEVICE CONFIG, not code
  └─────────────────────────────────────────┘
       │
       ▼
  cabinet actually moves
```

---

## 2. Root causes

### Cause 1 — signedness (three separate code defects)

Modbus holding registers are 16 bits with **no inherent signedness**. Both ends
must agree on the interpretation. Temperatures and setpoints here are *signed*
×10 integers, but three places treated them as unsigned.

**1a. Gateway validated the raw unsigned word.** This is symptom A.

```python
# before
if 0 <= sp_req <= 2000:          # sp_req is the RAW register word
```

`-1.0 °C` is `-10` ×10, which on the wire is `0xFFF6` = **65526**. That is
greater than 2000, so the gateway returned `ST_RANGE` (4) for *every* negative
setpoint. The floor was effectively **0.0 °C**, not −40.0 °C. `65526` is exactly
the `wSetpoint1Write` value observed in the watch window — the smoking gun.

```python
# after
sp_signed = u16_to_i16(sp_req)
if SP_MIN_X10 <= sp_signed <= SP_MAX_X10:    # -400 .. 2000
```

**1b. PLC_PRG read back unsigned.** `WORD` is unsigned in IEC 61131-3:

```pascal
(* before *)
rChamberTemp       := GVL_Modbus.wInput1Value  / 10.0;
rConfirmedSetpoint := GVL_Modbus.wSetpoint1Read / 10.0;
```

A −1.0 °C read-back (`16#FFF6`) becomes `6552.6`, not `-1.0`. So even after
fixing 1a, the `CONFIRM` state's comparison
`ABS(rConfirmedSetpoint - rReqSetpoint) < 0.1` could **never** match a negative
setpoint — it would always time out into `NOT_ACCEPTED`. Sub-zero chamber
temperatures would also have displayed as ~6550 °C.

```pascal
(* after *)
rChamberTemp       := WORD_TO_INT(GVL_Modbus.wInput1Value)  / 10.0;
rConfirmedSetpoint := WORD_TO_INT(GVL_Modbus.wSetpoint1Read) / 10.0;
```

**1c. PLC_PRG wrote via an undefined conversion.**

```pascal
(* before *)
GVL_Modbus.wSetpoint1Write := DWORD_TO_WORD(REAL_TO_DWORD(rReqSetpoint * 10.0));
```

`REAL_TO_DWORD` is **undefined for negative operands** in IEC 61131-3. On this
runtime it happened to produce the correct bit pattern — which is why `65526`
appeared at all rather than `0` — but that is luck, not contract. It also
*truncates* rather than rounds, so `26.45 → 264` instead of `265`.

```pascal
(* after *)
GVL_Modbus.wSetpoint1Write := INT_TO_WORD(REAL_TO_INT(rReqSetpoint * 10.0));
```

`REAL_TO_INT` rounds and is defined across the whole −40…200 range;
`INT_TO_WORD` reinterprets the signed value as the two's-complement word.

### Cause 2 — RANGE faults always reported as `RANGE_HIGH`

The gateway reports a single `RANGE` status (4) with no direction. PLC_PRG
mapped it unconditionally:

```pascal
(* before *)
ELSIF GVL_Modbus.wStatus = 4 THEN
    eFaultCode := E_FaultCode.RANGE_HIGH;    (* or RANGE_LOW; Python validates *)
```

So a −1.0 °C request that tripped the gateway's **floor** was reported as
`RANGE_HIGH`. That is precisely why symptom A sent us hunting for a ceiling
problem when the real fault was at the bottom of the range. Now resolved from
the request actually sent.

### Cause 3 — confirm timeout shorter than the confirm chain

This is symptom D. `dwMaxTimeout` was `300` (≈3 s at a 10 ms MainTask), but the
worst-case confirmation chain is longer:

| Stage | Time |
|---|---|
| Gateway cyclic poll period (`POLL_PERIOD`) | 1.0 s |
| Gateway RTU read-back confirm (`READ_TIMEOUT`) | 0.5 s |
| CODESYS cyclic read of reg 3 (channel 3 trigger) | 2.0 s |
| **Worst case total** | **3.5 s** |

3.5 s against a 3.0 s timeout → the state machine gives up on writes the F4S
*had already accepted* and reports `NOT_ACCEPTED`. Raised to `1000` (≈10 s).
Genuine failures still fault fast, because the gateway's own status codes
(2 / 3 / 5) short-circuit the wait — the headroom only affects the
no-news-yet path.

> Consider also dropping read channels 2/3/4 from 2000 ms to 500 ms. That cuts
> the worst case to ~2 s and makes the watch window noticeably more responsive.
> It costs four extra FC03 transactions per second, which this link handles
> comfortably (Error Counter has stayed frozen at 0 through the soak).

### Cause 4 — the F4S's own setpoint limits (NOT a code problem)

This is symptoms B and C, and it is the one **no code change can fix**.

Symptom B is the important one: 125.0 °C reported success at every software
layer — status 0, read-back 1250, state `IDLE`, `NO_FAULT` — while the front
panel did not follow. That combination means the F4S **acknowledged the Modbus
frame and echoed the register**, but did not adopt the value as its working
setpoint. A controller clamping to its own configured limit behaves exactly
like this.

The F4S has setpoint low/high limit parameters in its own setup menu. If those
are set to, say, 0…100, then the cabinet will refuse anything outside that
regardless of what PLC_PRG and the gateway permit. The observed ~100 °C ceiling
is consistent with exactly that.

**This must be measured on the hardware, not assumed.** See §3, step 3.

---

## 3. Step-by-step verification procedure

Work these in order. Each step isolates one layer, so a failure tells you
exactly which gate is responsible.

### Step 0 — deploy the fixes

On the Pi:

```bash
cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
git pull origin Omkar_Temperature_Cabinet_Setpoint_Control
```

> **The gateway folder was renamed** from
> `codesys-python-tcp-integration/python-gateway/` to `python-rtu-integration/`.
> The systemd unit points at the old path and **will fail to start** until it is
> updated:
>
> ```bash
> sudo systemctl edit --full f4s-gateway
> # update ExecStart= and WorkingDirectory= to .../python-rtu-integration
> sudo systemctl daemon-reload
> sudo systemctl restart f4s-gateway
> sudo systemctl status f4s-gateway     # expect: active (running)
> ```

In CODESYS: paste the updated `PLC_PRG_TCP_Retargeted.st`, then
Build → Download → Start.

### Step 1 — prove the gateway leg alone (isolates gate 2)

Gateway running, CODESYS irrelevant here:

```bash
cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/python-rtu-integration
python3 test_rtu_write.py        # the proven 3-test baseline — must still pass
python3 test_range_sweep.py      # the new -40..200 qualification
```

**Expected:** baseline 3/3. Sweep passes every in-range case including −40.0,
−15.5 and −1.0, and correctly *rejects* 200.1 and −40.1.

**If negative setpoints still report RANGE:** the gateway did not restart with
the new code. Check `sudo journalctl -u f4s-gateway -n 30`.

**If negative setpoints report RANGE-free but the read-back never matches:**
the F4S itself is refusing them — go to step 3.

### Step 2 — prove the CODESYS leg (isolates gates 1 and the confirm logic)

From the watch window, with the F4S on its **main run page**:

| Setpoint | Expect |
|---|---|
| `26.5` | `IDLE`, `NO_FAULT`, `rConfirmedSetpoint = 26.5` — regression check |
| `-1.0` | `IDLE`, `NO_FAULT`, `rConfirmedSetpoint = -1.0`, `wSetpoint1Write = 65526` |
| `-40.0` | `IDLE`, `NO_FAULT`, `rConfirmedSetpoint = -40.0` |
| `200.0` | `IDLE`, `NO_FAULT`, `rConfirmedSetpoint = 200.0` |
| `200.1` | `FAULTED`, `eFaultCode = RANGE_HIGH`, **no write issued** |
| `-40.1` | `FAULTED`, `eFaultCode = RANGE_LOW`, **no write issued** |

Note the last row: `RANGE_LOW` (not `RANGE_HIGH`) is now the correct result and
is itself part of the test.

**Watch `rChamberTemp` while the cabinet is below 0 °C** — it must show the
negative value, not ~6550. That confirms fix 1b.

### Step 3 — measure the F4S's own limits (isolates gate 3)

This is the step that answers symptoms B and C, and it must be run against the
hardware. Stop the gateway first — both processes want the serial port.

```bash
sudo systemctl stop f4s-gateway
cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI/python-rtu-integration

# read-only survey first: changes nothing
python3 probe_f4s_limits.py

# then the authoritative measurement (WRITES setpoints — cabinet will move)
python3 probe_f4s_limits.py --sweep --yes

sudo systemctl start f4s-gateway
```

The sweep binary-searches the boundary between accepted and rejected setpoints
and prints the range the device **actually** honours. Read-back equality is the
only trustworthy test — the F4S acknowledges the FC06 frame even when it
silently clamps, which is exactly the trap symptom B fell into.

**Interpreting the result:**

- **Reports −40.0 … 200.0** → all three gates now agree. Range fully qualified;
  proceed to the HMI phase.
- **Reports a narrower range (e.g. 0.0 … 100.0)** → this is the F4S's own
  configuration. Raise its setpoint low/high limits from the front panel
  (`SETUP` → `CONTROL` / `INPUT 1` — consult the F4S manual for the exact menu
  path on your firmware), then re-run the sweep to confirm.
- **Reports something odd around 0** → check whether the F4S input is
  configured for a thermocouple type whose own range starts at 0.

> The front panel and the Modbus register can disagree. Always trust the
> read-back-plus-panel combination over the Modbus acknowledgement alone.

### Step 4 — requalify

Once step 3 shows the full range, re-run steps 1 and 2 end to end, twice, per
the Week-2 discipline (two consecutive clean runs). Only then is −40…200 °C
proven.

---

## 4. Summary of changes

| File | Change |
|---|---|
| `python-rtu-integration/f4s_gateway.py` | Signed range check (`SP_MIN_X10 = -400`, `SP_MAX_X10 = 2000`); `u16_to_i16` / `i16_to_u16` helpers; sign-correct log lines |
| `codesys-python-gateway-modbus/src/POUs/PLC_PRG_TCP_Retargeted.st` | `WORD_TO_INT` on both reads; `INT_TO_WORD(REAL_TO_INT(...))` on the write; `RANGE_LOW`/`RANGE_HIGH` resolved by direction; `dwMaxTimeout` 300 → 1000 |
| `python-rtu-integration/probe_f4s_limits.py` | **New.** Measures the F4S's own limits over RTU |
| `python-rtu-integration/test_range_sweep.py` | **New.** Full −40…200 qualification over TCP |
| `python-rtu-integration/test_rtu_write.py` | **Unchanged** — proven baseline preserved deliberately |

## 5. Open items

1. **F4S device limits are still unmeasured.** Step 3 has not been run yet. Until
   it is, the effective top of the range is unknown; the ~100 °C ceiling
   observed in testing is unexplained by any code path and is almost certainly
   the device's own configuration.
2. **Changing the F4S's setpoint limits is a cabinet configuration change.**
   Confirm with the TL before altering the controller's setup menu — it affects
   anything else that drives this cabinet, not just this project.
3. **Read-channel interval** (2000 ms → 500 ms) is recommended but not applied;
   it changes bus loading, so it belongs in a deliberate change with its own
   soak test.
