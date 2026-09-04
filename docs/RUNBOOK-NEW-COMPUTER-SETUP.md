# Runbook — moving Hornelore to a new computer

**Written 2026-09-04** at the Phase 3 transition. Everything here is derived
from the paths and commands this repo actually uses; nothing is invented from
a general Windows/WSL guide. Where a value must be measured rather than copied,
the runbook says so and gives the command.

---

## 0. What actually has to move

Three things, and only the first is in Git.

| What | Where it lives now | In Git? |
|---|---|---|
| The repository | `C:\Users\chris\hornelore` (WSL: `/mnt/c/Users/chris/hornelore`) | **yes** |
| The narrator database and archives | `C:\hornelore_data` (`DATA_DIR`) | **no — and it is the irreplaceable half** |
| Local reports and runtime logs | `docs/reports/`, `.runtime/` | no, gitignored on purpose |

**`C:\hornelore_data` is the family's memory.** Kent's and Janice's words live
there, not in the repo. A move that clones the repo and forgets `DATA_DIR`
produces a working application with no life in it.

---

## 1. Before you touch the new machine

On the OLD machine, from WSL:

```bash
cd /mnt/c/Users/chris/hornelore
git status --porcelain          # must be empty except known untracked items
git log --oneline -3
```

Push anything outstanding from GitHub Desktop first. A move is the worst time
to discover uncommitted work.

Then confirm what the database actually is — read it, don't assume:

```bash
cd /mnt/c/Users/chris/hornelore
grep -E '^(DATA_DIR|DB_NAME)=' .env
python3 scripts/phase2_verify_ledger.py | head -5
```

The second command prints the resolved database path it opened. **That path is
what you are moving.** An earlier session read a stale in-repo
`data/db/lorevox.sqlite3` and reported zero candidates for a narrator with
five; the `.env` values are the truth.

---

## 2. Copy the data first, and verify it arrived

Copy `C:\hornelore_data` to the same path on the new machine. Then verify by
COUNTING, not by looking at the folder:

```bash
cd /mnt/c/Users/chris/hornelore
python3 - <<'EOF'
import sqlite3, os, pathlib
p = pathlib.Path(os.getenv("DATA_DIR", "/mnt/c/hornelore_data")) / "db" / "hornelore.sqlite3"
con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
for t in ("people", "turns", "story_candidates", "profiles",
          "turn_extraction_ledger", "turn_extraction_results"):
    try:
        print(f"{t:26} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    except Exception as e:
        print(f"{t:26} MISSING — {e}")
EOF
```

Run the same block on the old machine and compare the numbers. Equal counts is
the check; "the folder looks right" is not.

---

## 3. Clone and set up the repo

```bash
cd /mnt/c/Users/chris
git clone <the GitHub remote> hornelore
cd hornelore
```

Recreate `.env` — it is **not** in Git. At minimum it carries:

```
DATA_DIR=/mnt/c/hornelore_data
DB_NAME=hornelore.sqlite3
```

Copy the old `.env` across rather than retyping it; it also holds the Google
Photos Picker refresh token and any model paths. **Never commit it.**

---

## 4. The three interpreters — measure, never assume

This repo has `python3`, `.venv` (tests) and `.venv-gpu` (serving), and they do
**not** carry the same stack. Run the probe from `CLAUDE.md` in WSL:

```bash
cd /mnt/c/Users/chris/hornelore
for p in python3 .venv/bin/python .venv-gpu/bin/python; do
  printf '%-24s ' "$p"
  "$p" -c 'import sys; print(sys.version.split()[0], end=" ")' 2>/dev/null || { echo "(not runnable)"; continue; }
  for m in fastapi pydantic; do
    if "$p" -c "import $m" 2>/dev/null; then printf '%s ' "$m"; else printf '%s=ABSENT ' "$m"; fi
  done
  echo
done
```

Rebuild whichever is missing from `requirements-test.txt` and
`requirements-gpu.txt`. **`OK` with skips is not a pass** — a suite whose route
tests need fastapi *skips* on an interpreter without it and still prints `OK`.
Always read and report the skip count.

---

## 5. GPU / model

`.venv-gpu` is the serving venv and expects an NVIDIA card (the current machine
is a Blackwell RTX 50-series). If the new machine's GPU differs, the torch and
bitsandbytes wheels are what change; nothing in the application code is
GPU-specific. **The model and the 8,192-token window are LOCKED** — a move is
not an occasion to change either.

---

## 6. Prove the move, in this order

Cheapest first, so a failure tells you where you are.

```bash
# 1. Offline suites — no stack needed. Report the skip count.
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest \
  tests.test_value_grounding tests.test_kinship_group_guard \
  tests.test_correction_fallthrough tests.test_review_only_results \
  tests.test_confirmation_reasons tests.test_extraction_finalization \
  tests.test_eval_preservation_accounting tests.test_phase2_verify_ledger
```

```bash
# 2. Browser-module checks — Node only, no browser binary.
cd /mnt/c/Users/chris/hornelore
node scripts/ui/projection_authority_domtest.js
node scripts/ui/review_only_result_domtest.js
```

```bash
# 3. The database really is the one you moved.
cd /mnt/c/Users/chris/hornelore
python3 scripts/phase2_verify_ledger.py
```

Then start the stack yourself and, once the extractor is warm (**cold boot is
~4 minutes**; a `curl /` proves only that the socket is listening):

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/archive/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_move-verify.json
```

Compare against the last accepted baseline in `docs/reports/`. Read
`preservation_fates` alongside the pass count — a quarantined value is
preserved, not lost, and the pass count alone cannot tell you which.

---

## 7. Things that will bite

- **`docs/reports/` and `.runtime/` are gitignored and will be empty.** That is
  correct — they hold live narrator data and the public repo must not serve it.
  Do not "fix" the gitignore when a report refuses to stage; the refusal is the
  feature.
- **Agents do not run git here.** Commit from WSL, push from GitHub Desktop. A
  sandboxed agent that runs git can leave `.git/index.lock` behind, and the
  symptom is confusing: `git add` appears to work, `git commit` says nothing to
  commit, Desktop keeps showing changed files. Fix:
  `rm -f .git/index.lock`.
- **Two untracked items are off-limits by standing instruction:**
  `lori-review-20260901.zip` and `ziMVYqEP`. Move them if you want them; do not
  open them.
- **Sandbox bytecode:** any agent-side test run needs
  `PYTHONPYCACHEPREFIX=/tmp/pyc`, because `__pycache__` under `/mnt/c` can serve
  stale `.pyc` and make edited code appear not to have changed.

---

## 8. What "moved successfully" means

Not "it starts". All four:

1. the database row counts match the old machine;
2. the offline suites pass with a **reported** skip count;
3. both Node module checks pass;
4. a live eval lands within noise of the last accepted baseline — and the
   two identical-code runs on 2026-09-04 differed by **one case**, so the
   noise floor is about one, not five.
