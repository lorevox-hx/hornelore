# WO-KAWA-REMOVAL-01 — remove the retired Kawa / Memory River implementation

**Status:** ✅ **COMPLETE — ACCEPTED by Chris Horne, 2026-09-08.**
**Opened:** 2026-09-08 · **Closed:** 2026-09-08
**Authority for the decision:** Chris Horne, 2026-09-08 — see `CLAUDE.md` §*Kawa /
Memory River — REMOVED from the product 2026-09-08*.
**Baseline:** `fc781426` (mapping) → `ad15231e` (spec landed).
**Queue position:** `MASTER_WORK_ORDER_CHECKLIST.md` row 6 — **completed, not queued.**

**Landed in two commits, split at a real risk boundary:**

| Commit | Half | What it did |
|---|---|---|
| `3481d1a` | **compatibility** | Retired-value normalization for all three fields, landed **before** anything was deleted, so no step of the removal could strand a narrator |
| `0a16c88` | **removal** | Deleted the subsystem; **1,389 deletions against 393 insertions across 16 files** — 187 into existing files, 206 the new `tests/test_kawa_product_path_removed.py`. *(This cell said "187 insertions" as the whole-commit figure until 2026-09-08.)* |

**Why two commits.** Part 1 makes legacy state safe; Part 2 destroys the retired
implementation. If Part 2 had a problem it could be stopped or reverted without
losing the compatibility protections. The intermediate state — fallbacks present,
Kawa still mounted but no longer reachable by default — is harmless by design.

## Closeout — what was preserved

**Verified present after removal, and asserted PRESENT by
`tests/test_kawa_product_path_removed.py` so a future zero-occurrences sweep fails
the test instead of destroying them:**

| Preserved | Where |
|---|---|
| Narrator erasure still erases historical Kawa records | `services/narrator_erasure.py:105` |
| Erasure-integrity count of on-disk Kawa files | `api/db.py` `kawa_seg_dir` |
| Migration 0003 — immutable, untouched | `db/migrations/0003_media_archive.sql` |
| `kawa_segment` media type for rows that already carry it | `services/media_archive/types.py` |
| Retired-language eval, which **rejects** Kawa vocabulary | `data/evals/sentence_diagram_cultural_context_cases_sd044_sd065.json` |
| Geographic `River` in the place-fragment anchor regex | `ui/hornelore1.0.html` `_LV80_PLACE_FRAG_ANCHOR_RX` |
| On-disk footprint reporting for `kawa/people` | `scripts/step6_ws_probe.py` |
| Research papers and archived Kawa work orders | `docs/references/`, `docs/archive/workorders-pre-pivot/` — **not** `Research/Kawa/`, which this row named until 2026-09-08 and which does not exist at HEAD |

**Narrator data: `DATA_DIR/kawa/` was never touched.** On this deployment the
directory **did not exist**, so the pre-removal manifest was empty and the boundary
was satisfied trivially *here*. That says nothing about other deployments, which is
exactly why the erasure-support code above is preserved rather than removed.

## Closeout — verification evidence

Interpreter **`python3` 3.10.12**. **9 tests across 2 suites, `OK`, ZERO skips.**

* `node --check` clean on all six changed JS files **and** both inline `<script>`
  blocks extracted from `hornelore1.0.html`;
* `compileall` clean across `scripts/` and `tests/`;
* **five mutations each make the negative test fail** — remounting the router,
  restoring a `chronology_river` option, re-injecting `kawaContext` into the memoir
  prompt, deleting the erasure line, and stripping `River` from the place regex —
  and it returns green when reverted. Three test regression, two test over-deletion.

**Pre-existing RED, not caused by this work order and deliberately not repaired
here:** `tests/test_profile_seed_reachability_map.py` pins the *exact line numbers*
of the `currentPass` writers and was **already stale at `3481d1a`** — a pristine
`git archive` of that commit reproduces the failure. Removal moved those lines
further while the writer set stayed byte-identical in content. Registered in
[`docs/BACKLOG.md`](../BACKLOG.md) §2.5.

**This is the first change in the repository sequence that intentionally touches
`server/` and `ui/`.** Blocks 1-3 of `WO-REPOSITORY-HYGIENE-01` held zero product
changes on purpose so that this one is reviewable on its own.

---

## Mission alignment

Life Map is the only navigation surface. Kawa / Memory River was retired as doctrine
on 2026-05-01 and the implementation stayed mounted for four months, contradicting the
principle in every document that described it. Removing it ends a dual metaphor that
confused both the model and the narrator, and it removes a second navigation surface a
narrator could land on by accident.

## Non-regression requirements

This WO MUST NOT:

- reduce narrator dignity — **a narrator whose stored view is `"river"` must land
  somewhere real, not on a blank pane**;
- introduce new `must_not_write` violations or system-tone outputs;
- regress the current locked baseline without explicit justification;
- expand operator surfaces into narrator UI;
- add detectors that duplicate existing signals;
- **delete any narrator data under `DATA_DIR/kawa/`**;
- **make historical narrator data uneraseable.**

## Lori impact (Tier 3)

Memoir prompt composition changes: the client currently appends a Kawa sentence to the
memoir prompt (`ui/js/app.js:5113-5131`). Response length, questions per turn, tone,
pacing and the narrator/operator boundary are otherwise untouched. Narrator-facing
change: the Memory River tab and popover disappear; anyone whose session state points at
them lands on Life Map.

---

## 1. The three findings that change the obvious plan

### 1.1 The default narrator view is `"river"`, and an invalid view fails SILENTLY

`ui/js/state.js:191` — `narratorView: "river"`.

`ui/js/app.js:975-976`:

```js
function lvNarratorShowView(view) {
  if (!["map", "photos", "memoir", "trips"].includes(view)) return;
```

**A bare `return`.** No error, no fallback, nothing rendered. The sole caller,
`app.js:2317`, is `lvNarratorShowView(lvNarratorCurrentView() || "map")` — and that
`|| "map"` does **not** save it, because `"river"` is truthy: it passes the `||`, fails
the `includes`, and the function returns having painted nothing.

**So the failure mode of getting this wrong is a blank narrator room, silently.**

**Required — both halves, not either:**

1. change the default to `"map"`;
2. **normalize at the consumption boundary**: anything not in
   `map | photos | memoir | trips` becomes `map`. That protects restored and persisted
   session state, not just new sessions.

### 1.2 THREE separate state fields need normalization, and they do not share a vocabulary

**Getting this wrong means implementing a fallback against the wrong field.** The three
are distinct, verified at `fc781426`:

| Field | Where | Values today | Retired → |
|---|---|---|---|
| **narrator view** | `state.js:191` `narratorView` | `river` · `map` · `photos` · `memoir` · `trips` | **`river` → `map`** |
| **interview mode** | `state.js:243` `kawaMode` | `chronological` · **`hybrid`** · **`kawa_reflection`** | **`hybrid`, `kawa_reflection` → `chronological`** |
| **memoir mode** | `state.js:247` `memoirMode`; Kawa `organizationMode` at `state.js:321` and `lori-kawa.js:22,29` | `chronology` · **`chronology_river`** · **`river_organized`** | **`chronology_river`, `river_organized` → `chronology`** |

**`hybrid` is Kawa-specific and is easy to miss.** `state.js:241` describes it as
*"chronological skeleton + selective Kawa follow-ups"*; `lori-kawa.js:203` treats
*"hybrid and kawa_reflection modes"* as one pair; `:224` triggers on it; `:254` reads
`window.KAWA_PROMPTS.kawa_hybrid_followups`; `:258` increments `hybridPromptsShown`; and
`interview.js:943` intercepts the question in *"hybrid/reflection modes"*.
**A narrator left on `hybrid` would keep receiving Kawa follow-ups after removal if the
fallback only handled `kawa_reflection`.**

Related state to clear or normalize alongside: `lastKawaMode` (`state.js:244`),
`lastKawaSegmentId` (`:246`), `kawaPromptCooldown` (`app.js:4116`, `:4205`), and the
`hybridPromptsShown` / `kawaSegmentsUsedInMemoir` metrics (`lori-kawa.js:24`).

**Removing the `<option value="chronology_river">` at `hornelore1.0.html:4044` is not
enough**, and `app.js:10572` branches on the mode. Deleting a selector entry while
leaving stored values unmapped reproduces §1.1's failure in the memoir surface.

### 1.3 Two health checks currently REQUIRE the Kawa surface

* `ui/js/ui-health-check.js:58` registers a `"river"` category, `:250` expects
  `lv80RiverBtn`, and `:610-617` reports **`"#kawaRiverPopover missing"` as a
  FAILURE**;
* `ui/js/session-health-monitor.js:72` matches `/Memory River/i`.

**These must change in the same commit.** Otherwise a correct removal turns the health
check red and reads as a regression.

---

## 2. What must NOT be removed

**Four things look like Kawa and are not archive candidates.** Removing any of them
converts a clean removal into a data or integrity defect.

| Keep | Why |
|---|---|
| `server/code/api/services/narrator_erasure.py:105` — `("kawa_segments", ("kawa", "people"))` | **Narrator erasure must still erase historical Kawa records.** The standing boundary is *do not delete `DATA_DIR/kawa/` during CODE removal* — it is not *stop erasing it when a narrator asks to be erased*. Removing this line orphans narrator data that no code path can then reach |
| `server/code/api/db.py:5778-5783` — counts `kawa_segments` | The erasure-integrity count. Same reasoning |
| `server/code/db/migrations/0003_media_archive.sql:202` — `'kawa_segment'` | **Migrations are immutable.** Never edit a landed migration |
| `server/code/services/media_archive/types.py:69` — `"kawa_segment"` | An accepted media-attachment type that **existing rows may already carry**. Dropping the vocabulary entry invalidates stored data |
| `data/evals/sentence_diagram_cultural_context_cases_sd044_sd065.json:11` — `retired_language: ["Kawa","river","rocks","driftwood","water flow"]` | This case **rejects** Kawa language. It becomes a stronger negative regression test after removal, not a leftover |

**One narrowing of an earlier claim.** The *prompt composer* is already Kawa-free —
`prompt_composer.py:5423-5426` records that `kawa_mode` is no longer emitted in
`runtime71` and that the LLM gets no Kawa directive even if the payload carries it.
**The server as a whole is not**: `/api/kawa/*`, the router mount, the store and the
projection are all still live. Do not restate the narrow fact as the broad one.

---

## 3. Removal surface

**Compatibility and fallbacks FIRST**, then client, then server, then tests. Landing the
fallbacks first means no intermediate state can strand a narrator.

**Client**

- `ui/hornelore1.0.html` — Memory River button `#lv80RiverBtn`, `#kawaRiverPopover`,
  the `chronology_river` `<option>` (`:4044`), the `lori-kawa.js` script tag
- `ui/js/lori-kawa.js` — delete
- `ui/js/api.js` — Kawa REST client helpers
- `ui/js/app.js` — state, preload, rendering, mode setters (`:10546`), the
  `chronology_river` branch (`:10572`), and **the memoir injection at `:5113-5131`**
- `ui/js/interview.js` — `maybeApplyKawaFollowup`, `normalizeKawaLanguageForUser`,
  `tickKawaPromptCooldown`, the WO-KAWA-UI-01A hooks (`:943-948`, `:2002`)
- `ui/js/state.js` — `narratorView` default, `kawaMode`, `memoirMode` /
  `organizationMode` retired values, `kawaPromptCooldown`
- `ui/css/lori80.css` — river styles
- `ui/js/session-loop.js` — the passive-Kawa comment

**Server**

- `server/code/api/main.py` — the import (`:144`) and `app.include_router(kawa.router)`
  (`:187`)
- `server/code/api/routers/kawa.py` — delete (four routes: `/api/kawa/list`,
  `/segment` GET + PUT, `/build`)
- `server/code/kawa_store.py`, `server/code/kawa_projection.py` — delete **only after
  confirming no non-Kawa consumer**
- `data/prompts/kawa_prompts.json` — delete the runtime prompt path

**Harnesses** — `scripts/run_john_baldy_master_check.py`, `scripts/step6_ws_probe.py`,
`scripts/ui/run_parent_session_readiness_harness.py`,
`scripts/ui/run_parent_session_rehearsal_harness.py` all reference Kawa; update rather
than assume.

---

## 4. Acceptance — all must hold

**Compatibility**

- [ ] **narrator view** — default changes to `"map"` **AND** any value not in
      `map | photos | memoir | trips` normalizes to `map` **at the consumption
      boundary**. Both halves; the default alone does not protect restored or persisted
      state
- [ ] **interview mode** — `hybrid` and `kawa_reflection` normalize to `chronological`
- [ ] **memoir mode** — `chronology_river` and `river_organized` normalize to
      `chronology`
- [ ] the three fields are normalized **against their own vocabularies** — no fallback
      maps a value onto a field it does not belong to
- [ ] existing `DATA_DIR/kawa/` files are **untouched**
- [ ] narrator erasure still **counts and erases** those files on an explicit erasure
- [ ] existing media rows carrying `kawa_segment` remain valid

**Product removal — nothing reachable**

- [ ] no Memory River button · no Kawa popover · no Kawa CSS or rendering
- [ ] no `lori-kawa.js` · no Kawa API client · no `/api/kawa/*` route · no router mount
- [ ] no Kawa store or projection product path · no `kawa_prompts.json` runtime path
- [ ] **no Kawa context entering memoir prompts**
- [ ] no selectable or reachable `chronology_river` / `river_organized`
- [ ] no preloading of Kawa segments

**Tests**

- [ ] health checks no longer require Memory River
- [ ] **negative structural test** proving the retired subsystem cannot silently return
- [ ] fallback tests, one per field: `"river" → "map"` · `hybrid` and
      `kawa_reflection` → `chronological` · `chronology_river` and `river_organized`
      → `chronology`
- [ ] a test proving narrator erasure still handles historical Kawa data
- [ ] the retired-language eval is preserved

**The completion test is NOT `grep -c kawa == 0`.** Hits are *supposed* to remain in
archived work orders, research citations, migration history, erasure and compatibility
support, the media type vocabulary for old rows, and the negative tests. **The measure is
zero reachable Kawa product path.**

---

## 5. Verification

Focused structural and unit verification, not the three-hour mutation gate — this removes
a retired subsystem rather than altering the guarded production invariants that gate
measures. **If removal turns out to change a load-bearing invariant, stop and surface it
before deciding whether a mutation family is warranted.**

Name the interpreter and report the skip count on every suite. Byte-compile the tracked
Python under `scripts/` and `tests/`; `node --check` the changed JS; confirm no broken
relative Markdown links; confirm `DATA_DIR/kawa/` is byte-identical before and after.
