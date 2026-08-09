# Lean Lori Phase 8 — state matrix

**Date:** 2026-08-09 · **Measurement only. No code was changed.**
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
| identified ready `hi` *(corrected)* | **5975** | Y | Y | Y | **·** | Y | Y | Y | · | · |
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

**The interviewer path is very nearly state-invariant.** Eight of ten states sit within
**±1 token** of 5,878. Only three things move it at all: Spanish correctly drops
English-first (−107), cognitive support adds its block (+583), and photos add a line (+56).
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
| fatigue 75 | 6046 | Y | Y | Y | · | Y | · | · | · | · |
| fatigue 55 | 6014 | Y | Y | Y | · | Y | · | · | · | · |
| **stale `softened_state` while safety PARKED** | 5975 | Y | Y | Y | · | Y | · | · | **·** | · |
| `cognitive_support_mode` | 6558 | Y | Y | Y | · | Y | · | · | · | Y |
| `current_mode=recognition` | 6073 | Y | Y | Y | · | Y | · | · | · | · |

**Two verifications worth recording as good news.** A stale `softened_state` produces **no**
softened block while safety is parked — the park holds at composition, not just at the
classifier. And `witness active` is the single most expensive state in the system at
**+1,011 tokens**, which was previously unmeasured.

**`ERA EXPLAINER` is `Y` in all nineteen rows of this table and all ten of the first.** Its
unconditional status is now established across every state either matrix can produce.

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

**Recommended seam:** a `_looksLikeEraDefinitionQuestion(text)` beside its four siblings,
producing a routed mode the composer *consumes*. The glossary ships when the mode says so.

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
- `factual_chain` and `witness` never fired in these fixtures, so their cost is unmeasured
  here. Both are already conditionally gated.
- Retention figures use one fixture shape; see the note in §6.
- No edit has been made. Nothing in this report has been acted on.
