# BUG-LORI-RESPONSE-GUARDS-STALE-TRIP-SURFACE-DOCSTRING-01

**Status:** ACTIVE / SMALL CLEANUP
**Severity:** LOW (docs-only; zero runtime impact)
**Origin:** 2026-06-25 ChatGPT review of post-Path-A code state
**Depends on:** none
**Blocks:** none
**Locked principle:** Docstrings and module-level comments must reflect what the code actually does. The 2026-06-24 surface-scoped drift-skip iteration was replaced the same day by iteration 2 (drift guard active on every surface with a chain-aware English fallback), but several blocks of explanatory text still describe the iteration-1 state.

---

## Why this bug exists

Same-day evolution:

| Iteration | Behavior | Status |
|---|---|---|
| Iteration 1 (early 2026-06-24) | `surface="trip"` skips the drift guard. Trip-tab callers opt out so European place-name pile-ups don't trip the detector. | Stale — replaced same day |
| Iteration 2 (late 2026-06-24) | Drift guard ACTIVE on every surface. Replaced destructive `"Sorry — let's continue"` boilerplate with chain-aware English continuation built from narrator anchors. `_SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR = frozenset()` (empty). Surface plumbing remains in API for a future surface that genuinely wants opt-out. | Current shipped state |

The code-side implementation is correct (`_SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR` is empty; `repair_language_drift` accepts `anchors`; `apply_response_guards` accepts `surface` + `narrator_anchors`). The MODULE docstring at the top of `lori_response_guards.py` still narrates iteration 1 ("Goes OFF on the Trip-tab surface" / "Trip-tab callers pass surface='trip'"). That contradicts the iteration-2 implementation comments lower in the file and confuses future readers.

The harness B docstring also still says `params.surface="trip"` is sent — but iteration 2 dropped that line from the harness payload. (Already fixed in the harness file's comment block when iteration 2 landed; verify no stale string remains.)

---

## Goal

Make module-level docs match code reality. Specifically:

1. Rewrite the "STATUS (2026-06-24)" block in `lori_response_guards.py` lines ~12-27 to describe iteration 2 honestly: drift guard active on every surface, chain-aware English fallback, surface plumbing remains as API-only opt-out for a future caller.

2. Update the "Public API" summary block (lines ~51-69) so the function signature lines match the actual kwargs:
   - `repair_language_drift(target_language="en", anchors=None) -> str`
   - `apply_response_guards(assistant_text, narrator_text, recent_narrator_turns, target_language="en", seeded_facts=None, surface="narrator", narrator_anchors=None) -> Tuple[str, List[str]]`

3. Scan `chat_ws.py` for any iteration-1 comment language that survived the iteration-2 edit and contradicts current behavior. (Iteration 2 already cleaned the comment immediately before the `_apply_guards` call site, but verify.)

4. Scan `scripts/run_trip_route_canary_harness.py` for stale `surface="trip"` references. (Already cleaned during iteration 2, but verify.)

---

## Non-goals

This bug does NOT:

- Change any runtime behavior.
- Add or remove tests.
- Touch the surface routing plumbing — that stays as-is in case a future caller wants per-surface opt-out.
- Re-open the language-drift-repair debate.

---

## Acceptance criteria

1. `git diff` shows ONLY comment / docstring lines changed in `server/code/api/services/lori_response_guards.py`. No semantic code change.
2. AST parse OK before + after.
3. Module docstring contains the phrase "active on every surface" or equivalent.
4. Public-API summary shows the current kwargs.
5. `grep -rn 'surface="trip"' server/ scripts/` returns ONLY the `_SURFACES_WITHOUT_LANGUAGE_DRIFT_REPAIR = frozenset()` reference and the harness docstring's "removed" mention. No active call sites still send `surface="trip"`.

---

## Stop conditions

Stop if:

- The docstring rewrite drifts into prescribing a different behavior than the code does (the cleanup must match REALITY, not propose new policy).
- Any unit test or harness scoring rule references the iteration-1 wording and would need to change.

---

## Files likely to touch

```text
server/code/api/services/lori_response_guards.py  — main cleanup
server/code/api/routers/chat_ws.py                — verify comment around _apply_guards call site
scripts/run_trip_route_canary_harness.py          — verify docstring; should already be clean
```

---

## Revision history

- 2026-06-25 — Created from ChatGPT review noting the iteration-1 docstring still on the file after iteration-2 implementation landed.
