# Backlog — unresolved obligations, with their evidence

**Derived at:** `d0e52946aa77096841612df176f4cbb70d4edacd`, 2026-08-28
**Status:** registry only. Nothing here is scheduled, and nothing here has been repaired.

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
**accepted at `d0e5294`**. Phase 2 Step 6 is blocked only by the repository-hygiene
checkpoint, which is a deliberate sequencing decision and not an obligation.

---

## 2. Root specifications with unresolved or unclear obligations

Thirty specs sit at the repository root. These sixteen must be represented here before
their full specs move. **The audit named fifteen; the sixteenth is new** — see §2.1.

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

**Appendix A of the audit lists 29 root specs. There are 30.** The audit is not edited; the
[verification addendum](reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28_VERIFICATION_ADDENDUM.md)
§3 records the amendment.

---

## 3. `docs/wo/` — parked, banked, and spec-only work

Fifty-one files, mixing active implementation specs with completed, superseded, parked and
future-only documents. **Twenty-nine are not named by the four governing documents — a
triage signal, not proof of deadness.** The active Profile Seed transport map is itself
unreferenced by filename and is the most current design document in the tree.

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

## 4. Control-document corrections

Each is real, each is small, and **none belongs in an index-only or a file-move commit.**
They land in the control-authority commit.

| Where | Defect | Evidence |
|---|---|---|
| `CLAUDE.md` | Says the pre-pivot archive holds **114** work orders; Git derives **113** | `git ls-tree -r --name-only d0e5294 -- docs/archive/workorders-pre-pivot \| wc -l` |
| `CLAUDE.md` | Environment bullet asserts `.venv` has **no fastapi** (measured 2026-08-20) and that route tests skip there silently. On 2026-08-28 `.venv` ran the strict suite **22/22 with zero skips** | Chris's run, `.venv/bin/python -m unittest tests.test_profile_seed_expected_version_strict` |
| `CLAUDE.md` | "Where files live" table names the repo root as *the* location for WO specs, contradicting the `docs/wo/` convention stated at the top of the same file | Already flagged in-file, 2026-07-28 |
| `README.md` | Duplicates lane status that `HANDOFF.md` owns | Audit §12 |
| `docs/CHANGELOG-AGENT.md` | 614,130 bytes, 1,407 very long lines. `CLAUDE.md` points agents at it | Audit §7 |

The second row deserves emphasis: **the bullet that is wrong is the one warning agents
that `OK` with skips is not a pass.**

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
| No compile gate over `scripts/` and `tests/` | The reason Test 23 was silent for three and a half months |

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
