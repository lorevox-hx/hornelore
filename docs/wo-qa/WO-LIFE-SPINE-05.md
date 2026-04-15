# WO-LIFE-SPINE-05 — Phase-aware question composer

## Status: SHIPPED (dark — flag OFF until post-test activation)

## Purpose

Replace strict sequential DB ordering of interview questions with
phase-appropriate selection from `data/prompts/question_bank.json`.
Goal: when a narrator jumps from early_adulthood to legacy_reflection,
the NEXT question is legacy-appropriate, not whatever happens to be
next in the ordinal plan.

## Design

`server/code/api/phase_aware_composer.py` — pure stateless module.

### Data flow

```
narrator DOB  ──┐
                ├──► current_age ──► phase_for_age ──► phase_id
today (test)  ──┘                                            │
                                                             ▼
asked_keys ──► pick_next_question(phase_id, asked_keys) ──► question
```

Composer has NO session state. Callers pass `asked_keys` — a set of
`"phase:sub_topic:q_index"` strings derived from the session's answer
history. This keeps the module trivially testable and makes it
impossible for a stale cache to affect two different narrators.

### Question bank lookup

1. Bank loaded once per process, cached in `_BANK_CACHE`. `reload_bank()`
   busts the cache (tests and operators use it).
2. Location resolution walks up from this module's path; env override
   `HORNELORE_QUESTION_BANK_PATH` for non-standard layouts.
3. Malformed JSON or missing file → load returns None → composer
   returns None → caller falls back to sequential DB flow.

### Phase resolution

Bank phases carry `age_range: [min, max]`. First phase whose range
contains the narrator's current age wins. Phase order in JSON is
life-order, so the first-match rule is deterministic.

### Spine-anchor reachability

Some sub-topics are anchored to life events (e.g., `autonomy_milestones`
→ `civic_drivers_license_age`). A narrator younger than the envelope's
`min_age` has those sub-topics filtered out. Single source of truth:
the validator's `_AGE_ENVELOPES`. This prevents asking a 6-year-old
about their first driving lesson even if `phase_override` forces the
teen phase.

## Integration

`interview.py` wraps `db.get_next_question()` on both `/start` and
`/answer` endpoints:

```python
next_q = db.get_next_question(...)
if flags.phase_aware_questions_enabled():
    pa = _phase_aware_next_question(session_id, person_id)
    if pa is not None:
        next_q = pa  # override with phase-aware pick
```

`_phase_aware_next_question` fetches DOB from profile, builds
`asked_keys` from the session's answer history (`qb:*` prefixed question
IDs), and asks the composer for the next question. Any failure returns
`None` → caller continues with sequential DB flow. Never raises.

### Asked-key tracking

Questions returned by the composer have IDs of the form
`qb:<phase>:<sub>:<idx>`. When the narrator answers one, `add_answer`
writes that ID into `interview_answers.question_id`. Next call,
`_asked_keys_for_session` pulls all `qb:*` rows and strips the prefix
to rebuild the asked set. No new table, no schema migration.

## Activation

```bash
# .env
HORNELORE_PHASE_AWARE_QUESTIONS=1
```

Default is `0`. Flag is independent of the age validator — you can run
either one alone.

## Tests

`tests/test_phase_aware_composer.py` — 12 unit tests:

- Bank loads and contains 5 phases
- `current_age` handles birthday boundary
- `phase_for_age` maps 63 → legacy, 8 → developmental, 15 → adolescence
- `pick_next_question` returns None without DOB
- Returns phase-appropriate question for a teen
- Skips already-asked questions on second call
- Honors `phase_override`
- Response dict matches `db.get_next_question` shape (id, section_id,
  ord, prompt)
- Spine-anchor reachability: too-young narrator in forced phase doesn't
  see questions gated by anchors they can't reach

All 12 pass.

## Tomorrow's test plan

Flag stays OFF. Tomorrow we test the unchanged sequential flow with the
new life-spine ghosts and the extractor west-Fargo fix.

After that test passes, to activate:

1. Flip `HORNELORE_PHASE_AWARE_QUESTIONS=1`
2. Restart the API
3. Start a fresh interview session for a narrator with DOB (Chris or
   Lori)
4. Verify first question comes from the bank (`qid` starts with `qb:`)
5. Verify it's phase-appropriate (for a 63-year-old narrator: should be
   from `legacy_reflection` phase)
6. Answer it, confirm next question is from the bank too and isn't the
   same one

## Open decisions / future work

- **Phase advancement**: currently composer returns None when the
  current phase is exhausted. Caller then falls back to sequential.
  Future enhancement: cycle narrator back through earlier phases they
  may have missed, or allow operator to force a specific phase.
- **Question bank review**: the 99 questions and 75 follow-ups were
  drafted by Claude from the 5-phase framework. They need a voice-pass
  before production use to confirm they sound right for Horne-family
  narrators. Content is cheap to revise; this is low-risk to postpone.
- **Follow-up surfacing**: composer returns `_meta.follow_ups` but the
  interview router does not yet surface them. Wiring deepeners is a
  separate small WO.
- **Extract priority hints**: `_meta.extract_priority` lists field paths
  the extractor should prioritize. Not yet consumed. Future: pass these
  as a hint to `/api/extract-fields` so the LLM knows which fields to
  watch for given the current question.
