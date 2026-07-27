# Runtime / test environment drift audit — `.venv` vs `.venv-gpu`

**Work order:** WO-POST-LORI-CLEANUP-AND-UNBLOCK-01, Lane 1
**Date:** 2026-07-27
**Method:** package-by-package comparison of `requirements-gpu.txt` pins against the
`*.dist-info` directory names under each venv's `lib/python3.12/site-packages`,
cross-checked against a repo-wide import-reachability grep.
**Scope note:** this is an audit and a ruling. No package was installed, removed or
upgraded as part of this work order. Any change below that is marked *align now* ships
as a copy-paste block for Chris to run, because the agent sandbox has no network.

---

## 1. Why this audit exists

The stated problem was that the test venv and the serving venv disagree in ways that can
make tests lie. The canonical example was `transformers` — 5.8.0 in `.venv`, 4.55.4 in
`.venv-gpu` and in the pin file.

The audit found that the `transformers` mismatch is real but is **not** the one that can
currently make a test lie, and that a different, quieter divergence is.

It also found, while running the broad regression sweep for Lanes 2 and 3, that the most
active source of lying tests in this repo right now is not package versions at all. It is
the hand-written `sys.modules` stubs inside the test files themselves. That finding is in
section 6.

---

## 2. Headline numbers

`requirements-gpu.txt` carries 53 pins. `.venv-gpu` has 92 distributions installed,
`.venv` has 127.

Of the 53 pins:

- 15 agree across the pin, `.venv-gpu` and `.venv`.
- 23 are installed in both venvs at **different** versions.
- 14 are **absent from `.venv` entirely**.
- 1 (`lxml`) is a pin-file accuracy bug in the other direction — see section 5.

Beyond the pin file there are 7 further packages that differ between the two venvs and are
not pinned anywhere, all of them in the torch / CUDA stack.

---

## 3. Import reachability — the evidence the ruling rests on

A drift only matters if a test can reach the drifted code. So before ruling on anything,
every drifted package was traced to its import sites.

**`transformers` is unreachable from the test suite.**

- **Zero** files under `tests/` import `transformers`, directly or transitively through a
  module they import.
- `transformers` is imported at exactly five places in the repo: `api.py` lines 14, 259
  and 502; `chat_ws.py` line 127; and `server/code/test_model.py` line 97.
- Of those, only `api.py` is on a path a test could plausibly pull in — and `api.py` line
  22 does `from peft import PeftModel` at **module scope**, and `peft` is not installed in
  `.venv`. So any test that tried to import `api.py` under `.venv` would die on `peft`
  long before `transformers` version mattered. That is exactly what
  `tests/test_chat_ws_guard_failure.py` already does, and why it errors under `.venv` with
  `ModuleNotFoundError: No module named 'peft'`.

The other 13 packages missing from `.venv` — `bs4`, `readability`, `pypdf`, `pytesseract`,
`pdf2image`, `faster_whisper`, `psutil`, `accelerate`, `bitsandbytes`, `ctranslate2`,
`hf_transfer`, `sentencepiece`, `pydantic_settings` — are all imported lazily, inside
function bodies, not at module scope. A test can import their host module and never touch
them.

**The web-framework stack IS reachable, and heavily.**

Eight suites drive `fastapi.testclient.TestClient` against the real app:

    tests/boris_quality/test_phase3_facts_add_truth_v2.py
    tests/test_extract_api_subject_filters.py
    tests/test_import_provenance_promote.py
    tests/test_import_provenance_queue.py
    tests/test_import_provenance_routes.py
    tests/test_memoir_export_security.py
    tests/test_trip_days_http_sequence.py
    tests/test_trip_days_sqlite_error_classification.py

Every one of those exercises starlette, fastapi, pydantic and httpx. All four are drifted.

---

## 4. Rulings

### 4.1 `transformers` 4.55.4 → 5.8.0 — **DEFER, with a written rule**

This is the divergence the work order named, so it gets the explicit ruling it was
promised.

The mismatch is a **major version jump** and would normally be alarming. It is currently
**inert**, because — per section 3 — every code path that imports `transformers` is
already unreachable from `.venv` behind the `peft` module-scope import. The test venv
cannot execute a single line of transformers code today. A version skew in code that never
runs cannot make a test lie.

It is, however, a **latent hazard**, not a non-issue. The day someone makes the `peft`
import lazy, or adds a test that imports a narrator/model module, `.venv` starts silently
executing transformers 5.x while production executes 4.55.4 — and that test would pass
while proving nothing about production.

**Do not hand-downgrade `.venv` to transformers 4.55.4.** Doing so drags
`huggingface-hub` 1.14.0 → 0.36.2 and `tokenizers` 0.22.2 → 0.21.4 with it, which is a
larger and riskier dependency move than the problem justifies, and it would be undone by
the next unpinned install. The same reasoning bars installing `peft` into `.venv`, which
the work order also forbade explicitly.

**The rule instead is environmental, and is stated in section 7: any suite that imports
`transformers` runs in `.venv-gpu`, never in `.venv`.** The three suites in that category
today already run there. `huggingface-hub` 0.36.2 → 1.14.0 and `tokenizers` 0.21.4 →
0.22.2 inherit this same ruling for the same reason — they are transformers' own
dependencies and share its reachability.

### 4.2 The web stack — **ALIGN NOW** (this is the live one)

| package | pin / serving | `.venv` | why it matters |
|---|---|---|---|
| starlette | 0.52.1 | **1.0.0** | 0.x → 1.x major, under 8 TestClient suites |
| httpx | 0.27.2 | **0.28.1** | TestClient transport; 0.28 changed client defaults |
| fastapi | 0.135.1 | 0.136.1 | minor, but pairs with the starlette major |
| pydantic | 2.12.5 | 2.13.4 | request/response model validation |
| pydantic-core | 2.41.5 | 2.46.4 | follows pydantic |
| uvicorn | 0.41.0 | 0.46.0 | server, not exercised by TestClient |
| python-multipart | 0.0.22 | 0.0.27 | upload routes |

This is the drift that can actually make a test lie today, and it is the one nobody had
named. A `starlette` 0.x → 1.x jump under eight suites that assert on HTTP status codes,
exception handling and routing behaviour means those suites are validating a different
web framework generation than the one serving Chris's stack. A route-ordering or
exception-translation change between starlette 0.52 and 1.0 would show up as a green test
and a broken server, which is precisely the failure mode this lane was opened to prevent.

**Recommendation: pin the test venv's web stack to the serving versions**, via the
`requirements-test.txt` in section 8. This is low-risk — these are the same versions
production already runs, so aligning cannot break the serving path, and the seven packages
have no CUDA or model-stack entanglement. It is the only *align now* bucket in this audit.

**This alignment was NOT performed as part of this work order.** The work order authorised
package changes only where "low-risk and clearly justified," and a seven-package
downgrade of the framework under 8 suites deserves to be run deliberately, with the suites
re-run immediately after, rather than slipped in alongside two unrelated lanes. The
copy-paste block is in section 8; the re-run block is beside it.

### 4.3 torch / triton / CUDA — **INTENTIONALLY DIVERGE**

    torch            gpu 2.12.0.dev20260407+cu128   venv 2.11.0
    triton           gpu 3.7.0+git9c288bc5          venv 3.6.0
    cuda-bindings    gpu 12.9.4                     venv 13.2.0
    cuda-pathfinder  gpu 1.2.2                      venv 1.5.4
    cuda-toolkit     gpu 12.8.1                     venv 13.0.2
    fsspec           gpu 2026.3.0                   venv 2026.4.0
    setuptools       gpu 78.1.0                     venv 81.0.0

`requirements-gpu.txt` deliberately does not pin torch — the serving venv runs a dated
CUDA 12.8 nightly that is installed out-of-band from the PyTorch index, and the pin file
documents this by omission. Churning torch was explicitly out of scope for this work
order, and independently it is the correct call: `.venv` runs no model code, so its torch
is inert, and a CPU-side torch upgrade in the serving venv risks the whole narrator stack
for zero test fidelity gained.

`fsspec` and `setuptools` ride along with this bucket. Neither is pinned and neither
affects any assertion in the suite.

### 4.4 The 14 packages missing from `.venv` — **INTENTIONALLY DIVERGE (2) / DEFER (12)**

**Intentionally diverge, by explicit instruction:** `peft`, `accelerate`, `bitsandbytes`.
The work order forbade installing `peft` into `.venv`, and section 4.1 explains why that
is right rather than merely obedient — it would force the transformers/hub downgrade
through the back door. `accelerate` and `bitsandbytes` are in the same GPU-serving family
and inherit the ruling.

**Defer, documented:** `beautifulsoup4`, `readability-lxml`, `pypdf`, `pytesseract`,
`pdf2image`, `faster-whisper`, `ctranslate2`, `hf-transfer`, `sentencepiece`, `psutil`,
`pydantic-settings`. All are lazily imported inside function bodies. A `.venv` test that
walks into one of those functions gets a clean, loud `ModuleNotFoundError` — a test that
*fails visibly* is not a test that lies, so the drift is self-announcing and safe to
carry. Install any of them on demand, when a suite actually needs it, which is exactly the
pattern that already played out this session with `Pillow`, `python-docx` and `lxml`.

### 4.5 Cosmetic drift — **DEFER, no action**

`anyio`, `certifi`, `charset-normalizer`, `click`, `filelock`, `hf-xet`, `idna`,
`markupsafe`, `numpy`, `packaging`, `regex`, `requests`, `urllib3`. Patch and minor
bumps on transitive dependencies with no assertion in the suite touching their behaviour.
Freezing them in `requirements-test.txt` (section 8) is enough; forcing them now buys
nothing.

---

## 5. Independent finding: the serving venv is off its own pin

    lxml     pinned 6.0.2     .venv-gpu 6.1.1     .venv 6.0.2

This is the one case where `.venv` is correct and `.venv-gpu` is not. `requirements-gpu.txt`
pins `lxml==6.0.2`; the serving venv is running 6.1.1. Nothing that was audited is broken
by it — `lxml` is used through `python-docx` for the DOCX export path, and that path's
tests pass — but it means `requirements-gpu.txt` no longer describes the serving venv
truthfully, which quietly undermines the value of every other pin in the file.

**Ruling: defer, but do not lose.** Either bump the pin to 6.1.1 (if 6.1.1 is what the
export path should run) or downgrade the serving venv to 6.0.2 (if the pin is the
intent). That is a one-line decision, but it is Chris's, and it touches the serving venv,
which the agent does not modify. It is recorded here so the next environment pass starts
from a known discrepancy rather than rediscovering it.

---

## 6. The drift that was actually making tests lie was not a package at all

This finding came out of the Lane 2/3 regression sweep, and it belongs here because it is
this lane's stated problem — the test environment causing tests to report the wrong thing —
in its purest form.

Most test files in this repo run offline by installing hand-written stub modules into
`sys.modules` before importing product code:

    if "pydantic" not in sys.modules:
        pstub = types.ModuleType("pydantic")
        class _BaseModel:
            pass
        pstub.BaseModel = _BaseModel
        ...

Thirteen files shipped that stub with a bare `pass` body. A bare `pass` satisfies
`class X(BaseModel)` at definition time, but **not** `X(id=..., label=...)` at call time —
which raises `TypeError: MemoirSection() takes no arguments`.

The `if "pydantic" not in sys.modules` guard means **whichever test file loads first wins**,
and every sibling in the same process silently inherits its stub. So a suite passed when
run alone and failed when run in a batch, or vice versa, purely on alphabetical load
order. `tests/test_memoir_trip_story_lane.py` ships the correct stub and passes alone;
paired with `tests/test_trip_location_notes.py` it died at collection with
`unittest.loader._FailedTest`, because that file's fastapi stub registered
`sys.modules["fastapi"]` without a `fastapi.responses` submodule, so any sibling loaded
afterwards that imports `api.routers.memoir_export` failed on import.

That is a test environment producing a result that has nothing to do with the code under
test. It is worse than the package drift above, because package drift at least fails the
same way every time.

**Fixed in this work order.** 16 files were swept: `_BaseModel` given a kwargs `__init__`,
`Field` replaced with a `default_factory`-aware `_field`, and `tests/test_trip_location_notes.py`
given the missing `fastapi.responses` submodule. Every rewrite was `ast.parse`-gated before
write. Full file list in the consolidated closeout report.

**Standing recommendation:** these stubs should eventually become one shared
`tests/_offline_stubs.py` imported by every offline suite, so there is one definition to
be right instead of thirteen to drift. That is a real refactor across ~30 files and is
**not** in this work order's scope — recorded here as the next environment-hygiene item.

---

## 7. Which environment is authoritative for which kind of test

This is the durable output of the lane. Future work should not have to re-derive it.

**`.venv-gpu` is authoritative for anything that touches the model stack.**
Concretely: any suite that imports `transformers`, `peft`, `accelerate`, `bitsandbytes`,
`faster_whisper` or `ctranslate2`, directly or through `api.py` / `chat_ws.py`. This
includes `tests/test_chat_ws_guard_failure.py` and the BUG-LORI guard suites. `.venv`
cannot run these — it will fail at `peft` — and that failure is correct behaviour, not a
defect to patch.

**`.venv` is authoritative for the HTTP/route/repository layer** — the eight TestClient
suites and everything below them — **only once section 4.2's alignment lands.** Until
then `.venv` is running starlette 1.0.0 against a server on 0.52.1, and a green result
there is weaker evidence than it looks. This is the single most important sentence in this
report.

**Either venv is fine for pure-python suites** — the source-assertion tests, the JS
source-literal tests, the sqlite repository tests. These import no framework and no model
code. They are also the only ones that run under the agent's device VM, which has bare
system python3 and no site-packages: 42 of the 44 `test_t*.py` suites run there cleanly.

**Bare system python3 is authoritative for nothing.** It is a convenience for the agent.
`tests/test_trip_draft.py` errors there with `ModuleNotFoundError: No module named 'fastapi'`
because it ships no offline stub and needs the real framework. That is a correct signal
about the environment, not a defect in the suite, and it must not be "fixed" by adding a
stub — that suite is testing real fastapi behaviour and should keep needing real fastapi.

---

## 8. Recommendation: `requirements-test.txt`

The audit's concrete deliverable. This file does not yet exist; creating it is the
follow-on action, and it is deliberately left for Chris to run because it requires network
the agent sandbox does not have.

The proposed contents pin the test venv's **web stack to the serving versions** (section
4.2), freeze the cosmetic transitives at whatever `.venv` currently has (section 4.5), and
say nothing at all about torch, CUDA or the model stack (section 4.3) — because
`requirements-test.txt` is not the file that describes those.

    # requirements-test.txt
    # Test-environment lock for .venv. Companion to requirements-gpu.txt,
    # which describes the SERVING venv (.venv-gpu).
    #
    # Rule: the web stack here MUST match requirements-gpu.txt exactly.
    # Eight suites drive fastapi TestClient against the real app; if these
    # drift, those suites validate a different framework generation than
    # the one that serves. See docs/reports/VENV_DRIFT_AUDIT_2026-07-27.md.
    #
    # This file deliberately does NOT pin torch, CUDA, transformers, peft,
    # accelerate or bitsandbytes. Suites that need those run in .venv-gpu.

    # --- web stack: must match requirements-gpu.txt ---
    fastapi==0.135.1
    starlette==0.52.1
    pydantic==2.12.5
    pydantic-core==2.41.5
    httpx==0.27.2
    uvicorn==0.41.0
    python-multipart==0.0.22

    # --- document/export path (already aligned, keep it that way) ---
    pillow==12.2.0
    python-docx==1.2.0
    lxml==6.0.2
    jinja2==3.1.6
    markupsafe==3.0.2

    # --- transitives, frozen at current .venv ---
    anyio==4.13.0
    certifi==2026.4.22
    charset-normalizer==3.4.7
    click==8.3.3
    h11==0.16.0
    idna==3.13
    packaging==26.2
    python-dotenv==1.2.2
    pyyaml==6.0.3
    requests==2.33.1
    typing-extensions==4.15.0
    urllib3==2.7.0
    websockets==16.0

**Install block (Chris runs this; do NOT run it blind — read section 4.2 first):**

    cd /mnt/c/Users/chris/hornelore
    .venv/bin/python -m pip install -r requirements-test.txt

**Immediately after, re-run the eight suites that this alignment is for:**

    cd /mnt/c/Users/chris/hornelore
    .venv/bin/python -m unittest tests.test_import_provenance_queue tests.test_import_provenance_routes tests.test_import_provenance_promote tests.test_memoir_export_security tests.test_trip_days_http_sequence tests.test_trip_days_sqlite_error_classification tests.test_extract_api_subject_filters

If any of those go red after the downgrade, that is the audit paying for itself — it means
the suite had been depending on starlette 1.0.0 behaviour that production does not have.

---

## 9. Acceptance check against the work order

| Lane 1 acceptance line | status |
|---|---|
| A checked-in report listing the important `.venv` vs `.venv-gpu` differences | this file |
| The `transformers` mismatch has a written ruling | section 4.1 — defer, with the reachability evidence and the environmental rule |
| Future work knows which environment is authoritative for which kind of test | section 7 |
| No model stack is broken | nothing was installed, removed or upgraded; torch untouched; `peft` not added to `.venv` |
| Existing BUG-LORI guard tests still pass | re-run green — see the consolidated closeout report |
