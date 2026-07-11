"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 2 — public lookup provider.

Performs a PUBLIC lookup (a URL the operator pasted, or a public query)
and returns a concise draft summary to be stored as draft public_context.
Pure provider layer: no DB writes here, and it receives ONLY the public
query/URL the endpoint decided is safe to send (privacy filtering lives
at the endpoint).

Providers (HORNELORE_PUBLIC_LOOKUP_PROVIDER): off | url_only | searxng |
brave | command
  * url_only — fetch the exact URL the operator supplied; extract title +
               a short visible-text snippet (safest MVP).
  * command  — HORNELORE_PUBLIC_LOOKUP_CMD receives the query and returns
               JSON {"summary","source_url","title"}.
  * searxng / brave — reserved for Phase 3 (return ok=False here).

Master gate HORNELORE_PUBLIC_LOOKUP must be truthy. No network unless
explicitly enabled; never fabricates a result.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Any, Dict, Optional

_TRUTHY = {"1", "true", "yes", "on"}
_FETCH_TIMEOUT_SEC = 20
_MAX_BYTES = 500_000
_SUMMARY_CHARS = 500

_TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAG_RX = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RX = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)


def lookup_enabled() -> bool:
    return os.getenv("HORNELORE_PUBLIC_LOOKUP", "0").strip().lower() in _TRUTHY


def lookup_provider() -> str:
    return (os.getenv("HORNELORE_PUBLIC_LOOKUP_PROVIDER", "off")
            or "off").strip().lower()


def _result(ok: bool, provider: str, summary: str = "", title: str = "",
            source_url: str = "", error: str = "") -> Dict[str, Any]:
    return {"ok": ok, "provider": provider, "summary": summary,
            "title": title or None, "source_url": source_url or None,
            "error": error or None}


def _visible_text(html: str) -> str:
    html = _SCRIPT_STYLE_RX.sub(" ", html)
    text = _TAG_RX.sub(" ", html)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    return " ".join(text.split())


def _fetch_url(url: str):
    """Return (html, final_url). Prefers httpx, falls back to stdlib
    urllib so lookup works before httpx is installed. Raises on error."""
    headers = {"User-Agent": "Hornelore-TravelDoc/1.0"}
    try:
        import httpx  # type: ignore
        r = httpx.get(url, timeout=_FETCH_TIMEOUT_SEC, follow_redirects=True,
                      headers=headers)
        return r.text[: _MAX_BYTES * 2], str(r.url)
    except ImportError:
        pass
    from urllib.request import Request, urlopen
    with urlopen(Request(url, headers=headers),
                 timeout=_FETCH_TIMEOUT_SEC) as resp:
        raw = resp.read(_MAX_BYTES)
        return raw.decode("utf-8", errors="replace"), (resp.geturl() or url)


def _parse_html(html: str):
    """Return (title, main_text). Prefers readability-lxml + BeautifulSoup
    for clean main-article text; falls back to the title-regex /
    visible-text path when those libs are absent."""
    try:
        from bs4 import BeautifulSoup  # type: ignore
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
        title = ""
        if soup.title and soup.title.string:
            title = " ".join(soup.title.string.split())
        text = ""
        try:
            from readability import Document  # type: ignore
            text = _visible_text(Document(html).summary())
        except Exception:
            text = ""
        if not text:
            for t in soup(["script", "style"]):
                t.decompose()
            text = " ".join(soup.get_text(" ").split())
        return title, text
    except ImportError:
        m = _TITLE_RX.search(html)
        title = " ".join(m.group(1).split()) if m else ""
        return title, _visible_text(html)


def _run_url_only(url: str) -> Dict[str, Any]:
    if not url:
        return _result(False, "url_only", error="no url provided")
    if not re.match(r"^https?://", url, re.I):
        return _result(False, "url_only", error="url must be http(s)")
    try:
        html, final_url = _fetch_url(url)
    except Exception as exc:
        return _result(False, "url_only", error="fetch failed: %s" % exc)
    title, text = _parse_html(html)
    snippet = (text or "")[:_SUMMARY_CHARS].rstrip()
    if not title and not snippet:
        return _result(False, "url_only", error="no readable content")
    summary = (title + " — " + snippet).strip(" —") if title else snippet
    return _result(True, "url_only", summary=summary[:_SUMMARY_CHARS],
                   title=title, source_url=final_url)


def _run_command(query: str, url: Optional[str]) -> Dict[str, Any]:
    cmd = (os.getenv("HORNELORE_PUBLIC_LOOKUP_CMD", "") or "").strip()
    if not cmd:
        return _result(False, "command",
                       error="HORNELORE_PUBLIC_LOOKUP_CMD not set")
    arg = url or query or ""
    try:
        proc = subprocess.run(
            shlex.split(cmd) + [arg],
            capture_output=True, text=True, timeout=_FETCH_TIMEOUT_SEC,
        )
    except Exception as exc:
        return _result(False, "command", error="command failed: %s" % exc)
    if proc.returncode != 0:
        return _result(False, "command",
                       error="command exit %d" % proc.returncode)
    try:
        data = json.loads(proc.stdout or "{}")
    except Exception as exc:
        return _result(False, "command", error="bad JSON: %s" % exc)
    summary = (data.get("summary") or "").strip()
    if not summary:
        return _result(False, "command", error="no summary")
    return _result(True, "command", summary=summary[:_SUMMARY_CHARS],
                   title=(data.get("title") or "").strip(),
                   source_url=(data.get("source_url") or url or "").strip())


def run_lookup(query: Optional[str] = None,
               url: Optional[str] = None) -> Dict[str, Any]:
    """Run the configured public-lookup provider. ok=False when
    off/unconfigured/unavailable — the caller must NOT store a row on
    ok=False (no faked lookups)."""
    if not lookup_enabled():
        return _result(False, "off", error="HORNELORE_PUBLIC_LOOKUP is off")
    prov = lookup_provider()
    # A pasted URL always uses the direct fetch path (safest — the
    # operator supplied the exact source), regardless of provider.
    if url:
        return _run_url_only(url)
    if prov == "url_only":
        return _result(False, "url_only",
                       error="url_only provider requires a url")
    if prov == "command":
        return _run_command(query or "", url)
    if prov in ("searxng", "brave"):
        return _result(False, prov,
                       error="%s provider is reserved for Phase 3" % prov)
    return _result(False, prov or "off", error="no lookup provider configured")


__all__ = ["run_lookup", "lookup_enabled", "lookup_provider"]
