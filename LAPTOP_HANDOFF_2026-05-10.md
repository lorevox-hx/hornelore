# Laptop Handoff — 2026-05-10 — patience-layer follow-up bank

## TL;DR — what the laptop needs

Pull two new commits from `origin/main`. Add ONE env flag. Restart stack
(migration 0007 applies automatically). Run the harness before Chrome.

Zero new pip dependencies — `lori_followup_bank` is pure-stdlib. No
new model files. Kokoro TTS unchanged from the 2026-05-07 install.

The full layered test plan is in `MORNING_HANDOFF_2026-05-10.md` once
you've pulled. This doc covers ONLY the laptop-side sync. Run it, then
read MORNING_HANDOFF for the test plan.

## Dev vs laptop state — confirmed via MAG-Chris workspace audit

### Git history

| Commit | MAG-Chris (dev) | Laptop | Action |
|---|---|---|---|
| `a026caf` WO-LORI-WITNESS-FOLLOWUP-BANK-01 — patience layer (code) | ✅ | ❌ | **PULL** |
| `28018ce` WO-LORI-WITNESS-FOLLOWUP-BANK-01 + lang-contract — tests + docs + ops | ✅ | ❌ | **PULL** |
| Earlier today's commits (chat_ws + Spanish guard + lang-contract) | ✅ | ❌ if last sync was 2026-05-07 | **PULL (fast-forward)** |

If laptop hasn't pulled since 2026-05-07, expect ~10-15 commits to fast-forward.

### `.env` state (MAG-Chris confirmed line 244)

| Variable | MAG-Chris | Laptop | Action |
|---|---|---|---|
| `HORNELORE_OPERATOR_FOLLOWUP_BANK=1` | ✅ present | ❌ unknown | **ADD** if absent |
| `LORI_TTS_ENGINE=kokoro` | ✅ | should be ✅ from 2026-05-08 | verify |
| `LORI_TTS_KOKORO_VOICE_EN=af_heart` | ✅ | should be ✅ | verify |
| `LORI_TTS_KOKORO_VOICE_ES=ef_dora` | ✅ | should be ✅ | verify |

### Database

Migration `0007_follow_up_bank.sql` creates the `follow_up_bank`
table. Applied automatically by `init_db()` on stack startup. No
manual migration step.

If laptop's DB path differs from `.runtime/hornelore.sqlite` (some
laptop installs use `data/hornelore.sqlite`), the migration still
applies — `init_db` resolves the path from the runtime config.

### Pip dependencies

NONE. `lori_followup_bank.py` imports only `re`, `dataclasses`,
`typing` from stdlib. Nothing new to install.

---

## Sync commands (run on laptop)

### Step 1 — pull from origin

First, on MAG-Chris (dev), confirm push happened:

```bash
# On MAG-Chris (you should already be here)
cd /mnt/c/Users/chris/hornelore
git log --oneline -3
git push origin main
```

Then on laptop:

```bash
cd /mnt/c/Users/chris/hornelore
git fetch origin
git status                          # confirm "behind by N commits"
git pull origin main                # fast-forward
git log --oneline -5                # confirm a026caf and 28018ce arrived
```

If `git fetch` shows origin/main ALREADY at the right commit but `git
status` says "up to date", laptop already pulled — skip to Step 2.

### Step 2 — env adjustment

```bash
cd /mnt/c/Users/chris/hornelore
cp .env ".env.bak_$(date +%Y%m%d_%H%M%S)"

# Add operator follow-up bank flag if absent
grep -q "HORNELORE_OPERATOR_FOLLOWUP_BANK" .env || \
  echo "HORNELORE_OPERATOR_FOLLOWUP_BANK=1" >> .env

# If grep found it but it's set to 0, flip to 1
sed -i 's/HORNELORE_OPERATOR_FOLLOWUP_BANK=0/HORNELORE_OPERATOR_FOLLOWUP_BANK=1/' .env

# Verify
grep "HORNELORE_OPERATOR_FOLLOWUP_BANK" .env
# Expected output:  HORNELORE_OPERATOR_FOLLOWUP_BANK=1

# Sanity check the rest of the lang-contract + Kokoro env that should
# already be present from 2026-05-07 / 2026-05-08:
echo "--- Kokoro present? ---"
grep -E "^(LORI_TTS_ENGINE|LORI_TTS_KOKORO_VOICE_EN|LORI_TTS_KOKORO_VOICE_ES)=" .env
echo "--- Llama path present? ---"
grep -E "^(MODEL_PATH|HF_HUB_OFFLINE)=" .env
```

If the Kokoro + Llama lines are missing, see `LAPTOP_HANDOFF_KOKORO_INSTALL.md` — that's a longer setup that was supposed to land on 2026-05-08. The patience-layer commit doesn't depend on it being done today, but Lori's voice will be silent (TTS returns empty audio) until those are configured.

### Step 3 — Pre-stack-restart static verification

Same Layer 1 you ran on MAG-Chris before committing:

```bash
cd /mnt/c/Users/chris/hornelore

python3 -m unittest \
  tests.test_lori_followup_bank \
  tests.test_lori_witness_mode \
  tests.test_lori_session_language_contract \
  tests.test_lori_meta_question

python3 -m py_compile \
  server/code/api/services/lori_followup_bank.py \
  server/code/api/services/lori_witness_mode.py \
  server/code/api/routers/chat_ws.py \
  server/code/api/routers/operator_followup_bank.py \
  server/code/api/prompt_composer.py \
  server/code/api/db.py \
  server/code/api/main.py \
  scripts/set_session_language_mode.py
echo "Pre-stack-restart verification: PASS"
```

Expected: 190/190 green, zero py_compile errors.

If anything fails on the laptop that didn't fail on MAG-Chris, the
likely cause is a Python version drift OR a half-applied pull. Show
me the failure and `python3 --version`.

### Step 4 — start stack + warmup wait

Chris owns stack lifecycle. After your usual launcher, wait the **full
4 minutes** before sending the first chat turn. The HTTP listener
comes up at ~60-70s but the LLM weights + extractor warmup continues
for another 2-3 minutes.

```bash
# Probe extractor warmup with a tiny extract — if round-trip < 30s, ready
time curl -s -X POST http://localhost:8000/api/extract-fields \
  -H "content-type: application/json" \
  -d '{"answer":"My name is Test","section":"personal","question":"What is your name?"}' | head -c 200
echo
```

If that takes <30s and returns a JSON shape, stack is hot. Now run
Layer 2 verification.

### Step 5 — Layer 2: confirm migration applied + bank endpoint live

```bash
cd /mnt/c/Users/chris/hornelore

# Find the DB path
ls .runtime/hornelore.sqlite 2>/dev/null && DB=.runtime/hornelore.sqlite
ls data/hornelore.sqlite 2>/dev/null && DB=data/hornelore.sqlite
echo "DB: $DB"

# Schema check
sqlite3 "$DB" ".schema follow_up_bank"
```

Expected: prints the `CREATE TABLE follow_up_bank (...)` statement
with all 13 columns + 3 indexes. If empty, migration didn't apply —
restart the stack again, the migration runner only fires on
`init_db()` first call.

```bash
# Operator endpoint live
curl -s "http://localhost:8000/api/operator/followup-bank/summary" | head -3
```

Expected: JSON like `{"sessions":[],"count":0}`. If 404 or `{"detail":
"follow-up bank operator surface disabled..."}`, the env flag isn't
loaded — uvicorn doesn't auto-reload `.env`, you need a full process
kill + restart.

### Step 6 — Layer 3: harness with logs streaming

**Terminal 1 (logs, leave running):**

```bash
cd /mnt/c/Users/chris/hornelore
tail -n 0 -f .runtime/logs/api.log | \
  grep -E '\[lang-contract\]|\[followup-bank\]|\[bank-flush\]|\[floor-hold\]|\[witness\]'
```

**Terminal 2 (harness):**

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/replay_kent_deep_witness.py
```

Wait for completion (~3-4 minutes for 10 tests). Then capture three
artifacts:

**(a) Harness stdout** — copy the whole `[1/10] TEST-A` through
`=== Topline ===` block.

**(b) Logs from Terminal 1** — 30-50 lines around the run window.
Especially: `[chat_ws][lang-contract] EMERGENCY english lock`,
`[chat_ws][followup-bank][immediate] intent=...`,
`[chat_ws][followup-bank][to-bank] n=N intents=...`,
`[followup-bank] added id=...`,
`[chat_ws][followup-bank] persisted N/M doors`.

**(c) Bank state via curl:**

```bash
cd /mnt/c/Users/chris/hornelore
CONV_ID=$(grep "conv_id" $(ls -t docs/reports/kent_deep_witness_*.md | head -1) | head -1 | awk '{print $NF}' | tr -d '`')
echo "conv_id: $CONV_ID"
curl -s "http://localhost:8000/api/operator/followup-bank/session/$CONV_ID/all" | python3 -m json.tool
```

Paste back to dev (here) for evaluation. The hard gates:

1. ZERO Spanish/Spanglish in any LORI line.
2. TEST-A: ≤7 word ack, no question, `[floor-hold]` log marker.
3. TEST-COMMS-1959: Lori asks OR banks `communication_with_partner_overseas`.
4. TEST-G: Lori asks or banks `fragile_name_confirm_landstuhl` / `_ramstein` / `_schmick`.
5. TEST-F: Lori catches `role_pivot_courier_bridge` or `role_pivot_photography`.
6. `[followup-bank] persisted N` lines exist.
7. ZERO `[lang-contract][es-repair]` lines.

If ≥6 of 7 clear, proceed to Step 7. Otherwise, paste back and we
patch the door detector before going further.

### Step 7 — Chrome typed smoke (only after harness clears)

Open `http://localhost:8000/ui/hornelore1.0.html`.

Click **+ Add Test Narrator** → name it "Kent army-at-18 smoke".
Pick session style **Clear & Direct**. Cognitive Support Mode: OFF.

Pin the narrator to english (operator-side) for defense in depth:

```bash
# In a third terminal — find the new narrator's UUID
python3 scripts/set_session_language_mode.py --list | grep -i "Kent army"
# Then pin
python3 scripts/set_session_language_mode.py --name "Kent army" --mode english --primary en --code-switching false
```

Or use `--person-id <uuid>` with the UUID from `--list` if name match
is ambiguous.

Click **Start Narrator Session**. When the chat input is ready, paste
this as Kent (typed, NOT mic):

> I went down to the railroad depot in Stanley with my dad. From Stanley I went by train to Fargo for the induction process. They put us through the physical exam, the mental exam, and qualifying tests. I scored high enough that the Army put me in charge of meal tickets for a trainload of recruits going west.

**Expected Lori (immediate response):**
- English only (no Spanish)
- One receipt + one question max
- Receipt should reflect Stanley → Fargo → induction/testing → high score → meal tickets
- Question should be about Fort Ord, the train ride, OR the induction process — NOT scenery / sounds / feelings / camaraderie

Then type:

> Yeah, that's right.

**Expected Lori (bank flush):**
- Starts with: `I want to come back to one detail you mentioned earlier.`
- Then asks ONE banked question: probably the Fargo exam process, or
  the meal-ticket responsibility detail, or the conductor-and-meals
  followup.

### Stop rules — abort the smoke immediately

If Lori does any of these, screenshot + paste back:

- Spanish or Spanglish (Capté / `¿Qué` / `Tú` / `, y ` mid-English)
- Asks scenery / sights / sounds / smells / camaraderie / teamwork
- Asks "how did that feel" / "what was that like" when Kent gave facts
- Speaks AS Kent ("we were", "our son", "my wife", "I went")
- Asks more than one question per turn
- Bank-flush interrupts Kent mid-chapter (priority 1-3 immediate door
  should win; if flush fires anyway, that's a routing bug)
- Confirms Stanley/Fargo/Bismarck without Kent first signaling
  uncertainty (Tier B fragile-name overfire)

The architecture is structurally correct. If the smoke shows any of
the above, the failure is door-detector phrasing coverage — a few-line
patch, not an architectural rewrite.

---

## What did NOT change since 2026-05-07 laptop sync

- LLM model (Llama 3.1-8B Q4 unchanged)
- TTS engine (Kokoro from 2026-05-08 unchanged)
- Whisper STT
- Database schema except for ADDITIVE migration 0007
- Frontend bundle (no UI commits in this batch)
- Story trigger / extractor / safety classifier / reflection shaper

If the laptop was working with Mary on 2026-05-07 / 2026-05-09, it
will keep working — this batch is purely additive (new bank service,
new operator endpoints, new migration table).

## Rollback plan if anything breaks

The migration is additive (CREATE TABLE IF NOT EXISTS). Rollback is
a `git revert a026caf 28018ce` followed by stack restart — the
follow_up_bank table can stay (it's harmless when no code reads it).

```bash
# If you need to roll back
cd /mnt/c/Users/chris/hornelore
git revert --no-commit 28018ce a026caf
git commit -m "Revert WO-LORI-WITNESS-FOLLOWUP-BANK-01 — see paste-back"
# Restart stack
```

Do NOT roll back without telling me first — there's a high chance the
"failure" is a missing env flag or an un-restarted stack, not the
code.
