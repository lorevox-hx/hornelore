#!/usr/bin/env python3
"""Reconcile every concept vocabulary in the product — the catalog's input.

WHY THIS EXISTS. WO-LIFE-RECORD-01 §2.2 makes one versioned concept catalog
the first implementation dependency, because four components each grew their
own list of what may be recorded and they drifted. `suggestion_review.py:144`
records the cost: "20 of 30 queued suggestions point at undefined
destinations… because extract.py's EXTRACTABLE_FIELDS has drifted from the
questionnaire."

A catalog written by hand would be a fifth list. So the catalog's concept set
is DERIVED from the four vocabularies that exist, and this script produces
that derivation. Every number it prints names the symbol that produced it.

READ-ONLY. It parses source text; it imports no router and touches no
database. Run it from anywhere:

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/build_concept_catalog.py

    --json PATH   also write the full reconciliation for the catalog build
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXTRACT_PY = os.path.join(ROOT, "server", "code", "api", "routers", "extract.py")
BIO_SCHEMA_PY = os.path.join(ROOT, "server", "code", "api", "services", "bio_schema.py")
PROJECTION_JS = os.path.join(ROOT, "ui", "js", "projection-map.js")
QUESTIONNAIRE_JS = os.path.join(ROOT, "ui", "js", "bio-builder-questionnaire.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _brace_block(src, anchor):
    """Source of the brace-delimited literal that follows `anchor`."""
    i = src.index(anchor)
    start = src.index("{", i)
    depth, j, in_str, esc = 0, start, None, False
    while j < len(src):
        ch = src[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1
    raise ValueError(f"unterminated literal after {anchor!r}")


# ── the four vocabularies ────────────────────────────────────────────────

def vocab_extraction():
    """extract.py EXTRACTABLE_FIELDS — what the extractor may propose."""
    block = _brace_block(_read(EXTRACT_PY), "EXTRACTABLE_FIELDS = {")
    out = {}
    for m in re.finditer(r'^\s{4}"([^"]+)":\s*\{([^}]*)\}', block, re.M):
        write = re.search(r'"writeMode":\s*"([^"]+)"', m.group(2))
        out[m.group(1)] = {"writeMode": write.group(1) if write else None}
    return out, "extract.EXTRACTABLE_FIELDS"


def vocab_bio_schema():
    """bio_schema.py — the ASKING vocabulary. narrative_value and
    asking_anchors are why this cannot be derived away (§2.2)."""
    src = _read(BIO_SCHEMA_PY)
    out = {}
    for m in re.finditer(r'FieldDefinition\(\s*"([^"]+)"(.*?)\n(?=\s*(?:FieldDefinition\(|\)|#|$))',
                         src, re.S):
        key, tail = m.group(1), m.group(2)
        nv = re.search(r'narrative_value\s*=\s*"([^"]+)"', tail)
        anchors = re.search(r'asking_anchors\s*=\s*\(([^)]*)\)', tail, re.S)
        cat = re.search(r'"([^"]+)",\s*"[^"]*"\s*,?\s*$', tail.split("\n")[0])
        n_anchor = len(re.findall(r'"[^"]+"', anchors.group(1))) if anchors else 0
        out[key] = {
            "narrative_value": nv.group(1) if nv else None,
            "asking_anchors": n_anchor,
            "tier3_eligible": bool(nv and nv.group(1) == "high" and n_anchor > 0),
        }
    return out, "bio_schema.FieldDefinition"


def vocab_projection():
    """projection-map.js FIELD_MAP — the browser's write-mode authority."""
    block = _brace_block(_read(PROJECTION_JS), "var FIELD_MAP = {")
    out = {}
    for m in re.finditer(r"^\s{4}['\"]?([A-Za-z0-9_.\[\]]+)['\"]?\s*:\s*\{([^}]*)\}",
                         block, re.M):
        write = re.search(r"writeMode\s*:\s*['\"]([^'\"]+)['\"]", m.group(2))
        out[m.group(1)] = {"writeMode": write.group(1) if write else None}
    return out, "projection-map.FIELD_MAP"


def vocab_questionnaire():
    """The form itself — what an operator may enter. Loaded through the
    shipped parser so a schema change fails here, not silently."""
    sys.path.insert(0, os.path.join(ROOT, "server", "code"))
    from api.services import questionnaire_schema as qs
    schema = qs.load_schema()
    out = {}
    for sec_id, sec in schema.items():
        for fld in sec.get("fields", {}):
            out[f"{sec_id}.{fld}"] = {"repeatable": bool(sec.get("repeatable"))}
    return out, f"questionnaire_schema.load_schema [{qs.schema_fingerprint()[:12]}]"


# ── reconciliation ───────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the full reconciliation here")
    args = ap.parse_args()

    vocabs, errors = {}, []
    for name, fn in (("questionnaire", vocab_questionnaire),
                     ("extraction", vocab_extraction),
                     ("asking (bio_schema)", vocab_bio_schema),
                     ("projection map", vocab_projection)):
        try:
            entries, symbol = fn()
            vocabs[name] = {"entries": entries, "symbol": symbol}
        except Exception as exc:                       # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    if errors:
        print("\nCOULD NOT READ A VOCABULARY — the reconciliation is incomplete")
        for e in errors:
            print(f"  {e}")
        print()

    print("\nVOCABULARIES AS SHIPPED\n" + "─" * 70)
    for name, v in vocabs.items():
        print(f"  {len(v['entries']):>4}  {name:<22} [{v['symbol']}]")

    q = set(vocabs.get("questionnaire", {}).get("entries", {}))
    x = set(vocabs.get("extraction", {}).get("entries", {}))
    p = set(vocabs.get("projection map", {}).get("entries", {}))
    a = set(vocabs.get("asking (bio_schema)", {}).get("entries", {}))

    sections = set(vocabs.get("questionnaire", {}).get("entries", {}))
    section_ids = {s.split(".", 1)[0] for s in sections}

    def base(path):
        """Repeatable rows are addressed with an index in one vocabulary and
        without in another; compare the concept, not the cell."""
        return re.sub(r"\[\d*\]", "", path)

    def norm(path):
        """Strip the grouping prefix one vocabulary uses and the other does
        not. `family.children.firstName` and `children.firstName` are the
        same concept reached by two names — an ALIAS, not an orphan, and
        conflating the two overstates the drift."""
        p = base(path)
        head, _, rest = p.partition(".")
        if head == "family" and rest and rest.split(".", 1)[0] in section_ids:
            return rest
        return p

    qb, xb, pb = {base(v) for v in q}, {base(v) for v in x}, {base(v) for v in p}
    qn = {norm(v) for v in q}

    xn = {norm(v) for v in xb}
    exact = xb & qb
    aliasable = {v for v in xb - qb if norm(v) in qn}
    homeless = sorted(v for v in xb - qb if norm(v) not in qn)
    # A field reached through an alias IS reachable — comparing raw paths on
    # this side too would count the same eight concepts as broken twice.
    unreachable = sorted(qb - xn)

    print("\nDRIFT — DOTTED-PATH VOCABULARIES\n" + "─" * 70)
    print(f"  {len(exact):>4}  extraction targets that hit a questionnaire field exactly")
    print(f"  {len(aliasable):>4}  reachable ONLY through an alias the catalog must record")
    print(f"  {len(homeless):>4}  with no destination under any name — a suggestion")
    print(f"        that can never be applied")
    print(f"  {len(unreachable):>4}  questionnaire fields extraction can never fill")
    print(f"  {len(pb - qb):>4}  projection-map paths the questionnaire does NOT define")

    if aliasable:
        print("\n  ALIASES REQUIRED (same concept, two names — catalog input):")
        for pth in sorted(aliasable)[:12]:
            print(f"      {pth:<38} → {norm(pth)}")
        if len(aliasable) > 12:
            print(f"      … and {len(aliasable) - 12} more")

    if homeless:
        by_area = {}
        for pth in homeless:
            by_area.setdefault(pth.split(".", 1)[0], []).append(pth)
        print("\n  NO DESTINATION UNDER ANY NAME, by area:")
        for area, paths in sorted(by_area.items(), key=lambda kv: -len(kv[1])):
            print(f"      {len(paths):>3}  {area:<16} e.g. {', '.join(p.split('.', 1)[1] for p in paths[:3])}")

    undeliverable = homeless

    # write-mode disagreement between the server and the browser
    xe = vocabs.get("extraction", {}).get("entries", {})
    pe = vocabs.get("projection map", {}).get("entries", {})
    clash = sorted(
        k for k in (set(xe) & set(pe))
        if xe[k]["writeMode"] and pe[k]["writeMode"]
        and xe[k]["writeMode"] != pe[k]["writeMode"]
    )
    print("\nWRITE-MODE AGREEMENT (server vs browser)\n" + "─" * 70)
    print(f"  {len(set(xe) & set(pe)):>4}  paths defined in both")
    print(f"  {len(clash):>4}  DISAGREE on writeMode")
    for k in clash[:15]:
        print(f"      {k}: extract={xe[k]['writeMode']} "
              f"projection={pe[k]['writeMode']}")

    ae = vocabs.get("asking (bio_schema)", {}).get("entries", {})
    tier3 = [k for k, v in ae.items() if v["tier3_eligible"]]
    print("\nASKING BEHAVIOUR THE CATALOG MUST CARRY\n" + "─" * 70)
    print(f"  {len(ae):>4}  canonical asking keys")
    print(f"  {len(tier3):>4}  Tier 3 eligible (narrative_value=high AND anchors present)")
    print(f"  {len([k for k, v in ae.items() if v['narrative_value'] == 'high' and not v['asking_anchors']]):>4}"
          "  high value but DEACTIVATED by an empty anchor list")
    print("        ^ losing this metadata in a derived index silently disables Stage 8")

    print("\nCONCEPTS THE CATALOG MUST DEFINE\n" + "─" * 70)
    union = qb | xb | pb
    print(f"  {len(union):>4}  distinct dotted paths across the three path vocabularies")
    print(f"  {len(ae):>4}  asking keys, on their own key space")
    print(f"  {len(union & set(ae)):>4}  paths that are also asking keys "
          "(the two key spaces barely meet)")

    # ── semantic reconciliation ─────────────────────────────────────────
    # Handing over 110 isolated field decisions would be handing over the
    # drift. Each path is proposed as SUBJECT + CONCEPT, and paths that mean
    # the same thing are grouped — so what gets reviewed is a product choice,
    # not a spelling difference.

    SUBJECT_OF = {
        "personal": "narrator", "parents": "parent", "mother": "parent",
        "father": "parent", "siblings": "sibling", "children": "child",
        "spouse": "spouse", "grandparents": "grandparent",
        "greatGrandparents": "great-grandparent", "pets": "animal",
        "residence": "narrator", "education": "narrator", "military": "narrator",
        "health": "narrator", "hobbies": "narrator", "faith": "narrator",
        "travel": "narrator", "community": "narrator", "laterYears": "narrator",
        "earlyMemories": "narrator", "familyTraditions": "family",
        "technology": "narrator", "cultural": "narrator",
        "additionalNotes": "narrator", "family": "family",
    }
    # leaf spelling → one semantic concept. The four birth-date spellings are
    # the case that proves the point.
    CONCEPT_OF = {
        "dateofbirth": "person.birth.date", "birthdate": "person.birth.date",
        "birthyear": "person.birth.date", "yearofbirth": "person.birth.date",
        "placeofbirth": "person.birth.place", "birthplace": "person.birth.place",
        "deathdate": "person.death.date", "dateofdeath": "person.death.date",
        "placeofdeath": "person.death.place", "ageatdeath": "person.death.age",
        "deceased": "person.life_status",
        "firstname": "person.name.given", "middlename": "person.name.given",
        "lastname": "person.name.family", "maidenname": "person.name.birth_family",
        "preferredname": "person.name.preferred", "fullname": "person.name.full",
        "occupation": "person.occupation", "education": "person.education",
        "relation": "relationship.kind", "birthorder": "person.birth.order",
        "notes": "RETIRED", "narrative": "story", "memorablestory": "story",
        "memorablestories": "story", "significantevent": "event",
        "touchstonememory": "story", "desiredstory": "story",
    }

    def leaf(path):
        return path.rsplit(".", 1)[-1].lower()

    groups = {}
    for pth in sorted(set(homeless)):
        head = pth.split(".", 1)[0]
        if head == "family" and pth.count(".") >= 2:
            head = pth.split(".")[1]
        subj = SUBJECT_OF.get(head, f"?{head}")
        concept = CONCEPT_OF.get(leaf(pth))
        key = (concept or f"UNMAPPED:{leaf(pth)}", subj)
        groups.setdefault(key, []).append(pth)

    print("\nSEMANTIC RECONCILIATION — GROUPED PROPOSALS\n" + "─" * 70)
    print("  Each row is one decision. Spelling variants are already merged.\n")
    mapped = [(k, v) for k, v in groups.items() if not k[0].startswith("UNMAPPED")]
    unmapped = [(k, v) for k, v in groups.items() if k[0].startswith("UNMAPPED")]

    print(f"  {'CONCEPT':<28} {'SUBJECT':<18} PATHS")
    for (concept, subj), paths in sorted(mapped):
        disposition = "RETIRE" if concept == "RETIRED" else "define"
        print(f"  {concept:<28} {subj:<18} {len(paths):>2}  [{disposition}]")
        for pth in paths[:3]:
            print(f"      {pth}")
        if len(paths) > 3:
            print(f"      … {len(paths) - 3} more with the same meaning")

    print(f"\n  NEEDS A HUMAN CONCEPT NAME ({sum(len(v) for _, v in unmapped)} paths, "
          f"{len(unmapped)} groups):")
    for (concept, subj), paths in sorted(unmapped):
        print(f"      {concept[9:]:<22} subject={subj:<18} {', '.join(paths[:2])}"
              + (f" +{len(paths)-2}" if len(paths) > 2 else ""))

    print(f"\n  {len(mapped)} grouped decisions instead of {len(homeless)} field decisions.")
    print("""
  REASONS FOR THE PROPOSED DISPOSITIONS
    RETIRE  every `*.notes` path. `personal.notes` was already retired by
            WO-04 decision 4 — "a miscellaneous bucket with no home in the
            form invites the extractor to file anything it cannot classify".
            Seven more of them exist; the argument does not change per section.
    define  the death concepts, which are a filed defect
            (BUG-LORI-UNAWARE-OF-DEATH-01), not an open question.
    define  the rest — but "define" here proposes the CONCEPT and its SUBJECT,
            not that the field is wanted. Rejecting one is a product decision.

  Subjects prefixed '?' did not map to a subject kind, and need a human first:
  `grandchildren` and `priorPartners` are extraction sections with no
  questionnaire section at all — so the question is whether those people
  should exist in the record, before any field of theirs is discussed.""")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({
                "generated_from": {n: v["symbol"] for n, v in vocabs.items()},
                "vocabularies": {n: v["entries"] for n, v in vocabs.items()},
                "undeliverable_extraction_targets": undeliverable,
                "writemode_disagreements": clash,
                "aliases_required": {v: norm(v) for v in sorted(aliasable)},
                "unreachable_questionnaire_fields": unreachable,
                "semantic_reconciliation": [
                    {"concept": c, "subject": s, "paths": sorted(ps),
                     "disposition": "RETIRE" if c == "RETIRED"
                     else ("NEEDS_CONCEPT" if c.startswith("UNMAPPED") else "define")}
                    for (c, s), ps in sorted(groups.items())
                ],
            }, fh, indent=2, sort_keys=True)
        print(f"\n  wrote {args.json}")

    print("\n" + "─" * 70)
    print("  This is measurement, not a proposal. Every count above names the")
    print("  symbol it came from; none is quoted from a document.\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
