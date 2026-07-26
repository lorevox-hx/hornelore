# WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01

**Status:** Phase 0 complete (recon + plan). Phase 1 shipped AND RUN against
the live database -- result below. Phases 2+ NOT started; they wait on the
operator's identity decision, which the Phase 1 measurement now informs.

**Opened:** 2026-07-26
**Predecessor:** WO-TRAVEL-DOC-UNIFY-01 (closed 2026-07-25),
WO-HARNESS-DEPS-01 (closed 2026-07-26), WO-DOC-RECONCILE-01 (closed 2026-07-26)
**Epic:** Travel Doc Import, Review, Lori, and Export -- work order 1 of 8

> Naming note: the work order name comes from the operator's Epic Plan
> document verbatim. Phase numbering below is Claude's proposal and is
> open to renumbering.

---

## Goal

Create the shared backend foundation for future imports, review queues, and
export traceability: a way to record where evidence came from, what Lorevox
thinks it matches, why it thinks that, and what the operator decided.

Google Photos Picker (WO-3), Google Takeout (WO-4), upload hardening (WO-8)
and the Evidence Review Queue (WO-2) all need the same landing zone. Without
it each one invents its own tracking shape.

## Scope wall

In scope: backend and data foundation. Minimal frontend only where a
verification surface is required.

Out of scope, explicitly: Google OAuth, any Takeout parser, any Lori
behaviour change, any export feature, any narrator-facing change.

---

## Phase 0 -- recon (2026-07-26)

Read-only survey of the repository before any design. Findings below are
cited to file and line so a reviewer can check them without re-deriving.

### F1 -- the foundation is greenfield

`grep -rn "import_batch\|import_candidate"` across `*.py`, `*.js` and `*.md`
returns nothing. No prior art, no partial implementation, no abandoned
branch to reconcile. The next migration number is **0037**
(`server/code/db/migrations/` runs 0001..0036).

### F2 -- THE IDENTITY FAULT LINE (the central finding)

Two columns name the same human, and nothing in the schema says they must
agree.

| Column | Defined | Constraint |
|---|---|---|
| `photos.narrator_id` | `0001_lori_photo_shared.sql:15` | `TEXT NOT NULL` -- **no FOREIGN KEY** |
| `trips.person_id` | `0034_trips_person_id_fk.sql` | `TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE` |

The application equates them by convention. `routers/trips.py:702`:

```python
narrator_id = req.narrator_id or trip.get("person_id")
```

and hands that value straight to `_photos_for_narrator()`
(`routers/trips.py:332-345`), which filters `photos WHERE narrator_id = ?`.
The same `narrator_id=person_id` substitution appears at
`routers/trips.py:500`, `routers/chat_ws.py:933`, `routers/chat_ws.py:1839`,
`routers/people.py:190` and `routers/people.py:577`.

So the entire application rests on an unstated invariant:

> one row in `people` == one narrator == one photo owner

There is **no schema constraint** behind it. `people` is a flat table
(`api/db.py:371-379`: id, display_name, role, date_of_birth,
place_of_birth, created_at, updated_at) with no alias column, no canonical
pointer, and **no person-merge tooling anywhere in the repository**.

### F3 -- the invariant is already violated in live data

Backlog item 8 (promoted from WO-TRAVEL-DOC-UNIFY-01 Phase 6 Finding 4)
records two `people` rows reading as one narrator:

* `e7fdb578` -- `Christopher`
* `a4b2f07a` -- `Christopher Todd Horne`

### F4 -- photo links are not owner-scoped either

`trip_photo_links.photo_id` (`0015_trip_tables.sql:90`) is `TEXT NOT NULL`
with **no REFERENCES clause**. The unique index is `(trip_id, photo_id)`
(`:110`) -- scoping is by trip, never by owner. A link can point at a photo
belonging to a different narrator, or at a photo id that does not exist, and
nothing in the schema catches it.

### F5 -- the present-tense defect this already causes

If a trip is keyed to `e7fdb578` but the photos were uploaded under
`a4b2f07a`, `_photos_for_narrator()` returns an **empty list**. Photo
clustering does not raise. It reports a successful run with zero matches.

That is a live defect today, not merely a risk to the epic. It fails
silently, which is the worst available failure mode for an evidence tool.

### F6 -- why this blocks WO-1 specifically

The Epic Plan defines `import_candidate` carrying **both** `person_id` and
`photo_id`. That single row therefore straddles the fault line: its
`person_id` comes from the trips namespace and its `photo_id` points into a
table keyed by the photos namespace. Building the provenance foundation on
top of an unenforced, currently-violated invariant means every future
import, every review decision and every export trace inherits the split.

This is the reason WO-1 goes first in the epic, and it is the reason WO-1
cannot start with the migration.

### F7 -- the reversible-hidden precedent to follow

`0036_trip_evidence_hidden.sql` established the repo's reversible-hide
pattern: `hidden INTEGER NOT NULL DEFAULT 0` + `hidden_at TEXT` + an index
on `(trip_id, hidden)`, with physical purge only behind an explicit
double-confirmation. The Epic Plan's `import_candidate.review_status`
includes `hidden`. It should reuse this pattern rather than invent a second
shape for the same idea.

### F8 -- mechanics confirmed

* Migration runner: `server/code/db/migrations_runner.py`. Lexical order,
  `schema_migrations` tracking table, each file in its own transaction via
  `executescript`, failure leaves no tracking row so the next boot retries.
* Migration test pattern: temp sqlite file + `executescript` of the specific
  migration, then patch `db.DB_PATH` (`tests/test_trip_import.py:27-56`).
  Existing examples: `tests/test_c1_trips_person_id_fk_migration.py`,
  `tests/test_migration_0018_0021_atomic.py`.
* Feature flags: `server/code/api/flags.py`, env-var driven, default OFF.
* pytest is not installed; suites run under `python3 -m unittest`.

---

## The decision this work order needs

**Which identity key does `import_candidate` use, and is it enforced?**

Three options, with the trade the operator is actually choosing between:

**Option A -- match the status quo.** `import_candidate.person_id` with
`REFERENCES people(id) ON DELETE CASCADE`. Treat `photos.narrator_id` as the
same namespace and write that assumption down. Cheapest. Leaves F2/F4
unenforced, so the new table is correct while the tables it points at are
not.

**Option B -- turn the invariant into a schema guarantee.** Option A, plus
add the missing FK on `photos.narrator_id -> people(id)` and on
`trip_photo_links.photo_id -> photos(id)`. This is the same move
`0034_trips_person_id_fk.sql` made for trips, using the same documented
SQLite table-rebuild pattern. It converts a silent split into a loud,
blocking failure at migration time.

The cost is real and should not be soft-pedalled: SQLite cannot
`ALTER TABLE ... ADD FOREIGN KEY`, so this rebuilds `photos` -- a table with
live data and eight indexes. If photos exist under a `narrator_id` with no
`people` row, the migration fails and the stack does not come up until the
data is reconciled. 0034 hit exactly this and needed a rev 3 and a companion
0035 to recover.

**Option C -- defer.** Build `import_candidate` with `person_id` and no FK,
decide later. Fastest to the queue in WO-2. It also means the first thing
the epic builds is the first thing that will need migrating again.

**Claude's recommendation, now that the measurement is in: B, plus a separate
decision on the two Christopher rows before any import runs.**

The measurement removed the reason to hesitate on B. Every orphan count in the
live database is zero (R4), so the rebuild has nothing to trip over and the
0034-class failure that made B expensive is not in the current data. B is also
the right end state on the merits: the whole epic is a provenance system, and a
provenance system whose identity key can silently disagree with itself is not
one.

But B is only half the answer, and the smaller half. The FK closes the
dangling-reference failure; the Christopher split is a wrong-reference failure
and survives B untouched (R6). R2 is the part that should drive sequencing --
new photo activity is landing on `e7fdb578` while every trip lives on
`a4b2f07a`. Import Provenance is precisely the feature that turns that from a
tidiness problem into a data problem, because it writes a durable `person_id`
onto every candidate row it creates. Provenance recorded against the wrong
Christopher is worse than no provenance, because it looks correct.

**The decision the operator owns, in the order it matters:**

1. **The two Christopher rows** -- merge onto `a4b2f07a` (which holds the
   trips, the photo sessions and the older library), keep them separate
   deliberately, or add a canonical pointer. This blocks the first import, not
   the migration.
2. **A / B / C for `import_candidate`** -- with B now measured as safe.

A note, not a fourth option to decide today: if a merge is chosen, the cheap
shape is a `merged_into` column on `people` plus resolution at read time,
because it is reversible. A physical row move across five owner-keyed tables is
not.

---

## Phase plan

### Phase 1 -- identity pre-flight (READ-ONLY) -- DELIVERED 2026-07-26

Ship a read-only audit that measures the fault line in the live database, so
the Option A/B/C decision is made against facts rather than against the two
person ids in a Phase 6 note.

**Delivered:** `scripts/audit_identity_preflight.py`.

Opens the database with SQLite's `mode=ro` URI flag -- it cannot create a
file, cannot upgrade to a writer, and writes nothing anywhere. Resolves the
database path exactly as `api/db.py` does (`DATA_DIR`/db/`DB_NAME`, real
environment first then `.env`), with `--db` to override.

Reports five sections:

1. every `people` row;
2. duplicate-name **clusters**, with the rows each member actually owns --
   a cluster is only flagged `SPLIT CARRIES DATA` when more than one member
   has real narrator activity (`profiles` is excluded from that test, since
   `db.py` creates one profile row per person and it would make every
   cluster look loaded);
3. row ownership per table across `photos`, `photo_sessions`, `bio_facts`,
   `story_candidates`, `trips` and `profiles`, flagging any owner id with no
   `people` row;
4. **`trip_photo_links` crossing owners** -- links whose `photo_id` has no
   `photos` row, and links where `photos.narrator_id <> trips.person_id`.
   This is the query that decides the whole work order;
5. per trip, how many photos clustering would actually see -- naming any
   trip that would cluster against an empty set.

Exit codes: `0` clean, `1` split detected, `2` database unreachable.

**Verified:** `ast.parse` clean. Dry-run against the in-repo
`data/db/lorevox.sqlite3` returns `CLEAN` / exit 0 -- correctly ignoring 13
placeholder rows all named `Test` that carry a profile row each and no
narrator activity. That stale fixture is not the live database and proves
only that the script runs and that its noise filtering works.

**RUN 2026-07-26 -- and it did not need the operator after all.** Every prior
session recorded the live database as unreachable. That is no longer true:
`C:\hornelore_data` is now a connected folder alongside `C:\Users\chris\hornelore`,
so the database could be copied into the container and read there. The audit
ran against a byte-identical copy (`md5 fddf635a7526aa960495deb30d1ed65c`,
verified against the device before and after), opened `mode=ro`. The live file
was never opened by this session, and nothing was written to
`C:\hornelore_data` at any point.

### Phase 1 result -- IDENTITY SPLIT DETECTED (exit 1)

**R1 -- the Christopher split is real, and both halves carry data.**

| id | name | rows owned |
|---|---|---|
| `a4b2f07a` | Christopher Todd Horne | 13 photos, 6 photo_sessions, 3 story_candidates, **2 trips** |
| `e7fdb578` | Christopher | 6 photos, **9 bio_facts** |

Neither is a stub. Backlog item 8 called this "harmless while trips are
created by hand"; that reading holds only because of where the rows happen to
sit, not because anything prevents the split.

**R2 -- the split is actively widening, and it is widening the wrong way.**

The 13 photos on `a4b2f07a` were all uploaded on or before 2026-07-13. The 6
photos on `e7fdb578` were uploaded **2026-07-25, 03:33 to 23:31** -- during the
Phase 5/6 smoke sessions, and they are the same six rows backlog item 5 records
as smoke residue.

So the id receiving new photo activity is the id that owns **zero trips**, and
the id owning every trip has received no photo since 2026-07-13. This is not a
historical artifact that has settled. It is a live divergence, and the next
photo import lands on the wrong side of it by default.

**R3 -- the predicted failure has not fired yet, by placement rather than by
design.** Section 4 is clean: 0 links whose `photo_id` has no `photos` row, 0
links where `photos.narrator_id <> trips.person_id`. Section 5: 0 of 2 trips
would cluster against an empty set. All 13 linked photos and both trips sit on
`a4b2f07a`, so the namespaces have not yet been asked to disagree. F5 stands as
written -- one trip created under `e7fdb578` and it fires.

**R4 -- Option B would succeed today. That window is open now and is not
guaranteed to stay open.** Every orphan count is zero: `photos -> people` 0,
`trip_photo_links -> photos` 0, and `photo_sessions` / `bio_facts` /
`story_candidates -> people` 0. The FK-adding rebuild that F2/F4 describe has
nothing to trip over in the current data. This is the single most useful thing
the audit returned, because it converts Option B from "unknown blast radius"
into "known safe as of this row set."

**R5 -- five of the six flagged clusters are harness residue, not narrator
splits.** `Walt` x7 (15 bio_facts and 3 story_candidates on every one of the
seven), `Trip Canary Narrator (Spring 2026)` x5, `Trip Canary Narrator (2019
France Italy)` x4, `Esteban Garcia` x3, `Kent Horne (factual-chain harness)`
x3. Each harness run mints a fresh `people` row and rewrites the same facts
against it. They are noise for the identity decision -- but they are worth
naming for two reasons: `people` is now 37 rows of which roughly two thirds are
test residue, and **nothing in the data distinguishes a harness duplicate from
a real split.** Both look like "same name, several ids, all carrying rows."

**R6 -- what the FK does not fix.** Both Christopher rows are valid `people`
rows. A foreign key stops a reference pointing at *nothing*; it does not stop a
reference pointing at *the wrong one of two real rows*. Option B closes F2/F4
and leaves the Christopher question entirely untouched. Any claim that adding
the FKs "fixes the identity problem" would be false, and this spec should not
be read as making it.

Closing the Christopher question needs one of: a person merge (move
`e7fdb578`'s 6 photos and 9 bio_facts onto `a4b2f07a` and retire the row), or a
canonical pointer on `people` so both ids resolve to one narrator. **No merge
tooling exists in the repository.** Whichever is chosen is its own piece of
work, and it should land before the first import writes provenance rows, not
after.

### Phase 1.1 -- resolve the two Christopher rows (BLOCKS the first import)

Not started. Needs the operator's decision above before it can be specified.
Whatever shape it takes, it is a data/identity change and belongs in its own
session with its own before/after audit run -- the Phase 1 script is the
before/after instrument and should be re-run on both sides of it.

### Phase 2 -- migration 0037 (BLOCKED on the identity decision)

`import_batch` and `import_candidate` per the Epic Plan's field list, keyed
per the Option A/B/C decision, with `hidden`/`hidden_at` following F7.
Includes the FK hardening if and only if Phase 1 shows it is safe, or shows
what must be reconciled first.

### Phase 3 -- repository layer

`services/import_repository.py` plus its unit suite. Enforces the Epic
Plan's rules at the write path: import is intake not approval; candidate
creation implies neither memoir inclusion nor narrator-ready; candidates
cannot cross the person/trip boundary; no raw external tokens in candidate
rows; `match_reasons_json` round-trips.

### Phase 4 -- minimal verification surface

Operator-only list/create/decide endpoints -- the least UI that lets the
Phase 5 smoke happen. Not the Evidence Review Queue; that is WO-2.

### Phase 5 -- live smoke

The Epic Plan's smoke list: disposable trip, fake batch, fake candidates,
list, accept one, skip one, hide one, and confirm nothing became
narrator-facing or memoir-approved.

---

## Standing rules carried into this work order

* No native `prompt` / `confirm` / `alert` on any operator path.
* No DELETE on evidence lanes -- reversible hide only.
* Travel Documenter is the operator tool; the Travels shelf is the
  narrator/Lori surface. Their state does not mix.
* One phase per session.
* Import is intake. The human approves what becomes memory.

---

## Revision history

- 2026-07-26 -- Work order opened. Phase 0 recon complete: eight findings,
  the central one being that `photos.narrator_id` and `trips.person_id` name
  the same human with no schema constraint requiring agreement, no
  person-merge tooling, an invariant already violated in live data by the
  two Christopher rows, and a silent-empty-result failure mode in photo
  clustering today. Phase 1 delivered
  `scripts/audit_identity_preflight.py`, a read-only (`mode=ro`) audit that
  measures the split in the live database; it is `ast.parse` clean and
  returns CLEAN/exit 0 against the stale in-repo fixture, correctly ignoring
  13 placeholder rows. Phase 1 cannot be completed by an agent -- the live
  database is outside the repository and unreachable from both filesystems
  an agent has -- so the operator runs it and returns the output. Phases 2+
  are blocked on that output and on the Option A/B/C identity decision,
  which is the operator's. No schema, code, test, flag or UI change was made
  in this session.
- 2026-07-26 -- Phase 1 RUN against the live database, which turned out to be
  reachable after all: `C:\hornelore_data` is now a connected folder, so the
  database was copied into the container (md5-verified both directions) and
  read `mode=ro` there. Verdict: IDENTITY SPLIT DETECTED, exit 1. Results R1-R6
  added above. The headline results are that the Christopher split carries real
  data on both sides and is actively widening the wrong way -- all six photos
  added on 2026-07-25 went to `e7fdb578`, which owns zero trips, while both
  trips and all thirteen linked photos sit on `a4b2f07a`; that the crossing-link
  and empty-cluster queries are both clean today, so the F5 failure has not
  fired yet and has not fired only because of where the rows happen to sit; and
  that every orphan count is zero, so Option B's FK rebuild would succeed
  against the current data. Recommendation revised accordingly: B is now
  measured-safe, but it is the smaller half -- a foreign key cannot fix a
  reference that points at the wrong one of two valid rows, so the Christopher
  question is promoted to Phase 1.1 and blocks the first import rather than the
  migration. Still no schema, code, test, flag or UI change in this session.
