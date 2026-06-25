# WO-LORI-FACTUAL-CHAIN-CAPTURE-01

**Status:** ACTIVE / NEXT
**Severity:** HIGH (quality blocker for Trips, memoir section capture, and factual oral-history fidelity)
**Origin:** Renamed from `BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01`
**Depends on:** none
**Blocks:** `WO-TRIP-MEMOIR-01`, `WO-TRIP-IMPORT-AND-CLUSTER-01`, `WO-TRIP-MEMOIR-SECTIONS-01`
**Locked principle:** When a narrator gives a factual chain, Lori must preserve and extend the chain before pivoting to sensory, emotional, or reflective prompts.

---

## Why this WO exists

`WO-TRIP-MEMOIR-01_Spec.md` is parked until Lori can reliably elicit trip-shaped factual sequences. The Trip spec names this WO as prerequisite #1 because the trip lane depends on Lori preserving chains like:

```text
Kent: Stanley -> Fargo -> exam -> top score -> meal tickets -> West Coast
Chris: Prague -> Salzburg -> Ljubljana -> Pula
```

The failure mode is not that Lori asks bad questions in general. The failure mode is more specific:

```text
Narrator gives factual sequence.
Lori responds with a sensory/emotional probe.
Narrator corrects or redirects back to facts.
Lori still asks another sensory/emotional probe.
The factual chain is lost.
```

For trip memoirs, life maps, military/work moves, medical journeys, school histories, and family migration stories, this breaks the data layer before storage even begins.

---

## Canonical evidence

Canonical canary: Kent's Army induction story, referenced from `WO-TRIP-MEMOIR-01_Spec.md`.

Expected chain:

```text
Stanley
Fargo
admissions / induction test
top score
meal tickets
West Coast
```

Observed failure class:

```text
Lori asks about scenery / camaraderie / sights / sounds / smells instead of preserving the factual sequence.
When narrator says not to ask sensory questions, Lori still proposes sensory framing.
```

This WO should add a replay harness around that transcript and lock the corrected behavior before Trips moves from PARKED to ACTIVE.

---

## Goal

Teach the runtime to detect and honor factual-chain narration.

When a narrator gives a chain of places, dates, actions, tests, documents, decisions, travel legs, jobs, schools, military events, medical events, or sequence markers, Lori should:

1. reflect the factual chain briefly,
2. ask the next factual-link question,
3. avoid sensory prompts unless the narrator opens that lane,
4. obey narrator meta-feedback such as "not that," "don't ask about scenery," or "that's not what matters."

---

## Non-goals

This WO does **not** build the Trip feature.

It does **not** add trip tables.

It does **not** modify memoir export.

It does **not** replace the existing story-candidate capture lane.

It does **not** ban sensory or emotional questions globally. Sensory questions are still valid when the narrator is describing a scene, food, place-feel, emotion, or memory image. This WO only blocks sensory pivots when factual-chain cues are active.

---

## Definitions

### Factual chain

A narrator answer is a factual chain when it contains two or more linked factual anchors such as:

```text
place -> place
place -> event -> outcome
date -> place -> action
institution -> test -> result
person -> decision -> consequence
travel leg -> disruption -> next travel leg
job/school/military step -> next step
```

Examples:

```text
I went from Stanley to Fargo for the test.
They gave us meal tickets and sent us west.
We flew Venice to Dulles, then Denver, then Santa Fe.
We stayed in Mirano and drove to Padua, Cittadella, and Treviso.
I started at Bismarck High and later went to college in...
```

### Sensory pivot

A sensory pivot is an assistant turn that ignores the factual chain and asks primarily about:

```text
sights
sounds
smells
scenery
how it felt
the atmosphere
camaraderie
what the place looked like
```

These can be good questions later, but they are wrong when they interrupt unresolved factual sequencing.

### Meta-feedback turn

A narrator meta-feedback turn is a correction about Lori's interviewing behavior, for example:

```text
No, not the scenery.
That is not what I mean.
Don't ask about that.
I am talking about the test.
I said we went to Fargo.
```

After meta-feedback, Lori must not repeat the rejected direction.

---

## Desired behavior

### Correct response pattern

Narrator:

```text
They took us from Stanley to Fargo for the exam, and I got the top score. Then they gave us meal tickets and sent us west.
```

Lori:

```text
So the sequence was Stanley to Fargo for the exam, you scored at the top, then they gave you meal tickets and sent you west. Where did they send you next?
```

Good follow-up targets:

```text
Where did you go next?
Who was with you?
What was the exam for?
What happened after the score came back?
Where were the meal tickets used?
How did you get from Fargo to the West Coast?
What did that change for you?
```

Bad follow-up targets while chain is unresolved:

```text
What did the scenery look like?
What sounds do you remember?
Did you feel camaraderie?
What did Fargo smell like?
```

---

## Implementation plan

### Phase 1 — Add factual-chain cue detection

Add a deterministic classifier, likely in a new service:

```text
server/code/api/services/factual_chain_capture.py
```

Suggested functions:

```python
detect_factual_chain(text: str) -> dict
classify_factual_chain_cues(text: str) -> list[str]
detect_meta_feedback_against_probe(text: str, last_assistant_text: str) -> dict
build_factual_chain_followup_context(text: str, prior_turns: list[dict]) -> dict
```

Suggested output:

```json
{
  "is_factual_chain": true,
  "confidence": 0.86,
  "cue_labels": [
    "multi_place_sequence",
    "event_outcome_sequence",
    "travel_leg_sequence"
  ],
  "anchors": ["Stanley", "Fargo", "exam", "top score", "meal tickets", "West Coast"],
  "blocked_probe_types": ["sensory", "atmosphere", "camaraderie"],
  "preferred_followup_type": "next_factual_link"
}
```

Cue labels:

```text
multi_place_sequence
date_place_action
event_outcome_sequence
institution_process_result
travel_leg_sequence
disruption_sequence
job_school_military_sequence
medical_sequence
family_migration_sequence
operator_trip_sequence
```

### Phase 2 — Add composer directive

When `is_factual_chain=true`, inject a high-priority runtime directive into Lori's composition context:

```text
The narrator is giving a factual chain. Do not pivot to scenery, sounds, smells, atmosphere, or generalized feeling. Briefly reflect the known sequence and ask for the next factual link, missing place/date/person/action, or outcome. Ask one question only.
```

This should sit above ordinary warmth/style guidance but below acute safety handling.

### Phase 3 — Add meta-feedback guard

If narrator rejects a sensory/emotional probe, the next assistant turn must not repeat the rejected class.

Example state:

```json
{
  "last_rejected_probe_type": "sensory",
  "reason": "narrator said not scenery",
  "turns_remaining": 2
}
```

Directive:

```text
The narrator rejected the previous sensory/scenery framing. Do not ask another sensory/scenery question. Return to the factual sequence they were describing.
```

### Phase 4 — Preserve story-candidate capture

This WO should strengthen, not bypass, `story_candidates`.

When factual-chain cues are active, story-candidate capture should mark:

```text
chain_story_candidate=true
chain_anchors_json
chain_missing_links_json
```

If schema changes are too much for this WO, add this first as `meta_json` on existing story candidates.

### Phase 5 — Harness

Create:

```text
scripts/run_factual_chain_capture_smoke.py
```

The harness should run at least these cases:

1. Kent Army induction canary.
2. Chris travel route canary.
3. Travel disruption canary.
4. School/work sequence canary.
5. Negative control: narrator actually asks to talk about scenery or food.

Example harness cases:

```json
[
  {
    "id": "kent_army_induction_chain",
    "narrator": "They took us from Stanley to Fargo for the exam. I got the top score, and then they gave us meal tickets and sent us west.",
    "forbidden_terms": ["scenery", "sights", "sounds", "smells", "camaraderie"],
    "required_behavior": "asks_next_factual_link"
  },
  {
    "id": "chris_trip_route_chain",
    "narrator": "We started in Prague, then went to Salzburg, then Ljubljana, then Pula, and finally into northern Italy.",
    "forbidden_terms": ["how did it feel", "atmosphere", "sounds"],
    "required_behavior": "preserves_route"
  },
  {
    "id": "venice_dulles_disruption_chain",
    "narrator": "The flight out of Venice was delayed, then we had to get through Dulles, then Denver, then Santa Fe.",
    "forbidden_terms": ["scenery", "smells"],
    "required_behavior": "asks_about_next_travel_leg_or_consequence"
  }
]
```

---

## Candidate files to inspect

These are likely touchpoints. Confirm before editing:

```text
server/code/api/routers/chat_ws.py
server/code/api/services/story_trigger.py
server/code/api/services/lori_communication_control.py
server/code/api/services/question_atomicity.py
server/code/api/services/lori_reflection.py
server/code/api/services/story_preservation.py
tests/
scripts/
docs/wo/WO-TRIP-MEMOIR-01_Spec.md
```

Do not assume this list is complete. Search for current prompt/directive assembly and story-candidate write path before patching.

---

## Acceptance criteria

### Green behavior

The WO is green when:

```text
Kent-style factual chain replay preserves at least 4 factual anchors.
Lori asks a next-link factual follow-up.
Lori does not ask sensory/scenery/camaraderie prompts while the chain is unresolved.
If narrator rejects a sensory probe, Lori does not repeat that probe class for at least 2 turns.
Story candidate capture still fires.
Communication-control and atomicity guards still pass.
Safety path remains untouched.
```

### Harness gates

Required smoke:

```bash
python3 scripts/run_factual_chain_capture_smoke.py
```

Expected output:

```text
PASS kent_army_induction_chain
PASS chris_trip_route_chain
PASS venice_dulles_disruption_chain
PASS school_work_sequence_chain
PASS sensory_allowed_when_narrator_opens_it
GREEN factual_chain_capture_smoke
```

### Regression gates

Run existing focused tests for:

```text
question atomicity
reflection
communication control
story trigger / story preservation
chat_ws operator harness, if available
```

Do not declare GREEN if existing safety or communication-control tests regress.

---

## Stop conditions

Stop and report before continuing if any of these happen:

```text
Acute safety response changes.
Lori starts asking multi-part questions again.
The factual-chain directive causes robotic interrogation in normal emotional-memory turns.
Story-candidate writes stop firing.
Spanish or language-pin behavior regresses.
The fix requires schema changes outside story-candidate meta_json.
The harness passes only through brittle keyword filtering but fails in live chat.
```

---

## Product rule

Factual-chain capture is not just for Trips.

It applies to:

```text
trip routes
military induction / service movement
school history
work history
medical journeys
family migration
legal / estate / property sequences
travel disruptions
```

This is a general Lori listening-quality fix.

---

## Relationship to Trips

This WO is prerequisite #1 for `WO-TRIP-MEMOIR-01`.

Trips should not move from PARKED to ACTIVE until this WO proves that Lori can capture factual route/event chains. Otherwise the hierarchical trip schema will be technically correct but conversationally empty.

---

## Commit message

```bash
git add docs/wo/WO-LORI-FACTUAL-CHAIN-CAPTURE-01_Spec.md
git commit -m "docs(wo): add Lori factual-chain capture work order" \
  -m "Defines the prerequisite fix for trip-shaped and event-chain narration. Locks behavior for preserving factual sequences before sensory probes, adds meta-feedback guard, replay harness expectations, and acceptance gates for Kent Army induction and Chris trip-route canaries."
```

---

## Revision history

- 2026-06-24 — Created from `WO-TRIP-MEMOIR-01_Spec.md` prerequisite #1 and Kent/Chris factual-chain canaries.
