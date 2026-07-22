# Fresh CODESYS Project — Import Guide (Phase 1 TCP)

## Why this exists

The original "RnD DLS" CODESYS project opens **read-only** with **47 compile
errors**. Root cause is a **project version lock**: the project was saved by a
newer CODESYS version than the one installed, so CODESYS opens it read-only to
prevent corruption. The visualization-library errors (VisuElemBase 4.9.1.0
needing VisuShared symbols that only exist in a newer VisuShared, plus two
`visuinputs` versions loaded at once) are a *symptom* of that mismatch — they
cannot be fixed by editing, because the project is locked.

**Escape hatch:** the setpoint-control logic is already exported as text files
in `src/`. Rebuild it in a fresh, version-clean project with **no
visualization**. This compiles clean and downloads to the Pi runtime.

## Recommended entry point

Use the **standalone** `src/POUs/PLC_PRG_TCP_Retargeted.st` as the MainTask
program. It is self-contained (only depends on the two enums + `GVL_Modbus`),
and exposes the two watch variables used for live testing: `rReqSetpoint` and
`xStartWrite`.

> Alternative: `src/POUs/PLC_PRG.st` + `src/POUs/FB_CabinetSetpointControl.st`
> + `src/GVLs/GVL_HMI.gvl` (FB-based). Import those instead if you want the
> HMI-facing FB structure. Only one program may be the MainTask entry point.

## Steps

1. **New project** — `File → New Project → Standard project`. Name
   `TempCabinetTCP`. Device = the same Linux ARM64 runtime target as the Pi
   (10.1.6.17); copy the exact device name/version from the RnD DLS project's
   device **Information** tab if unsure. PLC_PRG language = **Structured Text**.

2. **DUTs** — Add two Enumeration DUTs, paste bodies from:
   - `src/DUTs/E_SetpointState.dut`
   - `src/DUTs/E_FaultCode.dut`

3. **GVL** — Add GVL `GVL_Modbus`, paste from `src/GVLs/GVL_Modbus.gvl`
   (keep the `{attribute 'qualified_only'}` line).

4. **Program** — Paste `src/POUs/PLC_PRG_TCP_Retargeted.st` into `PLC_PRG`.

5. **Build (F11)** — expect **0 errors** (logic is self-contained; no visu
   libraries). This checkpoint proves the version lock is escaped.

6. **Device** — Ethernet → Modbus TCP Master → Modbus TCP Slave.
   IP `10.1.6.17`, Port `502`, Unit ID `1`.

7. **Channels + I/O mapping** (holding registers, x10 scaled):

   | Reg | Access | GVL var |
   |-----|--------|---------|
   | 2 | FC03 read | `wInput1Value` |
   | 3 | FC03 read | `wSetpoint1Read` |
   | 4 | FC03 read | `wStatus` |
   | 0 | FC06 write | `wSetpoint1Write` |
   | 1 | FC06 write (rising edge) | `xWriteTrigger` |

8. **Task** — MainTask calls `PLC_PRG`, cyclic, **10 ms** (matches the
   `dwMaxTimeout := 300` ~3 s watchdog).

9. **Connect** — Device → Communication Settings → Scan network → select Pi
   runtime → Set active path → Login (Alt+F8) → download → Start (F5).

10. **Live test** — watch `rChamberTemp`, `rConfirmedSetpoint`; set
    `rReqSetpoint`; force `xStartWrite := TRUE`; watch `eSetpointState` walk
    `IDLE→READY→WRITING→CONFIRM→IDLE` and `rConfirmedSetpoint` snap to target.
    On fault, `eFaultCode` gives the reason.

## Fault codes (reg4 / `wStatus` / `eFaultCode`)

| Code | Meaning |
|------|---------|
| 0 | OK / NO_FAULT |
| 1 | COMMS_TIMEOUT (no FC03 response) |
| 2 | WRITE_FAILED (gateway couldn't write F4S) |
| 3 | NOT_ACCEPTED (read-back != target) |
| 4 / 5 | RANGE_LOW / RANGE_HIGH |
| 6 | OVER_TEMP (spare EL1409 DI interlock) |
