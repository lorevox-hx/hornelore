"""Cross-origin identity: what makes a row THE SAME ROW on two installations.

WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01. **ONE home, two consumers.**

This registry was born inside `scripts/two_origin_compare.py`, where it had a single
reader. Merge/Remap needs exactly the same judgements to classify a row, and a second
copy of it would be a second list of one truth — the failure `CLAUDE.md` opens by
naming and the one the 2026-09-14 `declared` drift had just cost a session. So it
moved here, verbatim in content and justification, and the comparator now imports it.

**This module answers ONE question and deliberately not the others.** Three different
keys exist and collapsing any two produces a tool that answers the wrong question:

  physical key    what the schema says the PK is. `turns.id` is a real primary key AND
                  installation-local: a collision surface we MEASURE, never an identity.
  ownership path  how `narrator_data_inventory` says the row belongs to the narrator.
                  Reference metadata only — never re-derived here, never used to
                  include or exclude a row.
  logical key     THIS module. Table-specific, individually justified, and frequently
                  NOT AVAILABLE — which is a verdict, not a gap.

TWO RULES, both corrections to the comparator's first draft and both binding on every
future entry:

  1. **CONTENT IS NEVER PART OF A LOGICAL KEY.** The first draft keyed `turns` on
     (conv_id, role, ts, content). If the content differs the key differs, so the one
     case worth hunting — same record, changed content — would have been reported as
     two unrelated one-side-only rows. A key must be independent of the values being
     compared.
  2. **A UUID IS NOT AUTOMATICALLY A CROSS-ORIGIN IDENTITY.** UUID syntax proves a
     minting format, not shared provenance. Two installations can mint different UUIDs
     for the same logical thing, and identical UUIDs mean "same row" only where the
     product creates the record once and carries it. There is NO blanket UUID rule:
     each table earns a logical key with a stated justification, or it is
     NO_SAFE_CROSS_ORIGIN_KEY.

**Absence from `LOGICAL_KEYS` is a decision.** It means correspondence could not be
proven — never that the rows are duplicates, and never a licence to drop one side.
"""
from __future__ import annotations

from typing import Dict, Tuple

# ── row verdicts: the vocabulary the merge and the comparator share ───
SAME_SAME = "SAME_LOGICAL_RECORD_SAME_CONTENT"
SAME_DIFF = "SAME_LOGICAL_RECORD_DIFFERENT_CONTENT"
ONLY_A = "ONLY_A"
ONLY_B = "ONLY_B"
NO_SAFE_KEY = "NO_SAFE_CROSS_ORIGIN_KEY"
KEYED = "KEYED"
# ── reported separately, never folded into the row verdicts ───────────
PHYSICAL_COLLISION = "PHYSICAL_ID_COLLISION_DIFFERENT_CONTENT"
FILE_SAME = "FILE_PATH_SAME_HASH"
FILE_DIFF = "FILE_PATH_DIFFERENT_HASH"
FILE_ONLY_A = "FILE_ONLY_A"
FILE_ONLY_B = "FILE_ONLY_B"

KIND_DECLARED = "declared_logical_key"
KIND_NO_KEY = "no_defensible_logical_key"

NO_KEY_JUSTIFICATION = (
    "no entry in the logical-key registry: no domain key, and a physical id "
    "is either installation-local or independently minted per installation. "
    "Refusing to invent a correspondence."
)


#: Every entry states WHY. A table absent from this registry has NO logical key —
#: the default is refusal, not a guess.
LOGICAL_KEYS: Dict[str, Tuple[Tuple[str, ...], str]] = {
    # The narrator themself. §31 measured the SAME people.id on both machines for
    # Chris, Kent and Janice -- empirical evidence that the row was created once
    # and carried, which is what makes this UUID an identity rather than a format.
    "people": (("id",),
               "same people.id measured on both installations (WO §31): created once, carried"),

    # One row per narrator per installation; the PK is the narrator. What differs
    # is the CONTENT, which is exactly what we want surfaced.
    "profiles": (("person_id",), "PK is person_id: one row per narrator per installation"),
    "bio_builder_questionnaires": (("person_id",), "PK is person_id"),
    "interview_projections": (("person_id",), "PK is person_id"),
    "profile_seed_onboarding": (("person_id",), "PK is person_id"),

    # A fact is (narrator, field). bio_facts.id is a per-installation UUID, so the
    # PK would wrongly report every fact as origin-unique. Multiple rows per field
    # are expected (BACKLOG §5 questionnaire_put duplication) and are reported as
    # duplicate keys rather than collapsed.
    "bio_facts": (("narrator_id", "field_key"),
                  "domain key: a fact is (narrator, field); the VALUE is the conflict"),

    # conv_id is the product-wide conversation identity (0039) and is carried in
    # every lane that references a conversation.
    "sessions": (("conv_id",), "conv_id is the product-wide conversation key (0039)"),
    "memory_archive_sessions": (("person_id", "conv_id"), "archive session is keyed by conversation"),
    "memory_archive_turns": (("person_id", "conv_id", "seq"),
                             "seq is a stable per-conversation ordinal in this table (0002)"),
}

#: Columns excluded from CONTENT comparison, per table, each with a reason that it
#: is non-semantic for merge purposes. Deliberately NOT a blanket "ignore all
#: timestamps": a timestamp can be narrator meaning (when a trip happened) and
#: hiding it would hide a real conflict.
VOLATILE_COLUMNS: Dict[str, Dict[str, str]] = {
    "profiles": {"updated_at": "row rewrite stamp; the app rewrites it on narrator open (BACKLOG §5)"},
    "bio_builder_questionnaires": {"updated_at": "row rewrite stamp; rewritten on narrator open"},
    "sessions": {"updated_at": "row rewrite stamp; not narrator meaning"},
}


def logical_key_for(table: str) -> Tuple[str, Tuple[str, ...], str]:
    """(kind, columns, justification). Absence from the registry is a VERDICT."""
    if table in LOGICAL_KEYS:
        cols, why = LOGICAL_KEYS[table]
        return KIND_DECLARED, cols, why
    return KIND_NO_KEY, (), NO_KEY_JUSTIFICATION


def volatile_columns(table: str) -> Dict[str, str]:
    return VOLATILE_COLUMNS.get(table, {})


__all__ = [
    "SAME_SAME", "SAME_DIFF", "ONLY_A", "ONLY_B", "NO_SAFE_KEY", "KEYED",
    "PHYSICAL_COLLISION", "FILE_SAME", "FILE_DIFF", "FILE_ONLY_A", "FILE_ONLY_B",
    "KIND_DECLARED", "KIND_NO_KEY", "NO_KEY_JUSTIFICATION",
    "LOGICAL_KEYS", "VOLATILE_COLUMNS", "logical_key_for", "volatile_columns",
]
