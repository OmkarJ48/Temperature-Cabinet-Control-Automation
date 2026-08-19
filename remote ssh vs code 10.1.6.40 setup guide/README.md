# Remote-SSH (VS Code) + GitHub Workflow

**Author:** OJ (Omkar Joshi) — Oliver Mechatronics  
**Applies to:** Any laptop connecting to the Raspberry Pi at **10.1.6.40** (`RnD Prototype`) that hosts the Temperature Swing integration development environment  
**Covers:** Remote development workflow for the tlelean/RnD repository on branch `Omkar_Temperature_Swing_Integration`

This folder covers the tooling layer only — how you get a terminal and an editor *onto* the Pi,
and how code changes made there get back to GitHub. It focuses on the development environment setup
and the GitHub workflow, keeping it separate from the CODESYS project configuration and hardware-specific
concerns for clarity and independent troubleshooting.

---

## Step 1: Connect to the Pi from VS Code

1. Install the **Remote - SSH** extension in VS Code (once, on your laptop).
2. `Ctrl+Shift+P` → **Remote-SSH: Connect to Host…** → enter:
   ```
   mechatronics@10.1.6.40
   ```
3. VS Code re-opens with its terminal, file explorer, and extensions all running **on the Pi**,
   not your laptop. Every command from here on (`git`, `python`, `nano`, etc.) executes on the Pi itself,
   over the SSH session — not locally.
4. Open the project folder via **File → Open Folder**:
   ```
   ~/RnD
   ```
   This is the tlelean/RnD repository cloned on the Pi with the `Omkar_Temperature_Swing_Integration` branch
   checked out. VS Code's Source Control panel talks to GitHub exactly as it would from a
   local clone — it is just physically executing on the Pi's filesystem.

If the connection fails, check:
- The Pi is powered on and on the same network as your laptop (ping `10.1.6.40` first).
- SSH is enabled on the Pi (`sudo systemctl status ssh`).
- Your SSH key (if used) is loaded, or the password is correct.
- If VS Code Server initialization hangs ("Initializing VS Code Server..."), kill it on the Pi and retry:
  ```bash
  rm -rf ~/.vscode-server
  ```
  Then reconnect from VS Code — this forces a fresh server install.

---

## Step 2: GitHub workflow from the Pi

Because the Remote-SSH session's Source Control panel runs *on the Pi*, working with the tlelean/RnD repo
from `10.1.6.40` is the same Git workflow as any other clone — there is nothing Pi-specific
about it beyond where the files physically live.

**Day-to-day (repo already cloned):**

```bash
cd ~/RnD

# Activate Python virtual environment (do this FIRST, every terminal session)
source venv/bin/activate
# (you should see (venv) at the start of your prompt now)

# Then sync with GitHub
git config pull.rebase true
git status
git fetch origin Omkar_Temperature_Swing_Integration
git pull origin Omkar_Temperature_Swing_Integration
```

Stage and commit new/changed files (ST code, docs, configs, etc.) either via the VS Code Source
Control UI, or from the integrated terminal:

```bash
# Make sure venv is still activated (you should see (venv) in your prompt)
# If not, run: source venv/bin/activate

git add <files>
git commit -m "…"
git push -u origin Omkar_Temperature_Swing_Integration
```

**First-time clone (fresh Pi, repo not present yet):**

```bash
# Clone the repo
git clone -b Omkar_Temperature_Swing_Integration https://github.com/tlelean/RnD.git

# Navigate into repo
cd RnD

# Set rebase strategy for clean history
git config pull.rebase true

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate
# (you should see (venv) at the start of your prompt)

# Install Python dependencies (if requirements.txt exists)
# pip3 install -r requirements.txt
```

The venv will remain active for the current terminal session. Each time you open a new terminal, activate it again with:
```bash
source venv/bin/activate
```

This Remote-SSH + GitHub path is how the `.html`, `.md`, `.py`, `.st`, and other development files
are authored and pushed directly from a VS Code window connected to this Pi.

---

## Step 3: Mirroring to OmkarJ48 Repository

Work conducted on tlelean/RnD `Omkar_Temperature_Swing_Integration` branch is mirrored to the
OmkarJ48/Temperature-Cabinet-Control-Automation repository in the
`Omkar_Temperature_Swing_Integration/temperature swing integration/` folder structure.

This keeps the development history documented and provides a secondary backup location for all work.
When pushing to tlelean/RnD, ensure corresponding documentation and findings are also committed
to the OmkarJ48 repository's temperature swing integration folder.

---

## Order of operations reminder

This folder only covers the *edges* of the workflow (connect in, push changes out). The middle —
the actual CODESYS development, testing methodology, and hardware interaction — is documented in the
tlelean/RnD repository's documentation and the temperature swing integration folder structure.

For the full development sequence (Stages 1–8: Understand → Design → Code → Test → Integrate),
refer to the Development_history folder in the temperature swing integration directory.

---

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| **SSH connection refused** | Verify Pi is on network and SSH is running: `sudo systemctl status ssh` on Pi |
| **VS Code Server hangs on initialization** | On Pi: `rm -rf ~/.vscode-server`, then reconnect from VS Code |
| **Git push fails (authentication)** | Ensure SSH keys are configured: `ssh-keygen -t ed25519` on Pi if needed, add public key to GitHub |
| **venv not found** | Create it: `python3 -m venv ~/RnD/venv` and activate with `source ~/RnD/venv/bin/activate` |
| **Git branch tracking issues** | Run `git branch -u origin/Omkar_Temperature_Swing_Integration Omkar_Temperature_Swing_Integration` |

