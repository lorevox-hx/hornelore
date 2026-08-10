# Phase 1c — consent trace (Unit 3)

**2026-08-09 · READ-ONLY.** No code changed, no table created or altered, no schema chosen,
no browser key inspected or deleted. Profile Seed, progression behaviour and
`LORI_INTERVIEW_DISCIPLINE` untouched.

Pinned separately from the remaining Phase 1 units so the correction below is not lost among
later findings.

---

## 1. The "always-false gate" hypothesis is RETIRED

Phase 1b proposed that `consent_attestation_has_complete_set()` had *"been getting `false`
for the life of the feature"* and that its consumer was untraced. The supervisor held it as
hypothesis pending that trace. **The trace retires it — and not in favour of either option I
offered.**

```text
grep consent_attestation_has_complete_set  →  server/  ui/js/   (definition excluded)
RESULT: ZERO callers.
```

It is **not** a silently-failing gate. It is **dead code** — defined at `db.py:7111` and
called by nothing. Nothing has been getting `false`, because nothing has been asking.

**Method note worth keeping.** I offered two possibilities — inert, or a gate that never
opened — and the answer was neither in the sense I meant: there is no consumer at all, so the
question of what it returned never arose. Holding it as hypothesis rather than reporting it
as a finding was correct, and the cost of doing otherwise would have been a plausible,
memorable, wrong claim in the record.

## 2. Live server writers exist, and they are the intake path

```text
server/code/api/routers/people.py:189   consent_attestation_create(...)
server/code/api/routers/people.py:576   consent_attestation_create(...)
attestation_type values written:  "recording_agreement", "disclosure_reviewed"
```

So the server attestation path is **wired and reachable** through the narrator-intake
orchestrator. Phase 1b's phrasing — *"built and never called"* — was too strong and is
**withdrawn**. The accurate statement, adopted from the supervisor:

> **The live facial-consent runtime does not use the server attestation path, and the current
> live database has zero attestation rows.**

## 3. 🔴 These are two different consent purposes, not one system with two stores

This is the finding that matters more than the wording, and it was not visible until the
attestation types were read.

| | consent purpose | where it lives today | evidence |
|---|---|---|---|
| **Server path** | **`recording_agreement`** — agreement to be recorded · **`disclosure_reviewed`** — disclosure was reviewed | `consent_attestations` (0 rows), written by narrator intake | `people.py:185`, `:574` |
| **Browser path** | **facial / affect analysis** | `localStorage` `lorevox_facial_consent:<pid>` only | `facial-consent.js` reads, writes, auto-restores, migrates a legacy global key, and revokes by deleting browser keys |

**So this is not "one consent system with a browser cache."** It is **two different
permissions**, one of which has a server home and an intake writer, and one of which has only
browser storage.

That changes the shape of the eventual Phase 2 work: facial-consent is not a matter of
pointing an existing writer at an existing row. It is a purpose that currently has **no
server representation at all**.

## 4. ⚖️ Architectural decision recorded: the two consents do not imply one another

**Recording/disclosure consent must not be treated as implying facial or affect-analysis
consent.** They remain separate consent purposes.

The reasoning, stated so it survives: agreeing that *your voice may be recorded* is not
agreeing that *a camera may analyse your face*. They differ in sensor, in what is inferred,
and in what a person is likely to have understood themselves to be agreeing to. A system
whose stated north star is narrator dignity should not widen a permission by inference —
particularly not for a capability the narrator may not know exists.

**This is a decision about meaning, not about storage**, and it holds regardless of where
either record eventually lives.

## 5. What is explicitly NOT decided here

- **No schema change is chosen.** Whether `consent_attestations` can carry facial-analysis
  consent as an additional `attestation_type`, or needs a small extension (consent text /
  version, `revoked_at`), remains **Phase 1 investigation**. The table has zero rows; the
  first question is still why the live runtime does not use it, not what to add to it.
- **No consent writer is proposed.**
- **The `lv_segs_` per-session vs per-person grain stays undecided**, per the standing guard,
  until the actual browser blob is compared with the 9 `segment_flags` rows.

---

## Remaining Phase 1 units

| unit | status |
|---|---|
| 1 — live Category-A browser values, **Quick Capture first** | **NOT STARTED** — browser connection lost mid-call. Highest priority; the only category-A family with no server owner, and it may hold narrator-authored words. |
| 2 — `lv_segs_` browser vs the 9 `segment_flags` rows | not started (depends on Unit 1's data) |
| **3 — consent callers / writers** | ✅ **this report** |
| 4 — voice capture / persistence truth chain | not started |
| 5 — writer + reader + shape for each HYPOTHESIS mapping | not started |
| 6 — deterministic server progression condition | not started |
| 7 — final owner/migration map and minimal deltas | not started |

**Unit 1 is not skipped.** It resumes on restored browser access: read-only enumeration of
`localStorage` filtered to the category-A prefixes, **Quick Capture first**. No writes, no
clearing, no narrator turns.

---

## Corrections to earlier reports in this series

| claim | status |
|---|---|
| `consent_attestation_has_complete_set()` "has been getting false for the life of the feature" (Phase 1b §2) | **withdrawn** — zero callers; dead code, not a failing gate. |
| consent API "built and never called" (Phase 1b §2) | **withdrawn** — live intake writers exist at `people.py:189`/`:576`. Replaced by the precise statement in §2. |
| implicit assumption that server and browser consent were the same permission in two stores | **withdrawn** — §3: they are different purposes. |
