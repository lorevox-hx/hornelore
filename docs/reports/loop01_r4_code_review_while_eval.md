# LOOP-01 R4 — Code review of extraction pipeline (eval-concurrent)

Date: 2026-04-19
Author: Claude
Scope: read-only review of `server/code/api/routers/extract.py`,
`server/code/api/api.py`, and neighbouring call sites.
Status: findings only, no code changes. Holding for the "eval is done"
signal before reading `master_loop01_r4.json`.

This review is deliberately orthogonal to the R4 patch set. It looks for
issues that may be affecting extraction quality **regardless of** the
A–K patches that just landed. Findings are ordered high → low.

> **Category note (validity vs. binding).** Several findings below —
> especially #1, #8, and most of the alias-dict observations — are
> symptoms of the same underlying pattern: the pipeline is using one
> mechanism (the alias dict) to solve both *validity* (is this path
> legal?) and *semantic binding* (which entity/field does this fact
> belong to?). Tactical fixes still apply. The long-term separation
> is in `loop01_r4_strategy_bridge.md`.

---

## High severity

### 1. R4-I rerouter rule 4e is partly dead code

Path: `_validate_item` (line 1738) runs the `_FIELD_ALIASES` dict
**before** `_apply_semantic_rerouter`. The alias dict rewrites
`personal.heritage` and `personal.ethnicity` to
`earlyMemories.significantEvent`:

```
"personal.ethnicity": "earlyMemories.significantEvent",
"personal.heritage":  "earlyMemories.significantEvent",
```

So when the LLM emits `personal.heritage="Norwegian"`, the alias fires
first and the fieldPath becomes `earlyMemories.significantEvent`.
Rerouter rule 4e (line 3473) then checks
`elif fp in ("personal.notes", "personal.heritage", "personal.ethnicity")`
— and misses, because `fp` is no longer `personal.heritage`.

Net effect: Patch I's ethnicity-routing only ever fires on the
`personal.notes` branch. The `personal.heritage` / `personal.ethnicity`
cases silently dump into `earlyMemories.significantEvent`.

Fix options:
- remove those two alias rows so the rerouter can see the raw path; or
- change the alias to route directly to `grandparents.ancestry` when
  value matches `_ANCESTRY_VALUE_CUES`.

### 2. `_FIELD_ALIASES` is rebuilt on every `_validate_item` call

~220 entries, constructed inside the function body (line 1738). For a
62-case master eval with ~15 items/case that's ~900 dict constructions.
Cheap in absolute terms but wasteful and adds GC pressure. Hoist to
module scope — no behaviour change, measurable latency win.

### 3. Patch H normalisation runs **after** rerouter Patch D (narrator birthOrder)

Order in `extract_fields`:
```
_apply_semantic_rerouter(...)         # includes Patch D (value-match check)
_apply_claims_validators(...)
  └─ _apply_write_time_normalisation  # Patch H — canonicalises birthOrder
```

Patch D decides reroute by string-matching the LLM's raw value against
`_NARRATOR_BIRTHORDER_CUES` captures in the answer. If the LLM paraphrased
the narrator's cue (narrator said "firstborn", LLM wrote "1st"), Patch D
silently misses; then Patch H normalises "1st" → "first" after it's too
late to reroute.

Fix: either normalise inside the rerouter for this rule, or normalise
both sides (cue set and item value) through `_normalize_birthorder_value`
before comparing.

---

## Medium severity

### 4. Prompt contains a direct contradiction on family military

System prompt line 735–736:
> "Family member's military service → military.* fields with a note that this is family history"

…but the SUBJECT RULE (lines 685–691) says the opposite:
> "A great-grandparent's Civil War service is greatGrandparents.memorableStories — NEVER military.* for the narrator."

Models seeing both will split behaviour across cases. Pick one; delete
the other. The SUBJECT RULE framing is the one aligned with the
ancestor-military guard (Patch 4 / J) and the schema additions for
`greatGrandparents.military*`. Line 735–736 should be rewritten to say
"Family member's military service → greatGrandparents.memorableStories
or *.notableLifeEvents — NOT military.*".

### 5. `compact_catalog` isn't compact and isn't section-filtered

`_build_extraction_prompt` builds `relevant_fields` (line 418) from
**all** of `EXTRACTABLE_FIELDS` regardless of `current_section`. The
comment claims "If we have a section hint, prioritize those fields but
still include identity" — no such prioritisation actually happens. As a
result the prompt carries every field label on every call.

Two fixes worth considering:
- If we want a real compact catalog: reintroduce a section-scoped
  subset, with a shared identity core always included.
- Otherwise drop `compact_catalog` and the unused `field_catalog`
  (line 410–413) — that's dead code today.

### 6. `_parse_llm_json` fallback `[.*]` is greedy

Line 1675: `re.search(r'\[.*\]', raw, re.DOTALL)` grabs from the first
`[` to the LAST `]`. If the LLM emits an extra bracketed token after the
JSON array ("Here's the data: [...] (note: [optional])"), this swallows
everything, `json.loads` fails, and we fall through to
`_salvage_truncated_array`. Most of the time the salvage path catches
this — but the bracket_search is supposed to be the **reliable** path,
not a decoy. A bracket-depth scanner (the same technique
`_salvage_truncated_array` already uses to find complete top-level
objects) would be deterministic.

### 7. Patch C pets splitter is too strict on surface form

`_PETS_NOTES_SPLIT` (line 3309):
- anchored `^…$` — any trailing colour ("dog named Ivan, a rescue")
  fails to match
- requires Title-case name (`[A-Z][a-zA-Z'\-]+`) — LLM lowercase pet
  names miss the split
- requires species-first OR name-first with no adjective — "small dog
  named Ivan" fails because "small " isn't in the article whitelist

These aren't bugs; they're coverage gaps. If pets is still showing up
as `.notes` sink in R4 metrics, relax the adjective position and lower
the Title-case requirement (normalise via `_normalize_name_value`
afterward).

### 8. `family.siblings.dateOfBirth` alias lands in the wrong place

Line 1856: `"family.siblings.dateOfBirth": "earlyMemories.significantEvent"`

Everything else in the `family.siblings.*` alias block routes to
`siblings.*`. This single row sends the sibling's birthdate into
`earlyMemories.significantEvent`, which then competes with legitimate
firstMemory/significantEvent records. Should be `siblings.birthDate`.

### 9. Rerouter runs before the validator chain, not after

On the LLM path (line 4221):
```
llm_items = _apply_semantic_rerouter(...)   # reroute
if llm_items:
    llm_items = _apply_birth_context_filter(...)
    llm_items = _apply_month_name_sanity(...)
    llm_items = _apply_field_value_sanity(...)
    llm_items = _apply_claims_validators(...)
```

Rules path doesn't call the rerouter at all. Two consequences:
- If a rule-emitted item is on a valid-but-wrong path (e.g. the rules
  fallback's current-target projection at line 4014), the rerouter
  won't touch it. Mostly fine because rules emit narrow targets, but
  an audit would be cheap.
- If a guard/validator would have dropped an item that then gets
  rerouted to a *different* allowed category, we lose the reroute
  opportunity. (Unlikely in practice but worth mapping.)

### 10. `_extract_via_rules` projects the full answer when a target is unset

Lines 4013–4021: if `current_target` is set and nothing matched, project
the whole `answer` as the value for that field (confidence 0.7). Patch
A's value-length cap catches this on the final guard pass, but it still
generates LLM-style answer-dump behaviour in the rules path. A
conservative guard (skip projection when `len(answer) > 200`, or skip
for scalar fields entirely) would avoid the need to rely on Patch A.

### 11. Twopass Pass-2A rules emit a narrow family schema

`_classify_spans_rules` for the `person` span type emits only
`firstName` (+ `relation`, + side for grandparents). LastName,
maidenName, birthPlace, ancestry all have to survive as **separate**
spans and then traverse Pass-2B LLM classification. On dense genealogy
answers this means the twopass path is systematically weaker than
singlepass, because cross-span association (entity-role binding) is the
hard IE problem — and the singlepass LLM does that association directly
inside its JSON output.

If the R4 report shows that dense/E-series cases regress more under
twopass than singlepass, this is why. Possible mitigation: let Pass-2A
pair a `person` span with nearby `place`/`time` spans and emit
`lastName`/`birthPlace` when they fall within the same clause.

---

## Low severity

### 12. `_record_metric` double-counts on the LLM path

```
_record_metric(_method, parsed=len(llm_items), accepted=len(final_items), rejected=0)
```

`llm_items` at this point has already been through the rerouter and
four guard layers. So `parsed` is not "raw LLM parse count" — it's
"post-guard count". `rejected=0` always. Reject volume is invisible to
`/api/extract-diag`. Low priority, but whoever's reading the metrics
endpoint for a gut-check on pipeline health is being misled.

### 13. Rules-path parent reorder has orphaned first-pass code

Lines 3976–3979 initialise `reordered`, `father_items`, `mother_items`,
`other_items` using `_parentType` tags — but the name extractor
(3871–3889) never sets `_parentType`. The subsequent block on lines
3984–4011 uses a different algorithm (walking `parent_items` and
tracking `current_group`). The first-pass variables are never appended
to or returned. Dead code from a refactor. Safe to delete.

### 14. Alias dict and rerouter can disagree on same symbolic paths

`education.career` → alias → `education.careerProgression` (line 1824).
But the rerouter rule 4d (line 3461) can push `education.careerProgression`
back to `education.earlyCareer` when no duration cue exists. So the
round trip is `education.career` → `careerProgression` → `earlyCareer`.
Probably correct — "education.career" with no duration is a first-job
phrasing — but worth an assertion that the duration-cue heuristic is
actually the right signal for this inverse reroute.

### 15. `_PETS_REMAP` remaps `hobbies.hobbies` → `pets.notes`

Line 3322. Guarded by `_SECTION_PETS` + `_PET_CUES`, so low risk, but
if the narrator is genuinely describing a hobby **with** a pet cue
inside a pets section ("walking my dog is my hobby"), we lose the
hobbies.hobbies emission entirely. If the R4 report shows a
hobbies-section dip coinciding with pet mentions, check this.

### 16. Model + warmup tightly coupled to API process

`api.py` lines 107–176: `_load_model` populates module-level `_model`
/ `_tokenizer` on first request via `AutoModelForCausalLM.from_pretrained`
plus optional `PeftModel.from_pretrained`. Every API restart loses the
warmup (hence `scripts/warm_llm.py` after `scripts/restart_api.sh`). Not
an extraction bug, but it's the reason Chris's "keep it warm during
patching" question exists. The fix is architectural: split the model
into a long-lived process (vLLM OpenAI-compat server or a minimal
handwritten model server) and have the API router just proxy. Flagged
here so the code review output covers the full picture.

---

## How these interact with the papers just uploaded

Loosely mapped for future patch planning, not current work:

- **Grammar-constrained decoding** (Draft-Conditioned Constrained
  Decoding, Integer Programming-Constrained Decoding, XGrammar line of
  work): would collapse the alias dict — you wouldn't need 220+ rows if
  the decoder can only emit valid `fieldPath` strings. The "rerouter
  runs after alias, alias runs before rerouter" conflict (finding #1)
  becomes a non-issue.
- **LLM-as-judge reliability** (Thunder-NUBench, "How Trustworthy Are
  LLM-as-Judge"): relevant to Issue #63 (should_pass drift) and to the
  Patch H "scorer compatibility vs extractor improvement" distinction
  noted in `loop01_r4_eval_first_note.md`. If R4 moves pass rate but
  not per-case per-axis signal, #63's drift is probably dominating.
- **Entity-role binding / attribution error**: directly relevant to
  Issue #11 (twopass entity-role pairing is the hard step) and to the
  `parents.siblings.*` / `family.siblings.*` alias jungle. A proper
  role-binding pass would let us delete those aliases and emit the
  correct fields first time.
- **Negation scope / contrastive assertion**: Patch 4 (narrator-scope)
  and Patch F (contrast-affirmation) are the hand-built analogue of
  what these papers formalise. If the R4 report shows Patch F
  over-triggering ("not X, Y" where Y isn't actually in the same
  category as X), the NegBench-style cue/scope annotation would be a
  principled upgrade.

---

## Not in this review

- Validator correctness (tests cover A/D/E/F/H; B/C/G/K are prompt-only
  and untested).
- The interview/identity_review graph-contamination path (extractor
  → family-truth → narrator profile). Those routers were skimmed but
  not deeply read; the extractor side was the focus.
- Performance profiling — observations are from code reading, not
  timing.
