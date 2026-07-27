# BUG-LORI-REASONING-LEAK-01 — the model's own planning sentence reached the transcript

**Opened:** 2026-07-27 (Chris's ruling, after the WO-EXPORT-ARCHIVE-WRITER-BRIDGE-01 diagnosis surfaced it)
**Status:** CODE-LANDED. Not yet live-verified against the running stack.
**Class:** response-guard detector miss. Not an archive bug, not an export bug, not a Travel Doc wiring bug.

---

## The leak

One live Lori turn was persisted with the model narrating its own decision in front of the real reply:

```
turns.ts   2026-07-27T04:17:38.134681
conv_id    tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3
role       assistant
content    The narrator is speaking in English, so I will respond in English too.
           "Hi there, I'm Lori. I'm here to listen to your story and learn more
            about your experiences. Would you like to share what you were working
            on in Bismarck?"
```

The actual greeting was already there, inside the quotes. Only the planning sentence in front of it was wrong.

## Why the guard did not catch it

The guard pipeline was alive and did run. `chat_ws.py:4375` calls `apply_response_guards` after
comm_control / reflection-shaper finalize the text and **before** persist + the WS done event, so the
repaired text is what reaches the bubble, the TTS pipeline, the transcript and the archive. That call
site is upstream of the modal archive skip at ~4594, so Travel Doc modal turns pass through it like any
other turn.

What failed was detection. `detect_meta_response_leak()` had no pattern for either shape in that sentence:

| Shape in the leak | Nearest existing pattern | Why it missed |
|---|---|---|
| `I will respond **in** English` | `_META_PREAMBLE_RX`: `(?:i'?ll\|i will\|i shall) (?:respond\|reply\|reflect) (?:by\|with\|using)` | wrong preposition — the 2026-07-07 fix enumerated `by/with/using` |
| `The narrator is speaking ..., so I ...` | none | nothing anywhere matched a third-person planning clause |
| `I'll respond **with a** neutral message` | `_META_REASONING_RX` | this one *does* match — it is the 2026-07-10 shape, not this one |

## Scope as ruled

| Item | State |
|---|---|
| Extend the meta-response leak detector only | DONE |
| Pattern: `I will respond in <language>` | DONE |
| Pattern: `I'll respond in <language>` | DONE |
| Pattern: third-person `The narrator is/has ..., so I ...` | DONE |
| Verbatim 2026-07-27 string as the regression fixture | DONE |
| False-positive test for legitimate `respond in` prose | DONE |
| Repair functions unchanged | HELD |
| Guard ordering unchanged | HELD |
| `chat_ws` call site unchanged | HELD |
| Archive / modal surface boundaries unchanged | HELD |
| Export, import-provenance, Picker, Takeout, memoir untouched | HELD |
| Historical 2026-07-10 and 2026-07-27 DB rows left in place | HELD |

## The change

One regex, `_META_REASONING_RX` in `server/code/api/services/lori_response_guards.py`. Two alternatives added:

```
|i(?:'ll| will| shall) (?:respond|reply|answer|speak|continue)\s+in\s+
 (?:english|spanish|french|german|italian|portuguese|inglés|español|
  the same language|that language|their language|the narrator'?s? language)
|the narrator (?:is|has|had|was|seems|appears)\b[^.!?\n]{0,100}?,\s*so i\b
```

Both are deliberately narrow. The language-planning branch is pinned to an explicit language vocabulary
so ordinary narrator-facing prose cannot trip it — *"he never knew how to respond in a crisis"* has no
language token after `in`. The third-person branch is anchored on the `, so I` tail, so the clause has to
actually be a planning statement, not a passing mention of the word "narrator".

## Why no repair change was needed

`_META_REASONING_RX` already drives per-sentence removal inside `repair_meta_response_leak`: matched
sentences are dropped, then the existing `_QUOTED_DRAFT_RX` branch recovers the longest quoted draft.
Dropping the planning sentence leaves the quoted greeting, which is exactly the right answer. Verified:

```
repair("The narrator is speaking in English, so I will respond in English too. \"Hi there, ...\"")
  -> "Hi there, I'm Lori. I'm here to listen to your story and learn more about
      your experiences. Would you like to share what you were working on in Bismarck?"
```

Not the deterministic `Tell me more about that.` fallback — the narrator's real greeting.

## Acceptance

1. Verbatim 2026-07-27 leak detected — `test_the_verbatim_2026_07_27_leak_is_detected`.
2. Repaired output is the quoted greeting — `test_repair_returns_the_quoted_greeting_not_the_meta_sentence`.
3. Existing meta-response guard tests still pass — both pre-existing tests in the file, plus
   `test_the_2026_07_10_shape_is_still_detected` pinning the older pattern.
4. Normal `respond in` prose survives untouched — `test_legitimate_narrator_facing_text_survives_untouched`,
   four controls, each asserted both undetected and byte-identical after repair.
5. No archive boundary test weakened — `tests/test_modal_archive_boundary.py` unchanged, 5/5 green.
6. No production path change except the detector pattern — `test_the_repair_path_was_not_rewritten`
   asserts the quoted-draft branch and both deterministic fallbacks survive, and that no
   bug-specific string ("Bismarck") was smuggled into the module.

## Tests

| Suite | Result |
|---|---|
| `tests/boris_quality/test_phase5_meta_response_guard.py` | 9 tests, OK (7 new + 2 pre-existing) |
| `tests/test_lori_response_guards.py` + `test_lori_meta_response_leak_guard` + `test_lori_seeded_fact_intake_guard` + `test_regex_inline_flags_py311` + `test_modal_archive_boundary` | 96 tests, OK |
| `tests/boris_quality/test_phase6_phrase_as_name_confirmation.py` | 3 tests, OK |
| `tests/test_chat_ws_guard_failure.py` | needs real fastapi — run in `.venv` |

## Files

**Changed:** `server/code/api/services/lori_response_guards.py` (one regex; +24 lines, 20 of them the comment explaining why each branch is bounded)
**Added:** `tests/boris_quality/test_phase5_meta_response_guard.py` gains `ReasoningLeakGuardTests`; this spec.
**Untouched:** `chat_ws.py`, every repair function, guard ordering, `apply_response_guards`, every archive and modal surface boundary, export, import-provenance, memoir.

## Open

- Live verification: the fix is deterministic and unit-proven, but the leak itself was stochastic, so a
  live re-observation is opportunistic rather than schedulable.
- The 2026-07-10 and 2026-07-27 rows stay in the database. They are history, and the no-DELETE posture
  from WO-2 Decision 4 applies to auditable records generally.
