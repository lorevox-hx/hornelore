# WO-PROMPT-BLOAT-AUDIT-01 — System Prompt Bloat Audit & Reduction

**Status:** ACTIVE Phase 0 (audit only — no behavior change)
**Origin:** rehearsal_quick_v5 + long_life_v2 (2026-05-04) — Life Map era-click turns logged `prompt_tokens=5675` for a SINGLE chat turn, pushing LLM response time past the 45s harness timeout and producing false-RED on era-click probes.
**Related lanes:** Lane 1 (era-click timeout 45s→90s, LANDED 2026-05-04) is a band-aid; this WO is the real fix. BUG-CHATWS-SWITCH-CONV-FK-01 is sibling but independent.
**Sequencing:** runs in parallel to Lane 1's verification + Lane 3 (switch_* FK fix).

---

## Problem statement

**Live evidence — single Lori chat turn = 5,675 prompt tokens.**

Two consecutive turns from `master_loop01` api.log on 2026-05-04 08:33-08:34:

```
[chat_ws][WO-10M] prompt_tokens=5675 max_new=512 required=1466 MB free=6181/16303 MB guard=pass
[chat_ws][WO-10M] prompt_tokens=5543 max_new=512 required=1448 MB free=5299/16303 MB guard=pass
[chat_ws][WO-10M] prompt_tokens=5651 max_new=512 required=1463 MB free=5703/16303 MB guard=pass
[chat_ws][WO-10M] prompt_tokens=3898 max_new=512 required=1217 MB free=3699/16303 MB guard=pass
[chat_ws][WO-10M] prompt_tokens=3824 max_new=512 required=1207 MB free=4137/16303 MB guard=pass
```

Range across 5 consecutive turns: 3,824–5,675 tokens. Mean ~4,918. **No single chat turn should need 5K+ tokens of system prompt context.** This bloats latency, increases hallucination risk, and pushes the stack closer to VRAM ceiling.

**Direct narrator-impact consequences:**

1. **Slower replies.** At Llama-3.1-8B-Q4 / RTX 5080, generation runs ~50-70 tok/s. Prompt processing for 5,675 tokens at ~2,500 tok/s adds ~2.3s before the first generated token. A typical Lori reply now takes 15-25s instead of 5-10s. For older narrators with short attention windows, the perceived "Lori is slow" feel matters.
2. **Higher chance of LLM losing thread.** Long context windows dilute the most recent turn's salience; the model wanders into earlier transcript or restated directive content.
3. **VRAM pressure climbs faster.** WO-10M guard checks `required` MB against `free`; today's guard passed by ~5-6 GB margin, but as the prompt grows, that margin shrinks. A 7-8K prompt could start tripping the guard during multi-voice loops.
4. **Harness timing assumptions break.** Lane 1 just bumped era-click timeout from 45s → 90s as containment; bloat is the actual cause.

---

## Phase 0 — Audit (this WO)

**Goal:** identify what's contributing to the 5,675-token system prompt for a single chat turn. Survey only — no behavior change, no flag flips, no edits to `prompt_composer.py`.

**Approach:** instrument `prompt_composer.py` to emit per-block token counts at INFO level, run a controlled probe scenario (single narrator, no voice loop, single turn), and produce a per-block breakdown.

### Phase 0.1 — Per-block token counter

Add a single instrumentation log in `server/code/api/prompt_composer.py` at the END of `compose_system_prompt()` (or whatever the master composer entry point is) that emits:

```
[prompt-composer][bloat-audit] turn_mode=interview composed_total=5675
  block_breakdown:
    base_identity=320
    safety_rules=180
    interview_discipline=240
    memory_echo_profile_seed=890
    bb_blob_summary=1240
    transcript_history=2120
    era_directive=205
    voice_library_directive=0
    narrative_cue_directive=0
    other=480
```

Implementation notes:
- Use `tiktoken` if available, else fall back to `len(text.split())*1.3` rough estimate. Both should converge within ~5%.
- Gate behind `HORNELORE_PROMPT_BLOAT_AUDIT=0` env flag, default-OFF. When OFF, byte-stable with current behavior.
- Single-line per-prompt log marker; do not pollute api.log under default settings.
- Log marker: `[prompt-composer][bloat-audit]` so we can `grep` cleanly.

### Phase 0.2 — Controlled probe scenario

Run a 3-turn synthetic conversation against a freshly-created narrator (no preceding voice loop, no transcript history) with `HORNELORE_PROMPT_BLOAT_AUDIT=1`:

1. **Turn 1:** narrator says `"hello how are you"` → Lori replies
2. **Turn 2:** narrator says `"I was born in 1962"` → Lori replies
3. **Turn 3:** narrator clicks Coming of Age era → Lori replies (sendSystemPrompt)

Expected per-turn breakdown patterns:
- T1 should be smallest (fresh narrator, no transcript, no era directive)
- T2 adds 1 turn of transcript history
- T3 adds 2 turns of transcript history + era directive

Goal: identify which block dominates and how it scales.

### Phase 0.3 — Audit report

Author `docs/reports/PROMPT_BLOAT_AUDIT_2026-05-04.md` with:
- Per-block contribution percentages
- Scaling behavior across T1/T2/T3
- Top 3 reduction targets ranked by `(token_count × likelihood-of-bloat)`
- Recommendations for Phase 1 (which block to trim first, expected savings)

---

## Phase 1 — Reduction (separate session, after Phase 0 lands)

**Top suspected bloat sources (to be confirmed by Phase 0 data):**

### Suspect #1 — Transcript history

The era-click turn fired AFTER 6 hearth voice-loop turns of accumulated context. If the composer is including full transcript text (not summarized), 6 turns of typical narrator+Lori dialogue (~150 words/turn × 6 = ~900 words = ~1,200 tokens) is plausible.

**Reduction options:**
- Cap transcript history at last 3 turns by default (drop from 6+ → 3)
- Summarize older turns into a single 50-word digest line
- Drop transcript from system prompt entirely; rely on conversation_history field in chat-completion API

### Suspect #2 — Memory echo profile_seed

SESSION-AWARENESS-01 Phase 1b-minimum (#327, landed) injects `profile_seed` into memory_echo composer. If profile_seed is being injected on EVERY turn (not just memory-echo turns), and includes full BB blob fields, easy 800-1,200 tokens of dead weight.

**Reduction options:**
- Restrict profile_seed to memory_echo turn_mode only (not interview / clear_direct turns)
- Truncate to top-5 most-recently-touched fields
- Replace verbose "(not on record yet)" placeholders with a single line summary

### Suspect #3 — BB blob summary

The composer may be loading the full BB blob and rendering it as JSON or YAML in the prompt. For narrators with rich BB data (Christopher: 50+ fields populated), this can be 1,000+ tokens.

**Reduction options:**
- Render only fields relevant to the current era / target_section
- Use a fixed-width compact format (key:value, one per line, no JSON braces)
- Move BB blob to a separate "context" SSE event the LLM can reference but doesn't have to re-process every turn

### Suspect #4 — Stacked directive blocks

Multiple WO-driven directive blocks may stack on every turn:
- WO-10C cognitive support framing
- LORI_INTERVIEW_DISCIPLINE
- ACUTE_SAFETY_RULE
- Narrative cue library directive (when LV_LORI_CUE_INJECTION enabled)
- Voice library reference (when applicable)

**Reduction options:**
- Most directives are turn-mode-specific; gate strictly on turn_mode
- Compress recurring rules to bullet form (5 words max per rule)
- Move evergreen directives to a system-level "constitution" injected once per session, not every turn

### Phase 1 acceptance gates

1. Single chat turn `prompt_tokens` < 2,500 for normal interview mode
2. Era-click turn `prompt_tokens` < 3,000 (slightly higher because of era directive + currentEra context)
3. Lori reply latency (first-token time) < 15s on RTX 5080 / 8B-Q4
4. r5h baseline eval (78/114, v3=49, v2=43) UNCHANGED — this is a Lori-side change, must not affect extractor pipeline
5. Three Lori-behavior eval packs (golfball, sentence-diagram-survey, lori_narrative_cue_eval) UNCHANGED on Lori-quality metrics

---

## Phase 2 — Verification (separate session)

After Phase 1 lands:
1. Re-run rehearsal_quick_v7 with full --standard mode (3 voices)
2. Confirm prompt_tokens ≤ 2,500 across all turns
3. Confirm Coming of Age + Today + all 7 eras get Lori replies within 30s (well below 90s safety margin)
4. Confirm long_life cascade no longer needs --include-long-life GPU exhaustion workaround

---

## Out of scope

- BUG-CHATWS-SWITCH-CONV-FK-01 (separate lane — sibling bug, not blocked by this)
- KV cache clear between voices (separate lane, OPS-VRAM-VOICE-LOOP)
- Extractor-side prompt size (separate concern; extractor uses its own composer)

---

## Non-negotiables

- **No removal of safety rule injection.** ACUTE_SAFETY_RULE block stays full-strength on every interview-mode turn. If the bloat audit shows safety rules are heavy, the answer is "yes, they are; that's by design" — we don't shrink safety guidance to save tokens.
- **No silent dropping of profile_seed.** If profile_seed is causing bloat, we either gate it cleanly behind turn_mode OR truncate to top-5 fields with explicit operator-visible logging — we do NOT just stop emitting it.
- **No breaking r5h eval.** Extractor pipeline uses a separate composer (`extract.py` few-shots) and must not be touched in this WO.

---

## Files this WO will touch (Phase 0)

- `server/code/api/prompt_composer.py` — instrumentation only, gated behind env flag
- `.env.example` — document `HORNELORE_PROMPT_BLOAT_AUDIT=0` flag
- `docs/reports/PROMPT_BLOAT_AUDIT_2026-05-04.md` — new report

## Files this WO will touch (Phase 1, separate session)

- `server/code/api/prompt_composer.py` — actual reductions per Phase 0 evidence
- Possibly `server/code/api/memory_echo.py` if profile_seed gating is the chosen reduction
- `docs/reports/WO-PROMPT-BLOAT-AUDIT-01_REPORT.md` — final report with before/after numbers

## Acceptance summary

Phase 0 is "audit only" — passes when the per-block breakdown report is authored and committed. No behavior change required for Phase 0 to close.
Phase 1 is the actual reduction. Phase 1 closes when Phase 1 acceptance gates above are met.
