# WO-KAWA-03A — River Canvas Engine (Layout + SVG + Physics)

**Status:** Specced, not started
**Priority:** After WO-KAWA-01 Phase 1 (LLM-driven proposals populate real segment data)
**Depends on:** WO-KAWA-UI-01A (popover + segment CRUD), WO-KAWA-02A (integration metadata + memoir modes)
**Related specs:** WO-KAWA-03B (Nudge Interaction), WO-KAWA-03C (Proposal/Mood System), WO-KAWA-04 (Tributaries)
**Companion doc:** `to do list.txt` (original vision doc with ChatGPT review)

---

## Objective

Build the Kawa river canvas: a dynamic SVG visualization inside the existing River popover that renders a narrator's life as a flowing river shaped by obstacles, supports, environment, and openings. The river reacts to the data — it is not a static drawing.

This WO covers **layout + rendering + animation only**. No memoir writing, no proposal system, no tributaries, no "set in stone" persistence, no nudge interactions beyond basic click-to-select.

---

## Why This WO Exists

WO-KAWA-UI-01A gave us the data layer: segments, CRUD, popover, form-based editing.
WO-KAWA-02A gave us the integration layer: questioning modes, memoir overlay, prompt routing.

What's missing is the **visual representation**. The River popover currently shows a list of segments with form fields. Janice sees text. She should see water.

The river metaphor is the whole point of Kawa. Without the visual, Lori says "imagine your life like a river" and then shows a JSON editor. The canvas makes the metaphor real.

---

## Hard Rules

```
1. River path must react to obstacles (no static path).
2. Confidence must affect visual solidity (opacity + size).
3. Spaces (sukima) must be visible and clickable.
4. Animation must reflect structural pressure (flow_state).
5. Canvas must be lightweight SVG — no heavy libraries.
6. No business logic inside the rendering layer.
7. All rendering derives from Kawa segment JSON only — no invented coordinate data.
8. Canvas must work inside the existing River popover (#kawaRiverPopover).
9. Must degrade gracefully when segments have no rocks/driftwood (show calm open water).
10. Clicking a construct selects it in the existing detail pane — no new editing UI in this WO.
```

---

## The Central Problem: Layout

The ChatGPT spec assumed rocks have `x` and `y` coordinates. They don't. The actual Kawa segment schema is:

```json
{
  "segment_id": "seg_abc123",
  "anchor": { "type": "timeline_event", "ref_id": "...", "label": "Marriage", "year": 1968 },
  "kawa": {
    "water": { "summary": "", "flow_state": "steady", "confidence": 0.7 },
    "rocks": [
      { "label": "Dad's disapproval", "notes": "He never accepted Kent", "confidence": 0.8 },
      { "label": "Money was tight", "notes": "", "confidence": 0.6 }
    ],
    "driftwood": [
      { "label": "Mom's support", "notes": "She helped with the wedding", "confidence": 0.9 }
    ],
    "banks": {
      "social": ["Small town expectations"],
      "physical": ["Living in a rental"],
      "cultural": ["Lutheran church community"],
      "institutional": ["Kent's employer"]
    },
    "spaces": [
      { "label": "Starting fresh together", "notes": "", "confidence": 0.7 }
    ]
  },
  "integration": {
    "memoir_relevance": 0.571,
    "narrative_weight": "medium",
    "kawa_dominant_constructs": ["rocks", "driftwood", "banks"],
    "questioning_priority": "medium"
  }
}
```

Rocks have labels and confidence. Not positions. **The layout engine must assign positions from semantic data.** That is the core deliverable of this WO.

---

## Layout Model

### River Geography

The canvas renders a **single segment** as a river cross-section (matching the Kawa clinical model — one life period, viewed as a stretch of river). The multi-segment "full life river" is a later WO (strip view with click-to-zoom).

```
┌─────────────────────────────────────────────────┐
│  LEFT BANK                                      │
│  ┌───────────┐                                  │
│  │ cultural  │                                  │
│  │ instit.   │  ~~~~~ water flows ~~~~~~>       │
│  └───────────┘     🪨 rock          🌿 driftwood│
│                       🪨 rock                   │
│                                    ✨ space      │
│                    ~~~~~ water flows ~~~~~~>     │
│  ┌───────────┐                                  │
│  │ social    │                                  │
│  │ physical  │                                  │
│  └───────────┘                                  │
│  RIGHT BANK                                     │
└─────────────────────────────────────────────────┘
```

### Coordinate Assignment Rules

The layout engine converts semantic data to renderable positions. No coordinate data is stored — positions are computed fresh each render.

**Vertical axis = time/sequence within the segment.** Rocks are spaced evenly down the river. If the segment has 3 rocks, they sit at 25%, 50%, 75% of the river height. This means the river always has room at top (entry) and bottom (exit).

**Horizontal axis = construct type.** The river channel occupies the center ~60% of the canvas. Banks sit on the edges (left and right). Rocks sit in the channel (they obstruct flow). Driftwood sits in the channel but offset from rocks (it moves with the water). Spaces sit in the widest gaps between rocks.

**Position formulas:**

```
canvas_width  = svg.clientWidth   (typically ~700px inside popover)
canvas_height = svg.clientHeight  (typically ~500px)

channel_left  = canvas_width * 0.20
channel_right = canvas_width * 0.80
channel_cx    = canvas_width * 0.50

For each rock[i] of N rocks:
  rock.y = canvas_height * (i + 1) / (N + 1)
  rock.x = channel_cx + (alternating_side * 40 * rock.confidence)
  rock.r = 8 + (rock.confidence * 12)       // radius 8–20px
  rock.opacity = 0.3 + (rock.confidence * 0.7)  // opacity 0.3–1.0

For each driftwood[i] of M driftwood items:
  drift.y = canvas_height * (i + 1) / (M + 1)
  drift.x = channel_cx + (opposite_side_from_nearest_rock * 30)
  drift.opacity = 0.3 + (drift.confidence * 0.7)

For each space[i]:
  // Spaces sit in the largest vertical gaps between rocks
  space.y = midpoint of largest gap
  space.x = channel_cx
  space.r = gap_size * 0.3  (bigger gap = bigger space indicator)

Banks:
  left_bank_x  = 0 to channel_left
  right_bank_x = channel_right to canvas_width
  // Banks are rendered as labeled rectangles along the edges
  // social + physical on left, cultural + institutional on right
```

### River Path (Bezier)

The river path is a flowing Bezier curve that **deforms around rocks**. Without rocks, it flows straight. With rocks, it bends.

```
Start: (channel_cx, 0)
For each rock (sorted by y):
  The path curves away from the rock based on:
    - rock.confidence (higher = more deflection)
    - rock.x position (path curves to the opposite side)
  Control point: rock.confidence * 40px of deflection
End: (channel_cx, canvas_height)
```

This means:
- A segment with no rocks = straight calm river
- A segment with many high-confidence rocks = winding, pressured river
- A segment with low-confidence rocks = gentle bends (uncertain obstacles barely disturb the flow)

### Flow Animation

The river path has a dashed-stroke animation. Speed derives from `flow_state`:

| flow_state   | dash speed | visual meaning |
|---|---|---|
| blocked      | 40s (very slow) | water barely moves |
| constricted  | 25s (slow) | squeezed through narrow gaps |
| steady       | 15s (medium) | normal life flow |
| open         | 10s (fast) | free-flowing water |
| strong       | 6s (very fast) | powerful current |
| unknown      | 20s (default) | not yet characterized |

When PHENO data becomes available (WO-PHENO-01), the emotional intensity score can modulate this further. For now, `flow_state` is the only input.

---

## File Plan

### File 1 — `ui/js/river-layout.js` (NEW)

Core layout engine. Pure functions, no DOM manipulation. Input: segment JSON. Output: renderable position objects.

```
RiverLayout.computeLayout(segment, canvasWidth, canvasHeight) → {
  path: "M ... Q ... L ...",    // SVG path d-attribute
  rocks: [{ x, y, r, opacity, label, confidence }],
  driftwood: [{ x, y, opacity, label, confidence }],
  spaces: [{ x, y, r, opacity, label }],
  banks: {
    left: [{ y, label, category }],
    right: [{ y, label, category }]
  },
  flow: { speed, state, pressure }
}
```

Key functions:
- `computeLayout(segment, w, h)` — master layout function
- `_layoutRocks(rocks, channelCx, canvasHeight)` — assign rock positions
- `_layoutDriftwood(driftwood, rocks, channelCx, canvasHeight)` — assign driftwood positions, offset from rocks
- `_layoutSpaces(spaces, rocks, channelCx, canvasHeight)` — find gaps, place space indicators
- `_layoutBanks(banks, canvasWidth, canvasHeight)` — assign bank label positions
- `_computePath(rocks, channelCx, canvasHeight)` — build Bezier path string
- `_flowSpeed(flowState)` — map flow_state to animation speed

This file has **zero DOM dependencies**. It can be unit-tested with Node.

### File 2 — `ui/js/river-renderer.js` (NEW)

SVG rendering layer. Takes a layout object, produces SVG elements.

Key functions:
- `renderRiverCanvas(segment)` — master render: calls layout, builds SVG
- `_renderPath(svg, pathD, flow)` — draw the river path with animated stroke
- `_renderRock(svg, rock)` — draw a rock node (circle/ellipse, opacity = confidence)
- `_renderDriftwood(svg, drift)` — draw driftwood (different shape, e.g., rounded rect)
- `_renderSpace(svg, space)` — draw sukima hotspot (pulsing circle, clickable)
- `_renderBanks(svg, banks)` — draw bank labels along edges
- `_clearCanvas(svg)` — remove all child elements before re-render

Click handlers on rocks/driftwood/spaces should **select the corresponding item in the existing detail pane** (scroll to card, highlight field). No new editing UI.

### File 3 — CSS additions in `hornelore1.0.html`

```css
/* River canvas */
#kawaRiverCanvas { width: 100%; height: 100%; min-height: 400px; }

/* Animated flow */
.river-flow-path {
  fill: none;
  stroke: rgba(96, 165, 250, 0.4);
  stroke-width: 60;
  stroke-linecap: round;
  stroke-dasharray: 10 30;
  animation: river-flow var(--flow-speed, 15s) linear infinite;
}
.river-flow-center {
  fill: none;
  stroke: rgba(96, 165, 250, 0.15);
  stroke-width: 80;
  stroke-linecap: round;
}

@keyframes river-flow {
  from { stroke-dashoffset: 400; }
  to   { stroke-dashoffset: 0; }
}

/* Construct nodes */
.kawa-rock-node {
  fill: #78716c; cursor: pointer;
  transition: fill-opacity 0.3s;
}
.kawa-rock-node:hover { fill: #a8a29e; }

.kawa-drift-node {
  fill: #65a30d; rx: 4; cursor: pointer;
  transition: fill-opacity 0.3s;
}
.kawa-drift-node:hover { fill: #84cc16; }

.kawa-space-node {
  fill: rgba(250, 204, 21, 0.2);
  stroke: rgba(250, 204, 21, 0.5);
  stroke-width: 1.5;
  cursor: pointer;
  animation: space-pulse 3s ease-in-out infinite;
}
@keyframes space-pulse {
  0%, 100% { r: attr(r); opacity: 0.6; }
  50% { opacity: 1; }
}

.kawa-bank-label {
  fill: #94a3b8; font-size: 11px; font-family: inherit;
}
.kawa-node-label {
  fill: #cbd5e1; font-size: 10px; pointer-events: none;
}
```

### File 4 — HTML mount point

Inside the existing `kawaPanel` render, add an SVG canvas element that sits above or alongside the detail pane. The layout is:

```
┌─────────────────────────────────────────────┐
│ sidebar (segment list)  │  SVG canvas       │
│                         │  (river viz)      │
│                         │                   │
│                         ├───────────────────│
│                         │  detail pane      │
│                         │  (existing forms) │
└─────────────────────────────────────────────┘
```

The canvas renders the **active segment**. Clicking a different segment in the sidebar re-renders the canvas. The detail pane below the canvas shows the form-based editor from 01A.

This means `renderKawaUI()` in app.js gets a small patch: insert `<svg id="kawaRiverCanvas">` above the existing detail HTML, and call `renderRiverCanvas(active)` after DOM insertion.

### File 5 — Script tags in `hornelore1.0.html`

```html
<script src="js/river-layout.js"></script>
<script src="js/river-renderer.js"></script>
```

Load order: after `lori-kawa.js`, before `app.js` (same block as the existing Kawa scripts).

---

## What This WO Does NOT Do

| Feature | Why not | Where it goes |
|---|---|---|
| Drag-and-drop rocks | Interaction system, not rendering | WO-KAWA-03B |
| "That felt narrow" nudge buttons | Interaction system | WO-KAWA-03B |
| AI proposes mood/tone for chapters | Proposal system | WO-KAWA-03C |
| Tributary rivers (spouse, institution) | Requires stable single-river first | WO-KAWA-04 |
| "Set in stone" confirmation UX | Needs diff tracking + conflict resolution | WO-KAWA-03B or 04 |
| Multi-segment full-life strip view | Needs stable single-segment canvas first | WO-KAWA-03A Phase 2 |
| Memoir export with embedded SVG | Rendering → export bridge | WO-KAWA-04+ |
| PHENO integration (emotional intensity → flow speed) | PHENO not built yet | WO-PHENO-01 → hook in later |

---

## Confidence → Visual Mapping (Detail)

This is the core visual language. Every Kawa construct uses the same rule:

```
opacity   = 0.3 + (confidence * 0.7)     // 0.3 at 0.0, 1.0 at 1.0
size      = base + (confidence * scale)   // bigger = more certain
```

The narrator sees:
- **Faint, small** = "Lori thinks this might be here, but isn't sure"
- **Solid, large** = "This is confirmed — the narrator said so"

This maps directly to the existing `proposed` vs `confirmed` provenance system. Unconfirmed segments have low-confidence constructs (faint). Confirmed segments have narrator-validated constructs (solid).

---

## Spaces (Sukima) — The Interactive Core

ChatGPT's review correctly identified that **Kawa therapy happens in the spaces**. The spaces are where the water still flows, where possibility exists, where the interview deepens.

In this WO, spaces are:
1. **Visually distinct** — pulsing golden circles, not static nodes
2. **Positioned in gaps** — they sit between rocks, in the open water
3. **Clickable** — clicking a space selects it in the detail pane and (in 03B) will trigger a Lori deep-dive question

The existing `segment.kawa.spaces` array is used directly. We do NOT infer spaces from rock gaps (that was the ChatGPT spec's mistake). The narrator and Lori explicitly name spaces. The layout engine places them in the visual gaps for narrative coherence, but their existence comes from the data, not from geometry.

---

## Integration with Existing Code

| Existing file | What changes |
|---|---|
| `app.js :: renderKawaUI()` | Insert SVG mount, call `renderRiverCanvas()` after DOM update |
| `app.js :: kawaSelectSegment()` calls | Trigger re-render when active segment changes |
| `hornelore1.0.html` | Add 2 script tags, add CSS block |
| `lori-kawa.js` | No changes — layout engine reads `state.kawa.activeSegment` directly |
| `state.js` | No changes — no new state needed for rendering |

---

## Acceptance Tests

### Rendering

```
[ ] Empty segment (no rocks/driftwood/spaces) renders calm straight river
[ ] Segment with 3 rocks renders winding path that curves around them
[ ] High-confidence rock creates larger deflection than low-confidence rock
[ ] Driftwood items render on opposite side of channel from nearest rock
[ ] Spaces render as pulsing circles in the largest gaps
[ ] Banks render as labeled regions on left/right edges
[ ] Canvas re-renders when active segment changes
```

### Confidence → Visual

```
[ ] Rock with confidence 0.3 is faint and small
[ ] Rock with confidence 0.9 is solid and large
[ ] Same rule applies to driftwood and spaces
```

### Animation

```
[ ] flow_state=blocked → very slow dash animation
[ ] flow_state=open → fast dash animation
[ ] flow_state=unknown → medium default speed
[ ] Animation speed changes when segment changes
```

### Interaction

```
[ ] Clicking a rock selects it in the detail pane
[ ] Clicking a space selects it in the detail pane
[ ] Clicking driftwood selects it in the detail pane
[ ] Canvas works inside the existing River popover at all viewport sizes
```

### Safety

```
[ ] Canvas renders from Kawa JSON only — no invented coordinates stored
[ ] No writes to canonical facts
[ ] No changes to chronology, extraction, or prompt composer
[ ] Existing 01A form editing still works alongside canvas
[ ] 114 unit tests still pass
```

---

## Scoping Boundary

This WO ships when:
1. The SVG canvas renders inside the River popover
2. The river path reacts dynamically to the rocks in the active segment
3. Confidence maps to visual weight
4. Flow state maps to animation speed
5. Spaces are visible and clickable
6. All construct types are rendered with distinct visual identity
7. Clicking any node selects it in the existing detail pane

This WO does NOT ship:
- Drag interaction
- Nudge buttons
- AI proposals
- Memoir integration
- Tributary rivers

---

## Estimated Effort

~1 session (3-4 hours). Two new files (`river-layout.js`, `river-renderer.js`), small patches to `app.js` and `hornelore1.0.html`. No backend changes. No new endpoints. No new state.

---

## Future WO Roadmap

```
WO-KAWA-03A  Canvas + physics + rendering (this WO)
WO-KAWA-03B  Nudge interaction system ("that felt narrow", drag rocks, resize)
WO-KAWA-03C  Proposal / mood system (AI suggests chapter soul, narrator shapes)
WO-KAWA-04   Tributaries + influence system (spouse rivers, institutional rivers)
```

Each WO is independently shippable. 03A must ship first because 03B/03C/04 all render on top of it.
