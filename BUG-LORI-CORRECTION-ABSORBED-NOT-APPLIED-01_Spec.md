# BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01 — Phase 3 Spec

**Status:** SPEC — Phase 1 detection landed (BUG-LORI-MIDSTREAM-CORRECTION-01); Phase 2 chat_ws dispatch landed; **Phase 3 (data application) parked here**.
**Filed:** 2026-05-07 from Melanie Zollner live test
**Sequenced:** behind parent-session-readiness blockers + #50 mic modal

## Problem

Narrator says a correction. Lori reflects it back conversationally — but the data layer never updates. Three real examples from Melanie Zollner's session:

| Time | Narrator | Lori | What got updated |
|---|---|---|---|
| 03:07:38 | "there was no Hannah I said hold my hand" | "You corrected me earlier that there was no Hannah..." | NOTHING — phantom Hannah persists in extracted candidates |
| 03:12:50 | "I never said hate" | "You are correct, you never said 'hate'..." | NOTHING — "hate" is in transcript record forever |
| 03:28:42 | "you got it wrong my daughter was born . my sister was 10 when my daughter was born" | "It seems like there's a correction needed – let's get back on track..." | NOTHING — Lori's confused family-tree inference (sister flying for daughter's birth got conflated as new sibling) is not unwound |

Net effect: narrator trusts Lori with corrections, Lori sounds like she heard them, but the data layer holds the wrong story. Operator review queue catches some via Shadow Review, but the narrator-visible memory_echo still surfaces the un-corrected version.

## Why this matters for parent sessions

Janice + Kent will both speak imprecisely. They will issue corrections. The system that ignores them will be experienced as not listening. Worse: in Memoir export, the un-corrected version becomes their canonical life story.

## Phase 1 + 2 (already landed)

- `_looksLikeStrongCorrection()` regex bank in app.js detects narrator corrections (explicit openers like "no actually", "Actually,", "that's wrong", and "X not Y" patterns)
- `_looksLikeWeakCorrectionAfterEcho()` catches biographical re-statements only when prior turn was memory_echo
- `lvRouteTurn()` returns `TURN_CORRECTION` when fired
- chat_ws backend dispatches to `compose_correction_response` (warm acknowledgment composer)

What's missing: the **apply** step.

## Phase 3 design

### 3a — Correction parsing (server-side)

New service `server/code/api/services/correction_parser.py`:

```python
def parse_correction(narrator_text: str, prior_lori_text: str = "") -> Optional[CorrectionEdit]:
    """Extract structured edit intent from a narrator correction.

    Returns a CorrectionEdit describing:
      - corrected_value:   what the narrator says is true
      - retracted_value:   what they're correcting (if explicit)
      - field_hint:        best guess at affected fieldPath (or None)
      - confidence:        high / medium / low

    Rule layers (regex-first, no LLM):
      1. "X not Y" pattern → corrected=X, retracted=Y
      2. "no, X" / "actually X" → corrected=X, retracted from prior_lori_text
      3. "we only had N, not M" → corrected=N, retracted=M, field_hint=children
      4. "there was no Z" → retracted=Z, corrected=null (deletion intent)

    If a fact-shape (number, name, place, date) is detected, attach to
    field_hint via existing utterance_frame.candidate_fieldPaths logic.
    """
```

### 3b — Application layer (server-side)

In `chat_ws.py` correction dispatch path:

```python
if turn_mode == "correction":
    edit = parse_correction(user_text, prior_lori_text=last_assistant_text)
    if edit and edit.confidence != "low":
        # Apply to projection_json (provisional truth, no operator gate)
        from .projection_writer import apply_correction
        apply_correction(person_id, edit, source_turn_id=turn_id)
        # Mark transcript turn with correction metadata for operator review
        archive.append_event(..., meta={"correction_applied": True, "edit": edit.to_dict()})
```

`projection_writer.apply_correction()`:
- If `field_hint` is set: write `corrected_value` to `projection.fields[field_hint]`, source="correction", confidence=high
- If `retracted_value` is set: scan `projection.pendingSuggestions` for that value and remove
- Always emit `[projection][correction] applied edit fp=... corrected=...` log marker

### 3c — UI feedback

Lori's correction response should change from generic ("noted, let's continue") to specific ("Got it — I've changed that to two children. Apologies for the confusion."). New composer in `prompt_composer.py`:

```python
def compose_correction_response(narrator_text, edit_applied: Optional[CorrectionEdit]) -> str:
    if not edit_applied:
        return _generic_correction_ack()  # current behavior
    if edit_applied.corrected_value:
        return f"Got it — I've changed that to {edit_applied.corrected_value}. Apologies for the confusion."
    if edit_applied.retracted_value:
        return f"You're right — I shouldn't have said {edit_applied.retracted_value}. Thanks for catching that."
```

Composer drives the LLM with this text as a directive (so warm tone is preserved).

### 3d — Operator surface

Bug Panel correction queue: list every applied correction with the underlying turn audio (#58 audio_id linkage required) so operator can verify the parse landed correctly. Phase 3d only sensible after #58 frontend audio_id wiring lands.

## Acceptance gates

- 5/5 Melanie examples produce a CorrectionEdit with field_hint set OR confidence="low" (skip)
- "two children, not three" applies to `family.children` count without operator approval
- "there was no Hannah" removes "Hannah" from any pendingSuggestion containing it
- Lori's response text reflects the actual change ("Got it — I've changed that to two children")
- Pre-edit value preserved in correction_audit table for rollback (Phase 3e — out of scope here)

## Risks

- LLM-detected "corrections" that aren't actually corrections (false positives): mitigated by the existing strong-vs-weak detector + applying ONLY when `confidence != "low"`
- Cascading corrections (narrator corrects a corrected fact): handle via ordered audit chain
- Voice-driven corrections subject to STT errors compound with #55 phantom-proper-nouns (e.g., "I said hold my hand not Hannah" — STT might mishear THAT too): out of scope; #55 handles upstream

## Sequencing

Land after: #50 mic modal (so narrator can SEE what STT heard — prevents many corrections from being needed in the first place), #54 cross-session identity (✓ landed tonight), #58 audio_id linkage (✓ landed tonight backend; FE pending).

Estimated implementation: ~4–6 hours (correction_parser + projection_writer + composer + 5 unit tests + integration test against Melanie examples).
