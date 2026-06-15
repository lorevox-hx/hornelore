"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase D Defense 3.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The cap-override loader. Raising the anchored-asking caps requires
crossing a visible line: an explicit override file with a required
acknowledgment field. Setting HORNELORE_BIO_ANCHORED_MAX_PER_SESSION
in .env alone does NOT take effect. The friction is the defense.

Per the WO §Defense 3 spec, raising any cap requires:
  1. A separate config file `bio_anchored_overrides.toml` (not .env)
  2. Required field: `i_understand_this_changes_lori_from_oral_history
     _to_questionnaire_mode = true`
  3. Log line on every session start when overrides active
  4. Operator dashboard banner persistent until removed
  5. Operator runbook section documenting the override is non-default
  6. Parent-session readiness gate failure if overrides active during
     any gate verification run (BLOCKED: parent_session_readiness
     module does not exist; this helper exposes a check that any
     future readiness framework can consult)

This module handles items 1-4 + the helper for #6. Items 5 + 6 are
operator-process / cross-WO work tracked in the build report.

═══════════════════════════════════════════════════════════════════════
  CAP VARIABLES + DEFAULTS
═══════════════════════════════════════════════════════════════════════

  HORNELORE_BIO_ANCHORED_MAX_PER_SESSION  (default 3)
  HORNELORE_BIO_ANCHORED_TURN_SPACING     (default 4)
  HORNELORE_BIO_ANCHORED_MOMENTUM_CEILING (default 0.4)
  HORNELORE_BIO_ANCHORED_CHAPTER_HEALTH_FLOOR (default 0.8)

Default values are the production-locked oral-history posture. The
helpers below return defaults unless the override file is present
AND well-formed AND the acknowledgment field is True.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  AnchoredOverrideError — raised when overrides file exists but is
      malformed (parse error, missing/false acknowledgment, type
      errors on cap values). The intent is fail-loud at process
      start: a malformed override is a loaded-gun for the
      oral-history posture and should never silently fall back to
      defaults.

  load_overrides(path=None) → AnchoredOverrides
      Load + validate the override file. Returns a frozen
      AnchoredOverrides with .active=False when no file present
      (caller uses defaults). Raises AnchoredOverrideError on
      malformed file. `path` is for tests; production reads
      BIO_ANCHORED_OVERRIDES_PATH env (default
      "./bio_anchored_overrides.toml").

  get_cap(name, overrides=None) → int | float
      Return the effective cap value: override-file value when
      overrides.active, else the production default. Pass overrides=
      None to load on demand.

  caps_overridden() → bool
      Cheap boolean for the operator dashboard banner check. Reads
      load_overrides() at call time.

  emit_session_start_log() → Optional[str]
      Returns the WARNING log line text when overrides are active,
      or None when defaults are in force. Caller logs at WARNING
      level.

  readiness_gate_blocked() → bool
      Helper for any future parent_session_readiness gate to
      consult. Returns True when overrides are active — that gate
      should refuse to pass.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Defaults (production-locked oral-history posture)
# ─────────────────────────────────────────────────────────────────────


DEFAULT_MAX_PER_SESSION = 3
DEFAULT_TURN_SPACING = 4
DEFAULT_MOMENTUM_CEILING = 0.4
DEFAULT_CHAPTER_HEALTH_FLOOR = 0.8


# Mapping of cap-name → (toml_key, default, type)
_CAP_DEFS: Tuple[Tuple[str, str, Any, type], ...] = (
    ("max_per_session", "max_per_session", DEFAULT_MAX_PER_SESSION, int),
    ("turn_spacing", "turn_spacing", DEFAULT_TURN_SPACING, int),
    ("momentum_ceiling", "momentum_ceiling",
     DEFAULT_MOMENTUM_CEILING, float),
    ("chapter_health_floor", "chapter_health_floor",
     DEFAULT_CHAPTER_HEALTH_FLOOR, float),
)


_ACK_FIELD = (
    "i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode"
)


# ─────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────


class AnchoredOverrideError(RuntimeError):
    """Override file present but malformed. Process-startup error;
    fail-loud so we never silently fall back to defaults when an
    override was intended."""


# ─────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnchoredOverrides:
    """Frozen record of effective caps for a process.

    active=False → caller uses production defaults; the cap fields
    are still populated with the defaults for convenience.
    active=True → cap fields hold the override-file values.
    """
    active: bool
    max_per_session: int
    turn_spacing: int
    momentum_ceiling: float
    chapter_health_floor: float
    source_path: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────


def _resolve_path(path: Optional[str]) -> Path:
    """Resolve the override-file path. `path` arg is for tests."""
    if path:
        return Path(path)
    env_path = os.environ.get("BIO_ANCHORED_OVERRIDES_PATH", "").strip()
    if env_path:
        return Path(env_path)
    return Path("./bio_anchored_overrides.toml")


def _read_toml(path: Path) -> Dict[str, Any]:
    """Read + parse the override TOML. Raises AnchoredOverrideError
    on parse failure. Uses stdlib tomllib when available (Python 3.11+)
    or falls back to a tiny key=value parser for the simple cases we
    support."""
    raw = path.read_text(encoding="utf-8")
    # Prefer tomllib (Python 3.11+); fall back to lightweight parse.
    try:
        import tomllib  # type: ignore
        try:
            return tomllib.loads(raw)
        except Exception as exc:
            raise AnchoredOverrideError(
                f"bio_anchored_overrides.toml parse failed: {exc}",
            ) from exc
    except ImportError:
        pass
    # Lightweight parser — supports `key = value` lines with int / float /
    # bool / quoted-string values + comments + blank lines. Sufficient
    # for the small override format we accept; complete TOML support
    # arrives with the tomllib fallback above on Python 3.11+.
    out: Dict[str, Any] = {}
    for lineno, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AnchoredOverrideError(
                f"bio_anchored_overrides.toml line {lineno}: "
                f"expected key = value, got {raw_line!r}",
            )
        key, _, value_raw = line.partition("=")
        key = key.strip()
        value_raw = value_raw.strip()
        # Strip trailing comments
        if "#" in value_raw and not (
            value_raw.startswith('"') or value_raw.startswith("'")
        ):
            value_raw = value_raw.split("#", 1)[0].strip()
        # Parse value
        if value_raw.lower() == "true":
            out[key] = True
        elif value_raw.lower() == "false":
            out[key] = False
        elif (
            (value_raw.startswith('"') and value_raw.endswith('"'))
            or (value_raw.startswith("'") and value_raw.endswith("'"))
        ):
            out[key] = value_raw[1:-1]
        else:
            try:
                if "." in value_raw or "e" in value_raw.lower():
                    out[key] = float(value_raw)
                else:
                    out[key] = int(value_raw)
            except ValueError as exc:
                raise AnchoredOverrideError(
                    f"bio_anchored_overrides.toml line {lineno}: "
                    f"cannot parse value {value_raw!r}: {exc}",
                ) from exc
    return out


def _coerce(name: str, value: Any, expected: type) -> Any:
    """Type-coerce or raise. Used to validate cap values from the
    override file."""
    if expected is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        raise AnchoredOverrideError(
            f"bio_anchored_overrides.{name}: expected number, "
            f"got {value!r}",
        )
    if expected is int:
        if isinstance(value, bool):
            # bool is a subclass of int in Python — exclude explicitly
            raise AnchoredOverrideError(
                f"bio_anchored_overrides.{name}: expected integer, "
                f"got bool {value!r}",
            )
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise AnchoredOverrideError(
            f"bio_anchored_overrides.{name}: expected integer, "
            f"got {value!r}",
        )
    return value


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def load_overrides(path: Optional[str] = None) -> AnchoredOverrides:
    """Load + validate the override file.

    Returns AnchoredOverrides(active=False, ...) populated with
    production defaults when no file exists. Raises
    AnchoredOverrideError when the file exists but is malformed.
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        return AnchoredOverrides(
            active=False,
            max_per_session=DEFAULT_MAX_PER_SESSION,
            turn_spacing=DEFAULT_TURN_SPACING,
            momentum_ceiling=DEFAULT_MOMENTUM_CEILING,
            chapter_health_floor=DEFAULT_CHAPTER_HEALTH_FLOOR,
            source_path=None,
        )
    parsed = _read_toml(resolved)
    # Acknowledgment field MUST be present and exactly True. Per WO:
    # both missing-field and value=False produce a startup error.
    if _ACK_FIELD not in parsed:
        raise AnchoredOverrideError(
            f"bio_anchored_overrides.toml missing required "
            f"acknowledgment field: {_ACK_FIELD}",
        )
    ack = parsed[_ACK_FIELD]
    if ack is not True:
        raise AnchoredOverrideError(
            f"bio_anchored_overrides.toml: {_ACK_FIELD} must be "
            f"literal `true`; got {ack!r}",
        )
    # Coerce + validate each cap. Missing keys fall back to default.
    effective: Dict[str, Any] = {}
    for attr_name, toml_key, default, expected in _CAP_DEFS:
        if toml_key in parsed:
            effective[attr_name] = _coerce(toml_key, parsed[toml_key], expected)
        else:
            effective[attr_name] = default
    return AnchoredOverrides(
        active=True,
        max_per_session=effective["max_per_session"],
        turn_spacing=effective["turn_spacing"],
        momentum_ceiling=effective["momentum_ceiling"],
        chapter_health_floor=effective["chapter_health_floor"],
        source_path=str(resolved),
    )


def get_cap(name: str, overrides: Optional[AnchoredOverrides] = None) -> Any:
    """Return the effective cap value. `overrides=None` loads on demand."""
    o = overrides if overrides is not None else load_overrides()
    return getattr(o, name)


def caps_overridden() -> bool:
    """Cheap operator-dashboard banner check. Returns True when an
    override file is present + well-formed + acknowledged."""
    try:
        return load_overrides().active
    except AnchoredOverrideError:
        # A malformed file is itself "override intent" — return True
        # so the operator sees that something is wrong rather than
        # silently using defaults.
        return True


def emit_session_start_log() -> Optional[str]:
    """Return the WARNING log line text when overrides are active.
    Returns None when defaults apply (caller emits nothing)."""
    try:
        o = load_overrides()
    except AnchoredOverrideError as exc:
        return (
            f"[bio_anchored] OVERRIDES FILE MALFORMED — "
            f"session is operating with default caps: {exc}"
        )
    if not o.active:
        return None
    return (
        f"[bio_anchored] OVERRIDES ACTIVE — session is operating outside "
        f"default oral-history posture: "
        f"max_per_session={o.max_per_session} "
        f"turn_spacing={o.turn_spacing} "
        f"momentum_ceiling={o.momentum_ceiling} "
        f"chapter_health_floor={o.chapter_health_floor} "
        f"(source={o.source_path})"
    )


def readiness_gate_blocked() -> bool:
    """Helper for any future parent_session_readiness gate. Returns
    True when overrides are active — that gate should refuse to pass.
    Per WO acceptance gate #16.

    Currently no caller exists in the codebase (parent_session_readiness
    module is not yet implemented). When that module lands, it
    consults this helper at gate-verification time."""
    return caps_overridden()


__all__ = [
    "AnchoredOverrideError",
    "AnchoredOverrides",
    "DEFAULT_MAX_PER_SESSION",
    "DEFAULT_TURN_SPACING",
    "DEFAULT_MOMENTUM_CEILING",
    "DEFAULT_CHAPTER_HEALTH_FLOOR",
    "load_overrides",
    "get_cap",
    "caps_overridden",
    "emit_session_start_log",
    "readiness_gate_blocked",
]
