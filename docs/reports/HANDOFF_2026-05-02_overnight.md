# Overnight handoff — 2026-05-01 → 2026-05-02

## What landed (uncommitted in tree, ready for morning bank)

**WO-LORI-SOFTENED-RESPONSE-01** — Lane C from yesterday's plan. Closes
parent-session readiness gate #6 (post-safety recovery). Built end-to-end:
spec, pure module, composer integration, chat_ws wire-up, wrapper
softened-mode word-cap, safety_events `/softened-state` endpoint, Bug
Panel banner (JS + CSS + HTML mount), harness Turn 08, full unit-test
suite + LAW-3 isolation gate.

5 design decisions locked exactly as Chris specified:
1. Softened window: 3 turns
2. Echo / presence first; one gentle invitation allowed
3. No auto-clear — full 3 turns
4. Bug Panel banner: yes
5. `HORNELORE_SOFTENED_RESPONSE=0` default-off

## Files touched (uncommitted)

```
NEW:
  WO-LORI-SOFTENED-RESPONSE-01_Spec.md
  server/code/api/services/lori_softened_response.py
  ui/js/bug-panel-softened-banner.js
  ui/css/bug-panel-softened-banner.css
  tests/test_lori_softened_response.py
  tests/test_lori_softened_response_isolation.py
  docs/reports/HANDOFF_2026-05-02_overnight.md  (this)

MODIFIED:
  server/code/api/services/lori_communication_control.py
    (safety-path softened-mode word-cap with acute-bypass via 988 ack)
  server/code/api/prompt_composer.py
    (SOFTENED MODE directive injection from runtime71["softened_state"])
  server/code/api/routers/chat_ws.py
    (per-turn turn_count increment, softened-state read,
     runtime71 thread-through, wrapper-side acute-or-softened gate,
     defensive _safety_result init for empty-user_text turns,
     env-flag-gated softened state read)
  server/code/api/routers/safety_events.py
    (GET /api/operator/safety-events/softened-state?conv_id=X)
  scripts/archive/run_golfball_interview_eval.py
    (Turn 08 added — softened-mode persistence verification)
  tests/test_lori_communication_control_isolation.py
    (allow lori_softened_response as a valid sibling import)
  ui/hornelore1.0.html
    (CSS + JS script tags for the softened banner)
  .env.example
    (HORNELORE_SOFTENED_RESPONSE flag with documentation)
```

## Verification

```
python3 -m py_compile server/code/api/services/lori_softened_response.py \
                      server/code/api/services/lori_communication_control.py \
                      server/code/api/prompt_composer.py \
                      server/code/api/routers/chat_ws.py \
                      server/code/api/routers/safety_events.py \
                      scripts/archive/run_golfball_interview_eval.py
→ AST CLEAN

python3 -m unittest tests.test_story_trigger \
                    tests.test_story_preservation \
                    tests.test_story_preservation_isolation \
                    tests.test_age_arithmetic \
                    tests.test_question_atomicity \
                    tests.test_question_atomicity_isolation \
                    tests.test_lori_reflection \
                    tests.test_lori_reflection_isolation \
                    tests.test_lori_communication_control \
                    tests.test_lori_communication_control_isolation \
                    tests.test_lori_softened_response \
                    tests.test_lori_softened_response_isolation
→ 238/238 OK
```

## Code-review findings (all fixed during the night)

Re-read every change in dependency order looking for bugs. Three
findings, all fixed:

### Bug 1 — `_safety_result` undefined when user_text is empty (PRE-EXISTING)

**Fixed.** chat_ws's safety scan only ran inside `if user_text and
user_text.strip():`. Empty user_text would never bind `_safety_result`,
then later the wrapper call `bool(_safety_result and ...)` would
NameError. This was a pre-existing latent bug surfaced during the
review. Defensive `_safety_result = None` initialization landed
upstream of the safety scan block.

### Bug 2 — Wrapper-side softened gate didn't match composer-side env gate

**Fixed.** Composer-side softened directive injection was env-gated
behind `HORNELORE_SOFTENED_RESPONSE`. Wrapper-side `_softened_state`
read was NOT — meaning if Chris turned the flag off but the DB had
leftover softened state, the composer would ignore it but the wrapper
would still see `safety_triggered=True`. Mismatched gate. Fixed by
moving the env check upstream so the DB read itself is gated, single
source of truth, both layers agree.

### Bug 3 — `softened_response_too_long` would falsely fire on acute

**Fixed.** The 35-word softened cap I added to the wrapper's safety
path would trip on legitimate acute responses (which run 40-60 words
including 988 phrasing). Distinguished by the existing
`_SAFETY_ACKNOWLEDGMENT_RX` (988 / "I'm so sorry" / "are you safe"
etc.). When `has_safety_ack=True`, the response is acute and the
softened cap is skipped. When `has_safety_ack=False` AND
`safety_triggered=True`, it's softened mode and the cap fires.
Test `test_wrapper_safety_path_long_acute_response_passes` verifies.

## Robustness sweep (Chris's STT-fragility checklist)

Probed every new module against narrator-input edge cases (lowercase
STT, dropped punctuation, word-finding fragments, generic-vs-proper
noun pairs, empty input, number-vs-word format mismatch). Findings:

- Atomicity is robust to all STT variations — its inputs are Lori
  output not narrator input
- Reflection grounding handles number-vs-words mismatch correctly
  (digits filtered out by `[a-zA-Z]` token regex; both directions
  carry overlap via remaining content tokens)
- Single-word narrator answers correctly trigger grounding-skip
  (`< 5 content tokens` check)
- Word-finding fragments / fillers tokenize cleanly (filler tokens
  hit stopwords; remaining content stays >= overlap threshold)
- Acute SAFETY responses (50+ words with 988) correctly bypass the
  softened-length cap (Bug 3 above)
- Softened responses (50+ words, no 988) correctly trip the cap
- Empty / whitespace / punctuation-only inputs all return atomicity
  failures: [] (correct — no false fires)

One follow-up note for REFLECTION-01 v2 (NOT a blocker): if Lori
echoes a number-spelling change ("1939" → "nineteen thirty nine" or
vice versa), the grounding check uses `[born, ...]` overlap and
handles it correctly — but the digit-vs-word distinction itself is
filtered out, not aligned. If we ever want to score that alignment,
we'd need a number-normalization pre-pass. Not parent-session
blocking.

## What this opens — Lane C verification

Chris's flow when he gets in:

1. Read this handoff
2. Skim git status — confirm tree matches the file inventory above
3. Bank the changes (single code commit + single docs commit
   following the CLAUDE.md hygiene rule). Suggested commit messages
   below.
4. Set `HORNELORE_SOFTENED_RESPONSE=1` in `.env`
5. Restart stack
6. Rerun the golfball harness

Expected on Turn 07 + Turn 08:

- Turn 07 (post-safety): `atomicity_failures: []` (no compound),
  `comm_control.failures: []` (no `normal_interview_question_during_safety`),
  Lori's response is presence-first, ≤35 words, no new memory probe
- Turn 08 (softened-persistence verification, narrator says "Thank
  you for being here with me."): still in softened mode,
  `comm_control.safety_triggered: true`, similar shape to Turn 07
- Turn 09 (would auto-clear softened — not tested by harness, the
  3-turn window is exhausted)
- DB locks delta still 0
- Master extractor eval pass count unchanged

## Suggested commit blocks for morning

### Commit 1 — code

```bash
cd /mnt/c/Users/chris/hornelore
git add -u
git add server/code/api/services
git add tests
git add ui/js
git add ui/css
git add ui/hornelore1.0.html
git add scripts/archive
git add .env.example

# Unstage docs to keep code commit clean
git reset HEAD WO-LORI-SOFTENED-RESPONSE-01*
git reset HEAD docs/reports/HANDOFF_2026-05-02*

git status --short
```

### Commit 2 — docs

```bash
git add WO-LORI-SOFTENED-RESPONSE-01*
git add docs/reports/HANDOFF_2026-05-02*

git status --short
```

(Detailed commit messages can be drafted post-bank; the spec doc has
the full architecture write-up so the docs commit message can be
short.)

## Lane state after Lane C lands + verifies

Parent-session readiness gate states:

| Gate | Before tonight | After live verify of tonight's build |
|------|----------------|--------------------------------------|
| 1. DB lock | 🟢 GREEN | 🟢 GREEN |
| 2. Atomicity discipline | 🟢 GREEN | 🟢 GREEN |
| 3. Story preservation | 🟢 GREEN | 🟢 GREEN |
| 4. Safety acute path | 🟢 GREEN | 🟢 GREEN |
| 5. Safety soft-trigger | 🔴 RED | 🔴 RED (still — needs SAFETY-INTEGRATION-01 Phase 2 LLM classifier) |
| 6. **Post-safety recovery** | 🔴 RED | 🟢 GREEN (this WO closes it) |
| 7. Truth-pipeline writes | 🔴 RED | 🔴 RED (still — needs TRUTH-PIPELINE-01 Phase 1 observability) |

Remaining REDs after this bank: gate 5 (soft-trigger) + gate 7 (truth
pipeline). Both are independent lanes, not coupled to softened-mode.

## Notes for morning

- Tree is clean syntactically and 238/238 tests pass. AST clean across
  6 modified .py files.
- The HTML mount for the softened banner is wired (script + CSS link).
  Live verify in Chrome will confirm the banner renders when softened
  state is active — should appear inside `#lv10dBpSafetyBanners`'s
  next-sibling slot.
- The `/api/operator/safety-events/softened-state` endpoint is gated
  behind the existing `HORNELORE_OPERATOR_SAFETY_EVENTS=1` flag (same
  flag the safety-events list endpoint uses). If Chris wants the banner
  to render but doesn't want the rest of the operator safety surface,
  that's a separate gating decision (probably keep them coupled — same
  operator audience, same lane).
- The `HORNELORE_SOFTENED_RESPONSE=0` flag remains default-off. Flip
  to 1 in `.env` after the morning code-bank to enable the softened
  flow for the rerun.
