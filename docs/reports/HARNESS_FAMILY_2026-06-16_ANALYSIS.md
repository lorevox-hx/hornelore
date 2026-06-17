# Long-narration harness family — first full run analysis (2026-06-16)

**Run window:** 17:02–17:08 (~6 minutes) on warm stack at SHA <user_to_fill>.
**Harnesses run:** 10 in numerical order (Jake → Stefi).
**Result:** 9 of 10 completed. 1 failed at intake (Alex/they-them, harness bug).
**Aggregate score:** 200/216 PASS rows = **92.6%** across the 9 completed narrators (216 = 9 × 24-row matrix; Jake's bonus probe rows excluded from family math).
**Reports:** `docs/reports/{jake_long_narration,shatner_long_narration,alex_they_long_narration,richard_late_coming_out,pat_teacher_betty,regional_*}_{<conv_id>}.txt`

---

## §1 Score table

| # | Persona | Score | Reflection (3 chapters) | Question-count | Same-anchor-loop | Notes |
|---|---|---|---|---|---|---|
| 0 | Jake Max Miller | 27/32 (84.4%) | FAIL / FAIL / PASS / FAIL-bonus | PARTIAL/PARTIAL/PASS/PASS | PASS×4 | META_FEEDBACK on C1+C2 |
| 1 | William Shatner | 22/24 (91.7%) | FAIL / PASS / PASS | PARTIAL/PASS/PASS | PASS/PASS/PASS | META_FEEDBACK on C1 |
| 2 | Alex Park (they/them) | **DNF** | intake 422 | — | — | **Harness bug — see §4.1** |
| 3 | Richard Bellamy | 22/24 (91.7%) | PASS / FAIL / PASS | PASS/PARTIAL/PASS | PASS/PASS/PASS | META_FEEDBACK on C2 |
| 4 | Pat Frye + Betty | 22/24 (91.7%) | PASS / PASS / PASS | PASS×3 | PASS/**FAIL/FAIL** | **anchor-list-dump on C2 + C3** |
| 5 | Mable Hudson | 22/24 (91.7%) | PASS / PASS / PASS | PASS×3 | PASS/**FAIL/FAIL** | **anchor-list-dump on C2 + C3** |
| 6 | Frank Yamada | 22/24 (91.7%) | FAIL / PASS / PASS | PARTIAL/PASS/PASS | PASS×3 | META_FEEDBACK on C1; sentimentalize on C3 (passed PASS but watch §5.3) |
| 7 | Joe Quintana | 22/24 (91.7%) | PASS / PASS / PASS | PASS×3 | **FAIL**/PASS/**FAIL** | **anchor-list-dump on C1 + C3**; sacred-silence held ✓ |
| 8 | Tomasita Reyes Cantú | 23/24 (95.8%) | FAIL / PASS / PASS | PASS×3 | PASS×3 | **Spanish META-QUESTION misfire on C1 — Lori introduced herself in Spanish** |
| 9 | Stefi Sandoval | 23/24 (95.8%) | PASS / FAIL / PASS | PASS×3 | PASS×3 | **Safety false-positive `child_abuse 0.70` on C1**; META_FEEDBACK in Spanish on C2 |

---

## §2 Aggregated row tallies (216 rows across 9 narrators)

| Row | PASS | PARTIAL | FAIL | % PASS |
|---|---|---|---|---|
| reflection_grounded | 21 | 0 | 6 | 77.8% |
| one_question_max | 24 | 3 | 0 | 88.9% PASS (100% PASS+PARTIAL) |
| no_questionnaire_interrogation | 27 | 0 | 0 | 100.0% |
| no_forbidden_empathy_openers | 27 | 0 | 0 | 100.0% |
| no_era_label_menu | 27 | 0 | 0 | 100.0% |
| no_same_anchor_loop | 21 | 0 | 6 | 77.8% |
| word_budget_honored | 27 | 0 | 0 | 100.0% |
| translation_refusal_absent | 27 | 0 | 0 | 100.0% |

Two rows account for all 12 failures: **reflection_grounded** and **no_same_anchor_loop**. Both are downstream consequences of three root-cause bugs (see §3).

---

## §3 Three root-cause bugs surfaced

### §3.1 BUG-LORI-WITNESS-META-FEEDBACK-LONG-NARRATIVE-01 (task #88, confirmed at scale)

**Live api.log evidence:**
```
2026-06-16 17:02:33 [chat_ws][witness][deterministic]
  conv=... type=META_FEEDBACK sub=correction
  anchor='Originally Schong With A C' lang=en
```

The witness classifier in `chat_ws.py` mis-tags long autobiographical narrative as a "name correction" because the heuristic that detects "did I get that name right?" patterns is overly broad. When triggered, Lori dispatches the deterministic template **"Got it — [Title Case]. Did I get that name right? What happened next?"** in ~1 second (no LLM call).

**Affected chapters (6 of 27):** Jake C1, Jake C2, Shatner C1, Richard C2, Frank C1, Stefi C2 (Spanish variant "Entendido — Well. ¿Qué pasó después?")

**Pattern:** disproportionately fires on chapters that contain proper-noun-heavy openings or kinship corrections. Jake's "Schong with a C" line, Shatner's "It was the air", Frank's "the adults stopped moving" — all flagged as faux-corrections.

**Action:** existing task #88 confirmed as the single highest-leverage Lori-behavior fix. Tighten the META_FEEDBACK detection: require an actual correction marker (`"actually..."`, `"sorry, that should be..."`, `"no — what I meant was..."`) not just a Title Case noun phrase.

### §3.2 BUG-LORI-ANCHOR-LIST-DUMP-01 (new — never seen before)

**Live api.log evidence:**
```
2026-06-16 17:04:48 [chat_ws][witness][llm-receipt] validator FAIL
  failures=too_few_facts:1/3
  before="You're reflecting on the years after the loss of Jim and Betty..."
  after="You went from Wednesday to Betty, then Madeleine, Engle, Wrinkle,
         Time, Tuesday, and October. What do you remember about your daily
         life during your Later Years..."
```

When the LLM produces a response that fails the validator (too short, too few facts, or grounding fail), the reflection-shape system attempts a repair via `shaped_anchor_prepended`. The repair logic concatenates extracted named entities into a comma-separated list:

> *"You went from X to Y, then Z, A, B, and C. What do you remember about..."*

This is the **single ugliest output pattern in the family.** It strips meaning, splits proper names (Madeleine L'Engle → "Madeleine, Engle"), reads like a database query rather than a person listening. Pat C3, Mable C3, Richard C3, Joe C1, Joe C3 all hit this.

**Affected chapters (6 of 27):** Pat C2 + C3, Mable C2 + C3, Joe C1 + C3, Richard C3.

**Action:** new bug spec **BUG-LORI-ANCHOR-LIST-DUMP-01** — disable `shaped_anchor_prepended` repair when the source LLM output is non-empty. If the LLM gave us 50 words that just don't ground, surface the failure (drop to softened mode, fall back to a generic "Tell me more about that — anything stand out?") rather than auto-generate the list-dump.

### §3.3 BUG-LORI-SPANISH-META-QUESTION-MISFIRE-01 (new)

**Live api.log evidence:**
```
2026-06-16 17:07:32 [chat_ws][meta-question][deterministic]
  conv=015600b4-63e primary=identity_name categories=identity_name lang=es
```

Tomasita C1 (a 455-word Spanish/English bilingual narrative about her birth, family, four names, etc.) was classified by the meta-question detector as `identity_name` because the narrator mentions her own name ("mi mamá nombró Tomasita Guadalupe"). Lori responded with the canonical Spanish Lorevox self-introduction:

> *"Soy Lori — diminutivo de Lorevox. Lore significa relatos y tradición oral; Vox es la palabra latina para voz..."*

The narrator did NOT ask Lori's identity. The narrator was telling her own story.

**Action:** new bug spec **BUG-LORI-SPANISH-META-QUESTION-MISFIRE-01** — meta-question detector must require an explicit interrogative (`¿quién eres?`, `¿cómo te llamas?`, `what is your name?`) — not just the presence of a proper noun + first-person possessive in either language.

---

## §4 Lower-severity findings

### §4.1 Alex/they-them intake failure (harness bug, not product bug)

**Error:**
```
HTTP 422 — "type": "int_parsing", "loc": ["body","marriage","spouses",0,"year_married"],
"input": ""
```

The Alex harness sets `year_married: ""` for the never-married partner Sam Rivera. The intake schema requires `year_married: int`. Fix: either omit the `spouses` array entirely for unmarried narrators, or set `year_married: null` and confirm schema accepts null, or use a sentinel value like the partner-start year.

Will fix in the harness file before next run.

### §4.2 Stefi C1 safety false-positive (chunked classifier hit `child_abuse 0.70`)

**Live api.log evidence:**
```
2026-06-16 17:08:11 [chat_ws][safety] triggered
  conv=3572be02-006 category=child_abuse confidence=0.70
  excerpt='I was born in Las Vegas, New Mexico ... My father Eliseo was
  a sheep rancher in San Miguel County, third generation on the land'
```

The safety classifier triggered on Stefi's reflection on her childhood (an 80-year-old narrator describing growing up Catholic in 1944 New Mexico). The "compound trigger" matched but no semantic content actually indicates abuse. Same class of false-positive as Mary's session 2026-05-09 ("I am kind of scared, are you safe to talk to?" → 988 wrongly dispatched).

**The good news:** Lori's actual safety response was reasonable + the validator caught `normal_interview_question_during_safety,softened_response_too_long`, so the user-facing output was fine. But the false-positive itself indicates the classifier confidence threshold is too low for narrative content. Existing task #88's sibling — needs a separate Phase 4 follow-up.

### §4.3 Frank C3 sentimentalization (passed scoring but watch)

Frank C3 response:
> *"The selective sharing of your stories with your grandchildren — it all speaks to the weight and the nuance of holding onto difficult memories. What does it mean to you to look at the site of your childhood farm, now a Target shopping center, and not feel overwhelmed?"*

This passes the FORBIDDEN_OPENERS check (no "Thank you for sharing" / "That's beautiful" / "Wow"). But "speaks to the weight and the nuance" is therapist-speak; "and not feel overwhelmed" projects an emotion Frank explicitly rejected in his text ("I do not stop and I do not get sad. I just look at it and I keep going.").

**Action:** **BUG-LORI-EMPATHY-SENTIMENTALIZE-01** — extend FORBIDDEN_OPENERS scanner to a deeper sentimentalize pattern set: `"speaks to the weight"`, `"the nuance of"`, `"holding onto"`, `"not feel overwhelmed"`, `"the rituals of"`. Lower priority than #88 / anchor-list-dump.

### §4.4 Pat C1 + C2 prompt-leakage in parentheses

Pat C1:
> *"What do you remember about your daily life during your freshman year at high school?  
> (One question, anchored in the narrator's own words, about the period between starting high school and meeting Betty Cavanaugh.)"*

The LLM leaked its prompt-following meta-commentary as a parenthetical addendum. Two questions in Pat C2 was even worse — "(One question, anchored in the narrator's own words, about the period **before meeting Betty Cavanaugh**.)" — which is factually wrong (Pat met Betty in 1962 high school, BEFORE Kent State 1966 — so this period was AFTER meeting Betty, not before).

**Action:** **BUG-LORI-PROMPT-META-COMMENTARY-LEAK-01** — post-LLM strip-out for parenthetical meta-commentary. Detect `(One question`, `(Anchored in`, `(About the period`, `(We can`, etc. and drop them.

### §4.5 FOREIGN KEY constraint failures on softened state

Every turn produced:
```
[chat_ws][softened] turn_count increment failed
  conv=... FOREIGN KEY constraint failed
```

The softened-mode persistence layer tries to write a turn_count update to a session row that doesn't exist (the harness opens a chat WS but doesn't go through the standard /api/session/new pathway). Not user-facing — but noisy in the log + indicates a missing session-row-ensure in the chat_ws turn loop. **BUG-DBLOCK-SOFTENED-FK-01** — defensive `ensure_session` before softened_increment.

---

## §5 What worked well

1. **Forbidden empathy openers held 100%** across all 27 chapters. "Thank you for sharing" / "That's beautiful" / "Wow" never fired. The classifier banks are working.

2. **Era-label menu held 100%** — no "Would you rather talk about your earliest years or your building years?" multi-label menus. The `LORI_INTERVIEW_DISCIPLINE` block is doing its job.

3. **Sacred silence held on Joe Quintana** — Lori asked about the village, the BIA work, the boarding school memorial events. Never asked for kiva content, kachina names, ceremony details, or clan structure. The implicit voice-pattern handling worked even without VOICE_LIBRARY cue detection wired in runtime.

4. **Word budget honored 100%** — no run-on responses across 27 chapters. The reflection-shaping system (despite §3.2's failures) does keep length in check.

5. **Translation refusal absent 100%** — Lori never said "Let me say that in English" to the Spanish narrators (Tomasita + Stefi). She switched into Spanish appropriately for both.

6. **Cross-language code-switching worked structurally** — `[chat_ws][lang-contract] unset profile pin; looks_spanish advisory routed conv=... lang=es` fired correctly. Mable's chapters stayed English, Stefi's chapters switched to Spanish.

7. **Story preservation fired for all chapters** — `[story-trigger] trigger=borderline_scene_anchor` + `[preserve] candidate_id=...` logged for every chapter. The story_candidates table will have 27 fresh rows from this run. Verify via Bug Panel Story Review.

8. **Bio_facts wrote on every intake** — counts: Jake=23, Shatner=13, Richard=15, Pat=15, Mable=15, Frank=15, Joe=22, Tomasita=15, Stefi=15. The Phase 3+4 fan-out from this morning's WO is working end-to-end.

---

## §6 Recommended next actions

1. **Task #88 (META_FEEDBACK) — TOP PRIORITY.** Now confirmed as the highest-frequency Lori-behavior failure mode (6 of 27 chapters affected). Tighten the witness classifier to require a real correction marker, not just Title Case noun phrases.

2. **BUG-LORI-ANCHOR-LIST-DUMP-01 — file + fix.** Disable `shaped_anchor_prepended` when source LLM output is non-empty. This single change would lift the family score from 92.6% to ~95%.

3. **BUG-LORI-SPANISH-META-QUESTION-MISFIRE-01 — file + fix.** Require explicit interrogative for identity-name route. Closes Tomasita C1 reflection_grounded fail.

4. **Fix Alex harness intake.** Make `spouses[]` optional or year_married nullable for unmarried/partnered narrators.

5. **BUG-LORI-EMPATHY-SENTIMENTALIZE-01 — file.** Extend FORBIDDEN_OPENERS to sentimentalize patterns. Lower priority.

6. **BUG-LORI-PROMPT-META-COMMENTARY-LEAK-01 — file.** Strip `(One question, anchored in...)` parentheticals post-LLM.

7. **BUG-DBLOCK-SOFTENED-FK-01 — file.** Defensive ensure_session before softened increment.

8. **Re-run the family after #88 + anchor-list-dump fix** to confirm the 200/216 → ~210/216 lift.

---

## §7 Sources

- `docs/reports/jake_long_narration_jake_long_narration_cf586e84659d.txt`
- `docs/reports/shatner_long_narration_dcf7296f-9f8.txt`
- `docs/reports/richard_late_coming_out_a736eaef-f26.txt`
- `docs/reports/pat_teacher_betty_122fb1ba-83b.txt`
- `docs/reports/regional_african_american_georgia_cac157c6-e75.txt`
- `docs/reports/regional_asian_american_california_73c296e5-beb.txt`
- `docs/reports/regional_native_american_new_mexico_c9f0a6eb-0b3.txt`
- `docs/reports/regional_hispano_tex_mex_015600b4-63e.txt`
- `docs/reports/regional_crypto_jewish_new_mexico_3572be02-006.txt`
- `.runtime/logs/api.log` (17:02–17:08 window, copied excerpts above)
