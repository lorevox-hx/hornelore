# HORNELORE HANDOFF

**Updated:** 2026-08-17  
**Repository:** `lorevox-hx/hornelore`  
**Branch:** `main`

## 1. Read this first

This file is the current operational starting point. When documents disagree, use:

```text
current code
> current tests and live evidence
> accepted closeout records and ADRs
> this handoff
> MASTER_WORK_ORDER_CHECKLIST.md
> old work-order status lines
> archived history
```

Do not restart work from an old status line. Read the current implementation, its tests,
and its latest live evidence first.

## 2. Current project state

**Phase 1 is ACCEPTED (2026-08-17).** Conflict-aware field-level projection authority;
explicit session ownership reconciled across `sessions` and `interview_sessions`; ONE server
chronology projection, extended from `/api/chronology-accordion` rather than added beside it,
consumed by both Life Map renderers. Live acceptance ran on the designated non-family acceptance narrator.
**Step 9 — rapid A→B narrator switching — is accepted with its synthetic-B limitation:** the
mechanism is proven, but not against a second narrator carrying a full live history, because
no such narrator exists outside the family set. Recorded in §8.1 of the spec, not only in a
local report.

**Phase 2 is ACCEPTED (2026-08-17) — 8/8 live acceptance steps passed.** Travel Document
connects to the chronology authority; narrator selection is reconciled across shell-launched
surfaces behind one shared contract; the legacy session-owner backfill is completed by
migration 0045. Contract in §12 and the acceptance record in §12.7 of
[`docs/wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md`](docs/wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md).

**Ownership results, aggregate:** 721 sessions — 8 recovered from unambiguous legacy payload,
1 newly explicit, 712 older rows with unrecorded provenance and deliberately not retro-stamped.
**Zero malformed payload rows currently exist; the `list_sessions` guard is preventive.**

**Two things this acceptance did NOT prove, and does not claim to.** The harness's
`completed-turn` route — chat → extraction ledger → result → owned-session — is **genuinely
unexercised**; the acceptance proved session *ownership* only. It needs
`HORNELORE_OPERATOR_HARNESS=1` and a deliberate restart, and is deferred until then rather than
counted as duplicated evidence. And `product-read` did not run because its reference personas
are soft-deleted; **soft deletion is respected and they are not restored.**

**Phase 3 (Reviewed story authority) is ACCEPTED WITH ONE ITEM OWED — 8 of 9 live steps,
2026-08-18.** A captured story now has ONE server-owned review state and ONE projection every
surface reads: approved stories reach the Life Map, the chronology and Lori's prompt;
provisional ones are counted and never quoted; discarded ones are ABSENT from every projection
rather than dimmed. Migration 0046 records `placement_source` and `review_version`, and every
review is an atomic compare-and-write.

**THE OWED ITEM, stated plainly:** step 6 has two halves and only one is proven live. The
negative half — *a provisional story is never asserted* — passed twice. The positive half —
*Lori speaks an approved story* — did NOT, and chasing it is what found the defect below. It
needs a restart to confirm.

**The live run found three real defects that 530 offline tests did not**, which is the argument
for keeping the live step a gate rather than a formality. All three are fixed:

1. **Every review action button was `disabled="undefined"`.** The panel's `el()` helper wrote
   attributes whose value was `undefined`, and an attribute's PRESENCE disables a control. No
   source scan can see this; it needs a browser.
2. **The panel wedged after every successful write.** One generation counter was answering two
   different questions, and `applyReview`'s own success path bumped it — so the cleanup arm
   decided it was stale and never cleared the busy latch. Now three counters: list reads,
   detail reads, and narrator switches. A write asks only the third.
3. **The reviewed-story prompt section carried no `drop_order`** — `required=False` with an
   implicit 0, ranked below a per-turn hint. Now 25: above the sections that rebuild themselves
   next turn, below the identity sections that must never be traded for episodic material.
   **CORRECTED the same day:** this was first written up as the CAUSE of the owed check. It is
   not. `render()` emits every section, `sections()`/`drop_order`/`required` have no production
   consumer at all, and the token budget trims history turns while leaving the system message
   untouched by contract — so **nothing was being dropped and the story reached the model.**
   The fix is kept as a LATENT defect, correct in itself and dangerous the moment enforcement
   lands. The retired claim read: *"The reviewed-story prompt section was the FIRST thing
   dropped … so the one thing Phase 3 exists to deliver ranked below a per-turn hint."*

**What the owed check actually is, now that the wrong cause has been withdrawn:** Lori received
the approved story and still said she did not recall it. That is a prompt-authority and
model-behaviour problem, not a budgeting one, and it does **not** need a restart to reproduce.
It folds into the Phase 4 block, which is chartered to make prompt assembly authoritative — and
the fact that the section classification is **declared but unenforced** is that block's single
most useful starting fact.

*(This section read "Phase 1 — canonical narrator authority … Phases 2–4 are sequenced and not
started" until 2026-08-17, and "Phase 3 (Witness/story connection) is NEXT and not yet started"
until 2026-08-18. A handoff that still names an accepted phase as active is an instruction to
redo it, which is the failure this file's own ordering rule exists to prevent.)*

**Known, deliberate and not this lane's work:** seven assertions in the older
`tests/test_lori_witness_mode` module conflict with later deliberate behaviour — four still
demand three-anchor cascade output despite the newer two-anchor cap, and three expect the
retired broad correction behaviour. That is reconciliation work for the Witness lane, not a
reason to divert the authority phase.

| Lane | State | Next decision |
|---|---|---|
| Google Photos Picker | **BANKED** | Reopen only for a demonstrated defect. |
| Travel Document core/export | **CLOSED on live evidence** | Preserve the editable timeline → DOCX projection rule. |
| Multi-day trip-photo placement | **COMPLETE; Gate 3 accepted 2026-08-14** | Close documentation; do not begin legacy-column removal. |
| Test-artifact inventory/classification | **DONE in Palette P0** | Classification complete; genuine memories preserved. |
| Test-artifact **cleanup** | **DEFERRED — requires Chris's authorization** | The 22 harness narrators were deliberately **not** deleted. No destructive cleanup without an explicit decision. |
| Photo Palette | **COMPLETE; P4 and P5 accepted 2026-08-14** | Close the work order; do not reopen for polish without a demonstrated defect. |
| Legacy photo-day scalar retirement (Phase 6) | **DEFERRED by supervisor recommendation, 2026-08-14 — NOT the next build** | Leave deferred until there is a concrete reason to remove the column. The scalar is frozen, no longer written, ignored for authoritative decisions, correctly derived on read, and covered by tests and live evidence; dropping it buys no product benefit and costs a risky SQLite table rebuild. |
| Lean Lori | **L1 COMPLETE 2026-08-14. L2 ran PARTIAL on 2026-08-16 and is CLOSED by product-priority decision — DO NOT RESUME IT.** *(This row said `NEXT: L2, awaiting Chris's authorization` until 2026-08-17. L2 had already run and been closed; a handoff that still names it as next is an instruction to redo a decision, which is the failure this file's own ordering rule exists to prevent.)* | **Substantial work is ALREADY LANDED — eleven commits, Gate A, 1A–1E, 5, 6, 7, Phase 8 first gate. Do not rebuild it.** Evidence for the partial run: `docs/reports/WO-LEAN-LORI-L2-PARTIAL-2026-08-16.md` (local-only, gitignored — live narrator data). **Gate B stays OPEN and Phase 10 stays open**; the deferred cases are deferred by decision, not failures. Profile Seed ownership is **CORRECTED 2026-08-20 — the ten-topic onboarding is PRESERVED for new Lorevox narrators REGARDLESS OF NARRATOR TYPE.** *(This read `DECIDED — Option A, live narrators only` until 2026-08-20. That wording was false and it was the harmful kind of false: it read as licence to gate the onboarding on narrator type, which would have removed the ten-topic workflow from exactly the narrators it exists for. Ordinary new-narrator reachability is still OWED and is the next substantive lane.)* **The three integration defects L2 surfaced were CLOSED by `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01`, which is COMPLETE — they are no longer the active lane.** *(This read `The three integration defects L2 surfaced are the active lane` until 2026-08-20, after that work order had been accepted; a handoff naming closed work as active is an instruction to redo it.)* **Profile Seed reachability is the active/next lane**; Lean Lori follows it, with its content unchanged at §4. The model / 8,192-token lock still binds. |
| **Narrator authority Phase 1** | **ACCEPTED 2026-08-17** | Step 9 accepted with its synthetic-B limitation. Closes no L2 gate. |
| **Narrator authority Phase 2** | **ACCEPTED 2026-08-17 — 8/8 live steps** | Travel Doc ↔ chronology, shared narrator-context contract, migration 0045. Record: spec §12.7. |
| **Harness `completed-turn`** | **PRODUCT ROUTE NOW EXERCISED LIVE (2026-08-18); the harness SCENARIO is still deferred** | Phase 3's live run drove two real Lori turns end to end: chat → `turn_extraction_ledger` rows → owned sessions, confirmed by the delete report removing 2 sessions and 2 interview_sessions scoped to that narrator. The harness's own scenario still needs `HORNELORE_OPERATOR_HARNESS=1` and a restart; what is no longer true is that the ROUTE is unexercised. |
| **Phase 3 — Reviewed story authority** | **ACCEPTED 2026-08-18; its owed item is CLOSED** | *(Read "ACCEPTED WITH ONE ITEM OWED — 8/9 live" until Phase 4's acceptance.)* Lori answered a direct memory question from the approved story: *"You mentioned your grandmother Elena from Corpus Christi."* Spec §14.2. |
| **Phase 4 — section-aware prompt authority** | **ACCEPTED 2026-08-18** | *(Read "NEXT — not started" until 2026-08-18.)* The section classification finally has a production reader; all three transports budget through it. Spec §14. |
| **`WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01`** | **COMPLETE — Phases 1–4 all accepted** | No Story Integration phases remain, and the three L2 integration defects are closed with it. **Next lane is Profile Seed reachability; Lean Lori follows it — see §4.** *(This row read `Next lane is Lean Lori` until 2026-08-20.)* |
| **`turn_extraction_ledger` cleanup** | **FIXED in Phase 4** | *(Read "REPORTED, NOT FIXED" until 2026-08-18.)* The table joined `_EXTENDED_PERSON_SCOPED_TABLES`, so it is both inventoried before deletion and removed by it — 6 rows removed live. **Two orphans remain and are NOT new: `turnrow:1663` and `turnrow:1665`, from the Phase 3 narrator hard-deleted before the fix existed.** They carry keys and timings and no narrator text. Sweeping those two is a one-line data decision for Chris. |
| **`WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01`** | **ACCEPTED AND COMPLETE 2026-08-20** | Story-to-memoir synthetic chain **11/11**; deletion-integrity acceptance **10/10**. Verified against the **filesystem and direct SQL**, never a response body. Lori asks naturally → the answer is preserved → the candidate binds to BOTH committed turn rows → extraction reaches operator review → approval and era placement are atomic → chronology and Life Map agree → preview, TXT and DOCX each contain it **exactly once** with one provenance digest. Spec: [`docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md`](docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md). **Gate B stays OPEN, L2 stays PARTIAL, the directive-family registry stays INERT, and Kawa appears here only as REACHABLE FROZEN LEGACY UI AWAITING ADJUDICATION — non-authoritative; do not extend or build on it — plus one storage directory in the erasure inventory.** **NEXT SUBSTANTIVE LANE: Profile Seed reachability — not another story/memoir testing pass.** |
| **Deletion integrity** | **CLOSED 2026-08-20 — a privacy defect this lane's own cleanup exposed** | `hard_delete_person` removed all active narrator/person-scoped content rows, answered 200, and left eight files on disk, five of them verbatim narrator speech. Erasure is now planned before the database authority is destroyed and persisted (0049) bound to the canonical absolute root (0050); refuses every symlink below the root, including one pointing at ANOTHER narrator inside it; covers eleven stores; deletes media rather than detaching it; purges the translation cache; **reports backups and exports rather than rewriting them**; fails closed before touching a row; and is retryable through the product API with a truthful audit trail. |
| **Narrators after the acceptance** | **UNTOUCHED** | **the four family narrators and the designated non-family narrator are all untouched**. The synthetic narrators' people rows, active content and filesystem residue are removed; their audit and erasure-job metadata is intentionally retained and carries no narrator speech. Also: `integrity_check ok`; the **six pre-existing `harness-test-gate7p2` FK violations in `interview_sessions` are unchanged and NOT closed by this lane**. |
| **Profile Seed reachability** | 🔵 **ACTIVE — PHASE 0 COMPLETE pending acceptance; PHASE 1 next** | [`WO-LORI-PROFILE-SEED-REACHABILITY-01`](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md), authored by Chris 2026-08-26. **The ten-topic workflow is preserved and ordinarily unreachable, and the cause is a race the intake itself starts:** intake requires name, DOB and birthplace; those three anchors are exactly what chronology needs; chronology promotes `pass1 → pass2a`; and the composer emits the ten-topic block only for an identity-complete narrator STILL in `pass1`. So the ordinary path supplies what closes its own gate before the narrator's first normal turn, while a testing-only narrator without the anchors goes down identity mode instead — which mutually excludes the block. Present in source, covered as a predicate, and proven by nothing. The spec also records completion-data gaps: siblings, explicit "none" answers, education field naming, childhood home versus birthplace, and actual retired/working status. **Phase 0 is COMPLETE pending acceptance** — 46 tests, three modules, one expected failure, no product or schema change. It pinned eight distinct promotion sites (including the direct ready-narrator initialisation that seats a narrator in `pass2a` AND identity-complete at once), demonstrated the skip as an `expectedFailure` proven to announce its own repair, and built the ten-topic fixtures on the work order's `unanswered | known | addressed | declined`. **Four findings change Phase 1's inputs:** the pass is browser-owned with no server writer anywhere under `server/code/api`; `_build_profile_seed()` returns five keys of which only two are walk topics and both are derived wrongly; the military `served` Boolean is ignored in BOTH directions, not just when false; a real `bio_facts.childhood_home_address` is overridden by birthplace; and there is no canonical marital-status field for an explicit "never married". **Phase 1 — server authority — is next.** |
| Kawa / Memory River | **REACHABLE FROZEN LEGACY UI** | Phase 2 did not extend it. Awaiting a deliberate removal decision. |
| Runtime safety | **PARKED, server-authoritative** | Never reactivate through environment values. |
| Model / 8,192-token window | **LOCKED** | Any proposed model change is stop-and-report. |
| Privacy canon extraction/history purge | **PARKED work order** | Not on the current product critical path. |

## 3. Multi-day placement closeout

`WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01` changed the authoritative model from one
nullable day on `trip_photo_links` to a set of placement rows in
`trip_photo_day_placements`.

Binding behavior now proven live:

- one permanent photo and one trip membership may have zero, one, or many day placements;
- one day may hold many photos;
- **Add to this day**, **Remove from this day**, and **Move** are distinct;
- removing one occurrence preserves every other placement, membership, original,
  thumbnail, caption, approval and context;
- the compatibility scalar is `null` for zero or multiple placements and must never be
  used to decide whether a photo is unplaced;
- explicit placements and taken-date suggestions are counted separately;
- shared captions project consistently across placements and do not grant Lori approval;
- bounded thumbnail windows keep every item reachable without unbounded DOM growth.

Live evidence, Bismarck Trip, 2026-08-14:

- Stage B persistence: **83 passed, 0 failed, 0 not exercised, 1 attested**;
- restoration: **45 passed, 0 failed, 0 not exercised**;
- photo links remained 4 → 4; placement total restored 3 → 3;
- conversation link and turn rows survived byte-identically;
- original placement sets were restored with no duplicate links;
- rail counts matched timeline rows on all six days.

Phase 6 is not implied by this acceptance. Dropping `trip_photo_links.trip_day_id`
requires a separately reviewed SQLite rebuild and rollback plan.

## 4. Immediate execution order

**Next action: Profile Seed reachability — Phase 0 of [`WO-LORI-PROFILE-SEED-REACHABILITY-01`](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md).** NOT another story/memoir testing pass.

*(This section read "finish Lean Lori, in one substantial implementation block" until
2026-08-20. `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` ran and closed in between, and its
closeout named the next lane explicitly. The Lean Lori block below is still the correct
content and is still owed; what changed is what comes first.)*

**The ten-topic Profile Seed onboarding is preserved for new Lorevox narrators REGARDLESS OF
NARRATOR TYPE.** What is owed is reachability: an ordinary new narrator must actually reach
it. That is the lane, and it now has a spec — [`WO-LORI-PROFILE-SEED-REACHABILITY-01`](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md), authored by Chris against
`6952ad0` on 2026-08-26 and READY FOR IMPLEMENTATION. It establishes server-owned,
restart-safe onboarding progress; all ten topics preserved regardless of narrator type; NO
automatic enrollment of historical narrators; chronology readiness separated from onboarding
completion; known / negative / declined / unanswered topic states; one question per turn;
versioned writes with narrator-switch isolation; and explicit offline and live acceptance
gates. **Start at Phase 0, which changes no behavior.** `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01` is **COMPLETE** — Phases 1–4
all accepted — and `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` is **ACCEPTED AND COMPLETE**.
Do not resume the L2 matrix.

*(This section read "Next action: open Phase 3 — Witness/story connection" until 2026-08-18,
while Phase 3 and Phase 4 were both built and accepted beneath it. A control document naming
an accepted phase as next is an instruction to redo it, which is the failure this file's own
ordering rule exists to prevent.)*

**The Lean Lori block, in the order it should be built:**

1. **Complete prompt-section metadata.** Sections carry `required` and `drop_order` today.
   They still need owner, activation condition, trim policy, source, priority tier, real token
   count and redacted hash. Phase 4 built the reader and the telemetry that make the last two
   observable; the fields themselves are not there yet.
2. **Finish directive gating.** Only the Era Explainer is gated by actual narrator state. Every
   other directive family must appear only when its state, feature or task is active. Profile
   Seed is **CORRECTED 2026-08-20 — the ten-topic onboarding is PRESERVED for
   new Lorevox narrators REGARDLESS OF NARRATOR TYPE.** *(This read `DECIDED —
   Option A, live narrators only` until 2026-08-20; that wording read as licence
   to gate the onboarding on narrator type.)* Ordinary new-narrator reachability
   is still OWED.
3. **Decide history versus optional-section priority FROM MEASUREMENTS.** Phase 4 deliberately
   exhausts history before shedding any section, which preserved every working turn and is the
   reason that change was safe to land. Whether low-value optional material should instead go
   before recent narrator/Lori conversation is a product decision, and the per-section token
   costs the new telemetry emits are the measurement it needs. **Not another test matrix.**
4. **Finish passive diagnostics.** One operator-readable record of which sections were
   activated, kept or removed across REST chat, REST streaming and the WebSocket — without
   storing narrator prose. The per-transport wiring exists; the unified record does not.
5. **Close the remaining Lean Lori live evidence.** A SMALL acceptance replacing the abandoned
   broad L2 campaign: ordinary conversation, one state-heavy turn, one trip turn, one
   approved-story turn, one safe oversized-prompt refusal.
6. **Reconcile the Lean Lori work order itself.** Its status table is stale now that
   optional-section budgeting has landed, and it still carries abandoned runtime-profile
   rollback language and Gate F assumptions that the architecture cannot satisfy. Replace them
   with what actually exists.

**After Lean Lori, in order:** extraction improvement against the new four-persona core and
challenge packs — finding BINDING failures rather than reporting pass counts, and retiring the
old evaluator only after scoring parity, preserved under `scripts/archive/`; then removal of
the frozen Kawa / Memory River UI once Life Map is confirmed to cover the active navigation
paths.

**Owed separately, and not part of any of the above:** the harness `completed-turn` SCENARIO
(the product route is now exercised live — see the lane table), deferred until a deliberate
operator-harness restart; and the harness usability fix so absent or soft-deleted reference
personas report `N/A` while the writable synthetic personas continue.

The Palette / multi-day sequence below is **historical and complete**. It is kept because
item 6 is still an open decision, not because any of it is the next lane.

Items 1–5 are **complete as of 2026-08-14**; item 6 remains an open decision.

1. Record the multi-day closeout. **Done.**
2. Inventory contaminated acceptance/test artifacts. **Done in Palette P0** — no genuine
   family material deleted, and the contamination proved not to reach the Palette at all
   (22 of 36 narrators are harness residue and none owns a trip).
3. Execute the Photo Palette work order. **Done — P0 through P5.**
4. Run one consolidated Palette regression gate. **Done** — 584 tests plus four harnesses
   at 113 / 32 / 16 / 56, verified in `.venv`.
5. Start once for live acceptance, restart once for persistence. **Done** — P4 final PASS
   after one correction; P5 persistence 14/14 and restoration 22/22.
6. **NEXT: decide separately whether to authorize legacy-column retirement.** Palette
   acceptance does **not** imply it.

### 4.1 Photo Palette closeout

**Reports are LOCAL-ONLY and deliberately not in the repository** — `docs/reports/` is
gitignored because those files carry live narrator data. Not links, because a link would be
broken for anyone cloning:

```text
docs/reports/WO-TRIP-PHOTO-PALETTE-01_P4_LIVE_ACCEPTANCE.md   (local working copy only)
docs/reports/WO-TRIP-PHOTO-PALETTE-01_P5_PERSISTENCE.md       (local working copy only)
```

The summary below is the tracked evidence and is intended to stand on its own.

Proven live and across a restart: placement identity preserved byte-for-byte; the derived
compatibility scalar correct at zero, one and many placements while the stored column is
never written; membership rendered once however many placements it has; filter counts equal
to their cards on every chip; batch Add, eligibility-checked Remove, source-named Move, and
reversible Hide/Restore; caption and Lori approval kept apart on the wire; dirty guards;
thumbnail-only grid with deferred loading on the modal's real scrollport; no duplicate
writes, no originals in the grid, no legacy-scalar writes.

**One defect was found live and fixed inside P4** (`b991353` code, `88429cc` tests): Add,
Remove, Move and a caption save refreshed the visible photo pool but not the Palette's own
hidden pool, so a hidden card kept showing a day it no longer had. `reloadPalettePhotoPools`
now owns that rule in one place, wired into five sites; eight mutations, eight killed.

Eight genuine Bismarck photographs were uploaded during acceptance and are **preserved** —
memberships only, no day placements, no approvals granted. Every temporary acceptance
caption, placement and hidden flag was restored afterwards and re-verified against the
original baseline.

**Two things carried forward, neither blocking:**

- **Region-only placement has no operator route.** `PhotoLinkPatch` carries no
  `trip_region_id` field and no clear-stop flag, so nothing in the Travel Document can
  create a region-only photo link. The Palette renders the badge; the state is
  unreachable. A product decision, not a defect.
- **Scale evidence is the harness's.** The trip holds 12 memberships, so 49/50/51/200/500/
  1,000, `Load more` and the mounted-window distinction remain proven by
  `run_photo_palette_behaviour.js` and `run_photo_window_arithmetic.js`. No rows were
  manufactured to change that.

## 5. Photo Palette product boundary

The Palette is a mode inside the existing Travel Document workspace, not a second product
or nested modal. It reuses the photo inventory, thumbnails, placement APIs, bounded window
helpers, current trip and selected-day state already landed.

The authoritative unplaced rule is:

```text
zero trip_photo_day_placements
```

Never use `trip_day_id IS NULL`; that is also the compatibility representation of a photo
placed on multiple days.

The Palette MVP includes filters, selection, batch Add, per-placement Remove/Move,
caption/approval separation, hidden/review states, and honest partial-failure reporting.
It does not include destructive deletion, face recognition, AI photo interpretation,
duplicate originals, or a schema rewrite.

Canonical plan:

- `docs/wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md`
- `docs/wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md`
- `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` ruling 1.16

## 6. Efficient work and verification policy

- Work in coherent product blocks, not one-line review cycles.
- Focused tests while coding; one consolidated regression run at the end of the block.
- Mutation/non-vacuity tests only for load-bearing behavior.
- Do not restart for documentation, tests, or harness-only changes.
- Keep the stack down through an implementation block.
- Start once for live acceptance and restart once for final persistence proof.
- Stop early only for schema risk, destructive live-data action, security boundary,
  model/configuration change, or a real design decision.
- **Claude prepares copy-paste `git add` + `git commit` blocks; Chris runs them and pushes;
  Chris and ChatGPT review the pushed block.** Agents do not run git here. The reason is in
  `CLAUDE.md`: a sandbox git command that hits the agent timeout on the `/mnt/c` 9p mount
  leaves `.git/index.lock` behind and silently blocks GitHub Desktop and Chris's own WSL
  git, presenting as "add succeeded, commit says nothing to commit, Desktop still shows N
  changed files." Read-only git (`log`, `status`, `diff`, `rev-parse`) is fine.

## 7. Known separate issues—not Palette scope

- six pre-existing `interview_sessions → people` foreign-key violations from old harness
  narrators;
- hard-delete filesystem residue root cause;
- legacy-column retirement;
- privacy canon extraction and public-history purge;
- broad `ws_chat`/extract-router decomposition;
- giant control-document archival;
- model, prompt-window, STT, TTS and runtime-safety changes.

Do not fold these into Palette implementation.

## 8. Required document set

| Document | Purpose |
|---|---|
| `HANDOFF.md` | Truthful current state and next action. |
| `MASTER_WORK_ORDER_CHECKLIST.md` | Small active/next/deferred coordination list. |
| `docs/wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md` | Executable researched Palette plan. |
| `docs/wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md` | Landed placement authority and acceptance history. |
| `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Binding Travel Document rulings. |

Historical handoffs and long status narratives remain in git history or `docs/archive/`;
they must not be appended back into this operational brief.
