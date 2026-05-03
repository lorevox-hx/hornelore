# WO-EX-FIELD-CARDINALITY-PETS-01 — Multi-entity pet sentence cardinality

**Status:** SPEC — scoped, not yet implemented
**Date:** 2026-05-02
**Lane:** Extractor cardinality. Sub-WO of the broader WO-EX-FIELD-CARDINALITY-01 (parked) — narrowed to the pets.* subtree because that's where the survey produced n=2+ live evidence.
**Sequencing:** Opens after BUG-EX-SPOUSE-ALIAS-01 lands. Independent of BINDING-01 second iteration. Independent rollback per phase.
**Blocks:** Nothing (parent-session-readiness lane is in Lori-behavior queue, not extractor).
**Lights up:** sd_011 (barn cats + dad's horse Silver), sd_012 (Biscuit beagle + unnamed barn cats), sd_040 (six-clause run-on with horse Grey + sister Verene), case_046 (legacy: barn cats + dad's horse Dusty for ranch work).

---

## What this WO is NOT

```
- NOT a generic FIELD-CARDINALITY fix.
  The parent WO-EX-FIELD-CARDINALITY-01 is parked behind BINDING-01
  evidence. This is the pets.* sub-slice that has clear repro
  evidence already and can ship independently.

- NOT a pet species canon fix.
  WO-EX-CASE-BANK-FIXUP-01 Phase 3 covers cat/kitten and
  dog/Labrador/golden-retriever normalization. That's scorer-side.
  This WO is extractor-side: when a sentence contains TWO pet
  entities, emit TWO records, not one merged record.

- NOT a Pass 2 prompt rewrite.
  Prompt-side fixes for cardinality are stochastic by nature (cf.
  BUG-LORI-REFLECTION-01 Patch B locked principle). The cure is a
  deterministic post-LLM splitter, not a prompt block telling the
  LLM to "remember to emit one item per pet."

- NOT a utterance-frame consumer wiring.
  WO-EX-UTTERANCE-FRAME-01 Phase 3 consumer wiring opens after
  BINDING-01 second iteration. This WO uses utterance-frame OUTPUT
  as one possible input signal but does NOT depend on Phase 3
  wiring landing first. If utterance-frame is off, the splitter
  falls back to lighter-weight regex-based detection.
```

## What this WO IS

```
A deterministic post-LLM cardinality splitter for the pets.*
subtree. When the LLM emits ONE pets.* item that conflates TWO
distinct narrator-mentioned animal entities, split into TWO
items with appropriate scoping. Falls back to no-op if cardinality
is genuinely 1, or if the signal is ambiguous.

The narrator's words distinguish "we always had cats" (collective
unnamed) from "my dad had a horse named Silver" (single named
animal with a role). The extractor currently merges these into
one pets.* record. The splitter teaches the post-LLM emit phase
to recognize the two-entity shape and emit two records.
```

## Why now (sd_011 + survey evidence)

```
sd_011 (sentence-diagram-survey, 2026-05-02):
  Narrator answer:
    "We always had cats. Barn cats mostly. And my dad had a
     horse named Silver that he used for ranch work."

  LLM emitted (collapsed):
    pets[0].species = 'cat'
    pets[0].name    = 'Silver'           ← BUG: Silver is the horse, not a cat
    pets[0].notes   = 'ranch work'       ← also belongs to the horse, not the cats

  Expected:
    pets[0].species = 'cat'              (narrator's family had cats, plural, unnamed)
    pets[0].notes   = 'barn cats'
    pets[1].species = 'horse'
    pets[1].name    = 'Silver'
    pets[1].notes   = 'ranch work'

sd_012 (same survey):
  "Our dog was named Biscuit, a beagle. We also had barn cats,
   but none of the cats had names that I remember."

  LLM emitted:
    pets[0].name    = 'Biscuit'
    pets[0].species = 'dog' (or 'beagle')
    [missing: any second pets.* item for the cats]

case_046 (legacy 114-case):
  "we always had cats. Barn cats mostly. And my dad had a horse
   named Dusty that he used for ranch work."

  Identical shape to sd_011. Same failure mode. Currently
  out-of-scope per WO-EX-CASE-BANK-FIXUP-01 (correctly — case_046
  is exactly THIS lane's territory, not the case-bank-fixup
  lane).

The pattern is durable: any sentence with collective-pet noun
("cats", "dogs", "the animals") + named-individual-pet noun
("a horse named X", "our dog Y") is a two-entity pet shape that
the current extractor merges.
```

## Scope (Phase 1 — narrator-self pets only)

Three cardinality rules, ordered most-conservative to least:

```
Rule A: collective + named-individual split
  WHEN pets[i].species ∈ {'cat', 'cats', 'dog', 'dogs', ...}
   AND narrator text contains BOTH:
       - collective-pet phrase: "had cats", "always had X", "barn X"
       - named-individual-pet phrase: "named [Name]", "our dog X"
   AND the named-pet's species DIFFERS from the collective:
       (e.g. collective=cats, named-individual=horse)
  THEN split into TWO items:
       pets[a] = {species: collective_species,
                  notes: collective_phrase ('barn cats')}
       pets[b] = {species: named_species,
                  name: named_name,
                  notes: named_role_phrase ('ranch work')}

Rule B: collective-only mention preserved
  WHEN narrator says "we had cats" / "we had dogs" with no name
  THEN preserve as a single record with species + notes,
       no .name field. (Current behavior; locked by this rule
       so the splitter doesn't accidentally invent a name.)

Rule C: named-individual-only preserved
  WHEN narrator says "our dog Biscuit, a beagle" with no
  collective mention
  THEN preserve as single record with name + species + breed
       (already handled by existing extraction; locked here
       to assert no regression).
```

All splits happen in the post-LLM emit phase. No Pass 2 prompt change. No schema change (`pets` is already a list-shaped schema field — the splitter just emits more list items).

## Integration point

Two viable spots, in priority order:

```
Option 1 (preferred): post-LLM, pre-validator
  Location: extract.py inside the main extraction loop, after
            `_parse_llm_json` returns and before `_validate_item`
            iterates.
  Logic:    For each emitted pets[*] item, check whether the
            narrator answer (req.answer) contains the two-entity
            shape (Rule A above). If yes, emit a synthetic
            second pets[*] item with method='pet_cardinality_split'
            and confidence=0.8 (deterministic, regex-grounded but
            slightly lower than the LLM's primary item to mark
            it as splitter-derived).

  This sits alongside BUG-EX-BIRTH-DATE-PATTERN-01's deterministic
  fallback (same architectural slot — post-LLM, pre-validator,
  narrator-text-grounded, no Pass 2 touch).

Option 2 (fallback): consume utterance-frame Phase 3 hints
  Once WO-EX-UTTERANCE-FRAME-01 Phase 3 wires consumer hooks,
  the frame's clause-level subject classification can identify
  the two-entity shape more cleanly: clause 1 = SUBJECT_PET
  (collective), clause 2 = SUBJECT_PARENT + object='horse'
  + named animal in clause text.
  Listed for completeness; Option 1 is the right Phase 1 choice
  because it doesn't depend on Phase 3 landing.
```

## Locked design rules

```
1. Narrator-text-only grounding.
   The splitter reads `req.answer`. It does NOT invent species,
   names, or notes — every emitted field traces to verbatim
   narrator text or canonical mapping (cats → 'cat' species).

2. Personal-only.
   This WO covers narrator-self pets ("we had cats", "my dad's
   horse"). Multi-entity pet sentences in great-grandparent or
   ancestor narratives are out of scope (the binding architecture
   for ancestor sub-entities is BINDING-01 territory).

3. Suppress-if-already-split.
   If the LLM already emitted TWO pets.* items, the splitter
   does NOT add a third. This is a fallback, not a forced
   override.

4. Conservative species-mismatch gate.
   The split only fires when collective-species DIFFERS from
   named-individual-species (cats + horse, dogs + cat, etc.).
   "We had cats. One was named Whiskers." stays as ONE item
   (Whiskers is one of the cats, not a separate species).

5. Log every fire.
   `[extract][pet-cardinality-split] fired collective='barn cats' → species='cat'; named='Silver' → species='horse', notes='ranch work'`
   So operators can see when the splitter rescued a multi-entity
   pet sentence.

6. No Pass 2 prompt changes. Period.
```

## Acceptance gates

```
Phase 1  [ ] sd_011 passes consistently (3 consecutive eval runs):
             pets[*].species contains BOTH 'cat' and 'horse'
         [ ] sd_012 passes: pets[*] contains BOTH the named dog
             AND a second item for the unnamed cats
         [ ] case_046 (legacy 114-case) passes the same shape
         [ ] No new mnw violations on the master 114
         [ ] v3 contract subset stays at 48/72 or improves
         [ ] v2 contract subset stays at 42/72 or improves
         [ ] mnw stays at 2 or improves
         [ ] [extract][pet-cardinality-split] log marker visible
             in api.log on sd_011 / sd_012 / case_046 turns
         [ ] False-positive rate ≤1 across the 114-case master
             (i.e., the splitter shouldn't introduce any newly-
             failing case via spurious second-pet items)
         [ ] False-positive rate ≤1 across the 42-case
             sentence-diagram-survey pack
```

## What this WO does NOT do (deliberate scope wall)

- Multi-entity sibling, parent, or grandparent splitting (those
  need richer subject-binding work; lane = BINDING-01)
- Pet death / loss handling (lane = WO-LORI-CONFIRM-01 if
  surfaced as fragile fact, otherwise narrative)
- Pet species canon table (lane = WO-EX-CASE-BANK-FIXUP-01
  Phase 3)
- Three-or-more-pet entities in one sentence (Phase 2 if Phase
  1 evidence supports it; defer)
- Reflective-listening behavior on multi-pet sentences (lane =
  WO-LORI-ACTIVE-LISTENING-01 + Lori behavior pack)

## Sequencing relative to other lanes

```
WO-EX-CASE-BANK-FIXUP-01 Phases 2/3 ← scorer/data side, parallel
BUG-EX-BIRTH-DATE-PATTERN-01        ← extractor fallback, parallel
WO-EX-FIELD-CARDINALITY-PETS-01     ← THIS (pet cardinality, parallel)
WO-EX-BINDING-01 second iter        ← parent/sibling/spouse binding
WO-EX-UTTERANCE-FRAME-01 Phase 3+   ← consumer wiring (overlaps THIS at Option 2)
```

Independent rollback per WO. No shared dependencies.

## Cost estimate

```
Implementation: ~50 lines (3 regex helpers + integration + log marker)
Unit tests:     ~12 cases (positive splits + negation guards +
                 species-mismatch gate + suppress-if-already-split)
Master 114 + survey verification: 1 master run + 1 survey run
                 (~10 min each on warm stack)
Total: ~half a session
```

## Bumper sticker

```
The narrator said "cats AND a horse" — two entities, not one merged pet.
The LLM is variable on whether it emits one or two items.
Variable LLM + deterministic narrator text = deterministic splitter.
This WO adds the splitter for the pets.* subtree, scoped to two-entity
sentences with mismatched collective + named-individual species.
```
