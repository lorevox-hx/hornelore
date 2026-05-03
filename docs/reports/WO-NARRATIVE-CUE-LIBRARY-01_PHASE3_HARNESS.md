# WO-NARRATIVE-CUE-LIBRARY-01 Phase 3 — Eval Harness

**Date:** 2026-05-03
**Tag:** ncue-eval-harness-v1
**Tests:** 39/39 green (31 from Phase 2 + 8 new harness smoke tests)

---

## Headline

Eval harness landed. The loop for measured library tuning now exists:
make a candidate library JSON, run `scripts/run_narrative_cue_eval.py
--candidate <path> --tag <name>`, and read the diff. The harness
surfaces regressions that would otherwise be invisible.

**Phase 3 acceptance: GREEN.** Phase 4 (prompt_composer log
observability behind `HORNELORE_LORI_CUE_LOG=0` default-off flag)
opens next. Library tuning itself is a separate downstream loop that
uses this harness; not in scope for Phase 3.

---

## Files banked

| File | Purpose |
|---|---|
| `scripts/run_narrative_cue_eval.py` | Eval harness CLI: baseline-only, baseline-vs-candidate diff, stability check. Output JSON + console. Exit codes: 0 OK / 1 stability fail / 2 strict-mode regression / 3 bad inputs. |
| `data/lori/narrative_cue_library.candidate_class_a_v1.json` | Demo candidate library: Class A trigger expansion for the 3 "no trigger fired" misses identified in PHASE2_CALIBRATION. |
| `tests/test_narrative_cue_eval_harness.py` | 8 smoke tests: stability, baseline report shape, miss_class field, diff structure, hits-reconcile-with-diff, Class A candidate sanity. |
| `docs/reports/narrative_cue_eval_baseline.json` + `.console.txt` | Banked baseline report (30/40 = 75%). |
| `docs/reports/narrative_cue_eval_class_a_v1_baseline.json` | Diff-mode baseline copy. |
| `docs/reports/narrative_cue_eval_class_a_v1_candidate.json` | Diff-mode candidate report (32/40 = 80%). |
| `docs/reports/narrative_cue_eval_class_a_v1_diff.json` + `.console.txt` | Side-by-side baseline-vs-candidate diff. |
| `docs/reports/WO-NARRATIVE-CUE-LIBRARY-01_PHASE3_HARNESS.md` | This report. |

---

## What the harness does

**Single-config (baseline) mode.** Walk every case in the eval pack
under one library, classify each result by miss_class, render per-cue-type
breakdown + overall pass rate. Output: full JSON + readable console.

**Diff mode (the real value).** Walk the same cases under TWO library
configurations and produce:
- Newly **passed** cases (which trigger expansion helped)
- Newly **failed** cases (regressions — must be fixed before adopting the candidate)
- Score-only changes (same ok/fail bucket but different cue or score)
- Per-cue-type delta (signed, where the patch is concentrated)
- Miss-class delta (Class A → Class B shifts often hide regressions)
- Verdict (GREEN / AMBER / strict-mode exit code 2)

**Stability check.** Run baseline twice, fail with exit 1 if any
record differs. Catches future violations of the detector's
deterministic contract.

---

## Miss classification (refined from Phase 2)

The harness classifies every miss into one of four buckets:

| Class | Meaning | Phase 2 baseline count |
|---|---|---:|
| `none` | Pass | 30 |
| `class_a` | No trigger fired at all (library coverage gap) | 3 |
| `class_b` | Wrong cue won; expected cue IS in the ranked list (tie-break by library order) | 6 |
| `class_c` | Wrong cue won; expected cue NOT in ranked list at all (library covers expected for OTHER texts but not this one) | 1 |

Class A and Class C call for trigger expansion. Class B calls for
either tie-break tuning (risk-level priority, section bonus
expansion) or section-anchored cue affinity. The harness reports the
miss_class delta on every diff so you can see at a glance where the
candidate is shifting cases.

---

## Real demo: Class A candidate v1

The Class A candidate library (`narrative_cue_library.candidate_class_a_v1.json`)
adds conservative trigger expansions to 3 cues:

- `journey_arrival` += `sky`, `horizon`, `fall upward`, `big sky`, `never seen`
- `hearth_food` += `bacon`, `grease`, `tin`, `jar`, `saved`, `pantry`, `cellar`
- `hidden_custom` += `greeting`, `nod`, `no one said`, `never said`, `meant something`, `unspoken`

**Diff result:**

```
  Baseline:   narrative_cue_library.v1.seed              →  30/40  (75.0%)
  Candidate:  narrative_cue_library.candidate_class_a_v1 →  32/40  (80.0%)
  Delta:      +5.0 pp

  Verdict:    AMBER — candidate has regressions; review newly_failed before adopting

  Newly PASSED (3 cases):
    + [ncue_011_journey_sky]      candidate_triggers=['fall upward', 'sky']
    + [ncue_021_food_tin]         candidate_triggers=['bacon', 'grease', 'saved', 'tin']
    + [ncue_036_hidden_greeting]  candidate_triggers=['greeting', 'no one said', 'nod']

  Newly FAILED — REGRESSIONS (1):
    - [ncue_025_object_jar]       candidate_actual=hearth_food
                                  baseline_triggers=['jar', 'ticket']
```

**The regression caught:** adding `jar` to `hearth_food` collides
with `object_keepsake` (which already had `jar`). The case was
"steamship ticket cost my father three years..." — with `jar` now in
both cues, `hearth_food` wins because it appears earlier in library
order (after parent_character also matches "father"). The harness
caught this. Without it, the +3 win would have looked clean and the
silent regression would have been invisible until later QA.

**This is the whole point of Phase 3.** The harness is doing the work
of preventing "I added one trigger, what could go wrong?" classes of
regressions. Library tuning decisions should always go through this
loop.

**Disposition for the demo candidate:** AMBER — DO NOT adopt as-is.
Either remove `jar` from hearth_food (lose the bacon/grease/tin
hearth_food gains? probably not — the `tin` trigger alone fired
4 trigger matches on ncue_021), or accept the object_keepsake
regression and add a tie-break rule that prefers narrower cues when
context suggests them.

---

## How to use the harness for real tuning work

**Loop:**

1. Identify a target case from the latest baseline report's miss list
2. Edit `data/lori/narrative_cue_library.v1.seed.json` to a candidate
   path (e.g. `narrative_cue_library.candidate_<change>.json`); add
   the trigger / move the cue / restructure
3. Run:
   ```bash
   python3 scripts/run_narrative_cue_eval.py \
     --candidate data/lori/narrative_cue_library.candidate_<change>.json \
     --tag <change_name> \
     --output-dir docs/reports/
   ```
4. Read `docs/reports/narrative_cue_eval_<change_name>_diff.console.txt`
5. **If newly_failed is non-empty: do not adopt.** Either patch the
   regression in the candidate, or accept it explicitly with a
   written rationale.
6. **If GREEN:** rename the candidate file to replace the seed
   library, re-run baseline to bank the new floor, commit.

**Stability sanity (run anytime):**
```bash
python3 scripts/run_narrative_cue_eval.py --stability-check
# Expected: stability OK — two runs produced byte-identical case records
```

**Strict mode for CI:**
```bash
python3 scripts/run_narrative_cue_eval.py \
  --candidate <path> --tag <name> --output-dir docs/reports/ --strict
# Exits 2 if newly_failed is non-empty; 0 otherwise
```

---

## Acceptance gates

Phase 3 ships when:
- ✓ Harness CLI works in all three modes (baseline / diff / stability-check)
- ✓ Diff mode produces structured JSON + readable console
- ✓ Hits reconcile: `candidate.hits = baseline.hits + len(newly_passed) - len(newly_failed)`
- ✓ Stability check returns identical records on two runs of the same library
- ✓ Smoke tests pass (8/8)
- ✓ Demo candidate exercises the full loop end-to-end

All five gates met. Phase 3 closed.

---

## What this does NOT do (Phase 4+)

- **No prompt_composer integration.** Phase 4 wires the detector to
  emit `[lori-cue]` log lines on each chat turn behind a default-off
  `HORNELORE_LORI_CUE_LOG=0` flag (mirrors `HORNELORE_UTTERANCE_FRAME_LOG`
  pattern). No behavior change to live narrator sessions.

- **No Lori response shaping.** Phase 5+ uses `safe_followups` /
  `forbidden_moves` from the top cue to inform Lori's response
  composer behind a separate default-off flag. Composer integration
  needs design discussion before code.

- **No library tuning decisions.** This phase ships the TOOL for
  measured tuning. The actual library JSON edits (which Class A
  triggers are worth it, whether to add risk-level tie-break, etc.)
  are downstream work that uses this harness.

- **No cultural humility eval reconciliation.**
  `data/evals/lori_cultural_humility_eval.json` uses a different
  schema axis (suppression_markers) than the v1 cue library. Phase 5+
  decision: either v2 library is brought into schema-alignment, or the
  detector grows a parallel suppression-marker channel.

---

## Pre-commit verification

Tree clean state requires `git status` from `/mnt/c/Users/chris/hornelore`
since sandbox can't run git. All 39 tests green at HEAD (31 from
Phase 2 + 8 new harness tests).
