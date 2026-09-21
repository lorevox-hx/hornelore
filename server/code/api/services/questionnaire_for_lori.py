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

__all__ = ["load_facts", "render_for_prompt", "detail_for", "STORY_FIELDS"]


# ── COMPACT BY DEFAULT, RETRIEVABLE ON DEMAND ───────────────────────
#
# Measured on a real record 2026-09-21: the full block for Chris is 127
# facts and 2,605 tokens, and the budget layer DROPPED it on every turn
# —
#
#     saved_biography:DROP:2605      directives_interview:keep:3918
#
# so he asked Lori about his mother while she held her name, maiden
# name, birth date, birthplace and occupation, and had been handed none
# of it. The feature worked only for narrators with almost no
# biography, which is the opposite of its purpose.
#
# The weight is not in the facts. It is in a handful of long prose
# answers:
#
#     parents.notableLifeEvents        883 chars
#     grandparents.memorableStories    808
#     grandparents.memorableStories    685
#
# Those are STORIES. Reciting them back is the thing Lori must not do
# anyway — they are material for a question. The identifying facts
# (who, when, where, what they did) cost ~900 tokens for the same
# record and are exactly what stops her asking a name she already has.
#
# So the default block carries the facts and SIGNPOSTS the stories:
# Lori is told they exist and that she can ask. `detail_for` is how a
# turn retrieves them when the narrator actually asks about that
# person. Nothing is dropped from storage, and nothing is permanently
# out of reach — the ruling was explicit on both.
STORY_FIELDS = frozenset({
    "notableLifeEvents", "memorableStories", "narrative", "notes",
    "memories", "additionalNotes", "culturalPractices", "significantEvent",
    "notableEvents", "whatHappened", "description", "story", "stories",
    "culturalBackground", "memorableStory", "reflections", "details",
    "firstMemory", "favoriteToy", "traditions",
})

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
                            # POSITION, always. 17 of 17 entries in a real
                            # record carry no `_entryId` — WO-02 introduced
                            # it and never backfilled — so grouping on the
                            # id alone collapsed a mother and a father into
                            # one person: "Kent James Horne (nee Zarr)",
                            # with her maiden name on him. Reading by
                            # position is safe here because nothing is
                            # written back; a WRITE must still refuse to
                            # infer an ordinal, which is what WO-02 is for.
                            "entry_index": i,
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

    COMPACT. Identifying facts only — see STORY_FIELDS for what is held
    back and why. The long answers are signposted, not deleted, and
    `detail_for` retrieves them when a narrator asks about that person.

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

    plain = [f for f in facts if f["field"] not in STORY_FIELDS]
    stories = [f for f in facts if f["field"] in STORY_FIELDS]
    if not plain and not stories:
        return ""

    # ONE LINE PER PERSON, NOT ONE PER FIELD.
    #
    # The first compact version still cost 1,533 tokens and left 62
    # tokens of headroom under the 8,192 limit — which is another way of
    # spelling "will be dropped again next week". Measured: only ~1,075
    # tokens were CONTENT. The rest was shape: 108 facts on their own
    # lines, with every person's name split across firstName,
    # middleName, lastName and maidenName.
    #
    # A person is one fact about one person, so they get one line:
    #
    #   Mother — Janice Josephine Horne (nee Zarr), b. 1939-09-30,
    #   Spokane, Washington — Homemaker
    #
    # which is both smaller and easier to read than four labelled
    # fragments.
    _all_unknown = all(f["origin"] == "unknown" for f in plain) if plain else True

    grouped: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    order: List[Tuple[str, str]] = []
    for f in plain:
        key = (f["section"], f["entry_id"] or f"#{f.get('entry_index', 0)}")
        if key not in grouped:
            grouped[key] = {}
            order.append(key)
        grouped[key][f["field"]] = f

    def _v(fields, *names):
        for n in names:
            if n in fields and fields[n]["value"]:
                return fields[n]["value"].strip()
        return ""

    lines: List[str] = []
    seen_section = ""
    shown = 0
    for section, _eid in order:
        if shown >= limit:
            break
        fields = grouped[(section, _eid)]
        if section != seen_section:
            lines.append(f"  {section}:")
            seen_section = section

        name = " ".join(x for x in (_v(fields, "firstName"), _v(fields, "middleName"),
                                    _v(fields, "lastName")) if x)
        maiden = _v(fields, "maidenName")
        if maiden:
            name = f"{name} (nee {maiden})" if name else f"(nee {maiden})"
        head = _v(fields, "relation", "side") or _v(fields, "name", "place",
                                                    "destination", "branch")

        bits: List[str] = []
        born = _v(fields, "birthDate", "dateOfBirth")
        where = _v(fields, "birthPlace", "placeOfBirth")
        if born or where:
            bits.append("b. " + ", ".join(x for x in (born, where) if x))
        occ = _v(fields, "occupation")
        if occ:
            bits.append(occ)

        used = {"firstName", "middleName", "lastName", "maidenName", "relation",
                "side", "name", "birthDate", "dateOfBirth", "birthPlace",
                "placeOfBirth", "occupation"}
        rest = [f"{k}: {v['value']}" for k, v in fields.items()
                if k not in used and v["value"]]

        # THE MARKER MUST NOT OVER-CLAIM EITHER WAY.
        #
        # One line now carries several fields, so a single marker has to
        # say which of them it is about. Caught by a test: a father
        # whose BIRTHPLACE was an accepted suggestion had his whole
        # entry labelled "Lori proposed this", including an occupation
        # an operator had typed. Flagging good data as machine-proposed
        # is the mirror of the laundering this file exists to prevent —
        # it is safer, but it is still false.
        marks = {v["origin"] for v in fields.values()}
        mark = ""
        if marks == {"narrator_direct"}:
            mark = "  [the narrator said this]"
        elif marks == {"ai_suggested"}:
            mark = "  [Lori proposed this; a person agreed]"
        elif "narrator_direct" in marks or "ai_suggested" in marks:
            named = sorted({k for k, v in fields.items()
                            if v["origin"] in ("narrator_direct", "ai_suggested")})
            said = [k for k in named if fields[k]["origin"] == "narrator_direct"]
            prop = [k for k in named if fields[k]["origin"] == "ai_suggested"]
            bits = []
            if said:
                bits.append("narrator said: " + ", ".join(said))
            if prop:
                bits.append("Lori proposed, agreed: " + ", ".join(prop))
            mark = "  [" + "; ".join(bits) + "]"
        elif not _all_unknown and marks == {"unknown"}:
            mark = "  [origin not recorded]"

        label = " — ".join(x for x in (head, name) if x) or section
        tail = " — ".join(bits + rest)
        lines.append(f"    {label}{(' — ' + tail) if tail else ''}{mark}")
        shown += 1

    if shown >= limit:
        lines.append(f"    ... and more; {shown} of {len(order)} entries shown.")

    # THE STORIES ARE NAMED, NOT CARRIED.
    #
    # Without this Lori would have the facts and no idea anything else
    # exists, and would ask for something already on record as though it
    # had never been said. She is told WHO has longer material and that
    # asking will retrieve it — `detail_for` does the retrieving when
    # the narrator's own message names that person.
    if stories:
        who: Dict[str, int] = {}
        for f in stories:
            k = f.get("entry_label") or f["section"]
            who[k] = who.get(k, 0) + 1
        lines.append("  LONGER MATERIAL ON RECORD (ask and it is retrieved): "
                     + "; ".join(f"{k} ({n})" for k, n in list(who.items())[:20]))

    _header = "THE NARRATOR'S SAVED BIOGRAPHY — entered in Bio Builder, on record."
    if _all_unknown:
        _header += ("\n  (Entered before per-answer origins were recorded; all of "
                    "it came from the form, none of it is a narrator statement.)")

    _conflict_block = _render_conflicts(find_conflicts(facts, competing))

    return (
        _header + "\n"
        + "\n".join(lines) + "\n"
        + _conflict_block
        + "\nHOW TO USE THIS:\n"
        "  - You KNOW these. Never ask for something on this list.\n"
        "  - You may ASK ABOUT them; knowing a fact is not having heard the story.\n"
        "  - NEVER say or imply the narrator told you any of it, unless the line "
        "says [the narrator said this]. Most of this was typed into a form, often "
        "by someone else in the family.\n"
        "  - A fact about a parent is not a fact about the narrator.\n"
    )


# ── RETRIEVAL ───────────────────────────────────────────────────────


def detail_for(facts: List[Dict[str, Any]], user_text: str,
               *, max_chars: int = 1800) -> str:
    """The longer answers about whoever the narrator just asked about.

    The default block carries facts and signposts the stories. This is
    the other half of that bargain, and the ruling was explicit about
    why it has to exist:

        Do not discard the longer stories from storage or make them
        permanently inaccessible to Lori. They can be omitted from the
        default prompt, but a question about a particular person or
        story must still have a way to retrieve the relevant detail.

    Matching is on the NAMES the narrator used. "what can you tell me
    about my mom" matches the entry labelled "Mother Janice Horne";
    "tell me about grandpa Peter" matches by the name. A turn that names
    nobody retrieves nothing, which is what keeps the default prompt
    small.

    Returns "" when nothing matches. Capped, because a retrieval that
    itself gets dropped for size would have solved nothing.
    """
    stories = [f for f in facts if f["field"] in STORY_FIELDS and f["value"]]
    if not stories or not (user_text or "").strip():
        return ""

    text = " " + " ".join(str(user_text).lower().split()) + " "

    # Relationship words the narrator is likely to use, mapped to what
    # the questionnaire calls them. "mom" is not a value in any field.
    RELATION_WORDS = {
        "mom": "mother", "mum": "mother", "mother": "mother", "ma": "mother",
        "dad": "father", "father": "father", "pa": "father",
        "grandma": "grandmother", "grandmother": "grandmother",
        "grandpa": "grandfather", "grandfather": "grandfather",
        "granny": "grandmother", "nana": "grandmother",
        "brother": "brother", "sister": "sister", "sibling": "sibling",
        "wife": "spouse", "husband": "spouse", "spouse": "spouse",
        "son": "son", "daughter": "daughter", "child": "child",
        "parents": "parent", "grandparents": "grandparent",
    }
    wanted = {v for k, v in RELATION_WORDS.items() if f" {k} " in text}

    hits: List[Dict[str, Any]] = []
    for f in stories:
        label = (f.get("entry_label") or "").lower()
        section = f["section"].lower()
        # A name the narrator typed, e.g. "Janice" or "Peter".
        named = any(len(w) > 2 and f" {w} " in text
                    for w in label.replace("·", " ").split())
        related = any(rel in label or rel in section
                      or (rel in ("parent", "grandparent") and section.startswith(rel))
                      for rel in wanted)
        if named or related:
            hits.append(f)

    if not hits:
        return ""

    out: List[str] = [
        "WHAT IS ON RECORD ABOUT THE PERSON THEY JUST ASKED ABOUT",
        "  Retrieved because their message named them. Same rule as the "
        "biography above: you KNOW this, you did not HEAR it. Do not say "
        "they told you, and do not read it back as a speech — use it to ask "
        "a better question.",
    ]
    used = 0
    for f in hits:
        who = f.get("entry_label") or f["section"]
        val = f["value"]
        if used + len(val) > max_chars:
            val = val[: max(0, max_chars - used)].rstrip() + " …"
        out.append(f"  {who} — {f['field']}:")
        out.append(f"    {val}")
        used += len(val)
        if used >= max_chars:
            out.append("  (more on record; ask about a specific person or year.)")
            break
    return "\n".join(out) + "\n"
