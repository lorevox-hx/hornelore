# HANDOFF — Laptop Parity Diagnostic + Kiosk Roadmap Context

**Authored:** 2026-05-04 (main machine session)
**Purpose:** Bring the laptop into parity with the main machine so it runs the same Hornelore version, then later harden it for kiosk use (parent-alone narrator session).
**Audience:** Chris on the laptop, OR Claude running on the laptop reading this handoff.

---

## TL;DR — Run this first

The laptop's running an older Hornelore even after `git pull` because GitHub Desktop only pulls **files**, not running processes, env vars, or browser cache. Run the parity diagnostic below first to see what's actually mismatched, then act on the results. **Don't start any code work until parity is confirmed** — otherwise we're debugging shadows.

---

## Why this matters (strategic context)

The product roadmap is now two arcs, in order:

1. **Parent-Presentable Listener Arc** (~2 weeks of work, in progress on main machine).
   Acceptance: Janice or Kent sit down WITH CHRIS NEARBY, talk for 30-60 min, walk away with an experience that felt like being heard. Locked principle: when operational tidiness trades against narrator dignity, narrator dignity wins.

2. **Kiosk Hardening Arc** (~1-2 weeks AFTER Arc 1).
   Acceptance: Janice or Kent sit at the laptop ALONE, no operator visible, for an unsupervised session that doesn't surface operator-only UI, doesn't break on network glitches, and ends with a clean session artifact Chris can review remotely.

The laptop is the kiosk machine. It's not Arc 1 work — but if the laptop is in a bad state right now, we won't be able to test ANYTHING when Arc 2 starts. Fixing parity NOW costs 30 minutes; fixing it during Arc 2 costs days of wasted debugging.

The Lorevox/Hornelore architecture this fits into:
- **Archive → History → Memoir** (the truth pipeline)
- **CLAUDE.md principles 1-5** (no dual metaphors, no operator leakage, no system-tone outputs, no partial resets, provisional truth persists)
- **Kiosk machine** is where principles #2 (no operator leakage) and #4 (no partial resets) get the hardest stress test, because the narrator is alone and can do anything.

The laptop's current "still on old version after git pull" issue is a symptom of: the runtime stack on the laptop doesn't restart automatically when files change, AND `.env` / browser cache / DATA_DIR aren't part of git, so they drift independently from the repo.

---

## Step 1 — Run the parity diagnostic

Open WSL on the laptop. Then:

```bash
cat > /tmp/parity_check.sh <<'EOF'
#!/bin/bash
echo "=== HORNELORE PARITY CHECK ==="
echo "host: $(hostname)"
echo "date: $(date)"
echo ""
cd /mnt/c/Users/chris/hornelore 2>/dev/null || { echo "ERROR: repo path missing"; exit 1; }
echo "--- repo state ---"
echo "branch: $(git branch --show-current 2>/dev/null)"
echo "commit: $(git log -1 --oneline 2>/dev/null)"
echo "tracking: $(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo 'no upstream')"
echo "behind/ahead: $(git rev-list --left-right --count @{u}...HEAD 2>/dev/null || echo 'n/a')"
echo "dirty files: $(git status --short | wc -l)"
echo ""
echo "--- env state (sanitized) ---"
if [ -f .env ]; then
  echo ".env exists: yes ($(wc -l < .env) lines)"
  grep -E "^(HORNELORE_|MODEL_|DATA_DIR|API_PORT|UI_PORT|LOREVOX_)" .env | sed 's/=.*/=***/' | sort
else
  echo ".env exists: NO"
fi
echo ""
echo "--- key files mtimes ---"
ls -la --time-style=full-iso server/code/api/prompt_composer.py 2>/dev/null
ls -la --time-style=full-iso ui/hornelore1.0.html 2>/dev/null
ls -la --time-style=full-iso scripts/start_all.sh 2>/dev/null
echo ""
echo "--- runtime health ---"
echo "API:8000  $(curl -sS -m 3 http://localhost:8000/api/test-lab/system 2>&1 | head -c 80)"
echo "UI:8082   $(curl -sS -m 3 -o /dev/null -w '%{http_code}' http://localhost:8082/ui/hornelore1.0.html 2>&1)"
echo ""
echo "--- DATA_DIR contents ---"
DD=$(grep -E "^DATA_DIR=" .env 2>/dev/null | cut -d= -f2 | tr -d '"' | tr -d "'")
[ -n "$DD" ] && ls -la "$DD" 2>/dev/null | head -10
echo ""
echo "=== END PARITY CHECK ==="
EOF
chmod +x /tmp/parity_check.sh && /tmp/parity_check.sh
```

Save the output. Compare to the same script run on the main machine. **Diff them — the differences ARE the bug.**

---

## Step 2 — Diagnose from the output

Look at each section in order. Fix the FIRST mismatch you find before checking the next, because each one cascades.

### Section: repo state

| Output | Meaning | Fix |
|---|---|---|
| `branch:` not `main` | On the wrong branch | `git checkout main && git pull` |
| `behind/ahead: 5 0` (or any non-zero `behind`) | Laptop is N commits behind main | `git pull` |
| `dirty files: 0` | Clean tree (good) | — |
| `dirty files: > 0` | Local edits not committed | `git status` to see them; either commit + push, or stash, before pulling |
| `tracking: no upstream` | Branch isn't tracking origin | `git push -u origin main` |

If branch + commit match the main machine, files on disk are right. Move on.

### Section: env state

The `.env` file is **NOT in git** (intentionally — it has machine-specific paths, secrets, model paths). Mismatches here are the second-most-common cause.

| Symptom | Meaning |
|---|---|
| `.env exists: NO` | Laptop never had one. Copy from `.env.example` and customize for laptop paths. |
| `HORNELORE_SPANTAG=***` present on main, missing on laptop | Some env flags were added on main but not synced to laptop. Check `.env.example` for new keys. |
| `DATA_DIR` differs | Laptop is reading from a different DB. This explains why narrators / data look different. |
| `MODEL_PATH` differs | Laptop is loading a different LLM weights file. Could explain different output behavior. |

**To compare without leaking secrets:** on each machine run:

```bash
grep -E "^[A-Z_]+=" /mnt/c/Users/chris/hornelore/.env | sed 's/=.*/=***/' | sort > /tmp/env_keys_$(hostname).txt
```

Then `diff` the two `/tmp/env_keys_*.txt` files. Lines that exist on one but not the other = missing env keys. Once you know the names, copy the actual values manually.

### Section: key files mtimes

These mtimes show when the files were last touched ON THIS MACHINE. If main machine's `prompt_composer.py` was touched today and laptop's was touched 3 weeks ago, the laptop's `git pull` didn't actually update files (or you're looking at the wrong path).

| Symptom | Meaning |
|---|---|
| Laptop mtime is older than main mtime | Either the pull didn't run, OR the pull updated files but you're looking at the wrong path, OR there's a build artifact / cache that's stale. |
| Both mtimes match (within seconds) | Files are synced. Move on. |

### Section: runtime health

| Output | Meaning | Fix |
|---|---|---|
| `API:8000` returns JSON or `200` | Backend is running | — |
| `API:8000` returns "Connection refused" or empty | Backend NOT running OR running on different port | Start backend: `./scripts/start_all.sh` (or whatever your main machine uses) |
| `UI:8082 200` | Frontend is running | — |
| `UI:8082 000` or "Connection refused" | Frontend NOT running OR different port | Start UI server |
| API up but UI down (or vice-versa) | Stack started partially. Restart fully. | Stop everything, start fresh. |

**Critical**: if the backend is ALREADY RUNNING on the laptop, `git pull` did NOT restart it. The running process is using OLD code. You MUST stop and restart the stack after every pull. This is almost certainly your "still on old version" symptom.

### Section: DATA_DIR contents

| Symptom | Meaning |
|---|---|
| `ls` shows a different set of `.db` files | Laptop has its own narrator database, not synced from main. |
| `ls` errors / DATA_DIR missing | Path in `.env` is wrong or directory doesn't exist. |

The narrator database is **not** in git either. If you want laptop to have the same Christopher/Janice/Kent narrators as main, you'll need to copy the DB file across. (For Arc 2 / kiosk testing this matters; for Arc 1 development the laptop can have its own DB.)

---

## Step 3 — The most likely fix (run this if you don't want to debug)

Based on the symptom "old version even after git pull," the highest-probability cause is: **the running backend process didn't restart**. Try this nuclear option first:

```bash
cd /mnt/c/Users/chris/hornelore

# 1. Stop everything
# (Use whatever stop script you have, e.g. ./scripts/stop_all.sh
#  or just kill the python and the static server processes)

# 2. Pull latest
git pull

# 3. Hard-clear Chrome cache for localhost:8082
# In Chrome: Settings → Privacy → Clear browsing data → Cached images and files
# OR open DevTools → Application → Clear storage → Clear site data
# (this also clears localStorage which holds projection state — important)

# 4. Start fresh
./scripts/start_all.sh
# (or whatever your main machine startup script is)

# 5. Wait ~4 minutes for cold boot (LLM warmup)

# 6. Re-run parity check
/tmp/parity_check.sh
```

If after this the laptop still shows old behavior, the issue is deeper than process state — likely env or DATA_DIR drift.

---

## Step 4 — Email Chris (or note for self) what you found

After the diagnostic, write down:
- Branch + commit on laptop vs main
- Any env keys missing
- Whether the stack was running stale code (most likely yes)
- File mtimes for `prompt_composer.py` (the big change today)
- DATA_DIR path on laptop

This becomes the input for the eventual **WO-LAPTOP-PARITY-01** spec, which will land a one-command sync script (`scripts/laptop_sync.sh`) that does pull + restart + cache clear + health check in one go.

---

## What's been happening on the main machine (so you know what's new)

In case you're on the laptop and trying to figure out what's different:

### Today (2026-05-04)
- Built TEST-23 v1 + v2 harness (`scripts/ui/run_test23_two_person_resume.py`)
- Two narrators: Mary Holts (messy input) + Marvin Mann (clean input)
- v2 added TTS-gated wait that fixed the "race condition" producing most of our previous false-RED tests
- Architecture audit at `docs/reports/PROVISIONAL_TRUTH_ARCHITECTURE_AUDIT_2026-05-04.md` traced 9 paths and found that chat-extracted narrator data (Mary's name, etc.) DOES persist to `interview_projections.projection_json.pendingSuggestions` server-side — but Lori's `_build_profile_seed` only read `profiles.profile_json`, missing the bridge.
- WO-PROVISIONAL-TRUTH-01 originally scoped 7-10 days of schema migrations; audit collapsed it to ~1 day.
- Phase A landed: `_build_profile_seed` now reads BOTH canonical (profile_json) and provisional (projection_json fields + pendingSuggestions). 11 unit tests pass.
- TEST-23 v3 is the verification step (run it after pull).

### Locked principle #5 in CLAUDE.md
> Provisional truth persists. Final truth waits for the operator. The interview never waits.

### Files changed today (commits to look at)
- `server/code/api/prompt_composer.py` (Phase A read-bridge in `_build_profile_seed`)
- `tests/test_provisional_profile_seed.py` (new, 11 tests)
- `WO-PROVISIONAL-TRUTH-01_Spec.md` (revised from 7-phase to 4-phase)
- `docs/reports/PROVISIONAL_TRUTH_ARCHITECTURE_AUDIT_2026-05-04.md` (new)
- `CLAUDE.md` (principle #5 added)
- `scripts/ui/run_test23_two_person_resume.py` (new, ~1600 lines, the canary harness)

### After parity is confirmed on laptop, run TEST-23 v3
This verifies Phase A works end-to-end:

```bash
cd /mnt/c/Users/chris/hornelore && python -m scripts.ui.run_test23_two_person_resume --tag test23_v3 --clear-kv-between-narrators
```

Expected results:
- Mary post-restart: `name=True pob=True` (was False in v1+v2)
- Mary recall stronger during session (provisional values surface)
- Marvin post-restart: still PASS, possibly stronger (more buckets)
- Era cell PASSes from v2 hold
- No new schema migrations applied

---

## What's coming next (Listener Arc sequencing — locked)

After v3 confirms Phase A:

1. WO-PROVISIONAL-TRUTH-01 Phase C — retire inline shadow-review widget (~half day)
2. WO-PROVISIONAL-TRUTH-01 Phase D — operator promotion surface in Bug Panel (~1.5 days, **timeboxed; pivot to Patch C if stretching**)
3. **BUG-LORI-REFLECTION-02 Patch C — runtime shaping** (~1.5 days, **load-bearing for parent-presentable**)
4. SAFETY-INTEGRATION-01 Phase 2 — LLM second-layer classifier (~1 day)
5. WO-NARRATIVE-CUE-LIBRARY-01 Phase B — sacred-silence cue detector (~3 days)
6. Long-session endurance + TEST-22 isolation (~2-3 days)

After this arc: parent-presentable supervised session works.

Then Kiosk Arc starts.

---

## What's coming for the laptop (Kiosk Arc — after Listener Arc)

Listed here so the laptop has a sense of its eventual destination:

1. **WO-LAPTOP-PARITY-01** — bit-equivalent state with main machine. One command sync script (`scripts/laptop_sync.sh`) that does git pull + rebuild + restart + cache clear + health check. Idempotent, safe to re-run.
2. **WO-KIOSK-MODE-01** — operator UI fully hidden. No Bug Panel access for narrator. No Operator tab visible. No nav chrome. Single-purpose narrator view.
3. **Network resilience** — WS reconnect on drops, offline-mode messaging, queued writes, no error UI surfaced to narrator.
4. **Multi-narrator session boundary** — each narrator sit-down opens a fresh session, no state leak from previous narrator. localStorage clears between narrators on the kiosk machine.
5. **Operator remote review surface** — Chris reviews from main machine while parent sat at laptop separately. Read-only sync of session artifacts.

The locked CLAUDE.md principles already cover most kiosk requirements:
- *No operator leakage* — kiosk can't show operator UI to narrator
- *No system-tone outputs* — kiosk Lori sounds like a person
- *No partial resets* — kiosk Reset Identity is atomic

The Kiosk Arc work is about *enforcing those under unsupervised conditions* — locking operator UI behind explicit role gates, blocking narrator access to dev tools, ensuring localStorage clears between narrators, etc.

---

## Questions to ask Claude on the laptop (if Claude is reading this)

Have laptop Claude help you:
1. Run the parity diagnostic above
2. Diff the output against what was on main machine (paste both into the chat)
3. Identify the FIRST mismatch causing the symptom
4. Apply the fix from Step 3 if it's the obvious "stack didn't restart" case
5. Re-run diagnostic to confirm parity
6. Then — and only then — try running TEST-23 v3 to see if Phase A landed cleanly

If laptop Claude is unfamiliar with the project, point it at:
- `CLAUDE.md` (principles + changelog)
- `docs/reports/PROVISIONAL_TRUTH_ARCHITECTURE_AUDIT_2026-05-04.md` (today's architecture work)
- `WO-PROVISIONAL-TRUTH-01_Spec.md` (the active WO)
- This file

Don't start any code work on the laptop until the parity check shows clean output. The symptom you're chasing might just be "the backend was running stale code" — a 30-second fix that reveals the laptop is fine, just needed a restart.

---

## End of handoff

If you're reading this on the laptop and the diagnostic surfaced something other than "stack needed restart," reply with the diagnostic output and we'll figure out the next step. Don't blind-fix.
