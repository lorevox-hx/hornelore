# Morning handoff — 2026-05-10 — patience layer + receipt rebuild

You're picking up after the overnight build of WO-LORI-WITNESS-FOLLOWUP-BANK-01 + the receipt + intent-priority rebuild + the session-language contract. The work-orders Chris signed off on last night are landed in tree, tested, and ready to commit. Goal: review, commit, push, then try the army-at-18 chapter with Kent.

## What's in tree (uncommitted) on /mnt/c/Users/chris/hornelore

Fresh from overnight:

**New files:**
- `server/code/db/migrations/0007_follow_up_bank.sql` — schema for the per-session bank.
- `server/code/api/services/lori_followup_bank.py` — Door dataclass + door detector + immediate/bank selector + flush triggers + flush composer. Pure-stdlib, no LLM, no DB.
- `server/code/api/routers/operator_followup_bank.py` — read-only Bug Panel endpoints (gated `HORNELORE_OPERATOR_FOLLOWUP_BANK=1`).
- `tests/test_lori_followup_bank.py` — 31 tests covering all 6 priority levels, selector, flush, composer.
- `tests/test_lori_session_language_contract.py` — 7 tests for english/spanish/mixed pin.
- `scripts/set_session_language_mode.py` — operator pin tool.
- `docs/reports/KENT_TRANSCRIPT_STUDY_2026-05-10.md` — your transcript study (already on disk for review).
- `MORNING_HANDOFF_2026-05-10.md` — this file.

**Modified files:**
- `server/code/api/db.py` — bank accessors (followup_bank_add, get_unanswered, get_all, mark_asked, mark_answered, get_by_id, clear_session).
- `server/code/api/main.py` — register operator_followup_bank router.
- `server/code/api/routers/chat_ws.py` — five integrations:
  1. `_HARDCODED_ENGLISH_PERSON_IDS` constant including Kent harness UUID — bypasses profile_json entirely for known english narrators.
  2. Early lang-contract resolution at handler top — reads `_session_lang_mode` from profile_json once, threads everywhere.
  3. Floor-hold short-circuit (TEST-A): emits "Take your time." / "I'm listening." / "Keep going." with no LLM call.
  4. STRUCTURED_NARRATIVE branch runs door detection → picks immediate (priority 1-3) → banks rest. Validator-fallback uses `compose_structured_witness_receipt` with the immediate door's question_en threaded in.
  5. Bank-flush short-circuit at handler top: when narrator turn is short with no door / says "what else" / floor released / operator click, emits "I want to come back to one detail you mentioned earlier. {Q}" deterministically.
  6. Post-LLM Spanish-scaffolding repair guard: english-locked turns with any Capté / ¿Qué / Tú / ¿ leak get repaired to deterministic English fallback.
- `server/code/api/services/lori_witness_mode.py` — split into `compose_chronological_chain_receipt()` (receipt only, no question) + `compose_structured_witness_receipt()` (receipt + immediate-door question, falls through to legacy intent bank when no door supplied).
- `server/code/api/prompt_composer.py` — `_build_profile_seed` surfaces `session_language_mode` / `primary_language` / `allow_code_switching` from profile_json with operator-tolerant alias normalization.
- `.env.example` — documents `HORNELORE_OPERATOR_FOLLOWUP_BANK=0`.

## Test gates (all green)

- `tests.test_lori_followup_bank` — 31 tests
- `tests.test_lori_witness_mode` — 87 tests
- `tests.test_lori_session_language_contract` — 7 tests
- `tests.test_lori_meta_question` — 58 tests

**183/183 green** across the four packs touching the patience-layer + receipt rebuild + lang-contract changes.

AST parse green on all 8 modified Python files.

## The architecture you signed off on, in code

Per turn flow for Kent's session:

```
Narrator sends turn
  ↓
chat_ws _is_floor_hold check  — if SYSTEM_FLOOR_HOLD, emit "Take your time." → return
  ↓
chat_ws lang-contract resolution — Kent UUID hardcoded → _session_lang_mode = "english"
  ↓
chat_ws witness detection — looks_spanish bypassed for english-locked, _wm_lang = "en"
  ↓
chat_ws bank-flush check — short-answer-no-door / "what else" / floor-released / operator-click
  → if YES: pull lowest-priority unanswered banked question
  → emit "I want to come back to one detail you mentioned earlier. {Q}" → return
  ↓
chat_ws witness STRUCTURED_NARRATIVE branch:
  → bank.detect_doors(user_text) — surfaces priority 1-6 doors
  → bank.select_immediate_and_bank(doors) → (immediate_door, doors_to_bank)
  → if immediate_door: stash question_en for fallback composer
  → set runtime71["witness_receipt_mode"] = True for prompt directive
  ↓
LLM runs with WITNESS RECEIPT directive
  ↓
Post-LLM: validate_witness_receipt(final_text, narrator_text)
  → if FAIL: compose_structured_witness_receipt(narrator_text,
              llm_question=final_text,
              immediate_door_question=immediate_door.question_en)
              → "You went from Stanley to Fargo, then Fort Ord, M1
                 expert, Nike Hercules training, and Germany.
                 How did you and Janice keep in touch from Germany
                 in 1959 — letters, phone calls, telegrams?"
  ↓
Post-LLM: lang-contract Spanish-scaffolding repair guard
  → english-locked + any ¿/Capté/Tú/¿Qué leak → recompose EN
  ↓
persist_turn_transaction
  ↓
archive_append_event
  ↓
**bank-write**: persist all _doors_to_bank rows to follow_up_bank table
  → priority 4 rank-asymmetry (private + General Schmick)
  → priority 5 daily-life (off-duty in Kaiserslautern)
  → priority 6 medical-family (premature/CP if narrator mentioned)
  ↓
WS done
```

## Door priority hierarchy (locked per Chris's signoff)

**Priority 1 — fragile-name confirms** (immediate ask):
- Self-correction patterns: "not X, was Y" / "I meant Y"
- Fragile place/person names: Landstuhl / Ramstein / Kaiserslautern / Frankfurt / Fort Ord / Stanley / Fargo / Bismarck / Schmick / Duffy / Salamander / Hochspeyer / Wiesbaden / Minot / Norway / Spokane

**Priority 2 — communication / logistics** (immediate ask):
- Communication-with-spouse-from-overseas (Germany + Janice + 1959 / letter / contacted / "not like today where you text")
- Spouse travel after wedding

**Priority 3 — role transition** (immediate ask):
- Photography pivot
- Courier-as-bridge mechanism
- Career choice under constraint (ASA-vs-Nike)

**Priority 4 — relationship / personality** (BANK ONLY — never immediate):
- Rank asymmetry (private + General → "yes-sir/no-sir or knew you personally?")
- Worked-for-boss

**Priority 5 — daily life / off-duty texture** (BANK ONLY):
- Living arrangements ("we were living in X")

**Priority 6 — medical / family** (BANK ONLY, asked carefully later):
- Premature + family member
- CP / cerebral palsy

## Refinements Chris asked for (landed 2026-05-10 night-shift end)

1. **Two-tier fragile-name detection** — Stanley/Fargo/Bismarck/Fort Ord
   are NOT confirmed every time anymore. They only fire when the
   narrator self-corrects OR volunteers an uncertainty marker ("I
   may not have that right" / "something like" / "the way it comes
   back to me"). Foreign + record-critical names (Landstuhl /
   Ramstein / Kaiserslautern / Schmick / 32nd Brigade / Lansdale /
   Selfridge / Salamander / Oslo / Trondheim) still fire on first
   appearance — those are the ones the memoir needs locked.

2. **Hardcoded UUID renamed** to `_EMERGENCY_ENGLISH_LOCK_PERSON_IDS`
   with a removal-criteria docstring. The constant is a safety belt
   for Kent's morning session, not the product design — that's
   profile-based `session_language_mode`. Once the operator UI for
   pinning is wired into Bug Panel and Kent + Janice each have a
   profile pin verified across a full session, this constant should
   be deleted.

3. **Pre-commit + replay-before-Kent gate** — see commit blocks below.

## Pre-commit verification (run BEFORE the commit blocks)

```bash
cd /mnt/c/Users/chris/hornelore

# Pure-stdlib unit tests — must be 100% green before committing.
python3 -m unittest \
  tests.test_lori_followup_bank \
  tests.test_lori_witness_mode \
  tests.test_lori_session_language_contract \
  tests.test_lori_meta_question

# Byte-compile every touched module so any import error surfaces
# before the stack tries to load it.
python3 -m py_compile \
  server/code/api/services/lori_followup_bank.py \
  server/code/api/services/lori_witness_mode.py \
  server/code/api/routers/chat_ws.py \
  server/code/api/routers/operator_followup_bank.py \
  server/code/api/prompt_composer.py \
  server/code/api/db.py \
  server/code/api/main.py \
  scripts/set_session_language_mode.py
echo "Pre-commit verification: PASS"
```

If either step fails, do not commit. Paste the failure and I'll fix.

## Commit blocks for /mnt/c/Users/chris/hornelore

Run these in order. Three commits split: code, tests + docs.

```bash
cd /mnt/c/Users/chris/hornelore
git status
git diff --stat
```

```bash
git add server/code/db/migrations/0007_follow_up_bank.sql \
        server/code/api/db.py \
        server/code/api/services/lori_followup_bank.py \
        server/code/api/services/lori_witness_mode.py \
        server/code/api/prompt_composer.py \
        server/code/api/routers/chat_ws.py \
        server/code/api/routers/operator_followup_bank.py \
        server/code/api/main.py
git commit -m "$(cat <<'EOF'
WO-LORI-WITNESS-FOLLOWUP-BANK-01 — patience layer

Each turn opens new doors. Lori receives the chapter, opens ONE
door if it is clearly the next door, and BANKS the rest. After a
chapter is told, Lori goes to the bank for unanswered followups
at natural pauses.

Architecture:

  - Migration 0007 + db.py accessors: follow_up_bank table with
    BankedQuestion schema (id, session_id, person_id, intent,
    question_en, triggering_anchor, why_it_matters, priority 1-6,
    triggering_turn_index, asked_at_turn, answered, timestamps).
    De-dupes per (session, intent, anchor); priority 1=fragile
    name, 2=communication/logistics, 3=role transition, 4=
    relationship, 5=daily-life, 6=medical/family.

  - services/lori_followup_bank.py: pure-stdlib door detector +
    selector + flush triggers + flush composer. Six priority
    levels with detector functions per the locked hierarchy.
    select_immediate_and_bank() picks priority 1-3 only for
    immediate ask; 4-6 always bank.

  - chat_ws.py routing:
      * Floor-hold short-circuit (TEST-A) — "Take your time."
      * Lang-contract resolution + Kent UUID hardcoded english lock
      * Bank-flush short-circuit BEFORE LLM dispatch — fires on
        narrator-cued ("what else"), short-answer-no-door,
        floor-released directive, operator-click directive, or
        chapter-summary mode. Emits "I want to come back to one
        detail you mentioned earlier. {Q}" deterministically.
      * STRUCTURED_NARRATIVE branch: detect doors, pick immediate,
        bank rest. Validator-fallback uses compose_structured_
        witness_receipt with immediate door's question_en threaded
        in.
      * Post-LLM Spanish-scaffolding repair guard for english-
        locked sessions.
      * Bank-write: persist doors_to_bank to DB after WS done.

  - witness_mode split: compose_chronological_chain_receipt()
    (receipt only, no question) + compose_structured_witness_
    receipt() with optional immediate_door_question kwarg. Legacy
    intent bank kept as fallback when no door supplied.

  - prompt_composer: _build_profile_seed surfaces session_language
    _mode / primary_language / allow_code_switching with operator
    alias normalization.

  - operator_followup_bank router: GET /unanswered, /all,
    /summary; POST /mark-answered. Gated HORNELORE_OPERATOR_
    FOLLOWUP_BANK=0 (404 when off).

Tests: 31 in tests/test_lori_followup_bank covering all 6
priority levels + selector + flush + composer. 87 in
tests/test_lori_witness_mode (carries forward). 183/183 across
all touched lanes.

Per Chris's locked design: "Each turn opens a new door. Lori can
bank follow-up questions. After a chapter is told, Lori goes to
the bank for unanswered followups as part of her active listener
skills." Immediate response = receipt + one door. Bank = all
other unresolved doors. Bank flush = later, one at a time, when
narrator has space.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git status
```

```bash
git add tests/test_lori_followup_bank.py \
        tests/test_lori_session_language_contract.py \
        scripts/set_session_language_mode.py \
        docs/reports/KENT_TRANSCRIPT_STUDY_2026-05-10.md \
        MORNING_HANDOFF_2026-05-10.md \
        .env.example
git commit -m "$(cat <<'EOF'
WO-LORI-WITNESS-FOLLOWUP-BANK-01 + lang-contract — tests + docs + ops

Tests:
  - test_lori_followup_bank: 31 tests, all 6 priority levels
    covered, selector + flush + composer locked. Kent TEST-G
    combined-narrative test asserts priority-1 fragile-name wins
    immediate AND priority-4 relationship door is in the bank.
  - test_lori_session_language_contract: 7 tests pinning the
    contract behavior and documenting the looks_spanish overfire
    cases that motivated the contract.

Operator script:
  - scripts/set_session_language_mode.py — pin a narrator's
    session_language_mode (english/spanish/mixed) in profile_json.
    --list / --batch-english / --person-id / --name / --primary /
    --code-switching. Tolerates narrators without a people row.

Documentation:
  - docs/reports/KENT_TRANSCRIPT_STUDY_2026-05-10.md — turn-by-
    turn study of Kent's deep-witness harness, with corrections
    for each turn ("what Lori actually did" vs "correct Lori")
    and banked follow-ups per turn. Source of truth for the
    intent bank patterns and door priority.
  - MORNING_HANDOFF_2026-05-10.md — review checklist + commit
    blocks + Kent army-at-18 readiness gate.

Env:
  - HORNELORE_OPERATOR_FOLLOWUP_BANK=0 documented in .env.example.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git status
```

After commits, push:

```bash
git log --oneline -8
git push
```

## REQUIRED replay gate before live Kent session

Per Chris's 2026-05-10 review: do NOT use this with Kent until the
deep-witness harness comes back clean against the 22:17 baseline.
Unit tests being green is necessary but NOT sufficient — the last
several iterations had unit-tests-green AND replay-still-failing.

After pull on the laptop, restart the stack (full ~4-min warmup),
then run:

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/replay_kent_deep_witness.py
```

**Required next-run expectations:**

- 0 Spanish / Spanglish in any reply (no Capté, no ¿Qué, no Tú,
  no comma-y mid-sentence)
- TEST-A floor-hold: PASS (≤7 word deterministic ack)
- TEST-COMMS-1959: Lori asks how Kent and Janice communicated
  (letters / phone / telegram) — `good_intents` must include
  `communication_with_wife` or equivalent
- TEST-G: asks Landstuhl OR Ramstein OR Schmick spelling
  confirmation
- TEST-F: stays good on missile → courier → photography
  transition (`good_intents` includes `role_transition` or
  `photography_work`)
- At least some `[chat_ws][followup-bank]` markers in
  `.runtime/logs/api.log` showing doors banked during the run

```bash
# Stream the new markers in a second terminal
tail -f /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | \
  grep -E '\[lang-contract\]|\[followup-bank\]|\[bank-flush\]|\[floor-hold\]|\[witness\]'
```

If those expectations clear, Kent is parent-presentable. If any
fail, paste the harness output + the grep output back to me. The
likely remaining gap is the door detector missing specific Kent
phrasing — that's a few-line patch to the intent patterns.

The Stanley/Fargo overfire from the prior architecture is fixed
(now requires uncertainty marker for Tier B names). The Spanish
contract is enforced at three layers (emergency UUID lock +
profile_json pin + post-output repair guard). The receipt + one
door + bank architecture is locked structurally.

DO NOT try with Kent before the replay gate clears.

## Pre-flight on the laptop after pull

The follow-up bank service runs unconditionally on every STRUCTURED_NARRATIVE turn — no env flag needed. Stack restart picks up the migration 0007 + db.py accessors automatically (init_db() applies pending migrations on startup).

The operator Bug Panel surface for the bank is gated. Enable it now so Layer 4 of the test plan can curl it:

```bash
cd /mnt/c/Users/chris/hornelore
grep -q "HORNELORE_OPERATOR_FOLLOWUP_BANK" .env || echo "HORNELORE_OPERATOR_FOLLOWUP_BANK=1" >> .env
```

Then bounce the stack. The operator endpoints become available at:
- `GET /api/operator/followup-bank/session/{session_id}/unanswered`
- `GET /api/operator/followup-bank/session/{session_id}/all`
- `GET /api/operator/followup-bank/summary`
- `POST /api/operator/followup-bank/mark-answered`

## Layer-by-layer test plan (run in order)

Don't go straight to Kent. Prove the mechanics, prove the replay, then short live trial with stop rules.

### Layer 1 — static / code tests before restart

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
```

**Expected**: 190/190 green. Zero py_compile errors.

This only proves the pieces load. It does NOT prove Kent-readiness.

### Layer 2 — restart stack, prove migration + language lock

After full restart (~4 min warmup), check the schema applied:

```bash
cd /mnt/c/Users/chris/hornelore
# Find the actual DB path from your stack — common locations:
ls -la data/hornelore.sqlite 2>/dev/null || \
ls -la .runtime/hornelore.sqlite 2>/dev/null || \
ls -la *.db 2>/dev/null
# Then once you know the path:
sqlite3 <path> ".schema follow_up_bank"
```

Expected: the `follow_up_bank` table from migration `0007_follow_up_bank.sql` with columns id / session_id / person_id / intent / question_en / triggering_anchor / why_it_matters / priority / triggering_turn_index / asked_at_turn / answered / created_at / updated_at, plus three indexes.

Then verify Kent's language pin (or set it if not present):

```bash
python3 scripts/set_session_language_mode.py --list
```

Look for the harness UUID `4aa0cc2b-1f27-433a-9152-203bb1f69a55` — it's hardcoded in chat_ws.py's `_EMERGENCY_ENGLISH_LOCK_PERSON_IDS` so you don't need to pin it manually. If you also want to pin it via profile_json (defense in depth):

```bash
python3 scripts/set_session_language_mode.py \
  --person-id 4aa0cc2b-1f27-433a-9152-203bb1f69a55 \
  --mode english --primary en --code-switching false
```

### Layer 3 — deep replay harness with logs open

Terminal 1 (logs):

```bash
cd /mnt/c/Users/chris/hornelore
tail -f .runtime/logs/api.log | \
  grep -E '\[lang-contract\]|\[followup-bank\]|\[bank-flush\]|\[floor-hold\]|\[witness\]'
```

Terminal 2 (harness):

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/replay_kent_deep_witness.py
```

**Hard gates** (all must pass before Layer 4):

1. ZERO Spanish / Spanglish in any reply: no Capté, no `¿Qué`, no `Tú` (capital T as Spanish pronoun), no comma-y mid-sentence inside English text.
2. TEST-A floor-hold: deterministic ack ≤7 words. One of: "Take your time." / "I'm listening." / "Keep going." No question. No LLM call (look for `[chat_ws][floor-hold]` log marker).
3. TEST-COMMS-1959: Lori either ASKS the Janice 1959 communication question immediately OR banks it (visible via `[followup-bank][to-bank] intents=communication_with_partner_overseas` log line).
4. TEST-G: Lori confirms Landstuhl / Ramstein / Schmick immediately (priority-1 fragile-name picks one for the immediate; the rest go to the bank). Watch for `[followup-bank][immediate] intent=fragile_name_confirm_*`.
5. TEST-F: Lori recognizes missile site → courier → 32nd Artillery Brigade → photography. `good_intents` should include `role_transition` or `photography_work`.
6. Logs show `[followup-bank] persisted N/M doors` lines — banks are filling.
7. Bank-flush works: at least one turn should produce `[chat_ws][bank-flush] reason=...` if the harness has any short-answer or "what else" turn.

### Layer 4 — inspect the bank, not just Lori's answer

After the replay, find the conv_id from the report (printed in stdout, also in `docs/reports/kent_deep_witness_*.md`):

```bash
cd /mnt/c/Users/chris/hornelore
ls -t docs/reports/kent_deep_witness_*.md | head -1
grep "conv_id" $(ls -t docs/reports/kent_deep_witness_*.md | head -1)
```

Then curl the operator bank endpoints (assuming `HORNELORE_OPERATOR_FOLLOWUP_BANK=1` is set in `.env` and stack restarted):

```bash
CONV_ID=$(grep "conv_id" $(ls -t docs/reports/kent_deep_witness_*.md | head -1) | head -1 | awk '{print $NF}' | tr -d '`')
echo "conv_id: $CONV_ID"

# All banked questions for this session (open + asked + answered)
curl -s "http://localhost:8000/api/operator/followup-bank/session/$CONV_ID/all" | python3 -m json.tool

# Just unanswered
curl -s "http://localhost:8000/api/operator/followup-bank/session/$CONV_ID/unanswered" | python3 -m json.tool

# Top-level summary across recent sessions
curl -s "http://localhost:8000/api/operator/followup-bank/summary" | python3 -m json.tool
```

**Expected bank items** from a clean Kent replay (pattern names, exact wording will vary):

- `communication_with_partner_overseas` — Janice 1959 communication
- `spouse_travel_paperwork` — how Janice got to Germany
- `role_pivot_photography` — what photography work involved
- `role_pivot_courier_bridge` — courier-to-photographer bridge
- `working_relationship_boss` OR `rank_asymmetry_relationship` — General Schmick personal relationship
- Multiple `fragile_name_confirm_*` for whichever names didn't win the immediate slot
- `medical_family_care` — only if narrator mentioned premature/CP

If the bank is empty after the replay, the door detector failed to fire OR the bank-write path raised. Check api.log for `[chat_ws][followup-bank]` lines.

### Tiny live Kent trial (only after Layers 1-4 clear)

10 minutes max. One chapter only. Goal: prove listen + one door + bank rest + return later.

Ask Kent only this:

> "When you left Stanley for the Army and went through Fargo induction, what happened?"

Let him talk uninterrupted. Watch the log stream in Terminal 1.

**What Lori should do (immediate response)**:

> "You went from Stanley to Fargo for induction, took the physical and mental tests, scored high enough to be trusted with meal tickets, and had responsibility before basic training. What happened when you reached Fort Ord?"

**What should be in the bank** (visible via curl):

- `What was the Fargo physical and mental exam process like?`
- `How did the meal-ticket responsibility work?`
- `What happened with the conductor and the meals?`

Then say to Kent:

> "Yeah, that's right."

(Or you can speak it through the UI if mic is on; the short-answer-no-door trigger fires the bank flush.)

**Expected Lori (bank flush)**:

> "I want to come back to one detail you mentioned earlier. What was the Fargo physical and mental exam process like?"

This is the patience-layer success condition: Lori heard the chapter, didn't jam everything into one turn, and circled back later.

### Stop rules — abort the live trial immediately if Lori does any of these

- Spanish or Spanglish anywhere in the reply
- Asks about scenery, sights, sounds, smells, camaraderie, teamwork
- Asks "how did that feel" / "what was that like" when Kent is giving facts
- Speaks AS Kent: "we were", "our son", "my wife", "I went"
- Asks more than one question per turn
- Bank-flush interrupts while Kent is still telling the chapter (priority-1-3 door should win the immediate over flush — if flush fires anyway, that's a routing bug)
- Confirms common American place names ("did I get Stanley right?") without Kent first signaling uncertainty

Stop, screenshot the api.log + transcript, paste back. The likely fix will be a few-line patch to the door detector or the flush trigger.

## Try with Kent — army-at-18 chapter

Kent picking up where TEST-COMBINED ended. Expected behavior in the new architecture:

When Kent says (chapter on basic training at age 18):

> "I went down to the railroad depot in Stanley with my dad. From Stanley I went by train to Fargo for the induction process. They put us through the physical exam, the mental exam, and qualifying tests. I scored high enough that the Army put me in charge of meal tickets for a trainload of recruits going west."

Lori should:
1. **Receipt** — "You went from the Stanley depot to Fargo for induction, scored high enough to be trusted with the meal tickets for the train west."
2. **One door (priority 1 fragile-name confirm)** — "Did I get Stanley and Fargo right?" OR if no fragile-name issue, the next priority — induction-journey door from intent bank.
3. **Bank** — silently writes:
   - "What was the Fargo physical/mental exam process like?" (priority 3 — career-choice mechanism, banked because immediate already won)
   - Other doors that surface

If Kent then says, "Yeah that's right" (short answer, no door):
- **Bank-flush triggers** because short-answer-no-door
- Lori emits: "I want to come back to one detail you mentioned earlier. What was the Fargo physical and mental exam process like?"

If Kent says, "What else would you like to know?":
- **Bank-flush triggers** on narrator-cued
- Same flush phrase, next banked question

## What to watch for in api.log during the Kent session

```bash
tail -f /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | grep -E '\[lang-contract\]|\[followup-bank\]|\[bank-flush\]|\[floor-hold\]|\[witness\]'
```

Expected markers per Kent turn:

- `[chat_ws][lang-contract] HARDCODED english conv=...` (Kent UUID locked english)
- `[chat_ws][witness][deterministic] type=STRUCTURED_NARRATIVE ... lang=en`
- `[chat_ws][followup-bank][immediate] intent=... priority=N anchor=...` (door picked for this turn)
- `[chat_ws][followup-bank][to-bank] n=N intents=...` (doors banking)
- `[followup-bank] added id=... session=... intent=... priority=N` (DB write)
- `[chat_ws][witness][llm-receipt] validator PASS` OR `validator FAIL ... fallback ...`
- `[chat_ws][followup-bank] persisted N/M doors`

When Kent gives a short answer:
- `[chat_ws][bank-flush] reason=short_answer_no_door:5w intent=... priority=N`

When Kent says "what else":
- `[chat_ws][bank-flush] reason=narrator_cued`

ZERO `[chat_ws][lang-contract][es-repair]` markers during Kent session (would indicate Spanish leaked through and got repaired — present but should not fire on english-locked narrator).

## What to do if something breaks

- **Kent gets Spanish/Spanglish anywhere**: the hardcoded UUID lock didn't take. Check:
  ```bash
  grep "_HARDCODED_ENGLISH_PERSON_IDS" /mnt/c/Users/chris/hornelore/server/code/api/routers/chat_ws.py
  ```
  Confirm `4aa0cc2b-1f27-433a-9152-203bb1f69a55` is in the frozenset. The actual narrator UUID Kent uses for the morning session may differ — add it to the constant if needed:
  ```bash
  python3 -c "
  import sys; sys.path.insert(0, 'server')
  from code.api import db; db.init_db()
  con = db._connect()
  for r in con.execute('SELECT id, display_name FROM people WHERE display_name LIKE \"%Kent%\";'):
      print(r)
  con.close()
  "
  ```
  Then add the actual UUID to `_HARDCODED_ENGLISH_PERSON_IDS` in chat_ws.py.

- **Bank not writing**: check api.log for `[followup-bank]` lines. If absent, the migration didn't apply — check init_db logs at stack startup.

- **Bank-flush firing too aggressively**: the `should_flush_bank` rules are conservative by default. If Lori interrupts with "I want to come back to..." too often, increase the short-answer floor (currently <8 words triggers).

- **Bank-flush never firing**: check that doors ARE being banked (`[followup-bank] persisted N` log) and that some are unanswered. Operator Bug Panel `/api/operator/followup-bank/session/{conv_id}/unanswered` shows the open queue.

## Open work (next session, after morning Kent)

These are NOT done — gates for next iteration:

1. **Door detector for Janice's later-years** — current pattern set is Kent-Army-heavy. Janice's narrative will hit different intent patterns (homemaking, raising children, family traditions, post-Kent life).

2. **Harness rewrite** — the existing `replay_kent_deep_witness.py` scores immediate-quality only. New harness should score immediate AND bank quality separately per ChatGPT's spec:
   - Immediate quality: did Lori reflect the chain? at-most-one-question? avoided interrupting?
   - Bank quality: did Lori bank communication-with-Janice? travel/paperwork? Schmick relationship? photography work? Landstuhl/Ramstein confirmation if not asked immediately?

3. **Bug Panel JS for the bank** — the operator HTTP endpoints are live but no Bug Panel UI yet. Pattern after `bug-panel-eval.js` / `bug-panel-story-review.js`. Render: per-session bank, badges (intent, priority, asked/answered), one-click "ask now" / "mark answered" / "discard."

4. **Bank-flush metronome experiment (deferred)** — Chris's locked rule is conservative ("not every Nth turn"). If after live trial the patience layer feels too quiet, consider a soft chapter-end detector (silence + last-turn-was-a-summary signals).

5. **Janice/Mary/Marvin language pins** — when those operator narrators get instantiated, append their UUIDs to `_HARDCODED_ENGLISH_PERSON_IDS` OR run `scripts/set_session_language_mode.py --batch-english <names>` once they exist in the people table.

## Bottom line

Kent's morning session is parent-presentable on the architecture side:
- english-locked, no Spanish drift possible
- floor-hold deterministic
- structured chapters get receipt + ONE door (priority 1-3)
- relationship + daily-life + medical doors silently bank
- short answers / "what else" cues flush the bank one question at a time
- bank persistence survives stack restart

The army-at-18 chapter should produce visibly better Lori behavior than the 22:17 harness run. The next failure mode (if any) will be that the door detector misses some specific Kent phrasing — not the architecture itself.

Push, pull on the laptop, restart the stack, click "Start Narrator Session" with Kent, and let him talk about the depot in Stanley. Watch for `[followup-bank][immediate]` and `[followup-bank][to-bank]` lines as he goes. The bank will accumulate; when he pauses, Lori will circle back.

Let him keep the floor.
