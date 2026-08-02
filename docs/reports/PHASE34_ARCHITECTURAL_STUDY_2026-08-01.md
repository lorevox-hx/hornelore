# Phase 3 / Phase 4 architectural study — read-only

**Status: STUDY ONLY. No production code changed. Nothing implemented.**
Baseline: `66d51c9`, tree clean, Phase 3+4 preserved in stash
`phase34 rejected live-chat regression 2026-08-01`.

Evidence: `hornelore_prompt_measure_readonly.py` run by Chris on
2026-08-01T13:32Z against the real `compose_system_prompt` and the real
Llama-3.1-8B tokenizer, model not loaded, no CUDA, family database opened
read-only against a disposable copy. Report:
`hornelore_prompt_measurements.json`.

---

## 0. The headline, before anything else

**Every narrator, in every condition, exceeds the 8,192-token window on
pushed main today.** This is not a Phase 4 regression. It is the current
state of the shipped system.

| narrator | plain `hi` final | over 8192 | over 7680 (with 512 reserve) | tokens cut off the FRONT every turn |
|---|---:|---:|---:|---:|
| Christopher Todd Horne | 9,221 | −1,029 | −1,541 | 1,029 |
| Janice | 9,677 | −1,485 | −1,997 | 1,485 |
| Kent | 9,194 | −1,002 | −1,514 | 1,002 |
| Melanie Zollner | 9,136 | −944 | −1,456 | 944 |

Worst observed: Janice with recent history, **10,131 final / −1,939**.

So the `inputs[:, -MAX_CONTEXT_WINDOW:]` slice on main is not a rare
safeguard. **It fires on every single turn, for every narrator, and has
been doing so for as long as these prompts have been this size.**

### What the front-cut removes — NOT YET PROVEN

**CORRECTED 2026-08-01 after review. The claim previously made here was
not supported by the evidence it cited, and is withdrawn.**

What this section originally said:

> `DEFAULT_CORE` is 17,859 characters ≈ **4,464 tokens**. […] The
> `ACUTE SAFETY RULE` begins ~2,481 tokens into `DEFAULT_CORE` […] The
> largest observed cut is 1,939. The crisis-handling block survives.

Every one of those token figures was derived by dividing a character
count by four. §9 of this same document states that no claim here rests
on character estimates. **Those two statements do not reconcile, and the
estimate is the one that has to go.** A four-chars-per-token divisor is
precisely the kind of assumption that produced the Phase 4 outage; using
it to reason about whether safety instructions survive is worse, because
the consequence of being wrong is not a broken turn.

What IS established, from the real tokenizer:

* the final prompt exceeds 8,192 in every measured case;
* the front-cut therefore removes 944–1,939 **real** tokens from the
  start of the prompt on every turn.

What is NOT established, and must be measured before anyone relies on
it:

* the real-token offset of `DEFAULT_CORE`'s start and end;
* the real-token offsets of the identity/purpose text, the
  "You are NOT …" boundary, the `ACUTE SAFETY RULE`, and the `988`
  instruction;
* which marker contains the **first surviving token** after the cut, per
  narrator and per condition.

Until the per-block instrument reports those positions, the honest
statement is: *material is being removed from the front of the core on
every turn, and we do not yet know which instructions it reaches.*

---

## 1. Why the 208 tests passed while `hi` failed

Every Phase 4 test fed the trimmer a **synthetic** message list with a
character-counting stub, and the largest "system" message in any fixture
was a few hundred characters. Not one test ever constructed a real
`compose_system_prompt` output for a real narrator.

The suite verified the trimmer's *algorithm* against an input
distribution that does not exist. Real inputs start at 9,100 tokens; my
fixtures topped out around 1,000.

This is the same error as Phase 5's 3.5-chars-per-token floor: calibrate
against synthetic data, ship, discover reality was outside the range.
**Making it twice in one work order is the pattern, not the incident.**

The rule this yields: *a budget test whose fixtures are smaller than the
production floor is not a budget test.*

## 2. Why the live acceptance credited chat coordination with no reply

Checks 2 and 3 read `[INFERENCE] acquire kind=chat concurrent=1` from
`api.log`. The slot is acquired **before** generation and logged whether
or not generation produces anything. The script therefore proved that a
lock was taken — not that a narrator received an answer.

A lock acquisition is not a conversation. The first acceptance check
should have been "a narrator types `hi` and Lori answers", and it was
not on the list at all.

---

## 3. Where the tokens actually are

From the measurement, per narrator, `plain_hi`:

| component | Christopher | Janice | Kent | Melanie |
|---|---:|---:|---:|---:|
| core only (composer, `runtime71=None`) | 4,081 | 4,081 | 4,081 | 4,081 |
| + identity / profile (`runtime71` supplied) | 9,185 | 9,641 | 9,158 | 9,100 |
| **growth from runtime71** | **+5,104** | **+5,560** | **+5,077** | **+5,019** |
| final after chat template | 9,221 | 9,677 | 9,194 | 9,136 |

And the scenario deltas on top of identity/profile:

| condition | added system tokens |
|---|---:|
| ordinary conversation | +11 |
| active Bismarck trip | +12 |
| Building Years (Life Map) | +56 |
| selected trip photo | +90 |
| recent history (system side) | +3 |

**This is the single most important finding in the study.**

The material Phase 4's tail-trim would have dropped — trip context, Life
Map context, photo context — totals **56 to 90 tokens**. The deficit is
944 to 1,939. Dropping *all* of the "optional" context recovers under
10% of what is needed.

My tail-trim patch could therefore never have fixed this. To reach a fit
it would have had to eat into the identity/profile mass — which is
exactly the "silently removes trip context, memory, directives" harm
ChatGPT warned about — and even then would still not have fitted for
Janice. **The emergency patch was reasoning from the same synthetic
evidence that caused the outage.** It should not be restored.

### Assembly order of `compose_system_prompt`

`compose_system_prompt` is 1,223 lines (`prompt_composer.py:3192-4415`).
It builds `parts` and returns `"\n\n".join(parts)`. In order:

| # | block | source | gate | purpose |
|---|---|---|---|---|
| 1 | `system_head` = `DEFAULT_CORE` (+ UI base) | module constant, 17,859 chars; real-token size UNMEASURED | always | Lori identity, purpose, boundaries, ACUTE SAFETY RULE, no-go phrases |
| 2 | `PROFILE_JSON: …` | session payload + UI profile + `last_user_text[:800]` | when non-empty | serialised narrator profile |
| 3 | `[ORAL_HISTORY_GUIDELINES]` | DB RAG `sys_oral_history_manifesto` | when present | pinned interviewing doctrine |
| 4 | `[GOLDEN_MOCK]` | DB RAG `sys_golden_mock_standard` | when present | pinned worked example |
| 5 | `_known_identity_facts_block(runtime71)` | runtime71 | `if runtime71` | verified narrator facts as ground truth |
| 6 | `_identity_grounding_rules_block(runtime71)` | runtime71 | `if runtime71` | anti-hallucination rules |
| 7 | English-first block | constant | `if runtime71` | language-drift rule |
| 8 | `[FACTUAL_CHAIN_DIRECTIVE]` | computed | conditional | chain-handling |
| 9–11 | three `directive_lines` blocks (L3616, L3672, L4400) | ~930 lines of branching logic, 76 mutation sites | `if runtime71` | pass/era/mode/session-style/safety/cognitive directives |
| 12 | `memory_block` | `build_conversation_memory_context(person_id)` | `if runtime71 and person_id` | conversation memory |

Blocks 1–4 are the 4,081-token core. Blocks 5–12 are the +5,019…+5,560.

**What is still unmeasured, and it is the number the architecture turns
on:** the split of that ~5,100 tokens across blocks 5–12 individually. I
can enumerate the blocks by reading; I cannot size them without the real
tokenizer. That is the one measurement I would ask for next (§8).

---

## 4. The runtime pipeline, as it actually is

### Narrator turn (chat)

```
browser sendUserMessage()
  -> WS /api/chat/ws  {start_turn, text, runtime71, surface}
  -> chat_ws: safety scan (deterministic patterns, then LLM 2nd layer)
  -> deterministic short-circuits (meta_question, age_recall, correction,
     witness, memory_echo, floor_hold) -- these RETURN without the LLM
  -> compose_system_prompt(conv_id, ui_system, user_text, runtime71)
  -> trip_interview_context appended INTO the system string
  -> msgs = [system] + history + [user]
  -> _apply_chat_template(msgs)  -> prompt string
  -> tok(prompt) -> inputs
  -> [main] blind tail slice to 8192 if over        <-- fires EVERY turn
  -> threading.Thread(model.generate, streamer, stopping_criteria)
  -> tokens BUFFERED server-side (BUG-LORI-RAW-STREAM-BEFORE-GUARDS-01)
  -> apply_response_guards on the complete text
  -> persist_turn_transaction + archive events
  -> single delta emitted, then `done`
  -> browser enqueueTts -> POST :8001 (separate process) -> audio
  -> browser plays audio
```

Three points that matter for Phase 3:

* generation is on a `threading.Thread`; extraction is on
  `asyncio.to_thread`. Nothing shared serialises them on main.
* the slot, if one exists, must cover `model.generate()` only. TTS is a
  **separate uvicorn process on 8001** and playback is in the browser.
  Neither is reachable from an in-process lock, and holding a lock across
  them would mean extraction never runs while Lori is speaking.
* `chat_ws` already serialises *itself* via `generation_thread_holder`
  and a 10s bounded join. It cannot see extraction.

### Completed-turn extraction

```
chat_ws completed-turn hook (gated on params["_persisted_turn_row_id"])
  -> turn_extraction.schedule_completed_turn_extraction
  -> _begin(): guards, then db.turn_extraction_claim
       key = "turnrow:<turns.id>"  UNIQUE(narrator_id, turn_key)
       existing row -> `duplicate`, never re-opened
  -> asyncio task, held in a strong-ref set, drained on shutdown
  -> _complete_claim: asyncio.wait_for(to_thread(_run_sync), 90s)
       -> routers/extract.py -> llm_interview._try_call_llm
       -> api._generate_text (SAME model, SAME process as chat)
  -> shape the payload; MalformedExtractionPayload if any item drops
  -> _finish_ledger(succeeded|noop|failed) + 0041 result row
  -> WS delivery + catch-up endpoint + ack
```

## 5. Every GPU consumer

| consumer | process | device | coordinated on main? | covered by my Phase 3? |
|---|---|---|---|---|
| chat `model.generate()` | API :8000 | CUDA | no | yes |
| extraction `model.generate()` | API :8000 | CUDA, same model object | no | yes |
| warmup `model.generate()` | API :8000 | CUDA | no | yes |
| **Whisper STT** (`routers/stt.py`) | **API :8000** | **`STT_GPU=1`, `STT_MODEL=large-v3` in `.env.example`** | **no** | **NO** |
| Kokoro TTS | **TTS :8001** | `KPipeline(device=None)` → auto-selects CUDA | no | not reachable in-process |

**Two findings here.**

**(a) Whisper may be a fourth CUDA consumer inside the same process, and
my Phase 3 coordinator did not cover it.** `.env.example` ships
`STT_GPU=1` with `large-v3`, and STT runs *immediately before* a
narrator turn, which is when contention would matter. So a coordinator
claiming "one generation at a time" may be overclaiming.

**But this is read from `.env.example` and `routers/stt.py`, not
observed.** Chris's actual `.env` values are unverified, and no VRAM
residency or overlap has been measured. The correct next move is to
MEASURE — device, residency, overlap — not to widen the LLM lock on the
strength of a config file. Whisper is a different model operation and
Kokoro is another process; both are GPU resource policy, which is a
separate question from serialising `model.generate()`.

**(b) Kokoro auto-selects CUDA** (`device: Optional[str] = None`,
confirmed by Chris) in a **separate process**. A `threading.Lock` cannot
reach it. Serialising it needs a cross-process mechanism; pretending
otherwise with an in-process lock would read as solved when it is not.
Per Chris's ruling this stays a performance follow-up unless a live run
shows real interference — recorded here so the claim boundary is honest.

---

## 6. Component classification

Per Chris's five tiers, with measured sizes where known:

| tier | components | measured |
|---|---|---|
| **mandatory core** | `DEFAULT_CORE` identity + boundaries + ACUTE SAFETY RULE; identity-grounding rules; language rule | UNMEASURED in real tokens (see §0 correction) |
| **current narrator turn** | the user message | 2 tok (`hi`) to a few hundred |
| **active task context** | trip block, Life Map era, selected photo | **56–90 tok total** |
| **recent conversation** | history messages | +3 system; +454 final for Janice's 8 msgs |
| **optional / compressible** | `PROFILE_JSON` blob, pinned RAG (two docs), known-identity facts, the three directive blocks, conversation memory | **≈5,100 tok combined, unsplit** |

The last row is the whole problem, and it is currently *indivisible* —
one `"\n\n".join()` with no structure a consumer can reason about.

---

## 7. Should Phase 3 and Phase 4 stay combined?

**No. Split them.** The evidence supports this clearly:

* **Phase 3 is a concurrency property.** Its correctness argument is
  about locks, threads and ownership, and is measurable without touching
  prompt content.

  **CORRECTED 2026-08-01.** This bullet previously said Phase 3 was
  "*working* — checks 1, 2, 3 and 7 passed on real log evidence". That
  overstates what the live run showed. Those four checks read LOCK
  MECHANICS from `api.log`; none of them established extraction
  preemption, same-claim continuation, absence of a partial extraction,
  one final result row, or a Lori answer generated, persisted and
  delivered. Checks 4/5/6 reported UNPROVEN.

  The accurate description is: **a promising coordinator design with
  partial mechanism evidence only, rejected with the combined block and
  not accepted.** It stays in the stash and is not restored.
* **Phase 4 is a prompt-architecture problem**, and the measurement shows
  it is not a trimming problem at all. It is a composer problem: ~5,100
  tokens of runtime material with no internal structure, on top of a
  4,081-token measured core, against an 8,192 window.

Bundling them is a direct cause of this failure. A coordinator whose acceptance was
never completed shipped alongside a budgeter that had never met a real
prompt, and the second took down the turns the first needed in order to
be proved at all.

---

## 8. Recommendation

**Sequence, smallest first. Nothing here is implemented.**

**Step 1 — measure the composer per block.** One more read-only
instrument, same posture as ChatGPT's: no model, no CUDA, disposable DB
copy, counts and hashes only. It reports the token size of each of the 12
blocks above, per narrator. Without this, any structural decision about
which blocks to compact is guesswork — and guesswork from synthetic
fixtures is what caused the outage.

**Step 2 — the composer returns structure, not a string.** The
source-level fix, not a trim. `compose_system_prompt` gains a sibling
that returns an ordered list of `(section_id, tier, text)` and joins it
for existing callers, so nothing changes behaviourally on landing. This
is what makes every later step possible and is the *only* step that
addresses the actual cause.

**Step 3 — compact the largest offenders**, chosen by Step 1's numbers.
On the reading, `PROFILE_JSON` (a JSON dump including
`last_user_text[:800]`) and the three directive blocks are the likely
mass. Compaction at source, not truncation at the edge.

**Step 4 — a budget that operates on tiers**, only once Steps 1–3 have
brought the mandatory core plus current turn inside the window with room
to spare. A budget layered on top of a prompt that cannot fit is a
mechanism for choosing what to lose, and this study shows there is
nothing cheap left to lose.

**Step 5 — Phase 3 separately.** The coordinator stays scoped to its
original contract: the shared Llama `model.generate()` calls — **chat,
extraction, warmup**. `ChatSlotTimeout` never bypasses the gate, and
release is ownership-checked.

**Whisper is NOT added to it by default.** §5 found that the STT router
may use CUDA in the same process, and that is worth knowing — but
Whisper is a different model operation and Kokoro is in another process.
That is a GPU resource-policy question, not automatically part of an LLM
generation lock. Measure the live STT device, VRAM residency and actual
overlap first; widen the gate only if evidence requires it. Letting
Phase 3 grow a fourth consumer before its original three are accepted is
how the last block got too big to land.

Acceptance begins with "a narrator types `hi` and Lori answers", and no
coordinator check counts unless a real reply was generated, persisted
and returned without a backend error.

### What must not happen

* Do not restore blind front slicing.
* Do not restore the tail-trim patch — measured, it recovers under 10% of
  the deficit and pays for it by removing context Lori needs.
* Do not change `MAX_CONTEXT_WINDOW`. Chris's ruling stands: the VRAM
  envelope is a fixed constraint.
* Do not treat the oversized composer as a later cleanup item. It is the
  finding.

---

## 9. Honest limits of this study

* The per-block split of the ~5,100 tokens is **not measured**. It is the
  one number the architecture depends on and it is Step 1.
* Trip / Life Map / photo scenarios are **controlled runtime envelopes**,
  not proof that any narrator currently has those states open. The
  instrument says so itself.
* Whisper's live GPU residency was **not observed**; it is read from
  `.env.example` and `routers/stt.py`. Whether `STT_GPU=1` is set in
  Chris's actual `.env` is unverified.
* Kokoro's device selection is inferred from the signature Chris ran plus
  the absence of any device argument at the call site. No live GPU
  measurement was taken.
* No claim here rests on character estimates. Where I had only estimates,
  I have said the number is unmeasured.

---

# ADDENDUM — per-block measurement, 2026-08-01

Instrument: `scripts/archive/hornelore_prompt_sections_readonly.py`, run
by Chris at HEAD `66d51c9`. Real Llama-3.1-8B tokenizer, model not
loaded, no CUDA, family DB read-only via disposable copy. Every figure
below is `len(tokenizer.encode(...))`. **No character estimates.**

## A1. Where the mass sits — and the limit of what that shows

**CORRECTED after review 2026-08-01. The original version of this
section claimed 8,741 tokens are "constant" and concluded the static
instruction set is 549 tokens over the window on its own. That
conclusion is WITHDRAWN. The arithmetic was right; the inference behind
it was not.**

Per-section, `plain hi`, all four narrators:

| section | Christopher | Janice | Kent | Melanie |
|---|---:|---:|---:|---:|
| `default_core` | 4,069 | 4,069 | 4,069 | 4,069 |
| `ui_base_or_profile_json` | 201 | 153 | 174 | 110 |
| `known_identity_facts` | 35 | 34 | 34 | 11 |
| `identity_grounding_rules` | 138 | 138 | 138 | 138 |
| `english_first_rule` | 849 | 849 | 849 | 849 |
| `lori_runtime_directives` | 3,612 | 3,613 | 3,612 | 3,612 |
| `conversation_memory` | 73 | 73 | 73 | 73 |
| **system total** | 8,977 | 8,929 | 8,949 | 8,862 |
| **final after chat template** | **9,013** | **8,965** | **8,985** | **8,898** |
| **over the 8,192 window** | 821 | 773 | 793 | 706 |

Sums verified against reported totals: exact, all four.

### What is established

* Every `plain hi` final prompt is **8,898–9,013 tokens** against an
  8,192 window, so **706–821 tokens are removed from the front** of
  every ordinary turn.
* The three largest blocks — `default_core`, `lori_runtime_directives`,
  `english_first_rule` — total **about 8,530 tokens** under the
  measured conditions.
* Content that varied **by narrator** was **121–236 tokens**: profile
  JSON and known identity facts.

### What is NOT established, and why the withdrawn claim was wrong

The original claim rested on reading "the same size for all four
narrators" as "static text". That inference does not hold, for three
separate reasons:

1. **All four scenarios used one runtime envelope.** Same
   `current_pass`, `session_style`, `cognitive_mode`, no safety mode, no
   softened mode. `lori_runtime_directives` is built by ~930 lines of
   branching on exactly those values. It came out the same size because
   the runtime was held constant, not because it is fixed text. **How it
   varies with runtime STATE is unmeasured.**
2. **`conversation_memory` = 73 in all four cases because there was no
   history** — this instrument passed an empty history list (see A6).
   That figure is an empty-block header, not a constant.
3. **`lori_runtime_directives` was not even identical** — 3,613 for
   Janice against 3,612 for the others. Small, but "byte-identical" was
   the word used and it was not true.

So the defensible statement is narrower: **under one measured runtime
configuration, the prompt is ~800 tokens over and almost none of the
excess is narrator data.** The stronger claim — that the instruction set
cannot fit regardless of narrator or state — is not supported by this
run and should not be repeated until it is.

### What survives the correction

The conclusion that mattered for Phase 4 is untouched: the excess is not
narrator context. Trip context measured ~12 tokens, Life Map ~56, photo
~90, against an overflow of 706–821. A trimmer working on those cannot
close the gap, so the Phase 4 budgeter was aimed at the wrong material
either way.

## A2. Where the mass is

Three blocks are 96% of it:

| block | tokens | what it is |
|---|---:|---|
| `default_core` | 4,069 | `DEFAULT_CORE`, one module constant |
| `lori_runtime_directives` | 3,612 | the `LORI_RUNTIME:` block — 930 source lines, 51 mutation sites |
| `english_first_rule` | 849 | one language-drift rule |

`lori_runtime_directives` is 3,612 tokens and **identical across all four
narrators to within one token**, which means it is almost entirely static
directive text rather than runtime data. It is named for the runtime and
is not, in practice, about the runtime.

`english_first_rule` at 849 tokens is worth stating plainly: that is
larger than the profile, identity facts, grounding rules and
conversation memory of all four narrators combined, for a single rule
about not drifting out of English.

## A3. The front-cut claim, now proven — by different evidence

§0 withdrew the claim that the cut spares the ACUTE SAFETY RULE, because
it rested on dividing characters by four. Measured in real tokens, for
**every narrator and every condition**:

| marker | removed by the front-cut? |
|---|---|
| `core_start` | **yes** |
| `identity_name_origin` | **yes** |
| `purpose_life_archive` | **yes** |
| `boundary_you_are_not` | **yes** |
| `acute_safety_rule` | no |
| `crisis_number_988` | no |

First surviving token lands in `boundary_you_are_not`, in all 16
narrator×condition cases.

So the original conclusion was right and the reasoning was not. Both
facts matter. A claim that happens to be true, argued from an estimate
the same document forbade, is still a claim that should not have been
made — and it was withdrawn for the right reason.

What Lori loses on every turn: her name and its origin, her stated
purpose, the Life Archive framing, and the opening of her behavioural
boundaries. What she keeps: crisis handling.

## A4. Additivity

`drift = 0` in all 16 cases. Section token counts **are** additive across
the `"\n\n"` joins here. The concern was legitimate — `encode(a) +
encode(b) ≠ encode(a+b)` in general — and the answer for this prompt is
that it does not bite. A section-structured composer can budget sections
independently without a correction factor.

## A5. Environment, as configured (read, not modified)

| key | value | note |
|---|---|---|
| `MAX_CONTEXT_WINDOW` | 8192 | fixed constraint per Chris's ruling |
| `STT_MODEL` | `large-v3` | |
| `STT_GPU` | **1** | **confirmed in the real `.env`, not just `.env.example`** |
| `STT_DEVICE` | unset | so `STT_GPU=1` decides: CUDA |
| `LORI_TTS_ENGINE` | `kokoro` | |
| `TTS_DEVICE` | `cpu` | |
| `TTS_GPU` | `0` | |
| `HORNELORE_EXTRACTION_BOUNDED` | 1 | bounded extraction prompt is live |

**Two findings here, both reported and neither actioned.**

**(a) Whisper large-v3 is configured for CUDA in the API process.** This
is now confirmed from Chris's actual `.env`, upgrading §5's inference.
Per Chris's ruling it stays a GPU resource-policy question and is
measured — device, residency, overlap — before anything widens the LLM
coordinator.

**(b) `TTS_DEVICE=cpu` and `TTS_GPU=0` are set, and the Kokoro adapter
reads neither.** `TTS_GPU` is consumed only by the retired Coqui adapter
(`tts/coqui.py:34`); `tts/kokoro.py` constructs `KPipeline(lang_code=…)`
with no `device` argument, and Kokoro's signature defaults
`device: Optional[str] = None`, which auto-selects. So the configuration
says CPU and the code cannot honour it. Not fixed here — recorded.

## A6. Limits of this measurement

Stated because the last two rounds of trouble came from unstated limits.

* **These numbers are a FLOOR, not production.** This instrument uses a
  fresh `conv_id` per condition, so `db.get_session_payload()` returns
  empty and `PROFILE_JSON` carries no session payload. The earlier
  instrument, using real session ids, measured Christopher at 9,221
  where this one measures 9,013 — a ~208-token session payload this run
  does not include. Production is *larger* than shown.
* **The `recent_history` condition measured no history.** The scenario
  list was called with an empty history list, so that row is a duplicate
  of `plain_hi`. The earlier instrument did load real history and found
  Janice's 8 messages worth +454 final tokens. Not re-measured here.
* `rag_oral_history` and `rag_golden_mock` **did not appear at all** in
  any produced prompt. Either those RAG documents are absent from the
  database or they returned empty. Unexplained; worth one query before
  any redesign assumes they are free.
* Trip / Life Map / photo conditions remain controlled runtime
  envelopes, not observations of live UI state.

## A7. Revised recommendation

**CORRECTED after review 2026-08-01.** An earlier version of this
section, and my summary to Chris, described reclaiming tokens from the
directive block as "one small, measured pass". That understates it and
the understatement is dangerous. `lori_runtime_directives` is ~3,612
tokens produced by ~930 lines of branching across 51 mutation sites,
governing pass, era, mode, session style, safety posture and cognitive
support. Compacting it safely is **its own Lori work order** with its
own browser acceptance — not a side task, and certainly not a warm-up
before the trip work.

Framing it as small is the same reflex that produced Phase 4: a change
that looked contained from the outside because I had not measured what
it touched.

**Step 1 — DONE.** The mass is located, with the limits recorded in A1.

**Step 2 — the composer returns structure.** Still the right direction
and still not started. Nothing can be reasoned about while the prompt is
one ~8,900-token string.

**Step 3 — reducing the static instruction mass is a SEPARATE WORK
ORDER**, sequenced before Daily Digest, full travelogue generation, long
history-rich interviews, and any significant addition to Lori's
behaviour. Not before the trip work. Its first task is measuring
`lori_runtime_directives` across real runtime STATES rather than across
narrators, since A1 shows that is the axis this study did not vary.

**Step 4 — a tier-aware budget is DEFERRED**, and may prove unnecessary.

**Step 5 — Phase 3 stays stashed.** Restore it only if WO1E produces
actual evidence that chat and extraction are still colliding. It is a
promising design with partial mechanism evidence, not an accepted one.

### Sequence agreed with Chris, 2026-08-01

1. **Freeze Lori's general prompt.** No composer changes.
2. Run **WO1E Bismarck acceptance** on `66d51c9`.
3. If the stack holds, finish **WO2 editable timeline acceptance**.
4. Clean test artifacts.
5. Build **Photo Palette**.
6. Prompt compaction as its own work order, before Daily Digest and
   Travelogue.
7. Phase 3 restored only on collision evidence from WO1E.

The trip work needs no prompt redesign. A language model cannot read the
database, so the backend summarises the relevant records into a compact
current-turn block — "Active trip: Bismarck Trip. Two photos attached.
No approved visual description." That mechanism already exists
(`trip_interview_context`) and measured ~12 tokens. It is context
plumbing, which is what Chris asked for in the first place.

## A8. What this says about the last two days

The Phase 4 budgeter was built to solve a problem that does not exist —
narrator context crowding out the core — while the actual condition was
a static instruction set 549 tokens too large before a narrator says
anything. Every test passed because the fixtures modelled the imagined
problem faithfully.

The measurement took one command and answered it in a minute.
