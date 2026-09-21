"""Projection writer — applies parsed corrections to a narrator's
interview_projections.projection_json record.

BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01 Phase 3 (2026-05-07):
this module closes the loop on corrections. Phase 1 (regex-based
detection in memory_echo.parse_correction_rule_based) and Phase 2
(chat_ws turn_mode dispatch + correction_payload to client) were
already in place. Phase 3 adds the server-side write so corrections
that the narrator volunteers actually mutate the canonical
provisional-truth surface — not just acknowledged in prose.

LAW 3 — this service touches DB only. It does NOT import from
extract.py / prompt_composer / llm_api / chat_ws. The chat_ws caller
hands us the parsed correction dict; we map it onto the projection
shape and write back via db.upsert_projection.

Layer boundaries (per Architecture Spec v1):
  - parser     (memory_echo.parse_correction_rule_based) — text → dict
  - applier    (this module) — dict → projection write
  - composer   (prompt_composer.compose_correction_ack) — dict → narrator-facing reply

Composition rule: applier runs FIRST so the projection has the new
value, THEN the composer reads (or the next memory_echo turn reads)
the updated state. Failures in apply_correction are non-fatal —
caller continues to compose + send the ack response. The DB write
is best-effort because LAW 3 says the chat path must not break on
storage trouble.

Fieldpath mapping (parser → projection):
  family.children.count        → personal.childrenCount
                                  (also clears any conflicting
                                  pendingSuggestion at children[].count)
  family.parents.father.name   → parents[0].firstName    (role=father)
                                  Or just store as parents.father.name
                                  pendingSuggestion if no parents[]
                                  array exists yet.
  family.parents.mother.name   → parents[1].firstName    (role=mother)
  identity.place_of_birth      → personal.placeOfBirth
  education_work.retirement    → community.retirement_status
                                  (free-form; "never fully retired")

_retracted (control sentinel, not a field path):
  Each retracted value is a string the narrator says they did NOT
  say or that should NOT be a real fact. Apply by scanning all
  pendingSuggestions + fields for any value that contains the
  retracted token (case-insensitive) and removing it / lowering
  confidence. This handles Melanie's "there was no Hannah" — any
  pendingSuggestion that introduced "Hannah" gets scrubbed.
"""
from __future__ import annotations

import json

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Mapping from parser field-path keys → canonical projection field paths.
# Conservative: only field paths we KNOW the schema accepts. Unmapped
# entries from the parser get logged but skipped (they may be valid
# parser output the schema doesn't yet have a slot for).
_PARSER_TO_PROJECTION: Dict[str, str] = {
    "family.children.count":        "personal.childrenCount",
    "family.parents.father.name":   "parents.father.firstName",
    "family.parents.mother.name":   "parents.mother.firstName",
    "identity.place_of_birth":      "personal.placeOfBirth",
    "education_work.retirement":    "community.retirementStatus",
}


def _server_owned_suggestion(field_path: str, value: str, now: str, *,
                             person_id: Optional[str] = None,
                             source_turn_id: Optional[str] = None,
                             confidence: float = 0.8,
                             **extra: Any) -> Dict[str, Any]:
    """A queue entry with the four facts the server owns.

    The append route (`routers/projection.py`) establishes these at
    proposal time and the comment there says they are "DECIDED HERE AND
    NEVER RE-DECIDED". This is the second producer, and it has to decide
    the same things or it makes rows the review surface cannot handle:

      suggestion_id           minted; without it the proposal can never
                              be accepted or declined, only accumulate
      turn_evidence           the MEASURED verdict on the cited turn
      destination_undefined   whether the questionnaire has this field.
                              Its PRESENCE is also what marks a proposal
                              as non-legacy, which is correct — this one
                              was checked by today's code
      destination_unresolved  a repeatable section needs a person to
                              choose an entry

    FAIL-CLOSED ON AN UNREADABLE SCHEMA. If the questionnaire cannot be
    parsed we cannot claim the destination is valid, so we say it is
    undefined. Acceptance then refuses until someone looks. Claiming
    `False` — "checked, and fine" — on the strength of an exception
    would be the one answer that is definitely wrong.
    """
    import uuid

    entry: Dict[str, Any] = {
        "suggestion_id": "sg_" + uuid.uuid4().hex[:16],
        "fieldPath": field_path,
        "value": value,
        "confidence": float(confidence),
        "turnId": source_turn_id,
        "source_turn_id": source_turn_id,
        "ts": now,
        "repeats": 1,
    }
    entry.update({k: v for k, v in extra.items() if v is not None})

    # The turn citation is a claim; verify it with the same join the
    # append route uses rather than asserting evidence we never checked.
    entry["turn_evidence"] = "absent"
    if source_turn_id and person_id:
        try:
            from .. import db as _db
            from .answer_provenance import verify_turn
            _c = _db._connect()
            try:
                entry["turn_evidence"] = verify_turn(_c, person_id, source_turn_id)
            finally:
                _c.close()
        except Exception:
            logger.warning("[projection-writer] could not verify turn %r; "
                           "recording the citation as unverified", source_turn_id)
            entry["turn_evidence"] = "unverified"

    section, _, rest = str(field_path or "").partition(".")
    field = rest.split(".")[-1] if rest else ""
    try:
        from . import questionnaire_schema as _qs
        entry["destination_undefined"] = not _qs.is_defined(section, field)
        if _qs.is_repeatable(section):
            entry["destination_unresolved"] = True
    except Exception:
        logger.warning("[projection-writer] questionnaire schema unreadable; "
                       "queuing %s as destination_undefined", field_path)
        entry["destination_undefined"] = True
    return entry


def apply_correction(
    person_id: str,
    parsed: Dict[str, Any],
    *,
    source_turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a parsed correction to the narrator's projection_json.

    Args:
        person_id:       narrator UUID. Required.
        parsed:          dict from parse_correction_rule_based. May contain
                         field paths (string keys) and/or control sentinels
                         (`_retracted` / `_meant`).
        source_turn_id:  optional turn_id to record in the field metadata
                         for audit / rollback.

    Returns:
        Summary dict with `applied` (list of {field_path, value}),
        `retracted` (list of values scrubbed from pendingSuggestions),
        `skipped` (list of {field_path, reason}), `errors` (list of
        strings — non-fatal). On any unexpected exception, logs +
        returns errors-only — never raises into the chat path.
    """
    summary: Dict[str, Any] = {
        "applied": [],
        "retracted": [],
        "skipped": [],
        "errors": [],
        # BUG-PROJECTION-CORRECTION-OVERRIDES-OPERATOR-01: corrections aimed
        # at operator-entered fields are not applied. They are queued as
        # pendingSuggestions and listed here, so a caller can tell "the model
        # proposed a change and it is waiting for a person" apart from both
        # "applied" and "skipped". Declared up front rather than via
        # setdefault so every caller sees the key whether or not it fired.
        "deferred": [],
    }
    if not person_id:
        summary["errors"].append("missing_person_id")
        return summary
    if not isinstance(parsed, dict) or not parsed:
        summary["errors"].append("empty_or_invalid_parsed")
        return summary

    # Lazy import — keeps LAW 3 boundary visible (db is the only project
    # dependency this module reaches into).
    try:
        from .. import db as _db
    except Exception as exc:
        summary["errors"].append(f"db_import_failed: {exc}")
        return summary

    # Read existing projection. Empty/missing → start with fresh shape.
    try:
        existing_blob = _db.get_projection(person_id) or {}
    except Exception as exc:
        logger.warning("[projection-writer] get_projection failed for %s: %s", person_id, exc)
        existing_blob = {}

    proj = existing_blob.get("projection") if isinstance(existing_blob.get("projection"), dict) else {}
    fields = proj.get("fields") if isinstance(proj.get("fields"), dict) else {}
    pending = proj.get("pendingSuggestions") if isinstance(proj.get("pendingSuggestions"), list) else []

    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 (2026-08-17).
    # Snapshot the fields and the suggestion queue BEFORE this correction
    # touches them, so the write below can be the DIFF rather than the
    # whole document. See the write site for why that matters.
    _fields_before = json.loads(json.dumps(fields, ensure_ascii=False)) if fields else {}
    _pending_before = json.loads(json.dumps(pending, ensure_ascii=False)) if pending else []

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ── Field corrections ────────────────────────────────────────────
    for parser_key, value in parsed.items():
        # Skip control sentinels — handled separately below
        if parser_key.startswith("_"):
            continue
        canonical = _PARSER_TO_PROJECTION.get(parser_key)
        if not canonical:
            summary["skipped"].append({
                "field_path": parser_key,
                "reason": "no_canonical_mapping",
            })
            continue
        # Normalize value to string for storage; numeric counts kept as
        # integer-looking string so downstream readers can choose how
        # to coerce. Lists are not used here.
        v_str = str(value).strip() if value is not None else ""
        if not v_str:
            summary["skipped"].append({
                "field_path": parser_key,
                "reason": "empty_value",
            })
            continue
        # ── BUG-PROJECTION-CORRECTION-OVERRIDES-OPERATOR-01 (2026-09-18) ──
        #
        # This assigned a fresh dict unconditionally. Two defects in one line.
        #
        # (a) IT OVERRODE THE OPERATOR. A model-detected correction landing on
        #     a path the operator had typed replaced it silently. `locked` is
        #     set true for human_edit (projection-sync.js:286) and the browser
        #     refuses lower-authority writes to a locked field
        #     (projection-sync.js:212-215) — but that gate lives only in the
        #     browser, and this is the server. An operator who entered their
        #     mother's birthplace from a document could have it changed by a
        #     model's reading of a sentence in conversation, with no record
        #     that it happened.
        #
        # (b) IT ERASED THE AUDIT TRAIL. The replacement carried no `history`
        #     and no `locked`, so the last-10 correction history
        #     (projection-sync.js:268-278) was destroyed by exactly the writer
        #     whose changes most need tracing, and the field silently lost its
        #     operator-authority flag on the way through.
        #
        # What happens now when a model corrects a locked field: it does NOT
        # apply. It is queued as a pendingSuggestion — the mechanism that
        # already exists for untrusted writes to protected paths
        # (projection-sync.js:238-247), with storage, an accept/dismiss UI
        # (acceptSuggestion / dismissSuggestion, :588-639) and a review
        # surface. The model may propose; the operator decides.
        #
        # See docs/wo/WO-BIOGRAPHY-READ-CONTRACT-01.md for the tier order.
        prev = fields.get(canonical) if isinstance(fields.get(canonical), dict) else None
        prev_locked = bool(prev.get("locked")) if prev else False
        prev_source = (prev.get("source") or "") if prev else ""
        operator_owned = prev_locked or prev_source == "human_edit"

        if operator_owned and prev.get("value") != v_str:
            # Propose, do not impose. One suggestion per path, newest wins,
            # mirroring the browser's queue semantics (projection-sync.js:564).
            #
            # ── THE SECOND PRODUCER (2026-09-20) ────────────────────────
            #
            # This block used to append seven keys and no `suggestion_id`.
            # That made it a live source of the exact problem the identity
            # backfill exists to repair: `find_suggestion` matches on
            #
            #     s.get("suggestion_id") == suggestion_id
            #
            # so an entry without one can never be accepted OR declined.
            # Every correction deferred here became permanently stuck in
            # the queue. A one-time backfill would have repaired the
            # thirty fossils and this would have started making new ones
            # the same afternoon.
            #
            # It also carried no `destination_undefined`, so
            # `_is_unchecked_legacy` read it as pre-cutover — a proposal
            # created today, labelled as predating the route that checks
            # destinations. The legacy tier is about PROVENANCE, and the
            # provenance of this one is known exactly.
            #
            # So it now establishes the same four facts the append route
            # does. What it does NOT change is the protection above: an
            # operator-entered value is still never overwritten, and this
            # is still only reached because it refused to overwrite one.
            dropped = [s.get("suggestion_id") for s in pending
                       if isinstance(s, dict) and s.get("fieldPath") == canonical]
            pending = [
                s for s in pending
                if not (isinstance(s, dict) and s.get("fieldPath") == canonical)
            ]
            if dropped:
                # Newest-wins is the existing semantics and is left alone,
                # but it must not be silent: a superseded proposal may
                # already carry a flag, a decline history or an id a
                # person has seen.
                logger.info(
                    "[projection-writer] superseded %d queued proposal(s) at "
                    "%s for %s: %s", len(dropped), canonical,
                    (person_id or "")[:8], dropped)
            pending.append(_server_owned_suggestion(
                canonical, v_str, now,
                person_id=person_id, source_turn_id=source_turn_id,
                confidence=0.8,
                supersedes=prev.get("value"),
                reason="correction_to_operator_entered_field",
            ))
            summary["deferred"].append({
                "field_path": canonical,
                "value": v_str,
                "current_value": prev.get("value"),
                "reason": "operator_entered_field_not_overwritten",
            })
            logger.info(
                "[projection-writer] correction DEFERRED for %s: %s is "
                "operator-entered (locked=%s). Queued for review instead of "
                "overwriting %r with %r.",
                (person_id or "")[:8], canonical, prev_locked,
                prev.get("value"), v_str,
            )
            continue

        # Applying. Carry the previous entry's history forward and append the
        # value being replaced, so a correction is traceable rather than a
        # silent substitution. Capped at 10 to match the browser writer.
        history = list(prev.get("history") or []) if prev else []
        if prev and prev.get("value") not in (None, "", v_str):
            history.append({
                "value": prev.get("value"),
                "source": prev.get("source"),
                "turnId": prev.get("turnId") or prev.get("turn_id"),
                "confidence": prev.get("confidence"),
                "ts": prev.get("ts") or prev.get("applied_at"),
            })
        fields[canonical] = {
            "value": v_str,
            "source": "correction",
            "confidence": "high",
            "turn_id": source_turn_id,
            "applied_at": now,
            # Both spellings. The browser's gates read `turnId`/`ts`
            # (projection-sync.js:281-289) and this writer's original keys
            # were turn_id/applied_at, so a corrected field was invisible to
            # every client-side check. Write both rather than migrate a shape
            # that already has two variants in production data.
            "turnId": source_turn_id,
            "ts": now,
            "locked": prev_locked,
            "history": history[-10:],
        }
        summary["applied"].append({
            "field_path": canonical,
            "value": v_str,
        })

    # ── Retraction handling — scrub pendingSuggestions ──────────────
    retracted_tokens: List[str] = []
    for r in (parsed.get("_retracted") or []):
        r_str = str(r).strip()
        if r_str:
            retracted_tokens.append(r_str)

    if retracted_tokens:
        scrubbed_pending: List[Dict[str, Any]] = []
        for sug in pending:
            if not isinstance(sug, dict):
                scrubbed_pending.append(sug)
                continue
            sug_value = (sug.get("value") or "")
            if not isinstance(sug_value, str):
                scrubbed_pending.append(sug)
                continue
            v_lower = sug_value.lower()
            matched_token = None
            for tok in retracted_tokens:
                if tok.lower() in v_lower:
                    matched_token = tok
                    break
            if matched_token is not None:
                summary["retracted"].append({
                    "field_path": sug.get("fieldPath"),
                    "value": sug_value,
                    "matched_token": matched_token,
                })
                # Drop the suggestion entirely. Audit trail is in
                # summary["retracted"] for the operator surface.
                continue
            scrubbed_pending.append(sug)
        pending = scrubbed_pending

        # Also scrub fields that match the retracted tokens, EXCEPT
        # corrections we just applied this turn (the fields[]
        # additions above) — those are the new authoritative values.
        applied_paths = {a["field_path"] for a in summary["applied"]}
        scrubbed_fields = {}
        for fp, entry in fields.items():
            if fp in applied_paths:
                scrubbed_fields[fp] = entry
                continue
            if not isinstance(entry, dict):
                scrubbed_fields[fp] = entry
                continue
            v = entry.get("value") or ""
            if not isinstance(v, str):
                scrubbed_fields[fp] = entry
                continue
            v_lower = v.lower()
            matched = None
            for tok in retracted_tokens:
                if tok.lower() in v_lower:
                    matched = tok
                    break
            if matched is not None:
                summary["retracted"].append({
                    "field_path": fp,
                    "value": v,
                    "matched_token": matched,
                    "from_fields": True,
                })
                # Drop from canonical fields entirely — the narrator
                # explicitly retracted this. If they want it back they
                # can volunteer it again.
                continue
            scrubbed_fields[fp] = entry
        fields = scrubbed_fields

    # Stage the updated projection shape and write back. Preserve any
    # other top-level keys the projection may carry (timeline_events,
    # extracted_summary, etc.) by mutating in place.
    proj["fields"] = fields
    proj["pendingSuggestions"] = pending
    proj["last_correction_at"] = now

    if not summary["applied"] and not summary["retracted"] and not summary.get("deferred"):
        # Parser returned only control sentinels with no effect —
        # nothing to persist. Still success-shaped so caller doesn't
        # treat this as an error.
        #
        # BUG-PROJECTION-CORRECTION-OVERRIDES-OPERATOR-01: `deferred` had to
        # join this condition. A correction aimed ONLY at operator-entered
        # fields applies nothing and retracts nothing — it just queues
        # suggestions — so without this the early return dropped the queue on
        # the floor and the model's proposal was lost silently. The whole
        # point of deferring is that somebody gets to see the proposal later.
        return summary

    try:
        # FIELD-LEVEL, not whole-document.
        #
        # This used to read the whole projection and call
        # upsert_projection(), which replaces the row. The HTTP PUT was
        # hardened first, and that left this internal path as the last
        # writer that could still erase a browser mutation landing
        # between the read above and the write here -- a correction turn
        # and a narrator edit are exactly the pair most likely to
        # overlap, because they happen in the same seconds.
        #
        # Only the paths this correction actually changed are sent, so a
        # concurrent edit to any other path survives. base_fields carries
        # what THIS writer read, so the per-path comparison and the write
        # happen inside one BEGIN IMMEDIATE transaction in
        # merge_projection_fields.
        _mutations = {
            k: v for k, v in fields.items()
            if k not in _fields_before or _fields_before[k] != v
        }
        _removals = [k for k in _fields_before if k not in fields]
        _pending_changed = pending != _pending_before
        _base = {k: _fields_before.get(k) for k in list(_mutations) + _removals}

        _result = _db.merge_projection_fields(
            person_id,
            mutations=_mutations,
            removals=_removals,
            source="correction",
            base_fields=_base,
            pending_suggestions=(pending if _pending_changed else None),
            extra_keys={"last_correction_at": now},
        )
        if _result.get("conflict"):
            # The narrator edited one of these very paths while the turn
            # was in flight. Reported, never overwritten -- the operator
            # review queue is where that is resolved.
            summary["errors"].append(
                "projection_conflict: " + ",".join(_result.get("conflicting_paths") or [])
            )
            logger.warning(
                "[projection-writer] correction CONFLICTED person=%s paths=%s turn=%s "
                "-- nothing written",
                person_id, _result.get("conflicting_paths"), source_turn_id,
            )
            return summary
        logger.info(
            "[projection-writer] applied correction person=%s applied=%d retracted=%d turn=%s",
            person_id,
            len(summary["applied"]),
            len(summary["retracted"]),
            source_turn_id,
        )
        # TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- observability only.
        # No behavior change. No-op unless HORNELORE_TRUTH_PIPELINE_LOG=1
        # AND a turn probe is active in this context. Failure is swallowed.
        try:
            from . import truth_pipeline_probe as _tp
            _tp.mark("projection_updated", "interview_projections")
        except Exception:
            pass
    except Exception as exc:
        logger.warning(
            "[projection-writer] merge_projection_fields failed person=%s: %s",
            person_id, exc,
        )
        summary["errors"].append(f"merge_failed: {exc}")

    return summary


__all__ = ["apply_correction"]
