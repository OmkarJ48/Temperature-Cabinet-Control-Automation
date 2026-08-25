# Rollout Checklist & To-Do — Temperature Cabinet Setpoint Control

**Author:** Omkar Joshi — Oliver Mechatronics
**Raised:** 7 August 2026, following sign-off with the manager that the DLS008 / Left Hand Small
Temperature Cabinet proof of concept is **a success**.
**Purpose:** Turn the proven one-cabinet system into a repeatable build, and replicate it across
the remaining temperature cabinets.
**Working branch:** `Omkar_Temperature_Cabinet_Setpoint_Control`

> **What is already proven and must not be re-litigated during rollout:**
> Modbus RTU to the Watlow F4S (reg 100 read / reg 300 write, 19200 8N1, slave 1), the Python
> gateway owning the serial port, CODESYS talking Modbus TCP only, and remote start/stop landing on
> the cabinet's own Omron CPM1A digital inputs. See the root `README.md` and
> `cabinet on-off automation proof of concept and integration/README.md` §19.
> **This checklist changes how those signals are carried and connectorised — not what they are.**

---

## 1. Procurement checklist

Order before any panel work starts. Nothing in Section 3 can begin until items 1 and 2 are on site.

| # | Item | Qty | Purpose | Status |
|---|---|---|---|---|
| 1 | **RS PRO Straight, Panel Female — 2 Port, Type USB A to A, USB 3.0 connector** | 1 per cabinet | Panel-mount USB feed-through. **Port 1** carries the USB-to-RS232 adapter link (proven Modbus path). **Port 2** carries keyboard/mouse straight out of the Raspberry Pi. | ☐ Ordered |
| 2 | **Beckhoff EL1859** — EtherCAT digital combi terminal (8× DI 24 V DC + 8× DO 24 V DC, 0.5 A) | 1 per cabinet | Replaces the **pin 36 / pin 37 DI-DO** route on the 37-way connector for the cabinet start/stop signals. | ☐ Ordered |
| 3 | Ferrules, Wago push-in connectors, 24 V hook-up wire (red / green / blue to match the drawing) | — | Harness build, Section 3.2 | ☐ |
| 4 | 2× interposing relays per cabinet (as per the proven RL15 START / RL16 STOP pair) | 2 per cabinet | DLS → relay → Omron CPM1A start/stop | ☐ |
| 5 | USB-to-RS232 adapter (same model as the qualified DLS008 unit) | 1 per cabinet | F4S serial link — must match the qualified part, do not substitute | ☐ |

**Verify before ordering item 2:** confirm on the Beckhoff datasheet that the EL1859 channel count
and current rating cover every DI and DO you are moving off pins 36/37 for that cabinet. If a
cabinet needs more than 8 DO, the EL2869 (16 DO) remains the correct part for that leg.

---

## 2. Job sequence — the order the work happens

The sequence is deliberate: **prove the comms path first, then the control path, then re-terminate
the I/O.** Each job has a precondition and an acceptance test. Do not start a job until the
previous job's acceptance test has passed.

```
 JOB 1                JOB 2                JOB 3               JOB 4
 USB A-A panel  ──►   DLS → harness  ──►   Relays →      ──►   EL1859 replaces
 connector +          to LH Small          Omron CPM1A         pin 36/37 DI-DO
 RS232 adapter        Temp Cab             start/stop
 (proven Modbus)                           (Omron unchanged)
```

---

## 3. The jobs

### JOB 1 — USB A-to-A panel connector + RS232 adapter (proven Modbus path) ⬅ **START HERE**

Re-terminate the existing, already-qualified serial link through a proper panel connector so the
Pi is no longer relying on a cable run through an open gland.

- [ ] Mount the RS PRO 2-port panel female USB A-to-A connector in the DLS enclosure face
- [ ] **Port 1:** Pi USB → panel port 1 → USB-to-RS232 adapter → cabinet "SERIAL COMMS" DB9
- [ ] **Port 2:** Pi USB → panel port 2 → keyboard/mouse (operator local access, no signal role)
- [ ] Confirm the udev symlink still resolves after the re-termination — the adapter may
      re-enumerate to a new `ttyUSB*` number through the new connector
      (`ls -l /dev/ttyWatlowF4S`)
- [ ] Restart the gateway service and confirm it claims the port cleanly
      (`sudo systemctl restart f4s-gateway && journalctl -u f4s-gateway -n 20`)

**Acceptance test:** with the gateway stopped, a raw read succeeds through the new connector —
```bash
mbpoll -m rtu -a 1 -b 19200 -P none -0 -r 100 /dev/ttyWatlowF4S
```
then restart the gateway and confirm CODESYS reg 2 / reg 3 update cyclically. **A setpoint write
must complete and confirm end-to-end before Job 2 begins.**

> **Why this is first:** it is the only job that touches an already-working path. Doing it first
> means any fault found later in Jobs 2–4 cannot be blamed on the comms link — it was re-proven
> after re-termination, on the record.

---

### JOB 2 — Wiring harness: DLS enclosure → LH Small Temperature Cabinet

- [ ] Build the harness from the DLS enclosure running direct to the LH Small Temperature Cabinet
- [ ] Wire colours to follow the control drawing: **red = start signal**, **green = stop signal**,
      **blue = NC2 → stop relay common**
- [ ] Ferrule both ends of every conductor; use Wago push-in connectors for any point where one
      source feeds two destinations (do not stack two ferrules under one screw terminal)
- [ ] Label every conductor with its drawing wire number (`100`, `102`, `103`) at both ends
- [ ] Land the 0 V / common return on a single shared rail — one bonded return, not per-device

**Acceptance test:** continuity and correct-terminal ring-out on every conductor, **before** any
24 V is applied. Record the results in the cabinet's test log.

---

### JOB 3 — Relays → Omron CPM1A start/stop (Omron program unchanged)

Two interposing relays per cabinet, matching the proven RL15 / RL16 pair.

- [ ] **RL15 (START):** coil `A1` ← red wire from the DLS start output; coil `A2` → 0 V common
- [ ] **RL16 (STOP):** coil `A1` ← green wire from the DLS stop output; coil `A2` → 0 V common
- [ ] Switch common `100` → RL15 terminal `11`, Wago-tapped across to RL16 terminal `21`
- [ ] RL15 NO `14` → wire `102` → Omron CPM1A input `0CH.00` (start)
- [ ] RL16 NC `22` → wire `103` → Omron CPM1A input `0CH.01` (stop)
- [ ] Button station NO4 / NC2 land **in parallel** on the same `102` / `103` nets — this is what
      preserves local manual authority (see the open item in §5 below)
- [ ] **Do not modify the Omron CPM1A program.** It owns the start/stop latching; CODESYS only
      presents a level on each input and holds it

**Acceptance test:** four cases, all four must pass —

| Command | Expected |
|---|---|
| `xStartPulse := TRUE` | Omron `0CH.00` LED lit, cabinet starts |
| `xStopPermit := TRUE` | Omron `0CH.01` LED lit, cabinet stops |
| Green button pressed by hand (CODESYS idle) | Cabinet starts |
| Red button pressed by hand (CODESYS commanding run) | Cabinet stops — **local authority wins** |

---

### JOB 4 — EL1859 EtherCAT DI/DO module replaces the pin 36 / pin 37 route ⬅ **DO LAST**

- [ ] Fit the EL1859 to the EK1100 EtherCAT coupler; scan the bus in CODESYS and confirm it
      enumerates in the device tree
- [ ] Move the cabinet start signal off **37-way connector pin 36** onto an EL1859 DO channel
- [ ] Move the cabinet stop signal off **37-way connector pin 37** onto an EL1859 DO channel
- [ ] Re-map `GVL_HMI.xStartPulse` and `GVL_HMI.xStopPermit` in the CODESYS I/O mapping to the new
      EL1859 channels
- [ ] Update `IO_Schedule.xlsx` to reflect the new channel allocation, and resolve the pin 36/37
      conflict flagged in §5 below

**Acceptance test:** repeat the full Job 3 four-case acceptance test, unchanged, through the new
EL1859 channels. Behaviour must be identical — **if anything differs, the mapping is wrong, not
the cabinet.**

> **Why this is last:** it is the only job that changes an I/O allocation already published in the
> I/O schedule and shared with other rig work. Doing it last means it is the only variable in play
> when it happens, and it can be reverted to pins 36/37 in minutes if the rig needs the cabinet
> back in service.

---

## 4. Cabinet rollout order

Same four jobs, repeated per cabinet. Order is chosen so the hardest and least-understood cabinet
is done when the procedure is at its most mature.

| # | Cabinet | Controller | Why this position | Status |
|---|---|---|---|---|
| 0 | **LH Small Temperature Cabinet (DLS008)** | Watlow F4S + Omron CPM1A | Proof of concept — **complete and signed off** | ✅ Proven |
| 1 | **Large temperature control cabinet (LH or RH — confirm which)** | *confirm on survey* | First replication. Largest and most representative of the remaining fleet, so the procedure gets stress-tested early while the DLS008 reference build is still fresh | ☐ |
| 2 | Remaining cabinet | *confirm on survey* | Procedure now repeatable | ☐ |
| 3 | Remaining cabinet | *confirm on survey* | Procedure now repeatable | ☐ |
| 4 | **RH Temperature Control Cabinet** | **Different controller — not F4S** | **Deliberately last.** Its controller differs, so its register map, baud rate and write behaviour are all unproven. Every other cabinet must be finished and stable before this one starts | ☐ |

**Before cabinet 4 starts, budget a separate investigation stage** equivalent to Stage 2 of the
original build: identify the controller, find its Modbus map, and prove a raw read/write from the
Linux shell **before** any CODESYS or panel work. Do not assume the F4S procedure transfers.

**Per-cabinet survey — do this before scheduling each cabinet:**

- [ ] Confirm the cabinet controller model and part number
- [ ] Confirm there is an Omron CPM1A (or equivalent) behind the button station, and identify its
      input terminals for start/stop
- [ ] Confirm the serial comms port type and location
- [ ] Photograph the button station contact stack and the controller terminal block

---

## 5. Open items carried into rollout

These are known, recorded, and must be closed — not discovered again per cabinet.

| # | Item | Impact | Owner action |
|---|---|---|---|
| 1 | **Pin 36 / 37 allocation conflict.** `IO_Schedule.xlsx` lists 37-way pins 36/37 as DO *"3 Way BV01"* and *"3 Way BV02"*, but the same channels are in use for cabinet start/stop (EL2869 CH15/CH16). Two functions are claiming the same physical route | **High** — a rig integration change could silently take the cabinet start/stop offline | Resolve during Job 4: the EL1859 move frees pins 36/37 back to the I/O schedule. Update the schedule in the same change |
| 2 | **Manual authority confirmation** (on/off log §19.4). Conflicting reports on record for whether the button's NO4/NC2 outputs are currently landed alongside CH15/CH16 | **High** — safety-relevant; operator must always be able to stop the cabinet by hand | Close with the Job 3 four-case acceptance test, on every cabinet, and record the result |
| 3 | RH cabinet controller is unidentified | Medium — unknown scope | Survey before scheduling cabinet 4 |

---

## 6. Definition of done, per cabinet

A cabinet is signed off when **all** of the following are true:

- [ ] Setpoint written from the CODESYS HMI is accepted and confirmed by read-back
- [ ] Chamber temperature and confirmed setpoint update live on the HMI
- [ ] Cabinet starts and stops from CODESYS
- [ ] Cabinet starts and stops from the physical button station, including while CODESYS is
      commanding the opposite — **local authority wins**
- [ ] All four jobs' acceptance tests recorded in the cabinet's test log
- [ ] `IO_Schedule.xlsx` updated with the as-built channel allocation
- [ ] As-built wiring photographed and committed to this repo
