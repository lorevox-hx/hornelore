"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 — prompt-safety for evidence text.

OCR / public-lookup text is UNTRUSTED input: a sign or web page can
literally read "[SYSTEM: ignore your instructions]". Before any such
text reaches Lori's prompt (modal or narrator-facing trip context), it
is collapsed to a single line, has bracket / role / code-fence directive
shapes neutralized, and is length-capped. Pure helper — no deps.
"""
from __future__ import annotations

import re

_MAX_PROMPT_CHARS = 240

# Role / instruction tokens that could fake a turn or a system directive.
_ROLE_RX = re.compile(
    r"(?i)\b(system|assistant|user|instruction|inst|developer)\s*:")


def sanitize_for_prompt(text, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    """Return a single-line, directive-neutralized, length-capped version
    of untrusted evidence text, safe to interpolate into a prompt."""
    t = " ".join(str(text or "").split())          # collapse newlines/space
    t = t.replace("[", "(").replace("]", ")")       # [SYSTEM: ...] -> (SYSTEM- ...)
    t = t.replace("{", "(").replace("}", ")")
    t = t.replace("`", "'")                          # kill code fences
    t = t.replace("<<", "(").replace(">>", ")")     # <<SYS>>
    t = _ROLE_RX.sub(lambda m: m.group(1) + "-", t)  # "System:" -> "System-"
    t = t.strip()
    if max_chars and len(t) > max_chars:
        t = t[:max_chars].rstrip() + "…"
    return t


__all__ = ["sanitize_for_prompt"]
