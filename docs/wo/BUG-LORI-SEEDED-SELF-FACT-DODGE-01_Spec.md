# BUG-LORI-SEEDED-SELF-FACT-DODGE-01 — Lori declines to answer a factual question about the narrator's own seeded profile

**Status:** OPEN / not started. Filed 2026-08-12 from live evidence during the post-restart smoke session. Parked behind Travel Document work by decision the same day.

**Class:** interview-lane behaviour. **Not** a Travel Doc issue, not a restart failure, and not caused by any of the 2026-08-12 security/database changes (those landed and verified in the same session).

---

## 1. What happened

Live session `switch_msq9ghg7_q88f`, narrator `a4b2f07a…`, 2026-08-12 09:46:41.

The narrator corrected Lori and asked a direct question about his own life:

```
I did not grow up in New Mexico.  Where did I grow up?
```

Lori did not answer. The runtime had the answer available: `[chat_ws][profile-seed] sources: ui=0 server=9 merged=9` on that very turn — nine seeded fields were merged into the prompt. The narrator's birthplace (reported as Williston, North Dakota) was among the material the system holds.

**Verification owed before building:** the birthplace value was read out of the exported session archive by a reviewer, not confirmed by me against `profile_json` / `projection_json`. Step 1 of any fix is to dump `_build_profile_seed(person_id)` for this narrator and confirm which bucket carries the value and under what key. If the seed does *not* carry it, this is a different bug (a projection gap — see §6) and the fix below is wrong.

## 2. Supporting runtime evidence from the same turn

```
[utterance-frame] conf=partial clauses=2 unbound=N
    shape=self/unknown@New Mexico|obj=-|feel=-|neg=1|unc=0|hints=-
         ;self/unknown@-        |obj=-|feel=-|neg=0|unc=0|hints=-
[extract][CLAIMS-01] Compound answer detected: 2 names={'New Mexico', 'Where'}
[extract-parse] Raw LLM output: [{"fieldPath":"personal.placeOfBirth","value":"","confidence":0.0}]
[extract-validate] REJECT: empty fieldPath='personal.placeOfBirth' or value=''
[extract][silent-root] cause=parse_drop
```

Three things worth noting, because they are each *correct* and none of them is the bug:

- The utterance frame parsed the turn properly: two clauses, the first negated, place `New Mexico` bound to the negated clause. It did not mistake the retraction for an assertion.
- The extractor correctly wrote nothing. The narrator supplied no new fact; a question is not an answer. `personal.placeOfBirth=""` being rejected is the validator doing its job.
- `CLAIMS-01` treating `Where` as a name candidate is cosmetic noise here (nothing was written), though it is the same over-capture family as `_NAME_STOPWORD_BLOCKLIST`.

The defect is downstream of all of that: **the response layer had the fact and declined to say it.**

## 3. Why this matters more than one dodged question

This violates two locked design principles at once:

- **Principle 7 — "Mechanical truth must visibly project."** A value in `profile_json` / `projection_json` must reach the surfaces that consume it. It reached the prompt and then failed to reach the narrator.
- **Principle 8 — "Operator seeds known structure; Lori reflects what is there."** The stated rule is *"If the operator seeded it, Lori knows it."* An operator who seeds a birthplace and then watches Lori refuse to state it has been told the seeding did not take.

For an older-adult narrator the felt experience is worse than a wrong answer: they corrected the system, asked it to confirm what it knows, and got deflection. That reads as the system not listening — the exact failure mode `BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01` and the questionnaire-first retirement were fought over.

## 4. The fix pattern already exists in this repo — three times

This is a solved shape. **Do not solve it with prompt engineering** (see the locked 2026-05-02 Patch B principle: prompt-heavy rules make Lori worse). Route it deterministically.

| Precedent | Defect | Fix |
|---|---|---|
| `BUG-LORI-LATE-AGE-RECALL-01` (2026-05-06) | Both narrators' age questions dodged with *"Is there something else on your mind?"* | `compose_age_recall()` in `prompt_composer.py:2084` — pure-deterministic, no LLM, reads `age_years` from profile_seed; dispatched by `turn_mode == "age_recall"` at `chat_ws.py:4017` |
| `BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01` (2026-05-09) | *"What is your name?"* → *"I don't have a name"* | `services/lori_meta_question.py` — server-side intercept **before** the LLM, 5 categories, overrides `turn_mode` |
| `BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01` (2026-07-09) | Direct photo/date questions → continuation boilerplate | `answer_modal_direct_question()` in `travel_doc_lori_modal.py:357` — answers from approved record, else an honest *"I don't know that from the approved trip record yet"* |

**This bug is `age_recall` one field over.** Birthplace is arguably more basic than age (no arithmetic required — it is a stored string).

## 5. Proposed fix

### Phase 1 — verify the seed (blocking)
Dump `_build_profile_seed(person_id)` for the affected narrator. Confirm the birthplace value, its bucket and its key. If absent, stop and re-file as a projection bug.

### Phase 2 — deterministic self-fact recall route
Generalise the age-recall pattern to the other seeded self-facts a narrator can ask about directly. New `server/code/api/services/lori_self_fact_recall.py`, modelled on `lori_meta_question.py`:

- Detect the question class and the field it targets: *where was I born / where did I grow up / what's my name / when's my birthday / what did I do for work / where did I live*.
- Resolve from profile_seed only. Never infer, never let the LLM fill a gap.
- Answer in the shape `compose_age_recall` already uses — plain, warm, one sentence, then hand the floor back.
- When the seed does **not** carry it, say so honestly (*"I don't have where you grew up written down yet — would you like to tell me?"*) rather than deflecting. That sentence is the difference between a system that doesn't know and a system that won't say.

**Put the detector server-side, in `chat_ws`, not in the browser.** The `age_recall` precedent detects in `ui/js/app.js:2459` and sends `turn_mode`; that works but a cached page, the Travel Doc modal socket, or any non-browser client bypasses it entirely. `lori_meta_question`'s server-side intercept is the stronger of the two precedents and should be the model. Reuse its LAW-3 isolation gate (no imports from extract / chat_ws / db).

### Phase 3 — handle correction-plus-question in one turn
The narrator's utterance was *two* speech acts: a correction and a question. Detection must not be defeated by the leading correction clause — the utterance frame already splits them (`clauses=2`), so the detector should consult it rather than regex the whole string. Verify against the verbatim live text, not a paraphrase.

### Phase 4 — bilingual parity
`compose_age_recall` takes `target_language`; the Spanish branch exists. Match it, or explicitly defer with a note (Spanish-only narrators asking the same question is a live scenario per the Melanie sessions).

## 6. Alternative mechanism to rule out first

The 2026-05-09 **ANTI-CONFABULATION RULE** in `prompt_composer.py` forbids Lori from claiming *"you mentioned X"* unless X is supported by profile_seed / promoted truth / a literal narrator sentence. Profile-seed material **is** listed as supported, so the rule should not have suppressed this answer — but an LLM steered by that block plus interview discipline plus the oral-history posture may be generalising to *"don't assert biographical facts about the narrator."* If Phase 1 confirms the seed carried the value, capture the composed prompt for that turn and check whether the answer was suppressed by directive conflict. That would not change the fix (deterministic routing bypasses the whole question) but it belongs in the record, and it is a live data point for the Phase 8 conflicting-authorities matrix already open in the Lean Lori lane.

## 7. Acceptance

- The verbatim live turn — *"I did not grow up in New Mexico. Where did I grow up?"* — produces the seeded birthplace, in one sentence, with no deflection.
- A narrator whose seed lacks the field gets the honest "not written down yet" answer, not a deflection and not a guess.
- The question asked without a leading correction works identically.
- No extraction is triggered by a question (current correct behaviour preserved — the turn must still write nothing).
- The route is reachable from a non-browser client (server-side detection proven, not assumed).
- Both live phrasings appear as named regression tests so the exact wording cannot silently regress.

## 8. Out of scope

Extractor behaviour on this turn (correct as-is), `CLAIMS-01` treating `Where` as a name candidate (cosmetic, no write), the Lean Lori compaction lane, and anything in Travel Document.
