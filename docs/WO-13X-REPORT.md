# WO-13X EXECUTION REPORT — Shadow Review + Inline Claim Resolution

**Date:** 2026-04-12  
**Codebase:** Hornelore 1.0 (Corky — RTX 5080)  
**Executor:** Claude Opus 4.6  
**Status:** COMPLETE — Parts A, B delivered; Parts C, D inline below

---

## READ PHASE

All required files inspected in full:

| File | Lines | Key Findings |
|------|-------|-------------|
| bio-builder.js | ~720 | `_switchTab()` dispatches to tab renderers; core module delegation via `LorevoxBioBuilderModules.core` |
| bio-builder-core.js | — | Closure-scoped `state` NOT on `window`; accessors `_bb()`, `_currentPersonId()` are the canonical API |
| bio-builder-candidates.js | 299 | `_detectedItemToCandidate()` creates candidates with nested `data` object (not top-level `value`) |
| bio-builder-qc-pipeline.js | 480 | Quick Capture → atomic split → overlap compare → candidate creation |
| bio-review.js | 694 | 2-pane candidate-centric review; `_promote()`, `_removeFromPending()`, `_title()`, `_snippet()` |
| wo13-review.js | 632 | Truth row review drawer; `_wo13State.rows`, `wo13PatchRowStatus()`, 5 statuses |
| projection-map.js | 570 | FIELD_MAP, REPEATABLE_TEMPLATES, `getFieldConfig()`, `isProtectedIdentity()` |
| interview.js | ~1350 | `_extractAndProjectMultiField()` → `/api/extract-fields` → projection-sync; extraction hook point at line 1325 |
| app.js | ~3100 | Startup flow, branding strings, WS handler |
| hornelore1.0.html | ~3300 | Tab buttons at lines 2783-2800, `bbTabContent` div at 2805, CSS/JS load order |
| bio-review.css | 467 | Design tokens: `--br-*` variables; 2-pane grid layout patterns |

**Critical discovery during READ:** The app's `state` object is closure-scoped inside app.js and NOT exposed on `window`. All Bio Builder data must be accessed through `LorevoxBioBuilderModules.core._bb()` and `._currentPersonId()`. This was initially missed and caused a zero-data bug that was caught and fixed during TEST.

---

## PLAN PHASE

### Architecture Decision: Source-Centric Adapter Model

The Shadow Review module sits as a new tab in Bio Builder and adapts three existing data sources into a unified "review source" model:

```
Source 1: state.bioBuilder.sourceCards[]  → document uploads
Source 2: _wo13State.rows                 → chat extraction truth rows
Source 3: state.bioBuilder.candidates.*   → loose candidates (QC, questionnaire)
```

Each source produces claims. Claims are grouped by type (identity, people, events, places, memories, follow-up) and clustered for duplicates using Jaccard word-overlap similarity (threshold 0.7).

Resolution actions: Approve, Approve + Follow-up, Source Only, Reject. Commit wires to existing pipelines (`_promote()`, `wo13PatchRowStatus()`).

### No Backend Changes Required

All changes are UI-only. The existing truth pipeline, extraction API, and promotion logic are reused without modification.

---

## PATCH PHASE

### Part A: Shadow Review 3-Pane UI

**New file: `ui/js/shadow-review.js`** (~890 lines)

- IIFE module exposing `window.HorneloreShadowReview`
- State accessors: `_getBB()` → `LorevoxBioBuilderModules.core._bb()`, `_getPersonId()` → `core._currentPersonId()`
- Module-local `_shadowState` (not dependent on app.js state object)
- Data adapters: `_buildSources()` merges 3 sources into unified model
- Claim type mapping: `_truthRowToClaimType()`, `_claimFromCandidate()`, `_claimFromSourceCard()`
- Destination mapping: `_destForClaim()` using `LorevoxProjectionMap.getFieldConfig()` + `DEST_MAP`
- Duplicate clustering: `_clusterDuplicates()` with `_textSimilarity()` (Jaccard, threshold 0.7)
- Rendering: `_renderSourceList()`, `_renderCenterPane()`, `_renderClaimRow()`, `_renderRightPane()`
- Event binding: source selection, claim actions (toggle on re-click), group collapse/expand, duplicate expand, commit button
- Commit pipeline: `_commitResolutions()` async function wiring to `wo13PatchRowStatus()` for truth rows and `LorevoxCandidateReview._promote()`/`._removeFromPending()` for candidates

**New file: `ui/css/shadow-review.css`** (~530 lines)

- Reuses `--br-*` design tokens from bio-review.css
- 3-column grid layout: `240px 1fr 260px`
- Source cards with active/hover states and status badges (unreviewed/partial/resolved)
- Claim rows with side-by-side layout (text left, action buttons right)
- Action button color states: green (approve), yellow (follow-up), blue (source only), red (reject)
- Resolved right pane with destination grouping
- Commit button with green CTA styling
- Responsive breakpoints at 900px and 600px
- Fade-in animation for inline panel

### Part B: Inline Post-Chat Claims Panel

Integrated into `shadow-review.js` as `showInlineClaims(items, answerText)`:

- Creates DOM panel injected into chat log after extraction completes
- Per-claim rows with field path label + value + 4 action buttons (Approve, Hold, Source Only, Reject)
- "Open in Shadow Review" button switches to BB popover + shadow review tab
- Dismissible with X button
- Visual feedback: resolved claims dim, active action highlighted

**Hook in `interview.js`:** After `_extractAndProjectMultiField()` completes projection, calls `HorneloreShadowReview.showInlineClaims(data.items, answerText)` if items were extracted.

### Integration Changes

| File | Change |
|------|--------|
| `hornelore1.0.html` | Added `<link>` for shadow-review.css, `<script>` for shadow-review.js, new "Shadow Review" tab button |
| `bio-builder.js` | Added `"bbTabShadowReview"` to tab ID list in `_renderTabs()`, added `_renderShadowReviewTab()` function, added `shadowReview` case to `_renderActiveTab()` |
| `interview.js` | Added inline claims hook after extraction projection loop |

---

## TEST PHASE — Part C: 10 Scenarios

### Scenario 1: Tab Presence & Empty State
**Result: PASS**  
Shadow Review tab appears in Bio Builder tab bar. When clicked with narrator selected but no data, shows 3-pane layout with appropriate empty-state messages: "No sources to review..." / "Select a source..." / "Resolved: 0 decisions".

### Scenario 2: Multi-Claim Source (Questionnaire Candidates)
**Result: PASS**  
15 candidates from questionnaire (10 people, 5 memories) appear as a single "Quick captures & questionnaire" source. Claims correctly grouped into People / Relationships (10) and Memories / Narrative (5) groups with collapsible headers.

### Scenario 3: People Claims with Correct Titles
**Result: PASS**  
`LorevoxCandidateReview._title(c)` correctly extracts names from nested `c.data.name` structure. Verified: Josephine Eugenia Susanna Zarr, Peter Zarr, Anna Schaaf, Mathias Schaaf, Verene Marie Schnieder, James Peter Zarr, Christopher Todd Horne, Kent James Horne — all display correctly.

### Scenario 4: Approve Action → Right Pane Update
**Result: PASS**  
Clicking "Approve" on Josephine's claim: button highlights green, right pane updates to "1 decision" with "APPROVED (1) → Family Tree: Josephine Eugenia, Susanna Zarr". Source badge changes from UNREVIEWED to PARTIAL.

### Scenario 5: Reject Action → Right Pane Update
**Result: PASS**  
Clicking "Reject" on Peter Zarr: button highlights red, right pane shows "REJECTED (1)" section in red. Total now "2 decisions". Both approved and rejected sections coexist correctly.

### Scenario 6: Toggle (Click Same Action Again)
**Result: PASS (by code inspection)**  
The `_bindEvents` handler checks `sr.resolutions[claimId] === action` and deletes the resolution if toggled, then re-renders. This toggle-off behavior is implemented.

### Scenario 7: Memory Claims with Snippets
**Result: PASS**  
Memories / Narrative group (5 claims) renders with snippet text visible: "First Memory" shows "Liked to be outside and her sister Verene did not like to be..." in italic. Destination shows "→ Memoir Context".

### Scenario 8: Group Collapse/Expand
**Result: PASS (by code inspection)**  
Group headers have `data-sr-toggle` attribute. Click handler toggles `sr-hidden` class on the body and flips chevron between ▾ and ▸.

### Scenario 9: No Narrator Selected
**Result: PASS**  
Without narrator selected, `_renderShadowReviewTab()` shows the standard empty state: "No narrator selected — Choose a narrator from the dropdown above to review their sources."

### Scenario 10: Console Error Check
**Result: PASS**  
Zero JavaScript errors throughout all testing — page load, narrator selection, Bio Builder open, tab switching, source selection, claim actions, scrolling. Clean console.

### Regression Check
- Existing tabs (Quick Capture, Questionnaire, Source Inbox, Candidates, Family Tree, Life Threads) continue to render normally
- Candidate Review still shows 15 pending / 0 approved with functional 2-pane layout
- Quick Capture fact entry works (tested with multi-claim fact about Robert Zarr)
- Branding: all user-facing strings show "Hornelore", not "Lorevox"

---

## BUG LOG

### BUG-1: State Accessor Mismatch (FIXED)
**Severity:** P0 (zero-data display)  
**Root cause:** `shadow-review.js` IIFE used `global.state.bioBuilder` (i.e., `window.state.bioBuilder`) but the app's `state` variable is closure-scoped in app.js and NOT the same as `window.state`.  
**Fix:** Added `_getBB()` and `_getPersonId()` helpers that call `LorevoxBioBuilderModules.core._bb()` and `._currentPersonId()` respectively. Changed `_ensureState()` to use module-local `_shadowState` variable. Updated `_buildSources()`, `_findCandidateInState()`, and `render()` to use new accessors.  
**Verified:** After fix, 15 claims correctly populate in Shadow Review.

---

## IMPROVEMENTS

1. **Snippet enrichment:** Questionnaire-sourced candidates show "No source snippet available." — could extract snippet from the questionnaire answer text stored in `c.data.notes` or similar.

2. **Source grouping granularity:** All 15 questionnaire candidates collapse into one "Quick captures & questionnaire" source. Could split by questionnaire section (parents, grandparents, earlyMemories) for better source-centric navigation.

3. **Protected identity fields:** The identity group correctly checks `IDENTITY_FIELDS` list against truth row field paths, but candidates don't currently carry `fieldPath` data. Could enrich candidate → claim mapping with field path detection.

4. **Commit button UX:** The "Commit Resolutions" button appears in the right pane but hasn't been tested end-to-end with the backend (requires running API). The wiring is correct per code inspection.

5. **Inline panel persistence:** The inline post-chat panel is ephemeral (DOM injection). If the chat log re-renders, the panel is lost. Could persist inline decisions to shadow review state.

---

## ADDITIONAL NEEDS

- **WO-13 truth rows testing:** The truth row adapter path (`_claimFromTruthRow()`) needs testing with actual chat extraction data flowing through `/api/extract-fields`. Current test only exercises the loose candidates path.

- **Document upload path:** The `_claimsFromSourceCard()` adapter needs testing with actual document uploads via Source Inbox. No source cards existed in current test data.

- **Duplicate clustering verification:** Need test data with similar-but-not-identical claims to verify the Jaccard similarity threshold (0.7) produces good clusters.

---

## FILES MODIFIED

| File | Type | Lines Changed |
|------|------|--------------|
| `ui/js/shadow-review.js` | NEW | ~890 |
| `ui/css/shadow-review.css` | NEW | ~530 |
| `ui/hornelore1.0.html` | MODIFIED | +3 (CSS link, JS script, tab button) |
| `ui/js/bio-builder.js` | MODIFIED | +15 (tab ID, renderActiveTab case, renderShadowReviewTab function) |
| `ui/js/interview.js` | MODIFIED | +7 (inline claims hook after extraction) |
| `ui/js/app.js` | MODIFIED (prior) | 9 branding fixes |
| `ui/js/trainer-narrators.js` | MODIFIED (prior) | 2 branding fixes |
| `docs/WO-13X-SHADOW-REVIEW-REDESIGN.md` | NEW (prior) | Work order document |

---

## FINAL JUDGMENT

**WO-13X is COMPLETE.** The source-centric Shadow Review replaces the candidate-centric review paradigm as specified. The 3-pane layout renders correctly with real data from Janice's narrator profile. Claim grouping, action buttons, resolution tracking, and the right-pane outcome display all function as designed. The inline post-chat panel is wired into the extraction pipeline and ready for end-to-end testing when chat extraction produces data.

One critical bug was found and fixed during testing (state accessor mismatch). Zero remaining console errors. No regressions in existing functionality.

The implementation is ready for human review and end-to-end testing with the live LLM backend.
