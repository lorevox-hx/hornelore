# WO-TRAVEL-DOC-PICKER-REINGEST-REPAIR-01

**Google Photos Picker: provider byte stability, re-ingest and repair
semantics.**

**Status:** SPEC ONLY. No code written.
**Opened:** 2026-07-29
**Parent:** WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 (Phase 2B, live smoke 9)
**Doctrine:** `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` ruling 1.14
**Blocks:** the three-source photo chooser and the destination schema work.
Chris: *"Do not start the three-source chooser or destination schema work
until both pass."*

---

## Why this exists

Live smoke 9 on 2026-07-28 re-ran ingest over an existing, healthy Google
Picker batch of seven candidates. The expected result was seven `unchanged`.
The actual result was seven `failed` / `hash_mismatch` / `retryable: false`.

Nothing was corrupt. The database and the staged files were verified
independently and agreed exactly: all seven `original.jpg` files on disk
sha256 to the `file_hash` on their row, all seven rows are still `pending`,
the batch counters did not move, and no duplicate row was created. The
deduplication half of smoke 9 did what it was built to do.

What failed was an assumption. Two ingest runs minutes apart were compared
item by item, and **five of the seven items returned different bytes on the
second fetch**. The deltas were +2, -3, +1, +1, +1, 0, +1 against the stored
size on one run and +3, -1, -1, 0, +2, +1, -3 on the other -- both directions,
never more than three bytes. That is metadata regenerated server-side per
request. It is not truncation, not a different rendition, and not damage.

Chris's ruling, verbatim:

> The mistake is treating a second download of the same Google media item as
> though its bytes must be identical forever. Google can evidently re-encode
> or alter metadata while still returning the same underlying media item.
> Therefore: same external_id + different newly downloaded hash -- must not
> automatically mean corruption.

and:

> The local database and staged files are healthy. The defect is the
> assumption that Google will reproduce identical bytes on later fetches.

---

## The ruling this work order implements

Recorded as doctrine ruling 1.14 and restated here because this is the work
order that has to satisfy it.

- `external_id` -- the Google media item id -- identifies the logical picked
  item. It remains the identity. **This does not justify changing candidate
  identity to hashes** (Chris, explicitly).
- `file_hash` verifies the integrity of *Hornelore's own staged copy*. It is
  the checksum of the copy Hornelore retained, not a permanent fingerprint
  supplied by Google.
- A later Google download is **not expected** to reproduce the same hash.
- `hash_mismatch` remains an error only for a local integrity problem or an
  unsafe write condition -- never because two separate Google fetches differ.

### The normal re-ingest path

    candidate exists
    + staged file exists
    + staged file hashes to the stored file_hash
    -> unchanged
    -> do not download it again

Chris asked the sharper question and it is the one that shapes the fix:

> Why are we downloading again at all? If the candidate already exists ...
> then there is no reason to ask Google for the bytes again. Just report:
> unchanged ... That avoids Google's byte jitter entirely.

So the local verification happens **before** the network call, not after it.
The saving is not incidental: it is what makes the jitter unobservable.

### The repair path

    candidate exists
    + local copy missing, corrupt, or an earlier attempt was incomplete
    -> download again as a repair
    -> stage atomically
    -> update file_hash, byte_size and related byte-derived metadata
    -> repaired

The same Google media id returning different bytes **during a repair is not
itself an error**. The new hash becomes the integrity record for the repaired
local copy. This is an explicit repair, not a non-retryable `hash_mismatch`.

---

## What must NOT change

- The refusal philosophy in `_settle_existing`. Chris: *"The detail messages
  are actually good ... 'a row and a file that disagree are worse than a
  refusal somebody can read.' is good defensive behavior. I would keep that
  philosophy. The system correctly refused to overwrite a good staged file.
  The mistake happened before that decision: it should never have downloaded
  the file again in the first place."*
- Candidate identity. `idx_import_candidate_batch_external` on
  `(batch_id, external_id)` stays.
- Ruling 1.6 -- an ingest failure is still not a candidate decision. Nothing
  here writes `error` onto a row.
- **No schema migration.** Not needed and not permitted by this work order.

---

## Scope

### In

1. `_settle_existing` in `server/code/api/routers/google_picker.py` (currently
   lines 584-686): verify the staged copy against the stored hash *first*, and
   return `unchanged` without a download when it verifies. Reorder, do not
   loosen.
2. The download-again branch, reachable only when the staged file is missing,
   fails its stored hash, or an earlier attempt left the item incomplete.
   Outcome `repaired`; stage atomically; update `file_hash`, `byte_size` and
   the byte-derived metadata on the row.
3. The `ingest_picker_session` docstring's idempotency claim, which smoke 9
   falsified. It reads *"the re-ingest branch above checks the bytes against
   the hash already on the row before it will replace anything"* -- true of
   the code, but it describes checking freshly downloaded bytes, which is the
   defect. Correct in place.
4. The response `next` string. It currently reads *"Review the new candidates
   in the evidence queue. Items that failed retryably can be picked up by
   running ingest again; nothing already landed is re-downloaded."* Chris:
   *"It is factually false today."* It becomes conditional, and Chris supplied
   the replacement shape: *"Complete, locally verified candidates are not
   downloaded again. Missing or damaged staged files may be downloaded again
   for repair."* The response **must also stop offering retry advice when all
   failures are permanent**.

### Out

- Promotion, `PROMOTABLE_SOURCES`, `photos` rows, `candidate_decide()`.
- Any schema or migration.
- The acquisition state machine of doctrine 4.2. Still future design.
- Takeout, Lori, the three-source chooser, destination schema.

---

## Test coverage required

Chris: *"This needs a regression test using the same external_id with slightly
different downloaded bytes on the second provider response."* and *"Add
real-provider regression coverage with a test double that returns different
bytes for the same external_id on successive calls."*

1. **Byte-jitter double.** A provider stub that returns different bytes for
   the same `external_id` on successive calls. Second ingest over a healthy
   batch must report `unchanged` and must **not** call the downloader at all.
   Assert the non-call, not only the outcome -- the outcome would be green for
   the wrong reason if the download happened and the result were discarded.
2. **Repair with jitter.** Delete the staged original, re-ingest, assert
   `repaired`, assert the row's `file_hash` and `byte_size` now match the new
   bytes on disk, and assert no `hash_mismatch`.
3. **Corrupt staged file.** Overwrite the staged original with different
   content, re-ingest, assert `repaired` and that the row is re-stamped.
4. **`hash_mismatch` still fires** where it should: a local integrity problem
   or an unsafe write condition inside one controlled write. This guard must
   be proven non-vacuous -- the whole point of the change is that the reason
   still exists and is narrower.
5. **Receipt wording.** Assert the conditional `next` string, and assert that
   an all-permanent-failure run does not offer retry advice.

Suites to re-run on the device: the Phase 1 / 2B-acquire / 2B-ingest set (193
at last count), plus whatever module the new tests land in.

---

## Acceptance

- Re-run live smoke 9 against the same existing batch
  (`8b5b47cb-4298-43fc-8ea6-827a5916e460`, seven candidates, expires
  2026-08-04) and get:

      created: 0   repaired: 0   unchanged: 7   failed: 0

- The candidate count does not increase, the batch stays `open`, no row is
  promoted, and the seven staged files are byte-identical before and after
  (they were never touched).
- No `google_picker:` log line and no HTTP response carries a `baseUrl`, a
  bearer value, an access or refresh token, a client secret, or a raw Picker
  session identifier.

---

## Operational note

The refresh token minted 2026-07-27 dies around 2026-08-03. A 503 with reason
`refresh_token_expired` is expected behaviour, not a defect; Chris re-mints it
in the OAuth Playground with the same client id and secret. **The app is not
published and must not be.** Chris does the Google Cloud console work and the
one-time authorization himself, and the agent never sees, enters, or handles
those values (spec §6, §7(a)).
