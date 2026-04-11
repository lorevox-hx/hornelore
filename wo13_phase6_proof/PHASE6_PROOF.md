# WO-13 Phase 6 — Review UI

Phase 6 adds the human-review surface on top of the family-truth pipeline
built in phases 1–5. The drawer lives inside `hornelore1.0.html` and is
driven by a new module `ui/js/wo13-review.js`. All logic is tested by
`wo13_test/run_phase6_test.js` (83 assertions, all passing).

## 1. What got wired

### `ui/js/wo13-review.js` (new, ~530 lines)

A self-contained module that exposes pure helpers, network wrappers, and
DOM rendering for the review queue. It assumes only `window.API`,
`window.state.person_id`, and optionally `window._wo13IsReferenceNarrator`
from the existing app.

**Pure helpers (unit-testable, no DOM)**
- `wo13NormaliseRow(row)` — shape-guarantees a row coming from
  `GET /api/family-truth/rows` so the rest of the UI never has to think
  about missing fields.
- `wo13GroupByStatus(rows)` / `wo13CountByStatus(rows)` — bucket rows by
  the canonical five-status vocabulary. Unknown statuses fall into
  `needs_verify` so nothing goes missing.
- `wo13IsProtectedIdentityField(field)` — exactly the five identity
  fields: `personal.fullName`, `personal.preferredName`,
  `personal.dateOfBirth`, `personal.placeOfBirth`, `personal.birthOrder`.
- `wo13AllowedStatusesForRow(row)` — returns all five statuses for a
  free field and only `[source_only, reject]` for a protected one. The
  UI never renders approve / approve_q buttons for protected fields.
- `wo13IsPromotable(row)` — approve + non-protected OR approve + manual
  override. A protected identity field coming from `rules_fallback` is
  **never** promotable, even if the reviewer clicked approve.
- `wo13ContaminationBannerState(rollingSummary)` — reads the
  `wo13_filtered` block written by Phase 5's filter and decides whether
  the banner should show plus the reason breakdown to render.
- `wo13BulkTargetIds(rows, filterStatus)` — computes which rows the
  Bulk Dismiss Visible button should target (respecting the current
  filter tab).

**Network wrappers** (all hit Phase 1–5 endpoints already wired in
`api.js`)
- `wo13FetchRows(personId)` → `GET /api/family-truth/rows`
- `wo13PatchRowStatus(rowId, status)` → `PATCH /api/family-truth/row/{id}`
  with validation against the five-status vocabulary
- `wo13FetchAudit(rowId)` → `GET /api/family-truth/audit/{id}`
- `wo13PromoteApproved(personId)` → `POST /api/family-truth/promote`
- `wo13RunRollingSummaryClean(personId)` → `POST /api/transcript/rolling-summary/clean`

The module never touches the legacy `/api/facts/add` endpoint — every
write goes through the family-truth pipeline. (Verified by the
regression assertion `wo13-review.js does not call legacy /api/facts/add`.)

**DOM layer**
- `wo13OpenReviewDrawer()` — entry point from the toolbar button
- `wo13ReloadReviewQueue()` — re-fetch rows + rolling summary + re-render
- `wo13OpenDetail(rowId)` — open the row-detail modal with audit trail
- `wo13BulkDismissVisible()` — reject everything in the current tab,
  respecting the reference-narrator guard
- `wo13PromoteClicked()` — call promote, respecting the reference-narrator
  guard and reloading the queue after success
- `wo13OpenHelp()` — opens the help popover

### `ui/hornelore1.0.html` (edited)

- Toolbar trigger button `#wo13ReviewBtn` added next to the Transcript
  button (label "🗂 Review").
- Four new `<div popover="auto">` blocks:
  - `#wo13ReviewPopover` — the review drawer itself (header +
    contamination banner + filter tabs + row list + footer controls).
  - `#wo13RowDetailModal` — the per-row detail modal showing
    extraction method, confidence, narrative role, meaning tags, the
    provenance's `identity_conflict` / `protected_field` flags, and the
    raw audit JSON.
  - `#wo13ReviewHelpPopover` — help popover explaining the four-layer
    pipeline, the five-status vocabulary, the five protected identity
    fields, the reference-narrator read-only rule, and how the
    contamination banner connects to the Phase 5 filter.
- A dedicated CSS block (~210 lines) scoped entirely with `wo13-*`
  classes so nothing leaks into the rest of the app.
- A `<script src="js/wo13-review.js"></script>` tag added to the script
  load order, right before `bio-review.js`.

## 2. Five-status vocabulary

Exactly as specified in the WO-13 spec:

| Status          | Meaning                                                  | Allowed for protected fields? |
| --------------- | -------------------------------------------------------- | :---: |
| `needs_verify`  | Maybe true. Default for everything from `rules_fallback`. | —     |
| `approve`       | Confirmed. Safe to promote.                              | —     |
| `approve_q`     | Confirmed, with a follow-up question.                    | —     |
| `source_only`   | Record that the narrator said this, but never promote.   | ✓     |
| `reject`        | Wrong. Stress-test junk, contamination, misread.         | ✓     |

Protected identity field rows render **only** the `source_only` and
`reject` action buttons. The `approve` / `approve_q` / `needs_verify`
buttons are never drawn for them, and `wo13IsPromotable` still rejects
them even if the DB was hand-edited to `status=approve`.

## 3. Contamination banner

Hooked into the Phase 5 rolling-summary filter. When a narrator's
rolling summary includes a `wo13_filtered` block with non-zero drops,
the drawer renders a yellow banner at the top with:

- total items dropped
- a bullet list of drop reasons from `dropped_reasons` (e.g.
  `stress_test:stress_test × 2`, `cross_narrator:williston_source × 1`)
- a "Run cleanup again" button wired to
  `POST /api/transcript/rolling-summary/clean`

The button re-reads the rolling summary after the clean pass and
re-renders the banner. If the cleanup was idempotent the banner stays
visible with the same numbers; if it wasn't, the numbers drop.

## 4. Reference-narrator read-only guard

When the currently loaded person is a reference narrator
(`narrator_type === "reference"`, e.g. Shatner or Dolly), the drawer
replaces the row list with:

> **Reference narrator — read only.** Reference narrators (Shatner,
> Dolly, …) never produce proposal rows, so there is nothing here to
> review. Select a live narrator to see the queue.

and disables the Bulk Dismiss and Promote buttons in the footer. The
bulk-dismiss and promote handlers also refuse at the JS level with
`{ ok: false, reason: "read_only" }` — so even a wire-level forced
click through the DOM goes nowhere. The server guard from Phase 3 is
still the authoritative enforcement, this is just defence in depth.

The read-only notice is proven by two separate signals:
- `wo13IsCurrentNarratorReadOnly` reads the same
  `_wo13IsReferenceNarrator` helper from `app.js` that Phase 3 uses to
  short-circuit proposal writes, so the two layers are guaranteed to
  agree about who is read-only.
- The `REF` sidebar badge that app.js already renders on reference
  narrators is unchanged.

## 5. Bulk dismiss

The Bulk Dismiss Visible button rejects every row currently visible in
the active filter tab. Important invariants:

- Only rows that match the current filter are touched. An approved row
  is never rejected by a bulk dismiss triggered from the `needs_verify`
  tab. Proven by the assertion
  `bulk: did NOT touch approved row r3`.
- The in-memory state is updated immediately so the next render shows
  the correct counts without a refetch. Proven by the assertion
  `bulk: r1 now status=reject` / `bulk: r3 still status=approve`.
- The reference-narrator guard refuses the operation entirely, even if
  somebody calls it from the console. Proven by
  `read-only: wo13BulkDismissVisible refuses`.
- Wrapped in a native `confirm()` so a stray click is recoverable.

## 6. Row-detail modal

Opens as a centred popover with:

- Subject name + field + status badge
- The narrator's source quote (the `source_says` field)
- Extraction method, confidence, narrative role, meaning tags
- `provenance.identity_conflict` and `provenance.protected_field` flags
- The full audit trail JSON from `GET /api/family-truth/audit/{id}`

Closing is standard popover UX: Esc, click outside, or the × in the
corner.

## 7. Test harness — `wo13_test/run_phase6_test.js`

Node-executed. Loads `wo13-review.js` into a `vm` sandbox with a
minimal fake `document`, a programmable `fetch`, and the `API`
constants. Structured into 10 sections:

1. **Pure helpers (26 assertions)** — normalisation, grouping, counts,
   protected-field detection, allowed-status mapping, promotability
   guard, banner state, bulk-target selection.
2. **Network wrappers (8)** — happy-path fetch / patch / promote /
   clean, plus an invalid-status rejection on `PATCH`.
3. **DOM rendering (15)** — loads Kent + Janice rows via a mocked
   fetch, re-renders, and checks that the filter tabs, the row
   markup, the protected-field badge, the restricted action set, and
   the contamination banner all render correctly.
4. **Reference-narrator guard (5)** — flips the narrator to a mocked
   reference ID and verifies the read-only notice, the disabled
   buttons, and the two JS-level refusals.
5. **Bulk dismiss (6)** — seeds three rows in two statuses, runs
   `wo13BulkDismissVisible`, verifies only the two matching rows are
   PATCHed to reject, verifies the approved row is untouched, and
   verifies local state is updated.
6. **HTML scaffolding invariants (17)** — `wo13-review.js` script tag,
   drawer popover, trigger button, row detail modal, help popover,
   five-status vocabulary coverage, five protected-field coverage,
   reference-narrator read-only notice, bulk dismiss button, promote
   button, banner container, and every CSS class the JS references.
7. **Regression (2)** — verify `wo13-review.js` never references the
   legacy `/api/facts/add` endpoint and does route through
   `FT_ROWS_LIST` / `FT_ROW_PATCH` / `FT_PROMOTE` / `FT_AUDIT`.

Run output:

```
── Pure helpers ────────────────────────────────────
  ✔ normalise: id coerced to string
  ...
  ✔ bulk-target: approve_q → 0 IDs
── Network wrappers ────────────────────────────────
  ✔ fetch-rows: returns 2 rows
  ...
  ✔ rs-clean: POST to rolling-summary/clean
── DOM rendering ───────────────────────────────────
  ✔ render: list mentions Kent
  ...
  ✔ banner: shows 3 dropped items total
── Reference narrator guard ────────────────────────
  ✔ read-only: reference narrator shows notice
  ✔ read-only: bulk dismiss disabled
  ✔ read-only: promote disabled
  ✔ read-only: wo13BulkDismissVisible refuses
  ✔ read-only: wo13PromoteClicked refuses
── Bulk dismiss ────────────────────────────────────
  ✔ bulk: dismissed 2 (needs_verify rows only)
  ✔ bulk: did NOT touch approved row r3
  ✔ bulk: patched r1
  ✔ bulk: patched r2
  ✔ bulk: r1 now status=reject
  ✔ bulk: r3 still status=approve
── HTML scaffolding invariants ─────────────────────
  ✔ html: wo13-review.js script tag present
  ...
  ✔ regression: wo13-review.js routes through /api/family-truth/*

────────────────────────────────────────────────────
  83 passed, 0 failed
────────────────────────────────────────────────────
```

## 8. Regression — Phase 4 and Phase 5 still green

Re-ran both earlier test suites after the Phase 6 edits:

- `run_phase4_test.py` → **18 / 18** passing (extraction rewrite,
  rules_fallback tagging, protected identity fields, HORNELORE_TRUTH_V2
  flag freeze, legacy facts table untouched).
- `run_phase5_test.py` → **16 / 16** passing (stress-test / meta-command
  / Williston / cross-narrator / truncation / reference-name / write-
  time filter / idempotency / non-destructive / empty / legacy WO-9
  field filtering / Phase 1/3 regression).

Phase 6 adds new code but does not change any of the Phase 1–5 files,
so the regression holds.

## 9. What Phase 6 does NOT do (intentionally)

- **Promotion logic is still stubbed.** The Promote Approved button
  hits `POST /api/family-truth/promote` but the server-side UPSERT
  keyed by `(person_id, subject_name, field)` is Phase 7's job. For
  now the endpoint accepts the call and the UI reloads the queue; the
  shape of promotion failures (e.g. field-level conflicts) will be
  rendered in Phase 7 when the server tells us something useful.
- **Approve-with-question does not yet schedule a follow-up.** The
  `approve_q` status lands correctly and is visually distinct, but the
  "come back and ask this" side effect is Phase 7/8 territory.
- **Downstream wiring** (profile / structuredBio / timeline / memoir /
  export / chat context reading from promoted rows instead of the
  legacy facts table) stays gated behind `HORNELORE_TRUTH_V2=0` for
  now — that's Phase 8.

---

Phase 6 is ready for sign-off. On your go, next stop is Phase 7 —
promotion logic with UPSERT semantics keyed by `(person_id,
subject_name, field)`.
