# Phase 1d — Unit 1: live browser inventory

**2026-08-09 · READ-ONLY.** Nothing written, cleared, migrated or edited. No narrator turns.

**Scope discipline for this report:** it records **what was observed in one browser store at
one moment**. It deliberately makes no claim about other machines, other profiles, or earlier
points in time. Two claims in the first draft crossed that line and are corrected at the end.

---

## What was observed

**Store identity confirmed.** The key list read from Chris's own DevTools console is
byte-identical to the list read through the extension, including
`lv_csm:d56900b5-3dda-4f44-b419-4891e1683007`. **Same browser store.** The earlier "wrong
Chrome profile" theory is retired.

**At inspection time, in that store:**

```text
TOTAL = 14      QC_KEYS = 0      lorevox.spine.* = 0
```

**Absent from this store at inspection time:** `lorevox_qc_draft_*`, `lorevox.spine.*`,
`lorevox_ft_draft_*`, `lorevox_lt_draft_*`, `lorevox_qq_draft_*`, `lorevox_proj_draft_*`,
`lorevox_sources_draft_*`, `lv_done_*`, `lv_segs_*`, `lorevox_offline_profile_*`,
`lorevox_facial_consent*`.

**Present — the 14 keys:**

| key | category |
|---|---|
| `hornelore_session_style_v1`, `lv_session_style` | A — session style |
| `lv_csm:d56900b5-…` | A — cognitive-support mode, Melanie |
| `ma_narrator_id_v1`, `pi_narrator_id_v1`, `trip_tab_narrator_id_v1`, `trip_tab_trip_id_v1` | A — per-surface destination identity |
| `ma_curator_user_id_v1`, `pi_curator_user_id_v1` | A — operator attribution |
| `hornelore_deleted_labels`, `lorevox_offline_people` | A — narrator list / labels |
| `lv74_cam_preview_size`, `lvTravelDocSurface`, `tdlRailCollapsed` | C — cosmetic |

11 of 14 category A, 3 cosmetic. None is a draft, a spine, a consent record or a
sensitive-segment decision.

---

## What follows, stated no wider than the evidence

1. **There is no current Quick Capture material to rescue from this browser.** That reduces
   the immediate data-rescue risk substantially.
2. **There is no current `lv_segs_` browser blob to compare against the 9 `segment_flags`
   rows.** Unit 2's comparison has no browser-side input at present.
3. **There is no current facial-consent value in this store to rescue.**

## What does NOT follow, recorded explicitly so it is not assumed later

- **Not proven: that Quick Capture never existed.** Another machine, another profile, or this
  profile before a clean-restart purge could have held one. The goal is removing browser
  persistence entirely, so the scope of this finding must stay accurate.
- **Not proven: that a cached spine did not cause the observed `pass2a`.** Absence now is not
  absence then. A spine key could have existed when the pass was assigned and been removed
  since — by a cleanup path, a narrator switch, or a purge. **The causal question moves to
  Unit 6 and must be answered by tracing setters, not by inferring from a current absence.**
- **Not proven: that browser/server segment divergence is impossible.** The browser
  persistence code path in `safety-ui.js` is live and would write `lv_segs_` again on the next
  sensitivity decision, and the per-person vs per-session grain mismatch with `segment_flags`
  is unresolved regardless of today's emptiness.
- **Not proven: that consent has never been granted in a browser.** `facial-consent.js` still
  writes on grant; emptiness today is a statement about this store's history, not about the
  code.

**The general form, which is the lesson worth keeping:** *the writers all still exist.* An
empty store describes history, not behaviour. Granting consent, opening a narrator with a
spine, or making a sensitivity decision tomorrow recreates these keys.

---

## Effect on the plan

The immediate **data-rescue** risk for this browser is much lower than assumed, which is good
news for Phase 6. It does **not** reduce the **code** work: every browser-authoritative path
identified in Phases 0–1c is still present and still needs removing.

**Unit 6 gains scope.** It is no longer only *"determine the deterministic server progression
condition."* It must also:

- trace **every** `setPass("pass2a")` caller — `app.js:3394`, `app.js:7694`,
  `life-map.js:493/549/611/791`, `interview.js:43/850`, `chronology-accordion.js:216`;
- determine which path establishes the **live** narrator's effective progression;
- determine whether any persistence or cleanup lifecycle could explain the current no-spine
  state alongside a `pass2a` reading.

---

## Remaining Phase 1 units

| unit | status |
|---|---|
| 1 — live browser inventory | ✅ **complete, this report** |
| 2 — `lv_segs_` browser vs server | 🟡 **no browser-side input at present**; code path and grain mismatch still open |
| 3 — consent callers / writers | ✅ Phase 1c |
| 4 — voice capture / persistence truth chain | not started |
| 5 — writer + reader + shape for each HYPOTHESIS mapping | not started |
| 6 — progression: server condition **+ every `pass2a` setter + lifecycle** | not started, scope expanded |
| 7 — final owner/migration map and minimal deltas | not started |

---

## Corrections to earlier reports

| claim | status |
|---|---|
| "wrong browser profile" (previous session) | **withdrawn** — key lists byte-identical; same store. |
| "Quick Capture is empty. The highest-risk unknown in the whole audit is retired." (first draft of this report) | **overreach — corrected.** Proven: no Quick Capture key in this store at inspection time. Not proven: that none ever existed anywhere. |
| "There is no spine key at all — so your `pass2a` did NOT come from a cached spine." (first draft) | **overreach — corrected and moved.** Absence now does not establish absence then. The causal question belongs to Unit 6. |
| "With zero `lv_segs_` keys … so no divergence" (first draft) | **overreach — corrected.** No current browser value to compare; divergence is not globally excluded. |
| "Chris avoids the conflict because his browser has a cached spine" (Phase 8 §10) | **withdrawn as unproven** — and *not* replaced with the opposite claim. Which setter established `pass2a` is now an open Unit 6 question. |

**Note on the pattern**, since it has now cost three claims in two reports: each error took an
observed absence and promoted it to a universal or causal statement. The evidence standard
that keeps catching this is worth more than any individual finding — including a clean one.
A good result is exactly when it is easiest to relax it.
