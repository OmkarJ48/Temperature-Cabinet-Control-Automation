# Temperature Swing Integration — Development History

Same workflow as Temperature Cabinet Control Stages 1–8: investigate → document → build PoC → test → iterate.

---

## Stage 1 — Remote SSH + VS Code onto the R&D Prototype Pi

**Status:** ✅ Complete (18 August 2026)

**Host:** Raspberry Pi 5 at **10.1.6.40** (`PrototypePi5`)  
**Development location:** `~/RnD` cloned from `tlelean/RnD` on branch `Omkar_Temperature_Swing_Integration`  
**Development environment:** VS Code Remote-SSH → `pi@10.1.6.40`  
**Python:** venv with `pymodbus==3.12.1` pinned (critical), `opcua==0.98.13`, `fastapi==0.135.1`

### What Stage 1 accomplished

1. **Remote SSH connection** established from laptop to 10.1.6.40
2. **RnD repository cloned** on `Omkar_Temperature_Swing_Integration` branch
3. **Python venv created** with dependencies pinned (full `pip freeze` for reproducibility)
4. **Directory structure initialized:**
   - `backend/` — Python OPC manager, FastAPI router
   - `frontend/` — HMI pages, JS client
   - `codesys/` — Structured Text state machine
   - `docs/` — Design documents, test plans
5. **All commits pushed** to GitHub `tlelean/RnD`

### Terminal setup

Same as Temperature Cabinet Control Stage 1 (`10.1.6.17`), but for the R&D Prototype Pi.

**Full setup guide:** See [`../remote ssh vs code 10.1.6.40 setup guide/`](../remote ssh vs code 10.1.6.40 setup guide/)

**Quick reference — ~/.ssh/config**
```
Host rnd-pi
    HostName 10.1.6.40
    User pi
    IdentityFile ~/.ssh/id_rsa
    AddKeysToAgent yes
```

**Activation sequence (every session):**
```bash
ssh rnd-pi
cd ~/RnD
source venv/bin/activate
```

### Why this matters

- Same workflow as original project — removes friction from multi-machine development
- All commands execute on the Pi; git and terminal run over SSH
- Python venv isolated, reproducible, fully locked in `requirements.txt`
- Ready for Stages 2–5 development without environment surprises

### Commits pushed to tlelean/RnD

| Commit | Message |
|---|---|
| 4101757 | Stage 1: Pin full venv dependencies (pip freeze) |
| 960b8c0 | Add files via upload |
| 31aca1d | Add files via upload |

**Branch:** `Omkar_Temperature_Swing_Integration`  
**Status:** Up to date with origin

---

## Stage 2 — Design Investigation & Review

**Status:** ✅ Complete (19 August 2026) — design proposal issued at **v2.0**

**Deliverable:** [`../docs/Stage2_Design_Document.md`](../docs/Stage2_Design_Document.md)

### Investigation completed

Six areas of the existing DLS implementation were reviewed before any design
was committed:

| Area | Outcome |
|---|---|
| Program/state-machine architecture | Condition-based state machines with a safety exit from any state — pattern adopted |
| Pressure application (`FB_Apply_Test_Pressure`) | Reused unmodified for establishment |
| Pressure maintenance | Existing bang-bang upstream/downstream solenoid pattern, ±0.5 psi deadband — reused |
| Stabilisation calculation | Existing rolling-window pattern: 1 Hz sample, 60 s window, 2-window debounce |
| Start Dialog & Pressure Display | Extended, not rebuilt |
| CSV data recorder | `Historical_CSV` / `FB_CSV_Handler` / `FB_Buffer_Data` reused as-is |

### Hardware issue resolved during Stage 2

**EL4078 device description missing** — the EtherCAT device tree showed EL4078
with a warning and "required device description not installed". Root cause was
the ESI file not being present in the CODESYS Device Repository. Fixed by
downloading the EL4078 ESI from Beckhoff and importing via
**Tools → Device Repository → Install**. EL4078 now resolves cleanly.

### Design reconciled against the kickoff document

The first design draft (v1.0) was written before the kickoff document was
available. Reviewing it against the kickoff forced **eight corrections** — full
table in Section 13 of the design document. The four most significant:

1. **No hold state.** The sequence is ramp → reach/pass → stabilise → complete.
   The `HOLD_EXTREME`, `RETURN`, and `RETURN_STABILISE` states were removed.
2. **11 °C is a displayed target range, not an abort trigger.** No auto-abort
   on overshoot.
3. **Sequence order corrected** — delayed start → normal startup + CSV begin →
   establish pressure, not pressure first.
4. **0 psi variant skips supervision entirely** — upstream closed, downstream
   open, no band checking at all.

Also added: end-of-test behaviour (never auto-vent; leave at setpoint), exact
HMI prompt-bar text and white→orange channel highlighting, and the fixed
five-channel monitoring list.

### Open items carried into Stage 3

| # | Item | Type |
|---|---|---|
| 1 | `rTempSwing_AmbientTolerance` = 5 °C for ambient-return detection | Needs TL sign-off |
| 2 | Program selector slot/ID convention (`ProgramSelecter`) | Investigation — inspect in CODESYS |

Item 1 blocks only the ambient-return path; the main hot/cold swing can be
drafted without it.

See [`../Stage_2_Design_Review/`](../Stage_2_Design_Review/) for the full
question-by-question record.

---

## Next: Stage 3 — Offline Development

Re-draft the deliverable source files against design v2.0. The existing files in
`../codesys/`, `../backend/`, and `../frontend/` are v1.0-era drafts carrying the
removed hold state and the old variable names — they are rewritten, not patched.

- [ ] `FB_TemperatureSwing.st` — 12-state machine per design Section 2
- [ ] `E_TemperatureSwingState.st` — state enum
- [ ] `GVL_TemperatureSwing.st` — variables per design Section 11
- [ ] Start Dialog HTML — setpoint, monitoring channel, pressure mode, Cycles fixed to 1
- [ ] Pressure Display extensions — prompt bar, channel highlighting, rate readout
- [ ] Offline CODESYS simulation before any hardware time

---

**Principle:** Rebuild → Retest → Requalify → Reattempt → Repeat
