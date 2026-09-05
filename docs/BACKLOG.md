# Backlog — unresolved obligations, with their evidence

**Baseline derived at:** `d0e52946aa77096841612df176f4cbb70d4edacd`
**Maintained live** by `WO-REPOSITORY-HYGIENE-01` — entries are added and resolved as work
lands, so **this is not a snapshot of the `d0e5294` tree.** Any figure that is a `d0e5294`
measurement says so; volatile populations are commands, not prose.
**Status:** registry only — nothing here is scheduled. Everything is **unresolved**
except **§4**, which is a **resolved record** kept so a later session does not re-open it.

---

## Why this file exists

**"Archived" must never come to mean "decided."**

The repository is about to move a large amount of historical material. Some of those
documents contain obligations that are still open — a bug nobody fixed, a phase nobody
built, a status header that says `ACTIVE` about work that stopped in July. If a document
moves to `docs/archive/` and the obligation inside it is not written down somewhere live,
the obligation disappears, and it disappears *quietly*, which is the worst way.

This file is the somewhere-live. **An item may only leave the repository root or
`docs/wo/` once it appears here.**

It is not a plan and it is not a queue. `MASTER_WORK_ORDER_CHECKLIST.md` owns the ordered
queue; `HANDOFF.md` owns the current action. This file owns *"what is still owed, and how
do we know"*.

**Status headers are not trusted here.** The audit found 14 of 30 root specs saying
`CLOSED` or `LANDED`, one of which is explicitly only partially landed, and three with no
clear status at all. Every entry below records what the document *claims* and, where they
differ, what the tree actually shows.

---

## 1. Blocking the current lane — nothing

The five pre-Step-6 product corrections and the two acceptance-instrument corrections are
**accepted at `d0e5294`**. **Phase 2 Step 6 is no longer blocked** — the hygiene sequencing
gate was superseded on 2026-08-28 by Chris's product-priority decision, and Step 6 is the
current action. Nothing in this file blocks it.

**One consequence belongs here rather than in a status document.** That decision defers the
remaining hygiene Step 3 cohorts and Steps 4–5, and those steps carried a precondition:
**the root `WO-*`/`BUG-*` specs may not move until their unresolved obligations appear in
§2, and the later cohorts owe the same treatment §9 gave the first.** Deferring the moves
defers that work too. §2 and §9 stay accurate for what has been examined; they are **not** a
complete registry of the unexamined cohorts, and no later session should read them as one.

---

## 2. Root specifications with unresolved or unclear obligations

The root specs must each be represented here before their full specs move. **The sixteen
below carry unresolved or unclear obligations** — the audit named fifteen; the sixteenth is
new, see §2.1. For the current root population:

```bash
git ls-tree -r --name-only origin/main | grep -cE '^(WO-|BUG-)[^/]*\.md$'
```

| Spec | Header claims | What is owed |
|---|---|---|
| `BUG-LIFEMAP-COMM-CONTROL-TRIM-01_Spec.md` | `OPEN — observed 2026-06-17` | Never started |
| `BUG-LIFEMAP-CONTEXT-TRUNCATION-01_Spec.md` | `OPEN — observed 2026-06-17` | Never started |
| `BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01_Spec.md` | `ACTIVE / NEXT` | "Next" since July; not started |
| `BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01_Spec.md` | `PARTIALLY LANDED 2026-07-02` | **The explicit partial.** Deterministic half landed; the remainder is unbuilt and unscoped |
| `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md` | `ACTIVE / NEXT (deferred until after stub-collapse)` | Blocked on `BUG-LORI-RESPONSE-STUB-COLLAPSE-01` |
| `BUG-LORI-META-PREAMBLE-LEAK-01_Spec.md` | `Filed: 2026-07-07` | Filed, never started |
| `BUG-LORI-RESPONSE-GUARDS-STALE-TRIP-SURFACE-DOCSTRING-01_Spec.md` | `ACTIVE / SMALL CLEANUP` | Small and open; a docstring describing a surface that moved |
| `BUG-LORI-RESPONSE-STUB-COLLAPSE-01_Spec.md` | `ACTIVE (active rewrite of pre-pivot spec)` | Blocks the exemplar-leak bug above |
| `BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01_Spec.md` | `OPEN — observed 2026-06-17` | Interacts with `WO-LORI-ENGLISH-FIRST-SESSION-MODE-01` |
| `BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01_Spec.md` | `FILED 2026-07-09 (not started)` | Says so itself |
| `WO-LORI-ENGLISH-FIRST-SESSION-MODE-01_Spec.md` | `ACTIVE / PHASE 1 LANDING` | Phase 1 landing; later phases unbuilt |
| `WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01_Spec.md` | no clear status in the opening block | **Status unknown — must be adjudicated before it moves** |
| `WO-TRIP-INTERVIEW-CONTEXT-01_Spec.md` | no clear status in the opening block | **Status unknown** |
| `WO-TRIP-LORI-ANSWER-CAPTURE-01_Spec.md` | no clear status in the opening block | **Status unknown.** Step 1 service exists and is live-wired; later steps unclear |
| `WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01_Spec.md` | `SUPERSEDED for status tracking` — a living copy exists in `docs/wo/` | Two copies of one work order. The root copy must not move until the pair is reconciled |
| `WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01_Spec.md` | `banked 2026-07-08 from Chris's review` | Banked by decision — deliberately not built |

### 2.1 New since the audit

| Spec | State | Owed |
|---|---|---|
| `BUG-HARNESS-TEST23-INDENTATION-01_Spec.md` | **OPEN, bounded, unscheduled** | `scripts/ui/run_test23_two_person_resume.py` has not parsed since `df82215` (2026-05-06). Repair owes: correct indentation *deliberately* (inside or outside the per-narrator loop — the traceback does not say which was meant), a live run, **and a compile gate over `scripts/` and `tests/`**. The gate is the part that matters; three and a half months of silence is the real defect |

**Appendix A of the audit enumerates the root specs as they stood at `ea3ab27`. At least one
has been filed since** — `BUG-HARNESS-TEST23-INDENTATION-01`, at `157af46`. The audit is
never edited; the
[verification addendum](reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28_VERIFICATION_ADDENDUM.md)
§3 records the amendment, and the command above gives the current figure.

---

## 3. `docs/wo/` — parked, banked, and spec-only work

A mix of active implementation specs and completed, superseded, parked and future-only
documents. **Many are not named by any governing document — a triage signal, not proof of
deadness.** The Profile Seed transport map was itself unreferenced by filename while being
the most current design document in the tree; it is linked now, and that episode is the
reason an absent reference never authorizes a move.

```bash
git ls-tree -r --name-only origin/main -- docs/wo | wc -l
```

Deliberately not built, and each must stay reachable:

| Document | State |
|---|---|
| `WO-PRIVACY-CANON-EXTRACTION-01_Spec.md` | **PARKED.** The authority for any history rewrite or public-history purge. Not part of this cleanup |
| `WO-TRIP-MEMOIR-01_Spec.md` | **PARKED / DO NOT IMPLEMENT YET** |
| `WO-LOREVOX-MULTI-OPERATOR-GOOGLE-AUTH-01_Spec.md` | **FUTURE DESIGN ONLY.** No token tables, no encryption, no multi-user auth without Chris explicitly opening it |
| `WO-LEAN-LORI-PROFILE-SEED-DECISION-BRIEF-2026-08-14.md` | **DECISION REQUESTED**, nothing implemented |
| `WO-TRAVEL-DOC-PICKER-QUEUE-REF-LEAK-01_Spec.md` | SPEC ONLY, no code |
| `WO-TRAVEL-DOC-PICKER-REINGEST-REPAIR-01_Spec.md` | SPEC ONLY, no code |
| `WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md` | SPEC, not started — **safety is parked; do not reactivate through an environment value** |
| `WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md` | SPEC, not started — same boundary |
| `WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md` | SPEC, not started |
| `WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md` | SPEC, not started |
| `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md` | SPEC, depends on the safety classifier |
| `WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md` | SPEC, not started |
| `WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md` | SPEC, revised 2026-06-11 |
| `WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01_Spec.md` | SPEC, designed 2026-06-15 |
| `BUG-LORI-SEEDED-SELF-FACT-DODGE-01_Spec.md` | OPEN, not started, filed 2026-08-12 from live evidence |
| `BUG-LORI-REASONING-LEAK-01_Spec.md` | CODE-LANDED, **not yet live-verified** |
| `WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01_Spec.md` | Phases 5 + 1 landed; **phases 2–4 and 6–9 unbuilt.** The living copy of the root duplicate |
| `WO-LEAN-LORI-RUNTIME-01-FINAL-R3-2026-08-04.md` | ACTIVE — implementation in progress |
| `WO-TRIP-IMPORT-AND-CLUSTER-01_Spec.md` | ACTIVE — phases 1+2 opened |
| `WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md` | ACTIVE — partially implemented |
| `WO-STORY-CANDIDATE-TEXT-CHAIN-PERSISTENCE-01_Spec.md` | ACTIVE, queued behind three behaviour bugs |
| `WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md` | ACTIVE |
| `WO-LORI-FACTUAL-CHAIN-CAPTURE-01_Spec.md` | ACTIVE / NEXT |

**Lean Lori L2** is PARTIAL and closed by product-priority decision. **Do not resume**;
Gate B stays open and substantial work is already in-tree.

---

## 3a. Test-expectation reconciliation owed — `tests/test_lori_witness_mode`

**Seven assertions conflict with later deliberate behaviour.** They split cleanly:

| Count | Expectation | Conflicts with |
|---:|---|---|
| **4** | three-anchor cascade output | the **accepted two-anchor cap** |
| **3** | the retired broad correction behaviour | its deliberate retirement |

**These are test-expectation reconciliation, NOT automatically product defects.** The
behaviour they contradict was changed on purpose and accepted; what is unresolved is that
the older module still asserts the earlier contract. Reconciling it means deciding, per
assertion, whether the test encodes something still wanted — in which case the product
question reopens — or whether it encodes a superseded contract and should be updated to the
accepted one. **Do not "fix" them by loosening assertions until that decision is made.**

Owned by the Witness lane, not by any current lane, and explicitly not a reason to divert
the active work.

*(Recorded here 2026-08-28. This was in `HANDOFF.md` §2 and Step 2's reduction removed it;
its only surviving copy was inside `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md`,
which is marked **COMPLETE**. A live obligation reachable only from a completed work order
is the "archived means decided" failure this file exists to prevent — committed, in this
instance, by the same commit that wrote the rule.)*

## 3b. Deferred authorization boundaries — reopening requires Chris

Not backlog items to schedule. Recorded so that neither the deferral nor the open question
inside it can quietly disappear.

**Palette legacy-column retirement (Phase 6) — drop `trip_photo_links.trip_day_id`.**

* **NOT approved, NOT scheduled, and NOT a decision currently on the table.** Reopening it
  requires **Chris's explicit authorization**.
* Palette and multi-day acceptance **do not imply it**, and the old handoff said so.
* The scalar is frozen, no longer written, ignored for authoritative decisions, correctly
  derived on read, and covered by tests and live evidence. Dropping it buys no product
  benefit and costs a risky SQLite table rebuild with its own rollback plan.
* **The compatibility scalar is `null` for zero OR multiple placements**, so it must never
  be used to decide whether a photo is unplaced. Authoritative rule: zero
  `trip_photo_day_placements`. `HANDOFF.md` §4.

*(The open decision — "decide separately whether to authorize legacy-column retirement" —
lost its last live home in Step 2. The deferral survived in the checklist; the fact that a
decision is outstanding did not.)*

## 4. Control-document corrections — RESOLVED

All five landed in `659896c` (Step 2), `db0c5e7` (Step 2 correction) and — the changelog
row — hygiene **Step 2b**. Retained as a record so a later session does not re-open them;
**nothing here is owed.**

| Where | Was | Resolved by |
|---|---|---|
| `CLAUDE.md` | hand-written count of the pre-pivot archive | a derived command |
| `CLAUDE.md` | stale `.venv` fastapi claim | a measure-it probe, plus the interpreter-probe block |
| `CLAUDE.md` | "where files live" row naming the repo root as *the* WO location | `docs/wo/` named as the only active location |
| `README.md` | duplicated lane status | a pointer table; current state has one home |
| `docs/CHANGELOG-AGENT.md` | 614,130 bytes, pointed at by `CLAUDE.md` | **RESOLVED by hygiene Step 2b** — preserved byte-for-byte at [`archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md); the live path is now a small decision index |

---

## 4a. Documentation portability — a link no clone can resolve

`docs/wo/WO-LEAN-LORI-RUNTIME-01-FINAL-R3-2026-08-04.md` links to
`docs/reports/LEAN-LORI-PHASE-8-STATE-MATRIX-2026-08-09.md`. **`docs/reports/` is gitignored**
(since `a87e865`, because reports carry live narrator data and this repository is public), so
that target exists on Chris's machine and **in no clone at all**. A whole-tree link check
reports it broken, correctly.

**Pre-existing, and not a Step 2b regression.** The link predates the hygiene lane; the file
is untouched by it. It surfaced only because Step 2b ran the first whole-tree link validation.

**Do NOT resolve it by adding the report or editing `.gitignore`.** The gitignore rule is
deliberate and load-bearing — `CLAUDE.md` is explicit that a report refusing to stage is the
feature, and re-publishing reports requires the redaction plan in
`WO-PRIVACY-CANON-EXTRACTION-01`, which is parked.

**What is actually owed** is a convention for citing local-only evidence, so a reader can tell
"this link is broken" from "this evidence is deliberately local". The Palette closeout already
solved it once, by naming report paths as plain text with `(local working copy only)` rather
than as links. Applying that convention here is the small fix; deciding it repository-wide is
the durable one. Either way it is a documentation commit, not a hygiene move.

---

## 5. Tooling defects — repairs, not archival

All four reproduce at `d0e5294`. Bounded tooling commits, separate from cleanup.

* `package.json` `main` → nonexistent `tailwind.config.js`
* `package.json` `license: ISC` vs the Lorevox Source-Available Proprietary `LICENSE`
* **7 npm script entries** → **4 distinct nonexistent** Playwright specs
* `playwright.config.ts` → nonexistent `scripts/start-lorevox-audit.sh`
* **Test Lab** points at nonexistent root script paths. **Repointing it at
  `scripts/archive/` is known to fail after returning a false success.** Separate bounded
  lane; do not attempt in passing

---

## 6. Verification posture

| Item | Detail |
|---|---|
| The mutation gate runs on the interpreter least able to exercise route tests | Documented command is `python3`; there the strict suite reports `22 ran, 5 SKIPPED` and `test_profile_seed_rest_read_authority` reports `48 ran, 6 SKIPPED`. The `S`-series mutations target `api.py` and `profile_seed_rest.py`. Decide whether the gate should now run under `.venv` |
| Six skips in `test_narrator_refusal_characterization` | Unexamined. Four mutations (`R1`, `R2`, `T1`, and the curly-apostrophe case) depend on that suite |
| ~~No compile gate over `scripts/` and `tests/`~~ | **CLOSED 2026-09-05** — `tests/test_scripts_compile.py`. Byte-compiles every tracked `.py` under `scripts/` and `tests/`, names the three UI harnesses explicitly so a discovery change cannot silently drop them, and carries a positive control planting the original defect's shape |

### 6b. `bio_fact_router` provenance is null in production — and a test hides it

**FOUND 2026-09-05 by external review, verified by execution here. Belongs to Phase 5C.**

`extract.py:9748-9749` passes `session_id=getattr(req, "conv_id", None)` and
`turn_id=getattr(req, "turn_id", None)` into `bio_fact_router`. **Neither `conv_id` nor
`turn_id` is a field on `ExtractFieldsRequest`** — confirmed by listing `model_fields` — so
**both are `None` on every production call.** Worse: **`session_id` IS a real field on that
model**, sitting unused while the caller asks for a name that does not exist.

So every production-routed bio fact records `session_id: None, turn_id: None`. The router
stores both faithfully (`bio_fact_router.py:363-364`); it is handed nothing.

**And the suite cannot see it.** `tests/test_bio_fact_router*.py:219` calls the router
directly with `session_id="s1", turn_id="t1"` and then asserts at `:230-231` that those
values were persisted. **The fixture supplies the exact property being proven**, and the
production caller — which supplies neither — is never exercised. A textbook instance of the
rule in [`docs/TESTING-DOCTRINE.md`](TESTING-DOCTRINE.md), found in the wild rather than by
mutation.

**Fix in Phase 5C**, where source-turn linkage is already scoped: provenance should come
from the completed-turn claim, not from ids guessed off the request. Add the
production-boundary companion test at the same time — the helper-level one passes today and
will keep passing.

### 6a. Measurement debt — the extraction baseline is not comparable

**NONBLOCKING. Nothing in the current lane waits on it.** Registered so the numbers stop
being quoted as though they were commensurable.

**Re-score the stored `r5h-followup-guard-v1` outputs under scorer `318df0d2ff1f`** to
establish a comparable extraction baseline. The historical **78/114** run used scorer
`cc7dd27507b4` and a **dirty tree** (`git_dirty: True`, `7c2b1f1`); it must not be used for
causal regression claims until normalized.

**Three scorers span the runs that get compared to each other:**

| Run | Cases | SHA | Tree | Scorer | Case bank |
|---|---|---|---|---|---|
| `r5h-followup-guard-v1` | 78/114 | `7c2b1f1` | **dirty** | `cc7dd27507b4` | `b487e54cd84d` |
| `r5j-phase3-v1` | 60/114 | `8aba910` | **dirty** | `591f56e47f89` | `b487e54cd84d` |
| `r5k-guard-v2` | 71/114 | `5afead5` | clean | `318df0d2ff1f` | `b487e54cd84d` |

The case bank is identical across all three, so the *cases* are comparable and the *scores*
are not. The r5h→r5k delta is **−7 total, −5 v3, −4 v2**, with **14 regressions and 7 fixes**
— and it measures the scorer and the extractor together. Nine of the fourteen regressions
fall from exactly `1.00`, several acquiring a failure category absent from their r5h row;
`case_073` moves `1.00 → 0.55` with an **empty failure-category list on both sides**, which
is scorer movement or it is nothing.

**What may and may not be said today:**

* `r5k-guard-v2` reports **0 `must_not_write` violations at `5afead5` on a clean tree**.
  That is solid CURRENT evidence.
* The **`2 → 0` delta is NOT established.** `must_not_write` is a scorer judgment, so the
  improvement cannot be claimed until r5h is re-scored. *(An earlier draft called it a
  scorer-independent improvement. It is not.)*

Settling this is a **re-scoring pass over stored outputs, not a new evaluation.**

---

## 7. Deferred by standing decision — not backlog, and not to be promoted quietly

From `CLAUDE.md`. Listed so nobody mistakes their absence for an oversight: Picker orphan
reconciliation; multi-operator Google auth; a generalized import-destination framework;
the three-source chooser; safety reactivation; model replacement; context-window
expansion; a broad inference coordinator; a framework rewrite; mass migration cleanup;
automatic historical rewrite of stored `[SYSTEM:]` rows.

**Deferred is not forgotten. Deferred means intentionally not active.**

---

## 8. Preserved boundaries — never archive candidates

Parked runtime safety (server-authoritative; reactivation takes Chris's explicit
decision) · frozen Kawa / Memory River, reachable legacy UI awaiting adjudication · the
inert directive-family registry · compatibility readers · migrations `0001–0051` · the
main `tests/` tree · Profile Seed onboarding preservation tests.

---

## 9. First Step 3 cohort — obligations preserved from dated artifacts

**Precondition for the move, not a record of it.** `WO-REPOSITORY-HYGIENE-01` §4 schedules
four root dated artifacts as the first Step 3 cohort. **The dated artifacts contain
actionable claims that were not fully represented in the live backlog. This section records
their current disposition before the artifacts move.** Several of those claims already have
owners in `MASTER_WORK_ORDER_CHECKLIST.md` or in a work order, and are cross-referenced
rather than restated; `HANDOFF_2026-07-01.md` contributes only resolved or superseded items,
recorded at §9.6. `clock_mockups_v1.html` contributes none — it is a design mockup with no
runtime references.

**Every entry cites its source artifact and section.** Where a checklist row or work order
already owns an item, the entry points at that owner rather than restating its status;
acceptance hashes are deliberately absent, because `HANDOFF.md` §1 is their one home.

**A classification here is evidence, not old status prose.** "Verified" means the defect
condition was observed in the current tree during the 2026-08-28 pre-move audit.
"Unverified" means the finding is an August-2026 review measurement that a read-only audit
could not reproduce — the cited line numbers have moved, or the claim is about the operator's
machine rather than the repository. **An unverified finding is not a current defect claim.**

### 9.1 Verified current defects

| Item | Source | Observed 2026-08-28 |
|---|---|---|
| WS receive loop catches only `WebSocketDisconnect` | Review §2 S3 | `chat_ws.py` receive loop; a malformed frame still skips cancel-event cleanup |
| REST `/api/chat/stream` stop event is dead wiring | Review §2 S4 | `ev.set()` occurs **zero** times in `server/code/api/api.py` |
| REST chat persists `msgs[-1]` as `role='user'` regardless | Review §2 S6 | `api.py:793` — the misattribution class `WO-SYSTEM-DIRECTIVE-PERSISTENCE-01` exists to prevent |
| `index.json` read-modify-write is neither locked nor atomic | Review §2 S9 | no `os.replace` in `server/code/api/archive.py` |
| No size cap on the direct photo upload lane | Review §2 S10 | no cap constant in `routers/photos.py`; the picker lane it "matches" enforces 50MB |
| DST-skewed log-timestamp conversion skews warm/idle classification | Review §2 S15 | one `time.mktime` use remains, at `services/stack_monitor.py:546` |
| Memoir save replaces the structured `<section>`/`<mark data-narrative-role>` DOM | Review §3 U4, §11.3, §12.4 | escaping half landed; the structural half was recorded as needing its own WO and none exists |
| Production shell starts Test Lab polling unconditionally | Review §3 U9 | `ui/hornelore1.0.html:10091` — two never-cleared intervals per operator session. **Repointing Test Lab is a known false-success lane; treat as bounded.** |
| `sysBubble()` narrator-dignity pass | `PLAN_2026-07-13` §C2 | 28 calls in `ui/js/app.js`, 7 gated. Design principle 2 (no operator leakage) applies to the remainder |
| Dead `_UNTRUSTED_DATE_LEVELS` constant | `PLAN_2026-07-13` §C6 | still at `services/trip_photo_clustering.py:103` |
| `story_candidates` extraction Path 2 | `PLAN_2026-07-13` §D2 | `extraction_status` / `extracted_fields` and a working setter, with **no callers outside `db.py`**. Preserved narrator memories unused. Draft candidates behind operator review only — never auto-promote |
| `utterance_frame` has no product consumer | `PLAN_2026-07-13` §D3 | `chat_ws.py` builds a frame behind `HORNELORE_UTTERANCE_FRAME_LOG` and passes it to `logger.info` and nowhere else. Still log-only |
| `.env` flag-audit work order | `PLAN_2026-07-13` §C4 | never written. Documented-versus-read flag drift already cost real time |
| Whole-tree `discover` isolation acceptance undemonstrated | `PLAN_2026-07-13` §A1 | the two named `DB_PATH` sites now save and restore, and `tests/__init__.py` sets a temp path — but A1's acceptance ("no spurious trips-table errors under full discover") has never been shown, and `CLAUDE.md` still mandates per-module runs |
| `CLAUDE.md` cross-suite contamination reference is **semantically misdirected** | found during the 2026-08-28 pre-move audit | `CLAUDE.md` sends the reader to `HANDOFF.md` §7 for cross-suite state contamination. **§7 exists; it does not document that subject.** The section link resolves — the claim it makes about the target does not. Introduced by the Step 2 `HANDOFF.md` reduction. Fix the pointer or restore the content; do not describe this as a broken link |
| Gate 7 truth-pipeline observability has no stated current colour | `PLAN_2026-07-13` §C3 and its parked list | `docs/architecture/LORI-RUNTIME-ARCHITECTURE.md` documents the design and a 2026-07-30 Phase 2, but no live control document states Gate 7's status. PLAN called it "the biggest parent-session blocker" |

**Travel Doc binding-eval corpus** — `PLAN_2026-07-13` §D1. Report-only, no truth writes.
The trip lane supplies free labels: when the narrator is scoped to a trip/day/stop/photo,
the correct binding target is already known, so per captured turn it can store expected
binding (UI scope) against predicted binding (extractor) with pass/fail/reason.
**Recorded as a distinct obligation.** `MASTER_WORK_ORDER_CHECKLIST.md` §B item 4
(extraction improvement, four-persona harness) may absorb it, but **only through an
explicit later scoping decision** — it is not the same work, and folding it in silently
would lose the trip-scope label source that makes it cheap.

### 9.2 Deferred or separately authorized — scheduled in checklist §F

`MASTER_WORK_ORDER_CHECKLIST.md` §F owns scheduling and authorization for these; this file
owns the record that they are unresolved. **Both entries are intended — neither replaces
the other, and §F rows are not to be removed on account of this section.**

| Item | Source | Owner |
|---|---|---|
| Shared-token authentication | Review §1 C3, §11.1 (recorded as deliberately not done — origin allowlist and loopback bind closed the browser and LAN classes; a token adds defense in depth and touches ~30 UI files) | checklist §F |
| Hard-delete / archive atomicity, and the six orphaned-session FK violations | Review §2 S12, §12.4 | checklist §F |
| Comprehensive test runner, plus the conftest-level isolation the runner would encode | Review §5.1 | checklist §F |
| ESLint / lint / build / typecheck for the UI JavaScript, and cache-busting | Review §5.3 | checklist §F |
| One unified boot entrypoint | Review §5.5 | checklist §F |
| `ws_chat`, extraction-router and giant-module decomposition | Review §4, §8 step 5 | checklist §F |

### 9.3 Parked safety-reactivation preconditions

Runtime safety is **PARKED** by the decision of 2026-08-04 and reactivation takes Chris's
explicit decision. **Parking removes current reachability; it does not settle these.** Each
must be reconsidered before any reactivation — they are preconditions, not scheduled work.

| Item | Source | Why it is not closed |
|---|---|---|
| End-to-end runtime safety routing proof | `PLAN_2026-07-13` §C1b | **Partially covered.** `tests/test_safety_e2e_routing.py` mirrors the WebSocket hook in a subprocess and duplicates `_LLM_CAT_MAP` and the routing order. C1b required extracting the real safety block into a callable function and testing *that function*; the extraction never happened. Before reactivation, replace or supplement the mirrored composition test with a callable or live-route proof |
| Sensitive-segment flags stored plaintext in `localStorage` | Review §3 U11 | Cleaned on narrator delete, unencrypted per browser profile. Parking makes it unreachable today; it does not decide the storage question |
| `_SAFETY_LLM_PARSE_FAILURES` grows unbounded per `conv_id` | Review §2 S13 | The trip caches took a 500-entry cap for exactly this reason. **Unverified** — six references found, no cap confirmed. Re-audit belongs with reactivation, not with hygiene |

### 9.4 Unverified August-review findings — bounded re-audit before closure

**From the 2026-08-12 review, not reproduced on 2026-08-28.** Cited line numbers have moved,
the measurement was of the operator's machine rather than the repository, or the grep shape
could not confirm the specific site. **None of these may be closed, and none may be asserted
as a current defect, without a bounded re-audit.** Do not investigate them during hygiene.

| Item | Source |
|---|---|
| Blocking DB work and whole-transcript rewrite on the event loop inside the async WS handler | Review §2 S5 |
| Photo people/events PATCH is delete-all-then-re-add across separate connections, with no rollback | Review §2 S7 |
| `_json_dumps` trusts any string as pre-serialized JSON; the read side masks corruption as `{}` | Review §2 S14 |
| Stale-narrator race in the WO-10 panels — `pid` captured once, no re-check, no `AbortController` | Review §3 U6 |
| WebSocket reconnect has no backoff; `catch{}` on `onmessage` silently drops frames | Review §3 U8 |
| Uncleared module-level `setInterval`s (the review's 22-versus-14 count did not reproduce) | Review §3 U10 |
| Per-narrator `localStorage` keys cleaned by two duplicated hand-written removal lists | Review §3 U12 |
| E2E plumbing broken — `playwright.config.ts` points at a nonexistent script; npm scripts reference missing specs | Review §5.2 |
| Roughly 45% of Python tests are source-shape scans; the pre-doctrine backlog remains | Review §5.4 |
| `.runtime/logs/api.log` retention not enforced; narrator prose accumulating | Review §6 |
| `package.json` rot — `main`, license, duplicated Playwright dependency | Review §6 |
| **No backup strategy for `C:\hornelore_data`** — the 93MB memory archive reported as having no backup at all | Review §10 hygiene |
| Retention date owed for the pre-wipe narrator backup | Review §10 privacy, LOW |
| `import_staging/` holds Picker originals with no expiry | Review §10 hygiene, LOW |
| `.env.bak*` deletion and Google refresh-token rotation | Review §1 C2, §12.4 — operator-machine action, not a repository change |

### 9.5 Banked historical options — not scheduled, and not promises

Recorded so an old parked option is not later mistaken for a current commitment, and not
lost either. **None of these is scheduled. None may be promoted without Chris's decision.**

* **SearXNG / Brave public-lookup Phase 3** — `PLAN_2026-07-13`, "Explicitly parked".
* **Vision drafts Phase 4** — same.
* **New Travel Doc features** — same, under the July freeze ("the lane is code-complete; it
  is not proven"). The Trip and Palette work accepted later does not reopen this.
* **Direct master-eval movement work** — same. PLAN's own ground rule 3 records that the
  trip lane will not move the master eval and that we would not claim it does.

### 9.6 Deliberately not carried forward

Listed so their absence is not mistaken for an oversight, in the manner of §7.

**Resolved with current evidence:** the `_looks_spanish` two-tier fix, thematic-chain and
anchor-echo follow-ups, and the sensory-invention guard (`HANDOFF_2026-07-01`) · the
`SafetyResult` import-contract test and the `memory_exercise` doctrine conflict
(`PLAN_2026-07-13` §A2, §C5) · S1, S2, S8, U1, U2, U3, U5, U7 and the `docs/reports/`
doctrine conflict (Review §11, §12.2) · the `hard_delete_person` archive residue and the
orphan photo directories (Review §10), closed by the 2026-08-20 erasure work, whose fixed
targets name `memory/archive/people` and `memory/archive/photos` directly.

**Withdrawn on evidence — recorded so it is not re-raised:** Review §2 S11 recommended
`PRAGMA user_version` migrations on the premise that migration correctness rested on every
DDL statement staying idempotent forever. **The premise is wrong.** Hornelore tracks applied
migrations by filename: `server/code/db/migrations_runner.py` creates `schema_migrations`,
reads the applied filenames, applies each unapplied file in its own transaction, and inserts
the filename only after that transaction succeeds — so a failed migration records no row and
is retried on the next run. The absence of `PRAGMA user_version` is a design difference, not
a demonstrated defect, and it is **not** carried forward as one. S11's separate remark about
`init_db()` re-running per call is a performance observation, not a correctness claim, and
is likewise not carried forward.

**Superseded:** `WO-TRIP-TAB-DB-01`, never written, its substance landed in the trip lane
(`HANDOFF_2026-07-01`) · README and checklist reconciliation, done by hygiene Step 2, Gate 7
excepted and carried at §9.1 (`PLAN_2026-07-13` §C3).

**Historical-only:** the B0–B6 live-test procedure and its pre-flight
(`PLAN_2026-07-13` Track B, §A3) · **and §C1, "fix whatever B exposes"** — a conditional
instruction with no surviving specific B-test failure, superseded by the independently
accepted Trip and Palette testing. It is recorded as historical, **not** as an unknown
defect · session close-out mechanics: push, restart, smoke test, venv re-verification
(Review §12.2) · root clutter and control-document size, owned by this work order's own
Steps 3–5 (Review §6) · the published-PII history purge, owned by
`WO-PRIVACY-CANON-EXTRACTION-01` (Review §1 C1).
