"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — bio schema service.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The universal bio schema definition. Source of truth for which bio
fields exist, their narrative_value (Tier 3 eligibility), their type,
and the asking_anchors patterns that signal a chapter is in their
territory.

Per the universal pivot, this schema is intentionally NARRATOR-AGNOSTIC.
It covers fields that apply to essentially any older-adult life story
(identity, family structure, education sequence, work history, military
service if applicable, geographic moves, marriage/children, milestones).

LAW 3 INFRASTRUCTURE BOUNDARY: this module is pure — it imports from
stdlib only. No DB connection, no extract.py, no chat_ws. The seed
loader IS called from db.init_db() at cold-start (see db.py wire-up);
that's the only integration point.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  BIO_SCHEMA_SEED — list of FieldDefinition dataclasses (the seed)
  FieldDefinition — typed accessor; coerces lists to JSON strings

  iter_seed() → Iterator[FieldDefinition] — stable iteration order
  get_field_keys() → Set[str] — quick lookup
  get_field_by_key(key) → Optional[FieldDefinition]
  get_fields_by_category(category) → List[FieldDefinition]
  get_high_value_fields() → List[FieldDefinition] — Tier 3 candidates
  validate_seed() → List[str] — returns empty list if seed is well-formed
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Set, Tuple


# ─────────────────────────────────────────────────────────────────────
# Enum constraints (enforced at write-time by db.py CRUD)
# ─────────────────────────────────────────────────────────────────────

FIELD_CATEGORIES: Tuple[str, ...] = (
    "identity",
    "family",
    "education",
    "work",
    "military",
    "geography",
    "relationships",
    "milestones",
)

FIELD_TYPES: Tuple[str, ...] = (
    "date",
    "date_range",
    "place",
    "person",
    "text",
    "enum",
    "integer",
)

NARRATIVE_VALUES: Tuple[str, ...] = (
    "high",
    "medium",
    "low",
)

LIFE_STAGE_RANGES: Tuple[str, ...] = (
    "childhood",
    "adult",
    "all",
    "military_only",
)

FACT_STATUSES: Tuple[str, ...] = (
    "empty",
    "extracted_needs_verify",
    "document_sourced",
    "anchored_asked_pending",
    "anchored_asked",
    "operator_entered",
    "approved",
    "conflicted",
    "superseded",
)


# ─────────────────────────────────────────────────────────────────────
# Field definition dataclass
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldDefinition:
    """One row of the universal bio schema.

    Fields default to safe/permissive values so adding a new entry to
    the seed doesn't require remembering every parameter. Seed entries
    that omit asking_anchors are NOT eligible for Tier 3 even if their
    narrative_value is 'high' (the empty list is the deactivation
    signal).
    """
    field_key: str
    field_label: str
    field_category: str
    field_type: str
    narrative_value: str = "medium"
    life_stage_range: str = "all"
    asking_anchors: Tuple[str, ...] = field(default_factory=tuple)

    def asking_anchors_json(self) -> str:
        return json.dumps(list(self.asking_anchors))


# ─────────────────────────────────────────────────────────────────────
# The seed (universal — narrator-agnostic)
# ─────────────────────────────────────────────────────────────────────
#
# Curated to ~80 entries. Adding more is fine; removing requires care
# (existing bio_facts rows reference field_key via FK).
#
# Asking_anchors are LOWERCASE substring patterns. They run against
# the lowercased narrator-turn text in the anchored-asker eligibility
# check. Patterns are intentionally short (2-6 tokens) and unambiguous —
# false positives are worse than false negatives because they would
# steer Lori into asking-mode when the chapter isn't actually in
# territory.

BIO_SCHEMA_SEED: Tuple[FieldDefinition, ...] = (

    # ── identity ─────────────────────────────────────────────────────
    FieldDefinition("birth_date", "Birth date", "identity", "date",
                    narrative_value="high",
                    asking_anchors=("when i was born", "born in", "my birthday",
                                    "the year i was born")),
    FieldDefinition("birth_place", "Birth place", "identity", "place",
                    narrative_value="high",
                    asking_anchors=("where i was born", "born in", "grew up in",
                                    "my hometown")),
    FieldDefinition("full_legal_name", "Full legal name", "identity", "text",
                    narrative_value="low"),
    FieldDefinition("preferred_name", "Preferred name", "identity", "text",
                    narrative_value="low"),
    FieldDefinition("middle_name", "Middle name", "identity", "text",
                    narrative_value="low"),
    FieldDefinition("nickname", "Nickname", "identity", "text",
                    narrative_value="medium",
                    asking_anchors=("called me", "they called me", "nickname")),
    FieldDefinition("name_origin", "Name origin or story", "identity", "text",
                    narrative_value="medium",
                    asking_anchors=("named after", "named for", "my name came from")),
    FieldDefinition("religion_raised", "Religion raised in", "identity", "text",
                    narrative_value="high",
                    life_stage_range="childhood",
                    asking_anchors=("church", "synagogue", "mosque", "temple",
                                    "sunday school", "catechism", "raised catholic",
                                    "raised baptist", "raised jewish", "religious")),
    # WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 Phase 2A — current faith
    # surfaces faith differences between childhood + adult life.
    # Operator-entered at intake; rarely re-asked of the narrator since
    # it's a sensitive identity field they may have already discussed.
    FieldDefinition("current_faith", "Current faith / practice", "identity", "text",
                    narrative_value="medium",
                    life_stage_range="adult",
                    asking_anchors=("still go to", "stopped going to",
                                    "left the church", "found a new church",
                                    "we belong to", "now i believe")),
    FieldDefinition("ethnicity_heritage", "Ethnicity / heritage", "identity", "text",
                    narrative_value="medium",
                    asking_anchors=("heritage", "ancestors came from", "from the old country")),
    FieldDefinition("languages_spoken_home", "Languages spoken at home", "identity", "text",
                    narrative_value="high",
                    life_stage_range="childhood",
                    asking_anchors=("spoke", "german at home", "italian at home",
                                    "yiddish", "spanish at home", "polish at home",
                                    "language at home")),

    # ── family ───────────────────────────────────────────────────────
    FieldDefinition("father_name", "Father's name", "family", "person",
                    narrative_value="high",
                    asking_anchors=("my father", "my dad", "papa", "my pop")),
    FieldDefinition("father_birth_year", "Father's birth year", "family", "integer",
                    narrative_value="low"),
    FieldDefinition("father_occupation", "Father's occupation", "family", "text",
                    narrative_value="high",
                    asking_anchors=("dad worked", "father worked", "my dad was",
                                    "my father was a")),
    FieldDefinition("father_birth_place", "Father's birth place", "family", "place",
                    narrative_value="medium",
                    asking_anchors=("dad was from", "father was from",
                                    "dad came from")),
    FieldDefinition("mother_name", "Mother's name", "family", "person",
                    narrative_value="high",
                    asking_anchors=("my mother", "my mom", "mama", "my ma")),
    FieldDefinition("mother_maiden_name", "Mother's maiden name", "family", "text",
                    narrative_value="low"),
    FieldDefinition("mother_birth_year", "Mother's birth year", "family", "integer",
                    narrative_value="low"),
    FieldDefinition("mother_occupation", "Mother's occupation", "family", "text",
                    narrative_value="high",
                    asking_anchors=("mom worked", "mother worked", "my mom was",
                                    "stay at home", "homemaker")),
    FieldDefinition("mother_birth_place", "Mother's birth place", "family", "place",
                    narrative_value="medium",
                    asking_anchors=("mom was from", "mother was from",
                                    "mom came from")),
    FieldDefinition("parents_marriage_year", "Parents' marriage year", "family", "integer",
                    narrative_value="low"),
    FieldDefinition("sibling_count", "Number of siblings", "family", "integer",
                    narrative_value="high",
                    asking_anchors=("my brothers", "my sisters", "my siblings",
                                    "brothers and sisters")),
    FieldDefinition("birth_order", "Birth order among siblings", "family", "text",
                    narrative_value="high",
                    asking_anchors=("oldest", "youngest", "middle child",
                                    "second oldest")),
    FieldDefinition("siblings_named", "Siblings named", "family", "text",
                    narrative_value="medium",
                    asking_anchors=("my brother", "my sister")),
    FieldDefinition("childhood_home_address", "Childhood home address", "family", "place",
                    narrative_value="medium",
                    life_stage_range="childhood",
                    asking_anchors=("the house we lived in", "our house on",
                                    "we lived on", "the old house")),
    FieldDefinition("grandparents_named", "Grandparents named", "family", "text",
                    narrative_value="medium",
                    asking_anchors=("my grandmother", "my grandfather",
                                    "grandma", "grandpa", "nana", "papa")),
    FieldDefinition("grandparents_origin", "Grandparents' country of origin", "family", "text",
                    narrative_value="high",
                    asking_anchors=("came from the old country", "came over from",
                                    "from ireland", "from italy", "from germany",
                                    "ellis island", "the old country")),

    # ── education ────────────────────────────────────────────────────
    FieldDefinition("elementary_school", "Elementary / grade school", "education", "text",
                    narrative_value="high",
                    life_stage_range="childhood",
                    asking_anchors=("grade school", "grammar school",
                                    "elementary school", "first grade",
                                    "kindergarten")),
    FieldDefinition("elementary_school_place", "Elementary school location", "education", "place",
                    narrative_value="medium",
                    life_stage_range="childhood",
                    asking_anchors=("walked to school", "the schoolhouse",
                                    "my school was")),
    FieldDefinition("high_school", "High school attended", "education", "text",
                    narrative_value="high",
                    asking_anchors=("high school", "freshman year",
                                    "senior year", "graduated from")),
    FieldDefinition("high_school_graduation_year", "High school graduation year",
                    "education", "integer",
                    narrative_value="high",
                    asking_anchors=("graduated in", "class of",
                                    "when i graduated")),
    FieldDefinition("college_attended", "College / university attended",
                    "education", "text",
                    narrative_value="high",
                    asking_anchors=("college", "university", "went to school at",
                                    "studied at")),
    FieldDefinition("college_degree", "College degree earned",
                    "education", "text",
                    narrative_value="high",
                    asking_anchors=("my degree", "majored in", "bachelor",
                                    "associate degree", "studied")),
    FieldDefinition("college_graduation_year", "College graduation year",
                    "education", "integer",
                    narrative_value="medium",
                    asking_anchors=("graduated college in", "got my degree in")),
    FieldDefinition("graduate_school", "Graduate school", "education", "text",
                    narrative_value="medium",
                    asking_anchors=("graduate school", "master's", "phd",
                                    "doctorate", "law school", "medical school")),
    FieldDefinition("vocational_training", "Vocational / trade training",
                    "education", "text",
                    narrative_value="high",
                    asking_anchors=("trade school", "apprenticeship", "journeyman",
                                    "trained as", "learned the trade")),
    # WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 Phase 2A — coarse education
    # picker captured at intake. Single string per spec ("Some primary"
    # / "High school" / "Bachelor's" / etc.). Specific institutions
    # come out in the chapter, not in the form — see WO Out of scope.
    FieldDefinition("highest_education_level", "Highest education level reached",
                    "education", "enum",
                    narrative_value="low"),

    # ── work ─────────────────────────────────────────────────────────
    FieldDefinition("first_job", "First job", "work", "text",
                    narrative_value="high",
                    asking_anchors=("first job", "my first paying", "my first work",
                                    "summer job", "newspaper route", "paper route")),
    FieldDefinition("first_job_age", "Age at first job", "work", "integer",
                    narrative_value="medium"),
    FieldDefinition("primary_career", "Primary career", "work", "text",
                    narrative_value="high",
                    asking_anchors=("my career", "my profession", "i worked as",
                                    "i was a", "did that for years")),
    FieldDefinition("primary_employer", "Primary employer", "work", "text",
                    narrative_value="high",
                    asking_anchors=("worked at", "worked for", "the company",
                                    "the plant", "the mill", "the factory",
                                    "the office")),
    FieldDefinition("career_start_year", "Career start year", "work", "integer",
                    narrative_value="medium"),
    FieldDefinition("retirement_year", "Retirement year", "work", "integer",
                    narrative_value="high",
                    asking_anchors=("when i retired", "after i retired",
                                    "i retired in")),
    FieldDefinition("career_change_story", "Career change moment", "work", "text",
                    narrative_value="high",
                    asking_anchors=("changed jobs", "switched careers", "moved to",
                                    "left the job", "got a new job")),
    FieldDefinition("union_membership", "Union membership", "work", "text",
                    narrative_value="medium",
                    asking_anchors=("the union", "union steward", "joined the union",
                                    "the local")),
    FieldDefinition("notable_workplace", "Notable workplace memory", "work", "text",
                    narrative_value="medium",
                    asking_anchors=("the boss", "the foreman", "the supervisor",
                                    "my coworkers")),

    # ── military ─────────────────────────────────────────────────────
    FieldDefinition("military_served", "Served in military", "military", "enum",
                    narrative_value="high",
                    life_stage_range="military_only",
                    asking_anchors=("the army", "the navy", "the marines",
                                    "the air force", "the coast guard",
                                    "i served", "in the service",
                                    "drafted", "enlisted", "boot camp",
                                    "basic training")),
    FieldDefinition("military_branch", "Military branch", "military", "enum",
                    narrative_value="high",
                    life_stage_range="military_only",
                    asking_anchors=("army", "navy", "marines", "air force",
                                    "coast guard", "boot camp", "basic training",
                                    "fort", "base", "deployed", "served")),
    FieldDefinition("military_service_period", "Service period", "military", "date_range",
                    narrative_value="high",
                    life_stage_range="military_only",
                    asking_anchors=("served from", "in the service for",
                                    "discharged in", "enlisted in")),
    FieldDefinition("military_rank", "Final rank", "military", "text",
                    narrative_value="medium",
                    life_stage_range="military_only",
                    asking_anchors=("sergeant", "lieutenant", "captain", "corporal",
                                    "private", "made rank", "promoted to")),
    FieldDefinition("military_locations", "Service locations", "military", "text",
                    narrative_value="high",
                    life_stage_range="military_only",
                    asking_anchors=("stationed at", "fort", "base", "deployed",
                                    "overseas", "vietnam", "korea", "germany",
                                    "japan", "iraq", "afghanistan")),
    FieldDefinition("military_combat", "Combat experience", "military", "text",
                    narrative_value="medium",
                    life_stage_range="military_only",
                    asking_anchors=("combat", "saw action", "fighting", "engaged")),
    FieldDefinition("military_discharge_type", "Discharge type", "military", "text",
                    narrative_value="low",
                    life_stage_range="military_only"),
    FieldDefinition("military_decorations", "Decorations / awards", "military", "text",
                    narrative_value="medium",
                    life_stage_range="military_only",
                    asking_anchors=("medal", "purple heart", "bronze star",
                                    "silver star", "decorated")),
    # WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 Phase 2A — wars / conflicts
    # served through. Operator-entered at intake from the VHP-pattern
    # military block; surfaces in memoir indexing but not anchored-
    # asked (narrative_value=low) since the existing combat /
    # military_locations / military_service_period fields already
    # carry asking anchors.
    FieldDefinition("military_wars_conflicts", "Wars / conflicts", "military", "text",
                    narrative_value="low",
                    life_stage_range="military_only"),
    FieldDefinition("military_experience_notes", "Service experience notes",
                    "military", "text",
                    narrative_value="low",
                    life_stage_range="military_only"),

    # ── geography ────────────────────────────────────────────────────
    FieldDefinition("childhood_geography", "Where childhood was spent",
                    "geography", "place",
                    narrative_value="high",
                    life_stage_range="childhood",
                    asking_anchors=("grew up in", "spent my childhood",
                                    "raised in", "moved around as a kid")),
    FieldDefinition("childhood_homes", "Childhood homes (list)",
                    "geography", "text",
                    narrative_value="medium",
                    life_stage_range="childhood",
                    asking_anchors=("the houses we lived", "we moved a lot",
                                    "the place on", "the house on")),
    FieldDefinition("adult_homes", "Adult residences (list)",
                    "geography", "text",
                    narrative_value="high",
                    life_stage_range="adult",
                    asking_anchors=("we moved to", "bought the house",
                                    "our first place", "we settled in")),
    FieldDefinition("current_residence", "Current residence", "geography", "place",
                    narrative_value="medium",
                    asking_anchors=("live here", "moved here", "ended up in")),
    FieldDefinition("notable_moves", "Notable moves", "geography", "text",
                    narrative_value="high",
                    asking_anchors=("when we moved", "the big move", "moving day",
                                    "left town", "left the farm")),
    FieldDefinition("travel_memories", "Notable travels", "geography", "text",
                    narrative_value="medium",
                    asking_anchors=("traveled to", "trip to", "vacation in",
                                    "took a trip", "saw the country")),

    # ── relationships ────────────────────────────────────────────────
    FieldDefinition("spouse_name", "Spouse name", "relationships", "person",
                    narrative_value="high",
                    asking_anchors=("my husband", "my wife", "we met", "married")),
    FieldDefinition("spouse_birth_year", "Spouse birth year",
                    "relationships", "integer",
                    narrative_value="low"),
    FieldDefinition("marriage_year", "Marriage year", "relationships", "integer",
                    narrative_value="high",
                    asking_anchors=("the year we married", "got married in",
                                    "our wedding was")),
    FieldDefinition("marriage_place", "Marriage place", "relationships", "place",
                    narrative_value="medium",
                    asking_anchors=("got married at", "the wedding was at",
                                    "married in")),
    FieldDefinition("how_met_spouse", "How met spouse", "relationships", "text",
                    narrative_value="high",
                    asking_anchors=("how we met", "we met at", "we met when",
                                    "the day i met")),
    FieldDefinition("previous_marriages", "Previous marriages",
                    "relationships", "text",
                    narrative_value="medium"),
    FieldDefinition("children_count", "Number of children",
                    "relationships", "integer",
                    narrative_value="high",
                    asking_anchors=("our children", "the kids", "my children",
                                    "i have a son", "i have a daughter",
                                    "we had a son", "we had a daughter")),
    FieldDefinition("children_named", "Children named", "relationships", "text",
                    narrative_value="high",
                    asking_anchors=("our oldest", "our youngest", "the baby",
                                    "named our son", "named our daughter")),
    FieldDefinition("children_birth_years", "Children birth years",
                    "relationships", "text",
                    narrative_value="low"),
    FieldDefinition("grandchildren_count", "Number of grandchildren",
                    "relationships", "integer",
                    narrative_value="medium",
                    asking_anchors=("the grandkids", "my grandchildren",
                                    "the grandbabies")),
    FieldDefinition("close_friends_named", "Close friends named",
                    "relationships", "text",
                    narrative_value="medium",
                    asking_anchors=("my best friend", "we grew up together",
                                    "lifelong friend")),

    # ── milestones ───────────────────────────────────────────────────
    FieldDefinition("first_car", "First car", "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("first car", "my first vehicle",
                                    "the old chevy", "bought my first car")),
    FieldDefinition("first_home_purchase", "First home purchase",
                    "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("first house", "bought the house",
                                    "our first home")),
    FieldDefinition("major_illness", "Major illness or surgery",
                    "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("when i got sick", "the surgery",
                                    "the hospital", "the diagnosis")),
    FieldDefinition("major_loss", "Major loss", "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("when she died", "when he died",
                                    "the year we lost", "buried")),
    FieldDefinition("formative_event", "Formative life event",
                    "milestones", "text",
                    narrative_value="high",
                    asking_anchors=("changed my life", "the day that changed",
                                    "i'll never forget", "that's when i")),
    FieldDefinition("religious_practice_adult", "Religious practice as adult",
                    "milestones", "text",
                    narrative_value="medium",
                    life_stage_range="adult",
                    asking_anchors=("our church", "the temple", "the parish",
                                    "we belonged to", "active in the church")),
    FieldDefinition("political_engagement", "Political engagement",
                    "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("voted for", "campaigned for", "the union",
                                    "the movement", "we marched")),
    FieldDefinition("community_involvement", "Community involvement",
                    "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("volunteer", "the lodge", "the club",
                                    "the elks", "the rotary", "the kiwanis",
                                    "the league")),
    FieldDefinition("hobby_primary", "Primary lifelong hobby",
                    "milestones", "text",
                    narrative_value="medium",
                    asking_anchors=("my hobby", "i loved", "always enjoyed",
                                    "spent my weekends", "started collecting")),
    FieldDefinition("hardship_overcome", "Major hardship overcome",
                    "milestones", "text",
                    narrative_value="high",
                    asking_anchors=("the depression", "the war", "the recession",
                                    "we got through", "hard times", "lean years",
                                    "tough times")),
)


# ─────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────


def iter_seed() -> Iterator[FieldDefinition]:
    """Stable-order iteration over the universal seed."""
    for fd in BIO_SCHEMA_SEED:
        yield fd


def get_field_keys() -> Set[str]:
    """Set of all canonical field_keys defined by the seed."""
    return {fd.field_key for fd in BIO_SCHEMA_SEED}


def get_field_by_key(key: str) -> Optional[FieldDefinition]:
    """Lookup the FieldDefinition for a field_key, or None."""
    for fd in BIO_SCHEMA_SEED:
        if fd.field_key == key:
            return fd
    return None


def get_fields_by_category(category: str) -> List[FieldDefinition]:
    """All fields belonging to the requested category."""
    if category not in FIELD_CATEGORIES:
        return []
    return [fd for fd in BIO_SCHEMA_SEED if fd.field_category == category]


def get_high_value_fields() -> List[FieldDefinition]:
    """Tier 3 candidates — narrative_value=high AND non-empty anchors.

    The anchor check is the deactivation signal: a high-value field
    with an empty asking_anchors list is NOT eligible for anchored
    asking even though its narrative_value would otherwise qualify.
    """
    return [
        fd for fd in BIO_SCHEMA_SEED
        if fd.narrative_value == "high" and len(fd.asking_anchors) > 0
    ]


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────


def validate_seed() -> List[str]:
    """Return a list of validation errors. Empty list = seed is OK.

    Run at cold-start before db.bio_schema_seed_load_to_db() fires so
    we never write malformed entries. Tests call this directly.
    """
    errors: List[str] = []
    seen_keys: Set[str] = set()
    for fd in BIO_SCHEMA_SEED:
        # Duplicate keys (FK collision in bio_facts)
        if fd.field_key in seen_keys:
            errors.append(f"duplicate field_key: {fd.field_key}")
        seen_keys.add(fd.field_key)
        # Enum constraints
        if fd.field_category not in FIELD_CATEGORIES:
            errors.append(
                f"{fd.field_key}: invalid field_category {fd.field_category!r}",
            )
        if fd.field_type not in FIELD_TYPES:
            errors.append(
                f"{fd.field_key}: invalid field_type {fd.field_type!r}",
            )
        if fd.narrative_value not in NARRATIVE_VALUES:
            errors.append(
                f"{fd.field_key}: invalid narrative_value "
                f"{fd.narrative_value!r}",
            )
        if fd.life_stage_range not in LIFE_STAGE_RANGES:
            errors.append(
                f"{fd.field_key}: invalid life_stage_range "
                f"{fd.life_stage_range!r}",
            )
        # Shape constraints
        if not fd.field_key or not fd.field_label:
            errors.append(
                f"{fd.field_key!r}: empty field_key or field_label",
            )
        # Asking-anchor shape: must be lowercase strings
        for anchor in fd.asking_anchors:
            if not isinstance(anchor, str):
                errors.append(
                    f"{fd.field_key}: non-string anchor: {anchor!r}",
                )
                continue
            if anchor != anchor.lower():
                errors.append(
                    f"{fd.field_key}: anchor must be lowercase: {anchor!r}",
                )
            if not anchor.strip():
                errors.append(
                    f"{fd.field_key}: empty anchor",
                )
    return errors


__all__ = [
    "FIELD_CATEGORIES",
    "FIELD_TYPES",
    "NARRATIVE_VALUES",
    "LIFE_STAGE_RANGES",
    "FACT_STATUSES",
    "FieldDefinition",
    "BIO_SCHEMA_SEED",
    "iter_seed",
    "get_field_keys",
    "get_field_by_key",
    "get_fields_by_category",
    "get_high_value_fields",
    "validate_seed",
]
