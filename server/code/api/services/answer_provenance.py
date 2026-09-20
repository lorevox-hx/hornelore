"""Where each questionnaire answer came from.

WO-03A. Migration 0059 holds the schema and the reasoning; this module is
the write and read side of it.

THE ONE RULE THIS MODULE EXISTS TO ENFORCE
------------------------------------------

    Lori must not be able to mark her own suggestions as human-confirmed
    merely by writing them into the questionnaire.  — Chris, 2026-09-20

So `origin` is NEVER taken from the request body. It is decided by WHICH
ENDPOINT the write arrived on, and the endpoints are separated precisely
so that the classification is a fact about the call rather than a claim
inside it. A client that could say "this is operator_direct" is a client
that could lie, and the one client we most need not to trust is the one
that composes text for a living.

The asymmetry that makes this workable: a caller claiming LOWER authority
is safe to believe — nothing gains by falsely calling itself a machine.
A caller claiming HIGHER authority is not. Hence a dedicated route for
the human-entry case and NO PROVENANCE AT ALL on the shared legacy PUT,
which has ~20 callers across five modules including two of Lori's own
writers. Silence is the honest record for those; `unknown` is a state,
not a gap.

THE LIMIT OF WHAT THIS ESTABLISHES
----------------------------------

`operator_direct` means THIS OPERATION WAS INVOKED — a write arrived on
the Bio Builder form's endpoint rather than the shared one. It does not
establish who invoked it. There is no operator authentication on these
routes. The separation stops Lori's writers acquiring the operator's
authority; it is not authentication, and `actor_id` is an unverified
claim recorded as given.

So the record supports "a write arrived on the human-entry route" and
not "Chris typed this". Those are different sentences, and a family
archive is where the difference matters. Any product claim about
provenance has to use the first one.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ── origins ──────────────────────────────────────────────────────────

ORIGIN_OPERATOR = "operator_direct"
ORIGIN_NARRATOR = "narrator_direct"
ORIGIN_SUGGESTED = "ai_suggested"

_ORIGINS = (ORIGIN_OPERATOR, ORIGIN_NARRATOR, ORIGIN_SUGGESTED)

# ── turn evidence ────────────────────────────────────────────────────

EVIDENCE_VERIFIED = "verified"
EVIDENCE_UNVERIFIED = "unverified"
EVIDENCE_ABSENT = "absent"

_EVIDENCE = (EVIDENCE_VERIFIED, EVIDENCE_UNVERIFIED, EVIDENCE_ABSENT)

ENTRY_ID_KEY = "_entryId"

__all__ = [
    "ORIGIN_OPERATOR", "ORIGIN_NARRATOR", "ORIGIN_SUGGESTED",
    "EVIDENCE_VERIFIED", "EVIDENCE_UNVERIFIED", "EVIDENCE_ABSENT",
    "AnswerOrigin", "identify_path", "verify_turn",
    "archive_provenance", "record_provenance", "load_provenance",
]


class AnswerOrigin:
    """What the ROUTE established about a write. Constructed by the route,
    never by parsing a request body.

    `turn_evidence` is settled before this object exists — `verify_turn`
    runs at the route boundary and its verdict is carried here. Nothing
    downstream re-decides it, because a second opinion on evidence is how
    an unverified claim becomes a verified one by accident.
    """

    __slots__ = ("origin", "actor_id", "source_turn_id", "turn_evidence",
                 "original_text", "proposed_by", "confirmed_via",
                 "confirmed_at", "sections")

    def __init__(
        self,
        origin: str,
        *,
        actor_id: str = "",
        source_turn_id: Optional[str] = None,
        turn_evidence: str = EVIDENCE_ABSENT,
        original_text: Optional[str] = None,
        proposed_by: Optional[str] = None,
        confirmed_via: Optional[str] = None,
        confirmed_at: Optional[str] = None,
        sections: Optional[Sequence[str]] = None,
    ) -> None:
        if origin not in _ORIGINS:
            raise ValueError(f"unknown origin {origin!r}")
        if turn_evidence not in _EVIDENCE:
            raise ValueError(f"unknown turn_evidence {turn_evidence!r}")
        # Mirrors the CHECK in 0059. Enforced here too so the failure lands
        # at the caller that made the mistake rather than as an opaque
        # IntegrityError halfway through someone's save.
        if turn_evidence != EVIDENCE_ABSENT and origin != ORIGIN_NARRATOR:
            raise ValueError(
                "turn evidence belongs only to a narrator statement; "
                f"{origin!r} cannot cite a chat turn"
            )
        self.origin = origin
        self.actor_id = actor_id or ""
        self.source_turn_id = source_turn_id
        self.turn_evidence = turn_evidence
        self.original_text = original_text
        self.proposed_by = proposed_by
        self.confirmed_via = confirmed_via
        self.confirmed_at = confirmed_at
        # WHICH SECTIONS THIS WRITE IS ENTITLED TO CLASSIFY.
        #
        # The Bio Builder form saves one section and sends the whole
        # document. A path that changed OUTSIDE the declared section
        # changed for some other reason inside the same PUT — a draft
        # mirror, a prefill, an identity sync — and stamping it with the
        # operator's authority would attribute to a person something they
        # did not do. None means "no restriction", used only by callers
        # that genuinely own every path they send.
        self.sections = None if sections is None else [str(s) for s in sections]

    def covers(self, section: str) -> bool:
        return self.sections is None or section in self.sections


# ── path → (section, entry_id, field) ────────────────────────────────


def identify_path(doc: Mapping[str, Any], path: str) -> Optional[Tuple[str, str, str]]:
    """Resolve a flattened path against the document it came from.

        parents[0].occupation   -> ('parents', 'e_k3x9q7', 'occupation')
        basics.firstName        -> ('basics', '',          'firstName')

    Returns None for anything that must not be classified:

      * a bookkeeping field (`_entryId` itself, and anything `_`-prefixed).
        Recording that an operator "entered" an identifier the code minted
        would be the system attributing its own bookkeeping to a person.
      * an indexed entry with no `_entryId`. Positional identity is exactly
        what WO-02 removed; falling back to the ordinal here would quietly
        reintroduce it in the one table whose whole purpose is to survive a
        reorder. A pre-WO-02 entry gains an id on the next save and becomes
        classifiable then.
      * a bare top-level scalar with no field part.
    """
    from .questionnaire_persistence import _split, _get

    try:
        parts = _split(path)
    except ValueError:
        return None
    if len(parts) < 2 or not isinstance(parts[0], str):
        return None

    section = parts[0]
    rest = parts[1:]

    if isinstance(rest[0], int):
        if len(rest) < 2:
            return None
        entry = _get(doc, [section, rest[0]])
        if not isinstance(entry, Mapping):
            return None
        entry_id = str(entry.get(ENTRY_ID_KEY) or "")
        if not entry_id:
            return None
        field_parts = rest[1:]
    else:
        entry_id = ""
        field_parts = rest

    if not field_parts:
        return None
    # A nested path below an entry keeps its remainder as the field name,
    # so `spouse[0].children[2]` is one identifiable answer rather than
    # three unrelated ones. Indexes stringify; the entry id above is what
    # carries identity.
    field = ".".join(str(p) for p in field_parts)
    if any(str(p).startswith("_") for p in field_parts):
        return None
    return (section, entry_id, field)


# ── turn verification ────────────────────────────────────────────────


def verify_turn(con: sqlite3.Connection, person_id: str,
                turn_id: Optional[str]) -> str:
    """Did this narrator actually say this, in this turn?

    Returns one of the three evidence states. NEVER raises for a turn that
    does not check out — a bookkeeping failure must not discard what the
    narrator said. The caller stores the answer either way and stores this
    verdict alongside it.

    Three conditions, all required:

      1. the turn exists and its session resolves to THIS narrator.
         `sessions.person_id` (0045) is write-once: a NULL incoming id
         cannot clear an owner and a different one raises
         SessionOwnerConflict rather than overwriting, so where it exists
         it can be trusted.

      2. role = 'user'. An assistant turn is Lori talking.

      3. NOT a system directive. This is the clause that is easy to omit
         and expensive to omit. Composed guidance travels in the user
         message slot — measured live, row 2634 on a real narrator's
         session is `[SYSTEM: The narrator has been quiet...]` carrying
         meta_json.origin='system_directive'. Without this clause the
         prompt composer's own stage directions would be citable as
         narrator testimony.

    Known and accepted: the directive flag landed 2026-08-09, and
    `db.py:2331` measured 120 of 794 user rows as unflagged directives
    before it. Historical turns mostly fail condition 1 anyway — 1,468 of
    1,487 have no resolvable owner — so an old citation returns
    'unverified'. That is the intended answer, not a gap to widen.
    """
    tid = (turn_id or "").strip()
    if not tid:
        return EVIDENCE_ABSENT
    try:
        row = con.execute(
            "SELECT 1 FROM turns t "
            "JOIN sessions s ON s.conv_id = t.conv_id "
            "WHERE t.id = ? AND s.person_id = ? AND t.role = 'user' "
            "  AND COALESCE(json_extract(t.meta_json, '$.origin'), '') "
            "      <> 'system_directive'",
            (tid, person_id),
        ).fetchone()
    except sqlite3.Error:
        # A verification that could not run is not a verification that
        # passed. Same reasoning as the concurrency check: unprovable is
        # not the same as safe.
        return EVIDENCE_UNVERIFIED
    return EVIDENCE_VERIFIED if row else EVIDENCE_UNVERIFIED


# ── read / archive / write ───────────────────────────────────────────


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "origin": row["origin"],
        "origin_at": row["origin_at"],
        "actor_id": row["actor_id"],
        "source_turn_id": row["source_turn_id"],
        "turn_evidence": row["turn_evidence"],
        "original_text": row["original_text"],
        "proposed_by": row["proposed_by"],
        "confirmed_via": row["confirmed_via"],
        "confirmed_at": row["confirmed_at"],
        "revision": int(row["revision"] or 0),
    }


def archive_provenance(
    con: sqlite3.Connection,
    person_id: str,
    keys: Sequence[Tuple[str, str, str]],
) -> Dict[str, Any]:
    """Read the provenance rows a write is about to supersede.

    Returned keyed by 'section|entry_id|field' so it can sit next to
    `previous_values` in the 0058 revision row and describe the same
    moment: what the value was, and where it came from. Read inside the
    caller's transaction, before the replace.
    """
    out: Dict[str, Any] = {}
    for section, entry_id, field in keys:
        row = con.execute(
            "SELECT * FROM bio_builder_answer_provenance "
            "WHERE person_id=? AND section=? AND entry_id=? AND field=?",
            (person_id, section, entry_id, field),
        ).fetchone()
        if row is not None:
            out[f"{section}|{entry_id}|{field}"] = _row_to_dict(row)
    return out


def record_provenance(
    con: sqlite3.Connection,
    person_id: str,
    document: Mapping[str, Any],
    changed_paths: Sequence[str],
    origin: AnswerOrigin,
    *,
    now: str,
    revision: int,
) -> Tuple[List[Tuple[str, str, str]], Dict[str, Any]]:
    """Stamp provenance for the paths a write actually changed.

    Called from inside `_write`'s BEGIN IMMEDIATE, after the archive and
    before the answer is written, so the two commit together or not at
    all. Provenance that can outlive the value it describes is worse than
    no provenance: it becomes a confident statement about something that
    is not there.

    `changed_paths` is the writer's own diff — paths whose stored value
    actually moved. A no-op never reaches here, which is why an unchanged
    save does not restamp an answer as freshly entered.

    Returns (keys, superseded) so the caller can archive what was replaced.
    """
    keys: List[Tuple[str, str, str]] = []
    for path in changed_paths:
        ident = identify_path(document, path)
        if ident is None:
            continue
        if not origin.covers(ident[0]):
            continue
        keys.append(ident)

    if not keys:
        return ([], {})

    superseded = archive_provenance(con, person_id, keys)

    for section, entry_id, field in keys:
        prior = superseded.get(f"{section}|{entry_id}|{field}")
        # AN ACCEPTED SUGGESTION STAYS AN ACCEPTED SUGGESTION.
        #
        # When a person enters a value over one Lori proposed, `origin`
        # does NOT silently become operator_direct — the record keeps
        # `ai_suggested` and gains the confirmation, because "Lori
        # proposed it and a person agreed" is a different and weaker
        # fact than "a person said it". Rewriting it would launder the
        # first into the second, and after two rounds nothing remembers
        # which it was.
        #
        # This applies only when the person is confirming the SAME value.
        # Typing something different is a correction, not an acceptance,
        # and a correction is theirs.
        confirming = (
            prior is not None
            and prior.get("origin") == ORIGIN_SUGGESTED
            and origin.origin in (ORIGIN_OPERATOR, ORIGIN_NARRATOR)
            and _same_value(document, section, entry_id, field, prior)
        )
        if confirming:
            con.execute(
                "UPDATE bio_builder_answer_provenance "
                "SET confirmed_via=?, confirmed_at=?, revision=? "
                "WHERE person_id=? AND section=? AND entry_id=? AND field=?",
                ("acceptance", now, int(revision),
                 person_id, section, entry_id, field),
            )
            continue
        con.execute(
            "INSERT INTO bio_builder_answer_provenance "
            "(person_id, section, entry_id, field, origin, origin_at, "
            " actor_id, source_turn_id, turn_evidence, original_text, "
            " proposed_by, confirmed_via, confirmed_at, revision) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(person_id, section, entry_id, field) DO UPDATE SET "
            "  origin=excluded.origin, origin_at=excluded.origin_at, "
            "  actor_id=excluded.actor_id, "
            "  source_turn_id=excluded.source_turn_id, "
            "  turn_evidence=excluded.turn_evidence, "
            "  original_text=excluded.original_text, "
            "  proposed_by=excluded.proposed_by, "
            "  confirmed_via=excluded.confirmed_via, "
            "  confirmed_at=excluded.confirmed_at, "
            "  revision=excluded.revision",
            (person_id, section, entry_id, field, origin.origin, now,
             origin.actor_id, origin.source_turn_id, origin.turn_evidence,
             origin.original_text, origin.proposed_by, origin.confirmed_via,
             origin.confirmed_at, int(revision)),
        )

    return (keys, superseded)


def _same_value(document: Mapping[str, Any], section: str, entry_id: str,
                field: str, prior: Mapping[str, Any]) -> bool:
    """Is the incoming value the one that was proposed?

    Conservative on purpose. `original_text` is only populated for a
    narrator statement, so for most suggestions there is nothing recorded
    to compare against — and in that case this returns False, which
    classifies the write as a fresh entry rather than as an acceptance.

    That is the safe direction. Calling a correction an acceptance would
    leave `origin='ai_suggested'` on a value a person actually typed,
    understating the person; calling an acceptance a fresh entry
    overstates nothing — it records a person as having entered a value
    they did in fact enter. The explicit accept operation in WO-03B is
    where acceptance becomes exact.
    """
    recorded = prior.get("original_text")
    if recorded is None:
        return False
    from .questionnaire_persistence import _get
    if entry_id:
        entries = document.get(section)
        if not isinstance(entries, list):
            return False
        for entry in entries:
            if isinstance(entry, Mapping) and entry.get(ENTRY_ID_KEY) == entry_id:
                return _get(entry, field.split(".")) == recorded
        return False
    return _get(document, [section] + field.split(".")) == recorded


def load_provenance(person_id: str) -> Dict[str, Dict[str, Any]]:
    """Every provenance row for a narrator, keyed 'section|entry_id|field'.

    Read-only, its own connection, safe to call from a read path. Returns
    {} for a narrator with no rows — which is every narrator whose answers
    predate this table, and is the truthful answer for them.
    """
    from .. import db as _db
    con = _db._connect()
    try:
        rows = con.execute(
            "SELECT * FROM bio_builder_answer_provenance WHERE person_id=?",
            (person_id,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return {
        f"{r['section']}|{r['entry_id']}|{r['field']}": _row_to_dict(r)
        for r in rows
    }
