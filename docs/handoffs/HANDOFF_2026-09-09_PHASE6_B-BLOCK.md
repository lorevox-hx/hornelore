# HANDOFF — Phase 6, B block complete, C block next

**Written 2026-09-09.** For picking Phase 6 up on another machine.
**Authority order is unchanged:** current code > current tests and live
evidence > accepted closeout records > `HANDOFF.md` > this file.

**Read first:** `CLAUDE.md`, `HANDOFF.md`,
`docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md`,
`docs/wo/WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01_Spec.md`,
`docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02_PHASE6-BASELINE-PROTOCOL.md`.

---

## 1. Do not reopen

* **Repository hygiene** — COMPLETE at `e0fde84`.
* **Kawa / Memory River** — REMOVED, `WO-KAWA-REMOVAL-01` complete.
* **Blocks A, B, C and Phase 5C** — DONE.
* **The 85/85 mutation gate** is the accepted acceptance-only baseline. Day
  to day run focused tests plus the family protecting the changed file.
* **Profile Seed**, the `test_profile_seed_reachability_map` line-number
  pinning defect, Test 23 RED and the WO-10C pytest-only issue are separate
  recorded debts. Do not divert into them.

**The block sequence is A–F. There is no Block G**; the "D/G" shorthand is
retired. D = Phase 6, E = Phase 7, F = Phase 8. Phase 6's own cohort arms
are separately labelled A/B/C (Lean / Defaults / All-on) — a different
alphabet from the Blocks.

---

## 2. State: Phase 6 is UNDERWAY

Captured before this session: Run 1 (rejected as a baseline), Runs 2–4 on
the populated narrator, and the A/B/C cohort. Landed before this session:
`ee7063c` (server-resolved identity outranks the browser) and `49c219c`
(a completed walk never sees the legacy list).

### What this session added

| | |
|---|---|
| **A1** | Corrected the malformed-anchor attribution in `docs/BACKLOG.md` and `docs/archive/INDEX.md` |
| **A2** | Recorded the two landed interventions; cleared the stale "Phase 6 is next" lines in four documents |
| **A3** | Built the Run 4 human-review worksheet, deliberately UNSCORED |
| **B1** | ids 30, 31, 47 now leave trace evidence on every turn |
| **B2** | The correction-route question is CLOSED on live evidence |
| **B3** | A six-shape correction canary batch under one frozen configuration |

---

## 3. The attribution correction — carry this forward

The record said Guard Lab **id 40** produced all three malformed strings.
The cohort-C response trace says **two** authorities produce two different
shapes:

| Stage | Shape | Turns of 38 |
|---|---|---|
| `witness_receipt_fallback` — **id 48** | `"X and Y — there's a lot held in that."` | 17 |
| `cc_40_chain_anchor_opener` — **id 40** | `"From A to B to C — "` | 16 |

On the `"West St and Paul"` turn **id 40 never fired**;
`witness_receipt_fallback` was the only stage that changed text. Id 40's own
registry entry at `lori_guard_registry.py:577` already called that example
"downstream", correctly.

**The defect is upstream of both:** punctuation-blind proper-noun regexes at
`factual_chain_capture.py:74` and `lori_structured_narrative_fallback.py:44`.
Neither character class admits `.` or `'`, so `"West St. Paul"` yields
`['West St', 'Paul']` and `"Saint Patrick's Day"` yields
`['Saint Patrick', 'Day']` (verified by execution).

**They are mirrored deliberately and are NOT identical** — `factual_chain_capture`
caps phrases at three words (`{0,2}`) and filters through `_BAD_ANCHOR_TOKENS`;
`lori_structured_narrative_fallback` caps at four (`{0,3}`) and filters through
`_CASCADE_FILTER_TOKENS`. `factual_chain_capture.py:71-73` records that the
mirroring is intentional and that the module stays independently auditable.

---

## 4. B1 — what landed, and the rule it encodes

Ids 30, 31 and 47 previously wrote no trace stage at all, so
**"selected, ran, found nothing" and "never ran" were byte-identical**. For
id 47 it was worse in kind: a validator that PASSED and one never selected
both left `_wr_ok=True` and no trace, so its verdict could only be inferred
backwards from whether id 48's fallback stage appeared — which cannot
separate *judged and approved* from *nobody judged*.

**Four facts, none inferred from another:** `selected` / `evaluated` /
`eligible` / `fired`. "No text changed" is deliberately not enough — a
detector never reached and one run against an empty corpus must not read the
same, and a test fails if a future edit derives `eligible` from `evaluated`.

**A validator fires when it REJECTS.** Id 47 never writes text, so its
`before` and `after` are equal and `changed` is always false. The
replacement belongs to id 48. Conflating those is what produced the original
misattribution.

Tests: `tests/test_phase6_authority_observability.py` — **7 tests, 0 skips**,
verified on `.venv`. The structural half is an AST guard because `chat_ws`
imports `transformers` and cannot load in the agent sandbox; it fails if a
stage is ever nested inside a "did the text change?" branch. **4 mutations
run, 4 caught, 0 broken**, product restored byte-identical.

**Zero narrator-behaviour change.** `final_text` assignments untouched; the
id-47 change only names the existing entry condition as a boolean.

---

## 5. B2 + B3 — the correction route is CLOSED

**Evidence (local working copies only; `.runtime/` and `docs/reports/` are
gitignored, so these are plain text, not links):**
`.runtime/eval/phase6-b2-correction-route-20260908/`

**The first attempt was INCONCLUSIVE and the reason matters.** Under Lean,
id 26 — the correction ROUTE — is excluded, so the Guard Lab clamp reset the
proposed `correction` before the parser was ever consulted. Lean removes the
very route being measured. `requested=correction, effective=interview,
generated=True` has two possible causes and they are not the same finding.

**Run 4 turn 6 is SUPERSEDED as proof of parser fallthrough** for the same
reason — same Lean configuration, id 26 excluded.

**The answering configuration is Lean + id 26 only** (revision 13, selected
`[20, 26, 49, 52, 53]`). Nine model turns plus one deterministic turn, one
narrator, one process, one revision. **`raw == delivered` on every generated
turn; zero words removed; no stage changed text.**

| Narrator said | proposed | parser | effective | model |
|---|---|---|---|---|
| *it wasn't the same after that* | correction | `{}` | interview | ran |
| *We used to drive up to Groton Pond…* | interview | — | interview | ran |
| *It was not a big house, but we managed.* | correction | `{}` | interview | ran |
| *…green glass dish…, not that it matters.* | correction | `{}` | interview | ran |
| *It wasn't the same after we moved to Lowell in 1961.* | correction | `{}` | interview | ran |
| *Actually, I was born in Lowell, not Boston.* | correction | **non-empty** | **correction** | **bypassed** |
| *Actually, I finished school in 1969, not 1968.* | correction | `{}` | interview | ran |

**Verdict: the server boundary holds.** Five false-positive browser
proposals were rescued by the parser returning empty; the one genuinely
actionable correction took the deterministic path as designed. **A broad
browser regex that the server resolves is not a defect — no `app.js` change
is warranted on this evidence.**

Instrument: `scripts/phase6_correction_route_probe.py`, read-only. It
refuses a wrong-arm turn, and it reads the parser outcome from the server
log rather than inferring it from the turn's outcome — the first version
did infer it, and was wrong.

---

## 6. Three findings recorded, NOT acted on

1. **Lori claims words she never said.** The deterministic correction
   template delivered *"Got it — born in Lowell. Thanks for catching that —
   I shouldn't have said Boston.."* Lori never said Boston; the narrator
   introduced it. The template assumes the retracted value came from Lori.
   For a narrator with memory difficulty, being told the system said
   something it did not is a dignity problem, not a cosmetic one. The
   doubled period comes from the parser capturing `'Boston.'` with the
   sentence-final period — the same punctuation-blindness family as §3, in
   a different parser.

2. **The deterministic correction turn is traced but unjoinable.** Its
   record carries `turn_key: ''`, `narrator_input: None`, **zero stages**,
   and every storage lane `not_measured — "no instrumentation attached this
   stage"`. The Guard Lab spec records the deterministic-path trace gap as
   CLOSED; a record now exists, but it carries nothing joinable to a ledger
   row or an utterance. Same family as item 3.

3. **The no-op trace stub lacks `bind_turn_key`.**
   `tests/test_lori_response_trace.py::DefensiveStubTests` fails at HEAD for
   this reason — *"an import failure would hit a missing method, be
   swallowed, and silently produce no trace"*. **Pre-existing**, confirmed
   identical on a pristine `git archive` of HEAD. The stub does define
   `stage(*a, **k)`, so B1's calls are safe.

**Also observed:** restoring Lean was refused with a **409** — *"you were
looking at revision 12; the live configuration is revision 13"* — then
adopted. That is one of the four banked Guard Lab acceptance checks
behaving correctly on a real browser. It was **not** the specified two-tab
procedure, so the clause is **not** claimed closed.

---

## 7. Pre-existing failures — do not chase

All three verified identical on a pristine `git archive` of HEAD:

* `test_lori_response_trace` — stub lacks `bind_turn_key` (§6.3)
* `test_phase6_baseline_turnset` — `test_the_shipped_router_preflight_passes_on_this_set`
* `test_walt_seven_era_conversation` — `StartAllPropagatesTheFlagTests`, 2 failures

A pristine tree has no `.env` (gitignored), so its `.env` precedence test
skips where a real working tree runs it. That skip difference is an artifact
of the extraction, not a regression.

---

## 8. NEXT: Block C — the malformed-anchor repair

**Authorized 2026-09-08.** It is measured narrator-facing fabrication from
existing deterministic machinery; it does not need another live cohort to
prove it is wrong. **Stack DOWN for this** — the stored cohort
counterfactuals and production-boundary tests prove it without a live run.

**Fix BOTH local extractors consistently. No shared-helper refactor** — the
current design deliberately keeps them independently auditable.

Narrow the repair to punctuation *inside proper-name structure*, not a
general loosening:

* an apostrophe inside a capitalized token — `Patrick's`, `O'Connor`;
* a known abbreviation such as `St.` **when it immediately continues into
  another capitalized name token** — `St. Paul`;
* otherwise retain existing phrase-termination behaviour.

**Record, do not solve, the residue:** `We lived on Currier St. Paul visited
that winter` is ambiguous to any regex. Do not grow the parser until it
pretends to understand grammar.

**Pin at both levels.**

Extractor regression: `West St. Paul` · `Saint Patrick's Day` · `O'Connor` ·
an ordinary multiword place · existing filter-token behaviour.

Production boundary, both authority paths: **id 40 cannot manufacture the
split chain opener**; **id 48 cannot manufacture the split
`"X and Y — there's a lot held in that"` fallback**; same for
`Saint Patrick` / `Day`.

**Parity test:** pin the punctuation cases only. **Do NOT assert the two
extractors return identical anchor sets** — their word caps and filter
vocabularies legitimately differ (§3).

Then **counterfactual-replay the stored cohort-C turns** through the
corrected extraction before any new live run.

> **Repairing these extractors does not vindicate ids 40 or 48.** It makes
> their inputs truthful enough that the authorities themselves can be
> evaluated. Phase 6 may still conclude either should default off or
> disappear.

## 9. Then Block D proper — generation-level quality under Lean

Under Lean nothing is removed and Lori is still weak. These are
GENERATION-level, evidenced by `raw_equals_delivered` being true on the
affected turns:

* dropped named relationships and details;
* flattened causal structure;
* unsupported significance and inference;
* generic responses after major disclosures.

Investigation order: **prompt/context composition → model behaviour →
smallest supported change.** **Do not add another deterministic guard to
repair Lean-generation blandness.**

**The human verdict is owed and is Chris's to give.** All four judgement
fields are blank on all 30 turns of Runs 2–4. Worksheet:
`docs/reports/PHASE6-RUN4-HUMAN-REVIEW-WORKSHEET.md` (local working copy
only). **An agent must not fill them** — model judgement labelled human
review is worth less than no verdict.

---

## 10. Machine notes

* **Agents do not run git.** Prepare copy-paste blocks; Chris runs them from
  `/mnt/c/Users/chris/hornelore` and pushes from GitHub Desktop. **Every
  block starts with the `cd`.**
* **A sandbox git command can leave `.git/index.lock` behind** on the 9p
  mount and silently block GitHub Desktop. Symptom: add succeeds, commit
  says nothing to commit, Desktop still shows N changed files. Fix:
  `rm -f .git/index.lock`.
* **Arming order is load-bearing.** `trace_env.sh` resolves tracing at
  process startup, so arm `.runtime/eval/current_eval_dir` BEFORE the stack
  starts and confirm the launcher banner reads `response_trace=1` naming the
  intended directory. `stop_all.sh` disarms on exit.
* **The UI runs at** `http://localhost:8082/ui/hornelore1.0.html`.
* **Driving the UI from a browser agent:** the page reports CSS
  `710×764` while the screenshot frame is `1064×1145` — a **1.4986× device
  pixel ratio**. Convert or every click lands on the wrong element. Measure
  geometry from the page and refuse when a selector matches more than one
  candidate; a loose ancestor walk matched all 39 narrator cards at once.
* **The Bug Panel is a native popover.** Open via `#lv10dBugBtn`, gate on
  `:popover-open`, never `offsetParent`. Its Guard Lab section is collapsed
  by default and its own copy of "All Switchable Off" stays in the DOM after
  closing — disambiguate against `#lv10dBugPanel.contains(el)`.
* **Interpreters:** `.venv` for tests, `.venv-gpu` for the serving stack.
  Report skip counts; `OK (skipped=N)` is not a pass.
