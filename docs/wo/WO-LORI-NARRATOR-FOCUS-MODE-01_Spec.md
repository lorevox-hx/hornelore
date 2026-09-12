# WO-LORI-NARRATOR-FOCUS-MODE-01 — Interview focus mode for the narrator room

**Status: DRAFTED 2026-09-12, REVISED same day after Chris's review against the shipped
page; not started.** Drafted on the laptop at the close of the Phase 6 laptop-origin
session; intended for implementation in a desktop session. Docs-only until then.

*(Revision record: the first draft claimed the composer `min-width` fix was still
withdrawn — a stale status line copied from HANDOFF §7 without reading the shipped page,
the exact defect class this repository's governing order exists to prevent. The repair
landed 2026-08-30: `#chatInput { min-width: 0 }` at `hornelore1.0.html:707-709` with the
wrap rules at 611-612 and the design comment at 696-704. Six further review amendments
are folded in below: generic popover closure, chord-only exit, the mic as sole status
surface with its LISTENING pulse kept, no contrast reduction on history, a
focus-transfer contract, and a readiness precondition.)*

**One sentence:** a presentation-only mode of the existing narrator room — large print,
one conversation, nothing else on screen — that the operator enters before handing the
room to the narrator and leaves by a deliberate gesture the narrator cannot produce by
accident.

---

## Mission alignment

The narrator is the author of their own story; the system exists to help them tell it.
Today the narrator converses inside an operator workspace that tolerates them — header
tabs, a Bug Panel launcher, small type, status furniture. This WO builds the first
surface designed *for* the narrator: Lori's words large enough to read, the microphone
large enough to find, and silence that looks like patience. It is the "no operator
leakage" and "no system-tone outputs" principles applied to visual furniture, for the
narrators the product actually serves — older adults, possibly with cognitive decline.

## Non-regression requirements

This WO MUST NOT:

- reduce narrator dignity;
- introduce new must_not_write violations or system-tone outputs;
- regress the current locked extractor baseline (none is touched — this WO contains no
  server code, no prompt change, no extractor change; naming it for completeness:
  `r5k-guard-v2` 71/114 at `5afead5`, scorer `318df0d2ff1f`);
- expand operator surfaces into narrator UI — **this WO removes operator surface from
  narrator view and must not smuggle any back in**;
- add detectors that duplicate existing signals;
- create a second turn path, a second transport, or a second place that proposes
  `turn_mode` (see Invariants).

## Lori impact (Tier 3)

**None at the model or pipeline layer, by design.** Response length, question cadence
(≤1 per turn), tone, pacing, routing, guards, prompts: all untouched. The mode changes
what the narrator *sees*, not what Lori *does*. The one behavioural surface it touches
is pacing-adjacent: the mode must add **no** visual element that pressures the narrator
during silence (no spinners, no "Lori is waiting…", no countdowns), which is the visual
counterpart of WO-10C's protected-silence guarantee, not a change to its timings.

## Narrator dignity check (Tier 3) — the eight locked principles, walked

| Principle | This WO |
|---|---|
| No dual metaphors | No navigation surface added or altered. Life Map untouched. |
| No operator leakage | **The point of the WO.** In focus mode: no tabs, no Bug Panel launcher, no operator controls, no exit *button* (see Exit). |
| No system-tone outputs | Extended to furniture: no operator, diagnostic, connection, database, or internal status strings; no timestamps or ids. **Narrator-facing microphone state labels remain** (`LISTENING`, `MIC OFF`, `WAIT — LORI IS SPEAKING`, `MIC BLOCKED`) — they are capture feedback that tells the narrator whose turn it is, not system tone. |
| No partial resets | Nothing narrator-scoped is written, so nothing new to reset. The mode flag is **not persisted** (see State). |
| Provisional truth persists / interview never waits | Untouched — no write path changes. |
| Lorevox is the memory system; Lori the interface | Untouched. |
| Mechanical truth must visibly project | Untouched — no consuming surface altered, only restyled. |
| Operator seeds; Lori reflects | Untouched. |

## Scope

**IS:** one body-level mode class (working name `lv-interview-focus`) on the existing
narrator room in `hornelore1.0.html`; the CSS it gates; an operator control to enter;
an operator gesture to leave; closure of open popovers on entry; composer narrow-width
**regression verification** (the repair itself is landed — see below); acceptance
evidence.

**IS NOT:** a second page or route · any server change · any new endpoint · any change
to `chat_ws.py`, routing, guards, prompts, extraction, or the model (LOCKED) · a
Cognitive Support Mode operator toggle (known WO-10C gap, stays its own item) · themes
or user-adjustable font settings · TTS/STT behaviour changes · anything on the
Operator tab beyond the entry control.

## Design

### Entry
An operator control in the ordinary operator surface (header/operator area — operator
side, so a visible button is fine there). Entering toggles the class on the already-open
room. **Entering must not re-open, re-select, or reload the narrator** — opening a
narrator appends four `bio_facts` through `questionnaire_put` (BACKLOG §5, proven in
Phase 6 §36.1), and a presentation toggle must not fire that path. Entry is a DOM class
change plus the three housekeeping steps below (popover closure, focus transfer,
readiness check) and nothing else.

**Readiness precondition.** Focus mode may be entered only with an active narrator and
a ready conversation surface. The application already has a warmup state that disables
`#chatInput` and shows readiness furniture; focus mode hides that furniture, so entering
during warmup would hand the narrator a beautiful screen with a dead composer and no
explanation. If the room is not ready, entry is **refused** (the operator stays in the
full UI until Lori is ready). This consumes readiness the page already computes — no new
authority, no new server read. The operator deliberately prepares the room, then hands
it over.

**Focus transfer.** The entry control disappears when the mode it triggers is applied,
and browser focus must not be left on a hidden element. On entry, focus moves to a
narrator-safe element in the conversation surface — preferred: a conversation container
with `tabindex="-1"`, so entering does not itself imply "start typing." On exit, focus
returns to the focus-mode entry control. Acceptance checks `document.activeElement` in
both directions.

### The surface in focus mode
- **Current exchange is the page.** Lori's latest words rendered large; the reply area
  below. Earlier exchanges remain **fully readable but subordinate through size, spacing
  and visual weight** — e.g. current turn 22–24px, history 18–20px with tighter
  surrounds. **Focus mode must not use low contrast or opacity to de-emphasise
  history**: the narrators this surface serves must never have to work harder to reread
  something they said. WO-10C single-thread context, applied visually. No timestamps,
  no metadata.
- **The mic is the hero, and the SOLE status surface.** The existing 4-state visual
  (WO-MIC-UI-02A: LISTENING / OFF / WAIT amber / BLOCKED) is preserved with states,
  semantics **and its existing LISTENING pulse unchanged**, scaled to be the dominant
  control. The pulse is positive confirmation — it answers "is this thing actually
  hearing me?", the most basic question an older narrator has — and is not a pressure
  cue. **Per-state animation, settled explicitly:** in focus mode LISTENING retains the
  existing red pulse; WAIT retains its amber state and label but is rendered **static**
  (the shipped WAIT pulses — that pulse is a waiting cue and focus mode suppresses it);
  BLOCKED and OFF are static. This is a CSS presentation override only; the mic state
  machine is unchanged. `#lv80LoriDot` (line 3579; pulses for
  thinking/drafting/speaking) is **hidden** in focus mode: two animated status
  indicators compete for attention, and the mic wins. The state machine is not touched;
  only its clothes are.
- **Composer** remains for typed input (the WO-STT-LIVE-02 fragile-fact typed-input
  fallback depends on it): full row width, large text, Send always visible.
- **Typography:** conversation text 22–24px minimum; line-height ≈1.6; measure ≤~65ch;
  no thin font weights; soft off-white ground, high contrast, no glare-white; touch
  targets ≥48px.
- **Motion/pressure:** no autoscroll while the narrator is mid-read of the latest
  response beyond keeping it in view. **No countdowns, elapsed-time indicators, or any
  animation that pressures the narrator during protected silence.** The LISTENING pulse
  is explicitly not in that class (see above); it is the one animation focus mode keeps.

### Exit — the one hard problem
The locked principles forbid a Return-to-Operator button in narrator flow, so **the
exit is a deliberate operator gesture with no visible affordance**: **one documented
multi-key keyboard chord, and nothing else.** Not a single key — narrators on voice or
touch cannot produce a chord. The unlabeled corner long-press considered in the first
draft is **rejected**: it is invisible state in the UI, accidentally triggerable by
touch, and one more magic interaction to remember. A chord is unambiguously an operator
gesture and cleanly testable: single key → no exit; ordinary typing → no exit;
mouse/touch on the transcript → no exit; the exact chord → exit. Exact binding chosen
at implementation and documented operator-side only. Leaving removes the class; the
full UI is simply present again. **Fail-open by non-persistence:** because the mode
never survives a reload (see State), a forgotten chord is never a lockout — refresh
restores the full UI. That is a deliberate safety property, not laziness.

### Popovers and dialogs
The shipped page has **many** native popovers, not two: review against the page found
Trips, Memoir, Life Map, Transcript, Review Queue, review row detail, Review Help, Bio
Builder, Bio Control Center, Settings, and the manual Delete Narrator popover, in
addition to `#lv10dBugPanel` and `#memoirScrollPopover`. All render in the **top layer**
(CLAUDE.md, UI harness hazards): CSS on ordinary containers does not cover them, and
`offsetParent` cannot detect them.

**The contract is therefore generic, not a hand-written list:** before applying the
class, entry closes **every** currently-open native popover —
`document.querySelectorAll('[popover]:popover-open')` → `hidePopover()`. A popover
added next month is covered without touching this code. This is the most likely
implementation miss in the whole WO.

**Modal dialogs are different, and the rule is generic there too.** A native `<dialog>`
may hold an unsaved edit, so focus mode must **never silently close one**: if **any**
`dialog[open]` exists at entry, **entry is refused** and the operator resolves it first.
The check is the selector, not a name — a dialog added next month is covered the same
way a new popover is. `memoirEditModal` is the known real unsaved-edit hazard and is
the acceptance example. Discarding an edit as a side effect of a presentation toggle
would be its own defect.

### Composer narrow-width — regression VERIFICATION, not repair
**The repair has landed.** The first draft of this spec said the fix was still
withdrawn, copied from HANDOFF §7 without reading the page — a stale status line, the
defect class the governing order exists for. Verified at HEAD (2026-09-12):
`#chatInput { flex: 1 1 auto; min-width: 0 }` at `hornelore1.0.html:707-709`, wrap
rules `.lv-composer-row { flex-wrap: wrap }` / `> * { flex-shrink: 0 }` at 611-612,
the narrow-layout full-row rule for the textarea below 820px, and the design comment
at 696-704 naming the exact 39px/clipped-Send problem these solve. `lv-composer-row`
was classed 2026-08-30 (comment at 3555). **Do not rebuild this.** (HANDOFF §7's open
entry for the composer should be corrected when this WO lands.)

What this WO owes instead: **measure and preserve the landed repair inside focus
mode** — composer and Send-button geometry at 697px (the documented failing viewport)
and at the narrowest supported width, with focus-mode styles applied, before
acceptance. Focus mode's own CSS must not undo `min-width: 0` or the wrap behaviour.
Change the ordinary composer only if live evidence shows the landed repair still
fails, and then as its own recorded finding.

## Invariants (fail the WO if violated)

1. **Presentation only.** No new WS wiring, no fetch, no state write, no read of
   anything the room does not already read. The production transport stays
   `ui/js/api.js` → `/api/chat/ws`, untouched.
2. **Client proposes, server resolves — and this mode proposes nothing.** No code in
   this WO reads or writes `turn_mode`, eligibility, or any Guard Lab surface.
3. **Entry/exit mutate no narrator state** — verified, not assumed: the acceptance walk
   includes a before/after read of the narrator's `bio_facts` count across an
   enter/leave cycle (the BACKLOG §5 mutation is exactly four rows, so a delta is
   unmistakable).
4. **Mode is not persisted.** No localStorage, no server flag. Every session starts in
   the full UI; entering is always an operator gesture. (Reload-restores-operator-UI is
   the anti-lockout property; do not "improve" it away.)
5. **The mic state machine, transcript guard, and TTS turn-claim interactions are
   untouched.** If any of WO-MIC-UI-02A / WO-10H / WO-10C code must change to ship
   this, stop and report — that is a different WO.

## Acceptance

Live walk on a **synthetic narrator** (never family; the ZZ pattern), one browser,
recorded like Phase 5a §35.3:

1. Enter focus mode from a normal operator session — narrator not re-opened;
   `bio_facts` count unchanged across enter + leave (invariant 3).
2. In focus mode: no tabs, no `#lv10dBugBtn`, no `#lv80LoriDot`, no operator control
   reachable by click or tab-focus traversal.
3. Enter with the Bug Panel popover open → closed, not merely styled over
   (`:popover-open` is the check; never `offsetParent`). Repeat with one
   narrator-side popover (Memoir or Life Map) open — the generic closure covers it
   without naming it.
4. Enter with a `dialog[open]` present (`memoirEditModal`, the real unsaved-edit
   hazard, is the example) → entry **refused**, dialog and its content untouched.
5. Entry attempted during warmup / no active narrator → entry **refused**; full UI
   retained.
6. Focus transfer: on entry `document.activeElement` is inside the narrator-safe
   conversation surface; on exit it is the focus-mode entry control.
7. A full spoken turn completes in focus mode — mic states render correctly at the new
   scale through LISTENING → WAIT → response → TTS playback: **LISTENING pulses, WAIT
   is static amber**, and no other animated status indicator is on screen. **One**
   spoken case (TTS-aware testing rule); text turns for everything else. Wait until
   Lori finishes speaking before continuing.
8. A typed turn completes, and composer geometry is measured with focus-mode styles
   applied, at **697px** (the documented failing viewport) and at the declared
   narrowest supported viewport. Hard regression boundary, not a visual judgment:
   textarea width **≥ 300px**, textarea height **≥ 44px**, Send fully inside the
   viewport with **≥ 48px** target height, and **zero horizontal clipping or
   overflow**. Record all four numbers at both widths. (This pins the old 33–39px
   collapse as a measured impossibility; the landed `min-width: 0` repair is
   preserved, not rebuilt.)
9. Exit chord works; single keys, ordinary typing, and taps/swipes on the transcript
   do **not** exit.
10. Reload mid-focus-mode → full operator UI returns (invariant 4).
11. Ordinary room after exit: pixel-order unchanged vs pre-entry (no style bleed);
    Bug Panel opens normally; `#lv80LoriDot` behaves as before.

Report the interpreter/browser and viewport for every measured number. A refusal is a
result.

## Verification duties for the implementer (cite the line that reads the value)

Selectors named in this spec with line citations were read at the 2026-09-12 HEAD
(`#chatInput` 707, `.lv-composer-row` 611/3558, `#lv80LoriDot` 738/3579/5801); the rest
(`#lv10dBugBtn`, `#lv10dBugPanel`, `#memoirScrollPopover`, `memoirEditModal`) are
documented in CLAUDE.md or Chris's review. **All of them must still be pinned against
the shipped page at implementation time** — a harness guard on a phantom selector
confirms the typo instead of catching it, and lines move. Everything else (the room's
container structure, transcript node, warmup/readiness state surface, mic pulse rule)
is to be derived by reading `hornelore1.0.html` and the relevant `ui/js` modules, not
assumed from this spec.

## Flags / gating

None. No env flag, no server gate — the mode is operator-invoked per session and
defaults to off by construction (Tier 5 noted for completeness: no flags introduced;
default state preserves current behaviour exactly).
