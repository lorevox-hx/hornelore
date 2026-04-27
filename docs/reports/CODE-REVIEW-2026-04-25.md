# Code Review — End-of-Session Notes (2026-04-25)

This week shipped a lot of UI surface area: three-tab shell, narrator room, archive, harness, session-style wiring, post-identity orchestrator, narrator audio + transcript pipeline. This doc is a sober look at what got accumulated, what's load-bearing, and what's now technical debt worth flagging before the next sprint.

## File-size shape

```
ui/hornelore1.0.html     8,539 lines   ←  4× heavier than any other file
ui/js/app.js             6,896 lines   ←  the catch-all
ui/css/lori80.css        1,297 lines
ui/js/ui-health-check.js 1,185 lines
ui/js/session-loop.js      425 lines   ←  this week
ui/js/session-style-router 215 lines   ←  this week
ui/js/archive-writer.js    240 lines   ←  this week
```

The two giants — `hornelore1.0.html` and `app.js` — are the catch-all cliffs everything else accumulates onto. They're not in immediate danger, but they're the surface area where the next merge conflict will happen if two WOs touch them simultaneously.

## What's working clean

**Three new modules from this week are well-bounded.** `session-style-router.js`, `session-loop.js`, and `archive-writer.js` each own one concern, expose a small surface, and don't cross each other's lanes. They also each expose a diagnostic accessor on `window` (`lvSessionLoop`, `lvSessionStyleRouter`, `lvArchiveWriter`) so the harness can observe state without invoking it. That pattern should be the default for every new module going forward.

**The harness is paying off.** WO-UI-TEST-LAB-01 has caught two real issues already (the photo preflight staleness, the camera state-on-but-preview-missing class) without anyone needing to remember to test for them. The 1.5s paint tick + per-tab dispatch in WO-NARRATOR-ROOM-01 likewise observable through harness-readable state.

**Side-channel flags for harness observation work better than fn.toString() introspection.** The `_lv80QuestionnaireFirstBypassFired` and `_lv80WelcomeBackSuppressedForQF` flags are 2-line additions that let the harness verify behavior happened without parsing source. Use this pattern more.

## Tech debt accumulated this week

### 1. `lv80SwitchPerson` rebuilds `state.session` from scratch every time

The function at `hornelore1.0.html:4646` rebuilds `state.session = {…}` in two parallel branches (READY at L4675, INCOMPLETE at L4736). Every new session-scoped field that ships gets DROPPED on narrator switch unless someone remembers to add a preservation line. Already bit:
- `#145` — onboarding object dropped (preservation added)
- `#194` — sessionStyle dropped (preservation added)
- `#206` — camera one-shot gate added then dropped (different fix)

The pattern is that `state.session` is treated as ephemeral but contains both narrator-scoped and session-scoped fields tangled together. Every WO that adds a session field has to remember to preserve it across switch.

**Fix idea**: split `state.session` into `state.session` (session-scoped, preserved) and `state.narratorSession` (narrator-scoped, rebuilt). Or document a "preserve list" up top of the function as a single source of truth so adding a field is a one-liner with a checklist.

Defer to a quiet-day refactor — not blocking parents-by-next-week.

### 2. `bio-builder-core.js` cross-narrator contamination (Bug #219)

Live verify of WO-01B BB save uncovered that `GET /api/bio-builder/questionnaire?person_id=<corky>` returns Christopher Todd Horne's data. `[bb-drift] KEY MISMATCH` logs in the console hint at the cause: bio-builder-core's persistence layer mixes narrators between `localStorage` (`lorevox_qq_draft_<pid>`) and backend, and the restore-fallback path can read the wrong key.

**Critical for parents-by-next-week.** Mom and Dad need clean per-narrator BB blobs or every session contaminates the next. Filed as Bug #219.

### 3. `app.js` is becoming the everywhere file

6,896 lines. This week added:
- `_setWarmupBanner` updated with readiness-card mirror (WO-UI-SHELL-01)
- `lvShellShowTab` / `lvShellInitTabs` / 6 shell helpers (WO-UI-SHELL-01)
- `lvSetSessionStyle` / `getSessionStyle` (WO-UI-SHELL-01)
- `lvOpenMediaTool` / `_lvMediaPreflightOnce` (WO-UI-SHELL-01)
- `lvNarratorRoomInit` / 8 narrator-room helpers (WO-NARRATOR-ROOM-01)
- `_lvNarratorPaintControls` / `_lvNarratorPaintIdentity` / paint tick (WO-NARRATOR-ROOM-01)
- 5 photos-view renderers (WO-NARRATOR-ROOM-01)
- `lvUpdateOperatorReadiness` (WO-UI-SHELL-01)
- inline call to `lvSessionLoopOnTurn` in 2 places (WO-HORNELORE-SESSION-LOOP-01)
- inline call to `lvArchiveOnNarratorTurn` (WO-ARCHIVE-INTEGRATION-01)
- `buildRuntime71` extension for `session_style_directive` (WO-HORNELORE-SESSION-LOOP-01)

**Fix idea**: factor the WO-UI-SHELL-01 + WO-NARRATOR-ROOM-01 helpers out into `ui/js/shell-tabs.js` and `ui/js/narrator-room.js`. They're additive and bounded — easy to extract without breaking the rest. Defer.

### 4. CSS is approaching the same shape

`lori80.css` is 1,297 lines. WO-UI-SHELL-01 and WO-NARRATOR-ROOM-01 each appended ~250 lines of scoped class blocks. Easy to factor into:
- `ui/css/shell-tabs.css`
- `ui/css/narrator-room.css`
- `ui/css/bug-panel-extensions.css`

The file is still readable; this is preventive, not urgent.

### 5. Cache-busting strategy is brittle

The `<script src="js/foo.js">` tags don't carry a version query. `?v=<timestamp>` on the HTML URL doesn't propagate. Several harness-verify failures tonight were "browser cached the old JS." Currently the workaround is hard-reload (Ctrl+Shift+R) which works but is operator-burden.

**Fix idea**: add `?v=<git-sha>` or `?v=<build-timestamp>` to all `<script src>` tags via a tiny build-time substitution. Or set explicit `Cache-Control: no-cache` headers on the static server for `js/*.js`. 1-day fix.

### 6. State-shape drift between state.js init and lv80SwitchPerson rebuild

State.js initializes session with a comprehensive shape. lv80SwitchPerson rebuilds with a much smaller shape (just the fields it explicitly sets). New fields get added to state.js but not to the rebuild — leading to "missing on switch" bugs (#145, #194, narrator-room handsFree, loop substate). Each WO has to remember to update both.

**Fix idea**: have lv80SwitchPerson MERGE into the existing session object rather than replace. Most fields stay; only the explicit keys get reset. 30-line change. Defer until two more "preserved field" bugs hit.

### 7. The `[v9-gate]` flow inside lv80SwitchPerson is getting deeply nested

Three branches: ready, incomplete, questionnaire_first override. Each has its own state.session rebuild + its own greeting branch. The `_ssIsQF` check is at the top of the welcome-back gate. It's all working but the flow chart is no longer a quick read.

**Fix idea**: extract `_v9GateClassify(personId)` and `_v9GateRoute(classification, ...)` so the function reads as classify + dispatch. Defer.

## Pattern inconsistencies worth standardizing

**1. Console log prefixes are inconsistent.**
`[Hornelore]`, `[Lori 7.1]`, `[Lori 9.0]`, `[Lorevox]`, `[lv-shell]`, `[session-loop]`, `[session-style]`, `[lv10d-…]`, `[WO-CAM-FIX]`, `[WO-13]`, `[WO-9]`, `[WO-11]`, `[WO-STT-LIVE-02]`, `[v9-gate]`, `[bb-debug]`. Different prefix style per author, hard to grep across modules.

**Recommend**: a single canonical prefix per module written down somewhere. Probably:
- `[Hornelore]` for module load notices
- `[<wo-id>]` for WO-specific instrumentation that should be findable in api.log greps

**2. Two flag-reading patterns.**
`getSessionStyle()` (helper function) vs `state.session.sessionStyle` (direct read) — both used. The helper has a default-fallback; the direct read can be undefined. Some call sites use one, some the other.

**Recommend**: always use the helper at runtime. Use the direct read only in init code where the field is just being set.

**3. Some modules expose diagnostic accessors, some don't.**
`window.lvSessionLoop`, `window.lvArchiveWriter`, `window.lvUiHealthCheck`, `window.lvSessionStyleRouter` all expose `{ ..., loaded: true }`. But older modules (camera-preview, focus-canvas, projection-sync) don't. Hard for the harness to observe their state.

**Recommend**: as we touch each older module for any reason, add `window.<moduleName> = {...}` accessor. Don't refactor specifically for this.

## Things NOT to refactor before parents-using

The list above is real but **none of it is blocking the parents-by-next-week ship**. Everything described is either:
- Pre-existing tech debt that shipped before this week (lv80SwitchPerson rebuild)
- Sized-up file pain that hasn't actually broken anything yet
- Polish that can wait until after the first family session

The one item that IS blocking is **Bug #219 (BB cross-contamination).** That should be triaged before parents touch the app — or each session pollutes the next.

## Recommended priorities for cleanup work

```
P0 (before parents):
  - Bug #219: bio-builder-core cross-narrator contamination

P1 (next quiet day):
  - Cache-busting strategy (?v= on script tags)
  - Extract state.session merge fix in lv80SwitchPerson

P2 (after parents using, before scale):
  - Factor app.js shell+narrator helpers into separate modules
  - Factor lori80.css into per-feature files
  - Standardize log prefixes

P3 (eventually):
  - Diagnostic accessors on every module
  - state.session split (session-scoped vs narrator-scoped)
  - _v9GateClassify / Route extraction
```

## Closing

The WO-driven rhythm is working. Each WO is a clean unit with its own spec, build, verify, commit. The harness catches regressions before merge. The doc-trail (every WO ships its own report) makes future-you's job easier than past-Claude's was.

The risk this week was scope creep on the orchestrator (session-loop) — five+ behaviors stacked into one module. We mostly held the line by deferring repeatable BB sections, hands-free auto-rearm, and audio capture into separate WOs. Worth being equally disciplined about Audio + STT next week — those have natural sub-WO lines and shouldn't fuse into a single sprawling module.
