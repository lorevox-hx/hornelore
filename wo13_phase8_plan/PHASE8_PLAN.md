# WO-13 Phase 8 v2 — Corrected Execution Plan

*Written after a full code survey, not from the outside. Every file
path and line reference below has been verified against the
current tree.*

## 0. The one big discovery

The Phase 8 v1 plan assumed five independent read paths (memoir,
export, profile/structuredBio, timeline, chat context) that each
needed their own rewire and flag. After surveying the code, **there
is only one read seam.** Every downstream consumer of "who the
narrator is" funnels through a single API call:

```
GET /api/profiles/{person_id}     →  routers/profiles.py:43
```

Client-side, the response lands in `state.profile`
(`ui/js/app.js:744`) and from there it fans out to every consumer:

| Consumer               | How it reads `state.profile`                                                                 |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| Profile form           | `hydrateProfileForm()` — reads `state.profile.basics/kinship/pets`                           |
| Obituary identity card | `updateObitIdentityCard(state.profile?.basics \|\| {})` — `app.js:791`                       |
| Memoir source name     | `state.profile?.basics?.preferred \|\| basics?.fullname` — `app.js:793`                      |
| Memoir draft prompt    | packed into system prompt by `saveProfile` → `/api/session/put` → `compose_system_prompt`    |
| Timeline spine         | `renderTimeline()` derives `birth_date`/`birth_place` from `state.profile.basics.dob/pob`    |
| Chat context (LLM)     | `saveProfile` POSTs `{profile: state.profile}` to `/api/session/put`; `compose_system_prompt` reads `session_payload` and injects as `PROFILE_JSON: {...}` context block (`prompt_composer.py:605`) |

**The five independent read paths in the v1 plan do not exist in
this codebase.** There is one `fetch(API.PROFILE(pid))` at
`app.js:740`, and every downstream surface — memoir, export,
obituary, timeline, chat — reads from the same in-memory
`state.profile` it populates.

### Things that look like read paths but aren't

- **`routers/memoir_export.py`** — pure DOCX renderer. Accepts
  memoir JSON as a POST body. Has no DB reads. Out of scope.
- **`routers/timeline.py`** — operates on a separate
  `timeline_events` table (user-added events via `POST /timeline/add`).
  Not derived from `facts` and not derived from `profile_json`.
  Out of scope for Phase 8.
- **`routers/projection.py`** — operates on a separate `projection`
  table (interview projection state). Not derived from `facts` and
  not derived from `profile_json`. Out of scope.
- **`ALL_EVENTS` in `app.js`** — a static interview trigger grid.
  Not narrator-derived. Out of scope.
- **`routers/facts.py`** — write path is already gated by Phase 4's
  `HORNELORE_TRUTH_V2` flag. Read path (`/api/facts/list`) exists
  but no downstream consumer calls it — confirmed by full-tree
  grep: zero callers in `server/code/` and zero in `ui/js/`.

### What this means for the plan

Instead of five gated rewirings (`…_MEMOIR`, `…_EXPORT`,
`…_PROFILE`, `…_TIMELINE`, `…_CHAT`), Phase 8 is **one gated
rewiring of `api_get_profile`**. When the flag is on, that
endpoint returns a profile_json assembled from promoted truth
instead of the raw `profiles.profile_json` blob. Every downstream
surface — memoir, obituary, timeline spine, chat context — flips
automatically because they all read `state.profile`.

This is a much safer plan than v1 because:
- One change point, not five.
- Rollback is one env variable.
- The harness only has to seed one fixture and assert on one endpoint.
- Chat context can never see raw shadow notes or proposals — the
  system prompt is built from `session_payload.profile`, and the
  only thing that writes to `session_payload.profile` is
  `saveProfile`, which reads from `state.profile`, which reads
  from `/api/profiles/{id}`.

## 1. Flag scheme

**One flag, new:**

```
HORNELORE_TRUTH_V2_PROFILE   (default off)
```

- OFF → `api_get_profile` returns the legacy `profiles.profile_json`
  blob exactly as today.
- ON  → `api_get_profile` returns a profile_json assembled by
  `build_profile_from_promoted(person_id)`, with the unchanged
  legacy fields merged through for anything promoted truth doesn't
  cover.

**One helper shared across any future flag growth:**

```python
# server/code/api/flags.py  (new file, ~15 lines)
import os

def _truthy(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")

def truth_v2_enabled(consumer: str) -> bool:
    """consumer ∈ {'profile', 'facts_write'}.
    - 'profile'     → HORNELORE_TRUTH_V2_PROFILE  (Phase 8)
    - 'facts_write' → HORNELORE_TRUTH_V2          (Phase 4, unchanged)
    """
    if consumer == "profile":
        return _truthy(os.environ.get("HORNELORE_TRUTH_V2_PROFILE"))
    if consumer == "facts_write":
        return _truthy(os.environ.get("HORNELORE_TRUTH_V2"))
    return False
```

Phase 4's `_truth_v2_enabled` in `routers/facts.py:30` is
rewritten as `return truth_v2_enabled("facts_write")` and its
behaviour is preserved exactly. No Phase 4 regression.

**Why not five flags?** Because there are not five seams. If a
future phase needs an independent seam (e.g. server-side chat
context bypassing session_payload), we add a new `consumer` string
then. Today, `profile` is the only new one.

## 2. Field mapping — legacy profile_json ↔ promoted truth

The `basics` block in `profile_json` has ~18 fields. Of those,
five overlap directly with the protected identity fields in
`FT_PROTECTED_IDENTITY_FIELDS` (Phase 7):

| profile_json key         | promoted truth field      |
| ------------------------ | ------------------------- |
| `basics.fullname`        | `personal.fullName`       |
| `basics.preferred`       | `personal.preferredName`  |
| `basics.dob`             | `personal.dateOfBirth`    |
| `basics.pob`             | `personal.placeOfBirth`   |
| `basics.birthOrder`      | `personal.birthOrder`     |

The other ~13 `basics` fields have no Phase 7 equivalent
(`culture`, `country`, `pronouns`, `phonetic`, `language`, the
five `legal*` fields, `timeOfBirth*`, `zodiac*`,
`placeOfBirth{Raw,Normalized}`). They will be **passed through
unchanged from the legacy `profiles.profile_json`** when the flag
is on. This is a hybrid read, which is the honest thing to do —
Phase 7 only proved truth for the 5 protected fields plus the
free-form `employment` / `marriage` / `residence` / `education`
narrative rows, and we shouldn't fake coverage for data types the
review pipeline hasn't been exercised on.

**Kinship and pets** are also passed through unchanged. Phase 7
does model kinship via `relationship != 'self'` rows, but the
`profile_json.kinship` shape uses a different schema (relation +
name + dob + pob + notes) and translating promoted rows into that
shape is its own decision. Phase 8 defers it.

**Free-form promoted rows** (`employment`, `marriage`, `residence`,
`education`, and any future field the extractor learns) are
written into a new `basics.truth[]` list that downstream consumers
can read, rendered inline in memoir (see section 6), and available
to the chat system prompt as structured data.

### Resulting profile_json shape (flag on)

```json
{
  "basics": {
    "fullname": "...",                    // from promoted truth (5 protected fields)
    "preferred": "...",
    "dob": "...",
    "pob": "...",
    "birthOrder": "...",
    "culture": "...",                     // passed through from legacy
    "country": "...",                     // passed through from legacy
    "pronouns": "...",
    "phonetic": "...",
    "language": "...",
    "legalFirstName": "...",
    "legalMiddleName": "...",
    "legalLastName": "...",
    "timeOfBirth": "...",
    "timeOfBirthDisplay": "...",
    "birthOrderCustom": "...",
    "zodiacSign": "...",
    "placeOfBirthRaw": "...",
    "placeOfBirthNormalized": "...",
    "_qualifications": {                  // NEW — per-field qualification text
      "personal.dateOfBirth": "Kent is unsure of the exact year"
    },
    "truth": [                            // NEW — free-form promoted rows
      {
        "subject_name": "Kent James Horne",
        "relationship": "self",
        "field": "employment",
        "value": "worked at the shipyard from 1965 until 2003",
        "qualification": "",
        "status": "approve",
        "reviewer": "chris",
        "source_row_id": "...",
        "updated_at": "..."
      }
    ]
  },
  "kinship": [...],                       // passed through from legacy
  "pets": [...]                           // passed through from legacy
}
```

`basics._qualifications` and `basics.truth` are additive keys —
the client's `normalizeProfile` (`app.js:1121`) is tolerant of
unknown keys, so dropping them in won't break the existing
profile form or the obituary renderer. This was verified by
reading `normalizeProfile`: it only reads named keys, it doesn't
strip extras.

## 3. Phase 8a — `build_profile_from_promoted` (REQUIRED)

**New function in** `server/code/api/db.py` **(add after the
existing `ft_list_promoted` helper from Phase 7, around line
5000 in the current tree):**

```python
def build_profile_from_promoted(person_id: str) -> Dict[str, Any]:
    """Assemble a profile_json-shaped dict from family_truth_promoted.

    Rules:
      - Protected identity fields (5) are written into basics.*
        using the legacy key names (fullname, preferred, dob, pob,
        birthOrder).
      - Non-identity promoted rows (employment, marriage, residence,
        education, ...) are written into basics.truth[] as a flat
        list of {subject_name, relationship, field, value,
        qualification, status, reviewer, source_row_id, updated_at}.
      - approve_q rows carry their qualification string into
        basics._qualifications[field] AND into the truth[] row.
      - Any `basics` field that is NOT one of the 5 protected fields
        is passed through unchanged from the legacy profile_json
        (culture, country, pronouns, all the legal*, zodiac, etc).
      - kinship[] and pets[] are passed through unchanged.
      - If no promoted rows exist for a person, fall back entirely
        to the legacy profile_json (so the flag flip never wipes a
        narrator's data visibly — worst case is "same as today").

    Returns a dict with the exact shape api_get_profile currently
    returns under key 'profile'.
    """
    # ... implementation walks ft_list_promoted, merges over legacy
    # basics, drops qualification + truth sidecar keys.
```

Mapping table used inside the function:

```python
_PROMOTED_TO_BASICS = {
    "personal.fullName":      "fullname",
    "personal.preferredName": "preferred",
    "personal.dateOfBirth":   "dob",
    "personal.placeOfBirth":  "pob",
    "personal.birthOrder":    "birthOrder",
}
```

**Estimated size:** ~60 lines of Python, no new DB queries (uses
`ft_list_promoted` from Phase 7 + `get_profile` from the existing
profiles layer).

## 4. Phase 8b — backfill helper (REQUIRED for safe rollout)

**New function in** `server/code/api/db.py` **(immediately after
`build_profile_from_promoted`):**

```python
def ft_backfill_from_profile_json(person_id: str) -> Dict[str, Any]:
    """Seed shadow notes + proposal rows from existing profile_json.

    For each of the 5 protected identity fields present on
    basics.*, create:
      1. A shadow note in family_truth_notes describing where the
         value came from (source_kind='backfill',
         source_ref='profile_json.basics.{key}',
         created_by='backfill').
      2. A proposal row in family_truth_rows with:
           status            = 'needs_verify'
           extraction_method = 'manual'
           confidence        = 1.0
           source_says       = <current value>
           subject_name      = <display_name>
           relationship      = 'self'
           field             = <promoted-truth field name>

    Does NOT auto-promote. Does NOT write to family_truth_promoted.
    The reviewer manually approves and promotes each row via the
    Phase 6 review drawer.

    Idempotent: skips any field that already has an existing
    proposal row for (person_id, subject_name, field), so re-running
    the backfill doesn't create duplicates.

    Returns {person_id, created_rows, skipped_existing}.
    """
```

**Why needs_verify and not approve**: because the reviewer has to
consciously approve before the protected field enters the truth
layer. This is the whole point of Phase 6. Auto-approving would
defeat the "human review" step.

**Why `extraction_method='manual'`**: so the Phase 7 blocking rule
(`protected + rules_fallback → blocked`) does not fire. Manual is
one of the three paths that CAN promote to protected fields.

**Optional companion endpoint:**

```python
# server/code/api/routers/family_truth.py
@router.post("/backfill")
def api_backfill(req: BackfillRequest):
    person = _require_person(req.person_id)
    _block_if_reference(person)
    result = db.ft_backfill_from_profile_json(req.person_id)
    return {"ok": True, **result}
```

Not called automatically. The operator triggers it per-narrator
before flipping the flag for that narrator.

## 5. Phase 8c — patch `api_get_profile` (the actual rewire)

**File:** `server/code/api/routers/profiles.py`
**Lines to edit:** 43–49

**Before (current):**

```python
@router.get("/{person_id}")
def api_get_profile(person_id: str):
    if not get_person(person_id):
        raise HTTPException(status_code=404, detail="person not found")
    ensure_profile(person_id)
    row = get_profile(person_id)
    return {"person_id": person_id, "profile": row["profile_json"], "updated_at": row["updated_at"]}
```

**After:**

```python
@router.get("/{person_id}")
def api_get_profile(person_id: str):
    person = get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="person not found")
    ensure_profile(person_id)
    row = get_profile(person_id)
    legacy_profile = row["profile_json"]
    if truth_v2_enabled("profile"):
        try:
            profile_obj = db.build_profile_from_promoted(person_id)
        except Exception as exc:
            logger.warning(
                "build_profile_from_promoted failed for %s, falling back to legacy: %s",
                person_id, exc,
            )
            profile_obj = legacy_profile
    else:
        profile_obj = legacy_profile
    return {
        "person_id": person_id,
        "profile":   profile_obj,
        "updated_at": row["updated_at"],
        "source":    "promoted_truth" if truth_v2_enabled("profile") else "legacy",
    }
```

The `source` key is purely diagnostic — lets the UI and operators
inspect which path a response came from. The Phase 6 review drawer
can show a small "reading from promoted truth" badge when it's
set.

The try/except around `build_profile_from_promoted` is the safety
net: if the builder ever throws (bad data, schema surprise), the
endpoint falls back to the legacy blob instead of returning 500.
This is the rollback-without-rollback path — even with the flag
on, a single narrator's broken promoted data doesn't take the
endpoint down.

**Import additions at top of `profiles.py`:**

```python
from .. import db
from ..flags import truth_v2_enabled
import logging
logger = logging.getLogger("profiles")
```

## 6. Phase 8d — UI refresh hook (the promote → memoir feedback loop)

**File:** `ui/js/wo13-review.js`
**Function:** `wo13PromoteClicked` (around line 450 in the Phase 6
module)

**Before (current, Phase 6):**

```js
async function wo13PromoteClicked(personId) {
  if (wo13IsCurrentNarratorReadOnly()) { /* refuse */ return; }
  const res = await wo13PromoteApproved(personId);
  // ... show toast, reload queue
}
```

**After (additive — no existing behaviour removed):**

```js
async function wo13PromoteClicked(personId) {
  if (wo13IsCurrentNarratorReadOnly()) { /* refuse */ return; }
  const res = await wo13PromoteApproved(personId);

  // Phase 8: after a successful promote, the promoted truth layer
  // has changed. If the server is reading profile from promoted
  // truth (HORNELORE_TRUTH_V2_PROFILE=1), the current state.profile
  // is now stale. Re-fetch and re-push to session_payload so the
  // next chat turn sees the new truth.
  try {
    if (typeof window.lvxRefreshProfileFromServer === "function") {
      await window.lvxRefreshProfileFromServer(personId);
    }
  } catch (e) {
    console.warn("[wo13] profile refresh after promote failed:", e);
  }

  // ... existing toast + reload queue
}
```

**New tiny shim in** `ui/js/app.js` **(add near `saveProfile`,
around line 1143):**

```js
// Phase 8: refresh state.profile from server and push to session.
// Called by wo13PromoteClicked after a successful promote so the
// memoir/obituary/chat surfaces all see the new promoted truth
// without a manual page reload.
window.lvxRefreshProfileFromServer = async function(pid) {
  if (!pid) return;
  try {
    const r = await fetch(API.PROFILE(pid));
    if (!r.ok) return;
    const j = await r.json();
    state.profile = normalizeProfile(j.profile || j || {});
    try { localStorage.setItem("lorevox_offline_profile_"+pid, JSON.stringify(state.profile)); } catch {}
    // Re-render everything that reads from state.profile
    hydrateProfileForm();
    updateObitIdentityCard(state.profile?.basics || {});
    const msn = document.getElementById("memoirSourceName");
    if (msn) {
      const n = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "No person selected";
      msn.textContent = n;
    }
    renderTimeline();
    // Push new snapshot to session payload so next chat turn picks it up
    if (state.chat?.conv_id) {
      fetch(API.SESS_PUT, {
        method: "POST",
        headers: ctype(),
        body: JSON.stringify({
          conv_id: state.chat.conv_id,
          payload: { profile: state.profile, person_id: pid },
        }),
      }).catch(() => {});
    }
  } catch (e) {
    console.warn("[lvx] refresh profile after promote failed:", e);
  }
};
```

No WebSocket, no `stream_bus` changes. One fetch + one re-render +
one session-put.

## 7. Phase 8e — test harness (REQUIRED before any flag flip)

**File:** `wo13_test/run_phase8_test.py` (new)

**Fixture:** synthetic narrator "Ada Lovelace" with a carefully
chosen mix of states:

| # | field                    | extraction_method | initial status | expected under flag ON                          |
| - | ------------------------ | ----------------- | -------------- | ------------------------------------------------ |
| 1 | `personal.fullName`      | manual            | approve        | → `basics.fullname`                              |
| 2 | `personal.dateOfBirth`   | manual            | approve        | → `basics.dob`                                   |
| 3 | `personal.placeOfBirth`  | rules_fallback    | approve        | BLOCKED, not in `basics.pob`; legacy value used  |
| 4 | `employment`             | rules_fallback    | approve_q      | → `basics.truth[]` + `_qualifications.employment`|
| 5 | `marriage`               | rules_fallback    | needs_verify   | NOT in basics.truth[] (not promoted)             |
| 6 | `residence`              | rules_fallback    | reject         | NOT in basics.truth[]                            |
| 7 | `education`              | rules_fallback    | source_only    | NOT in basics.truth[]                            |

Plus an existing `profiles.profile_json` with `basics.culture=
"Victorian English mathematician"` that must appear in the output
regardless of flag state (passthrough field).

**Assertions:**

1. **Schema check** — `build_profile_from_promoted` returns a dict
   with keys `basics`, `kinship`, `pets`.
2. **Basics mapping** — `basics.fullname == "Ada Lovelace"`,
   `basics.dob == "1815-12-10"`.
3. **Blocked protected field** — `basics.pob` equals the legacy
   passthrough value (from `profiles.profile_json`), NOT the
   blocked promoted row's value. Proof that the block propagated.
4. **Passthrough** — `basics.culture` equals the legacy value.
5. **`truth[]` membership** — `basics.truth[]` contains exactly
   one row (employment, approve_q). Marriage/residence/education
   are absent because they aren't in approve/approve_q.
6. **Qualification carried** — `basics._qualifications.employment`
   equals the qualification string byte-for-byte.
7. **Empty-promoted fallback** — `build_profile_from_promoted` on
   a narrator with zero promoted rows returns the legacy blob
   unchanged.
8. **Endpoint flag OFF** — `api_get_profile` returns legacy blob,
   `source="legacy"`.
9. **Endpoint flag ON** — `api_get_profile` returns the assembled
   profile, `source="promoted_truth"`, and the schema matches
   expectations from assertions 1–6.
10. **Backfill seeding** — `ft_backfill_from_profile_json` on a
    fresh narrator with only `basics` set produces 5 proposal
    rows, all `status='needs_verify'`, all
    `extraction_method='manual'`, none written to
    `family_truth_promoted`.
11. **Backfill idempotency** — second call returns zero new rows,
    skipped_existing == 5.
12. **Promote-refresh round-trip** — seed a narrator, call
    `ft_promote_row` on a manual protected-field row, then call
    `api_get_profile` with flag on, assert the new value is
    visible in `basics.*`. Proves the promote → refresh → profile
    loop works end-to-end without the UI.
13. **Reference narrator unaffected** — `api_get_profile` on a
    reference narrator (Shatner) with flag on returns a legacy
    blob and does NOT invoke `build_profile_from_promoted`
    (reference narrators have no promoted rows and shouldn't).
14. **Regression** — re-run Phase 4, 5, 6, 7 harnesses; all must
    still pass.

**Skeleton:**

```python
# run_phase8_test.py
import sys, os, sqlite3, time, json, traceback
# fastapi/pydantic stub (same as Phase 4/7)
# ...
import api.db as H
import api.routers.profiles as profiles_router
from api.flags import truth_v2_enabled

# 14 sections, each wrapped in its own assert/try-except
```

Target: 14 numbered sections, all passing, matching the Phase 4–7
harness style.

## 8. Phase 8f — qualification rendering in memoir

**Decision (per sign-off):** inline italic em-dash suffix.

Example:

```
Kent married Janice in the summer of 1968 — *he recalls it may
have been 1969*.
```

**Where it gets rendered:** client-side, in whatever function
builds the memoir draft from `state.profile`. Looking at
`app.js:1630` (`writeMemoir`), the existing prompt path is a pass
to the LLM — the model is told to "Ground every detail in the
collected interview answers. Do not invent facts." The cleanest
change is:

1. When the memoir prompt is built, walk `state.profile.basics.truth[]`
   and render each row as plain prose, formatting any row with a
   non-empty `qualification` using the em-dash suffix.
2. Append this block to the prompt as a "VERIFIED FACTS" section
   so the model uses it as ground truth.

This is one small edit in `app.js` around the memoir draft
builder, purely additive. The exact function name depends on
where the current draft-build lives; I'll pin it during
implementation.

No DOCX export changes needed — the export router is a passive
renderer and will preserve any italic/em-dash the client puts in
the memoir body.

## 9. Rollout

**Staged, but single-flag.** The flag is narrator-scoped via
environment, so the rollout is temporal, not per-narrator:

**Step 0 — Pre-flip preparation (MANDATORY)**
- Run `ft_backfill_from_profile_json` for every live narrator
  that has existing `profile_json` data. This seeds
  `needs_verify` proposal rows for the 5 protected identity
  fields, populated from current profile content.
- Reviewer walks through the Phase 6 review drawer for each
  narrator and promotes the rows that are correct.
- At the end of step 0, every live narrator has at least the 5
  protected identity fields in `family_truth_promoted`, approved
  by a reviewer.

**Step 1 — Flag flip in dev**
- `export HORNELORE_TRUTH_V2_PROFILE=1`, restart server.
- Sanity check: profile form, obituary, memoir source name,
  timeline spine, chat context all render correctly.
- Run `run_phase8_test.py` with the flag on.

**Step 2 — Observation window (recommended ~48h)**
- Leave flag on in dev.
- Every promote action must refresh profile correctly (via the
  Phase 8d hook).
- Any oddity → flip the flag off and investigate.

**Step 3 — Flag flip in production**
- Same env variable, same restart.
- Rollback is `unset HORNELORE_TRUTH_V2_PROFILE` + restart.
- No data is lost on rollback — promoted truth stays where it is,
  the read path just reverts to `profile_json`.

## 10. Rollback plan

**Instant rollback:**
```
unset HORNELORE_TRUTH_V2_PROFILE
systemctl restart lorevox-api     # or equivalent
```

**What survives rollback:**
- `family_truth_promoted` table content is intact.
- Proposal rows are intact.
- Shadow notes are intact.
- Review UI still works.
- The only change is `api_get_profile` returning legacy blob again.

**Data-loss risk:** zero. There is no write path in Phase 8 that
writes into `profiles.profile_json`. Only reads.

## 11. What Phase 8 does NOT do

- **Does not rewire `timeline_events`.** Separate table, separate
  write path (`POST /api/timeline/add`). If we want promoted-truth-
  derived timeline events, that's a Phase 9 deliverable that
  inserts into `timeline_events` on promote, not a Phase 8 concern.
- **Does not rewire `projection`.** The projection table is an
  interview-state snapshot used for the projection tab. Not
  narrator truth.
- **Does not rewire the extended `basics.*` fields** (culture,
  country, pronouns, language, all the legal*, timeOfBirth*,
  zodiac*, placeOfBirth{Raw,Normalized}). Those pass through
  from the legacy profile_json. Promoting them is a Phase 9
  decision.
- **Does not decompose `kinship[]` or `pets[]` into FT rows.**
  Pass-through.
- **Does not add a server-side direct read of promoted truth in
  `compose_system_prompt`.** Chat context continues to flow
  through session_payload, which is updated by the new promote-
  refresh hook. This avoids re-designing the chat prompt path.
- **Does not include `[SHADOW_NOTE]` or `[PROPOSAL]` tags in
  chat context.** Confirmed with user: chat context reads
  promoted truth (via profile_json via session_payload) and the
  filtered rolling summary only. Nothing else.
- **Does not auto-promote backfilled rows.** Review is still
  required. Zero auto-promotion.

## 12. Deliverables (end-of-Phase checklist)

1. `server/code/api/flags.py` — new shared flag helper
2. `server/code/api/db.py` — `build_profile_from_promoted`,
   `ft_backfill_from_profile_json`, constants, unit helpers
3. `server/code/api/routers/profiles.py` — patched
   `api_get_profile` with flag-gated read, try/except fallback,
   `source` response key
4. `server/code/api/routers/family_truth.py` — new `/backfill`
   POST endpoint (optional, can be internal-only via CLI)
5. `server/code/api/routers/facts.py` — `_truth_v2_enabled`
   rewritten to use `flags.truth_v2_enabled("facts_write")`,
   behaviour preserved
6. `ui/js/app.js` — `lvxRefreshProfileFromServer` shim
7. `ui/js/wo13-review.js` — `wo13PromoteClicked` calls the shim
   after a successful promote
8. `wo13_test/run_phase8_test.py` — 14-section harness
9. `wo13_phase8_proof/PHASE8_PROOF.md` — proof packet with:
   - test output
   - Phase 4/5/6/7 regression output
   - before/after JSON snapshots for Ada Lovelace (the fixture)
   - end-to-end trace for promote → refresh → profile response
10. Commit on `main` with scoped message

## 13. What could still go wrong (risk register)

- **`normalizeProfile` on the client unintentionally strips
  `basics.truth[]` or `basics._qualifications`.** Verified by
  reading `app.js:1121` — it only reads named keys, doesn't
  strip extras. Low risk, but the Phase 8 harness asserts it
  explicitly.
- **`compose_system_prompt` sees a stale session_payload after
  promote.** Mitigated by the UI refresh hook (`saveProfile` path
  called via `lvxRefreshProfileFromServer`). Acceptable residual
  risk: if the user promotes but doesn't say anything in chat
  for a while, the stale state is in `session_payload` anyway,
  which is how it already worked before Phase 8.
- **A narrator with `profile_json.basics` populated but zero
  promoted rows flips the flag and suddenly the system renders
  their data from nothing.** Mitigated by the empty-promoted
  fallback: when `ft_list_promoted(person_id)` returns zero rows,
  `build_profile_from_promoted` returns the legacy blob
  unchanged. This is checked by assertion #7.
- **`HORNELORE_TRUTH_V2_PROFILE` and `HORNELORE_TRUTH_V2` get
  confused.** Mitigated by the `truth_v2_enabled(consumer)`
  helper and a comment in `facts.py` documenting which flag is
  which.

---

**Bottom line:** the work collapses from "five gated rewirings"
to "one function + one flag + one endpoint patch + one client
hook + one harness". The collapse is because the code already
has only one narrator-truth read seam. We are not oversimplifying
— we are matching the plan to reality.

**Request for approval:** ship this plan as the Phase 8 v2
canonical doc and start executing in order
(flags.py → build_profile_from_promoted → backfill → profiles.py
→ app.js shim → wo13-review.js → harness → proof → commit).
