# WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01

**Restore conversational Lori, and make every intervention measurable, selectable and accountable.**

Opened 2026-09-06 · **ACTIVE** · supersedes nothing; `WO-LORI-ARCHIVE-TO-MEMOIR-02`
Phase 5C is queued behind it deliberately.

---

## 1. Why this exists

The Walt+John diagnostic (`docs/reports/WALT-JOHN-VRAM-PROMPT-BUDGET-DIAGNOSTIC.md`,
local-only) measured 15 generated turns against what the narrator actually
received:

| | |
|---|---:|
| raw response was reasonable | **12 / 15** |
| delivered was **better** than raw | **0 / 15** |
| delivered was **worse** than raw | **11 / 15** |
| no control fired at all | 2 / 15 |

**The two untouched turns are among the best in the dataset.** Neither the
256-token cap nor VRAM was ever binding. The dominant cause of what narrators
read was the post-generation control layer.

The deeper problem was not any single control. It was that nobody could say
*which* layer did it. "The guards" were an undifferentiated mass spread across a
router, a control wrapper, a validator, a fallback composer and a final writer,
each added in good faith to stop a real failure somebody had witnessed, none
ever measured against the others.

**This work order builds the instrument, not the fix.** It does not decide which
controls are good. It gives them numbers, switches and evidence so that question
can be answered by experiment instead of by argument.

---

## 2. The governing principle

> **MEMORY STRICT. CONVERSATION LIGHT.**

| Lorevox owns — not switchable | Lori owns — switchable where registered |
|---|---|
| identity, provenance, extraction | listening, acknowledging, connecting |
| provisional/canonical truth, chronology | asking, conversational phrasing |
| timeline/spine, story capture | prompt instruction and example families |
| relationship integrity, archive/memoir | post-generation prose transforms |
| deletion/privacy, acute safety | validators, fallbacks, final writers |

**An authority earns a registry entry only if it can change what the narrator
receives.** Provenance, relationship meaning, lane selection, story-capture
records and committed-turn ownership are not in the 43 and must not be added —
including Phase 5C's "meaning with no schema destination", whose three outcomes
are field / review / recorded refusal. An operator checkbox that let information
silently vanish again would undo what 5C exists to establish.

**A deterministic conversational intervention earns authority only by
demonstrated benefit.** Not by having once fixed a bug.

---

## 3. What is built

Pushed and accepted. See `HANDOFF.md` for live state.

- **`lori_guard_registry.py`** — 43 authorities, derived from the tree and then
  numbered: 10 PROMPT, 7 ROUTE, 11 TRANSFORM, 6 VALIDATE, 3 REPLACE, 1
  FINAL_WRITER, 5 LOCKED. **IDs are stable and reserved**; a retired authority
  keeps its number. `position` is separate and is canonical execution order.
- **Control policy** — `SWITCHABLE` / `PROTECTED` / `PENDING_SEAM`, because
  "cannot, for safety" and "cannot, until someone splits a string" are different
  truths and an operator staring at a disabled row deserves to know which.
  Population **37 / 6 / 0**, derived.
- **Prompt seams** — the Kent/Janice witness few-shots and the reflection
  examples are separable, byte-exact, SHA-pinned against the literals they
  replaced.
- **`lori_guard_authority.py`** — three-state resolution (canonical default /
  operator override / effective state + reason), registry fingerprint over
  behavioural fields only, selection fingerprint, revision.
- **Migration 0053 + `lori_guard_store.py`** — durable operator overrides,
  installation-scoped, atomic batch, optimistic revision.
- **`lori_guard_gate.py` + `chat_ws` wiring** — one frozen acquisition per turn,
  the deterministic route family clamped.
- **`scripts/lori_guard_catalog.py`** — the catalog, generated from registry
  metadata. There is no second hand-maintained list.

---

## 4. Invariants that must not be re-broken

1. **One acquisition per turn**, at the top of `_generate_and_stream_inner`,
   after `person_id`. It must dominate witness detection (~L2884), the browser's
   proposed `turn_mode` (~L3661) and every route gate (~L4207+). *"Before prompt
   composition" is already too late for routes.*
2. **Client proposes, server resolves.** Id 26's classifier is `lvRouteTurn` in
   `ui/js/app.js`, so a stale browser can propose `correction` regardless of what
   the server selected. A server detector cannot activate a disabled route
   either.
3. **Fail-closed on all four gate conditions** — a real person, durably
   `testing_only`, an armed eval marker, and a trace that is actually recording.
   An unmeasured experimental turn is worse than no experiment.
4. **Nothing downstream re-reads** the store, the marker, the eligibility flag or
   a legacy environment gate. Consumers read the snapshot.
5. **Selection controls membership only.** `{33,40}` and `{40,33}` are the same
   experiment; `position` decides order.
6. **Selected means allowed, not fired.** A selected authority still has its own
   eligibility condition.
7. **Safety precedence and id 20 floor hold survive `All Switchable Off`.** A
   narrator who has claimed the floor is not an experiment.
8. **PROMPT authorities are `requires_rerun`.** The trace may record `excluded`;
   it may never claim what an excluded prompt block *would have produced*.
9. **Id 54's seam wraps `finalize_presentation()` ONLY.** The existing
   `delivers_question()` containment at `chat_ws.py:6933` — *"the stamp follows
   the DELIVERED text, never the plan"* — is what stops protected id 53 stamping
   a presentation the narrator never received. Gating the enclosing block would
   remove it.

---

## 5. What remains

| | |
|---|---|
| **Next slice** | Prompt authorities (1, 3–11) read the snapshot; `comm_control` ids 32–42 selected per turn; post-generation and final-writer consumers wired, including the id 54 seam |
| **Then** | Operator API, Operator Guard Lab panel, counterfactual attribution, distinct trace identity for the nine authorities sharing `comm_control`, sub-attribution inside id 51 |
| **Then** | Structural accounting for prompt and comm_control consumers — the current `EXPECTED_OPERATIONS` tuple is hand-written and checked against another hand-written list, which proves nothing about the code |
| **Then** | Live acceptance: no-restart toggling, mid-turn freeze, stale-client clamp, restart persistence |
| **Owed separately** | The response-trace closer (diagnostic finding 2, untouched); the §5 short-natural Walt run |

**No Walt or John run until `All Switchable Off` is truthful across routing,
prompt composition, transforms/replacements and the Profile Seed final writer.**

---

## 6. Harness consequence

`run_lori_behavior_harness.py` uses synthetic ids such as `eval_person`. Under
the correct fail-closed gate an unpersisted person gets canonical production
behaviour. **Do not weaken the server gate for the harness** — make the harness
create and use a real `testing_only=true` narrator.

---

## 7. Recorded corrections

Kept because each was a wrong assumption that survived review once.

- **Kent and Janice are consenting lab narrators.** Their material in the prompt
  is an exemplar-leak and overfitting finding, **not a privacy defect**. Do not
  delete it and do not replace it with synthetic biographies — that would destroy
  the ability to tell authentic oral-history complexity from artificial examples.
- **`testing_only` was persisted nowhere.** Inferring storage from a response key
  is the "cite the line that READS the value" failure.
- **People columns are owned by `init_db()`'s PRAGMA-guarded block, never by a
  migration.** Migration 0013's header records the incident.
- **Excluding the prompt examples does not make the prompt name-free.** Both
  directives keep narrator nouns inside *prohibitions*; those are the guards
  against the failures they describe.
- **Tests that create narrators must isolate `DATA_DIR` and refuse to run
  otherwise.** `DB_PATH` resolves at import, relative to cwd.
