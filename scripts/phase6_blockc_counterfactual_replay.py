#!/usr/bin/env python3
"""Phase 6 Block C — read-only counterfactual replay over stored cohort evidence.

WO-LORI-ARCHIVE-TO-MEMOIR-02, Phase 6, Block C.

WHAT THIS DOES. Reads a stored response-trace JSONL, takes each turn's
`narrator_input` as it was actually spoken, and runs the anchor
extraction TWICE — once with the 4b205a8 patterns restored, once with
the Block C repair in place — then reports every difference and what it
would have done to Guard Lab ids 40 and 48.

WHAT THIS DOES NOT DO. No model call. No database access. No writes to
the trace. No serving stack. No narrator data is read beyond the
narrator utterances already stored in the trace being replayed. The only
optional write is the report itself, via --out.

HOW "OLD" IS PRODUCED. Not from memory, and not by reimplementing the
extractors. The pre-repair regexes are carried below as frozen literals
with their commit named, and are monkeypatched onto the live service
modules for the duration of one call. Every anchor list in both columns
is therefore produced by SHIPPED code — `detect_factual_chain` and
`compose_chronological_chain_receipt` — with only the two repaired
internals swapped. The unchanged helpers (`_filter_anchor`,
`_BAD_ANCHOR_TOKENS`, `_CASCADE_FILTER_TOKENS`, `_dedupe_preserving_order`)
are imported live, because the repair did not touch them; that is
asserted at startup rather than assumed.

USAGE
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python \\
        scripts/phase6_blockc_counterfactual_replay.py

    # explicit trace, and a written report
    PYTHONPATH=server/code .venv/bin/python \\
        scripts/phase6_blockc_counterfactual_replay.py \\
        --trace .runtime/eval/phase6-cohort-C-all-on-20260908/response-trace/2026-09-08.jsonl \\
        --out docs/reports/PHASE6-BLOCKC-COUNTERFACTUAL-cohortC.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from api.services import factual_chain_capture as fcc          # noqa: E402
from api.services import (                                     # noqa: E402
    lori_structured_narrative_fallback as lsnf,
)
from api.services.lori_witness_mode import (                   # noqa: E402
    compose_chronological_chain_receipt,
)

DEFAULT_TRACE = (
    REPO_ROOT / ".runtime" / "eval"
    / "phase6-cohort-C-all-on-20260908" / "response-trace" / "2026-09-08.jsonl"
)

# Guard Lab authority ids under examination.
ID_CHAIN_ANCHOR_OPENER = 40
ID_WITNESS_RECEIPT_FALLBACK = 48

# id 40 fires only with at least this many anchors
# (lori_communication_control.py:1273).
ID40_MIN_ANCHORS = 3
# id 48 renders at most this many into the receipt
# (lori_witness_mode.py:2172).
ID48_RECEIPT_ANCHORS = 2


# ══════════════════════════════════════════════════════════════════════
# The pre-repair patterns, frozen at 4b205a8
# ══════════════════════════════════════════════════════════════════════
#
# Copied verbatim from 4b205a8575fe4520d8d69374e9f0acf60b421a33:
#   factual_chain_capture.py:74-82
#   lori_structured_narrative_fallback.py:44-46
# Do not "tidy" these. They are a historical record, and their whole
# value is being byte-faithful to what actually ran during the cohort.

OLD_FCC_PROPER_NOUN_RX = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\b"
)
OLD_FCC_FROM_TO_RX = re.compile(
    r"\bfrom\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\s+to\s+"
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})\b"
)
OLD_LSNF_PROPER_NOUN_RX = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\b"
)


def _old_extract_proper_noun_anchors(text: str, max_n: int = 12) -> List[str]:
    """The 4b205a8 body of factual_chain_capture._extract_proper_noun_anchors.

    A bare `finditer` with no re-scan after a stripped leading filter
    token — which is the truncation half of the defect. Reads
    `fcc._PROPER_NOUN_RX` dynamically so the patch below applies.
    """
    if not text:
        return []
    anchors: List[str] = []
    for m in fcc._PROPER_NOUN_RX.finditer(text):
        candidate = fcc._filter_anchor(m.group(1))
        if candidate:
            anchors.append(candidate)
        if len(anchors) >= max_n:
            break
    return fcc._dedupe_preserving_order(anchors)


@contextmanager
def pre_repair_extractors():
    """Restore the 4b205a8 extraction internals for the duration."""
    saved = (
        fcc._PROPER_NOUN_RX,
        fcc._FROM_TO_RX,
        fcc._extract_proper_noun_anchors,
        lsnf._PROPER_NOUN_RX,
    )
    fcc._PROPER_NOUN_RX = OLD_FCC_PROPER_NOUN_RX
    fcc._FROM_TO_RX = OLD_FCC_FROM_TO_RX
    fcc._extract_proper_noun_anchors = _old_extract_proper_noun_anchors
    lsnf._PROPER_NOUN_RX = OLD_LSNF_PROPER_NOUN_RX
    try:
        yield
    finally:
        (
            fcc._PROPER_NOUN_RX,
            fcc._FROM_TO_RX,
            fcc._extract_proper_noun_anchors,
            lsnf._PROPER_NOUN_RX,
        ) = saved


def assert_repair_is_present() -> None:
    """Refuse to run against an unrepaired tree.

    Without this the replay would report "0 turns changed" on a tree
    where the repair was never applied, and that reads identically to
    "the repair changed nothing" — the exact confusion B1 was built to
    end.
    """
    probe = "The Saint Patrick's Day parade in Lowell."
    anchors = fcc.detect_factual_chain(probe)["anchors"]
    if "Saint Patrick's Day" not in anchors:
        raise SystemExit(
            "REFUSING: the Block C repair is not present in this tree.\n"
            f"  probe   : {probe!r}\n"
            f"  anchors : {anchors!r}\n"
            "  expected: \"Saint Patrick's Day\" to survive intact.\n"
            "Run this against a tree carrying the C1 repair."
        )
    # The helpers this script imports live must be the ones the repair
    # left alone; if a future change moves filtering into the patched
    # surface, the 'old' column silently stops being old.
    for mod, name in (
        (fcc, "_filter_anchor"),
        (fcc, "_BAD_ANCHOR_TOKENS"),
        (fcc, "_dedupe_preserving_order"),
        (lsnf, "_CASCADE_FILTER_TOKENS"),
    ):
        if not hasattr(mod, name):
            raise SystemExit(
                f"REFUSING: {mod.__name__}.{name} is gone. This script "
                "reuses it live on the assumption the repair did not "
                "touch it. Re-derive the 'old' column before trusting "
                "any output."
            )


# ══════════════════════════════════════════════════════════════════════
# Per-turn measurement
# ══════════════════════════════════════════════════════════════════════

_PUNCT_IN_NAME_RX = re.compile(r"[.'’]")


def _measure(text: str) -> Dict[str, Any]:
    """Everything the two authorities would derive from one utterance."""
    detection = fcc.detect_factual_chain(text)
    chain_anchors = list(detection["anchors"])
    fallback_anchors = lsnf.extract_safe_anchors(text, max_n=6)
    receipt = compose_chronological_chain_receipt(text)
    return {
        "is_factual_chain": bool(detection["is_factual_chain"]),
        "confidence": detection["confidence"],
        "chain_anchors": chain_anchors,
        "fallback_anchors": fallback_anchors,
        "receipt_anchors": fallback_anchors[:ID48_RECEIPT_ANCHORS],
        "receipt": receipt,
        # id 40 eligibility and the exact anchors it would splice.
        "id40_eligible": (
            bool(detection["is_factual_chain"])
            and len(chain_anchors) >= ID40_MIN_ANCHORS
        ),
        "id40_opener_anchors": (
            [chain_anchors[0], chain_anchors[1], chain_anchors[-1]]
            if len(chain_anchors) >= ID40_MIN_ANCHORS else []
        ),
    }


def _relate(old: Sequence[str], new: Sequence[str]) -> Dict[str, List]:
    """Classify how the anchor set moved.

    merge  — two or more old anchors are contained in one new anchor
             (the intended Block C outcome: 'West St' + 'Paul' ->
             'West St. Paul')
    split  — one old anchor became two or more new anchors. This should
             be EMPTY. Any entry is a regression.
    novel  — a new anchor sharing no text with any old anchor. Usually a
             consequence of a merge freeing a phrase slot; still worth
             eyeballing.
    lost   — an old anchor with no new anchor containing it.
    """
    old_set, new_set = list(old), list(new)
    merges, splits, novel, lost = [], [], [], []

    for n in new_set:
        if n in old_set:
            continue
        absorbed = [o for o in old_set if o not in new_set and o in n]
        if len(absorbed) >= 2:
            merges.append({"new": n, "from": absorbed})
        elif not any((o in n) or (n in o) for o in old_set):
            novel.append(n)

    for o in old_set:
        if o in new_set:
            continue
        produced = [n for n in new_set if n not in old_set and n in o]
        if len(produced) >= 2:
            splits.append({"old": o, "into": produced})
        elif not any((o in n) or (n in o) for n in new_set):
            lost.append(o)

    return {"merges": merges, "splits": splits, "novel": novel, "lost": lost}


# REMOVED 2026-09-09 — the punctuation / rescan / both sub-classifier.
#
# It was meant to isolate how many turns changed because of the
# leading-filter-token re-scan rather than the punctuation repair. It
# could not do that, and the way it failed is worth keeping.
#
# It scored a turn by looking at which anchors appeared or vanished and
# asking whether they carried '.' or an apostrophe. But a punctuation
# merge REMOVES the fabricated fragment — 'Paul' — and that fragment has
# no punctuation in it. So every merge scored as "both", and the metric
# returned punctuation=0 rescan=0 both=11 on a cohort where all eleven
# changes were punctuation-driven.
#
# It is deleted rather than repaired because it is a diagnostic of a
# diagnostic: the old→new anchor tables below are the actual evidence,
# and they answer the question directly by inspection. Nothing in the
# Block C acceptance claim rests on this classification, and no closeout
# should quote it.


def _historical_malformed(old: Sequence[str], new: Sequence[str]) -> List[str]:
    """Name the specific fabrications this Block was authorized to kill."""
    hits = []
    old_set = set(old)
    known = (
        ({"West St", "Paul"}, "West St / Paul"),
        ({"Saint Patrick", "Day"}, "Saint Patrick / Day"),
    )
    for tokens, label in known:
        if tokens <= old_set and not tokens <= set(new):
            hits.append(label)
    # Generic form: any old pair that the repair fused into one anchor.
    for n in new:
        if n in old_set:
            continue
        parts = [o for o in old_set if o not in new and o in n]
        if len(parts) >= 2 and _PUNCT_IN_NAME_RX.search(n):
            label = " / ".join(parts) + f"  ->  {n}"
            if label not in hits:
                hits.append(label)
    return hits


# ══════════════════════════════════════════════════════════════════════
# Trace reading
# ══════════════════════════════════════════════════════════════════════

def _resolve(rec: Dict[str, Any], key: str) -> Any:
    """Fetch `key` from the record, top level or nested under `context`.

    CORRECTED 2026-09-09 — the first version of this script read
    `rec["narrator_input"]` only. In this trace's schema the per-turn
    payload lives under a nested `context` object, so every lookup
    returned None, all 38 turns were skipped as "no narrator_input",
    and the report printed a clean zero across every column with
    exit=0. "Nothing changed" and "nothing was read" were byte-identical
    output — the same confusion B1 was built to end, reproduced in the
    instrument built to measure it.
    """
    if key in rec:
        return rec[key]
    ctx = rec.get("context")
    if isinstance(ctx, dict) and key in ctx:
        return ctx[key]
    return None


def _authority_stage(rec: Dict[str, Any], authority_id: int) -> Optional[Dict]:
    stages = _resolve(rec, "stages") or []
    if not isinstance(stages, list):
        return None
    for stage in stages:
        if isinstance(stage, dict) and stage.get("authority_id") == authority_id:
            return stage
    return None


def _classify(rec: Dict[str, Any]) -> Tuple[str, str]:
    """Decide what this record is. Every record gets a verdict.

    Returns (verdict, detail) where verdict is one of:

      applicable      — a generated turn carrying a narrator utterance.
                        `detail` is that utterance.
      not_applicable  — a deterministic route that never entered
                        generation, on which NEITHER id 40 nor id 48
                        left a stage. `detail` says why.
      unexplained     — anything else. The caller must refuse.

    MEASURED, not assumed (cohort-C, 2026-09-08): lines 11 and 26 carry
    `generation_attempted=False` with `effective_turn_mode` of `witness`
    and `meta_question` respectively, no `narrator_input`, and no id-40
    or id-48 stage. They are deterministic replies, so there is no
    narrator utterance for these extractors to have run on, and no
    authority decision for the counterfactual to change. Excluding them
    is a statement about the production route, not a convenience.

    The authority check is the load-bearing half. "It didn't generate"
    alone would not be enough — if id 40 or id 48 HAD left a stage on a
    deterministic turn, that turn participated and could not be dropped
    from a counterfactual about those authorities.
    """
    text = _resolve(rec, "narrator_input")
    if isinstance(text, str) and text.strip():
        return "applicable", text

    generation_attempted = _resolve(rec, "generation_attempted")
    mode = _resolve(rec, "effective_turn_mode") or "unknown"

    if generation_attempted is False:
        for authority_id in (
            ID_CHAIN_ANCHOR_OPENER, ID_WITNESS_RECEIPT_FALLBACK,
        ):
            if _authority_stage(rec, authority_id) is not None:
                return "unexplained", (
                    f"non-generated turn (effective_turn_mode={mode}) "
                    f"but authority id {authority_id} left a stage — it "
                    "participated, so it cannot be excluded from a "
                    "counterfactual about that authority"
                )
        return "not_applicable", (
            f"deterministic route, effective_turn_mode={mode}, "
            "generation_attempted=False, no id-40/id-48 stage"
        )

    return "unexplained", (
        f"no narrator_input and generation_attempted="
        f"{generation_attempted!r} (effective_turn_mode={mode})"
    )


def load_turns(
    trace_path: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
           List[Dict[str, Any]], int, int]:
    """Return (applicable, excluded, unexplained, malformed, total_records).

    `total_records` is counted directly rather than derived from the
    other three. Deriving it would make the record-count invariant
    unfalsifiable — it would agree with itself by construction.

    Each returned turn carries a normalised `_replay_text` and
    `_replay_turn_key` so the rest of the script never has to know where
    in the schema they were found.
    """
    turns: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    unexplained: List[Dict[str, Any]] = []
    malformed = 0
    total = 0
    with trace_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(rec, dict):
                malformed += 1
                continue

            verdict, detail = _classify(rec)
            entry = {
                "line": line_no,
                "turn_key": _resolve(rec, "turn_key") or "",
                "trace_id": rec.get("trace_id"),
                "mode": _resolve(rec, "effective_turn_mode"),
                "reason": detail,
            }
            if verdict == "applicable":
                rec["_replay_text"] = detail
                rec["_replay_turn_key"] = _resolve(rec, "turn_key") or ""
                rec["_replay_line"] = line_no
                turns.append(rec)
            elif verdict == "not_applicable":
                excluded.append(entry)
            else:
                unexplained.append(entry)
    return turns, excluded, unexplained, malformed, total


# ══════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════

def _fmt(anchors: Sequence[str]) -> str:
    return "[" + ", ".join(repr(a) for a in anchors) + "]"


def check_cohort_integrity(
    turns: List[Dict[str, Any]],
    excluded: List[Dict[str, Any]],
    unexplained: List[Dict[str, Any]],
    malformed: int,
    total_records: int,
    expect_records: int,
    expect_applicable: int,
) -> Dict[str, Any]:
    """Prove the cohort was recovered COMPLETELY before reporting anything.

    The instrument must refuse rather than report a partial replay as a
    result. Utterance and turn identity are read from the SAME record,
    so a duplicate or missing join is structurally impossible — but
    turn-key uniqueness is still checked, because a repeated key would
    mean the trace itself is not what we think it is.

    Narrator text is NEVER derived from Lori's delivered response. That
    would replay the wrong side of the pipeline: these extractors run on
    the narrator utterance, and scoring them against generated text
    would measure the generator.
    """
    problems: List[str] = []
    keys = [t["_replay_turn_key"] for t in turns]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    blanks = sum(1 for k in keys if not k or k == "?")
    narrators = sorted({
        str(_resolve(t, "narrator_id") or "") for t in turns
    })

    if total_records != expect_records:
        problems.append(
            f"trace holds {total_records} record(s), expected "
            f"{expect_records}")
    if len(turns) != expect_applicable:
        problems.append(
            f"recovered {len(turns)} replayable narrator utterance(s), "
            f"expected {expect_applicable}")
    if len(set(keys)) != len(turns):
        problems.append(
            f"{len(set(keys))} unique turn_key(s) across {len(turns)} "
            "replayable turn(s)")
    # Every record must land in exactly one bucket. This is the check
    # that makes "accounted for" mean something.
    accounted = len(turns) + len(excluded) + len(unexplained) + malformed
    if accounted != total_records:
        problems.append(
            f"{accounted} record(s) classified but {total_records} read "
            "— a record fell through the classification")
    if unexplained:
        for u in unexplained:
            problems.append(
                f"UNEXPLAINED record at line {u['line']} "
                f"(turn_key={u['turn_key']!r}): {u['reason']}")
    if malformed:
        problems.append(f"{malformed} malformed line(s)")
    if dupes:
        problems.append(f"duplicate turn_key(s): {dupes}")
    if blanks:
        problems.append(
            f"{blanks} replayable turn(s) with no usable turn_key")

    return {
        "ok": not problems,
        "problems": problems,
        "recovered": len(turns),
        "expected_applicable": expect_applicable,
        "expected_records": expect_records,
        "total_records": total_records,
        "excluded": excluded,
        "unexplained": unexplained,
        "malformed": malformed,
        "distinct_turn_keys": len(set(keys)),
        "narrator_ids": narrators,
    }


def build_report(
    trace_path: Path,
    turns: List[Dict[str, Any]],
    integrity: Dict[str, Any],
) -> Tuple[str, Dict[str, int]]:
    lines: List[str] = []
    w = lines.append

    w("# Phase 6 Block C — counterfactual replay")
    w("")
    try:
        shown_path: Any = trace_path.relative_to(REPO_ROOT)
    except ValueError:
        # A trace outside the repo is legitimate — the instrument's own
        # tests drive it from a temp directory, and refusing to name the
        # file would make the report lie about what it read.
        shown_path = trace_path
    w(f"**Trace:** `{shown_path}`")
    w("")
    w("Read-only. No model call, no database, no stack, no writes to the "
      "trace. Both anchor columns are produced by shipped code; only the "
      "two repaired internals are swapped, from frozen 4b205a8 literals.")
    w("")
    w("## Cohort integrity")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| trace records accounted for | {integrity['total_records']} |")
    w(f"| — generated turns replayed | {integrity['recovered']} |")
    w(f"| — deterministic, not applicable | {len(integrity['excluded'])} |")
    w(f"| — unexplained omissions | {len(integrity['unexplained'])} |")
    w(f"| — malformed | {integrity['malformed']} |")
    w(f"| unique turn keys across replayed turns | "
      f"{integrity['distinct_turn_keys']} |")
    w(f"| narrator ids in trace | {len(integrity['narrator_ids'])} |")
    w("")
    if integrity["excluded"]:
        w("**Excluded as not applicable** — these are not missing "
          "narrator inputs. They are production routes that never "
          "entered generation, so no narrator utterance ever reached "
          "these extractors and neither id 40 nor id 48 left a stage "
          "for a counterfactual to change:")
        w("")
        for e in integrity["excluded"]:
            w(f"* line {e['line']} — `effective_turn_mode="
              f"{e['mode']}`, {e['reason']}")
        w("")
        blank_keys = [e for e in integrity["excluded"] if not e["turn_key"]]
        if blank_keys:
            w(f"_Recorded, not repaired: {len(blank_keys)} of these carry "
              "`turn_key: \"\"`. That is the deterministic-trace "
              "joinability weakness already logged in Phase 6 "
              "(handoff §6.2), not the malformed-anchor defect. Block C "
              "does not expand to cover it._")
            w("")
    w("Narrator text is read from each record's own `context.narrator_input`, "
      "alongside that record's `turn_key` — utterance and turn identity come "
      "from the same object, so no join is performed and none can go wrong. "
      "Lori's delivered text is never used as an extractor input; these "
      "extractors run on the narrator utterance, and feeding them generated "
      "text would measure the generator instead.")
    w("")

    counts = {
        "turns": len(turns),
        "not_applicable": len(integrity["excluded"]),
        "malformed_lines": integrity["malformed"],
        "changed": 0,
        "unchanged": 0,
        "id40_eligibility_flips": 0,
        "id40_opener_anchor_changes": 0,
        "id48_receipt_anchor_changes": 0,
        "splits_created": 0,
        "merges_created": 0,
        "novel_anchors": 0,
        "lost_anchors": 0,
    }

    changed_rows: List[str] = []
    flag_rows: List[str] = []
    malformed_hits: List[str] = []

    for rec in turns:
        text = rec["_replay_text"]
        turn_key = rec["_replay_turn_key"]

        with pre_repair_extractors():
            old = _measure(text)
        new = _measure(text)

        chain_rel = _relate(old["chain_anchors"], new["chain_anchors"])
        fb_rel = _relate(old["fallback_anchors"], new["fallback_anchors"])

        chain_changed = old["chain_anchors"] != new["chain_anchors"]
        fb_changed = old["fallback_anchors"] != new["fallback_anchors"]
        id40_flip = old["id40_eligible"] != new["id40_eligible"]
        id40_anchor_change = (
            old["id40_opener_anchors"] != new["id40_opener_anchors"])
        id48_change = old["receipt_anchors"] != new["receipt_anchors"]

        any_change = (
            chain_changed or fb_changed or id40_flip
            or id40_anchor_change or id48_change)

        if not any_change:
            counts["unchanged"] += 1
            continue

        counts["changed"] += 1
        if id40_flip:
            counts["id40_eligibility_flips"] += 1
        if id40_anchor_change:
            counts["id40_opener_anchor_changes"] += 1
        if id48_change:
            counts["id48_receipt_anchor_changes"] += 1

        for rel in (chain_rel, fb_rel):
            counts["splits_created"] += len(rel["splits"])
            counts["merges_created"] += len(rel["merges"])
            counts["novel_anchors"] += len(rel["novel"])
            counts["lost_anchors"] += len(rel["lost"])

        hits = (
            _historical_malformed(old["chain_anchors"], new["chain_anchors"])
            + _historical_malformed(
                old["fallback_anchors"], new["fallback_anchors"])
        )
        for h in hits:
            if h not in malformed_hits:
                malformed_hits.append(h)

        changed_rows.append("")
        changed_rows.append(f"### turn `{turn_key}`")
        changed_rows.append("")
        changed_rows.append(f"> {text.strip()[:400]}")
        changed_rows.append("")
        changed_rows.append("| | old (4b205a8) | new (Block C) |")
        changed_rows.append("|---|---|---|")
        changed_rows.append(
            f"| factual-chain anchors | `{_fmt(old['chain_anchors'])}` "
            f"| `{_fmt(new['chain_anchors'])}` |")
        changed_rows.append(
            f"| fallback anchors | `{_fmt(old['fallback_anchors'])}` "
            f"| `{_fmt(new['fallback_anchors'])}` |")
        changed_rows.append(
            f"| id 40 eligible | {old['id40_eligible']} "
            f"| {new['id40_eligible']} |")
        changed_rows.append(
            f"| id 40 opener anchors | `{_fmt(old['id40_opener_anchors'])}` "
            f"| `{_fmt(new['id40_opener_anchors'])}` |")
        changed_rows.append(
            f"| id 48 receipt anchors | `{_fmt(old['receipt_anchors'])}` "
            f"| `{_fmt(new['receipt_anchors'])}` |")

        # What the authorities actually did on this turn, historically.
        st40 = _authority_stage(rec, ID_CHAIN_ANCHOR_OPENER)
        st48 = _authority_stage(rec, ID_WITNESS_RECEIPT_FALLBACK)
        if st40 or st48:
            changed_rows.append("")
            for label, st in (("id 40", st40), ("id 48", st48)):
                if st:
                    changed_rows.append(
                        f"* traced {label}: selected={st.get('selected')} "
                        f"eligible={st.get('eligible')} "
                        f"fired={st.get('fired')}")

        for name, rel in (("factual-chain", chain_rel), ("fallback", fb_rel)):
            if rel["splits"]:
                flag_rows.append(
                    f"* **SPLIT CREATED** — turn `{turn_key}` ({name}): "
                    f"{rel['splits']}")
            if rel["novel"]:
                flag_rows.append(
                    f"* novel anchor — turn `{turn_key}` ({name}): "
                    f"{rel['novel']}")
            if rel["lost"]:
                flag_rows.append(
                    f"* lost anchor — turn `{turn_key}` ({name}): "
                    f"{rel['lost']}")
        if id40_flip:
            flag_rows.append(
                f"* id 40 eligibility flip — turn `{turn_key}`: "
                f"{old['id40_eligible']} -> {new['id40_eligible']}")

    # ── summary ──────────────────────────────────────────────────────
    w("## Summary")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| turns replayed (applicable) | {counts['turns']} |")
    w(f"| turns with NO extraction change | {counts['unchanged']} |")
    w(f"| turns changed by the repair | {counts['changed']} |")
    w(f"| id 40 eligibility flips | {counts['id40_eligibility_flips']} |")
    w(f"| id 40 opener-anchor changes | {counts['id40_opener_anchor_changes']} |")
    w(f"| id 48 receipt-anchor changes | {counts['id48_receipt_anchor_changes']} |")
    w(f"| merges created (expected) | {counts['merges_created']} |")
    w(f"| **splits created (must be 0)** | **{counts['splits_created']}** |")
    w(f"| novel anchors | {counts['novel_anchors']} |")
    w(f"| lost anchors | {counts['lost_anchors']} |")
    w(f"| deterministic turns, not applicable | {counts['not_applicable']} |")
    w(f"| malformed lines | {counts['malformed_lines']} |")
    w("")

    w("## Historical malformed cases")
    w("")
    if malformed_hits:
        for h in malformed_hits:
            w(f"* repaired: `{h}`")
    else:
        w("_None of the named fabrications appear in this trace's "
          "narrator utterances. That is a fact about this trace, not "
          "evidence that the defect never occurred — the malformed "
          "strings were observed in DELIVERED text, and a turn whose "
          "utterance no longer produces them may simply not be in "
          "this file._")
    w("")

    w("## Flags")
    w("")
    if flag_rows:
        lines.extend(flag_rows)
    else:
        w("_None._")
    w("")

    w("## Changed turns")
    if changed_rows:
        lines.extend(changed_rows)
    else:
        w("")
        w("_No turn changed._")

    return "\n".join(lines) + "\n", counts


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    ap.add_argument("--out", type=Path, default=None,
                    help="optional path to write the markdown report")
    ap.add_argument(
        "--expect-records", type=int, required=True,
        help="how many records this trace MUST hold (cohort-C = 38).")
    ap.add_argument(
        "--expect-applicable", type=int, required=True,
        help="how many of those are generated turns carrying a narrator "
             "utterance and so replayable (cohort-C = 36; the other 2 "
             "are deterministic routes). Both are required on purpose: "
             "an expectation the operator states cannot be silently "
             "satisfied by a partial replay, and cannot be reused "
             "unexamined on a different cohort.")
    args = ap.parse_args(argv)

    if not args.trace.exists():
        raise SystemExit(f"trace not found: {args.trace}")

    assert_repair_is_present()

    turns, excluded, unexplained, malformed, total = load_turns(args.trace)
    integrity = check_cohort_integrity(
        turns, excluded, unexplained, malformed, total,
        args.expect_records, args.expect_applicable)

    # REFUSE ON AN INCOMPLETE COHORT. A run that read no turns — or only
    # some — produces zeroes indistinguishable from "the repair changed
    # nothing". That is how the first version of this script reported
    # exit=0 while skipping all 38 turns on a schema mismatch. A
    # measurement of nothing is not a measurement, and a partial one is
    # not a counterfactual.
    if not integrity["ok"]:
        print(
            "REFUSING: the cohort was not accounted for completely.\n"
            f"  trace      : {args.trace}\n"
            f"  records    : {integrity['total_records']} of "
            f"{integrity['expected_records']}\n"
            f"  replayable : {integrity['recovered']} of "
            f"{integrity['expected_applicable']}\n"
            f"  excluded   : {len(integrity['excluded'])} "
            f"(deterministic, not applicable)\n"
            + "".join(f"  problem   : {p}\n" for p in integrity["problems"])
            + "No report written. Any zeroes it produced would mean "
              "'nothing was read', not 'nothing changed'.",
            file=sys.stderr,
        )
        return 2

    report, counts = build_report(args.trace, turns, integrity)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(report)

    print(
        f"replayed={counts['turns']} changed={counts['changed']} "
        f"unchanged={counts['unchanged']} "
        f"merges={counts['merges_created']} "
        f"splits={counts['splits_created']} "
        f"lost={counts['lost_anchors']} "
        f"id40_flips={counts['id40_eligibility_flips']} "
        f"not_applicable={counts['not_applicable']} "
        f"records_accounted={integrity['total_records']}"
    )

    # A created split is the one outcome that invalidates the repair.
    return 1 if counts["splits_created"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
