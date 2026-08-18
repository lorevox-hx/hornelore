# Narrator Product Harness v1

Status: active harness contract

This is the routine non-family test surface for narrator reads and extraction.
It does not replace focused unit tests, and it does not authorize testing on a
family narrator.

## Personas and capability boundary

| Persona | Kind | Routine use |
|---|---|---|
| William Shatner | reference | Direct extraction, read projections, reference-write boundary |
| Dolly Parton | reference | Direct extraction, read projections, reference-write boundary |
| Tomasita Reyes Cantu | synthetic writable | Real intake, extraction, sessions, chronology and future product writes |
| Alex Eunseo Park | synthetic writable | Real intake, extraction, sessions, chronology and future product writes |

Shatner and Dolly must remain `narrator_type='reference'`. The harness never
converts them to live narrators to make a write test pass.

Tomasita and Alex are created per live run through the normal narrator-intake
API with `testing_only=true`. Their display name starts with
`HARNESS PRODUCT DELME`, contains a random run ID, and is verified immediately
after creation. Cleanup:

1. uses only the exact returned UUID;
2. re-reads and exactly verifies the harness display name;
3. obtains the delete inventory;
4. calls the normal hard-delete API;
5. reports and exits nonzero if cleanup fails.

There is no name-pattern batch deletion.

## Files

```text
scripts/run_narrator_product_harness.py
scripts/harness/extraction_scoring.py
data/qa/narrator_product_personas_v1.json
data/qa/extraction_core_v1.json
data/qa/extraction_challenge_v1.json
tests/test_narrator_product_harness.py
```

The historical runner remains at:

```text
scripts/archive/run_question_bank_extraction_eval.py
```

It is preserved for report reproduction and scorer compatibility. It is
retired as the routine runner because its live path hard-codes family UUIDs and
it combines historical GPU experiments, scoring, execution and reports in one
large module. Do not add new product acceptance behavior to it.

## Safe first commands

No stack and no writes:

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python \
  scripts/run_narrator_product_harness.py --scenario plan
```

Validate all 32 core contracts against their ideal mock outputs:

```bash
PYTHONPATH=server/code .venv/bin/python \
  scripts/run_narrator_product_harness.py \
  --scenario extraction-core --mode offline
```

This proves the corpus and scorer agree. It does **not** claim that the live
extractor passed.

Run the offline harness tests:

```bash
PYTHONPATH=server/code .venv/bin/python -m unittest \
  tests.test_narrator_product_harness
```

## Live direct extraction

Chris starts the stack. The two reference narrators must already exist exactly
once and be classified as `reference`. The runner creates and cleans Tomasita
and Alex itself.

```bash
PYTHONPATH=server/code .venv/bin/python \
  scripts/run_narrator_product_harness.py \
  --scenario extraction-core --mode live
```

Core is a gate: every case must pass, and any `must_not_write` emission fails
the run.

Run difficult research cases separately:

```bash
PYTHONPATH=server/code .venv/bin/python \
  scripts/run_narrator_product_harness.py \
  --scenario extraction-challenge --mode live
```

Challenge failures are findings and return zero by default. Add
`--strict-challenge` only when deliberately treating the current challenge
pack as a gate.

Useful focused options:

```text
--personas tomasita,alex
--case-ids xcore_017,xcore_025
--max-cases 8
--output /explicit/report.json
--keep-run
```

`--keep-run` preserves exact synthetic run rows for inspection and records
their UUIDs in the report. Without it, cleanup is mandatory.

## Live product reads

```bash
PYTHONPATH=server/code .venv/bin/python \
  scripts/run_narrator_product_harness.py \
  --scenario product-read --mode live
```

This checks narrator-scoped projection, chronology and session reads. It does
not mutate reference narrators.

## Completed-turn extraction path

This scenario uses the existing operator harness adapter over the real chat
WebSocket. It requires the server to have:

```text
HORNELORE_OPERATOR_HARNESS=1
```

and therefore requires a stack restart after that local environment change.
The optional truth-pipeline summary is richer when its existing observability
flag is enabled, but the durable pending extraction result remains the primary
proof.

```bash
PYTHONPATH=server/code .venv/bin/python \
  scripts/run_narrator_product_harness.py \
  --scenario completed-turn --mode live
```

Shatner and Dolly are reported as not applicable. Tomasita and Alex must each
prove:

```text
real chat turn
→ assistant response completed
→ one durable pending extraction result
→ truth-zone contract passes
→ session row carries the same narrator's person_id
```

The created narrators and their run-owned turns, sessions and extraction rows
are then inventoried and deleted through the exact-person hard-delete path.

## Reports

Default reports are written under `docs/reports/`, which remains covered by
the repository privacy rule. Reports record:

- git SHA;
- run ID;
- scenario and mode;
- exact created person IDs;
- server effective extraction diagnostics;
- case results and aggregate truth-zone rates;
- cleanup inventory/result;
- retained rows or cleanup errors.

Routine reports are evidence, not tracked source files.

## Improvement rule

Do not patch the extractor for one biography sentence.

Cluster failures into attribution, abstention, cardinality, schema routing,
guard false-positive, compound-answer, or model-output classes. A repaired
challenge case moves into the core gate only with:

1. the original case;
2. an equivalent case under a second persona;
3. a negative counterexample;
4. zero new `must_not_write` violations.

The extractor extracts facts. Lori preserves voice. Demographic fixture data
is test coverage, never a runtime identity classifier.
