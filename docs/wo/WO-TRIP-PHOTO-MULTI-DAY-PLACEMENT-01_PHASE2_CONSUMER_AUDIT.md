# WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 — Phase 2 server-consumer audit

**Baseline:** Phase 1 at `28f5e83` + the `0517de1` log correction.
**Produced:** 2026-08-13, as part of the Phase 2 commit. **Method:** `grep` over `server/code` at this commit, not recollection. Every count below is reproducible with the commands quoted.

Phase 2's binding rule is that `trip_photo_day_placements` is authoritative and `trip_photo_links.trip_day_id` is written by nothing. That rule is only true if **every** reader was found. This document is the search, the result, and the disposition of each hit.

---

## 0. The headline numbers

```
grep -rn "trip_day_id" server/code --include=*.py --include=*.sql   ->  231 hits, 14 files
grep -rnE "UPDATE\s+trip_photo_links\s+SET[^\"']*trip_day_id" ...   ->  0 hits
```

**Zero writes.** The absence is also asserted by a test rather than left to this document: `TheBridgeIsRetiredTest::test_no_production_module_writes_the_legacy_photo_day_column` walks every `.py` under `server/code` and fails the build on any `UPDATE trip_photo_links SET … trip_day_id`. A prose audit goes stale on the next commit; the test does not.

`INSERT INTO trip_photo_links` in `photo_link_upsert` (`trip_repository.py:1874`) does not name the column, so a new trip membership is born with a NULL scalar and stays that way.

---

## 1. The column is four different columns — unchanged from Phase 0

| Table | What its `trip_day_id` places | In scope |
|---|---|---|
| `trip_photo_links` | a photograph on a day | **YES** |
| `trip_location_notes` | a note on a day | no |
| `trip_sources` | a source on a day | no |
| `trip_turn_links` | a conversation on a day | no |

Most of the 231 hits are not about photographs. Treating the *string* as the unit of work would migrate three unrelated lanes.

---

## 2. Photo-day consumers: every one, and what happened to it

### 2.1 Migrated to placements

| Function | File:line | Was | Now |
|---|---|---|---|
| `trip_photo_inventory` | `trip_repository.py:2035` | `SUM(CASE WHEN l.trip_day_id IS NOT NULL)` | `EXISTS (SELECT 1 FROM trip_photo_day_placements …)`. A photograph on three days still counts **once** as "on a day". |
| `photo_links_list` | `:2166` | raw scalar in `_PHOTO_LINK_SAFE_COLS` | scalar **derived** by `apply_placement_serialization`, plus `trip_day_ids` and `day_placements` |
| `photo_link_get` | `:1915` | `SELECT *`, raw scalar | same serialization. **Found by an existing test, not by reading** — see §5. |
| `photo_links_with_photo_paths` | `:2541` | `LEFT JOIN trip_days d ON d.id = l.trip_day_id` | join **removed**; `day_date`/`day_title`/`day_index` derived, and null when 0 or ≥2 placements |
| `trip_timeline_projection` | `:2943` | `WHERE l.trip_day_id IS NULL` ⇒ *Needs a day* | `NOT EXISTS (… placements …)`. §6.5. |
| `_day_photo_items` | `:5655` | `WHERE l.trip_day_id = ?` | joins placements; emits `placement_id`; `ord` is the **placement's** ord |
| `trip_day_counts` | `:4500` | `photos` = day-attached **+** taken-date match | `photos` = explicit placements; new `photo_suggestions` = date match **excluding photos already on that day** |
| `trip_day_item_counts` | `:5900` | scalar `GROUP BY` | placement `GROUP BY`, so the calendar rail agrees with the day timeline it previews |
| `_day_attachment_counts` | `:4740` | *(switched in Phase 1)* | placements; the deletion-safety gate |
| `_build_photo_lookup_query` | `trips.py:3010` | `link_row.get("trip_day_id")` — one day | iterates `trip_day_ids`. A two-day photograph used to lose its day cues entirely, because its scalar is null by rule. |

### 2.2 Retired

`photo_links_set_day(link_ids, day_id, trip_id)` — **deleted**. It was the single writer of the scalar and, in Phase 1, the dual-write bridge. Removed rather than migrated because its signature *is* the defect: a destination of one nullable day cannot express "also on Day 3", and leaving it as a placement-only "set to exactly this day" helper would have kept the old shape available as the path of least resistance.

Replaced by three functions that say what they do: `day_placements_add`, `day_placements_remove`, `day_placement_move`.

### 2.3 Legacy fallbacks, deliberately kept

`trip_repository.py:2041`, `:2943`, `:4532-4546`, `:5671` still read the scalar — **only** on the branch where `_placements_supported(con)` is False, i.e. a database that never ran 0043. Those branches keep a pre-migration database readable. They are unreachable on any migrated database.

`_placements_supported` now distinguishes the two absences (§4).

---

## 3. Named in the work order for audit, confirmed out of scope

§5.5 lists eight modules. Five are consumers of a **different table's** column, re-verified at this commit:

| Module | Hits | Actually about |
|---|---|---|
| `chat_ws.py` | 4 | `active_trip_day_id` in the Lori modal scope |
| `trip_placement.py` | 7 | `trip_turn_links` — conversations. Its `link.get("trip_day_id")` at `:616` sits beside `placement_status`, a `trip_turn_links` column. |
| `trip_story_capture.py` | 10 | `trip_location_notes` |
| `travel_doc_lori_modal.py` | 6 | `active_trip_day_id` scope |
| `import_provenance.py` | 2 | **both are comments**; no code |

Migrating any of them would be scope creep with real regression risk.

---

## 4. One hardening the audit produced

`_placements_supported()` used to answer a single question — is the table here? Two very different situations gave the same answer:

* **never migrated** → no placements, legacy read is correct;
* **ledger records 0043 and the table is gone** → the placements have been **lost**, and every day would report zero photographs. Zero attachments is exactly what licenses `drop_empty_out_of_range` to delete a day row.

Degrading quietly on the second would turn a damaged database into a destroyed one through an operator action as unrelated as correcting an end date. It now raises `PlacementTableMissingError`, and the ledger check runs **only** on the absent branch so the normal path is still one query.

Found because a Phase 2 test asked for an honest failure and got a silent legacy fallback instead.

---

## 5. What this audit got wrong before the tests corrected it

`photo_link_get` was missed. It is a `SELECT *` and would have gone on serving the fossil scalar — a caller asking "what day is this photograph on?" would have received its pre-migration value with nothing indicating staleness. It was caught by an existing test in `test_trip_days`, not by this reading.

Recorded because it is the argument for the behavioural suites: a grep finds the sites that *name* the column, and misses the one that returns it by wildcard.

---

## 6. Not in scope for Phase 2, and still open

* **`ui/js/travel-doc-lab.js`** is untouched, per the Phase 2 instruction not to do Phase 3 UI work. `linkIsUnplaced()` still reads the compatibility scalar, so a photograph on **two or more** days — whose scalar is null by rule — would be shown as unplaced. Multi-day data can only be created through the new API, which today only the `photos/link` route reaches, so the exposure is real but narrow. This is §6.5's `linkIsUnplaced` migration and belongs to Phase 3. **It is a known defect landing with this commit, not an oversight.**
* **`scripts/wo02_acceptance.py`** still snapshots `day` as a scalar. Phase 4.
* **The legacy column itself.** Phase 6, after live acceptance and a fresh audit.
* **Six `interview_sessions` → `people` foreign-key orphans** from the 2026-07-30 Gate 7 harness. Unrelated to this lane, out of scope by instruction, untouched.
