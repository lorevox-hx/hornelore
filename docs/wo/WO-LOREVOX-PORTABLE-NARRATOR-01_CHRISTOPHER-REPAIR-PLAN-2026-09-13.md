# Christopher source-data repair — SUPERSEDED as a portability plan; retained as Phase 7 input

> **STATUS 2026-09-14: THIS PLAN IS NOT A PORTABILITY PREREQUISITE, and never should
> have read as one.** The portability fault was **nine stale
> `turn_extraction_ledger` rows** and nothing else. They were removed (ids
> 7,8,9,10,11,17,18,19,28; 533 → 524 records; files unchanged at 214), Christopher
> was re-exported as `24560db21dd6`, and the clean-root round trip compared
> **`EQUIVALENT tables=60 rows=524 files=214`** with zero unresolved references.
> **Laptop Christopher Phase 6 is RE-CLOSED** — see WO §36.5a.
>
> **None of §1–§3 below was executed and none of it was needed.** No ownership was
> materialised, no `trip_turn_link` was touched, no session was curated, no fact was
> salvaged. This document drifted from portability into curation: it asked which of
> Christopher's conversations deserve to be permanent family history, which is a
> **Phase 7 clean-data question** that portability does not ask.
>
> **§6's arithmetic is withdrawn.** It rested on the claim that "a session left NULL
> stays out of the package by construction", which is **false** under the shipped
> declaration — `DirectOrExclusiveInbound` admits a NULL-owner session that a
> Christopher-owned `trip_turn_link` reaches exclusively, and the 533 baseline
> already contained 9 such sessions and 100 turns. The 578 / 597 / 654 figures are
> wrong; the measured result was 524. §4's option C is also already implemented via
> `ENCODED_REFERENCES` (corrected in place below).
>
> **What remains useful:** §1's session inventory, §3's salvage destinations, and the
> distinction between preserving a *session* and preserving the *information* in it.
> Read it as Phase 7 input when deciding what enters the clean Lorevox world.

---

## Original document follows (as written 2026-09-13)

# Christopher source-data repair — DRY RUN, nothing executed

**`WO-LOREVOX-PORTABLE-NARRATOR-01`, 2026-09-13.** Derived entirely from the
read-only evidence in `..._SESSION-OWNERSHIP-FINDINGS-2026-09-13.md`.

**NO DATABASE WRITE IS PROPOSED FOR TONIGHT.** This is the plan to execute
tomorrow, written so that tomorrow's execution is auditable against a
before-state recorded now.

**Not repairing all 81 ownerless sessions.** That finding has served its purpose:
36 belong to synthetic personas, and most of Christopher's 42 are the archaeology
of building the travel-document, photo, guard and safety systems. Repairing them
would migrate the history of Hornelore's development into the product.

---

## 1. Sessions to keep as Christopher's canonical record

**Ownership repair and preservation are the same list.** A session left NULL stays
out of the package by construction; a session whose ownership is repaired enters
it. So the repair scope IS the preservation decision, and nothing else needs a
deletion to keep the package clean.

### 1a. Canonical, no reservations (3)

| conv_id | date | turns | unique narrator chars | anchors |
|---|---|---|---|---|
| `switch_mrb7cut9_04pi` | 2026-07-07 | 10 | 158 | 2 story candidates |
| `switch_ms8z59ie_xakt` | 2026-07-31 | 18 | 493 | 3 trip links, 8 ledger |
| `switch_msaiqgs2_a1mu` | 2026-08-01 | 14 | 263 | 3 trip links, 3 ledger |

### 1b. Real content, Chris decides (candidates, not decisions)

| conv_id | why it is a candidate | why it is not automatic |
|---|---|---|
| `switch_mseorb11_acy7` | 505 unique chars; the Bismarck cemetery material; 4 trip links, 5 ledger, 2 results | two of its unique turns are operator debugging ("Nobody talked about suicide…") |
| `tdlab_9538cd88…` | 534 unique chars; holds turn 1482, the strongest salvage fact; 1 trip link | structurally a lab session |
| `switch_mre0txvh_tb7w` | 168 unique chars; the lederhosen photo correction | photo correction belongs in photo context, not necessarily this session |
| `switch_mrkpipjr_twr7` | 800 unique chars | dominated by safety-path exercise and fixture replay |

**Everything else — 35 of the 42 — stays NULL and therefore stays out.**

## 2. Development/test sessions to exclude

No deletion is required for the package to be clean; leaving ownership unrepaired
is sufficient. Deletion is a separate, later, operator decision and is **not** part
of this plan. The inventory exists in `preservation_plan.py`'s report:

* 8 content-duplicated-elsewhere · 9 test-prefixed with unique content · 6
  empty/structural shells · plus the fixture-replay `switch_*` sessions
  (`switch_mrkt2k62_1h3v`, `switch_mrkrk19b_0mfq`).

## 3. The salvage set, and the clean destination for each

| item | destination | mechanism |
|---|---|---|
| [1482] "grandparents gravesite and my old schools with Melanie" | `trip_location_notes` on the Bismarck trip | operator adds a trip note through the product |
| [1182] "I was not in the outfit, it is a picture of men in lederhosen" | photo context/caption for that Munich photo | operator corrects the photo record through the product |
| [1218] "She was patient with me" | **Chris decides** — bio fact, or nothing | — |
| [1448] "light looked on the water" | **Chris decides** — likely fixture, likely nothing | — |
| [1532] Bismarck gravesite | **none needed** — already in `trip_location_notes` | — |

**Salvage happens through the product, not by SQL.** Writing a trip note or photo
caption by hand would create exactly the unprovenanced data this investigation
exists to clean up.

## 4. The three dangling-reference sessions

Their content is discardable; their **references are not yet resolved**. Three
options, with the trade-off stated rather than a choice made:

> **CORRECTED 2026-09-14, and the correction removes an option.** This section
> originally offered a third choice — "declare `turn_extraction_ledger → turns` in
> `COLUMN_ONLY_REFERENCES`" — and recommended it alongside B. **That work is already
> done, by a better mechanism, and implementing it again would add a duplicate
> declaration.** `narrator_data_inventory.ENCODED_REFERENCES` (line 475) declares
> `turn_extraction_ledger.turn_key` → `turns` as `FORM_TEXT_PREFIXED` with prefix
> `turnrow:`, cited to `0038:62-65`, alongside `turn_extraction_results.turn_key` and
> the `bio_facts.source` JSON field; the exporter consumes it, and a malformed
> encoding refuses rather than being skipped. `COLUMN_ONLY_REFERENCES` compares
> **column values** and structurally cannot reach a reference embedded *inside a
> string* — which is precisely why `ENCODED_REFERENCES` exists.
>
> **The plan was written without knowledge of that landed repair.** The guard gap is
> closed; only the data question remains.

| option | effect | cost |
|---|---|---|
| **A. Repair ownership on all three** | 28 turns enter the package; the 9 ledger rows resolve | migrates 28 turns of capability-probing into the canonical record — the opposite of this plan's intent |
| **B. Remove the 9 stale ledger rows** | references disappear; the sessions stay out | a write to a derived audit ledger on real data; needs its own authorization and a truthful record |

**Recommendation: B.** The rows are derived extraction bookkeeping pointing at
conversations nobody is keeping, and the semantic guard already in production will
stop an incomplete package shipping again. A is the option to avoid: it would
preserve "can you read my travel docs or trips" as family history.

**`switch_msaedccx_fkm1` is the clearest case**: the narrator typed **"hi"**, and
one ledger row names a turn in it.

## 5. The ownership repair itself

* **Scope:** only the sessions chosen in §1. Not all 81. Not all 42.
* **Mechanism:** a deliberate, recorded backfill of `sessions.person_id` for exactly
  those `conv_id`s, stamping `person_id_source` so the provenance is captured at
  the moment it is known — the rule `0045` states and follows.
* **Evidence required at execution:** each target must satisfy 0044's literal pass-1
  predicate at the moment of the write, re-checked, not trusted from tonight.
* **Not a re-run of 0044.** Its mechanism of failure is unrecovered; re-running it
  blind through the same runner could fail the same silent way.
* **Erasure parity:** repaired sessions become erasable with Christopher, as they
  should be. Unrepaired residue remains unerasable — pre-existing, unchanged by
  this plan, and true of 902 other sessions.

## 6. Pre/post expectations, for tomorrow's audit

**Before-state, measured 2026-09-13 (read-only):**

| measure | value |
|---|---|
| sessions total | 1016 |
| sessions with owner | 104 (95 `explicit`, 8 `legacy_payload_json`, 1 NULL source) |
| sessions NULL-owner | 912 |
| NULL-owner with a unique accepted owner | 81 |
| Christopher preflight | **533 records · 214 files · 129,508,043 bytes** |
| Christopher `sessions` in closure | 9 (via `DirectOrExclusiveInbound`) |
| Christopher `turns` in closure | 100 |

**Expected after, per scenario** — each repaired session adds itself plus its turns:

| scenario | sessions repaired | +sessions | +turns | expected records |
|---|---|---|---|---|
| §1a only | 3 | +3 | +42 | **578** |
| §1a + `switch_mseorb11_acy7` | 4 | +4 | +60 | **597** |
| §1a + all four §1b | 7 | +7 | +114 | **654** |
| option A additionally | 10 | +10 | +142 | **685** |

Files should not change in any scenario — this moves database rows only, as the
§36.5 closure did (533 = 424 + 9 + 100, files unchanged at 214).

**Acceptance for tomorrow:** the measured post-repair preflight equals the scenario
figure exactly. A different number is a finding, not a rounding error.

## 7. Order of execution tomorrow

1. Bank the desktop's semantic-reference repair (20/20 focused, 133/133 bank).
2. Chris chooses the §1b set and decides items [1218] and [1448].
3. Decide §4 — **A or B only; the guard half is already in production** (recommended: B).
4. Salvage [1482] and [1182] **through the product**.
5. Execute the narrow ownership repair; verify against §6.
6. New authoritative Christopher package; clean-root restore; no interaction;
   immediate re-export; semantic compare; full reference audit.
7. Christopher two-origin comparison only.
8. Only then Merge/Remap.

**Janice and Kent are not rebuilt on account of this investigation.**
