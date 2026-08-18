# Stage 2 — Design Investigation & Review

**Goal:** Understand existing DLS implementation before designing Temperature Swing.

**Approach:** Investigate → Document → Design → Review (same pattern as Temperature Cabinet Control Stages 1–8)

## Status

Stage 1 complete (Remote SSH + venv setup on Pi 10.1.6.40, pymodbus==3.12.1 pinned).

Stage 2 in progress:
- [ ] Explore existing DLS backend architecture (apps/dls/backend/)
- [ ] Document program/state-machine patterns
- [ ] Review pressure application & maintenance (FB_Apply_Test_Pressure, solenoid control)
- [ ] Examine Start Dialog & Pressure Display integration
- [ ] Cross-check against API 6A requirements (F.1.9, F.1.10, F.1.11)
- [ ] Identify what to reuse vs. build new

## Subfolders

| Folder | Purpose |
|---|---|
| `investigation/` | Raw exploration logs: code structure, existing functions, patterns |
| `findings/` | Analysis & synthesis: what we learned, decisions made |
| `docs/` | Design documents: state machine, pressure logic, HMI changes |

## Key Questions for Stage 2

1. **Program Architecture** — How do existing DLS programs (Holds, PR2, etc.) structure their state machines?
2. **Pressure Control** — What does `FB_Apply_Test_Pressure` do? How is 50–100% pressure maintained during dynamic tests?
3. **Start Dialog** — What fields does the existing Start Dialog have? How is it integrated into the HMI?
4. **Pressure Display** — How is chamber pressure displayed? Where should Temperature Swing status go?
5. **Stabilisation** — Does an existing `FB_Stabilisation_Check` exist? How is rate calculated?
6. **CSV Logging** — What data-recorder pattern is used? How to integrate Temperature Swing logs?

## Deliverables (end of Stage 2)

- Design document with state sequence, rate calculation, pressure logic
- OPC node map (variable names for CODESYS ↔ Python)
- Reuse checklist (what exists, what's new)
- Architecture review sign-off before Stage 3 (PoC development)

---

**Next:** Explore tlelean/RnD and document findings in `investigation/` folder.
