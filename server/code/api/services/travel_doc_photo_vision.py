"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 — image-context (vision) provider.

Optional short image-context description for a LOCAL photo. Command-only
in this phase (a local VLM or operator script); NO cloud model by
default. Pure provider layer — no DB, no network here.

Providers (HORNELORE_VISION_PROVIDER): off | command
Master gate HORNELORE_PHOTO_VISION must be truthy. Never fabricates a
description when no provider is configured.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any, Dict

_TRUTHY = {"1", "true", "yes", "on"}
_VISION_TIMEOUT_SEC = 120
_SUMMARY_CHARS = 300


def vision_enabled() -> bool:
    return os.getenv("HORNELORE_PHOTO_VISION", "0").strip().lower() in _TRUTHY


def vision_provider() -> str:
    return (os.getenv("HORNELORE_VISION_PROVIDER", "off")
            or "off").strip().lower()


def _result(ok: bool, engine: str, raw_text: str = "", summary: str = "",
            model: str = "", error: str = "") -> Dict[str, Any]:
    return {"ok": ok, "engine": engine, "raw_text": raw_text,
            "summary": summary, "model": model or None, "error": error or None}


def _run_command(image_path: str) -> Dict[str, Any]:
    cmd = (os.getenv("HORNELORE_VISION_CMD", "") or "").strip()
    if not cmd:
        return _result(False, "command", error="HORNELORE_VISION_CMD not set")
    try:
        proc = subprocess.run(
            shlex.split(cmd) + [image_path],
            capture_output=True, text=True, timeout=_VISION_TIMEOUT_SEC,
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
        return _result(False, "command",
                       error="bad JSON from command: %s" % exc)
    summary = (data.get("summary") or data.get("description") or "").strip()
    if not summary:
        return _result(False, "command", error="no_description")
    if len(summary) > _SUMMARY_CHARS:
        summary = summary[:_SUMMARY_CHARS].rstrip() + "…"
    return _result(True, "command", raw_text=(data.get("raw") or "").strip(),
                   summary=summary, model=(data.get("model") or "").strip())


def run_vision(image_path: str) -> Dict[str, Any]:
    """Run the configured vision provider on a LOCAL image path. ok=False
    when off/unconfigured/unavailable — the caller must NOT write a row on
    ok=False (no faked scene descriptions)."""
    if not vision_enabled():
        return _result(False, "off", error="HORNELORE_PHOTO_VISION is off")
    if not image_path or not os.path.exists(image_path):
        return _result(False, vision_provider(), error="image file not found")
    prov = vision_provider()
    if prov == "command":
        return _run_command(image_path)
    return _result(False, prov or "off", error="no vision provider configured")


__all__ = ["run_vision", "vision_enabled", "vision_provider"]
