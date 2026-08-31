# WO-LORI-RESPONSE-GATING-AUDIT-01

**Measure what the response-shaping stack does to Lori before removing or
recalibrating any of it. Then fix the layers, in evidence order.**

Status: **ABSORBED 2026-08-31 into `WO-LORI-LISTEN-AND-RETAIN-01`**, which adds the
storage half, de-privileges safety, and found the layers form a cascade
(75% of validator failures judge already-rewritten text). Retained for the
per-layer detail its successor cites.

Filed 2026-08-31 · Lane: Lori runtime (response shaping)
**Supersedes and absorbs `WO-LORI-WITNESS-RECEIPT-SCOPE-01`**, which addressed
one layer of nine.

Evidence: `.runtime/logs/api.log` (2026-06-24 → 2026-08-31, **393 generated
turns**) · `docs/reports/UI-REVIEW-2026-08-31.md` · interactive-dialogue
evaluation · dense baseline `r20260831-040506-010cd6`

---

## 0. The governing finding

Nine independent layers rewrite Lori's output after generation. Each was added
to fix a real incident. **None was measured against the others.** Stacked, they
rewrite the majority of what she says, and in the captured cases they replace
good sentences with worse ones.

| Layer | Fires | % of 393 turns |
|---|---:|---:|
| `comm_control` rewrite | **229** | **58%** |
| `reflection-shape` | 146 | 37% |
| witness receipt validator FAIL | 77 | 20% |
| `era-fragment-repair` | 47 | 12% |
| `response-guards` | 35 | 9% |
| `trim-to-one-q` | 19 | 5% |

`comm_control` alone shortened 110 replies from **7,075 words to 3,935 — 45%
of Lori's words deleted**. Worst single cuts: `99→6`, `122→23`, `215→112`.

**Every guard here was tuned on a small sample: Kent's TEST-B/C/G, and the
2026-06-17 five-narrator family run.** The ten-narrator / seven-era cohort is
the first broad sample this system has had, and it was taken *after* the guards
were in place — so it measured the guards, not Lori.

**Phase 1 is therefore observation, not repair.** Nothing below is to be
changed until we can see what she writes versus what reaches the narrator.

---

## PHASE 1 — Instrument before touching anything

### 1.1 Capture `before` at every layer

Each layer already logs a decision; only some log the text. Add structured
capture of `before` / `after` for all nine, keep emitting `after` so no
narrator ever sees unguarded text, and write both to the run report.

This is read-only with respect to behaviour. It is the thing none of these
guards has ever had.

### 1.2 Use Chris's Walt seven-era harness as the instrument

`Walt-Seven-Era-UI-Bundle.zip` (2026-08-31) is the right vehicle and should be
installed as-is:

- `scripts/ui/run_walt_seven_era_conversation.js`
- `tests/test_walt_seven_era_conversation.py`

It already opens Walt by journaled UUID, refuses on an ambiguous journal,
creates no narrator, deletes nothing, clicks all seven real Life Map era
buttons plus **Continue**, types through the real composer, records
`era shown` vs `era sent`, and — item 9 — reads a conversation-scoped
`api.log` delta and counts shaping signals.

**Extension needed** (small, and the raw lines are already retained in
`logEvidence.lines`, so this is parsing, not new capture):

1. Split `[comm_control]` into `changed=True` vs `validate-only` — currently
   counted together.
2. Parse `before_words` / `after_words` into a per-run **word-loss total**.
3. Parse `before=` / `after=` pairs from `validator FAIL` and
   `[response-guards] fired=` into structured before/after fields.
4. Add counters for `reflection-shape`, `trim-to-one-q`, `era-fragment-repair`,
   and `[witness][deterministic] type=`.
5. Record `prompt-budget kept_turns` / `dropped_turns` per turn.

Acceptance for Phase 1: a run produces, for every turn, what the model wrote
and what the narrator received, with the responsible layer named.

---

## PHASE 2 — The layers, in evidence order

### L1. Witness receipt validator — wrong gate, and floors that punish brevity

`lori_witness_mode.py:1626` · gate at `chat_ws.py:5656`

```python
def validate_witness_receipt(..., min_words: int = 35, max_words: int = 110,
                             max_questions: int = 1, min_facts: int = 3)
```

```python
if (_witness_use_llm_receipt
    and _witness_detection_for_fallback is not None   # ← detection, not mode
    and final_text):
```

**Gate:** `_detect_we(user_text)` returning anything. `turn_mode` is never
consulted. Detection counts:

| detection | fires |
|---|---:|
| `STRUCTURED_NARRATIVE` | **109** |
| `META_FEEDBACK` | 8 |

**93% of this gate's firings are on ordinary storytelling**, not on the
meta-feedback case it was built for. In a system whose interview default IS
`oral_history`, structured narrative is the normal turn.

**Floors:** `min_words=35` rejects a 17-word question. `min_facts=3` rejects a
one-fact reflection. Failure reasons across 77 FAILs:

| reason | count |
|---|---:|
| `too_short` | 62 |
| `too_few_facts` | 48 |
| `forbidden_token` | 9 |
| `too_long` | 1 |
| `first_person_mimicry` | 1 |

**110 arithmetic rejections against 10 content rejections.** The guard is
mostly enforcing a word count.

**Captured harm:**

```
before='New York marked a significant departure from Minnesota for you. …'
after ="Let and After — there's a lot held in that. …"
```

**Fix:** gate to the designed mode (or justify `STRUCTURED_NARRATIVE` staying —
see §4); recalibrate both floors against real narrator turns; on failure
**regenerate once** under a corrective instruction before substituting.

**Do not delete.** Origin: `BUG-LORI-WITNESS-RICH-RECEIPT-01 (2026-05-10)`,
fixing a thin template on Kent's TEST-B/C/G. Fail-closed on exception stays.

### L2. `forbidden_token` list — one narrator's vocabulary, matched as substrings

`lori_witness_mode.py:1531`

```
scenery · sights · sounds · smells · sensory · how did that feel
must have been · camaraderie · teamwork · culture among
sense of duty · pivotal · resilience
```

`sounds` is **4 of 9 fires**, and the captured case is the ordinary verb:

> *"Today is a Tuesday, and you're sharing a quiet morning with Catherine.
> **It sounds peaceful.**"* → `forbidden_token:sounds`

`camaraderie` / `teamwork` / `sense of duty` are the vocabulary of a military
service story — Kent's. Applied to Walter's **math team** it killed a good
question and substituted a worse one.

**Fix:** this is a style blocklist, not a safety check. Word-boundary matching
at minimum; better, drop the generic-noun entries and keep only the stock
emotional probes (`how did that feel`, `must have been`).

### L3. `first_person_mimicry` — KEEP, but delete the hardcoded biography

`lori_witness_mode.py:1542`

```
"we were in germany", "we were in kaiserslautern",
"i contacted janice", "i contacted my fiancée",
```

**Kaiserslautern and Janice are hardcoded into a general-purpose validator.**
One narrator's posting, one narrator's wife.

The *check* is protecting something real — Lori adopting the narrator's first
person puts words in the narrator's mouth in the memoir source, and its comment
names the incident (Kent K10/K11, *"we were in Germany"* / *"our son"*). **Keep
the check.** Replace the biography-specific strings with a general
first-person-plural-past-action rule.

### L4. `comm_control` — 58% of turns, 45% of words

Reasons across 229 rewrites:

| reflection reason | count | | atomicity reason | count |
|---|---:|---|---|---:|
| `echo_not_grounded` | 128 | | `and_pivot` | 27 |
| `missing_memory_echo` | 67 | | `or_speculation` | 18 |
| `echo_too_long` | 35 | | `hidden_second_target` | 9 |
| `echo_contains_diagnostic_language` | 10 | | `dual_retrieval_axis` | 4 |

| failure | count |
|---|---:|
| `response_stub_collapse` | 39 |
| `too_many_questions` | 37 |
| `too_long` | 32 |

The atomicity cut leaves fragments — *"The idea of finishing what you started
is still."* A 49-word reply became 10.

**Fix:** atomicity should split or re-ask, never truncate mid-clause. Any cut
that leaves a sentence without terminal punctuation is a bug.

### L5. `trim-to-one-q` — lengthens 16 of 19 times

```
[lori][discipline] trim-to-one-q reason=compound before_len=185 after_len=229
```

**19 fires, 16 made the reply longer.** A trimmer that lengthens 84% of the
time is not doing its job. Straightforward bug, independent of calibration.

### L6. `reflection-shape` — the anchor picker leaks stopwords and truncates names

`lori_reflection.py:784`

| action | fires |
|---|---:|
| `shaped_echo_dropped` | 77 |
| `shaped_echo_trimmed_to_anchor` | 39 |
| `shaped_anchor_prepended` | 30 |

Observed anchors: `"Let and After"` (from the narrator's own *"**Let**'s move
… **After** high school"*), `"Paul and For"`, `"For and They"`,
`"Seoul and Min"` (`Min` truncating **Min-Jung**), `"Saint Patrick to Day"`
(splitting *Saint Patrick's Day*).

The file's own LLR-21 note records the same class of failure already:
`"Peter Zarr. are laid to rest there."`

**Fix:** stopwords can never be anchors; names are never truncated;
`shaped_echo_dropped` at 77 fires needs justifying — it is discarding Lori's
reflection on 20% of turns.

### L7. `response-guards` — replacing good sentences with stubs

| guard | fires |
|---|---:|
| `language_drift` | 22 |
| `meta_response_leak` | 5 |
| `dangling_determiner` | 3 |
| `sensory_pivot_on_chain` | 2 |
| `broken_code_mix` | 2 |
| `narrator_echo` | 1 |

```
fired=language_drift
  before='Tu papá Roberto trabajaba en la industria del ferrocarril,
          cruzando la frontera todos los días. ¿Te recuerdas algo espec…'
  after ='Disculpa, continuemos. ¿Qué te gustaría contarme ahora?'
```

```
fired=dangling_determiner
  before="The idea of being connected to both sides, and yet, not fully
          belonging to either side - that's a complex identity, Toma"
  after ='Sigamos con eso. ¿Qué pasó después?'
```

Both `before` strings are better than both `after` strings.

### L8. Language contract — `prior_es_index` never clears

```
guard_target=es user_es=True  prior_es_index=-1   ← flip
guard_target=es user_es=False prior_es_index=0    ← stuck
guard_target=es user_es=False prior_es_index=0    ← still stuck
```

Triggered by `[lang-contract] unset profile pin; looks_spanish advisory routed`
on a turn that was **37 of 41 words English**, where the narrator had
translated her own Spanish sentence in the same breath. A narrator cannot
return to English by speaking English.

**Fix:** `prior_es_index` must decay; a fully-English turn must clear it.

### L9. Prompt budget — she is not being allowed to remember

```
[prompt-budget] reason=trimmed tokens=8128 limit=8192
                kept_turns=2 dropped_turns=5
```

Across 33 trims: **`kept_turns` mean 0.3, min 0, max 2. 86 turns dropped.**

On a trimmed turn Lori frequently has **zero** conversational history. Every
"she repeated the question" and "she ignored what he said two turns ago"
finding in the review has this as its mechanical cause.

**The 8,192 window is LOCKED and is not in scope.** What is in scope: a
20,523-char extraction system prompt and 6,300–8,100-token composed prompts
leaving nothing for the conversation. Budget the composed prompt so history
survives.

### L10. Buffered streaming — a UX consequence, recorded not fixed here

`witness][buffered-stream] tokens buffered server-side; emitting only validated
final via done event`. Correct given the validators exist, but it means the
narrator waits for full generation with no token stream. Revisit only after
the layers above settle.

---

## 3. Ordering

1. **Phase 1 instrumentation** — nothing else starts first.
2. **L5** `trim-to-one-q` lengthening — isolated, unambiguous, no calibration.
3. **L3** delete hardcoded biography, keep the check.
4. **L8** `prior_es_index` decay — a narrator locked out of their language.
5. **L1** gate + floors + regenerate-before-substitute.
6. **L6** anchor stopwords and name truncation.
7. **L2** blocklist word boundaries / pruning.
8. **L4** atomicity split-not-truncate.
9. **L9** prompt budget rebalance.
10. **L7** re-evaluate once L1/L4/L6 have moved — some of these fires may
    disappear when the upstream layers stop mangling text.

## 4. Decisions for Chris — not the agent's to make

1. **Should `STRUCTURED_NARRATIVE` route to the witness receipt path at all?**
   109 of 117 detections. If a narrator telling a structured story is exactly
   when a receipt matters, the gate stays and only floors and repair change.
2. **What is the target reply length for a narrator-facing turn?** Dense-run
   mean was 28 words; `min_words` is 35. These contradict, and one of them is
   wrong.
3. **On validator failure: regenerate, substitute, or pass through with a
   flag?** Substitution is current behaviour and is demonstrably lossy.

## 5. Standing prohibitions observed

Model and 8,192-token window LOCKED and untouched. Runtime safety PARKED and
untouched. No narrator created or deleted by any work in this WO. Extraction,
the field whitelist and JSON truncation are the extractor lane and are excluded.
Spanish canonical questions remain deferred.
