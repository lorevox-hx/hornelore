# WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 — Canonical narrator authority

**Opened:** 2026-08-16 · **Revised 2026-08-17 against Chris's supervisor review** ·
**Status: Phase 1 ACCEPTED 2026-08-17. Phase 2 BUILT 2026-08-17, offline gate run, live
acceptance owed.**

*(This header read `Status: Phase 1 built, offline gate run, awaiting the six-step live
acceptance` until 2026-08-17. Phase 1's live acceptance has since run and been accepted —
step 9 with a stated limitation, recorded in §8.1 — and a status line that still calls an
accepted phase "awaiting" is an instruction to re-run it. It also said "six-step"; §8 lists
ten.)*

> **Revision note.** The first cut of this spec proposed guarding the existing whole-document
> projection PUT, adding a nullable `sessions.person_id` backfilled from the memory archive
> alone, and a NEW `/api/narrator/chronology` service. Chris's review of pushed `main` at
> `2c3a593` rejected all three shapes and they were reworked before the gate:
>
> | First cut | Why it was wrong | What replaced it |
> |---|---|---|
> | Guarded whole-document PUT | Replacement erases server-authored keys the writer never saw, however well-guarded | **Field-level mutation** (`PATCH`) with **conflict-aware merge** and a 409 that preserves the newer server record |
> | Backfill from the memory archive only | The strongest recorded link was ignored | **`sessions.conv_id = interview_sessions.id` first**, archive second, durable turn metadata third |
> | Owner collision resolved by keeping A | Keeping A silently is still a silent resolution | **`SessionOwnerConflict` is raised** — the contradiction is the information |
> | New `services/narrator_chronology.py` + route | A second chronology engine | **`/api/chronology-accordion` extended**; the service and its route are **deleted** |
> | Six eras, `today` filtered out | Would have redefined the canonical taxonomy | **Six historical eras PLUS the separate `today` bucket**, in the payload, still never year-derived |
>
> §11 maps every supervisor requirement to where it landed.

**Predecessor:** `WO-LEAN-LORI-*` L2 live acceptance, closed **PARTIAL by product-priority
decision** on 2026-08-16. Evidence: `docs/reports/WO-LEAN-LORI-L2-PARTIAL-2026-08-16.md`
(local-only, gitignored — live narrator data; written as a path, not a link, because a link
would be broken for anyone cloning). **L2 is not resumed by this WO.** Gate B stays OPEN and
Phase 10 stays open; nothing here closes them.

---

## 1. Why this WO exists

L2 was stopped before its case list finished, but it was not wasted: it surfaced three
**integration defects** that no offline test could have found, because each one is a
disagreement between two components that are individually correct.

> **The defect these three share.** In each case the browser holds an opinion about a
> narrator, the server holds a row about the same narrator, and **nothing declares which one
> is the narrator.** Where the two disagree the browser wins by accident — by being the one
> that writes last, or by being the only one that holds the data at all.

| # | Defect, as observed in L2 | Where it bites |
|---|---|---|
| **D1** | Browser projection sync can rewrite a server row **merely because a narrator was loaded**. Christopher's `projection_json` was rewritten on app auto-load. | `interview_projections` |
| **D2** | `sessions` rows carry **no narrator ownership**. `payload_json` is literally `{}` (2 bytes) on every recent row. | `sessions` |
| **D3** | The Life Map spine is **browser-local**. There is no server row to reconcile against. | `lorevox.spine.<pid>` in `localStorage` |

**This WO makes the server the narrator of record for all three.**

### 1.1 What L2 proved, and what it did not

Proved, and therefore not re-litigated here:

- **No family narrator content changed.** Christopher's `projection_json` is byte-identical
  before and after — 12,535 bytes, sha256 `fc6566b52c6351e5c2932376c64156f9`, version 1, in
  both the P4 baseline (2026-08-14T17:43:34) and after the L2 run (2026-08-17T00:38:46). Only
  `updated_at` moved. **The write was a no-op *this* time.** That is a fact about the payload,
  not about the mechanism — the mechanism is unguarded and the next collision need not be
  benign. It was provable only because a P4 baseline happened to survive; there would
  otherwise have been no before-image at all.
- Identity completion promotes `pass1 → pass2a` and writes the spine cache **in the same
  browser**, which is why the spine's authority question is invisible from one tab.
- The auto-load that triggered the projection write came from **`trip_tab_narrator_id_v1`**,
  not from the main `lv_active_person_v55` key. There are several per-surface narrator keys
  and any of them can put a narrator in front of the projection code.

Not proved, and deliberately not assumed:

- **How many historical `sessions` rows can be attributed.** `payload_json` is `{}` on all of
  them. §4.4 forbids inference; the honest answer is expected to be "almost none", and the
  count is reported rather than improved.
- Anything requiring Case C (second browser). Case C was never run. **§5 does not claim it.**

---

## 2. Scope, and the boundary around it

### 2.1 In scope — Phase 1, three commits

1. `fix(projection): make server hydration authoritative on narrator load`
2. `feat(sessions): record explicit narrator ownership`
3. `feat(lifemap): project one server-owned narrator chronology`

### 2.2 Explicitly out of scope

- **Resuming L2.** No L2 case is re-run. No L2 gate is closed.
- **Reactivating runtime safety.** PARKED 2026-08-04; takes Chris's explicit decision and
  never an environment value.
- **Model or context-window change.** LOCKED — a change request there is a stop-and-report
  condition, not a task.
- **Prompt architecture and Lean Lori token work.**
- **Historical rewrite of unattributable rows** (§4.4).
- **Dropping or rebuilding any existing column**, including `sessions.payload_json`. The
  legacy JSON key stays readable forever; it is demoted, not deleted.
- **Travel Document wiring.** Travel Document connects to this authority *after* it works —
  that is Phase 2, and it is not started here.

### 2.3 Doctrine this WO inherits

- Truth order: **current code → current tests and live evidence → accepted reports/ADRs →
  `MASTER_WORK_ORDER_CHECKLIST.md` → old WO status lines → archived design history.**
- `docs/reports/` is gitignored and **nothing under it is ever staged**.
- Focused tests during development; **one** consolidated offline gate per product block.
- No stack start until all three commits and the offline gate are complete.

---

## 3. Commit 1 — `fix(projection): make server hydration authoritative on narrator load`

### 3.1 The defect, precisely

Loading a narrator issues a **PUT before it has ever issued a GET**.

`ui/js/projection-sync.js` `resetForNarrator(newPid)` has three branches. Two of them call
`_persistProjection` *then* `_loadProjection` — upload-then-download:

- same-narrator reset with fields in memory (`newPid === outgoingPid && hasFields`)
- identity-phase carry-over (`!outgoingPid && newPid && hasFields`)

`resetForNarrator` is reached from four load-path triggers, none of which is a save:
`app.js` `loadPerson` , `app.js` `lvxSwitchNarratorSafe`, `narrator-preload.js`, and
`projection-sync.js`'s own `_autoInitOnLoad` IIFE at script-parse time.

The server accepts it unconditionally. `PUT /api/interview/projection` does no freshness
check, and `db.upsert_projection` is `ON CONFLICT(person_id) DO UPDATE SET projection_json =
excluded.projection_json` — a blind, whole-blob, last-writer-wins replace. Anything the server
itself wrote during the turn (`services/projection_writer.apply_correction`) is destroyed by
the next browser PUT.

Two aggravating factors found while mapping this:

- `ProjectionPutRequest.projection` has `default_factory=ProjectionEnvelope`, so **a body that
  omits `projection` validates fine and silently writes an empty envelope over a populated
  row.** `ui/js/bio-builder-core.js` already sends exactly that malformed shape (`fields` at
  the top level instead of inside `projection`). It happens to wipe the row as intended, but
  by accident.
- `version` is taken verbatim from the caller, and the browser hardcodes `1`. The column is
  permanently pinned at 1 and carries **no ordering information** despite existing.

### 3.2 Required behaviour — as reworked

**R1.1 — The load path never writes.** `resetForNarrator` performs **no** projection write on
any branch. A write happens only on (a) an explicit mutation via `projectValue` (debounced),
(b) `forcePersist()` after an applied extraction batch, or (c) switching **away** from a
narrator with in-memory fields. The identity-phase carry-over is preserved in substance:
fields collected before a person existed are adopted under the new pid **in memory** and
reach the server through the ordinary mutation path, after hydration.

**R1.2 — Hydration is unconditional, and a failed request is not an empty server.**
`_sync.hydrated` is a tri-state: `true` only when the server actually answered — *including
when it answered "nothing"* — and `false` while unknown or after a failure. **Writes are
blocked while `false`.** That is what stops a `localStorage` draft repopulating a server that
merely failed to reply, and it is why a confirmed-empty server is allowed to stay empty.

**R1.3 — Writes are FIELD-LEVEL. A whole-document PUT could not be made safe by guarding it.**
The browser's envelope is not a superset of the server's: `projection_writer.apply_correction`
writes into `fields` mid-turn, and replacing the document erases those keys *even when the
replacement is fresh, non-empty and authorised*. New `PATCH /api/interview/projection` carries
only `{mutations, removals}` — the locally dirty paths — and `db.merge_projection_fields`
leaves every key it was not told about alone.

**R1.4 — Concurrency is checked PER PATH, and a conflict is never auto-retried.**
`base_version` proves only that *something* moved, not *what*. Rebasing a dirty path onto a
newer record and retrying is safe when the server touched **different** paths and silently
destructive when it touched the **same** one — the conflict is delayed, not resolved.

So every write carries `base_fields`: the value the caller hydrated for each path it is
writing. A path is **contested** when the stored value differs from that.

- **No contested paths → apply.** A moved `version` alone is not a conflict; the disjoint
  rebase happens **server-side, in one round trip**. The client neither needs nor is offered
  a retry.
- **Any contested path → refuse the whole write.** HTTP **409**, nothing changed (not even
  `updated_at`), and `conflicting_paths` names them. The browser keeps its mutation, keeps it
  dirty, emits `lorevox:projection-conflict`, and **does not retry** — a human decides.

`base_fields` omitted means the caller cannot demonstrate what it edited from; a version
mismatch then contests **every** path, because unprovable is not the same as safe. `GET`
reports `version: 0` for an absent row — `base_version` is unusable while "no row" and
"version 1" are indistinguishable, which they previously were.

**R1.5 — Version is server-owned and monotonic.** An applied write stores
`stored_version + 1`. The caller's `version` is advisory and retained only for wire
compatibility; the browser hardcodes `1`, which is why the column was pinned at 1 forever.

**R1.6 — Rapid narrator switching cancels in-flight work.** A generation token plus an
`AbortController`: switching aborts the hydration `GET`, clears the queued debounced save, and
causes any late write response to be discarded rather than applied to the new narrator.

**R1.7 — The whole-document route cannot erase, and replacement must be authorized.**
Keeping an unrestricted `PUT` beside the field-level `PATCH` would have defeated the `PATCH`:
`allow_empty` guarded only the *empty* case, so a **non-empty but stale** envelope still
erased server-authored keys. `PUT` therefore **merges by default** — keys the body does not
mention survive, and `pendingSuggestions` is treated as mentioned only when non-empty, since
the envelope model cannot distinguish "sent `[]`" from "omitted". True replacement is the
**reset** operation and requires `replace: true` **plus** a `base_version` that still matches;
a replace without a base is 400, a stale one is 409. *Empty* is defined once in
`projection_envelope_is_empty`: `fields` falsy **and** `pendingSuggestions` falsy; `syncLog`
is session-only audit and never counts. `ui/js/bio-builder-core.js`'s deep reset now reads the
current version first and asks for authorized replacement explicitly.

**R1.9 — Unsent edits survive a same-narrator reload.** `_resetSyncState(pid, {keepDirty})`:
a same-narrator reload keeps the dirty set and flushes it *after* hydration; a narrator
**switch** clears it, because those edits belong to someone else. Without this, an unsent edit
would sit visible in `proj.fields`, absent from the server, and never queue again.

**R1.8 — Nothing is destroyed.** No column dropped, no row deleted, no migration.

### 3.3 Acceptance — offline

- Loading a narrator issues zero projection writes (source scan).
- A field-level merge leaves a server-authored key the writer never saw **intact**.
- A stale `base_version` returns 409, writes nothing, and hands back the newer record.
- An empty PUT over a populated row leaves `projection_json` **byte-identical**; the same PUT
  with `allow_empty: true` wipes.
- `version` increments on every applied write and never on a refusal.
- An absent row reports `version: 0`, a once-written row reports `1`.

---

## 4. Commit 2 — `feat(sessions): record explicit narrator ownership`

### 4.1 The defect, precisely

`sessions` is `(conv_id PK, title, updated_at, payload_json)`. It has **no `person_id`**, no
index beyond the PK autoindex, and no FK to `people`.

`ensure_session(conv_id, title)` — the only writer that fires on the live WebSocket path —
**hardcodes `payload_json = "{}"`** and has no `person_id` parameter. Its signature cannot
express ownership even if a caller wanted to. `persist_turn_transaction` calls it and likewise
takes no person. All six `chat_ws.py` persist sites therefore drop the id.

The id is unquestionably in hand: `chat_ws.py` binds `person_id` at the top of every turn and
passes it to `archive_ensure_session` and to `ensure_interview_session` — **writing the
narrator into a sibling table for the very same `conv_id`** while the `sessions` row gets `{}`.
`routers/memory_archive.py` `session_start` is sharper still: it validates `person_id`, then
calls `ensure_session(conv_id, title=...)` and drops it, under a docstring explaining that the
call exists so the archive "isn't orphaned from the DB side."

Two consequences, both live today:

- `get_narrator_state_snapshot`'s `user_turn_count` joins `turns → sessions` on
  `json_extract(payload_json, '$.active_person_id')`. Every row is `{}`, so **the count is
  structurally always 0**, and the UI — which gates the "welcome back" resume prompt on it —
  treats every returning narrator as brand new.
- The one path that *can* write a payload (`/api/session/put`, from `app.js`) writes the key
  **`person_id`**, while the only reader reads **`$.active_person_id`**. Even on the rare
  occasions ownership is written, the key does not match.

### 4.2 Required behaviour — as reworked

**R2.1 — A real column and index.** Migration `0044_sessions_person_id.sql` adds
`sessions.person_id TEXT` (nullable) and `idx_sessions_person_updated ON sessions(person_id,
updated_at)`.

**R2.2 — BOTH session systems are reconciled, and the backfill runs in proof order.**
Three passes, each filling only rows still NULL so a weaker source never overrides a stronger
one, and each guarded by `COUNT(DISTINCT ...) = 1`:

1. **`sessions.conv_id = interview_sessions.id`** — the strongest link. `chat_ws` calls
   `ensure_interview_session(conv_id, person_id)` for the *same conv_id* whose `sessions` row
   it leaves ownerless. The narrator was already being written down, one table over, under
   the identical key.
2. `memory_archive_sessions(person_id, conv_id)` — an explicit recorded pair.
3. `turns.meta_json -> '$.person_id'` — durable per-turn metadata where a writer recorded it.

Where a source knows two narrators for one conv_id we **decline**. Nothing is attributed by
timestamp adjacency, by "the only narrator active that day", by archive-directory proximity,
or by anything read out of narrator prose.

**R2.3 — Every creation path carries the id.** `ensure_session`, `upsert_session`,
`add_turn`, `persist_turn_transaction`, all six `chat_ws` persist sites, REST `/api/chat`,
the streaming variant, `/api/session/new`, `/api/session/put`, and
`memory-archive/session/start` — which validated `person_id` and then dropped it, under a
docstring explaining the call existed so the archive would not be orphaned.

**R2.4 — A collision FAILS.** A NULL incoming id never clears an existing owner
(`COALESCE`), and a *different* incoming id raises `SessionOwnerConflict` — surfaced as
**HTTP 409** on `/api/session/put` and on archive session start. Quietly keeping A would also
have been a silent resolution of a contradiction, and **the contradiction is the
information**: a conversation does not change narrators.

**R2.5 — Reads, lists, exports and deletes use the field.** `user_turn_count` resolves the
column, then `$.active_person_id`, then `$.person_id` — the last of which is what `app.js`
has always written while the reader looked for the first. `list_sessions` accepts a
`person_id` filter; `/api/sessions/list` exposes it. `person_delete_inventory` counts
sessions.

**R2.6 — FK policy, enforced where deletion happens.** No SQLite foreign key: adding one
requires the two-phase table rebuild of `0034_trips_person_id_fk.sql`, and `sessions` is the
parent of the entire chat corpus. The behaviour a cascade would have given is implemented at
the delete path instead, where it is testable — `sessions` joins
`_EXTENDED_PERSON_SCOPED_TABLES`, so `hard_delete_person` removes a narrator's owned sessions
and `turns` follows through its **existing** `ON DELETE CASCADE` off `sessions(conv_id)`.
Unowned rows are **not** swept up, because sweeping them would mean guessing;
`db.session_ownership_residue()` reports them as numbers instead.

**R2.7 — Nothing is destroyed.** `payload_json` is untouched and stays readable forever.

### 4.3 Deliberate scope limit — turns are not touched

`turns` has no `person_id`. Adding one is a second migration with its own backfill question
and is **not** in this commit. Attribution runs `turns → sessions.person_id` via `conv_id`;
that join already exists, and the delete cascade already runs along it.

### 4.4 The honesty rule on backfill

> **No historical row is attributed by inference.**

Only the three recorded links in R2.2 are used. Everything else stays `NULL` and
`db.count_sessions_without_owner()` / `db.session_ownership_residue()` report the remainder
**as numbers**, in the commit body and in §7. Expect those numbers to be large. That is the
correct outcome, not a shortfall to be improved by cleverness.

---

## 5. Commit 3 — `feat(lifemap): project one server-owned narrator chronology`

### 5.1 The defect, precisely

The Life Map's periods exist **only** in the browser. `app.js` `initTimelineSpine()` computes
them client-side from `basics.dob` + `basics.pob` against `TIMELINE_ORDER`/`ERA_AGE_MAP`, and
`state.js` `saveSpineLocal()` writes them to `localStorage` under `lorevox.spine.<person_id>`.
`loadPerson` rehydrates from that key. `ui/js/life-map.js` never fetches anything — it is a
pure reader of `state.timeline.spine`.

**There is no server row to reconcile against.** No `eras` table exists in any of the 43
migrations. The two server-side analogues are both computed-on-read and neither returns a
spine: `derive_life_spine` is a pure function of `dob` with no `person_id` and no DB access,
reachable only through `GET /api/chronology-accordion`, whose own `periods` are the
age-scaffold bands and not spine output. `GET /api/narrator/state-snapshot` carries no
chronology at all.

Clear the browser and the narrator's chronology is gone until a profile save recomputes it.
Unlike D1 — where a server row existed and was being clobbered — here **there is nothing to
clobber, which is worse.**

The backend era mirror already anticipated this. `server/code/api/lv_eras.py` says so in its
own docstring: *"Phase 2 may promote backend to canonical (with an endpoint and frontend
fetch) if server-side era reasoning grows beyond what this mirror supports."* This commit is
that promotion.

### 5.2 Required behaviour — as reworked

**R3.1 — THERE IS EXACTLY ONE CHRONOLOGY ENGINE, and it is the one that already existed.**
`/api/chronology-accordion` is extended; `server/code/api/services/narrator_chronology.py`
and the `/api/narrator/chronology` route proposed in the first cut are **deleted**, and a
test asserts the file does not exist. Building a second projection beside the one that
already merges profile identity, promoted truth, derived spine events, trips and historical
context would have recreated, on the server, exactly the two-sources-of-truth problem this
lane exists to end.

**R3.2 — The canonical taxonomy is NOT redefined.** `periods` carries **six historical eras
PLUS the separate `today` current-life bucket** — seven entries. `today` is present in the
contract, flagged `is_current_life: true` with `start_year: null`, and **still never produced
by birth-year arithmetic**: `year_to_era` skips it, matching `era_id_from_age`, which has
never returned it. Travels remains a special shelf and is flagged `shelf: "travels"` rather
than folded into the era taxonomy.

**R3.3 — Periods are Life-Map-shaped.** Each carries `era_id`, `label` (the era_id, per
WO-CANONICAL-LIFE-SPINE-01 Step 3d), `start_year`, `end_year`, `is_approximate`,
`is_current_life`, `places`, `people`, `notes`, `source`, `status` — so a renderer consumes
this directly instead of deriving its own spine.

**R3.4 — Three lanes the Life Map needed and the payload did not carry:**

- `timeline_events` — **confirmed** events, with `status` read from the column rather than
  assumed, and undateable rows dropped rather than guessed at.
- `story_evidence` — captured stories with an explicit **approved / provisional** status
  mapped from `review_status`, plus a `placement` of `stated` vs **`derived`**, because
  "they told us" and "we worked it out from a date of birth" are different claims and
  collapsing them overstates the second. Discarded stories are excluded.
- `trip_days` — trip **days**, each with its own date and place, not one row per trip. A trip
  rendered as a single heading loses precisely what the narrator remembers.

**R3.5 — Truthful source/status metadata.** A `sources` block declares, per lane, where it
came from and whether it was read at all — so a consumer can tell "this narrator has none"
from "this lane could not be read", which is the distinction a renderer must make before it
draws an empty column as though it were an answer. Every lane fails soft: a missing table on
an older database is not a defect, but it is never silent.

**R3.6 — No DOB is a state, not an error.** `seed_ready: false`, `reason: "no_dob"`, and
`today` is **still returned** — current life does not depend on a birth year. The browser
therefore tests the *derived* eras, not `periods.length`, before claiming readiness.

**R3.7 — One shared era-selection and prompt dispatcher.** `window.LorevoxEraDispatch` with
`selectEra()` and `dispatchEraPrompt()`. The selection sequence was copy-pasted at four sites
in `life-map.js` alone, each slightly different — four chances for two renderers to disagree
about what selecting an era means. All four route through the dispatcher now; `today` does
not promote the pass engine; identical era prompts inside 1.5 s are suppressed, so a
double-click no longer asks Lori twice.

**R3.8 — Cancellation and rapid-click dedup.** `AbortController` cancels the in-flight
chronology request on narrator switch, a single in-flight promise per pid deduplicates rapid
clicks, and a response whose generation token or `person_id` no longer matches is discarded.

**R3.9 — Read-only, and nothing is destroyed.** The route writes no facts, timeline,
questionnaire, archive or table — asserted by a byte-comparison of the database file across
repeated reads. `lorevox.spine.<pid>` survives as a paint cache; `initTimelineSpine()` remains
for the offline/first-save path.

## 6. Testing

### 6.1 Rules

- **`pytest` is not installed.** `unittest` only, per module, in separate processes. Never
  whole-tree discovery — it cross-contaminates through `api.db.DB_PATH`.
- Fresh temp SQLite per test, `_db.DB_PATH` monkeypatched, `_db.init_db()` to apply all
  migrations, restored and unlinked in `tearDown` — the established house fixture.
- Router tests mount a bare `FastAPI()` with only the router under test.
- In the agent sandbox, redirect bytecode off the `/mnt/c` mount: `PYTHONPYCACHEPREFIX=/tmp/pyc`.

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest tests.<module>
```

### 6.2 New test modules

| Module | Covers |
|---|---|
| `tests/test_projection_server_authority.py` | R1.3–R1.5 at the `db` layer and through `PUT`/`GET`; byte-identity of a protected row; `allow_empty` wipe; version monotonicity |
| `tests/test_projection_load_no_write.py` | R1.1–R1.2, R1.5 — source scan of `ui/js/projection-sync.js` and `ui/js/bio-builder-core.js` via `tests.source_scan_helpers.strip_js_comments`, so prose in a comment cannot satisfy or trip the guard |
| `tests/test_sessions_narrator_ownership.py` | R2.1–R2.6 — migration applied, column + index present, `COALESCE` semantics (never cleared, never overwritten), `user_turn_count` through the column and through both legacy JSON keys |
| `tests/test_narrator_chronology_projection.py` | R3.1–R3.9 — exactly one engine (the deleted service is asserted absent); period boundaries against `LV_ERAS`; **`today` is PRESENT in `periods` and `year_to_era()` never derives it** (two separate assertions — it is *in* the taxonomy and *out* of the arithmetic); the three new lanes and their status metadata; no-DOB as a state; missing person 404; and a write-free assertion by byte-comparing the database file |

Mutation-style coverage is required where a guard, a transaction boundary or an
error-truthfulness claim exists — R1.3, R2.4 — and not for ordinary field plumbing.

### 6.3 Consolidated offline gate

One run, stack **down**, after all three commits: the four new modules plus the existing
modules that touch the changed surfaces. Recorded as a single pass/fail with counts.

---

## 7. Known gaps carried forward — not silently absorbed

1. **No SQLite FK on `sessions.person_id`** (R2.6). The deletion *policy* is enforced at the
   delete path and tested there, but the constraint itself would need a table rebuild of the
   chat corpus's parent. **Separately authorized.**
2. **Unattributable historical rows.** After the three-pass recorded-link backfill, whatever
   remains stays `NULL` and is reported by `session_ownership_residue()` — never reduced by
   inference (§4.4).
3. **`turns` has no `person_id`** (§4.3). Attribution goes through the `conv_id` join.
4. **The export verifier's contract is still wrong.** L2 finding 9: it matches replies to
   turns *by text*, so two legitimate identical deterministic replies read as a duplicate
   write. **Not fixed here** — it is test-harness machinery, and folding it into a product
   commit would muddy the evidence. Logged for the next L2 iteration.
5. **Per-surface narrator keys remain unreconciled.** `trip_tab_narrator_id_v1`,
   `ma_narrator_id_v1`, `pi_narrator_id_v1` (shared by Photo Intake and Photo Timeline) still
   select narrators independently of `lv_active_person_v55`. Commit 1 removes the *damage* an
   auto-load can do; it does not unify the keys. Phase 2.
6. **`tests/test_lori_witness_mode` carries seven known expectation failures** — four still
   demand three-anchor cascade output against the newer two-anchor cap, three expect the
   retired broad correction behaviour. **Pre-existing, verified against a clean checkout of
   `2c3a593`, and deliberately not "fixed" here**: they are Witness-lane reconciliation, and
   changing them from inside the authority lane would disguise a behaviour decision as a
   test tidy-up.
7. **Gate B and Phase 10 stay open.** Nothing in this WO closes an L2 gate.
8. **`prompt_composer.compose_system_prompt` still calls `ensure_session` without a narrator**
   — it has no `person_id` parameter. It records NULL, which `COALESCE` never lets clear an
   existing owner, so it is safe but not yet contributing. Threading it through is a
   signature change across the composer and belongs with Phase 2.

---

## 8. Live acceptance — after the offline gate

**The stack is not started until the code and the offline gate are complete.** Then, one
start. Each step names the delivered claim it exercises; a restart is optional persistence
confirmation and **does not replace** the era-dispatch and narrator-switch checks.

1. **No projection write on load.** Load a narrator with the network panel open. Zero
   `PUT` and zero `PATCH` on `/api/interview/projection`. `GET` fires and hydrates. *(R1.1)*
2. **Byte-identical projection after a load alone.** Read `projection_json` and `updated_at`
   before and after. Unchanged — this time as a *guarantee*, not the lucky payload L2 had to
   reconstruct forensically. *(R1.1/R1.2)*
3. **A same-path conflict does not auto-resolve.** With the narrator loaded, change a field
   server-side (a correction turn), then edit the same field in the browser. The flush returns
   **409**, `conflicting_paths` names that path, the **server value survives**, and the browser
   does **not** retry. *(R1.3/R1.4)*
4. **A disjoint edit still lands.** Repeat with the browser editing a *different* path. It
   applies in one round trip with no 409 and the server's own key survives. *(R1.4)*
5. **Owned live session.** Send one turn. The new `sessions` row carries `person_id`, and it
   equals `interview_sessions.person_id` for the same `conv_id`. *(R2.3)*
6. **`user_turn_count` is non-zero** on re-opening the narrator — the resume-prompt gate that
   has been structurally stuck at 0. *(R2.5)*
7. **Life Map survives clearing its cache.** Delete `lorevox.spine.<pid>` from `localStorage`
   and reload. **`GET /api/chronology-accordion?person_id=…`** returns the projection and the
   Life Map renders from it, including the `today` bucket. *(R3.1/R3.2/R3.6)*
8. **One era selection produces exactly ONE prompt.** Click a life period once, then
   double-click another. One system prompt each — the second click of the pair is suppressed.
   *(R3.7)*
9. **Rapid A→B narrator switching leaves nothing of A behind.** Switch A→B quickly. No
   delayed hydration of A lands on B, no queued A write is flushed, and the chronology request
   for A is aborted rather than raced. *(R1.6/R3.8)*
10. **Optional: restart and re-check 2 and 5.** Persistence confirmation only.

**Test narrator:** `6ad678ee-b295-49de-8578-da00200848ba` ("L2 ACCEPTANCE DELME 2026-08-16")
— live, testing-only, identity-complete, `pass2a`, with a spine cache. **No new narrator is
needed, and no family narrator is touched.**

---

## 9. Governing documents

- `HANDOFF.md` — orientation; outranks this file's status line.
- `MASTER_WORK_ORDER_CHECKLIST.md` row 8.
- `docs/reports/WO-LEAN-LORI-L2-PARTIAL-2026-08-16.md` — local-only, gitignored.
- `CLAUDE.md` — environment, test commands, the `__pycache__` and `.git/index.lock` hazards.

---

## 10. The sequence this WO sits in

Established with Chris on 2026-08-17. Phase 1 is the foundation the other three stand on;
none of them is started here.

| Phase | Work | State |
|---|---|---|
| **1** | **Canonical narrator authority — the three commits in this document** | **ACCEPTED 2026-08-17.** Step 9 accepted with its synthetic-B limitation (§8.1). |
| **2** | **Travel Document connection, surface narrator context, legacy session-owner backfill — §12** | **BUILT 2026-08-17; offline gate run; focused live acceptance owed (§12.6).** |
| 3 | Witness/story connection — captured stories enter that authority with truthful provisional/approved status | **NOT OPENED.** |
| 4 | Unified projection/output verification — Life Map, Chronology, Lori grounding, Travel Document and memoir agree, with no browser ownership anywhere | Not started |

## 11. Supervisor requirements — where each one landed

**Projection authority**

| Requirement | Where |
|---|---|
| Server read on load, no automatic PUT | R1.1 · `projection-sync.js resetForNarrator` |
| Server projection outranks browser cache | R1.2 · `_loadProjectionFromBackend` assigns unconditionally |
| localStorage is display fallback only; cannot silently repopulate an empty server | R1.2 · `_sync.hydrated` gates every write |
| Writes follow explicit mutation, not load/reset/switch | R1.1 · only `projectValue` marks dirty |
| **Field-level mutation or conflict-aware merging, not a timestamp check around the same unsafe replacement** | R1.3 · `PATCH` + `db.merge_projection_fields` |
| Stale writes return a clear conflict and preserve the newer server record | R1.4 · HTTP 409 with the server record in the body |
| Rapid switching cancels pending loads and saves | R1.6 · generation token + `AbortController` |
| Identity-creation path preserves new fields without "save on load" | R1.1 · `keepLocalFields` merge after hydration |
| Failed request ≠ confirmed-empty server | R1.2 · tri-state `hydrated`; the `catch` never sets it true |

**Session ownership**

| Requirement | Where |
|---|---|
| Reconcile both session systems | R2.2 pass 1 · `sessions.conv_id = interview_sessions.id` |
| Archive records and durable turn metadata as additional proof | R2.2 passes 2 and 3 |
| Ambiguous rows stay null; never inferred from prose | R2.2 · `COUNT(DISTINCT ...) = 1` guard on every pass |
| Every creation path updated | R2.3 · incl. `add_turn` and archive session start |
| Owner collision must FAIL, not silently replace | R2.4 · `SessionOwnerConflict` → 409 |
| List/read/export/delete inventory and hard-delete residue use the field | R2.5, R2.6 · `session_ownership_residue()` |
| Index and an FK policy consistent with narrator deletion | R2.1, R2.6 · policy enforced at the delete path and tested |

**Life Map and chronology**

| Requirement | Where |
|---|---|
| Do not create a second chronology engine; extend the accordion | R3.1 · the standalone service is deleted, and a test asserts it |
| Confirmed timeline events | R3.4 |
| Story evidence with approved/provisional/derived status | R3.4 · `status` + `placement` |
| Trip days, not merely a trip heading | R3.4 |
| Truthful source/status metadata | R3.5 · the `sources` block |
| One shared era-selection and prompt dispatcher | R3.7 · `window.LorevoxEraDispatch` |
| Request cancellation on narrator switch | R3.8 |
| Rapid-click deduplication | R3.8 (requests) and R3.7 (prompts) |
| **Canonical six historical eras PLUS the separate Today bucket; Travels is a special shelf** | R3.2 · `today` is in the payload and still never year-derived |

---

## 8.1 Phase 1 live acceptance — accepted 2026-08-17

Phase 1 ran its live acceptance and is **ACCEPTED**. Test narrator
`6ad678ee-b295-49de-8578-da00200848ba` ("L2 ACCEPTANCE DELME 2026-08-16"); no family
narrator was touched.

**Step 9 is accepted with a stated limitation, not silently.** The rapid A→B narrator
switch was exercised against a **synthetic narrator B**. What that proves is the
mechanism — a delayed hydration for A does not land on B, no queued A write is flushed,
and A's chronology request is aborted rather than raced. What it does not prove is the
same behaviour against a second narrator carrying a full live history, because no such
second narrator exists outside the family set and the family set is not available for
acceptance runs. The limitation is recorded here rather than in a report, because a
limitation that lives only in a local file is a limitation the next reader will not find.

**L2 remains PARTIAL and Gate B remains OPEN.** Phase 1's acceptance closes no L2 gate
and re-runs no L2 case. The deferred L2 cases — Case C, the remaining Case A branches,
five styles, trip/photo fixtures, the refusal matrix, Case E rows 2 and 4, and the final
restart with Case F — stay **deferred by product-priority decision, not by failure**.

---

## 12. Phase 2 — the contract

**Built 2026-08-17.** One integrated code commit and one governing-document commit. The
outcome: Travel Document connects to the accepted chronology authority, narrator selection
is reconciled across shell-launched surfaces, and the legacy session-owner migration is
completed safely.

### 12.1 The authority boundaries, unchanged

| Responsibility | Authority |
|---|---|
| Detailed trip/day editing | `trip_days` and `/api/trips/{trip_id}/days` |
| Person-wide chronology projection | `/api/chronology-accordion` |
| Narrator navigation | Life Map and Chronology Accordion |
| Travel memoir output | the visible editable Travel Document timeline, projected to DOCX |

**These are CONNECTED, not merged.** The chronology projection carries one row per day with
a date, an index, a label, a main location and a lodging base. Adopting it as the editor's
model would silently destroy conversations, photo placements, notes, sources and approvals —
everything the detailed model exists to hold. Replacing the projection with the detailed
model would rebuild the second chronology engine Phase 1 deleted.

### 12.2 Part A — Travel Document ↔ canonical chronology

- The mounted workspace loads `GET /api/chronology-accordion?person_id=<mounted narrator>`
  **through `travel-doc-lab.js`'s existing `api()` choke point**. No competing raw fetch, no
  new chronology engine. The file still contains exactly one `fetch(`.
- Responses are discarded when the **generation token** has moved, when the mount has been
  rebound to another narrator, or when the payload's own `person_id` does not match. Both
  the resolve arm and the reject arm carry the generation guard.
- The projection loads **alongside** the detailed selected-trip bundle, as a ninth parallel
  request, and cannot take the workspace down: an outage keeps the previous payload and
  flags it stale rather than blanking it.
- **Reconciliation is by stable day id**, not by index and not by date. A re-dated or
  re-ordered day would otherwise read as "every day changed". Compared: trip id, day id,
  day index, date, year, projected label, main location, lodging base.
- A day the projection legitimately dropped because it has **no date** is reported as a
  note, not as a disagreement. A day the projection **has and the workspace does not** is a
  disagreement, because it means the two are looking at different trips.
- An **operator-only connection panel** shows: canonical day count for the selected trip;
  overlapping historical period; the Travels **shelf** named as a shelf; confirmed
  timeline-event count for those years; approved and provisional story-evidence counts;
  per-lane provenance and status; and an honest unavailable/stale warning.
- **Today appears only when the trip is explicitly current** — the operator marked it live,
  or it carries a real year that is this year or later. **It is never derived from a missing
  year.**
- **Travels remains a special shelf and does not become a seventh historical era.**
- After a **chronology-bearing** write — trip create, trip edit, day generation, day
  reconcile, day save, day drop, trip delete — the canonical projection is refreshed. **Only
  after a successful refresh** is the shell notified, with
  `window.dispatchEvent(new CustomEvent("lorevox:chronology-refreshed", {detail:{person_id, reason}}))`.
  Photo-only writes do not refresh: they change no chronology-bearing field.
- If the detailed write succeeds and the refresh fails or disagrees, **the trip edit is
  preserved** and a truthful synchronisation warning is shown. It opens with the fact that
  the change was saved, because that is the operator's first question. It does not claim the
  Life Map was updated.
- The shell handler `lvRefreshNarratorChronology` **accepts the event only for its active
  narrator**, deduplicates concurrent refreshes with one trailing re-run, repaints both Life
  Map renderers (`window.LorevoxLifeMap.render` and `window.crInitAccordion`), **sends no
  prompt** and **writes no projection**.
- **Before preview or DOCX export** one shared gate runs: refuse while the day form is
  dirty, reload the detailed trip/day state, refresh and reconcile the chronology,
  invalidate any stale lazy preview. The binding rule is unchanged —
  **visible editable Travel Document timeline → DOCX** — and exactly-once day rendering
  remains the server projection's decision, not a client-side filter.

**The authority-reporting defect fixed inside this block.** `_sources_block` promised to
distinguish "this narrator has none" from "this lane could not be read" and could not: the
three collectors swallowed every exception into `return []` while the block hardcoded
`"status": "read"`, so a missing table and an empty narrator produced the identical
`{"status": "read", "count": 0}`. Collectors now return a `_LaneResult(items, status)` and
the block reports `read` / `unavailable` / `not_attempted` from the lane itself. Failing
soft is still right; failing soft **silently** is what changed.

### 12.3 Part B — one narrator-context contract

`ui/js/narrator-context.js`, shared by the shell and by every narrator-scoped standalone
surface.

- The shell authority stays `state.person_id` + `lv_active_person_v55`.
- Shell launches append `?narrator_id=<person_id>`. One launcher, `lvOpenNarratorTool`,
  replaces nine scattered `window.open` calls — **four of which passed no narrator at all**,
  so whether a tool inherited the shell's selection depended on which button was pressed.
- **An explicit query narrator is the initial handoff authority and is validated against
  `/api/people` before it is selected.**
- **An invalid explicit id FAILS CLOSED.** No narrator is selected, and it must never fall
  through to a legacy cache: "the id you asked for is wrong, so here is a different
  narrator's library" is the worst available answer, and Photo Intake stamps every upload
  with the narrator it believes in.
- A direct standalone load with **no** query parameter may use its legacy key, after the
  same validation. A stale cached id is dropped rather than honoured.
- A narrator chosen inside a standalone surface updates **that surface's** cache and never
  `lv_active_person_v55`. Enforced structurally: `remember()` refuses the shell key and says
  so; `readCache()` refuses it too, so no surface can inherit the shell's selection
  ambiently.
- Cross-page links carry the validated narrator: Photo Timeline → Photo Intake, Trip Tab →
  Photo Intake, and the existing Photo Elicit links.
- **Legacy keys are demoted to fallback caches, not deleted**, and every standalone picker
  is preserved.
- **Travel Document embedded in the shell keeps taking its narrator from `opts` only.** It
  acquires no selector authority of its own and does not load the helper.
- **Kawa / Memory River was not extended.** It remains reachable frozen legacy UI awaiting
  separate adjudication.

### 12.4 Part C — legacy session-owner backfill

`server/code/db/migrations/0045_sessions_legacy_payload_owner.sql`. **0044 is not edited.**

Reads exactly two structured fields — `payload_json.person_id` and
`payload_json.active_person_id` — and assigns ownership only when all five conditions hold:
the row has no explicit owner; the payload is valid JSON; exactly one id is established and
both fields agree where both are present; the person exists in `people`; and no stronger
recorded link contradicts it or is itself ambiguous.

`payload_json` is **never rewritten**. An existing explicit owner is **never overwritten**.
Ambiguous and conflicting rows **stay NULL**. Nothing is inferred from prose, names,
timestamps, proximity or UI history. The migration is idempotent.

**Provenance is recorded by the producer**, per the rule this repository earned in
`WO-SYSTEM-DIRECTIVE-PERSISTENCE-01`: a new nullable `sessions.person_id_source` is stamped
`legacy_payload_json` on exactly the rows 0045 fills, and `explicit` by the live write path.
Rows 0044 recovered are **not** retro-stamped — deciding after the fact which they were is
the reconstruction that rule forbids — and are reported honestly as
`owner_source_unrecorded`.

`session_ownership_residue()` now distinguishes explicit owners, rows recovered from legacy
payload, owners whose provenance predates the column, and four mutually exclusive reasons a
row was declined: disagreeing fields, an invalid legacy id, an ambiguous or conflicting
stronger source, and no recorded link at all. The four sum to the unowned total.

**One legacy-read defect fixed in the same part, because Part C owns the legacy session
reads.** `list_sessions`' narrator filter read the two legacy payload keys with a bare
`json_extract`. In SQLite that does not yield NULL on malformed JSON — it raises
`OperationalError: malformed JSON`, and it raises for the whole statement, so a **single**
junk historical row would return HTTP 500 from
`GET /api/sessions/list?person_id=…` for **every** narrator. `payload_json` is precisely the
column where junk is plausible: browser-supplied state persisted verbatim for the life of the
table. Migration 0045 and `session_ownership_residue()` both guard it for that reason; until
this change `list_sessions` was the one reader that did not, and therefore the one that could
take the endpoint down.

Both legacy expressions are now wrapped in `CASE WHEN json_valid(payload_json)`. An
unparseable row is **not attributable by the legacy fallback** — skipped, never guessed at —
and it stays visible in the unfiltered listing, because unattributable is not invisible.

Found while reviewing the four-persona harness landed in `425a2d2`, which reads that endpoint
in **both** its `product-read` and `completed-turn` scenarios. That is what turned a latent
fragility into a path something exercises routinely; the defect itself predates both lanes.
Six regression tests, driving the real route rather than the function — "does not return HTTP
500" is a claim about the route and a direct call could not prove it. The mutation that
restores the unguarded form is killed by five of them.

### 12.5 Offline gate — 2026-08-17

Focused suites during development, then one consolidated run. New modules:
`tests/test_travel_doc_chronology_integration.py` (33),
`tests/test_surface_narrator_context.py` (22),
`tests/test_sessions_legacy_payload_owner.py` (34), plus new lane-status cases in
`tests/test_narrator_chronology_projection.py` (54 total). Two behaviour harnesses execute
the **shipped** code rather than a copy of its logic:
`scripts/ui/run_chronology_connection_behaviour.js` (28) and
`scripts/ui/run_narrator_context_behaviour.js` (23).

**Seven mutants were injected and all seven killed**, and the first run of that exercise
found **three tests weaker than their names claimed** — a generation guard asserted once
where two arms needed it, a narrator check satisfied by a second occurrence elsewhere in the
function, and an export gate proved only in the negative, so a gate that refused everything
would have passed. All three were strengthened rather than accepted.

Two existing assertions were **narrowed in place, not deleted**: the Travel Doc endpoint
allow-list gains `/api/chronology-accordion` as a seventh sanctioned prefix, and the export
test re-points at `_exportTravelDocumentNow` now that `_exportTravelDocument` is the gate.

### 12.6 Live acceptance owed — focused, not another campaign

After review and push, one stack start, non-family narrator `6ad678ee`:

1. its provable legacy session receives explicit ownership after migration;
2. create trip `PHASE2 ACCEPTANCE DELME` with two days;
3. Travel Document shows the chronology connection and the Travels shelf status;
4. edit one day; detailed day, chronology endpoint and Life Map agree;
5. export once; both days appear exactly once with current values;
6. Trip Tab, Photo Intake, Photo Timeline and Media Archive launched from the shell all
   receive the same test narrator;
7. an invalid explicit narrator id does not fall back to another surface's cached narrator;
8. delete only that trip and this acceptance's artifacts, then verify residue and counts.

**No family narrator. No restart unless a real persistence question appears. The L2 matrix
is not resumed.**
