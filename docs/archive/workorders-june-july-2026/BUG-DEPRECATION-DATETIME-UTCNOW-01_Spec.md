# BUG-DEPRECATION-DATETIME-UTCNOW-01 — CLOSED (landed 2026-07-23)

**Status:** CLOSED — mechanical sweep landed the same session it was filed  
**Priority:** LOW (was)  
**Filed + closed:** 2026-07-23  

## Outcome

All 23 executable `datetime.utcnow()` call sites across 9 files were replaced with `datetime.now(timezone.utc).replace(tzinfo=None)` in the same commit. Wire format is byte-identical to the pre-sweep naive-UTC ISO strings, so no downstream consumer (memoir export, extractor, projection sync, Lori composer, timeline render) had to change. The `age_arithmetic.py:168` reference is a historical comment only and doesn't call the deprecated API.

## Why NOT `+00:00`

The filed spec initially recommended letting the `+00:00` suffix land as the wire format (Python's default `.isoformat()` output on an aware datetime). Discovery on implementation flipped that recommendation:

- `server/code/api/routers/operator_stack_dashboard.py:215` uses `datetime.strptime(row_ts_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")` — a strict naive format that rejects a `+00:00` suffix.
- `server/code/api/services/stack_monitor.py:544` uses the same strict naive format.

Both parsers strip only `"Z"` before `strptime`. Landing the `+00:00` shape would have broken both silently. The `.replace(tzinfo=None)` step produces exactly the same string `datetime.utcnow().isoformat()` was producing, so both parsers continue to work unchanged.

## Files touched (23 executable sites)

- `server/code/api/api.py` — 4
- `server/code/api/archive.py` — 1
- `server/code/api/db.py` — 8 (includes the `4560/4616/4617` comparison chain — write is naive, parse is naive, compare is naive-to-naive, no tz mismatch)
- `server/code/api/prompt_composer.py` — 2 (local imports inside two functions; `timezone` added to each)
- `server/code/api/routers/narrator_state.py` — 1
- `server/code/api/routers/projection.py` — 2
- `server/code/api/routers/questionnaire.py` — 3 (spec-filing count of 2 was low by one)
- `server/code/api/services/projection_writer.py` — 1
- `server/code/api/services/story_preservation.py` — 1

## Regression gate

New file `tests/test_datetime_utcnow_no_deprecation_warning.py` (2 tests):

- **Static gate** — scans all 9 swept files, fails the build if `datetime.utcnow(` appears in non-comment / non-string source. Comments and docstrings that describe the OLD bug shape are exempted via a `tokenize`-pass strip.
- **Runtime gate** — calls `db._now_iso()`, `archive._now_iso()`, `story_preservation._now_iso()` under `warnings.simplefilter('error', DeprecationWarning)`. Also asserts the returned strings do NOT carry `+00:00` or `Z` suffixes (byte-stability check protects the downstream strict-format parsers).

Under Python 3.10/3.11 the runtime warning wouldn't have fired even pre-sweep (no deprecation strictness); the static gate catches regressions there. Under 3.12+ the runtime gate catches them at the same time.

## Not changed

- No stored-data migration. Every existing ISO timestamp in the DB continues to parse via `fromisoformat` or `strptime` identically.
- No consumer contract changes. Every downstream parser reads the same byte-stable naive-UTC ISO string it was reading before.
- No shape change for the two comparison sites (`db.py:4617` and the pair around it).

## Doc posture

Kept in-tree as a landed-report note for the changelog trail. Safe to delete later once CLAUDE.md's changelog absorbs it. Alternatively, `git rm BUG-DEPRECATION-DATETIME-UTCNOW-01_Spec.md` in a future cleanup commit.
