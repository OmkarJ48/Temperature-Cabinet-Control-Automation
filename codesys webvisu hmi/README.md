# CODESYS WebVisu HMI — Temperature Cabinet Setpoint Control

**Status:** Design phase. The control layer (setpoint write and cabinet on/off automation) is complete and qualified on hardware. This folder contains the operator interface development.

**Objective:** Build a professional WebVisu operator page for remote temperature cabinet control, binding visualization elements to `GVL_HMI` rather than directly to `GVL_Modbus`, maintaining strict driver boundary separation.

---

## Development requirements

The WebVisu HMI must provide:

### Operator interface
- [ ] **Live temperature display** — real-time cabinet temperature from `GVL_HMI.rCurrentTemperature`
- [ ] **Current setpoint display** — current configured setpoint from `GVL_HMI.rCurrentSetpoint`
- [ ] **Requested setpoint entry** — numeric input field for operator to request new setpoint (with −40…200 °C range constraint as input constraint, in addition to three existing firmware gates)
- [ ] **Accept/Reject indication** — explicit visual feedback when:
  - Write is accepted (READY → WRITING)
  - Write succeeds (WRITING → CONFIRM → READY)
  - Write fails (CONFIRM timeout or F4S rejection)

### Fault handling and diagnostics
- [ ] **Fault code surface as readable text** — `GVL_HMI.eE_FaultCode` enum converted to operator-friendly strings:
  - `E_No_Fault` → "No Fault"
  - `E_Modbus_Timeout` → "Modbus Timeout — Gateway unreachable"
  - `E_Out_of_Range` → "Requested setpoint outside cabinet range (−40…200 °C)"
  - `E_Ramp_In_Progress` → "Setpoint ramp in progress"
  - `E_Panel_Lock` → "Cabinet front panel lock enabled"
  - `E_Confirm_Timeout` → "Setpoint confirmation timeout — cabinet did not respond"
  - `E_Cabinet_Not_Ready` → "Cabinet not ready for new command"
- [ ] **Comms health indicator** — driven by the confirm-timeout path since the gateway status register cannot report its own absence. Show:
  - Green (comms OK) — last confirm completed within timeout window
  - Yellow (comms degrading) — confirming, but within warning threshold
  - Red (comms lost) — confirm timeout, gateway unreachable

### Control interlocks and state machine reflection
- [ ] **Write interlock** — no new write accepted while a write is in flight (`READY` / `WRITING` / `CONFIRM` states). Grey out setpoint entry field while in-flight.
- [ ] **State display** — optional, for debugging:
  - Current state (`READY`, `WRITING`, `CONFIRM`)
  - Confirm timeout countdown (when in CONFIRM state)

### Design constraints
- Bind ALL visualization elements to `GVL_HMI.*` variables, **never** directly to `GVL_Modbus.*`
- Keep the driver boundary intact — the HMI layer must not know about Modbus registers, unit IDs, or function codes
- Three independent range gates exist in firmware (F4S PID, CODESYS, Modbus write); the HMI adds a fourth as input constraint for user guidance
- Watch-window qualification already proved the control layer; this HMI proves the presentation layer only

---

## Reference implementation

The existing proof-of-concept HMI page is located at:
[`../codesys modbus proof of concept and test logs/WebVisu/codesys_hmi.html`]

This layout serves as the starting point. Current state:
- Basic HTML/CSS/JavaScript structure
- Placeholder elements for temperature, setpoint, and state
- Minimal styling and no fault handling

**Next steps:**
1. Review the reference page for structure and element naming conventions
2. Enhance HTML semantic structure if needed (labels, ARIA attributes)
3. Implement fault code mapping and comms health indicator
4. Add range constraint input validation (−40…200 °C)
5. Wire all visualization elements to `GVL_HMI` variables via WebVisu binding

---

## Folder structure

```
codesys webvisu hmi/
├── README.md                          (this file)
├── WebVisu/
│   └── html/
│       └── codesys_hmi.html           (operator page — reference implementation)
├── docs/
│   └── (design notes, test procedures, user manual drafts)
└── tests/
    └── (operator test logs, drill 3 runtime restart evidence)
```

---

## GVL_HMI variable contract

The WebVisu HMI binds to the following `GVL_HMI` variables (defined in CODESYS):

| Variable | Type | Direction | Purpose |
|----------|------|-----------|---------|
| `rCurrentTemperature` | REAL | Read | Live cabinet temperature in °C |
| `rCurrentSetpoint` | REAL | Read | Current setpoint in °C |
| `rRequestedSetpoint` | REAL | Read/Write | Operator-requested setpoint (written by HMI) |
| `eE_FaultCode` | E_FaultCode (enum) | Read | Current fault status |
| `eCabinetState` | E_ControlState (enum) | Read | Control state: READY, WRITING, CONFIRM |
| `tConfirmRemain` | TIME | Read | Milliseconds remaining before confirm timeout (0 when not in CONFIRM) |
| `xSetOperational` | BOOL | Read | EL2869 operational status (comms health) |

**Fault code enumeration (E_FaultCode):**
```codesys
TYPE E_FaultCode :
	(
	E_No_Fault := 0,
	E_Modbus_Timeout := 1,
	E_Out_of_Range := 2,
	E_Ramp_In_Progress := 3,
	E_Panel_Lock := 4,
	E_Confirm_Timeout := 5,
	E_Cabinet_Not_Ready := 6
	)
END_TYPE
```

**Control state enumeration (E_ControlState):**
```codesys
TYPE E_ControlState :
	(
	READY := 0,
	WRITING := 1,
	CONFIRM := 2
	)
END_TYPE
```

---

## Operator workflows

### Normal setpoint change (happy path)

1. Operator observes current temperature and setpoint on HMI
2. Operator enters new setpoint in input field (−40…200 °C range enforced by input constraint)
3. Operator presses "Set Setpoint" button
4. HMI writes `rRequestedSetpoint` and monitors `eCabinetState`:
   - Button greyed out, state shows "WRITING"
   - Control layer attempts Modbus write to F4S
5. F4S accepts and begins ramp; `eCabinetState` → CONFIRM
   - State shows "Waiting for confirmation…"
   - Countdown timer shows remaining time (for debugging)
6. CODESYS confirms setpoint read-back matches; `eCabinetState` → READY
   - State shows "Ready" (green)
   - Button re-enabled
7. Temperature begins ramping to new setpoint

### Setpoint rejected by F4S (out of range or panel lock)

1. Operator enters setpoint outside cabinet's supported range
2. HMI writes request; F4S rejects (Modbus write ACK but value not accepted)
3. CODESYS detects mismatch in confirm read; `eE_FaultCode` → appropriate error
4. HMI displays fault text: "Requested setpoint outside cabinet range (−40…200 °C)" (example)
5. Operator sees fault, clears it (acknowledged), and retries with valid setpoint

### Gateway timeout (comms lost)

1. Operator initiates setpoint write
2. Python gateway crashes or network link drops
3. CODESYS detect Modbus timeout; `eE_FaultCode` → E_Modbus_Timeout
4. HMI displays: "Modbus Timeout — Gateway unreachable" (red)
5. Comms health indicator turns red
6. Operator waits for gateway restart or troubleshoots network

---

## Development phases

### Phase 1: Layout and basic binding (in progress)
- [ ] Review reference codesys_hmi.html structure
- [ ] Enhance HTML for accessibility (labels, ARIA)
- [ ] Set up WebVisu data bindings to `GVL_HMI` variables
- [ ] Test display of live temperature and setpoint

### Phase 2: Setpoint write and interlock
- [ ] Implement setpoint entry with −40…200 °C input constraint
- [ ] Wire setpoint "Set" button to write `rRequestedSetpoint`
- [ ] Implement state machine reflection:
  - Grey out button during WRITING/CONFIRM states
  - Display state text (READY/WRITING/CONFIRM/CONFIRM countdown)
- [ ] Test interlock prevents simultaneous writes

### Phase 3: Fault handling and diagnostics
- [ ] Implement fault code enumeration-to-text mapping
- [ ] Display fault code and friendly error message
- [ ] Implement fault acknowledgement (clears error once user confirms)
- [ ] Add comms health indicator logic (drive from `tConfirmRemain` and `xSetOperational`)

### Phase 4: Operator testing and documentation
- [ ] Operator test pass (happy path, error cases, timeout scenarios)
- [ ] Capture Drill 3 (runtime restart) with evidence:
  - HMI remains responsive during CODESYS download
  - Setpoint write survives restart
  - State machine restarts in READY
- [ ] Operator manual (screenshot walkthrough, fault reference)
- [ ] Sign-off checklist

---

## Testing and qualification

### Operator test plan

Before handoff to the R&D team:

| # | Test | Setup | Action | Expected | Evidence |
|---|------|-------|--------|----------|----------|
| OT-1 | Display live temperature | Cabinet running | Observe HMI | Temperature updates every 1–2 seconds | Screenshot of stable display |
| OT-2 | Display current setpoint | Cabinet running | Observe HMI | Setpoint matches cabinet F4S | Screenshot |
| OT-3 | Input constraint: below range | HMI displayed | Enter −50 °C | Input rejected or warned | Input field state screenshot |
| OT-4 | Input constraint: above range | HMI displayed | Enter +250 °C | Input rejected or warned | Input field state screenshot |
| OT-5 | Happy path: setpoint accepted | Cabinet idle | Enter +50 °C, press Set | State: WRITING → CONFIRM → READY; temperature ramps to +50 | Timeline screenshot |
| OT-6 | Fault: F4S rejects setpoint | Cabinet running with panel lock | Enter setpoint | Fault code displayed: "Cabinet front panel lock enabled" | Error message screenshot |
| OT-7 | Fault: gateway timeout | Gateway running | Stop gateway; initiate write | Fault code: "Modbus Timeout — Gateway unreachable"; red comms indicator | Error screenshot |
| OT-8 | Fault: confirm timeout | Gateway latency high | Initiate setpoint write | Fault code: "Setpoint confirmation timeout"; red comms | Timeout screenshot |
| OT-9 | Interlock: no simultaneous writes | Cabinet idle | Initiate write; try second write while first in-flight | Second write button stays greyed out until first completes | Button state screenshot |
| OT-10 | Drill 3: runtime restart | CODESYS online, setpoint write in-flight | Download CODESYS project; HMI remains responsive | Page does not freeze; write state survives restart | Timeline with console logs |

### Drill 3 — Runtime restart evidence

Capture and document:
1. Screenshot of HMI state before CODESYS download (setpoint in-flight)
2. Console log showing CODESYS stopped and restarted
3. Screenshot of HMI state after restart (write completed correctly)
4. Timestamp proof that setpoint persisted across restart

---

## Integration with cabinet on/off automation

The cabinet on/off automation (remote start/stop) and setpoint control are independent:
- Setpoint write uses EL2869 channels CH13 (Modbus TCP write signal) and CH14 (Modbus RTU control)
- Cabinet on/off automation uses EL2869 channels CH15 (start pulse) and CH16 (stop permit)
- No conflict; HMI for setpoint can be tested independently of start/stop automation

---

## References

| Document | Location | Purpose |
|----------|----------|---------|
| CODESYS PLC source | `../codesys modbus proof of concept and test logs/` | `GVL_HMI` and `PLC_PRG` definitions; state machine logic |
| Python gateway | `../python modbus proof of concept and test logs/` | Modbus TCP server (register map, comms behavior) |
| Cabinet on/off automation | `../commissioning of temperature cabinets/` | On/off design; independent of setpoint control |
| Reference HMI layout | `WebVisu/html/codesys_hmi.html` | Proof-of-concept HTML/CSS structure |

---

## Next steps

1. Review the reference `codesys_hmi.html` page to understand current HTML structure
2. Identify all `<input>`, `<div>`, and `<span>` elements that need WebVisu bindings
3. Create WebVisu binding definitions for each `GVL_HMI.*` variable
4. Implement fault code text mapping in JavaScript
5. Test binding and display updates using WebVisu live data
6. Execute operator test plan (OT-1 through OT-10)
7. Capture and document Drill 3 evidence
8. Prepare operator manual and sign-off

---

**Last updated:** 17 August 2026

**Status:** Ready for development phase 1 (layout and binding review).
