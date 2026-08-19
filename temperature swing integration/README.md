# Temperature Swing Integration

**Parent project:** Temperature Cabinet Setpoint Control from CODESYS HMI
**Compliance target:** API 6A — Temperature Testing (F.1.9), Hold Periods /
Stabilisation (F.1.10), Pressure/Temperature Cycles (F.1.11)
**Status:** Design complete (Stage 2), deliverable source files drafted
(Stage 3 draft), **not yet imported into the live CODESYS project or backend
— see the implementation checklist below before treating anything here as
commissioned.**

---

## What this adds

The parent repository proves two things end to end on hardware: remote
setpoint control and remote on/off automation of a temperature cabinet. This
folder adds the piece needed for API 6A compliance testing: an automated
**ramp → stabilise → hold → return** test cycle that

- drives the cabinet to an operator-specified extreme temperature,
- enforces a rate-of-change limit of **&lt;0.5&deg;C/min** during ramp and return,
- establishes and holds chamber pressure at **0/50/75/100%** of test pressure
  throughout,
- tracks overshoot against the **11&deg;C** ceiling past the extreme,
- holds at the extreme for an operator-specified duration, and
- logs the full cycle to CSV for compliance records.

It reuses the existing pressure-application function block and solenoid
control pattern rather than duplicating them — see
`docs/Stage2_Design_Document.md` Section 6 for exactly what is reused vs. new.

---

## Folder layout

| Folder | Owns |
|---|---|
| [`remote ssh vs code 10.1.6.40 setup guide/`](remote ssh vs code 10.1.6.40 setup guide/) | Remote SSH + GitHub workflow for 10.1.6.40 R&D Prototype Pi (Stage 1 tooling) |
| [`Development_history/`](Development_history/) | Stage-by-stage development progress: SSH setup, design reviews, PoC logs, hardware test results |
| [`Stage_2_Design_Review/`](Stage_2_Design_Review/) | Design investigation: existing DLS patterns, findings, design documents |
| [`docs/`](docs/) | Design document, GVL variable reference, hardware test plan |
| [`codesys/`](codesys/) | Structured Text: state machine, GVL variables, state enum |
| [`backend/`](backend/) | Python OPC UA manager, node map, WebSocket broadcaster, unit tests |
| [`frontend/`](frontend/) | HMI start dialog, live progress page, shared JS client |

Each folder has its own README with file-by-file detail and integration
steps specific to that layer.

**Development approach:** Same as Temperature Cabinet Control Stages 1–8 — investigate → document → build PoC → test → iterate. See [`Development_history/`](Development_history/) for the running log.

---

## How the pieces connect

```
Operator (HMI)
      │  fills in extreme temp / pressure mode / hold time
      ▼
frontend/start_dialog_temperature_swing.html
      │  POST /api/temperature-swing/start
      ▼
backend/temperature_swing_manager.py  ──OPC UA write──►  codesys/GVL_TemperatureSwing.st
                                                                  │
                                                                  ▼
                                                    codesys/FB_TemperatureSwing.st
                                                    (state machine, rate calc,
                                                     pressure establish/maintain)
                                                                  │
      ┌───────────────────────────OPC UA read───────────────────┘
      ▼
backend/websocket_temperature_swing.py  ──WebSocket──►  frontend/temperature_swing_progress.html
```

CODESYS owns the control logic and all safety-relevant decisions (rate
enforcement, overshoot tracking, pressure maintenance). The Python layer only
starts the test and displays live status — it never computes a control
decision itself, matching the parent project's "CODESYS is the control loop,
Python is the transport layer" boundary.

---

## Implementation checklist (Stage 3 → Stage 4)

- [ ] Import `codesys/` files into the live `Device.export` project (see
      `codesys/README.md` for exact steps and the two existing symbols
      `FB_TemperatureSwing` depends on that must be confirmed/renamed)
- [ ] Copy `backend/` files into `apps/dls/backend/automation/` in the main
      RnD repository and wire the FastAPI routes (see `backend/README.md`)
- [ ] Copy `frontend/` files into `apps/dls/frontend/pages/` and add the
      `_05_Automation` menu entry (see `frontend/README.md`)
- [ ] Run `backend/test_temperature_swing_manager.py` — passes against a
      fake OPC client today; re-run after wiring the real client
- [ ] Offline CODESYS simulation test before touching hardware
- [ ] Work through `docs/Test_Plan_Temperature_Swing.md` on an actual
      temperature cabinet and record sign-off

## Known gaps / explicitly out of scope here

- `FB_Apply_Test_Pressure` and `FB_Stabilisation_Check` are **referenced,
  not included** — they already exist in the live project; this design
  assumes their current signatures.
- `F_LogTemperatureSwingRow` / `F_BuildTemperatureSwingLogPath` are named in
  `FB_TemperatureSwing.st` but not implemented here — follow the existing
  CSV data-recorder pattern already in the project.
- No multi-cycle (repeated swing) support yet — single extreme per run. The
  design doc notes how the state machine could loop for that if needed later.
