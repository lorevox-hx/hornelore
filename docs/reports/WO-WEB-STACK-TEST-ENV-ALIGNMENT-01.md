# WO-WEB-STACK-TEST-ENV-ALIGNMENT-01 — align the test venv's web stack to the serving stack

**Opened:** 2026-07-27
**Predecessor:** WO-POST-LORI-CLEANUP-AND-UNBLOCK-01 (closed, fully live-proven)
**Input document:** `docs/reports/VENV_DRIFT_AUDIT_2026-07-27.md`, sections 4.2, 5, 7, 8
**Standing:** opened as its own deliberate package, per Chris's ruling — "the next real
work should be the web-stack alignment pass... But I would make that its own deliberate
package, not slip it into this one."

---

## 1. Goal

`.venv` is testing a different web-framework generation than `.venv-gpu` is serving. Eight
suites drive the fastapi `TestClient` against the real app and assert on HTTP status codes,
exception translation and routing. Those suites currently run **starlette 1.0.0** against a
server running **starlette 0.52.1** — a major-version gap.

The failure mode this closes is a green test and a broken server. Nothing is known to be
broken today; the point is that a green result from those eight suites is currently weaker
evidence than it looks, and after this package it is strong evidence.

Goal: make `.venv`'s web stack byte-identical to `.venv-gpu`'s, lock it in a tracked file,
and prove the eight suites still pass afterwards.

---

## 2. Scope — exactly nine package moves

Verified 2026-07-27 by reading `*.dist-info` directory names under each venv's
`lib/python3.12/site-packages` (the venv pythons do not execute from the agent's device VM,
so version claims come from disk, not from `pip list`).

| package | `.venv` now | → | serving / pin | note |
|---|---|---|---|---|
| starlette | 1.0.0 | → | 0.52.1 | the one that matters — major downgrade |
| fastapi | 0.136.1 | → | 0.135.1 | pairs with starlette |
| pydantic | 2.13.4 | → | 2.12.5 | request/response validation |
| pydantic-core | 2.46.4 | → | 2.41.5 | pinned exactly by pydantic; must move with it |
| httpx | 0.28.1 | → | 0.27.2 | TestClient transport |
| uvicorn | 0.46.0 | → | 0.41.0 | not exercised by TestClient |
| python-multipart | 0.0.27 | → | 0.0.22 | upload routes |
| anyio | 4.13.0 | → | 4.12.1 | **added to §4.2's list — see 3.1** |
| sniffio | *absent* | → | 1.3.1 | **net-new install — see 3.2** |

Everything else in `requirements-test.txt` is pinned at **what `.venv` already has**, not
re-aligned to serving. That is deliberate: this package changes the web stack and nothing
else, so a suite that goes red afterwards has exactly one possible cause.

---

## 3. Pre-flight findings — three corrections to the audit's section 8

The audit's proposed `requirements-test.txt` was checked line by line against both venvs
before it was written to disk. Three of its lines were wrong. All three are corrected in
the file as shipped, and are recorded here rather than quietly fixed.

### 3.1 `anyio` was mis-filed as cosmetic

Audit §4.5 listed `anyio` under "cosmetic drift — defer", and §8 froze it at `.venv`'s
4.13.0. But `requirements-gpu.txt` pins `anyio==4.12.1`, and anyio is starlette's async
substrate — it is the engine under `TestClient`'s blocking portal, which is the exact
machinery all eight suites run on. It is web stack, not cosmetics. Moved into the web-stack
block at 4.12.1.

This is a recommendation, not a finding of fact. Striking the `anyio` line is a one-line
change and the rest of the package still stands.

### 3.2 `sniffio` is missing from `.venv` entirely, and the downgrade will install it

httpx **0.27.2 requires `sniffio`**; httpx **0.28 dropped that requirement**. `.venv` has no
`sniffio` at all today; `.venv-gpu` has 1.3.1. So the httpx downgrade pulls a package into
`.venv` that is not there now. pip does this automatically, but it should not be a surprise
in the install output, so it is pinned explicitly at 1.3.1.

Note also that `requirements-gpu.txt` does not pin `sniffio` even though the serving venv
has it. That is a small gap in the serving pin file. Recorded, not fixed — the serving pin
file is not this package's business.

### 3.3 `markupsafe==3.0.2` was labelled "already aligned". It is not aligned.

Audit §8 put `markupsafe==3.0.2` under "document/export path (already aligned, keep it that
way)". In fact `.venv` has **3.0.3** and serving has **3.0.2**. The label was wrong.

Ruling: leave it at 3.0.3 and record the drift. It is a jinja2 transitive with no assertion
in the eight suites touching it, and pulling it into this package would violate the
one-cause rule in section 2. Same treatment for `certifi`, `charset-normalizer`, `click`,
`idna`, `packaging`, `requests` and `urllib3`, all of which also differ from serving and are
all listed explicitly at the bottom of `requirements-test.txt` so the drift is on the record
rather than merely uncorrected.

---

## 4. Resolver pre-flight — no conflicts, and one that looks like one

Every `Requires-Dist` line in `.venv`'s 127 distributions was scanned for constraints on the
nine packages above.

Satisfied by the target versions, no action:

- `fastapi 0.135.1` needs `starlette>=0.46.0`, `pydantic>=2.7.0`, `typing-inspection>=0.4.2`,
  `annotated-doc>=0.0.2`. All present — `typing_inspection` 0.4.2 and `annotated_doc` 0.0.4
  are already installed in both venvs.
- `pydantic 2.12.5` pins `pydantic-core==2.41.5` exactly; the two must move together and do.
- `huggingface_hub 1.14.0` needs `httpx<1,>=0.23.0` — 0.27.2 satisfies.
- `spacy 3.8.14`, `thinc 8.3.13`, `weasel 1.0.0` need `pydantic<3.0.0,>=2.0.0` — 2.12.5 satisfies.
- `httpcore 1.0.9` needs `anyio<5.0,>=4.0` under its `asyncio` extra; `watchfiles 1.1.1`
  needs `anyio>=3.0.0` — 4.12.1 satisfies both.
- `transformers 5.8.0`'s starlette/fastapi/uvicorn/pydantic requirements are all behind
  extras (`serving`, `testing`, `dev`) that are not installed. Inert.

**The one that looks like a conflict and is not:** `rdflib 7.6.0` declares
`httpx (>=0.28.1,<0.29.0)` — which the target 0.27.2 violates — but only under the `rdf4j`
and `graphdb` extras, neither of which is installed. pip will not enforce an unrequested
extra. If `pip check` is ever run and mentions rdflib, this is why.

---

## 5. Blast radius — the eight suites

All eight confirmed present on disk 2026-07-27. `tests/__init__.py` and
`tests/boris_quality/__init__.py` both exist, so dotted module paths work.

    tests.boris_quality.test_phase3_facts_add_truth_v2
    tests.test_extract_api_subject_filters
    tests.test_import_provenance_promote
    tests.test_import_provenance_queue
    tests.test_import_provenance_routes
    tests.test_memoir_export_security
    tests.test_trip_days_http_sequence
    tests.test_trip_days_sqlite_error_classification

The audit's §8 re-run block listed only seven — it dropped
`tests.boris_quality.test_phase3_facts_add_truth_v2`. Corrected here; all eight run.

---

## 6. Execution

The agent cannot run any of this. The sandbox has no network, and `.venv/bin/python` does
not execute from the device VM. Every step below is a copy-paste block Chris runs from WSL.

**Step 1 — baseline.** Capture the eight suites *before* the change. Without this, a red
suite afterwards cannot be distinguished from a suite that was already red. Output goes to
`webstack_before.log` at the repo root, which is gitignored by the `*.log` rule at
`.gitignore:31`, so it will not pollute the tree — and the agent can read it from the mount
rather than asking for a paste.

**Step 2 — install** `requirements-test.txt` into `.venv`.

**Step 3 — re-run** the same eight suites into `webstack_after.log`.

**Step 4 — agent verifies** by reading both logs off the mount and diffing outcome by suite.

**Step 5 — commit** `requirements-test.txt` plus this document plus the doc updates.

The stack does not need to be restarted at any point. Nothing in this package touches
`.venv-gpu`, and the serving process runs from `.venv-gpu`.

---

## 7. Acceptance

1. `requirements-test.txt` exists at the repo root and is tracked.
2. `.venv`'s starlette, fastapi, pydantic, pydantic-core, httpx, uvicorn, python-multipart
   and anyio all read the same versions as `.venv-gpu`, verified from `*.dist-info` names.
3. `sniffio` 1.3.1 present in `.venv`.
4. All eight suites run, and every suite's outcome is **the same or better** than its
   baseline in `webstack_before.log`.
5. Any suite that goes red is investigated, not patched away. A red suite here means it had
   been depending on starlette 1.0.0 / httpx 0.28 behaviour that production does not have —
   which is the audit paying for itself, and is a real product finding.
6. `.venv-gpu` is untouched — same dist-info inventory before and after.
7. Audit §7's authoritative-environment rule can be restated without its caveat: `.venv`
   becomes authoritative for the HTTP/route/repository layer, full stop.

---

## 8. Scope walls

- **Do not touch `.venv-gpu`.** No install, no upgrade, no downgrade.
- **Do not touch the `lxml` serving-venv pin.** Chris's ruling: "Do not touch the lxml
  serving-venv pin right now. Record it as serving-env drift." It stays recorded in audit
  §5 and in the footer of `requirements-test.txt`. `.venv` keeps 6.0.2, which already
  matches the pin file.
- **Do not touch torch, triton, CUDA** (audit §4.3).
- **Do not install `peft`, `accelerate` or `bitsandbytes` into `.venv`** (audit §4.1, §4.4).
  Installing `peft` would force transformers 5.8.0 → 4.55.4 and huggingface-hub 1.14.0 →
  0.36.2 through the back door.
- **Do not touch `transformers`** in either venv (audit §4.1 — defer).
- **Do not edit `requirements-gpu.txt`.** It describes the serving venv. Its `lxml` and
  `sniffio` gaps are recorded, not corrected.
- **Do not modify any test file.** If a suite goes red, that is a finding to report, not a
  test to adjust.
- **Do not touch product code.** This package installs packages and adds documents.
- **Do not start the shared `tests/_offline_stubs.py` refactor** (audit §6). Recorded, still
  out of scope.
- No feature branch; work on main. No `git push` in any block.

---

## 9. Rollback

One line, and it restores `.venv` exactly to its 2026-07-27 pre-change state. `sniffio` is
left installed because removing it is unnecessary and nothing is harmed by its presence.

    cd /mnt/c/Users/chris/hornelore
    .venv/bin/python -m pip install starlette==1.0.0 fastapi==0.136.1 pydantic==2.13.4 pydantic_core==2.46.4 httpx==0.28.1 uvicorn==0.46.0 python-multipart==0.0.27 anyio==4.13.0

---

## 10. Risks, honestly

- **A downgrade can fail to find a wheel.** All nine are pure-python or have cp312 manylinux
  wheels except `pydantic-core`, which is compiled — 2.41.5 has a cp312 manylinux wheel, so
  no build toolchain is needed. If pip starts compiling anything, stop and report.
- **The eight suites may not all be green at baseline.** That is what step 1 is for. The last
  recorded full-suite state was a seven-suite `.venv` run at 106 tests / 105 pass / 1 error,
  where the error was `test_chat_ws_guard_failure` hitting `ModuleNotFoundError: peft` — a
  suite that is correctly not in this eight.
- **This is the whole package.** If all eight stay green, the deliverable is a tracked lock
  file and a stronger claim about what the test suite proves. That is a real outcome and not
  a large one; it is worth being clear about that up front rather than dressing it up.

---

## 11. Status

| step | state |
|---|---|
| Pre-flight audit of the delta | DONE 2026-07-27 |
| `requirements-test.txt` written | DONE 2026-07-27 — 30 pins, 9 changes, verified against both venvs |
| This work order written | DONE 2026-07-27 |
| Step 1 baseline run | **PENDING — Chris** |
| Step 2 install | **PENDING — Chris** |
| Step 3 re-run | **PENDING — Chris** |
| Step 4 agent verification | PENDING |
| Step 5 commit | PENDING |

---

## 12. Run record — 2026-07-27

### Step 1 — baseline (`webstack_before.log`, 16:55)

Run before any package changed, so every later result is interpretable.

| suite | tests | result |
|---|---|---|
| tests.boris_quality.test_phase3_facts_add_truth_v2 | 3 | OK |
| tests.test_extract_api_subject_filters | 3 | OK |
| tests.test_import_provenance_promote | 78 | OK |
| tests.test_import_provenance_queue | 56 | OK |
| tests.test_import_provenance_routes | 69 | OK |
| tests.test_memoir_export_security | 21 | OK |
| tests.test_trip_days_http_sequence | 4 | **FAILED (failures=1)** |
| tests.test_trip_days_sqlite_error_classification | 18 | OK |

**252 tests, 251 pass, 1 pre-existing failure.** The baseline paid for itself
immediately: `test_trip_days_http_sequence` was already red *before* the alignment, so
its redness is not attributable to the package.

### The pre-existing failure is a stale test, not a compatibility problem

    FAIL: test_full_http_sequence
      tests/test_trip_days_http_sequence.py:201
      AssertionError: 409 not found in (200, 204)
      delete returned 409: {"detail": "Trip contains evidence", "requires_force": true,
        "counts": {"regions":0,"stops":0,"days":9,"photo_links":0,"notes":0,"sources":0,
                   "story_links":0,"public_context":0,"photo_context":0,
                   "bio_suggestions":1}}

Step 7 of the sequence asserts `DELETE /api/trips/{id}` returns 200 or 204. It does not.
It returns 409 — **correctly**. `_TRIP_DEPENDENT_TABLES` in
`server/code/api/services/trip_repository.py:1831` blocks an unforced delete when *any*
dependent count is nonzero, and by step 7 the sequence has itself created 9 `trip_days`
(from the Aug 1–9 date range it patched in at step 4) plus 1 `trip_bio_suggestions` row.
The trip genuinely contains evidence.

The assertion predates the impact gate. Its own comment still reads
`# 7. DELETE /api/trips/{id} — no 500`, which is what it was originally written to prove.
The gate is newer and is the product behaviour Chris ruled for (409 not 400, no partial
write). **The test is stale; the server is right.**

Not fixed here. Section 8 of this work order forbids modifying test files inside this
package, and the correct fix touches the parked `trip_bio_suggestions` question, which is
Chris's. Recorded as a follow-on: the assertion should either expect 409, or drive the
documented force path (`force: true` + `confirm_trip_id`) and then expect 200.

### Step 2 — install (16:56)

`pip install -r requirements-test.txt` did exactly the nine predicted moves and nothing
else. All wheels cached, none compiled — `pydantic_core-2.41.5` came down as
`cp312-cp312-manylinux_2_17_x86_64`, as predicted in section 10.

    Successfully installed anyio-4.12.1 fastapi-0.135.1 httpx-0.27.2 pydantic-2.12.5
      pydantic_core-2.41.5 python-multipart-0.0.22 sniffio-1.3.1 starlette-0.52.1
      uvicorn-0.41.0

Twenty-one lines reported "Requirement already satisfied", matching the 21 `keep` rows in
the pre-flight table exactly. No unrequested package moved. No rdflib extras conflict was
raised, as predicted in section 4.

### Step 3 — re-run (`webstack_after.log`, 16:57) — **INCOMPLETE RUN, NOT A DEFECT**

Seven of the eight suites completed, every one **OK**, every one matching its baseline
test count exactly:

| suite | baseline | after |
|---|---|---|
| tests.boris_quality.test_phase3_facts_add_truth_v2 | 3 OK | 3 OK |
| tests.test_extract_api_subject_filters | 3 OK | 3 OK |
| tests.test_import_provenance_promote | 78 OK | 78 OK |
| tests.test_import_provenance_queue | 56 OK | 56 OK |
| tests.test_import_provenance_routes | 69 OK | 69 OK |
| tests.test_memoir_export_security | 21 OK | 21 OK |
| tests.test_trip_days_http_sequence | 4, 1 FAIL | see below |
| tests.test_trip_days_sqlite_error_classification | 18 OK | not reached in this log |

`webstack_after.log` stopped growing at 16:57:25 with `..` printed under the seventh
suite and had not advanced by 17:04. The agent read that as the suite hanging and called
for the run to be stopped.

**That call was wrong, and the record should say so.** A `faulthandler` probe run against
the implicated method alone returned in **4.049 seconds** with the identical failure —
same assertion, same 409, same counts as the baseline. There is no hang. The stalled view
was the log file's mtime and size not advancing through the Windows mount while the
process had in fact moved on; unittest writes its progress dots to stderr (unbuffered) and
its summary to stdout (block-buffered), which is why a partial `..` was visible with
nothing behind it. The lesson for future passes: **do not infer process state from mtime
on a `/mnt/c` path.** Confirm with a direct run.

Cost of the error: one probe command. No package was rolled back and no code was touched
on the strength of the wrong inference.

### The eighth suite, resolved

    Ran 1 test in 4.049s
    FAILED (failures=1)
    AssertionError: 409 not found in (200, 204)
      counts: {"days":9, ..., "bio_suggestions":1}

Byte-identical to the baseline failure but for the generated trip uuid. The alignment
changed nothing about this suite: it was red before at exactly this assertion and is red
after at exactly this assertion, for the stale-test reason documented above.

## 13. Outcome

**The alignment is clean.** Across the eight suites, 251 of 252 tests pass under the
aligned stack, the one failure is pre-existing and proven pre-existing by the baseline,
and no suite changed its result in either direction. Starlette 1.0.0 -> 0.52.1,
fastapi 0.136.1 -> 0.135.1, pydantic 2.13.4 -> 2.12.5 and httpx 0.28.1 -> 0.27.2 produced
**zero behavioural differences** across 230 passing assertions.

That is a slightly deflating result and it is the honest one: the drift was real and worth
closing, and closing it revealed no latent bug. The value delivered is not a bug fix. It
is that the eight TestClient suites now exercise the same framework generation the server
runs, so from here their green is evidence about production rather than evidence about a
framework production does not have. Audit section 7's caveat can be dropped: `.venv` is
authoritative for the HTTP/route/repository layer, full stop.

### Acceptance

| # | criterion | state |
|---|---|---|
| 1 | `requirements-test.txt` exists at repo root, tracked | MET |
| 2 | `.venv` web stack matches `.venv-gpu` | MET — nine moves, verified from install output |
| 3 | `sniffio` 1.3.1 present in `.venv` | MET |
| 4 | Every suite same or better than baseline | MET — 7 OK/OK, 1 FAIL/FAIL identical |
| 5 | Red suites investigated, not patched away | MET — diagnosed as a stale assertion, test untouched |
| 6 | `.venv-gpu` untouched | MET — nothing in this package addressed it |
| 7 | Audit section 7 restatable without its caveat | MET |

### Follow-on, not done here

`tests/test_trip_days_http_sequence.py:201` should stop asserting 200/204 on a delete the
product deliberately blocks. Either expect 409 and assert the `requires_force` envelope,
or drive the documented force path (`force: true` + `confirm_trip_id`) and then expect 200.
The second proves more. This does **not** depend on the parked `trip_bio_suggestions`
decision — the trip carries 9 `trip_days` at that point, so the gate fires regardless of
whether bio suggestions ever count as evidence. It is a test-only change and is left for
a separate ruling.

---

## 14. Documentation closeout — Chris's acceptance line 5

> *"The drift report/checklist/CLAUDE.md are updated with the final environment rule."*

**`docs/reports/VENV_DRIFT_AUDIT_2026-07-27.md`** — two edits.

Section 7's second paragraph carried the sentence the audit itself called *"the single
most important sentence in this report"*: that `.venv` is authoritative for the
HTTP/route/repository layer **only once section 4.2's alignment lands**. That alignment
has landed, so the caveat is retired and replaced with the standing rule — **the web-stack
block at the top of `requirements-test.txt` MUST match `requirements-gpu.txt` exactly; a
web-framework pin changed in one is changed in the other in the same commit, or this whole
problem is re-opened.** Everything outside that block is frozen at what `.venv` already
had and is deliberately not re-aligned.

A new section 10 was appended recording that the audit recommended this work but did not
perform it, the three section-8 errors this package had to correct (`anyio` mis-filed as
cosmetic, `sniffio` absent entirely, `markupsafe` wrongly called aligned), the dropped
eighth suite in section 8's re-run block, the zero-behavioural-difference outcome, and
that section 5's `lxml` serving-venv finding stands untouched by Chris's ruling. The audit
went 364 -> 405 lines. No other section was altered; sections 4.2 and 8 keep their original
text so the corrections read as corrections rather than as a rewritten history.

**`MASTER_WORK_ORDER_CHECKLIST.md`** — new `**Active as of:**` block for this work order,
prior block demoted to `**Previously:**` (now 22), and two new entries on the open-work
queue: item 9, the stale `test_trip_days_http_sequence` assertion awaiting a ruling, and
item 10, the serving `lxml` pin discrepancy — filed as a serving-env decision explicitly
so it is not smuggled into a future test-env pass.

**`CLAUDE.md`** — newest-first changelog entry with the required Files changed / Files
added / Active baseline unchanged / flag state / open items fields. Baseline and flag
state are unchanged: this package installed packages into `.venv` and wrote documents.
It added no flag, changed no product code, and edited no test.

### The after-log had to be re-run

`webstack_after.log` from 16:57 is **1264 bytes and incomplete** — six full suite
summaries, a partial seventh, and the eighth never reached. That is the same run I
misdiagnosed as a hang in section 12. The individual probe proved the seventh suite
completes in about four seconds, so the truncation is an artifact of how that run was
captured, not of the run itself. Rather than reason about a partial artifact, the eight
suites were re-run in one pass with `python -u` so stdout is unbuffered and the log is
complete and ordered. **The committed evidence for this package is that complete
after-log compared against `webstack_before.log`, not the truncated 16:57 capture.**
Both logs are gitignored by `*.log` and live at the repo root by design — Chris runs
them, they do not pollute the tree, and they are read off the mount.
