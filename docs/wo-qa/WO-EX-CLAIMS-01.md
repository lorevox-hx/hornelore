# WO-EX-CLAIMS-01 — Claim-level extraction + shadow review

## Status: READY TO SCOPE — P1 (blocked by WO-EX-SCHEMA-01)

## Rationale

Live sessions on 2026-04-15 (see `docs/observations/2026-04-15-extraction-taxonomy.md`)
exposed two structural failures:

1. **Compound-loss** — "my sisters linda and sharon" produces zero sibling
   extractions because the LLM can't split coordinated names into two
   separate entities.

2. **Shadow review cognitively wrong** — operator sees fragments:
   `firstName=and`, `lastName=ND`, `firstName=Stanley`, `lastName=ND`.
   Nothing describes the meaningful unit ("my dad was born in Stanley,
   ND"). Operator clicks "Open in Shadow Review" and does not know what
   to do.

The fundamental architectural shift: **extraction output should be
semantic units (claims), not token fragments.**

## Core design principle

> Extract once at claim-granularity.
> Route fragments as sub-fields of their parent claim.
> Show operators claims, not fragments.

A claim is a coherent assertion about a real-world entity: **Mother =
Janice, born Spokane.** That's one claim with three sub-fields. The
current system would emit three separate extraction items that the
operator must mentally reassemble. The claims layer makes the reassembly
authoritative.

---

## Architecture

### Claim data structure

```python
class ExtractedClaim(BaseModel):
    claim_id: str                      # stable id, e.g. "claim_<hash>"
    kind: str                          # "person" | "event" | "residence" | "education" | "career" | "milestone"
    role: Optional[str]                # "mother" | "father" | "son" | "daughter" | "self" | "spouse" | None
    entity_index: Optional[int]        # for repeatable groups; 0 = first instance, 1 = second, etc.

    # Sub-fields, keyed by field path relative to the claim root
    fields: Dict[str, str]             # e.g. {"firstName": "Janice", "placeOfBirth": "Spokane"}

    # Provenance
    source_turn_id: str
    source_phrase: Optional[str]       # the fragment of the answer this claim came from
    confidence: float
    extraction_method: str             # "llm" | "rules_fallback"

    # Routing
    write_modes: Dict[str, str]        # field → "prefill_if_blank" | "candidate_only" | "suggest_only"
    target_paths: Dict[str, str]       # field → full path in EXTRACTABLE_FIELDS, e.g. "parents.firstName"
    
    # Status
    status: str                        # "pending" | "approved" | "rejected" | "merged" | "conflicted"
    
    # Optional: raw fragments, kept for debugging and rollback
    raw_fragments: List[Dict[str, Any]]
```

### Worked example — Janice's three children

Narrator says:

> "My oldest, vince was born in Germany in 1960, my middle son Jay or
> Jason was born in Bismarck in 1961 and my youngest Chris was born on
> his dads birhday in december 24 1962."

Current system output: *nothing*.

Claims-layer output: three claims, same turn:

```python
[
  ExtractedClaim(
    claim_id="claim_abc1", kind="person", role="son", entity_index=0,
    fields={
      "firstName": "Vince",
      "dateOfBirth": "1960",
      "placeOfBirth": "Germany",
      "birthOrder": "oldest",
    },
    target_paths={
      "firstName": "family.children.firstName",
      "dateOfBirth": "family.children.dateOfBirth",
      "placeOfBirth": "family.children.placeOfBirth",
      "birthOrder": "family.children.birthOrder",
    },
    source_phrase="My oldest, vince was born in Germany in 1960",
    confidence=0.85,
  ),
  ExtractedClaim(
    claim_id="claim_abc2", kind="person", role="son", entity_index=1,
    fields={"firstName": "Jason", "preferredName": "Jay",
            "dateOfBirth": "1961", "placeOfBirth": "Bismarck"},
    source_phrase="my middle son Jay or Jason was born in Bismarck in 1961",
    confidence=0.87,
  ),
  ExtractedClaim(
    claim_id="claim_abc3", kind="person", role="son", entity_index=2,
    fields={"firstName": "Christopher", "preferredName": "Chris",
            "dateOfBirth": "1962-12-24", "placeOfBirth": None},
    source_phrase="my youngest Chris...born on his dads birhday in december 24 1962",
    confidence=0.78,
  ),
]
```

Shadow Review now shows three review cards:

```
┌─────────────────────────────────────────────────┐
│ SON — Vince                                     │
│   Born: 1960                                    │
│   Place: Germany                                │
│   Birth order: oldest                           │
│   from: "My oldest, vince was born..."          │
│   [Approve] [Correct] [Reject]                  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ SON — Jay (Jason)                               │
│   Born: 1961                                    │
│   Place: Bismarck                               │
│   from: "my middle son Jay or Jason..."         │
│   [Approve] [Correct] [Reject]                  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ SON — Chris (Christopher)                       │
│   Born: 1962-12-24                              │
│   Place: (unknown)                              │
│   from: "my youngest Chris...december 24 1962"  │
│   [Approve] [Correct] [Reject]                  │
└─────────────────────────────────────────────────┘
```

Every field is context for every other field. Approval is meaningful.

---

## Implementation strategy — two approaches

### Strategy A: LLM emits claims directly (RECOMMENDED)

Upgrade the extraction prompt to demand claim-shaped output. The LLM
writes:

```json
[
  {
    "claim_kind": "person",
    "claim_role": "son",
    "fields": {
      "firstName": "Vince",
      "dateOfBirth": "1960",
      "placeOfBirth": "Germany"
    },
    "source_phrase": "My oldest, vince was born in Germany in 1960",
    "confidence": 0.85
  },
  ...
]
```

**Pros:**
- Simpler — no fragment assembly logic
- LLM is already doing the semantic grouping internally; make it explicit
- Easier to test and tune via prompt examples

**Cons:**
- Requires prompt re-engineering
- LLM may regress on single-fact extractions if prompt is too
  claim-heavy (mitigated by examples)
- Rules-fallback path still emits fragments; would need a separate
  fragment-to-claim assembler for that path OR leave rules_fallback
  as legacy fragment output

### Strategy B: Post-processor assembles fragments into claims

LLM still emits fragments. New server-side assembler groups fragments
by proximity in source text, same entity role, adjacent repeatable-group
indices. Outputs claims.

**Pros:**
- LLM prompt doesn't change
- Rules-fallback path gets claims for free

**Cons:**
- Assembler has to guess "what goes with what" — brittle
- Fragment grouping is exactly the problem that caused the bug; asking
  code to do it is recursive
- More state machine logic to test

### Recommendation: Strategy A

Prompt engineering is cheaper than an assembler. The LLM already does
claim-level grouping internally — we just stop throwing away that
structure at the output boundary. Rules-fallback can remain
fragment-based; it's already tagged as lower-trust via
`extractionMethod="rules_fallback"` and the UI can show those separately.

---

## File-level plan (Strategy A)

### Backend — `server/code/api/routers/extract.py`

1. **New response type `ExtractedClaim`** (pydantic model)
2. **Update `_build_extraction_prompt`** to demand claim-shaped JSON with:
   - System prompt: "Group related facts into claims. Each claim is about
     one real-world entity."
   - ~5 example narrator answers → claim-shaped outputs
3. **New parser `_parse_llm_claims`** — reads claim-shaped JSON, validates
4. **Claim → field-path resolver** — map `kind=person, role=son,
   firstName=...` to `family.children.firstName` for backward
   compatibility with projection-sync
5. **Update `ExtractFieldsResponse`** to carry claims as primary, with
   a fallback legacy `items` array for rules-fallback path
6. **Apply guards at claim level** — birth-context, subject, sanity
   filters now operate on claims (usually easier — they have role
   metadata)

### Backend — `server/code/api/db.py` or new module

New table or JSON column for tracking claim decisions:

```sql
CREATE TABLE claim_decisions (
  claim_id TEXT PRIMARY KEY,
  narrator_id TEXT NOT NULL,
  decision TEXT NOT NULL,    -- "approved" | "rejected" | "merged" | "pending"
  decided_by TEXT,           -- operator user id if we have one
  decided_at TEXT,
  merged_into TEXT,          -- claim_id of canonical target if merged
  raw_claim TEXT             -- JSON blob for audit
);
```

### Frontend — `ui/js/bio-builder-shadow-review.js` (likely path)

- Render claims as cards (not field-list tables)
- Card shows: role badge, sub-field list, source phrase, confidence
- Actions: Approve (writes all fields atomically), Correct (edit any
  sub-field), Reject (drops whole claim), Split (rare — operator
  insists two claims were merged by mistake)
- Shadow review empty state should explain what a claim is

### Projection sync — `ui/js/projection-sync.js`

- When a claim is approved: iterate its sub-fields, call existing
  projection-sync paths for each. Preserves existing write-mode rules.
- When a claim is rejected: log reason, discard.
- When a claim is merged: write canonical resolution to
  `claim_decisions.merged_into`, update state.

### Question bank — `data/prompts/question_bank.json`

- Each sub-topic's `extract_priority` stays the same, but the composer
  can now send claim-kind hints: "when answering this sub-topic, expect
  primarily `kind=person, role=child` claims."
- Optional: add `expected_claim_kinds` to each sub-topic for explicit
  contract (may defer to a later content pass).

---

## Migration strategy

Shipping claims-layer means existing shadow review fragments in-flight
need a plan. Options:

1. **Migrate on read** — when rendering shadow review, if item is
   fragment-shaped, wrap it as a single-field claim for display
2. **Accept in parallel for a period** — response returns both `items`
   (fragments) and `claims`. UI renders claims, falls back to items for
   legacy narrators
3. **Clean cut** — deprecate fragment display, ship claims, reject
   pre-claim state

Recommendation: option 2. Response envelope carries both. Frontend
prefers `claims` when present, else falls back. Gives a safe rollback.

---

## Testing strategy

### Unit (pure Python, no FastAPI)

1. Claim parser accepts valid claim-shaped JSON
2. Claim parser rejects malformed claims (missing role, missing fields,
   invalid kind)
3. Claim → field-path resolver covers all `kind/role` combinations
4. Guard filters operate on claims correctly (birth-context, subject,
   sanity — existing tests should pass with claim inputs once adapted)

### Integration (dev venv)

5. POST `/api/extract-fields` with Janice three-children compound →
   returns 3 `kind=person, role=son` claims
6. POST with "my sisters linda and sharon" → returns 2
   `kind=person, role=sister` claims
7. POST with single-fact answer → returns 1 claim (regression — don't
   lose single-fact performance)
8. POST with non-narrator subject ("my son was born...") → subject
   guard at claim level catches it

### Live

9. Re-run the 2026-04-15 Chris/Janice/Kent scripts. Compare shadow
   review UI — should feel meaningfully different.

---

## Acceptance criteria

- [ ] `ExtractedClaim` model shipped
- [ ] LLM prompt upgraded with claim-shaped examples
- [ ] Compound-loss test cases (3 children, 2 sisters) produce
  multiple claims, not zero
- [ ] Single-fact cases still produce clean single claims
  (regression protection)
- [ ] Shadow review UI renders claims as cards, not fragment tables
- [ ] Approve/Reject/Correct operate atomically on a claim's sub-fields
- [ ] Existing guard stack (WO-EX-01C, WO-EX-01D) still catches the
  bugs it catches today
- [ ] Rules-fallback path still works (emits legacy fragments, UI
  handles gracefully)
- [ ] All pre-existing unit tests pass

## Estimated size

- Backend: ~3 days (prompt engineering, parser, claim model, integration)
- Frontend: ~2 days (new review card UI, state management, action wiring)
- Testing: ~1 day
- Total: **~6 days**, likely split across 2 calendar weeks

## Risks

**R1 — LLM can't reliably produce claim JSON.** Mitigation: prompt with
~5 examples, test on 10+ real narrator transcripts, fall back to
fragment parse on parse failure.

**R2 — Claim splitting introduces over-segmentation.** A sentence
"Verene and Bill were inseparable" might produce 2 person-claims when
it should be 1 relationship claim. Mitigation: start with conservative
grouping (only split on explicit role markers like "my son X, my
daughter Y"), allow operator to "Merge" if the system over-splits.

**R3 — Migration friction if operator has in-flight fragment reviews.**
Mitigation: parallel response envelope, feature-flag the UI cutover.

**R4 — Upstream projection-sync assumptions.** Projection-sync writes
one field at a time. A claim approval triggering N field writes means
any single-field failure leaves partial state. Mitigation: wrap claim
approval in a transaction at state layer; if any field fails, rollback.

---

## Depends on

- **WO-EX-SCHEMA-01** (P0 blocker) — must land first. Claims about
  children, spouses, residences cannot exist without target field paths.

## Unblocks

- **WO-UI-SHADOWREVIEW-01** — operator-facing review UX is dependent on
  claim-level data
- **WO-COVERAGE-TRACKER-01** (CT-01) — coverage tracking is meaningful
  only at claim granularity; fragment-coverage is noise

## Report format (for Claude on completion)

```
WO-EX-CLAIMS-01 REPORT

FILES EDITED
- server/code/api/routers/extract.py  (ExtractedClaim, claim parser, guards)
- server/code/api/db.py                 (claim_decisions table)
- ui/js/bio-builder-shadow-review.js    (card renderer, actions)
- ui/js/projection-sync.js              (claim-level approve/reject/merge)
- data/prompts/question_bank.json       (optional: expected_claim_kinds)
- tests/test_extract_claims.py          (new, unit + integration)

ARCHITECTURE
- LLM now emits claim-shaped JSON
- Response envelope carries both `claims` (primary) and `items`
  (legacy fragments, rules-fallback only)
- UI renders claim cards, preferring claims over items

VERIFICATION
- Unit: N tests, all passing
- Integration: Janice 3-children compound returns 3 claims
- Integration: Kent's "linda and sharon" returns 2 claims
- Integration: single-fact regression — clean 1-claim output
- Live: re-ran 2026-04-15 scripts, operator review flow confirmed cleaner

NOTES
- [edge cases discovered during build]
- [migration-path decisions made]
- [frontend UI refinements deferred to follow-on WO]
```
