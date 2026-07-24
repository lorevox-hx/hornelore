# WO-TRAVEL-DOC-UNIFY-01

**Status:** ACTIVE — Phase 1 LANDED 2026-07-24. Phases 2–6 open.
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

### Phase 2 — coexist in the tab behind a toggle

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

## Revision history

- 2026-07-24 — Spec authored (Claude), folding Chris's merge brief, ChatGPT's six-phase work order, and Claude's six amendments. Phase 1 landed same day.
