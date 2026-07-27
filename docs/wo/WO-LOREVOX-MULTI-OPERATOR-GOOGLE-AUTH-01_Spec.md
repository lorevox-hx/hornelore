# WO-LOREVOX-MULTI-OPERATOR-GOOGLE-AUTH-01 — per-operator Google authorization

**Status: FUTURE DESIGN ONLY. Nothing here is implemented. Nothing here may be
implemented without Chris explicitly opening this work order.**

This file exists so the multi-operator shape is written down once, correctly,
while the picker lane is still small enough to reason about — and so that
nobody later "just adds a tokens table" in the middle of an unrelated phase.

---

## 0. Naming — why this file is not called "PHASE-2"

The handoff that produced this document proposed the filename
`WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-PHASE-2-MULTI-OPERATOR-AUTH-01_Spec.md`.
That name is not used, for one concrete reason:

**"Phase 2" of the picker lane already means something else, and it is already
committed.** In `docs/wo/WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md` §5,
in `CLAUDE.md`, and in `MASTER_WORK_ORDER_CHECKLIST.md`, **Phase 2 = the fetch
lane** (ingest, bytes, candidates — the phase that actually closes the hole).
Adding a second, unrelated "Phase 2" to the same lane would make every future
sentence containing the words "picker Phase 2" ambiguous.

So this design gets its own work-order name and no phase number. If Chris wants
the original filename anyway, say so and it will be renamed in one commit —
the content does not change either way.

---

## 1. The problem this solves

Phase 1 of the picker lane authorizes **one** Google Photos source account,
through **one** refresh token, held in **one** `.env` file, on **one** machine.
That is correct for a local single-operator proof and is explicitly blessed as
such.

It does not survive a second operator. The moment two humans use Lorevox, a
single shared refresh token means operator B is picking from operator A's photo
library — which is both wrong and a privacy failure.

---

## 2. The shape of the future model

- **Each Lorevox operator connects their own Google account.** Authorization is
  a property of the human who signed in, established by an interactive OAuth
  consent that *that human* completed.
- **Tokens are per-operator.** Never per-narrator, never per-person, never
  per-trip, never global.
- **Tokens are encrypted at rest**, with the key held outside the database.
- **Picker sessions use the active operator's token.** The session is opened
  with the credential of whoever is driving, and only that credential.
- **Selected photos can still be filed under any narrator/person/trip the
  operator is permitted to touch.** Source identity and destination identity
  stay orthogonal — this is the whole point.

That last bullet is the load-bearing one. Connecting a Google account changes
*where the bytes come from*. It does not change, restrict, or imply *whose
memoir they belong to*.

---

## 3. The rule this design must never break

Everything in `WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01_Spec.md` §10 applies here
unchanged and with more force:

> A Google account is not a Hornelore narrator. An operator is not a narrator
> unless a human explicitly selected that narrator as the destination. The
> application must never infer `person_id` or `trip_id` from the Google account.

Restated for the multi-operator case:

- Operator identity answers **"who is allowed to do this, and with whose
  library?"**
- `person_id` (+ optional `trip_id`) answers **"whose memoir does this land
  in?"**
- These are answered by different mechanisms and must never be wired together.
  A narrator does not sign in to Google. Many narrators cannot sign in to
  anything.
- `narrator_id` remains the `photos`-table column name for the same identity
  the import lane calls `person_id` (see §10.3 of the picker spec). It is not
  a separate destination field and must not become one here.

---

## 4. Sketch only — components that would be needed

Recorded so the scope is visible, **not** as an implementation plan. None of
this is designed to the level of a buildable spec, and none of it is built.

- An operator identity concept that actually exists as a first-class row.
  Phase 1 has no such thing; `created_by_user_id` is a free-text passenger
  field on a batch, not an authenticated principal.
- A per-operator credential store, encrypted, with the key supplied by the
  environment rather than the database.
- Interactive OAuth: a real redirect-URI round trip in the app, replacing the
  OAuth Playground procedure used to bootstrap Phase 1.
- Connect / disconnect routes, and a visible "which Google account is this
  operator connected to?" surface.
- Token lifecycle: refresh, revocation, and the Google **Testing**-mode
  7-day refresh-token expiry (see picker spec §4, constraint C4) — which
  becomes an operator-visible failure mode rather than a Chris-only annoyance.
- A permission model saying which narrators a given operator may file into.
  This does not exist and is a much larger question than authorization.

---

## 5. Explicitly out of scope for Phase 1

None of the following may be built as part of
`WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01`:

- token tables or any persistent token storage
- encryption-at-rest machinery for credentials
- connect / disconnect routes
- multi-user authentication or session management
- per-narrator Google credentials — **these are forbidden permanently, not
  merely deferred**

Phase 1 keeps its one global `.env` refresh token, its process-local access
token cache, and its boolean-only health reporting.

---

## 6. Acceptance for this document

1. The Google Cloud project, the authorized Google account, the operator, the
   narrator/person, and the trip are described as five separate things.
2. The existing Phase 1 local `.env` model remains valid and is not deprecated
   by anything written here.
3. The future multi-operator model is documented and **not** implemented.
4. Nothing in this document implies that Google account identity determines a
   Hornelore narrator, person, or trip.
