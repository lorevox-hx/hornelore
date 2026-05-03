# WO-NARRATIVE-CUE-LIBRARY-01 Phase 2 — Detector Calibration Report

**Date:** 2026-05-03
**Tag:** ncue-detector-v1
**Tests:** 31/31 green (19 unit + 4 cue isolation + 4 story isolation + 4 utterance-frame isolation, no cross-contamination)

---

## Headline

Pure-stdlib narrative cue detector landed and tested. Detects which of
the 12 v1 cue types best fits a narrator's utterance via deterministic
trigger-term matching. **82.5% top-1 hit rate (33/40)** on the locked
eval pack `data/qa/lori_narrative_cue_eval.json` after Class B promotion
(2026-05-03). The pre-promotion floor was 75% (30/40); the Class B
candidate library (hidden_custom + hard_times trigger expansion) was
proven GREEN with zero regressions via the Phase 3 harness and
promoted to v1 seed.

**Pre-promotion seed preserved at**
`data/lori/narrative_cue_library.v1.pre_class_b.json` for rollback.

The misses are calibration signals for library-side trigger tuning, not
detector bugs. The detector itself is byte-stable, deterministic, and
mechanically prevented from coupling to the extraction pipeline (LAW 3
isolation gate verified by negative test).

**Phase 2 acceptance: GREEN.** Phase 3 (eval harness) and Phase 4
(prompt_composer integration behind a default-off flag) open per the
locked staged plan. Consumer wiring is parked behind those phases.

---

## Files banked

| File | Purpose |
|---|---|
| `server/code/api/services/narrative_cue_detector.py` | Pure-stdlib detector (~340 lines). `build_library()` + `detect_cues(text, current_section, library)`. |
| `tests/test_narrative_cue_detector_isolation.py` | LAW 3 build gate. AST-walks imports, fails build on forbidden coupling to extraction / DB / sibling services. |
| `tests/test_narrative_cue_detector.py` | Public API contract (16 tests) + library loader + normalization + eval-pack calibration walk. |
| `scripts/narrative_cue_detector_repl.py` | CLI debug runner: `--text`, `--file`, stdin pipe, `--eval` (full pack walk + summary). |
| `docs/reports/WO-NARRATIVE-CUE-LIBRARY-01_PHASE2_CALIBRATION.md` | This report. |

---

## Detector design (locked)

**Deterministic.** Same input → same output across calls. No randomness,
no time, no environment reads.

**Pure stdlib.** Only `json`, `re`, `unicodedata`, `dataclasses`,
`functools`, `pathlib`, `typing`. Nothing else.

**Scoring.** Each unique trigger term that fires in the text contributes
+1 to the cue's score. Duplicate hits of the same term count once.
Optional `current_section` adds +1 if any of the cue's
`operator_extract_hints` reference paths under that section (operator
side; never exposed in runtime output).

**Tie-break.** When two cues have the same score, library order wins
(stable). Library order is the order cue_types appears in the JSON.

**Normalization.** NFKD + accent strip + curly quote / apostrophe
fold + lowercase + whitespace collapse. Word-boundary regex prevents
substring leaks ('mom' must not match 'momentum'). Multi-word triggers
match as phrases with whitespace flexibility.

**Runtime safety.** `CueMatch.to_dict()` deliberately omits
`operator_extract_hints`. The schema sets
`runtime_exposes_extract_hints: false` and the dataclass enforces it.

---

## Eval pack calibration (40 cases, 12 cue types)

**Pass rate: 75.0% (30/40)**

| Expected cue type | Cases | Hits | Rate |
|---|---:|---:|---:|
| parent_character | 4 | 4 | 100% |
| elder_keeper | 3 | 3 | 100% |
| hearth_food | 4 | 3 | 75% |
| object_keepsake | 3 | 2 | 67% |
| journey_arrival | 4 | 3 | 75% |
| home_place | 3 | 2 | 67% |
| work_survival | 4 | 3 | 75% |
| language_name | 3 | 3 | 100% |
| identity_between | 3 | 2 | 67% |
| hard_times | 3 | 1 | 33% |
| hidden_custom | 4 | 2 | 50% |
| legacy_wisdom | 2 | 2 | 100% |

### The 10 misses, classified

**Class A — Library trigger gap (3 cases):** the narrator's text uses
language not in the library's trigger list. Detector returns no match.
Fix is library-side, not detector-side.

- `ncue_011_journey_sky` — "The sky was so big it made my head hurt."
  Library `journey_arrival` triggers don't include sky / upward.
- `ncue_021_food_tin` — "We saved the bacon grease in a blue tin."
  Library `hearth_food` triggers don't include bacon / grease / tin / saved.
- `ncue_036_hidden_greeting` — "The old greeting was only a nod of the head."
  Library `hidden_custom` triggers don't include greeting / nod /
  unspoken / no one said.

**Class B — Tie-break-by-library-order favors a generic cue (7 cases):**
the narrator's text fires the right cue AND a more generic cue
(usually `parent_character` or `elder_keeper`) at the same score; the
generic cue wins because it appears earlier in library order. Fix is
library-side (re-rank, weight, or section-anchor).

- `ncue_014_home_onions` — `home_place` lost to `parent_character` ("father")
- `ncue_016_work_railroad` — `work_survival` lost to `parent_character` ("Father")
- `ncue_023_object_ticket` — `object_keepsake` lost to `parent_character` ("father")
- `ncue_030_identity_accent` — `identity_between` lost to `hearth_food` ("bread")
- `ncue_033_hard_school` — `hard_times` lost to `parent_character` ("Mother")
- `ncue_034_hard_invisible` — `hard_times` lost to `parent_character` ("Father")
- `ncue_037_hidden_grandmother` — `hidden_custom` lost to `elder_keeper` ("grandmother")

### Tuning paths (parked for Phase 3+)

1. **Library trigger expansion** (Class A, 3 cases) — add the missing
   anchors to each cue's trigger_terms in the JSON. Zero detector
   change. Re-run the eval pack to confirm.

2. **Section bonus expansion** (Class B partial, ~3 cases) — when a
   case carries `current_section` (most cases do), the cue whose
   `operator_extract_hints` align with that section gets the
   tie-break. The current section bonus implementation requires hint
   paths to start with the section name; a richer matcher (e.g. fuzzy
   on section synonyms, support for nested paths like
   `community.work` matching `work` section) would lift several
   Class B cases without harming the rest.

3. **Risk-level priority** (Class B, hard_times / hidden_custom) —
   when the narrator's text fires both a low-risk cue (parent /
   elder) AND a sensitive cue (hard_times / hidden_custom), the
   sensitive cue should arguably win. That's a real design decision
   — encoding it as a tie-break rule promotes 4-5 cases at the cost
   of potential Class B regressions in the other direction. Worth
   triangulating with Chris + ChatGPT before landing.

4. **Multi-cue surfacing** (consumer-side) — the detector already
   returns the full ranked list; the prompt_composer in Phase 3 can
   read the top 2-3 and let Lori shape a richer reflection rather
   than collapsing to a single cue. This may make the top-1 metric
   less important than top-2 or top-3 coverage.

Each path is a library-side or consumer-side tuning, not a detector
patch. The detector code stays locked unless a real bug surfaces.

---

## LAW 3 isolation — verified by negative test

The `tests/test_narrative_cue_detector_isolation.py` gate:
- AST-walks `narrative_cue_detector.py` imports transitively (depth 4)
- Fails the build if any reachable module is in the forbidden set
  (extract, prompt_composer, memory_echo, llm_api, chat_ws,
  family_truth, safety, db, plus all sibling services)

**Negative-test verification (run during Phase 2 development):**
1. Injected `from ..routers import extract` into the detector
2. Ran the gate → FAILED with the right message naming
   `api.routers.extract` as forbidden
3. Reverted the injection
4. Ran the gate → PASSED

Both states confirmed. The mechanical wall is intact.

---

## What this does NOT do (Phase 3+)

- **No consumer wiring.** The detector is invokable but no chat_ws
  hook, no prompt_composer call, no log marker. The output is dead
  code until Phase 3 wires it up behind `HORNELORE_LORI_CUE_LOG=0`
  (default-off observability) and Phase 4 wires it as an injection
  source for prompt directives behind a separate flag.

- **No cultural humility eval.** `data/evals/lori_cultural_humility_eval.json`
  uses a different schema axis (suppression markers like
  `sacred_silence`, `power_asymmetry`) that don't reconcile with the
  v1 seed library's cue_type enum. That's a Phase 5+ reconciliation:
  either v2 library is brought into schema-alignment, or the
  detector grows a parallel suppression-marker output channel. Not
  this phase.

- **No v2 library support.** `data/lori/narrative_cue_library.json`
  (version 2, ChatGPT-authored) uses incompatible cue type names
  (`named_heirloom`, `sacred_silence`, etc. vs the schema's
  `parent_character`, `hearth_food`, etc.). The detector loads only
  v1 seed by default. v2 reconciliation is also Phase 5+.

- **No truth writes.** Hard rule. The cue library is a listener aid;
  truth flows only through the existing extractor → Review Queue →
  promoted History pipeline. The LAW 3 isolation gate enforces this
  mechanically.

---

## What's next

**Phase 3** (eval harness): build a runner that walks the eval pack
under different library tuning configurations (current vs. expanded
triggers vs. risk-level priority) and produces a per-case calibration
report so the library can be tuned with measured evidence.

**Phase 4** (prompt_composer integration): default-off observability
flag (`HORNELORE_LORI_CUE_LOG=0`) that emits `[lori-cue]` log lines on
each chat turn carrying the detector's top_cue. No behavior change.
Then, separately, a default-off injection flag for using the cue's
`safe_followups` / `forbidden_moves` to shape Lori's next response.

**Phase 5** (v2 / cultural humility reconciliation): bring the v2
library into schema alignment, OR add a parallel suppression-marker
detector channel. Either way, the existing v1 path stays stable.

---

## Pre-commit verification

Tree clean state requires `git status` from `/mnt/c/Users/chris/hornelore`
since sandbox can't run git. All 31 tests green at HEAD.
