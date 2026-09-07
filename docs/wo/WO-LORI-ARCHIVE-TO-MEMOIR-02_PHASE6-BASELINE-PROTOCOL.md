# Phase 6 — lean conversational baseline: the protocol

**Status: SETUP BUILT, NOT RUN.** Nothing live has happened. This document
is the setup Chris asked for before any turn is sent.

**What Phase 6 measures.** Not "is Lori good". The first question is
narrower and answerable: *what does lean Lori actually do when the
empty-profile confound is removed?* Every intervention decision after
this one is measured against this baseline, so the baseline has to be
clean before it is worth having.

---

## 1. The confound being removed

Both lean turns on 2026-09-07 ran against `Guard Lab Test Narrator`, whose
record is deliberately empty. Profile Seed sat at 0/10, the banner read
`Narrator record incomplete`, and Lori spent both turns on intake:

> "What was your name during that time?"
> "What was your mother's maiden name?"

Those turns are good evidence about the **control plane** and useless as
evidence about **conversation**. A narrator with nothing on file makes
Lori an intake clerk, and judging her warmth or her follow-up choices in
that state measures the empty record.

`Guard Lab Test Narrator` is not being changed. It stays the
instrumentation narrator. Phase 6 gets a second one.

---

## 2. The narrator

**Ada Pruitt**, `testing_only=true`, wholly invented.

| | |
|---|---|
| Born | 17 March 1948, Barre, Vermont |
| Childhood | a duplex on Currier Street, Barre |
| Parents | Emil Bellandi, granite cutter at the quarry; Ruth Bellandi, school secretary |
| Siblings | Dennis (1945), Claire (1952) |
| Heritage | Italian on her father's side, Scots-Irish on her mother's |
| School | Spaulding High School; two years at Vermont Technical College |
| Military | did not serve |
| Work | dental assistant → hygienist → office manager, Montpelier |
| Partner | Warren Pruitt, lineman for the electric co-op |
| Children | Nadia (1972), Beth (1975) |
| Now | Montpelier; retired since 2011; volunteers at the historical society |

An ordinary life across a few eras, with enough relationships, places and
work that a follow-up question has somewhere to go — and enough left
unsaid at the edges that Lori has something real to ask about.

**No family material.** Kent, Janice, Walt, John and Del are untouched,
and no existing narrator was converted — `testing_only` is creation-time
only and has no write partner (`db.py:2852`).

### The name is a deliberate tradeoff, not an oversight

Other probe narrators are named `ZZ COHORT …` so an operator scanning the
list cannot mistake one for family. That is right for harness narrators
nobody talks to, and wrong here: **the display name reaches Lori's
context and her greeting.** A narrator called `ZZ PHASE6 SYNTH` would
confound the exact thing Phase 6 measures.

The boundary is carried by `testing_only=true`, which is what the gate
actually reads. If you would rather have the visible marker, it is one
constant in `scripts/phase6_populated_narrator.py` — the tradeoff is
yours to make, and I would rather state it than bury it.

---

## 3. The setup verifies itself against the shipped decision

Ten green topic rows would not have been enough. The thing that decides
whether Lori raises onboarding is `plan_turn`, and the deciding line is:

```text
profile_seed_turn.py:620   if state.get("status") != _seed.STATUS_ACTIVE:
                               return TurnPlan(IDLE)
```

So `--check` resolves the narrator through the shipped resolver
(`profile_seed.resolve_effective`, read-only, no version bump), feeds that
state to the shipped `plan_turn`, and **`IDLE` is the pass condition.**
A profile that satisfies all ten topics while the gate still reads
`active` would reproduce the confound, and only the second check catches
it.

**Read before writing, not assumed:**

* `has_value(False) → True` (`profile_seed.py:512`) — so `military.served:
  false` is the answer "I did not serve", not a gap. The whole military
  topic hangs on this.
* `parents_work` has `profile_paths=()` **deliberately** (line 282): a
  `parents` list of bare names is not evidence about their work, so every
  parent carries an occupation.
* `life_stage` reads `community.retirementStatus` only (line 367) — a date
  of birth is arithmetic, not an answer.
* `childhood_home` reads no birthplace path (line 254) — where you were
  born is not where you grew up.

---

## 4. The ten turns

**The authoritative list is `data/evals/phase6_lean_baseline_turns.json`.**
The table below describes it; the file decides. Three consumers read that
one file — the JS route preflight routes those exact strings, the Python
capture requires those exact narrator inputs in that exact order, and
this document points at it. It was briefly written out in three places,
which is the failure this repo has already recorded twice: two copies of
one truth stay equal until the first edit.

Categories are yours; the wording is Ada's.

| # | Category | Turn |
|---|---|---|
| 1 | childhood / family | "My brother Dennis used to walk me to school through the cemetery because it was the fast way." |
| 2 | place / move | "We left Currier Street the summer I turned eleven and moved out toward Websterville." |
| 3 | daily routine | "These days I'm up before Warren. I make the coffee and do the crossword while the house is quiet." |
| 4 | work | "At the practice I ended up building the schedule for both dentists. Nobody ever asked me to. I just started doing it." |
| 5 | emotionally meaningful | "My father came home from the quarry one afternoon and told us his hands had stopped working right. He was fifty-two." |
| 6 | **correction** | "Actually, he was fifty-four, not fifty-two. I keep getting that wrong." |
| 7 | multiple threads | "Claire moved out to California the same year we lost the house on Berlin Street." |
| 8 | must not over-interpret | "There was a green glass dish on the hall table. I have no idea why I remember it." |
| 9 | place / leisure | "We used to drive up to Groton Pond on Sundays in the summer, all four of us in the wagon." |
| 10 | resists date pressure | "I couldn't tell you what year we got the camp. Somewhere in the seventies." |

Turn 6 corrects **turn 5**, in session — a correction of something Ada
herself said, not of a profile field. Turn 7 offers three threads at once
(Claire, the move, losing the house) so the follow-up choice is
observable. Turn 8 is a detail with no significance attached, so invented
significance would be visible. Turn 10 withholds a date on purpose.

### Turn 6 is scored separately — two questions, not one

Turn 6 routes deterministically and **never reaches the model**, so it
cannot be evidence about what the model does. It stays in the baseline
and in the report, answering its own question:

| Turns | Question |
|---|---|
| 1–5, 7–10 (nine) | What does lean **generated** Lori do conversationally? |
| 6 | Does the **correction path** handle a genuine self-correction appropriately, and hand continuity back to the conversation? |

The turn set carries `in_quality_aggregate: false` on turn 6, and the
rendered report says so at the top and again on the turn itself.
Averaging one deterministic response into a model-quality measurement
would contaminate it.

---

## 5. A finding from the preflight — reported, not fixed

**`turn_mode` is assigned in the BROWSER**, by `lvRouteTurn`
(`ui/js/app.js:2704`), and a turn routed to `correction` takes a
deterministic path that **never reaches the model**. So every turn above
was routed through the shipped function before the set was accepted:

```text
node scripts/ui/phase6_turn_route_preflight.js
  -> 9 interview, 1 correction, as intended
```

While doing that, the detector at `app.js:2600` was measured against
ordinary narration:

| Sentence | Routes as |
|---|---|
| "There was a green glass dish… not that it matters." | **correction** |
| "It was not a big house, but we managed." | **correction** |
| "It wasn't the same after that." | **correction** |
| "We used to drive up to Groton Pond on Sundays." | interview |

Three ordinary sentences never reach the model. The third is the one that
matters: *"it wasn't the same after that"* is exactly how someone talks
about a loss, and Lori would answer it from a deterministic correction
branch.

**This is an observation for the Phase 6 defect list, not a fix.** It is
also the reason the ten turns are worded the way they are — otherwise the
baseline would have silently measured a regex. The witness is pinned in
the preflight and in the turn-set file, so if the detector is ever
narrowed the script says so.

**We word around it once, for this first baseline only.** Real future
conversations must not be shaped to survive a regex; a narrator saying
"it wasn't the same after that" is the product's problem to handle, not
the narrator's to avoid.

---

## 6. The capture instrument

`scripts/phase6_conversation_capture.py` is read-only and imports the
existing trace reader from `guard_lab_live_acceptance` rather than adding
a second one. **Nothing new had to be instrumented** — every field you
asked for is already written by the shipped trace: `narrator_input`,
`raw_text`, `delivered_text`, `raw_equals_delivered`,
`net_words_removed`, `delivered_questions`, and the `authority_*`
identity. Block C's `turn_key` bind is what lets a transcript join its
extraction row at all.

**It fills the measured columns and leaves the judged ones blank.**
Details reflected, details dropped, invented significance, and whether
the question follows the strongest thread are judgements. A generated
guess in those columns would be indistinguishable from a finding, so the
script prints them empty for a human.

**It refuses anything but the intended ten turns.** Selecting by narrator
id alone is right only on a perfect first run — an interrupted or retried
session leaves 11 or 15 Ada turns behind, and a renderer that drew them
all would produce a report indistinguishable from a clean one. So the run
is checked against the authoritative set for exact text, exact order and
once each. Wrong count, wrong text, wrong order or a retried turn all
REFUSE rather than render; `--diagnose` lists what was actually traced.
A contaminated run is not repaired by rendering it — preserve the
directory, arm a new one, start again.

`tests/test_phase6_baseline_turnset.py` pins every arm of that refusal
(14 tests, no skips). Its fixtures build their records by calling the
shipped trace store rather than hand-writing the shape, so a rename of
`narrator_input` fails at the fixture instead of passing against a shape
nothing produces. Three mutations were run against the enforcement —
duplicate detection off, length check off, order check off — and each
one kills a test.

---

## 7. Runbook

**Chris starts and stops the stack.** No block in this document does it,
and none should be added.

**Step 1 — arm a fresh evidence container, BEFORE the stack starts.**
Tracing is resolved at process startup (`trace_env.sh:63`), so arming
afterwards records nothing.

```bash
cd /mnt/c/Users/chris/hornelore
RUN="$PWD/.runtime/eval/phase6-lean-20260907"
mkdir -p "$RUN"
printf '%s\n' "$RUN" > .runtime/eval/current_eval_dir
```

**Measured, not inferred:** that marker is what the server actually reads
(`lori_guard_gate.py:110`, `trace_env.sh:69`), and a non-empty marker is
itself what turns tracing on (`trace_env.sh:79`).

**The arm survives startup.** `start_all.sh` prints the resolved banner
(line 36) and then runs `kill_all_hornelore` (line 39) — **not
`stop_all.sh`** — and that helper contains no marker reference. So the
sequence *arm → start → API comes up armed* holds.

Disarming belongs to `stop_all.sh` alone: its EXIT trap copies the
pointer to `last_eval_dir`, then removes `current_eval_dir`
(`stop_all.sh:56`). Deliberately — a stale marker would record every
ordinary Kent and Janice turn. Two consequences:

* **Stopping the stack mid-baseline ends that baseline.** Preserve the
  directory, arm a different new one, start over. Never reuse it. The
  capture refusing a short run is the backstop for this.
* Analysis after shutdown still works: the capture falls back to
  `last_eval_dir` **and prints which pointer it used** — reading the
  wrong run silently is the thing to avoid.

**Step 2 — Chris starts Hornelore his normal way, and confirms the
startup banner.** It must read `Response trace: ENABLED` and name the
Phase 6 directory. The banner prints the destination that was actually
resolved rather than a hardcoded path, which is what makes it worth
reading. **If it says OFF, or names another directory, stop there** — the
turns would not be recorded and there would be no baseline to render.

**Step 3 — create and verify the narrator** (the only write).

> **This step failed silently on its first run, 2026-09-07, and the
> failure is worth stating in full.** Ada was created, ten topics read
> `answered`, `plan_turn` returned `idle`, the script printed `PASS` —
> and `GET /api/people/<id>` returned **404**. Every check was true about
> a database nothing serves.
>
> `api.db` resolves `DATA_DIR` at import (`db.py:58`), defaulting to a
> repo-relative `data/`, and `DB_NAME` to `lorevox.sqlite3`
> (`db.py:62`). The server runs with `.env` loaded
> (`DATA_DIR=/mnt/c/hornelore_data`, `DB_NAME=hornelore.sqlite3`); the
> script exported neither, so `init_db()` created a **second, empty
> database** inside the repo and populated that. The instrument was
> correct and pointed at the wrong world — which is the same failure
> family as citing a name instead of the line that reads the value.
>
> Two corrections, both in the script: it now loads those two keys from
> `.env` before importing `db` (an exported value still wins, matching
> the server), and **`--create` refuses when the resolved database file
> does not already exist**, because being about to create one is the
> proof of pointing somewhere the product does not read. The resolved
> path is printed on every run. `tests/test_phase6_baseline_turnset.py`
> executes that refusal and asserts no database is created by it;
> removing the guard fails the test.
>
> The stray `data/db/lorevox.sqlite3` is gitignored (`.gitignore:76`), so
> nothing can commit it. Deleting it is a separate, authorized act.

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv-gpu/bin/python \
  scripts/phase6_populated_narrator.py --create
```

Expect ten `answered` rows, then `plan_turn action: idle` and **PASS**.
If it does not say PASS, stop — the baseline is not clean.

**Step 4 — preflight the turn set** (read-only):

```bash
cd /mnt/c/Users/chris/hornelore
node scripts/ui/phase6_turn_route_preflight.js
```

**Step 5 — select Ada in the Operator panel, set the Lean preset, and
snapshot the configuration:**

```bash
cd /mnt/c/Users/chris/hornelore
.venv-gpu/bin/python scripts/guard_lab_live_acceptance.py \
  snapshot phase6-lean-before
```

**Step 6 — I send the ten turns in order**, exactly once each, waiting
for each response, changing nothing between them.

**Step 7 — snapshot again, confirm the configuration never moved, and
render the capture:**

```bash
cd /mnt/c/Users/chris/hornelore
.venv-gpu/bin/python scripts/guard_lab_live_acceptance.py \
  snapshot phase6-lean-after
PYTHONPATH=server/code .venv-gpu/bin/python \
  scripts/phase6_conversation_capture.py --narrator "Ada Pruitt" \
  --out docs/reports/PHASE6-LEAN-BASELINE-20260907.md
```

`docs/reports/` is gitignored, which is correct — the report carries a
transcript. Do not `git add` it.

The before/after snapshots must show the **same revision and the same
selection fingerprint**. If they differ, the configuration moved during
the run and the ten turns were not all produced under one configuration —
that is a discarded baseline, not a footnote.

**Step 8 — human review of the four blank judgement fields.** That is
where the conversational verdict comes from; nothing upstream of it
generates one.

---

## 8. What comes back

1. the narrator profile setup — this document;
2. the ten turns as sent;
3. exact raw and delivered text per turn, from the trace;
4. which Guard Lab authorities were active (revision + both fingerprints);
5. extraction result per turn, reported separately;
6. observations — **with nothing fixed.**

### The question is not "was Lori better"

For the **nine generated turns**, what we are looking for is whether the
earlier lean problems survive now that Profile Seed is no longer a
confound:

* Does she reflect **specific narrator material** rather than a generic
  summary?
* Does she preserve **causal structure**?
* **Which** meaningful detail does she choose to follow?
* Does she **invent significance** — turn 8 exists for this?
* Does she keep steering toward biography or intake **even though Profile
  Seed is complete**?
* Does she ask **exactly one** useful question, naturally?
* Does **raw still equal delivered** under Lean?
* Does **extraction behave independently** of conversational quality?

**Turn 6 separately:** how does the deterministic correction route feel
inside an otherwise natural conversation?

## 9. What this deliberately does not do

No prompt changes. No controls re-enabled. No guards added. If lean Lori
is weak, the investigation order is prompt/context composition → model
behavior → smallest intervention hypothesis. Not: awkward response → add
a deterministic guard.

**Guard Lab live-acceptance debt is unchanged** — four checks still OPEN,
blocking Phase 8 only.
