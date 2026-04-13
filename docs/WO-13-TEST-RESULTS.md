# WO-13 Test Results — Corky Desktop

**Date:** 2026-04-12  
**Machine:** Corky (RTX 5080 Blackwell desktop)  
**Tester:** Claude (automated via Chrome)  
**DB Source:** Laptop transfer bundle (lorevox.sqlite3)

---

## Summary

**7 of 8 tests PASS. 1 PARTIAL PASS.**

The Hornelore stack on Corky is stable. All core flows — narrator switching, profile rendering, resume gate, trainer isolation, legacy freeze, backfill idempotency, and review UI — work correctly with the transferred laptop database.

The one partial result (Test 6) reflects a known gap: the chat extraction pipeline extracts facts and projects them into the bio builder, but does not create `source_kind=chat` shadow notes or `needs_verify` proposal rows in the family-truth tables. This means the extraction works but doesn't feed the review queue.

---

## Test Results

### Test 1 — V2 Profile Read Seam: PASS

All three Horne narrators render correctly from promoted truth:

| Narrator | fullName | DOB | POB | Source |
|---|---|---|---|---|
| Kent | Kent James Horne | 1939-12-24 | Stanley, North Dakota | promoted_truth |
| Janice | Janice Josephine Horne | 1939-08-30 | Spokane, Washington | promoted_truth |
| Christopher | Christopher Todd Horne | 1962-12-24 | Williston, North Dakota | promoted_truth |

Janice DOB confirmed corrected to August 30 (not September 30).

### Test 2 — WO-13 Resume Gate: PASS

All three narrators correctly suppressed resume prompts:

- Kent: `[WO-13] priorUserTurns for 4aa0cc2b = 0` — both paths suppressed
- Janice: `[WO-13] priorUserTurns for 93479171 = 0` — both paths suppressed
- Christopher: `[WO-13] priorUserTurns for a4b2f07a = 0` — both paths suppressed

No "welcome back" system prompts fired. Chat area clean.

### Test 3 — Trainer Narrators: PASS

- Shatner Trainer: loaded, header showed "ST / Shatner Trainer / Short, clear, anchored answers"
- Dolly Trainer: loaded, header showed "DT / Dolly Trainer / Warm, storytelling answers"
- Trainer buttons correctly labeled "Run" (not "Add") — known issue #1 from handoff doc is resolved
- WO-11 trainer isolation working: narrator suspended, trainer started, console logs clean

### Test 4 — Cross-Narrator Switching: PASS

Full switching cycle completed: Kent → Janice → Shatner → Chris → Dolly → Kent

- Each switch showed correct narrator data
- No stale name/DOB/POB from previous narrator
- No "loading..." stuck states
- Zero console errors across entire sequence
- Narrator card updated within ~3s each switch

### Test 5 — Legacy Facts Freeze: PASS

```
POST /api/facts/add → 410 Gone
{"detail":"facts.add is retired under HORNELORE_TRUTH_V2. Use POST /api/family-truth/note followed by POST /api/family-truth/note/{note_id}/propose instead."}
```

V2 truth pipeline feature flag active and enforced.

### Test 6 — Chat Extraction → Shadow Archive: PARTIAL PASS

Chat message sent as Christopher: "I grew up in Williston and my dad worked at the oil refinery there. My son Vincent was born in 1990."

Lori responded contextually. Extraction pipeline ran:

- `[extract][queue] deferred free-form extraction queued` — triggered
- `[facts] extracted 3 fact(s) from turn` — facts extracted
- `[extract] Backend returned 2 items via llm` — LLM extraction ran
- `[projection-sync] ⛔ Protected identity conflict: personal.placeOfBirth` — POB correctly blocked
- `[extract] ✓ Projected: parents[2].occupation = worked at the oil refinery` — new fact projected

**What works:** Extraction triggers, facts extracted, LLM extraction runs, protected fields blocked, new facts projected into bio builder.

**What's missing:** No `source_kind=chat` notes created in `family_truth_notes`. No `needs_verify` or `source_only` proposal rows created in `family_truth_rows`. The extraction goes directly to facts + projection, bypassing the shadow archive pipeline. This means extracted facts don't appear in the Review Queue.

**Impact:** Low for current use. Facts still get captured. But the review/approval workflow for chat-extracted content is not functional until the extraction pipeline is wired to write shadow notes.

### Test 7 — Review Drawer: PASS

Review Queue drawer opens correctly. All filter tabs present and functional: All, Needs verify, Approve, Approve + question, Source only, Reject. Action buttons present: Bulk dismiss visible, Promote approved, Refresh.

Queue correctly shows 0 rows because all existing rows are already approved/promoted and no new proposal rows were created from chat.

### Test 8 — Backfill Idempotency: PASS

```
POST /api/family-truth/backfill (Kent)
→ 200 OK
→ {"ok":true, "created_rows":0, "skipped_existing":5, "skipped_empty":0, "reference_refused":false}
```

All 5 identity fields already exist. No duplicates created.

---

## Known Issues Observed

1. **bb-drift KEY MISMATCH warnings** — Console shows `[bb-drift] KEY MISMATCH after 'restore_backend'` on every narrator switch. Memory keys (additionalNotes, children, etc.) don't match disk keys (empty). Not a blocker but indicates the questionnaire backend storage may not be fully synced.

2. **Chat extraction doesn't write shadow notes** — As documented in Test 6. The extraction pipeline projects facts directly to the bio builder without going through the family-truth notes/rows/review pipeline.

3. **Companion modal intercepts chat input** — Clicking the "Type a message..." input in Life Story mode opens the Companion input modal rather than a direct chat input. The message still gets sent through the correct path, but the UX flow is indirect.

---

## Environment

- Hornelore UI: port 8082
- Hornelore API: port 8000
- WebSocket: connected, stable
- Database: transferred from laptop, all 5 narrators present
- V2 Truth Pipeline: active (both feature flags ON)
- All prior conversation data from laptop preserved
