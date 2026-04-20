# WO-EX-SPANTAG-01 — Two-pass span-tag extraction (evidence + bind)

**Author:** Claude (LOOP-01 R5.5 Phase 1 setup, post-r4i baseline lock)
**Date:** 2026-04-20
**Status:** ACTIVE — next execution spec. Pre-reqs satisfied: r4i locked, r4j disposition written, #82 memo written. Starts as soon as CLAUDE.md changelog entry lands.
**Depends on:** r4i baseline (locked). `HORNELORE_PROMPTSHRINK=1` available in-tree (flag off by default; may be re-enabled if Pass 1 input budget needs relief).
**Blocks:** Pillar 2 (entity-role binding) and R5.5 citation grounding UI — both consume the `sourceSpan` primitive this WO produces.

This spec supersedes the original single-pass fieldPath-as-class stub. Rationale for the rewrite: the single-pass design conflated *evidence spotting* with *schema binding* and made the LLM's job harder, not easier. The two-pass split below lets Pass 1 be something a zero-shot 8B can actually do, and pushes schema knowledge into Pass 2 where it belongs.

---

## Problem framing

Three compounding problems on the stubborn frontier:

1. **No provenance.** Every extracted item today is `{fieldPath, value, confidence}` with no structural link to source text. We cannot cheaply answer "which sentence did `family.spouse.dateOfBirth=1939` come from?" and therefore cannot cheaply distinguish "hallucinated from nothing" from "real evidence, wrong routing". The `case_012` r4j regression is exactly this failure mode.
2. **Shape, not value, is the dominant error.** On the stubborn-15, rails cannot repair field_path_mismatch and schema_gap after the fact because the LLM emitted the wrong shape (wrong field path, or missing field entirely). Rails edit values; they do not restructure emissions.
3. **Truncation-dominated frontier.** r4j stability: 15 / 15 stubborn cases truncated in at least one run. Any single-pass contract that re-emits the narrator reply inline (Kiwi-LLaMA style full-echo) would *worsen* truncation. We need a contract whose output budget stays small even on long inputs.

## Design in one paragraph

Two passes, one model, same session.

**Pass 1 — evidence-only tagging.** LLM is given the narrator reply and a tiny natural-language tag inventory (see below). It emits a JSON array of tagged spans: `{type, text, start, end, polarity}`. No schema mentioned. No dotted field paths. Output is a small array even on long replies.

**Pass 2 — bind and project.** LLM is given Pass 1's tag array, the question-bank `extract_priority` list for the current sub_topic, the relevant slice of the schema catalog, and a short binding instruction. It emits `{fieldPath, value, confidence, sourceSpan: {start, end}, sourceTagIds: [...]}` for each write. Normalization and write-gating happen here.

## Pass 1 — tag inventory

Ten tags. Natural-language names. No schema leakage. Stable ordering in the prompt.

| Tag | Covers |
|---|---|
| `person` | Any named or role-referenced human (including the narrator self-reference) |
| `relation_cue` | Relational verbs/nouns binding two persons (`married`, `son of`, `my sister`, `adopted`) |
| `date_text` | Anything that reads as a date or date range, including holidays, years, ages, and imprecise phrasings (`the fall of '42`, `Christmas Eve`, `when I was nineteen`) |
| `place` | Towns, addresses, geographic regions, named buildings/farms |
| `organization` | Churches, companies, schools, military units, clubs |
| `role_or_job` | Occupations, titles, duties (`pastor`, `homemaker`, `sergeant`) |
| `event_phrase` | Bounded real-world events (`the wedding`, `the fire`, `when we moved`) |
| `object` | Physically specific objects when they anchor a claim (`the red tractor`, `Mom's ring`) |
| `uncertainty_cue` | Narrator hedges (`I think`, `maybe`, `around`, `I'm not sure but`) |
| `quantity_or_ordinal` | Numerals and ordinals carrying meaning (`three kids`, `the second wife`, `nineteen`) |

Each Pass 1 span carries a `polarity` field: `asserted` (default), `negated` (`we never went to church`), `hypothetical` (`if I had gone`). Polarity is cheap for the LLM to tag and critical for Pass 2 to avoid writing negated claims.

Pass 1 output shape (illustrative):

```json
{
  "tags": [
    {"id": "t0", "type": "person", "text": "Janice Josephine Zarr", "start": 10, "end": 32, "polarity": "asserted"},
    {"id": "t1", "type": "relation_cue", "text": "married", "start": 2, "end": 9, "polarity": "asserted"},
    {"id": "t2", "type": "date_text", "text": "October 10th, 1959", "start": 36, "end": 54, "polarity": "asserted"},
    {"id": "t3", "type": "quantity_or_ordinal", "text": "nineteen", "start": 62, "end": 70, "polarity": "asserted"},
    {"id": "t4", "type": "quantity_or_ordinal", "text": "twenty", "start": 82, "end": 88, "polarity": "asserted"}
  ]
}
```

## Pass 2 — bind and project

Inputs to Pass 2:

- Pass 1 tag array.
- The narrator reply text (for Pass 2 to quote/verify; not required for the model to re-emit).
- `extract_priority` list from the active sub_topic (e.g. `["family.spouse", "family.marriageDate"]`).
- The relevant slice of the canonical catalog (not the whole 108-field list — scoped per sub_topic via existing projection map).
- Narrator identity (for subject filtering).

Pass 2 output shape:

```json
{
  "writes": [
    {
      "fieldPath": "family.spouse.firstName", "value": "Janice", "confidence": 0.95,
      "sourceSpan": {"start": 10, "end": 16}, "sourceTagIds": ["t0"]
    },
    {
      "fieldPath": "family.marriageDate", "value": "1959-10-10", "confidence": 0.9,
      "sourceSpan": {"start": 36, "end": 54}, "sourceTagIds": ["t1", "t2"],
      "normalization": {"raw": "October 10th, 1959", "normalized": "1959-10-10"}
    }
  ],
  "no_write": [
    {
      "reason": "age_at_event_not_a_dob",
      "sourceTagIds": ["t3", "t4"]
    }
  ]
}
```

`no_write` with explicit `reason` is the Pass 2 answer to the `case_012` r4j regression — the model has to *explicitly refuse* to turn "she was twenty" into `spouse.dateOfBirth=1939`, and that refusal is recorded.

## Scope (in / out)

**In scope:**

- New Pass 1 prompt builder in `extract.py`: `_build_spantag_pass1_prompt`.
- New Pass 2 prompt builder: `_build_spantag_pass2_prompt`.
- Pass 1 parser: tolerant JSON parser that extracts the `tags` array, with a permissive regex fallback for malformed Llama output (missing commas, trailing text, duplicated keys).
- Pass 2 parser: produces the current `{fieldPath, value, confidence}` shape plus `sourceSpan` and `sourceTagIds`.
- Projection: Pass 2 output is down-projected to the legacy shape *before* the guardrail stack sees it. Rails remain unchanged. `sourceSpan` rides alongside the write but is stripped at the eval-scorer boundary by default (gated by `--with-source-spans`).
- Feature flag: `HORNELORE_SPANTAG=1` — off by default. Off = legacy single-pass. On = two-pass with fallback to legacy on any parse failure.
- New log tags: `[extract][spantag][pass1]`, `[extract][spantag][pass2]`, `[extract][spantag][fallback]`.
- Targeted first-pack eval: the **15 stubborn cases** plus a control slice of 20 random contract cases.

**Out of scope:**

- Model swap (Hermes / Qwen). Deferred; see appendix.
- Changing the catalog, schema, or `extract_priority` lists. #81 stays measured-not-adopted.
- Wiring `sourceSpan` into the review UI. That's R5.5 Phase 2.
- Repairing entity-role binding (#68 / Pillar 2). SPANTAG produces the *substrate* for that work, not the fix.
- Rewriting the guardrail stack. Pass 2 plus the existing rails is the v1.

## Goals (concrete, measurable)

1. **Pass 1 parse success ≥ 95%** on the 15-case stubborn frontier and ≥ 95% on the 20-case control slice. Measured over 3 runs per case.
2. **Pass 2 source-offset coverage ≥ 80%** — fraction of emitted writes whose `sourceSpan` is non-empty and whose substring at `[start, end]` appears in the narrator reply literally (or under a normalization known to Pass 2, tracked via the `normalization.raw` field).
3. **No regression vs r4i baseline on contract subsets.** v3 ≥ 34/62, v2 ≥ 31/62, must_not_write = 0.0%. Flag ships on default only if this holds.
4. **Stubborn-15 movement, truncation-aware.** First-pack success criterion: **either** ≥ 3 of the 15 stubborn cases flip stable_pass across 3 runs, **or** stubborn-pack truncation rate drops from 15/15 to ≤ 8/15 (i.e. Pass 1+Pass 2 output budget is materially smaller than legacy single-pass on the same inputs).
5. **Truncation as a required metric.** Every eval run under SPANTAG must report `truncation_rate` (fraction of cases where VRAM-GUARD fired on at least one pass) alongside pass rate. Truncation is first-class now.

## Target pack (first eval)

Fixed 15 stubborn cases, same as the existing stubborn-pack wrapper:

`case_008, case_009, case_017, case_018, case_053, case_075, case_080, case_081, case_082, case_083, case_084, case_085, case_086, case_087, case_088`

Plus a 20-case control slice drawn from `contract tiny clean` + `contract small clean` (to confirm Pass 2 produces legacy-shape writes byte-identical to r4i on cases that are already passing — this is the no-regression guard).

## Risks and mitigations

- **Llama 3.1 8B Pass 1 tag recall.** The ten-tag inventory is designed to be broad and NL-named to reduce instruction sensitivity, but recall on `uncertainty_cue` and `polarity` is likely the weakest surface. Mitigation: Pass 2 is robust to missing polarity (treats absence as `asserted`), and missing `uncertainty_cue` downgrades confidence but does not change the write/no-write decision alone.
- **Pass 1 span offset drift.** Llama may emit `start`/`end` values that don't match the substring. Mitigation: Pass 1 parser re-locates each span by substring-search against the narrator reply and corrects offsets; if substring is absent, the tag is dropped and logged `[extract][spantag][pass1][drop_orphan_tag]`. This is the substring-invariant-parser discipline.
- **Pass 2 schema flooding.** Sending the full 108-field catalog to Pass 2 is wasteful. Mitigation: the existing projection map already produces sub_topic-scoped field lists; Pass 2 receives only those. If PROMPTSHRINK-style topic-scoping of few-shots is needed for Pass 2, we re-enable `HORNELORE_PROMPTSHRINK=1` in combination (the flag stays in-tree for this reason).
- **Two calls = two latency budgets.** RTX 50-series is fast locally but two sequential LLM calls per turn will measurably lift latency. Mitigation: Pass 1 output is cacheable per (narrator_id, turn_id, reply_hash). Pass 2 reruns are free on the same narrator turn if `extract_priority` changes. Measure p95 end-to-end; gate default-on behind p95 ≤ 1.8× r4i.
- **Fallback coverage.** Any Pass 1 or Pass 2 parse failure falls back to the legacy `_extract_via_singlepass` path. Measured at log-tag `[extract][spantag][fallback]`. Target fallback rate ≤ 5% on the 104-case master.

## Measurement plan

Captured in `docs/reports/WO-EX-SPANTAG-01_REPORT.md` after the first eval run (provisional tag `r5a-spantag`):

1. Pass 1 parse success per case (count, % of runs).
2. Pass 2 parse success per case.
3. Fallback activation rate (% of all calls).
4. `sourceSpan` coverage of written items.
5. Topline pass rate, v3, v2, must_not_write, failure-category breakdown.
6. Per-bucket deltas: `contract`, `extract_multiple`, `extract_compound`, `dense_truth`, `large chunk`.
7. Stubborn-pack stability: stable_pass / stable_fail / unstable counts; **truncation rate as first-class metric**.
8. Latency: mean + p95 per turn, before/after. Separately Pass 1 and Pass 2.

## Implementation plan (commits)

1. **Commit 1 — Pass 1 scaffold.** `_build_spantag_pass1_prompt`, `_parse_spantag_pass1`, `_relocate_spans`. Unit tests for parser on hand-written Pass 1 outputs (well-formed, malformed, orphan spans, polarity absent). Flag off; no behavior change live.
2. **Commit 2 — Pass 2 scaffold.** `_build_spantag_pass2_prompt`, `_parse_spantag_pass2`. Unit tests.
3. **Commit 3 — Pipeline wiring.** `_extract_via_spantag(...)` function that runs Pass 1 → Pass 2 → down-projects to legacy shape. `_extract_via_singlepass` unchanged; flag decides which to call.
4. **Commit 4 — Eval harness additions.** Extend `run_stubborn_pack_eval.py` to report `truncation_rate` in the master block; add `--spantag` pass-through flag that sets `HORNELORE_SPANTAG=1` for the child eval.
5. **Commit 5 — First eval run + WO report.** `r5a-spantag` master + stubborn pack. Decide: ship-default / keep-flag / revert. Report in the standard post-eval audit block (extended with truncation_rate).
6. **(Conditional) Commit 6 — Re-enable PROMPTSHRINK pairing.** Only if Pass 2 input budget is the constraint; not on the critical path for commit 5.

Each commit independently reversible. Feature flag lets Chris A/B at runtime without code changes.

## Acceptance gate for default-on

Default-on requires **all** of:

- Contract guards held: v3 ≥ 34/62, v2 ≥ 31/62, must_not_write = 0.0%.
- Stubborn-pack: ≥ 3 stable_pass flips **or** truncation rate drops to ≤ 8/15.
- Fallback rate ≤ 5% on the full master.
- p95 end-to-end latency ≤ 1.8× r4i.
- `sourceSpan` coverage ≥ 80% of emitted writes.

If any fails, flag stays off-by-default and we iterate. If all hold, SPANTAG becomes default-on, the flag flips, and #82 / R5.5 Pillar 2 begin.

## Related work

- Hu et al., *Information extraction from clinical notes...*, JAMIA 2026 (doi:10.1093/jamia/ocaf213) — Kiwi-LLaMA `<span class=...>` contract. We borrow the substring-invariant-parser discipline, not the full-echo output shape.
- `docs/reports/loop01_research_synthesis.md` — SPANTAG provenance rationale, UniversalNER / GoLLIE / pointer-network lineage, KORIE staged-pipeline context.
- `WO-EX-PROMPTSHRINK-01_Spec.md` Disposition — why PROMPTSHRINK is measured-not-adopted and why it may re-enter via SPANTAG Pass 2.

## Appendix A — Why Hermes is sequenced after SPANTAG

Hermes 3 (and any Qwen-family A/B) requires ChatML chat-template porting from our current Llama-3 template. That's a one-time tax with low technical risk but meaningful harness churn. Running that A/B before SPANTAG means measuring two variables at once (model + contract) and we lose the ability to attribute any movement cleanly.

After SPANTAG lands with a stable ship/no-ship decision on Llama 3.1 8B:

- If SPANTAG shipped and is default-on: Hermes A/B becomes "does the same two-pass contract do better on Hermes?" — one variable at a time.
- If SPANTAG did not ship: Hermes A/B becomes "does any single-pass model do better on legacy contract?" — also one variable.

Either way, sequencing Hermes behind SPANTAG cleans up the attribution. Prerequisite: chat-template parity test harness (small, separate WO, pre-requisite for the Hermes A/B but not for SPANTAG).

## Appendix B — Conditional KORIE staged-pipeline note

KORIE-style staged pipelines (detection → OCR → IE) are a real option for Hornelore if we end up operating on document photos (letters, journals, census scans) rather than narrator transcripts. **Gate:** only consider this lane if SPANTAG Phase 1 delivers ≥ 20% topline lift **or** closes ≥ 3 of the stubborn 15. Below those thresholds, staged-pipeline infrastructure cost is not justified at our current scale. Document photos are a product-roadmap question, not an extraction-pipeline question, and should be revisited at R6 or later.

## Revision history

- 2026-04-19: Initial single-pass stub (`<span class='fieldPath'>value</span>`). Deferred behind r4i + #81.
- 2026-04-20: **Full rewrite to two-pass (evidence + bind).** Single-pass design superseded. Written against r4i baseline lock and r4j truncation-dominated finding. First target pack = stubborn 15. Truncation promoted to first-class metric. Appendices A (Hermes sequencing) and B (KORIE conditional lane) added.
