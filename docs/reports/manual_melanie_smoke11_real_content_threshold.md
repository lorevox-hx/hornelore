# Smoke 11 — Melanie Carter Real-Content Era Excerpt Threshold Test

**Date:** 2026-05-06 (afternoon → evening)
**Operator:** Chris (driving Chrome MCP through Cowork agent)
**Narrator:** Melanie Carter (auto-generated test narrator, two sessions on disk)
**Branch SHA + dirty state:** ahead of `origin/main` by 2 commits at smoke time (Phase 1c bundle + parent-session-readiness docs commit), tree clean except for this report
**Flag value:** `HORNELORE_MEMORY_ECHO_ERA_STORIES=1` after re-add (was inadvertently removed earlier in session by a `sed -i '218,219d'` dedup that took out L217 too)
**`_ERA_EXCERPT_MIN_CONTENT_TOKENS`:** 6 (lowered from 8 after standalone smoke caught false-rejects on 7-token narrator stubs)
**`_seed_age_years` UnboundLocalError:** ZERO new occurrences post-restart (147 stale errors in api.log were all from the pre-v11-rollback window 13:49–14:13; v11 rollback removed the consumer at L2245, dead-code definition cleaned up in this session's prompt_composer commit)

## Final Grade: **AMBER**

Architectural code is correct end-to-end. Phase 1 binding verified at the data layer with 100% era coverage on post-era-click user turns. Phase 1c user-visible "What you've shared so far" section did not render in either of the two manual probes — first probe was hampered by the flag being missing from .env, second probe ran in a fresh post-restart session that didn't carry the era-walk content. Cross-session readback is the actual product gap, captured as Phase 1d follow-up (#52).

---

## What Worked (GREEN)

### Phase 1 — archive write-time era binding
Direct dump of `transcript.jsonl` for session `switch_moumhein_1mru` showed:

```
Era distribution (user turns only):
  <NO ERA>             = 4   ← identity flow (before first era click) — expected
  earliest_years       = 5
  early_school_years   = 3
  adolescence          = 3
  coming_of_age        = 2
  building_years       = 3
  later_years          = 2
  today                = 4
```

Every era I clicked + every user turn that followed it carried the correct canonical era_id. The four `<NO ERA>` turns are the early identity flow (name/DOB/POB) before any Life Map click, which is correct behavior — runtime71 didn't have current_era set yet because the era walk hadn't started.

### Phase 1c smoke-test calibration
Standalone unit smoke of `_select_era_excerpts()` caught a real bug pre-deploy: the original `_ERA_EXCERPT_MIN_CONTENT_TOKENS = 8` threshold rejected legitimate 7-token narrator stubs ("These days I am quiet but content most afternoons" / "We walked to school through the snow, me and my brother"). Lowered to 6, re-tested 12 scenarios — all green:
- User-only filter (assistant turns dropped at render AND bin)
- Trivial-token gate (yes/no/I-dunno rejected)
- Filler stripping (Well/Um/I-think prefixes)
- First-sentence rule
- 80-char cap
- SYSTEM_-prefix skip (operator directives don't count as narrator content)
- Canonical era ordering (earliest_years → today)
- Multi-era pipeline

### `_seed_age_years` regression
Already fixed by v11 rollback; this session removed the 5 dead-code definition lines so the forward-reference class can't return. AST + 14 empirical scenarios all clean.

### Patch C reflection shaping
Lori reflected concrete narrator anchors on every era turn:
- Earliest Years: "That kitchen and the lake — two vivid memories"
- Adolescence: "That's a powerful lesson to learn at a young age"
- Coming of Age: "David's kindness at the church picnic has stuck with you"
- Later Years: "Walking the lake road was a source of comfort for you"
- Today: "Being quiet and content in the afternoons is a peaceful feeling"

### Era click → grounding rule
On clicking Earliest Years, Lori opened with: *"I have Duluth, Minnesota as your earliest home — what comes to mind when you picture those years there?"* — using the seeded POB rather than asking from cold. WO-PROVISIONAL-TRUTH-01 Phase A read-bridge working as designed.

### Identity capture
Name → Melanie Carter ✓
DOB → 1952-04-12 ✓ (header read "age 74" — math correct)
POB → Duluth, Minnesota ✓
brother → Paul ✓ (correctly extracted relation from "me and my brother Paul")

---

## What Didn't Work (AMBER → next steps)

### "What you've shared so far" section did not render in either probe
**Probe 1 (same-session, flag off):** Asked "what do you know about me so far?" at end of era walk. Memory_echo reply rendered cleanly with Identity / Family / Notes / What I'm less sure about sections + footer "Based on: profile, interview projection, session notes" — but no era-stories block. Root cause: `HORNELORE_MEMORY_ECHO_ERA_STORIES` flag was missing from .env (sed dedup error). Render gate returned False; entire block silently skipped.

**Probe 2 (post-restart, flag on):** After re-adding flag and restarting stack, navigated back to Melanie and re-asked the same probe. Section still missing. Root cause: chat_ws allocated a new session_id (`switch_mouvp9ki_8des`) post-restart. `peek_at_memoir.build_peek_at_memoir` reads from that session only; the era walk content lives in `switch_moumhein_1mru`. era_buckets returned empty → silent skip → no section header.

### Cross-session readback gap (Phase 1d) — captured at task #52
This is the real user-visible gap. The architectural code is correct for the same-session case, but the realistic narrator usage pattern (return the next day, ask "what do you know about me?") needs peek to read all sessions for the narrator and merge chronologically. ~20-line fix in `build_peek_at_memoir`. Sequenced behind parent-session readiness blockers.

### Era-fragment Lori responses (still present)
Two fragmenty responses observed: "The community you lived in during those early school years?" and "It affected your family during that time?" — the era-fragment-repair guard from stack-warm V isn't catching this exact shape (interrogative noun phrase with no main verb). Separate bug, parked.

### BUG-LORI-MIDSTREAM-CORRECTION-01 Phase 2 fired but produced confused response
Sent "Actually, we only had two children, not three." Lori detected it as a correction but responded: *"I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'."* — generic deflection rather than a clean update of the children count. Phase 2 routes detection but doesn't yet wire to the actual write path. Existing task.

### Type C extractor binding error (BINDING-01 lane)
"I drink tea by the window and watch the light move across the floor." → extractor routed "quiet but content most" (from the previous turn) to `personal.fullName`. Shadow Review queue caught it. Classic Type C narrative-prose-as-identity-field error — BINDING-01 lane already covers this.

---

## Header / Footer Verification

**Footer in memory_echo reply:** "Based on: profile, interview projection, session notes."
- "profile" → canonical truth read from profile_json ✓
- "interview projection" → provisional truth read from projection_json (Phase A read-bridge) ✓
- "session notes" → safety-filtered transcript read from archive ✓ — proves Phase 2 plumbing is alive even though the era-stories sub-section was empty

**No system-tone language in narrator-facing output:**
- ✓ No "era stories"
- ✓ No "recent turns"
- ✓ No "transcript"
- ✓ No "source"
- ✓ No "(not on record yet)" — Phase 1a improvement holding

---

## Net Recommendations

1. **Phase 1d cross-session readback (#52)** is the real user-visible gap. Small fix, but sequence behind today's two new parent-session blockers.

2. **BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01 (#50)** — narrator can't see what they're dictating in real-time. High-impact for Janice/Kent.

3. **BUG-LORI-CHAT-SCROLL-REGRESSION-01 (#51)** — conversation pane not auto-scrolling. Task #5's earlier fix appears to cover a narrower path than interview-mode.

4. **`_seed_age_years` dead code cleanup** is in this session's commit — defensive, not a behavior change.

5. **Phase 1c is architecturally complete.** Same-session readback would work given a fresh probe-in-same-session test (not yet executed). Cross-session is Phase 1d's lane.

## Artifacts captured

- `docs/reports/test23_two_person_resume_test23_v10_failures.csv` (banked earlier)
- `docs/reports/test23_two_person_resume_test23_v11_failures.csv` (banked earlier)
- `docs/specs/PARENT-SESSION-MANUAL-WALK-2026-05-06.md` (banked earlier)
- This file

## Tasks created during smoke

- #50 BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01
- #51 BUG-LORI-CHAT-SCROLL-REGRESSION-01
- #52 WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1d cross-session readback
