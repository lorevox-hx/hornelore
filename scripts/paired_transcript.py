#!/usr/bin/env python3
"""Paired diagnostic transcript — what Lori generated, what she said.

READ ONLY. Operator tool. Renders one conversation from the shipped
response trace as a side-by-side of the model's original output and the
text the narrator actually received, with the guard stages that connect
them.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv-gpu/bin/python \
        scripts/paired_transcript.py --list
    PYTHONPATH=server/code .venv-gpu/bin/python \
        scripts/paired_transcript.py --conversation switch_xxxx_yyyy \
        --export .runtime/eval/paired/zz-baseline.md

WHY THIS EXISTS
===============
On 2026-09-21 Lori answered "Did I tell you that, or is it information
in my biography?" with seven words. The log said `before_words=38
after_words=7`. It did not say what the 38 words were, and tracing was
off, so they are gone. Finding the cause took an in-process
reproduction against a reply I wrote myself — which is evidence about
the mechanism and no evidence at all about that turn.

This renderer exists so the next such question is answered by opening a
transcript instead of reconstructing one.

NOTHING HERE IS NEW INSTRUMENTATION
===================================
Every field below is already written by the shipped trace. The gap was
never capture; it was that the capture was off and its output was JSONL
scoped to a fixed ten-turn Phase 6 baseline.

    narrator_input        chat_ws.py:97          context.narrator_input
    raw_text              chat_ws.py:6061        _rt.raw(final_text)
    delivered_text        chat_ws.py:7780        _rt.seal(delivered=...)
    per-authority stages  chat_ws.py:6618-6634   one `cc_<id>_<name>`
                          per entry in CommunicationControlResult
                          .authority_records, carrying selected,
                          eligible, fired and exact before/after
    turn_key              bind_turn_key()        the join to the
                                                 durable transcript

ONE READER, ONE DEFINITION
==========================
`_trace_records`, `_db_path`, `_read_only`, `_armed_dir` are IMPORTED
from `guard_lab_live_acceptance`, and `is_system_directive` /
`_narrator_input` from `phase6_conversation_capture`, rather than
reimplemented. The repository's own recorded lesson:

    two readers of one trace format stay equal exactly until the first
    change

This file is a second RENDERER, which is a smaller hazard than a second
reader but not zero. The split is deliberate: `phase6_conversation_capture`
carries the baseline's ten-turn refusal contract, pinned by
`tests/test_phase6_baseline_turnset.py`, and generalising that file in
place would have meant loosening the refusal it exists to perform. So
the validation stays there and the plain side-by-side lives here, over
the same readers and the same field names.

It also does not re-derive guard events. `chat_ws` already serialises
`authority_records` into stages; this reads those stages. A second
description of what authority 33 did is the failure one level up from
a second reader.

FOUR OUTCOMES, AND ABSENCE IS NOT ONE OF THEM
=============================================
The distinction this renderer most has to get right:

    UNCHANGED        raw and delivered were BOTH captured and are equal
    CHANGED          both captured, and they differ
    NOT CAPTURED     one or both are missing — says nothing either way
    NEVER GENERATED  a terminal turn; the model was not called at all

A missing guard log is not proof that nothing changed. Chris's turn 4
emitted no `comm_control` line whatsoever, which today is
indistinguishable from a logger failure; under the trace it is a
recorded `fired=False`, which is evidence. This renderer will not
collapse the third row into the first, and it prints NOT CAPTURED in
full rather than leaving a blank that reads like a pass.

`fired` and `changed` are also kept apart. An authority can run, reach
a finding, and mutate nothing — #37 does exactly that. Reporting it as
"fired" alone would put a validator in the same column as the rule that
deleted an answer.

WHAT IT WILL NOT DO
===================
It renders no judgement. Whether an answer was adequate, whether the
follow-up question was the right one, whether a detail was dropped that
mattered — none of that is measured here and none of it is guessed. A
generated guess in a judgement column is indistinguishable from a
finding, which is how a guess gets quoted back as one.

It is not narrator-facing. Raw text may contain invented names, or
material a safety guard removed on purpose. Nothing in this file writes
to the narrator's archive, and its output belongs under `.runtime/`,
which is gitignored.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# ONE reader. See the module docstring.
from guard_lab_live_acceptance import (  # noqa: E402
    _armed_dir, _trace_records,
)
from phase6_conversation_capture import (  # noqa: E402
    _narrator_input, is_system_directive,
)

LAST_MARKER = REPO_ROOT / ".runtime" / "eval" / "last_eval_dir"
DEFAULT_TRACE = REPO_ROOT / ".runtime" / "eval"

# ── outcomes ────────────────────────────────────────────────────────
UNCHANGED = "UNCHANGED"
CHANGED = "CHANGED"
NOT_CAPTURED = "NOT CAPTURED"
NEVER_GENERATED = "NEVER GENERATED"


def _stage_to_authority() -> Dict[str, Any]:
    """`trace_stage` -> Intervention, for stages outside comm_control.

    The renderer named `cc_<id>_<name>` rows by authority and printed
    everything else as a bare stage label. So `profile_seed_delivery`
    — which discarded Lori's answer on five of twelve turns in the
    2026-09-21 rich capture — appeared as a stage name, and a reader
    had to already know it was authority 54 to look up its policy,
    its known harm or its switch.

    The registry carries `trace_stage` on each intervention precisely
    so this mapping does not have to be maintained twice.
    """
    try:
        from api.services import lori_guard_registry as reg
        return {i.trace_stage: i for i in reg.all_interventions()
                if getattr(i, "trace_stage", "")}
    except Exception:
        return {}


def _registry() -> Dict[int, Any]:
    """id -> Intervention, for display name, class and canonical default.

    Imported, never transcribed. The registry is what decides whether an
    authority is a PROMPT instruction or a post-generation TRANSFORM,
    and whether it ships on or off; a table of those facts kept here
    would be a second registry with no test holding it equal.
    """
    try:
        from api.services import lori_guard_registry as reg
        return {i.id: i for i in reg.all_interventions()}
    except Exception:
        return {}


def _resolve_trace_dir(explicit: Optional[str]) -> Tuple[Optional[Path], str]:
    """Where the traces are, and WHICH pointer said so.

    `stop_all.sh` removes the armed marker on exit, writing `last_eval_dir`
    first precisely so analysis after shutdown can still find the run.
    Falling back is correct; doing so silently is not.
    """
    if explicit:
        p = Path(explicit)
        return (p if p.is_dir() else None), f"--trace-dir {explicit}"
    armed = _armed_dir()
    if armed and (Path(armed) / "response-trace").is_dir():
        return Path(armed), f"armed marker -> {armed}"
    if LAST_MARKER.is_file():
        last = LAST_MARKER.read_text(encoding="utf-8",
                                     errors="replace").strip()
        if last and (Path(last) / "response-trace").is_dir():
            return Path(last), f"last_eval_dir -> {last}"
    if (DEFAULT_TRACE / "response-trace").is_dir():
        return DEFAULT_TRACE, f"default -> {DEFAULT_TRACE}"
    return None, "no trace directory found"


def classify(rec: Dict[str, Any]) -> str:
    """One of the four outcomes. Never inferred from absence."""
    if rec.get("terminal_outcome"):
        return NEVER_GENERATED
    has_raw = bool(rec.get("raw_captured")) and rec.get("raw_text") is not None
    has_delivered = rec.get("delivered_text") is not None
    if not (has_raw and has_delivered):
        return NOT_CAPTURED
    return UNCHANGED if rec["raw_text"] == rec["delivered_text"] else CHANGED


def authority_rows(rec: Dict[str, Any],
                   registry: Dict[int, Any]) -> List[Dict[str, Any]]:
    """The per-authority stages `chat_ws` wrote from `authority_records`.

    `fired` and `changed` are reported separately on purpose: an
    authority that ran, reached a finding and mutated nothing is a
    validator, not a rewriter, and one column cannot say both.
    """
    rows: List[Dict[str, Any]] = []
    for st in rec.get("stages") or []:
        name = str(st.get("stage") or "")
        if not name.startswith("cc_"):
            continue
        reason = st.get("reason")
        reason = reason if isinstance(reason, dict) else {}
        aid = reason.get("authority_id")
        meta = registry.get(aid) if isinstance(aid, int) else None
        rows.append({
            "id": aid,
            "name": name[3:].split("_", 1)[-1] if aid is None else
                    (meta.name if meta else name[3:]),
            "display": meta.display if meta else "",
            "cls": meta.cls if meta else "",
            "default_on": (None if meta is None else meta.default_on),
            "selected": reason.get("selected"),
            "eligible": reason.get("eligible"),
            "fired": bool(st.get("fired")),
            "changed": bool(st.get("changed")),
            "result": reason.get("result") or "",
            "before": st.get("before") or "",
            "after": st.get("after") or "",
            "words_delta": st.get("words_delta"),
        })
    rows.sort(key=lambda r: (r["id"] is None, r["id"] if r["id"] is not None else 0))
    return rows


def other_stages(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transformations outside the per-authority set that changed text.

    Reflection shaping runs INSIDE the comm_control call and cannot be
    separated at that layer; it is traced as its own span. Response
    guards, language repair and the witness validator are separate
    stages again. A renderer that showed only `cc_*` rows would report
    a turn as unexplained when a named stage had explained it.
    """
    out = []
    for st in rec.get("stages") or []:
        name = str(st.get("stage") or "")
        if name.startswith("cc_"):
            continue
        if st.get("changed"):
            out.append(st)
    return out


def budget_lines(rec: Dict[str, Any]) -> List[str]:
    """What this turn's prompt cost, and what it had to give up.

    A kept section is not evidence that the answer was available. It is
    evidence that the SECTION was. These lines exist so a poor answer
    can be attributed to a missing fact, a dropped section, a bad
    selection or a post-generation guard — the four causes — instead of
    to whichever one is easiest to assume.

    `reason` is the field to read, not `fits`: `fits=True` covers a turn
    where nothing was shed, one where old conversation went, and one
    where Lori's own sections went to make room.
    """
    b = (rec.get("context") or {}).get("prompt_budget")
    if not isinstance(b, dict):
        return []
    out: List[str] = []
    tokens, limit = b.get("tokens"), b.get("limit")
    head = "  PROMPT   %s / %s tokens" % (tokens, limit)
    if isinstance(tokens, int) and isinstance(limit, int):
        head += "   headroom %d" % (limit - tokens)
    head += "   reason=%s" % (b.get("reason") or "?")
    out.append(head)
    out.append("           conversation turns kept %s, shed %s"
               % (b.get("kept_turns"), b.get("dropped_turns")))

    secs = b.get("sections") or []
    if not secs:
        out.append("           per-section accounting NOT RECORDED for this "
                   "turn (trace predates it)")
        out.append("")
        return out

    total = sum(int(s.get("tokens") or 0) for s in secs)
    kept = sum(int(s.get("tokens") or 0) for s in secs if s.get("kept"))
    out.append("           sections offered %d tokens, kept %d" % (total, kept))
    for s in sorted(secs, key=lambda x: -int(x.get("tokens") or 0)):
        out.append("             %-26s %-5s %6d  %s" % (
            str(s.get("name"))[:26],
            "keep" if s.get("kept") else "DROP",
            int(s.get("tokens") or 0),
            "#" * max(1, int(s.get("tokens") or 0) // 90)))
    out.append("")
    return out


def _fmt(text: str, indent: str = "      ", width: int = 74) -> str:
    text = (text or "").strip()
    if not text:
        return indent + "(empty)"
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(indent + ln for ln in lines)


def _tri(v: Any) -> str:
    if v is None:
        return "  ?  "
    return " yes " if v else " no  "


def render(records: List[Dict[str, Any]], registry: Dict[int, Any],
           source: str) -> str:
    L: List[str] = []
    add = L.append

    add("PAIRED DIAGNOSTIC TRANSCRIPT")
    add("=" * 74)
    add(f"trace source : {source}")
    add(f"turns        : {len(records)}")
    if records:
        c = records[0]
        add(f"narrator     : {c.get('narrator_id') or '(unknown)'}")
        add(f"conversation : {c.get('conversation_id') or '(unknown)'}")
    add("")
    add("ORIGINAL is the model's output before any post-generation stage.")
    add("DELIVERED is the text the narrator received. Both are captured at")
    add("one boundary: chat_ws buffers all narrator-visible output and emits")
    add("it once, after the guards run, so these are a true pair and not a")
    add("comparison across a stream.")
    add("")

    tally = {UNCHANGED: 0, CHANGED: 0, NOT_CAPTURED: 0, NEVER_GENERATED: 0}

    for n, rec in enumerate(records, start=1):
        outcome = classify(rec)
        tally[outcome] += 1
        sysd = is_system_directive(rec)

        add("─" * 74)
        head = f"TURN {n}   {outcome}"
        if sysd:
            head += "   [system directive, not a narrator turn]"
        add(head)
        add("─" * 74)
        add("  NARRATOR")
        add(_fmt(_narrator_input(rec)))
        add("")
        for line in budget_lines(rec):
            add(line)

        if outcome == NEVER_GENERATED:
            add(f"  TERMINAL OUTCOME : {rec.get('terminal_outcome')}")
            add(f"  generation begun : {rec.get('generation_attempted')}")
            add("  The model was not asked to speak, or began and did not")
            add("  finish. There is no original response to compare; this is")
            add("  a recorded system state, not a missing measurement.")
            add("")
            continue

        if outcome == NOT_CAPTURED:
            add("  raw captured      : %s" % bool(rec.get("raw_captured")))
            add("  delivered captured: %s" % (rec.get("delivered_text") is not None))
            add("  Not comparable. This is NOT evidence that the text was")
            add("  unchanged — only that the pair is incomplete.")
            add("")
            continue

        add("  ORIGINAL (model, pre-guard)   %d words"
            % (rec.get("raw_words") or 0))
        add(_fmt(rec.get("raw_text") or ""))
        add("")
        add("  DELIVERED (narrator received) %d words"
            % (rec.get("delivered_words") or 0))
        add(_fmt(rec.get("delivered_text") or ""))
        add("")

        if outcome == CHANGED:
            add("  NET %+d words between original and delivered."
                % -(rec.get("net_words_removed") or 0))
            add("")

        rows = authority_rows(rec, registry)
        if rows:
            add("  AUTHORITIES")
            add("    id  name                       sel  elig fired chg  finding")
            add("    " + "-" * 68)
            for r in rows:
                add("    %-3s %-26s %s %s %s %s  %s" % (
                    r["id"] if r["id"] is not None else "?",
                    (r["name"] or "")[:26],
                    _tri(r["selected"]), _tri(r["eligible"]),
                    _tri(r["fired"]), _tri(r["changed"]),
                    r["result"] or ""))
            off = [r for r in rows if r["default_on"] is False]
            if off:
                add("")
                add("    canonically OFF (ship disabled, not a runtime choice): "
                    + ", ".join(f"#{r['id']}" for r in off))
            vo = [r for r in rows if r["fired"] and not r["changed"]]
            if vo:
                add("    validate-only this turn (finding, no mutation): "
                    + ", ".join(f"#{r['id']}" for r in vo))
            add("")

        mutators = [r for r in rows if r["changed"]]
        for r in mutators:
            add("  ── #%s %s (%s) CHANGED THE TEXT   %+d words"
                % (r["id"], r["name"], r["cls"] or "?", r["words_delta"] or 0))
            add("     finding: %s" % (r["result"] or "(none recorded)"))
            add("     before:")
            add(_fmt(r["before"], indent="        "))
            add("     after:")
            add(_fmt(r["after"], indent="        "))
            add("")

        _by_stage = _stage_to_authority()
        for st in other_stages(rec):
            name = str(st.get("stage") or "")
            meta = _by_stage.get(name)
            if meta is not None:
                add("  ── #%s %s (%s) CHANGED THE TEXT   %+d words"
                    % (meta.id, name, meta.cls, st.get("words_delta") or 0))
                if getattr(meta, "known_harm", ""):
                    add("     registry known harm: %s"
                        % meta.known_harm.split(".")[0][:150])
            else:
                add("  ── stage %s CHANGED THE TEXT   %+d words   "
                    "(no registered authority)"
                    % (name, st.get("words_delta") or 0))
            add("     reason: %s" % json.dumps(st.get("reason")))
            add("     before:")
            add(_fmt(st.get("before") or "", indent="        "))
            add("     after:")
            add(_fmt(st.get("after") or "", indent="        "))
            add("")

        if outcome == CHANGED and not mutators and not other_stages(rec):
            add("  UNEXPLAINED: original and delivered differ and no traced")
            add("  stage recorded a change. That is a gap in instrumentation,")
            add("  not a guard acting invisibly — report it.")
            add("")

    add("═" * 74)
    add("SUMMARY   " + "   ".join(f"{k}: {v}" for k, v in tally.items()))
    add("")
    add("Nothing above is a judgement about answer quality. Whether Lori")
    add("answered well, dropped a detail that mattered, or asked the right")
    add("follow-up is not measured here and is not guessed.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--conversation", help="conversation_id (conv_id) to render")
    ap.add_argument("--narrator", help="narrator/person id to render")
    ap.add_argument("--latest", action="store_true",
                    help="render the most recent conversation in the trace")
    ap.add_argument("--list", action="store_true",
                    help="list conversations present in the trace and exit")
    ap.add_argument("--trace-dir", help="override the trace directory")
    ap.add_argument("--export", help="also write the report to this path")
    args = ap.parse_args()

    base, source = _resolve_trace_dir(args.trace_dir)
    if base is None:
        print("No response-trace directory found.")
        print("")
        print("Tracing is OPT-IN and resolves at PROCESS START:")
        print("  HORNELORE_RESPONSE_TRACE=1 must be set before the API")
        print("  starts. Setting it on a running stack does nothing.")
        print("")
        print("An absent trace means the turns were not recorded. It does")
        print("NOT mean nothing happened to them.")
        return 2

    records = _trace_records(str(base))
    if not records:
        print(f"Trace directory found ({source}) but it holds no records.")
        print("Same caveat: not recorded is not the same as unchanged.")
        return 2

    if args.list:
        seen: Dict[str, Dict[str, Any]] = {}
        for r in records:
            cid = r.get("conversation_id") or "(none)"
            e = seen.setdefault(cid, {"turns": 0, "narrator": r.get("narrator_id"),
                                      "started": r.get("started_at")})
            e["turns"] += 1
            e["started"] = min(e["started"] or 0, r.get("started_at") or 0) or e["started"]
        print(f"trace source: {source}\n")
        print("%-28s %-40s turns" % ("conversation", "narrator"))
        print("-" * 78)
        for cid, e in sorted(seen.items(), key=lambda kv: kv[1]["started"] or 0):
            print("%-28s %-40s %d" % (cid, e["narrator"] or "?", e["turns"]))
        return 0

    if args.conversation:
        sel = [r for r in records if r.get("conversation_id") == args.conversation]
    elif args.narrator:
        sel = [r for r in records if r.get("narrator_id") == args.narrator]
    elif args.latest:
        last = max(records, key=lambda r: r.get("started_at") or 0)
        sel = [r for r in records
               if r.get("conversation_id") == last.get("conversation_id")]
    else:
        ap.error("choose one of --conversation / --narrator / --latest / --list")
        return 2

    if not sel:
        print("No traced turns matched. Use --list to see what is present.")
        return 2

    sel.sort(key=lambda r: r.get("started_at") or 0)
    report = render(sel, _registry(), source)
    print(report)

    if args.export:
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report + "\n", encoding="utf-8")
        print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
