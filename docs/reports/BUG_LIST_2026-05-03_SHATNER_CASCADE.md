# Bug list — open after Shatner cascade run

**Date:** 2026-05-03 evening
**Context:** post Life Map quote-fix commit; pre-Shatner-cascade run
**Update protocol:** check off when fixed; add Shatner cascade row when run completes

---

## Open bugs (strict — must fix before parent session)

| # | Bug | Severity | Status | Notes |
|---|---|---|---|---|
| 1 | Silence visual cue not visible during pause | AMBER | Open | Harness reports `visual_cue_present=false` on every run. Cue is **defined** in `presence-cue.js` but the test setup may be racing the mount. Verified: `idle_block_log_seen=true` (suppression works); spoken cue stays suppressed. The visual side just doesn't render in time for the harness probe. Need to: (a) trace `presence-cue.js` mount path; (b) add a `wait_for_selector('[data-purpose="visual_presence"]')` before the visibility check |
| 2 | Duplicate reply_text polling in harness | AMBER | Open | rehearsal_quick_v3+v4 both logged `WARN — duplicate reply_text detected, re-polling for fresh reply`. Lane G.1 dedup wrapper catches it but emits the warning. Root cause likely a console event ordering issue — the `lori_reply` event fires twice for some streamed turns. Cosmetic warning, not blocking. Fix sized: ~5 lines in `_wait_for_fresh_lori_turn` to suppress the warn when the second hit's text matches the first byte-for-byte |
| 3 | T1/T2 showed `…` placeholder text in v4 | AMBER | Open | rehearsal_quick_v4 turn results: T1 lori_reply=`…`, T2 lori_reply=`…`. The placeholder was captured because `_wait_for_fresh_lori_turn` returned the bubble text before the streaming had completed. Possible fix: require min word count > 1 OR wait for the `[chat-turn] complete` console marker. Did not occur in v3 (where T1+T2 had real text), so may be a flake on v4 specifically |

---

## Resolved (this session)

| # | Bug | Resolution |
|---|---|---|
| 4 | BUG #1 QF steamroll on "what day is it" | Fixed in regex extension to `_isConversationalNonAnswer` (commit prior) |
| 5 | BUG #3 menu-offer leak | Fixed by flipping `HORNELORE_INTERVIEW_DISCIPLINE` default to ON (commit prior) |
| 6 | BUG #4 countdown timer | Removed entirely — Lane H park (commit prior) |
| 7 | BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 | Fixed in `_lvInterviewRenderLifeMap` onclick HTML quote bug. Single-line patch matching Today button pattern (commit "fix: BUG-LIFEMAP root cause + remove countdown timer") |

---

## Known gaps (NOT bugs — by design or scoped to a separate WO)

| Item | Why it's not a bug | WO that opens it |
|---|---|---|
| Timeline doesn't react to era-click | Pre-existing wiring gap — `lv-interview-focus-change` event has zero subscribers. Surfaced as INFORMATIONAL in Shatner cascade. | WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 (parked, ready to land) |
| Peek at Memoir doesn't reframe by era | Same as above — popover has no era-scroll behavior | WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 |
| Lori doesn't recall last era conversation | Per-era memory not implemented — `compose_memory_echo` builds from BB blob + spine, not transcript history | WO-LORI-ERA-RECALL-01 (future, prerequisites: Timeline+Memoir wiring above) |
| BUG #2 — "basics down" cycle-vs-data gate | Patch B walk-completion gate fires on cycle exhaustion not data presence. Needs `_findNextEmptyPersonalField` patch + handoff guard | WO-LORI-WALK-COMPLETION-01 (parked — separate from Life Map work) |
| BUG #5 — Life Map historical eras require identity | NOT a real product gate — audit doc found no enforcement in product code; Christopher's identity_complete=true and his historical eras still failed (the actual cause was the onclick HTML bug, now fixed). The harness explicitly completes identity before clicking historical eras as defensive scaffolding only. | None — closed by Life Map quote-fix |

---

## Pending Shatner cascade — fill in after run

```
[ ] Shatner cascade overall: ___
[ ] Today step:
    [ ] clicked_ok: ___
    [ ] era_click_log_seen: ___
    [ ] lori_prompt_log_seen: ___
    [ ] currentEra == "today": ___
    [ ] lori_replied: ___
    [ ] lori_clean (Q≥1, nest=0, menu=0): ___
[ ] Coming of Age step:
    [ ] clicked_ok: ___
    [ ] era_click_log_seen: ___
    [ ] lori_prompt_log_seen: ___
    [ ] currentEra == "coming_of_age": ___
    [ ] lori_replied: ___
    [ ] lori_clean: ___
[ ] Informational rows (Timeline + Memoir): expected to show "stale" notes
    [ ] Today timeline_active_era_id: ___ (expected: today, actual likely: empty/stale)
    [ ] Coming of Age timeline_active_era_id: ___ (expected: coming_of_age, actual likely: stale)
    [ ] Today memoir_top_section_text: ___ (expected: "Today", actual likely: "Earliest Years" or similar)
    [ ] Coming of Age memoir_top_section_text: ___ (expected: "Coming of Age", actual likely: "Earliest Years")
```

If both era steps PASS strict and the Informational rows show the expected
"stale" pattern, **the Life Map quote-fix is verified end-to-end** and we
can move forward to:

1. Bank the cascade test commit
2. Open WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 next (5-15 line follow-up)
3. Move to BUG #2 walk-completion or first parent-narrator dry-run
