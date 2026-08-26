# Phase 2 transport mapping — read before any Phase 2 code

**WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 checkpoint.**
**Authored 2026-08-26 against `origin/main` at `8b2c392`. NO CODE HAS BEEN CHANGED.**

Every line number below was read from the tree at `8b2c392`, not recalled.

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

## 8. What I have NOT done

No code, no schema, no tests, no migration. The eight browser promotion sites are
untouched — that is Phase 3. Nothing in chronology, Life Map, memoir or story authority,
safety, model or context window, the directive registry, Kawa, or migrations `0001–0051`.

**Awaiting a ruling on §5 before Phase 2 implementation begins.**
