# Remote-SSH (VS Code) + GitHub Workflow

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics
**Applies to:** Any laptop connecting to the Raspberry Pi at **10.1.6.17** (`LeftHandSmallTempCab`) that hosts the CODESYS sandbox project
**Covers:** Steps 1 and 6 of the integration sequence in the root `README.md`

This folder covers the tooling layer only — how you get a terminal and an editor *onto* the Pi,
and how code changes made there get back to GitHub. It has nothing to do with the serial
hardware (see `linux-integration/`) or CODESYS itself (see `codesys-modbus-integration/`) — those are
kept separate on purpose so each concern can be read, fixed, and referenced independently.

---

## Step 1: Connect to the Pi from VS Code

1. Install the **Remote - SSH** extension in VS Code (once, on your laptop).
2. `Ctrl+Shift+P` → **Remote-SSH: Connect to Host…** → enter:
   ```
   mechatronics@10.1.6.17
   ```
3. VS Code re-opens with its terminal, file explorer, and extensions all running **on the Pi**,
   not your laptop. Every command from here on (`dmesg`, `apt-get`, `git`, `nano`, `mbpoll`)
   executes on the Pi itself, over the SSH session — not locally.
4. Open the project folder via **File → Open Folder**:
   ```
   ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI
   ```
   (or wherever the repo is cloned on this Pi — see Step 6 below if it isn't cloned yet). This
   is the same repository as
   `github.com/OJ4884/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI`, branch
   `Omkar_Temperature_Cabinet_Setpoint_Control`. VS Code's Source Control panel talks to GitHub exactly as it would from a
   local clone — it is just physically executing on the Pi's filesystem.

If the connection fails, check:
- The Pi is powered on and on the same network as your laptop (ping `10.1.6.17` first).
- SSH is enabled on the Pi (`sudo systemctl status ssh`).
- Your SSH key (if used) is loaded, or the password is correct.

---

## Step 6: GitHub workflow from the Pi

Because the Remote-SSH session's Source Control panel runs *on the Pi*, working with this repo
from `10.1.6.17` is the same Git workflow as any other clone — there is nothing Pi-specific
about it beyond where the files physically live.

**Day-to-day (repo already cloned):**

```bash
cd ~/.ssh/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI

# Activate Python virtual environment (do this FIRST, every terminal session)
source venv/bin/activate
# (you should see (venv) at the start of your prompt now)

# Then sync with GitHub
git config pull.rebase true
git status
git fetch origin Omkar_Temperature_Cabinet_Setpoint_Control
git pull origin Omkar_Temperature_Cabinet_Setpoint_Control
```

Stage and commit new/changed files (ST code, docs, configs, etc.) either via the VS Code Source
Control UI, or from the integrated terminal:

```bash
# Make sure venv is still activated (you should see (venv) in your prompt)
# If not, run: source venv/bin/activate

git add <files>
git commit -m "…"
git push -u origin Omkar_Temperature_Cabinet_Setpoint_Control
```

**First-time clone (fresh Pi, repo not present yet):**

```bash
# Clone the repo
git clone -b Omkar_Temperature_Cabinet_Setpoint_Control https://github.com/OJ4884/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI.git

# Navigate into repo
cd Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI

# Set rebase strategy for clean history
git config pull.rebase true

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate
# (you should see (venv) at the start of your prompt)

# Install Python dependencies
pip3 install -r codesys-python-tcp-integration/python-gateway/requirements.txt

# Verify pymodbus version (must be exactly 3.12.1)
pip3 list | grep pymodbus
```

The venv will remain active for the current terminal session. Each time you open a new terminal, activate it again with:
```bash
source venv/bin/activate
```

This Remote-SSH + GitHub path is how the `.html`, `.md`, `.dut`, `.gvl`, `.xml`, and `.st` files
already in this repo arrived — authored and pushed directly from a VS Code window connected to
this same Pi.

---

## Order of operations reminder

This folder only covers the *edges* of the workflow (connect in, push changes out). The middle —
identifying the serial adapter, granting permissions, bench-testing with `mbpoll`, and mapping
into CODESYS — is documented in `linux-integration/README.md` and `codesys-modbus-integration/README.md`.
See the root `README.md`'s "Linux ↔ Raspberry Pi ↔ CODESYS ↔ GitHub" section for the full
six-step sequence and how these three folders fit together.
