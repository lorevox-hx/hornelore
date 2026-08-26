# WO-LORI-PROFILE-SEED-REACHABILITY-01

**Make the preserved ten-topic Profile Seed onboarding reachable, durable and finite.**

**Authored:** 2026-08-26 against `main` at `6952ad0`  
**Predecessor:** `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01`, accepted and complete.

**Status:** IN IMPLEMENTATION — Phase 0 accepted 2026-08-26 at `661aa95`. **Phase 1 (server
authority) is COMPLETE, PENDING ACCEPTANCE — built and reviewed once, held for two
corrections, corrected, and awaiting a second review. It is NOT accepted.** Phase 2 has not
begun. *(This line read "READY FOR IMPLEMENTATION" until 2026-08-26, contradicting §6's own
`STATUS: COMPLETE, ACCEPTED` two hundred lines below. A spec whose header disagrees with its
body is worse than one that is merely stale, because the header is the part a reader trusts
without scrolling.)*

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

**Phase 1 — server authority — is next.**

### Phase 1 — server authority

**STATUS: COMPLETE, PENDING ACCEPTANCE (2026-08-26). NOT ACCEPTED.** Built at `f343031`,
held on review for two corrections, corrected, and awaiting a second review. **Phase 2 has
not begun and must not begin until this is accepted.**

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
