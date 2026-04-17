# WO-KAWA-01 -- Parallel Kawa Layer + Validation Harness

**Status:** Specced, not started
**Priority:** After WO-SCHEMA-02 and WO-CLAIMS-02
**Depends on:** Existing extraction pipeline, timeline/chronology, WO-PHENO-01 (optional)
**Origin:** Michael Iwama NMOTA 2025 presentation; Newbury & Lape 2021 aging-in-place pilot; UND OT life history papers (Crepeau, Norell)
**Reference docs:** `Kawa Model for Life History Documentation.docx`, `newbury-lape-2021-well-being-aging-in-place-and-use-of-the-kawa-model-a-pilot-study.pdf`

---

## Objective

Add a non-destructive Kawa interpretation layer that:

- attaches to existing timeline segments / life chapters
- is proposed by Lori, confirmed by narrator
- can be measured for usefulness
- never replaces existing extraction, timeline, or memoir pipelines

The Kawa model (Iwama, late 1990s) uses a river metaphor to represent life flow. Five constructs -- water, rocks, driftwood, riverbanks, spaces -- provide a cross-sectional view of a person's ecology at any point in time. The key architectural insight is: **the timeline answers "what happened"; Kawa answers "what was the flow like there."**

---

## Core Principle: Client as Theorist

The narrator defines meaning. Lori proposes candidates from existing data; the narrator confirms, corrects, or rejects. The system NEVER silently decides what constitutes a rock, driftwood, or space. This keeps faith with the Kawa philosophy and matches the collaborative model shown in the Newbury/Lape pilot study.

---

## Western Translation Layer

Narrators never see Kawa vocabulary. Lori uses plain English that maps 1:1 to constructs:

| Kawa Construct | Japanese | What Lori Says | What It Captures |
|---|---|---|---|
| Water / Flow | Mizu | "Did life feel like it was moving forward, or stuck?" | Narrator's self-assessment of vitality and well-being |
| Riverbanks | Torimaki | "Who or what was shaping your world then?" | Social and physical environment as container |
| Rocks | Iwa | "What felt like the biggest thing standing in your way?" | Obstacles, challenges, barriers |
| Driftwood | Ryuboku | "What in you helped you keep going?" | Personal assets, skills, values, beliefs |
| Spaces | Sukima | "Where was there still some room to breathe?" | Opportunities, openings, agency, hope |

---

## Phase 1 -- Data Model (No UI Yet)

### New Store

```
DATA_DIR/kawa/
  people/<person_id>/
    segments/<segment_id>.json
```

### Segment Schema

```json
{
  "segment_id": "seg_1991_marriage",
  "anchor": {
    "type": "timeline_event",
    "ref_id": "marriage_1",
    "year": 1991
  },
  "kawa": {
    "water": {
      "flow_state": "constricted",
      "summary": "Pressured but moving forward",
      "confidence": 0.4
    },
    "rocks": [
      {
        "label": "financial stress",
        "severity": "major",
        "narrator_quote": null,
        "confidence": 0.6
      }
    ],
    "driftwood": [
      {
        "label": "supportive spouse",
        "role": "helped",
        "confidence": 0.7
      }
    ],
    "banks": {
      "social": ["family expectations", "small-town community"],
      "physical": ["rural isolation"],
      "cultural": [],
      "institutional": []
    },
    "spaces": [
      {
        "label": "career opportunity",
        "type": "opportunity",
        "confidence": 0.3
      }
    ]
  },
  "provenance": {
    "source": "lori_proposed",
    "confirmed": false,
    "confirmed_at": null,
    "session_id": null,
    "version": 1
  }
}
```

### Rules

- NEVER overwrite -- always append versions if updated
- `confirmed = true` only via narrator explicit confirmation
- Proposed items start with `source: "lori_proposed"`, confirmed items become `source: "narrator_confirmed"`
- Driftwood `role` must be one of: `helped`, `snagged`, `mixed` (Kawa is relational -- driftwood can help or clog)

### Flow State Scale

5-step scale for `water.flow_state`:

- `blocked` -- life felt stopped
- `constricted` -- moving but under pressure
- `steady` -- manageable, stable
- `open` -- flowing well
- `strong` -- deep, powerful, thriving

Plus free text in `water.summary`.

---

## Phase 2 -- Kawa Projection Engine

### New function

```
buildKawaProjection(person_id, segment_id)
```

### Inputs

- Timeline events for the era
- Extraction candidates (family, residence, education, career)
- Phenomenology outputs (WO-PHENO-01 meaning units, if available)

### Mapping Logic (first pass)

| Existing Data | Kawa Mapping |
|---|---|
| family, community, location, workplace | banks |
| stress, conflict, loss, illness, barriers | rocks |
| skills, relationships, faith, values | driftwood |
| meaning, growth, opportunity, change | spaces |
| narrator self-assessment | water |

### Output

Populates low-confidence Kawa proposal. All items start `confirmed: false`.

---

## Phase 3 -- Lori Confirmation Loop

### Conversational Pattern

Lori proposes -> narrator edits -> system stores confirmed version.

Example exchange:

> **Lori:** "You've told me about moving to Washington for that first teaching job. I'd love to understand what that time was really like -- not just what happened, but what it felt like to live through it."
>
> **Lori:** "It sounds like family expectations and the small-town community were shaping your world then. Does that feel right?"
>
> **Narrator:** "Yeah, but also the church. That was a big part of it."
>
> **Lori:** "Got it -- the church was part of what contained your world. And the biggest thing standing in your way?"
>
> **Narrator:** "Money. We had nothing when we started."
>
> **Lori:** "And what in you helped you keep going despite that?"
>
> **Narrator:** "Stubbornness, I guess. And my wife. She believed in it when I didn't."

### Full Kawa Question Set (Western Language)

**Initial framing:**
- "I'd like to understand not just what happened, but what that time felt like for you."
- "Looking back at that chapter of your life..."

**Flow / Water:**
- "Did life feel like it was moving forward, or did it feel stuck?"
- "How would you describe the flow of your life then -- rushing, steady, stagnant?"
- "Were there parts that felt easier than others?"

**Banks / Environment:**
- "Who or what was shaping your world then?"
- "What was the community like? The family expectations?"
- "Did where you lived help or constrain you?"
- "Who were the people you spent the most time with?"

**Rocks / Obstacles:**
- "What felt like the biggest thing standing in your way?"
- "Was there anything you wanted to do but couldn't?"
- "If you could have removed one obstacle from that time, what would it have been?"

**Driftwood / Resources:**
- "What in you -- a skill, a belief, a stubbornness -- helped you keep going?"
- "What personal qualities got you through?"
- "Was there anything about you that made things harder instead of easier?"
- "Were there habits or traits that got stuck against the obstacles?"

**Spaces / Openings:**
- "Even when things were hard, where was there still some room to breathe?"
- "What kept a door open?"
- "What was the smallest thing that made a difference?"
- "Where was there still some hope or possibility?"

### Behavior Rules

- NEVER assert truth
- ALWAYS ask for correction
- STORE narrator edits as authoritative
- Respect "I don't know" or "it wasn't like that" -- not every chapter needs a full Kawa annotation

---

## Phase 4 -- UI: River View (Parallel to Timeline)

### Tab Structure

```
Timeline | River
```

### UI Stage A -- Text-First River Panel (Build First)

River tab shows structured cards for the selected chapter:

```
[Marriage / 1991]

Flow: pressured but moving          [edit]

Rocks:
- Money stress (major)               [edit] [remove]
- Relocation uncertainty             [edit] [remove]

Driftwood:
- Partner support (helped)           [edit] [remove]
- Faith (helped)                     [edit] [remove]
- Stubbornness (mixed)               [edit] [remove]

Banks:
- Family expectations (social)
- Small-town context (social)
- Rural isolation (physical)
- Church community (cultural)

Spaces:
- Teaching opportunity               [edit] [remove]
- First home                         [edit] [remove]

"We had nothing when we started, but she believed in it when I didn't."
```

No graphics yet. Text cards alongside chronology accordion.

### UI Stage B -- River Strip Timeline

Once data model is stable, render horizontal river view:

- Left to right = time
- Width/depth of river band = perceived flow
- Rock nodes = obstacles (sized by severity)
- Driftwood nodes = supports (with helped/snagged indicator)
- Context rails above/below = banks (social, physical, cultural)
- Highlighted channels between obstacles = spaces

### UI Stage C -- Interactive Cross-Section Editor

Select one era, see cross-section:
- Banks on both sides
- Rocks in channel (sized by severity)
- Driftwood lodged or floating
- Open spaces between them
- Water shown as narrow/moderate/open

This is where the OT value comes alive -- matches clinical Kawa practice.

### Recommended Transitional UI -- River + Timeline Split

```
Top pane:  factual timeline (existing chronology accordion)
Bottom pane: Kawa river for selected event/chapter
```

Click "Retirement 2026" on timeline -> river below updates.

---

## Phase 5 -- Instrumentation

### Metrics

1. **Engagement delta** -- avg response length (timeline vs kawa prompts), follow-up depth
2. **Correction rate** -- % of Lori Kawa proposals edited by narrator (target: >= 60% means engagement)
3. **Novel information** -- % of Kawa items NOT found in extraction layer (target: >= 30%)
4. **Retention signal** -- how often users return to River view
5. **Emotional density** (optional) -- sentiment variance vs normal interview turns

---

## Phase 6 -- A/B Test (Mandatory Before Deep Integration)

**Mode A -- Standard Lori:** Chronological questioning only
**Mode B -- Hybrid Lori:** Inject Kawa prompts every 3-5 turns after sufficient chapter data

Compare: session length, user corrections, richness of extracted meaning, user satisfaction (1-5 at end).

---

## Phase 7 -- Prompt Mode Switch (Controlled)

```javascript
state.session.currentMode = "chronological" | "kawa_reflection" | "hybrid"
```

- `chronological` -> current system
- `kawa_reflection` -> Kawa-first questioning (5-6 turns, then return)
- `hybrid` -> mixed mode

### Trigger Logic

Enter Kawa reflection mode when:
- Narrator has shared enough about a chapter (>= 3 extraction fields populated for that era)
- At least 10 turns since last Kawa reflection
- Narrator hasn't explicitly declined reflection

---

## Phase 8 -- Memoir Experiment (Read-Only)

Do NOT rewrite memoir system yet. Generate two outputs side-by-side:

**Output A (existing):** Chronological narrative

**Output B (experimental):** Kawa-structured narrative:

> "This period was marked by increasing financial pressure and the uncertainty of relocation. The support of a committed partner and deep faith provided the resources to navigate through. Family expectations and the constraints of rural life shaped the boundaries. Despite the obstacles, a teaching opportunity and the promise of a first home kept space open for growth."

Compare side-by-side. Do not ship Output B until validated.

---

## Phase 9 -- Acceptance Criteria

Move forward ONLY if:

1. >= 30% of Kawa entries contain new information not in extraction layer
2. >= 60% of Kawa proposals require narrator correction (proves engagement)
3. Users spend >= 20% more time per session in Kawa mode
4. Memoir B judged "more meaningful" in >= 60% of comparisons

---

## Phase 10 -- Decision Gate

**If FAIL:** Keep as optional reflection tool. Do not integrate deeper.

**If PASS:** Move to WO-KAWA-02 -- Deep Integration:
- Influence question selection
- Influence memoir structure
- Integrate into phenomenology layer (WO-PHENO-01)
- Kawa-aware bio-builder staging

---

## Architectural Notes

### Why This Fits Hornelore

- **Anchor points already exist.** Chronology accordion, timeline events, life map phases provide segments. Kawa annotations attach to existing `segment_id`.
- **Confirmation pattern already exists.** Extraction proposes, projection stores, narrator confirms. Kawa follows the same church/state separation.
- **Mode switch already exists.** `lvRouteTurn()` already routes turns by context. `kawa_reflection` becomes a new turn mode alongside `interview`, `memory_echo`, etc.
- **Non-destructive.** Kawa layer is additive. Existing extraction, timeline, and memoir pipelines are untouched.
- **Fully reversible.** If Kawa doesn't prove useful, remove the tab and the data sits inert.

### Church/State

- Kawa data lives in its own store (`DATA_DIR/kawa/`)
- Never mixes with extraction facts or profile data
- Never overwrites timeline events
- Proposals are always flagged as unconfirmed until narrator validates

### Key Insight

> You're not replacing the timeline. You're testing whether "meaning density per segment" increases when Kawa is present.

The pilot study shows Kawa improves communication, engagement, and perceived well-being. The job is to verify: does it improve memory capture quality in Hornelore?

### The One-Line UI Metaphor

> **A timeline that turns into a river when you want meaning.**

---

## Addendum: River of Memories + Engine Methods

### River of Memories (Pre-Generated River Skeleton)

The system pre-generates a "River of Memories" for each narrator based on:

- Historical chronology JSON (1900-2026 world events) -> bank context
- Already-extracted personal data (family, education, career, residence) -> proposed rocks/driftwood
- Timeline events and life map phases -> segment anchors

The narrator doesn't start with a blank river. They start with a river that already has banks (historical context) and proposed elements from what they've already told Lori. They correct it into truth. Same pattern as ghost decades in the chronology accordion, but for Kawa.

### Method 1: Metaphorical Tagging (Extraction Pipeline Extension)

Add `kawa_type` as a projection step after extraction. Entities already land with field paths (`education.schoolName`, `laterYears.significantEvent`). The Kawa projection layer adds a secondary tag:

| Extraction Field Category | Default Kawa Tag |
|---|---|
| Loss, illness, conflict, barrier | `rock` |
| Skill, relationship, faith, value | `driftwood` |
| Family, community, location, culture | `bank` |
| Opportunity, growth, change, achievement | `space` |
| Self-assessment, vitality, satisfaction | `water` |

Narrator always confirms or reclassifies. The tag is a proposal, never a truth.

### Method 2: Sukima Querying (Negative Space Detection)

Query across timeline + extraction data for segments where:

- Challenges exist alongside continued engagement (rocks present but no collapse)
- Narrator kept doing meaningful activities despite obstacles
- Gaps between major events where no rocks are recorded (possible unexamined flow periods)
- A rock was mentioned but followed by a success event

These are the sukima — the spaces where water kept flowing. This is where Lori asks the deepest questions:

> "In 1982, you were dealing with the farm crisis, but you were still teaching every day and gardening on weekends. How did those things help you keep moving?"

### Method 3: Cross-Sectional Narrative Engine (Decade Pools)

Instead of rendering the full river across time, display one era at a time:

- **Bottom/sides:** Historical context from chronology JSON (the riverbed/banks)
- **Suspended elements:** Narrator's rocks and driftwood floating within that decade's water
- **Water width:** Reflects narrator's self-assessed flow for that period

Lower cognitive load for elderly narrators. They don't traverse the whole river — they look at one pool at a time.

### Historical Chronology Kawa Extension

Add `kawa_impact` field to the 1900-2026 historical events JSON:

```json
{
  "year": 1962,
  "event": "Cuban Missile Crisis",
  "kawa_impact": "bank_constriction",
  "narrative_prompt": "Do you remember the tension back then? How did it change how your family planned?"
}
```

Kawa impact types for world events:

- `bank_constriction` -- social/economic pressure narrowing everyone's river
- `shared_rock` -- universal obstacle (pandemic, war, economic crisis)
- `bank_expansion` -- social liberation, new opportunity (GI Bill, civil rights)
- `contextual_shift` -- culture change that reshaped the riverbed

When the River of Memories is pre-generated for a narrator born in 1940, the banks already show postwar optimism, the Vietnam era, the farm crisis, the digital age — and the narrator drops their personal story into that shaped channel.

---

## References

1. Iwama, M. K. (2006). *The Kawa Model: Culturally Relevant Occupational Therapy.* Churchill Livingstone.
2. Iwama, M. K., Thomson, N. A., & Macdonald, R. M. (2009). The Kawa model: The power of culturally responsive occupational therapy. *Disability and Rehabilitation, 31*(14), 1125-1135.
3. Newbury, R. S. & Lape, J. E. (2021). Well-being, Aging in Place, and Use of the Kawa Model: A Pilot Study. *Annals of International Occupational Therapy, 4*(1), 15-25.
4. Teoh, J. & Iwama, M. K. (2015). *The Kawa Model Made Easy.* kawamodel.com.
5. Crabtree, N. & Gregoire, S. (2019). Evolution of OT Practice: Life History of Elizabeth Crepeau. UND Scholarly Commons.
6. Hansen, C. & Zimmer, J. (2018). Evolution of OT Practice: Life History of Diane Norell. UND Scholarly Commons.
