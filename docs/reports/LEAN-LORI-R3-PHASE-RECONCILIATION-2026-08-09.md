# Lean Lori R3 — phase reconciliation against current `main`

**Date:** 2026-08-09 · **HEAD:** `a217051` · **Method:** requirement-by-requirement trace to
code, tests, reports and the commit reflog. **No product code was read-modified; this is a
reconciliation, not an implementation.**

**Governing caution honoured throughout:** correspondence was **not** inferred from
similarly-named commit phases. Where a commit says `Phase 4A` and R3 says `Phase 4`, they are
different things, and the mapping below is derived from what the code actually does.

---

## 1. The headline finding: R3's phase numbers and the commit phase numbers are two different schemes

They overlap, they collide, and reading either as the other produces wrong conclusions in
both directions. The implementation ran its own numbering, and the code records it in
comments — `prompt_composer.py:3316` literally says `WO-LEAN-LORI-RUNTIME-01 Phase 2D`, on
work that is **R3 Phase 4**, not R3 Phase 2.

| Commit / code label | What it actually did | R3 phase it satisfies |
|---|---|---|
| `Phase 1A`–`1E` | as named | **R3 1A–1E** — the one range where labels *do* correspond |
| `Phase 2A` | named prompt sections, byte-identical output | **R3 Phase 4** |
| `Phase 2B` | removed `PROFILE_JSON.last_user_text` | **R3 Phase 5** |
| `Phase 2C` | split chat window from extraction window | *no R3 phase* — an enabling change for R3 9/11 |
| `Phase 2D` | `required` / `drop_order` classification | **R3 Phase 4** (attributes) + prep for R3 9 |
| `Phase 3A` | classifier stopped carrying the composed prompt | inside **R3 §3C** |
| `Phase 3B` | **parked the safety feature** | **R3 §3C** — *not* R3 §3B, which is speech |
| `Phase 4A` | `prompt_budget.py`, killed the blind slice | **R3 Phase 10** + partial **R3 Phase 9** |

**R3 §3C states this itself** (*"Implemented as Phase 3B"*), so the collision is recorded —
but only in one direction, and only in one place.

**Worse, the labels are not unique across the repository.** `ui/js/narrator-intake.js` carries
`Phase 2B` / `Phase 2C` belonging to `WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01`, and
`ui/js/travel-doc-lab.js` carries `Phase 3A` belonging to the Travel Doc unification. **A bare
phase label is not an identifier in this repository.** Any future status claim should cite a
commit or a file, not a phase number.

**The 2026-08-09 assessment said "Phase 2A–2D landed" as if against R3.** Those commits are
real, but they satisfy **R3 Phases 4 and 5**, and **R3 Phase 2 has not been started at all.**

---

## 2. Status by gate

Legend: **LV** landed-and-verified · **LLA** landed, live acceptance owed · **PL** partially
landed · **SUP** superseded · **PARK** parked by decision · **NS** not started · **NLA** no
longer applicable.

### Gate A — review and bug search — **LV**

| R3 requirement | Implementation / evidence | Commits | Status |
|---|---|---|---|
| 0.1–0.6, 0.8–0.10 baseline, review, runtime reconstruction, prompt + resource review, deliverable | `docs/reports/LEAN-LORI-PHASE-0-REVIEW-2026-08-04.md` (58 KB); `lean_lori_phase0_run_summary.txt` (31 KB) | `4da079a` closed Phase 0 | **LV** |
| 0.7 live LLM-safety efficacy and cost gate | `lean_lori_safety_gate.json` (213 KB, 192 cases); `lean_lori_safety_corpus_2026-08-04.json` | `4bf224a`, `be4115c` | **LV** |
| Durable outputs | TTS-aware testing rule + stale-`__pycache__` hazard, both now in `CLAUDE.md` | `4da079a` | **LV** |

**Remaining: none.** Gate A produced the safety-park decision as its own output.

### Gate B — core-function restoration — **LV on four, LLA on one**

| R3 phase | Implementation | Commit | Tests | Status |
|---|---|---|---|---|
| 1A deterministic turn finalization | `chat_ws.py` (marker `Phase 1A, 2026-08-04`) | `082d3cc` | counts/order assertions | **LLA** |
| 1B apostrophe person-anchor | `services/story_trigger.py` (marker `Phase 1B`) | `c155719` | `test_story_trigger` | **LV** |
| 1C remove bounded-extraction pre-generation | `api.py` (`Phase 1C guard`), `routers/extract.py` | `c6d0fdf` | extraction suites | **LV** |
| 1D safety-latch exit | browser posture latch | `85c1bd6` | precedence suite | **LV**, acceptance **amended** |
| 1E compound-value reflection trim | `services/lori_reflection.py` | `385c71d` | Patch C cases A/B/C1/C2/D | **LV** |

**1A is the one with owed evidence.** R3 requires *"a browser/export smoke proving each
delivered deterministic reply appears exactly once."* No such smoke is recorded.

**1A also covers six branches, not the five R3 named** — `floor_hold`, **`meta_question`**,
`witness`, `memory_echo`, `age_recall`, `correction`. See §3.

**1D is landed and its acceptance criterion was replaced**, not dropped: Gate F now asks that
the posture *cannot arm while parked*, and R3 keeps the exit in code deliberately *"because it
is what reactivation lands on."* **Do not delete it as dead code.**

### Gate C — feature profile — **one PARK, three NS**

| R3 phase | Status | Detail |
|---|---|---|
| **2 — profile resolver `HORNELORE_RUNTIME_PROFILE=lean_lori`** | **NS** | **Zero occurrences of `HORNELORE_RUNTIME_PROFILE`, `lean_lori` or `effective_profile` anywhere in `server/` or `ui/`.** |
| 3A camera / preview / browser affect | **NS** | no parking seam exists |
| 3B speech (Whisper, one STT lane, `/api/stt/status` passive) | **NS** | **the commits labelled `Phase 3B` are the safety work, not this** |
| **3C safety disposition** | **PARK + LV** | `flags.py:260` `HORNELORE_SAFETY_STATE`, default `parked`; seams in `safety.py`, `safety_classifier.py`, `chat_ws.py`, `interview.py`, `ping.py`, `safety_events.py`; `tests/test_safety_parked.py` **54 tests** |
| 3D optional Llama / derivative work | **PL** | "one bounded extraction is one LLM call" landed via 1C; the rest of the family is ungated |

**The structural finding of this reconciliation:** R3 wrote Gate C so that every parking
decision hangs off the Phase 2 resolver — *"When `lean_lori` is effective: …"*. **Phase 3C was
implemented without the resolver**, through a dedicated `HORNELORE_SAFETY_STATE`. That was the
right call for a decision that needed to land the same day, and it is server-authoritative and
well tested. But it means **R3's stated dependency is now false**, and a future 3A or 3B must
either build the resolver first or add a second bespoke setting. That is a decision, not an
oversight, and it is Chris's.

`HORNELORE_SAFETY_STATE` is **absent from `.env`**, so it takes its `parked` default. Correct,
and worth stating: parked is the behaviour of a machine nobody configured.

### Gate D — prompt architecture — **the live gate**

| R3 phase | Status | Detail |
|---|---|---|
| 4 structured composer | **PL** | `_PromptAssembly` / `_Section` in `prompt_composer.py:3288`. R3 asked for **nine** per-section attributes; the code has **four** (`name`, `text`, `required`, `drop_order`). Token counts are **deliberately absent** with a documented reason: the only honest count is post-`_apply_chat_template`, and a builder-side estimate *"was wrong by a wide margin."* Missing: priority tier, feature owner, activation condition, trim policy, source, redacted hash. Four-narrator production-fixture acceptance not evidenced. Tests: `test_prompt_sections` **36**. |
| 5 remove duplicated current-turn text | **LV** | `last_user_text` survives only inside its own retirement comment. It was write-only: one reference repo-wide, no reader. |
| 6 compact `default_core` | **NS** | `DEFAULT_CORE` explicitly **unchanged** (`prompt_composer.py:3213`); it was only *split* for the safety marker under Phase 3B. LLR-19 unproven. |
| 7 compact English-first | **NS** | `[ENGLISH_FIRST_RULE]` still emitted at `prompt_composer.py:3579` |
| 8 split directives by active state | **NS** | no state matrix anywhere |
| 9 real-token budget | **PL** | `services/prompt_budget.py`, `test_prompt_budget` **22 tests**. Landed: system message untouchable, history dropped oldest-first at turn-pair boundaries, `mandatory_too_large` refuses. **The module names its own gap** under `NOT IN THIS PHASE`: optional SYSTEM sections are *classified but never dropped*. Also missing: priority tiers, section ID/count/decision/hash reporting. |
| 10 remove blind slicing from every chat path | **LLA** | **all three paths covered** — `chat_ws.py:4216`, `api.py:639` (`rest-chat`), `api.py:771` (`rest-stream`). The old front-slice is replaced by backstops that **refuse** (`PROMPT_TOO_LARGE`) rather than cut. Live acceptance across R3's case list not recorded. |

**Phase 9 ran before Phases 6–8, which R3 forbade** (*"Do not start until required sections
plus realistic current-turn context fit"*). Recording it as **SUP-ordering, deliberate**: the
front-slice was destroying Lori's identity on **382 of 630 measured turns** in production, and
`prompt_budget.py` argues the inversion explicitly — *"a phase that fixes the live defect is
worth more than a phase that fixes it more elegantly later."* That reasoning holds. It does
mean R3's ordering constraint should be marked retired rather than silently violated.

### Gate E — extraction and diagnostics

| R3 phase | Status | Detail |
|---|---|---|
| 11 preserve bounded extraction, reconcile contracts | **PL** | Window split landed (`extraction_budget.py`; `test_extraction_prompt_budget` **42**, `test_context_window_split` **19**). **The 384-vs-768 compound cap is already reconciled** — see §3. Remaining: the explicit post-profile reconfirmation sweep. |
| 12 passive diagnostics and truthful surfaces | **PL** | `/api/extract-diag` passive via 1C; per-turn section log moved to DEBUG + explicit opt-in (`363da00`). The operator manifest R3 specifies — requested/effective profile, camera state, STT/TTS lanes — **depends on Phase 2 and is NS**. |

### Conditional follow-up — coordinator — **NS, correctly**

R3: *"If no direct collision evidence exists, do not build it."* None exists. **Do not open.**

### Gate F — final acceptance — **NS**

Not startable: it asserts a `lean_lori` manifest (Phase 2) and parked camera/Whisper
(3A/3B), none of which exist.

---

## 3. Requirements already satisfied elsewhere — do not rebuild these

This is the highest-value section of the reconciliation.

1. **`meta_question` exactly-once, extraction- and placement-ineligible** — a Gate F criterion,
   satisfied by **`7139644`**, *"fix(chat_ws): stop meta_question opening the completed-turn
   hooks"*, which lands **before `b5dc03f`** — i.e. **before R3 was written.** The Phase 1A
   comment records it as already repaired on 2026-08-01 under
   `BUG-DETERMINISTIC-TURN-ARCHIVE-MISSING-01`.
2. **Six-word trip-story floor and reason ordering** — a Gate F criterion, satisfied by
   **`09de0dc`**, *"raise the meaningful-word floor 3 → 6; question check first"*, also pre-R3.
3. **The 384-vs-768 compound cap** (R3 Phase 11) — **already one source of truth.**
   `extract.py:1962` defaults to `768` with the reason recorded at `:1956`: LOOP-01 R3 raised
   it after api.log evidence showed truncation at 384. Reconciliation work, not a rebuild.
4. **Extraction idempotency ledger, strong task references, shutdown drain, catch-up** (R3
   Phase 11 says *preserve*, not build) — landed 2026-07-30 under **WO-TRUTH-PIPELINE-01
   Phase 2**, migration `0038`, `services/turn_extraction.py`.
5. **Archive-before-extraction ordering** (Phase 11) — asserted by `0d87717`.
6. **WO1E** — closed 2026-08-04 (`9b92b57`, `b5dc03f`). R3: *"WO1E is not repeated."*

---

## 4. Model and window locks — **UNCHANGED, verified**

| Locked item | Observed |
|---|---|
| Model | `MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct`, `MODEL_PATH=/mnt/c/models/hornelore/Meta-Llama-3.1-8B-Instruct` |
| Quantization | `load_in_4bit=True` (`api.py:240`) |
| Device map | `device_map="auto"` (`api.py:250`) |
| Window | `MAX_CONTEXT_WINDOW=8192`; both derived windows default to `8192` (`api.py:107`, `:112`) |
| Serving backend / chat template | unchanged |

One observation, not a violation: `.env` still sets only the legacy `MAX_CONTEXT_WINDOW`, so
it governs **both** windows through the documented deprecation fallback. `api.py:121` already
prints a deprecation line. Setting `MAX_CHAT_PROMPT_TOKENS` and
`MAX_EXTRACTION_CONTEXT_WINDOW` explicitly would make the split real rather than latent —
**and would not change either value**, so it is not a window change.

---

## 5. The question this block was opened to answer

> **What is the smallest unfinished Lean Lori block that actually improves Lori next?**

**Answer: R3 Phase 6, then Phase 7 — compaction — preceded by one measurement.**

The reasoning is a direct consequence of Phase 4A rather than a preference. Before 4A, an
over-window turn cut the **front** of the prompt: Lori lost her identity and instructions, on
382 of 630 measured turns. After 4A she keeps them — and the cost moves to the **history**,
which is now dropped oldest-first instead. **The failure changed shape; it did not go away.**
Lori no longer forgets who she is; on a long session she forgets what the narrator just told
her, which for an oral-history system is the second-worst failure available.

Compaction is the only work that reduces how often history has to be dropped at all. Phase 6
(`DEFAULT_CORE`) and Phase 7 (the always-on English-first library, ~849 tokens by R3's own
count) are the two largest always-on blocks, and neither has been touched.

**Do the measurement first, and it is nearly free.** `BudgetOutcome` already reports
`dropped` and `total_turns`. One log line, or one pass over existing logs, answers *how many
production turns currently drop history, and how many pairs*. That number decides whether
compaction is urgent or merely tidy, and R3 forbids inventing thresholds from the May report.

**The competing candidates, and why they lose:**

- **Phase 9 completion** (drop optional sections whole) helps only in the extreme case that
  history alone was not enough — strictly narrower than compaction.
- **Phase 2 resolver** is infrastructure; it improves no narrator turn. Real, but not next.
- **3A/3B parking** saves VRAM. The measured envelope already showed idle 5.9 GB against a
  hypothesised 8–9 GB, so this is not currently the binding constraint.
- **`WO-SYSTEM-DIRECTIVE-PERSISTENCE-01`** is a *correctness* fix, not a conversational
  improvement. It is small, well-specified and blocked only on Chris's §5 ruling — a good
  candidate to run **alongside** the measurement, since they touch different files.

---

## 6. Proposed status changes — NOT APPLIED, held for review

### R3 document

1. Replace the interim "treat every phase marker as unverified" paragraph in the 2026-08-09
   status block with the §2 table above.
2. Add the §1 mapping table near the top, and the warning that **phase labels are not unique
   across this repository**.
3. Mark **Phase 9's ordering constraint retired**, quoting *"Do not start until required
   sections plus realistic current-turn context fit with measured headroom"* and recording
   that Phase 4A inverted it deliberately against a live production defect.
4. Note in **Phase 2** that Gate C's *"When `lean_lori` is effective"* framing was bypassed for
   3C by `HORNELORE_SAFETY_STATE`, so 3A/3B inherit a decision.
5. Note in **Phase 1A** that six branches were repaired, not five, and that `meta_question`
   was already repaired pre-R3.
6. Record the **owed live acceptance** on 1A and Phase 10.

### `MASTER_WORK_ORDER_CHECKLIST.md`

7. Under head-of-queue item **0a**, replace *"reconcile the remaining phases"* with the
   outcome: Gates A and B complete bar one smoke; Gate D is the live gate; **Phase 2 is not
   started**; next block is measure-then-Phase-6/7.
8. Add the §3 do-not-rebuild list so it survives outside this report.

### `CLAUDE.md`

9. In the state table, refine Lean Lori from *"advanced through Phase 4A"* to
   *"Gates A + B complete (one smoke owed); Gate D active; R3 Phase 2 not started"* — the
   current wording repeats a commit label the §1 table shows to be ambiguous.

---

## 7. Caveats on this reconciliation

- **Commit trail read from `.git/logs/HEAD`**, since git tooling does not run in the sandbox.
  That reflog gives subjects and hashes but **not diffs**; every status above was therefore
  confirmed against the *code*, and commits are cited for provenance only.
- **No test was executed for this report.** Counts are `def test_` counts, which measure
  coverage breadth, not passing state. A green run is Chris's `.venv`.
- **Live acceptance was not attempted.** Items marked LLA are code-verified only.
- Statuses for R3 Phase 4's four-narrator fixture acceptance and Phase 12's operator manifest
  are inferred from **absence of evidence**, which is weaker than the rest of this document
  and is flagged as such.
