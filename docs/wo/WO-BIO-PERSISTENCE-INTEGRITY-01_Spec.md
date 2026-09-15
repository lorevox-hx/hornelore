# WO-BIO-PERSISTENCE-INTEGRITY-01 — make bio entry safe enough to trust

**Status: PLANNED. NOTHING IMPLEMENTED.** Filed 2026-09-14.

Governed by [`WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00`](WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00_Spec.md),
which owns the invariants and requirements. **This document owns only scope and evidence**
and does not restate them.

**Blocked behind the portability lane.** Does not begin until Merge/Remap, family
consolidation, Phase 7 and Phase 8 are accepted. `HANDOFF.md` is the authority on what is
current.

---

## Mission alignment

Before an operator is asked to type a family history in by hand, the system has to be
worth typing into. Today reopening a narrator can add bio facts nobody entered, which
means the record of a person's life silently grows rows they never said — and the
narrator is the author of their own story. This work order makes bio entry idempotent and
its save acknowledgement truthful, so that nothing after it is built on sand.

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity; introduce `must_not_write` violations or
system-tone outputs; regress the locked extractor baseline (it touches no extractor,
prompt or model); expand operator surfaces into narrator UI; add detectors that duplicate
existing signals; or create a second authority for any lane the master's §2a assigns
elsewhere.

## In scope

- the bio-fact / questionnaire duplication on reopen — **BACKLOG §5 already records the
  cause**: opening a narrator appends four `bio_facts` through `questionnaire_put`, and
  the two-origin comparison measured the result as duplicate logical keys within one
  origin (Christopher: 4 on the desktop side);
- unchanged save is idempotent — saving the same questionnaire or profile twice changes
  no canonical row count;
- **awaited** save: the operator write is not fire-and-forget;
- visible, truthful save state — `Saving…` / `Saved to Lorevox` / `Save failed` /
  `Retry required` (INV-08);
- narrator-switch safety while asynchronous loads are in flight;
- restart and reopen reproduce the canonical record exactly.

## Out of scope

Family-tree UUID migration · the canonical editor · GEDCOM · the kinship resolver · Lori
family context · any new visualisation · the memoir appendix · any broad graph refactor.
If one of these turns out to be required, it is a Type B or Type C change under the
master's §6 — backlog or amend, never a quiet enlargement of this WO.

## Required tests

| | Case | Passes when |
|---|---|---|
| **B-T01** | open bio repeatedly, no edits | **no additional bio facts** — count measured in the real schema, not in a mock |
| **B-T02** | save the same values several times | canonical row count is stable |
| **B-T03** | change one value | the correct canonical update or supersession, no uncontrolled duplication |
| **B-T04** | narrator switch A → B → A while async data loads | **zero cross-narrator persistence** |
| **B-T05** | forced backend failure | the UI **never** displays *Saved* |
| **B-T06** | save → shut down → restart → reopen | canonical values return unchanged |
| **B-T07** | export → restore into a clean installation | the same bio information survives (INV-15) |

DOM assertions do not substitute for backend persistence (master §5, layer 4). Every count
above is read from the real SQLite schema through the real migrations.

## Acceptance gate

No known duplicate-on-open defect, and save behaviour is **truthful and idempotent** —
proven by B-T01 through B-T07 with an evidence packet per the master's §6.
