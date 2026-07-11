"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1 — OCR provider interface.

Reads visible text from a LOCAL photo file (signs, menus, tickets,
museum labels) and returns a draft result. Pure provider layer: no DB,
no router imports, no network. The image path is handed only to a LOCAL
provider; nothing leaves the machine here.

Providers (HORNELORE_OCR_PROVIDER): off | tesseract | command
  * off       — feature not configured; returns ok=False (no fake text).
  * tesseract — local pytesseract (lazy import; if unavailable -> ok=False).
  * command   — HORNELORE_OCR_CMD receives the image path and returns
                JSON {"text": "...", "summary": "..."} on stdout.

Master gate HORNELORE_PHOTO_OCR must be truthy for the feature to run.
Nothing here fabricates results when a provider is missing.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any, Dict

_TRUTHY = {"1", "true", "yes", "on"}
_OCR_TIMEOUT_SEC = 60
_SUMMARY_CHARS = 240


def ocr_enabled() -> bool:
    return os.getenv("HORNELORE_PHOTO_OCR", "0").strip().lower() in _TRUTHY


def ocr_provider() -> str:
    return (os.getenv("HORNELORE_OCR_PROVIDER", "off") or "off").strip().lower()


def _summarize(text: str) -> str:
    """A concise, single-line readable excerpt of the OCR text."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= _SUMMARY_CHARS:
        return collapsed
    return collapsed[:_SUMMARY_CHARS].rstrip() + "…"


def _result(ok: bool, engine: str, raw_text: str = "", summary: str = "",
            error: str = "") -> Dict[str, Any]:
    return {"ok": ok, "engine": engine, "raw_text": raw_text,
            "summary": summary, "error": error or None}


def _run_tesseract(image_path: str) -> Dict[str, Any]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - env dependent
        return _result(False, "tesseract",
                       error="tesseract/pillow not installed: %s" % exc)
    try:
        text = pytesseract.image_to_string(Image.open(image_path))
    except Exception as exc:
        return _result(False, "tesseract", error="ocr failed: %s" % exc)
    text = (text or "").strip()
    if not text:
        return _result(False, "tesseract", error="no_text_found")
    return _result(True, "tesseract", raw_text=text, summary=_summarize(text))


def _run_command(image_path: str) -> Dict[str, Any]:
    cmd = (os.getenv("HORNELORE_OCR_CMD", "") or "").strip()
    if not cmd:
        return _result(False, "command", error="HORNELORE_OCR_CMD not set")
    try:
        proc = subprocess.run(
            shlex.split(cmd) + [image_path],
            capture_output=True, text=True, timeout=_OCR_TIMEOUT_SEC,
        )
    except Exception as exc:
        return _result(False, "command", error="command failed: %s" % exc)
    if proc.returncode != 0:
        return _result(False, "command",
                       error="command exit %d: %s"
                       % (proc.returncode, (proc.stderr or "")[:200]))
    try:
        data = json.loads(proc.stdout or "{}")
    except Exception as exc:
        return _result(False, "command", error="bad JSON from command: %s" % exc)
    text = (data.get("text") or "").strip()
    summary = (data.get("summary") or "").strip() or _summarize(text)
    if not text and not summary:
        return _result(False, "command", error="no_text_found")
    return _result(True, "command", raw_text=text, summary=summary)


def run_ocr(image_path: str) -> Dict[str, Any]:
    """Run the configured OCR provider on a LOCAL image path.

    Returns {ok, engine, raw_text, summary, error}. ok=False whenever the
    feature is off, no provider is configured, the provider is unavailable,
    or no text was found — the caller must NOT write a row on ok=False."""
    if not ocr_enabled():
        return _result(False, "off", error="HORNELORE_PHOTO_OCR is off")
    if not image_path or not os.path.exists(image_path):
        return _result(False, ocr_provider(), error="image file not found")
    prov = ocr_provider()
    if prov == "tesseract":
        return _run_tesseract(image_path)
    if prov == "command":
        return _run_command(image_path)
    return _result(False, prov or "off", error="no OCR provider configured")


__all__ = ["run_ocr", "ocr_enabled", "ocr_provider"]
