# Kent Dry Run — Operator Sheet

**WO-13 Phase 8, Plan A. Host-side runbook.**

This sheet is what you execute on the Hornelore host. It walks the full
backfill → review → promote → refresh → flag-flip sequence against a
snapshot copy of the real DB, so nothing in this sheet can damage Kent's
live profile unless you deliberately opt into live mode.

The companion script is:

    wo13_phase8_proof/run_kent_dry_run.py

Everything below calls that script. Nothing below calls curl, the
browser-side UI, or a running server — **except** Step 7 (refresh shim)
and Step 8 (flag-flip under load), which explicitly require the server
to be up.

---

## 0. What you'll need before you start

1. Kent's `person_id` (the UUID / integer in the `people.id` column).
   If you don't know it:

       sqlite3 data/db/lorevox.sqlite3 \
           "SELECT id, display_name FROM people WHERE display_name LIKE '%Kent%';"

2. A backup of the live DB, before anything else. The script does not
   touch the live DB in the default mode, but you still want a
   rollback floor:

       cp data/db/lorevox.sqlite3 data/db/lorevox.sqlite3.pre-kent-$(date +%Y%m%d-%H%M%S).bak

3. Python 3.9+ inside the project's own venv, with `server/code` on
   the import path. Running the script from the hornelore project
   root is sufficient.

4. The server **STOPPED** for Steps 1–6. We start it again only for
   Steps 7 and 8.

Set an env var so every invocation below is short:

    export KENT=<kent person_id>

---

## 1. Audit — read-only, proves nothing is broken

    python wo13_phase8_proof/run_kent_dry_run.py audit --person-id "$KENT"

The script automatically creates a snapshot copy under
`wo13_phase8_proof/kent_dry_run_data/db/kent_dry_run_snapshot.sqlite3`
and applies the WO-13 schema migrations via `init_db()`. If your live
DB predates WO-13, this is where the FT tables and `narrator_type`
column get created — **on the snapshot only**, not on the live file.

Expected output:

    DB file : .../kent_dry_run_snapshot.sqlite3
    flag    : HORNELORE_TRUTH_V2_PROFILE=(unset)
    schema  : family_truth_notes     PRESENT
    schema  : family_truth_rows      PRESENT
    schema  : family_truth_promoted  PRESENT
    schema  : people.narrator_type   PRESENT
    person  : id=<kent_id>  name='Kent James Horne'  narrator_type=live

    LEGACY basics (the 5 protected fields will drive backfill):
      basics.fullname    = 'Kent J. Horne'
      basics.preferred   = 'KJ'
      basics.dob         = '1943-01-01'
      basics.pob         = 'Stoneycreek, NS'
      basics.birthOrder  = 'oldest'

    FT rows     : 0 total  {}
    FT promoted : 0 rows

**Capture for C:**

- Kent's legacy basics values, verbatim
- Whether any FT rows already exist (should be 0 for a first run)
- Whether `narrator_type` came back as `live` (it must — Kent is not a
  reference narrator)

**Rollback:** none required. The audit is read-only.

---

## 2. Backfill — seed the review queue from profile_json

    python wo13_phase8_proof/run_kent_dry_run.py backfill --person-id "$KENT"

Expected output:

    {
      "created_rows": 5,
      "person_id": "<kent_id>",
      "reference_refused": false,
      "skipped_empty": 0,
      "skipped_existing": 0
    }

**What just happened:** for each of the 5 protected identity fields
that was non-empty in Kent's legacy basics, the backfill created one
shadow note in `family_truth_notes` + one `needs_verify` row in
`family_truth_rows`. Nothing was promoted. Kent's public profile is
unchanged.

**Capture for C:**

- `created_rows` count (should match how many of the 5 protected fields
  had non-empty legacy values)
- `skipped_existing` should be 0 on a first run
- If `skipped_empty` > 0, note which fields were empty in legacy — that
  tells you what Kent still has to enter manually

**Idempotency check (optional but recommended):** run the backfill a
second time. Expected: `created_rows=0`, `skipped_existing=5`.

    python wo13_phase8_proof/run_kent_dry_run.py backfill --person-id "$KENT"

**Rollback:** discard the snapshot.

    rm -rf wo13_phase8_proof/kent_dry_run_data/

---

## 3. Review queue walk

    python wo13_phase8_proof/run_kent_dry_run.py queue --person-id "$KENT"

Expected output: five rows, one per protected field, all with
`status=needs_verify`. Each row prints its `row_id`, `field`,
`source_says` (the legacy value verbatim), `extraction_method=manual`,
and `confidence=1.0`.

This is your dry-run review drawer. You now exercise the four review
branches the real UI supports:

### 3a. Approve one row with a **correction** (this is the important one)

Pick the field where legacy is wrong. For the seeded demo fixture, the
clearest case is `personal.fullName`:

    python wo13_phase8_proof/run_kent_dry_run.py approve <fullName_row_id> \
        --approved-value "Kent James Horne" \
        --reviewer "<your name>"

This is the motion that makes Phase 8 actually matter: the reviewer
asserts a value different from what legacy had. The `approved_value`
column is what promoted truth will carry forward.

### 3b. Approve one row **without** a correction (legacy is already right)

For example, `personal.dateOfBirth` if legacy already has it right:

    python wo13_phase8_proof/run_kent_dry_run.py approve <dob_row_id> \
        --reviewer "<your name>"

With no `--approved-value`, the promoted value becomes `source_says`
(i.e. the legacy value verbatim).

### 3c. Approve one row **with a qualification** (true-but-uncertain)

    python wo13_phase8_proof/run_kent_dry_run.py approve <pob_row_id> \
        --qualification "County spelling uncertain — 'Queen's' vs 'Queens'." \
        --reviewer "<your name>"

This sends `status=approve_q`. The qualification text will surface in
both `basics._qualifications[field]` and `basics.truth[]` on the
flag-on read.

### 3d. Reject one row

    python wo13_phase8_proof/run_kent_dry_run.py reject <birthOrder_row_id> \
        --reviewer "<your name>"

`status=reject` rows never promote. They stay in the queue for audit.

### 3e. Leave one row untouched

Just don't approve/reject it. It stays `needs_verify`. The queue will
still show it on re-run.

**Capture for C:**

- How many clicks it took to get through the 5 rows
- Whether any field made you stop and think about where the truth
  actually lives (that's what the tool is for)
- Whether the `approved_value` / `qualification` / `reject` distinction
  felt natural or awkward in practice

---

## 4. Promote

    python wo13_phase8_proof/run_kent_dry_run.py promote --person-id "$KENT" \
        --reviewer "<your name>"

Expected output: a JSON block listing every approved row the promoter
processed, with each one showing `op: "created"` on the first run and
the promoted `value` that will now drive the profile endpoint.

**What just happened:**

- Every `approve` / `approve_q` row was upserted into
  `family_truth_promoted` keyed by `(person_id, subject_name, field)`.
- Qualified rows carry their qualification text across.
- `reject` rows were skipped.
- Rows you left as `needs_verify` were skipped.
- The promoter is content-addressable: re-running it immediately after
  is a no-op (`op: "noop"`).

**Idempotency check:** re-run the promote. Every `op` should be
`"noop"` and every `updated_at` identical.

**Capture for C:**

- Number of `created` / `updated` / `noop` / `blocked` ops on first run
- Any row that promoted with a surprising value (those are the ones
  that matter most)
- Total wall-clock time for the promote call

---

## 5. Read-profile — confirm the flag flip actually does something

    python wo13_phase8_proof/run_kent_dry_run.py read-profile --person-id "$KENT"

This reads Kent's profile under **both** flag states, back to back,
without involving a running server. It is the script-side equivalent of
a browser opening `GET /api/profiles/{id}` once with the flag off and
once with it on.

Expected output shape:

    ── flag OFF (legacy passthrough) ──
        basics.birthOrder           = '<legacy>'
        basics.fullname             = 'Kent J. Horne'             ← wrong
        ...
        kinship rows = 2
        pets    rows = 1

    ── flag ON  (promoted-truth hybrid) ──
        basics.birthOrder           = '<legacy passthrough, unchanged>'
        basics.fullname             = 'Kent James Horne'          ← corrected
        ...
        kinship rows = 2
        pets    rows = 1

    ── diff ──
    {
      "basics_diff": {
        "fullname": { "off": "Kent J. Horne", "on": "Kent James Horne" }
      }
    }

**What to verify:**

1. The corrected fields you approved in 3a show the new `approved_value`
   on the ON side and the old legacy on the OFF side.
2. The uncorrected fields you approved in 3b show the same value in
   both OFF and ON (sanity — promotion preserves legacy when no
   correction was given).
3. The qualified fields in 3c show up in `basics._qualifications` and
   `basics.truth` on the ON side and carry no mark on the OFF side.
4. The rejected field in 3d is absent from the ON side's diff (it
   simply never promoted, so the hybrid falls through to legacy).
5. `kinship` and `pets` rows are byte-identical across OFF and ON.
6. The unmapped `basics.*` keys (`culture`, `country`, `pronouns`, etc.)
   are byte-identical across OFF and ON.

**If any of these fail, STOP.** The flag flip is doing something it
shouldn't. File an observation in the C capture template and do not
proceed to Step 8.

**Capture for C:**

- The full diff JSON (paste it verbatim into the runbook)
- Any field that changed when you didn't expect it to

---

## 6. Run-all (optional) — single-shot trace

If you want a single-shot pipeline run that writes a machine-readable
trace file, use `run-all` **against a fresh snapshot** and without any
`--approved-value` corrections:

    python wo13_phase8_proof/run_kent_dry_run.py --fresh-snapshot \
        run-all --person-id "$KENT" \
        --trace-path wo13_phase8_proof/kent_dry_run_trace.json

Expected behavior:

- Backfill → approve-all → promote → read-profile under both flags
- Writes `kent_dry_run_trace.json` in the proof folder
- Zero diff in the read-profile step (expected — no corrections were
  applied, so promoted == legacy)

`run-all` is a pipeline smoke test, not a divergence test. It proves
the machinery runs end-to-end. For divergence evidence, use the
interactive Steps 1–5 above.

---

## 7. UI refresh shim — **server required, manual verification**

Start the real hornelore server. Set `HORNELORE_TRUTH_V2_PROFILE=0`
explicitly so you can see the pre-flag baseline:

    HORNELORE_TRUTH_V2_PROFILE=0 python server/hornelore-serve.py

Open the Hornelore web UI, select Kent.

Walk the following sequence **from the UI**, watching what happens
after each click:

| Action | What should happen |
|---|---|
| Open review drawer (wo13-review.js) | queue renders 5 rows, protected fields tagged |
| Click approve on row with correction | row turns green, `Promote approved` button enables |
| Click "Promote approved" | spinner → success toast → **profile form re-hydrates** |
| | **obituary identity card re-renders** |
| | **memoir source name updates to the corrected preferred/fullname** |
| | **timeline spine re-renders** |
| Open DevTools → Network | see `POST /api/session/put` with the new profile payload |
| Hard-refresh the page (Ctrl+R) | everything stays updated — promoted truth persisted |

If any of the starred UI surfaces fails to update after the promote
click, the `lvxRefreshProfileFromServer` shim is not wiring correctly.
B3 already proved the shim's contract in isolation (36 green
assertions) — a failure here means wo13-review.js is calling the shim
with the wrong `pid` or not calling it at all. Check the console for
`[lvx] refresh profile after promote failed` warnings.

**Capture for C:**

- Time between clicking "Promote approved" and the profile form
  re-hydrating (subjective — does it feel immediate?)
- Any surface that **didn't** update without a page refresh
- Whether the "Memory Truth in progress" state felt accurate
  when some fields were promoted and others still `needs_verify`
  (this is the state-2 banner case for Phase 9)

---

## 8. Flag flip under load

Stop the server. Restart with the profile flag on:

    HORNELORE_TRUTH_V2_PROFILE=1 python server/hornelore-serve.py

Curl the profile endpoint directly:

    curl -s http://localhost:<port>/api/profiles/$KENT | jq '.source, .profile.basics'

Expected:

    "promoted_truth"
    {
      "fullname": "Kent James Horne",   ← promoted
      "preferred": "KJ",                 ← legacy passthrough if not corrected
      ...
    }

Reload the UI. Watch for:

1. **No visual regression.** Profile form, obituary card, memoir
   source name, timeline — everything should look identical to what
   you saw post-promote in Step 7.
2. **No console errors.** Open DevTools, hard-refresh, check for any
   red in the console.
3. **No type drift.** If any field that was a string in Step 7 is now
   `null`, `undefined`, or an array, the builder is misreading the
   promoted row. Note the field and bail.

**Rollback if Step 8 goes wrong:** stop the server, restart without the
env var (or with `HORNELORE_TRUTH_V2_PROFILE=0`), and Kent is back on
the legacy read path. The promoted rows are still in the DB but the
endpoint ignores them.

**Capture for C:**

- Every field whose value or type shifted between the flag-off and
  flag-on reads (cross-check against Step 5's diff)
- Any UI element that flinched when the flag went on
- How long you let the flag stay on before declaring it clean
  (recommendation: an hour of normal usage before a second narrator)

---

## 9. Rollback floor (at any point)

1. Stop the server.
2. `cp data/db/lorevox.sqlite3.pre-kent-<stamp>.bak data/db/lorevox.sqlite3`
3. `rm -rf wo13_phase8_proof/kent_dry_run_data/`
4. `unset HORNELORE_TRUTH_V2_PROFILE`
5. Start the server normally. Kent is exactly where he was before
   you started this sheet.

Nothing in Steps 1–6 can reach the live DB in default mode. The only
steps that touch the live DB are 7 and 8, and only because the real
server is reading/writing it. If Steps 7 or 8 fail, the backup + flag
rollback above restores the pre-run state in under a minute.

---

## 10. What to capture for C — the runbook

When you finish Step 8, write down — verbatim, even if it feels small:

1. **Inputs you had to look up.** Kent's `person_id`, DB path, port,
   anything that wasn't obvious.
2. **Every step's actual output.** Copy-paste the JSON blobs, not
   summaries.
3. **Every moment of friction.** "I had to stop and guess X" is
   exactly what the runbook needs to preempt.
4. **Clock time per step.** Even rough minutes.
5. **What surprised you.** Anything that didn't match this sheet.
6. **One real conflict.** The field where legacy was wrong and
   promoted is right — name it and keep the diff.
7. **The flag-flip moment.** Did the UI lurch? Did the curl response
   shape match what Step 5 predicted? Any errors?
8. **What you'd automate next.** If something was mechanical and slow,
   note it so it goes into the runbook as a script, not prose.

That capture is what I fold into `C — OPERATOR_RUNBOOK.md` after
you're done. The runbook is written from observed reality, not from
this sheet.

---

## Appendix A — Smoke test from the sandbox

The companion script was smoke-tested in the sandbox against a seeded
Kent fixture with deliberately-wrong legacy values. The fixture and
the run produced:

**Backfill:** `created_rows=5`, `skipped_existing=0`, `skipped_empty=0`.

**Review queue:** 5 rows, one per protected field, all `needs_verify`.

**Interactive review:**

- `personal.fullName` approved with `--approved-value "Kent James Horne"`
- Other 4 rows approved without corrections

**Promote:** 5 `created` ops on first run, 5 `noop` on re-run.

**Read-profile diff** (this is the Phase 8 success condition):

    {
      "basics_diff": {
        "fullname": {
          "off": "Kent J. Horne",
          "on":  "Kent James Horne"
        }
      },
      "changed_top_keys": ["basics"],
      "same_top_keys":    ["kinship", "pets"],
      "added_top_keys":   [],
      "removed_top_keys": []
    }

Only the corrected field shifted. Every other key — the 4 un-corrected
protected fields, the 3 unmapped basics passthroughs (`culture`,
`country`, `pronouns`), kinship, pets — was byte-identical across the
flag flip. This is the exact shape the live Kent run should produce
after Step 5.

---

## Appendix B — Command cheat-sheet

    # set up
    export KENT=<kent person_id>

    # Step 1 — audit (creates snapshot on first call)
    python wo13_phase8_proof/run_kent_dry_run.py audit --person-id "$KENT"

    # Step 2 — backfill
    python wo13_phase8_proof/run_kent_dry_run.py backfill --person-id "$KENT"

    # Step 3 — review queue
    python wo13_phase8_proof/run_kent_dry_run.py queue --person-id "$KENT"

    # Step 3a — approve with correction
    python wo13_phase8_proof/run_kent_dry_run.py approve <row_id> \
        --approved-value "<correct value>" --reviewer "<you>"

    # Step 3b — approve without correction
    python wo13_phase8_proof/run_kent_dry_run.py approve <row_id> --reviewer "<you>"

    # Step 3c — approve with qualification
    python wo13_phase8_proof/run_kent_dry_run.py approve <row_id> \
        --qualification "<note>" --reviewer "<you>"

    # Step 3d — reject
    python wo13_phase8_proof/run_kent_dry_run.py reject <row_id> --reviewer "<you>"

    # Step 4 — promote
    python wo13_phase8_proof/run_kent_dry_run.py promote --person-id "$KENT" \
        --reviewer "<you>"

    # Step 5 — read profile both flag states
    python wo13_phase8_proof/run_kent_dry_run.py read-profile --person-id "$KENT"

    # Step 6 — one-shot smoke trace
    python wo13_phase8_proof/run_kent_dry_run.py --fresh-snapshot \
        run-all --person-id "$KENT"

    # Step 7 — server on with flag OFF (manual UI walk)
    HORNELORE_TRUTH_V2_PROFILE=0 python server/hornelore-serve.py

    # Step 8 — server on with flag ON
    HORNELORE_TRUTH_V2_PROFILE=1 python server/hornelore-serve.py

    # Live mode (only after the snapshot run is clean)
    python wo13_phase8_proof/run_kent_dry_run.py --live --i-understand \
        --live-db data/db/lorevox.sqlite3 \
        audit --person-id "$KENT"
