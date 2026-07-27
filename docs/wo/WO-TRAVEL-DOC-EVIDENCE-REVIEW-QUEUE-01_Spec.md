# WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01

**Status:** Phase 1 (the queue read) LANDED 2026-07-26 -- repository function,
one route, 56 new tests green, route baseline held at 67. Phase 2 (the screen)
NOT started; it is a separate session. **Three decisions belong to Chris and
two of them block Phase 2.**

**Opened:** 2026-07-26
**Predecessor:** WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 (closed
2026-07-26, all six phases done, live smoke 66/66)
**Epic:** Travel Doc Import, Review, Lori, and Export -- work order 2 of 8

> Naming note: the work order name comes from Chris's Epic Plan document
> verbatim. Phase numbering below is Claude's proposal and is open to
> renumbering.

---

## Goal

Give the operator one screen that answers: *what arrived, where did it come
from, what does Lorevox think it matches, why does it think that, and what am
I going to do about it.*

WO-1 built the landing zone. It can record an import and it can record a
decision, but there is no way to look at the pile. `GET /candidates` is a
table read -- it returns candidate rows and nothing else, so a screen built on
it would have to fetch each candidate's batch and each candidate's trip
separately. A real Takeout import lands hundreds of candidates from a handful
of batches, which makes that an N+1 against the exact shape of the data.

Everything downstream needs this queue to exist first. Google Photos Picker
(WO-3) and Takeout (WO-4) are producers with nowhere to deliver for review.
The Lori Review Assistant (WO-5) is an assistant to a review that has no
surface. Export traceability (WO-6) traces decisions that currently cannot be
made through a UI.

## Scope wall

**In scope:** the read behind the Evidence Review Queue, and later the screen
that shows it. Backend first, UI second, in separate phases.

**Out of scope, explicitly:** Google OAuth and the Picker (WO-3), any Takeout
parser (WO-4), any Lori behaviour change (WO-5), any export feature (WO-6),
any narrator-facing change, and any change to the Travels shelf. The locked
rule still holds -- **Travel Documenter is the operator tool for editing
trips; the Travels shelf is the narrator/Lori conversation surface; their
state does not mix.** The Evidence Review Queue is operator-side.

**Also out of scope:** the two hidden `PHASE5-SMOKE` batches. There is no
DELETE route on either import lane and there is not going to be one here.
Removing those rows is Chris's action, run by Chris, against
`C:\hornelore_data`.

---

## Phase 1 -- the queue read (LANDED 2026-07-26)

### What landed

**One repository function**, `queue_read()`, appended to
`server/code/api/services/import_repository.py`. **One route**,
`GET /api/import-provenance/queue`, appended to
`server/code/api/routers/import_provenance.py`. **One new test module**,
`tests/test_import_provenance_queue.py`, **56 tests, all green**. Baseline
**399 -> 455**.

The import-provenance route surface goes **15 -> 16**. Still **zero DELETE**
on either lane.

`tests/test_import_provenance_routes.py` needed exactly one edit: a new entry
in `FlagGateTests._all_routes()`. That is not bookkeeping --
`test_route_count_is_the_count_the_gate_test_covers` asserts the route set
equals the gate list, so a route added without a flag-off assertion turns the
suite red. It did, and that is the guard working. The new entry is listed
**without its required `person_id`** on purpose: with the flag off the answer
must be 404, not the 422 that would name the missing parameter and thereby
confirm the route exists. That suite still reports **67 tests**, unchanged.

### The four rules this read holds that `candidates_list()` does not

**1. `person_id` is required, not optional.** A review queue with no person is
a cross-person read. The boundary is easier to keep as a required argument
than as a caller's discipline. An unknown person raises rather than returning
`[]`, because *this person has nothing* and *there is no such person* are
different facts and must not share an answer.

**2. A candidate inside a hidden batch is out of the queue even when its own
`hidden` is 0.** Hiding a batch retires the material it landed; a queue that
kept serving its rows would make batch-hide a lie. `include_hidden=true`
brings both kinds back, and every row carries `batch.hidden` so the caller can
tell which kind of hidden it is looking at. Locked by eight tests, including
one that proves **reopening a batch is not the same as unhiding it** --
`status` and `hidden` are different axes and the queue must not conflate them.

**3. `state_counts` covers the whole filtered queue and deliberately ignores
the `state` filter.** Counting only the returned page would report "12
pending" because twelve fit on the page. Counting only the requested state
would report the queue depth as the thing you already asked for. The useful
answer is: you are looking at pending, and here is the shape of the whole
queue behind it. `total` *does* honour the state filter, because that is the
paging denominator.

**4. `match_reason` round-trips verbatim.** Migration 0037 made that column
JSON so the review queue could show the importer's reasoning, not a summary of
it. This is the first caller that displays it and it must not be the place a
summary creeps in. Locked by a test that sends a nested structure and asserts
deep equality both through the API shape and against the stored
`match_reason_json`.

### Shape

Each candidate carries its batch inline (`id`, `label`, `source`, `status`,
`external_ref`, `hidden`, and the three counters) and its trip inline (`id`,
`title`, `start_date`, `end_date`, `status`). The trip's **date window is
there on purpose**: the single most common review question is *does this
photo's `taken_at` fall inside the trip it is filed under*, and a queue that
showed only the trip title would force the reviewer to open the trip to
answer it.

A candidate with no trip gets `trip: null`, not a dict of nulls. "Not filed
yet" is the most common state in this queue and it should read as one thing,
not five.

The join columns are spelled out rather than `SELECT b.*` because
`import_batch`, `import_candidate` and `trips` all have `id`, `person_id`,
`hidden`, `created_at` and `updated_at` -- a star-join would silently let one
shadow another. Two tests exist for exactly that: one asserts no `_b_` / `_t_`
alias leaks into the payload, one asserts the candidate's own `id` is not the
batch's.

Order is **oldest-first, tiebroken on `rowid`**. This is the Phase 4 lesson
applied: `_now()` has whole-second precision, so a single import lands inside
one second and `ORDER BY created_at` alone degrades to uuid order -- which for
a real import is the whole batch. A twenty-candidate test written inside one
second pins it, and a second test proves the order survives paging.

### What Phase 1 deliberately is not

It is a **read**. It sets nothing, decides nothing, and materializes no photo.
Four tests assert this directly: the database is byte-unchanged across a
queue read, looking at a candidate does not promote it, the queue creates no
`photos` row, and the queue cannot serve a token because intake refuses to
store one in the first place.

It is **not the screen**. That is Phase 2.

It has **no `proposed_trip_day_id` / `proposed_region_id` /
`proposed_stop_id`**, because migration 0037 has no such columns. The route
does not invent a finer answer than the schema can hold. See Decision 1.

It **refuses `changed` and `skipped` with 400**, because neither is a 0037
state. There is a test named for it. See Decision 2.

It **cannot accept**. See Decision 3, which is the important one.

---

## THREE DECISIONS FOR CHRIS

These are the "schema/design decisions" flagged when WO-2 was queued. They are
recorded here with a recommendation each, not guessed at in code.

### Decision 1 -- placement granularity: does the queue file to a trip, or to a day/region/stop?

**The situation.** The Epic Plan's `import_candidate` carried
`proposed_trip_day_id`, `proposed_region_id` and `proposed_stop_id`. Migration
0037 shipped without them. The highest migration on disk is **0037; there is
no 0038**. So today a candidate is filed to a **trip and nothing finer**, and
Phase 1 reflects that honestly rather than papering over it.

**Recommendation: stay at trip granularity through Phase 2. Do not write 0038
yet.**

The reason is not effort, it is ordering. Those three columns hold what an
*importer proposed*, and there is no importer yet -- Picker is WO-3 and
Takeout is WO-4. Adding the columns now means guessing the shape of a proposal
before the thing that produces proposals exists, and the queue would then have
three columns that are permanently null and a UI affordance that never fires.
When WO-3 lands and can actually compute "this photo's GPS is inside the
Tuscany region on day 4", 0038 gets written against a producer that exists and
a known payload shape.

The cost of waiting is one migration later. The cost of not waiting is a
schema commitment made blind, and 0037 already paid that bill once (the plan's
`review_status` / `operator_decision_json` names lost to the shipped ones).

**If you disagree** and want day/region/stop now, say so and it becomes Phase
1.5: migration 0038, three nullable FK columns, repository validation that a
proposed day/region/stop belongs to the proposed trip and the proposed trip
belongs to the person, and the queue payload gains a `proposed` block. That is
a real phase, not an edit.

### Decision 2 -- are `changed` and `skipped` real states?

**The situation.** The shipped `candidate_states` are `pending`, `accepted`,
`rejected`, `duplicate`, `error`. `changed` and `skipped` appear in the Epic
Plan but have no 0037 state, and both Phase 4 and Phase 1 here refuse them
with 400 rather than quietly mapping them onto something near enough.

**Recommendation: neither becomes a sixth state. Model them differently.**

`changed` is not a review outcome. It is the difference between what the
importer proposed and what the operator saved. That is an audit fact about a
decision, and 0037 already has the columns for it -- `state_reason`,
`reviewed_by_user_id`, `reviewed_at`. A candidate the operator accepted after
re-filing it to a different trip is `accepted`; that it moved is recorded, not
a separate outcome. Making it a state means a row can be `changed` *or*
`accepted` but not both, which loses the more important of the two facts.

`skipped` is the harder one, because it means two different things and the
ambiguity is the argument against it. "I have not decided yet" is already
`pending`. "I decided not to use this" is already `rejected`. If what you
actually want is **"not now, ask me again later"** -- a third thing, a defer
-- then that is a separate nullable `deferred_until` or a boolean, not a
state, because every count, every `decidable_states` check and the whole Phase
1 counts contract keys on there being exactly five terminal-or-pending states.
A sixth state is a migration plus a sweep through three test suites; a defer
flag is additive.

**If you disagree** and want them as states, that is migration 0038 (widen the
CHECK constraint), plus updating `/enums`, plus the Phase 5 smoke assertion
that explicitly proves `skipped` and `changed` are absent, plus the Phase 1
test named `test_changed_and_skipped_are_not_states_this_queue_knows`. All
mechanical, all doable, but it is a phase and it invalidates a documented
guarantee, so it needs your word rather than an inference.

### Decision 3 -- who creates the `photos` row when a candidate is accepted? (THIS ONE IS NEW AND IT BLOCKS THE UI)

**This was not in the recorded WO-2 prerequisites. It surfaced while building
Phase 1 and it is the largest structural gap in this work order.**

**The situation.** `candidate_decide(state='accepted')` requires a `photo_id`
pointing at a `photos` row **that already exists and is already owned by the
candidate's person**. The repository deliberately never creates one -- that
absence is how *intake is not approval* got enforced in Phase 3, and a runtime
`PRAGMA table_info` guard fires if `narrator_ready` or `include_in_memoir`
ever appear on `import_candidate`.

So nothing in the entire import lane materializes a photo. Which means:

> **The Evidence Review Queue can display, reject, mark duplicate, mark error
> and file to a trip. It cannot accept anything.** Phase 5's smoke only
> managed an accept because it pointed at one of Christopher's four
> pre-existing photos.

A review screen whose primary affirmative action is disabled is not a review
screen. This has to be settled before Phase 2 draws a button.

**The three options.**

**(A) The decision route creates the photo.** `POST /candidates/{id}/decision`
with `state=accepted` and no `photo_id` materializes the `photos` row itself.
Fewest calls. But it puts a write to `photos` inside the decision path, which
is exactly the boundary Phase 3 was built to hold, and it makes "accept" a
compound operation that can half-fail.

**(B) An explicit promotion route.** `POST /candidates/{id}/promote` creates
the `photos` row from the candidate's stored metadata, returns its id, and
leaves the candidate `pending`. The operator (or the UI, in one gesture) then
calls the existing decision route with that `photo_id`. Two steps, each
independently auditable, and *intake is not approval* stays literally true --
promotion is a separate act with its own route, its own tests and its own
place in the log.

**(C) The importer creates the photo at intake, born unapproved.** WO-3/WO-4
write the `photos` row when the material lands; the candidate points at it
from birth; accept is then purely a state change. Simplest decision path. But
it means **intake writes to `photos`**, which is the thing 0037's column
absences were designed to prevent, and it fills the photo library with rows
for material the operator may never accept.

**Recommendation: (B).**

It is the only one of the three that does not weaken a guarantee already
shipped and tested. It also matches how you have described the review step --
promotion is a deliberate act, not a side effect of clicking through a queue.

**The honest caveat on (B), which you need before deciding.** A candidate
holds an `external_id` or a filename. It does **not** hold bytes. For a
manual/local-upload candidate the file is already on disk and promotion is a
metadata copy. For a Picker or Takeout candidate, promotion requires actually
fetching or extracting the image -- and that is WO-3/WO-4 work, not this work
order. So (B) probably ships in two pieces: the promotion route and the
local/manual path now, the Picker/Takeout fetch when those importers exist.

**Consequence if all three stay undecided:** Phase 2 ships a queue that can
triage but not approve. That is still useful -- rejecting and de-duplicating
several hundred Takeout candidates is most of the work -- but it should be a
choice you made, not a limitation you discovered after the screen was built.

---

## Proposed phases

| Phase | Status |
|---|---|
| 1 -- the queue read | ✅ **LANDED 2026-07-26.** `queue_read()` + `GET /api/import-provenance/queue` + 56 tests. Baseline 399 -> 455; routes suite held at 67; import-provenance surface 15 -> 16 routes; still zero DELETE. Person required and never inferred, both kinds of hidden honoured, counts describe the queue and not the page, order is insertion order tiebroken on `rowid`, `match_reason` verbatim, and four tests proving the read writes nothing. |
| 2 -- the screen | ⛔ **BLOCKED on Decisions 1 and 3.** The Evidence Review Queue UI on the operator path. Batch/state/trip filters, the counts header, per-candidate detail with `match_reason` shown as the importer wrote it, and the decision controls. No native `prompt`/`confirm`/`alert` -- in-panel review, same as the Travel Doc delete drawer. **A phase is a scope wall: this is a separate session.** |
| 3 -- promotion | ⬜ **NOT STARTED, depends on Decision 3.** Whatever settles the "who materializes the photos row" question. If (B), a `POST /candidates/{id}/promote` route plus the local/manual path. |
| 4 -- live smoke | ⬜ **NOT STARTED.** Against the serving stack from the operator UI origin, not the unittest harness -- `.venv` and `.venv-gpu` disagree on FastAPI/Starlette and the serving one is what answers requests. Read-only fingerprints before and after to prove blast radius, same as the WO-1 Phase 5 pattern. |

---

## Test surface

New: `tests/test_import_provenance_queue.py`, **56 tests** in eight classes.

| Class | Proves |
|---|---|
| `QueueGateTests` | Flag off -> 404, including **before** it validates a missing `person_id`, and on junk query parameters. A disabled surface does not advertise its schema. |
| `QueuePersonTests` | Missing person is 422, empty person is 422, unknown person is **409 not an empty queue**, a real person with no imports is an empty queue, and the person is echoed back so a screen can prove whose queue it is showing. |
| `QueueBoundaryTests` | Another person's trip 409, unknown trip 409, another person's batch 409, unknown batch 404, one person's queue never contains another's candidates, unknown state 400, `changed`/`skipped` 400, negative limit/offset 422. |
| `QueueHiddenTests` | Both kinds of hidden, `include_hidden` restoring both, each row saying which kind it is, hidden rows out of the counts too, unhiding restoring, and **reopening a batch is not unhiding it**. |
| `QueueCountsTests` | Counts cover every state including the empty ones, ignore the state filter, ignore the page size; `total` does honour the state filter; `queue_depth` is pending and only pending; filters echoed back; counts scoped to the batch filter. |
| `QueueOrderTests` | Oldest-first with a `rowid` tiebreak across twenty candidates inside one second, order surviving paging, offset without limit, offset past the end being an empty page not an error, `limit=0` returning counts and no rows. |
| `QueueShapeTests` | Batch inline, `trip: null` not a dict of nulls, trip date window present, no join alias leaking, no id or `person_id` shadowing, `match_reason` verbatim, **the read changes nothing in the database**, looking does not promote, the queue materializes no photo, an accepted candidate shows the photo it was promoted into, and the queue cannot serve a token because intake refuses one. |
| `QueueRepositoryTests` | The same boundaries at the repository layer rather than only at the edge, and that the read opens and closes its own connection. |

The fixture is a deliberate **copy** of the routes fixture rather than an
import: `unittest discover` cross-contaminates across modules in this repo, so
each module has to stand alone. Run it by module name, never by discovery.

---

## Files

**Changed**

- `server/code/api/services/import_repository.py` -- `queue_read()`,
  `_QUEUE_BATCH_COLUMNS`, `_QUEUE_TRIP_COLUMNS` appended. No existing function
  touched.
- `server/code/api/routers/import_provenance.py` -- `GET /queue` appended, and
  three header-docstring edits so the module's own description stops saying
  "this is not the Evidence Review Queue" when part of it now is.
- `tests/test_import_provenance_routes.py` -- one entry in
  `FlagGateTests._all_routes()`. Required, not cosmetic.

**Added**

- `tests/test_import_provenance_queue.py`
- `docs/wo/WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01_Spec.md` (this file)

**Not touched:** no migration, no `main.py` change (the router is already
registered), no UI file, no flag change, no `.env`, no schema.
