# Silence-Cue Dead-Code Audit — 2026-05-03

## Context

Lane A (2026-05-03 evening) added a single chokepoint gate at the top
of `lv80FireCheckIn()` in `ui/hornelore1.0.html` that suppresses all
downstream silence-prompt injectors when `LV_ATTENTION_CUE_TICKER ===
true`. The gate fires `[lv80-turn-debug] {event:"idle_fire_blocked",
reason:"phase3_visual_cue_active"}` and returns early.

Question: now that the gate is in place, are any of the suppressed
prompt variants dead code worth deleting outright (vs kept as
fallback for the default-OFF ticker case)?

## Inventory — 10 silence-prompt variants currently in tree

### WO-10C cognitive-support escalation (long silences, 5min + 10min)

Defined inline in `lv80FireCheckIn()` itself at lines ~6128-6143:

| # | Stage | Trigger | Prompt | Status |
|---|---|---|---|---|
| 1 | Stage 2 (gentle invite) | ~5min silence + CSM mode | "The narrator has been quietly present for several minutes..." | KEEP — load-bearing for cognitive-support narrators per WO-10C spec |
| 2 | Stage 3 (re-entry bridge) | ~10min silence + CSM mode | "The narrator has been quietly present for a long time..." | KEEP — final bridge before infinite-patience mode |

**Audit verdict:** keep both. WO-10C is a separate spec from Phase 3
and the only thing that changed is "Phase 3 visual cue replaces this
when ticker is on." Default-OFF preserves CSM behavior.

### WO-10B standard idle ladder (4 postures × 3 modes — 10 active variants)

Defined in `promptsByPosture` dict at lines ~6190-6206:

| # | Posture | Mode | Prompt key | Status |
|---|---|---|---|---|
| 3 | life_story | open | "narrator has been quiet for a while..." | KEEP — primary fallback |
| 4 | life_story | recognition | "...orienting prompt in recognition mode..." | KEEP — used by cognitive-auto recognition path |
| 5 | life_story | alongside | "...quiet presence — one very soft sentence..." | KEEP — used by cognitive-auto alongside path |
| 6 | memory_exercise | open | "...gentle, open-ended recall prompt..." | **FLAG** — see below |
| 7 | memory_exercise | recognition | "...very simple orienting question..." | **FLAG** — see below |
| 8 | memory_exercise | alongside | "...take your time, whenever you're ready..." | **FLAG** — see below |
| 9 | companion | open | "...presence check-in — no memoir questions..." | KEEP — referenced by `_lv80GetInteractionMode()` non_memoir collapse |
| 10 | companion | recognition | "...one simple, warm sentence..." | KEEP |
| 11 | companion | alongside | "...only quiet presence..." | KEEP |
| 12 | non_memoir | (single) | "...neutral check-in — no pressure, no memoir questions..." | KEEP — explicit non_memoir branch in `lv80FireCheckIn` |
| 13 | safety | (always null) | (never fires by design) | **DEAD-AS-DESIGNED** — keep the null sentinel |

### memory_exercise FLAG (rows 6-8)

Per task #257 (completed): "Remove memory_exercise from sessionStyle
picker (keep posture system)". The picker UI no longer offers it,
but the underlying posture system still routes through it. Practical
effect: `_lv80GetInteractionMode()` can still return `"memory_exercise"`
if `state.session.sessionStyle === "memory_exercise"` is set
programmatically (e.g. via legacy localStorage state or test
fixtures).

**Audit verdict on memory_exercise rows 6-8:** keep them in tree as
defensive fallback. Deleting them would crash any narrator that
hits the path with a stale `memory_exercise` sessionStyle. The
Lane A gate already silences them when Phase 3 ticker is on.

If `memory_exercise` is fully retired in a future cleanup (e.g.
removing the posture from `_LV80_MC_MAP`), THEN these prompts can
be deleted. Until then: keep + comment.

## Decision

**No prompts deleted. All 10 active variants preserved as default-OFF
fallback.** Lane A's chokepoint gate is the structural retirement
mechanism — when `LV_ATTENTION_CUE_TICKER === true`, none of these
fire regardless. When `false`, existing WO-10B / WO-10C behavior runs
unchanged.

Per Chris's locked principle (2026-05-03 pre-Phase-3 commit): "No new
Lori speech paths until Phase 5. This commit removes ONE path (when
ticker is on) and adds zero. The Phase 5 test matrix is the only
future gate that may reactivate spoken cues."

Translating to deletion policy: deletion of any of these 10 variants
**must wait for Phase 5 test-matrix evidence** that the visual presence
cue alone is sufficient across all postures + modes + cognitive-support
narrators. Until then, ticker-off fallback preservation is the right
call.

## What CAN be deleted in a future cleanup pass

Once Phase 5 test matrix locks `visual_only` as the parent-session
default + the ticker is moved to default-ON in `.env`/bootstrap:

1. The two WO-10C inline prompts (rows 1-2) become candidates IF the
   Adaptive Silence Ladder (Phase 4) covers the 5min + 10min long-
   silence cases with visual-only behavior.
2. The 10 WO-10B prompt variants (rows 3-12) become candidates IF the
   Phase 3 visual cue is sufficient for ALL postures in real
   parent-session evidence.
3. The `safety: null` sentinel (row 13) can be deleted as soon as
   `lv80FireCheckIn` early-returns on safety mode at the top
   (which is already the case via `_lv80GetInteractionMode()` →
   `"safety"` path returning before the prompt dict lookup).

None of these deletions should land before Phase 5.

## Audit footprint

- Lines audited: ui/hornelore1.0.html L6073-6225 (lv80FireCheckIn
  function body)
- Variants inventoried: 10 active + 1 inline-null + 2 WO-10C
  inline-staged
- Variants deleted: 0
- Variants flagged for future review (post-Phase-5): 13
- Files changed: 0 (audit-only)

## Cross-references

- **Lane A** (2026-05-03 evening) — `lv80FireCheckIn` chokepoint gate
- **Phase 3** (2026-05-03) — visual presence cue + dispatcher / ticker
- **Phase 5** (parked) — test-matrix-gated spoken-cue activation
- **Task #257** (completed 2026-04 timeframe) — memory_exercise
  removed from sessionStyle picker but kept in posture system
- **WO-10C spec** — cognitive-support staged-escalation invariants
- **WO-10B spec** — standard no-interruption idle ladder
