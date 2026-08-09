# Live stack sweep — 2026-08-09

**Method:** read-only inspection of the running stack (UI on `:8082`, API on `:8000`) from
Chrome, plus read-only queries against `hornelore.sqlite3` (`mode=ro`) and source tracing.
**No narrator turns were sent and nothing was written to any record.** Every probe was a GET.

**Scope note.** This was an exploratory sweep, not an acceptance run. The strongest finding
is a correction to my own earlier work, which is the honest headline: a claim I put in the
Phase 8 reconciliation was wrong, and only the live surface exposed it.

---

## 1. 🔴 The 384-vs-768 compound cap is NOT reconciled, and production runs the bad value

**This corrects `LEAN-LORI-R3-PHASE-RECONCILIATION-2026-08-09.md` §3, item 3.** That report
listed the cap in its **do-not-rebuild** list, saying *"already one source of truth —
`extract.py:1962` defaults to 768."* The default is 768. The deployment is not.

| source | value |
|---|---|
| `server/code/api/routers/extract.py:1962` — code default | **768** |
| `.env:136` `MAX_NEW_TOKENS_EXTRACT_COMPOUND` | **384** |
| **live server, `GET /api/extract-diag`** | **384** |

`extract.py:1956` records why the code default is 768: LOOP-01 R3 raised it **384 → 768**
after api.log evidence showed compound answers *"truncating at the 384 cap, falling to
salvage or zero-item rules fallback."*

**So the running deployment is set to exactly the value the code comment says causes
truncation.** R3 Phase 11's requirement — *"reconcile the documented 384 versus code 768
compound cap from current eval evidence and establish one source of truth"* — is **live and
unresolved**, not closed.

**How the error happened, because the pattern matters more than the instance.** I read the
code default, found a comment explaining the history, and stopped. I never asked what the
deployment was actually configured to. That is the same failure this repository has hit
repeatedly — trusting a source that *describes* behaviour instead of the one that
*produces* it — and it is why the 2026-07-29 Picker work lost a day to a stack serving
pre-change code.

**Two readings, and I cannot tell them apart from here:**

1. the `.env` value is a deliberate VRAM-driven choice that was never written down; or
2. it is a leftover from before LOOP-01 R3 raised the cap.

**Recommendation.** Decide which, then make the two agree. If 384 is intended, the code
comment at `:1956` needs correcting because it currently argues against the shipped
configuration. If 768 is intended, `.env` is silently degrading extraction. **Either way the
current state is that two artifacts disagree and the operator-visible one loses.**

---

## 2. 🟢 An owed R3 Phase 12 acceptance item now has evidence — and it passes

R3 Phase 12 requires that *"all status/health GETs must be observational… snapshot
model-loaded state, generation counters, stream state and queue state before/after repeated
polls and prove no change."* That had never been verified.

**Measured, six consecutive polls of `/api/extract-diag`:**

- `observational=true`, `probe_ran=false`, `narration_live=false`
- **30 of 32 fields byte-identical**
- the only two that moved were **wall-clock ages** — `seconds_since_generation`
  (748.374 → 748.391) and `llm_cache_age_sec` (1438.94 → 1438.95)
- **zero movement** in `total_turns`, `llm_turns`, `rules_turns`, `fallback_turns`

`/api/runtime-posture` was likewise identical across six polls.

**Phase 1C's passive-diagnostic contract holds in production.** This is real acceptance
evidence for a Gate E item and should be credited as such.

**A note on my own first pass:** I initially reported `IDENTICAL=false`, because my
timestamp-stripping regex did not cover those two age fields. The correct move was to diff
field-by-field before claiming a violation, which is what turned a false alarm into a pass.
A report that had stopped at the first number would have manufactured a defect.

---

## 3. 🔴 A real narrator is badged `TEST` and is the only one who can be deleted

`ui/hornelore1.0.html`, `lv80RenderNarratorCards`:

```js
const kind   = lv80NarratorKind(person);          // computed…
const isCore = _horneloreIsCoreNarrator(person);  // …and this is used instead
list.appendChild(_renderCard(person, isCore ? "FAMILY" : "TEST", isCore ? "real" : "test", null));
```

`kind` is **assigned and never read.** The badge is decided solely by whether the display
name is in the core-Horne allow-list.

**Melanie Zollner is a real person and a real narrator.** Read from the live database:

| narrator | `role` | `narrator_type` |
|---|---|---|
| Christopher Todd Horne | `subject` | `live` |
| Janice | `subject` | `live` |
| Kent | `subject` | `live` |
| **Melanie Zollner** | `''` | **`live`** |

There is **no `is_test` column at all**. Traced through `lv80NarratorKind()`, she returns
**`"real"`** — the function that exists to answer this question, with three heuristics and a
DB flag, gets the right answer and it is discarded one line later.

**Two consequences, and the second is the one that concerns me:**

1. **She is labelled a test fixture in the operator UI.** For a system whose north star is
   narrator dignity, that is a false statement about a person.
2. **The Delete button is gated on `!_horneloreIsCoreNarrator(person)`** — so destructive
   protection is keyed on *"is a Horne"*, not on *"is real"*. The one real non-family
   narrator is the only narrator that panel offers to delete.

**This is the same shape as the other defects found this week:** the system computes the
correct answer and discards it before the boundary that acts on it — exactly as
`_is_system_directive` was computed and thrown away, and as the browser knew which send path
built a message and did not transmit it.

**Recommendation.** Use the `kind` already computed for the badge, and gate Delete on
*real vs test* rather than *Horne vs not-Horne*. Small and self-contained. The honest version
of that change probably also asks whether a real narrator should be deletable from that panel
at all.

---

## 4. 🟡 The narrator badge shows plausible fake initials when nobody is selected

Two independent causes, both live-confirmed with `state.person_id === null`:

- **`hornelore1.0.html:2929` hardcodes `MT`** into the avatar markup, so that is what shows
  before JS first runs.
- `lv80UpdateActiveNarratorCard` does `if (!name) name = "Choose a narrator"`, then passes
  that sentinel to `lv80NarratorInitials(name)` → `["Choose","a","narrator"]` → **`"CA"`**.

`lv80NarratorInitials` has a designed `|| "LV"` fallback for empty input. **It is
unreachable**, because `name` is never empty by the time it is called.

So the active-narrator badge can read `MT` or `CA` — both look like a person's initials — for
a narrator who does not exist. This repository already logged
`BUG-NARRATOR-LABEL-COLLISION-01` on the grounds that *"in a system whose job is attributing
a life to the right person, that is how a memory lands in the wrong history."* This is the
same family, one step earlier.

**Recommendation.** Pass the sentinel to the label but not to the initials; let the `"LV"`
fallback do its job, and replace the hardcoded `MT` in the markup with the same.

---

## 5. 🟡 Latent: the hidden person select is pre-selected to a narrator who is not active

`#lv80PersonSelect` sits at `selectedIndex 0` — Melanie Zollner — while `state.person_id` is
`null`. So `sel.value` is a lie about who is active.

Nothing currently reads it that way: `app.js:574` already carries the warning *"NEVER from
`lv80PersonSelect.selectedOptions`"*, added by
`BUG-TRAVEL-DOC-HIDDEN-SELECT-LABEL-STALE-01`, and the only reader writes options rather than
reading them. **This is a trap for the next author, not a live defect** — recorded so it is
not rediscovered as a mystery.

---

## 6. ✅ Not a bug: the `past-tense-flags` 404

`GET /api/operator/past-tense-flags?limit=50` returns **404**, and fires **exactly once** per
page load. That is the 2026-07-06 fix working as designed: the gate-off 404 logs one calm
line and stops auto re-probing. No action.

---

## 7. Live flag surface, captured

From `/api/extract-diag`:

```text
SPANTAG=null   NARRATIVE=true   ATTRIB_BOUNDARY=false   PROMPTSHRINK=false
EXTRACTION_BOUNDED=true   EXTRACT_MAX=128   COMPOUND=384   extractable_fields=140
llm_available=true   rules_available=true   regex_patterns=115
```

**One loose thread I did not chase.** `.env:142` sets `HORNELORE_SPANTAG=0`, but the diag
reports `null` rather than `"0"`. Behaviour is correct either way — absent and `0` both mean
off — but **a diagnostic that cannot see a flag the `.env` sets is worth one look**, because
that surface is precisely what an operator would trust to confirm SPANTAG is off. Related:
the eval harness's discipline header has already been caught reporting flag state from the
wrong process (2026-04-23).

---

## 8. Clean

- **Zero console errors** across a full boot and all six shell tabs (Operator, Intake,
  Narrator Session, Trips, Travel Doc, Media).
- All 115 application assets 200. TTS voices 200. Warmup completed; `llmReady: true`.
- The narrator switcher's own initials are all correct — MZ, JJ, KJ, CT.
- Today's two shipped features are live and correct on the served asset: the era detector is
  present with a 10/10 truth table **as deployed**, `runtime71` carries
  `era_definition_requested`, both `start_turn` frames declare `message_kind`, and the
  detector is **not** wired into `lvRouteTurn`.

---

## Suggested order

1. **The `.env` compound cap (§1).** One decision, live evidence on both sides, and the
   deployment currently runs the value its own code comment argues against.
2. **The `TEST` badge and Delete gating (§3).** Small, self-contained, and it is about how
   the system talks about a real person.
3. **The empty-state initials (§4).** Cosmetic in isolation; part of a labelled-identity
   class this repo has already been bitten by.
4. §5 and §7 are one-line notes for whoever is next in those files.

**Nothing in this report has been acted on.** No product code was changed during the sweep.
