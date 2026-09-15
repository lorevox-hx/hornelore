#!/usr/bin/env python3
"""Build the human decision packet for a refused merge. EVIDENCE ONLY — mutates nothing.

WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 §5a.

V1 refuses every conflict and resolves none. This turns that refusal into something a
person can actually decide from: for each unresolved conflict, both origins' values, laid
out so the decision-bearing content is visible in full rather than summarised into
uselessness.

WHAT IT DOES NOT DO
    * choose a winner, rank the sides, or propose a default for anything except where the
      OPERATOR has already stated the rule (see `--timestamp-rule`);
    * concatenate, merge or reconcile any value;
    * modify a source package, the target root, or the plan. It re-derives the plan and
      the binding read-only, and writes only under `--out`.

WHY IT BINDS TO FINGERPRINTS
    A decision is about specific bytes. The packet records the narrator id, both package
    ids and FULL sha256s, the source-plan fingerprint and the bound execution fingerprint,
    so an adjudication can be checked against — and refused for — data that has since
    changed. A decision replayed against different source data is not the decision that
    was made.

USAGE
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/merge_adjudication_packet.py \\
        --a .runtime/two_origin/desktop/<pkg>.lorevox.zip \\
        --b .runtime/two_origin/laptop/<pkg>.lorevox.zip \\
        --label-a desktop --label-b laptop \\
        --target-root /mnt/c/hornelore_merge_rehearsal \\
        --out .runtime/merge/adjudication

Packets carry real narrator content and land under `.runtime/`, which is gitignored.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SERVER_CODE = str(Path(__file__).resolve().parents[1] / "server" / "code")
if _SERVER_CODE not in sys.path:
    sys.path.insert(0, _SERVER_CODE)

from api.services import narrator_merge as merge               # noqa: E402
from api.services import narrator_merge_apply as apply_mod     # noqa: E402


def _rehearsal_module():
    """`merge_rehearsal.py` owns "ask the product where its database is".

    IMPORTED, NOT COPIED. That rule already went wrong once in this lane — the first
    rehearsal script invented `<root>/<db_name>` and reported a correctly initialised
    root as uninitialised — and a second copy here would be a second chance to get it
    wrong. Scripts are not a package, so this loads it by path.
    """
    import importlib.util
    path = Path(__file__).resolve().parent / "merge_rehearsal.py"
    spec = importlib.util.spec_from_file_location("merge_rehearsal", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_resolve_db_path = _rehearsal_module()._resolve_db_path

#: How much of a value goes in the readable summary. THE FULL VALUE IS ALWAYS WRITTEN to
#: its own file beside the packet — this only governs the at-a-glance table, and every
#: truncation says where the whole thing is.
PREVIEW = 400


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Nested JSON to dotted leaf paths, so two documents can be compared field by field
    instead of as two walls of text. A list is indexed; a scalar is a leaf."""
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        if not obj:
            out[prefix or "."] = {}
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        if not obj:
            out[prefix or "."] = []
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix or "."] = obj
    return out


def _as_json(raw: Any) -> Tuple[Optional[Any], Optional[str]]:
    if raw is None:
        return None, "value is NULL"
    if isinstance(raw, (dict, list)):
        return raw, None
    try:
        return json.loads(str(raw)), None
    except Exception as exc:
        return None, f"not parseable as JSON ({exc})"


def _compare_json(a_raw: Any, b_raw: Any, label_a: str, label_b: str) -> Dict[str, Any]:
    """Field-level comparison of two JSON documents.

    Four buckets, kept apart on purpose: what both agree on is context for the decision,
    what only one side has is an addition rather than a conflict, and only the fourth
    bucket — same field, different value — is a choice anybody has to make.
    """
    a_obj, a_err = _as_json(a_raw)
    b_obj, b_err = _as_json(b_raw)
    if a_err or b_err:
        return {"parse_error": {label_a: a_err, label_b: b_err},
                "raw": {label_a: a_raw, label_b: b_raw}}
    fa, fb = _flatten(a_obj), _flatten(b_obj)
    same, only_a, only_b, differ = {}, {}, {}, {}
    for k in sorted(set(fa) | set(fb)):
        if k in fa and k in fb:
            if fa[k] == fb[k]:
                same[k] = fa[k]
            else:
                differ[k] = {label_a: fa[k], label_b: fb[k]}
        elif k in fa:
            only_a[k] = fa[k]
        else:
            only_b[k] = fb[k]
    return {"fields_agreeing": same, f"only_{label_a}": only_a,
            f"only_{label_b}": only_b, "fields_differing": differ}


def _text_diff(a: bytes, b: bytes, label_a: str, label_b: str) -> str:
    """A readable diff of two files. Pretty-printed first when both are JSON, so the diff
    shows what changed rather than how the serialiser happened to wrap it."""
    def _norm(raw: bytes) -> List[str]:
        try:
            return json.dumps(json.loads(raw.decode("utf-8")), indent=2,
                              sort_keys=True, ensure_ascii=False).splitlines()
        except Exception:
            return raw.decode("utf-8", errors="replace").splitlines()
    return "\n".join(difflib.unified_diff(_norm(a), _norm(b),
                                          fromfile=label_a, tofile=label_b, lineterm=""))


def _member_bytes(zip_path: Path, rel: str) -> Optional[bytes]:
    want = merge.FILES_PREFIX + rel
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name == want or name.endswith(want):
                return zf.read(name)
    return None


def _rows_for(plan: merge.MergePlan, table: str, key: str) -> Dict[str, Dict[str, Any]]:
    """Both origins' copies of one conflicting row, by origin label."""
    _kind, cols, _why = merge.xid.logical_key_for(table)
    out: Dict[str, Dict[str, Any]] = {}
    for row in plan.merged_records.get(table, []):
        if merge._key_of(row, cols) == key:
            out[row.get("_origin", "?")] = row
    return out


def build(plan: merge.MergePlan, bound, label_a: str, label_b: str,
          sources: Dict[str, Path], out_dir: Path, timestamp_rule: bool) -> Dict[str, Any]:
    refusals = plan.refusals + bound.refusals
    packet: Dict[str, Any] = {
        "generated": _now(),
        "narrator_id": plan.narrator_id,
        "origins": [{"label": o["label"], "package_id": o["package_id"],
                     "sha256": o["sha256"], "path": o["path"]} for o in plan.origins],
        "source_plan_fingerprint": apply_mod.plan_fingerprint(plan),
        "bound_execution_fingerprint": bound.execution_fingerprint,
        "target_basis_fingerprint": bound.basis_fingerprint,
        "target_root": str(bound.root),
        "decisions": [],
    }
    details = out_dir / "conflicts"
    details.mkdir(parents=True, exist_ok=True)

    for i, r in enumerate(refusals, 1):
        entry: Dict[str, Any] = {"n": i, "code": r["code"], "detail": r["detail"],
                                 "disposition": None, "decided_by": None, "note": None}

        if r["code"] == merge.R_SAME_KEY_DIFFERENT_CONTENT:
            table, key, columns = r["table"], r["key"], r["columns"]
            entry.update(table=table, key=key, columns=columns)
            rows = _rows_for(plan, table, key)
            a_row, b_row = rows.get(label_a, {}), rows.get(label_b, {})
            per_column: Dict[str, Any] = {}
            for col in columns:
                av, bv = a_row.get(col), b_row.get(col)
                looks_json = any(isinstance(v, str) and v.strip()[:1] in "{["
                                 for v in (av, bv))
                if looks_json:
                    cmp = _compare_json(av, bv, label_a, label_b)
                    per_column[col] = cmp
                    # full values, untruncated, one file per side
                    for lbl, val in ((label_a, av), (label_b, bv)):
                        p = details / f"{i:02d}_{table}_{col}_{lbl}.json"
                        try:
                            p.write_text(json.dumps(json.loads(str(val)), indent=2,
                                                    ensure_ascii=False, sort_keys=True),
                                         encoding="utf-8")
                        except Exception:
                            p.write_text(str(val), encoding="utf-8")
                else:
                    per_column[col] = {"values": {label_a: av, label_b: bv}}
            entry["columns_detail"] = per_column

            # every column that is NOT in dispute — context for the decision, and the
            # evidence behind a timestamp-only finding
            agreeing = sorted(k for k in set(a_row) | set(b_row)
                              if not k.startswith("_") and k not in columns
                              and a_row.get(k) == b_row.get(k))
            entry["columns_agreeing"] = agreeing

            if set(columns) <= {"updated_at", "created_at", "last_updated"}:
                entry["timestamp_only"] = True
                if timestamp_rule:
                    vals = {label_a: a_row.get(columns[0]), label_b: b_row.get(columns[0])}
                    winner = max(vals, key=lambda k: str(vals[k] or ""))
                    entry["disposition"] = f"keep {winner}"
                    entry["decided_by"] = "operator rule: --timestamp-rule later-wins"
                    entry["note"] = (
                        f"every other column on this row is identical ({len(agreeing)} of "
                        f"them); only {', '.join(columns)} differs, so no biographical "
                        f"claim is being chosen between")

        elif r["code"] == merge.R_FILE_PATH_DIFFERENT_BYTES:
            rel = r["detail"].split(" — ")[0].strip()
            entry["path"] = rel
            a_bytes = _member_bytes(sources[label_a], rel)
            b_bytes = _member_bytes(sources[label_b], rel)
            entry["sha256"] = {
                label_a: _sha256_bytes(a_bytes) if a_bytes is not None else None,
                label_b: _sha256_bytes(b_bytes) if b_bytes is not None else None}
            entry["bytes"] = {label_a: len(a_bytes or b""), label_b: len(b_bytes or b"")}
            if a_bytes is not None and b_bytes is not None:
                (details / f"{i:02d}_{Path(rel).name}.{label_a}").write_bytes(a_bytes)
                (details / f"{i:02d}_{Path(rel).name}.{label_b}").write_bytes(b_bytes)
                diff = _text_diff(a_bytes, b_bytes, label_a, label_b)
                (details / f"{i:02d}_{Path(rel).name}.diff").write_text(diff, encoding="utf-8")
                entry["diff_lines"] = len(diff.splitlines())
                entry["note"] = (
                    "derived but NOT regenerable: LLM-produced running memory, scored and "
                    "PRUNED, so neither side is a superset and 'take the newer' would "
                    "silently destroy memory (archive.py:654-687). Not concatenated, not "
                    "chosen.")
        packet["decisions"].append(entry)
    return packet


def _render(packet: Dict[str, Any], label_a: str, label_b: str) -> str:
    L: List[str] = []
    ap = L.append
    ap(f"# Adjudication packet — narrator `{packet['narrator_id']}`")
    ap("")
    ap("*Evidence only. Nothing was merged, written or chosen by producing this.*")
    ap("")
    ap("## Bound to")
    ap("")
    ap("| | |")
    ap("|---|---|")
    for o in packet["origins"]:
        ap(f"| {o['label']} package | `{o['package_id']}` |")
        ap(f"| {o['label']} sha256 | `{o['sha256']}` |")
    ap(f"| source-plan fingerprint | `{packet['source_plan_fingerprint']}` |")
    ap(f"| bound execution fingerprint | `{packet['bound_execution_fingerprint']}` |")
    ap(f"| target basis fingerprint | `{packet['target_basis_fingerprint']}` |")
    ap("")
    ap("**A decision recorded here applies to these bytes and no others.** If a package "
       "or the target changes, the merge refuses and the adjudication is re-made rather "
       "than replayed.")
    ap("")
    ap(f"## {len(packet['decisions'])} decisions")
    ap("")

    for d in packet["decisions"]:
        ap(f"### {d['n']}. `{d['code']}`")
        ap("")
        ap(f"{d['detail']}")
        ap("")
        if d.get("columns_detail"):
            ap(f"Columns in dispute: **{', '.join(d['columns'])}** · "
               f"columns agreeing: {len(d.get('columns_agreeing', []))}")
            ap("")
            for col, cmp in d["columns_detail"].items():
                ap(f"**`{col}`**")
                ap("")
                if "parse_error" in cmp:
                    ap(f"- could not parse as JSON: {cmp['parse_error']}")
                    ap("")
                    continue
                if "values" in cmp:
                    for lbl, v in cmp["values"].items():
                        ap(f"- {lbl}: `{v}`")
                    ap("")
                    continue
                differ = cmp.get("fields_differing", {})
                only_a = cmp.get(f"only_{label_a}", {})
                only_b = cmp.get(f"only_{label_b}", {})
                ap(f"- fields agreeing: **{len(cmp.get('fields_agreeing', {}))}**")
                ap(f"- only in {label_a}: **{len(only_a)}** · "
                   f"only in {label_b}: **{len(only_b)}**")
                ap(f"- same field, different value: **{len(differ)}**")
                ap("")
                if differ:
                    ap("| field | " + label_a + " | " + label_b + " |")
                    ap("|---|---|---|")
                    for k, v in differ.items():
                        va = str(v[label_a])[:PREVIEW]
                        vb = str(v[label_b])[:PREVIEW]
                        ap(f"| `{k}` | {va} | {vb} |")
                    ap("")
                for name, bucket in ((f"only in {label_a}", only_a),
                                     (f"only in {label_b}", only_b)):
                    if bucket:
                        ap(f"<details><summary>{name} ({len(bucket)})</summary>")
                        ap("")
                        for k, v in list(bucket.items()):
                            ap(f"- `{k}` = {str(v)[:PREVIEW]}")
                        ap("")
                        ap("</details>")
                        ap("")
                ap(f"*Full values: `conflicts/{d['n']:02d}_{d['table']}_{col}_*.json`*")
                ap("")
        if d.get("path"):
            ap(f"- `{label_a}` sha256 `{d['sha256'][label_a]}` "
               f"({d['bytes'][label_a]} bytes)")
            ap(f"- `{label_b}` sha256 `{d['sha256'][label_b]}` "
               f"({d['bytes'][label_b]} bytes)")
            ap(f"- diff: **{d.get('diff_lines', 0)} lines**, "
               f"`conflicts/{d['n']:02d}_{Path(d['path']).name}.diff`")
            ap("")
        if d.get("timestamp_only"):
            ap("> **Timestamp-only.** Every other column on this row is identical, so no "
               "biographical claim is in dispute — only when each installation last "
               "touched the record.")
            ap("")
        if d.get("disposition"):
            ap(f"**Proposed disposition: {d['disposition']}** — {d['decided_by']}.")
            if d.get("note"):
                ap(f"  {d['note']}")
            ap("")
        else:
            ap("**Disposition: _undecided_.** V1 resolves nothing; this needs a person.")
            ap("")
        if d.get("note") and not d.get("disposition"):
            ap(f"> {d['note']}")
            ap("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap_.add_argument("--a", required=True)
    ap_.add_argument("--b", required=True)
    ap_.add_argument("--label-a", default="A")
    ap_.add_argument("--label-b", default="B")
    ap_.add_argument("--target-root", required=True)
    ap_.add_argument("--db-name", default="")
    ap_.add_argument("--out", default=".runtime/merge/adjudication")
    ap_.add_argument("--timestamp-rule", action="store_true",
                     help="record the OPERATOR's stated rule for timestamp-only "
                          "conflicts: keep the later value. Applies to nothing else, "
                          "and still requires confirmation.")
    a = ap_.parse_args(argv)

    root = Path(a.target_root).resolve()
    sources = {a.label_a: Path(a.a).resolve(), a.label_b: Path(a.b).resolve()}
    out_base = Path(a.out).resolve()
    if out_base == root or root in out_base.parents:
        print(f"REFUSED: --out {out_base} is inside the target root", file=sys.stderr)
        return 2

    # measured, not asserted: the packet must not have changed what it read
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()}

    # re-derive the plan and binding READ-ONLY, from the same inputs, so the packet's
    # fingerprints are the ones an execution would check against
    db_path = _resolve_db_path(root, a.db_name)
    if not db_path.is_file():
        print(f"REFUSED: the target is not initialised — the product resolves its "
              f"database to {db_path}", file=sys.stderr)
        return 2
    plan = merge.plan_merge(sources[a.label_a], sources[a.label_b],
                            label_a=a.label_a, label_b=a.label_b)
    bound = apply_mod.bind_to_target(plan, data_dir=root, db_path=db_path)

    refusals = plan.refusals + bound.refusals
    if not refusals:
        print("No unresolved conflicts: this plan is executable and needs no "
              "adjudication.")
        return 0

    out_dir = out_base / f"christopher-{plan.narrator_id[:8]}-{_now()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    packet = build(plan, bound, a.label_a, a.label_b, sources, out_dir, a.timestamp_rule)
    (out_dir / "packet.json").write_text(
        json.dumps(packet, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    rendered = _render(packet, a.label_a, a.label_b)
    (out_dir / "packet.md").write_text(rendered, encoding="utf-8")

    print(rendered)
    print(f"\nwritten: {out_dir}")
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()}
    ok = after == before
    print(f"read-only proof: source packages byte-identical after the run = {ok}")
    if not ok:
        print("\nBUILDING A PACKET CHANGED A SOURCE PACKAGE. Stop and report it.",
              file=sys.stderr)
        return 4
    print("nothing was merged, written to the target, or decided by this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
