# API-down crank — 2026-04-22

**Context:** Chris's API is down. Agent executed the 10-item API-down task list during the window; this doc captures items not already landing as dedicated artifacts (CLAUDE.md changelog, WO specs, failure rundown), plus the holds-status snapshot and #111 scope note.

---

## What landed today (full list)

1. Standard post-eval audit block for r5h (delivered inline to Chris earlier in session).
2. CLAUDE.md changelog entries for r5g (null result, #119 complete-with-caveat) and r5h (adopt, 70/104); active-sequence reordered; #119 moved to Closed; #144, #141, #142, #97 task statuses updated.
3. `WO-EX-SCHEMA-ANCESTOR-EXPAND-01_Spec.md` — two-lane spec (scorer-only Lane 1 + schema-expansion Lane 2). Task #144.
4. `WO-EX-VALUE-ALT-CREDIT-01_Spec.md` — #97 value-axis alt-credit (case_087 fresh evidence).
5. `docs/reports/FAILING_CASES_r5h_RUNDOWN.md` — 34-case rundown, successor to r5e1 rundown.
6. `WO-EX-FAILURE-PACK-01_Spec.md` — cluster-JSON sidecar for every master eval. Task #141.
7. `WO-EX-DISCIPLINE-01_Spec.md` — run-report discipline header. Task #142.
8. case_028 / case_033 / case_039 answers + raw_items cross-referenced during spec authoring (see WO-EX-SCHEMA-ANCESTOR-EXPAND-01 §1 problem statement).
9. This file — #111 scope note and holds status.
10. (Post-artifacts) git commit block for Chris to paste — delivered in chat, not in-tree.

---

## #111 canon-grounding corpus expansion — scope note

**Status:** in_progress (task #111). Current canon-grounded corpus has 14 cases (pre-today). Target: ~24 cases.

**Expansion priorities (ordered):**

1. **≥2 stubborn date-range cases** — required to reactivate LORI v1.1 dateRange confirm bank (explicitly descoped from LORI v1 on 2026-04-22 morning). Without these, the bank stays parked; with them, a decision can be made about flipping it back on.
2. **≥3 family_rituals_and_holidays cases for janice-josephine-horne** — her weakest phase-family on r5h (case_028, 035, 039 all failing there). Need coverage beyond the current 3 failing cases so we can distinguish "systematic failure on this subTopic" from "bad luck on 3 unrepresentative cases."
3. **≥2 shong_family / ancestor-branch cases** — to sanity-check WO-SCHEMA-ANCESTOR-EXPAND-01 Lane 2 once schema expansion lands. case_087, case_081 alone are insufficient test surface for "does the expanded schema hallucinate NEW paths that weren't there before?"
4. **≥2 childhood_pets cases for Christopher or Kent** — janice has case_046/066 (pets sink), Christopher has 042/045 (LLM hallucination on pet content). The pattern is cross-narrator but under-represented; 2 more cases confirm or refute a systemic pet-routing issue.
5. **Legacy_reflection / life_lessons** — currently only 1 failing case (case_104) and its score is 0.00; one more case there would tell us if this is a phase-wide problem or a case-specific collapse.

**Scope-out for this expansion pass:**

- Do NOT expand sibling_dynamics (case_047, 014 are already covered; schema_gap there is path-specific, not corpus-width).
- Do NOT add more higher_education cases beyond case_078 (LORI-target; over-representing confuses LORI pilot acceptance math).
- Do NOT expand at the expense of the 14 existing canon-grounded cases — this is addition, not substitution.

**Next action:** hold until r5h-based WO lands (#144 Lane 1 r5i), then expand so r5j/r5k have a wider statistical surface.

---

## Holds status snapshot

| item | status | blocker / hold reason |
|---|---|---|
| WO-UI-CANON-SURFACE-01 | ON HOLD | no recent work surface; parked pending product-lane decision on canon-facing UI |
| WO-INTAKE-IDENTITY-01 (FINAL) | ON HOLD pending Chris's HIGH-severity decisions | rollback-flag data path (does disabling flag restore data access to gated schemas?); idempotency-guard legacy-key scan (does the guard bypass data stored under pre-migration keys?); see chat review earlier today |
| WO-LORI-CONFIRM-01 | PARKED | v1 scope locked (3-field pilot); implementation opens after SPANTAG (#90) default-on/off decision |
| WO-EVAL-MULTITURN-01 | PARKED | companion to LORI; canned-narrator harness; opens when LORI v1 opens |
| SPANTAG (#90) | IMPLEMENTATION PAUSED | SECTION-EFFECT Phase 3 (#95) must land first |
| SECTION-EFFECT Phase 3 (#95) | PENDING | Phase 1 + Phase 2 done; Phase 3 = 2-3-case causal matrix, scoped in `WO-EX-SECTION-EFFECT-01_PHASE3_WO.md` |
| #96 Truncation lane (WO-EX-TRUNCATION-LANE-01) | PENDING | 15/15 stubborn-pack truncation evidence exists; implementation untouched |
| #35 V4 scope axes | DEFERRED (R6) | |
| R6 Pillars 2 & 3 | DEFERRED | |
| Hermes 3 / Qwen A/B | DEFERRED (post-SPANTAG) | attribution clean-up before model swap |
| KORIE staged-pipeline | DEFERRED (conditional on SPANTAG lift) | |

No stale holds need recategorization today. Every hold has a stated unblock condition.
