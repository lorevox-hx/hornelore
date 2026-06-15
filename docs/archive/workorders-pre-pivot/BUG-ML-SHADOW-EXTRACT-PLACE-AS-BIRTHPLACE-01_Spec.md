# BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 — Place mentioned in narrative-connection misrouted to .birthPlace

**Status:** LANDED 2026-05-07 (post-LLM regex guard, sibling lane to PLACE-LASTNAME-01)
**Lane:** Extractor binding / Type C fix per Architecture Spec v1 §7.1
**Files:** `server/code/api/routers/extract.py`, `tests/test_extract_place_birthplace_guard.py` (new)
**Sibling:** BUG-EX-PLACE-LASTNAME-01 (architecture mirror)

---

## Live evidence

Melanie Carter Spanish session, 2026-05-07. Narrator turn:

> Cuando mi abuela hablaba de Perú, decía que extrañaba las montañas, el
> mercado donde compraba maíz, y el sonido de las campanas por la mañana.

Shadow Review queue showed:

> grandparents › birthPlace = Peru

But the narrator never said the grandmother was *born* in Perú — only
that she *talked about* Perú and *missed* it. This is narrative-connection
context (place was a topic of memory), not birth-evidence context.

## Type classification

Type C binding error per Architecture Spec v1 §7.1 — *Extraction is
semantics-driven, but errors are binding-driven*. The LLM correctly
identified Perú + grandmother as related entities, but bound the place
to the wrong schema slot because `.birthPlace` is the closest match for
"place + family-member" without the prompt rule disambiguating
narrative-connection from birth-origin.

## Architecture mirror — three required conditions

Same architecture as BUG-EX-PLACE-LASTNAME-01:

1. **Schema gate**: `fieldPath` ends in `.birthPlace` or `.placeOfBirth`
2. **Connection evidence**: source text contains value AFTER a
   narrative-connection verb phrase (talked about / missed / remembered
   / hablaba de / extrañaba / recordaba / contaba historias de)
3. **No birth evidence**: source text does NOT contain explicit
   birth-evidence (born in / nació en / era de / viene de /
   originario de / vino al mundo en)

All three required → drop. Otherwise keep.

## English + Spanish patterns

**Narrative-connection (drops birthPlace when present without birth-evidence):**

English: `talked about, talked of, spoke of, spoke about, would talk about,
missed, missing, remembered, remembering, reminisced about, told stories of/about,
stories of/about, tales of/about, longed for, yearned for, dreamed of/about`

Spanish: `hablaba de, hablaban de, hablaba sobre, habló de, hablar de,
contaba historias de, contaba historias sobre, contaba sobre, contaba de,
historias de, historias sobre, extrañaba/extranaba, extrañaban/extranaban,
extrañar/extranar, recordaba, recordaban, recordar, se acordaba de,
soñaba/sonaba con, añoraba/anoraba, añorar/anorar, decía que extrañaba`

**Birth-evidence (preserves birthPlace when present):**

English: `was/were/is born in/at/near/on, born in/at/near/on, birthplace was/is/of,
place of birth`

Spanish: `nació en, nació cerca de, nacid[ao] en, nacido cerca de, nacida cerca de,
vino al mundo en, era de, eran de, viene de, vienen de, originario de, originaria de,
oriunda de, oriundo de, lugar de nacimiento`

Whisper accent-strip variants (`extrañaba` ↔ `extranaba`, `nació` ↔ `nacio`)
included.

## Tests added — 26 new

5 test classes covering:

- **SpanishNarrativeConnection** (6 tests): hablaba/extrañaba/recordaba/contaba historias/decía que extrañaba — accented + accent-stripped
- **EnglishNarrativeConnection** (4 tests): talked about/missed/remembered/stories of
- **BirthEvidencePreservesCandidate** (5 tests): nació en/was born in/era de/originario de + compound (both contexts present → guard does NOT fire)
- **SchemaAndValueGate** (5 tests): non-birthplace field passes through, residence.place passes, empty/non-string values pass, value not in text passes
- **PlaceOfBirthFieldCovered** (1 test): personal.placeOfBirth also guarded
- **HelperFunctions** (5 tests): direct probes of `_looks_like_narrative_connection_for_value` and `_has_explicit_birth_evidence`

All 26 tests pass.

## Wire site

Single insertion in `extract_fields()` accepted-items loop at
`server/code/api/routers/extract.py`, immediately after the existing
`_drop_place_as_lastname()` call:

```python
# BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01: drop misbound
# narrative-connection-as-birthplace candidates
if _drop_place_as_birthplace(item, answer or ""):
    continue
```

Emits `[extract][place-birthplace-guard]` log marker on drop with
fieldPath + value + reason.

## Acceptance criteria

- [x] Live failure case dropped: `hablaba de Perú` no longer emits `grandparents.birthPlace=Peru`
- [x] Birth-evidence preserved: `nació en Perú` keeps `grandparents.birthPlace=Peru`
- [x] Compound case (both contexts present): birth-evidence wins, candidate kept
- [x] English equivalents work (talked about / missed / remembered / stories of)
- [x] Whisper accent-strip variants work (`extranaba`, `nacio`)
- [x] Non-birthplace fields pass through unchanged
- [x] residence.place is NOT guarded (legitimate slot for narrative-connection places)
- [x] Empty/non-string values pass through

## Risk

Low — same posture as PLACE-LASTNAME-01:

- Pure post-LLM regex; no LLM re-call
- Conservative: requires BOTH narrative-connection match AND no birth-evidence match
- When in doubt (no narrative-connection match), candidate is kept (false negative preferred over false positive)
- residence.place is unaffected (legitimate route for narrative-connection places)

## Rollback

Revert the two edits to `extract.py`:
1. Remove the `_drop_place_as_birthplace` block + helper definitions
2. Remove the call site in the accepted-items loop

No behavior change for cases where the guard wasn't firing.

## Sibling lane evidence

This guard runs independently of SPANTAG (no env flag). Default-on.
Same lane evidence pattern as BUG-EX-PLACE-LASTNAME-01: Chris's locked
posture is "Type C fixes that ship without SPANTAG re-enable are
preferred over those gated behind SPANTAG."

## Next steps

- Live verification on next Spanish narrator session
- Pair with BUG-ML-SHADOW-SPANISH-FIELD-ROUTING-01 (#90) — broader Spanish field-routing class, separate WO; this guard handles only the birthPlace slice
- Consider parallel guard for `*.deathPlace` if extractor shows the same pattern (deferred until evidence)
