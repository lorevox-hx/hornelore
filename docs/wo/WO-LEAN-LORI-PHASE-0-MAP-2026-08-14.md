# Lean Lori — Phase 0 reconciliation map

> ## ERRATA — 2026-08-17
>
> **L2 has since RUN and is CLOSED PARTIAL by product-priority decision (2026-08-16).**
> Everything below describes the state on 2026-08-14, when L2 was still unopened. It is
> design history now, not a build queue. **Do not read §8's "the stack was not started" as
> current** — it was true of *this map*, and is no longer true of the lane.
>
> Gate B stays OPEN and Phase 10 stays open; the unexercised L2 cases are deferred by
> decision, not failed. Profile Seed ownership is **DECIDED — Option A, live narrators
> only**. Evidence: `docs/reports/WO-LEAN-LORI-L2-PARTIAL-2026-08-16.md` (local-only,
> gitignored). The active lane is
> `docs/wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md`.


**Status:** PHASE 0 RE-REVIEW COMPLETE — 2026-08-14. **Offline only. No product code, no
schema, no migration, no flag change, no stack cycle, no live run.**
**Canonical WO:** `docs/wo/WO-LEAN-LORI-RUNTIME-01-FINAL-R3-2026-08-04.md`
**Binding:** the Phase 0.10 hard stop, the absolute model lock and the 8,192-token window.

---

## 0. The finding that must be read first

**The control documents disagree about whether this lane has started, and the dangerous
direction of that disagreement is the one that invites rebuilding landed work.**

| Document | Claim |
|---|---|
| `HANDOFF.md` (as written earlier today) | *"Implementation has NOT started."* |
| `CLAUDE.md` Lean Lori row | Gate A complete · Gate B complete except one smoke · Phase 2 not started · Gate D active |
| The WO status header | *"ACTIVE — IMPLEMENTATION IN PROGRESS, ADVANCED THROUGH PHASE 4A"* |

**`HANDOFF.md` was wrong and has been corrected in this same commit.** Eleven Lean Lori
production commits are in-tree and their code is live:

```
082d3cc  1A  deterministic turns finalized exactly once
c155719  1B  omitted-apostrophe person anchors
c6d0fdf  1C  one bounded extraction is one LLM call
85c1bd6  1D  browser safety latch has a defined exit
385c71d  1E  compound names survive the anchor trim
53a2cad  5   stop duplicating the narrator's message into PROFILE_JSON
fdda330  4A  stop cutting the front of Lori's prompt
363da00      per-turn section log to DEBUG + explicit opt-in
2829517  6   compact the always-on core        2,217 → 1,632 tok
3065cfc  7   compact the English-first block     850 →   108 tok
ce5e636  8   gate the ERA EXPLAINER glossary   first gate only
```

Because `CLAUDE.md` states that **HANDOFF outranks it**, an agent obeying the documents
literally would have read "implementation has not started" as authority to rebuild all
eleven. That is the exact failure `CLAUDE.md` opens by warning about, and it was introduced
today by the same session that is now correcting it. Recorded rather than quietly fixed.

**Second stale claim, same species.** `docs/reports/LEAN-LORI-R3-PHASE-RECONCILIATION-2026-08-09.md`
records **Phases 6, 7 and 8 as `NS` (not started)**. It was written at HEAD `a217051`;
commits `2829517`, `3065cfc` and `ce5e636` landed hours later the same day. **That report is
superseded on those three rows by the code.** Anyone quoting it for 6/7/8 will be wrong.

---

## 1. Reconciled phase state

Verdicts are against the current tree, not against any document.

| R3 phase | Verdict | Evidence / blocking item |
|---|---|---|
| Gate A (0.1–0.10) | **LANDED** | Phase 0 review + 192-case safety gate; closed `4da079a` |
| 1A finalize deterministic turns | **PARTIAL** | Code landed, six branches (`chat_ws.py:263` marker). **Browser/export smoke owed.** |
| 1B person anchors | **LANDED** | `story_trigger.py:291` |
| 1C one bounded extraction = one call | **LANDED** | `api.py:492`, `extract.py:1897` |
| 1D safety-latch exit | **LANDED** | `hornelore1.0.html:7464`. Keep — it is what reactivation lands on. |
| 1E compound-name trim | **LANDED** | `lori_reflection.py` |
| **2 profile resolver** | **NOT STARTED** | Zero occurrences of `HORNELORE_RUNTIME_PROFILE` / `lean_lori` / `effective_profile`. Deferred by Chris 2026-08-09. |
| 3A camera / affect | **NOT STARTED** | Needs Phase 2 or a bespoke flag |
| 3B speech | **NOT STARTED** | Needs Phase 2 + two acceptances (see §4) |
| 3C safety | **LANDED as PARK** | `flags.py:250-275`, default `parked`; `test_safety_parked.py` 54 tests |
| 3D optional Llama | **PARTIAL** | 1C landed; SPANTAG and auto-drafts ungated |
| 4 structured composer | **PARTIAL** | `_Section` has 4 of 9 attributes (`prompt_composer.py:3318`) |
| 5 duplicate turn text | **LANDED** | `53a2cad` |
| 6 compact core | **LANDED** | 2,217 → 1,632 tok. **LLR-19 acceptance owed.** |
| 7 compact English-first | **LANDED** | 850 → ~110 tok |
| 8 state gating | **PARTIAL** | First gate landed. Remainder blocked on a **product decision**, not measurement. |
| 9 real-token budget | **PARTIAL** | `prompt_budget.py` self-documents its gap at `:71-80` |
| 10 remove blind slicing | **LANDED** | All three chat paths. **Live acceptance case list owed.** |
| 11 bounded extraction | **PARTIAL** | Window split landed; **the 384/768 cap is already reconciled — do not redo it** |
| 12 diagnostics | **PARTIAL** | Operator manifest blocked on Phase 2 |
| Inference coordinator | **NOT STARTED, CORRECTLY** | No collision evidence. **Do not open.** |
| Gate F | **NOT STARTABLE** | Asserts a `lean_lori` manifest and parked camera/Whisper; none exist |

**Gate D is the active gate.** Cumulative measured effect of the landed compaction on an
ordinary interview turn: composed prompt **7,205 → 5,410 tok**.

### 1.1 A token-figure disagreement, reported rather than resolved

`CLAUDE.md` says 6+7 moved the prompt **7,205 → 5,878**. The WO says Phase 8's gate moved
**5,681 → 5,410**. The Phase 8 state matrix gives ordinary **5,410**, era-request **5,681**,
and a pre-gate ordinary figure of **5,878/5,975** — so the WO's 5,681 baseline is the matrix's
*era-request* row, and the arithmetic across the three documents does not close cleanly.
**Treat 5,410 as the only figure measured after landing.** Do not reconcile these by
choosing one; re-measure once on the next live run.

---

## 2. Model-independent work — safe to plan

Everything below is prompt content, gating and evidence, inside the existing model and
window. None of it touches model, window, prompt *configuration*, STT, TTS or safety flags.

- Phase 4 remainder — the five missing `_Section` attributes.
- Phase 9 remainder — optional-section dropping, priority tiers, section reporting.
- Phase 8 remainder — **blocked on a product decision, not on code** (§3).
- Phase 11 post-split sweep — **gated on Phase 2, which is deferred.**
- Phase 12 operator manifest — **gated on Phase 2.**
- The three owed live evidence items (§5).

---

## 2a. Rollback — corrected 2026-08-14 (L1)

The WO's rollback section and the Phase 0 review both roll back via
`HORNELORE_RUNTIME_PROFILE`, which has **zero readers repo-wide**. Both are therefore
**unexecutable as written**, and **Phase 2 must not be built merely to make that paragraph
true**. An executable rollback, written against the controls that actually exist, is §15 of
`docs/wo/WO-LEAN-LORI-L2-RUNBOOK-2026-08-14.md`.

The single most important rollback fact in this lane: **there is no DB column, no server flag
and no per-narrator setting controlling `current_pass`** — its only durable home is browser
`localStorage`, so a pass-ownership change cannot be rolled back server-side today.

## 3. The one product decision blocking Phase 8

Phase 8's remaining scope is blocked on **Profile Seed ownership** — which subsystem owns
the seed and therefore which directives may be state-gated off an ordinary turn. This is
Chris's decision, not an engineering unknown, and no amount of further measurement resolves
it. `LORI_INTERVIEW_DISCIPLINE` (2,899 tok) is frozen until it is answered, and the Phase 8
report notes that part of those tokens may exist only to argue with a block that should not
be there.

**Do not attempt Phase 8's remainder before this is decided.**

**Decision brief written 2026-08-14 (L1):**
`docs/wo/WO-LEAN-LORI-PROFILE-SEED-DECISION-BRIEF-2026-08-14.md` — competing authorities,
every reader and writer, cache-refresh and export consequences, rollback implications, a
recommended owner and the exact question for Chris. **The brief does not implement the
decision.**

---

## 4. ⚠️ STOP CONDITIONS — never an agent decision

1. **The language model.** No alternatives, comparisons, downloads, canaries, swaps or
   migrations; no change to model id/path/revision, quantization, offload, device map,
   serving backend or chat template. If a fix appears to require a model change: **stop and
   report the blocker, and do not propose another model.**
2. **The 8,192-token window.** Locked. One subtlety worth stating so it is not mistaken for
   a violation: writing `MAX_CHAT_PROMPT_TOKENS=8192` / `MAX_EXTRACTION_CONTEXT_WINDOW=8192`
   explicitly into `.env` changes neither value and is **not** a window change. Any other
   value **is**.
3. **Prompt configuration.** Phase 6 must preserve eight behaviours verbatim in meaning.
   **Do not change behaviour to reach a token target.**
4. **STT.** Do not change speech models. Do not load GPU Whisper — even only to inspect
   status — without Chris's permission. Web Speech egress acceptance is not recorded.
5. **TTS.** Kokoro measured on **GPU** despite `TTS_DEVICE=cpu`; the CPU-latency acceptance
   this phase depends on **is not recorded as given**.
6. **Safety flags.** Reactivation is Chris's word, **never** an environment value.
   Unrecognised values resolve to `parked` deliberately, so a typo cannot switch the family
   back on. Reactivation additionally requires resolving the deterministic `domestic_abuse`
   false positive, the un-re-measured mortality escalation and the passive-death-wish case.

**None of the work proposed in §6 requires any of these.**

---

## 5. Three owed live items — one session, no harness

`CLAUDE.md` already directs: *fold into the next live run, do not build a harness.* All
three fit one stack cycle:

1. **Phase 1A browser/export smoke** — prove each delivered deterministic reply appears
   exactly once. The only outstanding item in Gate B.
2. **Phase 10 live acceptance case list** — every measured narrator across plain `hi`,
   Building Years, active trip, selected photo, realistic history, a long valid turn, each
   style, and the mandatory-core-cannot-fit path; each proving generated, persisted,
   archived, delivered and visible **after a restart**.
3. **Phase 8 `current_pass` capture** — open the app for a narrator with no cached spine
   and read `current_pass` off the `[Lori 7.1] runtime71 → model:` line. If it reads
   `pass1`, the three-authority conflict is confirmed end to end.

The same run yields the **LLR-19 recitation probe** (Phase 6's owed acceptance): prove no
instruction block — including the ACUTE SAFETY RULE template — can be emitted as a
narrator-visible reply in any tested runtime state. Mitigating but **not** discharging:
the park removed ~1,800 tokens of that protocol from every prompt, so the specific text
that leaked in LLR-19 is no longer present at all.

---

## 6. Proposed execution batches

Offered for Chris's selection. **Nothing here is authorised by this map.**

### Batch L1 — documentation reconciliation (offline, no stack) — **COMPLETE 2026-08-14**
Correct the stale claims this map found: the reconciliation report's `NS` on Phases 6/7/8;
the WO's Definition-of-done bullets that still assert *"deterministic safety remains
active"*; the unexecutable `HORNELORE_RUNTIME_PROFILE` rollback plan; Phase 10's drifted
line numbers (cite markers, not lines); the Phase 7 *"849-token"* figure; the Phase 6
preamble asserting `DEFAULT_CORE` is unchanged. Also amend
`docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`, which still lists *"Safety Classification"*
as active pipeline stage 1 and carries no reference to the park.
**Gate:** review only. **Cheapest and highest-value first block — every item on it currently
invites rebuilding landed work.**

### Batch L2 — one live evidence run — **RUNBOOK WRITTEN, NOT STARTED**
Full runbook: `docs/wo/WO-LEAN-LORI-L2-RUNBOOK-2026-08-14.md`, **corrected 2026-08-14 after
repository-backed review**. **Budget is exactly one start and one restart.** Uses a dedicated
`L2 ACCEPTANCE DELME` narrator; **no family narrator's profile or cache is cleared.** Live
safety stays `parked` throughout.

Four corrections the review forced, each recorded in place in the runbook:

- **Case C was impossible as written** — `saveProfile()` calls `initTimelineSpine()`, which
  writes the spine cache *and* promotes to `pass2a`, so completing identity destroyed the
  state being measured. It is reachable via a **second browser profile** instead, because
  `initTimelineSpine()` has exactly one caller and never runs on load.
- **Case F contradicted "read-only"** — it required a post-restart turn, which writes. It now
  inspects page state without sending.
- **Restoration was materially wrong** — the normal UI delete is **soft** and cascades
  nothing; the filesystem archive is decoupled from narrator deletion by design. L2 no longer
  promises a clean baseline, it promises an **accounted** one, and permanent deletion is
  Chris's explicit decision.
- **Case A did not test export** — it now downloads
  `GET /api/memory-archive/people/{pid}/export` and proves each reply occurs exactly once.

Also: token counts come from the existing `[chat_ws][WO-10M] prompt_tokens=` log (no
instrumentation change), the five session styles are enumerated, and the baseline snapshot —
a full copy of the live database — has an explicit deletion command.
**Gate:** Gate B closes; Phase 10 and Phase 6 debts discharge; Gate D gets its re-measured
token table, resolving §1.1.

### Batch L3 — Phase 9 completion (offline, one consolidated gate)
Optional-section dropping, priority tiers, section reporting — the gap `prompt_budget.py`
documents about itself.
**Gate:** `test_prompt_budget`, `test_prompt_sections`, `test_extraction_prompt_budget`,
`test_context_window_split` in one run.

### Batch L4 — Phase 4 completion (offline, same gate as L3)
The five missing `_Section` attributes, plus the four-narrator production-fixture acceptance.
Sensibly merged with L3; both are composer-structure work touching one file.

### Blocked, not batched
Phase 8 remainder (needs the §3 decision) · Phases 2, 11-sweep, 12-manifest (need Phase 2,
deferred by Chris) · Phases 3A/3B (need Phase 2 plus the §4.4/§4.5 acceptances) · Gate F ·
the inference coordinator (**do not open**).

> **STATUS 2026-08-14: L1 is COMPLETE.** *(This read "Recommended order: L1, then L2, then
> L3+L4 as one block" — retired now that L1 has landed.)* Delivered: errata banners on the
> stale historical report, an executable rollback, corrected gate commands, the Profile Seed
> decision brief, the full L2 runbook, and reproducible safety-preservation evidence.
>
> **Next is L2, and it is NOT authorised** — it opens on Chris's word. After that, L3+L4 as
> one block, once the live evidence and the Profile Seed decision are settled.

---

## 7. Consolidated test gate

Per-module, never whole-tree discovery. Sandbox runs are evidence; `.venv` is verification.

> **The single combined command that stood here has been REMOVED, not annotated.** It
> included `tests.test_chat_ws_safety_precedence`, which contaminates any process it shares:
> it mutates `HORNELORE_SAFETY_LLM_LAYER`, `LV_ENABLE_SAFETY` and `DATA_DIR` at **import**
> time and never restores them. A warning printed *below* a runnable block is not a
> safeguard — an operator copies the block first.

**The correct commands are §13 of `docs/wo/WO-LEAN-LORI-L2-RUNBOOK-2026-08-14.md`** — four
separate invocations, with the reasoning at §14. They are deliberately not duplicated here,
so there is one place to keep correct.

Coverage breadth by `def test_` count: safety-parked 54 · prompt-budget 22 · prompt-sections
36 · core-compaction 22 · english-first 14 · era-gating 16 · extraction-budget 42 ·
window-split 19 · story-trigger 118 · reflection 20 · meta-question 37 ·
safety-precedence 16 · narrator-bridge 60. **These are breadth, not a passing state** — this
map executed nothing.

> **CORRECTED 2026-08-14 (L1).** This note previously read: *"`tests/test_chat_ws_safety_precedence.py`
> stays green only with `HORNELORE_SAFETY_STATE=active` set for that module."* **That was
> wrong and it was mine.** The module sets and restores the variable **itself** in
> `setUpModule`/`tearDownModule` (`:93-104`). Setting it externally is actively harmful — the
> module would then restore it to `"active"` instead of removing it, leaving safety active for
> every later module in the process.
>
> The module **does** need its own command, for a different and genuine reason: it mutates
> `HORNELORE_SAFETY_LLM_LAYER`, `LV_ENABLE_SAFETY` and `DATA_DIR` at **import** time
> (`:45-50`), which is not restored and leaks process-wide at collection.
>
> **Correct commands, and the full reasoning:** §13 and §14 of
> `docs/wo/WO-LEAN-LORI-L2-RUNBOOK-2026-08-14.md`. The gate above is superseded by §13 there.

---

## 8. What this map did not do

No product code, tests, schema, migration, flag or `.env` value was changed. The stack was
not started. No live run occurred. No phase was opened. **Phase 0.10's hard stop is
preserved: the next action is Chris choosing a batch, not an agent starting one.**
