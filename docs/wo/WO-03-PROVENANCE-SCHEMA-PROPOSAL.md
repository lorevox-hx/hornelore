# WO-03A — provenance and confirmation

Revision 3, 2026-09-20. **IMPLEMENTED.** Approved with four corrections;
correction 4 was then rewritten against the live schema after the table it
relied on turned out to be empty.

Two things changed during implementation and are marked ⚠ IMPLEMENTED AS
below rather than quietly absorbed:

- the operator route has TWO callers, not one — `_addRepeatEntry` had to
  join `_saveSection` or the no-op rule leaves answers unclassified
- `turn_evidence` became a stored three-state column (approved)

No narrator record was touched. No backfill exists.

ENABLES: Lori can tell what the narrator actually said, what a person
entered, and what she inferred — including after a correction.

## Correction 1 — the PUT is NOT a human-entry route

Revision 1 proposed stamping `operator_direct` for every changed path on the
existing PUT. That was the exact error this work order exists to remove.

`_persistDrafts` has ~20 callers across five modules, all funnelling through
`_persistQuestionnaire` with the literal `source: "ui_save"` — including
`_syncIdentityToBB` (Lori's identity captures, `app.js:6072, 6113, 6208,
6237, 6294`) and `_syncPrefillIfBlank` (model values on blank paths,
`projection-sync.js:407-435`). Stamping that route `operator_direct` would
have given Lori's own writes the system's authority. The review caught it.

**The asymmetry that makes this solvable.** A client claiming LOWER authority
is safe to believe — nothing gains by falsely calling itself a machine. A
client claiming HIGHER authority is not. So:

    a dedicated operator-entry route   ->  operator_direct
    the shared legacy PUT              ->  NO ROW. Unclassified.

`POST /api/bio-builder/questionnaire/answer` carries `sections` — what the
form actually saved — and provenance is stamped only for changed paths
WITHIN those sections. A changed path outside them came from somewhere else
in the same whole-document request and stays unclassified.

⚠ IMPLEMENTED AS: **two callers, not one.** `_addRepeatEntry` had to join
`_saveSection`. Tracing the no-op rule showed that leaving it out opens a
hole rather than closing one: the operator fills in the mother, clicks
"+ Add another parent" — which persists her answers — then clicks Save,
which now changes nothing, and a no-op writes no provenance. Her answers
would stay unclassified forever despite having been typed by a person into
the Bio Builder form. Both callers are scoped to one named section, so
neither claims more than the save would have.

Every other caller keeps the legacy PUT and writes no provenance at all.
Lori's writers therefore get `unknown`, not a false `operator_direct`.
They move to the propose operation in WO-03B; until then, silence is the
honest record.

Threading: `_saveSection` passes an operation hint through `_persistDrafts`
to `_persistQuestionnaire`, which selects the endpoint. The ~20 other callers
pass nothing and are unaffected.

**Enforcement is a test, not a promise.** The harness's server double records
which endpoint each write hit; a test fails if any Lori-derived writer
reaches the operator-entry route.

## Correction 2 — answer and provenance commit together

`_write` (`questionnaire_persistence.py:357`) already wraps compare-and-write
in `BEGIN IMMEDIATE` with rollback at `:402` and `:436`. Provenance is
written **inside that transaction**, not by the router afterwards. The origin
is passed into `merge_whole_document` rather than applied to its result.

A no-op returns at `:438` before any write — so **an unchanged save does not
touch provenance**, exactly as it does not touch the revision counter.

## Correction 3 — a correction preserves what it replaced

The primary key names the CURRENT provenance of the CURRENT value. History
lives where correction history already lives: `bio_builder_questionnaire_
revisions` (0058) stores `previous_values` per path and is written by
`_archive` inside the same transaction.

    ALTER TABLE bio_builder_questionnaire_revisions
      ADD COLUMN previous_provenance TEXT NOT NULL DEFAULT '{}';

When `_write` replaces the value at a path, the superseded provenance row for
that path is archived into `previous_provenance` alongside `previous_values`,
then the current row is replaced. The pair always describes the same moment:
what the value was, and where it came from.

Additive column on an existing table, no backfill, `'{}'` for every row
already written.

## Correction 4 — narrator evidence is verified, not taken on trust

**Revision 2 was wrong here, in both clauses.** Measured against the live
database 2026-09-20, read-only:

    memory_archive_turns          0 rows.  Never populated. Not once.
    turns                     1,487 rows
    sessions.person_id          EXISTS — added by 0045, write-once

The table Revision 2 named as the only narrator-scoped turn record is empty,
and the table it said had no owner column has one. I read the `CREATE TABLE`
at `db.py:594` — which migration 0045 superseded — instead of the live schema.
`sessions` carries `person_id` and `person_id_source`
(`0045_sessions_legacy_payload_owner.sql:83`).

**So the verification is a join, and it works.**

```sql
SELECT 1
  FROM turns t
  JOIN sessions s ON s.conv_id = t.conv_id
 WHERE t.id = ?
   AND s.person_id = ?
   AND t.role = 'user'
   AND COALESCE(json_extract(t.meta_json,'$.origin'),'') <> 'system_directive';
```

Ownership is trustworthy where it exists. `ensure_session` (`db.py:1760`)
writes it once and never silently changes it: a NULL incoming id cannot clear
an owner (`COALESCE`), and a *different* incoming id raises
`SessionOwnerConflict` rather than overwriting. Every `chat_ws` persist site
passes `person_id` (`:601, :2184, :3694, :4336`). Six turns written through
that path today resolve to ZZ WALKTHROUGH with `person_id_source='explicit'`.
The live path populates it.

**The third clause is not defensive padding.** A system directive is stored
with `role='user'`. Live row 2635 on ZZ's own session:

    2634  user  {"origin":"system_directive"}  "[SYSTEM: The narrator has been quiet..."

That is the prompt composer speaking in the narrator's slot. Cite it as
`narrator_direct` and the system records its own stage direction as something
a person said. The docstring at `db.py:2331` measured 120 of 794 user rows as
directives before the flag existed. Only 4 rows carry `origin` today, because
the flag landed 2026-08-09 — so for historical turns the clause does not
protect, which is a further reason a historical citation fails verification
rather than passing weakly.

**Coverage is thin, and honestly so.** 1,468 of 1,487 turns do not resolve:
337 sessions hold turns, 2 carry an owner. All of it predates 0045, plus the
REST chat path at `api.py:799-800`, which calls `add_turn` with no
`person_id` and none in `meta` and therefore still mints ownerless sessions
today. That path is a defect, recorded here, not fixed in WO-03A — changing a
turn writer is not something to smuggle into a provenance work order.

Consequence for the route: a citation to a turn written before 0045, or via
REST, **fails verification**. That is the correct answer, not a gap to paper
over. It is also why the route must not treat verification as a gate on
saving.

**Three evidence states, stored, never collapsed.** Per the ruling of
2026-09-20 — an unverified turn reference must not prevent saving the
narrator's answer, and must not produce a verified claim:

    turn_evidence = 'verified'    the join above returned a row
                  = 'unverified'  a turn id was cited and did not verify
                  = 'absent'      no turn id was cited

`source_turn_id` holds the **claimed** id in all three cases where one was
given — it is not nulled on failure. Nulling would erase the difference
between "no citation" and "a citation that did not check out", and the second
is the one worth investigating. The answer is stored either way: a
bookkeeping failure must not discard what the narrator said.

Only `verified` may be read as evidence. A consumer that treats `unverified`
as support is reading a claim as a fact, and the column name says so.

**The narrator's words and Lori's rendering of them are separate.**
`original_text` holds what the narrator said, before normalisation. The value
in the document may be a normalised form. A consumer comparing the two can
see whether the stored answer is the narrator's phrasing or a machine's
tidying, and attribute accordingly. No `normalized` flag — a derived fact
that can disagree with the data it describes is worse than a comparison.

## The table — 0059_answer_provenance.sql

```sql
CREATE TABLE IF NOT EXISTS bio_builder_answer_provenance (
  person_id       TEXT NOT NULL,
  section         TEXT NOT NULL,
  entry_id        TEXT NOT NULL DEFAULT '',   -- WO-02 _entryId; '' for flat sections
  field           TEXT NOT NULL,

  origin          TEXT NOT NULL,              -- operator_direct | narrator_direct | ai_suggested
  origin_at       TEXT NOT NULL,

  -- The CLAIMED turn, always stored when one was cited, and a separate
  -- column saying whether it stood up. Nulling the id on failure would
  -- erase the difference between "no citation" and "a citation that did
  -- not check out", and the second is the one worth investigating.
  source_turn_id  TEXT,
  turn_evidence   TEXT NOT NULL DEFAULT 'absent',   -- verified | unverified | absent
  original_text   TEXT,                       -- the narrator's own words, pre-normalisation

  proposed_by     TEXT,                       -- 'lori' when it began as a suggestion
  confirmed_via   TEXT,                       -- 'acceptance' | NULL
  confirmed_at    TEXT,

  PRIMARY KEY (person_id, section, entry_id, field),
  FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);
```

Keyed by entry id, not position — the WO-02 payoff. A reorder renames every
flattened path and does not move an entry's provenance.

`ai_suggested` is permanent. An acceptance adds `confirmed_via` and
`confirmed_at`; it never rewrites `origin`. The record always shows Lori
proposed it.

**No row means unknown.** Absence is the state, so there is no migration and
no write to any existing record. Janice's 100 values, Kent's 86 and
Christopher's 130 get zero rows.

`narrator_data_inventory.py` gains a lane: class AUTHORITATIVE, portable yes,
same shape as `identity_change_log`.

## Scope

IN: the table, the revisions column, the operator-entry route, the
narrator-answer route with turn verification, provenance written inside the
existing transaction, and the B6 read repair — `prompt_composer` builds a
`suggested` map and never returns it, so the "already on record,
provisionally — is that right?" hint lost its input when I removed
suggestions from `provisional`. Mine to fix.

OUT: propose/accept and the review control (WO-03B). Routing
`_syncIdentityToBB` and `_syncPrefillIfBlank` through propose (WO-03B, needs
propose to exist). Any rewrite of existing values. The fanout flag stays 0.

## Findings that changed the design, reported rather than absorbed

1. **`memory_archive_turns` is empty — 0 rows, always.** Revision 2 built
   verification on it. It could never have verified anything. Asked for
   explicitly; the answer is that it holds no live chat turn.

2. **`sessions.person_id` exists and works**, and is the real verification
   path. I asserted otherwise from a stale `CREATE TABLE`. The live schema is
   the only schema; reading DDL from source was the error.

3. **A system directive is stored as `role='user'`.** Verification must
   exclude it or the composer's own prompts become narrator testimony.

4. **The REST chat path mints ownerless sessions today** (`api.py:799-800`,
   `add_turn` with no `person_id`). Recorded as a defect. Not fixed here.

5. **19 of 1,487 existing turns are attributable.** Go-forward coverage on the
   WebSocket path is sound; the archive is not retrospectively verifiable and
   WO-03A does not pretend otherwise.

## What landed

`0059_answer_provenance.sql`; `services/answer_provenance.py`; provenance
written inside `_write`'s existing `BEGIN IMMEDIATE`; `POST
/questionnaire/answer` and `POST /questionnaire/narrator-answer`;
`API.BB_QQ_ANSWER` with the hint threaded `_saveSection` /
`_addRepeatEntry` → `_persistDrafts` → `_persistQuestionnaire`; the
provenance lane in `narrator_data_inventory` (AUTHORITATIVE, portable —
unlike 0058, because where an answer came from is part of what the
biography means); the B6 read repair.

23 provenance tests, 3 client routing sequences, 5 seed tests. 13 server
mutations and 3 client mutations, all caught, none survived. All 17 node
suites and the questionnaire/seed python suites green.

Four stale test files repaired along the way, three of which had been dark
since earlier work — two sliced source by string markers that later
renames removed, so they threw instead of testing; two matched exact
argument lists and failed against correct code. Detailed in the commit
message.

## Carried to WO-03B

Propose/accept and the review control. Routing `_syncIdentityToBB` and
`_syncPrefillIfBlank` through propose. Until then they write no provenance
and read as `unknown`.

## Recorded, not fixed here

The REST chat path (`api.py:799-800`) calls `add_turn` with no
`person_id` and none in `meta`, so it still mints ownerless sessions
today. Turns written through it can never be verified. Changing a turn
writer does not belong inside a provenance work order.
