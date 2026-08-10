# Phase 1b — ownership verified by writer/reader, not by table name

**2026-08-09 · READ-ONLY.** No code changed, no table created, no browser key deleted.
Profile Seed, progression behaviour and `LORI_INTERVIEW_DISCIPLINE` untouched.

Applies the two supervisor corrections to `144d9852`:

1. a table with a plausible name is **not** an ownership contract — verify producer, consumer
   and shape on both sides;
2. trace `lv_segs_<pid>` **independently** of `lv_done_<pid>`.

Both corrections found something. **The second overturns a row in my own map.**

---

## 1. 🔴 `lv_segs_<pid>` — my mapping was wrong, and it is a different subsystem

I grouped `lv_done_<pid>` and `lv_segs_<pid>` and mapped both to
`interview_sessions` / `interview_sections`. **I did that on name similarity — the exact
error the supervisor was warning about, one level down.**

Traced to producers, they are unrelated:

| key | producer | payload | subsystem |
|---|---|---|---|
| `lv_done_<pid>` | `interview.js:120` | `sectionDone` | interview structure |
| **`lv_segs_<pid>`** | **`safety-ui.js:151`** | **`sensitiveSegments`** | **safety** |

Readers likewise split: `lv_done_` is read in `app.js:3364`; `lv_segs_` is read by
`safety-ui.js:164 _loadSegments()`, called from both `app.js:3371` and `interview.js:893`.

**The correct server owner is `segment_flags`, and unlike most of this audit it is already
alive:**

```text
segment_flags   rows=9
  id, session_id, question_id, section_id,
  sensitive, sensitive_category, excluded_from_memoir, private, deleted, created_at

server writer : db.py:3968  save_segment_flag()          (INSERT OR IGNORE, :3997)
server readers: db.py:4022  get_segment_flags(session_id)
                db.py:4033  get_segment_flags_by_category(...)
```

**Two things follow, and the second is the more interesting.**

**(a) This is a dual-write with a populated server side.** Unlike consent, the server half is
not empty — 9 rows exist. So the browser copy is a *second* store of the same decisions
rather than the only one, and the two may already disagree. **Neither copy has been compared
against the other**, and that comparison belongs in Phase 1 before either is trusted.

**(b) The two sides are keyed at different grains.** `segment_flags` is scoped by
**`session_id`**; the browser key is scoped by **`person_id`**. A per-person browser blob and
per-session server rows are not the same shape, so this is **not** a lift-and-shift — someone
has to decide whether a sensitivity decision belongs to a session or to a person. *That is a
product question about whether "don't put this in the memoir" is a fact about one
conversation or about the narrator.* I am not answering it here.

**Why this matters more than a mis-filed row:** `excluded_from_memoir`, `private` and
`deleted` are decisions about what may be shown of someone's life. If the browser holds a
decision the server does not, **a cache clear can un-hide something a narrator asked to
keep private.** That moves `lv_segs_` up the priority list, next to consent.

---

## 2. 🔴 Consent: the server API is complete and has never been called

The supervisor asked for a more precise claim than *"the consent record exists only in
Chrome."* Here it is, and it is worse in an interesting way.

**A full server-side consent API already exists:**

```text
db.py:7023  consent_attestation_create(...)      → INSERT INTO consent_attestations (:7046)
db.py:7065  consent_attestation_list_for_narrator(...)
db.py:7111  consent_attestation_has_complete_set(narrator_id) -> bool

consent_attestations   rows = 0
```

So the correct statement is: **the facial-consent runtime persists grant/decline to browser
storage only, while a complete, purpose-built server attestation API sits unused and its
table is empty.** Not "nobody built it" — *built and never called.*

**And there is a live consequence I did not expect.** `consent_attestation_has_complete_set()`
exists to answer whether a narrator has a full set of attestations. Against an empty table it
**always returns false**. Whatever depends on that answer has been getting `false` for the
life of the feature. **Tracing that consumer is the next unit** — it may be inert, or it may
be a gate that has silently never opened.

---

## 3. Method correction, applied retroactively to my own claim

The supervisor is right that *"mostly wiring, not schema"* is too strong, and §1 proves it
concretely: `interview_sections` looked like the owner for `lv_segs_` and is not.

**Revised status of the Phase 1 map — three tiers, not one:**

| tier | meaning | rows |
|---|---|---|
| **VERIFIED** | producer, consumer and shape checked on both sides | `lv_segs_` → `segment_flags` (with the grain mismatch recorded); facial consent → `consent_attestations` (API verified, table empty) |
| **HYPOTHESIS** | table exists and is plausible; writer/reader/shape **not** yet compared | spine → `timeline_events`/`life_phases`; `lv_done_` → `interview_sections`; projection → `interview_projections`; questionnaire → `bio_builder_questionnaires`; profile → `profiles`; curator → `media_archive_*` |
| **STRENGTHENED, NOT CLOSED** | plausible **and** the server side holds real data | Family Tree → `graph_persons`/`graph_relationships` (63/52 rows) |
| **NO OWNER FOUND** | — | Quick Capture `lorevox_qc_draft_<pid>` |

**Life Threads → `interview_threads` moves from "mapped" back to hypothesis** — the table is
empty, so nothing about its actual use can be inferred from it, exactly as the supervisor
said.

**The general lesson, stated so it survives this report:** a populated table proves the
server side is *used*; an empty table proves nothing either way; and neither proves the
server table means what the browser key means. **Only the writer and the reader do.**

---

## 4. What this changes about priority

Consent was already first. `lv_segs_` now sits beside it, and for the same reason: both carry
decisions about what may be revealed of a person, and in both cases the browser is the only
place — or a divergent second place — where that decision lives.

Revised order for the remaining Phase 1 units:

1. **Live browser values, Quick Capture first** — still the highest, because it is the only
   category-A family with no server owner at all and may hold narrator-authored words.
2. **`lv_segs_` browser-vs-server comparison** — do the 9 `segment_flags` rows agree with what
   is in the browser, and does anything exist in one and not the other?
3. **Trace `consent_attestation_has_complete_set()`'s consumer** — is the always-false answer
   inert or load-bearing?
4. **Voice capture / persistence truth chain** — permission vs activity vs artifact.
5. **Writer/reader verification for every HYPOTHESIS row above.**
6. **Deterministic server progression condition.**
7. Then the owner/migration map with minimal schema/API deltas.

---

## Corrections to my own earlier reports

| claim | status |
|---|---|
| `lv_segs_<pid>` → `interview_sessions`/`interview_sections` (Phase 1 §map) | **WRONG — withdrawn.** Producer is `safety-ui.js`; owner is `segment_flags`. Grouped with `lv_done_` on name similarity. |
| "mostly wiring, not schema" (Phase 1 headline) | **too strong — downgraded.** One mapping already failed verification; most rows are hypotheses. |
| "the consent record exists only in Chrome" | **sharpened**: facial-consent runtime persistence is browser-only **and** a complete server attestation API exists, unused, against an empty table. |
| Life Threads → `interview_threads` | **downgraded to hypothesis** — table empty, nothing inferable. |
| "Family Tree suspicion withdrawn" | **stands, but as *strengthened*, not closed** — 63/52 rows make it plausible; shapes not yet compared. |
