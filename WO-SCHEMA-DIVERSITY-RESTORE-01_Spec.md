# WO-SCHEMA-DIVERSITY-RESTORE-01 — Restore Lorevox narrator-population coverage to Hornelore + normalize relationship-array schema + design sensitive-identity capture

**Status:** SPEC (not yet started)
**Authors:** Chris Horne + ChatGPT (template-population analysis), Claude (synthesis + sequencing)
**Date:** 2026-04-28
**Sequencing:** Three phases. Phase 1 is pure template port (zero risk). Phase 2 is array-shape normalization (UI + extractor + projection touches). Phase 3 is sensitive-identity field design (requires policy + research, not just code).
**Do NOT mix into:** WO-CANONICAL-LIFE-SPINE-01 (Steps 6/7/8) — keep memoir spine work separate.

---

## Why this exists

Hornelore inherited the narrator schema from Lorevox but lost most of the diverse-population fixtures during the subset extraction. The current `ui/templates/` folder has 6 files (kent / janice / christopher / shatner / dolly / narrator-template). Lorevox has 23+ files plus 9 doppleganger validation templates that exercise multi-spouse arrays, blended families, chosen family, same-sex relationships, no-children narrators, public-figure trauma, and complex kinship.

The cross-section coverage exists in Lorevox today — file paths verified at:

```
/sessions/ecstatic-determined-pasteur/mnt/lorevox/ui/templates/
```

The schema CAN handle multi-spouse arrays (the `donald-trump.json` template uses `spouse: [3 entries]` + `marriage: [3 entries]` — proof of concept). But the schema shape is INCONSISTENT across templates: some files use singular `spouse: {}` + `marriage: {}`, others use arrays. Code paths in the UI + extractor likely only handle the singular dict shape, which means even the array-shape templates Hornelore inherits can produce surprising behavior.

Also: representation diversity exists (gay narrator, Latina narrator, Native American narrator, woman-in-STEM narrator) but **field-level sensitive identity capture was never built** in either Lorevox or Hornelore. There's no `genderIdentity` field separate from pronouns, no `sexualOrientation` field, no `religiousAffiliation` field. The "diversity" narrators got REPRESENTATION but the schema can't hold sensitive self-disclosure data.

## Three-phase plan

### Phase 1 — Template port (no schema change, no code change)

**Goal:** Copy missing Lorevox templates into Hornelore. Pure file work.

**Sources** (from `/mnt/lorevox/ui/templates/`):

```
NAMED NARRATORS (17 files Hornelore lacks)
  david-alan-mercer.json         Black gay, long-term partner, chosen family
  dolores-huerta.json            Mexican-American Chicana labor leader
  donald-trump.json              Multi-marriage POC (3 spouses array)
  eleanor-mae-price.json         Blended family (bio + step + adopted children, same-sex spouse)
  elena-rivera-quinn.json        Queer Latina; spouse[] = former + partner + chosen family
  fred-korematsu.json            Japanese-American civil rights, internment trauma
  grace-hopper.json              Woman in STEM, divorce in narrative, no children
  harvey-milk.json               Jewish gay public figure, partners in prose, no marriage
  jane-goodall.json              Two husbands array, animals-not-pets, science/advocacy
  katherine-johnson.json         Black woman in NASA, widowhood + remarriage
  maya-angelou.json              Multiple marriages array, childhood trauma
  mark-twain.json                Historical figure, family grief, many cats
  mel-blanc.json                 Voice actor
  wilma-mankiller.json           Native American chief
  (plus the existing narrator-template / shatner / dolly already in Hornelore)

DOPPLEGANGER VALIDATION (9 files for storage-alignment testing)
  william-1-doppleganger.json    4-spouse array stress
  jane-2-doppleganger.json       2-spouse array
  maya-3-doppleganger.json       3-spouse array, sensitive history
  mark-4-doppleganger.json       Singular baseline
  katherine-5-doppleganger.json  2-spouse with widowhood
  grace-6-doppleganger.json      Singular with divorce-in-prose
  harvey-7-doppleganger.json     Empty marriage object, partners in prose
  fred-8-doppleganger.json       Singular baseline
  dolores-9-doppleganger.json    Compressed multi-relationship in prose

MANIFEST
  manifest.json                  Maps doppleganger templates back to source narrators
```

**Phase 1 rules:**
- No schema edits.
- No UI edits.
- No extraction edits.
- No array normalization yet (Phase 2).
- No sensitive identity field changes (Phase 3).
- Just copy the JSON files into `ui/templates/` + verify they parse.

**Phase 1 acceptance:**
- All 26 added JSON files parse cleanly (`python3 -c "import json; json.load(open(f))"` per file).
- Templates appear in the narrator picker dropdown without breaking the existing narrator load.
- Selecting a singular-spouse template (Fred, Grace, David) loads cleanly.
- Selecting an array-spouse template (Trump, Jane, William) either loads cleanly OR fails visibly with a known Phase 2 marker (do NOT silently mis-render).
- No regression to existing 3 Horne narrators.

**Estimated effort:** 1-2 hours. Pure file copy + git add + smoke load.

### Phase 2 — Array-shape normalization (UI + extractor + projection)

**Goal:** Code paths handle BOTH singular dict and array forms for `spouse` + `marriage`. Internal runtime always operates on array form. Templates and persisted data continue to support both shapes for back-compat.

**Do NOT rename `spouse` to `partners`.** Too much code expects `spouse`. Just teach every reader to accept both shapes.

**Phase 2 adapter contract:**

```
Input shape                          Runtime shape
─────────────────────────            ───────────────────────
spouse: {}    (empty dict)      →    spouse: []    (empty array)
spouse: {firstName: "X"}        →    spouse: [{firstName: "X"}]
spouse: [{firstName: "X"}]      →    spouse: [{firstName: "X"}]
spouse: [{a}, {b}, {c}]         →    spouse: [{a}, {b}, {c}]

marriage: {}                    →    marriage: []
marriage: {proposalStory: "X"}  →    marriage: [{proposalStory: "X"}]
marriage: [{a}]                 →    marriage: [{a}]
marriage: [{a}, {b}]            →    marriage: [{a}, {b}]
```

**Phase 2 normalized relationship fields** (additive — old fields stay; new fields optional):

```js
{
  "spouse": [
    {
      "relationshipType": "Spouse",          // NEW: see vocabulary below
      "relationshipStatus": "current",       // NEW: current | former | deceased | unknown
      "firstName": "",
      "middleName": "",
      "lastName": "",
      "maidenName": "",
      "birthDate": "",
      "birthPlace": "",
      "occupation": "",
      "deceased": false,
      "relationshipStartDate": "",           // NEW
      "relationshipEndDate": "",             // NEW
      "marriageDate": "",
      "separationDate": "",                  // NEW
      "divorceDate": "",                     // NEW (BUG-309 + GAP-7 root cause)
      "endReason": "",                       // NEW: divorce | death | mutual | other
      "childrenTogether": [],                // NEW: indexes into children[]
      "narrative": ""
    }
  ],
  "marriage": [
    {
      "spouseReference": "",                 // STANDARDIZED (was: spouseIndex / spouseName / spouseNumber / prose-only)
      "marriageDate": "",
      "separationDate": "",                  // NEW
      "divorceDate": "",                     // NEW
      "legalStatus": "",                     // NEW: legal | civil | committed | religious-only | none
      "proposalStory": "",
      "weddingDetails": "",
      "notes": ""
    }
  ]
}
```

**RelationshipType starting vocabulary:**

```
Spouse
Former Spouse
Partner
Former Partner
Committed Partner
Chosen Family
Companion
Unknown
```

**Phase 2 link-style normalization** (currently 5 different patterns across templates):

```
INPUT FORM                       NORMALIZED TO
spouseReference: "Donald + Ivana"   spouseReference: "Donald + Ivana"
spouseIndex: 0                       spouseReference: "<resolved from spouse[0]>"
spouseName: "Jim Goodall"            spouseReference: "<lookup in spouse[]>"
spouseNumber: 1                      spouseReference: "<resolved from spouse[1]>"
(prose only)                         spouseReference: ""  + warn-log
```

**Phase 2 test fixtures** (use the doppleganger set as the regression suite):

```
william-1                multi-spouse / spouseNumber linking
jane-2                   2-spouse / spouseIndex linking
maya-3                   3-spouse / sensitive history
mark-4                   singular compatibility baseline
katherine-5              2-spouse / spouseName linking + widowhood
grace-6                  singular with divorce-in-prose
harvey-7                 empty marriage object + partners-in-prose edge
fred-8                   singular compatibility baseline
dolores-9                compressed multi-relationship-in-prose edge
+ donald-trump           current best canonical array shape (existing)
+ elena-rivera-quinn     spouse[] containing chosen-family entries (semantic edge)
+ david-alan-mercer      singular partner with relationshipType already set
```

**Phase 2 code surfaces touched** (audit needed before writing patches):

```
ui/js/projection-map.js          REPEATABLE_TEMPLATES.spouse exists; check shape handling
ui/js/projection-sync.js         spouse write path
ui/js/bio-builder-family-tree.js spouse rendering in family graph
ui/hornelore1.0.html             memoir renderers (Crossroads pulls from spouse + marriage)
server/code/api/routers/extract.py
                                 family.spouse / family.marriageDate field handling
                                 plus all the few-shot examples that mention spouse/marriage
server/code/api/lv_eras.py       (no era-key impact; verify)
server/code/api/prompt_composer.py
                                 lori prompt tells about spouse — verify singular assumptions
```

**Phase 2 acceptance:**
- Every template in `ui/templates/` (including all dopplegangers) loads cleanly through the BB UI.
- Trump narrator displays 3 spouses correctly in family tree + Crossroads memoir section.
- Shatner narrator (if migrated to array shape during this phase) displays 4 spouses.
- Singular templates (Fred, Grace, David, Mark) still load identically to today (no behavior change).
- A new test narrator with `spouse: []` (empty array) loads cleanly with no spouse rendered.
- `[extract] family.spouse[i].fieldname` paths (indexed) flow through extraction without schema-validation drops.

**Estimated effort:** 1 day — depends heavily on how many code paths assume singular dict.

### Phase 3 — Sensitive identity capture (research + design)

**Goal:** Add structured fields for genderIdentity / sexualOrientation / religiousAffiliation / spiritualBackground / culturalAffiliations / raceEthnicity, with per-field visibility + provenance state. Lori NEVER auto-asks. Operator/preload/narrator-volunteer-only.

**This is the part that needs research, not just code.** Especially:
- LGBTQ+ field naming conventions (gender vs sex vs identity; orientation vs preference)
- Privacy-sensitive narrator-data architecture (encryption-at-rest? per-field visibility?)
- Reminiscence-therapy + life-story-template literature on what's safe to ASK vs only safe to RECEIVE
- Lori's ethical guardrails for older narrators with cognitive variability who may misunderstand the question

**Phase 3 schema shape** (the `identity` block):

```js
{
  "identity": {
    "pronouns": {
      "value": "he/him",
      "visibility": "known",       // visibility states below
      "source": "preload"
    },
    "genderIdentity": {
      "value": "",
      "visibility": "not_asked",
      "source": ""
    },
    "sexualOrientation": {
      "value": "",
      "visibility": "not_asked",
      "source": ""
    },
    "religiousAffiliation": {
      "value": "",
      "visibility": "not_asked",
      "source": ""
    },
    "spiritualBackground": {
      "value": "",
      "visibility": "not_asked",
      "source": ""
    },
    "culturalAffiliations": [
      {
        "value": "Germans from Russia",
        "visibility": "known",
        "source": "preload"
      },
      {
        "value": "North Dakota",
        "visibility": "known",
        "source": "preload"
      }
    ],
    "raceEthnicity": [
      {
        "value": "",
        "visibility": "not_asked",
        "source": ""
      }
    ]
  }
}
```

**Visibility states:**

```
not_asked      Operator hasn't filled, narrator hasn't volunteered, Lori hasn't asked.
not_shared     Narrator was offered the field and chose not to share.
declined       Narrator was asked and explicitly declined.
private        Operator marked the field as not for memoir export.
known          Field has a value from a trusted source.
unknown        Field was sought but answer was "I don't know".
```

**Hard Lori rule (Phase 3 acceptance non-negotiable):**

```
Lori MUST NOT auto-ask sensitive identity questions.

Allowed sources for the identity block:
  - trusted preload (operator-entered before session)
  - operator entry mid-session
  - narrator volunteers it spontaneously
  - human-reviewed extraction (operator approves the candidate)

Not allowed:
  - automatic inference from narrator stereotypes
  - automatic direct questioning by Lori
  - unreviewed extraction promoting to Promoted Truth
```

**Phase 3 also folds in `culture` overload cleanup.** Today `personal.culture` is a single string carrying ethnicity + religion + nationality + region + heritage. Phase 3 splits these into:

```
personal.culture                  (deprecated — kept for back-compat read)
identity.culturalAffiliations[]   (new authoritative list)
identity.raceEthnicity[]          (new — separate from cultural identity)
identity.religiousAffiliation     (new — separate from cultural identity)
```

**Phase 3 estimated effort:** 2-3 days for code + 1-2 days for narrator-data policy decisions. Should not start until Phase 1 + Phase 2 are banked.

---

## Cross-cutting schema gaps from the template population

The complete gap list ChatGPT's analysis surfaced (also tracked here for follow-up sequencing):

```
GAP  DESCRIPTION                                             PHASE
────────────────────────────────────────────────────────────────────────
1    spouse can be object or array — no stable contract     Phase 2
2    marriage can be object or array — no stable contract   Phase 2
3    relationship linking: 5 different styles               Phase 2
     (spouseReference / spouseIndex / spouseName /
      spouseNumber / prose-only)
4    relationshipType exists in some files, not all         Phase 2
5    legal marriage + committed partnership mixed under     Phase 2
     spouse
6    chosen family currently in spouse[] (Elena)            Phase 2
7    divorceDate missing                                    Phase 2
8    separationDate missing                                 Phase 2
9    relationshipStartDate missing                          Phase 2
10   relationshipEndDate missing                            Phase 2
11   endReason missing                                      Phase 2
12   childrenTogether / parent linkage missing              Phase 2
13   children[].relation inconsistent                       Phase 2
14   godchildren appear under children[] (Dolly + Miley)    Phase 2 / 1.5
15   pets[] overloaded (Jane: chimps + childhood toys)      Phase 1.5 / 2
16   culture overloaded (race + religion + region + nation) Phase 3
17   pronouns exist but genderIdentity does not             Phase 3
18   sexualOrientation does not exist                       Phase 3
19   religiousAffiliation does not exist                    Phase 3
20   spiritualBackground does not exist                     Phase 3
21   no sensitive-field visibility/provenance               Phase 3
22   no rule preventing Lori from auto-asking sensitive Qs  Phase 3
23   no migration adapter for singular → array              Phase 2
```

---

## Phase 1.5 — Personal-data template enrichment (between Phase 1 and Phase 2)

This is a small interstitial pass to add real narrator data Chris noted but couldn't represent because templates were thin:

**Janice template** (`ui/templates/janice-josephine-horne.json`):
- Add to `pets[]`: pet pig from childhood (species: "pig", lifeStage: "childhood", narrative: "...").

**Christopher template** (`ui/templates/christopher-todd-horne.json`):
- Expand `pets[]` to multiple lifetime entries: dogs (multiple), cats (multiple), fish, snakes, frogs, etc. across life stages.
- Expand `children[]` to include stepchildren entries with `relation: "stepchild"` (per ChatGPT's GAP-13: children[] should consistently use `relation` field).

**Per Chris's note:** "we have step children so much we need" — confirms GAP-13 is high-priority. Even before Phase 2 schema work, the templates can use existing `relation` field on children[] to demonstrate the pattern. Then Phase 2 normalizes the field across all templates.

**Phase 1.5 rule:** template content only. No schema field additions yet. The template must still parse cleanly under Phase 1 schema.

---

## Sequencing summary

```
NOW                    Phase 0  Backup + reset narrators (already in motion)
                       Phase 1  Port 26 templates to ui/templates/ (1-2 hrs)
                       Phase 1.5  Enrich Janice + Christopher templates with
                                pets + stepchildren content (~30 min)

FOLLOW-UP COMMIT       Phase 2  Array-shape normalization + adapter (~1 day)
                                Touches projection-sync, projection-map,
                                bio-builder-family-tree, hornelore.html
                                memoir renderers, extract.py field handlers,
                                prompt_composer spouse mentions.

SEPARATE WO            Phase 3  Sensitive identity block + visibility state
                                + Lori auto-ask prohibition (2-3 days code,
                                1-2 days policy research). Should wait until
                                BINDING-01 + LORI-CONFIRM-01 + LORI-SAFETY-
                                INTEGRATION-01 phases land so the policy
                                surface for sensitive-field handling is
                                already in place.
```

## Acceptance gates per phase

```
Phase 1 — Template port
  [ ] All 26 added JSON files parse cleanly (json.load no errors)
  [ ] Each template appears in narrator picker
  [ ] Each singular-spouse template loads in BB without UI crash
  [ ] Each array-spouse template either loads cleanly OR shows known
      Phase 2 marker (no silent miss-render)
  [ ] All 3 Horne narrators still load without regression

Phase 1.5 — Personal-data enrichment
  [ ] janice template adds pet pig
  [ ] christopher template expands pets to lifetime list
  [ ] christopher template adds stepchildren with relation: "stepchild"
  [ ] All 3 still parse + still load + still pass Phase 1 acceptance

Phase 2 — Array normalization
  [ ] Adapter accepts spouse: {} → []
  [ ] Adapter accepts spouse: {a} → [{a}]
  [ ] Adapter accepts spouse: [{a},{b}] → [{a},{b}] (passthrough)
  [ ] Same for marriage
  [ ] Trump narrator displays 3 spouses + 3 marriages correctly
  [ ] Shatner narrator (after array migration) displays 4 spouses
  [ ] Singular narrators still display identically to pre-Phase-2
  [ ] family.spouse[i].* extraction paths route correctly
  [ ] Memoir Crossroads section renders multi-marriage history
      (this is also a memoir UX touch — handle in same commit)

Phase 3 — Sensitive identity
  [ ] identity block parseable + visibility/source state present
  [ ] Lori prompt-composer never includes "ask about gender / orientation /
      religion" auto-questions
  [ ] Operator UI exists for entering sensitive identity values
  [ ] Narrator-volunteered values route through Shadow Review like
      any other extraction
  [ ] Backend tests confirm sensitive fields can be empty + visibility=
      not_asked is the safe default
  [ ] Privacy: confirm whether encryption-at-rest is needed (research
      decision)
```

## Operator-facing rule (taped-to-the-screen)

```
Do not force sensitive identity capture.
Do make the schema capable of safely holding it
when the narrator or operator provides it.
```

## Out of scope

- Renaming `spouse` to `partners` or `relationships` — too much code expects `spouse`. Defer indefinitely.
- Backfilling template content for narrators OTHER than Janice + Christopher — operator's call narrator-by-narrator.
- Schema migration of LIVE narrator data from singular to array form — only run when operator approves on a per-narrator basis (the array adapter handles the read side; the write side stays current shape until intentional migration).
- Inferring sensitive identity from any source — Lori MUST be explicitly told, never infer.

## File ownership

```
WO author + Phase 1 implementer:  Claude (Cowork session)
Phase 2 implementer:              Claude (after Chris signoff on Phase 1)
Phase 3 implementer:              Claude + ChatGPT joint review
                                  (sensitive-field policy decisions need
                                  Chris's explicit signoff per field)
Test fixtures owner:              Lorevox doppleganger templates (existing)
Acceptance signoff:               Chris
```

---

**Bottom line:** the templates aren't lost. The 23 Lorevox templates + 9 dopplegangers + manifest are intact at `/mnt/lorevox/ui/templates/`. The work is to (1) bring them into Hornelore so the population coverage exists locally, (2) make the code handle both spouse/marriage shapes consistently, then (3) design the sensitive-identity capture properly with policy guardrails. ChatGPT's analysis grounds the spec in actual file inspection — this WO is execution-ready, just not yet prioritized into the active sequence.
