# WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01

**Status:** Phases 1, 2 and 3 LANDED. **All three decisions are CLOSED by
Chris** (recorded below) and Phase 2/3 were opened together as one vertical
slice at his explicit instruction -- the single override of the standing
"a phase is a scope wall" rule, granted in writing for this slice only and
not generalisable to the next one.

- Phase 1 (the queue read) landed 2026-07-26: `queue_read()`, `GET /queue`,
  56 tests.
- Phase 3 (promotion) landed 2026-07-27: `candidate_promote()`,
  `POST /candidates/{id}/promote`, 62 tests. Built **before** Phase 2 on
  purpose: Decision 3 makes "accept" unreachable without it, and a screen
  shipping a button that cannot work is worse than a screen that waits.
- Phase 2 (the screen) landed 2026-07-27: the Evidence tab in Travel
  Documenter, 21 new tests, lab suite 129 -> 150.

Phase 4 (live smoke against the serving stack) is the only phase still open.

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

## THREE DECISIONS FOR CHRIS -- ALL THREE CLOSED 2026-07-27

These are the "schema/design decisions" flagged when WO-2 was queued. They are
recorded here with a recommendation each, not guessed at in code.

**Chris ruled on all three on 2026-07-27, in writing, before any of Phase 2 or
Phase 3 was built:**

| Decision | Ruling | What it forbids |
|---|---|---|
| 1 -- placement granularity | **Trip level. No migration 0038.** | No region / stop / day control anywhere on the screen. "File to trip" is the whole of placement. |
| 2 -- `changed` / `skipped` as states | **No. They do not become states.** | The state rail offers exactly the five that shipped in 0037 and the screen invents no sixth. |
| 3 -- who creates the `photos` row | **Explicit promote route, option B.** | No `create_photo` flag on the decision route. Promotion is a separate call that returns a `photo_id` and leaves the candidate `pending`; the existing decision route then accepts using that id. |

These are closed. They are not reopened by a later session, and the tests in
`EvidenceReviewQueueTest` pin each of them by name so that reopening one by
accident fails the build rather than shipping quietly.

The recommendations that follow are kept as written rather than rewritten
after the fact, so the reasoning that led to each ruling stays auditable.

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

*(Moot as of 2026-07-27. Chris decided all three, so the screen approves.)*

---

## Phase 3 -- promotion (LANDED 2026-07-27)

Decision 3, option B, built exactly as ruled.

`candidate_promote(candidate_id, source_path=None, original_filename=None,
promoted_by_user_id=None)` resolves in a fixed order, first match wins:

1. the candidate already carries a `photo_id` -> reuse it, `reused="candidate"`;
2. its declared `file_hash` matches a live photo of **this person** -> link
   that one, `reused="hash"`;
3. bytes were supplied -> sha256 them; a person-scoped hit links, a **global**
   clash raises `CrossPersonError` (409) rather than quietly linking one
   narrator's photo into another's queue; otherwise store the file, create the
   photo, and assert it was born unapproved;
4. no bytes and nothing to reuse -> `PhotoBytesMissingError` (409).

The route is `POST /candidates/{id}/promote`, taking an optional multipart
`file`. Three properties matter and each has tests:

- **The photo is born not narrator-facing and not approved for Lori**, on
  neither its date nor its location. `_assert_born_unapproved` is a real
  assertion, not a comment -- *intake is not approval* is enforced at runtime.
- **Promotion does not decide.** The candidate is still `pending` afterwards.
  Build point 3, and it is what makes the two-step honest.
- **Promotion is idempotent.** Re-promoting reuses. This is what makes the
  halfway state (promoted, accept failed) safe to retry, which is what lets
  the screen tell the operator to just press the button again.

No new dependency: `python-multipart` is already in both virtualenvs.

## Phase 2 -- the screen (LANDED 2026-07-27)

The **Evidence** tab in Travel Documenter, between Photos and Story Notes.
`ui/js/travel-doc-lab.js`, in that module's existing idiom -- `el`/`btn`/
`field`/`drawerShell`, the single `api()` choke point, the single `renderAll()`
repaint entry point.

**What it shows** (build point 6): candidates, the state counts, the batch
(label, source, status, hidden), the trip (title **and its date window**),
filename **and** external id both, mime, byte size, `taken_at` with its
source, `match_reason` printed key-by-key exactly as the importer stored it,
`match_confidence`, `state` and `state_reason`.

The trip date window sits next to `taken_at` deliberately: *does this photo's
`taken_at` fall inside the trip it is filed under* is the most common review
question, and the queue already returns the dates, so it is answerable without
opening the trip.

`match_reason` is printed as key/value pairs in a monospace column and never
paraphrased. The repository round-trips it and says why -- "round-trip, never
a summary, never prose" -- so a screen that summarised it would be the summary
that refusal exists to prevent.

**What it does** (build point 7): promote + accept, reject, duplicate, error,
hide/unhide, file to trip. Every one goes through an in-panel drawer. No
native `prompt`/`confirm`/`alert`, no DELETE.

### Four deliberate boundary changes, none of them quiet

1. **The sanctioned-endpoint gate was widened by one entry.**
   `tests/test_travel_doc_lab.py` locked this module to `/api/trips`,
   `/api/photos/`, `/api/people`, `/api/chat/ws`. `/api/import-provenance` is
   now a fifth. The gate is a prefix allow-list, so it still fails the build
   on anything else; the lane it admits is behind a default-off flag, is not
   narrator-facing, and cannot delete. The reason is written into the test.

2. **The Evidence tab is exempt from `renderAll()`'s selected-trip gate, and
   it is the only tab that is.** Every other tab describes a trip. This one
   describes a *person's* imports, and the rows most in need of review are
   precisely the ones not filed to a trip yet -- gating it on a selection
   would hide the unfiled queue behind a trip the operator has not made. The
   drawers are ungated for the same reason.

3. **The CSS namespace is `tdl-erq-`, not `tdl-ev-`.** `tdl-ev-` was already
   owned by the per-photo evidence panel (`tdl-ev-badge`, `tdl-ev-row`,
   `tdl-ev-off`, `tdl-ev-editor` and more). The first draft used it and would
   have restyled that panel from across the file. Two different meanings of
   "evidence" live in this stylesheet and they do not share a prefix. The same
   collision existed in JS -- `renderEvidenceRow` was already taken -- and the
   queue's row renderer is `renderErqRow`. A `var` hoist would have silently
   replaced the older function.

4. **Decided rows are not re-decidable from this screen.** That is a refusal,
   not an omission, and the row says so. `candidate_decide` writes `photo_id`
   unconditionally, so re-deciding an accepted candidate sets it to NULL and
   strands the `photos` row it pointed at -- unreferenced and still
   unapproved. That cleanup is a photo-lane act on the photo; it is not
   something to trigger by mis-clicking in a queue.

### Two states the screen names rather than hides

- **The flag is off.** Every route in the lane answers 404 while
  `HORNELORE_IMPORT_PROVENANCE` is unset, so the tab renders its own
  explanatory panel -- *switched off on this server, nothing is broken and
  nothing is lost* -- instead of the red error bar. Painting a configuration
  fact as an error sends an operator hunting for a broken trip.
- **Promoted but not accepted.** The two requests are separate by ruling, so
  the first can land and the second fail. The drawer reports it in those
  words, says the candidate is still pending, and says the retry is safe --
  which it is, because promotion is idempotent.

### Known limitation, stated rather than papered over

`GET /queue` has no "trip is null" filter and this screen does not invent one.
Unfiled candidates are found under **All trips**, and the count of unfiled
rows shown in the summary is computed from the current page only -- it is
labelled "on this page" for exactly that reason. If unfiled-only becomes a
real review need, it belongs in the route, not in client-side guesswork.

---

## Proposed phases

| Phase | Status |
|---|---|
| 1 -- the queue read | ✅ **LANDED 2026-07-26.** `queue_read()` + `GET /api/import-provenance/queue` + 56 tests. Baseline 399 -> 455; routes suite held at 67; import-provenance surface 15 -> 16 routes; still zero DELETE. Person required and never inferred, both kinds of hidden honoured, counts describe the queue and not the page, order is insertion order tiebroken on `rowid`, `match_reason` verbatim, and four tests proving the read writes nothing. |
| 2 -- the screen | ✅ **LANDED 2026-07-27.** The Evidence Review Queue tab on the operator path, in `ui/js/travel-doc-lab.js` + `ui/css/travel-doc-lab.css`. State/scope/hidden filters, the counts header, per-candidate detail with `match_reason` printed as the importer wrote it, and the seven row actions. No native `prompt`/`confirm`/`alert` -- in-panel drawers, same as the Travel Doc delete drawer. Lab suite 129 -> 150. |
| 3 -- promotion | ✅ **LANDED 2026-07-27, and built BEFORE phase 2 rather than after it.** Decision 3 chose the explicit promote route, which means "accept" is literally unreachable from a screen until promotion exists -- a candidate has no `photo_id` to accept with. Building the screen first would have shipped an accept button with nothing behind it. `candidate_promote()` + `POST /candidates/{id}/promote` + 62 tests. |
| 4 -- live smoke | ⬜ **NOT STARTED.** Against the serving stack from the operator UI origin, not the unittest harness -- `.venv` and `.venv-gpu` disagree on FastAPI/Starlette and the serving one is what answers requests. Read-only fingerprints before and after to prove blast radius, same as the WO-1 Phase 5 pattern. |

---

## Test surface

### Phase 1 -- `tests/test_import_provenance_queue.py`, **56 tests** in eight classes.

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

### Phase 3 -- `tests/test_import_provenance_promote.py`, **62 tests** in thirteen classes.

| Class | Tests | Proves |
|---|---|---|
| `PromoteFlagGateTests` | 2 | Flag off -> 404, before it validates anything else. |
| `PromoteUnknownCandidateTests` | 2 | Unknown candidate 404; another person's candidate is not reachable. |
| `PromotedPhotoIsBornUnapprovedTests` | 8 | The row is born **not narrator-facing and not Lori-approved** -- every approval-shaped column checked by name, not by a spot check on one of them. |
| `PromotionDoesNotDecideTests` | 7 | Build point 3. Promotion returns `photo_id` and **leaves the candidate `pending`**; it writes no `state`, no `state_reason`, no `reviewed_by_user_id`, no `reviewed_at`. The existing decision route is still the only thing that decides. |
| `PromotionIsIdempotentTests` | 2 | Promoting twice returns the same `photo_id` and creates no second row -- so a half-completed promote+accept is safe to re-run, which is exactly what the screen tells the operator. |
| `PromotionRefusesToInventAPhotoTests` | 4 | No bytes, no photo. `PhotoBytesMissingError` -> 409 rather than an empty file on disk. |
| `PromotableSourceTests` | 6 | Only `local_upload` and `manual` promote here. `google_photos_picker`, `google_takeout` and `csv` are refused -- those are later epics and this route does not quietly become their importer. |
| `PromoteMimeTests` | 3 | The six-value accepted-type tuple, and the refusal for anything outside it. |
| `PromoteHashTests` | 7 | The four-step resolution order for `file_hash`, and that a supplied file whose hash contradicts the candidate is refused rather than silently trusted. |
| `PromoteDateDoctrineTests` | 5 | `taken_at` / `taken_at_source` carry across without upgrading their own confidence -- a `filename_guess` does not become `exif` by being promoted. |
| `PromoteLocationDoctrineTests` | 5 | Same doctrine for lat/long and `location_source`. |
| `PromoteProvenanceTrailTests` | 6 | The photo points back at the candidate it came from and the trail survives a later decision. |
| `PromoteStaysTripLevelTests` | 2 | Decision 1. The promoted row inherits **trip** and nothing finer -- no region, no stop, no day. |
| `PromoteAddsNoDeleteTests` | 3 | Build point 12. The lane still has zero DELETE after this phase. |

### Phase 2 -- `tests/test_travel_doc_lab.py`, **129 -> 150** (`EvidenceReviewQueueTest`, 21 tests).

This is a source-reading suite, not a browser suite: it asserts against the
text of `travel-doc-lab.js` and `travel-doc-lab.css`. That is what the existing
150-test module already is, and it is why it can pin things a DOM test cannot
-- request ordering, the absence of a native dialog, namespace ownership.

The 21 map onto Chris's build list rather than onto the code's own shape:
build point 5 (`test_evidence_tab_is_registered`), point 6
(`test_screen_shows_the_six_things_build_point_6_asks_for`,
`test_match_reason_is_printed_verbatim_never_paraphrased`), point 7
(`test_all_seven_row_actions_exist`), points 1--4
(`test_promote_then_accept_is_two_requests_in_that_order`,
`test_refusals_send_no_photo_id`,
`test_promote_uses_formdata_through_the_single_api_choke_point`), Decision 1
(`test_placement_is_trip_granularity_and_nothing_finer`), Decision 2
(`test_state_rail_offers_exactly_the_five_shipped_states`), and points 8--12
(`test_no_picker_and_no_takeout_in_this_phase`,
`test_the_queue_adds_nothing_narrator_facing_and_no_lori_control`,
`test_hide_is_reversible_and_the_queue_has_no_delete`).

The ordering test is structural rather than textual -- it takes the index of
`"/promote"` and the index of `"/decision"` inside the function body and
asserts the first is less than the second. A test that merely asserted both
strings are present would pass on code that accepts before it promotes.

`_section()` slices exactly from `var EVIDENCE_BASE` to `function renderNotes(`
rather than taking a fixed-width window. Both failure modes of the fixed window
were observed while writing this suite: a window starting at
`function renderEvidence(` clipped the action-label constants off the front and
reported them missing, and the same window overran the section end and reported
`include_in_memoir` as a narrator leak from unrelated code below.

---

## Files

**Changed -- phase 1**

- `server/code/api/services/import_repository.py` -- `queue_read()`,
  `_QUEUE_BATCH_COLUMNS`, `_QUEUE_TRIP_COLUMNS` appended. No existing function
  touched.
- `server/code/api/routers/import_provenance.py` -- `GET /queue` appended, and
  three header-docstring edits so the module's own description stops saying
  "this is not the Evidence Review Queue" when part of it now is.
- `tests/test_import_provenance_routes.py` -- one entry in
  `FlagGateTests._all_routes()`. Required, not cosmetic.

**Changed -- phase 3**

- `server/code/api/services/import_repository.py` -- `candidate_promote()`
  appended. Again no existing function touched.
- `server/code/api/routers/import_provenance.py` -- `POST
  /candidates/{candidate_id}/promote` appended. Surface 16 -> 17 routes, still
  zero DELETE.
- `tests/test_import_provenance_routes.py` -- the promote route added to
  `FlagGateTests._all_routes()`, same reason as phase 1.

**Changed -- phase 2**

- `ui/js/travel-doc-lab.js` -- 5788 -> 6432 lines. Eight patch sites: seven
  small ones (state fields, the `selectTrip()` reset, the `TABS` entry, the
  lazy load in `setTab()`, the trip-gate exemption and drawer append in
  `renderAll()`, the `renderTab()` case) and the section itself at 4912--5512.
  No existing function body rewritten.
- `ui/css/travel-doc-lab.css` -- 664 -> 713 lines, appended only.
- `tests/test_travel_doc_lab.py` -- `EvidenceReviewQueueTest` added, **and one
  existing assertion deliberately widened** (see below).

**Added**

- `tests/test_import_provenance_queue.py`
- `tests/test_import_provenance_promote.py`
- `docs/wo/WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01_Spec.md` (this file)

**Not touched:** no migration (Decision 1 killed 0038), no `main.py` change
(the router is already registered), no flag change, no `.env`, no schema, no
narrator-facing file, no Travels-shelf file, no Lori file, no new dependency
(`python-multipart` is already in both virtualenvs).

The widened assertion, the two namespace collisions, the two named
states and the known limitation are all written up under **Phase 2 -- the
screen** above; they are not repeated here.
