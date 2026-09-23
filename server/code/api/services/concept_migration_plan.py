"""Legacy-store migration PLAN. WO-HORNELORE-INTEGRATED-LIFE-RECORD-01, Batch A5.

Given a legacy questionnaire document and/or a profile_json document, account
for EVERY leaf exactly once against the concept catalog:

    mapped                 → a concept and a subject; Batch B writes it
    derived_not_migrated   → the catalog computes this (zodiac); the stored
                             copy is NOT carried forward as truth
    retired_value_kept     → a decision retired the path; the VALUE is kept in
                             the ledger, because retiring a field is not
                             permission to lose what someone typed into it
    unmapped_value_kept    → nothing binds this key; kept verbatim for review
    empty                  → no value (blank, null, empty list)
    bookkeeping            → `_entryId` and other `_`-prefixed markers; the
                             entry id is carried on every row of its entry

The invariant, tested: rows == leaves. Nothing is dropped, and nothing is
counted twice.

WHAT THIS IS NOT. It does not write, and it does not transform values. The
`deceased: "Yes"` → three-state life status conversion, date parsing into
text/value/precision, and person identity are Batch B's writer. Rows that
need a value transformation say so in `note`.

LAW 3: standard library + the catalog loader. No DB, no IO beyond the catalog.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import concept_catalog as _cc

DISPOSITIONS = ("mapped", "derived_not_migrated", "retired_value_kept",
                "unmapped_value_kept", "empty", "bookkeeping")

_NEEDS_TRANSFORM = {
    "person.life_status": "value normalisation owed (Batch B): Yes/No/blank → "
                          "deceased/explicitly_living/unknown; blank is NOT 'living'",
    "person.birth.date": "date normalisation owed (Batch B): keep original text; "
                         "precision from the text, never invented",
    "person.death.date": "date normalisation owed (Batch B): as birth date",
}


def _is_empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _row(store, path, value, disposition, *, concept=None, subject=None,
         subject_detail=None, entry_id=None, entry_index=None,
         decision_ids=(), note=None) -> Dict[str, Any]:
    return {"store": store, "source_path": path, "value": value,
            "disposition": disposition, "concept_id": concept, "subject": subject,
            "subject_detail": subject_detail, "entry_id": entry_id,
            "entry_index": entry_index, "decision_ids": list(decision_ids),
            "note": note}


def _classify_path(cat, store, path, value, **kw) -> Dict[str, Any]:
    if _is_empty(value):
        return _row(store, path, value, "empty", **kw)
    b = cat.binding(path)
    if b is None:
        return _row(store, path, value, "unmapped_value_kept",
                    note="no catalog binding — review before any migration", **kw)
    if b["disposition"] == "retired":
        return _row(store, path, value, "retired_value_kept",
                    decision_ids=b["decision_ids"], subject=b["subject"],
                    note="path retired by decision; value preserved in the ledger", **kw)
    if b["disposition"] == "derived":
        return _row(store, path, value, "derived_not_migrated", concept=b["concept_id"],
                    subject=b["subject"], decision_ids=b["decision_ids"],
                    note="computed by the catalog; the stored copy is not carried forward", **kw)
    return _row(store, path, value, "mapped", concept=b["concept_id"], subject=b["subject"],
                decision_ids=b["decision_ids"], note=_NEEDS_TRANSFORM.get(b["concept_id"]), **kw)


def _count_leaves(doc: Any) -> int:
    if isinstance(doc, dict):
        return sum(_count_leaves(v) if isinstance(v, (dict, list)) and v else 1
                   for v in doc.values()) if doc else 0
    if isinstance(doc, list):
        return sum(_count_leaves(v) if isinstance(v, dict) else 1 for v in doc)
    return 1


def plan_questionnaire(doc: Dict[str, Any], cat=None) -> List[Dict[str, Any]]:
    """`doc` is the stored questionnaire: {section: {field: v}} or, for a
    repeatable section, {section: [{field: v, _entryId: ...}, ...]}."""
    cat = cat or _cc.load()
    rows: List[Dict[str, Any]] = []
    for section in sorted(doc or {}):
        body = doc[section]
        if section.startswith("_"):
            rows.append(_row("questionnaire", section, body, "bookkeeping",
                             note="document-level marker, not biography"))
            continue
        if isinstance(body, list):
            for i, entry in enumerate(body):
                if not isinstance(entry, dict):
                    rows.append(_classify_path(cat, "questionnaire", f"{section}[{i}]",
                                               entry, entry_index=i))
                    continue
                eid = entry.get("_entryId")
                for field in sorted(entry):
                    v = entry[field]
                    if field.startswith("_"):
                        rows.append(_row("questionnaire", f"{section}[{i}].{field}", v,
                                         "bookkeeping", entry_id=eid, entry_index=i))
                        continue
                    rows.append(_classify_path(cat, "questionnaire", f"{section}.{field}", v,
                                               entry_id=eid, entry_index=i))
        elif isinstance(body, dict):
            for field in sorted(body):
                v = body[field]
                if field.startswith("_"):
                    rows.append(_row("questionnaire", f"{section}.{field}", v, "bookkeeping"))
                    continue
                rows.append(_classify_path(cat, "questionnaire", f"{section}.{field}", v))
        else:
            rows.append(_classify_path(cat, "questionnaire", section, body))
    return rows


def _classify_profile(cat, key, value, **kw) -> Dict[str, Any]:
    if _is_empty(value):
        return _row("profile_json", key, value, "empty", **kw)
    b = cat.profile_binding(key)
    if b is None:
        return _row("profile_json", key, value, "unmapped_value_kept",
                    note="no catalog binding — review before any migration", **kw)
    return _row("profile_json", key, value, "mapped", concept=b["concept_id"],
                subject=b["subject"], note=_NEEDS_TRANSFORM.get(b["concept_id"]), **kw)


def plan_profile(profile: Dict[str, Any], cat=None) -> List[Dict[str, Any]]:
    """`profile` is profile_json: basics{}, kinship[], pets[], and whatever
    else a writer put there — anything unrecognised is kept, not dropped."""
    cat = cat or _cc.load()
    rows: List[Dict[str, Any]] = []
    for top in sorted(profile or {}):
        body = profile[top]
        if isinstance(body, dict):
            for k in sorted(body):
                rows.append(_classify_profile(cat, f"{top}.{k}", body[k]))
        elif isinstance(body, list):
            for i, entry in enumerate(body):
                if not isinstance(entry, dict):
                    rows.append(_classify_profile(cat, f"{top}[{i}]", entry, entry_index=i))
                    continue
                relation = entry.get("relation")
                for k in sorted(entry):
                    rows.append(_classify_profile(
                        cat, f"{top}.{k}", entry[k], entry_index=i,
                        subject_detail=relation if top == "kinship" else None))
        else:
            rows.append(_classify_profile(cat, top, body))
    return rows


def plan(questionnaire: Optional[Dict[str, Any]] = None,
         profile: Optional[Dict[str, Any]] = None, cat=None) -> Dict[str, Any]:
    cat = cat or _cc.load()
    rows = []
    leaves = 0
    if questionnaire is not None:
        rows += plan_questionnaire(questionnaire, cat)
        leaves += _count_leaves(questionnaire)
    if profile is not None:
        rows += plan_profile(profile, cat)
        leaves += _count_leaves(profile)
    summary = {d: sum(r["disposition"] == d for r in rows) for d in DISPOSITIONS}
    return {"catalog_version": cat.version, "leaves": leaves, "rows": rows,
            "summary": summary, "reconciled": leaves == len(rows)}
