"""Server authority for the ten-topic Profile Seed walk.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 1 (2026-08-26).

WHAT THIS MODULE OWNS
─────────────────────
The canonical topic registry — INCLUDING the narrator-facing wording of
all ten questions — the identity precondition, the evidence resolver,
and the reconciliation that keeps the durable row honest.

Nothing else. It composes no prompt and has no opinion about the
browser, and it holds no NARRATOR prose: the ten questions are Lori's
words, not the narrator's, and no answer text ever reaches this module.

*(The wording moved here in Phase 2 step 4. Work order 4.1 requires the
composer to render FROM this registry and forbids it keeping a second
hand-written order — so the questions live with the ids they belong to,
and both the live walk and the historical Pass-1 block are generated
from this one list.)*

THREE RULES ABOUT ITS SHAPE, EACH OF WHICH IS LOAD-BEARING
──────────────────────────────────────────────────────────

**1. No FastAPI, no router, no `api.db` import.** Every function that
touches storage takes an open `sqlite3.Connection`. `db.py` imports
this module for enrollment; if this module imported `db.py` back, the
cycle would surface as an import error at the worst moment. Taking the
connection is also what makes rule 2 possible.

**2. One connection means one snapshot.** The three truth stores this
resolver reads — `profiles.profile_json`, `interview_projections`,
`bio_facts` — each have an accessor in `db.py` that opens its OWN
connection. Resolving through those would read three unrelated points
in time, and worse, would make it impossible to re-resolve inside the
PATCH write transaction, which is precisely where a consistent read
matters most. So the snapshot is read here, directly, on the caller's
connection.

**3. The caller owns the transaction.** Nothing here commits. Enrollment
must land in the same transaction as the `people` row, and reconciliation
must land inside PATCH's `BEGIN IMMEDIATE`. A commit in this module
would silently break both.

WHAT COUNTS AS EVIDENCE, AND THE MISTAKE THIS REPLACES
──────────────────────────────────────────────────────
`prompt_composer._build_profile_seed()` assembles a readback string for
Lori's memory echo. It is not a completion gate and must not become
one: its `_first_str()` helper accepts only `isinstance(v, str)`, which
means the two answers that matter most to an onboarding walk — a zero
count and an explicit `False` — are invisible to it. Phase 0 measured
the consequence: `military.served` is ignored in BOTH directions, so
"served", "did not serve" and "never asked" are indistinguishable.

Here, **presence is the test, not truthiness.** `0` is evidence. `False`
is evidence. An empty string is not, and an empty list is not — an
empty `children` array cannot tell an explicit "none" apart from an
untouched optional section, which is exactly the ambiguity the walk
exists to resolve.

Two evidence rules are prohibitions rather than sources, and both come
from measurements in the work order:

  * **birthplace is never childhood-home evidence.** Being born
    somewhere does not prove you grew up there, and today a real
    `bio_facts.childhood_home_address` is overridden by the birthplace
    it should have beaten.
  * **an age band is never life-stage evidence.** "elder / retirement
    years" is arithmetic on a date of birth. The question is whether
    the narrator is retired or still working, and a narrator who still
    works at eighty is not answered by a birthday.

`known` is DERIVED and recomputed on every resolve, so evidence that is
corrected or superseded does not leave a fossilised `known` behind.
`addressed` and `declined` are STORED, because "they answered" and
"they would rather not" are facts about the conversation that no truth
store records.

STORAGE FAULTS ARE NOT ABSENCE
──────────────────────────────
**No reader in this module catches `sqlite3.Error`.** The first version
of all five caught it and returned an empty result, which is the
ordinary defensive habit and was wrong here, because in this module
EVERY EMPTY RESULT IS A PRODUCT DECISION:

  * no onboarding row  -> "this narrator is HISTORICAL, never enrol
    them";
  * no `people` row    -> "the identity anchors are missing, hold the
    walk at `pending`";
  * no `bio_facts`     -> "all ten topics are UNANSWERED".

The third is the one that matters most. A locked database, a corrupt
page or a closed connection would have produced a narrator with ten
unanswered topics — and the product's response to that is to ask them
all ten questions again. Someone who has already told Lori about their
siblings gets asked about their siblings because a query failed.
Principle 8 is that Lori must not interrogate the narrator for facts
the system already has; silently converting "could not read" into
"nothing is known" is how that principle gets violated by
infrastructure rather than by design.

Every caller reaches these readers through `init_db()`, which applies
migration 0051, so a missing table is a fault and not a phase. SQLite
errors propagate and become 500s. A 500 is a bad afternoon for the
operator; a silent re-interrogation is a bad afternoon for the
narrator, and only one of them is visible.

The narrow JSON-decoding defences are KEPT and are a different case: a
malformed `profile_json` is a real, recoverable data condition that
predates this lane, and treating one unparseable blob as "no profile"
degrades one topic rather than inventing a lifecycle state.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ── The four states (work order §4.2) ────────────────────────────────────
UNANSWERED = "unanswered"
KNOWN = "known"
ADDRESSED = "addressed"
DECLINED = "declined"

TOPIC_STATES: Tuple[str, ...] = (UNANSWERED, KNOWN, ADDRESSED, DECLINED)

#: Only these two may be written by a client. `known` is evidence-derived
#: and `unanswered` is the absence of everything — a client that could
#: declare either would be able to fake completion, or to un-answer a
#: question the narrator already answered.
CLIENT_DISPOSITIONS: Tuple[str, ...] = (ADDRESSED, DECLINED)

#: Stored dispositions survive reconciliation. Everything else is recomputed.
DURABLE_DISPOSITIONS: Tuple[str, ...] = (ADDRESSED, DECLINED)

#: A topic in any of these is finished. Asking again is interrogation.
FINAL_STATES: Tuple[str, ...] = (KNOWN, ADDRESSED, DECLINED)

# ── Lifecycle (work order §4.2) ──────────────────────────────────────────
STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"

STATUSES: Tuple[str, ...] = (STATUS_PENDING, STATUS_ACTIVE,
                             STATUS_PAUSED, STATUS_COMPLETED)

TABLE = "profile_seed_onboarding"


# ── Evidence-valid bio_fact statuses ─────────────────────────────────────
#: From the status enum documented in migration 0011. The exclusions are
#: the interesting part:
#:
#:   `empty`                  — a placeholder with no value.
#:   `anchored_asked_pending` — the ASK fired and no value came back.
#:                              Treating this as evidence would mark a
#:                              topic known because Lori raised it once.
#:   `superseded`             — the operator chose a different row.
#:   `conflicted`             — peer rows disagree and no human has
#:                              resolved it. An unresolved conflict is
#:                              not an answer.
#:
#: `extracted_needs_verify` IS included, because provisional truth
#: persists and Lori reads from it (CLAUDE.md principle 5). A narrator
#: should not be re-asked something they said last Tuesday merely
#: because the operator has not got to the review queue yet.
EVIDENCE_BIO_STATUSES: Tuple[str, ...] = (
    "extracted_needs_verify",
    "document_sourced",
    "anchored_asked",
    "operator_entered",
    "approved",
)


@dataclass(frozen=True)
class TopicDefinition:
    """One canonical topic. The composer renders from this in Phase 2;
    it must not keep a second hand-written order."""

    topic_id: str
    #: Narrator-facing INTENT — what the topic is for.
    intent: str
    #: THE MODEL-FACING DIRECTIVE. **NOT narrator-facing speech.**
    #:
    #: ── THIS DOCSTRING WAS WRONG UNTIL 2026-08-30 ──────────────────
    #:
    #: *(It read "THE NARRATOR-FACING QUESTION, and there is exactly one
    #: of these." Not one of the ten was narrator-facing. Every entry
    #: carried an ALL-CAPS label prefix, third person throughout
    #: ("they", "their"), and the set included a `[their birthplace]`
    #: placeholder and an operator aside — "(Ask warmly — many older
    #: narrators did.)". Two were compound questions the ONE THOUGHT,
    #: ONE QUESTION rule forbids outright.*
    #:
    #: *The docstring itself explains how: the wording was "moved
    #: VERBATIM from the hard-coded ten-item list that lived inside
    #: `prompt_composer`'s pass-1 directive block" — a list the MODEL
    #: read. Nothing was ever rewritten for the narrator, and calling
    #: it narrator-facing for four months is what let a delivery
    #: contract be specified against text no narrator can be told.)*
    #:
    #: Retained for prompt-directive compatibility: the composer still
    #: renders from it, and the work order's rule that the registry owns
    #: the order is unchanged. It fixes WHICH question. It is never what
    #: the narrator hears — that is `narrator_question`.
    question: str
    #: THE NARRATOR-FACING QUESTION. Exactly one, and it is spoken.
    #:
    #: Server-owned and delivered VERBATIM on a PRESENT or RE_PRESENT
    #: turn. That is the whole point: `WO-LORI-PROFILE-SEED-...` Phase 3
    #: found the model committing a `presented(childhood_home)` event
    #: while visibly asking "Where would you like to continue today?",
    #: and the next unrelated narrator turn was then recorded as the
    #: answer — closing the topic permanently without it ever being
    #: asked. A delivery guarantee cannot be built on prose the model
    #: chooses, so the question sentence is the server's.
    #:
    #: Approved wording, 2026-08-30. Second person, one question each,
    #: plain language, no labels or placeholders or operator asides, and
    #: deliberately LESS ASSUMPTIVE about family structure than the
    #: directives above. Lori's reflection on what the narrator just said
    #: still precedes it; only this sentence is fixed.
    narrator_question: str
    #: Whether an explicit negative is a meaningful answer for this topic
    #: ("no siblings", "I did not serve", "no children", "never married").
    negative_meaningful: bool
    #: `bio_facts.field_key` values that answer this topic. Every one is
    #: asserted to exist in `bio_schema` by the Phase 1 test suite, so an
    #: invented key fails a test rather than silently resolving to
    #: "unanswered" forever.
    bio_keys: Tuple[str, ...]
    #: Dotted paths into `profiles.profile_json`, tried against both the
    #: template shape and the `basics` shape.
    profile_paths: Tuple[str, ...]
    #: `interview_projections` field paths — from `projection.fields` and
    #: `projection.pendingSuggestions`.
    projection_paths: Tuple[str, ...]


#: THE CANONICAL REGISTRY, in the work order's order (§4.1).
TOPIC_REGISTRY: Tuple[TopicDefinition, ...] = (
    TopicDefinition(
        "childhood_home",
        "where the narrator grew up",
        "CHILDHOOD HOME — Did they grow up in [their birthplace], or did the family move?",
        "Where did you grow up?",
        negative_meaningful=False,
        bio_keys=("childhood_home_address", "childhood_homes",
                  "childhood_geography"),
        # NOTE the absence of every birthplace path. That absence is the
        # correction; see the module docstring.
        profile_paths=("personal.childhoodHome", "basics.childhoodHome",
                       "personal.childhoodGeography"),
        projection_paths=("personal.childhoodHome",),
    ),
    TopicDefinition(
        "siblings",
        "brothers and sisters, and where the narrator came in the order",
        "SIBLINGS — Were they an only child, or did they have brothers and sisters?",
        "Did you have any brothers or sisters?",
        negative_meaningful=True,
        bio_keys=("sibling_count", "siblings_named", "birth_order"),
        profile_paths=("family.siblingCount", "siblings"),
        projection_paths=("family.siblingCount", "personal.birthOrder",
                          "family.siblings.firstName"),
    ),
    TopicDefinition(
        "parents_work",
        "what the narrator's parents did for a living",
        "PARENTS' WORK — What did their parents do for a living?",
        "What kind of work did your parents or the people who raised you do?",
        negative_meaningful=False,
        bio_keys=("father_occupation", "mother_occupation"),
        # DELIBERATELY EMPTY. `parents` and `kinship` were listed here in
        # the first draft and a test caught it: a non-empty `parents`
        # list is not evidence about their WORK. Two names with no
        # occupations would have marked "what did your parents do for a
        # living" as answered, and the narrator would never be asked.
        # `_parents_have_work()` inspects the entries instead.
        profile_paths=(),
        projection_paths=("parents.occupation",),
    ),
    TopicDefinition(
        "heritage",
        "where the family came from, and what they carried with them",
        "HERITAGE — Do they know where the family originally came from — grandparents' background?",
        "What do you know about where your family came from?",
        negative_meaningful=True,
        bio_keys=("ethnicity_heritage", "grandparents_origin"),
        profile_paths=("personal.culture", "basics.culture",
                       "personal.ethnicity"),
        projection_paths=("personal.culture", "personal.ethnicity"),
    ),
    TopicDefinition(
        "education",
        "how far the narrator went in school",
        "EDUCATION — How far did they go in school — did they go to college?",
        "What schooling or education did you have?",
        negative_meaningful=True,
        bio_keys=("highest_education_level", "high_school", "college_attended"),
        # `education.highestLevel` is what the intake form actually
        # writes; the seed reads `schooling`/`higherEducation` and so
        # cannot see an operator-supplied answer. Both are read here.
        profile_paths=("education.highestLevel", "education.schooling",
                       "education.higherEducation", "basics.schooling"),
        projection_paths=("education.schooling", "education.higherEducation"),
    ),
    TopicDefinition(
        "military",
        "whether the narrator served, and what that was like",
        "MILITARY — Did they serve in the military? (Ask warmly — many older narrators did.)",
        "Did you ever serve in the military?",
        negative_meaningful=True,
        bio_keys=("military_served", "military_branch",
                  "military_service_period"),
        # `military.served` is read as a BOOLEAN in both directions.
        profile_paths=("military.served", "military.branch",
                       "military.servicePeriod", "military.rank"),
        projection_paths=("military.branch", "military.yearsOfService"),
    ),
    TopicDefinition(
        "career",
        "the work the narrator did",
        "CAREER — What was their main work or career over the years?",
        "What kind of work did you do over the years?",
        negative_meaningful=True,
        bio_keys=("primary_career", "first_job", "primary_employer"),
        profile_paths=("education.careerProgression", "community.role",
                       "basics.career", "basics.occupation"),
        projection_paths=("education.careerProgression", "community.role",
                          "education.earlyCareer"),
    ),
    TopicDefinition(
        "partner",
        "who the narrator married or shared their life with",
        "PARTNER — Have they been married, or do they have a long-term partner?",
        "Would you like to tell me about a spouse or partner in your life?",
        negative_meaningful=True,
        # `marital_status` is added to the bio schema by this phase — it
        # is the canonical home an explicit "never married" did not have.
        bio_keys=("marital_status", "spouse_name", "marriage_year"),
        profile_paths=("marriage.status", "spouse", "spouses"),
        projection_paths=("family.spouse.firstName", "family.marriageDate"),
    ),
    TopicDefinition(
        "children",
        "the narrator's children",
        "CHILDREN — Do they have children? Grandchildren?",
        "Do you have children?",
        negative_meaningful=True,
        bio_keys=("children_count", "children_named"),
        profile_paths=("children",),
        projection_paths=("family.children.count",
                          "family.children.firstName"),
    ),
    TopicDefinition(
        "life_stage",
        "whether the narrator is retired or still working",
        "LIFE STAGE — Are they retired now, or still working?",
        "Are you retired now?",
        negative_meaningful=False,
        bio_keys=("retirement_year",),
        # NOTE the absence of every date-of-birth path. An age band is
        # arithmetic, not an answer; see the module docstring.
        profile_paths=("community.retirementStatus",),
        projection_paths=("community.retirementStatus",),
    ),
)

TOPIC_IDS: Tuple[str, ...] = tuple(t.topic_id for t in TOPIC_REGISTRY)
_TOPIC_BY_ID: Dict[str, TopicDefinition] = {t.topic_id: t for t in TOPIC_REGISTRY}


def topic(topic_id: str) -> Optional[TopicDefinition]:
    return _TOPIC_BY_ID.get(topic_id)


def is_known_topic(topic_id: Any) -> bool:
    return isinstance(topic_id, str) and topic_id in _TOPIC_BY_ID


# ── Errors ───────────────────────────────────────────────────────────────
class ProfileSeedError(Exception):
    """Base for every failure this module reports to a route."""


class NotEnrolled(ProfileSeedError):
    """No onboarding row — the narrator is HISTORICAL.

    This is not an error to be repaired by writing a row. Auto-enrolling
    an existing narrator because their profile has gaps is forbidden by
    work order decision 3, and it would mean a narrator who has been
    talking to Lori for months suddenly gets asked where they grew up.
    """

    def __init__(self, person_id: str):
        super().__init__(f"{person_id} is not enrolled in Profile Seed onboarding")
        self.person_id = person_id


class PersonNotFound(ProfileSeedError):
    """No `people` row at all — 404.

    Distinct from `NotEnrolled`, and the distinction is the point.
    `NotEnrolled` is a statement about a REAL narrator: they predate
    migration 0051 and are deliberately not being walked through
    onboarding, so `enrolled: false` is the truthful, settled answer and
    a 200 is correct for it.

    A `person_id` that names nobody is not that. Answering it with the
    same reassuring 200 would tell a client that a typo, a stale
    bookmark or a deleted narrator is a legitimate historical narrator,
    and nothing in the response would let them tell the difference.
    """

    def __init__(self, person_id: str):
        super().__init__(f"no narrator exists with person_id {person_id!r}")
        self.person_id = person_id


class UnknownTopic(ProfileSeedError):
    """A topic id that is not in the canonical registry — 422."""

    def __init__(self, topic_id: Any):
        super().__init__(f"unknown Profile Seed topic: {topic_id!r}")
        self.topic_id = topic_id


class VersionConflict(ProfileSeedError):
    """The caller's read is stale — 409, and NOTHING was written.

    `current` carries the freshly resolved state so the client can
    re-render without a second round trip.
    """

    def __init__(self, expected: int, actual: int, current: "ResolvedState"):
        super().__init__(
            f"Profile Seed version conflict: expected {expected}, "
            f"current is {actual}"
        )
        self.expected = expected
        self.actual = actual
        self.current = current


class TopicNotActive(ProfileSeedError):
    """The topic is real, but it is not the one currently being asked.

    This is the failure the work order's concurrency note is about. A
    client GETs while `siblings` is active; the operator then enters the
    sibling count in Bio Builder; the client PATCHes `siblings` as
    addressed. The progress row's own version may not have moved, so
    `expected_version` alone would let the write land on a topic that is
    already answered and no longer being asked. Re-resolving inside the
    write transaction is what catches it.
    """

    def __init__(self, topic_id: str, active_topic_id: Optional[str]):
        super().__init__(
            f"topic {topic_id!r} is not the active topic "
            f"(active: {active_topic_id!r})"
        )
        self.topic_id = topic_id
        self.active_topic_id = active_topic_id


# ── The identity precondition ────────────────────────────────────────────
def identity_anchors_complete(person: Mapping[str, Any],
                              profile_basics: Mapping[str, Any]) -> bool:
    """Does this narrator have the three identity anchors?

    Requires display_name (or a preferred name) plus date_of_birth plus
    place_of_birth.

    **This is `routers.interview._identity_complete` moved, not rewritten.**
    Behaviour is preserved exactly, including the `or` between
    display_name and preferred and the `bool()` coercion of each. The
    router now imports it from here so that the Profile Seed resolver
    and the opener use ONE definition of "we know who this is" — a
    second definition would drift, and the two consumers would disagree
    about whether the walk may start.

    It lives here rather than in the router because the resolver must not
    import FastAPI, and it is a pure predicate over two mappings with no
    router concerns of its own.
    """
    name_ok = bool((person or {}).get("display_name")
                   or (profile_basics or {}).get("preferred"))
    dob_ok = bool((person or {}).get("date_of_birth"))
    pob_ok = bool((person or {}).get("place_of_birth"))
    return name_ok and dob_ok and pob_ok


# ── Presence ─────────────────────────────────────────────────────────────
def has_value(value: Any) -> bool:
    """Is this a real answer?

    PRESENCE, not truthiness. The distinction is the whole point:

        has_value(0)      -> True    an only child answered "none"
        has_value(False)  -> True    "I did not serve" is an answer
        has_value("")     -> False
        has_value([])     -> False   an empty array cannot tell an
                                     explicit "none" from an untouched
                                     optional section
        has_value(None)   -> False
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def _dig(root: Any, dotted: str) -> Any:
    """Walk a dotted path through nested mappings. Missing -> None."""
    cur = root
    for part in dotted.split("."):
        if not isinstance(cur, Mapping):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


# ── The snapshot ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Snapshot:
    profile: Mapping[str, Any]
    projection: Mapping[str, Any]
    bio: Mapping[str, Any]


def _load_profile_root(con: sqlite3.Connection, person_id: str) -> Mapping[str, Any]:
    # NO `except sqlite3.Error` HERE — see STORAGE FAULTS ARE NOT ABSENCE.
    row = con.execute(
        "SELECT profile_json FROM profiles WHERE person_id=?;",
        (person_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        blob = json.loads(row[0] or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(blob, Mapping):
        return {}
    # `profile_json` is written both as `{profile: {...}}` and flat,
    # depending on which writer hydrated the row.
    inner = blob.get("profile")
    return inner if isinstance(inner, Mapping) else blob


def _load_projection_values(con: sqlite3.Connection,
                            person_id: str) -> Dict[str, Any]:
    """Flatten `projection.fields` + `pendingSuggestions` to path -> value.

    Unlike `_build_profile_seed`, values are kept at their real type.
    A projected `False` or `0` arrives here intact, which is the point.
    Committed `fields` win over `pendingSuggestions` for the same path.
    """
    out: Dict[str, Any] = {}
    # NO `except sqlite3.Error` HERE — see STORAGE FAULTS ARE NOT ABSENCE.
    row = con.execute(
        "SELECT projection_json FROM interview_projections WHERE person_id=?;",
        (person_id,),
    ).fetchone()
    if not row:
        return out
    try:
        proj = json.loads(row[0] or "{}")
    except (TypeError, ValueError):
        return out
    if not isinstance(proj, Mapping):
        return out

    fields = proj.get("fields")
    if isinstance(fields, Mapping):
        for path, entry in fields.items():
            if isinstance(entry, Mapping) and "value" in entry:
                out[str(path)] = entry["value"]

    suggestions = proj.get("pendingSuggestions")
    if isinstance(suggestions, (list, tuple)):
        for sug in suggestions:
            if not isinstance(sug, Mapping):
                continue
            path = sug.get("fieldPath")
            if isinstance(path, str) and "value" in sug:
                out.setdefault(path, sug["value"])
    return out


def _load_bio_values(con: sqlite3.Connection, person_id: str) -> Dict[str, Any]:
    """Most recent evidence-valid `bio_facts` value per field_key.

    Ordered oldest-first so the newest write is the one that survives the
    dict assignment. Statuses outside `EVIDENCE_BIO_STATUSES` never enter
    — see the constant for why each exclusion matters.
    """
    out: Dict[str, Any] = {}
    placeholders = ",".join("?" * len(EVIDENCE_BIO_STATUSES))
    # NO `except sqlite3.Error` HERE — see STORAGE FAULTS ARE NOT ABSENCE.
    # This reader is the most dangerous of the five to suppress: an
    # unreadable `bio_facts` makes every topic look unanswered, which is
    # the exact shape of "ask this narrator all ten questions again".
    rows = con.execute(
        "SELECT field_key, value FROM bio_facts "
        f"WHERE narrator_id=? AND status IN ({placeholders}) "  # noqa: S608
        "ORDER BY last_updated ASC;",
        (person_id, *EVIDENCE_BIO_STATUSES),
    ).fetchall()
    for row in rows:
        key = row[0]
        raw = row[1]
        try:
            value = json.loads(raw) if raw is not None else None
        except (TypeError, ValueError):
            # A non-JSON legacy value is still a value.
            value = raw
        out[str(key)] = value
    return out


def load_snapshot(con: sqlite3.Connection, person_id: str) -> _Snapshot:
    """One consistent read of all three truth stores, on ONE connection."""
    return _Snapshot(
        profile=_load_profile_root(con, person_id),
        projection=_load_projection_values(con, person_id),
        bio=_load_bio_values(con, person_id),
    )


def _parents_have_work(profile: Mapping[str, Any]) -> bool:
    """`parents[]` / `kinship[]` entries carrying an occupation.

    Split out because a non-empty `parents` list is not by itself
    evidence about their WORK — a list of names with no occupations
    answers a different question than the one being asked.
    """
    for key in ("parents", "kinship"):
        entries = profile.get(key)
        if not isinstance(entries, (list, tuple)):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            if key == "kinship":
                relation = str(entry.get("relation")
                               or entry.get("role") or "").lower()
                if relation not in ("mother", "father", "parent"):
                    continue
            for occ_key in ("occupation", "work", "job"):
                if has_value(entry.get(occ_key)):
                    return True
    return False


def topic_has_evidence(topic_def: TopicDefinition, snap: _Snapshot) -> bool:
    """Does structured truth already answer this topic?"""
    for key in topic_def.bio_keys:
        if key in snap.bio and has_value(snap.bio[key]):
            return True
    for path in topic_def.projection_paths:
        if path in snap.projection and has_value(snap.projection[path]):
            return True
    for path in topic_def.profile_paths:
        if has_value(_dig(snap.profile, path)):
            return True
    if topic_def.topic_id == "parents_work" and _parents_have_work(snap.profile):
        return True
    return False


# ── Resolved state ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class ResolvedState:
    person_id: str
    status: str
    topic_state: Mapping[str, str]
    active_topic_id: Optional[str]
    version: int
    identity_complete: bool
    created_at: str
    updated_at: str
    completed_at: Optional[str]
    #: WHICH QUESTION IS OUTSTANDING — not how many times the row has
    #: been written. See migration 0052. `version` guards writes; this
    #: identifies the question, and the two must never be conflated
    #: again. Defaulted so every existing constructor call keeps working
    #: and so a malformed or pre-0052 row reads as "no question".
    presentation_epoch: int = 0

    @property
    def known_topics(self) -> List[str]:
        return [t for t in TOPIC_IDS if self.topic_state.get(t) == KNOWN]

    @property
    def remaining_topics(self) -> List[str]:
        return [t for t in TOPIC_IDS if self.topic_state.get(t) == UNANSWERED]

    def as_dict(self) -> Dict[str, Any]:
        """The API body. Ordered lists, never a set — the walk has an order."""
        return {
            "person_id": self.person_id,
            "enrolled": True,
            "status": self.status,
            "identity_complete": self.identity_complete,
            "topic_state": dict(self.topic_state),
            "active_topic_id": self.active_topic_id,
            "known_topics": self.known_topics,
            "remaining_topics": self.remaining_topics,
            "version": self.version,
            # Exposed because the turn reducer correlates on it. A client
            # may READ it; nothing lets a client author it, and the
            # composer only trusts an attested server-resolved payload.
            "presentation_epoch": self.presentation_epoch,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


def not_enrolled_body(person_id: str) -> Dict[str, Any]:
    """What a HISTORICAL narrator looks like over the wire.

    A distinct shape rather than an empty progress row, so no consumer
    can mistake "never enrolled" for "enrolled with nothing done" and
    start asking questions.
    """
    return {
        "person_id": person_id,
        "enrolled": False,
        "status": None,
        "topic_state": {},
        "active_topic_id": None,
        "known_topics": [],
        "remaining_topics": [],
        "version": None,
        # `None`, not 0. A historical narrator has no question outstanding
        # and never will; 0 is a real epoch belonging to a real enrolled
        # row that has not started yet, and the two must not read alike.
        "presentation_epoch": None,
    }


def initial_topic_state() -> Dict[str, str]:
    return {t: UNANSWERED for t in TOPIC_IDS}


def _coerce_topic_state(raw: Any) -> Dict[str, str]:
    """Read stored JSON defensively.

    Unknown keys are dropped and unknown values fall back to
    `unanswered`. A topic added to the registry later therefore appears
    as unanswered on an existing row rather than as a KeyError on every
    turn.
    """
    parsed: Mapping[str, Any] = {}
    if isinstance(raw, str):
        try:
            candidate = json.loads(raw or "{}")
        except (TypeError, ValueError):
            candidate = {}
        if isinstance(candidate, Mapping):
            parsed = candidate
    elif isinstance(raw, Mapping):
        parsed = raw

    out: Dict[str, str] = {}
    for topic_id in TOPIC_IDS:
        value = parsed.get(topic_id)
        out[topic_id] = value if value in TOPIC_STATES else UNANSWERED
    return out


def _valid_epoch(raw: Any) -> int:
    """A stored epoch, or 0 for anything unusable.

    Defensive for the same reason `_coerce_topic_state` is: a value this
    function cannot trust must not become a crash on every subsequent
    turn. 0 is the safe reading — it means "no question outstanding",
    which makes the next resolve mint a fresh epoch and re-present, and
    that is the direction that asks rather than assumes.

    Booleans are rejected explicitly. `True` is an `int` in Python and
    would compare equal to epoch 1, silently correlating an answer with a
    question it never belonged to — the same trap `_valid_version`
    documents in the reducer.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw if raw >= 0 else 0


def read_row(con: sqlite3.Connection, person_id: str) -> Optional[sqlite3.Row]:
    """The onboarding row, or `None` when the narrator is not enrolled.

    NO `except sqlite3.Error` HERE. The first version caught it and
    returned `None`, reasoning that the table is absent only before
    migration 0051 has run. That reasoning was wrong twice over: every
    caller reaches this through `init_db()`, which applies 0051, so a
    missing table is a fault rather than a phase; and `None` from this
    function is not "no table", it is **"this narrator is HISTORICAL"**
    — a settled product decision that a locked database or a corrupt
    page must never be able to make.
    """
    return con.execute(
        f"SELECT person_id, status, topic_state_json, active_topic_id, "  # noqa: S608
        f"version, presentation_epoch, created_at, updated_at, completed_at "
        f"FROM {TABLE} WHERE person_id=?;",
        (person_id,),
    ).fetchone()


def is_enrolled(con: sqlite3.Connection, person_id: str) -> bool:
    return read_row(con, person_id) is not None


def person_exists(con: sqlite3.Connection, person_id: str) -> bool:
    """Is there a `people` row at all?

    THE DISTINCTION THIS DRAWS IS PRODUCT-VISIBLE, not cosmetic.
    "Enrolled: false" is a statement ABOUT A REAL NARRATOR — that they
    predate migration 0051 and are deliberately not being walked
    through onboarding. Returning it for a person_id that does not exist
    says the same reassuring thing about a typo, a stale bookmark, or a
    narrator who was deleted, and a client cannot tell the two apart.

    Work order decision 3 governs HISTORICAL narrators. It says nothing
    about identifiers that name nobody, and a 200 is the wrong answer
    for those.
    """
    return con.execute(
        "SELECT 1 FROM people WHERE id=? LIMIT 1;", (person_id,),
    ).fetchone() is not None


def enroll(con: sqlite3.Connection, person_id: str, now: str) -> None:
    """Insert the onboarding row IN THE CALLER'S TRANSACTION.

    No commit, deliberately: `create_person()` must be able to roll the
    people row back if this fails, and it cannot do that if this has
    already committed. "Person created, onboarding best-effort" is
    explicitly refused by work order §4.2.

    Starts at `pending` regardless of what is already known. Reconciliation
    promotes it to `active` once the identity anchors are in place, so a
    narrator created with full details is `active` by their first resolve
    without a second creation-time code path deciding it.
    """
    con.execute(
        f"INSERT INTO {TABLE} "  # noqa: S608
        "(person_id, status, topic_state_json, active_topic_id, version, "
        " presentation_epoch, created_at, updated_at, completed_at) "
        # Epoch 0 means "no question has ever been outstanding". The first
        # reconcile that promotes this row to `active` moves it to 1.
        # Starting at 1 here would make a pending row indistinguishable
        # from a row with a live question.
        "VALUES (?, ?, ?, NULL, 1, 0, ?, ?, NULL);",
        (person_id, STATUS_PENDING, json.dumps(initial_topic_state()),
         now, now),
    )


def _person_and_basics(con: sqlite3.Connection,
                       person_id: str) -> Tuple[Dict[str, Any], Mapping[str, Any]]:
    # NO `except sqlite3.Error` HERE — see STORAGE FAULTS ARE NOT
    # ABSENCE. An empty `person` here reads as "the identity anchors are
    # missing", which holds the walk at `pending` — a database fault
    # would have looked exactly like a narrator whose name we do not
    # know yet.
    person: Dict[str, Any] = {}
    row = con.execute(
        "SELECT display_name, date_of_birth, place_of_birth "
        "FROM people WHERE id=?;",
        (person_id,),
    ).fetchone()
    if row:
        person = {
            "display_name": row[0],
            "date_of_birth": row[1],
            "place_of_birth": row[2],
        }
    profile = _load_profile_root(con, person_id)
    basics = profile.get("basics")
    return person, (basics if isinstance(basics, Mapping) else {})


def resolve_effective(con: sqlite3.Connection, person_id: str, *,
                      now: str) -> Optional[Tuple[ResolvedState, bool]]:
    """The resolution, with NO WRITE. `(state, changed)`, or `None`.

    ── EXTRACTED SO THERE IS ONE RESOLVER, 2026-08-26 ──────────────────

    Step 5 needs a narrator's onboarding state in order to compose a
    prompt, and must not write to find out: a read that materializes
    turns every page refresh into a version bump.

    The alternative was for the REST path to recompute status and active
    topic itself, and that would have been a SECOND definition of "what
    state is this narrator in". This lane has already paid twice for
    that exact shape — a renderer and a suppression predicate that
    disagreed about the same payload, and a baseline inventory
    duplicated beside the registry it described. Two definitions of one
    truth do not stay equal; they stay equal until the first change.

    So the computation lives here once. `reconcile()` calls it and
    writes when `changed` is True; a read-only caller ignores `changed`.

    **`state.version` is what the version WOULD BECOME had this been
    materialized.** A caller that does not write must not treat it as
    durable, nor use it to author a versioned write — that belongs to
    the committed-turn path, which reconciles first.

    Returning the resolved state without writing it would leave the
    durable row disagreeing with the API: a topic answered in Bio
    Builder would read as `known` over the wire while
    `topic_state_json`, `active_topic_id`, `status` and `version` still
    described the world before that answer. The next writer would then
    compare against a version that never moved.

    So:

      * stored `addressed` / `declined` are PRESERVED — no evidence
        change can un-answer a question the narrator answered;
      * every other topic is recomputed as `known` or `unanswered`;
      * `active_topic_id` becomes the first remaining topic in registry
        order;
      * `pending -> active` follows the identity anchors, and completion
        follows the topics;
      * `version` moves ONLY when the effective stored state changes, so
        a resolve that discovers nothing new does not invalidate a
        client's in-flight write;
      * `completed_at` is set exactly once;
      * `completed` is TERMINAL — a completed row is returned untouched,
        which is what stops a narrator being walked through onboarding a
        second time;
      * a narrator with no row gets `None` and NO INSERT.

    *(That list describes the RESOLUTION, which is why it lives on this
    function now rather than on `reconcile()`. `reconcile()` is the
    write half and says so.)*
    """
    row = read_row(con, person_id)
    if row is None:
        return None

    stored_state = _coerce_topic_state(row["topic_state_json"])
    stored_status = row["status"] if row["status"] in STATUSES else STATUS_PENDING
    stored_active = row["active_topic_id"]
    stored_version = int(row["version"] or 1)
    stored_epoch = _valid_epoch(row["presentation_epoch"])
    completed_at = row["completed_at"]

    if stored_status == STATUS_COMPLETED:
        # Terminal. Read-only, no recompute, no version movement.
        return ResolvedState(
            person_id=person_id,
            status=STATUS_COMPLETED,
            topic_state=stored_state,
            active_topic_id=None,
            version=stored_version,
            identity_complete=True,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=completed_at,
            # Carried, never reset. A completed walk is terminal, so this
            # is only ever read; zeroing it would let some future reopen
            # reuse an epoch that old turn metadata still refers to.
            presentation_epoch=stored_epoch,
        ), False

    person, basics = _person_and_basics(con, person_id)
    anchors_ok = identity_anchors_complete(person, basics)
    snap = load_snapshot(con, person_id)

    next_state: Dict[str, str] = {}
    for topic_def in TOPIC_REGISTRY:
        current = stored_state.get(topic_def.topic_id, UNANSWERED)
        if current in DURABLE_DISPOSITIONS:
            next_state[topic_def.topic_id] = current
            continue
        next_state[topic_def.topic_id] = (
            KNOWN if topic_has_evidence(topic_def, snap) else UNANSWERED
        )

    remaining = [t for t in TOPIC_IDS if next_state[t] == UNANSWERED]

    if not anchors_ok:
        # The walk must not begin before Lori knows who she is talking
        # to. This is CORRECT behaviour, pinned as such in Phase 0 —
        # not part of the reachability defect.
        next_status = STATUS_PENDING
    elif not remaining:
        next_status = STATUS_COMPLETED
    elif stored_status == STATUS_PAUSED:
        # A pause survives until an explicit resume. Note the ordering:
        # a paused narrator whose last topic gets answered elsewhere
        # completes rather than staying paused forever with nothing to
        # resume to.
        next_status = STATUS_PAUSED
    else:
        next_status = STATUS_ACTIVE

    # ── A PAUSED WALK KEEPS ITS OUTSTANDING TOPIC, 0052 ──────────────
    #
    # This read `remaining[0] if next_status == STATUS_ACTIVE else None`,
    # so a pause discarded the topic and a resume picked one again. The
    # question was unchanged throughout — the narrator was simply not
    # being asked — but the column said otherwise, and anything deriving
    # question identity from the column therefore saw two transitions
    # across a pause/resume that changed nothing the narrator can see.
    #
    # `paused` now carries the topic. Nothing renders it: `plan_turn`
    # returns IDLE for every status except `active`, which is the gate
    # that decides whether Lori asks, and it is unchanged.
    if next_status in (STATUS_ACTIVE, STATUS_PAUSED):
        next_active = remaining[0] if remaining else None
    else:
        next_active = None

    if next_status == STATUS_COMPLETED and not completed_at:
        next_completed_at: Optional[str] = now
    else:
        next_completed_at = completed_at

    # ── EPOCH: THE QUESTION CHANGED, NOT THE ROW ─────────────────────
    #
    # Increment only when the outstanding question becomes a NEW
    # question. `version` below still moves for every durable change,
    # which is the whole point of keeping them separate:
    #
    #   first activation          stored_active None -> a topic   BUMP
    #   advance A -> B            topics differ                   BUMP
    #   settled topic reopens     topics differ                   BUMP
    #   pause / resume, same A    topics equal (see above)         no
    #   evidence for another      active topic unchanged           no
    #
    # When nothing is outstanding — pending, or completed — the epoch is
    # CARRIED rather than reset, so a later reopen cannot reuse an epoch
    # that historical turn metadata still names.
    if next_active is not None and next_active != stored_active:
        presentation_epoch = stored_epoch + 1
    else:
        presentation_epoch = stored_epoch

    changed = (
        next_state != stored_state
        or next_status != stored_status
        or next_active != stored_active
        or next_completed_at != completed_at
        or presentation_epoch != stored_epoch
    )

    version = stored_version + 1 if changed else stored_version
    updated_at = now if changed else row["updated_at"]

    return ResolvedState(
        person_id=person_id,
        status=next_status,
        topic_state=next_state,
        active_topic_id=next_active,
        version=version,
        identity_complete=anchors_ok,
        created_at=row["created_at"],
        updated_at=updated_at,
        completed_at=next_completed_at,
        presentation_epoch=presentation_epoch,
    ), changed


def reconcile(con: sqlite3.Connection, person_id: str, *,
              now: str) -> Optional[ResolvedState]:
    """MATERIALIZE the resolution. No commit.

    The write half of `resolve_effective()`, which holds the rules and
    the reasoning. Behaviour is unchanged by the split: this still
    writes exactly when the effective stored state changes, and the
    version still moves only then.
    """
    resolved = resolve_effective(con, person_id, now=now)
    if resolved is None:
        return None
    state, changed = resolved
    if changed:
        con.execute(
            f"UPDATE {TABLE} SET status=?, topic_state_json=?, "  # noqa: S608
            "active_topic_id=?, version=?, presentation_epoch=?, "
            "updated_at=?, completed_at=? "
            "WHERE person_id=?;",
            (state.status, json.dumps(dict(state.topic_state)),
             state.active_topic_id, state.version, state.presentation_epoch,
             state.updated_at, state.completed_at, person_id),
        )
    return state


def apply_disposition(con: sqlite3.Connection, person_id: str, *,
                      topic_id: str, disposition: str, now: str) -> None:
    """Record `addressed` or `declined` for ONE topic. No commit.

    Writes the disposition only. Reconciliation is the caller's next
    step and is what advances the active topic and derives completion —
    which is why a client cannot declare either.
    """
    if disposition not in CLIENT_DISPOSITIONS:
        raise ValueError(
            f"disposition must be one of {CLIENT_DISPOSITIONS}; "
            f"got {disposition!r}"
        )
    if not is_known_topic(topic_id):
        raise UnknownTopic(topic_id)

    row = read_row(con, person_id)
    if row is None:
        raise NotEnrolled(person_id)

    state = _coerce_topic_state(row["topic_state_json"])
    state[topic_id] = disposition
    con.execute(
        f"UPDATE {TABLE} SET topic_state_json=?, updated_at=? "  # noqa: S608
        "WHERE person_id=?;",
        (json.dumps(state), now, person_id),
    )


def set_paused(con: sqlite3.Connection, person_id: str, *,
               paused: bool, now: str) -> None:
    """Pause or resume. No commit.

    A completed row is left alone: `completed` is terminal, and pausing
    something that is finished is not a state this system has.
    """
    row = read_row(con, person_id)
    if row is None:
        raise NotEnrolled(person_id)
    if row["status"] == STATUS_COMPLETED:
        return
    # `active` is not asserted here — reconciliation derives the real
    # status from the anchors and the remaining topics immediately after.
    target = STATUS_PAUSED if paused else STATUS_ACTIVE
    # ── THE VERSION MOVES HERE NOW, 0052 ─────────────────────────────
    #
    # A status change is a durable change and must invalidate a client's
    # in-flight write, or a PATCH authored before the pause would land
    # after it.
    #
    # It used to move by ACCIDENT. This wrote only the status, and the
    # reconcile that follows saw `next_active` go from the topic to NULL
    # (pausing) and back (resuming) — so the version moved as a side
    # effect of discarding the outstanding question. Now that the topic
    # is preserved across a pause, that side effect is gone and the bump
    # has to be stated. The EPOCH deliberately does not move: the
    # question is unchanged, which is the whole point of 0052.
    con.execute(
        f"UPDATE {TABLE} SET status=?, version=version+1, "  # noqa: S608
        "updated_at=? WHERE person_id=?;",
        (target, now, person_id),
    )


def contains_no_prose(topic_state: Mapping[str, Any]) -> bool:
    """Every key is a canonical topic and every value one of four states.

    Work order decision 8 as an executable predicate rather than a note.
    The progress row is where narrator speech would be easiest to park
    and hardest to notice, so the check is available to any caller and
    is asserted by the Phase 1 suite.
    """
    if not isinstance(topic_state, Mapping):
        return False
    for key, value in topic_state.items():
        if key not in _TOPIC_BY_ID:
            return False
        if value not in TOPIC_STATES:
            return False
    return True


__all__: Sequence[str] = (
    "UNANSWERED", "KNOWN", "ADDRESSED", "DECLINED", "TOPIC_STATES",
    "CLIENT_DISPOSITIONS", "DURABLE_DISPOSITIONS", "FINAL_STATES",
    "STATUS_PENDING", "STATUS_ACTIVE", "STATUS_PAUSED", "STATUS_COMPLETED",
    "STATUSES", "TABLE", "EVIDENCE_BIO_STATUSES",
    "TopicDefinition", "TOPIC_REGISTRY", "TOPIC_IDS", "topic", "is_known_topic",
    "ProfileSeedError", "NotEnrolled", "PersonNotFound", "UnknownTopic",
    "VersionConflict", "TopicNotActive",
    "identity_anchors_complete", "has_value", "load_snapshot",
    "topic_has_evidence", "ResolvedState", "not_enrolled_body",
    "initial_topic_state", "read_row", "is_enrolled", "person_exists",
    "enroll",
    # `resolve_effective` is DECLARED, not internal. It was extracted
    # from `reconcile()` for the REST read path, which makes it a
    # shared contract — and an extracted helper that nothing declares
    # is one refactor away from being inlined back by someone who
    # cannot see it has a second caller.
    "resolve_effective", "reconcile",
    "apply_disposition", "set_paused", "contains_no_prose",
)
