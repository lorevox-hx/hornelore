# Nested Extraction Architecture — Research Note

**Status:** Conceptual anchor. No implementation yet. Companion to `WO-EX-NESTED-BINDING-01_Spec.md` (PARKED).
**Date:** 2026-04-27.
**Source paper:** *Nested Text Labelling* (uploaded to session, 2026-04-27).

---

## Why this note exists

The Hornelore extractor lane has been climbing the same hill for months — `r5h` is locked at 70/104, the failure cluster is dominated by wrong-entity / wrong-generation / fragment-drift cases, and each WO has chipped away at one symptom without resolving the underlying frame. The Nested Text Labelling paper names the architecture the lane has been groping toward.

**Important framing note.** SPANTAG, BINDING, and the planned NESTED-BINDING refactor are not Lorevox inventions — they are our *productized versions* of established techniques in the span labeling / span-based extraction literature. The literature uses custom span markers (e.g. `@@evidence##`), constrained span decoding, and the broader pattern of separating evidence identification from field assignment. SPANTAG is our internal name for the Lorevox implementation of that pattern. The Nested Text Labelling paper supplies the formal three-level vocabulary; the broader span-labeling literature supplies the pass-based approach. See `docs/research/references.md` for the canonical sourcing trail and the boundary between borrowed method and reserved Lorevox expression.

The bumper sticker is short:

> **Don't extract final facts.
> Extract evidence spans first.
> Then group spans into role-bearing relational elements.
> Then attach overtext (assessor / context / uncertainty).
> Then let human review promote the element into truth.**

That is what `bio-builder-qc-pipeline.js`, the `extract.py` SPANTAG / BINDING / LORI-CONFIRM stack, and the four-layer family-truth pipeline are all reaching for. The paper supplies the vocabulary.

---

## The paper's three levels

| Level | What it is | What it produces |
|---|---|---|
| **I — Spans** | Highlight a section of text. Categorize it. | `{span_id, text, char range, tags[]}` — pure evidence, no field path, no truth claim. |
| **II — Elements** | Group related spans. Each span plays a *role* inside a larger structure. | `{element_id, type, spans[], roles, candidate_summary}` — relational, but still review-only. |
| **III — Assessor / Overtext** | Mark *who* annotated and *why*. Add commentary, uncertainty, conflict. | `{assessor, review_note, confidence, conflict_markers, needs_human_review}` — a layer ABOUT the annotation, not the annotation itself. |

Critical: levels are additive. A Level III markup is still a Level I + II markup; it just carries extra fields. Two assessors can annotate the same source and have their disagreements preserved as separate Level III markups instead of one silently overwriting the other.

---

## Mapping to existing Hornelore extractor work

| Paper level | Closest existing WO / surface | Status today | Gap |
|---|---|---|---|
| Level I — Spans | **WO-EX-SPANTAG-01** (active) | Pass 1 emits a schema-blind tag inventory; eval inconclusive (needs one clean full-master run with flag confirmed firing server-side). | The mechanism is in place. Lock it before doing anything else. |
| Level II — Elements with roles | **WO-EX-BINDING-01** (specced, post-SPANTAG) | Today's `BINDING-01` does *flat field binding* — chooses a `fieldPath` for each item. It does NOT group spans into a single element with internal roles. | This is the missing layer. "Germany" should be a `place` role inside a `residence_event` element, not a standalone `residence.place` field write. |
| Level III — Assessor / overtext / review | **WO-LORI-CONFIRM-01** (parked, v1 spec) + **#94 alt_defensible_paths** (scorer-side already) + **bio-review.js** | Partial. Multi-turn confirmation exists in spec; alt-defensible scoring exists in eval; review queue exists in UI. But there's no first-class `assessor` field, no preserved multi-pass disagreement, and overtext is implicit (model says "I think 1962" but the extractor doesn't capture "I think" as an uncertainty marker). | Make assessor + overtext explicit. Stop dropping uncertainty markers. |

So the architecture is **partly there**. SPANTAG covers Level I. BINDING-01 stops at flat field binding (a degenerate Level II — an element whose only role is "value"). LORI-CONFIRM + bio-review are heading toward Level III but lack the formal assessor / overtext model.

---

## The genuinely missing piece — role-bearing elements

Today's `BINDING-01` proposes:

```
"We lived in Germany when the boys were small — Vincent was born there."
   ↓ flat binding
{ fieldPath: "residence.place", value: "Germany" }
{ fieldPath: "siblings.firstName", value: "Vincent" }
```

The fragment-drift this produces is exactly the wrong-entity failure pattern in the eval: "Germany" can land in narrator `personal.placeOfBirth` because the binder lost the relational context. Vincent ends up as a free-floating sibling without the birth-in-Germany linkage.

The nested-element model proposes instead:

```
{
  "element_id": "el_001",
  "type": "residence_event",
  "spans": [
    { "role": "place",          "text": "Germany",                     "tags": ["place"] },
    { "role": "time_context",   "text": "when the boys were small",    "tags": ["time", "approximate"] },
    { "role": "related_person", "text": "Vincent",                     "tags": ["person", "sibling"] }
  ],
  "candidate_summary": "The narrator lived in Germany when the boys were small; Vincent was born there.",
  "overtext": {
    "review_note": "Place is explicit. Time is approximate. Vincent's birth-in-Germany is implied, not stated; needs human review.",
    "uncertainty_markers": ["when the boys were small"],
    "needs_human_review": true,
    "suggested_promotion_targets": [
      "residence.place",
      "siblings.{Vincent}.placeOfBirth"
    ]
  },
  "confidence": 0.78,
  "assessor": { "type": "model", "name": "lori_extractor_r6" }
}
```

Critical differences vs flat binding:

1. **Germany cannot land in narrator's `personal.placeOfBirth`** because Germany is locked inside a `residence_event` element with role `place`. The element's TYPE constrains where its spans can promote.
2. **Vincent's relationship to Germany is preserved** as a relational binding, not two independent flat writes that lose the link.
3. **The review note is visible auditable text**, not hidden chain-of-thought. An operator reading the candidate can see why the model flagged uncertainty.
4. **Promotion is multi-target with operator choice**. The element suggests `residence.place` AND `siblings.{Vincent}.placeOfBirth`; a human picks which to promote. No silent guess.

---

## What's NOT new from the paper

- **Span-only extraction** — already in SPANTAG.
- **Truth governance with human-in-the-loop** — already in WO-13's four-layer pipeline.
- **Provenance / source attribution** — already in `family_truth_notes` and `bio-builder-qc-pipeline.js`.
- **Confidence scoring** — already emitted by extract.py.

What IS new:

- **Roles within elements** (place / time_context / related_person / target_subject / etc.).
- **Multi-assessor first-class** — preserve disagreement instead of clobbering.
- **Overtext as structured field** — uncertainty markers, conflict markers, review notes, promotion hints.
- **Element-typed routing** — the element TYPE constrains which fieldPaths its spans can promote to.

These four are what the upgrade buys.

---

## Why NOT a separate parallel lane

The Boris-style instinct is to mint `WO-NESTED-EXTRACT-01` as a new lane sitting next to BINDING-01. **Don't.** Reasons:

1. **The paper does not introduce a fourth independent layer.** Levels I/II/III are the same chain we already have, just clarified. Stacking a new layer on top would be cargo-cult.
2. **It would fragment the extractor lane.** The existing WO ladder (SPANTAG → BINDING → LORI-CONFIRM) is already the right shape; the upgrade refines the middle step, not adds a sidecar.
3. **The eval would have two parallel scoring stories** — one for flat binding, one for nested binding. Bisect surface dies.
4. **It leaks into the lab/gold framing wrong.** A parallel lane implies the existing one is wrong; a refactor of the existing lane preserves the trail of evidence in the changelog.

Correct sequence:

1. **Lock SPANTAG.** One clean full-master run with the flag confirmed firing server-side. No regressions vs `r5h` baseline. SPANTAG-off path stays byte-stable.
2. **Refactor BINDING-01 into NESTED-BINDING-01.** Same WO number, same place in the queue, new vocabulary, new contract. Old BINDING-01 spec is superseded; the new spec at `WO-EX-NESTED-BINDING-01_Spec.md` is what BINDING-01 should have been.
3. **Reframe LORI-CONFIRM as the assessor / overtext layer.** No new mint; just deepen the spec to include explicit `assessor` field, multi-pass preservation, and overtext fields.
4. **Rename `bio-builder-qc-pipeline.js`'s candidate shape** to carry roles + overtext — no new file, just a richer JSON shape.

---

## Where the paper's vocabulary lands in our codebase

| Paper term | Hornelore home (today / future) |
|---|---|
| Span | `extract.py` SPANTAG Pass 1 output |
| Element | `bio-builder-qc-pipeline.js` candidate (refactored to carry roles) |
| Role | new field on each span inside an element |
| Assessor | new top-level field on every candidate (`{type: "model" | "human" | "import", name}`) |
| Overtext | new structured block carrying `review_note`, `uncertainty_markers`, `conflict_markers`, `promotion_hint`, `needs_review` |
| Markup | one assessor's full annotation of a source utterance (= one candidate today, but carrying assessor + overtext) |
| Multi-pass disagreement | second extraction pass stored as a separate markup, with a conflict marker if it diverges |

---

## Real-world data — when and how

Real narrator data helps the lane *after* SPANTAG locks, not before. Without stable spans, real-world failure cases pile noise on top of an unstable substrate.

When to add it:

1. SPANTAG locks (one clean full-master, no regressions).
2. Build a small **real-world shadow set** — 20-30 narrator turns from the actual Horne-family parent sessions (sanitized; no PII outside the family).
3. Hand-label the spans (place / time / person / event / role) without picking field paths yet.
4. Run SPANTAG against it.
5. Use failures to tune span tagging — the goal is failure coverage, not raw volume.

What the real-world set should target:

- Messy speech (filler words, restarts, "um")
- Uncertain dates ("I think it was '62", "around when the boys were small")
- Family nicknames (Vince / Vincent / Vinny)
- Partial names ("Mom", "my brother", "the older one")
- Cross-turn memories ("the little house on 8th Street" + later "it had a red door")
- Wrong-entity cases (place mentioned in same breath as different person)
- Relationship ambiguity ("my husband's brother" vs "my brother-in-law" vs "Bill")
- Place / date drift (narrator confuses two similar events)

What the dataset shape should be:

```
{
  "case_id": "real_001",
  "raw_utterance": "...",
  "expected_spans": [
    { "text": "Germany", "role": "place" },
    { "text": "when the boys were small", "role": "time_context" },
    { "text": "Vincent", "role": "related_person" }
  ],
  "do_not_tag": ["lived"],
  "ambiguity_notes": "Time is approximate; Vincent's birth-in-Germany is implicit"
}
```

No final field paths in the dataset. That comes after nested binding.

---

## What this note does NOT do

- Does not modify any code.
- Does not change extractor behavior.
- Does not start a parallel implementation lane.
- Does not modify `WO-EX-BINDING-01_Spec.md` or the canonical Architecture Spec v1.
- Does not write a real-world dataset.

It is purely an architectural anchor for future-Chris. The actionable companion is `WO-EX-NESTED-BINDING-01_Spec.md` (PARKED).

---

## Cross-references

- Canonical extractor architecture: `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`
- Active SPANTAG WO: `WO-EX-SPANTAG-01_FULL_WO.md`
- Current BINDING-01 spec (to be superseded once SPANTAG locks): `WO-EX-BINDING-01_Spec.md`
- This refactor's spec (PARKED): `WO-EX-NESTED-BINDING-01_Spec.md`
- LORI-CONFIRM prep pack: `WO-LORI-CONFIRM-01_PREP_PACK.md`
- Source paper: uploaded to session 2026-04-27 (Nested Text Labelling)

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created. Captures the alignment between the Nested Text Labelling paper and the Hornelore extractor lane. Names role-bearing relational elements as the genuinely missing layer. Locks the sequencing rule: SPANTAG must lock before BINDING-01 refactors into NESTED-BINDING-01. Companion WO spec parked. |
