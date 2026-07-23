# BUG-DEPRECATION-DATETIME-UTCNOW-01

**Status:** PARKED — spec-only, do NOT bundle into the Bucket A+B fold  
**Priority:** LOW (cosmetic deprecation warning on Python 3.12+, no behavioral impact today)  
**Filed:** 2026-07-23 as a companion to the Bucket A+B commit per Chris's direction  

## Symptom

Running any unit-test suite (or the API itself) on Python 3.12+ prints:

```
/mnt/c/Users/chris/hornelore/server/code/api/db.py:87: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
  return datetime.utcnow().isoformat()
```

Observed twice per test run (once at import time, once per fresh test that hits `_now()`). Also fires from `archive.py:40`, `api.py:98`, `api.py:300-301`, `api.py:462`, `prompt_composer.py:1153`, `prompt_composer.py:1167`, `narrator_state.py:47`, `projection.py:56`, `projection.py:64`, `questionnaire.py:86`, `questionnaire.py:95`, plus 8 additional call sites in `db.py` (lines 4560, 4617, 4883, 4949, 5035, 5062, 5097).

Total occurrences: **24 call sites across 8 files** (verified via grep 2026-07-23).

## Why it is deferred

Chris's Bucket A+B directive explicitly said: *"Also create a separate low-priority issue for replacing `datetime.utcnow()` in `server/code/api/db.py` with timezone-aware UTC timestamps. Do not mix that cleanup into this patch."* This spec captures the ask without polluting a focused correctness commit.

## Why it does not need urgent attention

- Python 3.10/3.11 do NOT emit the warning; the API and eval harness run cleanly on both.
- Python 3.12/3.13 emit the DeprecationWarning but the runtime behavior is unchanged (`datetime.utcnow()` still returns a naive UTC datetime).
- All 24 call sites are internal timestamp generators feeding SQLite TEXT columns (ISO-8601 string form). SQLite has no timezone type — the stored string is byte-identical either way.
- No consumer (memoir export, extractor, projection sync, Lori composer, timeline render) parses the timestamp back into a timezone-aware datetime object, so mixing naive-UTC and aware-UTC-with-Z-suffix strings would not break anything.

## Why it will eventually need to land

- The scheduled-for-removal warning becomes an `AttributeError` in whichever Python release ultimately removes `utcnow()` (no concrete date announced as of this filing).
- Timezone-aware ISO strings (with `+00:00` or `Z` suffix) are the correct interop shape once the codebase grows a consumer outside the Python + SQLite loop (e.g., a JSON API surfaced to a JavaScript FE that instantiates `new Date(str)` — naive UTC strings parse as LOCAL time in JS).
- CI on Python 3.13 will start rejecting the warnings once strictness lands.

## Scope

Single mechanical sweep across the 8 files. Replace every `datetime.utcnow()` with `datetime.now(timezone.utc)`, keeping the `.isoformat()` chain intact. Import `timezone` alongside `datetime` where missing.

### Files + line numbers (verified 2026-07-23)

- `server/code/api/db.py` — 8 occurrences (lines 87, 4560, 4617, 4883, 4949, 5035, 5062, 5097)
- `server/code/api/api.py` — 4 (98, 300, 301, 462)
- `server/code/api/archive.py` — 1 (40)
- `server/code/api/prompt_composer.py` — 2 (1153, 1167)
- `server/code/api/routers/narrator_state.py` — 1 (47)
- `server/code/api/routers/projection.py` — 2 (56, 64)
- `server/code/api/routers/questionnaire.py` — 2 (86, 95)
- Plus any additional files a fresh `grep -rn 'datetime\.utcnow'` finds at implementation time.

### One acceptance decision to make first

Should the resulting ISO string carry a `+00:00` suffix (Python default) or a `Z` suffix (RFC 3339 / JS-friendly)?

- **Option A — `+00:00`:** zero-cost, matches Python's default `.isoformat()` output. All existing stored timestamps (naive-UTC, no suffix) continue to work; new ones get `+00:00`. Downstream substring compares (`row['updated_at'] > cutoff`) keep working because ISO-8601 sort order is preserved between the two shapes.
- **Option B — `Z`:** requires a small helper (`_now() -> str`) that strips `+00:00` and appends `Z`. Cleaner interop with any future JS consumer that uses `new Date(str)`. Costs an extra `.replace('+00:00', 'Z')` per call.

Recommend Option A. The interop win from B is speculative; the codebase is Python+SQLite end-to-end today. Revisit if a JS consumer materializes.

## Test posture

- No behavior change. Every existing test continues to pass.
- Add one narrow test that runs under `warnings.simplefilter('error', DeprecationWarning)` and imports `api.db` + calls `_now()` once, asserting no warning fires. Locks the invariant so a future regression is caught immediately.

## Not in scope

- No changes to stored data. Old rows keep their naive-UTC ISO strings.
- No changes to consumers. Every parser continues to accept both shapes.
- No mass-refactor of unrelated deprecation warnings.

## Estimated size

- Code change: ~30 minutes of mechanical sweep.
- Test coverage: ~15 minutes for the assert-no-warning test.
- Total: **one hour, one commit**, no eval impact, no restart delay.

## Suggested commit posture

Standalone commit titled roughly:

> `chore: sweep datetime.utcnow() → datetime.now(timezone.utc) across 24 sites`

Bundle nothing else with it — keeps the sweep reviewable and revert-safe.
