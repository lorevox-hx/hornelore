# Lorevox / Hornelore Research References

**Purpose:** A canonical reference list for the external research that informs the Lorevox extractor lane, truth-governance architecture, and cognitive-support model. Maintained as papers / posts / source material come in.

**Convention:** each entry carries a short *Why it matters to Lorevox* paragraph and a *Wired (or to be wired) at* pointer. New entries land at the top of their topic section so the most recent thinking is on top.

**On naming:** Several of our internal WO names are productized versions of established methods. This is not theft and not novelty — it's how a working product names the patterns it depends on. The reference list is where those mappings live.

**PDF preservation:** PDF copies of cited papers, when retained for offline reading, live in `docs/research/papers/` (gitignored). The reference list links to canonical external sources (DOI, arXiv, publisher URL) where available so the canonical record doesn't depend on local copies.

---

## Topic A — Span labeling / span-based extraction

This is the family of techniques where a model first marks **the exact text spans that support an extraction**, then binds those spans to labels or fields. The literature describes custom span markers (e.g. `@@ ... ##`), constrained span decoding for LLM-based labeling, and the broader pattern of separating evidence identification from field assignment.

**Why this matters to Lorevox:** our biggest extraction failure mode is the model jumping straight to a field path without first proving what words caused it. Span labeling forces "show me the words, then tell me where they belong" — which is exactly the firewall against wrong-entity / wrong-generation / fragment-drift cases that the 104-case master eval keeps surfacing.

**SPANTAG is our productized name for this method.** Concretely it means:

1. Tag the evidence first. "John Michael Shong was from Alsace-Lorraine" gets marked as the source span.
2. Then bind it to the schema. Example: `greatGrandparents.ancestry`, not randomly `grandparents.ancestry`.
3. Store provenance. The extraction carries the actual quoted span, not just the guessed field.

Wired at: `WO-EX-SPANTAG-01_FULL_WO.md` (active, eval inconclusive — needs one clean full-master lock with flag confirmed firing server-side). Followed by `WO-EX-NESTED-BINDING-01_Spec.md` (PARKED — superseded BINDING-01 once SPANTAG locks).

### Entries

#### Nested Text Labelling — paper foundational to NESTED-BINDING refactor

- **Source:** uploaded to session 2026-04-27 (`21477_Nested_Text_Labelling_St.pdf`).
- **Local copy:** `docs/research/papers/21477_Nested_Text_Labelling_St.pdf` (gitignored; preserve locally).
- **Core argument:** semantic annotation can be built from four basic operations — highlighting a section of text, categorizing it, linking spans, and providing commentary. Specifies a three-level model: (I) spans, (II) elements composed of role-bearing spans, (III) assessor + overtext + context.
- **Why it matters to Lorevox:** names the architecture the extractor lane has been groping toward. Levels I/II/III map cleanly onto SPANTAG / BINDING / LORI-CONFIRM. The genuinely missing piece — role-bearing relational elements (e.g. "Germany" plays role `place` inside a `residence_event`, not a flat `residence.place` field write) — is what `WO-EX-NESTED-BINDING-01` is designed to add.
- **Wired at:** `docs/research/nested-extraction-architecture.md` (conceptual anchor, written 2026-04-27). `WO-EX-NESTED-BINDING-01_Spec.md` (PARKED; opens after SPANTAG locks).
- **Boundary:** copyright protects expressive implementation, not abstract methodology. Lorevox borrows the formal model and produces its own implementation with Lorevox-specific element types (residence_event, birth_event, etc.), Lorevox-specific overtext fields (uncertainty markers, conflict markers, suggested_promotion_targets), and Lorevox-specific assessor model. The expression in this codebase is reserved per LICENSE; the underlying method described in the paper is not.

#### Span labeling broadly (custom span markers, constrained span decoding)

- **Source:** general literature in NLP / information-extraction. Specific citations to be added as identified during further reading.
- **Core argument:** LLMs can be made more reliable for extraction by first marking exact text spans that support an extraction (often using custom delimiters like `@@evidence##` or constrained decoding that requires output spans match input character ranges), then binding those spans to labels.
- **Why it matters to Lorevox:** validates SPANTAG's design rationale. Pass 1's job is span identification with delimiters; Pass 2's job is span-to-schema binding. The technique is established; we are implementing the productized version.
- **Wired at:** `WO-EX-SPANTAG-01_FULL_WO.md`, `extract.py` SPANTAG Pass 1 + Pass 2.
- **TODO:** as specific citations are identified (during the SPANTAG-lock evaluation phase), add concrete entries above this generic note. Targets to look for: papers on LLM-based span tagging with delimiter prompts, constrained decoding for span extraction, evaluation methodology for span-level F1 vs field-level accuracy.

---

## Topic B — Truth governance, candidate-vs-fact boundaries, human-in-the-loop annotation

This is the family of techniques and practices around **separating AI suggestions from confirmed truth**, with explicit review queues, provenance, and approve/reject workflows. Foundational for memoir / family-history work where a hallucinated date is worse than no date.

**Why this matters to Lorevox:** the four-layer family-truth pipeline (shadow archive → proposal → human review → promoted truth) and Phase F approved-only downstream sync are the operational embodiment of this principle. The principle predates Lorevox; the implementation is reserved per LICENSE.

### Entries

*(none yet — to be added as references are identified. Targets: human-in-the-loop annotation literature; provenance models in digital humanities; consensus-based annotation for ambiguous data; assessor-disagreement preservation; weak supervision and the candidate-vs-truth separation pattern.)*

---

## Topic C — Older-adult HCI, dementia-safe pacing, life review

This is the family of work around **occupational therapy / life-review practice** that informs the Cognitive Support Model (WO-10C) and the Lori interviewer's behavioral directives.

**Why this matters to Lorevox:** the six dementia-safe behavioral guarantees (protected silence at 120s/300s/600s, invitational re-entry, no correction, single-thread context, visual-as-patience, invitational prompts) are operational versions of OT/life-review research practice. The pattern is established; the prompt-text implementation is reserved per LICENSE.

### Entries

*(none yet — to be added. Targets: Iwama Kawa Model literature; reminiscence therapy research; trauma-informed interviewing in geriatrics; pacing studies for older-adult conversation; life-review intervention efficacy.)*

---

## Topic D — Affect / facial expression / consent and privacy

This is the family of work around **deriving affect signals from facial-expression data while preserving consent and not transmitting raw data**. Informs the MediaPipe → affect → runtime71 pipeline.

**Why this matters to Lorevox:** the no-video-leaves-the-browser boundary, the 2-second sustain + 3-second debounce, the consent gate, and the transparency rule (Lori truthfully answers "are you using my camera?") are the operational implementation of consent-first affective computing. The technique is established; the Lorevox embodiment is reserved.

### Entries

*(none yet — to be added. Targets: MediaPipe Face Mesh literature; affective computing consent frameworks; on-device emotion classification; FACS-derived geometry features; transparency rules in affective UI.)*

---

## Topic E — Multi-pass interview models, life-stage scaffolding, narrative arc

This is the family of work around **structured interview design over time** — three-pass models, era-based questions, life-stage scaffolds. Informs the multi-pass interview model (Pass 1 / Pass 2A / Pass 2B), Timeline Spine, and Chronology Accordion.

### Entries

*(none yet — to be added. Targets: oral history methodology literature; structured-interview design in qualitative research; life-stage developmental frameworks; phase-aware questioning.)*

---

## How to add a new entry

When a new paper or source is identified:

1. Read it. Note the core argument in 1-2 sentences.
2. Identify the topic section it belongs in (or create a new topic section if none fits).
3. Add an entry at the top of that section's *Entries* block with:
   - **Source** — citation, DOI/URL, year
   - **Local copy** (if any, in `docs/research/papers/`)
   - **Core argument** — what the paper claims
   - **Why it matters to Lorevox** — explicit connection to a current or planned WO
   - **Wired at** — file paths or WO names where the idea lands or will land
   - **Boundary** — when relevant, a note about what is borrowed (method) vs reserved (implementation in this codebase)
4. If a new topic section is needed, mirror the format of Topic A above (header paragraph + *Why this matters to Lorevox* + *Entries* subsection).
5. Update CLAUDE.md changelog entry briefly noting the addition.

---

## On the boundary between method and implementation

Several reserved-rights items in `LICENSE` correspond to productized versions of established methods:

| Reserved expression in this codebase | Underlying method (not reserved) |
|---|---|
| SPANTAG (Pass 1 / Pass 2 / down-projection shim) | Span labeling / span-based extraction with custom delimiters |
| NESTED-BINDING (role-bearing element model, 16-type vocabulary, overtext shape) | Nested annotation (Levels I/II/III) per Nested Text Labelling paper |
| Four-layer family-truth pipeline (shadow / proposal / review / promoted) | Human-in-the-loop annotation with candidate-vs-truth separation |
| Cognitive Support Model (silence ladder, no-correction posture, invitational re-entry) | OT life-review practice; dementia-safe interviewing |
| MediaPipe → affect → runtime71 pipeline | On-device affective computing with consent-first transmission |
| Multi-pass interview model + Timeline Spine | Oral-history / life-review interview design |

This is the right legal posture: anyone is free to build a different AI memoir tool using span labeling, nested annotation, candidate-vs-truth pipelines, dementia-safe pacing, or multi-pass interviewing. No one is free to copy *this* codebase's expression of those methods — the source code, prompt text, schemas, UI language, character design, terminology, and workflows.

Per the License: *"Anyone is free to build a different AI memoir tool. No one is free to copy this one's code, prompts, persona, schemas, or expressed implementation."*

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created. First topic section (Span labeling / span-based extraction) populated with the Nested Text Labelling paper and a generic span-labeling-broadly note. SPANTAG framed explicitly as the Lorevox productized version of an established method. Topic sections B/C/D/E created as empty containers for future references. Added "On the boundary between method and implementation" section mapping reserved expression to underlying method for each major architectural piece. |
