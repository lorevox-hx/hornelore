# BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01

**Status:** FILED 2026-05-07 (night-shift bug hunt)
**Lane:** Multilingual / Lori output
**Severity:** YELLOW — affects Spanish narrators in three deterministic-composer paths (memory_echo, age_recall, continuation_paraphrase). Real Spanish narrators (Melanie Zollner) will hit at least the memory_echo path on every "qué sabes de mí" turn.
**Files:** `server/code/api/prompt_composer.py`, `server/code/api/routers/chat_ws.py`

---

## Evidence

The night-shift bug hunt traced three composers that emit text DIRECTLY to the narrator via WebSocket without an LLM round-trip — meaning the LANGUAGE MIRRORING RULE (which lives in the LLM system prompt) does NOT apply:

1. **`compose_memory_echo`** (`prompt_composer.py:1830`) — called from `chat_ws.py:1007` for `turn_mode == "memory_echo"`. Returns multi-line English text with section headers ("Identity", "Family", "What I'm less sure about"), narrator-facing prose ("Some parts are still blank, and that is completely fine..."), and footer ("Based on: profile, session notes."). All English.

2. **`compose_age_recall`** (`prompt_composer.py:1622`) — called from `chat_ws.py:1031` for age-question turns. Returns English: *"You were born on February 29, 1940, so you are 86 now."* / *"I don't have your birthday written down yet — would you like to share it?"*

3. **`compose_continuation_paraphrase`** (banked under WO-LORI-SWITCH-FRESH-GREETING-01 Phase 2 Slice 2a) — called from `interview.py:get_opener` when `HORNELORE_CONTINUATION_PARAPHRASE=1`. Returns English Tier C/D welcome-back: *"Welcome back, Mary. Last time we were in your building years..."*

A Spanish narrator like Melanie asking "¿qué sabes de mí?" or "cuántos años tengo?" will get an entirely English response in all three cases.

## Why the existing perspective + fragment guards don't catch this

Those guards run on LLM output only. Deterministic composers bypass the LLM call entirely, so post-LLM repair never sees their text. The guards are doing their job; the composers are emitting text the guards never see.

## Fix architecture

Three options, in increasing scope:

### Option A (minimum viable, narrator hears native language)

Add `target_language: str = "en"` parameter to all three composers. Branch the literal strings on Spanish:

```python
def compose_memory_echo(text, runtime=None, *, target_language="en"):
    is_es = target_language == "es"
    ...
    lines = [
        f"Esto es lo que sé de {speaker_name} hasta ahora:" if is_es
        else f"What I know about {speaker_name} so far:",
        ...
    ]
```

Detect at chat_ws call site:

```python
# chat_ws.py
target_lang = "es" if looks_spanish(user_text or "") else "en"
assistant_text = compose_memory_echo(text=user_text, runtime=runtime71, target_language=target_lang)
```

Pros: smallest change. Spanish narrators hear native phrasings.
Cons: doubles maintenance surface for the literal strings; section labels need professional Spanish review (this is what older narrators read).

### Option B (refactor to template-pack)

Extract all narrator-facing strings to a `_LOCALE_PACKS = {"en": {...}, "es": {...}}` dict at the top of prompt_composer.py. Composers reference `_pack[target_language]["section_identity"]` etc.

Pros: one centralized place for future locale additions.
Cons: ~100-line refactor, increases blast radius; recommended after Option A is verified live.

### Option C (LLM round-trip for all composer output)

Drop the deterministic-direct path entirely; compose a system-prompt-shaped instruction set + send through LLM with LANGUAGE MIRRORING RULE.

Pros: composer output gets perspective + fragment + question-quality guards "for free."
Cons: introduces LLM latency + hallucination risk on the deterministic path that was specifically built to AVOID those.

## Recommended path

**Option A**, sequenced:

1. Phase 1 — `compose_memory_echo` Spanish strings (biggest surface, real Melanie evidence)
2. Phase 2 — `compose_age_recall` Spanish strings
3. Phase 3 — `compose_continuation_paraphrase` Spanish strings (Tier C/D)
4. Phase 4 — chat_ws call site updates threading `target_language` from `looks_spanish(user_text)`

Each phase ships with unit tests + parses cleanly. Live verification on a real Spanish session before declaring closed.

## String inventory (Phase 1 — memory_echo)

Eleven narrator-facing strings need Spanish:

| English | Spanish |
|---|---|
| `What I know about {name} so far:` | `Esto es lo que sé de {name} hasta ahora:` |
| `Identity` | `Identidad` |
| `Name:` | `Nombre:` |
| `Date of birth` | `Fecha de nacimiento` |
| `Place of birth` | `Lugar de nacimiento` |
| `Family` | `Familia` |
| `Parents:` | `Padres:` |
| `Siblings:` | `Hermanos:` |
| `(not on record yet)` | `(aún sin registrar)` |
| `(none on record yet)` | `(ninguno aún registrado)` |
| `(on file, name not yet captured)` | `(en archivo, nombre aún no capturado)` |
| `Notes from our conversation` | `Notas de nuestra conversación` |
| `From our records` | `De nuestros registros` |
| `What you've shared so far` | `Lo que has compartido hasta ahora` |
| `What I'm less sure about` | `Lo que aún no tengo claro` |
| `Some parts are still blank...` | `Algunas partes aún están en blanco, y eso está completamente bien. Puedes corregir o agregar una cosa a la vez, cuando quieras.` |
| `Anything you mention now I'll keep as a working draft until you confirm it...` | `Lo que mencione ahora lo mantendré como borrador hasta que lo confirmes. Los datos confirmados vienen de tu perfil.` |
| `(Based on: {sources}.)` | `(Basado en: {sources}.)` |
| `(I don't have anything on record for you yet — would you like to start with your name?)` | `(Aún no tengo nada registrado para ti — ¿te gustaría empezar con tu nombre?)` |
| `You can correct anything that is wrong, missing, or too vague. One correction at a time works best.` | `Puedes corregir cualquier cosa que esté equivocada, faltando, o sea demasiado vaga. Una corrección a la vez funciona mejor.` |
| `Childhood home`, `Parents' work`, `Heritage`, `Education`, `Military service`, `Career`, `Partner`, `Children`, `Life stage` | (seed labels, also need Spanish) |

Sources footer translation map: `profile → perfil`, `interview projection → proyección de entrevista`, `session notes → notas de sesión`, `promoted truth → datos confirmados`, `session transcript → transcripción de sesión`.

## Acceptance criteria

- [ ] Spanish narrator's "qué sabes de mí" turn produces fully Spanish memory_echo (no code-switching)
- [ ] English narrator's "what do you know about me" turn unchanged byte-stable
- [ ] Test pack `tests/test_compose_memory_echo_spanish.py` covers branch detection + literal-string Spanish equivalents
- [ ] Live verified on a Spanish narrator session
- [ ] Operator console output (api.log) carries `[memory-echo][lang=es]` log marker on Spanish path

## Risk

LOW for Option A — additive parameter with English default preserves existing behavior. Spanish branch only activates when explicitly threaded.

## Sequencing note

Sequence behind:
- Live verification of Phase 5A-F (the perspective + fragment + name + phantom + correction-ack work landed today)
- Live verification of BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02 (also tonight)

Once those are confirmed in a real Spanish session, this composer-pack work has real evidence to anchor the Spanish translations against.

## Rollback

Remove the `target_language` parameter; revert to English-only. No behavior change for English narrators.
