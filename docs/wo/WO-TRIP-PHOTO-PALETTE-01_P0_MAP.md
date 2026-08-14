# WO-TRIP-PHOTO-PALETTE-01 — P0 reconciliation map

**Status:** P0 COMPLETE — 2026-08-14. Offline inventory only. **No product code, no schema,
no migration, no live-data mutation, no stack cycle.**

**Verdict up front, so the rest can be read as evidence:**

1. **P1 needs no new endpoint.** Every Palette read the spec asks for is already served by
   `GET /api/trips/{trip_id}/photo-links`, in two queries with no N+1.
2. **P1 is three small things**, none of them an endpoint: one missing `WHERE` clause, one
   single-item JS function promoted to batch, and one duplicated predicate unified.
3. **Artifact contamination does not reach the Palette.** 22 of 36 narrators are harness
   residue, and **not one of them owns a trip**. The Palette is trip-scoped.
4. **One genuine semantic conflict needs Chris's ruling before P2** — the landed definition
   of *Unplaced* and the spec's definition disagree. It is §6 below.

---

## 1. Server inventory

### 1.1 Endpoints that already exist

| Method | Path | Serves |
|---|---|---|
| GET | `/api/trips/{id}/photo-links` | the whole operator photo list; `max_confidence`, `include_hidden` |
| GET | `/api/trips/{id}/narrator-photo-links` | narrator-safe subset; **carries no placements by design** |
| GET | `/api/trips/{id}/photo-inventory` | three ints: attached / on_a_day / cleared_for_lori |
| GET | `/api/trips/{id}/days` | day cards + per-day `photos` (explicit) and `photo_suggestions` (date-match) |
| GET | `/api/trips/{id}/days/{day}/timeline` | merged day timeline; photo items carry `placement_id` |
| POST | `/api/trips/{id}/days/{day}/photos/link` | **add** placements; accepts `photo_link_ids` and/or `photo_ids` |
| POST | `/api/trips/{id}/days/{day}/photos/unlink` | **remove** placements naming that day only |
| POST | `/api/trips/{id}/photos/placement-move` | **move** one occurrence, `{photo_link_id, from_day_id, to_day_id}` |
| PATCH | `/api/trips/photo-links/{link_id}` | caption, approvals, `hidden`, stop/region — never days |

### 1.2 What the read model already returns per row

`photo_links_list` (`trip_repository.py:2157`) merges three column sets and then
`apply_placement_serialization` (`:524`). Present today: `id` (the link id), `photo_id`,
`trip_day_ids[]`, `day_placements[]` (each with placement `id`, `trip_day_id`, `ord`,
`placement_method`, `placement_note`, `day_index`, `day_date`, `day_title`), `caption`,
`narrator_caption`, all four `*_approved_for_lori` flags, `photo_narrator_ready`, `hidden`,
`hidden_at`, `cluster_confidence`, `assignment_method`, `photo_metadata_trust`,
`photo_date_*`, `photo_location_label`, `photo_gps_present`, `taken_at`, and the derived
compatibility `trip_day_id`.

Measured against the spec's §6 read requirements, **nothing required is missing**. Three
cosmetic gaps, all client-side derivable and none worth an endpoint:

| Gap | Why it does not need server work |
|---|---|
| no `thumbnail_url` | the client already builds `/api/photos/{id}/thumb` in `thumbUrl()` |
| no `needs_review` boolean | `linkNeedsReview()` already applies the 0.50 threshold client-side |
| no `placement_count` | `day_placements.length` |

**`photo_link_id` is named `id`.** Not a defect, but the Palette must map it, and the spec
names the field `photo_link_id` — worth one comment at the call site rather than a rename
that would ripple through every existing consumer.

### 1.3 Paging, batch cap, write semantics

- **No paging anywhere.** `photo_links_list` has no `limit`/`offset` and ends
  `ORDER BY l.taken_at, l.ord` with no `LIMIT`. The whole set returns every call.
- **`PLACEMENT_BATCH_MAX = 50`** (`trips.py:3559`), enforced by `_reject_oversized_batch`
  **before** any write, returning **400** with a message naming the count, the limit, and
  "Nothing was written". Counts promotions too. Correct as-is.
- **Writes are transactional**, single commit, rollback on any exception. UNIQUE races are
  classified by `_is_placement_unique_violation` (`:4323`), which requires the message to
  name both `photo_link_id` and `trip_day_id` so an FK failure still raises rather than
  being mislabelled *already present*. Cross-trip ownership is asserted in-repo because
  SQLite cannot express it.
- **Move refuses cleanly**: a missing source returns `{"moved": False, reason:
  "source_placement_not_found"}` with an explicit rollback, surfaced as **409, zero writes**.
- **No N+1**: two queries total — the link/photo join, then one grouped placement query
  bucketed in Python. The docstring names the case it avoids: 401 queries for 400 photos.

### 1.4 Server-side filtering that exists

Only two, both on `/photo-links`: `max_confidence` (the caller must supply 0.50 itself) and
`include_hidden` (a boolean — there is **no hidden-only mode**). Unplaced, on-a-given-day,
and multiple-placements are **not** expressible server-side today, because `day_placements`
is computed after the SQL.

---

## 2. Client inventory

### 2.1 Surfaces that already render trip photos

`renderPhotos()` (`:6459`, Photos tab), the day inspector's two grids (`:4750` on-this-day,
`:4787` taken-on-this-date), `renderPhotoPicker()` (`:5483`, drawer), `renderLightbox()`
(`:6394`), `renderTimelinePhoto()` (`:10404`, inside the trip timeline modal), and the
travel-document photo cells (`:9099`).

### 2.2 The helpers the Palette should reuse rather than rebuild

| Helper | Line | State |
|---|---|---|
| `linkDayIds(l)` | 5915 | the single definition of "which days"; prefers `trip_day_ids[]` |
| `linkIsOnDay(l, dayId)` | 5920 | ready for the **Day N** filter |
| `linkIsUnplaced(l)` | 5924 | zero-placement semantics — **but see §6** |
| `linkNeedsReview(l)` | 5895 | `< 0.50` and not operator-assigned |
| `linkSharedWithLori(l)` | 5944 | OR of the four approval flags |
| `photoWindow` / `slidePhotoWindow` / `photoPager` | 4376 / 4400 / 4414 | page 50, step 50, mounted bound 200 |
| `st.photoPickerChecked` | ~350 | the one existing multi-select; **repaint-safe by design** |
| `addPhotosToDay(day, linkIds)` | 4437 | batch, chunks above 50, uniform `{added, unsent, error, reloadError, blocked}` |
| `dayFormDirtyBlocks()` | 4255 | guards all five photo actions today |
| `thumbImg` + `armLazyThumbs` | 714 / 765 | observer rooted per image on the real scrollport |

**`photoWindow` already implements the spec's §7 paging contract exactly** — initial 50,
increment 50, mounted cards bounded by construction (`start = end - wide`), and it is
independently proven by `scripts/ui/run_photo_window_arithmetic.js`, which executes the real
functions rather than a restatement.

### 2.3 Gaps on the client

1. **`renderPhotos()` is not windowed.** `:6497` iterates all of `filteredLinks()` with no
   pager. The Photos tab survives on four photographs; a Palette over a real library needs
   the `photoWindow` wiring the picker already has.
2. **The filter predicate is duplicated.** `filteredLinks()` (`:5969`) and the chip-count
   loop in `renderPhotos()` (`:6486`) each carry their own copy of the same switch. The spec
   says *"Filter counts and rendered results must use the same predicate."* Today they are
   the same only because someone kept them in step. **Unify before adding three filters**,
   or counts and contents will diverge and the divergence will look like a data bug.
3. **Selection is picker-specific.** `st.photoPickerChecked` is the right pattern and is
   already repaint-safe, but there is no shared selection model to inherit.
4. **`unlinkDayPhoto` is single-item** in JS while its wire body is already
   `{photo_link_ids: [linkId]}`. Promoting it to batch is a signature change, not a protocol
   change.
5. **The timeline modal has no mode switching.** No `cal.mode` exists. "Timeline | Photo
   Palette" is a new key on `st.tripCal` plus a branch around the right-hand pane; the day
   rail on the left is reusable as-is.
6. **A stale comment worth acting on.** `renderTimelinePhoto()` (`:10409`) passes
   `lazy: false` with a comment explaining that the floating panel's own scrolling body meant
   the native hint never fired. That reason expired on 2026-08-14: `lazyThumbScrollport` now
   resolves the panel's own scroller as the observer root. **The Palette can safely defer
   thumbnails inside the modal** — which is the whole reason its bounded-window contract is
   affordable there.

---

## 3. Requirement-by-requirement map

**R = reuse as-is · E = extend existing · M = missing, must build · D = decision needed**

### Filters (spec §5.2)

| Requirement | Verdict | Where |
|---|---|---|
| All | **R** | `filteredLinks()` default |
| Unplaced | **D** | `linkIsUnplaced` — see §6 |
| Day N | **E** | `linkIsOnDay()` exists; add the filter entries and a day selector |
| Multiple days | **M** | trivial: `linkDayIds(l).length >= 2` |
| Needs review | **R** | `linkNeedsReview()` |
| Hidden | **E** | `photoLinksForReview()` + `st.showHiddenPhotos` exist; the spec wants hidden as a *filter*, not only a toggle |
| counts and results share one predicate | **M** | unify the duplicated switch first |

### Card content (spec §5.3)

| Requirement | Verdict |
|---|---|
| 400px thumbnail | **R** — `thumbImg` + `/thumb` |
| shared caption or "No caption" | **R** — `caption` present |
| day labels from authoritative placements | **R** — `day_placements[].day_title`/`day_date` |
| Unplaced / Multiple / Hidden / Needs review badges | **E** — predicates exist, badges do not |
| approval shown separately from caption | **R** — separate flags already |
| selection persists across paging and repaint | **E** — copy the `st.photoPickerChecked` pattern |
| never expose paths / provider ids / GPS / tokens | **R** — read model exposes `photo_gps_present` as a boolean only |

### Actions (spec §5.4)

| Requirement | Verdict |
|---|---|
| Add selected to day (batch) | **R** — `addPhotosToDay` is already batch and already chunks |
| Hide / Restore selected (batch) | **E** — `PATCH /photo-links/{id}` sets `hidden` one at a time; batch is a client loop with truthful partial reporting |
| Remove selected from the filtered day | **E** — promote `unlinkDayPhoto` to batch |
| Move one named placement | **R** — `movePlacement` + `POST /photos/placement-move` |
| bulk Move forbidden without an explicit single source day | **R** — no bulk move exists to remove |
| edit shared caption | **R** — `PATCH /photo-links/{id}` |
| approval only via its own control | **R** — separate field on the same PATCH |
| no Delete in MVP | **R** — no delete route exists on this lane |

### Paging and performance (spec §7)

| Requirement | Verdict |
|---|---|
| initial 50 / load more 50 | **R** — `photoWindow` / `slidePhotoWindow` |
| mounted cards bounded ~200 | **R** — `PHOTO_WINDOW_MAX = 200`, bounded by construction |
| no per-day or per-photo cap | **R** — placement model has none; the 50 is per *request* |
| thumbnail endpoint, never originals | **R** — `thumbUrl()` |
| observer rooted on the actual Palette scroller | **R** — `lazyThumbScrollport` resolves it per image |
| no N+1 | **R** — two queries |
| sizes 0 / 1 / 49 / 50 / 51 / 200 / 500 / 1000 | **E** — the arithmetic harness covers the window; the batch boundary is covered server-side; 500/1000 needs a fixture, not new code |

### Failure and safety (spec §8)

| Requirement | Verdict |
|---|---|
| dirty day text blocks placement actions without losing typing | **R** — `dayFormDirtyBlocks` guards all five |
| partial batch reports what landed, retains only outstanding | **R** — `{added, unsent, blocked}` |
| write-then-reload-failure reports the write as successful | **R** — `reloadError` is separate from `error` |
| removing one day leaves other placement ids unchanged | **R** — proven by the WO-02 acceptance |
| move is one transaction | **R** |
| hidden photos stay deletion-safety attachments | **R** — force-delete counts are independent of display |
| a query failure surfaces, never an empty Palette | **E** — `st.error` exists; the Palette must not render zero-as-success |
| no action changes Lori approval implicitly | **R** |
| no action deletes originals/thumbnails/rows | **R** |

---

## 4. Does P1 need a new endpoint? **No.**

The one honest argument for a new endpoint is paging: `/photo-links` returns everything.
It is not persuasive here.

- The spec's paging numbers are a **mounted-DOM** contract, and `photoWindow` already
  satisfies it client-side over a single fetch — which is exactly what the day picker does
  today at a 200-card bound.
- Server-side filtering cannot be pushed down as the query is written, because
  `day_placements` is assembled after the SQL. Adding it means restructuring the read for a
  benefit no measured workload needs: the largest real trip holds **13** photo links.
- A second read endpoint would create a second definition of *unplaced* on the server, next
  to the client one. The multi-day lane spent its whole Phase 2 removing exactly that kind
  of duplicate authority.

**P1 is therefore three small changes:**

| # | Change | Why |
|---|---|---|
| 1 | add `AND p.deleted_at IS NULL` to `photo_links_list` | **latent defect** — `narrator_photo_links` (`:2032`) and `_day_photo_items` (`:5866`) both exclude soft-deleted photos; `/photo-links` does not, so a soft-deleted photograph would appear in the Palette grid. **Zero current instances** (measured, §5), which is why it has never been seen. |
| 2 | promote `unlinkDayPhoto` to accept an array | the wire body is already plural; Remove-selected needs it |
| 3 | unify the filter predicate | counts and results must not be able to disagree |

Anything beyond these is P2 UI work. **No schema change. No migration.** Per the spec, a
discovered schema need is a stop-and-review boundary, and none was discovered.

---

## 5. Artifact classification

Read from a **copy** of the live database opened `mode=ro`. The live file was never opened
and nothing was written. No narrator content is reproduced here — this document is tracked
and the repository is public, so rows are named by id and category only.

### 5.1 The finding that matters for scope

**22 of 36 narrators are harness residue, and not one of them owns a trip.** Trips: 2, both
Christopher's. Photos: 22 rows across 4 narrators. The Palette is trip-scoped, so
**narrator contamination cannot reach it**.

### 5.2 Classification

| Class | What | Disposition |
|---|---|---|
| **Genuine family memory** | 2 trips (Bismarck, Spring 2026 Central Europe); 17 trip photo links; 3 placements; 22 photos; 18 trip notes created in July | **Preserved. Untouched.** |
| **Acceptance evidence** | 2 notes created 2026-08-13 on Bismarck Day 1 (72 and 49 chars — the Stage A and Stage B quick notes); 1 conversation link placed on Day 1 (`operator_selected` / `confirmed`); 1 photo caption on link `2a54d793` | **Kept and labelled.** Chris's restore instruction was explicit: *leave these alone.* |
| **Test noise, out of scope** | 5 named harness narrator clusters — Walt ×7, Trip Canary ×9, Kent Horne (factual-chain harness) ×4, Test Harness Sarah Reed ×3, Esteban García (Spanish smoke harness) ×3 | **Not cleaned, by standing instruction.** `CLAUDE.md` records this as explicitly forbidden work, and `audit_identity_preflight.py` exits 1 on exactly these five clusters **by design**. They own no trips and touch nothing the Palette reads. |
| **Uncertain — listed for Chris, not resolved** | `mary` and `Marvin Mann` (the TEST-23 two-person resume canary, but not name-flagged); `Wally Banks` (owns 1 photo); `Amelia` (a real family name, but no trips and no activity) | **Left alone.** Uncertain is not a disposition an agent may resolve. |
| **Reference narrators** | Shatner, Dolly Parton — `narrator_type='reference'` | Deliberate; `_block_if_reference()` already refuses six family-truth operations on them. |

### 5.3 Incidental observations, none of them Palette scope

- **0 soft-deleted photographs currently hold a trip link**, so P1 change #1 is a guard
  against a class rather than a repair of a live symptom.
- **`trip_turn_links.captured_at` is empty on all 20 rows** on the Bismarck trip. Not a
  Palette input; recorded so it is not rediscovered as a Palette bug.
- **Three repository functions are dead**: `placement_reorder` (`:369`),
  `placement_backfill_preflight` (`:400`), `placement_backfill_skips` (`:388`) — defined,
  never called, never routed. The migration's skip ledger is therefore unreachable from any
  endpoint. Not Palette scope; flagged so a later reader does not assume the reorder path is
  exercised.
- The **six `interview_sessions → people` FK violations** remain a separate data-integrity
  job, as the checklist and HANDOFF both state.

---

## 6. The one decision that needs Chris before P2

**The landed definition of *Unplaced* and the spec's definition disagree.**

Landed, `travel-doc-lab.js:5924`:

```js
return !l.trip_stop_id && !linkDayIds(l).length;
```

Spec §5.2: *"**Unplaced** — zero `day_placements`."*

The conjunction with `trip_stop_id` is the difference. A photograph attached to a **stop**
but to no **day** is:

- **not** Unplaced under the landed code — it has a place in the route;
- **Unplaced** under the spec as written — it has zero day placements.

Both readings are defensible. *Unplaced* can reasonably mean "not anywhere on the route", or
it can mean "not on any day of the calendar". The Palette is a day-placement surface, which
argues for the spec's reading; the existing Photos tab has meant the other thing since
2026-08-13, and changing it silently would move photographs into and out of a filter Chris
already uses.

**Recommended:** keep the landed conjunction and make the spec say so, because the Palette's
Day N and Multiple-days filters already cover the day axis precisely, and because a
stop-assigned photograph genuinely is placed — just not on a day. **But this is Chris's
call, and P2 should not start until it is made**, since it decides what the Unplaced filter
shows on the first screen of the feature.

---

## 7. One consolidated regression command

Per-module, never whole-tree discovery. Verified green in the sandbox at **498 tests in
63 seconds**:

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest \
  tests.test_trip_photo_day_placements tests.test_trip_photo_day_placements_full_chain \
  tests.test_trip_photo_placement_api tests.test_trip_photo_placement_projection \
  tests.test_trip_photo_placement_suite_isolation tests.test_trip_photo_multi_day_ui \
  tests.test_narrator_photo_links_safe tests.test_travel_doc_doctrine \
  tests.test_travel_doc_lab tests.travel_doc_surfaces tests.test_travel_doc_surface_gates \
  tests.test_travel_doc_evidence_ui tests.test_trip_days_reconcile
```

Plus the two executable harnesses, which need no server and no browser:

```bash
cd /mnt/c/Users/chris/hornelore
node scripts/ui/run_photo_window_arithmetic.js
node scripts/ui/run_lazy_thumb_scrollport.js
node scripts/ui/run_photo_placement_safety.js
```

**A green sandbox run is evidence, not verification** — `.venv` on Chris's machine is the
verification, per the standing rule.

---

## 8. What P0 deliberately did not do

- No product code, no schema, no migration, no new endpoint.
- No live-data mutation of any kind; the database was read from a copy.
- No harness-narrator cleanup — forbidden work, and it owns nothing the Palette reads.
- No resolution of the Unplaced conflict in §6.
- No stack cycle. The stack stays down through P1 and P2, and starts once at P4, which also
  carries the owed live confirmation of the 2026-08-14 deferred-thumbnail fix.
