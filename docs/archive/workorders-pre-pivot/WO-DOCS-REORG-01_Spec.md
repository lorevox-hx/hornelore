# WO-DOCS-REORG-01 — Spec

**Status:** READY (do NOT execute until SPANTAG decision lands)
**Type:** Repo organization, docs-only, mechanical
**Date:** 2026-04-27
**Lab/gold posture:** Hornelore-side. Lorevox already has clean root (no WO specs at top), so no Lorevox commit needed.
**Blocked by:** SPANTAG eval result (`r5f-spantag-on-v3`). Several WO statuses depend on the SPANTAG decision (lock vs fail). Reorg AFTER decision means we're sorting a stable corpus, not chasing files in flux.

---

## Why this WO exists

Repo root has accumulated ~25+ WO spec files (`WO-*_Spec.md`, `WO-*_FULL_WO.md`, `*_PREP_PACK.md`) plus standalone reports (`FAILING_CASES_r5e1_RUNDOWN.md`, `FAILURE_CLUSTERS_r5e1.md`, `POST-R4-BASELINE-LOCK.md`). Operational files (`README.md`, `LICENSE`, `CLAUDE.md`, `.bat` launchers, etc.) have to share visual space with workflow artifacts.

Effect: scanning the root to see "what's actually here" is harder than it should be. The lifecycle of a WO (active / parked / closed) is invisible without opening each file.

Fix: move WO specs into `docs/wo/{active,parked,closed}/` so the root carries operational files only and WO lifecycle is visible from the directory listing.

---

## Decisions locked

```
1. Structure: lifecycle-based, not domain-based.
   docs/wo/active/   — currently being worked on or about to be
   docs/wo/parked/   — specced, not in flight, may reactivate later
   docs/wo/closed/   — banked, kept for history and cross-reference

2. Filenames unchanged. Paths change; WO identifiers (e.g.
   WO-EX-SPANTAG-01) are stable.

3. CLAUDE.md cross-references update via sed pass.
   WO-internal cross-references update via grep + sed.
   Verification: zero broken references after the move.

4. Standalone reports stay in docs/reports/ (already there for most).
   Any *_RUNDOWN.md, FAILURE_CLUSTERS_*.md, POST-*-LOCK.md at root
   moves to docs/reports/.

5. Operational files stay at root: README, HANDOFF, CLAUDE.md, LICENSE,
   CONTRIBUTING.md, .env, .gitignore, *.bat (Windows launchers),
   launchers/, scripts/, server/, ui/, data/, docs/, tests/.
```

---

## Initial classification (verify before move)

The lifecycle classification is best-effort from CLAUDE.md changelog and task list as of 2026-04-27. Re-verify each WO's status during execution; status may have shifted by the time this runs.

### `docs/wo/active/` — currently being worked on or about to be

```
WO-EX-SPANTAG-01_Spec.md            (active extractor lane)
WO-EX-SPANTAG-01_FULL_WO.md         (execution companion)
WO-EX-BINDING-01_Spec.md            (active, post-SPANTAG lock)
WO-EX-VALUE-ALT-CREDIT-01_Spec.md   (active in queue, #97)
WO-EX-SCHEMA-ANCESTOR-EXPAND-01_Spec.md  (active in queue, #144)
WO-LIFE-MAP-ERA-AXIS-01_Spec.md     (ready, multi-phase)
WO-ACCORDION-TIMELINE-FORENSIC-01_Spec.md  (ready)
WO-LORI-PHOTO-SHARED-01_Spec.md     (acceptance tests pending, #171)
WO-LORI-PHOTO-INTAKE-01_Spec.md     (Phase 2 pending, #172)
WO-LORI-PHOTO-ELICIT-01_Spec.md     (Phase 2 pending, #173)
WO-INTAKE-IDENTITY-01_Spec.md       (Chris's lane, v3 spec final)
WO-MEDIA-ARCHIVE-01_Spec.md         (recent, may still be active)
```

### `docs/wo/parked/` — specced, not in flight

```
WO-EX-NESTED-BINDING-01_Spec.md     (parked behind SPANTAG lock)
WO-LORI-CONFIRM-01_PREP_PACK.md     (parked v1, dateRange descope)
WO-EVAL-MULTITURN-01_Spec.md        (parked spec)
WO-EX-PROMPTSHRINK-01_Spec.md       (measured not adopted, in-tree flag)
WO-EX-TRUNCATION-LANE-01_Spec.md    (#102, deferred)
WO-DOCS-REORG-01_Spec.md            (this file — moves itself last)
```

### `docs/wo/closed/` — banked, kept for cross-reference

```
WO-EX-SECTION-EFFECT-01_Spec.md     (#95 PARK)
WO-EX-NARRATIVE-FIELD-01_Spec.md    (#117 closed)
WO-EX-TURNSCOPE-01_Spec.md          (#72 closed)
WO-EX-FAILURE-PACK-01_Spec.md       (#141 closed)
WO-EX-DISCIPLINE-01_Spec.md         (#142 closed)
WO-EX-FIELDPATH-NORMALIZE-01_Spec.md (closed)
WO-EX-TWOPASS-01_Spec.md            (superseded by SPANTAG)
WO-AUDIO-NARRATOR-ONLY-01_Spec.md   (#234 built)
WO-HORNELORE-SESSION-LOOP-01_Spec.md (#204 built)
WO-KAWA-01_Spec.md                   (verify status)
WO-KAWA-03A_Spec.md                  (verify status)
WO-EX-SECTION-EFFECT-01_PHASE3_WO.md (closed with #95)
WO-LORI-PHOTO_PREP_PACK*.md          (if any superseded)
```

### `docs/reports/` — standalone reports (move from root if at root)

```
FAILING_CASES_r5e1_RUNDOWN.md
FAILURE_CLUSTERS_r5e1.md
POST-R4-BASELINE-LOCK.md
FAILING_CASES_r5h_RUNDOWN.md
LAPTOP-SETUP.md  (if at root — may belong in docs/ instead)
```

---

## Scope — IN

1. Create directory structure: `docs/wo/active/`, `docs/wo/parked/`, `docs/wo/closed/`.
2. `git mv` each WO file to its lifecycle folder per the classification above.
3. Move standalone reports from root to `docs/reports/`.
4. sed-update cross-references in `CLAUDE.md` (paths to WO files).
5. sed-update cross-references inside WO files themselves (each WO that references another WO).
6. Verification grep: zero broken references after move.
7. Single atomic commit (or two — one for moves, one for reference updates — if cleaner for review).

## Scope — OUT

- Renaming any WO file. Identifiers stay stable; only paths change.
- Modifying WO content. Pure path migration.
- Creating new WOs. (This WO writes itself last to its parked/ home.)
- Touching `docs/specs/`, `docs/research/`, or `docs/reports/` internal structure (already organized).
- Lorevox repo (already clean root).
- README/HANDOFF/CLAUDE.md content edits beyond reference paths.

---

## Phase plan

### Phase 0 — Pre-flight verification

```bash
cd /mnt/c/Users/chris/hornelore
git status                    # tree must be clean
ls -la WO-*.md *_PREP_PACK.md FAILING*.md FAILURE*.md POST-*.md  # inventory
ls -la docs/                  # confirm structure
```

Acceptance: tree clean, all listed files exist where expected, no surprises in the docs/ subtree.

If tree is dirty, halt and commit pending work first.

---

### Phase 1 — Re-verify WO lifecycle classification

Re-read CLAUDE.md changelog and the active task list. Adjust the active/parked/closed split if any WO has changed status since this spec was written. Common drifts to watch for:

- A WO marked active in this spec may have closed during SPANTAG resolution.
- A WO marked closed may have reactivated.
- New WOs authored after 2026-04-27 need classification.

Output: a refreshed classification table, captured as a comment block in the commit message OR as `docs/reports/wo-reorg-classification-{date}.md` if the changes are extensive.

---

### Phase 2 — Create directories + git mv

```bash
mkdir -p docs/wo/active docs/wo/parked docs/wo/closed

# Active
git mv WO-EX-SPANTAG-01_Spec.md docs/wo/active/
git mv WO-EX-SPANTAG-01_FULL_WO.md docs/wo/active/
# … continue for each active WO

# Parked
git mv WO-EX-NESTED-BINDING-01_Spec.md docs/wo/parked/
# … continue for each parked WO

# Closed
git mv WO-EX-SECTION-EFFECT-01_Spec.md docs/wo/closed/
# … continue for each closed WO

# Reports at root → docs/reports/
git mv FAILING_CASES_r5e1_RUNDOWN.md docs/reports/
# … continue for each report at root
```

`git mv` preserves history. Each move is one rename; verify with `git status`.

---

### Phase 3 — Update cross-references

CLAUDE.md is the highest-density reference site. After all `git mv` operations, run a sed pass to update every `WO-*_Spec.md`, `WO-*_FULL_WO.md`, `*_PREP_PACK.md`, `*_RUNDOWN.md` reference to its new path.

```bash
# Build the move map first (snake_case for clarity)
declare -A MOVES=(
  [WO-EX-SPANTAG-01_Spec.md]=docs/wo/active/WO-EX-SPANTAG-01_Spec.md
  [WO-EX-SPANTAG-01_FULL_WO.md]=docs/wo/active/WO-EX-SPANTAG-01_FULL_WO.md
  # … continue for every moved file
)

# Apply to CLAUDE.md and every WO file
for src in "${!MOVES[@]}"; do
  dst="${MOVES[$src]}"
  # Update plain references (e.g. "WO-EX-SPANTAG-01_Spec.md" → "docs/wo/active/WO-EX-SPANTAG-01_Spec.md")
  # Skip lines that already have the destination path (idempotent)
  sed -i -E "s|([^/]|^)${src}|\1${dst}|g" CLAUDE.md
  for f in docs/wo/active/*.md docs/wo/parked/*.md docs/wo/closed/*.md; do
    sed -i -E "s|([^/]|^)${src}|\1${dst}|g" "$f"
  done
done
```

**Don't blanket-update across the whole repo.** Reference strings appearing inside `docs/reports/master_loop01_*.json` files (eval reports) are historical and shouldn't be rewritten. Limit sed to CLAUDE.md and the WO files themselves.

---

### Phase 4 — Verification

```bash
# Find any reference to the OLD root-level path (should return zero hits)
grep -rn "WO-.*_Spec\.md\b\|WO-.*_FULL_WO\.md\b\|.*_PREP_PACK\.md\b" \
  CLAUDE.md docs/wo/ \
  | grep -v "docs/wo/active\|docs/wo/parked\|docs/wo/closed" \
  | grep -v "^[^:]*:[^:]*:[^:]*docs/reports"

# Expected output: empty.
# Any hit indicates a stale reference that didn't get rewritten.
```

```bash
# Verify directory listing
ls docs/wo/active/ docs/wo/parked/ docs/wo/closed/

# Verify root cleanup
ls WO-*.md *_PREP_PACK.md 2>/dev/null
# Expected output: nothing (all moved). If anything appears, classify it.
```

---

### Phase 5 — Commit

Single atomic commit OR two-commit pair (rename + ref-update) — your call. Single commit is simpler review; two commits separate "physical move" from "logical update."

If one commit:

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: reorg WO specs into docs/wo/{active,parked,closed}

Move ~25 WO spec files from repo root into lifecycle-based
subdirectories under docs/wo/. Classification verified against
CLAUDE.md changelog and active task list.

- Active: SPANTAG, BINDING, ERA-AXIS, ACCORDION, PHOTO trio,
  INTAKE-IDENTITY, VALUE-ALT-CREDIT, SCHEMA-ANCESTOR-EXPAND,
  MEDIA-ARCHIVE.
- Parked: NESTED-BINDING (post-SPANTAG), LORI-CONFIRM,
  EVAL-MULTITURN, PROMPTSHRINK, TRUNCATION-LANE, DOCS-REORG (this).
- Closed: SECTION-EFFECT, NARRATIVE-FIELD, TURNSCOPE,
  FAILURE-PACK, DISCIPLINE, FIELDPATH-NORMALIZE, TWOPASS,
  AUDIO-NARRATOR-ONLY, HORNELORE-SESSION-LOOP, KAWA family.

Standalone reports (FAILING_CASES_*, FAILURE_CLUSTERS_*,
POST-*-LOCK) moved to docs/reports/ where they belong.

CLAUDE.md cross-references updated. WO-internal cross-
references updated. Verification grep: zero broken references.

Repo root now carries only operational files: README, HANDOFF,
CLAUDE.md, LICENSE, CONTRIBUTING.md, .env, *.bat launchers,
launchers/, scripts/, server/, ui/, data/, docs/, tests/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If two commits: first one is just the `git mv` operations (move only, references not yet updated — repo will have broken refs at this commit). Second one is the ref-update sed pass. Bisect-friendly but means one commit on main with broken references; not great. Single commit is cleaner.

---

## Acceptance criteria

```
1. ls WO-*.md at repo root returns zero matches.
2. ls docs/wo/active/ docs/wo/parked/ docs/wo/closed/ shows all
   WOs in their classified homes.
3. grep -rn for old root-level WO path patterns in CLAUDE.md and
   docs/wo/*.md returns zero hits (besides the historical
   docs/reports/ entries which are intentionally preserved).
4. Open CLAUDE.md and verify a sample of cross-references resolve
   (e.g., the SPANTAG row's reference to WO-EX-SPANTAG-01_Spec.md
   now reads docs/wo/active/WO-EX-SPANTAG-01_Spec.md).
5. Open one WO file (e.g., WO-EX-NESTED-BINDING-01_Spec.md in
   docs/wo/parked/) and verify its cross-references to other WOs
   resolve to the new lifecycle paths.
6. git log --oneline --diff-filter=R shows ~25-30 R (rename)
   entries in the latest commit.
7. The repo root listing visually carries operational files only,
   no WO specs.
```

---

## Risks

1. **Stale lifecycle classification.** A WO marked active here may have closed by the time this WO runs. Mitigation: Phase 1 re-verification step is mandatory, not optional. Use the live task list and recent CLAUDE.md changelog as truth, not this spec's table.

2. **Missed cross-references.** Some WO might be referenced from a non-obvious file (e.g., a comment in `extract.py`, a test fixture, a README in `docs/research/`). Mitigation: Phase 4 grep is scoped narrowly (CLAUDE.md + docs/wo/), but a wider repo-grep at the end as a sanity check would catch outliers — `grep -rn "WO-.*_Spec\.md" --include="*.md" --include="*.py" --include="*.js" --include="*.html"` then audit each hit.

3. **Eval report JSONs reference WO paths.** `docs/reports/master_loop01_*.json` files may contain WO references in their `commit_msg` fields or similar. Those are historical and should NOT be rewritten — they're frozen at the time of the eval. Phase 3's sed scope explicitly excludes them.

4. **Future WOs need a home.** Once this lands, all new WO specs should be authored directly into `docs/wo/active/`. Worth a one-line addendum in CLAUDE.md noting the new convention.

5. **Reverting is expensive.** If we need to roll back the reorg, every reference has to be re-rewritten. Mitigation: keep the sed move-map saved as a comment in the commit message (already in the suggested commit body) so reversal can be mechanical if needed.

---

## Stop conditions

```
STOP if tree is dirty before Phase 0. Commit pending work first.

STOP if Phase 1 re-verification finds a WO whose lifecycle is
        ambiguous. Tag Chris for clarification before moving.

STOP if Phase 4 verification grep returns broken references.
        Roll back the partial move, fix the sed pattern, retry.

STOP if any non-rename git diff appears in the commit. The reorg
        should be 100% renames + reference path updates. Any other
        diff means we accidentally edited content.

STOP if WO files appear with content modifications beyond the path
        updates in cross-references. The sed pattern may have over-
        matched; review and tighten.
```

---

## Final directive

```
Move, don't modify.
Lifecycle, not domain.
Atomic commit.
Zero broken references.
The root should look like a project, not a workflow.
```

---

## Cross-references

- Companion to: `WO-LIFE-MAP-ERA-AXIS-01_Spec.md` (era-axis WO authored same day)
- Trigger: Chris's observation 2026-04-27 — "there are a lot of files there that should be organized in the doc folder"
- Lifecycle source: CLAUDE.md "Active sequence" block + recent task list
- Lab/gold rule: Lorevox already clean root; no Lorevox commit needed.

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created. Captures lifecycle-based reorg plan for ~25+ WO specs from repo root into docs/wo/{active,parked,closed}/. Blocked on SPANTAG decision so the corpus is stable when reorg runs. Single atomic commit, sed-based reference update, verification grep. Estimated effort: ~30 minutes carefully. |
