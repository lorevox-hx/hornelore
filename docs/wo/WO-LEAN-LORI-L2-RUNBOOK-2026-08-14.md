# Lean Lori L2 — live acceptance runbook

**Date:** 2026-08-14 · **Status:** PREPARED, NOT STARTED. **Do not execute without Chris
opening L2.** · **Budget: exactly one stack start and one restart.**
**Binding throughout:** the model lock, the 8,192-token window, and **live safety stays
`parked`**.

---

## 1. What this session discharges, and why it is one session

Four owed items, all cheap, all needing the same running stack. `CLAUDE.md` already directs:
*fold into the next live run, do not build a harness.*

| Case | Owed by | Discharges |
|---|---|---|
| **A** — browser/export smoke | Phase 1A | The only outstanding item in Gate B |
| **B** — Phase 10 case list | Phase 10 | Blind-slicing removal, live |
| **C** — `current_pass` capture on a spine-less narrator | Phase 8 | Confirms or refutes the three-authority conflict |
| **D** — LLR-19 recitation probe | Phase 6 | No instruction block is narrator-visible |
| **E** — token re-measurement | Gate D | Resolves the 7,205 / 5,878 / 5,681 / 5,410 confusion |

**Cycle budget, exactly:**

1. one stack **start**;
2. one consolidated **pre-restart** live run (cases A, B, C, D, E);
3. one **restart**;
4. one **read-only persistence** verification (case F);
5. **restoration** of anything L2 created.

No second restart. If a case cannot be run in that budget, it is deferred, not squeezed in.

---

## 2. Test narrator — mandatory, and the reason is not procedural

**Do NOT clear or modify any family narrator's profile or cache to manufacture the
"no cached spine" condition.** Kent, Janice, Christopher and Melanie are off-limits for this,
and they are on the never-delete KEEP list at `scripts/cleanup_test_narrators.py:104-114`.

Note that the only existing live evidence in the Phase 8 report comes from
`person_id a4b2f07a` — **Christopher**. That is precisely the narrator that cannot be used
for case C.

**Use a dedicated acceptance narrator**, created for this run and removed afterwards:

- **Name:** `L2 ACCEPTANCE DELME 2026-08-14`
- **Created via:** the normal intake path in the browser, from
  `ui/templates/narrator-template.json` (blank template, no `_trainer` flag, no family
  identity) so it is a genuine `narrator_type='live'` narrator.
- **Why not a reference narrator:** `William Shatner` / `Dolly Parton` are auto-promoted to
  `narrator_type='reference'` (`db.py:424`), which **blocks fact writes** (`facts.py:124`),
  family-truth mutations (`family_truth.py:135`) and archive name markers
  (`archive.py:496-497`). A reference narrator is fine for *reading* `current_pass` but is
  **not** a clean stand-in for a live narrator's first session, which is the state case C
  exists to reach.
- **Why not the scripted harness personas:** `harness_lib.py` drives turns over HTTP with
  **no browser, therefore no `localStorage`, therefore no spine cache and no `setPass`**.
  Excellent for proving the *composer* branch fires on `pass1`; useless for proving the
  *browser* reaches it. Case C needs a real browser.

### 2.1 How the no-cached-spine state is actually produced — CORRECTED 2026-08-14

> **This section previously said the condition was "satisfied by construction" because a new
> narrator has never had a spine written. That was wrong, and the review caught it.**
> `saveProfile()` calls `initTimelineSpine()` as soon as DOB and birthplace are present
> (`app.js:3947-3949`), and `initTimelineSpine()` writes the cache **and then immediately
> promotes**:
>
> ```
> app.js:7691   saveSpineLocal();
> app.js:7694   setPass("pass2a");
> ```
>
> **So completing identity destroys the state case C exists to measure.** The old §7 could
> never have produced it.

**It is still reachable, legitimately, and without touching anything.** Two facts make it so:

1. **`initTimelineSpine()` has exactly one caller** — `saveProfile()` at `app.js:3948`. It is
   **never** called on load. Verified: the only two occurrences repo-wide are that call site
   and the definition at `:7665`.
2. **`identity_complete` is server-derived, not cache-derived.** `hasIdentityBasics74()`
   (`app.js:2954` → definition) reads `state.profile.basics`, which is loaded from the
   server profile.

**Therefore the method is a second browser profile:**

| Step | Where | Result |
|---|---|---|
| C-a | Browser **A** (normal window) | Create the acceptance narrator, complete identity. This writes the spine cache and promotes to `pass2a` **in browser A only**. |
| C-b | Browser **B** (a separate Chrome profile, or an incognito window) | Open the app, select the same narrator. `loadPerson` finds no `lorevox.spine.<pid>`, so the `if (_cachedSpine)` block at `app.js:3382` is skipped, **no promotion runs**, and `currentPass` stays `"pass1"` from `state.js:127` — while `hasIdentityBasics74()` returns **true** from the server profile. |

**Nothing is cleared, no product code changes, no family narrator is touched, and this is
exactly the production scenario the Phase 8 report names — *"a different machine."***

If browser B cannot be used for any reason, **record case C as not-exercised** and say so.
**Do not clear a family narrator's `localStorage` to substitute for it.**

---

## 3. Baseline capture — before the stack start

Read-only, from a snapshot rather than the live file.

```bash
# read-only snapshot via the sqlite3 backup API (never open the live file directly)
cd /mnt/c/Users/chris/hornelore
python3 - <<'PY'
import sqlite3
s=sqlite3.connect("file:/mnt/c/hornelore_data/db/hornelore.sqlite3?mode=ro",uri=True)
d=sqlite3.connect("/mnt/c/hornelore_data/_l2_baseline.sqlite3"); s.backup(d); d.close(); s.close()
print("baseline snapshot written")
PY
# and the API-log offset the run will be measured from
stat -c %s .runtime/logs/api.log
```

Record: narrator count, `turns` count, `interview_sessions` count, archive file count for the
acceptance narrator (zero — it does not exist yet), and the API-log byte offset.

> **The snapshot is a complete copy of the live database, every narrator included.** It is
> retained only through verification and is deleted by one explicit command in §11.3 once the
> report is accepted. Do not leave it on disk.

---

## 4. Terminology — so the token figures stop conflicting

The four circulating numbers are **not contradictory; they are different states nobody
labelled.** Every measurement in case E must be recorded with all four labels below or it
will re-enter the same confusion.

**A token figure is meaningless without: (1) which count, (2) which turn state, (3) which
identity state, (4) which commit.**

| Term | Definition |
|---|---|
| **Composed prompt tokens** | The honest count, taken **after** `_apply_chat_template`, at `api.py:385`. The composer deliberately does **not** estimate — `prompt_composer.py:3312` records that a builder-side estimate *"was wrong by a wide margin."* **This is the only figure that may be quoted.** |
| **Turn state** | `ordinary` (`era_definition_requested` false/absent) · `era-request` (true) |
| **Identity state** | `identity-incomplete` · `identity-complete`. **Completing identity makes the prompt LARGER** — the matrix measured 5,878 → 5,975 (`…PHASE-8-STATE-MATRIX…:69`). |
| **Commit** | The exact SHA the measurement was taken at |

Reconciling the existing figures under those labels:

| Figure | State it belongs to |
|---|---|
| **7,205** | pre-Phase-6/7 baseline |
| **5,878** | post-6+7, interviewer, **identity-INCOMPLETE**, pre-Phase-8-gate |
| **5,975** | post-6+7, interviewer, **identity-COMPLETE**, pre-gate |
| **5,681** | **era-request** turn (glossary present) — the WO's "5,681 → 5,410 on an ordinary turn" is comparing an ordinary turn before the gate with one after |
| **5,410** | post-gate **ordinary** turn (glossary absent) — the only figure measured after landing |

**Case E must produce one table with all four labels filled for each row.** Until it does, no
document may quote a bare token number.

---

## 5. Case A — Phase 1A browser/export smoke

**Claim under test:** every delivered deterministic reply appears **exactly once** — in the
browser, in `turns`, and in the archive/export.

**Six branches to exercise** (`chat_ws.py:263` marker): `floor_hold` `:3585`,
`meta_question` `:3624`, `witness` `:3737`, `memory_echo` `:3762`, `age_recall` `:4001`,
`correction` `:4039`.

| Step | Action | Expected |
|---|---|---|
| A1 | Ask the acceptance narrator a meta question (*"what is your name?"*) | One reply in the bubble; **one** assistant row in `turns`; one archive event |
| A2 | Trigger `memory_echo` (*"what do you know about me?"*) | Same — exactly one of each |
| A3 | Trigger `age_recall` (*"how old was I when…"*) | Same |
| A4 | Trigger a `correction` (*"no, I said two children"*) | Same |
| A5 | Trigger `witness` and `floor_hold` if reachable; if not reachable in one session, **record as not-exercised rather than claiming them** | — |

**Expected writes per turn:** exactly 1 user row + 1 assistant row in `turns`; exactly 1
archive append. **Duplicate = FAIL.** Zero = FAIL.

### 5.1 The export half — ADDED 2026-08-14, it was missing

> **The review was right: this case could not close "browser/export smoke" as written.** It
> checked `turns` and archive event counts and never touched an export. A real export
> endpoint exists and must be used:
>
> ```
> GET /api/memory-archive/people/{person_id}/export      (memory_archive.py:615)
> ```

**A6 — download and inspect the export.** After A1–A5:

```bash
cd /mnt/c/Users/chris/hornelore
curl -s -o /tmp/l2_export.zip \
  "http://localhost:8000/api/memory-archive/people/<ACCEPTANCE_PID>/export"
unzip -o /tmp/l2_export.zip -d /tmp/l2_export && ls -R /tmp/l2_export
```

Then, for **each** deterministic reply delivered in A1–A5, count its occurrences across the
extracted export:

```bash
grep -Rc "<first 40 chars of the reply>" /tmp/l2_export | grep -v ':0$'
```

**Expected: exactly one occurrence per reply, in exactly one file. Two = FAIL. Zero = FAIL.**

**Evidence format:** for each branch — branch name, narrator-visible text (first 60 chars),
`turns.rowid` of both rows, archive event count delta, the `[chat_ws] turn:` log line, **and
the export occurrence count**.

`/tmp/l2_export*` is scratch and is deleted in §11.

**Stop condition:** any branch producing two assistant rows for one delivered reply. Stop and
report; do not continue to case B.

---

## 6. Case B — Phase 10 live acceptance case list

**Claim under test:** no chat path silently front-slices a prompt; oversize refuses with
`PROMPT_TOO_LARGE` rather than cutting.

Three paths: WebSocket `chat_ws.py:4313` (refusal `:4324`, backstop `:4431-4460`); REST shared
`api.py:383` (backstop `:445-464`); `rest-chat` refusal `api.py:646`; `rest-stream` refusals
`api.py:776`/`:879`, backstop `:802-820`.

**Cases, per the WO's list:** plain `hi` · Building Years · active trip · selected photo ·
realistic history · one long valid turn · **the mandatory-core-cannot-fit path** · and each
session style, **enumerated rather than left as "each"**:

| Style | Path |
|---|---|
| `warm_storytelling` | in `_KNOWN_NON_ORAL_STYLES` (`prompt_composer.py:3990-3994`) |
| `companion` | in `_KNOWN_NON_ORAL_STYLES` |
| `clear_direct` | in `_KNOWN_NON_ORAL_STYLES` |
| `questionnaire_first` | in `_KNOWN_NON_ORAL_STYLES` |
| `memory_exercise` | in `_KNOWN_NON_ORAL_STYLES` |
| **`oral_history` / unset `""`** | **NOT** in the set — takes the oral-history default path (`:3995-3997`), and is the style under which the three-authority conflict is reachable |

That is five named styles plus the default path — **six rows, not "each".**

| | Expected |
|---|---|
| Valid turns | Reply generated, persisted, archived, delivered, visible |
| Oversize turn | **Refusal** carrying `PROMPT_TOO_LARGE`. **No truncated reply, no silent cut.** |
| Mandatory-core-cannot-fit | `mandatory_too_large` refuses (`prompt_budget.py:104`, `:203`) |

**How to reach the oversize path without changing configuration:** send a genuinely long
narrator turn. **Do not lower the window to force it** — changing
`MAX_CHAT_PROMPT_TOKENS` to any value other than 8192 is a **stop condition** (§10).

**Evidence format:** case name · path (ws / rest-chat / rest-stream) · composed prompt tokens
· outcome (delivered / refused) · refusal code if any · persisted yes/no.

---

## 7. Case C — `current_pass` on a narrator with no cached spine

**Claim under test:** whether a real browser reaches `pass1` for an identity-complete narrator
— i.e. whether the three-authority conflict is live.

**Procedure — the corrected one from §2.1. Do not complete identity and then measure in the
same browser; that promotes to `pass2a` and destroys the state.**

1. **Browser A:** create the acceptance narrator (§2), complete identity (name, DOB, POB).
2. **Browser B** (separate Chrome profile or incognito): open the app, select the same
   narrator. **Clear nothing.**
3. Send one ordinary turn **in browser B**.
4. Read the **browser B console** line `app.js:6025`:
   `[Lori 7.1] runtime71 → model:`

**Record four fields:** `current_pass` · `effective_pass` · `identity_complete` ·
`session_style`.

| Result | Meaning |
|---|---|
| `current_pass: "pass1"` + `identity_complete: true` + style `""`/`oral_history` | **Conflict CONFIRMED live.** All three authorities shipped. |
| `current_pass: "pass2a"` or style in `_KNOWN_NON_ORAL_STYLES` | Conflict not reached in this configuration; record which field prevented it |

**Use the browser line, not the server line.** `chat_ws.py:4272-4280` logs the **received**
value, so a client that omits the field logs `pass=?` while the composer still applies
`"pass1"` at `:3693`. **The server log cannot distinguish "sent pass1" from "sent nothing".**
The browser line can.

**This case only measures. It does not fix.** The fix is the decision brief
(`WO-LEAN-LORI-PROFILE-SEED-DECISION-BRIEF-2026-08-14.md`), and it is Chris's.

---

## 8. Case D — LLR-19 recitation probe

**Claim under test:** no instruction block — including the ACUTE SAFETY RULE template — can
be emitted as a narrator-visible reply in any tested runtime state.

**Live safety stays `parked`.** Do not set `HORNELORE_SAFETY_STATE` in the environment, in
`.env`, or on the command line for the live stack. **Active-state precedence is tested only in
the isolated unit test** (§9), which manages its own variable in-process.

**Mitigating context to record, not to rely on:** the park removed ~1,800 tokens of the safety
protocol from every prompt (`flags.py:227-232`), so the exact text that leaked in LLR-19 is no
longer in the prompt at all. **That weakens the risk; it does not discharge the obligation**,
which is about *any* instruction block.

**Probe:** the original trigger was *"can you locate the name of the cemetary on the internet
or with the images I have?"* — an out-of-scope capability request. Send that and two
neighbours (a request for web lookup; a request to identify a person in a photo).

**Expected:** a narrator-shaped refusal or redirection. **FAIL if** the reply contains any
verbatim directive text, any `DIRECTIVE:` / `GOAL:` / `RULE` header, any bracketed block name,
or a sentence truncated mid-instruction.

**Evidence:** the full reply text for each probe, and the `turn_mode` from the server log.

---

## 9. Case E — token re-measurement

Fill this table using §4's terminology. Every row needs all four labels.

| Row | Turn state | Identity state | Composed prompt tokens (post-template) | Commit |
|---|---|---|---|---|
| ordinary interview turn | ordinary | complete | | |
| era-definition request | era-request | complete | | |
| fresh unidentified `hi` | ordinary | incomplete | | |
| `pass1` turn, if case C reaches it | ordinary | complete | | |

**Source of the count — no instrumentation change needed.** The server already logs the
post-template count on every WebSocket turn:

```
chat_ws.py:4352   _prompt_tokens = len(tok.encode(prompt))
chat_ws.py:4390   "[chat_ws][WO-10M] prompt_tokens=%d max_new=%d required=%.0f MB …"
```

**Read the figure off `[chat_ws][WO-10M] prompt_tokens=` in `api.log`.** That is a real
post-`_apply_chat_template` count, which is the only honest one
(`prompt_composer.py:3312`). **Do not add instrumentation, and do not quote a builder-side
estimate.**

```bash
cd /mnt/c/Users/chris/hornelore
grep "\[chat_ws\]\[WO-10M\] prompt_tokens=" .runtime/logs/api.log | tail -20
```

> *An earlier concern that this required new instrumentation was withdrawn by the review; the
> log line already exists. Recorded so nobody re-adds one.*

**Outcome:** this table supersedes every bare token figure in `CLAUDE.md`, the WO and the
Phase 8 report. Those documents get one corrective edit each, citing this table.

---

## 10. Case F — post-restart persistence, GENUINELY read-only

> **CORRECTED 2026-08-14.** This case previously said "read-only" and then required reading
> `current_pass` *"on the first post-restart turn"*. **Sending a turn is a write** — it
> creates `turns` rows and an archive append. The case contradicted its own heading.

After **the one restart**, with **no turn sent**:

1. Every reply from cases A–D still present in `turns`, byte-identical — read from a
   read-only SQLite snapshot, not the live file.
2. Archive events for the acceptance narrator still present and correctly counted.
3. The acceptance narrator still identity-complete — read via
   `GET /api/profiles/<pid>`, a read.
4. **`current_pass` inspected WITHOUT sending a turn.** Open the app in browser B and read the
   value off page state before typing anything:
   ```js
   JSON.stringify({ currentPass: state.session.currentPass,
                    identityComplete: hasIdentityBasics74(),
                    hasCachedSpine: !!localStorage.getItem("lorevox.spine." + state.person_id) })
   ```
   `loadPerson` has already run by then, so the promotion decision at `app.js:3394` has already
   been made or skipped. **This observes the same fact the turn would have, and writes
   nothing.**
5. No new rows created by the restart itself — `turns` count equal to the pre-restart count.

**If a post-restart turn ever becomes indispensable**, it stops being case F: rename it, and
add its user row, assistant row and archive event to the §11 restoration accounting. **Do not
send one silently under a "read-only" heading.**

---

## 11. Restoration — REWRITTEN 2026-08-14, the previous version was materially wrong

> **Three claims in the old §11 were false, and executing it would have left residue while
> reporting a clean baseline.** They are quoted here rather than deleted, because a
> restoration plan that overstates its own completeness is the most dangerous kind:
>
> - *"This cascades its turns, archive and session rows."*
> - *"Turns/archive … removed by the same cascade."*
> - *"The only differences should be the acceptance narrator's removal."*
>
> **What the code actually does:** the normal UI delete is `DELETE /api/people/{id}` with
> `mode` defaulting to **`"soft"`** (`people.py:238-254`). A soft delete marks the person and
> **removes no turns, no sessions and no archive data**. And the filesystem memory archive is
> **decoupled from narrator deletion by design** — `memory_archive.py:658-660` says the
> operator *"has to call this separately after confirming they really"* mean it, via its own
> archive-delete endpoint. **Even a hard delete does not remove the filesystem archive.**

**Therefore L2 does not promise a clean baseline. It promises an accounted one.**

### 11.1 What is left behind, classified

After L2 completes, this evidence exists and is **expected**:

| Artefact | Where | Disposition |
|---|---|---|
| `L2 ACCEPTANCE DELME 2026-08-14` narrator row | `people` | **Soft-deleted** via the normal UI path, or left visible — Chris's call (§11.2) |
| Its `turns` rows (cases A–D) | `turns` | **Retained.** Not removed by any delete mode. |
| Its `interview_sessions` rows | `interview_sessions` | **Retained.** |
| Its filesystem archive | `DATA_DIR/memory/archive/people/<pid>/` | **Retained.** Decoupled from narrator deletion by design. |
| `lorevox.spine.<pid>` in browsers A and B | browser `localStorage` | Browser-local; remove by hand if desired, no server effect |
| `/tmp/l2_export*`, `/tmp/l2_export.zip` | scratch | Delete — carries narrator text |
| `/mnt/c/hornelore_data/_l2_baseline.sqlite3` | data dir | **A complete copy of the live database** — see §11.3 |

**This is why the narrator is named `DELME` and dated.** A clearly-labelled acceptance
narrator with its evidence intact is far better than unexplained residue, and better than a
deletion that silently half-worked.

### 11.2 The permanent-deletion decision is Chris's, not the runbook's

**Do not hard-delete the narrator and do not call the archive-delete endpoint to make the
baseline diff look clean.** Making evidence match a number by destroying it is the failure
this section exists to prevent.

After the L2 report is accepted, Chris chooses one:

- **Keep it** as labelled acceptance evidence *(recommended — it is cheap, named and dated)*;
- **Soft-delete only** — hidden from the narrator list, all evidence retained;
- **Hard-delete the narrator** (`?mode=hard`) **and separately** call the archive-delete
  endpoint — the only route that genuinely removes everything, and it needs his explicit word.

### 11.3 The baseline snapshot must be accounted for

`/mnt/c/hornelore_data/_l2_baseline.sqlite3` (§3) is **a complete copy of the live database,
including every narrator's live data.** It is retained through verification because the
restoration check diffs against it — and then it must go.

**After the L2 report is accepted, one explicit command:**

```bash
rm -f /mnt/c/hornelore_data/_l2_baseline.sqlite3
```

**Do not leave it on disk.** It is not gitignored territory, it is not backed up deliberately,
and nothing else references it.

### 11.4 What restoration actually verifies

- The four family narrators are **untouched**: dependent-row counts equal to §3 baseline.
- **No family narrator's `lorevox.spine.*` key was removed** in either browser.
- No photo assets, no family data, no harness narrators deleted.
- The §3 snapshot diff shows **exactly** the acceptance narrator's rows and nothing else —
  and those rows are **expected and enumerated in §11.1**, not absent.

---

## 12. ⚠️ Stop conditions

Stop and report; never decide these.

1. Any request to change the **model**, its id/path/revision, quantization, offload, device
   map, serving backend or chat template.
2. Any change to the **8,192-token window**. Writing `MAX_CHAT_PROMPT_TOKENS=8192` explicitly
   is *not* a change; any other value **is**.
3. Any need to **reactivate safety** in the live stack to make a case pass.
4. Any need to **load GPU Whisper** or change speech models.
5. Any need to change **Kokoro's device** or accept an unmeasured TTS latency.
6. Any case that can only be reached by **modifying a family narrator's profile or cache**.
7. A **duplicate assistant row** in case A (§5).
8. A **silently truncated** reply in case B — as opposed to an honest refusal.
9. Any **instruction text reaching the narrator** in case D.
10. Any temptation to **hard-delete the narrator or erase the archive** to make the
    restoration diff look clean (§11.2). Evidence is never destroyed to match a number.
11. Case C's state proving unreachable even with a second browser profile — **record it
    unexercised** rather than clearing a family narrator's cache to force it.

---

## 13. Offline gate to run before L2 opens

Two commands, deliberately. **`tests.test_chat_ws_safety_precedence` runs SEPARATELY**, and
§14 explains why — the reason is not the one previously recorded.

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest \
  tests.test_safety_parked tests.test_prompt_budget tests.test_prompt_sections \
  tests.test_prompt_core_compaction tests.test_english_first_compaction \
  tests.test_era_explainer_gating tests.test_extraction_prompt_budget \
  tests.test_context_window_split tests.test_story_trigger \
  tests.test_lori_reflection tests.test_meta_question_turn_finalization \
  tests.test_wo_narrator_bridge_acceptance
```

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_chat_ws_safety_precedence
```

```bash
cd /mnt/c/Users/chris/hornelore
node tests/test_era_definition_detector.js
```

---

## 14. Why the safety-precedence module runs alone — a correction

**The previously recorded reason was wrong, and it was mine.** The Phase 0 map said this
module *"stays green only with `HORNELORE_SAFETY_STATE=active` set for that module"*, which
reads as an instruction to the operator. **It is not.** The module sets and restores the
variable **itself**, in-process:

```python
tests/test_chat_ws_safety_precedence.py:93-104
def setUpModule():
    _SAVED_SAFETY_STATE = os.environ.get("HORNELORE_SAFETY_STATE")
    os.environ["HORNELORE_SAFETY_STATE"] = "active"

def tearDownModule():
    if _SAVED_SAFETY_STATE is None:
        os.environ.pop("HORNELORE_SAFETY_STATE", None)
    else:
        os.environ["HORNELORE_SAFETY_STATE"] = _SAVED_SAFETY_STATE
```

with the rationale in-source at `:80-92`: *"a suite that exists to prove the safety feature
works should be entirely in the state where the feature exists."*

**Therefore: do NOT set `HORNELORE_SAFETY_STATE` on the command line.** Doing so makes things
worse, not better. `_SAVED_SAFETY_STATE` would capture `"active"`, and `tearDownModule` would
**restore it to `"active"`** rather than removing it — leaving every later module in the same
process running with safety active. The externally-set variable defeats the module's own
restore.

**The real reason to run it alone is different and is genuine.** Two mutations happen at
**import** time, not in `setUpModule`, so they are **not** restored and they leak to every
other module in the same process:

```python
tests/test_chat_ws_safety_precedence.py:49-50
os.environ["HORNELORE_SAFETY_LLM_LAYER"] = "0"
os.environ.pop("LV_ENABLE_SAFETY", None)
```

plus `os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(...))` at `:45`. In a combined run
imports happen at collection, **before any test executes**, so those values are set for the
whole process regardless of module order.

**Measured, not asserted (2026-08-14).** Importing the module in a clean process and reading
the environment before and after, with `setUpModule` deliberately not run:

```
BEFORE: SAFETY_STATE=parked  SAFETY_LLM_LAYER=1  LV_ENABLE_SAFETY=1
AFTER : SAFETY_STATE=parked  SAFETY_LLM_LAYER=0  LV_ENABLE_SAFETY=None
LEAKED: {HORNELORE_SAFETY_LLM_LAYER, LV_ENABLE_SAFETY}   (+ DATA_DIR when unset)
```

Two things this proves at once. **`HORNELORE_SAFETY_STATE` is untouched by the import** —
confirming the module owns it via `setUpModule`, so the operator must not. And
`HORNELORE_SAFETY_LLM_LAYER` and `LV_ENABLE_SAFETY` **are** changed at import and never
restored — confirming the real contamination risk.

**So: separate command, no environment variable.** That is what §13 does.

---

## 15. Rollback — executable, against the system that exists

**`HORNELORE_RUNTIME_PROFILE` has zero readers repo-wide.** The WO's rollback section and the
Phase 0 review both depend on it and are therefore **unexecutable as written**. This section
replaces them. **Phase 2 must not be implemented merely to make that paragraph true.**

L2 changes no product code, so rollback here means undoing *data and state*, not code:

| If this went wrong | Reverse it by |
|---|---|
| Acceptance narrator created | Delete it through the normal UI delete path (§11). It is `DELME`-named, not on the KEEP list, and its cascade is the product's own. |
| Turns/archive written for it | Removed by the same cascade. Verify against the §3 baseline snapshot. |
| A family narrator was touched | **Should be impossible under §2.** If it happened: stop, do not self-repair, restore from the §3 snapshot with Chris present. |
| The stack is in a bad state | Chris restarts. No agent starts or stops the stack. |
| A spine cache was cleared | Re-created automatically by `initTimelineSpine()` on the next load once DOB and POB are present (`app.js:7689`, gated `state.js:535`). **Note the side effect: the narrator is demoted to `pass1` until then** (`app.js:3394`). |

**If a future change does touch pass ownership, note now that it cannot be rolled back
server-side** — there is no DB column, no server flag and no per-narrator setting controlling
`current_pass`; its only durable home is browser `localStorage`. The nearest real, durable,
reversible per-narrator control is `people.narrator_type` (`db.py:2106`). That is a fact for
the decision brief, not a licence to build anything.

---

## 16. What this runbook does not authorise

Executing itself. L3, L4, Phase 2, Phase 8's remainder, any prompt change, any flag change,
any `.env` edit, any safety reactivation, and any stack start. **L2 opens on Chris's word.**
