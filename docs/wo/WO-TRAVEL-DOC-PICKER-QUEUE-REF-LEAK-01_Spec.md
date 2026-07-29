# WO-TRAVEL-DOC-PICKER-QUEUE-REF-LEAK-01

**Remove the raw Google Picker session identifier from the browser-visible
evidence queue payload.**

**Status:** SPEC ONLY. No code written.
**Opened:** 2026-07-29
**Parent:** WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 (live smoke 10)
**Doctrine:** ruling 1.10 -- credential hygiene is structural, not a review
item.
**Severity:** confirmed security-requirement failure. Chris: *"The browser
side of smoke 10 has failed already, so the security fix is required
regardless of what the logs show."*

---

## The finding

Live smoke 10 on 2026-07-28 scanned the browser side of the picker lane
against thirteen patterns: `baseUrl`, `base_url`, `ya29.`, a bearer-token
shape, `access_token`, `refresh_token`, `client_secret`, `GOCSPX`,
`authorization`, `session_id`, the raw session value itself, Google origins,
and `external_ref`.

Almost everything came back clean, and the clean results are worth stating
because they show the existing guards working:

- 81 network requests, every one to `localhost:8000`. No Google origin. No
  credential in any URL, path or query string.
- The ingest response body: clean on all thirteen patterns.
- `/api/google-picker/health`: presence booleans only, exactly as spec §10.4
  requires. The scope string is a plain scope URL, no query, no token, 64
  characters.
- The console: six messages, zero errors, nothing credential-shaped.
- `match_reason`: clean. The key `session_id` never appears anywhere. The
  deliberate `picker_session` naming works.

**One pattern failed.** `GET /api/import-provenance/queue` returns
`candidates[].batch.external_ref`, and that value was proven by direct
equality to be the **raw Google Picker session identifier**. It is served to
the browser on every queue read.

The source is a single tuple, `server/code/api/services/import_repository.py`
line 1018:

    _QUEUE_BATCH_COLUMNS = (
        "id", "label", "source", "status", "external_ref", "hidden",
        "candidate_count", "accepted_count", "rejected_count",
    )

The guards that were built all held. The value escaped through a door nobody
had looked at: a generic column list on a route that predates the picker lane.

---

## The fix

Chris's ruling, verbatim:

> My preferred fix is simple: Remove external_ref from _QUEUE_BATCH_COLUMNS --
> unless the browser has a demonstrated functional need for it. Do not merely
> rename the key or partially mask the value. The raw provider reference
> should remain server-side.

and:

> No renaming or masking -- the provider reference stays server-side.

So:

1. Remove `"external_ref"` from `_QUEUE_BATCH_COLUMNS`.
2. First confirm no browser code reads it. If the UI needs a batch identifier
   it already has Hornelore's internal `batch_id`; if it needs display
   information, `source`, `status`, `created_at` and `candidate_count` are
   safe and Chris named them. Add `created_at` only if something actually
   wants it -- this is a removal work order, not a shape redesign.
3. Confirm no non-browser consumer requires it. Chris: *"unless a specific
   non-browser consumer demonstrably requires it."* If one is found, it is
   reported to Chris rather than worked around.

**No schema migration.** The column stays on `import_batch`; it is correct
that the server holds it. Chris: *"No schema migration is needed for this
correction."*

---

## Test coverage required

A **response-contract test** on the queue JSON, proving it does not contain:

- the key `external_ref`, at any nesting depth;
- the raw Picker session value;
- any key containing `session_id`;
- OAuth tokens or bearer values;
- Google download URLs (`baseUrl`, `base_url`, `googleusercontent`,
  `googleapis.com`);
- client secrets (`client_secret`, `GOCSPX`).

Serialise the whole response and scan the serialised form, not a hand-picked
field list -- the defect this test exists to catch is precisely a value
arriving through a field nobody enumerated. The test must be proven
non-vacuous: it has to fail against the current tuple.

The existing `_SECRET_KEY_HINTS` vocabulary (`token`, `auth`, `secret`,
`session_id`) is the right source for the key-name half.

---

## Acceptance

- Re-run live smoke 10. The raw session identifier is absent from the queue
  response, and absent from the `google_picker:` server log lines.
- The evidence queue screen still renders and still functions -- the removal
  is not allowed to be verified only by a test.
- The other twelve patterns stay clean; this fix must not move anything into
  a different response to keep a scan green.

---

## Note on what this does not mean

The picker lane's credential-hygiene design is not being reopened. Ruling 1.10
holds and the smoke proved most of it in production for the first time. What
this work order records is that a structural guard applied to *the lane* did
not cover *a shared route the lane feeds*, and the contract test is the guard
that closes that gap for every future producer, not only for the picker.
