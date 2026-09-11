# HANDOFF — Phase 6, Block C closed, Lean conversational verdict recorded

**Written 2026-09-09, desktop session.** For picking Phase 6 up after the switch to
`WO-LOREVOX-PORTABLE-NARRATOR-01`.
**Authority order is unchanged:** current code > current tests and live evidence >
accepted closeout records > `HANDOFF.md` > this file.

**Machine note.** This session ran on the desktop, repo `main` at `7d5d040`, against
`/mnt/c/hornelore_data/db/hornelore.sqlite3`. Laptop evidence was copied into the
gitignored `.runtime/eval/` and `docs/reports/` first; nothing under `hornelore_data`
was copied or synchronized.

---

## 1. Block C — CLOSED, on `main`

Commits `cb38600` (extractors) and `7d5d040` (tests + replay instrument).

| | |
|---|---|
| Repair | punctuation-aware proper-name grammar in `factual_chain_capture.py` and `lori_structured_narrative_fallback.py`, kept separate, plus a position-driven scan in the former so a stripped leading filter token no longer costs the real name a phrase slot |
| Tests | 68 focused · 233 protecting family · 3 Boris · 17 replay instrument — **zero skips**, `.venv` |
| Counterfactual replay | `.runtime/eval/phase6-cohort-C-all-on-20260908`: **38/38 records accounted for = 36 replayed + 2 deterministic (witness, meta_question; no id-40/48 stage)**, 25 unchanged, 11 changed, **0 splits, 0 lost anchors, 0 id-40 eligibility flips**, id-40 opener changed on 6 turns, id-48 receipt on 3 |
| Reproduced from stored utterances | both malformed openers in `lori_guard_registry.py:586` — `['Saint Patrick','Day','1950']` (turn 2593) and `['Paul','Military','Discipline']` (turn 2539) — plus two nobody had named: `Madeleine L'Engle`, `Tom's Coffee Shop` |

**Recorded, not solved:** the leading-filter-token re-scan was never exercised by
cohort C, so it is unmeasured rather than proven safe; `_CASCADE_FILTER_TOKENS` still
lacks function words (`For`, `She`, `That` reach id 48's receipt pool); `Wrinkle` /
`Time` still split (no punctuation involved). **Repairing the inputs does not vindicate
id 40 or id 48.**

**The replay instrument's own false success is on the record.** Its first version read
`narrator_input` at the top level instead of under `context`, skipped all 38 turns, and
printed a clean zeroed report with exit 0. It now refuses an incomplete cohort
(`--expect-records` / `--expect-applicable` both required, exit 2, no report written),
classifies every record into exactly one bucket, and
`tests/test_phase6_blockc_replay_instrument.py` pins that class. A punctuation/rescan
sub-classifier was **deleted rather than repaired** — it scored every merge as "both"
and is not part of any acceptance claim.

---

## 2. The Lean conversational verdict — SCORED by Chris

Eval dir: `.runtime/eval/phase6-conversation-quality-20260909-152049` (local).
Capture: `ada-lean-baseline.md` in that dir, rendered by
`phase6_conversation_capture.py` against the exact frozen ten.

**Arm A — Lean.** Narrator Ada `8ec7a427`. Revision `1`, selection `55a52f0cb045`
(identical to the historical Lean arm), registry `bfcbfb69b9e5`, 4/43. Before and
after snapshots identical. Ten of ten: `generation_attempted=true`,
**`raw_equals_delivered=true`, `net_words_removed=0`**. Prompt 1,017 → 2,010 tokens.
Turn 6 requested `correction`, was reset to `interview` by the parser, generated.

| Listening | Warmth | Dignity | Continuity |
|---|---|---|---|
| **3/5** | **4/5** | **4/5** | **2/5** |

Strongest turns 1, 2, 4, 7. Consistent generation-level failures: **backward
redirects** on turns 3, 6 and 10 (*"Last time we were talking about…"*, *"Let's go
back to…"* — one of them invents prior context: *"the camp you mentioned earlier"* on a
first mention); **unsupported causality** on turn 5 (*"the quarry had taken a toll on
his health"* — she said his hands stopped working); **invented significance** on turn 8
(asked to find hidden meaning in a dish she said she had no idea why she remembered)
and turn 9 (*"must have been lovely"*, *"wonderful memories"*); turn 5 asked no
question at all.

**Lean is the best measured conversational configuration, and it is not good enough.
Its defects are generation-level. Do not answer them with a guard.**

---

## 3. Arm B — REJECTED: the accumulated prompt stack collapses the model

Fresh clone Ada `fe3063e1`, same ten turns. Lean + prompt authorities `1, 3, 5, 6, 7`
(ids 4, 8, 9, 10, 11 deliberately off — exemplar leakage evidence and over-surfacing).
Revision `6`, selection `9a7f3d374a9c`, 9/43, before/after identical.

Ten of ten: **`generated_tokens` 4–12, `generation_end_reason: eos`,
`raw_equals_delivered: true`, zero questions.** Prompt **5,181 → 5,731** tokens.

> *The cemetery.* · *Websterville.* · *Quiet mornings.* · *Building schedules for the
> dentists.* · **Fifty-two.** (to her father's hands) · *Fifty-four is a big milestone
> at fifty-four.* · *Berlin Street.* · *The green glass dish.* · *Groton Pond.* · *The
> seventies.*

No guard fired; nothing was cut; the model **chose** to stop. Five prompt layers turned
a model that was speaking in sentences at ~1K tokens into a noun-phrase echo at ~5.2K.
**`BUG-LORI-RESPONSE-STUB-COLLAPSE-01` and id 39's stub repair were built for this
symptom. Tonight shows the prompt set induces it.** The guard was treating a symptom the
instructions were causing.

---

## 4. Single-factor screen — which blocks are worth anything

Five fresh clones, Lean + one authority each, three frozen turns (cemetery, father's
hands, green dish). Every turn `eos`, `raw_equals_delivered=true`. **None collapses
alone.**

| Arm | Clone | Rev / selection | Turn-1 tokens (Lean 1,017) | Verdict |
|---|---|---|---|---|
| S1 `1` Who Lori Is | `db2b575a` | 8 / `34b9d9cec8cb` | 2,609 (**+1,592**) | **keep the intent.** Stayed with each turn, one question, no invented cause, invitational on the dish. One "feelings" probe |
| S3 `3` Listen + One Question | `4b6ddd54` | 10 / `d52682344b74` | 3,361 (**+2,344**) | **keep the intent.** One question every turn, kept Dennis by name, grounded the dish in Barre. "You mentioned…" ×2; echoed the age and the quarry, not the hands |
| S5 `5` Oral-History Listening | `470a3bf1` | 12 / `9290ed8e8caa` | 979 (≈0) | **reject.** Invented "every day", assumed childhood, drifted from the dish, two questions |
| S6 `6` Story-First | `28b83773` | 14 / `1744e1ac23ce` | 979 (≈0) | **reject.** *"fifty-two is relatively early onset for such issues"*; **directive leaked into her voice** — *"Let's try to weave that into the story"*; redirected the dish to the father |
| S7 `7` Follow-Up Priority | `c797cf39` | 16 / `c50a96f1b46d` | 1,169 (+152) | **reject — this is the redirect tic.** First turn of a fresh narrator: *"We've touched on several parts of your story. Where would you like to continue today?"* Menu or "go back" on 3 of 3 |

Sum of deltas ≈ 5,100; Arm B measured 5,181. **B's collapse is the combination —
mostly `1` + `3`, ~3.9K tokens together — not any one block.** The harmful behaviours
come from the short blocks; the useful ones from the two long blocks that cannot be
combined.

**Design direction, locked by this evidence:** write a new, compact Lori interviewing
prompt from the *intent* of `1` and `3` — Lean-sized, not production-sized. Do not
rebuild it by stacking existing blocks. **No further Phase 6 prompt arms, cohorts,
guard tests or clones before `WO-LOREVOX-PORTABLE-NARRATOR-01`.**

---

## 5. Retention is independently broken — QUARANTINE every retention number

Every one of Ada's ten Lean turns, and Chris's own production turn under Defaults, hit:

```
[llm] LLM call failed: 413 PROMPT_TOO_LARGE  prompt_tokens≈9,830  limit=8192
[extract] falling back to rules … outcome=noop
```

Ten of ten for Ada (`api.log` 16:57–17:01 local); ~9,827 for Chris. The **chat** prompt
ran 1,017–2,010 tokens — the conversation has six thousand tokens of headroom. The
**extraction** prompt is a fixed ~9,830 regardless of narrator or turn, ~1,640 over the
locked window. Rules fallback kept three items in ten turns. Story capture declined ten
of ten. **Ada's memoir export after the run contains only seeded profile data.**

Independent of the Guard Lab: extraction is Lorevox-owned and not among the 43; the
same wall under Lean and under Defaults.

**Lead, not cause:** earlier successful extractions in the same log read
`method=llm accepted=1…3 era=earliest_years pass=pass1`; today's all read
`era=? pass=?`. Un-scoped extraction may build a larger prompt than era-scoped. Undated.

Handling belongs to a separate lane — likely the post-session processing WO discussed
2026-09-09 — **and moving extraction post-session does not fix a 9,830-token prompt.
The prompt has to get smaller in whichever lane it runs. The window stays locked.**

---

## 6. Health reporting is false-green

Operator log during the Ada run: **`104 PASS · 3 AMBER · 0 RED`** while ten consecutive
extraction attempts failed. Session health cannot see extraction failure. Same class as
the replay instrument's original zeroed report. Recorded in `docs/BACKLOG.md`.

---

## 7. Synthetic narrator state — fixtures, not product narrators

Seven `testing_only` "Ada Pruitt" rows exist in the live database, all from
`scripts/phase6_populated_narrator.py`, tracked by id: `8ec7a427` (A), `fe3063e1` (B),
`db2b575a` (S1), `4b6ddd54` (S3), `470a3bf1` (S5), `28b83773` (S6), `c797cf39` (S7).
**Do not delete or clean them as part of closing this session.** One further Ada,
`85f52c6e`, sits in `/home/chris/lorevox_data/db/lorevox.sqlite3` — a database nothing
serves — from the wrong-world create below. Leave it; deleting a database is a
separate authorized act.

**Addendum 2026-09-11 — `8ec7a427` (A) was exercised by another lane and is no longer in
its post-run state.** WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 5a used it as the synthetic
narrator for the live Chrome acceptance walk (WO §35.3): it was opened through the picker
several times, exported twice, and restored into a disposable clean root that has since been
deleted. On the live root it gained what opening a narrator writes — a second `sessions` row
with its turns, and `bio_facts` rows appended on every open (12 → 96; the hydration is not
idempotent, BACKLOG §5) — and `interview_threads` went 8 → 0. **Nothing was deleted and no
row was hand-edited.** The other six are untouched. Decided by Chris 2026-09-11: all seven
stay held for this lane; when Block D resumes it decides whether A is reused, reset through a
sanctioned fixture mechanism, or erased — Phase 5a does not decide the fate of a Block D fixture.

Guard Lab is left at revision 16 on S7's configuration. Nothing else is selected.
Restoring Defaults is not required for the repo; it is required before the running
stack talks to a real narrator, and real narrators are never eligible for a selection
regardless.

---

## 8. Other defects found on the way — recorded, not chased

* **Wrong-database create, a second time by a different route.**
  `phase6_populated_narrator.py` let an exported `DATA_DIR`/`DB_NAME` win over `.env`,
  and its docstring said that "matches the server". It does not: `scripts/common.sh:26-29`
  sources `.env` under `set -a`. A stale WSL export put Ada in a database nothing serves
  while the script printed PASS. The "database must already exist" guard did not help,
  because a stale database existed. Fixed: `.env` wins, the override is announced, and
  `tests/test_phase6_populated_narrator_env.py` pins it. **The WSL profile still carries
  the stale exports.** The only check that caught it both times was asking the running
  product — `GET /api/operator/guard-lab/narrators` returned `count: 0`.
* **Trainer launcher blanks the session.** `lv80RunTrainerNarrator()`
  (`hornelore1.0.html:6749`) nulls `state.person_id`, removes `LS_ACTIVE` and clears the
  transcript **before** confirming its surface renders, with no visible restore path.
  "Questionnaire First" in the begin-chooser is this launcher, not the narrator's intake.
* **Family-locked runtime.** `_horneloreEnsureNarrators()` (`hornelore1.0.html:10083`)
  re-creates Chris, Kent and Janice from `ui/templates/*-horne.json` on first boot when
  they are absent; `:10136` disables their deletion. A fresh data root cannot be clean
  while this runs. **Removal is a required Phase 7 gate in
  `WO-LOREVOX-PORTABLE-NARRATOR-01`, not a flag.**
* **A dead-controls audit found no visible dead handlers** across 353 `onclick`
  attributes once namespaced calls (`FocusCanvas.setMemoryType`) were resolved
  correctly; an earlier pass in this session reported nine and was wrong.
* Delivered-text observations from Chris's own session: the welcome-back turn filled a
  stated uncertainty with a profile field (*"your earliest years growing up in
  Williston"*); `[SYSTEM: …]` rows ride along in narrator-visible exports (known,
  deferred); memoir export emits `(no entries yet)`.

---

## 9. What Phase 6 still owes, in order

1. The compact Lori interviewing prompt — written from `1`'s posture and `3`'s
   discipline in a few hundred tokens, none of `5`/`6`/`7`'s framing. Measured against
   Lean on the frozen ten with a fresh clone. **After portability.**
2. The extraction payload regression — date it, test the era-scoping lead.
3. Session health that can see extraction failure.
4. Only then: guards earn their way back one family at a time, against the winning
   prompt, on turns where each is eligible.

**The block sequence is A–F. Phase 6 is Block D. There is no Block G.**
