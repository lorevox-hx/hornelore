from __future__ import annotations

import functools
import logging
import os
import re
import json
# `shutil` was imported here for the one-directory Kawa cleanup inside
# `hard_delete_person`. Filesystem erasure moved to
# `services/narrator_erasure.py` on 2026-08-20 -- one inventory rather
# than one remembered case -- and nothing in this module removes files
# any more. Left as a comment rather than a silent deletion so the next
# reader knows where the removal went.
import sqlite3
import threading
import types
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 1 (2026-08-26).
# Safe at module scope BECAUSE the service imports nothing from here:
# every storage function it exposes takes an open connection. That is
# what lets `create_person()` enroll inside its own transaction, and
# what lets the PATCH accessor re-resolve inside `BEGIN IMMEDIATE`.
from .services import profile_seed as _profile_seed

logger = logging.getLogger(__name__)


# ── DOB sanitisation ─────────────────────────────────────────────────────────
_ISO_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _sanitise_dob(raw: Optional[str]) -> str:
    """Normalise a date-of-birth string.

    Accepts ISO format (YYYY, YYYY-MM, YYYY-MM-DD) as-is.
    Fuzzy/uncertain strings (e.g. "1947, I think?") are stored prefixed with
    ``uncertain:`` so downstream code can distinguish validated from raw input.
    Empty input returns empty string.
    """
    if not raw:
        return ""
    raw = raw.strip()
    if _ISO_DATE_RE.match(raw):
        return raw
    # Preserve uncertain input but flag it clearly
    if not raw.startswith("uncertain:"):
        return f"uncertain:{raw}"
    return raw


# -----------------------------------------------------------------------------
# Paths / connection
# -----------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", "data")).expanduser()
DB_DIR = DATA_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_NAME = os.getenv("DB_NAME", "lorevox.sqlite3").strip() or "lorevox.sqlite3"
DB_PATH = DB_DIR / DB_NAME

# v7.4D — log DB path at import time so startup output confirms the right file.
logger.info("Lorevox DB: %s", DB_PATH)


# WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A seed gate.
# Once-per-process flag for the bio_schema seed loader. init_db() runs
# on every CRUD call (cheap idempotent CREATE TABLE IF NOT EXISTS chain),
# but seeding ~67 bio_fields rows on every call is wasteful. This flag
# guarantees the seed lands at the first init_db() call (process boot
# or first chat turn after launch) and is skipped thereafter. Tests
# may reset it via the chore/bio-seed-loader-init test module to
# exercise the seed path under a fresh DB.
_BIO_SEED_LOADED: bool = False


# Thread-local registry for the connection-hygiene wrap (module bottom).
# A thread with no wrapper active has no ``open`` attribute and _connect()
# behaves exactly as before.
_CONN_TRACK = threading.local()


def _closes_connections_on_error(fn):
    """Guarantee close-on-exception for every connection ``fn`` opens.

    On success the wrapped function's own close discipline applies,
    unchanged.  On ANY exception, every connection opened during the call
    (registered by _connect) is rolled back and closed before the
    exception propagates, so a leaked connection can never keep holding
    the SQLite write lock — the 2026-07-22 incident class.

    Nested wrapped calls each track their own connections; on exit the
    child's list is folded into the parent's so tracking survives the
    whole call chain (closing an already-closed connection is a no-op
    here because both cleanup calls swallow ProgrammingError).
    """
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        prev = getattr(_CONN_TRACK, "open", None)
        mine: list = []
        _CONN_TRACK.open = mine
        try:
            return fn(*args, **kwargs)
        except BaseException:
            for _con in mine:
                try:
                    _con.rollback()
                except Exception:
                    pass
                try:
                    _con.close()
                except Exception:
                    pass
            raise
        finally:
            _CONN_TRACK.open = prev
            if prev is not None:
                prev.extend(mine)
    _wrapper.__hornelore_conn_guard__ = True
    return _wrapper


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA foreign_keys=ON;")
    # WO-LORI-SAFETY-INTEGRATION-01 Phase 1 follow-up — busy_timeout was 0
    # (the SQLite default), which caused "database is locked" errors when the
    # safety persist block (save_segment_flag + increment_session_turn +
    # set_session_softened) raced with archive_append_event during a chat
    # turn. Surfaced live in the 2026-04-28 19:40 chat smoke test: three
    # turns errored with "Chat backend error: database is locked", one of
    # which was the very first triggering safety message — a critical
    # failure mode (no safety response on a triggering turn). 5000ms gives
    # WAL-serialized writers enough time to queue cleanly without affecting
    # the latency of well-behaved single-writer turns.
    con.execute("PRAGMA busy_timeout=5000;")
    # SECURITY/STABILITY-REVIEW-2026-08-12 — connection-hygiene tracking.
    # 74 of ~142 call sites in this module open a connection with no
    # try/finally, so an exception anywhere in the function body leaks the
    # connection *while it may hold the write lock* — the documented root
    # cause of the 2026-07-22 "database is locked" live incident (see
    # add_timeline_event, which was fixed individually).  Rather than
    # hand-editing every function, _connect() registers each connection in
    # a thread-local list and every public function in this module is
    # wrapped (see module bottom) so that on ANY exception every
    # connection the call opened is rolled back and closed before the
    # exception propagates.  Success paths are untouched.
    _reg = getattr(_CONN_TRACK, "open", None)
    if _reg is not None:
        _reg.append(con)
    return con


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _json_load(s: str | None, default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ── WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1, 2026-08-09 ──────────────
# Internal guidance the browser composes for Lori travels in the user
# message slot and was written down as if the narrator had said it.
# Authorship is now decided ONCE, at the persistence boundary, and
# recorded on the row. Readers ask the row; they do not re-read the prose.
#
# `role` deliberately stays `'user'` (Option A) so the directive still
# replays to the model, which is the entire point of in-band guidance.

#: Value stored at `turns.meta_json["origin"]` for an internal directive.
TURN_ORIGIN_SYSTEM_DIRECTIVE = "system_directive"

#: Content prefixes the browser emits. Kept ONLY for the legacy fallback
#: below -- rows written before Phase 1 carry no flag, and this WO does
#: not rewrite history. New code must not use this to classify.
_LEGACY_DIRECTIVE_PREFIXES = ("[SYSTEM:", "[SYSTEM_QF:", "[SYSTEM")


def turn_is_system_directive(row: Any) -> bool:
    """True when this `turns` row is internal guidance, not narrator speech.

    ONE function so that eighteen modules stop each inventing their own
    version of the question. Takes a mapping or a sqlite3.Row with
    `meta_json` and `content`.

    THE FLAG WINS; THE PREFIX IS A FALLBACK WITH AN END DATE. Rows
    written from 2026-08-09 carry `origin`. Rows written before it carry
    nothing, there are 120 of them, and no historical rewrite is
    authorised -- so the prefix check remains for those and is marked as
    what it is. Once the pre-Phase-1 rows are gone or migrated by a
    separate approved decision, the fallback can go with them.

    A row that carries the flag is NOT re-checked against its text. That
    ordering is the fix: a narrator who genuinely types "[SYSTEM: ..."
    gets a row with no flag, falls to the fallback, and is misread only
    until their turn ages out -- whereas under the old scheme they were
    misread forever.
    """
    # `turns` rows spell it `meta_json` (a JSON string); `export_turns()`
    # hands back the same fact parsed, under `meta`. Both are accepted so
    # that a caller does not have to know which side of that mapping it
    # is on -- which is the mistake eighteen separate prefix checks were
    # already making about `content`.
    meta = None
    for key in ("meta_json", "meta"):
        try:
            meta = row[key] if not hasattr(row, "get") else row.get(key)
        except Exception:
            meta = None
        if meta:
            break
    if meta:
        try:
            parsed = json.loads(meta) if isinstance(meta, str) else meta
            if isinstance(parsed, dict):
                if parsed.get("origin") == TURN_ORIGIN_SYSTEM_DIRECTIVE:
                    return True
                # An explicit flag of any other origin is still an
                # answer: this row was classified and is not a directive.
                if "origin" in parsed:
                    return False
        except Exception:
            pass  # unparseable meta is no worse than the pre-Phase-1 state
    try:
        content = row["content"] if not hasattr(row, "get") else row.get("content")
    except Exception:
        content = None
    return str(content or "").lstrip().startswith("[SYSTEM")


# -----------------------------------------------------------------------------
# WO-13 Phase 1 — Legacy facts → family_truth_rows backfill
#
# Called from init_db() after the family_truth_* schema is created. The
# unique partial index on family_truth_rows.source_fact_id makes this
# idempotent: re-running on an already-migrated DB is a no-op.
#
# Policy:
#   - The legacy `facts` table is NEVER modified, deleted, or truncated.
#   - Every legacy fact becomes a `needs_verify` row in family_truth_rows so
#     a human reviewer can approve/qualify/reject it.
#   - Rows matching the WO-12B contamination patterns get legacy_suspect=1
#     so the UI can offer bulk dismiss.
# -----------------------------------------------------------------------------
_WO13_FACT_TYPE_TO_FIELD = {
    "birth": "date_of_birth",
    "birthplace": "place_of_birth",
    "death": "date_of_death",
    "marriage": "marriage",
    "children": "children",
    "employment_start": "employment",
    "employment_end": "employment",
    "education": "education",
    "residence": "residence",
    "family_relationship": "family_relationship",
}

_WO13_SENTENCE_TERMINATORS = set(".!?\"')”’…")


def _wo13_flag_legacy_suspect(
    statement: str,
    narrator_name: str,
    meta: Dict[str, Any],
    narrative_role: str,
    meaning_tags: List[str],
) -> int:
    """Return 1 if the legacy fact matches a WO-12B contamination pattern.

    Patterns:
      (a) Truncation: statement does not end with a sentence terminator.
      (b) Cross-narrator bleed: statement mentions 'Williston' but the
          narrator is not Chris (the known stress-test source).
      (c) chat_extraction origin: meta.source set by the broken client-side
          regex path in ui/js/app.js.
      (d) Climax + loss combo: narrative_role='climax' with a 'loss' tag
          (matches the climax-stamping routing bug).
    """
    s = (statement or "").strip()
    if s:
        last_char = s[-1]
        if last_char not in _WO13_SENTENCE_TERMINATORS:
            return 1
    if s and "williston" in s.lower() and "chris" not in (narrator_name or "").lower():
        return 1
    try:
        if str((meta or {}).get("source", "")).lower() == "chat_extraction":
            return 1
    except Exception:
        pass
    if (narrative_role or "").lower() == "climax":
        for t in meaning_tags or []:
            if str(t).lower() == "loss":
                return 1
    return 0


def _wo13_backfill_facts_to_family_truth_rows(
    con: sqlite3.Connection, cur: sqlite3.Cursor
) -> None:
    """Idempotent one-time backfill. Safe to run on every boot."""
    try:
        facts_rows = cur.execute(
            "SELECT id,person_id,session_id,fact_type,statement,date_text,"
            "date_normalized,confidence,status,inferred,source_turn_index,"
            "created_at,updated_at,meta_json,meaning_tags_json,narrative_role,"
            "experience,reflection FROM facts;"
        ).fetchall()
    except sqlite3.Error as e:
        logger.warning("WO-13 backfill: facts table not queryable (%s); skipping", e)
        return

    if not facts_rows:
        return

    people_map = {
        r[0]: (r[1] or "")
        for r in cur.execute("SELECT id, display_name FROM people;").fetchall()
    }

    now = _now_iso()
    inserted = 0
    suspect = 0
    for f in facts_rows:
        fid = f["id"]
        existing = cur.execute(
            "SELECT 1 FROM family_truth_rows WHERE source_fact_id=? LIMIT 1;",
            (fid,),
        ).fetchone()
        if existing:
            continue

        meta = _json_load(f["meta_json"], {}) or {}
        meaning_tags = _json_load(f["meaning_tags_json"], []) or []
        statement = (f["statement"] or "").strip()
        fact_type = (f["fact_type"] or "general").strip() or "general"
        person_id = f["person_id"] or ""
        narrator_name = people_map.get(person_id, "")
        narrative_role = f["narrative_role"] or ""

        legacy_suspect = _wo13_flag_legacy_suspect(
            statement, narrator_name, meta, narrative_role, meaning_tags
        )
        if legacy_suspect:
            suspect += 1

        field = _WO13_FACT_TYPE_TO_FIELD.get(fact_type, fact_type)

        provenance = {
            "session_id": f["session_id"] or "",
            "source_turn_index": f["source_turn_index"],
            "legacy_meta": meta,
            "legacy_fact_type": fact_type,
            "legacy_status": f["status"] or "",
            "legacy_experience": f["experience"] or "",
            "legacy_reflection": f["reflection"] or "",
            "backfilled_at": now,
        }

        cur.execute(
            """
            INSERT INTO family_truth_rows(
              id, person_id, note_id, subject_name, relationship, field,
              source_says, approved_value, status, qualification,
              reviewer, reviewed_at, confidence, narrative_role, meaning_tags,
              provenance, legacy_suspect, extraction_method, source_fact_id,
              created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                _uuid(),
                person_id,
                None,
                narrator_name,            # subject defaults to narrator (self-claim)
                "self",
                field,
                statement,                # source_says = raw statement (preserved)
                "",                       # approved_value — empty until reviewer sets it
                "needs_verify",           # every backfilled row must be reviewed
                "",                       # qualification
                "",                       # reviewer
                "",                       # reviewed_at
                float(f["confidence"] or 0.0),
                narrative_role,
                _json_dump(meaning_tags),
                _json_dump(provenance),
                legacy_suspect,
                "backfill",
                fid,
                f["created_at"] or now,
                now,
            ),
        )
        inserted += 1

    if inserted:
        logger.info(
            "WO-13 backfill: migrated %d legacy facts → family_truth_rows "
            "(%d flagged legacy_suspect=1). facts table untouched.",
            inserted,
            suspect,
        )


# -----------------------------------------------------------------------------
# WO-13 Phase 3 — Reference narrator seeding
#
# Known reference narrators are seeded by display_name substring match. The
# seed is idempotent — it only promotes a person from 'live' → 'reference'.
# It never demotes. To demote, use PATCH /api/people/{id}.
#
# Env override:
#   HORNELORE_REFERENCE_NARRATORS="Shatner,Dolly,Other Name"
# -----------------------------------------------------------------------------
_WO13_DEFAULT_REFERENCE_NAMES = ("shatner", "dolly")


def _wo13_reference_name_patterns() -> List[str]:
    raw = os.getenv("HORNELORE_REFERENCE_NARRATORS", "")
    if not raw.strip():
        return list(_WO13_DEFAULT_REFERENCE_NAMES)
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _wo13_seed_reference_narrators(
    con: sqlite3.Connection, cur: sqlite3.Cursor
) -> None:
    patterns = _wo13_reference_name_patterns()
    if not patterns:
        return
    rows = cur.execute(
        "SELECT id, display_name, narrator_type FROM people;"
    ).fetchall()
    promoted = 0
    for r in rows:
        name = (r["display_name"] or "").lower()
        current = (r["narrator_type"] or "live").lower()
        if current == "reference":
            continue
        if any(pat in name for pat in patterns):
            cur.execute(
                "UPDATE people SET narrator_type='reference', updated_at=? WHERE id=?;",
                (_now_iso(), r["id"]),
            )
            promoted += 1
    if promoted:
        logger.info(
            "WO-13 narrator_type seed: promoted %d people to reference (patterns=%s)",
            promoted,
            patterns,
        )


# -----------------------------------------------------------------------------
# WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 — 0043 backfill skip report
# -----------------------------------------------------------------------------
# Databases already reported on in THIS process. Keyed by path rather than
# a bare boolean because tests legitimately drive several databases through
# one interpreter, and a single global flag would let the first one silence
# the rest.
_0043_SKIPS_REPORTED: set = set()


def _report_0043_backfill_skips(con: sqlite3.Connection, db_path: str) -> None:
    """Report legacy photo-day values migration 0043 refused to carry.

    0043 backfills one placement per legacy ``trip_photo_links.trip_day_id``
    but will not copy a value pointing at a missing day or at a day in
    another trip — copying the first would fail the new foreign key and take
    the migration down, the second would propagate corruption SQLite cannot
    forbid. It records every such row in
    ``trip_photo_day_placement_skips``. A migration is SQL run through
    ``executescript`` and cannot log for itself, so this is where a skip
    becomes something an operator can see: without it a photograph that had
    a day in the old column would have no day in the new table and nothing
    anywhere would say why.

    CORRECTED 2026-08-12, and the correction is the interesting part. The
    first version logged on BOTH paths and lived inline in ``init_db()`` —
    which runs on essentially every CRUD call, not once at boot. On a clean
    database that produced dozens of identical
    ``0043 backfill: every legacy photo-day value carried over cleanly``
    lines in three minutes, one every thirty seconds thereafter. Two
    separate defects were hiding in that: a message on the clean path at
    all, and a repetition that would have applied to the WARNING too — a
    warning repeated 2,880 times a day is worse than an info one, because
    it teaches an operator to scroll past warnings.

    So: **the clean path is silent at every level**, and the warning fires
    once per database per process. Each boot is a new process, so every boot
    that has skips still warns exactly once; what is gone is the repetition
    *within* a boot, which was the flood.

    Non-fatal by design, like the pre-0034 orphan check it mirrors:
    refusing to start the stack over a historical row would take the whole
    product down to report a problem the operator can neither see nor fix at
    that moment.
    """
    if db_path in _0043_SKIPS_REPORTED:
        return
    try:
        _cur_skip = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='trip_photo_day_placement_skips';"
        )
        if _cur_skip.fetchone() is None:
            # Pre-0043 database. Not an error, and not something to
            # remember — the table appears the moment 0043 runs.
            return
        _rows = con.execute(
            "SELECT reason, COUNT(*) AS n, "
            "       GROUP_CONCAT(photo_link_id) AS ids "
            "  FROM trip_photo_day_placement_skips "
            " GROUP BY reason;"
        ).fetchall()
        _total = sum(int(r[1]) for r in _rows)
        if _total:
            logger.warning(
                "[migrations] 0043 backfill: %d legacy photo-day value(s) "
                "NOT carried into trip_photo_day_placements. By reason: %s. "
                "Those photographs are on no day in the new model until an "
                "operator places them. (Reported once per process.)",
                _total,
                "; ".join("%s=%d (%s)" % (r[0], int(r[1]),
                                          str(r[2] or "")[:200])
                          for r in _rows),
            )
        # Clean OR reported: either way this database has been assessed and
        # must not be assessed again on the next of thousands of init_db()
        # calls. Nothing writes to the ledger after 0043 runs, so there is
        # no later state to miss.
        _0043_SKIPS_REPORTED.add(db_path)
    except Exception:
        logger.exception(
            "[migrations] 0043 backfill preflight failed "
            "(non-fatal — migrations already applied)")
        # Remember the failure too. A preflight that cannot run will not
        # start running later in the same process, and re-raising the same
        # traceback every thirty seconds is the flood this correction
        # exists to remove.
        _0043_SKIPS_REPORTED.add(db_path)


# -----------------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------------
def init_db() -> None:
    con = _connect()
    cur = con.cursor()

    # -----------------------------
    # Sessions + turns (chat persistence)
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          conv_id TEXT PRIMARY KEY,
          title TEXT DEFAULT '',
          updated_at TEXT,
          payload_json TEXT DEFAULT '{}'
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          conv_id TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          ts TEXT NOT NULL,
          anchor_id TEXT DEFAULT '',
          meta_json TEXT DEFAULT '{}',
          FOREIGN KEY(conv_id) REFERENCES sessions(conv_id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_turns_conv_ts ON turns(conv_id, ts, id);")

    # -----------------------------
    # People + profiles
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
          id TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          role TEXT DEFAULT '',
          date_of_birth TEXT DEFAULT '',
          place_of_birth TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
          person_id TEXT PRIMARY KEY,
          profile_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )

    # -----------------------------
    # Media
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS media (
          id TEXT PRIMARY KEY,
          person_id TEXT,
          kind TEXT NOT NULL DEFAULT 'image',
          filename TEXT NOT NULL DEFAULT '',
          mime TEXT NOT NULL DEFAULT '',
          bytes INTEGER NOT NULL DEFAULT 0,
          sha256 TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE SET NULL
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_media_person_created ON media(person_id, created_at);")

    # -----------------------------
    # Timeline
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS timeline_events (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          date TEXT NOT NULL,                 -- ISO date or datetime string
          title TEXT NOT NULL,
          body TEXT NOT NULL DEFAULT '',
          kind TEXT NOT NULL DEFAULT 'event',
          created_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_person_date ON timeline_events(person_id, date);")

    # -----------------------------
    # Interview plans / questions / sessions / answers
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_plans (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_sections (
          id TEXT PRIMARY KEY,
          plan_id TEXT NOT NULL,
          title TEXT NOT NULL,
          ord INTEGER NOT NULL,
          FOREIGN KEY(plan_id) REFERENCES interview_plans(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_questions (
          id TEXT PRIMARY KEY,
          plan_id TEXT NOT NULL,
          section_id TEXT NOT NULL,
          ord INTEGER NOT NULL,
          prompt TEXT NOT NULL,
          kind TEXT NOT NULL DEFAULT 'text',
          required INTEGER NOT NULL DEFAULT 0,
          profile_path TEXT,
          FOREIGN KEY(plan_id) REFERENCES interview_plans(id) ON DELETE CASCADE,
          FOREIGN KEY(section_id) REFERENCES interview_sections(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interview_q_plan_ord ON interview_questions(plan_id, ord);")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_sessions (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          plan_id TEXT NOT NULL,
          started_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          active_question_id TEXT,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
          FOREIGN KEY(plan_id) REFERENCES interview_plans(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_answers (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          person_id TEXT NOT NULL,
          question_id TEXT NOT NULL,
          answer TEXT NOT NULL DEFAULT '',
          skipped INTEGER NOT NULL DEFAULT 0,
          ts TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
          FOREIGN KEY(question_id) REFERENCES interview_questions(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interview_a_session_ts ON interview_answers(session_id, ts);")

    # -----------------------------
    # Facts  (atomic, source-backed claims)
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          session_id TEXT,
          fact_type TEXT NOT NULL DEFAULT 'general',
          statement TEXT NOT NULL,
          date_text TEXT DEFAULT '',
          date_normalized TEXT DEFAULT '',
          confidence REAL DEFAULT 0.0,
          status TEXT NOT NULL DEFAULT 'extracted',
          inferred INTEGER NOT NULL DEFAULT 0,
          source_turn_index INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_facts_person ON facts(person_id, created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session_id);")

    # -----------------------------
    # Life phases  (e.g. "childhood", "first marriage", "OT career")
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS life_phases (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          title TEXT NOT NULL,
          start_date TEXT DEFAULT '',
          end_date TEXT DEFAULT '',
          date_precision TEXT DEFAULT 'year',
          description TEXT DEFAULT '',
          ord INTEGER DEFAULT 0,
          created_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_life_phases_person ON life_phases(person_id, ord);")

    # -----------------------------
    # Migrate timeline_events: add new calendar columns if missing
    # -----------------------------
    existing_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(timeline_events);").fetchall()
    }
    calendar_cols = {
        "end_date": "ALTER TABLE timeline_events ADD COLUMN end_date TEXT DEFAULT '';",
        "date_precision": "ALTER TABLE timeline_events ADD COLUMN date_precision TEXT DEFAULT 'exact_day';",
        "is_approximate": "ALTER TABLE timeline_events ADD COLUMN is_approximate INTEGER DEFAULT 0;",
        "confidence": "ALTER TABLE timeline_events ADD COLUMN confidence REAL DEFAULT 1.0;",
        "status": "ALTER TABLE timeline_events ADD COLUMN status TEXT DEFAULT 'reviewed';",
        "source_session_ids": "ALTER TABLE timeline_events ADD COLUMN source_session_ids TEXT DEFAULT '[]';",
        "source_fact_ids": "ALTER TABLE timeline_events ADD COLUMN source_fact_ids TEXT DEFAULT '[]';",
        "tags": "ALTER TABLE timeline_events ADD COLUMN tags TEXT DEFAULT '[]';",
        "display_date": "ALTER TABLE timeline_events ADD COLUMN display_date TEXT DEFAULT '';",
        "phase_id": "ALTER TABLE timeline_events ADD COLUMN phase_id TEXT DEFAULT '';",
    }
    for col_name, alter_sql in calendar_cols.items():
        if col_name not in existing_cols:
            cur.execute(alter_sql)

    # -----------------------------
    # Migrate facts: add Meaning Engine fields if missing (Bug MAT-01 fix)
    # These fields were sent by the frontend in POST /api/facts/add but not persisted.
    # Added in the meaning engine implementation (Phase A+B).
    # -----------------------------
    facts_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(facts);").fetchall()
    }
    meaning_cols = {
        "meaning_tags_json": "ALTER TABLE facts ADD COLUMN meaning_tags_json TEXT NOT NULL DEFAULT '[]';",
        "narrative_role":    "ALTER TABLE facts ADD COLUMN narrative_role TEXT DEFAULT NULL;",
        "experience":        "ALTER TABLE facts ADD COLUMN experience TEXT DEFAULT NULL;",
        "reflection":        "ALTER TABLE facts ADD COLUMN reflection TEXT DEFAULT NULL;",
    }
    for col_name, alter_sql in meaning_cols.items():
        if col_name not in facts_cols:
            cur.execute(alter_sql)

    # -----------------------------
    # Migrate media: add rich metadata columns if missing (Bug MB-01 fix)
    # Original table only had kind/filename/mime/bytes/sha256/meta_json.
    # Router expected description/taken_at/location_name/latitude/longitude/exif_json.
    # -----------------------------
    media_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(media);").fetchall()
    }
    media_new_cols = {
        "description":   "ALTER TABLE media ADD COLUMN description TEXT NOT NULL DEFAULT '';",
        "taken_at":      "ALTER TABLE media ADD COLUMN taken_at TEXT DEFAULT NULL;",
        "location_name": "ALTER TABLE media ADD COLUMN location_name TEXT DEFAULT NULL;",
        "latitude":      "ALTER TABLE media ADD COLUMN latitude REAL DEFAULT NULL;",
        "longitude":     "ALTER TABLE media ADD COLUMN longitude REAL DEFAULT NULL;",
        "exif_json":     "ALTER TABLE media ADD COLUMN exif_json TEXT NOT NULL DEFAULT '{}';",
    }
    for col_name, alter_sql in media_new_cols.items():
        if col_name not in media_cols:
            cur.execute(alter_sql)

    # -----------------------------
    # Media attachments — links a photo to a memoir section or fact (Media Builder)
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS media_attachments (
          id TEXT PRIMARY KEY,
          media_id TEXT NOT NULL,
          entity_type TEXT NOT NULL DEFAULT 'memoir_section',
          entity_id TEXT NOT NULL,
          person_id TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE SET NULL
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_media ON media_attachments(media_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_entity ON media_attachments(entity_type, entity_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_person ON media_attachments(person_id);"
    )

    # -----------------------------
    # Migrate people: add soft-delete columns if missing (Phase 2 — narrator delete)
    # -----------------------------
    people_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(people);").fetchall()
    }
    people_delete_cols = {
        "is_deleted":     "ALTER TABLE people ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;",
        "deleted_at":     "ALTER TABLE people ADD COLUMN deleted_at TEXT DEFAULT NULL;",
        "deleted_by":     "ALTER TABLE people ADD COLUMN deleted_by TEXT DEFAULT NULL;",
        "delete_reason":  "ALTER TABLE people ADD COLUMN delete_reason TEXT DEFAULT '';",
        "undo_expires_at":"ALTER TABLE people ADD COLUMN undo_expires_at TEXT DEFAULT NULL;",
    }
    for col_name, alter_sql in people_delete_cols.items():
        if col_name not in people_cols:
            cur.execute(alter_sql)

    # -----------------------------
    # Testing-only narrator eligibility.
    #
    # THIS BLOCK OWNS THE COLUMN. There is deliberately no migration for
    # it, and that is not an oversight — it is the rule this table
    # already learned the hard way. Migration 0013 records the incident
    # in its own header: an earlier version ALTERed `people` to add
    # pronouns / pronouns_other / current_residence, SQLite has no
    # "ADD COLUMN IF NOT EXISTS", so on every init_db retry the migration
    # re-ran, failed with "duplicate column name", never marked itself
    # complete, and "knock[ed] out every endpoint that consulted the
    # schema". The recorded fix was to let this PRAGMA-guarded block
    # handle people-column adds instead.
    #
    # The convention that follows is visible in the tree: `narrator_type`
    # is added here and by no migration; `presentation_epoch` is added by
    # a migration and mirrored nowhere. One owner per column, never both.
    #
    # `testing_only` was accepted by both creation paths for a long time
    # and stored by neither — it bypassed the consent gate, went into the
    # response body, and was dropped. Nothing depended on the difference
    # until the Guard Lab, whose whole safety gate is "armed evaluation
    # AND durably testing-only narrator". Experiments that strip Lori's
    # narrator-facing interventions must never be able to reach a real
    # narrator by accident, and a flag that is not persisted cannot
    # protect anyone.
    #
    # Existing rows become 0. Fail-closed is the only safe direction, and
    # the tempting inference — treat missing consent attestations as
    # evidence of a test narrator — is actively wrong: consent writes are
    # best-effort, so a failed write on a REAL narrator would silently
    # reclassify them as an experiment subject.
    if "testing_only" not in people_cols:
        cur.execute(
            "ALTER TABLE people ADD COLUMN testing_only INTEGER NOT NULL "
            "DEFAULT 0 CHECK (testing_only IN (0, 1));"
        )

    # Index for fast active-narrator queries (exclude soft-deleted)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_people_active ON people(is_deleted, updated_at);"
    )

    # -----------------------------
    # WO-13 Phase 3 — narrator_type (live | reference)
    #
    # live:       a real, interviewable narrator whose memories feed the memoir
    #             (Kent, Janice, Chris, Maggie, etc). Writable through the normal
    #             extraction + family-truth pipeline.
    # reference:  an illustrative / role-model narrator seeded from structuredBio
    #             or profile (Shatner, Dolly). Fully read-only from the
    #             narrative-memory pipeline — facts.add and family_truth writes
    #             are rejected with 403. Profile writes are still allowed so the
    #             canonical seed data can be maintained.
    #
    # Default 'live' for all existing rows; the seed routine below promotes
    # known reference narrators by display_name match.
    # -----------------------------
    if "narrator_type" not in people_cols:
        cur.execute(
            "ALTER TABLE people ADD COLUMN narrator_type TEXT NOT NULL DEFAULT 'live';"
        )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_people_narrator_type ON people(narrator_type, is_deleted);"
    )
    _wo13_seed_reference_narrators(con, cur)

    # -----------------------------
    # Narrator delete audit log (Phase 2 — append-only)
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS narrator_delete_audit (
          id TEXT PRIMARY KEY,
          action TEXT NOT NULL,
          person_id TEXT NOT NULL,
          display_name TEXT NOT NULL DEFAULT '',
          requested_by TEXT DEFAULT NULL,
          dependency_counts_json TEXT NOT NULL DEFAULT '{}',
          result TEXT NOT NULL DEFAULT 'success',
          error_detail TEXT DEFAULT NULL,
          ts TEXT NOT NULL
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_narrator_audit_ts ON narrator_delete_audit(ts);"
    )

    # Default plan (safe even if empty)
    now = _now_iso()
    cur.execute(
        "INSERT OR IGNORE INTO interview_plans(id,title,created_at) VALUES(?,?,?);",
        ("default", "Default Plan", now),
    )

    # -----------------------------
    # RAG (optional; used by inspector/router if you keep it)
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_docs (
          id TEXT PRIMARY KEY,
          title TEXT,
          source TEXT,
          created_at TEXT,
          text TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_chunks (
          id TEXT PRIMARY KEY,
          doc_id TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          text TEXT NOT NULL,
          FOREIGN KEY(doc_id) REFERENCES rag_docs(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id, chunk_index);")

    # -----------------------------
    # Section summaries  (persisted at section boundaries)
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS section_summaries (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          person_id TEXT NOT NULL,
          section_id TEXT NOT NULL,
          section_title TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_section_summaries_session ON section_summaries(session_id, section_id);")

    # -----------------------------
    # Segment flags  (Track A — Safety)
    # Sensitive flags on individual answer/segment records
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS segment_flags (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          question_id TEXT,
          section_id TEXT,
          sensitive INTEGER NOT NULL DEFAULT 0,
          sensitive_category TEXT DEFAULT '',
          excluded_from_memoir INTEGER NOT NULL DEFAULT 1,
          private INTEGER NOT NULL DEFAULT 1,
          deleted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_segment_flags_session ON segment_flags(session_id);")
    # v6.2: UNIQUE constraint on (session_id, question_id) prevents duplicate flags on answer retry.
    # SQLite requires CREATE UNIQUE INDEX rather than ALTER TABLE ADD CONSTRAINT.
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_seg_flags_session_question "
        "ON segment_flags(session_id, question_id) WHERE question_id IS NOT NULL;"
    )

    # -----------------------------
    # WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — interview_threads.
    # Persistent thread bank for unresolved story doors. Schema mirror
    # of server/code/db/migrations/0009_interview_threads.sql. Idempotent
    # CREATE TABLE IF NOT EXISTS so cold-start builds the table without
    # the migrations runner.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_threads (
            id                  TEXT PRIMARY KEY,
            session_id          TEXT NOT NULL,
            tenant_id           TEXT DEFAULT 'default',
            thread_anchor       TEXT NOT NULL,
            source_turn_index   INTEGER DEFAULT 0,
            source_excerpt      TEXT DEFAULT '',
            introduced_at       TEXT NOT NULL,
            status              TEXT DEFAULT 'open',
            surfaced_at         TEXT,
            resolved_at         TEXT,
            category            TEXT DEFAULT '',
            FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_threads_session_status "
        "ON interview_threads(session_id, status);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_threads_introduced_at "
        "ON interview_threads(introduced_at);"
    )

    # -----------------------------
    # WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A
    # Universal bio gap map. Two tables: bio_fields (schema definition)
    # and bio_facts (per-narrator filled values). Schema mirror of
    # server/code/db/migrations/0011_bio_fields_facts.sql. Idempotent
    # CREATE TABLE IF NOT EXISTS so cold-start builds the tables without
    # the migrations runner; migration 0011 holds the canonical
    # archeological record.
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bio_fields (
            id                  TEXT PRIMARY KEY,
            field_key           TEXT NOT NULL UNIQUE,
            field_label         TEXT NOT NULL,
            field_category      TEXT NOT NULL,
            field_type          TEXT NOT NULL,
            narrative_value     TEXT NOT NULL DEFAULT 'medium',
            life_stage_range    TEXT NOT NULL DEFAULT 'all',
            asking_anchors      TEXT NOT NULL DEFAULT '[]',
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bio_fields_category "
        "ON bio_fields(field_category);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bio_fields_narrative_value "
        "ON bio_fields(narrative_value);"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bio_facts (
            id                            TEXT PRIMARY KEY,
            tenant_id                     TEXT NOT NULL DEFAULT 'default',
            narrator_id                   TEXT NOT NULL,
            field_key                     TEXT NOT NULL,
            value                         TEXT NOT NULL DEFAULT '""',
            status                        TEXT NOT NULL DEFAULT 'empty',
            source                        TEXT NOT NULL DEFAULT '{}',
            confidence                    REAL NOT NULL DEFAULT 0.0,
            chapter_continuation_metric   TEXT,
            conflict_with                 TEXT,
            created_at                    TEXT NOT NULL,
            last_updated                  TEXT NOT NULL,
            FOREIGN KEY (field_key) REFERENCES bio_fields(field_key)
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bio_facts_narrator_field "
        "ON bio_facts(narrator_id, field_key);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bio_facts_narrator_status "
        "ON bio_facts(narrator_id, status);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bio_facts_status "
        "ON bio_facts(status);"
    )

    # -----------------------------
    # WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A consent ledger.
    # One row per attestation event so consent state has a proper audit
    # trail (timestamp + which operator checked the box, if attestation
    # happened on the narrator's behalf). Schema mirror of migration
    # 0013_narrator_intake.sql; CREATE TABLE IF NOT EXISTS so cold-start
    # builds the table without the migrations runner.
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS consent_attestations (
            id TEXT PRIMARY KEY,
            narrator_id TEXT NOT NULL,
            attestation_type TEXT NOT NULL,
            attested_at TEXT NOT NULL,
            checked_by_operator TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY (narrator_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_consent_attest_narrator "
        "ON consent_attestations(narrator_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_consent_attest_type "
        "ON consent_attestations(narrator_id, attestation_type);"
    )

    # Phase 1A people-column additions (pronouns, pronouns_other,
    # current_residence). SQLite ALTER TABLE ADD COLUMN is not
    # idempotent — it errors if the column already exists. Use
    # PRAGMA table_info to check first so cold-start + repeat
    # init_db calls don't crash.
    try:
        existing_cols = {
            row[1] for row in cur.execute(
                "PRAGMA table_info(people);"
            ).fetchall()
        }
        for col_name, col_def in (
            ("pronouns", "TEXT DEFAULT ''"),
            ("pronouns_other", "TEXT DEFAULT ''"),
            ("current_residence", "TEXT DEFAULT ''"),
        ):
            if col_name not in existing_cols:
                cur.execute(
                    f"ALTER TABLE people ADD COLUMN {col_name} {col_def};"
                )
    except sqlite3.Error:
        # Non-fatal: drift-check downstream will surface any
        # missing columns clearly; we don't want init_db to die
        # on a column-add race.
        logger.exception(
            "people intake-column ALTER skipped (non-fatal)",
        )

    # -----------------------------
    # WO-LORI-SAFETY-INTEGRATION-01 Phase 3 — operator notification surface.
    # Persists every safety trigger as a discrete event for the operator
    # Bug Panel banner + between-session digest. Distinct from segment_flags
    # (which tracks memoir-inclusion lifecycle of sensitive answers); this
    # is the operator-awareness ledger.
    #
    # Per the spec: never narrator-visible, no scores, no severity ranks,
    # no longitudinal trends. Operator gets a flat list of "what fired,
    # when, and the matched phrase + 200-char excerpt for context".
    # acknowledged_at is set when the operator dismisses the banner.
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS safety_events (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          person_id TEXT,
          category TEXT NOT NULL DEFAULT '',
          matched_phrase TEXT,
          turn_excerpt TEXT,
          created_at TEXT NOT NULL,
          acknowledged_at TEXT,
          acknowledged_by TEXT
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_safety_events_session ON safety_events(session_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_safety_events_person ON safety_events(person_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_safety_events_created ON safety_events(created_at);")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_safety_events_unacked "
        "ON safety_events(acknowledged_at) WHERE acknowledged_at IS NULL;"
    )

    # -----------------------------
    # Affect events  (Track B — Emotion Signal)
    # Derived affect state events from browser MediaPipe pipeline
    # Never stores raw landmarks or raw emotion labels
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS affect_events (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          section_id TEXT DEFAULT '',
          affect_state TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.0,
          duration_ms INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT 'camera',
          ts TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_affect_events_session_ts ON affect_events(session_id, ts);")

    # -----------------------------
    # Migrate interview_sessions: add softened mode columns if missing
    # -----------------------------
    existing_isess_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(interview_sessions);").fetchall()
    }
    softened_cols = {
        "interview_softened": "ALTER TABLE interview_sessions ADD COLUMN interview_softened INTEGER DEFAULT 0;",
        "softened_until_turn": "ALTER TABLE interview_sessions ADD COLUMN softened_until_turn INTEGER DEFAULT 0;",
        "turn_count": "ALTER TABLE interview_sessions ADD COLUMN turn_count INTEGER DEFAULT 0;",
        # WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14) — tag the
        # trigger so the read-side can pick the right prompt block and
        # per-state word/question caps. Values: "acute" (988-dispatch
        # path, default N=5), "past_tense_acknowledge" (memoir past-
        # tense ideation, default N=2), or "" / NULL for legacy rows.
        "softened_trigger": "ALTER TABLE interview_sessions ADD COLUMN softened_trigger TEXT DEFAULT '';",
        # The N value the caller passed when softened was set. Stored
        # for telemetry + nested-trigger arithmetic; not strictly
        # required for read-side state computation (which uses
        # turn_count vs softened_until_turn) but useful for surface
        # diagnostics in the operator panel.
        "softened_initial_n": "ALTER TABLE interview_sessions ADD COLUMN softened_initial_n INTEGER DEFAULT 0;",
    }
    for col_name, alter_sql in softened_cols.items():
        if col_name not in existing_isess_cols:
            cur.execute(alter_sql)

    _ensure_phase_g_tables(con, cur)
    _ensure_phase_q1_tables(con, cur)

    # -----------------------------
    # WO-13 Phase 1 — Family Truth tables (Shadow Archive + Proposal + Promoted)
    #
    # family_truth_notes : append-only raw shadow archive (freeform body a user
    #                      or the extractor dropped in, never promoted directly)
    # family_truth_rows  : structured proposals that may be approved / qualified
    #                      / flagged for verify / kept as source-only / rejected.
    #                      Promoted truth = rows with status in ('approve','approve_q').
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS family_truth_notes (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          body TEXT NOT NULL,
          source_kind TEXT NOT NULL DEFAULT 'chat',
          source_ref TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          created_by TEXT NOT NULL DEFAULT 'system',
          review_locked INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ft_notes_person ON family_truth_notes(person_id, created_at);"
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS family_truth_rows (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          note_id TEXT,
          subject_name TEXT NOT NULL DEFAULT '',
          relationship TEXT NOT NULL DEFAULT '',
          field TEXT NOT NULL,
          source_says TEXT NOT NULL DEFAULT '',
          approved_value TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'needs_verify',
          qualification TEXT NOT NULL DEFAULT '',
          reviewer TEXT NOT NULL DEFAULT '',
          reviewed_at TEXT NOT NULL DEFAULT '',
          confidence REAL NOT NULL DEFAULT 0.0,
          narrative_role TEXT NOT NULL DEFAULT '',
          meaning_tags TEXT NOT NULL DEFAULT '[]',
          provenance TEXT NOT NULL DEFAULT '{}',
          legacy_suspect INTEGER NOT NULL DEFAULT 0,
          extraction_method TEXT NOT NULL DEFAULT '',
          source_fact_id TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
          FOREIGN KEY(note_id)  REFERENCES family_truth_notes(id) ON DELETE SET NULL
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ft_rows_person_status ON family_truth_rows(person_id, status);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ft_rows_subject_field ON family_truth_rows(person_id, subject_name, field);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ft_rows_note ON family_truth_rows(note_id);"
    )
    # Idempotency guard: a given legacy facts.id may only produce ONE backfilled row.
    # Uses a partial unique index so non-backfilled rows (source_fact_id='') are unconstrained.
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ft_rows_source_fact "
        "ON family_truth_rows(source_fact_id) WHERE source_fact_id <> '';"
    )

    # -----------------------------
    # WO-13 Phase 7 — Promoted Truth table.
    #
    # This is the FOURTH layer of the four-layer truth pipeline:
    #
    #   Shadow Archive (notes) → Proposal (rows) → Review → Promoted Truth
    #
    # Each record is the canonical value for one (person_id, subject_name,
    # field) triple. `ft_promote_row` UPSERTs into this table using that key
    # as the uniqueness constraint, so re-running a promotion on an identical
    # row is a true no-op (same values → same hash → updated_at not touched).
    #
    # Rules enforced at promotion time:
    #   - Protected identity fields coming from `rules_fallback` are refused.
    #   - Reference narrators are refused upstream by the router's 403 guard.
    #   - Only rows with status IN ('approve','approve_q') are eligible.
    # -----------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS family_truth_promoted (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          subject_name TEXT NOT NULL DEFAULT '',
          relationship TEXT NOT NULL DEFAULT 'self',
          field TEXT NOT NULL,
          value TEXT NOT NULL DEFAULT '',
          qualification TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'approve',
          source_row_id TEXT NOT NULL DEFAULT '',
          source_note_id TEXT NOT NULL DEFAULT '',
          source_says TEXT NOT NULL DEFAULT '',
          extraction_method TEXT NOT NULL DEFAULT '',
          confidence REAL NOT NULL DEFAULT 0.0,
          reviewer TEXT NOT NULL DEFAULT '',
          content_hash TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    # The PRIMARY uniqueness key for promoted truth. Enforces one row per
    # (person, subject, field). ON CONFLICT DO UPDATE keyed off this index.
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ft_promoted_subject_field "
        "ON family_truth_promoted(person_id, subject_name, field);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ft_promoted_person "
        "ON family_truth_promoted(person_id, updated_at);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ft_promoted_source_row "
        "ON family_truth_promoted(source_row_id);"
    )

    # One-time (idempotent) backfill of legacy facts rows into family_truth_rows.
    _wo13_backfill_facts_to_family_truth_rows(con, cur)

    con.commit()

    # WO-LORI-PHOTO-SHARED-01 — apply post-legacy migrations in
    # server/code/db/migrations/*.sql. Runner is idempotent (tracked in
    # schema_migrations). Kept AFTER the legacy CREATE TABLE block so any
    # failure here never truncates the pre-WO schema.
    #
    # 2026-06-17 — robust import cascade. Production runs init_db via
    # `from server.code.api import db` so `..db.migrations_runner`
    # resolves cleanly. The unit test suite imports `api.db` as a
    # top-level module (sys.path tweak) and the relative-2-up form
    # raises `ImportError: attempted relative import beyond top-level
    # package`. That swallowed the runner silently and left fresh test
    # DBs without the post-0001 migrations applied — surfaced as
    # "table story_candidates has no column named language" across
    # ~22 story_preservation tests. Cascade: try the original relative
    # form, then the absolute form, then load by on-disk file path.
    try:
        run_pending_migrations = None
        try:
            from ..db.migrations_runner import run_pending_migrations  # type: ignore
        except (ImportError, ValueError):
            try:
                from server.code.db.migrations_runner import (  # type: ignore
                    run_pending_migrations,
                )
            except ImportError:
                import importlib.util as _ilu
                from pathlib import Path as _P
                _rp = (
                    _P(__file__).resolve().parent.parent
                    / "db" / "migrations_runner.py"
                )
                _spec = _ilu.spec_from_file_location(
                    "_hornelore_migrations_runner_fallback", _rp,
                )
                if _spec is None or _spec.loader is None:
                    raise ImportError(
                        f"migrations_runner not loadable at {_rp}"
                    )
                _mod = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                run_pending_migrations = _mod.run_pending_migrations
        # 2026-07-23 (Bucket C.1) — pre-migration orphan visibility
        # for 0034_trips_person_id_fk. The migration itself DELETEs
        # orphan trips (rows whose person_id has no matching
        # people.id) as part of its table rebuild — the FK constraint
        # it adds would otherwise reject them. Logging the count
        # BEFORE we apply the migration is the only way to give an
        # operator an honest record of which orphans got cleaned up
        # (the post-migration DB has no trace of them). Skipped
        # silently if 0034 has already been applied, if the trips
        # table doesn't exist yet (fresh DB — schema_migrations
        # tracking table catches this), or if any query in this
        # block raises (defensive — this is diagnostic-only, must
        # not block boot).
        try:
            # Guard against pre-migration-tracking-table state:
            # schema_migrations is created by the runner's
            # _ensure_tracking_table pass, which hasn't run yet on
            # our first-ever init_db against a truly fresh DB. Only
            # proceed to check 0034 when the tracking table already
            # exists.
            _cur_tracking = con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='schema_migrations';"
            )
            _has_tracking = _cur_tracking.fetchone() is not None
            if not _has_tracking:
                _already_applied = True  # no runs yet, nothing to preflight
            else:
                _cur_check = con.execute(
                    "SELECT 1 FROM schema_migrations "
                    "WHERE filename = '0034_trips_person_id_fk.sql';"
                )
                _already_applied = _cur_check.fetchone() is not None
            if not _already_applied:
                _cur_tables = con.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name IN ('trips','people');"
                )
                _table_names = {row[0] for row in _cur_tables.fetchall()}
                if 'trips' in _table_names and 'people' in _table_names:
                    _cur_orphans = con.execute(
                        "SELECT COUNT(*) FROM trips t "
                        "LEFT JOIN people p ON t.person_id = p.id "
                        "WHERE p.id IS NULL;"
                    )
                    _orphan_count = _cur_orphans.fetchone()[0]
                    if _orphan_count > 0:
                        # Also surface the offending person_ids so the
                        # operator can grep api.log later if they
                        # want to know which fake ids leaked. Bounded
                        # at 10 to keep the log line readable.
                        _cur_ids = con.execute(
                            "SELECT DISTINCT t.person_id FROM trips t "
                            "LEFT JOIN people p ON t.person_id = p.id "
                            "WHERE p.id IS NULL "
                            "LIMIT 10;"
                        )
                        _sample_ids = [row[0] for row in _cur_ids.fetchall()]
                        logger.warning(
                            "[migrations] pre-0034: %d orphan trip(s) "
                            "will be DELETEd by 0034_trips_person_id_fk. "
                            "Sample owner ids (up to 10): %r",
                            _orphan_count, _sample_ids,
                        )
                    else:
                        logger.info(
                            "[migrations] pre-0034: 0 orphan trips; "
                            "FK migration will land clean.")
        except Exception:
            # Never block boot on the diagnostic log itself.
            logger.exception(
                "[migrations] pre-0034 orphan check failed "
                "(non-fatal — proceeding with migration)")

        run_pending_migrations(con)

        # WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 — post-0043
        # backfill skip report, the counterpart to the pre-0034 check
        # above and written to the same rule: report, never block boot.
        # Silent on a clean database; see the function's own docstring
        # for why that silence is the whole point of the 2026-08-12
        # correction.
        _report_0043_backfill_skips(con, str(DB_PATH))
    except Exception:
        logger.exception("Post-legacy migrations failed")
        con.close()
        raise

    # Patch B (2026-04-30 polish): post-migration schema-drift sanity
    # check. Catches the case where an operator hand-created a table
    # with a different shape and the CREATE TABLE IF NOT EXISTS in the
    # migration silently did nothing — INSERTs would later crash with
    # cryptic "no such column" errors. We log a clear ERROR at boot
    # rather than crash so the operator sees the drift before any user
    # request comes in. Add new tables to _CRITICAL_SCHEMA below as new
    # WOs land.
    try:
        _assert_critical_schemas(con)
    except Exception:
        # Never crash boot on the drift check itself. The check is
        # informational; the cryptic INSERT-time error is the
        # backstop.
        logger.exception("Schema-drift check failed (non-fatal)")

    # WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A seed load.
    #
    # init_db is called from every db accessor; this seed loader is
    # idempotent (UPSERTs ~67 rows) but cost-prohibitive to run on
    # every CRUD call. Gate behind a module-level "ran once" flag so
    # the seed lands at the first DB touch of the process and is
    # skipped thereafter.
    #
    # WHY THIS IS LOAD-BEARING:
    # PRAGMA foreign_keys=ON (line ~60) means bio_facts.field_key FK
    # to bio_fields.field_key is enforced. Without the seed, EVERY
    # bio_fact_create() — Tier 1 / Tier 2 / Tier 3 / Tier 4 — would
    # fail with FOREIGN KEY constraint failed. The seed loader is
    # therefore not "would be nice" archaeological metadata; it's a
    # hard prerequisite for bio_builder to function.
    #
    # RECURSION GUARD (2026-06-15 fix):
    # The flag MUST be set BEFORE calling bio_schema_seed_load_to_db,
    # not after. Setting it after produces a catastrophic infinite
    # recursion: the loader iterates rows and calls bio_field_upsert,
    # which calls init_db() at the top (every accessor does), which
    # re-enters this block with the flag still False, which calls the
    # loader again, ad infinitum. RecursionError eventually fires,
    # gets caught + logged, and the seed never actually lands —
    # bio_fields stays empty and every bio_builder write FK-fails.
    #
    # Setting the flag FIRST breaks the recursion: the reentrant
    # init_db calls see the flag as True and skip the seed block
    # entirely, letting bio_field_upsert finish its INSERT/UPDATE
    # against the schema that init_db already built earlier in this
    # call. If the seed loader raises (genuine data error, not
    # recursion), we leave the flag True — better than retrying a
    # failing seed on every chat turn — but log the failure loudly.
    #
    # Failure here is logged but non-fatal — the rest of init_db
    # completed successfully and non-bio routes continue to work.
    # Bio routes will surface FK errors at write time, which is
    # exactly the failure mode this guard prevents under normal
    # circumstances.
    global _BIO_SEED_LOADED
    if not _BIO_SEED_LOADED:
        # CRITICAL: set the flag FIRST so reentrant init_db calls from
        # inside bio_schema_seed_load_to_db skip this block. See the
        # RECURSION GUARD note above.
        _BIO_SEED_LOADED = True
        try:
            n = bio_schema_seed_load_to_db()
            logger.info(
                "[bio_schema] seed loaded %d fields at first init_db()", n,
            )
        except Exception:
            logger.exception(
                "Bio schema seed load failed (non-fatal; bio_builder "
                "writes will fail at FK enforcement until resolved)",
            )

    con.close()


# Patch B (2026-04-30 polish) — schema-drift sanity table.
# Maps table name → set of column names that must be present for the
# accessor functions to work. Subset of full schema is fine; we only
# verify columns the INSERT statements reference.
_CRITICAL_SCHEMA: Dict[str, set] = {
    "story_candidates": {
        "id", "narrator_id", "transcript", "audio_clip_path",
        "audio_duration_sec", "word_count", "trigger_reason",
        "scene_anchor_count", "era_candidates", "age_bucket",
        "estimated_year_low", "estimated_year_high", "confidence",
        "scene_anchors", "extraction_status", "extracted_fields",
        "review_status", "review_notes", "reviewed_at", "reviewed_by",
        "session_id", "conversation_id", "turn_id", "created_at",
        # WO-ML-03B Phase 3 multilingual (2026-05-07) — added by
        # migration 0006_story_candidates_language.sql.
        "language", "language_probability",
    },
}


def _assert_critical_schemas(con: sqlite3.Connection) -> None:
    """Verify each critical table has at least the columns the
    accessor INSERTs reference. Logs ERROR on drift; does NOT raise."""
    for table_name, expected_cols in _CRITICAL_SCHEMA.items():
        cur = con.execute(f"PRAGMA table_info({table_name});")
        actual_cols = {row[1] for row in cur.fetchall()}
        if not actual_cols:
            # Table doesn't exist yet — migration didn't apply or
            # was deferred. Migration runner already logs that.
            continue
        missing = expected_cols - actual_cols
        if missing:
            logger.error(
                "[init_db] schema drift on %s: missing columns %s "
                "(actual=%s) — INSERTs will fail with cryptic errors. "
                "Inspect the live table or re-run migrations.",
                table_name,
                sorted(missing),
                sorted(actual_cols),
            )


# -----------------------------------------------------------------------------
# Sessions / turns (UI + SSE + WS)
# -----------------------------------------------------------------------------
def new_conv_id() -> str:
    return _uuid()


class SessionOwnerConflict(Exception):
    """A session already owned by narrator A was claimed for narrator B.

    Supervisor requirement (2026-08-16): *"If a session is already owned
    by narrator A, a later call for narrator B must fail -- not silently
    replace the owner."* Keeping A quietly would also have been a silent
    resolution of a contradiction, and the contradiction is the
    information. A conversation does not change narrators, so this is a
    bug to surface at the moment it happens, while the caller is still
    on the stack.
    """

    def __init__(self, conv_id: str, stored_person_id: str, incoming_person_id: str):
        self.conv_id = conv_id
        self.stored_person_id = stored_person_id
        self.incoming_person_id = incoming_person_id
        super().__init__(
            f"session {conv_id} is owned by {stored_person_id}; "
            f"refusing to reassign it to {incoming_person_id}"
        )


def _assert_session_owner(con, conv_id: str, incoming: Optional[str]) -> None:
    """Raise if `incoming` contradicts a recorded owner. Silent when it agrees."""
    if not incoming:
        return
    row = con.execute(
        "SELECT person_id FROM sessions WHERE conv_id=?;", (conv_id,)
    ).fetchone()
    if not row:
        return
    stored = (row["person_id"] or "").strip()
    if stored and stored != incoming:
        raise SessionOwnerConflict(conv_id, stored, incoming)


def ensure_session(conv_id: str, title: str = "", person_id: Optional[str] = None) -> None:
    """Create or touch a chat session row, recording who it belongs to.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 2 (2026-08-16), R2.3/R2.4.

    ``person_id`` is new. Until this commit the signature could not
    express ownership at all, which is why every row on the live
    WebSocket path was written with ``payload_json='{}'`` even though
    ``chat_ws`` had the narrator id in hand and was passing it to
    ``archive_ensure_session`` and ``ensure_interview_session`` for the
    very same ``conv_id``.

    OWNERSHIP IS WRITTEN ONCE AND NEVER SILENTLY CHANGED. A NULL
    incoming id never clears an existing owner
    (``COALESCE(sessions.person_id, excluded.person_id)``), and a
    DIFFERENT incoming id raises ``SessionOwnerConflict`` rather than
    replacing -- or quietly discarding -- either value. A conversation
    does not change narrators, so a collision is information, and
    resolving it silently in either direction destroys that
    information.

    ``payload_json`` is untouched. The legacy JSON key stays readable
    forever -- demoted, not deleted (see ``_session_owner_sql``).
    """
    init_db()
    con = _connect()
    now = _now_iso()
    pid = (person_id or "").strip() or None
    try:
        _assert_session_owner(con, conv_id, pid)
    except Exception:
        con.close()
        raise
    con.execute(
        """
        INSERT INTO sessions(conv_id,title,updated_at,payload_json,person_id,person_id_source)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(conv_id) DO UPDATE SET
          title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE sessions.title END,
          updated_at=excluded.updated_at,
          person_id=COALESCE(sessions.person_id, excluded.person_id),
          person_id_source=COALESCE(sessions.person_id_source, excluded.person_id_source);
        """,
        (conv_id, title or "", now, "{}", pid, "explicit" if pid else None),
    )
    con.commit()
    con.close()


def upsert_session(
    conv_id: str,
    title: str,
    payload: Dict[str, Any],
    person_id: Optional[str] = None,
) -> None:
    """Replace a session's payload. Ownership follows the same
    write-once rule as ``ensure_session`` (R2.4).

    When no ``person_id`` is passed explicitly the payload is consulted,
    accepting either historical key. ``app.js`` has always written
    ``person_id`` while the only reader looked for ``active_person_id``;
    both are honoured here so that mismatch stops costing attribution.
    """
    init_db()
    con = _connect()
    now = _now_iso()
    body = payload or {}
    pid = (person_id or body.get("active_person_id") or body.get("person_id") or "")
    pid = str(pid).strip() or None
    try:
        _assert_session_owner(con, conv_id, pid)
    except Exception:
        con.close()
        raise
    con.execute(
        """
        INSERT INTO sessions(conv_id,title,updated_at,payload_json,person_id,person_id_source)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(conv_id) DO UPDATE SET
          title=excluded.title,
          updated_at=excluded.updated_at,
          payload_json=excluded.payload_json,
          person_id=COALESCE(sessions.person_id, excluded.person_id),
          person_id_source=COALESCE(sessions.person_id_source, excluded.person_id_source);
        """,
        (conv_id, title or "", now, _json_dump(body), pid, "explicit" if pid else None),
    )
    con.commit()
    con.close()


def get_session_payload(conv_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    row = con.execute(
        "SELECT conv_id,title,updated_at,payload_json,person_id FROM sessions WHERE conv_id=?;",
        (conv_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    payload = _json_load(row["payload_json"], {})
    payload.setdefault("conv_id", row["conv_id"])
    payload.setdefault("title", row["title"] or "")
    payload.setdefault("updated_at", row["updated_at"] or "")
    # R2.5 — the column is the authority, and it is surfaced ONLY when an
    # owner is actually known.
    #
    # An earlier cut of this wrote `payload["person_id"] = owner or None`
    # unconditionally. That is a regression, and the offline gate caught
    # it: `prompt_composer` serialises this dict into the composed
    # prompt's trailing PROFILE_JSON blob, so every ownerless session --
    # which is every legacy row, including the shared "default" one --
    # started emitting `PROFILE_JSON: {"person_id": null}` into Lori's
    # system prompt. A read helper must not change what the composer
    # says. Callers wanting the owner alone use get_session_owner().
    owner = row["person_id"] or payload.get("active_person_id") or payload.get("person_id") or ""
    if owner:
        payload.setdefault("person_id", owner)
        payload.setdefault("active_person_id", owner)
    return payload


def get_session_owner(conv_id: str) -> Optional[str]:
    """The narrator a session belongs to, or None when unrecorded.

    R2.5. Resolution order: the `sessions.person_id` column added by
    0044, then `$.active_person_id` (the key the legacy reader expected),
    then `$.person_id` (the key `app.js` has actually been writing). None
    means "owner not recorded" -- which is the truthful answer for every
    row written before 0044, and is never upgraded to a guess.
    """
    init_db()
    con = _connect()
    try:
        row = con.execute(
            "SELECT payload_json, person_id FROM sessions WHERE conv_id=?;", (conv_id,)
        ).fetchone()
        if not row:
            return None
        if (row["person_id"] or "").strip():
            return row["person_id"]
        payload = _json_load(row["payload_json"], {}) or {}
        return payload.get("active_person_id") or payload.get("person_id") or None
    finally:
        con.close()


# WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2 Part C (2026-08-17).
#
# Why an unowned row was NOT backfilled by 0045, reported as the FIRST
# condition it failed, in the migration's own evaluation order. Reporting
# the first failure rather than every failure keeps the buckets mutually
# exclusive, so they sum to `sessions_unowned` and a reader can add them
# up and get the right answer.
_RESIDUE_UNOWNED_BUCKETS = (
    # Two structured fields contradicting each other. 0045 declines.
    "legacy_fields_disagree",
    # A structured id that points at no row in `people`.
    "legacy_id_invalid",
    # A stronger recorded link names two narrators, or names one that the
    # payload contradicts. Either way the payload does not get to decide.
    "stronger_source_ambiguous_or_conflicting",
    # No structured owner anywhere: '{}', invalid JSON, or a payload with
    # neither key. This is the honest remainder and it is expected to be
    # the largest bucket.
    "no_recorded_link",
)


def session_ownership_residue() -> Dict[str, Any]:
    """What narrator deletion cannot reach, counted rather than implied.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 2, R2.5, extended by
    Phase 2 Part C. A narrator hard-delete removes the sessions it OWNS
    (and their turns, via the existing cascade off ``sessions(conv_id)``).
    It deliberately does not touch rows whose owner was never recorded --
    deleting those would mean guessing, and guessing is the thing this
    lane exists to stop.

    So there is a residue, and this reports it in five parts, which is
    the shape Phase 2 asks for:

    * ``owner_explicit`` -- a writer recorded the narrator at the time.
    * ``owner_recovered_legacy_payload`` -- 0045 promoted one structured,
      unambiguous, existing id out of ``payload_json``.
    * ``owner_source_unrecorded`` -- owned, but provenance predates the
      ``person_id_source`` column. This covers every row 0044 recovered
      and every row written before Phase 2. It is NOT folded into either
      category above, because deciding after the fact which one it was
      would be exactly the reconstruction this lane forbids.
    * the four ``unowned_*`` buckets -- why each remaining row was
      declined, one bucket per row, summing to ``sessions_unowned``.
    * ``turns_in_unowned_sessions`` -- the conversation content that
      therefore cannot be attributed or deleted by narrator.

    The numbers are meant to be looked at, not fixed by inference.
    """
    init_db()
    con = _connect()
    try:
        def _one(sql: str) -> int:
            row = con.execute(sql).fetchone()
            return int(row[0] if row else 0)

        unowned = _one(
            "SELECT COUNT(*) FROM sessions WHERE person_id IS NULL OR TRIM(person_id)=''"
        )
        owned = _one(
            "SELECT COUNT(*) FROM sessions "
            "WHERE person_id IS NOT NULL AND TRIM(person_id)<>''"
        )
        orphan_turns = _one(
            "SELECT COUNT(*) FROM turns t JOIN sessions s ON s.conv_id=t.conv_id "
            "WHERE s.person_id IS NULL OR TRIM(s.person_id)=''"
        )
        legacy_json = _one(
            "SELECT COUNT(*) FROM sessions "
            "WHERE (person_id IS NULL OR TRIM(person_id)='') "
            "AND json_valid(payload_json) "
            "AND COALESCE(json_extract(payload_json,'$.active_person_id'),"
            "json_extract(payload_json,'$.person_id')) IS NOT NULL"
        )

        by_source: Dict[str, int] = {
            "owner_explicit": 0,
            "owner_recovered_legacy_payload": 0,
            "owner_source_unrecorded": 0,
        }
        for row in con.execute(
            "SELECT person_id_source AS src, COUNT(*) AS n FROM sessions "
            "WHERE person_id IS NOT NULL AND TRIM(person_id)<>'' "
            "GROUP BY person_id_source;"
        ).fetchall():
            src = (row["src"] or "").strip()
            if src == "explicit":
                by_source["owner_explicit"] += int(row["n"])
            elif src == "legacy_payload_json":
                by_source["owner_recovered_legacy_payload"] += int(row["n"])
            else:
                # An unrecognised marker is not silently promoted into a
                # category it did not claim.
                by_source["owner_source_unrecorded"] += int(row["n"])

        buckets: Dict[str, int] = {name: 0 for name in _RESIDUE_UNOWNED_BUCKETS}
        rows = con.execute(
            """
            SELECT
              CASE WHEN json_valid(s.payload_json)
                   THEN TRIM(COALESCE(json_extract(s.payload_json,'$.person_id'),''))
                   ELSE '' END AS lp,
              CASE WHEN json_valid(s.payload_json)
                   THEN TRIM(COALESCE(json_extract(s.payload_json,'$.active_person_id'),''))
                   ELSE '' END AS lap,
              (
                SELECT COUNT(DISTINCT x.pid) FROM (
                    SELECT isx.person_id AS pid FROM interview_sessions isx
                     WHERE isx.id = s.conv_id AND isx.person_id IS NOT NULL
                       AND TRIM(isx.person_id) <> ''
                    UNION
                    SELECT mas.person_id FROM memory_archive_sessions mas
                     WHERE mas.conv_id = s.conv_id AND mas.person_id IS NOT NULL
                       AND TRIM(mas.person_id) <> ''
                    UNION
                    SELECT json_extract(t.meta_json,'$.person_id') FROM turns t
                     WHERE t.conv_id = s.conv_id AND json_valid(t.meta_json)
                       AND json_extract(t.meta_json,'$.person_id') IS NOT NULL
                       AND TRIM(json_extract(t.meta_json,'$.person_id')) <> ''
                ) x
              ) AS stronger_count,
              (
                SELECT MIN(x.pid) FROM (
                    SELECT isx.person_id AS pid FROM interview_sessions isx
                     WHERE isx.id = s.conv_id AND isx.person_id IS NOT NULL
                       AND TRIM(isx.person_id) <> ''
                    UNION
                    SELECT mas.person_id FROM memory_archive_sessions mas
                     WHERE mas.conv_id = s.conv_id AND mas.person_id IS NOT NULL
                       AND TRIM(mas.person_id) <> ''
                    UNION
                    SELECT json_extract(t.meta_json,'$.person_id') FROM turns t
                     WHERE t.conv_id = s.conv_id AND json_valid(t.meta_json)
                       AND json_extract(t.meta_json,'$.person_id') IS NOT NULL
                       AND TRIM(json_extract(t.meta_json,'$.person_id')) <> ''
                ) x
              ) AS stronger_id
              FROM sessions s
             WHERE s.person_id IS NULL OR TRIM(s.person_id) = '';
            """
        ).fetchall()

        known_people = {
            r["id"] for r in con.execute("SELECT id FROM people;").fetchall()
        }
        for r in rows:
            lp = (r["lp"] or "").strip()
            lap = (r["lap"] or "").strip()
            candidate = lp or lap
            stronger_count = int(r["stronger_count"] or 0)
            stronger_id = (r["stronger_id"] or "").strip()
            if lp and lap and lp != lap:
                buckets["legacy_fields_disagree"] += 1
            elif not candidate:
                buckets["no_recorded_link"] += 1
            elif candidate not in known_people:
                buckets["legacy_id_invalid"] += 1
            elif stronger_count > 1 or (stronger_count == 1 and stronger_id != candidate):
                buckets["stronger_source_ambiguous_or_conflicting"] += 1
            else:
                # A resolvable candidate that survived every condition and
                # is still unowned means 0045 has not been applied to this
                # database yet. Truthful, and it is the number that should
                # drop to zero after the migration runs.
                buckets["no_recorded_link"] += 1

        out: Dict[str, Any] = {
            "sessions_total": owned + unowned,
            "sessions_owned": owned,
            "sessions_unowned": unowned,
            "turns_in_unowned_sessions": orphan_turns,
            # Retained verbatim from commit 2 so existing readers of this
            # dict keep working; the buckets below are the finer answer.
            "unowned_but_legacy_json_has_an_id": legacy_json,
        }
        out.update(by_source)
        out.update({"unowned_" + name: buckets[name] for name in _RESIDUE_UNOWNED_BUCKETS})
        return out
    finally:
        con.close()


def count_sessions_without_owner() -> int:
    """How many session rows still have no recorded narrator.

    R2.6/§4.4 of the work order: this number is REPORTED, never reduced
    by inference. It exists so the honest answer is cheap to obtain.
    """
    init_db()
    con = _connect()
    try:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE person_id IS NULL OR person_id='';"
        ).fetchone()
        return int(row["n"] if row else 0)
    finally:
        con.close()


def get_session(conv_id: str) -> Optional[Dict[str, Any]]:
    """Back-compat shim for api.py and older callers."""
    return get_session_payload(conv_id)


def list_sessions(limit: int = 50, person_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    if person_id:
        # R2.5 — the sidebar can finally scope to one narrator. Legacy
        # JSON keys are honoured so rows written before 0044 are not
        # invisible under a filter.
        #
        # THE json_valid GUARDS ARE LOAD-BEARING, added by Phase 2 Part C
        # (2026-08-17). `json_extract` on malformed JSON is not NULL in
        # SQLite -- it RAISES `OperationalError: malformed JSON` -- and it
        # raises for the whole statement, so ONE junk historical row makes
        # this endpoint 500 for EVERY narrator, not just for that row's.
        #
        # `payload_json` is exactly the column where junk is plausible:
        # it is browser-supplied state that has been persisted verbatim
        # for the life of the table. Migration 0045 and
        # session_ownership_residue() both guard it for that reason;
        # until this change `list_sessions` was the one reader that did
        # not, which made it the one reader that could take the endpoint
        # down.
        #
        # A row whose payload cannot be parsed is simply not attributable
        # by the legacy fallback. It is skipped, never guessed at, and it
        # remains visible in the unfiltered listing.
        rows = con.execute(
            "SELECT conv_id,title,updated_at,person_id FROM sessions "
            "WHERE COALESCE(NULLIF(person_id,''), "
            "CASE WHEN json_valid(payload_json) "
            "THEN json_extract(payload_json,'$.active_person_id') END, "
            "CASE WHEN json_valid(payload_json) "
            "THEN json_extract(payload_json,'$.person_id') END) = ? "
            "ORDER BY updated_at DESC LIMIT ?;",
            (person_id, int(limit)),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT conv_id,title,updated_at,person_id FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?;",
            (int(limit),),
        ).fetchall()
    con.close()
    # R2.5 — person_id is surfaced so the sidebar can finally filter by
    # narrator. None means "owner not recorded", which is the truthful
    # answer for every row written before migration 0044.
    return [
        {
            "conv_id": r["conv_id"],
            "title": r["title"] or "",
            "updated_at": r["updated_at"] or "",
            "person_id": r["person_id"] or None,
        }
        for r in rows
    ]


def delete_session(conv_id: str) -> None:
    init_db()
    con = _connect()
    con.execute("DELETE FROM turns WHERE conv_id=?;", (conv_id,))
    con.execute("DELETE FROM sessions WHERE conv_id=?;", (conv_id,))
    con.commit()
    con.close()


def add_turn(
    conv_id: str,
    role: str,
    content: str,
    ts: Optional[str] = None,
    anchor_id: str = "",
    meta: Optional[Dict[str, Any]] = None,
    person_id: Optional[str] = None,
) -> None:
    """Append one turn row.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3 (2026-08-16): the
    supervisor list of creation paths that must carry ownership includes
    this one. It is the sibling writer to ``persist_turn_transaction``
    and it creates `sessions` rows too, so leaving it out would have left
    a second way to mint an ownerless session.

    If ``person_id`` is omitted but ``meta`` carries one, that is used --
    a recorded fact from the caller, not an inference.
    """
    init_db()
    owner = (person_id or (meta or {}).get("person_id") or "") or None
    ensure_session(conv_id, person_id=owner)
    con = _connect()
    ts = ts or _now_iso()
    con.execute(
        "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) VALUES(?,?,?,?,?,?);",
        (conv_id, role, content, ts, anchor_id or "", _json_dump(meta or {})),
    )
    con.execute("UPDATE sessions SET updated_at=? WHERE conv_id=?;", (ts, conv_id))
    con.commit()
    con.close()


def export_turns(conv_id: str) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    rows = con.execute(
        "SELECT role,content,ts,anchor_id,meta_json FROM turns WHERE conv_id=? ORDER BY ts ASC, id ASC;",
        (conv_id,),
    ).fetchall()
    con.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "role": r["role"],
                "content": r["content"],
                "timestamp": r["ts"],
                "anchor_id": r["anchor_id"] or "",
                "meta": _json_load(r["meta_json"], {}),
            }
        )
    return out


def clear_turns(conv_id: str) -> int:
    """WO-2: Delete all turns for a conversation, returning count deleted."""
    init_db()
    con = _connect()
    cur = con.execute("DELETE FROM turns WHERE conv_id=?;", (conv_id,))
    con.commit()
    n = cur.rowcount
    con.close()
    return n


def persist_turn_transaction(
    conv_id: str,
    user_message: str,
    assistant_message: str,
    model_name: str = "",
    meta: Optional[dict] = None,
    row_ids_out: Optional[dict] = None,
    *,
    is_system_directive: bool = False,
    person_id: Optional[str] = None,
    story_capture_decision: Optional[dict] = None,
) -> Optional[int]:
    """Commit one user+assistant turn pair. Returns the assistant rowid.

    WO-LORI-STORY-CAPTURE-DECISION-DURABILITY-01 (Phase 4, 2026-09-05) --
    the optional keyword-only `story_capture_decision` was added here.
    Neither the return value nor any existing behaviour changed.

    It rides on the USER row's `meta_json` because the record explains
    what the narrator said, and because that row is the only thing every
    evaluated turn has: a DECLINED turn creates no `story_candidates`
    row, so a side table would need its own lifecycle and its own
    deletion path. Here the record commits inside this same transaction,
    cannot be orphaned from the turn it describes, and disappears through
    the turn/session/narrator deletion that already exists.

    **The transcript is already on this row and is NOT copied into the
    record.** The decision object carries measurements and an exception
    class name; `story_trigger.validate_story_capture_decision` re-checks
    that before the transaction opens, so a malformed or over-wide record
    fails loudly rather than committing.

    When the argument is absent this function behaves exactly as before,
    which is what keeps every existing call site byte-equivalent.

    WO-TRUTH-PIPELINE-01 Phase 2 (2026-07-30) -- the signature was
    ``-> None`` until this date. It stopped being true when Phase 2
    needed a stable idempotency key for turn-scoped field extraction.

    The `turns` table carries no `turn_id` column (cols: id, conv_id,
    role, content, ts, anchor_id, meta_json), and adding one is a wider
    schema change than this phase should make. The assistant row's
    AUTOINCREMENT `id` is already a stable, committed, per-turn
    identifier -- so it is returned rather than invented. Callers that
    need turn-scoped idempotency build their key from it
    (``turnrow:<id>``); everything downstream keys off a row that
    definitely exists rather than off a hash of the narrator's words.

    All pre-Phase-2 call sites ignore the return value, so returning an
    int instead of None is behaviour-preserving for them. Returns None
    only if sqlite declines to report a lastrowid, which it does not do
    for a successful INSERT into an INTEGER PRIMARY KEY table -- callers
    must still treat None as "no stable key available" and skip
    turn-scoped work rather than fabricate one.

    WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 (2026-07-30) -- the
    optional `row_ids_out` dict was added here. The return value did
    NOT change; the paragraph above still stands exactly as written.

    The trip timeline shows a conversation moment, which means both
    sides of it: what the narrator said and what Lori said back. It
    reads that text out of `turns` by row id and never stores a copy,
    so it needs the USER row id as well as the assistant one. That id
    existed inside this transaction and was thrown away.

    It is handed back through a caller-supplied dict rather than by
    widening the return type to a tuple, because eleven call sites in
    chat_ws.py already call this function for its side effect and one
    calls it for its int. Changing the return type a second time would
    break all of them to serve one. Callers that want the pair pass
    ``row_ids_out={}`` and read `user_row_id` and `assistant_row_id`
    from it after the call; callers that do not pass it are entirely
    unaffected. The dict is only populated after COMMIT succeeds, so a
    populated dict always means "these rows exist."

    Deriving the user row as ``assistant_row_id - 1`` would be right
    almost always and silently wrong the rest of the time. The
    timeline would then attribute one narrator's words to another
    narrator's turn, which is the one class of error a family memoir
    must never make. So it is captured, not computed.

    WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1 (2026-08-09) -- the
    keyword-only ``is_system_directive``. Internal guidance composed by
    the browser (``[SYSTEM: ...]`` / ``[SYSTEM_QF: ...]``) travels in
    the user message slot, because in-band guidance is how Lori is
    steered. It was then written down as if the narrator had said it,
    and **eighteen modules** grew a defensive check on the text prefix
    to undo that. Measured on the live database the day this landed:
    **120 of 794 user rows (15.1%) are directives, across 39 of 335
    conversations**, the worst carrying ten apiece.

    THE CLASSIFICATION IS AN ARGUMENT, NOT A RE-READING. The caller
    already knows -- ``chat_ws`` computes ``_is_system_directive`` at
    :1247 and carries it in ``params`` at :1263 -- and this function
    deliberately does NOT look at ``user_message`` to decide. Sniffing
    the prefix here would rebuild the nineteenth copy of the guess
    inside the one place that is supposed to end the guessing. It would
    also mean a narrator who types "[SYSTEM: ..." has their own words
    reclassified as machinery, which is the failure the prefix approach
    already has and this one must not inherit.

    IT IS A BOOLEAN RATHER THAN A METADATA DICT ON PURPOSE. A dict
    parameter invites a future caller to attach "just a bit" of turn
    context, and the nearest thing to hand is always the narrator's
    text -- which is how the duplicate ``PROFILE_JSON.last_user_text``
    happened. A flag cannot carry prose.

    ``role`` STAYS ``'user'``. Option A of the work order, ruled by
    Chris on 2026-08-09. The column is doing two jobs at once -- who
    authored this, and how it replays to the model -- and only the
    first is wrong. Changing ``role`` would silently stop directives
    reaching Lori, which is a behaviour change wearing a storage
    change's clothes.
    """
    init_db()
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3 — the narrator this
    # turn belongs to. Every chat_ws persist site has it in scope; it was
    # simply being dropped here. Keyword-only and defaulted, so callers
    # that genuinely have no narrator (tests, legacy REST) are unchanged
    # and record NULL rather than a guess.
    ensure_session(conv_id, person_id=person_id)
    ts = _now_iso()

    # VALIDATED BEFORE THE TRANSACTION OPENS, on purpose. A malformed
    # decision must not be discovered halfway through a write that has
    # already inserted the narrator's row — the turn itself matters far
    # more than its diagnostic, and an exception in here would roll the
    # conversation's own record back with it.
    _capture_decision_for_row: Optional[Dict[str, Any]] = None
    if story_capture_decision is not None:
        from .services.story_trigger import validate_story_capture_decision
        _capture_decision_for_row = validate_story_capture_decision(
            story_capture_decision)

    assistant_rowid: Optional[int] = None
    user_rowid: Optional[int] = None
    con = _connect()
    cur = con.cursor()
    cur.execute("BEGIN")
    try:
        # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1. `"{}"` was written
        # here unconditionally, so within THIS writer the field was free.
        # That is not true of the column: measured 2026-08-09, 232 user
        # rows already carry `meta_json` (a `section` key, written by the
        # sibling `add_turn`). None of them is a directive, so nothing
        # merges today -- but the dict is built rather than hardcoded so
        # that adding a second user-row fact later is an edit here and not
        # a silent overwrite of someone else's.
        #
        # `_json_dump({})` is exactly `"{}"`, so a non-directive turn
        # writes the identical bytes it always did.
        user_meta: Dict[str, Any] = {}
        if is_system_directive:
            user_meta["origin"] = TURN_ORIGIN_SYSTEM_DIRECTIVE
        # Phase 4. Merged rather than assigned, so the system-directive
        # origin above survives on a turn that carries both. Validated
        # BEFORE the transaction opened (see `_validated_capture_decision`
        # at the top of this function) — nothing unvalidated reaches here.
        if _capture_decision_for_row is not None:
            user_meta["story_capture_decision"] = _capture_decision_for_row
        cur.execute(
            "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) VALUES(?,?,?,?,?,?);",
            (conv_id, "user", user_message, ts, "", _json_dump(user_meta)),
        )
        # Captured here, inside the transaction, while it is still the
        # last row inserted. One statement later it is unrecoverable
        # without guessing.
        user_rowid = cur.lastrowid
        assistant_meta = {"model": model_name or "", **(meta or {})}
        cur.execute(
            "INSERT INTO turns(conv_id,role,content,ts,anchor_id,meta_json) VALUES(?,?,?,?,?,?);",
            (conv_id, "assistant", assistant_message, ts, "", _json_dump(assistant_meta)),
        )
        assistant_rowid = cur.lastrowid
        cur.execute("UPDATE sessions SET updated_at=? WHERE conv_id=?;", (ts, conv_id))
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        con.close()

    # Only after COMMIT: a populated dict always means the rows exist.
    if row_ids_out is not None:
        try:
            row_ids_out["user_row_id"] = user_rowid
            row_ids_out["assistant_row_id"] = assistant_rowid
        except Exception:
            pass

    # TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- observability only.
    # No behavior change. No-op unless HORNELORE_TRUTH_PIPELINE_LOG=1 AND a
    # turn probe is active in this context. Failure is swallowed.
    try:
        from .services import truth_pipeline_probe as _tp
        _tp.mark("raw_turn_saved", "turns")
    except Exception:
        pass

    return assistant_rowid


# -----------------------------------------------------------------------------
# People (routers/people.py)
# -----------------------------------------------------------------------------
# WO-13 Phase 3 — narrator_type constants
NARRATOR_TYPES = ("live", "reference")


def _normalise_narrator_type(value: Optional[str]) -> str:
    if value is None:
        return "live"
    v = str(value).strip().lower()
    if v not in NARRATOR_TYPES:
        raise ValueError(f"narrator_type must be one of {NARRATOR_TYPES}; got {value!r}")
    return v


def create_person(
    display_name: str,
    role: str = "",
    date_of_birth: str = "",
    place_of_birth: str = "",
    narrator_type: str = "live",
    *,
    # WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A identity fields.
    # These map to the new columns added by migration 0013 and the
    # idempotent ALTER TABLE block in init_db. Lori's prompt composer
    # reads pronouns + current_residence on every turn, so writing
    # them at create-time eliminates the "pronoun-unknown" gap that
    # forced Lori to guess.
    pronouns: str = "",
    pronouns_other: str = "",
    current_residence: str = "",
    # Guard Lab eligibility. DEFAULT FALSE, and every caller that wants a
    # test narrator must say so explicitly — a person is a real narrator
    # unless somebody deliberately declared otherwise. Callers previously
    # passed this nowhere, so it was accepted at the API boundary and
    # lost. The column is added by the PRAGMA-guarded people block in
    # init_db() above — there is deliberately no migration for it.
    testing_only: bool = False,
) -> Dict[str, Any]:
    init_db()
    pid = _uuid()
    now = _now_iso()
    nt = _normalise_narrator_type(narrator_type)
    con = _connect()
    # ── ATOMIC ENROLLMENT ────────────────────────────────────────────
    # WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 1 (2026-08-26).
    #
    # The people row and the Profile Seed onboarding row land in ONE
    # transaction. Work order §4.2 refuses "person created, onboarding
    # best-effort" as a partial success, and the reason is worth stating
    # plainly: a narrator with no onboarding row is HISTORICAL by
    # definition — the deliberate absence of a row is how this system
    # says "do not start a questionnaire on this person". A failed
    # enrollment that left the person behind would not produce a
    # narrator missing a feature. It would produce a brand-new narrator
    # permanently indistinguishable from one created before the
    # migration, silently excluded from the walk, with nothing anywhere
    # recording that it happened.
    #
    # This function used to commit and close before calling
    # ensure_profile(), so there was no transaction to join; the
    # explicit BEGIN below is what creates one. `ensure_profile()` keeps
    # its own later transaction — it is idempotent, its absence is
    # recoverable, and widening this boundary further would mean
    # rewriting the intake fan-out, which this lane is not.
    try:
        con.execute("BEGIN IMMEDIATE;")
        con.execute(
            """
            INSERT INTO people(
                id, display_name, role, date_of_birth, place_of_birth,
                created_at, updated_at, narrator_type,
                pronouns, pronouns_other, current_residence,
                testing_only
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                pid, display_name, role or "",
                _sanitise_dob(date_of_birth), place_of_birth or "",
                now, now, nt,
                (pronouns or "").strip(),
                (pronouns_other or "").strip(),
                (current_residence or "").strip(),
                1 if testing_only else 0,
            ),
        )
        _profile_seed.enroll(con, pid, now)
        con.commit()
    except Exception:
        # Both rows or neither. The rollback is what makes the sentence
        # above true rather than aspirational.
        try:
            con.rollback()
        except Exception:
            pass
        con.close()
        logger.exception(
            "create_person ROLLED BACK for name=%r — Profile Seed enrollment "
            "or the people insert failed; no person row was created",
            display_name,
        )
        raise
    con.close()
    ensure_profile(pid)
    # v7.4D — log person creation for DB verification (Phase 0)
    logger.info(
        "DB create_person: id=%s name=%r dob=%r pob=%r "
        "narrator_type=%s pronouns=%r residence=%r",
        pid, display_name, date_of_birth, place_of_birth,
        nt, pronouns, current_residence,
    )
    return get_person(pid) or {"id": pid, "display_name": display_name}


# ─────────────────────────────────────────────────────────────────────
# Profile Seed onboarding accessors
# WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 1 (2026-08-26)
# ─────────────────────────────────────────────────────────────────────
def profile_seed_resolve(person_id: str) -> Optional[Dict[str, Any]]:
    """Resolve one narrator's onboarding state, materializing any drift.

    Returns `None` for a HISTORICAL narrator — one with a `people` row
    and no onboarding row — and never creates one. Work order decision 3.

    Raises `PersonNotFound` when the id names NOBODY. That is a
    different answer to a different question, and collapsing the two was
    a real defect: a typo, a stale bookmark or a deleted narrator would
    have been reported as a legitimate historical narrator, with nothing
    in the response letting a client tell the difference. Decision 3 is
    about narrators who predate the migration; it says nothing about
    identifiers that name no one. **Neither case writes a row.**

    This is a WRITING read, and that is deliberate rather than
    convenient. If evidence arrived since the last resolve (the operator
    entered the sibling count in Bio Builder, an extraction promoted a
    career), returning the new answer without persisting it would leave
    `topic_state_json`, `active_topic_id`, `status` and `version`
    describing the world before that answer. The next writer would then
    compare `expected_version` against a number that never moved, and a
    stale write would be accepted as fresh. `reconcile()` moves the
    version only when the effective stored state actually changes, so a
    resolve that finds nothing new costs one SELECT and invalidates
    nobody.
    """
    init_db()
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE;")
        # Existence is checked on THE SAME CONNECTION, inside the same
        # transaction as the resolve, so the two answers cannot describe
        # different moments.
        if not _profile_seed.person_exists(con, person_id):
            con.rollback()
            raise _profile_seed.PersonNotFound(person_id)
        state = _profile_seed.reconcile(con, person_id, now=_now_iso())
        if state is None:
            con.rollback()
            return None
        con.commit()
        return state.as_dict()
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def profile_seed_apply(
    person_id: str,
    *,
    expected_version: int,
    action: str,
    topic_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply ONE client action to the onboarding row. All-or-nothing.

    `action` is one of `addressed`, `declined`, `pause`, `resume`.
    Deliberately NOT `known` and NOT `completed`: those are derived from
    evidence and from the remaining topics, and a client able to declare
    either could fake its way to the end of the walk, or un-answer a
    question the narrator has already answered.

    THE ORDER OF THE CHECKS IS THE CONTRACT, and it is the part that is
    easy to get subtly wrong:

      1. `BEGIN IMMEDIATE` takes the write lock BEFORE the first read.
         A deferred transaction would read the version, then upgrade,
         and lose a race it could not detect.
      2. **Reconcile first.** Evidence may have changed since the
         client's GET without the progress row's version moving — the
         operator answering the active topic in another tab is the
         ordinary case, not an exotic one. Reconciling first
         materializes that change and bumps the version, so step 3 sees
         a genuinely stale read for what it is.
      3. Compare `expected_version` against the version AFTER
         reconciliation. Mismatch -> `VersionConflict` carrying the
         fresh state, and nothing is written.
      4. For a topic disposition, the topic must still be THE ACTIVE
         TOPIC. Testing only the version would let a write land on a
         topic that reconciliation just answered.
      5. Apply, reconcile again so the active topic advances and
         completion derives, then commit.

    Raises `NotEnrolled` (404), `UnknownTopic` (422), `VersionConflict`
    (409) or `TopicNotActive` (409). Every one of them rolls back.
    """
    init_db()
    valid_actions = ("addressed", "declined", "pause", "resume")
    if action not in valid_actions:
        raise ValueError(f"action must be one of {valid_actions}; got {action!r}")
    if action in _profile_seed.CLIENT_DISPOSITIONS and not _profile_seed.is_known_topic(topic_id):
        # Validated before any lock is taken — an unknown topic is a
        # client bug, not a concurrency event.
        raise _profile_seed.UnknownTopic(topic_id)
    # ── STRICTLY AN INTEGER. `int(...)` WAS NOT STRICT, 2026-08-27 ─────
    #
    # This read `expected = int(expected_version)`, which is a CONVERTER
    # wearing a validator's clothes. `int()` accepts `True`, `"1"`,
    # `1.0`, `Decimal("1")` and anything with `__int__`, and the request
    # model on the route above it was no stricter — Pydantic coerced
    # `true` to `1`.
    #
    # Reproduced against a temporary database before this changed: a
    # pending narrator at version 1 accepted `expected_version=True` and
    # moved to version 2. The optimistic-concurrency contract is that a
    # caller states the exact version it read; `True` states nothing, and
    # it happened to win because `True == 1`.
    #
    # `float` is refused for the same reason and one more: `int(1.9)` is
    # `1`, so a client with an arithmetic bug would silently address a
    # version it never read. Rounding is not a decision this accessor is
    # entitled to make on a value whose whole job is to be exact.
    #
    # RANGE IS NOT CHECKED HERE, deliberately. A version of `0` or `-5`
    # is a well-typed claim that is simply wrong, and the comparison
    # below answers it correctly with `VersionConflict` carrying the
    # fresh state — more useful to a client than a 422, because it says
    # what the version actually is. Only the TYPE is a contract
    # violation, because a wrongly-typed version cannot be compared at
    # all without first inventing a value for it.
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise ValueError(
            "expected_version must be an int; got "
            f"{type(expected_version).__name__} {expected_version!r}. "
            "Booleans, floats and numeric strings are refused rather than "
            "coerced: a version is read from the server and echoed back "
            "exactly, and a value that had to be converted was not the "
            "value that was read.")
    expected = expected_version

    now = _now_iso()
    con = _connect()
    try:
        con.execute("BEGIN IMMEDIATE;")

        if not _profile_seed.person_exists(con, person_id):
            con.rollback()
            raise _profile_seed.PersonNotFound(person_id)

        if _profile_seed.read_row(con, person_id) is None:
            con.rollback()
            raise _profile_seed.NotEnrolled(person_id)

        # Step 2 — materialize evidence drift before comparing versions.
        state = _profile_seed.reconcile(con, person_id, now=now)
        if state is None:  # pragma: no cover — row proven present above
            con.rollback()
            raise _profile_seed.NotEnrolled(person_id)

        # Step 3 — the version comparison, against post-reconcile truth.
        if state.version != expected:
            fresh = state
            con.rollback()
            raise _profile_seed.VersionConflict(expected, fresh.version, fresh)

        if action in _profile_seed.CLIENT_DISPOSITIONS:
            # Step 4 — and this is the check `expected_version` cannot make.
            if state.active_topic_id != topic_id:
                active = state.active_topic_id
                con.rollback()
                raise _profile_seed.TopicNotActive(str(topic_id), active)
            _profile_seed.apply_disposition(
                con, person_id, topic_id=str(topic_id),
                disposition=action, now=now)
        else:
            _profile_seed.set_paused(
                con, person_id, paused=(action == "pause"), now=now)

        # Step 5 — advance the active topic and derive completion.
        final = _profile_seed.reconcile(con, person_id, now=now)
        con.commit()
        return (final or state).as_dict()
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def update_person(
    person_id: str,
    display_name: Optional[str] = None,
    role: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    place_of_birth: Optional[str] = None,
    narrator_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    init_db()
    now = _now_iso()
    nt = _normalise_narrator_type(narrator_type) if narrator_type is not None else None
    con = _connect()
    row = con.execute("SELECT id FROM people WHERE id=?;", (person_id,)).fetchone()
    if not row:
        con.close()
        return None
    con.execute(
        """
        UPDATE people
        SET display_name=COALESCE(?,display_name),
            role=COALESCE(?,role),
            date_of_birth=COALESCE(?,date_of_birth),
            place_of_birth=COALESCE(?,place_of_birth),
            narrator_type=COALESCE(?,narrator_type),
            updated_at=?
        WHERE id=?;
        """,
        (
            display_name,
            role,
            _sanitise_dob(date_of_birth) if date_of_birth is not None else None,
            place_of_birth,
            nt,
            now,
            person_id,
        ),
    )
    con.commit()
    con.close()
    return get_person(person_id)


def list_people(limit: int = 50, offset: int = 0, include_deleted: bool = False) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    if include_deleted:
        rows = con.execute(
            """
            SELECT id,display_name,role,date_of_birth,place_of_birth,created_at,updated_at,
                   narrator_type,is_deleted,deleted_at,undo_expires_at
            FROM people
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?;
            """,
            (int(limit), int(offset)),
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT id,display_name,role,date_of_birth,place_of_birth,created_at,updated_at,
                   narrator_type
            FROM people
            WHERE is_deleted = 0
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?;
            """,
            (int(limit), int(offset)),
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_person(person_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    row = con.execute(
        """
        SELECT id,display_name,role,date_of_birth,place_of_birth,created_at,updated_at,
               narrator_type,
               COALESCE(pronouns, '') AS pronouns,
               COALESCE(pronouns_other, '') AS pronouns_other,
               COALESCE(current_residence, '') AS current_residence,
               COALESCE(testing_only, 0) AS testing_only
        FROM people WHERE id=?;
        """,
        (person_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    person = dict(row)
    # Exposed as a real bool so callers cannot accidentally treat the
    # SQLite integer 0 as truthy-by-presence.
    person["testing_only"] = bool(person.get("testing_only"))
    return person


def person_is_testing_only(person_id: Optional[str]) -> bool:
    """Guard Lab eligibility, resolved fail-closed.

    An unknown person, a missing id, or any read failure answers False.
    The question this gates is "may an experimental configuration that
    strips Lori's narrator-facing interventions apply to this turn?", and
    the only safe answer when anything is uncertain is no.
    """
    if not person_id:
        return False
    try:
        person = get_person(str(person_id))
    except Exception:
        logger.exception(
            "person_is_testing_only: lookup failed for %r — answering False",
            person_id)
        return False
    return bool(person and person.get("testing_only"))


# -----------------------------------------------------------------------------
# WO-13 Phase 3 — Reference narrator helpers
# -----------------------------------------------------------------------------
def get_narrator_type(person_id: str) -> Optional[str]:
    """Return 'live' | 'reference' | None (if person does not exist)."""
    p = get_person(person_id)
    if not p:
        return None
    return (p.get("narrator_type") or "live").lower()


def is_reference_narrator(person_id: str) -> bool:
    return get_narrator_type(person_id) == "reference"


def set_narrator_type(person_id: str, narrator_type: str) -> Optional[Dict[str, Any]]:
    return update_person(person_id, narrator_type=narrator_type)


# -----------------------------------------------------------------------------
# Profiles (routers/profiles.py)
# -----------------------------------------------------------------------------
def ensure_profile(person_id: str) -> None:
    init_db()
    con = _connect()
    now = _now_iso()
    con.execute(
        "INSERT OR IGNORE INTO profiles(person_id,profile_json,updated_at) VALUES(?,?,?);",
        (person_id, "{}", now),
    )
    con.commit()
    con.close()


def get_profile(person_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    row = con.execute(
        "SELECT person_id,profile_json,updated_at FROM profiles WHERE person_id=?;",
        (person_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    return {
        "person_id": row["person_id"],
        "profile_json": _json_load(row["profile_json"], {}),
        "updated_at": row["updated_at"],
    }


def update_profile_json(person_id: str, profile_json: Dict[str, Any], merge: bool = True, reason: str = "") -> Dict[str, Any]:
    init_db()
    ensure_profile(person_id)
    cur_prof = get_profile(person_id) or {"profile_json": {}}
    merged: Dict[str, Any]
    if merge:
        merged = dict(cur_prof.get("profile_json") or {})
        merged.update(profile_json or {})
    else:
        merged = profile_json or {}

    now = _now_iso()
    con = _connect()
    con.execute(
        "UPDATE profiles SET profile_json=?, updated_at=? WHERE person_id=?;",
        (_json_dump(merged), now, person_id),
    )
    con.commit()
    con.close()
    # v7.4D — log profile saves for DB verification (Phase 0)
    logger.info("DB update_profile_json: person_id=%s reason=%r keys=%s", person_id, reason or "unspecified", list(merged.keys()))
    return get_profile(person_id) or {"person_id": person_id, "profile_json": merged, "updated_at": now}


def ingest_basic_info_document(
    person_id: str,
    document: Any,
    create_relatives: bool = False,
) -> Dict[str, Any]:
    """Ingest a basic-info form document into the profile.

    ``document`` may be a dict (from the JSON form) or a legacy plain-text string.
    ``create_relatives`` is accepted and stored; relative creation is not yet
    implemented — the flag is preserved so callers do not crash.
    """
    init_db()
    p = get_profile(person_id) or {"profile_json": {}}
    prof = dict(p.get("profile_json") or {})
    ingest = dict(prof.get("ingest") or {})
    if isinstance(document, str):
        ingest["basic_info"] = {"text": document, "ts": _now_iso()}
    else:
        ingest["basic_info"] = {
            "document": document or {},
            "create_relatives": create_relatives,
            "ts": _now_iso(),
        }
    prof["ingest"] = ingest
    return update_profile_json(person_id, prof, merge=False)


def _set_path(obj: Dict[str, Any], path: str, value: Any) -> None:
    keys = [k for k in (path or "").split(".") if k]
    if not keys:
        return
    cur: Any = obj
    for k in keys[:-1]:
        if not isinstance(cur, dict):
            return
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    if isinstance(cur, dict):
        cur[keys[-1]] = value


def update_profile_field(person_id: str, profile_path: str, value: Any) -> None:
    init_db()
    ensure_profile(person_id)
    p = get_profile(person_id) or {"profile_json": {}}
    prof = dict(p.get("profile_json") or {})
    _set_path(prof, profile_path, value)
    update_profile_json(person_id, prof, merge=False)


# -----------------------------------------------------------------------------
# Media (routers/media.py)
# Bug MB-01 fix: updated signatures to match what the router actually sends.
# Original function accepted (kind, filename, mime, bytes, sha256, meta) but
# the router called with (file_path, mime_type, description, taken_at, ...).
# -----------------------------------------------------------------------------
def add_media(
    person_id: Optional[str],
    filename: str,
    mime: str,
    bytes: int = 0,
    sha256: str = "",
    kind: str = "image",
    description: str = "",
    taken_at: Optional[str] = None,
    location_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    exif: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_db()
    mid = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        """
        INSERT INTO media(
          id, person_id, kind, filename, mime, bytes, sha256, created_at,
          description, taken_at, location_name, latitude, longitude, exif_json, meta_json
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        (
            mid, person_id, kind or "image", filename or "", mime or "",
            int(bytes or 0), sha256 or "", now,
            description or "", taken_at, location_name,
            latitude, longitude,
            _json_dump(exif or {}), "{}",
        ),
    )
    con.commit()
    con.close()
    return {
        "id": mid, "person_id": person_id, "kind": kind, "filename": filename,
        "mime": mime, "bytes": int(bytes or 0), "sha256": sha256, "created_at": now,
        "description": description, "taken_at": taken_at, "location_name": location_name,
        "latitude": latitude, "longitude": longitude, "exif": exif or {},
    }


def list_media(person_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    cols = (
        "id, person_id, kind, filename, mime, bytes, sha256, created_at, "
        "description, taken_at, location_name, latitude, longitude, exif_json"
    )
    if person_id:
        rows = con.execute(
            f"SELECT {cols} FROM media WHERE person_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            (person_id, int(limit), int(offset)),
        ).fetchall()
    else:
        rows = con.execute(
            f"SELECT {cols} FROM media ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            (int(limit), int(offset)),
        ).fetchall()
    con.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["exif"] = _json_load(d.pop("exif_json", "{}"), {})
        out.append(d)
    return out


def get_media_item(media_id: str) -> Optional[Dict[str, Any]]:
    """Return a single media row by id, or None if not found."""
    init_db()
    con = _connect()
    row = con.execute(
        "SELECT id,person_id,kind,filename,mime,bytes,sha256,created_at,"
        "description,taken_at,location_name,latitude,longitude,exif_json "
        "FROM media WHERE id=?;",
        (media_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    d = dict(row)
    d["exif"] = _json_load(d.pop("exif_json", "{}"), {})
    return d


def delete_media(media_id: str) -> bool:
    """Delete a media row. Returns True if a row was deleted."""
    init_db()
    con = _connect()
    cur = con.execute("DELETE FROM media WHERE id=?;", (media_id,))
    deleted = cur.rowcount > 0
    con.commit()
    con.close()
    return deleted


# Media attachments — links a photo to a memoir section or fact
# -----------------------------------------------------------------------------
def add_media_attachment(
    media_id: str,
    entity_type: str,
    entity_id: str,
    person_id: Optional[str] = None,
) -> Dict[str, Any]:
    init_db()
    aid = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        "INSERT INTO media_attachments(id,media_id,entity_type,entity_id,person_id,created_at) VALUES(?,?,?,?,?,?);",
        (aid, media_id, entity_type, entity_id, person_id, now),
    )
    con.commit()
    con.close()
    return {"id": aid, "media_id": media_id, "entity_type": entity_type,
            "entity_id": entity_id, "person_id": person_id, "created_at": now}


def delete_media_attachment(attachment_id: str) -> bool:
    init_db()
    con = _connect()
    cur = con.execute("DELETE FROM media_attachments WHERE id=?;", (attachment_id,))
    deleted = cur.rowcount > 0
    con.commit()
    con.close()
    return deleted


def list_media_attachments(person_id: Optional[str] = None, media_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    if media_id:
        rows = con.execute(
            "SELECT id,media_id,entity_type,entity_id,person_id,created_at "
            "FROM media_attachments WHERE media_id=? ORDER BY created_at ASC;",
            (media_id,),
        ).fetchall()
    elif person_id:
        rows = con.execute(
            "SELECT id,media_id,entity_type,entity_id,person_id,created_at "
            "FROM media_attachments WHERE person_id=? ORDER BY created_at ASC;",
            (person_id,),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT id,media_id,entity_type,entity_id,person_id,created_at "
            "FROM media_attachments ORDER BY created_at ASC;"
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# -----------------------------------------------------------------------------
# Timeline (routers/timeline.py)
# -----------------------------------------------------------------------------
def add_timeline_event(
    person_id: str,
    date: str,
    title: str,
    body: str = "",
    kind: str = "event",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """2026-07-23 fix: wrap in try/finally. Prior code was
    ``con = _connect(); con.execute(INSERT); con.commit(); con.close()``
    with no exception handling. When the INSERT hit a FOREIGN KEY
    violation (bogus person_id from an operator or upstream data-import
    bug), the exception propagated up and ``con.close()`` never ran.
    Python's GC eventually released the SQLite connection, but until
    then it held an implicit transaction with the write lock, causing
    the NEXT connection (e.g. auto-day-generation immediately after a
    trip bridge-sync) to fail with ``sqlite3.OperationalError:
    database is locked``. Root cause of the 2026-07-22 North Dakota
    live-test flake."""
    init_db()
    eid = _uuid()
    now = _now_iso()
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO timeline_events(id,person_id,date,title,body,kind,created_at,meta_json)
            VALUES(?,?,?,?,?,?,?,?);
            """,
            (eid, person_id, date, title, body or "", kind or "event", now, _json_dump(meta or {})),
        )
        con.commit()
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()
    return {"id": eid, "person_id": person_id, "date": date, "title": title, "body": body or "", "kind": kind or "event", "created_at": now, "meta": meta or {}}


def list_timeline_events(person_id: str, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    """2026-07-23 fix: try/finally around fetchall so a mid-query
    OperationalError does not leak the connection."""
    init_db()
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT id,person_id,date,title,body,kind,created_at,meta_json
            FROM timeline_events
            WHERE person_id=?
            ORDER BY date ASC, created_at ASC
            LIMIT ? OFFSET ?;
            """,
            (person_id, int(limit), int(offset)),
        ).fetchall()
    finally:
        con.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["meta"] = _json_load(d.pop("meta_json", "{}"), {})
        out.append(d)
    return out


def delete_timeline_event(event_id: str) -> bool:
    """2026-07-23 fix: try/finally — same reasoning as add_timeline_event."""
    init_db()
    con = _connect()
    try:
        cur = con.execute("DELETE FROM timeline_events WHERE id=?;", (event_id,))
        con.commit()
        rc = cur.rowcount
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()
    return rc > 0


# -----------------------------------------------------------------------------
# Interview helpers (routers/interview.py)
# -----------------------------------------------------------------------------
def start_session(person_id: str, plan_id: str = "default") -> Dict[str, Any]:
    init_db()
    sid = _uuid()
    now = _now_iso()
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO interview_sessions(id,person_id,plan_id,started_at,updated_at,active_question_id)
            VALUES(?,?,?,?,?,NULL);
            """,
            (sid, person_id, plan_id or "default", now, now),
        )
        con.commit()
        return {"id": sid, "person_id": person_id, "plan_id": plan_id or "default", "started_at": now, "updated_at": now}
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def ensure_interview_session(
    session_id: str,
    person_id: Optional[str],
    plan_id: str = "chat_ws",
) -> None:
    """Idempotent — create an interview_sessions row if one doesn't exist
    for the given session_id. Used by chat_ws.py to satisfy the
    segment_flags(session_id) FOREIGN KEY before any safety write.

    BUG-DBLOCK-01 PATCH 2 (2026-04-30): segment_flags FK's into
    interview_sessions(id), but chat_ws creates conv_ids that are never
    registered there (only routers/interview.py:start_session inserts).
    Without this idempotent ensure, every safety segment_flag insert on
    the chat path failed with FOREIGN KEY constraint failed, which
    pre-PATCH 1 leaked the write lock and cascaded the entire safety
    path into 15s of busy_timeout failures.

    Safe to call every turn: INSERT OR IGNORE deduplicates on the
    primary key. plan_id defaults to 'chat_ws' to distinguish these
    rows from real interview-router sessions in the DB.

    BUG-CHATWS-CONV-FK-01 (2026-06-17): interview_sessions FK's into
    interview_plans(id) via plan_id. The default 'chat_ws' plan_id is
    NOT pre-seeded by init_db() (only 'default' is), so every call
    failed with FOREIGN KEY constraint failed. The fix is to lazy-seed
    the chat_ws plan row in this function, ahead of the session insert.
    Both inserts are idempotent (INSERT OR IGNORE) so this is safe to
    call on every turn at zero ongoing cost after first call.
    """
    init_db()
    now = _now_iso()
    con = _connect()
    try:
        # BUG-CHATWS-CONV-FK-01: lazy-seed the chat_ws plan row so the
        # session insert below can satisfy its FK constraint. Idempotent.
        con.execute(
            "INSERT OR IGNORE INTO interview_plans(id, title, created_at) "
            "VALUES (?, ?, ?);",
            (plan_id, f"Plan: {plan_id}", now),
        )
        con.execute(
            "INSERT OR IGNORE INTO interview_sessions"
            "(id, person_id, plan_id, started_at, updated_at, active_question_id) "
            "VALUES (?, ?, ?, ?, ?, NULL);",
            (session_id, person_id, plan_id, now, now),
        )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def get_interview_session(session_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    row = con.execute(
        "SELECT id,person_id,plan_id,started_at,updated_at,active_question_id FROM interview_sessions WHERE id=?;",
        (session_id,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def set_session_active_question(session_id: str, question_id: str) -> None:
    init_db()
    con = _connect()
    now = _now_iso()
    con.execute(
        "UPDATE interview_sessions SET active_question_id=?, updated_at=? WHERE id=?;",
        (question_id, now, session_id),
    )
    con.commit()
    con.close()


def get_question(question_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    row = con.execute(
        """
        SELECT id,plan_id,section_id,ord,prompt,kind,required,profile_path
        FROM interview_questions WHERE id=?;
        """,
        (question_id,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def count_plan_questions(plan_id: str) -> int:
    """Return the number of questions seeded for plan_id. Used as a startup guard."""
    init_db()
    con = _connect()
    row = con.execute(
        "SELECT COUNT(*) AS n FROM interview_questions WHERE plan_id=?;",
        (plan_id or "default",),
    ).fetchone()
    con.close()
    return int(row["n"]) if row else 0


def get_next_question(session_id: str, plan_id: str, current_question_id: Optional[str]) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    plan_id = plan_id or "default"

    if not current_question_id:
        row = con.execute(
            """
            SELECT id,section_id,prompt,kind,required,profile_path,ord
            FROM interview_questions
            WHERE plan_id=?
            ORDER BY ord ASC
            LIMIT 1;
            """,
            (plan_id,),
        ).fetchone()
        con.close()
        return dict(row) if row else None

    cur_row = con.execute(
        "SELECT ord FROM interview_questions WHERE id=? AND plan_id=?;",
        (current_question_id, plan_id),
    ).fetchone()
    cur_ord = int(cur_row["ord"]) if cur_row else -1

    row = con.execute(
        """
        SELECT id,section_id,prompt,kind,required,profile_path,ord
        FROM interview_questions
        WHERE plan_id=? AND ord>?
        ORDER BY ord ASC
        LIMIT 1;
        """,
        (plan_id, cur_ord),
    ).fetchone()

    con.close()
    return dict(row) if row else None


def add_answer(session_id: str, question_id: str, answer: str, skipped: bool, person_id: str) -> None:
    init_db()
    con = _connect()
    now = _now_iso()
    con.execute(
        """
        INSERT INTO interview_answers(id,session_id,person_id,question_id,answer,skipped,ts)
        VALUES(?,?,?,?,?,?,?);
        """,
        (_uuid(), session_id, person_id, question_id, answer or "", 1 if skipped else 0, now),
    )
    con.execute("UPDATE interview_sessions SET updated_at=? WHERE id=?;", (now, session_id))
    con.commit()
    con.close()


# -----------------------------------------------------------------------------
# RAG minimal
# -----------------------------------------------------------------------------
def _tokenize(s: str) -> List[str]:
    import re
    return re.findall(r"[a-z0-9']{2,}", (s or "").lower())


def _chunk_text(text: str, size: int = 900) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = (buf + "\n" + p) if buf else p
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks




def rag_get_doc_text(doc_id: str) -> str:
    """Return the raw text for a specific RAG doc id, or '' if missing."""
    init_db()
    con = _connect()
    row = con.execute("SELECT text FROM rag_docs WHERE id=?;", (doc_id,)).fetchone()
    con.close()
    return row["text"] if row else ""

def rag_add_doc(doc_id: str, title: str, source: str, text: str) -> None:
    init_db()
    con = _connect()
    now = _now_iso()
    con.execute(
        "INSERT OR REPLACE INTO rag_docs(id,title,source,created_at,text) VALUES(?,?,?,?,?);",
        (doc_id, title, source, now, text),
    )
    con.execute("DELETE FROM rag_chunks WHERE doc_id=?;", (doc_id,))
    for i, ch in enumerate(_chunk_text(text, 900)):
        con.execute(
            "INSERT OR REPLACE INTO rag_chunks(id,doc_id,chunk_index,text) VALUES(?,?,?,?);",
            (f"{doc_id}::c{i}", doc_id, i, ch),
        )
    con.commit()
    con.close()


def rag_stats() -> Dict[str, int]:
    init_db()
    con = _connect()
    docs = con.execute("SELECT COUNT(*) AS n FROM rag_docs;").fetchone()["n"]
    chunks = con.execute("SELECT COUNT(*) AS n FROM rag_chunks;").fetchone()["n"]
    con.close()
    return {"docs": int(docs), "chunks": int(chunks)}


def rag_query(query: str, k: int = 5, only_ids: Optional[List[str]] = None, only_doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    tokens = [t for t in _tokenize((query or "").strip()) if t]
    if not tokens:
        return []
    k = max(1, min(int(k), 20))
    rows = con.execute(
        """
        SELECT c.id AS chunk_id, c.doc_id, c.text AS chunk_text, d.title AS doc_title, d.source AS doc_source
        FROM rag_chunks c JOIN rag_docs d ON d.id = c.doc_id;
        """
    ).fetchall()
    con.close()

    hits: List[Dict[str, Any]] = []
    for r in rows:
        cid = r["chunk_id"]
        # Back-compat: only_ids filters by chunk_id; only_doc_ids filters by doc_id.
        if only_doc_ids and r["doc_id"] not in only_doc_ids:
            continue
        if only_ids and cid not in only_ids:
            continue
        txt = (r["chunk_text"] or "").lower()
        score = 0
        for t in tokens:
            if t in txt:
                score += 1
        title = (r["doc_title"] or "").lower()
        for t in tokens:
            if t in title:
                score += 1
        if score > 0:
            hits.append(
                {
                    "id": cid,
                    "doc_id": r["doc_id"],
                    "title": r["doc_title"] or "",
                    "source": r["doc_source"] or "",
                    "score": score,
                    "snippet": (r["chunk_text"] or "")[:420].strip(),
                }
            )
    hits.sort(key=lambda x: (-x["score"], x["title"]))
    return hits[:k]


# -----------------------------------------------------------------------------
# Section summaries
# -----------------------------------------------------------------------------
def save_section_summary(
    session_id: str,
    person_id: str,
    section_id: str,
    section_title: str,
    summary: str,
) -> Dict[str, Any]:
    init_db()
    sid = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        """
        INSERT OR REPLACE INTO section_summaries(id,session_id,person_id,section_id,section_title,summary,created_at)
        VALUES(?,?,?,?,?,?,?);
        """,
        (sid, session_id, person_id, section_id, section_title or "", summary or "", now),
    )
    con.commit()
    con.close()
    return {
        "id": sid, "session_id": session_id, "person_id": person_id,
        "section_id": section_id, "section_title": section_title,
        "summary": summary, "created_at": now,
    }


def list_section_summaries(session_id: str) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    rows = con.execute(
        """
        SELECT id,session_id,person_id,section_id,section_title,summary,created_at
        FROM section_summaries WHERE session_id=? ORDER BY created_at ASC;
        """,
        (session_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# -----------------------------------------------------------------------------
# Interview progress helper
# -----------------------------------------------------------------------------
def get_interview_progress(session_id: str, plan_id: str) -> Dict[str, Any]:
    """
    Return total questions, answered count, and current section info.
    Used for the UI progress indicator.
    """
    init_db()
    con = _connect()

    total = con.execute(
        "SELECT COUNT(*) AS n FROM interview_questions WHERE plan_id=?;",
        (plan_id,),
    ).fetchone()["n"]

    answered = con.execute(
        "SELECT COUNT(*) AS n FROM interview_answers WHERE session_id=?;",
        (session_id,),
    ).fetchone()["n"]

    # Current active question details
    sess_row = con.execute(
        "SELECT active_question_id FROM interview_sessions WHERE id=?;",
        (session_id,),
    ).fetchone()
    active_qid = sess_row["active_question_id"] if sess_row else None

    current_section_title = ""
    current_question_ord = 0
    if active_qid:
        q_row = con.execute(
            """
            SELECT iq.ord, isec.title
            FROM interview_questions iq
            LEFT JOIN interview_sections isec ON isec.id = iq.section_id
            WHERE iq.id=?;
            """,
            (active_qid,),
        ).fetchone()
        if q_row:
            current_question_ord = int(q_row["ord"] or 0)
            current_section_title = q_row["title"] or ""

    con.close()

    pct = round((answered / total * 100)) if total > 0 else 0
    return {
        "total": int(total),
        "answered": int(answered),
        "remaining": max(0, int(total) - int(answered)),
        "percent": pct,
        "current_ord": current_question_ord,
        "current_section": current_section_title,
    }


# -----------------------------------------------------------------------------
# Facts  (atomic, source-backed claims)
# -----------------------------------------------------------------------------
def add_fact(
    person_id: str,
    statement: str,
    fact_type: str = "general",
    date_text: str = "",
    date_normalized: str = "",
    confidence: float = 0.0,
    status: str = "extracted",
    inferred: bool = False,
    session_id: Optional[str] = None,
    source_turn_index: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
    # Meaning Engine fields (Phase A+B — Bug MAT-01 fix)
    meaning_tags: Optional[List[str]] = None,
    narrative_role: Optional[str] = None,
    experience: Optional[str] = None,
    reflection: Optional[str] = None,
) -> Dict[str, Any]:
    init_db()
    fid = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        """
        INSERT INTO facts(
          id,person_id,session_id,fact_type,statement,
          date_text,date_normalized,confidence,status,inferred,
          source_turn_index,created_at,updated_at,meta_json,
          meaning_tags_json,narrative_role,experience,reflection
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        (
            fid, person_id, session_id, fact_type or "general", statement,
            date_text or "", date_normalized or "",
            float(confidence or 0.0), status or "extracted",
            1 if inferred else 0, source_turn_index, now, now,
            _json_dump(meta or {}),
            _json_dump(meaning_tags or []),
            narrative_role or None,
            experience or None,
            reflection or None,
        ),
    )
    con.commit()
    con.close()
    return {
        "id": fid, "person_id": person_id, "session_id": session_id,
        "fact_type": fact_type, "statement": statement,
        "date_text": date_text, "date_normalized": date_normalized,
        "confidence": float(confidence or 0.0), "status": status or "extracted",
        "inferred": bool(inferred), "created_at": now,
        "meaning_tags": meaning_tags or [],
        "narrative_role": narrative_role,
        "experience": experience,
        "reflection": reflection,
    }


def list_facts(
    person_id: str,
    status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    _FACTS_COLS = """
        id,person_id,session_id,fact_type,statement,date_text,
        date_normalized,confidence,status,inferred,source_turn_index,
        created_at,meta_json,meaning_tags_json,narrative_role,experience,reflection
    """
    if status:
        rows = con.execute(
            f"SELECT {_FACTS_COLS} FROM facts WHERE person_id=? AND status=? "
            "ORDER BY created_at ASC LIMIT ? OFFSET ?;",
            (person_id, status, int(limit), int(offset)),
        ).fetchall()
    else:
        rows = con.execute(
            f"SELECT {_FACTS_COLS} FROM facts WHERE person_id=? "
            "ORDER BY created_at ASC LIMIT ? OFFSET ?;",
            (person_id, int(limit), int(offset)),
        ).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = _json_load(d.pop("meta_json", "{}"), {})
        d["meaning_tags"] = _json_load(d.pop("meaning_tags_json", "[]"), [])
        d["inferred"] = bool(d.get("inferred"))
        out.append(d)
    return out


def update_fact_status(fact_id: str, status: str) -> bool:
    init_db()
    now = _now_iso()
    con = _connect()
    cur = con.execute(
        "UPDATE facts SET status=?, updated_at=? WHERE id=?;",
        (status, now, fact_id),
    )
    con.commit()
    con.close()
    return cur.rowcount > 0


def delete_fact(fact_id: str) -> bool:
    init_db()
    con = _connect()
    cur = con.execute("DELETE FROM facts WHERE id=?;", (fact_id,))
    con.commit()
    con.close()
    return cur.rowcount > 0


# -----------------------------------------------------------------------------
# WO-13 — Family Truth helpers (notes + rows)
#
# This is the new write path for narrative memory. Legacy `facts` stays frozen.
#   * family_truth_notes  = shadow archive (raw text, append-only)
#   * family_truth_rows   = structured proposals; promoted truth is the subset
#                           with status in ('approve','approve_q')
#
# Valid row statuses (five-status vocabulary from WO-13 v2):
#   approve | approve_q | needs_verify | source_only | reject
# -----------------------------------------------------------------------------
FT_ROW_STATUSES = ("approve", "approve_q", "needs_verify", "source_only", "reject")
FT_EXTRACTION_METHODS = ("llm", "rules", "hybrid", "rules_fallback", "backfill", "manual", "questionnaire")

# WO-13 Phase 4/6/7 — The five identity-critical fields.
# These fields can NEVER be promoted from a rules_fallback row (regex-based
# client-side extraction). They MAY be promoted from a manual, llm, or
# questionnaire source, but the rules_fallback path is permanently blocked
# as defence in depth against the WO-12B contamination class.
FT_PROTECTED_IDENTITY_FIELDS = (
    "personal.fullName",
    "personal.preferredName",
    "personal.dateOfBirth",
    "personal.placeOfBirth",
    "personal.birthOrder",
)


def ft_add_note(
    person_id: str,
    body: str,
    source_kind: str = "chat",
    source_ref: str = "",
    created_by: str = "system",
) -> Dict[str, Any]:
    """Append a raw shadow-archive note. Never promoted directly."""
    init_db()
    nid = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        """
        INSERT INTO family_truth_notes(
          id, person_id, body, source_kind, source_ref,
          created_at, created_by, review_locked
        ) VALUES(?,?,?,?,?,?,?,0);
        """,
        (nid, person_id, body or "", source_kind or "chat", source_ref or "", now, created_by or "system"),
    )
    con.commit()
    con.close()
    # TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- observability only.
    # No behavior change. No-op unless HORNELORE_TRUTH_PIPELINE_LOG=1 AND a
    # turn probe is active in this context. A browser-driven POST arrives
    # outside the turn task and so marks nothing --- that zero is the
    # evidence, not a defect (see services/truth_pipeline_probe.py).
    try:
        from .services import truth_pipeline_probe as _tp
        _tp.mark("family_truth_written", "family_truth_notes")
    except Exception:
        pass
    return {
        "id": nid,
        "person_id": person_id,
        "body": body or "",
        "source_kind": source_kind or "chat",
        "source_ref": source_ref or "",
        "created_at": now,
        "created_by": created_by or "system",
        "review_locked": 0,
    }


def ft_list_notes(person_id: str, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    rows = con.execute(
        "SELECT id,person_id,body,source_kind,source_ref,created_at,created_by,review_locked "
        "FROM family_truth_notes WHERE person_id=? "
        "ORDER BY created_at ASC LIMIT ? OFFSET ?;",
        (person_id, int(limit), int(offset)),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def ft_get_note(note_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    r = con.execute(
        "SELECT id,person_id,body,source_kind,source_ref,created_at,created_by,review_locked "
        "FROM family_truth_notes WHERE id=?;",
        (note_id,),
    ).fetchone()
    con.close()
    return dict(r) if r else None


def ft_add_row(
    person_id: str,
    field: str,
    source_says: str,
    note_id: Optional[str] = None,
    subject_name: str = "",
    relationship: str = "self",
    status: str = "needs_verify",
    approved_value: str = "",
    qualification: str = "",
    confidence: float = 0.0,
    narrative_role: str = "",
    meaning_tags: Optional[List[str]] = None,
    provenance: Optional[Dict[str, Any]] = None,
    extraction_method: str = "manual",
    legacy_suspect: int = 0,
    source_fact_id: str = "",
) -> Dict[str, Any]:
    """Create a new structured proposal row in family_truth_rows.

    Status defaults to `needs_verify`. `approve` and `approve_q` are only set
    through the review endpoints or the promotion flow.
    """
    if status not in FT_ROW_STATUSES:
        raise ValueError(f"invalid status {status!r}, expected one of {FT_ROW_STATUSES}")
    init_db()
    rid = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        """
        INSERT INTO family_truth_rows(
          id, person_id, note_id, subject_name, relationship, field,
          source_says, approved_value, status, qualification,
          reviewer, reviewed_at, confidence, narrative_role, meaning_tags,
          provenance, legacy_suspect, extraction_method, source_fact_id,
          created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        (
            rid,
            person_id,
            note_id,
            subject_name or "",
            relationship or "self",
            field,
            source_says or "",
            approved_value or "",
            status,
            qualification or "",
            "",
            "",
            float(confidence or 0.0),
            narrative_role or "",
            _json_dump(meaning_tags or []),
            _json_dump(provenance or {}),
            int(legacy_suspect or 0),
            extraction_method or "manual",
            source_fact_id or "",
            now,
            now,
        ),
    )
    con.commit()
    con.close()
    # TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- observability only.
    # No behavior change. No-op unless HORNELORE_TRUTH_PIPELINE_LOG=1 AND a
    # turn probe is active in this context. A browser-driven POST arrives
    # outside the turn task and so marks nothing --- that zero is the
    # evidence, not a defect (see services/truth_pipeline_probe.py).
    try:
        from .services import truth_pipeline_probe as _tp
        _tp.mark("family_truth_written", "family_truth_rows")
    except Exception:
        pass
    return ft_get_row(rid) or {}


def ft_get_row(row_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    r = con.execute(
        "SELECT * FROM family_truth_rows WHERE id=?;", (row_id,)
    ).fetchone()
    con.close()
    if not r:
        return None
    d = dict(r)
    d["meaning_tags"] = _json_load(d.get("meaning_tags"), [])
    d["provenance"] = _json_load(d.get("provenance"), {})
    return d


def ft_list_rows(
    person_id: str,
    status: Optional[Union[str, List[str]]] = None,
    include_suspect: bool = True,
    subject_name: Optional[str] = None,
    field: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    where = ["person_id = ?"]
    params: List[Any] = [person_id]
    if status:
        if isinstance(status, str):
            status_list = [s.strip() for s in status.split(",") if s.strip()]
        else:
            status_list = list(status)
        if status_list:
            where.append(f"status IN ({','.join('?' * len(status_list))})")
            params.extend(status_list)
    if not include_suspect:
        where.append("legacy_suspect = 0")
    if subject_name:
        where.append("subject_name = ?")
        params.append(subject_name)
    if field:
        where.append("field = ?")
        params.append(field)
    sql = (
        "SELECT * FROM family_truth_rows WHERE " + " AND ".join(where) +
        " ORDER BY created_at ASC LIMIT ? OFFSET ?;"
    )
    params.extend([int(limit), int(offset)])
    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["meaning_tags"] = _json_load(d.get("meaning_tags"), [])
        d["provenance"] = _json_load(d.get("provenance"), {})
        out.append(d)
    return out


def ft_update_row(
    row_id: str,
    status: Optional[str] = None,
    approved_value: Optional[str] = None,
    qualification: Optional[str] = None,
    reviewer: Optional[str] = None,
    subject_name: Optional[str] = None,
    relationship: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Reviewer-facing partial update. Records `reviewed_at` whenever status changes."""
    if status is not None and status not in FT_ROW_STATUSES:
        raise ValueError(f"invalid status {status!r}, expected one of {FT_ROW_STATUSES}")
    init_db()
    current = ft_get_row(row_id)
    if not current:
        return None
    fields: List[str] = []
    params: List[Any] = []
    if status is not None and status != current.get("status"):
        fields.append("status = ?")
        params.append(status)
        fields.append("reviewed_at = ?")
        params.append(_now_iso())
        if reviewer is not None:
            fields.append("reviewer = ?")
            params.append(reviewer)
    elif reviewer is not None:
        fields.append("reviewer = ?")
        params.append(reviewer)
    if approved_value is not None:
        fields.append("approved_value = ?")
        params.append(approved_value)
    if qualification is not None:
        fields.append("qualification = ?")
        params.append(qualification)
    if subject_name is not None:
        fields.append("subject_name = ?")
        params.append(subject_name)
    if relationship is not None:
        fields.append("relationship = ?")
        params.append(relationship)
    if not fields:
        return current
    fields.append("updated_at = ?")
    params.append(_now_iso())
    params.append(row_id)
    con = _connect()
    con.execute(
        f"UPDATE family_truth_rows SET {', '.join(fields)} WHERE id = ?;",
        tuple(params),
    )
    con.commit()
    con.close()
    return ft_get_row(row_id)


def ft_bulk_update_rows(
    row_ids: List[str],
    status: str,
    reviewer: Optional[str] = None,
) -> int:
    """Bulk status update used for e.g. 'bulk dismiss legacy_suspect'. Returns count."""
    if status not in FT_ROW_STATUSES:
        raise ValueError(f"invalid status {status!r}")
    if not row_ids:
        return 0
    init_db()
    now = _now_iso()
    con = _connect()
    placeholders = ",".join("?" * len(row_ids))
    con.execute(
        f"UPDATE family_truth_rows SET status=?, reviewer=COALESCE(?, reviewer), "
        f"reviewed_at=?, updated_at=? WHERE id IN ({placeholders});",
        tuple([status, reviewer, now, now, *row_ids]),
    )
    n = con.total_changes
    con.commit()
    con.close()
    return n


def ft_row_audit(row_id: str) -> Optional[Dict[str, Any]]:
    """Return provenance + full row snapshot for audit UI (Phase 2 surface).

    A full append-only audit log is deferred to Phase 7; for now we return
    the row's current state plus its provenance JSON, which is sufficient
    for the review UI to display where a claim came from.
    """
    row = ft_get_row(row_id)
    if not row:
        return None
    return {
        "row": row,
        "provenance": row.get("provenance") or {},
        "legacy_suspect": row.get("legacy_suspect") or 0,
        "extraction_method": row.get("extraction_method") or "",
        "source_fact_id": row.get("source_fact_id") or "",
    }


def _ft_is_protected_identity_field(field: str) -> bool:
    """True when `field` is one of the five identity-critical fields that
    can never be promoted from a rules_fallback row."""
    return str(field or "").strip() in FT_PROTECTED_IDENTITY_FIELDS


def _ft_promoted_content_hash(
    value: str,
    qualification: str,
    status: str,
    extraction_method: str,
    subject_name: str,
    relationship: str,
    source_says: str,
) -> str:
    """Stable hash over the fields that define 'meaning' of a promoted row.

    If this hash is unchanged on an upsert, the row is considered a no-op
    and `updated_at` is NOT touched — which is what makes idempotency
    directly provable with a timestamp check.
    """
    import hashlib
    payload = "\x1e".join([
        value or "",
        qualification or "",
        status or "",
        extraction_method or "",
        subject_name or "",
        relationship or "",
        source_says or "",
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def ft_get_promoted(person_id: str, subject_name: str, field: str) -> Optional[Dict[str, Any]]:
    """Fetch a single promoted row by the natural key."""
    init_db()
    con = _connect()
    r = con.execute(
        "SELECT * FROM family_truth_promoted "
        "WHERE person_id=? AND subject_name=? AND field=?;",
        (person_id, subject_name or "", field),
    ).fetchone()
    con.close()
    return dict(r) if r else None


def ft_list_promoted(
    person_id: str,
    subject_name: Optional[str] = None,
    field: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List promoted rows for a person. Optional filters by subject/field."""
    init_db()
    con = _connect()
    where = ["person_id = ?"]
    params: List[Any] = [person_id]
    if subject_name is not None:
        where.append("subject_name = ?")
        params.append(subject_name)
    if field is not None:
        where.append("field = ?")
        params.append(field)
    sql = (
        "SELECT * FROM family_truth_promoted WHERE " + " AND ".join(where) +
        " ORDER BY updated_at DESC LIMIT ? OFFSET ?;"
    )
    params.extend([int(limit), int(offset)])
    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def ft_promoted_upsert(row_id: str, reviewer: str = "") -> Dict[str, Any]:
    """Upsert a proposal row into family_truth_promoted, keyed by
    (person_id, subject_name, field).

    Returns a dict with:
      - ok          : bool
      - op          : 'created' | 'updated' | 'noop' | 'blocked' | 'skipped'
      - reason      : str  (only for blocked/skipped)
      - record      : dict (the promoted row, or None)
      - row_id      : the source row id
      - from_status : the source row status at time of promotion

    Rules:
      - Source row must exist and have status in ('approve','approve_q').
        Anything else returns op='skipped' with reason='not_approved'.
      - Protected identity fields coming from rules_fallback are refused
        with op='blocked' reason='protected_identity_rules_fallback'.
      - When the content hash is unchanged the existing record's
        updated_at is not touched; op='noop' is returned.
      - When no prior record exists the row is INSERTed; op='created'.
      - When values differ from the existing record the row is UPDATEd;
        op='updated' and updated_at is refreshed.
    """
    init_db()
    src = ft_get_row(row_id)
    if not src:
        return {"ok": False, "op": "skipped", "reason": "row_not_found",
                "record": None, "row_id": row_id, "from_status": None}

    if src.get("status") not in ("approve", "approve_q"):
        return {"ok": False, "op": "skipped", "reason": "not_approved",
                "record": None, "row_id": row_id,
                "from_status": src.get("status")}

    field = (src.get("field") or "").strip()
    extraction = (src.get("extraction_method") or "").strip()
    if _ft_is_protected_identity_field(field) and extraction == "rules_fallback":
        return {"ok": False, "op": "blocked",
                "reason": "protected_identity_rules_fallback",
                "record": None, "row_id": row_id,
                "from_status": src.get("status")}

    person_id = src["person_id"]
    subject_name = (src.get("subject_name") or "").strip()
    relationship = (src.get("relationship") or "self").strip()
    source_says = src.get("source_says") or ""
    qualification = src.get("qualification") or ""
    status = src.get("status") or "approve"
    # The canonical value: prefer a reviewer-approved value; otherwise fall
    # back to the narrator's source_says. This matches the review UI, which
    # stores explicit approved_value only when the reviewer edits the text.
    value = (src.get("approved_value") or "").strip() or source_says
    confidence = float(src.get("confidence") or 0.0)
    note_id = src.get("note_id") or ""

    new_hash = _ft_promoted_content_hash(
        value=value,
        qualification=qualification,
        status=status,
        extraction_method=extraction,
        subject_name=subject_name,
        relationship=relationship,
        source_says=source_says,
    )

    existing = ft_get_promoted(person_id, subject_name, field)
    now = _now_iso()
    con = _connect()
    if existing is None:
        pid = _uuid()
        con.execute(
            """
            INSERT INTO family_truth_promoted(
              id, person_id, subject_name, relationship, field, value,
              qualification, status, source_row_id, source_note_id,
              source_says, extraction_method, confidence, reviewer,
              content_hash, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                pid, person_id, subject_name, relationship, field, value,
                qualification, status, row_id, note_id, source_says,
                extraction, confidence, reviewer or "",
                new_hash, now, now,
            ),
        )
        con.commit()
        con.close()
        record = ft_get_promoted(person_id, subject_name, field)
        return {"ok": True, "op": "created", "record": record,
                "row_id": row_id, "from_status": status}

    # Already exists — compare hashes for true no-op semantics.
    if existing.get("content_hash") == new_hash:
        con.close()
        return {"ok": True, "op": "noop", "record": existing,
                "row_id": row_id, "from_status": status}

    con.execute(
        """
        UPDATE family_truth_promoted SET
          subject_name = ?, relationship = ?, field = ?, value = ?,
          qualification = ?, status = ?, source_row_id = ?,
          source_note_id = ?, source_says = ?, extraction_method = ?,
          confidence = ?, reviewer = ?, content_hash = ?, updated_at = ?
        WHERE id = ?;
        """,
        (
            subject_name, relationship, field, value, qualification, status,
            row_id, note_id, source_says, extraction, confidence,
            reviewer or existing.get("reviewer") or "",
            new_hash, now, existing["id"],
        ),
    )
    con.commit()
    con.close()
    record = ft_get_promoted(person_id, subject_name, field)
    return {"ok": True, "op": "updated", "record": record,
            "row_id": row_id, "from_status": status}


def ft_promote_row(row_id: str, reviewer: str = "", qualification: str = "") -> Dict[str, Any]:
    """WO-13 Phase 7 — real promotion semantics.

    Flow:
      1. Flip the source row's status to 'approve' (or 'approve_q' if a
         qualification is supplied) — preserves prior Phase 2 semantics.
      2. UPSERT into family_truth_promoted keyed by
         (person_id, subject_name, field). This is the authoritative truth
         layer that downstream consumers will read from in Phase 8.

    The return shape is:
      {
        "row":      <updated proposal row>,
        "promoted": <op result from ft_promoted_upsert>,
      }

    Idempotency is guaranteed by the content_hash check inside
    ft_promoted_upsert — calling ft_promote_row a second time with the same
    inputs returns op='noop' and does NOT advance updated_at.

    Protected identity fields from rules_fallback are still blocked: the
    source row's status flip still happens (a reviewer DID approve the
    claim, after all), but the UPSERT returns op='blocked' so no
    promoted-truth record is ever created for a rules_fallback identity
    field. Downstream readers never see it.
    """
    target_status = "approve_q" if (qualification or "").strip() else "approve"
    updated = ft_update_row(
        row_id,
        status=target_status,
        qualification=qualification or None,
        reviewer=reviewer or None,
    )
    if not updated:
        return {"row": None, "promoted": {
            "ok": False, "op": "skipped", "reason": "row_not_found",
            "record": None, "row_id": row_id, "from_status": None,
        }}
    promoted = ft_promoted_upsert(row_id, reviewer=reviewer or "")
    return {"row": updated, "promoted": promoted}


def ft_promote_all_approved(person_id: str, reviewer: str = "") -> Dict[str, Any]:
    """Bulk-upsert every approve/approve_q row for a person into
    family_truth_promoted. Drives the 'Promote approved' button in the
    Phase 6 review drawer.

    Returns counts per op-class plus the full list of results so the
    caller can show a detailed summary if desired.
    """
    init_db()
    approved = ft_list_rows(person_id=person_id, status=["approve", "approve_q"])
    results: List[Dict[str, Any]] = []
    counts = {"created": 0, "updated": 0, "noop": 0, "blocked": 0, "skipped": 0}
    for r in approved:
        res = ft_promoted_upsert(r["id"], reviewer=reviewer or "")
        results.append(res)
        op = res.get("op", "skipped")
        if op in counts:
            counts[op] += 1
    return {
        "person_id": person_id,
        "eligible": len(approved),
        "counts": counts,
        "results": results,
    }


# -----------------------------------------------------------------------------
# WO-13 Phase 8 — profile builder + backfill
# -----------------------------------------------------------------------------
#
# build_profile_from_promoted assembles a profile_json-shaped dict from
# family_truth_promoted. It is the single server-side rewire that makes
# Phase 8's "make truth visible" guarantee work — every downstream
# surface (profile form, obituary, memoir source, timeline spine, chat
# context) reads from state.profile on the client, which is populated
# from GET /api/profiles/{id}, which calls this function when
# HORNELORE_TRUTH_V2_PROFILE is on.
#
# The mapping from promoted-truth field names to profile_json.basics
# keys is deliberately narrow: only the 5 protected identity fields
# overlap directly. Everything else in basics.* (culture, country,
# pronouns, language, legal*, timeOfBirth*, zodiac*, placeOfBirth{Raw,
# Normalized}) passes through unchanged from the legacy profile_json
# blob, as do kinship[] and pets[]. This is a hybrid read: truth for
# what has been promoted, legacy for everything else.
#
# Free-form promoted rows (employment, marriage, residence, education,
# ...) go into a new basics.truth[] sidecar list. approve_q rows carry
# their qualification into basics._qualifications[field] AND into the
# truth[] entry for the same field.
#
# Empty-promoted fallback: if a person has zero promoted rows, the
# function returns the legacy profile_json unchanged so the first
# flag-flip on an unreviewed narrator produces the same output as
# flag-off. No empty-UI regression.

_PROMOTED_TO_BASICS: Dict[str, str] = {
    "personal.fullName":      "fullname",
    "personal.preferredName": "preferred",
    "personal.dateOfBirth":   "dob",
    "personal.placeOfBirth":  "pob",
    "personal.birthOrder":    "birthOrder",
}

# Inverse of _PROMOTED_TO_BASICS — used by the backfill helper.
_BASICS_TO_PROMOTED: Dict[str, str] = {v: k for k, v in _PROMOTED_TO_BASICS.items()}


# BUG-API-PROFILES-DROPS-INTAKE-KEYS-01 (2026-06-16):
# The operator intake orchestrator (WO-OPERATOR-NEW-NARRATOR-INTAKE-
# FORM-01 Phase 2B) writes to `profile_json.personal.{fullName,
# preferredName, dateOfBirth, placeOfBirth, currentResidence,
# pronouns, faithRaised, currentFaith, culture, languagesAtHome, ...}`
# — NOT to `profile_json.basics.{...}` which is the legacy FE shape.
#
# build_profile_from_promoted (below) used to read only from
# `legacy_basics` + promoted-truth rows. That meant any narrator
# created via the intake form returned `basics: {}` here (because the
# intake didn't write to basics) AND had no promoted rows yet
# (because intake doesn't run through the truth pipeline). The FE's
# state.profile.basics ended up empty → Bio Builder questionnaire
# hydration found nothing → operator saw a blank form even though
# bio_facts + profile_json had everything.
#
# Fix: project intake-written `profile_json.personal.*` into `basics.*`
# whenever the basics slot is empty. Promoted-truth values STILL win
# over both intake personal AND legacy basics — the precedence order
# is: promoted > intake personal > legacy basics. The structured
# blocks (parents, siblings, spouses, children, education, military,
# faith, today) are also passed through to the FE response shape so
# any consumer that wants them can read them.
_INTAKE_PERSONAL_TO_BASICS: Dict[str, str] = {
    "fullName":         "fullname",
    "preferredName":    "preferred",
    "dateOfBirth":      "dob",
    "placeOfBirth":     "pob",
    "birthOrder":       "birthOrder",
    "pronouns":         "pronouns",
    "currentResidence": "currentResidence",
    "timeOfBirth":      "timeOfBirth",
    "zodiacSign":       "zodiacSign",
    # Faith mirror — intake writes these into profile_json.personal
    "faithRaised":      "faithRaised",
    "currentFaith":     "currentFaith",
    "culture":          "culture",
    "languagesAtHome":  "language",
}

# Intake-written structured blocks that should pass through to the FE
# response regardless of the truth_v2 flag state. None of these are in
# the legacy basics-only shape; surfacing them lets the FE consume
# parents/siblings/etc. that the operator entered via the intake form.
_INTAKE_STRUCTURED_KEYS: Tuple[str, ...] = (
    "personal", "parents", "siblings", "spouses", "spouse",
    "children", "education", "community", "marriage",
    "military", "faith", "today",
)


def _project_intake_personal_into_basics(
    legacy_profile: Dict[str, Any], basics: Dict[str, Any],
) -> None:
    """Project intake-written profile_json.personal.* into basics.*
    when the basics slot is empty. Mutates `basics` in place. Safe to
    call when legacy_profile.personal is missing — no-op."""
    intake_personal = legacy_profile.get("personal") or {}
    if not isinstance(intake_personal, dict):
        return
    for intake_key, basics_key in _INTAKE_PERSONAL_TO_BASICS.items():
        v = intake_personal.get(intake_key)
        if v in (None, ""):
            continue
        if not basics.get(basics_key):
            basics[basics_key] = v


def build_profile_from_promoted(person_id: str) -> Dict[str, Any]:
    """Assemble a profile_json-shaped dict from family_truth_promoted.

    Hybrid read: promoted-truth data takes precedence where it exists,
    legacy profile_json fills in everywhere else.

    Returns a dict with the same shape api_get_profile currently
    returns under key ``profile``:

        {
          "basics": {
              "fullname": ..., "preferred": ..., "dob": ..., "pob": ...,
              "birthOrder": ...,
              # unmapped basics pass through from legacy:
              "culture": ..., "country": ..., "pronouns": ...,
              "phonetic": ..., "language": ...,
              "legalFirstName": ..., "legalMiddleName": ..., "legalLastName": ...,
              "timeOfBirth": ..., "timeOfBirthDisplay": ...,
              "birthOrderCustom": ..., "zodiacSign": ...,
              "placeOfBirthRaw": ..., "placeOfBirthNormalized": ...,
              # new sidecar keys (additive — normalizeProfile tolerates them):
              "_qualifications": { "<field>": "<qualification text>" },
              "truth": [ { "subject_name", "relationship", "field",
                           "value", "qualification", "status", "reviewer",
                           "source_row_id", "updated_at" }, ... ],
          },
          "kinship": [ ... ],   # passed through unchanged
          "pets":    [ ... ],   # passed through unchanged
        }
    """
    init_db()

    # Always start from the legacy blob — this is the passthrough layer
    # for unmapped basics.* fields, kinship, and pets.
    legacy = get_profile(person_id) or {"profile_json": {}}
    legacy_profile = dict(legacy.get("profile_json") or {})
    legacy_basics = dict(legacy_profile.get("basics") or {})
    legacy_kinship = list(legacy_profile.get("kinship") or [])
    legacy_pets = list(legacy_profile.get("pets") or [])

    # BUG-API-PROFILES-DROPS-INTAKE-KEYS-01 fix: project intake-written
    # profile_json.personal.* into basics.* when the basics slot is
    # empty. This makes the operator intake form data visible to the
    # FE without requiring the operator to also fill out the legacy
    # basic-info form.
    _project_intake_personal_into_basics(legacy_profile, legacy_basics)

    # Pass through the intake-written structured blocks (parents,
    # siblings, spouses, children, education, military, faith, today)
    # so the FE can render them. They sit alongside basics/kinship/pets
    # rather than replacing them — FE consumers can read whichever
    # shape they expect.
    structured_passthrough: Dict[str, Any] = {}
    for k in _INTAKE_STRUCTURED_KEYS:
        if k in legacy_profile and legacy_profile[k]:
            structured_passthrough[k] = legacy_profile[k]

    promoted_rows = ft_list_promoted(person_id, limit=10_000, offset=0)

    if not promoted_rows:
        # Empty-promoted fallback: behave exactly like flag-off.
        out: Dict[str, Any] = {
            "basics": legacy_basics,
            "kinship": legacy_kinship,
            "pets": legacy_pets,
        }
        out.update(structured_passthrough)
        return out

    # Start from the legacy basics so unmapped fields pass through.
    basics: Dict[str, Any] = dict(legacy_basics)

    # approve_q qualification sidecar (by promoted-truth field name).
    qualifications: Dict[str, str] = {}

    # Free-form promoted rows go here (everything that doesn't map to a
    # protected identity field).
    truth_rows: List[Dict[str, Any]] = []

    for row in promoted_rows:
        field = str(row.get("field") or "")
        status = str(row.get("status") or "")
        value = row.get("value") or ""
        qualification = row.get("qualification") or ""

        if field in _PROMOTED_TO_BASICS:
            # Protected identity field — write directly into basics.
            # The Phase 7 blocking rule already filtered out
            # rules_fallback for protected fields, so anything in
            # promoted here is safe to render.
            target_key = _PROMOTED_TO_BASICS[field]
            basics[target_key] = value
            if qualification:
                qualifications[field] = qualification
        else:
            # Free-form field — append to truth[] sidecar.
            truth_rows.append({
                "subject_name":  row.get("subject_name") or "",
                "relationship":  row.get("relationship") or "self",
                "field":         field,
                "value":         value,
                "qualification": qualification,
                "status":        status,
                "reviewer":      row.get("reviewer") or "",
                "source_row_id": row.get("source_row_id") or "",
                "updated_at":    row.get("updated_at") or "",
            })
            if qualification:
                qualifications[field] = qualification

    if qualifications:
        basics["_qualifications"] = qualifications
    if truth_rows:
        basics["truth"] = truth_rows

    out: Dict[str, Any] = {
        "basics": basics,
        "kinship": legacy_kinship,
        "pets": legacy_pets,
    }
    # BUG-API-PROFILES-DROPS-INTAKE-KEYS-01 fix: pass through intake-
    # written structured blocks even when promoted rows exist. Promoted
    # truth handles protected identity fields via basics.*; intake-
    # written parents/siblings/etc. should still surface.
    out.update(structured_passthrough)
    return out


def ft_backfill_from_profile_json(person_id: str) -> Dict[str, Any]:
    """Seed shadow notes + proposal rows from existing profile_json.

    For each protected identity field (5) that is present and
    non-empty on the legacy basics.*, create:
      1. A shadow note in family_truth_notes with
           source_kind='backfill'
           source_ref='profile_json.basics.<key>'
           created_by='backfill'
      2. A proposal row in family_truth_rows with
           status            = 'needs_verify'
           extraction_method = 'manual'
           confidence        = 1.0
           source_says       = <current value>
           subject_name      = <display_name>
           relationship      = 'self'
           field             = <promoted-truth field name>

    Does NOT auto-promote. Does NOT write to family_truth_promoted.

    Idempotent: skips any field that already has ANY row (in any
    status) for (person_id, subject_name=display_name, field=<name>),
    so re-running the backfill on a partially-reviewed narrator
    doesn't create duplicates.

    Returns {person_id, created_rows, skipped_existing, skipped_empty,
             reference_refused}.
    """
    init_db()

    person = get_person(person_id)
    if not person:
        return {
            "person_id": person_id,
            "created_rows": 0,
            "skipped_existing": 0,
            "skipped_empty": 0,
            "reference_refused": False,
            "error": "person_not_found",
        }

    # Reference narrators never get a backfill — same guard as the rest
    # of the FT write path.
    if is_reference_narrator(person_id):
        return {
            "person_id": person_id,
            "created_rows": 0,
            "skipped_existing": 0,
            "skipped_empty": 0,
            "reference_refused": True,
        }

    display_name = str(person.get("display_name") or "").strip() or "(unknown)"

    legacy = get_profile(person_id) or {"profile_json": {}}
    legacy_profile = dict(legacy.get("profile_json") or {})
    legacy_basics = dict(legacy_profile.get("basics") or {})

    # Build an index of existing proposal rows for this person so we
    # can do idempotent skip on (subject_name, field).
    existing_rows = ft_list_rows(person_id=person_id, limit=10_000, offset=0)
    existing_keys: set = set()
    for r in existing_rows:
        k = (str(r.get("subject_name") or ""), str(r.get("field") or ""))
        existing_keys.add(k)

    created = 0
    skipped_existing = 0
    skipped_empty = 0

    for basics_key, ft_field in _BASICS_TO_PROMOTED.items():
        raw_value = legacy_basics.get(basics_key)
        value = str(raw_value or "").strip()
        if not value:
            skipped_empty += 1
            continue

        key = (display_name, ft_field)
        if key in existing_keys:
            skipped_existing += 1
            continue

        note = ft_add_note(
            person_id=person_id,
            body=value,
            source_kind="backfill",
            source_ref=f"profile_json.basics.{basics_key}",
            created_by="backfill",
        )
        ft_add_row(
            person_id=person_id,
            note_id=note["id"],
            subject_name=display_name,
            relationship="self",
            field=ft_field,
            source_says=value,
            status="needs_verify",
            confidence=1.0,
            extraction_method="manual",
        )
        created += 1

    logger.info(
        "ft_backfill_from_profile_json: person_id=%s created=%d skipped_existing=%d skipped_empty=%d",
        person_id, created, skipped_existing, skipped_empty,
    )

    return {
        "person_id": person_id,
        "created_rows": created,
        "skipped_existing": skipped_existing,
        "skipped_empty": skipped_empty,
        "reference_refused": False,
    }


# -----------------------------------------------------------------------------
# Life phases
# -----------------------------------------------------------------------------
def add_life_phase(
    person_id: str,
    title: str,
    start_date: str = "",
    end_date: str = "",
    date_precision: str = "year",
    description: str = "",
    ord: int = 0,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_db()
    pid_val = _uuid()
    now = _now_iso()
    con = _connect()
    con.execute(
        """
        INSERT INTO life_phases(
          id,person_id,title,start_date,end_date,date_precision,
          description,ord,created_at,meta_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?);
        """,
        (
            pid_val, person_id, title,
            start_date or "", end_date or "", date_precision or "year",
            description or "", int(ord or 0), now, _json_dump(meta or {}),
        ),
    )
    con.commit()
    con.close()
    return {
        "id": pid_val, "person_id": person_id, "title": title,
        "start_date": start_date, "end_date": end_date,
        "date_precision": date_precision, "description": description,
        "ord": int(ord or 0), "created_at": now,
    }


def list_life_phases(person_id: str) -> List[Dict[str, Any]]:
    init_db()
    con = _connect()
    rows = con.execute(
        """
        SELECT id,person_id,title,start_date,end_date,date_precision,
               description,ord,created_at,meta_json
        FROM life_phases WHERE person_id=? ORDER BY ord ASC, start_date ASC;
        """,
        (person_id,),
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = _json_load(d.pop("meta_json", "{}"), {})
        out.append(d)
    return out


def delete_life_phase(phase_id: str) -> bool:
    init_db()
    con = _connect()
    cur = con.execute("DELETE FROM life_phases WHERE id=?;", (phase_id,))
    con.commit()
    con.close()
    return cur.rowcount > 0


# -----------------------------------------------------------------------------
# Enhanced timeline event  (wraps existing add_timeline_event with new fields)
# -----------------------------------------------------------------------------
def add_calendar_event(
    person_id: str,
    title: str,
    start_date: str,
    end_date: str = "",
    date_precision: str = "exact_day",
    display_date: str = "",
    body: str = "",
    kind: str = "event",
    is_approximate: bool = False,
    confidence: float = 1.0,
    status: str = "reviewed",
    source_session_ids: Optional[List[str]] = None,
    source_fact_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    phase_id: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extended timeline event with full calendar metadata.
    Adds to timeline_events table using the new columns.
    """
    init_db()
    eid = _uuid()
    now = _now_iso()
    full_meta = dict(meta or {})
    con = _connect()
    con.execute(
        """
        INSERT INTO timeline_events(
          id,person_id,date,title,body,kind,created_at,meta_json,
          end_date,date_precision,is_approximate,confidence,status,
          source_session_ids,source_fact_ids,tags,display_date,phase_id
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        (
            eid, person_id, start_date, title, body or "", kind or "event", now,
            _json_dump(full_meta),
            end_date or "", date_precision or "exact_day",
            1 if is_approximate else 0, float(confidence or 1.0),
            status or "reviewed",
            _json_dump(source_session_ids or []),
            _json_dump(source_fact_ids or []),
            _json_dump(tags or []),
            display_date or start_date,
            phase_id or "",
        ),
    )
    con.commit()
    con.close()
    return {
        "id": eid, "person_id": person_id,
        "start_date": start_date, "end_date": end_date,
        "title": title, "body": body, "kind": kind,
        "date_precision": date_precision, "display_date": display_date or start_date,
        "is_approximate": is_approximate, "confidence": float(confidence or 1.0),
        "status": status, "created_at": now,
        "source_session_ids": source_session_ids or [],
        "source_fact_ids": source_fact_ids or [],
        "tags": tags or [],
        "phase_id": phase_id,
    }


def list_calendar_events(
    person_id: str, limit: int = 500, offset: int = 0
) -> List[Dict[str, Any]]:
    """Return enriched timeline events with calendar fields."""
    init_db()
    con = _connect()
    rows = con.execute(
        """
        SELECT id,person_id,date,title,body,kind,created_at,meta_json,
               COALESCE(end_date,'') as end_date,
               COALESCE(date_precision,'exact_day') as date_precision,
               COALESCE(is_approximate,0) as is_approximate,
               COALESCE(confidence,1.0) as confidence,
               COALESCE(status,'reviewed') as status,
               COALESCE(source_session_ids,'[]') as source_session_ids,
               COALESCE(source_fact_ids,'[]') as source_fact_ids,
               COALESCE(tags,'[]') as tags,
               COALESCE(display_date,'') as display_date,
               COALESCE(phase_id,'') as phase_id
        FROM timeline_events
        WHERE person_id=?
        ORDER BY date ASC, created_at ASC
        LIMIT ? OFFSET ?;
        """,
        (person_id, int(limit), int(offset)),
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = _json_load(d.pop("meta_json", "{}"), {})
        d["is_approximate"] = bool(d.get("is_approximate"))
        d["source_session_ids"] = _json_load(d.get("source_session_ids"), [])
        d["source_fact_ids"] = _json_load(d.get("source_fact_ids"), [])
        d["tags"] = _json_load(d.get("tags"), [])
        d["start_date"] = d.pop("date", "")
        if not d.get("display_date"):
            d["display_date"] = d["start_date"]
        out.append(d)
    return out

# =============================================================================
# v6.1 Track A — Segment Flags (Safety)
# =============================================================================

def save_segment_flag(
    session_id: str,
    question_id: Optional[str],
    section_id: Optional[str],
    sensitive: bool,
    sensitive_category: str,
    excluded_from_memoir: bool = True,
    private: bool = True,
) -> str:
    """Create a segment flag record. Returns the flag id.
    Uses INSERT OR IGNORE so retrying the same answer never creates duplicates.

    BUG-DBLOCK-01 PATCH 1A (2026-04-30): wrapped in try/except/finally so a
    raised sqlite3.Error (e.g. FOREIGN KEY constraint failed when the
    parent interview_sessions row is missing) cannot leak the connection
    with an open transaction. Without this guard, a single FK failure
    here held the write lock for the duration of process garbage
    collection, cascading into 5s/10s/15s busy_timeout failures across
    set_session_softened, save_safety_event, and init_db (called from
    export_turns) — the exact safety-path lock chain logged on the
    2026-04-30 golfball harness Turn 6 (+4 lock events, deterministic
    across two consecutive runs).
    """
    con = _connect()
    now = _now_iso()
    flag_id = _uuid()
    try:
        con.execute(
            """
            INSERT OR IGNORE INTO segment_flags
              (id, session_id, question_id, section_id,
               sensitive, sensitive_category, excluded_from_memoir, private, deleted, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
            """,
            (flag_id, session_id, question_id, section_id,
             int(sensitive), sensitive_category, int(excluded_from_memoir), int(private), now),
        )
        # If a flag for this (session, question) pair already existed, fetch the existing id
        existing = con.execute(
            "SELECT id FROM segment_flags WHERE session_id=? AND question_id=?;",
            (session_id, question_id),
        ).fetchone()
        con.commit()
        return (existing["id"] if existing else flag_id)
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def get_segment_flags(session_id: str) -> List[Dict]:
    """Return all segment flags for a session."""
    con = _connect()
    rows = con.execute(
        "SELECT * FROM segment_flags WHERE session_id=? AND deleted=0 ORDER BY created_at;",
        (session_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_segment_flags_by_category(
    sensitive_category: str,
    limit: int = 50,
) -> List[Dict]:
    """WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — cross-session
    query for operator review surfaces.

    Returns segment_flags rows matching `sensitive_category` across
    ALL sessions, newest-first, capped at `limit`. Used by the
    operator past-tense flag review endpoint to surface flags that
    arrived during sessions the operator hasn't audited yet.

    Operator-side only — narrators never query this. The endpoint
    consuming this accessor is gated by an env flag (HORNELORE_
    OPERATOR_PAST_TENSE_REVIEW=1) so it doesn't advertise itself.

    The result is read-only metadata: the operator decides next
    actions (no_action / follow_up_outside_session / convert_to_
    active_concern) in a future endpoint (Phase 3 of the WO).
    """
    if not sensitive_category:
        return []
    # Defensive limit clamp.
    try:
        n = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        n = 50
    con = _connect()
    rows = con.execute(
        "SELECT * FROM segment_flags "
        "WHERE sensitive_category=? AND deleted=0 "
        "ORDER BY created_at DESC LIMIT ?;",
        (sensitive_category, n),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def delete_segment_flag(flag_id: str) -> bool:
    """Soft-delete a segment flag (user elected to remove sensitive segment)."""
    con = _connect()
    con.execute(
        "UPDATE segment_flags SET deleted=1 WHERE id=?;",
        (flag_id,),
    )
    changed = con.total_changes
    con.commit()
    con.close()
    return changed > 0


def include_segment_in_memoir(flag_id: str) -> bool:
    """User explicitly opts a sensitive segment into memoir drafts."""
    con = _connect()
    con.execute(
        "UPDATE segment_flags SET excluded_from_memoir=0, private=0 WHERE id=?;",
        (flag_id,),
    )
    changed = con.total_changes
    con.commit()
    con.close()
    return changed > 0


# v6.2 — lookup-by-(session_id, question_id) for frontend which uses those identifiers
def update_segment_flag_by_question(
    session_id: str, question_id: str, include_in_memoir: bool
) -> bool:
    """Toggle memoir inclusion for the flag matching (session_id, question_id)."""
    con = _connect()
    excluded = 0 if include_in_memoir else 1
    private_val = 0 if include_in_memoir else 1
    con.execute(
        "UPDATE segment_flags SET excluded_from_memoir=?, private=? "
        "WHERE session_id=? AND question_id=? AND deleted=0;",
        (excluded, private_val, session_id, question_id),
    )
    changed = con.total_changes
    con.commit()
    con.close()
    return changed > 0


def delete_segment_flag_by_question(session_id: str, question_id: str) -> bool:
    """Soft-delete the flag matching (session_id, question_id)."""
    con = _connect()
    con.execute(
        "UPDATE segment_flags SET deleted=1 WHERE session_id=? AND question_id=?;",
        (session_id, question_id),
    )
    changed = con.total_changes
    con.commit()
    con.close()
    return changed > 0


# =============================================================================
# WO-LORI-SAFETY-INTEGRATION-01 Phase 3 — Safety Events (operator surface)
# =============================================================================

def save_safety_event(
    session_id: str,
    person_id: Optional[str],
    category: str,
    matched_phrase: Optional[str],
    turn_excerpt: Optional[str],
) -> str:
    """Persist a safety trigger as an operator-review event. Returns the
    new event id. Called from chat_ws._safety_notify_operator on every
    Phase 1 safety scan that fires.

    Stores at most 200 chars of turn_excerpt and 60 chars of
    matched_phrase. May raise sqlite errors;
    chat_ws._safety_notify_operator catches and logs so the chat turn
    still proceeds. (Defensive init_db() call here so the helper works
    even on a fresh environment that hasn't initialized the schema yet.)

    BUG-DBLOCK-01 PATCH 4 (2026-05-02): mirror save_segment_flag's
    explicit rollback pattern. Pre-patch, an INSERT failure (e.g.
    UNIQUE/FK constraint violation, schema drift) closed the connection
    in `finally` without rolling back, relying on Python's sqlite3
    driver auto-rollback at GC time — defensive but asymmetric with the
    sibling safety-path writes that all use the explicit
    try/except sqlite3.Error → rollback → raise → finally close shape.
    No behavior change on success; tighter cleanup on failure paths.
    """
    init_db()
    con = _connect()
    try:
        now = _now_iso()
        event_id = _uuid()
        con.execute(
            """
            INSERT INTO safety_events
              (id, session_id, person_id, category, matched_phrase,
               turn_excerpt, created_at, acknowledged_at, acknowledged_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL);
            """,
            (
                event_id,
                session_id,
                person_id,
                (category or ""),
                (matched_phrase or "")[:60] if matched_phrase else None,
                (turn_excerpt or "")[:200] if turn_excerpt else None,
                now,
            ),
        )
        con.commit()
        return event_id
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def list_safety_events(
    person_id: Optional[str] = None,
    since_iso: Optional[str] = None,
    unacked_only: bool = False,
    limit: int = 50,
) -> List[Dict]:
    """Return safety events for the operator review surface.

    Filters:
      person_id      — restrict to one narrator
      since_iso      — only events with created_at > since_iso
      unacked_only   — only events without acknowledged_at
      limit          — cap result count (default 50, max 200)

    Returns most recent first. Each row is a dict with id / session_id /
    person_id / category / matched_phrase / turn_excerpt / created_at /
    acknowledged_at / acknowledged_by.
    """
    init_db()
    limit = max(1, min(int(limit or 50), 200))
    where_clauses: List[str] = []
    params: List[Any] = []
    if person_id:
        where_clauses.append("person_id = ?")
        params.append(person_id)
    if since_iso:
        where_clauses.append("created_at > ?")
        params.append(since_iso)
    if unacked_only:
        where_clauses.append("acknowledged_at IS NULL")
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    sql = (
        "SELECT id, session_id, person_id, category, matched_phrase, "
        "turn_excerpt, created_at, acknowledged_at, acknowledged_by "
        "FROM safety_events"
        + where_sql
        + " ORDER BY created_at DESC LIMIT ?;"
    )
    params.append(limit)
    con = _connect()
    try:
        rows = con.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def acknowledge_safety_event(event_id: str, acknowledged_by: Optional[str] = None) -> bool:
    """Mark a safety event as seen-by-operator. Idempotent — re-acking
    a previously-acked event is a no-op (preserves first-ack time)."""
    init_db()
    con = _connect()
    try:
        now = _now_iso()
        cur = con.execute(
            "UPDATE safety_events SET acknowledged_at=?, acknowledged_by=? "
            "WHERE id=? AND acknowledged_at IS NULL;",
            (now, (acknowledged_by or "")[:60], event_id),
        )
        changed = cur.rowcount
        con.commit()
        return changed > 0
    finally:
        con.close()


def count_unacked_safety_events(person_id: Optional[str] = None) -> int:
    """Lightweight count for the Bug Panel polling badge. Operator UI
    polls this on a 30s timer; only fetches the full event list when
    the count is non-zero."""
    init_db()
    con = _connect()
    try:
        if person_id:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM safety_events "
                "WHERE acknowledged_at IS NULL AND person_id=?;",
                (person_id,),
            ).fetchone()
        else:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM safety_events WHERE acknowledged_at IS NULL;"
            ).fetchone()
        return int(row["n"] or 0) if row else 0
    finally:
        con.close()


def safety_events_digest(
    since_iso: Optional[str] = None,
    person_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Between-session digest: flat counts by narrator + by category.
    Per spec: NO scores, NO severity ranks, NO longitudinal trends.
    Just "what fired, in which session, how often." Operator can
    drill into the full event list via list_safety_events.
    """
    init_db()
    con = _connect()
    try:
        where_clauses: List[str] = []
        params: List[Any] = []
        if since_iso:
            where_clauses.append("created_at > ?")
            params.append(since_iso)
        if person_id:
            where_clauses.append("person_id = ?")
            params.append(person_id)
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Per-category counts
        cat_rows = con.execute(
            "SELECT category, COUNT(*) AS n FROM safety_events"
            + where_sql
            + " GROUP BY category;",
            tuple(params),
        ).fetchall()
        by_category = {(r["category"] or "uncategorized"): int(r["n"]) for r in cat_rows}

        # Per-narrator counts
        nar_rows = con.execute(
            "SELECT person_id, COUNT(*) AS n FROM safety_events"
            + where_sql
            + " GROUP BY person_id;",
            tuple(params),
        ).fetchall()
        by_narrator = {(r["person_id"] or "unknown"): int(r["n"]) for r in nar_rows}

        total_row = con.execute(
            "SELECT COUNT(*) AS n FROM safety_events" + where_sql + ";",
            tuple(params),
        ).fetchone()
        total = int(total_row["n"] or 0) if total_row else 0

        unacked_row = con.execute(
            "SELECT COUNT(*) AS n FROM safety_events"
            + (where_sql + " AND " if where_sql else " WHERE ")
            + "acknowledged_at IS NULL;",
            tuple(params),
        ).fetchone()
        unacked = int(unacked_row["n"] or 0) if unacked_row else 0

        return {
            "since": since_iso,
            "person_id": person_id,
            "total": total,
            "unacknowledged": unacked,
            "by_category": by_category,
            "by_narrator": by_narrator,
        }
    finally:
        con.close()


# =============================================================================
# v6.1 Track A — Softened Interview Mode
# =============================================================================

def set_session_softened(
    session_id: str,
    current_turn: int,
    softened_turns: int = 3,
    trigger: str = "",
) -> None:
    """Mark session as softened for the next N turns.

    BUG-DBLOCK-01 PATCH 1B (2026-04-30): try/except/finally to prevent
    connection leak on sqlite3.Error. Same fatal pattern as
    save_segment_flag pre-patch.

    WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14): trigger param
    records WHICH safety event entered softened state ("acute" or
    "past_tense_acknowledge"). The read-side picks the right prompt
    block and per-state caps from this value. Empty string is the
    legacy/default for any caller that hasn't been updated to pass
    a trigger.

    NOTE: this function CLOBBERS — it overwrites any existing
    softened_until_turn. For nested triggers (acute fires while
    already softened) callers should use extend_session_softened()
    instead, which applies max-not-clobber arithmetic so a shorter
    nested window can't erase the original safety event's reach.
    """
    con = _connect()
    try:
        con.execute(
            """
            UPDATE interview_sessions
            SET interview_softened=1,
                softened_until_turn=?,
                softened_trigger=?,
                softened_initial_n=?
            WHERE id=?;
            """,
            (current_turn + softened_turns, trigger or "", int(softened_turns), session_id),
        )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def extend_session_softened(
    session_id: str,
    current_turn: int,
    softened_turns: int,
    trigger: str = "",
) -> None:
    """WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14) — max-not-
    clobber softened-state extension.

    When a session is already in softened state and a NEW safety
    event fires (acute during past-tense window; past-tense during
    acute window), the until_turn becomes the MAX of:
      - the existing until_turn (preserves the original event's reach)
      - current_turn + softened_turns (the new event's would-be reach)

    The trigger is upgraded to the new value only if it's stronger:
    acute > past_tense_acknowledge > "". A nested past_tense during
    an acute window leaves the trigger as "acute" — the operator
    review surface should still see this as an acute session, even
    if past-tense content arrives mid-window.

    Same DBLOCK-01 try/except/finally posture as set_session_softened.
    """
    con = _connect()
    try:
        # Read existing state under the write lock so we don't race
        # a concurrent caller. SQLite serializes writes anyway, but
        # this keeps the max() arithmetic deterministic if two
        # callers fire in the same connection cycle.
        row = con.execute(
            """
            SELECT COALESCE(softened_until_turn,0) AS u,
                   COALESCE(softened_trigger,'')   AS t,
                   COALESCE(softened_initial_n,0)  AS n
            FROM interview_sessions WHERE id=?;
            """,
            (session_id,),
        ).fetchone()

        existing_until = int(row["u"]) if row else 0
        existing_trigger = (row["t"] if row else "") or ""
        new_until = max(existing_until, current_turn + int(softened_turns))

        # Trigger upgrade hierarchy. Acute beats everything; past-
        # tense beats empty; new "" never overrides existing trigger.
        _hierarchy = {"": 0, "past_tense_acknowledge": 1, "acute": 2}
        eff_trigger = trigger or ""
        if _hierarchy.get(eff_trigger, 0) < _hierarchy.get(existing_trigger, 0):
            eff_trigger = existing_trigger

        con.execute(
            """
            UPDATE interview_sessions
            SET interview_softened=1,
                softened_until_turn=?,
                softened_trigger=?,
                softened_initial_n=?
            WHERE id=?;
            """,
            (new_until, eff_trigger, int(softened_turns), session_id),
        )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def increment_session_turn(session_id: str) -> int:
    """Increment turn counter, returns new count.

    BUG-DBLOCK-01 PATCH 1C (2026-04-30): try/except/finally to prevent
    connection leak on sqlite3.Error.
    """
    con = _connect()
    try:
        con.execute(
            "UPDATE interview_sessions SET turn_count=COALESCE(turn_count,0)+1 WHERE id=?;",
            (session_id,),
        )
        con.commit()
        row = con.execute(
            "SELECT COALESCE(turn_count,0) as tc FROM interview_sessions WHERE id=?;",
            (session_id,),
        ).fetchone()
        return int(row["tc"]) if row else 0
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def get_session_softened_state(session_id: str) -> Dict:
    """Return softened mode info for a session.

    WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14): extended return
    shape with `state` + `trigger` + `n_remaining` for the three-state
    machine (normal → softened → softened_exiting → normal).

    State computation:
      turn_count <  softened_until_turn  → "softened"
      turn_count == softened_until_turn  → "softened_exiting" (one
        turn of recovering-from-softened, gentle re-engagement
        permitted but no chapter-resumption phrases)
      turn_count >  softened_until_turn  → "normal"
      (interview_softened == 0 → "normal" regardless of arithmetic)

    Returned keys (all present for backward compat with old callers
    reading the legacy three keys; new callers should consume `state`
    + `trigger` + `n_remaining`):
      interview_softened: bool — True iff state is "softened" OR
                                  "softened_exiting"
      softened_until_turn: int — the last turn in non-normal mode
      turn_count:          int — current session turn counter
      state:               str — "normal" | "softened" | "softened_exiting"
      trigger:             str — "acute" | "past_tense_acknowledge" | ""
      n_remaining:         int — turns left before normal (0 when normal)
    """
    con = _connect()
    row = con.execute(
        """
        SELECT COALESCE(interview_softened,0) as interview_softened,
               COALESCE(softened_until_turn,0) as softened_until_turn,
               COALESCE(turn_count,0) as turn_count,
               COALESCE(softened_trigger,'') as softened_trigger,
               COALESCE(softened_initial_n,0) as softened_initial_n
        FROM interview_sessions WHERE id=?;
        """,
        (session_id,),
    ).fetchone()
    con.close()
    if not row:
        return {
            "interview_softened": False,
            "softened_until_turn": 0,
            "turn_count": 0,
            "state": "normal",
            "trigger": "",
            "n_remaining": 0,
        }
    d = dict(row)
    turn_count = int(d["turn_count"])
    until_turn = int(d["softened_until_turn"])
    flag = bool(d["interview_softened"])
    trigger = (d["softened_trigger"] or "") if d.get("softened_trigger") is not None else ""

    # State machine — only computed when the flag is on. When the
    # flag was never set (or was cleared) the session is normal
    # regardless of arithmetic.
    if not flag:
        state = "normal"
        n_remaining = 0
    elif turn_count < until_turn:
        state = "softened"
        n_remaining = max(0, until_turn - turn_count)
    elif turn_count == until_turn:
        state = "softened_exiting"
        n_remaining = 0  # the exiting turn itself; next turn is normal
    else:
        state = "normal"
        n_remaining = 0

    return {
        # Backward-compat keys
        "interview_softened": state in ("softened", "softened_exiting"),
        "softened_until_turn": until_turn,
        "turn_count": turn_count,
        # New three-state-machine keys
        "state": state,
        "trigger": trigger,
        "n_remaining": n_remaining,
    }


def clear_session_softened(session_id: str) -> None:
    """Explicitly clear softened mode."""
    con = _connect()
    con.execute(
        "UPDATE interview_sessions SET interview_softened=0, softened_until_turn=0 WHERE id=?;",
        (session_id,),
    )
    con.commit()
    con.close()


# =============================================================================
# v6.1 Track B — Affect Events
# =============================================================================

def save_affect_event(
    session_id: str,
    timestamp: float,
    section_id: Optional[str],
    affect_state: str,
    confidence: float,
    duration_ms: int,
    source: str = "camera",
) -> str:
    """Persist a derived affect event. Returns the event id."""
    con = _connect()
    now = _now_iso()
    eid = _uuid()
    con.execute(
        """
        INSERT INTO affect_events
          (id, session_id, section_id, affect_state, confidence, duration_ms, source, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (eid, session_id, section_id or "", affect_state,
         round(confidence, 4), duration_ms, source, now),
    )
    con.commit()
    con.close()
    return eid


def list_affect_events(session_id: str, limit: int = 50) -> List[Dict]:
    """Return stored affect events for a session, newest first."""
    con = _connect()
    rows = con.execute(
        """
        SELECT id, session_id, section_id, affect_state, confidence, duration_ms, source, ts
        FROM affect_events
        WHERE session_id=?
        ORDER BY ts DESC
        LIMIT ?;
        """,
        (session_id, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# -----------------------------------------------------------------------------
# Narrator Delete — Phase 2 (dependency inventory, soft/hard delete, restore, audit)
# -----------------------------------------------------------------------------

# ── Extended person-scoped deletion coverage ──────────────────────────
# WORK-AUDIT-2026-07-05 headline 3: ~14 person-scoped tables landed
# after the original delete-inventory/hard-delete were written, most
# WITHOUT an FK to people — hard-deleting a narrator silently orphaned
# photos, story candidates, bio facts, archives, safety events, and
# trips. Locked principle 4 ("no partial resets") requires deletion to
# be total. Every table below is guarded by existence checks so older
# DBs without a given migration don't break.
#
# Deletion order matters for the NO-ACTION FK children:
#   media_archive_links / media_archive_family_lines must go before
#   media_archive_items (their FKs would block the parent delete).
#   photos cascades photo_events/photo_session_shows/photo_memories;
#   trips cascades its whole trip_* family (foreign_keys=ON in
#   _connect). narrator_delete_audit is intentionally EXCLUDED — the
#   audit trail must survive the delete it records.
_EXTENDED_PERSON_SCOPED_TABLES: List[tuple] = [
    ("photos", "narrator_id"),
    ("photo_sessions", "narrator_id"),
    ("photo_people", "person_id"),
    ("story_candidates", "narrator_id"),
    ("bio_facts", "narrator_id"),
    ("follow_up_bank", "person_id"),
    ("memory_archive_turns", "person_id"),
    ("memory_archive_sessions", "person_id"),
    ("media_archive_items", "person_id"),
    ("media_archive_people", "person_id"),
    ("safety_events", "person_id"),
    ("section_summaries", "person_id"),
    ("trip_bio_suggestions", "person_id"),
    ("trips", "person_id"),
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 2 (2026-08-16).
    # `sessions` has no SQLite FK to `people` -- adding one needs a table
    # rebuild that rewrites the parent of the whole chat corpus (see
    # migration 0044). The deletion POLICY a cascade would have given is
    # implemented here instead, where it is testable: a narrator's owned
    # sessions are deleted explicitly, and `turns` follows through its
    # existing ON DELETE CASCADE off sessions(conv_id).
    #
    # Only OWNED rows go. Rows whose owner was never recorded are not
    # swept up on a guess -- they are reported by
    # session_ownership_residue() instead.
    ("sessions", "person_id"),
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 4 (2026-08-18).
    #
    # `turn_extraction_ledger` arrived with migration 0038 on 2026-07-30
    # (Gate 7 Phase 2) and was never added to this list, so a hard-deleted
    # narrator left ledger rows behind. Found by the Phase 3 live
    # acceptance: its two Lori turns left 2 orphans, and they were the
    # only 2 in the whole 40-row table -- newly observable rather than an
    # accumulated pile-up, because the table is young.
    #
    # The rows carry idempotency keys, outcomes and timings and NO
    # narrator text, so this was referential hygiene rather than a privacy
    # leak. It is still residue: the ledger is keyed to turns and a
    # narrator that no longer exist, and locked principle 4 -- "no partial
    # resets" -- says a deletion that leaves rows behind is not done.
    ("turn_extraction_ledger", "narrator_id"),
    # WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 Commit 1 (2026-08-19).
    #
    # `turn_extraction_results` (migration 0041) was missed the same way
    # the ledger was, and it is the more serious of the two: the ledger
    # holds keys and timings, while THIS table holds `items` -- the
    # extracted values themselves, which are derived directly from the
    # narrator's own speech ("Elena", "Corpus Christi", a date of birth).
    #
    # So a hard-deleted narrator was leaving structured facts about their
    # life in the database. Found by the deletion-residue test written for
    # this commit, not by reading the list -- which is the argument for
    # testing deletion per table rather than trusting an inventory that
    # has now been incomplete twice.
    ("turn_extraction_results", "narrator_id"),
]


def _table_column_exists(con, table: str, column: str) -> bool:
    try:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
            (table,),
        ).fetchone()
        if not row:
            return False
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table});").fetchall()]
        return column in cols
    except Exception:
        return False


def _extended_person_scoped_counts(con, person_id: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table, col in _EXTENDED_PERSON_SCOPED_TABLES:
        if not _table_column_exists(con, table, col):
            continue
        try:
            row = con.execute(
                f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col}=?;",  # noqa: S608
                (person_id,),
            ).fetchone()
            counts[table] = row["cnt"] if row else 0
        except Exception:
            counts[table] = -1  # visible signal that the count failed
    return counts


def _extended_person_scoped_delete(con, person_id: str) -> None:
    """Delete extended person-scoped rows inside the caller's
    transaction (no commit here — hard_delete_person owns the
    all-or-nothing boundary)."""
    # NO-ACTION FK children of media_archive_items go first.
    if _table_column_exists(con, "media_archive_items", "person_id"):
        for child, fk_col in (
            ("media_archive_links", "archive_item_id"),
            ("media_archive_family_lines", "archive_item_id"),
        ):
            if _table_column_exists(con, child, fk_col):
                con.execute(
                    f"DELETE FROM {child} WHERE {fk_col} IN "  # noqa: S608
                    f"(SELECT id FROM media_archive_items WHERE person_id=?);",
                    (person_id,),
                )
    for table, col in _EXTENDED_PERSON_SCOPED_TABLES:
        if _table_column_exists(con, table, col):
            con.execute(
                f"DELETE FROM {table} WHERE {col}=?;",  # noqa: S608
                (person_id,),
            )


def person_delete_inventory(person_id: str) -> Optional[Dict[str, Any]]:
    """Return dependency counts for a person, used before deletion confirmation."""
    init_db()
    con = _connect()
    person = con.execute(
        "SELECT id, display_name, is_deleted FROM people WHERE id=?;",
        (person_id,),
    ).fetchone()
    if not person:
        con.close()
        return None

    counts = {}
    tables = [
        ("profiles", "person_id"),
        ("timeline_events", "person_id"),
        ("interview_sessions", "person_id"),
        ("interview_answers", "person_id"),
        ("facts", "person_id"),
        ("life_phases", "person_id"),
        # R2.5 — the operator must see chat sessions in the confirmation
        # inventory, because deleting the narrator now removes them (and
        # their turns) rather than orphaning them.
        ("sessions", "person_id"),
        # WO-LORI-PROFILE-SEED-REACHABILITY-01 Phase 1 (2026-08-26).
        #
        # THIS BELONGS HERE AND NOT IN `_EXTENDED_PERSON_SCOPED_TABLES`.
        # That list exists for tables the FK cascade cannot reach —
        # `sessions` is in it precisely because it has no SQLite FK to
        # `people`. `profile_seed_onboarding` has a real
        # `REFERENCES people(id) ON DELETE CASCADE`, `_connect()` sets
        # `PRAGMA foreign_keys=ON`, and `hard_delete_person` deletes the
        # people row inside its transaction. Adding it to the extended
        # list as well would give a table with a working deletion path a
        # second one, and two paths to one outcome is how the surviving
        # one stops being tested.
        ("profile_seed_onboarding", "person_id"),
    ]
    for table, col in tables:
        row = con.execute(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE {col}=?;",  # noqa: S608
            (person_id,),
        ).fetchone()
        counts[table] = row["cnt"] if row else 0

    # Extended coverage (WORK-AUDIT-2026-07-05) — photos, archives,
    # story candidates, bio facts, safety events, trips, etc.
    counts.update(_extended_person_scoped_counts(con, person_id))

    # Media: count rows where person_id matches (ON DELETE SET NULL)
    media_row = con.execute(
        "SELECT COUNT(*) AS cnt FROM media WHERE person_id=?;",
        (person_id,),
    ).fetchone()
    counts["media_owned"] = media_row["cnt"] if media_row else 0

    attach_row = con.execute(
        "SELECT COUNT(*) AS cnt FROM media_attachments WHERE person_id=?;",
        (person_id,),
    ).fetchone()
    counts["media_attachments"] = attach_row["cnt"] if attach_row else 0

    # Kawa segments (JSON files on disk, not in SQLite)
    kawa_seg_dir = DATA_DIR / "kawa" / "people" / person_id / "segments"
    if kawa_seg_dir.exists():
        counts["kawa_segments"] = len(list(kawa_seg_dir.glob("*.json")))
    else:
        counts["kawa_segments"] = 0

    con.close()
    return {
        "person_id": person["id"],
        "display_name": person["display_name"],
        "counts": counts,
        "has_soft_delete": True,
        "is_deleted": bool(person["is_deleted"]),
    }


def _log_delete_audit(
    con: sqlite3.Connection,
    action: str,
    person_id: str,
    display_name: str,
    counts: Dict[str, Any],
    result: str = "success",
    error_detail: Optional[str] = None,
    requested_by: Optional[str] = None,
) -> str:
    """Append a row to the narrator_delete_audit table (within caller's transaction).

    Returns the row id (2026-08-20) so the caller can FINALISE the
    result once the filesystem phase is known. It used to be written as
    `success` before a file had been touched, which meant a partial
    erasure still left a successful hard-delete record in the one place
    an operator would look to find out whether a deletion worked.
    """
    audit_id = _uuid()
    con.execute(
        """
        INSERT INTO narrator_delete_audit
            (id, action, person_id, display_name, requested_by, dependency_counts_json, result, error_detail, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            audit_id,
            action,
            person_id,
            display_name,
            requested_by,
            _json_dump(counts),
            result,
            error_detail,
            _now_iso(),
        ),
    )
    return audit_id


def soft_delete_person(
    person_id: str,
    undo_minutes: int = 10,
    requested_by: Optional[str] = None,
    reason: str = "",
) -> Optional[Dict[str, Any]]:
    """Mark a person as soft-deleted. Reversible within undo_minutes."""
    init_db()
    con = _connect()
    person = con.execute(
        "SELECT id, display_name, is_deleted FROM people WHERE id=?;",
        (person_id,),
    ).fetchone()
    if not person:
        con.close()
        return None
    if person["is_deleted"]:
        con.close()
        return {"error": "already_deleted", "person_id": person_id}

    now = _now_iso()
    from datetime import timedelta
    undo_expires = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=undo_minutes)).isoformat()

    # Get inventory counts before marking deleted
    inv = person_delete_inventory(person_id)
    counts = inv["counts"] if inv else {}

    con.execute(
        """
        UPDATE people
        SET is_deleted = 1,
            deleted_at = ?,
            deleted_by = ?,
            delete_reason = ?,
            undo_expires_at = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (now, requested_by, reason or "", undo_expires, now, person_id),
    )

    _log_delete_audit(con, "soft_delete", person_id, person["display_name"], counts,
                       result="success", requested_by=requested_by)

    con.commit()
    con.close()

    logger.info("soft_delete_person: id=%s name=%r undo_expires=%s", person_id, person["display_name"], undo_expires)

    return {
        "status": "soft_deleted",
        "person_id": person_id,
        "display_name": person["display_name"],
        "undo_expires_at": undo_expires,
        "counts": counts,
    }


def restore_person(person_id: str, requested_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Restore a soft-deleted person if within the undo window."""
    init_db()
    con = _connect()
    person = con.execute(
        "SELECT id, display_name, is_deleted, undo_expires_at FROM people WHERE id=?;",
        (person_id,),
    ).fetchone()
    if not person:
        con.close()
        return None
    if not person["is_deleted"]:
        con.close()
        return {"error": "not_deleted", "person_id": person_id}

    # Check undo window
    undo_exp = person["undo_expires_at"]
    if undo_exp:
        try:
            exp_dt = datetime.fromisoformat(undo_exp)
            if datetime.now(timezone.utc).replace(tzinfo=None) > exp_dt:
                con.close()
                return {"error": "undo_expired", "person_id": person_id, "undo_expires_at": undo_exp}
        except ValueError:
            pass  # If parse fails, allow restore anyway

    now = _now_iso()
    con.execute(
        """
        UPDATE people
        SET is_deleted = 0,
            deleted_at = NULL,
            deleted_by = NULL,
            delete_reason = '',
            undo_expires_at = NULL,
            updated_at = ?
        WHERE id = ?;
        """,
        (now, person_id),
    )

    _log_delete_audit(con, "restore", person_id, person["display_name"], {},
                       result="success", requested_by=requested_by)

    con.commit()
    con.close()

    logger.info("restore_person: id=%s name=%r", person_id, person["display_name"])

    return {
        "status": "restored",
        "person_id": person_id,
        "display_name": person["display_name"],
    }


def hard_delete_person(person_id: str, requested_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Permanently and transactionally delete a person and all dependent records.

    The SQLite FK cascade handles most deletions automatically:
    - profiles, timeline_events, interview_sessions, interview_answers, facts, life_phases → CASCADE
    - media, media_attachments → SET NULL (person_id nulled, records preserved)
    - Kawa segment JSON files → removed from disk after DB commit

    This function wraps the delete in a transaction for all-or-nothing safety.
    """
    init_db()

    # Get inventory before deletion
    inv = person_delete_inventory(person_id)
    if not inv:
        return None

    con = _connect()
    person = con.execute(
        "SELECT id, display_name, is_deleted FROM people WHERE id=?;",
        (person_id,),
    ).fetchone()
    if not person:
        con.close()
        return None

    display_name = person["display_name"]
    counts = inv["counts"]

    # ── PLAN BEFORE DESTROYING THE AUTHORITY ──────────────────────
    # Trip-source directories, import-staging batches and legacy agent
    # transcript exports are all named by rows that cascade away with
    # the person. Once `people` is gone, so is the only record of which
    # directories were ever theirs -- which is why the first cut of
    # this could not be retried: the rows were deleted, the files
    # survived, and nothing knew their names any more.
    #
    # The plan is committed on its OWN connection so it survives a
    # rollback of the delete, and `pending` is written before the
    # database phase so a crash between the two leaves a recoverable
    # job rather than silence.
    # BOTH STEPS FAIL CLOSED (corrected 2026-08-20). They used to log
    # and continue -- a plan-building failure substituted `plan=[]` and
    # a job-write failure was swallowed -- so a deletion could destroy
    # the database authority and then have no plan to execute or to
    # retry. Refusing costs the operator a second attempt. Continuing
    # costs the narrator their files, permanently, with nothing left
    # that knows where they were.
    try:
        from .services import narrator_erasure as _erasure
        # THE ROOT IS PART OF THE PLAN (2026-08-20). A saved plan holds
        # RELATIVE paths, so a retry used to execute them against
        # whatever DATA_DIR the process had at that moment. Reproduced
        # in review: a plan created for root A, retried under root B,
        # left A intact and deleted B -- and the same narrator id
        # exists under both roots in any deployment that has been
        # migrated, restored, or pointed at a staging copy. The retry
        # is exactly when somebody is likely to be changing the
        # environment.
        plan_root = str(_erasure.data_root())
        plan = _erasure.build_plan(person_id, con)
        _erasure_job_upsert(person_id, display_name, plan, "pending",
                            requested_by=requested_by, required=True,
                            data_root=plan_root)
    except Exception as exc:
        con.rollback()
        con.close()
        logger.error("hard_delete_person REFUSED for %s — no retry plan: %s",
                     person_id, exc)
        return {
            "error": "plan_unavailable",
            "person_id": person_id,
            "detail": "the erasure plan could not be %s, so the deletion was "
                      "refused before any row was removed: %s"
                      % ("built" if isinstance(exc, _erasure.PlanIncomplete)
                         else "saved", exc),
        }

    try:
        # Extended person-scoped tables first (no FK to people — the
        # cascade can't reach them). See _EXTENDED_PERSON_SCOPED_TABLES.
        _extended_person_scoped_delete(con, person_id)

        # MEDIA IS DELETED, NOT DETACHED, on a confirmed hard erasure.
        # Chris, 2026-08-20: `ON DELETE SET NULL` may remain as a
        # database fallback, but an explicit hard deletion must not
        # turn a narrator's photographs into ownerless rows that
        # outlive them. Done BEFORE the people row so the FK cascade
        # never gets the chance to null them instead.
        media_deleted = _hard_delete_media(con, person_id)

        # FK CASCADE handles the remaining dependent rows when the
        # people row goes.
        con.execute("DELETE FROM people WHERE id = ?;", (person_id,))

        # `pending` is the truthful audit result at this point: the
        # rows are gone and the files have not been touched yet. It is
        # finalised to `success` or `partial` after the filesystem
        # phase. It used to be written as `success` here, which meant a
        # failed erasure still left a successful hard-delete record.
        audit_id = _log_delete_audit(
            con, "hard_delete", person_id, display_name, counts,
            result="pending", requested_by=requested_by)

        con.commit()
        logger.info("hard_delete_person: id=%s name=%r counts=%s", person_id, display_name, counts)

    except Exception as exc:
        con.rollback()
        # Log the failure
        try:
            _log_delete_audit(con, "hard_delete", person_id, display_name, counts,
                               result="rollback", error_detail=str(exc), requested_by=requested_by)
            con.commit()
        except Exception:
            pass
        con.close()
        logger.error("hard_delete_person ROLLBACK: id=%s error=%s", person_id, exc)
        return {"error": "rollback", "person_id": person_id, "detail": str(exc)}

    con.close()

    # The database phase is done. Everything below is the filesystem
    # phase plus honest reporting of both.
    return _run_erasure_phase(
        person_id, display_name, plan,
        rows_deleted=counts, media_deleted=media_deleted,
        audit_id=audit_id, requested_by=requested_by,
        data_root=plan_root)


# ── Media: deleted, not detached ────────────────────────────────────────

def _hard_delete_media(con: sqlite3.Connection, person_id: str) -> Dict[str, int]:
    """Delete this narrator's media rows and attachments.

    The schema keeps `ON DELETE SET NULL` on both, which is right for
    the ordinary cascade -- a shared asset should not vanish because
    one link to it went away. It is NOT right for a confirmed hard
    erasure, where the effect was to leave identifiable photographs on
    disk as rows belonging to nobody. Chris ruled on 2026-08-20 that an
    explicit hard delete removes them.

    Attachments go first so the media rows are not left referenced.

    NOTHING IS CAUGHT HERE (corrected 2026-08-20). Both statements used
    to swallow `sqlite3.Error` and continue, which could leave
    ownerless media rows pointing at files the filesystem phase then
    removed -- a row asserting a photograph exists, and no photograph.
    A failure propagates to the caller's rollback: the whole deletion
    is undone and the operator can retry it intact.
    """
    out = {"media": 0, "media_attachments": 0}
    cur = con.execute(
        "DELETE FROM media_attachments WHERE person_id = ? OR media_id IN "
        "(SELECT id FROM media WHERE person_id = ?);",
        (person_id, person_id))
    out["media_attachments"] = int(cur.rowcount or 0)
    cur = con.execute("DELETE FROM media WHERE person_id = ?;", (person_id,))
    out["media"] = int(cur.rowcount or 0)
    return out


# ── The erasure job: pending → complete | partial ───────────────────────

def _erasure_job_upsert(person_id: str, display_name: str,
                        plan: List[Dict[str, Any]], status: str,
                        *, result: Optional[Dict[str, Any]] = None,
                        requested_by: Optional[str] = None,
                        bump_attempt: bool = False,
                        required: bool = False,
                        data_root: Optional[str] = None) -> None:
    """Write the plan and its status on a SEPARATE connection.

    Separate on purpose: the job must survive a rollback of the delete
    it describes. A plan that vanished with the transaction would leave
    exactly the situation this exists to prevent -- files on disk and
    nothing that knows their names.

    `required=True` on the INITIAL pending write, which happens before
    any row is deleted. That write is the retry contract: without it a
    failed erasure is unrecoverable, so it raises rather than logging.
    Later writes are bookkeeping on work already done and must never
    break a deletion that succeeded, so they stay best-effort.
    """
    now = _now_iso()
    try:
        con = _connect()
        try:
            con.execute("BEGIN IMMEDIATE;")
            row = con.execute(
                "SELECT attempts FROM narrator_erasure_jobs WHERE person_id=?;",
                (person_id,)).fetchone()
            attempts = int((row["attempts"] if row else 0) or 0)
            if bump_attempt:
                attempts += 1
            if row:
                # The root is written ONCE, with the plan. A later
                # status update must never move it: the plan means the
                # paths under THAT root and nowhere else.
                if data_root:
                    con.execute(
                        "UPDATE narrator_erasure_jobs SET status=?, plan_json=?,"
                        " result_json=?, attempts=?, updated_at=?, data_root=?"
                        " WHERE person_id=?;",
                        (status, _json_dump(plan), _json_dump(result or {}),
                         attempts, now, data_root, person_id))
                else:
                    con.execute(
                        "UPDATE narrator_erasure_jobs SET status=?, plan_json=?,"
                        " result_json=?, attempts=?, updated_at=?"
                        " WHERE person_id=?;",
                        (status, _json_dump(plan), _json_dump(result or {}),
                         attempts, now, person_id))
            else:
                con.execute(
                    "INSERT INTO narrator_erasure_jobs (person_id, display_name,"
                    " status, plan_json, result_json, attempts, requested_by,"
                    " created_at, updated_at, data_root)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?);",
                    (person_id, display_name or "", status, _json_dump(plan),
                     _json_dump(result or {}), attempts, requested_by or "",
                     now, now, data_root or ""))
            con.commit()
        finally:
            con.close()
    except Exception as exc:
        logger.error("erasure job write failed for %s: %s", person_id, exc)
        if required:
            raise


def erasure_job_get(person_id: str) -> Optional[Dict[str, Any]]:
    """The saved plan for a narrator, if one exists."""
    init_db()
    con = _connect()
    try:
        row = con.execute(
            "SELECT person_id, display_name, status, plan_json, result_json, "
            "attempts, requested_by, created_at, updated_at, data_root "
            "FROM narrator_erasure_jobs WHERE person_id=?;",
            (person_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    out = dict(row)
    out["plan"] = _json_load(out.pop("plan_json", "[]"), [])
    out["result"] = _json_load(out.pop("result_json", "{}"), {})
    return out


def _finalize_delete_audit(person_id: str, audit_id: Optional[str],
                           result: str, detail: Optional[str] = None) -> None:
    """Set the audit row's outcome once the filesystem phase is known.

    It used to be committed as `success` before a single file was
    touched, so a partial erasure still left a successful hard-delete
    record -- the one place an operator would look to find out whether
    a deletion had actually worked.
    """
    if not audit_id:
        return
    try:
        con = _connect()
        try:
            con.execute(
                "UPDATE narrator_delete_audit SET result=?, error_detail=? "
                "WHERE id=?;", (result, detail, audit_id))
            con.commit()
        finally:
            con.close()
    except Exception as exc:                            # pragma: no cover
        logger.error("delete audit finalize failed for %s: %s", person_id, exc)


def _run_erasure_phase(person_id: str, display_name: str,
                       plan: List[Dict[str, Any]],
                       *, rows_deleted: Dict[str, Any],
                       media_deleted: Dict[str, int],
                       audit_id: Optional[str] = None,
                       requested_by: Optional[str] = None,
                       attempt: bool = False,
                       data_root: Optional[str] = None) -> Dict[str, Any]:
    """Execute the plan and answer with what actually happened.

    `data_root` is the root the plan was BUILT for. A plan holds
    relative paths, so executing it against the process's current root
    is how a retry after a `DATA_DIR` change comes to delete the same
    narrator id under a different data root -- proven in review: plan
    for A, retry under B, A intact and B destroyed.
    """
    try:
        from .services import narrator_erasure as _erasure
        erase = _erasure.execute_plan(plan, root=data_root or None).as_dict()
    except Exception as exc:
        logger.error("hard_delete_person: erasure could not run for %s: %s",
                     person_id, exc)
        erase = {
            "active_data_erased": False,
            "historical_residue_present": False,
            "paths_removed": [], "files_removed": 0, "removed_detail": [],
            "already_absent": [],
            "failed": [{"target": "*", "reason": exc.__class__.__name__,
                        "detail": str(exc)}],
            "historical_residue": [],
        }

    active = bool(erase.get("active_data_erased"))
    historical = bool(erase.get("historical_residue_present"))
    complete = active and not historical
    # THREE OUTCOMES, not two (Chris, 2026-08-20). Collapsing them made
    # a backup produce a permanent 207 on a deletion where nothing had
    # failed and `retry_available` was false -- an actionable error
    # code for a situation with no action. `hard_deleted_partial` now
    # means, and only means, that the active erasure failed.
    if not active:
        outcome = "hard_deleted_partial"
    elif historical:
        outcome = "hard_deleted_historical_residue"
    else:
        outcome = "hard_deleted"
    status = "complete" if active else "partial"
    _erasure_job_upsert(person_id, display_name, plan, status,
                        result=erase, requested_by=requested_by,
                        bump_attempt=attempt)
    _finalize_delete_audit(
        person_id, audit_id,
        "success" if active else "partial",
        None if active else "filesystem erasure incomplete: " + ", ".join(
            f.get("path") or f.get("target") or "?"
            for f in erase.get("failed", [])) or None)

    # `counts` from the pre-delete inventory is what MIGHT be affected,
    # not what was removed, and it is not even all database: it carries
    # `media_owned` (rows the cascade would DETACH, not delete) and
    # `kawa_segments`, which is a count of FILES ON DISK. Reporting
    # either under `database_rows_deleted` mixes three different
    # actions into one number.
    deleted_by_table = {k: v for k, v in (rows_deleted or {}).items()
                        if k not in _NON_TABLE_INVENTORY_KEYS}
    deleted_by_table["media"] = int(media_deleted.get("media", 0))
    deleted_by_table["media_attachments"] = int(
        media_deleted.get("media_attachments", 0))

    return {
        "status": outcome,
        "erasure_complete": complete,
        "active_data_erased": active,
        "historical_residue_present": historical,
        "person_id": person_id,
        "display_name": display_name,
        # Kept for existing callers; the same numbers now live under
        # names that say which question they answer.
        "counts_removed": deleted_by_table,
        "database_rows_deleted": deleted_by_table,
        "database_rows_detached": _detached_rows(),
        "files_removed": erase.get("files_removed", 0),
        "paths_removed": erase.get("paths_removed", []),
        "filesystem": erase,
        "intentionally_retained": _retained_records(),
        "historical_residue": erase.get("historical_residue", []),
        "failed_targets": erase.get("failed", []),
        "retry_available": not active,
        "retry": {
            "available": not active,
            "endpoint": "POST /api/people/%s/erase-retry" % person_id,
            "note": "the saved plan is executed again; targets already gone "
                    "are counted as absent, so a repeat is safe",
        },
    }


#: Keys `person_delete_inventory` returns that are NOT database tables
#: this deletion removes. `media_owned` counts rows the FK cascade
#: would detach; `kawa_segments` counts JSON files on disk. Both were
#: being reported as deleted database rows.
_NON_TABLE_INVENTORY_KEYS = ("media_owned", "media_attachments",
                             "kawa_segments")


def _detached_rows() -> List[Dict[str, Any]]:
    """Rows deliberately kept with their owner nulled.

    Empty for a hard delete now that media is deleted outright. The
    key stays in the response because the DISTINCTION is what the
    report is for: a caller must be able to see that nothing was merely
    detached, rather than infer it from an absence.
    """
    return []


def _retained_records() -> List[Dict[str, Any]]:
    """What survives on purpose, named so nobody has to infer it.

    `narrator_delete_audit` and `narrator_erasure_jobs` both outlive
    the person deliberately: one records that a deletion happened, the
    other is what makes a failed erasure retryable. Both hold ids,
    paths, counts and timestamps -- and no narrator speech.
    """
    return [
        {"record": "narrator_delete_audit", "kind": "database",
         "reason": "append-only deletion audit; ids, counts and a timestamp, "
                   "and no narrator speech"},
        {"record": "narrator_erasure_jobs", "kind": "database",
         "reason": "the saved erasure plan; paths and counts only, and it is "
                   "what makes a partial deletion retryable"},
    ]


def retry_person_erasure(person_id: str,
                         requested_by: Optional[str] = None
                         ) -> Optional[Dict[str, Any]]:
    """Run a saved erasure plan again, after the person row is gone.

    THIS IS THE PRODUCT CAPABILITY the first cut was missing. The
    service was idempotent all along; what did not exist was any route
    back to it once `people` no longer had the row, so `DELETE` just
    answered 404 and the surviving files were unreachable.

    A job already `complete` is READ BACK, not re-run: pressing delete
    again on a finished deletion should answer with what happened, not
    walk the filesystem forever because a backup keeps
    `erasure_complete` false.
    """
    init_db()
    job = erasure_job_get(person_id)
    if not job:
        return None
    if job.get("status") == "complete":
        return _completed_job_answer(person_id, job)

    # THE SAVED ROOT, OR NOTHING. Not the process's current root, and
    # not a guess for a job that predates the column: a plan whose root
    # is unknown may not be pointed at one by inference, because the
    # paths it holds exist under every root this deployment has ever
    # had.
    saved_root = (job.get("data_root") or "").strip()
    from .services import narrator_erasure as _erasure
    if not saved_root:
        return _plan_root_refusal(
            person_id, job,
            "this erasure plan was saved before its data root was recorded, "
            "so there is no way to know which root its paths belong to")
    try:
        validated = str(_erasure.validate_root(saved_root))
    except Exception as exc:
        return _plan_root_refusal(
            person_id, job,
            "the data root this plan was built for (%s) cannot be validated: "
            "%s" % (saved_root, exc))
    if validated != saved_root:
        # It resolves somewhere else now -- a moved mount, a changed
        # symlink. Same paths, different place.
        return _plan_root_refusal(
            person_id, job,
            "the data root this plan was built for (%s) now resolves to %s"
            % (saved_root, validated))

    out = _run_erasure_phase(
        person_id, job.get("display_name") or "", job.get("plan") or [],
        rows_deleted={}, media_deleted={},
        audit_id=None, requested_by=requested_by, attempt=True,
        data_root=validated)
    # THE AUDIT MUST NOT STOP AT `partial`. The first attempt left a
    # partial record; a successful retry used to update the job and
    # leave that record standing, so the one place an operator checks
    # said the deletion had failed after it had been finished. A
    # separate event is appended rather than the original rewritten,
    # so the history reads partial THEN completed.
    _append_retry_audit(person_id, job.get("display_name") or "",
                        out, requested_by=requested_by)
    return out


def _plan_root_refusal(person_id: str, job: Dict[str, Any],
                       why: str) -> Dict[str, Any]:
    """Refuse a retry whose root cannot be confirmed.

    NOTHING IS REMOVED. The alternative -- running relative paths
    against whatever root happens to be configured -- is how a retry
    deletes a different deployment's copy of the same narrator.
    """
    logger.error("[erasure] retry REFUSED for %s: %s", person_id, why)
    return {
        "status": "hard_deleted_partial",
        "erasure_complete": False,
        "active_data_erased": False,
        "historical_residue_present": False,
        "person_id": person_id,
        "display_name": job.get("display_name") or "",
        "counts_removed": {},
        "database_rows_deleted": {},
        "database_rows_detached": [],
        "files_removed": 0,
        "paths_removed": [],
        "filesystem": {"active_data_erased": False, "failed": [], "removed_detail": []},
        "intentionally_retained": _retained_records(),
        "historical_residue": [],
        "failed_targets": [{"target": "*", "reason": "data_root_unconfirmed",
                            "detail": why}],
        "retry_available": True,
        "retry": {
            "available": True,
            "note": "nothing was removed. Restore the data root this plan was "
                    "built for and retry; the plan's paths are relative to "
                    "that root and to no other.",
        },
    }


def _completed_job_answer(person_id: str, job: Dict[str, Any]) -> Dict[str, Any]:
    """The stored result of a deletion that already finished."""
    stored = job.get("result") or {}
    active = bool(stored.get("active_data_erased", True))
    historical = bool(stored.get("historical_residue_present"))
    return {
        "status": ("hard_deleted_historical_residue" if historical
                   else "hard_deleted"),
        "erasure_complete": active and not historical,
        "active_data_erased": active,
        "historical_residue_present": historical,
        "person_id": person_id,
        "display_name": job.get("display_name") or "",
        "already_completed": True,
        "completed_at": job.get("updated_at"),
        "attempts": job.get("attempts"),
        "counts_removed": {},
        "database_rows_deleted": {},
        "database_rows_detached": [],
        "files_removed": stored.get("files_removed", 0),
        "paths_removed": stored.get("paths_removed", []),
        "filesystem": stored,
        "intentionally_retained": _retained_records(),
        "historical_residue": stored.get("historical_residue", []),
        "failed_targets": [],
        "retry_available": False,
        "retry": {"available": False,
                  "note": "this deletion already completed; the stored result "
                          "is returned rather than re-running the plan"},
    }


def _append_retry_audit(person_id: str, display_name: str,
                        out: Dict[str, Any],
                        requested_by: Optional[str] = None) -> None:
    """Append the outcome of a retry attempt to the delete audit."""
    try:
        con = _connect()
        try:
            _log_delete_audit(
                con, "hard_delete_retry", person_id, display_name,
                {"files_removed": out.get("files_removed", 0)},
                result="success" if out.get("active_data_erased") else "partial",
                error_detail=None if out.get("active_data_erased") else
                ", ".join(f.get("path") or f.get("target") or "?"
                          for f in out.get("failed_targets", [])) or None,
                requested_by=requested_by)
            con.commit()
        finally:
            con.close()
    except Exception as exc:                            # pragma: no cover
        logger.error("retry audit append failed for %s: %s", person_id, exc)


def list_delete_audit(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent narrator delete audit log entries."""
    init_db()
    con = _connect()
    rows = con.execute(
        """
        SELECT id, action, person_id, display_name, requested_by,
               dependency_counts_json, result, error_detail, ts
        FROM narrator_delete_audit
        ORDER BY ts DESC
        LIMIT ?;
        """,
        (int(limit),),
    ).fetchall()
    con.close()
    results = []
    for r in rows:
        d = dict(r)
        d["dependency_counts"] = _json_load(d.pop("dependency_counts_json", "{}"), {})
        results.append(d)
    return results


# ── Phase G: Ensure Phase G tables ──────────────────────────────────────────

def _ensure_phase_g_tables(con: sqlite3.Connection, cur: sqlite3.Cursor) -> None:
    """Create Phase G tables: questionnaires, projections, identity change log."""

    # ─────────────────────────────────────────────────────────────────────────
    # bio_builder_questionnaires: canonical questionnaire state
    # ─────────────────────────────────────────────────────────────────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bio_builder_questionnaires (
            person_id TEXT PRIMARY KEY,
            questionnaire_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'unknown',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )

    # ─────────────────────────────────────────────────────────────────────────
    # interview_projections: canonical projection state
    # ─────────────────────────────────────────────────────────────────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_projections (
            person_id TEXT PRIMARY KEY,
            projection_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'unknown',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )

    # ─────────────────────────────────────────────────────────────────────────
    # identity_change_log: audit trail of proposed identity changes
    # ─────────────────────────────────────────────────────────────────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS identity_change_log (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            field_path TEXT NOT NULL,
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            source TEXT NOT NULL DEFAULT 'unknown',
            status TEXT NOT NULL DEFAULT 'proposed',
            accepted_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT DEFAULT '',
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_identity_change_person_created "
        "ON identity_change_log(person_id, created_at);"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase G: Questionnaire canonical persistence
# ─────────────────────────────────────────────────────────────────────────────

def get_questionnaire(person_id: str) -> Dict[str, Any]:
    """Load canonical questionnaire state from backend DB.

    WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 1: when
    HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1, route reads through the
    new bio_facts + profile_json aggregation service. The new view
    closes the gap where the operator intake form (which writes to
    bio_facts + profile_json, not the legacy blob) leaves the Bio
    Builder questionnaire UI looking empty for fresh narrators.

    Default-off: legacy blob path runs byte-stable so existing
    narrators keep their saved questionnaire content during rollout.
    Live verify + Phase 7.5 backfill readiness report gate the flip.
    """
    if os.getenv("HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ", "0").strip() == "1":
        try:
            # Lazy import to avoid circular-import risk on cold start
            # and keep db.py purity when the flag is off (default).
            from .services.bio_questionnaire_view import (
                build_questionnaire_view as _build_view,
            )
            view = _build_view(person_id)
            if view is not None:
                return view
        except Exception as exc:
            # Defensive fallback to legacy blob so a service-side
            # exception never breaks the Bio Builder UI for the
            # operator. Log so the gap shows up in api.log.
            logger.warning(
                "get_questionnaire: bio_facts read failed for %s — "
                "falling back to legacy blob: %s",
                person_id, exc,
            )
    con = _connect()
    try:
        row = con.execute(
            "SELECT questionnaire_json, source, version, updated_at "
            "FROM bio_builder_questionnaires WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        if not row:
            return {
                "person_id": person_id,
                "questionnaire": {},
                "source": "empty",
                "version": 0,
                "updated_at": "",
            }
        return {
            "person_id": person_id,
            "questionnaire": json.loads(row["questionnaire_json"] or "{}"),
            "source": row["source"],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }
    finally:
        con.close()


def upsert_questionnaire(
    person_id: str,
    questionnaire: Dict[str, Any],
    source: str = "ui",
    version: int = 1,
) -> Dict[str, Any]:
    """Save canonical questionnaire state to backend DB."""
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    q_json = json.dumps(questionnaire, ensure_ascii=False)
    con = _connect()
    try:
        con.execute(
            """INSERT INTO bio_builder_questionnaires
                   (person_id, questionnaire_json, source, version, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(person_id) DO UPDATE SET
                   questionnaire_json = excluded.questionnaire_json,
                   source = excluded.source,
                   version = excluded.version,
                   updated_at = excluded.updated_at""",
            (person_id, q_json, source, version, now),
        )
        con.commit()
        return {
            "person_id": person_id,
            "questionnaire": questionnaire,
            "source": source,
            "version": version,
            "updated_at": now,
        }
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase G: Projection canonical persistence
# ─────────────────────────────────────────────────────────────────────────────

def get_projection(person_id: str) -> Dict[str, Any]:
    """Load canonical interview projection state from backend DB."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT projection_json, source, version, updated_at "
            "FROM interview_projections WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        if not row:
            return {
                "person_id": person_id,
                "projection": {},
                "source": "empty",
                "version": 0,
                "updated_at": "",
            }
        return {
            "person_id": person_id,
            "projection": json.loads(row["projection_json"] or "{}"),
            "source": row["source"],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }
    finally:
        con.close()


def projection_envelope_is_empty(projection: Optional[Dict[str, Any]]) -> bool:
    """True when an envelope carries no narrator content.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R1.3. "Empty" is defined here,
    once, so the guard is testable rather than a matter of taste: an envelope
    is empty when ``fields`` is falsy/{} AND ``pendingSuggestions`` is
    falsy/[]. ``syncLog`` is session-only audit and is NEVER counted — a
    payload that carries nothing but its own audit trail is still empty.
    """
    if not isinstance(projection, dict):
        return True
    fields = projection.get("fields")
    pending = projection.get("pendingSuggestions")
    return not fields and not pending


def merge_projection_fields(
    person_id: str,
    mutations: Optional[Dict[str, Any]] = None,
    removals: Optional[List[str]] = None,
    source: str = "projection_sync",
    base_version: Optional[int] = None,
    base_fields: Optional[Dict[str, Any]] = None,
    pending_suggestions: Optional[List[Any]] = None,
    extra_keys: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply FIELD-LEVEL changes with PER-PATH optimistic concurrency.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 1.

    WHY A WHOLE-DOCUMENT PUT COULD NOT BE MADE SAFE BY GUARDING IT. The
    browser envelope is not a superset of the server one. The server
    writes keys the browser has never seen -- ``projection_writer.
    apply_correction`` rewrites ``fields`` mid-turn. Replacing the
    document destroys those keys even when the replacement is fresh,
    non-empty and authorised. Only a per-field write can leave a key the
    writer does not know about intact.

    WHY A GLOBAL VERSION IS NOT ENOUGH EITHER (supervisor review,
    2026-08-17). ``base_version`` proves only that SOMETHING changed, not
    WHAT. Rebasing a dirty path onto a newer record and retrying is safe
    when the server touched *different* paths and silently destructive
    when it touched the *same* one -- the conflict is delayed, not
    resolved.

    So concurrency is checked PER PATH. ``base_fields`` maps each path the
    caller is writing to the value it hydrated for that path. A path is
    CONTESTED when the stored value differs from that. Then:

      * no contested paths -> apply. A newer ``version`` alone is not a
        conflict; a disjoint edit rebases here, on the server, in one
        round trip, so no client retry is needed or offered.
      * any contested path -> REFUSE the whole write, change nothing, and
        return ``conflicting_paths``. The caller keeps its mutation and
        surfaces the conflict. It must NOT retry.

    ``base_fields=None`` means the caller cannot demonstrate what it was
    editing from. A version mismatch is then treated as contesting EVERY
    path, because unprovable is not the same as safe.

    ``pending_suggestions`` replaces that array when supplied and leaves
    it untouched when omitted -- the same "absent means leave alone" rule
    the field mutations follow.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    mutations = mutations or {}
    removals = list(removals or [])
    con = _connect()
    try:
        # ONE WRITE TRANSACTION AROUND COMPARE-AND-WRITE.
        # BEGIN IMMEDIATE takes the write lock BEFORE the SELECT. Without
        # it the read runs in autocommit and only the INSERT opens a
        # (deferred) transaction, so two concurrent requests could both
        # pass the per-path comparison before either wrote -- and the
        # second would land on top of the first having "proved" it was
        # safe against a row that no longer existed. busy_timeout=5000 is
        # already set in _connect, so a contending writer waits rather
        # than failing immediately.
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT projection_json, source, version, updated_at "
            "FROM interview_projections WHERE person_id = ?",
            (person_id,),
        ).fetchone()

        stored: Dict[str, Any] = json.loads(row["projection_json"] or "{}") if row else {}
        stored_version = int(row["version"] or 0) if row else 0
        stored_fields = stored.get("fields") or {}
        touched = list(mutations.keys()) + removals

        contested: List[str] = []
        if base_fields is not None:
            for path in touched:
                if stored_fields.get(path) != base_fields.get(path):
                    contested.append(path)
        elif base_version is not None and int(base_version) != stored_version:
            # Cannot prove any path is safe. Unprovable != safe.
            contested = list(touched)

        if contested:
            con.rollback()
            return {
                "person_id": person_id,
                "projection": stored,
                "source": row["source"] if row else "empty",
                "version": stored_version,
                "updated_at": (row["updated_at"] if row else "") or "",
                "write_applied": False,
                "conflict": True,
                "conflicting_paths": sorted(set(contested)),
            }

        if not mutations and not removals and pending_suggestions is None and not extra_keys:
            con.rollback()
            return {
                "person_id": person_id,
                "projection": stored,
                "source": row["source"] if row else "empty",
                "version": stored_version,
                "updated_at": (row["updated_at"] if row else "") or "",
                "write_applied": False,
                "conflict": False,
                "conflicting_paths": [],
            }

        merged = dict(stored)
        fields = dict(stored_fields)
        for path, value in mutations.items():
            fields[str(path)] = value
        for path in removals:
            fields.pop(str(path), None)
        merged["fields"] = fields
        if pending_suggestions is not None:
            merged["pendingSuggestions"] = list(pending_suggestions)
        else:
            merged.setdefault("pendingSuggestions", stored.get("pendingSuggestions") or [])
        # Envelope-level keys the caller owns (e.g. last_correction_at).
        # Named explicitly rather than swept in, so a merge still cannot
        # carry a whole document by accident.
        for k, v in (extra_keys or {}).items():
            merged[str(k)] = v
        # Any server-authored key not named above is carried through
        # untouched -- that is the whole point of this function.

        next_version = stored_version + 1
        con.execute(
            """INSERT INTO interview_projections
                   (person_id, projection_json, source, version, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(person_id) DO UPDATE SET
                   projection_json = excluded.projection_json,
                   source = excluded.source,
                   version = excluded.version,
                   updated_at = excluded.updated_at""",
            (person_id, json.dumps(merged, ensure_ascii=False), source, next_version, now),
        )
        con.commit()
        return {
            "person_id": person_id,
            "projection": merged,
            "source": source,
            "version": next_version,
            "updated_at": now,
            "write_applied": True,
            "conflict": False,
            "conflicting_paths": [],
        }
    finally:
        con.close()


def upsert_projection(
    person_id: str,
    projection: Dict[str, Any],
    source: str = "projection_sync",
    version: int = 1,
    allow_empty: bool = False,
    base_version: Optional[int] = None,
) -> Dict[str, Any]:
    """Save canonical projection state to backend DB.

    WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01, commit 1 (2026-08-16).

    Two changes to what was a blind last-writer-wins whole-blob replace:

    R1.3 — an EMPTY envelope over a NON-EMPTY stored row is REFUSED. The
    stored row is left byte-identical and the return value reports
    ``write_applied=False``. A caller that genuinely means to wipe passes
    ``allow_empty=True`` and says so. This is the durable half of the fix:
    it protects the row from every writer, not just from the browser path
    that was observed doing it during L2.

    R1.4 — ``version`` is server-owned and monotonic: an applied write
    stores ``stored_version + 1``. The caller's ``version`` is accepted for
    wire compatibility and is advisory only. It was previously stored
    verbatim, and because the browser hardcodes 1 the column was pinned at
    1 forever and carried no ordering information despite existing.

    ``base_version`` (supervisor requirement, 2026-08-16): a stale
    whole-document write returns ``conflict=True`` with the CURRENT
    server record and writes nothing.

    THIS IS THE REPLACEMENT PATH AND IT IS NOT THE DEFAULT ONE. Ordinary
    editing goes through ``merge_projection_fields``, because replacing
    a document destroys server-authored keys the writer never saw. Use
    this only where wholesale replacement is the actual intent -- a deep
    reset, or a restore.

    Nothing is destroyed to achieve either: no column dropped, no row
    deleted, no migration.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    con = _connect()
    try:
        # Same atomicity rule as merge_projection_fields: the base check
        # and the replacement are one write transaction.
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT projection_json, source, version, updated_at "
            "FROM interview_projections WHERE person_id = ?",
            (person_id,),
        ).fetchone()

        stored_version = int(row["version"] or 0) if row is not None else 0
        if base_version is not None and int(base_version) != stored_version:
            con.rollback()
            return {
                "person_id": person_id,
                "projection": json.loads(row["projection_json"] or "{}") if row else {},
                "source": row["source"] if row is not None else "empty",
                "version": stored_version,
                "updated_at": (row["updated_at"] if row is not None else "") or "",
                "write_applied": False,
                "conflict": True,
            }

        if row is not None and not allow_empty and projection_envelope_is_empty(projection):
            existing = json.loads(row["projection_json"] or "{}")
            if not projection_envelope_is_empty(existing):
                # R1.3 — refuse the silent wipe. Touch nothing, not even
                # updated_at: a refused write must leave no trace, so a
                # later forensic byte-comparison stays meaningful.
                con.rollback()
                return {
                    "person_id": person_id,
                    "projection": existing,
                    "source": row["source"],
                    "version": int(row["version"] or 0),
                    "updated_at": row["updated_at"] or "",
                    "write_applied": False,
                    "conflict": False,
                }

        next_version = int(row["version"] or 0) + 1 if row is not None else 1
        p_json = json.dumps(projection, ensure_ascii=False)
        con.execute(
            """INSERT INTO interview_projections
                   (person_id, projection_json, source, version, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(person_id) DO UPDATE SET
                   projection_json = excluded.projection_json,
                   source = excluded.source,
                   version = excluded.version,
                   updated_at = excluded.updated_at""",
            (person_id, p_json, source, next_version, now),
        )
        con.commit()
        return {
            "person_id": person_id,
            "projection": projection,
            "source": source,
            "version": next_version,
            "updated_at": now,
            "write_applied": True,
            "conflict": False,
        }
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase G: Combined narrator state snapshot
# ─────────────────────────────────────────────────────────────────────────────

def get_narrator_state_snapshot(person_id: str) -> Dict[str, Any]:
    """
    Return combined backend canonical state for a narrator.
    Used by frontend on startup/switch to hydrate from backend authority.
    """
    person = get_person(person_id) or {}
    profile_row = get_profile(person_id) or {}
    profile = {}
    if isinstance(profile_row, str):
        try:
            profile = json.loads(profile_row)
        except Exception:
            profile = {}
    elif isinstance(profile_row, dict):
        profile = profile_row

    qq = get_questionnaire(person_id)
    proj = get_projection(person_id)

    # Build protected identity snapshot from person record + profile basics
    basics = profile.get("basics", {}) if isinstance(profile, dict) else {}
    protected_identity = {
        "personal.fullName": person.get("display_name", ""),
        "personal.preferredName": basics.get("preferred", ""),
        "personal.dateOfBirth": person.get("date_of_birth", ""),
        "personal.placeOfBirth": person.get("place_of_birth", ""),
        "personal.birthOrder": basics.get("birthOrder", ""),
    }

    # WO-13: Count prior user-authored turns for this narrator.
    # Used by the UI to gate the session-resume prompt — a fresh narrator with
    # zero real user turns should NOT trigger a "welcome back" greeting.
    # Internal system prompts (role='user' but content starts with '[SYSTEM:')
    # are excluded so they never inflate the count.
    #
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 2, R2.5. This join
    # used to run ONLY on json_extract(payload_json,'$.active_person_id').
    # Every row in that column is '{}', so the count was structurally
    # always 0 and the UI treated every returning narrator as brand new.
    #
    # Ownership now resolves in three steps, most authoritative first:
    #   1. sessions.person_id      -- the real column, added by 0044
    #   2. $.active_person_id      -- the key the legacy reader expected
    #   3. $.person_id             -- the key app.js has actually written
    # Step 3 is not a new invention: /api/session/put has been writing
    # `person_id` while this query looked for `active_person_id`, so even
    # the rare rows that DID record an owner went uncounted.
    user_turn_count = 0
    try:
        con = _connect()
        row = con.execute(
            """
            SELECT COUNT(*) AS n
              FROM turns t
              JOIN sessions s ON s.conv_id = t.conv_id
             WHERE t.role = 'user'
               AND t.content NOT LIKE '[SYSTEM:%'
               AND COALESCE(
                     NULLIF(s.person_id, ''),
                     json_extract(s.payload_json, '$.active_person_id'),
                     json_extract(s.payload_json, '$.person_id')
                   ) = ?
            """,
            (person_id,),
        ).fetchone()
        con.close()
        if row is not None:
            user_turn_count = int(row["n"] if hasattr(row, "keys") else row[0])
    except Exception:
        user_turn_count = 0

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    return {
        "person_id": person_id,
        "person": person,
        "profile": profile,
        "questionnaire": qq.get("questionnaire", {}),
        "projection": proj.get("projection", {}),
        "protected_identity": protected_identity,
        "user_turn_count": user_turn_count,
        "updated_at": now,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase G: Identity change log
# ─────────────────────────────────────────────────────────────────────────────

def log_identity_change_proposal(
    person_id: str,
    field_path: str,
    old_value: str,
    new_value: str,
    source: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Log a proposed change to a protected identity field."""
    proposal_id = "chg_" + uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    con = _connect()
    try:
        con.execute(
            """INSERT INTO identity_change_log
                   (id, person_id, field_path, old_value, new_value, source,
                    status, created_at, meta_json)
               VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?)""",
            (proposal_id, person_id, field_path, old_value, new_value,
             source, now, meta_json),
        )
        con.commit()
        return {
            "proposal_id": proposal_id,
            "person_id": person_id,
            "field_path": field_path,
            "old_value": old_value,
            "new_value": new_value,
            "source": source,
            "status": "proposed",
            "created_at": now,
        }
    finally:
        con.close()


def approve_identity_change_proposal(
    proposal_id: str,
    accepted_by: str = "human",
) -> Dict[str, Any]:
    """
    Accept a proposed identity change, apply it to the person/profile record,
    and mark the log entry as accepted.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM identity_change_log WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "proposal_not_found"}
        row = dict(row)

        if row["status"] != "proposed":
            return {"ok": False, "error": f"proposal already {row['status']}"}

        # Apply the change to canonical person/profile data
        person_id = row["person_id"]
        field_path = row["field_path"]
        new_value = row["new_value"]

        # Map field_path to actual DB column/field
        _applied = False
        if field_path == "personal.fullName":
            con.execute(
                "UPDATE people SET display_name = ?, updated_at = ? WHERE id = ?",
                (new_value, now, person_id),
            )
            _applied = True
        elif field_path == "personal.dateOfBirth":
            con.execute(
                "UPDATE people SET date_of_birth = ?, updated_at = ? WHERE id = ?",
                (new_value, now, person_id),
            )
            _applied = True
        elif field_path == "personal.placeOfBirth":
            con.execute(
                "UPDATE people SET place_of_birth = ?, updated_at = ? WHERE id = ?",
                (new_value, now, person_id),
            )
            _applied = True
        elif field_path in ("personal.preferredName", "personal.birthOrder"):
            # These live in profile basics JSON
            prof_row = con.execute(
                "SELECT profile_json FROM profiles WHERE person_id = ?",
                (person_id,),
            ).fetchone()
            if prof_row:
                profile = json.loads(prof_row["profile_json"] or "{}")
                basics = profile.setdefault("basics", {})
                key = "preferred" if field_path == "personal.preferredName" else "birthOrder"
                basics[key] = new_value
                con.execute(
                    "UPDATE profiles SET profile_json = ?, updated_at = ? WHERE person_id = ?",
                    (json.dumps(profile, ensure_ascii=False), now, person_id),
                )
                _applied = True

        # Mark proposal as accepted
        con.execute(
            """UPDATE identity_change_log
               SET status = 'accepted', accepted_by = ?, resolved_at = ?
               WHERE id = ?""",
            (accepted_by, now, proposal_id),
        )
        con.commit()

        return {
            "ok": True,
            "proposal_id": proposal_id,
            "person_id": person_id,
            "field_path": field_path,
            "new_value": new_value,
            "applied": _applied,
            "accepted_by": accepted_by,
            "resolved_at": now,
        }
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase Q.1: Relationship Graph Layer
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_phase_q1_tables(con: sqlite3.Connection, cur: sqlite3.Cursor) -> None:
    """Create Phase Q.1 tables: graph_persons and graph_relationships."""

    # graph_persons: every person node in the relationship graph
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_persons (
            id TEXT PRIMARY KEY,
            narrator_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '',
            middle_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            maiden_name TEXT NOT NULL DEFAULT '',
            birth_date TEXT NOT NULL DEFAULT '',
            birth_place TEXT NOT NULL DEFAULT '',
            occupation TEXT NOT NULL DEFAULT '',
            deceased INTEGER NOT NULL DEFAULT 0,
            is_narrator INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'manual',
            provenance TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(narrator_id) REFERENCES people(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_persons_narrator "
        "ON graph_persons(narrator_id);"
    )

    # graph_relationships: edges between graph_persons
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_relationships (
            id TEXT PRIMARY KEY,
            narrator_id TEXT NOT NULL,
            from_person_id TEXT NOT NULL,
            to_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT '',
            subtype TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            provenance TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0,
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(narrator_id) REFERENCES people(id) ON DELETE CASCADE,
            FOREIGN KEY(from_person_id) REFERENCES graph_persons(id) ON DELETE CASCADE,
            FOREIGN KEY(to_person_id) REFERENCES graph_persons(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_rels_narrator "
        "ON graph_relationships(narrator_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_rels_from "
        "ON graph_relationships(from_person_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_rels_to "
        "ON graph_relationships(to_person_id);"
    )


# ── Graph Persons CRUD ──

def graph_upsert_person(
    narrator_id: str,
    person_id: Optional[str] = None,
    display_name: str = "",
    first_name: str = "",
    middle_name: str = "",
    last_name: str = "",
    maiden_name: str = "",
    birth_date: str = "",
    birth_place: str = "",
    occupation: str = "",
    deceased: bool = False,
    is_narrator: bool = False,
    source: str = "manual",
    provenance: str = "",
    confidence: float = 1.0,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert or update a person node in the relationship graph."""
    pid = person_id or _uuid()
    now = _now_iso()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO graph_persons
                   (id, narrator_id, display_name, first_name, middle_name,
                    last_name, maiden_name, birth_date, birth_place, occupation,
                    deceased, is_narrator, source, provenance, confidence,
                    created_at, updated_at, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   display_name=excluded.display_name,
                   first_name=excluded.first_name,
                   middle_name=excluded.middle_name,
                   last_name=excluded.last_name,
                   maiden_name=excluded.maiden_name,
                   birth_date=excluded.birth_date,
                   birth_place=excluded.birth_place,
                   occupation=excluded.occupation,
                   deceased=excluded.deceased,
                   is_narrator=excluded.is_narrator,
                   source=excluded.source,
                   provenance=excluded.provenance,
                   confidence=excluded.confidence,
                   updated_at=excluded.updated_at,
                   meta_json=excluded.meta_json""",
            (pid, narrator_id, display_name, first_name, middle_name,
             last_name, maiden_name, birth_date, birth_place, occupation,
             1 if deceased else 0, 1 if is_narrator else 0,
             source, provenance, confidence,
             now, now, _json_dump(meta or {})),
        )
        con.commit()
        return {
            "id": pid, "narrator_id": narrator_id,
            "display_name": display_name,
            "first_name": first_name, "middle_name": middle_name,
            "last_name": last_name, "maiden_name": maiden_name,
            "birth_date": birth_date, "birth_place": birth_place,
            "occupation": occupation, "deceased": deceased,
            "is_narrator": is_narrator,
            "source": source, "provenance": provenance,
            "confidence": confidence,
            "created_at": now, "updated_at": now,
            "meta": meta or {},
        }
    finally:
        con.close()


def graph_list_persons(narrator_id: str) -> List[Dict[str, Any]]:
    """List all person nodes for a narrator."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM graph_persons WHERE narrator_id=? ORDER BY created_at",
            (narrator_id,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "narrator_id": r["narrator_id"],
                "display_name": r["display_name"],
                "first_name": r["first_name"], "middle_name": r["middle_name"],
                "last_name": r["last_name"], "maiden_name": r["maiden_name"],
                "birth_date": r["birth_date"], "birth_place": r["birth_place"],
                "occupation": r["occupation"],
                "deceased": bool(r["deceased"]),
                "is_narrator": bool(r["is_narrator"]),
                "source": r["source"], "provenance": r["provenance"],
                "confidence": r["confidence"],
                "created_at": r["created_at"], "updated_at": r["updated_at"],
                "meta": _json_load(r["meta_json"], {}),
            })
        return out
    finally:
        con.close()


def graph_delete_person(person_id: str) -> bool:
    """Delete a person node (cascades to relationship edges)."""
    con = _connect()
    try:
        con.execute("DELETE FROM graph_relationships WHERE from_person_id=? OR to_person_id=?", (person_id, person_id))
        cur = con.execute("DELETE FROM graph_persons WHERE id=?", (person_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# ── Graph Relationships CRUD ──

def graph_upsert_relationship(
    narrator_id: str,
    rel_id: Optional[str] = None,
    from_person_id: str = "",
    to_person_id: str = "",
    relationship_type: str = "",
    subtype: str = "",
    label: str = "",
    status: str = "active",
    notes: str = "",
    source: str = "manual",
    provenance: str = "",
    confidence: float = 1.0,
    start_date: str = "",
    end_date: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert or update a relationship edge."""
    rid = rel_id or _uuid()
    now = _now_iso()
    con = _connect()
    try:
        con.execute(
            """INSERT INTO graph_relationships
                   (id, narrator_id, from_person_id, to_person_id,
                    relationship_type, subtype, label, status, notes,
                    source, provenance, confidence, start_date, end_date,
                    created_at, updated_at, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   from_person_id=excluded.from_person_id,
                   to_person_id=excluded.to_person_id,
                   relationship_type=excluded.relationship_type,
                   subtype=excluded.subtype,
                   label=excluded.label,
                   status=excluded.status,
                   notes=excluded.notes,
                   source=excluded.source,
                   provenance=excluded.provenance,
                   confidence=excluded.confidence,
                   start_date=excluded.start_date,
                   end_date=excluded.end_date,
                   updated_at=excluded.updated_at,
                   meta_json=excluded.meta_json""",
            (rid, narrator_id, from_person_id, to_person_id,
             relationship_type, subtype, label, status, notes,
             source, provenance, confidence, start_date, end_date,
             now, now, _json_dump(meta or {})),
        )
        con.commit()
        return {
            "id": rid, "narrator_id": narrator_id,
            "from_person_id": from_person_id, "to_person_id": to_person_id,
            "relationship_type": relationship_type, "subtype": subtype,
            "label": label, "status": status, "notes": notes,
            "source": source, "provenance": provenance,
            "confidence": confidence,
            "start_date": start_date, "end_date": end_date,
            "created_at": now, "updated_at": now,
            "meta": meta or {},
        }
    finally:
        con.close()


def graph_list_relationships(narrator_id: str) -> List[Dict[str, Any]]:
    """List all relationship edges for a narrator."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM graph_relationships WHERE narrator_id=? ORDER BY created_at",
            (narrator_id,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "narrator_id": r["narrator_id"],
                "from_person_id": r["from_person_id"],
                "to_person_id": r["to_person_id"],
                "relationship_type": r["relationship_type"],
                "subtype": r["subtype"],
                "label": r["label"], "status": r["status"],
                "notes": r["notes"],
                "source": r["source"], "provenance": r["provenance"],
                "confidence": r["confidence"],
                "start_date": r["start_date"], "end_date": r["end_date"],
                "created_at": r["created_at"], "updated_at": r["updated_at"],
                "meta": _json_load(r["meta_json"], {}),
            })
        return out
    finally:
        con.close()


def graph_delete_relationship(rel_id: str) -> bool:
    """Delete a relationship edge."""
    con = _connect()
    try:
        cur = con.execute("DELETE FROM graph_relationships WHERE id=?", (rel_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def graph_get_full(narrator_id: str) -> Dict[str, Any]:
    """Load the full relationship graph for a narrator (persons + relationships)."""
    return {
        "narrator_id": narrator_id,
        "persons": graph_list_persons(narrator_id),
        "relationships": graph_list_relationships(narrator_id),
    }


def graph_replace_full(narrator_id: str, persons: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replace the entire relationship graph for a narrator (atomic)."""
    now = _now_iso()
    con = _connect()
    try:
        # Clear existing graph
        con.execute("DELETE FROM graph_relationships WHERE narrator_id=?", (narrator_id,))
        con.execute("DELETE FROM graph_persons WHERE narrator_id=?", (narrator_id,))

        # Insert persons
        for p in persons:
            con.execute(
                """INSERT INTO graph_persons
                       (id, narrator_id, display_name, first_name, middle_name,
                        last_name, maiden_name, birth_date, birth_place, occupation,
                        deceased, is_narrator, source, provenance, confidence,
                        created_at, updated_at, meta_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p.get("id") or _uuid(), narrator_id,
                 p.get("display_name", ""), p.get("first_name", ""),
                 p.get("middle_name", ""), p.get("last_name", ""),
                 p.get("maiden_name", ""), p.get("birth_date", ""),
                 p.get("birth_place", ""), p.get("occupation", ""),
                 1 if p.get("deceased") else 0,
                 1 if p.get("is_narrator") else 0,
                 p.get("source", "manual"), p.get("provenance", ""),
                 p.get("confidence", 1.0),
                 p.get("created_at", now), now,
                 _json_dump(p.get("meta", {}))),
            )

        # Insert relationships
        for r in relationships:
            con.execute(
                """INSERT INTO graph_relationships
                       (id, narrator_id, from_person_id, to_person_id,
                        relationship_type, subtype, label, status, notes,
                        source, provenance, confidence, start_date, end_date,
                        created_at, updated_at, meta_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r.get("id") or _uuid(), narrator_id,
                 r.get("from_person_id", ""), r.get("to_person_id", ""),
                 r.get("relationship_type", ""), r.get("subtype", ""),
                 r.get("label", ""), r.get("status", "active"),
                 r.get("notes", ""),
                 r.get("source", "manual"), r.get("provenance", ""),
                 r.get("confidence", 1.0),
                 r.get("start_date", ""), r.get("end_date", ""),
                 r.get("created_at", now), now,
                 _json_dump(r.get("meta", {}))),
            )

        con.commit()
        return graph_get_full(narrator_id)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 1 ────────────────────────────
# story_candidates accessors. Stubs only in this commit; bodies land in
# Phase 1A Commit 2 alongside the services/story_preservation.py
# implementation. Per ChatGPT review pass 2: stubs raise RuntimeError
# (NOT NotImplementedError) so accidental calls during startup or tests
# are loud and immediately attributable, not silent fallthroughs.
#
# Schema lives in server/code/db/migrations/0004_story_candidates.sql.
# The migration runner (run_pending_migrations) applies it at init_db()
# time after the legacy CREATE TABLE block, so the table is present on
# any fresh DB without code changes here. These accessor stubs are the
# Python surface that the router and the preservation service will use.

_VALID_TRIGGER_REASONS = (
    "full_threshold",
    "borderline_scene_anchor",
    "rich_short_narrative",
    "chain_detection",
    "manual",
)
_VALID_CONFIDENCE = ("low", "medium", "high")
_VALID_EXTRACTION_STATUS = ("pending", "partial", "complete", "failed")
_VALID_REVIEW_STATUS = ("unreviewed", "in_review", "promoted", "discarded", "memoir_only")

# WHICH review statuses carry a story forward, defined ONCE.
# `story_candidate_list_for_memoir` below and
# `services/story_projection.py` both read these, so the export gate and
# the Life Map cannot drift apart on what "approved" means.
#
# The two sets differ by exactly `memoir_only`, which is the operator
# saying: these are the narrator's words and they belong in the memoir,
# but do not promote what the extractor made of them.
STORY_MEMOIR_ELIGIBLE = ("promoted", "memoir_only")
STORY_FACTS_ELIGIBLE = ("promoted",)


def _row_to_story_candidate(row: sqlite3.Row) -> Dict[str, Any]:
    """Inflate a story_candidates row to a Dict, hydrating JSON columns
    back into native Python lists/dicts. Centralizes the shape so callers
    don't all re-implement it."""
    d = dict(row)
    d["era_candidates"] = _json_load(d.get("era_candidates"), [])
    d["scene_anchors"] = _json_load(d.get("scene_anchors"), [])
    d["extracted_fields"] = _json_load(d.get("extracted_fields"), {})
    # WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 4 (2026-06-24): chain
    # detector output, written when chat_ws fires
    # factual_chain_capture.build_factual_chain_followup_context on the
    # narrator turn. May be {} for rows pre-dating the wiring or for
    # turns where the chain detector did not fire.
    if "chain_meta_json" in d:
        d["chain_meta"] = _json_load(d.pop("chain_meta_json"), {})
    else:
        d["chain_meta"] = {}
    return d


def story_candidate_insert(
    candidate_id: str,
    narrator_id: str,
    transcript: str,
    *,
    audio_clip_path: Optional[str] = None,
    audio_duration_sec: Optional[float] = None,
    word_count: Optional[int] = None,
    trigger_reason: str,
    scene_anchor_count: int = 0,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    era_candidates: Optional[List[str]] = None,
    age_bucket: Optional[str] = None,
    estimated_year_low: Optional[int] = None,
    estimated_year_high: Optional[int] = None,
    confidence: str = "low",
    scene_anchors: Optional[List[str]] = None,
    # WO-ML-03B (Phase 3 multilingual, 2026-05-07): ISO-639-1 language
    # code detected by the STT engine for THIS turn. Migration
    # 0006_story_candidates_language.sql adds the columns. Default
    # None preserves byte-stable behavior for callers that don't pass
    # the kwarg. Light-validated by the caller (story_preservation);
    # this writer treats whatever it gets as authoritative.
    language: Optional[str] = None,
    language_probability: Optional[float] = None,
    # WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 4 (2026-06-24): chain
    # detector output. Migration 0014_story_candidates_chain_meta.sql
    # adds the column with DEFAULT '{}'. None (the kwarg default)
    # writes '{}' so legacy callers stay byte-stable.
    chain_meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Insert a story_candidate row (Path 1 / preservation). Returns the
    candidate id on success.

    Validates trigger_reason and confidence enums to fail loud if the
    caller passes something the schema doesn't recognize."""
    if trigger_reason not in _VALID_TRIGGER_REASONS:
        raise ValueError(
            f"trigger_reason must be one of {_VALID_TRIGGER_REASONS}, got {trigger_reason!r}"
        )
    if confidence not in _VALID_CONFIDENCE:
        raise ValueError(
            f"confidence must be one of {_VALID_CONFIDENCE}, got {confidence!r}"
        )
    if not transcript or not transcript.strip():
        raise ValueError("transcript must be a non-empty string")
    if not narrator_id:
        raise ValueError("narrator_id required")

    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO story_candidates (
                id, narrator_id, session_id, conversation_id, turn_id,
                transcript, audio_clip_path, audio_duration_sec, word_count,
                trigger_reason, scene_anchor_count,
                era_candidates, age_bucket,
                estimated_year_low, estimated_year_high, confidence,
                scene_anchors,
                extraction_status, extracted_fields,
                review_status,
                language, language_probability,
                chain_meta_json
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?,
                'pending', '{}',
                'unreviewed',
                ?, ?,
                ?
            );
            """,
            (
                candidate_id, narrator_id, session_id, conversation_id, turn_id,
                transcript, audio_clip_path, audio_duration_sec, word_count,
                trigger_reason, int(scene_anchor_count),
                _json_dump(era_candidates or []), age_bucket,
                estimated_year_low, estimated_year_high, confidence,
                _json_dump(scene_anchors or []),
                language, language_probability,
                _json_dump(chain_meta or {}),
            ),
        )
        con.commit()
        return candidate_id
    except sqlite3.Error:
        # BUG-DBLOCK-01 hygiene parity (mirrors save_segment_flag).
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def story_candidate_get(candidate_id: str) -> Optional[Dict[str, Any]]:
    """Single-row fetch by id. Returns None if not found."""
    con = _connect()
    try:
        cur = con.execute(
            "SELECT * FROM story_candidates WHERE id = ?;",
            (candidate_id,),
        )
        row = cur.fetchone()
        return _row_to_story_candidate(row) if row is not None else None
    finally:
        con.close()


def story_candidate_get_by_turn(
    narrator_id: str,
    turn_id: str,
) -> Optional[Dict[str, Any]]:
    """Look up a story candidate by (narrator_id, turn_id).

    WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 3b — chat_ws may re-fire
    preservation on reconnect/retry; this is the application-level
    idempotency lookup. Returns None if either argument is missing or
    no row matches. If multiple rows somehow exist for the same
    (narrator, turn) pair (shouldn't happen, but the schema has no
    UNIQUE constraint yet), returns the newest.
    """
    if not narrator_id or not turn_id:
        return None
    con = _connect()
    try:
        cur = con.execute(
            """
            SELECT * FROM story_candidates
            WHERE narrator_id = ? AND turn_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1;
            """,
            (narrator_id, turn_id),
        )
        row = cur.fetchone()
        return _row_to_story_candidate(row) if row is not None else None
    finally:
        con.close()


def story_candidate_list_unreviewed(
    narrator_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List candidates with review_status='unreviewed', newest first.
    Optional narrator_id filter."""
    if limit <= 0:
        return []
    limit = min(int(limit), 500)  # hard cap so a runaway caller can't pull the table
    con = _connect()
    try:
        if narrator_id:
            cur = con.execute(
                """
                SELECT * FROM story_candidates
                WHERE review_status = 'unreviewed' AND narrator_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?;
                """,
                (narrator_id, limit),
            )
        else:
            cur = con.execute(
                """
                SELECT * FROM story_candidates
                WHERE review_status = 'unreviewed'
                ORDER BY created_at DESC, id DESC
                LIMIT ?;
                """,
                (limit,),
            )
        return [_row_to_story_candidate(r) for r in cur.fetchall()]
    finally:
        con.close()


def story_candidate_list_for_memoir(narrator_id: str) -> List[Dict[str, Any]]:
    """WO-MEMOIR-STORY-CANDIDATES-WIRE-01: captured stories that the
    operator has cleared for the memoir — review_status 'promoted' or
    'memoir_only' (the export gate; unreviewed/discarded never reach a
    family-facing artifact). Ordered oldest-first so stories read in
    the order they were told."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM story_candidates "
            "WHERE narrator_id = ? "
            "  AND review_status IN (" +
            ",".join("?" for _ in STORY_MEMOIR_ELIGIBLE) + ") "
            "ORDER BY created_at ASC",
            (narrator_id, *STORY_MEMOIR_ELIGIBLE),
        ).fetchall()
        return [_row_to_story_candidate(r) for r in rows]
    finally:
        con.close()


def story_candidate_update_placement(
    candidate_id: str,
    *,
    age_bucket: Optional[str] = None,
    era_candidates: Optional[List[str]] = None,
    estimated_year_low: Optional[int] = None,
    estimated_year_high: Optional[int] = None,
    confidence: Optional[str] = None,
    scene_anchors: Optional[List[str]] = None,
) -> None:
    """Update placement metadata after Lori asks the bucket question
    and the narrator answers. Does NOT touch extracted_fields or
    review_* columns — those are owned by their respective lanes.

    Only the supplied fields are written; passing None for a field
    leaves the existing value alone."""
    if confidence is not None and confidence not in _VALID_CONFIDENCE:
        raise ValueError(
            f"confidence must be one of {_VALID_CONFIDENCE}, got {confidence!r}"
        )

    sets: List[str] = []
    params: List[Any] = []
    if age_bucket is not None:
        sets.append("age_bucket = ?")
        params.append(age_bucket)
    if era_candidates is not None:
        sets.append("era_candidates = ?")
        params.append(_json_dump(era_candidates))
    if estimated_year_low is not None:
        sets.append("estimated_year_low = ?")
        params.append(int(estimated_year_low))
    if estimated_year_high is not None:
        sets.append("estimated_year_high = ?")
        params.append(int(estimated_year_high))
    if confidence is not None:
        sets.append("confidence = ?")
        params.append(confidence)
    if scene_anchors is not None:
        sets.append("scene_anchors = ?")
        params.append(_json_dump(scene_anchors))

    if not sets:
        return  # nothing to update

    params.append(candidate_id)
    con = _connect()
    try:
        con.execute(
            f"UPDATE story_candidates SET {', '.join(sets)} WHERE id = ?;",
            params,
        )
        con.commit()
    except sqlite3.Error:
        # BUG-DBLOCK-01 hygiene parity (mirrors save_segment_flag).
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def story_candidate_update_extraction(
    candidate_id: str,
    *,
    extraction_status: str,
    extracted_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """Path 2 (extraction) writes back here AFTER its async work. This
    accessor is what the extractor calls to record what it found, so
    preservation never depends on extraction's success.

    Note: this function is db-side only — it does NOT import the
    extractor. The extractor imports this. That direction is allowed."""
    if extraction_status not in _VALID_EXTRACTION_STATUS:
        raise ValueError(
            f"extraction_status must be one of {_VALID_EXTRACTION_STATUS}, "
            f"got {extraction_status!r}"
        )

    fields_json = _json_dump(extracted_fields or {})
    con = _connect()
    try:
        con.execute(
            """
            UPDATE story_candidates
            SET extraction_status = ?, extracted_fields = ?
            WHERE id = ?;
            """,
            (extraction_status, fields_json, candidate_id),
        )
        con.commit()
    except sqlite3.Error:
        # BUG-DBLOCK-01 hygiene parity (mirrors save_segment_flag).
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def story_candidate_update_review(
    candidate_id: str,
    *,
    review_status: str,
    review_notes: Optional[str] = None,
    reviewed_by: Optional[str] = None,
) -> None:
    """Operator review actions: promote / refine / discard / memoir_only.
    Sets reviewed_at = CURRENT_TIMESTAMP server-side."""
    if review_status not in _VALID_REVIEW_STATUS:
        raise ValueError(
            f"review_status must be one of {_VALID_REVIEW_STATUS}, "
            f"got {review_status!r}"
        )

    con = _connect()
    try:
        con.execute(
            """
            UPDATE story_candidates
            SET review_status = ?,
                review_notes = ?,
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (review_status, review_notes, reviewed_by, candidate_id),
        )
        con.commit()
    except sqlite3.Error:
        # BUG-DBLOCK-01 hygiene parity (mirrors save_segment_flag).
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


# ── WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit A ────────────
#
# Server-authoritative story review. Everything above this block writes a
# story candidate WITHOUT concurrency control: `story_candidate_update_review`
# has no version check, no row-existence check and no narrator check, so a
# bad id silently updates nothing and two operators silently overwrite each
# other. It is retained (tests reference it) and is no longer the review path.

_VALID_PLACEMENT_SOURCE = ("unknown", "narrator_stated", "operator_set", "dob_derived")

# The transitions the review contract accepts. `unreviewed` and `in_review`
# are the provisional states; the other three are terminal decisions the
# operator can still change their mind about.
_REVIEW_TRANSITIONS = ("unreviewed", "in_review", "promoted", "memoir_only", "discarded")


class StoryCandidateNotFound(Exception):
    """No such candidate for this narrator.

    Deliberately does NOT distinguish "no such row" from "belongs to a
    different narrator". Telling a caller which of the two it was would
    confirm the existence of another narrator's candidate to somebody
    who supplied its id.
    """


class StoryReviewConflict(Exception):
    """The observed review_version is stale; someone else wrote first.

    Carries the CURRENT record so the caller can show the operator what
    changed without a second round trip -- and, more importantly, so the
    UI can refuse to discard the operator's typed edit while telling them
    it could not be saved.
    """

    def __init__(self, candidate_id: str, expected: int, actual: int, current: Dict[str, Any]):
        self.candidate_id = candidate_id
        self.expected = expected
        self.actual = actual
        self.current = current
        super().__init__(
            f"story {candidate_id} was reviewed by someone else "
            f"(you saw version {expected}, it is now {actual})"
        )


def story_candidate_review_apply(
    candidate_id: str,
    narrator_id: str,
    expected_version: int,
    *,
    review_status: Optional[str] = None,
    review_notes: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    era_candidates: Optional[List[str]] = None,
    estimated_year_low: Optional[int] = None,
    estimated_year_high: Optional[int] = None,
    placement_source: Optional[str] = None,
    confidence: Optional[str] = None,
    clear_year_range: bool = False,
    clear_eras: bool = False,
) -> Dict[str, Any]:
    """Apply one operator review action atomically. Returns the new row.

    THE CONTRACT, and every clause of it is load-bearing:

    * **Candidate id AND narrator id are both required.** The narrator is
      part of the WHERE clause, not merely validated beforehand, so a
      review can never land on another narrator's candidate even if the
      caller's own scoping is wrong.
    * **The observed `review_version` is compared and incremented inside
      ONE transaction.** `BEGIN IMMEDIATE` takes the write lock before the
      read, so the compare and the write cannot be interleaved by a second
      writer. A stale version raises `StoryReviewConflict` and writes
      nothing.
    * **The preserved narrator transcript is never touched.** `transcript`,
      `audio_clip_path`, `scene_anchors`, `word_count` and the capture
      metadata are absent from the SET list by construction, not by a
      caller remembering to leave them out.
    * **Extraction cannot approve a story.** `extracted_fields` and
      `extraction_status` are likewise absent. Extraction writes through
      `story_candidate_update_extraction`; approval is a human act.

    Omitted arguments are LEFT ALONE. That matters here in a way it did
    not for the older accessor: `story_candidate_update_review` wrote
    `review_notes` and `reviewed_by` unconditionally, so a caller that
    only wanted to change the status silently erased the reviewer's notes.

    `clear_year_range` exists because `None` already means "leave alone",
    so there would otherwise be no way to say "this story has no year
    after all" -- and an operator who mis-dated a story must be able to
    take the date back off rather than only replace it.
    """
    init_db()
    if not (candidate_id or "").strip():
        raise ValueError("candidate_id required")
    if not (narrator_id or "").strip():
        raise ValueError("narrator_id required")
    try:
        expected = int(expected_version)
    except (TypeError, ValueError):
        raise ValueError("expected_version must be an integer")

    if review_status is not None and review_status not in _REVIEW_TRANSITIONS:
        raise ValueError(f"invalid review_status: {review_status!r}")
    if placement_source is not None and placement_source not in _VALID_PLACEMENT_SOURCE:
        raise ValueError(f"invalid placement_source: {placement_source!r}")
    if confidence is not None and confidence not in _VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence: {confidence!r}")

    con = _connect()
    try:
        # The write lock is taken FIRST. A deferred transaction would read
        # the version, then upgrade to a write lock, and lose a race it
        # could not detect.
        con.execute("BEGIN IMMEDIATE;")
        row = con.execute(
            "SELECT * FROM story_candidates WHERE id=? AND narrator_id=?;",
            (candidate_id, narrator_id),
        ).fetchone()
        if row is None:
            con.rollback()
            raise StoryCandidateNotFound(candidate_id)
        current_version = int(row["review_version"] or 1)
        if current_version != expected:
            current = _row_to_story_candidate(row)
            con.rollback()
            raise StoryReviewConflict(candidate_id, expected, current_version, current)

        sets: List[str] = []
        params: List[Any] = []
        if review_status is not None:
            sets.append("review_status = ?")
            params.append(review_status)
            # `reviewed_at` marks the last REVIEW DECISION, so it moves
            # only when the status moves -- a placement correction is not
            # a new decision about the story.
            sets.append("reviewed_at = ?")
            params.append(_now_iso())
        if review_notes is not None:
            sets.append("review_notes = ?")
            params.append(review_notes)
        if reviewed_by is not None:
            sets.append("reviewed_by = ?")
            params.append(reviewed_by)
        if clear_eras:
            # Clear placement: an operator who mis-filed a story must be
            # able to take the placement back OFF, not only replace it.
            sets.append("era_candidates = ?")
            params.append(_json_dump([]))
        elif era_candidates is not None:
            sets.append("era_candidates = ?")
            params.append(_json_dump(list(era_candidates)))
        if clear_year_range:
            sets.append("estimated_year_low = NULL")
            sets.append("estimated_year_high = NULL")
        else:
            if estimated_year_low is not None:
                sets.append("estimated_year_low = ?")
                params.append(int(estimated_year_low))
            if estimated_year_high is not None:
                sets.append("estimated_year_high = ?")
                params.append(int(estimated_year_high))
        if placement_source is not None:
            sets.append("placement_source = ?")
            params.append(placement_source)
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(confidence)

        # The version and the timestamp move on EVERY applied action,
        # including one that only edited a note -- otherwise a second
        # operator's stale save would be accepted because nothing they
        # could observe had changed.
        sets.append("review_version = review_version + 1")
        sets.append("updated_at = ?")
        params.append(_now_iso())

        params.extend([candidate_id, narrator_id, expected])
        cur = con.execute(
            f"UPDATE story_candidates SET {', '.join(sets)} "
            "WHERE id=? AND narrator_id=? AND review_version=?;",
            params,
        )
        if cur.rowcount != 1:
            # Belt and braces: the SELECT above already proved the row and
            # the version, and BEGIN IMMEDIATE holds the write lock, so
            # this is unreachable by concurrency. It is kept because a
            # silent zero-row UPDATE is the failure mode of the accessor
            # this one replaces.
            con.rollback()
            raise StoryReviewConflict(candidate_id, expected, current_version, _row_to_story_candidate(row))
        fresh = con.execute(
            "SELECT * FROM story_candidates WHERE id=? AND narrator_id=?;",
            (candidate_id, narrator_id),
        ).fetchone()

        # ── THE FINAL STATE MUST BE COHERENT, 2026-08-19 ────────────────
        #
        # Validation used to apply only to what the REQUEST carried, so a
        # caller could send `placement_source` alone and leave the row
        # claiming a human placed it nowhere -- or send an era alone and
        # leave a placed-looking story the projection reports as
        # UNPLACED, with the operator's choice silently ignored. Neither
        # is reachable through the panel any more, but the panel is not
        # the only caller and a rule the API does not enforce is a rule
        # that holds until somebody scripts against it.
        #
        # Checked on the ROW AS IT NOW STANDS, inside the same
        # transaction, so a partial request is judged on the state it
        # actually produces rather than on what it mentioned.
        _final_eras = _json_load(fresh["era_candidates"], [])
        _final_source = (fresh["placement_source"] or "unknown").strip()
        if _final_source != "unknown" and not _final_eras:
            con.rollback()
            raise ValueError(
                f"placement_source {_final_source!r} requires exactly one "
                f"life era; this change would leave the story placed "
                f"nowhere")
        if _final_source == "unknown" and _final_eras:
            con.rollback()
            raise ValueError(
                "an era without a placement source reads as UNPLACED "
                "everywhere; record who placed it, or clear the era")
        if len(_final_eras) > 1:
            con.rollback()
            raise ValueError(
                "a placement resolves to exactly one era; two is a pair "
                "of guesses and the Life Map would have to pick")

        con.commit()
        return _row_to_story_candidate(fresh)
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def story_candidate_get_for_narrator(candidate_id: str, narrator_id: str) -> Optional[Dict[str, Any]]:
    """One candidate, scoped to its narrator. None when it is not theirs."""
    init_db()
    if not (candidate_id or "").strip() or not (narrator_id or "").strip():
        return None
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM story_candidates WHERE id=? AND narrator_id=?;",
            (candidate_id, narrator_id),
        ).fetchone()
        return _row_to_story_candidate(row) if row else None
    finally:
        con.close()


def story_candidate_list_for_review(
    narrator_id: str,
    *,
    statuses: Optional[Sequence[str]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Narrator-scoped review list, optionally filtered by review status.

    Distinct from `story_candidate_list_unreviewed`, which is hard-wired
    to `unreviewed` -- so a candidate vanished from the operator's only
    list the moment they acted on it, and there was no way back to it.
    """
    init_db()
    if not (narrator_id or "").strip():
        return []
    limit = max(1, min(int(limit or 100), 500))
    wanted = [s for s in (statuses or ()) if s in _VALID_REVIEW_STATUS]
    con = _connect()
    try:
        if wanted:
            placeholders = ",".join("?" for _ in wanted)
            rows = con.execute(
                f"SELECT * FROM story_candidates WHERE narrator_id=? "
                f"AND review_status IN ({placeholders}) "
                "ORDER BY created_at DESC, id DESC LIMIT ?;",
                [narrator_id, *wanted, limit],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM story_candidates WHERE narrator_id=? "
                "ORDER BY created_at DESC, id DESC LIMIT ?;",
                (narrator_id, limit),
            ).fetchall()
        return [_row_to_story_candidate(r) for r in rows]
    finally:
        con.close()


def story_candidate_status_counts(narrator_id: str) -> Dict[str, int]:
    """Per-status totals for one narrator, every status present as a key.

    Every valid status is returned even at zero. A missing key and a zero
    read the same way to a careless renderer, and "this narrator has no
    discarded stories" is a different statement from "I did not look".
    """
    init_db()
    out = {status: 0 for status in _VALID_REVIEW_STATUS}
    if not (narrator_id or "").strip():
        return out
    con = _connect()
    try:
        for row in con.execute(
            "SELECT review_status, COUNT(*) AS n FROM story_candidates "
            "WHERE narrator_id=? GROUP BY review_status;",
            (narrator_id,),
        ).fetchall():
            status = (row["review_status"] or "").strip()
            if status in out:
                out[status] += int(row["n"])
        return out
    finally:
        con.close()


class StoryTurnBindRejected(Exception):
    """A proposed story→turn link did not prove itself. Nothing written.

    Carries `reason` so the caller can log WHICH check refused without
    re-deriving it. A refusal is a normal, expected outcome -- the bind
    runs on every captured turn and must decline rather than guess.
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def story_candidate_bind_turn_rows(
    candidate_id: str,
    *,
    narrator_id: str,
    conversation_id: str,
    user_turn_row_id: Any,
    assistant_turn_row_id: Any,
) -> Dict[str, Any]:
    """Record which committed rows a preserved story came from.

    WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 Commit 1 (2026-08-19).

    ── THIS IS PROVENANCE. IT IS NOT APPROVAL ──────────────────────────

    The only columns written are `source_user_turn_row_id` and
    `completed_assistant_turn_row_id`. `review_status`, `placement_source`,
    `era_candidates`, the estimated years, `confidence` and
    `extracted_fields` are NOT touched, and must never be touched here.
    Knowing where a story came from says nothing about whether it is
    true, where it belongs, or whether an operator has accepted it. A
    link that also promoted would turn a plumbing fix into an
    unreviewed-material-reaches-the-Life-Map defect.

    ── FIVE PROOFS, OR IT REFUSES ──────────────────────────────────────

    The bind runs late, after the turn is committed, and by then the
    narrator may have switched, the socket may have been reused, and a
    retry may have minted new rows. So nothing is assumed:

      1. the candidate exists;
      2. it belongs to `narrator_id`;
      3. it belongs to `conversation_id`;
      4. both turn rows exist, sit in that same conversation, and
      5. carry the EXPECTED ROLES -- user row `role='user'`, assistant
         row `role='assistant'`.

    Check 5 is the one that catches a caller passing the pair the wrong
    way round, which is otherwise silent and permanent: the story would
    claim to come from Lori's sentence rather than the narrator's.

    Refusal raises `StoryTurnBindRejected` and writes nothing. Attaching
    one narrator's evidence to another is the failure this guards, and
    an unlinked story is merely unlinked.

    Returns the two ids that were written, for the caller's log line.
    """
    init_db()
    cid = (candidate_id or "").strip()
    nid = (narrator_id or "").strip()
    conv = (conversation_id or "").strip()
    if not cid:
        raise StoryTurnBindRejected("candidate_id_required")
    if not nid:
        raise StoryTurnBindRejected("narrator_id_required")
    if not conv:
        raise StoryTurnBindRejected("conversation_id_required")

    def _row_id(value: Any, which: str) -> int:
        try:
            rid = int(value)
        except (TypeError, ValueError):
            raise StoryTurnBindRejected(f"{which}_not_an_int", repr(value))
        if rid <= 0:
            raise StoryTurnBindRejected(f"{which}_not_positive", str(rid))
        return rid

    user_rid = _row_id(user_turn_row_id, "user_turn_row_id")
    asst_rid = _row_id(assistant_turn_row_id, "assistant_turn_row_id")
    # The two rows of one completed turn are different rows. They are
    # commonly adjacent, which is exactly why an equality slip would go
    # unnoticed -- so it is refused explicitly rather than left to the
    # role check below to catch by luck.
    if user_rid == asst_rid:
        raise StoryTurnBindRejected("turn_rows_identical", str(user_rid))

    con = _connect()
    try:
        # ── ONE TRANSACTION, WRITE LOCK FIRST ───────────────────────────
        #
        # Corrected 2026-08-19 after review. Validation used to run
        # OUTSIDE any transaction: the turn rows were checked, and only
        # then did the UPDATE begin. A turn deleted in that gap has
        # already fired migration 0048's clearing trigger, so the bind
        # that follows writes ids pointing at rows which no longer exist
        # -- and the trigger has been and gone, so nothing cleans them up.
        # The result is a dangling provenance record that looks exactly
        # like a real one, which is the failure this whole lane is built
        # to avoid.
        #
        # `BEGIN IMMEDIATE` takes the write lock before the first read, so
        # validation and binding see one consistent database and no
        # deletion can land between them. Same idiom as
        # `story_candidate_review_apply`, and for the same reason: a
        # deferred transaction would read, then upgrade, and lose a race
        # it could not detect.
        con.execute("BEGIN IMMEDIATE;")
        cand = con.execute(
            "SELECT id, narrator_id, conversation_id FROM story_candidates "
            "WHERE id=?;", (cid,),
        ).fetchone()
        if cand is None:
            raise StoryTurnBindRejected("candidate_not_found", cid)
        if (cand["narrator_id"] or "") != nid:
            raise StoryTurnBindRejected(
                "candidate_narrator_mismatch",
                f"candidate={cand['narrator_id']!r} caller={nid!r}")
        if (cand["conversation_id"] or "") != conv:
            raise StoryTurnBindRejected(
                "candidate_conversation_mismatch",
                f"candidate={cand['conversation_id']!r} caller={conv!r}")

        rows = {
            r["id"]: r for r in con.execute(
                "SELECT id, conv_id, role FROM turns WHERE id IN (?, ?);",
                (user_rid, asst_rid),
            ).fetchall()
        }
        for rid, which, expected_role in (
            (user_rid, "user_turn_row", "user"),
            (asst_rid, "assistant_turn_row", "assistant"),
        ):
            row = rows.get(rid)
            if row is None:
                raise StoryTurnBindRejected(f"{which}_not_found", str(rid))
            if (row["conv_id"] or "") != conv:
                raise StoryTurnBindRejected(
                    f"{which}_conversation_mismatch",
                    f"row={row['conv_id']!r} caller={conv!r}")
            if (row["role"] or "").strip().lower() != expected_role:
                raise StoryTurnBindRejected(
                    f"{which}_unexpected_role",
                    f"expected={expected_role!r} got={row['role']!r}")

        # ── PROVENANCE IS WRITE-ONCE ────────────────────────────────────
        #
        # Corrected 2026-08-19 after review. The first cut issued an
        # unconditional UPDATE, so a second bind silently REPLACED the
        # first -- and a provenance record that can be reassigned is not
        # provenance, it is a mutable opinion about where a story came
        # from. A late retry, a duplicated frame or a future second caller
        # could quietly re-point a story at a different turn, and nothing
        # afterwards could tell that had happened.
        #
        # The guard is in the WHERE clause and the verdict is `rowcount`,
        # not the read above: between that SELECT and this UPDATE another
        # writer may have bound the same candidate. A check that trusts
        # its own earlier read is a race with a comment on it.
        cur = con.execute(
            """
            UPDATE story_candidates
               SET source_user_turn_row_id = ?,
                   completed_assistant_turn_row_id = ?
             WHERE id = ? AND narrator_id = ?
               AND source_user_turn_row_id IS NULL
               AND completed_assistant_turn_row_id IS NULL;
            """,
            (user_rid, asst_rid, cid, nid),
        )
        if cur.rowcount == 1:
            con.commit()
            return {
                "candidate_id": cid,
                "source_user_turn_row_id": user_rid,
                "completed_assistant_turn_row_id": asst_rid,
                "already_bound": False,
            }

        # Nothing moved, so this candidate is already bound (or half
        # bound). Re-reading decides which, and only an EXACT match of
        # both fields is success -- a repeat of the same bind is a
        # harmless retry, while a different pair is the reassignment this
        # guard exists to refuse.
        #
        # The read stays INSIDE the transaction. Rolling back first would
        # release the write lock and re-read outside it, which is the same
        # race in miniature: the answer could change between the failed
        # UPDATE and the question about why it failed.
        existing = con.execute(
            "SELECT source_user_turn_row_id, completed_assistant_turn_row_id "
            "FROM story_candidates WHERE id=? AND narrator_id=?;",
            (cid, nid),
        ).fetchone()
        if existing is None:
            raise StoryTurnBindRejected("candidate_not_found", cid)
        have_user = existing["source_user_turn_row_id"]
        have_asst = existing["completed_assistant_turn_row_id"]
        if have_user == user_rid and have_asst == asst_rid:
            # Nothing was written, so the transaction is closed by
            # rollback rather than commit. Idempotent means idempotent:
            # a retry must not even touch the row's timestamps.
            con.rollback()
            return {
                "candidate_id": cid,
                "source_user_turn_row_id": have_user,
                "completed_assistant_turn_row_id": have_asst,
                "already_bound": True,
            }
        # A half-populated pair is refused too. It cannot arise from this
        # function, which writes both or neither -- so it means something
        # else has written one column, and guessing the other would be
        # inventing provenance.
        raise StoryTurnBindRejected(
            "already_bound_to_a_different_turn",
            f"existing=({have_user},{have_asst}) proposed=({user_rid},{asst_rid})")
    except Exception:
        # BUG-DBLOCK-01 hygiene parity with every other writer here --
        # widened from `sqlite3.Error` on 2026-08-19, because every
        # refusal above now raises INSIDE an open write transaction.
        #
        # HONEST SCOPE OF THIS WIDENING, measured rather than assumed.
        # An earlier version of this comment claimed that catching only
        # SQLite errors would leave a rejected bind holding the lock and
        # was "a deadlock source". That is wrong: `finally: con.close()`
        # runs immediately, and a close on an open transaction both
        # releases the lock and discards the uncommitted write --
        # verified directly, not reasoned about. Mutation testing agrees;
        # narrowing this handler kills nothing.
        #
        # It is kept anyway, as defence in depth and as documentation:
        # relying on `close()` to undo a half-written provenance record
        # is a guarantee of the sqlite3 module rather than of this
        # function, and the rollback says out loud what must happen.
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def story_candidate_extraction_result(
    candidate: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """The extraction result for this story's completed turn, or None.

    READ ONLY, and deliberately not merged into anything. Extraction
    output is provisional evidence an operator may find useful while
    reviewing; it is not a fact about the narrator's life until a human
    says so. This returns it so a review surface can SHOW it, and copies
    nothing into `extracted_fields`, `review_status` or any placement
    column.

    ── THE JOIN, AND WHY IT USES THE ASSISTANT ROW ─────────────────────

    `turn_extraction_results.turn_key` is built by
    `turn_extraction_key_for_row` from the id `persist_turn_transaction`
    RETURNS, which is Lori's row. So the join key is
    `completed_assistant_turn_row_id` -- never the user row, and never
    the user row plus one. The story's own provenance is the user row;
    these are two different questions and the columns are separate for
    that reason.

    Narrator ownership is part of the join, not a filter applied after
    it: a turn_key is unique per row id, but reading one narrator's
    evidence while scoped to another is precisely the mistake worth
    making impossible.
    """
    init_db()
    row = candidate or {}
    nid = (row.get("narrator_id") or "").strip()
    key = turn_extraction_key_for_row(row.get("completed_assistant_turn_row_id"))
    if not nid or not key:
        return None
    con = _connect()
    try:
        found = con.execute(
            "SELECT * FROM turn_extraction_results "
            "WHERE narrator_id=? AND turn_key=? "
            "ORDER BY id DESC LIMIT 1;",
            (nid, key),
        ).fetchone()
        if found is None:
            return None
        out = {k: found[k] for k in found.keys()}
        out["items"] = _json_load(out.get("items"), [])
        out["clarification_required"] = _json_load(
            out.get("clarification_required"), [])
        return out
    finally:
        con.close()


# ── WO-LORI-WITNESS-FOLLOWUP-BANK-01 (2026-05-10) ──────────────────────────
#
# Per-session bank of unanswered story-doors. Schema lives in migration
# 0007_follow_up_bank.sql. Accessors below follow the existing house
# style (init_db + _connect + try-commit-finally with rollback hygiene).


def _row_to_banked_question(row) -> Optional[Dict[str, Any]]:
    """Convert sqlite row to dict. Returns None if row is None."""
    if row is None:
        return None
    return {
        "id": row[0],
        "session_id": row[1],
        "person_id": row[2],
        "intent": row[3],
        "question_en": row[4],
        "triggering_anchor": row[5],
        "why_it_matters": row[6],
        "priority": int(row[7]) if row[7] is not None else 5,
        "triggering_turn_index": int(row[8]) if row[8] is not None else 0,
        "asked_at_turn": int(row[9]) if row[9] is not None else None,
        "answered": bool(row[10]),
        "created_at": row[11],
        "updated_at": row[12],
    }


_BANK_SELECT_COLS = (
    "id, session_id, person_id, intent, question_en, "
    "triggering_anchor, why_it_matters, priority, "
    "triggering_turn_index, asked_at_turn, answered, "
    "created_at, updated_at"
)


def followup_bank_add(
    session_id: str,
    intent: str,
    question_en: str,
    triggering_anchor: str,
    why_it_matters: str,
    priority: int = 5,
    triggering_turn_index: int = 0,
    person_id: Optional[str] = None,
) -> str:
    """Insert a banked question. Returns the new row's id (uuid string).

    De-dupes within a session: if a row with the same (session_id,
    intent, triggering_anchor) already exists AND is not yet answered,
    returns its id without writing a new row. This prevents Lori from
    banking the same fragile-name confirmation 5 times during a single
    multi-turn chapter.
    """
    init_db()
    if not session_id or not intent or not question_en or not triggering_anchor:
        raise ValueError("followup_bank_add requires session_id, intent, question_en, triggering_anchor")
    con = _connect()
    try:
        # De-dupe check
        existing = con.execute(
            f"SELECT {_BANK_SELECT_COLS} FROM follow_up_bank "
            "WHERE session_id=? AND intent=? AND triggering_anchor=? "
            "AND answered=0 LIMIT 1;",
            (session_id, intent, triggering_anchor),
        ).fetchone()
        if existing is not None:
            return existing[0]
        new_id = str(uuid.uuid4())
        now = _now_iso()
        con.execute(
            "INSERT INTO follow_up_bank("
            "  id, session_id, person_id, intent, question_en, "
            "  triggering_anchor, why_it_matters, priority, "
            "  triggering_turn_index, asked_at_turn, answered, "
            "  created_at, updated_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?);",
            (
                new_id, session_id, person_id, intent, question_en,
                triggering_anchor, why_it_matters, int(priority),
                int(triggering_turn_index), now, now,
            ),
        )
        con.commit()
        logger.info(
            "[followup-bank] added id=%s session=%s intent=%s priority=%d anchor=%r",
            new_id, session_id, intent, priority, triggering_anchor[:60],
        )
        return new_id
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def followup_bank_get_unanswered(session_id: str) -> List[Dict[str, Any]]:
    """Return all unanswered, not-yet-asked banked questions for a
    session, ordered by priority (1 first) then most-recently-banked
    among ties."""
    init_db()
    con = _connect()
    try:
        rows = con.execute(
            f"SELECT {_BANK_SELECT_COLS} FROM follow_up_bank "
            "WHERE session_id=? AND answered=0 AND asked_at_turn IS NULL "
            "ORDER BY priority ASC, triggering_turn_index DESC;",
            (session_id,),
        ).fetchall()
        return [_row_to_banked_question(r) for r in rows if r is not None]
    finally:
        con.close()


def followup_bank_get_all(session_id: str) -> List[Dict[str, Any]]:
    """Return ALL banked questions for a session (asked + answered +
    open), ordered by priority then turn index. For operator UI
    surface — shows the full bank including resolved doors."""
    init_db()
    con = _connect()
    try:
        rows = con.execute(
            f"SELECT {_BANK_SELECT_COLS} FROM follow_up_bank "
            "WHERE session_id=? "
            "ORDER BY answered ASC, priority ASC, triggering_turn_index DESC;",
            (session_id,),
        ).fetchall()
        return [_row_to_banked_question(r) for r in rows if r is not None]
    finally:
        con.close()


def followup_bank_mark_asked(banked_id: str, asked_at_turn: int) -> None:
    """Mark a banked question as asked at a specific turn index."""
    init_db()
    con = _connect()
    try:
        now = _now_iso()
        con.execute(
            "UPDATE follow_up_bank SET asked_at_turn=?, updated_at=? "
            "WHERE id=?;",
            (int(asked_at_turn), now, banked_id),
        )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def followup_bank_mark_answered(
    banked_id: str, answered: bool = True,
) -> None:
    """Flip the answered flag. Operator UI calls this when a banked
    question has been resolved by the narrator's later turns."""
    init_db()
    con = _connect()
    try:
        now = _now_iso()
        con.execute(
            "UPDATE follow_up_bank SET answered=?, updated_at=? "
            "WHERE id=?;",
            (1 if answered else 0, now, banked_id),
        )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def followup_bank_get_by_id(banked_id: str) -> Optional[Dict[str, Any]]:
    """Lookup by primary key. Returns dict or None."""
    init_db()
    con = _connect()
    try:
        row = con.execute(
            f"SELECT {_BANK_SELECT_COLS} FROM follow_up_bank WHERE id=?;",
            (banked_id,),
        ).fetchone()
        return _row_to_banked_question(row)
    finally:
        con.close()


def followup_bank_clear_session(session_id: str) -> int:
    """Delete all banked questions for a session. Returns rows deleted.
    Operator-only — used for testing / reset."""
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM follow_up_bank WHERE session_id=?;",
            (session_id,),
        )
        con.commit()
        return cur.rowcount or 0
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


# ── WO-LORI-STORY-FIRST-PHASE-1-01 — interview_threads CRUD ─────────────────
#
# Thread bank persistence for the oral-history story-first behavior
# engine. Status enum (Python-side authoritative): 'open' | 'surfaced'
# | 'resolved' | 'declined'. Category enum: 'person' | 'place' |
# 'event' | 'object' | 'time_period'. Schema mirrors the migration at
# server/code/db/migrations/0009_interview_threads.sql; init_db()
# applies the CREATE TABLE idempotently.

_THREAD_SELECT_COLS = (
    "id, session_id, tenant_id, thread_anchor, source_turn_index, "
    "source_excerpt, introduced_at, status, surfaced_at, resolved_at, "
    "category"
)


def _row_to_thread(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def interview_thread_create(
    session_id: str,
    thread_anchor: str,
    source_turn_index: int,
    source_excerpt: str = "",
    category: str = "",
    tenant_id: str = "default",
) -> str:
    """Insert a new open thread. Returns the new id.

    Caller MUST dedupe against existing open threads for the same
    session+anchor BEFORE calling this — the underlying schema does
    not enforce uniqueness on (session_id, thread_anchor) because
    the same anchor may legitimately be re-introduced in a separate
    chapter (different turn index, different excerpt).
    """
    init_db()
    con = _connect()
    try:
        tid = _uuid()
        now = _now_iso()
        con.execute(
            "INSERT INTO interview_threads "
            "(id, session_id, tenant_id, thread_anchor, "
            " source_turn_index, source_excerpt, introduced_at, "
            " status, surfaced_at, resolved_at, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', NULL, NULL, ?);",
            (tid, session_id, tenant_id or "default",
             thread_anchor, int(source_turn_index),
             (source_excerpt or "")[:240], now, category or ""),
        )
        con.commit()
        return tid
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def interview_thread_list_for_session(
    session_id: str,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return threads for `session_id`, optionally filtered by status.
    Ordered by source_turn_index ASC then introduced_at ASC (stable)."""
    init_db()
    con = _connect()
    try:
        if status:
            rows = con.execute(
                f"SELECT {_THREAD_SELECT_COLS} FROM interview_threads "
                "WHERE session_id=? AND status=? "
                "ORDER BY source_turn_index ASC, introduced_at ASC;",
                (session_id, status),
            ).fetchall()
        else:
            rows = con.execute(
                f"SELECT {_THREAD_SELECT_COLS} FROM interview_threads "
                "WHERE session_id=? "
                "ORDER BY source_turn_index ASC, introduced_at ASC;",
                (session_id,),
            ).fetchall()
        return [_row_to_thread(r) for r in rows if r is not None]
    finally:
        con.close()


def interview_thread_anchor_open_exists(
    session_id: str, thread_anchor: str,
) -> bool:
    """True iff an OPEN thread already exists for (session_id, anchor).
    Used by the extractor for dedup. Case-insensitive anchor match."""
    if not session_id or not thread_anchor:
        return False
    init_db()
    con = _connect()
    try:
        row = con.execute(
            "SELECT 1 FROM interview_threads "
            "WHERE session_id=? AND status='open' "
            "  AND LOWER(thread_anchor)=LOWER(?) LIMIT 1;",
            (session_id, thread_anchor),
        ).fetchone()
        return row is not None
    finally:
        con.close()


def interview_thread_set_status(
    thread_id: str,
    new_status: str,
    *,
    surfaced_at: Optional[str] = None,
    resolved_at: Optional[str] = None,
) -> None:
    """Update status + optional timestamps. Caller passes the right
    *_at value for the transition; this function does not infer."""
    if new_status not in ("open", "surfaced", "resolved", "declined"):
        raise ValueError(f"invalid thread status: {new_status!r}")
    init_db()
    con = _connect()
    try:
        # Build dynamic SET clause based on which timestamps were
        # provided. We never overwrite a non-null timestamp; the
        # COALESCE ensures the existing value wins if a re-transition
        # passes None.
        con.execute(
            "UPDATE interview_threads "
            "SET status=?, "
            "    surfaced_at=COALESCE(?, surfaced_at), "
            "    resolved_at=COALESCE(?, resolved_at) "
            "WHERE id=?;",
            (new_status, surfaced_at, resolved_at, thread_id),
        )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def interview_thread_get_by_id(thread_id: str) -> Optional[Dict[str, Any]]:
    """Lookup a thread by primary key."""
    if not thread_id:
        return None
    init_db()
    con = _connect()
    try:
        row = con.execute(
            f"SELECT {_THREAD_SELECT_COLS} FROM interview_threads WHERE id=?;",
            (thread_id,),
        ).fetchone()
        return _row_to_thread(row)
    finally:
        con.close()


def interview_thread_clear_session(session_id: str) -> int:
    """Delete all threads for a session. Returns rows deleted.
    Operator/test-only — production should never call this on a live
    session because banked threads are part of the session's memory."""
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM interview_threads WHERE session_id=?;",
            (session_id,),
        )
        con.commit()
        return cur.rowcount or 0
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────
# WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A
#
# bio_fields + bio_facts CRUD accessors. Mirrors the BUG-DBLOCK-01
# try/except/finally rollback hygiene from the safety + story_candidate
# accessors. All writes go through this layer; bio_schema.py validates
# inputs before the write fires.
# ─────────────────────────────────────────────────────────────────────


_BIO_FIELD_SELECT_COLS = (
    "id, field_key, field_label, field_category, field_type, "
    "narrative_value, life_stage_range, asking_anchors, "
    "created_at, updated_at"
)

_BIO_FACT_SELECT_COLS = (
    "id, tenant_id, narrator_id, field_key, value, status, source, "
    "confidence, chapter_continuation_metric, conflict_with, "
    "created_at, last_updated"
)


def _row_to_bio_field(row: Any) -> Dict[str, Any]:
    return {
        "id": row[0],
        "field_key": row[1],
        "field_label": row[2],
        "field_category": row[3],
        "field_type": row[4],
        "narrative_value": row[5],
        "life_stage_range": row[6],
        "asking_anchors": row[7],  # JSON string — caller json.loads if needed
        "created_at": row[8],
        "updated_at": row[9],
    }


def _row_to_bio_fact(row: Any) -> Dict[str, Any]:
    return {
        "id": row[0],
        "tenant_id": row[1],
        "narrator_id": row[2],
        "field_key": row[3],
        "value": row[4],  # JSON string — caller json.loads if needed
        "status": row[5],
        "source": row[6],  # JSON string
        "confidence": row[7],
        "chapter_continuation_metric": row[8],  # JSON string or None
        "conflict_with": row[9],
        "created_at": row[10],
        "last_updated": row[11],
    }


def bio_field_upsert(
    field_key: str,
    field_label: str,
    field_category: str,
    field_type: str,
    *,
    narrative_value: str = "medium",
    life_stage_range: str = "all",
    asking_anchors_json: str = "[]",
) -> str:
    """Insert-or-update a bio_fields row keyed by field_key.

    Returns the row id. Caller (bio_schema seed loader) provides
    already-validated values; this layer does not re-validate enum
    constraints to keep the write hot path tight.
    """
    init_db()
    con = _connect()
    try:
        now = _now_iso()
        existing = con.execute(
            "SELECT id FROM bio_fields WHERE field_key=?;",
            (field_key,),
        ).fetchone()
        if existing:
            row_id = existing[0]
            con.execute(
                """
                UPDATE bio_fields
                   SET field_label=?, field_category=?, field_type=?,
                       narrative_value=?, life_stage_range=?,
                       asking_anchors=?, updated_at=?
                 WHERE id=?;
                """,
                (field_label, field_category, field_type,
                 narrative_value, life_stage_range,
                 asking_anchors_json, now, row_id),
            )
        else:
            row_id = _uuid()
            con.execute(
                """
                INSERT INTO bio_fields (
                    id, field_key, field_label, field_category, field_type,
                    narrative_value, life_stage_range, asking_anchors,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (row_id, field_key, field_label, field_category, field_type,
                 narrative_value, life_stage_range, asking_anchors_json,
                 now, now),
            )
        con.commit()
        return row_id
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def bio_field_get_by_key(field_key: str) -> Optional[Dict[str, Any]]:
    """Lookup a bio_fields row by canonical field_key."""
    init_db()
    con = _connect()
    try:
        row = con.execute(
            f"SELECT {_BIO_FIELD_SELECT_COLS} FROM bio_fields "
            "WHERE field_key=?;",
            (field_key,),
        ).fetchone()
        return _row_to_bio_field(row) if row else None
    finally:
        con.close()


def bio_field_list(
    category: Optional[str] = None,
    narrative_value: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List bio_fields, optionally filtered. Ordered by field_category +
    field_key for deterministic operator-UI presentation."""
    init_db()
    con = _connect()
    try:
        clauses: List[str] = []
        params: List[Any] = []
        if category:
            clauses.append("field_category=?")
            params.append(category)
        if narrative_value:
            clauses.append("narrative_value=?")
            params.append(narrative_value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = con.execute(
            f"SELECT {_BIO_FIELD_SELECT_COLS} FROM bio_fields"
            f"{where} ORDER BY field_category ASC, field_key ASC;",
            tuple(params),
        ).fetchall()
        return [_row_to_bio_field(r) for r in rows]
    finally:
        con.close()


def bio_field_count() -> int:
    """Total bio_fields row count. Operators use this to confirm seed
    landed; tests use it to lock the seed size."""
    init_db()
    con = _connect()
    try:
        row = con.execute("SELECT COUNT(*) FROM bio_fields;").fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        con.close()


def bio_fact_create(
    *,
    narrator_id: str,
    field_key: str,
    value_json: str,
    status: str,
    source_json: str = "{}",
    confidence: float = 0.0,
    chapter_continuation_metric_json: Optional[str] = None,
    conflict_with: Optional[str] = None,
    tenant_id: str = "default",
) -> str:
    """Insert a new bio_facts row. Returns the new id.

    Multiple rows per (narrator_id, field_key) are intentionally
    allowed — the WO's conflict-as-audit-trail model means the bio
    fact does NOT enforce uniqueness. Callers that need dedupe
    semantics (e.g., Tier 1 extraction routing same fact twice in a
    row) check first via bio_fact_list_by_field.
    """
    init_db()
    con = _connect()
    try:
        new_id = _uuid()
        now = _now_iso()
        con.execute(
            """
            INSERT INTO bio_facts (
                id, tenant_id, narrator_id, field_key, value, status,
                source, confidence, chapter_continuation_metric,
                conflict_with, created_at, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (new_id, tenant_id or "default", narrator_id, field_key,
             value_json or '""', status or "empty",
             source_json or "{}", float(confidence or 0.0),
             chapter_continuation_metric_json, conflict_with,
             now, now),
        )
        con.commit()
        return new_id
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def bio_fact_get(fact_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    try:
        row = con.execute(
            f"SELECT {_BIO_FACT_SELECT_COLS} FROM bio_facts WHERE id=?;",
            (fact_id,),
        ).fetchone()
        return _row_to_bio_fact(row) if row else None
    finally:
        con.close()


def bio_fact_list_by_narrator(
    narrator_id: str,
    *,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """All bio_facts for a narrator, optionally filtered by status."""
    init_db()
    con = _connect()
    try:
        if status:
            rows = con.execute(
                f"SELECT {_BIO_FACT_SELECT_COLS} FROM bio_facts "
                "WHERE narrator_id=? AND status=? "
                "ORDER BY field_key ASC, last_updated DESC;",
                (narrator_id, status),
            ).fetchall()
        else:
            rows = con.execute(
                f"SELECT {_BIO_FACT_SELECT_COLS} FROM bio_facts "
                "WHERE narrator_id=? "
                "ORDER BY field_key ASC, last_updated DESC;",
                (narrator_id,),
            ).fetchall()
        return [_row_to_bio_fact(r) for r in rows]
    finally:
        con.close()


def bio_fact_list_by_field(
    narrator_id: str,
    field_key: str,
) -> List[Dict[str, Any]]:
    """All bio_facts rows for one (narrator, field) — used by Tier 1
    conflict detection."""
    init_db()
    con = _connect()
    try:
        rows = con.execute(
            f"SELECT {_BIO_FACT_SELECT_COLS} FROM bio_facts "
            "WHERE narrator_id=? AND field_key=? "
            "ORDER BY last_updated DESC;",
            (narrator_id, field_key),
        ).fetchall()
        return [_row_to_bio_fact(r) for r in rows]
    finally:
        con.close()


def bio_fact_set_status(
    fact_id: str,
    status: str,
    *,
    conflict_with: Optional[str] = None,
) -> bool:
    """Update status (and optionally conflict_with). Returns True on
    successful update, False if the row doesn't exist."""
    init_db()
    con = _connect()
    try:
        now = _now_iso()
        cur = con.execute(
            "UPDATE bio_facts SET status=?, conflict_with=?, "
            "last_updated=? WHERE id=?;",
            (status, conflict_with, now, fact_id),
        )
        con.commit()
        return (cur.rowcount or 0) > 0
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def bio_fact_clear_narrator(narrator_id: str) -> int:
    """Delete all bio_facts for a narrator. Operator/test-only — never
    call this on a live narrator without explicit operator approval;
    the rows are part of the bio audit trail."""
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM bio_facts WHERE narrator_id=?;",
            (narrator_id,),
        )
        con.commit()
        return cur.rowcount or 0
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def bio_schema_seed_load_to_db() -> int:
    """Idempotently load the universal bio_schema seed to the DB.

    Returns the number of fields written (insert or update). Imported
    lazily so test environments that don't need the bio schema can
    avoid the import cost.
    """
    from .services.bio_schema import iter_seed, validate_seed
    errors = validate_seed()
    if errors:
        # Validation errors block the load — better to fail loud than
        # write a malformed seed that breaks downstream FK constraints.
        raise RuntimeError(
            "bio_schema seed validation failed: " + "; ".join(errors)
        )
    n = 0
    for fd in iter_seed():
        bio_field_upsert(
            field_key=fd.field_key,
            field_label=fd.field_label,
            field_category=fd.field_category,
            field_type=fd.field_type,
            narrative_value=fd.narrative_value,
            life_stage_range=fd.life_stage_range,
            asking_anchors_json=fd.asking_anchors_json(),
        )
        n += 1
    return n


# ─────────────────────────────────────────────────────────────────────
# WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1A
#
# consent_attestations CRUD. One row per attestation event. Two rows
# per fully-consented narrator (one for recording_agreement, one for
# disclosure_reviewed). Operator-on-behalf attestations carry the
# operator id in `checked_by_operator`; narrator-self attestations
# leave it as ''.
# ─────────────────────────────────────────────────────────────────────


_CONSENT_ATTEST_TYPES = frozenset({
    "recording_agreement",
    "disclosure_reviewed",
})


def consent_attestation_create(
    narrator_id: str,
    attestation_type: str,
    *,
    checked_by_operator: str = "",
    notes: str = "",
) -> str:
    """Insert a single consent attestation row. Returns the new id.

    `attestation_type` must be one of _CONSENT_ATTEST_TYPES. Raises
    ValueError on unknown type rather than writing a malformed row.
    """
    if attestation_type not in _CONSENT_ATTEST_TYPES:
        raise ValueError(
            f"unknown attestation_type: {attestation_type!r}; "
            f"expected one of {sorted(_CONSENT_ATTEST_TYPES)}"
        )
    init_db()
    con = _connect()
    try:
        new_id = _uuid()
        now = _now_iso()
        con.execute(
            "INSERT INTO consent_attestations "
            "(id, narrator_id, attestation_type, attested_at, "
            " checked_by_operator, notes) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (new_id, narrator_id, attestation_type, now,
             checked_by_operator or "", notes or ""),
        )
        con.commit()
        return new_id
    except sqlite3.Error:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def consent_attestation_list_for_narrator(
    narrator_id: str,
    attestation_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return all consent attestations for a narrator, newest first.

    Optional filter by attestation_type. Operator dashboards use this
    to surface consent-pending warnings for narrators missing either
    type of attestation.
    """
    init_db()
    con = _connect()
    try:
        if attestation_type:
            rows = con.execute(
                "SELECT id, narrator_id, attestation_type, attested_at, "
                "       checked_by_operator, notes "
                "FROM consent_attestations "
                "WHERE narrator_id=? AND attestation_type=? "
                "ORDER BY attested_at DESC;",
                (narrator_id, attestation_type),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, narrator_id, attestation_type, attested_at, "
                "       checked_by_operator, notes "
                "FROM consent_attestations "
                "WHERE narrator_id=? "
                "ORDER BY attested_at DESC;",
                (narrator_id,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "narrator_id": r[1],
                "attestation_type": r[2],
                "attested_at": r[3],
                "checked_by_operator": r[4],
                "notes": r[5],
            }
            for r in rows
        ]
    finally:
        con.close()


def consent_attestation_has_complete_set(narrator_id: str) -> bool:
    """True iff the narrator has at least one row for each of the
    required attestation types. Used by operator dashboards to flag
    consent-pending narrators."""
    rows = consent_attestation_list_for_narrator(narrator_id)
    seen = {r["attestation_type"] for r in rows}
    return _CONSENT_ATTEST_TYPES.issubset(seen)


# -----------------------------------------------------------------------------
# WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7) --- turn_extraction_ledger CRUD
# -----------------------------------------------------------------------------
#
# Schema: server/code/db/migrations/0038_turn_extraction_ledger.sql.
#
# THE CLAIM IS THE GUARD. turn_extraction_claim() performs an INSERT
# against a UNIQUE INDEX on (narrator_id, turn_key). The database, not
# a Python set, decides who wins. That is deliberate: an in-process
# guard dies with the worker, so a socket reconnect after a restart
# would re-extract the same committed turn and duplicate its proposals.
#
# The claim is written BEFORE the work runs, at outcome='started', and
# is updated to a terminal outcome after. A row left at 'started' is a
# recorded in-flight attempt -- which is what makes an extraction that
# disappears on process shutdown auditable instead of invisible.
#
# NOTHING HERE IS TRUTH. The ledger records that extraction was
# requested for a persisted turn and how the request ended. It stores
# identifiers, counts, and classifications only -- no narrative text,
# no extracted values, no field paths (Gate 7 Step 5 privacy rule).

TURN_EXTRACTION_OUTCOMES: Tuple[str, ...] = (
    "started",
    "succeeded",
    "noop",
    "failed",
)


def turn_extraction_key_for_row(turn_row_id: Any) -> str:
    """Build the canonical turn_key from a committed `turns.id`.

    Single place where the key format is decided so no caller invents a
    second one. Returns "" when the row id is missing or not an int-like
    value -- callers treat "" as "no stable key" and skip turn-scoped
    idempotency rather than fall back to hashing text.
    """
    try:
        rid = int(turn_row_id)
    except (TypeError, ValueError):
        return ""
    if rid <= 0:
        return ""
    return f"turnrow:{rid}"


def _row_to_turn_extraction(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def turn_extraction_get(
    narrator_id: str,
    turn_key: str,
) -> Optional[Dict[str, Any]]:
    """Look up the ledger row for one (narrator, persisted turn) pair."""
    if not narrator_id or not turn_key:
        return None
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            "SELECT * FROM turn_extraction_ledger "
            "WHERE narrator_id = ? AND turn_key = ? LIMIT 1;",
            (narrator_id, turn_key),
        )
        return _row_to_turn_extraction(cur.fetchone())
    finally:
        con.close()


def turn_extraction_claim(
    *,
    narrator_id: str,
    turn_key: str,
    turn_id: str = "",
    session_id: str = "",
    turn_mode: str = "",
    source: str = "",
) -> Optional[int]:
    """Claim the right to extract this persisted turn exactly once.

    Returns the new ledger row id when THIS caller won the claim, or
    None when a row already exists -- meaning some earlier attempt
    already owns this turn and the caller must report `duplicate` and
    do no work.

    The IntegrityError from the UNIQUE INDEX is the mechanism, not an
    error condition to be papered over. Any other sqlite error is
    re-raised: a broken ledger must not silently degrade into
    "extract every time".
    """
    if not narrator_id or not turn_key:
        return None
    init_db()
    now = _now_iso()
    con = _connect()
    try:
        cur = con.execute(
            """
            INSERT INTO turn_extraction_ledger(
                narrator_id, turn_key, turn_id, session_id, turn_mode,
                source, outcome, item_count, method, error_class,
                duration_ms, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,'started',0,'','',0,?,?);
            """,
            (
                narrator_id, turn_key, turn_id or "", session_id or "",
                turn_mode or "", source or "", now, now,
            ),
        )
        con.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # Expected on replay/reconnect/retry. Not a failure.
        try:
            con.rollback()
        except Exception:
            pass
        return None
    finally:
        con.close()


def turn_extraction_finish(
    *,
    ledger_id: int,
    outcome: str,
    item_count: int = 0,
    method: str = "",
    error_class: str = "",
    duration_ms: int = 0,
) -> bool:
    """Record the terminal outcome for a claim. Returns True if updated.

    `outcome` must be one of TURN_EXTRACTION_OUTCOMES minus 'started'.
    'duplicate' is deliberately NOT storable -- it describes a second
    attempt, and writing it here would overwrite the first attempt's
    real result.
    """
    if not ledger_id:
        return False
    outcome = (outcome or "").strip()
    if outcome not in ("succeeded", "noop", "failed"):
        raise ValueError(
            "turn_extraction_finish outcome must be succeeded|noop|failed; "
            f"got {outcome!r}"
        )
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            """
            UPDATE turn_extraction_ledger
               SET outcome = ?, item_count = ?, method = ?,
                   error_class = ?, duration_ms = ?, updated_at = ?
             WHERE id = ?;
            """,
            (
                outcome, int(item_count or 0), method or "",
                error_class or "", int(duration_ms or 0), _now_iso(),
                int(ledger_id),
            ),
        )
        con.commit()
        return bool(cur.rowcount)
    finally:
        con.close()


def turn_extraction_count_for_narrator(narrator_id: str) -> int:
    """How many ledger rows exist for this narrator. Harness/probe use."""
    if not narrator_id:
        return 0
    init_db()
    con = _connect()
    try:
        cur = con.execute(
            "SELECT COUNT(*) FROM turn_extraction_ledger WHERE narrator_id = ?;",
            (narrator_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        con.close()


# ── Durable extraction results (migration 0041) ──────────────────────────
#
# WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2. The backend now
# owns extraction and the browser still owns projection and Shadow
# Review, so a result has to survive the gap between them. A WebSocket
# frame does not: the narrator can close the tab, reload, lose the
# socket, or switch narrator while extraction is still running.
#
# These four functions are the whole lifecycle. Stored when the work is
# done, delivered when it goes on a socket, applied only when the
# browser says so. The gap between the last two is deliberate -- a send
# that did not raise is not evidence that anything was applied.


def turn_extraction_result_store(
    *,
    narrator_id: str,
    turn_key: str,
    turn_id: str = "",
    session_id: str = "",
    status: str = "succeeded",
    method: str = "",
    items: Optional[List[Dict[str, Any]]] = None,
    clarification_required: Optional[List[Dict[str, Any]]] = None,
    ledger_id: Optional[int] = None,
) -> Optional[int]:
    """Persist one applicable result. Idempotent on (narrator, turn_key).

    Returns the row id, or None when there was nothing to store or the
    key is missing. A replayed turn re-reaches the existing row rather
    than minting a second one, so the browser can never be handed the
    same turn's fields twice.

    `items` and `clarification_required` are the structured extractor
    output the browser already knows how to apply. No narrator prose is
    written here.
    """
    narrator_id = (narrator_id or "").strip()
    turn_key = (turn_key or "").strip()
    if not narrator_id or not turn_key:
        return None
    status = (status or "").strip() or "succeeded"
    if status not in ("succeeded", "noop", "failed"):
        raise ValueError(
            "turn_extraction_result_store status must be "
            f"succeeded|noop|failed; got {status!r}"
        )
    payload = items or []
    clar = clarification_required or []
    init_db()
    con = _connect()
    try:
        row = con.execute(
            "SELECT id FROM turn_extraction_results "
            " WHERE narrator_id = ? AND turn_key = ?;",
            (narrator_id, turn_key),
        ).fetchone()
        if row:
            # Already stored. Do NOT overwrite: the first result for a
            # committed turn is the real one, and a replay must not
            # reopen work the browser may already have applied.
            return int(row[0])
        cur = con.execute(
            """
            INSERT INTO turn_extraction_results
                (ledger_id, narrator_id, turn_key, turn_id, session_id,
                 status, method, items, clarification_required,
                 item_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                int(ledger_id) if ledger_id else None,
                narrator_id, turn_key, turn_id or "", session_id or "",
                status, method or "",
                _json_dump(payload), _json_dump(clar),
                len(payload), _now_iso(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    except sqlite3.OperationalError:
        # Pre-0041 database. Losing the durable copy costs catch-up, not
        # the turn, and the caller is a completed turn that must not be
        # disturbed.
        return None
    finally:
        con.close()


def turn_extraction_results_pending(
    narrator_id: str,
    session_id: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Results this narrator has not applied yet, oldest first.

    Scoped by narrator BY REQUIRED ARGUMENT rather than by optional
    filter: a catch-up read with no narrator is a cross-person read, and
    the boundary is easier to keep as a signature than as a caller's
    discipline. ``session_id`` narrows further when supplied.
    """
    narrator_id = (narrator_id or "").strip()
    if not narrator_id:
        return []
    init_db()
    con = _connect()
    try:
        sql = ("SELECT * FROM turn_extraction_results "
               " WHERE narrator_id = ? AND applied_at IS NULL ")
        args: List[Any] = [narrator_id]
        if session_id:
            sql += " AND session_id = ? "
            args.append(session_id)
        sql += " ORDER BY created_at, id LIMIT ?;"
        args.append(max(1, min(int(limit or 50), 500)))
        rows = con.execute(sql, tuple(args)).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            for key in ("items", "clarification_required"):
                d[key] = _json_load(d.get(key), []) or []
            out.append(d)
        return out
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def turn_source_text_for_key(turn_key: str) -> str:
    """The narrator's words for the turn this result came from.

    WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2. Catch-up must
    show Shadow Review the SAME source text the live path shows, and the
    live frame carries it from the claim. Rather than store a second copy
    of the transcript in turn_extraction_results, this reads the one that
    already exists.

    turn_key is 'turnrow:<turns.id>' and that id is the ASSISTANT row.
    persist_turn_transaction writes the user turn first, so the narrator
    utterance is the nearest preceding user row in the same conversation.

    Returns "" when the key is unparseable or the row is gone. A missing
    source echo costs a display detail; guessing would cost attribution.
    """
    key = (turn_key or "").strip()
    if not key.startswith("turnrow:"):
        return ""
    try:
        assistant_id = int(key.split(":", 1)[1])
    except (ValueError, IndexError):
        return ""
    init_db()
    con = _connect()
    try:
        row = con.execute(
            "SELECT content FROM turns "
            " WHERE conv_id = (SELECT conv_id FROM turns WHERE id = ?) "
            "   AND role = 'user' AND id < ? "
            " ORDER BY id DESC LIMIT 1;",
            (assistant_id, assistant_id),
        ).fetchone()
        return (row[0] if row else "") or ""
    except sqlite3.OperationalError:
        return ""
    finally:
        con.close()


def turn_extraction_result_mark_delivered(
    narrator_id: str, turn_key: str,
) -> bool:
    """Stamp that the result went onto a socket. NOT that it was applied.

    Deliberately does not retire the obligation. ws.send() returning
    without raising says the frame left this process; it says nothing
    about a browser that was closing at the time.
    """
    return _turn_extraction_result_stamp(narrator_id, turn_key, "delivered_at")


def turn_extraction_result_mark_applied(
    narrator_id: str, turn_key: str,
) -> bool:
    """Retire the obligation. Only the browser's acknowledgment gets here."""
    return _turn_extraction_result_stamp(narrator_id, turn_key, "applied_at")


def _turn_extraction_result_stamp(
    narrator_id: str, turn_key: str, column: str,
) -> bool:
    if column not in ("delivered_at", "applied_at"):
        raise ValueError("stamp column must be delivered_at|applied_at")
    narrator_id = (narrator_id or "").strip()
    turn_key = (turn_key or "").strip()
    if not narrator_id or not turn_key:
        return False
    # `column` is whitelisted immediately above, so this interpolation
    # cannot carry caller input into SQL. The values stay parameterised.
    sql = (
        "UPDATE turn_extraction_results"
        "   SET " + column + " = ?"
        " WHERE narrator_id = ? AND turn_key = ? AND " + column + " IS NULL;"
    )
    init_db()
    con = _connect()
    try:
        cur = con.execute(sql, (_now_iso(), narrator_id, turn_key))
        con.commit()
        return bool(cur.rowcount)
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


# ── Connection-hygiene wrap (SECURITY/STABILITY-REVIEW-2026-08-12) ──────────
# Applied LAST, after every function is defined.  Wraps every PUBLIC
# module-level function with _closes_connections_on_error so that an
# exception anywhere in a db call closes the connections that call opened
# (see the rationale comment inside _connect()).  Explicit facts this
# relies on, verified 2026-08-12: this module contains no generator
# functions and no async functions, so a plain wrapper preserves
# semantics.  Private helpers (leading underscore) are NOT wrapped — they
# run inside a wrapped public caller and their connections register to
# that caller's list.
def _wrap_module_functions_for_connection_hygiene() -> int:
    g = globals()
    wrapped = 0
    for _name, _obj in list(g.items()):
        if _name.startswith("_"):
            continue
        if not isinstance(_obj, types.FunctionType):
            continue
        if _obj.__module__ != __name__:
            continue  # names imported from elsewhere are not ours to wrap
        if getattr(_obj, "__hornelore_conn_guard__", False):
            continue
        g[_name] = _closes_connections_on_error(_obj)
        wrapped += 1
    return wrapped


_CONN_GUARD_WRAPPED_COUNT = _wrap_module_functions_for_connection_hygiene()
logger.info("db connection-hygiene wrap active on %d functions",
            _CONN_GUARD_WRAPPED_COUNT)
