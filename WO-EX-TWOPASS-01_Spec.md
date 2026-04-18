# WO-EX-TWOPASS-01 — Two-Pass Extraction Pipeline

**Status:** Specced
**Priority:** Next (after WO-EX-REROUTE-01, temp sweep complete)
**Estimated effort:** 2–3 sessions
**File scope:** `server/code/api/routers/extract.py`, `server/code/api/llm_interview.py`, new eval cases
**Feature flag:** `HORNELORE_TWOPASS_EXTRACT` (default 0)

---

## Problem Statement

Llama-3.1-8B-Instruct at 4-bit quantization performs poorly on single-pass extraction because one LLM call must simultaneously: read conversational text, identify factual spans, determine the correct fieldPath from 60+ options, and produce valid JSON. This cognitive overload produces three persistent failure categories:

- **schema_gap (14–15/52):** LLM invents fieldPaths that don't exist in EXTRACTABLE_FIELDS
- **hallucination (9–10/52):** LLM fabricates values not present in the narrator's answer
- **field_path_mismatch (7–9/52):** LLM picks a valid but semantically wrong fieldPath

Temperature tuning (0.01–0.15) proved these are systematic model-capacity errors, not sampling noise. The semantic rerouter (WO-EX-REROUTE-01) fixed 3 cases but can only address field_path_mismatch. The remaining 24 failures require architectural change.

### Evidence from Literature

- **Dligach et al. (2017):** XML-style argument tags outperform position embeddings for relation extraction. Raw tokens + explicit argument markup beat hand-engineered features.
- **Liu & Wang (2026):** Trigger words alone are insufficient; argument roles and node types improve extraction accuracy. Direction and role interactions must be explicitly modeled.
- **Khandelwal & Sawant (2020, NegBERT):** Negation is a dedicated problem of cue detection + scope resolution, not a side rule. Cues can be words, affixes, or discontinuous expressions; scope is the hard part.

### Core Hypothesis

Splitting extraction into two simpler tasks — (1) tag factual spans, (2) classify tagged spans to fields — will reduce all three failure categories because each pass has a narrower cognitive load and can be prompted/constrained independently.

---

## Architecture

### Current Pipeline (single-pass)

```
narrator answer → LLM (one call: find facts + pick fieldPaths + emit JSON) → JSON parse
→ semantic rerouter → birth-context filter → month-name sanity → field-value sanity
→ claims validators (shape + relation + confidence + negation guard)
```

### Proposed Pipeline (two-pass)

```
narrator answer → PASS 1: span tagger (LLM call #1)
→ intermediate span list (JSON)
→ PASS 2: field classifier (LLM call #2, or rule-based for simple mappings)
→ extraction items (same format as today)
→ semantic rerouter → birth-context filter → month-name sanity → field-value sanity
→ claims validators
```

Everything downstream of pass 2 is unchanged. The existing guard stack, rerouter, and validators all operate on the same `[{fieldPath, value, confidence}]` format.

---

## Pass 1: Span Tagger

### Input

- Narrator's answer (string)
- Current interview section (string, optional)

### Output — Intermediate Span Schema

ChatGPT's recommendation: compact JSON span list, not free-form XML. Easier to debug, eval, and pipe into pass 2.

```json
{
  "spans": [
    {
      "text": "my older brother Vincent",
      "type": "person",
      "role": "brother",
      "flags": ["family_member_not_narrator"]
    },
    {
      "text": "Germany",
      "type": "place"
    },
    {
      "text": "1960",
      "type": "time"
    },
    {
      "text": "a Golden Retriever named Ivan",
      "type": "pet",
      "flags": []
    },
    {
      "text": "I never served",
      "type": "event",
      "flags": ["negated"]
    }
  ]
}
```

### Span Types

| Type | Description | Examples |
|------|-------------|----------|
| `person` | Named or described person | "my dad John Smith", "my older sister" |
| `place` | Geographic location | "Spokane", "North Dakota", "Germany" |
| `time` | Date, year, period, duration | "1960", "from 1965 to 1968", "for thirty years" |
| `event` | Action, experience, milestone | "graduated from college", "had a heart attack" |
| `pet` | Animal owned or cared for | "a collie named Laddie", "barn cats" |
| `organization` | Named group, employer, institution | "the Lions Club", "Boeing", "St. Mary's Church" |
| `military` | Military-specific reference | "the Army", "Company G", "Sergeant" |
| `faith` | Religious or values reference | "Catholic", "church choir" |
| `health` | Medical or health reference | "heart attack", "diabetes" |
| `trait` | Personal attribute or skill | "stubborn", "good with numbers" |

### Span Flags

| Flag | When to apply |
|------|---------------|
| `negated` | Narrator explicitly denies: "I never...", "I didn't...", "we never had..." |
| `uncertain` | Hedging language: "I think maybe...", "probably around...", "I'm not sure but..." |
| `family_member_not_narrator` | Fact is about a family member, not the narrator being interviewed |

### Span Role (for `person` type only)

Free text from the narrator's words: "father", "mother", "older brother", "daughter", "wife", "grandmother on my mother's side", etc. Pass 2 uses this to route to the correct repeatable group.

### Pass 1 Prompt Design

The pass 1 prompt is deliberately schema-ignorant. It does NOT see EXTRACTABLE_FIELDS, fieldPaths, or writeMode. Its only job is: "What factual spans are in this text?"

```
System: You are a span tagger for oral history transcripts. Read the narrator's
answer and identify every factual span — people, places, times, events, pets,
organizations, military references, faith, health conditions, and personal traits.

Output a JSON object with a "spans" array. Each span has:
- "text": the exact words from the narrator (or minimal paraphrase)
- "type": one of person|place|time|event|pet|organization|military|faith|health|trait
- "role": (person type only) the relationship described: father, brother, wife, etc.
- "flags": array of zero or more: negated, uncertain, family_member_not_narrator

Rules:
- Only tag facts explicitly stated. Do not infer.
- "I never served in the military" → type=event, flags=["negated"]
- "My dad John" → type=person, role="father", flags=["family_member_not_narrator"]
- "I was born in Spokane" → type=place (Spokane) + type=event (born)
- If unsure whether something is a fact, include it with flags=["uncertain"]

Example — narrator says: "My older brother Vincent was stationed in Germany in 1960.
We had a Golden Retriever named Ivan."

Output:
{"spans":[
  {"text":"my older brother Vincent","type":"person","role":"brother","flags":["family_member_not_narrator"]},
  {"text":"Germany","type":"place","flags":[]},
  {"text":"1960","type":"time","flags":[]},
  {"text":"stationed","type":"military","flags":["family_member_not_narrator"]},
  {"text":"a Golden Retriever named Ivan","type":"pet","flags":[]}
]}
```

### Pass 1 Token Budget

Span tagging output is more compact than full extraction output (no fieldPaths, no confidence scores). Budget:

- Simple answers: 128 tokens (same as current simple cap)
- Compound answers: 256 tokens (lower than current 384 because no fieldPath text)

Use existing `_is_compound_answer()` detector.

### Pass 1 Temperature

0.15 (same as current extraction default). Span tagging is less sensitive to temperature than field classification because the output is closer to the input text.

---

## Pass 2: Field Classifier

### Input

- The span list from pass 1 (JSON)
- Current interview section (string)
- EXTRACTABLE_FIELDS catalog (the schema)

### Output

Standard extraction items: `[{fieldPath, value, confidence}]` — same format the rest of the pipeline already expects.

### Two Strategies for Pass 2

#### Strategy A: LLM-based classification (default)

A second LLM call that sees the tagged spans and the field catalog, and maps each span to the best fieldPath. This prompt is simpler than the current single-pass prompt because:

- It doesn't need to find facts (pass 1 did that)
- It doesn't need to handle negation (pass 1 flagged it)
- It doesn't need to distinguish narrator from family (pass 1 flagged it)
- It just needs to pick the right fieldPath for each span

```
System: Map each tagged span to the best fieldPath from this catalog.
Rules:
- Skip spans with flags=["negated"] — extract nothing for denied experiences
- For spans with flags=["family_member_not_narrator"], use family-scoped fields
  (parents.*, siblings.*, grandparents.*, family.children.*, family.spouse.*)
- For person spans: use "role" to pick the right family group
  (role=brother → siblings.*, role=father → parents.*, role=son → family.children.*)
- Confidence: 0.9 if span is clear, 0.7 if span has flags=["uncertain"]
- If no fieldPath fits, skip the span entirely

Available fieldPaths:
[compact catalog here]

Input spans:
[pass 1 output here]

Output a JSON array: [{fieldPath, value, confidence}]
```

#### Strategy B: Rule-based classification (for high-confidence mappings)

Some span-type → fieldPath mappings are deterministic and don't need an LLM:

| Span type + role | fieldPath | Condition |
|------------------|-----------|-----------|
| person, role=father/mother | parents.firstName | Extract name from text |
| person, role=brother/sister | siblings.firstName | Extract name from text |
| person, role=son/daughter | family.children.firstName | Extract name from text |
| person, role=wife/husband | family.spouse.firstName | Extract name from text |
| pet | pets.name + pets.species | Split name and species |
| military (not family) | military.branch / military.rank | Pattern match |
| faith | faith.denomination / faith.role | Pattern match |
| place + nearby event="born" | personal.placeOfBirth | Birth context |

Strategy B can handle the easy cases without burning a second LLM call. Only ambiguous spans (events, career references, compound person descriptions) need Strategy A.

### Recommended Approach: Hybrid

1. Run pass 1 (LLM call: span tagger)
2. Run rule-based classification on all spans (Strategy B)
3. For spans that Strategy B couldn't classify → run pass 2 LLM call (Strategy A)
4. Merge results

This minimizes latency: most extractions will only need one LLM call (pass 1) plus cheap rules. The second LLM call only fires when the rules can't handle a span.

---

## Integration Points

### `_extract_via_llm()` — Modified

```python
def _extract_via_llm(answer, current_section, current_target):
    if _twopass_enabled():
        return _extract_via_twopass(answer, current_section, current_target)
    else:
        # existing single-pass path (unchanged)
        return _extract_via_singlepass(answer, current_section, current_target)
```

The existing single-pass code moves into `_extract_via_singlepass()` untouched. The new `_extract_via_twopass()` function implements the two-pass flow.

### Feature Flag

```env
# WO-EX-TWOPASS-01 — Two-pass extraction pipeline.
# When 1, extraction uses span-tagger (pass 1) + field-classifier (pass 2)
# instead of single-pass LLM extraction. Falls back to single-pass on
# pass 1 failure.
HORNELORE_TWOPASS_EXTRACT=0
```

### Fallback Behavior

If pass 1 returns no spans or fails to parse:
1. Log the failure
2. Fall through to single-pass extraction (existing code)
3. Tag `extractionMethod` as `"llm"` (not `"twopass"`) so downstream can distinguish

If pass 1 succeeds but pass 2 (LLM) fails:
1. Use rule-based classification only
2. Tag `extractionMethod` as `"twopass_rules"`

If both passes succeed:
1. Tag `extractionMethod` as `"twopass"`

### Downstream Pipeline — No Changes

The semantic rerouter, birth-context filter, month-name sanity, field-value sanity, and claims validators all operate on `[{fieldPath, value, confidence}]`. They don't care how those items were produced. No changes needed.

---

## Eval Strategy

### New Eval Cases

Add 8–10 new eval cases specifically targeting two-pass strengths:

- Compound family descriptions ("My parents John and Mary had three kids...")
- Negated experiences ("I never served", "I've been pretty healthy")
- Mixed narrator/family facts ("I was born in Fargo, my dad was from Germany")
- Ambiguous career spans ("She worked as a teacher and later became principal")
- Pet descriptions embedded in hobby context
- Military service with rank, location, and dates interleaved

### A/B Eval Protocol

Run the full 52-case suite (plus new cases) with:
1. `HORNELORE_TWOPASS_EXTRACT=0` (single-pass baseline)
2. `HORNELORE_TWOPASS_EXTRACT=1` (two-pass)

Compare: pass rate, failure category distribution, average confidence, latency.

### Latency Measurement

Two LLM calls will be slower than one. Measure:
- Pass 1 generation time
- Rule-based classification time (should be <1ms)
- Pass 2 LLM generation time (when triggered)
- Total wall time vs. single-pass wall time

Acceptable latency increase: up to 2x is fine for extraction (it's not in the chat hot path — extraction runs asynchronously after each narrator turn).

---

## Implementation Phases

### Phase 1: Span Tagger (pass 1)

1. Write `_build_span_tagger_prompt()` — schema-ignorant prompt
2. Write `_extract_spans()` — calls LLM, parses span JSON
3. Write `_parse_span_json()` — validates span schema
4. Add intermediate span logging for debugging
5. Unit tests for span parsing

### Phase 2: Rule-Based Classifier (Strategy B)

1. Write `_classify_spans_rules()` — deterministic mappings
2. Handle person role → repeatable group routing
3. Handle negation flag → skip
4. Handle family_member_not_narrator flag → family-scoped fields
5. Unit tests for rule-based classification

### Phase 3: LLM Classifier (Strategy A)

1. Write `_build_field_classifier_prompt()` — sees spans + schema
2. Write `_classify_spans_llm()` — calls LLM for ambiguous spans
3. Write merge logic for rule + LLM classified items
4. Unit tests for LLM classification

### Phase 4: Integration & Eval

1. Wire `_extract_via_twopass()` into `_extract_via_llm()` behind feature flag
2. Add `extractionMethod` tagging
3. Add fallback path (pass 1 failure → single-pass)
4. Run full eval suite: single-pass vs. two-pass
5. Add new eval cases for two-pass-specific scenarios
6. Update HANDOFF.md

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Two LLM calls double latency | Hybrid approach: rule-based classification handles easy cases, LLM only fires for ambiguous spans |
| Pass 1 span tagger may be unreliable | Fallback to single-pass extraction. Feature flag allows instant rollback |
| Intermediate schema adds complexity | Span schema is deliberately minimal (10 types, 3 flags). JSON is self-validating |
| Rule-based classifier may miss edge cases | LLM classifier catches anything rules miss. Rules only handle high-confidence deterministic mappings |
| Prompt length for pass 2 (full catalog) | Pass 2 only sees the catalog, not the original answer or examples. Shorter than current single-pass prompt |

---

## Token Budget Analysis

### Current Single-Pass

- System prompt: ~2,500 tokens (catalog + examples + rules)
- User prompt: ~100–300 tokens (answer + context)
- Generation: 128–384 tokens
- **Total per extraction: ~2,700–3,200 tokens**

### Two-Pass

**Pass 1 (span tagger):**
- System prompt: ~500 tokens (no catalog, no examples beyond 1)
- User prompt: ~100–300 tokens
- Generation: 128–256 tokens
- **Subtotal: ~700–1,100 tokens**

**Pass 2 (field classifier, LLM path):**
- System prompt: ~1,200 tokens (catalog + mapping rules, no verbose examples)
- User prompt: ~200 tokens (span list from pass 1)
- Generation: 128–384 tokens
- **Subtotal: ~1,500–1,800 tokens**

**Two-pass total: ~2,200–2,900 tokens** — actually comparable to single-pass, because neither prompt needs to carry both the schema AND the extraction examples. The cognitive load splits cleanly.

---

## Success Criteria

- Pass rate improvement from 28/52 (54%) to ≥36/52 (69%) on the existing eval suite
- schema_gap failures reduced from 14–15 to ≤8 (pass 2 constrained to valid paths)
- hallucination failures reduced from 9–10 to ≤5 (pass 1 only tags explicit spans)
- field_path_mismatch failures ≤5 (pass 2 focused solely on classification)
- Zero regressions on currently-passing cases
- Latency ≤2x single-pass wall time

---

## References

- Dligach et al. (2017). "Neural Temporal Relation Extraction." EACL. → XML argument markup
- Liu & Wang (2026). "Event Relation Extraction Based on HGAN-EODI." TST. → Argument roles
- Khandelwal & Sawant (2020). "NegBERT." LREC. → Negation as dedicated problem
- Paolini et al. (2021). "TANL: Structured Prediction as Translation." EACL. → Augmented markup for extraction

All reference PDFs saved in `docs/references/`.
