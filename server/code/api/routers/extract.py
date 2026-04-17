"""Lorevox 8.0 — Multi-Field Extraction Router

POST /api/extract-fields

Accepts a conversational answer and the current interview context,
returns a list of structured field projections that the frontend
projection-sync layer can apply via batchProject / projectValue.

Design:
  - Uses the local LLM (same pipeline as /api/chat) to decompose a
    compound answer into multiple Bio Builder field projections.
  - Each extracted item carries: fieldPath, value, writeMode, confidence.
  - The backend NEVER writes to questionnaire or structuredBio directly.
    The frontend projection-sync layer enforces all write-mode discipline.
  - Falls back to a rules-based regex extractor when LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("lorevox.extract")

router = APIRouter(prefix="/api", tags=["extract"])


# ── Request / Response models ────────────────────────────────────────────────

class ExtractFieldsRequest(BaseModel):
    person_id: str
    session_id: Optional[str] = None
    answer: str
    current_section: Optional[str] = None
    current_target_path: Optional[str] = None
    profile_context: Optional[Dict[str, Any]] = None
    # WO-LIFE-SPINE-04: optional phase hint from the life spine. When
    # provided, the birth-context era guard uses this for decisions
    # instead of string-matching current_section. Valid values match
    # life_spine.school.school_phase_for_year output:
    # "pre_school" | "elementary" | "middle" | "high_school" | "post_school"
    current_phase: Optional[str] = None


class ExtractedItem(BaseModel):
    fieldPath: str
    value: str
    writeMode: str        # "prefill_if_blank" | "candidate_only" | "suggest_only"
    confidence: float     # 0.0–1.0
    source: str = "backend_extract"
    # WO-13 Phase 4 — four method tags: llm | rules | hybrid | rules_fallback
    # The "rules_fallback" tag is reserved for regex output produced after the
    # LLM path failed; downstream (family-truth proposal layer) treats it as
    # lower-trust and never auto-promotes it.
    extractionMethod: str = "llm"
    repeatableGroup: Optional[str] = None  # FIX-4: group tag for same-person field association

    # WO-EX-VALIDATE-01 — age-math plausibility annotations. Populated only
    # when HORNELORE_AGE_VALIDATOR=1. Frontend may use plausibility_flag
    # to render warn badges. 'impossible' items are dropped before
    # response assembly so they should never reach here.
    plausibility_flag: Optional[str] = None     # "ok" | "warn" | None
    plausibility_reason: Optional[str] = None   # human-readable explanation
    plausibility_age: Optional[int] = None      # computed age at event


class ExtractFieldsResponse(BaseModel):
    items: List[ExtractedItem]
    # WO-13 Phase 4 — mirror the four-tag taxonomy on the response envelope.
    method: str = "llm"   # "llm" | "rules" | "hybrid" | "rules_fallback" | "fallback"
    raw_llm_output: Optional[str] = None  # debug: raw model output (only in dev)


# ── Field schema for the LLM prompt ─────────────────────────────────────────

EXTRACTABLE_FIELDS = {
    # Identity / personal (prefill_if_blank)
    "personal.fullName":       {"label": "Full name", "writeMode": "prefill_if_blank"},
    "personal.preferredName":  {"label": "Preferred name or nickname", "writeMode": "prefill_if_blank"},
    "personal.dateOfBirth":    {"label": "Date of birth (YYYY-MM-DD if possible)", "writeMode": "prefill_if_blank"},
    "personal.placeOfBirth":   {"label": "Place of birth (city, state/country)", "writeMode": "prefill_if_blank"},
    "personal.birthOrder":     {"label": "Birth order (first child, second, etc.)", "writeMode": "prefill_if_blank"},

    # Early memories (suggest_only)
    "earlyMemories.firstMemory":       {"label": "Earliest childhood memory", "writeMode": "suggest_only"},
    "earlyMemories.significantEvent":   {"label": "Significant childhood event", "writeMode": "suggest_only"},

    # Education & career (suggest_only)
    "education.schooling":           {"label": "Schooling history (name of school, details)", "writeMode": "suggest_only"},
    "education.higherEducation":     {"label": "College or higher education", "writeMode": "suggest_only"},
    "education.earlyCareer":         {"label": "First job or early career", "writeMode": "suggest_only"},
    "education.careerProgression":   {"label": "Career progression and major changes", "writeMode": "suggest_only"},

    # Later years (suggest_only)
    "laterYears.retirement":               {"label": "Retirement experience", "writeMode": "suggest_only"},
    "laterYears.lifeLessons":              {"label": "Life lessons learned", "writeMode": "suggest_only"},
    "laterYears.significantEvent":         {"label": "Significant later-life event or turning point", "writeMode": "suggest_only"},

    # Hobbies (suggest_only)
    "hobbies.hobbies":              {"label": "Hobbies and interests", "writeMode": "suggest_only"},
    "hobbies.personalChallenges":   {"label": "Personal challenges or hardships", "writeMode": "suggest_only"},

    # Additional notes (suggest_only)
    "additionalNotes.unfinishedDreams":           {"label": "Unfinished dreams or goals", "writeMode": "suggest_only"},

    # Repeatable: parents (candidate_only)
    "parents.relation":          {"label": "Parent relationship (father/mother/step)", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.firstName":         {"label": "Parent first name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.lastName":          {"label": "Parent last name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.maidenName":        {"label": "Parent maiden name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.birthPlace":        {"label": "Parent birthplace", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.occupation":        {"label": "Parent occupation", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.notableLifeEvents": {"label": "Notable life events of parent", "writeMode": "candidate_only", "repeatable": "parents"},

    # Repeatable: siblings (candidate_only)
    "siblings.relation":              {"label": "Sibling relationship (brother/sister)", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.firstName":             {"label": "Sibling first name", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.lastName":              {"label": "Sibling last name", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.birthOrder":            {"label": "Sibling birth order (older/younger)", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.uniqueCharacteristics": {"label": "Sibling unique characteristics", "writeMode": "candidate_only", "repeatable": "siblings"},

    # ── WO-EX-SCHEMA-01 — Children (repeatable) ──────────────────────────────
    "family.children.relation":       {"label": "Child relation (son/daughter/etc.)", "writeMode": "candidate_only", "repeatable": "children"},
    "family.children.firstName":      {"label": "Child first name", "writeMode": "candidate_only", "repeatable": "children"},
    "family.children.lastName":       {"label": "Child last name", "writeMode": "candidate_only", "repeatable": "children"},
    "family.children.dateOfBirth":    {"label": "Child date of birth", "writeMode": "candidate_only", "repeatable": "children"},
    "family.children.placeOfBirth":   {"label": "Child place of birth", "writeMode": "candidate_only", "repeatable": "children"},
    "family.children.preferredName":  {"label": "Child nickname", "writeMode": "candidate_only", "repeatable": "children"},
    "family.children.birthOrder":     {"label": "Child birth order (oldest, youngest, etc.)", "writeMode": "candidate_only", "repeatable": "children"},

    # ── WO-EX-SCHEMA-01 — Spouse / partner ────────────────────────────────────
    "family.spouse.firstName":        {"label": "Spouse / partner first name", "writeMode": "prefill_if_blank"},
    "family.spouse.lastName":         {"label": "Spouse / partner last name", "writeMode": "prefill_if_blank"},
    "family.spouse.maidenName":       {"label": "Spouse / partner maiden name", "writeMode": "prefill_if_blank"},
    "family.spouse.dateOfBirth":      {"label": "Spouse / partner DOB", "writeMode": "prefill_if_blank"},
    "family.spouse.placeOfBirth":     {"label": "Spouse / partner place of birth", "writeMode": "prefill_if_blank"},

    # ── WO-EX-SCHEMA-01 — Marriage event ──────────────────────────────────────
    "family.marriageDate":            {"label": "Date of marriage", "writeMode": "prefill_if_blank"},
    "family.marriagePlace":           {"label": "Place of marriage", "writeMode": "prefill_if_blank"},
    "family.marriageNotes":           {"label": "Marriage context / how we met", "writeMode": "suggest_only"},

    # ── WO-EX-SCHEMA-01 — Prior partners (repeatable) ────────────────────────
    "family.priorPartners.firstName": {"label": "Previous partner first name", "writeMode": "candidate_only", "repeatable": "priorPartners"},
    "family.priorPartners.lastName":  {"label": "Previous partner last name", "writeMode": "candidate_only", "repeatable": "priorPartners"},
    "family.priorPartners.period":    {"label": "Period with previous partner", "writeMode": "candidate_only", "repeatable": "priorPartners"},

    # ── WO-EX-SCHEMA-01 — Grandchildren (repeatable) ─────────────────────────
    "family.grandchildren.firstName": {"label": "Grandchild first name", "writeMode": "candidate_only", "repeatable": "grandchildren"},
    "family.grandchildren.relation":  {"label": "Grandchild relation (via which child)", "writeMode": "candidate_only", "repeatable": "grandchildren"},
    "family.grandchildren.notes":     {"label": "Grandchild personality or notable trait", "writeMode": "candidate_only", "repeatable": "grandchildren"},

    # ── WO-EX-SCHEMA-01 — Residence (repeatable) ─────────────────────────────
    "residence.place":                {"label": "City / town / address lived in", "writeMode": "candidate_only", "repeatable": "residences"},
    "residence.region":               {"label": "State / country of residence", "writeMode": "candidate_only", "repeatable": "residences"},
    "residence.period":               {"label": "Years at this residence (e.g., 1962-1964)", "writeMode": "candidate_only", "repeatable": "residences"},
    "residence.notes":                {"label": "Residence notes (home type, memory)", "writeMode": "candidate_only", "repeatable": "residences"},

    # ── WO-SCHEMA-02 Priority 1 — Grandparents (repeatable) ─────────────────
    "grandparents.side":              {"label": "Grandparent side (maternal/paternal)", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.firstName":         {"label": "Grandparent first name", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.lastName":          {"label": "Grandparent last name", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.maidenName":        {"label": "Grandparent maiden name", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.birthPlace":        {"label": "Grandparent birthplace", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.ancestry":          {"label": "Grandparent ancestry or ethnic background", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.memorableStory":    {"label": "Memorable story about grandparent", "writeMode": "suggest_only", "repeatable": "grandparents"},

    # ── WO-SCHEMA-02 Priority 2 — Military ──────────────────────────────────
    "military.branch":                {"label": "Military branch (Army, Navy, etc.)", "writeMode": "suggest_only"},
    "military.yearsOfService":        {"label": "Years of military service (e.g., 1965-1968)", "writeMode": "suggest_only"},
    "military.rank":                  {"label": "Highest military rank attained", "writeMode": "suggest_only"},
    "military.deploymentLocation":    {"label": "Military deployment location", "writeMode": "suggest_only", "repeatable": "military"},
    "military.significantEvent":      {"label": "Significant military event or experience", "writeMode": "suggest_only", "repeatable": "military"},

    # ── WO-SCHEMA-02 Priority 3 — Faith & Values ────────────────────────────
    "faith.denomination":             {"label": "Faith denomination (Catholic, Lutheran, etc.)", "writeMode": "suggest_only"},
    "faith.role":                     {"label": "Role in faith community (choir, deacon, etc.)", "writeMode": "suggest_only"},
    "faith.significantMoment":        {"label": "Significant faith moment or turning point", "writeMode": "suggest_only"},
    "faith.values":                   {"label": "Core values or beliefs", "writeMode": "suggest_only"},

    # ── WO-SCHEMA-02 Priority 4 — Health ────────────────────────────────────
    "health.majorCondition":          {"label": "Major health condition or diagnosis", "writeMode": "suggest_only", "repeatable": "health"},
    "health.milestone":               {"label": "Health milestone (surgery, recovery, etc.)", "writeMode": "suggest_only"},
    "health.lifestyleChange":         {"label": "Significant lifestyle change for health", "writeMode": "suggest_only"},

    # ── WO-SCHEMA-02 Priority 5 — Community & Civic Life ────────────────────
    "community.organization":         {"label": "Community organization or group", "writeMode": "suggest_only", "repeatable": "community"},
    "community.role":                 {"label": "Role in community organization", "writeMode": "suggest_only", "repeatable": "community"},
    "community.yearsActive":          {"label": "Years active in community role", "writeMode": "suggest_only", "repeatable": "community"},
    "community.significantEvent":     {"label": "Significant community event or contribution", "writeMode": "suggest_only"},

    # ── WO-SCHEMA-02 Priority 6 — Pets ──────────────────────────────────────
    "pets.name":                      {"label": "Pet name", "writeMode": "candidate_only", "repeatable": "pets"},
    "pets.species":                   {"label": "Pet species (dog, cat, horse, etc.)", "writeMode": "candidate_only", "repeatable": "pets"},
    "pets.notes":                     {"label": "Pet notes (personality, story, meaning)", "writeMode": "suggest_only", "repeatable": "pets"},

    # ── WO-SCHEMA-02 Priority 7 — Travel ────────────────────────────────────
    "travel.destination":             {"label": "Travel destination", "writeMode": "suggest_only", "repeatable": "travel"},
    "travel.purpose":                 {"label": "Purpose of travel (vacation, work, family, military)", "writeMode": "suggest_only", "repeatable": "travel"},
    "travel.significantTrip":         {"label": "Most significant or memorable trip", "writeMode": "suggest_only"},
}

# ── Phase G: Protected identity fields ─────────────────────────────────────
# These fields MUST NOT be directly overwritten by chat extraction.
# If the backend already has a canonical value and the extracted value conflicts,
# the extraction result should be flagged as suggest_only with a conflict reason.
PROTECTED_IDENTITY_FIELDS = frozenset([
    "personal.fullName",
    "personal.preferredName",
    "personal.dateOfBirth",
    "personal.placeOfBirth",
    "personal.birthOrder",
])


# ── LLM availability cache ──────────────────────────────────────────────────
# Keep this cache very short-lived. A long negative cache causes extraction
# to stay stuck on rules fallback even after the model has warmed successfully.
# We re-check frequently and always refresh to True immediately after a
# successful probe.

import time as _time
import uuid as _uuid

_llm_available_cache: dict = {"available": None, "checked_at": 0.0}
_LLM_CHECK_TTL = 5  # seconds — keep short so negative cache clears quickly

# ── Extraction metrics (Phase 6B) ──────────────────────────────────────────
_extraction_metrics: dict = {
    "total_turns": 0,
    "llm_turns": 0,
    "rules_turns": 0,
    "fallback_turns": 0,
    "total_parsed": 0,
    "total_accepted": 0,
    "total_rejected": 0,
    "reject_reasons": {},  # reason → count
}


def _record_metric(method: str, parsed: int, accepted: int, rejected: int,
                   reject_reasons: Optional[List[str]] = None) -> None:
    """Record extraction metrics for a single turn."""
    _extraction_metrics["total_turns"] += 1
    if method == "llm":
        _extraction_metrics["llm_turns"] += 1
    elif method == "rules":
        _extraction_metrics["rules_turns"] += 1
    else:
        _extraction_metrics["fallback_turns"] += 1
    _extraction_metrics["total_parsed"] += parsed
    _extraction_metrics["total_accepted"] += accepted
    _extraction_metrics["total_rejected"] += rejected
    if reject_reasons:
        for reason in reject_reasons:
            _extraction_metrics["reject_reasons"][reason] = (
                _extraction_metrics["reject_reasons"].get(reason, 0) + 1
            )


def _is_llm_available() -> bool:
    """Return True if the LLM stack is responsive, using cached result."""
    now = _time.time()
    cache_age = now - _llm_available_cache["checked_at"]
    if (
        _llm_available_cache["available"] is not None
        and cache_age < _LLM_CHECK_TTL
    ):
        logger.info(
            "[extract] LLM availability cache hit: %s (age=%.1fs)",
            "available" if _llm_available_cache["available"] else "unavailable",
            cache_age,
        )
        return _llm_available_cache["available"]

    # Quick probe — tiny prompt, low max_new, should return fast
    try:
        from ..llm_interview import _try_call_llm
        result = _try_call_llm(
            "Return exactly: {\"status\":\"ok\"}",
            "ping",
            max_new=20, temp=0.01, top_p=1.0,
        )
        available = result is not None
    except Exception as exc:
        available = False
        logger.warning("[extract] LLM availability probe failed: %s: %s", type(exc).__name__, exc)

    _llm_available_cache["available"] = available
    _llm_available_cache["checked_at"] = now
    logger.info("[extract] LLM availability probe: %s", "available" if available else "unavailable")
    return available


def _mark_llm_available() -> None:
    """Refresh cache to available after a successful LLM response."""
    _llm_available_cache["available"] = True
    _llm_available_cache["checked_at"] = _time.time()
    logger.info("[extract] LLM cache refreshed: available")


def _mark_llm_unavailable(reason: str = "unknown") -> None:
    """Mark cache unavailable with reason logging."""
    _llm_available_cache["available"] = False
    _llm_available_cache["checked_at"] = _time.time()
    logger.warning("[extract] LLM cache refreshed: unavailable (%s)", reason)


# ── LLM-based extraction ────────────────────────────────────────────────────

def _build_extraction_prompt(answer: str, current_section: Optional[str], current_target: Optional[str]) -> tuple[str, str]:
    """Build system + user prompts for multi-field extraction."""

    # Build field catalog for the prompt
    field_lines = []
    for path, meta in EXTRACTABLE_FIELDS.items():
        field_lines.append(f'  "{path}": "{meta["label"]}" [{meta["writeMode"]}]')
    field_catalog = "\n".join(field_lines)

    # Build a COMPACT field list — only fields relevant to the current section
    # to reduce prompt size for small context windows
    relevant_fields = {}
    for path, meta in EXTRACTABLE_FIELDS.items():
        relevant_fields[path] = meta["label"]

    # If we have a section hint, prioritize those fields but still include identity
    compact_catalog = ", ".join(f'"{p}"={m}' for p, m in relevant_fields.items())

    system = (
        "Extract biographical facts from the narrator's answer as JSON.\n"
        "Rules: only explicit facts, no guessing. Return JSON array only.\n"
        "Each item: {\"fieldPath\":\"...\",\"value\":\"...\",\"confidence\":0.0-1.0}\n"
        "Confidence: 0.9=clearly stated, 0.7=implied.\n"
        "Dates: YYYY-MM-DD if full date given. Places: City, State format.\n"
        "IMPORTANT: Use ONLY these exact fieldPath values:\n"
        f"{compact_catalog}\n"
        "\n"
        "ROUTING DISTINCTIONS — common mistakes to avoid:\n"
        "• Pets vs hobbies: Animals the narrator owned (dogs, cats, horses) → pets.name / pets.species / pets.notes. "
        "NOT hobbies.hobbies. \"We had a Golden Retriever named Ivan\" → pets.*, not hobbies.*\n"
        "• Siblings vs children: Brothers and sisters the narrator grew up with → siblings.*. "
        "NOT family.children.* (which is for the narrator's own kids). "
        "\"My older brother Vincent\" → siblings.firstName, siblings.birthOrder\n"
        "• Birthplace vs residence: \"I was born in Spokane\" → personal.placeOfBirth. "
        "NOT residence.place (which is for places the narrator lived later).\n"
        "• Early career vs career progression: First job or entry-level work → education.earlyCareer. "
        "Long-duration work or later-career roles (\"since 1997\", \"for 29 years\", \"until retirement\") "
        "→ education.careerProgression.\n"
        "\n"
        "Example — narrator says: \"My dad John Smith was a teacher and my sister Amy was older.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"parents.relation\",\"value\":\"father\",\"confidence\":0.9},"
        "{\"fieldPath\":\"parents.firstName\",\"value\":\"John\",\"confidence\":0.9},"
        "{\"fieldPath\":\"parents.lastName\",\"value\":\"Smith\",\"confidence\":0.9},"
        "{\"fieldPath\":\"parents.occupation\",\"value\":\"teacher\",\"confidence\":0.9},"
        "{\"fieldPath\":\"siblings.relation\",\"value\":\"sister\",\"confidence\":0.9},"
        "{\"fieldPath\":\"siblings.firstName\",\"value\":\"Amy\",\"confidence\":0.9},"
        "{\"fieldPath\":\"siblings.birthOrder\",\"value\":\"older\",\"confidence\":0.7}]\n"
        "\n"
        "Example — narrator says: \"I worked as a welder and later became a supervisor at a shipyard.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"education.earlyCareer\",\"value\":\"welder\",\"confidence\":0.9},"
        "{\"fieldPath\":\"education.careerProgression\",\"value\":\"supervisor at a shipyard\",\"confidence\":0.9}]\n"
        "Career rules: use education.earlyCareer for first job, education.careerProgression for later roles. "
        "Do NOT invent career.* or personal.profession paths.\n"
        "\n"
        "Example — narrator says: \"She served in the Navy as a programmer and later became a professor of computer science.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"education.earlyCareer\",\"value\":\"served in the Navy as a programmer\",\"confidence\":0.89},"
        "{\"fieldPath\":\"education.careerProgression\",\"value\":\"later became a professor of computer science\",\"confidence\":0.91}]\n"
        "\n"
        "Example — narrator says: \"She began by studying chimpanzees in the field and later became a leading primatologist, author, and international advocate for animals.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"education.earlyCareer\",\"value\":\"began by studying chimpanzees in the field\",\"confidence\":0.84},"
        "{\"fieldPath\":\"education.careerProgression\",\"value\":\"later became a leading primatologist, author, and international advocate for animals\",\"confidence\":0.92}]\n"
        "\n"
        "Career rules: use education.earlyCareer for first work, early service, early fieldwork, apprenticeship, or initial occupation. "
        "Use education.careerProgression for later roles, promotions, research leadership, public recognition, authorship, teaching, advocacy, public office, or major career transitions. "
        "Organization names, military branches, research settings, and travel context belong inside the value text when relevant; do not invent separate field paths for them. "
        "Do NOT invent paths like education.career, employment.organization, education.travelDestination, career.fieldOfStudy, career.location, career.business, career.politics.*, or personal.profession.\n"
        "\n"
        "Example — narrator says: \"My oldest son Vince was born in Germany in 1960, and my daughter Sarah was born in Bismarck in 1962.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"family.children.relation\",\"value\":\"son\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.firstName\",\"value\":\"Vince\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.placeOfBirth\",\"value\":\"Germany\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.dateOfBirth\",\"value\":\"1960\",\"confidence\":0.7},"
        "{\"fieldPath\":\"family.children.relation\",\"value\":\"daughter\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.firstName\",\"value\":\"Sarah\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.placeOfBirth\",\"value\":\"Bismarck\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.dateOfBirth\",\"value\":\"1962\",\"confidence\":0.7}]\n"
        "\n"
        "Example — narrator says: \"I married my wife Dorothy in 1958 in Fargo.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"family.spouse.firstName\",\"value\":\"Dorothy\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.marriageDate\",\"value\":\"1958\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.marriagePlace\",\"value\":\"Fargo\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"We lived in West Fargo from 1962 to 1964, then moved to Bismarck.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"residence.place\",\"value\":\"West Fargo\",\"confidence\":0.9},"
        "{\"fieldPath\":\"residence.period\",\"value\":\"1962-1964\",\"confidence\":0.9},"
        "{\"fieldPath\":\"residence.place\",\"value\":\"Bismarck\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"My grandmother on my mother's side came from Russia. Her name was Anna Petrova.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"grandparents.side\",\"value\":\"maternal\",\"confidence\":0.9},"
        "{\"fieldPath\":\"grandparents.firstName\",\"value\":\"Anna\",\"confidence\":0.9},"
        "{\"fieldPath\":\"grandparents.lastName\",\"value\":\"Petrova\",\"confidence\":0.9},"
        "{\"fieldPath\":\"grandparents.birthPlace\",\"value\":\"Russia\",\"confidence\":0.7}]\n"
        "\n"
        "Example — narrator says: \"I served in the Army from 1965 to 1968. I was stationed in Germany and made Sergeant.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"military.branch\",\"value\":\"Army\",\"confidence\":0.9},"
        "{\"fieldPath\":\"military.yearsOfService\",\"value\":\"1965-1968\",\"confidence\":0.9},"
        "{\"fieldPath\":\"military.deploymentLocation\",\"value\":\"Germany\",\"confidence\":0.9},"
        "{\"fieldPath\":\"military.rank\",\"value\":\"Sergeant\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"We were Catholic, and I sang in the church choir for thirty years. My faith got me through the hard times.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"faith.denomination\",\"value\":\"Catholic\",\"confidence\":0.9},"
        "{\"fieldPath\":\"faith.role\",\"value\":\"church choir for thirty years\",\"confidence\":0.9},"
        "{\"fieldPath\":\"faith.values\",\"value\":\"faith got me through the hard times\",\"confidence\":0.7}]\n"
        "\n"
        "Example — narrator says: \"I had a heart attack in 2005 and had to change everything about how I ate.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"health.majorCondition\",\"value\":\"heart attack\",\"confidence\":0.9},"
        "{\"fieldPath\":\"health.milestone\",\"value\":\"heart attack in 2005\",\"confidence\":0.9},"
        "{\"fieldPath\":\"health.lifestyleChange\",\"value\":\"changed everything about how I ate\",\"confidence\":0.8}]\n"
        "\n"
        "Example — narrator says: \"I volunteered with the Lions Club for twenty years and was president twice.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"community.organization\",\"value\":\"Lions Club\",\"confidence\":0.9},"
        "{\"fieldPath\":\"community.role\",\"value\":\"president\",\"confidence\":0.9},"
        "{\"fieldPath\":\"community.yearsActive\",\"value\":\"twenty years\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"We always had dogs. Our first was a collie named Laddie.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"pets.species\",\"value\":\"dog\",\"confidence\":0.9},"
        "{\"fieldPath\":\"pets.name\",\"value\":\"Laddie\",\"confidence\":0.9},"
        "{\"fieldPath\":\"pets.notes\",\"value\":\"collie, first family dog\",\"confidence\":0.8}]\n"
        "\n"
        "Example — narrator says: \"We took a trip to Europe in 1985. It was our anniversary.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"travel.destination\",\"value\":\"Europe\",\"confidence\":0.9},"
        "{\"fieldPath\":\"travel.purpose\",\"value\":\"anniversary trip\",\"confidence\":0.8}]\n"
        "\n"
        "NEGATION RULE: If the narrator explicitly says they did NOT have an experience "
        "(e.g., 'I never served', 'I've been pretty healthy', 'I didn't go to college'), "
        "extract NOTHING for that category. Do not guess or infer fields from denied experiences.\n"
        "\n"
        "SUBJECT RULE: Only extract fields for the NARRATOR being interviewed. "
        "When the narrator describes a family member's experience (mother's school, father's work, "
        "grandfather's military service), use family-scoped fields (grandparents.*, parents.*) — "
        "NOT the narrator's personal fields. Example: narrator says 'My mother went to Mount Marty school' "
        "→ this is faith/family history, NOT education.schooling for the narrator.\n"
        "\n"
        "FIELD ROUTING RULES:\n"
        "- Narrator's volunteer, civic, or professional community involvement → community.* (NOT education.earlyCareer)\n"
        "- Animals the narrator owned or cared for → pets.* (NOT hobbies.hobbies)\n"
        "- Places narrator traveled to and returned from → travel.* (NOT residence.*)\n"
        "- Places narrator lived for an extended period → residence.* (can ALSO be travel.* if it was a relocation)\n"
        "- Family member's military service → military.* fields with a note that this is family history, "
        "but do NOT extract military.branch or military.rank for the NARRATOR unless they personally served"
    )

    context_note = ""
    if current_section:
        context_note += f"\nCurrent interview section: {current_section}"
    if current_target:
        context_note += f"\nPrimary question target: {current_target}"

    user = (
        f"Narrator's answer:{context_note}\n\n"
        f"\"{answer}\"\n\n"
        "Extract all facts as a JSON array:"
    )

    return system, user


def _is_compound_answer(answer: str) -> bool:
    """Detect whether a narrator answer contains multiple entities/facts.

    WO-EX-CLAIMS-01: Compound answers need more tokens for the LLM to emit
    a complete JSON array. Heuristics:
      - Multiple capitalized proper names (≥2 distinct)
      - List patterns: "and", commas separating named entities
      - Multiple date/year mentions
    """
    # Find capitalized multi-word names (e.g. "Vincent Edward", "Dorothy")
    # Exclude common sentence starters by requiring preceding comma, and, or lowercase
    proper_names = set()
    for m in re.finditer(r'(?<![.!?]\s)(?:^|(?<=[\s,;]))[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', answer):
        name = m.group()
        # Skip common non-name capitalized words
        if name.lower() not in {"the", "my", "our", "we", "they", "when", "then",
                                 "after", "before", "during", "yes", "no", "well",
                                 "oh", "so", "but", "and", "north", "south", "east",
                                 "west", "january", "february", "march", "april",
                                 "may", "june", "july", "august", "september",
                                 "october", "november", "december", "monday",
                                 "tuesday", "wednesday", "thursday", "friday",
                                 "saturday", "sunday"}:
            proper_names.add(name)

    # Count distinct years mentioned
    years = set(re.findall(r'\b(?:19|20)\d{2}\b', answer))

    # Check for multi-word full names (3+ capitalized words, e.g. "Janice Josephine Zarr")
    # These generate extra LLM fields (middleName, maidenName, etc.) that need more tokens
    has_full_name = bool(re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+', answer))

    # Compound if: 2+ proper names, or 3+ years, or full name present,
    # or answer is long with list markers
    has_list_pattern = bool(re.search(r'(?:,\s*and\s+|;\s+\w)', answer))
    is_compound = (
        len(proper_names) >= 2 or
        len(years) >= 3 or
        has_full_name or
        (has_list_pattern and len(answer) > 150)
    )

    if is_compound:
        logger.info("[extract][CLAIMS-01] Compound answer detected: %d names=%s, %d years, list=%s",
                    len(proper_names), proper_names, len(years), has_list_pattern)
    return is_compound


def _extract_via_llm(answer: str, current_section: Optional[str], current_target: Optional[str]) -> tuple[List[dict], Optional[str]]:
    """Call the local LLM to extract fields. Returns (items, raw_output).

    v8.0 FIX: Short-circuits immediately when the LLM is known to be
    unavailable, preventing the blocking model.generate() call from tying
    up the single uvicorn worker and causing 503 errors.
    """
    # Quick availability gate — cached for LLM_CHECK_TTL seconds
    if not _is_llm_available():
        logger.info("[extract] LLM unavailable (cached) — skipping to rules fallback")
        return [], None

    try:
        from ..llm_interview import _try_call_llm
    except ImportError:
        return [], None

    system, user = _build_extraction_prompt(answer, current_section, current_target)
    # FIX-3: Use a unique ephemeral conv_id for each extraction call to prevent
    # cross-narrator context contamination via shared session/RAG state.
    ephemeral_conv_id = f"_extract_{_uuid.uuid4().hex[:12]}"
    # WO-10M / WO-EX-CLAIMS-01: Token cap is now dynamic.
    # Simple single-fact answers: 128 tokens (original cap, ample for 1-3 items).
    # Compound answers (multiple names, years, list patterns): 384 tokens so the
    # LLM can emit a complete JSON array for 5-10+ items without truncation.
    # The old static 128 cap caused compound answers to truncate mid-JSON,
    # falling to regex fallback which loses entity grouping entirely.
    _base_cap = int(os.getenv("MAX_NEW_TOKENS_EXTRACT", "128"))
    _compound_cap = int(os.getenv("MAX_NEW_TOKENS_EXTRACT_COMPOUND", "384"))
    _extract_cap = _compound_cap if _is_compound_answer(answer) else _base_cap
    _extract_temp = float(os.getenv("EXTRACTION_TEMP", "0.15"))
    _extract_top_p = float(os.getenv("EXTRACTION_TOP_P", "0.9"))
    logger.info("[extract][WO-10M] calling LLM max_new=%d temp=%.2f top_p=%.2f conv=%s",
                _extract_cap, _extract_temp, _extract_top_p, ephemeral_conv_id)
    raw = _try_call_llm(system, user, max_new=_extract_cap, temp=_extract_temp, top_p=_extract_top_p, conv_id=ephemeral_conv_id)
    if not raw:
        # Empty response: mark temporarily unavailable so we retry soon,
        # but do not get stuck for 2 minutes.
        _mark_llm_unavailable("empty-response")
        return [], None

    # Successful response means the LLM is available right now.
    _mark_llm_available()

    # Parse JSON from LLM output
    items = _parse_llm_json(raw)
    return items, raw


def _parse_llm_json(raw: str) -> List[dict]:
    """Parse JSON array from LLM output, handling various formats."""
    raw = raw.strip()
    logger.info("[extract-parse] Raw LLM output (%d chars): %.500s", len(raw), raw)

    arr = None
    parse_method = None

    # Try direct JSON parse
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            arr = parsed
            parse_method = "direct"
        elif isinstance(parsed, dict):
            # LLM may return {"items": [...]} or {"results": [...]}
            for key in ("items", "results", "data", "extracted"):
                if isinstance(parsed.get(key), list):
                    arr = parsed[key]
                    parse_method = f"dict.{key}"
                    break
            if arr is None:
                logger.warning("[extract-parse] LLM returned dict but no array key found: %s", list(parsed.keys()))
    except json.JSONDecodeError as e:
        logger.info("[extract-parse] Direct JSON parse failed: %s", e)

    # Try extracting JSON array from markdown code block
    if arr is None:
        m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group(1))
                parse_method = "markdown_block"
            except json.JSONDecodeError as e:
                logger.info("[extract-parse] Markdown block parse failed: %s", e)

    # Try finding first [ ... ] in the output
    if arr is None:
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group(0))
                parse_method = "bracket_search"
            except json.JSONDecodeError as e:
                logger.info("[extract-parse] Bracket search parse failed: %s", e)

    if arr is None:
        logger.warning("[extract-parse] Could not parse ANY JSON from LLM output")
        return []

    logger.info("[extract-parse] Parsed %d raw items via %s", len(arr), parse_method)

    # Validate each item, logging rejections
    valid = []
    for i, x in enumerate(arr):
        result = _validate_item(x)
        if result:
            valid.append(result)
        else:
            logger.info("[extract-parse] Item %d REJECTED: %s", i, json.dumps(x, default=str)[:300])
    logger.info("[extract-parse] %d/%d items passed validation", len(valid), len(arr))
    return valid


def _validate_item(item: Any) -> Optional[dict]:
    """Validate and normalize a single extraction item."""
    if not isinstance(item, dict):
        logger.info("[extract-validate] REJECT: not a dict, got %s", type(item).__name__)
        return None

    # P1: Accept alternate key names the LLM may use
    fp = (item.get("fieldPath") or item.get("field_path") or item.get("field") or item.get("path") or "").strip()
    # P0: Normalize value — LLM may return list, dict envelope, or string
    raw_val = item.get("value") if "value" in item else item.get("val") if "val" in item else item.get("text")
    if isinstance(raw_val, dict):
        raw_val = raw_val.get("value", "")
    if isinstance(raw_val, list):
        raw_val = ", ".join(str(x) for x in raw_val if x)
    val = (str(raw_val) if raw_val else "").strip()
    if not fp or not val:
        logger.info("[extract-validate] REJECT: empty fieldPath=%r or value=%r (keys=%s)", fp, val, list(item.keys()))
        return None

    # Validate fieldPath exists in our schema
    # For repeatable fields, strip any index: "parents[0].firstName" → "parents.firstName"
    base_path = re.sub(r'\[\d+\]', '', fp)
    if base_path not in EXTRACTABLE_FIELDS:
        # P1: Try common LLM field path variants before rejecting
        # LLMs often output "firstName" instead of "parents.firstName", or
        # "dateOfBirth" instead of "personal.dateOfBirth"
        _FIELD_ALIASES = {
            # Bare field names → qualified paths
            "fullName": "personal.fullName", "full_name": "personal.fullName",
            "name": "personal.fullName",
            "preferredName": "personal.preferredName", "nickname": "personal.preferredName",
            "preferred_name": "personal.preferredName",
            "dateOfBirth": "personal.dateOfBirth", "date_of_birth": "personal.dateOfBirth",
            "dob": "personal.dateOfBirth", "birthday": "personal.dateOfBirth",
            "placeOfBirth": "personal.placeOfBirth", "place_of_birth": "personal.placeOfBirth",
            "birthPlace": "personal.placeOfBirth", "birthplace": "personal.placeOfBirth",
            "birthOrder": "personal.birthOrder", "birth_order": "personal.birthOrder",
            # LLM-invented personal.* paths → nearest valid field
            "personal.profession": "parents.occupation",
            "personal.occupation": "education.earlyCareer",
            "personal.job": "education.earlyCareer",
            "personal.career": "education.careerProgression",
            "personal.school": "education.schooling",
            "personal.education": "education.higherEducation",
            "personal.hobby": "hobbies.hobbies",
            "personal.hobbies": "hobbies.hobbies",
            # Family fields without section prefix
            "father": "parents.relation", "mother": "parents.relation",
            "fatherName": "parents.firstName", "motherName": "parents.firstName",
            "parentName": "parents.firstName", "parent_name": "parents.firstName",
            "parentOccupation": "parents.occupation", "parent_occupation": "parents.occupation",
            "occupation": "parents.occupation", "profession": "parents.occupation",
            "siblingName": "siblings.firstName", "sibling_name": "siblings.firstName",
            "brotherName": "siblings.firstName", "sisterName": "siblings.firstName",
            "brother": "siblings.relation", "sister": "siblings.relation",
            "siblingLastName": "siblings.lastName", "sibling_last_name": "siblings.lastName",
            "firstName": "parents.firstName", "first_name": "parents.firstName",
            "lastName": "parents.lastName", "last_name": "parents.lastName",
            "maidenName": "parents.maidenName", "maiden_name": "parents.maidenName",
            "relation": "parents.relation", "relationship": "parents.relation",
            # Family paths with wrong prefix
            "family.father": "parents.relation", "family.mother": "parents.relation",
            "family.relation": "parents.relation",
            "family.firstName": "parents.firstName",
            "family.lastName": "parents.lastName",
            "family.occupation": "parents.occupation",
            "family.sibling": "siblings.relation",
            "family.brother": "siblings.relation", "family.sister": "siblings.relation",
            # WO-EX-SCHEMA-01 — aliases for new field families
            "children.firstName": "family.children.firstName",
            "children.lastName": "family.children.lastName",
            "children.dateOfBirth": "family.children.dateOfBirth",
            "children.placeOfBirth": "family.children.placeOfBirth",
            "children.relation": "family.children.relation",
            "children.preferredName": "family.children.preferredName",
            "children.birthOrder": "family.children.birthOrder",
            "childName": "family.children.firstName", "child_name": "family.children.firstName",
            "sonName": "family.children.firstName", "daughterName": "family.children.firstName",
            "son": "family.children.relation", "daughter": "family.children.relation",
            "spouse.firstName": "family.spouse.firstName",
            "spouse.lastName": "family.spouse.lastName",
            "spouseName": "family.spouse.firstName", "spouse_name": "family.spouse.firstName",
            "wifeName": "family.spouse.firstName", "husbandName": "family.spouse.firstName",
            "wife": "family.spouse.firstName", "husband": "family.spouse.firstName",
            "marriageDate": "family.marriageDate", "marriage_date": "family.marriageDate",
            "marriagePlace": "family.marriagePlace", "marriage_place": "family.marriagePlace",
            "grandchildren.firstName": "family.grandchildren.firstName",
            "grandchildName": "family.grandchildren.firstName",
            "residence": "residence.place", "lived": "residence.place",
            "residence.address": "residence.place",
            # Education
            "school": "education.schooling", "college": "education.higherEducation",
            "firstJob": "education.earlyCareer", "first_job": "education.earlyCareer",
            "career": "education.careerProgression",
            # Memory paths
            "memory": "earlyMemories.firstMemory", "firstMemory": "earlyMemories.firstMemory",
            "childhood": "earlyMemories.firstMemory",
            # WO-EX-CLAIMS-01: LLM-invented family.siblings.* → siblings.*
            # The LLM frequently prepends "family." to sibling paths.
            "family.siblings.firstName": "siblings.firstName",
            "family.siblings.lastName": "siblings.lastName",
            "family.siblings.relation": "siblings.relation",
            "family.siblings.birthOrder": "siblings.birthOrder",
            "family.siblings.uniqueCharacteristics": "siblings.uniqueCharacteristics",
            # WO-EX-CLAIMS-01: LLM-invented parents.parent* → parents.*
            "parents.parentFirstName": "parents.firstName",
            "parents.parentRelation": "parents.relation",
            "parents.parentLastName": "parents.lastName",
            "parents.parentOccupation": "parents.occupation",
            # WO-EX-CLAIMS-01: LLM-invented education.work* → education.careerProgression
            "education.workHistory": "education.careerProgression",
            "education.workStartYear": "education.careerProgression",
            "education.career": "education.careerProgression",
            "education.job": "education.earlyCareer",
            # WO-EX-CLAIMS-01: LLM-invented ethnicity/heritage → earlyMemories
            "parents.ethnicity": "earlyMemories.significantEvent",
            "personal.ethnicity": "earlyMemories.significantEvent",
            "personal.heritage": "earlyMemories.significantEvent",
            "ancestors.familyName": "earlyMemories.significantEvent",
            "ancestors.placeOfBirth": "earlyMemories.significantEvent",
            # WO-EX-CLAIMS-01: LLM-invented fear/comfort → earlyMemories
            "earlyMemories.fear": "earlyMemories.significantEvent",
            "earlyMemories.comfort": "earlyMemories.significantEvent",
            # WO-EX-CLAIMS-01 batch 2: additional log-observed aliases
            # civic.* → laterYears (no civic section in schema)
            "civic.entryAge": "laterYears.significantEvent",
            "civic.service": "laterYears.significantEvent",
            "civic.role": "laterYears.significantEvent",
            # parents.sibling.* → parents.notableLifeEvents (lossy stopgap)
            "parents.sibling.firstName": "parents.notableLifeEvents",
            "parents.sibling.middleNames": "parents.notableLifeEvents",
            "parents.sibling.lastName": "parents.notableLifeEvents",
            "parents.sibling.relation": "parents.notableLifeEvents",
            "parents.sibling.birthLocation": "parents.notableLifeEvents",
            # parents.siblings.* (plural) — LLM uses both singular and plural
            "parents.siblings.firstName": "parents.notableLifeEvents",
            "parents.siblings.middleName": "parents.notableLifeEvents",
            "parents.siblings.lastName": "parents.notableLifeEvents",
            "parents.siblings.relation": "parents.notableLifeEvents",
            "parents.siblings.birthPlace": "parents.notableLifeEvents",
            "parents.siblings.birthOrder": "parents.notableLifeEvents",
            # parents.parentAttitude → parents.notableLifeEvents
            "parents.parentAttitude": "parents.notableLifeEvents",
            # family.siblings.dateOfBirth has no schema target — route to significantEvent
            "family.siblings.dateOfBirth": "earlyMemories.significantEvent",

            # ── WO-SCHEMA-02: Aliases for new field families ──────────────────
            # Grandparents — LLM may use family.grandparents.* or grandmother/grandfather
            "family.grandparents.firstName": "grandparents.firstName",
            "family.grandparents.lastName": "grandparents.lastName",
            "family.grandparents.maidenName": "grandparents.maidenName",
            "family.grandparents.birthPlace": "grandparents.birthPlace",
            "family.grandparents.side": "grandparents.side",
            "family.grandparents.ancestry": "grandparents.ancestry",
            "family.grandparents.memorableStory": "grandparents.memorableStory",
            "grandmother.firstName": "grandparents.firstName",
            "grandmother.lastName": "grandparents.lastName",
            "grandmother.maidenName": "grandparents.maidenName",
            "grandfather.firstName": "grandparents.firstName",
            "grandfather.lastName": "grandparents.lastName",
            "origins.grandparentName": "grandparents.firstName",
            "origins.ancestry": "grandparents.ancestry",
            # Military — LLM may use service.* or veteran.*
            "service.branch": "military.branch",
            "service.years": "military.yearsOfService",
            "service.rank": "military.rank",
            "service.location": "military.deploymentLocation",
            "veteran.branch": "military.branch",
            "veteran.years": "military.yearsOfService",
            "veteran.rank": "military.rank",
            "personal.militaryService": "military.branch",
            "laterYears.militaryService": "military.branch",
            # Faith — LLM may use religion.* or church.* or spirituality.*
            "religion.denomination": "faith.denomination",
            "religion.role": "faith.role",
            "church.denomination": "faith.denomination",
            "church.role": "faith.role",
            "spirituality.faith": "faith.denomination",
            "spirituality.values": "faith.values",
            "personal.faith": "faith.denomination",
            "personal.values": "faith.values",
            # Health — LLM may use medical.* or wellness.*
            "medical.condition": "health.majorCondition",
            "medical.diagnosis": "health.majorCondition",
            "medical.surgery": "health.milestone",
            "wellness.change": "health.lifestyleChange",
            "personal.health": "health.majorCondition",
            "laterYears.health": "health.majorCondition",
            # Community — LLM may use civic.* (already partially aliased above)
            "civic.organization": "community.organization",
            "civic.role": "community.role",
            "civic.years": "community.yearsActive",
            "volunteer.organization": "community.organization",
            "volunteer.role": "community.role",
            # Pets — LLM may use animals.* or pet.*
            "animals.name": "pets.name",
            "animals.species": "pets.species",
            "pet.name": "pets.name",
            "pet.species": "pets.species",
            "pet.notes": "pets.notes",
            # Travel — LLM may use trips.* or places.*
            "trips.destination": "travel.destination",
            "trips.purpose": "travel.purpose",
            "places.visited": "travel.destination",
            "hobbies.travel": "travel.significantTrip",
        }
        alias = _FIELD_ALIASES.get(base_path) or _FIELD_ALIASES.get(fp)
        if alias and alias in EXTRACTABLE_FIELDS:
            logger.info("[extract-validate] ALIAS: %r → %r", base_path, alias)
            base_path = alias
        else:
            logger.info("[extract-validate] REJECT: fieldPath %r (base=%r) not in EXTRACTABLE_FIELDS", fp, base_path)
            return None

    conf = item.get("confidence", 0.8)
    if not isinstance(conf, (int, float)):
        conf = 0.8
    conf = max(0.1, min(1.0, float(conf)))

    return {
        "fieldPath": base_path,
        "value": val,
        "confidence": round(conf, 2)
    }


# ── Rules-based extraction (fallback) ───────────────────────────────────────

# Date patterns
_DATE_FULL = re.compile(
    r'\b(?:born|birthday|date of birth)[^\d]*'
    r'(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})',
    re.IGNORECASE
)
_DATE_YEAR = re.compile(
    r'\b(?:born|birthday)\b[^.]{0,30}?\b((?:18|19|20)\d{2})\b',
    re.IGNORECASE
)

# Place patterns — v8.0 FIX: handle "grew up right there in Dartford", "lived in X"
# FIX: Added \b word boundaries to stop-words so "I" doesn't match inside "Island", etc.
# WO-EX-01: drop "lived" — it's residence semantics, not birth-place.
# Live example that triggered this fix: in School Years, narrator says
# "we lived in West Fargo in a trailer court" and the rules extractor
# slotted West Fargo into personal.placeOfBirth, contradicting his
# already-promoted Williston, North Dakota. "born/raised/grew up" still
# correlate with birth place strongly enough to keep; "lived" is too general.
_PLACE_BORN = re.compile(
    r'\b(?:born|raised|grew up)\s+(?:\w+\s+)*?(?:in|at|near)\s+'
    r'([A-Z][a-zA-Z\s,]+?)'
    r'(?:\.|,?\s+(?:(?:and|my|I|we|the|where|when)\b|\d))',
    re.IGNORECASE
)

# Name patterns
_NAME_FULL = re.compile(
    r"(?:my name is|I'm|I am|name was|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
    re.IGNORECASE
)

# FIX-6a: Parent name regex — limit to first name + at most 2 last name words.
# The old pattern used *? (lazy) which could still capture middle names when the
# lookahead didn't trigger soon enough. Limiting to {0,2} prevents this.
# "my father Walter Murray was..." → "Walter Murray" (not "Walter Fletcher Murray")
_PARENT_FATHER = re.compile(
    r'(?:my\s+(?:father|dad|papa|pop))\s+(?:(?:was|is|,)\s+)?([A-Z][a-z]+(?:\s+(?:Van\s+)?[A-Z][a-z]+){0,2}?)(?=\s+(?:was|is|had|who|and|worked|did|ran|taught|,)|[.,]|\s*$)',
    re.IGNORECASE
)
_PARENT_MOTHER = re.compile(
    r'(?:my\s+(?:mother|mom|mama|ma|mum))\s+(?:(?:was|is|,)\s+)?([A-Z][a-z]+(?:\s+(?:Van\s+)?[A-Z][a-z]+){0,2}?)(?=\s+(?:was|is|had|who|and|worked|did|ran|taught|,)|[.,]|\s*$)',
    re.IGNORECASE
)

# Sibling patterns — v8.0 FIX: handle "a younger brother named Chris", "my older sister Jane"
# Supports optional "named/called/who" bridge words before the actual name.
_SIBLING = re.compile(
    r'(?:(?:my|an?)\s+(?:\w+\s+)*?(?:brother|sister|sibling))\s+(?:(?:named|called|who\s+was)\s+)?([A-Z][a-z]+)',
    re.IGNORECASE
)
_SIBLING_NOT_NAME = {"named", "called", "who", "was", "is", "had", "and", "the", "that", "but", "in", "at", "from", "with", "about"}

# FIX-5: Sibling list patterns — handle coordinated pairs and comma-separated lists.
# Matches patterns like: "brothers Hi, Joe, and Harry", "my brother Roger and my sister Mary"
# FIX-5d: Require either 'my' prefix for singular OR plural form to prevent
# false matches like "sister Dorothy, and" being treated as a name list.
_SIBLING_LIST = re.compile(
    r'(?:my\s+(?:brothers?|sisters?|siblings?)|(?:brothers|sisters|siblings))\s+'
    r'(?:(?:named|called|were|,|:)\s+)*'
    r'([A-Z][a-z]+(?:(?:\s*,?\s+and\s+|\s*,\s*)[A-Z][a-z]+)+)',
    re.IGNORECASE
)
# Matches coordinated pairs: "my brother Roger and my sister Mary"
_SIBLING_PAIR = re.compile(
    r'my\s+(?:\w+\s+)?(brother|sister)\s+(?:(?:named|called)\s+)?([A-Z][a-z]+)\s+and\s+my\s+(?:\w+\s+)?(brother|sister)\s+(?:(?:named|called)\s+)?([A-Z][a-z]+)',
    re.IGNORECASE
)

# Occupation patterns — v8.0 FIX: also match "was a PE teacher", "was a hairdresser"
_OCCUPATION = re.compile(
    r'(?:(?:he|she|father|mother|dad|mom|mum)\s+(?:was|worked as|did|ran)\s+(?:a\s+)?)([\w\s]+?)(?:\.|,|\s+(?:in|and|for|at|who))',
    re.IGNORECASE
)
# v8.0: Also match "father/mother [Name] was a [occupation]" pattern
# FIX-6c: Use (?:\w+\s+){1,3} to handle multi-word names like "Walter Barker"
# but cap at 3 words to prevent greedy consumption of the entire sentence
# (e.g. "father Walter Barker was ... and my mother Mary Van Horne was ...")
_PARENT_OCCUPATION = re.compile(
    r'(?:my\s+(?:father|dad|papa|pop|mother|mom|mama|ma|mum))\s+(?:\w+\s+){1,3}(?:was|is|worked as)\s+(?:a\s+|an\s+)?([\w\s]+?)(?:\.|,|\s+(?:and|who|in))',
    re.IGNORECASE
)


# WO-EX-01 / WO-EX-01B / WO-EX-01C: birth-context era guard.
#
# Sections in which the narrator is plausibly giving their OWN birth info.
# Outside these sections, a `personal.placeOfBirth` or `personal.dateOfBirth`
# extraction is almost always a false positive (residence-during-life, a
# child's birth date mentioned in passing, etc.).
#
# WO-EX-01C (April 2026 production bug): dropped the pre-existing `None`
# entry because the *absence* of a section signal was letting everything
# through (frontend not always sends current_section). Callers that truly
# don't know the section now get the strict filter — this is the safer
# default given the live bug: "we lived in west Fargo in a trailer court"
# → placeOfBirth=west_Fargo.
#
# Also dropped the phase-based escape hatch. Phase "pre_school" used to
# return True here (is_birth_relevant_phase), which meant discussing any
# kindergarten-era memory re-opened the birth-field spigot. Phase is now
# advisory at the router level only and does NOT relax this guard.
_BIRTH_CONTEXT_SECTIONS = {
    "early_childhood",
    "earliest_memories",
    "personal",
    "personal_information",
}

# Fields the era guard filters. The LLM may confidently produce these from
# residence-during-life statements ("we lived in X"); outside birth context
# those are false positives.
_BIRTH_FIELD_PATHS = {
    "personal.placeOfBirth",
    "personal.dateOfBirth",
}

# WO-EX-01C: sanity blacklist for placeOfBirth values. The LLM occasionally
# extracts fragments like "april" from "born in april 10 2002" and proposes
# them as placeOfBirth. Months (full and common abbreviations) are never
# valid placeOfBirth values. Expand as other false-positive tokens surface.
_MONTH_NAMES = frozenset({
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "may.", "jun", "jul", "aug",
    "sep", "sept", "oct", "nov", "dec",
})


# WO-EX-01C: third-person / family-member subject patterns. If any match
# the answer, the `born` signal is almost certainly about SOMEONE ELSE
# (child, parent, sibling, spouse) — narrator-identity fields must not be
# proposed in that context.
_NON_NARRATOR_SUBJECT_PATTERNS = [
    r"\bhe was born\b",
    r"\bshe was born\b",
    r"\bhe's born\b",
    r"\bshe's born\b",
    r"\bmy son was born\b",
    r"\bmy daughter was born\b",
    r"\bmy child was born\b",
    r"\bour son was born\b",
    r"\bour daughter was born\b",
    r"\bhis birthday\b",
    r"\bher birthday\b",
    r"\bmy son's birthday\b",
    r"\bmy daughter's birthday\b",
    r"\bmy son\b",
    r"\bmy daughter\b",
    r"\bmy child\b",
    r"\bmy kids?\b",
    r"\bmy baby\b",
    r"\bour son\b",
    r"\bour daughter\b",
    r"\bmy father\b",
    r"\bmy mother\b",
    r"\bmy dad\b",
    r"\bmy mom\b",
    r"\bmy papa\b",
    r"\bmy mama\b",
    r"\bmy brother\b",
    r"\bmy sister\b",
    r"\bmy sibling\b",
    r"\bmy wife\b",
    r"\bmy husband\b",
    r"\bmy spouse\b",
    r"\bmy partner\b",
    r"\bmy grand(?:mother|father|ma|pa|son|daughter|child|kid)\b",
]

# WO-EX-01C: first-person narrator birth signals. An explicit claim of the
# narrator's own birth overrides ambiguous third-person references and
# lets identity-field extractions survive the subject filter.
_NARRATOR_BIRTH_SIGNALS = [
    r"\bi was born\b",
    r"\bi'm born\b",  # speech-recognition artifact
    r"\bi was born on\b",
    r"\bi was born in\b",
    r"\bmy birthday is\b",
    r"\bmy date of birth is\b",
    # WO-EX-CLAIMS-01: narrator identity signals (not birth-specific)
    # "I was the youngest of three boys" is a narrator identity statement
    # even when the answer also mentions "my mom" / "my dad".
    r"\bi was the (?:youngest|oldest|eldest|middle|only)\b",
    r"\bi(?:'m| am) the (?:youngest|oldest|eldest|middle|only)\b",
    r"\bi was (?:first|second|third|fourth|fifth|last)[- ]born\b",
    r"\bi was number \d\b",
    r"\bi grew up\b",
    r"\bi was raised\b",
]


def _is_birth_context(
    current_section: Optional[str],
    current_phase: Optional[str] = None,  # kept for signature compat; not used
) -> bool:
    """True when the narrator is plausibly discussing their OWN birth-era memories.

    WO-EX-01C: SECTION-ONLY. Previous versions consulted current_phase and
    treated None-section as permissive; both behaviors were the root cause
    of the 'west Fargo → placeOfBirth' production bug. The second argument
    is preserved for callers that still pass it, but has no effect.
    """
    if not current_section:
        return False  # strict default — no section means no birth context
    return current_section.lower() in _BIRTH_CONTEXT_SECTIONS


def _answer_has_explicit_birth_phrase(answer: str) -> bool:
    """True iff the raw answer unambiguously uses the word 'born' as a birth marker.

    Used by _apply_birth_context_filter to decide whether to run the subject
    guard branch on items even outside a birth-context section. The subject
    guard then gates whether the narrator is actually the subject.
    """
    if not answer:
        return False
    return bool(re.search(r"\bborn\b", answer, re.IGNORECASE))


def _subject_is_narrator_context(answer: str) -> bool:
    """WO-EX-01C: Return True when the sentence appears to be about the
    NARRATOR, not a child/parent/other family member.

    Positive-first conservative semantics:
      1. explicit 1st-person birth signals → True (allow narrator identity)
      2. explicit 3rd-person / family-member patterns → False (strip identity)
      3. generic 'born' without narrator signal → False (ambiguous, strip)
      4. no birth claim either way → True (nothing to gate)

    False negatives here are safer than corrupting narrator DOB/POB, so the
    ambiguous-'born' case defaults to False.
    """
    if not answer:
        return False
    text = answer.lower()

    # Strong narrator signals — these override everything else
    for pat in _NARRATOR_BIRTH_SIGNALS:
        if re.search(pat, text, re.IGNORECASE):
            return True

    # Strong non-narrator signals
    for pat in _NON_NARRATOR_SUBJECT_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return False

    # Generic 'born' without narrator signal is too risky
    if re.search(r"\bborn\b", text, re.IGNORECASE):
        return False

    # No explicit birth claim either way
    return True


def _apply_narrator_identity_subject_filter(
    items: List[dict],
    answer: str,
) -> List[dict]:
    """WO-EX-01C: Drop narrator-identity field proposals when the answer is
    plausibly about SOMEONE ELSE.

    Protects the full PROTECTED_IDENTITY_FIELDS set (fullName, preferredName,
    dateOfBirth, placeOfBirth, birthOrder). Catches cases like:
        'my youngest son Cole ... he was born April 10 2002'
    where the extractor would otherwise map the child's birth facts onto
    the narrator's canonical identity.

    Applied to both LLM and rules paths. Complementary to the section-based
    birth-context filter — one gates on section, the other on subject.
    """
    if not items:
        return items
    if _subject_is_narrator_context(answer):
        return items
    dropped = [it for it in items
               if it.get("fieldPath") in PROTECTED_IDENTITY_FIELDS]
    if dropped:
        try:
            logger.info(
                "[extract][subject-filter] stripping %d narrator-identity item(s) "
                "from non-narrator context: %s",
                len(dropped),
                [(it.get("fieldPath"), it.get("value")) for it in dropped],
            )
        except Exception:
            pass
    return [it for it in items
            if it.get("fieldPath") not in PROTECTED_IDENTITY_FIELDS]


def _apply_birth_context_filter(
    items: List[dict],
    current_section: Optional[str],
    answer: str,
    current_phase: Optional[str] = None,
) -> List[dict]:
    """WO-EX-01C: section-gated birth filter, layered with the
    narrator-identity subject filter on EVERY branch.

    Defense-in-depth:
      - In a birth-context section: subject filter still runs so a child's
        birth mentioned during personal_information doesn't pollute the
        narrator's canonical DOB.
      - Outside a birth-context section, with 'born' in the answer:
        subject filter decides whether the narrator is the subject. If
        not, identity fields are stripped.
      - Outside a birth-context section, no 'born' phrase: birth fields
        stripped wholesale; subject filter also runs on the remainder
        to catch any non-birth personal-identity leakage.
    """
    if _is_birth_context(current_section, current_phase):
        # Even in birth-era context, still do NOT allow narrator identity
        # fields when the sentence is explicitly about someone else.
        return _apply_narrator_identity_subject_filter(items, answer)

    if _answer_has_explicit_birth_phrase(answer):
        # 'born' alone is NOT enough — could be talking about a child.
        # Only allow if the narrator is plausibly the subject.
        return _apply_narrator_identity_subject_filter(items, answer)

    # Outside birth context AND no explicit 'born' → strip birth-field items
    dropped = [it for it in items if it.get("fieldPath") in _BIRTH_FIELD_PATHS]
    if dropped:
        try:
            logger.info(
                "[extract][WO-EX-01C] stripping %d birth-field item(s) outside birth context "
                "(section=%s, phase=%s): %s",
                len(dropped), current_section, current_phase,
                [(it.get("fieldPath"), it.get("value")) for it in dropped],
            )
        except Exception:
            pass
    filtered = [it for it in items if it.get("fieldPath") not in _BIRTH_FIELD_PATHS]
    return _apply_narrator_identity_subject_filter(filtered, answer)


def _apply_month_name_sanity(items: List[dict]) -> List[dict]:
    """WO-EX-01C: drop placeOfBirth extractions whose value is just a
    month name. Catches LLM mistakes like parsing 'born in april 10 2002'
    as placeOfBirth=april.
    """
    out = []
    for it in items:
        if it.get("fieldPath") == "personal.placeOfBirth":
            val = str(it.get("value", "")).strip().lower().rstrip(",. ")
            if val in _MONTH_NAMES:
                try:
                    logger.info(
                        "[extract][WO-EX-01C] dropping placeOfBirth=%r (month-name sanity check)",
                        it.get("value"),
                    )
                except Exception:
                    pass
                continue
        out.append(it)
    return out


# ── WO-EX-01D: field-value sanity blacklists ────────────────────────────────
# Tactical pre-claims-layer patch. Catches the worst token-level extraction
# artifacts that reach shadow review when the LLM mis-parses compound phrases.
#
# Live cases this was built against (2026-04-15 Chris session):
#   "my dad Stanley ND"  → extracted parents.firstName=Stanley, lastName=ND
#   "mother and dad"     → extracted parents.firstName=and, lastName=dad
#
# This is a band-aid, not a fix. The real solution is claim-level extraction
# (WO-CLAIMS-01). Until that lands, these filters stop the worst fragments
# from reaching the Approve/Reject UI and misleading operators.

# US states, territories, and DC — never valid as a lastName.
_US_STATE_ABBREVIATIONS = frozenset({
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc", "pr", "vi", "gu", "as", "mp",
})

# Stopwords, pronouns, relation-words — never valid as a firstName.
# If the LLM tokenizes "my mom Janice" into [firstName=my, firstName=mom,
# firstName=Janice], only Janice survives this gate.
_FIRSTNAME_STOPWORDS = frozenset({
    # Articles & connectives
    "a", "an", "the", "and", "or", "but", "if", "so", "that", "this",
    # Pronouns
    "i", "he", "she", "it", "we", "they", "you",
    # Possessives
    "my", "our", "your", "their", "his", "her", "its",
    # Relation words
    "mom", "mother", "mama", "mum", "ma",
    "dad", "father", "papa", "pop",
    "brother", "sister", "sibling",
    "son", "daughter", "child", "kid", "baby",
    "wife", "husband", "spouse", "partner",
    "grandma", "grandpa", "grandfather", "grandmother", "granddad",
    "uncle", "aunt", "cousin", "nephew", "niece",
    # Common filler / linking verbs that shouldn't surface as names
    "was", "is", "born", "named", "called", "said", "told", "been",
})


def _apply_field_value_sanity(items: List[dict]) -> List[dict]:
    """WO-EX-01D: drop fragment-level mis-extractions on known-bad patterns.

    Rules:
      - any *.lastName field whose value is a US state abbreviation is
        almost always a place-fragment leak ('Stanley, ND' → lastName=ND)
      - any *.firstName field whose value is a pronoun, article, possessive,
        relation-word, or stopword is a token-split artifact ('and', 'mom')

    Applied on both LLM and rules paths. Tactical — real fix is the claims
    layer (WO-CLAIMS-01).
    """
    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        raw = str(it.get("value", ""))
        normalized = raw.strip().strip(".,;:'\"").lower()
        # For state-abbr check only, collapse interior dots ('N.D.' → 'nd').
        # Done locally — we don't want to strip dots globally and break
        # hypothetical abbreviations elsewhere.
        collapsed = normalized.replace(".", "")

        if fp.endswith(".lastName") and collapsed in _US_STATE_ABBREVIATIONS:
            try:
                logger.info(
                    "[extract][WO-EX-01D] dropping %s=%r (US state abbreviation)",
                    fp, raw,
                )
            except Exception:
                pass
            continue

        if fp.endswith(".firstName") and normalized in _FIRSTNAME_STOPWORDS:
            try:
                logger.info(
                    "[extract][WO-EX-01D] dropping %s=%r (stopword / relation / pronoun)",
                    fp, raw,
                )
            except Exception:
                pass
            continue

        out.append(it)
    return out


# ── WO-EX-CLAIMS-02: quick-win post-extraction validators ─────────────────
# Three guardrails that reject clearly-bad items before they reach shadow
# review or the claims layer. Gated behind HORNELORE_CLAIMS_VALIDATORS flag
# (default ON — these are safe to run always).
#
# 1. Value-shape rejection — connector words, bare fragments, sub-3-char
#    narrative values
# 2. Relation allowlist — enumerated valid values for *.relation fields
# 3. Confidence floor — auto-reject items below 0.5

_RELATION_ALLOWLIST = frozenset({
    # Parent/child
    "son", "daughter", "child", "children",
    "mother", "father", "parent", "mom", "dad",
    # Siblings
    "brother", "sister", "sibling", "half-brother", "half-sister",
    "stepbrother", "stepsister", "stepsibling",
    # Grandparents
    "grandmother", "grandfather", "grandparent", "grandma", "grandpa",
    # Extended family
    "uncle", "aunt", "cousin", "nephew", "niece",
    # In-laws
    "mother-in-law", "father-in-law", "sister-in-law", "brother-in-law",
    "son-in-law", "daughter-in-law",
    # Step relations
    "stepmother", "stepfather", "stepson", "stepdaughter",
    # Spouse/partner
    "wife", "husband", "spouse", "partner", "ex-wife", "ex-husband",
    # Great-grandparents
    "great-grandmother", "great-grandfather",
})

# Connector words and sentence fragments that appear as field values when the
# LLM mis-tokenizes compound sentences. These are never valid field values
# for any field, period.
_VALUE_GARBAGE_WORDS = frozenset({
    "then", "and", "or", "but", "the", "a", "an", "of", "in", "to",
    "for", "with", "from", "at", "by", "on", "so", "if", "as", "that",
    "this", "also", "just", "too", "very", "really", "yeah", "yes", "no",
    "not", "was", "were", "is", "are", "been", "be", "had", "has", "have",
    "do", "did", "does", "will", "would", "could", "should",
    "kids", "ones", "them", "things",
})

# Minimum confidence threshold. Items below this are almost always
# hallucinations or low-signal guesses.
_CONFIDENCE_FLOOR = 0.5

# Minimum value length for narrative/suggest_only fields. Fields that hold
# descriptive text (not names, dates, or codes) should have meaningful content.
# Name fields and short-value fields are exempt.
_SHORT_VALUE_EXEMPT_SUFFIXES = frozenset({
    "firstName", "lastName", "middleName", "maidenName", "nickname",
    "dateOfBirth", "dateOfDeath", "birthYear", "deathYear",
    "birthOrder", "gender", "relation", "branch", "denomination",
    "rank", "status", "species", "type", "yearEnlisted", "yearDischarged",
    "yearStarted", "yearEnded", "startYear", "endYear",
    "placeOfBirth", "placeOfDeath", "state", "country", "city", "location",
})


def _apply_claims_value_shape(items: List[dict]) -> List[dict]:
    """WO-EX-CLAIMS-02 validator 1: reject garbage connector words and
    bare fragments that leak from compound-sentence mis-parsing.

    Also rejects sub-3-character values for narrative fields (but exempts
    name, date, and code fields where short values are valid).
    """
    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        raw = str(it.get("value", ""))
        normalized = raw.strip().strip(".,;:'\"").lower()

        # Reject universal garbage words
        if normalized in _VALUE_GARBAGE_WORDS:
            try:
                logger.info(
                    "[extract][WO-CLAIMS-02] dropping %s=%r (garbage connector word)",
                    fp, raw,
                )
            except Exception:
                pass
            continue

        # Reject sub-3-char values for non-exempt fields
        suffix = fp.rsplit(".", 1)[-1] if "." in fp else fp
        if suffix not in _SHORT_VALUE_EXEMPT_SUFFIXES and len(normalized) < 3:
            try:
                logger.info(
                    "[extract][WO-CLAIMS-02] dropping %s=%r (too short for narrative field)",
                    fp, raw,
                )
            except Exception:
                pass
            continue

        out.append(it)
    return out


def _apply_claims_relation_allowlist(items: List[dict]) -> List[dict]:
    """WO-EX-CLAIMS-02 validator 2: reject extracted .relation values that
    aren't in the known relation vocabulary.

    This catches LLM artifacts like relation='then', relation='and',
    relation='kids' that leak from compound sentence parsing.

    Includes a normalizer that converts plural/informal relation words to
    their canonical singular form before checking the allowlist.
    """
    # Normalize plural/informal → canonical singular before allowlist check
    _RELATION_NORMALIZER = {
        "brothers": "brother", "sisters": "sister", "siblings": "sibling",
        "kids": "child", "sons": "son", "daughters": "daughter",
        "parents": "parent", "mothers": "mother", "fathers": "father",
        "uncles": "uncle", "aunts": "aunt", "cousins": "cousin",
        "nephews": "nephew", "nieces": "niece",
        "grandmothers": "grandmother", "grandfathers": "grandfather",
        "grandparents": "grandparent",
    }

    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        if fp.endswith(".relation"):
            raw = str(it.get("value", ""))
            normalized = raw.strip().strip(".,;:'\"").lower()
            # Try plural → singular normalization first
            canonical = _RELATION_NORMALIZER.get(normalized, normalized)
            if canonical != normalized:
                logger.info("[extract][WO-CLAIMS-02] relation normalized: %r → %r", normalized, canonical)
                it = dict(it)  # shallow copy to avoid mutating original
                it["value"] = canonical.capitalize()
                normalized = canonical
            # Normalize hyphens and spaces for matching
            normalized_check = normalized.replace(" ", "-")
            if normalized_check not in _RELATION_ALLOWLIST and normalized not in _RELATION_ALLOWLIST:
                try:
                    logger.info(
                        "[extract][WO-CLAIMS-02] dropping %s=%r (not in relation allowlist)",
                        fp, raw,
                    )
                except Exception:
                    pass
                continue
        out.append(it)
    return out


def _apply_claims_confidence_floor(items: List[dict]) -> List[dict]:
    """WO-EX-CLAIMS-02 validator 3: reject items below the confidence floor.

    Items with confidence < 0.5 are almost always hallucinations or
    low-signal guesses. The threshold is deliberately conservative — 0.5
    is low enough that legitimate extractions rarely fall below it, but
    high enough to catch the worst LLM garbage.
    """
    out = []
    for it in items:
        conf = it.get("confidence")
        if conf is not None and isinstance(conf, (int, float)) and conf < _CONFIDENCE_FLOOR:
            try:
                logger.info(
                    "[extract][WO-CLAIMS-02] dropping %s=%r confidence=%.2f (below floor %.2f)",
                    it.get("fieldPath"), it.get("value"), conf, _CONFIDENCE_FLOOR,
                )
            except Exception:
                pass
            continue
        out.append(it)
    return out


# ── Semantic rerouter — fix valid-but-wrong fieldPath choices ──────────────
#
# The LLM sometimes picks a valid fieldPath from the wrong family.
# These rerouters fire only when ALL THREE conditions agree:
#   1. section context matches the reroute scenario
#   2. the chosen fieldPath matches the known misroute pattern
#   3. lexical cues in the answer or value confirm the reroute
# This keeps rerouting surgical — no broad fuzzy matching.

# Section keyword sets for context matching
_SECTION_PETS = frozenset({"pets", "animals", "childhood_pets", "family_pets", "pets_and_animals"})
_SECTION_SIBLINGS = frozenset({
    "early_caregivers", "siblings", "family_of_origin", "sibling_dynamics",
    "developmental_foundations", "family_dynamics",
})
_SECTION_BIRTH = frozenset({
    "origin_point", "birth", "birthplace", "origins", "developmental_foundations",
})

# Lexical cue patterns
_PET_CUES = re.compile(
    r'\b(?:dog|cat|horse|pony|bird|fish|rabbit|hamster|turtle|parrot|kitten|puppy'
    r'|golden retriever|labrador|poodle|collie|shepherd|beagle|terrier|spaniel'
    r'|tabby|siamese|persian|named\s+\w+|pet|pets|animal|animals)\b',
    re.IGNORECASE,
)
_SIBLING_CUES = re.compile(
    r'\b(?:brother|sister|brothers|sisters|sibling|siblings'
    r'|older brother|younger brother|older sister|younger sister'
    r'|big brother|big sister|little brother|little sister'
    r'|twin brother|twin sister)\b',
    re.IGNORECASE,
)
_BIRTH_CUES = re.compile(
    r'\b(?:born in|born on|born at|birthplace|place of birth|came into the world'
    r'|where I was born|where .{0,10} was born|I was born)\b',
    re.IGNORECASE,
)
_CAREER_DURATION_CUES = re.compile(
    r'\b(?:for \d+ years|for (?:twenty|thirty|forty|fifty)\S* years'
    r'|since \d{4}|worked there (?:for|until)|until (?:I )?retire'
    r'|spent \d+ years|spent (?:twenty|thirty|forty|fifty)\S* years'
    r'|over \d+ years|over (?:twenty|thirty|forty|fifty)\S* years'
    r'|almost \d+ years|almost (?:twenty|thirty|forty|fifty)\S* years'
    r'|career spanned|until retirement|retired from|retiring from'
    r'|whole career|entire career|long career|worked (?:there |here )?my whole)\b',
    re.IGNORECASE,
)

# Path mapping: (source_prefix, target_prefix) for each rerouter
_PETS_REMAP = {
    "hobbies.hobbies": "pets.notes",  # generic hobby → pet notes
    "hobbies.personalChallenges": "pets.notes",
}
_SIBLINGS_REMAP = {
    "family.children.relation": "siblings.relation",
    "family.children.firstName": "siblings.firstName",
    "family.children.lastName": "siblings.lastName",
    "family.children.birthOrder": "siblings.birthOrder",
    "family.children.preferredName": "siblings.uniqueCharacteristics",
    "family.children.dateOfBirth": "siblings.uniqueCharacteristics",
    "family.children.placeOfBirth": "siblings.uniqueCharacteristics",
}


def _section_matches(current_section: Optional[str], keywords: frozenset) -> bool:
    """Check if the current interview section matches any keyword set."""
    if not current_section:
        return False
    section_lower = current_section.lower().replace("-", "_").replace(" ", "_")
    return any(kw in section_lower for kw in keywords)


def _apply_semantic_rerouter(
    items: List[dict],
    answer: str,
    current_section: Optional[str] = None,
) -> List[dict]:
    """Reroute valid-but-wrong fieldPaths using section + path + lexical evidence.

    Each reroute requires all three signals to agree. No reroute happens
    on section context alone or lexical cues alone.
    """
    if not items:
        return items

    answer_lower = answer.lower()
    rerouted = []

    for it in items:
        fp = it.get("fieldPath", "")
        val = str(it.get("value", ""))
        combined_text = answer_lower + " " + val.lower()
        original_fp = fp

        # ── 1. Pets rerouter: hobbies.* → pets.* ────────────────────────
        if fp in _PETS_REMAP:
            if _section_matches(current_section, _SECTION_PETS) and _PET_CUES.search(combined_text):
                # Try to extract pet name and species from value
                new_fp = _PETS_REMAP[fp]
                logger.info("[extract][rerouter] pets: %s → %s (val=%r)", fp, new_fp, val[:60])
                it["fieldPath"] = new_fp

        # ── 2. Siblings rerouter: family.children.* → siblings.* ────────
        elif fp in _SIBLINGS_REMAP:
            if _section_matches(current_section, _SECTION_SIBLINGS) and _SIBLING_CUES.search(combined_text):
                new_fp = _SIBLINGS_REMAP[fp]
                logger.info("[extract][rerouter] siblings: %s → %s (val=%r)", fp, new_fp, val[:60])
                it["fieldPath"] = new_fp

        # ── 3. Birthplace rerouter: residence.place → personal.placeOfBirth ─
        elif fp == "residence.place":
            if _BIRTH_CUES.search(answer_lower):
                # Section context OR birth cues in the answer are enough here
                # because "born in X" is unambiguous regardless of section
                logger.info("[extract][rerouter] birthplace: residence.place → personal.placeOfBirth (val=%r)", val[:60])
                it["fieldPath"] = "personal.placeOfBirth"

        # ── 4. Career progression rerouter: earlyCareer → careerProgression ─
        elif fp == "education.earlyCareer":
            if _CAREER_DURATION_CUES.search(combined_text):
                logger.info("[extract][rerouter] career: education.earlyCareer → education.careerProgression (val=%r)", val[:60])
                it["fieldPath"] = "education.careerProgression"

        if it["fieldPath"] != original_fp:
            # Verify the rerouted path is valid
            if it["fieldPath"] not in EXTRACTABLE_FIELDS:
                logger.warning("[extract][rerouter] rerouted path %r not in EXTRACTABLE_FIELDS — reverting to %r",
                              it["fieldPath"], original_fp)
                it["fieldPath"] = original_fp

        rerouted.append(it)

    return rerouted


def _apply_negation_guard(items: List[dict], answer: str) -> List[dict]:
    """WO-EX-CLAIMS-02 validator 4: strip fields from categories the narrator
    explicitly denied.

    When the narrator says "I never served", "I didn't go to college",
    "I've been pretty healthy" etc., the LLM sometimes still emits fields
    for those categories. This validator detects denial patterns and removes
    any fields belonging to the denied category.
    """
    if not items or not answer:
        return items

    lower = answer.lower()

    # Map: (denial regex, set of field prefixes to strip)
    _DENIAL_PATTERNS = [
        # Military negation
        (re.compile(r'\b(?:never served|didn\'?t serve|did not serve|wasn\'?t in the (?:military|service|army|navy|marines)|no military|not military)\b', re.IGNORECASE),
         {"military.branch", "military.rank", "military.yearsOfService", "military.deploymentLocation"}),
        # Health negation — "been pretty healthy", "never had health problems"
        (re.compile(r'\b(?:(?:been |was |am )?(?:pretty |very |always )?healthy|never (?:had|been) (?:any |serious )?(?:health|medical)|no (?:health|medical) (?:issues|problems|conditions))\b', re.IGNORECASE),
         {"health.majorCondition", "health.milestone", "health.lifestyleChange"}),
        # Education negation
        (re.compile(r'\b(?:never went to college|didn\'?t go to college|did not go to college|didn\'?t attend college|no college|never attended college)\b', re.IGNORECASE),
         {"education.higherEducation"}),
    ]

    denied_fields = set()
    for pattern, fields in _DENIAL_PATTERNS:
        if pattern.search(lower):
            denied_fields.update(fields)
            logger.info("[extract][negation-guard] denial detected: stripping %s", fields)

    if not denied_fields:
        return items

    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        if fp in denied_fields:
            logger.info("[extract][negation-guard] dropping %s=%r (narrator denied this category)", fp, it.get("value"))
            continue
        out.append(it)
    return out


def _apply_claims_validators(items: List[dict], answer: str = "") -> List[dict]:
    """WO-EX-CLAIMS-02: apply all validators in sequence.
    Flag-gated behind HORNELORE_CLAIMS_VALIDATORS (default ON).
    """
    try:
        from .. import flags as _flags
        if not _flags.claims_validators_enabled():
            return items
    except Exception:
        return items  # if flag module fails, skip gracefully

    before = len(items)
    items = _apply_claims_value_shape(items)
    items = _apply_claims_relation_allowlist(items)
    items = _apply_claims_confidence_floor(items)
    items = _apply_negation_guard(items, answer)
    dropped = before - len(items)
    if dropped:
        logger.info("[extract][WO-CLAIMS-02] validators dropped %d of %d items", dropped, before)
    return items


def _extract_via_rules(
    answer: str,
    current_section: Optional[str],
    current_target: Optional[str],
    current_phase: Optional[str] = None,
) -> List[dict]:
    """Fallback: regex-based extraction when LLM is unavailable.

    WO-LIFE-SPINE-04: current_phase (from life spine) now takes priority
    over current_section for the birth-context guard. Falls back to
    section-based logic when phase is absent.
    """
    items = []
    in_birth_context = _is_birth_context(current_section, current_phase)

    # Full name
    m = _NAME_FULL.search(answer)
    if m:
        items.append({"fieldPath": "personal.fullName", "value": m.group(1).strip(), "confidence": 0.85})

    # Date of birth — only fire when we're plausibly talking about birth
    if in_birth_context:
        m = _DATE_FULL.search(answer)
        if m:
            items.append({"fieldPath": "personal.dateOfBirth", "value": m.group(0).split("born")[-1].strip().strip(",. "), "confidence": 0.85})
        elif _DATE_YEAR.search(answer):
            m = _DATE_YEAR.search(answer)
            items.append({"fieldPath": "personal.dateOfBirth", "value": m.group(1), "confidence": 0.7})

    # Place of birth — same era guard
    if in_birth_context:
        m = _PLACE_BORN.search(answer)
        if m:
            items.append({"fieldPath": "personal.placeOfBirth", "value": m.group(1).strip().rstrip(","), "confidence": 0.8})

    # Father
    m = _PARENT_FATHER.search(answer)
    if m:
        name = m.group(1).strip()
        items.append({"fieldPath": "parents.relation", "value": "Father", "confidence": 0.9})
        parts = name.split()
        items.append({"fieldPath": "parents.firstName", "value": parts[0], "confidence": 0.85})
        if len(parts) > 1:
            items.append({"fieldPath": "parents.lastName", "value": " ".join(parts[1:]), "confidence": 0.8})

    # Mother
    m = _PARENT_MOTHER.search(answer)
    if m:
        name = m.group(1).strip()
        items.append({"fieldPath": "parents.relation", "value": "Mother", "confidence": 0.9})
        parts = name.split()
        items.append({"fieldPath": "parents.firstName", "value": parts[0], "confidence": 0.85})
        if len(parts) > 1:
            items.append({"fieldPath": "parents.lastName", "value": " ".join(parts[1:]), "confidence": 0.8})

    # FIX-5: Sibling extraction — handle lists, pairs, and single siblings.
    sibling_items = []
    _sibling_extracted = False

    # Try coordinated pair first: "my brother Roger and my sister Mary"
    m_pair = _SIBLING_PAIR.search(answer)
    if m_pair:
        rel1 = m_pair.group(1).capitalize()
        name1 = m_pair.group(2).strip()
        rel2 = m_pair.group(3).capitalize()
        name2 = m_pair.group(4).strip()
        if name1.lower() not in _SIBLING_NOT_NAME:
            sibling_items.append({"fieldPath": "siblings.relation", "value": rel1, "confidence": 0.85})
            sibling_items.append({"fieldPath": "siblings.firstName", "value": name1, "confidence": 0.85})
        if name2.lower() not in _SIBLING_NOT_NAME:
            sibling_items.append({"fieldPath": "siblings.relation", "value": rel2, "confidence": 0.85})
            sibling_items.append({"fieldPath": "siblings.firstName", "value": name2, "confidence": 0.85})
        _sibling_extracted = True

    # Try comma/and-separated list: "brothers Hi, Joe, and Harry"
    if not _sibling_extracted:
        m_list = _SIBLING_LIST.search(answer)
        if m_list:
            names_str = m_list.group(1)
            # Parse comma/and-separated names
            # FIX-5b: Use ", and " as a single delimiter before plain "," or " and "
            # so that "Hi, Joe, and Harry" splits to ["Hi", "Joe", "Harry"]
            # instead of ["Hi", "Joe", "and Harry"] (where "and Harry" gets filtered).
            names = re.split(r'\s*,\s+and\s+|\s*,\s*|\s+and\s+', names_str)
            names = [n.strip() for n in names if n.strip() and n.strip()[0].isupper()]
            # Determine relation from the preceding word
            rel_match = re.search(r'(?:my\s+)?(?:\w+\s+)*(brothers?|sisters?|siblings?)', m_list.group(0), re.IGNORECASE)
            rel_word = (rel_match.group(1) if rel_match else "sibling").lower()
            if "brother" in rel_word:
                rel = "Brother"
            elif "sister" in rel_word:
                rel = "Sister"
            else:
                rel = "Sibling"
            for name in names:
                if name.lower() not in _SIBLING_NOT_NAME:
                    sibling_items.append({"fieldPath": "siblings.relation", "value": rel, "confidence": 0.85})
                    sibling_items.append({"fieldPath": "siblings.firstName", "value": name, "confidence": 0.85})
            if sibling_items:
                _sibling_extracted = True

    # Fallback: single/multiple sibling pattern via finditer
    # FIX-5c: Use finditer instead of search to catch ALL sibling mentions,
    # e.g. "a brother Roger and a sister Dorothy" yields both Roger and Dorothy.
    if not _sibling_extracted:
        for m in _SIBLING.finditer(answer):
            sib_name = m.group(1).strip()
            if sib_name.lower() not in _SIBLING_NOT_NAME:
                # Extract relation from THIS match's text only (not preceding context)
                match_text = m.group(0)
                rel_match = re.search(r'(brother|sister|sibling)', match_text, re.IGNORECASE)
                rel = rel_match.group(1).capitalize() if rel_match else "Sibling"
                sibling_items.append({"fieldPath": "siblings.relation", "value": rel, "confidence": 0.85})
                sibling_items.append({"fieldPath": "siblings.firstName", "value": sib_name, "confidence": 0.85})

    items.extend(sibling_items)

    # FIX-6b: Helper to strip article prefixes from occupations
    def _clean_occupation(val):
        val = val.strip()
        # Strip leading "a " or "an " article prefix
        val = re.sub(r'^(?:an?\s+)', '', val, flags=re.IGNORECASE)
        return val.strip()

    # FIX-4: Parent occupations — tag with _parentType so we can group with the correct parent.
    # This replaces the old approach of appending occupations after both parents' names,
    # which caused the frontend's duplicate-field detection to misassign them.
    father_occupation = None
    mother_occupation = None
    for occ_match in re.finditer(_PARENT_OCCUPATION, answer):
        occ_val = _clean_occupation(occ_match.group(1))
        parent_ctx = answer[max(0, occ_match.start()-30):occ_match.start()].lower()
        match_text = occ_match.group(0).lower()
        if any(w in parent_ctx or w in match_text for w in ["father", "dad", "papa", "pop"]):
            father_occupation = occ_val
        elif any(w in parent_ctx or w in match_text for w in ["mother", "mom", "mama", "ma", "mum"]):
            mother_occupation = occ_val

    # FIX-4: Reorder items so each parent's fields are contiguous (relation, firstName, lastName, occupation).
    # This ensures the frontend's duplicate-field counter bumps at the right time.
    reordered = []
    father_items = [i for i in items if i["fieldPath"].startswith("parents.") and i.get("_parentType") == "father"]
    mother_items = [i for i in items if i["fieldPath"].startswith("parents.") and i.get("_parentType") == "mother"]
    other_items = [i for i in items if not i["fieldPath"].startswith("parents.") or "_parentType" not in i]

    # Tag father/mother items from the name extraction above
    # The name extraction doesn't tag _parentType, so we need to split by discovery order:
    # First batch of parents.* items = father (if father was matched), second = mother
    parent_items = [i for i in items if i["fieldPath"].startswith("parents.")]
    non_parent_items = [i for i in items if not i["fieldPath"].startswith("parents.")]

    # Split parent items into father group and mother group
    father_group = []
    mother_group = []
    seen_relations = set()
    current_group = None
    for pi in parent_items:
        if pi["fieldPath"] == "parents.relation":
            val_lower = pi["value"].lower()
            if val_lower == "father":
                current_group = "father"
            elif val_lower == "mother":
                current_group = "mother"
        if current_group == "father":
            father_group.append(pi)
        elif current_group == "mother":
            mother_group.append(pi)

    # Append occupations to the correct parent group
    if father_occupation:
        father_group.append({"fieldPath": "parents.occupation", "value": father_occupation, "confidence": 0.8})
    if mother_occupation:
        mother_group.append({"fieldPath": "parents.occupation", "value": mother_occupation, "confidence": 0.8})

    # Rebuild items: non-parent first, then father group, then mother group
    items = non_parent_items + father_group + mother_group

    # If we have a current target and found nothing matching it, project the full answer
    if current_target and not any(i["fieldPath"] == current_target for i in items):
        base = re.sub(r'\[\d+\]', '', current_target)
        if base in EXTRACTABLE_FIELDS:
            items.append({
                "fieldPath": base,
                "value": answer.strip(),
                "confidence": 0.7
            })

    # WO-EX-01C: subject filter on the rules path too, so both extraction
    # routes behave the same when the answer is about a non-narrator subject
    # ('my son was born april 10 2002').
    return _apply_narrator_identity_subject_filter(items, answer)


# ── Repeatable field grouping ────────────────────────────────────────────────

def _group_repeatable_items(items: List[dict], answer: str = "") -> List[dict]:
    """Group repeatable fields by entity, using position-aware assignment.

    WO-EX-CLAIMS-01: Position-aware entity compiler.

    When the LLM extracts e.g. parents.firstName + parents.lastName for the
    same parent, they need the same entry index. The frontend handles indexing,
    but we group them so same-person fields travel together.

    Strategy for multi-entity sections:
      1. Find each firstName's character position in the narrator's answer.
      2. Find each non-name field's value position in the answer.
      3. Assign each non-name field to the entity whose firstName appears
         closest-before it in the answer text.
      4. Fall back to LLM output order when positions can't be resolved.
    """
    non_repeatable = []
    repeatable_groups: Dict[str, List[dict]] = {}  # section → [items]

    for item in items:
        meta = EXTRACTABLE_FIELDS.get(item["fieldPath"], {})
        section = meta.get("repeatable")
        if section:
            repeatable_groups.setdefault(section, []).append(item)
        else:
            non_repeatable.append(item)

    result = list(non_repeatable)
    answer_lower = answer.lower()

    for section, group in repeatable_groups.items():
        name_items = [i for i in group if i["fieldPath"].endswith(".firstName")]
        non_name_items = [i for i in group if not i["fieldPath"].endswith(".firstName")]

        if len(name_items) <= 1:
            # Single entity (or no name at all): all fields share one group
            group_id = f"{section}_0"
            for item in group:
                item["_repeatableGroup"] = group_id
            result.extend(group)
            continue

        # ── Multi-entity: position-aware assignment ──────────────────────
        # Step 1: locate each firstName in the answer text
        name_positions: List[tuple] = []  # (position, idx, name_value)
        for idx, ni in enumerate(name_items):
            name_val = ni["value"].lower()
            pos = answer_lower.find(name_val)
            name_positions.append((pos if pos >= 0 else idx * 10000, idx, ni["value"]))
            ni["_repeatableGroup"] = f"{section}_{idx}"

        # Sort by position so we know the textual order of names
        name_positions.sort(key=lambda x: x[0])
        # Build ordered list: (position_in_answer, group_idx)
        ordered_names = [(pos, idx) for pos, idx, _name in name_positions]

        logger.info("[extract][CLAIMS-01] Multi-entity grouping section=%s: %d names at positions %s",
                    section, len(name_positions),
                    [(n[2], n[0]) for n in name_positions])

        # Step 2: assign each non-name field to the nearest-preceding name
        for item in non_name_items:
            val_lower = item["value"].lower()
            val_pos = answer_lower.find(val_lower)

            if val_pos >= 0 and ordered_names:
                # Find the name whose position is closest-before (or at) this value
                best_idx = ordered_names[0][1]  # default: first name
                for name_pos, name_idx in ordered_names:
                    if name_pos <= val_pos:
                        best_idx = name_idx
                    else:
                        break  # names are sorted; no point continuing
                item["_repeatableGroup"] = f"{section}_{best_idx}"
            else:
                # Can't locate value in answer — fall back to LLM output order.
                # Assign to the last name item seen before this item in the
                # original LLM output sequence.
                last_seen_idx = 0
                for g_item in group:
                    if g_item is item:
                        break
                    if g_item in name_items:
                        last_seen_idx = name_items.index(g_item)
                item["_repeatableGroup"] = f"{section}_{last_seen_idx}"

            logger.debug("[extract][CLAIMS-01] %s=%r → pos=%d → group=%s",
                         item["fieldPath"], item["value"],
                         val_pos if val_pos >= 0 else -1,
                         item["_repeatableGroup"])

        result.extend(group)

    return result


# ── WO-EX-VALIDATE-01: age-math plausibility filter ─────────────────────────

def _fetch_dob_for_validation(person_id: Optional[str]) -> Optional[str]:
    """Return ISO DOB string from the narrator profile, or None if missing.

    Called only when HORNELORE_AGE_VALIDATOR is on. Failure-silent: if the
    profile lookup blows up for any reason, we return None and the
    validator short-circuits to 'ok'. Never raises.
    """
    if not person_id:
        return None
    try:
        from ..db import get_profile
        prof = get_profile(person_id) or {}
        blob = prof.get("profile_json") or {}
        # profile_json may be {profile: {basics: {...}}} or flat {basics: {...}}
        basics = ((blob.get("profile") or blob).get("basics")) or {}
        personal = ((blob.get("profile") or blob).get("personal")) or {}
        dob = basics.get("dateOfBirth") or personal.get("dateOfBirth") or ""
        return dob or None
    except Exception as e:
        logger.warning("[extract][validator] DOB lookup failed: %s", e)
        return None


def _apply_age_math_filter(
    items: List["ExtractedItem"],
    dob: Optional[str],
) -> List["ExtractedItem"]:
    """Run each item through life_spine.validator and drop 'impossible'
    entries. Remaining items are annotated with plausibility_* fields.

    Safe when dob is None — validator returns 'ok' with reason 'no dob'
    and items pass through unchanged.
    """
    if not items:
        return items
    try:
        from ..life_spine.validator import validate_fact
    except Exception as e:
        logger.error("[extract][validator] validator import failed: %s", e)
        return items

    surviving: List[ExtractedItem] = []
    dropped = 0
    for it in items:
        try:
            result = validate_fact(it.fieldPath, it.value, dob)
        except Exception as e:
            logger.warning("[extract][validator] validate_fact raised on %s=%r: %s",
                           it.fieldPath, it.value, e)
            surviving.append(it)
            continue

        if result.flag == "impossible":
            dropped += 1
            logger.info(
                "[extract][validator] DROP field=%s value=%r reason=%s age=%s",
                it.fieldPath, it.value, result.reason, result.age_at_event,
            )
            continue

        # Annotate ok / warn items so the frontend can surface a badge if desired
        it.plausibility_flag = result.flag
        it.plausibility_reason = result.reason
        it.plausibility_age = result.age_at_event
        surviving.append(it)

    if dropped:
        logger.info("[extract][validator] dropped=%d kept=%d", dropped, len(surviving))
    return surviving


# ── Main endpoint ────────────────────────────────────────────────────────────

@router.post("/extract-fields", response_model=ExtractFieldsResponse)
def extract_fields(req: ExtractFieldsRequest) -> ExtractFieldsResponse:
    """Extract multiple structured fields from a conversational answer."""
    answer = (req.answer or "").strip()
    if not answer:
        return ExtractFieldsResponse(items=[], method="fallback")

    # Try LLM extraction first
    logger.info("[extract] Attempting LLM extraction for person=%s, section=%s, target=%s",
                req.person_id[:8] if req.person_id else "?",
                req.current_section, req.current_target_path)
    llm_items, raw_output = _extract_via_llm(
        answer=answer,
        current_section=req.current_section,
        current_target=req.current_target_path,
    )

    # WO-EX-REROUTE-01: Semantic rerouter — fix valid-but-wrong fieldPaths
    # before validators run. Rerouter requires section + path + lexical evidence.
    if llm_items:
        llm_items = _apply_semantic_rerouter(llm_items, answer, req.current_section)

    # WO-EX-01C + WO-EX-01D: four-layer LLM output guard.
    #   1. birth-context filter    — section-gated + layered subject guard
    #                                (Bug A West-Fargo residence; Bug B
    #                                child-DOB contamination)
    #   2. month-name sanity       — drop placeOfBirth=month-name
    #   3. field-value sanity      — drop *.lastName=US-state-abbr and
    #                                *.firstName=stopword/pronoun/relation
    if llm_items:
        llm_items = _apply_birth_context_filter(
            llm_items,
            req.current_section,
            answer,
            current_phase=req.current_phase,
        )
        llm_items = _apply_month_name_sanity(llm_items)
        llm_items = _apply_field_value_sanity(llm_items)
        llm_items = _apply_claims_validators(llm_items, answer=answer)  # WO-EX-CLAIMS-02

    # WO: Summary line — log outcome at endpoint level
    _accepted = len(llm_items) if llm_items else 0
    _method = "llm" if llm_items else ("rules-fallback" if raw_output else "no-llm")
    logger.info("[extract][summary] llm_raw=%s accepted=%d method=%s",
                "present" if raw_output else "none", _accepted, _method)

    # Phase G: Load protected identity snapshot for conflict detection
    _protected_snapshot = {}
    if req.person_id:
        try:
            from ..db import get_narrator_state_snapshot
            snap = get_narrator_state_snapshot(req.person_id)
            _protected_snapshot = snap.get("protected_identity", {}) if snap else {}
        except Exception as e:
            logger.warning("[extract] Phase G: Could not load protected identity snapshot: %s", e)

    if llm_items:
        logger.info("[extract] LLM returned %d items", len(llm_items))
        # Add writeMode from our schema
        result_items = []
        for item in llm_items:
            meta = EXTRACTABLE_FIELDS.get(item["fieldPath"], {})
            write_mode = meta.get("writeMode", "suggest_only")

            # Phase G: Protected identity field conflict detection
            if item["fieldPath"] in PROTECTED_IDENTITY_FIELDS:
                canonical_val = _protected_snapshot.get(item["fieldPath"], "")
                if canonical_val and canonical_val.strip() and item["value"] != canonical_val:
                    write_mode = "suggest_only"
                    logger.warning(
                        "[extract] Phase G: Protected identity conflict for %s: canonical=%r extracted=%r — downgraded to suggest_only",
                        item["fieldPath"], canonical_val, item["value"],
                    )

            result_items.append(ExtractedItem(
                fieldPath=item["fieldPath"],
                value=item["value"],
                writeMode=write_mode,
                confidence=item["confidence"],
                source="backend_extract",
                extractionMethod="llm",
            ))

        # Group repeatable fields — FIX-4: preserve _repeatableGroup as repeatableGroup
        # WO-EX-CLAIMS-01: pass answer for position-aware entity grouping
        grouped = _group_repeatable_items([i.model_dump() for i in result_items], answer=answer)
        final_items = []
        for item in grouped:
            rg = item.pop("_repeatableGroup", None)
            ei = ExtractedItem(**item)
            ei.repeatableGroup = rg
            final_items.append(ei)

        # WO-EX-VALIDATE-01 — age-math plausibility filter. Flag-gated; off
        # by default. When on, fetches DOB once and drops temporally
        # impossible items, annotating survivors with plausibility_flag.
        try:
            from .. import flags as _flags
            if _flags.age_validator_enabled():
                _dob = _fetch_dob_for_validation(req.person_id)
                final_items = _apply_age_math_filter(final_items, _dob)
        except Exception as _e:
            logger.warning("[extract][validator] filter skipped (llm path): %s", _e)

        _record_metric("llm", parsed=len(llm_items), accepted=len(final_items), rejected=0)
        return ExtractFieldsResponse(
            items=final_items,
            method="llm",
            raw_llm_output=raw_output,
        )

    # Fallback: rules-based extraction (still include raw_llm_output for debugging)
    logger.warning("[extract] LLM extraction returned no items (raw_output=%s), falling back to rules",
                   "present" if raw_output else "None")
    rules_items = _extract_via_rules(
        answer=answer,
        current_section=req.current_section,
        current_target=req.current_target_path,
        current_phase=req.current_phase,
    )

    # WO-EX-01C + WO-EX-01D: same guard stack on rules output (subject filter
    # is also applied inside _extract_via_rules itself, so the birth-context
    # call here is defense-in-depth for any future regex that escapes era
    # gating; field-value sanity catches state-abbr and stopword fragments
    # regardless of whether they came from rules or LLM).
    if rules_items:
        rules_items = _apply_birth_context_filter(
            rules_items,
            req.current_section,
            answer,
            current_phase=req.current_phase,
        )
        rules_items = _apply_month_name_sanity(rules_items)
        rules_items = _apply_field_value_sanity(rules_items)
        rules_items = _apply_claims_validators(rules_items, answer=answer)  # WO-EX-CLAIMS-02

    if rules_items:
        result_items = []
        for item in rules_items:
            meta = EXTRACTABLE_FIELDS.get(item["fieldPath"], {})
            write_mode = meta.get("writeMode", "suggest_only")

            # Phase G: Protected identity field conflict detection (rules path)
            if item["fieldPath"] in PROTECTED_IDENTITY_FIELDS:
                canonical_val = _protected_snapshot.get(item["fieldPath"], "")
                if canonical_val and canonical_val.strip() and item["value"] != canonical_val:
                    write_mode = "suggest_only"
                    logger.warning(
                        "[extract] Phase G: Protected identity conflict (rules) for %s: canonical=%r extracted=%r",
                        item["fieldPath"], canonical_val, item["value"],
                    )

            result_items.append(ExtractedItem(
                fieldPath=item["fieldPath"],
                value=item["value"],
                writeMode=write_mode,
                confidence=item["confidence"],
                source="backend_extract",
                # WO-13 Phase 4 — this is the LLM fallback path, so tag items
                # as 'rules_fallback' (not plain 'rules'). The family-truth
                # proposal layer uses this tag to quarantine regex output and
                # prevent it from auto-promoting.
                extractionMethod="rules_fallback",
            ))

        # WO-EX-VALIDATE-01 — same flag-gated filter on the rules path so
        # both extraction routes behave consistently.
        try:
            from .. import flags as _flags
            if _flags.age_validator_enabled():
                _dob = _fetch_dob_for_validation(req.person_id)
                result_items = _apply_age_math_filter(result_items, _dob)
        except Exception as _e:
            logger.warning("[extract][validator] filter skipped (rules path): %s", _e)

        _record_metric("rules", parsed=0, accepted=len(result_items), rejected=0)
        return ExtractFieldsResponse(
            items=result_items,
            method="rules_fallback",
            raw_llm_output=raw_output,  # include for debugging even on rules fallback
        )

    # Nothing extracted — return empty
    _record_metric("fallback", parsed=0, accepted=0, rejected=0)
    return ExtractFieldsResponse(items=[], method="fallback", raw_llm_output=raw_output)


# ── Diagnostic endpoint ─────────────────────────────────────────────────────

@router.get("/extract-diag")
def extract_diag():
    """Diagnostic: check whether the LLM extraction stack is available."""
    llm_available = False
    llm_error = None
    cache_age = _time.time() - _llm_available_cache["checked_at"]
    try:
        from ..llm_interview import _try_call_llm
        # Quick ping: tiny extraction to see if LLM responds
        result = _try_call_llm(
            "Return exactly: {\"status\":\"ok\"}",
            "ping",
            max_new=20, temp=0.01, top_p=1.0,
        )
        if result:
            llm_available = True
            _mark_llm_available()
        else:
            llm_error = "LLM returned None (likely ImportError or empty response)"
            _mark_llm_unavailable("diag-empty-response")
    except ImportError as e:
        llm_error = f"ImportError: {e}"
        _mark_llm_unavailable(f"diag-import-error:{e}")
    except Exception as e:
        llm_error = f"{type(e).__name__}: {e}"
        _mark_llm_unavailable(f"diag-exception:{type(e).__name__}")

    return {
        "llm_available": llm_available,
        "llm_error": llm_error,
        "llm_cache_available": _llm_available_cache["available"],
        "llm_cache_age_sec": round(cache_age, 2),
        "llm_cache_ttl_sec": _LLM_CHECK_TTL,
        "rules_available": True,
        "regex_pattern_count": len([
            k for k in globals() if k.startswith("_") and k[1:2].isupper()
        ]),
        # Phase 6B: Extraction metrics
        "metrics": {
            "total_turns": _extraction_metrics["total_turns"],
            "llm_turns": _extraction_metrics["llm_turns"],
            "rules_turns": _extraction_metrics["rules_turns"],
            "fallback_turns": _extraction_metrics["fallback_turns"],
            "llm_ratio": round(
                _extraction_metrics["llm_turns"] / max(1, _extraction_metrics["total_turns"]), 3
            ),
            "total_parsed": _extraction_metrics["total_parsed"],
            "total_accepted": _extraction_metrics["total_accepted"],
            "total_rejected": _extraction_metrics["total_rejected"],
            "acceptance_ratio": round(
                _extraction_metrics["total_accepted"] /
                max(1, _extraction_metrics["total_parsed"] + _extraction_metrics["total_accepted"]), 3
            ),
            "reject_reasons": dict(_extraction_metrics["reject_reasons"]),
        },
    }
