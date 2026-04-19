# LOOP-01 R4 → R5+ strategy bridge

Date: 2026-04-19
Status: bridge document. **Not R4 work.** Gated behind R4 measurement.
Companion: `loop01_r4_code_review_while_eval.md` (tactical).

This document captures the architectural insight that emerged while R4
was running, synthesised from four lines of recent research
(grammar-constrained decoding, entity-role binding, negation scope,
LLM-as-judge reliability) and from code-review evidence of how current
Hornelore patches collide with each other.

It exists to park the R5+ direction while R4 is still being measured,
so "good idea creep" doesn't hijack the current cycle.

---

## The core frame: validity ≠ binding

Hornelore's extraction pipeline has two distinct jobs:

- **Validity.** Is this `fieldPath` legal? Does the value fit the
  expected shape? Is the JSON well-formed? Is the path spelled right?
- **Binding.** Given a fact, which entity does it belong to, and
  which field on that entity? (Narrator's birthplace vs. child's
  birthplace. Narrator's military service vs. great-grandfather's.
  Sibling birth order vs. narrator birth order.)

The current pipeline uses one mechanism — the alias dict + rerouter +
guard stack — to solve both jobs, and the two jobs keep colliding.
The proof cases are concrete:

- `personal.heritage` → alias rewrites to
  `earlyMemories.significantEvent` (a *validity* move) *before*
  rerouter rule 4e can bind it to `grandparents.ancestry` (a
  *binding* move). R4-I rule 4e is partly dead code as a result.
- `family.siblings.dateOfBirth` → alias sends it to
  `earlyMemories.significantEvent`, even though every other
  `family.siblings.*` row in the same dict routes to `siblings.*`.
  Mixed validity + binding intent in one row.
- `parents.siblings.*` → `parents.notableLifeEvents` — the alias
  comment even calls this a "lossy stopgap." It's binding work the
  validator has no business doing.
- Patch D narrator-birthOrder reroute compares raw LLM surface form,
  and Patch H canonicalises that surface form *afterwards*. Two
  separate stages both trying to reason about the same value at
  different moments.

Each patch has been a rational local fix. The collisions aren't from
sloppy work — they're from asking one mechanism to do two jobs.

---

## Three pillars for R5+

### Pillar 1 — Draft → Project → Bind (DCCD-inspired)

The constrained-decoding literature is clear: hard constraints from
token 1 improve validity but damage semantics, because the model is
forced to commit to a field before it finishes reasoning about which
entity the fact belongs to. The Draft-Conditioned Constrained Decoding
line of work addresses this by splitting the job:

1. **Draft.** Model generates a free-form semantic plan — no schema,
   no JSON enforcement. Its job is to reason about *who did what*.
2. **Project.** A constrained decoder (Outlines/XGrammar-style)
   projects the draft onto legal `fieldPath` shapes. Its job is to
   make the output *valid*.
3. **Bind.** A post-projection pass resolves entity attribution
   (which narrator / which parent / which ancestor) using explicit
   binding rules, not buried reroutes.

For Hornelore this means:

- The alias dict shrinks but does not disappear. Surface-variation
  rows (`dob` → `personal.dateOfBirth`, `firstName` →
  `parents.firstName`) are legitimate validity normalisation — the
  model emitted a plausible token sequence that didn't match our
  exact path string. Those stay. Roughly ~100 of the current ~220
  rows.
- Binding-disguised-as-validity rows go away. `personal.heritage` →
  `earlyMemories.significantEvent`, `parents.ethnicity` → same, the
  entire `parents.siblings.*` block, `family.siblings.dateOfBirth`
  → `earlyMemories.significantEvent`. That work relocates to the
  binding layer. Roughly the other ~120 rows.
- The rerouter moves from "fighting the alias dict" to "the
  dedicated binding layer." Its current seven rules stay; they just
  run on inputs that haven't already been corrupted by validity
  rewrites.

Non-goal for R5: do not implement hard constraints from token 1.
That would improve shape metrics and worsen attribution metrics.
The split matters.

### Pillar 2 — Mirrored counterexamples against OTS bias

The narrator/parent/grandparent confusions are not random
hallucinations. Evidence (from code review + research) points at a
structural bias: **Order-to-Space** — the model learned a shortcut
that first-mentioned-entity = primary role, from web-scale training
data where ~89% of caption order matches layout/role order.

Patch E (relation-scope guard) and Patch 4 (narrator-scoped negation)
are treating symptoms. The principled fix is mirrored
counterexample testing: for every binding-sensitive case in the
question bank, generate the entity-flipped version and confirm both
pass.

Concrete near-term work:

- Inventory which existing cases are binding-sensitive (probably the
  E-series, greatGrandparents cases, and anything with
  ancestor-military or parent-birthplace content).
- For each, author the flipped version. "Melanie is the wife of
  [Narrator]" paired with "[Narrator] is the husband of Melanie."
  "My grandfather served in the Navy" paired with "I served in the
  Navy, my grandfather was a baker."
- A binding-sensitive case should pass in **both** directions or
  neither. Asymmetric pass is the signal of OTS bias.

This is EX-series work, not a patch.

### Pillar 3 — Cue + scope + subject, not denial regex

Thunder-NUBench formalises what the current `_DENIAL_PATTERNS` list
approximates: negation is not "find the word *not*." It's the
interaction of three things:

- **Cue.** Which word(s) carry the negation?
- **Scope.** Which part of the sentence does the cue apply to?
- **Subject.** Who or what is the negation about?

Current guard fails cleanly split along exactly these axes:

- "I'm not X, more of a Y" — cue is "not," scope is X only, but the
  guard reads cue and strips the whole category. Patch F is a
  partial fix for the contrast-affirmation subcase.
- "I never served, but my great-grandfather did" — cue is "never,"
  subject is narrator, but the narrator-scope check runs via a
  *distance-from-ancestor-marker* heuristic (`_is_ancestor_context_near`)
  rather than actual subject resolution. Works for the common
  cases; fragile as phrasing varies.
- "No big health stories, but I've been healthy" — cue + scope
  interact in a way the regex can't represent at all.

Near-term structural upgrade: move from denial-pattern matching to
cue + scope annotation at the clause level. Even a lightweight
classifier (subject = narrator / other, scope = clausal / local,
assertion = denial / affirmation) would be a step function over the
current regex stack.

Not an R5 patch. EX-series work.

---

## Harness implications (the scorer-compatibility trap)

The LLM-as-judge literature says: automated judges track coarse
directional trends with human raters, but diverge on magnitude and
nuance. Position bias and prompt sensitivity are real. Practical
recommendation: use judges as *screening* (eliminate obviously worse
variants), not as *final grading* of interpretive fields.

This maps directly onto our suspected Patch H effect. Patch H
canonicalises dates and birthOrder surface forms. If the scorer
rewards ISO dates over MDY dates, Patch H will *move pass rate*
without the extractor actually improving — just because the scorer
is happier. That's scorer-compatibility, not extractor improvement.
The eval-first note (`loop01_r4_eval_first_note.md`) already flagged
this; the paper validates the concern.

Harness changes that follow from this (not R4 work):

- **Three-way scoring split.** Canonical fact fields (dateOfBirth,
  placeOfBirth, marriageDate, etc.) get strict match. Narrative
  note fields (`*.notes`, `*.memorableStory`, `personal.nameStory`)
  get signature-based partial credit on meaning preservation, not
  surface overlap. Judge-based grading stays for coarse model
  selection only.
- **R4 readout protocol.** For every case that moved pass→fail or
  fail→pass between R3b and R4, first check: did Patch H touch a
  scored value on that case? If yes, flag the movement as
  scorer-drift-candidate and inspect separately before counting it
  as a real delta. This gets built as step 0 of the R4 readout.
- **#63 (should_pass drift).** Up to 26 cases may have drifted
  since R2 baseline. The fair comparison across R2/R3/R3b/R4 is
  per-case pass/fail under a frozen should_pass, not aggregate
  pass rate under drifting predictions. Harness audit is its own
  work item.

---

## Where each finding in the code review eventually lives

Short mapping for when R5+ work starts:

| Code review finding                               | Becomes                                        |
| ---                                               | ---                                            |
| #1 Alias hijacks rerouter 4e                      | Dissolved by Pillar 1 (binding relocates)     |
| #2 Alias dict rebuilt per call                    | Tactical now; irrelevant after Pillar 1       |
| #3 Patch H runs after Patch D                     | Dissolved by Pillar 1 (ordering is explicit)  |
| #4 Prompt contradiction on family military        | Tactical — fix the prompt regardless          |
| #5 `compact_catalog` isn't compact                | Dissolved by Pillar 1 (projector replaces it) |
| #6 Greedy `[.*]` in JSON parse                    | Tactical — replace with depth scanner         |
| #7 Pets splitter too strict                       | Partly dissolved by Pillar 1 (better draft)   |
| #8 `family.siblings.dateOfBirth` wrong alias      | Tactical now; illustrates category error      |
| #9 Rerouter before validator order                | Becomes a Pillar-1 design question            |
| #10 Rules-fallback answer projection              | Tactical — add length guard                    |
| #11 Twopass Pass-2A weak on entity-role pairing   | Partly addressed by Pillar 2 (mirrored)       |
| #12 Metric double-counting                        | Tactical — fix in `_record_metric`            |
| #13 Dead parent-reorder code                      | Tactical — delete                             |
| #14 Alias ↔ rerouter round-trip                   | Dissolved by Pillar 1                         |
| #15 `hobbies.hobbies` → `pets.notes`              | Pillar 2 (mirrored pets-vs-hobbies tests)     |
| #16 Model coupled to API process                  | Independent architecture work (vLLM split)    |

Most of the alias/rerouter findings dissolve under Pillar 1. The
prompt contradiction, the metric bug, the dead code, and the greedy
regex are all tactical and worth fixing regardless of what R5 looks
like. The OTS-bias and negation findings need Pillars 2 and 3 to
really land.

---

## Gate

Nothing in this document is R4 work. R4 work is:

1. Clean restart, confirm R4 loaded, warm model.
2. Live master eval.
3. Per-axis diff vs. R2 / R3 / R3b.
4. Scorer-drift check on Patch H (step 0 of the readout above).
5. Per-patch decide: keep / surgically roll back / isolate / abandon.

Only after (5) does R5 scoping begin. At that point this document
becomes the requirements sketch for the new architecture.

---

## Open questions

- Is there a smaller projector step (Pillar 1) we could land before a
  full DCCD rebuild — e.g. a post-hoc schema projector that runs on
  already-generated JSON and corrects invalid paths via set
  membership + nearest-neighbour matching? That would be R5-scoped,
  not R6.
- What's the minimum mirrored-counterexample set needed to detect OTS
  bias? 20 cases? 40? Depends on how strong the current asymmetry is.
- For the cue/scope/subject negation upgrade: do we train a small
  classifier, or prompt the same LLM for structured annotation as a
  pre-pass? Cost vs. reliability tradeoff, benchmarkable.
