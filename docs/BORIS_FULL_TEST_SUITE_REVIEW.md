# Boris Full Test Suite Review Notes

## Repo surfaces reviewed

### `scripts/harness_lib.py`

The shared harness currently owns:
- `ChapterConfig`
- `HarnessConfig`
- `score_chapter()`
- `cross_chapter_anchor_loop_check()`
- report writing

`score_chapter()` currently returns the original 8-row matrix. The Boris suite demands additional rows so bad Lori responses cannot be counted as PASS.

### `server/code/api/safety.py`

This owns:
- `scan_answer()`
- `detect_crisis()`
- compound child-abuse trigger logic
- false-positive guards

The Boris safety tests directly exercise this module.

### `server/code/api/routers/facts.py`

This owns:
- `FactAddRequest`
- `/api/facts/add`
- Truth-v2 write-freeze via `HORNELORE_TRUTH_V2`

The Boris facts tests prove that when Truth-v2 is enabled, even proposal-shaped legacy requests must receive an explicit migration result, not a Pydantic 422.

### `server/code/api/routers/people.py`

This owns:
- `IntakeSpouse.year_married: Optional[int]`
- `NarratorIntakePayload`

The Boris intake tests directly exercise empty-string coercion.

### `scripts/run_john_baldy_full_diagnostic_harness.py`

This owns:
- Phase 0 evidence scan
- canonical John preflight
- full-family orchestration

The Boris path-normalization tests expect this harness to expose a path-normalizer for Windows/WSL evidence paths.
