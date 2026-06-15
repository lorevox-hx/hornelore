# WO-LORI-SESSION-AWARENESS-01 — Spec

**Status:** ACTIVE (Lori-behavior lane; parallel to extractor lane, does not displace BINDING-01)
**Type:** In-session listener behavior — memory echo + interview discipline + attention cue + adaptive silence ladder
**Date:** 2026-04-27
**Lab/gold posture:** Hornelore-side first. Promote the *pattern* (active-listener composition + adaptive ladder under hard rule constraints) to Lorevox after it locks against the three Horne narrators. Implementation here will be Horne-coupled.
**Blocks:** parent sessions (~3 days out) require Phase 1 to ship before first contact with Janice / Kent.
**Lane:** Lori behavior. **NOT** extractor lane. Do not mix with SPANTAG / BINDING / LORI-CONFIRM work.

---

## Values clause (load-bearing — read first)

> *Lori is a companion, not an instrument. She is a listener that knows when not to speak. Any signal she uses — silence, posture, gaze, rhythm — exists only to help her be a better listener in this moment, never to characterize the narrator as a subject of study. The system computes no clinical score, builds no diagnostic profile, and produces no longitudinal report. Future contributors looking at the timing data and thinking "we could detect X from this" should bounce off this rule.*

This clause is the structural constraint, not a tone preference. Pull requests against any phase of this WO that introduce scoring, classification, drift tracking, severity bucketing, or any operator surface that aggregates timing data across sessions get rejected on this clause alone.

---

## Banned vocabulary

The following terms must not appear anywhere in **new or modified** code, comments, log lines, UI strings, prompts, schema field names, eval reports, or downstream documentation produced by this WO:

```
cognitive decline    MCI    dementia    diagnostic    severity    clinical signal
drift score          impairment           CDTD              decline detector
```

**Scope clarification:** the ban applies to output **introduced by this WO**. Pre-existing legacy references in unrelated code paths (e.g. older cognitive-support code from WO-10C, comments in modules this WO doesn't touch) are out of scope — a global grep that surfaces them is not a build failure. However:
- Do **not** expand, surface, or copy legacy banned terms forward into any file this WO modifies.
- If you are touching a file that has legacy banned terms in unrelated lines, leave them alone unless the operator instructs otherwise — migrating them risks behavior change outside this WO's scope.
- If you must touch the legacy line itself, migrate it to the rhythm/pace/listener vocabulary below.

Allowed framing — use these instead:

```
rhythm    pace    pacing    attention    listener    companion    fit    adapts
```

---

## Why this WO exists

Three independent failure modes converge in the same place — Lori's in-session response composer:

1. **Memory echo crashes.** *"What do you know about me?"* currently throws on a bad import in `chat_ws.py` (`from api.prompt_composer` should be `from ..prompt_composer`). Lori either fails or surfaces internal "API/offline" language. First parent session in ~3 days; this cannot ship as-is.

2. **Lori talks too much.** Composer rules aren't enforced uniformly across response paths. Some answers are warm and grounded; others stack questions, offer menus, or read like a database dump.

3. **Lori doesn't know when to wait.** WO-10C's 120s / 300s / 600s silence ladder treats deep-thinkers and passive-waiters identically because it has no signal to distinguish them. The result: deep thinkers get nagged; passive waiters get abandoned. Both are corrosive in a life-review setting.

The three problems share a surface (Lori's composer) and a gold standard (warm, one ask, grounded, no nag). Bundling them into one WO under one composer discipline is the structural fix; splitting them into three WOs would let the voicing fragment.

---

## Decisions locked

```
1. Concept name:  Adaptive Narrator Silence Ladder
   (NOT adaptive thresholds, pacing fit, drift detector, decline ladder)

2. Purpose:
   Help Lori decide whether to wait, gently cue, or offer a simpler prompt.
   NOT diagnose cognition. NOT score anything. NOT create clinical reports.

3. Inputs (the only signals the ladder consumes):
   - response_gap_ms          (narrator_turn_start_ts − lori_turn_end_ts)
   - prompt_weight            (low / med / high — Lori-side classification)
   - mic_activity             (any sound in narrator audio above VAD threshold)
   - MediaPipe attention      (passive_waiting / engaged / face_missing / unknown)
   - recent narrator baseline (rolling window per narrator × prompt_weight)

4. Safe framing (what Lori embodies, what we tell ourselves):
   Some narrators need more time.
   Some are thinking.
   Some are waiting for help.
   Lori adapts to that person's rhythm.

5. Core logic (operational definition):
   If narrator is quiet but visually engaged:
     wait longer
   If narrator is quiet and visually passive:
     give one gentle cue
   If narrator is quiet very long:
     offer a simpler starting point
   If narrator begins speaking:
     do not interrupt

6. Composer discipline rules (universal across all three response paths —
   memory echo, interview question, attention cue):
   - intent-aware word caps:
     * `memory_echo`: max 100 words (structured readback; narrator asked
       for it). The Phase 1 reference example is ~75 words and correct.
     * `interview_question`: max 55 words (default ordinary turn)
     * `attention_cue`: max 25 words (cue may be statement-only)
     * `repair` / `clarify`: max 30 words
     * `safety`: exempt — owned by WO-LORI-SAFETY-INTEGRATION-01
   - max 1 question mark
   - max 1 atomic ask
   - reflect one concrete detail before asking
   - no menu questions
   - no "Are you still there?"
   - no "Please respond"
   - no internal/error language ("API", "offline", "undefined")

7. Augments WO-10C — does NOT replace it.
   The 120s / 300s / 600s no-signal ladder remains the fallback when camera
   is off or MediaPipe state is unknown. The adaptive ladder only activates
   when MediaPipe state is positively confident.

8. Hard floor: 25 seconds.
   No cue fires before 25s after Lori finishes speaking, regardless of any
   signal. The narrator deserves the first 25s no matter what.

9. Window persistence:
   Per-narrator rolling window of last ~30 turns persists between sessions
   only as much as needed for warm cold-start. No long-term aggregate is
   retained. No surface exposes the window data.

10. Lab/gold:
    Hornelore-side first. Promote the pattern, not the wiring, once locked.
```

---

## Acceptance rule

```
PASS if Lori adapts to the narrator's pace without nagging, interrupting,
diagnosing, or over-questioning.
```

Per-scenario PASS/FAIL conditions are spelled out in the test matrix below.

---

## Phases

### Phase 1 — Memory Echo Fix + Peek-at-Memoir Consultation

**Land first. Blocks parent sessions.** Two deliverables:

**1a. Import-fix hotfix (lands today, regression test added in this WO).**

```python
# server/code/api/routers/chat_ws.py

# OLD
from api.prompt_composer import compose_memory_echo

# NEW
from ..prompt_composer import compose_memory_echo
```

Add regression test that posts *"what do you know about me?"* through the chat WS path and asserts (a) no exception, (b) no `"API"` / `"offline"` / `"undefined"` substring in response, (c) response goes through `compose_memory_echo` (logged marker).

**1b-minimum. Memory-echo composer answers warmly from profile + runtime data.** *(Parent-session blocker — must land before Kent/Janice.)*

When a turn classifies as `memory_echo` intent, Lori must consult:

1. Profile facts (`profile_json` blob via `db.get_profile(person_id)` — implemented as `_build_profile_seed()` in `prompt_composer.py`)
2. `runtime71` payload from the UI (`speaker_name`, `dob`, `pob`, `projection_family`, optional UI-side `profile_seed`)
3. Parents / siblings / children / partner where present in the runtime or profile blob

Then produce a warm grounded answer that obeys the composer discipline rules (Phase 2). The answer must NOT contain "API" / "offline" / "undefined" / dict-stringified garbage. List values render through `_label_item` (preferredName / fullName / "First Last" composite / relation fallback). Reference style:

> *"Here's what I'm beginning to understand about you, Chris. You were born in Williston, North Dakota, grew up with Kent and Janice as central figures, and Bismarck became an important school-years anchor. I also know family, your work as an occupational therapist, your children, and your later marriage to Melanie are major threads in your story. What part of that feels most important for me to understand more deeply?"*

What this answer does right: warm first-person voicing; grounded in facts Lori actually has; organized but not sterile; one gentle invitation at the end, not a stack of questions; no "let me query the database" register.

Files touched (1b-minimum): `server/code/api/routers/chat_ws.py`, `server/code/api/prompt_composer.py`.

**1c. Promoted truth + session transcript + Peek-at-Memoir read accessor.** *(Post-parent-session enrichment. Defer if Peek-at-Memoir doesn't expose a clean read path — fall back to 1b-minimum sources only.)*

Once Phase 1b-minimum is live and verified with Christopher / Kent / Janice, extend the consultation set to:

5. Promoted truth (`family_truth_promoted`) — additional confirmed facts that aren't in the template/profile blob
6. Recent session transcript (current `conv_id` turns, structured only — never raw memoir prose treated as fact)
7. Peek-at-Memoir scaffold/draft (NEW read path — `chat_ws` does not currently access this; small read-only accessor required at `services/memoir_peek.py`)

**Stop condition for 1c:** if the Peek-at-Memoir read path is expensive (LLM call, slow DB join, etc.), fall back to 1b-minimum sources only. Don't block parent-session readiness on the accessor.

Files touched (1c): same two files as 1b-minimum, plus `services/memoir_peek.py` if the accessor lands.

---

### Phase 2 — Interview Discipline (universal composer rules)

**Land before parent sessions, alongside Phase 1.** This is the foundational fix — if Lori is asking bad questions, none of the other phases matter. Two-layer defense: system prompt block (primary) makes the LLM produce compliant output; runtime filter (fallback) trims when the LLM drifts. Both layers ship.

#### Two-layer defense

**Layer 1 — System prompt block (primary).** Inject `LORI_INTERVIEW_DISCIPLINE` constant into the system prompt after the session-style block and before any question-generation instructions:

```python
# server/code/api/prompt_composer.py

LORI_INTERVIEW_DISCIPLINE = """
INTERVIEW DISCIPLINE — STRICT

You are an oral-history interviewer, not a questionnaire menu.

For ordinary narrator turns:
- Maximum 55 words.
- Ask at most ONE question.
- Ask at most ONE actual thing.
- Do not ask compound, double-barreled, or multi-part questions.
- Do not offer menus such as "or we could..." / "would you rather..." / "which path...".
- Do not summarize the whole life story unless the narrator asks.
- After a long disclosure: reflect ONE specific detail, then ask ONE concrete follow-up.
- If the narrator seems unsure, simplify the question instead of adding choices.

Preferred shape:
1. One brief reflection anchored to the narrator's exact words.
2. One focused question.
3. Stop.

Bad:
"What was that like for you, and how did it affect your family, or would you rather talk about something else?"

Good:
"Bismarck sounds like an important anchor in your story. What is one scene from that time that still feels vivid?"
"""

# Then in the system-prompt assembly:
parts.append(LORI_INTERVIEW_DISCIPLINE)
```

**Layer 2 — Runtime filter (fallback).** Conservative post-generation guard in `chat_ws.py` that trims menu/compound behavior when the LLM overtalks. Does not invent content; only trims.

```python
# server/code/api/routers/chat_ws.py
import re
import logging

log = logging.getLogger(__name__)

# NOTE: "would you like to" is NOT blanket-blocked — only when followed by an "or" clause.
#       Bare "Would you like to share more?" is a valid soft invitation.
_MENU_PATTERNS = [
    r"\bor would you\b",
    r"\bor maybe\b",
    r"\bor perhaps\b",
    r"\bwhich (one|path|direction)\b",
    r"\beither of those\b",
    r"\bor explore\b",
    r"\bwould you like to\b.{0,80}\bor\b",   # menu form only
    r"\bwould you rather\b",
]

# NOTE: "and what/how/when/where/why" patterns require a wh-clause AFTER the "and"
#       to count as compound. "And how he met your mother" inside a single declarative
#       is fine; "and how did your parents meet" appended to a separate question is not.
#       Detection strategy: count wh-words within a single ?-bounded segment.
_COMPOUND_AND_PATTERNS = [
    r"\band how (did|do|does|was|were|is|are)\b",
    r"\band what (did|do|does|was|were|is|are|happened|kind)\b",
    r"\band when (did|do|does|was|were|is|are)\b",
    r"\band where (did|do|does|was|were|is|are)\b",
    r"\band why (did|do|does|was|were|is|are)\b",
    r"\band did (you|she|he|they|it)\b",
]

_WH_WORDS = re.compile(r"\b(what|who|when|where|why|how|which)\b", re.IGNORECASE)

# Intent-aware ceilings — do NOT use one universal cap.
INTENT_DISCIPLINE = {
    "memory_echo":       {"max_words": 100, "max_questions": 1},  # summarising known facts
    "interview_question":{"max_words":  55, "max_questions": 1},  # default
    "attention_cue":     {"max_words":  25, "max_questions": 1},  # cue may be statement-only
    "repair":            {"max_words":  30, "max_questions": 1},
    "safety":            {"max_words": 200, "max_questions": 0},  # safety responses exempt;
                                                                  # see WO-LORI-SAFETY-01
}

def _word_count(text: str) -> int:
    return len(re.findall(r"\b\S+\b", text or ""))

def _count_wh_words_per_question(text: str) -> int:
    """Detect compound questions by counting wh-words within a single ?-bounded segment."""
    segments = re.split(r"\?", text)
    return max((len(_WH_WORDS.findall(seg)) for seg in segments if seg.strip()), default=0)

def _lori_question_discipline_filter(text: str, intent: str = "interview_question") -> str:
    """
    Conservative post-generation guard. Does not invent content.
    Trims menu/compound behavior when Lori overtalks. Intent-aware.
    Safety-intent responses bypass discipline entirely (handled by WO-LORI-SAFETY-01).
    """
    if not text or intent == "safety":
        return text

    rules = INTENT_DISCIPLINE.get(intent, INTENT_DISCIPLINE["interview_question"])
    max_words = rules["max_words"]
    max_questions = rules["max_questions"]

    original = text.strip()
    text = original

    # Question-mark cap.
    if max_questions > 0:
        first_q = text.find("?")
        if first_q != -1 and text.count("?") > max_questions:
            text = text[: first_q + 1].strip()

    lower = text.lower()
    has_menu = any(re.search(p, lower) for p in _MENU_PATTERNS)
    has_compound_and = any(re.search(p, lower) for p in _COMPOUND_AND_PATTERNS)
    has_compound_wh = _count_wh_words_per_question(text) > 1
    too_long = _word_count(text) > max_words

    if has_menu or has_compound_and or has_compound_wh or too_long:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept = []
        target_words = min(max_words, 50) if intent != "memory_echo" else max_words
        for s in sentences:
            if not s.strip():
                continue
            kept.append(s.strip())
            if "?" in s and max_questions > 0:
                break
            if _word_count(" ".join(kept)) >= target_words - 10:
                break
        text = " ".join(kept).strip()

    if text != original:
        log.info(
            "[lori][discipline] intent=%s words_before=%s words_after=%s "
            "q_before=%s q_after=%s menu=%s cmpd_and=%s cmpd_wh=%s",
            intent,
            _word_count(original),
            _word_count(text),
            original.count("?"),
            text.count("?"),
            has_menu,
            has_compound_and,
            has_compound_wh,
        )

    return text
```

Call site (right before emitting Lori's final message over WebSocket):

```python
assistant_text = _lori_question_discipline_filter(
    assistant_text,
    intent=intent_classifier_result,   # whatever upstream classified the turn as
)
```

#### Intent-aware discipline tiers (the table)

| Intent | Max words | Max questions | Notes |
|---|---|---|---|
| `memory_echo` | 100 | 1 | Summarising known facts is the point — longer ceiling. The Phase 1 reference example is ~75 words and correct. |
| `interview_question` | 55 | 1 | Default. ChatGPT's discipline spec applies in full. |
| `attention_cue` | 25 | 0–1 | Cue may be statement-only ("Take your time"). Tier 0 silent indicator skips composer entirely. |
| `repair` / `clarify` | 30 | 1 | Tight; clarify the previous turn, don't expand. |
| `safety` | 200 | 0 | **Exempt from discipline.** Safety responses owned by WO-LORI-SAFETY-01; resources need to fit; warmth and care matter more than word count. |

The 1-question rule is universal across non-safety intents. The word-count cap varies; safety is the only exemption.

#### Pushbacks on ChatGPT's patch (already applied above)

1. **`would you like to`** changed from blanket block to menu-form-only (`would you like to ... or ...`). Bare *"Would you like to share that memory?"* is a valid soft invitation and stays.
2. **`and what/how/when/where`** changed from blanket block to verb-grounded patterns AND wh-word counting per question segment. *"Tell me about Bismarck and how it shaped you"* is one ask; *"What was Bismarck like, and how did your parents meet?"* is compound. The wh-counter catches the second; the verb-grounded pattern catches the explicit appended-question form.

#### What this WO does NOT change about the LLM

It does not retrain the model. It does not increase model size. It does not add reasoning chains. **It enforces restraint on whatever the model produces.** That's the entire job. A more restrained Lori is a better interviewer — not a smarter one.

#### Files touched

- `server/code/api/prompt_composer.py` — add `LORI_INTERVIEW_DISCIPLINE` constant; append to system-prompt assembly
- `server/code/api/routers/chat_ws.py` — add filter function; wire into emit path; survey current variable names first (`assistant_text` may not be the actual name)
- Bug-panel surfacing of `[lori][discipline]` violations during dev sessions (existing Bug Panel infrastructure)

#### Acceptance for Phase 2

| Test | Pass condition |
|---|---|
| 30-turn dev session | Zero `[lori][discipline] violation=` log entries (system prompt holds) OR all violations cleanly trimmed by filter (fallback works) |
| Compound rejection | *"What was that like, and how did it affect your family?"* → trimmed to first question only |
| Menu rejection | *"Would you like to talk about Bismarck, your parents, or another part of your childhood?"* → trimmed |
| Soft invitation preserved | *"Would you like to share more about that?"* → not modified |
| Memory echo not over-trimmed | Reference response (~75 words) on `memory_echo` intent → not trimmed |
| Safety exemption | Safety-classified turn → discipline filter is bypassed entirely |

---

### Phase 3 — MediaPipe Attention Cue

Add a passive-waiting detector that fires ONE warm cue when the visual signal positively indicates the narrator is waiting (not thinking).

**Detector inputs** (all four required for `passive_waiting`; three-of-four is `unknown` and falls back to time ladder):

```
- gaze_forward         (looking at screen)
- low_movement         (no animated retrieval / breath gathering)
- no_speech_intent     (mouth not pre-shaping a word)
- post_tts_silence_ms  (Lori already finished, > floor)
```

`face_missing` is its own state — narrator stepped away, sneezed, looked at her phone. Not "passive waiting." No cue fires; time ladder waits to next tier.

**Cue type tiering** (the cue type ladders, not just timing):

| Tier | Trigger | Cue type | Example |
|---|---|---|---|
| 0 | passive_waiting confident, gap ≥ 25s | silent presence affirmation | "Lori is listening" indicator pulses softly. No speech. |
| 1 | passive_waiting confident, gap ≥ 60–90s | affirmation, not question | *"Take your time. There's no rush."* |
| 2 | passive_waiting confident, gap ≥ 120–180s | soft offer | *"I'm here with you. Would it help if I gave you a simpler starting point?"* |
| 3 | gap ≥ 300s, any signal | warmer re-entry with concrete prompt | composer-generated, warm, single ask |
| 4 | gap ≥ 600s, any signal | offer break | *"Would you like to take a break?"* |

**Cooldown:** after any spoken cue (Tier 1+), no further cue for at least 90 seconds even if gap continues.

**Veto rule (cardinal):** if MediaPipe state is `engaged` / `reflective` (deep thinking), no cue fires at any tier below WO-10C's no-signal 120s mark. The visual signal can only *accelerate* a cue when it positively confirms passive waiting — uncertainty defaults to the long ladder.

**Logging:** every cue logged with `reason=attention_cue` + `tier=N` + `signal_state=passive_waiting` + `gap_ms=N`. Used for the test scenarios in Phase 5; not surfaced to the narrator.

Files touched: `ui/js/emotion.js` (visual signal classification — already partly there via cognitive-auto.js v7.4C), `ui/js/state.js` (`visualSignals` + `attention_state` + `last_seen_ms`), new `ui/js/attention-cue-dispatcher.js`, Lori cue composer (lives in same composer module as Phases 1–2 — single composer rule).

---

### Phase 4 — Adaptive Silence Ladder

Lori notices this narrator's natural rhythm over the recent window and fits her cueing to it. Not measurement. Not tracking. Just enough memory to fit.

**Phase 4 prep — data plumbing (lands with Phase 1, free):**

```
- Add lori_turn_end_ts        per Lori turn  (already partly via WO-TRANSCRIPT-TAGGING-01)
- Add narrator_turn_start_ts  per narrator turn
- Add prompt_weight           per Lori turn  (low / med / high — composer-side classification)
```

**Per-narrator rolling state** (kept small, scoped tight):

```
narrator_pacing[narrator_id][prompt_weight] = {
  recent_gaps: [<= 30 most recent response_gap_ms for this prompt_weight],
  last_updated: ts
}
```

**Ladder calculation** (per `narrator × prompt_weight`, recomputed lazily on cue-decision):

```
window = recent_gaps (last 30, or fewer if cold-start)

if len(window) < 10:
  # cold-start — fall back to WO-10C defaults
  tier1, tier2, tier3 = 120s, 300s, 600s
else:
  p75 = percentile(window, 75)
  p90 = percentile(window, 90)
  p95 = percentile(window, 95)
  tier1 = max(FLOOR_MS, p75 + 5s)
  tier2 = max(tier1 * 2, p90 + 10s)
  tier3 = max(tier2 * 2, p95 + 30s)

FLOOR_MS = 25_000
```

**Persistence:** stored locally only, attached to narrator profile. No aggregate, no trend, no operator-visible surface. The window naturally fades because old entries fall off. No "narrator pacing report" view exists in code or UI.

**Fusion with Phase 3 (the three cases):**

| Case | Signal state | Behavior |
|---|---|---|
| 1 — Waiting | `gap > tier1` AND MediaPipe = `passive_waiting` | Cue early (Phase 3 Tier 1 or 2 per gap) |
| 2 — Thinking | `gap > tier1` AND MediaPipe = `engaged` / `reflective` | No cue. Wait to next tier minimum or signal change. |
| 3 — Long-silence fallback | `gap > tier2` (any signal, including no signal) | Cue regardless. Tier 2 type. |
| 4 — Speaking | `mic_activity` detected at any point | Suppress any pending cue. Do not interrupt. |

Files touched: `server/code/services/narrator_pacing.py` (new — pure-Python rolling-window helper, no clinical surface), `server/code/api/routers/chat_ws.py` (cue dispatcher consults pacing helper), `ui/js/archive-writer.js` (timestamp emission already partly there — extend), `state.js` (small in-memory mirror).

---

## Test matrix (Phase 5)

Test-lab scenarios that exercise the acceptance rule. Run as part of `WO-UI-TEST-LAB-01` operator harness; PASS/FAIL bucketed automatically where possible, reviewer-judged for warmth/grounding.

| Scenario | Setup | Expected | Fail condition |
|---|---|---|---|
| Memory echo basic | Narrator types *"what do you know about me?"* | Warm grounded answer ≤100w (`memory_echo` intent cap), ≤1 question mark, references real profile facts, ends with one invitation | Crash, "API/offline" language, database-dump tone, multiple questions |
| Memory echo with Peek | Narrator types same with Peek-at-Memoir scaffold present | Answer references content from Peek-at-Memoir alongside profile | Peek content ignored |
| Deep thinker, camera engaged | Narrator silent 90s after Lori prompt; MediaPipe state = `engaged` | No cue fires before WO-10C's 120s mark | Cue fires early |
| Passive waiter, camera passive | Narrator silent 30s after Lori prompt; MediaPipe state = `passive_waiting` (all 4 inputs confirmed) | Tier 0 silent indicator at 25–30s, Tier 1 spoken cue at 60–90s | No cue, or cue stacks questions, or cue uses banned vocabulary |
| Camera off, no signal | Narrator silent; camera consent declined | WO-10C 120s/300s/600s ladder fires unchanged | Faster ladder fires (would mean adaptive path leaked into no-signal case) |
| Narrator starts speaking mid-cue-decision | `mic_activity` detected during cue dispatch | Cue suppressed; Lori does not speak | Lori interrupts |
| Long silence, all paths | Narrator silent 600s | Break offer fires, warm | "Are you still there?" or any nag |
| Cooldown | Cue fires; narrator silent another 60s | No second cue (in 90s cooldown) | Cue stacks |
| Composer discipline universal | Run full session, 30 turns | Zero **untrimmed** violations reaching the narrator. Layer 2 trim logs (`[lori][discipline] trim-to-one-q`) are warnings, not failures — the filter doing its job is acceptable. Each trim log must include `before_len` / `after_len` / `reason`. **Repeated trim logs on the same code path** become a Layer 1 prompt-composer bug to investigate. | Untrimmed compound/nested/menu reaches narrator |
| `face_missing` not treated as waiting | Narrator out of frame for 60s | No cue fires (`face_missing` ≠ `passive_waiting`) | Cue fires |
| Cold-start narrator | New narrator, < 10 turns of data | Falls back to WO-10C 120s/300s/600s | Adaptive ladder activates with insufficient data |
| Window-fit narrator | Narrator with 30 turns banked, p75 gap = 35s | Tier 1 fires at ~40s when MediaPipe confirms passive | Tier 1 fires at default 60s instead of fitted 40s |

---

## Failure conditions (what the WO must NOT produce)

```
- Lori asks "Are you still there?" or "Please respond" — ever
- Lori stacks questions
- Lori interrupts active speech
- Lori treats face_missing as passive_waiting
- Lori cues a deep-thinker before WO-10C's 120s no-signal mark
- Lori uses banned vocabulary in any output (logs, code, UI)
- Pacing data persists in any surface readable as a report or trend
- Memory echo crashes or surfaces internal/error language
- Discipline violations leak past the final composer guard
- Adaptive ladder activates with insufficient data (< 10 turns)
- Cue fires below 25s floor under any circumstance
```

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Vocabulary creep — "rhythm" → "pace data" → "pace report" → eventually clinical | Banned-vocabulary list checked in linter / pre-commit hook (manual code review at minimum); values clause cited in PR template |
| Composer fragmentation — three legs producing three voices | Single composer guard runs final pass on every response path; violations logged; rewrite-or-replace |
| WO-10C drift — adaptive ladder accidentally faster than no-signal ladder | Hard rule: no-signal narrators always get 120s/300s/600s; cold-start narrators (<10 turns) treated as no-signal |
| MediaPipe false positive on `passive_waiting` — narrator actually thinking | Veto rule: `engaged` / `reflective` blocks cue under WO-10C's 120s mark; uncertainty defaults to long ladder |
| Adaptive window feels surveilly even though it isn't surfaced | Narrator-visible disclosure in onboarding: *"Lori notices the rhythm of how you talk so she can be a better listener with you."* No more, no less. |
| Operator pressure to surface pacing data later | Values clause is the rejection ground. Cite it in PR comments. |
| Lori cue composer drift from Phase 2 discipline | Same enforcement point; **zero untrimmed violations reaching the narrator** on Phase 5 30-turn run is the gate (Layer 2 trim logs are acceptable; see acceptance row above) |

---

## Cross-references

- **WO-10C** — Cognitive Support Mode (the no-signal silence ladder this WO augments). 120s / 300s / 600s ladder unchanged for camera-off and cold-start narrators.
- **WO-NARRATOR-ROOM-01** — narrator-room layout, where the cue indicator (Tier 0) renders.
- **WO-TRANSCRIPT-TAGGING-01** — per-turn metadata that already provides part of the timestamp infrastructure Phase 4 needs.
- **WO-ARCHIVE-INTEGRATION-01** — two-sided text transcript writer (existing).
- **WO-UI-TEST-LAB-01** — operator harness where the Phase 5 test matrix runs.
- **WO-AFFECT-ANCHOR-01** — separate parked WO; multimodal affect anchoring is a different concern (memory-preservation artifact, not in-session listener behavior). Do not couple.
- **`facial-consent.js`** — existing consent surface; reuse, do not rewrite.
- **`emotion.js` / cognitive-auto.js v7.4C** — existing visual signal classification; extend for `passive_waiting` detection.

---

## File targets summary

```
NEW:
  server/code/services/narrator_pacing.py
  ui/js/attention-cue-dispatcher.js

MODIFIED:
  server/code/api/routers/chat_ws.py        (import fix + memory_echo route + cue dispatch)
  server/code/api/prompt_composer.py        (Peek-at-Memoir consultation + discipline guard)
  ui/js/emotion.js                          (passive_waiting detector)
  ui/js/state.js                            (visualSignals + attention_state + pacing mirror)
  ui/js/archive-writer.js                   (extend timestamp emission)

POSSIBLE NEW (if Peek-at-Memoir lacks chat-accessible read path):
  server/code/services/memoir_peek.py
```

---

## Stop conditions

Stop work and reconvene with Chris if any of these surface during build:

1. Phase 1 import-fix doesn't close the memory-echo crash cleanly (suggests deeper wiring rot).
2. Peek-at-Memoir read path turns out to be expensive (e.g., would require LLM call from inside chat_ws — that's a no, regress to profile + promoted truth + transcript only).
3. MediaPipe attention state proves too noisy in real session conditions to support a confident `passive_waiting` classification — fall back to time ladder only, file follow-up WO for visual-signal hardening.
4. Adaptive ladder math produces a tier1 below 25s on any prompt_weight — investigate window contamination (probably mixing question types).
5. Any phase requires breaching the values clause to ship — stop, escalate, do not ship.

---

## Final directive

Build to the values clause. The acceptance rule is the gate. Banned vocabulary is structural. Phases 1–2 land before parent sessions. Phases 3–4 follow once Phase 1–2 lock; no rush, no compromise on the discipline.

Lori is a listener that knows when not to speak.
