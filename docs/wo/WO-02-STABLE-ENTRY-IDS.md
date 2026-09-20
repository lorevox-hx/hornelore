# WO-02 — stable entry ids for repeatable sections

Plan written 2026-09-20 from a full trace of entry identity across render,
collect, transport, flatten, merge, revisions and every downstream consumer.
Nothing implemented yet. Three decisions below can change stored data and are
flagged for sign-off before execution.

Scope: identity only. Provenance (WO-02/R1), deletion (WO-03B) and the
confirmation model are explicitly out.

## The finding this starts from

**There is no per-entry identifier anywhere in the system.** Every hop
identifies an entry by its array index. The codebase says so itself, at
`questionnaire_persistence.py:75-100` ("KNOWN LIMITATION — POSITIONAL ARRAY
IDENTITY"), where stable ids are named as the fix and deliberately deferred.

Consequences, traced:

  - collect merges DOM index *i* onto stored entry *i* — a reorder
    cross-pollinates fields between two people
  - the PUT sends a bare array with no ids and no `base_fields`, so the
    server cannot tell a reorder from a set of edits
  - `flatten_document` produces `parents[0].occupation`; an insertion at the
    head renames every later path
  - `changed_paths` / `previous_values` in the revisions table are the same
    positional strings, so archived history re-points after a reorder
  - `projection-sync` candidate identity is literally `proj_<section>_<index>`

Two downstream consumers are *index-immune* and fragile in a different way:
the family tree dedupes on lowercased display name, and the graph's
`_stablePersonId` hashes the name — so correcting a spelling forks a new
node. Entry ids would let both key on the entry instead. Out of scope here;
recorded as enabled-by.

## Decision 1 — ids live INSIDE the entry, not in the path

    parents: [ { _entryId: "e_k3x9q7", relation: "Mother", ... }, ... ]

NOT `parents[<id>].occupation`.

Rationale: the server path grammar admits only integers between brackets
(`_SEGMENT`, `questionnaire_persistence.py:131`). An id-keyed path space would
require rewriting `_split`, `_get`, `_set`, `_unset` and `flatten_document`,
plus `projection-map.buildRepeatablePath`, the `test-harness.js` rubric, and
every `changed_paths` row already stored would become unresolvable. That is a
migration of the entire history for a benefit an in-entry field delivers.

With the id in-band, the path space is unchanged, the merge is unchanged, and
a reorder becomes *detectable* — the id at index 0 differs from the id that
was at index 0 — which is what provenance and deletion need.

**This does not make paths stable.** It makes entries identifiable. Path
stability is not achievable without the grammar change, and is not required
by anything in WO-02's scope.

## Decision 2 — minted by the client, lazily, and only persisted when the
   entry is real  ⚠ CHANGES STORED DATA

Where minted:
  - `_addRepeatEntry` pushes `{ _entryId: _uid() }` instead of `{}`
  - the collect path backfills an id for any rendered entry that has operator
    content and no id

`_uid()` already exists (`bio-builder-core.js:1235`), is already used for
candidate and family-tree node ids, and needs no new machinery.

**The data change to sign off:** existing entries have no id. Backfilling
means the next save of a section that already holds entries writes new leaves
— `parents[0]._entryId`, `parents[1]._entryId` — which bumps the revision and
records those paths in `changed_paths`.

For the three family narrators that is: Janice 2 parents + 2 grandparents,
Kent 2 + 2, Christopher 2 + 2 (exact counts to be confirmed by a read-only
probe before execution). It is not a bulk migration — nothing happens until
the operator saves that section for their own reasons — but it is a real
write to a real record, appearing in history as added `_entryId` paths.

Alternatives considered and rejected:
  - *server-side minting on write* — converges all clients on one authority
    and closes the two-tab race below, but requires `merge_whole_document` to
    ADD a leaf the client did not send. That is a change to the write path we
    spent four days stabilising, for a race with one operator.
  - *deterministic ids derived from position* — that is position again.
  - *deterministic ids derived from content* — the name is editable content;
    this is exactly what makes the graph rename-fragile.

**Known limitation, accepted:** two browser tabs rendering the same section
would mint different ids for the same positional entry, and last-writer-wins
with no `base_fields` sent means one tab's ids survive. The server already
implements per-path optimistic concurrency (`base_fields`,
`questionnaire_persistence.py:393-400`) and **no UI client sends it**. Wiring
that up closes this race and several others; it is a small separate item, not
smuggled into this work order.

## Decision 3 — an id alone does not make an entry real  ⚠ AFFECTS SAVE
   SEMANTICS

`flatten_document` (`:219-236`) does not skip bookkeeping keys, so
`{_entryId: "e_abc"}` flattens to a populated leaf and the server would store
it. That reintroduces BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-ASSERTION-01 by a new
route: clicking "+ Add another parent" and saving would file a phantom family
member whose only recorded fact is an identifier.

Rule: **the collect path drops entries whose only populated content is
bookkeeping.** An id is minted at add-time and lives in memory and the local
draft; it becomes durable the moment the entry gains a real answer.

Consequence: an id is not stable across a reload for an entry that was never
filled in. That is correct — a blank entry has nothing to anchor.

`_hasOperatorContent` (`bio-builder-core.js`) already implements exactly this
test, including the container rule from
BUG-BIO-QUESTIONNAIRE-LEGACY-SECTIONS-INVISIBLE-01. Reuse it; do not write a
second one.

The behavioural harness's `leaves()` does not skip bookkeeping keys either
(`bio-builder-harness.js:93-107`). It must mirror whatever the server does,
per the fidelity rule from BUG-QUESTIONNAIRE-NOOP-REPORTED-AS-WRITE-01 — and
since the server keeps flattening them, the double keeps flattening them, and
the suppression is asserted in the browser where it happens.

## Order is preserved, and is still meaningful

Entry order carries real meaning in three places and must not change:

  - `bio_questionnaire_writer.py:198-234` — the FIRST entry whose `relation`
    matches father/mother wins `father_name` / `mother_name`
  - `bio_questionnaire_writer.py:292-313, 573` — `out[0]` supplies
    `spouse_name`, `marriage_year`, `profile_patch["spouse"]`
  - `test-harness.js:248-263` — the rubric hard-codes `parents[0]` = father,
    `parents[1]` = mother, `spouse[0]` / `spouse[1]`

Ids are additive identity, not a replacement for order. Nothing in this work
order changes an order-dependent rule. Worth stating plainly because the
natural next thought — "now that entries have ids, stop relying on position"
— is a separate decision with its own blast radius.

## Implementation, in order

1. `_addRepeatEntry` mints `_entryId` on the pushed entry.
2. Collect backfills an id for any rendered entry with content and no id.
3. Collect drops bookkeeping-only entries before assigning the section.
4. Render emits `data-lv-entry-id` on the entry wrapper — for tests and for
   future per-entry controls. DOM input ids stay `bbQ_<idx>_<field>`;
   changing those would touch the collect probe, the operator-intake tab and
   every existing test for no gain in this work order.
5. `getSectionData` unchanged.

Server: no change. Path space, merge, revisions and the route are untouched.

## Tests — behavioural, in the harness

  - a new entry carries an id; a blank one is not stored
  - an entry's id survives a save / reload / narrator-switch / return
  - two entries have distinct ids
  - reordering two filled entries carries each id with its own values — the
    demonstration that identity now survives what position does not
  - an entry with content but no id (a pre-WO-02 document) gains one on the
    next save, and its values are unchanged
  - existing ids are never regenerated on a subsequent save
  - order is preserved across all of the above

Plus a route-level check that `_entryId` round-trips through
`merge_whole_document` unchanged.

## Sign-off needed before execution

  A. Decision 2 — backfilling ids writes `_entryId` paths into real records
     on the next ordinary save of a section that already holds entries.
     Revision bumps and `changed_paths` rows will show it.
  B. Decision 3 — an entry holding only an id is dropped at collect and never
     reaches the server.
  C. That `base_fields` is NOT wired up here, leaving the two-tab race open
     and recorded.
