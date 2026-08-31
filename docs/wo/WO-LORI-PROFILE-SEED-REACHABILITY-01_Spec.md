# WO-LORI-PROFILE-SEED-REACHABILITY-01

**Make the preserved ten-topic Profile Seed onboarding reachable, durable and finite.**

**Authored:** 2026-08-26 against `main` at `6952ad0`  
**Predecessor:** `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01`, accepted and complete.

**Status:** IN IMPLEMENTATION — **Phases 0, 1 and 2 are ACCEPTED. Phase 3 is IN
IMPLEMENTATION with ACCEPTANCE OPEN.** Reconciled against pushed `origin/main` at
`2b7e634`, 2026-08-30.

**Phase 3 is neither "not started" nor complete, and it is NOT accepted.** It said "CURRENT,
NOT STARTED" while eleven commits of it were already pushed — the stale-status defect this
lane has now produced three times. What follows is the pushed tree, not a plan.

| Phase | State |
|---|---|
| 0 — executable map | **ACCEPTED** at `661aa95` |
| 1 — server authority | **ACCEPTED** at `1288baa` |
| 2 — prompt and committed-turn wiring | ✅ **ACCEPTED 2026-08-29, steps 1–7 complete.** Steps 1–5 (step 5 `9127adb`); pre-Step-6 checkpoint `d0e5294`; **step 6 `12221e0`…`58dfc40`, proven live 16/16 twice through the production WebSocket and the real model**; step 7 — consolidated closure — `6885bb2`. Evidence by checkpoint: `HANDOFF.md` §1a |
| 3 — browser promotion sites and server authority | 🔵 **IN IMPLEMENTATION, ACCEPTANCE OPEN.** Landed and pushed; live acceptance not yet passed. See the ledger below |
| 4–5 | not begun, **not accepted** |

**Phase 3 — what is landed and pushed:**

| Range | What |
|---|---|
| `ff8efe3`…`5cd24e3` | Browser/server authority and attestation; server-derived effective phase; centralized promotion policy; narrator-scoped hydration |
| `579a281` | **Presentation identity separated from the concurrency version** — migration 0052 adds `presentation_epoch` |
| `f894a04` | Mutation coverage for the epoch, plus the consent-seed correction. Gate: **14/14 CAUGHT** |
| `6d908bc`…`f7c167c` | Cohort instrument foundation |
| `9cc4a42` | Orientation clock defaults **OFF** — it rendered opaque over the conversation |
| `490eaee` | Narrow-width composer restored — `#chatInput` was 33px and untypeable |
| `2b7e634` | **Deterministic canonical question delivery** — no presentation event without a delivered question |

**Phase 3 acceptance is OPEN on six conditions**, none of which is a documentation task:

1. deterministic delivery proven through the real UI **and** the persistence seam;
2. the narrator room usable at ~690px, ~900px and desktop width;
3. Profile Seed Pause/Resume visible and working;
4. the quick multi-era cohort reviewed **from actual Lori text**, not pass counts;
5. restart and narrator-switch isolation passing;
6. **the language boundary resolved explicitly** — see §3.1a.

Phase 2 steps 1–3 have landed: `f23040b` characterizes all eight refusal patterns;
`5a1eb56` moves them to one shared helper called by extraction and Profile Seed; `1875821`
adds the turn state-machine service — two durable events, exact
`(topic, presentation_epoch)` tuples *(they were `(topic, version)` until migration 0052;
`version` remains the optimistic-concurrency token and is still what `expected_version`
compares — it is no longer part of the question's identity)*,
classification and recovery; `b069680` corrects consumption so a response answers every
earlier presentation of its tuple; `c6c9ae4` adds a reproducible checked-in mutation
gate; and `0335cd3` makes that gate refuse an unclean tree or a red baseline, without
which every mutation could report CAUGHT against a suite that was already failing.

**Step 4 — the isolated composer section — is ACCEPTED at `b269184`.** It landed at
`620d692` and took eleven rounds of correction. The full range is the ledger for this step,
and it lives HERE and nowhere else:

| Commit | What it corrected |
|---|---|
| `620d692` | Step 4 lands — one canonical topic reaches Lori, nothing else moves |
| `2cfffae` | Apostrophes in two modules; the completion Lori could never deliver |
| `890e181` | Honest instruments — real idle mutation, baseline counts, policy note |
| `75e81c2` | One registry, one validated plan, tests measuring equality not subset |
| `e9e3cd3` | Strict `completes_walk`; three comments that pointed at nothing |
| `a1fe350` | The acknowledgement stops claiming the walk is over |
| `9f31d9f` | The asking turn stops claiming a last topic |
| `c99eb5f` | The AST guards scoped to `_profile_seed_onboarding_block` |
| `3e4c56a` | **Product:** malformed `known_topics` can no longer crash or invent settled topics |
| `a966a37` | Post-baseline additions inventory; three-module Step 4 gate |
| `b5148ed` | Errors-only runs are BROKEN; C15 split into three discriminating mutations |
| `b269184` | The last summary decides, and must agree with the exit code — **ACCEPTED** |

**`9f31d9f` is NOT the acceptance hash.** It was accepted there and the acceptance was
premature: **FIVE further corrective commits followed** — `c99eb5f`, `3e4c56a`, `a966a37`,
`b5148ed`, `b269184` — one of them a real product defect. It is recorded above as what it
is, a step in the range, and any document still naming it as the acceptance point is stale.
*(Recording it this way is deliberate. The tidier option is to list only the final hash,
and it would erase the fact that this step was declared finished five commits before it
was. The count itself first read "four", which is the sixth miscount in this lane and the
reason every number in this block is now derived from `git log` rather than read off the
table above.)*

**Two documentation commits sit inside this range and are deliberately NOT ledger rows:**
`da96cc0`, the five-control sweep during the corrections, and `d6e775a`, the reconciliation
that recorded the premature acceptance at `9f31d9f`. The ledger is the CODE AND TEST range
— twelve commits, one landing plus eleven corrections. *(`da96cc0` was a row here until
2026-08-26, which made the table inconsistent with itself: one docs commit listed, the
other excluded. A ledger that admits some non-code commits and not others cannot be counted
from.)*

Review found, across those rounds: a second hand-written question order in the composer; a
sparse-runtime byte-stability test asserting a subset rather than equality; a suppression
predicate broader than the renderer, so malformed state could silently remove existing
directives; an identity result inferred from a composer payload rather than supplied by the
server; an artificial FastAPI skip hiding thirty-five tests; and — twice, in two different
branches — **an authoritative claim about server state made before the versioned apply.**
The acknowledgement said the walk was complete; the asking turn said a topic was the last
one whenever `remaining_topics` was missing, empty or not a list. Both are gone. The
recurring lesson is recorded because it will recur: *the composer cannot know the outcome
of an apply it has not made.*

**Three lessons about the INSTRUMENT, which cost as many rounds as the product did.** A
guard that fails for reasons outside its own subject teaches people to switch it off, so
the AST checks read one function rather than the module. A mutation caught by a guard it
was not aiming at proves nothing about the guard it was — `C15`'s fixture collided with the
active topic and was rejected before the defect it targeted was ever reached, so it is now
three mutations, each discriminating one check. And a mutation that breaks the module
outright is not evidence at all: `C16` was written against a constant that does not exist,
the module failed at import, and the gate reported CAUGHT having tested nothing. The rule
is now the property rather than a list of exception names — **at least one real assertion
failure** — with the classifier's own tests running as an unconditional preflight, proven
able to refuse the gate rather than merely present in it.

**Step 5 — REST read authority — is ACCEPTED at `9127adb`.** It landed at `687c655` and
took EIGHT corrective commits:

| Commit | What it corrected |
|---|---|
| `687c655` | Step 5 lands — REST composes from server-authoritative onboarding state |
| `4c075b4` | Byte stability, route ordering, one snapshot, claim scope, `person_id` |
| `850f145` | Handler requirement derived from the service, not counted |
| `8d99a5e` | Race pointed the right way; exact status mapping; routes actually called |
| `b0b20b7` | The rollback must not mask the fault it follows |
| `3d7aa83` | The Option B limitation stated accurately, and pinned |
| `ef597ae` | Both-routes tests entered one route; answered-topic test never answered |
| `a612ee0` | Ambiguous-anchor guard covered; S11 added; `was_real` corrected |
| `9127adb` | Truthful test labels; the interpreter that can run the route gate — **ACCEPTED** |

*(The count first read "six" and the table omitted `a612ee0`. It is a lane commit —
it changes `run_mutation_gate.py` and `test_mutation_gate_classifier.py`, both Step 5
files — and it was dropped because it had been filed mentally as "gate work" rather than
as part of the step. That is the seventh miscount in this lane, and the same cause every
time: a number read off a narrative instead of derived. The eight are enumerated by
`git log --reverse 687c655..HEAD` filtered to lane files.)*

Git-derived, `687c655~1..9127adb`, lane files only: **6 files, +2203 / −10**.

### Pre-Step-6 correction checkpoint — ACCEPTED at `d0e5294`

**Accepted 2026-08-28**, between Step 5 and Step 6. Three commits:

| Commit | What |
|---|---|
| `157af46` | five product corrections — `M1`/`M8` repaired to fail by assertion; `expected_version` strict at request and accessor; the deterministic inventory corrected from six paths to **nine**; `HOLD` for control and system-directive turns with one shared control vocabulary; the derived-head rule in `HANDOFF.md` |
| `34cdf54` | acceptance-instrument corrections — route-stack guard names `fastapi` as well as `pydantic`; the nine-path inventory counts **call sites**, not distinct labels |
| `d0e5294` | the dependency sweep narrowed to `ModuleNotFoundError` with a matching root; `D4` unstarred; §16a's account of the two instrument defects corrected. **The acceptance point** |

**Evidence:** full clean-tree gate at `34cdf54` — **63/63 caught**, nine baselines green;
targeted gate at `d0e5294` — `P11` and `D4` **2/2**; strict suite `.venv-gpu` and `.venv`
both **22/22 with zero skips**; truthful shipped-design count **24**; tree clean, mutation
journal cleared.

**Step 6 was NOT STARTED at that checkpoint**, and its design was unchanged by it.
*(Dated statement, kept as history. Step 6 is now ACCEPTED — see the phase table.)* *(This also said
Step 6 was "additionally frozen until the repository-hygiene checkpoint is accepted". That
freeze is **superseded** — Chris's product-priority decision of 2026-08-28 accepted hygiene
Phase A, deferred the remainder, and made Step 6 the current action. See `HANDOFF.md`.)*
What Step 6 inherits and must not undo is in
[`WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md`](WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md)
§16 and §16a.

**THE ZERO-SKIP ROUTE GATE PASSED** — 48 tests, `OK`, **zero skips**, run on WSL with the
serving venv:

```bash
HORNELORE_REQUIRE_ROUTE_TESTS=1 PYTHONPATH=server/code \
    .venv-gpu/bin/python -m unittest tests.test_profile_seed_rest_read_authority
```

Both `chat` and `chat_stream` were entered for **contradictory claim**, **owner mismatch**,
**storage failure**, and the **non-refusal tripwire control** — asserted by
`assertBothRoutesExercised()`, so a partial pass is not possible. `.venv-gpu` is the only
interpreter that can import `api.api` (`.venv` and system `python3` both lack fastapi).

Focused **48 OK** · Step 4 + gate + bug-panel **168 OK** · reducer + refusal **84 OK** ·
preservation **156 OK (expected failures=1)** · mutations **S1–S11 11/11 CAUGHT**, six
marked as designs this lane actually shipped.

**"No live transport supplies `profile_seed_onboarding`" IS NO LONGER TRUE, and the
sentence has been removed everywhere it appeared.** REST supplies it now, verified against
the running API: a narrator created through the real intake form was asked her first
canonical topic over `/api/chat`. What remains true, and is the more useful statement:

> **The PRODUCTION NARRATOR UI path was still unwired when this was written, and is not
> now — Step 6 wired it and it is accepted on live evidence.** `ui/js/api.js` drives
> `/api/chat/ws`; a complete narrator turn produces **zero HTTP requests matching
> "chat"**. `/api/chat` has no UI caller at all, and `/api/chat/stream` is reachable only
> behind `window.LV_ALLOW_SSE_FALLBACK === true`, a dev-only escape hatch guarded by
> `BUG-SSE-FALLBACK-BYPASSES-CHAT-WS-GUARDS-01`. **A narrator using the production UI
> reaches the walk at Step 6.**
>
> *(This said "a real narrator reaches the walk at Step 6, not Step 5", which contradicts
> the live probe recorded immediately above it — a narrator WAS asked her first canonical
> topic over `/api/chat`. REST has already reached the walk. What Step 6 adds is the
> transport the product actually uses.)*

**Option B, preserved and unchanged: REST reads authority and does not advance.** Nothing
in Step 5 writes a turn event. The consequence, measured live: a narrator answers a topic
and the durable row still reads `active=childhood_home · remaining=10 · version=2`. Within
a session the conversation history hides it; **across a session boundary Lori asks for
something she was already told** — the re-interrogation Principle 8 forbids, arriving
through a gap in recording rather than by design. Pinned by
`test_an_answer_recorded_as_REST_SHAPED_TURNS_is_never_applied`, which is written to be
REPLACED when Step 6 lands rather than deleted.

**No historical-narrator auto-enrollment, and the consequence is live.** Enrollment happens
only inside `create_person()`. Measured against the running database: **all five existing
narrators — Del, Melanie Zollner, Janice, Kent and Christopher — are `enrolled: false`**,
so the ten-topic walk is permanently unreachable for them. That is doctrine working as
written, not a defect; extending the walk to family narrators is a **backfill decision**,
not a code change.

**Binding requirement, met:** REST supplies the server-derived narrator **name, DOB and
birthplace** alongside `identity_complete` and the resolved `person_id`. Supplying the
Boolean alone produces prompt text stating no verified identity facts are available — a
runtime that contradicts itself — and `person_id` is load-bearing because the composer's
person-dependent memory layer is skipped without it.

**Step 6 is ACCEPTED — 2026-08-29, on live evidence.** Implemented `12221e0`, corrected
`58dfc40`, instrument committed `525a43f`; 16/16 twice through the production WebSocket and
the real model. **Step 7 — consolidated closure — is ACCEPTED at `6885bb2`, and Phase 2
with it. Phase 3 is the current action.**

*(This block read "READY FOR IMPLEMENTATION" until 2026-08-26, contradicting §6's own
`STATUS: COMPLETE, ACCEPTED` two hundred lines below. A spec whose header disagrees with its
body is worse than one that is merely stale, because the header is the part a reader trusts
without scrolling. It became a table on the same day, after prose bold nested inside prose
bold for the third time in this lane — a table cannot nest.)*

---

## 1. Product outcome

An ordinary newly created Lorevox narrator reaches the ten-topic Profile Seed conversation
after the three identity anchors are known. Lori asks only about topics that remain unknown,
one at a time, and the narrator can answer, say there is none, decline, pause, or move on.
Progress survives reload, restart, narrator switching and a second browser. When the walk is
finished, the narrator advances to the Life Map interview and is not enrolled again.

This applies to a new narrator **regardless of `narrator_type`**. Narrator type is neither an
activation predicate nor a completion predicate.

## 2. Why the workflow is preserved but ordinarily unreachable

The present code has all of the pieces, but their gates do not overlap on the ordinary path.

1. `ui/js/narrator-intake.js` requires name, date of birth and place of birth and writes them
   through `POST /api/people/intake`.
2. `lvxSwitchNarratorSafe()` resets browser state to `currentPass = "pass1"`.
3. `loadPerson()` immediately restores or fetches a chronology. A cached chronology promotes
   `pass1 → pass2a`; `_hydrateChronologyFromServer()` does the same when the server returns
   derived eras. `initTimelineSpine()` and the chronology UI contain additional promotions.
4. `prompt_composer.py` emits the preserved ten-topic block only for an identity-complete
   interviewer turn whose browser-supplied `current_pass` is still `pass1`.

The ordinary intake itself supplies what chronology needs, so chronology wins the race before
the narrator's first normal turn. A testing-only narrator without the three anchors goes down
identity mode instead, which mutually excludes the ten-topic block. The workflow is therefore
present in source and covered as a predicate, but neither ordinary creation path proves that a
real narrator reaches it.

### 2.1 Current ownership defect

`currentPass` has no durable server owner. It is initialized and mutated in browser memory,
sent in `runtime71`, and defaulted independently by the composer. A chronology cache is doing
two unrelated jobs:

- painting the Life Map; and
- deciding that Profile Seed onboarding is over.

That makes the same narrator `pass1` on one device and `pass2a` on another, and clearing a
cache can reverse the result.

### 2.2 Current completion-data defects

The ten questions and `_build_profile_seed()` are not the same contract.

| Topic | Current evidence gap |
|---|---|
| Childhood home | `childhood_home` is populated from birthplace; being born somewhere does not prove the narrator grew up there. |
| Siblings | The ten-topic walk asks it, but `_build_profile_seed()` has no `siblings` bucket. |
| Education | Intake writes `education.highestLevel`; `_build_profile_seed()` reads `schooling` / `higherEducation`. An operator-supplied answer can look absent. |
| Military | **Two defects, not one.** Intake omits `served=False` from `profile_json`; *and* `_build_profile_seed()` ignores the Boolean **in both directions**, because `_first_str()` accepts only strings and `served` is never in its candidate list. So “served”, “did not serve” and “never asked” are all indistinguishable, and an affirmative survives only through a descriptive field such as `branch`. Storing the Boolean is necessary but not sufficient — the read adapter must be corrected too. *(This row named only the omitted `False` until 2026-08-26; Phase 0 measured the read side.)* |
| Partner / children | Empty arrays cannot distinguish an explicit “none” from an unanswered optional section. |
| Life stage | The seed derives an age band, not the question's actual “retired or still working” answer. |

The browser's `state.session.profileSeed` object does not repair this. It initializes ten keys
to `null`; no production writer changes them to `true`, and the server later replaces the
runtime seed with its own database-derived dictionary.

## 3. Binding decisions

1. **Preserve the ten topics.** This work order makes them reachable; it does not retire or
   reduce them.
2. **No narrator-type gate.** Live, reference, or any future type follows the same rule when
   newly enrolled.
3. **Do not auto-enrol historical narrators.** A missing new state row on an existing person
   means legacy/not enrolled, not “start a questionnaire now.”
4. **The server owns enrollment and progress.** Browser state may display it but cannot be the
   authority.
5. **Chronology readiness and onboarding completion are independent.** A Life Map may be ready
   while Profile Seed is still active.
6. **Known facts are skipped.** Canonical, operator-entered and provisional structured truth
   may satisfy a topic; a derived guess may not.
7. **Negative and declined answers are real completion states.** “No siblings,” “I did not
   serve,” “no children,” and “I would rather not discuss that” must not cause the same
   question to return forever.
8. **Progress rows store no narrator prose.** Biography remains in its existing truth stores;
   onboarding state stores topic ids, dispositions, versions and timestamps only.
9. **One question per turn, no menu.** The workflow remains conversational and honors the
   active session style without combining topics.
10. **The directive-family registry stays inert.** Its metadata may be updated after the real
    behavior lands; this work does not activate it.

## 4. Canonical contract

### 4.1 One topic registry

Add one server-owned registry, in order:

1. `childhood_home`
2. `siblings`
3. `parents_work`
4. `heritage`
5. `education`
6. `military`
7. `career`
8. `partner`
9. `children`
10. `life_stage`

The registry owns the stable id, narrator-facing intent, structured-evidence resolver and
whether an explicit negative is meaningful. The composer must render from this registry; it
must not keep a second hand-written order.

### 4.2 Durable state

Migration `0051` adds one row per enrolled narrator, for example
`profile_seed_onboarding`:

- `person_id` — primary key and `ON DELETE CASCADE` foreign key;
- `status` — `pending | active | paused | completed`;
- `topic_state_json` — each canonical topic mapped only to
  `unanswered | known | addressed | declined`;
- `active_topic_id` — nullable canonical topic id;
- `version` — server-owned monotonic compare-and-write version;
- `created_at`, `updated_at`, `completed_at`.

The migration creates the table but does **not** insert rows for existing people. All person
creation services used after the migration create the onboarding row in the same transaction
as the person row. A caller cannot opt out by choosing a narrator type.

If atomic enrollment cannot be achieved through the current `create_person()` transaction,
stop and move enrollment into that transaction; do not accept “person created, onboarding
best-effort” as a partial success.

### 4.3 Completion resolver

Build one resolver that combines:

- the corrected server `profile_seed` projection;
- `profiles.profile_json`;
- operator-entered `bio_facts`;
- `interview_projections` structured/provisional fields; and
- the disposition already stored for the topic.

The resolver returns ordered `known_topics`, `remaining_topics`, `active_topic_id`, `status`
and `version`. It never uses age band as proof of retired/working status and never uses
birthplace alone as proof of childhood home.

Correct the read adapters before using them as gates:

- add the siblings bucket;
- read `education.highestLevel` as education evidence;
- preserve explicit military non-service;
- preserve explicit no-partner / no-children answers;
- add an actual working/retirement value for `life_stage` rather than treating derived age as
  completion.

These are compatibility reads and explicit dispositions, not a profile-schema rewrite.

### 4.4 API and concurrency

Expose the state under the existing interview authority, not a second onboarding engine:

- `GET /api/interview/profile-seed?person_id=...` returns the resolved state;
- `PATCH /api/interview/profile-seed` records a topic disposition or pause/resume/completion
  using `expected_version`.

A stale write returns **409** and changes nothing. An unknown topic id returns **422**. A
narrator switch cannot apply a late response to the newly selected narrator.

### 4.5 Turn behavior

Before prompt composition, the server resolves onboarding by `person_id` and overwrites any
browser opinion about Profile Seed activation. All three transports must use the same
resolved state.

When active:

- the prompt receives exactly one `active_topic_id`, the known-topic summary and the allowed
  one-question instruction;
- existing structured evidence can change a topic from `unanswered` to `known`;
- a substantive answer to the active topic records `addressed` after the completed user and
  assistant turn rows exist;
- an explicit refusal records `declined` without storing the refusal text in the progress row;
- a control/meta turn (“repeat that,” help, pause, change narrator) does not advance the topic;
- completion occurs when no topics remain, then and only then the effective interview pass
  becomes `pass2a`.

Use the existing committed-turn finalization path. Do not add a browser-only counter and do
not infer completion from the mere existence of a chronology.

## 5. Browser behavior

1. Hydrate Profile Seed state during narrator load before enabling the first normal turn.
2. Treat `state.session.currentPass` as a view of the server decision.
3. Remove Profile Seed completion side effects from chronology hydration, cache restoration,
   `initTimelineSpine()` and chronology selection. Those paths may set a default era and may
   say the Life Map is ready; they may not end onboarding.
4. Reset onboarding view state before a narrator switch and discard late responses by
   generation/person id.
5. Show compact progress and a pause/resume affordance on the operator surface. Do not show a
   ten-item menu to the narrator.
6. Delete the dead all-null `state.session.profileSeed` tracker only after every reader is
   repointed. Do not leave a comment claiming it records answers when it does not.

## 6. Sequenced implementation

### Phase 0 — executable map, no behavior change

**STATUS: COMPLETE, ACCEPTED (2026-08-26).** Test-only; no product code or
schema changed. Three modules, 46 tests, one expected failure —
`tests/test_profile_seed_reachability_map.py` (13),
`tests/test_profile_seed_topic_fixtures.py` (23),
`tests/test_profile_seed_ordinary_intake_reachability.py` (10). Run with
`PYTHONPATH=server/code python3` — **not** `.venv`, which has no fastapi.

- Pin every current `pass1 → pass2a` writer and every composer activation path in tests.
  **Done:** eight distinct client sites, each pinned by enclosing function, plus per-file
  counts and a whole-tree stray sweep. Includes the direct ready-narrator initialisation,
  which seats a narrator in `pass2a` **and** `identityPhase: "complete"` in one object
  literal — so a "ready" narrator never occupies `pass1` for a single turn.
- Add a failing ordinary-intake reachability test that demonstrates the present skip.
  **Done** as one `expectedFailure`, proven to report an unexpected success when the fix is
  simulated. The identity-incomplete exclusion is pinned as CORRECT behaviour — Profile Seed
  must not run before the anchors are collected — and guards against an over-broad fix.
- Add fixtures for all ten topic evidence shapes, including explicit negatives.
  **Done** against this work order's `unanswered | known | addressed | declined`. An explicit
  negative is evidence resolving to `known` or `addressed`, never a fifth state.

**Findings that change Phase 1's inputs:**

- **The pass is browser-owned.** No file under `server/code/api` assigns a pass value, and
  `db.py` never persists one. Onboarding progress has no server-side owner today.
- **`_build_profile_seed()` returns five keys** — `age_years`, `childhood_home`,
  `full_name`, `life_stage`, `preferred_name` — of which only **two** correspond to walk
  topics, and **both are derived wrongly**. It does not answer five of the ten questions; it
  answers approximately none of them.
- **Military is worse than §2.2 stated.** `_first_str()` accepts only strings, so the
  `served` Boolean is ignored **in both directions**. "Served", "did not serve" and "never
  asked" are indistinguishable; an affirmative survives only through a descriptive field
  such as `branch`.
- **Childhood home overrides a real fact.** A `bio_facts.childhood_home_address` written
  through `bio_fact_create()` does not reach the seed; the bucket is sourced entirely from
  birthplace, so it is named for a question it never answers.
- **`community.retirementStatus` never reaches `life_stage`**, which stays an age band even
  when the narrator has stated they still work.
- **There is no canonical marital-status field.** `bio_schema` has `spouse_name`,
  `marriage_year`, `marriage_place`. Intake's `marital_status` lands in
  `profile_json.marriage.status`, which the seed does not read — so an explicit "never
  married" has nowhere to live. Phase 1 must give it one.
- **Test-harness constraint.** `bio_facts.field_key` has a foreign key to `bio_fields`, and
  `db._BIO_SEED_LOADED` is a once-per-process seed gate. A suite that switches `DB_PATH`
  more than once gets an empty registry, after which every `bio_fact_create()` fails with
  "FOREIGN KEY constraint failed" — which reads like a missing person row and is not.
  Reset `db._BIO_SEED_LOADED = False` before `init_db()`, as `db.py:62-70` documents.

**All five findings above are CLOSED by Phase 1, which is ACCEPTED. Phase 2 — prompt and
committed-turn wiring — is IN IMPLEMENTATION and is NOT ACCEPTED; see the status table at the top of this file for which steps have landed.** *(This line read "Phase 1 — server
authority — is next" until 2026-08-26. It sat immediately above the Phase 1 heading, whose
own status block already said the phase was complete, so the spec contradicted itself across
two consecutive lines.)*

### Phase 1 — server authority

**STATUS: COMPLETE, ACCEPTED (2026-08-26) at `1288baa`.** Built at `f343031`, held on review
for two corrections about silent failure, corrected, and accepted on the second review.
**Phase 2 — prompt and committed-turn wiring — is IN IMPLEMENTATION and is NOT accepted.**

- Migration 0051 and database accessors.
- Canonical topic registry and completion resolver.
- Atomic enrollment on every person-creation path.
- GET/PATCH contract with version conflicts and hard-delete cascade coverage.

**What landed.** `profile_seed_onboarding` with a real `ON DELETE CASCADE` and no backfill;
`services/profile_seed.py` holding the canonical ten-topic registry, the identity
precondition and one connection-scoped evidence resolver; atomic enrollment inside
`create_person()`'s transaction with rollback; versioned `GET`/`PATCH` under the existing
interview authority; the onboarding row in the ORDINARY deletion inventory. Two bounded
write-path corrections in `people.py` give an explicit non-service and an explicit
"never married" somewhere to live, without which the evidence rules for Boolean `False`
and marital status are correct but unreachable from the product path. `bio_schema` gains
`marital_status`.

**Two corrections after the first review, both about silent failure.**

- **Storage faults are not absence.** Five readers caught `sqlite3.Error` and returned an
  empty result. In this module every empty result is a PRODUCT DECISION — no onboarding row
  means "historical", no `people` row means "identity incomplete", no `bio_facts` means "ten
  topics unanswered" — so a locked database could have produced a narrator with ten
  unanswered topics, and the product's response to that is to ask all ten questions again.
  Someone who had already told Lori about their siblings would be asked about their siblings
  because a query failed. The suppression is removed; SQLite errors propagate. The narrow
  JSON-decoding defences are kept, because a malformed blob is a real recoverable data
  condition rather than an invented lifecycle state.
- **Historical is not nonexistent.** `GET` returned `200 enrolled:false` for any id with no
  onboarding row, including ids naming nobody. `enrolled: false` is a claim about a REAL
  narrator; a typo, a stale bookmark or a deleted narrator must not receive it. An existing
  narrator without a row is still `200 enrolled:false`; an unknown `person_id` is now `404`.
  Neither writes.

**Phase 1 does NOT make the walk reachable.** That is Phases 2 and 3. Phase 0's ordinary
reachability defect remains an `expectedFailure` and a Phase 1 test asserts it stays one.

### Phase 2 — prompt and completed-turn wiring

- Resolve state by narrator before all three transports compose.
- Render one canonical current topic from the registry.
- Advance only from the committed-turn path; keep meta/control turns stationary.
- Complete into `pass2a` without touching model, context window, safety, or the inert registry.

### Phase 3 — browser reachability

- Hydrate/reset safely on load and narrator switch.
- Separate chronology readiness from onboarding completion at every promotion site.
- Add operator progress plus pause/resume.
- Remove the dead UI tracker after repointing.

#### 3.1 Close the delivery proof — OWED

`2b7e634` is implemented and pushed. It is **not** live-accepted.

**The promised real-persistence proof is missing.** `test_profile_seed_presentation_delivery`
pins the router seam by reading source, and the existing persistence tests write
`"Lori says…"` — neither exercises `finalize_presentation` through storage. A source
assertion proves the call is wired, not that the bytes survive. Owed:

- build the finalized canonical presentation;
- persist it through `persist_turn_transaction`;
- read it back through `export_turns`;
- prove the assistant row carries **both** the exact finalized question text **and**
  matching `presented(topic, presentation_epoch)` metadata;
- prove the narrator row carries **neither** presentation metadata nor the canonical
  assistant question.

**No second persistence path.** The whole point of placing the finalizer where it sits is
that one string is emitted and stored.

#### 3.1a The language boundary — UNRESOLVED, and it blocks acceptance

**A Spanish-locked session currently receives an English question.**

`finalize_presentation` runs at `chat_ws.py:6135`. Every language repair runs before it —
`final_text = _repaired` (5508), `_es_repaired` (5532), `_es_repair_text` (5859). So the
finalizer appends `narrator_question` **after** the text has been repaired into Spanish,
and `narrator_question` exists only in English.

This is a direct consequence of making delivery deterministic: the guarantee that the
narrator receives the server's exact sentence is also a guarantee that they receive it in
the language that sentence was written in.

Two acceptable resolutions, and this work order takes **neither** without Chris:

- **approved Spanish wording** for all ten, added beside `narrator_question`; or
- **Profile Seed explicitly constrained to English**, with the walk refusing to present on
  a non-English session rather than presenting in the wrong language.

**Do not invent translations.** Narrator-facing wording was already escalated once for this
reason and approved with edits on 2026-08-30; machine-translated questions put in front of
an older narrator are the same decision made worse.

#### 3.2 Narrator-room usability — CURRENT ACTION

- Move `#psOnboarding` out of hidden `#lv80AppShims` into visible operator controls, labelled
  **Pause Profile Seed** / **Resume Profile Seed**.
- Compact the 219px topbar while preserving narrator identity and genuine controls.
- **Consolidate only proven duplicates.** Microphone pause, conversational break and Profile
  Seed pause are three different things and must not be merged because they share a word.
- Below the narrow breakpoint expose the Life Map through a visible button or drawer —
  **not `display:none`** — and preserve the selected era across open and close.
- **Leave the clock alone.** Its pushed default is already OFF (`9cc4a42`).
- **Preserve the composer correction** from `490eaee`.

Verify live at ~690px, ~900px and desktop: real keyboard typing; Send and microphone
reachable; no overlays; compact topbar; visible progress and a working Pause/Resume; all
seven Life Map eras reachable; narrator switching clears old progress immediately.

#### 3.3 Live Profile Seed recheck

Use a synthetic narrator with an **unconsumed** topic. Confirm the canonical question is
visibly delivered; persisted text and metadata match; the visible Pause/Resume moves
`version` while `topic` and `presentation_epoch` hold; one answer is accepted without
re-asking; advancement follows the assistant row's commit; and the outstanding state
survives a restart.

**Alex's consumed `childhood_home` is defect evidence and must never be presented as a
successful acceptance run.** It was closed by the phantom presentation `2b7e634` fixes.

#### 3.4 Cohort evidence repair — before any cohort run

The current report records `chars`, not text, and cannot answer whether Lori asked an
era-appropriate question. Running it first would produce exactly the vacuous pass this work
order exists to avoid. It must preserve full narrator input and full Lori response; person,
conversation and turn ids; requested and effective era; browser `currentEra` and
`currentPass`; Profile Seed status, topic, version and `presentation_epoch`; assistant
metadata; extracted facts and Life Map placement before and after; reload and
narrator-switch results; console errors and failed network requests.

**Response length is not evidence of response quality.** Reuse the journaled Alex/Walt run
where possible; create no duplicate narrators because the instrument changed; delete
nothing.

#### 3.5 Multi-era live evaluation

Alex as the shorter control, Walt across all seven eras, reviewed from actual responses.

#### 3.6 Acceptance

Phase 3 may be accepted only when all six conditions in the status block above are met.
Travel Document work begins only after that decision. Repository hygiene remains deferred.

### Phase 4 — consolidated offline gate

Run focused modules separately under `unittest`, then one named consolidated gate. Include
mutation checks proving the tests fail if:

- narrator type is added to activation;
- chronology promotes while onboarding remains active;
- an existing narrator is auto-enrolled;
- an explicit negative is treated as unanswered;
- a stale PATCH succeeds;
- a late narrator-A response changes narrator B;
- any transport trusts browser `current_pass` over the server state.

### Phase 5 — one live acceptance and restart

Use synthetic narrators only. Start the stack once for the run and restart once for
persistence. Do not touch the four family narrators or the designated non-family narrator.

## 7. Acceptance contract

1. **Ordinary intake reaches Profile Seed.** A new narrator created through the real intake
   form has identity complete and chronology ready, yet Lori asks the first remaining Profile
   Seed topic rather than jumping to Pass 2A.
2. **Narrator type changes nothing.** Equivalent new `live` and `reference` fixtures resolve
   the same onboarding state.
3. **Historical narrators are not enrolled.** A pre-migration narrator with a profile gap
   opens exactly as before.
4. **Known facts are skipped.** Intake-supplied education, career, family and other structured
   facts do not get re-asked.
5. **All ten meanings are representable.** Siblings, explicit non-service, no partner, no
   children and actual retirement/working state each resolve truthfully.
6. **The walk is finite.** One topic is active per turn; addressed or declined topics do not
   recur; completing the last remaining topic moves to Pass 2A.
7. **Restart persistence.** After server restart, browser reload and localStorage clear, the
   same next topic remains active and completed topics remain complete.
8. **Two-browser agreement.** A second browser sees the server's progress, not its own default
   `pass1` or chronology cache.
9. **Narrator isolation.** Rapid A→B switching shows no topic, progress or late write from A
   under B.
10. **Transport agreement.** REST chat, REST stream and WebSocket activate the same single
    topic from the same versioned state.
11. **Downstream preservation.** Conversation commitment, extraction, review, chronology,
    Life Map and canonical memoir behavior remain green; no Profile Seed status or question
    text enters memoir export merely because it is onboarding metadata.
12. **Deletion integrity.** Hard delete removes the onboarding row through the declared
    person-scoped inventory/cascade and leaves no new filesystem store.

## 8. Explicitly out of scope

- Resuming Lean Lori L2 or closing Gate B.
- Activating the directive-family registry.
- Changing the model or the locked 8,192-token window.
- Reactivating or modifying parked safety behavior.
- Extending Kawa / Memory River.
- Reworking the Life Map chronology or canonical memoir.
- Auto-enrolling existing narrators because their profiles have gaps.
- Storing narrator answers in the onboarding progress row.

## 9. Stop conditions

Stop and report instead of broadening the lane if implementation would require:

- a narrator-type exception;
- reusing chronology readiness as completion;
- treating missing data as an explicit negative;
- a second source of biographical truth;
- a browser-only completion counter;
- a whole-profile replacement write;
- any model, context-window, safety, registry-activation or Kawa change.

## 10. Closeout record required

At acceptance, update this file and the four current-control documents with:

- implementation and documentation commits;
- exact offline modules/counts;
- the live steps and restart result;
- migration and rollback result;
- synthetic narrator cleanup verified by SQL;
- confirmation that family/designated narrators were untouched;
- Gate B, L2, safety, model/window, registry and Kawa standing state; and
- the next lane, which remains finishing Lean Lori unless Chris changes the queue.
