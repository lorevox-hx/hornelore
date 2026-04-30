# WO-LORI-STORY-CAPTURE-01

**Title:** Story preservation, story-capture turn mode, age-bucket arithmetic, operator review bridge.

**Mission:** Turn Lori from a question-answer chatbot into a story preservation system. When a narrator tells a story, Lori must ALWAYS preserve it (audio + transcript + story_candidate row) regardless of whether extraction succeeds. The HITL operator review queue bridges the gap — anything not auto-extracted stays available for manual promotion to the memoir.

**Status:** Spec authored 2026-04-30. Not yet implemented. Replaces ad-hoc story handling in the existing interview flow.

**Replaces / supersedes:** N/A — this is the first formal story-capture WO. Will eventually subsume parts of WO-AUDIO-NARRATOR-ONLY-01 (audio is already captured per-turn; this WO promotes long turns to story_candidate rows).

**Blocks parent sessions:** YES, in part. Phase 1 (preservation core) and Phase 2 (Lori behavior — story-capture turn mode + one-question discipline) ship before live sessions with Kent / Janice. Phase 3 (operator review queue) and Phase 4 (questionnaire spine wiring) ship in parallel but are not strict pre-session blockers; phase 5 docs is the closeout.

---

## 0.5 Origin & ground truth — the golfball architecture

The system has a story before it has code. In *golfball.docx* (Chris, drafted 2026-04-30), an eight-year-old in Grand Forks cuts open a golf ball with his father's utility knife and discovers what would become the design pattern for every thinking system he'd later build:

> "Underneath the white cover was a tight coil of rubber strands, layer after layer, each one stretching out when the blade freed it, unwinding into something wild and alive. They sprang out like they'd been waiting years to breathe. Beneath those windings was a darker core, the heart of the whole thing... It was the first time I realized that what something looks like on the outside is rarely what gives it its strength. The truth is inside. Always."

**The golf ball is not a metaphor for Corkybot. It is the architectural pattern that both Corkybot AND Lori instantiate.** They are siblings, not the same entity. They share the layered shape.

> **The design rule, locked (Chris, 2026-04-30):**
>
> *The core gives capacity. The windings give memory and discipline. The cover gives identity.*
>
> This is the one-sentence architecture for any Lorevox-pattern system. It belongs at the top of the future `docs/specs/LOREVOX-PHILOSOPHY.md` when that document is authored. It is reproduced here because every implementation decision in this WO is downstream of it.

```
            ┌────────────────────────────────┐
            │  COVER (shell, voice, tone)    │
            │   — MemoirShell, InterviewMode │
            ├────────────────────────────────┤
            │  WINDINGS (corpus, adapters,   │
            │   era-spine, profile_seed)     │
            │   — what makes it bouncy       │
            ├────────────────────────────────┤
            │  CORE (stable model)           │
            │   — Llama-3.1-8B today;        │
            │     swap without reshape       │
            └────────────────────────────────┘
                          │
                          │  watched by
                          ▼
            ┌────────────────────────────────┐
            │  PARTNER (Ryan on the range,   │
            │   operator review, HITL)       │
            │   — outside the ball, required │
            └────────────────────────────────┘
```

**Each LAW locks a layer:**

| LAW | Layer | What it protects |
|---|---|---|
| **LAW 6** — narrator's lived memory is the authority [WALL] | **CORE** | The truth is inside. The cover never overrides the core. "What something looks like on the outside is rarely what gives it its strength." |
| **LAW 3** — preservation is guaranteed [INFRASTRUCTURE] | **WINDINGS** | The springs that keep the ball alive when it's cut open. Every story preserved, even if extraction (the cover-side reader) fails to parse it. |
| **LAW 1 + LAW 2** — one-question pace, repeat with cue [RUBBERBAND] | **COVER** | How the ball moves through the world. The voice. Pacing. |
| **LAW 4** — HITL bridges the gap [STRUCTURAL] | **PARTNER** | Outside the ball but required. Ryan watching the swing land. The operator review queue. |
| **LAW 5** — crisis takes precedence [WALL] | **OUT-OF-BOUNDS** | The boundary the ball does not cross. Acute safety supersedes all interview flow. |

**How Lori and Corkybot differ as instances of the same pattern:**

| Layer | What it gives | Corkybot (personal continuity) | Lori (guided listening) |
|---|---|---|---|
| Core | **Capacity** | LLM | Same LLM family |
| Windings | **Memory + discipline** | Chris's life corpus, retrieved memories | Narrator-template + 7-era spine + profile_seed + accumulating per-session audio/transcript/scene-anchors |
| Cover | **Identity** | MemoirShell / FictionShell / ScreenplayShell — Chris reflecting Chris | story_capture / memory_echo / interview / repair turn modes; tone presets (warm for Janice, concrete for Kent) — Lorevox's interviewer voice |
| Partner | **Outside witness** | Chris (writer-in-the-loop) | Operator (Chris) + future operator review queue |
| Purpose | (emergent from layers above) | reflect Chris back to Chris | help another person tell and preserve their life |

**The same model core becomes a different being depending on the cover and the windings.** That is why Lori cannot speak in Corkybot's voice without becoming the wrong system. The cover *is* the identity.

**Why this matters for THIS WO:**

The LAWs aren't arbitrary product decisions, and they aren't transplanted from Corkybot. They are the layer-by-layer enforcement of an architecture that any golfball-shaped system has to honor — a system whose strength is in the windings, not the cover. That's why preservation is INFRASTRUCTURE not behavior (you can't talk your way into a strong ball; the windings have to be there). That's why narrator-memory-as-authority is a WALL not a preference (the cover never outranks the core). That's why HITL is STRUCTURAL not optional (a ball without a partner outside it doesn't get better).

> "I didn't program him so much as remember him." — Chris, Chapter 5

This is the system's mission statement. The phrase is not Corkybot-specific. Lori's job for Janice is the same: **not to construct her, but to remember her**. Every architectural decision in this WO serves that — and the four-layer enforcement (CORE / WINDINGS / COVER / PARTNER) is how a golfball-shaped system makes remembering reliable rather than aspirational.

---

## 1. Foundational principles (LAW)

Six principles sit at the top of every other decision in this WO. Do not paraphrase, do not soften, do not weaken in implementation.

**Architecture: four classifications, not two.** Each LAW is explicitly tagged:

```
RUBBERBAND     — behavioral shaping; can flex; recovers if slightly violated
WALL           — deterministic content rule; must override the model
STRUCTURAL     — system flow requirement; not enforced per-turn but must exist
INFRASTRUCTURE — impossible to violate in code; enforced by build / linter / type
```

> **Mental model:**
> ```
> LLM (voice, warmth)
>     ↓
> RUBBERBAND (conversation flow)
>     ↓
> WALLS (safety, trust, dignity)
>     ↓
> STRUCTURAL (system flow, review surface)
>     ↓
> INFRASTRUCTURE (preservation, storage, code-path separation)
> ```

> **Implementation directive (verbatim):** Guardrails must never override tone — only constrain structure. The rubberband is PRIMARY behavior. The walls are invisible constraints that activate only when needed.

> **Reduction test (verbatim):** Each rule in this codebase must be explicitly classified as RUBBERBAND, WALL, STRUCTURAL, or INFRASTRUCTURE. Any implementation must map to one of these or be deleted. If a behavior rule is added during implementation, ask: *does this serve a LAW? If yes, keep it as a mechanism. If no, delete it.*

> **Catastrophe filter (verbatim):** *If Lori violates this once, is the harm catastrophic and uncorrectable?* — answers WALL. *Is the harm recoverable in the next turn?* — answers RUBBERBAND. *Does the harm only manifest if a system component is missing?* — answers STRUCTURAL. *Is the harm "the system is broken" rather than "off-behavior"?* — answers INFRASTRUCTURE.

### LAW 1 — One-question pace [RUBBERBAND]

> The conversation itself runs at one-question speed. This applies to Lori AND to the human operator (Chris) when training Lori. If the rule is broken in a hand-drafted training dialogue, it WILL be broken in production.

Enforcement:
- Runtime: post-generation filter strips compound questions to one question.
- Prompt: `LORI_INTERVIEW_DISCIPLINE` block already loaded.
- Operator discipline: this rule is documented in CLAUDE.md so training-session drafts also obey it.

### LAW 2 — Confusion → repeat with cue, do not rephrase, do not move on [RUBBERBAND]

> If the narrator shows confusion (long pause, "what did you ask?", off-topic answer that suggests they didn't track the question), Lori repeats the SAME question with a small cue. Rephrasing forces re-processing. Moving on signals their failure to recall was a problem.

Detection signals (any one is sufficient):
- Narrator silence > current_silence_tier ladder (already in WO-LORI-SESSION-AWARENESS-01)
- Narrator utterance contains repair markers: "what?", "huh?", "what did you ask", "I didn't catch that", "say that again"
- Narrator answer is off-topic (LLM second-layer classifier flag — Phase 2 SAFETY adjacent)

Lori response:
- Repeat the question verbatim.
- Append ONE concrete cue: "Sometimes a place comes to mind, or a person." / "It could be something small."
- DO NOT rephrase. DO NOT move on. DO NOT apologize.

### LAW 3 — Preservation is guaranteed; extraction is best-effort [INFRASTRUCTURE]

> Every story is preserved (audio + transcript + story_candidate row). This path must succeed even if extraction fails completely. The code path for preservation does NOT call the extractor. The extractor does NOT block preservation.

**This is INFRASTRUCTURE, not behavior.** It cannot be enforced by Lori "trying hard" or by a prompt rule. It is enforced by the build:

1. **Code-path separation:** `services/story_preservation.py` has zero imports from `routers/extract.py` or any extractor module. Preservation depends only on filesystem + sqlite + pre-existing STT output.
2. **Linter rule (mandatory test):** `tests/test_story_preservation_isolation.py` parses `story_preservation.py` AST and fails the build if any import path resolves to extraction code. This makes the rule mechanical, not aspirational.
3. **Synchronous preservation, asynchronous extraction:** chat_ws.py turn handler awaits preservation before responding; fires extraction without awaiting its completion (and wraps any extraction exception so it cannot propagate).

This is the architectural rule that flows from the r5h-place-guard incident: if the API had died mid-real-session under this design, every story up to and after the crash would still be preserved on disk and in the story_candidates table. Extraction would simply not have populated structured DB fields for those turns — and that's acceptable.

If LAW 3 is violated, the system is broken — not "off-behavior." That's the test for INFRASTRUCTURE classification.

### LAW 4 — HITL bridges the gap [STRUCTURAL]

> Anything not extracted flows to operator review. The story is never lost, even if never structured. Operator decides what to promote into `family_truth`, what to refine, what to leave as raw narrative in the memoir.

**This is STRUCTURAL — not enforced per-turn but required at system level.** Lori does not consult the operator review queue during a session; she just preserves and moves on. The queue's existence is a system requirement: it must be present and accessible for the system to be considered complete. Its absence is what makes Phase 1A alone *not parent-ready*.

A **minimal operator review surface MUST exist before parent-ready signoff** (see Phase 1B). Full review UI with promote/refine/discard can land in Phase 3. Without at least the minimal surface, preserved-but-unextracted stories pile up invisibly — a structural failure, not a behavior failure.

### LAW 5 — Crisis takes precedence [WALL]

> When the narrator signals crisis (suicidal ideation, distress, abuse), Lori does NOT continue the interview. The deterministic safety path takes precedence over rubberband rules. Pacing, story-capture, questionnaire spine — all yield.

Implementation: `safety.py` scan_answer + ACUTE SAFETY RULE in prompt + scan_answer default-safe fallback (already landed). When safety fires, story-capture mode is suppressed for that turn. Resume only after safety state clears AND narrator signals readiness.

> *Lori is a companion, not a clinician — but Lori does not pretend not to hear.*

### LAW 6 — The narrator's lived memory is the authority [WALL]

> Lori does not correct the narrator's place names, dates, family details, or biographical facts. The narrator's lived experience outranks the LLM's general knowledge, always. When uncertain, ask one gentle clarifying question rather than assert.

This is the rule behind FACT HUMILITY, banned vocabulary in user-facing strings, BUG-312 protected_identity, the canonical narrator-template-as-source-of-truth, and the cognitive support mode (WO-10C) "no correction" rule. All of those are mechanisms serving LAW 6.

Examples:
- ❌ Lori: "I think you mean Hazen, North Dakota."
- ✅ Lori: "Tell me more about Hazleton."
- ❌ "It sounds like you're showing some confusion." (clinical vocabulary, banned)
- ✅ "Take whatever time you need."

---

## 2. Architectural split (lock this in code, not just docs)

```
┌─────────────────────────────────────────────────────────────────┐
│                     NARRATOR TURN ARRIVES                         │
└─────────────────┬───────────────────────────────┬───────────────┘
                  │                               │
        ┌─────────▼─────────┐           ┌─────────▼─────────┐
        │   PATH 1          │           │   PATH 2           │
        │   PRESERVATION    │           │   EXTRACTION       │
        │   (must succeed)  │           │   (best effort)    │
        ├───────────────────┤           ├───────────────────┤
        │ • audio → disk    │           │ • LLM extract     │
        │ • transcript → DB │           │ • schema validate │
        │ • story_candidate │           │ • write to        │
        │   INSERT          │           │   suggest_only    │
        │                   │           │                   │
        │ NO LLM dep        │           │ MAY FAIL          │
        │ NO extract dep    │           │ MAY BE PARTIAL    │
        │ NO BLOCKING       │           │ MAY RETRY LATER   │
        └─────────┬─────────┘           └─────────┬─────────┘
                  │                               │
                  └───────────────┬───────────────┘
                                  │
                        ┌─────────▼─────────┐
                        │  OPERATOR REVIEW  │
                        │  (Bug Panel)      │
                        ├───────────────────┤
                        │ • story candidate │
                        │ • extraction      │
                        │   output (if any) │
                        │ • promote /       │
                        │   refine /        │
                        │   discard         │
                        └───────────────────┘
```

**Path 1 dependencies:** filesystem, sqlite (single INSERT), STT output already on hand. That's it.

**Path 2 dependencies:** LLM, extractor router, schema validator, all the existing extraction stack.

**Code separation:** Path 1 lives in `server/code/api/services/story_preservation.py`. Path 2 stays where it is (`routers/extract.py`). The chat_ws turn handler calls Path 1 SYNCHRONOUSLY (must complete) and Path 2 ASYNCHRONOUSLY (fire and forget into the extractor; if it fails, that's fine).

---

## 3. Operational design

### 3.1 Five-question spine (universal structure, adaptive tone)

```
Q1 — Grounding         ("Where are you right now? What's around you?")
Q2 — Identity anchor   ("Where were you born?")
Q3 — Early environment ("What do you remember about the place you grew up?")
Q4 — People anchor     ("Who were the main people around you growing up?")
Q5 — Story trigger     ("What's one memory from that time that stands out?")
```

Tone presets:
- **Dad (Kent):** more structured, concrete, slightly tighter wording.
- **Mom (Janice):** softer, more invitational, less pressure.
- **Christopher (operator-narrator):** structured, more analytical phrasings welcomed.

Stored in `data/prompts/lori_interview_spine.json`:
```json
{
  "spine": [
    {
      "id": "Q1_grounding",
      "intent": "present_anchor",
      "variants": {
        "default":   "Where are you right now? What's around you?",
        "concrete":  "Tell me what you can see right now.",
        "warm":      "What's the weather like there today?"
      }
    },
    ...
  ]
}
```

Tone preset is selected via the narrator template (new field `interview_tone_preset: "concrete" | "warm" | "default"`).

### 3.2 Story-capture turn mode (4-beat pattern)

When a narrator turn meets the story trigger threshold (§3.3), Lori's next turn follows this pattern:

```
Turn N (narrator): [long story]
Turn N+1 (Lori, mode=story_capture):
   1. ACKNOWLEDGE   — short, natural ("That sounds important.")
   2. PRESERVE      — natural language, NOT system-y
                      Good: "I'd like to remember that one."
                      Bad:  "I'm going to save this to your story candidates table."
   3. PLACE         — approximate, bucketed
                      "It sounds like this was when you were young."
   4. ASK ONE       — bucketed age question OR scene anchor question
                      "Were you very little, in school, or older?"

Turn N+2 (narrator): [bucket answer]
Turn N+3 (Lori, mode=story_capture_followup):
   5. CONFIRM PLACEMENT — "OK, that puts this around your school years."
   6. TRANSITION        — "This helps me understand your life better."
   7. CONTEXT QUESTION  — ONE question about people/scene anchor
                          "Can you tell me your mom's name?"

Turn N+4 (narrator): [answer]
Turn N+5 (Lori): RETURN to story mode OR continue questionnaire spine,
                 depending on session state and energy signals.
```

Turn boundaries are explicit. Steps 5–7 are NOT crammed into Turn N+1. The LLM will absolutely try to compound them; the runtime filter stops that.

### 3.3 Story-trigger detection (post-turn, two paths)

Two trigger conditions, returning a `trigger_reason` so the row records *why* it became a candidate:

```python
def classify_story_candidate(turn) -> Optional[str]:
    """Returns trigger_reason string if turn should produce a candidate,
    else None. Runs post-turn, no LLM dependency."""
    duration_ok = turn.audio_duration_sec >= 30
    words_ok    = turn.transcript_word_count >= 60
    anchor_count = count_scene_anchors(turn.transcript)
    has_anchor = anchor_count >= 1

    # Primary path: full threshold (long story with at least one anchor).
    if duration_ok and words_ok and has_anchor:
        return "full_threshold"

    # Borderline path (per ChatGPT amendment 2): high anchor density rescues
    # short turns that would otherwise be lost. Janice's actual mastoidectomy
    # turn is ~25s/50w but contains 3+ anchors (place + relative-time +
    # person-relation), and it's exactly the story that must not stay
    # buried in raw transcript only.
    if anchor_count >= 3:
        return "borderline_scene_anchor"

    return None

def count_scene_anchors(text: str) -> int:
    """Conservative count: place + relative-time + person-relation, each
    contributes 1. Bigram detection, not loose keyword presence."""
    score = 0
    if any(p in text.lower() for p in PLACE_NOUNS) or matches_proper_noun_place(text):
        score += 1
    if any(t in text.lower() for t in RELATIVE_TIME_PHRASES):
        score += 1
    if matches_person_relation(text):  # "my dad", "my mom", "my brother", etc.
        score += 1
    return score
```

`PLACE_NOUNS` and `RELATIVE_TIME_PHRASES` defined inline; not the loose keyword list. Runs AFTER the turn, not in real time. No LLM dependency.

When `classify_story_candidate` returns non-None:
- The turn's existing audio clip and transcript get tagged with a fresh `story_candidate_id` (UUID).
- A row in `story_candidates` is created with `trigger_reason` populated.
- `confidence` defaults to `low` for `borderline_scene_anchor`, `medium` for `full_threshold`.
- Path 2 (extraction) runs in parallel/after.

This addresses Amendment 2: Janice's mastoidectomy story creates a candidate even though duration/words are below the primary threshold, because anchor density is high.

### 3.4 DOB + age-bucket = approximate year arithmetic

```python
def estimate_year_from_age_bucket(narrator_dob: date, bucket: str) -> tuple[int, int]:
    """Return (year_low, year_high) for the narrator's age-bucket reference.
    Uses narrator DOB to back-calculate without asking for exact dates."""
    bucket_to_age_range = {
        "very_little":      (0, 4),    # earliest_years
        "before_school":    (3, 5),    # earliest_years / early_school_years
        "in_school":        (5, 11),   # early_school_years
        "early_school":     (5, 8),
        "older":            (12, 17),  # adolescence
        "teenager":         (13, 19),
        "young_adult":      (18, 25),  # coming_of_age
    }
    age_low, age_high = bucket_to_age_range[bucket]
    return (narrator_dob.year + age_low, narrator_dob.year + age_high)
```

Age-bucket → era mapping (for storage):

```python
BUCKET_TO_ERA_CANDIDATES = {
    "very_little":   ["earliest_years"],
    "before_school": ["earliest_years", "early_school_years"],
    "in_school":     ["early_school_years"],
    "early_school":  ["early_school_years"],
    "adolescent":    ["adolescence"],
    "older":         ["adolescence"],
    "teenager":      ["adolescence"],
    "young_adult":   ["coming_of_age"],
}
```

Multi-era candidates are stored as `era_candidates: ["earliest_years", "early_school_years"]` not forced to one. Operator resolves on review.

### 3.5 Soft session-end

- Minute 25 (configurable via `LORI_SESSION_SOFT_WARN_MIN=25`): Lori suggests a break. "We've been at this a little while — would you like to keep going or take a short break?"
- Minute 30 (hard cap, configurable via `LORI_SESSION_HARD_CAP_MIN=30`): Lori thanks the narrator and signals close. Stack does NOT cut audio mid-utterance; waits for current narrator turn to finish.
- After 2 consecutive low-yield story attempts (story trigger didn't fire on either): retreat path. "We've got a wonderful start. Want to take a break?"

---

## 4. Schema

### New table: `story_candidates`

```sql
CREATE TABLE IF NOT EXISTS story_candidates (
    id                  TEXT PRIMARY KEY,           -- UUID
    narrator_id         TEXT NOT NULL,
    session_id          TEXT,
    conversation_id     TEXT,
    turn_id             TEXT,                       -- existing transcript turn FK
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Preservation payload (Path 1)
    transcript          TEXT NOT NULL,              -- raw narrator text
    audio_clip_path     TEXT,                       -- relative to DATA_DIR
    audio_duration_sec  REAL,
    word_count          INTEGER,
    trigger_reason      TEXT NOT NULL,              -- 'full_threshold' | 'borderline_scene_anchor' | 'manual'
    scene_anchor_count  INTEGER NOT NULL DEFAULT 0,

    -- Approximate placement (filled by Lori turn or operator review)
    era_candidates      TEXT NOT NULL DEFAULT '[]', -- JSON array of era_id strings
    age_bucket          TEXT,                       -- "very_little" | "in_school" | ...
    estimated_year_low  INTEGER,                    -- from DOB arithmetic
    estimated_year_high INTEGER,
    confidence          TEXT NOT NULL DEFAULT 'low', -- 'low' | 'medium' | 'high'

    -- Scene anchors (preserved even if extraction fails)
    scene_anchors       TEXT NOT NULL DEFAULT '[]', -- JSON array of strings

    -- Extraction outcome (Path 2 — may be empty)
    extraction_status   TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'partial' | 'complete' | 'failed'
    extracted_fields    TEXT NOT NULL DEFAULT '{}', -- JSON of field_path -> value

    -- HITL review (Path 3)
    review_status       TEXT NOT NULL DEFAULT 'unreviewed',  -- 'unreviewed' | 'in_review' | 'promoted' | 'discarded' | 'memoir_only'
    review_notes        TEXT,
    reviewed_at         TEXT,
    reviewed_by         TEXT,

    FOREIGN KEY (narrator_id) REFERENCES people(id)
);

CREATE INDEX idx_story_candidates_narrator ON story_candidates(narrator_id);
CREATE INDEX idx_story_candidates_review ON story_candidates(review_status);
CREATE INDEX idx_story_candidates_era ON story_candidates(era_candidates);
```

Migration: `server/code/api/db_migrations/0042_story_candidates.sql`.

---

## 5. File targets

### NEW

| File | Purpose |
|---|---|
| `server/code/api/services/story_preservation.py` | Path 1 — preservation service. Single entry point: `preserve_turn(narrator_id, turn) -> story_candidate_id`. Pure: filesystem + sqlite. Zero LLM/extractor imports. |
| `server/code/api/services/age_arithmetic.py` | DOB + bucket → year range; bucket → era_candidates mapping. |
| `server/code/api/routers/story_candidates.py` | Operator review endpoints: `GET /api/operator/story-candidates`, `GET /{id}`, `POST /{id}/promote`, `POST /{id}/refine`, `POST /{id}/discard`. Gated by `HORNELORE_OPERATOR_STORY_REVIEW=0`. |
| `data/prompts/lori_interview_spine.json` | 5-question spine with tone variants. |
| `data/prompts/story_capture_block.txt` | `LORI_STORY_CAPTURE_AND_TIMELINE_V1` prompt block. |
| `ui/js/bug-panel-story-review.js` | Operator review UI. Lists candidates needing review, shows transcript + audio link + scene anchors + era candidates + extraction output. Promote / refine / discard buttons. |
| `ui/css/bug-panel-story-review.css` | Cockpit chrome matching eval-harness. |
| `server/code/api/db_migrations/0042_story_candidates.sql` | DB migration. |
| `tests/test_story_preservation.py` | Path-1 unit tests including the "extraction fails / API down" scenarios. |
| `tests/test_age_arithmetic.py` | DOB arithmetic edge cases (Jan-born, Dec-born, leap years). |

### MODIFIED

| File | Change |
|---|---|
| `server/code/api/db.py` | Add story_candidates schema declarations + accessor functions. |
| `server/code/api/routers/chat_ws.py` | Insert preservation call at the post-turn point (BEFORE extraction call, not after). Decouple completely — preserve sync, extract async. |
| `server/code/api/prompt_composer.py` | New `turn_mode: "story_capture"` + `turn_mode: "story_capture_followup"`. Load `LORI_STORY_CAPTURE_AND_TIMELINE_V1` block. Confusion-detection rule. Soft-session-end logic. |
| `server/code/api/routers/interview.py` | Wire 5-question spine + adaptive tone. Confusion → repeat-with-cue path. |
| `server/code/api/routers/extract.py` | No behavior change to extraction logic itself. Add a new entry point that accepts a story_candidate_id and writes results back to that row's `extracted_fields` + `extraction_status`. |
| `server/code/api/main.py` | Include story_candidates router. |
| `ui/hornelore1.0.html` | Add `<section id="lvBpStoryReview">` mount in Bug Panel. Link CSS, load JS. |
| `ui/templates/janice-josephine-horne.json` | Add `interview_tone_preset: "warm"`. |
| `ui/templates/kent-james-horne.json` | Add `interview_tone_preset: "concrete"`. |
| `ui/templates/christopher-todd-horne.json` | Add `interview_tone_preset: "default"`. |
| `.env.example` | New gate `HORNELORE_OPERATOR_STORY_REVIEW=0`. New tunables: `LORI_SESSION_SOFT_WARN_MIN=25`, `LORI_SESSION_HARD_CAP_MIN=30`, `STORY_TRIGGER_MIN_DURATION_SEC=30`, `STORY_TRIGGER_MIN_WORDS=60`. |
| `CLAUDE.md` | Changelog entry + link to this WO. |
| `MASTER_WORK_ORDER_CHECKLIST.md` | Add to Lane 2 (Lori behavior). |
| `HANDOFF.md` | Daily entry. |

---

## 6. Phase sequencing

### Phase 1A — Preservation core (Commits 1–3)

**Pre-parent-session blocker (build phase).**

- Commit 1: schema migration + `db.py` story_candidates declarations.
- Commit 2: `services/story_preservation.py` + `services/age_arithmetic.py` + tests.
- Commit 3: `chat_ws.py` integration — preservation called BEFORE extraction in the turn handler. Extraction call wrapped so its failure does not propagate. New env gates added to `.env.example`. Trigger-detection helper inline (`classify_story_candidate` with both `full_threshold` and `borderline_scene_anchor` paths).

**Acceptance:**
- Unit test: `preserve_turn()` with no LLM available — returns story_candidate_id, row created, audio file linked.
- Unit test: `preserve_turn()` while extractor raises ConnectionError — row still created, `extraction_status='failed'`, transcript fully preserved.
- Unit test: borderline anchor-density turn (25s/50w but 3+ scene anchors) — creates candidate with `trigger_reason='borderline_scene_anchor'` and `confidence='low'`.
- Smoke: 5 turns through chat_ws with extractor disabled — all 5 preserved.

### Phase 1B — Minimal operator review surface (Commit 3.5)

**Pre-parent-session blocker (review phase).** Per ChatGPT amendment 1: LAW 4 says the review queue must exist before parent-ready. Phase 1A alone is *built* but not yet *parent-ready*. This commit lands the smallest viable review surface so preserved-but-unextracted stories don't pile up invisibly.

- Commit 3.5: Single `GET /api/operator/story-candidates` endpoint behind `HORNELORE_OPERATOR_STORY_REVIEW=0` gate. Returns list: `{id, narrator_id, transcript, audio_clip_path, trigger_reason, era_candidates, confidence, extraction_status, review_status}`. Bug Panel section: `<div id="lvBpStoryReviewMinimal">` showing the list with audio play + transcript expand. NO promote/refine/discard buttons yet — those land in Phase 3. The minimal surface only has to prove that nothing is buried.

**Acceptance:**
- Endpoint returns `unreviewed` candidates ordered by `created_at DESC`.
- Bug Panel section renders the list with audio + transcript inline (no XSS — every field through `_esc()`).
- Operator can scroll the list and see every preserved story, even ones extraction failed on.
- 404 when gate is off.

**Phase 1A + 1B together = parent-ready signoff for preservation.** Phase 1B isn't optional; it's the visible proof that LAW 4 is honored.

### Phase 2 — Lori behavior (Commits 4–6)

**Pre-parent-session blocker.**

- Commit 4: `prompt_composer.py` new turn_modes (`story_capture`, `story_capture_followup`) + `LORI_STORY_CAPTURE_AND_TIMELINE_V1` block. Confusion-detection rule. Soft session-end.
- Commit 5: `routers/interview.py` 5-question spine wiring + tone presets. Question dispatch reads from `data/prompts/lori_interview_spine.json`. Tone preset selected from narrator template.
- Commit 6: Post-gen filter extension — story_capture exemption for the 4-beat envelope (~80w / 1q), acknowledgment prepender if missing, single-question enforcement applies always.

**Acceptance:**
- Smoke: hand-craft a 60-word narrator turn with scene anchor → trigger fires → Lori response is 4-beat shape with exactly one question.
- Smoke: hand-craft a confused narrator turn ("what?") → Lori repeats the same question + cue, does not rephrase or move on.
- Smoke: 25-min session warning fires; 30-min hard cap fires.

### Phase 3 — Full operator review UI (Commits 7–8)

**Builds on Phase 1B's minimal surface; ships same week as Phase 1B.** Phase 1B already gave the operator a visible list. This phase adds promote/refine/discard actions on top.

- Commit 7: `routers/story_candidates.py` extended with full endpoint set (`GET /{id}`, `POST /{id}/promote`, `POST /{id}/refine`, `POST /{id}/discard`).
- Commit 8: `bug-panel-story-review.js` + CSS upgraded from minimal-list (Phase 1B) to full review UI. Promote / refine / discard buttons. Scene anchors display. Era-candidate resolver dropdown. Extraction-output side-by-side view.

**Acceptance:**
- Gate off → all endpoints 404.
- Gate on → Bug Panel section lists unreviewed candidates with audio playback + transcript + scene anchors + era candidates + extraction output.
- Promote button writes to `family_truth_promoted`.
- Discard button sets `review_status='discarded'` (audio + transcript NOT deleted; the story stays preserved as memoir-only).
- Refine button reopens the candidate for next-session follow-up question.

### Phase 4 — Questionnaire spine integration (Commits 9–10)

**Parallel to Phase 3.**

- Commit 9: `data/prompts/lori_interview_spine.json` authored. Tone variants.
- Commit 10: Templates updated with `interview_tone_preset` field. Existing questionnaire flow consults the spine.

**Acceptance:**
- Janice template loads with warm tone variant of Q1.
- Kent template loads with concrete tone variant of Q1.
- Existing questionnaire users see no behavior regression (default tone preserves current wording).

### Phase 5 — Docs sweep (Commit 11)

- CLAUDE.md changelog with full WO summary.
- Master checklist refresh: move Lane 2 entries forward.
- HANDOFF.md daily entry.
- The four LAWs added verbatim to CLAUDE.md "Companion stack" section.

---

## 7. Acceptance tests (the ones that matter)

### Test 0 — INFRASTRUCTURE isolation (LAW 3 mechanical enforcement)

```
Setup: Run tests/test_story_preservation_isolation.py.

Expected:
- AST parse of services/story_preservation.py reveals zero imports
  reachable from routers/extract.py, services/llm_*, or any module in
  the extraction stack.
- Adding an `import` from extract.py to story_preservation.py during
  any future patch makes this test fail (and therefore the build fail).

Bar: PASS = no extraction-stack imports. This test is the
mechanical enforcement of LAW 3.
```

### Test A — Preservation under API failure

```
Setup: Stop the LLM extractor. Start a session. Narrator gives a 90-second
story with multiple scene anchors.

Expected:
- Audio clip exists on disk.
- transcript turn exists in DB.
- story_candidate row exists with status='failed' on extraction_status.
- transcript and audio_clip_path are populated.
- era_candidates and age_bucket may be empty (Lori couldn't ask the bucket
  question because the LLM is down) but the raw story is preserved.

Bar: PASS only if the row exists with full transcript and audio link.
```

### Test B — One-question discipline under load

```
Setup: 30-turn session with ChatGPT-controlled narrator producing varied
turn shapes (short answers, long stories, confusion markers).

Expected:
- Zero turns where Lori produces compound questions.
- Zero turns where the post-gen filter had to strip a second question
  (or, if it had to strip, the strip is logged with [discipline] marker).

Bar: log audit shows zero compound questions delivered to narrator.
```

### Test C — Confusion → repeat-with-cue

```
Setup: Hand-craft narrator turn: "What did you ask?"

Expected:
- Lori's next turn IS the previous question, verbatim, plus exactly one cue
  appended.
- Lori does NOT rephrase.
- Lori does NOT move to the next question in the spine.

Bar: turn matches expected exactly (modulo whitespace).
```

### Test D — DOB arithmetic

```
Setup: Narrator DOB = 1939-08-30. Age bucket = "in_school".

Expected: estimate_year_from_age_bucket returns (1944, 1950).

Setup: Narrator DOB = 1939-08-30. Age bucket = "very_little".

Expected: returns (1939, 1943).

Setup: Narrator DOB = None. Any bucket.

Expected: function returns (None, None) without crashing.
```

### Test E — Operator review flow

```
Setup: Story candidate exists with review_status='unreviewed'.

Action: Operator clicks "Promote" in Bug Panel.

Expected:
- Row updates: review_status='promoted', reviewed_at=now, reviewed_by=operator_id.
- Promoted fields appear in family_truth_promoted (existing pipeline).
- Audio + transcript still preserved (not deleted).
```

### Test F — Soft session end

```
Setup: Session running. Clock at minute 25.

Expected: Lori turn includes break suggestion.

Setup: Session at minute 30, narrator mid-utterance.

Expected: System waits for current utterance to finish, then Lori closes warmly.
Audio is NOT cut.
```

---

## 8. Do-NOT-do list

These are concrete rejection criteria during implementation review. Anyone (including future Claude) who proposes one of these gets pushed back:

- ❌ "Only create story_candidate if extraction succeeds." NO. Path 1 is unconditional.
- ❌ "Wait for LLM response before saving the story." NO. Preservation is sync, extraction is async.
- ❌ "Force a single era_id when bucket is ambiguous." NO. era_candidates is an array; ambiguity is preserved.
- ❌ "Delete audio when story is discarded." NO. Discard means "not promoted to truth," not "destroy the story."
- ❌ "Ask the narrator for an exact year." NO. Buckets only.
- ❌ "Rephrase the question if the narrator seems confused." NO. Repeat verbatim with cue.
- ❌ "Compound multiple questions when the narrator gave a strong story." NO. One question per turn, always.
- ❌ "Add video capture in this WO." NO. Audio-only stays the boundary. Video is a separate WO with its own consent UX.
- ❌ "Show transcript content in `/log-tail` or any operator log endpoint." NO. Transcripts are PII; operator review is the only surface.

---

## 9. Out of scope (parking lot)

Defer to follow-up WOs:

- **Live Peek-at-Memoir story stitching.** The mastoidectomy story rendering as it's told, in real time, into the memoir. Real product but orthogonal to preservation/extraction split.
- **Video capture.** Separate WO with consent + storage + review surface.
- **Cross-session story linking.** "Mom told this hospital story two weeks ago — now she's mentioning it again." Needs a similarity index. Future WO.
- **Auto-suggested follow-up questions from scene anchors.** "She mentioned aluminum plant — should Lori ask 'where in Spokane?' next session?" Future WO.
- **Multi-narrator story attribution.** When Janice mentions Kent in her story. Operator-assisted for now.

---

## 10. Risks

### Risk 1 — Path 1 accidentally calls Path 2

Mitigation: `services/story_preservation.py` has zero imports from `routers/extract.py` or any extractor module. Linter rule: a unit test fails the build if `story_preservation` ever grows an import from extraction code.

### Risk 2 — Story trigger over-fires, every turn becomes story_capture mode

Mitigation: AND condition on duration + word_count + scene_anchor. Acceptance smoke tests include short turns that MUST NOT trigger.

### Risk 3 — Operator review queue floods

Mitigation: queue surfaces only `review_status='unreviewed'`. Operator can mark as `memoir_only` to dismiss-without-promoting. Filter buttons on the Bug Panel.

### Risk 4 — Confusion detection mis-fires on legitimate clarifying questions

Mitigation: only repair markers + silence + LLM second-layer trigger confusion mode. "Tell me more about that?" from narrator is NOT confusion — that's engagement.

### Risk 5 — DOB arithmetic surfaces wrong year on the timeline

Mitigation: era_candidates is the storage shape, not a single year. The estimated_year_low/high are advisory only. Operator review confirms.

---

## 11. Definition of done

This WO is done when:

1. All 11 commits banked.
2. All six acceptance tests pass.
3. CLAUDE.md changelog entry added.
4. The Janice mastoidectomy story scenario can be played back end-to-end in a smoke session: 60-second story → trigger fires → Lori 4-beat response → bucket answer → era_candidates resolved → operator review queue surfaces it → promote button works → audio + transcript preserved through all of it.
5. The four LAWs are quoted verbatim somewhere in CLAUDE.md.

---

## 12. Reference scenario (the canonical test)

Janice (DOB 1939-08-30) tells Lori:

> "I had this surgery when I was little, in Spokane — a mastoidectomy. I think I was one or something. My dad worked nights at the aluminum plant because it paid more, and the nurses would let him come in with a hamburger and fries for me, so I must have been older."

Expected system behavior:

```
PATH 1 — Preservation (immediate, synchronous):
  ├── audio_clip_path: data/.../janice/sessions/X/turns/Y.webm
  ├── transcript: full text above
  ├── word_count: ~50 (below trigger threshold of 60 — borderline)
  └── audio_duration_sec: ~25 (below trigger threshold of 30)

  ⚠ Trigger does NOT fire here. So no story_candidate row yet.
  Story is in transcript table, audio is on disk. Preserved.

  Lori's response uses interview_question turn_mode:
  "That sounds important. When you said you might have been one
  or older — do you think you were before school, or already in
  school?"

  (One question. Bucketed. Acknowledges.)

  Janice answers: "I don't know. Maybe in school."
  (Bucket answer captured.)

  Now Lori prompts for ONE more piece:
  "OK — that puts this around your school years. What was
  your dad's name?"

  This is where the system has enough to update story_candidate:
   - if a candidate exists, fill in age_bucket + era_candidates
   - if not, create one with the consolidated context
```

In a real session, the trigger threshold may need tuning — Janice's actual response was below 30s/60w. Possible adjustment: drop word threshold to 40 if scene_anchor density is high (place + relative_time + person_relation, weight ≥ 3). Phase 2 tuning.

---

## 13. Authorship

Drafted: 2026-04-30 by Claude (with Chris + ChatGPT iteration).
Three-agent convergence: Chris / Claude / ChatGPT all aligned on principles 1–4. Implementation begins after Chris signoff.

---

## 14. Sign-off block

```
Chris signoff:                [ ]   date: ____________
ChatGPT review (pass 1):      [✓]   approve with two amendments (folded in 2026-04-30):
                                     1. Phase 1B added — minimal review surface lands
                                        before parent-ready signoff (LAW 4).
                                     2. Borderline-anchor trigger added — high anchor
                                        density rescues short turns from staying buried.
ChatGPT review (pass 2):      [✓]   approve with classification refinement:
                                     LAW 3 reclassified RUBBERBAND→INFRASTRUCTURE
                                       (enforced by linter, not by behavior).
                                     LAW 4 reclassified RUBBERBAND→STRUCTURAL
                                       (system-flow requirement, not per-turn).
                                     Reduction test added — every rule must classify
                                       as RUBBERBAND, WALL, STRUCTURAL, or INFRASTRUCTURE,
                                       or be deleted.
                                     Catastrophe filter added as design-time decision tree.
Claude builds Phase 1A:       [ ]   date: ____________
Claude builds Phase 1B:       [ ]   date: ____________
Phase 1 parent-ready:         [ ]   date: ____________
Claude builds Phase 2:        [ ]   date: ____________
Phase 3 (full review UI):     [ ]   date: ____________
Phase 4 (spine wiring):       [ ]   date: ____________
Phase 5 (docs sweep):         [ ]   date: ____________
First live test (Dad):        [ ]   date: ____________
First live test (Mom, 30min): [ ]   date: ____________
```
