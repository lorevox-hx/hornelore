# Integrated life record — decision packet 1

## ✅ DECIDED — Chris, 2026-09-22

This section is the record. The packet below it is kept as the question
that was answered, and **where the answer refines a recommendation, the
answer governs.**

| | decision | refinement recorded |
|---|---|---|
| **D1a** | approve | — |
| **D1b** | approve | — |
| **D1c** | approve | **An age at death stated by a source is a reported assertion; an age derived from birth and death dates is calculated and never stored.** `G14` is `person.death.reported_age`, attached to the death occurrence, not a generic `person.death.age`. If a reported age and a computed age disagree, that is a discrepancy for the operator to see, not something to resolve silently. *(Applied: `build_concept_catalog.py` `CONCEPT_OF`; appendix regenerated.)* |
| **D1d** | approve | — |
| **D1e** | approve | **Confirmed later the same day:** service is modelled as `event.service.*` occurrences with the great-grandparent as participant/subject (D7), not as permanent `person.service.*` attributes. `greatGrandparents.militaryEvent` is **not** narrative — its label is *"military event / deployment / dates"* and `extract.py:5054-5061` routes years of service, deployment location and rank into it — so it binds to the occurrence (`event.service.occurrence`), not `story.service`. |
| **D1f** | approve as the **current structured-extraction disposition** | **Batch A requirement:** questionnaire availability, structured-extraction eligibility, Lori asking/retrieval eligibility and narrative value are **separate catalog properties**. The permanent product is not made narrower because the current extractor sends every field on every call; Batch A adds **context/relevance-scoped extraction**, so catalog breadth is not tied to prompt size. The "operator-only for now — would cost prompt on every turn" reasoning in D1f below is **withdrawn** as a basis for judging value. *(Applied: catalog spec §3 entry format and §5.)* |
| **D2** | (a) | **Grandchildren and prior partners are ordinary people plus relationships, shown within the appropriate eleven-topic UI. No relationship-specific canonical schema is created to give them "sections".** The consequence line in D2 below saying Batch C "adds two people-bearing sections" is superseded. |
| **D3** | (a) | — |
| **D4** | (a) | — |
| **D5** | (a) | **One rule in every governing document and the validator: a living narrator's span stays open; a known death date ends it; a deceased narrator with an unknown date gets no invented endpoint.** *(Applied: integrated WO §1.3 and the DOB contract in `WO-LIFE-RECORD-01` §2A, both of which still said "computed at render". Validator `resolve_life_span` and the checkpoint already matched.)* |
| **D6** | (a) | — |
| **D7** | (a) | canonical occurrences and periods, **beneath**, not replacing, the DOB and seven-era scaffold |
| **D8** | (a) | shared SQLite; narrator isolation enforced in the writer and data model; no 30-call-site routing migration |
| **D9** | (a) | graph becomes a derived projection of the life record; server-side version protection while the current PUT exists |
| **D10** | approve | explicit Remove with recoverability, route support, and the full field-level eleven-topic questionnaire |
| **D11** | approve | **Retire `parents.notes`, `faith.notes`, `military.notes`, `pets.notes`, `travel.notes` from structured extraction.** Existing values are migration-preserved. There is no generic `note.about_subject` extractor destination — that would recreate the bucket D1d removed. The fields may stay questionnaire-editable as narrative/context, routed to the matching lane: parents → story about that person, faith → story of faith, military → story of service, pets → story about that animal, travel → the trip-notes lane. *(Recorded from the reviewer recommendation Chris forwarded on 2026-09-22.)* |
| **D12** | approve | **Compatibility redirect `family.marriageDate` → `marriage.marriageDate`, in A3.** A pure naming mismatch: WO-04 moved the field (`extract.py:290-292`) and the model still emits the old spelling — **because the extractor's own prompt still teaches it** (few-shots `extract.py:793-799`, `:1237-1242`; rule text `:1804-1805` says *"Do NOT drop family.marriageDate"*). Rejected **8×** across the full `r6-batchA-base2` run. **The prompt must be corrected in the same change as the redirect**, or the redirect is patching the extractor's own instruction. No new concept and no wider extraction — it restores delivery of a fact the model already finds. **Required tests:** (1) the legacy path is accepted and normalised to the canonical path; (2) the canonical path is unchanged; (3) both forms in one response produce ONE marriage-date candidate, not two. Keep the originally emitted path in provenance if that mechanism exists. **Other marriage aliases only on current evidence** (Chris, 2026-09-23). That evidence exists for **`family.marriagePlace` → `marriage.marriagePlace`**: emitted and rejected at 23:57:48 in `r6-batchA-base2` (`"North Dakota"`, `marriage_story`). It is included under this rule with the same three tests; nothing else is. *(Chris, 2026-09-23.)* |
| **D13** | approve | **Pet birth dates become extraction-eligible, with compatibility alias `pets.dateOfBirth` → `pets.birthDate`, in A3.** Evidence: `pets.dateOfBirth = "around 1964"` emitted and rejected in `r6-batchA-base2` (23:52:24, `childhood_pets`). The concept already exists in the catalog; this makes it extraction-eligible (a D1f-class change, not only a spelling fix). **Date semantics are the ones already adopted everywhere:** an approximate value stays approximate — `"around 1964"` never becomes `1964-01-01` and never presents as exact. **A pet's birth date is never inferred from an age** as authoritative fact; a derived estimate may exist only as a labelled estimate with provenance. Same three tests as D12 (legacy accepted and normalised; canonical unchanged; both forms → one candidate), plus: an approximate spoken value round-trips unchanged. *(Chris, 2026-09-23.)* |

**Additional catalog invariant, recorded:** a concept may be askable or
retrievable by Lori **without** being automatically extractable from every
turn, and may be editable in the questionnaire **without** being something
Lori should proactively ask about.

**Status:** Batch A is unblocked by these decisions. It has **not** started.

---

**2026-09-22 · for Chris to decide.** Nothing below is implemented, and
approving it implements nothing: each decision unblocks a batch, and the
batch does the work. Every recommendation says what it **changes** — in
particular whether it changes what Lori or the extractor **notices**, or only
where an operator's entry is **stored**.

**How to answer.** The last section is a one-line reply form. "Approve all
recommendations" is a valid answer; so is approving some and changing others.

**Where the evidence is.**
- Group ids (`B`, `A`, `G`, `Q`) are rows in the generated
  [`CONCEPT-DECISION-APPENDIX.md`](../specs/CONCEPT-DECISION-APPENDIX.md), each
  carrying its original source paths. The appendix is produced from the
  shipped sources by `build_concept_catalog.py --markdown` and is not edited by
  hand.
- Code claims carry `file:line`.
- Token figures are **estimates at 4 characters per token** and are labelled
  as such.

---

## What each decision gates

| before | decisions |
|---|---|
| **Batch A** (catalog) | **D1–D6** — this packet's main business |
| **Batch B** (canonical record) | D7 occurrences · D8 storage layout · D9 the graph's future |
| **Batch C** (questionnaire) | D10 removal and the form's breadth |
| nothing | encryption · package-job metadata reporting (recorded, not blocking) |

D7–D10 are written out below so you can see them coming. Only D1–D6 are needed now.

---

## Two measurements that shape D1

**Undeliverable output.** Of 146 extraction targets, **69 have no destination
under any name**. Their output reaches the review queue and can never be
accepted; `suggestion_review.py:144` recorded 20 of 30 queued suggestions in
that state.

**Every extraction call pays for all of them.** `_build_extraction_prompt`
sends every `EXTRACTABLE_FIELDS` entry on every call (`extract.py:697-702`).
The in-line comment says "only fields relevant to the current section", but
the loop does not filter. Measured: the field list is **9,118 characters
(~2,280 tokens, estimated)**, and **4,515 characters (~1,130 tokens) of it
are the 69 undeliverable paths**, all inside the locked 8,192-token window.
So adding fields to extraction costs budget on every turn, and removing them
gives it back.

**What "define" and "alias" do and don't do.** They make suggestions
*acceptable*. They don't turn on automatic writes. The browser's write mode
starts from the projection map and can only be lowered by the server, never
raised (`projection-sync.js:364-367`). `candidate_only` output goes to the
in-browser candidate list (`:518`); `suggest_only` output goes to the server
review queue (`:593`). Neither writes the questionnaire.

The extractor labels some spouse paths `prefill_if_blank`, but that label
cannot take effect. Spouse isn't in the projection map, so `getWriteMode`
returns its safe default, `suggest_only` (`projection-map.js`, `getWriteMode`).

---

## D1 — The concept catalog's contents

Split into parts so you decide product questions rather than field names.

### D1a · Five facts broken at both ends — `B01`–`B05`

The extractor looks for these, the form offers a home for them, and they
never meet because they are spelled differently: child and spouse birth date
and place (`dateOfBirth` against `birthDate`), and a grandparent's story
(`memorableStory` against `memorableStories`).

**Recommend: bind each pair to one concept.** Queued suggestions become
acceptable. **No change** to what the extractor notices or to prompt size.

### D1b · Eight prefix aliases — `A01`–`A08`

`family.children.firstName` against `children.firstName`, and so on.

**Recommend: bind them.** Same consequence as D1a. The `prefill_if_blank`
label on `A04`–`A08` is inert, as explained above.

### D1c · 34 ordinary facts with no home — `G01`–`G34`

These are facts about other people: birth, death, names, occupation and
education for children, spouse, siblings, parents, grandparents and
great-grandparents. Also narrator events (`G01`) and stories (`G32`–`G34`).

**Recommend: define each as one concept whose subject is a person reference.**
`person.birth.date` about a sibling is the same concept as about a parent.
That is the entity model's whole premise, measured in the catalog spec §2.

This includes the four **death** concepts (`G11`–`G14`), which are the filed
defect `BUG-LORI-UNAWARE-OF-DEATH-01`.

`G18`, `G20`, `G21`, `G29` and `G30` involve grandchildren and prior partners,
which have no form section; they depend on **D2**.

**Changes:** these suggestions become acceptable. **No prompt change**, since
the extractor already looks for all of them.

### D1d · Retire the seven `*.notes` paths — `G61`–`G64`

**Recommend: retire from extraction.** `personal.notes` was already retired
by WO-04 decision 4, because *"a miscellaneous bucket with no home in the
form invites the extractor to file anything it cannot classify"*. That
argument applies equally to each of these seven.

**Changes:** the extractor stops sending unclassifiable text to these buckets.
The prompt shrinks by **589 characters (~150 tokens, estimated)**. The
narrator's own words are not lost: verbatim capture is the story lane's job
(WO-LIFE-RECORD-01 §2.6), not extraction's.

### D1e · 26 targets that need a concept — `G35`–`G60`

| theme | groups | recommend | changes |
|---|---|---|---|
| **Community involvement** | `G53` organization · `G56` role · `G60` yearsActive | define as **one activity occurrence** (organization, role, period), per the work order | suggestions acceptable |
| | `G45` meetingDay · `G46` meetingLocation · `G47` memberCount · `G58` successor | **retire from extraction**; logistics, not a life. If the narrator tells it as a story, it is kept as a story | prompt −346 chars together with `G35` and `G44` |
| **Great-grandparent service** | `G49` branch · `G50` unit · `G51` event | define as `person.service.*` about **that person**, with source and uncertainty kept, per the work order. Usually second-hand; *"in the Navy, I think"* must survive as that | suggestions acceptable |
| **Heritage** | `G36` ancestry · `G41` ethnicBackground (+ form `Q11`) | one concept, `person.heritage`, **self-described free text**, never a picklist | suggestions acceptable |
| **Health** | `G38` `G39` `G42` `G43` `G48` | **→ D3** | |
| **Derived or bucket** | `G35` ageAtMarriage | **retire**; derive it from birth date and union date instead. Storing it gives a third value that can disagree | prompt shrinks |
| | `G44` marriageNotes | **retire**; a notes bucket (D1d) | prompt shrinks |
| **Story, not field** | `G52` nameStory | define as a **story** about the name, with a person reference | suggestions acceptable |
| **Education** | `G59` training | define as an education entry | suggestions acceptable |
| **Structure** | `G57` side (maternal/paternal) | a **relationship qualifier**, not a person attribute | suggestions acceptable |
| | `G54` priorPartners.period | `relationship.period` (depends on D2) | |
| | `G37` grandparents.childCount | `person.reported_count.children`: a **stated** count, and zero is an answer | suggestions acceptable |
| **Reading** | `G55` readingAbility | define as **volunteered, attributed biography** ("I taught myself to read at nine"), **never** an inferred literacy or cognitive assessment, per the work order. Lori must not raise it | suggestions acceptable, as a story |
| **Routine** | `G40` dailyRoutine | define as **Life Today description**, not a clinical inference, per the work order | suggestions acceptable |

### D1f · 41 form fields extraction can never fill — `Q01`–`Q12`

The question here is **which of these the extractor should start looking for**.
Each one costs roughly 62 characters on every call.

| group | recommend | why |
|---|---|---|
| `Q02` relatives' names and vitals (8) | make **4** extractable: `siblings.middleName`, `siblings.maidenName`, `children.middleName`, `grandparents.middleName` | the other 4 already have extractor paths under another spelling (D1a) |
| `Q10` life status (2) | make **extractable**, as the three-way `lifeStatus` | the death defect from the form side |
| `Q01` stories in field clothing (9) · `Q09` legacy messages (2) · `Q03` marriage detail (4) | **don't** make them extractable; **route them to the story model** | they are the narrator's words; the story lane captures them verbatim |
| `Q05` health (3) | operator-only | follows D3 |
| `Q04` technology and culture (4) · `Q06` pets (3) · `Q08` education (2) | operator-only for now | low narrative value, and they would cost prompt on every turn |
| `Q07` derived (2) | **derive `zodiacSign` from the birth date, never store it**; `timeOfBirth` operator-only | `zodiacSign` is the field that went stale on Janice's record |
| `Q11` heritage · `Q12` notes | `person.heritage` (D1e) · retire | |

**Net effect of D1 as recommended** (measured, apart from the added labels,
which are estimated at the 62-character average):

- **−685 characters (~−170 tokens) per extraction call.**
- Extraction targets go from 146 to 137.
- **Zero** undeliverable targets remain, since every path is defined,
  aliased or retired.
- **Coverage goes up while the prompt gets smaller.**

---

## D2 — Grandchildren and prior partners

Extraction already looks for them (`G20`, `G21`, `G29`, `G30`, `G18`, `G54`),
but **no form section exists** for either.

- **(a) Recommended:** ordinary **person records** connected by explicit,
  time-aware relationships. This is the work order's direction.
  - A prior partner does not imply a marriage.
  - A grandchild can be recorded without every person in between being known.
- (b) Flat sub-lists under the narrator. This is the status quo, and it is
  why they have nowhere to go.

**Changes:** adds two people-bearing sections in Batch C. Their extraction
paths get destinations. Nothing new is noticed, since they are already
extracted.

## D3 — Health: reflections against clinical facts

The work order requires this to be a **deliberate choice**. Extraction paths
may not be expanded or retired by default.

- **(a) Recommended:**
  - `cognitiveChange`, `lifestyleChange` and `milestone` (`G38`, `G42`,
    `G48`) become **narrator reflections**, stored as stories in the
    narrator's own words.
  - `majorCondition` and `currentMedications` (`G43`, `G39`) are **retired
    from extraction**.
  - Form health fields (`Q05`) are operator-only.
- (b) Keep structured clinical fields extractable, stored as sensitive
  assertions visible to operators only.
- (c) Retire all health extraction; health becomes operator-entered only.

**Changes:** this **does change what the extractor notices**. Under (a), a
medication or diagnosis mentioned in conversation is no longer pulled into a
structured field; it stays in the transcript. The prompt shrinks by 124
characters.

**Why (a).** The core user may have cognitive decline. A medication list
extracted from conversation and stored beside a life story is a different
promise from the one this product makes. **If you want (b), choose it
deliberately.**

## D4 — `trip_bio_suggestions`, the dead stub

**Verified dead:**

- Its only writer hardcodes `field_key="travel.trip"`
  (`trip_timeline_bridge.py:200-207`).
- That key is blocked by a foreign key to `bio_fields` (`0011:103`), and no
  `travel.*` key is seeded anywhere.
- Its content is never read.
- It has **0 rows** in the working root.

Options:

- **(a) Recommended:** **remove the writer call only.** The table stays
  empty and is declared historical in its `DbLane`. This follows the Kawa
  precedent: *zero reachable product path*, not zero occurrences.
- (b) Full removal: a new migration drops the table, and 4 migrations
  (read-only), 4 tests, 3 scripts and 4 services change.
- (c) Wire it through review as a real suggestion source.

**Changes:** nothing a user sees. (a) touches one call site and one inventory
note.

## D5 — Where a living narrator's life span ends

**What ships:** the span has **no end**. `later_years` is open
(`lv-eras.js:95`); there is no `date.today()` in `chronology_accordion.py`;
and `dateOfDeath` truncates nothing (`:564`, `:591`, `:604`).

- **(a) Recommended:**
  - Keep a living narrator's span **open**, as shipped.
  - **Add** truncation at a **known** death date.
  - A deceased narrator with **no** date is marked as deceased, not truncated
    and not extended.
- (b) Give a living narrator a computed present-day end at render.

**Changes:** under (a), nothing changes for living narrators, and deceased
narrators with a known date stop running on into later eras. Under (b), era
rendering changes for everyone.

## D6 — The identity-overwrite writer (`_overwriteBbPersonal`)

**Corrected risk.** It is **dormant by default**. It runs only inside the
legacy questionnaire-first walk, and only when
`localStorage.lv_qf_live_ownership === "1"` (`session-loop.js:123-132`).
When it does run, it **overwrites** the narrator's name, date of birth and
birthplace from a chat-text heuristic (`:280-334`), with no confirmation.

- **(a) Recommended:** route it through the review queue as a `needs_verify`
  candidate, the same "propose" operation `questionnaire.py:154-167` already
  assigns to Lori's other writers under WO-03B. Re-enabling the legacy walk
  can then never bring back silent overwrites.
- (b) Delete the legacy walk entirely. Larger, and WO-QF-RETIRE Phase 4 kept
  it for a possible structured-intake mode.
- (c) Leave it dormant behind the flag.

**Changes:** **no live behaviour change by default**, because the path is off.
Under (a), if the flag is ever set, a restated identity becomes an item for
the operator to review rather than an overwrite.

---

## Later decisions — written now so they don't surprise anyone

**D7 · before Batch B — typed occurrences.**
- **(a) Recommended:** canonical records.
- (b) A derived index over the existing domain records.

WO-LIFE-RECORD-01 §12 records the trade-off. A derived index is less
disruptive, but it leaves the multiple representations in place, and those
multiple representations are the measured cause of the drift.

**D8 · before Batch B — storage layout.**
- **(a) Recommended:** keep **shared SQLite** for this work, as Batch B
  already assumes.

One database per narrator stays open. Measured cost: 30 direct connect sites
and 79 inventory lanes to change. It also has an unresolved question about
unassigned media (WO §2B). Choosing (a) doesn't close the question; it
only avoids blocking on it.

**D9 · before Batch B — the relationship graph's future.** Nothing on the
server reads the graph (checkpoint §3.1), and its PUT is still an
unconditional full replacement.
- **(a) Recommended:** in Batch B, make the graph a **projection rebuilt from
  the life record**, and add an expected-revision check to its PUT until then.
- (b) Keep it as an independent store and add version checks only.

**D10 · before Batch C — removal and breadth.**
- **Recommended:** an explicit per-entry **Remove** control with a
  confirmation step, recoverable through the existing questionnaire archive.
- The PUT route gains the `removals` field that `merge_whole_document`
  already accepts.
- The eleven-topic form is built **field by field**, not as headings.

**Recorded, not blocking:**
- Package encryption.
- `narrator_package_jobs` and `narrator_package_export_jobs` retaining ids
  of erased narrators without declaring it (Batch E).

---

## Reply form

Copy, edit, and send back:

```
D1a approve      D1b approve      D1c approve      D1d approve
D1e approve      D1f approve
D2  (a)          D3  (a)          D4  (a)          D5  (a)          D6  (a)
D7  (a)          D8  (a)          D9  (a)          D10 approve
changes: none
```

Replacing `(a)` with `(b)` or `(c)` changes that decision. Anything written
after `changes:` overrides the row it names. For example,
`D1e: keep G45/G46 as operator fields` or `D3: (b), clinical visible to Chris only`.

**What happens after you reply:** Batch A starts with the catalog file and its
loader, and fail-closed checks against the real producers. It stops at its
gate for your review, not after each change.
