# BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 Re-audit — 2026-05-03 evening

## Question

Did Lane E's `_lvInterviewSelectEra()` patch ship correctly, or is the
`rehearsal_quick_v1` Life Map RED finding evidence of a real
regression?

## Lane E code re-trace (line-by-line)

`ui/js/app.js` `_lvInterviewSelectEra(eid)` (L689-768):

| Step | Action | Line | Status |
|---|---|---|---|
| 1 | Canonicalize era_id at boundary via `_canonicalEra()` | L695 | ✓ correct |
| 2 | Log `[life-map][era-click] era=X prev=Y` console marker | L700-701 | ✓ correct |
| 3 | Write `state.session.activeFocusEra = canonical` | L702 | ✓ correct |
| 4 | Call `setEra(canonical)` (writes `state.session.currentEra` via canonical setter) | L712-714 | ✓ correct (Lane E add) |
| 5 | Re-render Life Map column for active highlight | L718 | ✓ correct |
| 6 | Update Active Focus header text | L720-721 | ✓ correct |
| 7 | Dispatch `lv-interview-focus-change` CustomEvent | L725-728 | ✓ correct |
| 8 | Call `sendSystemPrompt(directive)` with Phase 1+2 discipline inlined | L747-767 | ✓ correct (Lane E add) |
| 9 | Log `[life-map][era-click] Lori prompt dispatched for era=X` | L763 | ✓ correct |
| 10 | Special-case `today` with present-tense framing | L749-755 | ✓ correct |

**Verdict: Lane E ships correctly.** All 10 steps from Chris's bug
spec land where they should.

## So why did rehearsal_quick_v1 see `era_click_log_seen=false`?

The harness chain in `run_life_map_cycle()`:

1. `add_test_narrator("clear_direct")` — creates a fresh test narrator
2. `session_start()` — opens the narrator session
3. `page.evaluate("lvEnterInterviewMode()")` — enters interview mode
4. wait 500ms
5. `click_life_map_era("Coming of Age")` — tries to click the button
6. `confirm_era_popover()` — clicks Continue if popover appeared
7. Wait 500ms then check `[life-map][era-click] era=` console marker

Steps 5+6 fail when EITHER:
- (a) the era button hasn't rendered yet → no click happens → no popover → no marker
- (b) the era button IS rendered but the popover doesn't appear (would only happen if `_lvInterviewConfirmEra` is broken — but the readiness harness TEST-08 verifies this works for Today)
- (c) the era button is rendered but DISABLED — click registers as no-op → no popover → no marker

## Likely root cause — option (c)

Reading the existing readiness harness `test_08_lifemap_era_cycle`
docstring (scripts/ui/run_parent_session_readiness_harness.py:1077-1090):

> "Per MANUAL-PARENT-READINESS-V1 (Manual TEST-08A): the historical-era
> buttons (Earliest Years, Early School Years, Adolescence, Coming
> of Age, Building Years, Later Years) require identity_complete to
> activate. Today is special-cased as the present-day anchor and
> always clickable."

The readiness harness explicitly calls `self._complete_identity_for_
test_narrator()` BEFORE clicking historical eras (line 1090).

The **rehearsal harness** (`run_parent_session_rehearsal_harness.py`
`run_life_map_cycle()` at lines ~752-823) does NOT call
`_complete_identity_for_test_narrator()`. It just adds the narrator,
starts the session, enters interview mode, and clicks. For the
Hearth voice baseline — which uses the synthetic test narrator added
via `add_test_narrator("clear_direct")` — the historical era buttons
are DISABLED until identity is complete.

Coming of Age (the era clicked in `--quick` mode) is a historical
era → disabled at the time of click → click is a no-op → no popover
appears → `_lvInterviewSelectEra` is never called → no
`[life-map][era-click]` log fires → `era_click_log_seen=false`.

## Conclusion

**Lane E is NOT a regression.** The rehearsal_quick_v1 Life Map RED
finding is a harness gap, not a product bug.

## Recommended fix (Lane G.2 candidate)

In `run_parent_session_rehearsal_harness.py` `run_life_map_cycle()`,
after `add_test_narrator(...)` and BEFORE `lvEnterInterviewMode()`,
call `self._complete_identity_for_test_narrator()` to unlock historical
era buttons.

Alternatively (faster, lower-coverage): in `--quick` mode, click ONLY
"Today" (which is always clickable regardless of identity state).
Today exercises the same `_lvInterviewSelectEra` → setEra →
sendSystemPrompt path, just with present-tense framing instead of
era-anchored framing.

The `--standard` mode should still complete identity + cycle all 7
eras, since cross-narrator divergence on era handoff is part of
the rehearsal contract.

## Cross-references

- **Lane E** — `_lvInterviewSelectEra` patch (2026-05-03 afternoon)
- **Lane G** — rehearsal harness build (2026-05-03 evening)
- **Lane G.1** — harness stabilization (this session) — bumped Life
  Map render wait to 2000ms + added `wait_for_selector('[data-era-id]')`
  but did NOT add identity completion. The wait fix addresses
  rendering timing but NOT button-disabled state.
- **Lane G.2 (proposed)** — add identity completion to
  `run_life_map_cycle` to address option (c).
- **MANUAL-PARENT-READINESS-V1 (TEST-08A)** — original spec for the
  identity-required era-button behavior.

## Files audited

- `ui/js/app.js` L689-768 (`_lvInterviewSelectEra` body)
- `scripts/ui/run_parent_session_rehearsal_harness.py`
  `run_life_map_cycle` body (~L752-845)
- `scripts/ui/run_parent_session_readiness_harness.py`
  `test_08_lifemap_era_cycle` for the identity-completion
  reference pattern

## Files changed

0. Audit-only.
