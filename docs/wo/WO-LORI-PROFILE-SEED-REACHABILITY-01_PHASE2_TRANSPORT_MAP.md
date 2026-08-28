# Phase 2 transport mapping — read before any Phase 2 code

**WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 checkpoint.**
**Authored 2026-08-26 against `origin/main` at `8b2c392`.**
**Phase 2 steps 1–4 have since landed; see §15 for the current state.**

**AMENDED THREE TIMES, 2026-08-26** — at `92c4a39` (§9–§13), `eccb3fe` (§11 two-event
rewrite, §12 rulings) and `dfda3c5` (§11 exact tuples and recovery, §12 count).
Option B is the accepted transport-scope ruling.

**FOUR design errors were caught across three reviews, and all are corrected in §11.**
The first
would have marked the topic Lori had just ASKED as `addressed` in the same committed turn,
before the narrator said anything about it. The second — my proposed repair for the first —
used one event type and re-stamped it, which cannot tell *"Lori presented A"* from *"the
narrator answered A and Lori acknowledged it"*, so the acknowledgement turn would have
re-asked the question it was acknowledging. The third compared topics where it had to
compare `(topic, version)` tuples, so an answer to an old version of a still-active
question could consume a newer presentation. And §13 claimed a durable retry that §11 did
not implement — what the machine actually did was re-ask a question the narrator had
already answered, which is repetition wearing retry's clothes.

**§4 is superseded by §11 and §13.** Those corrections are the most important thing in
this file.

**Status of each section:** §9, §10 and §13 ACCEPTED (§13 with one false sentence
corrected — see below). §12 ruled, rewritten to the ruling, and its pattern count fixed
from seven to EIGHT. §11 rewritten to two durable event types, then corrected again to
compare exact `(topic, version)` tuples and to add the missing recovery stage.

**The DESIGN is settled; the IMPLEMENTATION state is §15, not this paragraph.**

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

## 5. What "widening REST persistence" would actually mean — **RULED: OPTION B**

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

> ### ⚠ AMENDED 2026-08-27 — THIS TABLE SAID SIX AND THERE ARE **NINE**
>
> The deterministic list below was called "the complete inventory" and contained the
> six branches that route through `_finalize_deterministic_turn`. **Three more
> persisted deterministic early returns exist and BYPASS that function**, each calling
> `persist_turn_transaction` directly with its own inline `meta` dict and then
> returning: `floor_buffer`, `past_tense_acknowledge` and `bank_flush`.
>
> This is the most dangerous shape a wrong inventory can take. The six that were listed
> make the three that were not look considered — a reader checking "are the
> deterministic paths covered?" finds a table, a mechanism column, and line numbers, and
> stops. Step 6 merges Profile Seed metadata into the assistant row's turn commit; a
> persist site the map does not know about is a persist site nobody thinks to check.
>
> **The six inherit their guarantee. The three do not.** `_finalize_deterministic_turn`
> is structural: it never writes `_persisted_turn_row_id`, `_persisted_user_turn_row_id`
> or `_archive_event_persisted` into `params`, and one test asserts that over the
> function's own AST — so anything routed through it is held out by construction rather
> than by six authors each remembering. The other three inherit nothing at all, which is
> exactly why they need their own guards and their own rows here.
>
> Pinned executably in `tests/test_profile_seed_deterministic_paths.py`: the number of
> deterministic persist **call sites** in `chat_ws.py` must be exactly nine, every mode
> above must occur exactly once, no unlisted mode may appear, and each site must carry its
> expected finalized/bypassing classification — so a tenth path fails a named test rather
> than joining silently. That test also asserts this document names all nine, so the map
> and the code cannot drift apart again.
>
> *(Corrected 2026-08-28. This said "the SET of deterministic `turn_mode` values", and the
> extractor behind it returned a dict keyed by mode — so two call sites sharing a mode
> collapsed into one, and the "a tenth path cannot join silently" claim was false in
> exactly the case a tenth path is likeliest to arise: a branch copied from an existing one
> that keeps its predecessor's `turn_mode`. Proved on a two-line synthetic module: 2 call
> sites in, 1 site reported. Mutation `D4` adds a tenth site reusing `floor_buffer`; the
> old extractor reported 9 and passed, the corrected one reports 10 and fails.)*

### The nine persisted deterministic paths

| # | `turn_mode` | Persist site | Routing | Guard |
|---|---|---|---|---|
| 1 | `floor_hold` | `chat_ws.py:3855` | `_finalize_deterministic_turn` | structural — the finalizer never sets the params keys, never names a Profile Seed key, never applies |
| 2 | `meta_question` | `:3963` | same | same |
| 3 | `witness` | `:3993` | same | same |
| 4 | `memory_echo` | `:4237` | same | same |
| 5 | `age_recall` | `:4281` | same | same |
| 6 | `correction` | `:4354` | same | same |
| 7 | **`floor_buffer`** | `:1672` | **direct `persist_turn_transaction`, then `return`** | **its own** — the early-return region carries no Profile Seed key and calls no apply |
| 8 | **`past_tense_acknowledge`** | `:3071` | **direct, then `return`** | **its own**, as above |
| 9 | **`bank_flush`** | `:3654` | **direct, then `return`** | **its own**, as above |

`floor_buffer` is worth a sentence of its own: it answers `"I'm listening."` to a
buffered chunk and is the ONE deterministic path a narrator can hit repeatedly and
deliberately, by talking in pieces with the floor held. If it could stamp a
presentation, a narrator mid-sentence would answer questions Lori never asked.

### The rest of the inventory

| Class | Where it is already decided | Mechanism Phase 2 uses |
|---|---|---|
| System directive | `params["_is_system_directive"]`, set `:1433` from declared kind `internal_directive` or a `[SYSTEM` prefix | `plan_turn(eligible=False)` → **`HOLD`**, not `IDLE` — see §6b |
| Conversation control | `services/conversation_control.py`, the detector extracted from `trip_story_capture` | `HOLD` or `RE_PRESENT` by intent; never `addressed` — see §6b |
| Cancelled | `ev.is_set()`, already recorded in turn meta at `:5961` | `eligible=False` → `HOLD` |
| Safety turn | `_is_safety_turn` / `_safety_enabled` gate at `:1535` | explicit check; safety stays parked and untouched |
| Persistence failure | `except` at `:6040` — sends an error frame and writes nothing | advancement lives inside that same `try`, so a failed persist cannot reach it |
| Paused onboarding | Phase 1 `reconcile` returns `status="paused"` with `active_topic_id=None` | `IDLE`; nothing to advance, and no Life Map advancement either |
| Narrator switch | `person_id` is bound per turn (`:6178`, `:6180`, `:6217`) | the captured version belongs to the narrator composed for; a switch makes it stale and it conflicts |
| Historical narrator | Phase 1 `profile_seed_resolve` returns `None` | `IDLE` — byte-stable legacy behaviour; nothing added to `runtime71` |

---

## 6b. `HOLD` — the suppress-only state, and how a control is identified

**Decided 2026-08-27, BEFORE Step 6 code, because it is not a decision that belongs
inside a WebSocket hook.**

### The hole `IDLE` left

`plan_turn(..., eligible=False)` returned `IDLE`, and §7's suppression gate is driven by
whether there is a validated renderable plan. So `IDLE` **un-suppresses the legacy
browser Profile Seed block** — correctly, for a historical narrator who was never
enrolled and for whom that block is the only Profile Seed behaviour there is.

For a narrator with an **active server-owned walk** it was wrong in the direction this
whole lane exists to prevent. An internal system directive arriving mid-walk would:

* advance nothing — correct;
* and hand Lori back **"Gather the following 10 facts"**, the browser pass the server had
  just taken ownership of.

"Server state overrides browser pass" has to hold on the turns that do nothing as much
as on the turns that ask.

### The state

`HOLD` — a fifth action on `TurnPlan`, alongside `PRESENT`, `RE_PRESENT`, `ACKNOWLEDGE`
and `IDLE`:

| | `IDLE` | `HOLD` |
|---|---|---|
| there is an active walk | no | **yes** |
| asks a question | no | no |
| stamps `presented` / `response` | no | no |
| applies progress | no | no |
| legacy browser block | **left standing** | **suppressed** |
| renders | nothing | a short block that asks nothing |

`HOLD` renders TEXT rather than `""` on purpose. An empty string would still suppress —
suppression keys off the validated plan, not the rendered bytes — and that is precisely
the shape mutation **C6** exists to punish: working instructions removed with nothing in
their place. The held block is the replacement. It names no topic, contains no question
mark, and makes no claim about progress; naming the parked question is one edit away
from asking it.

`HOLD` is validated like every other action. A held plan naming an unknown topic is a
malformed payload and falls back to rendering nothing AND suppressing nothing — so
`hold` cannot become a way to delete the legacy block by sending junk.

### Which turns HOLD

* every ineligible turn **on an active walk** — the nine deterministic paths, system
  directives, cancelled turns;
* every ineligible turn with **no** active walk stays `IDLE` — historical, `pending`,
  `paused`, `completed`, or a state too malformed to plan against. Those four are what
  the byte-stability tests pin, and they do not move.

### How a conversation control is identified — ONE vocabulary, not a second list

The classifier reported, measured:

```
"repeat that"     -> addressed
"say that again"  -> addressed
"pause"           -> addressed
"help"            -> addressed
"change narrator" -> addressed
```

Every one of those **closed the open topic**. A narrator asking to hear the question
again would have had it recorded as answered and never hear it again.

The rule "everything else non-empty is `addressed`" (§12) was written against ANSWERS of
varying quality, and refusing to grade answers is right. **A control is not a
low-quality answer.**

A whole-turn control detector already existed, privately, in `trip_story_capture.py` —
written after "say that again" was saved as a Bismarck travel note on 2026-07-31. It has
been **extracted, not copied**, into `services/conversation_control.py`;
`trip_story_capture` imports it and a test asserts both modules resolve to the SAME
function object. Two lists agree on the day they are written and never again, and the
first divergence here would be a turn trip capture correctly skips and onboarding
records as `addressed`.

The shared vocabulary gained exactly two families, both named in the review: **`help`**
and **`change`/`switch narrator`**. Both are the narrator operating the conversation by
that module's own definition, so honouring them is the same rule applied, not a new one.

Two intents, both stationary, differing only in what Lori does next:

| Intent | Examples | Plan |
|---|---|---|
| `CONTROL_REPEAT` | "repeat that", "say it again", "what was that", "louder", "slower" | **`RE_PRESENT`** — a new presentation at the current version, no response event |
| `CONTROL_HOLD` | "pause", "stop", "help", "change narrator", "never mind", "go on" | **`HOLD`** — asks nothing, stamps nothing |

The split is deliberately lopsided: REPEAT is enumerated and everything else that is a
control falls to HOLD, because HOLD is the conservative outcome. Mis-filing a control as
HOLD costs one turn without a question; mis-filing it as REPEAT asks a narrator who said
"stop" the onboarding question again.

**A deferral still beats a control.** "hold on" and "just a minute" are in both
vocabularies. Step 3's accepted rule for a request for time is to come back to the
question gently, and that is unchanged — a narrator who says "hold on" is still working
on the answer, and falling silent on them would be a regression dressed as a correction.

### The anchoring is the whole design

Every one of these words appears inside real narration — "we had to GO BACK to the
hotel", "she would SAY THAT AGAIN every Christmas", "we STOPPED at the school and
CONTINUED to the cemetery". A substring match would eat all three. The pattern matches
the ENTIRE normalised turn with nothing before it and nothing after it but politeness,
under a six-word ceiling as a second wall. A turn that is a command says only the
command; a turn that is a memory says more.

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

## 8. (renumbered)

*What was §8, "What I have NOT done", is now §15 — the amendments were appended above it so
that the section numbers §9–§13 the reviews refer to stay stable. The number is left
standing rather than closed up, because silently renumbering sections that other documents
cite by number is how a cross-reference stops meaning anything.*

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
new accessor is needed.**

### ONE EVENT TYPE IS NOT ENOUGH — corrected 2026-08-26

*(This section first proposed a single `presented` event that was RE-STAMPED after a
response. The review found the defect and it is real: one event type cannot distinguish
**"Lori presented A"** from **"the narrator answered A and Lori acknowledged it"**. A
re-stamp on the acknowledgement turn leaves the presentation looking outstanding, so the
NEXT turn treats an already-consumed question as still open — and worse, the
acknowledgement turn itself would be composed as though A still needed asking, so Lori
would ask A again in the very breath she acknowledged the answer to it. Two events, not
one restamp.)*

### Two durable event types

Both live in the assistant row's `meta_json`, both are scalars, neither carries prose.

```python
# Lori PRESENTS a topic
"profile_seed_presented_topic":   <topic_id>
"profile_seed_presented_version": <int>

# Lori ACKNOWLEDGES a response to a previously presented topic
"profile_seed_response_topic":      <topic_id>
"profile_seed_response_version":    <int>
"profile_seed_response_disposition": "addressed" | "declined"
```

The response event is what makes §13 **genuinely** retryable. Topic and version alone
cannot reconstruct *whether the answer was `addressed` or `declined`* — a retry reading
only a presentation event would have to re-derive the disposition from the narrator's text
a second time, and could reach a different answer than the one the narrator was actually
given. The disposition is committed alongside the turn it describes.

### Correlation is on the EXACT `(topic_id, version)` TUPLE — corrected 2026-08-26

*(This section said "the same topic". That is not tight enough, and the case it misses is
ordinary rather than exotic: **the same topic can stay active while the version moves.**
Phase 1's `reconcile` bumps the version whenever effective stored state changes, so an
operator entering an unrelated fact, a superseded row, or a pause and resume all advance
the version with `siblings` still active. A response carrying the old version must not
consume — or apply against — a presentation minted at the new one.)*

Everywhere below, consumption and staleness compare the **tuple**:

```
consumed  iff  (response.topic, response.version) == (presented.topic, presented.version)
stale     iff  (outstanding.topic, outstanding.version) != (active_topic, current_version)
```

Not `topic != active_topic`. The version is half the identity of a question.

### The reduction

Scan `history` in committed row order. **The OUTSTANDING presentation is the latest
`presented` event for which no later `response` event carries the same
`(topic, version)` tuple.**

```
COMPOSE (chat_ws.py:4371-4375)
  RECOVERY FIRST — see "Recovery" below. It can change what follows.

  resolve -> status, active_topic_id A, version V
  outstanding = reduce(history)     # presented tuples minus exactly-consumed ones

  status != "active"
      -> render nothing. advance nothing.

  outstanding is None
      -> PRESENT. Render exactly A.
         Stamp presented(A, V) on THIS assistant row.
         ADVANCE NOTHING.                          <-- the self-advancing bug, closed

  (outstanding.topic, outstanding.version) != (A, V)
      -> STALE. Either the topic moved, or the SAME topic was re-versioned
         underneath the question by an operator entry, superseded evidence,
         or a pause/resume. Abandon the outstanding presentation, present A
         fresh, stamp presented(A, V). ADVANCE NOTHING, and never apply a
         disposition against a tuple that no longer exists.

  (outstanding.topic, outstanding.version) == (A, V), STATIONARY  (see 12)
      -> RE-PRESENT gently. Stamp presented(A, V) again — a NEW presented
         event at the current version. ADVANCE NOTHING.
         (A deferral is not an answer, so the question stays open.)

  (outstanding.topic, outstanding.version) == (A, V), ADDRESSED or DECLINED
      -> ACKNOWLEDGE. Lori responds to what the narrator said.
         SHE DOES NOT RE-ASK A. SHE DOES NOT ASK B.
         Stamp response(A, V, disposition).   # V is the OUTSTANDING version
         NO presented event on this row.
COMMIT
POST-COMMIT (see 13)
      -> apply(A, V, disposition)

NEXT TURN
      -> the response tuple consumed the presentation tuple, so `outstanding`
         is None again, the resolver returns the NEW active topic B, and B is
         presented on its own turn.
```

### Recovery — a committed response whose apply never landed

*(Added 2026-08-26. §13 described durable retry and the state machine did not implement
it, which meant the words and the algorithm disagreed. The review is right that what the
machine actually did was **repetition, not retry**: the response event consumes the
presentation, onboarding still has `(A, V)` active, the next reduction finds nothing
outstanding, and the machine presents A again — asking a narrator a question they had
already answered, with their answer sitting committed one row above.)*

**Recovery runs BEFORE composition, every turn, and can change what gets presented.**

```
RECOVER (before resolve)
  last_response = latest committed response event in history
  if none                    -> nothing to recover. proceed.

  state = resolve(person_id)                       # authoritative
  if (state.active_topic, state.version) == (last_response.topic,
                                             last_response.version):
        # The apply never landed. Onboarding still believes this question
        # is open, and the narrator has already answered it.
        RETRY apply(last_response.topic, last_response.version,
                    last_response.disposition)
        on success  -> resolve AGAIN. present the new B.
        on conflict -> the state moved for some other reason. ACCEPT the
                       authoritative state. NEVER force the stored
                       disposition onto a tuple it no longer matches.
  else
        # Already applied on the original turn, or superseded. Nothing owed.
        proceed with the authoritative state.

  if the recovery READ ITSELF fails (storage fault)
        -> REFUSE COMPOSITION, visibly. Do not fall back, do not
           silently re-ask. Phase 1's rule holds: a storage fault must
           never become an onboarding decision, and "ask it again" is an
           onboarding decision.
```

The recovery is **idempotent by the same mechanism as everything else**: it applies a
tuple, and Phase 1's `profile_seed_apply` refuses a stale one. Running it on every turn
when there is nothing to recover costs one resolve, which the turn was doing anyway.

### Why B is not asked on A's answer turn

**Until the post-commit apply succeeds, B is a prediction, not a fact.** Composition
happens before the commit; the apply happens after it. If Lori asks B in the same breath
she acknowledges A, and the apply then fails or conflicts, she has asked a question the
server does not believe is active — and the next resolve may hand back A or a different B
entirely. The narrator would be answering a question that no longer exists.

Asking one thing per turn is also the work order's own §4.5 rule ("one question per turn,
no menu") and matches how a person actually listens: you acknowledge what someone just
told you before moving on.

**The cost is honest and should be named: this makes the acknowledgement turn a turn
without a question in it.** In Phase 2 that is correct and slightly stilted. **Phase 3 can
initiate the next presentation automatically** once the browser is wired, so the narrator
experiences a natural "thank you — and tell me about…" rather than a pause. That is
deliberately deferred rather than faked here.

### The version applied

The version applied is **the one stamped on the assistant row that asked the question**,
not the one read at composition. A duplicated hook re-applies the same topic at the same
version and gets `VersionConflict` from Phase 1's `profile_seed_apply`, which writes
nothing. A retry after a crash re-derives topic, version *and* disposition from the
committed response event, so it applies exactly what the narrator was told had happened.

---

## 12. `addressed` versus `declined` versus stationary

The map excluded deterministic and meta turns and stopped there. It has to go further,
because **treating every model-path message as an answer is a way of not listening.**

### Two refusal vocabularies already exist, and neither is quite right

* `extract._apply_refusal_guard._REFUSAL_PATTERNS` (`routers/extract.py:6862–6873`) —
  **eight** regexes for explicit topic and privacy refusal: *"I'd rather not get into that"*,
  *"not for putting in a book"*, *"nothing I want to go into"*. **This is what `declined`
  means** and Phase 2 should reuse it rather than write an eighth list.
* `thread_bank.DECLINATION_PATTERNS` (`services/thread_bank.py:136–152`) — fifteen
  substrings, but it **mixes refusal with forgetting**: *"can't recall"*, *"nothing comes
  to mind"*, *"I don't remember much"* sit beside *"I'd rather not"*. For surfacing a
  banked thread that conflation is harmless. Here it is not, and reusing this list whole
  would be the mistake.

### THE RULED CLASSIFICATION — decided 2026-08-26, not by me

| Narrator response to the outstanding topic | State |
|---|---|
| Explicit privacy or topic refusal | `declined` |
| Explicit inability to remember or know | **`addressed`** |
| Clear TEMPORARY deferral — "let me think", "give me a moment", "come back to that" | **stationary** |
| Empty / system directive / control / meta / cancelled / failed turn | stationary |
| Any other non-empty interview response to a previously presented topic | `addressed` |

**"I don't remember" is `addressed`, and the recall difficulty is written nowhere.** This
keeps the walk finite and stops the system confronting an older narrator, session after
session, with something they cannot presently reach. It asserts no biographical fact — the
progress row records only that the topic is closed, and the ordinary committed
conversation is still there for a memory that surfaces later on its own.

**No word-count threshold.** `thread_bank._SUBSTANTIVE_WORD_COUNT = 30` (`:156`) exists for
a different job and is not borrowed: *"Devils Lake, North Dakota"* is four words and
completely answers the childhood-home question, while thirty words of *"oh goodness, let me
think, that was such a long time ago now"* answers nothing. **The ruling deliberately
favours narrator dignity over algorithmically grading answer quality.** Thin evidence is
the operator review surface's problem, later; it is not a reason to keep asking.

**The deferral category is narrow ON PURPOSE.** "Let me think about that" is the one case
where the narrator has explicitly said they are still working on it, and re-asking is
responsive rather than deaf. Everything vague, hesitant or short falls to `addressed` —
because the failure mode being guarded against is asking again, not recording an incomplete
answer.

### The refusal patterns move to a shared helper — they are not copied

`_REFUSAL_PATTERNS` is currently a local list inside `_apply_refusal_guard`
(`routers/extract.py:6862–6873`), so it cannot be imported. Phase 2 moves it into one
shared module — proposed `server/code/api/services/narrator_refusal.py`, free of FastAPI
imports like every other service this lane has added — and **both** extraction and Profile
Seed call it. A second copy of the list is exactly how the two would drift into disagreeing
about what a refusal is, which would mean Lori's extractor and Lori's onboarding treating
the same sentence differently.

`_apply_refusal_guard` keeps its behaviour precisely: same patterns, same order, same
`return []` on a match, same log line. It has **one** caller (`extract.py:7038`).

**One honest gap to close while moving it.** I searched for unit coverage of
`_apply_refusal_guard` and found none — its only exercise today is through the eval case
banks in `data/qa/`. Moving code with no unit-level net under it is how behaviour changes
without anyone noticing, so Phase 2 adds a characterization test over all EIGHT patterns
**before** the move, then re-runs it after. That test is not new coverage for its own sake;
it is the thing that makes the move provable.

### `thread_bank.DECLINATION_PATTERNS` is NOT reused

It is not deleted or changed either — it keeps doing its own job for banked threads. But it
is not the vocabulary for this, because it puts *"can't recall"*, *"nothing comes to mind"*
and *"I don't remember much"* in the same list as *"I'd rather not"*. Under the ruling
above those are opposite outcomes: forgetting is `addressed`, refusing is `declined`.
Borrowing the list whole would record a narrator's memory loss as a refusal to speak.

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
* **it is retryable and idempotent, and §11's RECOVERY stage is what performs the retry.**
  Topic, version and disposition are all on the committed assistant row, so the next turn
  re-derives them from durable state rather than from anything held in memory. Recovery
  runs before composition, compares the authoritative `(topic, version)` against the
  committed response tuple, and re-applies only if onboarding still believes that question
  is open.

  *(This bullet said the failure "costs one repeated question next turn". **That was
  false, and it was the sentence that hid a missing transition.** Without a recovery stage
  the next turn does not retry anything: the response event has consumed the presentation,
  onboarding still has the old tuple active, the reduction finds nothing outstanding, and
  the machine presents the same question again — asking the narrator something they had
  already answered, with their answer committed one row above. That is repetition wearing
  retry's clothes, and describing it as a small cost was how it went unnoticed. With §11's
  recovery, the cost is one extra resolve.)*
* **the narrator sees nothing.** They have already been answered. Recovery happens before
  the next composition, so in the ordinary case they never learn anything went wrong.
* **archive, extraction, story and trip hooks keep their existing behaviour**, gated
  exactly as they are today on `_persisted_turn_row_id` / `_persisted_user_turn_row_id` /
  `_archive_event_persisted`. Advancement adds no key any of them reads.

---

## 14. Required tests, folded in

Beyond the review's list, these fall out of the sections above:

* **the first presentation advances nothing** — the §11 self-advancing bug, named;
* **an acknowledgement turn re-asks nothing** — the assistant row carries a `response`
  event and NO `presented` event, and the rendered prompt contains neither A's question nor
  B's;
* **a response event consumes its presentation** — the following turn reduces to
  `outstanding is None` and presents B, once;
* **a deferral leaves the presentation outstanding** — "let me think" re-presents A and
  applies nothing;
* **a retry reconstructs the disposition** — a crash between commit and apply, replayed
  from the committed `response` event, applies `declined` where the narrator declined and
  `addressed` where they answered. This is the test that justifies storing the disposition
  at all;
* **a stale presentation is abandoned, not applied** — evidence answers A between
  presentation and response; the outstanding presentation is dropped and nothing is written
  against it;
* **SAME TOPIC, NEW VERSION does not advance** — `siblings` stays active while the version
  moves (an unrelated operator entry, a superseded row, a pause and resume). A response
  carrying the old version must neither consume the new presentation nor apply against it.
  This is the case a topic-only comparison silently gets wrong;
* **recovery retries a committed response whose apply never landed** — the turn after a
  post-commit failure re-applies the stored disposition and presents B, rather than
  re-asking A;
* **recovery accepts an authoritative conflict** — if the state moved for some other
  reason, the stored disposition is NOT forced onto a tuple it no longer matches;
* **a recovery read failure refuses composition visibly** — it does not fall back and does
  not silently re-ask, because "ask it again" is an onboarding decision and Phase 1's rule
  is that a storage fault must never make one;
* **three REST prompts are byte-identical** before and after Phase 2 (ownerless,
  historical, completed) — §10, with `/api/warmup` and the translation caller;
* **an owner/claim mismatch refuses and composes nothing** — §9;
* **a characterization test over all EIGHT refusal patterns**, landed in its own commit
  BEFORE the shared-helper move and re-run after — §12;
* **forgetting is not refusing** — "I can't recall" resolves `addressed`, not `declined`,
  and nothing about the recall difficulty reaches `topic_state_json`.

And a control on the tests themselves: **every new guard gets a mutation.** Four are
mandatory, and each is a design this map actually carried at some point:

1. removing the `outstanding is None` check must fail the first-presentation test;
2. re-stamping `presented` on an acknowledgement turn must fail the consumption test;
3. **comparing `topic` instead of the `(topic, version)` tuple** — in either the
   consumption or the staleness check — must fail the same-topic/new-version test;
4. **disabling the recovery stage** must fail the retry test, and the failure must be that
   A is re-asked rather than B presented.

Mutations 1, 2 and 3 were each the live design of this document until a review caught
them, and 4 was described in §13 without existing anywhere in §11. A suite that would not
have noticed any of the four is not worth having. Two instruments in this lane have
already measured themselves instead of the code, which is why the mutations are named here
rather than left to judgement at implementation time.

---

## 15. Implementation status — THIS MAP IS NO LONGER A PLAN ONLY

*(This section read "No code, no schema, no tests, no migration" and "Awaiting the
implementation-readiness review before Phase 2 code begins." Both became false at step 1
and are substantially false now. This document was missed by four rounds of
control-document reconciliation because the sweep covered four files and there are FIVE —
this map is a control document too, and a stale one says the code it describes does not
exist.)*

**Phase 2 is IN IMPLEMENTATION and is NOT ACCEPTED.**

| Step | State |
|---|---|
| 1 — characterize the eight refusal patterns | landed |
| 2 — one shared refusal helper | landed |
| 3 — turn state machine, exact tuples, recovery | landed |
| 4 — isolated composer section | **ACCEPTED** at `b269184` (landed `620d692`; `9f31d9f` was premature) |
| 5 — REST read authority | **ACCEPTED** at `9127adb` (landed `687c655`) |
| 6 — WebSocket presentation metadata and advancement | 🔵 **CURRENT ACTION** |
| 7 — suites and control reconciliation | not begun |

The commit ledger lives in the primary work order's status block, not here — one home, so
a new commit does not make five documents stale at once.

**UPDATED AT STEP 5 ACCEPTANCE.** REST wiring HAS landed: `/api/chat` and
`/api/chat/stream` supply `profile_seed_onboarding` for composition, on the READ side only
— they **advance nothing**. Verified against the running API, and by a zero-skip route run
in `.venv-gpu` that entered both route functions for all three refusals.

*(The previous wording — "no live transport supplies `profile_seed_onboarding`" — is
retired as FALSE. It was true through step 4 and stopped being true at `687c655`.)*

**The boundary that replaces it:** the narrator product path is still unwired. The UI drives
`/api/chat/ws`; a complete narrator turn makes zero HTTP requests matching "chat".
`/api/chat` has no UI caller, and `/api/chat/stream` is reachable only behind the dev-only
`window.LV_ALLOW_SSE_FALLBACK`. **Step 6 is what puts the walk in front of a narrator using
the production UI** — the walk is already live over REST. The eight browser promotion sites are untouched — that is Phase 3
— and nothing in chronology, Life Map, memoir or story authority, safety, model or context
window, the directive registry, Kawa, or migrations `0001–0051` has changed.

**Design rulings, all settled:** Option B is the accepted transport-scope ruling; §9, §10
and §13 are accepted; §12 is ruled; §11 carries exact `(topic, version)` correlation and
the recovery stage.

---

## 16. Pre-Step-6 correction checkpoint — ACCEPTED at `d0e5294`

**Accepted 2026-08-28.** The checkpoint is three commits:

| Commit | What |
|---|---|
| `157af46` | the five product corrections below |
| `34cdf54` | acceptance-instrument corrections — route-stack guard, duplicate-collapse inventory |
| `d0e5294` | the remaining instrument corrections; **the acceptance point** |

Step 6 was **blocked** by a review of the pushed Step 5 tree. Five bounded defects, none
of them narrator-reachable through the production UI, because WebSocket onboarding is
still unwired. All five are closed and accepted.

| # | Defect | Closed by |
|---|---|---|
| 1 | `M1` disabled the first-presentation branch and crashed with `AttributeError`; `M8` retried against a permanently-raising recorder. Both `BROKEN` — errors only, nothing asserted | `M1` now returns the defective ACKNOWLEDGE plan; `_Recorder` gained `raise_once` so the illicit second apply SUCCEEDS and is observable. Both fail by assertion |
| 2 | `expected_version` coerced: Pydantic turned `true` into `1`, `db.profile_seed_apply` called `int()`. **Reproduced: a pending narrator at version 1 accepted `True` and moved to version 2** | `StrictInt` on the request model, a type check in the accessor, `tests/test_profile_seed_expected_version_strict.py`, mutation `P11` |
| 3 | §6 said six deterministic paths; there are **nine** | §6 rewritten above; `tests/test_profile_seed_deterministic_paths.py`; mutations `D1`–`D3` |
| 4 | `eligible=False` returned `IDLE`, reviving the legacy browser block mid-walk; controls classified `addressed` | §6b above: the `HOLD` action and `services/conversation_control.py`; mutations `H1`–`H7` |
| 5 | `HANDOFF.md` named a hash as "current `main`" | replaced with `git rev-parse origin/main` |

### 16a. Two ACCEPTANCE-INSTRUMENT defects found reviewing `157af46` — 2026-08-28

The five product corrections were reviewed and found sound. Two of the instruments
proving them were not — **and they failed in OPPOSITE directions, which is the part worth
recording.**

* **Defect 6 failed LOUDLY.** It did not report success: it produced **eight errors**, and
  `run_mutation_gate.py --only P11` then **refused its red baseline**, so the mutation
  could not run at all. That is the gate working correctly against a broken instrument.
  The damage was that a mutation could not be exercised, not that a false pass was issued.
* **Defect 7 failed SILENTLY, and only defect 7.** The inventory counted distinct modes,
  called them paths, and **reported green** on a tree carrying a tenth path.

*(This section first said both "failed in the direction that reports success". That is
true of exactly one of them, and flattening the two together loses the distinction that
decides how worried to be: a loud instrument failure costs a run, a quiet one costs the
guarantee. Corrected 2026-08-28.)*

| # | Instrument defect | Closed by |
|---|---|---|
| 6 | **The strict-version suite checked `pydantic` and not `fastapi`,** while promising skips for unavailable route dependencies. On an ordinary interpreter with pydantic present and fastapi absent it produced **8 ERRORS**, and `run_mutation_gate.py --only P11` then correctly refused its red baseline — so the mutation could not run at all | `_ROUTE_DEPENDENCIES = ("pydantic", "fastapi")`; `_dependency_unavailable()` and `_router_import_unavailable()` skip ONLY for a `ModuleNotFoundError` whose missing root IS the dependency being imported, and re-raise everything else; nine `RouteGuardTests` that run on every interpreter, including the ones that skip |
| 6b | **The narrowing was applied to the router import and NOT to the dependency sweep above it** — the same defect, one call earlier, in the half that had no tests. A circular-import fastapi failure came back as `fastapi is not installed (cannot import name 'X' from partially initialized module 'fastapi')` | `_dependency_unavailable()` catches `ModuleNotFoundError` only, requires `exc.name` to BE the dependency (so a missing `starlette` under `import fastapi` re-raises as the broken install it is), and has four direct controls of its own |
| 7 | **The nine-path inventory collapsed duplicates.** `_deterministic_sites()` returned a dict keyed by `turn_mode`, so two call sites sharing a mode overwrote one another and the file counted DISTINCT MODES while claiming to count PATHS | a `Site` sequence in source order; assertions on the number of call sites, on each mode occurring exactly once, on no unlisted mode, and on each site's classification; a synthetic duplicate positive control; mutation **`D4`** |

**Why 7 mattered more than it looks.** It falsified this map's own headline guarantee —
"a tenth path fails a named test rather than joining silently" — in precisely the case a
tenth path is likeliest to arise: a branch copied from an existing one that keeps its
predecessor's `turn_mode`. Measured against the mutated tree, the old extractor reported
**9 sites and passed**; the corrected one reports **10 and fails**.

**Why 6 mattered.** A skip guard is the one part of a suite nothing else checks. Wrong in
the permissive direction it errors loudly; wrong in the other direction it reports `OK`
having measured nothing. The correction also refuses to treat an arbitrary router-import
failure as a skip — a circular import introduced by Step 6 is a defect, not an
environment fact, and must not be able to silence this suite.

Two-environment proof, required and produced:

| Interpreter | Result |
|---|---|
| generic, real `pydantic`, no `fastapi` | `OK (skipped=5)` — five route tests skipped, each naming `fastapi` |
| real `fastapi` + `pydantic` route stack | `OK`, **zero skips** |

**Step 6 is still NOT STARTED, and its design below is unchanged by this acceptance.**
It is additionally frozen behind the repository-hygiene checkpoint — see `HANDOFF.md`.

**Deliberately NOT touched, and this is the boundary that makes the checkpoint
reviewable:** the WebSocket wiring itself, the eight UI promotion sites, REST
persistence, safety, model/window, chronology, Life Map, memoir, story authority,
migrations, the directive registry and Kawa. `chat_ws.py` is **byte-identical** — the
nine-path guard reads it as source and parses it, which is also why that guard needs no
`fastapi` and skips on no interpreter.

**What Step 6 inherits, and must not undo:**

* the nine-path inventory, and the test that fails if a tenth appears;
* `HOLD` for every ineligible turn on an active walk — Step 6 supplies `eligible`, it
  does not re-decide what ineligibility means;
* one control vocabulary, in `conversation_control`;
* `expected_version` strict at both layers — the WebSocket path calls the accessor
  directly and inherits the second one, not the first.

`tests/test_profile_seed_deterministic_paths.py::Step6TripwireTests` will FAIL the moment
Step 6 adds Profile Seed metadata to `chat_ws.py`. That is deliberate: narrow it to the
model path, and leave the nine deterministic paths covered.
