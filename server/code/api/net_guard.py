"""Shared network-exposure guard (2026-08-12 security review).

One place answers two questions for every HTTP/WS entrypoint:

  1. Which browser origins may talk to this stack?  (CORS + WebSocket)
  2. What is the default bind address?              (loopback, not LAN)

Why this exists: the review found the API bound to 0.0.0.0 with
``allow_origins=["*"]`` and an unauthenticated websocket that accepts
destructive commands (``sync_session`` -> ``clear_turns`` on a
client-named conversation).  Websockets are NOT subject to CORS, so the
wildcard plus LAN bind meant any web page on any device on the network
could open ``ws://<host>:8000/api/chat/ws`` and drive the stack.

Policy:

- Default allowlist covers the three local surfaces this stack actually
  serves: the UI server (:8082), the API's own /ui mount (:8000) and the
  TTS service (:8001), on both ``localhost`` and ``127.0.0.1`` spellings.
- Override with a comma-separated ``HORNELORE_ALLOWED_ORIGINS`` env value
  when the stack is deliberately exposed differently.  An entry of ``*``
  restores the old wildcard explicitly (visible in .env, never implicit).
- ``origin_permitted(None)`` is True: non-browser clients (harnesses,
  curl, eval scripts) send no Origin header and must keep working.
- The literal ``"null"`` origin (file:// pages, sandboxed iframes,
  data: URLs) is deliberately NOT allowed by default -- sandboxed
  attacker iframes send exactly that value.  If you open the UI via
  file:// instead of the :8082 server, add ``null`` to the env override.
"""

from __future__ import annotations

import os
from typing import List, Optional

_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8082",
    "http://127.0.0.1:8082",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]


def allowed_origins() -> List[str]:
    """Return the configured browser-origin allowlist."""
    raw = os.getenv("HORNELORE_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_ALLOWED_ORIGINS)


def origin_permitted(origin: Optional[str]) -> bool:
    """True when a request/socket with this Origin header may proceed.

    ``None`` (header absent) is permitted: that is a non-browser client,
    and the threat model here is hostile *web pages*, which always send
    an Origin on cross-origin WS/fetch.
    """
    if origin is None:
        return True
    allowed = allowed_origins()
    if "*" in allowed:
        return True
    return origin in allowed
