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

**Both decisions were made by the operator on 2026-07-26. Neither is open.**

1. **The two Christopher rows -- DECIDED: delete `e7fdb578`, keep
   `a4b2f07a`.** Not a merge, not a canonical pointer, not a `merged_into`
   column, and explicitly not person-merge tooling. `a4b2f07a`
   (`Christopher Todd Horne`) holds both trips, all thirteen linked photos, the
   photo sessions and the older library, so it survives untouched; `e7fdb578`
   (`Christopher`) is treated as bad seed and removed with its dependent rows.
   The operator's words: *delete just the other one and keep Christopher Todd
   Horne*. See Phase 1.1 below for what that cost in rows.
2. **A / B / C for `import_candidate` -- DECIDED: Option B**, which Phase 1
   measured as safe (every orphan count zero). Landed as migration 0037.

**Scope wall, stated by the operator and binding on every later session:** the
deletion is the unblocker, not the project. No merge tooling, no canonical
pointer, no general duplicate-person cleanup, no Walt/Test/Kent harness
cleanup, no identity-architecture expansion. *Do not spend another session on
identity architecture.*

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

Closing the Christopher question therefore had to happen outside the
migration, and it did -- by deletion rather than by reconciliation. `e7fdb578`
and its dependent rows are removed; `a4b2f07a` is the single Christopher
identity the epic keys against. **No merge tooling exists in the repository and
none was written**, which is deliberate: a merge would have been a new
subsystem, and the operator ruled that out in favour of the cheaper reset. R6
still stands as a general statement -- an FK cannot fix a wrong-reference
failure -- but the specific wrong reference it described no longer has two
targets to choose between.

### Phase 1.1 -- resolve the two Christopher rows (EXECUTED AGAINST THE LIVE DATABASE 2026-07-26)

**Decision: delete `e7fdb578-5563-479f-8951-aab764faa6d8` (`Christopher`) and
every dependent row it owns. Keep `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2`
(`Christopher Todd Horne`) untouched.**

Delivered as `scripts/wipe_narrator_identity.py`, gated so that it cannot be
pointed anywhere else:

- **Allowlist refusal.** `ALLOWED_TARGETS` contains exactly one id.
  `PROTECTED_IDS` contains `a4b2f07a` plus Kent, Janice and Melanie Zollner.
  Anything else exits 1 without opening a write connection.
- **Delete by id, never by name.** The display name is an *abort-only*
  condition -- if the row's name does not match what the allowlist expects, the
  script refuses. It is never used as a selector. This is required safety rule
  4 and it is enforced in code, not by convention.
- **`--commit` requires `--i-acknowledge` *and* a `--backup` file** that passes
  `PRAGMA integrity_check` and still contains the target row.
- **Deletion delegates to the application's own `hard_delete_person()`** rather
  than to hand-written SQL, so the 14 non-FK person-scoped tables, the FK
  cascades, the `narrator_delete_audit` row and the KAWA directory removal all
  follow the path the product already uses.
- Modes: default dry-run/report, `--commit`, `--verify-only`. Exit 0 clean /
  1 refused-or-failed / 2 DB unreachable.

**Rehearsed end to end on throwaway copies of the live database** -- dry run,
commit, verify-only, then a preflight re-run -- exit 0 at every step. Full
transcript at `docs/reports/christopher_wipe_rehearsal_20260726.console.txt`.

**Then RUN LIVE by the operator on 2026-07-26**, against
`/mnt/c/hornelore_data/db/hornelore.sqlite3`, backup
`backup_pre_christopher_wipe_20260725_205530.sqlite3` (`integrity_check ok`,
verified to still contain the target row before the delete was allowed to
proceed). Live transcripts:
`docs/reports/christopher_wipe_dryrun_live.console.txt`,
`christopher_wipe_commit_live.console.txt`,
`christopher_wipe_verify_live.console.txt`,
`identity_preflight_after_wipe_live.console.txt`.

The live run reproduced the rehearsal **exactly** -- the same 21 dependent rows
across the same seven tables, the same four protected narrators with the same
121 / 51 / 41 / 5 dependent-row totals, the same clean orphan sweep. Live
result: `status: hard_deleted`, people row gone **YES**, residue **0**, orphan
sweep **CLEAN**, all four protected narrators **OK**, and section 4 of the
verify pass now lists exactly one Christopher row --
`a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2`. **`VERIFY: CLEAN`, exit 0.** Phase 1.1
is closed.

**One safety event worth recording, because the gate is the point.** On the
first attempt the operator passed the literal placeholder string `BACKUP_PATH`
rather than the backup's real path. The script printed its full impact report,
then **refused** -- `REFUSED: backup file does not exist: BACKUP_PATH` -- before
opening any write connection. The `--backup` requirement is not decoration; it
caught a real paste error on a real destructive run.

**Before/after counts (required safety rule 10).** 21 dependent rows destroyed
under `e7fdb578`:

| Table | Rows removed |
|---|---|
| photos | 6 |
| bio_facts | 9 |
| consent_attestations | 2 |
| profiles | 1 |
| interview_sessions | 1 |
| interview_projections | 1 |
| bio_builder_questionnaires | 1 |

Global totals across the whole database:

| Table | Before | After |
|---|---|---|
| people | 37 | 36 |
| photos | 22 | 16 |
| bio_facts | 123 | 114 |
| profiles | 37 | 36 |
| consent_attestations | 2 | 0 |
| interview_sessions | 61 | 60 |
| interview_projections | 13 | 12 |
| bio_builder_questionnaires | 13 | 12 |
| trips | 2 | 2 |
| trip_photo_links | 13 | 13 |
| trip_photo_context | 51 | 51 |
| photo_sessions | 7 | 7 |
| story_candidates | 75 | 75 |
| narrator_delete_audit | 52 | 53 |

Residue for the deleted id: **0** across all 29 person-scoped `(table, column)`
pairs. Orphan sweep CLEAN. `PRAGMA foreign_key_check` **empty**. All four
protected narrators intact with **unchanged** dependent-row totals -- `a4b2f07a`
121, Janice 51, Kent 41, Melanie 5 -- which is the direct evidence for required
safety rule 6. The `narrator_delete_audit` table survives the delete and records
it (52 -> 53).

**An honest limitation, recorded rather than engineered around.**
`scripts/audit_identity_preflight.py` still exits **1** after a perfect wipe.
Its verdict is global: it fires whenever *any* duplicate-name cluster carries
activity on more than one id. Before the wipe, six clusters qualified; after,
five -- Walt x7, Trip Canary x5 and x4, the Kent harness cluster, and Esteban x3.
Confirmed live: the post-wipe preflight prints *5 duplicate-name cluster(s)
carry narrator activity on more than one id* and exits 1, with `people` down
from 37 rows to 36.
Every one of those is smoke-test residue that the operator has explicitly
forbidden cleaning. Within its own sections the preflight is green on the thing
Phase 1.1 owns: the Christopher cluster is gone from section 2, section 4 shows
0 missing-photo links and 0 crossing links, and section 5 shows 0 of 2 trips
clustering empty. **The preflight was deliberately NOT modified** -- changing
its verdict logic would be exactly the identity-architecture expansion the scope
wall forbids. **The Phase 1.1 gate is therefore
`wipe_narrator_identity.py --verify-only`, which exits 0.**

Rule 9 -- creating one clean Christopher record afterward -- is not needed:
`a4b2f07a` is retained and is already that record.

### Phase 2 -- migration 0037 (LANDED AND VERIFIED LIVE 2026-07-26)

`server/code/db/migrations/0037_import_provenance_foundation.sql`, Option B,
built on `0034`'s two-phase FK-rebuild precedent (PRAGMA statements outside
`BEGIN`; the orphan `DELETE` runs with foreign keys **ON** so cascades fire; the
table rebuild runs with them **OFF**; then re-arm and `PRAGMA
foreign_key_check`). `0034`'s rev-1 bug -- deleting with FKs off -- is not
repeated.

**Part A, FK hardening.** A1 sweeps orphans in dependency order (orphan
`photos` first so cascades fire, then dangling `trip_photo_links`, then dangling
`trip_photo_context`). A2 rebuilds `photos` with
`narrator_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE`, all 33
columns carried verbatim through an explicit column-list `INSERT ... SELECT`,
5 indexes recreated. A3 rebuilds `trip_photo_links` with
`photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE`, preserving the
existing trips/trip_regions/trip_stops/trip_days foreign keys, 6 indexes
recreated including the UNIQUE `(trip_id, photo_id)`. This closes F2 and F4.

**Applied to the live database 2026-07-26 at 02:54:47** by the runner on
stack start, recorded in `schema_migrations`. Read-only verification against
the live file confirms both new FKs present with CASCADE, `import_batch` and
`import_candidate` present with all six FKs correct, `PRAGMA foreign_key_check`
**empty**, `integrity_check ok`, `import_candidate` at 25 columns with
`narrator_ready`, `include_in_memoir`, `access_token` and `refresh_token` all
**absent**, and row counts matching the predicted post-wipe state exactly
(people 36, photos 16, trip_photo_links 13, import_batch 0,
import_candidate 0). Note the ordering: 0037 landed at 02:54, the Phase 1.1
wipe ran at 03:00, so `hard_delete_person` cascaded **through** the new
`photos.narrator_id` foreign key rather than around it -- the stronger path --
and came out with `foreign_key_check` empty.

**Part B, the landing zone.** `import_batch` (18 columns, 3 indexes) and
`import_candidate` (25 columns, 6 indexes including UNIQUE
`(batch_id, external_id)`), both carrying the reversible `hidden`/`hidden_at`
pattern established by `0036`. `import_candidate.photo_id` is
`ON DELETE SET NULL`, not CASCADE: losing a photo must not silently destroy the
provenance record of how it arrived.

**Verified through the operator path, not only the schema.** Schema checks
cannot prove that a rebuilt table still *serves* the UI -- that every column the
API reads survived the explicit-column-list `INSERT ... SELECT`, that the
indexes still back the queries, that the UNIQUE `(trip_id, photo_id)` did not
silently drop a link. A read-only pass against the running stack closed that
gap: both of Christopher Todd Horne's trips list, `/photo-links` returns **13
links, 13 distinct `photo_id`, 0 null**, matching `trip_photo_links` exactly;
the chain `trip_photo_links.photo_id -> photos.id -> photos.narrator_id ->
people.id` resolves end to end and terminates on the surviving Christopher;
`/thumb` and `/image` both serve `image/jpeg`; memoir-preview,
travelogue-preview, narrator-photo-links, date-confirmations, sources, tree and
days all 200; the Photos tab renders `All (13) / Unplaced (4) / Needs review
(4) / Shared with Lori (1)` with thumbnails and date chips; and the console is
clean -- zero uncaught exceptions, zero failed fetches, zero 4xx, zero 5xx. The
narrator picker shows **exactly one Christopher**, which is Phase 1.1 confirmed
on the surface that made the split visible in the first place. Transcript at
`docs/reports/phase2_ui_verification_live.console.txt`. Nothing was written
during the pass -- no POST, no PATCH, no DELETE, no upload, no cluster run.

**Intake is not approval, enforced by absence.** `import_candidate` has **no**
`narrator_ready` column and **no** `include_in_memoir` column. The absence *is*
the enforcement -- a column that does not exist cannot be set by a future
import path that forgets the rule. It also carries no token or credential
columns of any kind. `tests/test_import_provenance_foundation_migration.py`
asserts all of this directly, including that setting `state='accepted'` flips no
photo flag.

**Proof.** 37 new tests, all green. The migration was applied through the real
`run_pending_migrations` runner against two copies of the live database -- one
pre-wipe, one post-wipe -- with zero row loss across all seven photo/link
tables, both new FKs present with CASCADE, `foreign_key_check` **empty**,
`integrity_check` **ok**, 20 indexes present, and a second run a clean no-op.
Regression-tested across the 20 affected suites: **539 tests, OK (skipped=6)**.

### Phase 3 -- repository layer (LANDED 2026-07-26)

`server/code/api/services/import_repository.py` plus its unit suite. Note the
path: there is no `services/` directory at the repository root -- the import
repository lives beside `trip_repository.py` in `server/code/api/services/`,
and earlier drafts of this spec said otherwise.

**What the module is for.** Migration 0037 states four rules in the only
language a schema has, which is the presence and absence of columns and
constraints. Three of those rules a schema cannot state at all. `import_batch`
carries `person_id` and `trip_id` as independent foreign keys, so nothing in
SQLite stops a batch owned by one person from pointing at another person's
trip -- that is exactly the class of confusion the two Christopher rows
produced. Nothing stops an OAuth access token from being pasted into
`external_ref`, which is a plain `TEXT` column. And the absence of
`narrator_ready` prevents a column from being set, but cannot prevent a future
import path from reaching sideways into `photos` and setting it there. Phase 3
is where those rules become procedure.

**Rule 1 -- import is intake, not approval.** `candidate_create` takes no
`state` parameter and no approval flag of any kind; every candidate is born
`pending`. `candidate_decide` is the only way a candidate leaves that state,
and `'accepted'` **requires** a `photo_id` that already exists and is owned by
the candidate's person -- the repository never creates a photos row, so
accepting records a decision about a photo the operator already has rather than
manufacturing one. Every other decision (`rejected`, `duplicate`, `error`)
**refuses** a `photo_id`; `'pending'` is not a decision. A runtime guard runs
`PRAGMA table_info(import_candidate)` on every write and raises if
`narrator_ready` or `include_in_memoir` has appeared, so if a later migration
adds the column the schema's silence is no longer load-bearing and the
repository says so out loud.

**Rule 2 -- the person/trip boundary.** A candidate does not accept a
`person_id`; it copies its batch's. A batch cannot be created on, or bound to,
a trip belonging to someone else. A candidate cannot claim a trip its person
does not own, and cannot disagree with the trip its batch is already bound to.
Accepting refuses a photo belonging to another person. `candidates_list`
filtered by person never returns another person's rows.

**Rule 3 -- no raw external tokens.** Every operator-supplied string is scanned
before it is written: Google OAuth access (`ya29.`) and refresh (`1//`) tokens,
GitHub tokens, OpenAI keys, JWTs, `Bearer` headers, and credential-bearing
query strings, plus a key-name check over `match_reason` that recurses to a
bounded depth. The scan is calibrated, not merely loud -- real Google Photos
media ids and real Takeout archive filenames pass, which is the test that keeps
the guard from becoming something a future author disables.

**Rule 4 -- reversibility.** The module contains no `DELETE FROM` and no
`DROP TABLE`; a test reads its own source and asserts that. Hiding is a flag,
and hidden rows still count toward batch totals. Counters are **recomputed**
from the candidate rows on every state change rather than incremented, so a
replayed decision cannot drift them.

**Idempotence.** `candidate_create` honours 0037's UNIQUE
`(batch_id, external_id)` by returning the existing id rather than raising, so
re-running the same fetch adds nothing and the first write wins.

**Proof.** 50 new tests, all green, in six classes matching the four rules plus
batch lifecycle and boundary enforcement -- including that a person hard-delete
cascades the whole landing zone through 0037's foreign keys, which is why
`import_batch` and `import_candidate` do **not** need adding to
`hard_delete_person`'s explicit table list. The 0037 migration lock re-ran
clean at 37 tests. Test baseline 279 -> 329.

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
- 2026-07-26 -- **Phase 1.1 tooling delivered and rehearsed; Phase 2 landed.**
  The operator closed both open decisions: delete `e7fdb578` and keep
  `a4b2f07a` (no merge, no canonical pointer, no merge tooling), and Option B
  for `import_candidate`. `scripts/wipe_narrator_identity.py` is a single-target
  allowlisted deleter that refuses on display name rather than selecting by it,
  requires a verified backup before `--commit`, and delegates the delete to the
  application's own `hard_delete_person()`. Rehearsed four ways on throwaway
  copies of the live database, exit 0 throughout: 21 dependent rows destroyed,
  residue 0, orphan sweep clean, `foreign_key_check` empty, all four protected
  narrators' dependent-row totals unchanged. The honest caveat is recorded in
  Phase 1.1 above -- `audit_identity_preflight.py` still exits 1 on five
  forbidden-to-clean harness clusters, so `--verify-only` is the gate instead,
  and the preflight itself was deliberately left alone. Migration 0037 adds the
  two missing foreign keys and creates `import_batch` and `import_candidate`
  with `hidden`/`hidden_at`, no `narrator_ready`, no `include_in_memoir` and no
  token columns; 37 new tests green, 539 green across the affected suites, and
  the migration verified idempotent against real data. **The destructive run
  itself belongs to Chris** -- the deliverable is the tooling plus a WSL run
  block, never an agent-side write to the live database.
- 2026-07-26 -- **Phase 3 landed: the import repository.**
  `server/code/api/services/import_repository.py` (ASCII-only, `ast.parse`
  clean) plus `tests/test_import_repository.py`, 50 tests green. The module
  holds procedurally the three rules a schema cannot state: a candidate copies
  its batch's person rather than accepting one, and no batch or candidate may
  reach a trip or photo belonging to someone else; every operator-supplied
  string is scanned for OAuth/JWT/bearer/credential-URL shapes before it is
  written, while real Google Photos media ids and Takeout archive names still
  pass; and acceptance requires an existing photo owned by the candidate's
  person, with the repository never creating a photos row and never setting an
  approval flag. It contains no `DELETE FROM` and no `DROP TABLE`, asserted by
  a test that reads its own source. Counters are recomputed, not incremented.
  `candidate_create` is idempotent on `(batch_id, external_id)`. A runtime
  `PRAGMA table_info` guard fires if `narrator_ready` or `include_in_memoir`
  ever appears on `import_candidate`, so the schema's silence stops being
  load-bearing the moment it is broken. Two documentation errors corrected
  here: the column is `match_reason_json` (singular), and the module path is
  `server/code/api/services/`, not a nonexistent root-level `services/`.
  Baseline 279 -> 329. **Phase 4 -- the minimal verification surface -- is
  next.**
- 2026-07-26 -- **Phase 2 verified live, schema and UI.** Migration 0037
  applied on stack start at 02:54:47 -- before the 03:00 wipe, so the delete
  cascaded through the new `photos.narrator_id` FK. Read-only checks against
  the live database: both FKs CASCADE, both new tables present with all six FKs
  correct, `foreign_key_check` empty, `integrity_check ok`, forbidden columns
  absent, row counts exact. Then a read-only pass over the running operator
  path: 13 photo links / 13 distinct photos / 0 null, the full
  link -> photo -> person chain resolving onto the surviving Christopher,
  thumbnails and images served, seven downstream trip endpoints 200, and a
  clean console. `docs/reports/phase2_ui_verification_live.console.txt`.
  **Phase 2 is closed at both layers. Phase 3 -- the import repository -- is
  next and is a separate session.**
- 2026-07-26 -- **Phase 1.1 EXECUTED LIVE by the operator.** `VERIFY: CLEAN`,
  exit 0. The live run matched the rehearsal on every number: 21 dependent rows
  across seven tables, people 37 -> 36, residue 0, orphan sweep clean, the four
  protected narrators unchanged at 121 / 51 / 41 / 5, and one Christopher row
  remaining (`a4b2f07a`). The post-wipe preflight exits 1 on the five remaining
  harness clusters exactly as predicted, which is forbidden work and stays.
  A first `--commit` attempt was **refused** because the backup path was still
  the literal placeholder -- the gate fired before any write connection opened.
  **Migration 0037 has not yet touched the live database**; the runner applies
  it on the next `init_db()`, so the next stack start is the moment it lands.
  *(Superseded by the entry above: it applied at 02:54:47 on that next start.)*
