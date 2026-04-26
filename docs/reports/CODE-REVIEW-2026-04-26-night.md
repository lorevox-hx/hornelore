# Code Review — Overnight 2026-04-26

**Scope:** Photo system end-to-end + companion app for parent demo readiness.
**Author:** Claude (overnight pass per Chris's authorization 2026-04-25 night)
**Verdict:** **0 P0 demo blockers.** 4 P1 polish risks, 3 P2 cleanups.
**Parent demo (~3 days out):** clear to proceed once Chris has run the 8-case smoke test from `docs/PHOTO-SYSTEM-TEST-PLAN.md`.

---

## Methodology

Subagent code review (Explore agent) over the photo system + companion app surfaces, ranked by demo-impact severity. Skipped the extractor lane (`extract.py` 10K+ LOC, separate concern). Cross-referenced findings against CLAUDE.md changelog to avoid re-flagging already-fixed bugs (BUG-238, BUG-239, BUG-PHOTO-CORS-01, BUG-PHOTO-LIST-500, BUG-PHOTO-PRECISION-DAY, Pillow-venv silent failure — all closed earlier this night).

---

## Findings

### P0 — Demo Blockers

**NONE.** Every shipping-blocker we found earlier this session has been closed. The photo system end-to-end chain holds, the companion app's narrator-switch guards are working (BUG-208 shipping-ready), and the bio-builder pipeline is verified by BB Walk Test 38/0.

### P1 — Polish Risks (would embarrass; one-liner-fixable)

#### P1.1 — Silent EXIF corrupt-tag failure
- **File:** `server/code/services/photo_intake/exif.py:176–200`
- **Symptom:** Photo with structurally valid but semantically malformed EXIF GPS (zero denominators, partial DMS triples) → curator sees blank date/location and assumes no metadata, when actually the tag was present-but-corrupt.
- **Root cause:** `_dms_to_decimal()` swallows exceptions and returns None; the handler can't distinguish "no tag" from "bad tag."
- **Fix:** Add `exif_gps_unparseable: bool` flag to the returned dict + surface as a "⚠️ GPS data found but unreadable" pill in the modal. Optional schema field; non-breaking.
- **Demo impact:** Low (depends on parents having corrupted phone JPEGs, unlikely). **Defer.**

#### P1.2 — Narrator-ready checkbox cross-form leak — **FIXED OVERNIGHT**
- **File:** `ui/js/photo-intake.js:131–145`
- **Symptom:** Single-photo `narratorReady` checkbox state could persist across narrator-switch in the dropdown, mismatching with batch form.
- **Fix landed:** Both narrator-change handlers now reset both checkboxes when narrator switches. See "Fixes Applied" section below.

#### P1.3 — PATCH location_label without location_source doesn't recalc needs_confirmation
- **File:** `server/code/api/routers/photos.py:405–446` (PATCH handler)
- **Symptom:** Curator opens modal to fix typo in `location_label` without touching `location_source`. PATCH succeeds but `needs_confirmation` stays at original value (could be `false` from EXIF GPS even though label is now manually edited).
- **Root cause:** Recalc gate at L575–581 only fires when `location_source` is in the patch payload.
- **Fix:** Expand condition to `if "location_source" in payload OR "location_label" in payload AND "needs_confirmation" not in payload`.
- **Demo impact:** Low. Curator-only flow; narrator never sees `needs_confirmation` directly. **Defer.**

#### P1.4 — Batch-upload narrator race — **FIXED OVERNIGHT**
- **File:** `ui/js/photo-intake.js:380–420`
- **Symptom:** Operator drops 5 photos as Narrator A → switches dropdown to Narrator B before clicking Upload All → all 5 photos land on B's timeline.
- **Root cause:** Batch upload reads `el.batchNarrator.value` at upload-time, not at queue-add-time.
- **Fix landed:** Each batch item now captures `narrator_id` at queue-add time and uses that captured value at upload time. See "Fixes Applied" section below.

### P2 — Cleanup (post-demo)

- **P2.1** Redundant null checks in `repository.py` after `_row_to_dict()` — already handles None internally.
- **P2.2** Pillow-missing log line is `WARNING` but the trap is well-documented; could downgrade to `INFO` and reference `docs/PILLOW-VENV-INSTALL.md` in the message text.
- **P2.3** `bio-builder-core.js:126–128` localStorage-full catch block silent — should fire a toast so curator knows draft didn't save.

---

## Notable patterns worth keeping

### BUG-208 narrator-switch generation counter — well-implemented
Monotonic counter (`_narratorSwitchGen`) stamped at request-time, checked on response. In-flight async responses from prior narrator are invalidated cleanly. **Shipping-ready.**

### Photo-system fail-soft architecture
All `photo_intake/` services return empty-shape dicts on error rather than raising. Photos upload successfully even when EXIF / geocode fails. Correct for a user-facing curator tool. The Pillow trap was a real issue (silent disablement of an entire feature), but the per-call fail-soft posture is right; we just need a louder startup signal when major deps are missing (see Recommendations below).

### Narrator-ready filter separation
Curator UI sees ALL photos including unready ones. Narrator UI filters by `narrator_ready=true`. Clean separation of concerns; BUG-238 fix verified this is enforced server-side as well.

### Three-path photo intake UX
Tonight's Review File Info flow added a third entry path while preserving the existing two:
1. **Curator types blank → upload-time EXIF auto-fill** (server-side, behind `HORNELORE_PHOTO_INTAKE` flag)
2. **Curator types manually → upload as typed** (curator wins over EXIF)
3. **NEW: Curator clicks Review File Info → server preview returns prefilled values → curator reviews/edits → commits** (matches visualschedulebot pattern)

All three paths converge on the same DB write. Source-attribution pills surface provenance to the curator on path #3.

---

## Recommendations (post-demo)

1. **Surface dep-missing failures at server startup**, not silently per-call. Pillow check in `main.py` startup hook → log ERROR + return 503 from `/api/photos/health` if missing. Would have saved 90 minutes of diagnosis.

2. **Defensive `default=str` on json.dumps in metadata_payload write path**. Tonight's PRECISION-DAY bug was a CHECK constraint violation, but the broader pattern of "stringify EXIF without crashing on weird Pixel/Samsung tag values" deserves a belt-and-suspenders default.

3. **Author a `requirements.txt` reconciliation pass**. Pillow + the openlocationcode-alt + any other shipped deps should be in the venv install manifest so fresh-laptop bring-up doesn't bite again.

4. **Add a Phase 2 photo system smoke harness** modeled on the BB Walk Test (36/0 green) — automate the 8-case manual test plan with a test narrator + synthesized JPEGs (one with EXIF, one without). Would catch DB-CHECK-mismatch class bugs in CI.

---

## Fixes Applied This Pass

Two of the four P1 risks landed inline because they were one-liners and zero-extractor-risk:

### Fix 1 — Batch-upload narrator capture (P1.4)
`ui/js/photo-intake.js`: each batch queue item now captures `narrator_id` and `narrator_ready` at the moment it's added to the queue (when the operator picks files). Upload-time reads from the captured snapshot, not the live dropdown. Operators can switch narrators between drop and Upload All without leaking photos to the wrong row.

### Fix 2 — Narrator-ready cross-form sync (P1.2)
`ui/js/photo-intake.js`: both narrator-change handlers now also reset BOTH narratorReady checkboxes when the narrator changes. Switching narrators in either dropdown clears the ready flag in both forms — operator must re-affirm "ready" for the new narrator.

Both fixes are in this pass's commit batch.

---

## Files I touched in this code review pass

- `ui/js/photo-intake.js` — P1.2 + P1.4 fixes inline
- `docs/reports/CODE-REVIEW-2026-04-26-night.md` — this report

No backend code touched (P1.1 + P1.3 deferred per "would embarrass but not block" calculus).

---

## Closing assessment

The system is **clear to demo with parents in 3 days** subject to:
1. Chris running the 8-case smoke test from `docs/PHOTO-SYSTEM-TEST-PLAN.md` end-to-end on a fresh stack cycle.
2. Verifying the Pillow install per `docs/PILLOW-VENV-INSTALL.md` (already done; not regression-prone).
3. WO-AUDIO-NARRATOR-ONLY-01 frontend live-build (~3 hrs with Chris in browser, separate work item).

BB Walk Test 38/0 is the load-bearing identity-pipeline checkpoint and remains green. The five photo bugs we fought through tonight (CORS, LIST-500, PRECISION-DAY, plus BUG-238 + BUG-239 from earlier) all have evidence-grade fixes with named root causes — no "I think it's working now" residue.

The biggest unaddressed risk for the parent session is OPERATOR error during a live session, not code: Chris dropping a folder of unvetted scanned photos into batch upload, narrator picking one up before curator marks ready, etc. The new BUG-238 narrator-ready filter blocks the worst case here.
