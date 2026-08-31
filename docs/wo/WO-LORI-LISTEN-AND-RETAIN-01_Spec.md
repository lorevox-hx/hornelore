# WO-LORI-LISTEN-AND-RETAIN-01

**Observation-first investigation of the complete path: what the narrator said,
what Lori wanted to say, what the control stack did to it, what she finally
said, and whether the narrator's story survived into biography, chronology,
Life Map, memory and memoir source.**

Status: OPEN · Filed 2026-08-31 · **This is the central Lori-development lane.**
Absorbs `WO-LORI-RESPONSE-GATING-AUDIT-01` and `WO-LORI-WITNESS-RECEIPT-SCOPE-01`
(both retained for root-cause detail, both unstarted).

UI traversal and PASS counts are supporting evidence only. The product outcome
is whether Lori listens intelligently and preserves the narrator's story
faithfully.

---

## 0. The three questions

1. **Did Lori understand and respond well to what the narrator actually said?**
2. **Did Lorevox store the narrator's information accurately, in the correct
   era and against the correct person?**
3. **Did that information remain available for later Life Map, memory and
   memoir creation?**

Response-log parsing answers only the first. **Both halves are traced together
or the work is not done.**

---

## 1. What is already established, and one new structural finding

Measured over **393 generated turns** in `.runtime/logs/api.log`:

| Layer | Fires | % turns |
|---|---:|---:|
| `comm_control` rewrite | 229 | 58% |
| `reflection-shape` | 146 | 37% |
| witness receipt FAIL | 77 | 20% |
| `era-fragment-repair` | 47 | 12% |
| `response-guards` | 35 | 9% |
| `trim-to-one-q` | 19 | 5% |

`comm_control` shortened 110 replies from **7,075 words to 3,935 (45% deleted)**.
Receipt gate fires `STRUCTURED_NARRATIVE` **109** vs `META_FEEDBACK` **8**.
Rejection reasons: `too_short` 62, `too_few_facts` 48, against `forbidden_token`
9 and `first_person_mimicry` 1. `prompt-budget kept_turns` mean **0.3**, min 0,
86 turns dropped. `trim-to-one-q` lengthened **16 of 19**.

### 1.1 NEW — the layers are a cascade, not independent defects

Execution order read from `chat_ws.py` (6,591 lines) places the receipt
validator at **line 5726**, *after* `comm_control` (5306/5340),
`reflection-shape` (5329), `trim-to-one-q` (5396) and `era-fragment-repair`
(5504).

Correlating each `validator FAIL` against shaping actions on the same `conv=`
in the preceding lines:

> **PROVISIONAL — conversation-correlated, NOT turn-proven.**
> 58 of 77 validator failures (75%) had an upstream rewrite logged on the same
> `conv=` within the preceding lines; 48 of those failed for `too_short`.

**This is a hypothesis, and the method used cannot prove it.** Correlation was
by conversation ID, and a conversation contains many turns — the rewrite line
found before a validator failure may belong to a different turn entirely.
Nothing in the current logs carries a turn-level identifier across layers, which
is precisely the gap this work order exists to close.

The hypothesis: `comm_control` deletes words, and the validator then rejects
what remains for being short. If true, **fixing the validator alone would be
wrong**, and the `too_short` counts cannot be read as evidence about the model.
**It must be proven at the individual-turn level, via the shared trace ID in
§4.1, before any behaviour changes.**

This is the strongest single argument for observation before repair.

---

## 2. Scope rules — binding

* **No threshold changes. No validator removals. No new conversational rules.
  No output repair.** The instrumentation commit must not alter one character
  of what any narrator receives.
* **Safety is not privileged.** Safety-labelled controls are inventoried and
  measured exactly like every other accumulated control, and judged on whether
  they help or harm ordinary narration. No new safety rules are added.
* **The crisis / suicidal-statement design is ON HOLD** and explicitly outside
  this work order. It is a separate, narrowly scoped design problem. It must
  stop driving how Lori handles ordinary biography, reflection, grief, family
  stories and structured narration.
* **`STRUCTURED_NARRATIVE` routing is NOT decided here.** Whether it should
  reach the receipt validator is one of the questions the evidence must answer.
* **Never turn missing instrumentation into a passing result, and never turn a
  broken measurement into a finding.** Every storage cell is one of:
  * `persisted` — found, with value and location
  * `rejected` — the system saw it and declined it, with the reason
  * `measured_absent` — the correct source **was successfully queried** and the
    value is genuinely not there
  * `measurement_failed` — the query itself failed: wrong origin, error,
    timeout, endpoint gated off. **This is not evidence of absence.**
  * `not_measured` — no instrumentation exists for this stage yet
* `Janice` and `Kaiserslautern` in `_VALIDATOR_FIRST_PERSON` are **recorded as
  confirmed cross-narrator contamination in a general-purpose control and are
  NOT repaired in this work order.**
* Model and 8,192-token window LOCKED. No narrator created or deleted.

---

## 3. Phase 1 — enumerate the real pipeline from the pushed source

Do not rely on any prior list, including §4 below. Derive the definitive order
by reading `chat_ws.py` and the services it calls. Record for each stage: file,
line, function, the condition that gates it, and whether it currently exposes
`before` text at all.

### 3.1 Order observed so far (starting point, to be verified and completed)

**The order is the durable finding. The line numbers are not.** They are an
as-of-2026-08-31 navigation aid against a 6,591-line file and will drift on the
next edit. Identify every stage by its function and log marker, never by line
number, and re-derive the order rather than trusting this table.

| # | Stage | marker (durable) | line as-of 2026-08-31 |
|---:|---|---|---:|
| 1 | Profile Seed plan | 4490 |
| 2 | Factual-chain detect | 4606 |
| 3 | **Prompt budget trim** (context loss) | 4766 / 4926 |
| 4 | Prompt composed (`style=`, era/pass/mode directives) | — |
| 5 | VRAM guard → **generate (RAW MODEL OUTPUT)** | `[WO-10M]`, then **NO MARKER EXISTS** | 4869 / 5075 |
| 6 | `comm_control` (1st) | `[comm_control]` | 5306 |
| 7 | `reflection-shape` | `[lori][reflection-shape]` | 5329 |
| 8 | `comm_control` (2nd) | 5340 |
| 9 | `trim-to-one-q` | 5396 |
| 10 | Buffered-stream defer | 5418 |
| 11 | `era-fragment-repair` | 5504 |
| 12 | **Witness receipt validator + fallback** | `[witness][llm-receipt]` | 5726 |
| 13 | Language contract / drift | 5845 |
| 14 | `response-guards` | 6048 |
| 15 | **Persist turn** | 6206 / 6301 |
| 16 | Story-trigger preserve | 6283 |
| 17 | Buffered-stream emit (narrator sees text) | 6471 |

Upstream detectors that set state consumed later: language contract (2491),
witness deterministic detect (2580), utterance frame (1939), safety (parked,
479/1516/2869/3088).

**Note the raw model output is currently not logged anywhere.** Stage 5 is the
single most important capture in this WO and it does not exist today.

---

## 4. Phase 2 — observation instrumentation (behaviour-neutral)

### 4.1 One shared trace

Keyed by **narrator ID · conversation ID · turn ID**. One record per turn,
carrying an ordered list of stage entries. Emitted into the evaluation
artifact, not into narrator-visible output.

Per stage capture:

* layer name and **execution index**
* fired: `true` / `false`
* reason / classification (the layer's own labels)
* **exact `before` text**
* **exact `after` text**
* words before / after · questions before / after
* text added / removed / replaced

**Counting log messages is not sufficient.** Where a layer does not expose its
before/after text, add observation-only instrumentation for it. Confirm the raw
response and every material after-stage are genuinely available; if a stage
cannot be captured, it is recorded `not_measured`, never inferred.

### 4.2 Response-half evidence per turn

| Stage | Evidence required |
|---|---|
| Narrator input | exact text, narrator, turn ID, conversation ID, selected era |
| Runtime context | era, pass, mode, Profile Seed state, stored biography supplied |
| Context retained | `kept_turns` / `dropped_turns`, and the **identity** of retained turns |
| Raw Lori response | model output before any rewriting |
| Control layers | before/after, fired, why, per layer in execution order |
| Delivered response | exact text shown to the narrator |

### 4.3 Storage-half trace — the part response logs cannot answer

Follow the same turn ID through:

| Stage | Evidence required | Known surface |
|---|---|---|
| Durable turns | narrator + assistant rows, metadata, correlation IDs | `persist_turn_transaction` / `export_turns` |
| Extraction | candidates proposed / accepted / rejected / updated, with reason | `turn_extraction`, `[extract-*]` |
| Bio facts | field path, value, status, **source turn**, narrator attribution | `/api/facts/list`, projection PATCH |
| Chronology | event created, era assigned | `/api/chronology-accordion` |
| Life Map | era placement, and whether it renders | `/api/interview/projection`, timeline |
| Rolling summary | what was written, what was lost | `/api/transcript/rolling-summary` |
| Threads / anchors | thread-anchor, update-threads | `/api/transcript/*` |
| Archive | story candidate preserved, id, path | `story_preservation`, `stories-captured/` |
| Memoir source | whether and how it becomes retrievable | `/api/memoir/canonical`, story-candidates review |

Each cell: `persisted` · `rejected` · `measured_absent` · `measurement_failed`
· `not_measured`. See §2 — the distinction is load-bearing.

**Known blocker to record, not fix:** `/api/memoir/canonical` is being requested
from the **static server on :8082**, which serves files and knows nothing about
that route, and 404s on every narrator open. **The correct memoir source has
therefore never been queried at all.** That result is `measurement_failed`, NOT
`measured_absent` — a 404 from the wrong host is not evidence that memoir data
is missing. The instrumentation must query the API origin directly; if that also
fails, the cell stays `measurement_failed`.

---

## 5. Phase 3 — the Walt seven-era run

Install Chris's harness into the repository matching current conventions:

* `scripts/ui/run_walt_seven_era_conversation.js`
* `tests/test_walt_seven_era_conversation.py`

Then extend for Phase 1/2 observation. **Existing log counters are explicitly
not sufficient** — they count fires, not effects.

**Conversation shape — this is a requirement, not a preference.** Walt speaks
in **several short, natural turns per era**, not one chapter-sized monologue.
The dense-narration baseline `r20260831-040506-010cd6` is preserved as a
contrast, not repeated. Real era controls, real composer, real Continue.

Preserve the complete narrator/Lori transcript and the complete storage trace.
Existing synthetic Walter O'Donnell, journaled UUID. No narrator created.
Nothing deleted.

---

## 6. The report — four causes, kept separate

Every observed weakness must be attributed to exactly one of:

1. **Raw model response quality** — she wrote it badly
2. **Missing context / prompt-budget damage** — she was not allowed to know it
3. **Post-generation control-layer damage or improvement** — a layer changed it
4. **Persistence, extraction, placement or retrieval failure** — it was said
   well and then lost

Conflating these is what produced four months of guards aimed at symptom 1 when
the evidence now points at 2 and 3.

The report must let a reader compare, per turn:

* what the narrator said
* what the raw model wanted to say
* what every control layer changed, in order
* what Lori ultimately said
* what facts Lorevox retained
* where those facts were placed
* what later memoir generation can actually retrieve

Include the quantitative findings from §1, each tied to a concrete before/after
example rather than left as a count.

---

## 7. Stop condition

**Stop after the Walt evidence report.** Do not open the full cohort. Do not
implement recalibration, removal or narrowing until the report is reviewed.

The report's purpose is to decide, per control, whether it **helps**, **harms**,
**needs narrower scope**, or **should be removed** — on evidence, for the first
time.

## 8. Questions the evidence must answer

1. Does `STRUCTURED_NARRATIVE` belong on the receipt path? (109 vs 8)
2. Are `too_short` failures caused by the model, or by `comm_control` upstream?
   The 75% figure is conversation-correlated and **must be re-derived from the
   turn-level trace** before it is quoted as a result.
3. What is the correct narrator-facing reply length? (observed mean 28 words;
   `min_words` is 35 — one of these is wrong)
4. Which layers, if any, made a response **better**? Nothing to date has looked
   for this, and the WO must not assume the answer is none.
5. Does the narrator's story reach the memoir source at all?
