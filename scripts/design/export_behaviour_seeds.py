#!/usr/bin/env python3
"""Export the product's BEHAVIOURAL vocabularies as measured seed data.

WHY THIS EXISTS. A blueprint of the life record (Chris + ChatGPT, Version 2)
needs the parts that decide how Lori behaves: when it is natural to ask
(bio_schema asking anchors), what closes a Profile Seed topic, which prompt
sections survive budget fitting, and what a package carries. Version 1 left
those columns empty. Writing them by hand would create a fifth vocabulary
beside the four this redesign is reconciling, which is the drift it exists
to end.

So they are exported from the shipped code, each section naming the symbol
it came from. Nothing here is a proposal and nothing is written back.

READ-ONLY. Imports four pure service modules; touches no database.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONPATH=server/code \\
      python3 scripts/design/export_behaviour_seeds.py --out PATH.json
"""

import argparse
import dataclasses as dc
import datetime as _dt
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "server", "code"))


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _plain(v):
    """JSON-safe: tuples to lists, dataclasses to dicts, anything else to str."""
    if dc.is_dataclass(v):
        return {f.name: _plain(getattr(v, f.name)) for f in dc.fields(v)}
    if isinstance(v, tuple) and hasattr(v, "_asdict"):      # NamedTuple, e.g. SectionPolicy
        return {k: _plain(x) for k, x in v._asdict().items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def asking():
    from api.services import bio_schema as bs
    rows = []
    for f in bs.iter_seed():
        d = _plain(f)
        d["tier3_eligible"] = bool(f.narrative_value == "high" and len(f.asking_anchors) > 0)
        rows.append(d)
    return {"symbol": "api.services.bio_schema.iter_seed",
            "rule": "Tier 3 (anchored asking) requires narrative_value == 'high' AND a "
                    "non-empty asking_anchors; an empty anchor list is the deactivation "
                    "signal (bio_schema docstring).",
            "rows": rows}


def profile_seed():
    from api.services import profile_seed as sd
    return {"symbol": "api.services.profile_seed.TOPIC_REGISTRY",
            "rule": "A topic is closed by EVIDENCE at any listed path (topic_has_evidence), "
                    "never by the narrator being asked. negative_meaningful: an explicit "
                    "'no' closes the topic.",
            "rows": [_plain(t) for t in sd.TOPIC_REGISTRY]}


def prompt_sections():
    from api.services import prompt_section_policy as ps
    rows = [_plain(v) for v in ps.REGISTRY.values()]
    rows.sort(key=lambda r: (r.get("drop_order") or 0, r["section_id"]))
    return {"symbol": "api.services.prompt_section_policy.REGISTRY",
            "rule": "TRIM_NEVER sections are required and never shed; the rest are shed in "
                    "ascending drop_order under budget. A section may be droppable because "
                    "its SOURCE is durable, never because the person could be made to say "
                    "it again (prompt_section_policy.py:367-370).",
            "rows": rows}


def inventory():
    from api.services import narrator_data_inventory as inv
    def lane(l):
        d = _plain(l)
        d["owner_kind"] = type(l.owner).__name__
        return d
    return {"symbol": "api.services.narrator_data_inventory.DB_LANES / FS_LANES",
            "rule": "Every narrator-owned table needs a DbLane or it silently fails to "
                    "export AND to erase. Rows without person_id in a CLASS_SHARED_ROW lane "
                    "are reported, never packaged.",
            "db_lanes": [lane(l) for l in inv.DB_LANES],
            "fs_lanes": [_plain(l) for l in inv.FS_LANES]}


def extraction_fields():
    src = _read_text(os.path.join(ROOT, "server", "code", "api", "routers", "extract.py"))
    i = src.index("EXTRACTABLE_FIELDS = {")
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                blk = src[j:k + 1]
                break
    rows = []
    for m in re.finditer(r'^\s{4}"([^"]+)":\s*\{"label":\s*"((?:[^"\\]|\\.)*)"(?:,\s*"writeMode":\s*"([^"]+)")?',
                         blk, re.M):
        rows.append({"path": m.group(1), "label": m.group(2), "writeMode": m.group(3)})
    catalog_chars = sum(len(f'"{r["path"]}"={r["label"]}') + 2 for r in rows)
    return {"symbol": "api.routers.extract.EXTRACTABLE_FIELDS",
            "rule": "Today EVERY field is sent on EVERY extraction call "
                    "(extract.py:697-702). D1f (2026-09-22) requires relevance-scoped "
                    "extraction; this list is the current state, not the target.",
            "catalog_chars_per_call": catalog_chars,
            "rows": rows}


def known_delivery_defects():
    """Measured facts about delivery that a blueprint must not reproduce."""
    from api.services import questionnaire_for_lori as qfl
    return {"symbol": "api.services.questionnaire_for_lori._SKIP_FIELDS",
            "rows": [{
                "fact": "questionnaire_for_lori strips `deceased` before anything reaches Lori",
                "value": sorted(getattr(qfl, "_SKIP_FIELDS", [])),
                "consequence": "no life status reaches the prompt by this path "
                               "(BUG-LORI-UNAWARE-OF-DEATH-01)",
            }]}


def legacy_ledger():
    """The 195-path ledger, from the catalog script (measured + proposed, labelled)."""
    out = os.path.join("/tmp", "catalog_recon_for_seeds.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "design", "build_concept_catalog.py"),
                    "--json", out], check=True, capture_output=True)
    d = json.loads(_read_text(out))
    return {"symbol": "scripts/design/build_concept_catalog.py --json",
            "labels": d.get("labels"),
            "per_path_ledger": d["measured"]["per_path_ledger"],
            "proposal": d["proposal"]}


GENERATOR_VERSION = "behaviour-seeds/2"
DECISIONS_MD = os.path.join(ROOT, "docs", "wo", "WO-HORNELORE-INTEGRATED-LIFE-RECORD-01_DECISIONS.md")
EXPECTED_DECISIONS = ["D1a", "D1b", "D1c", "D1d", "D1e", "D1f",
                      "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11"]


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_md(s):
    # `*` and backticks only. Stripping `_` as well mangled identifiers in the
    # recorded refinements (`person.death.reported_age` -> `reportedage`);
    # the decisions table uses `*` for emphasis, never `_`.
    return re.sub(r"[*`]", "", s).strip()


def _expand_ids(text):
    """Appendix group ids named in a passage: singles (`G14`) and ranges
    (`G01`–`G34`, en dash or hyphen). Ranges expand; order is preserved."""
    ids = []
    for m in re.finditer(r"\b([ABGQ])(\d{2})`?\s*[–-]\s*`?\1(\d{2})\b", text):
        ids += [f"{m.group(1)}{n:02d}" for n in range(int(m.group(2)), int(m.group(3)) + 1)]
    ids += re.findall(r"\b[ABGQ]\d{2}\b", text)
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return sorted(out)


def decisions():
    """Chris's recorded decisions, read from the ONE document he reads.

    Deliberately not a second JSON copy: two copies of a decision drift, and
    this project exists to end that. The markdown table is the authority; this
    parses it and FAILS CLOSED if any expected decision is missing, rather
    than exporting a partial set a generator would treat as complete."""
    src = _read_text(DECISIONS_MD)
    m = re.search(r"## ✅ DECIDED — Chris, (\d{4}-\d{2}-\d{2})(.*?)\n---\n", src, re.S)
    if not m:
        raise ValueError("no '## ✅ DECIDED' block — decisions are not recorded yet")
    approved_at, block = m.group(1), m.group(2)
    rows = {}
    for r in re.finditer(r"^\| \*\*(D\d+[a-f]?)\*\* \| (.+?) \| (.+?) \|\s*$", block, re.M):
        did, sel, ref = r.group(1), _strip_md(r.group(2)), _strip_md(r.group(3))
        opt = re.match(r"\(([a-c])\)", sel)
        rows[did] = {
            "decision_id": did,
            "state": "approved" if (opt or sel.lower().startswith("approve")) else "unrecognised",
            "selected_option": opt.group(1) if opt else ("approve" if sel.lower().startswith("approve") else sel),
            "selection_text": sel,
            "refinement": None if ref in ("—", "-", "") else ref,
            "approved_at": approved_at,
        }
    missing = [d for d in EXPECTED_DECISIONS if d not in rows]
    if missing:
        raise ValueError(f"decisions table is missing {missing} — refusing a partial export")

    # Affected appendix groups: the passage of the PACKET that asked each question.
    body = src[m.end():]
    heads = list(re.finditer(r"^(?:#{2,3} |\*\*)(D\d+[a-f]?)\b", body, re.M))
    # A decision's passage ends at the next heading of ANY kind, not only the
    # next decision: the first version let D10 run on into the reply form,
    # whose example line names G45/G46, and credited D10 with them.
    bounds = [b.start() for b in re.finditer(r"^(?:#{1,3} |\*\*D\d)", body, re.M)]
    for i, h in enumerate(heads):
        did = h.group(1)
        later = [b for b in bounds if b > h.start()]
        end = later[0] if later else len(body)
        if did in rows:
            rows[did]["affected_group_ids"] = _expand_ids(body[h.start():end])
    for r in rows.values():
        r.setdefault("affected_group_ids", [])

    # D1 as a whole covers D1a-f; the umbrella heading is not a decision.
    return {"symbol": os.path.relpath(DECISIONS_MD, ROOT).replace(os.sep, "/"),
            "source_sha256": _sha256(DECISIONS_MD),
            "rule": "Where a refinement is recorded it GOVERNS the packet's recommendation. "
                    "A generator must refuse to mark a catalog buildable if any decision "
                    "it depends on is not 'approved'.",
            "rows": [rows[d] for d in EXPECTED_DECISIONS]}


def _git_head():
    """HEAD commit read from .git files — no git process, so no index.lock."""
    g = os.path.join(ROOT, ".git")
    try:
        head = _read_text(os.path.join(g, "HEAD")).strip()
        if not head.startswith("ref:"):
            return {"commit": head, "ref": None}
        ref = head.split(" ", 1)[1]
        p = os.path.join(g, ref)
        if os.path.exists(p):
            return {"commit": _read_text(p).strip(), "ref": ref}
        for line in _read_text(os.path.join(g, "packed-refs")).splitlines():
            if line.strip().endswith(" " + ref):
                return {"commit": line.split()[0], "ref": ref}
    except OSError:
        pass
    return {"commit": None, "ref": None}


def fingerprints():
    """Which repository state produced these seeds, so any blueprint built
    from them can prove it. HEAD alone is not enough — the working tree may
    carry uncommitted edits — so every source file is hashed as well."""
    from api.services import questionnaire_schema as qs
    rel = {
        "questionnaire_js": "ui/js/bio-builder-questionnaire.js",
        "projection_map_js": "ui/js/projection-map.js",
        "extract_py": "server/code/api/routers/extract.py",
        "bio_schema_py": "server/code/api/services/bio_schema.py",
        "profile_seed_py": "server/code/api/services/profile_seed.py",
        "prompt_section_policy_py": "server/code/api/services/prompt_section_policy.py",
        "narrator_data_inventory_py": "server/code/api/services/narrator_data_inventory.py",
        "questionnaire_for_lori_py": "server/code/api/services/questionnaire_for_lori.py",
        "decisions_md": "docs/wo/WO-HORNELORE-INTEGRATED-LIFE-RECORD-01_DECISIONS.md",
        "decision_appendix_md": "docs/specs/CONCEPT-DECISION-APPENDIX.md",
        "catalog_script": "scripts/design/build_concept_catalog.py",
        "this_script": "scripts/design/export_behaviour_seeds.py",
    }
    return {
        "generator_version": GENERATOR_VERSION,
        "git_head": _git_head(),
        "questionnaire_schema_fingerprint": qs.schema_fingerprint(),
        "files_sha256": {k: _sha256(os.path.join(ROOT, v)) for k, v in rel.items()},
        "files": rel,
        "note": "A seed produced from a working tree with uncommitted edits still "
                "hashes those edits; compare files_sha256, not only git_head.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    seeds, errors = {}, []
    for name, fn in (("asking", asking), ("profile_seed", profile_seed),
                     ("prompt_sections", prompt_sections), ("inventory", inventory),
                     ("extraction_fields", extraction_fields),
                     ("known_delivery_defects", known_delivery_defects),
                     ("legacy_ledger", legacy_ledger),
                     ("decisions", decisions)):
        try:
            seeds[name] = fn()
        except Exception as exc:                                    # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    try:
        fp = fingerprints()
    except Exception as exc:                                        # noqa: BLE001
        fp = None
        errors.append(f"fingerprints: {type(exc).__name__}: {exc}")
    import hashlib
    sections_sha = hashlib.sha256(
        json.dumps(seeds, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    doc = {
        "kind": "measured behavioural seeds for the life-record blueprint",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "rule": "Every section names the symbol it was read from. The `decisions` section "
                "is Chris's recorded decisions, parsed from the one document he reads; "
                "everything else is measured from shipped code.",
        "sections_sha256": sections_sha,
        "fingerprints": fp,
        "errors": errors,
        "sections": seeds,
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False)
    for name, s in seeds.items():
        n = len(s.get("rows", s.get("db_lanes", s.get("per_path_ledger", []))))
        print(f"  {name:<24} {n:>4}  [{s['symbol']}]")
    if errors:
        print("ERRORS:", *errors, sep="\n  ")
    print(f"  wrote {a.out}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
