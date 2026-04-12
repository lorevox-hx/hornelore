# WO-13 Testing & Handoff Plan

**Date:** April 12, 2026
**Status:** Phase A (Kent Dry Run) complete. Phase 9 validation in progress.
**Operator:** Chris Horne (dev@lorevox.com)

---

## What Was Done Tonight

### 1. Auto-Resume Gate (Bug Fix)
**Problem:** Every narrator switch fired a "welcome back" system prompt, even for narrators who had never been spoken to. This created 6+ fake turns in the DB every time you switched narrators.

**Fix:** Added `user_turn_count` to the `/api/narrator/state-snapshot` endpoint. The UI now checks this count during Phase G hydration and suppresses both resume-prompt paths (legacy `lv80SwitchPerson` at `hornelore1.0.html:3662` and WO-8 `wo8OnNarratorReady` at `app.js:4560`) when count is 0. Operator-initiated resume (`wo10UseResume`) is deliberately NOT gated.

**Files changed:** `db.py`, `narrator_state.py`, `hornelore1.0.html`, `app.js`

### 2. Trainer Narrators Preloaded
Shatner (structured) and Dolly (storyteller) loaded into the DB via `scripts/preload_trainer.py` using Playwright to call `lv80PreloadNarrator()` headlessly. Both have full profiles (basics, kinship, pets) and questionnaires. They are NOT marked as `narrator_type='reference'` in the DB yet — that's a TODO.

**Files created:** `scripts/preload_trainer.py`, `scripts/requirements.txt`

### 3. V2 Truth Pipeline Live
Both feature flags turned ON in `.env`:
- `HORNELORE_TRUTH_V2=1` — freezes legacy `/api/facts/add` (returns 410 Gone)
- `HORNELORE_TRUTH_V2_PROFILE=1` — profile endpoint reads from `family_truth_promoted`

All 3 Hornes backfilled (5 protected identity fields each), approved, and promoted. All report `source: promoted_truth` on profile GET.

### 4. Janice DOB Corrected
Changed from 1939-09-30 to 1939-08-30 across all 6 locations: hornelore template, lorevox template, people table, profile_json, truth row, promoted truth.

---

## Current DB State

```
people:     5  (Kent, Janice, Christopher, Shatner, Dolly)
profiles:   5
turns:      0
sessions:   1  (empty shell from Playwright preload — harmless)
facts:      0
family_truth_notes:     15  (5 per Horne from backfill)
family_truth_rows:      15  (5 per Horne, all status=approve)
family_truth_promoted:  15  (5 per Horne)
```

---

## Testing Checklist

### Test 1 — V2 Profile Read Seam

**Goal:** Verify profiles render correctly from promoted truth.

| Step | Expected | Pass? |
|---|---|---|
| Switch to Kent in UI | Profile shows: Kent James Horne, DOB 1939-12-24, POB Stanley ND | |
| Switch to Janice | Profile shows: DOB **1939-08-30** (August not September), POB Spokane WA | |
| Switch to Christopher | Profile shows: DOB 1962-12-24, POB Williston ND, preferred "Chris" | |
| Each narrator: kinship list visible | Parents, siblings, spouse, children display | |
| Each narrator: pets visible | Pet entries display | |

**API verification:**
```bash
# Should all return source: promoted_truth
curl -s http://127.0.0.1:8000/api/profiles/4aa0cc2b-1f27-433a-9152-203bb1f69a55 | python3 -m json.tool | grep source
curl -s http://127.0.0.1:8000/api/profiles/93479171-0b97-4072-bcf0-d44c7f9078ba | python3 -m json.tool | grep source
curl -s http://127.0.0.1:8000/api/profiles/a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2 | python3 -m json.tool | grep source
```

### Test 2 — WO-13 Resume Gate

**Goal:** Confirm no resume prompts fire for fresh narrators (0 prior user turns).

| Step | Expected | Pass? |
|---|---|---|
| Open browser console (F12) | | |
| Switch to Kent | Console shows `[WO-13] suppressing resume prompt — no prior user turns` | |
| Switch to Janice | Same suppression message | |
| Switch to Christopher | Same suppression message | |
| NO `[SYSTEM: You are resuming...]` in chat | Chat area stays clean, no AI "welcome back" | |
| Turns table stays at 0 after switching | `SELECT COUNT(*) FROM turns` = 0 | |

### Test 3 — Trainer Narrators

**Goal:** Verify Shatner and Dolly load without errors.

| Step | Expected | Pass? |
|---|---|---|
| Switch to Shatner | Loads, profile shows William Alan Shatner, DOB 1931-03-22 | |
| Switch to Dolly | Loads, profile shows Dolly Rebecca Parton, DOB 1946-01-19 | |
| No resume prompt for either | Console shows WO-13 suppression | |
| Note trainer button labels | Should say "Run" not "Add" (known open issue) | |
| Click trainer button twice | Should NOT create duplicate (known open issue) | |

### Test 4 — Cross-Narrator Switching

**Goal:** No stale data, no stuck states, no console errors.

| Step | Expected | Pass? |
|---|---|---|
| Kent → Janice → Shatner → Chris → Dolly → Kent | Each switch shows correct narrator data | |
| No "loading..." stuck state | Narrator card updates within ~3s | |
| Console: no red errors | Only green/info WO-13 messages | |
| No stale name/DOB from previous narrator | Each profile is fully distinct | |

### Test 5 — Legacy Facts Freeze

**Goal:** Confirm `/api/facts/add` is frozen.

```bash
curl -s -X POST http://127.0.0.1:8000/api/facts/add \
  -H "Content-Type: application/json" \
  -d '{"person_id":"4aa0cc2b-1f27-433a-9152-203bb1f69a55","text":"test"}' \
  | python3 -m json.tool
```

| Expected | Pass? |
|---|---|
| Returns 410 Gone with message about using family-truth pipeline | |

### Test 6 — Chat Extraction → Shadow Archive

**Goal:** Verify that chatting creates shadow notes and proposal rows automatically.

| Step | Expected | Pass? |
|---|---|---|
| Switch to Christopher (use Chris, keep Kent clean) | | |
| Chat: mention a place ("I grew up in Williston") | | |
| Chat: mention a job ("I worked at the refinery") | | |
| Chat: mention a family member ("my son Vincent") | | |
| End chat after 3-4 turns | | |

**Then verify:**
```bash
# Shadow notes created (one per turn with extractable content)
curl -s "http://127.0.0.1:8000/api/family-truth/notes?person_id=a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2" | python3 -m json.tool

# Proposal rows derived (needs_verify or source_only)
curl -s "http://127.0.0.1:8000/api/family-truth/rows?person_id=a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2&status=needs_verify,source_only" | python3 -m json.tool
```

| Expected | Pass? |
|---|---|
| At least 1 shadow note with source_kind="chat" | |
| At least 1 proposal row with extraction_method="rules_fallback" | |
| Protected identity fields (DOB, POB, fullName) land as source_only, not needs_verify | |

### Test 7 — Review Drawer

**Goal:** Verify the review UI works for approving/rejecting rows from chat.

| Step | Expected | Pass? |
|---|---|---|
| Open Review Drawer in UI (after Test 6) | | |
| See needs_verify rows from chat | Rows display with field, source_says, confidence | |
| Change a row to "approve" | Row moves to Approve tab | |
| Change a row to "reject" | Row moves to Reject tab | |
| Click "Promote approved" | Promoted rows appear in promoted truth | |

### Test 8 — Backfill Idempotency

**Goal:** Confirm re-running backfill doesn't create duplicates.

```bash
curl -s -X POST http://127.0.0.1:8000/api/family-truth/backfill \
  -H "Content-Type: application/json" \
  -d '{"person_id":"4aa0cc2b-1f27-433a-9152-203bb1f69a55"}' \
  | python3 -m json.tool
```

| Expected | Pass? |
|---|---|
| `created_rows: 0, skipped_existing: 5` (all 5 already exist) | |

---

## Known Open Issues

1. **Trainer seed buttons mislabeled** — Say "Add Shatner/Dolly Trainer" instead of "Run Shatner/Dolly Trainer"
2. **Duplicate trainers on repeated clicks** — `lv80SeedTrainerNarrator()` doesn't check if trainer already exists
3. **Hardcoded examples in `_steps()`** — Shows "Christopher Todd Horne" and "Bismarck, North Dakota" regardless of active narrator
4. **Trainer state contamination** — Trainer state could bleed into real narrator sessions without hard-reset boundary
5. **Shatner/Dolly not marked as reference** — `narrator_type` is still default "live", not "reference". Should be set so the write guard works: `UPDATE people SET narrator_type='reference' WHERE display_name IN ('William Alan Shatner','Dolly Rebecca Parton')`
6. **Operator Bug Panel** — Planned but not implemented: header panel with Mic/Camera status and error surfacing
7. **birthOrder raw numeric** — Backfill stores "2" not "Second child". UI normalization may or may not handle this.

---

## Shadow Archive Quick Reference

### Viewing Notes (Raw Shadow Archive)
```bash
# All notes for a narrator
curl -s "http://127.0.0.1:8000/api/family-truth/notes?person_id=PID" | python3 -m json.tool

# Note fields: id, person_id, body, source_kind, source_ref, created_at, created_by
# source_kind values: chat, questionnaire, import, manual, extraction
```

### Viewing Proposal Rows
```bash
# All rows (any status)
curl -s "http://127.0.0.1:8000/api/family-truth/rows?person_id=PID" | python3 -m json.tool

# Filter by status
curl -s "http://127.0.0.1:8000/api/family-truth/rows?person_id=PID&status=needs_verify" | python3 -m json.tool

# Filter by field
curl -s "http://127.0.0.1:8000/api/family-truth/rows?person_id=PID&field=personal.dateOfBirth" | python3 -m json.tool
```

### Reviewing a Row
```bash
# Approve
curl -s -X PATCH "http://127.0.0.1:8000/api/family-truth/row/ROW_ID" \
  -H "Content-Type: application/json" \
  -d '{"status":"approve","approved_value":"the verified value","reviewer":"chris"}'

# Reject
curl -s -X PATCH "http://127.0.0.1:8000/api/family-truth/row/ROW_ID" \
  -H "Content-Type: application/json" \
  -d '{"status":"reject","reviewer":"chris"}'
```

### Promoting Approved Rows
```bash
# Bulk promote all approved rows for a narrator
curl -s -X POST http://127.0.0.1:8000/api/family-truth/promote \
  -H "Content-Type: application/json" \
  -d '{"person_id":"PID","reviewer":"chris"}'
```

### Viewing Promoted Truth
```bash
curl -s "http://127.0.0.1:8000/api/family-truth/promoted?person_id=PID" | python3 -m json.tool
```

### Audit Trail
```bash
# Full provenance for any row
curl -s "http://127.0.0.1:8000/api/family-truth/audit/ROW_ID" | python3 -m json.tool
```

---

## Person IDs (Reference)

| Narrator | person_id |
|---|---|
| Kent James Horne | `4aa0cc2b-1f27-433a-9152-203bb1f69a55` |
| Janice Josephine Horne | `93479171-0b97-4072-bcf0-d44c7f9078ba` |
| Christopher Todd Horne | `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2` |
| William Alan Shatner | `06b918b2-8c5f-4dd9-9c90-f7ef78af4aeb` |
| Dolly Rebecca Parton | `e2e2575b-a88a-4f04-82c9-51d26dde713c` |

---

## Next Steps (After Testing)

1. Complete all 8 test scenarios above
2. Fix known open issues (priority: #5 reference narrator marking, #2 duplicate trainers)
3. Write `OPERATOR_RUNBOOK.md` documenting the full operator workflow from observed reality
4. Stage 2: Write `scripts/preload_truth_from_template.py` for broader field coverage beyond the 5 protected identity fields
5. Consider extending `_PROMOTED_TO_BASICS` mapping to include pronouns, culture, zodiacSign, etc.
