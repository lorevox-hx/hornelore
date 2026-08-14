# WO-TRIP-PHOTO-PALETTE-01

**Status:** **COMPLETE — P0 through P5 accepted 2026-08-14.**
*(This read "READY FOR EXECUTION after the Gate 4 cleanup map" until 2026-08-14.)*
**Date:** 2026-08-14  

> **CLOSEOUT.** All three gates met. Offline: 584 tests plus four harnesses
> (113 / 32 / 16 / 56), verified in `.venv`. Live: P4 final PASS. Restart persistence:
> P5 14/14 read-only then restoration 22/22.
>
> Evidence at `docs/reports/WO-TRIP-PHOTO-PALETTE-01_P4_LIVE_ACCEPTANCE.md` and
> `..._P5_PERSISTENCE.md`. **Local-only and deliberately not in the repository** —
> `docs/reports/` is gitignored because those files carry live narrator data. Written as
> paths rather than links, because a link would be broken for anyone cloning. This closeout
> is the tracked evidence and is meant to stand on its own.
>
> **One defect found live and fixed inside P4** (`b991353` code, `88429cc` tests): Add,
> Remove, Move and a caption save refreshed the visible photo pool but not the Palette's
> own hidden pool, so a hidden card kept showing a day it no longer had and a caption it no
> longer had. `reloadPalettePhotoPools(guard, {days})` now owns that rule in one place and
> is wired into five sites — the fifth, `unlinkDayPhoto`, was not in the reported set but
> carried the same bug. Eight mutations, eight killed by their intended checks.
>
> **Eight genuine photographs** were uploaded through the real intake drawer during
> acceptance and are preserved: memberships only, zero day placements, no approvals
> granted. Every temporary acceptance caption, placement and hidden flag was restored
> afterwards and re-verified against the original baseline.
>
> **Two items carried forward, neither blocking.** §5 ruling 5's *Region assigned* badge
> has **no operator route to create the state it describes** — `PhotoLinkPatch` has neither
> a region field nor a clear-stop flag — which is a product decision, not a Palette defect.
> And the §7 acceptance sizes above 12 remain proven by
> `scripts/ui/run_photo_palette_behaviour.js` and `run_photo_window_arithmetic.js` rather
> than live; the trip holds 12 memberships and no rows were manufactured to change that.
>
> **Phase 6 legacy-column retirement is NOT authorized by this closeout.**
**Lane:** Travel Document / photo organization  
**Priority:** Next product build  
**Depends on:** completed `WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01`

## 1. Outcome

Add a **Photo Palette** mode inside the existing Travel Document workspace so an operator
can see the trip's unique photographs, understand every placement, select several photos,
and deliberately add, remove, move, hide, restore, review and caption them without
duplicating assets or confusing placement with ownership.

The Palette organizes existing Hornelore photographs. It is not an importer, a second
timeline, an AI-photo-analysis surface, or a permanent-photo deletion screen.

## 2. Researched product model

Established photo systems separate a permanent library item from membership in one or more
albums/collections:

- Google Photos adds existing media to albums in batches of up to 50 and preserves request
  order; its documented album maximum is 20,000 items. Hornelore adopts the 50-item
  transport batch but deliberately has no product cap per day.
- Apple Photos permits adding a library photo to albums and states that removing it from one
  album does not remove it from the library or other albums.
- PhotoPrism generates scaled previews/thumbnails because rendering originals in search
  results consumes browser memory and harms performance.
- Browser guidance on large lists recommends keeping DOM size bounded; IntersectionObserver
  must use the real scroll container as its root when used inside a nested scroller.

Primary references:

- <https://developers.google.com/photos/library/reference/rest/v1/albums/batchAddMediaItems>
- <https://support.apple.com/guide/photos/create-and-work-with-albums-pht6d60a1f1/mac>
- <https://docs.photoprism.app/user-guide/settings/advanced/>
- <https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API>
- <https://web.dev/articles/dom-size-and-interactivity>

Hornelore's canonical layers are therefore:

```text
photos                         permanent asset + original + derivatives
trip_photo_links               unique membership in one trip + shared caption/context
trip_photo_day_placements      zero/one/many explicit day occurrences
```

## 3. Binding rulings

1. A permanent photo is stored once.
2. A photo joins a trip once.
3. A trip photo may be placed on zero, one or many days.
4. A day may contain any number of photos.
5. **Two questions, kept apart — AMENDED 2026-08-14 by review ruling.**
   This read: *"Unplaced means zero authoritative placements. It never means
   `trip_photo_links.trip_day_id IS NULL`."* The second sentence stands
   unchanged and always will. The first was doing two jobs at once, and the
   Palette needs them separated:

   - **Not on a day** — `linkDayIds(link).length === 0`. This is the
     Palette's filter, because the Palette organises photographs onto DAYS.
   - **Completely unplaced** — no `trip_region_id`, no `trip_stop_id`, and
     zero day placements. This is a badge, not a filter.

   A stop- or region-assigned photograph with no day is **Not on a day** and
   is **not** completely unplaced, and the card shows both facts. Neither
   rule ever reads the compatibility scalar.

   **The review also caught what the landed code had always been missing:**
   `linkIsUnplaced()` tested stop and day and **forgot `trip_region_id`
   entirely**, so a photograph filed to a region was reported as unplaced.
   P0 did not account for that field either.
6. Caption and Lori approval belong to the trip membership and are shared across placements.
7. Add is the normal action. Move is explicit and names a source placement. Remove affects
   one occurrence only.
8. Hide is reversible presentation state. Delete is destructive and absent from Palette MVP.
9. Taken-date matches are suggestions, never placements until the operator accepts them.
10. The Palette uses thumbnails; originals open only on deliberate full view/download.

## 4. Reuse before build

Phase 0 must inventory and reuse the behavior already landed in `travel-doc-lab.js`:

- `linkDayIds()` and zero-placement semantics;
- On this day / Taken on this date sections;
- Add, Remove from this day and source-named Move;
- 50-item request batching;
- bounded sliding photo windows;
- selection state surviving repaint/window movement;
- dirty-form guards;
- partial-write and reload-failure truthfulness;
- shared 400px thumbnail endpoint;
- current trip, selected day, drawer and lightbox state.

The Palette must centralize these helpers or call them. It must not fork a second placement
implementation beside them.

## 5. UI contract

### 5.1 Location

Inside the existing Trip Calendar/Timeline modal:

```text
Timeline | Photo Palette
```

No second backdrop, nested modal, separate standalone app, or competing selected-day state.

### 5.2 Filters

- **All** — every live, non-deleted trip membership once.
- **Unplaced** — zero `day_placements`.
- **Day N** — membership has a placement on that day.
- **Multiple days** — two or more placements.
- **Needs review** — existing review/metadata-trust posture; do not invent a second flag.
- **Hidden** — hidden trip memberships, explicitly requested.

Filter counts and rendered results must use the same predicate. Taken-date suggestions do
not increase Day N's explicit placement count.

### 5.3 Card content

Each card shows:

- 400px thumbnail;
- shared caption or clear “No caption” state;
- day labels from authoritative placements;
- Unplaced / Multiple days / Hidden / Needs review badges as applicable;
- Lori approval shown separately from caption existence;
- selection control with persistent state across paging and repaint.

Never expose raw storage paths, raw provider identifiers, raw GPS, tokens or internal
staging references.

### 5.4 Actions

Batch-safe:

- Add selected to day;
- Hide selected;
- Restore selected from Hidden.

Contextual:

- Remove selected from the currently filtered day;
- Move one named placement from source day to destination day;
- edit the shared caption;
- explicitly change Lori approval through its existing separate control.

Bulk Move is forbidden unless a single source day is explicit for every selected item.
A multi-day photograph cannot be moved correctly from a bare photo-link id.

No Delete action in MVP.

## 6. API and repository contract

Prefer existing endpoints. Add an endpoint only if the current inventory cannot provide a
truthful or performant Palette.

Read responses require:

- unique `photo_link_id` and `photo_id`;
- `trip_day_ids`;
- ordered `day_placements` including placement id/day/ord/method;
- caption, approval, hidden and review state;
- safe thumbnail URL or photo id;
- safe capture-date/location summaries only where already authorized.

Writes:

- use `trip_photo_day_placements` exclusively;
- preserve membership and asset on placement removal;
- validate narrator, trip, day and link ownership transactionally;
- reject 51+ items per request with 400 and zero writes;
- treat an already-present pair idempotently;
- classify UNIQUE races instead of returning 500;
- return per-batch `{added, already_present, failed/unsent}` truth;
- never silently truncate or close a drawer after a partial failure.

No schema migration is expected. Any discovered schema need is a stop-and-review boundary.

## 7. Paging and thumbnail performance

- initial page: 50;
- Load more: 50;
- selection persists outside the mounted window;
- mounted Palette cards remain bounded around 200;
- no hard per-day or per-trip-photo cap;
- grid uses `thumb_400`/thumbnail endpoint, never original bytes;
- nested scrollers use eager thumbnails per bounded page or IntersectionObserver with the
  actual Palette scroller as `root`;
- requests are sequential enough to preserve order and honest failure boundaries;
- no N+1 placement or day-label queries.

Acceptance sizes: 0, 1, 49, 50, 51, 200, 500 and 1,000 trip memberships/placements.

## 8. Failure and safety contract

- Dirty day text blocks placement actions without losing typing.
- A partial batch reports exactly what landed and retains only outstanding selections.
- A successful write followed by reload failure reports the write as successful and the
  screen as stale; it never reports the write as failed.
- Removing one day leaves all other placement row ids unchanged.
- Moving creates/removes only the named occurrences in one transaction.
- Hidden photos remain deletion-safety attachments even when absent from display counts.
- A lock/I/O/query failure surfaces; it never becomes an empty Palette or zero count.
- No action changes Lori approval unless the operator used the approval control.
- No action deletes originals, thumbnails, photo rows or trip memberships.

## 9. Execution blocks

### P0 — reconciliation map, no product mutation

- inventory current Palette-like UI and endpoints;
- map every required filter/action to reuse, extension or missing support;
- reconcile cleanup artifacts that would pollute live acceptance;
- confirm no schema change;
- confirm whether P1 needs any new endpoint at all, or only new query support behind
  endpoints that already exist;
- record exact test modules and one consolidated regression command.

**Artifact classification is part of P0 and is not a separate work order.** The checklist
named a `WO-LIVE-TRIP-CLEANUP-01` gate that was never written; rather than leave the queue
pointing at a document that does not exist, its requirements are absorbed here, where the
inventory is happening anyway. Every contaminated acceptance/test artifact is classified as
exactly one of:

| Class | Disposition |
|---|---|
| Genuine family memory | **Preserved.** Never hidden, never deleted, whatever else is true of it. |
| Test noise | Hidden **reversibly** — the existing `hidden` flag, never a delete. |
| Acceptance evidence | Kept and labelled as evidence, so a later reader cannot mistake it for family material. |
| Uncertain | **Left alone and listed for Chris.** Uncertain is not a disposition an agent may resolve. |

**No destructive deletion, at all, without Chris.** P0 mutates nothing: it produces the map
and the classification, and the map is what gets reviewed.

**Review gate:** map approved. Continue without starting the stack.

### P1 — data/query contract — **LANDED 2026-08-14**

Three changes, no new read endpoint, no schema, no migration:

1. `photo_links_list()` excludes soft-deleted photographs
   (`AND p.deleted_at IS NULL`, probed so a pre-column database degrades
   rather than 500s). Latent when found — zero live instances.
2. The read order is now **total**: `ORDER BY l.taken_at, l.ord, l.id`.
   `taken_at` ties on every burst and every undated link, `ord` ties on
   everything never reordered, and a window over a nondeterministically
   ordered array moves cards between renders.
3. New `POST /api/trips/{trip_id}/photo-links/visibility` taking
   `{photo_link_ids, hidden}` — atomic batch Hide/Restore, max 50 rejected
   at 400 with zero writes, ownership validated for every id inside the
   write transaction, idempotent, returning `requested` / `updated` /
   `already_in_state` / `changed`. It names three columns — `hidden`,
   `hidden_at`, `updated_at` — so it cannot move a placement, edit a
   caption or flip an approval.

**Gate met:** `tests/test_trip_photo_visibility_batch.py`, 33 tests across
sizes 0/1/49/50/51, mixed ownership, rollback, idempotence, preserved
placements, soft-deleted exclusion, total order and 1,000-membership scale.
Five mutations of the shipped code each killed by their intended test.

**One correction recorded rather than quietly fixed.** A draft test asserted
that a link whose photos row is missing survives the read. The SQL reasoning
was right and the scenario is unreachable: `photo_id` carries
`REFERENCES photos(id) ON DELETE CASCADE`, so there is no orphan to keep.
The guarantee is the constraint, not the `WHERE` clause.

### P2 — Palette UI — **LANDED 2026-08-14**

`Timeline | Photo Palette` is a **mode of the existing trip calendar modal**
— one backdrop, one selected trip, one selected day; only the right pane
changes. Five named predicates (`linkHasNoDayPlacement`,
`linkIsCompletelyUnplaced`, `linkIsOnDay`, `linkIsOnMultipleDays`,
`linkMatchesPaletteFilter`), and **one** dispatcher drives both the chip
counts and the cards they label, so they cannot disagree.

Selection is a map keyed by `photo_link_id` held in `st`, never in a render
closure — `renderAll()` rebuilds every node in this module, so a closure
selection is emptied by every filter press and every Load more. Ticking a
box deliberately does **not** repaint, because that rebuilds the input under
the operator's finger. Select all is labelled **Select all shown**.

One sequential batch runner is shared by Remove and Hide/Restore, carrying
the contract Add already earned: chunk at 50, stop at the first failure,
record later batches as unsent without sending them, keep the failed batch
separate from the unsent, and never let a failed refresh downgrade a known
write. Only confirmed successes leave the selection.

Stale responses are refused by a **generation identity** rather than
`AbortController`: `api()` is the single fetch choke point and threading a
signal would change every call site for a guarantee this achieves at the
point of use. Aborting saves a download; refusing to apply is what protects
the screen.

Accessibility is native checkboxes and buttons with accessible names, a
visible focus ring and one `aria-live="polite"` status region. **No
`role="grid"`** — that pattern needs roving focus and arrow-key navigation,
and this grid recycles its window so most rows are not in the DOM.

**Gate met:** `tests/test_trip_photo_palette_ui.py` (41 guards) plus
`scripts/ui/run_photo_palette_behaviour.js` (55 executed checks, including
the 1,000-membership evidence). Five mutations each detected.

#### P2 corrections — 2026-08-14, after live review

Nine gaps that the source-shape tests could not see, found by review and by
driving the real UI. The first made the feature unusable:

1. **The action bar never kept up with the selection.** `disabled` was
   decided at render time, ticking deliberately does not repaint, and the
   change handler re-derived only the count. Select a photograph and every
   action stayed disabled; clear the selection and they stayed enabled.
   Measured live in both directions. The bar is now rebuilt in place by
   `paletteRefreshBar` on every tick — count *and* every button.
2. **Hidden was not self-contained.** It read `st.hiddenPhotoLinks`, which
   is only populated when the *Photos tab's* toggle is on, and its loader
   swallowed failures into an empty array. The Palette now loads its own
   pool, shows `(?)` before loading and `(!)` on failure, and renders an
   error rather than an honest-looking zero.
3. **The stale-response guard was never called.** `paletteGenerationIsCurrent`
   was defined and unused. It now gates every async apply, and every batch
   captures `tripId` once so a trip change mid-run cannot send the
   remaining ids to the new trip.
4. **Timeline "Move to…" performed an Add.** It POSTed to the day-link
   route, which adds a placement under the multi-day model and removes
   nothing, so a photograph "moved" ended up on both days. It now uses the
   atomic placement-move endpoint when both ends are named.
5. **"Select all shown" selected unseen cards** — the whole filtered list
   rather than the mounted window. Now the window, and it says so.
6. **Remove could claim success for ineligible ids.** Selection persists
   across filters, so it can hold photographs not on the visible day.
   `paletteRemovableIds` derives eligibility; ineligible ids stay selected.
7. **No route to the caption or approval surface.** Cards now carry
   **Open photo details**, reusing the existing editor rather than
   duplicating either.
8. **`role="tablist"` without tab keyboard behaviour** → a labelled group
   of native buttons with `aria-pressed`.
9. **Batch results overstated changes.** `changed` and `already_in_state`
   are now aggregated, so hiding fifty of which forty-nine were already
   hidden reports "Hid 1; 49 were already hidden".

**One reported finding was withdrawn rather than fixed.** Palette
thumbnails appeared never to load; measured again with the tab actually
visible, all four load correctly. Chrome does not deliver
IntersectionObserver callbacks to a background tab. The deferral mechanism
works inside the modal, which is also the first confirmation that the
2026-08-14 scrollport fix holds in its new home.

### P3 — consolidated offline verification

Run one combined Travel Document regression set after P1+P2. Do not rerun the full set after
each trivial correction. Mutation-test only the placement predicate, partial batch truth,
remove-one preservation, dirty guard and approval separation.

### P4 — live acceptance

Start the stack once and hard reload. Using a real trip:

1. switch Timeline ↔ Palette without losing selected trip/day;
2. verify every filter count equals its cards;
3. select across more than one 50-item window and confirm selection survives;
4. add one photo to two days without duplicating membership;
5. batch add several photos;
6. remove one occurrence while another survives;
7. move a named occurrence;
8. hide and restore without deleting;
9. edit caption on one occurrence and see it on all;
10. confirm approval stays unchanged;
11. inspect F12/logs for duplicate requests, originals fetched in grid, console errors,
    legacy writes or unclassified failures.

Restart once at the end and repeat the read-only checks for persistence.

## 10. Required tests

Behavioral tests must prove:

- multi-day scalar-null photo is not Unplaced;
- zero-placement photo is Unplaced;
- each membership renders once in All even with several placements;
- Day filters and counts use explicit placements only;
- selection survives filter/page/window changes;
- 50 batching and 51 server rejection;
- partial failure and reload failure remain distinct;
- Remove/Move preserve unrelated placement ids and assets;
- hidden/review filters do not collapse into each other;
- caption edit never grants approval;
- raw paths/GPS/provider references are absent;
- bounded DOM and thumbnail-only grid at 200/500/1,000;
- no production write to legacy `trip_photo_links.trip_day_id`.

## 11. Non-goals

- permanent photo deletion;
- importing from Google or local disk;
- duplicate detection or hash-clash redesign;
- AI image analysis, face recognition or semantic tagging;
- per-placement alternate captions or approval;
- changing memoir prose rules;
- dropping the compatibility scalar;
- model/prompt/STT/TTS/safety changes;
- cleanup of unrelated family data or historical evidence.

## 12. Definition of done

- operator can find every trip photo and understand its placement set;
- Unplaced is authoritative and correct for zero/one/many placements;
- batch and contextual actions are explicit, transactional and truthful;
- no asset is duplicated or deleted by organization actions;
- large collections remain reachable with bounded DOM and thumbnails;
- existing Travel Document state and dirty guards survive Palette rerenders;
- automated, live-browser and restart persistence evidence pass;
- the work order is closed in `HANDOFF.md` and the master checklist.

## 13. Research decisions retained

- Adopt Google-style 50-item transport batches, not Google's 20,000 album cap.
- Adopt Apple-style removal semantics: remove membership/placement, preserve library asset.
- Adopt PhotoPrism-style derivative browsing: thumbnails/previews, not originals.
- Adopt browser windowing/bounded-DOM guidance rather than rendering the full collection.
- Preserve Hornelore's stronger local-first privacy and explicit-operator-placement rules.
