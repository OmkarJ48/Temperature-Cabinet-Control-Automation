# Git Workflow Checklist

**Quick reference guide before making changes to the repo.**

## Branch Status

Current working branch: `Omkar_Temperature_Cabinet_Setpoint_Control`

Verify before each session:
```bash
git status
# Expected: "Your branch is up to date with 'origin/Omkar_Temperature_Cabinet_Setpoint_Control'"
```

---

## Step-by-Step Workflow

### 1. **Sync Latest Changes** (Always do this first)

```bash
git fetch origin
git pull origin Omkar_Temperature_Cabinet_Setpoint_Control
```

Expected output:
```
Already up to date.
# OR
Fast-forward
 [files changed]
```

---

### 2. **Make Your Changes**

Edit files as needed:
```bash
# Example: Edit a file
nano src/POUs/FB_CabinetSetpointControl.st

# Example: Add new files to a folder
cp new_file.py codesys-python-tcp-integration/python-gateway/
```

---

### 3. **Check Status Before Committing**

```bash
git status
```

Expected to see:
- Modified files (red text prefixed with `M`)
- New files (red text prefixed with `??`)

**Nothing should show "deleted" unless intentional.**

---

### 4. **Stage Your Changes**

```bash
# Stage specific files
git add src/POUs/FB_CabinetSetpointControl.st

# OR stage all changes
git add .

# Verify staging
git status
# Should show green text with "Changes to be committed"
```

---

### 5. **Commit with Clear Message**

```bash
git commit -m "Your clear commit message describing the changes"
```

**Message format tips:**
- ✅ `Fix pymodbus compatibility in gateway`
- ✅ `Update temperature range to -40 to 200°C`
- ✅ `Add test script for gateway validation`
- ❌ `changes` (too vague)
- ❌ `update` (unclear what)

Expected output:
```
[Omkar_Temperature_Cabinet_Setpoint_Control abc1234] Your commit message
 N files changed, M insertions(+), D deletions(-)
```

---

### 6. **Push to Remote**

```bash
git push origin Omkar_Temperature_Cabinet_Setpoint_Control
```

Expected output:
```
Enumerating objects: 5, done.
Counting objects: 100% (5/5), done.
Delta compression using up to 8 threads
Compressing objects: 100% (3/3), done.
Writing objects: 100% (5/5), 850 bytes | 850.00 KiB/s, done.
Total 5 (delta 2), reused 0 (delta 0), pack-reused 0 (from 0)
To github.com:OJ4884/Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI.git
   abc1234..def5678  Omkar_Temperature_Cabinet_Setpoint_Control -> Omkar_Temperature_Cabinet_Setpoint_Control
```

---

### 7. **Verify Push Success**

```bash
git status
```

Expected:
```
On branch Omkar_Temperature_Cabinet_Setpoint_Control
Your branch is up to date with 'origin/Omkar_Temperature_Cabinet_Setpoint_Control'
nothing to commit, working tree clean
```

---

## Common Scenarios

### Scenario A: "I realized I made a mistake in my commit message"

```bash
# Amend the last commit (before pushing)
git commit --amend -m "Corrected commit message"
git push origin Omkar_Temperature_Cabinet_Setpoint_Control
```

### Scenario B: "I committed something I didn't mean to"

```bash
# Undo the last commit (keeps your changes)
git reset --soft HEAD~1
git status  # See what's staged

# Re-stage only what you want
git add file1.txt
git commit -m "Corrected commit with only file1"
git push origin Omkar_Temperature_Cabinet_Setpoint_Control
```

### Scenario C: "Remote has changes I don't have locally"

```bash
# Pull the latest
git pull origin Omkar_Temperature_Cabinet_Setpoint_Control

# If there are conflicts, resolve them, then:
git add .
git commit -m "Merge remote changes"
git push origin Omkar_Temperature_Cabinet_Setpoint_Control
```

### Scenario D: "I want to see what changed before committing"

```bash
# See unstaged changes
git diff

# See staged changes
git diff --cached

# See changes in a specific file
git diff src/POUs/FB_CabinetSetpointControl.st
```

---

## Important Rules

⚠️ **ALWAYS follow this order:**
1. `git fetch` / `git pull` (sync first)
2. Make changes
3. `git add` (stage)
4. `git commit` (commit locally)
5. `git push` (push to GitHub)

⚠️ **NEVER:**
- Push to a different branch without explicit permission
- Force-push (`git push --force`) without asking
- Commit directly to `main` branch
- Mix multiple unrelated changes in one commit

✅ **ALWAYS:**
- Write clear commit messages
- Test changes before pushing (especially for code)
- Keep commits focused on one logical change
- Sync with remote before starting new work

---

## Quick Reference Commands

```bash
# Check current branch and status
git status

# Sync with remote
git pull origin Omkar_Temperature_Cabinet_Setpoint_Control

# See commit history
git log --oneline -10

# See what changed in last commit
git show

# See differences before committing
git diff

# Stage all changes
git add .

# Commit
git commit -m "message"

# Push
git push origin Omkar_Temperature_Cabinet_Setpoint_Control

# Undo last commit (keep changes)
git reset --soft HEAD~1
```

---

## Configuration (Already Set Up)

Your git is configured with:
```
pull.rebase = true                  (prevents merge conflicts)
branch.*.rebase = true              (per-branch rebase setting)
```

This means:
- ✅ Pulls will rebase instead of merge
- ✅ No divergence issues
- ✅ Cleaner commit history

---

## Need Help?

Common error → Solution:

| Error | Fix |
|-------|-----|
| "Your branch is ahead of origin" | Run `git push origin Omkar_Temperature_Cabinet_Setpoint_Control` |
| "Your branch is behind origin" | Run `git pull origin Omkar_Temperature_Cabinet_Setpoint_Control` |
| "nothing to commit" | You have no changes, or forgot to stage them with `git add .` |
| "fatal: not a git repository" | Navigate to repo folder: `cd Temperature-Cabinet-Setpoint-Control-from-CODESYS-HMI` |
| "divergent branches" | Run `git pull --rebase origin Omkar_Temperature_Cabinet_Setpoint_Control` |

---

**Last Updated:** 2026-07-21  
**Branch:** Omkar_Temperature_Cabinet_Setpoint_Control  
**Status:** ✅ Configured and ready
