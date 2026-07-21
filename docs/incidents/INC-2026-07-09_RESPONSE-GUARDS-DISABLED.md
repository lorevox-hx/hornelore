# INC-2026-07-09 — Response guards disabled in production (CLOSED)

**Severity:** Critical (narrator-facing)
**Outage window:** 2026-07-09 22:16 → 2026-07-14 restart (~5 days)
**Status:** CLOSED 2026-07-14

## What was broken

Every narrator-facing response guard was silently dead in production, on every
turn: `narrator_echo`, `meta_response_leak`, `dangling_determiner`,
`language_drift`, the "I can see" block — all of them.

Not degraded. Absent.

## Root cause

`_META_REASONING_RX` in `lori_response_guards.py` was written with a SECOND
inline `(?i)` before its alternation:

```python
re.compile(r"(?i)i(?:'ll| will) ... |(?i)since there(?:'s| is) no prior conversation")
```

An inline global flag past position 0 is a **DeprecationWarning on Python 3.10**
and a **hard `re.error` on Python 3.11+**:

```
re.error: global flags not at the start of the expression at position 99
```

The server runs **3.12**, so this module-level `re.compile` raised **at import**.

`chat_ws` imported the guards *inside* the per-turn `try/except` whose stated
purpose is "never break a turn on guard failure". That is correct for a
transient runtime error and catastrophic for an ImportError: it caught the
failure, logged one WARNING, and passed every reply through **unguarded**.

```
[chat_ws][response-guards] wrapper raised, passing through:
global flags not at the start of the expression at position 99
```

## Why nobody noticed

1. **The dev sandbox is Python 3.10.** Every unit test passed — on 3.10 the
   pattern merely warns. The suite was green while production had no guards.
2. **The failure was a WARNING, not an error.** It scrolled past 23 times.
3. **The symptom looked like model quality, not a broken import.** Lori parroting
   the narrator was easy to read as "the LLM is being repetitive today".

## How it surfaced

Live session, 2026-07-14. Lori repeated the narrator's own sentence back **in the
first person**:

> narrator: "My father built the back porch himself."
> Lori: "**My father built the back porch himself.** That's a specific memory."

The echo guard was working perfectly. It was simply never being called.

## Timeline (from api.log)

| When | What |
|---|---|
| 2026-07-09 16:13 | last successful guard fire (`fired=meta_response_leak`) |
| 2026-07-09 evening | Build 1.5 leak-hardening batch **adds** `_META_REASONING_RX` |
| 2026-07-09 22:16 | first `wrapper raised` — guards dead from here |
| 2026-07-14 | live parrot observed → root-caused → fixed |
| 2026-07-14 | restart: 23 crashes before, **0** after |

The regex written to catch Lori's meta-leaks is what killed every guard —
including the meta-leak guard it belonged to.

## Fix

1. **Flag moved into the compile call** — `re.compile(..., re.IGNORECASE)`, where
   a Python version bump cannot move it.
2. **Guards imported at module scope in `chat_ws`** — a guards module that cannot
   load now **fails the boot**. A stack that refuses to start is strictly better
   than a stack that quietly talks to an 86-year-old with every protection off.
3. **Build gate** (`tests/test_regex_inline_flags_py311.py`) — imports every
   module under 3.11+ regex strictness *regardless of the running interpreter*,
   so a 3.10 dev box cannot hide this again. Sweep runs in a clean subprocess
   (it must not itself mutate `sys.modules`); detector matches flag **groups**
   (`(?im)`, `(?is)`, `(?msx)`), while allowing scoped `(?i:...)`.

Verified by injection: the original `(?i)…|(?i)` goes RED, a combined `|(?im)`
goes RED, the fix goes GREEN. Zero other offenders across `server/code/api`.

## Standing lessons

- **A defensive `except` around an import is a silencer, not a safety net.**
  Runtime failure → degrade. *Structural* failure (can't even load) → fail loud.
  The two must not share a handler.
- **Test-environment parity is a safety property, not a chore.** A 3.10 sandbox
  testing a 3.12 server means an entire class of bug is invisible to CI.
- **Guards need liveness evidence, not just unit tests.** A guard that is never
  called passes every test it has. Worth considering a periodic assertion that
  the guard pipeline has fired at least once in a session.
