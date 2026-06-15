# WO-ACCORDION-TIMELINE-FORENSIC-01 — Spec

**Status:** READY (review-first, then patch)
**Type:** Forensic + restore + architectural correction
**Date:** 2026-04-27
**Lab/gold posture:** Hornelore-side. The accordion-as-authority-aware-projection model and the Memoir Correction Rule may eventually promote to Lorevox; this WO does NOT touch Lorevox v10.

---

## Goal

Find exactly when Hornelore stopped mounting the Chronology Accordion as a persistent surface and shifted the narrator-room primary UI to Memory River. Then restore the accordion timeline as the **persistent right rail** of the Narrator Room while keeping Peek at Memoir and Life Map. Memory River becomes a deferred experimental panel.

Apply the corrected architectural framing: the timeline is an **authority-aware projection**, not "read-only." It does not write truth itself; it displays the best current life record assembled from intake, Questionnaire First, Bio Builder, promoted truth, photo/document metadata, and approved memoir corrections. Human corrections (including via Peek at Memoir) flow back through the canonical truth path and reappear everywhere.

**Do not patch first.** Do the git archaeology and code review first. Produce evidence. Only then patch.

---

## Forensic finding so far (Phase 2 sandbox recon, 2026-04-27)

The chronology engine is intact. What got lost is the **mount/priority**.

| Surface | Status |
|---|---|
| `server/code/api/routers/chronology_accordion.py` | Present and mounted (`main.py:108, 138`) |
| `ui/js/chronology-accordion.js` | Present and loaded by shell (`hornelore1.0.html:4570`) |
| Backend `/api/chronology-accordion` endpoint | Live |
| Memory River as primary narrator-room tab | Yes (`hornelore1.0.html:3166`) — first in the view-tabs nav |
| Chronology Accordion as a narrator-room surface | No — not in view-tabs, no right rail mount |
| Memory River as separate header popover | Yes (`lv80RiverBtn`, `kawaRiverPopover`) — exists at TWO levels |
| WO origin of displacement | WO-NARRATOR-ROOM-01 commit batch (task list entries 185-189; "Commit 2: view-tab switching + Memory River / Life Map / Photos / Peek") |

**Conclusion:** The narrator-room rebuild promoted Memory River into the primary tab and never restored the accordion as the persistent rail. Engine + route + JS all still work; they just aren't being shown.

---

## Product decisions (locked at top of WO)

```
Accordion Timeline = persistent right-side spine.
                     Visible across all narrator-room views.
Life Map           = helper for shifting active life period.
                     Stays as a primary tab.
Peek at Memoir     = stays as a primary tab.
                     Becomes editable per the Memoir Correction Rule below.
Photos             = stays as a primary tab. Hangs on the timeline.
Documents          = added as a primary tab. Hangs on the timeline.
Memory River/Kawa  = deferred. Hidden behind feature flag OR moved to
                     Operator experimental panel. Code stays in tree but
                     is NOT a primary narrator tab.
Memory Exercise    = do not build or repair. Out of scope.
```

---

## Architectural framing (corrected wording)

The README currently describes the Chronology Accordion as a "read-only timeline sidebar." That framing is too narrow now. The replacement language:

> **The Accordion Timeline is an authority-aware projection of the current life record.** It is read-only in the narrow sense that clicking or expanding it never creates truth directly. But it is **live**: it reflects human intake, Questionnaire First, Bio Builder edits, promoted truth, curated photo/document metadata, and approved memoir corrections. When information is corrected by a human, the correction flows back through the canonical authority path and then reappears everywhere — Timeline, Life Map, Photos/Documents, Lori runtime context, and Peek at Memoir.

**Authority model (locked):**

```
Human-entered intake / Questionnaire First / Bio Builder
    = high-authority structured input

Curated photos and documents
    = source material with human-entered metadata
      (names, dates, places, captions, family lines)

Lori interview turns
    = raw archive + AI candidate proposals
    = NOT automatically truth

Human review / correction
    = promoted truth / canonical correction

Peek at Memoir human edit (NEW)
    = if cosmetic/narrative wording: save as memoir text edit
    = if factual: route to canonical truth path, lock as human-correction
```

---

## Memoir Correction Rule (NEW — to be added to the LICENSE Reserved Rights enumeration after this WO)

Peek at Memoir must support **two modes** of human edit, not one.

**Mode A — narrative wording edit.** Operator/narrator changes prose. No factual claim shifts.
- Save as memoir text edit on the rendered memoir surface only.
- Do not change structured truth.
- Do not propagate to Timeline / Life Map / Bio Builder / runtime context.

**Mode B — factual correction.** Operator/narrator changes a factual field that surfaces in the memoir. The factual fields are:
- `personal.fullName`, `personal.preferredName`
- `personal.dateOfBirth`, `personal.dateOfDeath`
- `personal.placeOfBirth`, `personal.placeOfDeath`
- `parents.{slot}.firstName`, `.lastName`, `.dateOfBirth`, `.dateOfDeath`, `.placeOfBirth`, `.placeOfDeath`
- `siblings.{slot}.firstName`, `.lastName`, `.dateOfBirth`, `.dateOfDeath`, `.placeOfBirth`, `.placeOfDeath`, `.relation`
- `spouse.firstName`, `.lastName`, `.dateOfMarriage`, `.placeOfMarriage`, `.dateOfDeath`
- `children.{slot}.firstName`, `.lastName`, `.dateOfBirth`, `.placeOfBirth`
- `residence.place`, `.dateRange`
- `education.{slot}.school`, `.dateRange`
- `military.branch`, `.servicePeriod`
- `community.role`, `.organization`, `.dateRange`
- Any other promoted-truth field

For Mode B corrections:
1. The edit is captured as a **promoted-truth correction** with `source: "memoir_human_edit"` and `assessor: "human"`.
2. The corrected value lands in `family_truth_promoted` as a human-edit entry, replacing or superseding the previous value with full provenance.
3. The Timeline / Life Map / Photos / Documents / Lori runtime context / Bio Builder all re-render from the corrected value.
4. The protected-identity-field protections in `projection-sync.js` already block AI overwrite of human-edited fields — that lock is honored automatically.
5. The audit trail in the WO-13 truth pipeline carries the memoir-edit provenance.

**Janice DOB worked example.** Janice's profile basics carry `personal.dateOfBirth = 1939-08-30`. If something upstream (intake error, OCR, AI extraction) wrote `1939-09-30` and that value reaches Peek at Memoir, the human reading the memoir corrects it to `1939-08-30`. The correction:
- Lands as a `family_truth_promoted` row with `source: "memoir_human_edit"`, `assessor: "human"`, `field: "personal.dateOfBirth"`, `value: "1939-08-30"`, `superseded: <previous_row_id>`.
- Locks the field via the existing protected-identity model in `projection-sync.js`.
- Re-renders the Timeline (birth anchor moves from 1939-09 to 1939-08).
- Re-renders the Life Map.
- Re-renders Bio Builder.
- Updates Lori runtime context (`speakerDOB` in `buildRuntime71`).
- Reappears in the next Peek at Memoir render at the corrected value.

**Rule (one sentence):** *AI may suggest corrections. Only human confirmation can make them canonical.*

---

## Phase 1 — Git archaeology (laptop-only — sandbox cannot run git)

CLAUDE.md states the sandbox cannot run git commands against the workspace mount. Phase 1 happens on the operator's laptop only. The agent provides the search recipes; the operator runs them and pastes back the output.

```bash
cd /mnt/c/Users/chris/hornelore
git status --short
git branch --show-current
git log --oneline --decorate -40

# Files most likely to carry the displacement
git log --oneline --decorate --all -- \
  ui/hornelore1.0.html \
  ui/js/app.js \
  ui/js/timeline-ui.js \
  ui/js/chronology-accordion.js \
  ui/css/chronology-accordion.css \
  server/code/api/routers/chronology_accordion.py \
  README.md

# Semantic commit searches
git log --oneline --decorate --all --grep="Chronology"
git log --oneline --decorate --all --grep="Accordion"
git log --oneline --decorate --all --grep="Memory River"
git log --oneline --decorate --all --grep="Narrator Room"
git log --oneline --decorate --all --grep="WO-NARRATOR-ROOM"
git log --oneline --decorate --all --grep="WO-CR"
git log --oneline --decorate --all --grep="KAWA"
git log --oneline --decorate --all --grep="Timeline"

# Content-history pickaxe searches (the strong ones)
git log -S "chronology-accordion" --oneline --decorate --all
git log -S "chronology_context"   --oneline --decorate --all
git log -S "Memory River"         --oneline --decorate --all
git log -S "timelinePane"         --oneline --decorate --all
git log -S "WO-NARRATOR-ROOM-01"  --oneline --decorate --all
git log -S "view tabs"            --oneline --decorate --all
git log -S "Life Map | Photos | Peek at Memoir" --oneline --decorate --all

# Inspect candidate commits
git show --stat <commit>
git show --name-only <commit>
git show <commit> -- ui/hornelore1.0.html
git show <commit> -- ui/js/app.js
git show <commit> -- README.md
```

**Output required:** `docs/reports/ACCORDION_TIMELINE_FORENSIC_REPORT.md`

Required sections:
1. Current branch + HEAD
2. Last commit where Chronology Accordion was mounted as a primary surface
3. First commit where Memory River became a primary narrator tab
4. Exact files changed in the displacement commit(s)
5. Whether chronology backend still exists (sandbox confirmed: yes)
6. Whether chronology frontend JS still exists (confirmed: yes)
7. Whether chronology CSS still exists (laptop check)
8. Whether runtime `chronology_context` injection still exists in `buildRuntime71`
9. Recommended patch target list
10. Risk notes

---

## Phase 2 — Code review (sandbox-side; partially complete)

Already-confirmed by sandbox recon (above):
- Chronology backend route exists and is mounted
- Chronology frontend JS exists and is loaded by shell
- Memory River is the primary narrator-room tab
- No persistent right rail in the narrator-room layout

**Remaining Phase 2 work (laptop-side, then or while Phase 1 runs):**

```bash
# Find every relevant file
find . -iname '*chronology*' -o -iname '*timeline*' -o -iname '*river*' -o -iname '*kawa*' \
  | grep -v __pycache__ | sort

# Search current code for everything related
grep -RIn "chronology-accordion\|chronology_context\|timelinePane\|Memory River\|Kawa\|memory-river\|lv.*River\|Narrator Room\|Peek at Memoir\|Life Map" \
  ui server docs README.md \
  | tee docs/reports/accordion_timeline_grep.txt

# Backend route detail
grep -RIn "chronology_accordion\|chronology-accordion\|Chronology" server/code server \
  | tee docs/reports/chronology_backend_grep.txt

# UI shell detail
grep -RIn "Memory River\|Life Map\|Photos\|Documents\|Peek at Memoir\|right rail\|timeline" ui \
  | tee docs/reports/narrator_room_ui_grep.txt

# Runtime payload context
grep -RIn "chronology_context\|memoir_context\|media_count\|projection_family" ui server \
  | tee docs/reports/runtime_context_grep.txt
```

**Output required (added to forensic report):**
- Current mounted narrator-room tabs (literal list from shell)
- Current right-side panel/context-panel behavior
- Any dead chronology code still on disk but not mounted
- Any missing files that need restoring from git history
- Whether `chronology_context` is still flowing through `buildRuntime71` to the LLM

---

## Phase 3 — Patch plan (only after report)

**Do not start until forensic + code-review report is written.**

Patch goals (locked):

1. **Restore accordion timeline as persistent right rail.**
2. **Timeline remains visible across:** Conversation / Life Map / Photos / Documents / Peek at Memoir.
3. **Main narrator-room tabs become:**
   - Conversation
   - Life Map
   - Photos
   - Documents
   - Peek at Memoir
4. **Remove Memory River from primary narrator tabs.** Acceptable disposition:
   - hidden behind feature flag, OR
   - moved to Operator experimental panel, OR
   - code left dormant in tree but not mounted.
5. **Reuse existing Chronology Accordion code.** Do not rebuild.
6. **Do not create a second timeline store.** One source of timeline truth.
7. **Do not write truth from timeline clicks.** Authority-aware projection only.
8. **Preserve Life Map.** Period click changes active era.
9. **Preserve Peek at Memoir.** Add Memoir Correction Rule routing.

---

## Phase 4 — Media timeline design check

Before coding photo/document thumbnail rendering on the timeline, inspect current schema.

```bash
grep -RIn "date_precision\|DATE_PRECISIONS\|exact.*month.*year.*decade.*unknown\|season" server ui
```

If the current `date_precision` enum lacks `season`, propose a migration. **Do not silently fake dates.**

**Required date precision model:**

```
exact
month
season
year
decade
unknown
```

**Required media timeline fields** (add migration if not present):

```
date_label       — operator-displayed string ("Summer 1968")
date_precision   — one of the six above
date_year        — int when known, else null
date_month       — 1-12 when known, else null
date_season      — "spring" | "summer" | "fall" | "winter" | null
date_sort_key    — derived sortable key, FOR ORDERING ONLY (not truth)
date_source      — "exif" | "operator_typed" | "ocr" | "filename_inference"
```

**`date_sort_key` is for ordering only. It is not truth.** A photo with `date_sort_key = "1968-07-04"` derived from EXIF still carries `date_precision = "exact"` and a real `date_*` field set; the sort key never gets promoted.

---

## Phase 5 — Implement restore

**After report banks.** Patch likely targets:

- `ui/hornelore1.0.html` — narrator-room view-tabs nav, persistent right-rail container, Memory River demoted
- `ui/js/app.js` — `lvNarratorShowView` switching logic if it has Memory River wired as the default
- `ui/js/chronology-accordion.js` — mount target switches from popover-only to right-rail + popover (or just right-rail)
- `ui/css/chronology-accordion.css` — collapsed/expanded width, persistent-rail layout
- `server/code/api/routers/chronology_accordion.py` — only if the route response shape needs a delta for media bucketing
- `ui/js/api.js` — only if endpoint constant missing
- `ui/js/ui-health-check.js` — add the new health checks (Phase 6)
- `README.md` — replace "read-only timeline sidebar" with the authority-aware projection wording

**Required UI:**
- persistent right rail
- collapsed width approximately 80px
- expanded width approximately 280-360px
- accordion grouped by decade / year
- media thumbnail strip in year rows
- unplaced media bucket (date_precision = "unknown")
- active era highlight (synced to Life Map)
- click on year/era updates `chronology_context` in runtime + sends to next chat turn

---

## Phase 6 — Tests

Required acceptance (must pass before WO closes):

| # | Test | PASS condition |
|---|---|---|
| 1 | Chronology endpoint responds | `GET /api/chronology-accordion?person_id=<id>` returns 200 with three lanes |
| 2 | Narrator Room opens with timeline rail visible | Right rail mounted on first render |
| 3 | Timeline rail persists across tab switches | Conversation → Life Map → Photos → Documents → Peek at Memoir; rail visible throughout |
| 4 | Memory River is not a primary narrator tab | Not in `.lv-narrator-view-tabs` nav |
| 5 | Life Map period click changes active era | Existing behavior preserved; era pill updates |
| 6 | Timeline year click changes active era | Synced bidirectionally with Life Map |
| 7 | Timeline click sends chronology_context | `buildRuntime71` payload includes the focused year/era |
| 8 | Photo thumbnail under correct year/month/season bucket | When metadata exists |
| 9 | Unknown-date media in Unplaced bucket | Date precision `unknown` lands at top of accordion in unplaced section |
| 10 | Peek at Memoir opens with content | Existing behavior preserved |
| 11 | **Peek at Memoir cosmetic edit** | Saved as memoir text edit; truth not touched |
| 12 | **Peek at Memoir factual correction** | Janice DOB scenario: corrected value lands in `family_truth_promoted` with `source: "memoir_human_edit"`; Timeline + Life Map + Bio Builder all re-render; Lori runtime sees corrected DOB |
| 13 | No timeline action writes to truth tables | `family_truth_notes`, `family_truth_rows`, `family_truth_promoted`, `facts`, `questionnaire` all unchanged after timeline interactions |
| 14 | UI Health Check additions | New checks: chronology route reachable; chronology rail mounted; rail persists across tabs; Memory River not primary; Peek at Memoir mounted; Memoir Correction Rule routing wired |

---

## Phase 7 — Report

`docs/reports/ACCORDION_TIMELINE_RESTORE_REPORT.md` with:
- Forensic finding: commit where timeline was lost
- Commit where Memory River became primary
- Files restored / changed
- Tests run (PASS/FAIL table for the 14 acceptance tests)
- Known limitations
- Next-WO recommendation if media thumbnail rendering is partial
- README change diff (read-only → authority-aware projection)
- License note: Memoir Correction Rule should be added to LICENSE Reserved Rights enumeration on next pass (not in this WO)

---

## Stop conditions

Stop and report before patching if:
- Chronology backend route is gone and cannot be recovered from history. *(Sandbox recon confirms it's still present — unlikely.)*
- Chronology frontend file is gone and no historical copy exists. *(Sandbox recon confirms it's still present — unlikely.)*
- Current narrator-room UI is on a different branch than expected.
- Uncommitted changes would be overwritten by the patch.
- Schema migration for date_precision needs operator decision before media timeline phase.

---

## Final commit message (template)

```
Restore accordion timeline as narrator-room persistent right rail

- Restore Chronology Accordion as the persistent right-side rail of
  the Narrator Room. Visible across Conversation / Life Map / Photos /
  Documents / Peek at Memoir.
- Demote Memory River from primary narrator tab. Code left in tree
  behind feature flag; not displayed by default.
- Add Documents as a primary narrator tab.
- Reframe accordion in README as "authority-aware projection of the
  current life record" rather than "read-only timeline sidebar."
- Add Memoir Correction Rule routing in Peek at Memoir: cosmetic
  edits save as memoir text; factual edits land as promoted-truth
  human corrections and re-render Timeline + Life Map + Bio Builder
  + Lori runtime context.
- 14 acceptance tests pass (see docs/reports/ACCORDION_TIMELINE_
  RESTORE_REPORT.md).
- Forensic record at docs/reports/ACCORDION_TIMELINE_FORENSIC_
  REPORT.md.
```

---

## Cross-references

- `docs/research/nested-extraction-architecture.md` — extractor lane research; not directly related but the same authority-aware framing applies to extractor candidates
- `docs/research/references.md` — reference list; will need a new Topic on memoir-correction-as-canonical-edit pattern
- `LICENSE` Reserved Rights enumeration — Memoir Correction Rule should land in the next license update
- `WO-NARRATOR-ROOM-01` (commit batch 185-189) — the WO that introduced the displacement (do not modify the historical WO; cite it as the source of the lost mount)
- `server/code/api/routers/chronology_accordion.py` — backend (do not modify)
- `ui/js/chronology-accordion.js` — frontend renderer (modify for right-rail mount)

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created. Forensic + restore + architectural-correction WO. Sandbox-side Phase 2 recon already confirms chronology engine intact and displaced by WO-NARRATOR-ROOM-01 view-tabs change. Authority-aware projection wording locked. Memoir Correction Rule (Janice DOB worked example) defined and added to acceptance tests #11/#12. |
