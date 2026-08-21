# Profile Seed ownership — decision brief

> ## SUPERSEDED — 2026-08-20 · Profile Seed
>
> **The Profile Seed instruction in this document is SUPERSEDED and must not be
> built from.** Whatever it says below about retiring the ten-topic walk, about
> "Option A, live narrators only", or about Option D remaining live, is retired.
>
> **The settled rule: PRESERVE the ten-topic Profile Seed onboarding for new
> Lorevox narrators REGARDLESS OF NARRATOR TYPE.** The earlier wording read as
> licence to gate that onboarding on narrator type, which would have removed the
> workflow from exactly the narrators it exists for.
>
> **Ordinary new-narrator REACHABILITY remains OWED** and is the next substantive
> lane. It is a separate question from the decision above: the onboarding is
> preserved; whether an ordinary new narrator actually reaches it is not yet
> settled in code.
>
> **This document is design and decision HISTORY, not current build authority.**
> Read it to understand why a subsystem behaves as it does. Do not read it as a
> build queue, and do not resolve a present-day question from it. The body below
> is left exactly as it was written, per this repository's correct-in-place rule.

**Date:** 2026-08-14 · **For:** Chris · **Lane:** Lean Lori, blocking Phase 8's remainder
**Status:** DECISION REQUESTED. **Nothing here is implemented, and this brief does not
authorise implementing it.**

---

## 0. A naming trap to clear first

The repository uses "profile seed" for **two unrelated things**. A decision that conflates
them will retire the wrong one.

| Name | What it is | Where |
|---|---|---|
| **`profile_seed`** (the data dict) | A 9-bucket read-only summary of what is already known about the narrator, built server-side. It exists so Lori does **not** re-ask known facts. | `prompt_composer.py:865` `_build_profile_seed()` |
| **"Pass 1 — Profile Seed"** (the directive) | A hard-coded **10-question questionnaire walk** emitted when `current_pass == "pass1"`. | `prompt_composer.py:4344` (gate), `:4386-4418` (text) |

**This brief is about the second.** The first is anti-questionnaire machinery and should be
kept.

---

## 1. The decision in one sentence

**On an ordinary oral-history turn for an identity-complete narrator, which single authority
speaks — and does the Pass 1 questionnaire walk reach that turn at all?**

---

## 2. The competing authorities

All three are appended to the same directive list and ship in one prompt, in this order:

| # | Authority | Cost | Where | Asserts |
|---|---|---:|---|---|
| 1 | `LORI_INTERVIEW_DISCIPLINE` | 2,899 tok | defined `prompt_composer.py:1368`, appended **unconditionally** `:3970` | "You are an oral-history interviewer, not a questionnaire menu." |
| 2 | `LORI_ORAL_HISTORY_RESPONSE` | 273 tok | defined `:1787`, appended `:4008`, gated on session style | "THE NARRATOR LEADS, YOU FOLLOW." |
| 3 | **Pass 1 Profile Seed walk** | — | gated `:4344` `if current_pass == "pass1"`, text `:4386-4418` | *"GOAL: Gather the following 10 facts, one per turn."* |

**(3) is a questionnaire walk; (1) and (2) exist to say Lori is not that.** This is not token
duplication — it is three generations of Lori behaviour instructing the model differently on
the same turn, with the newest two arguing against the oldest.

Authority 2's own source concedes the layering: `:3975` — *"overrides the question-cadence
guidance from LORI_INTERVIEW_DISCIPLINE"*; `:1775` — *"ADDITIVE to LORI_INTERVIEW_DISCIPLINE"*.

**A fourth authority exists that the Phase 8 report does not name.** The early-return
questionnaire path at `:3955-3957` returns before 1–3 are reached. That is the onboarding
lane `WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01` retired for live narrators. **Authority (3) is
a second, surviving copy of the same shape on the interviewer path** — which is the strongest
argument that its survival is an oversight rather than a design.

### 2.1 Standing rules this sits against

- `CLAUDE.md` design principle 8: *"If the operator seeded it, Lori knows it. If Lori knows
  it, she does not ask for it as intake."*
- `WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01` retired exactly this shape on the live path.

---

## 3. Who owns `current_pass` today — nobody, in three places

| Authority | Where | Behaviour |
|---|---|---|
| Browser session state | `state.js:127` (init `"pass1"`), setter `:568` | The canonical store |
| The composer's own default | `prompt_composer.py:3693` | `runtime71.get("current_pass", "pass1") or "pass1"` — the `or` also converts explicit `null`/`""` to `"pass1"` |
| A parallel derivation | `app.js:4713` `getEffectivePass74()` | Sent as a **separate** field `effective_pass`; composer re-derives at `:3717` |

**A split that matters:** `identity_mode` is computed from `effective_pass` (`:3718`), but the
Pass 1 seed block is gated on `current_pass` (`:4344`). **Two different fields decide adjacent
behaviours.**

### 3.1 The promotion is welded to a browser cache

```
app.js:3381   const _cachedSpine = loadSpineLocal(pid);      // localStorage
app.js:3382   if (_cachedSpine) {
app.js:3394       if (state.session.currentPass === "pass1") setPass("pass2a");
```

`pass1 → pass2a` happens **only if a locally cached timeline spine exists.** So:

- a new narrator, a cleared browser, or a different machine **stays on `pass1`**;
- `_KNOWN_NON_ORAL_STYLES` contains neither `""` nor `oral_history`, so an unset style takes
  the oral-history posture;
- **therefore a new narrator on the default style, on a machine with no cached spine, receives
  all three authorities on every turn.**

That is *"a narrator's first sessions"* — the situation the system most cares about. It is not
reachable in Chris's own session (`pass2a`, `clear_direct`), which is why it went unnoticed.

---

## 4. Readers and writers

**Writers of `current_pass`:** `state.js:127`, `state.js:568` (`setPass`, the only intended
mutator), `app.js:3497` (**a direct write that bypasses `setPass`**), `app.js:3394`,
`app.js:7694`, `interview.js:43/850/851`, `life-map.js:493/549/611/791`,
`chronology-accordion.js:216`, and the server-side default injection at
`prompt_composer.py:3693`.

**Readers:** `app.js:2866/2894/4718/7744`, `state.js:542`, `cognitive-auto.js:87`,
`interview.js:1308` (**sends `null`, not `"pass1"`**), `prompt_composer.py:3693/3754/4344/4419/4500`,
`chat_ws.py:859/4273`, `turn_extraction.py` (12 sites), `extract.py:75/3203` — where it is
**explicitly discarded** at `:3226-3232` because the #95 matrix found pass carries zero signal
for extraction.

**Writers of the `profile_seed` dict:** `prompt_composer.py:865` (server build),
`chat_ws.py:3574-3578` (**server overwrites the runtime71 field it received**),
`people.py:490-504` and `bio_questionnaire_writer.py:141-142` (intake mirrors), and
`app.js:4741-4752` (UI, all-null).

> **Defect found while tracing, reported not fixed.** `app.js:4738-4740` says the UI object
> *"records which of the 10 seed questions have been answered … true = answered"*. **No code
> anywhere sets a bucket to `true`.** The UI-side tracker is write-once-null and dead; the
> composer's *"skipping what you already know"* (`:4397`) is served entirely by the
> server-built seed. Low risk, but it is a comment asserting behaviour that does not exist.

> **Second finding:** the Pass 1 directive does **not** read `profile_seed` at all. It builds
> its own `_known_facts` from `speaker_name`, `dob`, `pob`, `projection_family`
> (`:4347-4385`) — **a third independent notion of "what Lori already knows."**

---

## 5. Consequences for cache refresh

Decided in one block, `app.js:3380-3395`.

**Invalidates the cached spine:** narrator delete (`app.js:3827`); stale-narrator startup
sweep (`app.js:2332`); harness teardown (`test-harness.js:368`); a profile save that re-runs
`initTimelineSpine()` (overwrites rather than invalidates).

**Does NOT invalidate it — the load-bearing list:**

- **Narrator switch deliberately preserves it** (`app.js:2368-2370`, documented in-source).
- **Nothing server-side can invalidate it.** It is browser-local, per-origin, per-device. No
  version stamp, no TTL, no schema version, no round-trip. `saveSpineLocal` swallows quota
  failures silently (`state.js:523`).
- **Changes to the server `life_spine/` package have zero effect** on any browser's cache.
  Two systems named "spine", no shared state.

**The consequence for this decision:** cache presence does double duty — a *rendering* cache
for the timeline **and** the sole trigger for the pass promotion, welded at `app.js:3394`.
**Any future change that clears spine caches silently demotes every affected narrator back to
`pass1`** and re-arms the conflict, with no server-side signal. Conversely one narrator can be
`pass2a` on one machine and `pass1` on another at the same time.

---

## 6. Consequences for export

**Direct: none.** Neither `current_pass` nor `profile_seed` reaches memoir export, the trip
DOCX, or the archive. `archive.append_event` takes `current_era` and **only** `current_era`
(`archive.py:133/141-146/191-194`); every `chat_ws` call site passes `current_era=` and
nothing pass-related. Extraction is the only lane that carries `current_pass` off the turn,
and it discards it.

**Indirect, and this is the part that matters.** The seed walk changes *what Lori asks*, which
changes *what the narrator says*, which is what extraction captures, what archive stores and
what export renders. **A narrator stuck on `pass1` produces ten turns of questionnaire answers
instead of ten turns of narrative.** That is permanent in the archive and therefore in the
memoir, and it is invisible to any export-side audit **because the pass label was never
recorded alongside the content**.

**Rolling back the seed walk cannot repair archives written while it was live, and nothing
marks which turns those were.** That asymmetry is the strongest argument for deciding sooner
rather than later.

---

## 7. Rollback implications

**There is no DB column, no server flag and no per-narrator setting that controls
`current_pass` today. Its only durable home is `localStorage`.** So a pass-ownership change
**cannot be rolled back server-side** as the system stands — the server holds no persisted
opinion about any narrator's pass.

Controls that do exist and could carry a decision without inventing a column:

| Control | Reader | Reverses |
|---|---|---|
| `people.narrator_type` | `db.py:2106`, enforced at 4 sites | The one durable, server-side, per-narrator, reversible switch in this area |
| `HORNELORE_COMMUNICATION_CONTROL` | `chat_ws.py:4672`, default OFF | The runtime question-count/word cap — the only runtime counterweight to a questionnaire walk |
| `HORNELORE_REFERENCE_NARRATORS` | `db.py:424-428` | Which narrators are reference-typed |
| `lorevox.spine.<pid>` | `state.js:518` | Today's de-facto pass control, in both directions — but manual and per-device |

**Do not propose `HORNELORE_RUNTIME_PROFILE`** — zero readers repo-wide.

> **A trap worth naming: `HORNELORE_INTERVIEW_DISCIPLINE` looks like the rollback control for
> authority (1) and is not.** It is read at `prompt_composer.py:1875` inside
> `_discipline_filter_enabled()`, and **that function has no callers.** It also does not gate
> what its name suggests — the Layer-1 prompt block at `:3970` is unconditional. The flag's
> default is documented inconsistently (`:1875` default `"1"`; `chat_ws.py:4567` says
> "off-by-default, opt in"). Three reports still reference it as live. **Reported as a
> disagreement; not resolved here.**

---

## 8. Recommendation

**Recommended owner: authority (1) + (2) — the oral-history posture. Retire authority (3)
from the interviewer path.**

Reasons, in order of weight:

1. Authority (3) is a **surviving second copy** of a shape already retired on the live path by
   `WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01`. The retirement was a product decision that this
   path silently escaped.
2. It contradicts `CLAUDE.md` design principle 8 directly, and principle 8 exists precisely to
   stop Lori interrogating narrators for facts the system already holds.
3. It reaches **new narrators first** — the population least able to absorb an interrogation
   cadence, and the one the north-star statement names.
4. The `pass2a`/`pass2b` rows are already ~310 tokens cheaper *because* the seed block is
   absent; the desired end state is already the measured normal case.
5. Its damage is **archived and unrepairable**; the fix's cost is a gate change.

**What I am NOT recommending, and why.** Not compaction of `LORI_INTERVIEW_DISCIPLINE` —
shortening it while a contradicting block still ships would make the prompt cheaper and no
clearer, and would destroy the evidence. **Ownership first, then length.** Not building the
Phase 2 profile resolver to hold this decision — that is architectural housekeeping that
improves no narrator turn, and Chris already deferred it.

---

## 9. The exact decision requested

**Answer one question:**

> On an ordinary interviewer turn for an identity-complete narrator, should the Pass 1
> Profile Seed questionnaire walk (`prompt_composer.py:4344-4418`) ship at all?

Choose one:

- **A — Retire it from the interviewer path.** The `current_pass == "pass1"` branch stops
  emitting the 10-question walk; the oral-history posture owns the turn. *(Recommended.)*
- **B — Keep it, and fix the trigger instead.** Make `pass1` unreachable for an
  identity-complete narrator by giving the promotion a durable server-side home rather than a
  browser cache. Larger, and it keeps two authorities arguing.
- **C — Keep it deliberately, and retire authority (2) instead**, accepting a questionnaire
  cadence for first sessions.
- **D — Not yet; gather the live evidence first.** The L2 runbook's `current_pass` capture
  confirms the conflict end-to-end on a real browser. *(This is the default if you say
  nothing, and it is why L2 carries that case.)*

**Second, if A or B:** does the decision apply to all narrators, or only to
`narrator_type='live'` (leaving `reference` narrators on the existing behaviour)?

**Nothing is implemented until you answer.** `LORI_INTERVIEW_DISCIPLINE` stays untouched, and
Phase 8's remainder stays closed, until then.
