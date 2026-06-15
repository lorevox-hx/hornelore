# WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01 — Anchor Lori responses in narrator sentence structure

**Status:** SPEC — scoped, Phase 1 (scoring-only) ready for implementation; Phases 2–4 gated behind Phase 1 measurement
**Date:** 2026-05-02
**Lane:** Lori behavior. Parallel to BUG-LORI-REFLECTION-02 (runtime-shaping reflection) and WO-LORI-ACTIVE-LISTENING-01 (one-question discipline). All three lanes converge on runtime shaping over prompt-paragraph rules.
**Sequencing:** Opens after WO-EX-UTTERANCE-FRAME-01 Phase 0-2 (LANDED 2026-05-02). Independent of extractor lanes. Independent rollback per phase.
**Blocks:** Nothing — this is parent-session-quality work, parallel to the parent-session blockers in WO-LORI-SAFETY-INTEGRATION-01 and WO-LORI-SESSION-AWARENESS-01.
**Lights up:** Every Lori response in the sentence-diagram-survey + golfball + Lori behavior pack. Specifically the 3-of-3 misses on `parents.notableLifeEvents` (sd_008, sd_009, sd_010) where Lori reflected on the wrong clause; the multi-entity pet cardinality misses where Lori asked about cats instead of the named horse; and the consistent over-questioning pattern surfaced by the 22/42 baseline.

---

## What this WO is NOT

```
- NOT another prompt-paragraph rule.
  Locked principle from BUG-LORI-REFLECTION-01 Patch B postmortem
  (2026-05-02): prompt-heavy reflection rules made Lori worse, not
  better — golfball regressed 4/8 → 1/8 with extra prompt rules.
  This WO is runtime shaping + measurement, NOT a "Lori must always
  reflect a concrete anchor" prompt block.

- NOT a Lori behavior change in Phase 1.
  Phase 1 ships pure scoring/instrumentation. Behavior change waits
  for measurement to show where the gap actually is and how big.
  This is the "wire it in as scoring first" gate Chris locked.

- NOT a replacement for WO-LORI-ACTIVE-LISTENING-01.
  ACTIVE-LISTENING enforces the one-question / word-count / no-menu
  discipline. THIS WO enforces the one-anchor-from-narrator-text
  discipline. They compose: ACTIVE-LISTENING handles SHAPE,
  SENTENCE-DIAGRAM handles GROUNDING. Both run in the comm-control
  wrapper.

- NOT extractor work.
  The extractor's binding is BINDING-01 / FIELD-CARDINALITY-PETS /
  CASE-BANK-FIXUP territory. This WO uses the EXISTING utterance-
  frame output (already producing clauses + subject/event/place/
  object/feeling) as the input signal for Lori-side response
  shaping.
```

## Why this WO exists (research + live evidence)

### Research foundation

From Alshenqeeti (2014), *Interviewing as a Data Collection Method: A Critical Review*, English Linguistics Research 3(1), pp. 39–45 — the paper Chris uploaded as the grounding doc:

> *"A 'good' qualitative interview has two key features: (a) it flows naturally, and (b) it is rich in detail. To attain this, it is therefore necessary for researchers to remember that they are there to 'listen' not just speak. … interviewers should 'always seek the particular' (Richards 2003: 53)."* — Alshenqeeti (2014), p. 41, citing Dörnyei (2007: 140) and Richards (2003).

> *"the shorter the interviewer's questions and the longer the subject's answers, the better an interview is."* — Barbour and Schostak (2005: 43), cited in Alshenqeeti (2014), p. 41.

> *"as interviews are interactive, interviewers can press for complete, clear answers and can probe into any emerging topics."* — Alshenqeeti (2014), p. 40.

Three load-bearing principles for Lori:

1. **Seek the particular.** Find the *specific concrete element* the narrator just said and reflect on that, not the abstract category.
2. **Short questions, long answers.** Lori speaks less; the narrator speaks more. One question per turn, no compound asks.
3. **Probe emerging topics.** When the narrator surfaces a detail (a name, an object, a place, an action), follow that thread — do not pivot back to a system agenda.

### Live evidence

From `sentence_diagram_story_survey_v1` (2026-05-02 baseline, 22/42 extract pass + Lori chat captures):

**sd_010 — *"My dad Leo worked nights at the glass plant, but on Saturdays he played fiddle at barn dances. The plant paid the bills; the fiddle was what made him happy."***

Lori said: *"That sounds like a wonderful balance your dad had in his life. What was it about playing the fiddle at barn dances that brought him joy?"*

Anchored on fiddle/barn dances — actually decent! But the extractor missed `parents.notableLifeEvents` because the LLM routed "fiddle at barn dances" into `parents.notes`. The case-bank patch (Commit 2 today, sd_010 alsoAccept) fixes the scorer side. Lori's response, though, asked a "what was it about X that Y" closed inferential question rather than the simpler "what do you remember about those barn dances?" — which is what the research rule "seek the particular" recommends.

**sd_011 — *"We always had cats. Barn cats mostly. And my dad had a horse named Silver that he used for ranch work."***

Lori said: *"It sounds like you grew up in a rural setting with animals. What was your favorite thing about having barn cats?"*

Two failures: (1) collapsed two pet entities into "animals", (2) chose the LESS specific anchor (cats) over the MORE specific (Silver, the named horse). The narrator gave us a name. Lori ignored the name. This is exactly the failure mode the paper warns about — interviewer drifting toward summary instead of seeking the particular.

**sd_009 — *"My mom Evelyn worked as a secretary when she was young, then after the children came she was home with us. She still typed letters for neighbors when they needed help."***

Lori said: *"That's lovely. It sounds like your mom, Evelyn, was a very capable and helpful person. What was it like growing up with her?"*

Used the name (good) but pivoted to "growing up with her" (generic) instead of "the typed letters for neighbors" (specific, story-rich, narrator-grounded).

**The 22/42 pattern across the survey:** Lori is consistently warm, names some details, but defaults to abstract follow-ups when a concrete anchor was right there in the narrator's last sentence. The extractor's `parents.notableLifeEvents` × 3 miss cluster is the *same shape* on the data side — both surfaces fail to bind the specific over the general.

### Why this WO connects extraction and Lori

The utterance-frame already produces the structured clause-level meaning. The extractor consumes some of it (Phase 3 wiring is parked). Lori currently consumes none of it. **Wire Lori to the same structured signal the extractor will use, and you get coherent system behavior across both surfaces from one input.**

```
Narrator turn
   ↓
Utterance Frame (LANDED 2026-05-02 Phase 0-2)
   ↓
   ├── (parked: extractor binding hints — Phase 3+)
   └── Lori-side anchor selection (THIS WO)
         ↓
       Anchor (single string from narrator text)
         ↓
       Phase 1: scoring only — does Lori response mention the anchor?
       Phase 2: validator log — flag when Lori misses the anchor
       Phase 3: runtime shaping — inject anchor as data-driven directive
       Phase 4: optional post-LLM rewrite (only if Phase 3 insufficient)
```

## Anchor selection algorithm

Read `frame.clauses[]`. For each clause, extract candidates in priority order. Return the first non-empty candidate from the highest-priority clause.

**Priority order (research-grounded — most particular to most general):**

1. **Named entity** in the clause raw text — `\b(?:named|called)\s+([A-Z][a-z]+)\b` → "Silver", "Sam", "Biscuit". Names are the most specific possible anchor.
2. **Object** from `clause.object` — "piano", "horse", "aluminum plant". Concrete physical/scene anchors.
3. **Place** from `clause.place` — "Spokane", "barn dances", "church weddings". Geographic / event-location anchors.
4. **Event token** from `clause.event` — "played", "born", "moved". Action verbs.
5. **Feeling** from `clause.feeling` — "scared", "tired". Narrator-stated affect (only when narrator named it).
6. **Fall-through:** no anchor available — Lori responds without anchor injection (Phase 3 should NOT invent one).

**Conservative gates:**
- If the clause has `negation=True`, do NOT pull an anchor from it (the narrator denied that detail).
- If the anchor string is < 3 characters, skip (avoids "I", "we", "us" leaking through).
- Multi-clause turn: pick the clause with the highest-priority candidate, not the last clause.

## Phase plan

### Phase 1 — Scoring layer (golfball + sentence-diagram-survey harness)

**Read-only. No Lori behavior change.** Adds new per-turn metrics to existing harnesses so we can measure the gap before changing anything.

**Files:**
- `scripts/archive/run_golfball_interview_eval.py` (or wherever the golfball turn-scorer lives)
- `scripts/archive/run_sentence_diagram_story_survey.py` (extend the existing harness)

**New per-turn fields:**
```
anchor_candidate: str | None     # selected anchor from utterance_frame
anchor_source: str | None        # "named_entity" | "object" | "place" | "event" | "feeling" | None
anchor_present: bool             # case-insensitive substring match in assistant_text
active_listening_failures: list[str]
  ├── "no_anchor_candidate"      # frame produced nothing usable
  ├── "missing_selected_anchor"  # anchor exists but Lori didn't reference it
  ├── "multi_question"           # assistant_text contains > 1 "?"
  ├── "why_question"             # \bwhy\b in assistant_text (research: avoid)
  └── "generic_or_inventive_reflection"  # "it sounds like" / "i imagine" / "you must have"
```

**New rollup summary line:**
```
active_listening_passed: N/M
anchor_present: N/M
anchor_source_distribution: named_entity=X, object=Y, place=Z, event=W, none=V
top_failure_categories: missing_selected_anchor=N, multi_question=N, ...
```

**Helper to add (golfball + survey harnesses both):** `_select_anchor_from_frame(user_text)` calls `build_frame()` and applies the priority order above. Same code in both harnesses (or factored into a shared helper).

**Acceptance:**
- [ ] Both harnesses emit the new fields per turn
- [ ] Cross-run rollup compares `anchor_present` vs total turns
- [ ] At least one survey run + one golfball run banked as the Phase 1 baseline
- [ ] Zero behavior change to live Lori sessions
- [ ] Zero behavior change to extractor

### Phase 2 — Runtime validator (chat_ws.py, log-only)

**Still no behavior change. Adds operator visibility into the live narrator session.**

**File:** `server/code/api/routers/chat_ws.py`

**Logic:** Right after `final_text` is assembled and BEFORE the comm-control wrapper, compute the anchor from the narrator's `user_text` and check whether `final_text` references it. Emit a single `[lori][active-listening]` log line per turn with the same fields the harness scores.

```python
if user_text and final_text:
    _anchor_v, _anchor_src = _select_lori_response_anchor(user_text)
    if _anchor_v and _anchor_v.lower() not in final_text.lower():
        logger.info(
            "[lori][active-listening] violation=missing_anchor "
            "anchor=%r src=%s conv=%s",
            _anchor_v, _anchor_src, conv_id,
        )
```

**Gate:** behind `HORNELORE_LORI_ANCHOR_LOG=0` (default-off; mirrors `HORNELORE_UTTERANCE_FRAME_LOG` posture). Lazy import of `utterance_frame` so flag-off keeps the module out of `sys.modules`.

**Acceptance:**
- [ ] `[lori][active-listening]` log markers visible in api.log when flag is on
- [ ] Zero behavior change when flag is off (default)
- [ ] No DB writes
- [ ] No mutation of `final_text`

### Phase 3 — Runtime shaping (data-driven, gated behind Phase 1+2 evidence)

**This is when Lori behavior actually changes.** Only opens after Phase 1 baseline + Phase 2 live evidence prove the gap is real and worth closing.

**Two-part patch:**

**Part A — Pre-LLM anchor selection** in `chat_ws.py` (`_generate_and_stream_inner`, BEFORE `compose_system_prompt` runs):
```python
_anchor = _select_lori_response_anchor(user_text)
if _anchor:
    runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
    runtime71["lori_response_anchor"] = _anchor
```

**Part B — Data-driven directive injection** in `prompt_composer.py` (NOT a new paragraph of rules — a small data-bound block):
```python
def build_lori_anchor_directive(anchor: str | None) -> str:
    if not anchor or not str(anchor).strip():
        return ""
    safe = str(anchor).strip()[:80]
    return (
        "ACTIVE LISTENING ANCHOR:\n"
        f"- The narrator's last turn included: {safe!r}.\n"
        "- Begin your response by acknowledging that detail naturally.\n"
        "- Ask only one open question.\n"
        "- Do not invent context.\n"
    )
```

The directive is appended ONLY when an anchor was selected. The composer block is ~6 lines, data-bound, not a general rule paragraph. This sidesteps the BUG-LORI-REFLECTION-01 Patch B failure mode (prompt-heavy rules degrade behavior) by making the prompt content *case-specific to this turn's narrator detail*.

**Gate:** behind `HORNELORE_LORI_ANCHOR_INJECTION=0` (default-off until Phase 1 + 2 measure baseline).

**Acceptance gate (must hold before Phase 3 is accepted):**
- [ ] Phase 1 baseline shows `anchor_present` < 60% across golfball + survey
- [ ] Phase 2 live log evidence shows the gap holds in real narrator sessions
- [ ] Phase 3 measurement shows `anchor_present` ≥ 90% on the same harnesses
- [ ] `multi_question` count does not increase (composes cleanly with ACTIVE-LISTENING-01)
- [ ] `generic_or_inventive_reflection` count drops materially
- [ ] sentence-diagram-survey extract_passed does not regress (Lori doesn't push the narrator toward narrowed answers that hurt extraction)
- [ ] Master 114 v3/v2/mnw byte-stable when flag off; ≥0 delta when flag on

### Phase 4 — Optional post-LLM hard rewrite

**Only if Phase 3 prompt-anchor injection proves insufficient.** Not promised. Spec for Phase 4 is deferred until Phase 3 evidence demands it. If Phase 4 happens, it lives in the comm-control wrapper alongside the existing atomicity/reflection enforcement, and rewrites the first sentence of `final_text` to include the anchor when missing.

The reason Phase 4 is gated behind Phase 3 evidence: post-LLM rewrite is the most aggressive intervention. We want to give the data-driven prompt-injection path a clean chance first because it preserves more of Lori's natural voice.

## Locked design rules

```
1. Runtime shaping over prompt-rule paragraphs.
   The BUG-LORI-REFLECTION-01 Patch B postmortem locked this
   principle. This WO is the second test case for it. Any
   future iteration that proposes "let's add a Lori must
   always seek the particular" prompt block gets rejected on
   the locked principle alone.

2. Scoring before behavior. Phase 1 ships first. Phase 2 ships
   only after Phase 1 baseline shows where the gap is. Phase 3
   ships only after Phase 2 live evidence confirms the gap
   holds outside the synthetic harness.

3. Anchor must come from narrator text, not invention.
   The selector reads the utterance-frame output of THE NARRATOR'S
   TURN. It does not pull from prior turns, profile, or schema.
   The narrator's words are the only valid source. (Same rule as
   BUG-EX-BIRTH-DATE-PATTERN-01 fallback.)

4. Negation suppresses anchor extraction.
   If the clause carries negation, no anchor is pulled from it.
   The narrator denied the detail; Lori must not push it back.

5. Compose with ACTIVE-LISTENING-01, do not collide.
   Both WOs run in the comm-control wrapper. ACTIVE-LISTENING-01
   enforces shape (one question, word cap, no menu offers). THIS
   WO enforces grounding (one anchor from narrator text). Acceptance
   gates check both don't regress each other.

6. Default-off env flag at every phase.
   Phase 1 is harness-side so no flag needed. Phase 2:
   HORNELORE_LORI_ANCHOR_LOG=0. Phase 3:
   HORNELORE_LORI_ANCHOR_INJECTION=0. Each defaults off until
   the prior phase's measurement gate passes.

7. Operator-visible log marker, not narrator-visible signal.
   [lori][active-listening] log markers go to api.log only.
   The narrator session never sees a "you missed an anchor"
   surface — that's per the SESSION-AWARENESS-01 banned-vocab
   spec (no scoring/grading visible to narrators).
```

## What this WO does NOT do (deliberate scope wall)

- Cross-clause coreference (resolving "he was just gone" to "Sam the pig" from a prior clause). Phase 0-2 utterance-frame doesn't do coreference; this WO inherits that limit. Future enhancement, separate WO.
- Multi-turn memory of prior anchors. Each turn's anchor selection reads only that turn's narrator text. Cross-turn theme tracking is SESSION-AWARENESS-01 territory.
- Anchor injection on memory_echo / correction / safety turns. Those bypass the comm-control wrapper by design (deterministic composers, not LLM). Anchor injection only fires on `turn_mode == 'interview'`.
- Extractor behavior changes. Anchor selection consumes utterance-frame output but does NOT modify how extractor consumes it. Extractor binding is BINDING-01.
- Lori prompt rewriting beyond the small data-bound directive in Part B. No new general behavior paragraphs.

## Sequencing relative to other lanes

```
WO-EX-UTTERANCE-FRAME-01 Phase 0-2     ← LANDED 2026-05-02 (input signal)
WO-LORI-ACTIVE-LISTENING-01            ← shape discipline (composes with THIS)
BUG-LORI-REFLECTION-02                 ← reflection runtime shaping (sibling lane)
WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01   ← THIS (anchor grounding)
WO-EX-BINDING-01 second iter           ← extractor binding (parallel)
WO-LORI-CONFIRM-01                     ← confirm pass (downstream)
```

Independent rollback per phase. Composes with ACTIVE-LISTENING-01 + REFLECTION-02 in the comm-control wrapper.

## Cost estimate

```
Phase 1 (harness scoring):        ~80 lines (selector + scorer + rollup),
                                  ~5 unit tests, 1 golfball run +
                                  1 survey run = half a session
Phase 2 (chat_ws runtime log):    ~25 lines, default-off flag + AST
                                  smoke + 1 live verification turn = 1 hour
Phase 3 (anchor injection):       ~60 lines (chat_ws pre-LLM hook +
                                  prompt_composer directive builder),
                                  default-off flag, 1 golfball run +
                                  1 survey run + master-114 byte-stability
                                  check = 1 session
Phase 4 (post-LLM rewrite):       deferred; not estimated
Total Phase 1-3:                  ~2 sessions across calendar week,
                                  with a measurement gate between each
```

## Acceptance gates (rolled up)

```
Phase 1  [ ] golfball + survey emit anchor_candidate / anchor_present /
             active_listening_failures per turn
         [ ] rollup summary line shows N/M for active_listening_passed
             + anchor_present
         [ ] one banked baseline run per harness
         [ ] zero behavior change to live Lori sessions
         [ ] zero extractor change

Phase 2  [ ] HORNELORE_LORI_ANCHOR_LOG flag added (default-off)
         [ ] [lori][active-listening] markers visible in api.log on
             fresh narrator turns when flag on
         [ ] zero behavior change when flag off
         [ ] zero DB writes from this layer

Phase 3  [ ] HORNELORE_LORI_ANCHOR_INJECTION flag added (default-off)
         [ ] anchor_present rises ≥30 percentage points on golfball +
             survey when flag on
         [ ] multi_question count does not increase
         [ ] generic_or_inventive_reflection count drops materially
         [ ] sentence-diagram-survey extract_passed ≥ baseline
         [ ] master 114 v3/v2/mnw byte-stable with flag off, ≥0 with on
         [ ] golfball stable_pass count ≥ baseline (no reflection
             regression)

Phase 4  (gate undefined; opens only on Phase 3 insufficient evidence)
```

## Bumper sticker

```
The narrator already gave us the particular.
Lori currently picks the abstract.
Phase 1 measures the gap. Phase 2 watches it in production.
Phase 3 closes it with a six-line data-bound directive,
not a fourth paragraph of prompt rules.

Seek the particular. Then ask one short question. Then listen.
```

## Citation

Alshenqeeti, H. (2014). *Interviewing as a Data Collection Method: A Critical Review*. English Linguistics Research, 3(1), pp. 39–45. doi:10.5430/elr.v3n1p39.

Operative quotes referenced in this spec:
- *"interviewers should 'always seek the particular'"* (Richards 2003: 53, cited p. 41)
- *"a 'good' qualitative interview … flows naturally and is rich in detail"* (Dörnyei 2007: 140, cited p. 41)
- *"the shorter the interviewer's questions and the longer the subject's answers, the better an interview is"* (Barbour and Schostak 2005: 43, cited p. 41)
- *"as interviews are interactive, interviewers can press for complete, clear answers and can probe into any emerging topics"* (p. 40)
