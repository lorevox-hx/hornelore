# BUG-LORI-SWITCH-FRESH-GREETING-01 — When switching back to a narrator with prior session content, Lori opens with cold-start identity-onboarding greeting instead of continuation

**Status:** OPEN — Phase 1 (basic continuation) auto-resolves when WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 lands; Phase 2 (active-listening continuation paraphrase) is the independent remaining scope.
**Severity:** AMBER — narrator-visible UX issue; narrator explicitly noticed
**Surfaced by:** Manual switch transcripts 2026-05-06 02:59 + 03:02
**Author:** Chris + Claude (2026-05-06; Phase 2 added 2026-05-05 after code review surfaced existing welcome-back path)
**Lane:** Lane 2 / parent-session blockers

---

## Problem

When the operator (or narrator) switches BACK to a narrator who already has prior session content, Lori opens with the canned cold-start identity-onboarding greeting:

> "Hi mary, I'm Lori. I'm here to help you capture your life story — the memories, the people, the places that mattered to you. There's no wrong way to do this. We can go in order of your life, or jump around to whatever you want to talk about today. What would you like to start with?"

That intro is correct for first contact. It is wrong when the narrator has already done multiple turns with Lori, has identity confirmed, has stories captured, and is just returning. The right behavior is a continuation greeting: "Welcome back, Mary" or "Last time we talked about your building years — would you like to continue there?"

Mary explicitly noticed in the production session: **"you tole me this last time"** — the narrator can tell Lori is treating them as a stranger. That's a direct trust-erosion signal.

## Evidence

`transcript_switch_motgx.txt` — Mary's transcript opens with the SYSTEM_QF birth-order question (after Lori's canned cold-start greeting that Chris's chat dump showed). Mary's first response is:

```
[2026-05-06 02:59:32] USER: you tole me this last time
```

She knows Lori already covered this material with her. Lori didn't recognize her returning state.

Same pattern after switching back to Marvin later in the same operator flow — Lori opens with "Hi Marvin, I'm Lori. I'm here to help you capture your life story..." despite Marvin having an active session with prior turns including identity, era walks, and a spouse-memory probe.

## Diagnosis hypothesis

The narrator-room initialization logic uses a single greeting path that doesn't differentiate "first contact" vs "returning narrator". Likely candidates for the differentiation signal:

- `state.session.turn_count > 0` (any prior turn = returning)
- `archive.get_turns(narrator_id, limit=1)` returns rows = returning
- `interview_projections.projection_json` has any non-null fields = returning
- `state.bioBuilder.personal.firstName` is set = returning (depends on Phase E mirror, may be None)

The greeting composer probably fires unconditionally on session_start because the cold-start path is the original / only code path that exists.

## Fix shape

Three components:

**A. Detection.** On session_start (or its successor "session_resume" path), check whether the narrator has prior session content. Use the most reliable signal — probably `archive.add_turn` history count or `interview_projections.projection_json` having fields. NOT `state.bioBuilder` because that's the BB mirror gap (Phase E) and is unreliable until Phase E lands.

**B. Continuation greeting templates.** Add new greeting templates to `prompt_composer.py` for the returning case. Examples:

- General returning: "Welcome back, [name]. We've been working on your life story together. Where would you like to pick up?"
- Era-aware: "Welcome back, [name]. Last time we were in your [last era touched] — would you like to continue there, or start somewhere new?"
- Identity-only-confirmed: "Welcome back, [name]. I have your name, your birthday, and where you were born. Where would you like to start today?"

**C. Skip the questionnaire-first onboarding sequence on resume.** When resuming, don't fire the identity-onboarding system prompts ("introduce yourself simply as Lori. Do NOT explain where your name comes from..."). Those are first-contact prompts. Resume should jump straight to the continuation greeting, then the regular interview loop.

## Phase split (post-2026-05-05 code review)

A 2026-05-05 code review changed the implementation picture for this BUG. The system already has a continuation-opener path that was being suppressed:

- **`server/code/api/routers/interview.py:495-547`** — `/api/interview/opener?person_id=...` endpoint with three branches (`first_time` / `welcome_back` / `onboarding_incomplete`).
- **`interview.py:486-489`** — welcome-back template: `"Welcome back, {name}. Where would you like to continue today?"` (basic but functional).
- **`ui/hornelore1.0.html:5184-5204`** — frontend already calls the opener on narrator open when prior user turns > 0 AND identity is complete.
- **`ui/hornelore1.0.html:5179`** — but a `_ssIsQF` gate (sessionStyle === "questionnaire_first") explicitly **suppresses** both the welcome-back SYSTEM prompt AND the opener fetch, with the WO-13 / #207 comment: *"questionnaire_first override — skipping welcome-back/opener so session-loop owns first prompt."*

This explains Mary and Marvin cleanly: they were running under questionnaire-first session style, the gate suppressed the welcome-back, and the QF lane fired its identity-onboarding cold-start template instead.

**Phase 1 (basic continuation greeting) — auto-resolves via WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1.** When QF retirement removes the QF lane from the live narrator path, `_ssIsQF` can never be true on the live path, the gate inverts, and the existing welcome-back composer fires. No new prompt_composer template is required for the basic case. Components A and C above ("Detection" and "Skip the questionnaire-first onboarding sequence on resume") become consequences of QF retirement rather than independent edits. Component B's basic "Welcome back, [name]" template is already in place at `interview.py:486-489`.

**Phase 2 (active-listening continuation paraphrase) — independent scope; remains the substantive work for this BUG.** The existing welcome-back template is paper-thin: *"Welcome back, {name}. Where would you like to continue today?"* That's a generic hello, not a paraphrase of where the conversation actually was. The desired shape is:

> *"Welcome back, Mary. Last time we were talking about your building years and the routines that helped hold your family together. Would you like to pick that up, or start somewhere else?"*

Phase 2 builds the composer that produces that.

## Phase 2 — Active-listening continuation paraphrase

**Inputs (data the composer needs).**

1. **Last era touched.** `state.session.currentEra` already exists and is canonical (Lane E from 2026-05-03 evening landed era-canonicalization). Surface as `last_era_id` + warm label via `lv_eras` registry.
2. **Last story disclosed in that era.** Comes from WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c — `peek_at_memoir.summarize_for_runtime` extension exposes `recent_turns_by_era`. The composer asks: "what's the most recent narrator-volunteered story stub for `last_era_id`?" Returns null if no narrator turn for that era exists yet.
3. **Last unfinished thread (optional).** "What was the last question Lori asked, and did the narrator answer it?" Requires a small new accessor reading the last two turns of `archive.get_turns(narrator_id, limit=2)`: if the most recent turn is a Lori question + no narrator response, that question is the unfinished thread. If the narrator's response was a non-substantive answer ("I don't remember", silence), still treat as unfinished. This input is optional in v1; degrade gracefully when not available.
4. **Identity scaffold (already present).** `_build_profile_seed` (Phase A read-bridge, landed 2026-05-04) provides name, DOB, POB, identity scaffold via `profiles.profile_json` + `interview_projections.projection_json`. Composer reads as it does today.

**Composer logic.** New `compose_continuation_paraphrase(narrator_id) → str` in `prompt_composer.py`. Cascading template selection by available signals:

```
Tier A — era + story stub + unfinished thread present:
  "Welcome back, {name}. Last time we were in your {warm_era_label}, talking
  about {story_anchor}. {tier_a_close}"
  where tier_a_close ∈ {
    "Would you like to pick that up, or start somewhere else?"  // default
    "I asked you about {unfinished_anchor} — would you like to answer that
     now, or pick a different thread?"  // when unfinished thread exists
  }

Tier B — era + story stub, no unfinished thread:
  "Welcome back, {name}. Last time we were in your {warm_era_label} and you
  were telling me about {story_anchor}. Where would you like to pick up?"

Tier C — era only, no story stub yet:
  "Welcome back, {name}. Last time we were in your {warm_era_label}. Would
  you like to continue there, or start somewhere else?"

Tier D — no era, no story stub (resume on a narrator who barely got going):
  "Welcome back, {name}. Where would you like to continue today?"
  (= existing interview.py:486-489 fallback)
```

**Anchor extraction.** `story_anchor` is a SHORT noun-phrase pulled from the narrator's most recent volunteered turn for `last_era_id` — same pattern as `lori_reflection.extract_concrete_anchor()` (proper-noun phrases > kinship anchors > content tokens, with `_PROPER_NOUN_BLOCKLIST`). Reuse that helper rather than building a parallel one. If anchor extraction returns None, drop to Tier C.

**Era warm-label rule.** Use the same warm-label mapping as the existing era-explainer block in `prompt_composer.py` ("the years before you started school" / "the building years when you were starting your family or career" / etc.) so Lori never says the bare era_id token to the narrator. This is principle-2 compliance ("no system-tone outputs").

**Output handoff.** The composed string replaces the welcome-back template return at `interview.py:486-489` (or wraps it as a v2 path while v1 stays as fallback). Frontend at `hornelore1.0.html:5184-5204` already consumes `opener_text` — no frontend change needed once Phase 1 (QF retirement) lands and re-enables the opener fetch.

**Default-on / default-off.** Phase 2 lands behind `HORNELORE_CONTINUATION_PARAPHRASE=0` default-off until QF-RETIRE Phase 1 has been live for at least one parent-session-equivalent cycle. Once verified, flip default-on. Tier D (bare welcome-back) is the safety floor when the flag is off OR when none of Tiers A/B/C have signals.

## Acceptance gate

**Phase 1 (auto-resolves via QF-RETIRE Phase 1):**
- After QF retirement Phase 1 lands, switching to a narrator with prior turns produces the existing `interview.py:486-489` welcome-back template ("Welcome back, {name}. Where would you like to continue today?") — NOT the cold-start identity-onboarding intro.
- Switching to a fresh narrator (no prior turns) still produces the cold-start `first_time` template as before.
- The narrator does NOT receive the identity-onboarding system-prompt sequence (askName/askDob/askPob) on resume.
- Manual smoke test: switch between Mary and Marvin in a real browser. Each produces a basic welcome-back, never the cold-start intro.

**Phase 2 (independent scope):**
- When all four inputs (era + story stub + unfinished thread + identity) are available, composer emits Tier A.
- When story stub exists but no unfinished thread, composer emits Tier B.
- When only era exists, composer emits Tier C.
- When neither era nor story stub is available, composer emits Tier D (= bare welcome-back, regression-safe).
- `story_anchor` is always verbatim narrator text or its kinship-canonicalized form — no LLM confabulation, no operator-side label leak.
- `warm_era_label` is the warm-label mapping, never the raw era_id.
- No "you tole me this last time"-shaped narrator complaints across the next 5+ manual switch sessions.
- Composer degrades gracefully — Tier D is reached without exception in any input-missing scenario.

## Files (planned, Phase 2)

**Likely modified:**
- `server/code/api/prompt_composer.py` — new `compose_continuation_paraphrase()` function with the four-tier cascade; reuses warm-era-label mapping from the existing era-explainer block.
- `server/code/api/routers/interview.py` — `_build_opener_text()` for `welcome_back` kind dispatches to `compose_continuation_paraphrase()` when `HORNELORE_CONTINUATION_PARAPHRASE=1`, else falls back to current bare welcome-back.
- `server/code/api/peek_at_memoir.py` (or wherever Phase 1c lands `recent_turns_by_era`) — exposed as composer input; depends on WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c.
- `server/code/api/services/lori_reflection.py` — the existing `extract_concrete_anchor()` helper gets reused for `story_anchor` extraction; no new code, just a public-API reference.

**Possibly modified:**
- `server/code/api/db.py` — small new accessor `get_last_lori_question_with_response_state(narrator_id)` returning the last Lori question turn + whether the narrator answered substantively. Optional input for Tier A's unfinished-thread variant; degrade gracefully if absent.
- `server/code/api/routers/extract.py` — zero touch (extractor unaffected).

**Zero touch:**
- Frontend (`ui/hornelore1.0.html`, `ui/js/app.js`) — opener_text consumption is unchanged; the API contract stays the same.
- Memory_echo composer (already correctly identifies returning state when called).
- Lori behavior services (lori_communication_control, lori_reflection — Patch C runtime shaping unaffected).
- Safety classifier path (Phase 2 of SAFETY-INTEGRATION-01 unaffected).

## Risks & rollback

**Risk 1: false-positive continuation greeting on real first-contact.** Mitigation: use multiple signals (archive turns AND projection fields) and require both. Better to occasionally show cold-start intro to a returning narrator than to skip onboarding for a real first-contact narrator.

**Risk 2: continuation greeting feels stale or generic.** "Welcome back, Mary. We've been working on your life story together." can feel chatty over many sessions. Mitigation: vary the greeting by era last touched, or by time since last session, so it doesn't feel formulaic.

**Risk 3: identity-onboarding sequence skip leaves a narrator without identity captured.** If a narrator had a session where they didn't actually answer name/DOB/POB (left mid-onboarding), resume would skip the onboarding and the system never gets identity. Mitigation: detection should require BOTH "prior turns exist" AND "identity is captured" (firstName + DOB + POB all present in profile_json). If only prior turns exist but identity is incomplete, route to "let's pick up where we left off — I still need [missing fields]".

**Rollback:** revert to cold-start greeting on every session_start. Narrators get treated as strangers on every return. No regression on first-contact flows.

## Sequencing

**Phase 1 lands implicitly when WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 lands.** No independent work order; the `_ssIsQF` gate inversion at `hornelore1.0.html:5179` re-enables the existing welcome-back path.

**Phase 2 lands after WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c.** Phase 1c is the data source for `recent_turns_by_era`; the continuation-paraphrase composer depends on it. Phase 2 also benefits from running on top of Patch C runtime shaping (`HORNELORE_REFLECTION_SHAPING=1`) so Lori's anchor extraction logic is consistent across reflection and continuation surfaces.

After both phases land, re-test with manual switch sessions for the "you tole me this last time" pattern. Phase 2 should produce a paraphrase that proves Lori remembers the prior conversation; Mary's complaint becomes structurally impossible.

## Cross-references

- **WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01** — landing Phase 1 of that WO auto-resolves Phase 1 of this BUG via the `_ssIsQF` gate inversion at `hornelore1.0.html:5179`. Critical dependency.
- **BUG-LORI-SYSTEM-QF-PREEMPTION-01** — supersededby WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 at architectural level; closes when that WO Phase 1 lands. Closing it also clears the SYSTEM_QF preemption that was secondary noise in this BUG's transcripts.
- **WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c** — primary data source for Phase 2's `recent_turns_by_era` input. Phase 2 cannot ship until Phase 1c lands.
- **WO-PROVISIONAL-TRUTH-01 Phase A** — landed 2026-05-04. Already provides identity scaffold via `_build_profile_seed`; no additional dependency.
- **WO-PROVISIONAL-TRUTH-01 Phase E** — parked. NOT a dependency for this BUG (we deliberately use archive turn count + projection_json, not `state.bioBuilder` mirror state, so we don't block on Phase E).
- **WO-LORI-SESSION-AWARENESS-01 Phase 1** — memory_echo composer fix landed 2026-04-27; same conceptual problem on a different turn-mode surface (memory_echo readback). Phase 2 of this BUG is the same kind of fix applied to the session-start greeting surface.
- **CLAUDE.md design principle 8** — "Operator seeds known structure; Lori reflects what is there." Phase 2's continuation paraphrase is the most concrete instance of "Lori reflects" on the resume surface.

## Changelog

- 2026-05-06: Spec authored after Mary's "you tole me this last time" production observation.
- 2026-05-05: Phase 1 / Phase 2 split added after code review surfaced the existing `/api/interview/opener` welcome-back path and the `_ssIsQF` suppression gate at `hornelore1.0.html:5179`. Phase 1 (basic continuation) now auto-resolves via WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 — no new code required for the basic case. Phase 2 (active-listening continuation paraphrase) added as the substantive remaining scope, dependent on WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c data feed.
