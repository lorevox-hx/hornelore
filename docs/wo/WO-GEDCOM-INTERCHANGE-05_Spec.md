# WO-GEDCOM-INTERCHANGE-05 — exchange family data without surrendering identity

**Status: PLANNED. NOTHING IMPLEMENTED.** Filed 2026-09-14.

Governed by [`WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00`](WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00_Spec.md),
which owns the invariants and requirements. **This document owns only scope and evidence.**

**Blocked behind the portability lane and behind WO-01 through WO-04.** DRIFT-06 is
explicit: no GEDCOM before the canonical Family Tree works.

---

## Mission alignment

A family's history should not be trapped in Lorevox, and Lorevox should be able to accept
what a family already gathered elsewhere. But an imported file is a stranger's claim about
the narrator's relatives — useful evidence, never authority. This work order lets data
cross the boundary in both directions while the operator, not a matching heuristic,
decides who is who.

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity; introduce `must_not_write` violations or
system-tone outputs; regress the locked extractor baseline; expand operator surfaces into
narrator UI; add detectors that duplicate existing signals; **let an import write into
canonical family identity before operator approval** (INV-10, R-16); or let an external
id become Lorevox identity (INV-12).

## In scope

**Target formats.** GEDCOM 5.5.1 and GEDCOM 7.x, against the accepted specification at
implementation time, proven with **real fixture files** rather than hand-written snippets.

**Import sequence.** Select `.ged` → hash and source-identify the file → parse into
**isolated staging** → extract supported people, families, events, places, sources →
compare against canonical Lorevox family → **rank** possible matches → operator reviews
every identity decision → canonical write happens **only** after approval.

**Reconciliation.** Each imported person is *likely existing* / *possible duplicate* /
*new* / *unresolved-disputed*, and the operator chooses **confirm same person**, **create
distinct person**, or **leave unresolved**. There is no automatic merge, and similarity of
name, date, place or relatives is never sufficient (INV-10, DRIFT-09).

**Conflicts are kept, not resolved.** Lorevox holds `Birth: 1931-04-04` (operator/narrator)
beside `Birth: 1931-04-06` (imported) with both provenances until a human decides. No
silent replacement — this is INV-05 in its sharpest form.

**Provenance retained**: source system, source filename and hash, GEDCOM version, source
XREF, import batch, the imported values themselves, and the reconciliation decision.

**Export.** Standards-compliant GEDCOM from canonical approved data, with **private and
operator-only content excluded by default** (INV-13).

## The dependency decision

A GEDCOM parser may require a third-party dependency. **None is approved.** Before
adoption, record in this work order: GEDCOM 5.5.1 support · GEDCOM 7 support · active
maintenance · parser correctness · malformed-file handling · licensing · dependency
footprint · test corpus · security implications — plus the master's ten-item gate
(offline behaviour, privacy impact, pinned version, failure mode, removal path). Writing a
bounded parser for the subset Lorevox actually needs is a legitimate answer.

## Out of scope

Publishing and charts · automated historical-record matching · DNA · any public research
service (master §10 non-goals).

## Required tests

- a **GEDCOM 5.5.1** fixture and a **GEDCOM 7** fixture, both real files;
- identical-name distinct people stay distinct;
- a likely match **requires human approval** before any canonical write;
- an intentional false match can be **rejected**;
- competing dates are **both retained** with their provenance;
- XREF and import-batch provenance retained;
- malformed GEDCOM **refuses** rather than partially importing;
- **staging creates zero canonical mutation before approval** — measured against the
  canonical tables, which is the assertion this whole work order turns on;
- export → re-import into a disposable environment → topology and supported facts survive,
  compared semantically;
- private and operator-only material is absent from the export by default;
- the §2b portability gate answered for every new staging and provenance lane.

## Acceptance gate

Genealogy import and export **do not compromise identity or provenance**: nothing merges
without a human, no conflict is silently resolved, no external id becomes identity, and
nothing private leaves by default. Evidence packet per the master's §6.
