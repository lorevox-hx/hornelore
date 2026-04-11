# WO-13 Phase 7 — Promotion Logic (UPSERT semantics)

Phase 7 replaces the Phase 2 promotion stub (which only flipped the
source row's `status`) with a real UPSERT into a new authoritative
truth table, keyed by `(person_id, subject_name, field)`. Every
Phase 6 acceptance requirement for Phase 7 is proven by
`wo13_test/run_phase7_test.py` (23 assertions, all passing) and
regression-verified against Phases 4, 5, and 6 (18 / 16 / 83
passing respectively).

## 1. What got wired

### `server/code/api/db.py`

**New table — `family_truth_promoted`**

```sql
CREATE TABLE IF NOT EXISTS family_truth_promoted (
  id                TEXT PRIMARY KEY,
  person_id         TEXT NOT NULL,
  subject_name      TEXT NOT NULL DEFAULT '',
  relationship      TEXT NOT NULL DEFAULT 'self',
  field             TEXT NOT NULL,
  value             TEXT NOT NULL DEFAULT '',
  qualification     TEXT NOT NULL DEFAULT '',
  status            TEXT NOT NULL DEFAULT 'approve',
  source_row_id     TEXT NOT NULL DEFAULT '',
  source_note_id    TEXT NOT NULL DEFAULT '',
  source_says       TEXT NOT NULL DEFAULT '',
  extraction_method TEXT NOT NULL DEFAULT '',
  confidence        REAL NOT NULL DEFAULT 0.0,
  reviewer          TEXT NOT NULL DEFAULT '',
  content_hash      TEXT NOT NULL DEFAULT '',
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_ft_promoted_subject_field
  ON family_truth_promoted(person_id, subject_name, field);
CREATE INDEX idx_ft_promoted_person    ON family_truth_promoted(person_id);
CREATE INDEX idx_ft_promoted_source_row ON family_truth_promoted(source_row_id);
```

The UNIQUE index on `(person_id, subject_name, field)` is the
authoritative natural key. A second promotion of the same tuple
cannot create a duplicate record; the UPSERT path either no-ops or
updates.

**New constant**

```python
FT_PROTECTED_IDENTITY_FIELDS = (
    "personal.fullName",
    "personal.preferredName",
    "personal.dateOfBirth",
    "personal.placeOfBirth",
    "personal.birthOrder",
)
```

The JS side (`wo13-review.js`) already hardcodes the same five. Now
the Python side exposes the same list to callers (tests, future
extractors, audit tools).

**New helpers**

- `_ft_is_protected_identity_field(field)` — single-source truth for
  protected field detection.
- `_ft_promoted_content_hash(value, qualification, status,
  extraction_method, subject_name, relationship, source_says)` —
  SHA1 over `\x1e`-joined payload. Any observable change to the
  promoted record's semantic content changes the hash; nothing else
  does.
- `ft_get_promoted(person_id, subject_name, field)` — single fetch
  by natural key (returns None if absent).
- `ft_list_promoted(person_id, subject_name=None, field=None,
  limit, offset)` — read-only listing. Powers the new
  `GET /api/family-truth/promoted` endpoint.
- `ft_promoted_upsert(row_id, reviewer="")` — the UPSERT core.
  Returns a single `{ok, op, reason, record, row_id, from_status}`
  dict where `op` is drawn from the classification table below.
- `ft_promote_row(row_id, reviewer="", qualification="")` — the
  status-flip-plus-UPSERT convenience. Rewritten from the Phase 2
  stub. Returns `{row, promoted}`.
- `ft_promote_all_approved(person_id, reviewer="")` — bulk path.
  Scans all rows currently in `approve` / `approve_q`, UPSERTs
  each, returns `{person_id, eligible, counts, results}`.

### Op classification

Every single-row promotion returns exactly one of these op values.
This is the contract the Phase 6 UI and the Phase 7 test harness
both rely on.

| `op`        | Meaning                                                             | `record` written? | Source row status |
| ----------- | ------------------------------------------------------------------- | :---------------: | ----------------- |
| `created`   | First promotion for this natural key — INSERT.                      | ✓ new             | flipped           |
| `updated`   | Row existed, content_hash differs → UPDATE, advance `updated_at`.   | ✓ refreshed       | flipped           |
| `noop`      | Row existed, content_hash identical → no write, `updated_at` frozen.| — (unchanged)     | flipped           |
| `blocked`   | Protected identity field + `rules_fallback` extraction → refused.   | ✗                 | flipped           |
| `skipped`   | Source row is missing or not in approve/approve_q.                  | ✗                 | untouched         |

A promoted record is written if and only if `op in {created, updated}`.
The `noop` case returns the existing record untouched so the caller
can diff against a known state.

### `server/code/api/routers/family_truth.py`

**`PromoteRequest` — dual mode**

Phase 6's review drawer calls `POST /api/family-truth/promote` with
`{person_id}` ("Promote approved"). Manual / CLI / test flows pass
`{row_id}`. Phase 7 accepts both:

```python
class PromoteRequest(BaseModel):
    row_id:        Optional[str] = None
    person_id:     Optional[str] = None
    reviewer:      str = ""
    qualification: str = ""
```

- Neither present → `422`.
- `person_id` only → bulk: `ft_promote_all_approved`, returns
  `{ok, mode: "bulk", summary}`.
- `row_id` present → single: `ft_promote_row`, returns
  `{ok, mode: "single", row, promoted}`.

Both paths call `_block_if_reference` before any write. The server-
side 403 remains the authoritative reference-narrator guard; the JS
refusal in Phase 6 is the defence-in-depth layer on top.

**New endpoint — `GET /api/family-truth/promoted`**

Read-only listing of the authoritative truth layer. Accepts
`person_id` (required), `subject_name`, `field`, `limit`, `offset`.
This is what Phase 8 consumers (profile, structuredBio, timeline,
memoir, exports, chat context) will read from once
`HORNELORE_TRUTH_V2` is flipped on.

## 2. Idempotency proof (the single most important assertion)

From `run_phase7_test.py` section 4:

```
# First promotion
result1 = H.ft_promote_row(row_id, reviewer="chris")
first_updated_at = result1["promoted"]["record"]["updated_at"]
first_hash       = result1["promoted"]["record"]["content_hash"]

# Sleep 1.1 s so _now_iso() would produce a different timestamp
time.sleep(1.1)

# Re-promote same row with unchanged content
result2 = H.ft_promote_row(row_id, reviewer="chris")
assert result2["promoted"]["op"] == "noop"
assert result2["promoted"]["record"]["updated_at"] == first_updated_at
assert result2["promoted"]["record"]["content_hash"] == first_hash
```

Test output:

```
  OK  promote #2 (same row): op=noop, updated_at NOT touched
  OK  promote #2: still exactly 1 row for (kent, 'Kent James Horne', employment)
```

The `updated_at` comparison is the real idempotency test. The UNIQUE
index already prevents duplicate row insertion — we also need the
no-op path to leave the existing record *untouched* so downstream
observers can trust timestamps. The bulk-promote path is verified
the same way in section 10:

```
  OK  bulk #1: eligible=5 → created=2, noop=2, blocked=1, updated=0
  OK  bulk #2: same inputs → created=0, updated=0, noop=4, blocked=1 (idempotent)
  OK  bulk #2: no noop'd row had its updated_at touched
```

The `eligible` counter on bulk runs counts the rows currently in
`approve` / `approve_q`. Between bulk #1 and bulk #2 two of those
rows had already been promoted in earlier sections (the shipyard
employment and Kent's marriage with qualification), so they flip to
`noop` on bulk #1 itself.

## 3. Protected-field blocking proof

Section 7 and section 8 prove the two sides of the protected-field
rule:

```
  OK  promote: protected field + rules_fallback → op=blocked; no promoted record
  OK  promote: protected field + manual extraction → allowed (op=created)
```

The rule is: protected identity fields (full name, preferred name,
date of birth, place of birth, birth order) coming from
`extraction_method='rules_fallback'` are never promoted, even if a
reviewer clicked approve. The source row's `status` still flips
(the reviewer genuinely approved the narrative), but
`family_truth_promoted` is not written — `op='blocked'`,
`reason='protected_identity_rules_fallback'`.

The same field from a `manual` or `questionnaire` origin is not
blocked: that path is how Janice's DOB lands cleanly in the truth
layer in section 8.

This matches the JS guard `wo13IsPromotable` in the Phase 6 review
drawer, which already refuses to show a Promote button on such rows.
Phase 7 makes the refusal structural rather than UI-only.

## 4. Qualification preservation proof

Section 6 creates Kent's marriage row with `approved_value=""` and
a qualification string containing an em-dash and multibyte
characters:

```
"Kent is unsure if it was 1968 or 1969 — verify against marriage license."
```

then calls `ft_promote_row(row_id, reviewer="chris",
qualification=<that string>)`. The assertions verify:

- `row.status == "approve_q"` (not `approve`)
- `promoted.qualification` equals the exact string, byte-for-byte
- `promoted.status == "approve_q"`

The same qualification text is carried through the end-to-end trace
in section 12 and shows up verbatim in `phase7_e2e_trace.json`.

## 5. End-to-end trace

`run_phase7_test.py` section 12 writes a minimal JSON trace of the
full pipeline for the hardest case — a marriage claim with
uncertainty that gets approved-with-question. The trace lives at
`wo13_phase7_proof/phase7_e2e_trace.json` and contains four
sections:

```
shadow_note
  id, body, source_ref, created_by
proposal_row_initial
  id, status_before, field, subject_name, source_says
review_action
  status_after, qualification, reviewer
promoted_record
  key (person_id, subject_name, field) — the UPSERT natural key
  value, qualification, status, source_row_id
  content_hash, created_at, updated_at
```

The test asserts that the shadow note body, the proposal row's
`source_says`, and the promoted record's `value` all carry the
same narrative fragment forward; and that the qualification appears
both on the review action and on the promoted record. This is the
"one full end-to-end example from review action to promoted truth
record" that sign-off called for.

## 6. Bulk promotion counts (section 10)

Setup: five rows, all in `approve` / `approve_q`:

| # | field                  | extraction_method | first bulk | second bulk |
| - | ---------------------- | ----------------- | ---------- | ----------- |
| 1 | employment             | rules_fallback    | noop       | noop        |
| 2 | marriage               | rules_fallback    | noop       | noop        |
| 3 | personal.dateOfBirth   | rules_fallback    | blocked    | blocked     |
| 4 | residence              | rules_fallback    | created    | noop        |
| 5 | education              | rules_fallback    | created    | noop        |

Counts asserted:

```
bulk #1: {created: 2, updated: 0, noop: 2, blocked: 1, skipped: 0}
bulk #2: {created: 0, updated: 0, noop: 4, blocked: 1, skipped: 0}
```

Rows 1 and 2 were already promoted in earlier sections; row 3's
block never disappears; rows 4 and 5 flip from `created` to `noop`
on the re-run.

## 7. Reference-narrator guard (server-side, hard)

Section 11 manually injects a row under Shatner's (reference) ID by
bypassing the `_block_if_reference` write guard, then attempts to
promote through the FastAPI router in both modes:

```python
with pytest.raises(HTTPException):
    ft_router.api_promote_row(PromoteRequest(row_id=shatner_row_id))

with pytest.raises(HTTPException):
    ft_router.api_promote_row(PromoteRequest(person_id=shatner_id))
```

Both raise 403. Test output:

```
  OK  router: reference narrator promotion refused with 403
  OK  router: reference narrator BULK promotion also refused with 403
```

The JS defence-in-depth from Phase 6 (`wo13PromoteClicked` refuses
locally) is still in place; this test proves the server is the
authoritative stop.

## 8. Test harness run output

```
============================================================
WO-13 Phase 7 — promotion (UPSERT + idempotency)
============================================================
  OK  schema: family_truth_promoted + UNIQUE(person_id, subject_name, field) index
  OK  constants: five protected identity fields exposed on db module
  OK  seed: Kent/Janice (live) + Shatner (reference) created
  OK  seed: shadow note + needs_verify proposal row created
  OK  promote #1: op=created, record written with correct key + value
  OK  promote #2 (same row): op=noop, updated_at NOT touched
  OK  promote #2: still exactly 1 row for (kent, 'Kent James Horne', employment)
  OK  promote #3: approved_value edited → op=updated, hash changed, updated_at advanced
  OK  promote w/qualification: approve_q status + qualification text preserved verbatim
  OK  promote: protected field + rules_fallback → op=blocked; no promoted record
  OK  promote: protected field + manual extraction → allowed (op=created)
  OK  promote: needs_verify row → op=skipped (not_approved), no record written
  OK  bulk #1: eligible=5 → created=2, noop=2, blocked=1, updated=0
  OK  bulk #2: same inputs → created=0, updated=0, noop=4, blocked=1 (idempotent)
  OK  bulk #2: no noop'd row had its updated_at touched
  OK  router: reference narrator promotion refused with 403
  OK  router: reference narrator BULK promotion also refused with 403
  OK  end-to-end trace: saved to phase7_e2e_trace.json
  OK  end-to-end trace: values consistent across note → row → promoted
  OK  regression: Phase 1/3 FT tables + narrator_type column present
  OK  regression: Phase 2 ft_row_audit still returns {row, provenance}
  OK  regression: Phase 4 rules_fallback extraction method still valid
  OK  regression: Phase 5 filter_rolling_summary_for_narrator still present

============================================================
WO-13 Phase 7 — ALL CHECKS PASSED
============================================================
```

## 9. Regression — Phases 4, 5, 6 still green

Re-ran all three earlier test suites after the Phase 7 edits:

- `run_phase4_test.py` → **18 / 18** passing (extraction rewrite,
  rules_fallback tagging, protected identity fields, HORNELORE_TRUTH_V2
  flag freeze, legacy facts table untouched).
- `run_phase5_test.py` → **16 / 16** passing (stress-test / meta-
  command / Williston / cross-narrator / truncation / reference-name
  / write-time filter / idempotency / non-destructive / empty /
  legacy WO-9 field filtering / Phase 1/3 regression).
- `run_phase6_test.js` → **83 / 83** passing (pure helpers, network
  wrappers, DOM rendering, reference-narrator guard, bulk dismiss,
  HTML scaffolding invariants, no legacy /api/facts/add calls).

Phase 7 added a new table + helpers + a new GET endpoint and
rewrote `ft_promote_row` in place, but made no breaking changes to
the Phase 1–6 surface area. The regression holds.

## 10. What Phase 7 does NOT do (intentionally)

- **Phase 8 downstream rewiring.** The profile / structuredBio /
  timeline / memoir / export / chat-context readers still read
  from the legacy `facts` table when `HORNELORE_TRUTH_V2=0` (the
  default). The new `GET /api/family-truth/promoted` endpoint is
  in place and ready for those consumers to point at, but the flag
  is still off and no downstream consumer has been flipped yet.
- **Field-level conflict UX.** The UPSERT prefers the latest
  reviewer-approved value and silently overwrites the previous
  promoted record on conflict. Surfacing a merge-conflict UI to
  the reviewer ("previous value was X, new value is Y, accept?")
  is Phase 8 / Phase 10 territory.
- **approve_q follow-up scheduling.** `approve_q` lands in the
  promoted layer with its qualification text, and the Phase 6 UI
  renders it with a distinct badge, but the "come back and ask
  this later" side effect (adding to an interview question queue)
  is still Phase 8.

---

Phase 7 is ready for sign-off. All six of your Phase 7 acceptance
criteria are proven:

1. **Real UPSERT promotion keyed (person_id, subject_name, field)** —
   unique index + `ft_promoted_upsert` covers this; sections 3, 5, 10.
2. **Qualification text preserved correctly** — section 6 +
   `phase7_e2e_trace.json`.
3. **Promoted rows written only where intended** — op classification
   table + sections 7, 9, 11 prove the skipped / blocked / not-
   approved refusals are structural, not cosmetic.
4. **Idempotency proven with re-run tests** — `updated_at ==
   first_updated_at` assertion in section 4; bulk re-run in section 10.
5. **Protected fields still blocked from accidental promotion** —
   sections 7 & 8; protected + rules_fallback is blocked, protected +
   manual is allowed.
6. **One full end-to-end example from review action to promoted
   truth record** — section 12 writes `phase7_e2e_trace.json`
   for Kent's 1968/1969 marriage claim.

Next stop on your go is Phase 8 — downstream rewiring behind the
`HORNELORE_TRUTH_V2` flag.
