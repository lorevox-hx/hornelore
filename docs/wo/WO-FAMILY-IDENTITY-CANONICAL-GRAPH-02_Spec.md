# WO-FAMILY-IDENTITY-CANONICAL-GRAPH-02 — permanent identity, one canonical editor

**Status: PLANNED. NOTHING IMPLEMENTED.** Filed 2026-09-14.

Governed by [`WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00`](WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00_Spec.md),
which owns the invariants and requirements. **This document owns only scope and evidence.**

**Blocked behind the portability lane and behind WO-01.**

---

## Mission alignment

A person's name is not who they are. Until family identity is a permanent opaque UUID and
the Family Tree writes to the canonical graph, a correction to someone's name can silently
sever them from their own photographs, facts and stories — the system editing the
narrator's account of their family on their behalf. This work order makes identity
survive correction and makes the editing surface canonical.

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity; introduce `must_not_write` violations or
system-tone outputs; regress the locked extractor baseline; expand operator surfaces into
narrator UI; add detectors that duplicate existing signals; **flatten the relationship
vocabulary** (R-26 — `ex-wife`, `late wife`, `partner`, `half-brother`, `stepmother` and
chosen family keep their distinctions and provenance); or ship a narrator-owned schema
change without the full §2b portability gate.

## In scope — three parts, one migration, one acceptance surface

They are one work order because they share a migration and cannot be accepted
independently: identity without the editor is unreachable, and the editor without
provenance is a lossy write.

### C.1 — UUID identity refactor

Permanent `graph_person_id`; no name-derived identity; legacy graph identities migrated
with zero loss; relationships, narrator ownership and package/merge semantics preserved.

### C.2 — the unified canonical editor

Add Person → canonical person. Edit → canonical update. Connect → canonical relationship.
Delete relationship → backend. Reload → backend authority. `localStorage` remains
transient assistance for unfinished edits, undo and form state, and **never** the final
authority (INV-07). A backend failure cannot report success (INV-08).

### C.3 — relationship semantics and provenance

Direct relationship types — biological, adoptive, step, foster, guardian, spouse, partner,
former relationship, deceased-spouse state, chosen family — with the source recorded:
operator input, narrator statement, questionnaire, Family Truth, document, GEDCOM import,
other import. **Editing a relationship must not lose its provenance history.**

## Out of scope

Lori context · kinship derivation · GEDCOM · publishing · charts. Convenience fields shown
in the tree form (birth year, birthplace, death year, occupation) are **routed** to the
canonical fact systems per R-04; this WO does not build a second fact store.

## Required tests

**Identity**

- rename a person → **UUID unchanged**, every reference still resolves;
- two relatives with identical names → distinct UUIDs, independently representable;
- maiden / preferred-name change → identity preserved;
- a same-name parent and child are both representable;
- legacy migration loses **zero** graph persons and **zero** relationships;
- the migration is safely re-runnable;
- narrator erasure remains complete afterwards.

**Editor**

- add → save → reload from the backend;
- edit → save → reload;
- add and remove a relationship;
- **clear browser `localStorage` after save → the canonical person remains**;
- a backend failure cannot claim success.

**Provenance**

- an operator-entered and a narrator-derived relationship carry different, persisted
  provenance;
- editing a relationship preserves provenance history.

**Portability — the §2b gate, answered before acceptance**

- ownership inventory, export, restore, erasure, Merge/Remap and semantic-reference
  validation all declared and tested for every changed lane;
- **export → restore → UUID unchanged**;
- **cross-origin and sequential merge**: `graph_persons.id` is already known to collide
  across installations because the product mints it deterministically from narrator +
  name, and `graph_relationships.from_person_id` / `.to_person_id` are real SQL foreign
  keys into it. A UUID refactor changes that surface and must re-answer it.

## Acceptance gate

An operator can maintain the narrator's canonical family identity and direct relationships
**entirely through Lorevox**, a correction never changes a UUID, and nothing depends on
browser state. Evidence packet per the master's §6.
