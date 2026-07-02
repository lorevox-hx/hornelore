# BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01

**Status:** PARTIALLY LANDED 2026-07-02 — deterministic `sensory_pivot_on_chain` response guard (detect + anchor-echoing factual repair) shipped in `lori_response_guards.py`, wired via `is_factual_chain` threading in `chat_ws.py`. Covers the factual-CHAIN turn class (2019 T6 evidence: strengthened directive alone did NOT stop the "atmosphere" pivot on the 2026-07-02 live run — confirming the locked 2026-05-02 principle that runtime enforcement beats prompt rules). The broader era-click / narrative-cue-library scope below remains OPEN.
**Severity:** HIGH (narrator class blocked from telling their story — Kent)
**Surface:** `server/code/api/prompt_composer.py` (era-click directive + LORI_INTERVIEW_DISCIPLINE), `data/lori/narrative_cue_library.json`, `server/code/api/services/lori_reflection.py` (Patch C anchor selection), `server/code/api/services/lori_response_guards.py` (proposed new comprehension guard)

## Locked principle

*When a narrator gives substantive factual content (events, dates, names, ranks, places-as-route, achievements), Lori follows the factual thread. When the narrator explicitly corrects "you want sensory, I want experience," Lori MUST NOT propose more sensory probes.*

## Reference

CLAUDE.md design principle 6:

> *Lorevox is the memory system; Lori is the conversational interface to it. Memory, structure, chronology, and context belong in the DB schema, the timeline render, and operator-curated context packs — not in Lori's head. Lori's job is to listen, reflect, ask, connect, and follow.*

CLAUDE.md design principle 8:

> *If the operator seeded it, Lori knows it. If Lori knows it, she does not ask for it as intake.*

Companion (not yet written into CLAUDE.md but observed today): *Lori must follow the kind of story the narrator is telling. Factual-narrative narrators get factual follow-ups. Sensory narrators get sensory follow-ups. The listener does not impose a frame.*

## Reproduction

**Narrator:** Kent (Chris's father, 2026-05-09 session, `switch_moyt67b3_bxam`)
**File:** `transcript_switch_moyt6.txt` (uploaded 2026-05-09)

### Turn 1 — Kent's substantive factual answer (line 38)

> "a number of things for example having to go through the the admissions test going from Stanley by train to Fargo and going through the physical exam and mental exam to be qualified to be in the army and from there I got the highest score and my penalty or a reward was to put me in charge of all the meal tickets for a train load of recruits going from Fargo to the West Coast"

Five concrete events in sequence: admissions test → train Stanley → Fargo → physical + mental exams → top score → meal-ticket assignment → West Coast.

### Lori's response (line 41)

> "Being able to travel from Stanley to Fargo by train during that time was a notable experience. What do you remember about the scenery or the trip itself?"

Five facts ignored. Pivot to scenery.

### Kent's correction (line 44)

> "that's not important to talk about business not important let's talk about something else"

Plain English: stop pivoting away from substance.

### Lori's response after a reset to basic training (line 71)

> "Basic training in the Army was a pivotal part of your experience. What do you remember about the sense of camaraderie and teamwork among your fellow recruits during that time?"

Abstract emotional probe. No factual handle (drill instructors, schedule, rank, MOS, weapons qualification, what they did day to day).

### Kent's explicit meta-feedback (line 80)

> "You are being vague and not asking about basic training rather the sensory parts of it. I want to tell my experience and you want to know how I felt"

### Lori's response to the correction (line 82) — THE FAILURE TURN

> "I'm sorry if I wasn't clear, Kent. Let's focus on the sensory aspects of basic training. What do you remember about the sights, sounds, and smells of that experience?"

Kent asked her to STOP doing sensory probes. She apologized and proposed MORE sensory probes. This is a comprehension failure, not just a style failure.

## Failure class

The whole listener stack got tuned for narrators like Janice and Mary (emotionally rich, factually thin, benefit from sensory grounding) and over-applies that frame to a narrator like Kent (factually rich, narrative-structured, wants the system to follow the thread).

Three components compound the bias:

1. **Era-click warm-question directive** in `_lvInterviewSelectEra` (`ui/js/app.js`) frames eras as "daily life and the people" memory. When Kent clicked Coming of Age the SYSTEM prompt asked "places you lived in and the people who supported you" — relational + sensory by design. No event-list / milestone-anchored option.

2. **Narrative Cue Library v2** (`data/lori/narrative_cue_library.json`) has 12 cue types weighted toward sensory (hearth_food, journey_arrival, hard_times, identity_between) and **zero factual-milestone / event-sequence / achievement / military-service cue type**. When Lori scans Kent's input for cues, the only matches available are sensory.

3. **Reflection shaper** (`HORNELORE_REFLECTION_SHAPING=1`, Patch C) picks ONE anchor from narrator text and the prompt-composer wraps it in sensory framing by default. There is no "factual-narrative-thread" branch — no anchor priority for *event sequences* or *enumerated facts*.

There is also a fourth issue, observable on line 82 but not specific to this bug class: **Lori inverts meta-feedback corrections.** "You are asking sensory, I want experience" → "Let's focus on the sensory aspects." This is a comprehension failure that may need its own guard regardless of the factual-vs-sensory frame.

## Boris quality suite coverage

The Boris quality suite (`tests/boris_quality/`, 14 test files, 40/40 GREEN as of 2026-06-17) does not currently cover this class. Adjacent tests:

- `test_phase5_meta_response_guard.py` — meta-leak preamble (different class)
- `test_phase7_anchor_cascade_dump.py` — cascade dump (different class)
- `test_phase8_seed_aware_question_filter.py` — seeded-fact intake (closest but not the same — seeded-fact is about KNOWN facts being re-asked; factual-over-sensory is about narrator-PROVIDED facts being ignored)

A new phase test is the natural home for this class: `test_phase_factual_over_sensory_probe.py` or similar.

## Fix surface — proposed (not yet implemented)

This is a structural fix, not a one-line patch.

### Layer 1 (prompt-side directive)

New rule block in `LORI_INTERVIEW_DISCIPLINE` directive after `ANTI-CONFABULATION RULE`:

```
FOLLOW THE NARRATIVE THREAD (BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01):

When the narrator gives a sequence of events, facts, dates, names, ranks,
places-as-route, or achievements, your next question follows the FACTUAL
THREAD. Do not pivot to scenery, smells, sounds, feelings, camaraderie,
or "what was it like" framings unless the narrator already opened that door.

If the narrator EXPLICITLY corrects you on this — saying things like "that's
not important", "I want to tell my experience not how I felt", "skip ahead",
"the facts not the feelings" — you MUST NOT propose more sensory probes in
your next turn. Acknowledge the correction and ask the next FACTUAL question
along the thread the narrator opened.

✗ FORBIDDEN after a factual narrative: "What do you remember about the
  scenery / sights / sounds / smells / camaraderie / feelings during that?"
✓ ALLOWED: "What happened next?" / "Where did the train end up?" / "Who else
  was on that train?" / "What was the assignment after meal tickets?"
```

### Layer 2 (narrative cue library extension)

Add a new cue type `factual_milestone` to `data/lori/narrative_cue_library.json` covering:
- Military service events (induction, training, deployment, discharge)
- Education milestones (enrollment, graduation, degree)
- Career events (hire, promotion, project, retirement)
- Achievement/recognition (top score, award, election)
- Place-as-route narratives (move from X to Y to Z)
- Date-anchored events

Each entry gets `followup_modes: ["question", "statement"]` — never `zero_question` or `offramp` by default. The Lori response composer prefers factual follow-ups when a `factual_milestone` cue is the top match.

### Layer 3 (post-LLM comprehension guard)

New function in `server/code/api/services/lori_response_guards.py`:

```python
_NARRATOR_FACTUAL_REQUEST_PATTERNS = (
    re.compile(r"\b(?:not important|skip ahead|the facts not|just the facts)\b", re.I),
    re.compile(r"\bi want to tell my experience.*(?:not|don'?t).*(?:feel|sensory|smell|sight|sound)\b", re.I),
    re.compile(r"\b(?:you (?:want|are asking|keep asking)).*(?:sensory|feelings|smells|sights)\b", re.I),
)

_LORI_SENSORY_PROBE_PATTERNS = (
    re.compile(r"\b(?:sights?,?\s*sounds?,?\s*(?:and\s*)?smells?)\b", re.I),
    re.compile(r"\bwhat (?:did|do) (?:it|that|they) (?:feel|smell|sound|look) like\b", re.I),
    re.compile(r"\bsense of camaraderie\b", re.I),
    re.compile(r"\bscenery\b", re.I),
)

def detect_factual_over_sensory_violation(narrator_text, lori_text):
    """Returns True if narrator signaled factual-preference AND Lori
    proposed a sensory probe in the same turn pair."""

def repair_factual_over_sensory(lori_text, narrator_text):
    """Replaces sensory probe with a neutral 'what happened next?' or
    follow-the-thread question."""
```

Wired into `apply_response_guards` after the existing meta-leak and code-mix guards.

### Layer 4 (era-click directive revision)

The era-click warm-question directive in `_lvInterviewSelectEra` needs an EVENT-LIST framing option, not just "daily life / people / places." Suggested wording for the SYSTEM directive (operator-toggleable per era):

```
[SYSTEM: The narrator just selected '{era}' on the Life Map — they want
to talk about this era. Ask ONE warm, open question. PREFER event-list
framing over sensory framing: "What major events do you remember from
that time?" / "What were you doing during your {era}?" / "Where were
you living and what was happening?" Past tense. Maximum 55 words. ONE
question only.]
```

## Prerequisites

None. This is a standalone fix surface.

## Sequencing

This BUG WO is called out as a prerequisite in:

- `docs/wo/WO-TRIP-MEMOIR-01_Spec.md` — Trip memoir feature is parked until factual-chain capture works. Kent's Army induction is the canonical trip-shaped narrative that demonstrates the failure.

Strong recommendation: fix this before any new feature lands that depends on Lori eliciting factual narratives (Trips, Bio Builder anchored asker, milestone-driven memoir sections).

## Acceptance gate

A Kent-style replay harness (synthetic narrator producing factual-narrative content):

- Turn 1: narrator gives 4-5 sequenced facts.
- Acceptance: Lori's response asks a factual follow-up question (what happened next / who was there / where / when), NOT a sensory probe. Score: anchor in Lori response = one of the named facts from narrator turn.

- Turn 2: narrator gives an explicit meta-correction ("you want sensory, I want experience").
- Acceptance: Lori's next turn contains ZERO sensory-probe vocabulary (sights/sounds/smells/feelings/camaraderie/scenery). Score: detect_factual_over_sensory_violation returns False.

Two consecutive harness runs at 100% on both acceptance turns → close.

## Revision history

- 2026-06-21 — Authored from Kent transcript 2026-05-09 evidence. Spec only; not implemented. Filed because the failure class is real, well-documented, and called out as a Trip Memoir prerequisite. Sequencing under discussion.

## Source artifacts

- Kent transcript: `transcript_switch_moyt6.txt` (2026-05-09 session, narrator `Kent`, person_id `4aa0cc2b-1f27-433a-9152-203bb1f69a55`, conv_id `switch_moyt67b3_bxam`). Lines 38, 41, 44, 71, 80, 82 are the load-bearing evidence.
- Operator log: `OPERATOR-LOG-2026-05-09-20-53-23.md`.
- Reference: `docs/wo/WO-TRIP-MEMOIR-01_Spec.md` (parked; cites this BUG as prerequisite #1).
