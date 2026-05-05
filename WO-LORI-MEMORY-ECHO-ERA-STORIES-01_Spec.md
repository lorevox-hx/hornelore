# WO-LORI-MEMORY-ECHO-ERA-STORIES-01 — Era-story recall in the memory_echo readback

**Status:** SCOPED — narrow extension of SESSION-AWARENESS-01 Phase 1c
**Date:** 2026-05-05
**Lane:** Lori behavior. Sub-WO of WO-LORI-SESSION-AWARENESS-01 Phase 1c (task #284).
**Source:** TEST-23 v5 readout + ChatGPT diagnosis (2026-05-05). Live evidence: Marvin walked all 7 eras during the lifemap walk telling Lori about his time at the aluminum plant, his marriage, his wife's death — none of that surfaced when he asked "what do you know about me."
**Blocks:** Nothing critical. Parent-session readiness is closed without this — Janice and Kent care that Lori greets them by name and listens, not that she summarizes their life stories back word-for-word. This WO is the next layer of warmth.
**Companion:** WO-LORI-SESSION-AWARENESS-01 Phase 1c (umbrella), `services/peek_at_memoir.py` (read accessor, already exists), `prompt_composer.compose_memory_echo` (where the readback is composed).

---

## The gap (ChatGPT-diagnosed, locked)

```
Era-click navigation:    WORKING (GREEN)
   Lori asks era-specific questions when an era is clicked.

Era-story readback:      MISSING (RED)
   When the narrator asks "what do you know about me," the readback
   shows Identity + Family + Notes (slot-shaped) but never surfaces
   the stories the narrator actually told Lori during the era walk.
```

The TEST-23 harness's `era_stories_in_readback` metric (renamed
2026-05-05 from `era_facts_recalled` to remove ambiguity) measures
exactly this: walks the readback for 1+ token from each era's expected
fact set; counts hits / 7 total. Mary v5 = 0/7. Marvin v5 = 0/7.

Both narrators told Lori specific era-shaped content:
- Mary: "I was born in Minot in 1940. The war was on but my mother said the prairie felt safe..."
- Marvin: "Bismarck High School, class of '67. I worked summers at the aluminum plant..."

None of that lives in `profile_seed`, `projection_family`, or `promoted_truth`. It lives in the session transcript — and the session transcript IS already read by `peek_at_memoir.recent_turns`. The composer just doesn't render it.

---

## Mission

Make `compose_memory_echo` show the narrator their own era stories. One short excerpt per era they've spoken about. Pulled from session transcript only. Never invented.

```
Sample readback (target shape after this WO lands):

What I know about Mary Holts so far:

Identity
- Name: Mary
- Date of birth: 1940-02-29       (after BUG-EX-DOB-LEAP-YEAR-FALLBACK)
- Place of birth: Minot, North Dakota  (after BUG-EX-POB-CORRECTION)

Family
- Parents: (none on record yet)
- Siblings: (none on record yet)

What you've shared so far                        ← NEW SECTION
- Earliest Years (Minot): the war was on but the prairie felt safe
- Early School Years: walking three blocks to the brick schoolhouse
- Adolescence: ...
[etc. — one entry per era the narrator has spoken about]

What I'm less sure about
- Some parts are still blank, and that is completely fine.
[...]
```

The new section is named "What you've shared so far" — narrator-facing
language, not "Era stories" or "Recent turns" (system-tone vocabulary).
Each entry pairs the warm era label with one sentence of the
narrator's own words, paraphrased to fit. The sentence is **excerpted
from narrator transcript text**, never generated from scratch.

---

## Locked design rules

1. **Pulled from narrator text only.** Lori never generates new biographical content for the readback. The excerpt is a contiguous span from the narrator's own utterance, verbatim or with minimal trimming (drop trailing fragments, drop "and then I" connector tails). Same posture as BUG-LORI-REFLECTION-02 anchor extraction.

2. **One entry per era maximum.** If the narrator spoke about Earliest Years across 3 turns, pick one excerpt — the highest-scoring per `_score_excerpt_for_era()` heuristic. No multi-paragraph era summaries.

3. **Era binding from `state.session.currentEra` at write-time.** Each transcript turn captures the active era when the user message lands. Bind via `archive.add_turn(turn_id, ..., currentEra=...)`. New turns get the binding; old turns without it skip.

4. **Safety filter wins.** `peek_at_memoir.recent_turns` already runs through `safety.filter_safety_flagged_turns()` — that filter applies before era-binning. Sensitive turns never reach the readback.

5. **No LLM call.** The composer is deterministic. Excerpt selection + trimming is regex + word-count math. The next iteration could LLM-summarize, but Phase 1 ships without LLM dependency.

6. **Default-OFF behind a flag.** `HORNELORE_MEMORY_ECHO_ERA_STORIES=0` for the first eval cycle. After two clean TEST-23 runs showing `era_stories_in_readback ≥ 4/7` for both narrators, flip default to `1`.

---

## Architecture (three layers)

### Layer 1 — Era binding at archive write-time

`server/code/api/archive.py` — extend `add_turn()` to accept and persist `current_era` (canonical era_id) on each turn record. Reads from `state.session.currentEra` (canonicalized via `lv_eras.legacy_key_to_era_id`).

```python
def add_turn(
    person_id: str, session_id: str, turn_id: str,
    role: str, content: str,
    *,
    current_era: Optional[str] = None,   # NEW
    ...
) -> None:
    """...
    current_era: canonical era_id (earliest_years / early_school_years /
                 adolescence / coming_of_age / building_years /
                 later_years / today). When the active era is unknown
                 at write time, pass None — the turn is filed without
                 era binding and won't appear in era-grouped readback.
    """
```

UI side: `chat_ws.py` already threads `runtime71.current_era` through. Plumb it into the `archive.add_turn` call. Backward-compatible — old turns without `current_era` are still readable; they just don't bin into era groups.

### Layer 2 — Era binning in peek_at_memoir.summarize_for_runtime

Extend `summarize_for_runtime()` to return turns grouped by era:

```python
out["recent_turns_by_era"] = {
    "earliest_years": [{"text": "...", "ts": "..."}, ...],
    "early_school_years": [...],
    ...
}
```

Pure rebinning of `recent_turns` by their `current_era` field. Empty era buckets are omitted. Within each bucket, retain chronological order.

### Layer 3 — Render in compose_memory_echo

Add a new section between "Notes from our conversation" and "What I'm less sure about":

```python
# WO-LORI-MEMORY-ECHO-ERA-STORIES-01 — render era stories when peek
# data is present and the era-stories flag is on. One excerpt per
# era that has at least one user-role turn.
if (
    _era_stories_enabled()
    and isinstance(peek_data, dict)
    and peek_data.get("recent_turns_by_era")
):
    era_excerpts = _select_era_excerpts(peek_data["recent_turns_by_era"])
    if era_excerpts:
        lines.extend(["", "What you've shared so far"])
        for era_id, excerpt in era_excerpts:
            warm_label = era_id_to_warm_label(era_id)
            lines.append(f"- {warm_label}: {excerpt}")
```

`_select_era_excerpts(by_era_dict)`:
- For each era key, walk the user-role turns in chronological order.
- Pick the **first non-trivial** turn (≥ 8 content tokens).
- Excerpt the first sentence, capped at 80 chars, ending at the nearest sentence boundary.
- Strip leading "Well, ", "I think, ", "Um, " filler.
- Skip the era entirely if no turn qualifies.

Excerpt shape rules (locked):
- Verbatim or near-verbatim from narrator text
- Single sentence
- ≤ 80 chars (Lori's readback line shouldn't wrap on a typical desktop)
- No trailing connectors ("and then", "but anyway", "so")
- Narrator pronoun rewrites: "I was" → "you were", "my mother" → "your mother" (kinship rewrite reuses `lori_reflection._KINSHIP_CANON` with possessive flip)

---

## Phase plan

### Phase 1 — Layer 1 era binding (archive write path)

Add `current_era` column to the turns table (or to the turn-row JSON
blob if turns are stored as JSON). Wire `chat_ws.py` to pass
`runtime71.current_era` into `archive.add_turn()`. Write a migration
that backfills `current_era=null` for historical turns.

**Files:** `server/code/api/archive.py`, `server/code/api/routers/chat_ws.py`, optionally `server/code/db/migrations/000X_turn_current_era.sql`.

**Acceptance:** A turn written via chat_ws with the lifemap walk active gets `current_era=earliest_years` (or whatever's active) in its archive row. Backward-compat — old turns read back as `current_era=null` and skip era-grouping.

**Scope:** ~half day.

### Phase 2 — Layer 2 era binning in peek_at_memoir

Add `recent_turns_by_era` field to `summarize_for_runtime()` output.
Pure server-side; no UI changes.

**Files:** `server/code/api/services/peek_at_memoir.py`, `tests/test_peek_at_memoir.py`.

**Acceptance:** Mock transcript with 6 turns spanning 3 eras → output has `recent_turns_by_era` keyed by 3 era_ids, each list ordered chronologically. Empty when no turns carry era binding.

**Scope:** ~half day.

### Phase 3 — Layer 3 render in compose_memory_echo

Add `_select_era_excerpts()` + the rendering block. Default-OFF behind `HORNELORE_MEMORY_ECHO_ERA_STORIES=0`.

**Files:** `server/code/api/prompt_composer.py`, `tests/test_compose_memory_echo_era_stories.py`.

**Acceptance:** Mock peek_data with `recent_turns_by_era` populated → readback contains a "What you've shared so far" section with one entry per non-empty era. When flag is off, readback is byte-stable to current.

**Scope:** ~1 day (excerpt-selection heuristic + pronoun rewrite + tests).

### Phase 4 — Live verify + flag flip

Run TEST-23 v7+ with `HORNELORE_MEMORY_ECHO_ERA_STORIES=1` AND `HORNELORE_PEEK_AT_MEMOIR_LIVE=1` (the existing peek-at-memoir gate). Expected: `era_stories_in_readback ≥ 4/7` for Mary AND Marvin. Two consecutive clean runs → flip default to 1 in `.env.example` + CLAUDE.md changelog entry.

**Scope:** ~half day (including the eval runs).

---

## What this WO does NOT do

- **Add memoir-style summarization.** That's a future iteration. This WO surfaces the narrator's own words; doesn't paraphrase or condense beyond first-sentence excerpting.
- **Touch promoted_truth.** Phase 1c-of-SESSION-AWARENESS-01 already covers promoted_truth → readback. This WO is the parallel era-stories lane.
- **Build a "story preservation" surface.** That's WO-LORI-STORY-CAPTURE-01 territory (already partly landed for full preservation; era stories in readback is just the read view).
- **Solve the era-binding-on-old-turns problem.** Backfill is null. Migration only adds the column. Old turns silently drop from era grouping.
- **Modify the era-click path.** That's working per ChatGPT's diagnosis. No changes to interview.js / app.js click handlers.

---

## Acceptance gates (per phase)

```
Phase 1  [ ] archive.add_turn writes current_era when supplied
         [ ] chat_ws threads runtime71.current_era through
         [ ] read_transcript returns turns with current_era field
         [ ] migration runs cleanly; old turns get NULL

Phase 2  [ ] summarize_for_runtime returns recent_turns_by_era
         [ ] empty era buckets omitted
         [ ] safety filter still applies (no sensitive turns leak in)
         [ ] unit tests pass

Phase 3  [ ] HORNELORE_MEMORY_ECHO_ERA_STORIES=0 → byte-stable to current
         [ ] flag=1 + peek_data with era turns → "What you've shared
             so far" section renders with one entry per non-empty era
         [ ] excerpt selection picks first non-trivial turn
         [ ] excerpts capped at 80 chars, end at sentence boundary
         [ ] kinship rewrite: "my dad" → "your dad" / "your father"
         [ ] no era entry when era has no user turns
         [ ] unit tests pass

Phase 4  [ ] TEST-23 with flag ON: era_stories_in_readback ≥ 4/7
             for both Mary AND Marvin
         [ ] No regression in identity/family/notes sections
         [ ] Two consecutive clean runs
         [ ] .env.example default flipped
         [ ] CLAUDE.md changelog entry banked
```

---

## Risk + rollback

**Risk 1: Excerpt picks wrong sentence (off-topic chunk of narrator text).**
Mitigation: select first non-trivial turn, first sentence; cap at 80 chars; prefer sentences containing era-anchor tokens (place names, kinship terms).
Rollback: flag default-OFF — toggle returns to byte-stable.

**Risk 2: Pronoun rewrite reads wrong (e.g., "you were a teacher" when narrator was talking about their parent).**
Mitigation: Phase 3 leaves pronoun rewrite OPTIONAL behind a sub-flag. Ship without rewrite first; add rewrite only if Phase 4 evidence supports it.
Rollback: revert the rewrite block; excerpts render verbatim with first-person pronouns.

**Risk 3: Old turns without era binding silently drop.**
Mitigation: documented behavior. Backfill is out of scope; running narrators get era binding starting from Phase 1 land date forward.
Rollback: N/A — there's nothing to roll back; the absence of data isn't a regression.

**Risk 4: Safety-filtered turn leaks via the era binding path.**
Mitigation: era binning happens AFTER `peek_at_memoir.recent_turns` already filtered. The architecture forces the safety filter through.
Audit: Phase 2 unit test verifies a turn with sensitive segment_flag is dropped before era binning sees it.

---

## Sequencing relative to other lanes

```
SESSION-AWARENESS-01 Phase 1b (LANDED 2026-04-29) — memory_echo
                                                     reads from profile +
                                                     runtime71. Identity
                                                     section works.
                                                     ↓
WO-PROVISIONAL-TRUTH-01 Phase A (LANDED 2026-05-04) — Identity section
                                                       surfaces provisional
                                                       values from
                                                       projection_json.
                                                       ↓
TEST-23 v5 evidence (2026-05-05)                  — Identity verified
                                                     working live; era
                                                     stories confirmed
                                                     missing.
                                                     ↓
WO-LORI-MEMORY-ECHO-ERA-STORIES-01 (this WO)      — Add era-story
                                                     section to readback.
                                                     Three-layer build,
                                                     default-OFF.
                                                     ↓
SESSION-AWARENESS-01 Phase 1c proper (parked)     — Promoted truth
                                                     enrichment via
                                                     peek-at-memoir
                                                     (separate lane,
                                                     same module).
```

---

## What goes into CLAUDE.md changelog when this WO lands

Single dated entry:
- Phase 1+2+3 landed (archive era-binding + peek_at_memoir era-grouping + composer render)
- Default-OFF on flag, byte-stable until live verify
- TEST-23 v_n result vs v5 baseline (era_stories_in_readback delta)
- Locked outcome: narrators see their own era stories in the readback
- Sub-flag for pronoun rewrite captured if shipped Phase 3+ with it
