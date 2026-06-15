# BUG-EX-NAME-EXTRACTION-NOW-01 — LLM extracts the word "now" as `personal.fullName`

**Title:** Block `personal.fullName="now"` (and similar discourse-marker tokens) before they reach the rules-fallback path
**Status:** SCOPED — small, additive, eval-gated
**Date:** 2026-05-05
**Lane:** Extractor / Phase-G follow-up
**Source:** TEST-23 v3 + v4 live runs (2026-05-04, 2026-05-05). Same fault on both narrators.
**Blocks:** Nothing. Ride-along with the next BINDING-01 iteration.
**Companion:** BUG-EX-PLACE-LASTNAME-01 (post-LLM scalar-shape guard, same posture).

---

## Mission

In two consecutive TEST-23 runs the rules-fallback extractor produced
`{"fieldPath": "personal.fullName", "value": "now", "confidence": ...}`
for **both** narrators on a `today` / pass2a turn. The Phase G
protected-identity guard caught it both times — canonical `'mary'` /
`'Marvin Mann'` rejected the overwrite — so no projection corruption
landed. But the rules-fallback shouldn't be emitting `now` as a name in
the first place: it's a discourse marker, not a noun phrase, and the
schema validator + Phase G guard are working harder than they should.

## Live evidence

```
2026-05-04 21:27:55  [extract] Phase G: Protected identity conflict (rules)
                     for personal.fullName: canonical='mary' extracted='now'

2026-05-04 21:44:49  [extract] Phase G: Protected identity conflict (rules)
                     for personal.fullName: canonical='Marvin Mann' extracted='now'
```

Both fired during pass2a `era=today` on a sentence shape like "I think
about my wife now and then." The fallback path's name extractor is
matching on a capitalized-or-leading-lowercase short token after a
finite-verb, then routing to fullName.

## Locked design rules

1. **Phase G stays as backstop.** The protected-identity write-gate is the
   correct last-line defense and must not change.
2. **Reject at the rules-fallback layer.** Add a `_NAME_STOPWORD_BLOCKLIST`
   to the rules-fallback name extractor. Words on the list never produce
   a `personal.fullName` / `personal.firstName` / `personal.lastName`
   item, regardless of capitalization or position.
3. **No prompt change.** The LLM-side extraction did not produce this —
   it's purely the rules-fallback. Prompt is not in scope.
4. **No schema change.** EXTRACTABLE_FIELDS already accepts
   `personal.fullName`; we're just teaching the rules path not to emit
   garbage.

## Fix shape

Single 8-line patch in `server/code/api/routers/extract.py` rules-fallback
name path. New constant:

```python
_NAME_STOPWORD_BLOCKLIST = frozenset({
    # Discourse markers / temporal hedges that are not names
    "now", "then", "well", "so", "okay", "yeah", "hmm", "uh", "um",
    "today", "yesterday", "tomorrow", "earlier", "later",
    # Filler clauses
    "yes", "no", "maybe", "sure",
    # Pronouns the LLM sometimes emits as "names"
    "he", "she", "they", "we", "i",
})
```

In the rules-fallback name regex match site, after a candidate is
captured, `if cand.lower().strip() in _NAME_STOPWORD_BLOCKLIST: continue`.
Emit `[extract][NAME-BLOCKLIST] dropped value=<X>` for traceability.

## Acceptance

- Same rules-fallback turn that produced `value="now"` in the live
  evidence emits zero items instead of an item-then-Phase-G-block.
- master eval r5h-followup-guard-v1 stays at 78/114 (no behavior change
  for cases that don't hit the discourse-marker class).
- New test fixture `case_111_now_marker` asserts must-not-write on
  `personal.fullName` for the input "I think about my wife now and then."

## Scope estimate

~30 minutes. Single-file diff, blocklist + 2 lines of guard logic + 1 log
line + 1 fixture.
