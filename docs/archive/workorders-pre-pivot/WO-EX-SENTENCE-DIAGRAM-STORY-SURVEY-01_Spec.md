# WO-EX-SENTENCE-DIAGRAM-STORY-SURVEY-01 — Sentence Diagram Story Survey Harness

**Status:** LANDED 2026-05-02 — base authored by ChatGPT (32 cases, 19 groups, three-pipeline harness with chat + extract + frame). Extended by Claude (+10 cases, +10 groups) covering: complex_family_blended (sd_033), identity_disclosure (sd_034), sparse_uncertain_kinship (sd_035), narrator_military_emotional (sd_036), faith_sensitivity (sd_037), pets_emotional (sd_038), stt_garbage_resilience (sd_039), run_on_compound_stress (sd_040), negation_secondhand_knowledge (sd_041), stated_affect_grounding (sd_042). **Final merged pack: 42 cases / 29 groups.** A complementary Lori-behavior-only chat probe lives at `tests/fixtures/lori_behavior_pack_v1.json` + `scripts/run_lori_behavior_pack.py` — see "Complementary chat-only probe" below.

## Purpose

Create a large synthetic narrator-turn survey that tests the specific weak spots exposed by the Josephine / pet / DOB / POB discussion:

- occupation vs talent vs side income vs homemaker/housewife life role
- multi-entity pet clauses such as barn cats plus dad's horse
- DOB and POB wording variants
- dual-subject same-place birthplace sentences
- spouse alias shape (`spouse.*` vs `family.spouse.*`)
- cultural heritage / thematic memory binding
- cardinality in children and sibling lists
- negation / uncertainty around fragile identity facts

The survey is not a replacement for the 114-case master eval. It is a diagnostic harness to show:

1. exactly what the narrator said to Lori;
2. exactly what Lori said back;
3. what the extractor emitted;
4. what expected fields were hit or missed;
5. what Story Clause Map frame was produced, if available.

## Files

Add:

```text
scripts/archive/run_sentence_diagram_story_survey.py
data/qa/sentence_diagram_story_cases.json
```

## Run command

```bash
cd /mnt/c/Users/chris/hornelore

python3 scripts/archive/run_sentence_diagram_story_survey.py \
  --api http://localhost:8000 \
  --cases data/qa/sentence_diagram_story_cases.json \
  --output docs/reports/sentence_diagram_story_survey_v1.json
```

For extractor-only:

```bash
python3 scripts/archive/run_sentence_diagram_story_survey.py \
  --api http://localhost:8000 \
  --cases data/qa/sentence_diagram_story_cases.json \
  --output docs/reports/sentence_diagram_story_survey_v1.json \
  --no-chat
```

## Report outputs

```text
docs/reports/sentence_diagram_story_survey_v1.json
docs/reports/sentence_diagram_story_survey_v1.console.txt
```

Each case row includes:

- `user_text`
- `chat.assistant_text`
- `utterance_frame.frame`
- `extract.payload`
- `extract.items`
- `score.expected_results`
- `score.must_not_results`
- `watch`

## Acceptance

GREEN does not mean all cases pass. GREEN means the harness provides interpretable evidence.

Minimum GREEN:

- script compiles
- report writes JSON and console files
- every case row includes `user_text`
- when chat is enabled, assistant text is captured or the chat error is explicit
- when extraction is enabled, raw extracted items are captured
- misses are grouped by field in console output

## Non-goals

- Do not wire utterance frames into extractor as part of this WO.
- Do not change extractor behavior as part of this WO.
- Do not change Lori prompts as part of this WO.
- Do not alter the 114-case master bank as part of this WO.

## Why this exists

The Josephine case showed that `musician`, `organist`, and `housewife/homemaker` can all be true at different timescales. The pet case showed that a sentence can contain multiple animal entities: household barn cats and dad's named horse. The DOB/POB case showed that the model can sometimes miss a clean date even though the date normalizer works when the field is emitted. These are not one bug. They are sentence-level meaning and binding problems that need a dedicated survey surface.

## Complementary chat-only probe

A second, smaller harness lives at:

- `tests/fixtures/lori_behavior_pack_v1.json` — 24 cases / 26 turns / 14 categories, each with an operator-readable `lookout_for` field instead of `expected_extract`/`must_not_extract`. Personas are named (Frances Eleanor Brennan = Josephine archetype; Eleanor Whitlock, David Reid, Mabel O'Connor, Walter Greenfield, Mariana Reyes-Quinn) and `narrator_id` is persona-stable across multiple cases for that persona, so multi-case-per-narrator continuity is testable.
- `scripts/run_lori_behavior_pack.py` — calls the existing `/api/operator/harness/interview-turn` HTTP endpoint (gated behind `HORNELORE_OPERATOR_HARNESS=1`). Stdlib-only (urllib). Outputs `lori_behavior_pack_<TAG>.{json,console.txt}` showing every narrator turn alongside Lori's actual response, plus per-turn `question_count`, `safety_mode_detected`, `db_locked`, latency, and `story_candidate_delta`/`safety_event_delta`. Includes one multi-turn flow case (lori_b_006) testing session continuity across 3 sequential turns under one session_id.

When to use which:

- **`run_sentence_diagram_story_survey.py`** (this WO) is the EXTRACTION-and-binding survey. It auto-grades hits/misses against `expected_extract` + `must_not_extract` per case, rolls up `misses_by_field` for triage, and optionally captures Lori's response and the utterance-frame output as evidence. Use this when you want to know "did the EXTRACTOR get it right?"
- **`run_lori_behavior_pack.py`** is the LORI-RESPONSE survey. It does NOT auto-grade text; it captures Lori's reply alongside an operator-readable `lookout_for` hint per case and lets a human read the per-case console output. Use this when you want to know "did LORI SAY THE RIGHT THING?"

The two harnesses share the Josephine-archetype design intent but answer different questions on different surfaces. Running both gives you the full extraction-vs-behavior split per case shape.
