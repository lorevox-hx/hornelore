# TRAVEL_DOCUMENT_DOCTRINE

**Status:** ACTIVE — permanent doctrine for the travel-document evidence lanes
**Date:** 2026-07-28
**Decision owner:** Chris Horne
**Type:** Architectural Decision Record (ADR) — not a Work Order
**Companion to:** `docs/wo/WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md` — §12.7 is restated here in full
**Consolidates:** the two permanent-doctrine sections in `CLAUDE.md` — "Travel Doc Evidence + Web Context Rule" (2026-07-10) and "Google Photos Picker identity boundary" (2026-07-27)

---

## TL;DR

Every external producer of travel evidence enters through a shared intake and
review lane. No producer builds its own review queue, its own approval
semantics, or its own permanent archive.

Which lane a piece of evidence enters is decided by what the evidence *is*,
not by where it came from. A PDF itinerary is not a photo candidate. There
are five lanes and they are named by database table, not by import source.

Nothing crosses from intake into permanent authority without an operator
decision, and no code path may manufacture that decision on the operator's
behalf — not a retry, not a repair, not a failure, not a duplicate.

This document is split into four parts that must not be blended: rulings,
shipped behaviour, deliberate absences, and documented intent. The reason for
the split is in the next section, and it is not stylistic.

---

## How to read this document

Four parts, kept structurally apart, because this repository has already been
bitten by the alternative.

The picker spec carried the sentence **"No Phase 2 code exists."** for a full
day after Phase 2 shipped, and the sentence sat two lines below a paragraph of
rulings that were still perfectly true. A ruling and a description of shipped
behaviour read identically in prose. They age completely differently. Mixed
together in one section, the false sentence is camouflaged by its true
neighbours, and a reader who trusts the section trusts all of it.

So:

**Part 1 — Binding rulings.** Decisions. True until Chris overturns them. They
do not expire when code lands and they are not evidence that any code exists.
A ruling here constrains whoever implements the thing, including the case
where nobody has implemented it yet.

**Part 2 — Implemented and verified.** What is on disk today and what proves
it. Every claim in Part 2 is falsifiable by reading a named file or running a
named suite. This is the only part that goes stale on its own, which is why it
carries a date in its heading and why the `## Maintenance` section names it
specifically.

**Part 3 — Deferred or not started.** Work that was considered and
consciously not done, each item with its reason. Absence with a reason and
absence by oversight are different facts and a reader needs to be able to tell
them apart.

**Part 4 — Future design only.** Documented intent with no implementation and
no committed schedule. Nothing in Part 4 may be cited as a constraint on
current work, and nothing in Part 4 may be treated as promised.

If a statement cannot be filed under exactly one of the four, it is not yet
clear enough to be written down.

---

## Part 1 — Binding rulings

### 1.1 The five evidence lanes (spec §12.7, restated in full)

An earlier draft of the Phase 2 work order stated that every future evidence
producer terminates at `import_candidate`. That is too broad, and this
repository already contradicted it before the draft was written.
`trip_sources` exists, with columns `source_type, title, filename, mime_type,
storage_path, pasted_text, link_url, source_date, summary, include_in_memoir,
ord, hidden` and placement at `trip_id / trip_region_id / trip_stop_id /
trip_day_id`. It is already shaped for itineraries, boarding passes, receipts,
PDFs, pasted text and links — the exact producers the draft wanted to force
through `import_candidate`.

The lanes, as ruled:

| Lane | Holds |
|---|---|
| `import_batch` / `import_candidate` | externally acquired photo/media candidates awaiting review and promotion — byte acquisition, hashing, metadata inspection, duplicate detection |
| `photos` | permanent approved photograph authority |
| `trip_photo_links` | approved photo placement within a trip |
| `trip_sources` | approved trip-scoped documents: itineraries, boarding passes, hotel confirmations, receipts, PDFs, pasted text, links — placed at trip, region, stop or day |
| `trip_location_notes` and the story structures | human memory, operator context, interview material, narrative |

The doctrine is therefore: **every external producer must enter an appropriate
shared intake and review lane, and no producer may create its own review
queue, its own approval semantics, or its own permanent archive.** Which lane
depends on the evidence type. A PDF itinerary is not a photo candidate.

### 1.2 The lane is chosen by evidence type, never by import source

There are five lanes. There are also five import sources, and they are not the
same list and do not correspond one-to-one:

```
IMPORT_SOURCES = ("google_photos_picker", "google_takeout",
                  "local_upload", "csv", "manual")
```

`google_photos_picker` and `local_upload` are different sources that land in
the same lane. A boarding-pass PDF and a photograph can arrive from the same
source and belong in different lanes. Anyone reading "five" in this
subsystem should check which five they are looking at — the spec alone uses
the word for four unrelated groups of five, including the five candidate
states and the five identity objects of §10.1.

### 1.3 The existing evidence queue is authoritative

There is one review queue for photo/media candidates and it is the Evidence
Review Queue built by `WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01`. A new import
source makes its candidates visible *in that queue*. It does not get a review
screen of its own.

This binds the Picker operator UI (Phase 2D / Phase 4) specifically and in
advance: that UI may open the picker, report the selection, trigger ingest and
refresh the queue. It may not decide candidates, and it may not render a
second list of pending items with its own accept and reject controls. A second
queue is a second approval semantics no matter how thin it looks on the day it
is written.

### 1.4 Location may never fall back. Date may.

The asymmetry is deliberate and it is the sharpest rule in this document.

A candidate's `taken_at` may fall back through a chain — EXIF, then provider
metadata, then a filename guess, then operator entry, then unknown — because a
wrong date is a wrong date and the operator can see it and fix it.

A candidate's location may not. `location_source` is `exif_gps` when EXIF in
the downloaded bytes carries GPS, and `unknown` otherwise. It is **never**
`provider_metadata` on this lane. A provider's idea of where a photograph was
taken is an inference about a place the narrator may never have been, and once
it is written into a latitude and longitude it is indistinguishable from a
measurement. The memoir is the output. A fabricated place in a memoir is not
a data-quality problem, it is a lie told in the narrator's voice.

A GPS block that is present but unparseable is recorded as such in
`match_reason`, with both coordinate columns left null. Recording that we saw
something we could not read is not the same as recording nothing, and it is
not the same as guessing.

### 1.5 A candidate id is never preallocated (spec §12.2)

Bytes are downloaded to a temporary file, validated, hashed and measured
before `candidate_create()` is called. The id the repository actually returns
is the id the bytes are staged under. No code path invents an id, stages
against it, and then hopes the insert agrees.

The ordering is structural, not stylistic. Reversed, a failed or refused
insert leaves staged bytes under an id that belongs to nothing, and the
staging tree stops being a function of the database.

### 1.6 An ingest failure is not a candidate decision (spec §12.3)

`pending`, `accepted`, `rejected`, `duplicate` and `error` are operator
decision states. A download that times out, a hash that disagrees, a file that
vanished from disk — none of these is an operator decision and none of them
may write one.

Concretely, on re-ingest, three independent claims exist about a candidate:
the row's stored `file_hash`, the bytes freshly downloaded from Google, and
the file currently on disk. The rule is majority:

- Row and fresh download agree, disk dissents or is missing → repair the
  file. The row is not touched.
- Row and fresh download disagree → there is no majority. Refuse with
  `hash_mismatch`. Neither the row nor the file is touched.

A refusal is not a decision. The candidate stays `pending` and the operator
still owns it.

Item outcomes are independent within a run. One item failing does not stop the
run and does not close the batch. The batch is closed `failed` only when the
Picker session itself is wholly unusable — not when an item inside it is.

### 1.7 There is no DELETE and no undecide on this lane

No DELETE anywhere on the import/evidence lane, including for failed
downloads. A batch closes or stays open; it is not removed. A decision is a
decision; `pending` is not among the states an operator can move a candidate
back to.

This is what makes the lane an audit trail rather than a working set. A record
that can be erased cannot later answer the question of what the system knew
and when.

### 1.8 Promotion requires bytes we hold

```
PROMOTABLE_SOURCES = ("local_upload", "manual")
```

The provider-side sources are deliberately absent. Promotion mints a `photos`
row, which is permanent authority, and it needs the image bytes.
`local_upload` and `manual` are the two sources where the operator is holding
them. `google_photos_picker` and `google_takeout` each have to fetch their own
bytes through their own lane first. `csv` is a manifest of claims about files
nobody has handed us.

Adding a source to that tuple without also building its fetch would turn
promotion into a way to mint photo rows for images that do not exist. When
`google_photos_picker` is added — Phase 3, see 3.1 — it is added *because* the
fetch lane now exists, and `google_takeout` still stays out.

### 1.9 The identity boundary

Five separate things, never collapsed into each other: the Google Cloud
project and OAuth client; the authorized Google account; the Hornelore
operator; the Hornelore person (the narrator); and the Hornelore trip.

The account that authorizes a picker session is not the narrator whose
evidence is being imported, and is not evidence of who the narrator is. A
`person_id` is supplied explicitly by the operator on every session. There is
no default, no fallback, and no "if only one person exists, use that one."
A single-narrator installation that guesses correctly today is a
multi-narrator installation that guesses wrongly later, and the failure is
silent — evidence filed against the wrong life.

### 1.10 Credential hygiene is structural, not a review item

The Picker `baseUrl` is a bearer-scoped download URL: possession of the string
is possession of the bytes. Together with the access and refresh tokens, it
must never reach an HTTP response, a log line, an exception message, a
database column, or `match_reason`.

Two consequences that are easy to get wrong and are therefore written down:

- An unexpected exception on the ingest path is reported by
  `exc.__class__.__name__` only, and no traceback is emitted, because a real
  `requests` exception stringifies to the URL that raised it.
- `/health` reports presence booleans. Never values, never prefixes, never
  lengths, never masked tails. A masked tail is a shorter secret.

`match_reason` additionally carries no staging path and no key containing any
`_SECRET_KEY_HINTS` substring. `_SECRET_KEY_HINTS` contains `session_id`, so
a key named `session_id` or `picker_session_id` raises `ExternalTokenError` at
write time. Use `picker_session`. This is a landmine and it has been stepped
on once already.

### 1.11 A phase is a scope wall

Each phase is its own session and its own commit. A wall is enforced by
executable tests — exact `ast` import sets, attribute sets, and assertions
that a route does not exist — not by intention.

When a phase legitimately passes a wall, the wall is **moved forward and told
why**. It is not loosened and it is not deleted. The four Phase 1 wall tests
that Phase 2B passed were each renamed to state the narrower thing they now
guard; `/health` moving from phase 1 to phase 2 was a wall moving, because
holding it at 1 would have been the health check lying rather than a wall
holding.

A second wall moved on 2026-07-28, inside `WO-TRIP-PLAN-AS-HUB-01` Phase A,
and it moved for the reason this section names rather than for convenience.
Phase A shipped only the refusal half of the shrinking-dates ruling and wrote
the gap down as a decision, in a test called
`test_shrinking_dates_never_drops_a_day_card_from_this_surface` whose
docstring said the drop half "needs a server route and is later work".
Chris's review of Phase A asked for that route, on that phase — *"Implement
the complete shrinking-date rule: remove empty out-of-range days; refuse and
clearly list out-of-range days containing work."* The test was renamed
`test_shrinking_dates_only_ever_removes_a_card_that_holds_nothing`, carries
the retired name and the retired claim inside it, and now guards the narrower
thing that is still true: the one removal path is the reconcile POST, no
prune/drop/remove route was invented on the surface, and the automatic
add-missing lane still only adds. Two comment blocks and one banner sentence
in `ui/js/travel-doc-lab.js`, a section banner in `trip_repository.py`, two
route docstrings in `trips.py` and one assertion in a neighbouring test were
corrected in place for the same reason. A wall renamed to the narrower claim
is a wall; a wall deleted the day the feature arrives was never one.

There has been exactly one override of this rule, granted for one slice, and
recorded as non-generalisable.

### 1.12 One photo has one placement per trip

Chris's ruling, 2026-07-28, verbatim:

> One photo may have one placement per trip.
>
> Use Move, not Also show on another day.

**This ruling needs no migration, because the database has enforced it since
2026-07-15 and nobody noticed it was a ruling.** `trip_photo_links` carries
`UNIQUE (trip_id, photo_id)` from `migrations/0015_trip_tables.sql:85`,
re-asserted in 0018, 0021 and 0037, never dropped.
`migrations/0028_trip_day_links.sql` later added `trip_photo_links.trip_day_id`,
so **the day is a column on the placement, not a second row.**

The ruling is therefore about what the interface may *offer*, not about what
the store may hold. An "Also show on another day" control has exactly two
implementations: write a second `trip_photo_links` row, which the unique index
refuses, or invent a second table beside it, which is the same mistake wearing
different clothes. Neither is a feature; both are a schema change arriving
disguised as a button.

The three layers this rests on, none of which may be collapsed into another:

- **`photos`** — the permanent approved archive. **No trip column and no day
  column.** A photograph is a thing Hornelore holds, not a thing that happened
  on a Tuesday.
- **`trip_photo_links`** — the placement. Trip, photo, and optionally day.
- **`import_candidate`** — the temporary review and provenance record. **No day
  concept at all**, and none may be added to it.

Said plainly, because it was said wrongly once in this repository's history and
Chris corrected it: *a photo does not belong to a day. Its placement does.*

**What a day surface may offer:** "Move to another day" and "Remove from this
day". **What it may not offer:** "Also show on another day".

**The full ladder, for the phases that will build it** — four verbs, in
widening order, and the fourth is not reachable from a day:

1. *Change day* — update the placement's `trip_day_id`.
2. *Remove from day* — keep the trip link, clear the day.
3. *Remove from trip* — delete the trip link. The permanent photo is untouched.
4. *Delete from Hornelore* — **not available from a day, a trip, or the review
   queue. Only from a protected library-management screen**, because it is the
   one verb that destroys something no other record can reconstruct.

The import candidate behind a photograph is a separate object from all four. It
**remains in the audit record** and may be hidden from the queue, never deleted
— which is 1.7 restated from the placement side rather than the queue side.

### 1.13 A candidate is an item Hornelore actually holds

Chris's ruling, 2026-07-28, verbatim:

> Failed acquisitions remain in the import receipt.
>
> Do not create candidate rows for files Hornelore did not acquire.

And the governing principle he gave with it, also verbatim:

> A candidate should represent an item Hornelore actually possesses and can
> review.

**The distinction this protects, in his words:** *acquisition failure = the
system could not obtain the item; candidate error = Hornelore obtained an item,
but it cannot be used or promoted.* Those are different facts about different
things. A row is Hornelore's assertion that it is holding bytes; a row for a
file that never arrived is an assertion it cannot support, and a queue of them
is a list of things that may not exist. The reviewer's question — *should this
become part of the record?* — has no answer for an item nobody has.

**This resolves 3.5 and settles §7(c) against the spec.** A picked standalone
video is reported in the run receipt as unsupported and **no candidate row is
created**. The shipped code was already doing this; it is now the ruling rather
than an undecided divergence, and §7(c)'s `error`-candidate recommendation is
recorded as considered and not taken.

**A Pixel Motion Photo that arrives as a valid JPEG stays a photograph
candidate.** Its embedded motion component is ignored until a real video or
media lane exists. This is not an exception to the ruling, it is the ruling
applied: what Hornelore acquired is a photograph, and a photograph is what the
row says.

**One consequence, and it is load-bearing rather than incidental.** Under 1.6
an ingest failure is already not a candidate decision; under 1.13 it is not a
row either. The receipt is therefore the *only* record a failed acquisition
ever gets — and today that receipt lives in an HTTP response and dies on
reload. See 3.4, which stopped being a nicety the moment this ruling landed.

### 1.14 Provider bytes are not identity

Chris's ruling, 2026-07-29, verbatim:

> external_id / Google media item ID identifies the logical picked item.
> file_hash verifies Hornelore's staged local copy.
> A later Google download is not expected to reproduce the same hash.

**This ruling was bought with a failed smoke, and the failure is the useful
part of the record.** Live smoke 9 re-ran ingest over seven healthy
candidates and got seven `hash_mismatch` refusals. Nothing was corrupt --
every staged file on disk hashed exactly to its row. Two runs minutes apart
were then compared item by item, and five of the seven returned *different
bytes each time*, within three bytes in both directions. Google regenerates
metadata server-side per request. The code was refusing correctly against an
assumption that was wrong.

So, for every producer on this lane and not only the Picker:

- The provider's own stable identifier is the identity of the picked item.
  Here that is `external_id`, indexed unique on `(batch_id, external_id)`.
  **A hash is not promoted to identity to solve this.** Chris, explicitly:
  *"This does not justify changing candidate identity to hashes."*
- `file_hash` is the checksum of the copy **Hornelore retained**, not a
  fingerprint supplied by the provider. It answers *is my file still my
  file*, and nothing else.
- Re-ingest verifies the local copy first and, when it verifies, reports
  `unchanged` **without asking the provider for the bytes again**. Chris:
  *"That avoids Google's byte jitter entirely."* The download that does not
  happen is the fix; skipping the comparison would only hide it.
- A re-download for **repair** -- missing, corrupt, or an earlier attempt left
  incomplete -- may legitimately return different bytes. It stages atomically
  and the new hash becomes the integrity record. That is `repaired`, not an
  error.
- `hash_mismatch` survives, narrower: a local integrity problem, or bytes
  changing unexpectedly inside one controlled write. **Never because two
  separate provider fetches differ.**

**The refusal behaviour itself was right and is kept.** Chris: *"The system
correctly refused to overwrite a good staged file. The mistake happened
before that decision: it should never have downloaded the file again in the
first place."* A row and a file that disagree are still worse than a refusal
somebody can read. What moves is where the decision sits, not how defensive
it is.

**Repair stops at the archive boundary.** Added 2026-07-29 on Chris's ruling,
after the first ruling was written and before it was implemented, because
implementing it exposed the hole. `file_hash` on a candidate is not private to
the staging lane -- promotion resolves a candidate to an archive photo *by
that hash*, and `photos.file_hash` is unique across the whole table. So there
are **three** meanings here, not two, and collapsing them is the error the
ruling forbids:

    external_id           = provider identity
    candidate.file_hash   = integrity of the staged working copy
    photos.file_hash      = identity/integrity of the permanent archived object

Chris: *"Once `photo_id` exists, a repair must not mutate the candidate fields
that were used to resolve or create that archive photo. Otherwise the
candidate can describe one byte stream while pointing at a different archived
object."* A repair on a candidate that already carries a `photo_id` therefore
refuses -- explicitly, non-retryably, with reason `candidate_already_promoted`
-- rather than re-downloading and re-stamping. Restoring the staged copy *from
the archive object* is the allowed repair for that case and is not yet built;
it is named so that building it later is an extension rather than a
correction. **Never mutate the archive linkage implicitly** is the general
form, and it binds every producer, not only the Picker.

Implemented by `WO-TRAVEL-DOC-PICKER-REINGEST-REPAIR-01`.

---

## Part 2 — Implemented and verified (as of 2026-07-29)

Everything in this part is checkable. Where a claim rests on a test run, the
suite and the count are named; where it rests on code, the file is named.

### 2.1 The provenance foundation

Migration `0037_import_provenance_foundation.sql` exists at
`server/code/db/migrations/` and is the highest-numbered migration in the
tree. It provides `import_batch` and `import_candidate`. The vocabularies —
`IMPORT_SOURCES`, `BATCH_STATUSES`, `CANDIDATE_STATES`, `TAKEN_AT_SOURCES`,
`CANDIDATE_LOCATION_SOURCES`, `DECIDABLE_STATES`, `PROMOTABLE_SOURCES` — live
in `server/code/api/services/import_repository.py`.

The Evidence Review Queue from `WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01` is the
review surface over that foundation.

### 2.2 Picker Phase 1 — credentials and session lifecycle

`server/code/services/google_picker/oauth.py` and the session routes on
`server/code/api/routers/google_picker.py` (`POST /sessions`,
`GET /sessions/{batch_id}`, `DELETE /sessions/{batch_id}`, `GET /health`),
behind `Depends(_require_enabled)`.

Live-proven on 2026-07-27 against a real Google Cloud project, a real OAuth
client and a real authorized account — the three checks are recorded in spec
§11.2. No bytes and no candidates in this phase, by design.

### 2.3 Picker Phase 2A — the listing

`picker_client.list_media_items()` in
`server/code/services/google_picker/picker_client.py`: pagination to
exhaustion, response-shape validation, typed upstream errors, and no `baseUrl`
or credential in any error or log. No database and no staging. Covered by
`tests/test_google_picker_phase2a.py`.

### 2.4 Picker Phase 2B — acquisition and ingest

`server/code/services/google_picker/acquire.py` provides content validation, a
byte cap, download to a temporary file, metadata extraction, true size, and
hashing. `POST /api/google-picker/sessions/{batch_id}/ingest` wires the
listing to the acquisition for the first time and creates candidates.

Implements rulings 1.4, 1.5, 1.6 and 1.10 directly. Failure vocabulary is data
— `RETRYABLE_REASONS` and `PERMANENT_REASONS` in `acquire`, a `_ROUTE_REASONS`
map in the router, asserted disjoint from both at import time — so
`retryable` is derived from the reason rather than decided at each raise site.
Staging is atomic: same-filesystem `os.replace`, with an `errno.EXDEV`
fallback to `shutil.copy2` and unlink.

`/health` reports `"phase": 2` and `"ingest_available": true`.

**Verification:** 193 tests, OK, in `.venv` on 2026-07-28 — the Phase 1,
2B-acquire and 2B-ingest suites run together with
`-W error::ResourceWarning`. `.venv` and `.venv-gpu` now carry identical web
stacks (fastapi 0.135.1 / starlette 0.52.1 / pydantic 2.12.5 / httpx 0.27.2,
exactly what `requirements-test.txt` pins), so a green TestClient result is
evidence about the same framework generation that serves.

### 2.5 Picker Phase 2D — the operator affordance

`ui/js/travel-doc-lab.js` gains a Google Photos import strip at the top of
the existing Evidence tab, styled from a new `tdl-gp-` block in
`ui/css/travel-doc-lab.css`. It is **not an eleventh tab**. Ruling 1.3 gives
candidate review to the Evidence Review Queue, and a screen of its own is how
a second queue starts — first as a place to see what was imported, then as a
place to act on it. A strip above the queue can only ever be an on-ramp to
the rows below it.

The strip speaks the four verbs §12.8 names and no others: `GET /health` to
learn whether the lane is even on, `POST /sessions` to open a picking
session, `GET /sessions/{batch_id}` to poll it, and
`POST /sessions/{batch_id}/ingest` to stage what was picked. After an
ingest it calls the queue's own reload, so the authoritative screen is the
one that shows the result.

**The per-run report is a receipt, not a queue.** It is rendered once from
the response already in hand, is never refetched, and carries no control:
the seven queue row actions, `/promote`, `/decision` and every `DELETE` are
asserted absent from the strip's half of the module. The lane's one DELETE
route — it releases the picking session at Google and answers
`batch_deleted: false` — is deliberately not surfaced. That is a scope wall,
not a safety one, and it is asserted rather than assumed, because "safe and
therefore fine to add" is how the first DELETE gets in.

**Nothing credential-shaped reaches the browser.** `/health` is rendered as
presence booleans and a list of missing key *names*; no response field named
`baseUrl`, `access_token`, `refresh_token`, `client_secret` or `session_id`
is read anywhere in the block. There is no Google JavaScript, no
`apis.google.com`, no injected `<script>` and no `window.open` — the picker
URI is an ordinary anchor with `target="_blank"` and
`rel="noopener noreferrer"`, so the one step that happens off this screen
happens in Google's own window with no handle back.

**The destination is explicit, per §10.2.** `person_id` is required and
`trip_id` is sent only when the operator has a trip selected and has left the
file-to-trip control on. Nothing is inferred from the Google account, and the
unfiled case is stated on the panel rather than defaulted away. The badge
names the batch's **own** trip id, because a run survives a trip switch and a
badge reading "filed to a trip" would otherwise mean "the one you are looking
at" exactly when that was false.

**Flag-off is rendered as configuration, not as an error** — a neutral dashed
panel modelled on the queue's `.tdl-erq-off`, deliberately not `.tdl-error`,
because a red panel sends an operator hunting for a broken thing when the
true answer is that nobody switched it on. The front end reads no flag; it
infers the gate from a 404, and **only on `/health` and `POST /sessions`**,
neither of which takes a path parameter, so nothing behind them can be "not
found" except the gate itself. On `GET /sessions/{batch_id}` and on ingest a
404 has three possible meanings, so it is reported with its reason instead of
interpreted. The two off-states are independent: the queue needs
`HORNELORE_IMPORT_PROVENANCE`, the strip needs that **and**
`HORNELORE_GOOGLE_PICKER`, so a readable queue with no import affordance
above it is a correct configuration rather than a fault.

**Verification:** `tests/test_travel_doc_picker_ui.py` is new — 24 tests,
source-scanning the shipped JS and CSS, ordered by what they guard:
credentials first, then ruling 1.3, then the explicit destination, then the
flag-off arm and its 404 disambiguation. `tests/test_travel_doc_lab.py` runs
150, OK; `tests/test_travel_doc_evidence_ui.py` runs 7, OK. Two existing
gates had to be loosened and both were **retired in place**, quoting the old
assertion with the date it stopped being right: the endpoint allow-list
gained `/api/google-picker` as a sixth and separate prefix, and the timer
inventory that read "the file's only timer" now counts two and asserts a
`destroyed` check on both. That second one failed first and named its own
fix — it is the gate working, not the gate being in the way.

### 2.6 What "verified" does not yet cover

**The last sentence of this paragraph stopped being true on 2026-07-28.** It
read, in full: *"No run has touched a real `baseUrl`, a real bearer token, or
real EXIF. The credential-hygiene claims in 1.10 are proved against fixtures.
The live smoke against a real Picker session is the next gate and it has not
been run."* The first two sentences were retired by the Phase 2B live run on
2026-07-27, which touched all three. The third was retired by smokes 9 and 10
on 2026-07-28. See 2.10, which is where the live claims now live -- and which
is careful about which of them passed.

What the paragraph was protecting is still worth keeping, so it is restated
rather than dropped: **a suite is not a browser and a fixture is not Google.**
Smoke 9 is the proof, not the counterexample -- 193 green tests did not know
that Google returns different bytes for the same item on a second fetch,
because no fixture had ever been asked to.

**2D does not change that, and it is worth being exact about why.** Its 24
tests read the shipped JavaScript and CSS as text. That is the right shape of
test for the properties they guard — "no credential-shaped field is read
anywhere in this block" and "no decision control exists in this half of the
file" are claims about what the source contains, and a browser could not
prove either one more strongly than a scan does. But no browser has rendered
the strip, no operator has clicked the link, and nothing has been ingested
through it. A source scan cannot see a typo in a class name or a panel that
lays out wrongly.

Phase 1 is live-proven. Phase 2, 2D included, is suite-proven. Those are
different words on purpose.

### 2.7 Ruling 1.12 as it stands in the interface today

A different work order — `WO-TRIP-PLAN-AS-HUB-01` Phase A, 2026-07-28 — rebuilt
the trip surface around the day workspace, and the one part of it this document
is entitled to speak about is the photograph action it left behind.

The day workspace's photo control reads **"Remove from this day"**. It reads
that way rather than "Unlink" because "unlink" describes the row and not the
consequence, and a reader who is not holding the three-layer model in their
head cannot tell from the word whether the photograph is about to leave the
trip or leave Hornelore.

**No second-placement control exists on that surface**, per 1.12, and
`tests/test_travel_doc_lab.py` asserts the absence by name rather than leaving
it to be noticed. "Move to another day" is *specified* by 1.12 but is not built
yet; it belongs to the later phase that also brings the two import buttons.
Absence with a reason, per Part 3's own opening line — recorded here rather
than in Part 3 only because what shipped and what did not are the same
sentence.

**This section carries no live-smoke claim.** 2.6 applies unchanged: the
assertion is a source scan, the browser has still not been watched doing it.

### 2.8 The shrinking-dates rule as it stands in the interface today

Chris's review of Phase A returned two corrections and placed them exactly:
*"Keep both commits. Do not roll Phase A back ... record this as an explicit
Phase A completion item, not bury it in a later Picker phase. It is unrelated
to Google Photos."* Both are built, which is why they are recorded here and
not in Part 3.

**The auto-generation guard is keyed on the missing-date set, not on the
trip.** `maybeAutoAddMissingDays()` and `reloadReconcile()` call each other,
and an `autoDaysTried` map holding one entry per trip was what made that
recursion terminate. It also meant that extending a trip's dates in the same
browser session produced no new cards until a reload. The map now holds the
set of missing dates the attempt was made against, so a different set is a
different attempt and the recursion is still bounded — the bound was never
the trip, it was "do not try the same thing twice."

**The drop half of the shrinking-dates ruling is built.** Saving a shorter
date range removes the out-of-range day cards that hold nothing, and refuses
— in Chris's own words, listing what sits on each blocking day — when any of
them holds work. The refusal runs *before* the PATCH, because the failure
Chris named is "the trip header could say July 14–18 while July 19 and July
20 still appear below", and a check that ran after the save would produce
exactly that. The one removal path is `POST /api/trips/{id}/days/reconcile`
with `drop_empty_out_of_range`, defaulting to false; the server re-decides
emptiness inside its write transaction under `BEGIN IMMEDIATE` and returns
anything it refused in `kept_out_of_range`, because the browser measures from
lists that exclude hidden rows and can legitimately undercount. The preview
route stayed read-only, and its guard now asserts SQL statement forms rather
than the word `DELETE` — the word-matching version had started firing on the
docstring that explains the word.

**One decision here is an implementation choice and not a ruling, and it is
flagged rather than buried.** Emptiness is measured as what is *attached* to
the card — `trip_day_id` on photo links, notes and sources — plus the text
typed into the day row itself, and deliberately **not** from the `counts` the
`/days` route merges in for display. Those display counts are generous on
purpose: they include photographs matched to the day by taken-date and notes
inherited through the day's stop or region, and generated cards are
auto-assigned a region. Measuring emptiness from them would refuse every
shrink on any trip carrying a region-scoped note — the feature would ship and
do nothing. The cost runs the other way: a card can be removed while a
region-scoped note still reads as being "about" that day. Chris has been
asked to push back on this and has not yet.

**This section carries no live-smoke claim.** 2.6 applies unchanged. The
suites are green and no browser has watched a day card disappear.

### 2.9 The Stage 1 cleanup pass on the day workspace

Six changes, committed as `7508f1f` on 2026-07-28, **no new behaviour**. They
are recorded here because 2.7 and 2.8 describe the surface they altered, and a
reader comparing this document to the tree would otherwise find wording that
does not match.

1. **The partial-success warning opens with what succeeded.** It now begins
   *"The trip dates were saved, but ..."*. It used to open with *"could not be
   removed"*, which is what a **failed** save looks like -- the operator was
   being told the opposite of what had happened. Deliberately still amber: a
   partial success is not a success.
2. **The generator-column guard exists.** New class
   `DayGeneratorEmptinessGuardTest` in `tests/test_trip_days_reconcile.py`, two
   tests. It reads `DAY_OWN_TEXT_FIELDS` and `DAY_OWN_LIST_FIELDS` out of the
   JavaScript, slices `trip_repository.py` down to `trip_days_generate` before
   searching for the INSERT, and asserts the generator writes no field that
   `dayOwnContent` counts as content. It also pins the one deliberate
   exception: `trip_region_id` **is** stamped by the generator and **is not**
   counted. This is the guard 2.8's flagged implementation choice needed and
   did not have -- an auto-generated card that the emptiness rule considers
   non-empty could never be dropped, and nothing was watching for one.
3. **"Attach photos" became "Add photos"** on the day workspace.
4. **The drawer kicker became "Choose existing Hornelore photos"**, which says
   which of the three sources it is rather than describing the drawer.
5. **The stale Upload instruction is gone from the empty picker.** It named a
   control that no longer exists in that workflow. Chris ruled on exactly this
   distinction: *"This trip has no photos yet. That is the right empty state.
   The problem was the stale instruction telling you to use a control that no
   longer exists in that workflow, not the factual sentence itself."* The
   assertion guarding it is a **NotIn**, so a fourth destination cannot be
   quietly written back in.
6. **The empty picker drawer is compact.** A `tdl-photo-picker-bare` modifier
   the renderer adds only when nothing is pickable.

**Two test-record notes, because both are the shape of defect this document
keeps warning about.** `test_round_2_fixes_preserved` had its "Attach photos"
assertion *inverted* rather than deleted, so the old wording cannot return
unnoticed. And `test_the_removal_is_reported_after_it_happens` was a single
whole-function `assertIn` that had been green for the entire life of the
defect it was supposed to catch; it now slices to the two branches separately.
That is the sixth-shape guard failure -- a whole-file or whole-function search
matching the wrong occurrence of a literal that appears more than once -- and
it has now bitten twice. **Slice to the enclosing function first.**

Suites green on the device: `trip_days_reconcile` 28, `trip_days` 45,
`travel_doc_lab` 168, `travel_doc_doctrine` 6, `travel_doc_picker_ui` 24,
`travel_doc_surface_gates` 13, `travel_doc_shell_mount` 45,
`travel_doc_evidence_ui` 7.

**This section carries no live-smoke claim, and the commit says so about
itself:** *"no browser has rendered any of this. The compact drawer and the
new wording are both visual claims still unverified."* 2.6 applies unchanged.
Chris's ten-item visual verification list is still open.

### 2.10 Live smokes 9 and 10 -- what they actually proved

Run 2026-07-28 against the real serving stack, the real batch
`8b5b47cb-4298-43fc-8ea6-827a5916e460` (seven candidates, session expires
2026-08-04), with `HORNELORE_IMPORT_PROVENANCE=1` and
`HORNELORE_GOOGLE_PICKER=1` confirmed in the `.env` the shortcut-launched
stack uses. Both were run twice -- once from the browser, once independently
by Chris from a WSL terminal -- and the two runs agreed.

**Smoke 9: the deduplication half passed. The retry half did not, and it
found a real defect.** Chris's ruling, verbatim: *"Record the deduplication
portion as passed, but do not mark the retry behavior complete. It found a
real provider-compatibility defect."*

What passed, and it is not a small list: re-ingesting an existing batch
created **no** duplicate row, promoted **nothing**, wrote **no** `photos` row,
moved **no** batch counter, and left all seven rows `pending`. Totals held at
14 candidates / 5 batches / 18 photos / 13 links. The
`(batch_id, external_id)` uniqueness is doing its job in production.

What failed: all seven items returned `outcome: failed`, `reason:
hash_mismatch`, `retryable: false`. The cause is ruling 1.14 -- Google returns
different bytes for the same media item on a later fetch. **The side-effect-free
pre-flight `GET /sessions/{batch_id}` was used before every ingest, as its own
docstring requires**, and the batch stayed `open` throughout, so the
`_SESSION_UNUSABLE` hazard never fired. Corrective work order:
`WO-TRAVEL-DOC-PICKER-REINGEST-REPAIR-01`. Until it lands and smoke 9 re-runs
to `created: 0 / repaired: 0 / unchanged: 7 / failed: 0`, **the retry path is
unverified and must not be described as working.**

**Smoke 10: the browser half is complete and it is a confirmed failure.** One
violation out of thirteen scanned patterns. `GET /api/import-provenance/queue`
returns `candidates[].batch.external_ref`, proven by direct equality to be the
raw Google Picker session identifier. Corrective work order:
`WO-TRAVEL-DOC-PICKER-QUEUE-REF-LEAK-01`. Chris: *"Do not merely rename the
key or partially mask the value. The raw provider reference should remain
server-side."*

The twelve that passed are evidence about ruling 1.10 and deserve naming: 81
network requests, all to `localhost:8000`, no Google origin, no credential in
any URL or query string; the ingest response body clean on all thirteen; the
health endpoint reporting credential presence as **booleans only**, exactly as
spec §10.4 requires; the console clean with zero errors; and `match_reason`
clean, with the key `session_id` appearing nowhere -- the deliberate
`picker_session` naming works.

**The lesson is where the leak was, not that there was one.** Every guard
written *for the picker lane* held. The value escaped through a generic column
tuple on a shared route that predates the lane. A structural rule applied to a
producer does not automatically cover the surfaces that producer feeds, which
is why the corrective work order's contract test scans the **serialised whole
response** rather than an enumerated field list.

**[CORRECTED IN PLACE 2026-07-29 -- the paragraph that stood here was wrong
about where the logs are, and the log half is now closed.]** The retired text
read: *"The server-log half of smoke 10 is still open. `hornelore_data/logs`
is empty -- the server logs to Chris's terminal and that is the only copy. The
`google_picker:` lines have not yet been scanned, so whether a second leak
exists is unknown, not clear."* The middle sentence was **never true**. The
server writes to `.runtime/logs/` in the repo root -- `api.log` was 10,450,170
bytes and current at the moment that sentence was published. The mistake was
looking in one plausible directory, finding it empty, and reporting an absence
as a fact instead of as a failed search. **`hornelore_data/logs` being empty
was evidence about `hornelore_data/logs` and nothing else.**

**The server-log half of smoke 10 passes.** Scanned across all four log files
-- `api.log`, `tts.log`, `ui.log`, `useful.log` -- with the true Picker
session values read out of `import_batch.external_ref` and grepped for
directly, rather than by pattern-guessing what a session id looks like:

- The two real Picker session values occur **zero** times in any log file.
- `ya29.`, `GOCSPX`, `client_secret`, `refresh_token`, `baseUrl`, `base_url`,
  `googleusercontent`, `googleapis.com`, `Authorization` and `Bearer ` occur
  **zero** times in any log file.
- `google_picker: minted access token, expires_in=3599s` reports no value, no
  prefix and no length -- spec §10.4 satisfied at the one line most likely to
  violate it.
- `google_picker: created picker session` deliberately logs **no** identifier.
- The UUID that does appear, in `opened batch` and `ingest for batch` lines
  and in access-log paths, is Hornelore's internal `batch_id`. That is the
  identifier ruling 1.10 wants in the open.
- `session_id` appears 645 times in `api.log` and **every** occurrence is the
  transcript/narration subsystem's own query parameter. Same word, unrelated
  lane -- which is the guard-writing rule showing up in a security scan.

**One advisory finding, not a violation, and it is Chris's to rule on.** The
21 `google_picker: downloaded item <id> -- <n> byte(s)` lines log the raw
Google **media item id**. It is not on the forbidden list -- it is not a
credential, not a bearer-scoped URL, and Hornelore already stores it as
`external_id` -- but it is a raw provider reference sitting in a log, and 1.10
is about where provider references are allowed to be, so the question is
legitimate and is recorded rather than answered here.

**The logs also confirmed ruling 1.14 a third time, from a source that is
neither the browser nor Chris's terminal.** `api.log` holds the *original*
creating ingest of 2026-07-28 12:40 as well as the two later runs, so the same
seven media items were fetched from Google three times and the server logged
its own byte count each time:

| media item (tail) | 12:39 (stored) | 17:42 | 17:55 |
| --- | --- | --- | --- |
| `...HthQ` | 4477047 | 4477050 | 4477049 |
| `...fRVjRA` | 4749520 | 4749519 | 4749521 |
| `...piqEOA` | 5954602 | 5954601 | 5954602 |
| `...WoXxA` | 4375462 | 4375462 | 4375463 |
| `...Jv60Q` | 5621898 | 5621900 | 5621899 |
| `...PXMHw` | 5658815 | 5658816 | 5658816 |
| `...i0kA` | 3275572 | 3275569 | 3275569 |

Two items returned **three different sizes in three fetches**. All seven
differ from the stored size on at least one later run. The stored column is
not a separate measurement -- it is the 12:39 run, which is the point: the
hash on the row is the checksum of the copy Hornelore kept from one particular
fetch, exactly as 1.14 says.

**The browser-side failure stands regardless**, and
`WO-TRAVEL-DOC-PICKER-QUEUE-REF-LEAK-01` is unaffected by any of this. A clean
log is not a clean response body; they are different surfaces and were scanned
separately on purpose.

---

## Part 3 — Deferred or not started

Each item here was considered and consciously left. The reason is the point.

### 3.1 Phase 3 — promotion unlock

Adding `google_photos_picker` to `PROMOTABLE_SOURCES`, so a reviewed picker
candidate can become a `photos` row. Not started. It is gated behind the fetch
lane existing, which it now does, and behind 3.3.

### 3.2 ~~Phase 2D~~ / Phase 4 — the operator affordance

**The 2D half moved to 2.5 on 2026-07-28. It is struck here rather than
deleted, per this document's own Maintenance rule.** It read, in full:

> The minimal Picker UI: open picker, check selection, ingest, refresh queue.
> Deliberately sequenced *after* 2A and 2B were reviewed and committed, so
> that the UI cannot hide a server defect. Bound in advance by ruling 1.3.

All four of those verbs shipped, in that sequencing, bound by that ruling.
The sentence about sequencing is the one worth keeping in view: it was
written as a plan and 2D is the evidence it was followed, which is a
different and better thing than a plan nobody checked afterwards.

**Phase 4 has not landed and does not move.** What 2.5 shipped is the
*minimal* affordance — a strip that opens a session, polls it, ingests it and
hands off to the queue. Anything past that (batch history, a re-open of a
prior batch, a persisted per-run failure summary — see 3.4) is Phase 4 and is
subject to 1.3 exactly as 2D was. A strip that grows a list of past runs with
controls on them has become the second queue ruling 1.3 forbids, and it will
get there one reasonable-looking feature at a time if nobody is counting.

### 3.3 The promote-time re-hash check (spec §8)

`store_photo_file()` will re-hash the staged file at promote time. If the
staged bytes and the ingest-time `file_hash` ever disagree, promotion should
refuse rather than reconcile. That check does not exist and belongs to Phase
3. This is on the record as an open risk, not as an oversight.

### 3.4 A persisted per-run failure summary (spec §12.4)

**Still not started. Scheduled, and no longer optional, as of 2026-07-28.**

[This section read, in full: "There is no home for one. The ingest route
returns partial successes and failures in its HTTP response and that is where a
run's outcome lives. Giving it a table means schema, and schema is not
improvised inside a phase." Every sentence of that is still literally true.
What changed is what it costs.]

Two things landed on 2026-07-28 that turned this from a convenience into a
gap. **Ruling 1.13** says a failed acquisition gets no candidate row, so the
receipt is the only record it ever gets — and a receipt that lives in an HTTP
response is gone the moment the operator reloads. A failure you can see exactly
once, and only if you were looking, is close to a failure nobody recorded.
**And Chris ruled the same day that a Retry control must work tomorrow, not
only in the tab that ran the import** — which is not implementable on top of a
response nobody kept.

He therefore pulled this forward out of Phase 4 and into **Phase B of
`WO-TRIP-PLAN-AS-HUB-01`**. The schema wall in the retired text is not waived
by that: it means the table gets designed in a phase that is *about* designing
it, which is the whole content of the original objection.

### 3.5 ~~Video, and a live divergence from the spec~~ — RULED 2026-07-28

**Answered by ruling 1.13. Struck here rather than deleted, and struck rather
than moved, because the question is the useful part of the record: the ruling
reads as obvious once given, and this section is the evidence that it was not.**

It read, in full:

> Video is out of scope for this work order — supporting it pulls in the media
> archive lane, which is a different work order. That much is settled. *How* a
> picked video is turned away is not, and the code and the spec currently
> disagree.
>
> Spec §7(c) recommends landing a picked video as a candidate in state `error`
> with reason `"video not supported by this lane"`, so that it is visible rather
> than silently dropped. The implementation refuses it outright and creates no
> candidate row at all.
>
> Both are defensible — a row makes the refusal auditable, no row keeps the lane
> strictly photographic — and the divergence is recorded here rather than
> resolved, because it is Chris's call and not an agent's. Until he rules, the
> code is the behaviour and §7(c) is a recommendation that was not taken.

**The ruling went to the code, and for a reason neither side of the divergence
had stated.** The argument recorded above was auditability against lane purity,
and on those terms it really is a coin toss. Chris ruled on a third axis: a
candidate row is Hornelore's claim to be *holding something reviewable*, and a
video it never downloaded is not that. The receipt keeps the refusal auditable
without the row having to.

**Video itself remains out of scope**, exactly as the first paragraph said, and
that half was never in question. What is settled now is only how a picked video
is turned away: reported in the receipt, no row. See 1.13, and see 3.4 for the
receipt's own unfinished half.

### 3.6 Google Takeout

Different lane, different work order. It stays out of `PROMOTABLE_SOURCES`
even after Phase 3.

### 3.7 Lori Review Assistant

Out of scope for the whole picker work order.

### 3.8 New dependencies

Everything on this lane is `requests` plus the standard library.
`google-auth` and `google-api-python-client` were explicitly rejected: they
would be environment work, and they buy nothing over a twenty-line token
exchange.

---

## Part 4 — Future design only

Nothing here is implemented, scheduled, or citable as a constraint.

### 4.1 Multi-operator

`docs/wo/WO-LOREVOX-MULTI-OPERATOR-GOOGLE-AUTH-01_Spec.md` is marked FUTURE
DESIGN ONLY. Phase 1's single-operator, local posture is a deliberate ceiling
and not an unfinished edge — ruling 1.9 is what the eventual multi-operator
design has to satisfy, not something it gets to relax.

### 4.2 A retryable acquisition state machine (spec §12.3)

A future work order may add acquisition states (`listed` / `downloading` /
`staged` / `fetch_error`) distinct from the operator-decision states. That
needs schema and repository design. It must not be improvised inside Phase 2,
and until it exists, ruling 1.6 is the whole of the answer.

---

## Corrections to the record made by this document

Made in place rather than deleted, because a claim that was true when written
and a claim that was never true are different facts.

In `docs/wo/WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md`:

- Line 3, `**Status:** SPEC ONLY. No code written.` — false since Phase 1
  landed on 2026-07-27.
- Line 483, the §12 heading `(recorded 2026-07-27, NOT implemented)` — false
  since Phase 2A landed.
- Line 487, `**No Phase 2 code exists.**` — the sentence this document was
  chartered to correct. The rulings around it were and remain true, which is
  exactly why it survived a day of being read.

In `CLAUDE.md`:

- Line 129 was stale in three places: it called `.venv` the test venv "at
  fastapi 0.136.1 / starlette 1.0.0", said the two venvs "are not
  interchangeable", and said "There is no `requirements-test.txt`" when that
  file exists, is dated 2026-07-27, and pins what is actually installed.
  `WO-WEB-STACK-TEST-ENV-ALIGNMENT-01` had already made all three false.
- Line 214 listed WO specs as living at the repo root, contradicting line 18,
  line 384 and the checklist's own tree. Root does still carry 29 legacy
  `WO-*_Spec.md` / `BUG-*_Spec.md` files against 28 in `docs/wo/`, so the row
  was half-true and mis-scoped — the worst kind to leave, since it reads as
  confirmation.
- The Phase 2B changelog entry's `Open items:` bullet opened "Not yet run in
  `.venv` and not yet live-proven against Google" six lines below the same
  entry's own record of **193 tests, OK**, run by Chris in `.venv` before that
  unit was committed. The entry contradicted itself for a day. Only the live
  half was ever true.

Dated changelog entries below the current ones were left alone. The
2026-07-26 entry still says the suite runs under fastapi 0.136.1, and that is
correct: it is a record of what was true on 2026-07-26, not a claim about now.
Rewriting past log entries would destroy the record rather than correct it.

In `MASTER_WORK_ORDER_CHECKLIST.md`:

- The `**Active as of:**` line carried the same two retired claims — "NOT YET
  RUN IN `.venv`" and "CHRIS MUST RE-RUN ALL THREE SUITES IN `.venv` UNDER WSL
  BEFORE THIS IS TREATED AS VERIFIED" — and was corrected on demotion rather
  than demoted verbatim, which is the one case where verbatim demotion would
  have preserved a falsehood instead of a record.
- "Root carries operational files only" in *Where things live now* is not yet
  true, for the same 29 files that made `CLAUDE.md` line 214 half-true.
  Recorded, not fixed: moving them is its own work order.
- The `**Active as of:**` Phase A line carried eight claims that Chris's
  2026-07-28 review retired: the scope line "UI, TESTS AND DOCS ONLY — no
  `server/` file"; that `maybeAutoAddMissingDays()` fires "once per trip";
  "ONLY THE ADD HALF OF THE SHRINKING-DATES RULING SHIPPED"; "this surface
  has no route that removes a day card at all"; the banner wording "They were
  kept, not deleted, because they have your work on them."; the count
  `tests/test_travel_doc_lab.py` 161 OK; the deferral of "a server route that
  drops empty out-of-range days"; and the standing demand that Chris re-run
  the suites in `.venv` before the phase is treated as verified. Each was
  corrected in place with the retired wording quoted beside it and dated,
  because that line is the live record — a live record that is only ever
  appended to stops being readable at the top, which is the whole reason it
  sits on one line.


In `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` itself, on 2026-07-29:

- 2.6's third sentence, "The live smoke against a real Picker session is the
  next gate and it has not been run", was retired by smokes 9 and 10 and
  corrected in place with the retired wording quoted. Its first two sentences
  had been retired a day earlier by the Phase 2B live run and are corrected in
  the same paragraph.
- The `ingest_picker_session` docstring's idempotency claim -- *"Running it
  twice over the same selection creates nothing the second time"* -- is
  **true**, and the sentence after it is not: *"the re-ingest branch above
  checks the bytes against the hash already on the row before it will replace
  anything"* describes checking freshly downloaded bytes, which is the defect
  smoke 9 found. It is corrected by
  `WO-TRAVEL-DOC-PICKER-REINGEST-REPAIR-01`, in code, not here -- recorded in
  this list so the two halves of one docstring are not confused for each
  other.
- The ingest response's `next` string, *"nothing already landed is
  re-downloaded"*, is false today. Chris: *"It is factually false today."*
  Also corrected by that work order.
- 2.10's closing paragraph claimed `hornelore_data/logs` is empty and that
  "the server logs to Chris's terminal and that is the only copy". **Never
  true.** The server writes to `.runtime/logs/`. Corrected in place at 2.10
  with the retired wording quoted. The same false claim was published in the
  same commit in `CLAUDE.md`'s 2026-07-29 changelog entry and in the
  checklist's `**Active as of:**` line; the checklist line is corrected in
  place, and the changelog entry is **left standing and retired by a later
  dated entry**, because a changelog is a record of what was believed on a
  date and rewriting it would destroy the evidence that the mistake happened.

---

## What this document is and is not

**This document IS:**

- The single place the travel-document lane doctrine is stated, so a WO author
  does not have to reconstruct it from four specs and two CLAUDE.md sections
- Binding on every future evidence producer, not only on the Google Photos
  Picker
- A record that separates what was decided from what was built from what was
  deliberately skipped from what is merely imagined
- The place a stale claim gets corrected rather than quietly overwritten

**This document IS NOT:**

- A Work Order (no acceptance gates, no files-changed, no test coverage)
- A schema reference (the lanes are named; their columns live in the
  migrations and in `import_repository.py`)
- An API specification (route shapes belong to the WO specs)
- A roadmap (Part 3 and Part 4 carry no dates and no commitments)
- A substitute for the picker spec, which remains the detailed decision record
  for that work order

---

## Maintenance

This document is updated whenever:

- A new evidence lane is introduced, or an existing lane's contents change
- A new external producer is added, so its lane assignment is recorded here
  before it is built
- A ruling in Part 1 is overturned — in which case the old ruling is struck
  through and dated, not removed
- A phase lands, in which case **Part 2 is the part that moves** and its
  heading date moves with it
- An item leaves Part 3 or Part 4, in which case it moves rather than being
  deleted from one and retyped into the other

**Part 2 is the perishable part.** If this document is ever found
disagreeing with the tree, assume Part 2 is wrong and the tree is right, then
fix Part 2 and say so in the changelog.

Read together with `CLAUDE.md`'s two permanent-doctrine sections before
authoring any WO that touches trips, photos, or imported evidence.

---

## Related artifacts

- `docs/wo/WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md` — the picker work
  order; §12 holds the Phase 2 rulings this document generalises, and §12.7 is
  restated here in full at 1.1
- `docs/wo/WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01_Spec.md` — migration
  0037; built the `import_batch` / `import_candidate` lane
- `docs/wo/WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01_Spec.md` — built the review
  screen that ruling 1.3 declares authoritative
- `docs/wo/WO-TRAVEL-DOC-UNIFY-01_Spec.md` — the unification arc these lanes
  sit inside
- `docs/wo/WO-LOREVOX-MULTI-OPERATOR-GOOGLE-AUTH-01_Spec.md` — FUTURE DESIGN
  ONLY; see 4.1
- `docs/wo/WO-TRAVEL-DOC-PICKER-REINGEST-REPAIR-01_Spec.md` -- opened
  2026-07-29; implements ruling 1.14 after live smoke 9
- `docs/wo/WO-TRAVEL-DOC-PICKER-QUEUE-REF-LEAK-01_Spec.md` -- opened
  2026-07-29; removes the raw Picker session id from the queue payload after
  live smoke 10
- `CLAUDE.md` — "Travel Doc Evidence + Web Context Rule (permanent doctrine,
  2026-07-10)" and "Google Photos Picker identity boundary (permanent
  doctrine, 2026-07-27)"
- `MASTER_WORK_ORDER_CHECKLIST.md` — phase status; the checklist is the
  schedule, this document is the doctrine

---

## Closing note

The lanes were always plural. What was missing was a document that said so in
one place, and that could be checked without trusting the person who wrote it.

Evidence enters where its type says it enters, an operator decides, and
nothing else does.
