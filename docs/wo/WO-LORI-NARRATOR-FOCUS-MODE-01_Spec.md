# WO-LORI-NARRATOR-FOCUS-MODE-01 — Interview focus mode for the narrator room

**Status: DRAFTED 2026-09-12, not started.** Drafted on the laptop at the close of the
Phase 6 laptop-origin session; intended for implementation in a desktop session.
Docs-only until then.

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
| No system-tone outputs | Extended to furniture: no timestamps, ids, status strings, connection chrome in narrator view. |
| No partial resets | Nothing narrator-scoped is written, so nothing new to reset. The mode flag is **not persisted** (see State). |
| Provisional truth persists / interview never waits | Untouched — no write path changes. |
| Lorevox is the memory system; Lori the interface | Untouched. |
| Mechanical truth must visibly project | Untouched — no consuming surface altered, only restyled. |
| Operator seeds; Lori reflects | Untouched. |

## Scope

**IS:** one body-level mode class (working name `lv-interview-focus`) on the existing
narrator room in `hornelore1.0.html`; the CSS it gates; an operator control to enter;
an operator gesture to leave; closure of open popovers on entry; the composer
`min-width` repair; acceptance evidence.

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
change and nothing else.

### The surface in focus mode
- **Current exchange is the page.** Lori's latest words rendered large; the reply area
  below. Earlier transcript scrolls above, visually receded (reduced size/contrast) —
  WO-10C single-thread context, applied visually. No timestamps, no metadata.
- **Mic is the hero.** The existing 4-state mic visual (WO-MIC-UI-02A: LISTENING / OFF /
  WAIT amber / BLOCKED) is preserved with its states and semantics **unchanged**, scaled
  to be the dominant control. The state machine is not touched; only its clothes are.
- **Composer** remains for typed input (the WO-STT-LIVE-02 fragile-fact typed-input
  fallback depends on it): full row width, large text, Send always visible.
- **Typography:** conversation text 22–24px minimum; line-height ≈1.6; measure ≤~65ch;
  no thin font weights; soft off-white ground, high contrast, no glare-white; touch
  targets ≥48px.
- **Motion/pressure:** no autoscroll while the narrator is mid-read of the latest
  response beyond keeping it in view; nothing animates during silence.

### Exit — the one hard problem
The locked principles forbid a Return-to-Operator button in narrator flow, so **the
exit is a deliberate operator gesture with no visible affordance**: a multi-key
keyboard chord (not a single key; narrators on voice/touch cannot produce it) and/or a
long-press on an unlabeled corner hotspot. Exact binding chosen at implementation and
documented operator-side only. Leaving removes the class; the full UI is simply present
again. **Fail-open by non-persistence:** because the mode never survives a reload (see
State), a forgotten chord is never a lockout — refresh restores the full UI. That is a
deliberate safety property, not laziness.

### Popovers
`#lv10dBugPanel` and `#memoirScrollPopover` are **native popovers in the top layer**
(CLAUDE.md, UI harness hazards): CSS on ordinary containers does not cover them, and
`offsetParent` cannot detect them. Entering focus mode must explicitly close any open
popover (`hidePopover()`/the platform API), and the acceptance walk must include
"enter focus mode with the Bug Panel open" as a case. This is the most likely
implementation miss in the whole WO.

### The composer `min-width` repair
Known open defect (HANDOFF §7): `#chatInput` is `flex: 1` with default
`min-width: auto`; measured **39px wide × 240px tall at a 697px viewport**; a fix was
written and **withdrawn unverified because it may clip Send**. This WO owns the repair
*within focus mode at minimum* (the simplified row has almost nothing competing for
width). Required evidence: measured composer and Send-button geometry at 697px and at
the narrowest supported width, in focus mode, before acceptance. If the same fix is
safe in the ordinary room, apply it there in the same commit with the same
measurement; if not, say so and leave the ordinary-room defect open rather than
half-fixing it.

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
2. In focus mode: no tabs, no `#lv10dBugBtn`, no operator control reachable by click
   or tab-focus traversal.
3. Enter with the Bug Panel popover open → it is closed, not merely styled over
   (`:popover-open` is the check; never `offsetParent`).
4. A full spoken turn completes in focus mode — mic states render correctly at the new
   scale through LISTENING → WAIT → response → TTS playback. **One** spoken case
   (TTS-aware testing rule); text turns for everything else. Wait until Lori finishes
   speaking before continuing.
5. A typed turn completes; composer and Send measured ≥ required geometry at 697px.
6. Exit gesture works; a plausible accidental input set (single keys, taps, swipes on
   the transcript) does **not** exit.
7. Reload mid-focus-mode → full operator UI returns (invariant 4).
8. Ordinary room after exit: pixel-order unchanged vs pre-entry (no style bleed);
   Bug Panel opens normally.

Report the interpreter/browser and viewport for every measured number. A refusal is a
result.

## Verification duties for the implementer (cite the line that reads the value)

The selectors named in this spec that are **documented** in CLAUDE.md/HANDOFF
(`#chatInput`, `#lv10dBugBtn`, `#lv10dBugPanel`, `#memoirScrollPopover`) still must be
**pinned against the shipped page at implementation time** — a harness guard on a
phantom selector confirms the typo instead of catching it. Everything else (the room's
container structure, transcript node, composer row) is to be derived by reading
`hornelore1.0.html` and the relevant `ui/js` modules, not assumed from this spec.

## Flags / gating

None. No env flag, no server gate — the mode is operator-invoked per session and
defaults to off by construction (Tier 5 noted for completeness: no flags introduced;
default state preserves current behaviour exactly).
