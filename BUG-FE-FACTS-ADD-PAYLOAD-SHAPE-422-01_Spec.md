# BUG-FE-FACTS-ADD-PAYLOAD-SHAPE-422-01

**Status:** OPEN — observed 2026-06-17
**Severity:** MEDIUM (silent data-loss class — extracted facts never
persist; failures swallowed by FE try/catch so the operator never
sees an error message)
**Narrator generality:** UNIVERSAL — affects every narrator turn that
fires `_extractFacts`

## Reproduction

1. Start a narrator session (any narrator).
2. Narrator sends a chat turn containing any of the patterns
   `_extractFacts` matches: "born in X", "I'm from X", "married X",
   "moved to X", "graduated from X", etc.
3. FE fires `for f of facts: fetch(API.FACTS_ADD, ...)` at
   `ui/hornelore1.0.html:8630` (or L8572 for fact-seed followups).
4. Backend returns **422 Unprocessable Entity**.
5. FE `try/catch` swallows the failure — operator sees no error;
   the extracted fact is silently dropped.

Live evidence from `.runtime/logs/api.log`:

```
127.0.0.1:47324 - "OPTIONS /api/facts/add HTTP/1.1" 200 OK
127.0.0.1:47324 - "POST /api/facts/add HTTP/1.1" 422 Unprocessable Entity
```

## Root cause

The FE `_extractFacts` builder at `ui/js/app.js:5790-5910` returns
objects built by `_propose` (L5803):

```js
return {
  subject_name,
  relationship,
  field,                     // e.g. "personal.placeOfBirth"
  source_says,               // e.g. "Born or raised in West St. Paul"
  status: isProtected ? "source_only" : "needs_verify",
  confidence,
  narrative_role,
  meaning_tags,
  extraction_method: "rules_fallback",
  provenance: { ... },
};
```

The backend `FactAddRequest` Pydantic model at
`server/code/api/routers/facts.py:55-71` requires:

```py
class FactAddRequest(BaseModel):
    person_id: str                           # REQUIRED
    statement: str = Field(...)              # REQUIRED
    fact_type: str = "general"
    date_text: str = ""
    date_normalized: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = "extracted"                # MUST be in STATUS_VALUES
    inferred: bool = False
    session_id: Optional[str] = None
    source_turn_index: Optional[int] = None
    meta: Dict[str, Any] = {}
    meaning_tags: List[str] = []
    narrative_role: Optional[str] = None
    experience: Optional[str] = None
    reflection: Optional[str] = None
```

with `STATUS_VALUES = ("extracted", "reviewed", "rejected",
"needs_review", "inferred")`.

### Three independent Pydantic-fatal mismatches

1. **`person_id` missing.** The FE `_propose` helper never sets it.
   Required field → 422.

2. **`statement` missing.** The FE uses `source_says` instead of
   `statement`. Required field → 422.

3. **`status` enum wrong.** The FE sends `"needs_verify"` or
   `"source_only"`. Backend requires one of `("extracted",
   "reviewed", "rejected", "needs_review", "inferred")`. Note
   `"needs_verify"` is close to `"needs_review"` but NOT equal →
   422.

(The extra fields `field`, `source_says`, `extraction_method`,
`provenance` would also fail under strict Pydantic, but Pydantic's
default mode is `extra="ignore"` so they're benign on their own.
The three missing/wrong fields above are the load-bearing failure.)

## Why the FE shape diverged

The `_propose` builder was clearly authored against the **proposal**
contract (the WO-13 `/api/family-truth/note/{id}/propose` shape with
`subject_name`/`relationship`/`field`/`source_says`/`status:
needs_verify`), then someone wired the loop to post to the
**fact** endpoint (`/api/facts/add` — the legacy `FactAddRequest`
contract with `person_id`/`statement`/`status: extracted|...`).

The comment block at `app.js:5912-5924` already says of a sibling
function `_extractAndPostFacts`:

> "The legacy /api/facts/add path is NOT used any more. Failures
> are silently ignored — this must never break the chat UI."

But two callers in `hornelore1.0.html` (L8572 and L8630) still post
to `API.FACTS_ADD` directly with the proposal-shaped objects from
`_extractFacts`. Those two callers were missed when the WO-13 Phase
4 family-truth pipeline replaced the Phase 7 path.

Defense-in-depth that ISN'T firing:

- `facts.py:30-46` has a `_truth_v2_enabled('facts_write')` gate that,
  when on, returns **410 Gone** for the legacy endpoint. The 422 we
  see means **`HORNELORE_TRUTH_V2_FACTS_WRITE` is OFF** in the
  current env. If it were on, the gate would catch the FE bug at
  the door with a 410 instead of letting Pydantic 422 every time.

## Why this matters

Per CLAUDE.md design principle 5: *"Provisional truth persists.
Final truth waits for the operator. The interview never waits."*
Provisional extraction is supposed to land in the DB at extraction
time. Today, every fact `_extractFacts` produces silently fails to
persist — the operator-visible Bug Panel Shadow Review queue is
empty NOT because Lori isn't extracting, but because the FE→API
write fails on every turn. That's the exact class of silent
data-loss the principle exists to prevent.

The FE log line at `ui/hornelore1.0.html:8641-8645` claims:

```js
event:                "facts_extracted",
facts_extracted_count: facts.length,
facts_posted_count:   facts.length,    // ← LIES
```

`facts_posted_count` always reports the same number as
`facts_extracted_count` because the `await fetch(...)` doesn't
inspect the response status. So Bug Panel telemetry says "12 facts
posted this turn" when reality is "0 of 12 actually landed."

## Three-way fix

### Layer 1 — Decide the FE contract (one of A or B)

**Option A: Update FE to match `FactAddRequest`.** In `_propose`,
emit `{person_id, statement, fact_type, confidence, status: "extracted"
| "needs_review", meaning_tags, narrative_role, ...}`. Cheapest fix,
preserves the legacy Phase 7 path. ~30 min + tests.

**Option B: Retire the legacy Phase 7 FE path entirely.** Remove
the L8572 and L8630 `fetch(API.FACTS_ADD, ...)` calls. Route the FE
through the WO-13 family-truth pipeline (`_extractAndPostFacts` at
`app.js:5925` and `/api/family-truth/note` + `/propose`). Aligns
with the long-term architecture. ~2 hrs + tests.

Recommend **B** — the comment at `app.js:5912-5924` explicitly says
the legacy path is "NOT used any more"; the two HTML callers are
left-behind code that should be deleted, not patched.

### Layer 2 — Flip `HORNELORE_TRUTH_V2_FACTS_WRITE=1`

Turn on the per-router write-freeze flag in `.env` (and
`.env.example`). After Option B lands, the FE never hits
`/api/facts/add` anyway, but the flag becomes a backstop so any
future regression (or third-party caller) gets a clean 410 with the
message "facts.add is retired under HORNELORE_TRUTH_V2. Use POST
/api/family-truth/note ..." instead of a confusing 422.

### Layer 3 — Fix the telemetry lie

In `ui/hornelore1.0.html:8628-8638`, inspect the fetch response and
emit `facts_posted_count` = number of actual `r.ok` returns, not
`facts.length`. While we're touching it, surface a warning toast for
the operator when any fact fails to post. This lying-success-counter
is what hid the bug for so long.

## Acceptance gates

1. Send a narrator turn containing "I was born in West St. Paul
   Minnesota on December 31 1960." Backend api.log shows EITHER a
   200 on `/api/family-truth/note` + `/propose` (Option B) OR a 200
   on `/api/facts/add` (Option A). No more 422.
2. Bug Panel Shadow Review surface shows the extracted candidates
   for that turn within ~2s of the turn completing.
3. `facts_posted_count` in `lv80LogTurnDebug` matches the number of
   successful posts, not the number of extracted candidates.
4. With `HORNELORE_TRUTH_V2_FACTS_WRITE=1`, a direct curl to
   `/api/facts/add` returns 410 Gone with the migration message.
5. The existing facts_smoke / family-truth pipeline tests
   still pass.

## Files likely touched

### Option B (recommended)
- `ui/hornelore1.0.html` — delete L8570-8574 and L8627-8638 legacy
  posting loops; replace with calls to `_extractAndPostFacts`
- `ui/js/app.js` — `_extractFacts` either retired or refactored to
  return proposal-shape objects for `_extractAndPostFacts`
- `ui/js/api.js` — `FACTS_ADD` constant can stay (still used for
  curl debugging) or be deleted

### Layer 2
- `.env` — add `HORNELORE_TRUTH_V2_FACTS_WRITE=1`
- `.env.example` — document the flag

### Layer 3
- `ui/hornelore1.0.html` — inspect `r.ok` in the posting loop, count
  successes, surface failure toast

## Related lanes

- WO-13 Phase 4 — family-truth pipeline replacement for legacy facts
  write (the architecture this bug is fighting against)
- WO-13 Phase 8 — `flags.truth_v2_enabled('facts_write')` per-router
  flag (the backstop that isn't on yet)
- 2026-04-22 Bug Panel Shadow Review surfaces — the consumer
  expecting these writes to land
- BUG-API-PROFILES-DROPS-INTAKE-KEYS-01 (2026-06-16, fixed) — same
  shape as this: FE/BE contract mismatch silently dropping data

## Investigation notes

Captured via:

1. `tail .runtime/logs/api.log | grep facts/add` confirmed the 422
   fires from real chat turns (not just curl).
2. `server/code/api/routers/facts.py:55-71` Pydantic model is the
   source of truth for the required shape.
3. `ui/js/app.js:5790-5910` `_extractFacts` + `_propose` is where
   the wrong shape is built.
4. `ui/hornelore1.0.html:8570-8638` is where the wrong shape is
   posted to the right endpoint.
5. Live Network capture via Chrome MCP `read_network_requests`
   couldn't isolate the specific failing request (filter behavior on
   substring inconsistent), but the source-side evidence is
   unambiguous — any item built by `_propose` will fail validation.
