# WO-LORI-COMMUNICATION-CONTROL-01 — Runtime Communication Guard for Lori

**Status:** SHIPPED (code landed 2026-05-01; this spec documents the architecture and the research grounding behind it)
**Owner:** Chris (scope) → Claude (build, landed)
**Author:** 2026-05-01
**Lane:** Lori-behavior, parent-session readiness gate
**Pre-reqs:** WO-LORI-QUESTION-ATOMICITY-01 (sibling lane, complete);
              WO-LORI-REFLECTION-01 (sibling lane, complete);
              WO-LORI-SAFETY-INTEGRATION-01 Phase 1 (acute-safety wiring);
              golfball-v2 harness operational

---

## 1. Why this exists

Lori was passing the shallow rule `question_count <= 1` in some configurations
but still violating the real interview rule **one cognitive target per turn**.
The 2026-04-30 golfball-v2-clean run produced four turn responses that were
double-barreled, two reflection turns that invented narrator emotion, and a
post-safety turn that drifted back into compound questioning. Layer 1 prompt
discipline alone — even a strong, explicit `LORI_INTERVIEW_DISCIPLINE` block
in the system prompt — did not produce reliable behavior.

This WO closes the gap by adding a **runtime communication-control layer**
that composes the existing atomicity filter and reflection validator,
adds per-session-style word-count limits + question-count enforcement,
and exempts acute-safety responses cleanly. Single chat_ws call site,
single harness report bundle.

The framing isn't ours — it's the research's. Six papers (cited in §1.1
below) converge on the same point: cooperative communication has rules,
prompt engineering can't reliably enforce them, and runtime control is
what makes a chatbot into a controlled conversational system.

### 1.1 Research grounding (six papers, with the role each plays)

> **Use Grice for communication rules, STA for runtime control
> justification, HumDial / Easy Turn / Proficiency-Conditioned Dialogue
> for spoken timing and turn-taking, and PersonaPlex for role-conditioned
> Lori behavior.** — Chris, 2026-05-01

**Load-bearing for THIS WO:**

1. **Rappa, Tang & Cooper 2026 — *Making Sense Together: Human-AI
   Communication through a Gricean Lens*** (*Linguistics & Education*
   91, doi:10.1016/j.linged.2025.101489).
   Defines the four maxims that map directly onto our enforcement
   rules: **Quantity** (don't make it more informative than required)
   → per-session-style word-count limits; **Manner** (avoid ambiguity,
   be brief, be orderly) → atomicity enforcement (truncate compounds);
   **Relation** (be relevant) → reflection grounding check; **Quality**
   (don't say what you believe to be false; don't say that for which
   you lack adequate evidence) → reflection validator (no invented
   affect, no archive language). The paper's critical finding —
   "communication failure is co-created by both user and model" — is
   why Lori needs guards on both sides of the turn boundary, not just
   on her output.

2. **Wang, Xu, Mao et al. 2025 — *Beyond Prompt Engineering: Robust
   Behavior Control in LLMs via Steering Target Atoms*** (ACL 2025
   Long Papers, pp. 23381–23399).
   The abstract is the operative quote: *"prompt engineering is
   labor-intensive and sensitive to minor input modifications, often
   leading to inconsistent or unpredictable model outputs. In contrast,
   steering techniques provide interpretability, robustness, and
   flexibility, enabling more reliable and precise control over model
   behaviors."* Justifies the architectural decision that this layer
   exists at all. Our wrapper isn't STA-style steering at the activation
   level; it's the conservative analog at the output level — pure-function
   deterministic enforcement on `final_text` after the LLM stream
   completes. Same logic, lower invasiveness.

**Supporting context (validity framing):**

3. **Mburu, Rong, McColley & Werth 2025 — *Methodological foundations
   for AI-driven survey question generation*** (*Journal of Engineering
   Education*, doi:10.1002/jee.70012).
   Explicitly names "double-barreled questions, redundant phrasing,
   and jargon" as clarity defects affecting data quality. Anchors our
   framing that this is a measurable validity issue, not a polish or
   style preference. Not load-bearing for the architecture but
   load-bearing for the *priority* — atomicity violations degrade
   research validity, not just narrator UX.

**Related lanes — the four spoken-dialogue / role papers:**

4. **Zhao, Wang, Li et al. 2026 — *The ICASSP 2026 HumDial Challenge:
   Benchmarking Human-Like Spoken Dialogue Systems in the LLM Era***
   (ICASSP 2026, paper 21850).
   Defines two tracks: (I) *Emotional Intelligence* — multi-turn
   emotional trajectory tracking, causal reasoning, empathetic response
   generation; (II) *Full-Duplex Interaction* — real-time decision-making
   under listening-while-speaking. Track I overlaps directly with
   REFLECTION-01's grounded-echo surface — "perceive and resonate with
   user emotional states" without inventing them is exactly the
   `echo_contains_unstated_emotion` guard. Track II is a **future lane**
   (Hornelore is currently cascaded ASR→LLM→TTS, not full-duplex);
   when we get there, the existing WO-LORI-SESSION-AWARENESS-01
   Phase 4 (Adaptive Narrator Silence Ladder) is its on-ramp.

5. **Liu et al. 2026 — *Easy Turn: Integrating Acoustic and Linguistic
   Modalities for Robust Turn-Taking in Full-Duplex Spoken Dialogue
   Systems***.
   Defines the four-state turn-taking taxonomy: *complete /
   incomplete / backchannel / wait*. Lori currently has none of these
   — she just emits when called. The framework lives in
   **WO-LORI-SESSION-AWARENESS-01 Phase 3 (MediaPipe attention cue)**
   and **Phase 4 (Adaptive Narrator Silence Ladder)**, both pending.
   This WO doesn't implement turn-taking; it composes cleanly with it
   when the time comes (the wrapper sees `final_text` after the LLM
   has decided to speak; turn-taking decides *whether* to speak).

6. **Roy, Raiman, Lee et al. 2026 — *PersonaPlex: Voice and Role
   Control for Full Duplex Conversational Speech Models*** (NVIDIA,
   ICASSP 2026, arXiv:2602.06053).
   Demonstrates state-of-the-art role-conditioned behavior via hybrid
   system prompts + voice cloning. Most directly relevant when Lori
   gets multi-narrator role adaptation (operator-vs-narrator persona,
   companion-mode warmth, etc.). **Future lane** — not this WO. The
   wrapper is persona-agnostic by design (operates on text shape, not
   tone).

7. **Obi, Yoshikawa, Saeki et al. 2026 — *Reproducing Proficiency-
   Conditioned Dialogue Features with Full-duplex Spoken Dialogue
   Models*** (IWSDS 2026, paper 1.4).
   Provides the metrics vocabulary for spoken interview quality:
   reaction time, response frequency, fluency, pause behavior,
   distributional alignment with human dialogues. **Future lane** —
   when we add spoken-dialogue evaluation to the harness, these are
   the columns. Doesn't justify the wrapper; tells us what to measure
   *next*.

(Counting note: Chris's six-paper synthesis at 2026-05-01 lists papers
1, 2, 4, 5, 6, 7 above. Mburu et al. appears in earlier ATOMICITY-01
v1.0 grounding and is retained here as supporting context.)

---

## 2. Hard rule

Every normal Lori interview response must pass:

1. Short grounded memory echo (≤25 words, narrator-grounded — Quality)
2. One atomic question (one subject, one predicate, one memory target — Manner)
3. No second inquiry (no `, and`/`, or` pivots into a second clause — Manner)
4. No invented emotion (Quality — narrator-affect whitelist applies)
5. No archive / database / extraction language (Quality)
6. No normal interview question during safety (Relation — safety frames are not interview frames)
7. Word count within session-style limit (Quantity)

Prompt composer guides this (Layer 1: `LORI_INTERVIEW_DISCIPLINE`);
runtime enforcement is the authority (Layer 2: this wrapper).

---

## 3. Scope

**In scope:**

- One additive `lori_communication_control` module in
  `server/code/api/services/`, composing the existing
  `question_atomicity` and `lori_reflection` modules
- Per-session-style word-count limits (clear_direct=55,
  warm_storytelling=90, questionnaire_first=70, companion=80)
- Acute-safety exemption (acute responses bypass enforcement; we still
  flag "normal_interview_question_during_safety" when appropriate)
- Single chat_ws call site, replacing the prior dual atomicity +
  reflection sites with one wrapper invocation
- Harness `communication_control` dict per turn (changed / failures /
  word_count / question_count / atomicity_failures / reflection_failures
  / safety_triggered / session_style)
- Unit tests + LAW-3 isolation gate

**Out of scope (explicitly):**

- Spoken-dialogue turn-taking (Easy Turn / Phase 3+4 of
  WO-LORI-SESSION-AWARENESS-01)
- Role / persona conditioning (PersonaPlex — future lane)
- Proficiency / fluency / reaction-time metrics in the harness (IWSDS
  — future lane)
- Reflection *rewriting* (per the §6 architecture in
  WO-LORI-REFLECTION-01_Spec — content-class deterministic rewrite is
  unsafe; v1 reports failures, never mutates the echo)
- Layer 3 (interview intelligence — emotional continuity, life-map
  anchoring) — separate lane, separate WOs
- BUG-DBLOCK-01 fix or any DB-write changes
- Truth-pipeline routing (TRUTH-PIPELINE-01)

---

## 4. Architecture — three layers

| Layer | What it is | Where it lives | Always-on? |
|-------|------------|----------------|------------|
| 1. Cognitive rules (Grice) | Defines WHAT good communication is | `LORI_INTERVIEW_DISCIPLINE` block in `prompt_composer.py` | Yes |
| 2. Behavioral control (this WO) | Enforces the rules at runtime | `lori_communication_control.py` wrapped in `chat_ws.py` | Gated `HORNELORE_COMMUNICATION_CONTROL=1` (default off → on after one clean run) |
| 3. Interview intelligence | Memory anchoring, emotional continuity, life-map alignment | Separate lanes: SESSION-AWARENESS-01 Phases 3+4, future lanes | Per-WO |

Layer 1 is the prompt directive. It catches ~80% of cases at zero
runtime cost but is sensitive to drift (per STA). Layer 2 is the
deterministic backstop — it runs on `final_text` after the LLM stream
completes, before the `done` event ships. Layer 3 is everything else
and is not in scope here.

---

## 5. Enforcement order

Per `services/lori_communication_control.py`:

```
0. If safety_triggered → exempt, validate-only path
   (acute SAFETY responses keep their own structure)
1. Atomicity → enforce_question_atomicity() truncates compounds
2. Question count → if > 1, truncate to first '?'
3. Word-count limit per session_style → truncate preserving first '?'
4. Reflection validator → REPORT-ONLY, no mutation
```

Each step modifies `final_text` (steps 1–3) or annotates the result
(step 4). The reflection step runs on the *post-truncation* text so
labels reflect what's actually being sent.

### 5.1 Why reflection is validator-only

Atomicity is **structure** — a deterministic rewrite (truncate at the
pivot) is safe because the operation only removes content, never
introduces it. Reflection is **content** — a deterministic rewrite
of an echo would invent narrator facts, which is exactly the LAW-3
failure mode WO-LORI-STORY-CAPTURE-01 was built to prevent. So v1 of
this wrapper logs reflection failures via `[chat_ws][comm_control]`
and lets the prompt-side directive carry the next turn. A future v2
*may* scope a narrator-fact-bounded rewrite — but only with strong
safety gates and only on heavy evidence that prompt-side discipline is
insufficient.

### 5.2 Acute-safety exemption

When `_safety_result.triggered` is True (acute pattern matched in
chat_ws's pre-stream safety scan), the wrapper short-circuits to a
**validate-only safety path**:

- `final_text` is returned unchanged
- atomicity / reflection / length checks all skipped
- the only check that runs is "normal_interview_question_during_safety"
  — which fires only when the response contains a normal interview
  question pattern AND lacks safety-acknowledgment markers (988 /
  "i'm so sorry" / "are you safe" / etc.). This catches the case
  where the LLM ignored the ACUTE SAFETY RULE and routed back to
  normal interview behavior

The 2026-04-30 golfball-v2-clean Turn 06 ACUTE response (`I'm an AI
and I can't place calls for you, but please call or text 988…`) passes
this path cleanly: contains 988 acknowledgment, no normal-Q regex
match, no failures.

---

## 6. Implementation

Landed 2026-05-01:

```
server/code/api/services/lori_communication_control.py    NEW
server/code/api/services/question_atomicity.py            (narrowed §4.5)
server/code/api/routers/chat_ws.py                        (refactored to single call site)
scripts/archive/run_golfball_interview_eval.py            (TurnResult + populate)
tests/test_lori_communication_control.py                  NEW (24 tests)
tests/test_lori_communication_control_isolation.py        NEW (LAW-3 gate)
tests/test_question_atomicity.py                          (3 new negative tests)
.env.example                                              (HORNELORE_COMMUNICATION_CONTROL flag)
WO-LORI-COMMUNICATION-CONTROL-01_Spec.md                  THIS DOC
```

ATOMICITY-01 narrowing in `§4.5 hidden_second_target`: dropped the
generic-relation branch (`mom and dad`, `school and church`, etc.).
Generic relation pairs are conventionally single coordinated retrieval
targets ("memories of my parents" is one memory blob); only proper-noun
pairs (`Spokane and Montreal`) still fire. `dual_retrieval_axis`
continues to catch the real compound (`place + emotion`).

`HORNELORE_COMMUNICATION_CONTROL=0` default. When ON, the wrapper
supersedes the legacy `HORNELORE_ATOMICITY_FILTER` and
`HORNELORE_REFLECTION_VALIDATOR` flags (those remain readable for
backward compat but the wrapper is the canonical path).

---

## 7. Acceptance criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | All six §4.1–4.6 atomicity categories surface via the wrapper on real Turn 03/04/07 inputs | `tests/test_lori_communication_control.py` GolfballRegressionTests |
| 2 | Reflection labels surface via the wrapper without mutating final_text | `ReflectionViaWrapperTests` |
| 3 | Per-session-style word limits enforced (55/90/70/80) | `LengthControlTests` |
| 4 | Multi-question turns truncate to first '?' | `QuestionCountTests` |
| 5 | Acute-safety responses pass through unchanged; "normal Q during safety" still flagged when it occurs | `SafetyExemptionTests` |
| 6 | Negative tests pass: "mother and father" / "reading and writing" / "you and your brother" do NOT flag | `NegativeTests` + `tests/test_question_atomicity.py` |
| 7 | LAW-3 isolation: wrapper imports zero extraction-stack code; only composes `question_atomicity` + `lori_reflection` | `tests/test_lori_communication_control_isolation.py` |
| 8 | `to_dict()` excludes raw text (privacy-safe harness export) | `test_to_dict_excludes_text` |
| 9 | Master extractor eval pass count unchanged (wrapper is chat-side, never touches `extract_fields`) | `r5h-place-guard` rerun shows ≥75/110 |
| 10 | Live: golfball harness rerun with `HORNELORE_COMMUNICATION_CONTROL=1` shows Turns 03/04/07 with `atomicity_failures: []` and per-turn `communication_control` dict populated | golfball-v3 |

Status as of 2026-05-01: criteria 1–8 green (211/211 tests pass). 9
and 10 pending live verification on Chris's stack.

---

## 8. Dispositions

- **ADOPT** if criteria 1–10 all green AND golfball-v3 (rerun with
  the wrapper enabled) shows `atomicity_failures: []` across Turns
  02–05 on two consecutive runs.
- **ITERATE** if reflection failures exceed ~30% of turns despite
  Layer 1 + the structural enforcement. Means the prompt directive
  needs sharper anchoring or the validator's whitelist needs widening.
- **PARK** if the safety-acknowledgment regex over-fires on legitimate
  acute responses (rare — current pattern is conservative). Reverts
  to validate-only-when-safe-pattern-matches.
- **ESCALATE** if the wrapper introduces master extractor regressions.
  Wrapper is chat-side and shouldn't touch extraction state, but if
  it somehow does we need to know fast.

---

## 9. Connections to existing lanes

- **WO-LORI-QUESTION-ATOMICITY-01** — the wrapper composes its
  `enforce_question_atomicity()`. ATOMICITY-01's §4.5 narrowing was
  done in this WO's commit because the negative tests demanded it.
- **WO-LORI-REFLECTION-01** — the wrapper composes its
  `validate_memory_echo()`. Reflection remains validator-only per
  REFLECTION-01's §6 architecture.
- **WO-LORI-SESSION-AWARENESS-01 Phase 2 (#285)** — the
  `LORI_INTERVIEW_DISCIPLINE` composer block (Layer 1) is its work.
  This WO is Layer 2.
- **WO-LORI-SESSION-AWARENESS-01 Phase 3+4 (#286, #287)** — future
  spoken-dialogue lane. Easy Turn / HumDial Track II / Proficiency-
  Conditioned cite forward into here.
- **WO-LORI-SAFETY-INTEGRATION-01** — supplies the
  `_safety_result.triggered` flag. Phase 1 landed; Phase 2 (LLM
  second-layer classifier) is pending. The wrapper's safety path is
  agnostic to which Phase fired.
- **WO-LORI-ACTIVE-LISTENING-01 (#314)** — partially superseded.
  Atomicity + reflection portions are now in their own WOs and
  wrapped here. Active reflection / direct-answer-first / menu-offer
  detection remain in #314's lane.
- **BUG-DBLOCK-01 (#344)** — orthogonal but co-blocking parent
  sessions. Atomicity + reflection + safety lock + truth pipeline are
  the four gates.
- **Future role-conditioning lane (PersonaPlex grounding)** — not
  yet specced. The wrapper is persona-agnostic; when a persona lane
  opens it can run before or after this wrapper without conflict.

---

## 10. Definition of done

```
Golf Ball harness shows on Turns 02–05:
  atomicity_failures: []
  question_count: 1
  compound_question: false
  communication_control.changed: true (when LLM compounded — wrapper truncated)
  communication_control.failures: [] (after truncation)

Turn 06:
  ACUTE SAFETY response unchanged (final_text == original)
  communication_control.safety_triggered: true
  no normal_interview_question_during_safety flagged

Turn 07:
  post-safety response does not contain "or is there something else"
  atomicity catches it (or_speculation)

Master extractor eval pass count unchanged (≥75/110 on r5h-place-guard).
No new DB lock events introduced.
Story_candidate creation still fires on canonical scene-anchor turns.
```

---

## 11. Anti-goals (worth saying explicitly)

- Do NOT make the wrapper clever. It composes existing modules + adds
  three deterministic checks (length, question-count, safety-path).
  Cleverness here is a regression vector.
- Do NOT pull in any LLM call inside the wrapper. STA-grounded
  determinism rule.
- Do NOT exempt `session_style` from the wrapper. Style varies tone
  and word budget; structure (echo + question, no compound) is fixed.
- Do NOT log narrator content. `to_dict()` excludes original_text and
  final_text by design; logs use failure labels only.
- Do NOT promote unreviewed extracted facts. This wrapper is chat-side
  and never touches the extractor.

---

## 12. Future lanes pointed at by the research

This WO closes the Grice/STA story. The other four papers point at
work that should land later:

- **HumDial Track II + Easy Turn** → spoken-dialogue full-duplex
  turn-taking. Maps to SESSION-AWARENESS-01 Phase 3+4.
- **PersonaPlex** → role-conditioned Lori behavior across operator /
  narrator / companion contexts. Not yet specced; opens a new lane
  when the persona-control surface becomes a measurable problem.
- **Proficiency-Conditioned Dialogue (IWSDS)** → spoken-dialogue
  evaluation metrics in the harness. Maps to a future
  WO-LORI-DIALOGUE-METRICS-01 that adds reaction-time / response-
  frequency / fluency / pause-behavior columns to the harness JSON.
  Currently parked because Hornelore is cascaded ASR→LLM→TTS, not
  full-duplex; the metrics need to wait for the architecture they
  measure.

The bumper sticker: **Layer 1 guides; Layer 2 enforces; Layer 3
listens.** This WO is Layer 2. Layer 3 is the work that lets Lori
hear the narrator.
