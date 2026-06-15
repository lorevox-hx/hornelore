# WO-PHENO-01 -- Phenomenology Layer for Lori

**Status:** DESIGN COMPLETE -- saved for future implementation  
**Created:** 2026-04-15  
**Section Name:** Lived Experience & Wisdom to Share  
**Internal Key/Path:** `lived_experience_wisdom`

---

## Objective

Add a phenomenology-aware interview and extraction layer so Lori can gently draw out lived experience, and the backend can convert transcripts into:

- meaning units
- themes
- essence statement
- memoir draft
- family-facing message

This must fit the existing LoreVox/Hornelore doctrine:

- Archive = raw transcript
- History = structured interpretation with provenance
- Memoir = narrative output

No direct write from conversational inference into canonical truth. This work adds an experience layer, not a truth overwrite path.

---

## Why This WO Exists

Current extraction is strongest on:

- facts
- timeline items
- entities
- relationships

But it is weak on:

- lived experience
- emotional meaning
- retrospective interpretation
- "what this meant to me"
- "what I want my family to understand"

That gap matters because older narrators often do not start with facts. They start with:

- scenes
- feelings
- family tension
- memory fragments
- lessons only understood later

This WO gives Lori a controlled way to interview for that material and gives extraction a formal output structure for it.

---

## Architectural Placement

```
Archive/
  shadow/
    raw transcripts
    raw notes
    raw imports

History/
  facts/
  timeline/
  entities/
  lived_experience_and_wisdom/
    meaning_units
    themes
    essence
    family_message

Memoir/
  drafts/
  composed_sections/
```

Per person/session path:

```
DATA_DIR/history/lived_experience_and_wisdom/people/<person_id>/sessions/<session_id>/
  experience.json
```

### Schema Split

```json
{
  "lived_experience": {
    "meaning_units": [],
    "themes": [],
    "essence": null
  },
  "wisdom_to_share": {
    "lessons": [],
    "family_message": null,
    "advice": [],
    "what_should_not_be_lost": []
  }
}
```

- **Lived Experience** = interpretation of the past
- **Wisdom to Share** = legacy-facing output

---

## Scope

### In Scope

1. Add a phenomenology-oriented prompt/question bank layer in interview flow
2. Add extraction support for: meaning units, themes, essence, memoir draft, family-facing message
3. Keep outputs non-canonical by default
4. Store with provenance and confidence
5. Add tests and eval harness cases

### Out of Scope

- No automatic promotion of themes/essence into canonical facts
- No changes to Life Map authority model
- No cross-person clustering
- No final memoir publishing UI overhaul
- No vector retrieval redesign
- No FaceMesh / TTS / trainer work mixed into this WO

---

## Design Rules

1. **Phenomenology is not fact extraction**
   - "I felt invisible" is not a fact row
   - "That shaped me" is not a timeline event
   - These must live in a separate experience structure

2. **Do not flatten lived experience into checkbox themes too early**
   - preserve source spans
   - preserve ambiguity
   - allow mixed emotional tones

3. **Essence is synthesized, not user-declared truth**
   - store as generated interpretive output
   - always linked to transcript/session provenance

4. **Memoir output is downstream composition**
   - never treated as authoritative fact source

5. **Lori should interview more gently**
   - fewer interrogation-style fact prompts
   - more reflective prompts when in relevant mode

---

## Phase 1 -- Read and Understand Current Code Paths

### Required Read Targets

- `server/code/api/routers/extract.py`
- `ui/js/interview.js`
- `ui/js/bio-builder.js`

### Read for Nearby Dependencies

- prompt composition path used by interview runtime
- any extraction schemas / adapters / candidate models
- any existing memoir preview or narrative synthesis path
- any existing review queue structure that can hold non-fact outputs

### Required Understanding Report Before Coding

Claude must first produce a short internal implementation note covering:

- where interview questions are currently selected
- whether interview mode / section / currentMode already affects prompts
- where extraction response schema is defined
- where non-fact structured outputs can safely live
- whether bio-builder can stage phenomenology prompts or just fact intake

Do not start patching until that map is clear.

---

## Phase 2 -- Interview Question System Changes

**File target:** `ui/js/interview.js`

### Question Bank

```javascript
const PHENOMENOLOGY_QUESTION_BANK = {
  gentle_entry: [
    "When you think about your younger years, what's one moment that still feels very clear to you?",
    "Who comes to mind first when you think about your family back then?",
    "What kind of home did it feel like you lived in?",
    "What's a small detail most people wouldn't think to ask about?"
  ],
  scene_building: [
    "What did that time in your life feel like, day to day?",
    "What do you remember noticing around you?",
    "What kind of person were you then?",
    "What did a normal day look like for you?"
  ],
  meaning_emergence: [
    "Looking back, why does that memory stay with you?",
    "What did that time teach you, even if you didn't realize it then?",
    "How do you think that shaped the person you became?",
    "Is there something about that experience you wish others understood better?"
  ],
  family_connection: [
    "Have you ever told your family this story before?",
    "What do you hope they understand about you from this?",
    "Is there something about your life you feel they don't fully see?",
    "What would you want them to remember about this time?"
  ],
  legacy_layer: [
    "If you had to put it simply, what did that part of your life mean to you?",
    "What stayed with you from it over the years?",
    "If this story were passed down, what should never be lost?",
    "What would you say to your family about it, in your own words?"
  ]
};
```

### Selection Triggers

- narrator is discussing family memories
- narrator gives reflective or emotionally weighted text
- narrator references aging, legacy, regret, pride, loss, or "want family to know"
- section intent is memoir/meaning rather than strict profile capture

### Lori Interaction Rules

- Prefer "Tell me more about that" over new questions
- Mirror language lightly: "That sounds like it stayed with you."
- Allow pauses / silence
- Never rush to next phase if depth is emerging
- Accept short answers
- Do NOT push yet in Phase 1
- Single question per turn, conversationally phrased

---

## Phase 3 -- Extraction Schema Additions

**File target:** `server/code/api/routers/extract.py`

### Meaning Units

```json
{
  "id": "mu_001",
  "text": "We were all in that small house together and it felt alive all the time",
  "kind": "environment",
  "emotional_tones": ["warmth", "belonging"],
  "time_reference": "childhood",
  "people": ["family"],
  "source_span": {
    "turn_start": 12,
    "turn_end": 12
  },
  "confidence": 0.82
}
```

Allowed `kind` starter set: `environment`, `relationship`, `emotion`, `reflection`, `identity`, `loss`, `legacy`, `family_meaning`

### Themes

```json
{
  "id": "theme_001",
  "name": "family_closeness",
  "description": "The narrator describes family togetherness as central to how home was experienced.",
  "meaning_unit_ids": ["mu_001", "mu_004"],
  "confidence": 0.78
}
```

### Essence

```json
{
  "text": "The narrator's experience is one of looking back on family closeness as something ordinary at the time but deeply formative in later life.",
  "basis_theme_ids": ["theme_001", "theme_003"],
  "confidence": 0.70
}
```

### Memoir Draft

```json
{
  "text": "When I think back on those years, what stays with me most is how close we all were...",
  "basis_theme_ids": ["theme_001", "theme_003"],
  "voice": "first_person_reflective",
  "confidence": 0.68
}
```

### Family Message

```json
{
  "text": "What I want my family to understand is that the closeness we had shaped how I came to think about love and home.",
  "basis_theme_ids": ["theme_001"],
  "voice": "direct_to_family",
  "confidence": 0.72
}
```

---

## Phase 4 -- Extraction Rules

### Hard Guards

Do not generate essence/memoir/family message from thin content like:

- "I was born in Bismarck"
- "I graduated in 1981"
- "My son was born in 2002"

Need reflective basis, not just facts.

### Minimum Support Rules

- **themes:** require at least 2 meaning units or one strong reflective unit
- **essence:** require at least 1 theme
- **memoir_draft:** require at least 1 theme plus reflective or descriptive support
- **family_message:** require explicit or strongly implied family-facing meaning

---

## Phase 5 -- Bio Builder Integration

**File target:** `ui/js/bio-builder.js`

Create a separate review block or staging section labeled:

- "Experience & Meaning" or "Reflective Themes" or "Memoir Draft Inputs"

This section is read/review oriented, not truth-promotion oriented.

### Do Not

- put these into canonical fact candidate rows as if they were facts
- mix them with DOB/POB/relationship extractions
- allow them to overwrite questionnaire truth fields

---

## Acceptance Tests

### A. Unit-level extraction tests

**A1 -- reflective family memory produces experience outputs**
Input: "When I think back on those years, what stays with me most is how close we all were. At the time I didn't realize it, but later I understood that it shaped how I think about family."
Expected: meaning_units >= 2, themes >= 1, essence present, memoir_draft present, no factual field overwrite

**A2 -- plain fact statement does not fabricate experience layer**
Input: "I was born in Williston in 1962 and graduated from high school in 1981."
Expected: standard factual extraction works, experience outputs empty/null

**A3 -- family-facing legacy statement produces family_message**
Input: "I want my grandchildren to know that even when life was hard, we stayed together and that mattered."
Expected: family_message present, togetherness/resilience theme, no false timeline events

**A4 -- ambiguous emotion alone does not overproduce**
Input: "It was hard. Really hard."
Expected: at most one low-confidence meaning unit, no strong essence, no memoir draft

### B. Interview behavior tests

**B1 -- reflective content triggers reflective follow-up**
**B2 -- plain biographical answer can still stay factual**
**B3 -- question pacing** (single question per turn)

### C. Bio Builder staging tests

**C1 -- experience outputs render separately from fact candidates**
**C2 -- no truth promotion path** (no writes to protected fact fields)

### Eval Harness

Suggested file: `phenomenology_extraction_cases.json`

Categories: `experience_none`, `experience_meaning_unit`, `experience_theme`, `experience_essence`, `experience_family_message`, `experience_guard_no_fabrication`

Target: 80% correctness on obvious positive/negative cases, zero protected-fact overwrites.

---

## Implementation Notes

### Do

- read first
- patch surgically
- preserve current architecture boundaries
- keep experience outputs separate from truth
- use existing provenance patterns where available
- fail closed when support is thin

### Do Not

- redesign the entire interview system
- add a giant new abstraction unless already justified by current code
- mix essence/memoir into fact candidate queues
- let phenomenology prompts dominate every interview turn
- convert reflection into fake timeline events

---

## Claude Review Notes (2026-04-15)

1. **Trigger model needed:** The question bank phases are well-designed but the selection heuristic needs the LLM itself to classify whether last answer was reflective vs factual -- keyword matching alone won't catch phenomenologically rich answers like "that little house on the hill."

2. **Sequencing concern:** Running the full meaning_units -> themes -> essence -> memoir pipeline per-turn would add 15-30s. Recommend: meaning_units per-turn, themes/essence/memoir as session-level post-processing.

3. **Confidence scores need grounding:** Start without calibrated confidence (hardcode 0.5 as "model-generated, not validated") until reviewer feedback data exists.

4. **System prompt interaction:** `compose_system_prompt()` needs a `phenomenology_active` flag to prevent the LLM from fighting the question bank by reverting to default interviewer persona.

5. **Sizing estimate:** 3-4 focused sessions (larger than CLAIMS-01).

---

## Definition of Done

1. Lori can ask better lived-experience follow-ups in appropriate contexts
2. Extraction returns a clean `experience` block
3. Experience outputs are staged separately from factual truth
4. Existing factual extraction does not regress
5. Guard tests prove no fabrication on plain fact-only inputs
6. Final report includes explicit PASS/FAIL acceptance results
