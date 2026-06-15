# BUG-LORI-MIDSTREAM-CORRECTION-01 — Lori doesn't handle narrator corrections during lifemap walks

**Status:** OPEN — pre-parent-session blocker
**Severity:** AMBER (degrades parent-session UX; narrators correct themselves often)
**Surfaced by:** TEST-23 v6 (2026-05-05)
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers (sequenced after BUG-UI-POSTRESTART-SESSION-START-01)

---

## Problem

When the narrator interrupts a lifemap-era walk with a correction (`"Actually we only had two kids, not three"`), Lori does NOT explicitly acknowledge the correction. The harness's `handled_well` scorer returns False, indicating Lori's response did not:

- Acknowledge the correction explicitly ("Two kids, got it" / "Thank you for the correction")
- Reflect the corrected value back so the narrator hears it
- Update the relevant projection/truth field via the extractor's correction-routing path

Mid-stream corrections during era walks are **load-bearing for parent sessions** — narrators with cognitive load (Janice, Kent, anyone older) self-correct frequently, and a Lori that plows past corrections feels both disrespectful and structurally broken (the truth never updates, so memory_echo will repeat the wrong value next turn).

## Evidence

v6 run, Mary's lifemap building_years phase:

```
[mary/lifemap/building_years] EXTRA sent='Actually we only had two kids, not three.' reply=37w handled_well=False
[mary/lifemap/building_years] click_log=True era=building_years prompt=12w (anchored=False q=1) seed=41w anchored=True AMBER
```

Lori's reply was 37 words, but `handled_well=False` — meaning the scorer's correction-detection heuristics didn't register an acknowledgment in the response.

The era cell scored AMBER because the seed (post-correction Lori prompt) was correctly anchored to building_years, but the correction itself wasn't acknowledged.

## What `handled_well` is supposed to detect

Per the harness scorer in `run_test23_two_person_resume.py` (search for `handled_well`):

The scorer looks for explicit correction-acknowledgment shapes in Lori's response — patterns like:
- "Two kids" / "Two children" / "Two of them" appearing verbatim in the reply (echoing the corrected value)
- Phrases like "Got it", "Thank you for clarifying", "Let me correct that"
- A reflection that incorporates the corrected count rather than the original

When none of those land, `handled_well=False`.

## Diagnosis hypothesis

Three candidate root causes, ranked by confidence:

**A. Correction-mode is not detected at the routing layer.** When the narrator's utterance starts with `"Actually"` or `"No, it was"` or similar correction markers, `chat_ws.py` routes it as a regular interview turn — NOT as a correction turn. `prompt_composer.py` has a CORRECTION mode (search the file for the mode dispatch) but it doesn't fire on this shape.

**B. The corrected value reaches the extractor but Lori's response is generated before the new truth lands.** Sequence: narrator sends → extractor pulls candidates → projection updates in DB → Lori's response is generated from a system prompt that doesn't yet reflect the new truth. Lori gives a confident-sounding response based on the old value.

**C. CORRECTION mode IS detected but its prompt directive doesn't include strong enough acknowledgment requirements.** The mode dispatches but the system prompt for it is too soft ("acknowledge the correction" without a hard "echo the corrected value verbatim" rule). Lori paraphrases or moves on without the harness-detectable acknowledgment shape.

## Reproduction

```bash
cd /mnt/c/Users/chris/hornelore
python -m scripts.ui.run_test23_two_person_resume --tag debug_correction --only mary
```

Watch the `[mary/lifemap/building_years]` phase. The harness sends the correction string, captures Lori's reply, and emits the `handled_well` flag.

Manual reproduction in a real session:
1. Start an interview with any test narrator who has confirmed family.children data
2. Mid-walk during any era, type `"Actually we only had two kids, not three"`
3. Observe Lori's reply — does she echo "two" verbatim and update her behavior, or does she continue as if the correction wasn't made?

## Diagnostic plan (read-only first)

1. **Capture the routing path.** Add temporary log markers to `chat_ws.py` showing which `turn_mode` is selected for this utterance shape. Confirm whether CORRECTION mode fires or whether it routes as standard interview.
2. **Capture the prompt sent to the LLM.** With `LV_DEV_MODE=1` (existing dev-log flag), dump the system prompt + user message at the moment Lori generates the response. Verify whether the correction marker is present in the prompt and what the system prompt directs Lori to do.
3. **Capture the post-correction projection state.** Confirm whether `family.children` count actually updates from 3 → 2 in `interview_projections.projection_json` after the correction. If yes, the truth path works; the gap is response-shape. If no, the gap is upstream (extractor / routing).

## Acceptance gate

TEST-23 v7 (or later) shows `[mary/lifemap/building_years] EXTRA ... handled_well=True` for Mary's correction turn, AND a parallel correction inserted into Marvin's lifemap walk also returns `handled_well=True`.

Concrete behavioral acceptance:
- Lori's response to a correction-shaped utterance includes the corrected value verbatim ("two") OR a reflective phrase that explicitly references the correction ("Two kids — got it. So...")
- The corrected value reaches `interview_projections.projection_json` within the same turn
- The next memory_echo turn for that narrator carries the corrected value, not the original

## Files (planned, after diagnostic)

**Likely modified:**
- `server/code/api/routers/chat_ws.py` (correction-mode detection at routing layer if hypothesis A confirmed)
- `server/code/api/prompt_composer.py` (CORRECTION mode directive strengthening if hypothesis C confirmed)

**Possibly modified:**
- `server/code/api/routers/extract.py` (correction-routing logic for value updates if hypothesis B confirmed)

**Likely added:**
- `server/code/api/services/lori_communication_control.py` — possible new validator step that catches "Lori didn't echo the corrected value" and routes through `shape_reflection()` or similar runtime fix (composes with BUG-LORI-REFLECTION-02 Patch C runtime shaping)

## Risks & rollback

**Risk 1: over-eager correction detection.** Patterns like "Actually" appear in non-correction utterances ("Actually I always wanted to be a teacher"). False-positive correction routing could route stories as corrections. Mitigation: require correction markers + a contradicted-fact pattern (numerical change, named-entity change, date shift). Build the test pack with both true positives and false-positive shapes.

**Risk 2: shape_reflection conflict.** If runtime shaping (BUG-LORI-REFLECTION-02 Patch C) is engaged on the same turn, the post-LLM rewrite could strip or reshape the acknowledgment Lori produced. Mitigation: the correction-acknowledgment requirement runs AFTER shape_reflection in the comm-control wrapper.

**Risk 3: confidence threshold churn.** Corrections often arrive with low LLM-side confidence (the narrator is interrupting, the utterance is short). The extractor's confidence gate may drop the corrected value before it reaches projection. Mitigation: correction-mode triggers an extractor-side confidence floor reduction for the affected field.

**Rollback:** revert the patch. Mid-stream corrections go back to plowing-past behavior. No regression on non-correction turns.

## Sequencing

Land after BUG-UI-POSTRESTART-SESSION-START-01 (so resume verification works). Compose with BUG-LORI-REFLECTION-02 Patch C (runtime shaping is already landed default-off; correction-acknowledgment work may benefit from flipping that on). Compose with WO-LORI-ACTIVE-LISTENING-01 + WO-LORI-SESSION-AWARENESS-01 Phase 2 (interview discipline) — the ONE-question rule from those WOs naturally tightens correction responses.

## Changelog

- 2026-05-05: Spec authored after v6 evidence. Three diagnostic hypotheses ranked. Acceptance gate ties to TEST-23 v7+ harness scoring.
