# BUG-HARNESS-RECALL-DICT-FIELDS-01 — Recall fields scored at runtime but not persisted to result dict

**Status:** **CLOSED-VIA-DIAGNOSIS** (2026-05-05) — bug does NOT exist; v6 evidence was pre-rename. See "Resolution" section at the bottom of this file before reading the original analysis.
**Severity:** LOW — was authored as harness-only fix; investigation closed the spec without code change
**Surfaced by:** TEST-23 v6 audit (2026-05-05)
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers — closed via diagnosis

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

---

## Resolution (2026-05-05, post-authoring)

**Bug does NOT exist.** Re-investigation before implementing the fix found:

1. The current `RecallResult` dataclass at `scripts/ui/run_test23_two_person_resume.py:230-243` already uses the renamed fields (`era_stories_in_readback` / `era_stories_total`) per Chris's metric-rename commit landed earlier on 2026-05-05.
2. `_to_serializable` at L1889-1891 calls `asdict(obj)` directly, which uses the live dataclass field names. No rename or alias logic is needed; serialization is correct.
3. v6 JSON shows OLD field names (`era_facts_recalled = 2`, `era_facts_total = 7`) because **v6 was generated BEFORE the rename commit landed**. Chris ran v6 against a stale dataclass; the rename commit shipped after v6 finished.
4. The "JSON shows None" interpretation in the original analysis was an audit-tool error — the audit code queried `pre.get('name_recalled')` etc. against a JSON that had `contains_name` etc. Three sets of field names were in flight simultaneously: (1) audit-name-list (`name_recalled` / `dob_year_recalled` / `pob_recalled`), (2) v6 JSON shape (`contains_name` / `contains_dob_or_year` / `contains_pob` / `era_facts_recalled` / `era_facts_total`), (3) current dataclass (`contains_name` / ... / `era_stories_in_readback` / `era_stories_total`). All three differ; the audit was reading list-#1 against JSON-list-#2.

### Verification

```python
from dataclasses import dataclass, field, asdict

@dataclass
class RecallResult:
    label: str = ""
    contains_name: bool = False
    contains_dob_or_year: bool = False
    contains_pob: bool = False
    era_stories_in_readback: int = 0
    era_stories_total: int = 0
    severity: str = "PASS"

rr = RecallResult(contains_name=True, contains_dob_or_year=True, contains_pob=True, era_stories_in_readback=2, era_stories_total=7, severity="AMBER")
print(asdict(rr))
# Output:
# {'label': '', 'contains_name': True, 'contains_dob_or_year': True, 'contains_pob': True,
#  'era_stories_in_readback': 2, 'era_stories_total': 7, 'severity': 'AMBER'}
```

The dataclass shape + `asdict()` produces the expected JSON shape. v7 JSON will carry the renamed fields natively.

### What v7 will show

Post-rename JSON shape for `pre_restart_recall`:

```json
{
  "label": "pre_restart_recall",
  "question": "what do you know about me",
  "reply": "Mary, you were born...",
  "contains_name": true,
  "contains_dob_or_year": true,
  "contains_pob": true,
  "era_stories_in_readback": 2,
  "era_stories_total": 7,
  "cross_contamination": false,
  "onboarding_restart": false,
  "severity": "AMBER",
  "notes": ["only 2/7 era stories surfaced in readback (<3) — this measures whether 'what do you know about me' includes era memories, NOT whether era-click navigation works"]
}
```

That is the correct shape and matches what the runtime print already shows. No code change needed.

### Why this matters as a record

The audit/spec/diagnose-first discipline caught the phantom before any code was changed. Without the verification step (running `asdict()` on the current dataclass to confirm what v7 would actually produce), this BUG would have shipped a no-op patch + a confused commit message. The spec stays in-tree as a record of:

1. Misread evidence can produce real-looking BUGs
2. Verifying the actual current state of the code BEFORE patching catches phantom bugs
3. Field-name renames need careful audit-tool coordination — all three name-lists must be synchronized to a single canonical set, OR the audit tool must use list aliases

### What this changes about Phase 0

This BUG drops out of the Phase 0 queue. Five Phase 0 items remain (down from six):

- BUG-UI-POSTRESTART-SESSION-START-01 (top of Track 1)
- WO-PROVISIONAL-TRUTH-01 Phase E
- BUG-LORI-MIDSTREAM-CORRECTION-01
- BUG-LORI-LATE-AGE-RECALL-01
- BUG-EX-DOB-LEAP-YEAR-FALLBACK-01 + BUG-EX-POB-CORRECTION-WRONG-PATH-01 implementation

Master checklist gets updated accordingly.

### Audit-tool fix (separate from this BUG)

The audit-tool I authored in `docs/reports/MARY_POST_RESTART_AUDIT_2026-05-05.md` queried with the wrong field names. That's a one-line fix in any future audit script — use `pre.get('contains_name')` not `pre.get('name_recalled')`. No code change needed in the harness or product surface.
