# MASTER_WORK_ORDER_CHECKLIST

**Active as of:** 2026-07-26 (**WO-DOC-RECONCILE-01** -- documentation reconciliation after the unification arc. Docs only; **no code, no tests, no config** -- not one file outside `README.md`, the unification spec, this checklist and `CLAUDE.md` was touched, and the 279-test baseline is unmoved. **The finding that prompted it:** `README.md` is the repository's front door and it still described the world as it stood on 2026-07-24 -- before Phases 1 through 6 landed. It named Travel Doc Lab depth as the active lane, carried no mention of `WO-TRAVEL-DOC-UNIFY-01` anywhere including the Work Orders table, and listed as an open MEDIUM issue a native `window.prompt()` in the evidence panel that the in-panel editor had already replaced -- verified here at **zero** executable `prompt`/`confirm`/`alert` calls in `ui/js/travel-doc-lab.js`, the six remaining occurrences all comments, and pinned by the surface gates. A second README issue was true but mis-scoped: the `travel-documenter.js` double-send defect now sits on a retired module unreachable from the shell, which a reader could not tell from the entry. Both corrected in place rather than deleted, because a known issue that was fixed and a known issue that moved off the operator path are different facts. **In the spec:** Phases 4, 5 and 6 carried full 'what landed' sections and a close-out but no status marker in the Phases index, so a reader skimming the index saw three open phases -- now `LANDED`/`CLOSED`; and Phase 6 Finding 1, the harnesses that could not run on this machine, is marked resolved by WO-HARNESS-DEPS-01. **Backlog moved from seven items to eight.** Item 5, the smoke-photo residue, is taken as *documented test rows* -- the second option it always offered -- because the live database lives outside the repository at `/mnt/c/hornelore_data/db/hornelore.sqlite3` per `.env`, which neither the container nor the device bridge can reach, so no agent-side pass can identify those six rows let alone clear them. New item 8 promotes Phase 6 Finding 4 -- `e7fdb578` is `Christopher` and `a4b2f07a` is `Christopher Todd Horne`, two person records that read as one human in every picker -- from curiosity to backlog, because Import Provenance Foundation writes provenance against a `person_id` and a split import across two narrators fails silently with both halves internally consistent. **Still open and needing Chris, not an agent:** whether `bio_suggestions` belongs in the force-delete gate at all. The evidence is now on the table -- `_TRIP_DEPENDENT_TABLES` already excludes `trip_themes` on the stated grounds that the gate keys on evidence lanes and themes are lightweight labels that must not break empty-trip semantics, and `trip_bio_suggestions` fails that same test on every count: written by `trip_timeline_bridge.sync_trip_to_life_record` on every create, one row, `status='suggested'`, derived from the trip rather than contributed to it. It is a backend change with a test consequence, so it is recorded, not taken.)

**Previously:** 2026-07-26 (**WO-HARNESS-DEPS-01** -- the Node Playwright toolchain is declared, pinned and documented, so both liveness harnesses now run where the code lives instead of container-only. Config and docs only; no `ui/`, `api/`, `server/`, schema, flag or test file changed and no test count moved. **The diagnosis was not a missing dependency.** `package.json` has declared `playwright` and `playwright-core` the whole time and is byte-identical on both copies; `.gitignore` line 61 excludes `node_modules/`, correctly, so the packages were never going to arrive with `git pull` and nothing in git could restore them once they were lost. **The browsers were already on disk and matched exactly:** `~/.cache/ms-playwright` holds `chromium-1208 chromium_headless_shell-1208 ffmpeg-1011 firefox-1509 webkit-2248`, and pulling `browsers.json` out of each candidate release maps that five-for-five onto Playwright **1.58.2**, the exact version the manifest names. Somebody did run `npx playwright install` properly once: the half that lives outside the repo survived and the half that lives inside it did not. **The caret was the active hazard** -- `^1.58.2` resolves to 1.62.0 today, which wants `chromium-1234`, so a plain `npm install` would have pulled a second ~500 MB browser set and stranded the one already there. All three Playwright entries are pinned exact, `@playwright/test` included because a mismatched one drags its own release in; tailwind's carets are deliberately untouched as out of scope, with `package-lock.json` committed to hold the rest of the tree still. **The root cause was documentation, not configuration:** the string `npm install` appeared in zero `.md` files in this repo and `node scripts/ui/` in zero, and `scripts/ui/README.md` documented one of that folder's five harnesses -- describing the Python toolchain that is *not* installed, in detail, while never mentioning either `.js` file. That README now covers both toolchains, both liveness harnesses, the exact-pin rationale, the `NODE_PATH` and `PLAYWRIGHT_CHROMIUM_PATH` overrides, and the WSL home-directory install that avoids writing `node_modules/` across `/mnt/c`. Also narrowed the stale Phase 4 plan line in the unification spec, which still read as though the retired Documenter and the dev harness were going to be deleted, per a review note.)

**Previously:** 2026-07-25 (**WO-TRAVEL-DOC-UNIFY-01 CLOSED** -- Phase 6 live smoke green on all thirty-seven steps with zero defects, so the work order closes rather than continuing. Live verification and docs only; **not one line of code was written** and no `ui/`, `api/`, `server/`, schema, flag or test file changed. Ref-based clicking was abandoned in the first few steps because refs churn on every re-render inside the workspace, so interaction ran through a page-side helper resolving elements by text and structure at call time, and every persistence claim was read back from `/api/trips/{id}/tree` server-side rather than off the DOM. Dialogs, listeners, sockets, console errors and non-2xx traffic came from an instrumentation spy installed before the mount -- including a `WebSocket.prototype.send` wrap, so the Lori modal scope was proved from the **actual outbound `start_turn` frame** rather than the on-screen label. The Travel Doc tab mounts the unified workspace directly with no toggle and no retired UI, and the shell's rendered text holds zero occurrences of *legacy*, *production Travel Doc*, *UI Lab*, *experimental*, *lab-only*, *removable* or *documenter*. Two regions and nine stops built, edited at all four levels, reordered, insert-before/after on a top-level stop and on a substop, a cross-region move through the edit drawer, substop arrows confined to their sibling group, and order surviving a full refresh. Upload `FileList` node identity held across a scope retarget; cluster stated its whole-library caveat. **The lifecycle census across three leave/re-enter cycles is the load-bearing proof:** read as deltas, every entry opened exactly what the previous exit closed -- never more than one live channel or one live keydown listener, and the Lori socket opened exactly once in the whole run. Zero native dialogs, zero console errors. **The force-delete gate rendered all ten impact lanes with `bio_suggestions` HOT at 1**, which is the Phase 3A finding reproducing live: production's nine-lane grid would have shown that evidence nowhere while the backend refused the delete. Arming was tested against a fifteen-case matrix -- case folding, prefix, suffix, one short and one long all refused; only the exact title, the exact id, or those with surrounding whitespace armed -- and the forced delete completed, with the narrator's trip list confirmed empty from the API. The dev harness still mounts; the retired Documenter is still served and still unreachable from the shell, its six remaining textual references all inside comments. 279 tests green; both Playwright harnesses PASS (14/14, 23/23). **Five findings, none a defect**, the most actionable being that **the two liveness harnesses cannot run on Chris's machine at all** -- `node_modules` is absent from the working tree, so they were run in the container after md5 proved the eight relevant files byte-identical, which is sound but leaves part of the proof chain unreproducible where the code lives. Seven-item post-unification backlog carried forward at the foot of the spec.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 5 LANDED -- one coherent Travel Doc test surface. Tests and docs only; no `ui/`, no `server/`, no backend, no API, no schema, no flag change, nothing deleted. Added `tests/travel_doc_surfaces.py`, the single map of the eleven Travel Doc surfaces and which are on the operator path, and `tests/test_travel_doc_surface_gates.py`, which holds the cross-cutting doctrine that used to be asserted once per originating work order. Six suites retargeted onto the map -- thirty private `Path` literals and eleven private copies of the comment stripper and the shell-region extractors gone -- with **no test body moved**, so no coverage shifted. **Chris's premise was half true and that matters:** Phase 4 had already narrowed most of the assertions this phase expected to find stale. Exactly one stale thing existed and it was a *name*, not an assertion: `test_lab_does_not_import_production_module` was renamed `test_the_unified_module_never_loads_the_retired_one` with its assertion untouched. One real duplicate was narrowed so the module-wide `prodTravelDocUrl` claim has a single owner. The retired `travel-documenter.js` still carries exactly two native confirm calls and still pre-stringifies its bodies; that is **pinned at two** rather than repaired (out of scope) or deleted from the tests (which would hide it), and a separate gate fails the build if the module is ever re-attached to the operator path. `scripts/ui/run_travel_doc_mount_liveness.js` had been in no surface inventory at all and is now in the map and in the dialog scan. 279 tests green (was 262); twelve mutations, twelve killed -- one of which exposed a real hole in a brand-new gate, where matching the bare name `lvTravelDocMount` also matched the `typeof` guard above the call, so the gate would have passed a shell that checked whether it could mount and then never did. **Deliberate deviation from the Phase 0 plan:** the two suites were NOT concatenated into one `tests/test_travel_doc.py`. They guard two different modules that both still exist; the fold would produce a 125K file whose name claims a boundary it cannot hold and would move every line number in both. Coherence came from a shared map plus one doctrine file instead. The literal fold remains available as a mechanical follow-up commit if Chris wants it.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 4 LANDED and smoke-accepted -- the legacy fallback is retired and the unified Travel Doc is the operator's only Travel Doc surface. Removal phase, front-end only; **no backend, no API, no schema, no flag change, and no endpoint or module deleted**. Out of the shell: the surface toggle and its whole support cast (`_LV_TD_SURFACE_KEY`, `_lvTravelDocSurface()`, `_lvTravelDocDestroyLegacy()`, `_lvTravelDocPaintSurfaceChrome()`, `window.lvTravelDocSetSurface`), the two legacy asset tags, the switch row, the `#lvTravelDocHost` div, the `.lv-td-surface-*` / `.lv-td-host-off` / `body.lv-td-focus` rules, and the route board's `prodTravelDocUrl()` deep-link foot-note. **Unmounting a surface is not deleting a module:** the old module, its stylesheet and its standalone page all stay on disk and that page still mounts it, pinned by a new `LegacyModuleStillExistsTest`. The dev harness `ui/travel-doc-lab.html` was **kept and labelled `DEV-ONLY`** rather than deleted, because it is the only caller of `lvTravelDocMount()` outside the shell and the only one that exercises the non-shell identity branch -- delete it and that branch rots untested. **Five on-path fixes the order did not name:** the `lv80SwitchPerson` teardown fallback was nulling the retired Documenter's marker and had become a silent no-op; the day photo picker's empty state was ungated, operator-visible, and pointed at a production Travel Doc that no longer exists for a capability Phase 3C moved onto this surface's own toolbar; the evaluation checklist still called itself part of a removable lab; the route-board deep link and its CSS rule; and three `body.lv-td-focus` rules that went unreachable when the Documenter left the shell path. **A gate that looked obvious and was wrong:** a file-wide `assertNotIn("legacy")` on the shell is invalid -- 19 unrelated occurrences live there -- so it is scoped to the Travel Doc panel and the `app.js` mount block, while a stronger gate became possible instead, because the shell now contains zero **raw** occurrences of the old module's name and can be asserted un-stripped. **Tests rewritten, not deleted:** five whose boundary inverted came out, thirteen went in, and seven more across two suites were narrowed so each keeps the half that still proves something and flips only the half Phase 4 retired -- absences are now *asserted*, so re-adding a `<script>` tag fails the build. 262 tests green (was 255); eight mutants, eight killed; the shell-mount liveness harness rewritten for one surface with a new `singleSurface` probe and its now-unrunnable negative controls marked as such rather than quietly dropped. Live smoke green on all fifteen of Chris's steps, including a three-round mount census showing opens 3 / closes 2, keydown +3 / -3, zero net sockets and one `.tdl-root` at every sample. Phase 5 test consolidation and the `travel-doc-lab.js` -> `travel-doc.js` rename are explicitly out of scope and stay parked.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 3D LANDED and smoke-accepted — route order and route-row ergonomics now exist in the unified Travel Doc workspace, which closes the last surface where the legacy Documenter still held a workflow advantage. Production's board was reviewed against the port and had exactly four affordances the port lacked — region reorder, stop reorder, evidence badges on route rows, and a selectable region row — and all four are in; **nothing was retired**, and production has no drag-and-drop on either tile (grep-verified). **The load-bearing decision is that a stop move sends two ids, not a permutation:** production posts the whole sibling list to `/stops/reorder`, which 400s unless that list is exactly the current sibling group — a request precisely as stale as the tree it was built from, so any concurrent insert or delete refuses a move the operator can see is legal. The port calls `/stops/{id}/move` with `before_stop_id`/`after_stop_id` and lets the backend re-derive the group; `/move` **is** the existing API shape and is what production already uses for cross-region moves. Regions still post a permutation because `/regions/reorder` is the only door, so a refusal is surfaced in-panel and the bundle reloaded rather than dead-ending. A reorder never reparents: `region_id` and `parent_trip_stop_id` are echoed back unchanged, so a substop moves among its own siblings only. `routeBusy` serialises moves and disables every arrow while one is in flight; `routeError` is the in-board failure surface; both clear with the trip and with a deleted row. Making region rows selectable revived Phase 3C's `defaultScopeKey()` region arm, which could never fire because `st.routeSel` was written in one place and only ever as a stop. Evidence badges cost zero fetches. **The live smoke found a defect nineteen source-scanning gates could not see:** `api()` owns the request encoding and stringifies `opts.body` itself, and both new movers pre-stringified theirs, so every arrow press on the board answered 422 - a defect that lives in the relationship between a call site and `api()` rather than inside either one, which is why no static gate could reach it and why the smoke stays a gate rather than a formality. Fixed with a raw object at both call sites plus two new gates, one banning `body: JSON.stringify` file-wide while pinning that the encoding still happens exactly once inside `api()`. 255 tests green (was 236); nineteen gates mutation-tested rather than trusted, nineteen mutants killed. **A pre-existing red found and repaired:** Phase 2 commit `e9b792c` widened the `lv80SwitchPerson` block in `hornelore1.0.html` but the matching test-window widening was never committed, so the device baseline had really been 235/236 since Phase 2 and container-only runs were masking it — that repair ships as its own commit. Front-end only; no backend, no API, no schema, no flag change. **Live smoke green on all eleven of Chris's steps**, verified server-side through `/api/trips/{id}/tree` rather than off the DOM: region and stop reorder both directions, substops travelling with their parent, insert before/after on a top-level stop and on a substop, cross-region move, cycle rejection at both the UI and the API layer, order surviving a full page refresh, counts refreshing, both Phase 3B delete ladders, the Phase 3C `FileList` node identity across a scope retarget, the Phase 3A force-delete gate arming only on the exact title, a clean mount/socket census across three legacy round trips, and zero native dialogs and zero console errors. Phase 4 is a separate session.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 3C CODE-LANDED — photo upload, source upload and photo clustering now exist in the unified Travel Doc workspace, so the legacy Documenter is no longer needed for intake. Built, not ported: the lab had zero `FormData` and zero file inputs, so `api()` grew a `FormData` branch ahead of its JSON branch and an intake module of roughly four hundred lines landed behind three new `st` fields. **Scope is an explicit drawer selection, not production's ambient `editorScope()` read** — production can silently retarget an upload between choosing a file and pressing Upload; the port names the destination in prose before the request. The load-bearing constraint is `FileList`, which script cannot write, so the drawer never repaints between choosing files and uploading, and a test pins that absence. Intake is not approval: no `include_in_memoir` and no `trip_day_id` is ever sent, day attach stays separate, evidence lanes stay hide-only, no new DELETE. **A same-scope bug found and fixed:** three suites used a string-blind comment stripper and went blind on `files.accept = "image/*"` — migrated to the repo's existing `strip_js_comments`, assertions unchanged, which is why that migration is its own commit landing before the Phase 3C code. 236 tests green (was 220); the sixteen new gates were mutation-tested rather than trusted; all twelve of Chris's live-smoke steps green across all three upload scopes, with no-auto-promotion verified server-side and zero native dialogs recorded by a spy. Front-end only; no backend, no API, no schema, no flag change. Phase 3D is a separate session.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 3B CODE-LANDED — trip create/edit and region/stop CRUD now exist in the unified Travel Doc workspace. Four editor drawers plus an in-panel delete-review ladder; the empty-state copy bug is fixed; the `current` tab is renamed `trip` behind a `setTab` shim; insert-at-position (`insertContext`/`insertHint`) is preserved with a stale-context guard production never had. **Region delete fixes a production defect rather than porting it:** the backend 409s on a non-empty region unless forced, and production neither forces nor handles the 409, so its `window.confirm()` delete silently dead-ends — the port tries unforced first and escalates to a second review stage quoting the server verbatim. Zero native dialogs, proved by a spy across every destructive flow, not by inspection. Also wired `st.daysWarning`, which the Trip Plan tab read but nothing ever set. 220 tests green (was 205); all thirteen of Chris's live-smoke steps green, including a functional mount/socket/listener census (1 socket live, 1 channel live, all eight bundle endpoints fetched exactly once after a broadcast). Front-end only; no backend, no API, no schema, no flag change. Phase 3C is a separate session.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 3A CODE-LANDED — the trip force-delete impact-review gate is now in the unified Travel Doc workspace: normal delete first, a 409 opens an in-panel review reading `e.body.detail`, force delete arms only on the exact trip title or trip id, and no native `confirm`/`prompt`/`alert` is used anywhere in the flow. The port renders **ten** impact lanes; production renders nine and omits `bio_suggestions`, which every trip is born with — so every trip is force-delete-only from birth and production shows an all-zero grid next to a refused delete. 205 tests green (was 192), and all ten of Chris's live-smoke steps passed on the running stack. Front-end only; no backend, no API, no schema, no flag change. Phase 3B is a separate session.)

**Previously:** 2026-07-25 (WO-TRAVEL-DOC-UNIFY-01 Phase 2 CODE-LANDED — the unified Travel Doc workspace now mounts directly in the shell's Travel Doc tab and is the default operator surface; the legacy Documenter stays reachable behind a temporary surface switch. Lab CSS scoped to `.tdl-root`, Lab branding gone from the operator path, exactly one mount ever live. 192 tests green plus a second headless proof `scripts/ui/run_travel_doc_shell_mount_liveness.js` (22 checks) with four negative controls actually run. Front-end only; no backend, no API, no schema, no flag change. Phase 3 is next and is a separate session.)
**Previously:** 2026-07-24 (WO-TRAVEL-DOC-UNIFY-01 Phase 1.1 CODE-LANDED — the mount can no longer be repainted after `destroy()`. Six guards at the file's six async choke points, plus the `document`-level keydown listener now unbound at teardown. 154 tests green; stale-callback behaviour proved in a real browser by `scripts/ui/run_travel_doc_mount_liveness.js`, with two negative controls confirmed red.)
**Previously:** 2026-07-23 (live-verification pass on the running stack — migrations 0034/0035, trip API baseline, Travel Doc smoke, and response-guard health all GREEN; INC-2026-07-09 response-guard outage closed; camera-consent ambush + extractor guards + trip-create day-count + public-lookup wording fixed. See README "Status as of 2026-07-23" and the CLAUDE.md 2026-07-14 changelog entry.)
**Earlier:** 2026-07-11 (doc-consistency pass — split "code landed" vs "flag live" vs "formal verification" statuses per Chris's audit; 2026-07-11 HIGH repo-review batch closed via commits ebe64af / cf62c49 / round-2 / round-3), 2026-07-02 (code-vs-checklist adjudication — ALL six build-sequence WOs verified LANDED in-tree; trip-lane conversation layer at 62/72→GREEN pending harness re-verify; Spanish-detection overfire class fixed), 2026-06-16 (post Phase 3+4+5+6+7.5 of QUESTIONNAIRE-BIO-FACTS-MIGRATE), 2026-06-14 (post-universal-pivot)

---

## Status legend (locked 2026-07-11)

Three distinct dimensions — do NOT conflate them:

- **CODE-LANDED** — the implementation exists in-tree, has unit-test coverage, and AST-parses clean. Verifiable by reading the code.
- **FLAG-LIVE** — the corresponding `HORNELORE_*` env flag is set to `1` in the running `.env`, so the code path actually fires in real sessions. Verifiable by reading `.env` + api.log startup line.
- **FORMAL-VERIFIED** — a written verification report exists in `docs/reports/` demonstrating the feature works under a target scenario (red-team pack, canary session, harness eval, live-narrator transcript). Verifiable by opening the report.

Something can be code-landed but not flag-live (behind a default-off flag). Something can be code-landed AND flag-live but not formal-verified (running in the wild but no written proof yet). "LANDED" without qualifier historically meant code-landed; from 2026-07-11 forward the word alone is deprecated — use one of the three explicit terms.
**Supersedes:** Pre-pivot checklist (archived at `docs/archive/handoffs-pre-pivot/MASTER_WORK_ORDER_CHECKLIST.md`)
**Read first:** [`docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`](docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md), [`docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`](docs/architecture/LORI-RUNTIME-ARCHITECTURE.md)

---

## Posture

Hornelore is Lorevox. The Horne family is tenant zero, not a special case in the architecture. Every WO from this date forward is written against the universal assumption: Lori must work for narrators she has never met. Pre-pivot WOs (114 specs, locked-narrator framing) are archived at `docs/archive/workorders-pre-pivot/` for traceability — they are not the active source of truth.

Interview default is moving from questionnaire-first to **oral-history-as-default**. Structured styles become operator-selectable overrides.

---

## Build sequence — one Cowork session per WO, in order

Each WO gets its own Cowork session with the WO spec as the brief. Do NOT start more than one at a time.

| # | WO | File | Closes / Introduces |
|---|---|---|---|
| 1 | SAFETY-LLM-CLASSIFIER | [`docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md`](docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md) | Closes Gate 5 (soft-trigger safety) — **LANDED (verified in-tree 2026-07-02):** `safety_classifier.py` 3-dim taxonomy + LLM layer + confidence floor + 44 tests; gated `HORNELORE_SAFETY_LLM_LAYER=0` |
| 2 | SOFTENED-MODE-PERSISTENCE | [`docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md`](docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md) | Closes Gate 6 (post-safety recovery) — **LANDED (verified in-tree 2026-07-02):** `lori_softened_response.py` 3-state machine + per-trigger caps (30/35/50) + 32 tests; gated `HORNELORE_SOFTENED_RESPONSE=0` |
| — | **Flag already flipped** | `HORNELORE_SAFETY_LLM_LAYER=1` + `HORNELORE_SOFTENED_RESPONSE=1` | ✅ **FLAG-LIVE 2026-07-05** (both `.env` values set). Remaining item is FORMAL-VERIFIED — red-team pack + softened-persistence harness against the live flag state. NOT a code-work blocker. |
| 3 | PHASE-9-DISCLOSURE-UPDATE | [`docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md`](docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md) | Consent disclosure edits — **LANDED (verified in-tree 2026-07-02):** three-tier disclosure + style descriptions in `docs/runbooks/SAFETY_OPERATOR_RUNBOOK.md` (docs-only WO) |
| 4 | STORY-FIRST-PHASE-1 | [`docs/wo/WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md`](docs/wo/WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md) | Oral-history behavior engine — **LANDED (verified in-tree 2026-07-02):** `reflection_grounding.py` + `story_momentum.py` + `thread_bank.py` + `question_hierarchy.py` + chat_ws wiring + 66 tests; REPORT-ONLY behind `HORNELORE_STORY_FIRST_PHASE_1=0` |
| 5 | ORAL-HISTORY-DEFAULT | [`docs/wo/WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md`](docs/wo/WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md) | Introduces `oral_history` style + makes it default — **LANDED AND ACTIVE (verified in-tree 2026-07-02):** style @ 90-word cap, system default in comm-control signatures, picker + 29 tests |
| 6 | BIO-BUILDER-UNIVERSAL | [`docs/wo/WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md`](docs/wo/WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md) | Four-tier Bio Builder — **LANDED (verified in-tree 2026-07-02):** `bio_fact_router.py` + `document_authority.py` + `bio_anchored_asker.py` + `bio_gap_map.py` + 3 creep defenses + 66 tests; gated `HORNELORE_BIO_*=0` |
| 6a | OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 | (root WO, 2026-06-15) | 9-section intake form + Phase 2B orchestrator + Phase 2C modal — **LANDED** |
| 6b | QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 | [`docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md`](docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md) | Phase 1 read swap + Phase 2 FE badges + Phase 3 write fan-out + Phase 4 primary_career bug + Phase 5 23-test pack + Phase 6 self-review + Phase 7.5 backfill readiness — **LANDED 2026-06-16**, Phase 7 live verify pending |
| 7 | MEMORY-EXERCISE-IMPLEMENTATION | (not yet drafted) | Specced in [`docs/architecture/MEMORY-EXERCISE-DECISION.md`](docs/architecture/MEMORY-EXERCISE-DECISION.md) |

---

## Superseded / history

The two docs below land for design-history traceability. Do NOT build from them.

- [`docs/wo/superseded/WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md`](docs/wo/superseded/WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md) — merged into #1 SAFETY-LLM-CLASSIFIER
- [`docs/wo/superseded/PRE-BUILD-ADDITIONS.md`](docs/wo/superseded/PRE-BUILD-ADDITIONS.md) — changelog of edits already folded into the strategy + WO specs
- [`docs/wo/superseded/REDESIGN-DOC-HEADER-TO-PREPEND.md`](docs/wo/superseded/REDESIGN-DOC-HEADER-TO-PREPEND.md) — header block for `WO-INTERVIEW-PROCESS-REDESIGN-01`; target doesn't exist in repo, header was not applied

---

## Parent-session readiness gates (locked checklist)

Inherited from pre-pivot work. Pre-pivot evidence in `docs/archive/`; post-pivot evidence as it lands.

| Gate | Code | Flag | Formal | Lane / note |
|------|------|------|--------|-------------|
| 1. DB lock fix | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 2. Atomicity discipline | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 3. Story preservation | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 4. Safety acute path | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 5. Safety soft-trigger | ✅ landed 2026-07-02 (`safety_classifier.py`, 44 tests) | ✅ live 2026-07-05 (`HORNELORE_SAFETY_LLM_LAYER=1` in `.env`) | 🟡 pending | Remaining: red-team pack on live flags; report → `docs/reports/`. Also `SafetyResult` NameError in `chat_ws.py` closed 2026-07-11 via `ebe64af` — no more silent no-op on trigger. |
| 6. Post-safety recovery | ✅ landed 2026-07-02 (`lori_softened_response.py`, 32 tests) | ✅ live 2026-07-05 (`HORNELORE_SOFTENED_RESPONSE=1` in `.env`) | 🟡 pending | Remaining: softened-persistence harness evidence on live flags (lockstep with Gate 5). |
| 7. Truth-pipeline observability | 🔴 not started | — | — | Scoped separately; not in the 6-WO sequence. Highest-priority unstarted lane. |

---

## Open work (locked 2026-07-23)

Priority order for what to build next. Items 1 + 2 (migration/trip verification, Travel Doc smoke) are **DONE** as of the 2026-07-23 live pass — the queue below is the remainder.

**✅ Closed 2026-07-23 (live-verified on the running stack):**

- **Migration 0034/0035 verification** — FK + orphan cleanup applied clean; 0 orphan trips; no FK-check errors.
- **Trip API live baseline** — bogus person_id → 422; create → auto-days; patch → renumber; delete → cleanup; real trips preserved; zero DB locks / FK failures / 500s. ND-incident class contained.
- **Travel Doc smoke (9 canaries)** — OCR text/textless, real+blocked lookup, approval ladder, Lori wording (no "I can see"/coords), capture scope. All green.
- **Response-guard health** — 0 `wrapper raised` in current boot; no first-person parrot. INC-2026-07-09 closed.
- **P1/P2 fixes** — trip-create surfaces `days_created` (+ Trips-tab message); public-lookup title suffix strip + spoken-context trim; camera-consent ambush; extractor affect-hedge + vague-temporal guards; narrator-label collision; modal-turns-as-life-story archive gate.

**Remaining open work (priority order):**

1. **C1b — end-to-end WebSocket safety-routing test** — indirect ideation → classifier → `SafetyResult` → segment flag → softened mode → operator-visible signal → safe reply. Not yet proven end-to-end; protects Kent & Janice. Highest-value open safety item.
2. **`.env.example` drift audit (NEW WO)** — codify a grep gate: `grep -oh 'os.getenv("[A-Z_]\+"' server/code/ | sort -u`. Compare against `.env.example`. Reconcile ~24 stale documented flags + ~30 code-referenced undocumented flags. Flag drift is becoming a real ops risk.
3. **TRUTH-PIPELINE-01 Phase 1 (Gate 7)** — observability stub across the five truth-write stages (`raw_turn_saved` / `archive_event_created` / `extract_fields_called` / `family_truth_written` / `projection_updated`) per harness turn. Highest-priority unstarted lane. Blocks the remaining 🟡 formal-verified marks on Gates 5 + 6 becoming ✅ (the harness needs turn-level truth-write visibility to distinguish a real bug from a harness coverage gap).
4. **`sysBubble()` narrator-dignity pass** — some operator-tone bubbles retired behind `LV_INLINE_OPERATOR_BUBBLES`; the full 28-call sweep is still open. Operator/status/debug strings must not write into narrator chat.
5. **Extraction Track D (measurement first)** — D1 Travel Doc binding-eval corpus (report-only, UI scope as expected binding), D2 `story_candidates` Path 2 (preserved story text → draft candidates, operator review, no auto-promotion), D3 `utterance_frame` first consumer (hints vs Travel Doc scope, report-only). No truth writes.
6. **QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 7 live verify** — code + tests landed 2026-06-16; live verify pending. Either finish it or explicitly park.
7. **WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01 draft** — ADR at `docs/architecture/MEMORY-EXERCISE-DECISION.md` says the style stays and needs a real implementation. Draft the WO spec before starting code.

## Travel Doc unification -- WO-TRAVEL-DOC-UNIFY-01 (✅ **CLOSED 2026-07-25**, all six phases landed, Phase 6 live smoke 37/37 green)

Spec: [`docs/wo/WO-TRAVEL-DOC-UNIFY-01_Spec.md`](docs/wo/WO-TRAVEL-DOC-UNIFY-01_Spec.md)

**The problem this closes.** Two divergent Travel Doc implementations means the
operator's day-to-day surface is whichever one they happened to open — day cards
in one, route editing in the other. That cost a working session on the Bismarck
trip: the six `trip_days` rows existed and were correct, but the panel reachable
from the shell does not render day cards, so the work looked lost.

**Direction (decided, do not relitigate): the Lab absorbs the Documenter.**
Either direction rewrites the losing file at roughly equal cost; only this one
keeps the newer render architecture (state object + `renderAll()` loop +
preserved scroll + dirty-guard) instead of landing on `template()` →
`innerHTML`. `renderCurrent()` in the Lab is a deliberate placeholder — the
merge socket, not a feature. **The backend needs no changes at all.**

| Phase | Status |
|---|---|
| 1 — make the Lab mountable (`window.lvTravelDocMount(hostEl, opts) -> {destroy()}`) | ✅ **CODE-LANDED 2026-07-24.** Behaviour-neutral. `node --check` clean, 142 tests green across the five suites that read the lab source, mount lifecycle driven in a headless browser with `BroadcastChannel` instrumented (load → 1 channel; 2nd mount → 2; `destroy()` → 1 with the first still fully rendered; repeat `destroy()` a no-op). NOT formal-verified in the shell — see Phase 2. |
| 1.1 — mount liveness (hardening gate before Phase 2) | ✅ **CODE-LANDED 2026-07-24.** Chris's Phase 1 review: `destroy()` tore down but nothing stopped an in-flight async callback from repainting the cleared host. The file has exactly one of each guardable thing — one `fetch(` (in `api()`), one repaint entry (`renderAll()`), one channel handler, one socket `onmessage`, one timer, one `document` listener — so six guards cover all 54 `.then(` sites; the tests pin those counts so a seventh path fails loudly. `api()` returns a never-settling promise when dead, so neither `.then()` nor `.catch()` fires. Socket-identity pinning also fixes a **live-mount** bug: `loriPane.reset()` runs on every trip switch, so a queued Trip A token could append into Trip B's transcript. Also unbinds the `document` keydown listener — the leak the review did not name. 154 tests green; headless proof `scripts/ui/run_travel_doc_mount_liveness.js` (control row repaints, three destroyed rows do not); two negative controls confirmed red. |
| 2 — coexist in the shell tab behind a toggle | ✅ **CODE-LANDED 2026-07-25.** The tab now holds two hosts and a surface switch; unified is the default, legacy is one click away, and exactly one is ever mounted — each surface owns a BroadcastChannel, a `document` keydown listener and a Lori socket, so two live mounts is a correctness bug, not untidiness. Lab CSS rescoped from `:root`/`.tdl-body` to `.tdl-root` (custom-property inheritance is DOM-based, so the three `position: fixed` overlays still resolve through the host and were left alone). Launcher block deleted; `?person_id=`/`?api=` quarantined to the standalone page. Closed two pre-existing leaks: the shell was discarding the Documenter's handle, and the Documenter never closed its trip-update channel. 192 tests green; `scripts/ui/run_travel_doc_shell_mount_liveness.js` 22/22 on the real shell. It caught three defects static tests could not, including a `window._lvTravelDocSurface` cache that overwrote the same-named function. **Behaviour change:** leaving the tab destroys the mount, so trip/day selection does not survive a tab round-trip. |
| 3A — trip force-delete impact-review gate | ✅ **CODE-LANDED 2026-07-25.** Normal delete first; a 409 loads `e.body.detail` into an in-panel review; force delete arms only on the exact trip title or trip id; zero native dialogs. `api()` now attaches `err.status`/`err.body` — without that the gate could not read the payload at all. Renders **ten** lanes; production renders nine. Three blanket never-DELETE test guards narrowed, not dropped. 205 tests green; ten-step live smoke green. |
| 3B — trip create/edit + region/stop CRUD | ✅ **CODE-LANDED 2026-07-25.** Trip create/edit (title, dates, summary, days/sync warnings), region create/edit/delete (label, area, start, end, base, summary, with a soft out-of-range date warning), stop create/edit/delete (eight-value `STOP_TYPES`, region selector, reparenting with subtree exclusion). Insert-at-position preserved via `insertContext`/`insertHint` plus a guard that drops a stale context when the drawer is retargeted — production had no such check. `window.confirm()` did **not** port: both deletes are in-panel reviews, and the region path fixes a production dead-end (the backend 409s on a non-empty region unless forced; production neither forces nor handles it, so the delete silently does nothing). Also wired `st.daysWarning`, read by the Trip Plan tab but never set. 220 tests green; thirteen-step live smoke green with a functional socket/channel/listener census. |
| 3C — photo / source upload + cluster | ✅ **CODE-LANDED 2026-07-25.** Built, not ported — the lab had zero `FormData` and zero file inputs, so `api()` grew a `FormData` branch ahead of its JSON branch. One upload drawer with an explicit trip / region / stop scope selector and a target line that names the destination in prose; production instead reads the ambient `editorScope()` at submit time and can silently retarget. The drawer never repaints between choosing files and uploading, because a `FileList` cannot be restored by script — a test pins that absence. Source upload preserves `source_type` and `title` and never promotes: no `include_in_memoir`, no `trip_day_id`. Cluster renders in-panel and states the caveat production hides — the endpoint clusters the narrator's whole photo library. Evidence lanes unchanged, no new DELETE. Also fixed a same-scope bug: three suites used a string-blind comment stripper and went blind on `files.accept = "image/*"`. 236 tests green; sixteen new gates mutation-tested; twelve-step live smoke green across all three upload scopes. |
| 3D — route board | ✅ **LANDED 2026-07-25 (smoke-accepted).** Rows render in server order (client-side `.sort(` / `.reverse()` banned on the board path) with per-row up/down arrows that disable at the ends and while a move is in flight. **A stop move posts two ids to `/stops/{id}/move`, not production's full permutation to `/stops/reorder`** — a permutation is exactly as stale as the tree it was built from, and `/move` is the existing shape production already uses for cross-region moves. Regions still post a permutation because `/regions/reorder` is the only endpoint, so a refusal is surfaced in-panel plus a bundle reload rather than dead-ending. `region_id` and `parent_trip_stop_id` are echoed back unchanged so a reorder can never reparent. `routeBusy` serialises moves, `routeError` is the in-board failure surface, both clear with the trip and with a deleted row. Region rows made selectable, which revived Phase 3C's unreachable `defaultScopeKey()` region arm. Evidence badges at zero fetch cost. **The live smoke caught what nineteen static gates could not:** both movers pre-stringified a body that `api()` already stringifies, so every arrow press answered 422; fixed with a raw object at both call sites plus two gates banning `body: JSON.stringify` file-wide while pinning the encoding inside `api()`. 255 tests green (was 236); nineteen gates mutation-tested, nineteen mutants killed. **Live smoke green on all eleven steps** — reorder both directions, insert before/after including on a substop, cross-region move, cycle rejection at both layers, order surviving a refresh, both delete ladders, `FileList` node identity, the force-delete gate, a clean mount/socket census, zero native dialogs. |
| 4 — retire the legacy fallback | ✅ **LANDED 2026-07-25 (smoke-accepted).** Removal only. The surface toggle and its whole support cast came out of `app.js`, the two legacy asset tags plus the switch row and `#lvTravelDocHost` came out of the shell, the `.lv-td-surface-*` / `.lv-td-host-off` / `body.lv-td-focus` rules came out of `lori80.css`, and the route board's `prodTravelDocUrl()` deep-link foot-note came out with its CSS rule. **This phase deliberately narrowed the plan written here in Phase 0.** The old row said "remove `travel-documenter.js` / `.css`, `travel-doc-lab.html`" and "rename survivors"; Chris's actual Phase 4 order said the opposite on all three counts, and it is right on all three. Requirement 7 forbids removing anything a backend endpoint still serves, and `ui/travel-documenter.html` still mounts that module — unmounting a surface from the shell and deleting a module are different acts. `travel-doc-lab.html` is **kept and labelled `DEV-ONLY`**, because it is the only caller of `lvTravelDocMount()` outside the shell and the only one that mounts without the shell's identity flag; delete it and that branch rots untested. The rename is parked as churn that would bury a real diff. **Five on-path fixes the order did not name**, chief among them a `lv80SwitchPerson` teardown fallback that was nulling the retired marker and had become a silent no-op, and an ungated, operator-visible photo-picker empty state pointing at a production Travel Doc that no longer exists. **A file-wide `assertNotIn("legacy")` on the shell is invalid** — 19 unrelated occurrences — so the gate is scoped to the panel and the mount block; a stronger one replaced it, since the shell now holds zero **raw** occurrences of the old module's name. Tests rewritten not deleted: five out, thirteen in, seven narrowed. 262 tests green (was 255); eight mutants, eight killed; the liveness harness rewritten for one surface with a `singleSurface` probe and its unrunnable negative controls marked rather than dropped. **Live smoke green on all fifteen of Chris's steps.** One surface and no fallback toggle in the shell (0 `[data-td-surface]`, 0 `.lv-td-surface-switch`, no `#lvTravelDocHost`, `lvTravelDocSetSurface` undefined), zero requests for the retired module across 190 resources, and zero visible occurrences of *legacy*, *production Travel Doc*, *UI Lab*, *experimental*, *lab-only*, *removable* or *documenter* anywhere in the shell's rendered text. Region and stop create, edit and reorder verified server-side through `/api/trips/{id}/tree` rather than off the DOM, with a region's stops travelling with it and no reparenting. Photo and source upload both green with `FileList` node identity held across the drawer; cluster correct including its whole-library caveat. Lori opened at `surface: travel_doc_modal` scoped to the trip. **The mount census across three leave/re-enter round trips is the load-bearing one for this phase:** instrumenting `BroadcastChannel`, `WebSocket` and `document` keydown showed each entry opening exactly what the previous exit closed -- opens 3 / closes 2, keydown +3 / -3, sockets 0 net, `.tdl-root` pinned at 1 at every sample -- so retiring the second surface did not leave a second listener behind. Force delete rendered all ten impact lanes, refused a title one character short, armed only on the exact title, and completed. Zero native dialogs across the whole run, recorded by a spy rather than by inspection, and zero console errors across a full reload plus a sweep of all eight Travel Doc tabs. The standalone harness still mounts. One observation, not a defect: the dev harness page's *rendered* copy still says "Travel Doc UI Lab" and "This experimental lab needs a narrator" and still paints the `UI Lab - experimental` badge, while the page's own HTML header declares it `DEV HARNESS -- DEV-ONLY, REMOVABLE`. All three strings sit behind `embedded ? ... : ...` ternaries (`travel-doc-lab.js` lines 1096, 1100, 1591), so they can only ever render on the standalone page and never in the shell -- which is why the shell-path copy gate came back clean. Requirement 5 is met by quarantine rather than removal, exactly as written. The harness now calls itself two different things; reconciling that is a copy edit, parked rather than taken unilaterally after the code had already been committed. Smoke residue: the disposable trip and its uploaded source went with the cascade, but the uploaded photo did not -- photo *links* are deleted, photos are not -- so narrator `e7fdb578`'s library now holds five smoke photos, up from the four already accepted as documented residue. |
| 5 — test consolidation | ✅ **LANDED 2026-07-25.** Tests and docs only. `tests/travel_doc_surfaces.py` is the one map of the eleven Travel Doc surfaces (path + prose role + `on_operator_path`) plus the comment stripper and the two shell-region extractors; `tests/test_travel_doc_surface_gates.py` proves the cross-cutting doctrine once instead of once per originating work order. Six suites retargeted onto the map with **no test body moved**. The boundary did invert as predicted, but Phase 4 had already narrowed the assertions -- the only genuinely stale thing was the NAME `test_lab_does_not_import_production_module`, renamed `test_the_unified_module_never_loads_the_retired_one` with its assertion intact. The retired module's two native confirm calls are pinned at two rather than repaired or hidden. 279 green (was 262); twelve mutations, twelve killed, one of which exposed a real hole in a new gate. **Did NOT fold both suites into one `tests/test_travel_doc.py`** -- they guard two different modules that both still exist, and the fold would move every line number in both to produce a file whose name overclaims. Available as a mechanical follow-up if Chris wants it. |
| 6 — live smoke | ✅ **LANDED 2026-07-25 -- and this WO CLOSES here.** Live verification and docs only; **no code written at all**. Thirty-seven steps, thirty-seven green, zero defects. Interaction ran through a page-side helper resolving elements by text and structure at call time, because refs churn on every re-render inside the workspace; every persistence claim was read back from `/api/trips/{id}/tree` server-side rather than off the DOM; and dialogs, listeners, sockets, console errors and non-2xx traffic came from an instrumentation spy installed before the mount, including a `WebSocket.prototype.send` wrap so **step 28 was proved from the actual outbound `start_turn` frame** carrying `surface: "travel_doc_modal"` rather than from the on-screen label. The tab mounts the unified workspace directly -- no toggle, no retired UI, and zero rendered occurrences of *legacy*, *production Travel Doc*, *UI Lab*, *experimental*, *lab-only*, *removable* or *documenter*. Two regions and nine stops built including a three-deep substop group, edited at all four levels, reordered, insert-before/after on a top-level stop and on a substop, a cross-region move through the edit drawer, substop arrows confined to their sibling group, order surviving a full refresh. `FileList` node identity held across a scope retarget; cluster stated its whole-library caveat. **The census across three leave/re-enter cycles is the load-bearing lifecycle proof** -- read as deltas, every entry opened exactly what the previous exit closed, never more than one live channel or one live keydown listener, and the Lori socket opened exactly once in the entire run. Zero native dialogs, zero console errors, zero page errors. **The force-delete gate rendered all ten lanes with `bio_suggestions` HOT at 1** -- the Phase 3A finding reproducing live, since production's nine-lane grid would have shown that evidence nowhere while the backend refused the delete -- and arming was tested against a fifteen-case matrix rather than a happy path: case folding, prefix, suffix, one character short and one character long all refused; only the exact title, the exact id, or those with surrounding whitespace armed. The dev harness still mounts; the retired Documenter is still served and still unreachable from the shell, with all six remaining textual references inside comments. 279 tests green; both Playwright harnesses PASS (14/14, 23/23). Five findings, none a defect -- chief among them that **neither liveness harness can run on Chris's machine**, because `node_modules` does not exist in the working tree. |

**WO-TRAVEL-DOC-UNIFY-01 is CLOSED.** The post-unification backlog below is carried forward from the Phase 6 close-out; each item needs its own decision or its own work order, and **the new epic is a separate session.**

**Post-unification backlog (from the Phase 6 close-out):**

1. **`travel-doc-lab.js` -> `travel-doc.js` rename** -- pure churn against a 240K file that would bury every future diff. Parked since Phase 4; still the right call until something else forces the file to move.
2. **Delete the retired standalone Documenter** -- `ui/travel-documenter.html`, `ui/js/travel-documenter.js` and its stylesheet still exist and are still served, and Requirement 7 is met by quarantine. Deleting them is also the trigger that would make the Phase 5 test fold into `tests/test_travel_doc.py` mechanical and correct.
3. **`bio_suggestions` force-delete-from-birth** -- every trip is born with at least one bio suggestion, so every trip is force-delete-only from the moment it exists. A backend/product question, not a UI one: either the lane should not count toward `requires_force`, or the ladder is right and production's nine-lane grid was simply wrong.
4. **Selection persistence across a tab round-trip** -- leaving the tab destroys the mount, so trip and day selection do not survive re-entering. Known since Phase 2 and accepted then; still a real cost for an operator who tab-hops.
5. **Smoke-photo residue** -- narrator `e7fdb578`'s library now holds **six** disposable smoke photos (photo *links* are deleted with a trip, photos are not). **Taken as documented test rows 2026-07-26**, the second of the two options this item offered. The cleanup pass is deferred, not declined: the live database sits outside the repository at `$DATA_DIR/db/$DB_NAME` -- `/mnt/c/hornelore_data/db/hornelore.sqlite3` per `.env` -- which neither the cloud container nor the device bridge can reach, so identifying those six rows needs the running stack or a sqlite session Chris opens himself.
6. **`WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01` live smoke** -- its gate was exercised end-to-end here as part of the Travel Doc path, but that WO has never had a live smoke run against it in its own right.
7. **The post-unification epic** -- Import Provenance Foundation, Evidence Review Queue, Google Photos Picker, Google Takeout import, Lori Review Assistant, Lori Narrator Trip Story, Export Pipeline.
8. **Two person records read as the same narrator** (promoted from Phase 6 Finding 4, 2026-07-26) -- `e7fdb578` is `Christopher`, `a4b2f07a` is `Christopher Todd Horne`. Pre-existing data, untouched by the unification, and harmless while trips are created by hand. The epic changes that: Import Provenance Foundation writes provenance against a `person_id`, and Photos/Takeout import against one too, so two rows that read as one human in every picker is precisely the failure that splits an import across two narrators without erroring -- each half internally consistent, the pair silently wrong. Cheaper to settle before the first import path exists than after two of them do. Decide which record is canonical, or confirm they are two real people.

**Resolved 2026-07-26 by WO-HARNESS-DEPS-01:** both liveness harnesses now run on Chris's machine, so the harness half of the proof chain is reproducible where the code lives. The dependency was always declared in `package.json`; only the gitignored `node_modules/` was missing, and the browser cache turned out to be present already and to match Playwright 1.58.2 exactly on all five binaries, so this cost a JavaScript-only install rather than a ~500 MB browser download. Versions pinned exact against caret drift, `package-lock.json` committed, and `scripts/ui/README.md` now documents the Node toolchain and both `.js` harnesses -- which it had never mentioned. See the 2026-07-26 CLAUDE.md changelog entry.

**Blocking constraints carried forward (each already cost real debugging
once, or would):**

- **`window.confirm()` must not port.** `travel-documenter.js` lines 2131
  (region delete) and 2153 (stop delete) both call it. They must land as
  in-panel review matching the trip force-delete gate, or they regress the
  posture `WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01` established. The Lab is
  currently clean.
- **The delete gate's error envelope** is pinned at `e.body.detail`, not
  `e.body`, because FastAPI nests structured payloads under `detail`.
  ✅ **CLOSED 2026-07-25 in Phase 3A** — the pinning assertion landed in the same
  commit as the port, and `api()` now attaches `err.status`/`err.body` so there
  is a body to read. Do not let it lapse in Phase 5's test consolidation.
- **The impact grid has ten lanes, not nine.** `_TRIP_DEPENDENT_TABLES` includes
  `bio_suggestions`, which `trip_timeline_bridge.sync_trip_to_life_record`
  writes on every trip create — so **every trip is force-delete-only from
  birth**. Production's nine-lane grid renders that as all zeros next to a
  refused delete. The unified port renders all ten. Whether a self-generated
  bio suggestion should block an unforced delete is a **backend/product
  decision** and was out of Phase 3A's frontend-only scope.
- **Upload is a capability to build, not a control to port.** The Lab contained
  zero `FormData` and zero file inputs; production has three photo-upload
  scopes plus source upload. The Lab was never a complete Travel Doc because
  uploads were always somebody else's job.
  ✅ **CLOSED 2026-07-25 in Phase 3C** — all three photo scopes plus source
  upload and cluster landed, with scope resolved inside the drawer rather
  than read from the ambient selection at submit time.
- **One Lori socket, not two.** Both panels open an operator socket on
  `source_surface=travel_doc_modal`. Merged, there must be exactly one
  connection and one modal scope, with the full `modal_scope` field list
  preserved. Check for a double-connect when the Lori tab and the Lori overlay
  drawer are both reachable in the same module.
- **The role boundary holds.** Travel Documenter = operator tool. Travels shelf
  = narrator surface. The merged panel keeps the 12-test boundary gate green.

**Defect found on the way in, fix in Phase 2:** the
`WO-TRAVEL-DOC-LAB-LAUNCH-BUTTON-01` block in `hornelore1.0.html` (~3600–3617)
has **zero CSS anywhere in `ui/`** for `lvTravelDocLabBtn`, `lv-td-lab-launch`,
or `lv-td-lab-hint` — which is why it renders as plain text and could not be
found. It is deleted in Phase 4 regardless; if Phase 2 keeps it reachable, it
needs a rule.

## Travel Doc Lab finish-pass — CLOSED, live-smoked (2026-07-23)

The finish-pass ran as one batch and passed a 16-canary live smoke on the
restarted stack. **CLOSED:** native `window.prompt()` removal (in-panel drawers);
"Lori will say…" preview aligned with the backend spoken trim (OCR untrimmed);
evidence text editing (Edit → PATCH revokes approval + clears memoir); refresh of
day/public-context counts after evidence actions; context patch/delete
trip-scoping (wrong trip_id → **409** live); unbounded conv-cache cap;
`travel-documenter.js` double-send guard; **mortality/988 reply leak** (live:
mortality → no escalation/no 988, acute → still triggers + 988). **C1b**:
composed-chain test code-landed AND live WebSocket smoke passed (indirect
ideation → safety_triggered + 988 + warm reply). Live smoke also: boot clean, 0
`wrapper raised`, OCR text/textless fail-safe, both drawers, real+blocked lookup,
approval ladder, no article dump / "I can see" / coordinates.

Public-lookup supersede: CLOSED + live-smoked 2026-07-23. Fresh lookup retires
prior UNAPPROVED drafts of the same source_type (sibling of OCR supersede);
approved rows untouched, rejected-not-deleted. Live: 2nd same-URL lookup
`retired_drafts=1`, only newest draft alive, approved row survived, blocked-URL
no row, scope 409 held. "One active unapproved draft per source_type per photo"
confirmed intended.

Remaining queue (unchanged priority): `.env.example` audit → sysBubble dignity
pass → Gate 7 truth-pipeline observability → Track D measurement-first.

## Travel Doc Lab — original get-it-working batch (2026-07-23, superseded by the CLOSED block above)

Organized by **restart-need**, to kill the stop/start churn: do all FRONTEND
items first (browser reload only, no stack restart), then ONE backend batch +
ONE restart that also picks up the three already-committed-but-not-yet-live
backend fixes (mortality-988 exception, modal spoken-trim, trip days_created).

**✅ Working, live-verified (2026-07-23):** trip lifecycle (create/patch/delete +
auto-days), OCR (tesseract eng+deu+ita+hrv+slv, confidence-gated, fails safe),
public lookup (url_only, SSRF-blocked, title-clean at storage), approval ladder
(draft → approved → memoir, edit revokes), Lori modal wording (provenance, no "I
can see"/coords), capture (modal turns → trip notes, scope-tagged), day-card
generate/reconcile.

**⚙️ Off by config (not bugs — deliberate):** vision (`HORNELORE_PHOTO_VISION=0`;
operators use manual "Add draft observation" instead), trip narration
(`HORNELORE_TRIP_NARRATION=log`, dry-run — flip to `1` when ready to bank), all
command adapters empty (`OCR_CMD` / `VISION_CMD` / `LOOKUP_CMD`).

**FRONTEND-ONLY (reload, NO restart) — do freely:**

1. **Replace `window.prompt()` in the Lab evidence panel** (`travel-doc-lab.js`
   L2089 + L2104 — "Add draft observation" + "Infer place from context") with an
   in-panel text input. Violates the Lab's own locked no-native-dialog doctrine.
2. Laptop-width UX: rail-collapse persists (done); re-verify the photo gallery /
   inspector at ≤1440px after any layout change.

**BACKEND (batch → ONE restart):**

1. **Context patch/delete route trip-scoping** — `patch_photo_context` (L2464) /
   `delete_photo_context` (L2496) / `patch_public_context` (L2127) /
   `delete_public_context` (L2172) accept `context_id` alone. Single-tenant so
   not a security hole, but a stale FE cache could patch the wrong trip's row.
   Add a body/query trip_id scope check.
2. **`chat_ws._TRIP_PREV_LORI` + `_TRIP_LAST_CAPTURE` unbounded dicts** — cap or
   LRU-evict; memory-leak on a long-running process.
3. **`travel-documenter.js` modal double-send guard** — parity with the
   2026-05-07 chat-path `_loriIsBusy` fix.
4. Restart picks up these + the 3 already-committed backend fixes above.

**DEFERRED (not this pass — spec-only or gated):** vision provider wiring;
PaddleOCR / Brave / SearXNG; `WO-TRAVEL-DOC-ACCORDION-TIMELINE-01` (spec only);
`WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01` (spec only, deferred 2026-07-08);
`WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01` (TODO: timeline-bridge photo meta, cover-
photo control); `story_candidates` Path 2 (Track D).

---

**MEDIUM open items (not blocking, but named so they don't drift):**

- Context patch/delete route trip-scoping — see the Travel Doc Lab batch above.
- `chat_ws._TRIP_PREV_LORI` + `_TRIP_LAST_CAPTURE` unbounded module-level dicts (memory-leak on long-running processes).
- `travel-documenter.js` modal double-send guard (parity with the 2026-05-07 chat-path fix).
- 7 named misses in `narrative_cue_detector` eval pack (33/40 = 82.5%).
- Travel Doc Lab evidence panel — replace native `window.prompt()` for draft observation + place-from-context with an in-panel editor / drawer — see the Travel Doc Lab batch above (frontend-only).

**Older README-open items to triage (decide active / parked / superseded / closed):**

- `WO-AUDIO-NARRATOR-ONLY-01`
- `WO-STT-HANDSFREE-01A`
- `WO-MEDIA-WATCHFOLDER-01`
- `WO-MEDIA-OCR-01`
- `WO-MEDIA-ARCHIVE-CANDIDATES-01`

These sit in the historical README status text and should not stay there forever.

---

## Where things live now

```
docs/
  architecture/                      strategic ADRs + this session's brief
    HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md
    LORI-RUNTIME-ARCHITECTURE.md
    MEMORY-EXERCISE-DECISION.md
    COWORK-HANDOFF.md
  wo/                                active WO specs (build from these)
    WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md
    WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md
    WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md
    WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md
    WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md
    WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md
    superseded/
  archive/
    workorders-pre-pivot/            114 pre-pivot specs (history only)
    handoffs-pre-pivot/              pre-pivot HANDOFF / MORNING / LAPTOP / CHECKLIST docs
  reports/                           eval reports, WO completion reports, .docx history
  (existing subtrees preserved: research/, specs/, observations/, voice_models/, …)
```

Root carries operational files only: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `AGENT_CONTRACT.md`, `LICENSE`, this checklist, `.env`, `*.bat` launchers, top-level dirs (`launchers/`, `scripts/`, `server/`, `ui/`, `data/`, `docs/`, `tests/`).
