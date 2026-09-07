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

**This is an observation for the Phase 6 pile, not a fix.** It is also
the reason the ten turns are worded the way they are — otherwise the
baseline would have silently measured a regex. The witness is pinned in
the preflight, so if the detector is ever narrowed the script says so.

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

---

## 7. Runbook

Nothing below starts or stops the stack — that is yours.

**Step 1 — create and verify the narrator** (the only write):

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv-gpu/bin/python \
  scripts/phase6_populated_narrator.py --create
```

Expect ten `answered` rows, then `plan_turn action: idle` and **PASS**.
If it does not say PASS, stop — the baseline is not clean.

**Step 2 — preflight the turn set** (read-only, no stack needed):

```bash
cd /mnt/c/Users/chris/hornelore
node scripts/ui/phase6_turn_route_preflight.js
```

**Step 3 — with the stack up, select Ada in the Operator panel, set the
Lean preset, and snapshot the configuration:**

```bash
cd /mnt/c/Users/chris/hornelore
.venv-gpu/bin/python scripts/guard_lab_live_acceptance.py \
  snapshot phase6-lean-before
```

**Step 4 — I send the ten turns in order**, one at a time, waiting for
each response, changing nothing between them.

**Step 5 — snapshot again and render the capture:**

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

---

## 8. What comes back

1. the narrator profile setup — this document;
2. the ten turns as sent;
3. exact raw and delivered text per turn, from the trace;
4. which Guard Lab authorities were active (revision + both fingerprints);
5. extraction result per turn, reported separately;
6. observations — **with nothing fixed.**

## 9. What this deliberately does not do

No prompt changes. No controls re-enabled. No guards added. If lean Lori
is weak, the investigation order is prompt/context composition → model
behavior → smallest intervention hypothesis. Not: awkward response → add
a deterministic guard.

**Guard Lab live-acceptance debt is unchanged** — four checks still OPEN,
blocking Phase 8 only.
