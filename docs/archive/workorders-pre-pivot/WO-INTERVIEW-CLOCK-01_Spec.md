# WO-INTERVIEW-CLOCK-01 — Narrator-visible orientation clock

**Title:** Narrator-visible orientation clock for the Interview tab
**Status:** SCOPED — ready to build
**Date:** 2026-05-01
**Lane:** Narrator dignity / parent-session readiness / older-adult UX
**Source:** Chris's clock mockup memo + uploaded `hornelore_interview_clock_mockups.jsx` (2026-05-01); placement + variant lock 2026-05-01 ("c on the lower left side by the mic but do them all in that location")
**Blocks:** Nothing (additive). Pairs naturally with WO-PARENT-KIOSK-01 install.

## Locked decisions (2026-05-01)

- **Placement: lower-left of the narrator chat region, adjacent to the mic affordance.** Not in the topbar. Not floating in the upper-right. The narrator's natural eye-travel during input lands in the lower-left — the orientation card sits there, where it's already in peripheral vision.
- **Lead variant: C (parchment "Right now" card).** B (slate header-style card) and A (floating pill style) are built *in the same lower-left slot* as alternates for visual comparison, not in different positions. The variant question is style; the placement question is settled.
- **The header-bar variant from the original mockup is DROPPED.** The narrator topbar carries identity + controls; orientation lives in the chat region.

---

## Mission

Give the narrator a steady orientation anchor — *what time is it, what day is it, where am I* — without making the interview feel clinical, technical, or dashboard-y. Older-adult narrators (Kent, Janice) should be able to glance at the screen mid-session and re-anchor in real-life time/place without asking Lori, without operator intervention, and without the system feeling like a monitoring surface.

The clock is a calm presence, not a notification. It never claims attention. It never changes shape on safety events. It updates once per minute. It reads as "you are here, today" — not as "the system is tracking you."

---

## Locked design rules

These are non-negotiable. They apply to whichever variant ships.

1. **Narrator-visible only.** Lives inside the Narrator Session / Interview tab. Never appears in the Operator tab, the Bug Panel, or any operator-only surface. Passes the no-operator-leakage check.
2. **No system-tone outputs.** No "device_context", no UTC offsets, no timezone abbreviations as a primary label, no "monitoring" or "tracking" copy, no technical-monitor framing. Reads like a wall clock, not a status bar.
3. **No dual metaphor.** The clock's "Today" is the same `today` era_id the canonical Life Map shows. There is one Today across the system; the clock surfaces it, the Life Map surfaces it, both reference the same source of truth.
4. **No softened-mode visual change.** When `safety.scan_answer()` flags a turn or Lori's tone shifts to softened, the clock does not flicker, recolor, hide, or move. Tone shifts live in Lori's reply, never in the orientation surface.
5. **No reset on narrator switch.** The clock's data source is system clock + static config; switching narrators changes nothing about it. Time and place do not depend on narrator identity.
6. **Once per minute.** No seconds, no blinking, no animated transitions. Updates via `setInterval(_, 60_000)` that re-reads `new Date()` (re-derive, do not accumulate — DST and clock drift handle themselves).
7. **Plain DOM, no framework.** Vanilla JS + `lori80.css` using existing CSS vars. The uploaded React/Tailwind mockup is a design artifact only; the build is plain DOM matching the rest of the narrator room.

---

## Variant decision (C lead, B + A as alternates in the same slot)

All variants live in the same locked location: lower-left of the narrator chat region, adjacent to the mic. The variant axis is purely *visual style*; the placement axis is settled.

### Lead: Variant C — Warm parchment "Right now" card

Cream parchment-styled card. Serif/warm typography on cream `#fdf7ea` with brown accent `#7b6544`. Small caps "Right now" eyebrow, large serif time, date below, place beneath. Reads as a *physical object* sitting on the narrator's desk — not a UI widget. Default for all narrators.

### Alternate: Variant B — Slate orientation card (same slot)

Same content and dimensions as C, rendered in dark slate matching the chat column palette. Available via the operator-side toggle for narrators who find the parchment too warm or who want the surface visually quieter against the dark theme.

### Alternate: Variant A — Pill style (same slot)

Same content and dimensions as C, rendered as a compact rounded pill (the upper-right floating-pill mockup ported to the lower-left slot — same shape, different position). Lightest visual weight; available for narrators who want minimal real estate.

### Rejected: Variant D — Bottom-right rail (mockup original)

The bottom-right card next to the input field competes with the typing surface for attention. The lower-*left* placement (Chris's call) avoids the input-field collision while keeping the orientation cue in peripheral vision near the mic.

### Rejected: Header-bar variant (original spec proposal)

Dropped. The narrator topbar carries identity + controls (mic / cam / pause / break / record-voice). Mixing orientation into that surface clutters the controls row and forces eye-travel up away from the input.

### Ship discipline

C is the default. B and A are operator-toggleable alternates via `localStorage["lvClockVariant"] in {"C","B","A","off"}`. After Phase 6 acceptance with parents, the chosen variant is the steady-state default *for that narrator id*; the other variants stay buildable but dormant.

---

## Five product decisions locked in this WO

These are the five sharpenings from Chris's memo. They apply to both B and C.

### 1. Location source

**Static config in `.env`. Single key, plain string. No browser geolocation, no IP-geolocation.**

```
LOREVOX_NARRATOR_LOCATION="Las Vegas, New Mexico"
```

Rationale: browser geolocation requires a permission prompt, which is unacceptable on a parent kiosk where the install is one-shot and the narrator should never see permission dialogs. IP-geolocation is wrong often enough to be alarming when wrong (parent reads "Phoenix, Arizona" while sitting in Las Vegas). Static config is the only option that's calm, correct, and silent.

When the key is unset or empty, the place line collapses (clock still renders time + date — place is optional in the layout, not load-bearing). Default in `.env.example` is empty string.

For travelling narrators (rare for parents, possible for Christopher), a future flag can opt into a different source. Out of scope for Phase 1.

### 2. No timezone abbreviation as a primary label

Drop "Mountain Time", "MT", "MDT", "UTC-7", and all variants from the visible surface. Kent and Janice have lived in MT for 50 years; the label is noise. The browser's `Intl.DateTimeFormat` already produces locale-correct output without surfacing the abbreviation.

If a future cross-timezone narrator (Christopher travels) needs the timezone shown, gate behind a separate `LOREVOX_NARRATOR_SHOW_TIMEZONE=0` flag. Not in Phase 1.

### 3. Time-of-day textual label inline with digital time

Pair every digital time reading with a textual time-of-day label. Examples:

- "7:42 PM · Friday evening"
- "9:14 AM · Wednesday morning"
- "1:30 PM · Sunday afternoon"
- "11:45 PM · Friday late evening"

Bands (24-hour input → label):

| Hour range | Label |
|---|---|
| 04:00–06:59 | "early morning" |
| 07:00–11:59 | "morning" |
| 12:00–16:59 | "afternoon" |
| 17:00–19:59 | "evening" |
| 20:00–22:59 | "late evening" |
| 23:00–03:59 | "night" |

The day-of-week is always full ("Friday", not "Fri"). The combined label uses `·` as the separator with a thin space on each side; never an em dash, never parentheses. The textual layer carries the cognitive orientation; the digital layer carries accuracy.

### 4. Canonical "Today" tie

The clock's data source for "today" is the same `today` era_id surfaced by the canonical `LV_ERAS` registry (`ui/js/lv-eras.js` + `server/code/api/lv_eras.py`). When the clock is visible AND the Life Map is visible AND the Today era exists in the rendered map, the Today era button gets a subtle visual continuity cue — same accent or a thin emerald connecting strip that runs from the clock to the Today button.

Implementation: a single shared CSS variable `--lv-today-accent` consumed by both surfaces. No JS coupling required; both surfaces independently check the canonical registry and apply the same var.

This is the locked Hornelore design rule "no dual metaphors" applied to the clock: there is one Today, surfaced consistently.

### 5. Plain DOM, no React, no Tailwind

The uploaded JSX mockup is a design artifact. The build is plain DOM matching the rest of `ui/hornelore1.0.html`. Use:

- IDs prefixed `lv10dClock*` matching the existing `lv10d*` namespace.
- Existing CSS vars from `lori80.css` for color, spacing, typography.
- Variant B styling: extend the existing `.lv-narrator-topbar` ruleset with a sibling `.lv-narrator-orient` row.
- Variant C styling: new `.lv-narrator-orient-card` ruleset with parchment palette as inline custom-property overrides scoped to the card (does not bleed to other surfaces).
- Update via `setInterval(_lv10dClockTick, 60_000)` in a new `ui/js/narrator-clock.js` IIFE matching the same module pattern as `bug-panel-eval.js` and `safety-banner.js`.

---

## Phases

### Phase 1 — Data layer (shared between B and C)

`ui/js/narrator-clock.js` (new). Pure data + render. No tab-switch logic.

- IIFE module exposing `window.lvNarratorClockRefresh()` for manual re-tick.
- `_renderClock()` reads `new Date()` + `window.LOREVOX_NARRATOR_LOCATION` (set at boot from a `<meta name="lorevox-narrator-location" content="…">` injected by server-side template) + canonical `today` era_id.
- Time formatter: `Intl.DateTimeFormat(undefined, {hour:'numeric',minute:'2-digit',hour12:true})`.
- Date formatter: `Intl.DateTimeFormat(undefined, {weekday:'long',year:'numeric',month:'long',day:'numeric'})`.
- Time-of-day band lookup per the table in §3.
- `setInterval(_renderClock, 60_000)`. First render immediate on DOMContentLoaded; not gated by tab visibility (cheap; runs once a minute).
- No console logs in steady-state. One `[clock] init src=static loc="<loc>"` line at boot for operator log greppability.

**Files touched:** `ui/js/narrator-clock.js` (new), `ui/hornelore1.0.html` (script tag + meta tag injection), `server/code/api/main.py` (one-line meta-tag template injection from env).

**Acceptance:** opening the narrator room renders time + date + (place when set) within 1s of DOMContentLoaded; the textual time-of-day label matches the band table; updating the system clock and waiting 60s re-renders without page reload.

### Phase 2 — Lower-left chat-region slot + base shell (shared across variants)

A single fixed slot in the narrator chat region, lower-left, positioned via CSS to sit just above or beside the mic affordance without overlapping the input field. The slot is variant-agnostic — same dimensions, same anchor, same z-index. Variants are CSS skins applied via `[data-variant="C|B|A"]`.

Mounted in `ui/hornelore1.0.html` near the chat input as `<aside class="lv-narrator-orient" id="lv10dClock" data-variant="C">` (initial variant is C; switched dynamically via Phase 5 selector).

`ui/css/lori80.css` adds:
- `.lv-narrator-orient` base ruleset: position (lower-left of chat region, ~16px from left edge, ~12–16px above the input field row), width ~240–280px, padding, shadow, border-radius. Fixed dimensions across variants so swapping does not relayout the chat column.
- Z-index layered above the chat scroll region but below any modal/overlay.
- Responsive collapse at <900px wide: card shifts to a single horizontal line, smaller, but stays in the lower-left slot.

**Acceptance:**
- Slot renders at lower-left of the chat region on initial load.
- Does not overlap the input field at any supported width (1024×768, 1280×800, 1920×1080).
- Does not occlude the mic button or any topbar control.
- Switching `data-variant` between `C`, `B`, `A` via dev tools re-skins without relayout.
- Slot is z-indexed below modals (Take a Break overlay does not get covered).

### Phase 3 — Variant C skin (parchment, lead default)

`ui/css/lori80.css` extension. `.lv-narrator-orient[data-variant="C"]` rules with parchment palette as scoped custom-property overrides:
- `--lv-orient-bg: #fdf7ea`
- `--lv-orient-fg: #2a241a`
- `--lv-orient-accent: #7b6544`
- Serif typography for time and date
- Small-caps eyebrow "Right now" (or whatever copy locks in §Open Questions)

**Acceptance:**
- Time + date + place readable at 1024×768 from typical seated narrator viewing distance.
- Parchment palette stays scoped to the card; no bleed to chat bubbles, controls, Life Map.
- Time renders in serif at ~28–32px; eyebrow at ~10–11px small caps.
- Cream-on-dark contrast meets WCAG AA against the surrounding chat-region background.

### Phase 4 — Variant B and A skins (alternates, same slot)

`.lv-narrator-orient[data-variant="B"]` — slate skin matching the chat-column palette (dark background, light text, modest border, sans-serif typography). Same dimensions and anchor as C; just a different visual weight.

`.lv-narrator-orient[data-variant="A"]` — compact pill skin (rounded-2xl, smaller padding, single-line layout when possible, slate-with-emerald-accent palette). Same anchor; visually lightest.

**Acceptance:**
- Toggling `lvClockVariant` localStorage key cycles through C / B / A / off without page reload (Phase 5 wires the toggle).
- All three variants render the same time + date + place text — only the visual skin changes.
- No variant bleeds palette outside the card.
- Variant `off` removes the card entirely without leaving an empty slot or layout gap.

### Phase 5 — Variant selection logic

`ui/js/narrator-clock.js`. Default variant is **C for all narrators** at first launch (Chris's lock 2026-05-01). Operator-side override via `localStorage["lvClockVariant"] in {"C","B","A","off"}` settable from the Bug Panel four-way toggle.

Bug Panel control: a small "Clock: C / B / A / off" toggle in the existing operator dashboard that writes the localStorage key and triggers re-render. Operator-only — never appears in the narrator surface. The toggle reads the current value on dashboard render to highlight the active state.

After Phase 6 real-narrator acceptance, if a particular narrator id is locked to a non-default variant, the operator can pin it via `localStorage["lvClockVariant.<narratorId>"]` (per-narrator override that wins over the global key).

**Acceptance:**
- First launch with no localStorage shows variant C.
- Setting `lvClockVariant="B"` from the Bug Panel re-renders to slate within one tick.
- Setting `lvClockVariant="off"` hides the card without reload.
- Setting `lvClockVariant.kent="A"` while narrator is `kent` and global is `C` shows pill skin for kent only; switching to `christopher` returns to C.

### Phase 5 — Canonical Today tie

CSS variable `--lv-today-accent` defined once at the root in `lori80.css`. Both `.lv-narrator-orient` and `.lv-narrator-orient-card` reference it for a small accent glyph or strip. The Life Map's Today era button (already styled emerald in `ui/js/life-map.js`) reads from the same var.

No JS coupling. The visual continuity is purely a shared CSS var.

**Acceptance:**
- Changing `--lv-today-accent` in dev tools updates both the clock surface and the Life Map Today button.
- Removing the Today era from the canonical `LV_ERAS` registry (hypothetical) does not break the clock — the clock still renders time + date, just without the accent tie.

### Phase 6 — Acceptance gate (the parent-session test)

The locked acceptance for declaring this WO done is a real-narrator test, not a unit test:

> Kent or Janice, asked unprompted "what day is it?" by the operator at any point at least 5 minutes into an interview session, can read the answer off the lower-left orientation card without operator intervention, without asking Lori, and without leaving the chat column.

Run with both parents at least once each before declaring Phase 6 closed. Operator notes the variant active during the test (default C; operator may switch to B or A if C reads wrong for that parent) and which parent.

If the test fails with C (parent looks confused, asks Lori, asks the operator), the operator switches to B for the next session and re-runs. If B also fails, try A. If all three fail for the same parent, the WO returns to design — the placement or content strategy needs rework, not a fourth variant.

### Phase 7 — TEST-09 harness hook (free win)

Add a Playwright assertion to `scripts/ui/run_parent_session_readiness_harness.py` TEST-09 that reads the chat-region orientation card DOM directly:

```python
clock_text = page.locator("#lv10dClock").inner_text(timeout=3000)
assert today_date_string() in clock_text  # e.g. "Friday, May 1, 2026"
```

This replaces (or supplements) the existing TEST-09 check that asserts Lori's *answer* contains the date. The DOM-read assertion is deterministic; the LLM-answer assertion is probabilistic. Keep both — but the DOM-read becomes the load-bearing one. The Lori-answer assertion drops to non-blocking (informational, not gating).

**Acceptance:** TEST-09 in the harness shows DETERMINISTIC PASS even when the LLM stochastically fails to surface the date in its reply.

---

## Acceptance criteria summary

The WO is closed when **all** of the following hold:

- [ ] Phase 1 data layer renders correctly at boot and updates once per minute.
- [ ] Phase 2 lower-left chat-region slot lands without overlapping input or topbar.
- [ ] Phase 3 Variant C parchment skin renders correctly at all supported widths.
- [ ] Phase 4 Variant B and A skins render in the same slot via data-attribute swap.
- [ ] Phase 5 variant selection respects operator localStorage override (global + per-narrator).
- [ ] Phase 5 canonical Today tie shares a single CSS var across the clock and Life Map.
- [ ] Phase 6 real-narrator test passes with at least one of Kent or Janice (and ideally both).
- [ ] Phase 7 TEST-09 harness hook is deterministic.
- [ ] No clock surface appears in the Operator tab, Bug Panel narrator-facing previews, or any non-narrator route.
- [ ] No softened-mode visual change to the clock surface (verified by toggling softened-mode flag in Bug Panel).
- [ ] No reset on narrator switch (clock data is system-clock + config, narrator-id-independent).
- [ ] Updates do not consume more than 1 ms of main-thread CPU per minute (cheap by construction; verify in Performance tab).
- [ ] Static location config falls back gracefully when unset.
- [ ] No console spam in steady-state (one boot line, then silence).

---

## Out of scope (explicit non-goals)

- Browser geolocation. Static config only in Phase 1.
- Timezone abbreviation display. Behind a flag for future Christopher / travelling narrator.
- Sub-minute updates. No seconds, no realtime ticking second hand, no animation.
- Operator-facing clock surface. The clock is narrator-only.
- Time-zone change detection during a session. The kiosk doesn't move.
- Calendar / agenda integration. Out of scope; this is an orientation anchor, not a calendar.
- "Time since last session" / "Days since last conversation". Surfaces back into longitudinal tracking that the SESSION-AWARENESS-01 banned-vocab spec rules out.

---

## Lorevox graduation note

This WO graduates cleanly to Lorevox after Phase 6 acceptance with at least one parent. Reasons:

- Narrator-dignity-aligned (Lorevox `Product Principles` #2 hide-the-scaffolding + #8 recollection-not-interrogation).
- Zero extractor risk; no LLM coupling.
- Generic — strip is `HORNELORE_*` → `LOREVOX_*` env keys; `LV_ERAS` registry is already cross-product canonical.
- Closes a soft gap in Lorevox's identity-first onboarding posture (currently no orientation surface).

Add to `docs/lorevox/GRADUATION_CANDIDATES_2026-05-01.md` Section A as candidate **A11** when Phase 6 closes.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Parchment palette (Variant C) clashes with the dark-mode chat column. | Phase 3 acceptance includes a side-by-side visual review at 1024×768 before parent test. If the visual contrast feels jarring, B or A picks up via the operator toggle. |
| Lower-left card overlaps the mic button or input field at narrow widths. | Phase 2 acceptance tests at 1024×768, 1280×800, and the smallest kiosk width. Card collapses to a single horizontal line under 900px. |
| Card occludes part of a long Lori reply that scrolls into the lower-left. | The card sits above the chat scroll boundary, not over the scroll content. The chat region's existing scroll container is the affordance the card lives next to, not on top of. Verify in Phase 2 acceptance. |
| Static location wrong if narrator moves. | Out of scope for Phase 1. Operator updates `.env` and restarts on relocation. |
| Clock interpreted as a notification or alert by parent. | Phase 6 real-narrator test catches this; rolls to other variant or returns to design. |
| Browser locale produces wrong format ("1/5/2026" vs "Friday, May 1, 2026"). | `Intl.DateTimeFormat` with explicit options is locale-stable. Verify with `en-US` and `en-CA` browser locales in Phase 1. |
| Clock keeps rendering during softened-mode visual changes elsewhere. | Phase 2/3 acceptance: clock visual is byte-stable across softened-mode toggle. |

---

## File touch summary

**New:**
- `ui/js/narrator-clock.js` (Phase 1, 4)
- `WO-INTERVIEW-CLOCK-01_REPORT.md` at completion (`docs/reports/`)

**Modified:**
- `ui/hornelore1.0.html` (script tag + meta tag + single `#lv10dClock` mount point near the chat input)
- `ui/css/lori80.css` (`.lv-narrator-orient` base + `[data-variant="C|B|A"]` skins + `--lv-today-accent` root var)
- `ui/js/life-map.js` (consume `--lv-today-accent` for Today era button)
- `server/code/api/main.py` (one-line meta-tag template injection from `LOREVOX_NARRATOR_LOCATION` env)
- `.env.example` (new `LOREVOX_NARRATOR_LOCATION=""` key with comment; no `LOREVOX_PARENT_NARRATORS` key — variant default is C globally per Chris's lock 2026-05-01)
- `scripts/ui/run_parent_session_readiness_harness.py` (TEST-09 DOM-read hook in Phase 7)

**Read-only reference:**
- `ui/js/lv-eras.js` + `server/code/api/lv_eras.py` (canonical Today)
- Existing `.lv-narrator-topbar` ruleset in `lori80.css`

---

## Sequencing within the parent-session readiness lane

This WO is **additive** — it does not block any other WO and is not blocked by any other WO. It pairs naturally with WO-PARENT-KIOSK-01 because:

- The kiosk install sets `LOREVOX_NARRATOR_LOCATION` once per laptop.
- The kiosk install hardcodes the narrator id, so the variant default (C for parents) is automatic.
- The clock is one of the first things visible when the kiosk lid opens, reinforcing the "you are here, today" cognitive anchor at session start.

Recommended sequencing: build Phases 1–5 in a single session; deploy Phase 6 against a parent during the next planned session; close Phase 7 the same day Phase 6 passes.

---

## Open questions for Chris

1. **Variant C eyebrow copy.** Mockup shows "Right now". Alternatives: "Today is", nothing (drop the eyebrow entirely). Calmer is better; "Right now" might read as event-driven. Lock before Phase 3 build.
2. **Time-of-day band boundaries.** The table in §3 is one defensible reading; 7 PM as "evening" vs "early evening" is a tone call. Lock before Phase 1 build.
3. **Place line for travelling narrators.** Christopher might end up with `LOREVOX_NARRATOR_LOCATION="Las Vegas, New Mexico"` while sitting in a hotel in Seattle. Phase 1 ships static; future enhancement is out of scope. Confirm acceptable.
4. **Card width at the lower-left slot.** Spec assumes ~240–280px. If the chat-region's natural left padding is wider or narrower than expected, may need a small Phase 2 adjustment after first visual.
5. **Operator-side variant toggle home.** Phase 5 spec says Bug Panel four-way toggle (C / B / A / off). Confirm the Bug Panel is the right home (vs the Operator tab dashboard).

---

## Definition of done

WO-INTERVIEW-CLOCK-01 is closed when:

- All seven phases pass their acceptance criteria.
- Phase 6 real-narrator test passes for at least one parent (target: both).
- Report at `docs/reports/WO-INTERVIEW-CLOCK-01_REPORT.md` written with: variant chosen per narrator, real-test observations, any band-boundary or eyebrow-copy adjustments made during the build, screenshots of B and C in the live narrator room.
- Lorevox graduation candidate row added to `docs/lorevox/GRADUATION_CANDIDATES_2026-05-01.md` as **A11**.
- TEST-09 harness assertion is deterministic-pass on three consecutive runs.
- No regression on the existing topbar controls (mic / cam / pause / break / record-voice toggle) — verified by running the full parent-readiness harness pass after Phase 5.
