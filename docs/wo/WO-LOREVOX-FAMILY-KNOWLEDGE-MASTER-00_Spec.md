# WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00 — family knowledge, bio, genealogy and memoir

**Status: PLANNED. Architecture frozen; NOTHING IMPLEMENTED.** Filed 2026-09-14.

**This document does not open any work.** Implementation begins only after the current
portability lane — `WO-LOREVOX-PORTABLE-NARRATOR-01` and
`WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01` — is accepted and Phase 7 has produced the clean
Lorevox root. `HANDOFF.md` remains the authority on what is current; this file is
architecture, not state, and must never be read as a work queue.

**This is the AUTHORITY for the six child work orders** listed in §8. They implement this
architecture; they may not silently redefine it. If implementation requires violating an
invariant here: **stop, amend this document, review, then implement.**

**It absorbs and supersedes `SPEC-LOREVOX-FAMILY-BIO-CANONICAL-01`** (2026-09-14), a
parallel draft of the same architecture. Both were filed the same day and each declared
itself canonical, which is the two-lists-of-one-truth failure `CLAUDE.md` opens by naming.
Rather than keep both, the material unique to that draft was folded in here and it is not
filed separately: the **visibility classes** (§2, INV-13), the **canonical-data
responsibilities table** (§2a), **relationship-interpreter integration** (R-26), the
**eight-question portability gate** (§2b), the **evidence packet** (§6) and the **explicit
non-goals** (§10). Its finer work-order granularity was not adopted — identity, the editor
and relationship provenance stay one child (WO-02) with three internal parts, because they
share one migration and one acceptance surface.

**ONE JOB PER DOCUMENT.** The invariants and requirements live HERE and are *referenced*
by the children, never restated in them. Two copies of one rule is how they drift — the
failure this repository has already paid for more than once.

---

## Mission alignment

An operator must be able to enter, correct and maintain a narrator's family and
biographical knowledge **once**, have it saved canonically, and have that same knowledge
appear everywhere it belongs. That serves the Mission directly: the narrator is the author
of their own story, and a system that loses or silently rewrites who their people were is
editing that story on their behalf.

**Enter once → identify once → save canonically → use everywhere.**

    Operator Family Tree → canonical SQLite → Lori context → kinship queries
    → bio/profile → timeline/media → memoir/appendix → GEDCOM → narrator package

## Non-regression requirements

This work order and every child MUST NOT:

- reduce narrator dignity;
- introduce `must_not_write` violations or system-tone outputs;
- regress the current locked extractor baseline (none of this touches the extractor,
  a prompt, or the model — name the baseline and its scorer if that ever changes);
- expand operator surfaces into narrator UI;
- add detectors that duplicate existing signals;
- **create a second authority for anything Lorevox already owns** — fact review,
  provenance, timeline, prompt budgeting, memoir authority, conflict handling,
  portability or erasure;
- **ship a narrator-owned schema change without its full portability treatment**
  (INV-15, DRIFT-08).

---

## 1. What already exists

Lorevox already has most of the foundation: the Family Tree UI (add / edit / connect /
delete, card, graph and scaffold views, seeding from the canonical graph, profile,
questionnaire and candidates), `graph_persons`, `graph_relationships` and their backend
APIs, Bio Builder questionnaire and profile storage, bio facts, the Family Truth review
systems, timeline and events, media and photographs, transcript and narrator audio,
memoir and story systems, prompt budgeting, relationship interpretation, and narrator
export / restore / merge.

**The one architectural defect this work exists to close:** the Family Tree editing
surface can still be a browser `localStorage` draft while a separate backend graph is
canonical. That split must disappear. **We finish the existing Family Tree architecture;
we do not build a second tree system beside it.**

## 2. Frozen invariants

These govern every child work order. Changing one is a Type C change (§6) and requires
amending this document first.

| | Invariant |
|---|---|
| **INV-01** | **Names are never identity.** Every family member gets a permanent opaque UUID, `graph_person_id`. Name, normalised name, maiden name, nickname, spelling, date of birth, role, relationship and narrator-relative label **never** determine identity. Changing `Clara Horne` to `Clara Mae McRae Horne` leaves the same UUID and every relationship, fact, photograph, story and reference intact. |
| **INV-02** | **Narrator identity stays the existing Lorevox UUID.** Never replaced by `kent_horne`, a name, a slug, a filename or an external genealogy id. |
| **INV-03** | **One canonical relationship graph.** `graph_persons` + `graph_relationships` are the identity and topology layer. No second authoritative browser, JSON, GEDCOM-derived or visualisation tree. |
| **INV-04** | **`graph_persons` stays lean** — UUID, narrator ownership/scope, primary display name, optional rendering hints, minimal lifecycle flags. It does not become another facts, timeline, Family Truth or genealogy-event store. |
| **INV-05** | **Facts remain facts.** Birth, birthplace, death, occupation, education, military service, residence, marriage, immigration, religion/culture, traditions live in the appropriate canonical fact/event system and reference the person UUID. **Conflicting claims stay separate claims with provenance** — Lorevox never silently picks a winner. |
| **INV-06** | **Store direct relationships; derive extended kinship.** Store what was asserted (parent/child, spouse/partner, directly asserted siblings, adoptive, step, foster, guardian, chosen family). Derive grandparent, great-grandparent, aunt/uncle, niece/nephew, cousins and removals. **Do not fill the database with redundant transitive edges.** |
| **INV-07** | **The Family Tree UI edits canonical data.** Drafts are allowed for unfinished edits, undo and form state; accepted data is written to canonical backend storage. `localStorage` is never the final authority. |
| **INV-08** | **Save acknowledgement must be truthful.** Saves are awaited. `Saving…` / `Saved to Lorevox` / `Save failed` / `Retry required`. **Never show success before durable backend confirmation.** |
| **INV-09** | **Lori gets relevant family context, not the whole graph.** No 100- or 500-person genealogy in a prompt. Family knowledge is projected through the existing prompt-budget machinery. |
| **INV-10** | **No automatic identity merge.** An import may *rank* candidate matches. Only the operator may decide "these are the same person". |
| **INV-11** | **GEDCOM is interchange only** — outside format ↔ Lorevox. It is not the internal schema. |
| **INV-12** | **External ids never become Lorevox identity.** A GEDCOM `@I0042@`, a FamilySearch id, a Gramps handle, an import record id are provenance values only. |
| **INV-13** | **Privacy is explicit, and it is not one switch.** Information available to Lori is not automatically printable, and printable information is not automatically operator-private. The architecture must carry at least three visibility classes: **conversational** (may reach Lori), **publishable** (may appear in profile/memoir output) and **operator-private** (kept for research or administration, excluded from Lori, publishing and GEDCOM export unless explicitly approved). Private notes, unresolved research and restricted material never travel by default. |
| **INV-14** | **Rendering is read-only.** Topola, SVG, D3 or any future renderer consumes canonical data and never becomes authority. |
| **INV-15** | **Portability is part of completion.** A new narrator-owned table, column, reference, file or provenance record is **incomplete** until its behaviour is declared for ownership, export, restore, Merge/Remap, erasure and reference validation. |
| **INV-16** | **Reuse existing authorities.** Do not recreate fact review, provenance, timeline, prompt budgeting, memoir authority, conflict handling, portability or erasure inside the Family Tree. |

## 2a. Who owns what

No child work order may redefine these boundaries without amending this document. The
question DRIFT-03 asks of every proposed new table is answered against this table.

| System | Governing responsibility |
|---|---|
| `graph_persons` | permanent person identity and minimal display metadata |
| `graph_relationships` | direct family/social topology |
| `bio_facts` / Family Truth | biographical claims, reviewed truth, disputes and qualifications |
| timeline / events | when and where things occurred |
| media / documents | photographs, scans, documents, other evidence |
| transcript / story system | memories, interview passages, narrative evidence |
| memoir system | narrative and publishing projection |
| GEDCOM | external interchange only |
| Family Tree UI | operator editing and visualisation surface |
| Lori family context | prompt projection derived from canonical data |

## 2b. The portability gate

INV-15 in practice. Every new Family/Bio schema or file lane must have an **explicit
answer** to all eight before acceptance — no answer means the storage is not accepted:

1. Who owns it?
2. How is it exported?
3. How is it restored?
4. How is it erased?
5. How does Merge/Remap handle it?
6. **What ids can collide across installations?**
7. What references point into it?
8. How are those references validated?

Questions 6–8 are not theoretical: the Merge/Remap lane established that `turns.id` is
stored in seven places of which SQLite can see none, that three narrator-owned integer
surrogates exist, and that a deterministic TEXT id can collide across installations
(`graph_persons` already does). A new lane inherits those lessons or repeats them.

## 3. Requirements

**Identity and editing**

- **R-01** Permanent UUID family identity; legacy graph identities migrate without loss.
- **R-02** Identity-safe correction: renaming never changes the UUID, and two relatives
  with identical names are independently representable.
- **R-03** Complete canonical CRUD: add, edit, connect, edit relationship, remove
  relationship, safely remove/retire a person, inspect provenance.
- **R-04** Family Tree fact entry **routes to the correct authority**. The UI may show
  birth year, birthplace, death year, occupation; accepted values go to the canonical
  fact/event system. The surface may look unified while the backend stays separated.
- **R-05** Relationship provenance records the source: operator input, narrator
  statement, questionnaire, Family Truth, document, GEDCOM import, other import.
- **R-06** Awaited save — explicit operator save waits for backend success or failure.
- **R-07** Restart integrity — save → restart → reopen reproduces the accepted graph and
  facts with no duplicate creation.

**Lori**

- **R-08** Core family context: narrator, spouse/partner, parents, children, active
  family subject.
- **R-09** Dynamic expansion when conversation shifts to a grandparent, aunt, uncle,
  cousin, sibling or other relative.
- **R-10** Prompt-budget integration — family context draws from the existing budget
  system; no permanently reserved allowance.
- **R-11** Privacy filtering — operator-private data is excluded unless authorised.
- **R-12** Ambiguous-person handling — two Johns, two Aunt Marys, several grandmothers,
  an ambiguous nickname: **never silently guess**.

**Kinship**

- **R-13** Kinship resolver answers "how is Clara related to Kent?", "who are
  Christopher's first cousins?", "is George Kent's paternal or maternal grandfather?".
- **R-14** Derived relationships are calculated deterministically from direct topology.
- **R-15** Stable person UUIDs support references from interview passages, transcripts,
  audio, stories, photographs, timeline events and memoir chapters. The UI for those
  links need not arrive first, but the identity model must support them.

**Interchange**

- **R-16** GEDCOM staging — a `.ged` enters isolated staging and never writes directly
  into canonical family identity.
- **R-17** Operator reconciliation — confirm same person / create distinct person /
  leave unresolved-disputed. No automatic merge.
- **R-18** External provenance preserved: source system, filename and hash, import batch,
  GEDCOM XREF, source references.
- **R-19** GEDCOM export of supported canonical information, private material excluded by
  default.

**Publishing**

- **R-20** Visualisation: cards, the existing graph/scaffold, pedigree, descendant,
  hourglass or comparable.
- **R-21** Narrator profile generated from approved canonical bio/family information.
- **R-22** Memoir family appendix: about the narrator, family tree, family register,
  selected life profile/timeline, optional sources and attribution.
- **R-23** **One-source regeneration** — correct canonical information once and the next
  Lori context, Family Tree, profile, appendix and GEDCOM export all reflect it.

**Portability**

- **R-24** All accepted family knowledge survives export → restore → another accepted
  Lorevox installation.
- **R-25** Family identity and references survive cross-origin consolidation and
  sequential multi-narrator merging.

**Language**

- **R-26** **The existing relationship interpreter feeds canonical topology; it is not
  replaced.** `relationship_interpreter.py` already holds one vocabulary, derived rather
  than duplicated, and Phase 5B made the narrator's own wording decide the lane. That must
  survive: *Daddy*, *Mama*, *late wife*, *ex-wife*, *partner*, *half-brother*,
  *stepmother*, *chosen family* keep their semantic distinctions **and their provenance**
  when they become graph topology. `ex-wife` stores relation `wife` with the phrase in
  provenance; `late wife` keeps the word *late* under the deceased state; `partner` binds
  without manufacturing a marriage. A Family Tree that flattened these to "spouse" would
  undo accepted work, not extend it.

## 4. Dependencies

**Core bio/family work requires NO new dependency.** Use the existing Python runtime,
`uuid`, SQLite, the FastAPI backend, the JavaScript UI and the existing prompt/context
infrastructure. Do **not** install `networkx`, a GEDCOM parser, Graphviz or PyVis during
core Family Tree work because they may be useful later.

A new dependency requires all ten of: the exact capability required; why the current code
or stdlib is inadequate; licence; offline behaviour; privacy impact; maintenance and
activity; pinned version; installation impact; failure mode; removal path.

## 5. Testing architecture

Tests follow the **invariant**, not whichever file changed.

| Layer | Proves |
|---|---|
| 1 — unit invariants | UUID identity, relationship semantics, kinship, privacy, context tiering, provenance mapping |
| 2 — real SQLite | persistence, uniqueness, FK integrity, migration, rollback, idempotency, semantic references — against the real migrations |
| 3 — API | actual backend Family Tree CRUD |
| 4 — UI/DOM | controls, narrator scoping, save state, canonical reload. **DOM tests never substitute for backend persistence** |
| 5 — Lori context | what ACTUALLY enters the context. "A graph row exists" is not proof that "Lori knows it" |
| 6 — portability | ownership inventory, export, validation, restore, equivalence, erasure, Merge/Remap, semantic reference validation |
| 7 — publishing | correct once, regenerate, and the new value appears without secondary editing |
| 8 — real narrator smoke | only after synthetic acceptance: enter one family member, restart, talk to Lori, export, restore, regenerate |

This inherits the repository's existing doctrine rather than replacing it — in particular
*a fixture may not supply the property being proven* and *cite the line that reads the
value* ([`docs/TESTING-DOCTRINE.md`](../TESTING-DOCTRINE.md), `CLAUDE.md`).

## 6. Anti-drift rules

- **DRIFT-01** This spec is authority. A child WO that needs to violate an invariant
  stops and amends this document first.
- **DRIFT-02** One bounded mission per WO. Bio persistence, identity/graph, Lori context,
  kinship, GEDCOM and publishing stay separate even though all touch the Family Tree.
- **DRIFT-03** No parallel authorities. Every proposed new table or service must answer
  *why does this not belong in the existing graph, facts, Family Truth, timeline,
  provenance, prompt or portability authority?* Without a strong answer, do not build it.
- **DRIFT-04** Do not mutate production architecture to satisfy a convenient test. A
  failing test is evidence; decide whether production, the test or the assumption is
  wrong. Never redesign Lorevox around a fixture.
- **DRIFT-05** Follow the moved invariant — when it moves module, move and re-pin its
  focused tests rather than running an enormous gate.
- **DRIFT-06** Acceptance before expansion. No GEDCOM before the canonical Family Tree
  works; no advanced publishing before Family Tree + Lori context; no NetworkX before the
  native kinship implementation proves it is needed.
- **DRIFT-07** No speculative dependencies.
- **DRIFT-08** Every narrator-owned schema change gets the full portability treatment:
  migration, narrator-data inventory, exporter, restore, Merge/Remap, erasure,
  semantic-reference declarations, tests.
- **DRIFT-09** No automatic truth choices — nothing silently decides same person, correct
  conflicting date, correct relationship or correct external record.
- **DRIFT-10** Reconcile documents in the same logical block: child WO, this file's status
  if it changed, `HANDOFF.md`, the checklist, the backlog. Accepted work is never left
  documented as pending.
- **DRIFT-11** No microcommits. One coherent implementation/acceptance block per commit.
- **DRIFT-12** Evidence must prove product behaviour. Weak: a function returned true, a
  mock was called, a fixture has a row. Strong: the real schema holds the canonical
  record, a restart restores it, Lori receives it, the package transports it, and the
  restored installation behaves equivalently.

**Change-control classification.** Every idea met during implementation is **Type A**
(implementation detail, preserves every invariant — proceed), **Type B** (requirement
expansion — backlog or a future WO, never a silent scope increase), or **Type C**
(changes identity, authority, provenance, privacy, conflict policy, portability or
context policy — stop and amend this spec first).

**Acceptance discipline.** A phase is PLANNED / IN IMPLEMENTATION / IMPLEMENTED-NOT-YET-
ACCEPTED / ACCEPTED. *"Code exists" is not "accepted."* Acceptance needs implementation,
the required focused tests, negative and failure tests, no known contradiction of the
phase mission, portability accounted for, documents reconciled, and evidence recorded.

**The evidence packet.** Each work order closes with one, and **no documentation-only
claim substitutes for it**: files changed · schema migrations · diff summary · the exact
focused test commands · exact pass/fail/skip counts *(a bare `OK` with skips is not a
pass)* · manual acceptance evidence where required · portability impact · known deferred
items · **confirmation that unrelated source data was not modified**.

## 7. The permanent end-to-end acceptance scenario

Use this as a standing acceptance case for the lane as a whole:

The operator opens the narrator's Family Tree and adds Clara Mae Horne; Lorevox assigns an
opaque UUID; the operator records the direct relationships that place Clara in the family
and enters birth year 1898. **The relationship saves in the canonical graph and the birth
year in canonical fact storage**, provenance records operator entry, and the UI reports
*Saved to Lorevox* only after backend success. The operator then changes Clara's displayed
or maiden name and **the UUID is unchanged**. Lorevox restarts; Clara and her relationships
remain. Clara does not waste prompt context while irrelevant. The narrator says *"Grandma
Clara taught me to sew"*; Lorevox resolves Clara **or asks for clarification**, promotes her
into family context, Lori recognises the relationship and responds naturally, and the
kinship engine can explain how Clara is related. The narrator package is exported and
restored on another accepted installation: Clara keeps the same UUID and her relationships
and facts survive. GEDCOM export includes the supported information, and the family
appendix can include Clara.

**The system is not accepted if any step depends solely on browser or local-machine state.**

## 8. The child work orders

The master owns architecture and invariants; each child owns only its implementation scope
and evidence.

| # | Work order | Owns |
|---|---|---|
| 01 | [`WO-BIO-PERSISTENCE-INTEGRITY-01`](WO-BIO-PERSISTENCE-INTEGRITY-01_Spec.md) | making bio entry safe enough for real manual family-history work |
| 02 | [`WO-FAMILY-IDENTITY-CANONICAL-GRAPH-02`](WO-FAMILY-IDENTITY-CANONICAL-GRAPH-02_Spec.md) | UUID identity, the canonical editor, relationship provenance |
| 03 | [`WO-LORI-FAMILY-CONTEXT-03`](WO-LORI-FAMILY-CONTEXT-03_Spec.md) | tiered, budgeted, dynamically expanding family context |
| 04 | [`WO-KINSHIP-RESOLVER-04`](WO-KINSHIP-RESOLVER-04_Spec.md) | derived extended kinship from direct topology |
| 05 | [`WO-GEDCOM-INTERCHANGE-05`](WO-GEDCOM-INTERCHANGE-05_Spec.md) | staged import, operator reconciliation, export |
| 06 | [`WO-FAMILY-PUBLISHING-06`](WO-FAMILY-PUBLISHING-06_Spec.md) | profile, register, charts, memoir appendix |

**Sequence, and it is not negotiable** — each depends on the one above it:

```text
Portable Narrator 0–6                    ✅ accepted
Multi-Origin Merge/Remap                 ← CURRENT (this lane is blocked behind it)
family consolidation acceptance
Phase 7 clean Lorevox data world
Phase 8 Lorevox product cutover
      │
      ▼
BIO-PERSISTENCE-INTEGRITY-01
      ▼
FAMILY-IDENTITY-CANONICAL-GRAPH-02
      ▼
LORI-FAMILY-CONTEXT-03
      ▼
KINSHIP-RESOLVER-04
      ▼
GEDCOM-INTERCHANGE-05
      ▼
FAMILY-PUBLISHING-06
```

## 9. The minimum usable milestone

Before GEDCOM or sophisticated publishing, Lorevox must already allow: **an operator
manually enters a family member and biographical facts → saves canonically → restart
preserves everything → Lori knows the relationship when relevant → the narrator package
transports it to another Lorevox installation.**

That milestone requires **no new Python dependency**.

## 10. The product boundary to protect

The goal is not *"build another family-tree program"*. It is to **connect the people in a
narrator's life to the memories the narrator leaves behind**. Clicking George Horne should
eventually show who George was, how he was related, what is known or disputed about him,
where he appears in the narrator's timeline, the photographs and documents involving him,
the interview passages about him, the audio and transcript references, and the memoir
stories and chapters he appears in.

That connection between family structure and living narrative memory is why this belongs
inside Lorevox and not in a genealogy application.

**Explicit non-goals.** Lorevox is not attempting to become Ancestry, FamilySearch or
Gramps; not a public genealogical research service; not an automated historical-record
matching service; not a DNA relationship system. Genealogy interoperability **supports**
the mission; it does not replace it. A proposal that moves Lorevox toward any of those is
a Type C change and needs this document amended before a line is written.
