# LEAN-LORI-RUNTIME-SPEC

**Status:** PROPOSED — architecture decision; no production code authorized

**Date:** 2026-08-04

**Reviewed release:** `FINAL-R3-2026-08-04`

**Supersedes:** `FINAL-R2-2026-08-03`

**Canonical repository target:** `docs/architecture/LEAN-LORI-RUNTIME-SPEC.md`

**Paired work-order delivery:**
`WO-LEAN-LORI-RUNTIME-01-FINAL-R3-2026-08-04.md`

**Decision owner:** Chris Horne

**Narrator generality:** UNIVERSAL — the Horne family remains tenant zero

**Repository baseline reviewed:** `b5dc03f`

---

## What changed from R2, and why

R2 was a thorough draft written against baseline `09de0dc`. Between that
draft and this one, WO1E closed, two production defects were found and
repaired, and a live narrator session produced evidence that R2 has no
record of. R2's *rulings* survive almost intact. Its *facts* did not.

| R2 claim | R3 correction |
|---|---|
| Baseline `09de0dc`; commits through `09de0dc` | Baseline `b5dc03f`; five further commits, listed below |
| "The 54-test focused suite is green" | 89 tests across the two focused suites |
| WO1E is an open Pre-Gate blocking Phase 0 | **WO1E is CLOSED** with live verify and restart-verify evidence |
| "both completed narrator interactions persisted" — two trip links | **One** link for the story, **zero** for the photo answer |
| — | The 988 instruction recital (§ *The prompt damage is now narrator-visible*) |
| — | The sticky browser safety posture |
| — | The compound-name reflection trim |
| — | The safety cost counterfactual (composed vs raw-ephemeral) |
| — | The effective turn-mode handoff defect |
| — | `ensure_session` mutates the shared default session |

Everything R2 said about model lock, feature parking, prompt sequencing,
the conditional coordinator and the evidence-gated safety decision stands
and is repeated here without weakening.

---

## Locked decision

Lean Lori parks features that overload or compete for the present laptop. It
does not park hardware, delete capabilities, or reduce Lori to a generic chat
prompt.

The production language model is locked to the model already in Hornelore.
This work does not evaluate, name, download, canary, compare, or substitute any
other language model. It does not change the current model's quantization,
offload, serving backend, or 8,192-token operating window.

The lean runtime has two distinct jobs:

1. restore Lori's required instructions by repairing the oversized prompt at
   its source; and
2. stop optional feature paths from initializing or competing with the core
   narrator experience.

Feature parking alone cannot restore Lori's missing instructions. Prompt
repair alone cannot guarantee that optional models and continuous browser work
stay out of the way. Both contracts are required, but they must be implemented
and accepted separately.

## Authority and sequencing

This ADR incorporates the pushed work through `b5dc03f`:

| Commit | What it is |
|---|---|
| `0a8db41` | `meta_question` transcript/archive finalization |
| `12689a4` | its focused regression coverage |
| `d4f829c` | the four-way WO1E photo-question harness |
| `260491b` | study corrections, execution order, read-only real-token instrument |
| `09de0dc` | trip-story six-word floor and question-before-floor ordering |
| `7139644` | **stop `meta_question` opening the completed-turn hooks** |
| `9b92b57` | three harness false negatives from the 2026-08-04 run |
| `b5dc03f` | prove the two interactions separately, not by link count |

Governing documents:

- `docs/reports/PHASE34_ARCHITECTURAL_STUDY_2026-08-01.md`;
- `docs/wo/HORNELORE_CORRECTED_EXECUTION_PLAN_2026-08-01.md`;
- the read-only real-token instrument
  (`scripts/archive/hornelore_prompt_sections_readonly.py`).

The corrected execution plan remains authoritative for Trip Companion
ordering. Chris explicitly opens Lean Lori implementation; this document
does not open it.

The rejected combined Phase 3+4 work must not be restored wholesale. Prompt
architecture and Llama-generation coordination are separate concerns and may
never share one implementation block or acceptance claim.

### WO1E is CLOSED — 2026-08-04

R2 carried WO1E as an open prerequisite. It closed on 2026-08-04 at HEAD
`b5dc03f`, against the running stack, with Chris driving the browser and
the restart. **It is not re-run during Lean development.**

Automated: 89 tests, `OK`, across
`tests.test_wo_narrator_bridge_acceptance` and
`tests.test_meta_question_turn_finalization`.

Live `verify` — 20 passed, 0 failed, 0 not exercised, exit `0`:

- the story turn persisted and reached the trip as conversation
  `409ab3ee`, linked exactly once, `travels_shelf_trip/needs_day`;
- **the photo capability answer created no trip conversation link**;
- candidate `2a5e7060` traced to exactly one shelf turn, review-only,
  no inferred day on a completed trip;
- the answer — 497 chars, sha `d8a8a12853f36d8d` — present in **both**
  `turns` and the exported archive;
- no visual claim; answered before it asked; stated the real count of
  four attached photos; quoted no unapproved caption;
- capture lane declined the question by name
  (`direct_question_or_command`), not a generic error;
- no family truth written (5 → 5); trip stayed `completed`.

Live `restart-verify` — 15 passed, 0 failed, 0 not exercised, exit `0`.
Same link ids, same turn rows, byte-identical transcript and candidate
text, unchanged placement, nothing duplicated.

**Do not run `capture` again.** It overwrites the accepted baseline.
The preserved evidence is
`WO-NARRATOR-BRIDGE_ACCEPTANCE_{preflight,capture,verify,restart-verify}.console.txt`
plus `_accepted.json` and `_state.json`, all under `docs/reports/`.

**The shape that run proved is the shape R2 got wrong.** R2's acceptance
language assumed both narrator interactions become trip conversations.
They do not. The story is an ordinary interview turn and links once; the
photo question resolves to `turn_mode="meta_question"`, exposes no
committed row id, and links zero times **by design**. Any future
acceptance text that counts links rather than proving the two
interactions separately is reintroducing the same error.

---

## What the updated review proves

### Prompt loss is real, current, and measured

The read-only instrument used the production Llama tokenizer, production chat
template, a disposable database copy, and no model/CUDA load. Under its measured
plain-`hi` runtime state:

| Component | Measured tokens |
|---|---:|
| `default_core` | 4,069 |
| `english_first_rule` | 849 |
| `lori_runtime_directives` | 3,612–3,613 |
| Full system prompt | 8,862–8,977 |
| Final prompt after chat template | 8,898–9,013 |
| Leading tokens silently removed at 8,192 | 706–821 |

Earlier production-shaped measurement with real session payload/history found
9,136–10,131 final tokens and 944–1,939 leading tokens removed. The per-block
run is a floor, not a worst case.

The marker measurement proves that the current front cut removes Lori's
opening identity and name origin, her Life Archive purpose, and the
beginning of her role boundaries. The measured acute-safety and `988`
markers survive *those* cases. That does not make silent instruction
removal acceptable, and § below shows it is worse than "instructions are
missing".

Trip, Life Map, and selected-photo context added only about 12–90 tokens in the
measured scenarios. Removing that useful current-turn context cannot solve a
706–1,939-token deficit. The rejected tail trimmer was aimed at the wrong
material and must not return.

No file affecting prompt construction, the tokenizer, STT, TTS, extraction, or
the safety classifier changed between measurement baseline `66d51c9` and this
review baseline `b5dc03f`. The pushed delta changed deterministic turn
finalization, completed-turn hook exposure, acceptance evidence, and
trip-story capture classification.

### THE PROMPT DAMAGE IS NOW NARRATOR-VISIBLE

**New in R3.** On 2026-08-04 at 13:27, in a live Bismarck session, Chris
asked:

> can you locate the name of the cemetary on the internet or with the
> images I have?

Lori answered:

> I'm an AI and I can't place calls for you, but please call or text 988
> right now — that is the current US Suicide.

`prompt_composer.py:292–293` contains:

> MUST follow this pattern: 'I'm an AI and I can't place calls for you,
> but please call or text 988 right now — that is the current US Suicide
> and Crisis Lifeline.'

The reply is that template, recited, and **cut off exactly where the
template's own sentence continues** — stopping at "US Suicide" and
dropping "and Crisis Lifeline.'".

This was **not** the safety system. The turn ran `turn_mode=interview`
and the backend recorded `safety=False`. No deterministic route, no
classifier. The model read an instruction out loud in answer to a
question about finding a cemetery, most plausibly keyed off "can you
locate…" against the template's "I can't place calls for you".

This changes what the prompt overflow means. We knew the front cut
*removes* Lori's identity and purpose. This is the model *emitting* the
surviving fragments as if they were its reply — to an 86-year-old-facing
system, in the form of an unprompted crisis referral, on a turn about
his grandparents' grave.

It is the strongest single argument in this document for doing the
prompt work, and it is why prompt repair is not merely a token-budget
exercise.

### The sticky browser safety posture

**New in R3.** `ui/hornelore1.0.html:7314` flips the browser into safety
mode on a keyword pattern, and `:5617` returns `safety_pattern`
unconditionally once `_lv80SafetyModeActive` is set. It fired at 13:29,
on Chris's own correction:

> First Nobody talked about suicide. I asked about the location of a
> cemetary.

From then on `[chat_ws][ui-posture] directive routed to system prompt
(posture=safety)` entered every subsequent turn, and the 988 line
repeated at 13:29 and 13:30.

**The system produced a false crisis response and then made itself
uncorrectable: the only natural way to object to it re-arms it.** There
is no exit inside the session. For the narrator population this system
is built for, this is the more serious of the two defects, and it is a
contained frontend repair independent of the prompt work.

### The compound-name reflection trim

**New in R3.** At 13:26 Chris said:

> My mom's parents were Peter Zarr and Josie Zarr.

Lori replied:

> **Peter Zarr. are laid to rest there.** How did that visit make you
> feel…

`[lori][reflection-shape] actions=shaped_echo_trimmed_to_anchor
softened=False before_words=52`. The anchor trim cut a compound name
list at the first name, leaving an ungrammatical sentence and dropping
Josie — his grandmother — from a reply about her grave.

This is a narrator-dignity defect, not a cosmetic one, and it belongs to
the runtime reflection shaper rather than the prompt.

### Current resource evidence has limits

The May 3 baseline measured approximately 5,868 MB resident and 8,036 MB peak
on the then-current warm stack. It did not establish the present isolated cost
or residency of current Kokoro, browser FaceMesh, or current Whisper behavior.
It sampled at one second and may have missed short peaks.

| Setting/path | Updated finding |
|---|---|
| Main LLM | Current production model; unchanged by this ADR. |
| `MAX_CONTEXT_WINDOW` | 8,192; fixed. |
| Bounded extraction | `HORNELORE_EXTRACTION_BOUNDED=1` in the real `.env`. |
| Whisper | `large-v3`, `STT_GPU=1`. **`/api/stt/status` calls `_load_engine()` at `stt.py:96`**, so a default-off frontend does not keep the engine unloaded — any status poll can load it onto CUDA. |
| TTS | `.env` requests CPU; the Kokoro adapter accepts `device: Optional[str] = None` and never forwards it, so it cannot prove it honors CPU. |
| LLM safety classifier | `HORNELORE_SAFETY_LLM_LAYER=1` in the real `.env`. `safety_classifier.py:461` passes `conv_id=None`, `:453` retries once, `:458` `max_new=128`. The call defaults to **composed** mode, so `api.py:417` resolves `conv_for_prompt` to `"default"` and the classifier instruction -- `_SYSTEM_PROMPT`, **measured 5,699 chars ≈ 1,400 tokens**, not the ~200 assumed at R3 drafting -- rides on top of `default_core`. Live sensitivity, specificity, parse reliability and cost are unmeasured. |
| Camera/affect | Browser-local FaceMesh; no backend facial-recognition model. `TARGET_FPS = 15` at `emotion.js:39` is the only occurrence in `ui/` — declared, never read. Browser GPU placement unmeasured. |

Configured, loaded, resident, running, and formally verified are different
states. Lean diagnostics must report them separately.

**Whisper savings must be reported as recovered or preventive.** If the
engine is not resident in normal use, parking it recovers nothing and the
honest word is *preventive*. But the status route can load it, so the
passive-status fix and the parking gate are two halves of one saving, and
only the measured baseline says which.

**Kokoro CPU placement is gated on measured latency, not assumed.** Chris
named TTS as one of the three stages making turns feel slow. Moving it to
CPU trades VRAM for exactly that. Cold and warm synthesis time,
time-to-first-audio, total synthesis time, real-time factor and VRAM are
all measured before he decides.

### There is no accepted global Llama coordinator

Current WebSocket code prevents two generations from overlapping on the same
socket while an old turn unwinds. It does not serialize Llama generation across
sockets, REST chat, bounded extraction, or warmup.

The rejected coordinator is not on pushed main. Its earlier acceptance proved
some lock mechanics but did not prove a Lori answer was generated, persisted,
delivered, or that extraction resumed exactly once. A lock acquisition is not
a successful conversation.

Any future coordinator stays conditional on direct contention evidence and is
limited initially to API-process Llama generation for chat, extraction, and
warmup. Whisper and TTS are not automatically added. TTS is a separate process;
Whisper is a different model operation. Each requires its own live evidence.

---

## Lean terminology

| State | Meaning |
|---|---|
| **Active** | Available and permitted to initialize and run. |
| **Bounded** | Active under a measured input/output/resource contract. |
| **Deferred** | Preserved durably and run after the live turn or by explicit operator action. |
| **Moved** | Still active on another device, such as CPU; not parked. |
| **Parked** | Cannot initialize, load, open a stream, schedule work, consume GPU, or inject feature-specific prompt text. Code, consent, and data remain. |

A feature is parked only when all of these are true:

1. no constructor, model load, stream, timer, callback, warmup, or background
   task can start;
2. no GPU work occurs;
3. no feature-specific prompt section is included;
4. UI controls are disabled or truthfully labelled;
5. requested and effective state, with reason, are operator-visible;
6. data, schema, consent, settings, and re-enable code are preserved.

A documented environment variable with no reader parks nothing.

## Non-parkable Lori core

Lean Lori must retain:

- the current production LLM, unchanged;
- Lori's name, identity, purpose, narrator dignity, fact humility,
  anti-invention boundaries, language contract, and direct-answer behavior;
- the nine-stage deterministic runtime in
  `docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`;
- deterministic safety scan, safety precedence, deterministic acute response,
  flags, notification, and softened-mode persistence;
- normal oral-history conversation and supported session styles;
- `memory_exercise` as a retained core mode;
- exact two-sided text transcript and archive;
- canonical/provisional truth, known-fact projection, Life Map, and operator
  review;
- bounded b2a completed-turn extraction with its claim/result ledger;
- one explicit speech-input lane and CPU speech output;
- narrator reset, privacy, consent, provenance, and cross-narrator isolation.

"Full Lori function" means all core behavior remains available with the
instructions relevant to the active state. It does not mean injecting every
inactive mode, old example, feature rule, and historical turn into every model
call.

## Recent invariants that Lean work must preserve

The `b5dc03f` baseline carries six explicit protections:

1. A deterministic `meta_question` answer persists one turn transaction,
   writes one assistant archive event, rebuilds once, **exposes no
   committed row id**, and remains extraction- and placement-ineligible.
   Live-proved 2026-08-04.
2. The five other deterministic branches — `floor_hold`, `witness`,
   `memory_echo`, `age_recall`, `correction` — still lack equivalent
   assistant archive finalization. That is a known gap for a separate
   narrow repair (WO Phase 1A), not a reason to weaken the
   `meta_question` tests. Their *lack* of the archive write is currently
   the only thing protecting them from invariant 6 below.
3. Trip-story candidates require at least six words. One-to-five-word
   fragments stay out of operator review.
4. Conversation commands remain first, direct questions are classified
   before the generic word floor, and the August 1 Bismarck 10- and
   30-word turns remain eligible.
5. The life-story person-anchor patterns recognize `my mom's` but not the
   common STT form `my moms`. Repair must accept straight, curly and
   omitted apostrophes without changing the six-word Trip Story floor.
6. **The effective turn-mode handoff is broken, and Lean work must not
   assume it is not.** The dispatcher resolves the deterministic mode into
   a *local* variable. The only three writes to `params["turn_mode"]` in
   `chat_ws.py` are `:5480` (whatever the browser sent) and `:1247` /
   `:2909`, which both force `"interview"`. Both completed-turn hooks
   read the mode from `params` (`:648`, `:836`) and both eligibility sets
   are `frozenset({"interview"})` — so on a server-resolved deterministic
   turn **both mode gates pass**. A deterministic `return` does not skip
   the hooks either: `_generate_and_stream_body` is awaited at `:481`
   with the hooks on `:490` and `:502`. The only thing holding them out is
   the absence of `_persisted_turn_row_id` and `_archive_event_persisted`.
   This is why `7139644` exists, and why Phase 1A cannot mechanically add
   row-id plumbing to the other five branches.

Lean implementation may not alter these outcomes incidentally.

## Lean capability matrix

| Capability | Lean state | Contract |
|---|---|---|
| Current production LLM | **Active, locked** | No model/configuration change. |
| Lori identity and deterministic runtime | **Active** | Non-parkable. |
| Deterministic safety | **Active** | Runs before short-circuits; cannot be disabled by Lean. |
| LLM second-layer safety classifier | **Active pending evidence decision** | Gate A measures live incremental sensitivity, mortality specificity, parse/retry behavior, prompt cost and latency **in both composed and raw-ephemeral mode**. Chris then chooses active, parked, or separate repair; Lean does not predetermine it. |
| Browser safety posture latch | **Active, defective** | Repaired in Gate B; must not be parked or disabled. Deterministic safety is unaffected. |
| Normal oral-history conversation | **Active** | Primary narrator function. |
| `memory_exercise` | **Active** | Retained per its ADR. |
| Exact two-sided archive | **Active** | Required for every delivered response, including deterministic branches. |
| Bounded b2a extraction | **Active, deferred** | Sole automatic extraction path; starts only after durable turn/archive state. |
| SPANTAG/two-pass extraction | **Parked** | Current quality/default posture remains off; no fallback into it. |
| LLM question-layer fallback | **Parked** | Deterministic hierarchy remains. |
| Automatic section/follow-up/final memoir generation | **Parked during live narration** | Preserved as explicit post-session/operator work. |
| Life Map, truth, review, and trip context | **Active** | Compact current-task context is preserved, not trimmed first. |
| Camera, preview, FaceMesh affect | **Parked** | No stream, preview fallback, frame loop, affect event, or visual prompt branch. |
| GPU Whisper `large-v3` | **Parked** | Engine cannot load through transcription, status, warmup, or fallback. Savings reported as recovered or preventive. |
| Browser Web Speech | **Available as the one lean STT lane** | Its browser-service audio egress must be disclosed; typed input remains available. |
| Kokoro TTS | **Active, moved to CPU pending measured latency** | Adapter must honor effective CPU device; same voices/model; Chris decides after the numbers. |
| Warmup and eval generation | **Maintenance only** | Never automatic during a live narrator session. |
| Active model probes in status routes | **Parked** | Status is passive; explicit probes are separate maintenance actions. |

Lean mode must never claim that deterministic and LLM safety are equivalent,
claim unmeasured coverage, or change the classifier's state merely because the
profile was selected.

## Effective profile contract

Use one server-authoritative profile, proposed as:

```text
HORNELORE_RUNTIME_PROFILE=lean_lori
```

The same current model is used in every feature profile. The profile resolves
existing settings once into an immutable effective capability document. Every
backend, TTS service, and browser entry point consumes effective state rather
than independently interpreting defaults.

For each capability report:

```text
requested | effective | reason | source | initialized | device
```

The profile cannot override `LV_ENABLE_SAFETY=1`. An invalid or unknown profile
fails visibly to the operator. It must not silently fall back to a more
resource-intensive configuration.

## Instruction recovery contract

### Structured composer first — WO Phase 4

The composer first gains an ordered section representation while preserving
joined output byte-for-byte. Each section has a stable ID, activation rule,
priority, required status, trim policy, source, real-token count, and hash.

No budgeting or omission is allowed in this step. Real production-sized
fixtures — not synthetic tiny strings — prove equivalence.

### Remove duplicated current-turn text — WO Phase 5

After the behavior-equivalent structured composer lands, remove the narrator's
current text from `PROFILE_JSON.last_user_text`
(`prompt_composer.py:3271`), or replace it with a non-prose reference that
cannot duplicate or truncate that turn. The exact narrator turn remains once as
the user message.

No Python branch reads the duplicated prose, but the model consumes it. This is
a measured prompt behavior change and receives normal `hi`, Building Years,
trip, language, safety, and exact-occurrence acceptance before source
compaction begins. It is deliberately **after** the structured composer, not
before it: treating it as pre-architecture cleanup is what produced the
rejected Phase 4 outage.

### Compact measured sources — WO Phases 6–8

Compact at the source, in separately accepted changes:

1. `default_core` while preserving identity, purpose, dignity, fact humility,
   anti-invention, direct-answer posture, one-question discipline, capability
   honesty, and acute safety;
2. the 849-token English-first example library into a concise equivalent
   policy; and
3. the 3,612-token runtime directive builder so only active state branches are
   emitted.

Runtime-state measurement must cover normal conversation, all session styles,
cognitive support, safety/softened states, Life Map, active trip/photo context,
language state, factual chain, and deterministic modes. Measuring four people
under one identical runtime state is not proof across runtime states.

Parked features emit zero feature-owned prompt sections. The exact current
narrator text remains present once as the user message.

### Real-token budget after compaction — WO Phase 9

Only after mandatory core plus a current turn fits with adequate headroom may a
tier-aware budget land. For the current 8,192-token window, a normal 512-token
response and 128-token margin propose a maximum final templated prompt of 7,552
tokens. The request's real response allowance controls the actual ceiling.

Priority order:

1. mandatory identity, dignity, truth, language, and safety;
2. complete current narrator turn;
3. compact active-task context;
4. relevant identity/known facts;
5. recent complete narrator/Lori message pairs;
6. optional memory, retrieval, and examples.

The budget counts after the production chat template with the current model's
tokenizer. Old history leaves at whole-message boundaries. Named optional
sections leave whole. No raw token array is sliced from the front or tail.

If mandatory core plus the current turn cannot fit, generation does not start.
The operator receives a specific fault; the narrator receives a safe human
response without token/prompt jargon.

### Remove every blind chat slice — WO Phase 10

After structured compaction and budget acceptance, remove blind slicing from
WebSocket, REST, and streaming chat. Bounded raw-ephemeral extraction keeps its
separate fail-closed budget and does not inherit the narrator composer.

## Transcript, extraction, and drafting order

Every delivered exchange follows:

```text
archive exact narrator turn + exact delivered Lori response
    -> establish durable completed-turn ownership
        -> run bounded extraction when eligible
            -> run optional drafts only after the live session/operator request
```

The transcript is the source record. Extraction and drafting are derivatives.
Failure or deferral of either derivative cannot erase or roll back the exchange.

The current extraction design correctly records a claim before its held task,
keeps strong task references, drains on shutdown, and limits extraction to
`turn_mode="interview"`. Preserve those properties.

Remove the current composed five-second LLM availability ping from the bounded
path. The real bounded extraction attempt is its own readiness test: success can
mark the loader available and a genuine unavailable error can record the failed
outcome. Do not replace the generation with an unauthoritative flag that can
disagree with the actual call. `_is_llm_available()` has **four** callers in
`extract.py` — `_extract_via_singlepass` (L1890, the active bounded path),
`_extract_spans` (L2142), `_classify_spans_llm` (L2501) and
`_extract_via_spantag` (L4061) — so it must not be deleted repository-wide.
`/api/extract-diag` becomes passive; any active probe is an explicit maintenance
action.

## Conditional Llama coordinator

Do not implement a coordinator merely because concurrency is possible in
source. First park the approved clear drains, enforce the CPU/device decisions,
and measure the remaining stack. Only direct evidence that surviving
chat/extraction/warmup overlap causes latency, failure, duplication, or resource
pressure can open coordinator work.

If Chris opens `WO-INFERENCE-COORDINATOR-01`, its first scope is only the shared
API-process Llama `model.generate()` calls: live chat first, bounded extraction
second, explicit warmup/maintenance last.

Acceptance must prove a real Lori answer was generated, persisted, delivered,
and followed by exactly one completed extraction result. Peak Llama generation
concurrency must equal one. Whisper and TTS remain outside this coordinator
unless separately measured and separately approved.

## Safety contract

Deterministic safety is always first and cannot wait for GPU coordination. It
keeps precedence over floor buffering, meta questions, trip routes, witness,
memory echo, and other deterministic paths. Scan failure keeps the existing
default-safe route into interview composition.

### The classifier's cost may be an artifact of its call mode

`_try_call_llm` defaults to `prompt_mode="composed"`, which routes through
`api.chat()`, and `api.py:417` sets
`conv_for_prompt = (req.conv_id or 'default')`. So the classifier's
instruction (`_SYSTEM_PROMPT`, measured 5,699 chars ≈ 1,400 tokens) is composed **on top of** `default_core` and pinned
RAG, under the shared `default` session.

`raw_ephemeral` exists, sends system and user verbatim with no composition,
and forbids a `conv_id` — which this call site already satisfies by passing
`None`. It is a legal one-word change here.

**Gate A must therefore measure both modes.** Otherwise the
keep-versus-park decision rests on a cost that may belong to the call mode
rather than to the classifier, and the `SEPARATE SAFETY REPAIR` disposition
can only be chosen on a hypothesis. The counterfactual is a read-only
measurement, not a change: Lean must not silently switch the mode.

Two second-order effects to measure at the same time: whether the composed
prompt is itself truncated (the classifier instruction sits *after*
`default_core`, so `default_core` would be cut first — plausible that it
never truncates at all, but that is measured, not assumed), and whether the
competing instruction — `default_core` says oral-history companion,
`_SYSTEM_PROMPT` says emit JSON — explains the ~3% malformed rate noted at
`safety_classifier.py:450`.

### Live measurement, not mocked routing

Existing sensitivity and mortality-reflection unit sets supply mocked
classifier JSON. They prove routing mechanics, not that the live model
produces those classifications. The full-live assets those tests name —
`data/safety_red_team_cases.json` and `scripts/run_safety_red_team.py` —
are **absent at this baseline**. Mocked unit packs must not be reported as
live sensitivity evidence.

Gate A must exercise the real classifier with synthetic text and no
narrator persistence, notification, flag, or archive write. Two facts
constrain how:

- `api.py:429` guards both `add_turn` calls and `upsert_session` behind
  `if req.conv_id:`, and the classifier passes `conv_id=None`, so a direct
  call to `classify_safety_llm()` writes no turn;
- **but** `compose_system_prompt` calls `db.ensure_session(conv_id)` at
  `prompt_composer.py:3216`, and with `conv_for_prompt = "default"` that
  touches the shared default session's `updated_at`. A row-count
  comparison cannot see an UPDATE.

So Gate A calls `classify_safety_llm()` and the pure routing predicate
directly — never WebSocket routing, which persists — against a disposable
writable database, comparing contents, hashes and timestamps rather than
counts.

Chris chooses the effective state after that report: `KEEP ACTIVE`, `PARK`,
or `SEPARATE SAFETY REPAIR`. Until then the production classifier state is
unchanged.

### The sticky posture is a repair, not a parking decision

The browser latch described above is repaired in Gate B and is not subject
to the classifier disposition. Deterministic safety, acute positives,
mortality/past-tense negatives, ambiguity, parse-failure and scan-failure
default-safe behavior all stay green through that repair.

## Camera and facial-analysis contract

The feature is browser-local facial-expression/affect analysis, not facial
recognition or identity matching. MediaPipe FaceMesh processes a 320×240 stream
and sends only derived affect state to Hornelore.

When parked:

- `getUserMedia` is not called for video;
- FaceMesh and Camera are not constructed;
- the frame callback and affect timers do not run;
- stored consent does not auto-restart the stream;
- the preview cannot request its fallback stream;
- no derived affect enters runtime state or Lori's prompt;
- consent and preference records remain unchanged.

`TARGET_FPS = 15` at `emotion.js:39` is declared and never read — it is the
only occurrence in `ui/`. The camera/affect/TTS environment flags are
documented as vestigial and have no runtime readers. Lean parking must be a
real gate, not one of those flags.

## Speech contract

Lean retains voice interaction without allowing two STT paths.

- GPU Whisper `large-v3` is parked and cannot load from `/transcribe`,
  `/status`, a warmup, or fallback. **`/api/stt/status` currently calls
  `_load_engine()` at `stt.py:96`**, so the passive-status fix and the
  parking gate are two halves of one saving.
- Browser Web Speech is the existing lean voice-input lane when the operator
  accepts its browser-service audio egress. If that egress is not accepted,
  typed input remains available; no silent cloud or GPU fallback is allowed.
- `/api/stt/status` becomes passive. It reports configured and loaded state
  without calling `_load_engine()`.
- Kokoro remains the current TTS engine and current voices remain unchanged.
  Its adapter must honor the effective CPU device instead of relying on
  automatic selection — **after** Chris accepts the measured latency.

This device policy is not part of the optional Llama coordinator.

## Passive diagnostics

`GET` health/status calls cannot initialize a model, open a stream, generate,
enqueue extraction, or mutate state.

At minimum the operator surface reports:

- requested/effective runtime profile;
- current LLM identity and unchanged configuration;
- prompt final-token count, ceiling, section IDs, omissions, and required-marker
  presence without prompt text;
- deterministic and LLM safety states separately;
- camera/affect requested, consent, initialized, and effective states;
- selected STT/TTS lanes, configured device, actual loaded device, and privacy
  note;
- extraction owner/mode, queue/claim state, and latest outcome;
- Llama coordinator state, only if that separate work is active;
- current/peak VRAM from the existing monitor.

No secrets, raw prompt, narrator prose, audio, video, landmarks, or raw affect
labels enter diagnostics.

## Acceptance gates

**Prerequisite: MET.** WO1E passed fresh browser `verify` and post-restart
`restart-verify` on 2026-08-04 at `b5dc03f`, with no failed or skipped
check. Its accepted evidence is preserved and is not re-run.

Lean Lori is accepted only when evidence proves:

1. the current production model and serving configuration are unchanged;
2. final templated prompts fit their real budget without blind slicing;
3. Lori's required identity, purpose, boundaries, language, and safety markers
   are present for every tested runtime state, **and no system-prompt
   instruction text appears in a narrator-visible reply**;
4. a normal `hi` generates, persists, reaches the browser, and survives restart;
5. Building Years, active trip, selected photo, recent history, safety, language,
   and `memory_exercise` work with realistic production-sized fixtures;
6. parked features perform zero initialization, GPU work, background work, and
   prompt injection;
7. deterministic safety remains active and its precedence suite stays green;
8. the browser safety posture clears when the triggering condition passes, and
   a narrator's correction cannot latch it;
9. the LLM safety classifier's effective state matches Chris's post-evidence
   decision, and the operator sees its state, measured contribution/cost, and
   coverage meaning;
10. every delivered deterministic and LLM response has an exact two-sided
    transcript/archive entry exactly once — **this requires WO Phase 1A, which
    is inside this work order and precedes final acceptance**;
11. bounded extraction remains the sole automatic extraction path and starts
    only after durable turn/archive state;
12. the six-word trip-story floor and question-before-floor classification are
    unchanged;
13. straight, curly, and omitted-apostrophe kinship phrases retain the person
    anchor and eligible memories are not silently lost;
14. a reflection that echoes a compound name keeps the whole name and stays
    grammatical;
15. an eligible bounded extraction performs one extraction generation, not a
    composed availability generation followed by extraction;
16. exactly one STT lane is available and its egress/device is truthful;
17. Kokoro's actual device matches the approved decision, with its measured
    latency recorded;
18. camera, FaceMesh, preview, and affect remain stopped without deleting
    consent;
19. repeated passive status polling causes zero loads and generations;
20. any separately opened Llama coordinator proves a delivered answer and one
    final extraction — not merely lock logs;
21. rollback changes feature availability without changing narrator archives,
    truth, consent, settings, or extraction ledgers.

## Related sources

- `CLAUDE.md`
- `docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`
- `docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`
- `docs/architecture/MEMORY-EXERCISE-DECISION.md`
- `docs/architecture/COWORK-HANDOFF.md`
- `docs/reports/PHASE34_ARCHITECTURAL_STUDY_2026-08-01.md`
- `docs/wo/HORNELORE_CORRECTED_EXECUTION_PLAN_2026-08-01.md`
- `scripts/wo_narrator_bridge_acceptance.py`
- `scripts/archive/hornelore_prompt_sections_readonly.py`
- `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`
- `BUG-LIFEMAP-CONTEXT-TRUNCATION-01_Spec.md`
- `docs/wo/WO-LEAN-LORI-RUNTIME-01-FINAL-R3-2026-08-04.md`
