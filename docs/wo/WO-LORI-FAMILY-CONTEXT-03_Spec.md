# WO-LORI-FAMILY-CONTEXT-03 — family knowledge Lori can actually use

**Status: PLANNED. NOTHING IMPLEMENTED.** Filed 2026-09-14.

Governed by [`WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00`](WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00_Spec.md),
which owns the invariants and requirements. **This document owns only scope and evidence.**

**Blocked behind the portability lane, WO-01 and WO-02.**

---

## Mission alignment

*"Operator seeds known structure; Lori reflects what is there."* If the operator has
recorded who the narrator's people are, Lori must not interrogate the narrator for facts
the system already holds — and must not be handed a five-hundred-person genealogy in
every prompt either. This work order makes canonical family knowledge reach Lori in the
right amount at the right moment.

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity; introduce `must_not_write` violations or
system-tone outputs; regress the locked extractor baseline; expand operator surfaces into
narrator UI; add detectors that duplicate existing signals; **reserve a permanently fixed
token allowance** (R-10 — the existing prompt-budget system governs); or build a
Lori-specific copy of family truth.

## Tier 3 — narrator-facing

**Lori impact.** Response length, questions per turn (**≤ 1**), tone, pacing and the
narrator/operator role boundary are all in scope for review. Family context changes what
Lori knows, not how much she says; a turn that grows because more relatives were injected
is a regression, not a feature.

**Narrator dignity check.** Walk the locked design principles at acceptance. The two that
bind hardest here: *no system-tone outputs* — a relationship Lori knows is spoken like a
person, never surfaced as provenance or a field name; and *operator seeds known structure*
— if the operator seeded it, Lori knows it and does not ask for it as intake. This WO must
not become a "next relative to ask about" loop, which is the interrogation pattern
`WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01` retired.

## In scope

**Tier 1 — core.** Narrator, spouse/partner, parents, children, and the active family
subject.

**Tier 2 — neighbourhood**, when relevant and budget permits. Siblings, grandparents,
grandchildren, the immediate connections of the active subject.

**Tier 3 — extended**, only when relevant. Great-grandparents, aunts and uncles, cousins,
derived graph paths.

**Mention-aware expansion — the dynamic rule.** Clara is a great-grandmother and normally
absent from context. The narrator says *"Grandma Clara taught me to sew."* Lorevox resolves
Clara against canonical family entities, promotes her and the relevant relationship path
into family context, and Lori responds with the relationship grounded — **without asking
who Clara is when the system already knows.**

**Ambiguity is visible.** If several people could be "Uncle John", Lorevox either resolves
from strong conversational context or **asks for clarification**. It never silently picks.

**Privacy.** Only the *conversational* visibility class reaches Lori (INV-13).
Operator-private material never does.

## Out of scope

Kinship derivation beyond what context needs (WO-04) · GEDCOM · publishing · charts · any
change to the prompt-budget mechanism itself.

## Required tests

| | Case | Passes when |
|---|---|---|
| **CXT-T01** | immediate family | Lori receives useful immediate family context |
| **CXT-T02** | an irrelevant great-grandparent exists | **not included** |
| **CXT-T03** | the narrator mentions Clara | Clara becomes active context |
| **CXT-T04** | two family members named John | **no silent selection** — resolved or clarified |
| **CXT-T05** | an operator-private note exists | **absent** from Lori context |
| **CXT-T06** | constrained prompt budget | deterministic degradation; essential narrator context survives |

**Evidence standard, and it is the whole point of this WO.** *"A graph row exists"* is not
proof that *"Lori knows it."* Acceptance inspects **what actually entered the context** —
the composed prompt or the response trace — not what a projection function returned. This
is master §5 layer 5, and DRIFT-12.

## Acceptance gate

Lori demonstrably receives and **uses** relevant canonical relationship context, distant
relatives stay out until they matter, ambiguity is surfaced rather than guessed, and
private material never appears. Evidence packet per the master's §6.
