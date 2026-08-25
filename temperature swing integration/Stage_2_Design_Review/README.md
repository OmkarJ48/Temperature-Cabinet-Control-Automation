# Stage 2 — Design Investigation & Review

**Goal:** Understand existing DLS implementation before designing Temperature Swing.

**Approach:** Investigate → Document → Design → Review (same pattern as Temperature Cabinet Control Stages 1–8)

## Status

Stage 1 complete (Remote SSH + venv setup on Pi 10.1.6.40, pymodbus==3.12.1 pinned).

Stage 2 complete — design proposal v2.0 issued, reconciled against the project
kickoff document. See [`../docs/Stage2_Design_Document.md`](../docs/Stage2_Design_Document.md).

- [x] Explore existing DLS backend architecture (apps/dls/backend/)
- [x] Document program/state-machine patterns
- [x] Review pressure application & maintenance (FB_Apply_Test_Pressure, solenoid control)
- [x] Examine Start Dialog & Pressure Display integration
- [x] Cross-check against API 6A requirements (F.1.9, F.1.10, F.1.11)
- [x] Identify what to reuse vs. build new
- [x] Reconcile draft design against kickoff document (8 corrections — design doc Section 13)

## Subfolders

| Folder | Purpose |
|---|---|
| `investigation/` | Raw exploration logs: code structure, existing functions, patterns |
| `findings/` | Analysis & synthesis: what we learned, decisions made |
| `docs/` | Design documents: state machine, pressure logic, HMI changes |

## Key Questions for Stage 2 — all answered

1. **Program Architecture** — How do existing DLS programs (Holds, PR2, etc.) structure their state machines? → Condition-based state machines with a safety exit from any state; reused as the pattern for `FB_Temperature_Swing`.
2. **Pressure Control** — What does `FB_Apply_Test_Pressure` do? How is 50–100% pressure maintained? → Establishment block reused unmodified; maintenance is the existing bang-bang upstream/downstream solenoid pattern, ±0.5 psi deadband.
3. **Start Dialog** — What fields exist and how is it integrated? → Existing fields reused; Temperature Swing adds setpoint, monitoring channel, pressure mode, with Cycles fixed to 1.
4. **Pressure Display** — Where should Temperature Swing status go? → Existing page extended with prompt bar, white→orange channel highlighting, and a °C/min readout. No new page architecture.
5. **Stabilisation** — How is rate calculated? → Existing rolling-window pattern: 1 Hz sampling, 60 s window, `|rate| < 0.5 °C/min`, 2-window debounce.
6. **CSV Logging** — What recorder pattern is used? → `Historical_CSV` / `FB_CSV_Handler` / `FB_Buffer_Data`; Temperature Swing added as another data source.

## Design questions closed by the kickoff document

| # | Question | Answer |
|---|---|---|
| 1 | Hold duration | No hold state at all — ramp → stabilise → complete |
| 2 | Overshoot handling | 11 °C is a displayed target range, not an auto-abort |
| 3 | Monitor channel scope | Fixed generic list of five channels, no cabinet filtering |
| 4 | 0 psi variant | Upstream closed, downstream open, all supervision skipped |
| 5 | Program selector integration | Resolved — slot 13, FB name `FB_Temperature_Swing`, safety exit is structural to `ProgramSelecter` (design doc Section 10a) |

Full reconciliation table (8 corrections against the v1.0 draft) is in
[`../docs/Stage2_Design_Document.md`](../docs/Stage2_Design_Document.md) Section 13.

## Deliverables (end of Stage 2)

- [x] Design document with state sequence, rate calculation, pressure logic — v2.0
- [x] Variable reference (CODESYS ↔ OPC naming) — [`../docs/GVL_TemperatureSwing_Variables.md`](../docs/GVL_TemperatureSwing_Variables.md)
- [x] Reuse checklist (what exists, what's new) — design doc Section 10
- [x] Program selector slot/ID convention — resolved, slot 13
- [ ] Architecture review sign-off before Stage 3 — blocked only on the 5 °C ambient tolerance

---

**Next:** Stage 3 — re-draft `FB_Temperature_Swing.st` against design v2.0. The
existing files in `../codesys/`, `../backend/`, and `../frontend/` are v1.0-era
drafts (they still contain hold states and v1.0 variable names) and must be
rewritten, not patched.
