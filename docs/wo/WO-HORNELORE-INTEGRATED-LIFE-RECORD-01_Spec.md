# WO-HORNELORE-INTEGRATED-LIFE-RECORD-01
## Complete product review, Repair A, canonical life record, questionnaire, Lori, chronology, and portability

**Issued:** 2026-09-22  
**Owner / Git operator:** Chris  
**Execution collaborator:** Claude, working in Chris's local Hornelore checkout  
**Status:** Work order for review and execution planning. **Chris explicitly authorizes clearing the currently active Lorevox narrators from the WORKING installation as a scoped, standalone cleanup after identifying the exact records and deletion path.** This does not authorize deleting the saved portable narrator packages or beginning the life-record product-code migration.

> **First instruction to Claude:** Review the actual local code and changed files, establish where Hornelore is today, explain the end product and the direction of travel, and return an integrated execution plan. Do not start by editing another validator or proposing a commit. Read this entire order and the referenced repository documents before reporting.

---

## 0. Baseline, boundaries, and ownership

### Known baseline—verify rather than repeat blindly

- Chris pushed four *design/documentation/script* commits ending at **`637ab95`**: `b1e64ac`, `8140802`, `efc2237`, `637ab95`. Verify current local HEAD and remote state **without performing Git mutations**. Nothing in those commits implements the new life record in production.
- At the last reported local status the only outstanding files were modified `ui/js/bio-builder-graph.js` and untracked `tests/test_bb_graph_partial_view_preservation.js` (**Repair A**). Claude must inspect their **current full contents and actual diff**, because they are absent from pushed `main`. Do not claim the changed repair has been externally reviewed merely because the committed version was read.
- Claude's most recent report acknowledges **26 design mutations caught**, not 25. Treat that as a *reported local result* until reproduced; no mutation count stands in for a real integration test.
- Current product uses **shared SQLite** (`DATA_DIR/db/lorevox.sqlite3`). One SQLite database per narrator was discussed but is **not implemented or recorded as a settled repository decision**. Keep the physical-layout decision open. Do not introduce MongoDB by default.
- Existing BagIt `.lorevox.zip` is the portable narrator package. **Restore, merge and schema migration are distinct operations**; restore preserves the narrator and identifiers verbatim. Do not invent a replacement exporter.

**Git is Chris's responsibility.** Claude must not stage, commit, amend, push, pull, reset, stash, discard, or remove locks on Chris's behalf. Supply bounded file lists, test results, and suggested commit grouping for Chris to execute. A clean tree is **not** a prerequisite for pushing already-committed work, and Repair A is not to be bundled into design commits.

**Data boundaries — revised by Chris:** The narrators currently loaded in the working Lorevox installation are finished, saved, and put away. **Chris wants those live working narrators removed; their removal is authorized by this instruction and does not need another generic approval checkpoint.** First use actual code and a read-only inventory to identify the exact active narrator IDs, which application/data root is being cleared, the existing narrator-deletion operation, and what it deletes. Then remove only the identified live narrator records through the application's supported scoped deletion process, checking the resulting working installation is empty of those narrator records. Do not invent a bulk SQL cleanup or classify real/synthetic narrators by names. If there is an ambiguous target, unsupported deletion path, or an operation would destroy shared/unassigned material or another narrator, stop **that deletion only** and ask one specific question. Keep saved USB/BagIt packages and other archived copies untouched, and do not restore their contents into the development workspace automatically. Browser-local drafts and caches associated with the removed narrator IDs must be explicitly reconciled so they cannot repopulate the working installation. Subsequent design and implementation use new synthetic narrators and isolated test roots. No privacy audit as part of Git cleanup or this work order. Package security/encryption is a separate product decision, not a reason to delay this cleanup.

**Execution rhythm:** One cohesive review and decision checkpoint; after approval, work in substantial dependency-ordered implementation batches with focused tests and a consolidated handoff. Do **not** ask for a commit after each tiny change or turn the full multihour gate into a routine unit test.

---

## 0A. Clear the current working narrators — an authorized cleanup, not a migration

**Chris's new direction:** The existing Lorevox narrators have been saved and put away. They are **not** the population that must remain in the working installation while the life record is rebuilt. Remove the *currently active narrator records* from Lorevox; leave the archived narrator packages alone. This supersedes prior wording that prohibited touching active narrator data without another approval.

**Sequence:** (1) As part of the first code review, identify the precise running `DATA_DIR`, narrator IDs, narrator-delete API/implementation, scope of associated DB rows and owned media, and any shared/unassigned records. (2) Establish that the saved packages Chris refers to are **outside the deletion target**; rely on his confirmation that they are saved rather than demanding a new full preservation project. (3) Use the product's established narrator-scoped removal mechanism for the identified active narrators; do not run indiscriminate `DELETE FROM`, remove the whole shared SQLite database, or delete files in the archival/USB locations. (4) Account for browser drafts/local caches belonging to the removed IDs, so opening Lorevox cannot repopulate it from a stale draft. (5) Report the exact removed narrator IDs and working root and confirm no active narrator records remain; distinguish any intentionally retained shared/unassigned objects. If an actual deletion path is missing or dangerously broad, report the *specific* blocker and an appropriately scoped correction rather than proceeding destructively.

**This cleanup is independent of the life-record migration.** Do not re-import the saved narrators into the new model as the default acceptance population. Build and test with new fictional narrators in isolated test roots. Revisit restoration of an archived narrator only if Chris asks for it later. A separate-narrator-DB decision is **not** a prerequisite for clearing the current working installation.

---

## 1. Define the actual end product before touching product code

Produce a concise, concrete **end-product contract**, illustrated by complete operator and narrator journeys:

1. An operator creates or opens a narrator, views their existing record, and fills **the complete questionnaire** in any order. People, relations, multiple homes/jobs/unions, times and uncertain dates, animals, legacy material, memories, and Life Today remain editable without mandatory completion, arbitrary repeatable caps, implicit deletion, or surprise save on navigation/switch. An intentionally removed item can be removed safely; omission in a partial view is not deletion. Unknown, unanswered, stated No, and stated **zero** are distinct.
2. The narrator is represented by a stable **person ID**. Names are retained as entered; no space-splitting into first/last names; optional supplied parts, alternate names and provenance do not mint another person. A parent's or child's DOB is the same semantic birth-date concept applied to **that person's ID**, not another section-specific concept.
3. The narrator's **accepted DOB** is the start anchor of Hornelore's **existing seven-era life-span scaffold**, not of a new event spine. For a living narrator, the present-day boundary is computed at render; for a deceased narrator, a *known* death date bounds the span, and an unknown death date does not turn into today. Unknown DOB yields no fabricated scaffold; approximate DOB and derived ages retain uncertainty. Related family history may precede the narrator's birth. Typed occurrences/periods supply connections without replacing this scaffold.
4. Lori sees appropriate, attributed recorded facts through **real final prompt assembly**, recognizes answered topics in Profile Seed, retrieves details when needed, handles each mentioned person's living/deceased/unknown status accurately without raising death unprompted, and does not convert operator-entered facts into purported narrator recollections or more interrogation.
5. The Life Map retains **promotion and `story_projection` placement authority**: a dated occurrence or calculated age never silently establishes an era; unplaced never becomes Today. The memoir retains its actual three lanes—operator-authored prose, verbatim captured stories, and trip notes; there is **no automatic memoir-writing service** in scope.
6. A portable package contains the selected narrator's complete **eligible** record and referenced sources/files, can be validated and restored into an isolated installation, and accurately declares intentionally excluded unsaved browser drafts and shared/unassigned material. A checksum means integrity of collected bytes, **not completeness**.

**Deliverable 1:** one-page description of the end product; at least three complete journeys (new narrator; family record with corrections and conflicting DOB; export/isolated restore); a diagram/table distinguishing authoritative records, explicit human approval ledgers, rebuildable projections, source recordings and installation-owned resources. Specify what is *already working*, *designed only*, *broken*, and *not yet decided*.

---

## 2. Review the real code and dependencies (first actual task)

Review **full relevant functions and their call sites**, not snippets, design summaries, or only the files one intends to edit. Inspect current local uncommitted code as well as pushed sources. Trace relevant paths across:

- `ui/js/bio-builder-core.js`, questionnaire, graph, family tree, projection map, source/candidate UI, hydration, local drafts, saves, narrator switching, and HTML initialization/load order;
- graph API / backend persistence, graph IDs, full-replace semantics, person/relationship ownership and source provenance;
- Operator Intake, `extract.py` and extraction ledger, `suggestion_review`, `questionnaire_schema`, `bio_schema`, `bio_fact_router`, family-truth review/promotion, `profile_json` and `interview_projections`;
- Profile Seed and Stage 8 anchored asking, questionnaire-to-Lori adapter, fact retrieval, prompt composer, prompt-budget drop order and **assembled model input**;
- `life_spine`, `chronology_accordion`, `lv_eras` Python/JS, `story_projection`, Life Map rendering and promotion paths;
- `story_candidates`, provenance, review states, narrator audio/transcripts, story retrieval and actual memoir export;
- trip repository, travel view and `trip_bio_suggestions` (currently documented as dead/stub, **verify**), photos, archive attachments, multi-person and shared/unassigned media;
- `db.py` and direct SQLite connection sites, narrator scoping, `narrator_data_inventory.py` / every applicable `DbLane`, `narrator_package.py`, existing restore/merge behavior, and schema/version migration dependencies.

For every changed or affected component, record **real writer(s), reader(s), authority, record identity, review/approval gate, narrator scoping, export/restore coverage, and tests**. State explicitly what was *not* inspected and why. If actual code disproves a document, correct the design assertion rather than reshaping the code to satisfy an old document. The first review should map the **minimal coherent change surface**, not conduct an unrestricted repository refactor.

**Deliverable 2:** a source-backed current-state → end-state dependency map, discovered risks, and a *single* ordered delivery plan showing which work genuinely depends on which decisions. Include the exact scoped-deletion route and target inventory for §0A; carry out the authorized cleanup once its scope is established, without waiting for the wider catalog and database decisions.

---

## 3. Review and isolate Repair A before the new model

Read the complete **local** modified `ui/js/bio-builder-graph.js`, its diff against HEAD, `tests/test_bb_graph_partial_view_preservation.js`, the graph backend `PUT/GET` contract, source-clearing logic and narrator-switch hooks. The reported failure: `syncFromQuestionnaire` rebuilds after clearing questionnaire-sourced nodes, so a partial mother-only document can remove an already stored father and a full-graph PUT may persist that loss.

Verify in actual code and focused tests:

- Partial response/partial questionnaire **does not delete absent people, relationships or fields**; confirmed empty, absent section and explicit delete are distinct.
- Intentional deletion is still possible and scoped to the selected entity; it cannot be resurrected by a later profile sync, browser draft or stale GET.
- Existing IDs survive edits; same-name people remain distinct, names are not identity keys, and relationship edges remain valid.
- Async graph fetch/PUT and narrator switches are generation- or identity-guarded; a late response for narrator A cannot populate or overwrite narrator B. Check core's generation pattern and the graph's own restore behavior rather than assuming one protects the other.
- Graphs from profile, questionnaire and manually curated sources obey one defined merge/source policy; full-replace backend writes are not built from incomplete or unhydrated state.
- Test the real modified module and actual backend boundary where feasible; characterize all **25 claimed graph checks** rather than relying on their count. Focus on omissions, explicit deletes, confirmed empty, concurrent/switch races, and round trips.

**Deliverable 3:** review of exact local changes; test command/output and failure cases; any small necessary repair; whether the two Repair A files are ready for a **separate Chris-controlled commit**. Do not fold the new canonical data model into Repair A.

---

## 4. Reconcile the design's known contradictions in one bounded pass

Claude has now reproduced the following; do **not** repeat the same pattern by merely changing expected values to make fixtures green:

**Assertion meaning.** `rule_competing_claims_kept_and_linked` currently infers conflict from *a list of length >1*. This rejects the DOB fixture when run through full `run()` and can misclassify successive jobs. Define the *identity of one proposition* (subject + concept + relevant temporal/context qualifier), its asserted alternatives, accepted assertion and dispute relations. A list may contain distinct facts, alternatives, historical versions or retellings. Preserve the explicit `acceptedAssertionId` decision; write eligibility or source/status names must never silently adjudicate whose account is true. Test the **same DOB fixture through all model rules** as well as the resolver.

**DOB evidence and event pointer.** Apply source/recordedAt/status/provenance requirements to date assertions despite their `{text,value,precision}` structure. Resolve `birthEventRef` only if it points to an existing **birth event whose subject is that person**; reject a union event, another person's birth, missing or ambiguous references. Apply analogous death-event integrity. Test corrections, conflicting and superseded DOBs, approximate and partial dates, exact ages before/on/after birthday, and missing anchors. An accepted assertion may not be rejected by a shape-based conflict rule. Do not infer Life Map placement from dates or ages.

**Stories and attribution.** Narrator correcting themself aloud is a **new captured telling** with its own preserved candidate; operator writing an editorial narrative is authored; a curation edit changes curation, not recorded narrator words. Define `supersedes`/links and presentation behavior without a duplicate authoritative body or misattribution.

**Catalog counts and epistemic labels.** Fix the decision sheet's incorrect “(10)” group and `spouse.middleName?` uncertainty by comparing to individual source paths—not by hand-adjusting the grand total. The reconciliation script's raw source counts are **measurement**; `SUBJECT_OF`, `CONCEPT_OF`, and define/retire dispositions are **human semantic proposals**. Label these separately in output and JSON; derive totals mechanically, including all 41 questionnaire-only fields. Do not present a zero literal key overlap as zero semantic overlap. Retain historical audit findings as dated rather than quietly overwriting their original evidence.

**Packages.** Clarify whether proposed `biography.json` is a **derived additional export view**, how it relates to shipped per-table JSONL, package version, authority and importer. Restore preserves IDs; merge is separate; older-package → new-schema migration uses its own reviewable ledger. No automatic migration of actual family records.

**Deliverable 4:** one reconciled model/spec/decision-sheet set, executable checks covering the full invariants rather than isolated favorable subfunctions, and a short list of genuinely unresolved *product* choices. Use independent expected results, negative cases and mutations selectively; don't create a second miniature product inside a validator.

---

## 5. Bring the actual product choices to Chris, with recommendations

Show a **machine-reconciled one-row-per-path ledger** for the four vocabularies, followed by grouping on `subject ID/subject role + semantic concept + context`. Give proposed outcomes and impacts for:

- all **26 `NEEDS_CONCEPT` groups** and **41 questionnaire-only fields** (confirm exact source path enumeration and grouping); separate aliasable spellings—including child/spouse DOB and birthplace—from truly missing concepts;
- ordinary people for grandchildren and prior partners, with time-aware relationships; a child may exist without every parent known;
- community involvement as an activity/period; great-grandparent service about *that person*, not automatically about the narrator;
- reading experiences as volunteered, attributed biography, **not an inferred literacy or cognitive assessment**; optional Life Today routine as a description, not a clinical inference;
- a deliberate choice about narrator-selected health reflections versus structured medical/medication facts; do not automatically expand or retire extraction paths;
- what to do with `trip_bio_suggestions`; breadth and exact field-level UX of the full eleven-topic operator questionnaire;
- whether typed occurrences are canonical or an interim derived index; narrator-scoped **shared SQLite vs per-narrator SQLite** with realistic routing, cross-person media and migration costs.

State where approval changes Lori's asking/extraction behavior versus only an editor binding. **Do not ask Chris to approve 110 unexplained raw field names** or implement a disposition because it appeared in a proposed column. Cite the original source paths for each grouped decision. Package encryption is a separately identified feature decision, not a privacy-audit requirement or blocker for this review.

**Deliverable 5:** a compact approval sheet with recommendations and consequences, plus machine-readable path coverage. Do not begin the wider product-code build until Chris has approved the consolidated direction and product decisions.

---

## 6. Approved implementation: one coherent system, in dependency order

**Only after the review/decision checkpoint and Chris's approval for the **new life-record product implementation**. §0A's targeted removal of existing working narrators is already authorized and may proceed after its scoped deletion route is established. Organize work as coherent batches with focused gate(s) per changed invariant, not one commit request per edit.

**Batch A — catalog and authority.** Build an actual versioned semantic-concept catalog and explicit subject/context UI and legacy bindings, with a loader and fail-closed checks against *real* producers **and consumers**: questionnaire, `EXTRACTABLE_FIELDS` and aliases, projection map, `bio_schema` asking anchors/narrative value/life-stage eligibility, Profile Seed, and Lori's renderer. Preserve `bio_facts` foreign keys and existing review semantics. Ensure every concept has an owner and packaging lane, or an explicit intentional exception. Provide migration mappings for existing stored keys and an unmapped-value ledger, not silent omission.

**Batch B — canonical record and safe writes.** Implement approved person/name/relationship/place/occurrence/period/assertion/story-reference model and the narrator-scoped single writer. Distinguish recordedBy from assertedBy and explicit acceptance; choose how evidence/source IDs link. Use path-level expectedPrevious and transactional all-or-nothing writes; permit nonoverlapping concurrent edits, reject conflicting same-path edits. Stable identities, no inferred person merges, date/text/precision preserved, unknown ≠ No, stated zero retained. Existing family truth and story source assets must not become silently overwritten parallel authorities. Keep physical database layout unchanged unless separately approved.

**Batch C — complete operator experience.** Build the **full field-level** questionnaire and interactions, not an eleven-heading mockup: supplied full names and optional components, uncapped repeatable people and periods, relationship edits, families without complete kinship, exact/partial/uncertain dates, life status, preferences, homes, learning/work, service/community, traditions, travel view, hobbies, animals, Life Today, memories, corrections, reviewed deletions and recoverability. Server-backed hydration/drafts/switch behavior must preserve real input and prevent stale drafts from winning. Opening or switching views must not write. Any migration from old questionnaire shapes preserves every source leaf or explicitly retains it as legacy.

**Batch D — real consumers.** Hook the canonical view into Profile Seed and Stage 8; trace known-answer and refusal/topic coverage. Feed Lori compact, mention-selected names/relations/life statuses within measured final-prompt budget, plus reliable retrieval of additional facts/stories. Demonstrate death-aware phrasing without unsolicited death discussion. Preserve the existing DOB scaffold and chronology engine; verified approved occurrence placement alone reaches Life Map. Memoir remains operator prose + verbatim candidate stories + opted-in trip notes, with correct attribution. Preserve existing 14-table trip hierarchy and trip text; optional place IDs are references, not destructive normalization.

**Batch E — package and restore.** Extend `narrator_data_inventory` and existing BagIt export for every approved new owned table, dependency/reference closure, paths and media, recordings, transcripts and reviewed assertions. Define shared/unassigned asset handling from **ownership and package inclusion**, not number of people depicted. Handle browser-only unsaved drafts through verified save or explicit manifest exclusion. Use schema/version-aware import. Test ordinary same-ID restore, distinct merge, and legacy migration separately into **isolated destinations**, comparing original data and all expected references/files. No edits to the saved narrator USB packages. The archived narrators are **not** automatically imported back into the working installation; package compatibility is proven with fictional packages and isolated destinations unless Chris separately asks to restore an archived narrator.

If sequencing requires revisiting an earlier batch, document the dependency and preserve the single architecture; do not ship a shadow store, temporary competing timeline, alternate packager, or permanently duplicated fact solely to avoid integration work.

---

## 7. Product-level acceptance, not a green fixture count

Before reporting *done*, demonstrate with hard fictional biographies and actual execution paths:

- A new narrator with no existing rows; a partially filled form with multiple people; mother-only edit preserving father; explicit father removal not resurrected; narrator switch with slow GET/PUT and no cross-narrator contamination.
- DOB accepted/corrected/conflicted and source-linked; another person's birth cannot anchor narrator; partial/approximate/unknown DOB, deceased-without-date, moving present endpoint, accurate ages, and the original seven-era chronology preserved.
- Similar names and alternate names without ID merging; multiple relationships and changed unions; six siblings stated/two named, explicit **zero siblings**, and blank list not treated as zero.
- Parent death and living spouse reaching **final assembled Lori prompt under realistic token budget**; unknown remains unknown; correct tense; no unsolicited death prompt; Profile Seed recognizes genuine topic evidence; retrieval succeeds for detail shed under budget.
- An unpromoted event cannot appear as a verified Life Map anchor; no inferred era from year or age; unplaced ≠ Today. Narrator retelling and operator prose retain distinct source and intact words; memoir renders only its existing three lanes with accurate attribution.
- Existing trip hierarchy, corrected shared place without rewriting trip text, multi-person media, relative-only and unassigned media policy, and no dangling refs.
- Real exporter inventory coverage, successful BagIt validation **and** isolated restore/re-export equivalence for all required data and media; explicit excluded drafts; independent restore vs merge vs migrate behavior.
- Focused test families corresponding to moved invariants, then the relevant preservation suites, and the long baseline only at the planned integration/acceptance milestone. Provide actual commands, exit codes, totals, skipped tests, comparison baseline and scorer; no hand-carried success number.

**Stop/rollback conditions:** any **unscoped or unintended** deletion or write (the exact working-narrator removals in §0A are expressly authorized); wrong narrator or wrong birth-event anchor; narrator words altered or misattributed in new work; unreviewed fact promoted; package excludes required owned data without refusal/disclosure; restore changes identity semantics; archived packages altered; any other existing data touched outside the approved removal scope. Isolate failures and repair underlying code, not merely expectations.

**Final deliverable:** source-to-end-product trace matrix, working UI walkthrough, resolved approval decisions, changed-file and test report, narrator-data/package coverage report, remaining limitations, suggested coherent commit groups for **Chris**, and explicit separation of implemented, verified, deferred and not examined.

---

## 8. Required first response from Claude—one checkpoint, not a drip feed

Return, in this order:

1. **What exists now** (including actual current local Repair A diff, not the committed old graph) and what the four pushed design commits did *not* implement.
2. **What the finished product will do**, with a truthful walkthrough from operator entry through Lori, DOB/eras, Life Map/memoir, and BagIt restore.
3. **Code-backed map** of relevant readers/writers, authority, risks, coverage, and the minimal coherent change surface.
4. **Repair A verdict**, including its real code/test evidence and what Chris would commit separately if accepted.
5. **One integrated batch plan**, dependencies, acceptance gates, and product decisions for Chris; distinguish decisions needed now from those safely deferred. Include the latest DOB/conflict/provenance/story/count/packaging corrections.
6. Include §0A's **precise deletion target, supported deletion route, and cleanup result**. Removal of the currently active working narrators is explicitly authorized after this narrow code/scope verification; no other live-data changes, no Git mutations, and no life-record product-code migration during the initial review.

Do not end with only “checking,” another generic audit promise, or a request for a tiny commit. Complete this review and return a substantive, actionable handoff.
