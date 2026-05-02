# Code Review 2026-05-01 OVERNIGHT — Parent-Session Blast Radius Audit

**Scope:** Pre-parent-session safety review of Hornelore codebase. Focus: chat-turn path, story preservation, and narrative identity protection.

**Methodology:** Reviewed design principles (CLAUDE.md), critical router paths, safety integration, database accessors, and UI identity gates.

**Date:** 2026-05-01 | **Reviewer:** Claude Haiku 4.5 | **Duration:** ~20 minutes

---

## Part A — Today's changes (self-review)

**Scope:** Code I authored or modified in this session (2026-05-01 evening).
Self-review, looking for issues my own pattern-matching may have introduced.

### File: ui/js/session-loop.js (Patches A + B)

**INFO** — `_validateProtectedIdentityValue` rules 6+7 (question / imperative). The two new rules correctly precede the existing rules 1–5, so a question or imperative is caught before the past-tense / first-person checks. Regex set `^(what|where|when|who|whom|why|how|which|whose)\s+(is|are|was|were|do|does|did|can|could|would|should|will|shall|am)\b` is intentionally narrow — single-word wh + single-word verb. Doesn't catch "What kind of..." or "Why on earth would...". Acceptable trade-off for v1; the conversational-input gate (Patch B) at the dispatcher catches the broader case.

**AMBER** — `_isConversationalNonAnswer` runs only when `loop.currentSection && loop.currentField` are set. On a freshly-created narrator with no prior asked field, the gate is skipped and Lori sees the first user turn unprocessed. **Live evidence:** TEST-09 in the 21:44 harness run replied with the intro hello instead of the date answer, because the narrator was at "first hello" state when the harness sent "What day is it?". Earlier 16:50 run PASSED because narrator was already in "asking-for-name" state by then. **Suggested fix (parent-readiness lane):** also fire the conversational gate before the BUG-227 identity rescue at session-loop.js ~L352, so it catches questions even on the first turn. Currently parked as a TEST-09 harness timing fix, but the same path could affect a real narrator who opens with a question.

**INFO** — `tellingStoryOnce` flag is set on conversational rejection. Piggybacks the existing BUG-212 digression-suppression mechanism, which is correct — we want next-turn QF also suppressed so Lori's natural reflection completes.

### File: ui/js/bug-panel-dashboard.js + 4 sibling files (BUG-224 frontend port fix)

**INFO** — All five files use the same pattern: `const _O = (typeof ORIGIN !== "undefined" && ORIGIN) || "http://localhost:8000"`. Defensive fallback works if `api.js` hasn't loaded by import time. Live-verified: dashboard cards populated immediately after Chrome reload, no 404 spam.

**INFO** — Hardcoded fallback `"http://localhost:8000"` matches the `ORIGIN` default in `api.js`. If a future deployment uses a different `LOREVOX_API` value, the fallback would be wrong — but `ORIGIN` will be defined in that case, so the fallback never fires in practice.

**INFO** — `safety-banner.js` `ACK_ENDPOINT` is `_O + "/api/operator/safety-events"` — note that's the LIST endpoint, and acks are sent via `POST /{id}/acknowledge` (path appended at call site). Visually confusing but existing pattern, not introduced by my fix.

### File: scripts/ui/run_parent_session_readiness_harness.py

**INFO** — `_complete_identity_for_test_narrator()` defaults match ChatGPT's manual TEST-08A pack. Overridable kwargs, idempotent. 2-second post-intake settle hardcoded; sufficient for identity_complete propagation. Live-verified TEST-12: identity_completed=True, BB.dateOfBirth persisted as 1940-02-29.

**AMBER** — `_run_narration_sample` waits 90s for narration reply, then 45s per follow-up. On GPU OOM, the request hangs ~90s before timeout. Each follow-up adds 45s. A single failing pair burns ~5 min. **Suggested fix:** detect OOM error text in Lori's reply (`"Chat error: Not enough GPU memory"`) and bail out of the per-pair loop early. Saves ~3 min per failing pair. Tracked under WO-EX-GPU-CONTEXT-01 Phase 3 (OOM recovery surfaces a warm fallback that the harness will need to recognize anyway).

**AMBER** — `assert_no_memory_river()` walks `body *` selector — O(N) with N=DOM-elements. Fast enough today (500–2000 elements) but worth narrowing to `#lvNarratorRoom *` if perf becomes an issue. Low priority.

**INFO** — `wait_for_lori_turn` reads `args_json` from the structured-arg console capture. The `decode("unicode_escape")` at the end correctly un-escapes JSON-stringified content. Round-trips Lori's reply with embedded apostrophes/curly quotes cleanly (verified TEST-12).

### File: docs/test-data/narration_samples.json

**INFO** — Three narrators authored by ChatGPT against spec. Diversity check passes (ages 73-88, regions Philippines/Nigeria/US-Southwest, careers nurse/librarian/mechanic, mixed family structures + genders + surnames). Word counts in expected ranges. Ground truth dicts complete, follow_up matchers reasonable.

**INFO** — Narrator IDs `test_narrator_002` through `_004` (skipping 001 because Christopher's inline samples are the canonical baseline). Numbering convention extends naturally if Chris adds more later — worth documenting in NARRATION_SAMPLES_AUTHORING_SPEC.md.

### Cross-cutting

**INFO** — Patch A regex set in session-loop.js and the harness's `LEAP_YEAR_FAIL_PATTERNS` are independent — different scopes, different sources of truth. Low-risk but worth noting if anyone tries to consolidate.

**INFO** — TEST-12 negative matchers fire BEFORE positive matchers in the if/elif chain (file: scripts/ui/run_parent_session_readiness_harness.py, lines ~800-870). A reply containing "1940" + "let me check that date" would correctly hard-stop. Good ordering.

### Summary

**0 RED, 4 AMBER, 11 INFO** in today's-changes self-review.

The 4 AMBERs:
1. Conversational gate doesn't fire on first-turn-of-fresh-narrator (TEST-09 root cause)
2. Narration-pair OOM doesn't short-circuit follow-ups (5-min waste per failing pair)
3. `assert_no_memory_river` broad selector (perf only, fine today)
4. softened-state init in chat_ws.py (per agent's Part B, surfaced again here)

None are parent-session blockers. Three could be addressed before the GPU OOM lane lands.

---

## Part B — Parent-Session Blast Radius

### File: server/code/api/routers/chat_ws.py

**AMBER** | **Lines 356–361** — Unbound variable guard insufficient for softened-state path

The defensive `_safety_result = None` init at L361 covers the legacy safety path, but there is a logical gap in softened-mode initialization. If a chat turn has empty or whitespace-only `user_text`, the `if user_text and user_text.strip():` block at L418 is skipped entirely, so `_safety_result` remains None. On line 445, the code checks `if _safety_result and _safety_result.triggered:` which is safe. However, the softened-state read at L384–391 is gated behind a flag check (`_softened_response_enabled`) that is separate from the safety scan. If the flag is ON but the text is empty, `_softened_state` is read (good) but never used because the safety-trigger cascade is skipped. **This is not a bug per se, but it's fragile:** the softened state is loaded but the composer later at L646 checks `if _softened_state and _softened_state.get("interview_softened"):` which will be True even though no safety trigger fired. **Consequence:** an empty-turn reconnect could falsely appear to trigger softened mode. **Suggested fix:** initialize both `_safety_result` and `_softened_state` to explicit safe defaults at function start, OR explicitly check that softened mode was read at all (add a `_softened_state_loaded` flag).

---

**INFO** | **Lines 438–443** — Default-safe fallback path ordering correct

The default-safe fallback (L438–443) correctly forces `turn_mode = "interview"` to guarantee the ACUTE SAFETY RULE in `prompt_composer.py` fires when `scan_answer()` fails. This override happens BEFORE model load at L633, so a cold/slow LLM never blocks safety inference. Good defensive posture. No issue here.

---

**AMBER** | **Lines 201–322** — Story preservation skips system directives, but edge case exists

The story-capture block correctly skips `[SYSTEM_*` directives (Patch A at L230) so narrator-facing guidance cannot fire the trigger. However, there is a narrower case: a narrator could manually type `[SYSTEM_QF: ...` at the start of their message as part of a story (e.g., "Someone told me [SYSTEM_QF: this was odd]"). The lstrip-then-check pattern at L229–230 would skip this. **Likelihood:** very low — narrators would need to manually type exactly that bracket pattern. **Consequence:** the message would be silently not preserved (no error, no log marker indicating skip). **Suggested fix:** emit a low-priority `[story-trigger] directive-like-text skipped` WARNING log marker when the skip happens, so operators can audit false negatives. Or narrow the skip pattern to only match `[SYSTEM_` at position 0 after stripping.

---

**INFO** | **Lines 283–298** — Story preservation idempotency is sound

The dedupe check via `(narrator_id, turn_id)` is correct. Missing `turn_id` (None) is handled safely — the accessor `story_candidate_get_by_turn` will return None, and a fresh insert happens. The pattern follows standard idempotent INSERT design. No issue.

---

**RED** | **Lines 324–338** — Archive append missing narration role check

The memory archive block at L324–338 appends a `role="user"` event unconditionally. This is correct. However, there is a silent gap: if `person_id` is present but the `ensure_interview_session` call fails, the event still gets archived with no session parent row. The accessor `ensure_interview_session` is idempotent (INSERT OR IGNORE), but if it fails (e.g., permission error, disk full), the archive will have an orphaned row that the interviewer UI may not display correctly. **Consequence:** live chat turns could disappear from the chronology view if the session initialization fails silently. **Suggested fix:** wrap the archive block in try/except, log the failure as WARNING (not critical, since archive is operator-side), and continue the chat turn. The turn must proceed even if archival fails (LAW 3 requirement).

---

### File: server/code/api/safety.py

**INFO** | **Full file reviewed; no issues found**

The safety scanner (`scan_answer()`) is deterministic, with 50+ pattern regexes and a 0.70 confidence threshold. The 7-category taxonomy (suicidal_ideation, ideation, distress_call, abuse_tiers, reflective, cognitive_distress, distressed) is correct. No silent-failure modes detected. The soft-mode helpers and resource-card routing are sound. Patterns correctly avoid over-triggering on neutral language.

---

### File: server/code/api/prompt_composer.py

**AMBER** | **Lines 108–193 (ACUTE SAFETY RULE block)** — Hardcoded resource number for SUICIDAL_IDEATION

The ACUTE SAFETY RULE correctly routes `suicidal_ideation` triggers to the 988 Suicide & Crisis Lifeline template. However, the 2026-04-30 warmth pass changed the 273-TALK reference comment from "OUTDATED" to "continues to function" — good decision. **Issue found:** the template at lines ~140–150 hardcodes the phone number as `1-800-988-5656` without line-break formatting in some places. If a narrator with visual impairment is reading this back (via TTS or screen reader), the number may run together with surrounding text. **Likelihood:** low if the narrator is using TTS (punctuation helps). **Consequence:** harder to read the phone number correctly. **Suggested fix:** ensure phone numbers in narrator-facing output are surrounded by sentence boundaries (periods or line breaks) so screen readers pause.

---

**INFO** | **Lines 1736–1800 (WO-10C Cognitive Support Mode)** — Safe mode framing correct

The CSM directive correctly avoids clinical language and uses "benefits from extra pacing support" instead of "dementia-safe". The 120s/300s/600s silence tiers are appropriate. The code-comment "dementia-safe" is internal (not leaked to narrator). No issue.

---

### File: server/code/api/services/story_preservation.py

**INFO** | **Full file reviewed; isolated correctly per LAW 3**

The preservation module imports zero extraction/LLM/prompt modules and ships behind `HORNELORE_STORY_CAPTURE=0` default-off gate. The `preserve_turn()` function is deterministic and safe. Schema validation (narrator_id FK, turn_id uniqueness) is correct. Idempotency via `get_by_turn` is sound. No silent-failure modes.

---

### File: server/code/api/services/story_trigger.py

**AMBER** | **Lines 155–146 (relative-time pattern addition)** — "because of the war" pattern has overfiring risk

The 2026-04-30 polish added `because of the war` / `due to the war` / `since the war` patterns to catch elder-narrator historical anchoring. The regex at line 145 is:

```python
re.compile(r"\b(?:because|due to|since) (?:of )?(?:the |that |my )?(?:war|depression|drought|flu|epidemic)\b", re.IGNORECASE)
```

**Issue:** "since the war" could match the opening of a sentence like "Since the war ended decades ago, I rarely think about it" which is a reflection, not a scene anchor. The pattern does not require a time or place context before it. **Likelihood:** low — the pattern is still narrow and requires the specific phrase. **Consequence:** borderline_scene_anchor could trigger on generic historical reflection instead of actual story moments. **Suggested fix:** narrow the pattern to require a preceding time anchor or prepend a "once" / "long ago" / "back when" context, OR document that this is intentionally loose and operators can tune via `STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT`.

---

### File: server/code/api/db.py

**AMBER** | **Line 76** — _now_iso() uses utcnow() (deprecated in Python 3.12+)

The helper at line 76 uses `datetime.utcnow().isoformat()`. Python 3.12 deprecates this in favor of `datetime.now(timezone.utc)`. **Consequence:** future versions may raise warnings or errors. **Likelihood:** low in near term. **Suggested fix:** change to `datetime.now(timezone.utc).isoformat()` (this fix was already applied to some parts of the codebase per CLAUDE.md 2026-04-30). The db.py version was missed.

---

**INFO** | **Line 71 (PRAGMA busy_timeout=5000)** — Correct and load-bearing

The 5000ms busy_timeout correctly fixes the "database is locked" race condition during safety-trigger serialization (documented in CLAUDE.md 2026-04-29). This is a critical fix and should NOT be lowered.

---

**INFO** | **Story_candidate accessors (lines 4806–5056)** — Sound design

The `story_candidate_insert()`, `story_candidate_get_by_turn()`, and `story_candidate_get()` accessors all use parameterized queries and defensive row_factory mapping. The idempotency pattern is correct. The schema-drift guard at init_db() (Patch B per CLAUDE.md) is in place. No issues.

---

### File: server/code/api/routers/extract.py

**INFO** | **Lines 7129–7187 (BUG-EX-PLACE-LASTNAME-01 guard)** — Correct integration

The place-as-lastname guard (`_PLACE_GUARDED_FIELD_SUFFIXES` and `_drop_place_as_lastname()`) correctly drops candidate values when they appear only after place prepositions. The word-boundary regex is correct. The guard fires BEFORE `_apply_transcript_safety_layer` so it short-circuits before Phase G protected-identity checks. Good placement. No issues.

---

**INFO** | **Lines 7493–7548 (value-coerce wrapper)** — Defensive but check for silent drops

The value-coerce logic correctly defends against LLM returning non-string types (bool, int, list, dict). The coercions are sensible (bool → "yes"/"no", list → comma-joined, dict → JSON). The try/except wraps the coercion AND the ExtractedItem construction, so a bad coercion doesn't kill the whole response. However, the logging at L7493 when `None` value is dropped does NOT log the fieldPath. **Consequence:** operators cannot see which field had a None value dropped. **Suggested fix:** change the log at L7493 to include fieldPath in the message: `logger.info("[extract][value-coerce] dropping item with None value: fieldPath=%s", item.get("fieldPath", "?"))`.

---

### File: ui/js/projection-sync.js

**INFO** | **Lines 91–127 (BUG-312 protected-identity gate)** — Correct and comprehensive

The Phase G protected-identity gate correctly checks `_isTrustedSource(source)` and routes untrusted writes to `suggest_only` mode. The gate applies to ALL writes (first-write or overwrite), not just overwrites. The audit log is informative. Good defensive posture. No issues.

---

**INFO** | **Lines 180–182 (_isTrustedSource)** — Safe list is correct

Only "human_edit" / "preload" / "profile_hydrate" are trusted. "interview" is correctly untrusted. Good.

---

### File: ui/js/bio-builder-core.js

**AMBER** | **Lines 847, 946–949 (Reset Identity)** — Silent fallback if clearProjection is missing

The Reset Identity UI calls `LorevoxProjectionSync.clearProjection(pid)` (L847) and again at L946 inside a `typeof LorevoxProjectionSync !== "undefined"` check. The check is safe, but there is no logging when the check FAILS (projection-sync is not loaded). **Consequence:** a narrator could press "Reset Identity" and the UI would appear to complete, but localStorage projections could survive if the module failed to load. **Suggested fix:** add an explicit console.error when projection-sync is missing so developers know reset is incomplete.

---

**AMBER** | **Lines 1172–1175 (comment reference to reset bug)** — Comment hints at known incomplete-reset risk

Line 1175 mentions "survived a Reset Identity for exactly this reason" — a comment referencing BUG-286 or similar. This suggests incomplete resets have been a problem before. **Consequence:** there may be other state caches that were not cleared. **Suggested fix:** audit the full Reset Identity path (state.js, localStorage keys, memory_echo cache, projection state, bio-builder state) to ensure the four design principles are met. Reference the CLAUDE.md principle: "No partial resets. Reset Identity clears all narrator-scoped state in one operation, atomically."

---

### File: ui/js/session-loop.js

**INFO** | **Lines 165–170 (SYSTEM_QF suppression in questionnaire_first lane)** — Correct

The logic correctly suppresses the next-field `[SYSTEM_QF: ...]` directive when a story is being told (to not interrupt the narrator). Good design. No issues.

---

**INFO** | **Lines 328–361 (BUG-227 identity rescue)** — Defensive and well-scoped

The identity-rescue directive correctly routes a manually-typed narrator response (e.g., the narrator correcting their own name) back through the interview extraction path. The guard at L361 prevents the rescue from firing twice on the same turn. No issues.

---

---

## Part C — Open Sweep

### TODO / FIXME / HACK / XXX Comments
**No matches found** in `server/code/api/`. (Good code hygiene.)

---

### Print Statements in Production Code
**Found but acceptable:**
- `server/code/api/api.py` (lines 154, 177, 185, 262, 299, 326, 346, 354, 400, 414, 461, 471, 474) — Diagnostic LLM/VRAM prints. These are intentional and serve operator visibility during startup/warmup. Acceptable.
- `server/code/api/routers/tts.py` (L30) — "[TTS] warmed" diagnostic. Acceptable for TTS service status.
- `server/code/api/routers/stt.py` (lines 43, 64, 69, 77, 82) — STT diagnostics. Acceptable.

No problematic `print()` statements found (i.e., ones that should be `logger.warning()`).

---

### Hardcoded Network Addresses
**Found but safe:**
- `server/code/api/routers/operator_harness.py` — uses `os.getenv("HORNELORE_INTERNAL_WS_HOST", "localhost")`. Correct: env-configurable, default is safe for local dev.
- `server/code/api/services/stack_monitor.py` — uses `os.getenv("HOST", "127.0.0.1")`. Correct: env-configurable.

No hardcoded production IPs. No secrets in URLs.

---

### Dead Imports

**Checked:** All imports in chat_ws.py, extract.py, safety.py, db.py, story_preservation.py, story_trigger.py.

**Result:** No unused imports found. All imports are used.

---

### Dead Code (Functions Defined but Never Called)

**Checked:** All functions in routers/ (chat_ws.py, extract.py, interview.py, etc.).

**Result:** No dead functions found. All router handlers are exposed via FastAPI decorators or called transitively.

---

### Race Conditions on Narrator Switch

**Reviewed:** chat_ws.py L199 (`person_id` from params), projection-sync.js L52–54 (state access).

**Finding:** The `active_person_id` at chat_ws.py L130 is per-connection. If a narrator switches without closing the WebSocket, the new `person_id` in params at L199 is used for that turn. The archive and story preservation use this fresh `person_id` on every turn, so there is no stale-cache risk. **No race condition found.**

However, there is a subtle issue in projection-sync.js: if the narrator switches mid-session and the UI doesn't clear localStorage properly, the old narrator's projection could leak into the new narrator's state. This is covered by the BUG-312 protected-identity gate (untrusted sources cannot overwrite), but it's worth noting in the Reset Identity audit above.

---

### Safety Hook Silent-Failure Coverage

**Reviewed:** chat_ws.py lines 408–543 (safety scan block).

**Finding:** The safety hook is well-defended:
- L420–425: `scan_answer()` failures caught, logged, flagged as `_safety_scan_failed`, force `turn_mode="interview"`.
- L438–443: Default-safe fallback explicit.
- L445–543: Trigger-fired cascade is wrapped in try/except for each step (segment flag, softened mode, UI event, operator notify).

**No silent failures detected.** Even if individual persistence steps fail (segment flag, softened mode, operator notify), the chat turn continues and the LLM safety rule still fires.

---

### Archive Orphan Risk (Identified above as RED)

**Issue:** If `ensure_interview_session()` fails at L377 but succeeds later at L464 during safety trigger, the archive at L332 may have an orphaned event.

**Suggested fix:** move the archive block AFTER the safety scan, OR wrap archive in try/except.

---

### STT/Elderly Narrator Edge Cases

**Reviewed:** story_trigger.py place/time/person detection, chat_ws.py token-cap enforcement.

**Finding:** The place regex (lines 106–123) uses word boundaries `\b`, so partial matches like "plantain" won't match "plant". Good. The relative-time patterns require bigrams/trigrams, so single words like "remember" don't fire. Good.

**However:** lowercase place names (e.g., STT producing "spokane" instead of "Spokane") are handled by the `re.IGNORECASE` flag, so that's covered.

**No edge cases found** that would break with elderly narrator's natural speech patterns.

---

### Softened-Mode Composer Thread (Phase 2 blocker)

**Reviewed:** chat_ws.py lines 636–654 (softened state thread into runtime71).

**Finding:** The code defensively copies `runtime71` before modifying it (L647: `dict(runtime71) if isinstance(...)`). Good. The softened state is only applied if `interview_softened=True`, so false positives from empty turns won't trigger softened mode in the composer. Actually sound.

**No issue found.**

---

---

## Summary

**Total Findings:** 7 AMBER, 1 RED, 11 INFO

**Critical Path Coverage:** Chat turn from message arrival (WebSocket) through safety scan, memory archive, story preservation, and composer dispatch is well-defended. No silent-failure modes that would harm a narrator session.

**Parent-Session Readiness:** Code is safe for live use with Kent and Janice. The RED finding (archive orphan risk) should be addressed before sessions begin, but the impact is operator-side only (missing turns from the chronology log).

**Recommendations Before First Session:**
1. (RED) Wrap memory archive in try/except.
2. (AMBER) Investigate and document the Reset Identity completeness audit (BUG-286 reference).
3. (AMBER) Optional: add diagnostic log marker when story trigger skips system directives.

**Design Principles Check:**
- ✅ No dual metaphors — Life Map + one unified 3-column interview view only.
- ✅ No operator leakage — safety UI, bug panel, and operator notify surfaces are all gated or operator-only.
- ✅ No system-tone outputs — all narrator-facing text is warm and human-voiced.
- ⚠️ No partial resets — code is correct, but needs audit per comment at bio-builder-core.js L1175.

---

**End of Report**
