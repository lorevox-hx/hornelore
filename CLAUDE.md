# CLAUDE.md — Hornelore agent doctrine

**Read this first at the start of every session.** These are persistent
operational facts and standing rules — not a task log and not a work queue.

**RESTRUCTURED 2026-08-20.** This file had reached 662 KB / ~169,000 tokens,
about 85% of a context window, while instructing every session to read it
first. A control document nobody can afford to read in full stops controlling
anything. Two changes, no content destroyed:

* the changelog moved **verbatim** to [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md)
  — 610 KB of it, 90% of the old file;
* the lane state table was **removed rather than duplicated**. `HANDOFF.md`
  already carried the same state, and this file's own governing order already
  said `HANDOFF.md` wins. Two lists of one truth is how they drift.

**This file now holds only what stays true across lanes.** For what is
happening right now — active lane, what is next, what is owed — read
`HANDOFF.md`.

---

## Where to look for what

| Question | Read |
|---|---|
| What is the current lane? What is next? | **`HANDOFF.md`** — the current-state document |
| What is the ordered work queue? | `MASTER_WORK_ORDER_CHECKLIST.md` |
| Why does this subsystem behave like this? | [`docs/CHANGELOG-AGENT.md`](docs/CHANGELOG-AGENT.md) — the decision INDEX — then the lane's WO in `docs/wo/` |
| What are the standing rules and hazards? | **this file** |
| Who is Lori for, and how is her behaviour produced? | `docs/architecture/` (see below) |

**The governing order:**

```text
current code
> current tests and live evidence
> accepted reports / ADRs / closeout records
> HANDOFF.md
> MASTER_WORK_ORDER_CHECKLIST.md
> old WO status lines
> archived design history
> docs/CHANGELOG-AGENT.md
```

*(**`HANDOFF.md` was MISSING from this list, corrected 2026-08-28** — and the omission was
self-contradictory: the restructuring note at the top of this file says "this file's own
governing order already said `HANDOFF.md` wins", and it did not. Every other control
document ranked the handoff above the checklist while this one skipped it entirely, so the
one file agents are told to read first was the one place its authority was not written
down. Restored in the position the other four documents already used: below accepted
closeout records, above the checklist.)*

Before changing product code in a lane: read recent commits, read that lane's
implementation and tests, check for a later closeout, *then* reconcile the
documents. **Never reimplement landed work from a stale status line.**

**Why that rule is stated so forcefully.** This file has twice carried a stale
current-work list, and both times it was an operational bug rather than a
documentation blemish — a wrong list here is a standing instruction to rebuild
finished work. In 2026-08-09 it named six WOs as "the next build sessions" when
all six had landed a fortnight earlier, and its first item said *build first*
about a feature that had been PARKED. In 2026-08-20 a second stale queue was
found 300 lines below the first, still naming an April extractor sequence as
active. **Both are recorded in [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md). The structural fix is
that current work is no longer tracked in this file at all.**

## Universal pivot framing (2026-06-14)

**Hornelore is the family R&D deployment of Lorevox.** *(This line read
"Hornelore is Lorevox" until 2026-08-17. Same architecture and code lineage,
different operating role — and collapsing the two is how a family-locked
assumption gets written into a generalized product. Hornelore is the crucible;
Lorevox is what is distilled out of it.)* The Horne family is *tenant zero* —
the first real user, whose sessions hardened the system — not a special case in
the architecture. Every WO, prompt and acceptance gate is written against the
universal assumption: **Lori must work for narrators she has never met.**

**Interview default IS `oral_history`** — narrator tells chapters; Lori listens
and follows. Structured styles are operator-selectable overrides of that
default. Questionnaire-first's live path is retired/redirected — see
`WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01` — while five style names stay accepted
for compatibility and testing.

**Read before starting any new work:**

- [`docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`](docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md) — strategy ADR (who Lori is for)
- [`docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`](docs/architecture/LORI-RUNTIME-ARCHITECTURE.md) — nine-stage runtime pipeline (how Lori's behavior is produced)
- [`docs/architecture/MEMORY-EXERCISE-DECISION.md`](docs/architecture/MEMORY-EXERCISE-DECISION.md) — design history for `memory_exercise`. **The style is REMOVED FROM THE PICKER and legacy values redirect to `warm_storytelling`.** The record explains why the concept was not discarded; it is not a statement that the style is selectable today.
- [`docs/architecture/COWORK-HANDOFF.md`](docs/architecture/COWORK-HANDOFF.md) — the operational brief that landed the pivot

Active WO specs live in `docs/wo/`. Pre-pivot WO/BUG specs are
archived at `docs/archive/workorders-pre-pivot/` and are NOT the active source
of truth; pre-pivot handoffs and checklists at
`docs/archive/handoffs-pre-pivot/`.

**Counts are derived, never written down here.** This line said "(114 files)"; Git derives
113, and it had been quoted forward since. A hand-maintained count of a directory is wrong
the moment anything moves, and the archive cohorts still to come will move plenty:

```bash
git ls-tree -r --name-only origin/main -- docs/archive/workorders-pre-pivot | wc -l
```

The manifest of every archived file is [`docs/archive/INDEX.md`](docs/archive/INDEX.md).

## Standing prohibitions

These do not expire with a lane, and none of them may be lifted by an agent.

| Subject | Rule |
|---|---|
| **Model + 8,192-token window** | 🔒 **LOCKED.** A change request here is a stop-and-report condition, not a task. |
| **Runtime safety** | ⏸️ **PARKED**, server-authoritative, code + corpus + tests preserved. **Never reactivate through an environment value** — it takes Chris's explicit decision. [`docs/decisions/2026-08-04-park-safety-feature.md`](docs/decisions/2026-08-04-park-safety-feature.md) |
| **Kawa / Memory River** | **Reachable frozen legacy UI awaiting adjudication.** Non-authoritative. **Do not extend it, do not build on it, and do not describe it as retired in code** — the button, popover, `chronology_river` mode and `js/lori-kawa.js` are still mounted in `ui/hornelore1.0.html`. |
| **Directive-family registry** | **INERT** — built, gated, deliberately not activated. Do not activate it. |
| **Lean Lori L2** | **PARTIAL and closed by product-priority decision. DO NOT RESUME.** Gate B stays OPEN. Substantial work is already in-tree — do not rebuild it. |
| **Per-narrator Google credentials** | **Permanently forbidden, not deferred.** See the Picker identity boundary below. |
| **Profile Seed ten-topic onboarding** | **PRESERVED for new Lorevox narrators regardless of narrator type.** Reachability for an ordinary new narrator is owed; the onboarding itself is not up for removal. |

**Deferred — do not quietly promote to active:** Picker orphan reconciliation;
multi-operator Google auth; generalized import-destination framework;
three-source chooser; safety reactivation; model replacement; context-window
expansion; a broad inference coordinator; framework rewrite; mass migration
cleanup; automatic historical rewrite of stored `[SYSTEM:]` rows.
*Deferred is not forgotten. Deferred means intentionally not active.*

## Mission

Lorevox is a privacy-first conversational memory system that helps older adults preserve life stories, supports cognitive engagement, and provides structured legacy outputs for family. The broader goal is a digital companion for aging populations — supporting memory recall, emotional processing, and intergenerational storytelling.

**This north star is more important than any single WO.** When a decision trades operational tidiness against narrator dignity, narrator dignity wins. The narrator is not an interview subject, not a data source, not a knowledge graph to populate — the narrator is the author of their own story, and the system exists to help them tell it. Operator-side tooling, eval harnesses, and extractor improvements all serve that. None of them outrank it.

**Hornelore** is the working implementation Chris uses with his own family (Kent and Janice Horne, his parents). The patterns shipped here graduate to **Lorevox**, the public product.

## Design principles (locked)

- **No dual metaphors.** Life Map is the only navigation surface. The river metaphor (Kawa, Memory River) was a useful theoretical lens early; it's retired as system, UI, and logic. Kept as a research citation only. **DOCTRINE ONLY — the tree disagrees:** the Memory River button, its popover, the `chronology_river` memoir mode and `js/lori-kawa.js` are all still mounted in `ui/hornelore1.0.html`. See **Standing prohibitions** above; that surface is frozen, not gone.
- **No operator leakage.** Anything a narrator can see or interact with must be designed for narrators. No Return-to-Operator buttons, no diagnostic surfaces, no operator-only controls in the narrator flow. Every UI element passes a role check.
- **No system-tone outputs.** Anything visible to the narrator sounds like a person talking, not a database query result. "(not on record yet)" disappears in narrator-facing output. "Based on: interview projection, session notes" never reaches the narrator. Source-of-truth attribution is operator-side.
- **No partial resets.** Reset Identity clears all narrator-scoped state in one operation, atomically. No lingering memoir cache, no surviving runtime softened-mode, no localStorage remnants. If a reset doesn't reset everything, it isn't done.

- **Provisional truth persists. Final truth waits for the operator. The interview never waits.** Extraction candidates become provisional truth at the moment of extraction — written to BB with `status: "provisional"` and full provenance (source utterance, confidence, timestamp, extractor version). Provisional truth is what Lori reads from in-session AND across sessions; it persists to the server-side narrator record without any approval gate. HITL review is asynchronous and operator-side — a separate review surface (Bug Panel queue, dedicated review dashboard) the operator visits on their own time to promote provisional → confirmed or reject → discard. **Inline review widgets that interrupt the narrator interview are retired.** The reference example of what this principle prevents: TEST-23 v1+v2 (2026-05-04) showed Mary's identity (name + POB) vanishing across browser restart because extraction candidates sat in an in-session shadow-review queue that evaporated on close. Lori knew the values mid-session via chat history; the BB writes never escaped review; the queue cleared on restart; the narrator effectively forgot her own name. That class of failure is exactly what provisional-as-default eliminates.

- **Lorevox is the memory system; Lori is the conversational interface to it.** Memory, structure, chronology, and context belong in the DB schema, the timeline render, and operator-curated context packs — not in Lori's head. Lori's job is to listen, reflect, ask, connect, and follow. Letting Lori carry memory generation, history contextualization, or structural reasoning destabilizes her — that path leads back toward the failure modes Lorevox explicitly avoids: chatbot memoir generator, fake historian, therapist simulator, identity classifier. The system carries the load so Lori can do what she's actually good at. Locked 2026-05-05 alongside the WO-TIMELINE-RENDER-01 + WO-TIMELINE-CONTEXT-EVENTS-01 pair; the architecture follows from this principle (DB/schema = memory + context, Timeline = visual scaffold, Lori = human-feeling conversational layer).

- **Mechanical truth must visibly project.** Any value that exists in canonical or provisional truth (`profile_json`, `projection_json`, promoted/confirmed `story_candidates`, `photos`, `timeline_context_events`) must mirror visibly into the surfaces that consume it — Lori's runtime knowledge via `_build_profile_seed`, the BB UI mirror via projection-sync, the timeline render via the read endpoint, the memoir export via the timeline JSON. Hidden state, inferred reconstruction, and "Lori remembers" pattern-completion are forbidden. The reference example: Mary v6 (2026-05-05) — her identity persisted server-side after Phase A landed but BB state still showed `firstName=None` because the projection→BB mirror was missing. The narrator effectively appeared identity-less in the operator-facing surface even though Lori knew her name fine. Phase E of WO-PROVISIONAL-TRUTH-01 closes that gap; this principle prevents future surfaces from re-introducing it. Pairs with principle 5 (persistence) and principle 6 (ownership) — those cover *what* truth is and *who owns it*; this principle covers *whether the surfaces that need it can see it*.

- **Operator seeds known structure; Lori reflects what is there.** Known narrator facts, family structure, locations, dates, and timeline context belong in BioBuilder/profile truth, projection truth, and operator-curated context packs. Lori must not interrogate the narrator for facts the system already has. **If the operator seeded it, Lori knows it. If Lori knows it, she does not ask for it as intake.** If the fact is not seeded, Lori may learn it naturally when the narrator volunteers it. **Live Lori sessions must not auto-advance questionnaire fields.** Reference example: the questionnaire-first lane was the system's first attempt at structured-field capture; it became Lori interrogating the narrator mid-conversation for fields the operator could enter directly in BB, racing memory_echo + corrections + Life Map era-clicks for turn ownership, and intentionally suppressing the existing welcome-back composer (`hornelore1.0.html:5179` `_ssIsQF` gate) so the QF lane could own first-prompt dispatch on narrator switch — which is what produced Mary's and Marvin's cold-start "Hi, I'm Lori" greetings on switch-back instead of "Welcome back" continuation. WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 retires that behavior on the live narrator path. This principle prevents future surfaces — structured-intake-mode, era-prompt walks, timeline-context capture loops, kinship-skeleton confirmation, anything else that builds a "next field to ask" loop — from re-introducing interrogation under a different name. Pairs with principle 6 (Lorevox is the memory system; Lori is the conversational interface to it) — principle 6 covers *what work Lori does*; this principle covers *what work Lori does NOT do because the system already did it*. Pairs with principle 7 (visible projection) — principle 7 says operator-seeded values must reach Lori's runtime; this principle says once they have, Lori must use them as known, not re-discover them.

These eight principles are checked against every UI element, every data write, and every WO acceptance criterion.

**Canonical extractor architecture reference:** `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`. Consult this when scoping any extractor-lane WO, prompt experiment, or eval. Core Law: *Extraction is semantics-driven, but errors arise from failures in causal attribution at the binding layer.* Five-layer pipeline: Architectural / Control / Binding (primary failure surface) / Decision / Evaluation. Type A/B/C question typology LOCKED.

## Travel Doc Evidence + Web Context Rule (permanent doctrine, 2026-07-10)

Travel Doc mode is the OPERATOR memoir-building workspace — not Narrator
Room / dementia-safe life-story mode. Narrator Room stays cautious (no
surprise machine guesses, no raw-metadata overload, gentle and human).
Travel Doc is EVIDENCE-RICH: use all available evidence (EXIF/filename
dates, GPS + reverse-geocoded broad place, OCR, draft image observations,
captions, operator/approved notes, trip route hierarchy, prior notes,
modal captures, and web/public context) to build the best travelogue,
with provenance wording.

**The rule is not "no web." The local Hornelore LLM/API may use web and
public-context tools in Travel Doc mode** (holidays, local events, museum
and site background, food context, neighborhood context, reverse
geocoding). The boundary is: **do not outsource private narrator memory
archives, life-story profiles, or raw memoir transcripts to an
uncontrolled cloud LLM as the reasoning engine.** Local web-enabled
evidence enrichment is allowed; cloud life-story outsourcing is not.
Web-derived context must be labeled as public context or draft evidence
until confirmed by the operator/narrator, and public context is never
presented as personal memory.

## Google Photos Picker identity boundary (permanent doctrine, 2026-07-27)

Five separate things, and collapsing any two of them is a defect: the **Google
Cloud project / OAuth client** owns app registration, consent screen, redirect
URIs, client id + secret, and API quota; the **authorized Google account** owns
the photo library being picked from (it is normal for these two to be different
accounts); the **Hornelore operator** drives the import; the **Hornelore person
(narrator)** is the destination; the **trip** is an optional destination
sub-scope.

**A Google account is not a Hornelore narrator. An operator is not a narrator
unless a human explicitly selected that narrator as the destination. The
application must never infer `person_id` or `trip_id` from the Google account**
— not from its email, display name, subject id, or anything in the picker
payload. Destination is always explicit in the request: no default, no
fallback, no "if there is only one person, use that one."

`narrator_id` is **not** a third destination field. It is the `photos` table's
column name for the same identity the import lane calls `person_id`; the
repository compares them directly at `import_repository.py:407` and `:1604`,
and that comparison *is* the cross-person guard. Anything that treats
`narrator_id` as separately suppliable is introducing a bug.

Credentials belong to humans who sign in, never to memoir subjects. **Do not
create per-narrator Google credentials** — permanently forbidden, not deferred.
Do not store raw Google tokens in SQLite; do not log, echo, or display token
values (no prefixes, no lengths, no masked tails); health may report credential
presence as **booleans only** and must never return raw or truncated values.

The single-operator `.env` refresh token is correct for the local proof and
authorizes one *source* account only — it says nothing about who the photos are
*for*. The multi-operator future (per-operator encrypted tokens, connect/
disconnect, interactive OAuth) is designed in
`docs/wo/WO-LOREVOX-MULTI-OPERATOR-GOOGLE-AUTH-01_Spec.md` and is **FUTURE
DESIGN ONLY** — no token tables, no encryption machinery, no multi-user auth is
to be built without Chris explicitly opening that work order. Full statement:
`docs/wo/WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md` §10.

## Runtime era is not a story placement (permanent doctrine, 2026-09-01)

**The era a conversation was in is not the era a story belongs to, and deriving one from
the other is a defect.** `story_preservation.preserve` writes every candidate with
`era_candidates=[]` and no placement (`story_preservation.py:225`). **That is deliberate,
not a gap.** Filing a story into a memoir chapter on the strength of whichever screen the
narrator happened to be looking at is exactly the wrong-chapter bug the refusal prevents,
and `story_projection` already states it: *an era candidate nobody confirmed is not a
placement.* The route enforces the same rule from the other side —
*"an operator-set placement needs exactly one era; two eras is not a placement, it is a
pair of guesses"* (`operator_story_review.py:366`).

| | What it is | Where it lives |
|---|---|---|
| **Runtime era** | the era the conversation was in when the narrator spoke | the turn / Life Map selection |
| **Story placement** | the era an **operator confirmed** the story belongs to | `era_candidates` + `placement_source` on the candidate |

**Promotion decides eligibility; placement decides where it goes.** They are independent: a
candidate can be promoted and still reach canonical memoir **unplaced**. Any ledger, report
or projection that collapses them into one destination is wrong.

`placement_source` is a closed set — `db.py:7865`
`("unknown", "narrator_stated", "operator_set", "dob_derived")`. **`operator_set` is not
hand-selectable in the UI**: choosing an era *is* the operator placement, and the era
control writes both fields in one gesture. Offering the source separately once allowed an
operator to build an era with source `unknown`, which the server then reported UNPLACED
while the operator believed they had placed it.

## UI harness hazards — an element that resolves is not a control that works

**Recorded 2026-09-01 after two live probe runs were lost to this class.** These are
durable facts about the shipped UI, not lane state.

- **The Bug Panel is a NATIVE POPOVER.** `<div id="lv10dBugPanel" popover>` opened
  declaratively by `popovertarget`. **There is no `onclick` anywhere to match**, and
  clicking the container itself does nothing at all.
- **Use `#lv10dBugBtn`** — the always-visible header launcher (#205), which exists
  specifically because the operator needs it during a Narrator Session. **Two launchers
  carry `popovertarget="lv10dBugPanel"`;** the other is "Open Full Bug Panel" in the
  operator launcher section, a surface not on screen during a session. **Never require
  uniqueness on the attribute** — that refuses against a correct product.
- **Gate on `:popover-open`,** not on some descendant becoming visible. The popover's open
  state is a fact the platform exposes; inferring it from a side effect can pass on an
  already-open panel.
- **The story-review section is COLLAPSED by default** (`bug-panel-story-review.js:116`),
  and `render()` returns before `renderControls()`. While collapsed the panel exposes **no
  filter input, no row and no promote control.** Expand through the section header —
  the operator's own gesture — never through `_state`.
- **A successful review write CLOSES the row.** `applyReview` sets
  `_state.detail = null; _state.openId = null` and refetches, so no action survives a save
  and the row must be reopened. This is why a stale-version promote is unreachable through
  this UI.
- **Assert visible AND enabled before clicking, and let a miss REFUSE.** Both lost runs
  came from `if (el) el.click()` swallowing a selector that matched nothing, then timing
  out thirty seconds later somewhere unrelated. The same family produced the
  `#lvNarratorCtxMemoir` div. **A guard pinned to a phantom selector confirms the typo
  instead of catching it** — pin every `#id` a harness uses against the shipped UI.
- **A sandboxed agent browser cannot reach the WSL-bound servers** (`chrome-error://`).
  Windows Chrome and Playwright *inside WSL* can. Do not conclude a product defect from an
  agent-side browser failure, and do not route around it.

## Environment

- **OS**: Windows 11 + WSL2 (Ubuntu). Chris works from WSL.
- **Repo path (WSL)**: `/mnt/c/Users/chris/hornelore` — NOT `~/hornelore`.
- **Agent workspace mount**: `/sessions/<session-id>/mnt/hornelore`. Edits here are live on Chris's repo.
- **Agents do NOT run git. Hand Chris copy-paste blocks instead.** *Corrected 2026-08-12 — the reason changed, the rule did not.* This bullet used to read: **"Git is NOT accessible from the sandbox mount.** `git status`, `git add`, `git commit`, `git diff --stat`, `git log` from the sandbox either fault with 'not a git repository' or 'unable to read <oid>'. This is permanent — do not retry." That is no longer true: on the current Cowork mount git **does** work from the sandbox, and a session on 2026-08-12 committed twelve times from it successfully. **The rule stands anyway, for a different and worse reason: the sandbox takes `.git/index.lock` for the duration of every git command, and a command that hits the agent's timeout on the `/mnt/c` 9p mount leaves that lock behind — silently blocking GitHub Desktop and Chris's own WSL git.** The symptom is deliberately confusing and cost real time twice in one day: **`git add` appears to succeed, `git commit` then reports nothing to commit, and Desktop keeps showing N changed files after a "successful" push.** If that happens the fix is `cd /mnt/c/Users/chris/hornelore && rm -f .git/index.lock`. An agent that must inspect state may run READ-ONLY git (`log`, `status`, `rev-parse`, `ls-remote`) and must confirm no `.git/*.lock` survives afterwards; `add`/`commit`/`push`/branch operations belong to Chris.
- **Chris commits from the WSL command line, then pushes from GitHub Desktop.** DO produce copy-paste `git add` + `git commit` blocks that he runs from `/mnt/c/Users/chris/hornelore` — this is the intended workflow. Rules for those blocks: stage with specific file paths only (NEVER `git add -A` or `git add .`), one `git add` + `git commit` pair per logical commit, and use `-m` for the subject plus a second `-m` for the body when the change wants one. Do NOT include `git push` in the block — after committing, Chris checks GitHub Desktop for a clean tree and pushes from there. `git status` / `git diff --stat` / `git log` copy-paste blocks are also fine (read-only inspection). Do NOT suggest SSH key swaps, `gh auth setup-git`, PAT entry, or any other auth dance — his auth is already wired through GitHub Desktop and is none of the agent's business.
- **Work directly on main; do NOT create feature branches.** Chris is the only developer on this repo and the branch/PR workflow is overkill. Going forward, every commit lands on `main` directly via GitHub Desktop. Do NOT suggest creating a new branch, opening a PR, or any branch-rename workflow. (Branches created earlier — e.g. `feat/operator-narrator-intake-form` from 2026-06-15 — can be deleted locally after they're merged. New work commits straight to main.)
- **GPU**: NVIDIA RTX 50-series (Blackwell). Local LLM serves from this machine.
- **THREE interpreters, and they do not carry the same stack. MEASURE, never assume — including from this bullet.** *(Corrected twice. It first claimed both venvs carried the same web stack. It then said, measured 2026-08-20, that "`.venv` is Python 3.10.12 and has NO fastapi at all" — and on **2026-08-28 `.venv` ran a route suite 22/22 with ZERO skips**, which is only possible if fastapi imports. The bullet whose whole purpose is warning that a skip is not a pass had itself gone stale. Any environment claim written here is a measurement with a date, not a standing fact.)*
  - **Check before claiming a verification.** The probe is at the end of this section, unindented and with no multi-line Python payload — see **Interpreter probe** below.
  - `.venv` — the TEST venv. `.venv-gpu` — the SERVING venv, what the running stack uses; model work belongs there. **Measured 2026-08-28 in WSL: both ran the strict-version route suite 22/22, zero skips.** Bare `python3` did not — it reported 5 route skips.
  - **THE TRAP, and it is silent.** A suite whose route tests need fastapi does not FAIL on an interpreter without it — it **skips**, and unittest still prints `OK`. During the deletion lane this produced `OK (skipped=12)`, where the twelve were every route-level test in the file. **`OK` with skips is not a pass.** Always read the skip count and report it: *"38 + 51 (12 skipped) + 6"* is honest; *"95 green"* is not.
  - **Reports must name the interpreter a result came from.** A result without one cannot be reproduced or trusted.
  - **The mutation gate's documented command is `python3`**, which is the interpreter least able to exercise route tests — its baselines show `22 ran, 5 SKIPPED` for the strict suite and `48 ran, 6 SKIPPED` for the REST route suite, while the `S`-series mutations target `api.py` and `profile_seed_rest.py`. Whether the gate should run under `.venv` instead is registered in [`docs/BACKLOG.md`](docs/BACKLOG.md) §6 and is not yet decided.
  - Other missing-dependency symptoms are confusing rather than obvious and are not product defects: a missing `PIL` surfaces as `ModuleNotFoundError` at collection, and a missing `python-docx` surfaces as every memoir-export assertion getting `503 != 200`, because the route's own `_DOCX_AVAILABLE` guard (`server/code/api/routers/memoir_export.py`) fires first. `requirements-test.txt` (2026-07-27) is the companion to `requirements-gpu.txt`; if a suite fails on an import or a blanket 503, compare against it first.

### Interpreter probe

**Unindented on purpose, and with no multi-line Python payload.**

*(The first version of this probe lived inside the bullet list above, so its fenced block
carried four leading spaces. Copying the block copies that indent, and the Python payload
was multi-line — so it died on `IndentationError: unexpected indent` at line 2, every
time. A verification command that cannot be pasted is not a verification command. Every
payload below is a single line, which cannot be broken by indentation at all.)*

```bash
cd /mnt/c/Users/chris/hornelore
for p in python3 .venv/bin/python .venv-gpu/bin/python; do
  printf '%-24s ' "$p"
  "$p" -c 'import sys; print(sys.version.split()[0], end=" ")' 2>/dev/null || { echo "(not runnable)"; continue; }
  for m in fastapi pydantic; do
    if "$p" -c "import $m" 2>/dev/null; then printf '%s ' "$m"; else printf '%s=ABSENT ' "$m"; fi
  done
  echo
done
```

**Run it in WSL, not from an agent sandbox.** A sandboxed container can execute
`.venv/bin/python` and still resolve none of its `site-packages`, so it reports every
module ABSENT for both venvs — which is an artifact of the container boundary, not a fact
about the laptop. The authoritative reading of these venvs is the one taken in WSL.

## Stack ownership

- **Chris starts and stops the API and full stack himself.** Do NOT include `./scripts/start_all.sh` or `./scripts/stop_all.sh` in copy-paste blocks.
- The API is assumed to be running at `http://localhost:8000` whenever an eval is asked for.
- **Cold boot takes ~4 minutes** — the HTTP listener comes up in ~60–70s but the LLM weights + extractor warmup continue for another 2–3 minutes after that. A `curl /` health check is NOT sufficient; it only proves the socket is listening, not that the extractor can serve a real request in <30s. This is why Chris owns start/stop: the agent-run combined blocks that restart the stack and immediately kick off evals cold-start the first case into a 90s read-timeout (observed on cg_001 during narrative-field r5c, 2026-04-21).
- If Chris ever explicitly asks for a combined restart+eval block, gate the eval behind an extractor-warmup probe (POST a trivial extract and loop until round-trip is <30s), not a bare `curl /` loop.

## Sandbox hazard: stale `__pycache__` on `/mnt/c` (recorded 2026-08-04)

**A test run from the agent sandbox can execute code that is not the code on disk.** The `__pycache__` directories under `server/` are **not deletable from the sandbox** — `rm` returns `Operation not permitted` — and they hold `.pyc` for both `cpython-310` and `cpython-312`. Python's mtime-based invalidation is unreliable across the 9p `/mnt/c` mount, so an edited module can keep loading its previous bytecode.

The symptom is bewildering rather than obvious, and it burned real time before it was named: `_extraction_bounded_enabled()` returned `True` when called directly, immediately before *and* after the call, while the same function inside the same module evaluated `False` — because the caller was the new source and the callee was a stale `.pyc`.

**Always run sandbox tests with the bytecode cache redirected out of the repository:**

```bash
PYTHONPYCACHEPREFIX=/tmp/pyc python3 -m unittest tests.<module>
```

`-B` is NOT sufficient — it stops Python *writing* bytecode, not reading a stale `.pyc`. This is the same family as the existing rule about not inferring process state from mtime or size on a `/mnt/c` path. **A green sandbox run without the prefix is not evidence.** `.venv` on the laptop remains the verification.

## TTS-aware testing rule (locked 2026-08-04)

**Speech is a feature, not a transport for every other feature's evidence.** Testing Lori's text behaviour by listening to Lori say it is slow, it burns Chris's attention on repeat playback of things already proven, and it silently corrupts every latency number by folding synthesis and playback into what gets reported as model time.

- **Most automated and browser checks validate Lori's TEXT response** and must not wait through spoken playback when speech is not the feature under test.
- **TTS gets ONE dedicated acceptance case per milestone.** It does not replay every test response.
- **The final combined acceptance tests real TTS with playback enabled** — once, at the end, as the representative spoken turn.
- **Never send the next browser message while Lori is still speaking.** Browser instructions must say so in those words: *"Wait until Lori finishes speaking before continuing."*
- **Test timeouts must include the generated audio's playback duration.** A timeout sized for text will fail a working spoken turn.
- **Performance reports must separate five numbers and never merge them:** LLM response time · TTS time-to-first-audio · TTS synthesis time · audio playback duration · complete narrator-visible turn time.
- **TTS playback must never be reported as LLM latency.** This is the rule the other four exist to protect: a 9.9-second utterance attributed to the model makes the model look broken and hides the real cost.
- **CPU Kokoro must be warmed before it is timed**, and its cold-start figure is reported separately. Measured 2026-08-04: cold 27.558 s for 39 characters (RTF 10.30) against warm 1.752 s for 9.875 s of audio (RTF 0.177). Reporting those as one number describes neither.
- **Chris is not asked to listen to the same acceptance twice.**

This strengthens the no-testing-loop rule rather than replacing it: **text-only verification for behaviour, then one representative spoken turn once the milestone is implemented.**

## Git hygiene gate

**Before any code-changing work starts, the tree must be clean** (`git status` shows nothing uncommitted). "Code-changing work" = edits to `server/`, `scripts/`, `ui/`, or any file the extractor / eval harness reads at runtime. Docs-only sessions are exempt but should still commit before EOD.

If the tree is dirty when new code work is requested, the agent's **first action** is to flag it and produce a copy-paste commit plan — NOT to start the code work. No "I'll commit after" — uncommitted state compounds silently across sessions because the sandbox can't run git, and a dirty tree destroys the bisect surface that every eval-gated patch depends on (today's 13-item pile-up — overnight WO batch + r5e1 reports + Phase 1 instrumentation all tangled — is the codifying example, 2026-04-22).

Agent action when tree is dirty:

1. Ask Chris to paste `git status && git diff --stat` from `/mnt/c/Users/chris/hornelore`.
2. Group changes into logical commits with **code isolated from docs** (so a regressing code change reverts cleanly without undoing doc work, and vice versa).
3. Produce copy-paste commit blocks using specific file paths (never `git add -A` or `git add .`).
4. Wait for Chris to confirm clean state before starting the next code change.

Exception: throwaway probe outputs under `.runtime/` that regenerate on every run. If in doubt, commit.

## Every copy-paste block starts with the `cd` (locked 2026-08-12)

**Any command block handed to Chris — tests, evals, git, probes, one-liners — must open with:**

```bash
cd /mnt/c/Users/chris/hornelore
```

No exceptions, even for a single-line command, and even when the previous block already `cd`-ed there. Chris runs these from a fresh `wsl` prompt that lands in `/mnt/c/Users/chris`, so a block without the `cd` fails with `No such file or directory` and he has to go and look the path up. Blocks are copied whole and out of order; each one has to stand alone.

## Standard test command (copy-paste ready)

Per-module, never whole-tree discovery (cross-suite state contamination is documented in `HANDOFF.md` §7). `.venv` is the test venv and a green agent-sandbox run is evidence only — **but read the skip count before calling anything verified**, because `.venv` has no fastapi and route tests skip there silently while unittest still prints `OK`. See the venv bullet under **Environment**.

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest tests.<module>
```

Several modules in one run, when they are related:

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest \
  tests.<module_a> tests.<module_b>
```

For sandbox-side runs only, redirect the bytecode cache out of the repository (`-B` is NOT sufficient — it stops Python writing bytecode, not reading a stale `.pyc` across the `/mnt/c` mount):

```bash
PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONPATH=server/code python3 -m unittest tests.<module>
```

## Standard eval command (copy-paste ready)

When asked to run or re-run a master eval, emit exactly this block, rotating the output suffix:

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/archive/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_<SUFFIX>.json
grep "\[extract\]\[turnscope\]" .runtime/logs/api.log | tail -40
```

(Eval runner moved from `./scripts/` to `./scripts/archive/` on 2026-04-25 to keep the start/stop folder clean. See `scripts/archive/README.md`.)

The eval script auto-writes `docs/reports/master_loop01_<SUFFIX>.console.txt` next to the JSON — no shell `| tee` needed (was silently producing 0-byte files under WSL pipe-buffer conditions; r4h's empty console triggered the fix on 2026-04-19).

Suffix convention: latest **locked baseline is `r5h`** (2026-04-22, 70/104, v3=41/62, v2=35/62, mnw=2 known). Earlier ladder: `r4h` TURNSCOPE v2 (#72 closed) → `r4i` #67 date-field (R4 floor 55/104) → `r4j` PROMPTSHRINK (measured, not adopted; flag in-tree for SPANTAG Pass 2) → `r5a–r5e1` NARRATIVE-FIELD (r5e1 floor 59/104) → `r5e2` ATTRIBUTION-BOUNDARY (REJECTED, in-tree behind `HORNELORE_ATTRIB_BOUNDARY=1`) → `r5f` SILENT-OUTPUT Phase 1+2 (69/104) → `r5g` #119 turnscope greatGrandparents (null, closed complete-with-caveat) → `r5h` WO-SCHEMA-ANCESTOR-EXPAND-01 Lane 1 trial annotations (current). Next: `r5i` = full Lane 1 (case_033 + case_039) or next extractor-lane patch.

The grep at the end rotates — change the tag to whatever filter is being tested (`turnscope`, `negation-guard`, `R4-E`, etc.) or drop it when not needed.

## Stubborn-pack diagnostic eval (copy-paste ready)

When the master eval moves but we need to know why stubborn cases (the frozen fail set) did or didn't shift, run this alongside. The master above stays the decision gate; this layer is diagnostic only.

```bash
cd /mnt/c/Users/chris/hornelore
HORNELORE_PROMPTSHRINK=1 ./scripts/archive/run_stubborn_pack_eval.py \
  --tag <SUFFIX> \
  --runs 3 \
  --api http://localhost:8000 \
  --master docs/reports/master_loop01_<SUFFIX>.json
```

Writes `docs/reports/stubborn_pack_<SUFFIX>_run{1,2,3}.json` plus a cross-run `stubborn_pack_<SUFFIX>_stability.json` + `.console.txt`. The stability console includes the master topline (when `--master` supplied) and buckets the 15 stubborn cases into stable_pass / stable_fail / unstable with per-case VRAM-GUARD truncation flag, failure-category change count, and field-path shape-change flag across the 3 runs.

Stubborn pack (15 cases, fixed): `case_008, case_009, case_017, case_018, case_053, case_075, case_080, case_081, case_082, case_083, case_084, case_085, case_086, case_087, case_088`.

Drop the `HORNELORE_PROMPTSHRINK=1` prefix when running the legacy prompt path — the wrapper itself is env-flag-agnostic.

## Standard post-eval audit block

After every eval that follows a code change, report this exact block before declaring any movement real:

- total pass count
- v2 contract subset
- v3 contract subset
- must_not_write violations
- named affected cases (newly passed, newly failed)
- pass↔fail flips
- scorer-drift audit on every flip (eyeball the truth zones — does the score change reflect a real extraction change, or a scorer/expectation drift?)

## Where files live

**`docs/reports/` is GITIGNORED as of 2026-08-12 — reports are LOCAL-ONLY while the
repository is public.** Commit `a87e865` untracked all 767 report files because they
carry live narrator data (transcripts, family names, runtime captures) and the public
repo was serving them to the open internet. Agents keep WRITING reports to
`docs/reports/` exactly as before — every path in the table below stays correct — but
**do not `git add` anything under `docs/reports/`, and do not "fix" the .gitignore rule
when a report refuses to stage; the refusal is the feature.** The same applies to the
other paths untracked in that commit (`wo12b_evidence/`, `wo13_phase*_proof/`,
`transfer/hornelore_data.zip`, the three real-person `ui/templates/*-horne.json`).
Re-publishing reports requires the redaction plan in
`docs/wo/WO-PRIVACY-CANON-EXTRACTION-01_Spec.md`, not a .gitignore edit.

| Kind | Path |
|---|---|
| API log | `/mnt/c/Users/chris/hornelore/.runtime/logs/api.log` |
| Eval JSON reports | `/mnt/c/Users/chris/hornelore/docs/reports/master_loop01_*.json` |
| Eval console readouts | `/mnt/c/Users/chris/hornelore/docs/reports/master_loop01_*.console.txt` |
| Stubborn-pack reports | `/mnt/c/Users/chris/hornelore/docs/reports/stubborn_pack_*.json` (+ `_stability.console.txt`) |
| Eval case source | `/mnt/c/Users/chris/hornelore/data/qa/question_bank_extraction_cases.json` |
| Extract router | `/mnt/c/Users/chris/hornelore/server/code/api/routers/extract.py` |
| WO specs | **Active: `docs/wo/<NAME>_Spec.md`** — the only location for current work. Legacy `WO-*_Spec.md` / `BUG-*_Spec.md` still sit at the repo root awaiting the hygiene lane's archive cohort; their unresolved obligations are registered in [`docs/BACKLOG.md`](docs/BACKLOG.md) §2. Pre-pivot: `docs/archive/workorders-pre-pivot/`, history only. **Counts are derived — see the block below this table.** *(This row once named the repo root as* the *location, contradicting the `docs/wo/` convention stated at the top of this file. A half-true row is the worst kind to leave, because it reads as confirmation.)* |
| WO reports | `/mnt/c/Users/chris/hornelore/docs/reports/WO-*_REPORT.md` |
| Canonical architecture spec | `/mnt/c/Users/chris/hornelore/docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` |
| SECTION-EFFECT Phase 1 output | `/mnt/c/Users/chris/hornelore/docs/reports/WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` (pending) |
| SECTION-EFFECT Phase 3 output | `/mnt/c/Users/chris/hornelore/docs/reports/WO-EX-SECTION-EFFECT-01_CAUSAL.md` (pending) |

All of these are readable from the agent workspace mount via the session prefix. After an eval runs, read the console + JSON directly — do not ask Chris to paste them.

### Derived counts

**Outside the table on purpose.** A markdown table cell must escape `|` as `\|`, and a
command copied out of one carries the backslashes — `git ls-tree … \| grep …` passes `\|`
to `git` as an argument, which prints usage text and no count at all. Commands live in
fenced blocks; tables point at them.

```bash
cd /mnt/c/Users/chris/hornelore
git ls-tree -r --name-only origin/main | grep -cE '^(WO-|BUG-)[^/]*\.md$'   # root WO/BUG specs
git ls-tree -r --name-only origin/main -- docs/archive/workorders-pre-pivot | wc -l
git ls-tree -r --name-only origin/main -- docs/wo | wc -l
```

**Current result of the first: `30`** (2026-08-28) — 29 from the audit baseline plus
`BUG-HARNESS-TEST23-INDENTATION-01_Spec.md`, filed at `157af46` and open. Do not write a
count into prose; run the command.

## Extractor lane — reference, not a queue

*(**RETIRED AS A WORK QUEUE 2026-08-20.** This section was headed "Current
phase" and carried a numbered "Active sequence (reordered 2026-04-23)" naming
SPANTAG, SCHEMA-ANCESTOR-EXPAND and VALUE-ALT-CREDIT as the next items, plus a
locked baseline dated 2026-05-03. It was roughly four months stale and it
contradicted the real lane — the second time this file has carried a stale
current-work list. The numbers and the sequence are preserved in
[`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md), where they are dated history rather than an
instruction. **The commands below are still correct and still useful; the
priorities are not this file's to state.** For the current lane, read
`HANDOFF.md`.)*

**Last locked master baseline** was `r5h-followup-guard-v1` (78/114, v3=49/72,
v2=43/72, mnw=2), 2026-05-03. **Treat that as a historical reference point, not
as today's number** — confirm against the newest report in `docs/reports/`
before quoting it anywhere.

**Canonical extractor architecture reference:**
`docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`. Consult this when scoping any
extractor-lane WO, prompt experiment or eval. Core Law: *Extraction is
semantics-driven, but errors arise from failures in causal attribution at the
binding layer.* Five-layer pipeline: Architectural / Control / **Binding
(primary failure surface)** / Decision / Evaluation. Type A/B/C question
typology LOCKED.

## Chris's working preferences

- Honest critique over flattery. Push back on ideas when warranted.
- Tight readouts, not walls of text.
- Do NOT relitigate things already decided.
- When three agents (Claude/Gemini/ChatGPT) converge on the same answer, act on it; don't re-argue.
- Do not regenerate command blocks from memory — copy from this file.
- Read logs and reports directly from the workspace mount; don't ask Chris to paste.

## Companion stack (Lori — the point of the whole system)

The extraction pipeline is one output surface; **Lori is the companion** — designed around older-adult narrators with possible cognitive decline. When planning UI, interview flow, or LORI-CONFIRM work, remember the narrator may not be able to correct, clarify, or re-engage on a standard cadence.

**WO-10C Cognitive Support Mode (landed, dementia-safe):** six behavioral guarantees — protected silence, invitational re-entry, no correction, single-thread context, visual-as-patience, invitational prompts. Silence timing stretched 30s/55–75s → 120s/300s/600s. Re-entry bypasses confidence gates. **Known gap: no operator UI toggle yet — flag must be set programmatically.** Report: `Hornelore-WO10C-Cognitive-Support-Report.docx`.

**Facial awareness stack (browser-only, zero video transmission):** MediaPipe FaceMesh (468 landmarks) → geometry rules → affect labels (steady / engaged / reflective / moved / distressed / overwhelmed). Never ships video, raw landmarks, or raw emotion vectors — only derived `affect_state` + confidence + duration. `facial-consent.js` persists consent in `localStorage['lorevox_facial_consent_granted']`. `emotion.js` L348 has a load-bearing SIMD→non-SIMD WASM redirect (SIMD build crashes at `loadGraph` on Chris's stack). `cognitive-auto.js` v7.4C policy: visual can *accelerate* but not *cause* a mode transition; text has veto.

**Camera / mic / TTS state-machine interactions:** activation chain is `toggleEmotionAware()` → `FacialConsent.request()` → `LoreVoxEmotion.init()` → `LoreVoxEmotion.start()` → `cameraActive=true` + `state.inputState.cameraActive=true` + `window.lv74.showCameraPreview()`. Two truth sources for `cameraActive` (global at `state.js:407` and mirror at `state.js:283`) can desync on narrator switch. Perm-card path flips `emotionAware=true` only — it does NOT call `startEmotionEngine`. `camera-preview.js` reuses the emotion-engine's hidden video `srcObject`; if absent, falls back to a second `getUserMedia` (can double-prompt or fail silently). WO-MIC-UI-02A's 4-state visual (LISTENING / OFF / WAIT amber / BLOCKED) × WO-10H turn-claim state machine × WO-10C stretched silence can interact badly when TTS on 8001 errors mid-stream (mic stuck amber).

**Post-generation response guards are UNCONDITIONAL — do not assume they behave like the
parked safety feature.** `server/code/api/services/lori_response_guards.py` contains **no
environment gate at all**: it exposes 7 `detect_` / 7 `repair_` pairs, and every detector
has a repair partner. Its own design rule is *"LAW 3: pure deterministic. No LLM. No DB.
No IO."* New guards belong in that pair pattern. Stub collapse is the existing exception:
both its detection and `compose_stub_collapse_repair()` live in
`lori_communication_control.py`, under the enclosing communication-control gate, rather
than in the unconditional response-guard family.

**A detector that only detects is not a guardrail.** For this project reserve *guardrail*
for something that prevents or repairs narrator-facing behaviour before the person sees it;
a test, a prompt instruction and a Bug Panel warning are none of them.

**Diag panel first.** For any camera/mic/TTS bug, open the in-app diag at `app.js:5730–5819` (`lv10dSyncHeaderControls`) — it already emits warnings for "Camera active but preview DOM not created", "emotionAware=true but facial consent declined", "Turn state stuck in awaiting_tts_end", plus live `lv10dBpFacialConsent` / `lv10dBpConsentStored` / `lv10dBpCamPreview` / `lv10dBpTts` / `lv10dBpSignalAge` readouts. Check these first; the fault surface collapses to one branch.

**Parallel/supporting subsystems:**

- **Kawa — DOCTRINE retired 2026-05-01; the SURFACE is reachable frozen legacy UI awaiting adjudication.** *(This bullet read `Kawa (RETIRED 2026-05-01)` until 2026-08-20, which reads as settled and is not: the button, popover, `chronology_river` mode and `js/lori-kawa.js` are still mounted. Retiring a metaphor in doctrine is not the same as removing a surface from the tree, and collapsing the two is how a reader skips a decision nobody made.)* The river metaphor was a useful theoretical lens early on; gave the project vocabulary for client-as-theorist framing and "river of memories" visualization. The implementation has converged on the canonical 7-era life spine + Life Map UI, and a second river metaphor confused both the model and the user (the broken "narrator-room Memory River view tab" in the 2026-04-30 audit was the trigger). Decision: **Life Map is the only navigation surface; Memory River is removed as a UI.** Kawa is kept as a research citation only — the four papers in `Research/Kawa/` (OTI2023-2768898, TST.2024.9010104, The_Dynamic_Use_of_the_Kawa_Model_A_Scop, newbury-lape-2021-well-being-aging-in-place) support the academic framing of "narrator-as-theorist of their own life" for write-ups. No Kawa engine, no Kawa rendering, no River-of-Memories pre-generation.

- **Pheno (PARKED)** — lived experience + wisdom extraction, separate from truth fields. DESIGN COMPLETE spec, not wired. Doesn't conflict with anything currently shipping. Reactivate when extractor lane settles.

- **WO-STT-LIVE-02 fragile-fact transcript guard** is landed (7-pattern classifier + 30s staleness cap + typed-input fallback).
