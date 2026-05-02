# WO-EX-UTTERANCE-FRAME-01 — Narrator Utterance Frames (Story Clause Maps)

**Status:** ACTIVE — Phase 0-2 LANDED 2026-05-02 (builder + fixtures + tests + isolation gate + CLI + chat_ws observability log behind `HORNELORE_UTTERANCE_FRAME_LOG=1`, default-off). Consumer wiring (extractor binding, Lori grounding, validator) remains parked behind separate phases.
**Date:** 2026-05-02
**Lane:** Architectural / shared infrastructure. Consumed by the extractor (binding lane), Lori (behavior lane), AND the reflection validator. Belongs to the binding layer per Lorevox Extractor Architecture v1 §7.1.
**Sequencing:** Phase 0-2 ships independently of all consumer phases. Consumer wiring (Phase 3+) opens after BINDING-01 PATCH 1-4 evidence stabilizes (so we can compare frame-driven binding deltas against the same baseline that gates BINDING-01 default-on).
**Blocks:** Nothing.
**Lights up:** case_111 + case_112 (same-place dual-subject extraction), the BINDING-01 "Type C weakly-constrained narrative" failure class, AND BUG-LORI-REFLECTION-01's "concrete-noun grounding" need.

---

## Phase 0-2 landing summary (2026-05-02)

```
Files added:
  server/code/api/services/utterance_frame.py       — pure-deterministic builder
  tests/fixtures/utterance_frame_cases.json         — 20 hand-authored fixtures
  tests/test_utterance_frame.py                     — 16 unit tests (all green)
  tests/test_utterance_frame_isolation.py           — 4 build-gate tests (all green)
  scripts/utterance_frame_repl.py                   — CLI debug runner

Files modified:
  server/code/api/routers/chat_ws.py                — gated [utterance-frame] log
  .env.example                                      — HORNELORE_UTTERANCE_FRAME_LOG=0

Acceptance gates met:
  [x] Pure deterministic. No LLM. No DB. No IO. No NLP framework.
  [x] Imports only stdlib + lori_reflection._AFFECT_TOKENS_RX (zero new deps).
  [x] Build-gate isolation test enforces no extractor/Lori/safety/UI imports
      (mirrors test_story_preservation_isolation.py — both states verified
      via deliberate negative-test injection of `from ..routers import extract`).
  [x] 20/20 tests green. case_111 dual-subject motivating fixture passes.
  [x] CLI runner exercises --text / --file / stdin / --fixtures input modes.
  [x] chat_ws hook fires only when HORNELORE_UTTERANCE_FRAME_LOG=1 AND text
      is non-empty AND not a SYSTEM_* directive (mirrors story-trigger gate).
  [x] Build-gate failure on injected extract import returns clear error
      message naming the forbidden prefix (negative-test verified).
  [x] Frame-build failure in chat_ws is non-fatal (logs WARNING, turn
      continues unchanged) — pure observability discipline.

NOT done in Phase 0-2 (deliberate scope wall):
  [ ] Extractor binding consumes frame.candidate_fieldPaths     → Phase 3
  [ ] Lori reflection consumes frame.clauses[*] for grounding   → Phase 4
  [ ] Validator consumes frame.negation flags                   → Phase 5
  [ ] UI surface for operator inspection of recent frames       → Phase 6
  [ ] Generation-walking ("my mom's mother" → grandparent)      → LANGUAGE-CANON-01
  [ ] Multi-clause subject coreference                          → LANGUAGE-CANON-01

How to use the observability log:
  1. Operator sets HORNELORE_UTTERANCE_FRAME_LOG=1 in .env (or as a session
     env var before stack restart).
  2. Run a narrator session.
  3. After: `grep "\[utterance-frame\]" .runtime/logs/api.log` shows one
     line per turn carrying the parse summary + per-clause (subject_class /
     event_class / place / negation / uncertainty / candidate_fieldPaths).
  4. For per-utterance JSON dumps, `python3 scripts/utterance_frame_repl.py
     --text "..."` re-runs the same parser deterministically against any
     transcript you want to probe.

Phase 0-2 is the load-bearing groundwork. Phase 3+ consumer wiring is
where the extractor / Lori / validator start using the frame as their
binding signal — but those phases need their own evidence (BINDING-01
deltas, LORI golfball reruns, validator alt-credit numbers) before they
ship default-on.

---

## Mission

Define the lightweight semantic clause-level representation that sits between **raw narrator transcript** and **extractor / Lori / validator consumption**. Currently each consumer re-derives clause structure from scratch on every turn (extractor regex-matches against the whole answer; Lori reflects against the whole answer; validator overlaps tokens against the whole answer). This duplicates work, hides ambiguity, and is the root cause of failures like case_111/case_112 where compound dual-subject utterances are treated as a single binding decision.

A Narrator Utterance Frame is the answer to: *"What did this turn actually contain, broken into atomic semantic units, with each unit's binding target preserved?"*

## What it is, what it isn't

```
IS:
- A lightweight clause-level decomposition emitted ONCE per
  narrator turn, consumed by multiple downstream layers.
- Subject-aware (which clause is about whom).
- Concrete-noun preserving (the actual narrator words, not
  paraphrases).
- Field-target hinting (each clause carries a candidate
  fieldPath the extractor can use OR override).
- Negation- and uncertainty-aware (clauses carry a flag for
  "I don't remember" / "maybe" / "I think").

ISN'T:
- A grammar parser. We are not building a syntactic tree.
  No NP/VP, no government-and-binding, no dependency graph.
- An NLP framework dependency. No spaCy, no NLTK constituency
  parser, no transformer-based SRL. Native Python + small
  hand-tuned rules + the kinship canon already in tree.
- A truth-write source. The frame produces CANDIDATES, not
  truth. Extractor + projection layer + Phase G protected
  identity all retain final authority.
- A complete coverage tool. We classify what we can; we mark
  unknowns honestly. Coverage gaps are logged, not invented.
```

## The naming

**Primary term:** *Narrator Utterance Frame* (the architectural primitive — like Type A/B/C question typology).
**Operational synonym:** *Story Clause Map* (the output artifact — what gets logged + consumed downstream).

Both names refer to the same thing. Prefer "Narrator Utterance Frame" in code + spec; prefer "Story Clause Map" in operator-facing logs and documentation when we want the human-readable name.

## The motivating example (case_111)

Narrator says:

> "My dad was born in Stanley, and I was born in Stanley too."

Today's extractor sees this as one block, gets the place noun right, gets the second subject wrong:

```
parents.birthPlace = Stanley   ✓
parents.birthPlace = Stanley   ✗  (second clause mis-bound to parents)
                              MISSING: personal.placeOfBirth = Stanley
```

The frame splits it cleanly:

```
NarratorUtteranceFrame {
  raw_text: "My dad was born in Stanley, and I was born in Stanley too."
  clauses: [
    Clause {
      raw: "My dad was born in Stanley"
      who: "my dad"
      who_canonical: "father"            # via _KINSHIP_CANON
      who_subject_class: "parent"
      event: "was born"
      event_class: "birth"
      place: "Stanley"
      time: null
      object: null
      feeling: null
      negation: null
      uncertainty: null
      candidate_fieldPaths: ["parents.birthPlace"]
    },
    Clause {
      raw: "I was born in Stanley too"
      who: "I"
      who_canonical: "narrator"
      who_subject_class: "self"
      event: "was born"
      event_class: "birth"
      place: "Stanley"
      time: null
      object: null
      feeling: null
      negation: null
      uncertainty: null
      candidate_fieldPaths: ["personal.placeOfBirth"]
    }
  ]
  unbound_remainder: ""
  parse_confidence: "high"   # both clauses fully classified
}
```

The extractor's binding layer then has clause-aware candidates instead of inferring "two birthPlace claims" from a flat token stream. case_111 + case_112 pass not because the LLM got smarter but because the frame did the subject-split before the LLM was asked.

## Slots the frame captures

```
WHO              I, my dad, my mom, my brother, my wife, my daughter,
                 grandma, my brother Tom, our pastor, etc.

KINSHIP CANON    Resolved via _KINSHIP_CANON (already in tree from
                 BUG-LORI-REFLECTION-01). dad → father, etc.

SUBJECT CLASS    self / parent / sibling / spouse / child / grandparent
                 / great-grandparent / community-member / pet / unknown

EVENT / ACTION   was born, moved, worked, married, served, remembered,
                 lost, learned, met, started, finished, escaped, stayed

EVENT CLASS      birth / death / move / work / marriage / military /
                 education / faith / illness / loss / leisure / unknown

PLACE            Verbatim narrator string ("Stanley", "the aluminum
                 plant", "outside Spokane", "on the farm").

TIME             "when I was little", "in 1954", "during the war",
                 "after high school". Resolved to era_id when possible
                 (canonical 7-bucket spine).

OBJECT / SCENE   railroad tracks, kitchen table, uniform, hospital,
                 car, church. The concrete physical anchors that
                 make a memory specific.

FEELING          ONLY captured when the narrator used the word.
                 NEVER inferred. (Same rule as the existing
                 echo_contains_unstated_emotion check.)

NEGATION         "I don't remember", "we never", "no one ever".

UNCERTAINTY      "maybe", "I think", "I'm not sure", "it might
                 have been".

FIELD TARGETS    A list of candidate fieldPaths for the clause.
                 Empty list = "unbound; extractor or Lori may
                 still produce something but the frame had no
                 strong candidate."
```

## Three consumption surfaces

This is why the frame is its own WO and not folded into BINDING-01 or LANGUAGE-CANON-01:

### Surface A — Extractor (binding lane)

The extractor's BINDING-01 layer consumes the frame to bind each clause to the right fieldPath BEFORE the LLM extraction call. Same-place dual-subject, sibling-attribution, generation-walking, place-vs-residence — all of these become clause-level binding decisions instead of post-hoc filter rules.

Effectively replaces the Type C "weakly-constrained narrative" failure surface from Architecture Spec v1 §7.1 with a structural representation the extractor can reason over.

### Surface B — Lori (behavior lane)

The LORI_INTERVIEW_DISCIPLINE composer consumes the frame to know which concrete noun to echo. Today Lori has the raw narrator text and is told "echo a concrete noun the narrator said" — a hard ask under load. With the frame, Lori can be told *"echo `clauses[-1].place` or `clauses[-1].object`"* — explicit reference instead of judgment.

Lori also gets follow-up vocabulary from the frame's `event_class`. If `event_class == "work"`, Lori knows the topic-pool follow-ups for work apply. If `event_class == "birth"`, the birth follow-ups apply. This is what WO-LORI-LANGUAGE-CANON-01 Layer 3 (life-story topic canon) needs to operationalize.

### Surface C — Reflection validator

The validator consumes the frame to score grounding more accurately. Today it counts overlap between echo content tokens and user content tokens. With the frame, it can count `echo_concrete_nouns ⊆ frame.clauses[*].place ∪ object ∪ who_canonical` — semantic-unit overlap instead of bag-of-tokens overlap. Eliminates the "Lori echoed 'father' but validator didn't see it because narrator said 'dad'" class of false positives. (Currently fixed by the kinship canon, but the frame generalizes the pattern.)

## Design rules (locked)

```
1. ONE pass per turn.
   The frame is built ONCE in the chat-turn pipeline. All
   downstream consumers read the same frame. No re-parsing.

2. NEVER inventive.
   Every slot must trace to verbatim narrator text or a
   canonical mapping (kinship canon). Unknown stays unknown.
   Empty stays empty. The frame must NEVER fabricate slots.

3. CONCRETE-NOUN PRESERVING.
   The narrator's actual words are preserved alongside any
   canonical form. "Dad" canonicalizes to "father" but the
   raw "Dad" is also kept so Lori can echo it back verbatim.

4. NEGATION + UNCERTAINTY ARE FIRST-CLASS.
   "I don't remember Stanley" must NOT produce a Stanley
   place-claim with negation flag set; it must produce a
   negation-flagged clause that downstream consumers can
   honor (extractor: skip; Lori: don't push; validator:
   don't score grounding on negated content).

5. UNBOUND REMAINDER IS PRESERVED.
   When the parser can't classify part of the turn, that
   text goes in `unbound_remainder` honestly. The extractor +
   Lori + validator can still see it. We don't drop signal.

6. PARSE CONFIDENCE IS REPORTED.
   "high" = all clauses fully classified.
   "partial" = some slots filled, some unknown.
   "low" = parser fell back to whole-turn-as-one-clause.
   Downstream consumers MAY downgrade behavior on low
   confidence (e.g., extractor might skip aggressive binding
   when frame confidence is low).

7. NO FRAMEWORK DEPENDENCY.
   Native Python. Hand-tuned rules. Reuse the kinship canon
   already in tree. NO spaCy, NO NLTK constituency, NO
   transformer-based SRL. The frame is small, fast, and
   testable as deterministic Python.
```

## Phase plan

```
Phase 0 — corpus snapshot
  Pull 30-50 real narrator utterances from the canon-grounded
  corpus + parent-session transcripts. Hand-author the
  expected frame for each. This becomes the unit-test
  fixture for Phase 1.

Phase 1 — frame builder, deterministic
  Build server/code/api/services/utterance_frame.py.
  Pure Python + the existing kinship canon. Produces a
  NarratorUtteranceFrame for any input string. Unit-tested
  against Phase 0's hand-authored fixtures. NO consumer
  wiring yet.
  Risk: zero (no integration). Gate: Phase 0 fixtures pass.

Phase 2 — wire into chat_ws as observability only
  Build the frame on every chat turn. Log it via
  [utterance-frame] log marker. Don't consume yet.
  Gives operators a way to see what the parser produces in
  real sessions before any consumer changes behavior.
  Risk: low (read-only).

Phase 3 — validator consumer
  lori_reflection.py reads the frame for grounding overlap
  instead of bag-of-tokens. Smaller false-positive surface.
  Gate: golfball harness reflection failures drop further.

Phase 4 — extractor binding consumer
  BINDING-01 PATCH 5+ reads the frame for clause-level
  binding decisions. case_111 + case_112 should pass with
  the frame regardless of LLM behavior.
  Gate: master eval at tag r5h-utterance-frame ≥ baseline,
  case_111 + case_112 flip green.

Phase 5 — Lori composer consumer
  LORI_INTERVIEW_DISCIPLINE references frame slots in the
  prompt directly: "echo {frame.clauses[-1].place}".
  Gate: golfball harness echo_not_grounded → 0 across all
  non-trivial-response turns.
```

## Acceptance gates (per phase)

```
Phase 0 [ ] 30+ hand-authored utterance/frame pairs banked
        [ ] Coverage spans: identity, place, work, marriage,
            family, military, illness, loss, leisure
        [ ] Edge cases: compound clauses, negation, uncertainty,
            generation-walking ("my mom's mother"), STT noise

Phase 1 [ ] utterance_frame.py builds clean
        [ ] All Phase 0 fixtures pass
        [ ] Frame builder is pure (no IO, no LLM, no DB)
        [ ] Unit tests cover negation + uncertainty + low-
            confidence fallback paths

Phase 2 [ ] Frame logged on every chat turn behind
            HORNELORE_UTTERANCE_FRAME_LOG=1 (default off)
        [ ] No behavior change to any consumer
        [ ] Operator can pull a session's frames from api.log

Phase 3 [ ] lori_reflection.py uses frame.clauses[*].place +
            object + who_canonical for grounding overlap
        [ ] Golfball reflection failures drop ≥1 turn vs
            BUG-LORI-REFLECTION-01 baseline

Phase 4 [ ] BINDING-01 PATCH N consumes frame in pre-LLM bind
        [ ] case_111 + case_112 pass at r5h-utterance-frame
        [ ] Master eval ≥ r5h baseline (no regression)

Phase 5 [ ] LORI_INTERVIEW_DISCIPLINE references frame slots
        [ ] Golfball echo_not_grounded → 0 on non-trivial turns
        [ ] At least 1 parent narrator session live-tested
```

## Out of scope

- **Multi-turn frame stitching.** Each turn produces its own frame. Cross-turn coreference ("she" pointing back to a prior turn's "my mom") is a future WO if needed.
- **Discourse markers / pragmatic analysis.** "Anyway", "you know", "I mean" — these are STT/conversational filler. The frame ignores them. Not a meaning slot.
- **Sentiment / affect grading.** FEELING captures only narrator-stated affect words. No sentiment scoring. No affect classification beyond verbatim word capture. (Affect scoring lives in WO-AFFECT-ANCHOR-01 — separate lane, separate values clause.)
- **Auto-promotion of frame slots to truth.** Frame is candidates, not facts. Extractor projection + Phase G protected identity remain the truth-write authority.
- **Coreference resolution beyond simple kinship canon.** "Mom said grandma was sick" — the frame captures "Mom" + "grandma" as two WHO entries; it does NOT auto-promote "grandma" to "narrator's grandmother on mother's side." That's a generation-walking inference the extractor handles separately.
- **Cross-language support.** English only for v1. Translation/multilingual frames are out of scope.

## Sequencing relative to other lanes

```
BINDING-01 PATCH 1-4              (in tree, default-off, pending
                                   re-iteration evidence)
                                   ↓
WO-LORI-LANGUAGE-CANON-01         (parked — kinship canon shipped,
                                   life-story topic canon designed)
                                   ↓
WO-EX-UTTERANCE-FRAME-01          (this WO — shared representation
                                   layer that BOTH binding and canon
                                   consume; opens after BINDING-01
                                   evidence tells us which fields
                                   routinely cross-bind)
                                   ↓
WO-EX-UTTERANCE-FRAME-01 Phase 4  (binding consumer — case_111/112
                                   target, Type C surface fix)
                                   ↓
WO-LORI-LANGUAGE-CANON-01 Layer 3 (life-story topic canon — consumes
                                   frame's event_class for follow-up
                                   vocabulary)
```

## The product rule (echoes WO-LORI-LANGUAGE-CANON-01)

```
Schema    = what Lori CAN know.
Truth     = what Lori is allowed to TRUST.
Canon     = how Lori can RECOGNIZE narrator speech.
Frame     = how the system can REPRESENT narrator speech.
Behavior  = how Lori SPEAKS in response.

The frame helps everyone listen better.
The frame never invents.
```

## External grounding

The "always seek the particular" principle (Richards in Alshenqeeti 2014) is exactly what the frame operationalizes. Lori today has the rule but no reliable mechanism to hit it under load — she has to extract concrete nouns from raw text on every turn. The frame pre-computes those concrete nouns once so Lori, the validator, AND the extractor can all reference them. The same paper's warning about *"misperceptions on the part of the interviewer regarding what the interviewee is saying"* (Cohen et al's bias factors) is what the frame's concrete-noun preservation defends against — Lori cannot misperceive a slot that's a verbatim narrator word.
