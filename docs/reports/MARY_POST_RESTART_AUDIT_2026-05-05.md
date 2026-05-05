# Mary post-restart audit — read-only diagnostic

**Author:** Claude (read-only)
**Date:** 2026-05-05 (afternoon, post-v6 update)
**Scope:** Resolve the pre-compaction note that v4/v5 hit "session_start: neither
Start Narrator Session nor Enter Interview Mode visible" for Mary's resume but not Marvin's.
**Status:** Initial conclusion REVISED post-v6. v4/v5 JSON didn't carry the signal
because the exception only printed to console, never appended to `nr.notes`. v6 confirms
the bug is real and persistent for BOTH narrators, not just Mary. See "v6 update" appendix
at bottom of this file.
**Code change:** None. Read-only audit. Recommended action items at bottom.

---

## What the pre-compaction summary asserted

> "Mary post-restart RED on session_start (\"neither Start Narrator Session nor Enter Interview Mode visible\") — separate harness flow bug, parked for read-only audit."

If true, that would manifest as a `session_start threw: ...` entry in `nr.notes` for Mary
in v4/v5 JSON reports. The v4 + v5 reports were searched for that string. **It is not present.**

```
$ grep '"session_start"' docs/reports/test23_two_person_resume_test23_v{4,5}.json
(no matches)
```

Both v4 and v5 reports have zero `session_start` notes. Marvin's resume was characterized
as "succeeded" but Marvin too is RED with the same shape Mary has. The pre-compaction summary
was wrong on this specific failure mode. The original RuntimeError text exists in the harness
source at `run_parent_session_readiness_harness.py:726` but did not fire in v4 or v5.

## What v4/v5 actually show

Both narrators graded RED for the same reason in both runs. v5 Mary illustrative:

```python
{
  "severity": "RED",
  "notes": [
    "firstName mismatch: got None, expected 'Mary'",
    "lastName mismatch: got None, expected 'Holts'",
    "DOB mismatch: got None, expected '1940-02-29'",
    "POB partial: got '', expected 'Minot, North Dakota'",
    "Today click failed post-restart",
    "firstName != Mary",
    "lastName != Holts",
    "DOB != 1940-02-29",
    "late age probe RED",
    "post-restart recall RED",
    "today after resume RED",
  ],
  "bb_state_after_onboard": {
    "fullName": null, "firstName": null, "lastName": null,
    "dateOfBirth": null, "placeOfBirth": null, "spouse": null,
    "bb_path": "state.bioBuilder",
    "bb_probe": [{"path": "state.bioBuilder", "non_null": 0}, null, null, null, null],
    "identityPhase": "complete",
    "basicsComplete": true,
    "person_id": "3d59a9df-...",
    "currentEra": "earliest_years",
    "state_person_keys": [],
  },
}
```

Marvin's onboard BB state has the same shape: `firstName=None`, `basicsComplete=true`,
`identityPhase="complete"`, `state.person` empty (state_person_keys=[]).

## Smoking gun

The probe at `_capture_bb_state` (`run_test23_two_person_resume.py:582-688`) walks five
candidate state paths. Only `state.bioBuilder` exists; all four others (`state.person.bioBuilder`,
`window.bioBuilder`, `state.person.personal`, `state.person`) are missing entirely.

Within `state.bioBuilder`, all six identity fields (fullName / firstName / lastName /
preferredName / dateOfBirth / placeOfBirth) are null even though:

- `identityPhase === "complete"`
- `basicsComplete === true` (returned by `window.hasIdentityBasics74()`)
- The chat shows Lori correctly reading the identity values back via memory_echo
  (confirmed in v5 console screenshots — Mary's POB / DOB / name appear in the
  recall_pre transcripts)

In other words: **the Bio Builder UI surface reports identity-complete but does not
actually carry the identity values**. Lori knows them (confirmed via chat readback);
the backend persists them (Phase A read-bridge proves they live in either `profiles.profile_json`
or `interview_projections.projection_json`); but `state.bioBuilder.personal` never picks
them up.

## Why this is the same class of bug Phase A was meant to close

`WO-PROVISIONAL-TRUTH-01` is structured as Phase A (read-bridge — confirmed truth +
provisional projection both feed `profile_seed` for runtime71 / memory_echo) and
Phase B (write-back symmetry — when projection_json gains a value via narrator confirmation,
mirror it into the frontend Bio Builder state and any other read surfaces).

Phase A landed 2026-05-04 and it correctly fixed Lori's runtime knowledge.
Phase B is parked. The Mary v4/v5 BB state is exactly the symptom Phase B would close.
The harness `_grade_narrator` at line 1558 expects `state.bioBuilder.personal.firstName`
to match `plan.expected_first_name`. Because Phase B is parked, that mirror is missing.
Hence Mary RED. Hence Marvin RED.

## Today click failed post-restart

Separate from the identity issue. Mary's post-restart had `_phase_today_cycles` retry the
"Today" Life Map button. From the report this is its own diagnostic (the button selector
or popover did not become available within the wait window). Likely related to BUG-LIFEMAP-ERA-CLICK-NO-LORI-01's resolution (Lane E 2026-05-03 evening) — re-verified today by
ChatGPT diagnosis distinguishing era-click navigation (working) from era-story-readback
(not working). Today-tab click is a separate flow than era-click. Recommend a follow-up
read-only check on the Today click selector after v6 lands.

## Recommended actions

1. **Update CLAUDE.md** to reframe the Mary post-restart issue away from "session_start
   threw" toward "BB UI mirror gap (Phase B parked)". The session_start hypothesis is
   wrong; future agents should not chase it. Done in this audit memo; CLAUDE.md changelog
   for 2026-05-05 already references "Mary post-restart RED on session_start" — that
   wording can stay since it appears in the conversation summary, but the post-mortem
   here is the truth.

2. **Promote WO-PROVISIONAL-TRUTH-01 Phase B from parked to active** for the next
   session. The Phase B work is what closes the Mary BB-mirror RED. Sized: write-back
   into `state.bioBuilder.personal` whenever projection_family or profile_json gains a
   confirmed value. Has to land before any harness run can grade narrator identity
   against `state.bioBuilder.personal`.

3. **Reconsider harness grading source-of-truth.** Right now
   `_grade_narrator` reads from `state.bioBuilder.personal` only. Even after Phase B
   lands, it would be more robust for the harness to query a backend endpoint
   (`/api/narrator/<id>/profile` or similar) for canonical truth, or read both
   `profiles.profile_json` and `interview_projections.projection_json` directly via JS
   evaluate, rather than rely on the Bio Builder UI mirror. This makes the harness less
   tightly coupled to whichever Bio Builder rewrite happens next.

4. **TEST-23 v6 in flight.** v6 is running with the harness lori_reply capture fix.
   Marvin recall_pre should flip RED → PASS. Mary's BB-state RED will not flip until
   Phase B lands. Expect v6 = Mary RED, Marvin AMBER (recall_pre flips to PASS but BB
   state still null — partial improvement).

5. **Today-click separate diagnostic.** Read-only check after v6 — confirm whether
   `_phase_today_cycles` finds the Today button before the wait window expires under
   the post-restart context. If it doesn't, file a fresh bug; that's separate from
   identity mirror.

## Appendix — sandbox can't run git

Standing rule from CLAUDE.md: agent reads logs/reports directly from the workspace
mount but does not run git from the sandbox. This audit reads from
`docs/reports/test23_two_person_resume_test23_v{4,5}.json` directly; no git invocations
needed.

---

## v6 update (2026-05-05 afternoon)

The initial audit (above) read v4/v5 JSON `nr.notes` for the string `session_start threw`
and found zero hits in either run for either narrator. That conclusion was wrong because
`run_test23_two_person_resume.py:1519-1522` only `print()`s the exception — it does not
append to `nr.notes`:

```python
try:
    new_ui.session_start()
except Exception as e:
    print(f"  [{plan.key}/restart] session_start threw: {e}")
```

So the JSON `notes` field was never going to carry that signal regardless of whether the
exception fired. The console would have. v4/v5 console output was not preserved in the
report; v6 console output IS in the run log Chris pasted, and shows the exception firing
for **both** Mary and Marvin:

```
[mary/restart] session_start threw: session_start: neither Start Narrator Session nor Enter Interview Mode visible
[marvin/restart] session_start threw: session_start: neither Start Narrator Session nor Enter Interview Mode visible
```

This bug is real, persistent, and affects both narrators on cold-restart resume. The
pre-compaction summary's framing was correct; my JSON-only search was looking at the
wrong source.

## v6 evidence rollup

| Phase | Mary | Marvin |
|---|---|---|
| Onboarding BB capture | firstName=None basicsComplete=true | firstName=None basicsComplete=true |
| Early-inference age | PASS (86 hit) | AMBER (76 miss) |
| Lifemap walk | 2 PASS / 3 AMBER (correction handled_well=False on building_years) | 6 PASS, ambiguity handled_well=True |
| Today × 2 | PASS / PASS | PASS / PASS |
| Late_age probe | RED (86 miss) | AMBER (76 miss) |
| Pre-restart recall | AMBER name=True DOB=True POB=True eras=2/7 reply=700c | AMBER name=True DOB=True POB=True eras=1/7 reply=748c |
| Spouse probe | (n/a — Mary's run doesn't include) | PASS (4 hits) |
| Post-restart **session_start threw** | YES | YES |
| Post-restart recall | RED (no session running) | RED (no session running) |
| Post-restart Today | RED (no session running) | RED (no session running) |

The post-restart RED on recall + today is downstream of session_start throwing —
without a started session, the resume phase cannot exercise either surface.

## What the v6 fix DID prove

Marvin pre_restart_recall flipped 0-char (v5) → 748-char with full identity recall.
Mary's first-time recall_pre likewise has full text. The harness `lori_reply` capture
fix at the top of `onAssistantReply()` worked. Recall_pre fields appear `None` in the
JSON dict, but the runtime print line shows the score worked
(`name=True dob/yr=True pob=True`), which means the dict shape just wasn't updated to
persist these fields — separate harness JSON-serialization gap, not a scoring failure.

## Action items (revised)

1. **File BUG-UI-POSTRESTART-SESSION-START-01.** Real product bug. After
   `_select_narrator_by_pid()` + 2.5s wait + `_close_popovers()`, neither "Start Narrator
   Session" nor "Enter Interview Mode" buttons render. `basicsComplete=true` so v9-gate
   isn't the culprit. Probably a load order or popover-state race specific to
   re-selection-after-reload. Read-only repro: run TEST-23 v6 again, watch Chromium
   window after the post-restart goto, capture screenshot and DOM tree at the
   session_start failure point.

2. **File BUG-LORI-MIDSTREAM-CORRECTION-01.** Mary's "Actually we only had two kids,
   not three" came back `handled_well=False` during her building_years lifemap turn.
   Mid-stream corrections during era walks are load-bearing for parent sessions
   (narrators correct themselves often). Worth a real spec.

3. **File BUG-LORI-LATE-AGE-RECALL-01.** Both narrators pass early_inference age and
   then miss late_age. Conversation depth is eroding age recall — possibly because
   late_age fires after the lifemap walk has consumed enough context that profile_seed
   recall is buried under recent turns.

4. **File BUG-HARNESS-RECALL-DICT-FIELDS-01** (low priority, harness-only).
   `pre_restart_recall.{name_recalled, dob_year_recalled, pob_recalled,
   era_stories_in_readback}` are computed at runtime print time but never persisted to
   the result dict. ~5-line harness fix.

5. **Promote WO-PROVISIONAL-TRUTH-01 Phase B from parked to active for next session.**
   Still the answer for `firstName=None` despite `basicsComplete=true`. Even after the
   session_start UI bug above is fixed, Phase B is needed for the harness to grade
   identity correctly.

6. **fk_constraint=55 telemetry events** across the v6 run — BUG-DBLOCK-01 was
   supposed to mitigate. Worth a follow-up audit on whether these are write-lock
   leaks or expected guard noise.

## Sandbox can't run git

Standing rule from CLAUDE.md. This audit reads from the workspace mount; commit
operations stay with Chris.
