# MASTER WORK ORDER CHECKLIST

**Active as of:** 2026-08-14  
**Authority:** code and live evidence outrank this coordination list. Start with
`HANDOFF.md`.

## A. Critical path

| Order | Work | State | Exit gate |
|---:|---|---|---|
| 1 | `WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01` | **COMPLETE** | 83/0/0 verify; 45/0/0 restore; live restart persistence. |
| 2 | Multi-day closeout record | **DONE 2026-08-14** | Recorded in the WO and in `CLAUDE.md`. The final F12/API-log inspection is **not a separate stack cycle** — the post-acceptance sweep is done and clean, and the one item still owed (live confirmation of the deferred-thumbnail fix) folds into P4. |
| 3 | Artifact inventory and classification **(classification only — cleanup is a separate, unauthorized action)** | **CLASSIFICATION DONE 2026-08-14; CLEANUP DEFERRED, requires Chris.** The 22 harness narrators were deliberately not deleted, and none of them owns a trip. | Every artifact classified; genuine memories preserved; test noise hidden reversibly; no destructive deletion without Chris. *(This row named `WO-LIVE-TRIP-CLEANUP-01`, a work order that was never written. Rather than leave the queue pointing at a document that does not exist, the requirement now lives in `WO-TRIP-PHOTO-PALETTE-01_Spec.md` §9 P0, which was already doing the inventory.)* |
| 4 | `WO-TRIP-PHOTO-PALETTE-01` | **COMPLETE 2026-08-14** | All three gates met: offline 584 tests + 4 harnesses (113/32/16/56); P4 live acceptance final PASS; P5 restart persistence 14/14 and restoration 22/22. Evidence: `docs/reports/WO-TRIP-PHOTO-PALETTE-01_P4_LIVE_ACCEPTANCE.md` and `..._P5_PERSISTENCE.md` — **local-only, not in the repository** (`docs/reports/` is gitignored; live narrator data). |
| 5 | Legacy-column retirement (Palette Phase 6) | **DEFERRED by supervisor recommendation 2026-08-14 — NOT the next build** | Leave deferred until there is a concrete reason. The scalar is frozen, unwritten, ignored for authoritative decisions, correctly derived on read and covered by tests; dropping it buys no product benefit and costs a risky SQLite rebuild. |
| 6 | **Lean Lori — Phase 0 map + L1** | **COMPLETE 2026-08-14** — [map](docs/wo/WO-LEAN-LORI-PHASE-0-MAP-2026-08-14.md) · [L2 runbook](docs/wo/WO-LEAN-LORI-L2-RUNBOOK-2026-08-14.md) · [Profile Seed brief](docs/wo/WO-LEAN-LORI-PROFILE-SEED-DECISION-BRIEF-2026-08-14.md) | **Substantial work is ALREADY LANDED (11 commits) — do not rebuild it.** L1 delivered: errata banners, executable rollback, corrected gate commands, decision brief, L2 runbook. Safety-preservation evidence is now reproducible from a clean clone. |
| 7 | **Lean Lori — L2 live acceptance** | **L2 PARTIAL — closed for now by product-priority decision, 2026-08-16.** **DO NOT RESUME.** | Evidence: `docs/reports/WO-LEAN-LORI-L2-PARTIAL-2026-08-16.md` (local-only, gitignored). Case C, remaining Case A branches, five styles, trip/photo fixtures, refusal matrix, Case E rows 2/4 and the final restart with Case F are **DEFERRED by decision — not failures.** **Gate B stays OPEN.** L2 established: identity completion promotes `pass1→pass2a` and the spine is browser-local; deterministic turns archive 1:1; memory echo sees the server profile seed; LLR-19 did not reproduce; export ZIP valid; identity completion *raised* the prompt 6,008→6,709 tok; **no family narrator content changed (proven byte-identical)**. Three integration defects surfaced and feed the next lane: text-based export verification is invalid for identical deterministic replies; `sessions` rows carry no narrator ownership; browser projection sync can rewrite a server row merely on narrator load. |
| 8 | **`WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01`** | **NEXT — fresh session** | Phase 1 canonical narrator authority: server-authoritative projection hydration, durable session ownership, server-owned Life Map projection. Absorbs Lean Lori Gate D. Travel Document connects to this authority **after** it works. |
| 8 | **Profile Seed ownership** | **DECISION REQUESTED** | Blocks Phase 8's remainder. Recommendation: Option A, live narrators only. See the brief. |

## B. Photo Palette delivery blocks

| Block | Deliverable | Stack cycle |
|---|---|---|
| P0 | Reconcile existing Palette surfaces/APIs and cleanup dependencies. **DONE 2026-08-14** — [`WO-TRIP-PHOTO-PALETTE-01_P0_MAP.md`](docs/wo/WO-TRIP-PHOTO-PALETTE-01_P0_MAP.md). Verdict: no new endpoint needed; P1 is three small changes; artifact contamination does not reach the Palette. **One decision open — see map §6.** | Stack down; no restart. |
| P1 | Query/filter contract and any missing repository/API support. **DONE 2026-08-14** — soft-deleted exclusion, total read order, batch visibility endpoint; 33 tests. | Stack stays down. |
| P2 | Palette UI, selection, batch actions, bounded thumbnails and truthful errors. **DONE 2026-08-14** — plus nine post-review corrections. | Stack stays down. |
| P3 | One consolidated regression run and review of P1+P2 together. **DONE** — 584 tests + 4 harnesses. | Stack stays down. |
| P4 | Live browser acceptance and F12/log review. **DONE 2026-08-14 — final PASS.** Carried the owed deferred-thumbnail confirmation. One reproduced defect found and fixed mid-phase (`b991353`, `88429cc`): the Hidden pool was not refreshed after Add/Remove/Move/caption-save. Eight genuine photographs uploaded. | Started once. |
| P5 | Persistence verification and closeout. **DONE 2026-08-14 — 14/14 read-only, then restoration 22/22.** | Restarted once. |

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
