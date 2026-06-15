# WO-GOLFBALL-HARNESS-03 — API-down recovery + DB-lock reproduction

**Status:** SPEC (parent-session safety gate)
**Owner:** Claude (build) → Chris (live verify)
**Author:** 2026-04-30 evening
**Lane:** Parallel to BINDING-01; builds on WO-LORI-HARNESS-01 (operator harness) and WO-GOLFBALL-HARNESS-02 (narrator isolation)
**Pre-reqs:** WO-LORI-STORY-CAPTURE-01 Phase 1A landed; operator harness endpoint live; BUG-DBLOCK-01 (#344) RED

---

## 1. Why this exists

The harness lane today proves Lori behaves correctly **on the happy path**. The parent-session readiness checklist does not yet include any evidence that Lori behaves correctly **on the failure path**. Three concrete unknowns block the parent session:

1. **API-down mid-turn** — Janice is in the middle of saying something memorable, the LLM falls over (OOM, VRAM spike, server crash, network partition). Does her text survive? Does her audio file survive? Does the next turn after recovery acknowledge what was lost?
2. **DB-lock surfacing** — BUG-DBLOCK-01 (#344) reports "database is locked" errors at suspiciously regular 5-second intervals during real sessions. The fix lane is blocked because no one can reliably reproduce it. Without a reproducer, any future patch is unfalsifiable.
3. **Operator recovery surface** — when the system fails mid-session, does the operator know **which turn was last saved** without grepping the DB by hand?

This WO turns those unknowns into automated tests with deterministic pass/fail dispositions.

**Bumper sticker:** *Story preservation is sacred. Behavior on failure is the actual product.*

---

## 2. Scope (locked)

**In scope:**

- Failure-injection harness extending `scripts/archive/run_golfball_interview_eval.py` with three new modes:
  - `--inject-api-down` — kill API process mid-turn, then verify preservation rows + audio files survive
  - `--inject-dblock` — synthetically hold a write transaction to reproduce BUG-DBLOCK-01
  - `--inject-llm-timeout` — force an LLM read-timeout, verify chat_ws fallback path
- New `last_saved_turn` accessor — DB read returning the most recent `story_candidate` row + the most recent `archive_segment` row per narrator
- Operator-harness extension exposing `last_saved_turn` over HTTP
- Bug Panel section surfacing `last_saved_turn` so the operator can read recovery state without DB inspection
- Narrator-facing recovery message contract — when chat_ws reconnects after failure, the next turn's response must acknowledge the gap

**Out of scope (explicitly):**

- Fixing BUG-DBLOCK-01 itself. This WO ships the reproducer; the fix is a separate lane that gets eval-gated by this reproducer.
- Audio recovery from corrupt files. We verify the file exists on disk and is readable; restoring corrupted audio is a separate problem.
- Network-partition simulation across narrator switches. Single-narrator failure-recovery is enough for parent-session readiness.
- Multi-day session resume. Recovery means "the next turn after a failure"; week-long resume is post-parent-session.

---

## 3. Architecture

### 3.1 Failure injection — three modes

All three modes ride the existing `run_golfball_interview_eval.py` shape (sequential turns through the operator harness). Each mode wraps the **third** turn in the sequence with a failure injection, then runs turns 4-N through the recovery path. Failure-on-third-turn is deliberate: turns 1-2 establish baseline so the recovery turn has prior state to acknowledge.

#### Mode A — `--inject-api-down`

```
Turn 1: clean turn (baseline)
Turn 2: clean turn (memorable, full_threshold story)  ← preservation-eligible
Turn 3: send turn → wait 1s → SIGTERM the API process → wait 5s
        verify story_candidate row from Turn 2 still in DB
        verify audio file from Turn 2 still on disk
        verify chat_ws gracefully closed (no half-written rows)
        restart API
Turn 4: send turn → assistant_text MUST acknowledge the gap
        ("we got disconnected", "I'm back", "let me pick up where we left off",
         OR include the last_saved_turn timestamp)
```

Pass: Turn 2 row + audio survive AND Turn 4 acknowledges. Fail: any condition violated.

#### Mode B — `--inject-dblock`

```
Turn 1: clean turn (baseline)
Turn 2: open a synthetic long-held write transaction in a sidecar process:
          BEGIN IMMEDIATE; INSERT INTO …; -- hold for 10s without COMMIT
        meanwhile send Turn 3 through operator harness
        record: did chat_ws hit "database is locked"?
        record: did preserve_turn fail?
        record: did the chat turn return assistant_text or error?
        sidecar COMMITs after 10s
Turn 4: clean turn (verify recovery)
```

This is the reproducer for BUG-DBLOCK-01. The 10s hold is calibrated against the observed 5s `busy_timeout` and the empirical 5s interval pattern. We expect to see the lock surface; the WO's job is to make that observation deterministic and CI-runnable.

Pass: lock surfaces deterministically, harness records `db_locked=True`, **AND** the system recovers cleanly on Turn 4 (no orphan rows, no zombie connections). Fail: lock doesn't surface (reproducer broken) OR recovery is unclean.

#### Mode C — `--inject-llm-timeout`

```
Turn 1: clean turn
Turn 2: clean turn
Turn 3: set HORNELORE_LLM_FORCE_TIMEOUT=1 in env, send turn
        verify chat_ws falls through to fallback / safe-default response path
        verify story_candidate STILL written (transcript was captured pre-LLM)
        clear env
Turn 4: clean turn
```

This validates the half of WO-LORI-STORY-CAPTURE-01 LAW 3 that says preservation is decoupled from extraction. If the LLM fails, the transcript still lands.

### 3.2 `last_saved_turn` accessor

New `db.py` function:

```python
def last_saved_turn(narrator_id: str) -> Optional[dict]:
    """Return the most recent saved-state evidence for a narrator.

    Result shape:
      {
        "narrator_id": str,
        "story_candidate": {"id": str, "created_at": str, "transcript_preview": str} | None,
        "archive_segment": {"id": str, "created_at": str, "session_id": str} | None,
        "latest_created_at": str | None,  # max of the two
      }
    Returns None if narrator has no saved state at all.
    """
```

Reads from `story_candidates` and `archive_segments` tables, narrator-scoped, ORDER BY created_at DESC LIMIT 1 each. No JOIN — two small queries, simpler index plan.

### 3.3 Operator-harness extension

Add one endpoint to `operator_harness.py` (default-off behind same `HORNELORE_OPERATOR_HARNESS=1` gate):

```
GET /api/operator/harness/last-saved-turn?narrator_id=<id>
   → {ok, narrator_id, story_candidate, archive_segment, latest_created_at}
   → 404 if narrator has nothing saved
```

This is the read accessor; the recovery message contract uses it.

### 3.4 Bug Panel section

New JS module + HTML mount:

- `ui/js/bug-panel-recovery.js` — IIFE polling the last-saved-turn endpoint every 30s when Bug Panel is open + on focus
- `ui/css/bug-panel-recovery.css` — minimal chrome matching existing operator sections
- Mount above the existing Eval Harness section in `hornelore1.0.html`

Display per-narrator:

```
[Narrator: Janice] Last saved: 2026-04-30 16:42:17
  story_candidate: 9bb91643-… ("the day we set the kitchen on fire …")
  archive_segment: turn_482 (session abc-123)
```

Operator sees recovery state without opening sqlite.

### 3.5 Recovery message contract

When chat_ws reconnects after a session interruption (heuristic: gap between previous chat_ws close and new connect > 30s for the same `(narrator_id, session_id)`), the next turn's prompt-composer block prepends:

```
RECOVERY CONTEXT: Session was interrupted. The narrator's last saved turn
was at {latest_created_at}, preview: "{transcript_preview[:80]}". Briefly
acknowledge the gap before continuing.
```

This is a system-prompt addition, gated behind `HORNELORE_RECOVERY_MESSAGE=1` (default off until live-tested). When off, no behavior change.

---

## 4. Implementation order

1. **`db.last_saved_turn()` accessor** + 4 unit tests (empty narrator, story-only, archive-only, both-present-pick-newer). Pure read, no side effects.
2. **Operator-harness `/last-saved-turn` endpoint** + integration test hitting it via FastAPI TestClient.
3. **Mode C — `--inject-llm-timeout`** first (least invasive, no signal-handling complexity). Validates the preservation-decoupled-from-extraction guarantee.
4. **Mode A — `--inject-api-down`** next. Adds process-kill via subprocess.Popen + SIGTERM; restart via `start_all.sh`. Worth its own checkpoint.
5. **Mode B — `--inject-dblock`** last. Sidecar process holding `BEGIN IMMEDIATE`. This is the BUG-DBLOCK-01 reproducer — once it runs deterministically, the bug is no longer "RED with no fix lane," it's "RED with a regression test waiting."
6. **Bug Panel `bug-panel-recovery.js` + CSS + mount** — read-only surface, parallel to existing operator sections.
7. **Recovery message contract** — prompt-composer addition behind env flag. Live-test after stack restart; do not enable by default.

Each step lands as its own commit. Same posture as WO-GOLFBALL-HARNESS-02 (Phase 1A bug sweep) — small, reviewable, byte-stable when the new mode isn't invoked.

---

## 5. Acceptance criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | `db.last_saved_turn(narrator_id)` returns correct shape, picks newer of story_candidate vs archive_segment | unit tests, 4 cases |
| 2 | `/api/operator/harness/last-saved-turn` returns 404 when narrator has nothing, 200 with shape when populated | TestClient integration test |
| 3 | Mode C: LLM forced to timeout on Turn 3 → story_candidate from Turn 3 STILL exists in DB | harness self-check |
| 4 | Mode A: API SIGTERM after Turn 2 commits → Turn 2 story_candidate + audio file survive ; Turn 4 assistant_text acknowledges gap | harness self-check (acknowledgment is regex-checked: `\b(disconnected|interrupted|gap|earlier|came back|picking up)\b`) |
| 5 | Mode B: synthetic 10s write lock → harness records `db_locked=True` for the contended turn ; Turn 4 succeeds cleanly with no orphan rows | harness self-check + post-run DB integrity probe |
| 6 | Bug Panel "Last Saved Turn" section auto-loads + auto-refreshes ; shows per-narrator timestamps + previews ; quiet-skip when endpoint disabled | live-verify in Chrome |
| 7 | Recovery message contract enabled via env flag triggers acknowledgment in next turn after >30s gap ; off by default ; byte-stable when off | flagged unit test + live verify |
| 8 | All four py_compile clean ; full test suite (`tests/test_story_*` + `tests/test_age_arithmetic` + new tests) green ; LAW 3 isolation test still green | CI + manual `python3 -m unittest` |

---

## 6. Dispositions

- **ADOPT** if criteria 1-8 all green and Mode B reliably surfaces the lock at least 9/10 runs.
- **ITERATE** if Mode B surfaces the lock but inconsistently (<9/10) — calibrate hold duration and retry. Do not ship a flaky reproducer.
- **PARK** if Mode A's SIGTERM-then-restart adds enough complexity that the harness becomes brittle. Fall back to a softer "kill the LLM connection only, leave API running" variant. Do not block the WO on getting full process-kill perfect.
- **ESCALATE** if Mode C reveals that preservation is **not** decoupled from extraction — that means LAW 3 is breaking somewhere, and BINDING-01 / SPANTAG work cannot proceed safely.

---

## 7. Files touched

```
server/code/api/db.py                                       (+30 -0)  last_saved_turn accessor
server/code/api/routers/operator_harness.py                 (+40 -0)  /last-saved-turn endpoint
scripts/archive/run_golfball_interview_eval.py              (+~150)   3 injection modes + flags
scripts/archive/golfball_dblock_sidecar.py                  (NEW)     synthetic write-lock holder
ui/js/bug-panel-recovery.js                                 (NEW)     last-saved-turn surface
ui/css/bug-panel-recovery.css                               (NEW)     minimal chrome
ui/hornelore1.0.html                                        (+3)      mount + link + script tag
.env.example                                                (+4)      HORNELORE_LLM_FORCE_TIMEOUT,
                                                                       HORNELORE_RECOVERY_MESSAGE
server/code/api/prompt_composer.py                          (+25)     RECOVERY CONTEXT block
                                                                       (gated, default-off)
tests/test_last_saved_turn.py                               (NEW)     4 accessor tests
tests/test_recovery_message_contract.py                     (NEW)     flagged composer test
WO-GOLFBALL-HARNESS-03_Spec.md                              (this)
```

No `extract.py` changes. No schema migration (uses existing `story_candidates` + `archive_segments` tables).

---

## 8. Sequencing notes

- Mode B's sidecar holds a write lock against the **same** SQLite file the API uses. Sidecar must use `PRAGMA busy_timeout=0` so it doesn't queue behind itself. Sidecar process tree is logged + killed in finally-block to prevent stuck locks across runs.
- Mode A's API restart goes through Chris's `start_all.sh`. Per CLAUDE.md, the agent does NOT restart the stack. Mode A is the exception because it's the test injecting the failure — it owns the restart it caused. Cold-boot warmup probe (per CLAUDE.md stack-ownership rule) must precede Turn 4.
- Recovery message contract (§3.5) is the only piece that touches narrator-facing behavior. It defaults OFF for that reason. Chris signs off after live-test before flag flips on.
- BUG-DBLOCK-01 (#344) cannot be marked completed until Mode B reproducer passes 9/10, the underlying fix lands, AND Mode B then shows the lock no longer surfaces. The reproducer is the eval gate.

---

## 9. Connections

- **WO-LORI-STORY-CAPTURE-01 LAW 3** — preservation imports zero extraction-stack code. Mode C is the runtime test of that law.
- **WO-LORI-HARNESS-01** — operator harness is the surface this WO extends. No second pipeline.
- **WO-GOLFBALL-HARNESS-02** — narrator isolation test pattern (synthetic narrator with cleanup) is reused for failure-injection narrators.
- **BUG-DBLOCK-01 (#344)** — Mode B is its reproducer; the bug closes only when reproducer passes both as red-flag (lock surfaces today) and as green-light (lock does not surface after fix lands).
- **Parent-session readiness checklist** — this WO ships the failure-path evidence the checklist is missing today.

---

## 10. Estimate

- §3.2 + §3.3 + §3.4: 3-4 hours (read accessor + endpoint + Bug Panel surface + tests)
- Mode C: 1-2 hours (least-invasive)
- Mode A: 2-3 hours (process kill + cold-boot warmup probe + acknowledgment regex)
- Mode B: 3-5 hours (sidecar process, calibration to hit 9/10 reproduction rate)
- Recovery message contract (§3.5): 2 hours (composer addition, flagged test, live-verify hold for Chris)

Total: ~12-16 hours. Lands as 7 commits, code-isolated from docs per CLAUDE.md hygiene gate.
