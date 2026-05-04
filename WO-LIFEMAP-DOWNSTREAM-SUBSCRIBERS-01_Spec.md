# WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01

**Status:** PARKED — opens after Shatner cascade confirms the Life Map quote-fix landed
**Severity:** YELLOW (UI cohesion gap, not behavioral regression)
**Owner:** TBD
**Authored:** 2026-05-03 evening
**Lane:** Lori-behavior parallel to extractor lane

---

## Why this WO exists

The Life Map quote-fix (commit landing the `JSON.stringify` → single-quote
correction in `_lvInterviewRenderLifeMap`) **reconnects the click chain
end-to-end through Lori**: click → popover → Continue → state.session.currentEra
update → `sendSystemPrompt` → backend prompt_composer reads `current_era` →
Lori asks an era-anchored question.

But the click chain has **two downstream consumers that never subscribed**
to era-change events. The Shatner cascade test (TEST-21 in the rehearsal
harness) surfaces them as INFORMATIONAL rows and the cascade markdown
table flags them with the explicit note: *"Timeline (chronology accordion)
and Peek at Memoir (popover) do NOT auto-react to era-click events today."*

This WO closes that gap.

---

## What's broken (verified by code-read 2026-05-03)

### Gap 1 — Timeline (chronology accordion)

**File:** `ui/js/chronology-accordion.js`

- L128-129 reads `state.session.currentEra` to highlight the active year-band
  with `cr-active-era` class
- BUT only renders during `crInitAccordion(narrator_id)` which fires on:
  - Narrator load (post-onboarding)
  - identity_complete event
  - Manual operator refresh
- **Has zero subscribers** to:
  - `state.session.currentEra` mutations
  - `lv-interview-focus-change` CustomEvent dispatched by `_lvInterviewSelectEra` (`app.js` L738)
- **Effect:** narrator clicks "Coming of Age" → `currentEra='coming_of_age'`
  → Lori asks the era question → but Timeline column still highlights
  whatever era was active at last narrator-load. Stays stale until next
  `crInitAccordion` invocation.

### Gap 2 — Peek at Memoir (inline card + popover)

**Files:** `ui/js/app.js` (`_lvInterviewRenderLifeMap` inline card),
`ui/hornelore1.0.html` (`memoirScrollPopover`),
`lv80BuildMemoirSections` in `hornelore1.0.html`

- Inline body div `lvInterviewPeekFloaterBody` contains hard-coded placeholder
  text *"Your story will appear here as you tell it…"* — never updated
- The "Open memoir" button opens `memoirScrollPopover` which calls
  `lv80BuildMemoirSections` — always renders ALL 7 eras top-to-bottom
- **Does not auto-scroll** to the active era when opened
- **Does not subscribe** to era-change events
- **Effect:** clicking an era doesn't surface what's already captured
  for that era. Operator must scroll memoir manually.

---

## Scope

Minimal first cut. Two changes, ~20 lines total. Defer richer behavior
(per-era memory recall, era-scoped DB queries, scroll-with-easing) to
follow-up WOs.

### Change 1 — Timeline subscribes to era-change

**File:** `ui/js/chronology-accordion.js`

Add at the bottom of the IIFE (or wherever module init lives):

```js
// WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 — react to Life Map era click.
// _lvInterviewSelectEra dispatches lv-interview-focus-change on every
// click. Re-render the accordion on receive so the active-era highlight
// stays in sync with state.session.currentEra. crInitAccordion() is
// idempotent and narrator-scoped — safe to call repeatedly.
window.addEventListener("lv-interview-focus-change", function (ev) {
  try {
    var pid = (window.state && window.state.person_id) || null;
    if (pid && typeof window.crInitAccordion === "function") {
      window.crInitAccordion();
    }
  } catch (e) {
    console.warn("[chronology-accordion] focus-change handler threw:", e);
  }
});
```

### Change 2 — Memoir popover scrolls to active era on open

**File:** `ui/hornelore1.0.html` — find the `memoirScrollPopover` open
handler (search for `memoirScrollPopover?.showPopover` and trace back to
the click handler).

Add post-open scroll behavior:

```js
// WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 — when memoir opens after an
// era click, scroll the matching section into view.
function _scrollMemoirToActiveEra() {
  var era = (window.state && window.state.session && window.state.session.currentEra) || null;
  if (!era) return;
  // Memoir sections render with data-era-id="<era_id>" on the section
  // wrapper (see lv80MakeSection / lv80BuildMemoirSections).
  var section = document.querySelector('#memoirScrollPopover [data-era-id="' + era + '"]');
  if (section && typeof section.scrollIntoView === "function") {
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}
// Wire into the existing "open memoir" click handler — both the inline
// peek card button and any other entry point. Call _scrollMemoirToActiveEra
// after showPopover() with a brief setTimeout to let layout settle.
```

(If memoir sections don't yet have `data-era-id` attributes, add them in
`lv80MakeSection` first — that's a 1-line change there.)

---

## Acceptance — re-run Shatner cascade after this lands

Before:
```
Today / Coming of Age:
  Timeline active era_id: (empty) or stale value
  Memoir top heading: "Earliest Years" (always first)
```

After:
```
Today:
  Timeline active era_id: today
  Memoir top heading: contains "Today"

Coming of Age:
  Timeline active era_id: coming_of_age
  Memoir top heading: contains "Coming of Age"
```

Cascade severity stays PASS. Informational rows flip from notes-present
to notes-empty. The README/HANDOFF can stop calling out the gap.

---

## NOT in scope (separate WOs)

- **Per-era memory recall** ("Last time we talked about Building Years
  you mentioned the aluminum plant…"). That needs a backend
  `get_turns_by_era(narrator_id, era_id)` accessor + `compose_memory_echo`
  extension. Tracked separately as **WO-LORI-ERA-RECALL-01**.

- **Memoir filtering** (show ONLY the active era, hide others). Today's
  spec is "all 7 eras visible, scroll to active" because the operator
  may want to compare adjacent eras. Filter mode is a separate UX
  question.

- **Timeline auto-expand of the active era's decade band**. Optional
  polish; can wait for live operator feedback.

- **Era-scoped story_candidates display in the inline Peek card**
  (`lvInterviewPeekFloaterBody`). The inline card is a separate render
  path from the popover; making it era-reactive is its own ~30-line
  change.

---

## Cross-references

- **Life Map quote-fix:** the commit immediately preceding this WO. The
  one-line `JSON.stringify` → single-quote fix in
  `_lvInterviewRenderLifeMap`.
- **Shatner cascade test:** TEST-21 in `run_parent_session_rehearsal_harness.py`.
  This WO closes the INFORMATIONAL notes the cascade currently emits.
- **WO-LORI-ERA-RECALL-01:** future WO for per-era memory; this WO is a
  prerequisite (Timeline + Memoir need to react before Lori's recall
  surface makes sense).
- **CLAUDE.md design principle:** "Life Map is the only navigation
  surface." This WO makes the navigation surface actually navigate the
  rest of the UI, not just trigger Lori.
