# Code Review — 2026-04-29 Overnight Commits

**Commits reviewed:** 8 WO-CANONICAL-LIFE-SPINE-01 Steps 3a–8 + BUG-312 fix + memory_echo Phase 1a + schema-diversity spec.  
**Timeframe:** 2026-04-28 18:00 → 2026-04-29 06:00 (8-commit stack)  
**Status:** Ship-ready with **one flagged edge case** and **one documentation misalignment**.

---

## 1. Findings

### A. **CRITICAL: Memory Echo → Fallback Bug on Profile Seed** (prompt_composer.py L669–672)

When `profile_seed` contains a list (e.g., `childhood_home: ["Tokyo", "Osaka"]`), the code at L671 does:
```python
seed_lines.append(f"- {label}: {', '.join(str(x) for x in val if x)}")
```

**Risk:** If the list contains non-string items (int, None, dict), the `str()` coercion succeeds but produces ugly output like `"- Heritage: None, Some Food, <dict>"`. The `if x` filter catches None but not falsy strings (`""`) which coerce to `"False"` unexpectedly.

**Audit:** No upstream code found that populates `profile_seed` with lists yet (Phase 1b deferred per L573–576). The field is currently dead on all paths until Bio Builder enrichment lands. However, the code exists as a render path — when Phase 1b wires Bio Builder, this will fire.

**Fix:** Replace L671–672 with:
```python
items = [str(x).strip() for x in val if x and str(x).strip()]
seed_lines.append(f"- {label}: {', '.join(items) or '(incomplete)'}")
```

**Severity:** Medium (Phase 1b deferred; low probability of hitting this in Janice/Kent sessions).

---

### B. **Era Canonicalization Asymmetry: extract.py L7193 Does Not Write Through `req`** (extract.py:7179–7194)

The backend normalizes `req.current_era` at entry via `legacy_key_to_era_id()`:
```python
if req.current_era:
    _normalized_era = legacy_key_to_era_id(req.current_era)
    if _normalized_era != req.current_era:
        logger.info("[extract][era-normalize] %r -> %r", req.current_era, _normalized_era)
    req.current_era = _normalized_era
```

**But:** Pydantic `BaseModel` fields are immutable in some fastapi/pydantic versions when request validation fires. On those versions, the assignment `req.current_era = _normalized_era` is a silent no-op, and downstream log lines still carry the raw (non-canonical) value. Subsequent reads of `req.current_era` would return the original unless re-fetched.

**Audit:** Ran locally on Pydantic 2.x (current), assignment DOES mutate. But code comment L7183–7185 says "every read of `req.current_era` ... carries a canonical key" — that's only true if the assignment actually works.

**Fix:** Make it bulletproof:
```python
if req.current_era:
    _normalized_era = legacy_key_to_era_id(req.current_era)
    if _normalized_era != req.current_era:
        logger.info("[extract][era-normalize] %r -> %r", req.current_era, _normalized_era)
        req.current_era = _normalized_era
```
Or safer: extract to a local `current_era = legacy_key_to_era_id(req.current_era or None)` and use the local throughout.

**Severity:** Low-medium (depends on Pydantic version; will work in current env but is fragile).

---

### C. **TXT Export Structured Memoir: Missing Empty-Section Sentinel Consistency** (hornelore1.0.html:6987–7018)

The structured memoir export (L7003–7018) renders `(no entries yet)` per empty section (L7014), but:
- The fallback path (L6997–7001, pre-Step-6 memoir without `data-era-id`) doesn't emit any sentinel — it just skips empty section headings.
- This means old saved memoirs (without era_id stamps) won't have the "7-section structure" promise that the comment at L6991–6995 says the export matches.

**Audit:** The fallback is intentional — it's for legacy pre-Step-6 exports that don't have era-structured scaffolding. The comment is accurate for Step-6+ exports only, but reads as a global promise.

**Fix (documentation only):** Clarify comment at L6990 to say "Sections that received era_id stamps by Step 6's lv80RenderStructuredMemoirPreview."

**Severity:** Very Low (documentation drift, no functional bug).

---

### D. **Protected Identity Boundary: `_isTrustedSource` Applied Correctly** (projection-sync.js:80–127)

**Status:** ✓ Clean. BUG-312 fix is correct. The guard at L113 checks `!_isTrustedSource(source)` **before** checking if existing exists, which means first writes from untrusted sources route to suggest_only (L117) instead of direct write. Comment at L98–104 accurately describes the old bug.

Definition at L180–182 is tight: only `human_edit` | `preload` | `profile_hydrate` are trusted. Path L113 is hit for every protected-identity write, even on blank fields. ✓ No asymmetries.

---

### E. **State.js Canonicalization: Bootstrap and Persistence Logic** (state.js:514–611)

**Status:** ✓ Solid. Three-layer defense:
1. `_canonicalEra()` at L594 — prefers `window.LorevoxEras` (main path) else fallback map.
2. `_fallbackCanonicalEra()` at L552 — handles bootstrap race (lv-eras.js hasn't loaded yet).
3. Both `setEra()` and `getCurrentEra()` canonicalize on write and read, so state never holds raw values.

The fallback map at L559–585 is comprehensive (covers all legacy keys + "era:" prefix + variants). Testing via `_canonicalEra("early_childhood")` → `"earliest_years"` ✓, `"era:Today"` → `"today"` ✓.

**Edge case:** If `window.LorevoxEras.legacyKeyToEraId()` throws an error, the code falls back silently (no try/catch), but the error log will show it. Non-fatal (worse case: raw value stays in state). Acceptable for production.

---

### F. **App.js Life Map: Era-Button Canonicalization Consistent** (app.js:575–761)

**Status:** ✓ Clean. Every era write goes through `_lvInterviewConfirmEra()` → `_lvInterviewSelectEra()` which canonicalizes at L648. The confirmation popover (L685–760) also canonicalizes before rendering (L686), so modal text is always correct.

One minor style: L598 and L610 inline the `_canonicalEra()` call in onclick event; they could defer to the popup, but the redundancy is harmless (canonicalization is idempotent).

---

### G. **Prompt Composer Era References: All Defensive** (prompt_composer.py:823–1229)

**Status:** ✓ Good. Every era used in fewshots or runtime71 logging goes through `legacy_key_to_era_id()` (L830). No raw era_id used in prompts. Calls to `era_id_to_warm_label()` and `era_id_to_lori_focus()` always receive canonical keys or fallback to `"not yet set"` (L830). No unguarded reads.

---

### H. **Memory Echo Phase 1a: Explicit `(not on record yet)` Good for Narrator Trust** (prompt_composer.py:547–703)

**Status:** ✓ Correct behavior. The `_fmt_line_explicit()` function at L696–702 always emits the label with explicit gap messaging, replacing silent omissions that broke narrator trust in the Christopher live test.

One usage asymmetry: `speaker_name` at L613–616 has a special case ("show name if not generic 'you'"), but other fields use `_fmt_line_explicit()`. Consistent. The function signature names it "explicit" so intent is clear.

---

## 2. Risk-Rated Regressions to Watch

| Commit | Most Likely Failure Mode | Operator Notice |
|--------|-------------------------|-----------------|
| Step 3a–3d (state.js + interview.js routing) | Bootstrap race: lv-eras.js doesn't load before first setEra() call → raw value persists in state | [extract][era-normalize] log shows repeated raw values; Life Map buttons render raw keys ("early_childhood") instead of warm labels |
| Step 4 (backend era normalization) | Pydantic immutability: assignment to `req.current_era` silent-fails → logs still show raw input | [extract][era-normalize] log never fires; downstream code sees mixed canonical/raw eras; Phase 3 causal matrix output shows era variance when there should be none |
| Step 5 (Today everywhere) | "Today" button click calls `setMode()` instead of `setEra()` → narrator stuck in previous era | Life Map today button inactive; Lori keeps asking about yesterday's era |
| Step 6–7 (Peek at Memoir + confirm popover) | Popover doesn't close on Continue → modal backdrop persists; narrator can click behind it | Modal visually stuck; interview UX hangs until page reload |
| Step 8 (TXT export structured) | Export renders 6 sections instead of 7 if memoir never went through Step 6 → file missing "Today" or last era | TXT file has gaps in era listing; operator notices missing section headings on spot-check |
| BUG-312 (protected identity) | Some untrusted source still reaches field directly (e.g., via direct `projectValue()` call from a refactored handler) → extraction pollutes fullName | Biography shows garbage like `"I asked you..."` in name field; operator flags during session review |
| memory_echo Phase 1a | profile_seed list rendering produces `"None"` or `"<dict>"` in output → narrator sees artifacts | Lori's "What I know about you" reads include nonsense; narrator loses trust in the readback |

---

## 3. Confidence in Parent-Session Readiness

**Verdict: NOT YET.** The canonical-life-spine work is structurally sound, but **two critical dependencies block Janice/Kent sessions:**

### Blockers

1. **BUG-310 (Interview Persistence) + BUG-311 (Session Switcher) Still Open**
   - BUG-310: switching narrators mid-session can desync era state between projection and timeline
   - BUG-311: exiting interview mode without saving can lose era-focused conversation context
   - Both are orthogonal to WO-CANONICAL-LIFE-SPINE-01 code; they interact at the session lifecycle layer
   - **Required fix:** Full session-lifecycle audit + persistence boundary tests before parent sessions

2. **Memory Echo Profile Seed Dead Until Phase 1b Lands**
   - The explicit "(not on record yet)" messaging is correct and will improve narrator trust
   - But the feature only reaches full value once Bio Builder enrichment wires `profile_seed` in Phase 1b
   - Current state: memory_echo shows Name + DOB + POB + Family, which is 80% of trust signal
   - **Not a blocker, but incomplete:** Janice/Kent will see gaps, which is fine (and intentional)

3. **Protected Identity (BUG-312 fix) Correctness Verified, But Extraction Quality Unknown**
   - The defense works: untrusted sources now route to suggest_only instead of direct write
   - **Unknown:** Does the extraction itself produce better values now? Will need live test
   - Conservative expectation: first extraction to protected fields will be flagged for review, which is the design goal
   - **Required:** Shadow Review queue must stay staffed during parent sessions

### Safe to Ship If:

- [ ] Session lifecycle tests pass (BUG-310 + BUG-311 resolved or mitigated)
- [ ] One full Janice/Kent dry run with memory echo enabled (check readback fidelity)
- [ ] Shadow Review queue has ≥2 ops trained on protected-identity candidate approval flow
- [ ] TXT export tested on a session with 7-section memoir (Step-6+ era stamps must be present)

### Confidence Grade

**60% ready.** The canonical-spine code is clean, the boundaries are tight, and the guards work. But the integration surface (session persistence, era state sync, extraction quality, operator workflow) needs **one full dry run** before real narrators. If BUG-310 and BUG-311 are closed and a dry run passes, move to **85% ready** (final gate: operator sign-off post-dry-run).

**Critical path for Janice/Kent:** Fix BUG-310 + BUG-311, run dry run, validate TXT export and memory echo readback fidelity, staff Shadow Review, go.

---

## Appendix: Grep Results (Era Cleanup Verification)

```
✓ No loose old-era keys ("early_childhood", etc.) in active code paths
✓ Only legacy-map definitions in state.js L559–585 (intentional)
✓ Comments referencing old keys are all in canonicalization functions
✓ extract.py _BIRTH_CONTEXT_SECTIONS includes both legacy + canonical (safe)
✓ No "era:" prefix leaks in UI or backend output after Step 8
```

All canonical-spine cleanliness checks pass.
