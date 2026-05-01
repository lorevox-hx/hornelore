# Handoff — 2026-05-01 EOD → 2026-05-02 morning

## What landed today

### Banked

1. **WO-LORI-SOFTENED-RESPONSE-01** (overnight build, 2026-05-01 morning)
   - Two commits: code + docs
   - 238 → 240 unit tests pass
   - DB lock delta=0 across the harness

2. **Step-1 + step-2 cleanup pass** (regex tighten + harness assertion + composer rules)
   - Tightened `_SAFETY_ACKNOWLEDGMENT_RX` to acute-resource tokens only
   - Added `expect_softened_mode_only` field on harness TestTurn
   - Added CONTROL-YIELD + NO-FORK rules to LORI_INTERVIEW_DISCIPLINE
   - 240/240 tests pass after this commit

3. **Gate #6 verify run** (`golfball-softened-on-v2.json` banked)
   - **Gate #6 closed RED → GREEN.** Post-safety recovery mechanism verified.
   - DB lock delta = 0
   - Turn 06 acute / Turn 07-08 softened-mode wrapper-side flags all working
   - Surfaced 3 follow-up findings (composer-side, not safety-mode failures)

### NOT yet banked — uncommitted in tree at EOD

**Step-3 patch bundle** (push-after-resistance + softened-mode-aware wrapper + harness Phelan rollup). This is the (a) work from your "a b then c" sequence.

Files modified, AST clean, 240 → 248 tests pass:

```
server/code/api/services/lori_communication_control.py
  - softened_mode_active param threaded through enforce_lori_communication_control + _safety_path
  - normal_interview_question_during_safety check skips when softened_mode_active=True
  - _RESISTANCE_RX (no bare "I don't know")
  - _PROBE_RX (no bare ?$)
  - _detect_push_after_resistance function
  - Wired into Step 5 of wrapper (non-safety path)

server/code/api/routers/chat_ws.py
  - Passes softened_mode_active=_softened_now to wrapper

scripts/archive/run_golfball_interview_eval.py
  - Passes softened_mode_active=bool(turn.expect_softened_mode_only) to wrapper
  - _OR_QUESTION_RX = re.compile(r"\bor\b[^.?!]*\?", re.IGNORECASE)  (correct order)
  - _CONTROL_FAILURE_LABELS set
  - _phelan_failures_for_turn / _has_control_failure / build_phelan_rollup / print_phelan_rollup
  - phelan_rollup field on HarnessReport dataclass
  - Wired into report builder + console summary

tests/test_lori_softened_response.py
  - 9 new tests:
    * test_softened_mode_active_skips_normal_question_check
    * test_softened_mode_active_false_acute_path_still_fires_normal_q
    * PushAfterResistanceTests: 6 tests covering off-ramp / no-resistance / bare-don't-know / safety-skip
```

**248/248 tests pass. AST clean across 4 files.**

Suggested commit (single code commit, no docs touched in this round):

```bash
cd /mnt/c/Users/chris/hornelore

git add server/code/api/services/lori_communication_control.py
git add server/code/api/routers/chat_ws.py
git add scripts/archive/run_golfball_interview_eval.py
git add tests/test_lori_softened_response.py
git add docs/reports/HANDOFF_2026-05-02_morning.md

git status --short

git commit -m "$(cat <<'EOF'
feat(lori): step-3 cleanup — wrapper softened-mode aware + push-after-resistance + harness Phelan rollup

Three patches from "a b then c" sequence step (a):

1. WRAPPER SOFTENED-MODE AWARE — lori_communication_control.py
   New softened_mode_active param threaded through enforce_lori_communication_control
   to _safety_path. Normal-interview-question check (wh-word + '?') is
   skipped when softened_mode_active=True. Composer prompt + softened
   cap own discipline in softened mode; gentle invitations like
   "Would you like to talk?" are legitimate. Acute path (softened_mode_
   active=False) preserves original behavior.

   chat_ws.py passes softened_mode_active=_softened_now (separated from
   _acute_now in the existing _safety_triggered_now block).

   Harness passes softened_mode_active=bool(turn.expect_softened_mode_only).

2. PUSH-AFTER-RESISTANCE DETECTOR — Phelan SIN 3 (too much arguing)
   Single-turn detection: narrator-side resistance phrase + Lori-side
   probe verb in same turn. Wired into Step 5 of wrapper (non-safety path).

   _RESISTANCE_RX includes "I don't remember", "not really", "I'm not
   sure", "I don't want to talk about", "let's not", "no thanks", and
   six related phrases. Bare "I don't know" intentionally NOT in the
   list (too conversational, would over-fire).

   _PROBE_RX includes strong probe verbs (can you tell me, tell me more,
   what was it like, do you remember, etc.). Bare "?$" alternative
   intentionally NOT included so legitimate off-ramps like "Would you
   like to try a different memory?" don't get falsely flagged.

   Single-turn only by design — sequence-level escalation patterns
   (resistance → probe → resistance → probe) live in the harness rollup.

3. HARNESS PHELAN ROLLUP — Four Cardinal Sins lens on existing signals.
   Does NOT add new detection — rolls up atomicity / reflection /
   comm_control failures into Talking / Emotion / Arguing / Control
   buckets. Phelan is interpretive layer; detection is the wrapper.

   Sequence detection: 3+ consecutive turns with any of (missing_memory_
   echo, echo_not_grounded, push_after_resistance, normal_interview_
   question_during_safety) flag a control_yield_sequence_failure. Plus
   a narrower missing_memory_echo-only counter for diagnostic clarity.

   _OR_QUESTION_RX correct order: \\bor\\b[^.?!]*\\? (or first, then
   '?'). Catches "Would you like X, or Y?" — not the inverse.

VERIFICATION
  python3 -m py_compile server/code/api/services/lori_communication_control.py \\
                        server/code/api/routers/chat_ws.py \\
                        scripts/archive/run_golfball_interview_eval.py \\
                        tests/test_lori_softened_response.py
  → AST CLEAN

  python3 -m unittest tests.test_story_trigger \\
                      tests.test_story_preservation \\
                      tests.test_story_preservation_isolation \\
                      tests.test_age_arithmetic \\
                      tests.test_question_atomicity \\
                      tests.test_question_atomicity_isolation \\
                      tests.test_lori_reflection \\
                      tests.test_lori_reflection_isolation \\
                      tests.test_lori_communication_control \\
                      tests.test_lori_communication_control_isolation \\
                      tests.test_lori_softened_response \\
                      tests.test_lori_softened_response_isolation
  → 248/248 OK

Server-side changes (wrapper + chat_ws) require stack restart.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Live-test findings (afternoon, before EOD)

Live-tested Janice (questionnaire_first) and Kent. Audit + memoir export uploaded.
Findings categorized below. Ranked by parent-session readiness impact.

### 🔴 BLOCKER — truth-pipeline pollution on Janice

`lorevox_memoir_janice_structured.txt` shows two protected-identity fields polluted:

```
- Janice Josephine Horne, known as Janice. Born August 30, 1939 in My dad worked nights at the aluminum plant..
- Birth order: I just told you something you ignored.
```

- `personal.placeOfBirth` = "My dad worked nights at the aluminum plant.."  (should be "Spokane, Washington")
- `personal.birthOrder` = "I just told you something you ignored."  (resistance text leaked into truth)

**This is exactly the BUG-EX-PLACE-LASTNAME-01 / BUG-311 / BUG-312 class.** Type C binding hallucination per Architecture Spec v1 §7.1. Both fields ARE in the BUG-312 protected_identity gate's covered list (fullName / dateOfBirth / placeOfBirth / preferredName / birthOrder). So either:

  a) The protected_identity gate isn't catching the questionnaire_first walk's writes (might be coming through as a "trusted source" the gate considers valid)
  b) BUG-312's gate is bypassed when the user-flow actually walks identity onboarding
  c) An upstream extraction wrote before the gate could check

**Action**: trace which source signature wrote these two fields. Need transcript-side data to know whether the writes came via `human_edit`, `preload`, `profile_hydrate`, or unsigned chat extraction. The first three should be trusted — but the values look like LLM/extractor hallucinations from prior chat context, not user-typed answers. So source signature is suspect.

This is a parent-session blocker. Must be diagnosed before Janice/Kent live sessions.

**Tracker**: file as `BUG-326: protected_identity gate bypass during questionnaire_first walk on Janice`.

### 🟡 UI / UX bugs — Narrator Room

| # | Bug | Severity | Note |
|---|-----|----------|------|
| 1 | Life Map didn't render initially in questionnaire_first; appeared after switch to clear_direct and back | Medium | Race / one-shot init issue. Life Map should render on first load regardless of session_style. |
| 2 | Today button locks green; clicking other Life Map eras after Today does nothing | Medium | UI state not clearing properly. |
| 3 | Lori responds to "what day is it" with "I'm in a conversation mode that doesn't allow me to keep track of the current date" | Medium | Hallucinated capability constraint. She CAN tell the date — it's `Today: <date>` in the system prompt context. |
| 4 | Peek at Memoir Earliest Years in-app shows polluted data, but TXT export shows cleaner placeholders ("(no entries yet)") | High | In-app peek and export disagree. One pulls from polluted truth, other from a cleaner source. |
| 5 | Peek at Memoir cuts off content (Earliest Years gets truncated "ecord yet) - Date of...") | Medium | Render overflow. |
| 6 | Peek at Memoir button is too bright — eye magnet, distracting | Low | Reduce size + match theme color. |
| 7 | Take a Break button is orange while Lori is speaking, can't be clicked | Medium | Should be gated until Lori finishes. |
| 8 | Take a Break gives narrator a "Return to Operator" option | High | Narrators should not see operator-return — only Resume. |
| 9 | Resume after Take a Break: Lori is silent | Medium | Should say "Welcome back, Kent. Ready to continue?" |
| 10 | Two Pause buttons / two Resume buttons in the UI | Medium | Cleanup needed. |

### 🟡 Lori behavior bugs

| # | Bug | Note |
|---|-----|------|
| 1 | Kent's first turn includes both standard 3-anchor request AND "Take your time" | Pre-existing intro disjointed. |
| 2 | After "what day is it", Lori pivots back to story instead of acknowledging the question or the date | Composer prompt should: (a) answer direct narrator questions first, (b) include current date in runtime context. |
| 3 | After clicking Early School Years and waiting, Lori said "Let's take a step back and revisit the story you were sharing about your family's life in Spokane during the war." | Era-click → topic-shift wiring issue. Lori should acknowledge era context shift. |

### 🟢 Design questions / proposals from Chris

1. **Session styles consolidation.** Currently 4 modes: questionnaire_first / clear_direct / warm_storytelling / companion. Chris asks: do they all actually work? Proposes 3 modes:
   - **The Interview** = questionnaire_first (formal data collection)
   - **The Conversation** = clear_direct + warm_storytelling combined (storytelling middle path)
   - **Companion** = passive right-side mode

   Worth auditing: how distinct is each style's actual output? The harness style_diff_checks already measure this. Run those numbers + decide.

2. **Audit Panel name** ("what should I call the panel"). Options:
   - **Session Audit** (factual, operator-side)
   - **Run Report** (matches eval-language)
   - **Health Check** (matches health probes)
   - **Pre-flight** (aviation metaphor, fits parent-session blocker readiness)
   - **Readiness Report** (matches the "parent-session readiness gates" frame)

   My pick: **Run Report** — matches the eval-side vocabulary you already use, signals "this is a snapshot not a persistent surface", neutral.

3. **Today button** — replace with active clock widget (current date/time from computer) below Peek at Memoir. Clean, narrator-visible, no Lori-introspection needed.

4. **UI layout cleanup** (per Chris's spec):
   - Remove Resume + Take a Break from between "Camera on" and "Save my voice"
   - Remove Resume from next to Send
   - Move modified Take a Break next to Mic icon (lower left)
   - Lori acknowledges narrator return on Resume with "Welcome back, <name>. Ready to continue?"

### Operator panel question

Chris asks: "Didn't we work on a new operator panel and gauges? Are we not current with that?"

**Yes.** WO-OPERATOR-DASHBOARD-MERGE-01 unified cockpit was banked 2026-04-30 (CLAUDE.md changelog #340). It includes:
- stack_monitor.py backend
- operator_stack_dashboard.py router (HORNELORE_OPERATOR_STACK_DASHBOARD=0 default-off)
- Bug Panel dashboard frontend (JS + CSS + HTML mount)
- UI heartbeat for camera/mic state

**Today's operator log shows the dashboard endpoint is 404** (`operator_stack: status=404`) — so the env flag isn't on, OR the router didn't get included in main.py. Worth checking.

Operator log also shows:
- `operator_safety: 404` — same flag-off / not-mounted concern
- `operator_eval_harness: 404` — same
- `Media launcher cards present (3) — count=4` — RED, asserted-count mismatch, harness expected 3 found 4

These need an env review:
```bash
grep -E "OPERATOR_(SAFETY_EVENTS|STACK_DASHBOARD|EVAL_HARNESS|STORY_REVIEW|DB_INSPECTOR)" .env
```

If any are 0 and you want them visible, flip + restart.

---

## Parent-session readiness state (after today)

| Gate | State | Notes |
|------|-------|-------|
| 1. DB lock | 🟢 GREEN | held across multiple harness runs today |
| 2. Atomicity discipline | 🟢 GREEN | wrapper enforced |
| 3. Story preservation | 🟢 GREEN | 1 row landed live |
| 4. Safety acute path | 🟢 GREEN | Turn 06 verified |
| 5. Safety soft-trigger | 🔴 RED | needs SAFETY-INTEGRATION-01 Phase 2 |
| 6. **Post-safety recovery** | 🟢 **GREEN** ← closed today | softened-mode persistence verified end-to-end |
| 7. Truth-pipeline writes | 🔴 **RED — confirmed live** | Janice memoir shows protected_identity bypass; BUG-326 |

Net: **gate 6 closed today**, but **gate 7 was confirmed broken in live test** — the BUG-EX class hit Janice in production. Truth-pipeline lane (TRUTH-PIPELINE-01 Phase 1 observability) is now top priority among parent-session blockers, ahead of gate 5.

---

## Morning priorities (suggested)

1. **Bank the step-3 patches** (commit block above).
2. **Restart stack + verify** today's patches don't regress: re-run golfball harness with `HORNELORE_SOFTENED_RESPONSE=1`. Expect 248-test green stays green; expect Phelan rollup section in console output; expect Turn 07/08 wrapper-side `normal_interview_question_during_safety` no longer fires.
3. **File BUG-326** — protected_identity bypass on Janice. Investigation: trace source signature on placeOfBirth + birthOrder writes from today's session. Use the archive ZIP as evidence.
4. **Decide UI cleanup priority** vs. extractor lane — Janice-pollution is the bigger blocker; UI cleanup (10 items) can run parallel via a single WO-UI-NARRATOR-ROOM-CLEANUP-01.
5. **Operator dashboard env review** — flag-off audit, decide which to enable for the upcoming operator-side parent-session.

---

## Files referenced in this handoff

- `docs/reports/golfball-softened-on-v2.json` (banked) — gate #6 verify
- `docs/reports/RESEARCH_REFERENCES_2026-05-01.md` (banked) — research reference list
- Uploads from today (in `mnt/uploads/`):
  - `OPERATOR-LOG-2026-05-01-14-47-49.md`
  - `hornelore_archive_4aa0cc2b_2026-05-01-14-47-49.zip`
  - `lorevox_memoir_janice_structured.txt`

Today's archive (Kent session start) and Janice memoir export are evidence for BUG-326. Worth keeping — copy them into `docs/evidence/2026-05-01/` if you want them preserved alongside the bug investigation.
