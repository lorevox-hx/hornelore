#!/usr/bin/env python3
"""Build question_bank_extraction_cases_v2.json from v1 — A3 (2026-09-23).

The v1 bank is NOT modified. It stays the runner's default, so every
historical report keeps its `case_bank_version` (b487e54cd84d) and a live run
with no `--cases` stays comparable to B0/B1.

v2 changes ONLY expectations that the decided vocabulary makes wrong, and
records every change in the case's `_migration` list. Four rules, each tied
to a decision; nothing else is touched:

  M1  D12 same-fact rename, every zone plus expectedFields/forbiddenFields:
        family.marriageDate  → marriage.marriageDate
        family.marriagePlace → marriage.marriagePlace
      A must_not_write keeps its meaning only if it follows the rename.
  M2  WO-04 same-fact rename of a FORBIDDEN narrator path:
        military.deploymentLocation → military.location
        military.yearsOfService     → military.serviceStart + military.serviceEnd
      (must_not_write only — a forbidden fact stays forbidden.)
  M3  The ancestor-military duplication (_ANCESTOR_MIL_DUP_MAP, removed in
      A3). case_033 / case_034 expected a GREAT-GRANDFATHER's Civil War
      service under the NARRATOR's military.*. Rewritten to the ancestor's
      own fields, and the narrator's branch/unit made must_not_write.
  M4  must_extract / may_extract on a path the decided vocabulary no longer
      offers the extractor is REMOVED (not moved, not guessed):
        retired from extraction — pets.notes, family.marriageNotes (D11/D1e),
          health.majorCondition (D3);
        retired by WO-04 with no same-fact destination — faith.values,
          residence.period;
      plus one bank typo: faith.significantMoment → faith.significantMoments.

Zones that cannot be satisfied or violated either way (should_ignore and
must_not_write on paths nobody can emit) are left alone — changing them
would move nothing and add noise to the ledger.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/eval/migrate_case_bank_v2.py            # writes v2
    python3 scripts/eval/migrate_case_bank_v2.py --check    # v2 is current?
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V1 = REPO / "data" / "qa" / "question_bank_extraction_cases.json"
V2 = REPO / "data" / "qa" / "question_bank_extraction_cases_v2.json"

RENAME_ALL = {  # M1 — D12
    "family.marriageDate": "marriage.marriageDate",
    "family.marriagePlace": "marriage.marriagePlace",
}
RENAME_FORBIDDEN = {  # M2 — WO-04
    "military.deploymentLocation": ["military.location"],
    "military.yearsOfService": ["military.serviceStart", "military.serviceEnd"],
}
REMOVE_EXPECTED = {  # M4
    "pets.notes": "D11 — retired from extraction; the story lane keeps pet stories",
    "family.marriageNotes": "D1e — retired from extraction; a notes bucket",
    "health.majorCondition": "D3 — diagnoses are not extracted",
    "faith.values": "WO-04 — retired, no same-fact destination",
    "residence.period": "WO-04 — free-text period retired; a duration is not a year",
}
TYPO = {"faith.significantMoment": "faith.significantMoments"}  # M4

ANCESTOR = {  # M3 — rewritten whole, from the narrator's words
    "case_033": {
        "remove": ["military.branch", "military.yearsOfService",
                   "military.deploymentLocation", "military.significantEvent"],
        "zones": {
            "greatGrandparents.militaryBranch": {"zone": "must_extract", "expected": "Army"},
            "greatGrandparents.militaryUnit": {"zone": "must_extract",
                                               "expected": "Company G, 28th Infantry"},
            "greatGrandparents.militaryEvent": {"_multi": [
                {"zone": "must_extract", "expected": "Civil War"},
                {"zone": "may_extract", "expected": "1865-1866"},
                {"zone": "may_extract", "expected": "Kansas and Missouri"}]},
            "military.branch": {"zone": "must_not_write"},
            "military.unit": {"zone": "must_not_write"},
        },
        "fields": {"greatGrandparents.militaryBranch": "Army",
                   "greatGrandparents.militaryUnit": "Company G, 28th Infantry",
                   "greatGrandparents.militaryEvent": "Civil War"},
        "why": "M3: the great-grandfather's service, not the narrator's",
    },
    "case_034": {
        "remove": ["military.significantEvent"],
        "zones": {
            "greatGrandparents.militaryEvent": {"zone": "must_extract", "expected": "Civil War"},
        },
        "fields": {"greatGrandparents.militaryEvent": "Civil War"},
        "why": "M3: the narrator never served; the Civil War service is his ancestor's",
    },
}


def _zone_of(rec):
    return rec.get("zone") if isinstance(rec, dict) and "_multi" not in rec else "_multi"


def migrate_case(c: dict) -> dict:
    c = copy.deepcopy(c)
    log = []
    tz = c.get("truthZones") or {}
    ef = c.get("expectedFields") or {}
    ff = c.get("forbiddenFields") or []

    if c["id"] in ANCESTOR:
        spec = ANCESTOR[c["id"]]
        for p in spec["remove"]:
            if p in tz:
                log.append(f"M3 removed {_zone_of(tz[p])} {p}")
                tz.pop(p)
            ef.pop(p, None)
        for p, rec in spec["zones"].items():
            tz[p] = rec
            log.append(f"M3 set {_zone_of(rec)} {p}")
        ef.update(spec["fields"])
        log.append(spec["why"])

    for old, new in RENAME_ALL.items():
        if old in tz:
            tz[new] = tz.pop(old)
            log.append(f"M1 {_zone_of(tz[new])} {old} → {new}")
        if old in ef:
            ef[new] = ef.pop(old)
        if old in ff:
            ff[ff.index(old)] = new
            log.append(f"M1 forbiddenFields {old} → {new}")

    for old, news in RENAME_FORBIDDEN.items():
        if old in tz and _zone_of(tz[old]) == "must_not_write":
            tz.pop(old)
            for n in news:
                tz.setdefault(n, {"zone": "must_not_write"})
            log.append(f"M2 must_not_write {old} → {' + '.join(news)}")

    for old, new in TYPO.items():
        if old in tz:
            tz[new] = tz.pop(old)
            log.append(f"M4 typo {old} → {new}")
        if old in ef:
            ef[new] = ef.pop(old)

    for p, why in REMOVE_EXPECTED.items():
        if p in tz and _zone_of(tz[p]) in ("must_extract", "may_extract"):
            log.append(f"M4 removed {_zone_of(tz[p])} {p} ({why})")
            tz.pop(p)
        if p in ef:
            ef.pop(p)

    c["truthZones"], c["expectedFields"], c["forbiddenFields"] = tz, ef, ff
    if log:
        c["_migration"] = log
    return c


def build() -> dict:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    v2 = copy.deepcopy(v1)
    v2["cases"] = [migrate_case(c) for c in v1["cases"]]
    v2["_version"] = f"{v1.get('_version', '1')}+a3-v2"
    v2["_migration"] = {
        "from": V1.name,
        "from_sha12": hashlib.sha256(V1.read_bytes()).hexdigest()[:12],
        "by": "scripts/eval/migrate_case_bank_v2.py",
        "rules": ["M1 D12 rename", "M2 WO-04 forbidden rename",
                  "M3 ancestor-military correction", "M4 retired-path removal + typo"],
        "cases_changed": sorted(c["id"] for c in v2["cases"] if c.get("_migration")),
    }
    return v2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if a.check:
        ok = V2.exists() and V2.read_text(encoding="utf-8") == text
        print("v2 is current" if ok else "v2 is STALE — rerun without --check")
        return 0 if ok else 1
    V2.write_text(text, encoding="utf-8")
    v2 = json.loads(text)
    print(f"wrote {V2.relative_to(REPO)}  sha12="
          f"{hashlib.sha256(V2.read_bytes()).hexdigest()[:12]}  "
          f"cases changed: {len(v2['_migration']['cases_changed'])}")
    for c in v2["cases"]:
        for line in c.get("_migration", []):
            print(f"  {c['id']}  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
