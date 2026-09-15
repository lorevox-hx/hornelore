# WO-FAMILY-PUBLISHING-06 — one source, regenerated everywhere

**Status: PLANNED. NOTHING IMPLEMENTED.** Filed 2026-09-14.

Governed by [`WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00`](WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00_Spec.md),
which owns the invariants and requirements. **This document owns only scope and evidence.**

**Blocked behind the portability lane and behind WO-01 through WO-05.** DRIFT-06: no
advanced publishing before the canonical Family Tree and Lori context work.

---

## Mission alignment

This is where the family knowledge becomes something the family can hold — a profile, a
register, a chart, an appendix bound into the memoir. It is also the last place a
duplicate authority could creep in, because an appendix that gets hand-edited immediately
becomes a second version of the truth. Everything here is a **projection**: correct the
canonical record once and the next output carries the correction.

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity; introduce `must_not_write` violations or
system-tone outputs; regress the locked extractor baseline; expand operator surfaces into
narrator UI; add detectors that duplicate existing signals; **create an independent
canonical copy of family data for publishing**; or let a renderer become authority
(INV-14).

## Tier 3 — narrator-facing output

**Narrator dignity check** at acceptance. Published material is read by the family and
often by the narrator. *No system-tone outputs*: `(not on record yet)` and
`Based on: interview projection` never reach the page; an absent fact is absent, not
annotated. Disputed claims are presented as the family's differing accounts, not as a
data-quality defect. Source attribution belongs in the sources appendix, not mid-sentence.

## In scope

**Narrator profile** — a readable human profile from approved canonical information:
full and preferred name, birth and death, parents, grandparents, siblings,
spouse/partners, children, places lived, education, occupation and career, military,
cultural and faith background, traditions, interests, selected life events.

**Family register** — a readable listing of approved family members and selected facts.

**Family charts** — evaluate the existing Lorevox renderer, pure SVG, and Topola or an
equivalent genealogy-specific renderer, for pedigree, descendant and hourglass charts.
Topola would be a **JavaScript/vendor/npm** decision rather than pip, and it answers the
dependency gate like any other. Whatever is chosen **consumes canonical data and never
becomes authority.**

**Memoir family appendix**, optional, generated:

    Appendix A — About the Narrator
    Appendix B — Family Tree
    Appendix C — Family Register
    Appendix D — Life Profile / Timeline
    Appendix E — Sources / Oral-History Attribution

**Person–story hooks.** Lay the stable references so a family member can eventually show
their interview passages, photographs, timeline events, audio and memoir chapters
(R-15). The full UI need not arrive here; the identity model must support it.

**Visibility.** Only the *publishable* class appears by default; operator-private material
requires explicit approval (INV-13).

## Out of scope

New canonical storage of any kind · editing family data from the publishing surface ·
automated selection of which disputed claim is true (DRIFT-09).

## Required tests

- **the one-source test, and it is the acceptance criterion in miniature:** correct a
  canonical value once, regenerate, and the new value appears in the profile, the
  register, the chart and the appendix **with no secondary editing anywhere**;
- a disputed fact renders as competing claims, not as a silently chosen winner;
- operator-private material is absent from every generated artefact by default;
- an approved private item appears only after explicit approval;
- a renderer failure degrades the output without corrupting canonical data;
- person–story references resolve, and an unresolved reference fails acceptance;
- generated artefacts survive export → restore: the same correction regenerates
  identically on another accepted installation (R-23, R-24).

## Acceptance gate

**A canonical correction regenerates correctly everywhere without separately editing the
appendix.** Evidence packet per the master's §6.
