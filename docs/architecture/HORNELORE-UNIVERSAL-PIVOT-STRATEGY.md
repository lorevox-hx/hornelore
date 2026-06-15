# HORNELORE-UNIVERSAL-PIVOT-STRATEGY

**Status:** ACTIVE — architectural decision record
**Date:** 2026-05-24
**Decision owner:** Chris Horne
**Supersedes:** Implicit locked-narrator framing in README and prior WO lineage
**Type:** Architectural Decision Record (ADR) — not a Work Order

---

## TL;DR

Hornelore is Lorevox. The two names refer to the same codebase under different
labels for different audiences. The Horne family is tenant zero — the first
real user, whose sessions hardened the system — not a special case in the
architecture.

When the product is ready to serve other families, the rename happens. No
fork. No migration. No upstream/downstream relationship between Hornelore
and Lorevox repositories.

All subsequent architecture, WOs, and acceptance gates are written against
the universal assumption: Lori must work for narrators she has never met,
operated by people who do not know the narrator personally, using only the
context the system can collect during sessions and from documents the
operator uploads.

The locked-narrator principle is reclassified: it was a temporary operating
constraint during the Horne family's exclusive use of the system, not an
architectural commitment.

---

## The principle

The bio's purpose is to support the memoir, not to be the memoir.

A birth date without context matters less than a moment of context
without a birth date.

Optimize for high-context completeness, not absolute completeness.

If anchored asking ever produces more data and less story, the
architecture has failed.

This principle governs every decision about when Lori may interrupt
the narrator for the operator's purposes. It applies to Tier 3
anchored asking specifically and to any future mechanism that uses
Lori's mouth on behalf of the operator. When in doubt, the chapter
wins and the bio gap remains a gap.

---

## Context

### How we got here

Hornelore was created as a hardened production fork of Lorevox locked to
the Horne family — three real narrators (Chris, Kent, Janice) and two
trainer narrators (Shatner, Dolly). The locked-narrator principle was
load-bearing for several reasons:

- Safety classification could lean on prior knowledge of Kent and Janice
- Bio Builder could pre-load substantial known biographical material
- Operator (Chris) knew every narrator personally and could correctly
  pick session style, interpret ambiguous turns, and override the system
  with confidence
- Trust model assumed a closed universe; "NEVER auto-promote to truth"
  was safer when every truth was about three known people
- Trainer narrators (Shatner, Dolly) calibrated to two specific voice
  patterns chosen for fidelity testing

The locked-narrator framing produced real benefits. It let the system
harden quickly against high-quality ground truth. It kept the operator
loop tight enough to catch failures fast. It made parent-session
readiness gates concrete rather than abstract.

### Why the framing now changes

Two converging pressures forced the decision:

1. The interview process redesign document
   (WO-INTERVIEW-PROCESS-REDESIGN-01) is universal in scope by
   construction. The turn classifier, mode state machine, story momentum
   detection, narrator rhythm adaptation, population diversity harness,
   and twelve narrator archetypes cannot be implemented coherently if the
   target population is three known people. The redesign assumes
   narrator variability the locked-fork did not.

2. The product vision — preserving the meaning, texture, chronology, and
   emotional truth of *a life*, not specifically three lives — was
   never narrowed to the Horne family in principle. The locked fork was
   the *how*, not the *what*. With the safety and interview
   architecture nearing readiness, continuing to treat the Horne family
   as a special case introduces an artificial migration step later that
   serves no one.

The cleanest answer is that there is no fork. Hornelore is the codebase.
Lorevox is the brand for when the codebase is ready for other families.
Today is the day the codebase stops pretending those are different things.

---

## Decision

### Primary decision

**Hornelore and Lorevox are the same project under two names.**

- Single repository: `lorevox-hx/hornelore` continues as the active
  development repo. The Lorevox repo (if it exists separately) is
  archived or made a stable release pointer. No code lives in two
  places.
- Single architecture: all new work assumes universal narrator scope.
  Code paths that currently assume Horne-specific knowledge are
  reclassified as "tenant-zero defaults" — they still run, but they
  are not load-bearing for system correctness.
- Single principle set: the locked product rules are audited against
  universal applicability (see Audit Findings below). Rules that are
  universal stay; rules that were Horne-specific operational
  constraints are either generalized or removed.
- The "Hornelore" name and brand persist through the entire build-out
  of universal capability. The rename to "Lorevox" is a marketing and
  packaging event that happens when the product is ready for second-
  family pilot. It is not a code event.

### Sequencing decision

**Route A: ship dignity-and-safety work for tenant zero first; build
universal capability on top of stable foundations.**

The trio (past-tense + softened-mode + Phase 9 disclosure) and Phase 1
of the redesign (reflection-first + thread banking + question hierarchy)
are narrator-agnostic. They transfer to every future tenant without
rework. They close Gate 6 RED for Kent and Janice, whose production
sessions are happening now. They are prerequisites to the oral-history
default flip working well.

Phase 2+ of the redesign (turn classifier, orchestrator, story momentum,
rhythm adaptation, quality harness, population diversity testing) is the
architectural commitment that prepares the system for non-Horne
narrators. It happens after the dignity-and-safety foundations are
stable.

### Deployment model decision

**Single-tenant today; multi-tenant-capable architecture going forward;
SaaS deployment deferred.**

- Today: one deployment, one tenant (Horne family), one operator
  (Chris). No tenant isolation work, no auth surface, no billing.
- Architectural standard going forward: new code does not encode
  single-tenancy assumptions. Database schemas accept a `tenant_id`
  column even when there is currently one value. Configuration is
  per-tenant-loadable even when there is currently one tenant.
  Operator surfaces are per-tenant-scoped even when there is currently
  one operator. This is *capability*, not *deployment* — the system
  can become multi-tenant without rewrite, but does not yet run that
  way.
- SaaS deployment, multi-operator support, family-facing surfaces,
  billing, and compliance work (GDPR, CCPA, age-related considerations
  for elder-care contexts) are explicitly deferred. They are
  pre-rebrand work, but not now-work.

### Trainer narrator decision

**Shatner and Dolly remain as voice-pattern reference narrators.
Population diversity testing uses a separate synthetic archetype set.**

Shatner and Dolly were chosen for fidelity calibration to two specific
voice patterns — not as representatives of the broader narrator
population. They continue to serve that fidelity role. The twelve
archetypes from the interview redesign document
(talkative, quiet, trauma, nonlinear, resistant, humor, immigrant,
factual/engineer, emotionally expressive, memory-gap, grief, sensory
storyteller) become a *separate* synthetic narrator set used for the
population diversity harness. The two sets are not collapsed.

---

## Consequences

### What changes today

Nothing in production. This is a framing decision, not a code change.
The Horne family continues to use the system exactly as before. The
trio and Phase 1 are written and shipped against the universal frame.

### What changes in WO authorship going forward

Every new WO is written under the assumption that the narrator could be
anyone. Specific Horne-family examples (Kent's Fort Ord chapter, Janice's
[chapters], Chris's [chapters]) appear as evidence and motivation, but
the architecture is not tuned to them. Acceptance gates that rely on
"Kent would never say this" sanity checks are reformulated against
generalizable signals.

WO templates gain an explicit "narrator generality" section: every WO
declares whether its scope is universal (default), tenant-specific
(rare, requires justification), or Horne-tenant-zero historical context
(documentation only).

### What changes in the trio (already drafted)

Nothing structural. The trio was already written narrator-agnostic —
past-tense acknowledgment, softened-mode persistence, and consent
disclosure work for any narrator. The strategy doc validates that
framing retrospectively. The trio ships as drafted.

One small revision worth noting: the Phase 9 disclosure update
(WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01) currently references
"the Horne family" implicitly through the Phase 9 lineage. When that
WO is built, the consent disclosure should be written for the Horne
family as written, but the operator runbook additions should be
written for any operator. The runbook is universal; the consent doc
is tenant-zero. This is the first instance of the new pattern.

### What changes for Phase 1 of the redesign

Phase 1 is now explicitly framed as universal. Reflection-first
hardening, story interruption rules, thread banking, and question
hierarchy work for any narrator. The implementation does not encode
Horne-specific knowledge or examples. Tests use synthetic narrator
turns alongside real Horne session evidence.

### What changes for Phase 2+ of the redesign

Phase 2+ is now the primary architectural workstream for the path to
rebrand. Turn classifier, interview orchestrator, story momentum
detection, narrator rhythm adaptation, interview quality harness,
and population diversity testing are all on-path for opening Lorevox
to other families. They are no longer optional architectural
improvements; they are prerequisites to the rebrand event.

### What changes for the Bio Builder problem

Significantly. The previous Bio Builder discussion assumed substantial
pre-load from family knowledge — Chris knows Kent's birthdate, military
record, employment history, etc., and types these in. For a universal
system, every bio starts empty. Chapter-driven extraction becomes the
primary mechanism, not the supplementary one. Document Archive
ingestion of unfamiliar family papers becomes a first-class surface.
The four-tier division (chapter-driven / anchored asking / operator
direct-entry / document-derived) still holds, but the weight shifts
toward tiers 1 and 4. This will be the subject of its own WO; the
strategy doc only flags the change of emphasis.

### What changes for operator UX

Eventually significantly; not now. Today the operator is Chris, who
knows the narrators personally. The operator surfaces assume that
knowledge. Before second-family pilot, the operator UX needs:

- First-session diagnostic to inform session-style selection (today
  Chris picks based on knowing the narrator)
- Operator briefing surface to capture what the operator does know
  about the narrator before the first session
- Post-session review surfaces that work without prior narrator
  familiarity (today Chris can spot a wrong extraction in milliseconds)
- Operator training material for the family-as-operator vs.
  professional-operator distinction

These are flagged as Universal Audit items below. Not now-work.

### What does NOT change

- The locked product rule "NEVER auto-promote to truth from media
  archive" — universal. Stays.
- The locked product rule "Lori does not pretend not to hear" —
  universal. Stays.
- The acute safety path — universal. Stays.
- The communication control wrapper (atomicity, word caps,
  reflection validation) — universal. Stays.
- Trainer narrators Shatner and Dolly as fidelity references — stays.
- The parent-session readiness framework, with the understanding that
  "parent-session" generalizes to "any narrator's session" rather than
  specifically Kent and Janice's.

---

## Universal Audit Findings

A first-pass audit of existing principles, rules, and assumptions
against the universal framing. Items marked **U** are universal as
written. Items marked **T0** are Horne-tenant-zero assumptions that
need either generalization or explicit reclassification before rebrand.
Items marked **R** require revisiting in their own WO before rebrand.

| Item | Class | Notes |
|---|---|---|
| "NEVER auto-promote to truth from media archive" | **U** | Reason shifts from Horne-family safety to universal trust model. No change. |
| "Lori does not pretend not to hear" | **U** | Universal dignity principle. No change. |
| Acute safety path (988, operator notification) | **U** | Universal. No change. |
| Past-tense acknowledgment (sibling WO) | **U** | Universal. Drafted narrator-agnostic. |
| Softened-mode persistence (sibling WO) | **U** | Universal. Drafted narrator-agnostic. |
| Communication control (atomicity, word caps, reflection) | **U** | Universal. No change. |
| Five session styles (warm_storytelling, questionnaire_first, companion, memory_exercise — plus oral_history to be added) | **T0** | The live runtime table currently has four styles: clear_direct, warm_storytelling, questionnaire_first, companion. oral_history is NOT yet a defined style; it must be introduced as part of `WO-LORI-ORAL-HISTORY-DEFAULT-01`. memory_exercise is referenced but missing from the parameter table (resolved by `MEMORY-EXERCISE-DECISION.md`). |
| Oral-history as default session style | **U** | Universal. Worth ensuring the default works for narrators who *don't* want oral history (resistant, quiet, factual archetypes). |
| Locked narrator universe (Chris, Kent, Janice + trainers) | **T0** | Reclassified as tenant-zero configuration, not architectural commitment. |
| Bio Builder pre-load from family knowledge | **T0** | Universal Bio Builder must work from empty state. See Bio Builder lane. |
| Operator knows narrator personally | **T0** | Universal operator may not. Operator briefing surface needed before rebrand. |
| Operator picks session style based on personal knowledge | **T0** | First-session diagnostic needed before rebrand. |
| Trainer narrators are Shatner and Dolly only | **T0** | Expanded synthetic archetype set needed for population diversity harness. |
| Document Archive primarily supplements known facts | **T0** | Universal Document Archive is primary fact source. |
| Phase 9 consent disclosure references Horne family context | **T0** | Family-facing language remains tenant-zero; operator runbook generalized. |
| Parent-session readiness gates defined against Kent/Janice sessions | **T0** | Framework generalizes; gate definitions need restatement against universal narrators before rebrand. |
| Operator real-time visibility into all sessions | **R** | Works for one operator; multi-operator visibility model needs design. |
| "Operator briefs family outside the system" | **R** | Assumes operator and family are different people; in family-as-operator deployments they're the same. Needs disambiguation. |
| Trust model for narrator-stated facts vs document-stated facts | **R** | Universal version needs explicit conflict resolution policy (whose memory wins when documents disagree). |
| Per-narrator template defaults (rhythm, style, gate values) | **R** | Currently implicit in operator's head; needs first-class data model before rebrand. |
| Auth, tenant isolation, billing, compliance surfaces | **R** | Entirely absent today; all needed before SaaS deployment. Pre-rebrand if SaaS is rebrand model; deferrable if self-hosted is rebrand model. |
| Spanish-fragment detection (ML-LORI lane) | **U** | Universal narrator population has language variability. Existing lane stays. |
| Cognitive accessibility scaffolding (WO-10C) | **U** | Universal narrator population includes cognitively variable narrators. Existing work stays. |
| Tier 3 anchored asking authorization to interrupt narrator for operator purposes | **R** | The only piece of Bio Builder that uses Lori's mouth for operator goals. Carries the architecture's highest regression risk (drift back to questionnaire). Pre-rebrand decision required: keep with creep defenses (`WO-LORI-BIO-BUILDER-UNIVERSAL-01` Anchored Asking Creep Defense section) or delete entirely (slower bio fill, but creep becomes architecturally impossible). The defended position is workable; the undefended middle is not. |
| memory_exercise as deprecated vs implemented | **RESOLVED 2026-05-24** | Initial direction (deprecate) reversed by `MEMORY-EXERCISE-DECISION.md`. Style is preserved and gets proper implementation via `WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01`. First **RESOLVED** entry in the audit table — pattern established: resolved items remain visible so decision history is traceable, rather than vanishing. |

### Items needing decisions before rebrand (not now-work)

Each of these is a real architectural choice that the universal pivot
puts on the table but does not resolve. Listed here so they don't go
invisible.

1. **Deployment model.** SaaS (multi-tenant hosted by you), self-hosted
   single-tenant (each family runs their own), or hosted multi-instance
   (you operate separate instances per family on shared infrastructure).
   Determines whether auth/billing/compliance work is needed.

2. **Operator model.** Is the operator always a family member, always a
   professional (oral historian, memoir writer, eldercare worker), or
   either? Affects operator UX, training material, liability model.

3. **Family-facing surfaces.** Today there is no family-facing surface
   beyond the operator briefing the family in person. Universal
   deployment may need a family-readable transcript view, a memoir
   preview, or a way for adult children to consent on behalf of a
   parent narrator (and the ethics of that).

4. **Narrator-as-tenant vs. family-as-tenant.** Is the "tenant" the
   individual narrator (one bio, one consent, one set of sessions) or
   the family (multiple narrators, shared archive, cross-narrator
   references)? Hornelore-tenant-zero is the family model. Universal
   may need both.

5. **Data portability and exit.** What happens to a tenant's data if
   they stop using the system? Memoir export format, bio export
   format, transcript export format, deletion guarantees.

6. **The "memoir" deliverable.** Today implicit in Chris's head. For
   universal deployment, the path from sessions → bio → memoir
   manuscript needs to be a first-class product surface, or the
   product needs to be honest that it produces source material and the
   family hires a writer.

7. **Tier 3 anchored asking — keep or delete.** Tier 3 is the only
   mechanism by which Lori asks bio questions for the operator's
   purposes. The creep risk is real and the defenses in
   `WO-LORI-BIO-BUILDER-UNIVERSAL-01` address it operationally but
   not philosophically. Before rebrand, write the explicit defense
   ("Tier 3 exists because chapter-anchored asking is qualitatively
   different from questionnaire asking, and the difference is worth
   the regression risk; here is what makes it worth it; here are the
   conditions under which we would delete it"), or delete Tier 3
   and rely on chapter extraction + documents + operator entry. The
   undefended middle is what allows the architecture to drift back
   to questionnaire behavior under operational pressure.

These are the conversation topics for the post-Phase-2 strategic review.

---

## What this document is and is not

**This document IS:**
- The architectural decision record that all subsequent WOs reference
- The audit trail for which assumptions were Horne-specific vs universal
- The strategic anchor for the path from Hornelore-as-locked-fork to
  Lorevox-as-rebrand
- A living document, updated when Horne-specific assumptions surface
  during build (Audit Findings section gets new rows)

**This document IS NOT:**
- A Work Order (no acceptance gates, no test coverage, no files-changed)
- A product spec (no feature definitions, no UX, no API contracts)
- A roadmap (no dates, no resource estimates, no commitments)
- A marketing document (the rebrand is mentioned but not described)
- A consent or legal document (separate work, separate authorship)

---

## Maintenance

This document is updated whenever:

- A new Horne-specific assumption surfaces during WO build (add to
  Universal Audit Findings)
- A Universal Audit item is resolved (move from R to U with reference
  to the resolving WO)
- A pre-rebrand decision item is decided (move from "Items needing
  decisions" to the appropriate section)
- The deployment model decision changes (revise Decisions section)

The document is read by every WO author before starting a new WO, to
ensure the WO's narrator-generality section is correctly classified.

---

## Related artifacts

- `WO-INTERVIEW-PROCESS-REDESIGN-01` — universal redesign vision; this
  strategy doc is the anchor that lets the redesign land coherently
- `WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01` — universal as drafted
- `WO-LORI-SOFTENED-MODE-PERSISTENCE-01` — universal as drafted
- `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01` — tenant-zero consent doc;
  universal operator runbook additions
- `WO-LORI-STORY-FIRST-PHASE-1-01` (next to draft) — universal as
  intended; first WO authored under the new framing from inception
- README — to be updated to reflect the Hornelore-is-Lorevox framing
  at the top, removing locked-narrator language as a structural claim
  (becoming tenant-zero context instead)

---

## Closing note

The locked-narrator principle did good work. It kept the operator
loop tight, the safety architecture honest, and the parent-session
readiness framework concrete during the period when the system was
not yet trustworthy enough to extend beyond people whose voices we
knew well.

It is being retired now because the system has earned the right to
extend, and because continuing to encode the constraint in
architecture creates a migration debt that would have to be paid
later with worse information than we have today.

Hornelore was always going to become Lorevox. Today is the day we
stop pretending it wouldn't.
