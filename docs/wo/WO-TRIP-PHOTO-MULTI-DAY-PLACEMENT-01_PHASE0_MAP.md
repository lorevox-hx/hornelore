# WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 — Phase 0 implementation map

**Baseline:** `e691105` (the approved work order, itself on top of `e6388ae` / `5d1a4fa` / `10c44f8`).
**Produced:** 2026-08-12. **Status:** inventory only — no production code, schema, API, UI or test was modified in this phase.
**Linked from:** the work order's §10 Phase 0, which directs that this map be a tracked document.

Every count below is from the tree at `e691105`. Where the work order's own text and the code disagree, the code is recorded and the disagreement is called out.

---

## 0. The single most important finding

**`trip_day_id` is four different columns on four different tables, and this work order changes exactly one of them.**

| Table | Column added by | What it places | In scope? |
|---|---|---|---|
| `trip_photo_links` | 0028 | a photograph on a day | **YES — this WO** |
| `trip_location_notes` | 0028 | a note on a day | no |
| `trip_sources` | 0029 | a source on a day | no |
| `trip_turn_links` | 0039 | a conversation on a day | no |

**Corrected 2026-08-12 after review.** An earlier revision of this table listed a fifth row, `import_candidate` (0037), as a `trip_day_id` column. That is wrong. `0037_import_provenance_foundation.sql` gives `import_candidate` a **`trip_id`** only — `trip_id TEXT REFERENCES trips(id) ON DELETE SET NULL` — and no day column at all. The absence is deliberate and documented in the import lane: placement granularity is trip-level at intake because no importer exists to propose a finer answer, and `proposed_trip_day_id` was explicitly not added.

`import_candidate` remains an **audited related surface** — the promote-to-day path reaches day placement through `link_day_photos`, not through a column of its own — but it is not a fifth instance of this column and must not be migrated as one.

156 occurrences of the string `trip_day_id` exist in `server/code`. Most are not about photographs. Treating the string as the unit of work would migrate three unrelated lanes; treating the *photo* column as the unit is correct.

**This corrects the work order's §5.5 audit list.** That list names `chat_ws`, `trip_placement`, `trip_story_capture`, `travel_doc_lori_modal`, `import_provenance`, the trips router, `trip_repository` and both frontends. Verified at `e691105`:

- `trip_placement.py` (7 hits) operates on **`trip_turn_links`** — conversations. Its `link.get("trip_day_id")` at L616 is a turn link. **Not a photo consumer.**
- `trip_story_capture.py` (10 hits) scopes **notes**. **Not a photo consumer.**
- `travel_doc_lori_modal.py` (6 hits) reads `active_trip_day_id` for Lori scope. **Not a photo consumer.**
- `chat_ws.py` (4 hits) passes `active_trip_day_id` through the modal scope. **Not a photo consumer.**
- `import_provenance.py` (2 hits) — **both are comments**, no code.

Migrating those five would be scope creep with real regression risk. They stay untouched. The list is not wrong to name them for *audit*; it is wrong to read it as a migration list.

---

## 1. Photo-day readers and writers (the actual scope)

### 1.1 The one writer

`trip_repository.photo_links_set_day(link_ids, day_id, trip_id)` — `trip_repository.py:3742-3781`.
Sole mutator of `trip_photo_links.trip_day_id`. `day_id=None` is detach. Returns rows updated.

**Transaction boundary, corrected 2026-08-12 after review.** An earlier revision of this map called the function "already transactional and cross-trip validated." That overstates it, and the difference matters for Phase 1:

- **Day validation is OUTSIDE the write transaction.** `trip_day_get(day_id)` runs at **L3750**, on its own connection, *before* `con = _connect()` at **L3753**.
- **Link validation and the writes are inside** the transaction — `SELECT trip_id FROM trip_photo_links` at L3757, `UPDATE` at L3765, with `commit()` / `rollback()` / `close()`.

So the destination day is checked against a snapshot taken before the write connection exists. A day deleted or re-parented between those two statements would not be caught.

**Phase 1 requirement:** validate the destination day **and** every link inside the *same* write transaction that performs the scalar and placement mutations. Do not rely on the pre-connection `trip_day_get`. This is a strengthening of an existing weakness, not a regression introduced by this WO — but the bridge writes two representations, so a stale day check now risks a placement row pointing at a day that no longer exists, which is worse than a stale scalar.

**This is the function the Phase 1 dual-write bridge attaches to.** There is exactly one, which is why the bridge is a small, containable change.

### 1.2 Readers, with enclosing function

| Function | Line | Reads | Phase |
|---|---|---|---|
| `trip_photo_inventory` | 1561 | `SUM(CASE WHEN l.trip_day_id IS NOT NULL)` — "placed" count | 2 |
| `photo_links_with_photo_paths` | 2036 | `LEFT JOIN trip_days d ON d.id = l.trip_day_id` | 2 |
| `trip_timeline_projection` | 2440 | `WHERE l.trip_day_id IS NULL` → **Needs a day** | 2 (§6.5) |
| `photo_links_set_day` | 3765 | the `UPDATE` | 1 (bridge) |
| `trip_day_counts` | 3834 | `GROUP BY l.trip_day_id` + date-match fallback | 2 (§7) |
| `_day_photo_items` | 4877 | `WHERE l.trip_id=? AND l.trip_day_id=?` — day timeline | 2 |
| `_day_attachment_counts` | 4029 | `trip_photo_links … trip_day_id IS NOT NULL` | **1 — blocking** |

`_day_note_items` (4941) and `_day_source_items` (4974) read the *notes* and *sources* columns. Out of scope.

### 1.3 The deletion hazard path, concretely

`_day_attachment_counts` (4012-4032) → `_day_is_empty` (4044-4050) → `trip_days_reconcile_preview` / `drop_empty_out_of_range` (4177-4249).

`_day_is_empty` returns True when `day_own_content(day)` is false and the day has no photos, notes or sources attached. `drop_empty_out_of_range` **deletes** such day rows when a trip's dates shrink. If placements move to the new table and this tally is not switched in the same phase, a day holding only new-style placements reports zero and is deleted by an unrelated operator action.

Its existing docstring already states the governing principle — *"a lock or an I/O failure reported as 'zero attachments' would license a delete on a day nobody could read"* — and a half-finished migration is that failure in a new form.

---

## 2. Router endpoints and payloads

`server/code/api/routers/trips.py`, 32 `trip_day_id` hits.

| Endpoint | Line | Handler | Body |
|---|---|---|---|
| `POST /{trip_id}/days/{day_id}/photos/link` | 3566 | `link_day_photos` | `TripDayPhotoLinksReq` |
| `POST /{trip_id}/days/{day_id}/photos/unlink` | 3650 | `unlink_day_photos` | same model, `photo_ids` rejected |

`TripDayPhotoLinksReq` (3536-3542): `photo_link_ids: List[str] = []`, `photo_ids: List[str] = []`.
`photo_ids` (added 2026-07-29) promotes narrator photos into trip membership first; accepted on attach only. Both handlers call `photo_links_set_day(...)` — attach with `day_id`, detach with `None`. Attach returns `{photo_link_ids, created_link_ids, updated}`.

Note for §6.1: today **detach is the same call with `None`**, so "unlink" currently cannot target one placement among several — it has nothing to name. That is the API-shape reason the WO requires placement ids in read models.

---

## 3. Frontends

### 3.1 `ui/js/travel-doc-lab.js` — the only photo-placement frontend (72 hits, ~30 photo-relevant)

| Site | Line | Role |
|---|---|---|
| `dayHolds` | 1527 | emptiness/shrink-warning display |
| `dayLinkedPhotoLinks` | 4038 | photos **on** a day |
| `dateMatchedPhotoLinks` | 4043 | `!l.trip_day_id && takenDate === day.date` — the suggestion lane already exists |
| `unlinkDayPhoto` | 4151 | POST `/photos/unlink` |
| `paintAttach` | 4990-5061 | the picker; **L5044 chooses the label "Move to this day" vs "Attach"** purely from `l.trip_day_id` |
| `selCounts` | 4968 | counts move-vs-attach for the button label |
| `linkIsUnplaced` | 5271-5282 | `!trip_stop_id && !trip_day_id` (centralized `5d1a4fa`) |
| `filteredLinks` / chip count | 5310 / 5822 | both call `linkIsUnplaced` |
| `renderLightbox` | 5758, 5863 | day label fallback |
| `promoteAndAccept` | 6577 | picker promote → place on day |
| `moveTripPhotoLink` | 9673 | POST link/unlink |
| `renderEvalChecklist` | 3876 | dev-harness only |

L5044 is where the product ruling becomes visible: **"Move to this day" is generated, not authored** — it exists because the data model allowed one day. Phase 3 replaces it with Add + a separate Move.

### 3.2 `ui/js/travel-documenter.js` — **zero** `trip_day_id` hits, **zero** `photos/link` or `photos/unlink` calls

The retired frontend never implemented photo-day placement. **§8.2's concern does not apply**: there is no legacy page writing the scalar authority, so no port and no read-only lockdown is required for this feature. Phase 3 should record that as verified rather than doing work to satisfy a hazard that does not exist.

---

## 4. Consumers by lane

| Lane | Consumes | Phase |
|---|---|---|
| **Timeline** | `trip_timeline_projection` (2440) — scalar-null ⇒ "Needs a day" | 2 |
| **Memoir/DOCX** | `trip_memoir_docx.py` has **0** `trip_day_id` hits — it renders `trip_timeline_projection`'s output. Fixing the projection fixes the document. | 2 |
| **Counts** | `trip_day_counts` (3834) hybrid; `trip_photo_inventory` (1561) | 2 |
| **Deletion safety** | `_day_attachment_counts` (4029) | **1** |
| **Import/promote** | `promoteAndAccept` (UI) + `link_day_photos` | 2 |
| **Lori / story / placement** | conversations and notes only — **out of scope** | — |

The DOCX finding matters: §6.5's export ruling needs **no change to `trip_memoir_docx.py`**. One projection change carries it, and the DOCX tests assert the result.

---

## 5. WO-02 harness fields and assertions to convert

`scripts/wo02_acceptance.py`, four modes preserved (`capture`, `checkpoint`, `verify`, `restore-verify`).

**Scalar field:** `snapshot()` L190-192 — `snap["photo_links"][id] = {"day": link.get("trip_day_id"), "ch": …, "approved": …}` → becomes `days: [...]` (sorted, stable) plus placement ids.

**Assertions keyed to the scalar:**

| Site | Assertion | Becomes |
|---|---|---|
| 283-285 (`do_checkpoint`) | removed = `day is None` and was not None | placement-set shrank |
| 286, 292-294 | link vanished / count unchanged | unchanged (link-level) |
| 359-368 (`do_restore_verify`) | `cur["day"] == was["day"]` — "back on its original day" | back to its original **day set** |
| 323 | `stage_a.removed_photo_links` | placement ids, not link ids |

Under many-to-many the 359-368 assertion is **wrong, not merely incomplete**: a photo restored to Day 1 while still on Day 3 would fail a check that should pass. The strongest new assertion is *removing one placement leaves the others and the link intact*.

**Protected regressions (do not disturb while converting):** attestation recorded inside `do_verify()` before `_verdict()`; `main()` dispatch coverage; ATTEST line precedes the summary; nonzero summary count; ATTEST never raises PASS (all from `e6388ae`).

---

## 6. Tests and fixtures

16 test modules reference `trip_day_id`; **12 touch photo-day placement**:

| Module | photo-day refs | Why it matters |
|---|---|---|
| `test_travel_doc_evidence_preflight.py` | 56 | largest surface |
| `test_travel_doc_evidence_tools.py` | 27 | |
| `test_trip_story_capture.py` | 17 | mostly notes; verify per-test |
| `test_evidence_lifecycle.py` | 16 | |
| `test_trip_days.py` | 14 | |
| `test_picker_promote_to_day.py` | 11 | promote → day |
| `test_travel_doc_lab.py` | 8 | UI source gates incl. `linkIsUnplaced` |
| `test_trip_days_sqlite_error_classification.py` | 5 | **fail-closed posture — §9.5** |
| `test_travel_document_day_lane.py` / `test_travel_document_export.py` | 3 / 3 | export ordering |
| `test_trip_placement.py` / `test_wo_narrator_bridge_acceptance.py` | 1 / 1 | turn links; likely incidental |

Also required by §12 and not in the list above: `test_trip_days_reconcile.py` (the deletion path), `test_chronology_trip_lane_failures.py`, `test_photo_upload_hash_clash.py`, `test_travel_documenter_panel.py`, `test_wo02_acceptance_harness.py`.

**Fixtures:** no JSON/py fixture carries `trip_photo_links.trip_day_id`. The only match is the checked-in `data/db/lorevox.sqlite3`. Backfill correctness is therefore proved by migration tests against constructed databases, not by editing fixtures.

---

## 7. Migration runner and number

- Runner: `server/code/db/migrations_runner.py:58` `run_pending_migrations(con, base_dir)`.
- Behaviour: reads applied filenames from `schema_migrations`, iterates files in sorted order, `con.executescript(sql)` per file, records the filename, returns the list applied. Re-running is a no-op for already-recorded files, so **discovery is idempotent by filename** — a migration must be safe to leave in place, and must not depend on being the last one applied.
- Invoked from `db.py:1305-1353` with a defensive import fallback.
- **41 migration files. Highest: `0042_trip_days_include_in_memoir.sql`. `0043` does not exist. Confirmed next.**
- `trip_photo_day_placements` and `day_placements` appear **0 times** anywhere in `server/`, `ui/`, `tests/`, `scripts/` — no name collision.

---

## 8. Exact Phase 1 transition order

Ordered so that the deletion hazard is never open, not even between two statements.

1. **Migration `0043`** — create `trip_photo_day_placements` + both indexes. Additive only; legacy column untouched.
2. **Backfill inside the same migration** — one placement per live `trip_photo_links.trip_day_id`, `placement_method` recording that it came from backfill, `ord` 0. Assert exact counts and uniqueness.
3. **Repository primitives** — list / add-many / remove-from-day / move / reorder / attachment tally. Cross-trip validated transactionally (SQLite cannot express the rule with two FKs).
4. **Dual-write bridge in `photo_links_set_day`** — the scalar `UPDATE` and the placement mutation in **one transaction** (the function already has `con.commit()` / `con.rollback()`; extend it, and pull day validation inside per §1.1).

   **The bridge MIRRORS the scalar exactly. It does not add multi-day behaviour.** Phase 1 changes storage, not product semantics: while the UI still says "Move to this day", the placement set must say what the scalar says, transition for transition:

   | Scalar transition | Placement set must become | Atomic? |
   |---|---|---|
   | `null` → Day B | `{Day B}` — insert | yes |
   | Day A → Day B | `{Day B}` — **delete A and insert B** | yes, one transaction |
   | Day A → `null` | `{}` — delete A | yes |
   | Day A → Day A (no-op) | `{Day A}` — unchanged, no duplicate | yes |

   **The failure to avoid:** inserting Day B while leaving Day A behind. That would silently produce a two-day placement from an operator action the UI describes as a *move*, creating multi-day data before the product offers multi-day controls — and the operator would have no way to see or undo the second placement. Phase 2 is what turns "move" into "add"; Phase 1 must not anticipate it.

   A `photo_links_set_day` call carries a *list* of link ids, so each link's own prior placement is the one deleted — the delete is scoped to `(photo_link_id, previous day)`, never "all placements for this day".

   §9.11's test therefore needs both halves: after a legacy-path move, the destination day is protected from date-shrink deletion **and** the source day no longer counts that photo.
5. **Switch `_day_attachment_counts`** to the placement table, keeping the `_table_has_column` legacy-DB guard so a pre-0043 database still behaves.
6. **§9 tests**, including §9.11: a placement made *through the legacy path* creates a placement row and its day then refuses date-shrink deletion; injected failure rolls back both writes.

**Order 4-before-5 is the requirement.** If 5 lands first, every legacy-path write between the two is invisible to the tally — the hazard, reopened inside one commit. If 4 lands first, the tally is merely redundant for a moment, which is safe.

Nothing in Phase 1 touches routers or UI: `link_day_photos` / `unlink_day_photos` keep calling `photo_links_set_day`, which now maintains both representations.

---

## 9. Corrections this inventory makes to the work order

None of these change the design; they narrow the work and remove two false requirements.

1. **§5.5's audit list is not a migration list.** Five of the eight named modules are conversation/note/comment consumers of a different table's column. Verified individually above.
2. **§8.2 requires no work.** `travel-documenter.js` has zero photo-day code. Phase 3 records the verification instead of porting or locking down.
3. **§6.5 requires no `trip_memoir_docx.py` change.** It has zero `trip_day_id` hits and renders the projection; the projection change carries the export ruling, and the DOCX tests assert it.
4. **The scalar writer is a single function.** `photo_links_set_day` is the only mutator, which is what makes the bridge small.
5. **The suggestion lane already exists client-side** (`dateMatchedPhotoLinks`, L4043) and already excludes placed photos via `!l.trip_day_id`. §7's server-side `photo_suggestion_count` should match that existing definition rather than invent a second one.

---

## 10. Phase 0 gate evidence

- Every `trip_photo_links.trip_day_id` reader and writer enumerated with file and line (§1).
- Endpoints and payload models recorded (§2).
- Both frontends inspected; one has no photo-day code at all (§3).
- Timeline, memoir/DOCX, counts, import, Lori, placement and story lanes classified in/out of scope (§4).
- Harness fields and the four scalar assertions identified, with the one that becomes *wrong* rather than incomplete called out (§5).
- 12 photo-touching test modules and the fixture position recorded (§6).
- Runner behaviour described and `0043` confirmed next, with no name collision (§7).
- Transition order fixed, with the reason the bridge must precede the tally switch (§8).

**No product mutation.** This phase added one document.
