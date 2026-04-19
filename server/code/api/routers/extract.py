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
    # ── LOOP-01 R2 wide — narrative-catch slots ──────────────────────────────
    "personal.nameStory":      {"label": "Story behind the narrator's name (who picked it, religious/family origin, why)", "writeMode": "suggest_only"},
    "personal.notes":          {"label": "General personal color (personality, identity context, miscellaneous)", "writeMode": "suggest_only"},

    # Early memories (suggest_only)
    "earlyMemories.firstMemory":       {"label": "Earliest childhood memory", "writeMode": "suggest_only"},
    "earlyMemories.significantEvent":   {"label": "Significant childhood event", "writeMode": "suggest_only"},

    # Education & career (suggest_only)
    "education.schooling":           {"label": "Schooling history (name of school, details)", "writeMode": "suggest_only"},
    "education.higherEducation":     {"label": "College or higher education", "writeMode": "suggest_only"},
    "education.earlyCareer":         {"label": "First job or early career", "writeMode": "suggest_only"},
    "education.careerProgression":   {"label": "Career progression and major changes", "writeMode": "suggest_only"},
    "education.notes":               {"label": "Education / career color (school affiliation, geography, mentors, anecdotes)", "writeMode": "suggest_only", "repeatable": "education"},

    # Later years (suggest_only)
    "laterYears.retirement":               {"label": "Retirement experience", "writeMode": "suggest_only"},
    "laterYears.lifeLessons":              {"label": "Life lessons learned", "writeMode": "suggest_only"},
    "laterYears.significantEvent":         {"label": "Significant later-life event or turning point", "writeMode": "suggest_only"},
    "laterYears.dailyRoutine":             {"label": "Current daily routine or lifestyle", "writeMode": "suggest_only"},
    "laterYears.desiredStory":             {"label": "Story the narrator specifically wants told", "writeMode": "suggest_only", "repeatable": "laterYears"},

    # Cultural / generational touchstones (suggest_only) — WO-QB-GENERATIONAL-01
    "cultural.touchstoneMemory":    {"label": "Where-were-you memory tied to a historical event", "writeMode": "suggest_only", "repeatable": "cultural"},

    # Hobbies (suggest_only)
    "hobbies.hobbies":              {"label": "Hobbies and interests", "writeMode": "suggest_only"},
    "hobbies.personalChallenges":   {"label": "Personal challenges or hardships", "writeMode": "suggest_only"},
    "hobbies.notes":                {"label": "Hobby color / leisure narrative (how it started, meaning, context)", "writeMode": "suggest_only", "repeatable": "hobbies"},

    # Additional notes (suggest_only)
    "additionalNotes.unfinishedDreams":           {"label": "Unfinished dreams or goals", "writeMode": "suggest_only"},

    # Repeatable: parents (candidate_only)
    "parents.relation":          {"label": "Parent relationship (father/mother/step)", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.firstName":         {"label": "Parent first name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.middleName":        {"label": "Parent middle name(s) — comma-separated if multiple", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.lastName":          {"label": "Parent last name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.maidenName":        {"label": "Parent maiden name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.birthDate":         {"label": "Parent birth date", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.birthPlace":        {"label": "Parent birthplace", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.occupation":        {"label": "Parent occupation", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.notes":             {"label": "Parent notes (nicknames, personality, color)", "writeMode": "candidate_only", "repeatable": "parents"},
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
    "family.children.notes":          {"label": "Child color (personality, nickname origin, anecdote)", "writeMode": "suggest_only", "repeatable": "children"},

    # ── WO-EX-SCHEMA-01 — Spouse / partner ────────────────────────────────────
    "family.spouse.firstName":        {"label": "Spouse / partner first name", "writeMode": "prefill_if_blank"},
    "family.spouse.lastName":         {"label": "Spouse / partner last name", "writeMode": "prefill_if_blank"},
    "family.spouse.maidenName":       {"label": "Spouse / partner maiden name", "writeMode": "prefill_if_blank"},
    "family.spouse.dateOfBirth":      {"label": "Spouse / partner DOB", "writeMode": "prefill_if_blank"},
    "family.spouse.placeOfBirth":     {"label": "Spouse / partner place of birth", "writeMode": "prefill_if_blank"},
    "family.spouse.notes":            {"label": "Spouse / partner personality or color beyond marriage facts", "writeMode": "suggest_only"},

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

    # ── LOOP-01 R2 — Great-grandparents (repeatable) ────────────────────────
    # Added per WO-EX-DENSE-DIAG-01 Phase 2 finding: greatGrandparent recall
    # was 0% across all length buckets because the schema had no destination
    # field for great-grandfather/great-grandmother facts. Mirror the
    # grandparents.* shape (one row per ancestor person).
    "greatGrandparents.side":         {"label": "Great-grandparent side (maternal/paternal/mother's father, etc.)", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.firstName":    {"label": "Great-grandparent first name", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.lastName":     {"label": "Great-grandparent last name", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.maidenName":   {"label": "Great-grandparent maiden name", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.birthDate":    {"label": "Great-grandparent birth date", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.birthPlace":   {"label": "Great-grandparent birthplace", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.ancestry":     {"label": "Great-grandparent ancestry or ethnic background", "writeMode": "candidate_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.memorableStories": {"label": "Memorable stories about great-grandparent (Civil War, immigration, name origin, etc.)", "writeMode": "suggest_only", "repeatable": "greatGrandparents"},

    # ── WO-SCHEMA-02 Priority 2 — Military ──────────────────────────────────
    "military.branch":                {"label": "Military branch (Army, Navy, etc.)", "writeMode": "suggest_only"},
    "military.yearsOfService":        {"label": "Years of military service (e.g., 1965-1968)", "writeMode": "suggest_only"},
    "military.rank":                  {"label": "Highest military rank attained", "writeMode": "suggest_only"},
    "military.deploymentLocation":    {"label": "Military deployment location", "writeMode": "suggest_only", "repeatable": "military"},
    "military.significantEvent":      {"label": "Significant military event or experience", "writeMode": "suggest_only", "repeatable": "military"},
    "military.notes":                 {"label": "Service color (camaraderie, daily life, transition out, post-service)", "writeMode": "suggest_only"},

    # ── WO-SCHEMA-02 Priority 3 — Faith & Values ────────────────────────────
    "faith.denomination":             {"label": "Faith denomination (Catholic, Lutheran, etc.)", "writeMode": "suggest_only"},
    "faith.role":                     {"label": "Role in faith community (choir, deacon, etc.)", "writeMode": "suggest_only"},
    "faith.significantMoment":        {"label": "Significant faith moment or turning point", "writeMode": "suggest_only"},
    "faith.values":                   {"label": "Core values or beliefs", "writeMode": "suggest_only"},
    "faith.notes":                    {"label": "Faith / spiritual color (parish, traditions, family religion, lapses, returns)", "writeMode": "suggest_only"},

    # ── WO-SCHEMA-02 Priority 4 — Health ────────────────────────────────────
    "health.majorCondition":          {"label": "Major health condition or diagnosis", "writeMode": "suggest_only", "repeatable": "health"},
    "health.milestone":               {"label": "Health milestone (surgery, recovery, etc.)", "writeMode": "suggest_only"},
    "health.lifestyleChange":         {"label": "Significant lifestyle change for health", "writeMode": "suggest_only"},
    "health.currentMedications":      {"label": "Current medications or treatments", "writeMode": "suggest_only"},
    "health.cognitiveChange":         {"label": "Self-reported memory or cognitive change", "writeMode": "suggest_only"},
    "health.notes":                   {"label": "Health narrative color (caregiving, family history, attitudes, adaptations)", "writeMode": "suggest_only"},

    # ── WO-SCHEMA-02 Priority 5 — Community & Civic Life ────────────────────
    "community.organization":         {"label": "Community organization or group", "writeMode": "suggest_only", "repeatable": "community"},
    "community.role":                 {"label": "Role in community organization", "writeMode": "suggest_only", "repeatable": "community"},
    "community.yearsActive":          {"label": "Years active in community role", "writeMode": "suggest_only", "repeatable": "community"},
    "community.significantEvent":     {"label": "Significant community event or contribution", "writeMode": "suggest_only"},
    "community.notes":                {"label": "Community / civic color (people met, meaningful projects, context)", "writeMode": "suggest_only", "repeatable": "community"},

    # ── WO-SCHEMA-02 Priority 6 — Pets ──────────────────────────────────────
    "pets.name":                      {"label": "Pet name", "writeMode": "candidate_only", "repeatable": "pets"},
    "pets.species":                   {"label": "Pet species (dog, cat, horse, etc.)", "writeMode": "candidate_only", "repeatable": "pets"},
    "pets.notes":                     {"label": "Pet notes (personality, story, meaning)", "writeMode": "suggest_only", "repeatable": "pets"},

    # ── WO-SCHEMA-02 Priority 7 — Travel ────────────────────────────────────
    "travel.destination":             {"label": "Travel destination", "writeMode": "suggest_only", "repeatable": "travel"},
    "travel.purpose":                 {"label": "Purpose of travel (vacation, work, family, military)", "writeMode": "suggest_only", "repeatable": "travel"},
    "travel.significantTrip":         {"label": "Most significant or memorable trip", "writeMode": "suggest_only"},
    "travel.notes":                   {"label": "Travel color (companions, memorable moments, return impressions)", "writeMode": "suggest_only", "repeatable": "travel"},

    # ── LOOP-01 R3 — Schema gap fills from api.log audit ────────────────────
    # Added after the R2 api.log audit revealed 325 REJECTs across 218 unique
    # fieldPaths. These entries give homes to factual fields the LLM was
    # emitting correctly but which had no schema target. Companion aliases
    # live in _FIELD_ALIASES under the same R3 banner.

    # parents.* extensions — preferred names, death facts, education, background
    "parents.preferredName":     {"label": "Parent nickname / preferred name", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.deathDate":         {"label": "Parent death date", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.ageAtDeath":        {"label": "Parent age at death", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.placeOfDeath":      {"label": "Parent place of death", "writeMode": "candidate_only", "repeatable": "parents"},
    "parents.education":         {"label": "Parent education (schooling, college)", "writeMode": "suggest_only", "repeatable": "parents"},
    "parents.ethnicBackground":  {"label": "Parent ethnic / cultural background", "writeMode": "suggest_only", "repeatable": "parents"},

    # grandparents.* extensions — mirror greatGrandparents shape where missing
    "grandparents.birthDate":    {"label": "Grandparent birth date", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.deathDate":    {"label": "Grandparent death date", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.occupation":   {"label": "Grandparent occupation", "writeMode": "candidate_only", "repeatable": "grandparents"},
    "grandparents.childCount":   {"label": "Number of children grandparent had", "writeMode": "candidate_only", "repeatable": "grandparents"},

    # siblings.* extensions — birth facts + preferred name + occupation
    "siblings.birthDate":        {"label": "Sibling birth date", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.birthPlace":       {"label": "Sibling birthplace", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.preferredName":    {"label": "Sibling nickname / preferred name", "writeMode": "candidate_only", "repeatable": "siblings"},
    "siblings.occupation":       {"label": "Sibling occupation", "writeMode": "candidate_only", "repeatable": "siblings"},

    # family.spouse.* extensions — relation, middle name, nickname, age at
    # marriage, occupation, education (the dominant R2 spouse-cluster rejects)
    "family.spouse.relation":       {"label": "Spouse relation type (wife, husband, partner)", "writeMode": "prefill_if_blank"},
    "family.spouse.middleName":     {"label": "Spouse middle name(s)", "writeMode": "prefill_if_blank"},
    "family.spouse.preferredName":  {"label": "Spouse nickname / preferred name", "writeMode": "prefill_if_blank"},
    "family.spouse.ageAtMarriage":  {"label": "Spouse age at marriage", "writeMode": "prefill_if_blank"},
    "family.spouse.occupation":     {"label": "Spouse occupation", "writeMode": "prefill_if_blank"},
    "family.spouse.education":      {"label": "Spouse education (schooling, college)", "writeMode": "suggest_only"},

    # greatGrandparents.military* — ancestor-scoped military so the narrator-
    # scoped negation-guard (which strips military.* on "I never served")
    # cannot eat legitimate Civil War / WWI ancestor facts. See R3 Patch 4.
    "greatGrandparents.militaryBranch": {"label": "Great-grandparent military branch (ancestor-scoped)", "writeMode": "suggest_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.militaryUnit":   {"label": "Great-grandparent military unit / regiment", "writeMode": "suggest_only", "repeatable": "greatGrandparents"},
    "greatGrandparents.militaryEvent":  {"label": "Great-grandparent military event / deployment / dates", "writeMode": "suggest_only", "repeatable": "greatGrandparents"},

    # community.* dense-interview extensions
    "community.meetingDay":       {"label": "Day/frequency community group meets", "writeMode": "suggest_only", "repeatable": "community"},
    "community.meetingLocation":  {"label": "Where community group meets", "writeMode": "suggest_only", "repeatable": "community"},
    "community.memberCount":      {"label": "Number of members in community group", "writeMode": "suggest_only", "repeatable": "community"},
    "community.successor":        {"label": "Person who took over community role", "writeMode": "suggest_only", "repeatable": "community"},

    # education.* dense-interview extensions
    "education.gradeLevel":       {"label": "Grade level achieved (e.g., 8th grade, high school diploma)", "writeMode": "suggest_only"},
    "education.readingAbility":   {"label": "Self-reported reading ability / literacy context", "writeMode": "suggest_only"},
    "education.training":         {"label": "Trade or technical training (apart from schooling/college)", "writeMode": "suggest_only"},
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
        "Example — narrator says: \"Our first son Christopher was born December 24, 1962 in Williston, North Dakota. "
        "That was the best Christmas Eve of our lives.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"family.children.relation\",\"value\":\"son\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.firstName\",\"value\":\"Christopher\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.dateOfBirth\",\"value\":\"December 24, 1962\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.placeOfBirth\",\"value\":\"Williston, North Dakota\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.birthOrder\",\"value\":\"first\",\"confidence\":0.85}]\n"
        "When the narrator calls a child \"our first\" / \"our oldest\" / \"the baby\", also write family.children.birthOrder.\n"
        "\n"
        "Example — narrator says: \"Gretchen was a surprise — I was almost 40 when she came along.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"family.children.firstName\",\"value\":\"Gretchen\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.children.notes\",\"value\":\"surprise child; narrator was almost 40\",\"confidence\":0.8}]\n"
        "\n"
        "Example — narrator says: \"My closest friend all through school was Harold Schmitt. "
        "He was the one who got me interested in carpentry — he and my Uncle Pete were the two people who shaped me most.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"earlyMemories.significantEvent\",\"value\":\"closest friend: Harold Schmitt, through school; Uncle Pete; both shaped narrator; Harold got narrator interested in carpentry\",\"confidence\":0.85},"
        "{\"fieldPath\":\"relationships.closeFriends\",\"value\":\"Harold Schmitt\",\"confidence\":0.9}]\n"
        "(Use relationships.closeFriends if in schema; otherwise earlyMemories.significantEvent is the catch-all for formative relationships.)\n"
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
        "Example — narrator says: \"We were married at St. Mary's Catholic Church in Williston on June 4th, 1960.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"family.marriageDate\",\"value\":\"June 4, 1960\",\"confidence\":0.9},"
        "{\"fieldPath\":\"family.marriagePlace\",\"value\":\"St. Mary's Catholic Church, Williston\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"Our wedding was a small one at the courthouse in Minot.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"family.marriagePlace\",\"value\":\"courthouse, Minot\",\"confidence\":0.85}]\n"
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
        "Example — narrator says: \"My grandparents on my father's side were French (Alsace-Lorraine) and German. "
        "On my mother's side, Norwegian and a little Irish.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"grandparents.side\",\"value\":\"paternal\",\"confidence\":0.9},"
        "{\"fieldPath\":\"grandparents.ancestry\",\"value\":\"French (Alsace-Lorraine), German\",\"confidence\":0.9},"
        "{\"fieldPath\":\"grandparents.side\",\"value\":\"maternal\",\"confidence\":0.9},"
        "{\"fieldPath\":\"grandparents.ancestry\",\"value\":\"Norwegian, Irish\",\"confidence\":0.9}]\n"
        "\"Ancestry\" / \"ethnic background\" / \"came from [country]\" → grandparents.ancestry (NOT grandparents.birthPlace unless a specific person's birth-city was named).\n"
        "\n"
        "Example — narrator says: \"My great-grandfather John Michael Shong was born in Lorraine, France in 1829, "
        "served in the Civil War, and settled at Fall Creek, Wisconsin. The family name was originally Schong and "
        "the C got dropped after they came to America.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"greatGrandparents.firstName\",\"value\":\"John Michael\",\"confidence\":0.9},"
        "{\"fieldPath\":\"greatGrandparents.lastName\",\"value\":\"Shong\",\"confidence\":0.9},"
        "{\"fieldPath\":\"greatGrandparents.birthDate\",\"value\":\"1829\",\"confidence\":0.85},"
        "{\"fieldPath\":\"greatGrandparents.birthPlace\",\"value\":\"Lorraine, France\",\"confidence\":0.9},"
        "{\"fieldPath\":\"greatGrandparents.ancestry\",\"value\":\"French (Alsace-Lorraine)\",\"confidence\":0.9},"
        "{\"fieldPath\":\"greatGrandparents.memorableStories\",\"value\":\"Civil War service, settled Fall Creek Wisconsin, family name originally Schong with C dropped after immigration\",\"confidence\":0.9}]\n"
        "Great-grandparents (\"my great-grandfather\", \"my great-grandmother\", \"my dad's grandfather\") → greatGrandparents.* — "
        "NOT grandparents.*, NOT parents.*, NOT personal.*. The narrator's own military, birthplace, and ancestry are SEPARATE from a great-grandparent's.\n"
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
        "Example — narrator says: \"I had a dog named Ivan when I was little.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"pets.name\",\"value\":\"Ivan\",\"confidence\":0.9},"
        "{\"fieldPath\":\"pets.species\",\"value\":\"dog\",\"confidence\":0.9}]\n"
        "(Do NOT write `pets.notes=\"dog named Ivan\"` — name and species go on their own fields.)\n"
        "\n"
        "Example — narrator says: \"Our cat Whiskers lived to be sixteen.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"pets.name\",\"value\":\"Whiskers\",\"confidence\":0.9},"
        "{\"fieldPath\":\"pets.species\",\"value\":\"cat\",\"confidence\":0.9},"
        "{\"fieldPath\":\"pets.notes\",\"value\":\"lived to be sixteen\",\"confidence\":0.8}]\n"
        "\n"
        "Example — narrator says: \"We took a trip to Europe in 1985. It was our anniversary.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"travel.destination\",\"value\":\"Europe\",\"confidence\":0.9},"
        "{\"fieldPath\":\"travel.purpose\",\"value\":\"anniversary trip\",\"confidence\":0.8}]\n"
        "\n"
        "GENERATIONAL & LATE-LIFE EXAMPLES — touchstones, medications, memory, frustrations, desired stories:\n"
        "\n"
        "Example — narrator says: \"We were watching on a little black-and-white set when they landed on the moon. "
        "The whole family was in the living room.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"laterYears.significantEvent\",\"value\":\"watched the moon landing on TV with the whole family\",\"confidence\":0.9},"
        "{\"fieldPath\":\"cultural.touchstoneMemory\",\"value\":\"moon landing — watched on a black-and-white TV with the whole family in the living room\",\"confidence\":0.9}]\n"
        "Touchstone 'where-were-you' memories get BOTH laterYears.significantEvent (the fact) AND "
        "cultural.touchstoneMemory (the vivid memory with sensory detail). If the narrator only gives a bare "
        "fact ('yeah, I saw it on TV'), use only laterYears.significantEvent.\n"
        "\n"
        "Example — narrator says: \"In Bismarck we sat in line with the engine off hoping the gas held out. "
        "My wife packed sandwiches.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"residence.place\",\"value\":\"Bismarck\",\"confidence\":0.9},"
        "{\"fieldPath\":\"laterYears.significantEvent\",\"value\":\"waited in gas lines during the 1970s energy crisis\",\"confidence\":0.8}]\n"
        "Scene-setting family mentions (wife, kids in the car) are NOT extractable spouse/children facts.\n"
        "\n"
        "Example — narrator says: \"I take blood pressure medicine every morning, and something for arthritis "
        "when my hands flare up.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"health.currentMedications\",\"value\":\"blood pressure medicine daily, arthritis medication as needed\",\"confidence\":0.9},"
        "{\"fieldPath\":\"health.majorCondition\",\"value\":\"high blood pressure\",\"confidence\":0.8},"
        "{\"fieldPath\":\"health.majorCondition\",\"value\":\"arthritis\",\"confidence\":0.8}]\n"
        "Medications → health.currentMedications. The conditions those medications treat → health.majorCondition. Both valid.\n"
        "\n"
        "Example — narrator says: \"Names take longer than they used to, but the old stories are still there. "
        "It's the little daily things that slip first.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"health.cognitiveChange\",\"value\":\"names are slower to recall, small daily details slip first, but long-term memories remain\",\"confidence\":0.8}]\n"
        "Self-reported memory change → health.cognitiveChange. Do NOT write health.majorCondition — this is normal aging, not a diagnosis.\n"
        "\n"
        "Example — narrator says: \"Everything takes longer now, and younger people assume older means helpless. "
        "That gets under my skin.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"hobbies.personalChallenges\",\"value\":\"frustration with slowing down and being treated as helpless\",\"confidence\":0.9}]\n"
        "Late-life frustrations → hobbies.personalChallenges. Do NOT invent paths like laterYears.frustrations.\n"
        "\n"
        "Example — narrator says: \"An uncle of mine got drafted and the whole house went quiet for weeks. "
        "I was still a senior in high school out in rural Montana, and the grown-ups talked about it at supper "
        "every night.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"laterYears.significantEvent\",\"value\":\"family atmosphere shifted when uncle was drafted during the Vietnam era\",\"confidence\":0.85},"
        "{\"fieldPath\":\"education.schooling\",\"value\":\"high school\",\"confidence\":0.8},"
        "{\"fieldPath\":\"residence.region\",\"value\":\"Montana\",\"confidence\":0.8}]\n"
        "\n"
        "Example — narrator says: \"First time was at the office in the early nineties. They wheeled a desktop "
        "onto my desk and I spent weeks feeling like the new hire half my age was teaching me.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"laterYears.significantEvent\",\"value\":\"first workplace desktop computer arrived in the early 1990s\",\"confidence\":0.9},"
        "{\"fieldPath\":\"hobbies.personalChallenges\",\"value\":\"felt behind learning computers at work\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"Every Friday night in summer we'd pile into the station wagon and head "
        "out to the drive-in outside Minot. Popcorn, mosquitoes, and all.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"hobbies.hobbies\",\"value\":\"going to the drive-in\",\"confidence\":0.9},"
        "{\"fieldPath\":\"residence.place\",\"value\":\"Minot\",\"confidence\":0.85}]\n"
        "\n"
        "Example — narrator says: \"Watching these new crews head up reminds me that each generation gets its "
        "own turn at the sky. The dreams of my time are becoming the work of my grandchildren.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"laterYears.lifeLessons\",\"value\":\"each generation inherits and carries forward the wonder of the last\",\"confidence\":0.9}]\n"
        "\n"
        "Example — narrator says: \"I'd want my family to hear about my dad dying in '67, the years we built "
        "a life in Germany, and how their mother and I got started with almost nothing.\"\n"
        "Output:\n"
        "[{\"fieldPath\":\"laterYears.desiredStory\",\"value\":\"father's death in 1967\",\"confidence\":0.9},"
        "{\"fieldPath\":\"laterYears.desiredStory\",\"value\":\"years building a life in Germany\",\"confidence\":0.9},"
        "{\"fieldPath\":\"laterYears.desiredStory\",\"value\":\"early married life starting with almost nothing\",\"confidence\":0.9}]\n"
        "When narrator lists stories they want told, each is a separate laterYears.desiredStory (repeatable). "
        "Do NOT collapse into one value. Do NOT extract mentioned places/dates as residence.* or parents.* — "
        "the narrator is listing priorities, not narrating those events.\n"
        "\n"
        "NEGATION RULE: If the narrator explicitly says they did NOT have an experience "
        "(e.g., 'I never served', 'I've been pretty healthy', 'I didn't go to college'), "
        "extract NOTHING for that category. Do not guess or infer fields from denied experiences.\n"
        "\n"
        "SUBJECT RULE: Only extract fields for the NARRATOR being interviewed. "
        "When the narrator describes a family member's experience (mother's school, father's work, "
        "grandfather's military service), use family-scoped fields (grandparents.*, parents.*, greatGrandparents.*) — "
        "NOT the narrator's personal fields. Example: narrator says 'My mother went to Mount Marty school' "
        "→ this is faith/family history, NOT education.schooling for the narrator. "
        "A great-grandparent's Civil War service is greatGrandparents.memorableStories — NEVER military.* for the narrator. "
        "A great-grandparent's birthplace is greatGrandparents.birthPlace — NEVER personal.placeOfBirth.\n"
        "\n"
        "SAME-ENTITY ELABORATION RULE (applies to all sections): When the narrator elaborates on an already-mentioned "
        "person, place, name, school, organization, pet, trip, or event — explaining why the name was chosen, what it meant, "
        "who named it, where exactly it was, what people called it, its religious/family background — these elaborations "
        "enrich the EXISTING record. Do NOT emit a second record for the explanation. Fold the elaboration into the matching "
        "notes/nameStory/story field for that entity, and/or enrich the canonical record's value.\n"
        "Canonical narrative-catch slots by section:\n"
        "  • personal.nameStory — naming origin: \"Mom wanted Todd because the priest said Christopher was a saint\"\n"
        "  • personal.notes — general narrator color (identity, personality, misc)\n"
        "  • parents.notes / parents.notableLifeEvents — parent color beyond structured fields\n"
        "  • grandparents.memorableStory — grandparent color\n"
        "  • greatGrandparents.memorableStories — great-grandparent color\n"
        "  • siblings.uniqueCharacteristics — sibling color\n"
        "  • family.children.notes — child personality, nickname origins, anecdotes\n"
        "  • family.spouse.notes — spouse personality beyond marriage facts (family.marriageNotes is for the marriage event)\n"
        "  • education.notes — school color: religious affiliation, geography, mentors\n"
        "  • faith.notes — parish, traditions, family religion, lapses\n"
        "  • hobbies.notes — hobby origins and meaning\n"
        "  • military.notes — service color (camaraderie, transition, post-service)\n"
        "  • health.notes — health narrative color (caregiving, family history, adaptations)\n"
        "  • travel.notes — trip color (companions, memorable moments)\n"
        "  • community.notes — civic color (people met, projects)\n"
        "  • pets.notes — pet personality and story\n"
        "  • residence.notes — residence color\n"
        "Examples:\n"
        "• \"My name is Christopher Todd Horne — Mom wanted the Todd name because the priest said Christopher was a saint.\" "
        "→ ONE personal.fullName='Christopher Todd Horne' + ONE personal.middleName='Todd' + ONE "
        "personal.nameStory='mother chose Todd because the priest said Christopher was a saint'. Do NOT emit a saint record, "
        "a priest record, or duplicate name records.\n"
        "• \"Grandma Lizzie. Her real name was Elizabeth\" → ONE grandparents.firstName='Elizabeth' (not also 'Lizzie').\n"
        "• \"Josephine Eugenia Susanna Schaaf — everyone called her Josie\" → ONE parents.firstName='Josephine', "
        "ONE parents.middleName='Eugenia, Susanna'. Josie folds into parents.notes or parents.preferredName.\n"
        "• \"Mount Marty — a Catholic school in Yankton, run by the Benedictines\" → ONE education.schooling='Mount Marty' + "
        "ONE education.notes='Catholic school in Yankton run by the Benedictines'. Do NOT emit a second schooling record.\n"
        "• \"The family name was originally Schong, possibly Le Shong, became Shong in America\" → ONE "
        "grandparents.maidenName='Shong' (post-immigration canonical form) + grandparents.memorableStory capturing the spelling history. "
        "Do NOT emit additional grandparent records for Schong or Le Shong.\n"
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
    """Route to two-pass or single-pass extraction based on feature flag.

    WO-EX-TWOPASS-01: When HORNELORE_TWOPASS_EXTRACT=1, uses span-tagger
    (pass 1) + field-classifier (pass 2). Falls back to single-pass on
    any pass 1 failure. When flag is OFF, behavior is identical to pre-WO.
    """
    try:
        from .. import flags as _flags
        if _flags.twopass_extract_enabled():
            logger.info("[extract][twopass] flag ON — using two-pass pipeline")
            return _extract_via_twopass(answer, current_section, current_target)
    except Exception as _e:
        logger.warning("[extract][twopass] flag check failed (%s), using single-pass", _e)

    return _extract_via_singlepass(answer, current_section, current_target)


def _extract_via_singlepass(answer: str, current_section: Optional[str], current_target: Optional[str]) -> tuple[List[dict], Optional[str]]:
    """Original single-pass LLM extraction. Returns (items, raw_output).

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
    # WO-10M / WO-EX-CLAIMS-01 / LOOP-01 R3: Token cap is now dynamic.
    # Simple single-fact answers: 128 tokens (original cap, ample for 1-3 items).
    # Compound answers (multiple names, years, list patterns): 768 tokens so the
    # LLM can emit a complete JSON array for 10-20+ items without truncation.
    # LOOP-01 R3 raised the compound ceiling from 384→768 after the R2 api.log
    # audit showed dense genealogy answers (greatGrandparents, parents+spouse+
    # children combined) hitting 1400-1550 char outputs that truncated mid-JSON
    # at the 384 cap, falling to salvage or zero-item rules fallback.
    # ~1 token ≈ 3 chars for JSON output, so 768 gives ~2300 chars of headroom.
    _base_cap = int(os.getenv("MAX_NEW_TOKENS_EXTRACT", "128"))
    _compound_cap = int(os.getenv("MAX_NEW_TOKENS_EXTRACT_COMPOUND", "768"))
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


# ── WO-EX-TWOPASS-01 — Two-Pass Extraction Pipeline ──────────────────────────
#
# Pass 1: Schema-blind span tagger — identifies factual spans with type/role/flags
# Pass 2: Field classifier — maps tagged spans to EXTRACTABLE_FIELDS
#   2A: Rule-based deterministic mapping (cheap, no LLM)
#   2B: LLM classifier for unresolved spans (only when needed)

# ── Span types and flags ──────────────────────────────────────────────────────

_VALID_SPAN_TYPES = frozenset({
    "person", "place", "time", "event", "pet",
    "organization", "military", "faith", "health", "trait",
})

_VALID_SPAN_FLAGS = frozenset({
    "negated", "uncertain", "family_member_not_narrator",
})


def _build_span_tagger_prompt(answer: str, current_section: Optional[str]) -> tuple[str, str]:
    """Build system + user prompts for Pass 1: span tagging.

    This prompt is deliberately schema-blind. It does NOT see EXTRACTABLE_FIELDS
    or fieldPaths. Its only job is: what factual spans are present?
    """
    system = (
        "You are a span tagger for oral history transcripts. Read the narrator's "
        "answer and identify every factual span.\n"
        "\n"
        "Output a JSON object: {\"spans\": [...]}\n"
        "Each span has:\n"
        "- \"text\": exact words from the narrator (keep brief)\n"
        "- \"type\": one of: person, place, time, event, pet, organization, "
        "military, faith, health, trait\n"
        "- \"role\": (person type only) relationship: father, mother, brother, "
        "sister, son, daughter, wife, husband, grandmother, grandfather, etc.\n"
        "- \"flags\": array of zero or more: negated, uncertain, "
        "family_member_not_narrator\n"
        "\n"
        "Rules:\n"
        "- Tag only facts EXPLICITLY stated. Do not infer or guess.\n"
        "- \"I never served\" → type=event, flags=[\"negated\"]\n"
        "- \"My dad John\" → type=person, role=\"father\", "
        "flags=[\"family_member_not_narrator\"]\n"
        "- \"I was born in Spokane\" → one place span (Spokane) + one event span (born)\n"
        "- If uncertain, include with flags=[\"uncertain\"]\n"
        "- A person's name and role go in ONE span, not separate spans\n"
        "- Separate facts get separate spans\n"
        "\n"
        "Example — narrator says: \"My older brother Vincent was stationed in "
        "Germany in 1960. We had a Golden Retriever named Ivan.\"\n"
        "Output:\n"
        "{\"spans\":["
        "{\"text\":\"older brother Vincent\",\"type\":\"person\",\"role\":\"brother\","
        "\"flags\":[\"family_member_not_narrator\"]},"
        "{\"text\":\"Germany\",\"type\":\"place\",\"flags\":[]},"
        "{\"text\":\"1960\",\"type\":\"time\",\"flags\":[]},"
        "{\"text\":\"stationed\",\"type\":\"military\","
        "\"flags\":[\"family_member_not_narrator\"]},"
        "{\"text\":\"Golden Retriever named Ivan\",\"type\":\"pet\",\"flags\":[]}"
        "]}\n"
        "\n"
        "Example — narrator says: \"I never served in the military. "
        "I've been pretty healthy my whole life.\"\n"
        "Output:\n"
        "{\"spans\":["
        "{\"text\":\"never served in the military\",\"type\":\"event\","
        "\"flags\":[\"negated\"]},"
        "{\"text\":\"pretty healthy my whole life\",\"type\":\"health\","
        "\"flags\":[\"negated\"]}"
        "]}\n"
        "\n"
        "Output ONLY the JSON object. No extra text."
    )

    context_note = ""
    if current_section:
        context_note = f"\nInterview section: {current_section}"

    user = (
        f"Narrator's answer:{context_note}\n\n"
        f"\"{answer}\"\n\n"
        "Tag all factual spans as JSON:"
    )

    return system, user


def _parse_span_json(raw: str) -> List[dict]:
    """Parse and validate span tagger output. Returns list of valid spans."""
    raw = raw.strip()
    logger.info("[extract][twopass][p1-parse] Raw span output (%d chars): %.500s",
                len(raw), raw)

    parsed = None

    # Try direct JSON parse
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    if parsed is None:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

    # Try finding first { ... } in the output
    if parsed is None:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    if parsed is None:
        logger.warning("[extract][twopass][p1-parse] Could not parse span JSON")
        return []

    # Extract spans array
    spans_raw = []
    if isinstance(parsed, dict):
        spans_raw = parsed.get("spans", [])
    elif isinstance(parsed, list):
        spans_raw = parsed
    else:
        logger.warning("[extract][twopass][p1-parse] Unexpected type: %s", type(parsed).__name__)
        return []

    # Validate each span
    valid = []
    for i, s in enumerate(spans_raw):
        if not isinstance(s, dict):
            continue
        text = (s.get("text") or "").strip()
        span_type = (s.get("type") or "").strip().lower()
        if not text or not span_type:
            logger.info("[extract][twopass][p1-parse] Span %d skipped: empty text/type", i)
            continue
        if span_type not in _VALID_SPAN_TYPES:
            logger.info("[extract][twopass][p1-parse] Span %d unknown type '%s', keeping as 'event'",
                        i, span_type)
            span_type = "event"

        flags = s.get("flags", [])
        if not isinstance(flags, list):
            flags = []
        flags = [f for f in flags if isinstance(f, str) and f in _VALID_SPAN_FLAGS]

        role = (s.get("role") or "").strip().lower() if span_type == "person" else ""

        valid.append({
            "text": text,
            "type": span_type,
            "role": role,
            "flags": flags,
        })

    logger.info("[extract][twopass][p1-parse] %d/%d spans valid", len(valid), len(spans_raw))
    return valid


def _extract_spans(answer: str, current_section: Optional[str]) -> tuple[List[dict], Optional[str]]:
    """Pass 1: Call LLM to tag factual spans. Returns (spans, raw_output)."""
    if not _is_llm_available():
        logger.info("[extract][twopass][p1] LLM unavailable — cannot tag spans")
        return [], None

    try:
        from ..llm_interview import _try_call_llm
    except ImportError:
        return [], None

    system, user = _build_span_tagger_prompt(answer, current_section)
    ephemeral_conv_id = f"_span_{_uuid.uuid4().hex[:12]}"

    # Token budget: spans are more compact than full extraction output
    _base_cap = 128
    _compound_cap = 256
    _span_cap = _compound_cap if _is_compound_answer(answer) else _base_cap
    _extract_temp = float(os.getenv("EXTRACTION_TEMP", "0.15"))
    _extract_top_p = float(os.getenv("EXTRACTION_TOP_P", "0.9"))

    logger.info("[extract][twopass][p1] calling LLM max_new=%d temp=%.2f conv=%s",
                _span_cap, _extract_temp, ephemeral_conv_id)
    raw = _try_call_llm(system, user, max_new=_span_cap, temp=_extract_temp,
                        top_p=_extract_top_p, conv_id=ephemeral_conv_id)
    if not raw:
        _mark_llm_unavailable("twopass-p1-empty")
        return [], None

    _mark_llm_available()
    spans = _parse_span_json(raw)
    return spans, raw


# ── Pass 2A: Rule-based span classifier ──────────────────────────────────────

# Person role → repeatable group + relation field mapping
_ROLE_TO_GROUP = {
    "father": ("parents", "father"),
    "mother": ("parents", "mother"),
    "dad": ("parents", "father"),
    "mom": ("parents", "mother"),
    "stepfather": ("parents", "stepfather"),
    "stepmother": ("parents", "stepmother"),
    "step-father": ("parents", "stepfather"),
    "step-mother": ("parents", "stepmother"),
    "brother": ("siblings", "brother"),
    "sister": ("siblings", "sister"),
    "older brother": ("siblings", "brother"),
    "younger brother": ("siblings", "brother"),
    "older sister": ("siblings", "sister"),
    "younger sister": ("siblings", "sister"),
    "big brother": ("siblings", "brother"),
    "big sister": ("siblings", "sister"),
    "little brother": ("siblings", "brother"),
    "little sister": ("siblings", "sister"),
    "twin brother": ("siblings", "brother"),
    "twin sister": ("siblings", "sister"),
    "half brother": ("siblings", "brother"),
    "half sister": ("siblings", "sister"),
    "half-brother": ("siblings", "brother"),
    "half-sister": ("siblings", "sister"),
    "son": ("children", "son"),
    "daughter": ("children", "daughter"),
    "stepson": ("children", "stepson"),
    "stepdaughter": ("children", "stepdaughter"),
    "wife": ("spouse", None),
    "husband": ("spouse", None),
    "spouse": ("spouse", None),
    "partner": ("spouse", None),
    "grandmother": ("grandparents", None),
    "grandfather": ("grandparents", None),
    "grandma": ("grandparents", None),
    "grandpa": ("grandparents", None),
    "maternal grandmother": ("grandparents", None),
    "paternal grandmother": ("grandparents", None),
    "maternal grandfather": ("grandparents", None),
    "paternal grandfather": ("grandparents", None),
    "grandson": ("grandchildren", None),
    "granddaughter": ("grandchildren", None),
    # ── LOOP-01 R2 — Great-grandparents ──────────────────────────────────
    "great-grandmother": ("greatGrandparents", None),
    "great-grandfather": ("greatGrandparents", None),
    "great grandmother": ("greatGrandparents", None),
    "great grandfather": ("greatGrandparents", None),
    "great-grandma": ("greatGrandparents", None),
    "great-grandpa": ("greatGrandparents", None),
    "maternal great-grandmother": ("greatGrandparents", None),
    "paternal great-grandmother": ("greatGrandparents", None),
    "maternal great-grandfather": ("greatGrandparents", None),
    "paternal great-grandfather": ("greatGrandparents", None),
}

# Regex to extract a proper name from span text like "older brother Vincent"
# LOOP-01 R2: added great-grandmother/great-grandfather to cover the deep-ancestry tier.
_NAME_FROM_PERSON = re.compile(
    r'(?:my\s+)?(?:older|younger|big|little|twin|half[- ]?)?'
    r'(?:great[- ]?grand(?:mother|father|ma|pa)|'
    r'brother|sister|dad|mom|father|mother|son|daughter|wife|husband|'
    r'grandmother|grandfather|grandma|grandpa|grandson|granddaughter|'
    r'stepfather|stepmother|stepson|stepdaughter|partner|spouse)\s+'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
    re.IGNORECASE,
)

# Military branch patterns
_MILITARY_BRANCH = re.compile(
    r'\b(Army|Navy|Air Force|Marines|Marine Corps|Coast Guard|National Guard)\b',
    re.IGNORECASE,
)
_MILITARY_RANK = re.compile(
    r'\b(Private|Corporal|Sergeant|Lieutenant|Captain|Major|Colonel|General|'
    r'Admiral|Commander|Ensign|Petty Officer|Chief|Specialist|PFC|SPC|SGT|'
    r'CPL|SSG|SFC|MSG|SGM|CSM|1SG|2LT|1LT|CPT|MAJ|LTC|COL|BG|MG|LTG|GEN)\b',
    re.IGNORECASE,
)

# Faith patterns
_FAITH_DENOM = re.compile(
    r'\b(Catholic|Lutheran|Baptist|Methodist|Presbyterian|Episcopal|'
    r'Pentecostal|Mormon|LDS|Jewish|Muslim|Buddhist|Hindu|Quaker|'
    r'Mennonite|Amish|Congregational|Orthodox|Evangelical|Adventist|'
    r'Unitarian|Jehovah|Assembly of God|Church of Christ|Non-denominational)\b',
    re.IGNORECASE,
)

# Pet species patterns
_PET_SPECIES = re.compile(
    r'\b(dog|cat|horse|pony|bird|fish|rabbit|hamster|turtle|parrot|'
    r'kitten|puppy|golden retriever|labrador|poodle|collie|shepherd|'
    r'beagle|terrier|spaniel|tabby|siamese|persian|canary|parakeet|'
    r'guinea pig|ferret|gecko|iguana|snake|chicken|duck|goat|pig|cow)\b',
    re.IGNORECASE,
)

# Pet name extraction: "named X", "called X", "X the dog", species + name
_PET_NAME = re.compile(
    r'(?:named|called)\s+([A-Z][a-z]+)',
    re.IGNORECASE,
)


def _classify_spans_rules(spans: List[dict], answer: str,
                          current_section: Optional[str]) -> tuple[List[dict], List[dict]]:
    """Pass 2A: Classify spans using deterministic rules.

    Returns (classified_items, unresolved_spans).
    classified_items: [{fieldPath, value, confidence}] ready for downstream.
    unresolved_spans: spans that rules couldn't handle → go to LLM classifier.
    """
    classified = []
    unresolved = []

    # Pre-scan: is there a "born" event span nearby place spans?
    has_birth_event = any(
        s["type"] == "event" and re.search(r'\b(?:born|birth)\b', s["text"], re.IGNORECASE)
        for s in spans
    )

    for span in spans:
        # Skip negated spans — extract nothing for denied experiences
        if "negated" in span.get("flags", []):
            logger.info("[extract][twopass][p2a] Skipping negated span: %s", span["text"][:60])
            continue

        conf = 0.7 if "uncertain" in span.get("flags", []) else 0.9
        is_family = "family_member_not_narrator" in span.get("flags", [])
        matched = False

        # ── Person spans → family group routing ──────────────────────────
        if span["type"] == "person" and span.get("role"):
            role_key = span["role"].lower().strip()
            group_info = _ROLE_TO_GROUP.get(role_key)
            if group_info:
                group, relation_val = group_info
                # Extract name from text
                name_match = _NAME_FROM_PERSON.search(span["text"])
                name = name_match.group(1) if name_match else ""

                if group == "parents":
                    if relation_val:
                        classified.append({"fieldPath": "parents.relation", "value": relation_val, "confidence": conf})
                    if name:
                        classified.append({"fieldPath": "parents.firstName", "value": name, "confidence": conf})
                    matched = True

                elif group == "siblings":
                    if relation_val:
                        classified.append({"fieldPath": "siblings.relation", "value": relation_val, "confidence": conf})
                    if name:
                        classified.append({"fieldPath": "siblings.firstName", "value": name, "confidence": conf})
                    # Birth order from role text
                    if any(w in role_key for w in ("older", "big", "elder")):
                        classified.append({"fieldPath": "siblings.birthOrder", "value": "older", "confidence": 0.7})
                    elif any(w in role_key for w in ("younger", "little")):
                        classified.append({"fieldPath": "siblings.birthOrder", "value": "younger", "confidence": 0.7})
                    elif "twin" in role_key:
                        classified.append({"fieldPath": "siblings.birthOrder", "value": "twin", "confidence": 0.7})
                    matched = True

                elif group == "children":
                    if relation_val:
                        classified.append({"fieldPath": "family.children.relation", "value": relation_val, "confidence": conf})
                    if name:
                        classified.append({"fieldPath": "family.children.firstName", "value": name, "confidence": conf})
                    matched = True

                elif group == "spouse":
                    if name:
                        classified.append({"fieldPath": "family.spouse.firstName", "value": name, "confidence": conf})
                    matched = True

                elif group == "grandparents":
                    # Detect side from role text
                    side = None
                    if "maternal" in role_key or "mother" in role_key:
                        side = "maternal"
                    elif "paternal" in role_key or "father" in role_key:
                        side = "paternal"
                    if side:
                        classified.append({"fieldPath": "grandparents.side", "value": side, "confidence": conf})
                    if name:
                        classified.append({"fieldPath": "grandparents.firstName", "value": name, "confidence": conf})
                    matched = True

                elif group == "greatGrandparents":
                    # LOOP-01 R2: mirror grandparents branch one generation up
                    side = None
                    if "maternal" in role_key:
                        side = "maternal"
                    elif "paternal" in role_key:
                        side = "paternal"
                    if side:
                        classified.append({"fieldPath": "greatGrandparents.side", "value": side, "confidence": conf})
                    if name:
                        classified.append({"fieldPath": "greatGrandparents.firstName", "value": name, "confidence": conf})
                    matched = True

                elif group == "grandchildren":
                    if name:
                        classified.append({"fieldPath": "family.grandchildren.firstName", "value": name, "confidence": conf})
                    matched = True

        # ── Pet spans ────────────────────────────────────────────────────
        elif span["type"] == "pet":
            species_m = _PET_SPECIES.search(span["text"])
            name_m = _PET_NAME.search(span["text"])
            if species_m:
                classified.append({"fieldPath": "pets.species", "value": species_m.group(1).lower(), "confidence": conf})
            if name_m:
                classified.append({"fieldPath": "pets.name", "value": name_m.group(1), "confidence": conf})
            if not species_m and not name_m:
                # Still a pet reference, put whole text as notes
                classified.append({"fieldPath": "pets.notes", "value": span["text"], "confidence": 0.7})
            matched = True

        # ── Place spans ──────────────────────────────────────────────────
        elif span["type"] == "place" and not is_family:
            if has_birth_event:
                classified.append({"fieldPath": "personal.placeOfBirth", "value": span["text"], "confidence": conf})
                matched = True
            # else: could be residence or travel — leave for LLM

        # ── Military spans (narrator only) ───────────────────────────────
        elif span["type"] == "military" and not is_family:
            branch_m = _MILITARY_BRANCH.search(span["text"])
            rank_m = _MILITARY_RANK.search(span["text"])
            if branch_m:
                classified.append({"fieldPath": "military.branch", "value": branch_m.group(1), "confidence": conf})
                matched = True
            if rank_m:
                classified.append({"fieldPath": "military.rank", "value": rank_m.group(1), "confidence": conf})
                matched = True
            if not branch_m and not rank_m:
                # Generic military reference
                classified.append({"fieldPath": "military.significantEvent", "value": span["text"], "confidence": 0.7})
                matched = True

        # ── Faith spans ──────────────────────────────────────────────────
        elif span["type"] == "faith":
            denom_m = _FAITH_DENOM.search(span["text"])
            if denom_m:
                classified.append({"fieldPath": "faith.denomination", "value": denom_m.group(1), "confidence": conf})
                matched = True
            else:
                classified.append({"fieldPath": "faith.role", "value": span["text"], "confidence": 0.7})
                matched = True

        # ── Health spans ─────────────────────────────────────────────────
        elif span["type"] == "health" and not is_family:
            classified.append({"fieldPath": "health.majorCondition", "value": span["text"], "confidence": conf})
            matched = True

        if not matched:
            unresolved.append(span)

    logger.info("[extract][twopass][p2a] Rules classified %d items, %d unresolved",
                len(classified), len(unresolved))
    return classified, unresolved


# ── Pass 2B: LLM classifier for unresolved spans ─────────────────────────────

def _build_field_classifier_prompt(unresolved_spans: List[dict],
                                    current_section: Optional[str]) -> tuple[str, str]:
    """Build system + user prompts for Pass 2B: field classification.

    Shorter than single-pass prompt — no need for extraction examples.
    Only sees unresolved spans + compact field catalog.
    """
    # Build compact catalog
    catalog_lines = []
    for path, meta in EXTRACTABLE_FIELDS.items():
        catalog_lines.append(f'  "{path}": "{meta["label"]}"')
    catalog = "\n".join(catalog_lines)

    system = (
        "Map each span to the best fieldPath from the catalog below.\n"
        "Output a JSON array: [{\"fieldPath\":\"...\",\"value\":\"...\",\"confidence\":0.0-1.0}]\n"
        "\n"
        "Rules:\n"
        "- Use ONLY fieldPaths from this catalog. Do not invent paths.\n"
        "- Skip spans with flags=[\"negated\"] — extract nothing.\n"
        "- For family_member_not_narrator spans, use family-scoped fields "
        "(parents.*, siblings.*, grandparents.*, family.children.*, family.spouse.*)\n"
        "- For person spans, use \"role\" to pick the right group:\n"
        "  role=brother/sister → siblings.*\n"
        "  role=father/mother → parents.*\n"
        "  role=son/daughter → family.children.*\n"
        "  role=wife/husband → family.spouse.*\n"
        "- Confidence: 0.9=clear, 0.7=uncertain flag present\n"
        "- If no fieldPath fits, skip the span entirely\n"
        "- Do NOT extract fields for denied/negated experiences\n"
        "\n"
        f"Available fieldPaths:\n{catalog}\n"
        "\n"
        "Output ONLY the JSON array. No extra text."
    )

    # Format spans for user prompt
    spans_json = json.dumps(unresolved_spans, ensure_ascii=False)

    context_note = ""
    if current_section:
        context_note = f"\nInterview section: {current_section}"

    user = (
        f"Unresolved spans to classify:{context_note}\n\n"
        f"{spans_json}\n\n"
        "Map to fieldPaths as JSON array:"
    )

    return system, user


def _classify_spans_llm(unresolved_spans: List[dict],
                         current_section: Optional[str]) -> List[dict]:
    """Pass 2B: Use LLM to classify spans that rules couldn't handle."""
    if not unresolved_spans:
        return []

    if not _is_llm_available():
        logger.info("[extract][twopass][p2b] LLM unavailable — skipping LLM classification")
        return []

    try:
        from ..llm_interview import _try_call_llm
    except ImportError:
        return []

    system, user = _build_field_classifier_prompt(unresolved_spans, current_section)
    ephemeral_conv_id = f"_classify_{_uuid.uuid4().hex[:12]}"

    _extract_temp = float(os.getenv("EXTRACTION_TEMP", "0.15"))
    _extract_top_p = float(os.getenv("EXTRACTION_TOP_P", "0.9"))
    # Token cap: smaller than single-pass because we're only classifying, not extracting
    _classify_cap = 256

    logger.info("[extract][twopass][p2b] calling LLM for %d unresolved spans, max_new=%d conv=%s",
                len(unresolved_spans), _classify_cap, ephemeral_conv_id)
    raw = _try_call_llm(system, user, max_new=_classify_cap, temp=_extract_temp,
                        top_p=_extract_top_p, conv_id=ephemeral_conv_id)
    if not raw:
        logger.warning("[extract][twopass][p2b] LLM returned empty — no classification")
        return []

    _mark_llm_available()
    # Reuse the existing JSON parser — same [{fieldPath, value, confidence}] format
    items = _parse_llm_json(raw)
    logger.info("[extract][twopass][p2b] LLM classified %d items from %d unresolved spans",
                len(items), len(unresolved_spans))
    return items


def _merge_rule_and_llm_items(rule_items: List[dict], llm_items: List[dict]) -> List[dict]:
    """Merge rule-classified and LLM-classified items, deduplicating by fieldPath+value."""
    seen = set()
    merged = []
    # Rules first — they're higher confidence
    for item in rule_items:
        key = (item["fieldPath"], item["value"].lower().strip())
        if key not in seen:
            seen.add(key)
            merged.append(item)
    # Then LLM items
    for item in llm_items:
        key = (item["fieldPath"], item["value"].lower().strip())
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


# ── Two-pass orchestrator ─────────────────────────────────────────────────────

def _twopass_debug_enabled() -> bool:
    """When True, _extract_via_twopass writes stage artifacts to a JSON file."""
    return os.environ.get("HORNELORE_TWOPASS_DEBUG", "").lower() in ("1", "true", "yes")


def _write_twopass_debug(answer: str, section: Optional[str],
                          spans: List[dict], p1_raw: Optional[str],
                          rule_items: List[dict], unresolved: List[dict],
                          llm_items: List[dict], merged: List[dict],
                          token_cap: int):
    """Append one debug record to docs/reports/twopass_debug_artifacts.jsonl."""
    import datetime
    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "input": {
            "answer": answer,
            "answer_length_words": len(answer.split()),
            "section": section,
            "is_compound": _is_compound_answer(answer),
        },
        "pass1": {
            "token_cap": token_cap,
            "raw_output": p1_raw or "",
            "raw_output_length": len(p1_raw) if p1_raw else 0,
            "looks_truncated": (
                p1_raw is not None and
                not p1_raw.strip().endswith("}") and
                not p1_raw.strip().endswith("]") and
                len(p1_raw.strip()) > 10
            ),
            "span_count": len(spans),
            "spans": spans,
            "type_distribution": {},
            "flag_distribution": {},
        },
        "pass2a_rules": {
            "classified_count": len(rule_items),
            "classified_items": rule_items,
            "unresolved_count": len(unresolved),
            "unresolved_spans": unresolved,
        },
        "pass2b_llm": {
            "classified_count": len(llm_items),
            "classified_items": llm_items,
        },
        "merge": {
            "total_items": len(merged),
            "items": merged,
        },
    }
    # Type/flag distribution
    for s in spans:
        t = s.get("type", "unknown")
        record["pass1"]["type_distribution"][t] = record["pass1"]["type_distribution"].get(t, 0) + 1
        for f in s.get("flags", []):
            record["pass1"]["flag_distribution"][f] = record["pass1"]["flag_distribution"].get(f, 0) + 1

    try:
        debug_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..",
                                   "docs", "reports", "twopass_debug_artifacts.jsonl")
        debug_path = os.path.normpath(debug_path)
        os.makedirs(os.path.dirname(debug_path), exist_ok=True)
        with open(debug_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        logger.info("[extract][twopass][debug] Wrote debug record to %s", debug_path)
    except Exception as e:
        logger.warning("[extract][twopass][debug] Failed to write debug record: %s", e)


def _extract_via_twopass(answer: str, current_section: Optional[str],
                          current_target: Optional[str]) -> tuple[List[dict], Optional[str]]:
    """WO-EX-TWOPASS-01: Two-pass extraction pipeline.

    Pass 1: Tag factual spans (schema-blind)
    Pass 2A: Rule-based classification (deterministic)
    Pass 2B: LLM classification (unresolved spans only)

    Falls back to single-pass on any pass 1 failure.
    """
    _debug = _twopass_debug_enabled()

    # ── Pass 1: Span tagging ─────────────────────────────────────────────
    spans, p1_raw = _extract_spans(answer, current_section)

    # Compute token cap for debug logging (mirror _extract_spans logic)
    _base_cap = 128
    _compound_cap = 256
    _token_cap = _compound_cap if _is_compound_answer(answer) else _base_cap

    if not spans:
        logger.warning("[extract][twopass] Pass 1 returned no spans — falling back to single-pass")
        if _debug:
            _write_twopass_debug(answer, current_section, [], p1_raw,
                                  [], [], [], [], _token_cap)
        return _extract_via_singlepass(answer, current_section, current_target)

    logger.info("[extract][twopass] Pass 1 tagged %d spans", len(spans))

    # ── Pass 2A: Rule-based classification ───────────────────────────────
    rule_items, unresolved = _classify_spans_rules(spans, answer, current_section)

    # ── Pass 2B: LLM classification for unresolved spans ─────────────────
    llm_items = []
    if unresolved:
        llm_items = _classify_spans_llm(unresolved, current_section)

    # ── Merge ────────────────────────────────────────────────────────────
    all_items = _merge_rule_and_llm_items(rule_items, llm_items)

    # ── Debug dump ───────────────────────────────────────────────────────
    if _debug:
        _write_twopass_debug(answer, current_section, spans, p1_raw,
                              rule_items, unresolved, llm_items, all_items,
                              _token_cap)

    if not all_items:
        logger.warning("[extract][twopass] No items after both passes — falling back to single-pass")
        return _extract_via_singlepass(answer, current_section, current_target)

    # Build raw output string for debug/logging (combine both passes)
    raw_combined = f"[TWOPASS] P1_SPANS={len(spans)} P2A_RULES={len(rule_items)} P2B_LLM={len(llm_items)}"
    if p1_raw:
        raw_combined += f"\n--- P1 RAW ---\n{p1_raw}"

    logger.info("[extract][twopass] Final: %d items (rules=%d, llm=%d)",
                len(all_items), len(rule_items), len(llm_items))
    return all_items, raw_combined


def _salvage_truncated_array(raw: str) -> List[dict]:
    """Recover complete top-level {...} objects from a truncated JSON array.

    Used as a last-resort parse strategy when the LLM output was cut off
    mid-string (token budget hit) and the outer array/final string is never
    closed. Scans the prefix of the array character by character, tracking
    object-nesting depth and string-escape state, and returns each complete
    top-level object that parses cleanly. Nothing is fabricated — items are
    pure prefixes of what the LLM actually produced, and they still flow
    through _validate_item / rerouters / guards downstream.
    """
    text = raw.lstrip()
    if not text.startswith("["):
        return []

    items: List[dict] = []
    depth = 0            # {} nesting depth
    in_string = False
    escaped = False
    start = -1

    # Scan contents after the opening '['
    for i in range(1, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        items.append(obj)
                except json.JSONDecodeError:
                    pass
                start = -1
    return items


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

    # Salvage: if every structured parse failed and we have a truncated
    # array (LLM hit token budget mid-string), recover complete top-level
    # {...} objects from the prefix. Pure prefix-recovery — nothing is
    # fabricated; items still run through the full validator pipeline.
    if arr is None:
        salvaged = _salvage_truncated_array(raw)
        if salvaged:
            arr = salvaged
            parse_method = "salvage_truncated"
            logger.info("[extract-parse] Salvaged %d item(s) from truncated JSON array", len(salvaged))

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
            # LOOP-01 R2: grandparents plural↔singular for memorableStory
            "grandparents.memorableStories": "grandparents.memorableStory",
            "family.grandparents.memorableStories": "grandparents.memorableStory",
            # ── LOOP-01 R2 wide — narrative-catch aliases (all sections) ──────
            # personal.nameStory / personal.notes
            "personal.nameOrigin": "personal.nameStory",
            "personal.namingStory": "personal.nameStory",
            "personal.nameMeaning": "personal.nameStory",
            "personal.story": "personal.notes",
            "personal.color": "personal.notes",
            "personal.background": "personal.notes",
            "personal.miscellany": "personal.notes",
            "identity.notes": "personal.notes",
            "identity.nameStory": "personal.nameStory",
            # education.notes
            "education.color": "education.notes",
            "education.background": "education.notes",
            "education.story": "education.notes",
            "education.affiliation": "education.notes",
            "education.schoolNotes": "education.notes",
            "education.schoolColor": "education.notes",
            "school.notes": "education.notes",
            "school.color": "education.notes",
            "school.story": "education.notes",
            # family.children.notes / family.spouse.notes
            "family.children.color": "family.children.notes",
            "family.children.story": "family.children.notes",
            "family.children.personality": "family.children.notes",
            "family.children.memorableStory": "family.children.notes",
            "family.children.memorableStories": "family.children.notes",
            "family.spouse.color": "family.spouse.notes",
            "family.spouse.story": "family.spouse.notes",
            "family.spouse.personality": "family.spouse.notes",
            "family.spouse.memorableStory": "family.spouse.notes",
            "spouse.notes": "family.spouse.notes",
            "spouse.color": "family.spouse.notes",
            "wife.notes": "family.spouse.notes",
            "husband.notes": "family.spouse.notes",
            # faith.notes
            "faith.color": "faith.notes",
            "faith.story": "faith.notes",
            "faith.background": "faith.notes",
            "faith.tradition": "faith.notes",
            "faith.parish": "faith.notes",
            "religion.notes": "faith.notes",
            "religion.color": "faith.notes",
            "church.notes": "faith.notes",
            # hobbies.notes
            "hobbies.color": "hobbies.notes",
            "hobbies.story": "hobbies.notes",
            "hobbies.background": "hobbies.notes",
            "hobbies.memorableStory": "hobbies.notes",
            "leisure.notes": "hobbies.notes",
            # military.notes
            "military.color": "military.notes",
            "military.story": "military.notes",
            "military.memorableStory": "military.notes",
            "military.serviceNotes": "military.notes",
            "service.notes": "military.notes",
            "veteran.notes": "military.notes",
            # health.notes
            "health.color": "health.notes",
            "health.story": "health.notes",
            "health.background": "health.notes",
            "health.memorableStory": "health.notes",
            "medical.notes": "health.notes",
            "wellness.notes": "health.notes",
            # travel.notes
            "travel.color": "travel.notes",
            "travel.story": "travel.notes",
            "travel.memorableStory": "travel.notes",
            "trips.notes": "travel.notes",
            "trips.color": "travel.notes",
            "places.notes": "travel.notes",
            # community.notes
            "community.color": "community.notes",
            "community.story": "community.notes",
            "community.memorableStory": "community.notes",
            "civic.notes": "community.notes",
            "civic.color": "community.notes",
            "volunteer.notes": "community.notes",
            "volunteer.color": "community.notes",
            # ── LOOP-01 R2 — Great-grandparents ───────────────────────────
            # Catch the common LLM-emitted variants and normalize to canonical
            # greatGrandparents.* paths. Singular .memorableStory → plural .memorableStories.
            "greatGrandparents.memorableStory": "greatGrandparents.memorableStories",
            "family.greatGrandparents.firstName": "greatGrandparents.firstName",
            "family.greatGrandparents.lastName": "greatGrandparents.lastName",
            "family.greatGrandparents.maidenName": "greatGrandparents.maidenName",
            "family.greatGrandparents.birthDate": "greatGrandparents.birthDate",
            "family.greatGrandparents.birthPlace": "greatGrandparents.birthPlace",
            "family.greatGrandparents.side": "greatGrandparents.side",
            "family.greatGrandparents.ancestry": "greatGrandparents.ancestry",
            "family.greatGrandparents.memorableStory": "greatGrandparents.memorableStories",
            "family.greatGrandparents.memorableStories": "greatGrandparents.memorableStories",
            "great-grandfather.firstName": "greatGrandparents.firstName",
            "great-grandfather.lastName": "greatGrandparents.lastName",
            "great-grandfather.birthDate": "greatGrandparents.birthDate",
            "great-grandfather.birthPlace": "greatGrandparents.birthPlace",
            "great-grandfather.ancestry": "greatGrandparents.ancestry",
            "great-grandmother.firstName": "greatGrandparents.firstName",
            "great-grandmother.lastName": "greatGrandparents.lastName",
            "great-grandmother.maidenName": "greatGrandparents.maidenName",
            "great-grandmother.birthDate": "greatGrandparents.birthDate",
            "great-grandmother.birthPlace": "greatGrandparents.birthPlace",
            "great-grandmother.ancestry": "greatGrandparents.ancestry",
            "greatGrandfather.firstName": "greatGrandparents.firstName",
            "greatGrandfather.lastName": "greatGrandparents.lastName",
            "greatGrandfather.birthDate": "greatGrandparents.birthDate",
            "greatGrandfather.birthPlace": "greatGrandparents.birthPlace",
            "greatGrandfather.ancestry": "greatGrandparents.ancestry",
            "greatGrandmother.firstName": "greatGrandparents.firstName",
            "greatGrandmother.lastName": "greatGrandparents.lastName",
            "greatGrandmother.maidenName": "greatGrandparents.maidenName",
            "greatGrandmother.birthDate": "greatGrandparents.birthDate",
            "greatGrandmother.birthPlace": "greatGrandparents.birthPlace",
            "greatGrandmother.ancestry": "greatGrandparents.ancestry",
            "ancestors.firstName": "greatGrandparents.firstName",
            "ancestors.lastName": "greatGrandparents.lastName",
            "ancestors.birthDate": "greatGrandparents.birthDate",
            "ancestors.birthPlace": "greatGrandparents.birthPlace",
            "ancestors.ancestry": "greatGrandparents.ancestry",
            "ancestors.memorableStory": "greatGrandparents.memorableStories",
            "ancestors.memorableStories": "greatGrandparents.memorableStories",
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

            # ── LOOP-01 R3 — Alias fills from api.log audit ────────────────
            # Near-miss paths the LLM emits that map cleanly onto canonical
            # fields (or new R3 fields above in EXTRACTABLE_FIELDS). These
            # save ~60+ rejections per eval run.

            # family.parents.* → parents.* (dominant family-prefix variant)
            "family.parents.firstName":  "parents.firstName",
            "family.parents.middleName": "parents.middleName",
            "family.parents.lastName":   "parents.lastName",
            "family.parents.maidenName": "parents.maidenName",
            "family.parents.relation":   "parents.relation",
            "family.parents.occupation": "parents.occupation",
            "family.parents.birthDate":  "parents.birthDate",
            "family.parents.birthPlace": "parents.birthPlace",

            # parents.* date/place/misc variants (LLM alternates phrasings)
            "parents.dateOfBirth":       "parents.birthDate",
            "parents.placeOfBirth":      "parents.birthPlace",
            "parents.dateOfDeath":       "parents.deathDate",
            "parents.workplace":         "parents.occupation",
            "parents.alternateName":     "parents.preferredName",
            "parents.characteristic":    "parents.notes",
            "parents.license":           "parents.notes",
            "parents.deliverer":         "parents.notes",
            "parents.born":              "parents.birthPlace",
            "parents.childRelation":     "parents.relation",
            "parents.mother.firstName":  "parents.firstName",
            "parents.mother.maidenName": "parents.maidenName",
            "parents.mother.lastName":   "parents.lastName",
            "parents.father.firstName":  "parents.firstName",
            "parents.father.lastName":   "parents.lastName",

            # grandparents.* variants
            "grandparents.dateOfBirth":       "grandparents.birthDate",
            "grandparents.placeOfBirth":      "grandparents.birthPlace",
            "grandparents.placeOfBirthFather":"grandparents.birthPlace",
            "grandparents.countryOfOrigin":   "grandparents.ancestry",
            "grandparents.siblingCount":      "grandparents.memorableStory",
            "grandparents.birthAge":          "grandparents.birthDate",
            "grandparents.sibling":           "grandparents.memorableStory",
            "grandparents.parentFirstName":   "greatGrandparents.firstName",

            # siblings.* variants
            "siblings.dateOfBirth":                  "siblings.birthDate",
            "siblings.placeOfBirth":                 "siblings.birthPlace",
            "siblings.siblingRelationship":          "siblings.relation",
            "siblings.reactionToOutdoorActivities":  "siblings.uniqueCharacteristics",

            # greatGrandparents.* variants (schema has birthDate/birthPlace;
            # LLM sometimes emits dateOfBirth/placeOfBirth)
            "greatGrandparents.dateOfBirth":  "greatGrandparents.birthDate",
            "greatGrandparents.placeOfBirth": "greatGrandparents.birthPlace",

            # family.spouse.* variants and in-law spill-over
            "family.spouse.familyHistory":           "family.spouse.notes",
            "family.spouse.characteristic":          "family.spouse.notes",
            "family.spouse.narratorAgeAtMarriage":   "family.spouse.ageAtMarriage",
            "family.spouse.parent.firstName":        "family.spouse.notes",
            "family.spouse.parent.name":             "family.spouse.notes",
            "family.spouse.parent.placeOfWork":      "family.spouse.notes",
            "family.spouse.child.placeOfBirth":      "family.children.placeOfBirth",
            "family.spouse.child.hometown":          "family.children.placeOfBirth",
            "family.spouse.child.activity":          "family.children.notes",
            "family.spouse.child.pet":               "family.children.notes",
            "spouse.placeOfBirth":                   "family.spouse.placeOfBirth",

            # community.* variants → R3 additions or existing fields
            "community.numberOfMembers":    "community.memberCount",
            "community.leadershipDuration": "community.yearsActive",
            "community.learnings":          "community.notes",
            "community.influentialPerson":  "community.notes",
            "community.values":             "faith.values",

            # family.member.* — generic "relative" catch-alls
            "family.member":              "parents.notableLifeEvents",
            "family.member.name":         "parents.firstName",
            "family.member.relationship": "parents.relation",
            "family.member.dateOfBirth":  "parents.birthDate",
            "family.relative":            "parents.notableLifeEvents",

            # Ancestor-scoped military — route parents.parents.military.*
            # (LLM's instinct for "my great-great-grandfather's service") onto
            # the new greatGrandparents.military* fields so negation-guard
            # (which is narrator-scoped on military.*) cannot strip them.
            "parents.parents.military.branch":              "greatGrandparents.militaryBranch",
            "parents.parents.military.yearsOfService":      "greatGrandparents.militaryEvent",
            "parents.parents.military.unit":                "greatGrandparents.militaryUnit",
            "parents.parents.military.deploymentLocation":  "greatGrandparents.militaryEvent",
            "parents.parents.military.rank":                "greatGrandparents.militaryEvent",
            "greatGrandparents.military.branch":            "greatGrandparents.militaryBranch",
            "greatGrandparents.military.unit":              "greatGrandparents.militaryUnit",
            "greatGrandparents.military.yearsOfService":    "greatGrandparents.militaryEvent",
            "greatGrandparents.military.deploymentLocation":"greatGrandparents.militaryEvent",
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


# ── LOOP-01 R4 Patch A — answer-dump length cap ─────────────────────────────
# R3b master-eval root cause: 13 of 54 failing cases had the LLM dump the entire
# narrator answer into a scalar field's value (e.g. grandparents.side=224-char
# monologue, family.marriageDate=622-char paragraph, residence.place=510-char
# anecdote). The LLM falls back to "here is the relevant passage" when it
# can't cleanly extract the fact. These hallucinated long values pollute the
# graph. Cap scalar suffixes hard at 120 chars / 2 sentences; cap narrative
# suffixes at 500 chars (big enough for legit memorableStory entries).
_SCALAR_VALUE_SUFFIXES = frozenset({
    # Names
    "firstName", "middleName", "lastName", "maidenName",
    "preferredName", "nickname", "fullName", "name", "nameStory",
    # Dates / years
    "dateOfBirth", "dateOfDeath", "birthDate", "deathDate",
    "birthYear", "deathYear", "startYear", "endYear",
    "marriageDate", "yearEnlisted", "yearDischarged",
    "yearStarted", "yearEnded", "age", "ageAtMarriage",
    # Places
    "placeOfBirth", "placeOfDeath", "birthPlace",
    "marriagePlace", "destination",
    # Enumerated / short identifiers
    "birthOrder", "gender", "relation", "relationship",
    "branch", "denomination", "rank", "status", "species", "type",
    "side", "role", "organization", "ancestry",
    "yearsActive", "yearsOfService", "yearsOfMarriage",
    "memberCount",
})
_NARRATIVE_VALUE_SUFFIXES = frozenset({
    "notes", "significantEvent", "memorableStory", "memorableStories",
    "notableLifeEvents", "lifeLessons", "desiredStory",
    "touchstoneMemory", "significantTrip", "lifestyleChange",
    "milestone", "majorCondition", "currentMedications",
    "cognitiveChange", "firstMemory", "uniqueCharacteristics",
    "values", "story", "background", "personality",
    "characteristic", "deploymentLocation", "significantMoment",
    "hobbies", "personalChallenges", "unfinishedDreams",
    "careerProgression", "earlyCareer", "higherEducation",
    "schooling", "training", "purpose", "militaryEvent",
    "militaryUnit", "militaryBranch",
})
_SCALAR_VALUE_MAX_CHARS = 120
_NARRATIVE_VALUE_MAX_CHARS = 500
_SENTENCE_BOUNDARY = re.compile(r'[.!?]\s+[A-Z]')


def _apply_value_length_cap(items: List[dict]) -> List[dict]:
    """LOOP-01 R4 Patch A — reject items whose value is an answer-dump.

    Scalar suffixes (name/date/place/role/side/etc.) are capped at
    ``_SCALAR_VALUE_MAX_CHARS`` and must not contain a sentence boundary
    (period + space + capital). Narrative suffixes (notes, memorableStory,
    etc.) are capped at ``_NARRATIVE_VALUE_MAX_CHARS``. Unknown suffixes
    are passed through unchanged.
    """
    if not items:
        return items
    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        val = it.get("value", "")
        if not isinstance(val, str) or not val:
            out.append(it)
            continue
        suffix = fp.rsplit(".", 1)[-1] if "." in fp else fp
        n = len(val)
        if suffix in _SCALAR_VALUE_SUFFIXES:
            has_sentence_boundary = bool(_SENTENCE_BOUNDARY.search(val))
            if n > _SCALAR_VALUE_MAX_CHARS or has_sentence_boundary:
                logger.info(
                    "[extract][R4-A answer-dump] dropping %s (scalar, %d chars, "
                    "sentence_boundary=%s): %r…",
                    fp, n, has_sentence_boundary, val[:80],
                )
                continue
        elif suffix in _NARRATIVE_VALUE_SUFFIXES:
            if n > _NARRATIVE_VALUE_MAX_CHARS:
                logger.info(
                    "[extract][R4-A answer-dump] dropping %s (narrative, "
                    "%d chars > %d): %r…",
                    fp, n, _NARRATIVE_VALUE_MAX_CHARS, val[:80],
                )
                continue
        out.append(it)
    return out


# ── LOOP-01 R4 Patch E — relation-scope safety guard ────────────────────────
# R3b master-eval had 2 must_not_write violations, both this shape:
#   - case_008: narrator describes uncle → extractor wrote family.children.*
#   - case_094: narrator describes sibling → extractor wrote parents.*
# Fix: if the answer mentions uncle/aunt/nephew/niece/cousin WITHOUT a
# "my son/daughter/child/kid" anchor, reject family.children.*. Symmetric
# rule for parents.* vs sibling cues. Graph-contamination safety.
_CHILD_ANCHORS = re.compile(
    r"\bmy\s+(?:son|daughter|child|children|kid|kids|boy|girl|baby|"
    r"firstborn|little one|oldest|youngest)\b",
    re.IGNORECASE,
)
_PARENT_ANCHORS = re.compile(
    r"\bmy\s+(?:mother|father|mom|dad|mama|papa|ma|pa|mum|parents?)\b",
    re.IGNORECASE,
)
_CHILD_CONFLICT_CUES = re.compile(
    r"\b(?:uncle|aunt|nephew|niece|cousin|"
    r"great[- ]?uncle|great[- ]?aunt|step[- ]?uncle|step[- ]?aunt)\b",
    re.IGNORECASE,
)
_SIBLING_CONFLICT_CUES = re.compile(
    r"\bmy\s+(?:brother|sister|siblings?|twin|"
    r"older brother|younger brother|older sister|younger sister|"
    r"big brother|big sister|little brother|little sister|"
    r"half[- ]?brother|half[- ]?sister|step[- ]?brother|step[- ]?sister)\b",
    re.IGNORECASE,
)


def _apply_relation_scope_guard(items: List[dict], answer: str) -> List[dict]:
    """LOOP-01 R4 Patch E — reject family.children.* / parents.* extractions
    when the answer's dominant relational cue doesn't match the written path.

    Fires only when the conflict cue is present AND the legitimating anchor
    is absent — a conservative rule designed to eliminate must_not_write
    violations without touching healthy extractions.
    """
    if not items or not answer:
        return items
    has_child_anchor = bool(_CHILD_ANCHORS.search(answer))
    has_parent_anchor = bool(_PARENT_ANCHORS.search(answer))
    has_child_conflict = bool(_CHILD_CONFLICT_CUES.search(answer))
    has_sibling_conflict = bool(_SIBLING_CONFLICT_CUES.search(answer))

    if not (has_child_conflict or has_sibling_conflict):
        return items
    if has_child_anchor and has_parent_anchor:
        # Dense family answer — narrator is describing both kids and parents,
        # don't interfere; the router's section-aware logic is better equipped.
        return items

    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        if (
            fp.startswith("family.children.")
            and has_child_conflict
            and not has_child_anchor
        ):
            logger.info(
                "[extract][R4-E relation-scope] dropping %s=%r "
                "(answer has uncle/aunt/nephew cue without my-son/daughter anchor)",
                fp, it.get("value"),
            )
            continue
        if (
            fp.startswith("parents.")
            and has_sibling_conflict
            and not has_parent_anchor
        ):
            logger.info(
                "[extract][R4-E relation-scope] dropping %s=%r "
                "(answer has my-brother/sister cue without my-mother/father anchor)",
                fp, it.get("value"),
            )
            continue
        out.append(it)
    return out


# ── WO-EX-TURNSCOPE-01 — follow-up turn-scope filter (task #72) ─────────────
# Problem: on a follow-up turn whose target resolves to one family-relations
# branch root (e.g. siblings.*), the extractor sometimes writes to adjacent
# entity-role branches (parents.*, family.children.*, etc.) purely because
# relational names from those branches appeared as references in the reply.
# See master_loop01_r4f.json case_094 (janice-josephine-horne sibling_detail
# → wrote parents.firstName = "Ervin" off "Kent's parents' wedding
# anniversary. Ervin and Leila Horne's anniversary.")
#
# Fix: when current_target_path resolves to a member of the family-relations
# cluster below, drop any extracted item whose fieldPath lives in a DIFFERENT
# member of that cluster. Items outside the cluster (personal.*, residence.*,
# earlyMemories.*, pets.*, education.*, community.*, military.*, travel.*,
# health.*, laterYears.*, family.marriage*, etc.) pass through unchanged so
# that cross-cluster may_extracts in passing follow-up cases (089 pets/
# earlyMemories, 091 family.marriageNotes) remain intact.
#
# Runtime: no-op when current_target_path is None or resolves outside the
# cluster. No regex; cost is one prefix walk per item.
#
# Research tie: Order-to-Space Bias / entity-role binding — cf. loop01
# research_synthesis.md §2.7 (OINL) and R6 "Upstream field-scope filter"
# candidate. This is the scoped-down runtime variant.

# Ordered longest-first so that `family.children` and `family.spouse` win
# the prefix match over the bare `family` segment (which is intentionally
# NOT a cluster member — family.marriage* and family.marriageNotes are
# out-of-cluster by design).
_FAMILY_RELATIONS_ROOTS = (
    "family.children",
    "family.spouse",
    "greatGrandparents",
    "grandparents",
    "siblings",
    "parents",
)


def _resolve_turn_scope_branch(current_target_path: Optional[str]) -> Optional[str]:
    """Return the family-relations branch root of current_target_path, or
    None if the target is outside the family-relations cluster.

    Longest-prefix match: 'family.children.firstName' → 'family.children',
    'siblings.uniqueCharacteristics' → 'siblings'.
    """
    if not current_target_path:
        return None
    for root in _FAMILY_RELATIONS_ROOTS:
        if current_target_path == root or current_target_path.startswith(root + "."):
            return root
    return None


def _fieldpath_branch_root(field_path: str) -> Optional[str]:
    """Return the family-relations branch root of a field_path, or None
    if the path is outside the family-relations cluster."""
    if not field_path:
        return None
    for root in _FAMILY_RELATIONS_ROOTS:
        if field_path == root or field_path.startswith(root + "."):
            return root
    return None


def _apply_turn_scope_filter(
    items: List[dict],
    current_target_path: Optional[str],
) -> List[dict]:
    """WO-EX-TURNSCOPE-01 — entity-role binding enforcement on follow-up turns.

    When ``current_target_path`` resolves to a family-relations branch root,
    drop any item whose fieldPath resolves to a DIFFERENT family-relations
    branch root. Items outside the cluster pass through unchanged.

    No-op when ``current_target_path`` is None or outside the cluster.
    """
    if not items:
        return items
    target_root = _resolve_turn_scope_branch(current_target_path)
    if target_root is None:
        return items

    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        item_root = _fieldpath_branch_root(fp)
        if item_root is not None and item_root != target_root:
            try:
                logger.info(
                    "[extract][turnscope] DROP fieldPath=%s value=%r "
                    "target_branch=%s item_branch=%s reason=cross_branch_bleed",
                    fp, str(it.get("value", ""))[:80], target_root, item_root,
                )
            except Exception:
                pass
            continue
        out.append(it)
    return out


# ── LOOP-01 R4 Patch F — contrast-affirmation exception for negation-guard ──
# R3b + log evidence: when the narrator says "I'm not X, (more of a) Y"
# the guard strips BOTH X and Y. Patch 4's ancestor-scope check doesn't
# apply because the speaker is the narrator themselves. Preserve the
# affirmative half Y by collecting sentence-scoped affirmative clauses;
# any extraction whose value lives inside one of those clauses is kept.
_DENIAL_WORDS = re.compile(
    r"\b(?:not|never|don'?t|didn'?t|doesn'?t|wasn'?t|isn'?t|haven'?t|no(?=\s))\b",
    re.IGNORECASE,
)
_CONTRAST_MARKER = re.compile(
    r"\b(?:but|more of a|more like|just (?:a )?|"
    r"I'?m (?:more|just )?|I am (?:more|just )?|I'?ve been|I was)\s+",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _collect_contrast_affirmations(answer: str) -> list:
    """Return sentence-scoped affirmative clauses from the answer
    (lowercased).

    LOOP-01 R4 Patch F — NARROWED after R4 readout.

    A sentence contributes an affirmative ONLY when it contains BOTH a
    denial marker AND a contrast marker; the preserved text is the
    portion after the LAST contrast marker in that sentence. The
    original Patch F also treated any non-denial sentence as fully
    affirmative, which over-preserved narrator "nothing to report"
    answers — each hedge-affirmation sentence ("I've been pretty
    healthy", "I was tough", "I was more of a one-on-one person")
    leaked into forbidden health/community writes despite the
    negation-guard's denial patterns correctly firing on the whole
    answer. See loop01_r4_eval_readout.md (cases 038, 056, 100).

    Preserved pattern (same-sentence "not X, but Y"):

    1. ``not X, (but|more of a) Y``        → Y kept
    2. ``never X, just Y``                 → Y kept

    NO LONGER preserved (ambiguous cross-sentence):

    1. ``not X. I'm Y.``                   → narrator-denied category wins
    2. ``Y. I don't X.``                   → narrator-denied category wins

    If the cross-sentence contrast shape turns out to be common in
    real oral histories, revisit by introducing a separate
    "contrast-marker-in-sentence-without-denial-immediately-after-
    a-denial-sentence" rule rather than by reintroducing the
    blanket non-denial-sentence branch.
    """
    if not answer:
        return []
    affirmatives: list = []
    for raw in _SENTENCE_SPLIT.split(answer.strip()):
        s = raw.strip()
        if not s:
            continue
        if not _DENIAL_WORDS.search(s):
            # Narrowed: non-denial sentences no longer contribute
            # affirmatives. They are judged by the negation-guard's
            # category-level denial patterns alone.
            continue
        # Sentence has a denial; keep text after the last contrast marker.
        m = None
        for hit in _CONTRAST_MARKER.finditer(s):
            m = hit  # keep the last hit — "not X, but Y" -> Y
        if m is not None:
            affirm = s[m.end():].strip().strip('.,;:"\'').lower()
            if len(affirm) >= 3:
                affirmatives.append(affirm)
    return affirmatives


def _value_in_affirmative_clause(value, affirmatives: list) -> bool:
    """True if ``value`` appears as a substring of any affirmative clause."""
    if not value or not affirmatives:
        return False
    val_lower = str(value).lower().strip().strip('.,;:"\'')
    if not val_lower:
        return False
    for aff in affirmatives:
        if val_lower in aff:
            return True
    return False


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


# ── LOOP-01 R4 Patch H — write-time value normalisation ─────────────────
# Normalises certain scalar field values to their canonical surface form so
# downstream scorers and graph consumers see consistent strings regardless
# of how the narrator phrased it. Runs BEFORE negation-guard so normalised
# values are still matched against ancestor-context / affirmative-clause
# detectors on the original answer text.
#
# Covers:
#   - *.birthOrder: map "1st/first/oldest/eldest" → "first" etc.
#   - dates on *.birthDate / *.deathDate / family.marriageDate:
#       strip surrounding prose like "born in 1929, January 15th" → "1929-01-15"
#       when the raw value is already parseable; otherwise leave as-is.
#   - *.firstName / *.lastName: strip surrounding punctuation + quoting,
#       collapse whitespace, Title-case if all-lowercase.

_BIRTHORDER_CANON = {
    # narrator-side ordinals → canonical lowercase ordinal label
    "1st": "first", "first": "first", "firstborn": "first",
    "oldest": "oldest", "eldest": "oldest",
    "2nd": "second", "second": "second",
    "3rd": "third", "third": "third",
    "4th": "fourth", "fourth": "fourth",
    "5th": "fifth", "fifth": "fifth",
    "6th": "sixth", "sixth": "sixth",
    "7th": "seventh", "seventh": "seventh",
    "8th": "eighth", "eighth": "eighth",
    "9th": "ninth", "ninth": "ninth",
    "10th": "tenth", "tenth": "tenth",
    "middle": "middle",
    "youngest": "youngest", "baby": "youngest",
    "last": "youngest", "last-born": "youngest", "lastborn": "youngest",
    "only child": "only",
    "older": "older", "younger": "younger",
    "twin": "twin",
}

_MONTH_MAP = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}

_DATE_ISO_RX   = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_YEAR_RX  = re.compile(r"\b(1[89]\d{2}|20[0-4]\d)\b")
_DATE_MDY_RX   = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)

_DATE_FIELD_SUFFIXES = frozenset({"birthDate", "deathDate", "marriageDate"})


def _normalize_birthorder_value(raw: str) -> str:
    """Return canonical birthOrder surface form, or the raw value unchanged
    if no mapping applies."""
    if not raw:
        return raw
    norm = raw.strip().lower().strip(".,;:\"'")
    norm = re.sub(r"^(?:the |an? )", "", norm)
    return _BIRTHORDER_CANON.get(norm, raw)


def _normalize_date_value(raw: str) -> str:
    """Best-effort ISO-ish date normalisation.

    Conservative: if the raw value already looks ISO (YYYY-MM-DD), keep it.
    If it matches "Month D, YYYY" or "Month Dth YYYY", convert to YYYY-MM-DD.
    If it's just a year, return the year as-is. Otherwise return unchanged
    (so unstructured prose still survives)."""
    if not raw:
        return raw
    s = raw.strip().strip(".,;:\"'")
    # Already ISO — done
    m = _DATE_ISO_RX.search(s)
    if m:
        return m.group(0)
    # Month Day, Year
    m = _DATE_MDY_RX.search(s)
    if m:
        month = _MONTH_MAP.get(m.group(1).lower().rstrip("."))
        if month:
            day = m.group(2).zfill(2)
            year = m.group(3)
            return f"{year}-{month}-{day}"
    # Year only
    m = _DATE_YEAR_RX.search(s)
    if m and len(s) <= 10:
        return m.group(0)
    return raw


def _normalize_name_value(raw: str) -> str:
    """Collapse whitespace, strip surrounding punctuation/quotes, Title-case
    if all lowercase. Leaves mixed-case names alone (preserves McArthur, D'Amico)."""
    if not raw:
        return raw
    s = raw.strip().strip(".,;:\"'").strip()
    s = re.sub(r"\s+", " ", s)
    if s and s == s.lower():
        s = s.title()
    return s


def _apply_write_time_normalisation(items: List[dict]) -> List[dict]:
    """R4 Patch H: normalise selected scalar surface forms in place.

    Mutates a copy of each item (original dict is untouched). Only applied
    to fields where normalisation is safe; other items pass through.
    """
    if not items:
        return items
    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        raw = it.get("value", "")
        if not isinstance(raw, str):
            out.append(it)
            continue
        suffix = fp.rsplit(".", 1)[-1] if "." in fp else fp
        new_val = raw
        if suffix == "birthOrder":
            new_val = _normalize_birthorder_value(raw)
        elif suffix in _DATE_FIELD_SUFFIXES:
            new_val = _normalize_date_value(raw)
        elif suffix in ("firstName", "lastName", "preferredName"):
            new_val = _normalize_name_value(raw)
        if new_val != raw:
            logger.info(
                "[extract][R4-H] normalise %s: %r → %r",
                fp, raw, new_val,
            )
            nd = dict(it)
            nd["value"] = new_val
            out.append(nd)
        else:
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

# LOOP-01 R4 Patch I — higher-education value cues.
# When an item lands on education.schooling but the value references a
# college/university/degree, reroute to education.higherEducation.
_HIGHERED_VALUE_CUES = re.compile(
    r"\b(?:college|university|bachelor|master|phd|doctorate|associate\'?s?|"
    r"graduate school|grad school|community college|state college|"
    r"business college|nursing school|medical school|law school|"
    r"technical college|vocational school|trade school|"
    r"BA|BS|BSc|MA|MS|MBA|JD|MD|EdD|DDS)\b",
    re.IGNORECASE,
)

# LOOP-01 R4 Patch I — ancestry-phrase value cues.
# When an item lands on personal.notes or personal.heritage but the value
# obviously describes ethnic ancestry, reroute to grandparents.ancestry.
_ANCESTRY_VALUE_CUES = re.compile(
    r"\b(?:germans? from russia|volga german|black sea german|"
    r"alsace[- ]lorraine|french[- ]canadian|pennsylvania dutch|"
    r"scotch[- ]irish|irish[- ]american|italian[- ]american|"
    r"ashkenazi|sephardic|bohemian|moravian|slovak|polish|"
    r"norwegian|swedish|finnish|danish|german|irish|french|italian|"
    r"czech|ukrainian|russian|mennonite|amish)\b",
    re.IGNORECASE,
)


# LOOP-01 R4 Patch D — narrator first-person birthOrder rerouter cues.
# Matches "I was the youngest", "I'm the second", "I was the middle one", etc.
# When one of these phrases is present, an item with fieldPath=siblings.birthOrder
# whose value matches the captured position word should be rerouted to
# personal.birthOrder (the narrator's own order among siblings), not written
# as a sibling's birth order.
_NARRATOR_BIRTHORDER_CUES = re.compile(
    r"\bI(?:'?m| was| am)\s+the\s+"
    r"(youngest|oldest|eldest|middle|baby|firstborn|only child|"
    r"second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|"
    r"last|last[- ]born)\b",
    re.IGNORECASE,
)


# WO-QB-GENERATIONAL-01B: touchstone event detection for cultural.touchstoneMemory
# Extended (01B surgical pass): drive-in / first-computer / first-cell-phone cues added.
# Drive-in stays here so that any fallback routing to laterYears.significantEvent still
# earns a cultural.touchstoneMemory dup; the preferred route (hobbies.hobbies +
# residence.place) is taught via a dedicated few-shot in _build_extraction_prompt().
_TOUCHSTONE_EVENT_CUES = re.compile(
    r'\b(?:moon landing|apollo|landed on the moon|walked on the moon'
    r'|vietnam|draft(?:ed)?|gas lines|energy crisis|oil crisis'
    r'|challenger|shuttle'
    r'|9[\-/]11|september 11|twin towers|world trade'
    r'|covid|pandemic|lockdown|quarantine'
    r'|berlin wall|wall came down|wall fell'
    r'|kennedy|jfk|president.*shot|assassination'
    r'|watergate|nixon resign'
    r'|sputnik|space race'
    r'|artemis|going back to the moon|return.{0,10}moon'
    r'|drive[\- ]in|first computer|first pc|first personal computer'
    r'|first cell ?phone)\b',
    re.IGNORECASE,
)

# WO-QB-GENERATIONAL-01B: witness-memory cues — narrator was THERE, not just
# mentioning an event in passing. Required alongside event keywords to prevent
# false touchstone duplicates on sentences like "my son was born during COVID".
_WITNESS_MEMORY_CUES = re.compile(
    r'\b(?:I remember|we were|we watched|we sat|we saw|we quit|we stopped'
    r'|we had to|we couldn\'?t|we started|we used to|we\'?d (?:sit|watch|listen|go|drive)'
    r'|when (?:it|they|that) happened|got used to'
    r'|watching|heard about it|heard (?:the|about)|where were you|where I was'
    r'|the whole family|in the living room|on (?:the |a )?(?:TV|television|radio|set)'
    r'|sitting in|stood there|couldn\'?t believe|never forget'
    r'|the day (?:it|they|that|we)|that (?:morning|evening|night|day)'
    r'|made.{0,10}(?:smaller|different|harder|quieter|changed)'
    r'|everything (?:changed|stopped|shut)|world (?:changed|stopped|felt))\b',
    re.IGNORECASE,
)

# WO-QB-GENERATIONAL-01B: story-priority language for laterYears.desiredStory
_STORY_PRIORITY_CUES = re.compile(
    r'(?:want.{0,15}family to hear|only had time for|stories? I\'?d'
    r'|want.{0,10}on the record|want.{0,10}written down|want.{0,10}told'
    r'|if I (?:could|only)|three stories|important.{0,10}to tell'
    r'|before.{0,15}(?:too late|gone|I\'?m gone|I go))',
    re.IGNORECASE,
)

# Path mapping: (source_prefix, target_prefix) for each rerouter
# LOOP-01 R4 Patch C — pets.notes splitter.
# Matches compact descriptors like "collie named Laddie", "Ivan, our family dog",
# "a cat named Whiskers", "dog called Rex". Captures name + species so the
# rerouter can split one pets.notes item into pets.name + pets.species.
_PETS_NOTES_SPLIT = re.compile(
    r"^\s*(?:a |an |our |my |the )?"
    r"(?:(?P<species1>dog|cat|horse|bird|parrot|rabbit|hamster|guinea pig|gerbil|"
    r"fish|turtle|tortoise|snake|lizard|ferret|chicken|duck|goat|pig|cow|pony)"
    r"\s+(?:named|called|we called)\s+(?P<name1>[A-Z][a-zA-Z'\-]+)"
    r"|(?P<name2>[A-Z][a-zA-Z'\-]+),?\s+(?:our |my |the )?"
    r"(?P<species2>dog|cat|horse|bird|parrot|rabbit|hamster|guinea pig|gerbil|"
    r"fish|turtle|tortoise|snake|lizard|ferret|chicken|duck|goat|pig|cow|pony)"
    r")\s*$",
    re.IGNORECASE,
)

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
    pets_splits = []  # LOOP-01 R4 Patch C — items emitted from pets.notes splits

    # LOOP-01 R4 Patch D — collect narrator-first-person birth-order values
    # once per answer so per-item reroute decisions are cheap.
    narrator_birthorders = {
        m.group(1).lower() for m in _NARRATOR_BIRTHORDER_CUES.finditer(answer)
    }

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

        # ── 1b. LOOP-01 R4 Patch C — pets.notes splitter ────────────────
        # If pets.notes looks like "dog named Ivan" / "Ivan, our family dog",
        # split into pets.name + pets.species. Keep the original pets.notes
        # only if it also carries extra colour beyond the name+species match.
        elif fp == "pets.notes":
            m = _PETS_NOTES_SPLIT.match(val.strip())
            if m:
                name = m.group("name1") or m.group("name2")
                species = (m.group("species1") or m.group("species2") or "").lower()
                if name and species:
                    conf = it.get("confidence", 0.8)
                    pets_splits.append({
                        "fieldPath": "pets.name",
                        "value": name,
                        "confidence": conf,
                    })
                    pets_splits.append({
                        "fieldPath": "pets.species",
                        "value": species,
                        "confidence": conf,
                    })
                    logger.info(
                        "[extract][rerouter] R4-C pets.notes split → pets.name=%r, pets.species=%r",
                        name, species,
                    )
                    # Drop the original pets.notes since the content is now
                    # fully captured by name+species (it was just the descriptor).
                    continue

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

        # ── 4b. LOOP-01 R4 Patch D — narrator birthOrder rerouter ────────
        # When narrator said "I was the youngest/middle/oldest" and the LLM
        # wrote it as siblings.birthOrder, reroute to personal.birthOrder.
        elif fp == "siblings.birthOrder":
            val_norm = val.strip().lower().rstrip(".,;:")
            # Strip leading articles / descriptors
            val_norm = re.sub(r"^(?:the |an? )", "", val_norm)
            if val_norm in narrator_birthorders:
                logger.info(
                    "[extract][rerouter] R4-D birthOrder: siblings.birthOrder → "
                    "personal.birthOrder (val=%r, narrator-first-person cue detected)",
                    val[:60],
                )
                it["fieldPath"] = "personal.birthOrder"

        # ── 4c. LOOP-01 R4 Patch I — higher-education vs schooling ───────
        # If LLM wrote education.schooling but the value clearly references a
        # college/university/degree, reroute to education.higherEducation.
        elif fp == "education.schooling":
            if _HIGHERED_VALUE_CUES.search(val):
                logger.info(
                    "[extract][rerouter] R4-I: education.schooling → education.higherEducation (val=%r)",
                    val[:60],
                )
                it["fieldPath"] = "education.higherEducation"

        # ── 4d. LOOP-01 R4 Patch I — careerProgression inverse ───────────
        # If LLM wrote education.careerProgression but there is NO duration
        # cue in the answer (and it's probably the first job they named),
        # reroute to education.earlyCareer.
        elif fp == "education.careerProgression":
            if not _CAREER_DURATION_CUES.search(combined_text):
                logger.info(
                    "[extract][rerouter] R4-I: education.careerProgression → education.earlyCareer (no duration cue, val=%r)",
                    val[:60],
                )
                it["fieldPath"] = "education.earlyCareer"

        # ── 4e. LOOP-01 R4 Patch I — personal.notes → grandparents.ancestry ─
        # When value reads as an ethnic/ancestry phrase, reroute. Conservative:
        # requires the phrase to match _ANCESTRY_VALUE_CUES without additional
        # identifying content (preserves "personal.notes" when it's a full story).
        elif fp in ("personal.notes", "personal.heritage", "personal.ethnicity"):
            val_stripped = val.strip().rstrip(".,;:")
            if _ANCESTRY_VALUE_CUES.search(val_stripped) and len(val_stripped) < 80:
                logger.info(
                    "[extract][rerouter] R4-I: %s → grandparents.ancestry (val=%r)",
                    fp, val_stripped[:60],
                )
                it["fieldPath"] = "grandparents.ancestry"

        # ── 5. Story-priority rerouter: unfinishedDreams/lifeLessons → desiredStory ─
        # WO-QB-GENERATIONAL-01B: when the narrator lists stories they want told,
        # the LLM sometimes routes to additionalNotes.unfinishedDreams or
        # laterYears.lifeLessons. Reroute to laterYears.desiredStory.
        elif fp in ("additionalNotes.unfinishedDreams", "laterYears.lifeLessons"):
            if _STORY_PRIORITY_CUES.search(answer_lower):
                logger.info("[extract][rerouter] story-priority: %s → laterYears.desiredStory (val=%r)", fp, val[:60])
                it["fieldPath"] = "laterYears.desiredStory"

        if it["fieldPath"] != original_fp:
            # Verify the rerouted path is valid
            if it["fieldPath"] not in EXTRACTABLE_FIELDS:
                logger.warning("[extract][rerouter] rerouted path %r not in EXTRACTABLE_FIELDS — reverting to %r",
                              it["fieldPath"], original_fp)
                it["fieldPath"] = original_fp

        rerouted.append(it)

    # ── 6c. LOOP-01 R4 Patch C — merge pets.notes splits ────────────────
    # Only add pets.name/pets.species rows we don't already have (don't
    # double-up with what the LLM emitted directly).
    if pets_splits:
        existing_pets = {
            (it.get("fieldPath", ""), str(it.get("value", "")).strip().lower())
            for it in rerouted
            if it.get("fieldPath", "").startswith("pets.")
        }
        for sp in pets_splits:
            key = (sp["fieldPath"], str(sp["value"]).strip().lower())
            if key in existing_pets:
                continue
            rerouted.append(sp)
            existing_pets.add(key)

    # ── 6b. LOOP-01 R4 Patch I — parents.deathDate dup-emit ─────────────
    # parents.deathDate is narrow; truth sometimes expects the death fact in
    # parents.notableLifeEvents as prose. Dup-emit the year/date into
    # notableLifeEvents so either target matches.
    deathdate_dupes = []
    existing_nle = {
        (it.get("fieldPath", ""), it.get("value", ""))
        for it in rerouted
        if it.get("fieldPath") == "parents.notableLifeEvents"
    }
    for it in rerouted:
        if it.get("fieldPath") == "parents.deathDate":
            v = it.get("value", "")
            if not v:
                continue
            dup_val = f"died {v}"
            if ("parents.notableLifeEvents", dup_val) in existing_nle:
                continue
            deathdate_dupes.append({
                "fieldPath": "parents.notableLifeEvents",
                "value": dup_val,
                "confidence": max(0.1, min(1.0, float(it.get("confidence", 0.8)) - 0.1)),
            })
            existing_nle.add(("parents.notableLifeEvents", dup_val))
            logger.info(
                "[extract][rerouter] R4-I parents.deathDate dup → parents.notableLifeEvents=%r",
                dup_val,
            )
    rerouted.extend(deathdate_dupes)

    # ── 6a. LOOP-01 R4 Patch J — ancestor-military dup-emit ──────────────
    # When greatGrandparents.militaryBranch/Unit/Event lands (via direct LLM
    # emission or via alias) AND the value is in ancestor context, ALSO emit
    # the root military.* field so scorer/consumer code that indexes military
    # service at the root can match. Patch 4's ancestor-context check on
    # _apply_negation_guard preserves root military.* values when the narrator
    # denied their own service; the ancestor's facts survive the guard.
    # Dup-emit (don't remove) so the ancestor-scoped record remains intact.
    _ANCESTOR_MIL_DUP_MAP = {
        "greatGrandparents.militaryBranch": "military.branch",
        "greatGrandparents.militaryUnit":   "military.significantEvent",
        "greatGrandparents.militaryEvent":  "military.significantEvent",
    }
    ancestor_mil_dupes = []
    existing_root_mil = {
        (it.get("fieldPath", ""), it.get("value", ""))
        for it in rerouted
        if it.get("fieldPath", "").startswith("military.")
    }
    for it in rerouted:
        fp = it.get("fieldPath", "")
        if fp in _ANCESTOR_MIL_DUP_MAP:
            val = it.get("value", "")
            if not val:
                continue
            if not _is_ancestor_context_near(answer, val):
                continue
            new_fp = _ANCESTOR_MIL_DUP_MAP[fp]
            if (new_fp, val) in existing_root_mil:
                continue
            ancestor_mil_dupes.append({
                "fieldPath": new_fp,
                "value": val,
                "confidence": it.get("confidence", 0.8),
            })
            existing_root_mil.add((new_fp, val))
            logger.info(
                "[extract][rerouter] R4-J ancestor-mil-dup: %s → +%s (val=%r)",
                fp, new_fp, val[:60],
            )
    rerouted.extend(ancestor_mil_dupes)

    # ── 6. Touchstone duplicate: laterYears.significantEvent → ADD cultural.touchstoneMemory ─
    # WO-QB-GENERATIONAL-01B: when the answer mentions a known historical event
    # and the LLM routed to laterYears.significantEvent, ADD a duplicate item
    # routed to cultural.touchstoneMemory. Don't remove the original — both valid.
    # Requires THREE signals: event keyword + significantEvent route + witness-memory cue.
    # The witness cue prevents false positives on "my son was born during COVID".
    if _TOUCHSTONE_EVENT_CUES.search(answer_lower) and _WITNESS_MEMORY_CUES.search(answer_lower):
        touchstone_dupes = []
        existing_touchstones = {it.get("value", "") for it in rerouted if it.get("fieldPath") == "cultural.touchstoneMemory"}
        for it in rerouted:
            if it.get("fieldPath") == "laterYears.significantEvent":
                val = it.get("value", "")
                if val and val not in existing_touchstones:
                    touchstone_dupes.append({
                        "fieldPath": "cultural.touchstoneMemory",
                        "value": val,
                        "confidence": it.get("confidence", 0.8),
                    })
                    logger.info("[extract][rerouter] touchstone-dup: laterYears.significantEvent → +cultural.touchstoneMemory (val=%r)", val[:60])
        rerouted.extend(touchstone_dupes)

    return rerouted


def _apply_refusal_guard(items: List[dict], answer: str) -> List[dict]:
    """WO-EX-GUARD-REFUSAL-01: strip ALL fields when the narrator explicitly
    refuses to discuss a topic or asks that something not be written down.

    This catches topic refusals that the negation guard misses:
      - "nothing I want to go into"
      - "I'd rather not get into that"
      - "I don't think that's something I want written down"
      - "not for putting in a book"
      - "I'd rather leave it at that"

    Unlike the negation guard (which targets specific categories like
    "I never served"), a topic refusal strips everything from the answer
    because the narrator is refusing the entire line of questioning.
    """
    if not items or not answer:
        return items

    lower = answer.lower()

    _REFUSAL_PATTERNS = [
        # Direct privacy refusal — narrator says don't write / don't record
        re.compile(r"(?:not |don\'?t )(?:think )?(?:that\'?s )?something I (?:want|need) (?:written|recorded|put (?:down|in))", re.IGNORECASE),
        re.compile(r"not for (?:putting|writing) (?:in|down|into) (?:a book|the record|a record)", re.IGNORECASE),
        # Topic avoidance — narrator deflects the question
        re.compile(r"nothing I (?:want|need|care) to (?:go into|get into|talk about|discuss|share)", re.IGNORECASE),
        re.compile(r"(?:I\'?d |I would |I\'?d just )rather (?:not|leave it|skip|move on)", re.IGNORECASE),
        re.compile(r"(?:I\'?d |I would )prefer not to", re.IGNORECASE),
        re.compile(r"(?:let\'?s |can we )(?:skip|move on|not go there|leave) (?:that|this|it)", re.IGNORECASE),
        re.compile(r"I don\'?t (?:want|need|care) to (?:talk|go|get) (?:about |into )(?:that|this|it)", re.IGNORECASE),
        re.compile(r"rather not (?:get into|talk about|discuss|say|share|go there)", re.IGNORECASE),
    ]

    for pat in _REFUSAL_PATTERNS:
        if pat.search(lower):
            logger.info(
                "[extract][refusal-guard] topic refusal detected in answer, "
                "stripping all %d items. Pattern: %s",
                len(items), pat.pattern[:60]
            )
            return []

    return items


# ── LOOP-01 R3 Patch 4 — narrator-scoped negation-guard helpers ─────────────
# Ancestor attribution markers. If a denied-category value appears in the
# answer within ~120 chars after one of these markers, the negation guard
# must NOT strip it — the narrator's denial does not apply to ancestors.
# Classic failure case (Kent, R2 api.log):
#   "No, I never served. But my great-great-grandfather John Michael Shong
#    fought in the Civil War with Company G of the 28th Infantry..."
# Pre-R3 behavior: guard saw "never served", stripped all military.*, which
# ate Civil War, 1865-1866, Kansas and Missouri, and Company G.
# Post-R3 behavior: guard sees each stripped value in ancestor context and
# keeps it; separately, Patch 2 aliases route parents.parents.military.* and
# greatGrandparents.military.* onto the new greatGrandparents.military*
# fields so the ancestor facts land in the right place.
_ANCESTOR_MARKERS = re.compile(
    r"\b("
    r"great[- ]?great[- ]?grand(?:father|mother|pa|ma|parent|parents)|"
    r"great[- ]?grand(?:father|mother|pa|ma|parent|parents)|"
    r"grand(?:father|mother|pa|ma|parent|parents)|"
    r"(?:my|his|her|their) (?:father|mother|dad|mom|pa|ma)|"
    r"(?:his|her|their) grand(?:father|mother|pa|ma|parent|parents)|"
    r"ancestor|ancestors|forebear|forebears|forefather|forefathers"
    r")\b",
    re.IGNORECASE,
)


def _is_ancestor_context_near(answer: str, value, window_chars: int = 120) -> bool:
    """Return True if ``value`` appears in ``answer`` within ``window_chars``
    after a third-person ancestor marker. Checks ALL occurrences of the value
    (not just the first), so an early narrator mention does not mask a later
    ancestor attribution."""
    if not value or not answer:
        return False
    lower = answer.lower()
    val_lower = str(value).lower().strip()
    if not val_lower:
        return False
    # For long values, match the whole string; for very short ones (e.g.
    # "Army", "1865"), fall back to the first token to avoid missing the
    # position when the LLM paraphrases capitalization/punctuation.
    tokens = val_lower.split()
    search_term = val_lower if len(val_lower) >= 4 else (tokens[0] if tokens else val_lower)
    # Collect every occurrence of the search term in the answer.
    positions = []
    start = 0
    while True:
        pos = lower.find(search_term, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + 1
    if not positions:
        return False
    for pos in positions:
        window = lower[max(0, pos - window_chars):pos]
        if _ANCESTOR_MARKERS.search(window):
            return True
    return False


def _apply_negation_guard(items: List[dict], answer: str) -> List[dict]:
    """WO-EX-CLAIMS-02 validator 4: strip fields from categories the narrator
    explicitly denied.

    When the narrator says "I never served", "I didn't go to college",
    "I've been pretty healthy" etc., the LLM sometimes still emits fields
    for those categories. This validator detects denial patterns and removes
    any fields belonging to the denied category.

    LOOP-01 R3 Patch 4: the guard is now narrator-scoped. Before stripping
    a denied-category item, it checks whether the item's value appears in
    an ancestor-attributed context (e.g., "my great-grandfather fought in
    the Civil War..."). If yes, the item is preserved — the denial applied
    to the narrator, not the ancestor being discussed.
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
         {"health.majorCondition", "health.milestone", "health.lifestyleChange", "health.currentMedications", "health.cognitiveChange"}),
        # Education negation
        (re.compile(r'\b(?:never went to college|didn\'?t go to college|did not go to college|didn\'?t attend college|no college|never attended college)\b', re.IGNORECASE),
         {"education.higherEducation"}),
        # Community/organization denial — "not really", "wasn't a joiner", "not involved"
        (re.compile(r'\b(?:wasn\'?t (?:a |really )?(?:a )?joiner|not (?:really )?(?:a |much of a )?joiner|wasn\'?t (?:really )?involved|not (?:really )?involved|didn\'?t (?:really )?(?:join|belong|participate)|not really,? no)\b', re.IGNORECASE),
         {"community.organization", "community.role", "community.yearsActive"}),
    ]

    denied_fields = set()
    for pattern, fields in _DENIAL_PATTERNS:
        if pattern.search(lower):
            denied_fields.update(fields)
            logger.info("[extract][negation-guard] denial detected: stripping %s", fields)

    if not denied_fields:
        return items

    # LOOP-01 R4 Patch F: collect contrast-affirmation clauses once per answer.
    # When the narrator says "I'm not X, more of a Y" we want to keep the Y
    # even though its category matched a denial pattern.
    affirmatives = _collect_contrast_affirmations(answer)

    out = []
    for it in items:
        fp = str(it.get("fieldPath", ""))
        if fp in denied_fields:
            # LOOP-01 R3 Patch 4: preserve if value lives in ancestor context.
            if _is_ancestor_context_near(answer, it.get("value", "")):
                logger.info(
                    "[extract][negation-guard] keeping %s=%r (ancestor context detected — narrator denial does not apply)",
                    fp, it.get("value"),
                )
                out.append(it)
                continue
            # LOOP-01 R4 Patch F: preserve if value is inside an affirmative
            # clause following a contrast marker ("not X, but Y" → Y kept).
            if _value_in_affirmative_clause(it.get("value", ""), affirmatives):
                logger.info(
                    "[extract][negation-guard] keeping %s=%r (contrast-affirmation: value in affirmative clause)",
                    fp, it.get("value"),
                )
                out.append(it)
                continue
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
    # WO-EX-GUARD-REFUSAL-01: refusal guard fires first — if narrator refuses
    # the topic entirely, strip everything before wasting time on other checks.
    items = _apply_refusal_guard(items, answer)
    if not items and before > 0:
        logger.info("[extract][WO-CLAIMS-02] refusal guard stripped all %d items", before)
        return items
    items = _apply_claims_value_shape(items)
    # LOOP-01 R4 Patch A — cap scalar/narrative field values before the
    # other validators run. Catches LLM answer-dumps early so downstream
    # stages don't waste cycles on 500+ char scalar values.
    items = _apply_value_length_cap(items)
    items = _apply_claims_relation_allowlist(items)
    # LOOP-01 R4 Patch E — relation-scope safety; eliminates must_not_write
    # violations where family.children.* was written from an uncle/aunt
    # anecdote or parents.* was written from a sibling anecdote.
    items = _apply_relation_scope_guard(items, answer)
    # LOOP-01 R4 Patch H — normalise scalar surface forms (birthOrder, dates,
    # names) AFTER the shape/allowlist/scope checks have filtered the bad
    # items but BEFORE confidence-floor and negation-guard. Keeps values
    # consistent for downstream consumers and scorers without affecting
    # guard decisions (both check against the raw answer text).
    items = _apply_write_time_normalisation(items)
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

    # WO-EX-TURNSCOPE-01 (task #72): Follow-up turn-scope filter.
    # Enforce entity-role binding — on a follow-up turn whose target resolves
    # to one family-relations branch root (siblings/parents/grandparents/
    # greatGrandparents/family.children/family.spouse), drop items that leak
    # into adjacent branches of the same cluster. No-op on non-follow-up
    # turns and on follow-ups targeting fields outside the cluster.
    # Runs AFTER rerouter (so valid-but-wrong paths get a chance to be fixed
    # first) and BEFORE birth-context / negation guard so downstream guards
    # see a turn-scope-clean item list.
    if llm_items:
        llm_items = _apply_turn_scope_filter(llm_items, req.current_target_path)

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

    # WO-EX-TWOPASS-01: detect extraction method from raw_output marker
    _is_twopass = raw_output and raw_output.startswith("[TWOPASS]")
    _is_twopass_rules_only = _is_twopass and "P2B_LLM=0" in (raw_output[:100] if raw_output else "")

    # WO: Summary line — log outcome at endpoint level
    _accepted = len(llm_items) if llm_items else 0
    if _is_twopass:
        _method = "twopass_rules" if _is_twopass_rules_only else "twopass"
    else:
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

            # WO-EX-TWOPASS-01: tag extraction method based on pipeline used
            _item_method = "twopass" if _is_twopass else "llm"
            if _is_twopass_rules_only:
                _item_method = "twopass_rules"

            result_items.append(ExtractedItem(
                fieldPath=item["fieldPath"],
                value=item["value"],
                writeMode=write_mode,
                confidence=item["confidence"],
                source="backend_extract",
                extractionMethod=_item_method,
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

        _record_metric(_method, parsed=len(llm_items), accepted=len(final_items), rejected=0)
        return ExtractFieldsResponse(
            items=final_items,
            method=_method,
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
        # WO-EX-TURNSCOPE-01 (task #72): apply turn-scope filter on the rules
        # path too for symmetry. Rules extractions are narrower than LLM but
        # this is an idempotent no-op when the target is outside the family-
        # relations cluster, and cheap when inside.
        rules_items = _apply_turn_scope_filter(rules_items, req.current_target_path)
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
