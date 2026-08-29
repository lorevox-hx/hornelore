# HORNELORE HANDOFF

**Repository:** `lorevox-hx/hornelore` · **Branch:** `main`
**Reduced 2026-08-28** by `WO-REPOSITORY-HYGIENE-01` Step 2. Superseded narrative and
retirement notes were removed, not lost — they are in Git history and in the work orders
this file points to. **No new obligation was introduced** — the reduction removed
superseded narrative, not owed work. *(This said "nothing was added", which was literally
false: the reduction rewrote and restructured, and a later correction added the hard-delete
rule back. The claim that matters is the one about obligations.)*

---

> # ▶ CURRENT ACTION — PROFILE SEED PHASE 2 STEP 7. HYGIENE PHASE A IS ACCEPTED AND PAUSED.
>
> | | |
> |---|---|
> | **Current action** | Profile Seed Phase 2 **Step 7. NOT STARTED.** |
> | **Step 6** | ✅ **ACCEPTED 2026-08-29 on live evidence.** Implemented `12221e0`, corrected `58dfc40`, instrument committed `525a43f`. Two independent runs of `scripts/step6_ws_probe.py` through the **production WebSocket and the real model — 16/16 each.** Run 2 was made from a committed instrument on a clean tree |
> | **Hygiene Phase A** | **ACCEPTED** through the first Step 3 cohort — Steps 0, 1, 2, 2b and the four root dated artifacts |
> | **Hygiene remainder** | **DEFERRED by Chris's product-priority decision:** the remaining Step 3 cohorts, Steps 4–5, and the final verification checkpoint. They remain indexed, not cancelled |
> | **Is the hygiene work order complete?** | **NO — incomplete and PAUSED.** Phase A acceptance is not completion of `WO-REPOSITORY-HYGIENE-01` |
> | **May Step 7 begin?** | **YES.** The rule that Profile Seed waited for the whole hygiene checkpoint is **superseded** by that decision |
>
> **The supersession is deliberate and is recorded so it is not mistaken for drift.** The
> earlier rule — that no individual hygiene step's acceptance releases Step 6, only Steps 3–5
> and the final verification together — was correct when hygiene was the priority. Chris
> changed the priority. **What that decision does not do is claim the hygiene work is
> finished**, and no document may say it is.
>
> **Still frozen, and not by hygiene:** the boundaries in §3 are the lane's own, and they do
> not relax. Runtime safety, the model and its window, the directive registry and Kawa are
> governed by `CLAUDE.md`, which no priority decision touches.

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

Where everything else lives: [`docs/INDEX.md`](docs/INDEX.md) ·
[`docs/BACKLOG.md`](docs/BACKLOG.md) · [`scripts/INDEX.md`](scripts/INDEX.md) ·
[`docs/archive/INDEX.md`](docs/archive/INDEX.md).

## 2. Current state

| Lane | State |
|---|---|
| **Repository hygiene** | ⏸️ **PHASE A ACCEPTED, REMAINDER PAUSED — the work order is INCOMPLETE.** Steps 0, 1 `5f6b01b`, 2 `db0c5e7`, 2b `ff1ff4f` and the first Step 3 cohort `5086490` are accepted. **Deferred by product-priority decision:** the remaining Step 3 cohorts, Steps 4–5, and the final verification checkpoint. Still indexed, still owed, not scheduled |
| **Profile Seed reachability** | 🔵 **ACTIVE — Step 7 is the current action.** Phase 0 `661aa95` · Phase 1 `1288baa` · Phase 2 steps 1–5 accepted (step 4 `b269184`, step 5 `9127adb`) · pre-Step-6 corrections `d0e5294` · **Step 6 ACCEPTED on live evidence** · **Step 7 NOT STARTED** · Phases 3–5 not started. **Phase 3 is the next narrator-facing block:** reconcile the eight browser promotion sites with server authority and remove the remaining browser-controlled race |
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

## 3. Step 6 — what it inherits and what it must not touch

**REST reads authority and DOES NOT ADVANCE.** Measured live: a narrator answers a topic
and the durable row still reads `active=childhood_home · remaining=10 · version=2`. Within
a session the history hides it; across a session boundary Lori asks for something she was
already told. **Step 6 is the fix**, and
`test_an_answer_recorded_as_REST_SHAPED_TURNS_is_never_applied` is written to be REPLACED
when it lands, not deleted.

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
| `docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md` | The **paused** repository lane — Phase A accepted, remainder deferred and incomplete. **Not the current action;** Profile Seed is |
| `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md` + `..._PHASE2_TRANSPORT_MAP.md` | The current product lane |
| `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Binding Travel Document rulings |

Historical handoffs and long status narratives live in Git history and `docs/archive/`.
**They must not be appended back into this operational brief.**
