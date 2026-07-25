# WO-TRAVEL-DOC-UNIFY-01

**Status:** ACTIVE — Phase 1 LANDED 2026-07-24; Phase 1.1 (mount liveness) LANDED 2026-07-24. Phases 2–6 open.
**Lane:** Trips / operator tooling
**Parent:** `WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01` (the production panel), `WO-TRAVEL-DOC-UI-LAB-02` / `-03` (the lab being promoted), `WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01` (the delete gate that must survive the port).
**Origin:** Chris, 2026-07-24 — *"I dont want a cosmetic fix, I want one merged best of what we have on the two and do away with the lab and have it just be the travel docs."*

## Mission alignment

Travel Doc is the operator memoir-building workspace. Two divergent implementations of it means the operator's day-to-day surface is whichever one they happened to open, with day cards in one and route editing in the other. That directly cost Chris a working session on the Bismarck trip (2026-07): the trip's six `trip_days` rows existed and were correct, but the panel reachable from the shell does not render day cards at all, so the work looked lost. Consolidating to one panel serves the Mission by making the structured-legacy pipeline operable without the operator having to know which of two UIs holds which half of the feature set.

Narrator dignity is not directly implicated — this is an operator surface — but the locked role boundary is: **Travel Documenter = operator tool for editing trips. Travels shelf = narrator/Lori conversation surface. Do not mix their state.** The merge must not become a route by which operator tooling leaks into the narrator flow.

## Non-regression requirements

This WO MUST NOT:

- reduce narrator dignity
- introduce new must-not-write violations or system-tone outputs
- degrade the r5h baseline without explicit justification (no extractor-lane code is touched, so the baseline is expected byte-stable)
- expand operator surfaces into narrator UI — the merged panel stays operator-only and must keep the 12-test boundary gate green (never reference `activeTripId` / `travelsShelfOpen` / `tripStyle` / `runtime71` / `sendSystemPrompt` / `state.session`; sanctioned endpoints only)
- add detectors that duplicate existing signals
- silently drop a production affordance — see the retire list; anything not on it ports or blocks
- regress the destructive-action posture established by `WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01` (no native `window.confirm` / `window.prompt` for destructive actions)

**Tiers skipped and why (per AGENT_CONTRACT §13):** Tier 2 N/A — no extractor-lane code. Tier 3 N/A — operator surface, not narrator-facing; the role-boundary half of the check is covered under non-regression above. Tier 4 N/A — story capture untouched. Tier 5 N/A — no env flags introduced or modified.

## Goal

One Travel Doc panel in the shell tab. No standalone lab page, no launcher button, no second implementation. **The backend needs no changes at all** — both panels already talk to the same `/api/trips*` surface, so this is a pure front-end consolidation with no schema change, no migration, and no endpoint work.

## Direction: the Lab absorbs the Documenter

This is the one decision worth arguing, because it determines how much code gets rewritten.

The two files use incompatible render architectures. `travel-documenter.js` (2737 lines) builds one large HTML string in `template()`, assigns it with `hostEl.innerHTML`, then wires behaviour imperatively through `data-td` attribute lookups. `travel-doc-lab.js` (3414 lines pre-Phase-1) uses a state object with a `renderAll()` re-render loop, a `renderTab()` dispatch, DOM construction via an `el()` helper, preserved scroll position across re-renders, and a dirty-guard (`dayFormDirtyBlocks()`) that blocks navigation on unsaved edits.

Either direction rewrites the losing file at roughly equal cost. The difference is what you are left holding: porting the Lab into the Documenter's model loses the re-render loop, scroll preservation, and the dirty-guard, and lands on the older architecture. Take the other direction.

Two facts make this more tractable than the line counts suggest:

1. **The Lab was built with a socket for exactly this.** `renderCurrent()` (line 597) is not a feature — it is a placeholder reading *"Baseline lives in production. This lab does not re-implement the current Travel Doc panel,"* followed by a link out. The Lab's authors carved out a space the size and shape of the Documenter and declined to fill it. That is the merge target.
2. **The split is narrower than it looks.** The Lab owns the day/evidence working surface; the Documenter owns trip and route structure plus the delete gate. The Lab's Route Outline sidebar already renders regions and stops from `/tree` — it is simply **read-only**. So the port is "make the existing read-only route view editable and give it a board," not "invent route handling."

The Documenter's `lvTravelDocumenterMount(hostEl, opts)` contract is worth keeping as an idea — it is the right shape and the shell already calls it correctly.

## Phases

### Phase 1 — make the Lab mountable ✅ LANDED 2026-07-24

Convert `travel-doc-lab.js` from a page-level IIFE into `window.lvTravelDocMount(hostEl, opts) -> {destroy()}`. State scopes into the mount closure so two mounts cannot collide; `boot()` moves inside the mount; the `qsParams` reads for `api` and `person_id` become `opts` fields with the querystring kept as a standalone fallback. `travel-doc-lab.html` stays alive as a thin harness that calls the mount, so the dev page survives the migration.

Behaviour-neutral by construction — no markup, no CSS, no API surface, no backend change.

**Acceptance:** module exposes the mount ✓ · host comes from the caller ✓ · opts beat the querystring ✓ · no page-scope `boot()` ✓ · mounting twice and destroying one leaves the other fully functional with exactly one channel subscription ✓ (see verification below).

### Phase 1.1 — mount liveness ✅ LANDED 2026-07-24

Hardening gate between Phase 1 and Phase 2, opened by Chris's review of Phase 1: `destroy()` tore the mount down but nothing stopped an **in-flight** async callback from resolving afterwards and repainting a host the caller had already cleared. Phase 1 could not surface this because the standalone harness never unmounts; Phase 2 mounts and unmounts on tab switches, which is exactly when it bites.

Six guards, no behaviour change while a mount is alive. **Phase 2 was blocked until this landed.**

### Phase 2 — coexist in the tab behind a toggle ✅ LANDED 2026-07-25

Mount the module into `#lvTravelDocHost` alongside the Documenter, with a switch between them. One cycle of using the merged panel on real trips, with production one click away, will surface the affordances the inventory below misses. **Resist skipping this.**

Also fix the discoverability defect found on the way in: the `WO-TRAVEL-DOC-LAB-LAUNCH-BUTTON-01` launcher block in `hornelore1.0.html` (~3600–3617) has **zero CSS** — no rule for `lvTravelDocLabBtn`, `lv-td-lab-launch`, or `lv-td-lab-hint` exists anywhere in `ui/`, which is why it renders as plain text and Chris could not find it. It is deleted in Phase 4 regardless; if Phase 2 keeps it reachable, it needs a rule.

### Phase 3 — port the Documenter's features in (3A ✅ 3B ✅ 3C ✅ 3D ✅ — all LANDED 2026-07-25)

The bulk of the work. **The delete gate goes first** — it is the newest and least-exercised code in either panel and the thing most likely to be quietly broken by a port.

Everything lands in the tab currently called "Current", which should be renamed — "Trip" or "Route" reads better than "Current" once it is no longer a comparison stub.

| Production feature | Where it lands | Notes |
|---|---|---|
| Trip force-delete gate | Sidebar, selected-trip card | ✅ **Phase 3A, LANDED 2026-07-25.** Not verbatim — production's grid renders nine lanes and omits `bio_suggestions`; the port renders all ten. `e.body.detail` envelope read preserved and pinned in the same commit. |
| **Photo upload (trip / region / stop)** | Photos tab | ✅ **Phase 3C, LANDED 2026-07-25.** Built, not ported — the lab had zero `FormData` and zero file inputs. One drawer, an explicit scope selector (trip / region / stop) and a target line that names the destination in prose. All three backend endpoints already existed. |
| **Source file upload** | Sources tab | ✅ **Phase 3C, LANDED 2026-07-25.** `POST /api/trips/{id}/sources/upload` with `source_type` and an optional `title` (single file only). Intake never promotes: neither `include_in_memoir` nor `trip_day_id` is ever sent. |
| Cluster photos | Photos tab | ✅ **Phase 3C, LANDED 2026-07-25.** In-panel result, never `alert()`. Reports photos considered and links written, warns when placements land below the backend's confidence threshold, and states the honest caveat production hides: the endpoint clusters the narrator's **whole** photo library, not just this trip's. |
| Trip create / edit modal | Trip tab + sidebar "New trip" | ✅ **Phase 3B, LANDED 2026-07-25.** `+ New trip` in the rail head; edit drawer covers title, dates and summary; `days_warning`/`sync_warning` preserved. |
| Region / stop CRUD | Trip tab | ✅ **Phase 3B, LANDED 2026-07-25.** All six region fields and the full stop editor including the region selector, the eight-value `STOP_TYPES` and reparenting with subtree exclusion. Both deletes are in-panel reviews (A5 honoured). The region delete is **not verbatim**: it tries unforced first and escalates on 409, because production sends no force flag and never handles the 409, so its delete silently dead-ends. |
| Stop insert-at-position | Trip tab | ✅ **Phase 3B, LANDED 2026-07-25.** `insertContext` / `insertHint` preserved, plus a guard that discards a stale context when the drawer is retargeted to a different region or parent — production had no such check. |
| Itinerary tile board | Trip tab, main column | ✅ **Phase 3D, LANDED 2026-07-25.** Rows render in server order (a test bans client-side `.sort(` / `.reverse()` on the board path) with per-row up/down arrows that disable at the ends and while a move is in flight. Evidence badges ported at zero fetch cost. Insert-at-position was already in from 3B and is unchanged. |
| Editable Route Outline | Existing sidebar | ✅ **Phase 3D, LANDED 2026-07-25.** Rail and board now share `st.routeSel` in both directions, and the rail's region summary became selectable — previously `st.routeSel` was written in exactly one place and only ever as a stop. |
| Timeline view | Trip tab right rail | Documenter's `rightView: editor \| timeline` toggle. |
| Memoir preview | Trip tab toolbar | |
| `days_warning` / `sync_warning` banner | Global, above tabs | ✅ **Phase 3B, LANDED 2026-07-25.** `applyTripWarnings()` sets `st.tripWarning` (Trip tab) and `st.daysWarning` (day cards). The latter had been **read but never set** since the Lab was read-only — a dead banner, now wired. |
| Focus mode | Shell-level | Writes a body class; check it does not fight the Lab's rail collapse. |
| Wide editor / Quick Save / Clear | Trip tab editor | Ergonomics from `WO-TRAVEL-DOC-EDITOR-ERGONOMICS-01`. |

**Retire rather than port** (A3 — the checklist needs a closing condition):

| Control | Reason |
|---|---|
| `ping` / "Check API" | Standalone-harness diagnostic. The shell already has the Bug panel. |
| `apiBase` / `personId` inputs | Standalone-only. The shell supplies both via `opts`. |
| `loadTrips` "Load trips" | Standalone entry point; the shell mounts with a narrator already selected. |
| Output console + `clearOutput` + `statusLine` | Superseded by `st.error` and the days/sync warning banner. |
| "Baseline lives in production" banner + `prodTravelDocUrl()` | Lab-only comparison scaffolding. |
| Lab evaluation checklist panel | Lab-only. |
| "UI LAB · EXPERIMENTAL" chip | Lab-only. |

**Everything not on that list ports or blocks.**

**Phase 3 splits into scope walls.** 3A — trip force-delete gate (✅ landed). 3B — trip create/edit + region/stop CRUD, including insert-at-position, with region/stop delete landing as in-panel review rather than `window.confirm()` (A5) — ✅ landed. 3C — photo and source upload plus cluster (a capability to build, A2) — ✅ landed. 3D — the itinerary tile board, reorder, and the editable Route Outline (✅ landed). Each is its own session.

### Phase 4 — flip and delete

Make the merged module the default, then remove `ui/js/travel-documenter.js`, `ui/css/travel-documenter.css`, `ui/travel-doc-lab.html`, and the launcher block in `hornelore1.0.html`. Rename the survivors to `travel-doc.js` / `travel-doc.css`.

### Phase 5 — test consolidation

Fold `tests/test_travel_documenter_panel.py` and `tests/test_travel_doc_lab.py` into one `tests/test_travel_doc.py`. This is a rewrite, not a merge — see risks.

### Phase 6 — live smoke

Unification-critical items: shell tab mounts the unified workspace · trip create/edit · region/stop create/edit/reorder · day generate/reconcile · day edit · photo attach · **photo upload** · **source upload** · evidence approve/reject · travelogue preview · draft-stays-draft · force-delete through impact review · exactly one Lori socket across tab/overlay switching.

OCR, textless-OCR-fails-safe, public lookup on a real URL, and blocked-localhost-stores-no-row exercise the photo-evidence lane, not the merge (A6). Run them; do not let them gate unification sign-off.

## Two conventions settled up front

**Keep the `tdl-` class prefix.** The instinct is to rename to `td-` now that it is production, but the Documenter already owns `td-` (`td-root`, `td-days-warning`), so a rename collides during Phase 2 coexistence and produces a 3000-line diff that changes nothing. Rename the files, keep the prefix. It stops meaning "lab" and starts meaning nothing, which is fine.

**Scope the Lab's CSS to a root class.** The Lab is a full page today and styles `body`. Dropped into the dark shell it will restyle things it does not own. Move those rules onto `.tdl-root`, matching the `.td-root` / `body.td-standalone` scoping the Documenter already passes a line-walking test on. The light-panels-on-dark-shell look is already how the Documenter renders inside the shell, so the cream theme is not the problem — only the `body`-level reach is.

## Amendments folded in (2026-07-24 review of the ChatGPT work order)

- **A1 — Phase 1 gains an unmount (blocking).** Landed. Rationale under Phase 1 verification.
- **A2 — the Lab has no file-upload capability at all.** `travel-doc-lab.js` contains **zero** `FormData` and zero file inputs. Production has three photo-upload scopes plus source upload. The Lab's own comments confirm it punted deliberately: line 864 *"new uploads still come in via Photo Intake,"* line 1796 cluster happens *"from the production Travel Doc."* Those are the load-bearing sentences — the Lab was never a complete Travel Doc because uploads were always somebody else's job. Treat upload as building a capability, not porting a control, and move it ahead of route-board work.
- **A3 — explicit retire list.** Folded into the Phase 3 table above.
- **A4 — route editing is wider than the outline suggests.** Region fields and stop insert-at-position, folded into the Phase 3 table.
- **A5 — region/stop delete must not port as-is.** `travel-documenter.js` line **2131** (region delete) and line **2153** (stop delete) both call `window.confirm()`. These must land as in-panel review matching the trip force-delete gate. The Lab is currently clean — its only two `window.prompt` matches (2039, 2203) are comments stating the doctrine. Importing these two dialogs would regress the exact posture `WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01` established.
- **A6 — Phase 6 scope trim.** Folded into Phase 6 above.

## Risks, in order

**Silently dropping a production affordance.** The real failure mode is not a crash, it is a button that quietly stops existing and gets noticed three weeks later. The Phase 3 table is a start, not a spec — before Phase 3 begins, walk the production panel and tick every control off. Controls found by grep: Edit trip, New trip, + Region, + Stop, Delete trip, Reload, Memoir preview, Travelogue preview, Timeline, Focus, Wide editor, Quick Save, Clear, Upload photos, Cluster photos, Upload sources.

**The delete gate's error envelope.** `tests/test_travel_documenter_panel.py` pins the read at `e.body.detail` rather than `e.body`, because FastAPI nests structured error payloads under `detail`. That bug was found once already and cost real debugging. Move the pinning assertion into the merged test file **in the same commit** as the port, so the pin never lapses even briefly.

**Two Lori WebSockets becoming one.** Both panels open an operator socket with `source_surface=travel_doc_modal` — the Lab at its Lori pane (3039), the Documenter at its modal (2429). Merged, there must be exactly one connection and one modal scope, with the full `modal_scope` field list preserved. Check for a double-connect when both the Lori tab and the Lori overlay drawer are reachable in the same module.

**Test consolidation is not a merge, it is a rewrite.** `tests/test_travel_doc_lab.py` currently asserts the Lab does **not** reference the production Travel Doc module — a boundary that inverts under this WO. That assertion must be deliberately rewritten, not deleted.

## Phase 1 — what landed (2026-07-24)

**`ui/js/travel-doc-lab.js`** — the module body is now the body of `window.lvTravelDocMount(hostEl, opts) -> {destroy()}`. Every former module-level binding (`st`, `root`, `railCollapsed`, `insOpen`, `_tdlUpdateChannel`, `photoEvidence`, `lightbox`, `loriPane`) is scoped per mount. `opts.person_id` / `opts.apiBase` / `opts.person_label` take precedence, querystring kept as the standalone fallback. `root` is `hostEl || document.getElementById("tdlRoot")`. `boot()` moved inside the mount; the bare page-scope call is gone.

The body is **deliberately NOT re-indented** under the new function. Re-indenting 3,400 lines would bury a 4-hunk diff in a whitespace change and make review impossible. The mount boundary is marked by banner comments at the head and foot.

**Teardown (A1).** `destroy()` closes the BroadcastChannel, drops the Lori socket via `loriPane.reset()`, and clears the host. This is load-bearing, not cosmetic: `"hornelore-trip-updates"` is a **named** channel, so two live mounts mean two subscriptions on the same name and one cross-tab trip update fires two refreshes — a double re-render on every save in the shell, flake in tests. Every step is individually guarded and `destroy()` is idempotent, because a teardown that throws strands a caller mid-swap.

**`ui/travel-doc-lab.html`** — reduced to a thin harness that calls the mount. The handle is parked on `window` so teardown can be driven from the console.

**`tests/test_travel_doc_lab.py`** — new `MountContractTest` pins the entry point, caller-supplied host, opts-over-querystring precedence, absence of a page-scope `boot()`, and the `destroy()` handle. One assertion was deliberately **relaxed**: `test_page_loads_only_lab_assets` went from "exactly one `<script>` tag" to "exactly one `<script src=>`, and it is the lab's own." The harness needs an inline mount call, and the property that test exists to protect is *no foreign assets*, not *no inline code*. Flagging it explicitly because it is the only pin that moved outward in this phase.

### Phase 1 verification

`node --check` clean · **142 tests green** across the five suites that read the lab source (`test_travel_doc_lab` 54, `test_travel_doc_evidence_ui`, `test_travel_doc_livetest_fixes`, `test_trip_lane_fixpack_js`, `test_travel_documenter_panel`).

Mount lifecycle driven in a headless browser rather than asserted by inspection, with `BroadcastChannel` instrumented to count live subscriptions on the trip-updates name:

| step | channels open | observed |
|---|---|---|
| page load | 1 | mount is a function, handle exposes `destroy`, root rendered |
| second mount into a fresh host | 2 | second host renders independently |
| `destroy()` the second | 1 | second host cleared, **first still fully rendered** |
| `destroy()` again | 1 | no throw — idempotent |

That is Phase 1's acceptance criterion met literally.

**Not exercised:** the shell mount path (`#lvTravelDocHost`) — that is Phase 2 by design. `hornelore1.0.html` is untouched in this phase.

## Phase 1.1 — what landed (2026-07-24)

Chris's review of Phase 1: *"destroy() closes the BroadcastChannel, resets Lori, and clears the host — good. But I do not see a destroyed/mounted-alive guard that prevents pending async callbacks from rendering after destroy()."* The Lab has many async flows — `loadTrips`, trip bundle loads, evidence reloads, Lori drawer refreshes, draft preview — and any of them in flight at teardown resolves into a dead mount.

**Why six guards and not fifty-four.** There are 54 `.then(` call sites in this file. Guarding each one is unreviewable and rots on the next feature. Instead the file was surveyed for choke points, and it turns out to have exactly **one of each thing worth guarding**:

| choke point | count | guard |
|---|---|---|
| `fetch(` | 1, inside `api()` | `if (destroyed) return abandoned();` on all three arms (pre-flight, response, error-body) plus a two-arg `.then` rejection handler |
| repaint entry | 1, `renderAll()` — all 24 `render*` functions route through it | early return |
| BroadcastChannel handler | 1 | early return |
| WebSocket `onmessage` | 1 | early return, **plus socket-identity pinning** |
| timer | 1, the Lori send-retry ladder | early return |
| `document`-level listener | 1, `keydown` | early return **and unbound in `destroy()`** |

The tests pin every one of those counts. If a seventh async path ever appears, the strategy self-invalidates loudly instead of silently leaking.

**`abandoned()`** — `new Promise(function () {})`, a promise that never settles. `api()` returns it when the mount is dead so that neither `.then()` nor `.catch()` runs at any of the 54 call sites. Rejecting would fire every `.catch(e => { st.error = e.message; renderAll(); })` in the file, which is itself a write to dead state; resolving would fire every success path. Never settling is the only option that is silent.

**Socket-identity pinning** covers a case `destroyed` alone does not. `connect()` captures `var sock = this.ws` and `onmessage` bails on `destroyed || self.ws !== sock`. `loriPane.reset()` runs on every **trip switch**, not just teardown — it nulls `this.ws` while the old socket may still deliver a queued frame. Without the pin, a token from Trip A's stream appends into Trip B's transcript. That is a live-mount bug the liveness work happened to expose.

**The leak the review did not name.** `document.addEventListener("keydown", ...)` is the only listener bound outside the host, so clearing the host does not remove it. Two mounts meant two live listeners on `document`, and after `destroy()` an arrow key still drove `lightboxStep()` -> `renderAll()`. The handler is now named `onDocKeydown` and `destroy()` unbinds it.

`destroy()` sets `destroyed = true` **first**, before any teardown step, because each step can run script that re-enters the module. Closing the door and then flipping the sign leaves a window open. It remains idempotent and every step remains individually guarded.

### Phase 1.1 verification

`node --check` clean - **154 tests green** across the same five suites (was 142; `test_travel_doc_lab` gained 12).

Static pins (`MountLivenessTest`) check the *shape* of the guards. They cannot watch a stale callback land on a dead host, so that is proved in a real browser by `scripts/ui/run_travel_doc_mount_liveness.js` — no backend, no manual server, no arguments, exits 0/1.

Its method matters: `window.fetch` is replaced with one that **parks** every request and never settles until the test releases it. With fetch parked, `boot()` paints nothing at all, because `renderAll()` lives inside the `.then()`. So "host is empty" is the identical starting state for every row, and the only difference between them is whether the mount was destroyed before the release.

| scenario | destroyed first | released as | host mutations | children |
|---|---|---|---|---|
| `control_live` | no | 200 OK | **3** | **1** |
| `destroyed_then` | yes | 200 OK | 0 | 0 |
| `destroyed_notok` | yes | 500 + error body | 0 | 0 |
| `destroyed_reject` | yes | network rejection | 0 | 0 |

`control_live` is the load-bearing row. Without it, three "nothing happened" results prove nothing — a harness that never delivers a callback also produces three empty hosts.

| census | two mounts | after first destroy | after second |
|---|---|---|---|
| `hornelore-trip-updates` subscriptions | 2 | 1 | 0 |
| `document` keydown registrations | 2 | 1 | 0 |

Both censuses count bind/unbind rather than observing effects, deliberately: the keydown handler early-returns unless a lightbox is open, so an "assert no repaint on keypress" test would pass with the listener still bound — vacuously. Counting cannot go vacuous. Zero unhandled rejections, zero page errors, `destroy()` still idempotent.

**Negative controls run by hand, both confirmed red:**

1. `destroy()` changed to set `destroyed = false` -> all three destroyed rows flipped to 3 mutations / 1 child. The reviewer's reported bug, reproduced exactly.
2. `destroy()`'s `removeEventListener` line deleted -> keydown census went 2 -> 2 -> 2 instead of 2 -> 1 -> 0.

A green suite that cannot go red is decoration. Re-run both by hand if the guards change.

**Not exercised:** the shell mount path, still. No backend change, no shell change, `hornelore1.0.html` untouched.

## Phase 2 — what landed (2026-07-25)

Front-end only. No backend, no API, no schema, no flag, no route-editing port,
no upload/cluster port, no delete-gate port; `travel-documenter.js` still
present and still reachable.

**The shape.** The Travel Doc tab now hosts two divs, `#lvTravelDocUnifiedHost`
(the mountable workspace) and `#lvTravelDocHost` (the legacy Documenter), and a
two-button surface switch above them. `_lvTravelDocSurface()` resolves the
active surface from `localStorage["lvTravelDocSurface"]`, defaulting anything
that is not the literal `"legacy"` to `"unified"` — a corrupt or absent value
must land on the default path, never on the fallback. `lvShellShowTab`
destroys the surface it is not showing before it mounts the one it is, and
leaving the tab tears down both.

**Exactly one mount, ever, is a correctness rule and not a tidiness one.** Each
surface owns a `hornelore-trip-updates` BroadcastChannel subscription, a
`document`-level keydown listener and a Lori `/api/chat/ws` socket. Two live
mounts double all three, and the two keydown handlers both answer Escape.

**Two pre-existing leaks closed on the way through.** The shell already called
`lvTravelDocumenterMount()` and threw the returned handle away, so every
narrator switch leaked that surface's keydown listener and its modal-Lori
socket; Phase 2 keeps the handle and calls `destroy()`. Separately,
`travel-documenter.js` opened its trip-update BroadcastChannel at mount and
never closed it — tolerable while the shell mounted it once per narrator,
not once Phase 2 destroys and remounts on every tab exit, narrator switch and
surface toggle. `destroy()` now closes it. Touching the Documenter is inside
the Phase 2 wall: the non-goal is *do not remove it yet*, not *do not touch it*.

**CSS scoping — Chris's named risk.** `travel-doc-lab.css` was standalone-page
styling: `:root` custom properties and bare element rules under `.tdl-body`.
The 16 `--tdl-*` properties moved from `:root` to `.tdl-root`, and the element
resets were rescoped beneath it. Custom-property inheritance is DOM-based, not
layout-based, so the module's three `position: fixed` overlays
(`.tdl-drawer-scrim`, `.tdl-drawer`, `.tdl-lightbox`) still resolve their
variables through the host and were deliberately left alone. `lvTravelDocMount()`
adds `.tdl-root` / `.tdl-root-embedded` to the host and `destroy()` takes them
back off, so the stylesheet is inert in the shell until something is mounted.
The `tdl-` prefix is unchanged, per the settled convention above.

**The Lab framing is gone from the operator path.** The
`WO-TRAVEL-DOC-LAB-LAUNCH-BUTTON-01` block — the unstyled "🧪 Open Travel Doc
UI Lab" button that opened a second browser tab — is deleted, replaced by the
surface switch. The module gates its own Lab furniture on `opts.embedded`: the
"UI Lab · experimental" badge and the eval checklist are not rendered, the
picker reads "Travel Doc", and `?person_id=` / `?api=` are quarantined to the
standalone page so shell identity comes from `opts` and never from the shell
URL's querystring. `ui/travel-doc-lab.html` is untouched and still works.

### Phase 2 verification

`node --check` clean on `app.js`, `travel-doc-lab.js`, `travel-documenter.js`
and both inline script blocks of `hornelore1.0.html`. **192 tests green** —
the five existing lab-reading suites plus `tests/test_travel_doc_shell_mount.py`
(38 new: shell load, mount contract, one-surface-ever, default surface, CSS
scoping, no native dialogs, standalone still works).

Static tests pin shape and cannot watch a census, so the behaviour is proved in
a real browser by `scripts/ui/run_travel_doc_shell_mount_liveness.js` — a second
headless script that loads the **real** `hornelore1.0.html`, parks every
`fetch`, and drives `lvShellShowTab` / `lvTravelDocSetSurface` the way an
operator would. Nine rows (`open_unified`, `leave_tab`, `reenter_tab`,
`switch_to_legacy`, `switch_to_unified`, `narrator_switch`, `lori_open`,
`lori_then_leave`, `lori_then_reenter`) plus a destroyed-repaint scenario and a
branding scan; **22 checks, PASS**, zero unhandled rejections, zero page errors.

**Three defects the script caught that the static tests could not:**

1. `function _lvTravelDocSurface()` cached its result on
   `window._lvTravelDocSurface`. `app.js` is a classic script with no IIFE, so
   that identifier **is** the function — the first call overwrote itself with
   the string `"unified"` and the second died with *"_lvTravelDocSurface is not
   a function"*. The cache moved to `window._lvTravelDocActiveSurface`, and a
   new test now fails on any `window.foo = …` in `app.js` that shadows a
   top-level `function foo()`.
2. The socket census tested the URL for `/travel_doc/`. Both modules dial
   `apiBase + "/api/chat/ws"`, so that regex matched nothing and every `ws`
   assertion in the script was decoration. Attribution is now by call stack.
3. The destroyed-repaint observer was installed **before** the navigation, so
   it counted `destroy()`'s own legitimate cleanup as a repaint. The window
   narrowed to after teardown, with a separate `tornDown` assertion keeping the
   cleanup itself under test.

**Negative controls, actually run (results in the script header).** Deleting
the tab-exit `lvTravelDocTeardownAll()` call turns 5 checks red. Deleting
*both* toggle guards turns 5 red with the census at 2/2 and both hosts painted —
the exact defect Chris named as the top risk. Deleting *either* toggle guard
alone still passes: **the two are mutually redundant**, each the other's
backstop, and a green run should not be read as proof that both are
load-bearing. Reverting the socket attribution turns the non-vacuity guard red.

**Known behaviour change:** leaving the Travel Doc tab now destroys the mount,
so trip/day selection does not survive a tab round-trip. That is a deliberate
reading of the acceptance line *"Switching away/remounting calls destroy()"* —
a hidden panel is `display:none`, not unloaded, and the alternative is leaving
a socket and a `document` keydown listener live underneath whatever tab the
operator is actually looking at. If the round-trip cost is not worth it, the
fix is to persist selection in `opts`, not to stop destroying.

## Phase 3A — what landed (2026-07-25)

Front-end only. No backend, no API, no schema, no flag. No route board, no
upload, no cluster, no region/stop CRUD, no theme pass. `travel-documenter.js`
is untouched and the legacy surface is still reachable.

**The shape.** The selected-trip card in the unified sidebar carries a
`tdl-btn-danger` "Delete trip" control. It attempts an unforced
`DELETE /api/trips/{id}` first. A **409** puts the structured impact payload
into `st.deleteReview`, and `renderAll()` appends `renderDeleteTripReview()` —
an in-panel review, consistent with the drawer idiom the rest of the module
already uses. Force delete re-sends with `{force: true, confirm_trip_id,
reason}`. After a successful delete the trip list reloads with
`noAutoSelect`, so the operator lands on "Select a trip from the left rail."
rather than being silently dropped onto a neighbouring trip.

**A prerequisite the port could not have worked without.** The module's single
`api()` choke point discarded the response body on a non-OK status, so there
was no impact payload to read. The error arm now attaches `err.status` and
`err.body`, and the gate reads **`e.body.detail`** — FastAPI nests structured
payloads under `detail`, and the pinning assertion landed in the same commit as
the port, exactly as the risks section demanded.

**No native dialogs.** All eight textual `confirm`/`prompt` matches in the file
are inside comments. Arming is a text input compared against the exact trip
title *or* the trip id; the drawer holds live DOM references in closures and
reads `.value` on submit, so typing never triggers a repaint — verified live
across 27 real keystrokes with focus retained. Handlers are assigned by
property (`input.oninput = fn`), never `addEventListener`, so reopening the
review for a different trip cannot stack a stale closure.

**The port is deliberately not verbatim.** `travel-documenter.js` renders
**nine** impact lanes and never mentions `bio_suggestions` anywhere in the
file. `trip_repository._TRIP_DEPENDENT_TABLES` has **ten**, and
`trip_timeline_bridge.sync_trip_to_life_record` writes one `travel.trip` bio
suggestion on **every trip create**. So every trip is force-delete-only from
birth, and in production the operator sees an all-zero impact grid beside a
delete the backend refuses. This was proved live, not inferred: a disposable
trip created with no dates, no regions and no notes returned 409 with every
lane zero except `1 Bio suggestions`. The unified port renders all ten lanes.
Whether a self-generated bio suggestion should block an *unforced* delete is a
backend/product decision and was outside this phase's frontend-only wall.

**Three blanket "the lab never DELETEs" test guards were narrowed, not
deleted.** The file-wide form stopped being true the moment the phase ported
one sanctioned destructive control, but deleting the tests would have retired
the properties they were really protecting. They now assert that every DELETE
targets `/api/trips/` plus a trip id and none targets an evidence lane
(evidence is hide-only — PATCH, never DELETE), and that the reconcile drawer
and its loader contain no DELETE at all (reconcile *reviews* missing and
outside-date days; it never silently cleans them up).

### Phase 3A verification

`node --check` clean on `travel-doc-lab.js`. **205 tests green** (was 192),
including a new `TripForceDeleteGateTest` covering all ten of Chris's stated
gates: the control exists, normal delete is attempted first, a 409 opens the
in-panel review, the read is `e.body.detail`, counts render, wrong text blocks
force delete, the exact title or id enables it, the list refreshes and the
selection clears, no native dialog appears in the flow, and the legacy fallback
stays reachable.

Live smoke on the running stack, all ten steps green: DELETE with no body →
409 → drawer opens with all ten counts · a case-mismatched title leaves the
button disabled and fires no request · the exact trip id arms · the exact title
arms · force delete sends `{"force":true,"confirm_trip_id":"…","reason":"…"}`
→ 200 · the trip disappears from both the server and the rail · nothing is
auto-selected · exactly one mount at every point · legacy fallback round-trips
cleanly · zero console errors.

## Phase 3B — what landed (2026-07-25)

Trip create/edit and region/stop CRUD, in Chris's stated order: the empty-state
copy bug first, then trip create/edit, then region CRUD, then stop CRUD, with
insert-at-position preserved and the legacy fallback still reachable. Front-end
only — no backend, no API, no schema, no flag change. `server/code/api/routers/trips.py`
was read and needed nothing: every endpoint this phase calls already exists.

**Shape.** Six new `st` fields (`tripEditor`, `regionEditor`, `stopEditor`,
`routeDelete`, `insertContext`, `tripWarning`) drive four editor drawers and one
delete-review ladder. The placeholder `renderCurrent()` becomes `renderTripTab()`
plus a route board; the tab is renamed `current` → `trip` behind a `setTab`
back-compat shim. New helpers: `notifyTripUpdated`, `allStops`, `locateStop`,
`subtreeIds`, `regionStopCount`, `regionLabel`, `stopLabel`, `dateRangeWarning`,
`refreshTripBundle`, `refreshTripsPreservingSelection`, `applyTripWarnings`.
The CSS added is **structural only** — every colour reuses an existing `--tdl-*`
variable, because the theme item is retired at Chris's instruction, not deferred.

**Three deliberate non-verbatim ports**, all banner-documented at the head of
`travel-doc-lab.js`. The load-bearing one is the region delete. `DELETE
/api/trips/regions/{id}` returns **409** when the region still holds stops unless
the caller sends a force flag. Production's `deleteRegion` sends no flag and has
no 409 arm, so once the operator answers `window.confirm()` the request
dead-ends and nothing is deleted, silently. The port tries unforced first; on
409 it opens a second review stage that quotes the server's own refusal verbatim
next to the lab's independent count from the loaded tree, and escalates the
button to name the blast radius.

**Insert-at-position** keeps production's `insertContext` / `insertHint`
meaning and adds a guard production lacks:

```js
var useCtx = (ctx && regionId === ctx.region_id &&
              parentId === (ctx.parent_stop_id || null)) ? ctx : null;
```

so retargeting the drawer to a different region or parent drops the stale
context instead of inserting in the wrong place.

**No native dialogs, by construction and by measurement.** The delete executor
is named `deleteStopReviewed` rather than `deleteStopConfirmed`, because the
source scanner strips comments but bans the native-dialog call substrings in
code. At runtime a spy wrapping all three functions recorded zero hits across
every destructive flow.

### Phase 3B verification

`node --check` clean on `travel-doc-lab.js`, `ast.parse` clean on both test
files, CSS braces 332/332, `CR: 0` on all four files on both sides of the
transfer. **220 tests green** (was 205) across the six suites Phase 3A counted,
plus a 55-test adjacent sweep green. The new `TripRegionStopCrudTest` adds
fifteen gates; its `_fn` helper slices the **actual** function body rather than a
fixed-width window, so a gate cannot pass on text belonging to the next
function. Test 9's DELETE allow-list widened from one sanctioned shape to three
(`/api/trips/`, `/api/trips/regions/`, `/api/trips/stops/`) — narrowed, not
dropped: evidence lanes remain hide-only.

Live smoke on the running stack, all thirteen of Chris's steps green: the
workspace opens with exactly one `.tdl-root` and zero `.td-root` · the
empty-state copy fix is live · trip created (10 day cards) with the title typed
across 19 real keystrokes, focus retained · trip edited, rail row and card both
refreshed · `+ Stop` correctly disabled at zero regions · region created with all
six fields, soft out-of-range date warning firing and clearing · region edited
including a summary cleared to empty (`clear_summary` path confirmed by
reopening the drawer) · stop created, edited, reparented (36px → 54px indent) and
moved across regions, with subtree exclusion holding · stop delete review
in-panel, children-promoted copy verified · empty region deleted unforced ·
non-empty region opened stage 2 and destroyed nothing at stage 1, then cascaded
correctly when confirmed · disposable trips removed through the Phase 3A
force-delete gate · legacy fallback toggled out and back · zero console errors.

**The mount/socket/listener census is functional, not visual.** Counting
`.tdl-root` proves only the DOM; a leaked subscription is invisible there. So the
census wraps `WebSocket` and `BroadcastChannel` and drives a full legacy round
trip with the Lori pane open — 1 socket created / 1 closed / 1 live, channels 6
created / 5 closed / 1 live, one mount throughout — and then posts a single
trip-saved message on the named channel and counts the reload: **all eight
bundle endpoints fetched exactly once**, which would read 2 if the toggle had
leaked a second mount. The first attempt at that probe returned zero fetches and
proved nothing, because the handler correctly ignores a trip id that is not the
open trip; a probe that cannot fail is decoration, so it was rerun against a
real selected trip.

**Backlog, unchanged by this phase:** whether a self-generated `travel.trip` bio
suggestion should block an unforced trip delete is a backend/product call and
stays outside the frontend wall. Selection still does not survive a tab
round-trip — the fix is to pass saved state into `lvTravelDocMount()`, not to
keep a hidden mount alive.

## Phase 3C — what landed (2026-07-25)

Photo upload, source upload and photo clustering, so the unified workspace can
now do intake and the legacy Documenter is no longer needed to get material into
a trip. Front-end only — **no backend, no API, no schema, no flag change**.
`server/code/api/routers/trips.py` was read first and needed nothing: all five
endpoints this phase calls already exist.

**The load-bearing constraint is not a backend one — it is `FileList`.** An
`<input type="file">` holds a `FileList` that script cannot write. That makes
Phase 3B's problem worse rather than similar: a lost text cursor can be
restored, a lost file selection cannot. So the upload drawer must not repaint
between "choose files" and "Upload", and it doesn't — the scope target line
swaps its own `textContent`, the file hint counts in place, the title field
enables and disables itself, and the submit button toggles its own `disabled`.
There is no `renderAll()` anywhere inside either `onchange` handler, and a test
pins that absence.

**Shape.** Three new `st` fields — `uploadDrawer`, `photoIntake`, `sourceIntake`
— plus an intake module of roughly four hundred lines: `parseScopeKey`,
`scopeChoices`, `defaultScopeKey`, `openUploadDrawer`, `renderUploadDrawer`,
`photoUploadPath`, `uploadPhotoFiles`, `uploadSourceFiles`, `runClusterPhotos`,
`renderIntakeResult`, `renderPhotoIntakeBar`, `renderSourceIntakeBar`. All three
fields clear in `selectTrip()` and in `afterTripDeleted()`, for the same reason
the Phase 3B editors do: an intake result describes a trip the operator may no
longer be looking at.

**`api()` grew a `FormData` branch.** The file has exactly one `fetch(`, and it
stringified every body and hand-set `Content-Type: application/json`. A
`FormData` must go out untouched and *without* a hand-set content type, because
the browser has to write that header itself in order to append the multipart
boundary — and `JSON.stringify(new FormData())` yields `"[object FormData]"`.
The branch sits ahead of the JSON branch, and a test asserts that ordering
rather than merely asserting both exist.

**Scope is explicit, never ambient — this is a deliberate divergence from
production.** Production's `uploadSourceFiles` reads `editorScope()` at submit
time, so retargeting the workspace between choosing a file and pressing Upload
silently moves the destination. The port instead resolves a scope key inside the
drawer. `defaultScopeKey()` is the only function permitted to read `st.routeSel`;
the four upload functions never do, and a test asserts that. The target line
spells the destination out — *"Target: the stop “Smoke Stop Alpha” in Smoke
Region North."* — so a wrong scope is visible before the request, not after.

**Intake is not approval.** Nothing here touches the OCR / public-lookup /
caption / observation ladder. No `include_in_memoir` and no `trip_day_id` is
ever sent on a source upload; day attach stays its own separate act on the Trip
Plan tab. Evidence lanes stay hide-only — no new DELETE was added, and the
existing allow-list tests still hold. Uploads are stamped
`uploaded_by_user_id = "travel_doc_unified"` so intake from this surface is
identifiable after the fact; the backend gives special meaning only to
`uploaded_from_surface == "travels_shelf"`, which this surface deliberately does
not claim.

### Phase 3C verification

`node --check` clean on `travel-doc-lab.js`, `ast.parse` clean on all four test
files, CSS braces 344/344, `CR: 0` on all six files on both sides of the
transfer. **236 tests green** (was 220) across the six suites Phase 3B counted,
plus a 306-test adjacent sweep green.

The sixteen new gates in `TripIntakeUploadClusterTest` were **mutation-tested
rather than trusted**: all sixteen passed on the first run, which is suspicious,
so the tree was copied aside and four defects introduced — the `FormData` branch
disabled, `uploadPhotoFiles` made to re-read the ambient selection, a
`renderAll()` added inside `files.onchange`, and `include_in_memoir` appended to
the source form. Each was caught by exactly its intended gate and by no other.

**A same-scope bug found and fixed: three test suites had gone blind.** Phase
3C's code contains `files.accept = "image/*"`. Three suites
(`test_travel_doc_evidence_ui`, `test_travel_doc_livetest_fixes`,
`test_trip_lane_fixpack_js`) stripped comments with the naive regex
`/\*[\s\S]*?\*/|//[^\n]*`, which does not know about string literals — so that
`/*` opened a phantom block comment that swallowed hundreds of lines down to the
next real `*/`, and three tests failed with one erroring on a `substring not
found`. The repo already had a string-aware stripper,
`tests/source_scan_helpers.strip_js_comments`, added under
`WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01` Phase 6.4 for exactly this
class of bug, but never applied to these three files. They now use it. The
assertions were **not** loosened and `image/*` was **not** avoided: the tests
were blind, not wrong. This is why the stripper migration lands as its own
commit **before** the Phase 3C code — the Phase 3C code is what makes the naive
stripper fail, so committing them in the other order would leave one red commit
on main.

Live smoke on the running stack, every one of Chris's twelve steps green:
disposable trip created · region and stop added · photos uploaded at **all
three** scopes, not just one — stop (`/api/trips/stops/{id}/photos`), trip
(`/api/trips/{id}/photos`) and region
(`/api/trips/{id}/regions/{id}/photos`), each hitting its own endpoint · the
Photos tab count climbing 0 → 2 → 3 → 4 with the thumbnails rendering · a photo
attached to Day 1 through the existing day-attach picker, which offered all four
uploads · a source uploaded at stop scope with type `itinerary` and a title ·
Sources climbing 0 → 1 · cluster run in-panel · counts refreshed · no
auto-promotion · the trip removed through the Phase 3A force-delete gate · and
the mount census clean.

Three things the smoke proved that a static test could not. **The `FileList`
survives retargeting**: with two files chosen, changing the scope select from
trip to stop left the file input node *identically the same object*, both files
still selected, and only the target line's text changed. **The panel reports
honestly rather than optimistically**: a byte-identical duplicate uploaded to a
second scope came back *"Ingested: 0."* because the backend deduplicates on
hash, and re-running with a genuinely new file gave *"Ingested: 1."* and moved
the count — the first result was correct, not a failure, and the panel said so.
And **no-auto-promotion was verified server-side, not by reading the UI**: the
uploaded source row carries `include_in_memoir = 0`, `trip_day_id = null`, its
title and `source_type` preserved, and both `trip_region_id` and `trip_stop_id`
set, which is the stop-scope path correctly deriving the parent region.

Cluster reported 4 photos considered and 4 links written, all below the
confidence threshold, and the counts did not move — correct, because the smoke
images were synthetic and carry no EXIF timestamps, and the panel's warning says
exactly that. A spy wrapping the three native dialog functions recorded **zero
hits** across the entire run: three uploads, a day attach, two clusters, a
dismiss, and the force delete.

The mount census was rerun functionally: on legacy exactly one `.td-root` and
zero `.tdl-root`, back on unified exactly one `.tdl-root` and zero `.td-root`,
channels 2 created / 1 closed / **1 live**, sockets balanced. The standalone
`ui/travel-doc-lab.html` still mounts with exactly one `.tdl-root`.

**One honest residue, reported not hidden.** Photos belong to the narrator's
library, not to a trip, so the four disposable smoke images survived the trip
force-delete and are still in narrator `e7fdb578`'s library. They are
identifiable precisely because of the stamp this phase added — every one carries
`uploaded_by_user_id = "travel_doc_unified"`. They were **not** deleted here:
photo deletion is outside this phase's wall and the doctrine is hide-only.

## Phase 3D — what landed (2026-07-25)

Route order and route-row ergonomics, so the legacy Documenter no longer holds a
workflow advantage on the one surface where it still had one. Front-end only —
**no backend, no API, no schema, no flag change**. `trips.py` was read first and
needed nothing: all three reorder/move endpoints already exist and validate
strictly.

**The gap list.** Production's route board was reviewed against the unified
workspace and had exactly four affordances the port did not: region reorder,
stop reorder, evidence badges on route rows, and a selectable region row. All
four are now in and **nothing was retired**. Production has no drag-and-drop on
either tile — grep-verified, not assumed — so nothing was copied that does not
exist.

**The load-bearing decision: a stop move sends two ids, not a permutation.**
Production's stop reorder builds the whole sibling list and posts it to
`POST /api/trips/{id}/stops/reorder`, which 400s unless that list is *exactly*
the current sibling group. Such a request is precisely as stale as the tree it
was built from, so any concurrent insert or delete turns a move the operator can
see is legal into a refusal they cannot explain. The port instead calls
`POST /api/trips/{id}/stops/{stop_id}/move` with `before_stop_id` /
`after_stop_id` and lets the backend re-derive the sibling group from two ids
that are still true. This is a deliberate divergence, and it satisfies Chris's
test line *"stop reorder before/after works through existing API shape"* —
`/move` **is** the existing shape, and it is the endpoint production already
uses for cross-region moves. A test bans both `ordered_ids` and `/stops/reorder`
inside `moveStopRelative` so the permutation cannot creep back in later.

**A reorder must never quietly reparent.** `moveStopRelative` echoes `region_id`
and `parent_trip_stop_id` back unchanged, so a substop moves among its own
siblings and only there. That is the one way an up/down arrow could destroy a
branch the operator was never shown, and two tests pin it.

**Regions still send a permutation, because there is no other door.**
`POST /api/trips/{id}/regions/reorder` is the only region-order endpoint and it
demands a full permutation, so the staleness above is unavoidable there. The
port handles it the way Phase 3B handled the region-delete 409: the refusal is
surfaced in-panel, next to the rows it is about, and the trip bundle is reloaded
so the operator's next attempt is built from a fresh tree. It does not dead-end,
and it never reaches for a native dialog.

**Two new `st` fields.** `routeBusy` holds the id of the row whose move is in
flight and disables every arrow on the board while it is set — two interleaved
reorders are each built from the tree as it looked before the other one landed.
`routeError` is the in-board failure surface; a refused move has to be readable
next to the rows it concerns. Both clear in `selectTrip()`, in
`afterTripDeleted()` and in `afterRouteDeleted()`, for the same reason the 3B
editors and the 3C intake fields do: a move in flight against a row that is
being deleted is a dangling handle of the same kind.

**Row selection revived a branch that could never fire.** Phase 3C's
`defaultScopeKey()` has a region arm, but `st.routeSel` was written in exactly
one place and only ever as a stop — so the upload drawer could default to a
region that nothing on the surface was able to select. Route rows are now
selectable for regions as well as stops, on both the board and the rail, and the
arm is live. The row body became a `<button>` so selection works from the
keyboard as well as the pointer, which is why the first new CSS rule exists: it
strips the browser button skin back to the `div` it replaced.

**Evidence badges cost nothing.** `st.notes`, `st.sources` and `st.photoLinks`
already carry `trip_region_id` / `trip_stop_id`, so the badges are a filter over
state the bundle has already fetched. A test asserts there is no `api(` call
anywhere on the badge path.

### Phase 3D verification

`node --check` clean on `travel-doc-lab.js`, `ast.parse` clean on the test
files, `CR: 0` on all four files on both sides of the transfer. **255 tests
green** (was 236) across the same six suites Phase 3C counted, in the container
and on the device.

The nineteen new gates in `RouteOrderBoardTest` were **mutation-tested rather
than trusted**: nineteen mutants, nineteen killed, each by its intended gate.
Seventeen of them existed before the live smoke. The last two were written
*because* of it, and the reason is the next section.
One mutant exposed a flaw in the harness rather than in the code — the anchor
`parent_trip_stop_id: parentId,` occurs twice (the 3B stop-editor drawer and the
new mover), and the harness correctly refused to mutate an ambiguous anchor
instead of silently patching the wrong one; re-run with a two-line unique
anchor, it was killed. One test also had to be rewritten after it passed: the
CSS check originally sliced from the first Phase 3D class name to end-of-file,
which swept in every later block and made the no-new-colour assertion about
somebody else's code. It is now line-based over the six Phase 3D class names.

**A pre-existing red, found here and red since Phase 2.** The device's six-suite
run came back `FAILED (failures=1)` while the container's came back OK. The
cause was not this phase. Phase 2 commit `e9b792c` widened the
`lv80SwitchPerson` block in `ui/hornelore1.0.html`, but the matching widening of
the 1200-character regex window in `tests/test_travel_documenter_panel.py` never
got committed — so on the device that window truncated before the
`lvShellShowTab("traveldoc")` assertion. The device's real baseline had been
**235/236 since Phase 2**, and container-only test runs had been masking it. An
md5 comparison of eight files confirmed this was the *only* container/device
divergence. The repair ships as its **own commit**, separate from Phase 3D,
because it is a Phase 2 test-sync fix and not this phase's work.

### Phase 3D live smoke - and the bug that nineteen tests could not see

**The smoke ran, and it earned its place in the gate list.** The very first
arrow press on the running stack failed. Region WEST's up arrow put this into
the board's own error strip:

    POST /api/trips/{id}/regions/reorder -> 422
    [{"type":"model_attributes_type","loc":["body"],
      "msg":"Input should be a valid dictionary or object to extract fields from",
      "input":"{\"ordered_ids\":[...]}"}]

**Every arrow press on the board was broken, on regions and on stops both.** The
cause is a convention this file has and never stated: `api()` owns the request
encoding. It stringifies `opts.body` itself, in the branch that sits after the
`FormData` check, so a call site must hand it a **raw object**. Both Phase 3D
movers were written as `body: JSON.stringify({...})`, which double-encoded the
request into a JSON *string*, and the backend answered 422 on every press.

Two things about how this got through are worth recording. First, **no
source-scanning test could have caught it**, because both spellings look equally
plausible read in isolation - the defect lives in the relationship between the
call site and `api()`, not inside either one, and seventeen gates plus seventeen
mutants had just passed over it. Second, **the convention was already
unanimous**: every other call site in a 5,500-line file passes a raw object, so
the two new movers were the only offenders in the whole file. That is precisely
the shape of defect a live smoke exists to catch, and it is the argument for
keeping the smoke a gate rather than a formality.

The fix is a raw object at both call sites plus two new gates. The first bans
`body: JSON.stringify` **file-wide** while asserting that the encoding still
happens exactly once inside `api()` - without that positive half, deleting it
from both ends would pass. The second pins that the two movers still send a body
at all and still leave the encoding to `api()`, since the file-wide ban alone
would also be satisfied by a mover that stopped posting anything. Both were
mutation-tested: reintroducing each `JSON.stringify` gave `FAILED (failures=2)`,
restoring gave OK.

**The failure surface itself behaved exactly as designed**, which is worth
crediting rather than glossing: in-panel, next to the rows it was about, quoting
the server verbatim, with a Dismiss control, no native dialog, and a bundle
reload that left the board consistent afterwards. An operator hitting this would
have been able to report it precisely.

**After the fix, every one of Chris's eleven live-smoke steps is green.** All
tree assertions below were read server-side from `/api/trips/{id}/tree` rather
than off the DOM, so the board is being checked against the database and not
against itself.

- **Disposable trip, three regions, seven stops.** Chris's line said two
  regions; a third was added so that a middle region exists with both arrows
  enabled.
- **Region reorder both directions.** WEST up gave `NORTH | WEST | SOUTH`; WEST
  down put it back.
- **Stop reorder both directions, and the substops travelled with their
  parent.** Moving N-Alpha never detached its children, so a reorder did not
  quietly reparent.
- **Substop reorder inside its own sibling group**, sub2 up giving
  `N-Alpha(N-Alpha-sub2, N-Alpha-sub)`.
- **Arrow end-disable is per sibling group, not per screen row.** The last
  substop's down arrow is disabled even though a top-level stop sits visually
  below it, because that stop is not its sibling. A forced click on a disabled
  arrow is a genuine no-op: the tree before and after was byte-identical, with
  no error and no dialog - the substop could not be lifted out of its group.
- **Insert before and insert after**, on a top-level stop and on a substop. The
  hint reads *"Inserting before N-Bravo"*, and for a child
  *"Inserting before N-Alpha-sub (as a child stop)"* with the parent select
  pre-set to N-Alpha. `insertContext` / `insertHint` are intact, and an insert
  taken relative to a substop lands in the child sibling group rather than at
  top level.
- **Move a stop between regions** through the stop editor's region select:
  N-Bravo went from NORTH to WEST and the server tree agreed.
- **Unsafe moves stay blocked at both layers.** The parent select for a stop
  with children offers `Top level` and its non-descendants only; its own subtree
  is absent. Forcing it past the UI with a direct API call returned **400
  `move would create a cycle (parent is a descendant of this stop)`**.
- **Displayed order survives a refresh.** After a full page reload and remount,
  the twelve board rows came back in exactly the pre-reload sequence and matched
  the server tree depth-first.
- **Counts still refresh.** The trip header read `3 regions - 9 stops` and the
  region row `7 stops`, both having tracked the inserts; the Trip Plan tab's ten
  day cards each render their photo / note / source / context counts.
- **Both Phase 3B delete ladders still pass.** The stop ladder opened in-panel
  with its "loses the stop link" copy and deleted cleanly. The region ladder on
  a non-empty region tried unforced first, was refused, and escalated to a
  second rung quoting the server verbatim and naming the blast radius
  (*"Delete region and its 1 stop"*). **Nothing was destroyed at rung one**; the
  cascade landed only after the second.
- **The Phase 3C upload drawer still preserves file selection.** Retargeting the
  scope select from trip to a stop left the file input node the *identically
  same object*, still in the document. That node identity is the whole reason a
  `FileList` survives, and the route work did not disturb it. The scope list had
  also picked up every stop added during the smoke, including the inserted ones.
- **The Phase 3A force-delete gate is unchanged and still arms strictly.** Empty
  field: disabled. `P3D SMOKE` against a title of `P3D SMOKE - disposable`:
  still disabled. Exact title: armed. Force delete returned the trip to a server
  404 and the rail to its empty state.
- **No duplicate mount, socket or listener.** Three full legacy round trips left
  exactly one `.tdl-root`, zero `.td-root`, one host and **zero new WebSockets**.
  The legacy fallback is still reachable, as Chris's scope requires.
- **Zero native dialogs and zero console errors** across the entire run, the spy
  reading empty at every checkpoint.

## Phase 4 — what landed (2026-07-25)

**Scope:** removal only. Front-end; no backend, no API, no schema, no flag
change, and — deliberately — no file deleted. Chris framed it as *"a
cleanup/removal phase, not a new feature phase"* whose job is *"simple: remove
the split from the operator path."*

### What came out

| Where | What |
|---|---|
| `ui/js/app.js` | `_LV_TD_SURFACE_KEY`, `_lvTravelDocSurface()`, `_lvTravelDocDestroyLegacy()`, `_lvTravelDocPaintSurfaceChrome()`, `window.lvTravelDocSetSurface`, the focus-toggle painter block and the `lv-td-focus` body-class clear. The `traveldoc` arm of `lvShellShowTab` is a single-host mount now; `lvTravelDocTeardownAll()` is a single destroy. |
| `ui/hornelore1.0.html` | Both legacy asset tags, the `.lv-td-surface-switch` row and the `#lvTravelDocHost` div. The panel is one `<div id="lvTravelDocUnifiedHost">` and nothing else. |
| `ui/css/lori80.css` | The surface-switch block, `.lv-td-host-off`, and three `body.lv-td-focus` rules that became unreachable the moment the Documenter left the shell path. |
| `ui/js/travel-doc-lab.js` | `prodTravelDocUrl()` and the `.tdl-route-legacy` foot-note that deep-linked off the route board. |
| `ui/css/travel-doc-lab.css` | The `.tdl-route-legacy` rule, with the markup it styled. |

### What deliberately did NOT come out

The Phase 0 plan in this spec said Phase 4 would *"remove `travel-documenter.js`
/ `.css`, `travel-doc-lab.html`"* and *"rename survivors to `travel-doc.js` /
`travel-doc.css`."* Chris's actual Phase 4 order said the opposite on all three
counts, and it is right on all three.

1. **The old module, its stylesheet and `ui/travel-documenter.html` all stay on
   disk.** Requirement 7 forbids removing backend endpoints either surface uses,
   and that standalone page still mounts the module against them. *Unmounting a
   surface from the shell and deleting a module are different acts, and only the
   first was ordered.* A new `LegacyModuleStillExistsTest` fails the build if any
   of those files goes missing — so a future cleanup has to be a decision
   somebody makes on purpose, not a tidy-up that silently succeeds.
2. **`ui/travel-doc-lab.html` is kept and explicitly marked `DEV-ONLY`**
   (requirement 6). Three reasons, now written into the page: it is the only
   caller of `window.lvTravelDocMount()` outside the shell **and the only one
   that mounts without the shell's identity flag** — the flag that governs
   branding, layout and whether the querystring may supply a narrator id, so
   without this page that whole branch would have no caller and would rot
   untested; it mounts against a bare host with no shell chrome, which is how a
   layout or teardown bug the shell happens to mask shows up early; and it parks
   the handle on `window` so a developer can drive teardown from the console.
3. **The `travel-doc-lab.js` -> `travel-doc.js` rename is parked**, per Chris's
   out-of-scope list. Renaming a 3,400-line module is churn that would bury a
   real diff. The file headers now read *"lab"* as *"this file"*, not as *"a
   thing you can throw away"*, and the liveness harness carries a note that the
   rename must update its stack-attribution regex.

### Five on-path fixes the work order did not name

Reported under the standing autonomy rule; all are removal fallout, none crosses
into another subsystem.

1. **`lv80SwitchPerson`'s teardown fallback was a silent no-op.** It nulled
   `window._lvTravelDocMountedFor` — the retired Documenter's marker, which no
   longer exists anywhere — so on any load where `app.js` failed to define the
   teardown, a narrator switch would have left the previous narrator's mount
   alive. It nulls `_lvTravelDocUnifiedMountedFor` now, and a test pins it.
2. **The day photo picker's empty state was ungated and operator-visible**, and
   read *"add them via Photo Intake, then cluster from the production Travel
   Doc"* — a dead end twice over: there is no production Travel Doc left to go
   to, and Phase 3C put both Upload and Cluster on this surface's own toolbar,
   so the instruction pointed away from the buttons that do the job.
3. **`renderEvalChecklist` still called itself *"part of the removable lab, not
   production Travel Doc."*** It is dev-harness framing now, and the test
   guarding the copy also pins the `!embedded` call site, so the words and the
   gate cannot drift apart.
4. The route-board deep-link foot-note and its CSS rule (listed above).
5. The unreachable `body.lv-td-focus` rules (listed above).

### A gate that looked obvious and was wrong

The acceptance list asks for no visible *"legacy"* on the normal shell path, and
a file-wide `assertNotIn("legacy")` over `hornelore1.0.html` looks like the way
to prove it. It is not: the shell carries **19** unrelated occurrences — the QF
live-ownership override, the retired `/api/facts/add` path,
`LorevoxEras.legacyKeyToEraId`, welcome-back fallback prose. That gate would
have been a permanent false alarm about somebody else's code, so it is scoped to
the Travel Doc panel plus the `app.js` mount block, with the reason recorded in
the test.

A **stronger** gate became available instead. Every replacement comment in the
shell was deliberately written without naming the old module, so
`hornelore1.0.html` now contains **zero raw occurrences** of that name — which
lets `test_the_shell_never_names_the_legacy_module` assert against the
un-stripped file rather than a comment-stripped copy.

### Tests: rewritten, not deleted

Requirement 8. Five tests whose boundary genuinely inverted came out of
`tests/test_travel_doc_shell_mount.py` (the second-handle store, the
both-destroyers pin, the destroy-the-other-surface pin, the
switch-tears-both-down pin, the hiding-is-never-the-only-teardown pin) and
thirteen new ones went in.

The design rule behind the new `LegacyFallbackIsGoneTest`: **assert the absence,
do not merely stop asserting the presence.** An absence that is asserted fails
the build when someone re-adds a `<script>` tag; an absence that is only
unmentioned does not.

Seven inverted tests across the other two suites were narrowed rather than
dropped. Each keeps the half that still proves something and flips only the half
Phase 4 retired:

- `test_native_panel_uses_selected_narrator_not_paste` — still proves identity
  comes from the shell and never from a paste; the mount assertion moved onto
  the module's surviving caller.
- `test_shell_tab_and_panel_wired` — still proves the tab is wired; now proves
  the shell does **not** load that module's assets.
- `test_legacy_deep_link_survives_the_tab_rewrite` -> `test_the_tab_rewrite_strands_no_operator`
  — keeps the `current` -> `trip` tab-id migration, drops the escape hatch.
- `test_legacy_fallback_remains_reachable` -> `test_force_delete_gate_needs_no_fallback_surface`
  — the gate has shipped and been smoked through 3B/3C/3D; what still needs
  proving is that it is self-contained on this surface.
- `test_lab_files_carry_removable_marker` -> `test_the_harness_page_is_the_removable_one`
  — the old form required a delete-me sign on the two files that are now the
  operator's Travel Doc. It now pins the true split and fails if either ever
  claims to be removable again.

### Verification

- `node --check` clean on all three JS files; `ast.parse` clean on all three
  test files; `CR: 0` on all ten files on both sides of the transfer.
- **262 tests green** (was 255) across the same six suites, in the container and
  on the device.
- **Eight mutants, eight killed**, each by its intended gate: re-add the legacy
  script tag; re-add the surface toggle markup; revert the switch fallback to
  the retired marker; re-add the removable marker to the module; re-add the
  deep-link helper; strip `DEV-ONLY` from the harness page; re-add the off-host
  CSS rule; re-add the legacy mount call to `app.js`.
- `scripts/ui/run_travel_doc_shell_mount_liveness.js` rewritten for one surface,
  with a new `singleSurface` probe that reads the live document for a second
  host, a toggle, a surface setter or resolver, a legacy asset and a stored
  surface preference.

**The negative controls were kept honest.** Controls 1 and 5 are still
re-runnable. Controls 2, 3 and 4 tested toggle behaviour that no longer exists,
so they are marked **NOT re-runnable after Phase 4** and a re-runnable
substitute is named in their place: delete `_lvTravelDocDestroyUnified()` from
the remount arm and confirm `narrator_switch` reports 2/2. A harness that keeps
a control it can no longer run is a harness that lies about its own coverage.

### Live smoke

**Green on all fifteen steps, 2026-07-25.**

Steps 1-6, one surface: the unified workspace mounted directly with
`_lvTravelDocUnifiedMountedFor` set to the selected narrator; zero
`[data-td-surface]` attributes, zero `.lv-td-surface-switch` nodes, no
`#lvTravelDocHost`, and `lvTravelDocSetSurface` and
`lvTravelDocumenterMount` both undefined on `window`. Across 190
loaded resources there was not one request for anything named
documenter, and not one zero-byte JS or CSS asset -- the asset tags
did not merely stop being referenced, they stopped being fetched. A
sweep of every visible text node in the shell found zero occurrences
of *legacy*, *production Travel Doc*, *UI Lab*, *experimental*,
*lab-only*, *removable* or *documenter*.

Steps 7-10, the workflows Phases 3A-3D moved onto this surface, each
verified server-side through `/api/trips/{id}/tree` rather than off
the DOM. Two regions and two stops created; a stop reorder took
`0:ONE,1:TWO` to `0:TWO,1:ONE` and a region reorder took
`0:ALPHA,1:BRAVO` to `0:BRAVO,1:ALPHA` with ALPHA's stops travelling
with it and `region_id`/`parent_trip_stop_id` unchanged; region and
stop renames both persisted. Photo upload landed unplaced behind the
intake-not-approval warning, source upload landed private to the trip
and out of the memoir, and the `FileList` node identity held across
both drawers. Cluster wrote five links and stated its whole-library
caveat. Lori opened at `surface: travel_doc_modal`, scoped to the
trip, captures marked flags-0.

Steps 12-13 are the load-bearing ones for a removal phase. Retiring a
second surface is exactly the kind of change that leaves a listener
behind, so the census was functional rather than visual:
`BroadcastChannel`, `WebSocket` and `document`-level keydown were
instrumented before the loop, then Travel Doc was left and re-entered
three times.

```
round 1   bc 1 / close 0    ws 0 / close 0    keydown +1 / -1    .tdl-root 1
round 2   bc 2 / close 1    ws 0 / close 0    keydown +2 / -2    .tdl-root 1
round 3   bc 3 / close 2    ws 0 / close 0    keydown +3 / -3    .tdl-root 1
```

Each entry opens exactly what the previous exit closed: one channel
live, one keydown listener live, one root, at every sample. Zero net
sockets -- leaving Travel Doc never orphaned a Lori socket.

Step 14, the force-delete gate, rendered all ten impact lanes
(regions 2, stops 2, day cards 6, photo links 5, story notes 0,
sources 1, story links 0, public context 0, photo context 0, bio
suggestions 1 -- the lane production omits, and still the reason every
trip is force-delete-only from birth). A negative control ran first:
the button was disabled initially, still disabled on a title one
character short, and armed only on the exact title. Delete completed
and the trip list returned to zero.

Step 15, and the doctrine gates: **zero native dialogs across the
entire run**, recorded by a spy over `alert`/`confirm`/`prompt`
rather than by inspection, and **zero console errors** across a full
reload plus a sweep of all eight Travel Doc tabs. The standalone
harness still loads, still exposes `lvTravelDocMount`, and still
mounts one root.

#### One observation, not a defect

One observation, not a defect: the dev harness page's *rendered* copy still says "Travel Doc UI Lab" and "This experimental lab needs a narrator" and still paints the `UI Lab - experimental` badge, while the page's own HTML header declares it `DEV HARNESS -- DEV-ONLY, REMOVABLE`. All three strings sit behind `embedded ? ... : ...` ternaries (`travel-doc-lab.js` lines 1096, 1100, 1591), so they can only ever render on the standalone page and never in the shell -- which is why the shell-path copy gate came back clean. Requirement 5 is met by quarantine rather than removal, exactly as written. The harness now calls itself two different things; reconciling that is a copy edit, parked rather than taken unilaterally after the code had already been committed.

#### Residue

Smoke residue: the disposable trip and its uploaded source went with the cascade, but the uploaded photo did not -- photo *links* are deleted, photos are not -- so narrator `e7fdb578`'s library now holds five smoke photos, up from the four already accepted as documented residue.

## Revision history

- 2026-07-24 — Spec authored (Claude), folding Chris's merge brief, ChatGPT's six-phase work order, and Claude's six amendments. Phase 1 landed same day.
- 2026-07-24 — Phase 1.1 added and landed after Chris's Phase 1 review found no stale-async guard. Phase 2 was held until it was in.
- 2026-07-25 — Phase 2 landed: the unified workspace mounts in the shell's Travel Doc tab by default, the legacy Documenter stays reachable behind a temporary surface switch, and the Lab launcher is gone. CSS scoped to `.tdl-root`. Two pre-existing Documenter leaks closed.
- 2026-07-25 — Phase 3A landed: the trip force-delete impact-review gate ported into the unified workspace, reading `e.body.detail` and rendering ten impact lanes where production renders nine. `api()` now surfaces `err.status`/`err.body`. Phase 3 formally split into 3A/3B/3C/3D scope walls. Backlog note: every trip is born with a `travel.trip` bio suggestion, so every trip is force-delete-only from birth.
- 2026-07-25 — Phase 3C landed: photo upload at trip/region/stop scope, source upload, and photo clustering built into the unified workspace — a capability, not a port, since the lab had no `FormData` and no file input. `api()` grew a `FormData` branch ahead of its JSON branch. Scope is an explicit drawer selection rather than production's ambient `editorScope()` read, and the drawer never repaints between choosing files and uploading, because a `FileList` cannot be restored by script. Intake never promotes. Found and fixed a same-scope bug: three suites used a string-blind comment stripper and went blind on `files.accept = "image/*"` — migrated to the repo's existing `strip_js_comments`, assertions unchanged. 236 tests green (was 220), sixteen new gates mutation-tested; twelve-step live smoke green across all three upload scopes, with no-auto-promotion verified server-side.
- 2026-07-25 — Phase 3B landed: trip create/edit and region/stop CRUD ported into the unified workspace, with insert-at-position preserved and both deletes as in-panel reviews. The region delete is deliberately not verbatim — it fixes a production dead-end where a non-empty region's DELETE 409s and production neither forces nor handles it. Empty-state copy fixed; `st.daysWarning` wired after being read-but-never-set. 220 tests green (was 205); thirteen-step live smoke green with a functional socket/channel/listener census.
- 2026-07-25 — Phase 4 landed and smoke-accepted (fifteen steps green, including a three-round mount census showing opens 3 / closes 2, keydown +3 / -3, zero net sockets and one root at every sample): the legacy fallback is retired and the unified Travel Doc is the operator's only Travel Doc surface. Removal only — no backend, API, schema or flag change, and no file deleted. Out: the surface toggle and its whole support cast, both legacy asset tags, the switch row, `#lvTravelDocHost`, the `.lv-td-surface-*` / `.lv-td-host-off` / `body.lv-td-focus` rules, and the route board's `prodTravelDocUrl()` deep-link foot-note. **Deliberately not out:** the old module, its stylesheet and its standalone page, because requirement 7 forbids removing what a backend endpoint still serves and that page still mounts it — unmounting a surface and deleting a module are different acts; and `ui/travel-doc-lab.html`, kept and marked `DEV-ONLY` because it is the only caller of `lvTravelDocMount()` that exercises the non-shell identity branch. This narrows the Phase 0 plan written above, which had called for deleting all four and renaming the survivors; the rename stays parked. Five on-path fixes the order did not name, chief among them a `lv80SwitchPerson` teardown fallback nulling the retired marker (a silent no-op) and an ungated, operator-visible photo-picker empty state pointing at a production Travel Doc that no longer exists. A file-wide `assertNotIn("legacy")` on the shell proved invalid — 19 unrelated occurrences — so the gate is scoped to the panel and the mount block, and a stronger one replaced it because the shell now holds zero **raw** occurrences of the old module's name. Tests rewritten not deleted: five out, thirteen in, seven narrowed, with absences now asserted rather than merely unmentioned. 262 tests green (was 255); eight mutants, eight killed; the liveness harness rewritten for one surface with a `singleSurface` probe and its unrunnable negative controls marked as such rather than quietly dropped.
- 2026-07-25 — Phase 3D landed and smoke-accepted: route order and route-row ergonomics in the unified workspace. Region and stop up/down reorder, evidence badges on route rows, and region rows made selectable — which revived Phase 3C's `defaultScopeKey()` region arm, previously unreachable because `st.routeSel` was only ever written as a stop. A stop move deliberately posts two ids to `/stops/{id}/move` rather than production's full permutation to `/stops/reorder`, because a permutation is exactly as stale as the tree it was built from; regions still post a permutation because that is the only endpoint, so a refusal is surfaced in-panel and the bundle reloaded rather than dead-ending. `routeBusy` serialises moves; `routeError` is the in-board failure surface. **The live smoke found a bug that nineteen source-scanning gates could not**: `api()` owns the request encoding, and both new movers pre-stringified their body, so every arrow press on the board answered 422. Fixed with a raw object at both call sites plus two new gates, one banning `body: JSON.stringify` file-wide while pinning that the encoding still happens exactly once inside `api()`. 255 tests green (was 236), nineteen gates mutation-tested, nineteen mutants killed. Eleven-step live smoke green, including insert before/after on a substop, cross-region move, cycle rejection at both layers, order surviving a refresh, both delete ladders, `FileList` node identity, the force-delete gate, and a clean mount/socket census. Also repaired a pre-existing red: the Phase 2 `lv80SwitchPerson` test window was never committed, so the device baseline had really been 235/236 since Phase 2.
