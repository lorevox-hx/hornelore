# MASTER WORK ORDER CHECKLIST

**Authority:** code and live evidence outrank this list. Start with
[`HANDOFF.md`](HANDOFF.md).

**Reduced 2026-08-28** by `WO-REPOSITORY-HYGIENE-01` Step 2 to active / next / deferred /
separately-authorized work. Completed rows became the ledger in §D; their evidence lives in
the work orders and in Git history. **No new obligation was introduced.**

**Derive the head, do not read it from here:** `git rev-parse origin/main`.

---

## A. Active

**Acceptance hashes are NOT repeated here.** `HANDOFF.md` §1 is their authoritative home,
and each work order carries its own ledger. **One authoritative home does not mean zero
references** — this list points at state, it does not restate it, because a hash written in
two places is a hash that will disagree in one of them.

| # | Work | State |
|---:|---|---|
| 1 | **`WO-LORI-PROFILE-SEED-REACHABILITY-01`** — Phase 2 Step 7 | 🔵 **CURRENT.** Phases 0–1 accepted; Phase 2 steps 1–5 accepted; pre-Step-6 corrections accepted; **Step 6 ACCEPTED 2026-08-29 on live evidence — 16/16 through the production WebSocket. Step 7 NOT STARTED**, Phases 3–5 not started. Hashes: `HANDOFF.md` §1 and the spec's status block. [Spec](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md) · [Transport map](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md) |
| 2 | **`WO-REPOSITORY-HYGIENE-01`** — indexed reorganization | ⏸️ **PHASE A ACCEPTED, REMAINDER PAUSED — INCOMPLETE.** Steps 0, 1, 2, 2b and the first Step 3 cohort accepted. **Deferred by Chris's product-priority decision:** the remaining Step 3 cohorts, Steps 4–5, and the final verification checkpoint. Hashes: `HANDOFF.md` §1. [Spec](docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md) |

**Profile Seed no longer waits for hygiene.** The earlier rule — that it was released only
by Steps 3–5 **and** the final verification together — is **superseded** by Chris's
product-priority decision. That decision defers the hygiene remainder; it does **not** claim
the hygiene work order finished, and this list must not describe it as complete. The lane's
scope, inheritance and prohibitions are in `HANDOFF.md` §3, and they are unchanged.

## B. Next, in order

| # | Work | Precondition |
|---:|---|---|
| 3 | **Finish Lean Lori** — one substantial implementation block | After Profile Seed reachability. Six items, in order: (1) complete prompt-section metadata — owner, activation condition, trim policy, source, priority tier, real token count, redacted hash; (2) finish directive gating so each family appears only when its state/feature/task is active — **the ten-topic Profile Seed onboarding is PRESERVED for new Lorevox narrators regardless of narrator type**; (3) decide history-versus-optional-section priority **from measurements** — Phase 4 exhausts history first and its telemetry emits the per-section costs that decision needs; (4) finish passive diagnostics — one operator-readable record across all three transports, no narrator prose; (5) a SMALL live acceptance replacing the abandoned L2 campaign — ordinary conversation, one state-heavy turn, one trip turn, one approved-story turn, one safe oversized refusal; (6) reconcile the Lean Lori WO's stale status table and remove its abandoned rollback language and unsatisfiable Gate F assumptions. **Substantial work is ALREADY LANDED (11 commits) — do not rebuild it. Gate B stays OPEN.** |
| 4 | **Extraction improvement** with the four-persona harness | After Lean Lori. Run the core and challenge packs against the REAL extractor; identify **binding** failures rather than reporting pass counts; retire the old evaluator **only after scoring parity**, preserving it under `scripts/archive/` |
| 5 | **ADJUDICATE removal of the frozen Kawa / Memory River UI** | After extraction work. **Removal is NOT decided and is NOT scheduled.** The button, popover, `chronology_river` mode and `js/lori-kawa.js` are still reachable in `ui/hornelore1.0.html`. Removal requires **Chris's explicit decision AND confirmed Life Map coverage of the active navigation paths** — both, not either. Until then the surface is frozen: **do not extend it, do not build anything new on it, and do not describe it as retired in code.** *(This row read "Remove the frozen Kawa / Memory River UI", which schedules as settled a decision nobody has made. `CLAUDE.md` is explicit that retiring the metaphor in doctrine is not the same as removing the surface from the tree.)* |

## C. Owed separately — small, unscheduled

* **Harness `completed-turn` scenario** — needs `HORNELORE_OPERATOR_HARNESS=1` and a
  deliberate restart. The product ROUTE was exercised live in Phase 3; the harness's own
  scenario was not.
* **Harness reference-persona handling** — absent or soft-deleted reference personas should
  report `N/A` while writable synthetic personas continue. A harness commit.
  **Soft deletion is respected; those narrators are not restored.**
* **Two `turn_extraction_ledger` orphans** — `turnrow:1663` / `1665`, from a narrator
  hard-deleted before the Phase 4 fix existed. Keys and timings only, no narrator text.
  A one-line data decision.
* Everything registered in [`docs/BACKLOG.md`](docs/BACKLOG.md), including the 16 root
  specifications with unresolved obligations and the four tooling defects.

## D. Complete — ledger only

Do not reopen without a demonstrated regression. Evidence is in each work order; acceptance
detail is deliberately **not** repeated here.

| Work | Accepted | Ledger |
|---|---|---|
| `WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01` + closeout | 2026-08-14, Gate 3 | its spec |
| `WO-TRIP-PHOTO-PALETTE-01` — P0 through P5 | 2026-08-14 | its spec |
| Artifact inventory and **classification** (cleanup is separate and unauthorized) | 2026-08-14 | Palette spec §9 P0 |
| Lean Lori Phase 0 map + L1 | 2026-08-14 | the L1 map |
| `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01` — Phases 1–4 | 2026-08-17 / 08-18 | its spec §12.7, §13, §14 |
| `turn_extraction_ledger` cleanup | 2026-08-18, in Phase 4 | same spec |
| `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` | 2026-08-20 — 11/11 and 10/10 | its spec |
| Deletion / erasure integrity | 2026-08-20 | same spec |
| Profile Seed Phases 0–1, Phase 2 steps 1–5, pre-Step-6 corrections | through 2026-08-28 | `HANDOFF.md` §1 + spec status block |
| Repository hygiene Steps 1, 2 and 2b | 2026-08-28 | `HANDOFF.md` §1 |
| **Profile Seed Phase 2 Step 6** — the committed-turn walk over the production WebSocket | 2026-08-29, **live** 16/16 | `HANDOFF.md` §1 + §5 · spec status block |

**Profile Seed ownership is settled**, and the settlement is the durable part: the
ten-topic onboarding is **preserved for new Lorevox narrators regardless of narrator
type**. Only reachability was ever owed.

## E. Banked — preserve, do not reopen for polish

Google Photos Picker live workflow · Travel Document editable timeline → DOCX projection ·
multi-day photo placement and placement-aware counts · S2 photo hash-clash protection ·
S8 chronology failure visibility · U7 legacy Documenter socket-race guards · loopback bind,
origin allowlist, DB close-on-exception and applied XSS fixes · the four-mode WO-02
acceptance harness and its separate ATTEST accounting.

## F. Deferred — separately authorized only

Drop `trip_photo_links.trip_day_id` and delete pre-0043 compatibility branches · privacy
canon extraction, prose fictionalization and Git history purge · shared-token
authentication · multi-operator Google authorization · hard-delete/archive atomicity repair
and the six orphaned-session FK violations · one unified boot entrypoint, comprehensive
test runner and ESLint/toolchain work · `ws_chat`, extraction-router and giant-module
decomposition · Lean Lori continuation beyond §B, prompt architecture, safety reactivation,
model changes · test-artifact **cleanup** — the 22 harness narrators were deliberately not
deleted.

**Legacy photo-day scalar retirement (Palette Phase 6)** — dropping
`trip_photo_links.trip_day_id` — is **deferred and requires Chris's explicit authorization
to reopen. It is not approved, not scheduled, and not a decision currently on the table.**
Palette and multi-day acceptance do not imply it. Detail and the reasoning:
[`docs/BACKLOG.md`](docs/BACKLOG.md) §3b.

**Deferred is not forgotten. Deferred means intentionally not active.**

## G. Work discipline

1. One coherent product slice may contain multiple closely coupled fixes.
2. Do not stop for review after trivial test, import or comment corrections.
3. Keep unrelated fixes distinguishable in the commit message or a small adjacent commit.
4. Focused tests during development; consolidated regression once per product block.
5. Mutation tests are required for critical guards, transactions, destructive boundaries
   and error truthfulness — not for every token or comment.
6. No stack restart for docs, unit tests or harness-only changes.
7. One live acceptance start and one final persistence restart per product gate.
8. **Report skip counts.** `OK (skipped=N)` is not a pass, and a result must name the
   interpreter it came from.
9. **Never combine product corrections, indexing, file moves and deletion in one commit.**
10. Claude prepares copy-paste `git add` + `git commit` blocks; Chris runs them and pushes
    from GitHub Desktop. Agents do not run `git add`/`commit`/`push` here — see the
    `.git/index.lock` hazard in `CLAUDE.md` and `HANDOFF.md` §6. Read-only git is fine.

## H. Governing documents

[`HANDOFF.md`](HANDOFF.md) · [`CLAUDE.md`](CLAUDE.md) ·
[`docs/INDEX.md`](docs/INDEX.md) · [`docs/BACKLOG.md`](docs/BACKLOG.md) ·
[`docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md`](docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md) ·
[`docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md`](docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md)

Old dated blocks belong in Git history or `docs/archive/`, not in this active checklist.
