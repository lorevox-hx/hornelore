# BUG-EX-LLM-COMMENTARY-AS-VALUE-01 — LLM emits explanatory commentary in `value` field instead of an actual value or null

**Title:** Drop / suggest_only LLM-emitted items whose `value` is meta-commentary about the absence of data, not the data itself
**Status:** SCOPED — small, additive, eval-gated
**Date:** 2026-05-05
**Lane:** Extractor / Post-LLM validator
**Source:** TEST-23 v4 (2026-05-04). Marvin's spouse-status turn during pass2a building_years.
**Blocks:** Nothing.
**Related:** Architecture Spec v1 §7.1 (Type C binding errors); WO-EX-BINDING-01 (same lane).

---

## Mission

When the LLM is asked about a field whose value isn't explicitly stated
in the narrator's answer, it sometimes emits the field with a string
that explains *why* the value is missing — e.g.:

```json
{"fieldPath": "family.spouse.firstName",
 "value": "Wife's first name is implied, not explicitly stated.",
 "confidence": 0.7}
```

That string then survives validation (it's a non-empty string, the field
path is in EXTRACTABLE_FIELDS), gets length-normalized via Patch H
(`R4-H normalise family.spouse.firstName: "...stated." → "...stated"`),
and lands in `interview_projections.projection_json.fields` as if it
were Marvin's wife's actual first name. Lori's downstream readers then
see "Marvin's wife's first name is: Wife's first name is implied..."
which is exactly the kind of system-tone garbage that locked principle
#3 (no system-tone narrator outputs) is meant to prevent.

## Live evidence

TEST-23 v4 (2026-05-04 21:42:15):

```
[extract-parse] Raw LLM output (475 chars): Here is the extracted JSON array:
[
  {"fieldPath": "family.spouse.firstName",
   "value": "Wife's first name is implied, not explicitly stated.",
   "confidence": 0.7},
  {"fieldPath": "family.children.relation",
   "value": "Children are implied, not explicitly stated.",
   "confidence": 0.7},
  {"fieldPath": "family.children.count",
   "value": "Multiple children are implied, not explicitly stated.",
   "confidence": 0.7}
]
```

Three items, three pieces of meta-commentary. The validator dropped one
(`family.children.count` — not in EXTRACTABLE_FIELDS) and the
WO-CLAIMS-02 relation allowlist dropped another (`family.children.relation`).
But the spouse.firstName one slipped through because:

1. `family.spouse.firstName` IS in EXTRACTABLE_FIELDS (real schema field)
2. The string is non-empty and longer than the 3-char SHORT_VALUE_EXEMPT threshold
3. Patch H length-normalization just trimmed the trailing period

Final accepted item: `family.spouse.firstName="Wife's first name is implied, not explicitly stated"`.

## Locked design rules

1. **Drop the meta-commentary class entirely.** If the value is a
   sentence about the absence of data, it's not the data — it should
   produce zero items, same as if the LLM had returned an empty array.
2. **No prompt change.** Hardening the prompt to "never emit
   commentary" hasn't worked across multiple iterations
   (BUG-LORI-REFLECTION-02 lessons). This must be a deterministic
   post-LLM filter.
3. **Pattern-based, not LLM-judged.** A small pattern set covers >90%
   of the observed shape. False positives (a real narrator surname that
   happens to contain "implied") are vanishingly rare; the alt-credit
   path remains for genuine values.
4. **Log every drop.** `[extract][COMMENTARY-DROP] fieldPath=<X> value=<Y>`
   so we can audit drift if narrator answers ever start hitting the
   pattern legitimately.

## Fix shape

Single new validator in `server/code/api/routers/extract.py`, runs
after the EXTRACTABLE_FIELDS check, before Patch H normalization:

```python
_LLM_COMMENTARY_PATTERNS = re.compile(
    r"\b("
    r"(is|are|was|were)\s+(implied|inferred|assumed|not\s+(explicitly\s+)?stated|"
    r"unknown|not\s+specified|not\s+provided|"
    r"likely|possibly|presumably)|"
    r"(no|none|nothing)\s+(stated|provided|specified|mentioned|extracted)|"
    r"(narrator|user|speaker)\s+(does\s+not|doesn'?t|did\s+not|didn'?t)\s+"
    r"(say|state|mention|provide|specify)|"
    r"information\s+(is\s+)?(missing|absent|unavailable|not\s+available)|"
    r"context\s+suggests|"
    r"based\s+on\s+the\s+(provided|given)\s+(text|answer|context)"
    r")\b",
    re.IGNORECASE,
)

def _is_llm_commentary(value: str) -> bool:
    """True if the value reads like LLM meta-commentary about the
    absence of data, not the data itself."""
    if not value or not isinstance(value, str):
        return False
    if len(value) < 12:
        return False  # Too short to be a sentence
    return bool(_LLM_COMMENTARY_PATTERNS.search(value))
```

In the per-item validation loop (post EXTRACTABLE_FIELDS, pre Patch H):

```python
if _is_llm_commentary(item["value"]):
    logger.info(
        "[extract][COMMENTARY-DROP] fieldPath=%s value=%r",
        item["fieldPath"], item["value"][:80]
    )
    continue
```

## Acceptance

- The exact TEST-23 v4 spouse-firstName item is dropped at parse time;
  zero accepted items from that LLM emission.
- master eval r5h-followup-guard-v1 stays at 78/114 (no existing case
  emits commentary at this length-and-pattern shape).
- New fixtures `case_113_commentary_spouse`, `case_114_commentary_children`
  assert must-not-write on the meta-commentary outputs.
- Live re-run: Marvin's spouse status turn produces zero
  `family.spouse.firstName` candidates, leaving canonical empty (which
  is the correct outcome — Marvin's wife's name was never stated).

## Scope estimate

~30 minutes. Single regex constant + 8-line validator function + 3-line
loop integration + 2 fixtures.

## Related

- WO-CLAIMS-02 — the claims-validator already drops some
  meta-commentary subclasses (the `family.children.relation` one); this
  WO extends the same posture to bare scalar fields.
- BUG-EX-PLACE-LASTNAME-01 — same fix posture (deterministic post-LLM
  drop, narrow pattern, no prompt change).
- Architecture Spec v1 §7.1 — Type C binding errors. This is technically
  not a binding error (the path is correct; the value is the problem),
  but the fix posture is identical: deterministic post-LLM repair.
