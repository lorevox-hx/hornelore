# BUG-STT-PHANTOM-PROPER-NOUNS-01 — STT Phantom Character Spec

**Status:** SPEC — design parked behind #50 mic modal (which mitigates upstream)
**Filed:** 2026-05-07 from Melanie Zollner ELL test
**Severity:** MEDIUM — compounds for ELL speakers and any narrator with mild dysarthria

## Problem

Web Speech API mishearings sometimes produce proper-noun-shaped tokens that Lori then weaves into the narrative as if they were real characters in the narrator's life. Two confirmed examples from Melanie Zollner's session 1:

1. **"hold my hand" → "Hannah"**
   - Narrator described a childhood earthquake: "my mom or dad was holding my brother who was newborn, and I was [hold my hand]ing someone, walking down the stairs"
   - STT emitted "Hannah" instead of "hold my hand"
   - Lori's reflection: *"There's also Hannah, who was part of that scene"* — invented a character
   - Narrator caught it: "there was no Hannah I said hold my hand"
   - Lori absorbed but didn't retract from extracted candidates — phantom Hannah persists in the data layer (#56)

2. **"pinch" → "paint"**
   - Narrator: "I would pinch the housekeeper because I didn't want her to walk me to school"
   - STT: "I would paint the housekeeper..."
   - Lori reflected: "you would paint her" — confused but absorbed
   - Narrator caught it: "I meant pinch I would pinch the housekeeper"
   - This case STT-corrected the next turn before it became canon

Compounds severely for ELL speakers (Spanish-accented English in Melanie's case) and for soft-spoken or rapid speakers.

## Root cause

Lori treats every emitted word from STT as canonical narrator content, then introduces it back into the conversation as if it were a fact. Her LLM does what an LLM does: when "Hannah" appears in the user turn, she assumes Hannah exists and reflects accordingly.

Per CLAUDE.md design principle: *"Lori reflects what is there"* — but only what the narrator actually said, not what the microphone heard. The current pipeline doesn't distinguish.

## Design — three layers of defense

### Layer 1 — narrator-visible (covered by #50 mic modal)

If narrator can SEE accumulating transcript live (#50 mic modal), they catch the mishear BEFORE Send. Most phantom proper nouns die at the source. This is the highest-leverage fix; ship #50 first.

### Layer 2 — Lori behavioral guardrail (this layer)

In `prompt_composer.compose_interview_response`, add a directive rule:

> NEVER name a character, place, or thing the narrator hasn't already mentioned by name within the last 2 narrator turns, unless that name is in profile_seed (canonical truth). If the narrator's current turn is the FIRST mention of a proper noun, reflect it back tentatively — "It sounds like you're remembering [X]?" — rather than weaving X into prose as a fixed fact.

Implementation: pass the recent narrator-turn corpus into the directive's CONSTRAINTS section. The LLM has the rule; it self-enforces. Add a runtime check post-LLM: scan Lori's reply for proper-noun candidates (capitalized non-sentence-start words ≥3 chars) and verify each appears in either:
- Last 2 narrator turns (verbatim or fuzzy substring)
- profile_seed canonical fields
- profile_seed array values (parents, children, spouse names, etc.)

If ≥1 proper noun fails the check, soft-trim Lori's reply to remove the speculative proper noun OR replace with "they" / "the person you mentioned".

### Layer 3 — extraction-side guardrail

In `extract.py`, when an extractor candidate has a `personal.firstName` / `parents.firstName` / etc field, require the value to appear verbatim in the source utterance text. Reject candidates where the extractor "inferred" a name that the narrator never said. This already exists for some patterns; extend coverage to all character-name fields.

## Acceptance gates

1. Re-run Melanie session corpus: "hold my hand" → "Hannah" mishear, Lori NEVER names "Hannah" in her reflection (Layer 2 catches)
2. "pinch" → "paint" mishear: Lori's reflection acknowledges narrator's content WITHOUT inventing a "paint" object as canonical
3. Deliberate test: narrator says clearly-pronounced proper noun ("My friend Sarah came over") — Lori references "Sarah" by name in reflection (must NOT regress on real proper nouns)
4. ELL speaker stress test: simulate 5 STT mishearings of common-phrase-as-proper-noun shapes; Lori produces zero phantom characters

## Sequencing

After #50 mic modal lands (Layer 1 absorbs most cases). Layer 2 + 3 are belt-and-suspenders for narrators who don't catch the live mishear (sight-impaired, fast talkers, etc.).

## ELL-specific consideration

Web Speech API has language-locale settings. Currently it likely defaults to `en-US`. For Spanish-accented English speakers like Melanie, switching to `en-US` with `interimResults: true` + `maxAlternatives: 3` may surface the right word among alternatives. Worth a Phase 0 audit before Layer 2 lands.

The longer-term move: when narrator's identity / volunteered story includes "I'm originally from Peru" or similar, the operator can offer to switch STT to a Spanish-accented variant. Out of scope here; file as future work.

## Estimated implementation

Layer 2 (composer directive + post-LLM check): 4-6 hours including unit tests.
Layer 3 (extractor verbatim guard): 2-3 hours, integrates cleanly with existing `_NAME_STOPWORD_BLOCKLIST` work.

Total: ~6-9 hours.
