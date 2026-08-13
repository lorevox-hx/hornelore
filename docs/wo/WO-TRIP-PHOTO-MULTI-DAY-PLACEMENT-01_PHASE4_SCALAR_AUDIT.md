# WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 — Phase 4 scalar audit

**Baseline:** Phase 3 closed at `e89fa19`. **Produced:** 2026-08-13.
**Question:** after Phases 2 and 3, what still reads
`trip_photo_links.trip_day_id`, and is each survivor justified?

The Phase 2 audit answered *did we find every reader*. This one answers the
narrower and harder question: *of the readers that remain, does each one have a
reason that survives scrutiny*. A reference that is merely harmless is not
justified — the column is dropped in Phase 6, and anything still reading it
then becomes a defect.

---

## 0. The method, and why the raw count is misleading

```
grep -rn "trip_day_id" server/code ui/js scripts tests   ->  ~430 hits
```

That number is close to meaningless, because **`trip_day_id` is four different
columns on four different tables** (Phase 0 §0):

| Table | Places | In scope |
|---|---|---|
| `trip_photo_links` | a photograph on a day | **YES** |
| `trip_location_notes` | a note on a day | no |
| `trip_sources` | a source on a day | no |
| `trip_turn_links` | a conversation on a day | no |

Plus `trips.active_trip_day_id`, which is the operator's current selection and
not a placement at all, and `trip_photo_day_placements.trip_day_id`, which is
the **new** authoritative column and reads of it are the point.

Filtering to executable lines that concern the **photo** scalar leaves the
table in §2. Everything else is a different lane.

---

## 1. Writes: zero, and asserted

```
grep -rnE "UPDATE\s+trip_photo_links\s+SET[^\"']*trip_day_id" server/code  ->  0
```

`photo_link_upsert` does not name the column, so a new trip membership is born
with a NULL scalar and stays that way.

The absence is guarded by a test rather than by this document:
`TheBridgeIsRetiredTest::test_no_production_module_writes_the_legacy_photo_day_column`
walks every `.py` under `server/code` and fails the build on any such UPDATE.
Prose goes stale on the next commit; the test does not.

---

## 2. Every surviving read, and its justification

### 2.1 Pre-0043 legacy branches — five sites

| Site | Guard |
|---|---|
| `trip_photo_inventory` (`:2073`) | `elif _table_has_column(...)` |
| `trip_timeline_projection` (`:2976`) | `_unplaced_where` fallback |
| `_day_attachment_counts` → `_tally` (`:4720`) | `if not _placements_supported(con)` |
| `_day_photo_items` (`:5855`) | `if _placements_supported(con): … else:` |
| `trip_day_counts` (`:4720` region) | same probe |

**Justified.** Each is the `else` arm of a runtime probe and is unreachable on
any database that has run 0043. They exist so a database that never ran the
migration stays readable rather than silently reporting every day as empty —
and "every day is empty" is what licenses `drop_empty_out_of_range` to delete
day rows.

**Phase 6 disposition:** delete with the column. They have no other purpose.

### 2.2 `apply_placement_serialization`, the compatibility scalar — `:555`

```python
row["trip_day_id"] = (str(placements[0]["trip_day_id"])
                      if len(placements) == 1 else None)
```

**Justified, and it is a WRITE to the response rather than a read of the
column.** The value served is derived from placements every time, so the stored
column is unreachable through any serialized read. That is what lets Phase 6
drop it without a second consumer audit.

### 2.3 `_PHOTO_LINK_SAFE_COLS` still SELECTs `l.trip_day_id` — `:2132`

**Justified, narrowly, and flagged for Phase 6.** The column is selected and
then overwritten by the serializer, so the value never escapes. Removing it
from the projection would be tidier and is deliberately NOT done here: on a
pre-0043 database the serializer's legacy branch (§4) reads that very field to
build `trip_day_ids`, so removing the SELECT would break the compatibility path
this phase just repaired. It comes out with the column, in Phase 6, when both
go together.

### 2.4 `_is_placement_unique_violation` — `:4317`

```python
return ("unique" in msg and "photo_link_id" in msg
        and "trip_day_id" in msg)
```

**Justified.** This is matching the SQLite error text for
`UNIQUE(photo_link_id, trip_day_id)` on `trip_photo_day_placements` — the NEW
table. The string is a coincidence of naming, not a reference to the legacy
column.

### 2.5 `ui/js/travel-doc-lab.js::linkDayIds` — `:5646`

```javascript
if (Array.isArray(l.trip_day_ids)) return l.trip_day_ids;
return l.trip_day_id ? [l.trip_day_id] : [];
```

**Justified.** The single sanctioned client-side reader, for a response that
predates Phase 2 and carries no `trip_day_ids`. It cannot resurrect a stale
value: the server never serves that column raw, so when it is present it means
exactly one placement.

Pinned by
`OneDefinitionOfWhereAPhotographIsTest::test_only_linkDayIds_may_read_the_compatibility_scalar`,
which fails the build if any other line in the module reads it.

### 2.6 Response fields named `trip_day_id` — `trips.py:3687`, `:3748`

**Justified.** These are the day the *route acted on*, echoed back to the
caller. They are not the link's column and never were.

### 2.7 Out of scope entirely

`trip_story_capture.py` (notes), `trip_placement.py` (`trip_turn_links`),
`travel_doc_lori_modal.py` and `chat_ws.py` (`active_trip_day_id`),
`import_provenance.py` (comments only), and every `trip_day_id` in
`travel-doc-lab.js` outside `linkDayIds` (notes, sources, conversations).
Re-verified line by line at this commit; unchanged from Phase 0 §3.

---

## 3. What the audit FOUND — a defect, not a documentation gap

**`apply_placement_serialization` was blanking the scalar on a pre-0043
database.** It overwrote `trip_day_id` on every row unconditionally, and
`placements_by_link_for_trip` correctly returns `{}` when the table is absent —
so `photo_link_get` on such a database answered *"on no day"* about a
photograph that was on `d1`.

Every other reader in the module keeps an explicit legacy branch (§2.1). This
one had lost its, in Phase 2, and no test noticed because no test built a
pre-0043 database and then asked a serialized read about it.

**Fixed** by `placements_supported=False`, which leaves the scalar alone and
derives `trip_day_ids` *from* it, so a consumer written against the new field
still works against an old database. Three call sites pass
`_placements_supported(con)`.

Two tests pin it, and a mutation reverting the guard fails exactly the first:

- `test_the_serialized_read_does_not_blank_the_legacy_scalar`
- `test_a_link_with_no_legacy_day_is_still_empty` (non-vacuity: an absence is
  still reported as an absence)

**Severity, stated honestly:** low in practice, because Chris's database ran
0043 on 2026-08-12 and there is no other. It matters because the legacy
branches elsewhere are load-bearing for exactly this scenario, and a codebase
that keeps five careful fallbacks and one accidental hole is worse than one
with none — the hole is where nobody is looking.

---

## 4. Phase 6 checklist, assembled here so it need not be rediscovered

Dropping `trip_photo_links.trip_day_id` requires, in one migration and one
commit:

1. Delete the five legacy branches in §2.1 and their `_placements_supported`
   `else` arms.
2. Delete `placements_supported=False` from `apply_placement_serialization`
   (§3) — it exists only for databases the column still lives on.
3. Remove `l.trip_day_id` from `_PHOTO_LINK_SAFE_COLS` (§2.3).
4. Simplify `linkDayIds` to `l.trip_day_ids || []` (§2.5).
5. Keep `_is_placement_unique_violation` (§2.4) — different table.
6. `days_of()` in `scripts/wo02_acceptance.py` keeps its legacy arm as long as
   any pre-2026-08-13 state file might still be compared. That is an evidence
   question, not a schema one.
7. Re-run this audit. The grep must come back with the four *other* tables and
   nothing else.
