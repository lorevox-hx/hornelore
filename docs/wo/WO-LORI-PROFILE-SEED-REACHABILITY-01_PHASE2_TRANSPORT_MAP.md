# Phase 2 transport mapping — read before any Phase 2 code

**WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 checkpoint.**
**Authored 2026-08-26 against `origin/main` at `8b2c392`. NO CODE HAS BEEN CHANGED.**

**AMENDED 2026-08-26 at `92c4a39`.** Option B is the accepted transport-scope ruling, and
five review findings are answered in §9–§13. **§4 as first written was WRONG and is
superseded by §11** — it would have marked the very topic Lori had just asked as
`addressed` in the same committed turn, before the narrator said anything about it. That
correction is the most important thing in this file.

Every line number was read from the tree, not recalled, and re-verified after writing.

---

## 0. The headline, first

**Two of the three transports cannot commit a two-row turn today, and one of them
cannot commit a narrator turn at all.**

| | REST chat `/api/chat` | REST stream `/api/chat/stream` | WebSocket `/api/chat/ws` |
|---|---|---|---|
| Writes a **user** turn row | yes, separately | **NO — none, ever** | yes |
| Writes an **assistant** turn row | yes, separately | yes | yes |
| Both rows in **one transaction** | **no** | n/a | **yes** |
| Knows `person_id` at composition | **no** | **no** | yes |
| Passes `person_id` to the row writer | **no** | **no** | yes |
| Used by the narrator UI | **no** | **dev-only, disabled by default** | **yes — this is the product** |

So question 6 answers itself: **yes, a genuine two-row committed boundary on the REST
paths requires widening REST persistence.** The exact widening is §5. I have not done it,
and I am not proposing to do it inside Phase 2 without a ruling.

---

## 1. Where authoritative onboarding state can be resolved before composition

### WebSocket — one clean insertion point, already the pattern

`server/code/api/routers/chat_ws.py:4371–4375`, in `_generate_and_stream_body`: the comment
*"LLM-path setup — only reached for turn_mode='interview'"* is `:4371` and
`model, tok = _load_model()` is `:4375`. The resolve goes between them.

Three properties make this the right seam rather than a convenient one:

* `person_id` is already bound for the turn and already in scope;
* `runtime71` is **already being mutated here for exactly this kind of reason** — the
  softened-state handoff at `:4396–4399` does `runtime71 = dict(runtime71)` and sets
  `runtime71["softened_state"]` before composition, and its own comment says it should "be
  readable as refusing on its own terms rather than relying on a value set 1,600 lines
  earlier";
* it is *after* the deterministic branches have returned (`:3855`, `:3963`, `:3993`,
  `:4237`, `:4281`, `:4354`), so the six modes that must not advance never reach it.

### REST chat and REST stream — **there is no such place today**

Both call `compose_prompt_sections(conv_for_prompt, ui_system=..., user_text=...)`
(`api.py:654` and `:788`) and **pass no `runtime71` at all**. The parameter exists
(`prompt_composer.py:5215`) and is simply never supplied.

The consequence is larger than Profile Seed: `prompt_composer.py:5121` reads
`runtime71.get("person_id")`, so with no `runtime71` the composer's entire
person-dependent layer is skipped on both REST paths. **REST composition has no narrator
context whatsoever today.**

`person_id` *is* recoverable — `db.get_session_owner(conv_id)` (`db.py:1817`) resolves it
from `sessions.person_id`, then `$.active_person_id`, then `$.person_id`, and returns
`None` rather than guessing. But it is only populated for a conversation that has already
had a turn: both REST routes write `payload['active_person_id']` **after** generation
(`api.py:693`, `:898`). A first REST turn on a fresh conversation has no owner.

---

## 2. Where the topic id and version would be captured

WebSocket: the same seam as §1 (`chat_ws.py:4371–4375`). One `profile_seed_resolve(person_id)` call yields
`active_topic_id` and `version` together, and both go into the new runtime key before
composition — which is what makes a retry conflict instead of advancing the next topic.

REST: nowhere, for the reason in §1.

---

## 3. Where both committed turn rows become durable

### The good news: the primitive already exists and is correct

`db.persist_turn_transaction` (`db.py:2179`) writes the user row and the assistant row
inside **one** explicit `BEGIN` / `COMMIT` (`db.py:2282–2318`), rolls back on any
exception, and populates `row_ids_out` **only after `COMMIT`** — its own comment at
`:2325` says *"a populated dict always means the rows exist."* That is a genuine
committed-turn boundary and Phase 2 does not need to build one.

### WebSocket has TWO call sites, and the difference between them is deliberate

1. **Model path** — `chat_ws.py:5952`. Sets `params["_persisted_turn_row_id"]` and
   `params["_persisted_user_turn_row_id"]` at `:5977–5980`. **This is the advancement
   site.**
2. **`_finalize_deterministic_turn`** — `chat_ws.py:360`, called by all six deterministic
   branches. Persists both rows identically, captures row ids into a **local** dict, and
   **structurally never writes those keys into `params`**.

That second contract is not an accident and the supervisor was right to warn about it.
`chat_ws.py:3903–3944` records that the first cut of the meta-question repair *did* set
the keys, which fired an extraction generation and a trip conversation link against Lori's
own deterministic answer, and was reverted on 2026-08-03. The docstring at `:289–306`
notes that both hooks *also* gate on turn mode, that
`PLACEMENT_ELIGIBLE_TURN_MODES` / `EXTRACTION_ELIGIBLE_TURN_MODES` are each
`frozenset({"interview"})`, that both read the mode from `params`, and that the dispatcher
resolves deterministic modes into a **local** `turn_mode` it never writes back — so **both
mode gates PASS on a deterministic turn**, and the absence of the three keys is the only
thing holding the hooks out. There is already a test asserting that over the function's own
AST.

**Phase 2 inherits this for free and must not weaken it.** Advancement keyed off the same
`params` keys is non-advancing on deterministic turns by construction, not by six branches
each remembering.

### REST chat — two rows, two transactions

`api.py:697` and `:698` are two independent `add_turn()` calls. A crash between them
leaves a narrator turn with no reply. Neither passes `person_id`, so both rows record a
`NULL` owner even though `add_turn` has accepted `person_id` since R2.3 (`db.py:2119`).

### REST stream — the assistant row only

`api.py:902` writes `add_turn(conv_id, "assistant", full, ...)` and **that is the only
`add_turn` in the whole function.** I grepped the entire route body (`api.py:763–931`) to
be sure. There is no user row. There is nothing to make a boundary out of.

---

## 4. The exact shared post-commit advancement point

> **SUPERSEDED IN TWO RESPECTS — read §11 and §13 before implementing this section.**
> As written below it advances the topic that was *asked* in the same turn, which is the
> self-advancing bug §11 exists to prevent; and it sits inside the persistence `try`,
> whose failure message would then lie, which §13 corrects. The location and the
> version-conflict reasoning are still right.

One implementation, in a new `server/code/api/services/profile_seed_turn.py`, called from
**one** place: `chat_ws.py`, immediately after the `params["_persisted_turn_row_id"]`
assignment at `:5977–5982` and inside the same `try` that already guards persistence.

It receives the topic id and version captured in §2, plus the committed assistant row id,
and calls the Phase 1 accessor `db.profile_seed_apply(...)` with that **captured** version.
Consequences, all of which fall out of Phase 1's existing contract rather than needing new
machinery:

* a duplicate hook on a retried turn hits `VersionConflict` and changes nothing, instead of
  advancing a second topic;
* an evidence change between composition and commit hits `VersionConflict` or
  `TopicNotActive` and changes nothing;
* a storage fault raises rather than returning a decision (Phase 1's accepted correction),
  so it can be logged and surfaced and can never silently fall back.

`_finalize_deterministic_turn` is **not** called into. That is the whole of the
non-advancement wiring for six of the seven modes.

---

## 5. What "widening REST persistence" would actually mean — **STOPPING HERE FOR A RULING**

To give the REST paths a true two-row committed boundary:

1. **REST stream would have to start writing a user turn row it has never written.** This
   is not a refactor; it changes the shape of the stored corpus for every REST-stream
   conversation, and `_save_chat_memory_fs` (`api.py:904`) writes a filesystem transcript
   from a different source, so the two would need reconciling.
2. **REST chat's two `add_turn` calls would have to collapse into one
   `persist_turn_transaction`.** Its user row currently stores `msgs[-1]["content"]`
   (`api.py:697`) — the post-fit message list — and its `meta` carries `{"section": ...}`,
   neither of which the WS path writes. Both would change.
3. **Both would need `person_id` resolved before composition**, via
   `db.get_session_owner(conv_id)`, which is unavailable on the first turn of a fresh
   conversation.
4. Neither route has the classification machinery the WS path has — no
   `_is_system_directive` (`chat_ws.py:1433`), no `turn_mode`, no cancellation event, no
   safety gate. Advancement decisions made there would be made with less information.

**And the strongest argument against doing it inside this lane:** the REST paths are not
the narrator product. `ui/js/app.js:6515–6528` disables the SSE fallback by default under
`BUG-SSE-FALLBACK-BYPASSES-CHAT-WS-GUARDS-01` (2026-07-07), whose own comment says it
*"bypassed the chat_ws turn machinery entirely — no safety cascade, no deterministic
routing, no response guards, no archive writer, and no user-turn persistence"* and that
*"a narrator session must NEVER silently degrade onto that path."* It survives only behind
`window.LV_ALLOW_SSE_FALLBACK === true`, dev-only. `/api/chat` is not referenced by the
narrator UI at all.

### The three options, and my recommendation

**A — widen REST persistence now.** Delivers advancement on all three transports. Costs a
change to two product routes' storage shape, inside a lane about onboarding reachability,
on paths the narrator never takes. I do not recommend it.

**B — split read authority from advancement. RECOMMENDED.** Give **all three** transports
server-authoritative *read* — the server's onboarding state overrides browser `current_pass`
everywhere, satisfying supervisory boundary 1 — by resolving `person_id` through
`get_session_owner` and passing a `runtime71` to the REST composers. Wire *advancement*
only where a genuine committed-turn boundary exists, which is WebSocket. A REST turn would
then render the correct single topic and never advance it, which is **honest**: that path
cannot prove a turn completed, so it must not claim one did.

**C — declare REST out of scope.** Simplest and least truthful; the two REST paths would
keep composing with no narrator context at all.

I recommend **B** and want it ruled on before I write Phase 2 code, because it is the one
place where "all three transports agree" has to mean something weaker than it sounds, and
that weakening should be your decision rather than mine.

One honest note about B: giving REST a `runtime71` for the first time changes what those
two routes put in their prompt — today they compose with no person-dependent layer at all.
That is a fix, but it is a behaviour change on a path that has not had one in a while, and
it should be named rather than slipped in under "read authority".

---

## 6. Turns that must not advance — the complete inventory

| Class | Where it is already decided | Mechanism Phase 2 uses |
|---|---|---|
| `floor_hold` | `chat_ws.py:3839` → `:3855` | `_finalize_deterministic_turn` never sets the params keys |
| `meta_question` | `:3878` → `:3963` | same |
| `witness` | `:3991` → `:3993` | same |
| `memory_echo` | `:4016` → `:4237` | same |
| `age_recall` | `:4256` → `:4281` | same |
| `correction` | `:4294` → `:4354` | same |
| System directive | `params["_is_system_directive"]`, set `:1433` from declared kind `internal_directive` or a `[SYSTEM` prefix | explicit check before advancing |
| Cancelled | `ev.is_set()`, already recorded in turn meta at `:5961` | explicit check before advancing |
| Safety turn | `_is_safety_turn` / `_safety_enabled` gate at `:1535` | explicit check; safety stays parked and untouched |
| Persistence failure | `except` at `:6040` — sends an error frame and writes nothing | advancement lives inside that same `try`, so a failed persist cannot reach it |
| Paused onboarding | Phase 1 `reconcile` returns `status="paused"` with `active_topic_id=None` | nothing to advance; no Life Map advancement either |
| Narrator switch | `person_id` is bound per turn (`:6178`, `:6180`, `:6217`) | the captured version belongs to the narrator composed for; a switch makes it stale and it conflicts |
| Historical narrator | Phase 1 `profile_seed_resolve` returns `None` | byte-stable legacy behaviour; nothing added to `runtime71` |

---

## 7. The `runtime71` key boundary

`runtime71["profile_seed"]` is **not touched.** Its live readers, all preserved:

* `prompt_composer.py:2269` and `:2870` — memory echo and name recovery;
* `prompt_composer.py:4634` — the composer's own seed read;
* `chat_ws.py:3531`, `:3719`, `:3727` (the UI-seed merge), `:5084`.

Phase 2 introduces a **distinct** key — proposed `runtime71["profile_seed_onboarding"]`,
carrying `{status, active_topic_id, version, known_topics, remaining_topics}` and nothing
else. No narrator prose, per work-order decision 8. A test will assert the legacy key is
byte-identical with and without onboarding state present.

---

## 9. First-turn REST identity resolution — §1's "nowhere" was too pessimistic

**The correction stands and I was wrong to write it off.** §1 said `person_id` is only
recoverable from a session that has already had a turn. That is true of
`get_session_owner`, and it is not the whole picture: **both REST routes already parse
`PROFILE_JSON` before composition**, at `api.py:640` and `:775`, via
`extract_profile_json_from_ui_system` (`prompt_composer.py:489`), and both already read
`profile_obj.get('person_id')` out of it — at `:692` and `:897`, to write
`payload['active_person_id']`. The identifier is in scope on the *first* turn. It is
simply used only afterwards.

`ui/js/app.js:6634` confirms the SSE caller puts `person_id` into that blob.

### The resolution rule

```
owner   = db.get_session_owner(conv_id)          # db.py:1817
claimed = (profile_obj or {}).get("person_id")   # already parsed, api.py:640 / :775

owner and claimed and owner != claimed  ->  REFUSE. 409. Compose nothing.
owner                                   ->  use owner        (established, authoritative)
claimed                                 ->  use claimed      (first turn only)
neither                                 ->  legacy ownerless prompt, BYTE-STABLE
```

**Why the mismatch is a refusal and not a preference.** An established session owner is a
server fact; a browser-supplied id is a claim. Letting the claim win would let a stale tab
or a mid-switch race compose one narrator's onboarding state into another narrator's
conversation — the cross-person failure the Picker identity boundary in `CLAUDE.md` is
written to prevent, arriving through a different door. Silently preferring the owner would
be safer than preferring the claim and still wrong: the caller believes it is talking to
somebody else, and it should be told.

**The claim identifies; it never carries state.** `PROFILE_JSON` may say *who*. Onboarding
status, active topic and version are read from `profile_seed_onboarding` by that id and
from nowhere else. A browser cannot assert that a topic is answered, on any transport.

**Ownerless stays byte-stable.** No owner and no claim means no `runtime71` is constructed
at all, and the prompt is the one that path produces today. §10 is what makes that
guarantee testable rather than hoped for.

---

## 10. Sparse-runtime isolation — the finding that would have broken REST

**This is real and I had not seen it.** `prompt_composer.py:3942` opens `if runtime71:`,
and inside it `:4100` reads

```python
identity_complete = bool(runtime71.get("identity_complete", False))
...
identity_mode     = (effective_pass == "identity") or (not identity_complete)
```

So a runtime object carrying only `{"person_id": ..., "profile_seed_onboarding": ...}`
does not merely add a section. **It flips `identity_complete` to `False`, which flips
`identity_mode` to `True`, which puts REST into identity interrogation** — Lori asking a
narrator she has known for months for their name, because a dict gained two keys. The same
block also defaults `current_pass` to `"pass1"` (`:4078`), `current_era` to
`"not yet set"` (`:4086`), `current_mode` to `"open"`, `affect_state` to `"neutral"`, and
`assistant_role` to `"interviewer"`.

### The rule

**Onboarding rendering must be gated on its own key, independently of `if runtime71:`.**
Two requirements, both testable:

1. **The onboarding section is emitted iff `runtime71["profile_seed_onboarding"]` is
   present and its status is `active`.** Not iff `runtime71` is truthy.
2. **A runtime object built by Phase 2 for a REST turn must either be complete enough to
   be truthful, or absent.** Concretely: when REST resolves a narrator, it supplies
   `person_id` **and** the real `identity_complete` from
   `profile_seed.identity_anchors_complete` — the same predicate the resolver uses, so the
   two cannot disagree — rather than letting the default decide. When REST resolves
   nobody, it passes no `runtime71` and the prompt is unchanged.

### The byte-stability test this needs

Three REST prompts must be **byte-identical** before and after Phase 2:

* an ownerless conversation (no owner, no claim);
* a historical narrator (owner exists, `profile_seed_resolve` returns `None`);
* an enrolled narrator whose onboarding status is `completed`.

Byte-identical, not "equivalent". A diff of one character means an unrelated default moved,
and the whole point of this section is that those defaults are load-bearing on a path that
has never carried them.

Also byte-stable, and named because they call the same composer: the translation caller and
`/api/warmup` (`api.py:702`), which skips composition entirely and must keep doing so.

---

## 11. The prior-question correlation — §4 as written was a self-advancing bug

**The review is right, the sequence it describes is exactly what §4 would have produced,
and it is worth stating in full because it is the failure mode the whole lane exists to
prevent.**

With §4 as first written:

1. onboarding resolves `active_topic_id="childhood_home"`, version 7;
2. Lori's prompt receives it and she asks where the narrator grew up;
3. the turn commits;
4. the post-commit hook applies `addressed` to `childhood_home` at version 7;
5. **the narrator has not answered. They have not spoken since before the question
   existed.**

The next turn would move to `siblings`. Ten turns later the walk would report itself
complete having received zero answers, and the narrator would have been asked ten
questions and heard none of them acknowledged. That is worse than the defect being fixed.

### The correlation rule

**A topic advances only when the current user row is a response to a topic presented in a
PREVIOUS committed assistant row.**

The turn Lori *asks* in and the turn the narrator *answers* in are different turns, and the
state machine has to hold that fact across a commit boundary.

### Where the presented topic is recorded — no schema change, no prose

`persist_turn_transaction` already merges caller `meta` into the assistant row's
`meta_json` (`db.py:2308`, `assistant_meta = {"model": ..., **(meta or {})}`), and the WS
model path already passes `meta={"ws": True, "cancelled": ev.is_set()}` at `:5961`. Phase 2
adds two scalars there:

```python
meta={"ws": True, "cancelled": ev.is_set(),
      "profile_seed_presented_topic": <topic_id>,
      "profile_seed_presented_version": <version>}
```

Two identifiers and an integer. No narrator text, no question wording, no answer — work
order decision 8 holds. The topic id is one of ten fixed registry strings.

### Where it is read back — already in scope

`chat_ws.py:4376` already calls `export_turns(conv_id)` into `history` for the model, and
`export_turns` (`db.py:2146`) returns each row's parsed `meta` dict (`db.py:2162`). **No
new accessor is needed.** The last assistant row carrying
`profile_seed_presented_topic` is the question this user turn is answering.

### The state machine

```
COMPOSE (chat_ws.py:4371-4375)
  resolve -> status, active_topic_id A, version V
  presented = the last assistant row in history carrying a presented topic

  if status != "active":            render nothing; no advancement
  if presented is None:             FIRST PRESENTATION.
                                      render topic A
                                      stamp A/V on THIS assistant row
                                      ADVANCE NOTHING            <-- the bug, closed
  if presented.topic == A:          the narrator is answering A now.
                                      classify (see 12) -> addressed | declined | stationary
                                      re-stamp A/V so a non-answer can be answered next turn
  if presented.topic != A:          A moved underneath us (operator entry, superseded
                                      evidence). Treat as first presentation of the new A.
                                      ADVANCE NOTHING.
COMMIT (persist_turn_transaction)
POST-COMMIT (see 13)
  apply the classification to presented.topic at presented.version
```

The version applied is **the one stamped on the assistant row that asked the question**,
not the one read at composition. That is what makes a retry harmless: a duplicated hook
re-applies the same topic at the same version and gets `VersionConflict` from Phase 1's
`profile_seed_apply`, which writes nothing.

---

## 12. `addressed` versus `declined` versus stationary

The map excluded deterministic and meta turns and stopped there. It has to go further,
because **treating every model-path message as an answer is a way of not listening.**

### Two refusal vocabularies already exist, and neither is quite right

* `extract._apply_refusal_guard._REFUSAL_PATTERNS` (`routers/extract.py:6862–6873`) —
  seven regexes for explicit topic and privacy refusal: *"I'd rather not get into that"*,
  *"not for putting in a book"*, *"nothing I want to go into"*. **This is what `declined`
  means** and Phase 2 should reuse it rather than write an eighth list.
* `thread_bank.DECLINATION_PATTERNS` (`services/thread_bank.py:136–152`) — fifteen
  substrings, but it **mixes refusal with forgetting**: *"can't recall"*, *"nothing comes
  to mind"*, *"I don't remember much"* sit beside *"I'd rather not"*. For surfacing a
  banked thread that conflation is harmless. Here it is not, and reusing this list whole
  would be the mistake.

### The proposed classification

| Narrator turn | State | Why |
|---|---|---|
| Substantive response to the presented topic | `addressed` | they answered |
| Explicit refusal (`extract` patterns) | `declined` | "I would rather not" is an answer, and final |
| **"I don't remember"** | **RULING NEEDED — see below** | |
| Meta / control / repeat / help | stationary | already routed to a deterministic branch |
| Empty or whitespace | stationary | |
| System directive (`params["_is_system_directive"]`, `chat_ws.py:1433`) | stationary | not the narrator speaking |
| Cancelled (`ev.is_set()`, `:5961`) | stationary | the narrator did not hear the answer |
| Persist failure (`:6040`) | stationary | see §13 |

### Two things I will not decide alone

**1. "I don't remember" is genuinely ambiguous and it is a dignity question, not a
technical one.** It is not a refusal. It is arguably an answer — asking a ninety-year-old
the same question every session because they could not recall it the first time is the
interrogation principle 8 forbids. It is also arguably *not* an answer — memory returns,
and a topic they could not reach on Tuesday they may reach on Friday, which is much of the
point of the system. I lean toward `addressed` **with the recall failure recorded nowhere
in the progress row**, so the walk stays finite and the narrator is not re-asked. But this
decides how Lori treats a narrator's memory loss, and it should be Chris's call.

**2. There is no defensible word-count threshold for "substantive".**
`thread_bank._SUBSTANTIVE_WORD_COUNT = 30` (`:156`) exists for a different purpose and
must not be borrowed: *"Devils Lake, North Dakota"* is four words and completely answers
the childhood-home question, while thirty words of *"oh goodness, let me think, that was
such a long time ago now"* answers nothing. I propose **any non-empty narrator turn on the
model path that is neither a refusal nor a control turn counts as addressed**, and that
the operator review surface, not a word counter, is where a thin answer gets caught.

---

## 13. Post-commit advancement failure is NOT turn-persistence failure

**The review is right and the existing error string would have lied.**

`chat_ws.py:6040–6042` catches persistence failure and sends the client
`"Turn persist failed — no state written"`. §4 placed advancement inside that same `try`.
But advancement runs **after** `persist_turn_transaction` has returned, which means both
turn rows are already committed — so a `profile_seed_apply` failure would emit a frame
saying no state was written when the entire conversation turn had just been durably
written. An operator reading that would look for a lost turn that is sitting in the
database.

### The rule

Advancement gets its **own** `try`, after the persistence `try`, never inside it:

* **conversation rows stay committed.** They are not rolled back and are not the failure.
* **onboarding stays unchanged.** `profile_seed_apply` is all-or-nothing (Phase 1,
  `BEGIN IMMEDIATE` + rollback on every raise), so a failure leaves the row as it was.
* **the failure is visible.** A distinct log line naming the narrator, the topic and the
  version — not the persistence message, and not a swallowed exception.
* **it is retryable and idempotent.** The topic and version are on the committed assistant
  row (§11), so a retry re-derives them from durable state rather than from anything held
  in memory. Re-applying at the same version conflicts and changes nothing.
* **the narrator sees nothing.** They have already been answered. A failed onboarding
  advance costs one repeated question next turn, which is a smaller harm than an error
  frame after a turn that worked.
* **archive, extraction, story and trip hooks keep their existing behaviour**, gated
  exactly as they are today on `_persisted_turn_row_id` / `_persisted_user_turn_row_id` /
  `_archive_event_persisted`. Advancement adds no key any of them reads.

---

## 14. Required tests, folded in

Beyond the review's list, three that fall out of the sections above:

* **the first presentation advances nothing** — the §11 bug, as a named test;
* **three REST prompts are byte-identical** before and after Phase 2 (ownerless,
  historical, completed) — §10, and `/api/warmup` and the translation caller with them;
* **an owner/claim mismatch refuses and composes nothing** — §9.

And one control on the tests themselves: a mutation that removes the `presented is None`
guard must fail the first-presentation test. Two instruments in this lane have already
measured themselves instead of the code, so every new guard gets a mutation.

---

## 15. What I have NOT done

No code, no schema, no tests, no migration. The eight browser promotion sites are
untouched — that is Phase 3. Nothing in chronology, Life Map, memoir or story authority,
safety, model or context window, the directive registry, Kawa, or migrations `0001–0051`.

**Option B is the accepted transport-scope ruling. Awaiting review of the §9–§13
amendments before Phase 2 implementation begins.**
