# BUG-EX-PLACE-LASTNAME-FOLLOWUP-01 — Place-as-lastName binding under follow-up question context

**Title:** Block place→lastName binding when narrator answers a "last name?" follow-up with a recently-disclosed place noun
**Status:** SCOPED — ready to build (small, additive, eval-gated)
**Date:** 2026-05-02
**Lane:** Extractor / Binding-layer cleanup
**Source:** Live runtime trace 2026-05-01 23:01:38 (post-eval narrator session, Janice + Christopher canon)
**Blocks:** Nothing. Pre-parent-session cleanup; complements BUG-EX-PLACE-LASTNAME-01.
**Companion:** Architecture Spec v1 §7.1 (binding-layer failures); BUG-EX-PLACE-LASTNAME-01 (the inline-shape guard already shipped).

---

## Mission

The original BUG-EX-PLACE-LASTNAME-01 guard at `server/code/api/routers/extract.py` correctly drops `parents.lastName=Stanley` when the source text contains "in Stanley" / "born in Stanley" — i.e., the value sits after a place-preposition in the same span. **It does not fire when the narrator answers a follow-up "what's your dad's last name?" with just the noun.**

Live trace evidence (2026-05-01 23:01:38):

> Section: `early_caregivers`
> Prior turn established: parents.firstName=Kent, parents.lastName=Horne, parents.birthPlace=Stanley
> Follow-up question: "what's your dad's last name?"
> Narrator answer (single noun): "Stanley"
> LLM raw output: `{"fieldPath": "parents.lastName", "value": "Stanley", "confidence": 0.9}`
> Original guard: did not fire (no place-preposition in answer span)
> Outcome: `parents.lastName=Stanley` accepted, polluting the extraction

This is the same class of binding error as the inline form, just cued by a different conversational shape. The narrator did NOT mean to assign their father's last name as "Stanley" — they almost certainly mis-spoke, mis-heard the question, or the STT clipped a longer answer. Either way, the existing canon already has `parents.lastName=Horne` for Janice's father, so this is a clean overwrite-of-correct-data bug.

---

## Locked design rules

1. **Additive guard, not replacement.** The original BUG-EX-PLACE-LASTNAME-01 inline-shape guard stays exactly as-is. This WO adds a second guard for the follow-up shape.
2. **No prompt change.** The extraction path is already prompt-tuned; a new few-shot example here would burn token budget and risk side-effects on other binding decisions.
3. **No LLM call.** The guard is deterministic post-LLM, same posture as the original.
4. **Conversation-state-aware, not narrator-state-aware.** The guard uses the *current extraction call's recently-emitted items* and the *prior conversation turn's place mentions* — not the narrator's full canon. Reasoning: pulling from canon would interact with the protected-identity / Phase G layer in ways that need their own audit.
5. **Suggest_only, not drop.** When the guard fires, the item downgrades to `writeMode=suggest_only` (same posture as Phase G protected-identity conflicts) instead of being dropped outright. The narrator might genuinely answer a "last name?" question with a surname that happens to be a place — operator review is the right adjudicator.

---

## Fix shape

Three implementation options, ranked.

### Option A (lead, scope-limited) — Cross-emission guard, post-LLM, SAME-CALL only

In the same `extract_fields()` call where the LLM emits `{lastName, value=X, ...}`, check whether the call ALSO emitted `{birthPlace, value=X, ...}` or `{placeOfBirth, value=X, ...}` for the same entity prefix (parents / grandparents / siblings / spouse / family.*). If yes AND the lastName value is exactly equal (case-insensitive) to a place value emitted in the same call → downgrade lastName to `suggest_only` and emit `[extract][PLACE-LASTNAME-FOLLOWUP] downgrade fieldPath=<X>.lastName value=<Y> reason=co_emitted_with_place`.

**Honest scope note (added 2026-05-02 during build):** this catches the *compound-utterance* shape where the narrator says both the place and the lastName-matching-place in the same turn (e.g., "Dad was born in Stanley and his last name was Stanley too"), and the LLM emits both in the same call. It does NOT catch the original live-trace evidence at 2026-05-01 23:01:49 where the narrator answered "Stanley" alone to a "what's dad's last name?" follow-up — in that call the LLM emitted only `parents.lastName=Stanley` and never re-emitted the place from prior turns. That across-turn shape requires Option A2 (below) and is filed as future work.

**Why Option A is still the lead:** the within-call compound shape is a real subclass observed in production logs (whenever the narrator's utterance contains both signals), and the fix is zero-state, zero-wiring, single-file. Ship the catchable subset now; defer the across-turn case.

### Option A2 (future) — Across-turn turn-context place memory

Pass the prior turn's accepted-items list as an optional `recent_places: List[str]` field on the `ExtractFieldsRequest` (or compute it server-side from `req.conversation_history` if that's already wired). The cross-emission guard then unions `_emitted_places` (this call) with `_recent_places` (prior turns) before the per-item check. Catches the across-turn follow-up shape from the live trace.

**Why this is future:** requires runtime-side wiring of the recent-places list into the request payload (or a server-side conversation buffer keyed by `conv_id`). More state, more surface area. Build after Option A's coverage is locked in the eval and the across-turn class still produces visible noise in live traces. File as **BUG-EX-PLACE-LASTNAME-FOLLOWUP-02** when triggered.

### Option C (rejected) — Prompt-side few-shot

Add a few-shot example to the extraction prompt showing "what's your dad's last name?" → narrator answers a place noun → emit `{lastName: X, writeMode: suggest_only}`. Rejected because (a) burns token budget, (b) risks side-effects on other binding decisions, (c) not deterministic enough for a suggest_only downgrade rule.

---

## Implementation (Option A)

`server/code/api/routers/extract.py`. Add a helper near the existing `_drop_place_as_lastname()` (which BUG-EX-PLACE-LASTNAME-01 introduced):

```python
def _downgrade_followup_place_as_lastname(items: List[Dict]) -> List[Dict]:
    """
    BUG-EX-PLACE-LASTNAME-FOLLOWUP-01: when an extraction call emits
    BOTH a lastName AND a birthPlace/placeOfBirth for the same entity
    prefix AND the lastName value equals a place value (case-insensitive),
    downgrade the lastName to suggest_only.

    Catches the follow-up shape: narrator answered a "what's the last
    name?" question with just a place noun, and the LLM bound it to
    lastName because of question-context priming.
    """
    # Gather (prefix, value) tuples for places emitted in this call
    place_tuples: Set[Tuple[str, str]] = set()
    for it in items:
        fp = (it.get("fieldPath") or "").lower()
        val = (it.get("value") or "")
        if not fp or not val or not isinstance(val, str):
            continue
        if fp.endswith(".birthplace") or fp.endswith(".placeofbirth"):
            prefix = fp.rsplit(".", 1)[0]
            place_tuples.add((prefix, val.strip().lower()))

    if not place_tuples:
        return items

    # For each lastName item, check if the same prefix has a matching place
    for it in items:
        fp = (it.get("fieldPath") or "").lower()
        if not (fp.endswith(".lastname") or fp.endswith(".maidenname") or fp.endswith(".middlename")):
            continue
        val = (it.get("value") or "")
        if not val or not isinstance(val, str):
            continue
        prefix = fp.rsplit(".", 1)[0]
        val_norm = val.strip().lower()
        for (place_prefix, place_val) in place_tuples:
            if place_prefix == prefix and place_val == val_norm:
                it["writeMode"] = "suggest_only"
                it["downgradeReason"] = "co_emitted_with_place_followup"
                LOGGER.info(
                    "[extract][PLACE-LASTNAME-FOLLOWUP] downgrade fieldPath=%s value=%r "
                    "reason=co_emitted_with_place prefix=%s",
                    it.get("fieldPath"), val, prefix
                )
                break

    return items
```

Wire-in: call `_downgrade_followup_place_as_lastname()` after the existing `_drop_place_as_lastname()` and before the protected-identity (Phase G) check, in the same loop position used by BUG-EX-PLACE-LASTNAME-01.

**LOC:** ~30 lines. Single-file change. Zero schema changes.

---

## Eval cases (4 new fixtures)

Add to `data/qa/question_bank_extraction_cases.json`:

- **case_111** — Father's last name follow-up, narrator answers place. Source: prior turn established `parents.birthPlace=Stanley`; follow-up "what's your dad's last name?" → answer "Stanley". must_extract: `parents.birthPlace=Stanley`. must_not_write: `parents.lastName=Stanley`.
- **case_112** — Mother's last name follow-up, narrator answers place. Same shape, mother variant. Source establishes `parents.birthPlace=Spokane`; follow-up "what's your mom's last name?" → answer "Spokane". must_not_write: `parents.lastName=Spokane`.
- **case_113** — Negative case (the real surname). Narrator answers "Horne" to "what's your dad's last name?" — guard MUST NOT fire because "Horne" was not co-emitted as a place. must_extract: `parents.lastName=Horne`.
- **case_114** — Compound shape (full identity utterance). "My dad's name was Kent Horne, born in Stanley" → must extract all three (firstName=Kent, lastName=Horne, birthPlace=Stanley). Guard must NOT fire on lastName=Horne (not co-emitted as place). Tests that the new guard doesn't false-positive on the inline-disclosure shape that the original guard already handles cleanly.

Master pack 110 → 114.

---

## Acceptance criteria

- [ ] case_111 + case_112 PASS (lastName downgraded to suggest_only).
- [ ] case_113 PASSES (real surname not downgraded).
- [ ] case_114 PASSES (compound full-identity utterance still extracts cleanly).
- [ ] Master eval at tag `r5h-followup-guard` shows ≥75/114 (no regression on existing 110 cases) and the 4 new cases all pass.
- [ ] `[extract][PLACE-LASTNAME-FOLLOWUP] downgrade` log line fires on case_111 + case_112, does not fire on case_113 + case_114.
- [ ] No effect on cases 105–110 (the original BUG-EX-PLACE-LASTNAME-01 fixtures still pass via the original inline-shape guard, not the new follow-up guard).
- [ ] Live verification: re-create the 2026-05-01 23:01:38 trace condition (early_caregivers section, prior turn discloses place, follow-up "last name?" with place answer) and confirm the runtime log shows the downgrade.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Guard false-positives on compound utterance ("my dad Kent Horne, born in Stanley" — extracts both lastName=Horne AND birthPlace=Stanley in same call). | The guard checks for *exact value match* (case-insensitive). Horne ≠ Stanley → no false-positive. case_114 locks this. |
| Narrator's actual surname genuinely matches a place name (e.g., "my father's name was Stanley Stanley, born in Stanley"). | Suggest_only downgrade preserves the candidate for operator review; no data is lost. The candidate appears in the Bug Panel candidate review queue with `downgradeReason=co_emitted_with_place_followup` for adjudication. |
| Cross-prefix interaction (e.g., narrator's grandparents.birthPlace=Stanley AND parents.lastName=Stanley). | Guard only matches within the same prefix (parents/grandparents/etc.). Different prefixes → no downgrade. |
| Future fields with `.birthPlace` or `.placeOfBirth` suffix emerge that should NOT participate in the cross-check. | The prefix list is implicit (any field path ending in `.birthplace` / `.placeofbirth` qualifies). If a future schema adds something like `event.birthPlace` for an unrelated entity, this would over-match. **Mitigation:** keep the place-suffix check on `personal.* / parents.* / grandparents.* / siblings.* / spouse.* / family.*` prefixes only; whitelist explicitly. |

---

## File touch summary

**Modified:**
- `server/code/api/routers/extract.py` (~30 lines: helper + wire-in)
- `data/qa/question_bank_extraction_cases.json` (+4 cases)

**No changes to:**
- Schema
- Eval harness
- Frontend
- Prompts

---

## Lorevox graduation note

Pairs with the original BUG-EX-PLACE-LASTNAME-01 guard for graduation. Both are deterministic post-LLM regex/cross-emission guards; they generalize to any narrator universe trivially (the place→lastName confusion is universal, not Horne-family-specific). Add to `docs/lorevox/GRADUATION_CANDIDATES_2026-05-01.md` Section A as candidate **A12** when this guard lands clean and BINDING-01 lane reopens.

---

## Definition of done

WO closed when:
- All 4 acceptance criteria pass.
- Master eval at tag `r5h-followup-guard` shows ≥75/114, no regressions on cases 1–110.
- `[extract][PLACE-LASTNAME-FOLLOWUP] downgrade` log marker observed in live runtime once.
- CLAUDE.md changelog entry recording the patch + the live-trace evidence that triggered it.
