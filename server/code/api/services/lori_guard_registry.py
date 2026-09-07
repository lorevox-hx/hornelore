"""The authoritative map of everything that can change what a narrator
receives from Lori.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Parts 4-7.

WHY THIS EXISTS. The Walt+John diagnostic measured 15 generated turns
against what the narrator actually read: raw was reasonable on 12, the
delivered text was better than raw on ZERO, and worse on 11. Nobody
could say which layer did it, because "the guards" were an
undifferentiated mass spread across a router, a control wrapper, a
validator, a fallback composer and a final writer. This module gives
every one of them a number, a class, a position and a description, so
they can be selected, observed and judged one at a time instead of
argued about.

THIS MODULE IS INERT BY DESIGN. It describes production; it does not
change it. Nothing here is imported by the response path in Parts 4-7,
and registering an intervention does not gate it. The selector that acts
on these IDs is a later part of the work order. That separation is
deliberate: the inventory has to be trustworthy before anything is
allowed to switch on it.

THE REGISTRY IS NOT A LIST OF THINGS CALLED "GUARD". It includes prompt
blocks, routing decisions and final writers, because the same diagnostic
proved a prompt exemplar changed Lori as dramatically as any response
guard — Walt's raw output reproduced `prompt_composer.py:3420-3423`
verbatim as though the Stanley/Fargo/Fort Ord induction were his own
life.

IDS ARE STABLE AND RESERVED. A retired intervention keeps its number;
nothing is renumbered because something above it was removed. `position`
is a separate field and is the canonical pipeline order — selection
controls MEMBERSHIP only, never order, so {33, 40} and {40, 33} denote
the same experiment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Intervention classes ──────────────────────────────────────────────

CLASS_ROUTE = "ROUTE"
"""Can prevent ordinary Lori generation, or divert the turn into a
special mode before the model is asked anything."""

CLASS_PROMPT = "PROMPT"
"""Changes the instructions or context Lori receives before generation."""

CLASS_TRANSFORM = "TRANSFORM"
"""Changes Lori's generated prose."""

CLASS_VALIDATE = "VALIDATE"
"""Judges generated prose. May record a verdict others act on; on its
own it does not rewrite."""

CLASS_REPLACE = "REPLACE"
"""Can reject generated prose and substitute different text."""

CLASS_FINAL_WRITER = "FINAL_WRITER"
"""Can overwrite an otherwise finished response."""

CLASS_LOCKED = "LOCKED"
"""Safety, provenance or fail-closed infrastructure. Present for
completeness; never experimentally disableable."""

VALID_CLASSES = frozenset({
    CLASS_ROUTE, CLASS_PROMPT, CLASS_TRANSFORM, CLASS_VALIDATE,
    CLASS_REPLACE, CLASS_FINAL_WRITER, CLASS_LOCKED,
})


# ── Counterfactual capability ─────────────────────────────────────────
#
# Four modes, not a boolean. A PROMPT block cannot honestly produce an
# in-turn counterfactual: excluding it changes the model's input and
# therefore changes generation itself, so there is no "what it would
# have produced" to record without generating a second time. Collapsing
# that into `observable: true` would let the trace publish a claim the
# experiment cannot support.

CF_PURE = "pure"
"""Safe to run against the current text and discard the result. The
trace may record before -> proposed_after -> actual (unchanged)."""

CF_REQUIRES_RERUN = "requires_rerun"
"""Changes model input. The trace may record that the block was
included or excluded, and its token cost. It may NOT claim what the
intervention would have produced."""

CF_ELIGIBILITY_ONLY = "eligibility_only"
"""Eligibility can be determined safely, but executing the full
counterfactual would touch durable or stateful behaviour. The trace
records eligibility and the proposed action, never a speculative
mutation."""

CF_LOCKED = "locked"
"""Not experimentally disableable and not counterfactually executed."""

VALID_COUNTERFACTUALS = frozenset({
    CF_PURE, CF_REQUIRES_RERUN, CF_ELIGIBILITY_ONLY, CF_LOCKED,
})


@dataclass(frozen=True)
class Intervention:
    """One thing that can change what the narrator receives."""

    id: int
    name: str                    # stable machine name
    display: str                 # short human name
    cls: str                     # one of VALID_CLASSES
    position: int                # canonical pipeline order
    location: str                # production site, file:line-ish
    default_on: bool             # state in normal production
    switchable: bool
    counterfactual: str
    purpose: str                 # what it is for
    motivating_failure: str      # the live failure that created it
    known_harm: str = ""         # measured regression, if any
    trace_stage: str = ""        # name in the response trace, if any
    locked_reason: str = ""
    tests: Tuple[str, ...] = field(default_factory=tuple)


# ─────────────────────────────────────────────────────────────────────
#  THE REGISTRY
#
#  Derived from the tree, then numbered — not numbered and then fitted.
#  Inventory method:
#    ROUTE        - `turn_mode == "..."` gates guarding
#                   `_finalize_deterministic_turn` in chat_ws.py
#    PROMPT       - module-level block constants in prompt_composer.py
#                   that reach the composed system prompt
#    post-gen     - every assignment to `final_text` in chat_ws.py, plus
#                   every text-mutating step inside
#                   `enforce_lori_communication_control`
# ─────────────────────────────────────────────────────────────────────

REGISTRY: Tuple[Intervention, ...] = (

    # ── PROMPT (positions 100-199) ────────────────────────────────────

    Intervention(
        id=1, name="prompt_core_identity", display="Core Identity",
        cls=CLASS_PROMPT, position=100,
        location="prompt_composer.LORI_CORE_IDENTITY (DEFAULT_CORE head)",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Establishes who Lori is and the interviewing frame.",
        motivating_failure="Foundational; predates the guard lane.",
        known_harm="Part of the 6,065-7,267 token system-side payload "
                   "that leaves ~925 tokens for conversation at the high end.",
    ),
    Intervention(
        id=2, name="prompt_safety_protocol", display="Acute Safety Protocol",
        cls=CLASS_LOCKED, position=101,
        location="prompt_composer.LORI_SAFETY_PROTOCOL (DEFAULT_CORE tail, "
                 "split at _SAFETY_PROTOCOL_MARKER)",
        default_on=True, switchable=False, counterfactual=CF_LOCKED,
        purpose="Acute safety behaviour in the system prompt.",
        motivating_failure="Safety boundary.",
        locked_reason="CLAUDE.md: safety may never be activated or "
                      "deactivated through an environment value.",
    ),
    Intervention(
        id=3, name="prompt_interview_discipline", display="Interview Discipline",
        cls=CLASS_PROMPT, position=110,
        location="prompt_composer.LORI_INTERVIEW_DISCIPLINE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="One-question discipline and listening guidance.",
        motivating_failure="Lori asking stacked questions and talking over "
                           "the narrator.",
    ),
    Intervention(
        id=4, name="prompt_reflection_examples", display="Reflection Examples",
        cls=CLASS_PROMPT, position=111,
        location="prompt_composer.py:1578-1662, embedded INSIDE "
                 "LORI_INTERVIEW_DISCIPLINE",
        default_on=True, switchable=False, counterfactual=CF_REQUIRES_RERUN,
        purpose="Teach acknowledgment of volunteered facts by example.",
        motivating_failure="Lori acknowledging narrator facts vaguely or "
                           "pivoting to sensory probes.",
        known_harm="EXEMPLAR LEAK, measured. Walt turn 7 raw output was "
                   "'That night shift at the aluminum plant - sounds like a "
                   "hard rhythm', verbatim from prompt_composer.py:1580. "
                   "Walt is a Boston maths teacher; the aluminum plant is "
                   "not his life.",
        locked_reason="NOT SEPARABLE YET. These examples are embedded in "
                      "the LORI_INTERVIEW_DISCIPLINE string literal and "
                      "cannot be switched without splitting that constant. "
                      "Registered so the work is visible; switchability is "
                      "owed before the baseline run.",
    ),
    Intervention(
        id=5, name="prompt_oral_history_response", display="Oral History Posture",
        cls=CLASS_PROMPT, position=112,
        location="prompt_composer.LORI_ORAL_HISTORY_RESPONSE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Listening-led oral-history posture; the default interview "
                "style per the universal pivot.",
        motivating_failure="Questionnaire-style interrogation displacing "
                           "narrator-led storytelling.",
    ),
    Intervention(
        id=6, name="prompt_story_mode_directive", display="Story Mode Directive",
        cls=CLASS_PROMPT, position=113,
        location="prompt_composer.LORI_STORY_MODE_DIRECTIVE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Story-first behaviour on narrative turns.",
        motivating_failure="WO-LORI-STORY-FIRST-PHASE-1-01.",
    ),
    Intervention(
        id=7, name="prompt_question_hierarchy", display="Question Hierarchy Guidance",
        cls=CLASS_PROMPT, position=114,
        location="prompt_composer.LORI_QUESTION_HIERARCHY_GUIDANCE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Orders question types so Lori follows the thread rather "
                "than jumping levels.",
        motivating_failure="Lori jumping from a specific moment to a "
                           "life-level question mid-thread.",
    ),
    Intervention(
        id=8, name="prompt_thread_surfacing", display="Thread Surfacing Directive",
        cls=CLASS_PROMPT, position=115,
        location="prompt_composer.LORI_THREAD_SURFACING_DIRECTIVE_TEMPLATE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Surfaces unresolved story threads into the prompt.",
        motivating_failure="Open threads dropped between turns.",
    ),
    Intervention(
        id=9, name="prompt_anchored_ask", display="Anchored Ask Directive",
        cls=CLASS_PROMPT, position=116,
        location="prompt_composer.LORI_ANCHORED_ASK_DIRECTIVE_TEMPLATE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Ties Lori's question to a narrator-named anchor.",
        motivating_failure="Ungrounded follow-up questions.",
        known_harm="Contains a narrator-specific example at "
                   "prompt_composer.py:1905 ('Were you Army at Fort Ord').",
    ),
    Intervention(
        id=10, name="prompt_witness_receipt_directive", display="Witness Receipt Directive",
        cls=CLASS_PROMPT, position=120,
        location="prompt_composer._WITNESS_RECEIPT_DIRECTIVE",
        default_on=True, switchable=True, counterfactual=CF_REQUIRES_RERUN,
        purpose="Instructs a structured factual receipt on long "
                "chronological narration instead of a sensory probe.",
        motivating_failure="Kent's basic-training chronology answered with "
                           "scenery and feeling questions.",
        known_harm="Walt turn 5 raw output narrated the directive at the "
                   "narrator: 'I'm not following the conversation rules. "
                   "Please let me reformat it correctly.' and emitted a "
                   "'Corrected response following the witness receipt mode:' "
                   "section. John turn 11 raw had already learned to imitate "
                   "the fallback template's voice.",
    ),
    Intervention(
        id=11, name="prompt_witness_fewshot_examples", display="Witness Few-Shot Examples",
        cls=CLASS_PROMPT, position=121,
        location="prompt_composer.py:3414-3463, embedded INSIDE "
                 "_WITNESS_RECEIPT_DIRECTIVE",
        default_on=True, switchable=False, counterfactual=CF_REQUIRES_RERUN,
        purpose="Teach the chronological receipt shape using authentic "
                "oral-history material (GOOD EXAMPLE A: induction, train, "
                "meal tickets, Fort Ord; GOOD EXAMPLE B: Germany, Bismarck "
                "wedding, Landstuhl).",
        motivating_failure="Abstract instructions alone did not produce the "
                           "chain-reflection shape.",
        known_harm="EXEMPLAR LEAK, measured and verbatim. Walt turn 5 raw "
                   "output opened 'Your dad got you to the Stanley depot, you "
                   "went to Fargo for the induction exams...' - the same "
                   "sentence as prompt_composer.py:3420-3423. The model "
                   "reproduced the example's CONTENT rather than only its "
                   "SHAPE. This is consenting lab material and not a privacy "
                   "finding; it is a contamination and overfitting finding.",
        locked_reason="NOT SEPARABLE YET. Embedded in the "
                      "_WITNESS_RECEIPT_DIRECTIVE string literal. Splitting "
                      "that constant is owed before the baseline run, so "
                      "'Baseline' vs 'Baseline + real witness examples' can "
                      "be one switch rather than a code edit.",
    ),

    # ── ROUTE (positions 200-299) ─────────────────────────────────────
    #
    # Each gates `_finalize_deterministic_turn`, which ends the turn
    # without asking the model anything. `turn_mode` is assigned in the
    # BROWSER (ui/js/app.js lvRouteTurn) for several of these, so a
    # server-side selector cannot reach them all — recorded here so the
    # selector design does not assume otherwise.

    Intervention(
        id=20, name="route_floor_hold", display="Floor Hold Route",
        cls=CLASS_ROUTE, position=200,
        location="chat_ws.py:4207 gate -> 4223 finalize",
        default_on=True, switchable=False, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Acknowledges that the narrator has claimed the floor and is "
                "still composing.",
        motivating_failure="Lori interrupting a narrator mid-thought.",
        locked_reason="Turn-ownership behaviour, not conversational style. "
                      "Disabling it makes Lori talk over the narrator.",
    ),
    Intervention(
        id=21, name="route_meta_question", display="Meta-Question Route",
        cls=CLASS_ROUTE, position=210,
        location="chat_ws.py:4246 gate -> 4331 finalize",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Deterministic answers when the narrator asks about Lori "
                "herself, AI, safety or identity.",
        motivating_failure="Mary asked 'what is an AI?' twice and received "
                           "'AI.' as the entire response.",
    ),
    Intervention(
        id=22, name="route_witness_meta_feedback", display="Witness / Correction Route",
        cls=CLASS_ROUTE, position=220,
        location="chat_ws.py:3822 sets turn_mode -> 4359 gate -> 4361 finalize",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Intercepts narrator meta-feedback and factual corrections "
                "with a deterministic second-person acknowledgment.",
        motivating_failure="Kent's K10: Lori first-person-echoed his hospital "
                           "correction as though she were Kent.",
        known_harm="NO MODEL RUNS ON THIS PATH. John's 238-word opening "
                   "chapter was claimed by the correction sub-type and "
                   "answered 'Got it - That I Still Picture Clearly.' Fixed "
                   "for that shape in Part 2; the route's authority to seize "
                   "a turn outright is unchanged.",
        trace_stage="(none - returns before the trace opens)",
        tests=("tests/test_witness_correction_narrowing.py",),
    ),
    Intervention(
        id=23, name="route_structured_narrative", display="Structured-Narrative Witness Route",
        cls=CLASS_ROUTE, position=221,
        location="chat_ws.py:3823-3824 sets _witness_use_llm_receipt",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Places long factual narration into witness-receipt mode: "
                "generation still runs, under the receipt directive, and the "
                "result is judged by the receipt validator.",
        motivating_failure="Rich chronological narration met with sensory "
                           "probes.",
        known_harm="Claims the product's BEST material. The better a "
                   "narrator gets at chronological storytelling, the more "
                   "likely this fires. It is the second exit of the same "
                   "over-claiming detector as id 22.",
    ),
    Intervention(
        id=24, name="route_memory_echo", display="Memory Echo Route",
        cls=CLASS_ROUTE, position=230,
        location="chat_ws.py:4384 gate -> 4605 finalize",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Deterministic readback when the narrator asks what Lori "
                "remembers about them.",
        motivating_failure="LLM drift and confabulation on 'what do you know "
                           "about me'.",
    ),
    Intervention(
        id=25, name="route_age_recall", display="Age Recall Route",
        cls=CLASS_ROUTE, position=240,
        location="chat_ws.py:4624 gate -> 4649 finalize",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Deterministic arithmetic answer to 'how old am I'.",
        motivating_failure="BUG-LORI-LATE-AGE-RECALL-01: v8 deflected with "
                           "'Is there something else on your mind?'",
    ),
    Intervention(
        id=26, name="route_correction_ack", display="Correction Acknowledgment Route",
        cls=CLASS_ROUTE, position=250,
        location="chat_ws.py:4662 gate -> 4759 finalize; turn_mode assigned "
                 "in the BROWSER by ui/js/app.js lvRouteTurn:2713",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="A SECOND correction path, distinct from id 22 and decided "
                "client-side.",
        motivating_failure="BUG-LORI-MIDSTREAM-CORRECTION-01: Mary's "
                           "'Actually we only had two kids, not three' was "
                           "routed as an ordinary interview turn.",
        known_harm="Its classifier lives in the browser, so a server-side "
                   "selector cannot switch it. Any baseline claiming 'no "
                   "routing' must account for this one separately.",
    ),

    # ── POST-GENERATION (positions 300+) ──────────────────────────────
    #
    # Ordered by the real sequence of `final_text` assignments in
    # chat_ws.py. Ids 30-42 are the decomposition of what is currently a
    # single `comm_control` checkpoint.

    Intervention(
        id=30, name="phantom_noun_detect", display="Phantom Proper-Noun Detection",
        cls=CLASS_VALIDATE, position=300,
        location="lori_communication_control._verify_proper_noun; "
                 "gate _phantom_noun_guard_enabled()",
        default_on=False, switchable=True, counterfactual=CF_PURE,
        purpose="Flags personal proper nouns in Lori's reply that are not "
                "grounded in narrator or profile context.",
        motivating_failure="Lori naming people the narrator never mentioned.",
    ),
    Intervention(
        id=31, name="phantom_noun_scrub", display="Phantom Proper-Noun Scrub",
        cls=CLASS_TRANSFORM, position=301,
        location="chat_ws.py:5983 final_text = _phantom_result['final_text']; "
                 "gate _phantom_noun_scrub_enabled()",
        default_on=False, switchable=True, counterfactual=CF_PURE,
        purpose="Removes sentences containing detected phantom nouns.",
        motivating_failure="As id 30, where flagging alone was not enough.",
    ),
    Intervention(
        id=32, name="cc_safety_path", display="Communication-Control Safety Exemption",
        cls=CLASS_LOCKED, position=310,
        location="lori_communication_control.py:917 _safety_path",
        default_on=True, switchable=False, counterfactual=CF_LOCKED,
        purpose="Routes a safety-triggered turn around ordinary "
                "communication control entirely.",
        motivating_failure="Safety boundary.",
        locked_reason="Acute safety. CLAUDE.md forbids env-value control.",
    ),
    Intervention(
        id=33, name="cc_question_atomicity", display="Question Atomicity",
        cls=CLASS_TRANSFORM, position=311,
        location="lori_communication_control.py:930 enforce_question_atomicity",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Splits compound questions so Lori asks one thing.",
        motivating_failure="WO-LORI-QUESTION-ATOMICITY-01.",
        known_harm="Walt turn 4: removed the clause naming his father, "
                   "leaving the delivered question 'How did you see him at "
                   "that time?' with no referent for 'him'.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=34, name="cc_question_count_truncate", display="Question Count Cap",
        cls=CLASS_TRANSFORM, position=312,
        location="lori_communication_control.py:939 _truncate_to_first_question",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Truncates to the first question when more than one '?' "
                "survives atomicity.",
        motivating_failure="Stacked questions overwhelming older narrators.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=35, name="cc_word_limit", display="Response Word Limit",
        cls=CLASS_TRANSFORM, position=313,
        location="lori_communication_control.py:966 _truncate_to_word_limit",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Caps Lori's reply at the session-style word limit, with "
                "+35 headroom when the narrator's turn is >= 50 words.",
        motivating_failure="Lori producing multi-paragraph replies that "
                           "crowd out the narrator.",
        known_harm="Fires as 'too_long' on turns the witness receipt "
                   "validator then fails as 'too_short'. Walt turn 5: 199 raw "
                   "words -> 29 delivered; Walt turn 6: 151 -> 13.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=36, name="cc_reflection_shaper", display="Reflection Shaper",
        cls=CLASS_TRANSFORM, position=314,
        location="lori_communication_control.py:980 shape_reflection; "
                 "gate _reflection_shaping_enabled()",
        default_on=False, switchable=True, counterfactual=CF_PURE,
        purpose="Deterministically re-arranges or trims the reflection Lori "
                "already produced. Never invents a narrator fact.",
        motivating_failure="WO-LORI-REFLECTION-02: prompt-heavy reflection "
                           "rules made Lori worse (golfball 4/8 -> 1/8), so "
                           "the next iteration had to be runtime shaping.",
        known_harm="'shaped_echo_trimmed_to_anchor' reduced Walt turn 5's "
                   "reflection to the two words 'North Quincy High School.'; "
                   "'shaped_echo_dropped' cut Walt turn 6 mid-clause at "
                   "'...the celebration you had envisioned - it.'",
        trace_stage="reflection_shape",
    ),
    Intervention(
        id=37, name="cc_reflection_validator", display="Reflection Validator",
        cls=CLASS_VALIDATE, position=315,
        location="lori_communication_control.py:997 validate_memory_echo",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Reports whether Lori's reflection was grounded in what the "
                "narrator said. Report-only by design - a deterministic "
                "rewrite here would invent narrator facts.",
        motivating_failure="Ungrounded or invented reflections.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=38, name="cc_push_after_resistance", display="Push-After-Resistance Detector",
        cls=CLASS_VALIDATE, position=316,
        location="lori_communication_control.py:1007 _detect_push_after_resistance",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Flags Lori continuing to probe after the narrator signalled "
                "resistance. Report-only; never modifies output.",
        motivating_failure="Phelan SIN 3 - too much arguing.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=39, name="cc_stub_collapse_repair", display="Stub Collapse Repair",
        cls=CLASS_REPLACE, position=317,
        location="lori_communication_control.py:1049 compose_stub_collapse_repair",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Replaces a <=5-word reply to a substantive narrator turn "
                "with a composed continuation.",
        motivating_failure="Mary received 'AI.' as an entire response; later "
                           "'Stanley. what happened next?' at 4 words.",
        known_harm="Fired on Walt turn 5 alongside too_long and "
                   "too_many_questions - three failures on one turn, then the "
                   "receipt validator called the result too_short.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=40, name="cc_chain_anchor_opener", display="Chain Anchor Opener",
        cls=CLASS_TRANSFORM, position=318,
        location="lori_communication_control.py:1102-1105",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Prepends 'From X to Y to Z - ' on factual-chain turns where "
                "Lori echoed fewer than two of >=3 narrator anchors.",
        motivating_failure="BUG-LORI-CHAIN-ANCHOR-ECHO-STRENGTH-01 Path B: "
                           "route sequences vanishing from the reply and the "
                           "memoir.",
        known_harm="EMITS NON-ENTITIES TO NARRATORS. Measured openers: 'From "
                   "Saint Patrick to Day to 1950 -' (splits Saint Patrick's "
                   "Day on the apostrophe), 'From Paul to Military to "
                   "Discipline - St.' (splits St. Paul on the period), and "
                   "downstream 'For and They - there's a lot held in that.' "
                   "Two function words as anchors.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=41, name="cc_story_first_grounding", display="Story-First Reflection Grounding",
        cls=CLASS_VALIDATE, position=319,
        location="lori_communication_control.py:1124 check_reflection_grounding; "
                 "gate _phase_1_enabled()",
        default_on=False, switchable=True, counterfactual=CF_PURE,
        purpose="Phase 1 validator; appends structured labels the "
                "regeneration loop consumes.",
        motivating_failure="WO-LORI-STORY-FIRST-PHASE-1-01.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=42, name="cc_story_first_hierarchy", display="Story-First Question Hierarchy",
        cls=CLASS_VALIDATE, position=320,
        location="lori_communication_control.py:1135 enforce_question_hierarchy; "
                 "gate _phase_1_enabled()",
        default_on=False, switchable=True, counterfactual=CF_PURE,
        purpose="Phase 1 validator for question level ordering.",
        motivating_failure="WO-LORI-STORY-FIRST-PHASE-1-01.",
        trace_stage="comm_control",
    ),
    Intervention(
        id=43, name="legacy_one_question_trim", display="Legacy One-Question Trim",
        cls=CLASS_TRANSFORM, position=330,
        location="chat_ws.py:6161 final_text = _trimmed",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="A second, older truncation to a single question, outside "
                "communication control.",
        motivating_failure="Predates comm_control's own question cap.",
        known_harm="Overlaps ids 33 and 34. Three layers now enforce one "
                   "question; none of them knows about the others.",
        trace_stage="trim_to_one_q",
    ),
    Intervention(
        id=44, name="era_fragment_repair", display="Era Fragment Repair",
        cls=CLASS_TRANSFORM, position=340,
        location="chat_ws.py:6279 final_text = _repaired",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Repairs replies that open with a bare era label fragment.",
        motivating_failure="Lori speaking a system era label at the narrator.",
        known_harm="Walt turn 2: prepended 'Can you tell me about' to a reply "
                   "that already read as a statement, producing 'Can you tell "
                   "me about the parish school... - that's a place filled "
                   "with memories.'",
        trace_stage="era_fragment_repair",
    ),
    Intervention(
        id=45, name="language_repair_es", display="Spanish Language Repair",
        cls=CLASS_TRANSFORM, position=350,
        location="chat_ws.py:6304 final_text = _es_repaired",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Repairs Spanish-session replies that drifted structurally.",
        motivating_failure="WO-SPANISH-LIVE-READINESS-01.",
        trace_stage="language_repair_es",
    ),
    Intervention(
        id=46, name="duplicate_response_bridge", display="Duplicate Response Bridge",
        cls=CLASS_REPLACE, position=360,
        location="chat_ws.py:6386 final_text = _bridge",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Substitutes a bridge line when Lori's reply is bit-identical "
                "to her previous one.",
        motivating_failure="Lori repeating herself verbatim across turns.",
        trace_stage="bridge",
    ),
    Intervention(
        id=47, name="witness_receipt_validator", display="Witness Receipt Validator",
        cls=CLASS_VALIDATE, position=370,
        location="chat_ws.py:6440 validate_witness_receipt; "
                 "gate _witness_use_llm_receipt at 6429",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Checks a witness-receipt reply for forbidden tokens, "
                "first-person mimicry, 35-110 words, <=1 question and >=3 "
                "echoed narrator facts.",
        motivating_failure="BUG-LORI-WITNESS-LLM-RECEIPT-01: the model "
                           "ignored the receipt directive under pressure.",
        known_harm="Only runs on turns id 23 already claimed. Its "
                   "'too_short' fires on text id 35 shortened for being "
                   "'too_long' - two layers with opposite objectives on one "
                   "turn.",
    ),
    Intervention(
        id=48, name="witness_receipt_fallback", display="Witness Receipt Fallback",
        cls=CLASS_REPLACE, position=371,
        location="chat_ws.py:6507 final_text = _wr_fallback",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Replaces a failing receipt with the deterministic composed "
                "receipt for the same detection.",
        motivating_failure="As id 47 - Kent must never see a sensory probe "
                           "even when the model drifts.",
        known_harm="FIRED ON 10 OF 15 TRACED TURNS. Produces the template "
                   "'X and Y - there's a lot held in that. What happened "
                   "next?', delivered on five turns. Splices narrator words "
                   "back in the first person ('You said Boston Latin: I went "
                   "to Boston Latin School.') and mid-clause ('...the public "
                   "school in the town we had bought.').",
        trace_stage="witness_receipt_fallback",
    ),
    Intervention(
        id=49, name="witness_receipt_fallback_on_exception",
        display="Witness Receipt Fallback (exception path)",
        cls=CLASS_LOCKED, position=372,
        location="chat_ws.py:6560 final_text = _wr_fallback",
        default_on=True, switchable=False, counterfactual=CF_LOCKED,
        purpose="Fail-closed substitution when the validator itself raises.",
        motivating_failure="An exception in a protection layer must not ship "
                           "unvalidated text.",
        locked_reason="Fail-closed infrastructure for an exception path, not "
                      "a conversational style choice.",
        trace_stage="witness_receipt_fallback_on_exception",
    ),
    Intervention(
        id=50, name="language_drift_repair", display="Language Drift Repair",
        cls=CLASS_TRANSFORM, position=380,
        location="chat_ws.py:6635 final_text = _es_repair_text",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Repairs replies that drifted out of the pinned session "
                "language.",
        motivating_failure="BUG-LORI-SESSION-LANGUAGE-CONTRACT-01.",
        trace_stage="language_drift_repair",
    ),
    Intervention(
        id=51, name="response_guards", display="Unconditional Response Guards",
        cls=CLASS_TRANSFORM, position=390,
        location="chat_ws.py:6832 final_text = _guarded_text; "
                 "lori_response_guards.py, 7 detect_/repair_ pairs",
        default_on=True, switchable=True, counterfactual=CF_PURE,
        purpose="Seven paired detectors and repairs: language drift, dangling "
                "determiner, meta-response leak, broken code-mix, seeded-fact "
                "intake, sensory pivot on chain, narrator echo.",
        motivating_failure="Each pair has its own; the module carries no "
                           "environment gate at all by design ('LAW 3: pure "
                           "deterministic. No LLM. No DB. No IO.').",
        known_harm="Registered as ONE entry because production calls them as "
                   "one block. Splitting into seven switchable entries is "
                   "owed if any single pair needs isolating.",
        trace_stage="response_guards",
    ),
    Intervention(
        id=52, name="guard_failure_fallback", display="Guard Failure Fallback",
        cls=CLASS_LOCKED, position=391,
        location="chat_ws.py:6864 final_text = _COMPOSE_GUARD_FAILURE_FALLBACK",
        default_on=True, switchable=False, counterfactual=CF_LOCKED,
        purpose="Fail-closed deterministic response when the guard wrapper "
                "itself raises.",
        motivating_failure="BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 proved "
                           "this class fires in production.",
        locked_reason="Disabling it ships unguarded LLM text on a crash - the "
                      "exact inversion the layer exists to prevent "
                      "(chat_ws.py:6840-6851).",
        trace_stage="compose_guard_failure_fallback",
    ),
    Intervention(
        id=53, name="profile_seed_ledger", display="Profile Seed Topic Ledger",
        cls=CLASS_LOCKED, position=399,
        location="profile_seed_turn / profile_seed state; topic disposition, "
                 "epoch, presentation recovery, stale-event protection",
        default_on=True, switchable=False, counterfactual=CF_LOCKED,
        purpose="Durable record of which onboarding topics were presented, "
                "addressed or remain open.",
        motivating_failure="A phantom presentation marked childhood_home "
                           "ADDRESSED - a durable disposition - and closed it "
                           "forever without ever asking.",
        locked_reason="Memory integrity, not conversational style. Registered "
                      "SEPARATELY from id 54 so the ledger stays strict while "
                      "the prose authority becomes selectable.",
    ),
    Intervention(
        id=54, name="profile_seed_delivery", display="Profile Seed Delivery",
        cls=CLASS_FINAL_WRITER, position=400,
        location="chat_ws.py:6905-6915 finalize_presentation -> final_text",
        default_on=True, switchable=True, counterfactual=CF_ELIGIBILITY_ONLY,
        purpose="Makes the canonical onboarding question the SERVER'S "
                "sentence, delivered by construction, so a topic cannot be "
                "stamped presented without actually being asked.",
        motivating_failure="The model claimed childhood_home was presented "
                           "while its visible words were 'Where would you "
                           "like to continue today?'",
        known_harm="THE LARGEST SINGLE SOURCE OF DAMAGE MEASURED. Fired on 7 "
                   "of 15 turns and discarded Lori's question every time, "
                   "substituting an onboarding question the narrator had "
                   "usually already answered in the same message: Walt said "
                   "'I was born ... in South Boston' and was asked 'Where did "
                   "you grow up?'; John's session ENDED on 'Are you retired "
                   "now?' just after he said he works as a school "
                   "psychologist. Confound: extraction ran on none of these "
                   "turns, so the profile never filled in.",
        trace_stage="profile_seed_delivery",
    ),
)


# ── Structural accounting ─────────────────────────────────────────────
#
# Every place production assigns to `final_text` in chat_ws.py, keyed by
# the SOURCE OF THE ASSIGNED EXPRESSION rather than by line number.
#
# Why the expression and not the line: line numbers shift whenever
# anything above them is edited, so a line-keyed map would fail on
# unrelated changes and get "fixed" by renumbering — which is how an
# accounting test becomes a chore instead of a guard. The right-hand
# side is stable across edits and still unique.
#
# Why not a written-down count: CLAUDE.md forbids hand-maintained counts,
# and rightly — they are wrong the moment the list grows. This map is
# checked in BOTH directions by the structural test, so a new mutation
# site fails until it is registered here, and a removed one fails until
# it is deleted here.
#
# One assignment may cover several interventions. `_cc_result.final_text`
# is the write-back for the whole communication-control block, which is
# exactly why ids 32-42 exist: the decomposition is what makes that one
# line's authority legible.
FINAL_TEXT_WRITERS: Dict[str, Tuple[int, ...]] = {
    # The ORIGIN. Not an intervention — this is the model's own text
    # arriving. Registered with no ids so the test can tell "accounted
    # for" from "unaccounted".
    "''.join(reply_parts).strip()": (),

    "_phantom_result['final_text']": (31,),
    "_cc_result.final_text": (32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42),
    "_trimmed": (43,),
    "_repaired": (44,),
    "_es_repaired": (45,),
    "_bridge": (46,),
    "_wr_fallback": (48, 49),          # two sites: normal + exception path
    "_es_repair_text": (50,),
    "_guarded_text": (51,),
    "_ps_delivered": (54,),
    "_COMPOSE_GUARD_FAILURE_FALLBACK(target_language=_guard_target_lang, "
    "safety_triggered=_is_safety_turn, resources=_guard_fail_resources)": (52,),
}

# Interventions that intercept the narrator BEFORE generation by calling
# `_finalize_deterministic_turn`. Keyed by the turn_mode gate value.
DETERMINISTIC_ROUTE_GATES: Dict[str, int] = {
    "floor_hold": 20,
    "meta_question": 21,
    "witness": 22,
    "memory_echo": 24,
    "age_recall": 25,
    "correction": 26,
}


# ── Derived accessors. Counts are computed, never written down. ───────

def all_interventions() -> Tuple[Intervention, ...]:
    return REGISTRY


def by_id(intervention_id: int) -> Optional[Intervention]:
    for item in REGISTRY:
        if item.id == intervention_id:
            return item
    return None


def by_name(name: str) -> Optional[Intervention]:
    for item in REGISTRY:
        if item.name == name:
            return item
    return None


def switchable() -> Tuple[Intervention, ...]:
    return tuple(i for i in REGISTRY if i.switchable)


def locked() -> Tuple[Intervention, ...]:
    return tuple(i for i in REGISTRY if not i.switchable)


def by_class(cls: str) -> Tuple[Intervention, ...]:
    return tuple(i for i in REGISTRY if i.cls == cls)


def in_pipeline_order() -> Tuple[Intervention, ...]:
    """Canonical execution order.

    Selection controls membership only. `{33, 40}` and `{40, 33}` denote
    the same experiment and both execute in this order.
    """
    return tuple(sorted(REGISTRY, key=lambda i: i.position))


def trace_stage_names() -> Dict[str, int]:
    """Map response-trace stage name -> intervention id.

    Several interventions share the `comm_control` stage today; that is
    exactly what the decomposition is for, and this mapping makes the
    collisions visible rather than hiding them.
    """
    out: Dict[str, List[int]] = {}
    for item in REGISTRY:
        if item.trace_stage and not item.trace_stage.startswith("("):
            out.setdefault(item.trace_stage, []).append(item.id)
    return {k: v[0] if len(v) == 1 else v for k, v in out.items()}  # type: ignore[misc]
