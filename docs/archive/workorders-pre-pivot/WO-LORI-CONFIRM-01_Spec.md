# WO-LORI-CONFIRM-01 — Interview-engine confirm pass + kinship skeleton (canon-first)

**Author:** Claude (LOOP-01 R5.5, post-r5e1 45-case rundown)
**Date:** 2026-04-21
**Status:** SPEC PARKED. Implementation gated behind (a) SECTION-EFFECT-01 Phase 3 signoff (#95), and (b) WO-EX-SPANTAG-01 default-on decision. Three-agent convergence (Chris / Claude / ChatGPT, 2026-04-21) on this sequencing: if confirm-pass lands before extractor-side accountability work is closed, it will blur the attribution between *extractor failed*, *elicitation was insufficient*, and *confirmation resolved ambiguity later*.
**Depends on:** (1) SECTION-EFFECT Phase 3 causal matrix closed. (2) SPANTAG ship/no-ship decision — confirm-pass is complementary to SPANTAG, not a replacement. (3) STT-LIVE-02 plumbing in-tree (already landed 2026-04-20 commit `WO-STT-LIVE-02_REPORT.md`): `ExtractedItem.needs_confirmation`, `ExtractedItem.confirmation_reason`, `ExtractFieldsResponse.clarification_required: List[Dict]`, and `writeMode=suggest_only` are all present and byte-stable on the r5a+ baseline.
**Blocks:** Nothing on the R5.5 extractor roadmap. This is product-lane work, orthogonal to Pillars 1–2.

This spec is a **parked pilot**, not a full system feature. The rationale for parking rather than scheduling: the r5e1 master shows 45 / 104 failing on the extractor-only axis, and three agents converged that a meaningful slice of those (birth-order arithmetic, parent/sibling relation tags, date-range preference) are not best solved inside the extractor at all — they're interview-elicitation problems with an extractor burden piled on top. But we should not let that realization short-circuit the extractor accountability work still in flight.

---

## Problem framing

The extractor is asked to do two structurally different jobs on the same pass:

1. **Harvest rich narrative prose** — life events, motifs, relationships, place-and-era texture. The 8B LLM does this well when prompted loosely.
2. **Resolve brittle scalars** — a single integer for `personal.birthOrder`, a two-valued token (`older` / `younger`) for `siblings.birthOrder`, a canonical relation label (`mother` / `father`) for `parents.relation`, a normalized date range. The LLM does this unreliably because the arithmetic (e.g. "middle of three → 2") and canonical-form selection are not what narrative-turn prompting optimizes for.

The r5e1 rundown evidence (see `docs/reports/FAILING_CASES_r5e1_RUNDOWN.md`):

- **Birth-order arithmetic cluster** (cases 002, 014, 024, 028, 031 and others in the `school_years` band, 24 / 45 failures): narrator says *"middle child"* or *"youngest of three"* → extractor emits `siblings.birthOrder='youngest'` when scorer wants `'older'` / `'younger'`, and drops `personal.birthOrder` entirely.
- **Relation-tag drops**: `parents.relation='mother'` frequently missing when the reply gives names without explicit role ("It was my mom Janice and my dad Kent" extracts names but not relations, or vice versa).
- **Date-range preference**: case class where narrator says *"twenty-five years"* and scorer wants an explicit `1997–2026`. Phase 3 Fix C (prompt rule) narrowed but did not eliminate.
- **Parent-detail → narrator-field attribution** (cases 035, 093): narrator describes a parent's schooling in a faith turn → emission lands on `education.schooling` (narrator) or `parents.education`. ATTRIBUTION-BOUNDARY rule on r5e2 is the extractor-side fix; confirmation would be the elicitation-side fix.

Across these classes, the common shape is *the narrator's reply is ambiguous or compressed in a way the extractor can't reliably decompress*. More prompt-massage buys diminishing returns. A short targeted follow-up question from Lori would resolve each case in one turn with high confidence.

## Design in one paragraph

Two complementary interview-engine features sharing the same plumbing:

**(A) Kinship skeleton block — canon-first onboarding.** At the start of a new narrator's interview, before narrative flow begins, Lori runs a short structured block that establishes the family shape: mother and father names + relation tags, siblings with birth-order, spouse, children. The answers populate canon deterministically. All subsequent narrative turns are extracted *against* a known canon rather than *into* an empty canon — the extractor's entity-binding problem gets massively easier when `parents.firstName=Janice` and `parents.relation=mother` are already written facts before the prose arrives.

**(B) Confirm pass — reactive scalar resolution.** During narrative flow, the extractor stages flaky-scalar writes as `writeMode=suggest_only` + `needs_confirmation=True` instead of committing. At section boundaries (not per-turn — see interview-feel guardrails below), Lori fires short directed questions from a confirmation bank keyed to the staged-debt fields. Confirmed answers get promoted to `write`; unconfirmed stay `suggest_only` and are surfaced to the user in the canon view as pending.

Both features use the same three pieces of plumbing: `writeMode=suggest_only`, `needs_confirmation`, and `clarification_required` — all already in-tree from STT-LIVE-02. What this WO adds is the **dispatcher logic** (when to fire a confirm / when to run the skeleton), the **confirmation banks** (the actual micro-flow prompt sets keyed to field paths), and the **section-boundary batching** (so Lori doesn't interrupt narrative every turn).

## Pilot scope — four fields only

Deliberately narrow. The converged list:

| Field path | Confirmation micro-flow (sketch) |
|---|---|
| `personal.birthOrder` | "How many children were in your family?" → "What number were you in that lineup?" |
| `siblings.birthOrder` (per-sibling) | "Was [NAME] older or younger than you?" |
| `parents.relation` | "And [NAME] — was that your mother or your father?" (when names were harvested without roles) |
| Date-range fields (`*.yearsActive`, `*.dateRange`, `*.servicePeriod`) | "When you say twenty-five years, was that roughly [YEAR_A] to [YEAR_B]?" |

Not in pilot: pets, narrator-schooling, marriage anchors, children DOBs, kinship-skeleton expansions beyond mother/father/siblings/spouse/children. These are documented below as follow-ons if the pilot succeeds.

## Kinship skeleton block (Feature A)

Fires once at narrator onboarding, before first narrative turn. Deterministic sequence:

1. Mother: "Let's start with your family. What was your mother's name?" → writes `parents.firstName` + `parents.relation='mother'`.
2. Father: "And your father's name?" → writes second `parents.firstName` + `parents.relation='father'`.
3. Siblings roster: "Did you have any brothers or sisters growing up?" (yes path → "Tell me their names and whether they were older or younger than you.") → writes `siblings.firstName[]` + `siblings.birthOrder[]`.
4. Narrator's spot: "And where did you fall — oldest, youngest, or somewhere in between?" → writes `personal.birthOrder` as integer.
5. Spouse (optional, asked only if the narrator's era in life-map is `early_adulthood` or later): "Are you or were you married?" → writes `family.spouse.firstName`.
6. Children (optional, same era gate): "How many children did you have?" → enumerates `family.children.firstName[]`.

All six steps are skippable by the narrator ("I'd rather get to the stories"). Skipped fields stay null and are available for narrative-pass extraction as they normally would be. Completed fields are written as canon **before** the first narrative turn, so the extractor's catchment knows them.

**Canon-building angle.** Chris's framing: *"Lori can well ask interview style questions with a new narrator to better build an overall product/helpful questionnaire that is canon."* The skeleton block is not just accuracy hygiene — it produces the canonical template JSON (`templateSource` in the question bank) that currently has to be hand-authored per narrator. New-narrator onboarding yields a machine-populated canon for free.

## Confirm pass (Feature B)

Fires mid-interview at section boundaries, when staged-suggest scalar debt exists.

**Dispatcher logic (first cut — deterministic).** After the last question in a `subTopic` has been asked:

1. Scan the canon diff for the section: which paths were staged as `suggest_only` + `needs_confirmation=True`?
2. If any of the four pilot fields are staged, fire their confirmation micro-flow in sequence.
3. Cap at 2 confirms per section boundary — if more staged debt exists, log it but let it carry forward (prevents interview from turning into an interrogation).
4. After confirms resolve, promote confirmed writes to `writeMode=write`. Unconfirmed staging stays.

**Dispatcher logic (future — LLM-dispatched).** Deferred. A small model would decide whether the narrative texture justifies the interruption. Too much surface area for the pilot; revisit only if the deterministic lane proves too rigid.

**Interview-feel guardrails.**

- **Section-boundary batching, not per-turn.** Confirms fire only when the narrator has visibly wrapped a subTopic (last question asked + narrator response received), not mid-narrative.
- **Max 2 confirms per section.** Hard cap.
- **Narrator can skip.** "Can we come back to that?" exits the confirm sequence, leaves the staging in place, and returns to narrative.
- **No confirm if the narrative pass wrote `writeMode=write` with `confidence >= 0.8`.** Don't confirm what the extractor is already sure about.

## Plumbing reuse (no new primitives needed)

Everything the pilot needs is already in-tree from WO-STT-LIVE-02 (landed 2026-04-20):

| Piece | Current use | Pilot reuse |
|---|---|---|
| `writeMode=suggest_only` | STT low-confidence downgrade | Staged-scalar downgrade |
| `ExtractedItem.needs_confirmation` | STT fragile-field guard | Staged-scalar flag |
| `ExtractedItem.confirmation_reason` | STT confidence explanation | Scalar-ambiguity explanation |
| `ExtractFieldsResponse.clarification_required` | STT dispatches clarification | Confirm-pass dispatches follow-up |
| TURNSCOPE `current_target_path` | Narrows `allowed_branches` on targeted questions | Locks branch on confirm questions |
| SECTION-EFFECT `current_era / current_pass / current_mode` | Stage context for extraction | Gates spouse/children skeleton steps on era ≥ `early_adulthood` |

The only net-new surface area is the confirmation banks (static JSON, per-field question sets) and the section-boundary dispatcher hook in `ui/js/interview.js`.

## Measurement — separate lane from extractor baseline

Critical point, flagged by ChatGPT in convergence and agreed by Chris:

The confirm-pass must be measured *separately* from the raw extractor baseline. Running confirm-pass cases through the existing master eval would pollute the attribution: we would no longer know whether a pass came from the extractor getting better or from confirmation resolving ambiguity. Two implications:

1. **Existing master eval stays single-turn.** `r5e2`, `r5f`, etc. continue to measure the extractor in isolation.
2. **New eval surface: multi-turn confirm-pass cases.** Schema extension to `question_bank_extraction_cases.json` — a case becomes a **list of turns** (Lori prompt + narrator reply pairs) rather than a single pair. Initial pilot eval targets the 12–15 failing cases in the r5e1 rundown that fall in the four pilot-field classes. Each case runs twice: once as current single-turn (baseline fail), once as multi-turn with confirm-pass active (expected pass). Deltas attribute directly to the confirm mechanism.

**Cost of the multi-turn eval surface.** Real. The harness (`scripts/run_question_bank_extraction_eval.py`) is built for single-turn. Extending to multi-turn requires: (a) case schema bump, (b) harness-side turn sequencing, (c) canon-diff between turns so we can measure what each turn contributed. Estimated effort: 1–2 days. **Not included in the pilot implementation**; the multi-turn harness is its own WO (likely WO-EVAL-MULTITURN-01 when drafted).

Until the multi-turn harness exists, pilot validation is **qualitative only** — hand-run a small set of cases through the interview UI with confirm-pass active, inspect the canon diff, verify the four pilot fields land clean. Not benchmark-measured.

## Out of scope (follow-ons if pilot succeeds)

Parked for future WOs, do not fold into this pilot:

- **Pets micro-flow** (cases 025, 045, 046, 066) — target salience issue, worth its own structured follow-up: *"What was the animal? What was its name? Did it feel like yours or the family's?"*
- **Narrator-only schooling anchors** (cases 064, 072 and related) — fragile even with explicit answers.
- **Marriage anchors** — date, place, spouse name as a structured block.
- **Children enumeration beyond count** — names, DOBs, birthplaces per-child.
- **Kinship skeleton extensions** — grandparents, great-grandparents, extended family. Only if the 4-step skeleton proves its weight.

## Sequencing and go/no-go

**Sequencing (non-negotiable):**

1. SECTION-EFFECT-01 Phase 3 (#95) closes.
2. SPANTAG (#90) implementation lands and reaches a default-on or default-off call.
3. **Then** this WO opens for implementation.

The reason is honest attribution, not caution for its own sake. If confirm-pass lands first, every future extractor regression on the affected fields could be explained away as "confirm-pass will catch it" — and extractor accountability erodes. Extractor lane first, interview lane second.

**Go/no-go on opening implementation:** decided after SPANTAG signoff. If SPANTAG materially moves the 4 pilot-field classes (especially birth-order arithmetic via evidence-then-bind), the pilot's value drops and may re-park indefinitely. If SPANTAG doesn't move those classes, this pilot is the natural next lever.

## Risks and strain points

- **Dispatcher rigidity.** Deterministic dispatcher is testable but feels scripted. Mitigation: narrow pilot scope; accept scriptedness in v1.
- **Narrator interview fatigue.** Too many confirms break oral-history texture. Mitigation: max-2-per-section cap + skippable skeleton.
- **Eval-surface debt.** Multi-turn harness is its own build. Mitigation: qualitative validation first, benchmark later.
- **Canon collision with extractor-pass writes.** If narrative pass writes `parents.firstName=Janice` and skeleton has already written it, reconciliation rules needed. Mitigation: canon-first wins on exact match; narrative extracts log `already_in_canon` instead of writing.
- **Interview state divergence between Cowork/live session and eval harness.** Addressed by keeping the multi-turn eval a separate lane.

## Deliverables (when implementation opens)

1. `data/interview/kinship_skeleton.json` — ordered question-set for Feature A.
2. `data/interview/confirmation_banks/{birthOrder,siblingsBirthOrder,parentsRelation,dateRange}.json` — per-field micro-flows for Feature B.
3. `ui/js/interview.js` — skeleton dispatcher at session start, confirm dispatcher at section boundaries.
4. `server/code/api/routers/extract.py` — lean hook to stamp `needs_confirmation=True` on the 4 pilot fields when `writeMode=suggest_only` is assigned (already exists for STT-LIVE; extend catchment).
5. `docs/reports/WO-LORI-CONFIRM-01_PILOT_REPORT.md` — qualitative validation on 12–15 pilot cases, per-field before/after canon diffs.

Multi-turn benchmark eval is **not** a deliverable of this WO. It's tracked as a separate parked spec (WO-EVAL-MULTITURN-01, to be drafted).

---

## Changelog

- 2026-04-21: Created as parked spec following three-agent convergence (Chris / Claude / ChatGPT) on the r5e1 rundown. Scope pinned to 4 fields + kinship skeleton onboarding. Sequenced behind SECTION-EFFECT Phase 3 and SPANTAG decision.
