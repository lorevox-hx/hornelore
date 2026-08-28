# Documentation index — what is authoritative, and what is history

**Derived at:** `d0e52946aa77096841612df176f4cbb70d4edacd`, 2026-08-28
**Status:** index only. **Nothing has been moved, renamed or deleted.**

---

## 1. Read these, in this order

| Question | Read | Authority |
|---|---|---|
| What is the current state? What is next? | [`../HANDOFF.md`](../HANDOFF.md) | **Current state. Wins over every other document** |
| What is the ordered queue? | [`../MASTER_WORK_ORDER_CHECKLIST.md`](../MASTER_WORK_ORDER_CHECKLIST.md) | Active / next / deferred |
| What are the standing rules and hazards? | [`../CLAUDE.md`](../CLAUDE.md) | Durable doctrine and prohibitions |
| What is still owed, and how do we know? | [`BACKLOG.md`](BACKLOG.md) | Unresolved obligations with evidence |
| What is the product, and how is it operated? | [`../README.md`](../README.md) | Product and operator documentation |

**The governing order, from `CLAUDE.md`:**

```text
current code
> current tests and live evidence
> accepted reports / ADRs / closeout records
> HANDOFF.md
> MASTER_WORK_ORDER_CHECKLIST.md
> old WO status lines
> archived design history
> docs/CHANGELOG-AGENT.md
```

*(This copy repeated `CLAUDE.md`'s order faithfully — including the missing `HANDOFF.md`.
Both corrected 2026-08-28. Copying a list is how a defect in it propagates; the copy is
kept because a reader here needs the order, and it is now checked against its source.)*

A status line in a document never outranks the code and the tests. This repository has
twice carried a stale current-work list that read as an instruction to rebuild finished
work, and that ordering is the defence.

**Derive the live head; never read it from a document:**

```bash
git rev-parse origin/main
git status --porcelain      # must be empty before any gate
```

---

## 2. Architecture and decisions — why the system behaves as it does

| Document | Subject |
|---|---|
| `architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md` | Who Lori is for. **Hornelore is the family R&D deployment of Lorevox**, and the Horne family is tenant zero, not a special case |
| `architecture/LORI-RUNTIME-ARCHITECTURE.md` | The nine-stage runtime pipeline — how Lori's behaviour is produced |
| `architecture/MEMORY-EXERCISE-DECISION.md` | Design history for `memory_exercise`. **The style is removed from the picker**; legacy values redirect to `warm_storytelling` |
| `architecture/COWORK-HANDOFF.md` | The operational brief that landed the pivot |
| `architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Travel Doc evidence and web-context rule |
| `decisions/2026-08-04-park-safety-feature.md` | **Runtime safety is PARKED**, server-authoritative, code and tests preserved. Never reactivate through an environment value |
| `specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` | Canonical extractor reference. Consult before any extractor-lane work |

---

## 3. Active work orders

Live implementation specs are in [`wo/`](wo/) — 51 files. It is **not** a clean cohort: it
mixes active specs with completed, superseded, parked and future-only documents. See
[`BACKLOG.md`](BACKLOG.md) §3 before assuming any of them is dead.

The current lane:

| Document | Role |
|---|---|
| `wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md` | The work order |
| `wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md` | **The most current design document in the repository.** Read §6, §6b and §16 before any Step 6 work |

*Both are now linked from a governing document. The transport map previously had **no
incoming filename reference** from any of the four control documents while being the live
design authority — which is why "unreferenced" is a triage signal and never proof of
deadness.*

---

## 4. Reviews and audits

| Document | What it is |
|---|---|
| [`reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28.md`](reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28.md) | The repository audit, **verbatim**, inspected at `ea3ab27`. No figure edited |
| [`reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28_VERIFICATION_ADDENDUM.md`](reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28_VERIFICATION_ADDENDUM.md) | Git-derived verification, re-derived at `d0e5294`. **Read this alongside the audit** — its §4 records that the audit's "owed" section is historical |

**The audit's §6 lists five pre-Step-6 corrections as owed. All five are accepted at
`d0e5294`.** Reading §6 as a live work list would rebuild finished work.

---

## 5. History — kept, and not to be read as instruction

| Path | Files | What it is |
|---|---:|---|
| [`archive/`](archive/) | 130 | Pre-pivot work orders and handoffs, plus one post-pivot handoff. See [`archive/INDEX.md`](archive/INDEX.md) |
| `CHANGELOG-AGENT.md` | 1 | **614,130 bytes.** Dated history, not a work queue. Consult for *why a subsystem behaves like this*, after the code and the ADRs |
| `wo-qa/` | 11 | April-era QA notes |
| `handoffs/`, `drafts/`, `mockups/` | 4 / 3 / 16 | Dated historical material |
| `reports/` | — | **Gitignored since `a87e865`.** Reports are written here and are local-only: they carry live narrator data and the repository is public. Do not `git add` them, and do not "fix" the ignore rule when one refuses to stage — the refusal is the feature |

---

## 6. Where things live

| Kind | Path |
|---|---|
| API log | `.runtime/logs/api.log` |
| Eval JSON / console reports | `docs/reports/master_loop01_*.json` / `.console.txt` |
| Eval case source | `data/qa/question_bank_extraction_cases.json` |
| Active WO specs | `docs/wo/<NAME>_Spec.md` |
| Legacy WO/BUG specs | **30 still at the repository root** — see [`BACKLOG.md`](BACKLOG.md) §2 |
| Pre-pivot specs | `docs/archive/workorders-pre-pivot/` — history only |
| Scripts | [`../scripts/INDEX.md`](../scripts/INDEX.md) |

---

## 7. What this index does not do

It does not move anything, and it does not decide anything. It records where the authority
currently is so that the cleanup can proceed one reviewable cohort at a time.

The hygiene sequence, its boundaries, and its prohibitions are in
[`wo/WO-REPOSITORY-HYGIENE-01_Spec.md`](wo/WO-REPOSITORY-HYGIENE-01_Spec.md).

**Phase 2 Step 6 does not begin until that checkpoint is complete and accepted.**
