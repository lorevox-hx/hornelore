# Lorevox ↔ Hornelore Template Parity Audit — 2026-04-29

**Status:** Reference doc (not a WO). Survives session boundary so future
agents do not re-derive these findings.
**Authors:** Chris Horne (memory grounding), ChatGPT (file-by-file analysis),
Claude (synthesis + diff).
**Source paths:**

```
Lorevox templates:    /sessions/ecstatic-determined-pasteur/mnt/lorevox/ui/templates/
Hornelore templates:  /sessions/ecstatic-determined-pasteur/mnt/hornelore/ui/templates/
```

## TL;DR

The diverse-population templates ARE NOT LOST. Lorevox holds 23+ narrator templates plus 9 doppleganger validation files. Hornelore inherited only 6 (the 3 Horne family + Shatner + Dolly + narrator-template). The 17 named diverse narrators + 9 dopplegangers were dropped during the Hornelore subset extraction.

The narrator-template SCHEMA (top-level keys + per-section field shape) is identical between Lorevox and Hornelore. The "lost diversity" is FIXTURE coverage, not schema fields. With one exception: `donald-trump.json` in Lorevox uses array-shape spouse + marriage (proving the schema accepts it), and Hornelore inherited zero array-shape templates.

## Inventory

### Hornelore current (6 files)

```
kent-james-horne.json          Horne family
janice-josephine-horne.json    Horne family
christopher-todd-horne.json    Horne family
william-shatner.json           Single celebrity (singular dict shape)
dolly-parton.json              Single celebrity (singular dict shape)
narrator-template.json         Empty canonical schema
```

### Lorevox holds (24+ files — full population coverage)

```
NAMED NARRATORS (17 total)
  david-alan-mercer.json         Black gay, long-term partner, chosen family
  dolores-huerta.json            Mexican-American Chicana labor leader
  donald-trump.json              ARRAY-SHAPE multi-marriage POC (3 spouses)
  eleanor-mae-price.json         Blended family (bio + step + adopted, same-sex spouse)
  elena-rivera-quinn.json        Queer Latina; spouse[] = former + partner + chosen family
  fred-korematsu.json            Japanese-American civil rights, internment trauma
  grace-hopper.json              Woman in STEM, divorce-in-narrative, no children
  harvey-milk.json               Jewish gay public figure, partners-in-prose, no marriage
  jane-goodall.json              Two husbands array, animals-not-pets, science/advocacy
  katherine-johnson.json         Black woman in NASA, widowhood + remarriage
  maya-angelou.json              Multiple marriages array, childhood trauma
  mark-twain.json                Historical figure, family grief, many cats
  mel-blanc.json                 Voice actor
  wilma-mankiller.json           Native American chief
  dolly-parton.json              (also in Hornelore)
  william-shatner.json           (also in Hornelore)
  narrator-template.json         (also in Hornelore — empty canonical)

DOPPLEGANGER VALIDATION (9 files for storage-alignment testing)
  william-1-doppleganger.json    4-spouse array stress
  jane-2-doppleganger.json       2-spouse array
  maya-3-doppleganger.json       3-spouse array, sensitive history
  mark-4-doppleganger.json       Singular baseline
  katherine-5-doppleganger.json  2-spouse with widowhood
  grace-6-doppleganger.json      Singular with divorce-in-prose
  harvey-7-doppleganger.json     Empty marriage object, partners-in-prose
  fred-8-doppleganger.json       Singular baseline
  dolores-9-doppleganger.json    Compressed multi-relationship in prose

MANIFEST
  manifest.json                  Maps doppleganger templates back to source narrators
```

## Schema-shape findings

### Personal section — uniform across all 6 Hornelore templates AND all 23+ Lorevox templates

```
fullName / preferredName
legalFirstName / legalMiddleName / legalLastName     ← legal-vs-preferred split
dateOfBirth / timeOfBirth / placeOfBirth
birthOrder / zodiacSign
pronouns                                              ← already supports he/she/they
culture                                               ← OVERLOADED: ethnicity + religion + nationality + region + heritage all jammed into one string
country / language
```

### Spouse + Marriage shapes — MIXED

```
TEMPLATE                       spouse type    marriage type
─────────────────────────      ───────────    ─────────────
HORNELORE
  kent-james-horne             dict           dict
  janice-josephine-horne       dict           dict
  christopher-todd-horne       dict           dict
  william-shatner              dict           dict (yet Shatner had 4 wives — schema lies)
  dolly-parton                 dict           dict
  narrator-template            dict           dict

LOREVOX
  david-alan-mercer            dict           dict (singular partner — relationshipType="Partner")
  dolores-huerta               dict           dict (compressed multi-relationship in marriage.weddingDetails)
  donald-trump                 ARRAY (3)      ARRAY (3)   ← THE ONLY PROOF schema accepts array shape
  eleanor-mae-price            dict           dict (same-sex spouse, blended children)
  elena-rivera-quinn           ARRAY          ARRAY       ← spouse[] = Former + Partner + Chosen Family
  fred-korematsu               dict           dict
  grace-hopper                 dict           dict
  harvey-milk                  dict           dict (empty marriage — partners in prose)
  jane-goodall                 ARRAY (2)      ARRAY (2)   ← spouseIndex linking
  katherine-5-dopp             ARRAY (2)      ARRAY (2)   ← spouseName linking
  maya-3-dopp                  ARRAY (3)      ARRAY (3)   ← multiple marriages
  william-1-dopp               ARRAY (4)      ARRAY (4)   ← spouseNumber linking
```

**Conclusion:** schema is permissive (accepts both shapes) but only 1 of 6 Hornelore templates and roughly 5 of 23+ Lorevox templates exercise the array form. Code paths in projection-sync, projection-map, bio-builder-family-tree, hornelore.html memoir renderers, extract.py, and prompt_composer LIKELY assume singular dict by default — meaning even the array-shape templates Hornelore could inherit may produce surprising behavior without Phase 2 normalization.

### Marriage-link styles — 5 different patterns across the Lorevox templates

```
spouseReference: "Donald + Ivana"   donald-trump, elena-rivera-quinn
spouseIndex: 0                       jane-goodall (2-spouse)
spouseName: "Jim Goodall"            katherine-5-dopp
spouseNumber: 1                      william-1-dopp (4-spouse)
(prose only)                         dolores-huerta, grace-hopper, harvey-milk, david
```

Phase 2 needs a relationship-link normalization adapter that resolves all 5 inputs to a single canonical key (per WO-SCHEMA-DIVERSITY-RESTORE-01 spec).

### Sensitive identity fields — NEVER BUILT in either codebase

```
FIELD                       LOREVOX    HORNELORE
genderIdentity              ✗          ✗     (pronouns exists but is not a substitute)
sexualOrientation           ✗          ✗     (Harvey/Elena/David are gay narrators
                                              but the field doesn't exist)
religiousAffiliation        ✗          ✗     (currently jammed into culture)
spiritualBackground         ✗          ✗
culturalAffiliations[]      ✗          ✗     (currently a single overloaded culture string)
raceEthnicity[]             ✗          ✗     (currently jammed into culture)
visibility/provenance       ✗          ✗     (per-field "not_asked" / "declined" /
                                              "private" / "known" — not designed)
```

**This is the hardest part of Phase 3.** Designing it isn't just code — it's narrator-data policy. See WO-SCHEMA-DIVERSITY-RESTORE-01 Phase 3 for the proposed identity-block shape with per-field visibility/source state and the locked rule "Lori MUST NOT auto-ask sensitive identity questions."

### Children + Pets — schema works, but vocabulary is loose

```
children[].relation values seen in templates:
  Daughter / Son / Stepchild / Adopted Daughter / Stepdaughter /
  Half-sister (when used in siblings[]) / "Goddaughter" (Dolly →
  Miley Cyrus appears under children[])

children[] without relation field:
  Most Hornelore templates do not populate children[].relation
  (Phase 1.5 added relation:"biological" to existing Christopher children
  for consistency).

pets[] is overloaded with significant animals:
  jane-goodall.json    pets[] contains wild chimpanzees + childhood toys
  mark-4-dopp.json     pets[] contains many cats (literal pets)
  janice-josephine     pets[] contains horse + dog + Phase 1.5 pet pig
  christopher          pets[] now contains lifetime: dogs/cats/fish/snakes/frogs (Phase 1.5)
```

Per Chris's note about his lifetime pets + Janice's childhood pet pig + Eleanor's blended-family children, the GAP-13 / GAP-15 sequencing (kinship + animal role refinement) became Phase 3 of WO-SCHEMA-DIVERSITY-RESTORE-01.

## Recovery plan (per WO-SCHEMA-DIVERSITY-RESTORE-01)

```
Phase 1   Pure template port (1-2 hrs)
          Copy 17 named diverse + 9 dopplegangers + manifest.json from
          Lorevox into ui/templates/. JSON parse smoke per file.

Phase 1.5 Personal-data enrichment (LANDED 2026-04-29)
          Janice: pet pig added.
          Christopher: lifetime pets (dogs, cats, fish, snake, frog
                       placeholders) + stepchildren placeholder + relation
                       :"biological" on existing 3 children.
          All entries explicitly noted as "to be confirmed by operator"
          per ChatGPT's "don't fabricate" rule.

Phase 2   Array-shape normalization (~1 day)
          Adapter accepts spouse: {} and spouse: [] both.
          Same for marriage. Internal runtime always operates on array.
          Touches: projection-sync, projection-map,
          bio-builder-family-tree, hornelore.html memoir, extract.py,
          prompt_composer.

Phase 3   Sensitive identity capture (2-3 days code + 1-2 days policy)
          identity block with visibility/source state.
          Lori auto-ask prohibition.
          Splits overloaded culture field.
          Plus kinship + animal-role refinement (GAP-13 / GAP-15).
```

## Cross-references

- Spec: `WO-SCHEMA-DIVERSITY-RESTORE-01_Spec.md` (full three-phase plan)
- Companion behavior specs: `WO-LORI-SESSION-AWARENESS-01_Spec.md`,
  `WO-LORI-ACTIVE-LISTENING-01_Spec.md`,
  `WO-LORI-RESPONSE-HARNESS-01_Spec.md`
- Code review: `docs/reports/CODE_REVIEW_2026-04-29.md`
- Backup snapshot before laptop migration:
  `/mnt/c/hornelore_data/backups/2026-04-28_2340_before-laptop-migration-canonical-reset/`
