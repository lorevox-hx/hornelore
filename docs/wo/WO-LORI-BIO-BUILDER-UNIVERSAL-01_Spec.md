# WO-LORI-BIO-BUILDER-UNIVERSAL-01

**Status:** SPEC — not yet started
**Severity:** HIGH (memoir deliverable depends on this; first WO that
materially differs from pre-pivot architecture)
**Narrator generality:** UNIVERSAL — authored under
`HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`. Resolves the "Bio Builder pre-load
from family knowledge" T0 audit item.
**Locked principle:** *A bio that is 90% filled with story-grounded facts
is more valuable for a memoir than a bio that is 100% filled but half of it
came from direct asks that stripped the context out. Optimize for
high-context completeness, not absolute completeness.*

## Why this WO exists

The previous Bio Builder ran a one-question-at-a-time field-walking
orchestrator inside the interview itself. The narrator was asked
"what is your mother's maiden name" mid-conversation. The system optimized
for filling slots.

Two things broke this model:

1. **The universal pivot.** When Bio Builder was Horne-specific, much of
   the bio came pre-loaded from Chris's knowledge and from family
   documents already in hand. The Bio Builder filled the gaps. For
   universal narrators there is no pre-load. Every bio starts empty.
   The slot-filling orchestrator becomes the *only* source of structured
   facts, which means it must run aggressively, which means it dominates
   the interview, which destroys the oral-history posture the rest of
   the architecture is moving toward.

2. **The oral-history default flip** (WO-LORI-ORAL-HISTORY-DEFAULT-01).
   The orchestrator is now gated by session style — it does not run in
   oral_history mode. Which means the bio in oral_history mode is filled
   by *something else* or it is not filled at all. "Not at all" produces
   a memoir without structured chronology, named-entity index, or
   relationship graph. Unacceptable.

This WO defines what fills the bio when the orchestrator does not run.

The answer, drawn from earlier conversation: a four-tier division of
labor where chapter-driven extraction is the primary source, document
ingestion is a high-authority parallel source, anchored in-session
asking handles a few high-value gaps, and operator direct-entry handles
the long tail of low-narrative-value fields.

## Live evidence

Two failure modes this WO addresses:

**Failure mode A — bio sparseness in oral_history mode.**

Projected universal narrator runs 6 sessions in oral_history mode.
Sessions are rich — chapters about growing up, military service, marriage,
children, work, retirement, grandchildren. Hours of audio.

Current state after WO-LORI-ORAL-HISTORY-DEFAULT-01 ships without this WO:

- Session loop orchestrator does not run → no field-walking
- Extraction pipeline writes proposals to `family_truth_rows` based on
  narrator turns
- Operator reviews proposals in WO-13 queue
- Bio schema has dozens of formal fields (birth date, birth place, parents,
  siblings, schools attended, employers, addresses lived, etc.)
- Many of these are mentioned in chapters but in narrative form: "I went
  to Pasco High and graduated in '47"
- Extractor catches some, misses others, depending on extraction prompt
  quality
- No mechanism tracks which fields remain empty vs. weakly sourced vs.
  filled
- Operator has no surface showing "narrator has run 6 sessions and we
  still don't have a confirmed birth date"

Result: bio is patchy, operator doesn't know what's missing until the
memoir-writing phase reveals gaps too late to ask.

**Failure mode B — anchored asking happens too rarely or not at all.**

The earlier conversation established that Lori should occasionally ask
anchored bio questions: "you were still around Stanley when the Army
chapter started?" — but only when (a) a gap exists, (b) the current
chapter provides a natural anchor, (c) the chapter has reached a natural
pause.

Phase 1's thread bank surfaces unresolved *story* doors. It does not
surface unresolved *bio gaps.* Without this WO, anchored asking does not
happen at all in oral_history mode — there's no service that knows
which fields are gaps, what the current chapter context is, or when to
surface a question.

Result: bio gaps stay gaps forever; Lori never closes them even when
the conversation provides perfect openings.

## Fix architecture

Four tiers, three new services, one new operator surface, one schema
extension.

### Tier model — division of labor

| Tier | Source | When | Authority | Tracks |
|---|---|---|---|---|
| 1 | Chapter-driven extraction | Every narrator turn | needs_verify (default) | All facts mentioned in chapters |
| 2 | Document-derived | Operator uploads | varies by document type | Facts from identity docs, family papers, prior memoirs |
| 3 | Anchored asking | In-session, low-momentum gaps | needs_verify (default) | High-value bio fields when chapter provides anchor |
| 4 | Operator direct-entry | Between sessions | approved (operator authority) | Long-tail low-narrative-value fields |

Tier 1 does the bulk of the work. Tier 2 provides high-confidence
ground truth where documents exist. Tier 3 is sparse and selective.
Tier 4 catches the remainder.

### Bio schema — gap map foundation

New table: `bio_fields` defines the universal bio schema.

Schema:
```
bio_fields
  id                  uuid pk
  field_key           text uniq         -- 'birth_date' / 'mother_maiden_name'
  field_label         text              -- 'Birth date' (display)
  field_category      enum              -- 'identity' | 'family' | 'education' |
                                        --   'work' | 'military' | 'geography' |
                                        --   'relationships' | 'milestones'
  field_type          enum              -- 'date' | 'date_range' | 'place' |
                                        --   'person' | 'text' | 'enum'
  narrative_value     enum              -- 'high' | 'medium' | 'low'
                                        --   high: anchored asking eligible
                                        --   medium: extractor target, no asking
                                        --   low: operator-entry only
  life_stage_range    text              -- 'childhood' | 'adult' | 'all'
  asking_anchors      jsonb             -- patterns that signal a chapter is
                                        --   in this field's territory
```

Initial schema seeded with ~80 universal bio fields covering identity,
family structure, education sequence, work history, military service
if applicable, geographic moves, marriage and children, major life
milestones. Schema is universal (works for any narrator) but extensible
per-tenant if specific narrators have unusual structure (a tenant who
wants to track a specific genealogical custom can extend; not in scope
for v1).

New table: `bio_facts` stores the actual filled values per narrator.

Schema:
```
bio_facts
  id                  uuid pk
  tenant_id           uuid              -- per universal pivot
  narrator_id         uuid              -- which person this bio is about
  field_key           text fk           -- which schema field
  value               jsonb             -- the actual value
  status              enum              -- 'empty' | 'extracted_needs_verify' |
                                        --   'document_sourced' | 'anchored_asked' |
                                        --   'operator_entered' | 'approved' |
                                        --   'conflicted'
  source              jsonb             -- {tier: 1-4, session_id?, turn?, doc_id?,
                                        --   operator_id?, timestamp}
  confidence          numeric(3,2)      -- 0.00-1.00
  last_updated        timestamp
  conflict_with       uuid nullable     -- if status=conflicted, points at peer row
```

Bio facts can have multiple rows per field if sources conflict (Kent's
memory says 1959; birth certificate says 1958). Both rows persist with
`status='conflicted'` until operator resolves. Conflict resolution
preserves both as audit trail; one row is promoted to `approved`, the
other moves to `superseded`.

### Tier 1 — chapter-driven extraction

The extraction pipeline already exists (`family_truth_rows` writes from
narrator turns). This WO extends it to write to `bio_facts` in parallel
when extracted facts match bio schema fields.

Mapping happens in a new service: `services/bio_fact_router.py`.

Logic:
- Existing extractor returns proposed facts as today
- Router checks each fact against `bio_fields` schema
- If field_key matches: write to `bio_facts` with
  `status='extracted_needs_verify'`, source recorded
- If field_key does not match: existing `family_truth_rows` flow only
- Conflict detection: if a `bio_facts` row already exists for this
  `narrator_id` + `field_key` with a different value:
  - If existing status is `approved` or `document_sourced` (higher
    authority): new extraction is logged as candidate, not promoted;
    surfaced in operator review as "narrator memory differs from
    document"
  - If existing status is `extracted_needs_verify`: new row written
    with `status='conflicted'`, both rows linked via `conflict_with`,
    surfaced in operator review

### Tier 2 — document-derived

Document Archive exists. This WO extends document ingestion to write
to `bio_facts` based on document type.

Document type → authority mapping:

| Document type | Default status when extracted |
|---|---|
| Birth certificate | `document_sourced`, confidence 1.0 |
| Marriage certificate | `document_sourced`, confidence 1.0 |
| Military DD-214 | `document_sourced`, confidence 1.0 |
| Death certificate (for family members) | `document_sourced`, confidence 1.0 |
| Diploma | `document_sourced`, confidence 0.95 |
| Prior published memoir | `extracted_needs_verify`, confidence 0.7 |
| Family genealogy document | `extracted_needs_verify`, confidence 0.6 |
| Handwritten letter | `extracted_needs_verify`, confidence 0.5 |
| Photograph (with caption) | `extracted_needs_verify`, confidence 0.4 |
| Unknown document | `extracted_needs_verify`, confidence 0.3 |

The "NEVER auto-promote to truth from media archive" locked principle is
preserved: only identity documents (birth/marriage/death/military
certificates, diplomas) auto-promote. Everything else proposes.

Document-sourced facts beat narrator-memory facts in conflict resolution
by default. Narrator may correct the document ("my birth certificate has
the wrong year, I was born in '38 not '37") in which case operator can
manually override.

### Tier 3 — anchored asking

This is the new substantive capability. New service:
`services/bio_anchored_asker.py`.

Decision logic per Lori composition turn:

1. Get current bio gaps for this narrator: query `bio_facts` where status
   is `empty` or where field exists in schema but no `bio_facts` row
   exists. Filter to `narrative_value='high'` fields only — never ask
   for low-value fields in-session.

2. Get current chapter context: the last 3-5 narrator turns, the
   classified turn type, the story momentum score (from Phase 1).

3. Eligibility check:
   - Momentum must be < 0.4 (chapter is in pause or transition; never
     interrupt story momentum for a bio question)
   - At least 4 narrator turns have elapsed since last anchored ask
     (rate limit — at most ~1 anchored ask per 4-5 turns)
   - The current chapter context must match at least one `asking_anchors`
     pattern for an empty high-value field

4. Anchor matching:
   - `bio_fields.asking_anchors` is a list of trigger patterns
   - Example for field `military_branch`: anchors include keywords
     "Army", "Navy", "Marines", "boot camp", "basic training", "fort",
     "base", "deployed", "served"
   - When chapter context contains anchor patterns, the corresponding
     bio gap becomes eligible for asking

5. Composition:
   - If an eligible gap is matched, compose an anchored question rather
     than a generic one
   - Template: leverages chapter context to phrase the question as if
     it's part of the chapter's natural progression
   - Example: chapter mentions "Fort Ord", `military_branch` is empty,
     composed question is "Were you Army at Fort Ord, or another
     branch?" not "What military branch did you serve in?"
   - The anchored question is composed by the LLM with explicit prompt
     guidance to phrase as chapter-natural; not template-filled

6. Logging:
   - Anchored ask written to `bio_facts` with status
     `anchored_asked_pending` — placeholder row indicating an ask
     happened, no value yet
   - Next narrator turn's extraction either fills the value (status
     becomes `extracted_needs_verify`) or doesn't (placeholder remains;
     operator sees that an ask was made and narrator didn't answer)

7. Frequency cap:
   - Maximum 1 anchored ask per 4 turns (env-tunable)
   - Maximum 3 anchored asks per session (env-tunable)
   - These caps exist because oral-history posture must not slip back
     into questionnaire mode through anchored-asking creep

### Tier 4 — operator direct-entry

New operator surface: bio editor.

UI:
- Per-narrator view, grouped by field_category
- Each field shows current status (color-coded: green=approved,
  amber=needs verify, gray=empty, red=conflicted)
- Click any field to enter, edit, approve, or mark as
  unanswerable-known-gap
- Operator entries write to `bio_facts` with
  `status='operator_entered'` immediately promoted to `approved`
  (operator has authority)

The editor is also where conflict resolution happens. Conflicted rows
display side by side with their sources; operator picks which to promote.

This surface is built minimally in this WO. Full operator-UX polish is a
separate lane.

## Anchored Asking Creep Defense

Tier 3 is the only piece of this architecture where Lori's mouth is
used as an operator instrument. Every other tier (chapter extraction,
document derivation, operator direct-entry) fills bio without
interrupting the narrator. Tier 3 interrupts.

The architecture has natural pressure pushing every other gate toward
discipline. Anchored asking has natural pressure in the wrong
direction: operator visibility into bio gaps creates instinct to
close them; visible filling moments get disproportionate credit over
invisible chapter extraction; memoir-writing gap reveals create
retroactive pressure to have asked; sparse-narrator sessions tempt
compensatory asking; per-narrator tuning aggregates into systemic
drift.

The per-session frequency caps (max 3 per session, 4+ turns between
asks) prevent in-session bloat but do not prevent inter-session
drift of the caps themselves. This section adds defenses that operate
against drift, not just against per-session count.

### Defense 1 — Chapter continuation telemetry

Every anchored ask writes a `chapter_continuation_metric` to the
`bio_facts` row alongside the existing source data:

```
chapter_continuation_metric: {
  narrator_turn_length_before_ask: int,    -- avg of last 3 turns
  narrator_turn_length_after_ask: int,     -- the turn immediately after
  narrator_turn_length_baseline: int,      -- session avg at similar momentum
  continuation_delta: float,               -- (after - baseline) / baseline
  ask_caused_chapter_end: bool,            -- true if next 2 turns < 20 words each
}
```

`continuation_delta` is the load-bearing measurement. Negative values
mean anchored asks systematically shorten subsequent narrator turns
— the creep mechanism showing up in data. Operator dashboard surfaces
this as a per-narrator rolling average across all anchored asks ever
made.

If `continuation_delta` average drops below -0.25 for any narrator
over a rolling 5-ask window, the bio gap map shows an amber warning
banner: "Anchored asks are systematically shortening this narrator's
chapters. Consider reducing asking frequency or relying more on
chapter extraction." This is information for the operator; the system
does not auto-throttle, but it makes the data visible.

If `ask_caused_chapter_end` is true for more than 40% of anchored
asks across any narrator's session history, the architectural posture
is failing for that narrator and the warning escalates to red.

### Defense 2 — Budget tied to chapter health, not just turn count

The current cap is "3 per session AND 4+ turns between asks." This
counts events. It does not detect chapter exhaustion.

Extended cap (replaces current cap):

> An anchored ask is permitted only when ALL of the following are true:
> - Fewer than 3 anchored asks have fired in this session
> - 4+ narrator turns have elapsed since the last anchored ask
> - Momentum is < 0.4 (existing)
> - Chapter context matches `asking_anchors` pattern (existing)
> - Field is `narrative_value='high'` (existing)
> - **NEW:** Narrator's last 5 turn average length is at least 80% of
>   the session's first-5-turn average length

The last clause means: if the narrator's chapters are getting
shorter, anchored asks are off-budget regardless of count. The system
recognizes chapter exhaustion as the dispositive condition, not
elapsed time.

This change protects against the failure mode where a narrator's
first session is rich, gets 3 anchored asks early, gets exhausted by
those asks, and ends in short factual turns — at which point the cap
"resets" for the next session and the cycle repeats. With the new
clause, anchored asks self-throttle when the narrator stops
producing chapters at sustainable length, regardless of which
session they're in.

### Defense 3 — Hard friction on raising caps

The current architecture allows tuning of anchored asking caps via
`.env`:
- `HORNELORE_BIO_ANCHORED_MAX_PER_SESSION` (default 3)
- `HORNELORE_BIO_ANCHORED_TURN_SPACING` (default 4)
- `HORNELORE_BIO_ANCHORED_MOMENTUM_CEILING` (default 0.4)
- `HORNELORE_BIO_ANCHORED_CHAPTER_HEALTH_FLOOR` (default 0.8, new from
  Defense 2)

Raising any of these caps requires:

1. A separate config file `bio_anchored_overrides.toml` (not just
   an `.env` edit), with explicit per-cap entries
2. A required acknowledgment field in the file:
   `i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode = true`
3. Log line on every session start when overrides are active:
   `[bio_anchored] OVERRIDES ACTIVE — session is operating outside
   default oral-history posture: <list of changed caps and values>`
4. Operator dashboard banner persistent until overrides removed:
   amber-bordered, dismissable per session only, never globally
5. Operator runbook section documenting that overrides are a
   non-default state requiring explicit justification per narrator
6. Parent-session readiness gate failure if overrides active during
   any gate verification run — overridden caps cannot pass the
   readiness framework

This is deliberate friction. Raising caps must require crossing a
visible line, not adjusting a single env value. The friction is the
defense; the friction is what makes "we're an oral-history system"
a maintained promise rather than an aspirational one.

### Bio gap map — operator's primary view

New operator dashboard surface: bio gap map.

For each narrator, displays:
- Bio completeness percentage by category
- Visual heatmap of fields by completion + confidence
- "Recently asked" section showing the last few anchored asks and
  their outcomes
- "Suggested asks" section showing high-value empty fields that
  currently have no chapter anchor — operator can manually ask via
  direct entry or note for next session
- "Conflicts pending" section

The gap map is read-only-ish (entries route to the bio editor for
modification). It is the operator's situational awareness surface
for what the memoir is missing.

## Acceptance gates

1. **Schema seeded with universal bio fields.**
   - `bio_fields` table contains ~80 field definitions across all 8
     categories
   - Each field has narrative_value, field_type, asking_anchors set

2. **Tier 1 extraction routes to bio_facts when fields match.**
   - Narrator says "I was born in Spokane in 1938"
   - Extractor proposes facts as today
   - Router writes `bio_facts` rows for `birth_place=Spokane` and
     `birth_date=1938` with `status='extracted_needs_verify'`,
     source records session_id and turn

3. **Tier 1 conflict detection writes correctly.**
   - First session: narrator says "born in '38" → bio_facts row created
   - Second session: narrator says "born in '37" → second row created
     with `status='conflicted'`, both rows linked via `conflict_with`

4. **Tier 2 identity documents auto-promote.**
   - Operator uploads birth certificate showing 1938
   - Extracted to bio_facts with `status='document_sourced'`,
     confidence 1.0
   - If conflicts exist with narrator-memory rows, narrator-memory rows
     surfaced for review but document-sourced row holds

5. **Tier 2 non-identity documents propose.**
   - Operator uploads handwritten letter mentioning a date
   - Extracted to bio_facts with `status='extracted_needs_verify'`,
     confidence 0.5
   - Never auto-promoted regardless of confidence

6. **Tier 3 anchored asking fires only when conditions met.**
   - Narrator in story momentum (>= 0.4): NO anchored ask, period
   - Narrator in low momentum, fewer than 4 turns since last ask:
     NO anchored ask
   - Narrator in low momentum, 4+ turns since last ask, chapter context
     matches `military_branch.asking_anchors`, field is empty: anchored
     ask composed
   - Composed question references chapter content ("Were you Army at
     Fort Ord..."), not generic ("What military branch...")
   - `bio_facts` placeholder row written with
     `status='anchored_asked_pending'`

7. **Tier 3 session frequency cap honored.**
   - Maximum 3 anchored asks per session regardless of how many gaps
     or anchors arise
   - Cap is env-tunable

8. **Tier 3 never fires for low-narrative-value fields.**
   - Narrator's middle name spelling, parents' middle names, exact
     dates of unrelated minor events: extractor catches if mentioned;
     anchored asker NEVER asks these in-session

9. **Tier 4 operator entry promotes to approved.**
   - Operator types value via bio editor
   - Row written with `status='operator_entered'` and immediately
     `approved`
   - Audit trail preserved

10. **Bio gap map displays correctly.**
    - Operator can see per-narrator completeness by category
    - Recently asked section shows last anchored asks with outcomes
    - Suggested asks section shows high-value empty fields without
      current chapter anchor
    - Conflicts pending section shows conflicted rows

11. **Universal applicability (no Horne-specific assumptions).**
    - Schema seed contains zero Horne-family-specific fields
    - `asking_anchors` patterns generalize across narrators
    - Tests run against synthetic narrator turns covering varied
      backgrounds (military, non-military, immigrant, urban, rural,
      varied family structures)

12. **Backward compatibility with existing family_truth_rows.**
    - The legacy `family_truth_rows` pipeline continues running
      unchanged
    - Bio facts are written in parallel, not as replacement
    - Operator can still use existing WO-13 review queue for
      non-bio-schema facts (story details, named individuals, etc.)

13. **Chapter continuation telemetry is written on every anchored ask.**
    - `bio_facts` row for every anchored ask contains
      `chapter_continuation_metric` JSON
    - All 5 fields present and computed correctly
    - Operator dashboard surfaces rolling average per narrator

14. **Chapter exhaustion blocks anchored asks regardless of count.**
    - Synthetic test: narrator with declining turn-length pattern
    - Confirm anchored ask declined when last-5-avg < 80% of first-5-avg
    - Confirm log line `[bio_anchored] skipped — chapter health floor
      violated, last_5_avg=22 first_5_avg=68 ratio=0.32 floor=0.8`

15. **Cap overrides require explicit acknowledgment file.**
    - `.env` cap changes alone do NOT take effect (read but ignored
      unless overrides file present)
    - `bio_anchored_overrides.toml` without acknowledgment field
      causes startup error
    - Acknowledgment field with `false` value causes startup error
    - All conditions met → overrides take effect with all logging
      and dashboard banner active

16. **Readiness gates fail when overrides active.**
    - Run parent-session readiness verification with overrides active
    - Confirm gate verification fails with explicit message
      `Bio anchored override active — system not in default posture;
      readiness gate verification requires default caps`

17. **Telemetry warning thresholds fire correctly.**
    - Synthetic test data with -0.30 average continuation_delta
      → amber warning visible on bio gap map
    - Synthetic test with 50% ask_caused_chapter_end rate
      → red escalation visible
    - Warnings persist across stack restart (computed from
      historical bio_facts rows)

## Test coverage

`tests/test_bio_schema_seed.py` (new):

- 5 tests: seed integrity, category coverage, narrative_value
  distribution, asking_anchors well-formed, universal applicability
  spot-checks

`tests/test_bio_fact_router.py` (new):

- 10 tests: extraction routing, schema match, no-match passthrough,
  conflict detection, conflict linking, status transitions

`tests/test_document_authority.py` (new):

- 12 tests: each document type's default status and confidence;
  auto-promote rules for identity docs; conflict resolution between
  document and narrator-memory sources

`tests/test_bio_anchored_asker.py` (new):

- 15 tests: momentum gate, turn-spacing rate limit, session frequency
  cap, anchor matching for several field types, composition guidance,
  narrative_value filter, placeholder row creation, narrator response
  outcome tracking

`tests/test_bio_gap_map.py` (new):

- 8 tests: per-narrator query, category aggregation, recently-asked
  surfacing, suggested-asks logic, conflict surfacing

`tests/test_bio_editor.py` (new):

- 6 tests: direct entry, conflict resolution UI, audit trail
  preservation, status transitions on operator action

`tests/test_bio_builder_universal_integration.py` (new):

- 5 end-to-end tests: full session in oral_history mode with bio
  filling via all four tiers; verify gap map accuracy after multiple
  sessions; verify universal narrator (non-Horne synthetic) works

`tests/test_bio_anchored_creep_defense.py` (new):

- 5 tests: chapter continuation metric written and computed on every
  anchored ask; chapter health floor blocks asks regardless of count;
  override file acknowledgment validation (missing file, missing field,
  false field, all-valid); readiness gate failure when overrides
  active; telemetry warning thresholds (amber at -0.25 delta, red at
  40% chapter-end rate, persistence across restart)

Target: 66 new tests across 8 files, all green before merge.

## Live verification

1. Cycle stack with trio + Phase 1 + oral-history default + this WO
2. Create new narrator (synthetic universal test narrator, not Horne)
3. Run 3 sessions in oral_history mode
4. After each session, check `bio_facts`:
   - Session 1: confirm extracted facts written, status correct
   - Session 2: confirm new facts added, any conflicts flagged
   - Session 3: confirm anchored asks happened (1-3 per session),
     anchored composition matched chapter context
5. Upload synthetic birth certificate
6. Confirm:
   - Document parsed, fact extracted with `status='document_sourced'`
   - Conflicts with narrator memory surfaced for review
7. Open bio gap map for narrator
8. Confirm:
   - Completeness percentages reasonable given 3 sessions
   - Categories shown
   - Recently asked section populated
   - Suggested asks section shows high-value gaps without chapter anchors
9. Use bio editor to enter a long-tail field (e.g., father's middle name)
10. Confirm:
    - Row created with `status='operator_entered'`, `approved`
    - Audit trail shows operator + timestamp
11. Counter-test: confirm questionnaire_first mode session still runs
    the orchestrator and fills bio via traditional asking — this WO
    must not break the explicit-questionnaire workflow

## Files changed

- `server/data/migrations/` (new: `bio_fields` table, `bio_facts` table,
  schema seed)
- `server/code/services/bio_schema.py` (new, ~80 lines: field
  definitions, seed loader, schema query helpers)
- `server/code/services/bio_fact_router.py` (new, ~150 lines: extraction
  routing, conflict detection, status transitions)
- `server/code/services/document_authority.py` (new, ~120 lines:
  document type → authority mapping, auto-promote rules, conflict
  resolution with narrator-memory sources)
- `server/code/services/bio_anchored_asker.py` (new, ~360 lines:
  eligibility logic, anchor matching, composition guidance, frequency
  caps, chapter continuation metric computation, chapter health floor
  check, override file loader with acknowledgment validation)
- `server/code/services/bio_gap_map.py` (new, ~210 lines: per-narrator
  aggregation queries, suggested-asks logic, recently-asked surfacing,
  chapter continuation rolling average, creep warning banner thresholds)
- `server/code/api/parent_session_readiness.py` (+~30 lines: anchored
  override detection in readiness gate verification — overridden caps
  cannot pass gates)
- `server/code/api/chat_ws.py` (+~50 lines: anchored asker invocation
  in composition pipeline; runs only in oral_history /
  warm_storytelling / companion / memory_exercise modes; skipped in
  questionnaire_first)
- `server/code/services/lori_communication_control.py` (+~30 lines:
  anchored ask composition goes through Phase 1 validators normally;
  no special-casing)
- `server/code/api/extraction_pipeline.py` (+~40 lines: bio_fact_router
  invocation parallel to existing family_truth_rows write)
- `ui/js/bio-editor.js` (new, ~250 lines: per-field UI, conflict
  resolution view, audit trail display)
- `ui/js/bio-gap-map.js` (new, ~240 lines: dashboard surface including
  creep warning banners)
- `ui/css/bio-editor.css` (new, ~100 lines)
- `docs/operator_runbook.md` (new section: "Anchored Asking Override
  Procedure" — documents the friction and when, if ever, overrides are
  justified)
- 8 new test files (counts above)
- `.env.example` (+~30 lines: anchored asker frequency caps including
  chapter health floor, note that cap variables require the overrides
  file to take effect, document authority overrides, anchored asker
  enable flag)

## Related lanes

- **HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md** — resolves "Bio Builder
  pre-load from family knowledge" T0 audit item; resolves "Document
  Archive primarily supplements known facts" T0 audit item
- **WO-LORI-ORAL-HISTORY-DEFAULT-01** (REQUIRED predecessor — Bio
  Builder universal assumes orchestrator is gated by style; anchored
  asking is the substitute mechanism in oral_history mode)
- **WO-LORI-STORY-FIRST-PHASE-1-01** (REQUIRED predecessor — Phase 1
  thread bank, momentum signal, and reflection grounding are substrate;
  anchored asker depends on momentum signal for eligibility, depends
  on Phase 1's chapter-context understanding for anchor matching)
- **Existing extraction pipeline** (`family_truth_rows`, WO-13 review
  queue) — runs unchanged; this WO writes in parallel
- **Existing Document Archive** — extended with type-based authority
  mapping; auto-promote scope expanded for identity docs only
- **Future operator-UX polish lane** — bio editor and gap map in this
  WO are functional but minimal; full UX work deferred
- **Future per-narrator template lane** — `bio_fields.asking_anchors`
  are universal in v1; per-narrator anchor customization deferred to
  the per-narrator template work flagged in strategy doc audit (R)
- **Future memoir-assembly lane** — bio_facts is the structured-fact
  substrate that memoir assembly will draw from; not in scope here
  but designed for downstream consumption

## Out of scope (deferred)

- **Genealogy mode.** Some narrators have rich multi-generational data
  (grandparents, great-grandparents). The schema supports it (parents,
  siblings extensible) but the asking and review surfaces are tuned for
  the narrator themselves and their immediate family. Multi-generational
  bio editing is a separate lane.
- **Cross-narrator bio linking.** When Kent's bio mentions Janice and
  Janice's bio mentions Kent, the system today stores both
  independently. A future "shared family graph" lane links them. Not
  in scope.
- **Bio export formats.** The bio is queryable from the database. A
  formatted export (PDF bio sheet, structured JSON for genealogy
  tools, narrative-prose summary) is a separate downstream lane.
- **Family-facing bio review.** Today only operator sees the gap map
  and bio editor. A future surface may allow family members to
  review and confirm/correct facts. Tied to family-facing surfaces
  pre-rebrand decision in strategy doc.
- **Bio versioning beyond conflict resolution.** Today bio_facts
  supports conflicts (two rows with different values) and resolution
  (one promoted, other superseded). Full version history with
  rollback is a separate lane.
- **Anchored ask composition with LLM-generated phrasing variations.**
  V1 composes anchored asks via LLM with guidance prompt; full
  variation tracking and A/B-style learning of which phrasings get
  best narrator engagement is deferred.
- **Tier 3 in questionnaire_first mode.** Anchored asker is disabled
  in questionnaire_first because the explicit questionnaire flow is
  itself anchored-asking. Re-enabling in questionnaire_first would
  duplicate; defer indefinitely.
- **Automated suggested-ask generation as draft operator email/SMS
  prompts** for between-session asking. Considered; rejected for v1
  because it adds outbound communication surface that triggers
  consent/compliance work not yet ready.
- **Memoir-readiness scoring** based on bio completeness + chapter
  coverage. Future quality metric; this WO produces the substrate
  data but not the score.
