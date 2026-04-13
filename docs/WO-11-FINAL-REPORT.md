# WO-11 Final Report: Trainer Isolation + Transcript Overlay Fix

## Summary

WO-11 addressed five interconnected bugs in Hornelore 1.0 that prevented clean trainer operation, caused the transcript popover to be un-dismissable, triggered false chat-down states, auto-loaded narrators defeating startup neutrality, and allowed stale Janice DOB data in cross-reference templates. All five root causes were identified and fixed at the source.

## Root Causes

1. **Trainer piggybacks on narrator state**: `lv80RunTrainerNarrator` reused the active narrator's `person_id` and `conv_id` instead of isolating trainer sessions. Trainer messages polluted the real narrator's conversation history.

2. **Auto-load defeats startup neutrality**: The startup sequence auto-selected the first narrator in the people list, making it impossible to open a trainer from a blank state (v8.1 principle violation).

3. **Transcript popover never hides**: CSS rule `#wo10TranscriptPopover { display: flex; }` overrode the UA Popover API's `[popover]:not(:popover-open) { display: none; }` due to ID specificity. The close button called `hidePopover()` successfully but the element remained visible.

4. **False chat-down state**: The 30-second timeout guards in `sendUserMessage` and `sendSystemPrompt` fired `setLoriState("unavailable")` without checking whether the WebSocket was actually connected. Also, stale error state persisted across WS reconnections.

5. **Janice DOB mismatch**: `kent-james-horne.json` and `christopher-todd-horne.json` had Janice's DOB as "1939-09-30" (September 30) while her canonical file `janice-josephine-horne.json` correctly had "1939-08-30" (August 30).

## Files Changed

### `ui/hornelore1.0.html`

- **Lines ~4034-4090**: Rewrote `lv80RunTrainerNarrator` with full trainer isolation: suspends active narrator's `person_id` and `conv_id`, nulls `state.person_id`, generates isolated `trainer_*` conv_id, clears chat, closes transcript, updates header via `_wo11UpdateHeaderForTrainer`.

- **Lines ~4092-4114**: Added `_wo11UpdateHeaderForTrainer(style)` function to render trainer avatar (DT/ST), display name, and subtitle into `#lv80ActiveNarratorCard`.

- **Lines ~4117-4160**: Added `_wo11RestoreNarratorAfterTrainer()` function: clears trainer isolation state (`active`, `suspendedNarratorId`, `suspendedConvId`), clears chat, clears stale `profile.basics`, restores original narrator card DOM structure (IDs: `lv80NarratorAvatar`, `lv80ActiveNarratorName`, `lv80ActiveNarratorSub`), calls `lv80UpdateActiveNarratorCard()`, opens narrator selector for explicit re-selection.

- **Lines ~1994-2005**: Fixed CSS — removed `display: flex` from base `#wo10TranscriptPopover` rule, keeping it only in `#wo10TranscriptPopover:popover-open`. This lets the UA Popover API properly hide the element when not open.

- **Lines ~2619-2626**: Added `✕` close button to transcript popover header that calls `hidePopover()`.

- **Lines ~6684-6718**: Added transcript toggle listener with trainer guard (blocks open when trainer active or no narrator), and capture-phase click listener on the Transcript button to prevent `popovertarget` from firing in trainer mode.

- **Lines ~6735**: Replaced auto-select first narrator block with WO-11 startup neutral log.

### `ui/js/app.js`

- **Lines ~4424-4465**: Modified `lv80StartTrainerInterview` to call `_wo11RestoreNarratorAfterTrainer()` and stash pending style hint for narrator re-selection.

- **Lines ~4472-4506**: Modified `lv80ClearTrainerAndCaptureState` to check for trainer-active state and call restore function.

- **Lines ~2444-2460**: Modified `sendUserMessage` 30s timeout: added WS health check — if `ws && wsReady`, suppresses false unavailable state and sets Lori to "ready".

- **Lines ~2482-2490**: Modified `sendSystemPrompt` 30s timeout: same WS health check, also removes stale thinking bubble.

- **Lines ~2928**: Modified WS `onopen` handler: clears any stale error state with `setLoriState("ready")` and console log.

### `ui/templates/kent-james-horne.json`

- Line 128: Changed `"birthDate": "1939-09-30"` to `"1939-08-30"`
- Line 131: Changed narrative from "September 30" to "August 30"

### `ui/templates/christopher-todd-horne.json`

- Line 30: Changed `"birthDate": "1939-09-30"` to `"1939-08-30"`

## Test Results

| Test | Description | Result |
|------|-------------|--------|
| A1 | Clean trainer open from startup — no narrator active | **PASS** |
| A2 | Trainer with Janice already loaded — header switches to DT, Janice suspended | **PASS** |
| A3 | Exit trainer — header restores to "Choose a narrator", selector opens | **PASS** |
| B1 | Transcript opens with narrator active | **PASS** |
| B2 | Transcript close button (✕) hides popover completely | **PASS** |
| B3 | Transcript reopens after close | **PASS** |
| B4 | Transcript blocked during trainer mode | **PASS** |
| C1 | WS connected — no false unavailable state | **PASS** |
| C2 | WS onopen clears stale error state | **PASS** |
| D1 | Narrator selector shows Janice DOB as "Aug 30, 1939" | **PASS** |
| D2 | All template files agree on 1939-08-30 | **PASS** |
| D3 | Profile basics dob = "1939-08-30" in live app | **PASS** |

## Evidence

### A1 — Startup neutral
```
[WO-11] Startup neutral — no auto-load. User must choose narrator or trainer.
[WO-11][trainer] Suspending narrator: null for trainer: storyteller
[WO-11][trainer] Header updated for: Dolly Trainer
[WO-11][trainer] Trainer started: storyteller
```

### A2 — Trainer with Janice present
```
[WO-11][trainer] Suspending narrator: 93479171-0b97-4072-bcf0-d44c7f9078ba for trainer: storyteller
[WO-11][trainer] Header updated for: Dolly Trainer
[WO-11][trainer] Trainer started: storyteller
```

### A3 — Trainer exit and restore
```
[WO-11][trainer] Trainer interview handoff — style: storyteller
[WO-11][trainer] Restoring narrator after trainer exit. Suspended: 93479171-0b97-4072-bcf0-d44c7f9078ba
[WO-11][trainer] Trainer exited — narrator selector will open for explicit choice.
```
Header correctly showed "Choose a narrator" with "?" avatar after exit.

### B4 — Transcript guard
```
[WO-11][transcript] Click blocked — trainer active or no narrator.
```

### C1/C2 — WS health
```
[WO-11][chat-state] WS connected — clearing any stale error state
```
(Repeated on each reconnection with no false unavailable state)

### D3 — Profile DOB
```javascript
state.profile.basics.dob = "1939-08-30"
```

## Additional Bugs Found and Fixed During Testing

1. **Header stuck on trainer after narrator re-selection (DOM ID destruction)**: `_wo11UpdateHeaderForTrainer` replaced `#lv80ActiveNarratorCard` innerHTML with trainer-specific HTML using CSS classes instead of IDs. When `lv80UpdateActiveNarratorCard()` ran after trainer exit, `getElementById` for `lv80ActiveNarratorName`, `lv80ActiveNarratorSub`, `lv80NarratorAvatar` returned null, silently failing. Fixed by restoring original DOM structure in `_wo11RestoreNarratorAfterTrainer` before calling the update function.

2. **Stale profile.basics after trainer exit**: `state.profile.basics` retained the previous narrator's data after trainer exit with `person_id = null`, causing the header to show the old narrator's name/DOB instead of "Choose a narrator". Fixed by clearing `state.profile.basics = {}` in the restore function.

3. **Transcript popover CSS specificity**: `#wo10TranscriptPopover { display: flex; }` overrode the UA popover hidden state. This was the root cause of the "un-closeable transcript" — `hidePopover()` worked but the element stayed visible. Fixed by moving `display: flex` to the `:popover-open` pseudo-class only.

## Remaining Risks

- **Transcript button `popovertarget` interaction**: The Transcript button's `popovertarget="wo10TranscriptPopover"` attribute conflicts with other `popover="auto"` elements (narrator selector). Clicking the Transcript button can trigger light-dismiss on the narrator popover, causing a toggle race. The `showPopover()` JS call works reliably. This is a pre-existing Popover API interaction issue, not introduced by WO-11.

- **Zodiac sign inconsistency**: Janice's profile shows `zodiacSign: "Libra"` but Aug 30 is Virgo. This is a pre-existing data issue, not WO-11 scope.

## Conclusion

All five WO-11 root causes are resolved. Trainer sessions are fully isolated from narrator state. Startup is neutral. The transcript popover properly hides when closed. Chat availability is accurately reported. Janice's DOB is canonical across all templates and the live profile. Three additional bugs discovered during acceptance testing were fixed in the same patch.
