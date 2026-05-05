# BUG-EX-POB-CORRECTION-WRONG-PATH-01 — Place-of-birth correction routes to `residence.place` instead of `personal.placeOfBirth`

**Title:** Route narrator-corrected birthplace ("Actually it's X, not just Y") back to `personal.placeOfBirth`, not to `residence.place`
**Status:** SCOPED — extractor binding-layer follow-up
**Date:** 2026-05-05
**Lane:** Extractor / Binding-layer cleanup
**Source:** TEST-23 v3 (2026-05-04). Mary's POB correction during onboarding.
**Blocks:** Nothing.
**Companion:** BUG-EX-PLACE-LASTNAME-01 (same Type C binding error class — narrator says "X" and the LLM picks the wrong slot for X).

---

## Mission

When the narrator corrects a previously-stated place of birth ("Actually
it's Minot, North Dakota — not just ND"), the LLM extracts the corrected
value to `residence.place` instead of `personal.placeOfBirth`. The
canonical path stays empty; the correction is preserved but in the
wrong slot. Lori's later memory_echo + era-walk logic both miss the
update because they read from `personal.placeOfBirth`.

This is a Type C binding error in the same family as
BUG-EX-PLACE-LASTNAME-01 — the LLM emits the value with high confidence,
but the routing decision picks a path that doesn't match the narrator's
correction intent.

## Live evidence

TEST-23 v3 telemetry (2026-05-04):

```
[mary/onboard/pob_correction]
  sent='Actually it's Minot, North Dakota — not just ND...'
  elapsed=12243ms

... later projection_json.fields (Mary):
  "personal.placeOfBirth": {"value": "Minot ND", ...}      ← original (stale)
  "residence.place":       {"value": "Minot, North Dakota", ...}  ← correction landed HERE
```

Expected: the corrected `"Minot, North Dakota"` value updates
`personal.placeOfBirth`. Actual: it lands in `residence.place`, leaving
canonical POB stale.

The "Actually..." prefix is a strong correction signal. The LLM
recognizes it (the value emerges with high confidence) but doesn't
re-target the original path.

## Locked design rules

1. **Correction signal must preserve target path.** When the narrator
   uses "actually it's", "no, it was", "I meant", "let me correct" plus
   a value that semantically matches the prior turn's `personal.*`
   field, the new value must update the SAME path, not a sibling.
2. **No prompt change.** Same posture as BUG-EX-PLACE-LASTNAME-01 — the
   guard is deterministic post-LLM, not a few-shot.
3. **Suggest_only on ambiguity.** If the prior turn established multiple
   place-typed paths (e.g., the narrator first stated a place of birth
   then a current residence), the correction guard downgrades to
   `suggest_only` rather than picking arbitrarily.
4. **Canonical paths win.** `personal.placeOfBirth` is canonical,
   `residence.place` is provisional/lifetime-track. When both are
   candidates and the prior turn established `personal.placeOfBirth`,
   the correction prefers canonical.

## Fix shape

Two-part patch in `server/code/api/routers/extract.py`:

### Part A — Correction-marker detection

Pre-LLM, classify the narrator turn as a correction when its first
clause matches `_CORRECTION_PREFIXES`:

```python
_CORRECTION_PREFIXES = re.compile(
    r"^\s*(actually|no,|wait,|let me correct|i meant|to be exact|"
    r"more precisely|sorry,?\s*it'?s|that should be)\b",
    re.IGNORECASE,
)
```

When `_is_correction_turn(text)` is True, set a `correction=True` flag
on the extraction request; thread through to the rules-fallback +
post-LLM stages.

### Part B — Correction-aware path stickiness

When `correction=True` AND the prior turn's accepted items included a
`personal.placeOfBirth` value AND the current LLM emission has a
`residence.place` (or any place-typed sibling) value that semantically
matches the corrected text, REWRITE the fieldPath from `residence.place`
to `personal.placeOfBirth` and emit:

```
[extract][POB-CORRECTION] rewrite residence.place → personal.placeOfBirth
  value=<X> reason=correction_marker prior_turn_path=personal.placeOfBirth
```

Same logic for `personal.dateOfBirth` correction → don't let it land in
`personal.notes`. Same for `personal.fullName` → don't let it drift to
`personal.preferredName`.

## Acceptance

- TEST-23 v3 rerun: Mary's "Actually it's Minot, North Dakota..." turn
  produces `personal.placeOfBirth="Minot, North Dakota"` (overwriting
  the prior "Minot ND") and zero items at `residence.place`.
- Synthetic fixture `case_112_pob_correction` asserts must-extract
  `personal.placeOfBirth=Minot, North Dakota` AND must-not-write on
  `residence.place=Minot, North Dakota`.
- master eval r5h-followup-guard-v1 stays at 78/114 (no existing case
  in the 114 exercises the correction-marker class).
- Live re-run: Mary post-restart memory_echo shows "Minot, North Dakota"
  on her POB line.

## Scope estimate

~1 hour. Single-file diff (regex constant + two helper functions + 2
fixtures), no schema change, no prompt change.

## Related

- **BUG-EX-PLACE-LASTNAME-01** (already shipped) — same Type C binding
  error class, different conversational shape.
- **WO-LORI-CONFIRM-01** prep pack — corrections as a confirmation
  surface; this WO complements that lane by ensuring corrections that
  *do* arrive land in the right slot.
- Architecture Spec v1 §7.1 (Binding-layer failures, Type C).
