# WO-POST-LORI-CLEANUP-AND-UNBLOCK-01 — consolidated closeout

**Date:** 2026-07-27
**Baseline entering:** `b91518c`
**Predecessor:** BUG-LORI-REASONING-LEAK-01, closed.
**Shape:** three lanes, delivered as one package. Per the work order, no per-lane work
orders were opened.

---

## Verdict at a glance

| Lane | Subject | Code | Tests | Live |
|---|---|---|---|---|
| 1 | Runtime/test env drift audit | n/a (audit) | n/a | n/a |
| 2 | `lv80ToggleNarratorSwitcher` ReferenceError | landed | 11 new, green | **verified in Chrome** |
| 3 | Operator promotion surface for trip notes | landed | 24 new, green | **blocked on API restart** |

One honest caveat up front, stated before anything else: **Lane 3 has unit proof but not
live proof.** The route is absent from the running server's OpenAPI schema because the
uvicorn process on :8000 predates the `trips.py` edit. Chris owns starting and stopping the
stack, so this closes with that check outstanding. Everything else is done.

---

## Lane 1 — Runtime / test environment drift audit

Full report: **`docs/reports/VENV_DRIFT_AUDIT_2026-07-27.md`**. Summary of the rulings:

- **`transformers` 4.55.4 vs 5.8.0 — defer, with an environmental rule.** The mismatch is
  real but currently **inert**: zero test files import `transformers`, and the only path
  that could reach it (`api.py`) hard-imports `peft` at module scope, which `.venv` does
  not have. A version skew in code that never runs cannot make a test lie. Hand-downgrading
  would drag `huggingface-hub` 1.14.0 → 0.36.2 and `tokenizers` 0.22.2 → 0.21.4 with it —
  a bigger dependency problem than the one being solved, which the work order explicitly
  warned against. The rule instead: **any suite importing `transformers` runs in
  `.venv-gpu`.**
- **The web stack — align now. This is the drift nobody had named, and it is the live
  one.** `starlette` 0.52.1 → **1.0.0** (a 0.x → 1.x major) plus `httpx` 0.27.2 → 0.28.1,
  `fastapi` 0.135.1 → 0.136.1 and `pydantic` 2.12.5 → 2.13.4, underneath **eight suites
  that drive `TestClient` against the real app**. Those suites are currently validating a
  different web framework generation than the one serving the stack. A copy-paste install
  block and the re-run block are in section 8 of the audit. **Not executed here** — a
  seven-package framework downgrade under eight suites deserves a deliberate run, not a
  slip-in alongside two unrelated lanes.
- **torch / triton / CUDA — intentionally diverge.** `requirements-gpu.txt` omits torch on
  purpose; `.venv` runs no model code so its torch is inert. Not churned, per instruction
  and on the merits.
- **`peft` / `accelerate` / `bitsandbytes` — intentionally diverge**, per explicit scope,
  and independently correct per the reasoning above.
- **11 lazily-imported packages — defer, documented.** All imported inside function
  bodies, so a `.venv` test that reaches one gets a loud `ModuleNotFoundError`. A test that
  fails visibly is not a test that lies.
- **Independent finding: the serving venv is off its own pin.** `requirements-gpu.txt` pins
  `lxml==6.0.2`; `.venv-gpu` runs 6.1.1 (`.venv` is the one that matches). Nothing is
  broken by it, but it means the pin file no longer describes the serving venv truthfully.
  Left as Chris's one-line call — it touches the serving venv, which the agent does not
  modify.
- **Deliverable:** a proposed `requirements-test.txt` (audit section 8) and a written
  statement of which environment is authoritative for which kind of test (audit section 7).

---

## Lane 2 — `lv80ToggleNarratorSwitcher is not defined`

### Diagnosis

The work order asked whether the function was renamed, removed, or never loaded. **None of
the first two.** Static analysis found the function alive and well at `hornelore1.0.html`
line 6546, only three occurrences of the name repo-wide, the inline block syntactically
clean, and the declaration genuinely top-level in a classic script.

The answer was **load order**. The header narrator card sits near the top of `<body>` and
carries an inline `onclick`, but its handler is declared ~3,600 lines into a ~105 KB inline
`<script>` that starts at line 5532, with roughly 60 external scripts still loading behind
it. During the ~4-minute cold boot an operator can click the chip before that block has
finished evaluating.

### The browser confirmed it exactly

Immediately after navigating to `http://localhost:8082/ui/hornelore1.0.html`:

    {"cardExists": true, "onclickHasGuard": true, "toggleOnWindow": "undefined",
     "openOnWindow": "undefined", "popoverExists": true, "scriptCount": 25}

The clickable card is painted and reachable while the handler is still undefined. Six
seconds later:

    {"readyState": "complete", "scriptCount": 82,
     "before": {"toggle": "function", "open": "function"}, "clickThrew": null}

`scriptCount` 25 → 82 is the external-script tail finishing. That is the race, measured.

### The fix — two halves, both small

1. **`ui/hornelore1.0.html` line 2928**, the inline handler is now feature-tested:

       onclick="window.lv80ToggleNarratorSwitcher ? window.lv80ToggleNarratorSwitcher() : console.warn('[lv80] narrator switcher not ready yet — page still loading')"

   An early click now warns instead of throwing. `console.warn`, not a native dialog — the
   no-native-dialog rule holds on the operator path.

2. **Explicit `window` mirrors**, inserted immediately before `lv80ConfirmNarratorSwitch`:

       window.lv80ToggleNarratorSwitcher = lv80ToggleNarratorSwitcher;
       window.lv80OpenNarratorSwitcher   = lv80OpenNarratorSwitcher;

   This makes the global binding **intentional** rather than a side effect of sloppy-mode
   top-level function declarations — the same convention already used for the WO-10C
   silence-ladder constants further down the file.

**The function body at 6546 was not touched.** The control is fixed, not retired.

### Verification

- `node --check` on the extracted inline block (lines 5532–9898, 4365 lines): **SYNTAX OK**.
- A **real mouse click** at (440, 74) opened the Narrators switcher listing Melanie Zollner
  (TEST), Janice Josephine (Zarr) Horne, Kent James Horne and Christopher Todd Horne, plus
  "+ Add Narrator" and the three opening styles. Behaviour preserved.
- Console filtered for `lv80ToggleNarratorSwitcher|is not defined|ReferenceError|narrator switcher not ready`:
  **no messages**.
- **`tests/test_narrator_switcher_handler.py`** — 11 new tests, green. They assert the card
  is not a bare `onclick="lv80ToggleNarratorSwitcher()"`, that the guard literal is present,
  that it degrades to `console.warn` with no native dialog, that the function is defined
  exactly once and both mirrors exist after the declaration, and that the switcher still
  toggles the popover, still blocks in trainer mode, and **still honours the CHRIS RULE**
  (`assertNotIn("await", body)`, `assertIn("_lv80RenderOrKickRefresh()", body)`).

One thing investigated and dismissed: a programmatic `card.click()` reported
`popoverOpenedByClick: false`. That is popover light-dismiss consuming the same synthetic
click event — `trainerActive: false`, `popAttr: "auto"`, and a direct
`window.lv80ToggleNarratorSwitcher()` call returned `afterDirect: true`. Not a defect, not
touched.

---

## Lane 3 — Operator promotion surface for "In memoir" trip notes

### The actual problem

The capture chain worked and the memoir lane correctly filtered on `include_in_memoir=1`.
But every captured note was `include_in_memoir=0` and **there was no way to find them**. A
note captured by the Travel Doc modal lands under whichever trip/region/stop/day scope the
operator happened to be in, and the only list surface was the per-trip Story Notes list —
which requires already knowing the trip. The toggle existed; it was unreachable.

The work order's instruction was explicit: *prefer a review/list surface over changing the
capture rules*. That is what shipped.

### What was built

**Repository layer — `server/code/api/services/trip_repository.py`** (3268 → 3441 lines).
`captured_notes_review_list(person_id, source_surface, include_hidden, promoted, limit)` and
`captured_notes_review_counts(person_id)`. Read-only. Joins `trips`, LEFT JOIN
`trip_regions`, LEFT JOIN `trip_stops`. Newest-first (`ORDER BY n.created_at DESC, n.id DESC`).
Tolerant of pre-0036 (no `hidden`) and pre-0031 (no `source_surface`) schemas; returns `[]`
on `sqlite3.OperationalError` rather than 500-ing. Limit clamped to 1..1000 — not trusted.

**Route — `server/code/api/routers/trips.py`** (→ 3459 lines).
`GET /api/trips/captured-notes`, flag-gated by `_require_trips_enabled()` like every other
trip route. Single-segment path, safe at any position in the module: there is no bare
`@router.get("/{trip_id}")` to shadow it, and `/capture-status` is the existing
single-segment precedent. Verified against the full on-disk route inventory.

**UI — `ui/js/travel-doc-lab.js`** (6432 → 6670 lines). A new **"Captured Notes"** tab in
Travel Doc Lab, exempt from the `st.trip` gate exactly as Evidence already is — because the
whole point is finding notes when you *don't* know the trip. Rows show source type,
source surface, current In-memoir state, hidden badge, trip title, scope label, created
date, title, and a 400-character text preview. Filters for surface, promotion state and
hidden. A counter strip shows the `travel_doc_modal` count alongside
total/promoted/unpromoted/hidden. `reloadCaptured()` mirrors `reloadEvidence()`'s 404 →
`capturedOff` posture, because flag-off is configuration, not an error, and must not paint
the workspace-wide red bar.

### What was deliberately NOT built

**No new write route.** Promotion reuses the pre-existing
`PATCH /api/trips/location-notes/{note_id}` with the validation it has always had. The new
surface is read-only plus that one existing write. `include_in_memoir=0` remains the
default. Nothing auto-promotes. Nothing reaches the archive. The two-surface rule is
untouched, and no `travel_doc_modal` turn is written to the life-story archive.

### Verification — `tests/test_captured_note_review.py`, 24 tests, green

Against **real sqlite**, not mocks: two people, one trip with region and stop,
`HORNELORE_TRIPS=1`.

Mapped to the work order's five acceptance lines:

| Acceptance | Proof |
|---|---|
| Operator can find captured Travel Doc modal notes | `FeedShapeTest` — shows-what-operator-needs, crosses-trips, surface filter, newest-first, no narrator leak |
| Operator can promote/demote a note | `OperatorToggleIsTheOnlyPromotionTest` — promote, demote, and reflected in feed + counts |
| Unpromoted notes stay out of memoir | `MemoirLaneWiringTest`, driving the **real** `memoir_export._trip_story_sections(person_id)` |
| Promoted notes appear in the memoir trip lane | same class — promote via the operator endpoint, note appears; demote, it leaves |
| Default stays off, operator toggle is what changes it | `DefaultRemainsOffTest` — arrives unpromoted, the feed does not promote what it reads, counts confirm |

Plus `ScopeWallTest`, which asserts the scope walls in source: only PATCH writes in the
`renderCaptured` block; no reach for `/api/archive`, `archive.append`, `append_event` or
`/api/memoir-export`; the route never defaults promotion on and never calls
`location_note_update/create/delete`; `@router.get("/captured-notes")` appears exactly once
with no post/patch/put/delete variant; no native dialog.

### Outstanding

`GET /api/trips/captured-notes` returned **405** live, and `openapi.json` confirms the path
is absent from the running schema. The request falls through to
`PATCH`/`DELETE /api/trips/{trip_id}` and Starlette answers 405. **This is a stale server
process, not a routing defect** — the on-disk inventory is correct. Needs an API restart,
which is Chris's.

---

## Incidental fixes — found on the path, fixed and documented

Both under the standing order: *"note if there is an issue that we can fix not dont wait
fix it and document so we have it in the git."*

### 1. Sixteen test files whose stubs made tests lie

This is Lane 1's stated problem in its purest form, and it turned out to be the most active
one. Most offline suites install hand-written `sys.modules` stubs before importing product
code, behind an `if "pydantic" not in sys.modules` guard — which means **whichever file
loads first wins, and every sibling in the process silently inherits its stub.**

Thirteen files shipped `class _BaseModel: pass`. That satisfies `class X(BaseModel)` at
definition time but not `X(id=..., label=...)` at call time, so
`MemoirSection(BaseModel)` raised `TypeError: MemoirSection() takes no arguments` — but
only when the wrong file won the race. Suites passed alone and failed in batch on
alphabetical load order alone. `tests/test_trip_location_notes.py` additionally registered
`sys.modules["fastapi"]` without a `fastapi.responses` submodule, so any sibling loaded
afterwards that imports `api.routers.memoir_export` died at **collection** with
`unittest.loader._FailedTest` — which is how `test_memoir_trip_story_lane` had been
erroring.

Swept 16 files: `_BaseModel` given a kwargs `__init__`, `Field` replaced with a
`default_factory`-aware `_field`, and the missing `fastapi.responses` added. Every rewrite
`ast.parse`-gated before write. Files:

    tests/test_evidence_lifecycle.py            tests/test_trip_days.py
    tests/test_stop_type_validation.py          tests/test_trip_days_reconcile.py
    tests/test_travelogue_builder.py            tests/test_trip_editable_fixes.py
    tests/test_travel_doc_evidence_preflight.py tests/test_trip_force_delete.py
    tests/test_travel_doc_evidence_tools.py     tests/test_trip_lane_fixpack02.py
    tests/test_trip_auto_day_generation.py      tests/test_trip_location_notes.py
    tests/test_trip_patch.py                    tests/test_trip_reorder_move.py
    tests/test_trip_sources.py                  tests/test_trip_stop_upload.py

The durable fix is one shared `tests/_offline_stubs.py` so there is one definition to be
right instead of thirteen to drift. That is a ~30-file refactor and is **not** in this work
order — recorded in the audit as the next environment-hygiene item.

### 2. `tests/test_trip_editable_fixes.py` — 4 pre-existing FK errors

Four tests errored with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` inside
`photo_link_upsert`. Cause: the tests linked photo ids `"photo-1"` and `"photo-child"` that
were never inserted, and `trip_photo_links.photo_id` carries
`REFERENCES photos(id) ON DELETE CASCADE`.

**Proved pre-existing before touching it.** The suite was re-executed with the *pre-sweep*
pydantic stub reconstructed in memory: identical 4 errors. So the stub sweep did not cause
this — it merely surfaced it, because nobody had run this suite in a broad sweep recently.

Fixed test-only: a `_seed_photo()` helper on `_EditableFixesCase` that inserts a real
`photos` row (`narrator_id` FK to people, `image_path`, UNIQUE `file_hash`) before the two
link calls. **No product code touched.** Now 30 tests, OK.

Side note, not fixed: `_EditableFixesCase` is a base `TestCase` that unittest also collects
directly, so every test in it runs twice under both class names. Cosmetic test-hygiene
noise, pre-existing, left alone.

### 3. `tests/test_trip_draft.py` — not a defect

3 errors under bare system python3: `ModuleNotFoundError: No module named 'fastapi'`. That
suite ships no offline stub and tests real fastapi behaviour, so it correctly requires the
real venv. Deliberately **not** "fixed" by adding a stub — that would convert a suite with
real coverage into one that tests a hand-written mock. Recorded in the audit as a data
point for the authoritative-environment rule.

---

## Test results

**Broad `test_t*.py` sweep — 44 suites, all green after the fix above.** Run per-file
because the device VM caps commands at 45 seconds:

    42 suites OK on first pass
    tests.test_trip_editable_fixes  4 errors -> FIXED -> 30 tests OK
    tests.test_trip_draft           3 errors -> environment, not a defect (needs real fastapi)

Selected counts: `test_travel_doc_lab` 150, `test_travel_doc_evidence_preflight` 86,
`test_trip_interview_context` 72, `test_trip_story_capture` 70, `test_trip_days` 45,
`test_travel_doc_shell_mount` 45, `test_travelogue_builder` 42,
`test_travel_doc_evidence_tools` 41.

**The lane-specific and BUG-LORI guard suites, re-run individually:**

    tests.test_captured_note_review        24 tests   OK
    tests.test_narrator_switcher_handler   11 tests   OK
    tests.test_modal_archive_boundary       5 tests   OK
    tests.test_memoir_trip_story_lane      21 tests   OK
    tests.test_travel_doc_lab             150 tests   OK
    tests.test_trip_location_notes         17 tests   OK

**And as a batch in one process** — the case that used to expose the stub race:

    Ran 228 tests in 14.013s
    OK

**Syntax gates:** `node --check ui/js/travel-doc-lab.js` OK; `node --check` on the
extracted `hornelore1.0.html` inline block OK; `ast.parse` clean on all seven touched
Python files.

---

## One deliberate test change, called out rather than buried

`tests/test_travel_doc_lab.py::test_evidence_tab_is_the_only_one_exempt_from_the_trip_gate`
broke, because Lane 3 legitimately adds a second exempt tab. It was **not** silently
loosened. It was renamed to `test_only_the_review_tabs_are_exempt_from_the_trip_gate` and
rewritten to pin both exemptions **and** prove there is no third:

    exempt = re.findall(r'st\.tab !== "(\w+)"', self.src)
    self.assertEqual(sorted(set(exempt)), ["captured", "evidence"])

The assertion is now stronger than it was, not weaker.

---

## Files changed

**Production (4):**

    server/code/api/services/trip_repository.py   3268 -> 3441   Lane 3 repo layer
    server/code/api/routers/trips.py                   -> 3459   Lane 3 route
    ui/js/travel-doc-lab.js                       6432 -> 6670   Lane 3 Captured Notes tab
    ui/hornelore1.0.html                         10205 -> 10224   Lane 2 guard + window mirrors

**Tests added (2):**

    tests/test_captured_note_review.py             392 lines, 24 tests
    tests/test_narrator_switcher_handler.py        123 lines, 11 tests

**Tests modified (17):** `tests/test_travel_doc_lab.py` (gate assertion rewritten),
`tests/test_trip_editable_fixes.py` (FK seed + stub sweep), and the 15 remaining files of
the stub sweep listed above.

**Docs added (2):**

    docs/reports/VENV_DRIFT_AUDIT_2026-07-27.md
    docs/reports/WO-POST-LORI-CLEANUP-AND-UNBLOCK-01_CLOSEOUT.md

**No flag was added by this work order.** `HORNELORE_TRIPS` (default-OFF) already gates the
trips surface, the memoir trip lane, and now the captured-notes route.

---

## Scope walls — all held

No Google Photos Picker. No Takeout. No archive rewrite. No Lori Review Assistant. No change
to the two-surface rule. No `travel_doc_modal` turn written to the life-story archive. No
DELETE added anywhere. Capture rules unchanged. `torch` not churned. `peft` not installed
into `.venv`. No per-lane work orders opened.

---

## Open items

1. **Restart the API**, then confirm `GET /api/trips/captured-notes` returns 200 and the
   Captured Notes tab paints. The only unproven claim in this package.
2. **Decide the web-stack alignment** (audit section 4.2 / 8). Recommended; not executed.
3. **`lxml` pin vs serving venv** (audit section 5) — one-line call, Chris's.
4. **Shared `tests/_offline_stubs.py`** — the durable fix for the stub race. Out of scope
   here; worth its own small pass.
