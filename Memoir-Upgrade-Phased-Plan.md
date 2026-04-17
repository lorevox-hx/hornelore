# Memoir Upgrade -- Phased Plan (Lorevox vNext)

**Status:** REFERENCE DESIGN -- saved for future implementation  
**Created:** 2026-04-15

---

## Objective

Move Memoir from:
"structured narrative assembled from facts"

To:
"lived experience narrative with preserved meaning, texture, and reflection"

Without violating:

- HITL authority
- Archive -> History -> Memoir separation
- Candidate -> Review -> Promote pipeline

---

## Phase 1 -- Phenomenological Signal Capture (Non-Destructive)

**Goal:** Capture experience signals during interview without changing extraction or facts.

### 1.1 Meaning Signal Detection Layer (local, rule-based)

Extend existing Meaning Engine to tag:

- Turning points: "that's when everything changed"
- Reflection: "looking back..."
- Emotional weight: "I'll never forget"
- Disorientation: "I didn't understand it then"
- Identity: "that's who I became"

Output per turn:

```json
{
  "meaning_signals": [
    { "type": "turning_point", "confidence": 0.82 },
    { "type": "reflection", "confidence": 0.74 }
  ]
}
```

### 1.2 Add to runtime71 (read-only for model)

Extend `buildRuntime71()`:

```json
{
  "meaning_context": {
    "signals": ["turning_point", "reflection"],
    "density": 0.6
  }
}
```

Sits alongside: affect_state, fatigue_score, era.

### 1.3 Archive Preservation (CRITICAL)

Store raw phenomenological language in Archive:

- DO NOT normalize
- DO NOT summarize
- DO NOT extract away

"Archive is immutable ground truth."

### Acceptance Tests

- Signals detected in >= 70% of reflective statements
- No impact on candidate extraction accuracy
- No writes to facts/history

---

## Phase 2 -- Memory Object Enrichment

**Goal:** Upgrade "memory" from text to structured lived-experience unit.

### 2.1 New Memory Schema

```json
{
  "id": "...",
  "type": "memory",
  "text": "...",
  "era": "early_adulthood",
  "approx_year": 1985,
  "phenomenology": {
    "affect": "reflective",
    "tone": "bittersweet",
    "clarity": "fragment",
    "temporal_position": "retrospective",
    "significance": "turning_point"
  }
}
```

### 2.2 Extraction Rules

- Only populate if confidence > threshold
- Otherwise leave null (never hallucinate)

### 2.3 UI

Do NOT surface fully yet. But store it, log it, make it queryable.

### Acceptance Tests

- No overwrite of user text
- Phenomenology fields sparsely populated (correct bias)
- Zero bleed into facts layer

---

## Phase 3 -- Lori Interview Behavior Upgrade

**Goal:** Shift Lori from "fact collector" to "experience facilitator."

### 3.1 Prompt Composer Additions

When `meaning_signals` present:

| Signal | Before (current) | After (phenomenological routing) |
|--------|------------------|----------------------------------|
| Turning point | "What happened next?" | "What about that moment made it stand out?" |
| Reflection | "What happened next?" | "When you look back now, what feels different about it?" |
| Fragment | "What happened next?" | "Even a small piece -- what do you remember first?" |

### 3.2 Mode Interaction

Map to existing modes:

- recognition -> anchor memory
- grounding -> slow + present
- open -> deepen meaning

### 3.3 Hard Rules

Lori must NEVER interpret meaning for the narrator. ONLY invite articulation.

### Acceptance Tests

- Follow-ups reference experience, not just events
- No increase in hallucinated facts
- Conversation length increases but remains coherent

---

## Phase 4 -- Memoir Assembly Engine (MAJOR)

**Goal:** Transform memoir generation logic.

### 4.1 New Assembly Strategy

Instead of: timeline -> paragraph  
Use: memory clusters -> meaning arcs -> narrative sections

### 4.2 Narrative Arc Roles

Formalize: setup, tension, turning_point, reflection, resolution

### 4.3 Section Builder Logic

Each section should:

1. Anchor in time (History)
2. Insert memory fragments (Archive-derived)
3. Preserve narrator phrasing
4. Add light connective tissue (AI)

### 4.4 Example Output Shift

Before: "In 1985, he moved to Austin and began working."

After: "In 1985, he moved to Austin. 'I didn't think much of it at the time,' he recalls, but looking back, it marked the beginning of a different kind of life."

### Acceptance Tests

- >= 60% of memoir sentences traceable to original language
- Clear narrative arcs per section
- No AI-invented meaning

---

## Phase 5 -- Memoir Review UI (HITL)

**Goal:** Give user control over meaning, not just facts.

### 5.1 New Review Actions

Per memoir segment:

- Keep as written
- Edit wording
- Lock phrasing (protected)
- Mark as important
- Remove

### 5.2 Meaning Visibility

Show subtle tags: "Turning point", "Reflection", "Memory fragment" -- not intrusive, just visible.

### Acceptance Tests

- Users can override AI framing
- Locked text never changes
- Edits persist across rebuild

---

## Phase 6 -- Life Map + Memoir Integration

**Goal:** Bridge structure and meaning.

### 6.1 Life Threads to Narrative Arcs

Use existing Life Threads system:

- nodes = memories/events
- edges = meaning relationships

### 6.2 Map to Memoir

- Threads -> sections
- Dense clusters -> chapters
- High-degree nodes -> key moments

### Acceptance Tests

- Threads visually map to memoir sections
- No orphan sections without source nodes

---

## Phase 7 -- Export Upgrade (DOCX)

**Goal:** Deliver a readable human memoir.

Add:

- Section titles based on meaning (not just time)
- Pull quotes from narrator language
- Optional "reflection blocks"

### Acceptance Tests

- Reads like a story, not a report
- Family members can follow narrative without system knowledge

---

## Critical Do-Not Rules

- Do NOT auto-promote meaning to fact
- Do NOT summarize away narrator language
- Do NOT infer emotional truth beyond what is stated
- Do NOT collapse ambiguity

---

## Final Architecture After Upgrade

```
ARCHIVE
  | (raw lived experience)
  v
HISTORY
  | (structured + verified)
  v
MEMOIR
  | (phenomenological assembly)
  v
MEANING LAYER (NEW -- spans all three)
```

---

## Strategic Impact

This turns Lorevox into not just a memory system or a family history tool, but a lived-experience preservation engine.

---

## Recommended First WO

WO-MEM-01: Meaning Signal Detection Layer (Phase 1) -- tight, file-level patch plan, exact functions, and test harness.

---

## Phenomenology Core Concept

A phenomenological answer doesn't try to say how many people feel something or how often it happens. It tries to get at: What is this experience like, from the inside, in a way that feels true across people?

What's shared across people is not the exact events or even the same emotions. It's the structure of experience: remembering in fragments, attaching meaning after the fact, wanting to be known, feeling certain moments "stand out" without knowing why.

The layer Lorevox should capture beyond facts and memories:

- texture ("it felt quiet, like everything slowed down")
- orientation ("I didn't realize it was important at the time")
- meaning shift ("looking back, that's when things changed")

That's the layer where memoir becomes human, not just structured.
