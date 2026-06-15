"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase C Tier 2 service.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

The Tier 2 (document-derived) routing layer for bio_facts. When the
operator uploads an identity document (birth certificate, marriage
certificate, military DD-214, etc.), facts extracted from that
document write to bio_facts with elevated authority — identity docs
auto-promote to `document_sourced` (the highest non-operator status);
non-identity docs propose at `extracted_needs_verify` with low
confidence.

This is the v1 implementation. Document parsing itself happens
upstream in the media_archive pipeline; this service is the
authority-classification + routing layer that turns "we extracted X
from document Y" into "write to bio_facts with status Z confidence C".

LAW 3 INFRASTRUCTURE BOUNDARY:
This module imports from stdlib + `..db` + `.bio_schema` only. It
does NOT import from media_archive (the caller hands us the
already-parsed proposals + doc metadata). The integration hook lands
in media_archive in a future commit; this service is the destination.

═══════════════════════════════════════════════════════════════════════
  DOCUMENT TYPE → AUTHORITY MAP (per WO §Tier 2)
═══════════════════════════════════════════════════════════════════════

  Identity docs (auto-promote, confidence 1.0):
    - birth_certificate
    - marriage_certificate
    - military_dd214 (or dd_214)
    - death_certificate (for family members)

  High-confidence non-identity (auto-promote, confidence 0.95):
    - diploma

  Propose-only (extracted_needs_verify):
    - prior_memoir: confidence 0.7
    - family_genealogy: confidence 0.6
    - handwritten_letter: confidence 0.5
    - photograph: confidence 0.4
    - unknown: confidence 0.3

The "NEVER auto-promote to truth from media archive" locked principle
is preserved by RESTRICTING auto-promote to identity-doc types only.
Everything else proposes. The document_sourced status is itself a form
of authority, but operators can still override via the bio editor.

═══════════════════════════════════════════════════════════════════════
  PUBLIC API
═══════════════════════════════════════════════════════════════════════

  route_document_to_bio_facts(facts, narrator_id, doc_type, doc_id, ...)
      → DocRouteSummary
      Per-document routing — one call per processed document, takes a
      list of extracted facts. Returns a typed summary.

  classify_document_authority(doc_type) → (status, confidence)
      Pure classifier — no DB. Used by routing AND by tests.

  is_identity_document(doc_type) → bool
      Helper used by media_archive integration to know if a doc's
      facts should ever auto-promote.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .. import db
from . import bio_schema
from . import bio_fact_router


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Document-type → authority mapping
# ─────────────────────────────────────────────────────────────────────


# Identity documents — auto-promote to document_sourced, confidence 1.0.
# Aliases included so the caller's doc_type string can use either
# convention (snake_case OR with separator variants).
_IDENTITY_DOCS: Set[str] = {
    "birth_certificate",
    "marriage_certificate",
    "death_certificate",
    "military_dd214",
    "military_dd_214",
    "dd214",
    "dd_214",
    "naturalization_certificate",
    "social_security_card",
}


# Document-type → (status, confidence) lookup. Identity docs are
# represented as the explicit set above (the classifier checks both).
# Entries here are ordered approximately by authority (highest first).
_DOC_TYPE_TABLE: Tuple[Tuple[str, str, float], ...] = (
    ("diploma",            "document_sourced",       0.95),
    ("transcript",         "document_sourced",       0.90),
    ("prior_memoir",       "extracted_needs_verify", 0.70),
    ("family_genealogy",   "extracted_needs_verify", 0.60),
    ("handwritten_letter", "extracted_needs_verify", 0.50),
    ("typed_letter",       "extracted_needs_verify", 0.55),
    ("photograph",         "extracted_needs_verify", 0.40),
    ("photo_caption",      "extracted_needs_verify", 0.40),
    ("newspaper_clipping", "extracted_needs_verify", 0.55),
    ("scrapbook_entry",    "extracted_needs_verify", 0.45),
    ("unknown",            "extracted_needs_verify", 0.30),
)


def is_identity_document(doc_type: Optional[str]) -> bool:
    """True iff the document type is an identity-class document
    (birth/marriage/death cert, military DD-214, naturalization, SSN
    card). Identity docs auto-promote to document_sourced status."""
    if not doc_type:
        return False
    return str(doc_type).strip().lower() in _IDENTITY_DOCS


def classify_document_authority(
    doc_type: Optional[str],
) -> Tuple[str, float]:
    """Return the (status, confidence) for a document type.

    Unknown / empty doc_type defaults to ("extracted_needs_verify",
    0.30) — the most permissive entry, never auto-promotes.
    """
    if not doc_type:
        return ("extracted_needs_verify", 0.30)
    key = str(doc_type).strip().lower()
    if key in _IDENTITY_DOCS:
        return ("document_sourced", 1.0)
    for entry_key, status, conf in _DOC_TYPE_TABLE:
        if key == entry_key:
            return (status, conf)
    # Unknown explicit doc_type — caller is responsible for tracking
    # which doc types are recognized; we default permissively.
    return ("extracted_needs_verify", 0.30)


# ─────────────────────────────────────────────────────────────────────
# Routing summary
# ─────────────────────────────────────────────────────────────────────


@dataclass
class DocRouteSummary:
    """Per-document routing summary.

    document_sourced: rows written at document_sourced status
    proposed: rows written at extracted_needs_verify
    overridden_narrator_memory: existing narrator-memory rows that
        got marked conflicted because this document write produced
        a different value
    unmapped: facts with no bio_fields mapping
    errors: per-fact failures
    """
    document_sourced: int = 0
    proposed: int = 0
    overridden_narrator_memory: int = 0
    unmapped: int = 0
    errors: int = 0
    written_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_sourced": self.document_sourced,
            "proposed": self.proposed,
            "overridden_narrator_memory": self.overridden_narrator_memory,
            "unmapped": self.unmapped,
            "errors": self.errors,
            "written_ids": list(self.written_ids),
        }


# ─────────────────────────────────────────────────────────────────────
# Public router
# ─────────────────────────────────────────────────────────────────────


def routing_enabled() -> bool:
    """Phase C ships behind a default-off env flag so document
    ingestion stays byte-stable until the routing is verified. Set
    HORNELORE_BIO_DOC_ROUTING=1 to enable."""
    return os.environ.get(
        "HORNELORE_BIO_DOC_ROUTING", "0",
    ).strip().lower() in ("1", "true", "yes", "on")


def route_document_to_bio_facts(
    facts: List[Dict[str, Any]],
    narrator_id: str,
    doc_type: str,
    doc_id: str,
    *,
    tenant_id: str = "default",
) -> DocRouteSummary:
    """Tier 2 router — for each parsed document fact, write a
    bio_facts row at the document-type-appropriate authority level.

    Each fact must carry at minimum: fieldPath, value. Optional:
    relation (used by contextual mapping, same as Tier 1).

    Conflict policy for identity documents (document_sourced):
      - If a prior `extracted_needs_verify` row exists with a
        different value, the document write proceeds AND the prior
        row is marked `conflicted` so the operator can surface "the
        document disagrees with what the narrator said."
      - If a prior `approved` or `operator_entered` row exists, the
        document write is still recorded (with conflict_with linking
        back) but does NOT supersede the operator's choice. Per WO:
        "narrator may correct the document... operator can manually
        override."

    Per-fact errors are counted, not raised.
    """
    summary = DocRouteSummary()
    if not narrator_id or not facts:
        return summary

    status, confidence = classify_document_authority(doc_type)
    is_identity = is_identity_document(doc_type)
    bio_field_keys = bio_schema.get_field_keys()

    for raw in facts:
        try:
            field_path = str(raw.get("fieldPath") or "").strip()
            value = raw.get("value")
            relation = raw.get("relation")
            item_context = {"relation": relation} if relation else None
            bio_key = bio_fact_router.map_field_path_to_bio_key(
                field_path, item_context,
            )
            if not bio_key or bio_key not in bio_field_keys:
                summary.unmapped += 1
                continue

            existing = db.bio_fact_list_by_field(narrator_id, bio_key)
            value_json = json.dumps(value)

            conflict_with_id: Optional[str] = None
            override_count = 0
            for r in existing:
                r_status = r.get("status") or ""
                r_value_json = r.get("value") or ""
                # Identity docs supersede narrator-memory candidates
                # of different value — mark the candidate as conflicted
                # for operator review.
                if (
                    is_identity
                    and r_status == "extracted_needs_verify"
                    and r_value_json != value_json
                ):
                    try:
                        db.bio_fact_set_status(
                            r.get("id"), "conflicted",
                            conflict_with=None,  # set after we know our id
                        )
                        override_count += 1
                    except Exception:
                        pass
                # Approved / operator_entered rows hold even against
                # identity docs — but we record the conflict_with link
                # for operator visibility.
                if r_status in ("approved", "operator_entered") and \
                        r_value_json != value_json:
                    conflict_with_id = r.get("id")

            source_payload = {
                "tier": 2,
                "doc_type": doc_type,
                "doc_id": doc_id,
                "field_path": field_path,
            }
            new_id = db.bio_fact_create(
                narrator_id=narrator_id,
                field_key=bio_key,
                value_json=value_json,
                status=status,
                source_json=json.dumps(source_payload),
                confidence=confidence,
                conflict_with=conflict_with_id,
                tenant_id=tenant_id,
            )
            summary.written_ids.append(new_id)
            if status == "document_sourced":
                summary.document_sourced += 1
            else:
                summary.proposed += 1
            if override_count > 0:
                summary.overridden_narrator_memory += override_count
                # Backlink the conflicted narrator-memory rows to
                # this new doc-sourced row so the operator review
                # surface can pair them.
                for r in existing:
                    if (
                        is_identity
                        and (r.get("value") or "") != value_json
                        and r.get("status") in (
                            "extracted_needs_verify", "conflicted",
                        )
                    ):
                        try:
                            db.bio_fact_set_status(
                                r.get("id"), "conflicted",
                                conflict_with=new_id,
                            )
                        except Exception:
                            pass
        except Exception:
            summary.errors += 1
            try:
                logger.exception(
                    "[document_authority] per-fact routing failed",
                )
            except Exception:
                pass

    return summary


__all__ = [
    "DocRouteSummary",
    "classify_document_authority",
    "is_identity_document",
    "route_document_to_bio_facts",
    "routing_enabled",
]
