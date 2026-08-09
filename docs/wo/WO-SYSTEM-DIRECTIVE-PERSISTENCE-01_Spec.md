# WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 — Stop persisting internal directives as narrator speech

**Status:** 📝 **SPEC ONLY — NOT IMPLEMENTED.** Written 2026-08-09. No code was changed.

**Priority:** P1 — the clearest known data-semantics defect in the system as of 2026-08-09.

**Execution owner:** Claude · **Decision owner:** Chris Horne

**Narrator generality:** UNIVERSAL — nothing here is family-specific.

**Opened by:** `HANDOFF.md` §5, which named this as its own concern and said explicitly:
*"Do not fold this into unrelated Lean Lori or Travel Document work."*

---

## 1. The defect in one sentence

Internal guidance that Hornelore composes for itself is written to the `turns` table with
`role='user'`, so **every reader downstream has to be told, one at a time, that the narrator
did not say it** — and eighteen modules have now been told.

---

## 2. What is actually happening

**The directives are composed in the browser.** `ui/js/app.js` builds strings such as
`[SYSTEM: SPEAKER IDENTITY — The person is named "…", born … in …]`,
`[SYSTEM: Begin the identity onboarding sequence. …]`,
`[SYSTEM: RESUME SESSION — … is returning …]`,
`[SYSTEM: COGNITIVE SUPPORT MODE RE-ENTRY. …]`, and roughly twenty more.
`ui/js/session-loop.js` additionally emits `[SYSTEM_QF: …]`. These are sent over the chat
WebSocket **in the user message slot**, because in-band guidance is how Lori is steered.

**Nothing reclassifies them before they are stored.**
`server/code/api/db.py:persist_turn_transaction()` (defined at **`db.py:1548`**, called from
**14 sites**) writes the pair:

```python
cur.execute(
    "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) VALUES(?,?,?,?,?,?);",
    (conv_id, "user", user_message, ts, "", "{}"),
)
```

`role` is hardcoded `"user"`. `meta_json` is hardcoded `"{}"`. The sibling single-row writer
`db.py:add_turn()` (**`db.py:1494`**) *does* take `role` as a parameter, so the table itself
has never been the constraint.

**`turns` carries no constraint that would have caught this.** Columns are
`id, conv_id, role, content, ts, anchor_id, meta_json` (`db.py:352`). `role` is plain
`TEXT NOT NULL` with **no `CHECK`**, and `meta_json` on the user row is unused — it is
literally the two characters `{}`.

**So the truth about authorship survives only as a string prefix**, and every consumer
re-derives it by sniffing that prefix.

### 2.1 The finding that makes this WO small

**The classification already exists, in the right place, one function above the write, and is
already carried in the right object.** `server/code/api/routers/chat_ws.py:1247`:

```python
_ut_lstrip = (user_text or "").lstrip()
_is_system_directive = _ut_lstrip.startswith("[SYSTEM")
...
params["_is_system_directive"] = _is_system_directive     # chat_ws.py:1263
```

The comment above it already states the principle in the repository's own words: *"those are
not narrator-authored content and must not be classified."* It was added for story capture
(Patch A, 2026-04-30) and extended to trip placement
(`BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01`, 2026-07-31).

**This value never reaches the row.** That is the whole defect. The system knows the answer
and throws it away at the moment of writing it down.

---

## 3. Why a nineteenth reader-side filter is the wrong fix

Non-cache modules that reference the `[SYSTEM` prefix, counted 2026-08-09:

| Layer | Modules |
|---|---|
| Server (13) | `routers/chat_ws.py` · `routers/transcript.py` · `db.py` · `archive.py` · `prompt_composer.py` · `services/lori_witness_mode.py` · `services/trip_repository.py` · `services/trip_placement.py` · `services/peek_at_memoir.py` · `services/evidence_text.py` · `services/turn_extraction.py` · `services/trip_interview_context.py` · `services/lori_followup_bank.py` |
| Browser (5) | `ui/js/app.js` · `ui/js/travels-shelf.js` · `ui/js/interview.js` · `ui/js/session-loop.js` · `ui/js/life-map.js` |

The filtering has already reached the SQL layer — `db.py:5193` carries
`AND t.content NOT LIKE '[SYSTEM:%'` — and the *comment* above it
(`db.py:5182`) states the defect outright: *"Internal system prompts (role='user' but content
starts with '[SYSTEM:')."*

Three properties make this a boundary problem rather than a filtering problem:

1. **It is opt-out, and opt-out defaults fail silently.** A new reader is correct only if its
   author happened to know. The Travel Document lane is the worked example: it was correct
   *because* it was written after a live export attributed 740 characters of instructions to
   Christopher — a defect found by a human reading a memoir, not by a test.
2. **The prefix is not a contract.** `[SYSTEM:` and `[SYSTEM_QF:` differ; some readers match
   `"[SYSTEM"`, some `"[SYSTEM:"`, some `lstrip()` first and some do not, one matches in SQL.
   Any directive that ever starts differently defeats an unknown subset of them.
3. **A narrator could type it.** Nothing stops a narrator from beginning a sentence with
   `[SYSTEM:`. Today that would silently erase their words from their own memoir. Unlikely is
   not the same as impossible, and this system's whole job is not losing what someone said.

**The rule this WO establishes:** *authorship is decided once, at the persistence boundary,
and recorded on the row. Readers ask the row; they do not re-read the prose.*

---

## 4. Scope

**In scope:** the canonical persistence boundary for chat turns; an explicit non-narrator
representation on the row; migrating readers from prefix-sniffing to the recorded flag; a
non-vacuous regression test at that boundary.

**Explicitly OUT of scope — do not do these in this WO:**

- **Any automatic rewrite of historic rows.** `HANDOFF.md` §9 lists it as deferred.
  Historic rows keep a documented legacy fallback instead (§6, Phase 3).
- Changing what the browser emits, or how directives are worded.
- Removing directives from the LLM prompt. **They are meant to reach the model** — that is
  the entire point of in-band guidance. This WO changes how a turn is *recorded*, never what
  Lori is *told*.
- Lean Lori phases, Travel Document, Picker, extraction quality, safety.
- Any schema change beyond what the chosen option in §5 requires.

---

## 5. DECISION REQUIRED FROM CHRIS — the representation

This is an architecture ruling and it is deliberately not being made by an agent. Three
options, with the honest cost of each.

### Option A — mark the row in `meta_json`, keep `role='user'` *(RECOMMENDED)*

Write `{"origin": "system_directive"}` (or similar) into the user row's `meta_json`, which is
currently the unused literal `"{}"`.

- **No schema change, no migration, no new column.** The field exists and is empty.
- **Zero blast radius on history builders.** Every reader that selects `role='user'` to build
  the model's conversation history keeps working unchanged — which matters, because the
  directive *must* still reach Lori.
- Readers that care about authorship switch from prefix-sniffing to reading one flag.
- **Cost, stated plainly:** `role` remains slightly dishonest in isolation. The row still
  says `user`; the truth lives one field over. This is a real semantic compromise and it is
  the price of not moving fourteen call sites and every history query at once.
- **Reversible** in one commit if it proves wrong.

### Option B — a distinct `role` value

Write `role='system_directive'` (or `'system'`).

- Semantically honest: the column that means *who authored this* would say so.
- **Cost:** `role` is doing double duty — *who wrote it* **and** *how it replays to the
  model*. Splitting the first meaning off silently changes the second. **Every history
  builder must be audited in the same commit**, or directives quietly stop reaching Lori and
  her behaviour changes for reasons nobody connects to a storage change. That is a
  significantly larger and riskier commit than A, and the failure mode is behavioural rather
  than loud.

### Option C — a separate `directives` table

Cleanest separation; largest change; requires a migration, a new writer, and a merge at every
point that reconstructs a conversation in order. **Not recommended now** — it is the right
answer only if directives later need their own lifecycle (retention, redaction, replay).

**Recommendation: A.** It closes the defect at the boundary, costs no migration, cannot
change what Lori is told, and leaves B or C open later. **No implementation starts until
Chris rules.**

---

## 6. Phases

Each phase is a scope wall. One concern per commit; code and docs may be separate commits.

### Phase 0 — evidence, no code

Confirm on the live database (read-only, `mode=ro`) how many `turns` rows have
`role='user'` and content matching the directive shapes, per conversation and in total. This
number sizes the legacy fallback in Phase 3 and belongs in the WO report. **Do not write.**

### Phase 1 — the boundary

`persist_turn_transaction()` accepts an explicit, keyword-only, default-false parameter
carrying the classification, and records it per the ruling in §5. `chat_ws.py` passes the
`params["_is_system_directive"]` value that **already exists** at `chat_ws.py:1247`.

- Default false means **all 14 existing call sites are behaviour-preserving** without edit.
- The parameter is the *classification*, not the text: the boundary must not re-sniff the
  prefix. The whole point is that the decision is made once, upstream, where the context is.
- `db.py:add_turn()` gets the same treatment for parity, or a comment stating why not.
- **No reader changes in this phase.** After Phase 1 the flag is written and nothing reads
  it — that is correct, and it means Phase 1 can be reverted alone.

### Phase 2 — one reader, proving the flag works

Migrate exactly one reader — **`routers/transcript.py:452` is the suggested pilot**: single
call site, one line, easy to observe. It reads the flag and keeps the prefix check as an
explicit legacy fallback. Verify against a real conversation containing both kinds of turn.

### Phase 3 — the remaining readers, with the fallback stated

Migrate the rest. **Every migrated reader keeps the prefix check** as a documented fallback
for pre-Phase-1 rows, with a comment naming this WO and the date, because no historical
rewrite is authorised. The prefix check stops being the *primary* mechanism; it does not stop
existing.

Include the SQL filter at `db.py:5193` — a `meta_json` predicate replaces it under Option A,
and the retired `NOT LIKE '[SYSTEM:%'` clause is quoted in a comment above the new one.

### Phase 4 — browser (optional, Chris's call)

The seven UI modules classify for *display*. They may keep sniffing — display is not
persistence, and a wrong guess there is cosmetic. Migrate only if the flag is already on the
wire for free.

---

## 7. Acceptance

**A green test is not acceptance here; several of these must be proven behaviourally.**

1. A directive turn persists with the recorded classification; **its `content` is byte-identical** to before.
2. **A genuine narrator turn is byte-identical across every column, including `meta_json`.** Compare whole rows, not the field under test — a partial write must not be able to hide.
3. **The composed prompt Lori receives is byte-identical before and after.** This WO must not change her behaviour, and the only way to know is to compare the prompt.
4. A narrator turn whose text genuinely begins with `[SYSTEM:` is recorded as **narrator speech** and survives to the memoir. This is the case the prefix approach gets wrong and is the clearest demonstration that the boundary fix is not cosmetic.
5. Archive, transcript, extraction, timeline, trip placement, story capture and Travel Document export all behave as they do today, on a real conversation containing both kinds of turn.
6. **A Travel Document export still attributes no `[SYSTEM:` text to the narrator** — re-run against the same trip the 2026-08-06 live acceptance used, and compare.
7. `turn_extraction` ledger behaviour is unchanged: idempotency still keys on `turnrow:<rowid>` and row ids do not shift.

### Non-vacuity is required, not optional

The guard test **must be mutation-tested**: revert the Phase 1 boundary change on a scratch
copy and confirm the test fails; restore and confirm it passes. A test that cannot go red is
decoration, and this repository has produced that outcome enough times to have written it
down as doctrine.

**Prefer behavioural assertions over source scans.** A source scan asserting "no reader
sniffs the prefix" will match the retirement comments this WO requires those readers to
carry — the same false-positive class the repo has now hit at least four times. Assert on
stored rows and rendered artifacts.

---

## 8. Stop conditions

Stop and report rather than proceeding, if:

- the flag cannot be threaded without changing what Lori is told (that is Option B's cost arriving early, and it is Chris's ruling, not a workaround);
- any reader turns out to depend on directives being indistinguishable from narrator speech;
- fixing this appears to require a historical rewrite (deferred — ask, do not migrate);
- the work starts to need a schema change under Option A (it should not; if it does, the option was wrong).

## 9. Rollback

Phase 1 alone is one commit and reverts cleanly — the flag becomes unwritten and every reader
still has its prefix check. Phases 2 and 3 revert per reader. **Nothing in this WO deletes a
fallback**, which is what keeps rollback safe at every point.

---

## 10. Evidence index (verified 2026-08-09, cited so the next reader need not re-derive it)

| Claim | Location |
|---|---|
| Canonical turn-pair write, `role` hardcoded `"user"`, `meta_json` hardcoded `"{}"` | `server/code/api/db.py:1548` (body ~`:1615`) |
| 14 call sites | `grep -rn persist_turn_transaction server/code/api/` |
| Sibling single-row writer, already takes `role` | `server/code/api/db.py:1494` (`add_turn`) |
| `turns` schema; `role TEXT NOT NULL`, no `CHECK` | `server/code/api/db.py:352` |
| Classification already computed and threaded into `params` | `server/code/api/routers/chat_ws.py:1247`, `:1264` |
| The defect stated in an existing comment | `server/code/api/db.py:5182` |
| Filtering has reached SQL | `server/code/api/db.py:5193` |
| Archive-side filter | `server/code/api/archive.py:1187` |
| Transcript-side filter | `server/code/api/routers/transcript.py:452` |
| Prior partial fixes, same root cause | story capture Patch A 2026-04-30; `BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01` 2026-07-31; Travel Doc closeout 2026-08-06 |

**Three lanes have now each fixed this locally.** That is the argument for fixing it once.
