# Lean Lori Phase 8 — state matrix

**Date:** 2026-08-09 · **Measurement only when written. See the addendum: the ERA gate
has since LANDED in `ce5e636`, and everything below is the BEFORE evidence.**
Real tokenizer (`Meta-Llama-3.1-8B-Instruct/tokenizer.json`), real `compose_system_prompt`,
budget limit 7,552 (R3 Phase 9: 8192 − 512 response − 128 margin).

**The matrix comes before any edit, per the rule of engagement. It changed the plan.**

---

## 1. Where the state surface actually is

`compose_system_prompt` has only **10 `parts.add()` sections**, but the composed prompt is 76
blocks. Almost everything lives inside one of them — `directives_interview` — built from a
`directive_lines` list with **51 append sites**. That list, not the section table, is Phase
8's subject.

Of the 51, **8 are unconditional** once `runtime71` exists. The rest are gated on
`assistant_role`, `identity_mode`, `current_pass`, `current_mode`, `cognitive_support_mode`,
`session_style`, softened state, witness state, visual affect and fatigue score.

## 2. The matrix

`Y` = present, `·` = absent. Identical fixture except where the state requires otherwise.

| state | tok | core | disciplin | oralhist | era_expl | ident_md | eng_first | transpar | helper | cog_supp |
|---|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| fresh unidentified `hi` | 5878 | Y | Y | Y | Y | Y | Y | Y | · | · |
| identified ready `hi` *(corrected)* | **5975** | Y | Y | Y | Y | **·** | Y | Y | · | · |
| active era, building years | 5877 | Y | Y | Y | Y | Y | Y | Y | · | · |
| era-definition question | 5878 | Y | Y | Y | Y | Y | Y | Y | · | · |
| oral-history story turn | 5878 | Y | Y | Y | Y | Y | Y | Y | · | · |
| **helper** | **2263** | Y | · | · | · | · | Y | Y | Y | · |
| **onboarding** | **2186** | Y | · | · | · | · | Y | Y | · | · |
| Spanish turn | 5771 | Y | Y | Y | Y | Y | **·** | Y | · | · |
| cognitive support mode | 6461 | Y | Y | Y | Y | Y | Y | Y | · | **Y** |
| trip / photo turn | 5934 | Y | Y | Y | Y | Y | Y | Y | · | · |

> **Row 2 corrected 2026-08-09 (second pass).** It read `5878 … IDENTITY MODE = Y`, which
> contradicted §3 and §6 of this same report. The fixture had not set `identity_complete`,
> so that row was measuring the *fresh* state twice. Corrected in place rather than deleted,
> because a table that disagrees with the prose two sections below it is exactly how a
> reader ends up believing the opposite of what was proved.

**The interviewer path is very nearly state-invariant.** **Four of ten** states sit within
**±1 token** of 5,878 — and the count is worth flagging because this sentence read *"eight of
ten"* until 2026-08-09 and was wrong **in both versions**: it was five before the row-2
correction and is four after it. Four things move the prompt at all: completing identity
(**+97**, the identity block replaced by larger post-identity directives), Spanish correctly
dropping English-first (−107), cognitive support (+583), and photos (+56).
`helper` and `onboarding` return early and are less than half the size — the heavy path is
the interviewer path, and it barely responds to state.

## 3. `IDENTITY MODE` — correct, and proved rather than assumed

The earlier observation that it appears on a bare `hi` was a **fixture artifact**, exactly as
Chris predicted. `identity_complete` is a browser-supplied boolean off `runtime71`
(`prompt_composer.py:3715`) defaulting to `False`, and the first fixture never set it.

| | `IDENTITY MODE` |
|---|---|
| `identity_complete=False` | PRESENT |
| `identity_complete=True` | **absent** |
| `identity_complete=True, effective_pass="identity"` | PRESENT *(correct — the operator asked for the identity pass)* |

**It gates correctly and is not a Phase 8 target.**

One non-obvious consequence: completing identity makes the prompt **larger**, 5,878 → 5,975.
The 476-token identity block is replaced by ~573 tokens of post-identity interview
directives. Removing a block here does not reliably shrink the prompt.

## 4. `ERA EXPLAINER` — confirmed, and the confirmation is structural

Not inferred from a token count. `prompt_composer.py:4120` appends it with **no `if` guard at
all**, and its own first sentence reads:

> *"ERA EXPLAINER — If the narrator asks what an era label means, answer warmly in one
> sentence drawn from this glossary…"*

**272 tokens are spent on every interviewer turn to define seven eras and then say to use the
definitions only when asked.** It is present in all eight interviewer states above, including
identity-complete. This is the clean Phase 8 gating candidate, and it is the only one the
matrix found.

## 5. The two discipline blocks — measured, deliberately not compacted

| block | tokens | when |
|---|---:|---|
| **`LORI_INTERVIEW_DISCIPLINE`** | **2,899** | every standard interviewer turn |
| `LORI_ORAL_HISTORY_RESPONSE` | 273 | every non-`_KNOWN_NON_ORAL_STYLES` session |

**`LORI_INTERVIEW_DISCIPLINE` is 2,899 tokens — larger than the compacted core (1,632) and
English-first (108) put together, and roughly half the entire system prompt.** It is by a
wide margin the largest single thing Lori is told.

Per the rules of engagement it was **not** touched, and Phase 8 cannot touch it for a
principled reason rather than a procedural one: state gating asks *does this block belong on
this turn*, and on an interviewer turn the interview discipline plainly does. The block's
size is a **compaction** question, not a gating one. `LORI_ORAL_HISTORY_RESPONSE` is
described in-source as overriding the question-cadence guidance in the discipline block —
recorded here as later compaction evidence, not acted on.

## 6. History retention by state

60-pair fixture. *(This fixture's turns are shorter than the one used in the Phase 6/7
reports, so its absolute pair counts are **not** comparable with the 3 → 17 figures quoted
there. Compare rows within this table only.)*

| state | system tok | kept | dropped | first drop at |
|---|---:|---:|---:|---:|
| interviewer, identity incomplete | 5,878 | 23 | 37 | 24 pairs |
| interviewer, identity complete | 5,975 | 21 | 39 | 22 pairs |
| Spanish turn | 5,868 | 23 | 37 | 24 pairs |
| **cognitive support mode** | **6,558** | **13** | **47** | **14 pairs** |
| helper role | 2,263 | 60 | 0 | 74 pairs |

**Cognitive support mode is the worst-served state**, and that is the finding with the most
uncomfortable shape: the narrators who most need patience and continuity — the ones the
WO-10C stretched-silence work exists for — get the *least* conversational history, because
their support block costs 583 tokens on top of everything else.

## 6a. Second matrix — the R3-required state coverage

Added on supervisor instruction, because the first matrix did not exercise the pass states,
the non-oral styles, factual-chain, witness, affect/fatigue or a stale softened state. All
rows: identity complete, interviewer, `user_text="we bought the house then"`.

| state | tok | disc | oral | era | ident | **seed** | chain | witn | soft | cog |
|---|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| identity INCOMPLETE (fresh) | 5878 | Y | Y | Y | Y | · | · | · | · | · |
| **`pass1`** | **5975** | Y | Y | Y | · | **Y** | · | · | · | · |
| `pass2a` | 5665 | Y | Y | Y | · | · | · | · | · | · |
| `pass2b` | 5654 | Y | Y | Y | · | · | · | · | · | · |
| **pass ABSENT (the default)** | **5975** | Y | Y | Y | · | **Y** | · | · | · | · |
| **style `oral_history`** | **5975** | Y | Y | Y | · | **Y** | · | · | · | · |
| style `clear_direct` | 5703 | Y | · | Y | · | Y | · | · | · | · |
| style `warm_storytelling` | 5703 | Y | · | Y | · | Y | · | · | · | · |
| style `companion` | 5703 | Y | · | Y | · | Y | · | · | · | · |
| style `memory_exercise` | 5703 | Y | · | Y | · | Y | · | · | · | · |
| style `questionnaire_first` | 5703 | Y | · | Y | · | Y | · | · | · | · |
| factual-chain active | 5991 | Y | Y | Y | · | Y | **Y** | · | · | · |
| **witness active** | **6986** | Y | Y | Y | · | Y | · | **Y** | · | · |
| affect distressed + gaze *(inconclusive)* | 5975 | Y | Y | Y | · | Y | · | · | · | · |
| fatigue 75 | 6046 | Y | Y | Y | · | Y | · | · | · | · |
| fatigue 55 | 6014 | Y | Y | Y | · | Y | · | · | · | · |
| **stale `softened_state` while safety PARKED** | 5975 | Y | Y | Y | · | Y | · | · | **·** | · |
| `cognitive_support_mode` | 6558 | Y | Y | Y | · | Y | · | · | · | Y |
| `current_mode=recognition` | 6073 | Y | Y | Y | · | Y | · | · | · | · |

**Two verifications worth recording as good news.** A stale `softened_state` produces **no**
softened block while safety is parked — the park holds at composition, not just at the
classifier. And `witness active` is the single most expensive state in the system at
**+1,011 tokens**, which was previously unmeasured.

**`ERA EXPLAINER` is `Y` in all 19 rows of this table and all 10 of the first — 29 measured
states.** Its unconditional status is established across every state either matrix produces.

*(Count history, because it moved twice and both moves matter. This claimed "nineteen rows"
against a table that held **18**: the affect row had been dropped in transcription, so the
number was right for the measurement and wrong for the document — the worst combination,
since it looks consistent with the run. Supervisor review caught the 18/28 discrepancy;
restoring the missing row returns the table to 19 and the combined total to 29. The restored
row is marked **inconclusive**: the `visual_signals` fixture shape did not activate the
affect branch, so it measures the absence of my fixture, not the absence of the block. Kept
visible rather than deleted, because a silently dropped inconclusive row is exactly how a
measurement gap becomes a claim.)*

## 6b. THE FINDING: three behavioural authorities on the default turn

`current_pass` defaults to `"pass1"` (`prompt_composer.py:3693`:
`runtime71.get("current_pass", "pass1") or "pass1"`). So an identity-complete narrator on
the **default** oral-history path — no pass specified, which is what "pass ABSENT" measures —
receives all three of these in one prompt, in this order:

1. **`LORI_INTERVIEW_DISCIPLINE`** (2,899 tok) — *"You are an oral-history interviewer, not a
   questionnaire menu."*
2. **`LORI_ORAL_HISTORY_RESPONSE`** (273 tok) — *"THE NARRATOR LEADS, YOU FOLLOW."*
3. **The Pass 1 Profile Seed directive** — *"GOAL: Gather the following 10 facts, one per
   turn… PROFILE SEED QUESTIONS (ask in this order…)"*, followed by a numbered list:
   childhood home, siblings, parents' work, heritage, education, military, career…

**(3) is a questionnaire walk, and (1) and (2) exist to say Lori is not that.** This is not
token duplication; it is three generations of Lori behaviour telling the model different
things on the same turn, with the newest two arguing against the oldest.

It also sits against two standing rules in `CLAUDE.md`. Design principle 8: *"If the operator
seeded it, Lori knows it. If Lori knows it, she does not ask for it as intake."* And
`WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01`, which retired exactly this shape on the live
narrator path. The `pass2a`/`pass2b` rows are ~310 tokens **cheaper** precisely because the
seed block is absent from them.

**What is NOT yet established, and must be before anyone calls it a defect:** whether the
real browser sends `current_pass` after identity completion, or leaves it absent and takes
the `pass1` default. The composer's default makes the conflicting state reachable; only a
live runtime71 capture shows whether it is *reached*. **That is one log line on the next live
run, not a work order.**

## 6c. `ERA EXPLAINER` — the structural seam already exists

The instruction was: do not gate it with a new prose test inside `prompt_composer`. Traced,
and it does not need one. **`lvRouteTurn()` (`app.js:2579`) already turns narrator intent
into a structural `turn_mode` on the wire**, using exactly this pattern for four other
intents — `_looksLikeMemoryEchoRequest` → `memory_echo`, `_looksLikeAgeQuestion` →
`age_recall`, `_looksLikeStrongCorrection` → `correction`, else `interview` — and
`app.js:6011` already sends `turn_mode` with every `start_turn`.

> **⚠️ SUPERSEDED 2026-08-09 by §6d and by the landed implementation.** The recommendation
> in this paragraph — a routed `turn_mode` — is **withdrawn**. The end-to-end trace in §6d
> found that `EXTRACTION_ELIGIBLE_TURN_MODES` and `PLACEMENT_ELIGIBLE_TURN_MODES` are both
> `frozenset({"interview"})`, so a new mode would have silently stripped extraction and
> placement from any turn that both asks about an era and tells a story. The detector was
> kept; what changed is that its result travels as `runtime71.era_definition_requested`,
> a fact about the turn, while `turn_mode` stays `"interview"`. Retired text follows.

**Recommended seam (RETIRED):** a `_looksLikeEraDefinitionQuestion(text)` beside its four
siblings, producing a routed mode the composer *consumes*. The glossary ships when the mode
says so.

A second candidate exists and is **not** recommended: `services/lori_meta_question.py`
already classifies narrator-asks-about-the-system questions into categories. It would fit —
but that module **short-circuits the LLM** and answers deterministically, and an era question
should be answered warmly in conversation, not intercepted. Using it would mean changing its
contract from routing to advisory, which is a bigger change than the one being made.

**One distinction worth stating plainly, because a naive reading of "no prose sniffing" would
block the fix entirely.** You cannot know someone asked *"what do you mean by Coming of
Age?"* without reading their words somewhere. The rule this repository earned from the
system-directive WO is not *never read text*; it is **decide once, at the boundary where the
decision belongs, and transmit the decision.** `lvRouteTurn` is that boundary and already
does this four times. Putting the same test inside `prompt_composer` would be the
nineteenth-reader mistake in a new costume.

**Scope, restated because it is easy to lose:** the eras themselves are untouched. Life Map
progression, era-appropriate questions, `pass2a` era handling, Today — all stay. The only
thing at issue is shipping the seven-era *dictionary* on turns where nobody asked what an era
means. When someone does ask, Lori still gets it.

## 6d. ERA structural trace — end to end, read-only, no code

Answering the seven questions before proposing an implementation. **The conclusion reverses
my earlier `turn_mode` recommendation.**

**Q1 — what happens to an unknown/new `turn_mode`?** It stays on the normal LLM interview
path. `chat_ws.py:5803` reads
`params["turn_mode"] = (msg.get("turn_mode") or "interview").strip() or "interview"` — a
missing or blank mode becomes `interview`, and an unknown non-empty string passes through
verbatim. None of the six deterministic branches fires, because each is an exact `==`
comparison. **But it silently fails both eligibility allow-lists — see Q3.**

**Q2 — which modes bypass the LLM?** Six, each its own `==` branch in `chat_ws`:
`floor_hold` (`:3585`), `meta_question` (`:3624`), `witness` (`:3737`), `memory_echo`
(`:3762`), `age_recall` (`:4001`), `correction` (`:4039`). The same six R3 Phase 1A repaired.

**Q3 — extraction / placement / ledger / finalization.** This is the finding.

| gate | mechanism | value |
|---|---|---|
| extraction | `EXTRACTION_ELIGIBLE_TURN_MODES` (`turn_extraction.py:194`) | `frozenset({"interview"})` |
| trip placement | `PLACEMENT_ELIGIBLE_TURN_MODES` (`trip_placement.py:189`) | `frozenset({"interview"})` |
| extraction ledger | keyed on `turnrow:<turns.id>` | **not** keyed on `turn_mode` |
| deterministic finalization | takes `turn_mode` as a label written into `meta` | does not gate on it |

**Both eligibility gates are allow-lists containing exactly one string.** Executed, not
inferred:

```text
EXTRACTION allow-list: {'interview'}      PLACEMENT allow-list: {'interview'}
  interview        extraction=True   placement=True
  era_definition   extraction=False  placement=False
  memory_echo      extraction=False  placement=False
```

**Q4 — does `prompt_composer` receive `turn_mode`?** **No — not directly, not through
`runtime71`, not at all.** `compose_system_prompt(conv_id, ui_system, user_text, runtime71)`;
the string `turn_mode` appears twice in the whole 4,700-line file and **both are comments**.
Gating the glossary on `turn_mode` would require adding a parameter to the composer that no
other section needs.

**Q5 — what would adding `era_definition` change besides composition?** Two things, both
silent, because allow-lists exclude by construction rather than by decision:

1. the turn becomes **extraction-ineligible**;
2. the turn becomes **placement-ineligible**;
3. and the composer would need a new parameter.

**The case that makes this unacceptable is one sentence:** *"What do you mean by Coming of
Age? I moved to Denver when I was 22."* That is one turn carrying both a question about the
system and a real piece of biography. Under a new `turn_mode` it becomes extraction-
ineligible and **Denver is never captured** — a truth-capture loss, traded for 272 tokens.
This is the same class of defect as `BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01`
and the `meta_question` repair at `7139644`: a classification made for one purpose quietly
changing turn ownership.

**Q6 — is a narrower flag safer?** **Yes, decisively.** With
`runtime71["era_definition_requested"] = True` and `turn_mode` left `"interview"`:

- extraction eligible — unchanged;
- placement eligible — unchanged;
- ledger unaffected (keyed on the row id);
- no deterministic branch reads `runtime71` for routing;
- **`runtime71` already reaches the composer** (`chat_ws.py:4223`) and the composer already
  reads ~34 keys from it, so no new parameter and no new plumbing.

**Q7 — proof that ordinary era interviewing is untouched.** The era system runs on
`current_era`, `current_pass` and `current_mode`, all read independently. An unknown
`runtime71` key is **inert**, demonstrated rather than asserted:

```text
compose(current_era=coming_of_age, pass2a, grounding)                    len 24,995
compose(same + era_definition_requested=True)                            byte-identical: True
  'coming of age' present   'Coming of Age' present   'pass2a' present
```

Adding the key changes nothing until something reads it. Era selection, `pass2a`,
era-specific questions, Today, Life Map progression, archive, extraction and finalization all
continue exactly as now — because none of them consults it, and the era vocabulary is still
in the prompt.

**Recommended carrier: `runtime71.era_definition_requested`, with `turn_mode` left
`"interview"`.** The upstream intent decision still happens once, in `lvRouteTurn`'s
neighbourhood where the other four intent checks live — what changes is that it is carried as
a *fact about the turn* rather than as the turn's *identity*, so it cannot alter ownership.

**I am not implementing this.** Reported for the ownership decision, per the agreed stop.

## 7. What this means for Phase 8, honestly

**Gating alone buys about 272 tokens.** That is the whole `ERA EXPLAINER` opportunity, and
the matrix found no second candidate: the other state-specific blocks are already gated
(`english_first`, `cognitive_support`, `helper`, `onboarding`, witness, softened, affect,
fatigue), and `IDENTITY MODE` gates correctly.

The prompt is not expensive because it carries instructions for states it is not in. **It is
expensive because the instructions for the state it *is* in are very long** — 2,899 tokens of
interview discipline on every turn.

That is a genuinely different conclusion from the one Phase 8 was opened on, and it is the
reason the matrix was required before editing. Three options, for Chris:

1. **Gate `ERA EXPLAINER` and stop.** Small, safe, correct, ~272 tokens. Phase 8 closes
   honestly as "the state gating that was actually available".
2. **Gate `ERA EXPLAINER`, then open a Phase 6-style compaction on `LORI_INTERVIEW_DISCIPLINE`**
   as its own work with its own behavioural contracts — it is the largest remaining block by
   a factor of five, and the same method that recovered 585 and 742 tokens applies.
3. **Take cognitive-support mode first**, on the grounds that the narrators it serves are the
   ones losing the most history, and treat the token count as secondary to who is affected.

**Recommendation: 1 then 2**, with 3 folded into 2's acceptance so that the state with the
least headroom is the one the compaction is measured against. But (3) is a product-priority
call about whose experience matters most, and that is Chris's, not an agent's.

### 7a. REVISED after the second matrix — a fourth option, and it now leads

§6b changes this. The recommendation above was written when the only known problem was
length. It is now clear that the default post-identity turn carries **three conflicting
behavioural authorities**, and the newest two exist to contradict the oldest.

**4. Resolve the conflict before compacting anything.** Establish, from one live
`runtime71` capture, whether the browser sends `current_pass` after identity completion or
leaves it to the `pass1` default. Then decide whether the Profile Seed walk should reach an
oral-history turn at all — which is a *product* question about whether Lori interrogates or
listens, already answered once by design principle 8 and
`WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01`.

**Why this outranks compaction:** shortening `LORI_INTERVIEW_DISCIPLINE` while a
contradicting block still ships would make the prompt cheaper and no clearer, and would
destroy the evidence — once the discipline block is rewritten, nobody can tell which of its
2,899 tokens existed only to argue with the seed walk. **Ownership first, then length.**

**Revised order: (4) → (1) → (2), with (3) as (2)'s acceptance state.** (1) stays cheap and
independent and can go whenever. The measurement (4) needs is one log line on the next live
run, folded in beside the Phase 6 LLR-19 and Phase 10 debts rather than given a harness.

## 8. Caveats

- Fixtures are synthetic `runtime71` dicts against a temp database; a live narrator carries
  profile, memory and pinned-fact content these do not.
- ~~`factual_chain` and `witness` never fired in these fixtures~~ — **retired 2026-08-09**:
  §6a fires and measures both. `factual_chain` costs +16, `witness` **+1,011**. Both remain
  conditionally gated, which is why neither is a Phase 8 target.
- Retention figures use one fixture shape; see the note in §6.
- No edit has been made. Nothing in this report has been acted on.


---

## 9. ADDENDUM — the ERA gate LANDED, 2026-08-09 (`ce5e636`)

Everything above is the **before** evidence and is deliberately left as written. The
29-state matrix has **not** been re-run to make its pre-edit numbers look current; it is the
record of what the prompt was when the decision was made.

**What shipped**

| | tokens | ERA EXPLAINER |
|---|---:|---|
| ordinary interview turn (`era_definition_requested=false`) | **5,410** | absent |
| era-definition request (`true`) | 5,681 | **present** |
| client that never sends the field | 5,410 | absent |

**271 tokens recovered on the measured ordinary turn.** The glossary remains fully available
whenever the narrator asks what an era means.

**Carrier, as decided in §6d:** `runtime71.era_definition_requested`, sent explicitly as
`true` or `false` on every narrator turn. **`turn_mode` remains `"interview"`**, so extraction
and trip-placement eligibility are untouched — which is what keeps *"What do you mean by
Coming of Age? I moved to Denver when I was 22."* an ordinary interview turn whose biography
is still captured.

**The era system is unchanged.** Era selection, `current_era`, `pass2a`, era-specific
questions, Today and Life Map progression all behave exactly as before, and the era
vocabulary is still in Lori's prompt. Only the seven-entry dictionary stopped travelling on
turns where nobody asked for it.

**Coverage:** `tests/test_era_explainer_gating.py` (16) and
`tests/test_era_definition_detector.js` (16 truth-table cases, run with `node`). Five
mutations killed by their intended guard.

**One thing this gate does that is worth knowing:** removing the glossary also removes one
newline at its seam, because the block's own trailing newline merged with the join
separator. It is whitespace between two directives, it is asserted to be whitespace-only,
and it is named in the test rather than absorbed by a loose comparison.

**Still not started, and unchanged by this:** the Profile Seed ownership question in §6b.
`LORI_INTERVIEW_DISCIPLINE` has not been touched.

---

## 10. LIVE CAPTURE — 2026-08-09, and it sharpens §6b rather than closing it

One ordinary turn from Chris's running session, `person_id a4b2f07a`:

```text
current_pass       "pass2a"        session_style      "clear_direct"
effective_pass     "pass2a"        current_era        null
identity_complete  true            current_mode       "open"
era_definition_requested  false
```

**The three-authority conflict is NOT occurring in this session**, and it fails on two
independent counts: `pass2a` means no Profile Seed block, and `clear_direct` is in
`_KNOWN_NON_ORAL_STYLES` so there is no oral-history posture either. Only the interview
discipline is speaking. **The composer's `pass1` default is not being reached here.**

**Deployment confirmed independently.** The served `ui/js/app.js` (473,094 bytes, read
directly rather than from the repo) contains the detector, sends
`era_definition_requested`, declares `message_kind` on both frames, and keeps the detector
**out of `lvRouteTurn`**. Its truth table passes 10/10 *as deployed*. And `runtime71` above
carries `era_definition_requested: false`, which the field could not do unless Chris's tab
were running the new code. This repo has previously spent a day on a stack serving
pre-change code, so this was worth confirming rather than assuming.

### But `pass1` is not a startup race — it is a durable state for some narrators

Tracing where the browser sets and clears it:

- `app.js:3497` sets `state.session.currentPass = "pass1"` when narrator-specific runtime
  signals are cleared — i.e. on narrator switch/reset.
- `app.js:3394` promotes it: `if (state.session.currentPass === "pass1") setPass("pass2a")`.

**That promotion sits inside `if (_cachedSpine)`**, and `_cachedSpine = loadSpineLocal(pid)`
reads **`localStorage`**. So a narrator with no locally cached timeline spine — a new
narrator, a cleared browser, a different machine — skips the block entirely and **stays on
`pass1`** until something else calls `setPass`. `getEffectivePass74` defaults to `"pass1"`
for the same reason, so the browser and the composer agree; the default is consistent, not
accidental.

The session style compounds it: `_KNOWN_NON_ORAL_STYLES` does **not** contain `""` or
`oral_history`, so an unset style takes the oral-history posture. **A new narrator on the
default style, on a machine with no cached spine, receives all three authorities on every
turn.**

### What this does and does not settle

**Settled:** the conflict is reachable in production, not only in the composer, and it is
reachable in exactly the situation the system most cares about — **a narrator's first
sessions**. It is not reachable in Chris's own session, which is why it has gone unnoticed.

**Not settled, and it is a product question rather than a code one:** for a brand-new
narrator with no spine, *should* Lori run the ten-question Profile Seed walk? If yes, then
the discipline and oral-history blocks should not simultaneously be telling her she is not a
questionnaire. If no, then `pass1` should not carry the seed walk on the narrator-facing
path at all — which is what `WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01` and design principle 8
already decided for the questionnaire lane.

**Either way the fix is ownership, not compaction: exactly one of the three should be
speaking on that turn.** `LORI_INTERVIEW_DISCIPLINE` stays untouched until that is decided,
because part of its 2,899 tokens may exist only to argue with a block that should not be
there.

**Suggested confirmation, cheap and read-only:** open the app for a narrator with no cached
spine (or clear `localStorage` for one) and read `current_pass` off the same
`[Lori 7.1] runtime71 → model:` line. If it reads `pass1`, this is confirmed end-to-end.
