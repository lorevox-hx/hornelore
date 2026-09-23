"""Concept catalog — the SEMANTIC SOURCE. WO-HORNELORE-INTEGRATED-LIFE-RECORD-01, Batch A1.

This module holds only the human judgements: which section's facts are about
whom, which field name means which concept, which asking key and Profile Seed
path read which concept, and what was retired by which decision. Everything
MEASURABLE (which paths exist, their write modes, which asking keys are Tier-3
eligible, which sections the extractor sees them in) is read from the shipped
code by `scripts/catalog/compile_concept_catalog.py`, which compiles this
module plus those measurements into `concept_catalog_v1.json`.

WHY SPLIT IT THIS WAY. A catalog typed out as one big JSON file is a fifth
vocabulary, and hand-copied measurements go stale. Here the judgements are
small, reviewable tables; the compiled file is regenerated and a test fails if
the committed copy differs from a fresh compile.

THE CORE IDEA, in two tables. A legacy path is (section, field). The SECTION
says whose fact it is (`SUBJECT_BY_SECTION`); the FIELD says what the fact is
(`CONCEPT_BY_FIELD`). `children.birthDate` and `personal.dateOfBirth` are the
same concept, `person.birth.date`, about two different people.

LAW 3: pure data. No imports beyond the standard library, no IO.

Decision ids refer to docs/wo/WO-HORNELORE-INTEGRATED-LIFE-RECORD-01_DECISIONS.md.
"""

CATALOG_VERSION = 1

# ── whose fact is it ─────────────────────────────────────────────────────
# Subject kinds are RELATIONSHIP ROLES to the narrator, not separate schemas
# (D2): every one of them is an ordinary person record in the life record.
SUBJECT_BY_SECTION = {
    "personal": "narrator",
    "parents": "parent",
    "siblings": "sibling",
    "children": "child",
    "family.children": "child",
    "spouse": "spouse",
    "family.spouse": "spouse",
    "family.priorPartners": "prior_partner",     # D2: an ordinary person
    "family.grandchildren": "grandchild",        # D2: an ordinary person
    "grandparents": "grandparent",
    "greatGrandparents": "great_grandparent",
    "pets": "animal",
    "travel": "trip",                            # the trip domain, not the life record (§2.3)
    "marriage": "union",                         # an occurrence with the narrator and a spouse
    "family": "biography",
    # the narrator's own life
    "earlyMemories": "narrator", "education": "narrator", "faith": "narrator",
    "hobbies": "narrator", "laterYears": "narrator", "additionalNotes": "narrator",
    "cultural": "narrator", "familyTraditions": "narrator", "military": "narrator",
    "residence": "narrator", "community": "narrator", "health": "narrator",
    "technology": "narrator",
}

# ── what is the fact ─────────────────────────────────────────────────────
# Keyed by field name, overridable per (section, field) below. A person field
# means the same thing whoever the person is.
CONCEPT_BY_FIELD = {
    "fullName": "person.name.full",
    "firstName": "person.name.given",
    "middleName": "person.name.given",           # additional given name (D1c: names are never parsed)
    "lastName": "person.name.family",
    "maidenName": "person.name.birth_family",
    "preferredName": "person.name.preferred",
    "dateOfBirth": "person.birth.date",
    "birthDate": "person.birth.date",
    "placeOfBirth": "person.birth.place",
    "birthPlace": "person.birth.place",
    "timeOfBirth": "person.birth.time",
    "birthOrder": "person.birth.order",
    "deathDate": "person.death.date",
    "placeOfDeath": "person.death.place",
    "ageAtDeath": "person.death.reported_age",   # D1c: STATED age at death, never a stored derived age
    "deceased": "person.life_status",            # three states: deceased / explicitly_living / unknown
    "occupation": "person.occupation",
    "education": "person.education",
    "ethnicBackground": "person.heritage",       # D1e: self-described free text
    "ancestry": "person.heritage",
    "culturalBackground": "person.heritage",
    "relation": "relationship.kind",
    "relationshipType": "relationship.kind",
    "side": "relationship.qualifier.lineage_side",  # D1e: a property of the lineage, not the person
    "childCount": "person.reported_count.children",  # D1e: STATED count; zero is an answer
    "zodiacSign": "person.zodiac_sign",          # D1f: derived from the birth date, never stored
    "nameStory": "story.name_origin",            # D1e: a story about the name
    "notableLifeEvents": "story.about_person",
    "memorableStory": "story.about_person",      # D1a B05: singular and plural are one concept
    "memorableStories": "story.about_person",
    "sharedExperiences": "story.about_person",
    "uniqueCharacteristics": "story.about_person",
    "narrative": "story.about_person",
    "period": "relationship.period",             # D1e: prior partners
    # animals (D1f: animals are their own entity)
    "name": "animal.name",
    "species": "animal.species",
    "breed": "animal.breed",
    "adoptionDate": "animal.joined_household",
}

CONCEPT_BY_PATH = {
    # animals: the generic birthDate means the animal's
    "pets.birthDate": "animal.birth.date",
    # the narrator's own life, by section
    "earlyMemories.firstMemory": "story.memory",
    "earlyMemories.favoriteToy": "story.memory",
    "earlyMemories.significantEvent": "event.significant",
    "education.schooling": "event.education.schooling",
    "education.higherEducation": "event.education.higher",
    "education.gradeLevel": "event.education.level",
    "education.training": "event.education.training",           # D1e G59
    "education.careerProgression": "event.work.career",
    "education.earlyCareer": "event.work.early",
    "education.communityInvolvement": "event.activity.organization",  # D1f Q08
    "education.mentorship": "relationship.kind",                # D1f Q08: a mentor is a relationship
    "education.readingAbility": "story.reading",                # D1e G55: volunteered biography, never an assessment
    "faith.denomination": "person.faith.current",
    "faith.raisedIn": "person.faith.raised",
    "faith.communityRole": "event.activity.role",
    "faith.significantMoments": "story.faith",
    "hobbies.hobbies": "person.interest",
    "hobbies.personalChallenges": "story.reflection",
    "hobbies.travel": "trip.view",                              # D1f Q04: a view into the trip domain
    "hobbies.worldEvents": "story.memory",
    "laterYears.retirement": "event.retirement",
    "laterYears.lifeLessons": "story.lesson",
    "laterYears.adviceForFutureGenerations": "story.message",   # D1f Q09
    "laterYears.desiredStory": "story.desired",                 # D1c G34
    "laterYears.dailyRoutine": "story.life_today.routine",      # D1e G40: description, not clinical inference
    "laterYears.significantEvent": "event.significant",         # D1c G01
    "additionalNotes.messagesForFutureGenerations": "story.message",
    "additionalNotes.unfinishedDreams": "story.reflection",
    "cultural.touchstoneMemory": "story.memory",                # D1c G34
    "familyTraditions.description": "story.tradition",
    "familyTraditions.occasion": "story.tradition",
    "marriage.marriageDate": "event.union.date",
    "marriage.marriagePlace": "event.union.place",
    "marriage.proposalStory": "story.union",                    # D1f Q03
    "marriage.weddingDetails": "story.union",
    "marriage.spouseReference": "event.union.participant",
    # military service is an OCCURRENCE (D7; WO-LIFE-RECORD-01 §3.5). See
    # RECONCILIATIONS: D1e named great-grandparent service `person.service.*`
    # before D7 decided occurrences are canonical.
    "military.branch": "event.service.branch",
    "military.unit": "event.service.unit",
    "military.rank": "event.service.rank",
    "military.role": "event.service.role",
    "military.location": "event.service.place",
    "military.serviceStart": "event.service.period",
    "military.serviceEnd": "event.service.period",
    "military.notableEvents": "story.service",
    "greatGrandparents.militaryBranch": "event.service.branch",  # D1e G49
    "greatGrandparents.militaryUnit": "event.service.unit",      # D1e G51
    # NOT story.service: the field is "military event / deployment / dates" and
    # extract.py:5054-5061 routes yearsOfService, deploymentLocation and rank
    # into it. It describes the occurrence itself (D1e as confirmed, D7).
    "greatGrandparents.militaryEvent": "event.service.occurrence",  # D1e G50
    "residence.place": "event.residence.place",
    "residence.periodStart": "event.residence.period",
    "residence.periodEnd": "event.residence.period",
    "residence.homeType": "event.residence.type",
    "residence.memories": "story.home",
    "siblings.memories": "story.about_person",
    "community.organization": "event.activity.organization",     # D1e G53
    "community.role": "event.activity.role",                     # D1e G56
    "community.yearsActive": "event.activity.period",            # D1e G60
    "community.significantEvent": "event.significant",           # D1c G01
    "health.cognitiveChange": "story.health.reflection",         # D3(a)
    "health.lifestyleChange": "story.health.reflection",         # D3(a)
    "health.lifestyleChanges": "story.health.reflection",        # D3(a), form spelling
    "health.milestone": "story.health.reflection",               # D3(a)
    "health.healthMilestones": "story.health.reflection",        # D3(a)
    "health.wellnessTips": "story.health.reflection",            # D3(a)
    "technology.firstTechExperience": "story.memory",
    "technology.favoriteGadgets": "person.interest",
    "technology.culturalPractices": "story.tradition",
    "travel.destination": "trip.destination",
    "travel.year": "trip.date",
    "travel.purpose": "trip.purpose",
    "travel.companions": "trip.companions",
    "travel.whatHappened": "trip.story",
    # D11: operator-authored narrative/context in the form, routed to the lane
    # it belongs to — and retired from structured extraction (EXTRACTION_RETIRED).
    "parents.notes": "story.about_person",
    "faith.notes": "story.faith",
    "military.notes": "story.service",
    "pets.notes": "story.about_animal",
    "travel.notes": "trip.story",
}

# ── retired from STRUCTURED EXTRACTION only (D1f: separate properties) ────
# The path stays bound and questionnaire-editable; the extractor stops being
# offered it (Batch A3 removes it from EXTRACTABLE_FIELDS). Existing values
# migrate. Distinct from RETIRED below, which retires the path outright.
EXTRACTION_RETIRED = {
    "parents.notes": "D11", "faith.notes": "D11", "military.notes": "D11",
    "pets.notes": "D11", "travel.notes": "D11",
}

# ── retired — no concept, and the extractor stops looking (Batch A3) ──────
# Each carries the decision that retired it. A retired path is a BINDING with
# disposition `retired`, never a silent omission.
RETIRED = {
    # D1d: notes buckets
    "family.grandchildren.notes": "D1d", "family.children.notes": "D1d",
    "family.spouse.notes": "D1d", "community.notes": "D1d", "education.notes": "D1d",
    "health.notes": "D1d", "hobbies.notes": "D1d",
    # D1f Q12: the one form-only notes bucket
    "siblings.notes": "D1f",
    # NOT here: parents/faith/military/pets/travel `.notes`. D11 retires them
    # from extraction only; they stay in the form — see EXTRACTION_RETIRED.
    # D1e: logistics, not a life; a derived age; a notes bucket
    "community.meetingDay": "D1e", "community.meetingLocation": "D1e",
    "community.memberCount": "D1e", "community.successor": "D1e",
    "family.spouse.ageAtMarriage": "D1e", "family.marriageNotes": "D1e",
    # D3(a): no structured clinical extraction
    "health.majorCondition": "D3", "health.currentMedications": "D3",
}

# ── asking keys (bio_schema) → concept + subject ─────────────────────────
# The asking layer names a concept WITHOUT a subject; this says which. Tier-3
# eligibility, narrative value and anchors are MEASURED, not restated here.
ASKING_KEY_BINDINGS = {
    "adult_homes": ("event.residence.place", "narrator"),
    "birth_date": ("person.birth.date", "narrator"),
    "birth_order": ("person.birth.order", "narrator"),
    "birth_place": ("person.birth.place", "narrator"),
    "career_change_story": ("event.work.career", "narrator"),
    "career_start_year": ("event.work.early", "narrator"),
    "childhood_geography": ("event.residence.place", "narrator"),
    "childhood_home_address": ("event.residence.place", "narrator"),
    "childhood_homes": ("event.residence.place", "narrator"),
    "children_birth_years": ("person.birth.date", "child"),
    "children_count": ("person.reported_count.children", "narrator"),
    "children_named": ("person.name.given", "child"),
    "close_friends_named": ("person.name.given", "friend"),
    "college_attended": ("event.education.higher", "narrator"),
    "college_degree": ("event.education.higher", "narrator"),
    "college_graduation_year": ("event.education.higher", "narrator"),
    "community_involvement": ("event.activity.organization", "narrator"),
    "current_faith": ("person.faith.current", "narrator"),
    "current_residence": ("event.residence.place", "narrator"),
    "elementary_school": ("event.education.schooling", "narrator"),
    "elementary_school_place": ("event.education.schooling", "narrator"),
    "ethnicity_heritage": ("person.heritage", "narrator"),
    "father_birth_place": ("person.birth.place", "parent:father"),
    "father_birth_year": ("person.birth.date", "parent:father"),
    "father_name": ("person.name.given", "parent:father"),
    "father_occupation": ("person.occupation", "parent:father"),
    "first_car": ("story.memory", "narrator"),
    "first_home_purchase": ("event.residence.place", "narrator"),
    "first_job": ("event.work.early", "narrator"),
    "first_job_age": ("event.work.early", "narrator"),
    "formative_event": ("event.significant", "narrator"),
    "full_legal_name": ("person.name.full", "narrator"),
    "graduate_school": ("event.education.higher", "narrator"),
    "grandchildren_count": ("person.reported_count.grandchildren", "narrator"),
    "grandparents_named": ("person.name.given", "grandparent"),
    "grandparents_origin": ("person.heritage", "grandparent"),
    "hardship_overcome": ("story.reflection", "narrator"),
    "high_school": ("event.education.schooling", "narrator"),
    "high_school_graduation_year": ("event.education.schooling", "narrator"),
    "highest_education_level": ("event.education.level", "narrator"),
    "hobby_primary": ("person.interest", "narrator"),
    "how_met_spouse": ("story.union", "union"),
    "languages_spoken_home": ("person.languages", "narrator"),
    "major_illness": ("story.health.reflection", "narrator"),   # D3(a): a reflection, never a clinical record
    "major_loss": ("event.loss", "narrator"),
    "marital_status": ("relationship.kind", "spouse"),
    "marriage_place": ("event.union.place", "union"),
    "marriage_year": ("event.union.date", "union"),
    "middle_name": ("person.name.given", "narrator"),
    "military_branch": ("event.service.branch", "narrator"),
    "military_combat": ("story.service", "narrator"),
    "military_decorations": ("event.service.decorations", "narrator"),
    "military_discharge_type": ("event.service.discharge", "narrator"),
    "military_experience_notes": ("story.service", "narrator"),
    "military_locations": ("event.service.place", "narrator"),
    "military_rank": ("event.service.rank", "narrator"),
    "military_served": ("person.military_service", "narrator"),
    "military_service_period": ("event.service.period", "narrator"),
    "military_wars_conflicts": ("event.service.conflict", "narrator"),
    "mother_birth_place": ("person.birth.place", "parent:mother"),
    "mother_birth_year": ("person.birth.date", "parent:mother"),
    "mother_maiden_name": ("person.name.birth_family", "parent:mother"),
    "mother_name": ("person.name.given", "parent:mother"),
    "mother_occupation": ("person.occupation", "parent:mother"),
    "name_origin": ("story.name_origin", "narrator"),
    "nickname": ("person.name.alias", "narrator"),
    "notable_moves": ("event.residence.place", "narrator"),
    "notable_workplace": ("event.work.career", "narrator"),
    "parents_marriage_year": ("event.union.date", "parents_union"),
    "political_engagement": ("event.activity.organization", "narrator"),
    "preferred_name": ("person.name.preferred", "narrator"),
    "previous_marriages": ("relationship.kind", "prior_partner"),
    "primary_career": ("event.work.career", "narrator"),
    "primary_employer": ("event.work.career", "narrator"),
    "religion_raised": ("person.faith.raised", "narrator"),
    "religious_practice_adult": ("person.faith.current", "narrator"),
    "retirement_year": ("event.retirement", "narrator"),
    "sibling_count": ("person.reported_count.siblings", "narrator"),
    "siblings_named": ("person.name.given", "sibling"),
    "spouse_birth_year": ("person.birth.date", "spouse"),
    "spouse_name": ("person.name.given", "spouse"),
    "travel_memories": ("trip.story", "trip"),
    "union_membership": ("event.activity.organization", "narrator"),
    "vocational_training": ("event.education.training", "narrator"),
}

# ── Profile Seed evidence paths → concept + subject ──────────────────────
# Profile Seed reads profile_json and projection paths that the other
# vocabularies do not all contain. Binding them here is what lets Profile Seed
# later resolve "is this topic answered?" against concepts rather than paths.
PROFILE_SEED_PATH_BINDINGS = {
    "basics.career": ("event.work.career", "narrator"),
    "basics.childhoodHome": ("event.residence.place", "narrator"),
    "basics.culture": ("person.heritage", "narrator"),
    "basics.occupation": ("person.occupation", "narrator"),
    "basics.schooling": ("event.education.schooling", "narrator"),
    "children": ("relationship.kind", "child"),
    "community.retirementStatus": ("event.retirement", "narrator"),
    "community.role": ("event.activity.role", "narrator"),
    "education.careerProgression": ("event.work.career", "narrator"),
    "education.earlyCareer": ("event.work.early", "narrator"),
    "education.higherEducation": ("event.education.higher", "narrator"),
    "education.highestLevel": ("event.education.level", "narrator"),
    "education.schooling": ("event.education.schooling", "narrator"),
    "family.children.count": ("person.reported_count.children", "narrator"),
    "family.children.firstName": ("person.name.given", "child"),
    "family.marriageDate": ("event.union.date", "union"),
    "family.siblingCount": ("person.reported_count.siblings", "narrator"),
    "family.siblings.firstName": ("person.name.given", "sibling"),
    "family.spouse.firstName": ("person.name.given", "spouse"),
    "marriage.status": ("relationship.kind", "spouse"),
    "military.branch": ("event.service.branch", "narrator"),
    "military.rank": ("event.service.rank", "narrator"),
    "military.served": ("person.military_service", "narrator"),
    "military.servicePeriod": ("event.service.period", "narrator"),
    "military.yearsOfService": ("event.service.period", "narrator"),
    "parents.occupation": ("person.occupation", "parent"),
    "personal.birthOrder": ("person.birth.order", "narrator"),
    "personal.childhoodGeography": ("event.residence.place", "narrator"),
    "personal.childhoodHome": ("event.residence.place", "narrator"),
    "personal.culture": ("person.heritage", "narrator"),
    "personal.ethnicity": ("person.heritage", "narrator"),
    "siblings": ("relationship.kind", "sibling"),
    "spouse": ("relationship.kind", "spouse"),
    "spouses": ("relationship.kind", "spouse"),
}

# ── profile_json keys → concept (Batch A5: the migration reads this store) ─
# profile_json is a legacy projection with no schema, and it spells the same
# fact several ways — measured 2026-09-22 across app.js, bio-builder-graph.js,
# chronology_accordion.py, prompt_composer.py and profile_seed*.py:
# dob/dateOfBirth, pob/placeOfBirth/place_of_birth, fullname/fullName/full_name,
# preferred/preferredName/preferred_name. Every spelling maps to ONE concept.
# Keys whose meaning cannot be pinned down (basics.location, basics.country)
# are deliberately NOT bound: the migration ledger keeps them, value intact,
# as `unmapped` rather than guessing.
#   subject "narrator" for basics.*; "by_relation" for kinship[] entries,
#   where each entry's own `relation` decides the person.
PROFILE_JSON_BINDINGS = {
    "basics.fullname": ("person.name.full", "narrator"),
    "basics.fullName": ("person.name.full", "narrator"),
    "basics.full_name": ("person.name.full", "narrator"),
    "basics.preferred": ("person.name.preferred", "narrator"),
    "basics.preferredName": ("person.name.preferred", "narrator"),
    "basics.preferred_name": ("person.name.preferred", "narrator"),
    "basics.firstName": ("person.name.given", "narrator"),
    "basics.dob": ("person.birth.date", "narrator"),          # chronology_accordion.py:1022
    "basics.dateOfBirth": ("person.birth.date", "narrator"),
    "basics.pob": ("person.birth.place", "narrator"),
    "basics.placeOfBirth": ("person.birth.place", "narrator"),
    "basics.place_of_birth": ("person.birth.place", "narrator"),
    "basics.dateOfDeath": ("person.death.date", "narrator"),
    "basics.culture": ("person.heritage", "narrator"),
    "basics.career": ("event.work.career", "narrator"),
    "basics.occupation": ("person.occupation", "narrator"),
    "basics.schooling": ("event.education.schooling", "narrator"),
    "basics.higherEducation": ("event.education.higher", "narrator"),
    "basics.childhoodHome": ("event.residence.place", "narrator"),
    # kinship[] entries (read by bio-builder-graph.js syncFromProfile)
    "kinship.name": ("person.name.full", "by_relation"),
    "kinship.maidenName": ("person.name.birth_family", "by_relation"),
    "kinship.birthDate": ("person.birth.date", "by_relation"),
    "kinship.pob": ("person.birth.place", "by_relation"),
    "kinship.occupation": ("person.occupation", "by_relation"),
    "kinship.deceased": ("person.life_status", "by_relation"),
    "kinship.relation": ("relationship.kind", "by_relation"),
    # pets[] entries
    "pets.name": ("animal.name", "animal"),
    "pets.species": ("animal.species", "animal"),
    "pets.breed": ("animal.breed", "animal"),
}

# ── concepts ─────────────────────────────────────────────────────────────
# (label, value_type, cardinality). The kind of subject comes from the prefix.
CONCEPTS = {
    "person.name.full": ("Full name as written", "name", "many"),
    "person.name.given": ("Given name", "name", "many"),
    "person.name.family": ("Family name", "name", "many"),
    "person.name.birth_family": ("Birth family name", "name", "one"),
    "person.name.preferred": ("Preferred name", "name", "one"),
    "person.name.alias": ("Also known as", "name", "many"),
    "person.birth.date": ("Date of birth", "date", "one"),
    "person.birth.place": ("Place of birth", "place_ref", "one"),
    "person.birth.time": ("Time of birth", "text", "one"),
    "person.birth.order": ("Birth order, as stated", "text", "one"),
    "person.death.date": ("Date of death", "date", "one"),
    "person.death.place": ("Place of death", "place_ref", "one"),
    "person.death.reported_age": ("Age at death, as reported by a source", "number", "one"),
    "person.life_status": ("Life status", "enum:deceased|explicitly_living|unknown", "one"),
    "person.occupation": ("Occupation", "text", "many"),
    "person.education": ("Education (of a relative)", "text", "many"),
    "person.heritage": ("Heritage, self-described", "text", "many"),
    "person.languages": ("Languages", "text", "many"),
    "person.faith.raised": ("Faith raised in", "text", "one"),
    "person.faith.current": ("Faith now", "text", "one"),
    "person.interest": ("Interest", "text", "many"),
    "person.military_service": ("Served in the military", "boolean_3", "one"),
    "person.reported_count.children": ("Children, count as stated", "number", "one"),
    "person.reported_count.grandchildren": ("Grandchildren, count as stated", "number", "one"),
    "person.reported_count.siblings": ("Siblings, count as stated", "number", "one"),
    "person.zodiac_sign": ("Zodiac sign (derived from birth date)", "text", "one"),
    "relationship.kind": ("Relationship to the narrator", "enum:relationship_kind", "one"),
    "relationship.period": ("Relationship period", "date_interval", "one"),
    "relationship.qualifier.lineage_side": ("Maternal or paternal side", "enum:maternal|paternal", "one"),
    "event.significant": ("Significant event", "occurrence", "many"),
    "event.loss": ("A loss", "occurrence", "many"),
    "event.retirement": ("Retirement", "occurrence", "one"),
    "event.union.date": ("Union date", "date", "one"),
    "event.union.place": ("Union place", "place_ref", "one"),
    "event.union.participant": ("Union partner", "person_ref", "many"),
    "event.education.schooling": ("Schooling", "occurrence", "many"),
    "event.education.higher": ("Higher education", "occurrence", "many"),
    "event.education.level": ("Highest level reached", "text", "one"),
    "event.education.training": ("Training", "occurrence", "many"),
    "event.work.career": ("Work", "occurrence", "many"),
    "event.work.early": ("Early work", "occurrence", "many"),
    "event.activity.organization": ("Organisation", "occurrence", "many"),
    "event.activity.role": ("Role in an organisation", "text", "many"),
    "event.activity.period": ("Years active", "date_interval", "many"),
    "event.residence.place": ("Place lived", "place_ref", "many"),
    "event.residence.period": ("Period lived there", "date_interval", "many"),
    "event.residence.type": ("Kind of home", "text", "many"),
    "event.service.branch": ("Service branch", "text", "one"),
    "event.service.unit": ("Service unit", "text", "many"),
    "event.service.rank": ("Rank", "text", "many"),
    "event.service.role": ("Service role", "text", "many"),
    "event.service.place": ("Where served", "place_ref", "many"),
    "event.service.period": ("Service period", "date_interval", "many"),
    "event.service.decorations": ("Decorations", "text", "many"),
    "event.service.discharge": ("Discharge", "text", "one"),
    "event.service.conflict": ("Wars or conflicts", "text", "many"),
    "animal.name": ("Animal's name", "text", "one"),
    "animal.species": ("Species", "text", "one"),
    "animal.breed": ("Breed", "text", "one"),
    "animal.birth.date": ("Animal's birth date", "date", "one"),
    "animal.joined_household": ("Joined the household", "date", "one"),
    "story.memory": ("Memory", "story", "many"),
    "story.about_person": ("Story about a person", "story", "many"),
    "story.name_origin": ("How a name came about", "story", "many"),
    "story.reflection": ("Reflection", "story", "many"),
    "story.lesson": ("Lesson", "story", "many"),
    "story.message": ("Message for others", "story", "many"),
    "story.desired": ("A story the narrator wants told", "story", "many"),
    "story.tradition": ("Tradition", "story", "many"),
    "story.union": ("Story of a union", "story", "many"),
    "story.service": ("Story of service", "story", "many"),
    "story.home": ("Story of a home", "story", "many"),
    "story.faith": ("Story of faith", "story", "many"),
    "story.reading": ("Reading, as the narrator tells it", "story", "many"),
    "story.health.reflection": ("Health, as the narrator reflects on it", "story", "many"),
    "story.life_today.routine": ("A day now, described", "story", "many"),
    "trip.view": ("Travel (the trip domain)", "trip_ref", "many"),
    "trip.destination": ("Trip destination", "place_ref", "one"),
    "trip.date": ("Trip date", "date", "one"),
    "trip.purpose": ("Trip purpose", "text", "one"),
    "trip.companions": ("Trip companions", "person_ref", "many"),
    "trip.story": ("Trip story", "story", "many"),
    "story.about_animal": ("Story about an animal", "story", "many"),
    "event.service.occurrence": ("A period of service, as described", "text", "many"),
}

# Concepts the questionnaire shows but that are COMPUTED, never stored (D1f).
DERIVED_CONCEPTS = {"person.zodiac_sign": "D1f"}

# Concepts D1f made extractable where no extraction path exists yet (the
# paths are added in Batch A2/A3). Recorded here so the catalog states intent.
EXTRACTION_ADDED = {
    # concept: (decision, sections where extraction may offer it)
    "person.life_status": ("D1f", ("parents", "spouse")),   # Q10
    # Q02: relatives' middle and birth-family names are person.name.given /
    # person.name.birth_family, already extractable in those sections; D1f
    # adds the missing PATHS in Batch A3, not a new concept.
}

# The narrator's own identity is rendered on every turn today, in the
# TRIM_NEVER `identity_facts` section (prompt_composer.py:576-602: name,
# date of birth, place of birth). For anyone else, name, relationship and
# life status are TURN-SCOPED: required when the person is being discussed,
# otherwise retrieved (WO-LIFE-RECORD-01 §9.1).
PROMPT_ROLE = {
    "person.name.full":      {"narrator": "constant", "other": "turn_scoped"},
    "person.name.preferred": {"narrator": "constant", "other": "turn_scoped"},
    "person.name.given":     {"narrator": "retrieved", "other": "turn_scoped"},
    "person.birth.date":     {"narrator": "constant", "other": "retrieved"},
    "person.birth.place":    {"narrator": "constant", "other": "retrieved"},
    "relationship.kind":     {"narrator": "never", "other": "turn_scoped"},
    "person.life_status":    {"narrator": "constant", "other": "turn_scoped"},
}

# The life span's anchors (WO-LIFE-RECORD-01 §2A, D5).
SPECIAL_PROJECTION = {
    "person.birth.date": {"when": "subject_is_narrator", "supplies": "life_span.start"},
    "person.death.date": {"when": "subject_is_narrator", "supplies": "life_span.end"},
}

# Where a decision's wording and the concept used here differ, it is said
# here rather than silently. Each needs Chris's confirmation.
RECONCILIATIONS = [
    {
        "decision": "D1e",
        "decided_wording": "great-grandparent service as `person.service.*` about that person",
        "catalog_uses": "event.service.* with that person as participant",
        "why": "D7 (decided the same day) made occurrences canonical, and "
               "WO-LIFE-RECORD-01 §3.5 lists `service` as an occurrence type. The "
               "narrator's own service uses the same concepts, so a great-grandparent's "
               "Navy service and the narrator's are one concept about two people. The "
               "D1e intent — about THAT person, source and uncertainty kept — holds.",
        "status": "confirmed: D1e refinement, 2026-09-22",
    },
    {
        "decision": "D11",
        "decided_wording": "D1d retired seven EXTRACTION-ONLY notes paths; D1f retired siblings.notes",
        "catalog_uses": "parents/faith/military/pets/travel .notes bound to their story/trip "
                        "lane, questionnaire-editable, retired from structured extraction",
        "why": "These five live in BOTH the form and the extractor. D1d's argument "
               "(a bucket invites the extractor to file anything it cannot classify) "
               "applies, but no decision covered them, and retiring undecided paths is "
               "the silent promotion the decision record exists to prevent.",
        "status": "decided: D11, 2026-09-22",
    },
]
