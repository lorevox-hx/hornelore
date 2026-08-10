# Browser-persistence ownership census — Phase 0

**2026-08-09 · READ-ONLY. No code changed. No `pass1`, Profile Seed or `pass2a` work done.**

**Scope:** every `localStorage` / `sessionStorage` access in active product code
(`ui/js/*.js`, `ui/*.html`), comment lines excluded.

**Total: 181 accesses across 25 files, resolving to ~40 distinct key families.**

| file | accesses |
|---|---:|
| `app.js` | 57 |
| `bio-builder-core.js` | 34 |
| `hornelore1.0.html` | 13 |
| `facial-consent.js` | 10 |
| `narrator-preload.js` | 9 |
| `ui-health-check.js` · `test-harness.js` · `media-archive.js` | 7 each |
| `trip-tab.js` · `photo-intake.js` | 5 each |
| `projection-sync.js` | 4 |
| 15 further files | 1–3 each |

---

## The single strongest signal in the data

**Roughly half the key families are suffixed with `<pid>` — the narrator's id.**

`lorevox.spine.<pid>` · `lv_done_<pid>` · `lv_segs_<pid>` ·
`lorevox_offline_profile_<pid>` · `lorevox_proj_draft_<pid>` · `lorevox_qq_draft_<pid>` ·
`lorevox_ft_draft_<pid>` · `lorevox_lt_draft_<pid>` · `lorevox_qc_draft_<pid>` ·
`lorevox_sources_draft_<pid>` · `lorevox_facial_consent:<pid>` · `lv_csm:<pid>`

**A key that is namespaced by person is not a preference. It is a record about a person.**
Preferences are per-device; records about a person belong with the person. That naming
convention is the codebase telling us, in its own hand, which keys are category A — and it
means the classification below is mostly mechanical rather than a judgement call.

---

## Classification

### A — durable narrator state. Must become SQLite-authoritative.

| key | owner | what it carries | can it change Lori / product behaviour? |
|---|---|---|---|
| **`lorevox_facial_consent:<pid>`** (+ legacy global `lorevox_facial_consent_granted`) | `facial-consent.js` | **consent to affect analysis, per narrator** | **yes — gates camera/affect entirely** |
| **`lorevox.spine.<pid>`** | `app.js` `LS_SPINE` | timeline spine | **yes — its mere presence promotes `pass1 → pass2a`** |
| `lv_done_<pid>` / `lv_segs_<pid>` | `app.js` `LS_DONE`/`LS_SEGS` | interview section completion / progress | yes — interview progression |
| `lorevox_offline_profile_<pid>` | `app.js`, `narrator-preload.js` | **profile fallback when the API fails** | **yes — identity** |
| `lorevox_offline_people` | `app.js` | people-list fallback | yes — who exists |
| `lorevox_proj_draft_<pid>` | `projection-sync.js` | **projection / provisional truth** | **yes — truth** |
| `lorevox_qq_draft_<pid>` | `bio-builder-*` | Bio Builder questionnaire | yes |
| **`lorevox_ft_draft_<pid>`** | `bio-builder-family-tree.js` | **Family Tree draft** | yes — *see “browser-only” below* |
| **`lorevox_lt_draft_<pid>`** | `bio-builder-life-threads.js` | **Life Threads draft** | yes — *browser-only* |
| **`lorevox_qc_draft_<pid>`** | `bio-builder-core.js` | **Quick Capture** | yes — *browser-only, may hold narrator words* |
| `lorevox_sources_draft_<pid>` | `bio-builder-sources.js` | sources draft | yes |
| `lorevox_draft_pids` | `bio-builder-core.js` | draft index | yes |
| `lv_csm:<pid>`, `lv_cognitive_support_mode`, `lv_csm:_operator_default_` | `app.js` | **cognitive-support mode** | **yes — a care setting about a person** |
| `lv_active_person_v55` | `app.js` | **which narrator is active** | **yes — identity** |
| `hornelore_session_style_v1`, `lv_session_style`, `lv_trip_style` | `app.js`, `session-loop.js`, `travels-shelf.js` | session style | **yes — style selects Lori's posture blocks** |
| `ma_narrator_id_v1`, `pi_narrator_id_v1`, `trip_tab_narrator_id_v1`, `ma_family_line_v1` | media / photo / trip tabs | **per-surface narrator pointers** | **yes — destination identity for imports** |
| `ma_curator_user_id_v1`, `pi_curator_user_id_v1` | media / photo intake | **curator (operator) identity** | **yes — provenance attribution** |
| `hornelore_deleted_labels` | `app.js` | deleted-narrator labels | yes |
| `lvNarratorLocation` | `lori-clock.js` | narrator location | yes — narrator-facing |

### B — operator/device preference. SQLite preference row only if persistence is actually wanted.

`lorevox_device_onboarded` · `lv_oral_history_default_notice_seen` ·
`wo10b_operator_resume_gate` · `lv_trip_confirm_offered_<tripId>`

### C — UI convenience. In-memory only; losing them costs a re-pick.

`lvClockVariant` · `tdlRailCollapsed` · `lv74_cam_preview_size`

### D — dev/debug. Remove, or move to server config / query flag.

`LV_INLINE_OPERATOR_BUBBLES` · `lv_qf_live_ownership` · `hornelore.intake.minimal`

### ⚠️ Contested: capability toggles

`lv_use_whisper_stt` · `lv_mic_modal_enabled`

These look like preferences and are not. **See the finding below.**

---

## Four findings the census produced that the plan did not anticipate

### 1. 🔴 A browser toggle decides what Lori says is true about recording

The live `runtime71` capture contains this, inside `session_style_directive`:

> *"If the narrator asks whether their voice or audio is being recorded, answer based on the
> toggle state: 'Yes, your voice is being saved this session — your voice only, never mine.'
> … NEVER claim capabilities that aren't listed above."*

The toggle state behind that sentence is held in browser storage
(`lv_use_whisper_stt`, `lv_mic_modal_enabled`). So **the answer Lori gives an 86-year-old
about whether they are being recorded is derived from `localStorage`.**

That is a capability-honesty path running through browser state, and capability honesty is
one of the ten behavioural contracts Phase 6 was required to preserve. Whatever else is
staged, **this one should not stay where it is.** It belongs with the session record that
knows what was actually captured.

### 2. 🔴 Consent is stored only in the browser

`lorevox_facial_consent:<pid>` is the record that a narrator agreed to local affect analysis.
**A consent record that exists only in a browser cannot be audited, does not survive a cache
clear, and cannot be produced later as evidence that permission was given.** For every other
category-A item the risk is a wrong answer; for this one the risk is being unable to
demonstrate a person agreed to something.

I would make this the **first** item migrated, ahead of the spine and ahead of progression.

### 3. 🟡 Three keys appear to be browser-only, with no server equivalent

`lorevox_ft_draft_<pid>` (Family Tree), `lorevox_lt_draft_<pid>` (Life Threads) and
`lorevox_qc_draft_<pid>` (Quick Capture) have no obvious counterpart in the API surface.

**Quick Capture is the one to check first, because it may contain narrator words** — and if
it does, there is life-story content that exists in exactly one Chrome profile and nowhere
else. **Nothing may be deleted until each of these is proven either migrated or empty.**

*Stated as a suspicion, not a conclusion:* absence of an obvious endpoint is weak evidence.
Phase 1 should confirm against the API and schema rather than trust this row.

### 4. 🟡 Operator identity is also browser-held

`ma_curator_user_id_v1` / `pi_curator_user_id_v1` carry the curator's identity into media and
photo-intake provenance. That is **attribution data written into the archive**, sourced from
browser storage. It sits oddly beside the Picker doctrine, which is emphatic that identity
must never be inferred and must always be explicit in the request.

---

## What this means for the `pass1` question

**My live capture on 2026-08-09 measured a browser, not a narrator.** It read
`current_pass: "pass2a"` and I reported the Profile Seed conflict as "not occurring in this
session." The correct statement is narrower: *that Chrome profile had a cached spine.* The
same `person_id`, against the same SQLite, answers `pass1` on a machine that does not.

So the Profile Seed investigation cannot be concluded from browser evidence at all, and the
ownership correction is genuinely the predecessor. **`pass1`, Profile Seed and
`LORI_INTERVIEW_DISCIPLINE` stay untouched.**

---

## One scope question for Chris

The evidence establishes decisively that **browser storage must not own narrator semantic
state** — categories A and the two contested toggles.

It does not, by itself, establish **zero `localStorage` anywhere**. Category C is three keys
whose loss costs an operator a re-pick; routing them through the API adds latency and a
failure mode to something that does not matter, and an allow-list pinned at zero would push
cosmetic state into the database for symmetry rather than need.

**Recommendation:** make the hard gate *no product/narrator state in browser persistence*,
with a grep allow-list that may hold category-C and D keys **only**, each with a one-line
justification. Treat *zero localStorage* as a separate preference to decide per key rather
than as the acceptance criterion. If Chris still wants zero, the cost is small — but the two
claims have different evidential strength and the strong one should not carry the weak one.

---

## Proposed sequencing change

The staged plan is sound. One reordering and one guard:

1. **Consent (§2) first**, ahead of the spine — it is the only item where the failure mode is
   *unable to prove a person agreed*.
2. **Capability toggles (§1) second** — Lori is currently making honesty claims from browser
   state.
3. Then progression / spine / projection / Bio Builder as planned.
4. **Phase 2's single hydration boundary behind a flag**, with the existing path intact until
   acceptance passes. "Narrator selection now awaits a server response" changes startup for
   every narrator at once, and this repository's own history says that is where the
   surprises are.

**And one discipline carried from this week:** the audit will surface durable data with no
server owner. **Do not invent tables for producers that do not exist yet** — establish who
writes it before deciding where it lives.

---

## Limits of this census

- It is a **static scan of active product code**. It does not prove which keys hold data on
  Chris's machine today; §3 in particular needs a live `localStorage` enumeration per
  narrator before anything is deleted.
- Test/harness files (`test-harness.js`, `test-bb-walk.js`, `emotion-pipeline-tests.js`) are
  counted in the 181 but are not product paths; they are listed for completeness and should
  be excluded from the eventual gate.
- Category assignments for B versus A are the judgement calls. The `<pid>`-suffixed keys are
  not.
