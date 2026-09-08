# BUG-HARNESS-TEST23-INDENTATION-01 — Test 23 does not parse

**Status:** OPEN, bounded, **not scheduled into any active lane.**
**Found:** 2026-08-27, during the Profile Seed pre-Step-6 review.
**Owner lane:** none yet. It is recorded here so it stops being rediscovered.

---

## 1. The defect

```
$ python3 -m py_compile scripts/ui/run_test23_two_person_resume.py
Sorry: IndentationError: unexpected indent
       (run_test23_two_person_resume.py, line 2082)
```

`scripts/ui/run_test23_two_person_resume.py:2075-2082`:

```python
        ctx.add_init_script(
            "try {"
            "  localStorage.setItem('lorevox_facial_consent_granted', '1');"
            "  localStorage.setItem('lorevox_facial_consent_declined', '0');"
            "} catch (_) {}"
        )
                page = ctx.new_page()          # <- line 2082, over-indented
                console = ConsoleCollector(page)
```

The `add_init_script(...)` call was inserted at one indentation level and the
block that follows it kept a deeper one. Python cannot parse the module, so
**Test 23 has not run since the edit landed.**

## 2. It is not this lane's

```
$ git log -1 --format='%h %ad %s' --date=short -- scripts/ui/run_test23_two_person_resume.py
df82215 2026-05-06 fix(harness)+reports: BUG-HARNESS-FACIAL-CONSENT-OVERLAY-BLOCK-01 + v10/v11 evidence
```

**2026-05-06**, in the facial-consent overlay repair. The Profile Seed lane
began on 2026-08-26 and has never touched `scripts/ui/`. It surfaces now only
because a repository-wide compilation was run as part of the Step 6 review —
which is the useful part of the finding: nothing in the ordinary test path
compiles this file, so a harness can stop parsing and stay silent for three
and a half months.

## 3. Why it is being written down instead of fixed

Repairing it means re-deriving what the two-narrator resume harness was
supposed to do at that point — whether the consent init-script belongs inside
the per-narrator loop or before it — and then RUNNING it against a live stack
to confirm the harness still measures what it claims. That is a bounded piece
of work with its own evidence, and folding it into a Profile Seed correction
checkpoint would put an unverifiable UI-harness change inside a commit whose
whole purpose is that every claim in it is reproducible.

**Do not repair this inside the Profile Seed lane.**

## 4. What a repair owes

1. Correct the indentation so the module parses, deciding deliberately whether
   `add_init_script` belongs inside or outside the per-narrator loop — the two
   readings give different harness behaviour, and the traceback does not say
   which was meant.
2. Run Test 23 against a live stack and attach the report.
3. **A compile gate**, so the next one is loud: a test that byte-compiles every
   tracked `.py` under `scripts/` and `tests/` and fails on the first
   `SyntaxError` / `IndentationError`. This defect's real cost is not the broken
   file; it is the three and a half months of silence, and only the gate
   addresses that.

## 5. Scope

* Touches `scripts/ui/run_test23_two_person_resume.py` and, for item 3, one
  new test module.
* Touches **no** product code.
