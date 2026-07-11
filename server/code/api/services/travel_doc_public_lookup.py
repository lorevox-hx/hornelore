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

import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
from urllib.parse import urlparse
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


_MAX_REDIRECTS = 5


def _host_is_safe(host: str) -> bool:
    """True only when EVERY IP the host resolves to is a PUBLIC address.
    Blocks localhost/loopback, private LAN (10/172.16-31/192.168),
    link-local incl. the 169.254.169.254 cloud-metadata address,
    reserved, multicast, and unspecified (0.0.0.0). This is the SSRF
    guard — a 'fetch this URL' feature must only reach the public web."""
    if not host or host.strip().lower() == "localhost":
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = str(info[4][0]).split("%")[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast
                or addr.is_unspecified):
            return False
    return True


def _check_url_safe(url: str):
    """(ok, reason). Only public http/https URLs pass."""
    try:
        p = urlparse(url)
    except Exception:
        return False, "unparseable url"
    if (p.scheme or "").lower() not in ("http", "https"):
        return False, "only http/https URLs are allowed"
    if not _host_is_safe(p.hostname or ""):
        return False, "URL host is not a public address"
    return True, ""


def _fetch_once(url: str, headers):
    """One hop. Returns (html, final_url) on a real response, or a string
    (the next URL) on a redirect. NEVER auto-follows redirects and caps
    the download at _MAX_BYTES so a hop can't be re-pointed at, or flood
    from, a blocked address."""
    try:
        import httpx  # type: ignore
        with httpx.stream("GET", url, timeout=_FETCH_TIMEOUT_SEC,
                          follow_redirects=False, headers=headers) as r:
            if r.is_redirect and r.headers.get("location"):
                return str(httpx.URL(url).join(r.headers["location"]))
            chunks, total = [], 0
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total > _MAX_BYTES:
                    break
            return (b"".join(chunks).decode("utf-8", errors="replace"),
                    str(r.url))
    except ImportError:
        pass
    import urllib.error
    from urllib.parse import urljoin
    from urllib.request import Request, build_opener, HTTPRedirectHandler

    class _NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(Request(url, headers=headers),
                         timeout=_FETCH_TIMEOUT_SEC) as resp:
            raw = resp.read(_MAX_BYTES)
            return raw.decode("utf-8", errors="replace"), (resp.geturl() or url)
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            loc = exc.headers.get("Location")
            if loc:
                return urljoin(url, loc)
        raise


def _fetch_url(url: str):
    """Return (html, final_url). SSRF-guarded: every hop (including each
    redirect target) must pass _check_url_safe; blocked hosts, non-http
    schemes, oversized bodies, and redirect loops all raise ValueError so
    the caller stores no row."""
    headers = {"User-Agent": "Hornelore-TravelDoc/1.0"}
    cur = url
    for _ in range(_MAX_REDIRECTS + 1):
        ok, reason = _check_url_safe(cur)
        if not ok:
            raise ValueError(reason)
        nxt = _fetch_once(cur, headers)
        if isinstance(nxt, tuple):
            return nxt
        cur = nxt   # redirect target — re-checked at the top of the loop
    raise ValueError("too many redirects")


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
