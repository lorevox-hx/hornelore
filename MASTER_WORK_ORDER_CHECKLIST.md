# MASTER WORK ORDER CHECKLIST

**Active as of:** 2026-08-14  
**Authority:** code and live evidence outrank this coordination list. Start with
`HANDOFF.md`.

## A. Critical path

| Order | Work | State | Exit gate |
|---:|---|---|---|
| 1 | `WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01` | **COMPLETE** | 83/0/0 verify; 45/0/0 restore; live restart persistence. |
| 2 | Multi-day closeout record | **DONE 2026-08-14** | Recorded in the WO and in `CLAUDE.md`. The final F12/API-log inspection is **not a separate stack cycle** — the post-acceptance sweep is done and clean, and the one item still owed (live confirmation of the deferred-thumbnail fix) folds into P4. |
| 3 | Artifact inventory and classification | **FOLDED INTO PALETTE P0** | Every artifact classified; genuine memories preserved; test noise hidden reversibly; no destructive deletion without Chris. *(This row named `WO-LIVE-TRIP-CLEANUP-01`, a work order that was never written. Rather than leave the queue pointing at a document that does not exist, the requirement now lives in `WO-TRIP-PHOTO-PALETTE-01_Spec.md` §9 P0, which was already doing the inventory.)* |
| 4 | `WO-TRIP-PHOTO-PALETTE-01` | **ACTIVE — starts at P0** | Automated, live-browser and restart acceptance all pass. |
| 5 | Decide whether to authorize legacy-column retirement | **DECISION** | Separate migration/rollback proposal reviewed; not automatic. |

## B. Photo Palette delivery blocks

| Block | Deliverable | Stack cycle |
|---|---|---|
| P0 | Reconcile existing Palette surfaces/APIs and cleanup dependencies. **DONE 2026-08-14** — [`WO-TRIP-PHOTO-PALETTE-01_P0_MAP.md`](docs/wo/WO-TRIP-PHOTO-PALETTE-01_P0_MAP.md). Verdict: no new endpoint needed; P1 is three small changes; artifact contamination does not reach the Palette. **One decision open — see map §6.** | Stack down; no restart. |
| P1 | Query/filter contract and any missing repository/API support. | Stack stays down. |
| P2 | Palette UI, selection, batch actions, bounded thumbnails and truthful errors. | Stack stays down. |
| P3 | One consolidated regression run and review of P1+P2 together. | Stack stays down. |
| P4 | Live browser acceptance and F12/log review. **Also carries the owed live confirmation of the deferred-thumbnail fix** — it is not a cycle of its own. | Start once. |
| P5 | Persistence verification and closeout. | Restart once at end. |

## C. Banked / preserve

- Google Photos Picker live workflow.
- Travel Document editable timeline → DOCX projection.
- Multi-day photo placement and placement-aware counts.
- S2 photo hash-clash protection.
- S8 chronology failure visibility.
- U7 legacy Documenter socket-race guards.
- Loopback bind, origin allowlist, DB close-on-exception and applied XSS fixes.
- Four-mode WO-02 acceptance harness and separate ATTEST accounting.

Do not reopen banked work for polish without a demonstrated regression.

## D. Deferred, separately authorized

- Drop `trip_photo_links.trip_day_id` and delete pre-0043 compatibility branches.
- Privacy canon extraction, prose fictionalization and Git history purge.
- Shared-token authentication.
- Multi-operator Google authorization.
- Hard-delete/archive atomicity repair and the six orphaned-session FK violations.
- One unified boot entrypoint, comprehensive test runner and ESLint/toolchain work.
- `ws_chat`, extraction-router and giant-module structural decomposition.
- Lean Lori continuation, prompt architecture, safety reactivation or model changes.

## E. Work discipline

1. One coherent product slice may contain multiple closely coupled fixes.
2. Do not stop for review after trivial test/import/comment corrections.
3. Keep unrelated fixes distinguishable in the commit message or a small adjacent commit.
4. Focused tests during development; consolidated regression once per product block.
5. Mutation tests are required for critical guards, transactions, destructive boundaries and
   error truthfulness—not for every token or comment.
6. No stack restart for docs, unit tests or harness-only changes.
7. One live acceptance start and one final persistence restart per product gate.
8. Claude prepares copy-paste commit blocks, Chris runs them and pushes, Chris + ChatGPT
   review current pushed `main`. Agents do not run `git add`/`commit`/`push` here — see the
   `.git/index.lock` hazard in `CLAUDE.md` and `HANDOFF.md` §6. Read-only git is fine.

## F. Governing documents

- `HANDOFF.md`
- `docs/wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md`
- `docs/wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md`
- `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md`
- `docs/wo/HORNELORE_CORRECTED_EXECUTION_PLAN_2026-08-01.md` (historical sequence;
  Palette scalar wording is superseded by the new Palette WO)

Old dated blocks belong in git history or archives, not in this active checklist.
