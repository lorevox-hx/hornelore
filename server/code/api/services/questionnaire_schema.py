"""The questionnaire's field schema, read from the file that defines it.

WO-03B. Filed from BUG-SUGGESTION-ACCEPTED-INTO-AN-INVISIBLE-FIELD-01.

WHY THIS EXISTS
---------------
On 2026-09-20 a suggestion was accepted through the review surface. The
whole transaction succeeded — questionnaire written, provenance stamped
`ai_suggested/acceptance`, queue cleared, review recorded, revision 8 —
and the value was then invisible. It had been proposed for
`personal.notes`, and the Personal Information section defines seven
fields, none of them `notes`. The form could not render it, so a person
had approved information they could not afterwards see or correct.

`questionnaire_persistence` will create any path it is handed: `_set`
walks and builds. That is correct for a storage layer and disastrous as
the only check, because it turns a typo in an extractor's `fieldPath`
into a durable orphan key with provenance attached.

THE SCHEMA IS THE JAVASCRIPT, AND THAT IS NOT NEGOTIABLE HERE
-------------------------------------------------------------
`SECTIONS` in `ui/js/bio-builder-questionnaire.js` is what renders the
form. It is therefore the only thing that decides whether an accepted
value will be visible. There is no build step, no generated JSON, and no
complete server-side enumeration — the nearest candidates have all
drifted:

    extract.py EXTRACTABLE_FIELDS   141 paths, includes residence.*,
                                    travel.*, military.*, faith.* which
                                    the questionnaire does not define,
                                    and omits ones it does
    projection-map.js FIELD_MAP     25 of ~130 fields
    bio_schema.py                   a different vocabulary entirely
                                    (bio_facts keys, snake_case)

So a Python copy would be a seventeenth parallel list, and the one thing
every existing copy has in common is that it drifted. This module reads
the real file instead.

FAIL CLOSED, LOUDLY
-------------------
A parser over someone else's source is fragile, and the dangerous
failure is a SILENT partial parse: read half the fields, and validation
starts rejecting perfectly good destinations — or worse, a parse that
returns nothing and a caller that treats "not found" as "allow".

So `load_schema()` validates its own output against invariants that
cannot hold by accident (section count, repeatable count, a sample of
known fields) and raises `SchemaUnavailable` if any fail. Callers must
let that propagate; refusing to accept is the safe direction, because
the alternative is writing another invisible value.

I got this wrong once already while building it: a first regex matched
nested objects and reported "76 sections, 31 fields", which would have
rejected every real destination. The count assertions below exist
because that happened, not in anticipation of it.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Dict, List, Optional, Tuple

__all__ = [
    "SchemaUnavailable", "load_schema", "is_defined", "is_repeatable",
    "labels_for", "section_ids", "repeatable_section_ids", "schema_fingerprint",
]

# Located relative to this file: server/code/api/services/ -> repo root.
_JS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "ui", "js", "bio-builder-questionnaire.js",
))

# Invariants. If the questionnaire legitimately grows a section these
# move — deliberately, in the same commit — and the test that mirrors
# them fails until they do.
_EXPECT_SECTIONS = 20
_EXPECT_REPEATABLE = 11
# Measured, not guessed. The first draft of this constant said 100 and
# the parser was right — 91 — which is the failure mode these invariants
# are meant to catch working in the awkward direction. An invariant
# asserted from memory is a bug with a confident tone.
# WO-04 added military (9), residence (5), travel (6), faith (5),
# education.gradeLevel and marriage.marriagePlace: 91 + 27 = 118.
# Re-measured from the file, not incremented from memory.
_EXPECT_FIELDS = 118
# A sample that a partial or misaligned parse would not produce. Every
# one of these was read out of the file, not recalled.
_EXPECT_PRESENT: Tuple[Tuple[str, str], ...] = (
    ("personal", "placeOfBirth"),
    ("personal", "timeOfBirth"),
    ("personal", "zodiacSign"),
    ("parents", "occupation"),
    ("parents", "notableLifeEvents"),
    ("grandparents", "side"),
    ("education", "schooling"),
    ("additionalNotes", "messagesForFutureGenerations"),
    # WO-04's four new sections, sampled so a parse that silently
    # dropped one is caught.
    ("military", "branch"),
    ("military", "serviceStart"),
    ("residence", "place"),
    ("travel", "whatHappened"),
    ("faith", "denomination"),
    ("marriage", "marriagePlace"),
    ("education", "gradeLevel"),
)
# Known NOT to exist. Guards the opposite failure: a parser so loose it
# accepts anything would pass the presence checks above.
_EXPECT_ABSENT: Tuple[Tuple[str, str], ...] = (
    # `personal.notes` stays absent deliberately — WO-04 decision 4
    # retires it as an extraction destination rather than creating a
    # catch-all field, which is where information goes to be unfindable.
    # ZZ's historical accepted value at that path is preserved; nothing
    # rewrites it.
    ("personal", "notes"),
    # `residence.place` and `military.branch` WERE here and are now
    # real fields (WO-04). Replaced with paths that remain undefined, so
    # the guard against a too-loose parser still has teeth.
    ("military", "servicePeriod"),      # superseded by serviceStart/End
    ("residence", "period"),            # superseded by periodStart/End
    ("community", "organization"),      # no community section
)


class SchemaUnavailable(RuntimeError):
    """The questionnaire schema could not be read or did not validate.

    Never swallow this into "allow the write". The whole point of the
    module is that an unverifiable destination is refused."""


_lock = threading.Lock()
_cache: Optional[Dict[str, Dict]] = None
_cache_key: Optional[Tuple[float, int]] = None


# ── stripping comments without eating string contents ────────────────


def _strip_comments(src: str) -> str:
    """Remove // and /* */ comments, respecting string literals.

    Necessary rather than cosmetic: the `parents` section carries an
    eighteen-line bug narrative inside its `fields` array, and prose
    contains braces and quotes that would wreck a brace walk.
    """
    out = []
    i, n = 0, len(src)
    quote = None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`":
            quote = c; out.append(c); i += 1; continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        out.append(c); i += 1
    return "".join(out)


def _match_bracket(src: str, start: int) -> int:
    """Index just past the bracket/brace opened at `start`."""
    opener = src[start]
    closer = {"[": "]", "{": "}"}[opener]
    depth = 0
    i, n = start, len(src)
    quote = None
    while i < n:
        c = src[i]
        if quote:
            if c == "\\":
                i += 2; continue
            if c == quote:
                quote = None
            i += 1; continue
        if c in "\"'`":
            quote = c; i += 1; continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SchemaUnavailable(f"unbalanced {opener!r} at {start}")


def _split_objects(array_src: str) -> List[str]:
    """Top-level `{...}` members of an array literal, in order."""
    out: List[str] = []
    i, n = 0, len(array_src)
    while i < n:
        if array_src[i] == "{":
            end = _match_bracket(array_src, i)
            out.append(array_src[i:end])
            i = end
        else:
            i += 1
    return out


_ID_RE = re.compile(r'\bid\s*:\s*"([A-Za-z0-9_]+)"')
_LABEL_RE = re.compile(r'\blabel\s*:\s*"((?:[^"\\]|\\.)*)"')
_TYPE_RE = re.compile(r'\btype\s*:\s*"([A-Za-z]+)"')
_REPEAT_LABEL_RE = re.compile(r'\brepeatLabel\s*:\s*"((?:[^"\\]|\\.)*)"')


def _parse(src: str) -> Dict[str, Dict]:
    clean = _strip_comments(src)
    anchor = clean.find("var SECTIONS = [")
    if anchor == -1:
        raise SchemaUnavailable("`var SECTIONS = [` not found")
    arr_start = clean.index("[", anchor)
    arr = clean[arr_start:_match_bracket(clean, arr_start)]

    schema: Dict[str, Dict] = {}
    for obj in _split_objects(arr[1:-1]):
        sid_m = _ID_RE.search(obj)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        f_at = obj.find("fields")
        if f_at == -1:
            continue
        f_start = obj.index("[", f_at)
        fields_src = obj[f_start:_match_bracket(obj, f_start)]
        fields: Dict[str, Dict] = {}
        for fobj in _split_objects(fields_src[1:-1]):
            fid_m = _ID_RE.search(fobj)
            if not fid_m:
                continue
            lbl = _LABEL_RE.search(fobj)
            typ = _TYPE_RE.search(fobj)
            fields[fid_m.group(1)] = {
                "label": lbl.group(1) if lbl else fid_m.group(1),
                "type": typ.group(1) if typ else "text",
            }
        head = obj[:f_start]
        lbl = _LABEL_RE.search(head)
        rlbl = _REPEAT_LABEL_RE.search(head)
        schema[sid] = {
            "label": lbl.group(1) if lbl else sid,
            "repeatable": bool(re.search(r"\brepeatable\s*:\s*true", head)),
            "repeat_label": rlbl.group(1) if rlbl else "",
            "fields": fields,
        }
    return schema


def _validate(schema: Dict[str, Dict]) -> None:
    n_sec = len(schema)
    n_rep = sum(1 for s in schema.values() if s["repeatable"])
    n_fld = sum(len(s["fields"]) for s in schema.values())
    problems: List[str] = []
    if n_sec != _EXPECT_SECTIONS:
        problems.append(f"{n_sec} sections, expected {_EXPECT_SECTIONS}")
    if n_rep != _EXPECT_REPEATABLE:
        problems.append(f"{n_rep} repeatable, expected {_EXPECT_REPEATABLE}")
    # Exact, not a floor. A floor would let a parser that quietly picked
    # up extra objects pass, and inventing destinations is as harmful as
    # losing them — it is how `personal.notes` would be waved through.
    if n_fld != _EXPECT_FIELDS:
        problems.append(f"{n_fld} fields, expected {_EXPECT_FIELDS}")
    for sec, fld in _EXPECT_PRESENT:
        if sec not in schema or fld not in schema[sec]["fields"]:
            problems.append(f"missing known field {sec}.{fld}")
    for sec, fld in _EXPECT_ABSENT:
        if sec in schema and fld in schema[sec]["fields"]:
            problems.append(f"parser invented {sec}.{fld}")
    if problems:
        raise SchemaUnavailable(
            "questionnaire schema failed validation — REFUSING to validate "
            "destinations rather than guess: " + "; ".join(problems))


def load_schema(force: bool = False) -> Dict[str, Dict]:
    """Parsed schema, cached on the file's (mtime, size).

    Re-read when the file changes, so a schema edit takes effect without
    a restart — which also means a destination valid when a suggestion
    was proposed can become invalid before it is accepted. That is
    exactly why acceptance re-validates rather than trusting the flag
    recorded at proposal time.
    """
    global _cache, _cache_key
    try:
        st = os.stat(_JS_PATH)
        key = (st.st_mtime, st.st_size)
    except OSError as e:
        raise SchemaUnavailable(f"cannot stat {_JS_PATH}: {e}") from e
    with _lock:
        if not force and _cache is not None and _cache_key == key:
            return _cache
        try:
            src = open(_JS_PATH, encoding="utf-8").read()
        except OSError as e:
            raise SchemaUnavailable(f"cannot read {_JS_PATH}: {e}") from e
        schema = _parse(src)
        _validate(schema)
        _cache, _cache_key = schema, key
        return schema


# ── the questions callers actually ask ───────────────────────────────


def is_defined(section: str, field: str) -> bool:
    """Would the form render an answer at this destination?

    False means accepting it would store a value nobody can see or edit.
    A nested field path (`a.b.c` below a section) is NOT defined: the
    renderer draws one input per declared field and nothing deeper.
    """
    schema = load_schema()
    sec = schema.get(section)
    return bool(sec) and field in sec["fields"]


def is_repeatable(section: str) -> bool:
    schema = load_schema()
    sec = schema.get(section)
    return bool(sec) and sec["repeatable"]


def labels_for(section: str, field: str) -> Dict[str, str]:
    """Human labels, for messages and for the review card."""
    try:
        schema = load_schema()
    except SchemaUnavailable:
        return {"section": section, "field": field, "single": section}
    sec = schema.get(section)
    if not sec:
        return {"section": section, "field": field, "single": section}
    f = sec["fields"].get(field)
    return {
        "section": sec["label"],
        "field": f["label"] if f else field,
        "single": sec["repeat_label"] or sec["label"],
    }


def section_ids() -> List[str]:
    return sorted(load_schema().keys())


def repeatable_section_ids() -> List[str]:
    return sorted(k for k, v in load_schema().items() if v["repeatable"])


def schema_fingerprint() -> str:
    """Stable digest of section/field ids. Lets a caller notice that the
    schema moved between two moments without diffing the whole thing."""
    import hashlib
    schema = load_schema()
    flat = ";".join(
        f"{s}:{','.join(sorted(schema[s]['fields']))}" for s in sorted(schema)
    )
    return hashlib.sha256(flat.encode("utf-8")).hexdigest()[:16]
