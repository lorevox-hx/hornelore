# BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02 — Dangling demonstratives + question-aware closure

**Status:** LANDED 2026-05-07
**Lane:** Multilingual / Lori output guard
**Files:** `server/code/api/services/lori_spanish_guard.py`, `tests/test_lori_spanish_guard.py`
**Sibling:** BUG-ML-LORI-SPANISH-PERSPECTIVE-01 (already landed)

---

## Live evidence

Melanie Carter Spanish session, 2026-05-07. Narrator gave a tender Spanish
story about her abuela talking about Perú; Lori returned the perspective
fix correctly ("Tu abuela") but the trailing question was truncated:

> ¿Qué recuerdas de cómo sonaba su voz cuando contaba esas.

The demonstrative determiner "esas" requires a following noun (esas
historias / esas cosas / esas tardes). Llama produced an incomplete
sentence; the fragment guard didn't cover demonstratives, so the dangling
token slipped past the existing repair.

## Two failure modes addressed

### A. Demonstrative determiners as fragment endings

Add to `_FRAGMENT_CONNECTORS` (server/code/api/services/lori_spanish_guard.py):

- Demonstratives: `esas, esos, esa, ese, estas, estos, esta, este, aquellas, aquellos, aquella, aquel`
- Possessives: `mi, mis, tu, tus, nuestra, nuestro, nuestras, nuestros` (in addition to existing `su, sus`)

These all require a following noun in Spanish; ending on one is a fragment.

### B. Question-aware closure

When trimming a fragment from a sentence that opened with `¿` but never
closed with `?`, the existing logic appended `.`, leaving a malformed
question. New helper `_has_unclosed_spanish_question(text)` counts `¿`
vs `?` and returns True when openers exceed closers; the fragment guard
consults it before choosing the closing punctuation.

```
"¿Qué recuerdas de cómo sonaba su voz cuando contaba esas."
  → "¿Qué recuerdas de cómo sonaba su voz cuando contaba?"
  (NOT "¿Qué recuerdas de cómo sonaba su voz cuando contaba.")
```

For balanced text (no unclosed `¿`), the existing `.` closure is preserved.

## Tests added

9 new tests under `FragmentGuardTest`:

- `test_dangling_demonstrative_esas_closes_with_question_mark` (live failure)
- `test_dangling_demonstrative_esos`
- `test_dangling_demonstrative_esa`
- `test_dangling_demonstrative_aquellas`
- `test_dangling_possessive_mi_in_question`
- `test_dangling_demonstrative_in_statement_closes_with_period` (regression — no `?` when no `¿`)
- `test_balanced_question_marks_no_extra_question`
- `test_demonstrative_followed_by_noun_not_treated_as_fragment` (regression — clean text untouched)
- `test_demonstrative_idempotent`

All 57 tests in `tests/test_lori_spanish_guard.py` pass (48 prior + 9 new).

## Acceptance criteria

- [x] Live failure case repaired: `esas.` no longer appears at end-of-string
- [x] Question-aware closure: unclosed `¿` triggers `?` instead of `.`
- [x] Regression: clean Spanish sentences with `noun + .` are NOT mangled
- [x] Idempotent: running guard twice produces same result as once
- [x] English passthrough preserved
- [x] Quote-safe (existing behavior preserved)

## Architectural posture

Same posture as the existing perspective guard:

- Pure post-LLM repair (no LLM re-call)
- Idempotent
- Quote-safe
- English passthrough
- Failure non-fatal

## Risk

Low. The new patterns are demonstratives — which are not typically the
last word of a well-formed Spanish sentence. The regression test
`test_demonstrative_followed_by_noun_not_treated_as_fragment` covers the
sole at-risk case (demonstrative + noun + period).

The question-mark closure logic only fires when `¿` count > `?` count in
the pre-fragment text — a balanced question ending will never get an
extra `?` appended.

## Rollback

Revert the two edits in `lori_spanish_guard.py`. No behavior change
for English text or balanced Spanish text.

---

## Live verification (pending stack restart)

After Chris restarts the stack, run a Spanish narrator session and
confirm Lori's questions close with `?` instead of trailing on a
dangling demonstrative.
