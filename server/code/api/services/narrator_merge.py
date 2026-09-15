"""Multi-Origin Merge/Remap — THE PLANNER. Writes nothing, anywhere, ever.

WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01, implementation block 1.

Given the same narrator packaged independently from two installations, decide what a
merged root WOULD contain: which rows carry across, which physical ids must be
reallocated, every reference that must be rewritten with them, and every conflict a
human has to settle. **This module opens no database, writes no file and creates no
root.** Producing the plan and executing it are separate steps on purpose — acceptance
§6.3 is that the dry run writes nothing and that its plan matches what the real run
then does, and a planner that cannot write cannot fail that clause by accident.

WHAT THIS MODULE REFUSES TO DO, by construction:
  * choose a winner for any conflict (§4: V1 refuses, it does not resolve);
  * pair two rows in a NO_SAFE_CROSS_ORIGIN_KEY table (that verdict means
    correspondence could not be PROVEN, never that the rows are duplicates);
  * infer identity from equal integers, UUID syntax, timestamps or similar content;
  * modify, normalise, re-zip or delete a source package.

━━━ A PHYSICAL ID COLLISION IS NOT AN INTEGER PROBLEM ━━━━━━━━━━━━━━━━
The first draft of this module remapped only the three installation-local INTEGER
surrogates, on the assumption that a TEXT/UUID primary key cannot collide across
installations. **The real Christopher comparison disproves that on its own evidence:**
`graph_persons` is NO_SAFE_CROSS_ORIGIN_KEY, holds 1 desktop row against 14 laptop
rows, and reports **one shared physical id with non-identical content** — because the
product mints graph-person ids deterministically from narrator + name, so two
installations that met the same relative independently mint the same id for different
rows. Two such rows cannot both be inserted under one `TEXT PRIMARY KEY`.

So the collision hunt runs over **every packaged table**, comparing the actual values of
whatever the schema declares as the primary key, and the remap is type-agnostic:

  INTEGER surrogates in `REMAP_TARGETS`   renumbered UNIFORMLY (see `plan_remap`)
  every other colliding physical id       reallocated ONLY where it collides,
                                          deterministically, as a uuid5

The two policies differ deliberately. A `turns.id` is a private counter nobody outside
the installation can mean anything by, so renumbering all of them costs nothing and
keeps the rewrite on one exercised path. A TEXT id may itself be meaningful — the
deterministic graph-person id IS the product's own equality rule — and churning every
one of them would leave a merged root whose ids match neither origin, for no benefit.

**An id collision in a table whose reference closure has not been ESTABLISHED is a
refusal, not a guess** (`CLOSURE_ESTABLISHED`). Remapping a row whose children we
cannot enumerate would silently orphan them.

**And equal bytes never make a shared id safe in a no-safe-key table.** Whether a
collision may be left alone depends on what the TABLE can prove, not on whether the rows
match — see `find_physical_collisions`, which is where that distinction lives and where
the first implementation got it wrong.

━━━ WHEN IS A DIFFERENT REFERENCE "THE SAME"? ━━━━━━━━━━━━━━━━━━━━━━━
Only when both references resolve to the SAME MERGED ROW. This module's first draft
normalised every reference to a sentinel before comparing content, so that two origins
citing "their own copy" of a conversation would not be reported as a conflict. That was
wrong, and dangerously so: `turns` has no defensible cross-origin key by design, so
desktop turn 17 and laptop turn 84 have never been shown to be the same evidence, and
blanking both citations would have declared two facts identical on the strength of a
correspondence nobody proved — the exact "similarity becomes identity" failure this WO
exists to prevent.

The fix is to classify rows AFTER the remap, on the remapped values. Two references are
then equal if and only if they point at the same merged row, which is precisely the
condition under which ignoring the difference is safe. Where the parent genuinely
corresponds across origins the ids converge and the difference disappears; where it
does not, the difference survives and is reported.

━━━ WHERE THE REFERENCE CLOSURE COMES FROM ━━━━━━━━━━━━━━━━━━━━━━━━━━━
From `narrator_data_inventory` — the SAME production declaration the exporter, restore
validation and the two-origin comparator consume. A fifth private copy of that list is
how the fourth one went stale. Only real SQL foreign keys are named locally, in
`SQL_FK_REFERENCES`, because SQLite declares those and the inventory deliberately does
not: `COLUMN_ONLY_REFERENCES` exists for references the schema does NOT declare.

Independence is preserved where it does work: `scripts/two_origin_compare.py` keeps its
own closure, discovered by reading migrations and writers, and `tests/test_narrator_merge.py`
holds the two against each other and re-derives `SQL_FK_REFERENCES` from the shipped
schema. Deriving BOTH from the declaration would make those checks tautological.
"""
from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import cross_origin_identity as xid
from . import narrator_data_inventory as inv
from . import narrator_package

MANIFEST_NAME = "lorevox-manifest.json"
RECORDS_PREFIX = "data/records/"
FILES_PREFIX = "data/files/"
HASH_MANIFEST = "manifest-sha256.txt"

#: Stable namespace for reallocated TEXT ids. Frozen: changing it changes every
#: reallocated id the merge would produce, which breaks determinism across versions.
REMAP_NAMESPACE = uuid.UUID("6f2d1f48-0c1e-4a3b-9f07-2b7c5a1d8e33")

#: Physical primary key per table, where it is NOT a single `id` column. Empty today:
#: every narrator-owned lane in the shipped schema keys on `id`, and no table anywhere
#: uses a composite `PRIMARY KEY (a, b)` — both measured 2026-09-14 and pinned by test.
#: The map exists so a future lane cannot bypass the collision hunt by naming its key
#: something else; the test fails first and the fix is an entry here.
PHYSICAL_KEYS: Dict[str, Tuple[str, ...]] = {}

#: The installation-local INTEGER surrogates, renumbered uniformly. Established by the
#: §3d closure hunt; `test_remap_targets_cover_every_narrator_owned_integer_surrogate`
#: pins that no narrator-owned lane grows a fourth without this list being updated.
REMAP_TARGETS: Tuple[str, ...] = (
    "turns.id",
    "turn_extraction_ledger.id",
    "turn_extraction_results.id",
)

#: Real SQL foreign keys into a remappable parent. Named here because SQLite declares
#: them and `narrator_data_inventory.COLUMN_ONLY_REFERENCES` — whose whole purpose is
#: references the schema does NOT declare — correctly omits them. Reading only the
#: inventory would leave these joins unrewritten.
#: (table, column, parent_table, parent_key, cite)
SQL_FK_REFERENCES: Tuple[Tuple[str, str, str, str, str], ...] = (
    ("turn_extraction_results", "ledger_id", "turn_extraction_ledger", "id",
     "0041:67-68 REFERENCES turn_extraction_ledger(id) ON DELETE CASCADE"),
    ("graph_relationships", "from_person_id", "graph_persons", "id",
     "db.py:7422 FOREIGN KEY(from_person_id) REFERENCES graph_persons(id) ON DELETE CASCADE"),
    ("graph_relationships", "to_person_id", "graph_persons", "id",
     "db.py:7423 FOREIGN KEY(to_person_id) REFERENCES graph_persons(id) ON DELETE CASCADE"),
)

#: Parents whose reference closure has been ESTABLISHED by reading the schema and the
#: writers, with the evidence. An EMPTY closure is a finding, not an absence — which is
#: why this is a separate declaration from `reference_sites()` returning nothing: those
#: two states are indistinguishable otherwise, and treating "unknown" as "no children"
#: is how a remap silently orphans rows.
CLOSURE_ESTABLISHED: Dict[str, str] = {
    "turns.id":
        "§3d: seven sites — 4 INTEGER columns, 2 TEXT 'turnrow:' keys, 1 JSON field",
    "turn_extraction_ledger.id":
        "§3d: one site, turn_extraction_results.ledger_id (real SQL FK, 0041:67-68)",
    "turn_extraction_results.id":
        "§3d: ZERO references — measured across migrations, db.py, routers, services, "
        "scripts, tests and ui/js, not inferred from an absence of FKs",
    "graph_persons.id":
        "db.py:7421-7423: graph_relationships.from_person_id and .to_person_id, both "
        "real table-level FOREIGN KEY clauses ON DELETE CASCADE",
}

# ── file policy from spec §3b, decided from code rather than filenames ─
#: Derived and fully regenerable from the merged `sessions/*/meta.json`
#: (`archive.py:1217-1224` writes only fields already in `meta.json`, `:90-96`).
REGENERABLE_FILE_SUFFIXES: Tuple[str, ...] = ("/index.json",)

# ── refusal reason codes ──────────────────────────────────────────────
R_PACKAGE_INTEGRITY = "package_integrity"
R_DIFFERENT_NARRATORS = "different_narrators"
R_SAME_KEY_DIFFERENT_CONTENT = "same_logical_record_different_content"
R_FILE_PATH_DIFFERENT_BYTES = "file_path_different_bytes"
R_UNKNOWN_ENCODED_FORM = "encoded_reference_form_not_in_closure"
R_MALFORMED_ENCODED_REFERENCE = "malformed_encoded_reference"
R_UNKNOWN_COLLISION_CLOSURE = "physical_id_collision_in_table_with_unestablished_closure"


class MergeRefused(Exception):
    """A refusal is a result. It names the reason and writes nothing."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class Origin:
    """One package, read into memory. Never mutated after load."""
    label: str
    path: Path
    package_id: str
    sha256: str
    narrator_id: str
    manifest: Dict[str, Any]
    records: Dict[str, List[Dict[str, Any]]]
    files: Dict[str, str]          # narrator-relative path -> sha256

    @property
    def rank_key(self) -> Tuple[str, str]:
        """Deterministic ordering that depends on neither argument order nor a label
        the caller chose. Same two packages, same order, every run."""
        return (self.package_id or "", self.label or "")


@dataclass
class ReferenceSite:
    table: str
    column: str
    parent: str                    # '<table>.<key>'
    form: str                      # 'integer' | 'text_prefixed' | 'json_field'
    declared_by: str
    cite: str
    encoded: Optional[inv.EncodedRef] = None


@dataclass
class MergePlan:
    narrator_id: str
    origins: List[Dict[str, str]]
    #: parent ('<table>.<col>') -> origin label -> old id -> new id
    remap: Dict[str, Dict[str, Dict[Any, Any]]]
    remap_rows: int
    physical_collisions: List[Dict[str, Any]]
    reference_rewrites: List[Dict[str, Any]]
    carried_rows: Dict[str, int]
    #: The rows a real run would insert, already remapped and rewritten, each carrying
    #: `_origin` and `_origin_package` (§5 provenance). In memory only — the planner has
    #: no writer, and an executor built on it must strip the two underscore keys before
    #: they reach a column.
    merged_records: Dict[str, List[Dict[str, Any]]]
    keyed_verdicts: List[Dict[str, Any]]
    no_safe_key_tables: List[str]
    files_union: List[Dict[str, str]]
    files_regenerate: List[str]
    refusals: List[Dict[str, str]]
    dangling_after_rewrite: List[Dict[str, Any]]
    wrote_anything: bool = False

    @property
    def refused(self) -> bool:
        return bool(self.refusals) or bool(self.dangling_after_rewrite)


# ══════════════════════════════════════════════════════════════════════
# Reading a package
# ══════════════════════════════════════════════════════════════════════

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_origin(zip_path: Path, label: str) -> Origin:
    """Read one package into memory. READ ONLY.

    Integrity is delegated to the shipped validator rather than re-implemented, so a
    package this module accepts is one the product already accepts.
    """
    zip_path = Path(zip_path)
    try:
        report = narrator_package.validate_package(zip_path)
    except Exception as exc:                      # not a zip, unreadable, truncated…
        raise MergeRefused(R_PACKAGE_INTEGRITY, f"{zip_path.name}: {exc}") from exc
    if not report.ok:
        raise MergeRefused(R_PACKAGE_INTEGRITY,
                           f"{zip_path.name}: {'; '.join(report.problems)[:400]}")

    records: Dict[str, List[Dict[str, Any]]] = {}
    files: Dict[str, str] = {}
    manifest: Dict[str, Any] = {}

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for name in names:
            if name.endswith(MANIFEST_NAME):
                manifest = json.loads(zf.read(name).decode("utf-8"))
                break
        for name in names:
            idx = name.find(RECORDS_PREFIX)
            if idx >= 0 and name.endswith(".jsonl"):
                table = name[idx + len(RECORDS_PREFIX):-len(".jsonl")]
                rows = [json.loads(line) for line in
                        zf.read(name).decode("utf-8").splitlines() if line.strip()]
                if rows:
                    records[table] = rows
        for name in names:
            if name.endswith(HASH_MANIFEST):
                for line in zf.read(name).decode("utf-8").splitlines():
                    parts = line.split(maxsplit=1)
                    if len(parts) != 2:
                        continue
                    digest, member = parts[0].strip(), parts[1].strip()
                    pos = member.find(FILES_PREFIX)
                    if pos >= 0:
                        files[member[pos + len(FILES_PREFIX):]] = digest
                break

    return Origin(label=label, path=zip_path,
                  package_id=str(manifest.get("package_id") or ""),
                  sha256=_sha256_file(zip_path),
                  narrator_id=str(manifest.get("narrator_id") or ""),
                  manifest=manifest, records=records, files=files)


# ══════════════════════════════════════════════════════════════════════
# The reference closure, consumed from the production declaration
# ══════════════════════════════════════════════════════════════════════

def reference_sites(parent: str) -> List[ReferenceSite]:
    """Every place `parent` ('<table>.<key>') is referenced, per PRODUCTION.

    Three mechanisms, and reading fewer than three is how a rewrite goes silently
    incomplete: `COLUMN_ONLY_REFERENCES` (bare columns SQLite cannot declare),
    `ENCODED_REFERENCES` (TEXT and JSON forms an FK walk cannot see), and the real SQL
    foreign keys in `SQL_FK_REFERENCES`.
    """
    parent_table, _, parent_key = parent.partition(".")
    parent_key = parent_key or "id"
    sites: List[ReferenceSite] = []
    for cr in inv.COLUMN_ONLY_REFERENCES:
        if cr.parent_table == parent_table and cr.parent_key == parent_key:
            sites.append(ReferenceSite(cr.table, cr.column, parent, "integer",
                                       "COLUMN_ONLY_REFERENCES", "narrator_data_inventory"))
    for er in inv.ENCODED_REFERENCES:
        if er.parent_table == parent_table and er.parent_key == parent_key:
            sites.append(ReferenceSite(er.table, er.column, parent, er.form,
                                       "ENCODED_REFERENCES", er.cite, encoded=er))
    for table, column, ptable, pkey, cite in SQL_FK_REFERENCES:
        if ptable == parent_table and pkey == parent_key:
            sites.append(ReferenceSite(table, column, parent, "integer",
                                       "SQL FOREIGN KEY", cite))
    return sites


def render_encoded(ref: inv.EncodedRef, raw: Any, new_id: Any) -> Any:
    """Rebuild an encoded reference around `new_id`, preserving everything else.

    The INVERSE of `ref.parse`, built from the declaration's own `prefix` / `json_key`
    rather than a literal here — the grammar has one home. The test proves the inverse
    property by feeding every render back through the PRODUCTION parser.
    """
    if ref.form == inv.FORM_JSON_FIELD:
        text = "" if raw is None else str(raw).strip()
        blob = json.loads(text) if text and text not in ("{}", "null") else {}
        if not isinstance(blob, dict):
            raise MergeRefused(R_MALFORMED_ENCODED_REFERENCE,
                               f"{ref.table}.{ref.column} is not a JSON object")
        blob[ref.json_key] = f"{ref.prefix}{new_id}"
        # sort_keys so a rewritten row is byte-stable across runs (determinism, §5)
        return json.dumps(blob, sort_keys=True, separators=(",", ":"))
    return f"{ref.prefix}{new_id}"


# ══════════════════════════════════════════════════════════════════════
# Physical id collisions — over EVERY packaged table, by value
# ══════════════════════════════════════════════════════════════════════

def _row_ids(rows: Sequence[Dict[str, Any]], column: str = "id") -> List[Any]:
    out = []
    for r in rows:
        v = r.get(column)
        if v is None or isinstance(v, bool):
            continue
        out.append(v)
    return out


def _canonical(row: Dict[str, Any], drop: Sequence[str] = ()) -> str:
    payload = {k: v for k, v in row.items()
               if k not in drop and not k.startswith("_")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def physical_key_columns(table: str) -> Tuple[str, ...]:
    """The physical primary key the collision hunt compares.

    Every narrator-owned lane in the shipped schema keys on a single `id` column, and
    no table anywhere uses a composite `PRIMARY KEY (a, b)` — both measured, and pinned
    by `test_every_no_safe_key_table_is_covered_by_the_collision_hunt`. The override map
    exists so that a future `something_key TEXT PRIMARY KEY` lane cannot bypass the hunt
    merely by not being called `id`: the test fails first, and the answer is an entry
    here rather than a silently unscanned table.
    """
    return PHYSICAL_KEYS.get(table, ("id",))


def _physical_value(row: Dict[str, Any], cols: Sequence[str]) -> Optional[Any]:
    if any(c not in row or row[c] is None for c in cols):
        return None
    return row[cols[0]] if len(cols) == 1 else tuple(row[c] for c in cols)


def find_physical_collisions(origins: Sequence[Origin]) -> List[Dict[str, Any]]:
    """Every table whose physical primary-key values overlap across origins, BY VALUE.

    Deliberately not restricted to integers, and deliberately not skipping a table
    because its ids look like UUIDs: UUID syntax is a minting format, and the product
    mints some ids deterministically from content, so two installations can and do
    produce the same id for different rows.

    **WHETHER A SHARED ID IS SAFE DEPENDS ON THE TABLE, NOT ON THE BYTES.** Two
    classifications come out of this, and conflating them was a real defect in the first
    implementation:

      `safe_same_record`   the table has a PROVEN cross-origin logical key and both rows
                           carry the SAME logical key. The keyed classification owns the
                           outcome and no id is reallocated — identical content is
                           represented once, differing content is a keyed conflict for a
                           human. `people` is the case this exists for.
      `must_reallocate`    a shared id that is NOT the same logical record — including a
                           shared id whose rows are BYTE-IDENTICAL in a
                           `NO_SAFE_CROSS_ORIGIN_KEY` table, where correspondence was
                           never established at all.

    That last clause is the fix. §1 is explicit that `CONTENT_OVERLAP` does **not** mean
    the two rows are the same record, and a no-safe-key table is one where correspondence
    could not be proven at all — so V1 must preserve both rows, and two rows cannot share
    one `TEXT PRIMARY KEY`. The first implementation skipped reallocation whenever the
    bytes matched, which would have handed the executor two `graph_persons` rows under
    one primary key and forced it to either fail or drop one. Letting content equality
    decide identity is exactly what this work order exists to prevent, and the earlier
    test missed it because it exercised `people`, which HAS a proven logical key.
    """
    ordered = sorted(origins, key=lambda o: o.rank_key)
    a, b = ordered[0], ordered[1]
    out: List[Dict[str, Any]] = []
    for table in sorted(set(a.records) | set(b.records)):
        rows_a, rows_b = a.records.get(table, []), b.records.get(table, [])
        if not rows_a or not rows_b:
            continue
        cols = physical_key_columns(table)
        by_a = {v: r for r in rows_a if (v := _physical_value(r, cols)) is not None}
        by_b = {v: r for r in rows_b if (v := _physical_value(r, cols)) is not None}
        shared = sorted(set(by_a) & set(by_b), key=str)
        if not shared:
            continue

        kind, key_cols, _why = xid.logical_key_for(table)
        same_content, diff_content, safe, must = [], [], [], []
        for pk in shared:
            ra, rb = by_a[pk], by_b[pk]
            identical = _canonical(ra) == _canonical(rb)
            (same_content if identical else diff_content).append(pk)
            if kind == xid.KIND_DECLARED:
                ka, kb = _key_of(ra, key_cols), _key_of(rb, key_cols)
                same_record = ka is not None and ka == kb
                # SAME LOGICAL RECORD IS NEVER A PHYSICAL COLLISION, whatever the
                # content says. The keyed classification owns the outcome: identical ->
                # represented once; differing -> SAME_LOGICAL_RECORD_DIFFERENT_CONTENT,
                # refused for a human. Reallocating here would give the merged root TWO
                # `people` rows for one narrator — exactly what the keyed path prevents.
                #
                # Corrected 2026-09-14, found by the first real Christopher rehearsal:
                # this read `same_record and identical`, so his `people` row (identical
                # but for `updated_at`) fell into the reallocation path and refused as
                # a collision in a table with no established closure. A sixth refusal
                # that was really the fourth one counted twice. The fix is NOT to
                # declare a closure for `people.id`.
                (safe if same_record else must).append(pk)
            else:
                # No defensible cross-origin key: correspondence was never established,
                # so both rows are preserved and the shared id must be broken.
                must.append(pk)

        out.append({
            "table": table, "parent": f"{table}.{cols[0]}",
            "physical_key": list(cols),
            "logical_key_kind": kind,
            "shared": len(shared),
            "shared_same_content": same_content,
            "shared_different_content": diff_content,
            "safe_same_record": safe,
            "must_reallocate": must,
            "closure_established": f"{table}.{cols[0]}" in CLOSURE_ESTABLISHED,
        })
    return out


# ══════════════════════════════════════════════════════════════════════
# Deterministic remap
# ══════════════════════════════════════════════════════════════════════

def _realloc_text(package_id: str, table: str, old: Any) -> str:
    """A deterministic replacement id. Same inputs, same output, every run and every
    version — which is why the namespace is frozen."""
    return str(uuid.uuid5(REMAP_NAMESPACE, f"{package_id}|{table}|{old}"))


def plan_remap(origins: Sequence[Origin],
               collisions: Sequence[Dict[str, Any]],
               ) -> Tuple[Dict[str, Dict[str, Dict[Any, Any]]], List[Dict[str, str]]]:
    """Allocate new ids. Returns (remap, refusals).

    TWO POLICIES, on purpose.

    **The three INTEGER surrogates are renumbered UNIFORMLY**, every row, not only the
    colliding ones. Renumbering on collision alone gives the rewrite two code paths
    where the rare one — the one that fires only on real family data — is the one no
    synthetic test exercises. Uniform renumbering means the path that runs against
    Christopher is the path the suite has already run thousands of times.

    **Every other physical id is reallocated ONLY where it actually collides**, because
    a TEXT id can carry meaning the installation relies on (the deterministic
    graph-person id IS the product's own equality rule) and churning all of them would
    leave a merged root whose ids match neither origin, for nothing.

    Ordering is (origin rank, old id) with rank from `package_id`. The lower-ranked
    origin KEEPS its id in a collision; the higher-ranked one is reallocated.
    """
    ordered = sorted(origins, key=lambda o: o.rank_key)
    remap: Dict[str, Dict[str, Dict[Any, Any]]] = {}
    refusals: List[Dict[str, str]] = []

    for parent in REMAP_TARGETS:
        table, _, column = parent.partition(".")
        per_label: Dict[str, Dict[Any, Any]] = {}
        next_id = 1
        for origin in ordered:
            mapping: Dict[Any, Any] = {}
            ids = sorted({int(v) for v in _row_ids(origin.records.get(table, []), column)
                          if isinstance(v, int) or (isinstance(v, str) and
                                                    v.strip().lstrip("-").isdigit())})
            for old in ids:
                mapping[old] = next_id
                next_id += 1
            per_label[origin.label] = mapping
        remap[parent] = per_label

    for coll in collisions:
        parent = coll["parent"]
        if parent in REMAP_TARGETS:
            continue                      # already renumbered uniformly above
        if not coll["must_reallocate"]:
            # Every shared id here is `safe_same_record`: a PROVEN logical key, the same
            # logical record, identical content. That row is represented once by the
            # keyed classification and needs no new id. Note the test is NOT "the bytes
            # match" — see `find_physical_collisions`.
            continue
        if not coll["closure_established"]:
            # Remapping a row whose children we cannot enumerate would orphan them.
            refusals.append({
                "code": R_UNKNOWN_COLLISION_CLOSURE,
                "detail": f"{coll['table']} has {len(coll['must_reallocate'])} "
                          f"colliding physical id(s) and no established reference "
                          f"closure — establish it (read the schema and the writers) "
                          f"before this pair can be merged",
            })
            continue
        higher = ordered[1]
        per_label = {ordered[0].label: {}, higher.label: {}}
        for old in coll["must_reallocate"]:
            per_label[higher.label][old] = _realloc_text(higher.package_id,
                                                         coll["table"], old)
        remap[parent] = per_label
    return remap, refusals


def _map_id(remap: Dict[str, Dict[str, Dict[Any, Any]]], parent: str,
            label: str, old: Any) -> Optional[Any]:
    if old is None or isinstance(old, bool):
        return None
    table = remap.get(parent, {}).get(label, {})
    if old in table:
        return table[old]
    if isinstance(old, str) and old.strip().lstrip("-").isdigit():
        return table.get(int(old))
    return None


def apply_remap(origin: Origin, remap: Dict[str, Dict[str, Dict[Any, Any]]],
                ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """This origin's rows with every remapped id and every reference rewritten.

    Works on copies; `origin.records` is never mutated. Returns (records, rewrites),
    where `rewrites` is the evidence trail.
    """
    out: Dict[str, List[Dict[str, Any]]] = {
        t: [dict(r) for r in rows] for t, rows in origin.records.items()
    }
    rewrites: List[Dict[str, Any]] = []

    for parent in remap:
        table, _, column = parent.partition(".")
        for row in out.get(table, []):
            new = _map_id(remap, parent, origin.label, row.get(column))
            if new is not None and new != row.get(column):
                rewrites.append({"origin": origin.label, "table": table, "column": column,
                                 "kind": "physical_id", "old": row.get(column), "new": new})
                row[column] = new

    for parent in remap:
        for site in reference_sites(parent):
            for row in out.get(site.table, []):
                raw = row.get(site.column)
                if raw is None or raw == "":
                    continue
                if site.encoded is None:
                    new = _map_id(remap, parent, origin.label, raw)
                    if new is None or new == raw:
                        continue
                    rewrites.append({"origin": origin.label, "table": site.table,
                                     "column": site.column, "kind": "reference",
                                     "form": site.form, "old": raw, "new": new})
                    row[site.column] = new
                    continue
                ref = site.encoded
                old_id, malformed = ref.parse(raw)
                if malformed:
                    raise MergeRefused(R_MALFORMED_ENCODED_REFERENCE,
                                       f"{site.table}.{site.column} value={str(raw)[:80]!r}")
                if old_id is None:
                    continue
                new = _map_id(remap, parent, origin.label, old_id)
                if new is None:
                    continue
                rewrites.append({"origin": origin.label, "table": site.table,
                                 "column": site.column, "kind": "reference",
                                 "form": site.form, "old": old_id, "new": new})
                row[site.column] = render_encoded(ref, raw, new)
    return out, rewrites


# ══════════════════════════════════════════════════════════════════════
# The semantic reference validator — acceptance §6.2
# ══════════════════════════════════════════════════════════════════════

def validate_semantic_references(records: Dict[str, List[Dict[str, Any]]],
                                 parents: Sequence[str] = (),
                                 ) -> List[Dict[str, Any]]:
    """Does every stored reference resolve inside this record set?

    **`PRAGMA foreign_key_check` cannot answer this and passing it proves nothing.** No
    migration declares `REFERENCES turns` at all, so SQLite sees none of the seven
    `turns.id` sites. A merged database can be SQL-valid and internally broken, which is
    why acceptance is THIS validator passing.
    """
    checked = list(parents) or list(CLOSURE_ESTABLISHED)
    dangling: List[Dict[str, Any]] = []
    for parent in checked:
        table, _, column = parent.partition(".")
        present = {r.get(column) for r in records.get(table, []) if r.get(column) is not None}
        for site in reference_sites(parent):
            for row in records.get(site.table, []):
                raw = row.get(site.column)
                if raw is None or raw == "":
                    continue
                if site.encoded is None:
                    value = raw
                else:
                    value, malformed = site.encoded.parse(raw)
                    if malformed:
                        dangling.append({"table": site.table, "column": site.column,
                                         "value": str(raw)[:80], "reason": "malformed"})
                        continue
                    if value is None:
                        continue
                if value not in present:
                    dangling.append({"table": site.table, "column": site.column,
                                     "parent": parent, "value": value,
                                     "reason": "no such parent row"})
    return dangling


# ══════════════════════════════════════════════════════════════════════
# Row and file classification — on the REMAPPED rows
# ══════════════════════════════════════════════════════════════════════

def _content_for_compare(row: Dict[str, Any], key_cols: Sequence[str],
                         volatile: Dict[str, str]) -> str:
    """Canonical content hash of an ALREADY-REMAPPED row.

    Two exclusions, both narrow. The logical key itself (identity, not content), and
    the declared volatile columns (row-rewrite stamps the app writes on narrator open,
    BACKLOG §5). A physical `id` that is not part of the logical key is also dropped:
    `bio_facts.id` is a per-installation UUID, so two origins recording the same fact
    about the same field mint different ids, and hashing that would report every such
    row as a conflict over a difference carrying no narrator meaning.

    **References are NOT excluded, and are compared at their remapped values.** That is
    the whole point: two citations are equal here if and only if they resolve to the
    same merged row. A reference difference that survives the remap is a difference in
    what the two rows are evidence OF, and it stays visible.
    """
    payload = _comparable(row, key_cols, volatile)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def _comparable(row: Dict[str, Any], key_cols: Sequence[str],
                volatile: Dict[str, str]) -> Dict[str, Any]:
    """The columns `_content_for_compare` actually hashes — one definition, so the
    reported differing set cannot disagree with the verdict that produced it."""
    return {k: v for k, v in row.items()
            if k not in key_cols and k not in volatile and not k.startswith("_")
            and not (k == "id" and "id" not in key_cols)}


def _differing_columns(a: Dict[str, Any], b: Dict[str, Any], key_cols: Sequence[str],
                       volatile: Dict[str, str]) -> List[str]:
    ca, cb = _comparable(a, key_cols, volatile), _comparable(b, key_cols, volatile)
    return [c for c in set(ca) | set(cb) if ca.get(c) != cb.get(c)]


def _key_of(row: Dict[str, Any], cols: Sequence[str]) -> Optional[str]:
    parts = []
    for c in cols:
        if c not in row or row[c] is None:
            return None
        parts.append(str(row[c]))
    return "\x1f".join(parts)


def classify_rows(records_a: Dict[str, List[Dict[str, Any]]],
                  records_b: Dict[str, List[Dict[str, Any]]],
                  label_a: str, label_b: str,
                  ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, str]],
                             Dict[str, set]]:
    """Per-table verdicts over REMAPPED rows.

    Returns (keyed_verdicts, no_safe_key_tables, refusals, identical_keys), where
    `identical_keys` names the keyed rows proven identical so the merge can represent
    them once instead of inserting a duplicate narrator.
    """
    verdicts: List[Dict[str, Any]] = []
    no_key: List[str] = []
    refusals: List[Dict[str, str]] = []
    identical: Dict[str, set] = {}

    for table in sorted(set(records_a) | set(records_b)):
        kind, cols, _why = xid.logical_key_for(table)
        rows_a, rows_b = records_a.get(table, []), records_b.get(table, [])
        if kind == xid.KIND_NO_KEY:
            # Correspondence could not be PROVEN. Both sides carry, with origin
            # provenance. Never paired, never deduplicated, never dropped — this is the
            # largest class in the real evidence (31 tables for Christopher).
            no_key.append(table)
            continue

        volatile = xid.volatile_columns(table)

        def _group(rows):
            out: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows:
                key = _key_of(r, cols)
                if key is not None:
                    out.setdefault(key, []).append(r)
            return out

        idx_a, idx_b = _group(rows_a), _group(rows_b)
        same = diff = 0
        duplicated: List[str] = []
        for key in sorted(set(idx_a) & set(idx_b)):
            ga, gb = idx_a[key], idx_b[key]
            if len(ga) > 1 or len(gb) > 1:
                # One origin holds several rows under one logical key — `bio_facts`
                # does, and BACKLOG §5's `questionnaire_put` is the known cause.
                # Correspondence WITHIN the key is not established, so pairing would be
                # a guess; both sides carry and a human sees the duplication. §4:
                # carry duplicates as-is, never collapse.
                duplicated.append(key)
                continue
            if _content_for_compare(ga[0], cols, volatile) == \
               _content_for_compare(gb[0], cols, volatile):
                same += 1
                identical.setdefault(table, set()).add(key)
            else:
                diff += 1
                # NAME THE COLUMNS. "profiles key=… differs" tells a human nothing they
                # can decide on, and a caller that wants to know whether a conflict is
                # only a row-rewrite stamp would otherwise have to guess it from the
                # table name. Adjudication needs the actual differing set.
                differing = sorted(_differing_columns(ga[0], gb[0], cols, volatile))
                refusals.append({
                    "code": R_SAME_KEY_DIFFERENT_CONTENT,
                    "table": table,
                    "key": key,
                    "columns": differing,
                    "detail": f"{table} key={key} — {label_a} and {label_b} differ in "
                              f"{', '.join(differing) if differing else '(no column)'}",
                })
        verdicts.append({
            "table": table, "key": list(cols), "same": same, "different": diff,
            "duplicate_keys": duplicated,
            f"only_{label_a}": len(set(idx_a) - set(idx_b)),
            f"only_{label_b}": len(set(idx_b) - set(idx_a)),
        })
    return verdicts, no_key, refusals, identical


def classify_files(origins: Sequence[Origin],
                   ) -> Tuple[List[Dict[str, str]], List[str], List[Dict[str, str]]]:
    """Union is overwhelmingly the answer: each machine recorded its own sessions, so
    the file merge is a union, not a reconciliation."""
    ordered = sorted(origins, key=lambda o: o.rank_key)
    a, b = ordered[0], ordered[1]
    union: List[Dict[str, str]] = []
    regenerate: List[str] = []
    refusals: List[Dict[str, str]] = []

    for path in sorted(set(a.files) | set(b.files)):
        in_a, in_b = path in a.files, path in b.files
        if in_a and in_b:
            if a.files[path] == b.files[path]:
                union.append({"path": path, "origin": "both", "sha256": a.files[path]})
            elif any(path.endswith(s) for s in REGENERABLE_FILE_SUFFIXES):
                regenerate.append(path)
            else:
                # `rolling_summary.json` is the case this protects: LLM-produced,
                # scored and PRUNED (archive.py:654-687), so neither side is a superset
                # and "take the newer last_updated" would silently destroy memory.
                refusals.append({
                    "code": R_FILE_PATH_DIFFERENT_BYTES,
                    "detail": f"{path} — {a.label} {a.files[path][:12]}… vs "
                              f"{b.label} {b.files[path][:12]}…",
                })
        else:
            origin = a.label if in_a else b.label
            union.append({"path": path, "origin": origin,
                          "sha256": a.files[path] if in_a else b.files[path]})
    return union, regenerate, refusals


# ══════════════════════════════════════════════════════════════════════
# The plan
# ══════════════════════════════════════════════════════════════════════

def plan_merge(package_a: Path, package_b: Path, *,
               label_a: str = "A", label_b: str = "B") -> MergePlan:
    """Read two packages and decide what a merged root WOULD contain. Writes nothing."""
    origins = [load_origin(Path(package_a), label_a), load_origin(Path(package_b), label_b)]
    if origins[0].narrator_id != origins[1].narrator_id:
        raise MergeRefused(
            R_DIFFERENT_NARRATORS,
            f"{origins[0].narrator_id!r} vs {origins[1].narrator_id!r} — "
            "same-person equivalence across origins is never inferred here")

    ordered = sorted(origins, key=lambda o: o.rank_key)
    collisions = find_physical_collisions(ordered)
    remap, remap_refusals = plan_remap(ordered, collisions)

    remapped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    rewrites: List[Dict[str, Any]] = []
    for origin in ordered:
        records, done = apply_remap(origin, remap)
        rewrites.extend(done)
        for rows in records.values():
            for row in rows:
                row["_origin"] = origin.label
                row["_origin_package"] = origin.package_id
        remapped[origin.label] = records

    a, b = ordered[0], ordered[1]
    verdicts, no_key, row_refusals, identical = classify_rows(
        remapped[a.label], remapped[b.label], a.label, b.label)

    # Build the merged set. A keyed row proven identical on both origins is represented
    # ONCE — inserting it twice would give the narrator two `people` rows — and its
    # provenance records that both origins held it. Everything else carries from both.
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for origin in ordered:
        for table, rows in remapped[origin.label].items():
            _kind, cols, _why = xid.logical_key_for(table)
            dedupe = identical.get(table, set())
            for row in rows:
                key = _key_of(row, cols) if cols else None
                if key is not None and key in dedupe:
                    if origin is not a:
                        continue                      # already carried from rank 0
                    row = dict(row, _origin="both")
                merged.setdefault(table, []).append(row)

    dangling = validate_semantic_references(merged)
    files_union, regenerate, file_refusals = classify_files(ordered)

    return MergePlan(
        narrator_id=a.narrator_id,
        origins=[{"label": o.label, "package_id": o.package_id, "sha256": o.sha256,
                  "path": str(o.path)} for o in ordered],
        remap=remap,
        remap_rows=sum(len(m) for p in remap.values() for m in p.values()),
        physical_collisions=collisions,
        reference_rewrites=rewrites,
        carried_rows={t: len(rows) for t, rows in sorted(merged.items())},
        merged_records=merged,
        keyed_verdicts=verdicts,
        no_safe_key_tables=no_key,
        files_union=files_union,
        files_regenerate=regenerate,
        refusals=remap_refusals + row_refusals + file_refusals,
        dangling_after_rewrite=dangling,
        wrote_anything=False,
    )
