# BUG-EX-DISCOURSE-AS-NAME-01 — Rules-fallback name extraction captures discourse fragments as fullName candidates

**Status:** **PARTIAL FIX LANDED 2026-05-06** — `_NAME_STOPWORD_BLOCKLIST` extended with negation/uncertainty words (not / don't / can't / etc.); new `_NAME_DISCOURSE_FRAGMENT_RX` substring guard catches "not sure" / "don't know" / "what day" / "no idea" / etc. anywhere in the captured value.
**Severity:** AMBER — narrator-visible Shadow Review noise. Not a truth-write regression (BUG-312 protected-identity gate routes these to `suggest_only`), but operator review fatigue is real and the operator-facing surface looks broken.
**Surfaced by:** Mary's live session 2026-05-06 12:30+ — Mary said *"i am not sure what day is it"* in response to Lori's "What day is it today?" question. The `_NAME_FULL` regex captured "not sure what day" as a fullName candidate. Shadow Review showed the entry. Chris correctly named this as a broader class than the original NAME-EXTRACTION-NOW-01.
**Author:** Chris + Claude (2026-05-06)
**Lane:** Lane 1 / extractor cleanup. Independent of QF retirement.

---

## Problem

The rules-fallback name extraction path at `extract.py:6836+` uses `_NAME_FULL` regex with `re.IGNORECASE`:

```python
_NAME_FULL = re.compile(
    r"(?:my name is|I'm|I am|name was|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
    re.IGNORECASE
)
```

Under `IGNORECASE`, `[A-Z][a-z]+` matches lowercase starts. The pattern captures up to 4 words after "I am" / "I'm" / etc. So Mary's *"i am not sure what day is it"* matches "i am" as the prefix and captures "not sure what day" as a 4-word "name."

`BUG-EX-NAME-EXTRACTION-NOW-01` (LANDED 2026-05-05) added a first-token blocklist for single-word discourse markers ("now"/"yes"/"well"/etc.). But the blocklist's first token check was too narrow — "not" wasn't on the list, so "not sure what day" passed through.

Chris correctly broadened the BUG name from NOW-01 to DISCOURSE-AS-NAME-01 since the underlying class is "discourse fragments captured as name candidates" — which includes:

- Negation phrases: *"not sure"*, *"don't know"*, *"can't remember"*
- Question fragments: *"what day"*, *"what time"*, *"who knows"*
- Filler phrases: *"uh well"*, *"um okay"* (some already caught by NOW-01)

## Evidence

**Mary's session 2026-05-06 12:30+:**
```
Lori: "Hi mary. It's lovely to meet you. What day is it today?"
mary: "i am not sure what day is it"
Lori: "It's currently Wednesday, May 6th, 2026..."

[Shadow Review notification]
✕ personal › fullName    "not sure what day"
  [Approve] [Correct] [Hold] [Source Only] [Reject]
```

The protected-identity gate (BUG-312) correctly routed this to `suggest_only` so Mary's real fullName isn't overwritten — but the operator sees noise in Shadow Review and may approve out of fatigue.

## Fix landed 2026-05-06

Two edits to `server/code/api/routers/extract.py`:

**Edit 1 — Extend `_NAME_STOPWORD_BLOCKLIST`** with negation / uncertainty words:

```python
# BUG-EX-DISCOURSE-AS-NAME-01 (2026-05-06): negation/uncertainty words
# that begin a refusal phrase. With these added, "not"/"don't"/etc. as
# the FIRST token of a captured name dropped at the first-token gate.
"not", "don't", "dont", "can't", "cant", "won't", "wont",
"shouldn't", "shouldnt", "haven't", "havent", "didn't", "didnt",
"isn't", "isnt", "aren't", "arent", "doesn't", "doesnt",
```

**Edit 2 — New `_NAME_DISCOURSE_FRAGMENT_RX`** substring guard for phrases that the first-token check can't catch (e.g., when the regex captures the prefix differently):

```python
_NAME_DISCOURSE_FRAGMENT_RX = re.compile(
    r"\b("
    r"not\s+sure|"
    r"don'?t\s+know|"
    r"no\s+idea|"
    r"who\s+knows|"
    r"can'?t\s+remember|"
    r"can'?t\s+recall|"
    r"haven'?t\s+(?:said|told|decided)|"
    r"what\s+(?:day|time|date|year|month|week)|"
    r"i\s+(?:dunno|donno)"
    r")\b",
    re.IGNORECASE,
)
```

Wired into the rules-fallback name path at `extract.py:6847+`:

```python
elif _NAME_DISCOURSE_FRAGMENT_RX.search(_captured):
    logger.info(
        "[extract][NAME-BLOCKLIST] dropped fullName candidate value=%r reason=discourse_fragment",
        _captured,
    )
```

## Smoke test (run pre-commit)

```python
# Mary's actual phrase
"i am not sure what day is it" → captured "not sure what day"
                                → first_tok="not" → DROPPED via stopword
# Variant: "I'm not really sure"
"I'm not really sure" → captured "not really sure"
                     → first_tok="not" → DROPPED via stopword
# Variant: "I am uh well not sure"
"I am uh well not sure" → captured "uh well not sure"
                       → first_tok="uh" → DROPPED via stopword
# Real names still pass:
"my name is Mary Holts"   → "Mary Holts"      → EMIT (clean)
"I am Marvin Mann"        → "Marvin Mann"     → EMIT (clean)
"I'm Christopher Now"     → "Christopher Now" → EMIT (only first token checked)
```

All five cases verified in standalone Python smoke test pre-commit (`extract.py` AST parse + isolated regex test).

## Acceptance gate

After fix:
- Mary's *"i am not sure what day is it"* answer produces NO fullName candidate (no Shadow Review entry).
- Real-name introductions ("my name is X" / "I'm X" / "I am X") still produce candidates correctly.
- `[extract][NAME-BLOCKLIST]` log markers fire with `reason=stopword_first_token` OR `reason=discourse_fragment` for dropped candidates — operator-side observability for tuning.
- Across a 30-turn dev session: zero discourse-fragment candidates make it to Shadow Review.

## What this fix does NOT solve

**LLM-extracted candidates.** The LLM extraction path doesn't use `_NAME_FULL` regex; it uses `_validate_item` which runs a different cleanup. Discourse-shaped LLM outputs ("Lori, the narrator said she's not sure what day...") are caught by the `_LLM_COMMENTARY_PATTERNS` regex (LANDED 2026-05-05). Composes with this fix; not blocked.

**Other field paths.** `_NAME_FULL` is only the fullName / firstName rules-fallback. Similar discourse-fragment leakage could affect other rules-fallback patterns (DOB, POB, parents.*, etc.). If observed, scope a broader cleanup. Not in this fix's scope.

**Shadow Review fatigue from other extractor noise.** This fix removes one source of noise; the larger fatigue problem (BINDING-01 Type C errors, schema-gap candidates, etc.) remains a separate concern.

## Files modified

- `server/code/api/routers/extract.py` — `_NAME_STOPWORD_BLOCKLIST` extended (16 new words); new `_NAME_DISCOURSE_FRAGMENT_RX` regex; new `elif` branch in name-emit path.

## Risks and rollback

**Risk 1: false-positive on real names containing "not" / "no" / question words.** Names like "Notley", "Norbert", "Noh" begin with "No"/"Not" but are real. The first-token blocklist matches the EXACT lowercase token only — "not" matches "not" but NOT "Notley" or "Norbert". Test pass: "I'm Notley" → captured "Notley" → first_tok="notley" → not in blocklist → EMIT.

**Risk 2: discourse fragment regex over-firing.** Tested patterns are deliberately narrow (\\b boundaries, specific phrases). "What day" matches only when preceded by a word boundary. False-positive surface should be minimal.

**Risk 3: missing patterns.** Operator may surface other discourse fragments not yet in the regex. Mitigation: log marker `reason=discourse_fragment` enables operator-side tuning. Add patterns as they appear.

**Rollback:** revert both edits. Mary's "not sure what day" returns to Shadow Review. No truth-write regression (gate still routes to suggest_only).

## Cross-references

- **BUG-EX-NAME-EXTRACTION-NOW-01** — landed 2026-05-05; this BUG broadens its scope. NOW-01 specifically addressed single-word discourse markers ("now"/"yes"/etc.). DISCOURSE-AS-NAME-01 generalizes to multi-word phrases. NOW-01 stays closed; this is the next iteration.
- **BUG-312 protected_identity gate** (LANDED 2026-04-29 at `ui/js/projection-sync.js`) — the truth-protection layer that catches what the extractor misses. With this fix, fewer candidates reach the gate; gate still acts as defense-in-depth.
- **BUG-EX-LLM-COMMENTARY-AS-VALUE-01** (LANDED 2026-05-05) — sister fix for LLM-side commentary. Composes with this rules-side fix.

## Changelog

- 2026-05-06: Spec authored after Mary's "not sure what day" Shadow Review noise. Fix landed same day; pending live re-test verification.
