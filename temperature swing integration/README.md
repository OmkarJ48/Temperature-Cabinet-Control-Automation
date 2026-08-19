# Temperature Swing Integration

**Parent project:** Temperature Cabinet Setpoint Control from CODESYS HMI
**Compliance target:** API 6A — Temperature Testing (F.1.9), Hold Periods /
Stabilisation (F.1.10), Pressure/Temperature Cycles (F.1.11)
**Status:** Design complete (Stage 2) at **v2.0**, reconciled against the project
kickoff document. The source files in `codesys/`, `backend/`, and `frontend/` are
**v1.0-era drafts that now lag the design** — they still contain a hold state and
v1.0 variable names, and must be re-drafted in Stage 3 rather than patched.
Nothing here is imported into the live CODESYS project or backend.

---

## What this adds

The parent repository proves two things end to end on hardware: remote
setpoint control and remote on/off automation of a temperature cabinet. This
folder adds the piece needed for API 6A compliance testing: an automated
**ramp → reach/pass setpoint → stabilise → complete** sequence that

- drives the cabinet to an operator-specified setpoint, positive or negative,
- **measures** rate of change against the **&lt;0.5&deg;C/min** stabilisation
  criterion (measured and reported, not artificially throttled),
- establishes and supervises chamber pressure at **0/50/75/100%** of test
  pressure, with the 0 psi variant skipping supervision entirely,
- displays the **11&deg;C** target range and records any excursion past it, and
- logs the run to CSV through the existing recorder for compliance records.

One execution per start — no hold period, no automatic return ramp, and no
multi-cycle chaining.

It reuses the existing pressure-application function block and solenoid
control pattern rather than duplicating them — see
`docs/Stage2_Design_Document.md` Section 10 for exactly what is reused vs. new,
and Section 13 for the eight corrections the kickoff document forced on the
v1.0 draft.

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
      │  fills in setpoint / monitoring channel / pressure mode
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
measurement, target-range tracking, pressure maintenance). The Python layer only
starts the test and displays live status — it never computes a control
decision itself, matching the parent project's "CODESYS is the control loop,
Python is the transport layer" boundary.

---

## Implementation checklist (Stage 3 → Stage 4)

- [ ] **Re-draft `codesys/`, `backend/`, and `frontend/` against design v2.0**
      — remove the hold/return states, adopt the `TempSwing_` variable names,
      add the monitoring-channel selector and the 0 psi skip path. Do this
      before any of the import steps below.
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
- No multi-cycle (repeated swing) support — single execution per start, by
  design. Cycles is present in the Start Dialog but fixed to 1.
- Ambient-return detection is designed but **not to be implemented** until the
  proposed 5 °C tolerance is signed off (design doc Sections 9 and 12).
