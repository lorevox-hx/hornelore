"""The concept catalog — loader and queries. WO-HORNELORE-INTEGRATED-LIFE-RECORD-01, Batch A1.

Reads the COMPILED `concept_catalog_v1.json` (built by
scripts/catalog/compile_concept_catalog.py from concept_catalog_source.py, the
measured vocabularies and Chris's recorded decisions). Nothing in the product
edits the JSON; nothing here writes.

FAIL-CLOSED ON LOAD. A catalog that is malformed does not half-load: every
concept must STATE all four independent properties (questionnaire,
extraction, lori, narrative_value — D1f; none defaults from another), every
binding must resolve to a defined concept, no path may be bound twice, and
every retirement must name its decision. Any violation raises
`CatalogInvalid` with every problem found, not just the first.

LAW 3: standard library only. No DB, no extraction stack, no network.
"""

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "concept_catalog_v1.json")

QUESTIONNAIRE_VALUES = {"editable", "derived_readonly", "not_offered"}
ASKABLE_VALUES = {"proactive", "responsive_only", "never"}
PROMPT_ROLES = {"constant", "turn_scoped", "retrieved", "never"}
NARRATIVE_VALUES = {"high", "medium", "low", "unassessed"}
MEMOIR_ROUTES = {"operator_use_only", "from_record_origin", "trip_notes_lane"}
DISPOSITIONS = {"bind", "derived", "retired"}


class CatalogInvalid(Exception):
    """The catalog failed validation. `.problems` lists every violation."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} catalog problem(s): " + "; ".join(problems[:5]))


def _base(path: str) -> str:
    return re.sub(r"\[\d*\]", "", path)


def validate(cat: Dict[str, Any]) -> List[str]:
    """Every violation in `cat`. Empty list means valid."""
    p: List[str] = []
    concepts = cat.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        return ["catalog has no concepts"]
    ids = [c.get("concept_id") for c in concepts]
    if len(ids) != len(set(ids)):
        p.append("duplicate concept ids")
    defined = set(ids)

    for c in concepts:
        cid = c.get("concept_id", "?")
        for prop in ("questionnaire", "extraction", "lori", "narrative_value"):
            if prop not in c:
                p.append(f"{cid}: does not state `{prop}` (D1f: every property explicit)")
        if c.get("questionnaire") not in QUESTIONNAIRE_VALUES:
            p.append(f"{cid}: questionnaire={c.get('questionnaire')!r}")
        ex = c.get("extraction") or {}
        if not isinstance(ex.get("eligible"), bool):
            p.append(f"{cid}: extraction.eligible must be a bool")
        if not isinstance(ex.get("scope"), list):
            p.append(f"{cid}: extraction.scope must be a list")
        elif ex.get("eligible") and not ex["scope"]:
            p.append(f"{cid}: eligible for extraction but offered in no scope")
        elif not ex.get("eligible") and ex["scope"]:
            p.append(f"{cid}: not eligible for extraction but has a scope")
        lori = c.get("lori") or {}
        if lori.get("askable") not in ASKABLE_VALUES:
            p.append(f"{cid}: lori.askable={lori.get('askable')!r}")
        for s, v in (lori.get("askable_by_subject") or {}).items():
            if v not in ASKABLE_VALUES:
                p.append(f"{cid}: askable_by_subject[{s}]={v!r}")
        if not isinstance(lori.get("retrievable"), bool):
            p.append(f"{cid}: lori.retrievable must be a bool")
        role = lori.get("prompt_role") or {}
        if set(role) != {"narrator", "other"} or not set(role.values()) <= PROMPT_ROLES:
            p.append(f"{cid}: lori.prompt_role={role!r}")
        if c.get("narrative_value") not in NARRATIVE_VALUES:
            p.append(f"{cid}: narrative_value={c.get('narrative_value')!r}")
        if (c.get("memoir") or {}).get("route") not in MEMOIR_ROUTES:
            p.append(f"{cid}: memoir.route={(c.get('memoir') or {}).get('route')!r}")
        if c.get("questionnaire") == "derived_readonly" and lori.get("askable") != "never":
            p.append(f"{cid}: a derived concept must not be asked for")

    b = cat.get("bindings") or {}
    seen = set()
    for r in b.get("paths", []):
        path = r.get("path")
        if path in seen:
            p.append(f"path `{path}` is bound twice")
        seen.add(path)
        if r.get("disposition") not in DISPOSITIONS:
            p.append(f"path `{path}`: disposition={r.get('disposition')!r}")
        if r.get("disposition") == "retired":
            if r.get("concept_id") is not None:
                p.append(f"path `{path}`: retired but names a concept")
            if not r.get("decision_ids"):
                p.append(f"path `{path}`: retired without a decision")
        elif r.get("concept_id") not in defined:
            p.append(f"path `{path}`: concept `{r.get('concept_id')}` is not defined")
    for kind in ("asking_keys", "profile_seed", "profile_json"):
        for r in b.get(kind, []):
            if r.get("concept_id") not in defined:
                p.append(f"{kind} `{r.get('key') or r.get('path')}`: concept "
                         f"`{r.get('concept_id')}` is not defined")
    return p


class Catalog:
    def __init__(self, raw: Dict[str, Any]):
        problems = validate(raw)
        if problems:
            raise CatalogInvalid(problems)
        self.raw = raw
        self.version = raw["catalog_version"]
        self._concepts = {c["concept_id"]: c for c in raw["concepts"]}
        self._paths = {r["path"]: r for r in raw["bindings"]["paths"]}
        self._asking = {r["key"]: r for r in raw["bindings"]["asking_keys"]}
        self._profile = {r["key"]: r for r in raw["bindings"].get("profile_json", [])}

    # ── concepts ─────────────────────────────────────────────────────────
    def concept(self, concept_id: str) -> Optional[Dict[str, Any]]:
        return self._concepts.get(concept_id)

    def concepts(self) -> List[Dict[str, Any]]:
        return list(self._concepts.values())

    # ── bindings ─────────────────────────────────────────────────────────
    def binding(self, path: str) -> Optional[Dict[str, Any]]:
        """The binding for a legacy dotted path; `[n]` indices are ignored."""
        return self._paths.get(_base(path))

    def concept_for_path(self, path: str) -> Optional[str]:
        """None for an unknown or a RETIRED path — callers must distinguish
        with `binding()` if they need to know which."""
        r = self.binding(path)
        return r["concept_id"] if r else None

    def alias_target(self, path: str) -> Optional[str]:
        """The questionnaire field a DECIDED alias (D1a/D1b) stands for, e.g.
        `family.children.dateOfBirth` → `children.birthDate`; None otherwise.
        Only pairs recorded path by path in the decision appendix — never a
        guess from a shared concept."""
        r = self.binding(path)
        return r.get("alias_of") if r else None

    def is_retired(self, path: str) -> bool:
        r = self.binding(path)
        return bool(r and r["disposition"] == "retired")

    def asking_binding(self, key: str) -> Optional[Dict[str, Any]]:
        return self._asking.get(key)

    def profile_binding(self, key: str) -> Optional[Dict[str, Any]]:
        """profile_json key such as `basics.dob` or `kinship.relation`."""
        return self._profile.get(key)

    # ── behaviour, each property read on its own (D1f) ──────────────────
    def extraction_paths_for_scope(self, section: str) -> List[str]:
        """Extraction paths to offer when the conversation is in `section`:
        members of the extraction vocabulary, not retired, whose concept is
        eligible AND scoped to this section. The basis of Batch A4."""
        out = []
        for r in self._paths.values():
            if not r["extraction_member"] or r["disposition"] == "retired":
                continue
            c = self._concepts.get(r["concept_id"])
            if c and c["extraction"]["eligible"] and section in c["extraction"]["scope"] \
                    and r["section"] == section:
                out.append(r["path"])
        return sorted(out)

    def askable(self, concept_id: str, subject: Optional[str] = None) -> str:
        c = self._concepts[concept_id]
        by = c["lori"].get("askable_by_subject") or {}
        if subject is not None and subject in by:
            return by[subject]
        return c["lori"]["askable"]

    def prompt_role(self, concept_id: str, subject_is_narrator: bool) -> str:
        return self._concepts[concept_id]["lori"]["prompt_role"][
            "narrator" if subject_is_narrator else "other"]


@lru_cache(maxsize=1)
def load(path: str = CATALOG_PATH) -> Catalog:
    with open(path, encoding="utf-8") as fh:
        return Catalog(json.load(fh))
