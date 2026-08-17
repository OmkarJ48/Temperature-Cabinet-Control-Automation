# Hardware Test Plan — Temperature Swing (Stage 4)

Run only after Stage 3 (offline development in CODESYS simulation) passes.

## Pre-requisites

- [ ] `FB_TemperatureSwing.st` compiles with no warnings
- [ ] GVL variables online-forced and readable via OPC UA
- [ ] `temperature_swing_manager.py` connects and reads status without error
- [ ] Start Dialog writes reach CODESYS (verified via online watch)

## Test 1 — Cold cycle, no pressure

- Extreme: -45 degC, Pressure mode: None, Hold: 10 min
- Start from ambient (~25 degC)
- **Pass criteria:**
  - [ ] Every logged rate sample < 0.5 degC/min (single isolated spike tolerated)
  - [ ] Extreme reached (T <= -45 degC)
  - [ ] Overshoot <= 11 degC (T did not go below -56 degC)
  - [ ] Hold timer accurate to +/- 5 s
  - [ ] Returns to within 2 degC of ambient
  - [ ] CSV log contains continuous timestamp/temp/rate/state rows

## Test 2 — Hot cycle, no pressure

- Extreme: +85 degC, Pressure mode: None, Hold: 10 min
- Same pass criteria as Test 1, mirrored (overshoot ceiling = 96 degC)

## Test 3 — Cold cycle, 50% pressure

- Extreme: -45 degC, Pressure mode: 50%, Hold: 10 min
- **Additional pass criteria:**
  - [ ] Pressure established before ramp begins (FB_Apply_Test_Pressure `xDone`)
  - [ ] Pressure held within +/-0.5 psi of target through ramp/hold/return
  - [ ] Solenoids do not chatter (no more than 1 open/close transition per 5 s)

## Test 4 — Hot cycle, 100% pressure

- Extreme: +85 degC, Pressure mode: 100%, Hold: 10 min
- Same additional criteria as Test 3

## Test 5 — Abort handling

- [ ] STOP mid-RAMP -> immediate transition to IDLE, solenoids close, log marked "aborted"
- [ ] Simulated Body Temperature channel fault mid-test -> falls back to Monitor
      Temperature, fallback logged, test continues
- [ ] Pressure establishment timeout (valve disconnected) -> test does not start
      RAMP, error logged, operator alerted on HMI

## Sign-off

| Test | Date | Result | Operator |
|---|---|---|---|
| 1 — Cold, no pressure | | | |
| 2 — Hot, no pressure | | | |
| 3 — Cold, 50% pressure | | | |
| 4 — Hot, 100% pressure | | | |
| 5 — Abort handling | | | |
