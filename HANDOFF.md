# HORNELORE HANDOFF

**Repository:** `lorevox-hx/hornelore` · **Branch:** `main`
**Reduced 2026-08-28** by `WO-REPOSITORY-HYGIENE-01` Step 2. Superseded narrative and
retirement notes were removed, not lost — they are in Git history and in the work orders
this file points to. **No new obligation was introduced** — the reduction removed
superseded narrative, not owed work. *(This said "nothing was added", which was literally
false: the reduction rewrote and restructured, and a later correction added the hard-delete
rule back. The claim that matters is the one about obligations.)*

---

> # ▶ CURRENT ACTION — THE LORI MEASUREMENT BLOCK. ARCHIVE-TO-MEMOIR PHASES 0–4 AND 5A/5B ARE CLOSED; 5C IS QUEUED.
>
> | | |
> |---|---|
> | **Current action** | **Instrument Lori's prompt budget, generation and VRAM, then run the Walt+John diagnostic on ONE warmed stack, then review the evidence jointly.** `WO-LORI-LISTEN-AND-RETAIN-01` §9, the VRAM/prompt-budget extension. Observation only — no narrator-visible behaviour changes, and `max_new_tokens=256` stays because whether that cap binds is one of the things being measured. **Order: instrumentation (stack DOWN) → push → review → GPU recorder → stack → preflight proving tracing is ON and writing to THIS run's directory → Walt → no restart → John → stop → evidence.** |
> | **Why before 5C** | Two of Phase 5C's three open destinations — what consumes `STATE_DECEASED`, and where the `adult`/`older`/`younger` qualifiers belong — are questions about what the memoir needs. Walt+John is the first measurement that speaks to them. Deciding them first would design a destination before seeing the traffic |
> | **Phase 5C** | ⏸ **QUEUED, not active.** Scope unchanged in the work order: one disposition path for "understood, no destination", and a deliberate decision or recorded refusal for the qualifiers and `STATE_DECEASED`. **`siblings.birthOrder` is not the answer for `older`** — mapping it would manufacture a fact. **Do not disable `HORNELORE_CLAIMS_VALIDATORS` as a product fix** — it gates several safeguards while leaving the parse-time whitelist active |
> | **Mutation gate** | ✅ **85/85 caught, 0 MISSED, 0 BROKEN, 180.0 min** — 2026-09-06, `.venv/bin/python`, clean tree, journal absent, product tree restored. 35 of the 85 are designs a lane actually carried. **Baseline: 12 unique commands, all green — and `test_profile_seed_rest_read_authority` ran 48 with 6 SKIPPED**, which is stated because `OK` with skips is not a pass and eleven `S` mutations depend on that suite. **This is the accepted Phase 5B/tooling baseline, and the gate is now ACCEPTANCE-ONLY.** Three suites are 80% of the three hours (`docs/BACKLOG.md` §6c); day to day run the focused tests plus the family that protects the changed file, per the map in `scripts/run_mutation_gate.py`. **The rule is "follow a moved invariant", not "run nearby families"** — `C8` survived a full gate because a refactor moved `identity_complete` into a reader its tests did not watch |
> | **Phase 5A + 5B** | ✅ **ACCEPTED 2026-09-06** on the 85/85 gate. 5A bound bio-fact provenance to the committed-turn `_Claim`. 5B built `relationship_interpreter.py` — one vocabulary, derived rather than duplicated — added `family.priorPartners.relation`, and made **the narrator's wording decide the lane**: the deliberately crossed passage is corrected, `ex-wife` stores relation `wife` with the phrase in provenance, `partner` binds without manufacturing a marriage, `late wife` keeps the word `late` under a third state `deceased`, an ex-wife's occupation goes to review rather than to the current spouse, person association is re-derived after a lane change, and the Family Tree draws `partnership` / `former_marriage` / `marriage` instead of `marriage` for everything. **74 tests in the two lane suites (0 skips); 156 with the Phase 4/5A suites; mutation gate `L1`–`L9` 9/9 caught, 7 of them designs this lane actually carried.** Sandbox `python3` only — `.venv` is Chris's run |
> | **Phase 5B — the four boundary defects** | All four were invisible to helper-level tests: (1) `getattr(req, "conv_id")` — not a field on the request, so production wrote null provenance while `session_id` sat unused; (2) `ExtractedItem(...)` names its kwargs, so the recorded narrator phrase was dropped one call before the pass that needed it; (3) the lane was chosen by the CANONICALIZED value, and `wife` occurs twice in the mixed passage, Mary's first; (4) grouping runs BEFORE the lane pass, so moved items reached callers with no person association while a comment claimed they were regrouped |
> | **Phase 5B — what it does NOT claim** | **No live turn was run.** `STATE_DECEASED` is recorded, not consumed. The qualifiers are read, not carried. The 114/14 banks were **not** rerun |
> | **Phase 4** | ✅ **ACCEPTED 2026-09-05.** The story-capture decision is durable on the source narrator turn, **including declined turns that create no candidate**. Implementation `24c7130` (clean tree); live probe `20260905-151658` on `.venv-gpu` — **11 passed / 0 failed / 0 unverified**; offline `.venv` **241 tests, ZERO skips**; **8/8 mutations caught**. Nominated turn bound candidate `8a159445`; declined turn carried a full eight-field diagnostic and no story row |
> | **Phase 4 — what it did NOT change** | No threshold, anchor regex, chain classifier, source unit, review rule, memoir behaviour, migration or new table. The 114/14 banks were deliberately **not** rerun — Phase 4 changed observability, not extraction |
> | **Phase 4 — one honest gap** | **Ten of eleven acceptance clauses were proven LIVE.** `measurement_failed` is covered offline and by mutations 3 and 6 but has never been seen on a live turn. Also: a trigger firing with **no `person_id`** fits none of the three closed outcomes and deliberately records nothing — opening the vocabulary is Chris's call |
> | **Phase 3** | ✅ **ACCEPTED 2026-09-05.** Group-local kinship guard; per-value grounding (`spoken`/`derived`/`unsupported`); review-only results end to end; browser authority enforcement (the server's downgrade now binds the browser — it previously did not, which also silently affected shipped transcript safety); empty-correction fallthrough resetting BOTH copies of `turn_mode`. Live gate: Stefi `20260905-021741`, **9/9** over the production WebSocket |
> | **Phase 3 — last box closed** | *Jim binds as Pat's husband* — **CLOSED 2026-09-05.** `Jim` had no test anywhere while `Otis` had five and `Domingo` two. `TheJimCase` drives the shipped `run_field_extraction` with Pat's own wording: parent language elsewhere keeps `Walter` and quarantines Jim; the spouse field still reaches him. **The guard was already correct — nobody had written the test** |
> | **Extraction baseline** | **NOT comparable.** `r5h`/`r5j`/`r5k` span **three scorers** and two dirty trees over one case bank. `r5k`'s **0 `must_not_write` at `5afead5`** is solid current evidence; the `2 → 0` delta is **not established** — `must_not_write` is itself a scorer judgment. Nonblocking debt: [`docs/BACKLOG.md`](docs/BACKLOG.md) §6a |
> | **Testing doctrine** | **A fixture may not supply the property being proven.** The maintained table in [`docs/TESTING-DOCTRINE.md`](docs/TESTING-DOCTRINE.md) **owns the count** — no other document restates it. Every helper assertion needs a production-boundary companion, and every mutation must make that companion fail |
> | **Phase 2** | ✅ **CLOSED 2026-09-04** — read-only mechanism audit, cohort not rerun, nothing curated. Archival 38/38 · candidates 35/38 · transcripts 35/35 byte-exact · zero over-capture |
> | **Phase 1** | ✅ **ACCEPTED 2026-09-04.** `20260904T123556Z` performed the only two authorized mutations; `20260904T130525Z` carried that proof forward at **zero mutations** |
> | **Mutations — ALL SPENT** | `447eee18` is `promoted`, `building_years`/`operator_set`, `review_version: 3`. **No further mutation is authorized** |
> | **Do NOT** | curate the synthetic queue, promote the 35, adjust the classifier, rerun the cohort, or repair `turn_extraction_ledger` for a harness that never requested extraction |
>
> **A refusal is a result.** A run that stops before mutating, names the failing link and
> exits non-zero has done its job. It is not a failed attempt to be retried until it passes.
>
> **Profile Seed Phase 3 is OWED, not current.** It was a previous current action and is
> **IN IMPLEMENTATION with ACCEPTANCE OPEN**; it is not cancelled and not superseded — see
> §2. Hygiene Phase A remains ACCEPTED with its remainder PAUSED and
> `WO-REPOSITORY-HYGIENE-01` INCOMPLETE. **No priority change ever converts owed work into
> finished work**, and no document may say otherwise.
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
| **`WO-LORI-ARCHIVE-TO-MEMOIR-02`** | 🔵 **ACTIVE — Phases 0–2 CLOSED; PHASE 3 is the current action. §9.** **Phase 1** proved the memoir chain (`20260904T123556Z` mutations, `20260904T130525Z` proof at zero mutations, exit 0, agreement 1/1/1). **Phase 2** closed the mechanism audit read-only: archival 38/38, candidates 35/38, transcripts 35/35 byte-exact, zero over-capture. **Its findings were CORRECTED 2026-09-04 after reading `.runtime/logs/api.log`, which the original audit never opened:** the capture decision is recorded for all 38 turns and agrees exactly with the recomputed split (18/17/3), so the defect is durability not absence; the three misses share one cause (no relative time phrasing in a present-day life inventory); and the zero ledger rows are a **harness** gap, not a product defect. **Phase 3:** correction-route bypass + spouse-under-`parents.*`, both now cited to their reading lines — the browser regex at `app.js:2599` fires on *"not the"* in Stefi's clarification, and `chat_ws.py:965` passes `assistant_text=None` so the extractor reads the narrator. Capture-decision persistence is **Phase 4**. Reproduce: `python3 scripts/phase2_verify_ledger.py` |
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
| `docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md` | The **paused** repository lane — Phase A accepted, remainder deferred and incomplete. **Not the current action;** `WO-LORI-ARCHIVE-TO-MEMOIR-02` **Phase 5** is |
| `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md` + `..._PHASE2_TRANSPORT_MAP.md` | The owed Profile Seed lane — Phase 3 implementation landed, acceptance open |
| `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Binding Travel Document rulings |

Historical handoffs and long status narratives live in Git history and `docs/archive/`.
**They must not be appended back into this operational brief.**

## 9. `WO-LORI-ARCHIVE-TO-MEMOIR-02` — Phases 1–4 and 5A/5B CLOSED; **5C QUEUED behind the Lori measurement block** (2026-09-06)

**Phase 3 ACCEPTED 2026-09-05.** Its exit gate is met: Stefi follows the normal turn path,
the three spouse fixtures bind, no false parent field is written, and uncertain
relationships stay reviewable.

The last open clause was proven live rather than argued from source — the Stefi
correction-fallthrough gate `20260905-021741`, **9/9 over the production WebSocket**
(`scripts/stefi_correction_fallthrough_probe.py`). The turn routes as `correction` by the
shipped `app.js` regex, the parser finds nothing actionable, `[correction-fallthrough]`
fires, **no `correction_payload` frame and no `correction-apply`**, an ordinary response is
committed, both turns persist, and a story candidate is **preserved and bound** —
`bf8f41e6`, `user_row=2202`, `assistant_row=2203` — which a deterministic correction turn
never does. That candidate carries no placement, as it must.

**Clean final evaluations, at their recorded SHAs:** `r5k-guard-v2` 71/114 at `5afead5` on a
clean tree, 0 `must_not_write`; `r5k-generational` 7/14 at `4ab00fc`, clean, 0
`must_not_write`.

**What is NOT claimed.** The extraction baseline is not comparable: `r5h`, `r5j` and `r5k`
used **three different scorers** and two of the three ran on dirty trees. The r5h→r5k −7
measures scorer and extractor together. `r5k`'s **0 `must_not_write` is solid current
evidence**; the `2 → 0` delta is **not established** — `must_not_write` is a scorer
judgment. Registered as nonblocking measurement debt in
[`docs/BACKLOG.md`](docs/BACKLOG.md) §6a. **No further Phase 3 evaluation is needed.**

**PHASE 4 ACCEPTED 2026-09-05.** The capture decision is durable on the source narrator
turn, including the declined turns that create no candidate.

| | |
|---|---|
| Implementation SHA | `24c71309aa3dd3d73e58811cfec7b1359b670167`, clean tree |
| Live probe | `20260905-151658` — `scripts/story_capture_decision_probe.py` |
| Interpreter (live) | `.venv-gpu/bin/python`, the serving venv |
| Interpreter (offline) | `.venv/bin/python` — **241 tests, `OK`, ZERO skips** |
| Live result | **11 passed, 0 failed, 0 unverified** |
| Mutations | **8/8 caught**, product restored byte-exact |

Nominated turn: `borderline_scene_anchor`, candidate `8a159445`, bound to the same source
conversation. Declined turn: `below_all_capture_paths`, `candidate_id: null`, full eight-field
diagnostic, **no `story_candidates` row at all**. No narrator or assistant prose in either
record; nothing written to an assistant row.

**Ten of eleven acceptance clauses were proven LIVE. One was not** — `measurement_failed` is
covered by the offline suite and by mutations 3 and 6, but has never been seen on a live
turn, and the record says so.

**Nothing about capture changed.** No threshold, anchor regex, chain classifier, source unit,
review rule, memoir behaviour, migration or new table. The 114/14 extractor banks were
deliberately not rerun — Phase 4 changed observability, not extraction.

**One branch records nothing deliberately:** a trigger firing with no `person_id` fits none of
the three closed outcomes, so it stays an existing exclusion with the log line as its record,
pinned by a test. Opening the vocabulary is Chris's call.

**PHASE 5A AND 5B ARE COMPLETE 2026-09-05, review open.** Kinship normalization now retains
the narrator's own word: `ExtractedItem` carries `source_phrase` and `normalized_from`, and
one vocabulary — `server/code/api/services/relationship_interpreter.py` — decides every
relationship reading, with the kinship guard's per-role patterns DERIVED from it rather than
maintained beside it. That duplication is what let `mama` bind while `daddy` did not.

**The governing rule this phase installed:** *the model proposes an interpretation; the
NARRATOR'S WORDING decides which lane is legal.* The deliberately crossed passage — the
current wife proposed as prior partner, the ex-wife as current spouse — is corrected rather
than obeyed.

| Measured at the production boundary | |
|---|---|
| `tests.test_spouse_state_characterization` + `tests.test_kinship_qualifier_binding` | **74 tests, ZERO skips** |
| with the Phase 4 / 5A suites and the gate classifier | **156 tests, ZERO skips** |
| mutation gate `L1`–`L9` (checked in, reproducible) | **9/9 caught behaviourally**, 7 marked `was_real` |
| `node tests/test_family_tree_spouse_edge_types.js` | 26 checks, 2 call sites wired |
| 19 extraction-adjacent modules, 600 tests | failure set **byte-identical to the same modules at `HEAD` product code** |
| Interpreter | **agent sandbox `python3` only.** `.venv` is the verification and it is Chris's run |

**Four defects were found at the production boundary, and every one was invisible to a
helper-level test:** `getattr(req, "conv_id")` on a request that has no such field, so
production wrote null provenance while the real `session_id` sat unused; an `ExtractedItem`
constructor that names its kwargs, silently dropping the recorded narrator phrase one call
before the pass that needed it; a lane chosen by the *canonicalized* value, where `wife`
occurs twice and Mary's comes first; and grouping that runs before the lane pass, so moved
items reached callers with no person association while a comment claimed otherwise.

**What 5B does NOT claim.** No live turn was run — everything is offline against the shipped
path. `STATE_DECEASED` is recorded and consumed by nothing but the Family Tree edge. The
`adult` / `older` / `younger` qualifiers are read correctly and carried to no field; mapping
`older` onto `siblings.birthOrder` would manufacture a fact and was deliberately not done.
The 114/14 banks were not rerun.

**Phase 5C is QUEUED, not current** — the Lori measurement block runs first (see the
current-action box at the top of this file), because two of 5C's three open destinations
are questions the Walt+John evidence speaks to. Its scope is unchanged: meaning with no
schema destination, one disposition path for
"understood, no destination" instead of one per case, and a deliberate decision (or a
recorded refusal) for the qualifiers and for `STATE_DECEASED`. **Do not disable
`HORNELORE_CLAIMS_VALIDATORS` as a product fix** — it gates several safeguards while leaving
the parse-time whitelist active, and two of the three arity-crash paths found in 5B were that
flag's own branches.

**Phase 3's last open box is CLOSED (`a62bfeb`).** *Jim binds as Pat's husband* — `Jim`
had no test anywhere while `Otis` had five and `Domingo` two. `TheJimCase` now drives the
shipped `run_field_extraction` with Pat's own wording, with a positive spouse control.
**The guard was already correct; the coverage was missing.**

## 9a. Phase 1 and Phase 2 — the earlier record (2026-09-04)

> **The working detail that used to live here has been REMOVED, not lost.** It described a
> target that was unplaced at `review_version: 1`, preview and export unproven, and a "fresh
> run, no `--resume`" instruction — every one of which became false when the mutations
> landed, and one of which would have driven a fresh run against a promoted candidate.
> **A current-state document must not carry executable orders that have expired.** The full
> record, including all seven defects found while proving the chain, is in
> [`docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md`](docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md);
> the runs themselves are under `.runtime/eval/phase1-memoir-chain/`; Git holds the rest.

**Accepted on two runs, and the split is the claim:**

| Run | What it did | Mutations |
|---|---|---|
| `20260904T123556Z` | performed the **only two authorized mutations** — placement `v1→v2`, then promotion `v2→v3` | **2** |
| `20260904T130525Z` | **carried that proof forward** and completed preview and export | **0** |

Exit **0**, `Phase 1: PASS — full chain proven`. Agreement canonical **1** / preview **1** /
DOCX **1**. Control `5a56f942` **item identical — the changing `fetched_at` envelope
excluded by design**. `containsSourceId: false`; `forbidden: []`.

**Current target state:** `447eee18` is `promoted`, `building_years`/`operator_set`,
`review_version: 3`. **No further mutation is authorized.** There is no pending live run.

**Gates at acceptance:** 141 Python tests (zero skips on `.venv`) and **four** DOM suites —
launcher, memoir popover, placement workflow, row selection.

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
