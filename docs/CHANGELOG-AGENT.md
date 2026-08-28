# Agent decision index

**This is an INDEX. It is not current status, not a work queue, and not a changelog.**

For what is happening now, read [`../HANDOFF.md`](../HANDOFF.md). For the ordered queue,
[`../MASTER_WORK_ORDER_CHECKLIST.md`](../MASTER_WORK_ORDER_CHECKLIST.md). For standing
doctrine, [`../CLAUDE.md`](../CLAUDE.md). For what is still owed,
[`BACKLOG.md`](BACKLOG.md).

**The governing order:**

```text
current code
> current tests and live evidence
> accepted reports / ADRs / closeout records
> HANDOFF.md
> MASTER_WORK_ORDER_CHECKLIST.md
> old WO status lines
> archived design history
> this index and the archived snapshot below
```

This file is the **lowest** rung. Nothing here outranks the code, the tests, or a work
order. Use it to find *why* a subsystem behaves as it does — then verify against the
implementation.

---

## The archived snapshot

Everything this file used to contain is preserved **byte-for-byte**:

**[`archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md)**

| | |
|---|---|
| Date range | **2026-04-11 → 2026-08-20** |
| Bytes | **614,130** |
| Lines | **1,407** |
| SHA-256 | `2e91723267d85bf2ee262645d605546f7e5025193022089c3ebdf22f7facd4c3` |
| Git blob | `4edbdc80bd2917299d2c835494b705b3043e8cfe` |
| Original path | `docs/CHANGELOG-AGENT.md` |
| Moved | 2026-08-28, `WO-REPOSITORY-HYGIENE-01` Step 2b |

**Why it moved.** At 614 KB it was roughly 85% of a context window, and `CLAUDE.md`
instructed every session to consult it. A history nobody can afford to load is a history
nobody reads. The bytes are unchanged; only the entry point is new.

---

## Subsystem decision index

Current authority first. The archived snapshot is where the *reasoning* was recorded, not
where a decision is ratified.

| Subsystem | Current authority | Archived history |
|---|---|---|
| Lori runtime and prompt composition | [`architecture/LORI-RUNTIME-ARCHITECTURE.md`](architecture/LORI-RUNTIME-ARCHITECTURE.md) | Lean Lori sections of the snapshot |
| Who Lori is for | [`architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`](architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md) | pivot sections, 2026-06-14 |
| Runtime safety — **PARKED** | [`decisions/2026-08-04-park-safety-feature.md`](decisions/2026-08-04-park-safety-feature.md) | safety sections |
| Extractor | [`specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`](specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md) | extractor-lane eval ladder, r4–r5 |
| Travel Doc, evidence and web context | [`architecture/TRAVEL_DOCUMENT_DOCTRINE.md`](architecture/TRAVEL_DOCUMENT_DOCTRINE.md) | Travel Doc sections |
| Trip photos and placement | [`wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md`](wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md) · [`wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md`](wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md) | placement and Palette sections |
| Narrator and story authority | [`wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md`](wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md) | Phases 1–4 |
| Memoir and erasure integrity | [`wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md`](wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md) | deletion-integrity sections |
| Profile Seed onboarding | [`wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md`](wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md) · [transport map](wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md) | — lane opened after the snapshot |
| Kawa / Memory River — **frozen** | [`CLAUDE.md`](../CLAUDE.md) standing prohibitions | Kawa retirement, 2026-05-01 |
| Repository hygiene | [`wo/WO-REPOSITORY-HYGIENE-01_Spec.md`](wo/WO-REPOSITORY-HYGIENE-01_Spec.md) | — lane opened after the snapshot |

---

## The rule for new decisions

**A durable decision belongs in an ADR under `decisions/`, or in the work order that owns
it. Only a LINK is added here.**

Do not append narrative to this file. Do not add acceptance hashes, current lane status, or
a running chronological log. This index exists because the last one became all four of
those, and a control document that carries current state in a second place is how two
copies come to disagree.
