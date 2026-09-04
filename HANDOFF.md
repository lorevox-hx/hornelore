# HORNELORE HANDOFF

**Repository:** `lorevox-hx/hornelore` · **Branch:** `main`
**Reduced 2026-08-28** by `WO-REPOSITORY-HYGIENE-01` Step 2. Superseded narrative and
retirement notes were removed, not lost — they are in Git history and in the work orders
this file points to. **No new obligation was introduced** — the reduction removed
superseded narrative, not owed work. *(This said "nothing was added", which was literally
false: the reduction rewrote and restructured, and a later correction added the hard-delete
rule back. The claim that matters is the one about obligations.)*

---

> # ▶ CURRENT ACTION — `WO-LORI-ARCHIVE-TO-MEMOIR-02` PHASE 2. PHASE 1 IS CLOSED AND PROVEN.
>
> | | |
> |---|---|
> | **Current action** | **Phase 2 — the read-only 38-turn span/granularity ledger. NOT STARTED.** Rebuild from existing evidence; **do NOT rerun the cohort** |
> | **Phase 1** | ✅ **CLOSED AND PROVEN 2026-09-04.** `20260904T130158Z`, exit **0**, `Phase 1: PASS — full chain proven`. Preview PASS · export PASS · agreement canonical **1** / preview **1** / DOCX **1** · control byte-identical |
> | **Phase 0** | ✅ **ACCEPTED at `fdaa255`.** The evaluation is frozen |
> | **Mutations — ALL SPENT** | The two authorized mutations were performed in `20260904T123556Z`: placement `v1→v2`, promotion `v2→v3`. `447eee18` is now `promoted`, `building_years`/`operator_set`, `review_version: 3`. **NO further mutation is authorized by this record** |
> | **The proving run mutated NOTHING** | mode `promoted`, budget `0`, observed `0`, no blocked PATCHes, no refusals. Control `5a56f942` byte-identical |
> | **Contract guarantees held** | `containsSourceId: false` — no raw UUID in the document · `forbidden: []` — no known bad substitution reached the export |
> | **What Phase 1 does NOT claim** | **ONE** passage completes the chain. It says nothing about the other 27 archived-but-uncaptured statements, nothing about capture granularity, nothing about correctness at scale. That is Phase 2 |
>
> **A refusal is a result.** A run that stops before mutating, names the failing link and
> exits non-zero has done its job. It is not a failed attempt to be retried until it passes.
>
> **Profile Seed Phase 3 is OWED, not current.** It was the previous current action and is
> **IN IMPLEMENTATION with ACCEPTANCE OPEN**; it is not cancelled and not superseded — see
> §2. Hygiene Phase A remains
> ACCEPTED with its remainder PAUSED and `WO-REPOSITORY-HYGIENE-01` INCOMPLETE. **No priority
> change ever converts owed work into finished work**, and no document may say otherwise.
>
> **Still frozen:** runtime safety, the model and its 8,192-token window, the directive
> registry and Kawa are governed by `CLAUDE.md`, which no priority decision touches.

---

## 1. Read this first

When documents disagree:

```text
current code
> current tests and live evidence
> accepted closeout records and ADRs
> this handoff
> MASTER_WORK_ORDER_CHECKLIST.md
> old work-order status lines
> archived history
```

**Do not restart work from an old status line.** Read the implementation, its tests and its
latest live evidence first.

**Derive the live head. Never read it from a document:**

```bash
git rev-parse origin/main      # the live head, always
git status --porcelain         # must be empty before any gate
```

Fixed acceptance checkpoints stay written down, because they describe trees that have
stopped moving:

| Hash | What it is |
|---|---|
| `9127adb` | Profile Seed Step 5 accepted |
| `d0e5294` | Pre-Step-6 correction checkpoint accepted; tagged `archive/pre-hygiene-2026-08-28` |
| `ea3ab27` | Tree inspected by the repository audit; tagged `audit/repository-baseline-2026-08-28`. **Not** the rollback point |
| `5f6b01b` | Repository hygiene **Step 1** (indexes) accepted |
| `db0c5e7` | Repository hygiene **Step 2** (control authority) accepted |
| `ff1ff4f` | Repository hygiene **Step 2b** (changelog preservation) accepted |
| `5086490` | Repository hygiene **Step 3, first cohort** — the four root dated artifacts, moved byte-for-byte. **The last accepted hygiene commit; Phase A ends here** |
| `12221e0`…`58dfc40` | Profile Seed **Phase 2 Step 6** — implementation and correction block. **ACCEPTED 2026-08-29**, 16/16 live through the production WebSocket |
| `525a43f` | The Step 6 live probe, committed. Run 2's provenance rests on this |
| `6885bb2` | Profile Seed **Phase 2 Step 7** — consolidated closure and control reconciliation |

Where everything else lives: [`docs/INDEX.md`](docs/INDEX.md) ·
[`docs/BACKLOG.md`](docs/BACKLOG.md) · [`scripts/INDEX.md`](scripts/INDEX.md) ·
[`docs/archive/INDEX.md`](docs/archive/INDEX.md).

## 1a. Phase 2 acceptance evidence — by checkpoint and changed target

**Recorded this way deliberately.** A single "69/69 in one invocation" figure was NOT
produced and must not be claimed: the one full-gate attempt was interrupted, and stitching
its partial results onto earlier runs would manufacture an aggregate no invocation ever
reported. What follows is what was actually run, against what.

| Evidence | Scope | Result |
|---|---|---|
| Last complete clean-tree gate | all mutations at that checkpoint | **63/63 CAUGHT** |
| Step 6 changed-file mutations | WebSocket, runtime, REST — `D1`–`D4`, `S1`–`S6`, `S11`, `X1`–`X6` | **17/17 CAUGHT** |
| Follow-up-ruling composer mutations | `prompt_composer.py` after `8cc51b4` | **14/14 CAUGHT** |
| `C3` after its anchor repair | the instrument itself | **CAUGHT** (reported `BROKEN` first — the runner refusing to score a mutation it could not apply) |
| `C8`, `H4`, `H5`, `C16` at `291197a` | remaining composer guards | **4/4 CAUGHT** |
| Consolidated Phase 2 suites | eleven modules, derived from the tree | **436 ran, 6 skipped, 0 failed** on `python3` |
| Route coverage, zero skips | `.venv-gpu`, REST authority + strict version | **70/70, 0 skipped** |
| Live production WebSocket | two probe runs, real model | **16/16 each** |

**The untouched Phase 1 and reducer mutations were deliberately NOT re-run.** Documentation
changed; that code did not. Re-testing unchanged code to raise a count is ceremony, and
the count it produces is not evidence about this change.

---

## 2. Current state

| Lane | State |
|---|---|
| **`WO-LORI-ARCHIVE-TO-MEMOIR-02`** | 🔵 **ACTIVE — Phase 1 CLOSED AND PROVEN; Phase 2 is next. §9.** Phase 0 `fdaa255`. **Phase 1 PASS `20260904T130158Z`, exit 0** — full chain archive → placement → promotion → canonical → preview → export, agreement 1/1/1, control byte-identical, proving run mutated nothing. Both authorized mutations SPENT in `20260904T123556Z`; **no further mutation is authorized.** Phase 2 (read-only 38-turn span/granularity ledger) **NOT STARTED** |
| **Memory Integrity Layer / guardrail audit** | 🟡 **DESIGN THREAD — no work order yet.** Response-guard audit done; `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md` (repo root) is **ACTIVE / NEXT**. Nothing here is scheduled. §10 |
| **Repository hygiene** | ⏸️ **PHASE A ACCEPTED, REMAINDER PAUSED — the work order is INCOMPLETE.** Steps 0, 1 `5f6b01b`, 2 `db0c5e7`, 2b `ff1ff4f` and the first Step 3 cohort `5086490` are accepted. **Deferred by product-priority decision:** the remaining Step 3 cohorts, Steps 4–5, and the final verification checkpoint. Still indexed, still owed, not scheduled |
| **Profile Seed reachability** | ⏸️ **OWED — Phase 3 IN IMPLEMENTATION with ACCEPTANCE OPEN, and no longer the current action.** *(It was, until `WO-LORI-ARCHIVE-TO-MEMOIR-02` took priority. Owed work does not become finished work when the lane changes.)* Phase 0 `661aa95` · Phase 1 `1288baa` · **Phase 2 ACCEPTED 2026-08-29, steps 1–7 complete** (step 4 `b269184`, step 5 `9127adb`, pre-Step-6 corrections `d0e5294`, step 6 `12221e0`…`58dfc40` live, step 7 `6885bb2`) · Phase 3 implementation landed through `2b7e634`; its six acceptance conditions remain open. Phases 4–5 are partially run and not accepted. See the Profile Seed spec's reconciled status block |
| `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01` | **COMPLETE** — Phases 1–4 accepted. Closes the three L2 integration defects |
| `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` | **ACCEPTED AND COMPLETE 2026-08-20** — story-to-memoir 11/11, deletion integrity 10/10, verified against filesystem and SQL |
| Deletion / erasure integrity | **CLOSED 2026-08-20.** Erasure planned before the DB authority is destroyed, persisted (0049), bound to the canonical absolute root (0050); refuses every symlink below the root; eleven stores; deletes media; purges the translation cache; reports backups rather than rewriting them; fails closed; retryable with a truthful audit trail |
| Multi-day trip-photo placement | **COMPLETE**, Gate 3 accepted 2026-08-14. §4 |
| Photo Palette | **COMPLETE**, P4/P5 accepted 2026-08-14. Do not reopen for polish. §4 |
| Travel Document core/export | **CLOSED on live evidence.** Preserve the editable timeline → DOCX projection rule |
| Google Photos Picker | **BANKED.** Reopen only for a demonstrated defect |
| Lean Lori | **L1 COMPLETE. L2 PARTIAL and CLOSED by product-priority decision — DO NOT RESUME.** Eleven commits already landed; do not rebuild. **Gate B stays OPEN**, Phase 10 open |
| Legacy photo-day scalar retirement (Phase 6) | **DEFERRED — reopening requires Chris's explicit authorization. Not approved, not scheduled, not a decision currently on the table.** Palette and multi-day acceptance do not imply it. The scalar is frozen, unwritten, ignored for authoritative decisions and correctly derived on read; dropping it buys nothing and costs a risky SQLite rebuild. [`docs/BACKLOG.md`](docs/BACKLOG.md) §3b |
| Test-artifact **cleanup** | **DEFERRED — needs Chris's authorization.** The 22 harness narrators were deliberately not deleted |
| Kawa / Memory River | **REACHABLE FROZEN LEGACY UI.** Non-authoritative; do not extend, build on it, or describe it as retired in code. **Removal is NOT decided and NOT scheduled** — it needs Chris's explicit decision AND confirmed Life Map coverage |
| Runtime safety | **PARKED**, server-authoritative. Never reactivate through an environment value |
| Model / 8,192-token window | **LOCKED.** Any proposed change is stop-and-report |
| Directive-family registry | **INERT** — built, gated, deliberately not activated |
| Privacy canon extraction / history purge | **PARKED work order.** The authority for any history rewrite |

**Profile Seed, why it exists:** the ten-topic workflow is preserved and ordinarily
unreachable, because the intake supplies exactly what closes its own gate. Intake requires
name, DOB and birthplace; those three anchors are what chronology needs; chronology
promotes `pass1 → pass2a`; and the composer emits the ten-topic block only for an
identity-complete narrator **still in `pass1`**. The onboarding is **preserved for new
Lorevox narrators regardless of narrator type**; what is owed is reachability.

**Narrators are untouched.** The four family narrators and the designated non-family
narrator are all untouched. Six pre-existing `harness-test-gate7p2` FK violations in
`interview_sessions` are unchanged and are **not** closed by any current lane.

## 3. Step 6 — ACCEPTED: the boundary it honoured, and the result

**Preserved as the accepted record, not as a plan.** *(This section spoke about Step 6 in
the future tense — "Step 6 is the fix", "what it must not touch". Step 6 landed and was
accepted on live evidence; a section that still describes it as upcoming is the exact
stale-status defect this file has twice been reduced to remove. The boundaries below were
honoured and are kept because they still bind Phase 3.)*

**Result:** the walk reaches a narrator through the production WebSocket. Two probe runs,
16/16 each, real model. Presentation and response events commit on the assistant row;
advancement happens only after that commit; recovery runs before composition; the nine
deterministic paths stamp nothing.

### What it inherited and did not touch

**REST reads authority and DOES NOT ADVANCE**, and that is still true — Option B is
unchanged. The defect it caused: a narrator answered a topic and the durable row still
read `active=childhood_home · remaining=10 · version=2`, so across a session boundary Lori
asked for something she had already been told. **Step 6 fixed that on the WebSocket path**,
which is the path the narrator UI actually uses.

**WebSocket is the production narrator transport.** `ui/js/api.js` drives `/api/chat/ws`;
a complete narrator turn produces **zero HTTP requests matching "chat"**. `/api/chat` has
no UI caller; `/api/chat/stream` is reachable only behind the dev-only
`window.LV_ALLOW_SSE_FALLBACK`. **A narrator using the production UI reaches the walk at
Step 6.** The walk is already live over REST.

**No historical-narrator auto-enrollment.** Enrollment happens only inside
`create_person()`. All five existing narrators are `enrolled: false`. Extending it to
family narrators is a **backfill decision**, not a code change.

**Step 6 inherits, and must not undo** — from the accepted correction checkpoint:

* the **nine** deterministic persist paths, and the test that fails if a tenth appears;
* `HOLD` for every ineligible turn on an active walk — Step 6 supplies `eligible`, it does
  not re-decide what ineligibility means;
* one conversation-control vocabulary, in `services/conversation_control.py`;
* `expected_version` strict at **both** layers — the WebSocket path calls the accessor
  directly and inherits the second one, not the first.

`tests/test_profile_seed_deterministic_paths.py::Step6TripwireTests` fails the moment Step
6 adds Profile Seed metadata to `chat_ws.py`. That is deliberate: narrow it to the model
path, leave the nine covered.

**Step 6 must NOT touch:** REST persistence · UI promotion sites (Phase 3) · schema or
migrations · chronology · Life Map · memoir · story authority · safety (PARKED) · model /
8,192-token window (LOCKED) · directive-family registry (INERT) · Kawa (frozen legacy).
**Stop after focused implementation and tests, before Step 7.**

Detail: [`docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md`](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md)
§6, §6b, §16, §16a.

## 4. Product boundaries that bind

**Multi-day placement.** The authoritative model is a set of rows in
`trip_photo_day_placements`, not one nullable day on `trip_photo_links`. One photo and one
trip membership may have zero, one or many placements; one day may hold many photos; **Add
to this day**, **Remove from this day** and **Move** are distinct; removing one occurrence
preserves every other placement, membership, original, thumbnail, caption, approval and
context; explicit placements and taken-date suggestions are counted separately; shared
captions project across placements and **do not grant Lori approval**.

**The compatibility scalar is `null` for zero OR multiple placements and must never be
used to decide whether a photo is unplaced.** The authoritative unplaced rule is:

```text
zero trip_photo_day_placements
```

Never `trip_day_id IS NULL`.

**Hard-delete truthfulness.** **A deletion is complete only when the erasure result says
complete.** Three outcomes are distinguished and must stay distinguished; **HTTP 207 is the
operator-actionable partial** — something was removed, something was not, and the operator
can act on the difference. Never describe a hard delete as complete because the call
returned without raising. Retained audit and erasure-job metadata is kept on purpose and
**must contain no narrator speech**.

This is here, not only in its work order, because it is a rule a reader needs at the moment
they are looking at deletion behaviour. The defect it exists for was real:
`hard_delete_person` removed every active narrator-scoped row, answered **200**, and left
eight files on disk — five of them verbatim narrator speech. Detail:
[`docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md`](docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md).

**Photo Palette** is a mode inside the existing Travel Document workspace — not a second
product, not a nested modal. It reuses the landed inventory, thumbnails, placement APIs,
bounded-window helpers and trip/day state. It does **not** include destructive deletion,
face recognition, AI photo interpretation, duplicate originals or a schema rewrite.

Rulings: [`docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md`](docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md) 1.16.

## 5. Live-review artifacts — PRESERVE, NO DELETION AUTHORIZED

**Erasure of any narrator listed below takes Chris's
explicit authorization and must go through the product erasure path, with the result
reported truthfully. **No family narrator appears here and none was touched:** only the
three `ZZ` probes are enrolled in a Profile Seed walk, verified against the live database
on 2026-08-29.

| What | Exact IDs |
|---|---|
| **Del** (`6ad678ee-b295-49de-8578-da00200848ba`) | turns **1712–1717** on `switch_mtbn3x4a_ifo9`; **22 turns total** across all sessions |
| **`ZZ Step5 Probe (delete me)`** (`6e606ace-2a72-439a-8474-04140409098b`) | owns `zz-probe-seed-1`, turns **1718–1721** |
| **`ZZ Step6 WebSocket Probe (delete me)`** (`7d64b8be-8bbb-48a1-98cc-9ab1ce09421a`) | owns `step6-ws-probe-2026-08-28`, turns **1722–1731**; onboarding `active/siblings/v3`; `memory/archive/people/<id>` exists. **Step 6 live acceptance run 1** |
| **`ZZ Step6 WebSocket Probe 2 (delete me)`** (`9ae02617-6c6d-41f0-832d-41e82caba976`) | owns `step6-ws-probe-2-2026-08-28`, turns **1732–1741**; onboarding `active/siblings/v3`. **Step 6 live acceptance run 2 — the clean-tree, committed-instrument run** |
| `zz-probe-contradiction` | **no session, no turns** — the 409 fired before anything was written |

**Nothing has been deleted and no deletion is authorized.** The synthetic probe may be
hard-deleted through the product erasure path **only on Chris's explicit instruction**. Del
and all of his data are to be left alone.

## 6. Working and verification policy

* Work in coherent product blocks, not one-line review cycles.
* Focused tests while coding; one consolidated regression run at the end of the block.
* Mutation and non-vacuity tests only for load-bearing behaviour.
* Do not restart for documentation, tests, or harness-only changes.
* Keep the stack down through an implementation block. Start once for live acceptance,
  restart once for final persistence proof.
* Stop early only for schema risk, destructive live-data action, a security boundary, a
  model/configuration change, or a real design decision.
* **Report skip counts.** `OK (skipped=N)` is not a pass. Name the interpreter a result
  came from.
* **Claude prepares copy-paste `git add` + `git commit` blocks; Chris runs them and pushes
  from GitHub Desktop.** Agents do not run git here. A sandbox git command that hits the
  agent timeout on the `/mnt/c` 9p mount leaves `.git/index.lock` behind and silently
  blocks GitHub Desktop and Chris's own WSL git — presenting as "add succeeded, commit says
  nothing to commit, Desktop still shows N changed files". Read-only git is fine.

## 7. Known separate issues — not the current lane

Full register with evidence: [`docs/BACKLOG.md`](docs/BACKLOG.md).

* **Test Lab returns a 500.** `scripts/run_test_lab.sh` was archived by `c4ca24e`.
  **Repointing the constant is NOT the fix** — tried at `8e93262`, reverted at `b61f4a8`.
  The archived harness is not location-aware, so repointing returns `{"ok": true}` and the
  child dies in a log. Worse than the loud failure. A bounded task of its own.
* **Narrator composer collapses on a narrow viewport.** `#chatInput` is `flex: 1` with
  default `min-width: auto`; measured 39 px wide × 240 px tall at a 697 px viewport. Needs
  ~500 px of row width. A `min-width` fix was written and **withdrawn unverified** — it may
  clip Send. Open.
* **`scripts/ui/run_test23_two_person_resume.py` does not parse** — `IndentationError` at
  line 2082 from `df82215` (2026-05-06), so Test 23 has not run since. Spec:
  [`BUG-HARNESS-TEST23-INDENTATION-01_Spec.md`](BUG-HARNESS-TEST23-INDENTATION-01_Spec.md).
  **Do not repair it inside a product lane.**
* Six pre-existing `interview_sessions → people` FK violations from old harness narrators.
* Hard-delete filesystem residue root cause · legacy-column retirement · privacy canon
  extraction and public-history purge · broad `ws_chat`/extract-router decomposition ·
  model, prompt-window, STT, TTS and runtime-safety changes.
* **Bug Panel narrator label** — `_narratorLabel()` read three keys that do not exist on
  `state.session`, rendering `(unnamed)` for every narrator. Fixed `23cbdec`, covered at
  `5e7571c`. Recorded separately and deliberately not counted as lane evidence.

## 8. Required document set

| Document | Purpose |
|---|---|
| `HANDOFF.md` | Current state and next action. Nothing else |
| `MASTER_WORK_ORDER_CHECKLIST.md` | Active / next / deferred coordination |
| `CLAUDE.md` | Durable doctrine and prohibitions |
| `docs/INDEX.md` | Where documentation authority lives |
| `docs/BACKLOG.md` | Unresolved obligations, with evidence |
| `docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md` | The **paused** repository lane — Phase A accepted, remainder deferred and incomplete. **Not the current action;** `WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 1 is |
| `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md` + `..._PHASE2_TRANSPORT_MAP.md` | The owed Profile Seed lane — Phase 3 implementation landed, acceptance open |
| `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Binding Travel Document rulings |

Historical handoffs and long status narratives live in Git history and `docs/archive/`.
**They must not be appended back into this operational brief.**

## 9. `WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 1 — CLOSED AND PROVEN (2026-09-04)

> ✅ **EXIT GATE MET.** `20260904T130158Z`, exit **0**, `Phase 1: PASS — full chain proven`.
> Preview PASS · export PASS (`…__pat_structured.docx`, 36,975 bytes) · agreement
> canonical **1** / preview **1** / DOCX **1** · control byte-identical · **zero mutations in the
> proving run**. `containsSourceId: false` and `forbidden: []` — no raw UUID and no known bad
> substitution reached the document. Full closure record, including the seven defects found
> and fixed along the way, is in the work order.

*(The sections below are the working state that produced that result, kept as the record.)*

**Plan:** [`docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md`](docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md).
Phase 0 accepted at `fdaa255`. **Phase 1 is in implementation. Phase 2 is NOT STARTED.**

### The finding that reshaped the phase

**Runtime era is not a story placement, and conflating them is the bug this phase exists
to avoid.** The conversation Pat spoke in carried era `building_years`; her story candidate
carried none. `story_preservation.preserve` writes **every** candidate with
`era_candidates=[]` and no placement (`story_preservation.py:225`). **That is deliberate.**
Deriving a placement from whichever screen the narrator happened to be on is how a story is
filed into the wrong memoir chapter; `story_projection` already refuses it, and the route
enforces the same rule from the other side — *"an operator-set placement needs exactly one
era; two eras is not a placement, it is a pair of guesses"* (`operator_story_review.py:366`).

**Consequence, and it binds Phase 2:** a candidate can be **promoted and still reach
canonical memoir unplaced**. Promotion decides *eligibility*; placement decides *where it
goes*. The ledger must record them as two destinations, never one.

### Authorized mutations — the whole authorization

| | |
|---|---|
| Target | `447eee18-9ea5-4961-bf3d-157773d3cd44` (Pat), currently **unplaced, `unreviewed`, `review_version: 1`** |
| Mutation 1 | **Placement** — era selector → `building_years`, then `Save placement / notes`. Sets `placement_source=operator_set` in the same gesture |
| Mutation 2 | **Promotion** — that row's `Promote`, at the version the placement returned |
| Control | `5a56f942-001b-453b-8e4d-01fb82062013` — **must stay byte-identical**, verified in `finally` |
| Budget | Enforced in flight: fresh run 2, resumed-at-placement 1, fully-resumed **0** |

**Nothing beyond these two is authorized.** A third mutation, a wrong order, or any PATCH to
another candidate is aborted before the request leaves the browser.

### Live-run history

| Run | Outcome | Mutations | Cause / result |
|---|---|---|---|
| `20260901T212134Z` | **DESIGNED REFUSAL** | 0 | Demanded a placement the candidate never had. **Produced the runtime-era finding** |
| `20260901T232656Z` | **UNHANDLED ERROR** | 0 | Probe-selector defect: `#lv10dBugPanelBtn` does not exist |
| `20260904T120642Z` | **DESIGNED REFUSAL** | 0 | 2 of 5 rows matched the passage text. **Produced the granularity finding** |
| `20260904T123556Z` | ✅ **BOTH MUTATIONS PERFORMED** | 2 | Placement `v1→v2`, promotion `v2→v3`, order `placement>promotion`, provenance unchanged, control identical |

**Preserve every run directory under `.runtime/eval/phase1-memoir-chain/`.** §5's no-deletion
rule governs them, and three of the four are the evidence for findings now in the WO.

### What `20260904T123556Z` proved, and what it did not

**PROVEN — the chain reaches canonical.** `1_preconditions` · `1b_narrator_active` ·
`2a0_bug_panel_open` · `2a0_section_expanded` · `2a_filter` · `2_row_located` ·
`2b_detail_verified` · `3a_placed` · `3a_verify_placement` · `3b_row_refetched` ·
`3b_promoted` · `4_canonical` all PASS. Canonical returns the passage **exactly once**, with
`era=building_years`, `source_id=5d57a43ce780`, `lane=captured_story`, `complete=true`.

**NOT PROVEN — preview and export.** `5_preview` FAILS. Both memoir-opening stages were
found and clicked (`stage2.label = "Open your memoir"`), but the popover never became
visible and contained the passage 0 times. **The cause is named and confirmed live:**
`ui/hornelore1.0.html:8551` fetches `/api/memoir/canonical` **relative**, so it resolves to
the UI server. Three UI-issued requests, all `404` off `:8082`; the identical query against
`:8000` returns `200`. Export is `not_reached` **by design** — the probe refuses to attempt
an export whose preview never rendered.

**This is not a regression and not a canonical failure.** It is a one-line origin defect in
the UI, sitting between a working canonical API and a working memoir popover. Fixing it is
a product change and is **not authorized by this record.**

### Target state after the run — READ THIS BEFORE RE-RUNNING

`447eee18` is now **`promoted`**, placed **`building_years`/`operator_set`**,
**`review_version: 3`**. The control `5a56f942` is byte-identical and untouched.

**The next run must be `--resume 20260904T123556Z`** — mode `promoted`, PATCH budget **0**,
so it verifies and continues downstream while mutating nothing. A fresh run would refuse at
preconditions, correctly, because the target is no longer unplaced.

### Harness — all offline, all green on `.venv`

`Ran 116 — OK`, **zero skips** on `.venv/bin/python` (the Playwright tests skip only in an
agent sandbox, which has no browser binary).

- `scripts/ui/phase1_memoir_chain_probe.js` — the live probe. `--self-test` runs offline
- `scripts/ui/phase1_bugpanel_launcher_domtest.js` — launcher contract, **12/12**
- `scripts/ui/phase1_placement_workflow_domtest.js` — placement workflow against the **real
  shipped panel module**, **22/22**
- `scripts/ui/phase1_row_selection_domtest.js` — row selection, **21/21**
- `tests/test_phase1_memoir_chain_probe.py` — 116 offline contract guards

```bash
cd /mnt/c/Users/chris/hornelore
node scripts/ui/phase1_bugpanel_launcher_domtest.js
node scripts/ui/phase1_placement_workflow_domtest.js
node scripts/ui/phase1_row_selection_domtest.js
PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_phase1_memoir_chain_probe
```

Then, and only when all four are green:

```bash
cd /mnt/c/Users/chris/hornelore
node scripts/ui/phase1_memoir_chain_probe.js
```

**Expected partial failure, already known and NOT a regression:** preview and export fail
because `ui/hornelore1.0.html:8551` fetches `/api/memoir/canonical` **relative**, resolving
to `:8082` and 404ing. The probe reports that as `failed — wrong API origin` and does not
confuse it with a real canonical failure. Canonical itself is queried against `:8000`.

### Owed before the next live attempt

- **Confirm the tree is clean.** The launcher fix is pushed at `369e9aa`; no launcher work
  remains before the run. `git status --porcelain` still decides local cleanliness.
- Nothing else. The next attempt is a **fresh run, no `--resume`**.

## 10. Memory Integrity Layer — design thread, nothing scheduled

A guardrail audit ran alongside Phase 1. **No work order exists and nothing here is
approved.** Recorded so the thread is not lost or mistaken for a plan.

**What is real in the tree today:** `lori_response_guards.py` is 1,294 lines exposing
**7 `detect_` / 7 `repair_` pairs** — every detector has a repair partner. It contains **no
environment gate: the response guards are unconditional.** Do not assume they behave like
runtime safety, which is PARKED behind a decision.

**Known gaps, both with specs or diagnoses, neither scheduled:**

- **Stub collapse** — detection and `compose_stub_collapse_repair()` both exist in
  `lori_communication_control.py`, outside the unconditional detect/repair family. The
  repair runs only with the enclosing communication-control layer. The open work is to
  evaluate its benefit and false-positive rate, reconcile the stale root spec, and decide
  whether it belongs in the common response-guard architecture — not to build a missing
  repair.
- **Few-shot exemplar leakage** — `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md` **at the repo
  root**. Its own status line reads **`ACTIVE / NEXT (deferred until after stub-collapse +
  harness G4 ports land)`** — so the repo already sequences stub-collapse first, and that
  dependency is the spec's, not a preference. Proposes placeholder examples plus
  `detect_exemplar_leak()`.
  *(A search scoped to `docs/wo/` misses it. Legacy `BUG-*_Spec.md` files still sit at the
  root awaiting the archive cohort — see `CLAUDE.md`.)*

**The design position reached, for whoever writes the work order:**

> We do not want a weaker Lori. We want a knowledgeable Lori with a disciplined boundary
> between *what I know about the world* and *what I know about you*.

The constraint is on **attribution, not on knowing**. World knowledge predicated of the
world is allowed and is one of Lori's main assets for cueing recall; an ungrounded specific
predicated of *the narrator* is not. The proposed guard is
`detect_ungrounded_personal_claim`, and its acceptance pair is: *"Bismarck was a much
smaller city then"* must PASS, *"You stopped in Flagstaff"* must FAIL. **A guard that cannot
separate those two is not ready** — and over-applying this rule produces the intake-clerk
failure `CLAUDE.md` principle 8 exists to prevent.

**Still unmeasured, and the next evidence task:** the first complete raw-vs-delivered Walt
trace has already shown post-generation damage, but the nine layers still lack per-guard
false-positive rates across a broader cohort. Use the trace for per-guard fire rates plus a
judged sample. The guards were tuned against **synthetic** narrators, so any synthetic
cohort number is a floor, not an estimate.
