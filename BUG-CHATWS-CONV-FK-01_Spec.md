# BUG-CHATWS-CONV-FK-01

**Status:** CLOSED — patched 2026-06-17 (lazy plan-row seed in `ensure_interview_session`)

## Resolution

Root cause was the `plan_id="chat_ws"` default in
`db.ensure_interview_session` — `interview_plans(id)` is FK-referenced
by `interview_sessions(plan_id)`, but only the `'default'` plan row is
seeded by `init_db()`. Every `INSERT OR IGNORE INTO interview_sessions`
that used `plan_id='chat_ws'` therefore fired `FOREIGN KEY constraint
failed` because the IGNORE clause does NOT swallow FK violations (only
unique-key violations).

Patch: lazy-seed the `interview_plans` row inside
`ensure_interview_session` before the session insert. Both inserts are
idempotent (`INSERT OR IGNORE`) so this is safe to call on every turn
at zero ongoing cost after first call. Any future caller passing any
`plan_id` will Just Work.

### Files changed

- `server/code/api/db.py:ensure_interview_session` — lazy-seed plan row
- `tests/test_chatws_conv_fk_hygiene.py` — 3-test pack:
  1. `test_lazy_seeds_chat_ws_plan_row` — plan row materializes on first call
  2. `test_idempotent_multiple_calls` — N calls = 1 session row
  3. `test_increment_turn_succeeds_after_ensure` — turn_count actually advances

### Acceptance gates verified

- chat_ws full-family harness no longer logs `FOREIGN KEY constraint failed`
  on `turn_count`, `ensure_interview_session`, or `segment_flag persist`
- softened mode lifecycle (BUG-LORI-SOFTENED-MODE-PERSISTENCE-01) actually
  advances and exits after N turns
- safety segment_flag writes succeed (no FK cascade on safety path)

**Status:** OPEN — observed 2026-06-17
**Severity:** LOW (caught by try/except, logged as WARNING, does not
abort the turn — but softened-state turn counter increments are lost
and per-turn softened lifecycle math drifts)
**Narrator generality:** UNIVERSAL — fires on any conv_id created
via the narrator-switch path that hasn't been registered with the
`interview_sessions` table yet

## Reproduction

1. Switch to a narrator via the FE narrator picker. The FE generates
   a conv_id with the `switch_<random>_<random>` format
   (e.g. `switch_mqi9rego_cd2k`).
2. Send a chat turn.
3. Backend `chat_ws.py` L1054-1061 fires `ensure_interview_session`
   then `increment_session_turn`; one of those raises
   `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
4. The try/except at L1057-1061 catches the exception and logs:
   ```
   [chat_ws][softened] turn_count increment failed
   conv=switch_<...>: FOREIGN KEY constraint failed
   ```
5. Chat continues normally. Softened-state `turn_count` stays at 0.

Live evidence from `.runtime/logs/api.log` 2026-06-17 11:12:09:

```
[chat_ws][softened] turn_count increment failed
  conv=switch_mqi9rego_cd2k: FOREIGN KEY constraint failed
```

## Diagnosis

Code path: `server/code/api/routers/chat_ws.py` L1054-1056:

```python
ensure_interview_session(conv_id, person_id)
_session_turn_count = increment_session_turn(conv_id)
```

`ensure_interview_session` (db.py L2004-2043) is supposed to be
idempotent and FK-safe:

```python
INSERT OR IGNORE INTO interview_sessions(id, person_id, plan_id, ...)
```

`INSERT OR IGNORE` handles PRIMARY KEY / UNIQUE conflicts cleanly,
but **does not silence FK constraint violations** — those still
raise. So the FK that's failing is either:

1. `interview_sessions.person_id → people.id` — narrator was
   deleted or has a malformed id at the moment of insert
2. Something downstream of the insert (a trigger / cascade)
3. `increment_session_turn`'s UPDATE running against an FK that
   was satisfied a moment ago but rolled back

The most likely cause: the conv_id `switch_<...>` was first created
in some earlier path that DIDN'T call `ensure_interview_session`,
and is now associated with state in a parallel table (e.g.
softened-state rows, segment-flags) whose FK chain breaks the
insert when it finally tries.

`BUG-DBLOCK-01 PATCH 2` (2026-04-30) added the `ensure_interview_session`
call specifically to satisfy `segment_flags(session_id)`'s FK. That
PATCH was working at the time, but the `switch_*` conv_id path may
have been introduced (or changed) after the PATCH and bypasses it.

## Why this matters

Two narrow but real impacts:

1. **Softened-state lifecycle math drifts.** The softened-mode
   per-trigger `softened_until_turn` accounting in
   `WO-LORI-SOFTENED-MODE-PERSISTENCE-01` (2026-04-26 lane)
   depends on `turn_count` incrementing every turn. When the
   increment silently fails, the softened state never decays and
   either: (a) Lori stays in softened mode longer than designed,
   OR (b) the decay logic decides the state expired immediately
   because `turn_count` is still 0. Either is wrong.

2. **Telemetry noise.** Every `switch_*` narrator's session
   produces a WARNING in `api.log` per turn, polluting the eval
   harness and operator log surfaces.

The FK violation is caught, so the chat is not broken. This is a
LOW-severity bug, not a session-killer. It just steadily corrupts
the softened-mode accounting under the hood.

## Proposed fix

### Option A: Audit the switch_* conv_id path

Find where conv_ids with the `switch_` prefix originate. If they
get attached to softened-state or segment-flag rows BEFORE
`ensure_interview_session` runs, change the ordering so
`ensure_interview_session` always fires first. Most likely a fix
in either `chat_ws.py` (in the narrator-switch on-connect handler)
or in `ui/js/app.js` (in the `lvxSwitchNarratorSafe` flow that
creates the conv_id).

### Option B: Wrap ensure-and-retry around increment_session_turn

If the FK violation comes from `increment_session_turn`'s UPDATE
rather than the INSERT (because the row exists but the FK chain
into people.id was rolled back), wrap the call in a single retry
after re-running `ensure_interview_session`. Defense-in-depth only.

### Option C: Defer the increment

Catch the exception (current behavior) AND queue the increment to
retry on the next turn after the FK chain has been satisfied. Adds
complexity for marginal gain; skip unless A and B don't fix the
underlying issue.

Recommend **A** — fix the root ordering. The current try/except is
masking a sequencing bug, not a transient one.

## Acceptance gates

1. Run the John Baldy Life Map harness through 7 era prompts. Zero
   `[chat_ws][softened] turn_count increment failed` warnings.
2. After a fresh narrator switch + 5 turns, query
   `interview_sessions` for the `switch_*` conv_id — row exists
   with `turn_count = 5`.
3. Softened-mode persistence regression test pack still passes.

## Files likely touched

- `server/code/api/routers/chat_ws.py` — the switch_-handling
  on-connect path (find via `grep -n "switch_" chat_ws.py`)
- Possibly `ui/js/app.js` lvxSwitchNarratorSafe — if the conv_id
  is being constructed before any backend handshake
- `server/code/api/db.py` — only if Option B is chosen

## Related lanes

- BUG-DBLOCK-01 (2026-04-30) — the original lane that added
  `ensure_interview_session` for segment_flags FK satisfaction.
  This bug shows that fix doesn't cover the softened-state path
  for `switch_*` conv_ids.
- WO-LORI-SOFTENED-MODE-PERSISTENCE-01 — the consumer that
  depends on turn_count incrementing correctly.

## Investigation notes

Captured via `scripts/tail_harness_log.sh` (added 2026-06-17 as a
sibling of this bug). The filtered log makes the WARNING stand out
instead of being lost in dashboard heartbeat traffic.
