# HANDOFF -- moving Hornelore agent work from the cloud sandbox to local

Written 2026-07-26, at the close of
WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 5.

Read this file **and** `CLAUDE.md` before touching anything. `CLAUDE.md` is
the standing contract; this file is the transition note plus the state of
the work in flight.

---

## 1. Where the work stands right now

**WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 is COMPLETE.** Phases 0, 1,
1.1, 2, 3, 4 and 5 are all done. Phase 5 -- the live smoke against the
serving stack -- is **green at 66 assertions, 66 pass**.

Report: `docs/reports/phase5_import_provenance_smoke.console.txt`

Two commits were pending at handoff time. Check `git log --oneline -5`:

* **Code commit** -- `server/code/api/routers/import_provenance.py`,
  `tests/test_import_provenance_routes.py`, `.env.example`.
  Subject: `fix(import-provenance): gate every route on
  HORNELORE_IMPORT_PROVENANCE via a router dependency`
* **Docs commit** -- `docs/reports/phase5_import_provenance_smoke.console.txt`,
  `docs/wo/WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01_Spec.md`,
  `MASTER_WORK_ORDER_CHECKLIST.md`, `CLAUDE.md`.
  Subject: `docs: WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 5
  close-out, live smoke green`

If those two are not in the log, they still need to run. **This handoff file
is a third, separate commit.**

**The next work order is WO-2, the Evidence Review Queue. It is a separate
session and must not be started as a continuation of Phase 5.**

---

## 2. What actually changes when Claude runs locally

A lot of the ceremony in the recent transcripts was sandbox plumbing, not
process. Retire it:

| Sandbox behaviour | Why it existed | Local |
| --- | --- | --- |
| gzip + base64 + heredoc paste blocks to move files | the agent had no path to the disk | **gone** -- edit files in place |
| md5-verify a staged copy before editing | the agent's copy could drift from the real file | **gone** -- it reads the real file |
| md5-gated patch scripts | same | **gone** |
| batching a whole smoke into one JS payload | Chrome throttles backgrounded tabs 75-120s | **gone** -- use `curl` from the shell |
| `javascript_tool` field-slicing to dodge `[BLOCKED: Cookie/query string data]` | browser tool payload filter | **gone** |
| the remote-devices file bridge | cloud-only | **gone** |

**These are NOT sandbox artefacts and they stay verbatim:**

* **Git.** Chris commits from the WSL command line and pushes from GitHub
  Desktop. The agent produces copy-paste `git add` + `git commit` blocks run
  from `/mnt/c/Users/chris/hornelore`. Stage **specific file paths only** --
  never `git add -A` or `git add .`. One `git add` + `git commit` pair per
  logical commit. `-m` subject, second `-m` for the body. **Never include
  `git push`.** Never suggest SSH key swaps, `gh auth setup-git`, or PAT
  entry -- auth is wired through GitHub Desktop and is not the agent's
  business. Work directly on `main`; do **not** create feature branches.
  *Being able to run git is not permission to run git.*
* **Long multi-line `-m` bodies get mangled by his terminal paste. Use
  single-line `-m` bodies.**
* **Stack ownership.** Chris starts and stops the API and the full stack
  himself. Do **not** put `./scripts/start_all.sh` or `./scripts/stop_all.sh`
  in a copy-paste block.
* **Chris runs all destructive DB operations himself.** The agent never
  writes to `C:\hornelore_data`.
* **A phase is a scope wall.** Do not do the next phase in the same session.

---

## 3. Environment facts that will bite a fresh agent

**Two virtualenvs, and they are not interchangeable.**

* `.venv` -- fastapi 0.136.1 / starlette 1.0.0. **This is what the tests run
  under.**
* `.venv-gpu` -- fastapi 0.135.1 / starlette 0.52.1. **This is what actually
  serves.**

Test command is `.venv/bin/python -m unittest tests.<module>`. Aligning the
two belongs to a future harness/environment work order, not to feature work.
Phase 5 handled this by verifying against the serving version directly.

* **pytest is NOT installed.** `python3 -m unittest discover -s tests` is not
  a usable gate -- it suffers cross-module contamination. Run modules
  individually.
* **Test baseline 399:** migration 37, routes 67, repository 53, FK migration
  11, person delete 3, api_smoke 31 (skipped), db_smoke 14 (skipped).
* **Active harness baseline unchanged:** `r5h-followup-guard-v1` 78/114,
  v3 49/72, v2 43/72, mnw 2.
* **DB:** `/mnt/c/hornelore_data/db/hornelore.sqlite3`
* **API log:** `ROOT_DIR/.runtime/logs/api.log` -- read it directly, do not
  ask Chris to paste it.
* **UI:** `http://localhost:8082/ui/hornelore1.0.html` ; **API:** port 8000.
* **Cold boot is ~4 minutes.** The HTTP listener answers at 60-70s but LLM
  weights and extractor warmup continue for another 2-3 minutes. **A
  `curl /` health check is NOT sufficient.**
* `code.api.main` must be imported from `server/`, not `server/code/`.
* Flags: `.env` line 253 `HORNELORE_TRIPS=1`, line 254
  `HORNELORE_IMPORT_PROVENANCE=1`. `.env.example` line 869 `HORNELORE_TRIPS=0`,
  line 870 `HORNELORE_IMPORT_PROVENANCE=0`.

---

## 4. Import Provenance schema gotchas

* **Table names are singular: `import_batch` and `import_candidate`.**
* **The stored column is `match_reason_json`, NOT `match_reason`.**
* `import_candidate` has `external_id`; only `import_batch` has
  `external_ref`.
* Photos are owned by `narrator_id`, not `person_id`.
* `candidate_create` inherits the batch's trip.
* `_now()` has whole-second precision, so both list queries tiebreak on
  `rowid`. Do not "fix" that.

### The vocabulary, confirmed live from `/enums`

```
import_sources    google_photos_picker, google_takeout, local_upload, csv, manual
batch_statuses    open, closed, failed
candidate_states  pending, accepted, rejected, duplicate, error
decidable_states  accepted, rejected, duplicate, error
taken_at_sources  exif, provider_metadata, filename_guess, operator, unknown
location_sources  exif_gps, provider_metadata, typed_address, operator, unknown
```

**`skipped` and `changed` are not shipped states.** They are WO-2 design
inputs. Do not use either word as a state.

### The 15 routes -- there is ZERO DELETE, by design

```
GET   /api/import-provenance/batches
GET   /api/import-provenance/batches/{batch_id}
GET   /api/import-provenance/batches/{batch_id}/counts
GET   /api/import-provenance/candidates
GET   /api/import-provenance/candidates/{candidate_id}
GET   /api/import-provenance/enums
PATCH /api/import-provenance/batches/{batch_id}/hidden
PATCH /api/import-provenance/batches/{batch_id}/trip
PATCH /api/import-provenance/candidates/{candidate_id}/hidden
PATCH /api/import-provenance/candidates/{candidate_id}/trip
POST  /api/import-provenance/batches
POST  /api/import-provenance/batches/{batch_id}/candidates
POST  /api/import-provenance/batches/{batch_id}/close
POST  /api/import-provenance/batches/{batch_id}/reopen
POST  /api/import-provenance/candidates/{candidate_id}/decision
```

---

## 5. State the Phase 5 smoke left in the live database

Two **hidden** batches and four candidates. They stay. There is no DELETE
route and removing them would be a deliberate operator action against the
live DB -- Chris's to run, not the agent's.

```
batch A  7055671b-b3fe-450c-ab75-204d7ed429ca  Christopher  PHASE5-SMOKE-A  counts 3/1/2
batch B  3f5a06dd-5eb5-49c9-9b8b-182151355eef  Kent         PHASE5-SMOKE-B  counts 1/0/0
c1  e8562917  picker shape   -> accepted (photo 20eb684daa754fc5832816220ed7ff9a)
c2  df13331e  takeout shape  -> rejected
c3  7b4c6c8d  manual shape   -> duplicate
c4  bd719e31  Kent           -> pending (cross-person accept correctly 409'd)
```

Verified unchanged by fingerprint: `photos` approval subset
`6c4c6a07e2...`, `trip_photo_links` `e3b0c44298...` (0 rows). New forward
baseline for `photos` full-row: `8e5f7a577a...`. No `narrator_ready` and no
`*_approved_for_lori` value moved.

Person ids in play: Christopher Todd Horne
`a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2`, Kent James Horne
`4aa0cc2b-1f27-433a-9152-203bb1f69a55`, Janice Josephine Horne
`93479171-0b97-4072-bcf0-d44c7f9078ba`, Melanie Zollner
`3fc781ae-aa03-4991-922f-f5ea6d813ae1`.

---

## 6. Open items carried forward

1. The two hidden `PHASE5-SMOKE` batches stay (above).
2. `.venv` / `.venv-gpu` FastAPI-Starlette drift -- deferred to a future
   harness/environment work order.
3. Pre-existing cross-module contamination in `tests/` -- not touched.
4. WO-2 input: `proposed_trip_day_id / region_id / stop_id` columns do not
   exist; the Evidence Review Queue will need a future migration 0038.
5. WO-2 decision: whether `changed` and `skipped` become states, a separate
   column, or nothing.
6. `WO-E2E-HARNESS-SANDBOX-01` recorded, not worked.
7. Identity preflight exits 1 on 5 harness clusters -- known, not in scope.
8. **`trip_bio_suggestions` is parked and is Chris's call**, a
   backend/product decision, not the agent's.

---

## 7. Decisions that are closed -- do not reopen

* The light-on-cream theme mismatch on the Travel Documenter. *"i like how
  the styles look on the travel doc so leav it as it is."* **Retired.**
* **Travel Documenter = operator tool for editing trips. Travels shelf =
  narrator/Lori conversation surface. Do not mix their state.**
* No person-merge tooling, no canonical pointer, no general duplicate
  cleanup, no Walt/Test/Kent harness cleanup, no identity architecture
  expansion. *"Do not spend another session on identity architecture."*
* No native `prompt` / `confirm` / `alert` on the operator path.
* No evidence-lane DELETE.
* *"Do not keep the wrong names just because the plan said them."*
* **Do not start Google Photos, Takeout, Lori review, export,
  bio_suggestions, or general duplicate cleanup** outside their own work
  orders.

---

## 8. Working style Chris expects

* Honest critique over flattery. Push back when something is wrong.
* Tight readouts, not walls of text.
* Do not relitigate decided things.
* Do not regenerate command blocks from memory -- derive them from the
  actual files.
* Read logs and reports directly; do not ask Chris to paste them.
* **No "cheap" / "expensive" cost framing in readouts.**
* Autonomy rule: *"Claude can fix anything it discovers that is directly on
  the path of the current phase, as long as it reports it clearly and does
  not quietly expand into a different subsystem."* And: *"note if there is
  an issue that we can fix, do not wait -- fix it and document so we have it
  in the git."*
* Syntax gates before handing anything over: `node --check` on JS,
  `ast.parse` on Python, JSON parse on data files.
* Git hygiene gate: the tree must be clean before code-changing work starts.
  Code and docs go in separate commits.
* Every session adds a `CLAUDE.md` changelog entry with **Files changed:**,
  **Files added:**, **Active baseline unchanged:**, flag state and open
  items, and refreshes `MASTER_WORK_ORDER_CHECKLIST.md` alongside it.
* **`MASTER_WORK_ORDER_CHECKLIST.md` records a phase status in THREE places:**
  the `**Active as of:**` block at the top (the old one is demoted to
  `**Previously:**` and the new one inserted above it), the
  `## Post-unification epic ...` section heading, and the phase table row.
  Patch all three.
* `docs/reports/` uses a `<name>.console.txt` naming convention.

---

## 9. First moves for the local agent

1. Read `CLAUDE.md` end to end, then `MASTER_WORK_ORDER_CHECKLIST.md`.
2. `git log --oneline -5` -- confirm the Phase 5 code and docs commits landed.
3. `git status` -- confirm a clean tree before starting anything.
4. Do **not** start WO-2, or any other work order, until Chris says which one
   and opens it as its own session.
