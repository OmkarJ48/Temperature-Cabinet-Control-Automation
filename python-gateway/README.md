## Python Gateway Integration — End-to-End Setup Guide

**Goal (from TL email):** exchange 4 values between the working Python serial layer and CODESYS — current cabinet temperature, current setpoint, requested new setpoint, and confirmation the new setpoint was accepted. CODESYS-native serial Modbus is abandoned; Python owns the serial port.

**Branch:** `Omkar_Temperature_Cabinet_Setpoint_Control` (dev/test only — never merge to main)
**Sandbox CODESYS project:** `RnD DLS - Omkar_Temperature_Cabinet_Setpoint_Control.project`

### 1. Architecture

```
 CODESYS (sandbox project)          Raspberry Pi 10.1.6.17              Watlow F4S
 ┌────────────────────────┐  Modbus TCP  ┌──────────────────────────┐ RS-232 ┌─────────┐
 │ Modbus TCP MASTER      │ ── :502 ───► │ f4s_gateway.py           │ ─────► │ slave 1 │
 │ reads reg2/3/4         │ ◄──────────  │  TCP slave + RTU master  │ ◄───── │ 100/300 │
 │ writes reg0/1          │              │  SOLE serial owner       │        └─────────┘
 └────────────────────────┘              └──────────────────────────┘
```

Why this is robust: CODESYS Modbus TCP master is native and reliable (no serial red-triangle issues). Python is the single serial owner — no port contention. Same register/scale model you already proved with mbpoll (reg100 temp, reg300 SP, /10, addr 1, 19200 8N1).

**The 4 values ↔ TCP register map** (holding registers, x10 ints)

| Value | TCP reg | Direction | Notes |
|---|---|---|---|
| Requested new setpoint | 0 | CODESYS → Python | write x10 int (265 = 26.5 °C) |
| Apply trigger | 1 | CODESYS → Python | write 1 to apply; gateway clears to 0 |
| Current cabinet temperature | 2 | Python → CODESYS | live, x10 |
| Current setpoint (confirmed) | 3 | Python → CODESYS | read-back, x10 |
| Confirmation / fault status | 4 | Python → CODESYS | 0=OK 2=WRITE_FAILED 3=NOT_ACCEPTED 4=RANGE 5=COMMS |

"Confirmation the setpoint was accepted" = reg4 == 0 and reg3 == reg0 after an apply.

### 2. Git — create & push the new branch (SSH already set up)

On the Pi, in your existing repo clone:

```bash
cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI   # your existing clone
# make sure you have the latest
git fetch origin
# create the new branch off main (dev/test only, never merged to main)
git checkout main
git pull origin main
git checkout -b Omkar_Temperature_Cabinet_Setpoint_Control
# push it and set upstream
git push -u origin Omkar_Temperature_Cabinet_Setpoint_Control
```

Verify:

```bash
git branch -vv        # shows * Omkar_Temperature_Cabinet_Setpoint_Control ... [origin/...]
git remote -v         # confirms git@github.com:OJ4884/... (SSH)
```

If `git remote -v` shows `https://`, switch to SSH so your key is used:

```bash
git remote set-url origin git@github.com:OJ4884/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI.git
```

### 3. Install the gateway on the Pi

```bash
# put the script in the repo (e.g. under python-gateway/)
mkdir -p python-gateway
cp /path/to/f4s_gateway.py python-gateway/
pip install "pymodbus>=3" pyserial --break-system-packages
```

Free the serial port (Python must be the sole owner):

```bash
# CODESYS no longer uses serial -> stop any old hold, kill mbpoll
pkill -9 mbpoll 2>/dev/null
sudo systemctl stop codesyscontrol         # only if it was holding the serial port
sudo lsof /dev/ttyWatlowF4S                 # expect: nothing
```

### 4. Temperature Range

**Setpoint valid range:** -40°C to 200°C (x10 integers: -400 to 2000)
- Minimum setpoint: -40°C (raw value -400)
- Maximum setpoint: 200°C (raw value 2000)
- Outside this range: gateway returns RANGE fault code (4)

### 5. Running the Gateway

```bash
cd python-gateway
python3 f4s_gateway.py
```

Logs to both `f4s_gateway.log` and stdout. Use `tail -f` to monitor live:

```bash
tail -f python-gateway/f4s_gateway.log
```

### 6. Troubleshooting

**Serial port busy:**
- Ensure CODESYS serial hold is released (no old Modbus RTU device in project)
- Kill any old mbpoll: `pkill -9 mbpoll`
- Check device exists: `ls -l /dev/ttyWatlowF4S`

**Modbus TCP connection refused:**
- Gateway must run with `sudo` or `setcap` to bind port 502
- Check: `sudo netstat -ln | grep 502`

**Temperature reads stuck / write fails:**
- Verify F4S Modbus address is 1 and baud is 19200 8N1
- Test with mbpoll: `mbpoll -m rtu -a 1 -b 19200 -r 100 -c 1 /dev/ttyWatlowF4S`
- Check F4S is not in menu/profile mode (write must happen from run page)
