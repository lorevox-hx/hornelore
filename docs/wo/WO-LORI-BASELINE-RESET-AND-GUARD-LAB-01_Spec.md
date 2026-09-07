# WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01

**Restore conversational Lori, and make every intervention measurable, selectable and accountable.**

Opened 2026-09-06 · **ACTIVE** · supersedes nothing; `WO-LORI-ARCHIVE-TO-MEMOIR-02`
Phase 5C is queued behind it deliberately.

---

## 1. Why this exists

The Walt+John diagnostic (`docs/reports/WALT-JOHN-VRAM-PROMPT-BUDGET-DIAGNOSTIC.md`,
local-only) measured 15 generated turns against what the narrator actually
received:

| | |
|---|---:|
| raw response was reasonable | **12 / 15** |
| delivered was **better** than raw | **0 / 15** |
| delivered was **worse** than raw | **11 / 15** |
| no control fired at all | 2 / 15 |

**The two untouched turns are among the best in the dataset.** Neither the
256-token cap nor VRAM was ever binding. The dominant cause of what narrators
read was the post-generation control layer.

The deeper problem was not any single control. It was that nobody could say
*which* layer did it. "The guards" were an undifferentiated mass spread across a
router, a control wrapper, a validator, a fallback composer and a final writer,
each added in good faith to stop a real failure somebody had witnessed, none
ever measured against the others.

**This work order builds the instrument, not the fix.** It does not decide which
controls are good. It gives them numbers, switches and evidence so that question
can be answered by experiment instead of by argument.

---

## 2. The governing principle

> **MEMORY STRICT. CONVERSATION LIGHT.**

| Lorevox owns — not switchable | Lori owns — switchable where registered |
|---|---|
| identity, provenance, extraction | listening, acknowledging, connecting |
| provisional/canonical truth, chronology | asking, conversational phrasing |
| timeline/spine, story capture | prompt instruction and example families |
| relationship integrity, archive/memoir | post-generation prose transforms |
| deletion/privacy, acute safety | validators, fallbacks, final writers |

**An authority earns a registry entry only if it can change what the narrator
receives.** Provenance, relationship meaning, lane selection, story-capture
records and committed-turn ownership are not in the 43 and must not be added —
including Phase 5C's "meaning with no schema destination", whose three outcomes
are field / review / recorded refusal. An operator checkbox that let information
silently vanish again would undo what 5C exists to establish.

**A deterministic conversational intervention earns authority only by
demonstrated benefit.** Not by having once fixed a bug.

---

## 3. What is built

Pushed and accepted. See `HANDOFF.md` for live state.

- **`lori_guard_registry.py`** — 43 authorities, derived from the tree and then
  numbered: 10 PROMPT, 7 ROUTE, 11 TRANSFORM, 6 VALIDATE, 3 REPLACE, 1
  FINAL_WRITER, 5 LOCKED. **IDs are stable and reserved**; a retired authority
  keeps its number. `position` is separate and is canonical execution order.
- **Control policy** — `SWITCHABLE` / `PROTECTED` / `PENDING_SEAM`, because
  "cannot, for safety" and "cannot, until someone splits a string" are different
  truths and an operator staring at a disabled row deserves to know which.
  Population **37 / 6 / 0**, derived.
- **Prompt seams** — the Kent/Janice witness few-shots and the reflection
  examples are separable, byte-exact, SHA-pinned against the literals they
  replaced.
- **`lori_guard_authority.py`** — three-state resolution (canonical default /
  operator override / effective state + reason), registry fingerprint over
  behavioural fields only, selection fingerprint, revision.
- **Migration 0053 + `lori_guard_store.py`** — durable operator overrides,
  installation-scoped, atomic batch, optimistic revision.
- **`lori_guard_gate.py` + `chat_ws` wiring** — one frozen acquisition per turn,
  the deterministic route family clamped.
- **`scripts/lori_guard_catalog.py`** — the catalog, generated from registry
  metadata. There is no second hand-maintained list.
- **All four runtime surfaces consume the snapshot.** Prompt composition
  (ids 1, 3–11), the route family (20–26) clamped at the DETECTOR rather
  than only at the finalizer, communication control (32–42) individually
  selectable, and the post-generation and final-writer authorities
  (30–31, 43–54) including the id 54 seam.
- **Legacy env authority retired (requirement T).** Four flags —
  `HORNELORE_REFLECTION_SHAPING`, the two phantom-noun flags, and
  `HORNELORE_STORY_FIRST_PHASE_1` — governed **eight** registered
  authorities (6, 7, 8, 30, 31, 36, 41, 42), not the five first
  identified. They are read once at acquisition as deployment DEFAULTS
  an operator override outranks; no runtime consumer calls them, and a
  structural test enforces that.
- **Distinct attribution (requirement L).** Ten identities across the
  comm-control service — 33, 34, 35, 37, 38, 39, 40, 41, 42 plus 36's
  pre-existing `reflection_shape` — each carrying selected / eligible /
  fired / result and before-after where text changes. Id 51 stays one
  authority and records which of its seven detect/repair pairs fired.
  **`selected` and `fired` are separate fields**, and a test fails if
  they ever coincide: selected means allowed, not that it acted.
- **Consumer accounting, both directions.** Every switchable id has a
  production consumer, and every narrator-facing writer, route gate and
  prompt block is registered or deliberately protected.
- **The operator control surface (sections Q + R).**
  `routers/operator_guard_lab.py`, gated by
  `HORNELORE_OPERATOR_GUARD_LAB=1` and answering 404 when off so an
  outside probe cannot distinguish "off" from "absent".
  - `GET /state` — all 43 rows with **four separate state fields**
    (canonical default, deployment default, operator override,
    effective) plus the reason, the policy and its reason, the revision,
    both fingerprints, the pending-seam list, and the gate's four
    eligibility conditions **named individually**. Without that last
    block the panel is a trap: an operator selects a lean baseline, gets
    canonical Lori because nothing is armed, and concludes the switches
    do nothing.
  - `POST /authorities/{id}` — `enabled` is three-valued; **null RESETS**
    by deleting the row, so the canonical default stays live in code.
    404 unknown · 400 with the policy reason for PROTECTED · 409 stale.
  - `POST /all-switchable-off`, `POST /restore-defaults` — **one request,
    one transaction, one revision**. Asserted as an exact delta.
  - `GET /narrators` — testing-only eligibility, **read-only, with no
    write partner**. This surface may show eligibility and never confer
    it.
  - Every mutation returns the WHOLE new state, which is what makes the
    panel reload-free and stops it re-deriving rows locally; a 409
    carries the live configuration so a stale second tab corrects itself
    instead of overwriting a newer selection.
  - The panel is a section of the **existing** Bug Panel
    (`ui/js/bug-panel-guard-lab.js`, mount `#lv10dBpGuardLab`), not a
    second experimental application. It is tested by RENDERING the
    shipped module (`scripts/ui/guard_lab_panel_domtest.js`) against a
    real server response — four mutations of the product turn it red,
    including one that loops 37 writes and one that patches a row
    locally instead of adopting the server's answer.

---

## 4. Invariants that must not be re-broken

1. **One acquisition per turn**, at the top of `_generate_and_stream_inner`,
   after `person_id`. It must dominate witness detection (~L2884), the browser's
   proposed `turn_mode` (~L3661) and every route gate (~L4207+). *"Before prompt
   composition" is already too late for routes.*
2. **Client proposes, server resolves.** Id 26's classifier is `lvRouteTurn` in
   `ui/js/app.js`, so a stale browser can propose `correction` regardless of what
   the server selected. A server detector cannot activate a disabled route
   either.
3. **Fail-closed on all four gate conditions** — a real person, durably
   `testing_only`, an armed eval marker, and a trace that is actually recording.
   An unmeasured experimental turn is worse than no experiment.
4. **Nothing downstream re-reads** the store, the marker, the eligibility flag or
   a legacy environment gate. Consumers read the snapshot.
5. **Selection controls membership only.** `{33,40}` and `{40,33}` are the same
   experiment; `position` decides order.
6. **Selected means allowed, not fired.** A selected authority still has its own
   eligibility condition.
7. **Safety precedence and id 20 floor hold survive `All Switchable Off`.** A
   narrator who has claimed the floor is not an experiment.
8. **PROMPT authorities are `requires_rerun`.** The trace may record `excluded`;
   it may never claim what an excluded prompt block *would have produced*.
9. **Id 54's seam wraps `finalize_presentation()` ONLY.** The existing
   `delivers_question()` containment at `chat_ws.py:6933` — *"the stamp follows
   the DELIVERED text, never the plan"* — is what stops protected id 53 stamping
   a presentation the narrator never received. Gating the enclosing block would
   remove it.

---

## 4a. Isolation contracts IC-1 … IC-12

**The authoritative negative-acceptance list.** Earlier work orders
referred to "V1–V12" without ever defining them here, and the only
`V1`/`V6` vocabulary that exists in this repository is the unrelated
pre-pivot SECTION-EFFECT extraction matrix
(`docs/archive/workorders-pre-pivot/`). Citing an undefined label as
acceptance is how a claim becomes unfalsifiable, so these are numbered
`IC-n` to avoid colliding with that older meaning.

Each is proven by a test that fails against the specific wrong
implementation named in the right-hand column.

| | Contract | The false implementation it catches |
|---|---|---|
| **IC-1** | One and only one authority acquisition per turn | Two acquisitions, so a turn runs half on one configuration |
| **IC-2** | No mid-turn re-resolution — no consumer reads the store, marker, eligibility, legacy env, or calls the resolver again | A consumer reads live state and changes underneath a half-composed response |
| **IC-3** | A client `turn_mode` proposal cannot reactivate a disabled route | A stale browser re-enters an excluded deterministic route |
| **IC-4** | A rejected route resets the effective mode downstream too, not only the local | `params["turn_mode"]` keeps the rejected proposal and extraction eligibility is lost |
| **IC-5** | Detector isolation — an OFF route discards its detector's narrator-facing side effects, not merely finalizer entry | Route OFF, but the detector still suppresses bank flush or injects grounding |
| **IC-6** | A real narrator cannot receive an experiment, whatever is armed | Overrides reach an ordinary narrator |
| **IC-7** | Client data cannot manufacture eligibility | `runtime71` / `profile_json` / `params` makes a narrator experimental |
| **IC-8** | An unmeasured experiment cannot run | Armed + testing-only + tracing off still applies overrides |
| **IC-9** | Store failure is fail-closed and never fails the turn | A Guard Lab read error costs the narrator their turn |
| **IC-10** | Mid-turn configuration change affects the next turn only | A toggle changes the turn already in flight |
| **IC-11** | `All Switchable Off` is truthful across all 37 | An authority survives through an env gate or an alternate path |
| **IC-12** | Id 54 OFF suppresses the replacement while `delivers_question()` containment still prevents id 53 stamping | The protected ledger stamps a presentation the narrator never received |

**Complement of the consumer accounting.** "Every switch has a wire" is
only half. The other half is *every relevant wire has a switch, or is
deliberately PROTECTED or outside the registry* — an unregistered
narrator-facing decision on a controlled surface is an authority nobody
can turn off and nobody can see.

---

## 5. What remains

| | |
|---|---|
| **Next slice** | **Live acceptance on a running stack**: no-restart toggling, the mid-turn freeze observed rather than only structurally proven, the stale-client clamp against a real second tab, restart persistence |
| **Then** | The lean baseline prompt and a populated synthetic Walt, then the owed §5 short-natural run |
| **Owed separately** | The response-trace closer (diagnostic finding 2, untouched). **Its sibling finding — that the deterministic witness path produced no trace at all — is CLOSED**: that was true of the frozen diagnostic tree, where those turns returned before tracing opened; the trace now opens at authority acquisition and deterministic responses complete through the shared finalizer |
| **External dependency — DISCHARGED 2026-09-07** | The `chat_ws` behavioural suites cannot execute in the agent sandbox (`transformers` absent, fails identically at HEAD), so `.venv-gpu` in WSL is their only verification. Run there: **48 tests, 48 passed, 0 skipped** — safety precedence, the fail-closed guard path, session identity and turn cancellation |

**No Walt or John run until `All Switchable Off` is truthful across routing,
prompt composition, transforms/replacements and the Profile Seed final writer.**

---

## 5a. The live acceptance — procedure and clauses

**Section X.** Run on the laptop, where `.venv-gpu`, the model and the
live database already are. The instrument is
`scripts/guard_lab_live_acceptance.py` — **read-only, with no mutation
path at all**; the acceptance is Chris in the browser and the script
records what that leaves behind. `tests/test_guard_lab_live_acceptance.py`
fails if it ever gains one.

**ORDER IS LOAD-BEARING, AND IT HAS TWO PHASES.** `trace_env.sh`
resolves the eval marker into `HORNELORE_RESPONSE_TRACE` **only when a
process starts**. Arm after the API is up and tracing stays off, the
gate refuses every experimental turn with `trace_not_enabled`, and
nothing on screen explains why.

**The testing-only narrator is NOT a before-startup condition, and
treating it as one made this procedure impossible to satisfy.** It can
only be created through the product UI, which needs a running stack —
so demanding it before startup asks `preflight` for its own output as
its input. The rule is about when the *startup configuration* exists,
not about when a read-only check may be run. So:

> marker armed and `HORNELORE_OPERATOR_GUARD_LAB=1` set **before the
> process starts** → start the stack → create the narrator through the
> product path → **re-run the read-only `preflight` against that same
> still-running stack** → continue the acceptance on it. No restart, and
> no second arming.

`preflight` distinguishes the two itself: **exit 1** when a
startup-time condition is unmet (*do not start the stack, you would
bake the wrong answer in*), **exit 3** for BOOTSTRAP INCOMPLETE when
only the narrator is missing (*start the stack and create it*), **exit
0** when all four hold.

| | Step | Evidence |
|---|---|---|
| 1 | `HORNELORE_OPERATOR_GUARD_LAB=1` in `.env`; arm a run-scoped marker | `preflight` no longer exits 1 |
| 2 | Start the stack (Chris) | trace banner says ENABLED and names the run directory |
| 3 | Create ONE testing narrator through the product path — **New narrator → "Skip — add narrator for testing only"**. **The live database holds none**, and it cannot be granted to an existing narrator afterwards | `preflight` exits 0 and lists it |
| 4 | Bug Panel → Guard Lab: 43 rows, four state fields, four gate conditions | `snapshot before-all-off` |
| 5 | Select the **listed testing narrator** for the interview, press `All Switchable Off`, talk to Lori | revision +1; traced turns carry `experiment_applied=true` |
| 6 | Change one authority without restarting; take another turn | two distinct consumed revisions in one process |
| 7 | Toggle **while Lori is generating**; note the unix second | `verify --toggle-at` decides the freeze |
| 8 | Second browser tab, stale revision, press a control | 409, conflict shown, live configuration adopted |
| 9 | Talk once to an ordinary narrator with a configuration selected | a turn refused `not_testing_only` |
| 10 | `snapshot before-restart`, stop, re-arm, start, `snapshot after-restart` | identical overrides at an unchanged revision |
| 11 | `verify`, then `Restore Defaults` unless the lean baseline is wanted | `N passed / 0 failed / 0 unverified` |

**Step 9 needs an ordinary narrator, not a family one.** The property
under test is `not_testing_only` — it says nothing about any particular
person, and any narrator whose `testing_only` is false demonstrates it
identically. Use one of the synthetic `ZZ COHORT` narrators already in
the database. There is no reason to route this through Kent or Janice.

**Step 10's snapshots are selected BY LABEL.** `verify` compares the
snapshot named `before-restart` against the one named `after-restart`
(the latest such pair, so a retried restart supersedes an earlier
attempt) — never the first and last files in the run directory. It also
refuses a vacuous pass: if `before-restart` carries no override, two
matching snapshots prove nothing and the clause is `UNVERIFIED`.

**`UNVERIFIED` IS NOT A SOFT PASS** and exits 2. Six of the clauses are
decided by comparing two recorded facts, and a person reading a log at
midnight believes whichever they expected.

**The mid-turn freeze is not decidable from the trace alone.** It needs
the operator's own timestamp for the toggle compared against the turn's
start and end, so the script requires `--toggle-at` and reports
`UNVERIFIED` without it rather than inferring it from turn order.

**One distinction the panel does not close.** It answers *is there an
eligible testing narrator?* — not *is the narrator currently selected in
the interview that narrator?* So the test narrator has to be chosen
deliberately. Talking to Kent, Janice or any other ordinary narrator
gives canonical Lori whatever the panel shows selected. **That is the
safety property, not a failure**, and step 9 exists to observe it rather
than assume it.

**`stop_all.sh` disarms the marker.** The override and the revision live
in SQLite and survive the restart; tracing does not. Re-arm before the
second start or step 10's turns are unrecorded.

---

## 6. Harness consequence

`run_lori_behavior_harness.py` uses synthetic ids such as `eval_person`. Under
the correct fail-closed gate an unpersisted person gets canonical production
behaviour. **Do not weaken the server gate for the harness** — make the harness
create and use a real `testing_only=true` narrator.

---

## 7. Recorded corrections

Kept because each was a wrong assumption that survived review once.

- **Kent and Janice are consenting lab narrators.** Their material in the prompt
  is an exemplar-leak and overfitting finding, **not a privacy defect**. Do not
  delete it and do not replace it with synthetic biographies — that would destroy
  the ability to tell authentic oral-history complexity from artificial examples.
- **`testing_only` was persisted nowhere.** Inferring storage from a response key
  is the "cite the line that READS the value" failure.
- **People columns are owned by `init_db()`'s PRAGMA-guarded block, never by a
  migration.** Migration 0013's header records the incident.
- **Excluding the prompt examples does not make the prompt name-free.** Both
  directives keep narrator nouns inside *prohibitions*; those are the guards
  against the failures they describe.
- **Tests that create narrators must isolate `DATA_DIR` and refuse to run
  otherwise.** `DB_PATH` resolves at import, relative to cwd.
