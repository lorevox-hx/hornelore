# BUG-LIFEMAP-CONTEXT-TRUNCATION-01

**Status:** OPEN — observed 2026-06-17
**Severity:** MEDIUM (silent content loss — narrator gets a clipped
response; the harness produces unreliable Life Map entries; the
clip is logged but not surfaced to the operator)
**Narrator generality:** UNIVERSAL — fires on any session whose
prompt_tokens exceed `VRAM-GUARD`'s WS truncation threshold (8192
tokens on the current MAG-Chris stack)

## Reproduction

1. Start a narrator session that has accumulated a moderate amount
   of history (any 7-era Life Map walk gets there quickly).
2. Send a chat turn carrying a long operator-side directive — e.g.
   the John Baldy Life Map era-click harness 200-word era prompts.
3. Backend `chat_ws.py` constructs the LLM input including:
   - the seeded profile_seed (~5 sources)
   - prior turn history
   - rolling summary
   - the new user turn
   - the era warm-prompt directive
4. The total exceeds the per-turn token cap. `WO-10M` VRAM-GUARD
   logs:
   ```
   [chat_ws][WO-10M] prompt_tokens=8609 max_new=512
     required=1819 MB free=7259/16303 MB guard=pass
   [VRAM-GUARD] WS truncating input from 8609 to 8192 tokens
   ```
5. Lori receives a 417-token-clipped prompt and responds. The
   narrator and operator have no visible indication the prompt was
   trimmed.

Live evidence from `.runtime/logs/api.log` 2026-06-17 11:12:10:

```
prompt_tokens=8609 max_new=512 required=1819 MB free=7259/16303 MB guard=pass
[VRAM-GUARD] WS truncating input from 8609 to 8192 tokens
```

## Diagnosis

The VRAM-GUARD truncation is a deliberate safety floor — without
it, oversized prompts OOM the GPU. The truncation strategy
(implemented in `chat_ws.py` per the 2026-04-30 BUG-DBLOCK lane and
the VRAM bench from 2026-05-03) trims the OLDEST tokens first, which
generally preserves the new user turn intact.

But the trim heuristic has no domain awareness:

1. It does not preserve the operator-side era directive (which is
   the load-bearing portion of a Life Map harness turn).
2. It does not preserve the seeded profile_seed (which is the
   load-bearing portion of every grounded warm-question turn).
3. It does not preserve the era-walk context block that the
   2026-05-03 listener-arc polish work depends on (ERA EXPLAINER
   + REFRAME RULE + GROUNDING RULE).

In a Life Map harness specifically, the harness prompt is being
prepended in the user-turn position, so the user's `Type a message`
content tends to survive intact. But the BACKEND-side composer
content (`compose_*` blocks, profile_seed, ERA EXPLAINER block) is
exactly what gets clipped — meaning Lori sees the operator's
verbose directive AND a half-truncated background context.

That's why the harness produces shaped-but-shallow responses (see
sibling BUG-LIFEMAP-COMM-CONTROL-TRIM-01) — the model has the user
turn, but not the seeded ground it was supposed to anchor to.

## Why this matters

CLAUDE.md design principle 7: *"Mechanical truth must visibly
project."* If the seeded profile_seed gets clipped out of Lori's
prompt by VRAM-GUARD, principle 7 is violated by a runtime memory
constraint rather than by code drift — Lori physically cannot see
truth that exists in the DB. That's a real failure even though
nothing crashes.

The narrator's experience: a slightly empty-feeling reply from Lori
when the prompt was supposed to land grounded. The operator's
experience: a Life Map entry that doesn't reflect the seeded facts
it should have. Neither has any visible indication WHY.

## Proposed fix

Two layers — short-term mitigation + medium-term architecture.

### Layer 1 — operator-visible warning

Surface the truncation event to the operator in real time. When
VRAM-GUARD trims a turn:

1. Emit a `[chat_ws][turn][truncated]` event over the
   operator-stack-dashboard channel
2. Bug Panel renders an amber pill: "Lori's prompt was trimmed
   by N tokens this turn. Consider shortening the operator
   directive or pruning history."
3. Eval harness picks this up via api.log and refuses to claim
   the turn as a clean test result.

### Layer 2 — domain-aware token budget

Reorder the composer's section-merging so that, when the total
exceeds the 8192 budget, the trim order is:

1. Trim rolling-summary first (it's reconstructable)
2. Trim oldest history turns second
3. Trim active-thread-bank context third
4. Trim era-warm-prompt directive ONLY as a last resort
5. Preserve profile_seed + ERA EXPLAINER + REFRAME + GROUNDING
   blocks UNCONDITIONALLY (these are load-bearing for principle 7)

Implementation lives in `chat_ws.py` and `prompt_composer.py`.
Probably 1-2 days because every composer call site needs to be
audited for which blocks are load-bearing.

### Harness-side workaround (immediate)

Chris already drafted the right immediate workaround: rewrite each
era prompt to be SHORTER — only the facts for that era, no
repeated identity blocks, no full John Map. Example for Earliest
Years:

```
Lori, Life Map era: Earliest Years.

John Baldy was born December 31, 1960, in West St. Paul, Minnesota.
His mother is still alive at 99 and lives in St. Paul, so his
earliest roots remain connected to the present.

Write one warm factual Life Map entry for Earliest Years. Do not
invent names, schools, hospitals, or emotions. End with one question.
```

That should avoid the 8609 → 8192 truncation entirely and produce
cleaner evidence on the next harness run.

## Acceptance gates

1. Re-run the John Baldy Life Map harness with the shorter era
   prompts. No VRAM-GUARD truncation lines in api.log for any of
   the 7 era turns.
2. After Layer 1 lands, when truncation DOES fire, the operator
   Bug Panel surfaces the amber pill within 2 seconds.
3. After Layer 2 lands, when truncation fires, the load-bearing
   blocks (profile_seed, ERA EXPLAINER, REFRAME, GROUNDING) are
   still in Lori's prompt — verified by adding a debug-log line
   that emits a hash of each block before send and after trim.

## Files likely touched

- `server/code/api/routers/chat_ws.py` — VRAM-GUARD trim heuristic
- `server/code/api/prompt_composer.py` — section-merging logic
- `ui/js/bug-panel-*.js` — Layer 1 amber pill
- `scripts/tail_harness_log.sh` — already filters the truncation
  warnings (banked sibling 2026-06-17)

## Related lanes

- 2026-05-03 WO-OPS-VRAM-VISIBILITY-01 Phase 5 — established the
  baseline VRAM envelope (idle 5.9 GB, normal active turn 8.0 GB,
  SPANTAG-off long prompt 8.0 GB). Truncations were assumed rare;
  this bug shows a class of operator-driven content that hits the
  cap reliably.
- 2026-04-30 BUG-DBLOCK-01 PATCH series — VRAM-GUARD trim logic
- 2026-05-03 listener-arc polish — ERA EXPLAINER / REFRAME /
  GROUNDING blocks that this trim is silently removing

## Investigation notes

Captured via `scripts/tail_harness_log.sh`. The filtered log makes
the VRAM-GUARD truncation visible without scrolling past 200 lines
of dashboard heartbeat noise.
