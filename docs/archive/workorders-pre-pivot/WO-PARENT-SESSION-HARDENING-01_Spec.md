# WO-PARENT-SESSION-HARDENING-01

**Session Review, Truth-Pipeline, Life Map, Today Mode, Break Controls, and Narrator Isolation**

Status: SCOPED · 2026-05-01

---

## Mission alignment

Per `CLAUDE.md`'s Mission section: "When a decision trades operational tidiness against narrator dignity, narrator dignity wins." This WO is a hard parent-session blocker. Until it lands, **no live narrator session with Kent or Janice may run**. The 2026-05-01 live test on Janice exposed real product bugs (truth-pipeline corruption, cross-narrator state leak, operator controls visible to narrator) that would directly compromise narrator dignity if they hit the parents.

## Why now

The 2026-05-01 live test surfaced:

1. Janice's memoir export carried polluted protected-identity fields:
   - `personal.placeOfBirth` = "My dad worked nights at the aluminum plant.."
   - `personal.birthOrder` = "I just told you something you ignored."
2. The Reset Identity flow does not actually reset all narrator-scoped state. Memoir cache, projection fields, runtime softened-mode/turn-count, and 5 permission flags survive narrator switch.
3. Take a Break exposes a "Return to Operator" button to the narrator.
4. Today mode is not wired — Lori claims she can't tell the date, even though `device_context` builds local date/time every turn.
5. Life Map fails to render on cold-start in `questionnaire_first` mode.
6. Life Map era buttons can become visually active but behaviorally dead (Today highlights green, then no other era responds).
7. Peek at Memoir cuts off content; in-app peek and TXT export disagree on data source.
8. Break / Pause / Resume controls duplicate (two of each) and the orange Take a Break button can't be clicked while Lori is speaking.

These are catalogued in:
- `docs/reports/BUG-326_TRACE_2026-05-01.md` (truth-pipeline trace)
- `docs/reports/UI_HUMAN_IN_THE_LOOP_AUDIT_2026-05-01.md` (10 issues across 7 surfaces)
- `docs/reports/HANDOFF_2026-05-02_morning.md` (consolidated handoff)
- Janice memoir evidence: `mnt/uploads/lorevox_memoir_janice_structured.txt`

## Hard rule

**Until every Phase 1–6 acceptance gate is GREEN, the operator panel must refuse to start a narrator session.** RED status from the Run Report (see Phase 9) is a hard block, not a warning.

## Vocabulary (locked)

To unify the operator-side surface naming:

- **Run Report** — the popup that opens after every session. Replaces the current "audit" / "operator log" terminology. Single label, single surface.
- **Session Audit** (tab inside Run Report) — health, transcript, mode switches, UI events, errors, RED/AMBER/PASS counts.
- **Review Queue** (tab inside Run Report) — facts/candidates waiting for approval, edit, or rejection. The legal path from AI suggestion to confirmed truth.
- **Evidence Card** (item inside Review Queue) — each individual proposed fact with source transcript excerpt, confidence score, and accept/reject/edit controls.

The button on the operator panel reads: **Open Run Report**.

---

## Phase 1 — P0: Truth-pipeline hardening (BUG-326)

**Block: parent session start.**

### 1.1 — `questionnaire_first` auto-save must validate before write

The smoking gun in `BUG-326_TRACE`: `_saveBBAnswer()` in `session-loop.js` writes directly to `PUT /api/bio-builder/questionnaire`, bypassing `projection-sync.js` and the BUG-312 protected-identity gate. If the narrator's response to "where were you born?" doesn't look like a place, the answer is saved verbatim.

Fix:
1. Route `_saveBBAnswer()` through `projection-sync.projectValue()` for protected-identity fields (`fullName`, `dateOfBirth`, `placeOfBirth`, `preferredName`, `birthOrder`). Use `source: "qf_walk_answer"` (a NEW non-trusted source).
2. Add a value-shape validator step before write. Reject and route to Review Queue (NOT to truth) if the value:
   - Contains second-person pronouns ("you", "your", "yours") — a clean signal of resistance/complaint text
   - Exceeds 80 chars for `placeOfBirth` / 30 chars for `birthOrder`
   - Contains past-tense narrative verbs ("worked", "said", "told", "ignored") — these don't appear in legitimate place-of-birth or birth-order answers
3. The new `qf_walk_answer` source is NOT trusted. The BUG-312 gate routes it to `suggest_only`. Operator approves through Review Queue.

### 1.2 — Hard reset narrator identity

The Reset Identity button currently clears Bio Builder fields and `state.profile.basics`, but leaves projection cache, memoir preview cache, runtime mode state, and localStorage keys intact.

Fix: a real `hardResetNarratorIdentity(person_id)` that clears everything in one operation:
- Bio Builder personal identity fields
- `state.profile.basics`
- `state.interviewProjection.fields` (all entries scoped to person_id)
- `state.bioBuilder.questionnaire`
- Cached memoir preview content (`state.memoirCache[person_id]` if it exists)
- Timeline spine cache
- localStorage keys matching `lorevox_*_<person_id>` and `bb_*_<person_id>`
- Backend person row: PATCH `/api/people/<id>` with `dob: null, birthplace: null, identity_complete: false`
- Any active chat/session labels for that narrator
- Runtime softened-mode + turn-count + safety state

Invocation: triggered by the existing Reset Identity button. Confirms intent via the existing dialog. Logs a `[reset-identity] hard-reset person=<pid>` line to `api.log`.

### 1.3 — Extend BUG-EX-PLACE-LASTNAME-01 deterministic guard

The 2026-04-29 guard in `extract.py` covers `.lastName` / `.maidenName` / `.middleName`. Extend coverage to `.placeOfBirth`:
- Drop candidates where the value contains past-tense narrative verbs and no place token
- Drop candidates where the value is longer than 80 chars

Add 6 new eval fixtures (`case_111–116`) covering the Janice failure mode (resistance phrases, prior-turn narrative pulled into placeOfBirth).

### 1.4 — Phase 1 acceptance

- ✅ A new BB harness case: feed `_saveBBAnswer()` a non-place response to "where were you born?" (e.g., "My dad worked nights at the aluminum plant"). The value MUST land in Review Queue, NOT in `personal.placeOfBirth`.
- ✅ Same harness case for birthOrder: feed a complaint response. MUST land in Review Queue.
- ✅ Hard reset: after `hardResetNarratorIdentity(janice_id)`, Janice has zero personal-identity values in any of: BB questionnaire / projection / memoir cache / localStorage. Switching to Kent shows none of Janice's data anywhere.
- ✅ The 6 new eval fixtures pass on `r5h-place-guard-v3` master eval.
- ✅ Janice's specific polluted values from the 2026-05-01 evidence become regression tests in `tests/test_qf_walk_validation.py`.

---

## Phase 2 — P0: Cross-narrator state isolation

**Block: parent session start.**

Per UI audit P0 #1: 5 runtime fields survive narrator switch — `softenedMode`, `turnCount`, `sessionAffectLog`, plus permission flags (camera, mic, TTS, save-voice, hands-free). This means Janice's safety posture can carry into Kent's interview.

### 2.1 — Narrator-scoped state initialization

Refactor `state.js` so all narrator-runtime state lives under `state.narratorRuntime[<person_id>]` instead of global keys. On narrator switch:
1. Save current narrator's runtime state to `state.narratorRuntime[<old_pid>]`
2. Load new narrator's runtime state from `state.narratorRuntime[<new_pid>]` (or initialize fresh if absent)
3. Permissions are NOT carried over — each narrator gets a fresh permissions check on first session

### 2.2 — Phase 2 acceptance

- ✅ Janice triggers softened mode → switch to Kent → Kent's `softenedMode` is False
- ✅ Janice has 12 turn count → switch to Kent → Kent's `turnCount` is 0
- ✅ Janice grants camera consent → switch to Kent → Kent does NOT inherit consent (must grant own)
- ✅ Switch back to Janice → her softened-mode + turn-count + camera consent are restored from runtime cache

---

## Phase 3 — P0: Narrator UI safety

**Block: parent session start.**

### 3.1 — "Return to Operator" hidden from narrator

Per UI audit P0 #2: the Break overlay shows a Return-to-Operator button. Narrators must never see operator-side controls.

Fix: gate the Return-to-Operator button on `state.session.role === "operator"`. Default narrator-mode hides it.

### 3.2 — Mic auto-rearm restored after Break resume

Per UI audit P0 #3: narrator clicks Resume after Break, mic stays silent because `micAutoRearm` was paused on Break and not restored on Resume.

Fix: Break sets a snapshot of pre-break mic state; Resume restores it.

### 3.3 — Today mode wired to runtime + composer

Per ChatGPT P0 + UI audit E:
- When Today is selected, runtime sets `current_era: "today"` AND `device_context: { date, time, timezone, dow }` is included in every prompt for that turn
- Prompt composer must allow present-day direct answers — strip the "I'm in a conversation mode that doesn't allow me to keep track of the current date" hallucinated capability constraint
- "What day is it?" answers the date first, THEN gently returns to the story

Add a small live date/time clock below Peek at Memoir in the right rail. It grounds the narrator and makes Today feel concrete. Updates every minute via `setInterval`.

### 3.4 — Phase 3 acceptance

- ✅ Open the Break overlay as a narrator (not operator). Return-to-Operator button MUST be invisible.
- ✅ Narrator clicks Break → Resume. Mic auto-rearm fires the way it did pre-break (or stays off if it was off pre-break).
- ✅ Narrator clicks Today in Life Map. Asks "what day is it?". Lori answers with the actual date (from `device_context`).
- ✅ Date/time clock visible in right rail under Peek at Memoir. Updates by the minute.

---

## Phase 4 — P1: Break / Pause / Resume cleanup

### 4.1 — Single Break button only

Per UI audit P1 #3 and ChatGPT spec:
- Remove `Take a break` from the top row (between Camera on and Save my voice)
- Remove `Resume` from next to Send
- Move the modified Break button to the lower-left near the Mic icon
- Break overlay shows ONE button: Resume (no Return-to-Operator for narrator; see 3.1)
- Remove the dead-code Pause duplicate from the footer

### 4.2 — Welcome-back TTS on Resume

Per UI audit P1 #1: silence after Break looks like failure. On Resume:
- Lori speaks: `"Welcome back, <preferred_name>. Ready to continue?"` via local TTS
- Falls back to text-only if TTS is disabled
- `<preferred_name>` resolves to `state.profile.basics.preferredName` or `firstName` or "you"

### 4.3 — In-flight TTS cancelled on Break

Per UI audit P1 #2: clicking Break while Lori is mid-sentence currently lets the audio finish. Confusing.

Fix: Break click cancels in-flight TTS immediately. If a model response is in progress, the UI ignores the result (drops the partial buffer).

### 4.4 — Escape-key dismissal on Break overlay

Per UI audit P1 #4: Break overlay traps the user — no Escape, no click-outside dismiss.

Fix: Esc key triggers Resume action (same as clicking Resume).

### 4.5 — Phase 4 acceptance

- ✅ Single Break button visible to narrator, lower-left near Mic
- ✅ Break overlay shows ONLY a Resume button (when narrator)
- ✅ Resume triggers Lori's "Welcome back, <name>. Ready to continue?" via TTS
- ✅ Mid-sentence Lori cancellation works (audio stops within 200ms of click)
- ✅ Escape key on Break overlay is equivalent to clicking Resume
- ✅ No duplicate Pause/Resume buttons anywhere in the UI

---

## Phase 5 — P1: Life Map cold-start + era binding

### 5.1 — Life Map renders on cold start in all modes

Per UI audit + Chris's reproducer: starting Janice in `questionnaire_first` mode shows the timeline but no right-side Life Map. Switching to clear_direct made it appear; switching back kept it. The Life Map mount is happening on a path that doesn't include cold-start in `questionnaire_first`.

Fix: Life Map render is mounted from `state.session.session_id` change, not from `sessionStyle` change. Refactor `interview.js` Life Map mount to subscribe to session-id, render once on first mount of the narrator room, and refresh from the timeline spine on era change.

### 5.2 — Era buttons stay live + sync runtime

Per UI audit P1 #2: Today highlighted green, then Earliest Years click did nothing.

Fix: every era button click MUST:
1. Update visual highlight (current behavior, keep)
2. Call `runtime.setCurrentEra(era_id)` (currently missing on some paths)
3. Trigger a refresh of Lori's prompt context (clear stale era from runtime71)
4. Log a `[life-map][era-click] era=<id>` line to console + harness audit

If any step fails, the click bubbles up an error to the diag panel — never silently dies.

### 5.3 — Phase 5 acceptance

- ✅ Start Janice fresh in `questionnaire_first` → Life Map renders on right immediately, no mode-switch dance required
- ✅ Same for Kent in `questionnaire_first`, `clear_direct`, and the future consolidated `interview` mode
- ✅ Click Today → Earliest Years → Coming of Age → Today in sequence. Each click: highlight changes, runtime era updates, next Lori prompt-type matches the era, Run Report shows 4 era-click events in audit.
- ✅ No "stuck green" state ever — all era buttons remain clickable always

---

## Phase 6 — P1: Peek at Memoir cleanup

### 6.1 — Source-of-truth alignment

Per UI audit P1 #6: in-app peek and TXT export read from different sources, so they disagree (in-app showed polluted Janice data, TXT export showed cleaner placeholders).

Fix: both surfaces read from `compose_memoir_view(person_id)` (a single backend-side composer that returns a structured view). The view always reads from confirmed truth (`projection.fields` where `confirmed=true` AND value is non-empty) — never from `suggest_only` candidates and never from BB questionnaire raw values.

### 6.2 — Overflow + scroll

Per UI audit P1 #5: in-app peek truncates Earliest Years.

Fix: peek popover gets proper `overflow-y: auto` with a max-height. First section never clips. Add subtle bottom-fade gradient when content exceeds visible area.

### 6.3 — Visual quieter

Per Chris: Peek at Memoir button is too bright.

Fix: button reduced to ~85% size of current, color matches the secondary right-rail buttons (no longer the brightest control on screen).

### 6.4 — Phase 6 acceptance

- ✅ In-app peek and TXT export show identical content for the same narrator at the same point in time
- ✅ Earliest Years renders with no clipping in the popover
- ✅ Peek button is no longer the visual focal point

---

## Phase 7 — P2: Polish (parallel cleanup, doesn't block parent run)

These can land alongside or after the gated phases.

- Lori date-capability: composer prompt drops the "I can't tell the date" hallucinated constraint when Today mode is active
- Mid-session Reset Identity recovery button on the operator panel (keyboard shortcut + visible button)
- Peek popover stale-state refresh on data change events
- Operator dashboard env audit (`OPERATOR_*` flags) — ensure the right ones are enabled for parent runs

---

## Phase 8 — P1: Session-style consolidation

Per Chris's question + today's `style_diff_checks` evidence (clear_vs_warm word_delta=1, scene_score parity=0):

Reduce 4 modes to 3:

1. **Questionnaire First** — structured identity and family intake. Best for setup. KEEP.
2. **The Interview** — combine `clear_direct` + `warm_storytelling` (the system internally adjusts tone, the operator picks one mode). The current style_diff data shows these two modes barely differentiate in practice — collapsing them simplifies the operator surface without losing capability.
3. **Companion** — keep separate, preferably as right-side or explicit posture. KEEP.

For the parents' laptop, default to **The Interview** with operator-only access to mode changes.

### 8.1 — Implementation

- Rename `clear_direct` to `interview` in `state.js`, `prompt_composer.py`, `chat_ws.py`, eval harness
- `warm_storytelling` becomes an internal posture inside `interview` mode, switched per-narrator-context (e.g. by `current_era` or affect signal). Keep the existing per-style word limits but apply them as posture-conditional.
- Remove `warm_storytelling` from the operator picker. Migrate any narrator-saved-state value `"warm_storytelling"` to `"interview"` on read.
- Update the harness `style_diff_checks` to validate the new 3-mode layout

### 8.2 — Phase 8 acceptance

- ✅ Operator picker shows 3 options: Questionnaire First / The Interview / Companion
- ✅ A narrator who had `warm_storytelling` saved migrates to `interview` cleanly with no warning
- ✅ The Interview mode still produces warm responses for narrative content and direct responses for fact retrieval (per the existing posture system)
- ✅ `style_diff_checks` updated and pass

---

## Phase 9 — Run Report panel

Land the unified `Run Report` panel that opens after every session wrap-up.

### 9.1 — Replaces

- Current operator-log popup
- Current operator audit surface
- Current eval-harness Bug Panel section (subsumed as a tab)

### 9.2 — Three tabs

- **Session Audit** — health probes, transcript count, mode switches, UI events, RED/AMBER/PASS counts. Sourced from existing `operator_eval_harness` + `operator_stack_dashboard` endpoints.
- **Review Queue** — each candidate fact with Accept / Edit / Reject controls. Sourced from `interview_segment_flags` + projection `suggest_only` candidates. Each row is an Evidence Card.
- **Evidence Cards** view (within Review Queue) — for each candidate: field path, proposed value, source transcript excerpt, confidence, narrator turn timestamp, action buttons.

### 9.3 — Hard block

If Session Audit shows RED, the operator-panel "Start Narrator Session" button is disabled. Only PASS or AMBER (with explicit operator override) allows session start.

### 9.4 — Phase 9 acceptance

- ✅ Run Report opens automatically when a session ends
- ✅ Session Audit reflects today's RED/AMBER/PASS count taxonomy
- ✅ Review Queue shows the Janice-style polluted candidates (after Phase 1 lands they go here instead of truth)
- ✅ Operator approving from Review Queue actually writes to truth via a trusted `human_edit` source signature
- ✅ Start Narrator Session is disabled while Session Audit shows RED

---

## Files touched (rough inventory)

```
NEW:
  server/code/api/services/qf_walk_validator.py     (Phase 1.1)
  server/code/api/services/memoir_view_composer.py  (Phase 6.1)
  server/code/api/routers/run_report.py             (Phase 9)
  ui/js/run-report.js                               (Phase 9)
  ui/css/run-report.css                             (Phase 9)
  tests/test_qf_walk_validation.py                  (Phase 1)
  tests/test_hard_reset_identity.py                 (Phase 1.2 + 2)
  tests/test_today_mode_wiring.py                   (Phase 3.3)
  data/qa/qf_validation_cases.json                  (Phase 1.3, 6 new fixtures)
  WO-PARENT-SESSION-HARDENING-01_Spec.md            (this doc)

MODIFIED:
  ui/js/session-loop.js                             (Phase 1.1 — _saveBBAnswer routing)
  ui/js/projection-sync.js                          (Phase 1.1 — qf_walk_answer source)
  ui/js/state.js                                    (Phase 2 — narratorRuntime scoping)
  ui/js/app.js                                      (Phase 3.1 + 4 — break overlay + topbar)
  ui/js/interview.js                                (Phase 5 — Life Map mount + era click)
  ui/css/lori80.css                                 (Phase 4 + 6.3 — button placement + Peek styling)
  ui/hornelore1.0.html                              (Phase 4 — DOM cleanup, single Break button)
  server/code/api/routers/extract.py                (Phase 1.3 — placeOfBirth deterministic guard)
  server/code/api/prompt_composer.py                (Phase 3.3 — Today mode + drop date-capability denial)
  server/code/api/routers/chat_ws.py                (Phase 3.3 — device_context propagation)
  server/code/api/main.py                           (Phase 9 — run_report router include)
  data/qa/question_bank_extraction_cases.json       (Phase 1.3 — case_111–116)
  scripts/archive/run_golfball_interview_eval.py    (Phase 8 — style_diff_checks update)
  CLAUDE.md                                         (Phase 8 — session-style consolidation note)
  .env.example                                      (Phase 9 — HORNELORE_RUN_REPORT flag)
```

---

## Acceptance gate (overall)

**Before any live narrator session with Kent or Janice:**

1. ✅ Phase 1 (truth-pipeline) green — Janice-style pollution cannot reach truth
2. ✅ Phase 2 (state isolation) green — narrator switch is clean
3. ✅ Phase 3 (UI safety) green — operator controls hidden from narrator, mic auto-rearms, Today works
4. ✅ Phase 4 (Break/Pause cleanup) green — single Break button, welcome-back TTS, in-flight TTS cancellation
5. ✅ Phase 5 (Life Map) green — cold-start renders, era buttons live in all modes
6. ✅ Phase 6 (Peek at Memoir) green — single source of truth, no clipping
7. ✅ Run Report (Phase 9) opens automatically and blocks RED-state session start

Phase 7 (polish) and Phase 8 (mode consolidation) can land in parallel; they don't block.

---

## Anti-goals

- Don't add NEW Lori-behavior detectors here. Phelan / push-after-resistance / control-yield rollup all live in WO-LORI-CONTROL-YIELD work; this WO is structural / UI / truth-pipeline.
- Don't fix the broken Memory River tab — Memory River is RETIRED per CLAUDE.md mission section + the 2026-05-01 Kawa retirement decision. Just delete the tab from the DOM (Phase 5 cleanup).
- Don't overhaul Bio Builder. The QF auto-save fix in Phase 1.1 is targeted at protected-identity fields; the rest of BB stays as-is.
- Don't ship operator-side debugging surfaces to narrator. Every UI element must be checked against narrator-vs-operator role.

---

## Sequencing recommendation

Phases 1, 2, 3 are all P0 and can land in any order — they don't depend on each other. Phase 1 (truth-pipeline) is the most invasive. Phase 2 (state isolation) is the highest-leverage refactor. Phase 3 (UI safety) is the most user-visible.

Suggested order:
1. **Phase 1** first — truth-pipeline blocks everything else; Janice's pollution evidence is the loudest signal we have
2. **Phase 2** alongside Phase 3 — they touch different files, can run in parallel
3. **Phase 4 + 5** together — UI-only, share the lori80.css + app.js + interview.js editing surface
4. **Phase 6** after Phase 1 (Phase 6 reads from truth; Phase 1 cleans truth)
5. **Phase 9** can start now in parallel as a docs-only spec for the panel; backend wiring waits until Phase 1 lands so the Review Queue has real candidates to render
6. **Phase 8** (mode consolidation) any time — independent of all above

Cost estimate: ~5–7 days of focused work, depending on how aggressively the Run Report panel is scoped.
