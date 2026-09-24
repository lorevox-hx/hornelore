"""Establish a newly created narrator in the Life Record (Batch C-2R2).

WHY. A brand-new narrator had a `people` row and nothing in the Life Record,
so Questionnaire V2 — which edits the record — had no subject and could not
make the first write (the C-2 live smoke, 2026-09-24). Creating a narrator
now writes their identity floor THROUGH THE ONE WRITER, so the record exists
from the first moment and every later edit is an ordinary change.

Only what the operator actually supplied is written. Nothing is inferred:
no name is split, no date is invented, blank stays blank. The `people` row
and `profile_json` keep their copies for the consumers that still read them
(Lori, Profile Seed — Batch D moves those onto the record).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from . import writer as _writer

_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def establish_narrator(narrator_id: str, *, full_name: str,
                       preferred_name: Optional[str] = None,
                       pronouns: Optional[str] = None,
                       birth_date: Optional[str] = None,
                       birth_place: Optional[str] = None,
                       actor: str = "operator:new_narrator") -> Dict[str, Any]:
    full = (full_name or "").strip()
    if not full:
        return {"ok": False, "refused": [{"path": "", "reason": "a narrator needs a name"}]}
    changes: List[Dict[str, Any]] = [
        {"op": "add", "path": f"people/{narrator_id}/names/{narrator_id}-name",
         "value": {"fullText": full, "kind": "current"}},
    ]
    preferred_id = f"{narrator_id}-name"
    pref = (preferred_name or "").strip()
    if pref and pref != full:
        preferred_id = f"{narrator_id}-preferred"
        changes.append({"op": "add", "path": f"people/{narrator_id}/names/{preferred_id}",
                        "value": {"fullText": pref, "kind": "current", "use": "everyday"}})
    changes.append({"op": "set", "path": f"people/{narrator_id}/preferredNameRef",
                    "value": preferred_id, "expectedPrevious": None})

    def asserted(aid, stype, sid, concept, value):
        # Typed by the operator at creation: recorded AND asserted by the
        # operator. Never labelled the narrator's own words by default.
        return {"op": "add", "path": f"assertions/{aid}",
                "value": {"subjectType": stype, "subjectId": sid, "conceptId": concept, "value": value,
                          "source": "operator", "assertedBy": "operator", "status": "operator_entered"}}

    pr = (pronouns or "").strip()
    if pr:
        changes.append(asserted(f"{narrator_id}-pronouns", "person", narrator_id, "person.pronouns", pr))

    dob, pob = (birth_date or "").strip(), (birth_place or "").strip()
    if dob or pob:
        ev = f"{narrator_id}-birth"
        value: Dict[str, Any] = {"type": "birth", "participants": [{"person": narrator_id, "role": "subject"}]}
        if pob:
            changes.append({"op": "add", "path": f"places/{narrator_id}-birthplace", "value": {"label": pob}})
            value["place"] = f"{narrator_id}-birthplace"
        changes.append({"op": "add", "path": f"events/{ev}", "value": value})
        if dob:
            # the text exactly as given; an ISO day is a day, anything else
            # keeps its words and claims no precision it was not given
            changes.append(asserted(f"{narrator_id}-dob", "event", ev, "person.birth.date",
                                    {"text": dob, "value": dob if _ISO_DAY.match(dob) else None,
                                     "precision": "day" if _ISO_DAY.match(dob) else "unknown"}))
        changes.append({"op": "set", "path": f"people/{narrator_id}/birthEventRef",
                        "value": ev, "expectedPrevious": None})
    return _writer.apply_changes(narrator_id, None, changes, actor)
