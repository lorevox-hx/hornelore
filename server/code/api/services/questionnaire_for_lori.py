"""The saved biography, shaped for Lori's prompt. Read-only.

WO-QUESTIONNAIRE-REACHES-LORI-01.

THE FINDING THIS ANSWERS
------------------------
An operator saves `parents[1].occupation = "ore dock foreman"`. It is
durably stored, versioned, audited and recoverable — and Lori cannot see
it. `prompt_composer` assembles her prompt from `profiles.profile_json`,
`interview_projections`, the `people` row, the client runtime payload
and transcripts. It never reads `bio_builder_questionnaires`. Verified
again 2026-09-20: zero references.

WHY A READ PATH AND NOT THE FAN-OUT
------------------------------------
The WO names a second break: turning `HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE`
on would not carry the fact anyway. `_apply_parents` writes three keys —
father_name, mother_name, mother_maiden_name — and an occupation is not
among them. Confirmed still true.

And the fan-out's carrier is dangerous. `db.update_profile_json` merges
at the TOP LEVEL:

    merged.update(profile_json or {})        # db.py:2977

so a patch containing `parents` REPLACES the whole parents array. That is
the shape of BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01 — a partial view
written back over a fuller record — aimed at `profile_json` instead of
the questionnaire. Two days went into removing that behaviour from one
table.

So nothing is copied. The questionnaire is READ where the prompt is
built. No fifth store, no schema change, no second version of a fact to
drift, and `update_profile_json` is not involved at all.

WHEN TWO STORES DISAGREE — NEITHER SILENTLY WINS
-------------------------------------------------
The first version of this module said "the questionnaire wins". That is
the wrong rule, and the ruling that corrected it is the better one:

    define conflict handling using provenance and confirmation status,
    not store location alone. Preserve conflicting values and their
    sources; do not silently replace one with another.

Store location is an accident of which screen somebody used. Provenance
is a claim about how a fact came to be believed, and it is what should
decide — or, where it cannot decide, what should be shown.

So a disagreement is RENDERED, not resolved. Both values reach the
prompt with their origins, and Lori is told to ask rather than choose.

NO EVIDENCE HIERARCHY. An earlier version of this module ranked the
origins and told Lori which value was "better evidence" — a narrator's
own statement over a form entry about them. That was wrong, and wrong in
a way worth naming, because it is easy to talk oneself into:

    Provenance tells Lori WHO SUPPLIED a value, not which value is
    correct.

A narrator can misremember their mother's birthplace; an operator can
have the certificate in front of them. Neither origin predicts truth.
The origins are shown because they are useful context for the question
Lori asks next — not as a ranking she should resolve the disagreement
with. There is no tie-break here, and there should not be one.

Nothing is overwritten in either store. This module only reads.

PROVENANCE SURVIVES THE HOP
---------------------------
Every fact carries its origin, read from `bio_builder_answer_provenance`
and keyed the same way the write path keys it — (section, entry_id,
field). An operator-entered answer and an accepted AI suggestion stay
distinguishable at the point Lori reads them. A fact with no provenance
row predates WO-03A and says so rather than claiming to be operator
truth.

FACTS ARE NOT RECOLLECTIONS
---------------------------
Knowing Bertil was an ore dock foreman must let Lori ASK about it. It
must not let her narrate it as Thorvald's memory. That distinction is
made in `render_for_prompt`, at the point the facts are injected, not
here in the data.

NARRATOR ISOLATION
------------------
Every query is `WHERE person_id = ?`. There is no path through this
module that reads another narrator's row.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["load_facts", "render_for_prompt"]

# Sections whose entries describe a PERSON other than the narrator.
# Named so the renderer can say "your father" rather than listing a bare
# path, and so a fact about a relative is never phrased as a fact about
# the narrator.
_PEOPLE_SECTIONS = {
    "parents": "parent",
    "grandparents": "grandparent",
    "siblings": "sibling",
    "children": "child",
    "spouse": "spouse",
    "pets": "pet",
}

# Fields that identify an entry rather than saying something about it.
# Used to build a label, not repeated as facts of their own.
_LABEL_FIELDS = ("relation", "firstName", "preferredName", "lastName",
                 "name", "branch", "place", "destination", "side")

# Bookkeeping that is not biography.
_SKIP_FIELDS = {"_entryId", "deceased"}


def _label(entry: Dict[str, Any], kind: str, index: int) -> str:
    parts = [str(entry.get(f)).strip() for f in _LABEL_FIELDS
             if entry.get(f) and str(entry.get(f)).strip()]
    if parts:
        return " ".join(parts[:3])
    return f"{kind} {index + 1}"


def load_facts(person_id: str, *, con=None) -> List[Dict[str, Any]]:
    """Every populated questionnaire answer, with its provenance.

    Returns a list of dicts: section, entry_id, entry_label, field,
    value, origin. Empty on any failure — this runs in the chat path and
    must never raise into it. A missing biography is a quiet absence,
    not an error, because most narrators start with one.
    """
    if not person_id:
        return []
    own = con is None
    try:
        if own:
            from .. import db as _db
            con = _db._connect()
        row = con.execute(
            "SELECT questionnaire_json FROM bio_builder_questionnaires "
            "WHERE person_id = ?", (person_id,)).fetchone()
        if not row:
            return []
        doc = json.loads(row["questionnaire_json"] or "{}") or {}

        prov: Dict[Tuple[str, str, str], str] = {}
        try:
            for p in con.execute(
                    "SELECT section, entry_id, field, origin "
                    "FROM bio_builder_answer_provenance WHERE person_id = ?",
                    (person_id,)):
                prov[(p["section"], p["entry_id"] or "", p["field"])] = p["origin"]
        except Exception:
            # Provenance is additive. Without it every fact reads as
            # `unknown`, which is honest; refusing to show the biography
            # because its origins are unreadable would be worse.
            logger.warning("[questionnaire-for-lori] provenance unreadable for %s",
                           (person_id or "")[:8])

        out: List[Dict[str, Any]] = []
        for section, val in (doc.items() if isinstance(doc, dict) else []):
            if isinstance(val, dict):
                for field, v in val.items():
                    if field in _SKIP_FIELDS or not _is_value(v):
                        continue
                    out.append({
                        "section": section, "entry_id": "", "entry_label": "",
                        "field": field, "value": str(v).strip(),
                        "origin": prov.get((section, "", field), "unknown"),
                    })
            elif isinstance(val, list):
                kind = _PEOPLE_SECTIONS.get(section, section)
                for i, entry in enumerate(val):
                    if not isinstance(entry, dict):
                        continue
                    eid = str(entry.get("_entryId") or "")
                    label = _label(entry, kind, i)
                    for field, v in entry.items():
                        if field in _SKIP_FIELDS or not _is_value(v):
                            continue
                        out.append({
                            "section": section, "entry_id": eid,
                            "entry_label": label, "field": field,
                            "value": str(v).strip(),
                            "origin": prov.get((section, eid, field), "unknown"),
                        })
        return out
    except Exception as exc:
        logger.warning("[questionnaire-for-lori] read failed for %s: %s",
                       (person_id or "")[:8], exc)
        return []
    finally:
        if own and con is not None:
            try:
                con.close()
            except Exception:
                pass


def _is_value(v: Any) -> bool:
    return isinstance(v, (str, int, float)) and str(v).strip() != ""


def find_conflicts(facts: List[Dict[str, Any]],
                   competing: Optional[Dict[str, Tuple[str, str]]] = None
                   ) -> List[Dict[str, Any]]:
    """Where the biography and another store disagree about one fact.

    `competing` maps "section.field" to (value, origin) from elsewhere —
    the seed buckets built from `profile_json` and
    `interview_projections`. Comparison is case- and space-insensitive,
    so "Marrow Bay" and "marrow bay " are not a disagreement.

    Returns one row per genuine disagreement, carrying BOTH values and
    BOTH origins. Nothing is dropped, chosen, or RANKED here — see "NO
    EVIDENCE HIERARCHY" in the module docstring for why there is no
    tie-break field.
    """
    if not competing:
        return []
    out: List[Dict[str, Any]] = []
    for f in facts:
        key = f"{f['section']}.{f['field']}"
        other = competing.get(key)
        if not other:
            continue
        other_value, other_origin = other
        if not str(other_value or "").strip():
            continue
        if _same(f["value"], other_value):
            continue
        out.append({
            "field": key,
            "entry_label": f.get("entry_label") or "",
            "questionnaire_value": f["value"],
            "questionnaire_origin": f["origin"],
            "other_value": str(other_value).strip(),
            "other_origin": other_origin or "unknown",
        })
    return out


def _same(a: Any, b: Any) -> bool:
    return " ".join(str(a or "").split()).casefold() == \
           " ".join(str(b or "").split()).casefold()


def _render_conflicts(conflicts: List[Dict[str, Any]]) -> str:
    if not conflicts:
        return ""
    _say = {
        "narrator_direct": "the narrator said this",
        "operator_direct": "typed into the form",
        "ai_suggested": "Lori proposed it, a person agreed",
        "unknown": "from the form, origin not recorded",
    }
    out = ["\nTWO RECORDS DISAGREE — DO NOT PICK ONE SILENTLY:"]
    for c in conflicts:
        where = f" ({c['entry_label']})" if c["entry_label"] else ""
        out.append(f"  {c['field']}{where}")
        out.append(f"      biography says: {c['questionnaire_value']}  "
                   f"[{_say.get(c['questionnaire_origin'], 'origin not recorded')}]")
        out.append(f"      elsewhere says: {c['other_value']}  "
                   f"[{_say.get(c['other_origin'], 'origin not recorded')}]")
    out.append("  The origins say who supplied each value. They do NOT say which "
               "is correct — a narrator can misremember, and a form entry may "
               "have come from a document.")
    out.append("  Say what you have and ask which is right. NEVER state one of "
               "these as settled, never rank them for the narrator, and never "
               "quietly drop the other.")
    return "\n".join(out) + "\n"


def render_for_prompt(facts: List[Dict[str, Any]], *, limit: int = 120,
                      competing: Optional[Dict[str, Tuple[str, str]]] = None) -> str:
    """The block Lori is given, and the rule that governs it.

    Two things this must get right, and they are the whole reason the
    text is built here rather than assembled ad hoc at the call site.

    FACTS ARE NOT RECOLLECTIONS. Lori may ASK about the ore dock. She
    may not narrate it as the narrator's memory, or imply she was told.
    Someone reading their own life back must not find a record saying
    they said something they never said.

    ORIGIN IS SHOWN, NOT AVERAGED. An operator typed most of this. Some
    of it Lori proposed and a person accepted — weaker, and it is
    labelled so. Anything predating the provenance work says `unknown`
    rather than borrowing the authority of the rest.
    """
    if not facts:
        return ""

    _all_unknown = all(f["origin"] == "unknown" for f in facts)

    lines: List[str] = []
    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for f in facts:
        by_section.setdefault(f["section"], []).append(f)

    shown = 0
    for section, items in by_section.items():
        if shown >= limit:
            break
        entries: Dict[str, List[Dict[str, Any]]] = {}
        for f in items:
            entries.setdefault(f.get("entry_label") or "", []).append(f)
        lines.append(f"  {section}:")
        for label, fields in entries.items():
            if shown >= limit:
                break
            if label:
                lines.append(f"    {label}:")
            for f in fields:
                if shown >= limit:
                    break
                # MARK THE EXCEPTIONS, NOT THE RULE — except when
                # "unknown" IS the exception.
                #
                # Everything here was typed into Bio Builder, so
                # `operator_direct` is the default and needs no label.
                # When EVERY line is `unknown` the header says so once,
                # because a marker on every line is a marker nobody
                # reads.
                #
                # But in a MIXED biography an unmarked line would read as
                # operator-entered, and an unreviewed legacy entry must
                # stay visibly origin-unknown. So when some origins are
                # recorded and some are not, the unrecorded ones are
                # marked individually.
                mark = {
                    "narrator_direct": "  [the narrator said this]",
                    "ai_suggested": "  [Lori proposed this; a person agreed]",
                }.get(f["origin"], "")
                if f["origin"] == "unknown" and not _all_unknown:
                    mark = "  [origin not recorded — entered before origins were kept]"
                indent = "      " if label else "    "
                lines.append(f"{indent}{f['field']}: {f['value']}{mark}")
                shown += 1

    if shown >= limit:
        lines.append(f"    … and more; {shown} of {len(facts)} shown.")

    _header = "THE NARRATOR'S SAVED BIOGRAPHY — entered in Bio Builder, on record."
    if _all_unknown:
        _header += ("\n  (Entered before per-answer origins were recorded, so "
                    "individual lines below are unmarked; all of it came from "
                    "the form. None of it is a narrator statement.)")

    _conflict_block = _render_conflicts(find_conflicts(facts, competing))

    return (
        _header + "\n"
        + "\n".join(lines) + "\n"
        + _conflict_block
        + "\nHOW TO USE THIS, AND HOW NOT TO:\n"
        "  - You KNOW these things. Do not ask a question this already answers, "
        "and do not ask the narrator to repeat something on this list.\n"
        "  - You may ASK ABOUT them — 'what was it like on the ore docks?' — "
        "because knowing a fact is not the same as having heard the story.\n"
        "  - NEVER narrate one of these as the narrator's own memory, and never "
        "say or imply they told you, unless a line is marked "
        "[the narrator said this]. Most of this was typed into a form, often "
        "by somebody else in the family.\n"
        "  - A line marked [Lori proposed this; a person agreed] is weaker than "
        "the rest. Treat it as probably right, not as something they said.\n"
        "  - These are facts about the people named. A fact about a parent is "
        "not a fact about the narrator.\n"
    )
