# Deep repository review, part 2 — 2026-09-22

The seven areas [part 1](REPO-REVIEW-2026-09-22.md) §10 declared unexamined:
`extract.py` beyond bio routing · `chat_ws` · memoir generation · trip
semantics · RAG · media archive · Life Map render.

Read-only. Nothing changed. **Includes a correction to part 1.**

---

## 0. Correction to part 1

Part 1 §2 said *"travel writes biography"* on the strength of
`trip_bio_suggestions` carrying a `field_key`. **That is wrong.**

The lane is a stub that cannot reach biography:

- Its only writer is `trip_timeline_bridge.py:200-211`, with a **hardcoded**
  `field_key="travel.trip"`.
- `travel.trip` is not a real key. `bio_schema.py:411` defines
  `travel_memories`; `extract.py:401-406` defines `travel.destination`,
  `.year`, `.purpose`, `.companions`, `.whatHappened`, `.notes`.
- `bio_facts.field_key` has an enforced FK to `bio_fields.field_key`
  (`0011_bio_fields_facts.sql:103`), so `travel.trip` **could not be
  promoted even if a path existed**.
- No production code ever SELECTs the table. `routers/trips.py` contains no
  "suggestion" string.

The code's own rule is correct and was always respected: *"promotion to bio
truth is a review decision, never automatic"*
(`trip_repository.py:924-926`); *"they do NOT write bio_facts directly"*
(`trip_timeline_bridge.py:20-24`).

**Corrected finding:** travel does not write biography. It has a dead stub
that should be either wired properly or deleted.

---

## 1. `extract.py` — a ninth vocabulary, already failing

**Extraction has its own field vocabulary and it has drifted from the
questionnaire.** `EXTRACTABLE_FIELDS` holds **141** dotted paths
(`extract.py:198+`), against the questionnaire's 118.
`services/questionnaire_schema.py:28-31` states it plainly: extraction
*"includes `residence.*`, `travel.*`, `military.*`, `faith.*` which the
questionnaire does not define, and omits ones it does."*

**This is already costing the product.** `services/suggestion_review.py:144-147`:
*"20 of 30 queued suggestions point at undefined destinations … because
`extract.py`'s EXTRACTABLE_FIELDS has drifted from the questionnaire."*
Two thirds of a review queue unusable — the exact failure mode the field
audit predicted, already realised.

**The questionnaire schema is JavaScript, read by Python.**
`questionnaire_schema.py:21-24` loads `ui/js/bio-builder-questionnaire.js`
`SECTIONS`, and asserts counts: `_EXPECT_SECTIONS=20`,
`_EXPECT_REPEATABLE=11`, `_EXPECT_FIELDS=118` (`:80-90`), raising
`SchemaUnavailable` on mismatch. **A questionnaire change fails closed until
those constants move in the same commit.** That is a genuinely good safety
property and a hard constraint on any redesign.

**Extraction writes no biography directly.** `extract.py:12-15`: *"The
backend NEVER writes to questionnaire or structuredBio directly."* It writes
`turn_extraction_ledger` / `_results`, and optionally `bio_facts` behind
`HORNELORE_BIO_FACT_ROUTING` (default **off**). It never writes
`family_truth_rows` — *"family truth remains operator-gated behind
POST /api/family-truth/\*"* (`turn_extraction.py:27-32`).

**Invariants worth keeping:**

- Guard ordering is the contract: *"materialize → group → publish
  repeatableGroup → THEN apply any authority-reducing guard… New guards go
  beside it, never earlier"* (`:9855-9897`).
- `personal.notes` is **retired** — *"that is where information goes to be
  unfindable"* (`:207-220`). Independent support for stories being
  first-class rather than a notes box.
- *"Extraction may interpret meaning; it may not decide which turn the
  meaning came from"* (`:10553-10555`).
- LAW 3 boundaries are AST-enforced by tests, not conventions.

## 2. `chat_ws` — the biography **is** droppable, and the rule for it is excellent

**Confirmed: sections are shed under budget.**
`services/prompt_budget.py:387` `fit_chat_messages_with_sections` exhausts
history first, then sheds optional sections by ascending `drop_order`,
re-measuring through the real chat template.

```
memory_context 5 · trip_context 15 · approved_stories 25
ui_context 30 · saved_biography 35 · saved_biography_detail 38
identity_facts, identity_grounding = TRIM_NEVER
```

So "the biography reached the loader" is genuinely not "the biography reached
the model". The delivered-prompt test is not pedantry.

**The governing rule is one of the best things in this codebase**
(`prompt_section_policy.py:342`): a section *"may be droppable because its
SOURCE is durable, never because the person could be made to say it again"*
— enforced at import by `_BANNED_RATIONALES`, and the registry fails the boot
if violated (`:334`).

**A conflict rule between stores already exists.**
`prompt_composer.py:1732`: *"The questionnaire WINS on conflict with
`profile_json`"*, and `load_facts` already emits `biography_conflicts`
(`:1772-1774`). My design proposed surfacing conflicts as if from scratch;
part of it is built.

**Biographical truth is written from a turn on exactly one path** —
`turn_mode == "correction"` → `projection_writer.apply_correction`
(`chat_ws:5146-5150`). Narrow and deliberate.

**Narrator switch flushes almost nothing** — only `clear_turns`
(`:8180, :8218-8222`). No archive, projection, profile-seed, ledger or
follow-up reset. And the fallback conversation id is `f"person_{id}"`, a
guess when the client omits `old_conv_id`.

Also: *"facts are not recollections"* (`prompt_composer.py:4530`) — Lori may
ask about a form-entered fact, may not narrate it as the narrator's memory.
And *"A suggestion is not a fact at any tier"* (`:1264`) — `pendingSuggestions`
are deliberately not merged into the seed.

## 3. Memoir — there is no memoir writer

**No chapter-generation service exists.** The only LLM call in the memoir
path is translation (`memoir_export.py:242`). The memoir is assembled from
three independent lanes:

1. **Client-authored sections** — operator prose, bucketed in the browser.
   *"Operator-authored prose is NOT evidence"* (`memoir_contract.py:36-39`).
2. **Captured stories** — `story_projection.memoir_projection`, **verbatim,
   no summarising**, grouped by era (`memoir_export.py:1083-1165`).
3. **Trip notes** — `trip_location_notes` where `include_in_memoir=1`.

**The questionnaire is not read by the memoir server path at all.** The only
questionnaire→memoir surface is a browser-side *structured preview* fallback
with hand-written per-field renderers (`hornelore1.0.html:8262-8285`),
mapping fields to eras by hand, not by date.

**Story promotion** is operator-only, via `PATCH /api/operator/story-candidates/{id}`
with optimistic `review_version`. States: `unreviewed · in_review · promoted ·
discarded · memoir_only`, where *"`memoir_only` is the operator saying: these
are the narrator's words and they belong in the memoir, but do not promote
what the extractor made of them"* (`db.py:8042-8044`).

**Verbatim, exactly once, never text-deduped** — *"two tellings are two
things the narrator said"* (`memoir_contract.py:130-134`).

## 4. Life Map and chronology — an era is never derived from a year

The seven-era spine lives in **`lv_eras.py:43-107`**, mirrored byte-for-byte
in `ui/js/lv-eras.js`. **Not a table.**

`chronology_accordion.build_scaffold_periods(birth_year, …)` is, in its own
words, *"THE ONLY CHRONOLOGY ENGINE"* (`:97`). **No date of birth → no
spine** (`life_spine/engine.py:86-87`).

**The questionnaire feeds chronology through a three-field gate only** —
`personal.dateOfBirth`, `placeOfBirth`, `dateOfDeath` — because *"expansion
beyond birth identity comes from PROMOTED TRUTH ONLY … so unreviewed answers
never leak into the sidebar as verified anchors"* (`:544-547`).

**So a marriage date or a job date sitting in the questionnaire does not
become a timeline entry today.** That is the single strongest argument for
the event model in my design — and also the reason it must not bypass the
promotion gate.

**Three placement rules a redesign must obey:**

- *"NEVER derives an era from a year. A year is not a position on the Life
  Map … inferring one is the guess this whole lane exists to stop"*
  (`story_projection.py:152-155`).
- *"Today is the current-life bucket, not a bin for things that failed to
  sort"* (`:36-39`).
- `placement_source ∈ {unknown, narrator_stated, operator_set, dob_derived}`,
  and *"Confidence is not provenance"* (`0046_story_review_authority.sql`).

`story_projection` is the **single placement authority** for five consumers;
memoir stopped reading the table directly because it produced a second answer
(`memoir_export.py:1094-1111`). `timeline_context_events` is **dead code**,
AST-enforced unreachable.

## 5. Trips — a parallel world with its own places and dates

Entity tree: `trips → trip_regions → trip_stops (self-nesting) →
trip_photo_links + trip_themes / trip_location_notes / trip_bio_suggestions
+ trip_story_links`, plus `trip_days` and `trip_turn_links`.

**Trips carry their own places and dates entirely separately**: free-text
`location_name`, lat/lon, `base_address`, `country_or_area`, `main_location`,
`places_visited_json`, and dates as **bare TEXT with no precision column** —
while `photos.date_precision` and `media_archive_items.date_precision` exist.
**Three incompatible date models coexist in the product today.**

`trip_turn_links` declares its own limit: *"THIS TABLE IS NOT TRUTH …
Placing a conversation on a trip day says where it happened. It does not
assert a biographical fact"* (`0039:97-102`).

## 6. Media archive — free text is the identity

Four tables plus `photos`, `photo_people`, and a third older polymorphic
`media_attachments`.

**Person attachment is dual and weak**: `media_archive_people.person_label
TEXT NOT NULL` is the real payload; `person_id` is **optional**. Identity is
free text with the FK as a bonus — the opposite of what a person model needs.

`media_archive_links` is an **untyped polymorphic pointer**
(`link_type` ∈ life_map_era / timeline_year / memoir_section /
family_tree_person / bio_builder_candidate / kawa_segment / source_note,
with *"link_target shape depends on link_type"*).

**Paths are absolute at rest** and normalised to DATA_DIR-relative on export
(`narrator_package.py:39, 824`), refusing a column that mixes bases. **Items
without `person_id` do not travel** — *"reported, never packaged"*.

Product rule worth preserving verbatim: *"Preserve first. Tag second.
Transcribe / OCR third. Extract candidates only after that. NEVER auto-promote
to truth."* (`0003_media_archive.sql:9-11`).

## 7. RAG — irrelevant

`rag_docs` / `rag_chunks`, a non-vector token scan. **Nothing indexes
narrator content.** The only production reader fetches two fixed
installation documents, `sys_oral_history_manifesto` and
`sys_golden_mock_standard` (`prompt_composer.py:4383-4390`). Classified
`CLASS_INSTALLATION`, 0 rows, travels=no. Not a factor.

## 8. What this means for the design

**New hard constraints:**

1. **`bio_facts.field_key` is an enforced FK to `bio_fields.field_key`.** Any
   rename needs a migration plus backfill — field names are not free to
   change.
2. **`questionnaire_schema.py` count invariants fail closed.** A redesign
   must move `_EXPECT_SECTIONS/_REPEATABLE/_FIELDS` in the same commit.
3. **`narrator_data_inventory.py` is a hand-maintained ownership registry.**
   Every new table needs a `DbLane` entry **or it silently fails to export or
   erase** — the portability and erasure guarantee depends on it.
4. **Never derive an era from a year**, never let unplaced fall into Today,
   and keep `placement_source` as recorded provenance.
5. **The three-field chronology gate exists on purpose.** Events with dates
   must not bypass promoted-truth review to reach the Life Map.
6. **String-literal maps must be re-edited together**: `EXTRACTABLE_FIELDS`,
   `_FIELD_ALIASES` (~200 entries), `_DIRECT_FIELD_PATH_MAP`,
   `PROTECTED_IDENTITY_FIELDS`, `FRAGILE_FIELD_*`, turnscope branch roots,
   negation-guard field sets, and the prompt rule blocks that name paths
   literally.

**Design changes now justified by evidence:**

- **A places entity absorbs five parallel free-text location models** —
  `trip_stops`, `trip_regions`, `trip_days`, `photos.location_label`,
  `media_archive_items.location_label`.
- **A people entity absorbs `media_archive_people.person_label` and
  `photo_people`**, replacing free-text identity with a reference.
- **An events entity replaces four untyped anchors** —
  `trip_stops.timeline_event_id` (no FK),
  `trips.meta_json.timeline_event_id`, `media_archive_links.link_target`,
  `media_attachments.entity_id`.
- **One date model with precision** replaces three.
- **The memoir has no writer.** Anything claiming a redesign "improves the
  memoir" must say which of the three lanes it touches.

**Design claims now withdrawn or weakened:**

- Travel does **not** write biography (§0).
- Conflict surfacing is **not** new — `biography_conflicts` and the
  questionnaire-wins rule exist.
- "Adding a questionnaire field automatically reaches Lori" is **false** at
  the prompt boundary: `saved_biography` has `drop_order 35` and is shed
  under budget.

## 9. Still unexamined

`lori_witness_mode` (2,500 lines) · the guard/authority registry ·
`import_repository` · photo intake and OCR · TTS · the eval harness ·
`chat_ws` safety branches in detail. This review does not clear them.
