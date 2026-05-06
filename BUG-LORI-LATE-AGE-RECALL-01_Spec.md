# BUG-LORI-LATE-AGE-RECALL-01 — Lori loses age recall after lifemap walk

**Status:** OPEN — pre-parent-session blocker
**Severity:** RED Mary / AMBER Marvin (real degradation; one of the things narrators most directly notice when Lori "forgets" something they just told her)
**Surfaced by:** TEST-23 v6 (2026-05-05)
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers

---

## Problem

Lori passes the early_inference age probe (right after onboarding) but fails the late_age probe (after the lifemap walk + Today cycles). Conversation depth erodes age recall — by the time Lori has been talking for ~15-20 turns, the narrator's age value has rotated out of whatever surface Lori reads age from.

This is one of the most directly noticeable failures from the narrator's perspective. The narrator told Lori their age (or DOB, from which age derives) early in the session. Twenty turns later, when asked, Lori either guesses wrong or refuses to commit. For older narrators with cognitive load this reads as Lori "forgetting" them — load-bearing on trust.

## Evidence

v6 run:

```
[mary/early_inference/age] expected=86 hit=True severity=PASS
...
[mary/late_age] expected=86 hit=False severity=RED

[marvin/early_inference/age] expected=76 hit=False severity=AMBER
...
[marvin/late_age] expected=76 hit=False severity=AMBER
```

Mary's age recall goes PASS → RED. Marvin's was AMBER throughout (his early_inference miss is its own data point; the late_age miss confirms the degradation pattern even when Lori didn't have a clean read at the start).

## Diagnosis hypothesis

Three candidates, ranked by confidence:

**A. profile_seed identity anchor rotation.** Lori's system prompt is built per-turn by `prompt_composer.py` from the `profile_seed` returned by `chat_ws._build_profile_seed()`. After Phase A landed (2026-05-04), the seed reads from BOTH `profiles.profile_json` (canonical) AND `interview_projections.projection_json` (provisional). But the seed is built fresh each turn — and the prompt's identity-anchor block (which carries DOB / age / current_year) may either: (a) not be consistently included in every turn's prompt, OR (b) be truncated/dropped when the prompt approaches its size budget after recent_user_turns + Lori's last few responses fill the window.

**B. Age computation site-of-truth drift.** `dateOfBirth` is stored in `profile_json`, but `age` itself isn't a stored field — it's computed as `current_year - birth_year` somewhere. If the computation happens at a single site (e.g., in `prompt_composer.py` when assembling identity context) but a different site reads it for late_age responses, the two sites can desync if one path is taken and the other is skipped.

**C. LLM confabulation under context pressure.** The DOB IS in the prompt at every turn, but as the conversation grows the LLM's "what year is it" or "how old is this narrator" computation becomes stochastic — it may state an age that doesn't match the math. This is an LLM-behavior issue, not a prompt-build issue.

## Reproduction

```bash
cd /mnt/c/Users/chris/hornelore
python -m scripts.ui.run_test23_two_person_resume --tag debug_lateage --only mary
```

Watch the `[mary/early_inference/age]` and `[mary/late_age]` lines. Compare expected vs hit for both. The full lifemap walk between them is what triggers the degradation.

Lighter manual reproduction:
1. Onboard a test narrator with DOB in the past (e.g., 1940-02-29 → expected age 86)
2. Ask Lori: "How old am I?" — note the answer
3. Walk through 5-7 lifemap eras with one or two beats per era
4. Ask Lori again: "How old am I?" — compare to the first answer

## Diagnostic plan (read-only first)

1. **Capture the system prompt at early_inference vs late_age.** With `LV_DEV_MODE=1` (existing dev-log flag), dump the system prompt at both probe moments. Diff them. Look for: (a) is the DOB present in both? (b) is the age explicitly computed and stated, or just the DOB? (c) what's the prompt token count at each — is the late prompt approaching truncation?
2. **Add a deterministic age block to the prompt.** As a probe: temporarily inject a hard-coded `"YOUR AGE IS {age}"` block at the top of every system prompt. Re-run TEST-23. If Mary's late_age PASSes with the hard-coded block, hypothesis A is confirmed (the seed-side gap is the cause). If she STILL misses, hypothesis B or C is in play.
3. **Capture Lori's actual reply text on the late_age probe.** What does she SAY? Wrong number, refusal to commit, "I don't have that information," generic deflection? The reply shape narrows the diagnosis.

## Acceptance gate

TEST-23 v7+ shows BOTH narrators PASSing the late_age probe. Specifically:
- `[mary/late_age] expected=86 hit=True severity=PASS`
- `[marvin/late_age] expected=76 hit=True severity=PASS`

Concrete behavioral acceptance:
- After 15+ conversation turns, Lori still answers "How old am I?" with the correct numerical age
- The answer shape is direct ("You are 86" / "You're 86 years old"), not deflective ("I'm not sure what your current age is")
- No regression on early_inference age probe

## Files (planned, after diagnostic)

**Likely modified:**
- `server/code/api/prompt_composer.py` — identity anchor block (DOB + computed age + current_year) included in EVERY turn's system prompt, not just memory_echo or identity-mode turns
- `server/code/api/routers/chat_ws.py` — `_build_profile_seed()` may need an explicit `age` field computed from DOB so the prompt-composer doesn't have to do the math itself

**Possibly modified:**
- `server/code/api/services/lori_communication_control.py` — runtime guard catching "age question + missing or wrong number in reply" and reshaping (similar pattern to BUG-LORI-REFLECTION-02 Patch C)

**Zero touch:**
- Extract router (DOB extraction is upstream and not the gap here)
- Lori behavior services beyond the comm-control wrapper

## Risks & rollback

**Risk 1: token budget pressure.** Adding a guaranteed identity anchor to every turn's prompt costs ~30-50 tokens per turn. On long sessions, this competes with `recent_user_turns` for context space. Mitigation: identity anchor is highest-priority and never trimmed; recent_user_turns trims first under pressure. Alternative: identity anchor goes into the system message (always-included by API contract), not the user/assistant turn history.

**Risk 2: stochastic LLM behavior under hypothesis C.** If the diagnosis lands on "LLM just gets it wrong sometimes," prompt fixes alone won't close the gap to 100%. Mitigation: comm-control runtime guard catches age-question + wrong-number-shape responses and reshapes via deterministic substitution.

**Risk 3: false-positive harness scoring.** The harness's age-hit detection may have its own bugs (regex matching, expected value computation). Mitigation: when investigating, also inspect what the harness compared against — is `expected=86` correct given Mary's DOB and the current_year used in computation?

**Rollback:** revert the patch. Late_age recall goes back to the v6 baseline. No regression on other recall surfaces.

## Sequencing

Compose with BUG-LORI-MIDSTREAM-CORRECTION-01 (both target the identity-anchor surface in different ways). Land after BUG-UI-POSTRESTART-SESSION-START-01 so the harness can verify across both pre-restart and post-restart late_age behavior.

## Open questions

- **Marvin's AMBER on early_inference age** is its own data point — Lori didn't have a clean read at the START. That suggests the gap isn't only "late conversation depth" but also "even early-on the recall is fragile." Worth checking whether Marvin's onboarding flow gives Lori his DOB cleanly before the early_inference probe runs. If not, that's a separate sub-bug — probably an extraction-routing issue where Marvin's DOB ("December 6, 1949") doesn't normalize cleanly enough to land in projection_json by the time the age probe fires.
- Is `current_year` computed dynamically (`datetime.now().year`) or stored on the profile? If dynamic, what timezone? If the server is in a different timezone than the narrator's expected timezone, year boundaries (December 31 → January 1) could produce off-by-one age errors. Probably not the cause of the v6 misses (we're in May), but worth confirming.

## Changelog

- 2026-05-05: Spec authored after v6 evidence. Three diagnostic hypotheses ranked. Acceptance ties to TEST-23 v7+ harness scoring.
