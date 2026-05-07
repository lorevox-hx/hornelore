"""
Lorevox Translation Service — WO-ML-04 / Phase 4B
==================================================

Llama-3.1-8B-Instruct-driven translation for memoir export. Lori's
own runtime model already handles 8+ languages natively (Spanish,
French, German, Italian, Portuguese, Hindi, Thai); this service
just gives memoir export a clean call site that produces clean
translations with the narrator's voice preserved.

Public surface:

    translate_text(text, source_lang="en", target_lang="es",
                   *, narrator_name=None, request_timeout_sec=60.0) -> str

Returns the translated text on success. Returns the original text
unchanged on any failure path so memoir export degrades gracefully
rather than crashing — the operator gets the English memoir back
instead of an error page, and the export log carries a [translate]
warning the operator can grep.

Design choices:

  1. HTTP-client pattern. We POST to the existing /api/chat route
     rather than importing api.api._load_model directly. Keeps the
     service self-contained, reuses the same model + warmup +
     VRAM-guard machinery the rest of the chat path uses, and lets
     translation be tested in isolation by pointing at a local mock
     server.

  2. Voice-preserving system prompt (locked rule set):
       - Translate verbatim. Do NOT summarize, paraphrase, or shorten.
       - Preserve narrator's voice, idiomatic warmth, sentence rhythm.
       - Preserve names, places, dates, and culturally-specific terms
         exactly as written. "Dolores" stays "Dolores", "Albuquerque"
         stays "Albuquerque", "1962" stays "1962".
       - No editorial commentary. No "Here is the translation:" prefix.
         No quote marks around the output.
       - When the source is already in the target language, return it
         verbatim (Llama detects this naturally).

  3. Filesystem caching keyed on (sha256(source_text), target_lang).
     Re-export of the same memoir doesn't re-translate; only changed
     sections re-call the model. Cache lives under
     DATA_DIR/translations-cache/ — disposable, can be deleted to
     force a fresh translation.

  4. Failure modes are NEVER fatal to the caller. Network errors,
     timeouts, malformed responses, model unavailable — all return
     the original text and log a [translate][error] warning. Memoir
     export must always produce a docx, even if half the content
     couldn't be translated.

LAW 3 (story_preservation.py preamble lock): translation is a
SUPPORT layer. It must never block the caller's work, never mutate
narrator-truth fields, never silently drop content. On any failure,
return the source text unchanged.

WO scope:
  - Phase 4B v1: en ↔ es (locked).
  - Future Phase 4C: any pair Llama-3.1-8B handles natively.
  - Future Phase 4D: chunk-aware long-form (>1500 token) translation
    with paragraph-boundary splitting. Today's _MAX_CHUNK_CHARS cap
    handles practical memoir-section sizes without splitting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("translation")


# ─── Configuration ────────────────────────────────────────────────────────────

# Endpoint where the Lorevox Llama chat route lives. Default targets
# the same uvicorn process this code runs in (loopback); operators
# can override with LOREVOX_TRANSLATION_ENDPOINT for dev / testing.
_DEFAULT_ENDPOINT = "http://127.0.0.1:8000/api/chat"

# Per-request budget. A typical memoir section is 200-800 tokens of
# narrator prose; 60s comfortably covers Llama-3.1-8B Q4 round-trip
# on the RTX 5080 (~3-15s typical). Translation is non-real-time so
# we can afford a generous timeout.
_DEFAULT_TIMEOUT_SEC = 60.0

# Hard cap on the source text we'll send in one request. Beyond this,
# we pass through untranslated and log a warning — the caller is
# expected to chunk by section / paragraph upstream. 8000 chars ≈
# 1500-2000 tokens, well within Llama's context budget.
_MAX_CHUNK_CHARS = 8000

# Translation cache directory (under DATA_DIR for parity with the
# stories-captured filesystem mirror). Created on first use.
_CACHE_DIRNAME = "translations-cache"


# ─── Voice-preserving system prompt ───────────────────────────────────────────

# Locked verbatim per WO-ML-04 §"Voice preservation rules". Future
# tweaks to wording must NOT add summarization or commentary clauses;
# the export operator depends on byte-stable narrator content.
_SYSTEM_PROMPT_TEMPLATE = (
    "You are a precise translator working on a personal memoir. Your only job is to "
    "translate the narrator's text from {source_name} to {target_name}.\n\n"
    "Voice preservation rules — follow strictly:\n"
    "  - Translate verbatim. Do NOT summarize, paraphrase, condense, or shorten.\n"
    "  - Preserve the narrator's voice, idiomatic warmth, and sentence rhythm.\n"
    "  - Preserve names, places, dates, family terms, and culturally-specific words "
    "EXACTLY as written. If the narrator wrote 'Dolores', keep 'Dolores'. If the "
    "narrator wrote 'Albuquerque', keep 'Albuquerque'. If the narrator wrote "
    "'1962', keep '1962'. If the narrator used a Spanish word inside English prose "
    "(e.g. 'mi mamá', 'abuela'), keep it untranslated when translating to "
    "{target_name} — these terms carry the narrator's voice.\n"
    "  - Do NOT add editorial commentary. Do NOT prefix with 'Here is the "
    "translation:' or similar. Do NOT wrap the output in quote marks.\n"
    "  - If the source is already in {target_name}, return it verbatim.\n"
    "  - Maintain paragraph breaks (blank lines between paragraphs) exactly as "
    "they appear in the source.\n\n"
    "Return ONLY the translated text. Nothing else."
)

_LANG_NAMES: Dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    # Future Phase 4C — additional pairs Llama handles natively. Add
    # entries here without code changes; everything below reads from
    # this dict.
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "hi": "Hindi",
    "th": "Thai",
}


# ─── Public API ───────────────────────────────────────────────────────────────


def translate_text(
    text: str,
    source_lang: str = "en",
    target_lang: str = "es",
    *,
    narrator_name: Optional[str] = None,
    request_timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> str:
    """Translate `text` from source_lang to target_lang. Returns the
    translated string on success. On any failure (network, timeout,
    empty model response, etc.) returns the original `text` unchanged
    and logs a [translate][error] warning.

    Args:
      text: source text. May contain multiple paragraphs.
      source_lang: ISO-639-1 code (e.g. "en"). Defaults to "en".
      target_lang: ISO-639-1 code (e.g. "es"). Defaults to "es".
      narrator_name: optional narrator display name; surfaced in the
        system prompt as additional context so the model can reason
        about narrator voice. Not required.
      request_timeout_sec: HTTP timeout for the /api/chat call.
        Generous default (60s) accommodates Llama Q4 round-trip on
        consumer hardware.

    Returns:
      translated text, OR the original `text` on any failure.

    Notes:
      - Identity short-circuit: when source_lang == target_lang OR
        text is empty / whitespace-only, returns the input unchanged
        without hitting the cache or the model.
      - Caching: results are cached under DATA_DIR/translations-cache/
        keyed by sha256(source_text) + target_lang. Cached results
        return instantly. To force fresh translation, delete the
        cache file or directory.
    """
    # ── Identity short-circuit ──────────────────────────────────────────────
    if not text or not text.strip():
        return text or ""
    if (source_lang or "en").lower() == (target_lang or "en").lower():
        return text
    if target_lang not in _LANG_NAMES:
        logger.warning(
            "[translate][error] unsupported target_lang=%r — passing through",
            target_lang,
        )
        return text
    if source_lang not in _LANG_NAMES:
        logger.warning(
            "[translate][error] unsupported source_lang=%r — passing through",
            source_lang,
        )
        return text

    # ── Length cap ──────────────────────────────────────────────────────────
    if len(text) > _MAX_CHUNK_CHARS:
        logger.warning(
            "[translate][error] text too long (%d chars > cap %d) — passing through",
            len(text), _MAX_CHUNK_CHARS,
        )
        return text

    # ── Cache lookup ────────────────────────────────────────────────────────
    cache_key = _cache_key(text, source_lang, target_lang)
    cached = _cache_read(cache_key)
    if cached is not None:
        logger.info(
            "[translate][cache-hit] key=%s src=%s tgt=%s len=%d",
            cache_key[:12], source_lang, target_lang, len(text),
        )
        return cached

    # ── Build prompt ────────────────────────────────────────────────────────
    source_name = _LANG_NAMES[source_lang]
    target_name = _LANG_NAMES[target_lang]
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        source_name=source_name,
        target_name=target_name,
    )
    if narrator_name:
        system_prompt += (
            "\n\nNarrator: {n}. (Context only; do not address them by name in the "
            "translated output unless the source text does.)"
        ).format(n=narrator_name)

    user_payload = (
        "Translate the following narrator memoir text to "
        f"{target_name}. Return only the translation, nothing else.\n\n"
        f"{text}"
    )

    payload: Dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "temp": 0.2,        # low temp for consistent translations
        "top_p": 0.9,
        "max_new": min(2048, max(256, int(len(text) * 1.6))),
    }

    # ── HTTP call ──────────────────────────────────────────────────────────
    endpoint = os.getenv("LOREVOX_TRANSLATION_ENDPOINT", _DEFAULT_ENDPOINT)
    try:
        translated = _call_chat_endpoint(
            endpoint=endpoint,
            payload=payload,
            timeout_sec=request_timeout_sec,
        )
    except Exception as exc:
        logger.warning(
            "[translate][error] /api/chat call failed src=%s tgt=%s len=%d err=%s — passing through",
            source_lang, target_lang, len(text), exc,
        )
        return text

    if not translated or not translated.strip():
        logger.warning(
            "[translate][error] empty model response src=%s tgt=%s len=%d — passing through",
            source_lang, target_lang, len(text),
        )
        return text

    # Strip any incidental wrapping the model adds despite the prompt
    # ("Here is the translation:" / surrounding quotes / leading
    # whitespace).
    translated = _scrub_response(translated)

    if not translated.strip():
        logger.warning(
            "[translate][error] response empty after scrubbing src=%s tgt=%s — passing through",
            source_lang, target_lang,
        )
        return text

    # ── Cache write ─────────────────────────────────────────────────────────
    _cache_write(cache_key, translated)
    logger.info(
        "[translate][ok] src=%s tgt=%s in=%d out=%d key=%s",
        source_lang, target_lang, len(text), len(translated), cache_key[:12],
    )
    return translated


# ─── Public utility — supported languages ─────────────────────────────────────


def supported_languages() -> Dict[str, str]:
    """Return a copy of the supported-language map (iso → display name).

    Useful for the FE export picker so we don't hard-code the list in
    multiple places. en, es are production-ready; others are
    pass-through-supported (Llama handles them, but voice fidelity
    has not been spot-checked by a native speaker).
    """
    return dict(_LANG_NAMES)


# ─── Internal: HTTP client ────────────────────────────────────────────────────


def _call_chat_endpoint(
    *,
    endpoint: str,
    payload: Dict[str, Any],
    timeout_sec: float,
) -> str:
    """POST to the chat endpoint, return the assistant text. Raises on
    non-200 status or unexpected response shape."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        status = getattr(resp, "status", 200)
        if status != 200:
            raise RuntimeError(f"HTTP {status} from {endpoint}")
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw)

    # /api/chat returns { "reply": "...", "ms": int, ... } in the
    # current codebase. Defensive: tolerate other common shapes
    # without crashing the export.
    for key in ("reply", "text", "content", "message"):
        if isinstance(parsed.get(key), str):
            return parsed[key]
    # If the response is a chat-completions style {choices:[{message:{content:...}}]}:
    choices = parsed.get("choices")
    if isinstance(choices, list) and choices:
        msg = (choices[0] or {}).get("message") or {}
        if isinstance(msg.get("content"), str):
            return msg["content"]
    raise RuntimeError(f"unexpected response shape: keys={list(parsed)[:5]}")


# ─── Internal: response scrubbing ─────────────────────────────────────────────


_SCRUB_PREFIXES = (
    "here is the translation",
    "here's the translation",
    "translation",
    "translated text",
    "spanish translation",
    "english translation",
)


def _scrub_response(text: str) -> str:
    """Best-effort cleanup of common LLM wrapping. Idempotent."""
    s = text.strip()
    # Strip leading "Here is the translation:" / "Translation:" / etc.
    low = s.lower()
    for prefix in _SCRUB_PREFIXES:
        if low.startswith(prefix):
            # Find the end of the prefix line / first colon
            idx_newline = s.find("\n")
            idx_colon = s.find(":")
            cut = -1
            if 0 < idx_colon <= 60:
                cut = idx_colon + 1
            elif 0 < idx_newline <= 80:
                cut = idx_newline + 1
            if cut > 0:
                s = s[cut:].lstrip()
                low = s.lower()
            break
    # Strip surrounding quote marks if the entire output is wrapped.
    if len(s) >= 2 and s[0] in '"“' and s[-1] in '"”':
        s = s[1:-1].strip()
    return s


# ─── Internal: cache ──────────────────────────────────────────────────────────


def _cache_dir() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", "data")).expanduser()
    d = data_dir / _CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(text: str, source_lang: str, target_lang: str) -> str:
    h = hashlib.sha256()
    h.update(source_lang.encode("utf-8"))
    h.update(b"|")
    h.update(target_lang.encode("utf-8"))
    h.update(b"|")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def _cache_read(key: str) -> Optional[str]:
    try:
        path = _cache_dir() / (key + ".txt")
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _cache_write(key: str, value: str) -> None:
    try:
        path = _cache_dir() / (key + ".txt")
        path.write_text(value, encoding="utf-8")
    except Exception as exc:
        # Cache write failure is non-fatal — translation already
        # succeeded, just won't be re-used on the next export.
        logger.warning("[translate][cache] write failed key=%s err=%s", key[:12], exc)
