# WO-EX-SPANTAG-01 — Full execution pack (Commits 3 → 5)

**Author:** Claude (LOOP-01 R5.5, overnight pack, 2026-04-21)
**Status:** DRAFT — promotes the existing design spec (`WO-EX-SPANTAG-01_Spec.md`, last revised 2026-04-20) to a full work order with concrete commit-by-commit execution, integrating r5e1/r5e2 lessons and the four failure clusters from `docs/reports/FAILURE_CLUSTERS_r5e1.md`.
**Tasks this pack covers:** remaining SPANTAG implementation — pipeline wiring (Commit 3), eval harness additions (Commit 4), first eval + decision (Commit 5). Commits 1 (Pass 1 scaffold) and 2 (Pass 2 scaffold) are already landed.
**Blocks:** WO-EX-SECTION-EFFECT-01 Phase 3 must be **reportable** (not necessarily adopted) before Commit 5 eval, so SPANTAG's measurement #10 has a citable source. Phase 3 WO sits at `WO-EX-SECTION-EFFECT-01_PHASE3_WO.md`.
**Does not block:** live r5e1 floor. All SPANTAG activity rides behind `HORNELORE_SPANTAG=1`, off by default. Default byte-stability with r5e1 is a Commit 3 hard requirement.

---

## 1. What this WO is, and what it is not

### Is

- The execution pack for finishing SPANTAG Phase 1.
- A concrete commit-by-commit instruction set with exact files, LOC references, acceptance criteria per commit, and a rollback plan per commit.
- Integration of two new inputs the parent spec did not have:
  - r5e2 rejection lesson — a single well-intentioned prompt rule can friendly-fire on the very class it meant to protect (case_075).
  - `FAILURE_CLUSTERS_r5e1.md` target packs — SPANTAG's case pack is now aligned with the cluster doc's Pack 2 (attribution) and gets a clean "this is not our lane" callout against Packs 1 / 3 / 4.

### Is not

- A redesign. The two-pass (evidence → bind) contract, the 10-tag inventory, the subject-beats-section rule, the dual-path emission, and the feature flag are all unchanged from the parent spec.
- A prompt-engineering pass. Prompt templates are sketched in §5 but the fine-tuning of example counts / wording is Commit 3 work with the parent spec as the controlling doc.
- A replacement for `WO-EX-SPANTAG-01_Spec.md`. That spec remains the design-authority document. This file is the operational pack sitting underneath it.

---

## 2. State of the tree

Already landed:

- `_build_spantag_pass1_prompt` at `server/code/api/routers/extract.py` L2545 — prompt builder, 10-tag inventory, schema-blind.
- `_parse_spantag_pass1` at L2631 — tolerant JSON parser, substring-search offset relocation, orphan-tag drop logging.
- `_SPANTAG_TAG_TYPES` and `_SPANTAG_POLARITY_VALUES` constants at L2526 / L2540.
- `_build_spantag_pass2_prompt` at L2974 — Pass 2 prompt builder, consumes Pass 1 tags + controlled priors.
- `_parse_spantag_pass2` at L3131 — Pass 2 output parser.
- `HORNELORE_SPANTAG` env-flag shape agreed, **not yet wired**.

Not yet landed (this WO's scope):

- `_extract_via_spantag(...)` pipeline wiring function.
- `_spantag_enabled()` flag check.
- Flag-dispatched dispatch inside `_extract_via_llm` (which currently only dispatches legacy-vs-TWOPASS, not SPANTAG).
- Eval harness additions (truncation_rate, spantag flag pass-through, dual-path primary-pick metric).
- First eval run + decision.

The existing `_extract_via_twopass` (L1790+) is a **different lane** (WO-EX-TWOPASS-01, flag `HORNELORE_TWOPASS_EXTRACT`). Do not merge it with SPANTAG. Two lanes, two flags, two fallbacks — by design.

---

## 3. Hard lessons to wire in from r5e1 / r5e2

### Lesson 1 — friendly-fire is the default, not the exception

r5e2 adopted a well-argued ATTRIBUTION-BOUNDARY prompt rule. It hit its named targets (case_093 0.70 → 0.90, case_005 0.00 → 1.00) and correctly cleared mnw from 2 → 0. It also regressed case_075 (1.00 → 0.00) — *the rule's own target class*, mother_stories. Net: -3 vs r5e1. **A rule cannot claim to protect a class if it can't pass that class's own gold-label cases.**

**SPANTAG anti-friendly-fire discipline for this WO:**

- Commit 5 eval must include a **no-regression guard on the rule's own target class.** That means: on the primary sub-pack (case_008/009/018/082 — dual-answer-defensible), we require ≥ 3/4 flip to stable_pass **AND** 0/4 regress from baseline pass to new fail. A "new pass but new fail" trade is rejection, not acceptance.
- The 20-case control slice from the parent spec §Target pack is **also** read as a friendly-fire guard, not only a general regression guard. If any control case regresses (r5e1 pass → SPANTAG fail) **and** the failure mode is novel (not a known r5e1 stochasticity), that's a single-case veto.
- Any Pass 2 prompt rule added during Commit 3 that names a cluster (ownership, attribution, etc.) gets a 3-case smoke probe on the rule's own target class before the rule ships. Pattern: `python scripts/run_question_bank_extraction_eval.py --cases <3-case-list> --runs 3`.

### Lesson 2 — mnw floor is honest

r5e1 baseline mnw = 2 (case_035, case_093). We decided those two are the known cost of the active floor. **SPANTAG must not worsen mnw.** Commit 5 gate: mnw ≤ 2, same two offenders or fewer, no new mnw cases.

### Lesson 3 — the real fix for attribution is elicitation-side

`WO-LORI-CONFIRM-01_Spec.md` parks the right long-term answer for the attribution class: interview-engine confirm pass + kinship skeleton. SPANTAG's subject-beats-section rule is a **prompt-side partial** for the same problem. Implication for this WO: we do not claim SPANTAG closes the attribution class. We claim it should flip ≥ 3/4 of the dual-answer sub-pack on dual-path emission + scorer `alt_defensible_paths`, and that case_035 / case_093 stay as mnw offenders until WO-LORI-CONFIRM-01 ships.

---

## 4. Integration with FAILURE_CLUSTERS_r5e1.md

Four packs live in the cluster doc. SPANTAG's posture on each is now explicit:

| Cluster (from FAILURE_CLUSTERS_r5e1.md) | SPANTAG role | Rationale |
|---|---|---|
| **Pack 1 — Birth-order / sibling arithmetic** (cases 002, 014, 024, 047) | **Not a SPANTAG target.** | Arithmetic-derivation refusal + canonical form drift. Cluster doc routes this to WO-LORI-CONFIRM-01 (elicitation-side confirm pass). SPANTAG's Pass 2 has no lever on arithmetic. |
| **Pack 2 — Ownership / attribution** (cases 028, 035, 039, 068, 093 core) | **Partial SPANTAG target.** | Subject-beats-section rule is the mechanism. Claim: cases where Pass 1 binds a non-narrator relation_cue cleanly should flip. Cases where subject is ambiguous in the reply text (e.g. case_035's faith-practice question answered with narrator-side content) are not SPANTAG's lane — they need confirm pass. Expected flip count: ≤ 3 of the 5 cores, not all 5. |
| **Pack 3 — Pets salience** (cases 025, 042, 045, 046, 066) | **Conditional SPANTAG target.** | Mechanism is "surrounding-subject wins over pet routing." If Pass 2's scope slice includes both the pet path and the surrounding-subject path, the subject-beats-section rule may or may not correctly land on pet. Depends on relation_cue quality. Expected flip count: informative-only, not a ship gate. |
| **Pack 4 — Silent output / fallback drops** (13 cases) | **Not a SPANTAG target.** | Truncation, method=fallback, explicit-answer silent drops. These need truncation-lane work (#96 / WO-EX-TRUNCATION-LANE-01). Measured only as truncation_rate under SPANTAG; pass flips here are bonus. |

This replaces the parent spec's §Target pack rollup, which was written before the cluster doc existed. The first-pack 15 stubborn cases still get run (for backward-compatibility with the parent measurement plan), but the **decision weight** now sits on the cluster packs above.

---

## 5. Commit 3 — pipeline wiring

### Scope

Add `_extract_via_spantag(...)` and wire it into the main `_extract_via_llm` dispatch behind `HORNELORE_SPANTAG=1`. Nothing else.

### Files

- `server/code/api/routers/extract.py` — add `_spantag_enabled()` near the other flag helpers, add `_extract_via_spantag()` body after the existing Pass 2 scaffold (natural home: after L3131 where `_parse_spantag_pass2` ends), and extend the dispatch block at L1722 to consult SPANTAG before TWOPASS.

### Function sketch

```python
def _spantag_enabled() -> bool:
    return os.environ.get("HORNELORE_SPANTAG", "").lower() in ("1", "true", "yes")


def _extract_via_spantag(
    answer: str,
    current_section: Optional[str],
    current_target: Optional[str],
    *,
    current_era: Optional[str] = None,
    current_pass: Optional[str] = None,
    current_mode: Optional[str] = None,
) -> tuple[List[dict], Optional[str]]:
    """
    WO-EX-SPANTAG-01 Commit 3: two-pass extraction pipeline.

    Pass 1 → Pass 2 → down-project to legacy-shape items.
    Falls back to single-pass on any parse failure (Pass 1 or Pass 2).
    """
    # Pass 1
    p1_system, p1_user = _build_spantag_pass1_prompt(
        answer, current_section, current_target,
    )
    p1_raw = _try_call_llm(p1_system, p1_user, max_new=512, temp=0.1, top_p=0.9,
                           conv_id=f"_spantag_p1_{_uuid.uuid4().hex[:12]}")
    if not p1_raw:
        logger.warning("[extract][spantag][fallback] empty pass1 raw")
        return _extract_via_singlepass(answer, current_section, current_target)

    tags = _parse_spantag_pass1(p1_raw, answer)
    if not tags:
        logger.info("[extract][spantag][fallback] pass1 yielded 0 tags — single-pass")
        return _extract_via_singlepass(answer, current_section, current_target)

    # Pass 2
    p2_system, p2_user = _build_spantag_pass2_prompt(
        answer=answer,
        tags=tags,
        current_section=current_section,
        current_target_path=current_target,
        current_era=current_era,
        current_pass=current_pass,
        current_mode=current_mode,
    )
    p2_raw = _try_call_llm(p2_system, p2_user, max_new=1024, temp=0.15, top_p=0.9,
                           conv_id=f"_spantag_p2_{_uuid.uuid4().hex[:12]}")
    if not p2_raw:
        logger.warning("[extract][spantag][fallback] empty pass2 raw")
        return _extract_via_singlepass(answer, current_section, current_target)

    writes, no_writes = _parse_spantag_pass2(p2_raw, tags, answer)
    if writes is None:
        logger.warning("[extract][spantag][fallback] pass2 parse failed")
        return _extract_via_singlepass(answer, current_section, current_target)

    # Down-project: SPANTAG writes carry sourceSpan / sourceTagIds / priority /
    # disagreement_reason. Legacy rails expect {fieldPath, value, confidence}.
    # Strip SPANTAG-only keys here so the rails are untouched. Keep sourceSpan
    # in a parallel dict keyed by index for later surfacing (stripped before
    # eval scorer unless --with-source-spans).
    items = _down_project_spantag_writes(writes)
    raw_combined = f"[SPANTAG] P1_TAGS={len(tags)} P2_WRITES={len(writes)} P2_NOWRITES={len(no_writes)}"
    logger.info("[extract][spantag][summary] tags=%d writes=%d no_writes=%d",
                len(tags), len(writes), len(no_writes))
    return items, raw_combined
```

Key choices:

- **Fallback on any parse failure, not just Pass 2.** The parent spec's parser-discipline lives in Pass 1; if Pass 1 produces zero usable tags, it's cheaper to fall back than to feed Pass 2 an empty tag array (which it would then either hallucinate against or refuse).
- **Pass 1 max_new = 512, Pass 2 max_new = 1024.** Pass 1 output is a small tag array (target ≤ 30 tags even on long replies, ≤ 400 tokens typical). Pass 2 output carries dual-path writes + no_write reasons and needs more headroom. These are first-pass budgets; measure on Commit 5 and tighten.
- **Ephemeral conv_id per pass.** Same pattern as single-pass (prevents cross-narrator contamination via session/RAG state). Two conv_ids per extraction is fine.
- **No in-flight changes to the rails.** The guardrail stack runs on `items` after down-project, unchanged from legacy.

### Dispatch wiring at L1722

```python
# current:
if _flags.twopass_extract_enabled():
    return _extract_via_twopass(answer, current_section, current_target)

# new:
if _spantag_enabled():
    return _extract_via_spantag(answer, current_section, current_target,
                                current_era=current_era,
                                current_pass=current_pass,
                                current_mode=current_mode)
if _flags.twopass_extract_enabled():
    return _extract_via_twopass(answer, current_section, current_target)
```

SPANTAG gets precedence because it's the active lane. TWOPASS is left in place for rollback / A/B. The caller of `_extract_via_llm` must forward `current_era` / `current_pass` / `current_mode` — they arrive from the request body and are already threaded through into the extraction call site (Phase 2 payload landed). Verify that chain in `extract_fields` request handler before Commit 3 lands.

### Down-project helper

```python
def _down_project_spantag_writes(writes: List[Dict[str, Any]]) -> List[dict]:
    """
    Strip SPANTAG-only keys so the legacy rails see {fieldPath, value, confidence}.
    Retain sourceSpan / sourceTagIds in a metadata map for later surfacing.
    """
    items = []
    for w in writes:
        if w.get("priority") == "secondary":
            # Secondary writes are dual-path candidates. Rails should not promote
            # them as primary writes in r5-class evals. Keep them in the return
            # behind a metadata flag so the scorer can credit alt_defensible_paths.
            items.append({
                "fieldPath": w["fieldPath"],
                "value": w["value"],
                "confidence": w.get("confidence", 0.5),
                "_spantag_priority": "secondary",
                "_spantag_disagreement_reason": w.get("disagreement_reason"),
            })
        else:
            items.append({
                "fieldPath": w["fieldPath"],
                "value": w["value"],
                "confidence": w.get("confidence", 0.8),
            })
    return items
```

Note: the `_spantag_priority=secondary` marker is a **private key** (leading underscore) that downstream rails must ignore. The scorer, not the rails, consumes it. Document in the Commit 3 diff header.

### Commit 3 acceptance

1. Flag off → pipeline is byte-identical to r5e1 on a 5-case smoke (case_010, case_012, case_020, case_049, case_060 — standard smoke set from prior WOs).
2. Flag on → 3-case smoke (case_008, case_018, case_049) completes without parse failure, no fallback to single-pass, emits at least one `{fieldPath, value, confidence}` per case.
3. No AttributeError, no KeyError, no type mismatch. Python-level smoke clean.
4. `[extract][spantag][summary]` log line appears for every flag-on extraction.
5. `[extract][spantag][fallback]` log line appears for any fallback; log level `warning` for parse failures, `info` for zero-tag Pass 1.

### Commit 3 rollback

One commit, localized to three additions in `extract.py` (flag helper + wiring + pipeline function + down-project). Revert is the commit's inverse. No schema / catalog / rails change to unwind.

---

## 6. Commit 4 — eval harness additions

### Scope

Three additions to the eval harness, strictly report-side. No scoring change beyond what Phase 1 / #94 already landed.

### Files

- `scripts/run_question_bank_extraction_eval.py` — add `truncation_rate` to the topline block, add dual-path primary-pick metric, add `--spantag` pass-through flag that sets `HORNELORE_SPANTAG=1` in the child env.
- `scripts/run_stubborn_pack_eval.py` — propagate `--spantag` to the child eval invocation and fold the new metrics into the stability console.

### Additions

**1. truncation_rate as first-class topline metric.**

Parse `.runtime/logs/api.log` for `[VRAM-GUARD] Truncating input` events per case during the eval run window, attribute each to a case by session_id suffix (eval harness uses `eval_<case_id>` as session_id — see L689), emit `truncation_rate = (cases with ≥1 truncation) / total cases` in the topline block.

**2. Dual-path primary-pick metric.**

For each case in the primary sub-pack (008, 009, 018, 082), if the extractor emitted both a primary path and a secondary path (detected via `_spantag_priority` private key on items, or alternatively via the Pass 2 raw output recorded alongside), record `primary_pick_subject_driven: bool`. Aggregate across the sub-pack and across 3 runs into `dual_path_primary_pick_rate = (n primary-is-subject-driven) / (n dual-path emissions)`. Target ≥ 80% per the parent spec §Goal 6.

**3. `--spantag` pass-through.**

```python
parser.add_argument("--spantag", action="store_true",
                    help="Run eval with HORNELORE_SPANTAG=1 in child env")
# then when invoking the extract endpoint:
env = os.environ.copy()
if args.spantag:
    env["HORNELORE_SPANTAG"] = "1"
# ... requests.post uses env-free python-requests; flag is set on the API
# server-side, not the child. Document in eval-readme: the flag belongs on
# the API server, not here. --spantag merely ASSERTS the server is running
# with the flag on (by checking the /status endpoint if one exists, else by
# reading first extraction response metadata for a spantag marker).
```

Correction: `HORNELORE_SPANTAG` is a *server-side* env var, not a client-side one. The eval harness cannot set it on the running API. The `--spantag` flag should instead (a) probe the API for a `spantag_enabled: bool` key in the first response or `/status` payload, (b) fail-fast if the caller asserts `--spantag` but the server has it off, (c) pass through the assertion into the output JSON as `meta.spantag_enabled: true` for audit.

Spec `/status` or equivalent probe as part of Commit 4 if it doesn't already exist; low-risk, additive.

### Commit 4 acceptance

1. `truncation_rate` appears in every master-eval topline block, including runs with no truncation (writes `0.0%`).
2. `dual_path_primary_pick_rate` appears in the primary sub-pack section of the report when SPANTAG is on; omitted cleanly when off.
3. `--spantag` flag: (a) fails fast with a clear error message when asserted but server has flag off, (b) passes clean when both agree.
4. Byte-identical report on r5e1 when SPANTAG is off and no truncation occurred (the two new metrics default to `0.0%` and `omitted`).
5. Stubborn-pack stability console reads the new metrics without barfing.

### Commit 4 rollback

Revert the three additions. No data-file changes, no catalog changes.

---

## 7. Commit 5 — first eval + decision

### Scope

Run a SPANTAG eval tagged **r5f-spantag** (not r5e2-anything — that tag is burnt). Fill in the report, call the gate.

### Stack prep

- Chris cycles the stack with `HORNELORE_SPANTAG=1` set in the server env. (`HORNELORE_NARRATIVE=1` stays on; `HORNELORE_ATTRIB_BOUNDARY` stays off.)
- Cold boot wait per CLAUDE.md discipline: ~4 minutes. Chris runs the standard eval block after warmup.

### Eval block (copy-paste ready for Chris)

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/run_question_bank_extraction_eval.py --mode live \
  --spantag \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_r5f-spantag.json
HORNELORE_SPANTAG=1 ./scripts/run_stubborn_pack_eval.py \
  --tag r5f-spantag \
  --runs 3 \
  --spantag \
  --api http://localhost:8000 \
  --master docs/reports/master_loop01_r5f-spantag.json
grep "\[extract\]\[spantag\]" .runtime/logs/api.log | tail -60
grep "\[extract\]\[spantag\]\[fallback\]" .runtime/logs/api.log | wc -l
```

### Acceptance gate (ship default-on)

All of the following must hold:

- **Contract guards.** v3 ≥ 34/62 (r5e1 = 38/62), v2 ≥ 31/62 (r5e1 = 32/62). Current r5e1 clears the floor comfortably; SPANTAG default-on must not slide below it.
- **mnw ≤ 2** with same two offenders (035, 093) or fewer. **No new mnw cases.**
- **Primary sub-pack flips.** ≥ 3 of 4 (008, 009, 018, 082) flip stable_pass across 3 runs **and** 0/4 regress baseline_pass → new fail.
- **No friendly-fire on the rule's own target class.** On the attribution cluster (Pack 2 from FAILURE_CLUSTERS_r5e1.md), cases that pass on r5e1 must continue to pass. Specifically: cases 075 (not a SPANTAG target but a classic friendly-fire canary) and other cluster-2 r5e1 passes.
- **Fallback rate ≤ 5%** on the 104-case master.
- **Pass 1 parse success ≥ 95%** on both stubborn-15 and 20-case control slice.
- **sourceSpan coverage ≥ 80%** on emitted writes.
- **p95 end-to-end latency ≤ 1.8× r5e1.** (Two LLM calls per turn is the known cost; the gate ensures it stays within Chris's tolerance.)
- **Topline pass count** must not drop. r5e1 = 59/104. SPANTAG default-on requires ≥ 59/104. A net-neutral with cluster-2 flips counterbalancing control-slice drops is still a PASS — but only if the 0-regression-on-target-class rule above also holds.

If all hold: **ADOPT default-on.** Flip the flag default in `_spantag_enabled()` to `True`, update CLAUDE.md phase block, close #95 / #132. SPANTAG becomes the active extraction path. `HORNELORE_SPANTAG=0` stays available for diagnostic fallback.

If any hold except **Primary sub-pack flips:** **KEEP FLAG BEHIND ENV, iterate.** Commit 6 (conditional) fires: re-enable PROMPTSHRINK pairing or tighten Pass 2 prompt and re-run.

If friendly-fire fires (new mnw or regression on rule's target class): **REJECT.** Follow r5e2 playbook — keep SPANTAG scaffolds in-tree, flag stays off by default, re-lock r5e1, document the rejection in CLAUDE.md evening-entry style.

If topline drops but contract guards hold: **PARK.** Revisit post-SECTION-EFFECT Phase 3. The extractor is finding evidence differently but not better; SPANTAG's design may need Commit 6 refinement before being defensible.

### Decision gate summary — what gets written in CLAUDE.md

One of:

- `ADOPT default-on` — with 8 criteria all green, flag flipped, r5f-spantag locked as new floor, SPANTAG default.
- `ADOPT-WITH-FLAG` — with 7 of 8 green, flag stays `0` by default, `HORNELORE_SPANTAG=1` documented for anyone running it locally.
- `ITERATE` — one gate failed with a clean-attribution fix known; Commit 6 triggered.
- `REJECT` — friendly-fire or target-class regression observed; SPANTAG scaffolds parked in-tree, r5e1 remains active floor, spec revision needed.

### Commit 5 deliverables

- `docs/reports/master_loop01_r5f-spantag.json` + `.console.txt` — raw eval outputs.
- `docs/reports/stubborn_pack_r5f-spantag_run{1,2,3}.json` + `_stability.json` + `_stability.console.txt` — diagnostic layer.
- `docs/reports/WO-EX-SPANTAG-01_REPORT.md` — the readout. Section shape per the parent spec §Measurement plan, updated with the §5.1 table of 8 gate criteria and their pass/fail call.
- CLAUDE.md changelog entry (evening style if it closes in a session, morning style if it opens the next day).

---

## 8. Commit 6 — conditional, only if Commit 5 says ITERATE

### Triggers

- Primary sub-pack flips ≥ 2 (not 3) but other gates green → Pass 2 prompt needs a tighten on subject-beats-section phrasing.
- Fallback rate > 5% → Pass 1 or Pass 2 parser needs more tolerance.
- p95 latency > 1.8× → re-enable PROMPTSHRINK pairing to reduce Pass 2 input token count.

### Scope

- Whatever the specific failure was, not a generic retry.

### Non-scope

- Do not touch the legacy single-pass path to "compensate." The point of the flag is to isolate blame.
- Do not stack a new WO on top of Commit 6; if Commit 6 doesn't land the gate, we reject and revisit Phase 2 of the WO in a follow-up.

---

## 9. What happens after SPANTAG decision

**If ADOPT default-on:**

- Close #132 / #90 / parent spec is called "landed".
- SPANTAG becomes the active extraction path; the `HORNELORE_SPANTAG=1` assertion becomes moot (flag defaults to on).
- **Next WO in sequence:** WO-LORI-CONFIRM-01 implementation unblocks (its parked spec sits at `WO-LORI-CONFIRM-01_Spec.md`). Cluster 1 (birth-order) and cluster 2's residual attribution cases become the target.
- R5.5 Pillar 2 (entity-role binding, #68 follow-up) opens.

**If ADOPT-WITH-FLAG:**

- Close #132 with notation; flag stays off by default.
- WO-LORI-CONFIRM-01 is un-blocked on sequencing but Chris decides whether to start there or iterate SPANTAG first.

**If REJECT:**

- Document the rejection per r5e2 pattern.
- Keep the Pass 1 / Pass 2 scaffolds in-tree (they may be reused by a future WO).
- WO-LORI-CONFIRM-01 sequencing is unaffected — it was always an elicitation-side lever, not a prompt-side one.

---

## 10. Risk register (delta from parent spec)

New risks this WO surfaces that the parent did not:

- **R-A (MEDIUM)** — Commit 3's down-project helper may mis-handle edge cases where Pass 2 emits a primary-with-no-secondary (the rule-doesn't-fire case). Mitigation: down-project treats "no priority field" as primary by default; unit test covers the 3 canonical Pass 2 outputs (only-primary, primary+secondary, only-secondary).
- **R-B (LOW)** — `--spantag` flag assertion against the API server requires a probe endpoint. If no `/status` exists, add one as a separate 10-line commit ahead of Commit 4. Do not skip the assertion; silent "ran without the flag" is worse than a fail-fast.
- **R-C (MEDIUM)** — r5e2 taught us that a rule can look perfect on the 4 named targets and still wreck 7 other cases. Commit 5 acceptance gates include the 20-case control slice for this reason. Do not relax the gate if the primary sub-pack looks excellent.
- **R-D (LOW)** — WO-EX-SECTION-EFFECT-01 Phase 3 may not have landed before Commit 5. The gate does not require Phase 3's disposition, only that its matrix ran (even ITERATE-disposition is fine). If Phase 3 hasn't run at all, Commit 5 reads measurement #10 as "unmeasured" and notes the absence in the report.

Inherited from parent spec: Llama tag-recall, Pass 1 offset drift, Pass 2 schema flooding, two-call latency. All mitigations unchanged.

---

## 11. Test fixtures needed before Commit 5

### Unit-test fixtures (for Commits 3 and 4)

- `tests/extract/fixtures/spantag_pass1_wellformed.txt` — canonical Pass 1 output for case_008 reply; parser should yield 5 tags cleanly.
- `tests/extract/fixtures/spantag_pass1_malformed.txt` — trailing garbage, missing commas, duplicated keys; parser should recover via regex fallback.
- `tests/extract/fixtures/spantag_pass2_only_primary.json` — no `priority` field anywhere; down-project emits all as primary-default.
- `tests/extract/fixtures/spantag_pass2_dual_path.json` — one primary + one secondary for case_008; down-project emits both with `_spantag_priority` marker.
- `tests/extract/fixtures/spantag_pass2_only_secondary.json` — (theoretically impossible; guard against) all entries marked `secondary`; down-project emits with warning log.

These fixtures are small and cheap; author them in the same commit as Commit 3.

### Smoke-test case lists

- 5-case default-off smoke: `case_010, case_012, case_020, case_049, case_060`.
- 3-case flag-on smoke: `case_008, case_018, case_049`.
- 4-case primary-sub-pack: `case_008, case_009, case_018, case_082`.
- 20-case control slice: drawn from `contract tiny clean` + `contract small clean`; fix the list in `scripts/spantag_control_slice.json` for reproducibility.

---

## 12. Post-eval audit block (Commit 5)

Required in the CLAUDE.md changelog and in `WO-EX-SPANTAG-01_REPORT.md`:

```
r5f-spantag — SPANTAG default-<on|off> first eval
Topline:                XX/104   (delta vs r5e1: ±YY)
v3 contract:            XX/62    (delta vs r5e1: ±YY)
v2 contract:            XX/62    (delta vs r5e1: ±YY)
must_not_write:         XX violations (offenders: ...)
Primary sub-pack:       X/4 flipped stable_pass  (008: <P|F>, 009: <>, 018: <>, 082: <>)
Primary sub-pack regr:  X/4 baseline_pass→new_fail  (0/4 required to ship)
Control slice:          XX/20  (r5e1: <>)
Control slice regr:     X cases, <case_ids>
Friendly-fire check:    <clean | OFFENDERS: case_NNN, case_NNN>
Fallback rate:          X.X%  (gate: ≤ 5%)
Pass 1 parse success:   XX.X%  (gate: ≥ 95%)
sourceSpan coverage:    XX.X%  (gate: ≥ 80%)
truncation_rate:        XX.X%  (reported; not a gate)
dual_path_primary_pick: XX.X%  (on primary sub-pack; gate: ≥ 80%)
p95 latency:            <ms>  (r5e1: <ms>; gate: ≤ 1.8×)
method_distribution:    llm=XX rules=XX fallback=XX

Decision: ADOPT default-on | ADOPT-WITH-FLAG | ITERATE | REJECT
Reasoning: <one paragraph>
```

---

## 13. What this WO does NOT do

- Does not touch the legacy single-pass path.
- Does not alter the catalog, schema, or `extract_priority` lists.
- Does not change the rails / guardrail stack. Rails see down-projected items; they do not see SPANTAG's richer output shape.
- Does not surface `sourceSpan` in the review UI. That's R5.5 Phase 2 UI work, a separate WO.
- Does not run a Hermes / Qwen A/B. Parent spec Appendix A owns that sequencing.
- Does not close the attribution class. WO-LORI-CONFIRM-01 owns the remainder.

---

## 14. Related work

- `WO-EX-SPANTAG-01_Spec.md` — design authority document; this file is its execution companion.
- `WO-EX-SECTION-EFFECT-01_Spec.md` + `_PHASE3_WO.md` — prerequisite for measurement #10.
- `docs/reports/WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` — primary-sub-pack definition.
- `docs/reports/FAILURE_CLUSTERS_r5e1.md` — target-cluster mapping (§4 of this WO).
- `WO-LORI-CONFIRM-01_Spec.md` — the long-term answer for the attribution class; sequenced after SPANTAG decision.
- `WO-EX-PROMPTSHRINK-01_Spec.md` — conditional pairing, Commit 6.
- CLAUDE.md current-phase block — updated on Commit 5 landing.

---

## 15. Revision history

- 2026-04-21: Drafted as execution pack for tasks #95 / #132. Integrates r5e1/r5e2 lessons (friendly-fire discipline, mnw floor, confirm-pass routing for attribution residuals). Aligns target pack with `FAILURE_CLUSTERS_r5e1.md` Pack 2 (partial), explicitly excludes Packs 1/3/4. Commits 3 / 4 / 5 / 6(conditional) fully scoped. Eval tag fixed at `r5f-spantag` (r5e2 tag is burnt).
