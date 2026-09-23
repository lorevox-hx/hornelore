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
    src = open(os.path.join(ROOT, "server", "code", "api", "routers", "extract.py"),
               encoding="utf-8").read()
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
    d = json.load(open(out, encoding="utf-8"))
    return {"symbol": "scripts/design/build_concept_catalog.py --json",
            "labels": d.get("labels"),
            "per_path_ledger": d["measured"]["per_path_ledger"],
            "proposal": d["proposal"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    seeds, errors = {}, []
    for name, fn in (("asking", asking), ("profile_seed", profile_seed),
                     ("prompt_sections", prompt_sections), ("inventory", inventory),
                     ("extraction_fields", extraction_fields),
                     ("known_delivery_defects", known_delivery_defects),
                     ("legacy_ledger", legacy_ledger)):
        try:
            seeds[name] = fn()
        except Exception as exc:                                    # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    doc = {
        "kind": "measured behavioural seeds for the life-record blueprint",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "rule": "Every section names the symbol it was read from. Nothing here is a "
                "decision; decisions are in docs/wo/WO-HORNELORE-INTEGRATED-LIFE-RECORD-01_DECISIONS.md.",
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
