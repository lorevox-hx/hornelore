# Archive index — what is in `docs/archive/`, and what it is not

**Derived at:** `d0e52946aa77096841612df176f4cbb70d4edacd`, then updated by hygiene Step 2b
**Contents:** **131 archived files, 2,712,097 bytes**, in **four** cohorts
**Status:** **one file has been moved in** — the agent changelog, Step 2b. Nothing has ever
been moved *out*, and nothing has been deleted.

**The count excludes this index.** `INDEX.md` lives in `docs/archive/` but is not archived
content, and counting it would drift the figure by its own 15,305 bytes:

```bash
find docs/archive -type f ! -name INDEX.md | wc -l                                  # 131
find docs/archive -type f ! -name INDEX.md -printf '%s\n' | awk '{s+=$1} END{print s}'  # 2712097
```



---

## 1. What "archived" means here, and the one thing it must never mean

An archived document is **history that has stopped being an instruction.** It is kept
because the reasoning in it is worth reading, and moved because leaving it beside live
documents makes a reader treat it as current.

**Archived does not mean decided, finished, or safe to delete.** That distinction is the
whole reason this index exists. `CLAUDE.md` records two occasions when this repository
carried a stale current-work list, and both times the consequence was an agent rebuilding
finished work from a status line. Filing a document under `archive/` without recording
what was still open inside it produces the mirror of that failure: work quietly vanishing
because the document naming it moved.

**So the rule for every future cohort is:**

> Before a document moves here, any unresolved obligation inside it is written into
> [`../BACKLOG.md`](../BACKLOG.md) with its evidence. The move records where the *reasoning*
> went. The backlog records what is still *owed*.

Nothing is ever deleted from this directory. Removing a file from a public repository does
not remove it from Git history, and this archive is not a privacy mechanism — that is
`WO-PRIVACY-CANON-EXTRACTION-01`, which is parked and separately authorized.

---

## 2. The three cohorts, and why they are not one thing

| Cohort | Files | Bytes | Last touched | What it is |
|---|---:|---:|---|---|
| `workorders-pre-pivot/` | 113 | 1,697,413 | 2026-06-14 | Work orders and bug specs predating the universal pivot. **Not the active source of truth** |
| `handoffs-pre-pivot/` | 16 | 374,461 | 2026-06-14 | Handoffs and checklists from the same era |
| `handoffs/` | 1 | 26,093 | 2026-08-09 | A single post-pivot handoff |
| **`changelogs/`** | **1** | **614,130** | 2026-08-28 | The agent changelog, preserved byte-for-byte by Step 2b |

Both pre-pivot cohorts were moved together on **2026-06-14**, the day the universal pivot
landed. That is a single deliberate act, not accumulation, and it is why they read as a
coherent set.

### A number to correct, recorded not fixed

`CLAUDE.md` says the pre-pivot archive holds **114** work-order files. **Git derives 113.**

```bash
git ls-tree -r --name-only d0e5294 -- docs/archive/workorders-pre-pivot | wc -l   # 113
```

Off by one, and it has been quoted forward since. The correction belongs in the
control-document commit, not this one — this commit adds indexes and changes nothing
else. It is in [`../BACKLOG.md`](../BACKLOG.md).

**The durable fix is not the number.** A hand-maintained count of a directory drifts the
moment anything moves, and every archive cohort still to come will move something. The
replacement wording should be a command, exactly as `HANDOFF.md`'s "current `main`" hash
became `git rev-parse origin/main`.

---

## 3. What is NOT here, and must not be moved here without adjudication

The audit is explicit about three populations that look archivable and are not:

* **`scripts/archive/`** is not a genuine inert archive. It holds currently documented
  eval runners, backup and restore tools, and Test Lab files. See
  [`../../scripts/INDEX.md`](../../scripts/INDEX.md). Nothing there may be bulk-deleted or
  assumed dead.
* **`docs/wo/`** mixes active implementation specs with completed, superseded, parked and
  future-only documents. Twenty-nine of its 51 files are not named by the governing
  documents — **a triage signal, not proof of deadness.** The active Profile Seed transport
  map is itself unreferenced by filename from the four control documents, and it is the
  most current design document in the repository.
* **The main `tests/` tree** is the preservation contract for accepted behaviour. It is
  never archived on age. Source-shape tests may be replaced behaviourally; they are not
  deleted for being old.

Also preserved and never archive candidates: parked runtime safety, frozen Kawa, the inert
directive-family registry, compatibility readers, and migrations.

---

## 4. Planned destinations for future cohorts

Created when the first cohort actually moves, not before — an empty directory that
announces an intention is another thing that can go stale.

| Destination | For |
|---|---|
| `docs/archive/workorders/completed/` | Accepted or landed work orders, with their acceptance hash |
| `docs/archive/workorders/superseded/` | Replaced by a later spec, which the entry must name |
| `docs/archive/workorders/banked/` | Designed, deliberately not built; summarized in `BACKLOG.md` first |
| `docs/archive/handoffs/` | Dated handoffs and plans — exists already |
| `docs/archive/mockups/` | `docs/mockups/`, `ui/mockups/`, `clock_mockups_v1.html` |
| `docs/archive/reviews/` | Superseded review and audit documents |

Every cohort move owes: an entry in this index naming **the original path**, a link check
over the whole tree, and its own separately reviewable commit. Moves are never combined
with product corrections, index creation, or deletion.

---

## 5. Manifest

Original path is `docs/archive/<cohort>/<file>` — none of these files has been moved since
it was archived, so the recorded path is still the real one. "Added" is the commit date
that first introduced the file at this path.

<!-- BEGIN GENERATED MANIFEST — derived from `git ls-tree -r -l d0e5294 -- docs/archive` -->

### `docs/archive/changelogs/` — 1 file, 614,130 bytes

**Added by `WO-REPOSITORY-HYGIENE-01` Step 2b, 2026-08-28.**

| | |
|---|---|
| File | `CHANGELOG-AGENT-through-2026-08-20.md` |
| **Original path** | **`docs/CHANGELOG-AGENT.md`** |
| Destination | `docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md` |
| Date range | 2026-04-11 → 2026-08-20 |
| Bytes | **614,130** |
| Lines | 1,407 |
| SHA-256 | `2e91723267d85bf2ee262645d605546f7e5025193022089c3ebdf22f7facd4c3` |
| Git blob | `4edbdc80bd2917299d2c835494b705b3043e8cfe` |

Preserved **byte-for-byte**; `cmp` reports identical and both checksums are unchanged. The
live path `docs/CHANGELOG-AGENT.md` still exists and now holds a small **decision index**
pointing here — the entry point moved, the history did not.

### `docs/archive/handoffs/` — 1 files, 26,093 bytes

| File | Bytes | Added |
|---|---:|---|
| `HANDOFF_2026-07-31_TRIP-NARRATOR-BRIDGE.md` | 26,093 | 2026-08-09 |

### `docs/archive/handoffs-pre-pivot/` — 16 files, 374,461 bytes

| File | Bytes | Added |
|---|---:|---|
| `HANDOFF.md` | 109,887 | 2026-06-14 |
| `HANDOFF_2026-05-12_to_2026-06-10.md` | 26,400 | 2026-06-14 |
| `HANDOFF_LAPTOP_PARITY_2026-05-04.md` | 15,163 | 2026-06-14 |
| `KENT_FLOOR_CONTROL_2026-05-10.md` | 5,909 | 2026-06-14 |
| `LAPTOP-SETUP-2026-04-26.md` | 23,011 | 2026-06-14 |
| `LAPTOP_HANDOFF_2026-05-07.md` | 16,222 | 2026-06-14 |
| `LAPTOP_HANDOFF_2026-05-10.md` | 11,824 | 2026-06-14 |
| `LAPTOP_HANDOFF_KOKORO_INSTALL.md` | 13,413 | 2026-06-14 |
| `MASTER_WORK_ORDER_CHECKLIST.md` | 59,327 | 2026-06-14 |
| `MORNING-2026-04-26-night2.md` | 10,071 | 2026-06-14 |
| `MORNING-2026-04-26.md` | 12,190 | 2026-06-14 |
| `MORNING_HANDOFF_2026-05-10.md` | 30,856 | 2026-06-14 |
| `Memoir-Upgrade-Phased-Plan.md` | 7,093 | 2026-06-14 |
| `NIGHT_SHIFT_2026-05-07_MULTILINGUAL_BANK.md` | 16,074 | 2026-06-14 |
| `PILLOW-VENV-INSTALL.md` | 4,154 | 2026-06-14 |
| `SYSTEM-SWEEP-PROTOCOL-2026-04-25.md` | 12,867 | 2026-06-14 |

### `docs/archive/workorders-pre-pivot/` — 113 files, 1,697,413 bytes

| File | Bytes | Added |
|---|---:|---|
| `BUG-EX-BIRTH-DATE-PATTERN-01_Spec.md` | 7,681 | 2026-06-14 |
| `BUG-EX-DISCOURSE-AS-NAME-01_Spec.md` | 8,422 | 2026-06-14 |
| `BUG-EX-DOB-LEAP-YEAR-FALLBACK-01_Spec.md` | 4,240 | 2026-06-14 |
| `BUG-EX-LLM-COMMENTARY-AS-VALUE-01_Spec.md` | 6,103 | 2026-06-14 |
| `BUG-EX-NAME-EXTRACTION-NOW-01_Spec.md` | 3,670 | 2026-06-14 |
| `BUG-EX-PLACE-LASTNAME-FOLLOWUP-01_Spec.md` | 13,069 | 2026-06-14 |
| `BUG-EX-POB-CORRECTION-WRONG-PATH-01_Spec.md` | 5,289 | 2026-06-14 |
| `BUG-EX-PROTECTED-IDENTITY-FRAGMENT-WRITE-01_Spec.md` | 6,298 | 2026-06-14 |
| `BUG-HARNESS-RECALL-DICT-FIELDS-01_Spec.md` | 11,358 | 2026-06-14 |
| `BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01_Spec.md` | 6,716 | 2026-06-14 |
| `BUG-LORI-DUPLICATE-RESPONSE-01_Spec.md` | 9,878 | 2026-06-14 |
| `BUG-LORI-ERA-CONFABULATION-01_Spec.md` | 6,385 | 2026-06-14 |
| `BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01_Spec.md` | 10,368 | 2026-06-14 |
| `BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01_Spec.md` | 5,262 | 2026-06-14 |
| `BUG-LORI-LATE-AGE-RECALL-01_Spec.md` | 8,440 | 2026-06-14 |
| `BUG-LORI-LATENCY-VISIBILITY-01_Spec.md` | 5,294 | 2026-06-14 |
| `BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01_Spec.md` | 6,588 | 2026-06-14 |
| `BUG-LORI-MIDSTREAM-CORRECTION-01_Spec.md` | 8,219 | 2026-06-14 |
| `BUG-LORI-REFLECTION-02_Spec.md` | 11,591 | 2026-06-14 |
| `BUG-LORI-RESPONSE-STUB-COLLAPSE-01_Spec.md` | 4,685 | 2026-06-14 |
| `BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01_Spec.md` | 5,379 | 2026-06-14 |
| `BUG-LORI-SWITCH-FRESH-GREETING-01_PHASE_2_PLAN.md` | 24,993 | 2026-06-14 |
| `BUG-LORI-SWITCH-FRESH-GREETING-01_Spec.md` | 17,983 | 2026-06-14 |
| `BUG-LORI-SYSTEM-QF-PREEMPTION-01_Spec.md` | 8,268 | 2026-06-14 |
| `BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01_Spec.md` | 4,054 | 2026-06-14 |
| `BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01_Spec.md` | 7,611 | 2026-06-14 |
| `BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02_Spec.md` | 4,005 | 2026-06-14 |
| `BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01_Spec.md` | 6,253 | 2026-06-14 |
| `BUG-SESSION-STYLE-SWITCH-STALE-QF-STATE-01_Spec.md` | 9,157 | 2026-06-14 |
| `BUG-STT-PHANTOM-PROPER-NOUNS-01_Spec.md` | 5,409 | 2026-06-14 |
| `BUG-UI-API-BASE-RESET-01_Spec.md` | 10,113 | 2026-06-14 |
| `BUG-UI-POSTRESTART-SESSION-START-01_Spec.md` | 14,115 | 2026-06-14 |
| `Hornelore-WO-Checklist.md` | 23,105 | 2026-06-14 |
| `PARENT-SESSION-READINESS-CHECKLIST.md` | 11,084 | 2026-06-14 |
| `PHOTO-SYSTEM-TEST-PLAN.md` | 11,569 | 2026-06-14 |
| `WO-ACCORDION-TIMELINE-FORENSIC-01_Spec.md` | 20,052 | 2026-06-14 |
| `WO-AFFECT-ANCHOR-01_Spec.md` | 23,455 | 2026-06-14 |
| `WO-AUDIO-NARRATOR-ONLY-01_Spec.md` | 10,376 | 2026-06-14 |
| `WO-DISCLOSURE-MODE-01_Spec.md` | 23,395 | 2026-06-14 |
| `WO-DOCS-REORG-01_Spec.md` | 14,808 | 2026-06-14 |
| `WO-EVAL-MULTITURN-01_Spec.md` | 20,342 | 2026-06-14 |
| `WO-EX-BINDING-01_Spec.md` | 16,471 | 2026-06-14 |
| `WO-EX-CASE-BANK-FIXUP-01_Spec.md` | 13,023 | 2026-06-14 |
| `WO-EX-DISCIPLINE-01_Spec.md` | 5,580 | 2026-06-14 |
| `WO-EX-EVAL-WRAPPER-01_Spec.md` | 10,307 | 2026-06-14 |
| `WO-EX-FAILURE-PACK-01_Spec.md` | 4,808 | 2026-06-14 |
| `WO-EX-FIELD-CARDINALITY-PETS-01_Spec.md` | 10,877 | 2026-06-14 |
| `WO-EX-FIELDPATH-NORMALIZE-01_Spec.md` | 9,945 | 2026-06-14 |
| `WO-EX-GPU-CONTEXT-01_Spec.md` | 17,430 | 2026-06-14 |
| `WO-EX-NARRATIVE-FIELD-01_Spec.md` | 5,781 | 2026-06-14 |
| `WO-EX-NESTED-BINDING-01_Spec.md` | 12,772 | 2026-06-14 |
| `WO-EX-PROMPTSHRINK-01_Spec.md` | 17,184 | 2026-06-14 |
| `WO-EX-SCHEMA-ANCESTOR-EXPAND-01_Spec.md` | 10,321 | 2026-06-14 |
| `WO-EX-SECTION-EFFECT-01_PHASE3_WO.md` | 18,179 | 2026-06-14 |
| `WO-EX-SECTION-EFFECT-01_Spec.md` | 13,047 | 2026-06-14 |
| `WO-EX-SENTENCE-DIAGRAM-STORY-SURVEY-01_Spec.md` | 5,816 | 2026-06-14 |
| `WO-EX-SPANTAG-01_FULL_WO.md` | 29,995 | 2026-06-14 |
| `WO-EX-SPANTAG-01_Spec.md` | 27,416 | 2026-06-14 |
| `WO-EX-TRUNCATION-LANE-01_Spec.md` | 17,314 | 2026-06-14 |
| `WO-EX-TURNSCOPE-01_Spec.md` | 9,902 | 2026-06-14 |
| `WO-EX-TWOPASS-01_Spec.md` | 16,798 | 2026-06-14 |
| `WO-EX-UTTERANCE-FRAME-01_Spec.md` | 24,092 | 2026-06-14 |
| `WO-EX-UTTERANCE-FRAME-SURVEY-01_Spec.md` | 5,021 | 2026-06-14 |
| `WO-EX-VALUE-ALT-CREDIT-01_Spec.md` | 5,283 | 2026-06-14 |
| `WO-GOLFBALL-HARNESS-03_Spec.md` | 15,078 | 2026-06-14 |
| `WO-HORNELORE-SESSION-LOOP-01_Spec.md` | 17,284 | 2026-06-14 |
| `WO-INTERVIEW-CLOCK-01_Spec.md` | 25,128 | 2026-06-14 |
| `WO-KAWA-01_Spec.md` | 17,488 | 2026-06-14 |
| `WO-KAWA-03A_Spec.md` | 18,363 | 2026-06-14 |
| `WO-KAWA-UI-01_Spec.md` | 13,577 | 2026-06-14 |
| `WO-LIFE-MAP-ERA-AXIS-01_Spec.md` | 39,194 | 2026-06-14 |
| `WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01_Spec.md` | 7,045 | 2026-06-14 |
| `WO-LORI-ACTIVE-LISTENING-01_Spec.md` | 11,127 | 2026-06-14 |
| `WO-LORI-BEHAVIOR-HARNESS-01_Spec.md` | 4,909 | 2026-06-14 |
| `WO-LORI-COMMUNICATION-CONTROL-01_Spec.md` | 20,341 | 2026-06-14 |
| `WO-LORI-CONFIRM-01_PREP_PACK.md` | 39,675 | 2026-06-14 |
| `WO-LORI-CONFIRM-01_Spec.md` | 15,816 | 2026-06-14 |
| `WO-LORI-LANGUAGE-CANON-01_Spec.md` | 15,514 | 2026-06-14 |
| `WO-LORI-MEMORY-ECHO-ERA-STORIES-01_Spec.md` | 15,488 | 2026-06-14 |
| `WO-LORI-PHOTO-ELICIT-01_Spec.md` | 16,349 | 2026-06-14 |
| `WO-LORI-PHOTO-INTAKE-01_Spec.md` | 15,632 | 2026-06-14 |
| `WO-LORI-PHOTO-SHARED-01_Spec.md` | 35,362 | 2026-06-14 |
| `WO-LORI-QUESTION-ATOMICITY-01_Spec.md` | 22,099 | 2026-06-14 |
| `WO-LORI-REFLECTION-01_Spec.md` | 17,553 | 2026-06-14 |
| `WO-LORI-RESPONSE-HARNESS-01_Spec.md` | 27,466 | 2026-06-14 |
| `WO-LORI-RETURNING-NARRATOR-01_Spec.md` | 16,212 | 2026-06-14 |
| `WO-LORI-SAFETY-INTEGRATION-01_Spec.md` | 33,505 | 2026-06-14 |
| `WO-LORI-SAFETY-PASSIVE-DEATH-WISH-01_Spec.md` | 13,805 | 2026-06-14 |
| `WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01_Spec.md` | 21,079 | 2026-06-14 |
| `WO-LORI-SESSION-AWARENESS-01_Spec.md` | 31,708 | 2026-06-14 |
| `WO-LORI-SOFTENED-RESPONSE-01_Spec.md` | 11,801 | 2026-06-14 |
| `WO-LORI-STORY-CAPTURE-01_Spec.md` | 46,054 | 2026-06-14 |
| `WO-MEDIA-ARCHIVE-01_Spec.md` | 24,230 | 2026-06-14 |
| `WO-ML-TTS-EN-ES-01_Spec.md` | 17,911 | 2026-06-14 |
| `WO-NARRATIVE-CUE-LIBRARY-01_CLAUDE-ADDENDUM.md` | 9,227 | 2026-06-14 |
| `WO-NARRATIVE-CUE-LIBRARY-01_Spec.md` | 31,435 | 2026-06-14 |
| `WO-OPS-STRESS-TELEMETRY-KV-01_Spec.md` | 9,266 | 2026-06-14 |
| `WO-OPS-VRAM-VISIBILITY-01_Spec.md` | 16,178 | 2026-06-14 |
| `WO-PARENT-KIOSK-01_Spec.md` | 22,464 | 2026-06-14 |
| `WO-PARENT-SESSION-HARDENING-01_Spec.md` | 22,910 | 2026-06-14 |
| `WO-PARENT-SESSION-LONG-LIFE-HARNESS-01_Spec.md` | 16,599 | 2026-06-14 |
| `WO-PHENO-01_Spec.md` | 12,901 | 2026-06-14 |
| `WO-PROMPT-BLOAT-AUDIT-01_Spec.md` | 9,872 | 2026-06-14 |
| `WO-PROVISIONAL-TRUTH-01_Spec.md` | 15,735 | 2026-06-14 |
| `WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01_PHASE_1_PLAN.md` | 17,609 | 2026-06-14 |
| `WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01_Spec.md` | 22,298 | 2026-06-14 |
| `WO-SCHEMA-02_Gap-Analysis.md` | 14,441 | 2026-06-14 |
| `WO-SCHEMA-DIVERSITY-RESTORE-01_Spec.md` | 22,227 | 2026-06-14 |
| `WO-SESSION-STYLE-WIRING-01_Spec.md` | 16,331 | 2026-06-14 |
| `WO-STT-HANDSFREE-01A_Spec.md` | 6,152 | 2026-06-14 |
| `WO-TIMELINE-CONTEXT-EVENTS-01_Spec.md` | 35,323 | 2026-06-14 |
| `WO-TIMELINE-RENDER-01_Spec.md` | 20,658 | 2026-06-14 |
| `WO-UI-TEST-LAB-01_Spec.md` | 16,550 | 2026-06-14 |
<!-- END GENERATED MANIFEST -->
