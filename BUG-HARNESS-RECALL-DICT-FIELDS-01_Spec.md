# BUG-HARNESS-RECALL-DICT-FIELDS-01 — Recall fields scored at runtime but not persisted to result dict

**Status:** OPEN — harness-only fix
**Severity:** LOW (harness reporting gap; no product impact)
**Surfaced by:** TEST-23 v6 audit (2026-05-05)
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers — quick win, lands in ~5-line patch

---

## Problem

`pre_restart_recall.{name_recalled, dob_year_recalled, pob_recalled, era_stories_in_readback, era_stories_total}` and `post_restart_recall.*` are scored at runtime (visible in console print lines) but `None` in the JSON output. The values get computed for the print statement and never written back into the `RecallResult` dataclass before serialization.

Downstream effect: any future analysis that reads the JSON reports (rollup tools, regression diff scripts, agents reviewing past v-runs) sees fields=None and assumes Lori didn't recall anything — when in fact the recall worked, the harness just didn't write the score back.

This bug masked a real Lori success in v5 (Marvin recall_pre showed up as RED in the JSON despite Lori's chat content being correct, which led to the harness lori_reply capture fix landing 2026-05-05) and would mask future similar wins if not fixed.

## Evidence

v6 run, both narrators:

```python
=== mary/pre_restart_recall ===
  severity: AMBER
  reply len: 700
  name=None dob=None pob=None eras=None/None     # ← all None despite reply being 700c
=== marvin/pre_restart_recall ===
  severity: AMBER
  reply len: 748
  name=None dob=None pob=None eras=None/None     # ← all None despite reply being 748c
```

Console print at the same moment:

```
[mary/recall_pre] name=True dob/yr=True pob=True eras=2/7 contam=False restart=False severity=AMBER
[marvin/recall_pre] name=True dob/yr=True pob=True eras=1/7 contam=False restart=False severity=AMBER
```

The print line shows `name=True` etc. — so the values ARE computed. They just don't reach the dataclass.

## Reproduction

Trivial. Run any TEST-23 version after v5. Dump the JSON. Compare the runtime print to the dict fields.

```bash
python3 -c "
import json
v = json.load(open('docs/reports/test23_two_person_resume_test23_v6.json'))
nr = v.get('mary') or {}
pre = nr.get('pre_restart_recall') or {}
print('reply len:', len(pre.get('reply', '') or ''))
print('name=', pre.get('name_recalled'))
print('eras=', pre.get('era_stories_in_readback'), '/', pre.get('era_stories_total'))
"
# expected (post-fix):
# reply len: 700
# name= True
# eras= 2 / 7

# actual (current):
# reply len: 700
# name= None
# eras= None / None
```

## Diagnosis

In `scripts/ui/run_test23_two_person_resume.py`, the recall scoring code computes the booleans + counts and uses them in the print line at L1335-1337 and L1364-1366:

```python
print(f"  [{plan.key}/recall_pre] name={rr.contains_name} dob/yr={rr.contains_dob_or_year} "
      f"pob={rr.contains_pob} story_recall={rr.era_stories_in_readback}/{rr.era_stories_total} "
      f"contam={rr.cross_contamination} restart={rr.onboarding_restart} severity={rr.severity}")
```

The `rr` object IS populated correctly per the print — `rr.contains_name`, `rr.contains_dob_or_year`, etc. are all set. But the JSON serialization at the end of the run dumps `nr.pre_restart_recall = rr` and somewhere the JSON serialization has a different field-name expectation OR the rr-to-dict conversion uses `dataclasses.asdict()` which renames fields.

Most likely cause: the harness's `_to_serializable()` helper uses different field names from what the JSON dump expects, OR the `RecallResult` dataclass field names don't match what the dict-reading code at v6 audit time looked for. The audit code used `name_recalled`, `dob_year_recalled`, `pob_recalled`, `era_stories_in_readback` — but `RecallResult` may use `contains_name`, `contains_dob_or_year`, `contains_pob`, `era_stories_in_readback` (the rename from era_facts_recalled landed cleanly per the diff Chris pasted).

So the fix is one of:
- Rename the dataclass fields to match what the audit / downstream consumers expect (more invasive)
- OR rename the audit / downstream code to match the dataclass (cheaper, no harness behavior change)
- OR add the audit-style field names as `__post_init__` or `to_dict` aliases (compromise)

## Reproduction confirmation step

Read `RecallResult` field definitions in `scripts/ui/run_test23_two_person_resume.py:235-244`. Compare to what the audit-time JSON read code expected. Confirm whether the issue is the dict-key mismatch OR something deeper (e.g., the result is being serialized but a different empty `RecallResult()` is being assigned to `nr.pre_restart_recall` later in the flow, overwriting the populated one).

## Acceptance gate

TEST-23 v7 JSON output shows non-None values for all five fields when the runtime print shows them as True/False/numeric:

```python
{
  "pre_restart_recall": {
    "reply": "Mary, you were born...",     # 700+ chars
    "contains_name": true,                   # was: None
    "contains_dob_or_year": true,            # was: None
    "contains_pob": true,                    # was: None
    "era_stories_in_readback": 2,            # was: None
    "era_stories_total": 7,                  # was: None
    "severity": "AMBER",
    ...
  },
  ...
}
```

(Or whatever the canonical field names are after the rename — the gate is "JSON values match runtime print values," not the specific field names.)

## Files (planned)

**Modified:**
- `scripts/ui/run_test23_two_person_resume.py` — single file, ~5-15 line patch depending on which fix is chosen

**Zero touch:**
- All product code (this is harness-only)
- All other test fixtures / tests / specs

## Risks & rollback

**Risk 1: downstream consumers assume the broken shape.** If any existing analysis code or rollup scripts read these fields expecting None, fixing the harness could surprise them. Very low risk — these fields are new since the metric rename, and consumers are agents/operators reading the output, not stable scripts.

**Risk 2: rename breaks v6 retro-comparison.** If the field names change as part of the fix, comparing v6 (broken) to v7 (fixed) becomes annoying. Mitigation: prefer adding aliases over renaming, OR document the rename clearly so v6 is treated as a baseline of "everything-shows-None-but-runtime-print-was-correct."

**Rollback:** revert the patch. JSON values go back to None. Print lines remain accurate.

## Sequencing

This is a quick-win that improves harness reporting fidelity for every subsequent test run. Land before TEST-23 v7 so the v7 baseline carries clean JSON. Independent of the other Phase 0 specs — no shared files, no shared logic.

## Changelog

- 2026-05-05: Spec authored after v6 audit caught the JSON-vs-print divergence. Diagnosis points to dataclass-field-vs-dict-key mismatch; fix is ~5-15 lines.
