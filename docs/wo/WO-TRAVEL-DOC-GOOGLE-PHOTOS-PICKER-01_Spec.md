# WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 — Google Photos Picker into the Evidence Queue

**Status:** SPEC ONLY. No code written. Awaiting Chris's decisions in §7.
**Opened:** 2026-07-27
**Predecessors:** WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 (migration 0037),
WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 (the review screen), WO-MEMOIR-TRIP-STORY-LANE-01.

---

## 1. Goal

Bring real Google Photos into the evidence queue as `import_candidate` rows on a
`google_photos_picker` batch, so the operator reviews actual trip photographs on the
screen that already exists instead of hand-uploading them one at a time.

This is the next major Travel Doc producer. Everything downstream of it — the review
queue, the promotion path, the trip binding, the memoir trip lane — already shipped.
The only missing piece is the producer.

---

## 2. The hole this closes, stated by the code itself

`server/code/api/services/import_repository.py` already reserved the shape:

```python
IMPORT_SOURCES = ("google_photos_picker", "google_takeout", "local_upload", "csv", "manual")
PROMOTABLE_SOURCES = ("local_upload", "manual")
```

and the comment on `PROMOTABLE_SOURCES` is the exact statement of the problem:

> The provider-side sources are deliberately absent: `google_photos_picker` and
> `google_takeout` each have to fetch their own bytes through their own lane first,
> and `csv` is a manifest of claims about files nobody has handed us. Adding a source
> here without also building its fetch would turn promotion into a way to mint photo
> rows for images that do not exist.

`server/code/api/routers/import_provenance.py` line 66 says the same thing from the
route side: *"There is no Google Photos and no Takeout here."*

So this work order is not "add a source string." It is **build the fetch lane**, and
only then is `google_photos_picker` allowed to join `PROMOTABLE_SOURCES`.

---

## 3. Recon — what already exists and will be reused, not rebuilt

| Thing | Where | Why it matters here |
|---|---|---|
| `import_batch` / `import_candidate` DDL | `server/code/db/migrations/0037_import_provenance_foundation.sql` | The landing zone. `source` CHECK already permits `google_photos_picker`. **No new migration is needed.** |
| `candidate_create(batch_id, external_id, file_hash, filename, mime_type, byte_size, taken_at, taken_at_source, latitude, longitude, location_source, match_reason, match_confidence, trip_id, candidate_id)` | `import_repository.py:635` | Idempotent on `(batch_id, external_id)` — returns the existing id rather than raising. This is what makes a re-poll of the same picker session safe. |
| `candidate_promote()` | `import_repository.py:~1465` | Resolution order: existing `photo_id` → `file_hash` match → `source_path` + `sha256_file` + `store_photo_file` → else `PhotoBytesMissingError`. Branch 3 is the one a picker fetch lane feeds. |
| `sha256_file()`, `store_photo_file()` | `server/code/services/photo_intake/storage.py` | Hashing and archive placement. Already used by `POST /api/photos`. |
| `extract_exif()` (GPSInfo handling at `exif.py:238-274`) | `server/code/services/photo_intake/exif.py:176` | **The only source of GPS for a picked photo.** See §4. |
| `classify_metadata_trust()` | `photo_intake/metadata_trust.py` | Scanned-film / stripped-share / pristine classification, already applied on the upload path. |
| The EXIF auto-fill block | `server/code/api/routers/photos.py:520-600` | The precedent to copy: EXIF fills only what the operator left blank, raw tag map always preserved into `metadata_json` as a non-authoritative forensic trail. |
| Evidence Review Queue screen | `ui/js/travel-doc-lab.js` (`EVIDENCE_BASE = "/api/import-provenance"`, `renderEvidence()` at 5070, `reloadEvidence()` at ~5018) | Where the "Import from Google Photos" affordance goes. Surfaced by `ui/travel-doc-lab.html`. |
| Flag pattern | `server/code/api/flags.py`; `import_provenance.py:110` reads `HORNELORE_IMPORT_PROVENANCE` inline | Default-OFF, all routes 404 while off, and the UI already renders a dedicated explanatory panel on 404 (`st.evidenceOff`). |
| `requests` | `.venv 2.33.1` / `.venv-gpu 2.32.5`, both present | The whole HTTP surface can be built on this. See §7a. |

**There is no Google, OAuth, or picker code anywhere in `server/code` today.** There are
no google/oauth Python dependencies in either venv (`.venv-gpu`'s `google` namespace is
protobuf only). There are no `GOOGLE_*` keys in `.env.example`.

---

## 4. The Picker API as actually verified (Google's live docs, 2026-07-27)

Host `https://photospicker.googleapis.com/v1`.

- `POST /v1/sessions` → `PickingSession {id, pickerUri, mediaItemsSet, pollingConfig{pollInterval, timeoutIn}}`
- `GET /v1/sessions/{sessionId}` → poll until `mediaItemsSet` is true
- `DELETE /v1/sessions/{sessionId}`
- `GET /v1/mediaItems?sessionId=...&pageSize=...&pageToken=...` (pageSize max 100, default 50)

`PickedMediaItem { id, createTime, type, mediaFile }`
`MediaFile { baseUrl, mimeType, filename, mediaFileMetadata }`
`MediaFileMetadata { width, height, cameraMake, cameraModel, photoMetadata, videoMetadata }`

Bytes: `baseUrl + "=d"` with an `Authorization: Bearer <token>` header. Google's docs
state `=d` returns all metadata **except location**.

Scope: `https://www.googleapis.com/auth/photospicker.mediaitems.readonly` — the only one
needed, and it covers create/get/delete session plus list media items.

### The four constraints that determine the architecture

**C1 — There is no GPS anywhere in the Picker response.** Not on `PickedMediaItem`, not
on `MediaFile`, not on `MediaFileMetadata`. Location can only come from EXIF in the
downloaded bytes. Consequence: a picker candidate's `location_source` is `exif_gps` when
EXIF carries GPS and `unknown` otherwise. It is **never** `provider_metadata`, because
the provider does not supply location.

**C2 — There is no byte-size field anywhere in the Picker response.** `byte_size` must
come from `os.stat()` on the downloaded file, and `file_hash` from `sha256_file()`.

**C3 — `baseUrl` is valid for 60 minutes**, sooner if the user revokes access. This is
the load-bearing constraint. A "land candidate rows now, fetch bytes on promote later"
design is dead on arrival past an hour — which is precisely why the existing
`PROMOTABLE_SOURCES` comment says a provider-side import must fetch its own bytes
through its own lane first. **The bytes must be fetched during ingest, not at promote.**

**C4 — OAuth verification review is required**, independent of and additional to the
Google Photos APIs partner program. And the operational sting: a Google Cloud project
whose OAuth consent screen is external-type with publishing status **"Testing"** issues
refresh tokens that **expire in 7 days** unless the only scopes requested are a subset of
name/email/profile. The picker scope is not in that subset. So in Testing status Chris
would re-authorize weekly. Publishing the app removes that, but publishing is what
triggers the verification review. This is a real cost and it is his call, not mine — see
§7d.

---

## 5. Proposed architecture

Two new server modules and one new router. **No new migration. No new table. No change
to `import_repository.py`'s rules.**

```
server/code/services/google_picker/
    __init__.py
    oauth.py          # refresh_token -> access_token, in-process cache, never logged
    picker_client.py  # thin requests wrapper over the four Picker endpoints
    ingest.py         # download -> hash -> exif -> candidate_create
server/code/api/routers/google_picker.py
```

### Phase 1 — credentials + session lifecycle (no bytes, no candidates)

`oauth.py` exchanges `GOOGLE_PICKER_REFRESH_TOKEN` for an access token via a plain
`POST https://oauth2.googleapis.com/token` using `requests`, reading
`GOOGLE_PICKER_CLIENT_ID` / `GOOGLE_PICKER_CLIENT_SECRET` / `GOOGLE_PICKER_REFRESH_TOKEN`
from the process environment. The access token is cached in memory with its expiry and
**never** written to the DB, never logged, never returned in a response body. This is
import rule 3 (`NO RAW EXTERNAL TOKENS`) honoured at the source: *"the real rule is that
credentials live in the process environment."*

New router `server/code/api/routers/google_picker.py`, gated behind
`HORNELORE_GOOGLE_PICKER=1` **and** `HORNELORE_IMPORT_PROVENANCE=1` — 404 while either is
off, matching every other lane and matching what the queue UI already knows how to render.

| Route | Does |
|---|---|
| `GET /api/google-picker/health` | Reports flag state and whether all three credential env keys are present. **Reports presence as a boolean. Never echoes a value, not even truncated.** |
| `POST /api/google-picker/sessions` | Body `{person_id, trip_id?}`. Creates the Picker session AND the `import_batch` with `source="google_photos_picker"` in one call, storing the Picker `sessionId` as the batch's `external_ref` — which is what that
column was built for; 0037's comment on it reads *"Opaque provider-side handle for the
fetch (an album id, a Takeout archive name, an upload session id). NOT a token, NOT a
URL with credentials in it."* Returns `{batch_id, picker_uri, poll_interval, timeout_in}`. |
| `GET /api/google-picker/sessions/{batch_id}` | Polls Google, returns `{media_items_set, expires_hint}`. |
| `DELETE /api/google-picker/sessions/{batch_id}` | Deletes the Picker session at Google. Does **not** delete the batch — no DELETE on this lane, ever. The batch closes or stays open. |

Phase 1 acceptance: with the flag on and credentials set, `POST /sessions` returns a
`pickerUri` Chris can open, and `GET` flips to `media_items_set: true` after he picks.
No candidate rows are created in Phase 1.

### Phase 2 — the fetch lane (this is the phase that closes the hole)

`POST /api/google-picker/sessions/{batch_id}/ingest`

For each `PickedMediaItem` across all pages:

1. Skip `type != PHOTO` unless §7c says otherwise.
2. `GET baseUrl + "=d"` with the Bearer header, streamed to a temp file (same
   `tempfile.mkstemp` + chunked-write shape as `upload_photo`).
3. `file_hash = sha256_file(tmp)`; `byte_size = os.stat(tmp).st_size`  ← closes C2.
4. `exif = extract_exif(tmp)` → `captured_at`, `gps`  ← closes C1.
5. Move the temp file into a **staging area keyed by candidate id**, not into the photo
   archive. Proposed: `C:\hornelore_data\import_staging\<batch_id>\<candidate_id>.<ext>`.
   **Intake is not approval.** A rejected candidate must never have minted a `photos` row,
   so `store_photo_file()` is not called at ingest — it is called at promote, from the
   staged path, through `candidate_promote()`'s existing branch 3.
6. `candidate_create(batch_id=..., external_id=item.id, file_hash=..., filename=mediaFile.filename, mime_type=mediaFile.mimeType, byte_size=..., taken_at=<exif captured_at, else item.createTime>, taken_at_source=<"exif" | "provider_metadata">, latitude/longitude=<exif gps or None>, location_source=<"exif_gps" | "unknown">, match_reason={...}, trip_id=<batch trip_id>)`.

`match_reason` carries the forensic trail — the picker session handle,
`cameraMake`/`cameraModel`, width/height, `metadata_trust`, and which fields EXIF supplied
versus which came from `createTime`. It round-trips verbatim (0037 made that column JSON
precisely so the review screen sees what the importer saw).

**Phase 2 landmine — key naming inside `match_reason`.** `import_repository._assert_reason_clean()`
(the `_SECRET_KEY_HINTS` tuple at `import_repository.py:277`) refuses any `match_reason` KEY whose
lowercased name *contains* one of `token`, `secret`, `password`, `passwd`, `authorization`, `auth`,
`credential`, `cookie`, `api_key`, `apikey`, `private_key`, **`session_id`**, `bearer` — raising
`ExternalTokenError`. So the obvious key names `session_id` and `picker_session_id` are both
REFUSED. Phase 2 must use **`picker_session`** (no `session_id`, `auth` or `token` substring).
This is a guard doing its job, not a bug: the guard cannot tell a session handle from a token by
looking at the value, so it judges the key name. The batch's `external_ref` is the other half of
the same story and is safe — `_assert_no_secret()` runs `_TOKEN_PATTERNS` against the VALUE there,
and a plain Picker session id matches none of them.

Idempotency: `candidate_create` is already idempotent on `(batch_id, external_id)`, so
re-running ingest after a partial failure resumes instead of duplicating. Any item whose
download fails lands as a candidate in state `error` with the reason recorded — not
silently dropped, and not deleted.

The 60-minute clock (C3): ingest records the session creation time and refuses to start
if the window has already closed, with a clear message telling Chris to re-pick rather
than a wall of 403s from Google.

### Phase 3 — promotion unlock

Only once Phase 2 is green and has staged real bytes:

```python
PROMOTABLE_SOURCES = ("local_upload", "manual", "google_photos_picker")
```

plus the staged path threaded into `candidate_promote()`'s `source_path`. The comment on
`PROMOTABLE_SOURCES` gets amended to say the picker's fetch lane now exists and where it
lives. `google_takeout` stays out.

### Phase 4 — the Evidence tab affordance

An "Import from Google Photos" button in `renderEvidence()`, in-panel only (no native
prompt/confirm/alert), that: creates the session, shows the `pickerUri` as a link Chris
opens himself, polls on `pollingConfig.pollInterval`, then calls ingest and reloads the
queue. Wording follows the no-DELETE screen contract — Hide / Unhide / Retire from queue.

**Each phase is a scope wall. One phase per session.**

---

## 6. What this work order does NOT do

- No Google Takeout. Different lane, different work order.
- No Lori Review Assistant.
- No DELETE anywhere on the import/evidence lane, including for failed downloads.
- No new migration and no schema change.
- No change to the five candidate states.
- No new Python dependency. Everything is `requests` + stdlib. (`google-auth` /
  `google-api-python-client` are explicitly rejected — they would be environment work,
  which is closed for this session, and they buy nothing over a 20-line token exchange.)
- No `.venv-gpu` / `requirements-gpu.txt` change.
- No handling of Chris's Google credentials by me, in any form, at any point.

---

## 7. Decisions that are Chris's

**(a) Credential path.** Recommendation: `GOOGLE_PICKER_CLIENT_ID`,
`GOOGLE_PICKER_CLIENT_SECRET`, `GOOGLE_PICKER_REFRESH_TOKEN` in `.env` (gitignored at
`.gitignore:90`), exchanged for short-lived access tokens at call time. Adds no
dependency and satisfies import rule 3 directly. **Chris does the Google Cloud console
work and the one-time authorization himself; I never see, enter, or handle the values.**
I will write `.env.example` documentation lines with empty values and a `GET /health`
endpoint that reports presence as a boolean only.

**(b) Fetch-at-ingest vs land-then-fetch.** Recommendation: **fetch at ingest**, per C3.
Land-then-fetch cannot survive the 60-minute `baseUrl` window and would reintroduce
exactly the "photo rows for images that do not exist" failure the existing code warns
about. The cost is that ingest is a long-running call over N photos; mitigated by
idempotent resume.

**(c) Videos.** The Picker returns `type: VIDEO` items. Recommendation: **ingest photos
only in this work order**, and land any picked video as a candidate in state `error` with
reason `"video not supported by this lane"` so it is visible rather than silently
dropped. The alternative — supporting video — pulls in the media archive lane and is a
different work order.

**(d) OAuth publishing status.** In "Testing" the refresh token expires every 7 days
(§4 C4). Options: live with weekly re-authorization while this is a single-operator tool,
or go through Google's OAuth verification review. Recommendation: **stay in Testing for
now** — the re-auth is a two-minute browser step, and verification review is not worth
starting until the lane is proven. The `GET /health` endpoint will make an expired token
obvious instead of mysterious.

**(e) Trip binding.** Does a picker batch auto-bind to the currently selected trip?
Recommendation: **yes, when a trip is selected**, passing `trip_id` through to both the
batch and each candidate — the operator is standing in a trip when they click the button,
and `PATCH /batches/{id}/trip` already exists to correct a mistake. Candidates cannot
cross the person/trip boundary afterward, which is the safety net.

**(f) Staging location.** `C:\hornelore_data\import_staging\<batch_id>\` is a new
directory under the data root. Chris owns that root and runs all destructive operations
there. Nothing in this work order deletes from it; staged bytes for rejected candidates
accumulate until a future maintenance work order defines a guarded sweep. Flagging this
now rather than discovering it as disk growth later.

---

## 8. Open risk I want on the record

`store_photo_file()` at promote time will re-hash the staged file. If the staged bytes
and the ingest-time `file_hash` ever disagree, promotion should refuse rather than
reconcile. That check does not exist yet and belongs in Phase 3.

---

## 9. Recon gaps closed this session

- Migration 0037's file, previously unlocated, is
  `server/code/db/migrations/0037_import_provenance_foundation.sql`. The migrations
  directory is `server/code/db/migrations/`, highest number 0037. Earlier notes said
  `server/` had no migrations directory — **that was wrong**; the search was scoped to
  `server/schema` and `server/code/api`.
- Work-order specs live in `docs/wo/` as `<NAME>_Spec.md`. `docs/reports/` holds audits
  and run reports. This file follows the `docs/wo/` convention.

---

## 10. Identity boundary — who owns what (Phase 1 doctrine, binding)

This section exists because media-import systems fail in one predictable way:
they collapse the source provider's identity into the application's domain
model. Once that happens, "whose photo is this?" is answered by whoever
happened to be signed in to Google, and the answer is wrong the first time a
second person is involved. The boundary below is set now, while the lane is
still dark, so no later phase can drift across it.

### 10.1 Five separate things

| Thing | What it owns | Where it lives |
| --- | --- | --- |
| **Google Cloud project / OAuth client** | App registration, consent screen, publishing status, authorized redirect URIs, client id + secret, and **API quota**. | Google Cloud console. Configured once by Chris. |
| **Authorized Google account** | The **source library** the picker picks from. This is the account that granted the refresh token. | Google. Referenced only by the refresh token in `.env`. |
| **Hornelore operator** | Drives the import. Clicks the picker, decides what gets filed where. | Phase 1: implicit — there is exactly one, locally. |
| **Hornelore person (narrator)** | The **destination** identity. Whose evidence queue and whose photo library the picked media lands in. | `person_id`, an explicit request field. |
| **Hornelore trip** | The optional destination sub-scope inside that person. | `trip_id`, an explicit request field. |

The Cloud project and the authorized account are **not the same account and
must not be described as if they were**. It is normal and expected for the
Cloud project to sit under one address (e.g. a development address) while the
photo library being picked from belongs to a different personal Google
account. Quota belongs to the project; photos belong to the account.

### 10.2 The core rule

> **A Google account is not a Hornelore narrator.**
> **An operator is not a narrator** unless a human explicitly selected that
> narrator as the destination.
> **The application must never infer `person_id` or `trip_id` from the Google
> account** — not from its email address, not from its display name, not from
> its subject id, not from anything in the picker payload.

Destination is always **explicit, and supplied by the request**. There is no
default, no fallback, and no "if only one person exists, use that one."

The Phase 1 code already obeys this. `SessionCreateBody.person_id` is
`Field(..., min_length=1)` — required, never defaulted — and the router's own
docstring records why: a picker session that inferred its person would be one
bad inference away from landing someone else's photographs in a narrator's
evidence queue. `repo.batch_create()` then re-checks the same thing server-side
via `_assert_person_exists` (raises `CrossPersonError`) and
`_assert_trip_owned_by` (raises `CrossTripError` for an unknown trip **and** for
a trip owned by a different person).

### 10.3 `narrator_id` is not a third destination field

Earlier drafts of this doctrine listed `person_id`, `narrator_id`, and
`trip_id` as three destination fields. **That is wrong for this repository**
and would have written a fiction into the docs.

`narrator_id` is the **`photos` table's column name for the same identity that
the import lane calls `person_id`**. They are not two identities; they are one
identity under two column names, and the repository compares them directly:

```python
# server/code/api/services/import_repository.py
"SELECT narrator_id FROM photos WHERE id = ?", (photo_id,)   # :403
if row["narrator_id"] != person_id:                          # :407
    ... % (photo_id, row["narrator_id"], person_id)           # :412

"SELECT id, narrator_id, deleted_at FROM photos "            # :1597
if clash["narrator_id"] != person_id:                        # :1604
```

That comparison **is** the cross-person guard. So the accurate statement is:

- The destination is **`person_id`**, optionally narrowed by **`trip_id`**.
- **`narrator_id`** is the `photos`-table column holding that same person, and
  the repository already refuses any operation where the two disagree.

Any future doc or code that treats `narrator_id` as a separately-suppliable
destination field is introducing a bug, not a feature.

### 10.4 Phase 1 is local, single-operator, and that is a deliberate ceiling

- Phase 1 is **local / single-operator only**.
- **One global `.env` refresh token is acceptable** for Chris's local proof.
- That token authorizes **one Google Photos source account**. It says nothing
  about who the photos are *for*.
- **Do not create per-narrator Google credentials.** Ever. Not in Phase 1, not
  in the multi-operator design. Credentials belong to humans who sign in, not
  to memoir subjects who may be elderly, deceased, or otherwise incapable of
  holding an OAuth grant. This is the single most important line in this
  section.
- **Do not store raw Google tokens in SQLite.** Phase 1 holds the access token
  in a process-local memory cache only (`oauth._cached_token`), and it dies
  with the process.
- **Do not log, echo, or display token values** — no full values, no prefixes,
  no lengths, no masked tails.
- **The health endpoint may report credential presence as booleans only. It
  must never return raw or truncated credential values.** `credentials_present()`
  returns `{key: bool(...)}` and nothing else, by construction.

### 10.5 What this means for later phases

When Phase 2 files a picked media item, the destination comes from the batch
that Phase 1 opened, which got it from the operator's explicit request. It does
not come from the picker payload. The picker payload contributes bytes,
filename, mime type, timestamps, and the Google media id — **evidence**, not
**identity**.

The multi-operator future — where each Lorevox operator connects their own
Google account — is designed in
`docs/wo/WO-LOREVOX-MULTI-OPERATOR-GOOGLE-AUTH-01_Spec.md`. That document is
**FUTURE DESIGN ONLY**. Nothing in it is implemented, and nothing in it may be
implemented as part of this work order.
