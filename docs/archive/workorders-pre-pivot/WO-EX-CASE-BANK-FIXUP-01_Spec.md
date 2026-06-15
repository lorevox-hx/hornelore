# WO-EX-CASE-BANK-FIXUP-01 — Scorer/data-side cleanup of case-bank annotation drift

**Status:** SPEC — Phase 1 SHIPPED (case_110 data patch landed 2026-05-02), Phases 2 + 3 scoped, not yet implemented
**Date:** 2026-05-02
**Lane:** Scorer / case-bank / canon. Pure `data/qa/question_bank_extraction_cases.json` and `scripts/archive/run_question_bank_extraction_eval.py` changes. **Zero extract.py touch.**
**Sequencing:** Independent of all extractor lanes. Independent rollback per phase.
**Blocks:** Nothing.
**Lights up:** case_110 (already), case_075 (Phase 2), case_042 / case_045 (Phase 3).

---

## What this WO is NOT

```
- NOT an extractor change.
  Every fix here is annotation/canon side. extract.py is not touched.
  If a finding turns out to require extractor work, it leaves this WO
  and gets minted as its own lane.

- NOT a sentence-diagram / multi-entity cardinality fix.
  case_046 ("we always had cats. Barn cats mostly. And my dad had a horse
  named Dusty that he used for ranch work.") is EXPLICITLY OUT OF SCOPE
  for this WO. Two narrator entities (barn cats + dad's horse Dusty) live
  in one answer; this is the multi-entity cardinality class that opens
  with utterance-frame Phase 3 consumer wiring + FIELD-CARDINALITY work.
  Flattening case_046 here by accepting "horse" as an alternate species
  for "cat" would mask the real architectural problem and degrade the
  contract surface. Do not touch.

- NOT a "make every failure pass" sweep.
  Only failures whose root cause is documentably scorer/canon-side land
  here. Real extraction misses (LLM-genuine omission, binding errors,
  schema gaps) belong to BUG-EX-BIRTH-DATE-PATTERN-01 / BINDING-01 /
  SCHEMA-ANCESTOR-EXPAND-01.
```

## What this WO IS

```
A staged data-side cleanup. Each phase touches a small, named subset
of the 114-case bank with a documented narrator-text grounding for
why the annotation should change. Each phase ships independently and
is reversible by a single commit revert.

The reason this WO exists as one umbrella rather than three separate
WOs: the work is so small per phase (≤30 lines of JSON each) that
sub-WO overhead would dominate. Grouping under one banner with
explicit per-phase rollback boundaries keeps it auditable without
fragmenting the tracker.
```

## Phase 1 — case_110 spouse path normalize ✅ SHIPPED 2026-05-02

```
Status: LANDED via data patch on 2026-05-02 prior to this spec
        being formalized.

What it did:
  case_110 in data/qa/question_bank_extraction_cases.json carried
  bare `spouse.*` paths in 5 places (extractPriority, expectedFields
  list, forbiddenFields cross-reference, and two truthZones keys).
  Every other case in the bank uses canonical `family.spouse.*`
  (64 occurrences across 7 cases). case_110 was the lone outlier.

  Patch: 5 string-level normalizations
    spouse.firstName    → family.spouse.firstName
    spouse.lastName     → family.spouse.lastName
    spouse.maidenName   → family.spouse.maidenName
    spouse.dateOfBirth  → family.spouse.dateOfBirth
    spouse.placeOfBirth → family.spouse.placeOfBirth

Verification:
  jq '..' on the file parses clean
  grep -c '"spouse\.'        → 0 (was 5)
  grep -c '"family\.spouse\.' → 69 (was 64)

Rollback: revert the single commit that touched case_110.

Why it lives in this WO: it's the canonical example of what
case-bank-fixup looks like — narrator words unchanged, schema
unchanged, extract.py unchanged, only the case-bank annotation
shape made consistent with the rest of the corpus.
```

## Phase 2 — case_075 occupation alt_defensible_values

```
Status: SCOPED, not yet implemented.

Narrator answer (verbatim, from the case):
  "My mother was a Housewife mostly. But she also played piano
   at the silent movies in town when I was little, to make a
   little money."

Current case-bank state:
  truthZones["parents.occupation"].expected_values = ["Housewife"]

Current extractor behavior:
  LLM emits parents.occupation = "musician" (or "pianist" /
  "organist" — varies by sample). Scorer rejects under the
  ≥0.5 fuzzy gate because "musician" vs "Housewife" doesn't
  fuzzy-match.

Why the extractor is right at one timescale:
  Playing piano at the silent movies for money IS an occupation
  — narrator explicitly grounds it as paid work ("to make a
  little money"). The narrator's own framing is a both/and:
  Housewife (lifetime summary) AND musician (specific paid work).

Why "Housewife" stays the primary expected_value:
  Narrator literally says "mostly" — Housewife is her dominant
  identification of her mother's life-work. Removing it would
  trade one annotation problem for another.

Patch:
  Add `alt_defensible_values` annotation under
  truthZones["parents.occupation"]:

    "alt_defensible_values": [
      "musician",
      "pianist",
      "organist",
      "piano player",
      "organ player",
      "silent movie pianist"
    ]

  Plus a per-zone note documenting WHY:
    "note": "Narrator frames Housewife as primary ('mostly')
             but explicitly identifies paid musical work at silent
             movies. Both are narrator-grounded. Either credits."

Scorer behavior change:
  Same ≥0.5 fuzzy gate as #97 / WO-EX-VALUE-ALT-CREDIT-01 but
  applied per-case rather than as a global rule. value-axis
  alt_credit on a single zone, no extractor risk.

Acceptance:
  case_075 should pass when LLM emits any of: Housewife,
  musician, pianist, organist, piano player, organ player,
  silent movie pianist (case-insensitive, ≥0.5 fuzzy).
  Other 113 cases byte-stable.

Rollback: revert the JSON edit on case_075 truthZones block.
```

## Phase 3 — case_042 / case_045 pet species canon

```
Status: SCOPED, not yet implemented. Smaller than Phase 2;
        exists primarily to consolidate pet-related annotation
        drift surfaced during the master-114 audit.

Background:
  case_042 and case_045 both involve pets. Narrator answers
  use breed-or-type names ("Lab", "kitten", "Golden Retriever",
  "barn cat") that the case-bank `expected_values` for
  pets.species or pets.type entries don't currently canonicalize.

Where this lives:
  Two viable spots; pick one:

  Option A (preferred): per-zone alt_defensible_values
    Same shape as Phase 2 — touch only the affected zones in
    case_042 / case_045. Cheap, scoped, reversible per case.

  Option B: scorer-side species canon table
    New `_PET_SPECIES_ALIASES` dict in
    scripts/archive/run_question_bank_extraction_eval.py
    around the existing `_ROLE_ALIASES` (extract.py L149-168
    is the role-alias precedent — same shape, same place).
      "cat":  ["cat", "kitten", "barn cat", "house cat"]
      "dog":  ["dog", "puppy", "lab", "labrador",
               "golden retriever", "retriever", "terrier", ...]
      "bird": ["bird", "parakeet", "parrot", "canary"]
    Wire into score_field_match for any zone whose path matches
    `pets.*.species` or `pets.*.type`.

Decision criterion:
  If the same species canon issue surfaces in ≥3 future cases,
  go Option B (table is reusable). Otherwise go Option A
  (case-local annotations, contained blast radius).

  At time of this spec, only case_042 and case_045 are known
  to need this. Default to Option A unless a third case appears.

Patch (Option A):
  case_042 truthZones["pets.dog.0.breed"]:
    expected_values: ["Lab"]
    alt_defensible_values: ["Labrador", "Labrador retriever",
                            "yellow lab", "black lab"]

  case_045 truthZones["pets.cat.0.species"] (or equivalent path):
    expected_values: ["cat"]
    alt_defensible_values: ["kitten", "barn cat", "house cat",
                            "tabby", "tom"]

  (Exact paths to be confirmed against the cases at
   implementation time — narrator answers and zone names need
   to be re-read once Phase 2 lands and we know exactly which
   zones the extractor was emitting against.)

Acceptance:
  case_042 and case_045 pass when LLM emits any of the
  defensible breed/type values per case. Other 112 cases
  byte-stable.

Rollback: revert the JSON edits per case (Option A) or revert
  the alias-table commit (Option B).
```

## Out-of-scope (deliberate exclusions, do not fold in)

```
case_046 — multi-entity sentence diagram
  Narrator: "we always had cats. Barn cats mostly. And my dad
  had a horse named Dusty that he used for ranch work."
  Two entities: barn cats (narrator's family) + dad's horse
  Dusty (single named animal with a role). Flattening this by
  accepting "horse" as an alternate species for "cat" would
  mask the real architectural failure: cardinality + subject
  binding on a multi-clause utterance. Lane = WO-EX-FIELD-
  CARDINALITY-01 / utterance-frame Phase 3 consumer wiring.
  Do not patch this case in this WO.

case_049 — DOB recall miss on canonical birth sentence
  Narrator: "I was born in Spokane, Washington, on August 30th,
  1939." LLM stochastically omits personal.dateOfBirth. R4-H
  date normalizer is fine (api.log proves it). The cure is
  deterministic post-LLM regex fallback, not a case-bank
  annotation. Lane = BUG-EX-BIRTH-DATE-PATTERN-01.

case_028 / case_033 / case_044 / case_069 — greatGrandparents
  hallucinations
  These are extractor binding/schema failures, not annotation
  problems. Lane = BINDING-01 + SCHEMA-ANCESTOR-EXPAND-01
  (Lane 2 schema work).

Anything that requires extract.py to behave differently
  Hard scope wall. If the implementation discovers a fix
  needs extract.py touch, the fix leaves this WO and gets
  minted as its own lane.
```

## Locked design rules

```
1. Data/scorer-only.
   Every patch in this WO touches `data/qa/question_bank_
   extraction_cases.json` and/or
   `scripts/archive/run_question_bank_extraction_eval.py` only.
   No extract.py touch. No prompt change. No schema change.

2. Narrator-text-grounded.
   Every alt_defensible_value addition cites the narrator's
   verbatim words in a per-zone "note" field. If the extractor
   value isn't visibly grounded in narrator text, it doesn't
   get added — that's a real extraction miss, not annotation
   drift.

3. Per-phase rollback boundary.
   Each phase commits separately. Reverting Phase 2 must not
   touch Phase 1 or Phase 3 changes.

4. Contract surface preservation.
   Each phase MUST keep v3 ≥ baseline, v2 ≥ baseline, mnw
   ≤ baseline. If a phase regresses any of those three on
   any case, the phase is rolled back, not "fixed forward."

5. No new global rules without ≥3-case evidence.
   Per-zone alt_defensible_values is the default shape.
   Promotion to a scorer-wide table (the `_ROLE_ALIASES` /
   `_PET_SPECIES_ALIASES` shape) requires ≥3 distinct cases
   exhibiting the same pattern. Otherwise the change stays
   case-local.
```

## Acceptance gates

```
Phase 1 (already shipped, locked-in):
  [x] case_110 passes (was failing on field_path_mismatch
      `family.spouse.*` vs bare `spouse.*`)
  [x] No new mnw violations
  [x] v3 contract subset stays at 48/72 or improves
  [x] v2 contract subset stays at 42/72 or improves
  [x] mnw stays at 2 or improves
  [x] JSON parses clean (jq validation)
  [x] bare `spouse.*` count = 0; `family.spouse.*` count = 69

Phase 2:
  [ ] case_075 passes consistently (3 consecutive eval runs)
      on any of the alt_defensible_values
  [ ] No new mnw violations introduced
  [ ] v3 contract subset stays at 48/72 or improves
  [ ] v2 contract subset stays at 42/72 or improves
  [ ] mnw stays at 2 or improves
  [ ] case_075 truthZone block carries explicit grounding note
      citing narrator's "to make a little money" phrasing

Phase 3:
  [ ] case_042 + case_045 pass on the defensible breed/type
      values per case
  [ ] No new mnw violations introduced
  [ ] v3 contract subset stays at 48/72 or improves
  [ ] v2 contract subset stays at 42/72 or improves
  [ ] mnw stays at 2 or improves
  [ ] If Option B (alias table) is chosen, ≥3 cases must
      already need the canon at time of landing
```

## Sequencing relative to other lanes

```
WO-EX-CASE-BANK-FIXUP-01 Phase 2/3 ← THIS (data/scorer side, parallel)
BUG-EX-SPOUSE-ALIAS-01           ← merged into Phase 1 above
BUG-EX-BIRTH-DATE-PATTERN-01     ← extractor fallback, parallel lane
WO-EX-BINDING-01 second iter     ← parent/sibling DOB binding
WO-EX-FIELD-CARDINALITY-01       ← multi-entity splitting (case_046)
WO-EX-UTTERANCE-FRAME-01 Phase 3 ← consumer wiring (case_046 cardinality)
```

Independent rollback per phase. No shared dependencies.

## Cost estimate

```
Phase 1: 0 (already shipped)
Phase 2: ~15 lines of JSON + per-zone note + 1 master eval = ~1 hour
Phase 3: ~25 lines of JSON (Option A) OR ~30 lines of script
         (Option B) + 1 master eval = ~1-2 hours
Total remaining: 2-3 hours, single session
```

## Bumper sticker

```
Sometimes the extractor is right and the case bank is stale.
When the narrator's words ground both, both get credit.
This WO is the trash compactor for case-bank annotation drift.
The extractor is not touched.
```
