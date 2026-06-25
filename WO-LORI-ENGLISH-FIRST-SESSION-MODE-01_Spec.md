# WO-LORI-ENGLISH-FIRST-SESSION-MODE-01

**Status:** ACTIVE / PHASE 1 LANDING
**Severity:** MEDIUM (replaces a structurally-wrong prompt rule with the right one)
**Origin:** 2026-06-25 Chris + ChatGPT review after Spring 2026 trip canary
**Depends on:** none
**Blocks:** none (composes cleanly with `WO-TRIP-IMPORT-AND-CLUSTER-01_Spec.md`)
**Locked principle:** English is the default for narrator chat. Foreign content (place names, food terms, accented words, menus, signs, route stacks) is STORY CONTENT, not a language preference. Lori must NOT auto-switch the whole conversation to another language just because the narrator mentions a foreign place. Language switches are a deliberate choice — by the operator (via `session_language_mode` pin) or by the narrator (via explicit answer to Lori's one-time ask).

---

## Why this WO exists

The current `LANGUAGE MIRRORING RULE` at `prompt_composer.py` L77 says:

> *"Respond in the language the narrator most recently used. If they spoke Spanish, respond in Spanish. If they spoke English, respond in English. If they code-switched, mirror their pattern."*

Three real failure modes that rule produces:

1. **Spring 2026 trip canary** — narrator speaks English about Prague→Salzburg→Ljubljana, Lori pattern-completes into Spanish because the LLM reads the proper nouns as "foreign." Patched downstream with chain-aware fallback + ENGLISH_FIRST_RULE fewshots, but the underlying rule still pulls the wrong direction.
2. **Code-switch mirroring trap** — narrator drops one Spanish word in an English sentence ("we had svíčková"), Lori reads "code-switched" → mirror → switches to Spanish for the whole reply.
3. **No-ask switch** — sustained Spanish narrator turn silently flips the entire interview language with no confirmation. Operator who didn't intend a Spanish session has no signal that it happened.

The replacement is a `LANGUAGE MODE RULE` plus a paired `VOICE PRESERVATION RULE`. Together: English by default, ask before switching full language, preserve narrator's verbatim foreign words while optionally helping the memoir reader.

---

## Phase 1 — what lands in this WO (one commit)

### Rule rewrite

Replace `prompt_composer.py` L77-83 (`LANGUAGE MIRRORING RULE` block) with:

```text
LANGUAGE MODE RULE: English default. session_language_mode pin
overrides. Foreign place names / food / signs are story content,
not language preferences. On sustained foreign-language narrator
turn with no session pin, ask once whether to continue in that
language. After narrator chooses, follow that preference.

VOICE PRESERVATION RULE: Echo narrator's foreign words verbatim.
Optional parenthetical explanation on first mention if it helps
a memoir reader. Optional offer to add a fuller explanation. Never
replace narrator's word with a translation.
```

Concrete prompt text in `Implementation` section below.

### Composition with existing infrastructure

The new rule defers to:

- `session_language_mode` field on profile_json — set via `scripts/set_session_language_mode.py` (operator script). Values: `english` / `spanish` / `mixed`. When set, the new rule SKIPS the ask and follows the pin.
- `ENGLISH_FIRST_RULE` (prompt directive added in BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01 Path A) — handles single foreign words + place-name pile-ups at prompt time. Reinforces LANGUAGE MODE RULE; does not conflict.
- Post-LLM `repair_language_drift` (in `lori_response_guards.py`) — runs as the safety net if drift slips through. Now uses chain-aware English continuation. Stays active.

### Soft-ask-don't-loop (Phase 1)

If narrator gives a sustained foreign-language turn with no session pin:

- Lori asks ONCE: *"I can keep going in English, or respond in Spanish if that is easier — which would you prefer?"*
- If narrator's NEXT turn answers explicitly, Lori follows.
- If narrator's next turn is also sustained foreign-language but does NOT answer, Lori defaults to English (status quo) and may ask again.
- **No persistent state** in Phase 1. Phase 2 closes the loop via narrator-initiated `session_language_mode` write.

---

## Non-goals

Phase 1 does NOT:

- Wire narrator-initiated `session_language_mode` write (that's Phase 2).
- Touch SPANISH PERSPECTIVE RULE / SPANISH SENTENCE COMPLETENESS RULE / other Spanish-shaping rules in the prompt. Those describe HOW Spanish responses should be shaped when they happen — orthogonal to WHEN Lori switches.
- Change `looks_spanish()` or any guard. Detection logic stays.
- Touch `repair_language_drift` or the chain-aware English fallback.
- Block memoir export from using foreign terms with translations — narrator-facing rule only.

---

## Phase 2 — followup (separate WO, not in this commit)

Narrator-initiated `session_language_mode` write flow:

1. Detect when the narrator's reply to Lori's language-mode question is an explicit choice ("Spanish please" / "English" / "let's stay in English"). Deterministic regex over the reply text.
2. Write the chosen value to `profile_json.session_language_mode` for the narrator's session.
3. On the next turn, the new rule sees the pin and skips the ask permanently.

Why this is Phase 2: it requires a new write path in `chat_ws.py` and a deterministic intent classifier for narrator language-choice replies. Worth doing only if Phase 1 evidence shows the soft-ask-don't-loop produces re-asking that frustrates narrators.

---

## Implementation — prompt text (Phase 1)

Concrete replacement for the LANGUAGE MIRRORING RULE block:

```text
"LANGUAGE MODE RULE: English is the default for narrator chat unless "
"the narrator's session_language_mode is explicitly pinned to another "
"language OR the narrator clearly asks Lori to respond in another "
"language. Foreign place names (Prague, Ljubljana, Pula, Mirano, "
"Padua, Cittadella, Chioggia, Venice, Roma), food terms (svíčková, "
"prosciutto, gelato), accented words, signs, menus, and travel routes "
"are STORY CONTENT, not language preferences — they do not trigger a "
"language switch on their own. If session_language_mode is set "
"('english' / 'spanish' / 'mixed'), follow that pin and DO NOT ask. "
"If session_language_mode is unset AND the narrator writes a full "
"turn in another language, Lori responds briefly in English and asks "
"once: \"I can keep going in English, or respond in Spanish if that "
"is easier — which would you prefer?\" (substitute the actual detected "
"language in that template). Do not assume a permanent switch from a "
"single foreign turn. Once the narrator chooses a language for the "
"session, follow that preference until they change it. "

"VOICE PRESERVATION RULE: When echoing or reflecting the narrator's "
"own foreign words back to them, preserve the word verbatim. If the "
"narrator said 'svíčková', Lori says 'svíčková' — not 'a Czech beef "
"dish'. Lori MAY add a brief parenthetical explanation ON FIRST "
"MENTION when it would help the memoir reader, formatted as a short "
"appositive (e.g. 'svíčková (the Czech beef-and-cream dish)'). Lori "
"MAY ALSO offer once: \"Would you like me to add a short note about "
"what svíčková is, for memoir readers who don't know it?\" Never "
"replace the narrator's word with a translation; preserve names, "
"places, culturally-specific terms, and quoted words exactly as the "
"narrator said them. "
```

---

## Acceptance criteria

```text
1. prompt_composer.py L77 LANGUAGE MIRRORING RULE block REPLACED with
   LANGUAGE MODE RULE + VOICE PRESERVATION RULE per Implementation
   section above. AST parses clean.

2. SPANISH PERSPECTIVE RULE / SPANISH SENTENCE COMPLETENESS RULE /
   downstream Spanish-shaping rules NOT touched. grep should confirm
   they are still present at their original line offsets +/- the rule
   replacement delta.

3. session_language_mode pin path verified — when profile_json carries
   session_language_mode='spanish', a probe call to compose_system_prompt
   shows Lori is still allowed to respond in Spanish (rule defers to
   the pin).

4. Trip-route canary re-runs after stack restart: G3 (lori_reply_is_english)
   still 100% across graded turns. G2 (not drift repair) still zero
   firings. No regression on the post-Path-A 45/49 GREEN baseline.

5. Factual-chain regression harness re-runs: no regression on
   post-Path-A 47/49 GREEN. Kent canary still preserves chain in English.

6. Visual confirmation in api.log: at least one live conv where Lori
   echoes a narrator's foreign term verbatim (svíčková / prosciutto /
   etc.) without translating. Operator-side review.

7. No new unit tests required for Phase 1 — the rule is prompt-side
   directive, not deterministic code. Behavior is verified via the
   two live harnesses + visual inspection.
```

---

## Stop conditions

Stop and reassess if:

- session_language_mode='spanish' narrators (María, Esteban-class) stop receiving Spanish replies.
- Lori refuses to translate a foreign word when the narrator explicitly asks ("what does svíčková mean?").
- Lori's parenthetical explanations grow into multi-sentence digressions ("svíčková (the famous Czech beef-and-cream dish that is traditionally served on Sundays with bread dumplings and cranberry sauce, and is considered one of the national dishes of the Czech Republic...)").
- The one-time ask becomes a loop on every Spanish turn from the same narrator.
- Boris quality suite regresses on existing narrator-tab behavior.

---

## Files likely to touch

```text
server/code/api/prompt_composer.py
    L77-83 — replace LANGUAGE MIRRORING RULE block with LANGUAGE MODE
    RULE + VOICE PRESERVATION RULE
```

No new spec dependencies; no migration; no test changes; no router changes.

---

## Revision history

- 2026-06-25 — Created from 2026-06-24 Spring 2026 trip canary evidence + Chris + ChatGPT review of the LANGUAGE MIRRORING RULE failure modes. Phase 1 = rule rewrite. Phase 2 = narrator-initiated session_language_mode write flow, deferred.
