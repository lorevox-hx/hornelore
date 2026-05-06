# BUG-LORI-SWITCH-FRESH-GREETING-01 — Phase 2 implementation plan

**Status:** READY FOR REVIEW. Two upstream dependencies must land first (see "Blocking dependencies" below).
**Scope:** Phase 2 only — active-listening continuation paraphrase composer. Phase 1 (basic continuation) auto-resolves via WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1.
**Authored:** 2026-05-05 night-shift code review.
**Reviewer:** Chris.

---

## What Phase 2 is

Replace the bare welcome-back template (`"Welcome back, {name}. Where would you like to continue today?"`) with an active-listening continuation paraphrase that reads back where the conversation actually was:

> *"Welcome back, Mary. Last time we were talking about your building years and the routines that helped hold your family together. Would you like to pick that up, or start somewhere else?"*

Phase 2 composer is **deterministic, no LLM call, narrator-text-verbatim** — same posture as `compose_memory_echo`. Excerpts come from session transcript via `peek_at_memoir`; era labels come from `lv_eras` registry; identity comes from `_build_profile_seed`.

## Blocking dependencies

Both must land before Phase 2 can ship:

| Dep | Why blocking | Status |
|---|---|---|
| **WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1** | The welcome-back code path is currently suppressed by `_ssIsQF` gate at `hornelore1.0.html:5179`. Until Phase 1 inverts that gate, no continuation greeting fires at all — Phase 2 composer would never be invoked. | Plan banked 2026-05-05; ready to land. |
| **WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c** | Phase 2's Tier A and Tier B variants require `recent_turns_by_era` data — turns grouped by canonical era_id, requiring `archive.add_turn(..., current_era=...)` write-time binding + a new `summarize_for_runtime` field exposing the era-grouped turns. Without Phase 1c, the composer can only reach Tier C (era only) and Tier D (bare welcome-back) — degraded but functional. | Spec banked 2026-05-05; not yet implemented. |

**Phase 2 can ship in two slices** if we want partial uplift sooner:
- **Slice 2a (no Phase 1c dependency):** Tier C + Tier D. Lands after QF-RETIRE Phase 1 only. Provides "Welcome back, {name}. Last time we were in your {warm_era_label}. Would you like to continue there, or start somewhere else?" — a real upgrade over bare welcome-back.
- **Slice 2b (after Phase 1c):** Tier A + Tier B. Adds the story-anchor paraphrase ("...telling me about {story_anchor}"). Full target shape.

I'd recommend **landing Slice 2a immediately after QF-RETIRE Phase 1** — partial uplift, validates the composer wiring end-to-end, lets Slice 2b ship as a pure additive upgrade once Phase 1c lands.

## Existing scaffolding (reuse)

The following already exist and Phase 2 plugs into them. Zero rewrite of any of these.

| Surface | Path | What it gives Phase 2 |
|---|---|---|
| `peek_at_memoir.build_peek_at_memoir(person_id, session_id)` | `server/code/api/services/peek_at_memoir.py:57` | Returns `{recent_turns: [...filtered through safety...], promoted_truth, sources_available}`. Phase 2 reads `recent_turns` for the era-grouped lookup. Already runs through `safety.filter_safety_flagged_turns()` so sensitive turns never reach the composer (LAW 3 satisfied by construction). |
| `peek_at_memoir.summarize_for_runtime(peek_data)` | `server/code/api/services/peek_at_memoir.py:138` | Phase 1c extends this with `recent_turns_by_era` (Phase 2 consumes it). |
| `lori_reflection.extract_concrete_anchor(narrator_text)` | `server/code/api/services/lori_reflection.py:515` | Returns one short noun-phrase from narrator text (proper-noun phrase > kinship reference > content token, with `_PROPER_NOUN_BLOCKLIST` filtering). Phase 2 reuses this verbatim for `story_anchor` selection. |
| `lori_reflection._KINSHIP_CANON` | `server/code/api/services/lori_reflection.py:190` | Kinship canonicalization (`dad → father`, etc.). Already used by `extract_concrete_anchor`. |
| `prompt_composer._build_profile_seed(person_id)` | `server/code/api/prompt_composer.py:671` | Returns identity scaffold (preferred_name, full_name, childhood_home, parents_work, etc.) by reading both `profiles.profile_json` AND `interview_projections.projection_json` (Phase A read-bridge, landed 2026-05-04). Phase 2 reads `preferred_name` for the greeting address form. |
| `prompt_composer.compose_memory_echo(text, runtime, state_snapshot)` | `server/code/api/prompt_composer.py:1305` | The pattern Phase 2 mirrors — pure-deterministic composer, runtime-fed, no LLM. |
| `prompt_composer.compose_system_prompt(...)` | `server/code/api/prompt_composer.py:1588` | Where Phase 2's composer slots into the system-prompt path if needed (probably NOT needed; Phase 2 returns through the opener API instead). |
| `lv_eras.LV_ERAS` registry | `server/code/api/lv_eras.py` + `ui/js/lv-eras.js` | Era_id → warm label mapping (`earliest_years` → "the years before you started school", `building_years` → "the building years when you were starting your family or career", etc.). Phase 2 reads this for `warm_era_label`. |
| `lv_eras.legacy_key_to_era_id(...)` | `server/code/api/lv_eras.py` | Canonicalizes a possibly-legacy era key. Phase 2 calls this on `state.session.currentEra` to normalize. |
| `interview.py:_build_opener_text(kind, name)` | `server/code/api/routers/interview.py:474` | The function that returns the opener text. Three kinds: `first_time` / `welcome_back` / `onboarding_incomplete`. Phase 2 modifies the `welcome_back` branch to call the new continuation composer when the flag is on. |
| `interview.py:get_opener` | `server/code/api/routers/interview.py:496` | The `/api/interview/opener?person_id=...` endpoint already does the kind-routing. Frontend already consumes `opener_text`. Phase 2 doesn't change the API contract — only what the `welcome_back` branch returns. |

## New additions (the actual Phase 2 work)

### Addition 1 — `prompt_composer.compose_continuation_paraphrase()`

New function in `server/code/api/prompt_composer.py`, sibling to `compose_memory_echo`. Pure-deterministic, no LLM, no DB write.

```python
def compose_continuation_paraphrase(
    person_id: str,
    session_id: Optional[str] = None,
    last_era_id: Optional[str] = None,
    runtime: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a deterministic active-listening continuation greeting for a
    returning narrator. Mirrors compose_memory_echo's pattern.

    Tier cascade (highest signal wins):
      Tier A — era + story stub + unfinished thread → full paraphrase
      Tier B — era + story stub                     → no-thread paraphrase
      Tier C — era only                             → era-aware welcome-back
      Tier D — no era, no story stub                → bare welcome-back fallback

    Pure-stdlib + lazy imports. LAW 3 — does NOT import from extract /
    chat_ws / llm_api. Reads peek_at_memoir + lv_eras + lori_reflection
    + _build_profile_seed.

    Returns a string suitable as opener_text. Always returns a non-empty
    string (Tier D guarantees a fallback).
    """
    # 1. Identity
    seed = _build_profile_seed(person_id) or {}
    name = (seed.get("preferred_name") or "").strip()
    if not name:
        full = (seed.get("full_name") or "").strip()
        name = full.split()[0] if full else "friend"

    # 2. Era resolution
    era_id = None
    warm_era_label = None
    if last_era_id:
        try:
            from ..lv_eras import legacy_key_to_era_id, era_warm_label
            era_id = legacy_key_to_era_id(last_era_id) or last_era_id
            warm_era_label = era_warm_label(era_id)
        except Exception:
            era_id = last_era_id
            warm_era_label = None

    # 3. Story anchor + unfinished thread (lazy — only if era is known)
    story_anchor = None
    unfinished_anchor = None
    if era_id and session_id:
        try:
            from ..services.peek_at_memoir import build_peek_at_memoir, summarize_for_runtime
            from ..services.lori_reflection import extract_concrete_anchor
            peek = build_peek_at_memoir(person_id, session_id=session_id)
            summary = summarize_for_runtime(peek)
            # Phase 1c data feed
            era_turns = (summary.get("recent_turns_by_era") or {}).get(era_id) or []
            if era_turns:
                # Pick the most recent narrator turn for this era
                latest_user_text = ""
                for turn in reversed(era_turns):
                    if turn.get("role") == "user":
                        latest_user_text = (turn.get("content") or "").strip()
                        if latest_user_text:
                            break
                if latest_user_text:
                    story_anchor = extract_concrete_anchor(latest_user_text)
        except Exception as exc:
            logger.warning("[continuation-paraphrase] peek/anchor failed: %s", exc)

    # 4. Unfinished thread (lazy — only if Tier A potentially reachable)
    if story_anchor:
        try:
            from .. import db as _db
            unfinished = _db.get_last_lori_question_with_response_state(
                person_id, session_id
            )
            if unfinished and not unfinished.get("answered_substantively"):
                unfinished_anchor = (unfinished.get("question_anchor") or "").strip() or None
        except Exception as exc:
            logger.warning("[continuation-paraphrase] unfinished read failed: %s", exc)

    # 5. Tier selection
    if warm_era_label and story_anchor and unfinished_anchor:
        # Tier A — full paraphrase with unfinished thread
        return (
            f"Welcome back, {name}. Last time we were in {warm_era_label}, "
            f"talking about {story_anchor}. I asked you about {unfinished_anchor} — "
            f"would you like to answer that now, or pick a different thread?"
        )
    if warm_era_label and story_anchor:
        # Tier B — full paraphrase without unfinished thread
        return (
            f"Welcome back, {name}. Last time we were in {warm_era_label} "
            f"and you were telling me about {story_anchor}. Where would you "
            f"like to pick up?"
        )
    if warm_era_label:
        # Tier C — era only
        return (
            f"Welcome back, {name}. Last time we were in {warm_era_label}. "
            f"Would you like to continue there, or start somewhere else?"
        )
    # Tier D — bare welcome-back (regression-safe fallback, matches legacy)
    return f"Welcome back, {name}. Where would you like to continue today?"
```

Notes:
- Uses lazy imports throughout (LAW 3 + `HORNELORE_CONTINUATION_PARAPHRASE=0` keeps this module out of `sys.modules` when default-off).
- Each tier's signals are checked in priority order; partial signals downgrade gracefully.
- Tier D matches `interview.py:486-489` text exactly so default-off + Tier-D-fallback paths are byte-stable with the current welcome-back template.

### Addition 2 — `db.get_last_lori_question_with_response_state()`

New accessor in `server/code/api/db.py`. Reads last 2 turns from the archive for `(person_id, session_id)`; returns metadata about the last Lori question + whether narrator answered substantively.

```python
def get_last_lori_question_with_response_state(
    person_id: str,
    session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return metadata about the last Lori question and whether the
    narrator answered it substantively. Used by the continuation
    paraphrase composer to decide between Tier A (with unfinished
    thread) and Tier B (without).

    Returns None if:
      - no session_id given
      - last 2 turns don't form a (lori_question, narrator_answer) pair
      - last Lori turn was not a question
    Returns dict with keys:
      - question_text: the literal Lori question (capped at 200 chars)
      - question_anchor: noun-phrase pulled via extract_concrete_anchor
      - answered_substantively: bool
        (False when narrator response is < 4 content tokens OR matches
         "I don't remember" / "I don't know" / silence patterns)
    """
    # ... read last 2 turns from archive, classify, return ...
```

Implementation outline:
- Read last 2 turns from `archive.read_transcript(person_id, session_id)` (newest at end).
- If newest is `role=user` and prior is `role=assistant`: candidate pair.
- If `role=assistant` text ends in `?` (or matches a question regex): treat as question.
- For `answered_substantively`: count content tokens in narrator response, compare against a 4-token threshold + "I don't remember"/etc. patterns.
- Use `lori_reflection.extract_concrete_anchor()` for `question_anchor`.

Cap on read scope: only read last 2 turns; don't walk the full session.

### Addition 3 — `lv_eras.era_warm_label()`

New helper in `server/code/api/lv_eras.py` (and parity in `ui/js/lv-eras.js`). Returns the warm narrator-facing label for a canonical era_id.

```python
def era_warm_label(era_id: str) -> Optional[str]:
    """Return the warm narrator-facing label for a canonical era_id.
    Examples:
      earliest_years → "the years before you started school"
      early_school_years → "the early school years when you were learning to read"
      adolescence → "your adolescence"
      coming_of_age → "the years when you were coming of age"
      building_years → "the building years when you were raising a family or building a career"
      later_years → "the years after the building years"
      today → "today"
    Returns None for unknown era_id.
    """
    return _LV_ERA_WARM_LABELS.get(era_id)
```

The warm-label vocabulary should match the existing era-explainer block already in `prompt_composer.py` (the listener-arc polish landed 2026-05-04). Pull text from there to keep voice consistent.

### Addition 4 — `interview.py:_build_opener_text()` flag-gated dispatch

Modify `_build_opener_text` to call `compose_continuation_paraphrase` when the flag is on for the `welcome_back` kind:

```python
def _build_opener_text(kind: str, name: str, person_id: Optional[str] = None,
                       session_id: Optional[str] = None,
                       last_era_id: Optional[str] = None) -> str:
    """Compose the opener utterance Lori should say as her first turn."""
    safe_name = name or "friend"
    if kind == "first_time":
        return (
            f"Hi {safe_name}, I'm Lori.\n\n"
            "I'm here to help you capture your life story — the memories, "
            "the people, the places that mattered to you. There's no wrong "
            "way to do this. We can go in order of your life, or jump "
            "around to whatever you want to talk about today.\n\n"
            "What would you like to start with?"
        )
    if kind == "welcome_back":
        # WO-BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 2:
        # Flag-gated active-listening continuation paraphrase. Default OFF
        # falls through to the bare welcome-back template (Tier D-equivalent).
        if (
            os.getenv("HORNELORE_CONTINUATION_PARAPHRASE", "0") == "1"
            and person_id
        ):
            try:
                from ..prompt_composer import compose_continuation_paraphrase
                return compose_continuation_paraphrase(
                    person_id=person_id,
                    session_id=session_id,
                    last_era_id=last_era_id,
                )
            except Exception as exc:
                logger.warning(
                    "[opener] continuation paraphrase failed; "
                    "falling back to bare welcome-back: %s", exc
                )
        return f"Welcome back, {safe_name}. Where would you like to continue today?"
    return ""
```

Two argument additions to `_build_opener_text`: `person_id`, `session_id`, `last_era_id`. Caller (`get_opener`) already has `person_id` and looks up the snapshot — passes through. `session_id` and `last_era_id` come from the snapshot too (need to verify they're available; if not, surface them via the snapshot helper).

Default-off keeps the byte-stable bare welcome-back path. Flag-on enters the cascade.

### Addition 5 — `.env.example` flag entry

```
# WO-BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 2 (active-listening continuation paraphrase)
# When 1: returning-narrator opener uses compose_continuation_paraphrase
#   to surface era + last story stub + (optional) unfinished-thread
#   anchor. Reads from peek_at_memoir + lori_reflection + lv_eras.
#   Pure-deterministic, no LLM call.
# When 0 (default): bare "Welcome back, {name}. Where would you like to
#   continue today?" template fires (legacy interview.py:486-489).
# Flip to 1 only after WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c lands
# (Phase 2 Slice 2a works partially without Phase 1c — Tiers C and D only).
HORNELORE_CONTINUATION_PARAPHRASE=0
```

### Addition 6 — Tests

`tests/test_compose_continuation_paraphrase.py` (new):

```
TierSelectionTests:
  test_tier_a_full_paraphrase_with_unfinished
  test_tier_b_full_paraphrase_no_unfinished
  test_tier_c_era_only
  test_tier_d_bare_welcome_back_fallback

InputDegradationTests:
  test_no_session_id_falls_back_to_tier_c_or_d
  test_no_era_id_falls_back_to_tier_d
  test_peek_at_memoir_failure_degrades_to_tier_c
  test_anchor_extraction_returns_none_falls_to_tier_c
  test_unfinished_thread_failure_degrades_to_tier_b

DeterminismTests:
  test_same_inputs_produce_byte_identical_output
  test_no_llm_call_made (mock + assert no llm import attempted)

LawThreeTests (build-gate):
  test_no_extract_router_import
  test_no_chat_ws_import
  test_no_llm_api_import

NameFallbackTests:
  test_preferred_name_used_when_present
  test_full_name_first_token_used_when_no_preferred
  test_friend_fallback_when_no_name

VerbatimAnchorTests:
  test_story_anchor_is_substring_of_narrator_text_or_kinship_canon
  test_warm_era_label_is_lv_eras_registry_value
```

`tests/test_db_get_last_lori_question.py` (new):

```
LastQuestionTests:
  test_returns_none_when_no_session_id
  test_returns_none_when_only_one_turn
  test_returns_none_when_last_lori_was_not_a_question
  test_returns_dict_when_question_then_answer_pair
  test_answered_substantively_true_when_4plus_tokens
  test_answered_substantively_false_when_under_4_tokens
  test_answered_substantively_false_for_dont_remember_pattern
```

Goal: 30 unit tests minimum. Same testing posture as `test_shape_reflection.py` (21 tests for runtime shaping, all green).

## Acceptance gate

Slice 2a (no Phase 1c dep):
- Returning narrator with `last_era_id` set produces Tier C greeting (era only).
- Returning narrator without `last_era_id` produces Tier D bare welcome-back.
- 30 unit tests + 3 LAW 3 isolation tests all green.
- `HORNELORE_CONTINUATION_PARAPHRASE=0` produces byte-identical output to current bare welcome-back.
- TEST-23 v8 measures `era_aware_continuation_seen` ≥ 0 for both narrators (a Tier C result counts).

Slice 2b (after Phase 1c lands):
- Returning narrator with era + recent narrator turn for that era produces Tier B greeting (story anchor present).
- Returning narrator with all signals produces Tier A greeting (with unfinished thread).
- TEST-23 v8 measures `story_anchor_in_continuation` ≥ 1 for narrators who told an era story.
- No "you tole me this last time" complaints across 5+ manual switch sessions.

## Files (planned for Phase 2)

**Likely modified:**
- `server/code/api/prompt_composer.py` — new `compose_continuation_paraphrase()` function (~80 lines).
- `server/code/api/db.py` — new `get_last_lori_question_with_response_state()` accessor (~30 lines).
- `server/code/api/lv_eras.py` — new `era_warm_label()` helper + `_LV_ERA_WARM_LABELS` dict (~20 lines).
- `server/code/api/routers/interview.py` — `_build_opener_text()` gains 3 optional kwargs + flag-gated dispatch (~15 lines net); `get_opener` passes them through (~10 lines).
- `.env.example` — flag entry (~12 lines).

**New files:**
- `tests/test_compose_continuation_paraphrase.py` (~250 lines).
- `tests/test_db_get_last_lori_question.py` (~120 lines).

**Zero touch:**
- Frontend (`ui/hornelore1.0.html`, `ui/js/app.js`) — opener_text consumption is unchanged; the API contract stays the same. Tier D fallback matches current bare welcome-back so default-off is byte-stable.
- `services/peek_at_memoir.py` — read accessor unchanged; only the `summarize_for_runtime` extension lives in Phase 1c (separate WO).
- `services/lori_reflection.py` — `extract_concrete_anchor()` reused as-is, no edit.
- Memory_echo composer — separate composer; unchanged.
- Safety classifier path — unchanged.

## Risks and rollback

**Risk 1: continuation paraphrase feels wrong on certain narrators.** "Last time we were in your building years and you were telling me about Stanley" might land flat for a narrator who only mentioned Stanley once in passing. Mitigation: Tier B requires `story_anchor` to be a proper-noun phrase or kinship reference (filtered by `extract_concrete_anchor`'s scoring). Single-mention proper nouns score high enough to be picked, but if quality is poor in real testing, lower the score floor or require a multi-token anchor.

**Risk 2: era warm label feels formulaic across many sessions.** "Last time we were in the building years" repeated session after session gets stale. Mitigation: vary the connector ("Last time we were talking about" / "We were spending time in" / "We were exploring") with a small rotation set seeded by session_id hash. Phase 2 Slice 2a ships with one connector; rotation is a Slice 2c improvement if needed.

**Risk 3: unfinished thread misclassification.** A narrator who answered "Yes" to "Did you go to the prom?" (legitimate substantive answer at 1 token) might get classified as `answered_substantively=False` by the 4-token heuristic and trigger Tier A's "I asked you about... would you like to answer that now?" — feels like Lori didn't hear them. Mitigation: the 4-token threshold should be tightened with a yes/no-answer detector (single-token "yes"/"no"/"yep"/"nope" → answered substantively). Add to `db.get_last_lori_question_with_response_state` test pack.

**Risk 4: peek_at_memoir read latency on resume.** The opener endpoint is on the critical path for narrator switch; adding a DB read for `recent_turns` adds latency. Mitigation: peek_at_memoir already caps `transcript_limit=20`; add a hard 200ms timeout on the read inside `compose_continuation_paraphrase` and degrade to Tier D on timeout. Also acceptable since the alternative is the legacy bare welcome-back that doesn't read at all.

**Rollback:** flip `HORNELORE_CONTINUATION_PARAPHRASE=0`. Default-off path is byte-stable with current bare welcome-back. No data harm.

## Smoke test plan (after Phase 2 lands)

Each test takes <2 minutes.

**Test 1 — Slice 2a Tier C lands cleanly.** Mary has prior turns + `state.session.currentEra=building_years`. Switch back. Expect: "Welcome back, Mary. Last time we were in the building years when you were starting your family or career. Would you like to continue there, or start somewhere else?"

**Test 2 — Tier D fallback when era is unknown.** Test narrator with prior turns but no era set. Expect: "Welcome back, {name}. Where would you like to continue today?"

**Test 3 — Default-off byte-stability.** With `HORNELORE_CONTINUATION_PARAPHRASE=0`, all returning narrators get the legacy bare welcome-back regardless of era. Verify zero behavior change.

**Test 4 — Slice 2b Tier B (after Phase 1c).** Mary said "we used to walk to the elbow Woods on the river" during her building_years walk. Switch back. Expect Tier B greeting with `story_anchor="the elbow Woods"` (or similar — proper noun phrase from her transcript).

**Test 5 — Slice 2b Tier A (after Phase 1c).** Marvin's last Lori turn was "What was your wife's name?" and he hadn't answered. Switch back. Expect Tier A greeting with unfinished-thread reference.

## Total effort estimate

Slice 2a (no Phase 1c dep):
- Code: 4 files, ~155 lines net.
- Tests: 2 new files, ~370 lines (30 unit tests + 3 LAW 3 isolation tests).
- Smoke tests: 5 tests, ~15 minutes.

**One focused 4-hour session lands Slice 2a.**

Slice 2b (after Phase 1c lands):
- Code: small additive changes (Tier A + Tier B template paths).
- Tests: ~10 additional unit tests for Tier A/B.

**~2 hours layered on top of Slice 2a.**

## Out of scope for Phase 2

- Phase 1c implementation itself (WO-LORI-MEMORY-ECHO-ERA-STORIES-01).
- LLM-summarized continuation paraphrase (deterministic-only for Phase 2; LLM is a parked future option).
- Multi-era continuation ("Last time we covered building years AND adolescence...") — single era for v1.
- Operator-facing UI for unfinished-thread state (operator can read it via Bug Panel if exposed; not Phase 2 scope).
- Cross-session paraphrase ("Three sessions ago you told me about...") — only most-recent session for v1.
