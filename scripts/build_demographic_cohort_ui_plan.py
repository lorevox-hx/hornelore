#!/usr/bin/env python3
"""Build a read-only UI conversation plan from the existing cohort fixtures.

The fixture modules remain the biography authority.  This helper reads their
``ChapterConfig.text`` values and selects short, verbatim excerpts for a real
browser conversation.  It also resolves each narrator by the artifact journal
that created them.  It performs no network, database, or product writes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_narrator_cohort_acceptance as cohort  # noqa: E402

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
SAFE_RUN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class PlanRefusal(RuntimeError):
    """The requested run cannot safely identify the configured cohort."""


def _sentences(text: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]


def _chunks(text: str, *, minimum: int = 28, maximum: int = 72) -> List[str]:
    """Return ordered, sentence-boundary chunks from one fixture chapter."""
    out: List[str] = []
    current: List[str] = []
    words = 0
    for sentence in _sentences(text):
        sentence_words = len(sentence.split())
        if current and words + sentence_words > maximum:
            out.append(" ".join(current))
            current, words = [], 0
        if sentence_words > maximum:
            # Long fixture sentences are split only at natural clause marks.
            clauses = [c.strip() for c in re.split(r"(?<=[,;:—])\s+", sentence)
                       if c.strip()]
            if len(clauses) == 1:
                clauses = [" ".join(sentence.split()[i:i + maximum])
                           for i in range(0, sentence_words, maximum)]
            for clause in clauses:
                clause_words = len(clause.split())
                if current and words + clause_words > maximum:
                    out.append(" ".join(current))
                    current, words = [], 0
                current.append(clause)
                words += clause_words
                if words >= minimum:
                    out.append(" ".join(current))
                    current, words = [], 0
            continue
        current.append(sentence)
        words += sentence_words
        if words >= minimum:
            out.append(" ".join(current))
            current, words = [], 0
    if current:
        tail = " ".join(current)
        if out and len(tail.split()) < minimum:
            merged = f"{out[-1]} {tail}"
            if len(merged.split()) <= maximum + 12:
                out[-1] = merged
            else:
                out.append(tail)
        else:
            out.append(tail)
    return [x for x in out if x.strip()]


def select_excerpts(text: str, count: int = 1) -> List[str]:
    """Choose ``count`` ordered excerpts distributed across a chapter."""
    chunks = _chunks(text)
    if not chunks:
        raise PlanRefusal("chapter has no usable narrator text")
    count = max(1, int(count))
    if len(chunks) <= count:
        return chunks
    if count == 1:
        return [chunks[0]]
    indices = sorted({round(i * (len(chunks) - 1) / (count - 1))
                      for i in range(count)})
    return [chunks[i] for i in indices]


def _journal_path(run_id: str) -> Path:
    if not SAFE_RUN_RE.fullmatch(run_id or ""):
        raise PlanRefusal("unsafe --run-id")
    return (REPO_ROOT / ".runtime" / "eval" / "narrator-cohort" /
            run_id / "artifacts.json")


def build_plan(run_id: str, *, turns_per_era: int = 1) -> Dict[str, Any]:
    path = _journal_path(run_id)
    if not path.is_file():
        raise PlanRefusal(f"source journal not found: {path}")
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanRefusal(f"source journal is unreadable: {type(exc).__name__}") from exc

    people = list(journal.get("people") or [])
    personas = [p for p in cohort.load_personas(quick=False)
                if p.get("source") == "harness"]
    expected = set(cohort.COHORT_HARNESSES)
    got = {p["harness"] for p in personas}
    if got != expected:
        raise PlanRefusal(
            f"configured scripted cohort mismatch: missing={sorted(expected - got)} "
            f"extra={sorted(got - expected)}")

    planned: List[Dict[str, Any]] = []
    for persona in personas:
        source = persona["harness"]
        rows = [row for row in people if row.get("source") == source]
        if len(rows) != 1:
            raise PlanRefusal(
                f"expected exactly one journaled {source} narrator in {run_id}; "
                f"found {len(rows)}")
        row = rows[0]
        person_id = str(row.get("person_id") or "")
        if not UUID_RE.fullmatch(person_id):
            raise PlanRefusal(f"{source} has an invalid journaled person_id")
        # ── The journal stores the FIXTURE LABEL, not the product name ──
        #
        # This previously required the journaled display_name to start
        # with "ZZ COHORT <run_id> · ", which is the PRODUCT display
        # name. The journal records the fixture label instead —
        # 'Alex Eunseo Park (they/them)' — so the check refused for all
        # ten narrators, every time, and no plan could ever be built.
        #
        # This module takes no --api argument and performs no network by
        # design, so it CANNOT verify a product name. What it can verify
        # is that the journal row matches the fixture the plan is built
        # from. The product-marker check belongs to the runner, which
        # has the API; the expected prefix is emitted below so the
        # runner can make it exactly rather than by substring guessing.
        display_name = str(row.get("display_name") or "").strip()
        # `label` is the fixture's own narrator_label — what the cohort
        # runner journaled. `expected_label` is the shorter configured
        # name in COHORT_HARNESSES ('Alex Eunseo Park' against the
        # fixture's 'Alex Eunseo Park (they/them)'). Either is a valid
        # identification of the same person; requiring the configured
        # one refused a correctly journaled narrator.
        accepted = {str(persona.get("label") or "").strip(),
                    str(persona.get("expected_label") or "").strip()}
        accepted.discard("")
        if accepted and display_name not in accepted:
            raise PlanRefusal(
                f"{source} journaled label {display_name!r} matches neither "
                f"the fixture label nor the configured one {sorted(accepted)!r}")
        # ── The EXACT product display name, not the shared prefix ────
        #
        # All ten narrators share "ZZ COHORT <run_id> · ", so a check
        # that only tests the prefix passes on a stale card still
        # showing a DIFFERENT cohort narrator — precisely the failure
        # the person-id check exists to prevent, reintroduced through
        # the visible name.
        #
        # The product name is derivable without the network: the cohort
        # runner stamps `preferred_name` through `mark_intake_payload`
        # and that becomes the people row's display_name. Same function,
        # same run id, same fixture payload — so the same string.
        product_marker = f"ZZ COHORT {run_id} · "
        marked = cohort.mark_intake_payload(
            dict(persona.get("intake_payload") or {}), run_id)
        product_display_name = str(marked.get("preferred_name") or "").strip()
        if not product_display_name.startswith(product_marker):
            raise PlanRefusal(
                f"{source} could not derive a marked product display name "
                f"(got {product_display_name!r})")

        eras: List[Dict[str, Any]] = []
        for chapter in persona.get("chapters") or []:
            text = chapter.text  # direct access: a fixture rename must fail loudly
            excerpts = select_excerpts(text, turns_per_era)
            eras.append({
                "era_id": chapter.runtime71_era,
                "label": chapter.label,
                "source_words": len(text.split()),
                "turns": excerpts,
                "anchors": list(chapter.anchors or []),
            })
        if not eras:
            raise PlanRefusal(f"scripted persona {source} has no chapters")
        planned.append({
            "product_marker": product_marker,
            "product_display_name": product_display_name,
            "source": source,
            "fixture_label": persona["label"],
            "expected_label": persona["expected_label"],
            "person_id": person_id,
            "display_name": display_name,
            "eras": eras,
        })

    return {
        "schema_version": 1,
        "source_run_id": run_id,
        "journal_path": str(path),
        "narrators": planned,
        "narrator_count": len(planned),
        "era_count": sum(len(p["eras"]) for p in planned),
        "narrator_turn_count": sum(
            len(e["turns"]) for p in planned for e in p["eras"]),
        "turns_per_era_requested": int(turns_per_era),
        "writes": "NONE — plan construction reads fixtures and the source journal only",
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--turns-per-era", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--out")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        plan = build_plan(args.run_id, turns_per_era=args.turns_per_era)
    except PlanRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
