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

### Phase 3 — port the Documenter's features in

The bulk of the work. **The delete gate goes first** — it is the newest and least-exercised code in either panel and the thing most likely to be quietly broken by a port.

Everything lands in the tab currently called "Current", which should be renamed — "Trip" or "Route" reads better than "Current" once it is no longer a comparison stub.

| Production feature | Where it lands | Notes |
|---|---|---|
| Trip force-delete gate | Trip tab, trip header | Port verbatim. Preserves the `e.body.detail` envelope read — see risks. |
| **Photo upload (trip / region / stop)** | Trip + Photos tabs | **Capability to build, not a control to port — see A2.** |
| **Source file upload** | Sources tab | `uploadSourceFiles` → `POST /api/trips/{id}/sources/upload`. Missing from both inventories. |
| Cluster photos | Photos tab | |
| Trip create / edit modal | Trip tab + sidebar "New trip" | Lab has no trip create at all today. |
| Region / stop CRUD | Trip tab | Lab's `/tree` render is read-only; genuinely new UI. Includes region **area / start / end / base / summary** and stop **region selector + type** from the eight-value `STOP_TYPES` list — see A4. |
| Stop insert-at-position | Trip tab | `insertContext` / `insertHint` semantics — behavioural, not visual. See A4. |
| Itinerary tile board | Trip tab, main column | Route order = tile order; reorder, insert, restructure. |
| Editable Route Outline | Existing sidebar | Share selection with the board via the existing `st.routeSel`. |
| Timeline view | Trip tab right rail | Documenter's `rightView: editor \| timeline` toggle. |
| Memoir preview | Trip tab toolbar | |
| `days_warning` / `sync_warning` banner | Global, above tabs | Added 2026-07-23; **do not drop it** — it is the fix for the day-cards-look-missing confusion. |
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

## Revision history

- 2026-07-24 — Spec authored (Claude), folding Chris's merge brief, ChatGPT's six-phase work order, and Claude's six amendments. Phase 1 landed same day.
- 2026-07-24 — Phase 1.1 added and landed after Chris's Phase 1 review found no stale-async guard. Phase 2 was held until it was in.
- 2026-07-25 — Phase 2 landed: the unified workspace mounts in the shell's Travel Doc tab by default, the legacy Documenter stays reachable behind a temporary surface switch, and the Lab launcher is gone. CSS scoped to `.tdl-root`. Two pre-existing Documenter leaks closed.
