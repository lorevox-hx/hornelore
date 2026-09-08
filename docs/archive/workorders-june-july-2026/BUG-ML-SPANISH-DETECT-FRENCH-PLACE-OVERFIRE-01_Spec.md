# BUG-ML-SPANISH-DETECT-FRENCH-PLACE-OVERFIRE-01

**Status:** LANDED 2026-07-02 (code + unit tests; live verification pending next stack cycle)
**Severity:** HIGH (narrator-visible Spanish output in an English session)
**Origin:** 2026-07-02 05:19 live run of `run_trip_2019_france_italy_canary_harness.py` — T4 narrator saw `"Disculpa, continuemos. ¿Qué te gustaría contarme ahora?"` on a fully-English French-trip session.
**Surfaces:** `server/code/api/services/lori_spanish_guard.py`, `server/code/api/services/lori_response_guards.py`, `server/code/api/routers/chat_ws.py`

## Locked principle

*A language detector that routes narrator-visible output must be precision-first. Accented vowels and function words shared with English/French/Italian are not Spanish evidence on their own. When a session-language profile pin exists, heuristics are advisory — the pin governs every repair target.*

## Root cause (three layers, all confirmed from api.log 57716/57744/57745)

1. **`lori_spanish_guard.looks_spanish` accent tier was case-sensitive.** T3's narrator turn ("Trocadéro … Champs Élysées") produced `é` + `É` = "two distinct accents" → Spanish. Additionally "Palais **de** Chaillot" made `de` a function-word hit, so the accent+word tier fired too. French/Italian share ONLY acute `é` with Spanish (French has no `á í ó ú`; Italian uses grave accents), so casefolded accent counting is safe — the word list was the real hazard: `de, la, en, que, es, son, era, hay, once, como, vino, vine, con, sin, el, los, las, una, …` are all common English/French/Italian tokens.
2. **The misfire was sticky.** The 3-turn smoothing window (`prior_es_index`) carried `guard_target=es` into T4–T6.
3. **`lori_response_guards._looks_spanish` had the same class of hole.** Lori's English T4 reply ("Can you tell **me** about … **Marché** d'Aligre") satisfied accent + "me" (an English word present in the Spanish word list) → drift fired with target=es → the English reply was replaced with the Spanish neutral repair.

## Fix (landed)

- `lori_spanish_guard.looks_spanish`: casefolded accent set (acutes only); `ñ/¿/¡` promoted to definitive; `_AMBIGUOUS_FUNCTION_TOKENS` set — ambiguous tokens never carry the accent tier and the no-accent tier now requires ≥3 hits with ≥2 strong; NEW `_SPANISH_PHRASE_RX` definitive phrase tier ("me llamo", "se llamaba", "quise decir", "nací en", "mi madre" …) — this phrase tier also FIXED THREE PRE-EXISTING misses found at HEAD (`test_quise_decir_es`, `test_mother_name_es`, `test_cs_001_has_spanish_marker` were failing before this WO).
- `lori_response_guards._looks_spanish`: `_AMBIGUOUS_ES_TOKENS` exclusion (`me, te, se, nos, el, los, las, una, con, sin, era, que, cuando`) for the accent tier; no-accent tier requires ≥1 strong token.
- `chat_ws.py`: the `_session_lang_mode` profile pin now also governs `_guard_target_lang` (previously only witness/meta/memory-echo consulted it) — english-pinned narrators can never receive a Spanish repair even if a heuristic misfires. `lang-debug` log line extended with `lang_mode=`.
- Two known-overfire documentation tests in `test_lori_session_language_contract.py` flipped from assertTrue (documenting the bug) to assertFalse (locking the fix): "fiancée + Once", "attaché + son".

## Acceptance

1. `FrenchPlaceOverfireTest` (11 tests) green — includes literal 2019 T3/T4 turns. ✅
2. All prior Spanish suites green (spanish_guard 68, session contract, correction-ack, memory-echo-es, code-switching, response guards — 263 total). ✅
3. Live re-run of the 2019 harness: T4 reply is English (no "Disculpa"), `lang-debug` shows `guard_target=en` on all 8 turns, no `[lang-contract] … advisory routed lang=es` line. PENDING stack cycle.
4. Spanish live smoke (`run_spanish_live_smoke.py`) still green on a real Spanish narrator. PENDING stack cycle.

## Do-not-relitigate

- Do NOT re-add bare accent counting without casefolding.
- Do NOT let ambiguous tokens carry any single-signal tier.
- The drift-repair safety net stays ACTIVE — Kent K1/K2/K10 real-drift evidence (ñ/¡ or ≥2 strong words) still detects under the new tiers (verified in unit tests).

## Revision history

- 2026-07-02 — Created + landed in the same session (root-caused from api.log during the post-fix harness triage of the G3 clamp fix).
