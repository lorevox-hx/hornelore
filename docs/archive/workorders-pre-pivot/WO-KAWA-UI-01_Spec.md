# WO-KAWA-UI-01 — River View UI for Hornelore

**Status:** Specced, not started
**Priority:** After WO-KAWA-01 Phase 1-3 (data model + projection engine + confirmation loop)
**Depends on:** WO-KAWA-01 data model, Kawa API endpoints
**Companion spec:** `WO-KAWA-01_Spec.md` (data model, projection engine, instrumentation)

---

## Objective

Add a visible Kawa UI layer to Hornelore so the narrator's life can be viewed not only as a chronological timeline, but also as a river-based cross-sectional meaning view.

This WO does not replace the timeline. It adds a parallel River UI that lets the user inspect, edit, and confirm: flow/water, rocks, driftwood, banks, and spaces.

The Kawa literature supports exactly this kind of participant-led, collaborative visual/storytelling use: the river is used to surface life flow, supports, barriers, context, and openings, and the user is expected to correct and shape the representation rather than passively receive it.

---

## Product Intent

Hornelore currently has: chronology, entities, milestones, extraction-backed structure.

Kawa adds: relational context, barrier/support interaction, meaning at a given life point, visible "space" for adaptation and hope.

```
Timeline = what happened
River    = what life felt like and what shaped the flow
```

---

## Hard Rules

1. Do not remove or replace the current Timeline/Life Map UI.
2. River view must be parallel to timeline, not destructive to it.
3. River items are provisional until narrator-confirmed.
4. Lori may propose Kawa elements, but UI must clearly mark proposed vs confirmed.
5. First version is text-and-shape UI only; no freehand drawing canvas in this WO.
6. The user must be able to inspect one segment at a time and see how it fits in the larger life river.
7. Kawa UI must not write to canonical facts directly.

---

## User Experience Goal

A narrator should be able to:

- Click a life chapter or event
- Open River
- See the Kawa interpretation for that segment
- Edit what is wrong
- Confirm what is right
- Compare the river view to the timeline view
- Understand that chronology and meaning are being held separately but together

---

## UI Model

### Primary Navigation

Add a mode switch in the main life-history workspace:

```
Timeline | River
```

Optional later:

```
Timeline | River | Memoir
```

### Behavior

- Timeline = current chronology UI unchanged
- River = new Kawa panel
- Switching tabs preserves selected person and selected segment/event

---

## River UI Structure

### Two-Pane Layout

**Left Pane — River Segment List**

Ordered life segments / chapters / anchors. Each row:

```
[Year or range]  [Label]
Flow: open / constricted / blocked / steady
Status: proposed / confirmed
```

Examples:

- 1962-1970 Early Home
- 1981 Graduation / Launch
- 1991 Marriage
- 2026 Retirement

Data binding:

```javascript
state.kawa.segmentList
state.kawa.activeSegmentId
```

**Right Pane — Active River Segment Detail**

Shows the selected segment's Kawa elements in this order:

1. Flow
2. Rocks
3. Driftwood
4. Banks
5. Spaces
6. Narrator Notes / Quote
7. Status + Actions

---

## Component Layout

### A. Flow Card

**Label:** Flow

```
Flow State: [blocked | constricted | steady | open | strong]
Summary: [text]
Confidence: [proposed confidence, if unconfirmed]
```

Visual treatment: One horizontal band at top of panel. Thicker/wider band if open/strong, thinner/narrower if blocked/constricted.

Data binding:

```
segment.kawa.water.flow_state
segment.kawa.water.summary
segment.kawa.water.confidence
```

Edit behavior: Inline editable text, dropdown for flow state.

### B. Rocks Card

**Label:** Rocks

Each rock renders as a pill/card in a vertical stack showing: label, notes, confidence, proposed/confirmed badge.

Visual treatment: Large rounded blocks. Darker emphasis than driftwood.

Actions per rock: edit, delete, mark confirmed.

Add control: `+ Add Rock`

Data binding: `segment.kawa.rocks[]`

Empty state: "No rocks recorded for this segment yet."

### C. Driftwood Card

**Label:** Driftwood

Each driftwood item renders as a smaller card/pill showing: label, notes, confidence, proposed/confirmed badge.

Visual treatment: Lighter than rocks. Visually "mobile" / secondary. Should read as supports, traits, values, resources.

Actions: edit, delete, mark confirmed.

Add control: `+ Add Driftwood`

Data binding: `segment.kawa.driftwood[]`

### D. Banks Card

**Label:** Banks

Four grouped mini-lists:

```
Social:
- spouse
- children
- church

Physical:
- ranch house
- stairs

Cultural:
- Catholic upbringing

Institutional:
- school district
- military structure
```

Actions: add item, edit item, delete item.

Data binding:

```
segment.kawa.banks.social[]
segment.kawa.banks.physical[]
segment.kawa.banks.cultural[]
segment.kawa.banks.institutional[]
```

Note: Banks should visually appear as the "containment/context" of the river. In v1 use top/bottom border containers rather than complex diagram.

### E. Spaces Card

**Label:** Spaces

**This is the most important card after Flow.**

Each space is a highlighted opening/opportunity card showing: label, notes, confidence, proposed/confirmed badge.

Examples: chance to teach, more time with grandchildren, counseling opening, room to travel, church support.

Visual treatment: Lighter/open accent box. Visually separated from rocks and driftwood. Should feel like "room" or "opening."

Actions: edit, delete, mark confirmed.

Add control: `+ Add Space`

Data binding: `segment.kawa.spaces[]`

The Kawa materials make clear that these gaps are where flow still happens and where growth/intervention is possible, so they must be visually emphasized rather than buried.

### F. Narrator Notes / Quote Card

**Label:** Narrator Voice

Hold one short narrator-confirmed phrase or quote for the segment.

Examples:

- "That was when everything felt squeezed."
- "I still had room to move because of teaching."
- "Family was the bank around everything."

Data binding:

```
segment.narrator_note
segment.narrator_quote
```

Optional but important: Kawa is narrator-authored meaning, not just system labels.

### G. Status / Actions Footer

Show: Proposed/Confirmed, Last updated, Source, Session id if available.

Buttons:

```
Build Proposal    — calls Kawa projection endpoint
Accept All        — only if user explicitly wants current proposal
Edit              — unlocks inline edit state
Save              — saves provisional
Confirm Segment   — sets confirmed=true
Rebuild           — regenerates proposal from current anchor data
```

Rule: No silent auto-confirmation.

---

## Secondary View — River Strip

Minimal horizontal river strip above or below the segment list.

### Purpose

At-a-glance whole-life river, not just one segment.

### Representation

Horizontal strip broken into eras/segments:

- Each segment width proportional to duration
- Flow color/thickness based on flow_state
- Rock count badge
- Driftwood count badge
- Spaces count badge

```
[Early Home====][School===][Launch==][Marriage====][Career=======][Retirement===]
```

### Interaction

- Click segment -> loads detail panel
- Hover -> preview summary

Data binding: `state.kawa.segmentList`

Rule: Not a full custom SVG river yet unless easy. A styled horizontal strip is enough in v1.

---

## Data Bindings

### Frontend State

```javascript
state.kawa = {
  segmentList: [],
  activeSegmentId: null,
  activeSegment: null,
  isLoading: false,
  isDirty: false,
  mode: "river",
  filter: "all"
};
```

### Expected Backend Payload Shape

```json
{
  "segment_id": "seg_1991_marriage",
  "person_id": "uuid",
  "anchor": {
    "type": "timeline_event",
    "ref_id": "event_marriage_1",
    "label": "Marriage",
    "year": 1991
  },
  "kawa": {
    "water": {
      "summary": "Pressured but moving",
      "flow_state": "constricted",
      "confidence": 0.5
    },
    "rocks": [],
    "driftwood": [],
    "banks": {
      "social": [],
      "physical": [],
      "cultural": [],
      "institutional": []
    },
    "spaces": []
  },
  "provenance": {
    "source": "lori_proposed",
    "confirmed": false
  }
}
```

---

## API Wiring

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/kawa/list?person_id=...` | Load all segments for narrator |
| GET | `/api/kawa/segment?person_id=...&segment_id=...` | Load single segment |
| POST | `/api/kawa/build` | Build/rebuild proposal from extraction + timeline data |
| PUT | `/api/kawa/segment` | Save/update segment (proposed or confirmed) |

### Data Flow

```
timeline selection
→ derive segment anchor
→ build/load kawa segment
→ render right pane
→ user edits/confirms
→ save back to kawa store
```

---

## Lori Behavior in UI Context

When River tab is active, Lori should support Kawa-aware review prompts.

### Required Prompt Behavior

If no segment exists:

> "Would you like to build a river view for this part of your life?"

If proposal exists but unconfirmed:

> "I've sketched a possible river view for this period. What feels right, and what should change?"

If confirmed:

> "This river view is confirmed. Would you like to revise it or move to another chapter?"

### Kawa-Specific Follow-ups

- "What felt like the biggest rock here?"
- "What in you helped keep the water moving?"
- "What were the banks around you at the time?"
- "Where was there still some space?"

---

## Editing Rules

1. Users can edit any proposed Kawa element.
2. Users can add their own Kawa elements manually.
3. Proposed confidence must remain visible until confirmation.
4. Confirmation is per segment, not global.
5. Editing a confirmed segment creates a new saved version and unconfirms until re-confirmed.

---

## Component Behavior Details

### Segment Selection

- Selecting a timeline event auto-highlights corresponding river segment if one exists
- Selecting a river segment can optionally highlight the timeline event

### Empty State

```
No river view exists yet for this segment.
[Build Proposal]
```

### Dirty State

```
You have unsaved river edits.
[Save] [Discard]
```

### Confirmed State

Badge: `Confirmed by narrator`

### Proposed State

Badge: `Proposed — needs narrator confirmation`

---

## Visual Hierarchy

Order of emphasis:

1. Flow — defines the chapter
2. Rocks — defines restriction
3. Spaces — defines opportunity
4. Driftwood — defines personal resources
5. Banks — defines context/containment
6. Narrator note — optional voice

---

## Out of Scope

Do not build in this WO:

- Freehand drawing canvas
- Drag-and-drop rock placement
- Full SVG river simulation
- Auto-memoir rewriting from Kawa
- Side-by-side clinical scoring instruments
- Collaborative multi-user/team river mode

Those can come later (WO-KAWA-UI-02+).

---

## Acceptance Tests

### UI Structure

- [ ] Timeline and River tabs both visible
- [ ] River tab opens without breaking Timeline
- [ ] Left segment list renders
- [ ] Right detail panel renders

### Data Loading

- [ ] River list loads from /api/kawa/list
- [ ] Single segment loads from /api/kawa/segment
- [ ] Empty-state shown when no segment exists

### Proposal Flow

- [ ] Build Proposal button calls /api/kawa/build
- [ ] Returned segment renders correctly
- [ ] Proposed badge visible

### Editing

- [ ] User can edit flow summary/state
- [ ] User can add/edit/delete rocks
- [ ] User can add/edit/delete driftwood
- [ ] User can add/edit/delete banks
- [ ] User can add/edit/delete spaces
- [ ] Save writes through /api/kawa/segment

### Confirmation

- [ ] Confirm Segment sets confirmed state
- [ ] Confirmed badge visible after save
- [ ] Editing confirmed segment creates dirty state

### Linking

- [ ] Selecting timeline segment can open corresponding river segment
- [ ] River segment shows its anchor label/year

### Safety

- [ ] River edits do not mutate canonical fact/timeline data
- [ ] Proposed vs confirmed always visually distinct

---

## Required Report

```
WO-KAWA-UI-01 REPORT

FILES EDITED
- ...

FILES CREATED
- ...

UI
- Timeline/River tabs implemented: PASS / FAIL
- River segment list implemented: PASS / FAIL
- River detail pane implemented: PASS / FAIL
- River strip implemented: PASS / FAIL

DATA BINDING
- list endpoint wired: PASS / FAIL
- detail endpoint wired: PASS / FAIL
- build endpoint wired: PASS / FAIL
- save endpoint wired: PASS / FAIL

EDITING
- flow editable: PASS / FAIL
- rocks editable: PASS / FAIL
- driftwood editable: PASS / FAIL
- banks editable: PASS / FAIL
- spaces editable: PASS / FAIL

STATUS
- proposed badge works: PASS / FAIL
- confirmed badge works: PASS / FAIL

LINKING
- timeline-to-river linking works: PASS / FAIL
- river-to-timeline linking works: PASS / FAIL

SAFETY
- chronology unaffected: PASS / FAIL
- canonical fact layer unaffected: PASS / FAIL

TESTS
- acceptance tests run: PASS / FAIL

NOTES
- what was deferred
- what should come next in WO-KAWA-UI-02
```

---

## Tight Patch Block

```
RULES FOR WO-KAWA-UI-01
1. Build Kawa as a visible parallel UI layer beside Timeline, not as hidden metadata.
2. Add a River tab with segment list, segment detail, and minimal river strip overview.
3. Expose Flow, Rocks, Driftwood, Banks, and Spaces as editable UI components.
4. Keep all Kawa content provisional until narrator-confirmed and visually label proposed vs confirmed.
5. Do not mutate canonical fact/timeline storage from River UI edits.
6. Support build, edit, save, and confirm flows through the Kawa API.
7. Ship text-first / shape-first UI only; no freehand drawing canvas in this WO.
```
