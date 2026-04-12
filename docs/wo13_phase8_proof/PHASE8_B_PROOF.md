# WO-13 Phase 8 — B-Round Proof Packet

**Edge tests that gate the Kent rollout**

Date: 2026-04-11
Harnesses:
- `/sessions/nice-fervent-clarke/wo13_test/run_phase8_b1_conflict_test.py`
- `/sessions/nice-fervent-clarke/wo13_test/run_phase8_b2_flagflip_test.py`
- `/sessions/nice-fervent-clarke/wo13_test/run_phase8_b3_shim_test.js`

Result: **B1 9/9 + B2 14/14 + B3 36/36 = 59 new assertions, all green.**

---

## 1. Why a B-round

Phase 8's base harness (`run_phase8_test.py`) used the Ada Lovelace
fixture where the legacy blob and the promoted truth rows either agreed
on every protected field (`preferred='Ada'` in both) or the legacy value
was the only one that existed at all (`fullname`, `dob`, `pob`,
`birthOrder` never got promoted). That closed the "promoted wins"
contract from one side only: we proved that *when* promoted truth exists
it shows up in the output, but we never proved the precedence rule in
the case where legacy and promoted actively disagree.

Three concrete failure modes would have slipped past the base harness
onto Kent:

1. **Precedence** — a builder bug that silently preferred legacy over
   promoted on the five protected identity fields
2. **Flag-flip schema drift** — a stray code path that mutated FT tables
   on a read, or surfaced new top-level keys outside the two agreed
   sidecars, so that turning the flag on and off left residue on
   `state.profile`
3. **Refresh shim regression** — a rename or rewire of
   `lvxRefreshProfileFromServer` that quietly dropped one of its
   post-promote side effects (obit card, memoir source name, timeline,
   session payload)

The B-round closes all three.

## 2. B1 — Legacy vs promoted conflict precedence

Fixture: Kent James Horne, **every** legacy value deliberately wrong on
all five protected fields. Corrections promoted via
`extraction_method='manual'` so the Phase 7 rules_fallback gate does not
block them.

| Field | Legacy (wrong) | Promoted (correct) |
|---|---|---|
| `basics.fullname` | `"Kent J. Horne"` | `"Kent James Horne"` |
| `basics.preferred` | `"KJ"` | `"Kent"` |
| `basics.dob` | `"1943-01-01"` | `"1943-01-03"` |
| `basics.pob` | `"Stoneycreek, NS"` | `"Stoneycreek, Nova Scotia"` |
| `basics.birthOrder` | `"oldest"` | `"eldest of three"` |

Nine assertions, in order:

1. Seed: legacy blob written with all five fields wrong
2. Seed: five correction rows promoted, every `op` is `created`
3. **Builder: every protected field returns the promoted value** —
   every legacy value is asserted to be absent from the output
4. Builder: six unmapped legacy `basics.*` keys (`culture`, `country`,
   `pronouns`, `legalFirstName`, `legalMiddleName`, `legalLastName`)
   pass through untouched
5. Builder: `kinship` and `pets` pass through untouched even when a
   non-promoted decoy row with `field='spouse'` is staged
6. **Partial conflict** (Janice fixture): two fields promoted, three
   un-promoted. The two promoted win; the three un-promoted fall
   through to legacy. This closes the "partial review" case that the
   base harness did not cover.
7. **Traceability** — every promoted protected record has a non-null
   `source_row_id` that matches the `row_id` returned by
   `ft_promote_row` at seed time. This is the B1 floor for per-field
   provenance; Phase 9 `basics._provenance` will sit on top of this.
8. **Idempotent re-promote** — all five rows re-promoted after a 1.1s
   sleep, every op is `noop`, and every `updated_at` is byte-identical
   before and after. This catches the "promoted wins but the row got
   re-created" class of bug.
9. Builder output byte-identical pre- and post-noop round.

```
==============================================================
WO-13 Phase 8 B1 — legacy vs promoted conflict precedence
==============================================================
  OK  seed: Kent with deliberately-wrong legacy values for all 5 protected fields
  OK  seed: 5 corrected protected-field rows promoted via manual extraction
  OK  builder: all 5 protected fields — promoted wins over conflicting legacy
  OK  builder: unmapped legacy basics.* pass through untouched during conflict
  OK  builder: kinship + pets pass through untouched regardless of FT rows
  OK  builder: partial conflict — 2 promoted fields win, 3 unreviewed fall through
  OK  traceability: every promoted protected field points back to its FT row_id
  OK  conflict is content-addressable: re-promoting all 5 rows → all noop
  OK  builder: output is stable across a no-op re-promote round
==============================================================
  WO-13 Phase 8 B1 — ALL CONFLICT ASSERTIONS PASSED
==============================================================
```

## 3. B2 — Flag-flip mid-session additivity

Fixture: Ada Lovelace, legacy blob + one promoted protected field
(`preferredName="Ada"`) + one promoted free-form field (`employment`
with qualification `"Exact dates of the collaboration are disputed."`).

B2 makes four reads in a row, flipping `HORNELORE_TRUTH_V2_PROFILE`
between every call, and asserts the schema-additivity contract of the
profile endpoint:

```
read #1: flag OFF        → source='legacy',         no sidecar keys
read #2: flag ON         → source='promoted_truth', sidecar keys present
read #3: flag OFF        → source='legacy',         no sidecar keys
read #4: flag ON         → source='promoted_truth', sidecar keys present
```

The strict contract:

```python
ALLOWED_SIDECAR_KEYS = {"_qualifications", "truth"}
```

Every legacy key present in the flag-off read must be present in the
flag-on read with the same Python type. The only permitted *additions*
are keys in `ALLOWED_SIDECAR_KEYS`. Any other drift — a new top-level
key, a type change, a dropped legacy field — is a failure.

Fourteen assertions cover:

- Schema additivity (OFF→ON): every OFF key present in ON, types
  invariant, only `_qualifications` and `truth` added
- **Byte-identical OFF shape** across read #1 and read #3. If the flag
  ever mutated FT tables on a read, this would fail.
- **Deterministic ON shape** across read #2 and read #4. Same input,
  same output.
- `kinship` + `pets` byte-identical across all four reads
- Envelope invariance: every response carries
  `{person_id, profile, updated_at, source}`
- **FT snapshot unchanged**: `_ft_snapshot` measures
  `(notes, rows, promoted)` counts before the first read and after the
  last one. Both must match — the flag-gated builder is a pure read.
- `source` field transitions exactly `legacy → promoted_truth → legacy →
  promoted_truth`
- Value precedence sanity check: Ada's `preferred='Ada'` in both shapes
  (B1 covers the disagreement case; B2 covers the agreement case)
- Machine-readable trace at `phase8_b2_flagflip_trace.json`

```
==============================================================
WO-13 Phase 8 B2 — flag-flip mid-session schema additivity
==============================================================
  OK  seed: Ada with legacy basics + 1 protected + 1 free-form promoted row
  OK  FT snapshot: notes=2 rows=2 promoted=2 (baseline)
  OK  flag OFF (1st read): source='legacy', no sidecar keys
  OK  flag ON: source='promoted_truth', both sidecar keys populated
  OK  transition OFF→ON is strictly additive: legacy keys preserved, types invariant
  OK  flag OFF (post-rollback): source='legacy', sidecar keys cleared
  OK  flag flip is read-only: OFF shape is byte-identical before and after ON
  OK  rapid flip: two ON reads are byte-identical (deterministic)
  OK  kinship + pets are invariant across all four flag transitions
  OK  envelope: all 4 responses carry {person_id, profile, updated_at, source}
  OK  FT snapshot unchanged: notes=2 rows=2 promoted=2 (no side effects)
  OK  value precedence: preferred='Ada' in both (B1 tested disagreement)
  OK  source envelope: legacy → promoted_truth → legacy → promoted_truth
  OK  trace: saved to phase8_b2_flagflip_trace.json
==============================================================
  WO-13 Phase 8 B2 — ALL FLAG-FLIP ASSERTIONS PASSED
==============================================================
```

## 4. B3 — `lvxRefreshProfileFromServer` shim contract

Phase 8 introduced a single client-side refresh shim in `ui/js/app.js`
that `wo13-review.js` calls after a successful promote. The shim is the
*only* way downstream UI surfaces (profile form, obituary identity
card, memoir source name, timeline spine, session payload) learn about
promoted truth without a manual page reload. Any regression here is
silent: the promote would succeed, the review queue would clear, and
the narrator's profile card would just be stale.

B3 slices the shim function text out of `app.js` at test time (by
walking braces from the known start marker) and runs it inside a Node
`vm` sandbox with mocked `fetch`, `API`, `state`, `normalizeProfile`,
`localStorage`, `document`, `hydrateProfileForm`,
`updateObitIdentityCard`, `renderTimeline`, and `ctype`. Because the
shim is extracted from the live file rather than copy-pasted, any edit
to `app.js` that breaks the markers surfaces as an explicit failure.

Thirty-six assertions cover:

- **Happy path** (10 assertions): fetches `GET /api/profiles/42`,
  normalises the payload onto `state.profile`, writes
  `lorevox_offline_profile_42` to localStorage, calls
  `hydrateProfileForm` exactly once, passes basics to
  `updateObitIdentityCard`, sets `memoirSourceName.textContent` from
  the preferred name, calls `renderTimeline` exactly once, POSTs
  `{conv_id, payload: {profile, person_id}}` to `SESS_PUT`, zero
  warnings emitted.
- **Falsy pid** (4): `null`, `undefined`, `0`, `""` all short-circuit
  before any fetch.
- **Non-OK profile response** (5): `r.ok === false` is a silent return —
  `state.profile` untouched, no DOM side effects, no session POST, no
  warning.
- **fetch throws** (4): caught via the outer try/catch, one warn
  emitted, error never propagates, `state.profile` stays null.
- **localStorage throws** (6): inner try/catch absorbs the throw; rest
  of the pipeline still runs (hydrate + obit + timeline + memoir name +
  session POST), no warning surfaced.
- **No conv_id** (4): pipeline runs, session POST is skipped.
- **Memoir name fallback** (2): falls back to `fullname` when preferred
  is absent, then to `"No person selected"` when both are empty.
- **Payload shape tolerance** (1): accepts both `{profile: {...}}`
  wrapper and bare `{basics, kinship, pets}` object — matches the
  shim's `j.profile || j || {}` code.
- **wo13-review.js wiring** (1): regression string check that the
  call site in `wo13-review.js` still references
  `lvxRefreshProfileFromServer`.

```
==============================================================
WO-13 Phase 8 B3 — lvxRefreshProfileFromServer shim test
==============================================================
  OK  slice: extracted 1050 chars of shim source from app.js
  OK  happy: fetched GET /api/profiles/42
  OK  happy: state.profile normalised and populated
  OK  happy: localStorage snapshot written under lorevox_offline_profile_42
  OK  happy: hydrateProfileForm called exactly once
  OK  happy: updateObitIdentityCard received basics
  OK  happy: memoirSourceName populated from preferred name
  OK  happy: renderTimeline called exactly once
  OK  happy: session POST issued to SESS_PUT
  OK  happy: session POST body carries {conv_id, payload:{profile, person_id}}
  OK  happy: no warnings emitted
  OK  falsy pid: no fetches issued
  OK  falsy pid: no DOM updates
  OK  falsy pid: all falsy values short-circuit
  OK  !r.ok: the profile GET was attempted
  OK  !r.ok: state.profile left untouched (null)
  OK  !r.ok: no hydrate/obit/timeline side effects
  OK  !r.ok: no session POST issued
  OK  !r.ok: no warning emitted (this path is a silent return)
  OK  fetch throws: shim did not propagate the error
  OK  fetch throws: console.warn emitted
  OK  fetch throws: warn message mentions 'refresh profile'
  OK  fetch throws: state.profile left null
  OK  localStorage throws: state.profile still populated
  OK  localStorage throws: hydrate/obit/timeline still ran
  OK  localStorage throws: memoir source name still updated
  OK  localStorage throws: session POST still issued
  OK  localStorage throws: no warning surfaced (inner try/catch)
  OK  no conv_id: state.profile populated
  OK  no conv_id: hydrate/obit/timeline all ran
  OK  no conv_id: session POST was NOT issued
  OK  no conv_id: memoir source name updated
  OK  memoir fallback: uses fullname when preferred is absent
  OK  memoir fallback: default 'No person selected' when both empty
  OK  payload tolerance: bare profile object (no .profile wrapper) accepted
  OK  wiring: wo13-review.js invokes lvxRefreshProfileFromServer
==============================================================
  WO-13 Phase 8 B3 — ALL SHIM ASSERTIONS PASSED  (36/36)
==============================================================
```

## 5. Updated regression matrix

| Phase | Suite | Result |
|---|---|---|
| 4 | `run_phase4_test.py` (facts-write freeze + reference guard) | 18 / 18 PASS |
| 5 | `run_phase5_test.py` (rolling-summary filter, WO-9 legacy drop) | 16 / 16 PASS |
| 6 | `run_phase6_test.js` (review drawer JS + CSS + routing) | 83 / 83 PASS |
| 7 | `run_phase7_test.py` (UPSERT, idempotency, block, bulk) | 23 / 23 PASS |
| 8 base | `run_phase8_test.py` (flag seam, hybrid read, backfill) | 19 / 19 PASS |
| 8 B1 | `run_phase8_b1_conflict_test.py` (precedence on conflict) | **9 / 9 PASS** |
| 8 B2 | `run_phase8_b2_flagflip_test.py` (flag-flip additivity) | **14 / 14 PASS** |
| 8 B3 | `run_phase8_b3_shim_test.js` (refresh shim contract) | **36 / 36 PASS** |

**Total: 218 / 218** across eight suites with both flags OFF by default.

## 6. What B gates for A

With B green, the Kent dry run can proceed with high confidence in
exactly the three places that would have hurt most:

1. **Kent's legacy blob is not known to be correct.** B1 proves that
   whatever he reviews and approves will win over whatever is sitting
   in his `profile_json` today, on every protected field, and that the
   partial review case is also covered.
2. **The flag can be flipped on for Kent and nothing else.** B2 proves
   the flag is a pure read — flipping it on one narrator's process
   leaves the FT tables, the kinship/pets passthroughs, the envelope
   shape, and every other narrator's view of the world untouched.
3. **Promoting through the review drawer will actually update Kent's
   profile card without a reload.** B3 proves the refresh shim
   re-populates every downstream surface correctly, swallows network
   and storage errors without breaking the pipeline, and is still
   wired into `wo13-review.js`.

## 7. Files in this proof

- `PHASE8_B_PROOF.md` — this document
- `../wo13_test/run_phase8_b1_conflict_test.py` — B1 harness (9 assertions)
- `../wo13_test/run_phase8_b2_flagflip_test.py` — B2 harness (14 assertions)
- `../wo13_test/run_phase8_b3_shim_test.js` — B3 harness (36 assertions)
- `../wo13_test/data/phase8_b2_flagflip_trace.json` — B2 machine-readable trace

## 8. Next

**A — Kent dry run.** Backfill Kent with `POST /api/family-truth/backfill`,
walk the review queue, approve the five protected fields, click
"Promote approved", watch the refresh shim repopulate his profile card,
obit card, memoir source name, and timeline, flip
`HORNELORE_TRUTH_V2_PROFILE=1` in his process, verify
`source='promoted_truth'` on the endpoint, and keep the legacy-fallback
escape hatch one env-var-unset away.

**C — Write `OPERATOR_RUNBOOK.md` from the observed A reality**, not
from theory. Everything that was awkward, slow, or surprising during
Kent's dry run gets captured there so the rollout to subsequent
narrators is mechanical.
