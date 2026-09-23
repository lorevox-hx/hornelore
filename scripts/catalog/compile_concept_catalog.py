#!/usr/bin/env python3
"""Compile the concept catalog. WO-HORNELORE-INTEGRATED-LIFE-RECORD-01, Batch A1.

    semantic source (concept_catalog_source.py)      — human judgements
  + measured vocabularies (the shipped code)         — what exists, write modes,
                                                       Tier-3 asking, sections
  + Chris's recorded decisions (DECISIONS.md)        — what is approved
  ─────────────────────────────────────────────────────────────────────────
  = server/code/api/services/concept_catalog_v1.json

FAIL-CLOSED. The compile refuses, writing nothing, if:
  • any path, asking key or Profile Seed evidence path is unbound;
  • a binding names a concept the source does not define, or a defined
    concept is bound by nothing (a typo either way);
  • a retirement or override names a path no vocabulary contains;
  • any decision a binding depends on is not `approved`.

DETERMINISTIC. No timestamps. The same inputs give the same bytes, so
`tests/test_concept_catalog.py` can require the committed file to equal a
fresh compile. It fingerprints the MEASURED VOCABULARIES rather than whole
files: an unrelated edit to extract.py does not invalidate the catalog, but a
change to what it can extract does.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONPATH=server/code \\
      python3 scripts/catalog/compile_concept_catalog.py            # write
    ... compile_concept_catalog.py --check                           # compare only
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "server", "code"))
OUT = os.path.join(ROOT, "server", "code", "api", "services", "concept_catalog_v1.json")
APPENDIX = os.path.join(ROOT, "docs", "specs", "CONCEPT-DECISION-APPENDIX.md")
PROJECTION_JS = os.path.join(ROOT, "ui", "js", "projection-map.js")
COMPILER_VERSION = "concept-catalog-compiler/1"


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _base(path):
    return re.sub(r"\[\d*\]", "", path)


def _split(path):
    parts = _base(path).split(".")
    return ".".join(parts[:-1]), parts[-1]


class CompileRefused(Exception):
    pass


def _repeatable_write_modes():
    """projection-map.js REPEATABLE_TEMPLATES: section -> writeMode. With
    FIELD_MAP this is everything `getWriteMode` consults; any other path falls
    to its safe default, suggest_only (projection-map.js getWriteMode)."""
    src = _read_text(PROJECTION_JS)
    bcc = _load("bcc", "scripts/design/build_concept_catalog.py")
    block = bcc._brace_block(src, "var REPEATABLE_TEMPLATES = {")
    out = {}
    for m in re.finditer(r"^\s{4}(\w+):\s*\{\s*\n\s*writeMode:\s*\"([^\"]+)\"", block, re.M):
        out[m.group(1)] = m.group(2)
    return out


def _browser_write_mode(path, field_map, repeatable):
    """What the browser would do with this path — the server can only LOWER
    it (projection-sync.js:364-367), so this is the ceiling."""
    b = _base(path)
    if b in field_map and field_map[b].get("writeMode"):
        return field_map[b]["writeMode"]
    section = b.split(".")[0]
    if section in repeatable:
        return repeatable[section]
    return "suggest_only"


def _appendix_groups():
    """path -> appendix group id (B/A/G/Q), parsed from the generated appendix."""
    out = {}
    for line in _read_text(APPENDIX).splitlines():
        m = re.match(r"^\| ([ABGQ]\d{2}) \|(.*)$", line)
        if not m:
            continue
        for p in re.findall(r"`([A-Za-z][\w.]*\.[\w.]+)`", m.group(2)):
            out.setdefault(p, []).append(m.group(1))
    return out


def _appendix_alias_pairs():
    """D1a/D1b: the DECIDED aliases, path by path, from the appendix. `A` rows
    are (extractor path, form path); `B` rows are (concept, subject, extractor
    paths, form paths). Pairs are taken as written, never inferred from a
    shared concept: `spouse.firstName` and `spouse.middleName` are both
    person.name.given, so concept equality alone would be ambiguous."""
    pairs = {}
    for line in _read_text(APPENDIX).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not re.match(r"^[AB]\d{2}$", cells[0]):
            continue
        tick = lambda c: re.findall(r"`([^`]+)`", c)
        if cells[0].startswith("A") and len(cells) >= 3:
            ext, form = tick(cells[1]), tick(cells[2])
        elif cells[0].startswith("B") and len(cells) >= 5:
            ext, form = tick(cells[3]), tick(cells[4])
        else:
            continue
        if len(form) != 1:
            continue
        for e in ext:
            pairs[e] = (form[0], cells[0])
    return pairs


def compile_catalog():
    src = _load("concept_catalog_source", "server/code/api/services/concept_catalog_source.py")
    bcc = _load("bcc", "scripts/design/build_concept_catalog.py")
    seeds = _load("seeds", "scripts/design/export_behaviour_seeds.py")
    problems = []

    # ── measure ──────────────────────────────────────────────────────────
    q, q_sym = bcc.vocab_questionnaire()
    x, x_sym = bcc.vocab_extraction()
    pm, pm_sym = bcc.vocab_projection()
    asking = {r["field_key"]: r for r in seeds.asking()["rows"]}
    topics = seeds.profile_seed()["rows"]
    decisions = {r["decision_id"]: r for r in seeds.decisions()["rows"]}
    repeatable = _repeatable_write_modes()
    groups_of = _appendix_groups()
    alias_pairs = _appendix_alias_pairs()
    group_decision = {}
    for d in decisions.values():
        for g in d["affected_group_ids"]:
            group_decision.setdefault(g, set()).add(d["decision_id"])

    vocab_of = {}
    for name, vocab in (("questionnaire", q), ("extraction", x), ("projection_map", pm)):
        for p in vocab:
            vocab_of.setdefault(_base(p), set()).add(name)
    # A RETIRED path stays in the catalog after its producer drops it (A3,
    # 2026-09-23): stored values may still sit at it (A5 keeps them), and
    # the decision that retired it must stay findable. It keeps a row with
    # `in: []` — present in no vocabulary, which is what retired means.
    all_paths = sorted(set(vocab_of) | set(src.RETIRED))

    # ── typo guards on the source ────────────────────────────────────────
    for p in src.CONCEPT_BY_PATH:
        if p not in vocab_of:
            problems.append(f"source names `{p}`, which no vocabulary contains")
    for p in src.RETIRED:
        # Once gone from every vocabulary, the only thing that proves a
        # retired path is not a typo is the decision record that named it.
        if p not in vocab_of and p not in groups_of:
            problems.append(f"RETIRED `{p}` is in no vocabulary and no decision group — a typo?")
    for p, d in src.EXTRACTION_RETIRED.items():
        # Retired from extraction ONLY: the path must still be a form field and
        # must not also be retired outright, or the two tables disagree.
        if p in src.RETIRED:
            problems.append(f"`{p}` is in both RETIRED and EXTRACTION_RETIRED")
        elif "questionnaire" not in vocab_of.get(p, ()):
            problems.append(f"EXTRACTION_RETIRED `{p}` is not a questionnaire field — "
                            "retire the path outright instead")
        if not d:
            problems.append(f"EXTRACTION_RETIRED `{p}` names no decision")
    # A3 (2026-09-23) EXECUTED these retirements in the producer. A retired
    # path the extractor still offers is a retirement that did not happen --
    # the catalog would call it ineligible while extract.py kept teaching it.
    for p, d in list(src.RETIRED.items()) + list(src.EXTRACTION_RETIRED.items()):
        if "extraction" in vocab_of.get(p, ()):
            problems.append(f"`{p}` is retired from extraction ({d}) but "
                            "EXTRACTABLE_FIELDS still offers it")
    for k in src.ASKING_KEY_BINDINGS:
        if k not in asking:
            problems.append(f"ASKING_KEY_BINDINGS names `{k}`, not a bio_schema key")
    for k in asking:
        if k not in src.ASKING_KEY_BINDINGS:
            problems.append(f"UNBOUND asking key `{k}`")

    # ── path bindings ────────────────────────────────────────────────────
    path_rows = []
    for p in all_paths:
        section, field = _split(p)
        subject = src.SUBJECT_BY_SECTION.get(section)
        row = {"path": p, "in": sorted(vocab_of.get(p, ())), "section": section,
               "subject": subject, "groups": sorted(groups_of.get(p, []))}
        if p in src.RETIRED:
            row.update(disposition="retired", concept_id=None,
                       decision_ids=[src.RETIRED[p]])
        else:
            concept = src.CONCEPT_BY_PATH.get(p) or src.CONCEPT_BY_FIELD.get(field)
            if subject is None:
                problems.append(f"UNBOUND section `{section}` (path `{p}`)")
            if concept is None:
                problems.append(f"UNBOUND path `{p}` (field `{field}`)")
            row.update(disposition="derived" if concept in src.DERIVED_CONCEPTS else "bind",
                       concept_id=concept,
                       decision_ids=sorted({d for g in row["groups"]
                                            for d in group_decision.get(g, ())}))
        row["extraction_member"] = "extraction" in row["in"]
        # D11-style: bound and editable, but no longer offered to the extractor.
        row["extraction_retired_by"] = ([src.EXTRACTION_RETIRED[p]]
                                        if p in src.EXTRACTION_RETIRED else [])
        if row["extraction_retired_by"]:
            row["decision_ids"] = sorted(set(row["decision_ids"])
                                         | set(row["extraction_retired_by"]))
        row["browser_write_mode"] = (_browser_write_mode(p, pm, repeatable)
                                     if row["extraction_member"] else None)
        path_rows.append(row)

    # decided aliases (D1a/D1b): the extractor's spelling → the form's field.
    # Refused unless both sides really are the same fact about the same person.
    by_path = {r["path"]: r for r in path_rows}
    for ext, (form, dec) in getattr(src, "ALIASES_ADDED", {}).items():
        if ext in alias_pairs:
            problems.append(f"ALIASES_ADDED `{ext}` is already an appendix alias")
        alias_pairs[ext] = (form, dec)
        if ext in by_path:
            by_path[ext]["decision_ids"] = sorted(set(by_path[ext]["decision_ids"]) | {dec})
    for ext, (form, gid) in sorted(alias_pairs.items()):
        e, f = by_path.get(ext), by_path.get(form)
        if e is None or f is None:
            problems.append(f"alias {gid}: `{ext}` → `{form}` names a path no vocabulary contains")
            continue
        if "questionnaire" not in f["in"]:
            problems.append(f"alias {gid}: target `{form}` is not a questionnaire field")
        if (e["concept_id"], e["subject"]) != (f["concept_id"], f["subject"]):
            problems.append(f"alias {gid}: `{ext}` is {e['concept_id']}/{e['subject']} but "
                            f"`{form}` is {f['concept_id']}/{f['subject']} — not the same fact")
        e["alias_of"] = form
    for r in path_rows:
        r.setdefault("alias_of", None)

    # alias: two paths, same concept and subject, one of them the extractor's
    by_cs = {}
    for r in path_rows:
        if r["concept_id"]:
            by_cs.setdefault((r["concept_id"], r["subject"]), []).append(r["path"])
    for r in path_rows:
        if r["concept_id"]:
            others = [o for o in by_cs[(r["concept_id"], r["subject"])] if o != r["path"]]
            r["same_fact_as"] = sorted(others)

    asking_rows = []
    for k in sorted(asking):
        if k not in src.ASKING_KEY_BINDINGS:
            continue
        concept, subject = src.ASKING_KEY_BINDINGS[k]
        a = asking[k]
        asking_rows.append({"key": k, "concept_id": concept, "subject": subject,
                            "narrative_value": a["narrative_value"],
                            "tier3_eligible": a["tier3_eligible"],
                            "anchor_count": len(a["asking_anchors"]),
                            "life_stage_range": a.get("life_stage_range")})

    seed_rows = []
    for t in topics:
        for kind in ("profile_paths", "projection_paths"):
            for p in t[kind]:
                if p in src.PROFILE_SEED_PATH_BINDINGS:
                    concept, subject = src.PROFILE_SEED_PATH_BINDINGS[p]
                    how = "profile_seed_binding"
                elif p in vocab_of and p not in src.RETIRED:
                    s_, f_ = _split(p)
                    concept = src.CONCEPT_BY_PATH.get(p) or src.CONCEPT_BY_FIELD.get(f_)
                    subject = src.SUBJECT_BY_SECTION.get(s_)
                    how = "path_binding"
                else:
                    problems.append(f"UNBOUND Profile Seed {kind[:-1]} `{p}` (topic {t['topic_id']})")
                    continue
                seed_rows.append({"topic_id": t["topic_id"], "kind": kind[:-6], "path": p,
                                  "concept_id": concept, "subject": subject, "how": how,
                                  # profile_json is written by the profile save path, which
                                  # is not one of the measured vocabularies — so the check is
                                  # only meaningful for PROJECTION paths.
                                  "producer_vocabulary": (("present" if p in vocab_of else "none")
                                                          if kind == "projection_paths"
                                                          else "profile_json (not measured)"),
                                  "negative_meaningful": t["negative_meaningful"]})
        for k in t["bio_keys"]:
            if k in src.ASKING_KEY_BINDINGS:
                concept, subject = src.ASKING_KEY_BINDINGS[k]
                seed_rows.append({"topic_id": t["topic_id"], "kind": "bio_key", "path": k,
                                  "concept_id": concept, "subject": subject,
                                  "how": "asking_binding", "producer_vocabulary": "bio_schema",
                                  "negative_meaningful": t["negative_meaningful"]})

    profile_rows = [{"key": k, "concept_id": c_, "subject": s_}
                    for k, (c_, s_) in sorted(src.PROFILE_JSON_BINDINGS.items())]

    # ── concepts ─────────────────────────────────────────────────────────
    used = ({r["concept_id"] for r in path_rows if r["concept_id"]}
            | {r["concept_id"] for r in profile_rows}
            | {r["concept_id"] for r in asking_rows}
            | {r["concept_id"] for r in seed_rows})
    for c in sorted(used - set(src.CONCEPTS)):
        problems.append(f"binding names undefined concept `{c}`")
    for c in sorted(set(src.CONCEPTS) - used):
        problems.append(f"concept `{c}` is defined but bound by nothing")

    rank = {"low": 1, "medium": 2, "high": 3}
    concepts = []
    for cid in sorted(src.CONCEPTS):
        label, vtype, card = src.CONCEPTS[cid]
        prows = [r for r in path_rows if r["concept_id"] == cid]
        arows = [r for r in asking_rows if r["concept_id"] == cid]
        in_form = any("questionnaire" in r["in"] for r in prows)
        # Eligibility comes only from paths still offered to the extractor.
        x_rows = [r for r in prows
                  if r["extraction_member"] and not r["extraction_retired_by"]]
        added = cid in src.EXTRACTION_ADDED
        added_dec, added_scope = src.EXTRACTION_ADDED.get(cid, (None, ()))
        nv = max((a["narrative_value"] for a in arows if a["narrative_value"]),
                 key=lambda v: rank.get(v, 0), default=None)
        derived = cid in src.DERIVED_CONCEPTS
        prefix = cid.split(".")[0]
        dec = sorted({d for r in prows for d in r["decision_ids"]}
                     | ({src.DERIVED_CONCEPTS[cid]} if derived else set())
                     | ({added_dec} if added else set()))
        concepts.append({
            "concept_id": cid, "label": label, "subject_kind": prefix,
            "value_type": vtype, "cardinality": card,
            # ── the four independent properties (D1f); none defaults from another
            "questionnaire": ("derived_readonly" if derived else
                              "editable" if in_form else "not_offered"),
            "extraction": {
                "eligible": bool(x_rows) or added,
                "scope": sorted({r["section"] for r in x_rows} | set(added_scope)),
                "write_mode": "per_binding",
            },
            "lori": {
                # Asking keys carry a subject: a father's name being Tier-3
                # says nothing about a friend's. Per subject, measured; the
                # concept-level value is only the summary.
                "askable_by_subject": ({} if derived else {
                    s_: ("proactive" if any(a["tier3_eligible"] for a in arows
                                            if a["subject"] == s_) else "responsive_only")
                    for s_ in sorted({a["subject"] for a in arows})}),
                "askable": ("never" if derived else
                            "proactive" if any(a["tier3_eligible"] for a in arows) else
                            "responsive_only"),
                "retrievable": not derived,
                "prompt_role": src.PROMPT_ROLE.get(cid, {"narrator": "retrieved",
                                                         "other": "retrieved"}),
            },
            "narrative_value": nv or "unassessed",
            "special_projection": src.SPECIAL_PROJECTION.get(cid),
            "memoir": {"route": ("trip_notes_lane" if prefix == "trip" else
                                 "from_record_origin" if prefix == "story" else
                                 "operator_use_only")},
            "storage": {"owner": "trip_domain" if prefix == "trip" else "life_record",
                        "entity": prefix,
                        "db_lane": ("existing trip_* lanes" if prefix == "trip"
                                    else "pending — Batch B tables")},
            "decision_ids": dec,
            "provenance": {
                "questionnaire": "measured: questionnaire_schema.load_schema",
                "extraction": ("measured: EXTRACTABLE_FIELDS sections"
                               + (f" + decision {added_dec}" if added else "")),
                "lori.askable": ("rule: derived concepts are not asked" if derived else
                                 "measured: bio_schema Tier-3 eligibility of bound asking keys"),
                "lori.prompt_role": ("source: PROMPT_ROLE (identity_facts, prompt_composer.py:576-602; "
                                     "WO-LIFE-RECORD-01 §9.1)" if cid in src.PROMPT_ROLE
                                     else "default: retrieved"),
                "narrative_value": ("measured: max over bound asking keys" if nv
                                    else "unassessed: no asking key binds this concept"),
                "memoir": "rule: WO-LIFE-RECORD-01 §2.6/§9.2",
            },
        })

    # ── the build gate ───────────────────────────────────────────────────
    needed = {d for c in concepts for d in c["decision_ids"]} | {
        d for r in path_rows for d in r["decision_ids"]}
    for d in sorted(needed):
        if decisions.get(d, {}).get("state") != "approved":
            problems.append(f"decision {d} is not approved — catalog is not buildable")

    if problems:
        raise CompileRefused(problems)

    measured = {"questionnaire": sorted(q), "extraction": {k: x[k] for k in sorted(x)},
                "projection_map": {k: pm[k] for k in sorted(pm)},
                "asking": {k: asking[k] for k in sorted(asking)}, "profile_seed": topics}
    return {
        "catalog_version": src.CATALOG_VERSION,
        "compiler": COMPILER_VERSION,
        "rule": "Compiled, not hand-edited. Change concept_catalog_source.py or the "
                "producers and recompile; tests fail if this file differs from a fresh compile.",
        "fingerprints": {
            "measured_vocabularies_sha256": _sha(measured),
            "questionnaire_schema": q_sym,
            "semantic_source_sha256": _sha({k: getattr(src, k) for k in dir(src)
                                           if k.isupper()}),
            "decisions_sha256": _sha({d: (v["state"], v["refinement"]) for d, v in decisions.items()}),
        },
        "decisions_used": {d: {"state": decisions[d]["state"],
                               "refinement": decisions[d]["refinement"]} for d in sorted(needed)},
        "reconciliations": src.RECONCILIATIONS,
        "counts": {
            "concepts": len(concepts),
            "paths": len(path_rows),
            "paths_retired": sum(r["disposition"] == "retired" for r in path_rows),
            "asking_keys": len(asking_rows),
            "profile_seed_evidence": len(seed_rows),
            "profile_seed_projection_paths_in_no_producing_vocabulary": sorted(
                {r["path"] for r in seed_rows if r["producer_vocabulary"] == "none"}),
        },
        "concepts": concepts,
        "bindings": {"paths": path_rows, "asking_keys": asking_rows,
                     "profile_seed": seed_rows, "profile_json": profile_rows},
    }


def render(catalog):
    return json.dumps(catalog, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare a fresh compile with the committed file; write nothing")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    try:
        cat = compile_catalog()
    except CompileRefused as e:
        print("COMPILE REFUSED — nothing written:")
        for p in e.args[0]:
            print("  •", p)
        return 2
    text = render(cat)
    if a.check:
        same = os.path.exists(a.out) and _read_text(a.out) == text
        print("catalog is current" if same else "catalog is STALE — recompile")
        return 0 if same else 1
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    c = cat["counts"]
    print(f"  {c['concepts']} concepts · {c['paths']} paths ({c['paths_retired']} retired) · "
          f"{c['asking_keys']} asking keys · {c['profile_seed_evidence']} Profile Seed evidence rows")
    print(f"  wrote {os.path.relpath(a.out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
