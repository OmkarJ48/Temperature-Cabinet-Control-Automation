# Temperature Swing Integration — Development History

Same workflow as Temperature Cabinet Control Stages 1–8: investigate → document → build PoC → test → iterate.

---

## Stage 1 — Remote SSH + VS Code onto the R&D Prototype Pi

**Status:** ✅ Complete (18 August 2026)

**Host:** Raspberry Pi 5 at **10.1.6.40** (`PrototypePi5`)  
**Development location:** `~/RnD` cloned from `tlelean/RnD` on branch `Omkar_Temperature_Swing_Integration`  
**Development environment:** VS Code Remote-SSH → `mechatronics@10.1.6.40`  
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
    User mechatronics
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

## Next: Stage 2 — Design Investigation & Review

Before writing code, investigate existing DLS implementation:
- Program/state-machine architecture
- Pressure application & maintenance (FB_Apply_Test_Pressure)
- Start Dialog & Pressure Display patterns
- Stabilisation calculations
- CSV data-recorder pattern

See [`../Stage_2_Design_Review/`](../Stage_2_Design_Review/) for investigation setup and key questions.

---

**Principle:** Rebuild → Retest → Requalify → Reattempt → Repeat
