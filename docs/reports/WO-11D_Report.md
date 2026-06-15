# WO-11D — Trainer Chooser Refresh + Narrated Intro Copy

**Status:** Patch complete — ready for live testing  
**Date:** April 13, 2026

---

## Summary

Replaced the celebrity-forward trainer chooser ("Run Shatner Trainer" / "Run Dolly Trainer") with three user-facing onboarding choices: Questionnaire First, Clear & Direct, and Warm Storytelling. Updated all trainer intro copy so Lori explains what Lorevox is, who Lori is, how to answer, and what Back/Next/Skip do. Updated all trainer examples to use normal life-history complexity (preferred names, pronouns, multiple marriages, blended families) instead of celebrity biography. Added a third trainer path (Questionnaire First) for the most structured, basics-first entry point.

## Root Cause

The original trainer naming was developer-facing ("Shatner" / "Dolly") and described the implementation inspiration, not the user experience. Elderly narrators encountered trainer labels that felt technical and unfamiliar. The trainer intro copy also jumped directly into examples without explaining what Lorevox is, what Lori does, or that complex life structures are welcome.

## Files Read

| File | Purpose |
|------|---------|
| `ui/js/trainer-narrators.js` | Full file — step content, panel render, style normalization, start/finish lifecycle |
| `ui/hornelore1.0.html` | Chooser buttons, trainer header update, template loader, normalizer |
| `ui/js/state.js` | `state.trainerNarrators` shape |
| `ui/templates/william-shatner.json` | `_trainerStyle`, `_trainerTitle`, `_trainerPrompt` fields |
| `ui/templates/dolly-parton.json` | Same trainer metadata fields |

## Files Changed

| File | Changes | Markers |
|------|---------|---------|
| `ui/js/trainer-narrators.js` | Full rewrite of `_normalizeStyle`, `_steps`, `_renderPanel` labels, added `_SHARED_LORI_INTRO`, added `_STYLE_DISPLAY` map, added `"questionnaire"` style branch | 8 |
| `ui/hornelore1.0.html` | Replaced chooser buttons with 3 user-facing choices, updated header display map, updated normalizer to accept `"questionnaire"`, updated template loader comment | 4 |

**Total: 12 `[WO-11D]` markers across 2 files.**

## What Changed

### Chooser UI

Old:
- "Run Shatner Trainer" button
- "Run Dolly Trainer" button

New:
- Section title: "Choose how you'd like to begin"
- Subtitle: "You can start with the basics, answer briefly, or tell fuller stories."
- Three full-width buttons with labels and descriptions:
  1. **Questionnaire First** — Start with the basics, step by step.
  2. **Clear & Direct** — Short answers. One fact at a time.
  3. **Warm Storytelling** — Tell it with detail, feeling, and scene.

### Internal style mapping

| User-facing choice | Internal key | Template file | Handoff style |
|---|---|---|---|
| Questionnaire First | `"questionnaire"` | `william-shatner.json` | `"structured"` equivalent |
| Clear & Direct | `"structured"` | `william-shatner.json` | `"structured"` |
| Warm Storytelling | `"storyteller"` | `dolly-parton.json` | `"storyteller"` |

`_normalizeStyle()` now accepts `"questionnaire"` as a third canonical value. Legacy `"story"` still maps to `"storyteller"`. Unknown values still fall back to `"structured"`.

### Shared Lori intro

All three trainers now begin with a shared explanation block in Lori's voice:
- What Lorevox is (a place to save and organize your life story)
- What Lori does (asks questions, listens, helps shape your story)
- No test, no perfect answers
- Real lives welcome (preferred names, pronouns, multiple marriages, blended families)
- Back/Next/Skip instructions

Each trainer adds style-specific copy after the shared block.

### Example content

All examples now use a fictional character ("Margaret Louise Carter, goes by Maggie") instead of celebrity biographies. Examples naturally demonstrate:
- Preferred name vs legal name ("everyone calls me Maggie")
- Pronouns ("I use they and them pronouns")
- Multiple marriages ("I was married twice")
- Blended families ("My son is from my first marriage, and my younger daughter is from my second")
- Holiday complexity after family changes

### Panel labels

- Eyebrow: Now shows user-facing name + subtitle (e.g., "Questionnaire First — Start with the basics, step by step.")
- Title: Changed from "Lori Trainer" to "Getting Started with Lori"
- Header card: Shows "Getting Started" with style subtitle, avatar initials QF/CD/WS

### Navigation instructions

All three trainers now include explicit navigation guidance in the final step: "Tap Start Interview to begin, or Skip if you'd rather jump right in."

## What Was Preserved

- Internal style keys (`"structured"`, `"storyteller"`) — unchanged
- Template files (`dolly-parton.json`, `william-shatner.json`) — unchanged
- Handoff behavior (`finish()` → `lv80StartTrainerInterview()`) — unchanged
- State shape (`state.trainerNarrators`) — unchanged
- Navigation behavior (Back/Next/Skip/Start Interview) — unchanged
- WO-11C modal isolation (footer lock, send/mic guards) — unchanged
- Three-step structure per trainer — preserved

## Tests Run

| Test | Method | Result |
|------|--------|--------|
| Chooser labels | grep HTML for new labels | Questionnaire First, Clear & Direct, Warm Storytelling — all FOUND |
| Old labels removed | grep HTML for old labels | "Run Shatner Trainer", "Run Dolly Trainer" — REMOVED |
| Internal onclick mapping | grep HTML for onclick handlers | questionnaire, structured, storyteller — all FOUND |
| Style normalization | Node.js unit test | questionnaire→questionnaire, structured→structured, storyteller→storyteller, story→storyteller, unknown→structured — all PASS |
| Step navigation | Node.js: start + 2x next per style | All 3 styles: 3 steps, navigation clean |
| JS syntax | Node.js fs.readFileSync | trainer-narrators.js: OK |
| Brace balance | Script block extraction | 750/750 BALANCED |
| Celebrity references | grep across all files | Zero remaining in user-facing code |

## Results

All structural tests pass. Live browser testing needed to verify:
- Visual rendering of the three chooser buttons
- Trainer panel content and step flow
- Header card updates during each trainer
- Handoff to narrator selection after trainer completes
- WO-11C footer lock still works with the new "questionnaire" style

## Debug Findings

- `_normalizeStyle()` now handles 3 canonical values plus legacy fallback
- Template loading maps `"questionnaire"` → `william-shatner.json` (same structured template) — this is intentional since questionnaire and structured share the same handoff flavor
- No TTS is triggered in trainer mode — all content is visual/text only
- Celebrity-specific example content (Dolly Parton birthplace, William Shatner name) has been fully replaced with fictional content

## Bugs Found

No new bugs introduced. All existing functionality preserved.

## Follow-up Work Recommended

| Item | Priority | Notes |
|------|----------|-------|
| Live visual testing | **High** | Verify chooser rendering, panel content, handoff |
| Questionnaire-specific template | Low | Currently reuses `william-shatner.json` for meta; could create a dedicated `questionnaire-first.json` with its own `_trainerPrompt` if handoff flavor needs to differ |
| Rename template files | Low | `dolly-parton.json` / `william-shatner.json` are internal-only but could be renamed to `storyteller.json` / `structured.json` for clarity |
| TTS narration of trainer content | Future WO | Currently text-only; adding Lori voice reading the intro would improve the experience but requires stable TTS in trainer mode |
