# WO-EX-01 — Extractor birth-place tightening

**Status:** Complete
**Owner area:** `server/code/api/routers/extract.py`

---

## Trigger

Live operator-path bug observed 2026-04-14:

> Narrator (Chris) said: *"It was different. When I was in kindergarten we
> lived in west Fargo in a trailer court. My parents were going to school
> at NDSU."*
>
> Extractor proposed: `personal.placeOfBirth = west Fargo`
>
> But Chris's promoted `placeOfBirth` is *Williston, North Dakota*. The
> conversation was in the **School Years** section, not anywhere near a
> birth-related question.

The proposal surfaced in the operator review queue as approve-able, generating
review friction for a clearly-wrong fact.

## Root cause (two layers)

**Layer 1 — verb conflation in the regex** (`extract.py` line ~516):

```python
_PLACE_BORN = re.compile(
    r'\b(?:born|raised|grew up|lived)\s+(?:\w+\s+)*?(?:in|at|near)\s+'
    ...
)
```

`lived in [place]` is residence semantics, not birth-place semantics. The
regex conflated them.

**Layer 2 — no era awareness in the rules path.** The LLM extractor (`_build_extraction_prompt`)
already receives `current_section` and uses it as context. The rules
extractor (`_extract_via_rules`) ignored `current_section` entirely. So
even when the interview was deep in School Years, the rules path still
fired birth-place patterns from any matching narrator phrase.

## Fix

Two surgical changes in `server/code/api/routers/extract.py`.

**Change 1: drop `lived` from `_PLACE_BORN`.**

```python
_PLACE_BORN = re.compile(
    r'\b(?:born|raised|grew up)\s+(?:\w+\s+)*?(?:in|at|near)\s+'
    r'([A-Z][a-zA-Z\s,]+?)'
    r'(?:\.|,?\s+(?:(?:and|my|I|we|the|where|when)\b|\d))',
    re.IGNORECASE
)
```

`born`/`raised`/`grew up` still correlate with birth-place strongly enough to
keep. `lived` is too general; it's the actual culprit.

**Change 2: add an era guard for the rules path.**

```python
_BIRTH_CONTEXT_SECTIONS = {
    "early_childhood",
    "earliest_memories",
    "personal",
    None,            # backward compat — no section info → permissive
}

def _is_birth_context(current_section: Optional[str]) -> bool:
    if current_section is None:
        return True
    return current_section.lower() in _BIRTH_CONTEXT_SECTIONS
```

Then `_extract_via_rules` reads the section once and gates both
`personal.dateOfBirth` and `personal.placeOfBirth` extractions:

```python
in_birth_context = _is_birth_context(current_section)
...
if in_birth_context:
    m = _DATE_FULL.search(answer)
    ...
if in_birth_context:
    m = _PLACE_BORN.search(answer)
    ...
```

When the interview is in School Years (or any non-birth section), birth-related
extractions don't fire from the rules path at all. The LLM path already had
this awareness via the prompt; this brings the rules path into parity.

## Backward compatibility

- `current_section=None` is treated as permissive (current behavior preserved).
- Other extractions (parents, siblings, education, hobbies) are unchanged.
- The LLM extraction path is unchanged — it already had era awareness.
- Protected-identity promotion guards in `family_truth.py` are unchanged —
  they remain the second line of defense.

## Acceptance test (manual)

After deploying:

1. Open Chris in the UI, navigate to a School Years question.
2. Type: *"We lived in West Fargo in a trailer court."*
3. **Expected:** no `personal.placeOfBirth` proposal in the operator review queue.
4. **Counter-test:** open a fresh narrator, ask a birth question (or set
   `current_section="early_childhood"`), say *"I was born in Helena, Montana."*
5. **Expected:** `personal.placeOfBirth = Helena, Montana` proposal appears.

## Why this matters

This is the smallest possible fix to the immediate operator-friction bug.
The structural answer (life-phase derivation that grounds the extractor in
real age math) is **WO-LIFE-SPINE-01**, shipping next. WO-EX-01 stops the
bleeding now; WO-LIFE-SPINE-01 prevents the whole class of future
verb-pattern false positives.

## Follow-ups (not in scope here)

- **WO-EX-02** (deferred): conflict detection in the proposal layer. When a
  new proposal contradicts existing promoted truth on a protected identity
  field, mark as `needs_verify_conflict` and route to the conflict console
  rather than the normal review queue. Needs per-field normalizers (so
  "Williston, ND" and "Williston, North Dakota" don't read as a conflict).
- **WO-EX-03A** (deferred): event-bundle extraction. Modify the LLM
  extraction prompt so multi-fact statements ("I worked at Exxon in Houston
  in 1985") return as linked event objects, not scattered fields. LLM-prompt
  upgrade only — no naive Python string parsing.
