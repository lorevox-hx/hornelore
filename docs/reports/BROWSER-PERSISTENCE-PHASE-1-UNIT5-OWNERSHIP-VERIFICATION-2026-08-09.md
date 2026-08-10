# Phase 1 — Unit 5: writer + reader + shape verification

**2026-08-09 · READ-ONLY.** No code changed, no schema changed, no browser key touched,
**no narrator turn taken**. Static trace against the seven-point standard.

**Result: 1 of 8 mappings survives verification.** Four have **no server owner at all**, two
are **wrong owners**, one is **conditional**. The Phase 1 headline — *"this is mostly wiring,
not schema"* — is now decisively dead, and this report retires it.

---

## 1. The table

| browser key | proposed owner | classification |
|---|---|---|
| `lorevox_proj_draft_<pid>` | `interview_projections` | ✅ **VERIFIED SAME SEMANTICS** |
| `lorevox_qq_draft_<pid>` | `bio_builder_questionnaires` | 🟡 **PARTIAL** — flag-gated write, read path can bypass |
| `lorevox_offline_profile_<pid>` | `profiles` | 🟡 **PARTIAL** — cache *and* independent write path |
| **`lorevox.spine.<pid>`** | `timeline_events` / `life_phases` | 🔴 **NO OWNER** |
| **`lv_done_<pid>`** | `interview_sections` / `interview_sessions` | 🔴 **NO OWNER** |
| **`lorevox_ft_draft_<pid>`** | `graph_persons` / `graph_relationships` | 🔴 **NO OWNER** |
| **`lorevox_lt_draft_<pid>`** | `interview_threads` | 🔴 **WRONG OWNER** |
| **curator identity** | photo/media provenance columns | 🔴 **WRONG OWNER** |
| `lorevox_qc_draft_<pid>` (Quick Capture) | — | 🔴 **NO OWNER** (unchanged; none invented) |

**Five of the nine now have no valid server home.** Phase 1 listed six of these as
plausible on the strength of table names and row counts. **The standard caught all six.**

---

## 2. 🔴 The spine is never transmitted — and this decides Unit 6

The single most consequential finding.

- **Writer:** `state.js:522` `saveSpineLocal()` — bare object
  `{birth_date, birth_place, periods:[{era_id, label, start_year, end_year, is_approximate, places[], people[], notes[]}]}`.
  (`LS_SPINE` is at `state.js:518`, **not** `app.js` as my Phase 0 census said.)
- **Reader:** `state.js:526` → consumed `app.js:3381–3392`, where it sets
  `state.timeline.spine`, `seedReady = true`, calls `setEra(...)` and **promotes `pass1 → pass2a`**.
- **Server writer: NONE.** *"grep for `spine` across `ui/js/*.js` returns zero fetch/API
  references."* The spine never leaves the browser.
- `life_phases` has a writer (`db.add_life_phase`, reachable via `POST /api/calendar/phase/add`)
  with **no UI caller** — grep for `api/calendar` in `ui/js/` returns nothing.
- **Shape:** `periods[]` carry `era_id`, integer years, `places[]`/`people[]`/`notes[]`.
  `life_phases` has `title`, TEXT dates, `description`, `ord` — no era key, no arrays, no
  integer years. `birth_date`/`birth_place` have no column anywhere.

> **The condition that promotes a narrator from `pass1` to `pass2a` is a browser blob with no
> server representation whatsoever.** Not an under-populated table — no transmission path at
> all.

This is the mechanism behind the finding I withdrew twice. Phase 8 §10 claimed Chris avoids
the Profile Seed conflict *"because his browser has a cached spine"*; that was withdrawn as
unproven, and Phase 1d refused to conclude it from a current absence. **Unit 5 supplies the
missing half by tracing the setter rather than inferring from a value:** a cached spine *can*
promote `pass2a` unilaterally, from data the server has never seen. Whether it did so in
Chris's session is still Unit 6's question — but the mechanism is now observed, not supposed.

---

## 3. 🔴 `lv_done_<pid>` — the concept does not exist server-side

- **Writer:** `interview.js:120` `persistSectionDone()` — a **bare positional boolean array**
  (`[false, true, false, …]`, 37 slots) indexed against the client constant
  `INTERVIEW_ROADMAP` (`data.js:25+`).
- **Reader:** `app.js:3364` — drives checkbox state, auto-advance of `sectionIndex`, progress
  counts, per-chapter *"Ready for draft"* vs *"Limited source material"* labels
  (`app.js:4423–4426`), and the done-list injected into memoir/draft context strings.
- **Server writer/reader: NONE FOUND.** *"grep for `section_done|sectionDone|sections_done|
  section_complete` across `server/**/*.py` returns zero hits."*
- **Grain mismatch is disqualifying on its own:** `interview_sections` is `(id, plan_id,
  title, ord)` — **keyed by `plan_id`, with no `person_id` column at all.** It is a static
  plan catalogue. There is no join key between a roadmap index and `interview_sections.id`,
  and **neither candidate table has a completion column.**

This one reaches memoir-draft readiness labelling, so it is not cosmetic.

---

## 4. 🟡 The two partials, and why neither is a simple lift

**`lorevox_proj_draft_<pid>` → `interview_projections` — ✅ the one clean mapping.** The same
`{fields, pendingSuggestions}` object goes to `PUT /api/interview/projection` →
`upsert_projection` (`db.py:5230`) and returns via `get_projection` (`db.py:5202`), at
identical per-person grain (`person_id` is the PRIMARY KEY). Server-side it is genuinely
consumed — `prompt_composer.py:934–960` reads `fields[…].value` and `pendingSuggestions`.
Deltas are envelope-only: the LS `{v,d}` wrapper, and a Pydantic-injected empty `syncLog` the
browser never sends and ignores on read.

**`lorevox_qq_draft_<pid>` — conditional ownership, in both directions.** The legacy blob
write is gated on `HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE` (default on); with it off the
route echoes and **writes nothing**. Separately, `get_questionnaire` (`db.py:5120–5127`) can
short-circuit to `bio_questionnaire_view.build_questionnaire_view()` and **never touch the
table** — so the server can return a questionnaire assembled from `bio_facts` + `profile_json`
while the browser's copy still reflects the legacy blob. Also worth recording: the browser
carries a **double-wrap repair** (`bio-builder-core.js:310–315`), meaning `{v,d:{v,d:{…}}}`
has occurred in the wild; the server has no such guard and would store it verbatim.

**`lorevox_offline_profile_<pid>` — the label "offline fallback" is only half true.**
`app.js:3345` and `:3981` write it as a genuine read-cache after a successful GET. But
`narrator-preload.js:598` and `:701` write a **narrower** `{basics, kinship, pets}` blob —
no `person_id`, no STRUCTURED_KEYS — and those `setItem` calls sit **outside** the try/catch
around the server PUT, so they run **even when the PUT fails**. That is an independent write
path with a lossier shape than server truth.

**The live consequence is a silent data-loss path, and it is worth stating plainly.** On a
failed fetch the reader (`app.js:3351–3357`) hydrates from cache and sets `profileSaved =
true`; a later `saveProfile()` (`app.js:3931`) sends only `{basics, kinship, pets}` — so
every STRUCTURED_KEY the cache preserved (`parents`, `siblings`, `spouses`, `children`, …)
**is dropped on the way back to the server.** An API blip can therefore narrow a narrator's
stored profile. I have **not** confirmed this has happened; the path is observed, the
occurrence is not.

---

## 5. 🔴 The two wrong owners

**Life Threads → `interview_threads` is a different concept.** The draft is a per-person,
operator-authored graph: nodes `{id:"ltn_…", type, label, text, notes, source, sourceRef}`
**plus an `edges` array**. `interview_threads` (`migrations/0009`) is
`(id, session_id, tenant_id, thread_anchor, source_turn_index, source_excerpt, introduced_at,
status, surfaced_at, resolved_at, category)` — **session-scoped with no `person_id` column at
all**, no edge concept whatsoever, and populated exclusively by server-side transcript
extraction (`thread_bank.py:485`) for in-conversation surfacing. Nothing browser-side ever
reaches it.

**Curator identity → provenance columns: the value has no referent.**
`media-archive.js:124` and `photo-intake.js:247` each mint `"curator_" + random`, **two
independent identities for the same human on the same device**, with nothing synchronising
them. Both are sent on every upload and PATCH. And:

> **There is no `users` table.** *"grep `CREATE TABLE IF NOT EXISTS users|REFERENCES users`
> across migrations and `db.py` returns zero hits."* `uploaded_by_user_id` is unconstrained
> free text with no FK, no CHECK and no lookup — the server never validates it.

The same column is also fed hardcoded **surface** labels from other lanes — `"operator"`,
`"narrator"`, `"travel_documenter"` — so it is a mixed identity/surface namespace. And
`last_edited_by_user_id` is **required** by the media-archive PATCH model (`min_length=1`) on
a table that **has no such column**: the value is validated, written to a log line, and
discarded.

This sits directly against the Picker doctrine's rule that identity must be explicit and
never inferred. **A random per-device pseudonym is not an identity, and the archive currently
attributes narrator material to it.**

---

## 6. Structural finding: six of these tables are not in `migrations/` at all

Reported because it changes how any future schema work must be done, and it was not known
before this pass.

`timeline_events` (`db.py:489`), `interview_sections` (`:518`), `interview_sessions` (`:547`),
`life_phases` (`:609`), `bio_builder_questionnaires` (`:5047`), `interview_projections`
(`:5063`), `profiles` (`:454`), `graph_persons` (`:5474`), `graph_relationships` (`:5505`) are
created **imperatively inside `init_db()` / `_ensure_phase_*_tables()`**, not by a numbered
migration. All 42 files in `server/code/db/migrations/` are trip / photo / story / extraction
scoped.

**So "read the migration" is not a reliable way to learn this schema**, and any Phase 2+
change to these tables has to decide whether it joins the imperative path or starts migrating
it. Not a decision for this phase.

---

## 7. What this changes

**The migration is smaller than feared and the redesign is larger.** Only one key can be
pointed at an existing owner and left alone. Five have no home, so Phase 6 is not a copy for
them — it is either *build the owner*, or *decide the state should not be durable at all*.

**Two of the five may not need a server owner:** the spine (§2) and `lv_done_` (§3) both look
like **derived** state in the sense Chris named early — computable from facts the server
already holds, rather than truth needing its own table. **That is the Unit 6 question and it
should not be prejudged here**; §2's contribution is that the *current* mechanism has no
server side, not that the future one needs a table.

**The discipline is what produced this.** Six mappings looked right on names and row counts;
one survived. Had Phase 2 started from the Phase 1 map, we would have built a hydration
boundary over five keys with nothing behind them.

---

## 8. Status

| unit | status |
|---|---|
| 1 — live browser inventory | ✅ `c884e22` |
| 2 — `lv_segs_` browser vs server | ⏸️ held |
| 3 — consent callers / writers | ✅ Phase 1c |
| 4 / 4b / 4c / 4d — voice truth chain | ✅ CLOSED · `afbfd01` · `1a608b7` · `aa058b7` · `e4414f3` |
| **5 — writer + reader + shape per mapping** | ✅ **this report** |
| 6 — progression: server condition + every `pass2a` setter + lifecycle | **next — and §2 is the key input** |
| 7 — final owner/migration map and minimal deltas | not started |

**Not traced, carried forward:** whether the `profiles` truth-v2 read path
(`profiles.py:66`) means the cache can hold a *derived* document no PUT can reproduce (§4,
flagged by the trace, not confirmed); Quick Capture still has no owner and none was invented.

---

## Corrections to earlier reports

| claim | status |
|---|---|
| **"this is mostly wiring, not schema"** (Phase 1 headline; already downgraded in Phase 1b) | **retired outright.** One of eight verified. |
| `lorevox.spine.<pid>` → `timeline_events`/`life_phases` (Phase 1 map) | **WRONG — NO OWNER.** Never transmitted; `life_phases`' only writer has no UI caller. |
| `lv_done_<pid>` → `interview_sections` (Phase 1 map) | **WRONG — NO OWNER.** No completion column; `interview_sections` is plan-scoped with no `person_id`. |
| Family Tree → `graph_persons`/`graph_relationships` — *"strengthened, not closed"* on 63/52 rows (Phase 1b) | **WRONG — NO OWNER.** Those rows come from `bb.graph`, derived from questionnaire + profile; the FT draft is never sent. **Row counts proved a table was used, not that it was this key's owner** — exactly the failure mode the standard exists to catch. |
| Life Threads → `interview_threads` — *"downgraded to hypothesis"* (Phase 1b) | **WRONG OWNER**, confirmed by shape and grain, not by the empty row count. |
| curator identity → media/photo provenance (Phase 1 map) | **WRONG OWNER.** No `users` table exists; the column is unconstrained free text shared with surface labels. |
| `LS_SPINE` located in `ui/js/app.js` (Phase 0 census) | **corrected** — `ui/js/state.js:518`. |
