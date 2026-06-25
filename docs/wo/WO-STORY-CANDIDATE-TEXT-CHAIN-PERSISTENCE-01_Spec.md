# WO-STORY-CANDIDATE-TEXT-CHAIN-PERSISTENCE-01

**Status:** ACTIVE (queued behind the three behavior BUGs above)
**Severity:** LOW-MEDIUM (no narrator-facing impact; operator-side observability gap)
**Origin:** 2026-06-24 factual-chain + trip-route harness runs (D1 informational fail)
**Depends on:** none
**Blocked by (sequencing):** `BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01`, `BUG-LORI-RESPONSE-STUB-COLLAPSE-01`, `BUG-LORI-CHAIN-ANCHOR-ECHO-STRENGTH-01` (do those first)
**Blocks:** `WO-TRIP-IMPORT-AND-CLUSTER-01` (NO — trip-import work can proceed independently; this WO only affects whether text-only chain turns produce story_candidate rows)
**Locked principle:** When `factual_chain_capture.detect_factual_chain` classifies a narrator turn as a chain, the chain_meta_json MUST persist to `story_candidates` — regardless of whether the turn carries audio_duration_sec, hits the 60-word floor, or trips the 3-dimension anchor count.

---

## Why this WO exists

`WO-LORI-FACTUAL-CHAIN-CAPTURE-01` Phase 4 wired `chain_meta_json` into `story_candidates` (migration `0014_story_candidates_chain_meta.sql`). The direct preserve_turn → DB roundtrip is verified by `scripts/verify_chain_meta_persistence.py` (11/11 GREEN).

**BUT** the live chat-WS harnesses report `db_rows=0 chain_rows=0` because `story_trigger.classify_story_candidate` only fires on:

| Trigger | Gate |
|---|---|
| `full_threshold` | audio_duration_sec ≥ 30s AND words ≥ 60 AND ≥ 1 anchor |
| `borderline_scene_anchor` | ≥ 3 dimension anchors (PLACE + RELATIVE_TIME + PERSON_RELATION) |
| `rich_short_narrative` | audio_duration_sec ≥ 10s AND words ≥ 15 AND place + (person OR time) |

Text-only WS turns from typed input or Web-Speech STT carry `audio_duration_sec=None`. The borderline path requires 3 dimension anchors, which is rare — most chain turns hit ≤ 2.

Net result: factual-chain detection FIRES (composer directive lands, drift guard runs, repair shapes correctly) but the chain row is NEVER persisted to `story_candidates` for typed/Web-Speech narrators. The Phase 4 `chain_meta_json` column is dead code for that input class.

Operator-side cost: any narrator who types their session (rather than using audio capture) leaves no chain footprint in `story_candidates` for memoir export, trip-route extraction, or chain-shaped review.

---

## Goal

Add a fourth trigger path to `story_trigger.classify_story_candidate`:

```text
chain_detection — fires when factual_chain_capture.detect_factual_chain
                   returns is_factual_chain=True for the narrator turn,
                   regardless of audio_duration / words / dimension-anchors
```

When this fires, `chat_ws` calls `preserve_turn(trigger_reason="chain_detection", chain_meta=...)` with the full chain context. The row lands in `story_candidates` with `chain_meta_json` populated.

---

## Non-goals

This WO does NOT:

- Lower thresholds on the existing 3 triggers (full_threshold, borderline_scene_anchor, rich_short_narrative). Those are calibrated for audio-bearing turns and should stay.
- Change the chain_meta payload shape (locked by `WO-LORI-FACTUAL-CHAIN-CAPTURE-01` Phase 4).
- Add new schema columns (uses the existing `chain_meta_json`).
- Touch the Trip Tab feature (still parked behind import + DB WOs).

---

## Implementation strategy

### Step 1 — Extend `_VALID_TRIGGER_REASONS` in `db.py`

```python
_VALID_TRIGGER_REASONS = (
    "full_threshold",
    "borderline_scene_anchor",
    "rich_short_narrative",          # 2026-05-08 trigger
    "chain_detection",                # NEW — this WO
    "manual",
)
```

### Step 2 — Add the trigger path in `story_trigger.py`

`classify_story_candidate(transcript, audio_duration_sec=None, chain_ctx=None) -> dict`:

After the existing borderline/rich_short checks, add:

```python
if chain_ctx and chain_ctx.get("is_factual_chain"):
    return {
        "trigger": "chain_detection",
        "word_count": _word_count(transcript),
        "anchor_count": len(chain_ctx.get("anchors") or []),
        "place_anchor": chain_ctx.get("anchors")[0] if chain_ctx.get("anchors") else None,
        "time_anchor": None,
        "person_anchor": None,
    }
```

Ordering: chain_detection fires AFTER full_threshold + borderline_scene_anchor + rich_short_narrative (so audio-bearing chain turns still classify by their stronger signal).

### Step 3 — Wire from `chat_ws.py`

The existing chat_ws block (around L540) builds `_chain_ctx` BEFORE the story_trigger block runs. Pass `_chain_ctx` into `trigger_diagnostic` and `classify_story_candidate`. When the trigger is `chain_detection`, call `preserve_turn` with `chain_meta=_chain_meta_for_preserve` as already wired.

### Step 4 — Unit tests

`tests/test_story_trigger.py` — add a `ChainDetectionTriggerTest` class covering:

- Chain detected + audio_duration None → trigger=chain_detection
- Chain detected + audio_duration ≥ 30s + words ≥ 60 → trigger=full_threshold (stronger signal wins)
- Chain NOT detected + short text → trigger=None
- chain_ctx with `is_factual_chain=False` → no chain_detection trigger

### Step 5 — Live harness re-verification

After landing:

- `scripts/run_factual_chain_live_harness.py` D1 row should now PASS (chain_meta rows land for T1/T2/T3/T4/T6)
- `scripts/run_trip_route_canary_harness.py` D1 row should also PASS

Both harnesses' D1 hard-clamp removal (done in the 2026-06-24 honest-scoring iteration) means D1 newly PASSing only adds to the GREEN count — doesn't change verdict logic.

---

## Acceptance criteria

The WO is closed when:

```text
1. tests/test_story_trigger.py ChainDetectionTriggerTest all GREEN
2. scripts/verify_chain_meta_persistence.py still 11/11 GREEN
3. scripts/run_factual_chain_live_harness.py D1+D2 informational
   rows now PASS (db_rows ≥ floor(chain_turns × 0.5))
4. scripts/run_trip_route_canary_harness.py D1+D2 informational
   rows now PASS
5. No regression on existing trigger types (full_threshold /
   borderline_scene_anchor / rich_short_narrative continue to
   fire on their own terms — chain_detection only fires when
   THOSE don't)
6. story_candidates rows with trigger_reason='chain_detection'
   carry chain_meta_json populated per Phase 4 contract
```

---

## Stop conditions

Stop and reassess if:

- chain_detection trigger fires too aggressively (every typed narrator turn produces a story_candidate row, bloating operator review).
- The trigger conflicts with existing extraction or memoir-export downstream consumers that key off trigger_reason.
- Schema changes prove necessary beyond the existing chain_meta_json column.

---

## Files likely to touch

```text
server/code/api/db.py                       — extend _VALID_TRIGGER_REASONS
server/code/api/services/story_trigger.py   — Step 2 chain_detection path
server/code/api/routers/chat_ws.py          — pass _chain_ctx through
tests/test_story_trigger.py                 — Step 4 unit tests
```

No new migration needed — `chain_meta_json` column already exists.

---

## Sequencing note

This WO is queued behind the three behavior BUGs (deep-route drift, stub-collapse, anchor-echo strength). Chris's 2026-06-24 sequencing rule: the conversation layer must be stable BEFORE adding more persistence paths. If a chain detection produces a Spanish-drifted Lori response, persisting that row to `story_candidates` just makes the operator review surface dirty.

Once BUGs #1-3 are GREEN, this WO can land in a single session.

---

## Revision history

- 2026-06-24 — Created from D1 informational failure on both 2026-06-24 live harnesses; queued behind 3 behavior BUGs per Chris's sequencing rule.
