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
| 0 | **`WO-LOREVOX-PORTABLE-NARRATOR-01`** — Portable Narrator | 🔵 **CURRENT — PHASE 6 PASSED ON BOTH ORIGINS; THE TWO-ORIGIN COMPARISON IS THE CURRENT ACTION.** Desktop 2026-09-11 (§36.1–36.3) and laptop 2026-09-12 (§36.5): Christopher, Kent and Janice each restored into their own clean root and re-exported `EQUIVALENT` with no narrator interaction, on both machines. The laptop found the **ownership-closure** defect the desktop data could not reach (20 `trip_turn_links` → 9 residue `sessions` / 100 turns; new `DirectOrExclusiveInbound` owner type, derived never written, export/erasure parity, closure resolved before deletion; 109 rows brought under the rule; residue suite 18/18, five-suite bank 90/90). **Six packages exist on two machines and the comparison needs both sets in one place — a transfer nobody has run.** Its output is the input to the Multi-Origin Merge/Remap WO (row 0a), which is designed after it, proven on synthetic two-origin data, and rehearsed into a new root before Phase 7. Phase 5a accepted live 2026-09-11 (§35.3). *(This cell said "laptop origin next" until 2026-09-12 — it had already passed.)* Narrator Data Center on the Operator tab (`HORNELORE_OPERATOR_PORTABLE_NARRATOR=1`): router `operator_narrator_package.py`, migration `0056` export-job ledger, two-verdict import (integrity / readiness), server stepper, restore only while READY, no verb deletes narrator data; API suite `tests/test_operator_narrator_package_api.py` under `.venv`. **Phase 5b (rich per-domain inspection) is post-Phase-7 and blocks nothing.** Phases 2–4 LANDED 2026-09-10/11 (WO §32 · §33 + §33.1 · §34) — one service `narrator_package.py` (export / validate / dry-run / restore / recover / compare), CLI, migrations `0054` + `0055`, `bagit==1.8.1`; last full combined acceptance under `.venv` **66/66** (restore 18, round-trip 9, export 24, parity 15); post-review focused additions restore 19/19 and round-trip 10/10, not rerun combined. Synthetic Ada with the full travel domain exports, restores into an empty root with ids verbatim, survives simulated process death at both crash windows, and round-trips semantically equivalent. **Known V1 boundary:** installation-local integer ids (`turns.id`) — same-origin packages coexist, multi-origin may collide and V1 refuses; Merge/Remap is a separate WO owed before a one-root family cutover. |
| 0a | **Multi-Origin Merge/Remap** — not yet a WO | ⏸️ **OWED before the Phase 7 one-root cutover.** First step is an inventory of every reference to `turns.id`; then integer remap vs globally unique turn identity. Not absorbed into V1. | Phase 0 landed (`20260910T015024Z`); Phase 1 landed 2026-09-10 (ownership declaration `narrator_data_inventory.py`, three erasure repairs, gap 4/4 + parity 15/15 under `.venv`; WO §31). **Two-machine data audit CLOSED 2026-09-10** — eleven labelled reports and `scripts/phase0_report_comparator.py`, all under `.runtime/`; family ids identical on both machines, each narrator's lanes split across them, neither machine is "the copy"; Phase 6 exports from both. **Phase 2 is governed by WO §30**: any narrator, the declaration as the only ownership authority, the complete travel domain generically whenever present, ids preserved, referential integrity refused-never-dangled, no deletion, no merge; proven on synthetic Ada with a seeded travel domain before any real narrator. Decided 2026-09-09: portability lands before more is built on Hornelore. [Work order](docs/wo/WO-LOREVOX-PORTABLE-NARRATOR-01.md) |
| 0b | **`WO-LORI-NARRATOR-FOCUS-MODE-01`** — interview focus mode for the narrator room | 🟡 **IMPLEMENTED 2026-09-12; STRUCTURAL SUITE 36/36 under `.venv`; LIVE ACCEPTANCE PARTIAL — NOT ACCEPTED.** Proven live on disposable `ZZ FOCUS MODE TEST`: cases 1, 3, 4, 5, 6, 9, 10, 11. **Owed before acceptance:** case 2's final live retest (the parked FocusCanvas controls were keyboard-reachable — repaired in focus-mode scope, `display:none` on `#fcCanvas`/`#fcScrim` plus a refusal while that overlay is open because `#fcTextarea` may hold unsent narrator text; the global leak is NOT repaired and stays a separate defect), case 7's real spoken/TTS turn, and case 8's exact 697px and 650px geometry (`resize_window` is a no-op in this harness — resize Chrome by hand or use Playwright in WSL). Ledger and evidence in the spec's status block. *(Formerly "specced, not started".)* Original spec docs-only at `3a62b38`. Drafted and revised 2026-09-12 on the laptop against the shipped page, for implementation in a desktop session. A presentation-only mode of the existing narrator room: large print, one conversation, nothing else on screen; entered by the operator before handing over, left by a deliberate gesture the narrator cannot produce by accident. **No server code, no prompt change, no extractor change, no second turn path** — it removes operator surface from narrator view rather than adding any. **This is the "UI work", and it is NOT Phase 5b** (the Rich Data Center, post-Phase-7). Independent of the portability lane; it waits on Chris's go, not on Phase 7. [Spec](docs/wo/WO-LORI-NARRATOR-FOCUS-MODE-01_Spec.md) |
| 1 | **`WO-LORI-ARCHIVE-TO-MEMOIR-02`** — EXECUTION REVISION 2026-09-07 | ⏸️ **PAUSED FOR PORTABILITY 2026-09-09 — Block D (Phase 6 conversational quality) has its verdict RECORDED and resumes after row 0**: Lean scored by Chris 3/4/4/2; Arm B rejected (stub collapse); single-factor screen kept the *intent* of prompts 1 and 3 only; next is a compact Lori prompt, Lean-sized — see `docs/handoffs/HANDOFF_2026-09-09_PHASE6_C-BLOCK-AND-LEAN-QUALITY.md`. *(This cell read 🔵 CURRENT until 2026-09-10, a day after HANDOFF.md recorded the pause — the two-lists-of-one-truth drift this file warns about.)* The text below is as it stood. **The measurement detour is CLOSED as the blocking action.** `WO-LORI-LISTEN-AND-RETAIN-01` §9 delivered its evidence and the Guard Lab was built from it; neither is a prerequisite for product work any longer. Active sequence: **Block A Operator control integration → Block B Phase 5C meaning disposition → Block C response-trace closer → Block D Phase 6 conversational quality → Block E Phase 7 review/memoir workflow → close Guard Lab acceptance debt → Phase 8**. **Guard Lab live acceptance is PARTIAL and BANKED — 6 verifier clauses passed, 0 failed, 3 unverified, plus the stale-tab 409 unexercised, so FOUR live checks remain open.** They are required evidence before final acceptance and **block nothing below**. Detail: `HANDOFF.md`, and `docs/wo/WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01_Spec.md` §5a. **Blocks A, B and C are DONE — Phase 5C landed as Block B on 2026-09-07 and is CLOSED, not active. THE CURRENT WORK IS BLOCK D, PHASE 6 CONVERSATIONAL QUALITY — and it is UNDERWAY, not pending:** Runs 1–4 and the A/B/C cohort are captured, and interventions `ee7063c` and `49c219c` have landed. Owed: the human-scored conversational verdict (Chris scores it; an agent must not), and the malformed-anchor extractor repair. **The sequence is A–F — there is no Block G, and the "D/G" shorthand is retired.** *(This cell read "Phase 5C is now ACTIVE, not queued" until 2026-09-08, while `HANDOFF.md` read "QUEUED, not active" — both were stale, in opposite directions.)* [Work order](docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md) |
| 1a | *(superseded)* **Lori measurement block** (`WO-LORI-LISTEN-AND-RETAIN-01` §9) | ✅ **EVIDENCE DELIVERED — no longer CURRENT.** Kept because its accepted evidence is still cited. **INSTRUMENT, THEN MEASURE.** Prompt-budget / generation / VRAM instrumentation with the stack DOWN, then the Walt+John diagnostic on ONE warmed stack, then joint evidence review. Observation only; `max_new_tokens=256` stays, because whether that cap binds is one of the things being measured. `WO-LORI-ARCHIVE-TO-MEMOIR-02` Phases 0–4 and 5A/5B CLOSED; **its Phase 5C is QUEUED behind this evidence**, since what 5C should do about `STATE_DECEASED` and the kinship qualifiers is partly what the measurement answers. **PHASE 4 ACCEPTED 2026-09-05**: the story-capture decision is durable on the source narrator turn, **including declined turns that create no candidate** — the case the phase existed for. Implementation `24c7130` (clean tree); live probe `20260905-151658` on `.venv-gpu`, **11 passed / 0 failed / 0 unverified**; offline `.venv` **241 tests, zero skips**; **8/8 mutations caught**. Nominated turn bound candidate `8a159445`; declined turn carried a full diagnostic with no story row. **Ten of eleven clauses proven live — `measurement_failed` is offline-only** and the record says so. **Nothing about capture changed**: no threshold, classifier, source unit, review rule, migration or new table, and the 114/14 banks were deliberately not rerun (observability, not extraction). One branch records nothing on purpose — a trigger with no `person_id` fits none of the three closed outcomes; opening the vocabulary is Chris's call. **PHASE 5A + 5B ACCEPTED 2026-09-06** on the 85/85 mutation gate (0 MISSED, 0 BROKEN, 180.0 min). The ONE central contract was built rather than `daddy` added to four regexes: `server/code/api/services/relationship_interpreter.py` holds the whole vocabulary and the kinship guard's per-role patterns are DERIVED from it. `ExtractedItem` now carries `source_phrase` and `normalized_from`; `family.priorPartners.relation` exists; **the narrator's wording decides the lane**, so the deliberately crossed passage is corrected, `ex-wife` stores relation `wife` with the phrase in provenance, `partner` binds without manufacturing a marriage, `late wife` keeps the word `late` under a third state `deceased`, an ex-wife's occupation goes to review naming `would_need`, person association is re-derived after a lane change, and the Family Tree draws `partnership` / `former_marriage` / `marriage`. **74 tests in the two lane suites, 156 with the Phase 4/5A suites, zero skips; mutation gate `L1`–`L9` 9/9, seven `was_real`** — sandbox `python3`, `.venv` is Chris's run. **NOT claimed:** no live turn; `STATE_DECEASED` recorded but unconsumed; the `adult`/`older`/`younger` qualifiers read but carried nowhere; banks not rerun. **PHASE 5C — since DONE 2026-09-07 as Block B; the words "QUEUED, NOT CURRENT" below describe where it stood when this superseded row was written: meaning with no schema destination** — one disposition path instead of one per case, and a deliberate decision or recorded refusal for the qualifiers and for `STATE_DECEASED`. `siblings.birthOrder` is not the answer for `older`. **do not disable `HORNELORE_CLAIMS_VALIDATORS` as a product fix** — two of the three arity-crash paths found in 5B were that flag's own branches. **Phase 3's last open box is CLOSED 2026-09-05** — *Jim binds as Pat's husband*: `Jim` had no test while `Otis` had five and `Domingo` two; `TheJimCase` now drives the shipped `run_field_extraction` with Pat's own wording and the guard was already correct. State: `HANDOFF.md` §9. [Work order](docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md) |
| 2 | **`WO-LORI-PROFILE-SEED-REACHABILITY-01`** — Phase 3 | ⏸️ **OWED, NOT CURRENT — IN IMPLEMENTATION WITH ACCEPTANCE OPEN.** Phases 0–1 accepted; **Phase 2 ACCEPTED 2026-08-29, steps 1–7 complete**. Phase 3 implementation landed through `2b7e634`; its six acceptance conditions remain open. Phases 4–5 are partially run and not accepted. Hashes: `HANDOFF.md` §1 and the spec's reconciled status block. [Spec](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md) · [Transport map](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md) |
| ~~3~~ | ✅ **DONE 2026-09-08 — `WO-REPOSITORY-HYGIENE-01`, indexed reorganization** | **COMPLETE and CLOSED at `e0fde84`. This row is a ledger entry, not active work — do not reopen repository hygiene.** Phase A accepted 2026-08-28 (Steps 0, 1, 2, 2b, first Step 3 cohort); the remainder Chris deferred that day was resumed and discharged 2026-09-08 across `93a8f85`, `9e1db2a` and `e0fde84`. **Completion is not "the repository is clean":** ten scripts stay explicitly `unknown`, and the obligations the pass found were **registered in [`docs/BACKLOG.md`](docs/BACKLOG.md), not fixed.** Hashes: `HANDOFF.md` §1. *(This row read "PHASE A ACCEPTED, REMAINDER PAUSED — INCOMPLETE".)* [Spec](docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md) |

**Profile Seed no longer waits for hygiene, and hygiene is now finished anyway.** The
earlier rule — that Profile Seed was released only by Steps 3–5 **and** the final
verification together — was **superseded** on 2026-08-28 by Chris's product-priority
decision, which deferred the hygiene remainder. That remainder was then resumed and
discharged on 2026-09-08, and `WO-REPOSITORY-HYGIENE-01` is **COMPLETE at `e0fde84`.**
*(Until 2026-09-08 this paragraph ended "it does not claim the hygiene work order finished,
and this list must not describe it as complete." That was correct while the remainder was
merely deferred; the work order has since been closed on its own evidence, so the sentence
is corrected rather than deleted.)* Profile Seed's own scope, inheritance and prohibitions
are in `HANDOFF.md` §3, and they are unchanged — **completing hygiene did not advance
Profile Seed, whose Phase 3 acceptance remains OPEN.**

## B. Next, in order

| # | Work | Precondition |
|---:|---|---|
| 4 | **Finish Lean Lori** — one substantial implementation block | After Profile Seed reachability. Six items, in order: (1) complete prompt-section metadata — owner, activation condition, trim policy, source, priority tier, real token count, redacted hash; (2) finish directive gating so each family appears only when its state/feature/task is active — **the ten-topic Profile Seed onboarding is PRESERVED for new Lorevox narrators regardless of narrator type**; (3) decide history-versus-optional-section priority **from measurements** — Phase 4 exhausts history first and its telemetry emits the per-section costs that decision needs; (4) finish passive diagnostics — one operator-readable record across all three transports, no narrator prose; (5) a SMALL live acceptance replacing the abandoned L2 campaign — ordinary conversation, one state-heavy turn, one trip turn, one approved-story turn, one safe oversized refusal; (6) reconcile the Lean Lori WO's stale status table and remove its abandoned rollback language and unsatisfiable Gate F assumptions. **Substantial work is ALREADY LANDED (11 commits) — do not rebuild it. Gate B stays OPEN.** |
| 5 | **Extraction improvement** with the four-persona harness | After Lean Lori. Run the core and challenge packs against the REAL extractor; identify **binding** failures rather than reporting pass counts; retire the old evaluator **only after scoring parity**, preserving it under `scripts/archive/` |
| ~~6~~ | ✅ **DONE 2026-09-08 — Remove the retired Kawa / Memory River implementation** | **COMPLETE and ACCEPTED.** `WO-KAWA-REMOVAL-01` landed as `3481d1a` (compatibility — retired-value normalization first, so no removal step could strand a narrator) + `0a16c88` (removal — **16 files changed, 1,389 deletions / 393 insertions**; of those insertions, 206 are the new structural test `tests/test_kawa_product_path_removed.py` and **187 are the edits to existing files**). Router unmounted, `/api/kawa/*` gone, `routers/kawa.py` · `kawa_store.py` · `kawa_projection.py` · `ui/js/lori-kawa.js` · `data/prompts/kawa_prompts.json` deleted, client helpers / state / preload / render / **memoir-context** / button / popover / CSS / mode selectors removed, the interview question-replacement path removed. Negative structural test at `tests/test_kawa_product_path_removed.py`, mutation-verified in both directions. **Kept, and asserted present by that test:** historical research, archived specs, narrator-erasure support, the `kawa_segment` media type, migration 0003, the retired-language eval, the geographic `River` regex. **`DATA_DIR/kawa/` narrator data was NOT deleted.** *(This row read "ADJUDICATE removal…", then "Removal DECIDED". Now executed.)* |

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
| **Profile Seed Phase 2 — steps 1–7, the server-side walk** | 2026-08-29 | `HANDOFF.md` §1a evidence table |

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
