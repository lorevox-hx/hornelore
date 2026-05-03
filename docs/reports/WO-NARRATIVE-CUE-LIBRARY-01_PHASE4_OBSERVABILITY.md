# WO-NARRATIVE-CUE-LIBRARY-01 Phase 4 — chat_ws Observability Hook

**Date:** 2026-05-03
**Tag:** lori-cue-observability-v1
**Tests:** 39/39 green (no test changes; existing isolation gates unaffected)

---

## Headline

Single observation-only log hook landed in `chat_ws.py` behind
`HORNELORE_LORI_CUE_LOG=0` (default-OFF). When enabled, every narrator
turn emits one `[lori-cue]` log line carrying the top cue type
detected from the v1 library, its risk level, score, and which trigger
terms fired. **Zero behavior change to live narrator sessions
regardless of flag setting.** Mirrors the `[utterance-frame]` and
`[story-trigger]` patterns from prior weeks.

**Phase 4 acceptance: GREEN.** The Lori-side lane now has its
production observability surface; flipping the flag for a session
gives operator-side visibility into what cue the library would
select if Phase 5 ever wired it into Lori's response composer.

Phase 5 (cue-driven Lori response shaping) needs a separate design
discussion before code — explicitly NOT in this phase.

---

## Files modified

| File | Change |
|---|---|
| `server/code/api/routers/chat_ws.py` | +66 lines: new lori-cue observability block immediately after the existing `[utterance-frame]` block. Same gate posture (flag on AND non-empty user_text AND not `[SYSTEM_*]` directive). Lazy import of `services.narrative_cue_detector`. Single compact `[lori-cue]` log line per turn. Failure swallowed at WARNING; turn always continues. |
| `.env.example` | +28 lines: full doc block for `HORNELORE_LORI_CUE_LOG=0` with use-case framing, default-off rationale, the LISTENER AID covenant (cue library never writes truth), and the staged-plan pointer to Phase 5+. |

No detector code changes. No new tests required (the existing
detector test suite + isolation gate fully cover the surface; the
chat_ws hook is one-way trivially-correct plumbing).

---

## What the log line looks like

When a cue matched:
```
2026-05-03 ... [lori-cue] conv=conv_abc narrator=janice-josephine-horne
  cue_type=elder_keeper risk=low score=2 triggers=grandmother,kept ranked_count=3
```

When no cue matched (text didn't fire any trigger term):
```
2026-05-03 ... [lori-cue] conv=conv_abc narrator=janice-josephine-horne
  cue_type=- no_match_reason=no_trigger_match ranked_count=0
```

When the detector raised an unexpected exception (defensive — should
never happen on stdlib regex, logged for surface):
```
2026-05-03 ... [lori-cue] detect_cues failed (conv=conv_abc): ...
```

---

## Gate semantics (mirror of utterance-frame / story-trigger)

The block fires only when ALL of:

1. `os.getenv("HORNELORE_LORI_CUE_LOG", "0") in ("1", "true", "True")`
2. `user_text` is non-empty after strip
3. `_is_system_directive` is False (skips `[SYSTEM_QF: ...]` and similar
   in-band UI control messages — same rule from story-trigger Patch A)

Lazy import of `services.narrative_cue_detector` keeps the module out
of `sys.modules` entirely when the flag is off — extra LAW 3 gate.

Detector failure is caught and logged at WARNING; the turn continues
without disruption. This is observation-only by design; it must NEVER
be the reason a chat turn breaks.

---

## What is NOT wired (Phase 5+)

- **No prompt_composer integration.** The cue's `safe_followups` /
  `forbidden_moves` are NOT yet shaping Lori's response. Phase 5
  needs a design discussion before code: how does the cue compose
  with WO-LORI-ACTIVE-LISTENING-01's one-question discipline, with
  WO-LORI-SAFETY-INTEGRATION-01's safety acuity tiers, with
  WO-LORI-SESSION-AWARENESS-01's interview discipline? The cue
  library is one input; Lori's composer needs a layered policy.

- **No section context.** chat_ws doesn't currently thread
  `current_section` (the interview's active section) into the chat
  turn payload. Phase 4 passes `current_section=None` to
  `detect_cues()`, so the section bonus tie-break is not applied
  in the live log. If the operator side wants to inform tie-breaks
  later, the path is to thread the active section from interview
  state into the chat turn — separate WO.

- **No cue history / aggregation.** Each turn's cue is logged
  independently. No "cue trajectory" tracking, no per-narrator cue
  histograms in the operator dashboard. Those are downstream
  observability work that would build on top of this log marker.

- **No truth writes.** Hard rule. The cue library is a LISTENER
  AID; truth flows only through the existing extractor → Review
  Queue → promoted History pipeline. The LAW 3 isolation gate on
  `narrative_cue_detector.py` enforces this mechanically.

---

## Verification done at landing

- `chat_ws.py` AST-parses clean (`python3 -c "import ast;
  ast.parse(open('server/code/api/routers/chat_ws.py').read())"`)
- All 39 prior tests still pass (19 detector unit + 4 detector
  isolation + 8 harness smoke + 4 story_preservation isolation +
  4 utterance_frame isolation). The detector and isolation gates
  are untouched.
- The lazy import direction (chat_ws → detector) is one-way; the
  detector's import graph is unchanged. LAW 3 isolation gate
  remains intact.

---

## How to use

Turn the flag on for a session you want to survey, restart the stack
(launcher auto-sources `.env` via `common.sh`), then grep `api.log`:

```bash
# In .env: change HORNELORE_LORI_CUE_LOG=0 to =1
# (or use a sister .bat shortcut like the SPANTAG pair if you build one)
# Restart stack, run a real or synthetic narrator session
grep "\[lori-cue\]" .runtime/logs/api.log | tail -40
```

Then feed observations back into library tuning via the eval harness:

```bash
# If you see, e.g., a narrator turn that should have hit hard_times but
# fired parent_character, add an eval case to lori_narrative_cue_eval.json
# reproducing the text + expected cue, then run:
python3 scripts/run_narrative_cue_eval.py \
  --candidate data/lori/narrative_cue_library.candidate_<your_change>.json \
  --tag <change_name> --output-dir docs/reports/
```

The diff console will tell you whether your library tweak helps the
new case without regressing existing ones.

---

## Phase 5+ pointer

When the Lori-side lane is ready to actually USE the cue (not just
log it), the path is:

1. **Design discussion first.** Triangulate Claude / Chris /
   ChatGPT on: which cue surfaces (top_cue.cue_type only, or the
   full ranked top-3?), what composition rule (cue's
   `safe_followups[0]` as a fallback when LORI-ACTIVE-LISTENING
   doesn't have a better question? Cue's `forbidden_moves` as a
   prompt-side directive?), and how risk_level interacts with
   safety acuity tiers.

2. **Default-off injection flag.** A NEW flag like
   `HORNELORE_LORI_CUE_INJECT=0` that is separate from the log
   flag. Log-only stays on for surveillance; injection stays off
   until validated.

3. **Composer guard.** The injection point is in
   `prompt_composer.py`, downstream of LORI-ACTIVE-LISTENING and
   LORI-SAFETY. Cue is one input; doesn't override either.

4. **Eval acceptance.** Before injection-flag default-on, cue must
   pass a multi-turn eval that confirms it ADDS warmth without
   regressing question discipline or safety routing.

That whole sequence is Phase 5+, not this phase.

---

## Pre-commit verification

Tree clean state requires `git status` from `/mnt/c/Users/chris/hornelore`
since sandbox can't run git. All 39 tests green at HEAD. chat_ws.py
AST-parses clean. .env.example documents the flag clearly.
