"""Import repository -- the only sanctioned write path into the import
landing zone (`import_batch` / `import_candidate`, migration 0037).

WO-TRAVEL-DOC-IMPORT-PROVENANCE-FOUNDATION-01 Phase 3 (2026-07-26).

Migration 0037 built the landing zone and stated four rules in its
header. A schema can only enforce some of them. `CHECK` constraints and
`REFERENCES` clauses cannot express "a candidate may not be attached to
a photo that belongs to a different person", and the *absence* of a
`narrator_ready` column stops nobody from writing approval semantics
into `state_reason` instead. This module is where the rules that need a
procedure rather than a constraint actually get enforced, and it is the
reason the API layer never touches these two tables directly.

The four rules, and how each one is held here:

  1. INTAKE IS NOT APPROVAL.
     Creating a candidate does not mean narrator-ready, does not mean
     memoir inclusion, and does not mean an operator has seen it.
     `candidate_create()` writes `state='pending'` and nothing else --
     there is no parameter that could set an approval field, and
     `_assert_intake_not_approval()` re-checks at runtime that the table
     has not grown a `narrator_ready` or `include_in_memoir` column
     behind the migration lock. Promotion to a photo is a separate,
     explicit `candidate_decide(..., state='accepted', photo_id=...)`
     call that requires a photos row the caller already materialized.
     This module never creates a photos row and never sets an approval
     flag on one.

  2. CANDIDATES CANNOT CROSS THE PERSON/TRIP BOUNDARY.
     `import_candidate.person_id` is denormalized from the batch on
     purpose, so `candidate_create()` does not accept a person_id at all
     -- it copies the batch's. Every other place where a foreign row
     could smuggle in a different person is checked and refused:
     binding a trip to a batch, giving a candidate a trip, and accepting
     a candidate onto a photo. See CrossPersonError / CrossTripError.

  3. NO RAW EXTERNAL TOKENS.
     `external_ref` and `external_id` are opaque provider handles. Every
     caller-supplied string that lands in a row is scanned for the
     shapes a replayable credential actually takes (OAuth access and
     refresh tokens, bearer headers, JWTs, credential-bearing query
     strings), and every key of `match_reason` is checked against a
     secret-ish name list. A hit raises ExternalTokenError before any
     write connection opens. This is a guard against accident, not an
     adversary; the real rule is that credentials live in the process
     environment.

  4. REVERSIBLE, NOT DESTRUCTIVE.
     There is no DELETE in this file. Retiring a batch or a candidate is
     `*_hide()`, a stamp that `*_unhide()` clears with the match reasons
     and review history intact. Rows leave only by FK cascade when their
     person is hard-deleted.

Plus one thing the schema explicitly delegated: `match_reason_json` is
JSON so the Evidence Review Queue can display the importer's reasoning
unchanged. `candidate_create()` takes a dict and `candidate_get()` hands
back an equal dict -- round-trip, never a summary, never prose.

Design rules, same posture as `trip_repository.py`:
- Pure stdlib (sqlite3 + json + re + uuid + datetime). No import of the
  extract / prompt_composer / chat_ws / llm layers.
- Connects through `api.db.DB_PATH` resolved AT CALL TIME so unit tests
  can patch `db.DB_PATH` to a temp file.
- All writes commit-or-rollback per call; no long-lived connections.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------- enums
#
# Single source of truth for the CHECK enums in migration 0037. The
# repository validates against these so an off-enum value is refused
# cleanly instead of surfacing as an unhandled 500 when SQLite raises
# IntegrityError on insert.

IMPORT_SOURCES = (
    "google_photos_picker",
    "google_takeout",
    "local_upload",
    "csv",
    "manual",
)

BATCH_STATUSES = ("open", "closed", "failed")

CANDIDATE_STATES = ("pending", "accepted", "rejected", "duplicate", "error")

TAKEN_AT_SOURCES = (
    "exif", "provider_metadata", "filename_guess", "operator", "unknown",
)

CANDIDATE_LOCATION_SOURCES = (
    "exif_gps", "provider_metadata", "typed_address", "operator", "unknown",
)

# The states a candidate can be moved to by an operator decision.
# 'pending' is not among them: a decision is a decision, and un-deciding
# is not a write this module offers.
DECIDABLE_STATES = ("accepted", "rejected", "duplicate", "error")

# The batch sources a candidate can be promoted from. Promotion needs
# the image bytes, and `local_upload` / `manual` are the two sources
# where the operator is the one holding them. The provider-side sources
# are deliberately absent: `google_photos_picker` and `google_takeout`
# each have to fetch their own bytes through their own lane first, and
# `csv` is a manifest of claims about files nobody has handed us. Adding
# a source here without also building its fetch would turn promotion
# into a way to mint photo rows for images that do not exist.
PROMOTABLE_SOURCES = ("local_upload", "manual")


# Columns that must never exist on import_candidate. If one appears, the
# migration lock in tests/test_import_provenance_foundation_migration.py
# has been argued away and this module refuses to write rather than
# quietly participating in approval-by-intake.
FORBIDDEN_CANDIDATE_COLUMNS = ("narrator_ready", "include_in_memoir")


# ---------------------------------------------------------------- errors


class ImportRepositoryError(Exception):
    """Base for every refusal this module makes."""


class BatchNotFoundError(ImportRepositoryError):
    pass


class CandidateNotFoundError(ImportRepositoryError):
    pass


class CrossPersonError(ImportRepositoryError):
    """A write would have attached rows belonging to two different people."""


class CrossTripError(ImportRepositoryError):
    """A write would have attached a candidate to a trip its batch does
    not own, or to a trip belonging to another person."""


class ExternalTokenError(ImportRepositoryError):
    """A caller-supplied value looks like a replayable credential."""


class IntakeIsNotApprovalError(ImportRepositoryError):
    """The intake table has grown an approval column, or a caller tried
    to express approval through the intake layer."""


class InvalidStateError(ImportRepositoryError):
    """An off-enum value, or a decision that does not match its payload."""


class PhotoBytesMissingError(ImportRepositoryError):
    """Promotion was asked for and there is nothing to promote.

    `photos.image_path` is NOT NULL and `photos.file_hash` is NOT NULL
    UNIQUE. An import_candidate carries a filename, a size, a mime type
    and possibly a hash -- it does NOT carry the image. So promotion has
    exactly two honest ways to end up with a photos row: the operator
    hands over the file, or the same bytes are already in the archive
    under this person and we point at them. When neither is true this is
    the refusal. It is emphatically not an invitation to write a
    plausible-looking image_path: a photos row whose path resolves to
    nothing would flow straight into Lori's photo grounding as a real
    picture, and there is no later check that would catch it."""


class BatchClosedError(ImportRepositoryError):
    """New candidates cannot land in a batch that is closed or failed."""


# ---------------------------------------------------------------- plumbing


def _connect() -> sqlite3.Connection:
    from .. import db as _db  # late import so tests can patch DB_PATH
    con = sqlite3.connect(str(_db.DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA busy_timeout = 5000;")
    return con


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Row -> plain dict, with match_reason_json parsed back to the object
    the caller handed in. A stored value that will not parse is surfaced
    as an empty dict rather than raising: a malformed reason must not
    make an already-landed candidate unreadable in the review queue."""
    if row is None:
        return None
    d = dict(row)
    if "match_reason_json" in d:
        raw = d.get("match_reason_json")
        if isinstance(raw, str):
            try:
                d["match_reason"] = json.loads(raw)
            except Exception:
                d["match_reason"] = {}
        else:
            d["match_reason"] = {}
    return d


# ---------------------------------------------------------------- rule 3
#
# Token shapes. Each pattern is a credential format that has actually
# been pasted into a field somebody thought was opaque:
#
#   ya29.*            Google OAuth2 access token
#   1//*              Google OAuth2 refresh token
#   ghp_ / gho_ ...   GitHub tokens
#   eyJ....           JWT (three base64url segments)
#   Bearer <x>        an Authorization header, pasted whole
#   ?access_token=    a URL with the credential in the query string
#
# The list is deliberately narrow. A broad "looks random" heuristic
# would reject legitimate opaque provider ids, which is the exact thing
# external_ref exists to hold.

_TOKEN_PATTERNS = (
    re.compile(r"\bya29\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?:^|\s)1//[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]{16,}"),
    re.compile(r"(?i)\b(?:access|refresh|id)_token\s*[=:]"),
    re.compile(r"(?i)\bauthorization\s*:\s*\S"),
    re.compile(r"(?i)[?&](?:access_token|refresh_token|api_key|apikey|"
               r"client_secret|password|auth)="),
)

# Key names that must not appear anywhere in a match_reason object.
_SECRET_KEY_HINTS = (
    "token", "secret", "password", "passwd", "authorization", "auth",
    "credential", "cookie", "api_key", "apikey", "private_key",
    "session_id", "bearer",
)


def _assert_no_secret(value: Any, field: str) -> None:
    """Refuse a caller-supplied string that carries a replayable
    credential. Raises ExternalTokenError before any connection opens."""
    if not isinstance(value, str) or not value:
        return
    for pat in _TOKEN_PATTERNS:
        if pat.search(value):
            raise ExternalTokenError(
                "%s looks like a replayable credential (matched %s). "
                "external_ref / external_id hold opaque provider handles "
                "only; tokens belong in the process environment, never in "
                "the database." % (field, pat.pattern)
            )


def _assert_reason_clean(obj: Any, field: str, _depth: int = 0) -> None:
    """Walk a match_reason object and refuse secret-ish keys or token-ish
    values at any depth. Depth is bounded so a cyclic or absurdly nested
    structure cannot spin here."""
    if _depth > 12:
        raise ExternalTokenError(
            "%s is nested deeper than 12 levels; match reasons are a flat "
            "record of why the importer matched, not a payload dump."
            % field
        )
    if isinstance(obj, dict):
        for key, val in obj.items():
            if not isinstance(key, str):
                raise InvalidStateError(
                    "%s keys must be strings (got %r)" % (field, type(key))
                )
            low = key.lower()
            for hint in _SECRET_KEY_HINTS:
                if hint in low:
                    raise ExternalTokenError(
                        "%s carries a key named %r, which reads as a "
                        "credential. Match reasons explain the match; they "
                        "do not carry authentication material."
                        % (field, key)
                    )
            _assert_reason_clean(val, "%s.%s" % (field, key), _depth + 1)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_reason_clean(item, "%s[]" % field, _depth + 1)
    else:
        _assert_no_secret(obj, field)


# ---------------------------------------------------------------- rule 1


def _assert_intake_not_approval(con: sqlite3.Connection) -> None:
    """Runtime re-check that import_candidate still has no approval
    columns. The migration test locks this at build time; this catches a
    live database that drifted (an ALTER run by hand, a restored older
    file) before anything lands in it."""
    try:
        cols = {r["name"] for r in
                con.execute("PRAGMA table_info(import_candidate)").fetchall()}
    except sqlite3.OperationalError as exc:
        raise ImportRepositoryError(
            "import_candidate is missing; migration 0037 has not been "
            "applied to this database (%s)" % exc
        )
    if not cols:
        raise ImportRepositoryError(
            "import_candidate is missing; migration 0037 has not been "
            "applied to this database"
        )
    found = sorted(cols & set(FORBIDDEN_CANDIDATE_COLUMNS))
    if found:
        raise IntakeIsNotApprovalError(
            "import_candidate has grown approval column(s) %s. Intake is "
            "not approval: a candidate is not a photo and cannot be "
            "narrator-ready or in the memoir. Refusing to write."
            % ", ".join(found)
        )


# ---------------------------------------------------------------- rule 2


def _batch_row(con: sqlite3.Connection, batch_id: str) -> sqlite3.Row:
    row = con.execute(
        "SELECT * FROM import_batch WHERE id = ?", (batch_id,)
    ).fetchone()
    if row is None:
        raise BatchNotFoundError("no import_batch with id %r" % batch_id)
    return row


def _candidate_row(con: sqlite3.Connection, candidate_id: str) -> sqlite3.Row:
    row = con.execute(
        "SELECT * FROM import_candidate WHERE id = ?", (candidate_id,)
    ).fetchone()
    if row is None:
        raise CandidateNotFoundError(
            "no import_candidate with id %r" % candidate_id
        )
    return row


def _assert_trip_owned_by(con: sqlite3.Connection, trip_id: str,
                          person_id: str) -> None:
    row = con.execute(
        "SELECT person_id FROM trips WHERE id = ?", (trip_id,)
    ).fetchone()
    if row is None:
        raise CrossTripError("no trip with id %r" % trip_id)
    if row["person_id"] != person_id:
        raise CrossTripError(
            "trip %s belongs to person %s, not %s -- an import cannot "
            "reach across people" % (trip_id, row["person_id"], person_id)
        )


def _assert_photo_owned_by(con: sqlite3.Connection, photo_id: str,
                           person_id: str) -> None:
    row = con.execute(
        "SELECT narrator_id FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    if row is None:
        raise CrossPersonError("no photo with id %r" % photo_id)
    if row["narrator_id"] != person_id:
        raise CrossPersonError(
            "photo %s belongs to narrator %s, not %s -- accepting a "
            "candidate onto another person's photo is the exact confusion "
            "migration 0037 was written to end"
            % (photo_id, row["narrator_id"], person_id)
        )


def _assert_person_exists(con: sqlite3.Connection, person_id: str) -> None:
    row = con.execute(
        "SELECT 1 FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if row is None:
        raise CrossPersonError("no person with id %r" % person_id)


# ---------------------------------------------------------------- counters


def _refresh_batch_counters(con: sqlite3.Connection, batch_id: str) -> None:
    """Recompute the denormalized counters from the candidate rows.

    Recomputed, never incremented. The migration header calls these a
    display convenience and not the source of truth; an increment would
    quietly make them the source of truth the first time a decision was
    replayed. Hidden candidates still count -- hiding is retirement from
    a view, not a claim the import never happened."""
    row = con.execute(
        """SELECT
               COUNT(*) AS total,
               SUM(CASE WHEN state = 'accepted' THEN 1 ELSE 0 END) AS acc,
               SUM(CASE WHEN state IN ('rejected', 'duplicate')
                        THEN 1 ELSE 0 END) AS rej
           FROM import_candidate WHERE batch_id = ?""",
        (batch_id,),
    ).fetchone()
    con.execute(
        "UPDATE import_batch SET candidate_count = ?, accepted_count = ?, "
        "rejected_count = ?, updated_at = ? WHERE id = ?",
        (row["total"] or 0, row["acc"] or 0, row["rej"] or 0,
         _now(), batch_id),
    )


# ---------------------------------------------------------------- batches


def batch_create(
    person_id: str,
    source: str,
    trip_id: Optional[str] = None,
    external_ref: Optional[str] = None,
    label: Optional[str] = None,
    notes: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> str:
    """Open a batch for one person. `trip_id` is optional because intake
    can happen before the operator has decided which trip the material
    belongs to; `batch_bind_trip()` sets it later."""
    if source not in IMPORT_SOURCES:
        raise InvalidStateError(
            "unknown import source %r; known sources are %s"
            % (source, ", ".join(IMPORT_SOURCES))
        )
    for field, val in (("external_ref", external_ref), ("label", label),
                       ("notes", notes)):
        _assert_no_secret(val, field)

    bid = batch_id or _new_id()
    con = _connect()
    try:
        _assert_intake_not_approval(con)
        _assert_person_exists(con, person_id)
        if trip_id:
            _assert_trip_owned_by(con, trip_id, person_id)
        con.execute(
            """INSERT INTO import_batch
                   (id, person_id, trip_id, source, external_ref, label,
                    notes, status, created_by_user_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)""",
            (bid, person_id, trip_id, source, external_ref, label, notes,
             created_by_user_id, _now(), _now()),
        )
        con.commit()
        return bid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def batch_get(batch_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        return _row_to_dict(
            con.execute("SELECT * FROM import_batch WHERE id = ?",
                        (batch_id,)).fetchone()
        )
    finally:
        con.close()


def batch_list(person_id: Optional[str] = None,
               status: Optional[str] = None,
               include_hidden: bool = False) -> List[Dict[str, Any]]:
    if status is not None and status not in BATCH_STATUSES:
        raise InvalidStateError("unknown batch status %r" % status)
    where: List[str] = []
    args: List[Any] = []
    if person_id:
        where.append("person_id = ?"); args.append(person_id)
    if status:
        where.append("status = ?"); args.append(status)
    if not include_hidden:
        where.append("hidden = 0")
    sql = "SELECT * FROM import_batch"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # rowid, not id, as the tiebreaker. created_at has whole-second
    # precision, so a batch opened in the same second as another would
    # otherwise sort by uuid -- which is to say, at random. rowid is
    # insertion order, which is what "newest first" actually means.
    sql += " ORDER BY created_at DESC, rowid DESC"
    con = _connect()
    try:
        return [_row_to_dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def batch_bind_trip(batch_id: str, trip_id: Optional[str]) -> bool:
    """Bind (or, with None, unbind) the batch's trip.

    Rule 2 lives here: the trip must belong to the batch's person. Note
    that unbinding does not retroactively clear the trip on candidates
    that already have one -- those were separate operator decisions and
    are theirs to change."""
    con = _connect()
    try:
        batch = _batch_row(con, batch_id)
        if trip_id:
            _assert_trip_owned_by(con, trip_id, batch["person_id"])
        cur = con.execute(
            "UPDATE import_batch SET trip_id = ?, updated_at = ? WHERE id = ?",
            (trip_id, _now(), batch_id),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def batch_close(batch_id: str, failed: bool = False,
                failure_reason: Optional[str] = None) -> bool:
    """Stop accepting candidates. `failed=True` records that the fetch
    itself broke; the candidates that did land stay exactly where they
    are, because a partial import is evidence too."""
    _assert_no_secret(failure_reason, "failure_reason")
    status = "failed" if failed else "closed"
    con = _connect()
    try:
        _batch_row(con, batch_id)
        cur = con.execute(
            "UPDATE import_batch SET status = ?, failure_reason = ?, "
            "closed_at = ?, updated_at = ? WHERE id = ?",
            (status, failure_reason, _now(), _now(), batch_id),
        )
        _refresh_batch_counters(con, batch_id)
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def batch_reopen(batch_id: str) -> bool:
    """Return a closed or failed batch to 'open' so a retry can land its
    remaining items. Clears failure_reason and closed_at; leaves every
    candidate untouched."""
    con = _connect()
    try:
        _batch_row(con, batch_id)
        cur = con.execute(
            "UPDATE import_batch SET status = 'open', failure_reason = NULL, "
            "closed_at = NULL, updated_at = ? WHERE id = ?",
            (_now(), batch_id),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def batch_hide(batch_id: str, hidden: bool = True) -> bool:
    """Retire (or restore) a batch. Rule 4: a stamp, not a DELETE. The
    candidates keep their match reasons and review history, and clearing
    the flag brings the whole batch back."""
    con = _connect()
    try:
        _batch_row(con, batch_id)
        cur = con.execute(
            "UPDATE import_batch SET hidden = ?, hidden_at = ?, "
            "updated_at = ? WHERE id = ?",
            (1 if hidden else 0, _now() if hidden else None, _now(), batch_id),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------- candidates


def candidate_create(
    batch_id: str,
    external_id: Optional[str] = None,
    file_hash: Optional[str] = None,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    byte_size: Optional[int] = None,
    taken_at: Optional[str] = None,
    taken_at_source: str = "unknown",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_source: str = "unknown",
    match_reason: Optional[Dict[str, Any]] = None,
    match_confidence: Optional[float] = None,
    trip_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
) -> str:
    """Land one incoming item.

    Note what this signature does NOT have. There is no person_id: it is
    copied from the batch, so a candidate cannot be filed under a person
    its batch does not belong to (rule 2, made structural rather than
    checked). There is no state: every candidate is born 'pending', and
    there is no parameter anywhere here that could express narrator
    readiness or memoir inclusion (rule 1).

    Idempotent on (batch_id, external_id), matching the UNIQUE index the
    migration created for exactly this: re-running the same fetch returns
    the existing candidate id instead of raising or duplicating. A
    candidate with no external_id is always a new row, because there is
    nothing to be idempotent about.
    """
    if taken_at_source not in TAKEN_AT_SOURCES:
        raise InvalidStateError(
            "unknown taken_at_source %r; known values are %s"
            % (taken_at_source, ", ".join(TAKEN_AT_SOURCES))
        )
    if location_source not in CANDIDATE_LOCATION_SOURCES:
        raise InvalidStateError(
            "unknown location_source %r; known values are %s"
            % (location_source, ", ".join(CANDIDATE_LOCATION_SOURCES))
        )
    if match_reason is not None and not isinstance(match_reason, dict):
        raise InvalidStateError(
            "match_reason must be a dict (got %r); it round-trips to the "
            "review queue as an object, not prose" % type(match_reason)
        )
    for field, val in (("external_id", external_id), ("filename", filename),
                       ("file_hash", file_hash), ("mime_type", mime_type)):
        _assert_no_secret(val, field)
    _assert_reason_clean(match_reason or {}, "match_reason")
    reason_json = json.dumps(match_reason or {}, ensure_ascii=False,
                             sort_keys=True)

    con = _connect()
    try:
        _assert_intake_not_approval(con)
        batch = _batch_row(con, batch_id)
        if batch["status"] != "open":
            raise BatchClosedError(
                "import_batch %s is %s; reopen it before landing more "
                "candidates" % (batch_id, batch["status"])
            )
        person_id = batch["person_id"]

        if external_id:
            existing = con.execute(
                "SELECT id FROM import_candidate WHERE batch_id = ? "
                "AND external_id = ?", (batch_id, external_id),
            ).fetchone()
            if existing is not None:
                return existing["id"]

        if trip_id:
            _assert_trip_owned_by(con, trip_id, person_id)
            if batch["trip_id"] and batch["trip_id"] != trip_id:
                raise CrossTripError(
                    "batch %s is bound to trip %s; a candidate in it cannot "
                    "claim trip %s. Rebind the batch or open a new one."
                    % (batch_id, batch["trip_id"], trip_id)
                )
        effective_trip = trip_id or batch["trip_id"]

        cid = candidate_id or _new_id()
        con.execute(
            """INSERT INTO import_candidate
                   (id, batch_id, person_id, trip_id, photo_id, external_id,
                    file_hash, filename, mime_type, byte_size, taken_at,
                    taken_at_source, latitude, longitude, location_source,
                    match_reason_json, match_confidence, state,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       'pending', ?, ?)""",
            (cid, batch_id, person_id, effective_trip, external_id,
             file_hash, filename, mime_type, byte_size, taken_at,
             taken_at_source, latitude, longitude, location_source,
             reason_json, match_confidence, _now(), _now()),
        )
        _refresh_batch_counters(con, batch_id)
        con.commit()
        return cid
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def candidate_get(candidate_id: str) -> Optional[Dict[str, Any]]:
    """Read one candidate. `match_reason` comes back as the object that
    went in; `match_reason_json` is left on the dict as the stored form."""
    con = _connect()
    try:
        return _row_to_dict(
            con.execute("SELECT * FROM import_candidate WHERE id = ?",
                        (candidate_id,)).fetchone()
        )
    finally:
        con.close()


def candidates_list(
    batch_id: Optional[str] = None,
    person_id: Optional[str] = None,
    trip_id: Optional[str] = None,
    state: Optional[str] = None,
    include_hidden: bool = False,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """The Evidence Review Queue's read. Ordered oldest-first because a
    review queue is a queue."""
    if state is not None and state not in CANDIDATE_STATES:
        raise InvalidStateError(
            "unknown candidate state %r; known states are %s"
            % (state, ", ".join(CANDIDATE_STATES))
        )
    where: List[str] = []
    args: List[Any] = []
    if batch_id:
        where.append("batch_id = ?"); args.append(batch_id)
    if person_id:
        where.append("person_id = ?"); args.append(person_id)
    if trip_id:
        where.append("trip_id = ?"); args.append(trip_id)
    if state:
        where.append("state = ?"); args.append(state)
    if not include_hidden:
        where.append("hidden = 0")
    sql = "SELECT * FROM import_candidate"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # See batch_list: rowid is insertion order, uuid is not. A real
    # import lands hundreds of candidates inside one second, and a
    # review queue that shuffles them is not a queue.
    sql += " ORDER BY created_at ASC, rowid ASC"
    if limit is not None:
        if not isinstance(limit, int) or limit < 0:
            raise InvalidStateError("limit must be a non-negative int")
        sql += " LIMIT ?"; args.append(limit)
    con = _connect()
    try:
        return [_row_to_dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def candidate_set_trip(candidate_id: str, trip_id: Optional[str]) -> bool:
    """Operator files a pending candidate under a trip (or unfiles it).

    Refuses a trip belonging to another person, and refuses to disagree
    with a batch that is already bound to a different trip."""
    con = _connect()
    try:
        cand = _candidate_row(con, candidate_id)
        if trip_id:
            _assert_trip_owned_by(con, trip_id, cand["person_id"])
            batch = _batch_row(con, cand["batch_id"])
            if batch["trip_id"] and batch["trip_id"] != trip_id:
                raise CrossTripError(
                    "candidate %s is in a batch bound to trip %s; it cannot "
                    "claim trip %s" % (candidate_id, batch["trip_id"], trip_id)
                )
        cur = con.execute(
            "UPDATE import_candidate SET trip_id = ?, updated_at = ? "
            "WHERE id = ?", (trip_id, _now(), candidate_id),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def candidate_decide(
    candidate_id: str,
    state: str,
    reason: Optional[str] = None,
    reviewed_by_user_id: Optional[str] = None,
    photo_id: Optional[str] = None,
) -> bool:
    """Record an operator decision about one candidate.

    This is the whole of rule 1 in one function, so read it as the rule
    and not as CRUD:

      * 'accepted' REQUIRES a photo_id, and that photos row must already
        exist and must belong to the candidate's person. Acceptance is
        the record that a photo was materialized -- this module does not
        materialize it, does not set narrator_ready on it, and does not
        put it in a memoir. Those are later, separate, explicit operator
        acts on the photo itself.
      * every other decision REFUSES a photo_id, because a rejected or
        duplicate candidate has no photo to point at.
      * 'pending' is not decidable. Undeciding is not a write offered
        here; the review history is the point of the table.
    """
    if state not in DECIDABLE_STATES:
        raise InvalidStateError(
            "%r is not a decision; decidable states are %s"
            % (state, ", ".join(DECIDABLE_STATES))
        )
    _assert_no_secret(reason, "state_reason")
    if state == "accepted" and not photo_id:
        raise IntakeIsNotApprovalError(
            "accepting a candidate requires the photo_id of the photos row "
            "it was materialized into. Acceptance records a promotion that "
            "already happened; it cannot be asserted on its own."
        )
    if state != "accepted" and photo_id:
        raise InvalidStateError(
            "a %r candidate cannot carry a photo_id" % state
        )

    con = _connect()
    try:
        _assert_intake_not_approval(con)
        cand = _candidate_row(con, candidate_id)
        if photo_id:
            _assert_photo_owned_by(con, photo_id, cand["person_id"])
        cur = con.execute(
            "UPDATE import_candidate SET state = ?, state_reason = ?, "
            "photo_id = ?, reviewed_by_user_id = ?, reviewed_at = ?, "
            "updated_at = ? WHERE id = ?",
            (state, reason, photo_id, reviewed_by_user_id, _now(), _now(),
             candidate_id),
        )
        _refresh_batch_counters(con, cand["batch_id"])
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def candidate_hide(candidate_id: str, hidden: bool = True) -> bool:
    """Retire (or restore) one candidate. Rule 4 again: a stamp. The
    match reasons and the decision survive, and the batch counters keep
    counting it, because hiding is retirement from a view and not a
    claim that the import never happened."""
    con = _connect()
    try:
        _candidate_row(con, candidate_id)
        cur = con.execute(
            "UPDATE import_candidate SET hidden = ?, hidden_at = ?, "
            "updated_at = ? WHERE id = ?",
            (1 if hidden else 0, _now() if hidden else None, _now(),
             candidate_id),
        )
        con.commit()
        return cur.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def batch_counts(batch_id: str) -> Dict[str, int]:
    """Live counts straight from the candidate rows, plus the stored
    counters, so a caller can see if the two ever disagree."""
    con = _connect()
    try:
        batch = _batch_row(con, batch_id)
        rows = con.execute(
            "SELECT state, COUNT(*) AS n FROM import_candidate "
            "WHERE batch_id = ? GROUP BY state", (batch_id,),
        ).fetchall()
        by_state = {s: 0 for s in CANDIDATE_STATES}
        for r in rows:
            by_state[r["state"]] = r["n"]
        return {
            "total": sum(by_state.values()),
            "pending": by_state["pending"],
            "accepted": by_state["accepted"],
            "rejected": by_state["rejected"],
            "duplicate": by_state["duplicate"],
            "error": by_state["error"],
            "stored_candidate_count": batch["candidate_count"],
            "stored_accepted_count": batch["accepted_count"],
            "stored_rejected_count": batch["rejected_count"],
        }
    finally:
        con.close()


# ------------------------------------------------------- WO-2 queue read
#
# WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 1 (2026-07-26).
#
# `candidates_list()` above is the raw table read: it answers "which rows
# match these filters". A review screen needs a different thing. For each
# candidate it must also show which batch the material arrived in, what
# that batch's source and status were, and which trip -- if any -- the
# candidate is filed under. Assembling that from `candidates_list()`
# means one query for the page, plus one per distinct batch, plus one per
# distinct trip. A real Takeout import lands hundreds of candidates from
# a handful of batches, so that is an N+1 against the exact shape of the
# data. This does it in one read.
#
# Four rules this function holds that the raw list does not:
#
#   1. `person_id` is REQUIRED, not optional. A review queue with no
#      person is a cross-person read. The boundary is easier to keep as a
#      required argument than as a caller's discipline, and an unknown
#      person raises CrossPersonError rather than returning [] -- "this
#      person has nothing" and "there is no such person" are different
#      facts and must not share an answer.
#
#   2. A candidate inside a hidden batch is out of the queue even when
#      the candidate's own `hidden` is 0. Hiding a batch retires the
#      material it landed; a queue that kept serving its rows would make
#      batch-hide a lie. `include_hidden=True` brings both back, and each
#      row carries `batch.hidden` so the caller can tell which kind of
#      hidden it is looking at.
#
#   3. `state_counts` is computed over the whole filtered set and
#      deliberately IGNORES the `state` filter. Counting only what the
#      page returned would report "12 pending" because twelve fit on the
#      page; counting only the requested state would report the queue
#      depth as the thing you already asked for. The useful answer is:
#      you are looking at pending, and here is the shape of the whole
#      queue behind it.
#
#   4. `match_reason` round-trips unchanged, exactly as `candidate_get()`
#      hands it back. Migration 0037 made that column JSON so the review
#      queue could show the importer's reasoning verbatim. This function
#      is the first caller that actually displays it, and it must not be
#      the place a summary creeps in.
#
# This is a read. There is no write here, no counter refresh, and no
# decision: WO-2's decision path is still `candidate_decide()`, which
# still refuses to materialize a photo. Intake is not approval, and
# neither is being looked at.

# Batch and trip columns the queue needs, and no others. Spelled out
# rather than SELECT b.* because `import_batch`, `import_candidate` and
# `trips` all have `id`, `person_id`, `trip_id`, `hidden`, `created_at`
# and `updated_at`, and a star-join would silently let one shadow
# another.
_QUEUE_BATCH_COLUMNS = (
    "id", "label", "source", "status", "external_ref", "hidden",
    "candidate_count", "accepted_count", "rejected_count",
)
#
# The trip columns include its date window on purpose. The single most
# common review question is "does this photo's taken_at fall inside the
# trip it is filed under", and a queue that showed only the trip title
# would make the reviewer open the trip to answer it.
_QUEUE_TRIP_COLUMNS = ("id", "title", "start_date", "end_date", "status")


def queue_read(
    person_id: str,
    trip_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    state: Optional[str] = None,
    include_hidden: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """One read that answers everything an Evidence Review Queue page needs.

    Returns a dict with the page of candidates (each carrying its batch
    and trip inline), the total behind the page, and the state counts for
    the whole filtered queue. Ordered oldest-first, tiebroken on rowid,
    because a review queue is a queue and `created_at` has whole-second
    precision -- a single import lands inside one second and must not
    come back shuffled into uuid order.
    """
    if not isinstance(person_id, str) or not person_id.strip():
        raise InvalidStateError(
            "queue_read requires a person_id; a review queue with no "
            "person is a cross-person read"
        )
    person_id = person_id.strip()
    if state is not None and state not in CANDIDATE_STATES:
        raise InvalidStateError(
            "unknown candidate state %r; known states are %s"
            % (state, ", ".join(CANDIDATE_STATES))
        )
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        raise InvalidStateError("limit must be a non-negative int")
    if not isinstance(offset, int) or offset < 0:
        raise InvalidStateError("offset must be a non-negative int")

    con = _connect()
    try:
        _assert_person_exists(con, person_id)
        if trip_id:
            _assert_trip_owned_by(con, trip_id, person_id)
        if batch_id:
            batch = _batch_row(con, batch_id)
            if batch["person_id"] != person_id:
                raise CrossPersonError(
                    "batch %s belongs to person %s, not %s -- a review "
                    "queue cannot read across people"
                    % (batch_id, batch["person_id"], person_id)
                )

        # The filter every query below shares. `state` is applied to the
        # page and the total but NOT to the state counts; see rule 3.
        base_where = ["c.person_id = ?"]
        base_args: List[Any] = [person_id]
        if batch_id:
            base_where.append("c.batch_id = ?"); base_args.append(batch_id)
        if trip_id:
            base_where.append("c.trip_id = ?"); base_args.append(trip_id)
        if not include_hidden:
            # Both kinds of hidden. See rule 2.
            base_where.append("c.hidden = 0")
            base_where.append("b.hidden = 0")

        join = ("FROM import_candidate c "
                "JOIN import_batch b ON b.id = c.batch_id "
                "LEFT JOIN trips t ON t.id = c.trip_id")
        base_sql = " WHERE " + " AND ".join(base_where)

        # -- state counts, over the filtered queue minus the state filter
        counts = {s: 0 for s in CANDIDATE_STATES}
        for row in con.execute(
            "SELECT c.state AS state, COUNT(*) AS n " + join + base_sql
            + " GROUP BY c.state", base_args,
        ).fetchall():
            if row["state"] in counts:
                counts[row["state"]] = row["n"]

        page_where = list(base_where)
        page_args = list(base_args)
        if state:
            page_where.append("c.state = ?"); page_args.append(state)
        page_sql = " WHERE " + " AND ".join(page_where)

        total = con.execute(
            "SELECT COUNT(*) AS n " + join + page_sql, page_args,
        ).fetchone()["n"]

        select_cols = ["c.*"]
        select_cols += ["b.%s AS _b_%s" % (c, c) for c in _QUEUE_BATCH_COLUMNS]
        select_cols += ["t.%s AS _t_%s" % (c, c) for c in _QUEUE_TRIP_COLUMNS]
        sql = ("SELECT " + ", ".join(select_cols) + " " + join + page_sql
               + " ORDER BY c.created_at ASC, c.rowid ASC")
        args = list(page_args)
        if limit is not None:
            sql += " LIMIT ?"; args.append(limit)
            if offset:
                sql += " OFFSET ?"; args.append(offset)
        elif offset:
            # SQLite will not take OFFSET without LIMIT. -1 is its
            # documented "no limit" sentinel, not a magic number.
            sql += " LIMIT -1 OFFSET ?"; args.append(offset)

        out: List[Dict[str, Any]] = []
        for row in con.execute(sql, args).fetchall():
            d = _row_to_dict(row)
            batch_d = {c: d.pop("_b_" + c) for c in _QUEUE_BATCH_COLUMNS}
            trip_d = {c: d.pop("_t_" + c) for c in _QUEUE_TRIP_COLUMNS}
            d["batch"] = batch_d
            # A candidate with no trip gets None, not a dict of Nones --
            # "not filed yet" is the single most common state in this
            # queue and it should read as one thing, not three nulls.
            d["trip"] = trip_d if trip_d.get("id") else None
            out.append(d)

        return {
            "person_id": person_id,
            "filters": {
                "batch_id": batch_id,
                "trip_id": trip_id,
                "state": state,
                "include_hidden": bool(include_hidden),
                "limit": limit,
                "offset": offset,
            },
            "total": total,
            "returned": len(out),
            "state_counts": counts,
            "queue_depth": counts["pending"],
            "candidates": out,
        }
    finally:
        con.close()


# --------------------------------------------------- WO-2 promotion
#
# WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 3 (2026-07-27).
#
# `candidate_decide(state='accepted')` has always required a photo_id
# and has always refused to create one. Migration 0037 wrote the reason
# into its own DDL comment: "'accepted' means an operator promoted it to
# a photos row". Until now nothing in this lane performed that
# promotion, so acceptance was a state no operator could actually reach
# from the review queue -- they had to go and materialize a photo by
# some other route and bring its id back. This function is that missing
# step, kept as a separate explicit call rather than folded into the
# decision (WO-2 Decision 3, option B, closed by Chris 2026-07-27).
#
# Why a separate route and not an argument on the decision:
#
#   * The decision route's contract is that acceptance RECORDS a
#     promotion that already happened. Making it also perform the
#     promotion would mean a request that fails halfway leaves a photos
#     row with no accepted candidate, or an accepted candidate with no
#     photo -- and the caller could not tell which.
#   * Promotion moves bytes onto disk. The decision does not. Keeping a
#     filesystem write out of the state machine keeps the state machine
#     replayable.
#   * Promotion is idempotent here; a decision is not.
#
# What promotion deliberately does NOT do:
#
#   * It does not decide. The candidate is still `pending` afterwards.
#     Point 3 of the build list, and the honest reading: materializing
#     the file is not the same act as saying "yes, this one belongs".
#     The operator still has to accept, and the existing decision route
#     is what they accept through.
#   * It does not approve. The photos row is born narrator_ready = 0,
#     needs_confirmation = 1, date_approved_for_lori = 0 and
#     location_approved_for_lori = 0. Three of those four are simply
#     the schema defaults and the fourth is passed explicitly; this
#     function asserts them rather than trusting them, because "born
#     unapproved" is the entire safety property and a default is a
#     weaker guarantee than a check.
#   * It does not delete anything, ever, including on failure. If the
#     bytes land and the row insert then fails, the bytes stay in the
#     archive as an orphan and the candidate stays pending. That is the
#     recoverable failure; unwinding a filesystem move is not.
#
# One consequence worth knowing rather than discovering: rejecting a
# candidate AFTER promoting it clears `import_candidate.photo_id` (the
# decision path sets photo_id = NULL for every non-accepted state), and
# the photos row it pointed at survives, unreferenced and still
# unapproved. There is no DELETE in this lane and this function does not
# add one. Cleaning that up is a photo-lane act on the photo, not an
# import-lane act on the candidate.


# ---- vocabulary translation -----------------------------------------
#
# The two tables do NOT share their enums, and promotion is where that
# stops being a documentation problem. `import_candidate.location_source`
# allows 'provider_metadata' and 'operator'; `photos.location_source`
# does not -- its CHECK is (exif_gps, typed_address, spoken_place,
# description_geocode, unknown). A pass-through would raise IntegrityError
# on insert and surface as a 500.
#
# So the collapse is explicit and documented, and it always collapses
# DOWNWARD, to 'unknown'. Promotion must never assert more provenance
# than it has: 'operator' on a candidate means an operator typed the
# coordinates during import, which is not the same claim as
# 'typed_address', and 'provider_metadata' is Google saying so, which is
# not EXIF. Neither has an honest home in the photos vocabulary, so both
# become 'unknown' and the true candidate-side value is preserved
# verbatim in photos.metadata_json.import_provenance, where nothing
# consumes it as authority but the trail survives.
_PROMOTE_LOCATION_SOURCE = {
    "exif_gps": "exif_gps",
    "typed_address": "typed_address",
    "provider_metadata": "unknown",
    "operator": "unknown",
    "unknown": "unknown",
}

# `photos.date_source` has NO CHECK constraint -- migration 0023 left its
# vocabulary (exif | filename_guess | operator_confirmed | missing |
# unknown) as a header comment. That makes it the easy column to lie in,
# so this map is deliberately conservative in the one place it matters:
# candidate 'operator' does NOT become 'operator_confirmed'. At promotion
# time nothing has been confirmed by anyone -- the operator supplied a
# file, they did not review a date -- and 'operator_confirmed' is a value
# a later approval gate could reasonably trust.
_PROMOTE_DATE_SOURCE = {
    "exif": "exif",
    "filename_guess": "filename_guess",
    "provider_metadata": "unknown",
    "operator": "unknown",
    "unknown": "unknown",
}


def _promote_date_fields(cand: Dict[str, Any]) -> Dict[str, Any]:
    """Candidate taken_at -> the four photos date columns.

    Migration 0023 is binding here: a date parsed from a FILENAME is
    "LOW CONFIDENCE -- display only, NEVER auto-fills date_value". So
    the filename_guess branch parks the value in
    `taken_at_filename_guess` and leaves `date_value` NULL, which is the
    one branch where promotion knowingly drops a date it was handed.
    """
    taken_at = cand.get("taken_at")
    src = cand.get("taken_at_source") or "unknown"
    date_source = _PROMOTE_DATE_SOURCE.get(src, "unknown")

    if src == "filename_guess":
        return {
            "date_value": None,
            "date_precision": "unknown",
            "date_source": date_source,
            "taken_at_filename_guess": taken_at,
        }
    if src == "exif" and taken_at:
        # EXIF is the only source that earns 'exact'. Every other
        # precision value ('month', 'year', 'decade') is a claim about
        # how coarse the date is, and a candidate has no column that
        # could express it.
        return {
            "date_value": taken_at,
            "date_precision": "exact",
            "date_source": date_source,
            "taken_at_filename_guess": None,
        }
    if src in ("provider_metadata", "operator") and taken_at:
        return {
            "date_value": taken_at,
            "date_precision": "unknown",
            "date_source": date_source,
            "taken_at_filename_guess": None,
        }
    return {
        "date_value": None,
        "date_precision": "unknown",
        "date_source": date_source,
        "taken_at_filename_guess": None,
    }


def _promote_location_fields(cand: Dict[str, Any]) -> Dict[str, Any]:
    """Candidate location -> the photos location columns.

    `location_label` stays NULL. A candidate has coordinates, not a
    place name, and 0023 is explicit that raw GPS stays private while
    location approval covers "the operator-entered broad location_label
    only" -- so inventing a label here would manufacture the exact field
    the approval gate exists to guard.
    """
    src = cand.get("location_source") or "unknown"
    return {
        "location_source": _PROMOTE_LOCATION_SOURCE.get(src, "unknown"),
        "latitude": cand.get("latitude"),
        "longitude": cand.get("longitude"),
        "location_label": None,
    }


def _promote_metadata(cand: Dict[str, Any],
                      batch: Dict[str, Any],
                      promoted_by_user_id: Optional[str]) -> Dict[str, Any]:
    """The forensic trail, stamped into photos.metadata_json.

    Non-authoritative by contract (0001 says so of the whole column), and
    that is exactly right for this: it holds the candidate-side values
    the vocabulary collapse above could not carry, so 'this photo's
    location_source is unknown' and 'the importer said provider_metadata'
    are both recoverable facts.
    """
    reason = cand.get("match_reason")
    if not isinstance(reason, dict):
        reason = {}
    return {
        "import_provenance": {
            "candidate_id": cand.get("id"),
            "batch_id": cand.get("batch_id"),
            "batch_source": batch.get("source"),
            "batch_label": batch.get("label"),
            "external_id": cand.get("external_id"),
            "filename": cand.get("filename"),
            "mime_type": cand.get("mime_type"),
            "byte_size": cand.get("byte_size"),
            "trip_id": cand.get("trip_id"),
            "candidate_taken_at": cand.get("taken_at"),
            "candidate_taken_at_source": cand.get("taken_at_source"),
            "candidate_location_source": cand.get("location_source"),
            "match_confidence": cand.get("match_confidence"),
            "match_reason": reason,
            "promoted_at": _now(),
            "promoted_by_user_id": promoted_by_user_id,
        }
    }


# ---- late imports ----------------------------------------------------
#
# Deferred, and with the same two-rooting fallback `photos/repository.py`
# uses on its own db import, because the offline test env roots sys.path
# at `server/` while the served app roots it at `server/code`. Deferring
# also keeps this module importable by the migration tests, which have
# no reason to drag the photo lane in.

def _photo_repo() -> Any:
    try:
        from ...services.photos import repository as _pr  # type: ignore
    except ImportError:
        from services.photos import repository as _pr  # type: ignore
    return _pr


def _store_photo_file() -> Any:
    try:
        from ...services.photo_intake.storage import (  # type: ignore
            store_photo_file as _s,
        )
    except ImportError:
        from services.photo_intake.storage import (  # type: ignore
            store_photo_file as _s,
        )
    return _s


def _sha256_file() -> Any:
    try:
        from ...services.photo_intake.dedupe import (  # type: ignore
            sha256_file as _h,
        )
    except ImportError:
        from services.photo_intake.dedupe import (  # type: ignore
            sha256_file as _h,
        )
    return _h


# ---- the promotion --------------------------------------------------

def _link_photo(candidate_id: str, photo_id: str) -> None:
    """Point the candidate at its photo WITHOUT touching its state.

    Spelled out as its own write rather than reusing candidate_decide so
    that it is impossible for this function to move a candidate out of
    'pending' by accident. The batch counters are refreshed anyway --
    they recompute from the rows, and the rows did not change state, so
    this is a no-op that keeps the "counters are always recomputed after
    a candidate write" habit unbroken.
    """
    con = _connect()
    try:
        cand = _candidate_row(con, candidate_id)
        con.execute(
            "UPDATE import_candidate SET photo_id = ?, updated_at = ? "
            "WHERE id = ?",
            (photo_id, _now(), candidate_id),
        )
        _refresh_batch_counters(con, cand["batch_id"])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _assert_born_unapproved(photo_id: str) -> None:
    """Read the row back and refuse to hand over a photo_id that is
    approved for anything.

    This is a paranoid re-read, on purpose. Everything above passes
    narrator_ready=False and leans on schema defaults for the three
    Lori flags, and a schema default is exactly the kind of guarantee
    that gets quietly changed by a later migration. If that ever
    happens, promotion must fail loudly here rather than start minting
    narrator-facing photos out of an import queue.
    """
    con = _connect()
    try:
        row = con.execute(
            "SELECT narrator_ready, needs_confirmation, "
            "date_approved_for_lori, location_approved_for_lori "
            "FROM photos WHERE id = ?", (photo_id,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise ImportRepositoryError(
            "photo %s vanished between creation and verification" % photo_id
        )
    offenders = []
    if int(row["narrator_ready"] or 0):
        offenders.append("narrator_ready")
    if not int(row["needs_confirmation"] or 0):
        offenders.append("needs_confirmation=0")
    if int(row["date_approved_for_lori"] or 0):
        offenders.append("date_approved_for_lori")
    if int(row["location_approved_for_lori"] or 0):
        offenders.append("location_approved_for_lori")
    if offenders:
        raise IntakeIsNotApprovalError(
            "promoted photo %s was born with %s set. A photo materialized "
            "from an import candidate is not narrator-facing and is not "
            "approved for Lori; something has changed the photos defaults."
            % (photo_id, ", ".join(offenders))
        )


def candidate_promote(
    candidate_id: str,
    source_path: Optional[str] = None,
    original_filename: Optional[str] = None,
    promoted_by_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Materialize one candidate into a photos row. Does NOT decide it.

    Returns {photo_id, created, reused, candidate}. `created` is True
    only when this call inserted the photos row; `reused` says why it
    did not ('candidate' = already promoted, 'hash' = the same bytes are
    already in this person's archive).

    Resolution order, first match wins:

      1. The candidate already has a photo_id -> return it. Promotion is
         idempotent, which matters because the review screen's
         "promote + accept" is two requests and the second one can fail.
      2. The candidate's declared file_hash matches a live photo of this
         person -> point at it. This is the ordinary case once the
         operator has already uploaded the image through the photo lane.
      3. `source_path` was supplied -> hash it, refuse if those bytes
         belong to another narrator, store, insert.
      4. Otherwise PhotoBytesMissingError.
    """
    con = _connect()
    try:
        _assert_intake_not_approval(con)
        cand_row = _candidate_row(con, candidate_id)
        batch_row = _batch_row(con, cand_row["batch_id"])
        cand = _row_to_dict(cand_row) or {}
        batch = dict(batch_row)
    finally:
        con.close()

    if batch.get("source") not in PROMOTABLE_SOURCES:
        raise InvalidStateError(
            "batch %s is a %r import; promotion is defined only for %s. A "
            "provider-side import has to fetch its own bytes through its "
            "own lane before there is anything to promote."
            % (batch.get("id"), batch.get("source"),
               " and ".join(PROMOTABLE_SOURCES))
        )

    person_id = cand["person_id"]
    photo_repo = _photo_repo()

    # -- 1. already promoted ------------------------------------------
    if cand.get("photo_id"):
        con = _connect()
        try:
            # Deleted rows included on purpose: a soft-deleted photo is
            # still the photo this candidate was promoted into, and
            # saying "not promoted" about it would invite a second
            # promotion that the UNIQUE file_hash would then refuse.
            _assert_photo_owned_by(con, cand["photo_id"], person_id)
        finally:
            con.close()
        return {
            "photo_id": cand["photo_id"],
            "created": False,
            "reused": "candidate",
            "candidate": candidate_get(candidate_id),
        }

    # -- 2. these bytes are already in this person's archive -----------
    declared_hash = (cand.get("file_hash") or "").strip()
    if declared_hash:
        hit = photo_repo.find_photo_by_hash(person_id, declared_hash)
        if hit:
            _link_photo(candidate_id, hit["id"])
            return {
                "photo_id": hit["id"],
                "created": False,
                "reused": "hash",
                "candidate": candidate_get(candidate_id),
            }

    # -- 3. materialize from supplied bytes ----------------------------
    if not source_path:
        raise PhotoBytesMissingError(
            "candidate %s has no photo to promote: it is not already "
            "linked, and no file was supplied. An import candidate "
            "carries a filename and a size, never the image itself, so "
            "promotion needs either the file or a photo of this person "
            "already holding the same bytes." % candidate_id
        )

    # Hash BEFORE moving anything, exactly as POST /api/photos does, so
    # a duplicate does not litter the archive with an orphan copy.
    real_hash = _sha256_file()(source_path)

    con = _connect()
    try:
        # Person-scoped first: same bytes, same person -> link, and the
        # operator's file was simply one they already had.
        mine = photo_repo.find_photo_by_hash(person_id, real_hash)
        if mine:
            _link_photo(candidate_id, mine["id"])
            return {
                "photo_id": mine["id"],
                "created": False,
                "reused": "hash",
                "candidate": candidate_get(candidate_id),
            }
        # photos.file_hash is UNIQUE across the WHOLE table, not per
        # narrator, and soft-deleted rows keep their hash. So a hash
        # owned by anyone else -- or soft-deleted under this person --
        # is an insert that will raise IntegrityError. Answer it here,
        # where the reason can be named, instead of as a 500.
        clash = con.execute(
            "SELECT id, narrator_id, deleted_at FROM photos "
            "WHERE file_hash = ?", (real_hash,),
        ).fetchone()
    finally:
        con.close()

    if clash is not None:
        if clash["narrator_id"] != person_id:
            raise CrossPersonError(
                "those bytes are already stored as photo %s under another "
                "narrator; promoting them here would file one person's "
                "picture as another person's evidence" % clash["id"]
            )
        raise CrossPersonError(
            "those bytes are already stored as photo %s for this person "
            "but that photo is deleted; restore it in the photo lane "
            "rather than promoting a second copy" % clash["id"]
        )

    date_fields = _promote_date_fields(cand)
    loc_fields = _promote_location_fields(cand)
    metadata = _promote_metadata(cand, batch, promoted_by_user_id)

    photo_id = uuid.uuid4().hex
    stored = _store_photo_file()(
        narrator_id=person_id,
        source_path=source_path,
        original_filename=(original_filename or cand.get("filename")
                           or "promoted.bin"),
        photo_id=photo_id,
    )

    photo_repo.create_photo(
        narrator_id=person_id,
        photo_id=photo_id,
        image_path=stored["image_path"],
        thumbnail_path=stored.get("thumbnail_path"),
        file_hash=stored["file_hash"],
        description=None,
        date_value=date_fields["date_value"],
        date_precision=date_fields["date_precision"],
        location_label=loc_fields["location_label"],
        location_source=loc_fields["location_source"],
        latitude=loc_fields["latitude"],
        longitude=loc_fields["longitude"],
        # Born not narrator-facing. needs_confirmation stays 1 because
        # nothing about this row has been looked at by a human yet.
        narrator_ready=False,
        needs_confirmation=True,
        uploaded_by_user_id=promoted_by_user_id,
        metadata=metadata,
    )

    # `create_photo` does not list date_source or taken_at_filename_guess
    # in its INSERT -- they were added by 0023, after it was written, and
    # widening a module the whole photo lane shares is not this slice's
    # business. So they are stamped here, in their own statement. The
    # two *_approved_for_lori columns are deliberately NOT touched: their
    # DEFAULT 0 is the correct value and writing it explicitly would make
    # this function look like it has an opinion about approval.
    con = _connect()
    try:
        con.execute(
            "UPDATE photos SET date_source = ?, taken_at_filename_guess = ? "
            "WHERE id = ?",
            (date_fields["date_source"],
             date_fields["taken_at_filename_guess"], photo_id),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    _assert_born_unapproved(photo_id)
    _link_photo(candidate_id, photo_id)

    return {
        "photo_id": photo_id,
        "created": True,
        "reused": None,
        "candidate": candidate_get(candidate_id),
    }
