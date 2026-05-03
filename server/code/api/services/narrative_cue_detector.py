"""WO-NARRATIVE-CUE-LIBRARY-01 Phase 2 — Pure Cue Detector.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

A pure-stdlib, deterministic narrative-cue detector. Given a narrator's
utterance text and (optionally) the section the interview is currently
in, returns ranked CueDetection results: which cue type best fits the
narrator's text, and what trigger terms matched.

This is a LISTENER AID. The detector does NOT write truth, does NOT
classify the narrator, does NOT infer cultural identity. Its only job
is to surface a cue that downstream Lori-side composers can use to
shape the next reflection / question / silence.

═══════════════════════════════════════════════════════════════════════
  LAW 3 [INFRASTRUCTURE] — same pattern as story_preservation.py
═══════════════════════════════════════════════════════════════════════

This module imports ONLY from stdlib. It MUST NOT import from:
  - api.routers.extract
  - api.prompt_composer
  - api.memory_echo
  - api.routers.llm_api
  - api.routers.chat_ws
  - api.routers.family_truth
  - api.safety
  - api.db
  - api.services.story_preservation
  - api.services.story_trigger
  - api.services.utterance_frame
  - api.services.lori_reflection

The mechanical gate is `tests/test_narrative_cue_detector_isolation.py`,
which AST-walks this module's imports transitively and fails the build
if any forbidden prefix is found.

The wall exists because this is a LISTENER AID with hard rules:
  1. Cue library must NEVER write truth
  2. Cue library must NEVER infer narrator identity
  3. Detector's runtime output must NOT include operator_extract_hints
     (those are operator-side coaching, not runtime guidance)

Coupling to extraction would invite "while we're here, let's also
write the field" — which violates rule 1.

═══════════════════════════════════════════════════════════════════════
  WHAT IT IS NOT
═══════════════════════════════════════════════════════════════════════

  - NOT an LLM call. Pure regex / keyword matching against the locked
    library's trigger terms.
  - NOT a classifier of the narrator's cultural identity. It tags the
    UTTERANCE pattern, not the speaker.
  - NOT a truth writer. It returns hints; Lori composes; truth flows
    only through the existing Review Queue.
  - NOT a one-cue-only judgment. Multiple cues can match; the top
    one is the highest-scoring match with stable tie-breaking by
    library order, but consumers can read the full ranked list.

═══════════════════════════════════════════════════════════════════════

Public API:
    build_library() → NarrativeCueLibrary
        Loads the locked v1 seed library from
        data/lori/narrative_cue_library.v1.seed.json. Cached.

    build_library_from_path(path: str) → NarrativeCueLibrary
        Loads from any path. Used by tests and operator tools.

    detect_cues(text: str, current_section: str | None = None,
                library: NarrativeCueLibrary | None = None)
        → CueDetection
        The main detector. Returns ranked cues with trigger matches.

Determinism guarantee: the same input always produces the same output.
No randomness, no hashing of timestamps, no environment reads.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ── Module-internal constants ─────────────────────────────────────────────

# Default library path (v1 seed — schema-aligned, eval-aligned).
# v2 library exists at narrative_cue_library.json but uses incompatible
# cue type names; reconciliation is parked for a later phase.
_REPO_ROOT = Path(__file__).resolve().parents[4]  # services/<f>.py → repo root
_DEFAULT_LIBRARY_PATH = _REPO_ROOT / "data" / "lori" / "narrative_cue_library.v1.seed.json"

# Section-to-cue affinity bonus. When the interview is in a known section
# and a cue's operator_extract_hints reference paths under that section,
# the cue gets a small score bump to break ties in the cue's favor.
# Operator-side hint, never exposed in the runtime CueMatch output.
_SECTION_BONUS = 1


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CueMatch:
    """A single cue type that matched the narrator's text.

    Fields surfaced at runtime:
      cue_id, cue_type, label, risk_level, scene_anchor_dimensions,
      safe_followups, forbidden_moves, trigger_matches, score.

    DELIBERATELY OMITTED at runtime: operator_extract_hints. Those are
    operator-side coaching notes (which extraction fields a cue COULD
    inform if the narrator confirms in a later turn) — they must not
    leak into Lori's response composer or the runtime UI. The library
    schema enforces `runtime_exposes_extract_hints: false`.
    """

    cue_id: str
    cue_type: str
    label: str
    risk_level: str  # "low" | "medium" | "sensitive" | "safety_override"
    scene_anchor_dimensions: Tuple[str, ...]
    safe_followups: Tuple[str, ...]
    forbidden_moves: Tuple[str, ...]
    trigger_matches: Tuple[str, ...]   # which library trigger terms hit (in order)
    score: int                          # number of unique trigger hits (+ section bonus)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "cue_type": self.cue_type,
            "label": self.label,
            "risk_level": self.risk_level,
            "scene_anchor_dimensions": list(self.scene_anchor_dimensions),
            "safe_followups": list(self.safe_followups),
            "forbidden_moves": list(self.forbidden_moves),
            "trigger_matches": list(self.trigger_matches),
            "score": self.score,
        }


@dataclass(frozen=True)
class CueDetection:
    """Ordered result of running the detector on one narrator utterance.

    cues: full ranked list of CueMatch objects (highest score first,
          library order on tie). Empty if no trigger fired.
    top_cue: convenience pointer to cues[0] (or None if empty).
    no_match_reason: short string when cues is empty (else "").
    """

    cues: Tuple[CueMatch, ...]
    top_cue: Optional[CueMatch]
    no_match_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cues": [c.to_dict() for c in self.cues],
            "top_cue": self.top_cue.to_dict() if self.top_cue else None,
            "no_match_reason": self.no_match_reason,
        }


@dataclass(frozen=True)
class _CueDef:
    """Internal: one cue type loaded from the library JSON, with its
    pre-compiled trigger pattern. Held in NarrativeCueLibrary."""

    cue_id: str
    cue_type: str
    label: str
    risk_level: str
    scene_anchor_dimensions: Tuple[str, ...]
    safe_followups: Tuple[str, ...]
    forbidden_moves: Tuple[str, ...]
    operator_extract_hints: Tuple[str, ...]
    trigger_terms: Tuple[str, ...]
    # Map normalized lowercase trigger → original-case trigger (for output)
    _trigger_lookup: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class NarrativeCueLibrary:
    """Loaded library with cue defs in stable order. Held immutably so
    a passed-in library survives concurrent detector calls without
    mutation risk."""

    version: int
    description: str
    cue_defs: Tuple[_CueDef, ...]


# ── Library loader ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def build_library() -> NarrativeCueLibrary:
    """Load the locked v1 seed library. Cached — parses once per process."""
    return build_library_from_path(str(_DEFAULT_LIBRARY_PATH))


def build_library_from_path(path: str) -> NarrativeCueLibrary:
    """Load a library from any path. Useful for tests and operator tools.

    Validates the structural minimum: cue_types is a list, each has the
    required fields the detector reads. Does NOT validate against the
    full JSON Schema — the schema validator can ride on top if needed
    (and the schema file lives at data/lori/narrative_cue_schema.json).

    Raises ValueError on malformed input with a clear message naming
    the specific cue index that failed.
    """
    raw_path = Path(path)
    try:
        raw_text = raw_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"narrative_cue_detector: cannot read library at {path}: {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"narrative_cue_detector: library JSON parse failed at {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"narrative_cue_detector: library root must be an object at {path}")
    if data.get("no_truth_write") is not True:
        raise ValueError(
            f"narrative_cue_detector: library at {path} must declare "
            f"'no_truth_write': true. Refusing to load — that flag is the "
            f"safety covenant of the cue library."
        )

    version = int(data.get("version", 0))
    description = str(data.get("description", ""))
    raw_cue_types = data.get("cue_types")
    if not isinstance(raw_cue_types, list) or not raw_cue_types:
        raise ValueError(f"narrative_cue_detector: library at {path} has no cue_types")

    cue_defs: List[_CueDef] = []
    for idx, raw in enumerate(raw_cue_types):
        if not isinstance(raw, dict):
            raise ValueError(f"narrative_cue_detector: cue_types[{idx}] must be an object")
        try:
            cue_id = str(raw["cue_id"])
            cue_type = str(raw["cue_type"])
            label = str(raw["label"])
            risk_level = str(raw["risk_level"])
            scene_anchor_dimensions = tuple(str(x) for x in raw["scene_anchor_dimensions"])
            safe_followups = tuple(str(x) for x in raw["safe_followups"])
            forbidden_moves = tuple(str(x) for x in raw["forbidden_moves"])
            operator_extract_hints = tuple(str(x) for x in raw.get("operator_extract_hints", ()))
            trigger_terms_raw = raw["trigger_terms"]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"narrative_cue_detector: cue_types[{idx}] missing required field: {exc}"
            ) from exc

        if not isinstance(trigger_terms_raw, list) or not trigger_terms_raw:
            raise ValueError(
                f"narrative_cue_detector: cue_types[{idx}] ({cue_id}) "
                f"must have at least one trigger_term"
            )

        trigger_terms: List[str] = [str(t) for t in trigger_terms_raw]
        # Build the normalized-lowercase → original lookup for output rendering.
        # If two trigger terms normalize to the same key, the FIRST wins (stable).
        seen_lower: Dict[str, str] = {}
        for term in trigger_terms:
            key = _normalize(term)
            if key and key not in seen_lower:
                seen_lower[key] = term
        trigger_lookup = tuple(sorted(seen_lower.items()))  # stable shape

        cue_defs.append(
            _CueDef(
                cue_id=cue_id,
                cue_type=cue_type,
                label=label,
                risk_level=risk_level,
                scene_anchor_dimensions=scene_anchor_dimensions,
                safe_followups=safe_followups,
                forbidden_moves=forbidden_moves,
                operator_extract_hints=operator_extract_hints,
                trigger_terms=tuple(trigger_terms),
                _trigger_lookup=trigger_lookup,
            )
        )

    return NarrativeCueLibrary(
        version=version,
        description=description,
        cue_defs=tuple(cue_defs),
    )


# ── Text normalization ────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Canonical lowercase form for matching: NFKD-normalized,
    apostrophe-folded, lowercased, whitespace-collapsed.

    Why NFKD: handles smart quotes ('Father's' → 'father's') and accented
    characters that may differ between narrator typing and trigger terms.
    Why apostrophe-folded: 'Father's' / 'Father’s' / 'Fathers'
    should all match 'father'. We strip apostrophes entirely so the
    word-boundary regex catches the bare stem.
    """
    if not s:
        return ""
    n = unicodedata.normalize("NFKD", s)
    # Strip combining marks (accents). Keep base letters.
    n = "".join(ch for ch in n if not unicodedata.combining(ch))
    # Fold curly apostrophes / quotes to ASCII, then strip them entirely.
    n = n.replace("‘", "").replace("’", "").replace("'", "")
    n = n.replace("“", "").replace("”", "").replace('"', "")
    # Lowercase + whitespace collapse.
    n = n.lower()
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _build_match_pattern(trigger_lower: str) -> re.Pattern[str]:
    """Compile a word-boundary regex for a normalized trigger term.

    Multi-word triggers ("Sunday voice", "first time") match as a phrase
    with whitespace flexibility. Single-word triggers match as whole
    tokens (no substring like 'mom' matching 'momentum').
    """
    parts = trigger_lower.split()
    if not parts:
        return re.compile(r"^$")
    escaped = [re.escape(p) for p in parts]
    pattern = r"\b" + r"\s+".join(escaped) + r"\b"
    return re.compile(pattern)


# Cache compiled patterns per trigger term (saves recompiling on every detect call).
@lru_cache(maxsize=512)
def _pattern_for(trigger_lower: str) -> re.Pattern[str]:
    return _build_match_pattern(trigger_lower)


# ── Section bonus helper ──────────────────────────────────────────────────

def _section_bonus_applies(cue_def: _CueDef, current_section: str) -> bool:
    """Return True if `current_section` is referenced (as a path prefix)
    by any of this cue's operator_extract_hints. Used to break ties when
    two cues match equally on trigger terms but the interview is in a
    section the cue is operator-tagged to inform.

    Conservative: matches only when current_section appears as the dotted
    prefix of a hint (e.g. section='parents' matches hint
    'parents.notableLifeEvents' but NOT 'grandparents.memorableStory').
    """
    if not current_section:
        return False
    sec = current_section.strip().lower()
    if not sec:
        return False
    for hint in cue_def.operator_extract_hints:
        h = hint.strip().lower()
        if h == sec or h.startswith(sec + ".") or h.startswith(sec + "_"):
            return True
    return False


# ── The detector ──────────────────────────────────────────────────────────

def detect_cues(
    text: str,
    current_section: Optional[str] = None,
    library: Optional[NarrativeCueLibrary] = None,
) -> CueDetection:
    """Detect narrative cues in narrator text.

    Returns a CueDetection with cues ranked by score (descending), with
    library order as the stable tie-breaker. The top_cue convenience
    pointer is cues[0] when any cue matched, else None.

    Scoring:
      - Each unique trigger_term that fires within the text contributes
        +1 to the cue's score. Duplicate hits of the same term in the
        same text count once.
      - If `current_section` is provided and matches one of the cue's
        operator_extract_hints (as a dotted prefix), score gets +1
        (the section bonus). Operator-side coaching only.

    Determinism: deterministic in `text`, `current_section`, and
    `library` content. No external state read.

    Edge cases:
      - Empty / None text → CueDetection(cues=(), top_cue=None,
        no_match_reason="empty_text")
      - No trigger fires → CueDetection(cues=(), top_cue=None,
        no_match_reason="no_trigger_match")
      - All-whitespace text behaves as empty.
    """
    if library is None:
        library = build_library()

    if not text or not text.strip():
        return CueDetection(cues=(), top_cue=None, no_match_reason="empty_text")

    norm_text = _normalize(text)
    if not norm_text:
        return CueDetection(cues=(), top_cue=None, no_match_reason="empty_text")

    matches: List[Tuple[int, int, CueMatch]] = []  # (score, library_idx, CueMatch)

    for lib_idx, cue_def in enumerate(library.cue_defs):
        hit_terms: List[str] = []
        for lower_term, original_term in cue_def._trigger_lookup:
            pat = _pattern_for(lower_term)
            if pat.search(norm_text):
                hit_terms.append(original_term)

        if not hit_terms:
            continue

        score = len(hit_terms)
        if current_section and _section_bonus_applies(cue_def, current_section):
            score += _SECTION_BONUS

        matches.append((
            score,
            lib_idx,
            CueMatch(
                cue_id=cue_def.cue_id,
                cue_type=cue_def.cue_type,
                label=cue_def.label,
                risk_level=cue_def.risk_level,
                scene_anchor_dimensions=cue_def.scene_anchor_dimensions,
                safe_followups=cue_def.safe_followups,
                forbidden_moves=cue_def.forbidden_moves,
                trigger_matches=tuple(hit_terms),
                score=score,
            ),
        ))

    if not matches:
        return CueDetection(cues=(), top_cue=None, no_match_reason="no_trigger_match")

    # Sort by score DESC, then library_idx ASC (stable tie-break).
    matches.sort(key=lambda x: (-x[0], x[1]))
    ordered_cues = tuple(m[2] for m in matches)
    return CueDetection(
        cues=ordered_cues,
        top_cue=ordered_cues[0],
        no_match_reason="",
    )


# ── Module-level public surface (explicit) ────────────────────────────────

__all__ = [
    "CueMatch",
    "CueDetection",
    "NarrativeCueLibrary",
    "build_library",
    "build_library_from_path",
    "detect_cues",
]
