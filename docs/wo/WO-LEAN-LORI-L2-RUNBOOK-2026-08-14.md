# Lean Lori L2 — live acceptance runbook

> ## ERRATA — 2026-08-17
>
> **THIS RUNBOOK HAS BEEN EXECUTED AND L2 IS CLOSED. DO NOT RUN IT AGAIN.**
>
> The status line below read *"PREPARED, NOT STARTED"* until 2026-08-17. That was accurate
> when it was written and became false on 2026-08-16, when L2 ran and closed **PARTIAL by
> product-priority decision (Chris)**. It is quoted rather than deleted, per the
> correct-in-place rule, because a runbook that describes itself as unstarted is an
> instruction to start it.
>
> **Gate B stays OPEN. Phase 10 stays open.** The unexercised cases — Case C, the remaining
> Case A branches, the five styles, the trip/photo fixtures, the refusal matrix, Case E rows
> 2 and 4, and the final restart with Case F — are **DEFERRED BY DECISION, not failures.**
>
> The budget was also not met: the run consumed one start, a clean shutdown, an authorized
> resume start and a final restart. That deviation is recorded in the evidence report, not
> smoothed over here.
>
> **Evidence of record:** `docs/reports/WO-LEAN-LORI-L2-PARTIAL-2026-08-16.md` — local-only
> and gitignored (live narrator data), written as a path rather than a link because a link
> would be broken for anyone cloning.
>
> **Known correction this run earned, carried forward and NOT yet fixed:** §5.1 A6c's export
> verifier matches replies to turns *by text*, so two legitimate identical deterministic
> replies read as a duplicate archive write. The verifier's contract is wrong; the product
> behaviour was correct.
>
> **The active lane is `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01`**, which takes up the three
> integration defects L2 surfaced.

**Date:** 2026-08-14 · **Status:** ~~PREPARED, NOT STARTED~~ **EXECUTED 2026-08-16 — CLOSED
PARTIAL. Do not re-run.** · **Budget as written: exactly one stack start and one restart
(not met — see the errata above).**
**Binding throughout:** the model lock, the 8,192-token window, and **live safety stays
`parked`**.

---

## 1. What this session discharges, and why it is one session

**Five cases**, all needing the same running stack. `CLAUDE.md` already directs: *fold into
the next live run, do not build a harness.* *(This sentence said "four owed items" while
listing five rows — corrected 2026-08-14.)*

| Case | Owed by | Discharges |
|---|---|---|
| **A** — browser/export smoke | Phase 1A | The only outstanding item in Gate B |
| **B** — Phase 10 case list | Phase 10 | Blind-slicing removal, live |
| **C** — `current_pass` capture on a spine-less narrator | Phase 8 | Confirms or refutes the three-authority conflict |
| **D** — LLR-19 recitation probe | Phase 6 | No instruction block is narrator-visible |
| **E** — token re-measurement | Gate D | Resolves the 7,205 / 5,878 / 5,681 / 5,410 confusion |

**Cycle budget, exactly:** one stack **start** · one consolidated pre-restart run · one
**restart** · one read-only verification · restoration. No second restart.

### 1.1 Chronological execution plan — ONE ordered timeline

> **ADDED 2026-08-14.** The cases were previously written as independent sections whose
> required states **conflict**: `fresh unidentified hi` needs identity **incomplete**, while
> cases C and E need it **complete**. Run in section order and the first is unreachable.
> This is the order; the section numbers are reference material, not a sequence.

| # | Step | Required state | Notes |
|---|---|---|---|
| 1 | §3 baseline snapshot + API-log offset | stack down | fails closed if the file exists |
| 2 | **Chris starts the stack**, ~4 min warm | — | agents never start it |
| 3 | §5.1 **A6a archive preflight** | — | decides whether the export half runs at all |
| 4 | Create acceptance narrator, **do not complete identity** | — | browser A |
| 5 | **Case B — `fresh unidentified hi`** | identity **INCOMPLETE** | **must happen here**; later it is unreachable |
| 6 | **Case E row 3** — token count for the unidentified turn | identity INCOMPLETE | read `[chat_ws][WO-10M]` |
| 7 | Complete identity (name, DOB, POB) | — | this writes the spine cache and promotes to `pass2a` **in browser A** |
| 8 | **Case A** A1–A5 deterministic branches | identity complete | browser A |
| 9 | **Case D** LLR-19 probes | identity complete | browser A |
| 10 | **Case B** remaining rows: 5 styles, fallback, long turn, oversize, mandatory-core | identity complete | plus §6.1 fixtures **if Option 1** |
| 11 | **Case E** rows 1–2 | identity complete | ordinary + era-request |
| 12 | **Case C** — browser **B**, fresh profile | identity complete, **no cache** | see §2.1 and §7 |
| 13 | **Case A6b/A6c** export download + structural verify | — | only if step 3 said enabled |
| 14 | **Chris restarts the stack** | — | the one restart |
| 15 | §10 post-restart snapshot, then **Case F**, read-only | — | no turn sent |
| 16 | §11 restoration accounting + report | — | deletion decisions deferred to Chris |

If a case cannot be run inside this budget it is **deferred and recorded unexercised**, never
squeezed in.

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

**Fails closed if a snapshot already exists** — an interrupted earlier run's evidence must
never be silently overwritten.

```bash
# read-only snapshot via the sqlite3 backup API (never open the live file directly)
cd /mnt/c/Users/chris/hornelore
python3 - <<'PY'
import sqlite3, os, sys
OUT="/mnt/c/hornelore_data/_l2_baseline.sqlite3"
if os.path.exists(OUT):
    sys.exit(f"REFUSED: {OUT} already exists — evidence from an earlier run. "
             "Inspect it, then remove it deliberately before re-running.")
s=sqlite3.connect("file:/mnt/c/hornelore_data/db/hornelore.sqlite3?mode=ro",uri=True)
d=sqlite3.connect(OUT); s.backup(d); d.close(); s.close()
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

**A6a — PREFLIGHT, before anything else in this case.** The export endpoint is gated:
`_require_enabled()` returns **404** when `HORNELORE_ARCHIVE_ENABLED` is off, and its
**documented default is off** (`memory_archive.py:19-20`, `:68-69`).

> **CORRECTED 2026-08-14. Checking the HTTP status is not the test.** `/health` is
> **flag-agnostic** — it returns `200` with `{"ok": true, "enabled": flags.archive_enabled()}`
> whether the feature is on or off. A `200` therefore proves nothing. **Parse the JSON
> `enabled` field.**

> **CORRECTED AGAIN 2026-08-14 — the preflight must ENFORCE, not narrate.** The previous
> version printed `enabled: True`/`False` and **exited 0 either way**, so an operator who
> glanced past the line would continue into a verification that cannot work. A preflight that
> cannot stop you is not a preflight. **Fail closed.**

```bash
cd /mnt/c/Users/chris/hornelore
.venv/bin/python - <<'PY'
import sys, json
try:
    import requests
    r = requests.get("http://localhost:8000/api/memory-archive/health", timeout=5)
    r.raise_for_status()
    d = r.json()
except Exception as e:                       # unreachable, non-2xx, or not JSON
    sys.exit(f"PREFLIGHT FAILED (unreachable/invalid): {e!r}")
if not isinstance(d, dict) or "enabled" not in d:
    sys.exit(f"PREFLIGHT FAILED (malformed payload): {d!r}")
if d["enabled"] is True:
    print("archive ENABLED — continue to A6b"); raise SystemExit(0)
if d["enabled"] is False:
    print("archive DISABLED — export stays UNEXERCISED; change no flag"); raise SystemExit(3)
sys.exit(f"PREFLIGHT FAILED (enabled is not a bool): {d['enabled']!r}")
PY
echo "preflight exit: $?"
```

| Exit | Meaning | Action |
|---|---|---|
| **0** | `enabled is True` | Continue to A6b |
| **3** | `enabled is False` | **Record the export portion UNEXERCISED.** Do **not** edit `.env`, do **not** restart with a different flag, and **do not claim Gate B fully closed** (§16.1). |
| **1 / other** | unreachable, non-2xx, non-JSON, malformed, or `enabled` not a boolean | **Stop.** Do not guess and do not proceed to A6b. |

`enabled` is compared with `is True` / `is False` deliberately: a string `"false"` or a `0`
must fail loudly rather than being coerced into an answer.

> If Chris wants the export exercised, **that environment decision must be made before the
> single authorised start** — it is not something L2 may change mid-run.

**A6b — download, with HTTP and archive validation.**

```bash
curl -fS -o /tmp/l2_export.zip \
  "http://localhost:8000/api/memory-archive/people/<ACCEPTANCE_PID>/export" \
  || { echo "EXPORT DOWNLOAD FAILED — do not proceed"; exit 1; }
unzip -t /tmp/l2_export.zip >/dev/null || { echo "ZIP INVALID"; exit 1; }
unzip -o /tmp/l2_export.zip -d /tmp/l2_export && find /tmp/l2_export -type f
```

**A6c — verify structurally, not by grepping the whole ZIP.**

> **CORRECTED 2026-08-14.** The previous instruction counted occurrences across the extracted
> ZIP and expected exactly one. **That test could not pass on a correct export.** The archive
> writer appends each event to `transcript.jsonl` **and rebuilds `transcript.txt` from that
> JSONL**, so a healthy export contains the same reply in **two representations**. A naive
> count would have reported every correct export as a duplicate-write failure. `grep -Rc`
> also counts matching *lines* rather than occurrences, treats the reply as a **regex**, and
> collides when two replies share an opening phrase.

The contract is:

1. Parse `transcript.jsonl` and match the **full assistant response string, exactly** — not a
   40-character prefix, not a regex.
2. **Exactly one structured assistant event** per delivered reply. Two = FAIL. Zero = FAIL.
3. **Separately**, confirm `transcript.txt` renders that response once. This is a derived
   human-readable view, **not a second archive write**, and must not be counted as one.

> **CORRECTED 2026-08-14 (second pass).** The first version used
> `next(root.rglob("transcript.jsonl"))`, which inspects **only the first exported session**.
> An export contains one transcript pair *per session*, and the acceptance run spans several
> — so a duplicate landing in session 2 would have gone unseen, and a reply recorded in a
> later session would have read as missing. **Aggregate across every exported session.**

```bash
python3 - <<'PY'
import json, pathlib
root = pathlib.Path("/tmp/l2_export")
jls = sorted(root.rglob("transcript.jsonl"))
txts = sorted(root.rglob("transcript.txt"))
print(f"sessions found: {len(jls)} jsonl, {len(txts)} txt")
assert jls, "no transcript.jsonl in the export — stop, do not interpret"

events = []
for p in jls:
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line); e["_session"] = p.parent.name; events.append(e)
rendered = "\n".join(p.read_text(encoding="utf-8") for p in txts)

REPLIES = [ "<paste the full assistant reply from case A1>",
            "<A2>", "<A3>", "<A4>" ]          # exact strings, not prefixes

fails = 0

# The two representations must come from the same set of sessions. A JSONL
# without its rendered pair (or vice versa) means a partial export, and every
# per-reply count below would be measured against an incomplete corpus.
jl_dirs  = {p.parent for p in jls}
txt_dirs = {p.parent for p in txts}
if jl_dirs != txt_dirs:
    fails += 1
    print(f"FAIL  session transcript sets disagree: "
          f"jsonl-only={sorted(d.name for d in jl_dirs - txt_dirs)} "
          f"txt-only={sorted(d.name for d in txt_dirs - jl_dirs)}")

for r in REPLIES:
    hits = [e for e in events
            if e.get("role") in ("assistant", "ai")
            and (e.get("text") or e.get("content")) == r]
    n_struct = len(hits)
    n_render = rendered.count(r)
    # EXACTLY one of each. `>= 1` was wrong: the stated contract is that the
    # rendered transcript shows the reply once, and a second rendering is a
    # duplicate worth failing on, not noise worth tolerating.
    ok = (n_struct == 1 and n_render == 1)
    fails += (not ok)
    where = ",".join(sorted({h["_session"] for h in hits})) or "-"
    print(f"{'PASS' if ok else 'FAIL'}  structured={n_struct} rendered={n_render} "
          f"session(s)={where}  {r[:44]!r}")

print(f"\n{'ALL PASS' if not fails else str(fails)+' FAILED'} "
      f"(across {len(jls)} session transcript(s))")
# EXIT NONZERO ON FAILURE. Without this the verifier printed FAILED and the
# shell still reported success, so a broken export read as a clean one.
raise SystemExit(1 if fails else 0)
PY
echo "export verifier exit: $?"
```

**Exit 0 means every reply appeared exactly once structurally and exactly once rendered,
across every exported session, with the two transcript sets agreeing. Any other exit is a
failure and stops case A.**

**Expected: `structured=1` for every reply.** `rendered` is reported for completeness and is
**not** a duplicate-write signal.

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

> **CORRECTED 2026-08-14.** The previous table listed `memory_exercise` as a live style and
> called the default a sixth. Both were wrong. `memory_exercise` is **retired** — it is
> absent from `LV_VALID_SESSION_STYLES` (`app.js:217-220`) and is **rejected** by the setter
> at `:235`. Its surviving `_KNOWN_NON_ORAL_STYLES` entry in the composer is **legacy
> tolerance for old stored values, not a selectable style.** Do not reactivate it.

**The five currently accepted styles** — `LV_VALID_SESSION_STYLES`, `app.js:217-220`:

| # | Style | Composer path |
|---|---|---|
| 1 | `oral_history` | **NOT** in `_KNOWN_NON_ORAL_STYLES` → oral-history posture (`prompt_composer.py:3995`). The default (`app.js:225`, `:292`) and the style under which the three-authority conflict is reachable. |
| 2 | `warm_storytelling` | in `_KNOWN_NON_ORAL_STYLES` (`:3990-3994`) |
| 3 | `companion` | in `_KNOWN_NON_ORAL_STYLES` |
| 4 | `questionnaire_first` | in `_KNOWN_NON_ORAL_STYLES` |
| 5 | `clear_direct` | in `_KNOWN_NON_ORAL_STYLES` |

**Five styles.** Separately, one **fallback case** — an unset or invalid stored value, which
`app.js:292` resolves to `oral_history`. That is a fallback behaviour to exercise, **not a
sixth style**.

| | Expected |
|---|---|
| Valid turns | Reply generated, persisted, archived, delivered, visible |
| Oversize turn | **Refusal** carrying `PROMPT_TOO_LARGE`. **No truncated reply, no silent cut.** |
| Mandatory-core-cannot-fit | `mandatory_too_large` refuses (`prompt_budget.py:104`, `:203`) |

**How to reach the oversize path without changing configuration:** send a genuinely long
narrator turn. **Do not lower the window to force it** — changing
`MAX_CHAT_PROMPT_TOKENS` to any value other than 8192 is a **stop condition** (§12).

### 6.1 Active-trip and selected-photo — fixtures, or unexercised

> **CORRECTED 2026-08-14.** These two cases had no fixture. The acceptance narrator has no
> trip and no photo, and family narrators are off-limits, so **as written they could not
> execute at all.**

Chris chooses **one** before the run, and the choice is recorded in the report:

**Option 1 — labelled fixtures, fully accounted.** Create, on the acceptance narrator only:

| Artefact | Table / location |
|---|---|
| `L2 ACCEPTANCE TRIP DELME` | `trips` |
| its generated day cards | `trip_days` |
| one uploaded photograph | `photos` + the file under `DATA_DIR` |
| one trip membership | `trip_photo_links` |
| one day placement, if the case needs it | `trip_photo_day_placements` |

**Every one of these is added to §11.1's accounting.** The photograph must be a throwaway
image, **not** a family photograph.

**Option 2 — record both cases UNEXERCISED.** Phase 10 stays **partially open**, and §16.1
says so explicitly. This is the cheaper and entirely honest choice.

**Never make these cases pass by using a family narrator's trip or photographs.**

### 6.2 Refusal writes — measure six surfaces, do not assume zero

> **CORRECTED 2026-08-14.** The old evidence format recorded "persisted yes/no", which
> assumes a refusal writes nothing. **It does not.** On the WebSocket path the narrator's
> archive append runs **before** the prompt-budget refusal, and the final user/assistant
> turn-pair persistence runs **after** it. So an oversize turn can leave a narrator archive
> event behind while writing no `turns` rows at all.

**Record all six per case, per transport:**

| # | Surface |
|---|---|
| 1 | user **archive** event written? |
| 2 | user **`turns`** row written? |
| 3 | assistant **archive** event written? |
| 4 | assistant **`turns`** row written? |
| 5 | **model invoked?** (a refusal before generation must not invoke it) |
| 6 | returned **status / error code** (`PROMPT_TOO_LARGE`, `mandatory_too_large`, …) |

**Evidence format:** case name · transport (ws / rest-chat / rest-stream) · composed prompt
tokens from `[chat_ws][WO-10M]` · outcome · the six surfaces above.

**Any archive event written for a refused turn is accounted for in §11.1** — it is real
residue, not nothing.

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

**First, take the post-restart snapshot.** §3's baseline predates the run and cannot show the
acceptance narrator's rows, so a second snapshot is required. It also fails closed.

```bash
python3 - <<'PY'
import sqlite3, os, sys
OUT="/mnt/c/hornelore_data/_l2_post_restart.sqlite3"
if os.path.exists(OUT):
    sys.exit(f"REFUSED: {OUT} already exists — inspect and remove deliberately.")
s=sqlite3.connect("file:/mnt/c/hornelore_data/db/hornelore.sqlite3?mode=ro",uri=True)
d=sqlite3.connect(OUT); s.backup(d); d.close(); s.close()
print("post-restart snapshot written")
PY
```

**Both files are complete copies of the family database.** Both are accounted for and removed
in §11.3, and only after the report is accepted.

Then, with **no turn sent**:

1. Every reply from cases A–D still present in `turns`, byte-identical — read from the
   **post-restart** snapshot, compared against what the pre-restart run recorded.
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

> **EXPANDED 2026-08-14.** The previous list named four surfaces. An acceptance run touches
> many more — the correction trigger in case A and ordinary narrative turns activate
> downstream writers (extraction, story preservation, follow-up bank, projections).

| Artefact | Where | Disposition |
|---|---|---|
| `L2 ACCEPTANCE DELME 2026-08-14` narrator row | `people` | Soft-deleted or left visible — Chris's call (§11.2) |
| Profile row | `profiles` | **Retained** |
| Session rows | `interview_sessions` **and** ordinary `sessions` | **Retained.** Ordinary sessions link through `sessions.payload_json`, **not** a person foreign key — see §11.2 |
| Turn rows, cases A–D + case B | `turns` | **Retained** |
| **Archive events for refused turns** (§6.2) | `turns` / archive | **Retained** — a refusal is not zero writes |
| Extraction rows | extraction claim / ledger tables | **Retained** if extraction ran |
| Story candidates | `story_candidates` | **Retained** if a trigger fired |
| Follow-up bank entries | follow-up bank | **Retained** if written |
| Projection rows | `interview_projections` | **Retained** if the correction path ran |
| Facts / family truth | `bio_facts`, family-truth tables | **Retained** if any write occurred |
| Delete-audit row | `narrator_delete_audit` | **Created** by any delete, and append-only |
| Filesystem archive | `DATA_DIR/memory/archive/people/<pid>/` | **Retained** — decoupled by design |
| §6.1 Option 1 fixtures, if chosen | `trips`, `trip_days`, `photos`, `trip_photo_links`, `trip_photo_day_placements` + the image file | **Retained** |
| `lorevox.spine.<pid>` + narrator-scoped keys, browsers **A and B** | browser `localStorage` | Browser-local, per-device; remove by hand if wanted |
| `/tmp/l2_export*` | scratch | **Delete** — carries narrator text |
| `_l2_baseline.sqlite3`, `_l2_post_restart.sqlite3` | data dir | **Two complete copies of the family database** — §11.3 |

**The report enumerates what was actually created, not this list in the abstract.** Anything
found that is not here gets added rather than ignored.

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
  endpoint — the most thorough route available, and it needs his explicit word.

> **This combination is NOT total, and the runbook must not claim it is.** Hard delete removes
> **person-linked** rows; archive deletion removes the filesystem archive and its index rows.
> **Ordinary `sessions` and their turns are connected through `sessions.payload_json`, not a
> person foreign key, and can survive both.** Anyone choosing this option should expect
> residue and verify rather than assume.

### 11.3 The baseline snapshot must be accounted for

`/mnt/c/hornelore_data/_l2_baseline.sqlite3` (§3) is **a complete copy of the live database,
including every narrator's live data.** It is retained through verification because the
restoration check diffs against it — and then it must go.

**Two** such copies exist by the end of the run — the §3 baseline and the §10 post-restart
snapshot. **After the L2 report is accepted, one explicit command:**

```bash
rm -f /mnt/c/hornelore_data/_l2_baseline.sqlite3 \
      /mnt/c/hornelore_data/_l2_post_restart.sqlite3
rm -rf /tmp/l2_export /tmp/l2_export.zip
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

**Four commands**, deliberately separate. `tests.test_chat_ws_safety_precedence` runs in its
**own process** and §14 explains why. *(This said "two commands" while listing three —
corrected 2026-08-14, and a fourth added for the helper-import suites.)*

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
PYTHONPATH=server/code .venv/bin/python -m unittest \
  tests.test_prompt_sections tests.test_system_directive_persistence
```

```bash
cd /mnt/c/Users/chris/hornelore
node tests/test_era_definition_detector.js
```

**Note on `PYTHONPATH`:** it is `server/code` only. Neither suite may require `:tests` — that
is what the stale top-level `source_scan_helpers` imports were doing, and they are fixed.

### 13.1 Expected noise in Gate 1 — read this before reporting a failure

`tests.test_wo_narrator_bridge_acceptance` prints its **own** acceptance-harness report to
stdout, ending:

```
=== 18 passed, 1 failed, 1 not exercised ===
RESULT: FAIL -- a check that was exercised did not hold.
```

**The module nevertheless passes unittest: `Ran 68 tests … OK`, exit 0.** Its printed FAIL is
**not wired to an assertion**, so it cannot turn the gate red.

**This is expected output, not a defect.**

> **CORRECTION 2026-08-14 — my earlier characterisation of this was wrong.** I described the
> module as "a harness printing FAIL and exiting 0", i.e. decoration with no assertion behind
> it. **That was overstated and the review was right to reject it.** Those lines are
> **deliberate negative-test fixtures**: the unit tests drive failing harness scenarios *on
> purpose* and then assert that the harness reports them correctly —
>
> ```python
> tests/test_wo_narrator_bridge_acceptance.py:924   self.assertIn("FAIL", log)
> tests/test_wo_narrator_bridge_acceptance.py:931   self.assertNotEqual(0, rc, log)
> ```
>
> So the printed FAIL **is** asserted; it is the thing being proved. A module that reported
> PASS for a broken scenario would be the actual bug. I withdraw the "decoration" reading.

What remains is a genuine **output-clarity** issue, and it is worth one line of guidance:

**Read the gate's verdict from unittest's exit status and summary on stderr — not from
harness text on stdout.** The two streams interleave misleadingly under a pipe (`CLAUDE.md`
records this same buffering trap), and a module that deliberately exercises failure paths
will print `RESULT: FAIL` while passing. Keep the module in the gate.

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
| Acceptance narrator created | **There is no clean reversal.** `DELETE /api/people/{id}` defaults to `mode=soft` (`people.py:241`) and removes no dependent rows. Follow §11 — account for the evidence, do not claim it is gone. |
| Turns / sessions / archive written for it | **Retained.** No delete mode removes them, and the filesystem archive is decoupled from narrator deletion by design (`memory_archive.py:658-660`). Enumerated in §11.1; keep-or-delete is Chris's decision in §11.2. |
| A family narrator was touched | **Should be impossible under §2.** If it happened: stop, do not self-repair, restore from the §3 snapshot with Chris present. |
| The stack is in a bad state | Chris restarts. No agent starts or stops the stack. |
| A spine cache was cleared | Re-created automatically by `initTimelineSpine()` on the next load once DOB and POB are present (`app.js:7689`, gated `state.js:535`). **Note the side effect: the narrator is demoted to `pass1` until then** (`app.js:3394`). |

**If a future change does touch pass ownership, note now that it cannot be rolled back
server-side** — there is no DB column, no server flag and no per-narrator setting controlling
`current_pass`; its only durable home is browser `localStorage`. The nearest real, durable,
reversible per-narrator control is `people.narrator_type` (`db.py:2106`). That is a fact for
the decision brief, not a licence to build anything.

---

## 16.1 Gate closure is CONDITIONAL

**No gate closes on a case that was not exercised.** The report states, per case, one of
PASS / FAIL / **UNEXERCISED (reason)** — and any UNEXERCISED case leaves its gate explicitly
open:

| If unexercised | Consequence |
|---|---|
| `witness` or `floor_hold` branch (§5, A5) | **Gate B stays open.** Phase 1A is not fully discharged. |
| Export half (§5.1, archive flag off) | **Gate B stays open.** "Browser/export smoke" is not closed by the browser half alone. |
| Active-trip or selected-photo (§6.1 Option 2) | **Phase 10 stays partially open.** |
| Case C (no second browser) | The Profile Seed conflict stays **unconfirmed**; the decision brief's option D remains live. |

**Do not write "Gate B closed" unless every case under it passed.** A partial pass is a
partial pass, and saying so costs nothing.

## 16. What this runbook does not authorise

Executing itself. L3, L4, Phase 2, Phase 8's remainder, any prompt change, any flag change,
any `.env` edit, any safety reactivation, and any stack start. **L2 opens on Chris's word.**
