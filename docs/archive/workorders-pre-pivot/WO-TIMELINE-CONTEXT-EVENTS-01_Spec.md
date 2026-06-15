# WO-TIMELINE-CONTEXT-EVENTS-01 — Operator-Curated Cohort Memory Scaffolding

**Status:** ACTIVE (parallel cleanup lane, parent-session-non-blocking)
**Pair WO:** WO-TIMELINE-RENDER-01 (the timeline renderer that consumes this table)
**Author:** Chris + Claude (2026-05-05)
**Renamed from WO-WORLD-EVENTS-TABLE-01 (2026-05-05):** the table is `timeline_context_events`, NOT `world_events`. The breakthrough: this is not generic Wikipedia history. It's locally meaningful memory scaffolding for a specific cohort in a specific region living a specific kind of life.
**Flag:** none — table is data only; consumption is gated by `HORNELORE_TIMELINE_RENDER_V1`

---

## Core breakthrough (locked)

**A timeline does not need to know "World War II happened." It needs to know what mattered to THIS cohort in THIS region for THIS kind of life.**

For a Germans-from-Russia narrator born 1939 in North Dakota, the context layer is not Apollo + JFK + WWII. It is:

```
prairie droughts          church communities
grain elevators           wartime rationing
farm auctions             German-Russian migration memory
county fairs              local floods
regional industry         closed rail lines
```

For a South Asian Central Valley immigrant family, the context layer is entirely different — Punjabi farming expansion, Stockton gurdwara, regional ag history, Bhagat Singh Thind era citizenship rulings.

The table holds **historical context packs**, filtered per narrator by region/heritage/cohort. That's why the schema is `timeline_context_events` plural-tagged-and-filtered, not a single global history table.

---

## North Star (locked)

**Lori does not write to this table.** Ever. Not via inference during interview turns. Not via an operator-approval queue. Not via any path. The events table is operator-curated from researched sources only.

**Voice library is context filtering, not identity inference.** Heritage tags like `germans_from_russia` get used by the OPERATOR at curation time (when tagging an event) and by the RENDERER at filter time (when picking the narrator's slice). They are NOT used by Lori at runtime to classify a narrator. Per CLAUDE.md design principle: *Lori is a pattern-aware listener, not an identity-detector.* The narrator's heritage_tags come from intake (operator records what the narrator tells them), not from speech-pattern inference.

**Local-sourced first.** Generic published events are the LAST resort, not the first. A grandmother remembers the year the Stanley grain elevator burned down better than she remembers Apollo 11. Real value comes from operators who lived in or researched a region carrying that knowledge forward — county histories, archived newspapers, historical-society pamphlets, oral-history corpora collected separately, family archives.

**Stored, not retrieved.** Render-time is pure DB read. No LLM call to generate events. No web fetch at render time.

**No laundering.** *No narrator memory may become regional or cohort context without independent sourcing.* Janice's grain elevator anecdote stays Janice's personal-truth pin in *her* timeline. It enters the `timeline_context_events` table only if independently sourceable (newspaper archive, town history book, named oral-history interview with non-Janice source).

---

## Why this changes what Lori is for (load-bearing)

This table is not just data hygiene. It changes Lori's job. Today Lori has to invent context from scratch — remember, contextualize, structure, summarize, relate historically — from a prompt and partial memory. That is unstable. With structured context, Lori instead receives:

```
structured memory          era structure
photos                     regional context
cohort context             historical scaffolding
```

already prepared mechanically. Lori becomes free to do what she should actually do — **listen, reflect, ask, connect, follow** — instead of pretending to be a historian + archivist + memory engine all at once.

### Concrete before/after

**Without context schema** — narrator says: *"We lost the farm after the drought."* Lori has to guess what drought, where, when, whether it mattered regionally. Often she says something generic.

**With context schema** — same utterance, but the renderer (and a future composer hook) knows the narrator's region/heritage tags overlap a `1954–1959 Great Plains drought` event in the table. Lori can respond naturally:

> *"That drought period was hard on a lot of prairie families. What do you remember changing at home during those years?"*

That is dramatically better — and it doesn't require Lori to know history. It requires the SYSTEM to know history.

### Five concrete improvements

1. **Better follow-up questions.** Instead of generic *"Tell me more,"* Lori can ask *"Did your family stay on the farm through those drought years?"* because the context exists mechanically.
2. **Less hallucination.** Lori stops inventing fake history, wrong timelines, generic context. The grounded context is in the DB, not in her head.
3. **Better emotional resonance.** Older adults connect memory through shared hardship, local events, cultural patterns, historical periods. The schema gives Lori awareness of those anchors without inferring identity from speech.
4. **Better memory recall.** Historical scaffolding triggers autobiographical recall. *"North Dakota drought years"* may unlock crops, weather, neighbors, schools, family stress, migration memories — that helps the interview itself.
5. **Less prompt pressure.** Instead of bloating prompts with *"remember they are Germans-from-Russia prairie people..."* the system provides structured context. Smaller prompts, less drift, less overfitting, more consistency across sessions.

### The architecture (locked)

```
DB/schema     = memory + context
Timeline      = visual scaffold
Lori          = human-feeling conversational layer
```

The timeline/context system does not replace Lori. **It supports Lori** — by removing the burdens that destabilize her (memory, structure, history, contextualization) so she can do the thing she's actually good at.

This moves Lori from *generic AI interviewer* toward *historically situated conversational companion* without turning her into a therapist, a historian, an identity classifier, or a hallucinating memoir writer.

### Critical rule (paired with principle 7)

The system may know `heritage_tags=["germans_from_russia"]` because the operator seeded it from intake or the narrator explicitly confirmed it. But **Lori must never say *"You sound Germans-from-Russia."*** The tags are contextual, structural, filtering metadata — NOT labels Lori imposes on people. Identity inference at runtime is forbidden regardless of how rich the context becomes.

### Future composer hook (out of v1 scope)

The pair WO (WO-TIMELINE-RENDER-01) covers the visible render. A separate future WO covers the *prompt-side composer hook* — surfacing relevant context events to Lori's system prompt during turns that touch their year/era. That work is parked behind:
- BINDING-01 second iteration (extractor lane priority)
- Parent-session readiness (Lane 2 priority)
- This pair (timeline_context_events table needs to ship and accumulate before composer surfacing has anything to surface)

When that future WO opens, the rule will be: composer reads the same query the renderer does (deterministic), formats matching events as a context block, drops it into the system prompt for that turn only. No generation. No retrieval at runtime. Just deterministic surfacing of already-stored context.

---

## Operator role (load-bearing)

The operator's role is ongoing curatorial work, not one-time seed-and-walk-away. The operator can:

- **add** new events as they research a cohort
- **edit** existing events to refine title/summary/citation
- **seed** region/cohort packs from researched sources
- **curate** a pack over multiple sessions, improving citations as documentation surfaces
- **extend** the tag vocabulary when a new cohort doesn't fit existing tags

Each new narrator cohort potentially seeds 30–50 new events. Each existing pack improves over time as research deepens. The table grows with use; per-narrator coverage improves as more cohorts get curated.

---

## Schema (locked v1)

```sql
CREATE TABLE timeline_context_events (
    id              TEXT PRIMARY KEY,                  -- stable slug, e.g. "nd_1957_prairie_drought"

    title           TEXT NOT NULL,                     -- short, render-friendly: "Prairie drought"
    summary         TEXT NOT NULL,                     -- 1-3 sentences: what happened and why it matters for this cohort

    year_start      INTEGER,                           -- single-year events: year_start = year_end
    year_end        INTEGER,

    scope           TEXT NOT NULL CHECK (scope IN (
                        'global',
                        'national',
                        'regional',
                        'local',
                        'cultural'
                    )),

    region_tags     TEXT NOT NULL,                     -- JSON array: ["nd", "great_plains", "prairie"]
    heritage_tags   TEXT NOT NULL,                     -- JSON array: ["germans_from_russia", "rural_us"]

    source_kind     TEXT NOT NULL CHECK (source_kind IN (
                        'local_oral_history',
                        'archived_newspaper',
                        'historical_society',
                        'academic',
                        'reference_work',
                        'web_resource',
                        'family_archive',
                        'operator_research_note'
                    )),
    source_citation TEXT NOT NULL,                     -- real citation; "general knowledge" fails the validator

    narrator_visible INTEGER NOT NULL DEFAULT 1,       -- boolean; operator_research_note rows ship as 0 by default

    created_by      TEXT NOT NULL,                     -- operator user_id
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by     TEXT,                              -- nullable; set when an operator promotes an operator_research_note
    reviewed_at     TEXT,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TEXT,                              -- soft-delete; preserves audit trail when wrong-fact corrections happen

    notes           TEXT                               -- operator notes: "see also nd_1958_continued_drought"
);

CREATE INDEX idx_tce_year_start  ON timeline_context_events(year_start);
CREATE INDEX idx_tce_year_end    ON timeline_context_events(year_end);
CREATE INDEX idx_tce_scope       ON timeline_context_events(scope);
CREATE INDEX idx_tce_deleted     ON timeline_context_events(deleted_at);
CREATE INDEX idx_tce_visible     ON timeline_context_events(narrator_visible, deleted_at);
```

**Why these columns and not others:**

- `year_start` + `year_end` (vs separate `year`/`year_low`/`year_high`): cleaner, no redundancy. Single-year events set `year_start = year_end`. Multi-year ranges (droughts, eras, migration waves) use the pair directly.
- `summary` (vs `description`): aligns with rendering use ("show me a one-paragraph summary of this event for the timeline").
- `narrator_visible` boolean (vs `pack_visibility` enum): only two values exist in v1 (narrator-visible or operator-only); a boolean is simpler.
- No `month`/`day`: regional/cohort events are year-grained. If a specific newspaper-archive event has month/day precision worth surfacing, it can ride in the `summary` text ("On August 14, 1957, the Stanley Sun reported...").
- No `confidence` column: `source_kind` already carries that information (`academic` / `historical_society` are higher-rigor than `local_oral_history` / `web_resource`). Render-time can map source_kind to a visual confidence indicator if needed.
- Audit columns (`created_at` / `updated_at` / `deleted_at`) match the photos-table pattern from migration 0001 — cheap and load-bearing for any future correction workflow.

---

## source_kind enum (8 values, locked)

| Value | Use for |
|---|---|
| `local_oral_history` | A real person's recorded recollection. Acceptable for private/family packs as a primary source; reusable/shared regional packs require independent corroboration OR explicit oral-history provenance with named person + date recorded. |
| `archived_newspaper` | Specific newspaper article with date + publication. Single-best-source class. |
| `historical_society` | County/state historical society publications, pamphlets, exhibits. |
| `academic` | Peer-reviewed paper, dissertation, scholarly book. |
| `reference_work` | Encyclopedia, gazetteer, atlas, almanac. |
| `web_resource` | Specific URL with access date. Lowest-rigor of the published-source kinds — prefer one of the above when available. |
| `family_archive` | Family-held source material: letters, photos, journals, funeral cards, church programs, family Bibles, recorded oral histories. Acceptable for private/family packs; reusable packs need stronger provenance. Citations name the artifact specifically: `"Horne family Bible, marriage entry on flyleaf, dated 1947"` not `"family records"`. |
| `operator_research_note` | Temporary/staging research notes the operator hasn't yet finished verifying. **NOT narrator-visible by default** (`narrator_visible = 0`). Must be reviewed and promoted to a published-source kind before inclusion in reusable packs. |

### local_oral_history rule (locked)

`local_oral_history` is acceptable for:
- private/family packs (Hornelore family deployment, single-narrator packs)
- provisional regional context (operator carrying knowledge forward from someone they spoke with)

Reusable/shared regional packs (the kind that get checked into Lorevox as community resources) require:
- independent corroboration via another `source_kind` (newspaper, historical society, academic), **OR**
- explicit oral-history provenance: named person + date recorded + relationship to the event

**Acceptable citation:** `"Interview with Kent Horne, recorded 2026-04-15"`
**Acceptable citation:** `"Stanley Sun newspaper archive 1957-08-14"`
**Not acceptable:** `"general family knowledge"`, `"common knowledge"`, `"my grandmother said"` (without name + date), `"i remember"`, `"wikipedia"` without article + access date

The validator (Phase B) enforces this — packs flagged via a `pack_kind: shared_regional` JSON-file annotation get the stricter check; private/family packs (`pack_kind: private_family`) accept `local_oral_history` and `family_archive` as standalone primary sources.

### operator_research_note rule

`operator_research_note` exists for the workflow case where an operator is mid-research on an event but hasn't yet found a citable published source. The note ships into the table with `narrator_visible = 0` so the narrator doesn't see unverified context. The operator's review pass either promotes the row to a stronger `source_kind` (with corresponding citation update) or deletes it. Not promoted ≠ deleted automatically — operator-only notes can persist as long as needed.

---

## Tag taxonomy (extensible — no cohort gets force-mapped)

The locked v1 taxonomy below is a starting set. **No narrator cohort should be force-mapped into an existing tag** — when a new cohort doesn't fit any existing `heritage_tag`, the right move is to add a new tag, not to misclassify the cohort. New tags get added by appending to `data/timeline_context_events/tag_vocabulary.json`. Validator catches unknown tags but accepts new ones once they're in the vocabulary file. Voice Library is the v1 spine, not the ceiling.

`region_tags` align with US Census regions plus state abbreviations plus distinct cultural-geographic identifiers:

```
states:        al, ak, az, ..., ny, nd, ..., wy, dc
regions:       northeast, midwest, south, west, great_plains, pacific_northwest,
               new_england, southwest, deep_south, appalachia, rust_belt,
               california_central_valley, texas_borderlands, ...
non-US:        mexico, canada, germany_russia, ukraine_central, european_jewish,
               punjab, north_india, vietnam, philippines, mexico_central, ...
```

`heritage_tags` start from the seven voices in `docs/voice_models/VOICE_LIBRARY_v1.md` and extend as cohorts get curated:

```
v1 spine (from Voice Library):
  germans_from_russia
  adamic_urban_industrial
  african_american_georgia
  asian_american_california
  native_american_new_mexico
  hispano_tex_mex
  crypto_jewish_new_mexico

extensions (add as cohorts ship):
  south_asian_california
  punjabi_central_valley
  hispano_nm
  rural_us
  industrial_midwest
  mennonite
  catholic_polish_chicago
  filipino_american_navy
  ...
```

Plus orthogonal community/cohort tags as needed:

```
rural_us, urban_us, military_family, mennonite, catholic, jewish, evangelical,
wwii_home_front, vietnam_era, civil_rights_era, post_war_boom, depression_era,
dust_bowl_displaced, redlined_neighborhood, ...
```

**Tag discipline:** new tags get added by appending to `data/timeline_context_events/tag_vocabulary.json`. Validator (Phase B) enforces tag membership. Adding a tag is a tiny PR; using an unrecognized tag fails the validator.

---

## Renderer query pattern

```python
# Pseudocode for `_pull_context_events(narrator_lifetime_range, narrator_region_tags, narrator_heritage_tags)`
events = db.query("""
    SELECT * FROM timeline_context_events
    WHERE deleted_at IS NULL
      AND narrator_visible = 1
      AND year_start <= ? AND year_end >= ?
""", narrator_lifetime_end, narrator_lifetime_start)

filtered = [
    e for e in events
    if e.scope IN ('global', 'national')                                  # everyone sees these (subject to time-range)
    or any(rt in narrator_region_tags for rt in e.region_tags)            # regional/local match by region
    or any(ht in narrator_heritage_tags for ht in e.heritage_tags)        # cultural match by heritage
]
```

Operator-only view (toggleable in operator surface) includes `narrator_visible = 0` rows for review queue purposes.

---

## v1 Scope

**Schema + initial seed pack + read-side index for the renderer.** No operator UI surface in v1 (curators edit JSON files; validator catches schema errors). Operator UI for curation is a v2 successor WO if curation volume justifies it.

### Initial seed pack (Phase C of pair WO consumes this)

**Pack 1 — Janice / Germans-from-Russia / ND prairie** (~30-50 entries, `pack_kind: private_family`):

Mix of:
- Birth-cohort national/global events that landed for ND prairie families differently than for urban populations (WWII home-front rationing with agricultural-exemption details, Cold War prairie missile silos, 1950s drought)
- ND state events (statehood anniversaries, weather catastrophes, Garrison Dam 1956, oil booms)
- Bismarck/Mandan/Stanley local events (specific town fires, parish events, county fair years if locally documented, closed rail lines, grain elevator history)
- Germans-from-Russia migration history and 20th-century cohort experience (church communities, mother-tongue retention, school assimilation)

Example titles (Chris's set):

```
Stanley elevator fire (1953)
North Dakota drought years (1955-1959)
Garrison Dam completion (1956)
Closure of Stanley-Lostwood rail line (1968)
County fair revival in McLean County (1970s)
Mennonite Heritage Society of ND founded (1990)
Las Vegas NM flood (date TBD — separate pack for hispano_nm cohort)
Punjabi farming expansion in Central Valley (1960s-1980s, separate pack for south_asian_california cohort)
```

**Source rule:** every entry cites a real source. v1 acceptable sources include Chris's local knowledge cited as `local_oral_history` with `"Interview with [named family member], recorded 2026"` for entries he carries from family — these get a follow-up review pass when published documentation surfaces.

### What's NOT in v1

- No operator curation UI surface (JSON-file editing + validator only)
- No bulk import from external corpora (genealogy databases, historical-society APIs) — defer to v2 if curation volume demands
- No multi-region event packs that compose automatically (operators curate one pack at a time; validator dedupes by `id`)
- No language-localized titles/summaries — v1 ships English-only; localization is a future WO
- No event-to-photo binding ("this photo is *of* this event") — photo provenance stays in the photos table
- No "narrator approved this event for their timeline" flag — events render for all narrators whose tags match; per-narrator hide/show is a v2 feature
- No Lori-side composer hook — surfacing context to system prompt is a separate future WO (see "Future composer hook" above)

---

## Implementation phases

### Phase A — schema + repository

1. New migration `server/code/db/migrations/0005_timeline_context_events.sql` per the schema above
2. New repository module `server/code/api/services/timeline_context_events_repository.py`:
   - `query_events_for_narrator(narrator_id, lifetime_range, region_tags, heritage_tags, *, include_operator_only=False) → list[ContextEvent]`
   - `add_event(event_data, *, created_by_user_id) → ContextEvent` (operator-only path; not exposed to chat_ws)
   - `update_event(event_id, patch, *, edited_by_user_id) → ContextEvent`
   - `soft_delete_event(event_id, *, deleted_by_user_id) → None`
   - `promote_research_note(event_id, *, new_source_kind, new_citation, reviewed_by) → ContextEvent`
3. Build-gate isolation test (`tests/test_timeline_context_events_isolation.py`) following the LAW 3 INFRASTRUCTURE pattern. Forbidden imports: `api.routers.extract`, `api.prompt_composer`, `api.memory_echo`, `api.routers.llm_*`, `api.routers.chat_ws`, `api.services.story_*`, `api.services.lori_*`, `api.services.utterance_frame`. Allowlist: `api.db`, `api.services.timeline_render` (pair WO).
4. Unit tests covering: schema validation, tag-vocabulary enforcement, narrator filtering by region/heritage tag overlap, year-range matching, soft-delete behavior, `narrator_visible=0` exclusion from default query, operator_research_note promotion path

### Phase B — JSON validator + seed loader

1. New validator `scripts/validate_timeline_context_events.py` — reads JSON files in `data/timeline_context_events/`, validates each entry against schema + tag vocabulary, reports errors with file path + line number. Pre-commit hook hookable.
2. Tag vocabulary file `data/timeline_context_events/tag_vocabulary.json` shipping with the locked v1 taxonomy
3. Seed loader `scripts/seed_timeline_context_events.py` — reads `data/timeline_context_events/*.json`, calls `add_event()` for each entry, idempotent (re-running is a no-op if `id` already exists)
4. Pack-kind annotation: each JSON file carries a top-level `pack_kind: "private_family" | "shared_regional"` field; validator applies stricter `local_oral_history` rules to `shared_regional` packs
5. Initial seed pack `data/timeline_context_events/janice_germans_from_russia_nd_prairie.json` (`pack_kind: private_family` for v1) — Chris's contribution, ~30-50 entries

### Phase C — operator surface (deferred until volume demands)

Future work:
- Bug Panel curation surface (read-only browse + filter by tag/year/source)
- Inline edit form with citation requirement
- Bulk import from CSV / external corpora
- Per-narrator "hide this event from my timeline" preferences
- Pack promotion UI (private_family → shared_regional) with stricter validation

v1 ships without any of these. Operators edit JSON files and re-run the seed loader.

---

## Acceptance gates

**Phase A passes when:**

- Migration runs clean against an empty DB and against a populated DB
- Repository functions return correct shapes
- Tag-vocabulary enforcement rejects unknown tags at `add_event()` time
- Narrator filtering correctly excludes events whose tags don't overlap the narrator's tags AND aren't in scope `global` or `national`
- Year range matching: an event with `year_start=1955, year_end=1959` matches narrators whose lifetime range overlaps that interval
- Soft-delete excluded from `query_events_for_narrator` results
- `narrator_visible=0` excluded from default query; included when `include_operator_only=True`
- `promote_research_note` correctly transitions a row from `operator_research_note` source_kind to a published-source kind with `reviewed_by` + `reviewed_at` set
- Build-gate isolation test passes (negative-test verified)

**Phase B passes when:**

- Validator catches: missing required fields, invalid `scope` value, unknown tag in `region_tags`/`heritage_tags`, missing `source_citation`, missing `pack_kind`, malformed year ranges, invalid citation pattern (`general knowledge` / `common knowledge` etc.)
- Validator passes the locked seed pack (Janice / Germans-from-Russia / ND prairie)
- Validator applies stricter local_oral_history rule to `shared_regional` packs only
- Seed loader is idempotent (running twice produces same row count, no errors)
- Validator runs in <1s on a 50-entry pack

**Phase C** has no v1 acceptance gates (deferred).

---

## Risks & rollback

**Risk 1: tag vocabulary churn.** As more cohorts get curated, `heritage_tags` will grow. Mitigation: treat `tag_vocabulary.json` as locked-but-extensible. Adding a tag = adding a row + reviewer signoff. Removing/renaming a tag = a migration that updates all downstream entries (rare, painful, document carefully).

**Risk 2: source citation rigor erosion.** Easy to ship an entry with `source_citation: "general knowledge"` and lose the discipline. Mitigation: validator rejects citations matching common low-rigor patterns. Force operators to either cite real or use `source_kind: 'local_oral_history'` with a person name + date.

**Risk 3: operator burden gates new cohorts.** A new heritage cohort can't ship until someone curates a pack. For Janice's cohort, Chris carries that knowledge. For future narrators outside operator expertise, either someone researches OR the timeline shows fewer events for that narrator. The latter is fine for v1 — better empty than wrong. Document the expectation explicitly.

**Risk 4: narrator-anecdote contamination (no-laundering rule).** An operator curating Janice's pack might be tempted to add "Stanley grain elevator burned 1953" because Janice mentioned it during interview. **Rule: that entry only ships if independently sourceable** (newspaper archive, town history book, named oral-history interview with non-Janice source). If the only source is Janice's interview, it stays as Janice's personal-truth pin in *her* timeline only and does NOT enter `timeline_context_events`. The validator can't enforce this rule by code (it has no way to know what an operator heard from a narrator), so it lives in the curator's onboarding doc as a behavioral discipline check. Reusable/shared regional packs (`pack_kind: shared_regional`) get the stricter validator check that rejects `local_oral_history` as a sole primary source — they require independent corroboration OR named oral-history provenance.

**Risk 5: heritage_tag misuse as identity inference.** Operators or future agents might be tempted to use `heritage_tags` as a Lori-side classification signal ("this narrator sounds Mennonite, tag them so"). **Rule: heritage_tags are operator-recorded at intake, never inferred at runtime.** Lori is a pattern-aware listener, not an identity-detector (per CLAUDE.md). Even when the future composer hook surfaces context events to the system prompt, Lori's job is to *use* the context — not to *speak the tag back at the narrator* ("you sound Germans-from-Russia"). Document this rule in the curator's onboarding doc so future contributors don't drift.

**Rollback:** drop migration `0005_timeline_context_events.sql`. Empty table = renderer returns zero events. Zero impact on interview / extractor / Lori-behavior / story-preservation lanes.

---

## Files (planned)

**New:**

- `server/code/db/migrations/0005_timeline_context_events.sql`
- `server/code/api/services/timeline_context_events_repository.py`
- `tests/test_timeline_context_events_repository.py`
- `tests/test_timeline_context_events_isolation.py`
- `scripts/validate_timeline_context_events.py`
- `scripts/seed_timeline_context_events.py`
- `data/timeline_context_events/tag_vocabulary.json`
- `data/timeline_context_events/janice_germans_from_russia_nd_prairie.json` (initial seed pack, `pack_kind: private_family`)
- `docs/operator/TIMELINE_CONTEXT_CURATION_GUIDE.md` (one-page how-to-curate document)

**Modified:**

- `server/code/api/services/timeline_render.py` (pair WO — `_pull_context_events()` reads from this table)
- `MASTER_WORK_ORDER_CHECKLIST.md` (add lane row)

**Zero touch:**

- Extract router
- Prompt composer (until the future composer-hook WO opens — then prompt_composer gains a deterministic context-block surfacing function)
- Lori behavior services
- Memory echo composer
- Chat WebSocket router
- Photo intake / archive
- Story trigger / preservation
- Utterance frame service

---

## Sequencing within the lane

1. **Sprint 1:** Phase A schema + repository + isolation test + unit tests. ~half a session.
2. **Sprint 2:** Phase B validator + seed loader + tag vocabulary + Janice initial pack. ~one session (the pack curation is the bulk).
3. **Sprint 3+:** new region/heritage packs ship as Chris (or future operators) curate them. Each new pack is ~30-50 entries; budget 30-60 min per pack of operator time at first interview.
4. **Future:** composer-hook WO surfaces context events to Lori's system prompt. Parked behind BINDING-01 second iteration + parent-session readiness + this pair shipping with a populated table.

Phase C operator UI is deferred until curation volume justifies it. v1 ships with JSON-file editing.

---

## Companion: TIMELINE_CONTEXT_CURATION_GUIDE.md

A short operator document that says (paraphrased):

> Curating a context pack is research work, not interview-extraction work. Pull from county histories, archived newspapers, historical-society pamphlets, oral-history corpora, academic sources, family archives. Cite every entry. If you only know an event because a narrator told you about it during interview, do NOT add it to a `shared_regional` pack — that entry stays as the narrator's personal-truth pin in their own timeline only. Private/family packs (Hornelore family deployment) accept `local_oral_history` and `family_archive` as standalone primary sources because the audience is the family itself.
>
> A good pack is local. Generic US history events (moon landing, JFK assassination, 9/11) are scoped `global` or `national` and apply to most narrators automatically. The pack's value is the local layer — town fires, regional droughts, parish events, factory closures, county fair years, migration waves, regional industry shifts.
>
> Source rigor matters. "General knowledge" is not a citation. "ND State Historical Society pamphlet 2018" is. "Stanley Sun newspaper archive, 1957-08-14" is. "Interview with Kent Horne, recorded 2026" is, with `source_kind: 'local_oral_history'` and the person's name + date.
>
> Heritage tags are recorded by the operator at narrator intake — never inferred from speech patterns. Lori is a pattern-aware listener, not an identity-detector. The same rule applies during curation: tag events by the cohorts they actually mattered to, but never let those tags become Lori-side runtime classification. Even when a future composer hook surfaces context events into Lori's prompt, Lori's job is to USE the context warmly — never to speak the tag back at the narrator.

Operator onboards by reading this guide before their first curation pass.

---

## Locked principles (do not relitigate)

1. **Stored, not retrieved.** No LLM call at render time. No web fetch at render time. The table holds it.
2. **Operator-curated only.** Lori never writes here. Not even via approval queues. Period.
3. **Local-sourced first.** Generic published events are the last resort, not the first.
4. **Citation discipline.** Every row has a real source. No row ships without one. "General knowledge" / "common knowledge" / "i remember" / "wikipedia" without article + access date all fail the validator.
5. **No laundering.** *No narrator memory may become regional or cohort context without independent sourcing.* Narrator anecdotes stay personal-truth pins on that narrator's timeline only.
6. **Heritage_tags are extensible — no cohort gets force-mapped.** When a new narrator cohort doesn't fit any existing tag, add a new tag rather than misclassify. The Voice Library taxonomy is the v1 spine, not the ceiling.
7. **Voice library is context filtering, not identity inference.** Heritage tags are operator-recorded at narrator intake and used by the renderer for filtering. They are NEVER used by Lori at runtime to classify a narrator. *Lori is a pattern-aware listener, not an identity-detector.* (Per CLAUDE.md design principle.)
8. **The table holds historical context packs, not generic chronology.** The value is locally meaningful memory scaffolding for THIS cohort in THIS region for THIS kind of life. Generic Wikipedia events are a fallback layer, not the primary content.
9. **The table supports Lori — it does not replace her.** Structured context removes the burdens that destabilize Lori (memory, structure, history) so she can do what she's actually good at (listen, reflect, ask, connect, follow). The architecture: DB/schema = memory + context; Timeline = visual scaffold; Lori = human-feeling conversational layer.

---

## Changelog

- 2026-05-05 (initial): Spec authored alongside WO-TIMELINE-RENDER-01 after the timeline architectural conversation. Operator-only curation rule locked. Local-sourced rule locked. Heritage tag taxonomy aligned with `docs/voice_models/VOICE_LIBRARY_v1.md` seven-voice corpus.
- 2026-05-05 (rename + reframe): Renamed from `WO-WORLD-EVENTS-TABLE-01` to `WO-TIMELINE-CONTEXT-EVENTS-01` after Chris's "oldest person question was the missing clue" framing. Table is `timeline_context_events`, NOT `world_events`. Schema simplified to Chris's shape (`year_start`/`year_end`, `summary`, `narrator_visible` boolean) with audit-trail hygiene retained. Added `family_archive` + `operator_research_note` to `source_kind` enum. New principle 7 (voice library as context filtering, not identity inference). New principle 8 (historical context packs, not generic chronology). Examples updated to Chris's set (Stanley elevator fire / Punjabi farming Central Valley / Las Vegas NM flood). Operator role explicitly framed as ongoing curatorial work (add/edit/seed/curate/extend), not one-time seed.
- 2026-05-05 (Lori-support reframe): New "Why this changes what Lori is for" section captures Chris's framing that the context schema is not just data hygiene — it changes Lori's job by removing the burdens that destabilize her (memory, structure, history). Five concrete improvements documented (better follow-up questions, less hallucination, better emotional resonance, better memory recall, less prompt pressure). New principle 9 (the table supports Lori — does not replace her). Future composer-hook WO referenced as parked successor work.
