# Phase 1A Commit 3b — Bug Sweep, 2026-04-30 evening

Performed while Chris was away after the runtime test landed
candidate `9bb91643-e2aa-49f6-bd38-b57e3a45c3e0`. Phase 1A is
LIVE in production — this is a discipline pass on what's there.

Method: own re-read of the `chat_ws.py` gated block + the
preservation lane, plus an independent code-review subagent
working from the same files. Findings reconciled below; my own
ranking, not the subagent's verbatim.

Test battery: **111 / 111 PASS** (re-run after the runtime test).
LAW 3 isolation test green. No regressions surfaced.

---

## SHIP-BLOCKERS

**None.** Phase 1A holds. The lane writes rows on real story-shaped
turns (proven). Below are real bugs but none of them put the
preservation pipeline at risk.

---

## REAL BUGS — worth a small follow-up commit

### A. SYSTEM_QF directives go through the trigger as if narrator-authored
**File:** `server/code/api/routers/chat_ws.py:220-224`

The gated block runs `trigger_diagnostic()` on any non-empty
`user_text`. UI-side `session-loop.js` emits `[SYSTEM_QF: ...]`
messages as user-role WS payloads to feed Lori in-band guidance.
These get classified just like real narrator turns.

**Live evidence:** in the runtime test session, log line at
10:56:26.759 shows `words=103 anchors=1 place=True` — that's a
SYSTEM_QF directive being scored, not narrator content. Today
no SYSTEM_QF directive happens to hit 3 anchors, so no fake rows
have landed. Tomorrow's directive could. False-positive
preservation rows are an operator-review polluter.

**Fix (one-liner):** at the gate, skip when `user_text.lstrip()`
starts with `[SYSTEM_QF` or `[SYSTEM:` or any `[SYSTEM_*` prefix.
Or check for the bracket+SYSTEM pattern explicitly.

**Severity:** real bug, low live impact today, will become
visible the moment a SYSTEM_QF directive happens to mention a
relative, a place noun, AND a time phrase. Worth the one-line
patch in a follow-up commit.

---

### B. Schema drift goes silent across `CREATE TABLE IF NOT EXISTS`
**File:** `server/code/db/migrations/0004_story_candidates.sql:14`

Migration runner says "idempotent" — and it is, for the
no-table-exists path. But if some operator has hand-created a
`story_candidates` table with a different shape (column dropped,
type changed, default missing) and then the app runs the
migration, the migration silently does nothing and the inserts
later crash with cryptic "no such column" errors.

**Fix:** at boot, after `run_pending_migrations()`, run a
`PRAGMA table_info(story_candidates);` and assert the live
columns match the expected set (or at least all the columns the
INSERT statement uses). Log a clear ERROR if they drift.

**Severity:** unlikely to bite Chris's machine right now (no
hand-edited tables), but a real risk on the laptop migration
later. ~20 lines of defensive code in `init_db`.

---

### C. `transcript` column has no soft cap
**Files:** `server/code/api/services/story_preservation.py:99-106`,
`server/code/db/migrations/0004_story_candidates.sql`

Schema accepts unbounded TEXT. If STT misbehaves and dumps a
500MB transcript into one turn, it goes straight into the row
and the `list_unreviewed` query then has to read it back. Not
a security issue, but a tail-risk operability issue.

**Fix:** add `MAX_TRANSCRIPT_BYTES = 50_000` (or similar) at the
top of `story_preservation.py`. At `preserve_turn` entry, if
`len(transcript) > MAX`, truncate with a `[...truncated]` marker
and log WARNING.

**Severity:** unlikely under normal operation; real if a STT
failure mode produces runaway output. Cheap defensive add.

---

## NICE-TO-FIX (tracked, not blocking)

### D. Dedupe path returns `existing_id` without explicit None guard
**File:** `server/code/api/services/story_preservation.py:120-124`

```python
existing_id = existing.get("id")
logger.info(...)
return existing_id  # type: ignore[return-value]
```

The schema has `id TEXT PRIMARY KEY NOT NULL` so on a valid row
this can't be `None`. But defensive coding says: if
`existing_id` is falsy, fall through to a fresh insert rather
than return None. ~3 lines.

### E. `turn_id` whitespace not normalized
**File:** `server/code/api/routers/chat_ws.py:265`

```python
_turn_id = params.get("turn_id") or None
```

`turn_id="  "` becomes `"  "`, not `None`. Dedupe lookup runs
with `"  "`, won't match anything, writes a new row. Not
catastrophic but log marker says `turn_id="  "` instead of
`turn_id=None` which is misleading. One-char fix:

```python
_turn_id = (params.get("turn_id") or "").strip() or None
```

### F. `scene_anchors` field never read in any test
**File:** `tests/test_story_preservation.py`

Column is written to on insert but no test reads it back to
confirm round-trip works. One-line addition to existing
`test_preserve_minimal`: `self.assertEqual(row["scene_anchors"], [])`.

### G. `datetime.utcnow()` deprecation
**File:** `server/code/api/services/age_arithmetic.py:168`

Already queued — Chris's standing follow-up. Replace with
`datetime.now(timezone.utc)`. One-liner.

---

## SUBAGENT FINDINGS I PUSHED BACK ON

The independent code-review subagent flagged two items I
disagree with:

**S1. "Duplicate CRITICAL logging"** — subagent ranked BLOCKER.
The story_preservation.py logger emits CRITICAL when the DB
insert fails (logs the LAW 3 violation surface), THEN re-raises;
chat_ws.py catches and logs CRITICAL again. Subagent says this
is operator noise. I disagree — both layers see different
context (preservation sees the DB call site; chat_ws sees the
session/turn metadata). The double-log is informative, not
noise. Keep as-is.

**S2. "No SQL-special character test"** — subagent suggested
adding a test for `narrator_id="kent\\'-x"` to confirm
parameterization. All queries use `?` placeholders so this is
provably safe. Test would be tautological. Skip.

---

## ALSO CONFIRMED CLEAN

- LAW 3 isolation test still passes after 3b (`test_story_preservation_isolation.py`)
- 111/111 unit tests green
- Live runtime: trigger fires correctly, preserve_turn writes,
  log markers all three present in correct order
- `confidence='low'` correctly assigned for borderline path
- `scene_anchor_count=3` matches the diagnostic log marker
- Idempotency: `turn_id=None` from UI means dedupe is opt-out by
  design — no production duplicate risk yet because every turn
  has a unique candidate_id

---

## RECOMMENDED FOLLOW-UP COMMIT

Bundle A + B + C + D + E + F + G as a single small commit named:

```
WO-LORI-STORY-CAPTURE-01 Phase 1A polish — SYSTEM_QF skip,
schema-drift guard, transcript cap, dedupe null safety,
turn_id normalization, datetime.utcnow cleanup
```

~80–100 lines of code total across 4 files. None of it changes
the working pipeline; all of it hardens edges. Worth it before
parent sessions start landing real preservation rows in volume.

Phase 1B (operator review surface) is still queued behind this.
Lane is sequenced.
