# WO-EX-NESTED-BINDING-01 — Spec

**Status:** PARKED
**Blocked by:** ONE clean full-master SPANTAG lock (no regressions vs `r5h`; SPANTAG-off path byte-stable; SPANTAG-on path produces span inventory without breaking baseline).
**Supersedes:** `WO-EX-BINDING-01_Spec.md` after SPANTAG locks. Do NOT implement as a parallel lane.
**Date:** 2026-04-27.
**Conceptual anchor:** `docs/research/nested-extraction-architecture.md`.

---

## Core rule (read this first)

```
SPANTAG identifies evidence spans.
NESTED-BINDING groups spans into role-bearing relational elements.
LORI-CONFIRM / review tooling turns those elements into human-assessed candidates.
No final truth write is permitted in this WO.
```

NESTED-BINDING does not replace SPANTAG. It depends on SPANTAG. Without stable spans, role-bearing elements will be built on sand.

---

## Why this WO exists

The Hornelore extractor lane is locked at `r5h` 70/104 with the failure cluster dominated by wrong-entity / wrong-generation / fragment-drift cases. The current `BINDING-01` does **flat field binding** — it picks one `fieldPath` per item:

```
"We lived in Germany when the boys were small — Vincent was born there."
   ↓ flat binding
{ fieldPath: "residence.place", value: "Germany" }
{ fieldPath: "siblings.firstName", value: "Vincent" }
```

That representation cannot stop "Germany" from leaking into narrator `personal.placeOfBirth` because the relational context — *Germany is a place where a residence event happened, NOT the narrator's birthplace* — was never preserved.

The Nested Text Labelling paper names the architecture the lane has been groping toward. The fix is to **upgrade BINDING-01 from flat field binding to nested relational element binding**:

```
   ↓ nested binding
{
  element_type: "residence_event",
  spans: [
    { role: "place", text: "Germany" },
    { role: "time_context", text: "when the boys were small" },
    { role: "related_person", text: "Vincent" }
  ],
  overtext: { review_note, uncertainty_markers, needs_human_review: true }
}
```

The element TYPE constrains where its spans can promote. "Germany" is locked inside a `residence_event` and cannot promote to `personal.placeOfBirth`.

---

## Scope — IN

1. **Refactor `BINDING-01` into nested element binding.** Same place in the queue. Same WO number conceptually. New name. New JSON contract.
2. **Element type vocabulary.** Define the closed set of element types (residence_event, birth_event, education_event, etc.).
3. **Role vocabulary per element type.** Each type has a fixed set of allowed roles. `residence_event` allows `place`, `time_context`, `related_person`, `with_whom`. `birth_event` allows `subject`, `place`, `date`, `relation_to_narrator`. Etc.
4. **JSON contract for the extractor output.** Spans + elements + overtext. Backward-compat shim that down-projects to the legacy `{fieldPath, value, confidence}` shape until downstream consumers are migrated.
5. **`bio-builder-qc-pipeline.js` consumes elements, not facts.** Atomic-claim splitting now happens at element granularity, not span granularity.
6. **`bio-review.js` UI shows elements with roles.** Operator sees a single "residence in Germany when boys were small" candidate with three role-tagged spans, not three independent rows.
7. **Promotion is multi-target.** An element can suggest multiple `fieldPath` targets; operator picks which to promote.
8. **Five acceptance tests** (preserved from architectural review, listed below). All must PASS before this WO is called done.

---

## Scope — OUT

1. **No SPANTAG changes.** SPANTAG must already be locked.
2. **No LORI-CONFIRM changes.** LORI-CONFIRM continues to be the assessor / overtext deepening layer; that's a separate refactor *after* this one.
3. **No truth-write changes.** This WO is review-only. Phase F approved-only sync stays exactly where it is; nothing in NESTED-BINDING writes to `family_truth_promoted`.
4. **No real-world dataset.** Real-world data comes after this WO ships and SPANTAG holds. The 104-case master eval + targeted synthetic cases are the gate.
5. **No multi-assessor model yet.** Preserving multi-pass disagreement is a downstream LORI-CONFIRM upgrade, not part of this WO. (Note in the architecture doc; defer to a separate WO.)
6. **No new env flag.** This work happens inline in the extractor when SPANTAG=on. There is no `LOREVOX_NESTED_BINDING` flag — the moment NESTED-BINDING ships, it is the new contract under SPANTAG.
7. **No Lorevox v10 promotion.** This is bucket B (in flux); stays in Hornelore until proven against `r5h` baseline + the 5 acceptance tests + a follow-up master eval.

---

## Acceptance tests (preserved from architectural review)

These are fixtures NOW. Mark them parked. Activate when this WO opens (after SPANTAG locks).

### Test 1 — Wrong-entity firewall
**Input:** *"We lived in Germany when the boys were small — Vincent was born there."*

**PASS if:**
- One `residence_event` element is created with `place: "Germany"`, `time_context: "when the boys were small"`, `related_person: "Vincent"`.
- One `birth_event` element OR a relationship hint is created for Vincent born in Germany.

**FAIL if:**
- "Germany" is bound to narrator `personal.placeOfBirth`.
- Vincent is created as a free-floating sibling without the Germany linkage.
- The relational binding between place + time + person is lost.

### Test 2 — Uncertainty preservation
**Input:** *"I think it was 1962 when we moved."*

**PASS if:**
- `overtext.uncertainty_markers` contains "I think".
- `needs_human_review` is `true`.
- The 1962 date is held as a candidate, not promoted to locked truth.

**FAIL if:**
- The "I think" hedge is silently dropped.
- 1962 is promoted as a confirmed fact.
- The candidate is auto-approved.

### Test 3 — Sibling vs narrator firewall
**Input:** *"My older brother Vince was born in Germany."*

**PASS if:**
- A sibling/person element is created for Vince (with `older brother` qualifier preserved).
- A `birth_event` element exists with `subject: "Vince"`, `place: "Germany"`.

**FAIL if:**
- Narrator `personal.placeOfBirth` becomes Germany.
- The "older brother" qualifier is dropped.

### Test 4 — Multi-pass disagreement is signal, not noise
**Input:** Same source utterance, two extraction passes.

**PASS if:**
- Both markups are stored as separate assessor outputs (or, in this WO scope, the second pass is preserved with a `conflict_marker` if it diverges from the first).
- Disagreement is surfaced to the review queue.

**FAIL if:**
- The later pass silently overwrites the earlier pass.

(Note: full multi-assessor preservation is a LORI-CONFIRM-side upgrade. For NESTED-BINDING, the minimum is: when SPANTAG fires twice on the same source, conflicting role assignments produce a visible conflict marker on the element, not a silent overwrite.)

### Test 5 — Cross-turn element attachment
**Input:**
- Turn 1: *"We lived in the little house on 8th Street."*
- Turn 8: *"It had a red door."*

**PASS if:**
- Both spans can attach to the same `residence_event` element across turns.
- The 8th-Street residence carries `place: "8th Street house"`, `description: "red door"` after the second turn.

**FAIL if:**
- Turn 8 produces a standalone fragment with no link to Turn 1.
- Turn 8 creates a duplicate residence_event.

---

## File targets (for the post-SPANTAG-lock implementation)

```
server/code/api/routers/extract.py
  ├─ extend SPANTAG Pass 2 to emit elements + overtext, not flat items
  └─ keep down-projection shim for legacy callers until they migrate

server/code/api/prompt_composer.py
  └─ new prompt: "group spans into role-bearing elements" replaces
     "choose final field path"

ui/js/bio-builder-qc-pipeline.js
  ├─ atomicSplit() now operates on elements, not raw text
  ├─ buildElements() — new step: groups spans into role-bearing elements
  ├─ attachOvertext() — new step: review_note + uncertainty + conflict markers
  └─ existing duplicate/overlap comparison + provenance labeling
     migrated to element-aware

ui/js/bio-builder-candidates.js
  └─ candidate shape carries elements + spans + roles + overtext

ui/js/bio-review.js
  └─ render element with role-tagged spans; multi-target promotion picker

ui/js/projection-sync.js
  └─ accept multi-target promotion from elements (operator picks one)

tests/e2e/bio-builder-nested-extract.spec.js
  └─ new — 5 acceptance tests above

docs/architecture/nested-extraction.md
  └─ companion to docs/research/nested-extraction-architecture.md;
     post-implementation reference
```

---

## Element type vocabulary (initial closed set)

These names are stable; new types require an explicit WO addendum, not ad-hoc additions.

```
person_identity
family_relationship
birth_event
death_event
residence_event
education_event
work_event
marriage_event
migration_event
military_event
faith_event
medical_event
memory_scene
life_lesson
uncertain_claim
correction
```

Each type has a fixed role vocabulary. Example for `residence_event`:

```
roles:
  - place           (required)
  - time_context    (optional)
  - related_person  (optional, repeatable)
  - with_whom       (optional)
  - duration        (optional)
  - departure_reason (optional)
```

Full role vocabulary specced as part of this WO's implementation phase.

---

## JSON contract — element shape

```json
{
  "element_id": "el_001",
  "type": "residence_event",
  "element_tags": ["residence", "midlife"],
  "spans": [
    {
      "span_id": "sp_001",
      "text": "Germany",
      "start_char": 19,
      "end_char": 26,
      "role": "place",
      "tags": ["place"]
    },
    {
      "span_id": "sp_002",
      "text": "when the boys were small",
      "start_char": 27,
      "end_char": 51,
      "role": "time_context",
      "tags": ["time", "approximate"]
    },
    {
      "span_id": "sp_003",
      "text": "Vincent",
      "start_char": 55,
      "end_char": 62,
      "role": "related_person",
      "tags": ["person", "sibling"]
    }
  ],
  "candidate_summary": "The narrator lived in Germany when the boys were small; Vincent was born there.",
  "overtext": {
    "review_note": "Place is explicit. Time is approximate. Vincent's birth-in-Germany is implied, not stated.",
    "uncertainty_markers": ["when the boys were small"],
    "conflict_markers": [],
    "promotion_hint": "residence.place is high-confidence; siblings.{Vincent}.placeOfBirth needs operator confirmation.",
    "needs_human_review": true
  },
  "confidence": 0.78,
  "assessor": {
    "type": "model",
    "name": "lori_extractor_r6"
  },
  "review_status": "candidate",
  "suggested_promotion_targets": [
    "residence.place",
    "siblings.{Vincent}.placeOfBirth"
  ],
  "source_turn_id": "...",
  "source_text": "We lived in Germany when the boys were small — Vincent was born there."
}
```

---

## Acceptance gate (when the WO is allowed to be called done)

1. All 5 acceptance tests above PASS.
2. `r5h` master eval: NESTED-BINDING-on path scores ≥ 70/104 (no regression vs `r5h` baseline).
3. NESTED-BINDING-off path is byte-identical to `r5h` (the refactor is opt-in via existing SPANTAG flag; no new flag).
4. Per-element scorer reports are emitted in the master eval JSON output (so future WOs can target element-level failures, not just field-level).
5. Standard post-eval audit block (total / v2 / v3 / mnw / named flips / scorer-drift audit) clean.

---

## Sequencing reminder

```
1. Lock SPANTAG     ← BLOCKING, NOT DONE
2. NESTED-BINDING-01  ← THIS WO (parked)
3. LORI-CONFIRM v2  (assessor + overtext + multi-pass preservation)
4. Real-world shadow set (20-30 sanitized narrator turns)
5. Eval-driven refinement
```

Do not start step 2 until step 1 banks.

---

## Cross-references

- `docs/research/nested-extraction-architecture.md` — conceptual anchor, paper alignment, why role-bearing elements are the missing piece.
- `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` — canonical extractor architecture (Type A/B/C question typology, binding-layer-as-primary-failure-surface framing).
- `WO-EX-SPANTAG-01_FULL_WO.md` — current active WO; must lock before this opens.
- `WO-EX-BINDING-01_Spec.md` — superseded by this WO when SPANTAG locks. Keep the file for historical reference; mark superseded in CLAUDE.md changelog at refactor time.
- `WO-LORI-CONFIRM-01_PREP_PACK.md` — companion downstream layer (assessor + overtext); reframes after this WO ships.

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created PARKED. Sequencing rule locked: SPANTAG must lock before this opens. Five acceptance tests preserved as fixtures (parked). Supersedes `WO-EX-BINDING-01_Spec.md` upon refactor — no parallel lane. |
