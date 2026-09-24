from __future__ import annotations

"""Relationships Router — LoreVox Phase Q.1 (Relationship Graph Layer)

Relationship graph API. The graph is a PROJECTION of the Life Record
(services/life_record/graph_projection.py), not a truth model: rows written by
the projection are refused here, and a full PUT needs the revision it read
(Batch B-4). Until Batch C-3 the earlier Family Tree draft still reads it.
(This docstring called it the "canonical" graph and "the truth model" until
Batch C-2b, 2026-09-24.)

Endpoints:
- GET    /api/graph/{narrator_id}                — full graph (persons + relationships)
- PUT    /api/graph/{narrator_id}                — replace full graph (atomic)
- POST   /api/graph/{narrator_id}/person         — upsert one person node
- DELETE /api/graph/person/{person_id}            — delete a person node
- POST   /api/graph/{narrator_id}/relationship   — upsert one relationship edge
- DELETE /api/graph/relationship/{rel_id}         — delete a relationship edge
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import (
    GraphRevisionConflict,
    GraphWriteRefused,
    get_person,
    graph_delete_person,
    graph_delete_relationship,
    graph_get_full,
    graph_list_persons,
    graph_list_relationships,
    graph_replace_full,
    graph_upsert_person,
    graph_upsert_relationship,
)

router = APIRouter(prefix="/api/graph", tags=["relationship-graph"])


# ── Models ──

class GraphPersonUpsert(BaseModel):
    id: Optional[str] = None
    display_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    maiden_name: str = ""
    birth_date: str = ""
    birth_place: str = ""
    occupation: str = ""
    deceased: bool = False
    is_narrator: bool = False
    source: str = "manual"
    provenance: str = ""
    confidence: float = 1.0
    meta: Dict[str, Any] = Field(default_factory=dict)


class GraphRelUpsert(BaseModel):
    id: Optional[str] = None
    from_person_id: str = ""
    to_person_id: str = ""
    relationship_type: str = ""
    subtype: str = ""
    label: str = ""
    status: str = "active"
    notes: str = ""
    source: str = "manual"
    provenance: str = ""
    confidence: float = 1.0
    start_date: str = ""
    end_date: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)


class GraphReplaceFull(BaseModel):
    persons: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    # Batch B-4: the revision the client hydrated from (GET returns it).
    # Required — a full replacement from an unknown baseline is refused.
    revision: Optional[int] = None


def _refused(e: GraphWriteRefused):
    raise HTTPException(status_code=422, detail=str(e))


# ── Endpoints ──

@router.get("/{narrator_id}", summary="Get full relationship graph")
def api_graph_get(narrator_id: str):
    if not get_person(narrator_id):
        raise HTTPException(status_code=404, detail="Narrator not found")
    return graph_get_full(narrator_id)


@router.put("/{narrator_id}", summary="Replace full relationship graph (atomic)")
def api_graph_replace(narrator_id: str, body: GraphReplaceFull):
    if not get_person(narrator_id):
        raise HTTPException(status_code=404, detail="Narrator not found")
    if body.revision is None:
        raise HTTPException(status_code=428, detail="A full graph replacement must carry the "
                            "revision it was read at (GET /api/graph/{narrator_id} returns it).")
    try:
        return graph_replace_full(narrator_id, body.persons, body.relationships,
                                  expected_revision=body.revision)
    except GraphRevisionConflict as e:
        raise HTTPException(status_code=409, detail={
            "reason": "the family graph changed since it was read; re-read it and re-apply",
            "revision": e.current, "baseRevision": e.expected})
    except GraphWriteRefused as e:
        _refused(e)


@router.post("/{narrator_id}/person", summary="Upsert a person node")
def api_graph_upsert_person(narrator_id: str, body: GraphPersonUpsert):
    if not get_person(narrator_id):
        raise HTTPException(status_code=404, detail="Narrator not found")
    try:
        return _upsert_person(narrator_id, body)
    except GraphWriteRefused as e:
        _refused(e)


def _upsert_person(narrator_id: str, body: GraphPersonUpsert):
    return graph_upsert_person(
        narrator_id=narrator_id,
        person_id=body.id,
        display_name=body.display_name,
        first_name=body.first_name,
        middle_name=body.middle_name,
        last_name=body.last_name,
        maiden_name=body.maiden_name,
        birth_date=body.birth_date,
        birth_place=body.birth_place,
        occupation=body.occupation,
        deceased=body.deceased,
        is_narrator=body.is_narrator,
        source=body.source,
        provenance=body.provenance,
        confidence=body.confidence,
        meta=body.meta,
    )


@router.delete("/person/{person_id}", summary="Delete a person node")
def api_graph_delete_person(person_id: str):
    try:
        deleted = graph_delete_person(person_id)
    except GraphWriteRefused as e:
        _refused(e)
    if not deleted:
        raise HTTPException(status_code=404, detail="Person node not found")
    return {"ok": True}


@router.post("/{narrator_id}/relationship", summary="Upsert a relationship edge")
def api_graph_upsert_rel(narrator_id: str, body: GraphRelUpsert):
    if not get_person(narrator_id):
        raise HTTPException(status_code=404, detail="Narrator not found")
    try:
        return _upsert_rel(narrator_id, body)
    except GraphWriteRefused as e:
        _refused(e)


def _upsert_rel(narrator_id: str, body: GraphRelUpsert):
    return graph_upsert_relationship(
        narrator_id=narrator_id,
        rel_id=body.id,
        from_person_id=body.from_person_id,
        to_person_id=body.to_person_id,
        relationship_type=body.relationship_type,
        subtype=body.subtype,
        label=body.label,
        status=body.status,
        notes=body.notes,
        source=body.source,
        provenance=body.provenance,
        confidence=body.confidence,
        start_date=body.start_date,
        end_date=body.end_date,
        meta=body.meta,
    )


@router.delete("/relationship/{rel_id}", summary="Delete a relationship edge")
def api_graph_delete_rel(rel_id: str):
    try:
        deleted = graph_delete_relationship(rel_id)
    except GraphWriteRefused as e:
        _refused(e)
    if not deleted:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return {"ok": True}
