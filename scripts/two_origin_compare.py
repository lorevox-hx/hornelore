#!/usr/bin/env python3
"""READ ONLY. Compare the SAME narrator as packaged from TWO different installations.

WO-LOREVOX-PORTABLE-NARRATOR-01, between Phase 6 and the Multi-Origin Merge/Remap
work order. Phase 6 proved each origin independently: a package from either machine
restores into a clean root and re-exports EQUIVALENT. This answers the next question,
which no existing tool answers:

    Given Christopher-as-the-desktop-holds-him and Christopher-as-the-laptop-holds-him,
    what is on both, what is on only one, and what CONFLICTS?

WHY THE EXISTING TOOLS DO NOT DO THIS
  * `narrator_package.compare_packages_semantically` answers "are these two packages
    the same?" For rows without an `id` it uses the WHOLE CANONICAL ROW as identity, so
    a changed row appears as two unrelated rows and it CANNOT name the differing
    columns -- the question a merge must answer.
  * `scripts/phase0_report_comparator.py` compares audit COUNTS, and says so itself.

WHAT THIS WILL NOT DO, by construction: never writes to, rewrites, normalises,
re-zips or deletes a package; never opens a database; never restores; implements no
merge and no remap. It produces evidence, and nothing else.

═══════════════════════════════════════════════════════════════════════
THREE DIFFERENT KEYS, DERIVED SEPARATELY (review 2026-09-12)
═══════════════════════════════════════════════════════════════════════
Collapsing any two of these produces a comparator that answers the wrong question.

  physical key    what the schema says the PK is. `turns.id` is a real primary key
                  AND installation-local: the collision surface we MEASURE, never an
                  identity we trust.
  ownership path  how the declaration says the row belongs to the narrator. Reference
                  metadata ONLY -- never re-derived, never used to include/exclude.
                  The package already holds exactly what the exporter selected.
  logical key     what makes a row THE SAME ROW on two installations. Table-specific,
                  justified, and often NOT AVAILABLE -- which is a verdict.

TWO RULES LEARNED THE HARD WAY, both corrections to this file's first draft:

  1. CONTENT IS NEVER PART OF A LOGICAL KEY. The first draft keyed `turns` on
     (conv_id, role, ts, content). If the content differs the key differs, so the
     one case we are hunting -- same record, changed content -- would have been
     silently reported as two one-side-only rows. A key must be independent of the
     values being compared.
  2. A UUID IS NOT AUTOMATICALLY A CROSS-ORIGIN IDENTITY. UUID syntax proves a
     minting format, not shared provenance: two installations can mint different
     UUIDs for the same logical thing, and identical UUIDs only mean "same row"
     where the product creates the record once and carries it. So there is NO
     blanket UUID rule. Each table earns a logical key or is reported
     NO_SAFE_CROSS_ORIGIN_KEY, and shared-physical-id counts are reported
     SEPARATELY as evidence for the merge design to weigh.

USAGE
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/two_origin_compare.py \\
        --a .runtime/two_origin/desktop/<pkg>.lorevox.zip \\
        --b .runtime/two_origin/laptop/<pkg>.lorevox.zip \\
        --label-a desktop --label-b laptop \\
        --out .runtime/two_origin/reports

Writes report.json (complete detail) and summary.md (aggregated, bounded examples).
Reports carry real narrator content and live under `.runtime/`, which is gitignored.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_NAME = "lorevox-manifest.json"
RECORDS_PREFIX = "data/records/"
FILES_PREFIX = "data/files/"

# ── the shared registries live in ONE place, not two ──────────────────
#
# The logical-key registry and the verdict vocabulary were defined HERE until
# 2026-09-14, when Merge/Remap became their second consumer. A second copy would
# have been a second list of one truth — the drift that had just cost a session
# via the `declared` booleans — so they moved to the service layer and this file
# imports them. Names are re-exported unchanged: `toc.LOGICAL_KEYS`,
# `toc.SAME_DIFF` and the rest still resolve, and no caller or test changed.
_SERVER_CODE = str(Path(__file__).resolve().parents[1] / "server" / "code")
if _SERVER_CODE not in sys.path:
    sys.path.insert(0, _SERVER_CODE)

from api.services import cross_origin_identity as _xid  # noqa: E402

# ── row verdicts: the vocabulary the Merge/Remap WO consumes ──────────
SAME_SAME = _xid.SAME_SAME
SAME_DIFF = _xid.SAME_DIFF
ONLY_A = _xid.ONLY_A
ONLY_B = _xid.ONLY_B
NO_SAFE_KEY = _xid.NO_SAFE_KEY
KEYED = _xid.KEYED
# ── reported separately, never folded into the row verdicts ───────────
PHYSICAL_COLLISION = _xid.PHYSICAL_COLLISION
FILE_SAME = _xid.FILE_SAME
FILE_DIFF = _xid.FILE_DIFF
FILE_ONLY_A = _xid.FILE_ONLY_A
FILE_ONLY_B = _xid.FILE_ONLY_B


# ══════════════════════════════════════════════════════════════════════
# The logical-key registry. Every entry states WHY. A table absent from
# this registry has NO logical key -- the default is refusal, not a guess.
#
# DEFINED IN `api.services.cross_origin_identity`, not here, since 2026-09-14.
# Merge/Remap needs the same judgements to classify a row, and the entries carry
# their own justifications -- a second copy would drift exactly the way the
# `declared` booleans in this file had just drifted. Re-exported so every existing
# reference (`toc.LOGICAL_KEYS`, `toc.VOLATILE_COLUMNS`) still resolves.
# ══════════════════════════════════════════════════════════════════════

LOGICAL_KEYS: Dict[str, Tuple[Tuple[str, ...], str]] = _xid.LOGICAL_KEYS
VOLATILE_COLUMNS: Dict[str, Dict[str, str]] = _xid.VOLATILE_COLUMNS

#: Where an installation-local surrogate is REFERENCED. The Merge/Remap closure must
#: rewrite every one of these consistently, or the merged root dangles.
#: `form` matters: an integer column can be rewritten by a join; a STRING-EMBEDDED
#: reference has to be parsed and rebuilt, and an FK-graph walk does not see it at all.
# ── ONE reference-record shape, validated at the producer ────────────
#
# The renderer must never guess at a record's fields. An earlier revision renamed
# `kind` to `form` in the declaration table but not in the summary, and the mismatch
# surfaced as a KeyError in the middle of a real family comparison — the renderer
# discovering a schema drift that the producer should have refused to create.
# Every reference record is now built through `_ref()`, which raises on a missing
# field, and a test asserts the shape of every emitted record.

# ── `declared` is ASKED of production, never restated here (2026-09-14) ──
#
# It used to be a hand-written boolean beside each site, and five of them went
# stale the moment the 2026-09-12 repair landed: that repair added both
# `story_candidates` turn columns to `COLUMN_ONLY_REFERENCES` and all three
# encoded forms to `ENCODED_REFERENCES`, and nothing updated this file. The
# report then told a real family comparison that the exporter's §30 "refuse,
# never dangle" guard does not check references it had been checking for two
# days — and `narrator_data_inventory` names THIS FILE as one of the four
# consumers the single declaration exists to keep from drifting.
#
# THE SEVEN SITES BELOW STAY INDEPENDENTLY DISCOVERED, by reading the shipped
# migrations and writers. Deriving the closure itself from the declaration
# would make this file ask the declaration what exists, and the comparator
# would lose the one thing that can catch the declaration being WRONG. What is
# derived is a single bit per site — whether production currently declares it —
# so the two lists can be COMPARED (`closure_parity`) instead of silently
# agreeing with each other.

REFERENCE_RECORD_FIELDS = ("table", "column", "form", "declared", "declared_by",
                           "requires_rewrite", "cite")
#: Audit records add these four to the base shape.
REFERENCE_AUDIT_FIELDS = REFERENCE_RECORD_FIELDS + ("rows_in_package", "references_found",
                                                    "dangling", "dangling_samples")

#: What `declared_by` reports. A real SQL FK is declared by SQLite itself and is
#: NOT in `COLUMN_ONLY_REFERENCES`, whose whole purpose is references the schema
#: does *not* declare — so asking only the two inventory tuples would report the
#: one genuine foreign key in this closure as undeclared, replacing a stale false
#: statement with a fresh one.
DECLARED_BY_SQL_FK = "SQL FOREIGN KEY"
DECLARED_BY_NOTHING = "(not declared)"


def _inventory():
    """Import the live production declaration, or REFUSE.

    Deliberately NOT the swallow-and-degrade idiom `ownership_path` uses: there a
    missing declaration costs a printed label, whereas here it would silently mark
    every site undeclared and reproduce the exact defect this lookup was written to
    remove. A refusal is a result; a quiet `False` is a false report.
    """
    root = str(Path(__file__).resolve().parents[1] / "server" / "code")
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.services import narrator_data_inventory as inv  # type: ignore
    return inv


def production_declared_references(parent_table: str,
                                   parent_key: str = "id") -> Dict[Tuple[str, str], str]:
    """Every (table, column) PRODUCTION declares as a reference to `parent_table.parent_key`,
    mapped to the mechanism that declares it.

    BOTH inventory mechanisms count, and reading only one is how this drifted:
    `COLUMN_ONLY_REFERENCES` carries the bare-INTEGER columns SQLite cannot declare
    (ALTER TABLE cannot add an FK), `ENCODED_REFERENCES` the TEXT and JSON forms an
    FK walk cannot see at all.
    """
    inv = _inventory()
    found: Dict[Tuple[str, str], str] = {}
    for cr in inv.COLUMN_ONLY_REFERENCES:
        if cr.parent_table == parent_table and cr.parent_key == parent_key:
            found[(cr.table, cr.column)] = "COLUMN_ONLY_REFERENCES"
    for er in inv.ENCODED_REFERENCES:
        if er.parent_table == parent_table and er.parent_key == parent_key:
            found[(er.table, er.column)] = "ENCODED_REFERENCES"
    return found


def _ref(table: str, column: str, form: str, cite: str, parent: str,
         requires_rewrite: bool = True, sql_fk: bool = False) -> Dict[str, Any]:
    """Build a reference record, refusing to create a malformed one.

    `declared` is resolved against the CURRENT production declaration at build
    time. `parent` is '<table>.<key>' — the surrogate this site stores.
    """
    parent_table, _, parent_key = parent.partition(".")
    if sql_fk:
        declared_by = DECLARED_BY_SQL_FK
    else:
        declared_by = production_declared_references(
            parent_table, parent_key or "id").get((table, column), DECLARED_BY_NOTHING)
    rec = {"table": table, "column": column, "form": form,
           "declared": declared_by != DECLARED_BY_NOTHING, "declared_by": declared_by,
           "requires_rewrite": requires_rewrite, "cite": cite, "sql_fk": sql_fk,
           "parent": parent}
    missing = [f for f in REFERENCE_RECORD_FIELDS
               if f not in rec or (f != "declared" and rec[f] in (None, ""))]
    if missing:
        raise ValueError(f"reference record for {table}.{column} is missing {missing}")
    return rec


def validate_reference_record(rec: Dict[str, Any], audit: bool = False) -> None:
    """Raise unless `rec` carries every field the renderer will read."""
    required = REFERENCE_AUDIT_FIELDS if audit else REFERENCE_RECORD_FIELDS
    missing = [f for f in required if f not in rec]
    if missing:
        raise ValueError(f"reference record {rec.get('table')}.{rec.get('column')} missing {missing}")


#: Built by READING the shipped migrations and writers, 2026-09-12, not by walking
#: PRAGMA foreign_key_list -- which finds NONE of these seven. Corrected 2026-09-14:
#: this comment said "only two of the seven", conflating "two are declared in
#: COLUMN_ONLY_REFERENCES" with "two are visible to SQLite". They are different
#: claims and both trip_turn_links columns are the counter-example -- 0039:135-136
#: declares them bare INTEGER with no REFERENCES clause, the 0040 rebuild keeps them
#: bare, and no migration anywhere contains `REFERENCES turns`. SQLite sees ZERO
#: references to turns.id, which is a stronger statement of the same point.
#: This list is INDEPENDENT EVIDENCE and must stay that way:
#: it is what `closure_parity` holds the production declaration against. Whether a
#: site is declared is resolved by `_ref` against the live inventory, never written
#: down here. `form` is also the parse instruction: INTEGER / TEXT / JSON decide how
#: a value is read and how it would have to be rewritten.
SURROGATE_REFERENCES: Dict[str, List[Dict[str, Any]]] = {
    "turns.id": [
        _ref("trip_turn_links", "user_turn_row_id", "INTEGER column",
             "0039:135 -- no SQL FK", "turns.id"),
        _ref("trip_turn_links", "assistant_turn_row_id", "INTEGER column",
             "0039:135 -- no SQL FK", "turns.id"),
        _ref("story_candidates", "source_user_turn_row_id", "INTEGER column",
             "0047:68 ALTER TABLE ADD COLUMN INTEGER -- SQLite cannot add an FK", "turns.id"),
        _ref("story_candidates", "completed_assistant_turn_row_id", "INTEGER column",
             "0047:69 -- SQLite cannot add an FK", "turns.id"),
        _ref("turn_extraction_ledger", "turn_key", "TEXT 'turnrow:<turns.id>'",
             "0038:62-65; built by db.turn_extraction_key_for_row (db.py:9679)", "turns.id"),
        _ref("turn_extraction_results", "turn_key", "TEXT 'turnrow:<turns.id>'",
             "0041:71-73", "turns.id"),
        _ref("bio_facts", "source", "JSON object, key `turn_key` = 'turnrow:<turns.id>'",
             "bio_fact_router.py:367-373 source_payload", "turns.id"),
    ],
    "turn_extraction_ledger.id": [
        _ref("turn_extraction_results", "ledger_id", "INTEGER column (real SQL FK)",
             "0041:67-68 REFERENCES turn_extraction_ledger(id) ON DELETE CASCADE",
             "turn_extraction_ledger.id", sql_fk=True),
    ],
}


def closure_parity(parent: str = "turns.id") -> Dict[str, Any]:
    """Hold the INDEPENDENTLY discovered closure against the production declaration.

    This is the cross-check the `declared` bit exists to enable, and it is printed in
    the report rather than living only in a test, because either direction is a real
    finding that a merge design must not inherit silently:

      * discovered but NOT declared -> an EXPORT GAP. The exporter's §30 guard is not
        checking that column, so a package can ship a dangling reference.
      * declared but NOT discovered -> EVIDENCE DRIFT. Production knows a reference
        this closure does not carry, so a remap built from this list would leave it
        unrewritten.

    Neither is resolved here. Both are named. Sites declared by a real SQL FK are
    excluded: they are declared by SQLite, not by the inventory tuples, and counting
    them either way would make the comparison meaningless.
    """
    parent_table, _, parent_key = parent.partition(".")
    discovered = {(r["table"], r["column"]) for r in SURROGATE_REFERENCES[parent]
                  if not r["sql_fk"]}
    declared = production_declared_references(parent_table, parent_key or "id")
    only_discovered = sorted(discovered - set(declared))
    only_declared = sorted(set(declared) - discovered)
    return {
        "parent": parent,
        "discovered": sorted(discovered),
        "declared": sorted(declared),
        "discovered_count": len(discovered),
        "declared_count": len(declared),
        "discovered_not_declared": only_discovered,
        "declared_not_discovered": only_declared,
        "in_parity": not only_discovered and not only_declared,
    }

TURNROW_RX = re.compile(r"^turnrow:(\d+)$")

KIND_DECLARED = _xid.KIND_DECLARED
KIND_NO_KEY = _xid.KIND_NO_KEY

_UUIDISH = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")


def _looks_uuid(v: Any) -> bool:
    return isinstance(v, str) and bool(_UUIDISH.match(v))


def _looks_integer_surrogate(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, str) and v.isdigit()


def physical_key(rows: List[Dict[str, Any]]) -> str:
    """What the PACKAGE shows the primary key to be. Reported even -- especially --
    when it is not usable as a cross-origin identity."""
    ids = [r.get("id") for r in rows if "id" in r]
    if not ids:
        return "(no `id` column in the packaged rows)"
    if all(_looks_uuid(v) for v in ids):
        return "id (UUID)"
    if all(_looks_integer_surrogate(v) for v in ids):
        return "id (INTEGER surrogate, installation-local)"
    return "id (mixed shapes)"


def ownership_path(table: str) -> str:
    """How the DECLARATION describes this lane -- reference metadata only, printed
    beside the numbers. Never used to include or exclude a row."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "code"))
        from api.services import narrator_data_inventory as inv  # type: ignore
        for lane in inv.DB_LANES:
            if lane.table == table:
                o = lane.owner
                detail = getattr(o, "column", "") or getattr(o, "parent_table", "") or ""
                return f"{type(o).__name__}({detail})" if detail else type(o).__name__
        return "(not a declared narrator lane)"
    except Exception:
        return "(declaration unavailable)"


def logical_key_for(table: str) -> Tuple[str, Tuple[str, ...], str]:
    """(kind, columns, justification). Absence from the registry is a VERDICT.

    Delegates to the shared registry so the comparator and the merge cannot disagree
    about what makes a row the same row.
    """
    return _xid.logical_key_for(table)


def _volatile(table: str) -> Dict[str, str]:
    return _xid.volatile_columns(table)


def _key_of(row: Dict[str, Any], cols: Tuple[str, ...]) -> str:
    return json.dumps([row.get(c) for c in cols], sort_keys=True, ensure_ascii=False, default=str)


def _content_of(row: Dict[str, Any], table: str, key_cols: Tuple[str, ...],
                drop_id: bool = False) -> Dict[str, Any]:
    vol = _volatile(table)
    out = {k: v for k, v in row.items() if k not in key_cols and k not in vol}
    if drop_id:
        out.pop("id", None)
    return out


def _content_hash(row, table, key_cols, drop_id=False) -> str:
    blob = json.dumps(_content_of(row, table, key_cols, drop_id), sort_keys=True,
                      ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _clip(v: Any, n: int = 160) -> Any:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + f"...(+{len(s)-n})"


# ══════════════════════════════════════════════════════════════════════
# Reading a package (read-only)
# ══════════════════════════════════════════════════════════════════════

def read_package(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"path": str(path), "sha256": "", "manifest": {}, "records": {},
                           "files": {}, "problems": []}
    out["sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for required in ("bagit.txt", MANIFEST_NAME, "manifest-sha256.txt"):
            if required not in names:
                out["problems"].append(f"{required} missing -- package structure incomplete")
        if MANIFEST_NAME in names:
            out["manifest"] = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        for n in sorted(names):
            if n.startswith(RECORDS_PREFIX) and n.endswith(".jsonl"):
                table = n[len(RECORDS_PREFIX):-len(".jsonl")]
                rows = []
                for i, line in enumerate(zf.read(n).decode("utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        out["problems"].append(f"{n}:{i} unreadable JSON ({e})")
                out["records"][table] = rows
        if "manifest-sha256.txt" in names:
            for line in zf.read("manifest-sha256.txt").decode("utf-8").splitlines():
                if not line.strip():
                    continue
                digest, _, member = line.partition(" ")
                member = member.strip()
                if member.startswith(FILES_PREFIX):
                    out["files"][member[len(FILES_PREFIX):]] = digest.strip()
    # the manifest's own declared counts vs what is actually in the records
    declared = out["manifest"].get("record_counts_by_lane") or {}
    for t, n in declared.items():
        actual = len(out["records"].get(t, []))
        if actual != n:
            out["problems"].append(f"manifest says {t}={n} but {actual} rows are packaged")
    return out


# ══════════════════════════════════════════════════════════════════════
# Comparison
# ══════════════════════════════════════════════════════════════════════

def compare_table(table: str, rows_a: List[Dict[str, Any]], rows_b: List[Dict[str, Any]]) -> Dict[str, Any]:
    kind, key_cols, why = logical_key_for(table)
    all_rows = rows_a + rows_b
    res: Dict[str, Any] = {
        "table": table,
        "physical_key": physical_key(all_rows),
        "ownership_path": ownership_path(table),
        "logical_key": list(key_cols),
        "logical_key_justification": why,
        "volatile_columns_excluded": _volatile(table),
        "count_a": len(rows_a), "count_b": len(rows_b),
        "verdict": KEYED if kind == KIND_DECLARED else NO_SAFE_KEY,
        "on_both_identical": 0, "on_both_conflicting": [],
        "only_a": [], "only_b": [],
        "duplicate_keys_a": [], "duplicate_keys_b": [],
        "shared_physical_ids": None,
        "multiset": None,
    }

    # Evidence reported for EVERY table, independent of the logical verdict: how many
    # physical ids appear on both sides. Strong evidence for the merge design to
    # weigh; never treated here as proof of identity.
    ida = {r["id"] for r in rows_a if "id" in r}
    idb = {r["id"] for r in rows_b if "id" in r}
    if ida and idb:
        res["shared_physical_ids"] = {
            "a": len(ida), "b": len(idb), "shared": len(ida & idb),
            "note": "evidence only: a shared physical id is not asserted here to mean the same record",
        }

    if kind == KIND_NO_KEY:
        # No defensible correspondence. Compare as canonical row MULTISETS, ignoring
        # the installation-local surrogate, and report under this table's own verdict
        # -- never as "conflicts", which would assert a pairing the evidence lacks.
        drop = "id" in (rows_a[0] if rows_a else rows_b[0] if rows_b else {})
        ha = Counter(_content_hash(r, table, (), drop_id=drop) for r in rows_a)
        hb = Counter(_content_hash(r, table, (), drop_id=drop) for r in rows_b)
        res["multiset"] = {
            "identical_content_rows_on_both": sum((ha & hb).values()),
            "content_only_in_a": sum((ha - hb).values()),
            "content_only_in_b": sum((hb - ha).values()),
            "surrogate_id_excluded_from_content": drop,
            "note": "similarity is NOT identity; no row-to-row correspondence was established",
        }
        res["on_both_identical"] = res["multiset"]["identical_content_rows_on_both"]
        return res

    def index(rows):
        d = defaultdict(list)
        for r in rows:
            d[_key_of(r, key_cols)].append(r)
        return d

    ia, ib = index(rows_a), index(rows_b)
    res["duplicate_keys_a"] = [{"key": json.loads(k), "n": len(v)} for k, v in ia.items() if len(v) > 1]
    res["duplicate_keys_b"] = [{"key": json.loads(k), "n": len(v)} for k, v in ib.items() if len(v) > 1]
    for k in sorted(set(ia) - set(ib)):
        res["only_a"].append({"verdict": ONLY_A, "key": json.loads(k)})
    for k in sorted(set(ib) - set(ia)):
        res["only_b"].append({"verdict": ONLY_B, "key": json.loads(k)})

    for k in sorted(set(ia) & set(ib)):
        ra, rb = ia[k][0], ib[k][0]
        # `id` is excluded from content: for these tables it is an independently
        # minted per-installation surrogate, and a differing id is not a content
        # conflict -- it is a remap input, recorded below.
        if _content_hash(ra, table, key_cols, drop_id=True) == _content_hash(rb, table, key_cols, drop_id=True):
            res["on_both_identical"] += 1
            continue
        ca = _content_of(ra, table, key_cols, drop_id=True)
        cb = _content_of(rb, table, key_cols, drop_id=True)
        cols = sorted(c for c in set(ca) | set(cb) if ca.get(c) != cb.get(c))
        res["on_both_conflicting"].append({
            "verdict": SAME_DIFF, "key": json.loads(k), "columns": cols,
            "a": {c: _clip(ca.get(c)) for c in cols},
            "b": {c: _clip(cb.get(c)) for c in cols},
            "surrogate_id_a": ra.get("id"), "surrogate_id_b": rb.get("id"),
        })
    return res


def surrogate_collisions(table: str, rows_a, rows_b) -> Dict[str, Any]:
    """Where the SAME installation-local integer identifies DIFFERENT content."""
    ids_a = {r["id"]: r for r in rows_a if _looks_integer_surrogate(r.get("id"))}
    ids_b = {r["id"]: r for r in rows_b if _looks_integer_surrogate(r.get("id"))}
    if not ids_a or not ids_b:
        return {}
    shared = sorted(set(ids_a) & set(ids_b), key=lambda x: int(x))
    same, different = 0, []
    for i in shared:
        if _content_hash(ids_a[i], table, ("id",)) == _content_hash(ids_b[i], table, ("id",)):
            same += 1
        else:
            different.append(int(i))
    refs = SURROGATE_REFERENCES.get(f"{table}.id", [])
    return {
        "table": table, "surrogate": f"{table}.id",
        "ids_a": len(ids_a), "ids_b": len(ids_b), "shared_ids": len(shared),
        "shared_id_same_content": same, "shared_id_DIFFERENT_content": len(different),
        "colliding_ids_sample": different[:40],
        "verdict": (PHYSICAL_COLLISION if different else
                    ("no shared physical ids" if not shared else "shared physical ids, same content")),
        "remap_required": bool(different),
        "reference_closure": refs,
        "reference_closure_note": (
            "every reference above must be rewritten consistently with any remap. "
            "STRING-EMBEDDED references are NOT visible to a foreign-key graph walk."
        ) if refs else "no references to this surrogate in the discovered closure",
    }


def turnrow_reference_audit(pa, pb) -> Dict[str, Any]:
    """`turn_key` is literally 'turnrow:<turns.id>' (0038:62). It looks like a stable
    key and is installation-local. Measured on both sides so the remap closure is a
    fact rather than a reading of the migration."""
    def scan(p):
        found = Counter()
        for t in ("turn_extraction_ledger", "turn_extraction_results"):
            for r in p["records"].get(t, []):
                m = TURNROW_RX.match(str(r.get("turn_key", "")))
                if m:
                    found[t] += 1
        return found
    fa, fb = scan(pa), scan(pb)
    return {
        "pattern": "turnrow:<turns.id>",
        "a": dict(fa), "b": dict(fb),
        "total": sum(fa.values()) + sum(fb.values()),
        "implication": ("these TEXT values embed an installation-local integer; a turns.id "
                        "remap must parse and rebuild them. An FK walk cannot see them."),
    }


def reference_integrity_audit(p: Dict[str, Any]) -> Dict[str, Any]:
    """Does every reference to `turns.id` inside ONE package resolve inside that
    same package?

    This tests the exporter's own §30 guarantee -- "refuse, never dangle" -- across
    the FULL reference set rather than the declared subset. A dangling value in an
    UNDECLARED column would mean a package that restores into a clean root and looks
    healthy to `PRAGMA foreign_key_check` while a story or a bio fact points at a turn
    that is not there. Read-only, and a finding either way."""
    turn_ids = {int(r["id"]) for r in p["records"].get("turns", []) if _looks_integer_surrogate(r.get("id"))}
    out = {"packaged_turn_ids": len(turn_ids), "checks": [], "total_dangling": 0}
    for ref in SURROGATE_REFERENCES["turns.id"]:
        rows = p["records"].get(ref["table"], [])
        seen = dangling = 0
        samples: List[Any] = []
        for r in rows:
            vals: List[Optional[int]] = []
            if ref["form"].startswith("INTEGER"):
                v = r.get(ref["column"])
                if _looks_integer_surrogate(v):
                    vals = [int(v)]
            elif ref["form"].startswith("TEXT"):
                m = TURNROW_RX.match(str(r.get(ref["column"], "")))
                if m:
                    vals = [int(m.group(1))]
            else:  # JSON payload
                try:
                    blob = json.loads(r.get(ref["column"]) or "{}")
                    m = TURNROW_RX.match(str(blob.get("turn_key", "")))
                    if m:
                        vals = [int(m.group(1))]
                except Exception:
                    vals = []
            for v in vals:
                seen += 1
                if v not in turn_ids:
                    dangling += 1
                    if len(samples) < 10:
                        samples.append({"row_id": r.get("id"), "value": v})
        rec = dict(ref)
        rec.update({"rows_in_package": len(rows), "references_found": seen,
                    "dangling": dangling, "dangling_samples": samples})
        validate_reference_record(rec, audit=True)
        out["checks"].append(rec)
        out["total_dangling"] += dangling
    out["verdict"] = ("all turn references resolve inside the package"
                      if out["total_dangling"] == 0 else
                      "DANGLING TURN REFERENCES -- a restored root would be internally inconsistent")
    return out


def compare_files(files_a: Dict[str, str], files_b: Dict[str, str]) -> Dict[str, Any]:
    both = set(files_a) & set(files_b)
    same = sorted(p for p in both if files_a[p] == files_b[p])
    diff = sorted(p for p in both if files_a[p] != files_b[p])
    only_a, only_b = set(files_a) - set(files_b), set(files_b) - set(files_a)
    # identical bytes living at different paths: a dedupe opportunity, not a conflict
    by_hash_a = defaultdict(list)
    for p, h in files_a.items():
        by_hash_a[h].append(p)
    cross = []
    for p in sorted(only_b):
        h = files_b[p]
        if h in by_hash_a:
            cross.append({"b_path": p, "a_paths": by_hash_a[h], "sha256": h})
    return {
        "verdict_vocabulary": [FILE_SAME, FILE_DIFF, FILE_ONLY_A, FILE_ONLY_B],
        "count_a": len(files_a), "count_b": len(files_b),
        "same_path_same_hash": len(same),
        "same_path_DIFFERENT_hash": len(diff),
        "same_path_different_hash_paths": diff[:80],
        "only_a_count": len(only_a), "only_b_count": len(only_b),
        "only_a": sorted(only_a)[:200], "only_b": sorted(only_b)[:200],
        "identical_bytes_at_different_paths": cross[:60],
        "hash_source": "the bag's own manifest-sha256.txt, which BagIt validated; nothing re-hashed",
    }


def compare_packages(pa, pb, label_a: str, label_b: str) -> Dict[str, Any]:
    ma, mb = pa["manifest"], pb["manifest"]
    tables = sorted(set(pa["records"]) | set(pb["records"]))
    per_table, collisions = [], []
    for t in tables:
        ra, rb = pa["records"].get(t, []), pb["records"].get(t, [])
        if not ra and not rb:
            continue
        per_table.append(compare_table(t, ra, rb))
        c = surrogate_collisions(t, ra, rb)
        if c:
            collisions.append(c)
    same_narrator = ma.get("narrator_id") == mb.get("narrator_id")
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True,
        "tool": "scripts/two_origin_compare.py",
        "origins": {
            lbl: {"path": p["path"], "package_sha256": p["sha256"],
                  "package_id": m.get("package_id"), "narrator_id": m.get("narrator_id"),
                  "narrator_display_name": m.get("narrator_display_name"),
                  "created_at": m.get("created_at"), "source_commit": m.get("source_commit"),
                  "schema_fingerprint": m.get("source_schema_fingerprint"),
                  "integrity_problems": p["problems"]}
            for lbl, p, m in ((label_a, pa, ma), (label_b, pb, mb))
        },
        "same_narrator_id": same_narrator,
        "identity_note": ("Both packages name the same narrator_id."
                          if same_narrator else
                          "DIFFERENT narrator_id: these are not the same narrator RECORD. Whether "
                          "they are the same PERSON is an identity question this tool does not "
                          "answer and must not be assumed."),
        "tables": per_table,
        "surrogate_id_collisions": collisions,
        "turnrow_string_references": turnrow_reference_audit(pa, pb),
        "reference_integrity": {label_a: reference_integrity_audit(pa),
                                label_b: reference_integrity_audit(pb)},
        "remap_closure_for_turns_id": SURROGATE_REFERENCES["turns.id"],
        "closure_parity_for_turns_id": closure_parity("turns.id"),
        "files": compare_files(pa["files"], pb["files"]),
        "installation_dependencies": {label_a: ma.get("installation_dependencies") or {},
                                      label_b: mb.get("installation_dependencies") or {}},
        "external_person_dependencies": {label_a: ma.get("external_person_dependencies") or {},
                                         label_b: mb.get("external_person_dependencies") or {}},
    }


# ══════════════════════════════════════════════════════════════════════
# Markdown summary -- aggregate first, bounded examples second
# ══════════════════════════════════════════════════════════════════════

def summarize(rep: Dict[str, Any], label_a: str, label_b: str) -> str:
    oa, ob = rep["origins"][label_a], rep["origins"][label_b]
    L: List[str] = []
    ap = L.append
    ap(f"# Two-origin comparison — {oa['narrator_display_name']}")
    ap("")
    ap(f"*Read-only. No package, database or narrator was modified. Generated {rep['generated_at']}.*")
    ap("")
    ap(f"| | {label_a} | {label_b} |")
    ap("|---|---|---|")
    ap(f"| narrator_id | `{oa['narrator_id']}` | `{ob['narrator_id']}` |")
    ap(f"| package | `{oa['package_id']}` | `{ob['package_id']}` |")
    ap(f"| created | {oa['created_at']} | {ob['created_at']} |")
    ap(f"| source commit | `{oa['source_commit']}` | `{ob['source_commit']}` |")
    ap(f"| package sha256 | `{oa['package_sha256'][:16]}…` | `{ob['package_sha256'][:16]}…` |")
    ap("")
    ap(f"**{rep['identity_note']}**")
    ap("")
    for lbl in (label_a, label_b):
        for p in rep["origins"][lbl]["integrity_problems"]:
            ap(f"- ⚠ **{lbl} integrity**: {p}")
    ap("")

    ap("## Key model")
    ap("")
    ap("Physical key, ownership path and cross-origin logical key are three different")
    ap("things. A row verdict is only as good as the logical key behind it.")
    ap("")
    ap("| table | physical key | ownership | logical key | justification |")
    ap("|---|---|---|---|---|")
    for t in rep["tables"]:
        lk = "`" + ",".join(t["logical_key"]) + "`" if t["logical_key"] else "**none**"
        ap(f"| `{t['table']}` | {t['physical_key']} | {t['ownership_path']} | {lk} | {t['logical_key_justification'][:90]} |")
    ap("")

    keyed = [t for t in rep["tables"] if t["verdict"] == KEYED]
    nokey = [t for t in rep["tables"] if t["verdict"] == NO_SAFE_KEY]

    ap("## Keyed tables — row correspondence established")
    ap("")
    ap(f"| table | {label_a} | {label_b} | same | **differing** | only {label_a} | only {label_b} |")
    ap("|---|---|---|---|---|---|---|")
    tot = Counter()
    for t in keyed:
        tot["same"] += t["on_both_identical"]; tot["diff"] += len(t["on_both_conflicting"])
        tot["a"] += len(t["only_a"]); tot["b"] += len(t["only_b"])
        ap(f"| `{t['table']}` | {t['count_a']} | {t['count_b']} | {t['on_both_identical']} | "
           f"**{len(t['on_both_conflicting'])}** | {len(t['only_a'])} | {len(t['only_b'])} |")
    ap(f"| **total** | | | {tot['same']} | **{tot['diff']}** | {tot['a']} | {tot['b']} |")
    ap("")

    ap("## No safe cross-origin key — correspondence NOT established")
    ap("")
    ap("Compared as canonical row multisets with the installation-local surrogate excluded.")
    ap("Similarity is not identity: these rows **must not be auto-merged by pairing**.")
    ap("")
    ap(f"| table | {label_a} | {label_b} | identical content | content only {label_a} | content only {label_b} | shared physical ids |")
    ap("|---|---|---|---|---|---|---|")
    for t in nokey:
        m = t["multiset"] or {}
        sp = t["shared_physical_ids"]
        ap(f"| `{t['table']}` | {t['count_a']} | {t['count_b']} | {m.get('identical_content_rows_on_both', 0)} | "
           f"{m.get('content_only_in_a', 0)} | {m.get('content_only_in_b', 0)} | "
           f"{sp['shared'] if sp else '—'} |")
    ap("")

    conf = [t for t in keyed if t["on_both_conflicting"]]
    if conf:
        ap("## Same logical record, different content — every one needs a merge policy")
        ap("")
        for t in conf:
            ap(f"### `{t['table']}` ({len(t['on_both_conflicting'])})")
            ap("")
            for c in t["on_both_conflicting"][:8]:
                ap(f"- key `{json.dumps(c['key'], ensure_ascii=False)}` — columns: {', '.join(c['columns'])}")
                for col in c["columns"][:4]:
                    ap(f"    - {label_a}: `{c['a'].get(col)}`")
                    ap(f"    - {label_b}: `{c['b'].get(col)}`")
            if len(t["on_both_conflicting"]) > 8:
                ap(f"- …and {len(t['on_both_conflicting']) - 8} more (complete detail in report.json)")
            ap("")

    dups = [t for t in keyed if t["duplicate_keys_a"] or t["duplicate_keys_b"]]
    if dups:
        ap("## Duplicate logical keys within one origin")
        ap("")
        ap("A naive union would multiply these. BACKLOG §5 (`questionnaire_put`) is the known cause.")
        ap("")
        for t in dups:
            ap(f"- `{t['table']}`: {label_a} {len(t['duplicate_keys_a'])}, {label_b} {len(t['duplicate_keys_b'])}")
        ap("")

    ap("## Installation-local surrogate ids")
    ap("")
    any_remap = False
    for c in rep["surrogate_id_collisions"]:
        ap(f"### `{c['surrogate']}` — {c['verdict']}")
        ap("")
        ap(f"- {label_a} ids: {c['ids_a']} · {label_b} ids: {c['ids_b']} · shared: {c['shared_ids']}")
        ap(f"- shared id, same content: {c['shared_id_same_content']}")
        ap(f"- **shared id, DIFFERENT content: {c['shared_id_DIFFERENT_content']}**")
        if c["remap_required"]:
            any_remap = True
            ap(f"- colliding ids (sample): `{c['colliding_ids_sample']}`")
        if c["reference_closure"]:
            ap("- references that must be rewritten with any remap:")
            for r in c["reference_closure"]:
                validate_reference_record(r)
                ap(f"    - `{r['table']}.{r['column']}` — {r['form']} ({r['cite']})")
        ap("")
    tr = rep["turnrow_string_references"]
    ap(f"**String-embedded turn references** (`{tr['pattern']}`): {label_a} {tr['a']}, {label_b} {tr['b']}. "
       f"{tr['implication']}")
    ap("")

    ap("### Remap closure for `turns.id` — every place the local integer is stored")
    ap("")
    ap("Built by reading the shipped migrations and writers. A `PRAGMA foreign_key_list`")
    ap("walk finds **none of these seven** — no migration declares `REFERENCES turns`,")
    ap("so the bare INTEGER columns, the TEXT keys and the JSON field are all invisible")
    ap("to SQLite. That is why `PRAGMA foreign_key_check` passing says nothing about")
    ap("whether a merged root is sound, and why Merge/Remap owes a semantic validator.")
    ap("")
    ap("`declared by` is read from the LIVE production declaration at run time, never")
    ap("restated here, so this column cannot go stale against the exporter.")
    ap("")
    ap("| where stored | form | declared by | requires rewrite | source |")
    ap("|---|---|---|---|---|")
    for r in rep["remap_closure_for_turns_id"]:
        validate_reference_record(r)
        d = r["declared_by"] if r["declared"] else f"**{DECLARED_BY_NOTHING}**"
        ap(f"| `{r['table']}.{r['column']}` | {r['form']} | {d} | "
           f"{'yes' if r['requires_rewrite'] else 'no'} | {r['cite']} |")
    ap("")

    cp = rep["closure_parity_for_turns_id"]
    ap("#### Closure parity — independent evidence vs the production declaration")
    ap("")
    ap("The seven sites above were found by reading migrations and writers. The set below")
    ap("is what `narrator_data_inventory` declares. They are derived SEPARATELY and then")
    ap("compared: a site found here but undeclared is an **export gap** (§30 does not check")
    ap("it); a site declared but missing here is **evidence drift** (a remap built from this")
    ap("closure would leave it unrewritten).")
    ap("")
    ap(f"- independently discovered (excluding real SQL FKs): **{cp['discovered_count']}**")
    ap(f"- declared by `COLUMN_ONLY_REFERENCES` + `ENCODED_REFERENCES`: **{cp['declared_count']}**")
    if cp["in_parity"]:
        ap(f"- **PARITY — the two sets are identical.**")
    else:
        for t, c in cp["discovered_not_declared"]:
            ap(f"- ⚠ **EXPORT GAP** — `{t}.{c}` is stored but not declared")
        for t, c in cp["declared_not_discovered"]:
            ap(f"- ⚠ **EVIDENCE DRIFT** — `{t}.{c}` is declared but absent from this closure")
    ap("")

    ap("### Reference integrity inside each package")
    ap("")
    ap("Does every stored turn reference resolve inside the same package? This tests the")
    ap("exporter's own §30 'refuse, never dangle' guarantee across the FULL reference set,")
    ap("not just the declared subset.")
    ap("")
    for lbl in (label_a, label_b):
        ri = rep["reference_integrity"][lbl]
        ap(f"**{lbl}** — {ri['packaged_turn_ids']} packaged turn ids — {ri['verdict']}")
        ap("")
        rows = [c for c in ri["checks"] if c["references_found"] or c["dangling"]]
        if not rows:
            ap("*No stored turn references of any form in this package — nothing to rewrite.*")
        else:
            ap("| reference | declared by | form | refs found | dangling |")
            ap("|---|---|---|---|---|")
            for c in rows:
                ap(f"| `{c['table']}.{c['column']}` "
                   f"| {c['declared_by'] if c['declared'] else '**' + DECLARED_BY_NOTHING + '**'} "
                   f"| {c['form']} | {c['references_found']} "
                   f"| {'**' + str(c['dangling']) + '**' if c['dangling'] else 0} |")
        ap("")

    f = rep["files"]
    ap("## Files")
    ap("")
    ap(f"| | count |")
    ap("|---|---|")
    ap(f"| {label_a} | {f['count_a']} |")
    ap(f"| {label_b} | {f['count_b']} |")
    ap(f"| {FILE_SAME} | {f['same_path_same_hash']} |")
    ap(f"| **{FILE_DIFF}** | **{f['same_path_DIFFERENT_hash']}** |")
    ap(f"| {FILE_ONLY_A} | {f['only_a_count']} |")
    ap(f"| {FILE_ONLY_B} | {f['only_b_count']} |")
    ap("")
    for p in f["same_path_different_hash_paths"][:20]:
        ap(f"- ⚠ same path, different bytes: `{p}`")
    if f["identical_bytes_at_different_paths"]:
        ap(f"- {len(f['identical_bytes_at_different_paths'])} file(s) hold identical bytes at different paths (dedupe opportunity, not a conflict)")
    ap("")

    ap("## What this means for Merge/Remap")
    ap("")
    ap(f"- **Safe union (one origin only):** {tot['a']} keyed rows from {label_a}, {tot['b']} from {label_b}, "
       f"plus {f['only_a_count']} and {f['only_b_count']} files.")
    ap(f"- **Represent once (identical):** {tot['same']} keyed rows, {f['same_path_same_hash']} files.")
    ap(f"- **Needs an explicit policy (same key, different content):** {tot['diff']} rows"
       f"{', ' + str(f['same_path_DIFFERENT_hash']) + ' files' if f['same_path_DIFFERENT_hash'] else ''}.")
    ap(f"- **Must not be auto-merged by pairing:** {len(nokey)} tables have no defensible cross-origin key.")
    ap(f"- **Remap required:** {'YES' if any_remap else 'no colliding surrogate ids measured'}.")
    ap("")
    ap("*This is evidence for designing Multi-Origin Merge/Remap. It is not a merge, and no")
    ap("merge rule is implied by any number above.*")
    return "\n".join(L)


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap_.add_argument("--a", required=True)
    ap_.add_argument("--b", required=True)
    ap_.add_argument("--label-a", default="A")
    ap_.add_argument("--label-b", default="B")
    ap_.add_argument("--out", default=".runtime/two_origin/reports")
    ap_.add_argument("--quiet", action="store_true")
    args = ap_.parse_args(argv)

    pa, pb = read_package(Path(args.a)), read_package(Path(args.b))
    rep = compare_packages(pa, pb, args.label_a, args.label_b)
    md = summarize(rep, args.label_a, args.label_b)

    name = (rep["origins"][args.label_a]["narrator_display_name"] or "narrator").replace(" ", "_")
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"{name}-{args.label_a}-vs-{args.label_b}-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (outdir / "summary.md").write_text(md + "\n", encoding="utf-8")

    # read-only proof: the inputs are byte-identical after the run
    after_a = hashlib.sha256(Path(args.a).read_bytes()).hexdigest()
    after_b = hashlib.sha256(Path(args.b).read_bytes()).hexdigest()
    ok = (after_a == pa["sha256"]) and (after_b == pb["sha256"])
    (outdir / "readonly-proof.txt").write_text(
        f"{args.label_a} before {pa['sha256']}\n{args.label_a} after  {after_a}\n"
        f"{args.label_b} before {pb['sha256']}\n{args.label_b} after  {after_b}\n"
        f"byte-identical: {ok}\n", encoding="utf-8")

    if not args.quiet:
        print(md)
    print(f"\nwritten: {outdir}")
    print(f"read-only proof: inputs byte-identical after the run = {ok}")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
