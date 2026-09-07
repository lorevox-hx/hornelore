#!/usr/bin/env python3
"""Phase 6 — render the lean conversational baseline. READ ONLY.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv-gpu/bin/python \
        scripts/phase6_conversation_capture.py --narrator "Ada Pruitt"

WHAT THIS IS NOT. It is not a second trace reader. `_trace_records`,
`_authority`, `_armed_dir`, `_db_path` and `_read_only` are IMPORTED from
`guard_lab_live_acceptance` rather than reimplemented, because two readers
of one trace format stay equal exactly until the first change — the
failure this repository has now recorded against a renderer/predicate
pair, a baseline inventory beside its registry, and a resolver about to
become two.

WHY NOTHING NEW HAD TO BE INSTRUMENTED. Every per-turn field Chris asked
for is already written by the shipped trace:

    narrator_input          <- chat_ws.py:97 / :1621
    raw_text                <- lori_response_trace.py:261
    delivered_text          <- :340   (and `delivered_words`, :341)
    delivered_questions     <- :342   the question count, already derived
    raw_equals_delivered    <- :350
    net_words_removed       <- :351
    authority_revision      <- chat_ws.py:1729, from
    authority_*fingerprint     `lori_guard_authority.trace_identity()`:215
    turn_key                <- bound late by `bind_turn_key`, Block C

That last one is what makes the extraction join possible at all. Before
Block C a Guard Lab trace persisted with `turn_key: ""`, so a transcript
and its extraction result could not be tied together without guessing.

MEASURED VS JUDGED — AND WHY THE JUDGEMENT COLUMNS ARE LEFT EMPTY
=================================================================

Chris's capture list mixes two different kinds of thing, and printing
them in one table without saying which is which is how a judgement gets
quoted back later as a measurement.

  MEASURED, and filled in here — raw vs delivered, whether they are
  equal, word counts, question count, the active configuration, the
  extraction outcome.

  JUDGED, and deliberately left BLANK for a human — details reflected,
  details dropped, invented significance, whether the question follows
  the strongest thread.

This script will not guess the second group. A blank cell is an honest
statement that nobody has judged it yet; a generated guess in that column
would be indistinguishable from a finding.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# ONE reader. See the module docstring.
from guard_lab_live_acceptance import (  # noqa: E402
    _armed_dir, _db_path, _read_only, _trace_records, _authority,
)

_JUDGED = ("details reflected", "details dropped", "invented significance",
           "follows strongest thread")


def _rows_conn() -> sqlite3.Connection:
    """`_read_only` deliberately returns a bare connection.

    It is shared with the acceptance verifier, which reads by index. This
    renderer reads by column NAME, so it attaches the row factory here
    rather than changing the shared helper out from under that caller.
    """
    con = _read_only(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _resolve_narrator(name_or_id: str) -> Optional[Dict[str, Any]]:
    con = _rows_conn()
    try:
        row = con.execute(
            "SELECT id, display_name, COALESCE(testing_only,0) AS testing_only "
            "FROM people WHERE is_deleted=0 AND (id=? OR display_name=?) "
            "LIMIT 1;",
            (name_or_id, name_or_id),
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


def _extraction_by_turn_key(narrator_id: str) -> Dict[str, Dict[str, Any]]:
    """turn_key -> newest extraction row. Read only, no product call."""
    con = _rows_conn()
    out: Dict[str, Dict[str, Any]] = {}
    try:
        rows = con.execute(
            "SELECT * FROM turn_extraction_results WHERE narrator_id=? "
            "ORDER BY id ASC;",
            (narrator_id,),
        ).fetchall()
    except Exception as exc:                       # table absent is a FACT
        print(f"  (turn_extraction_results unreadable: {exc})",
              file=sys.stderr)
        return out
    finally:
        con.close()
    for row in rows:
        rec = {k: row[k] for k in row.keys()}
        key = str(rec.get("turn_key") or "")
        if key:
            out[key] = rec                          # ASC, so newest wins
    return out


def _loads(raw: Any, fallback: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw) if raw else fallback
    except Exception:
        return fallback


def _extraction_summary(rec: Optional[Dict[str, Any]]) -> str:
    if rec is None:
        return "no extraction row joined to this turn_key"
    items = _loads(rec.get("items"), [])
    clar = _loads(rec.get("clarification_required"), [])
    reasons = []
    for entry in clar if isinstance(clar, list) else []:
        if isinstance(entry, dict):
            reasons.append(str(entry.get("disposition")
                               or entry.get("reason") or "?"))
    bits = [f"status={rec.get('status') or '?'}",
            f"items={len(items) if isinstance(items, list) else '?'}"]
    if reasons:
        bits.append("dispositions=" + ",".join(sorted(set(reasons))))
    return "  ".join(bits)


def _render(records: List[Dict[str, Any]], narrator: Dict[str, Any],
            extraction: Dict[str, Dict[str, Any]]) -> str:
    out: List[str] = []
    add = out.append
    add(f"# Phase 6 — lean conversational baseline")
    add("")
    add(f"Narrator: **{narrator['display_name']}**  `{narrator['id']}`  "
        f"testing_only={bool(narrator['testing_only'])}")
    add(f"Traced turns: **{len(records)}**")
    add("")
    add("Measured fields come from the shipped response trace. The four "
        "judgement columns are left blank on purpose — see the script "
        "docstring.")
    add("")

    for index, rec in enumerate(records, start=1):
        ctx = rec.get("context") or {}
        auth = _authority(rec)
        key = str(rec.get("turn_key") or "")
        raw = rec.get("raw_text")
        delivered = rec.get("delivered_text")

        add(f"## Turn {index}")
        add("")
        add(f"* trace `{rec.get('trace_id') or '?'}`   turn_key "
            f"`{key or 'UNBOUND'}`")
        add(f"* revision `{auth.get('revision')}`   selection "
            f"`{auth.get('selection_fingerprint')}`   registry "
            f"`{auth.get('registry_fingerprint')}`")
        selected = auth.get("selected")
        add(f"* selected authorities: "
            f"{len(selected) if isinstance(selected, list) else '?'}   "
            f"experiment_applied={auth.get('experiment_applied')}   "
            f"gate_reason={auth.get('gate_reason')}")
        add("")
        add("**Narrator said**")
        add("")
        add("> " + str(ctx.get("narrator_input") or "(not captured)")
            .replace("\n", "\n> "))
        add("")

        if raw is None and delivered is None:
            add(f"**No text on this trace.** terminal_outcome="
                f"`{ctx.get('terminal_outcome')}` "
                f"generation_attempted={ctx.get('generation_attempted')}")
            add("")
        else:
            equal = rec.get("raw_equals_delivered")
            add(f"**Lori — raw** ({rec.get('raw_words', '?')} words)")
            add("")
            add("> " + str(raw or "(absent)").replace("\n", "\n> "))
            add("")
            if equal is True:
                add("**Lori — delivered: IDENTICAL to raw.** The "
                    "post-generation layer removed nothing.")
            else:
                add(f"**Lori — delivered** "
                    f"({rec.get('delivered_words', '?')} words, "
                    f"net_words_removed={rec.get('net_words_removed', '?')})")
                add("")
                add("> " + str(delivered or "(absent)")
                    .replace("\n", "\n> "))
            add("")
            add(f"* raw_equals_delivered: **{equal}**")
            add(f"* questions asked (delivered): "
                f"**{rec.get('delivered_questions', '?')}**")
        add(f"* extraction: {_extraction_summary(extraction.get(key))}")
        add("")
        add("Judgement (blank until a human fills it in):")
        add("")
        for label in _JUDGED:
            add(f"* {label}: ")
        add("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--narrator", default="Ada Pruitt",
                        help="display name or person id")
    parser.add_argument("--eval-dir", default=None,
                        help="armed run dir; defaults to the armed marker")
    parser.add_argument("--out", default=None,
                        help="write markdown here instead of stdout")
    args = parser.parse_args()

    narrator = _resolve_narrator(args.narrator)
    if not narrator:
        print(f"No narrator matching {args.narrator!r}.", file=sys.stderr)
        return 1

    armed = args.eval_dir or _armed_dir()
    if not armed:
        print("No armed trace directory. `HORNELORE_RESPONSE_TRACE` must "
              "have been armed for the session, and the marker must "
              "survive it — nothing to render.", file=sys.stderr)
        return 1

    everything = _trace_records(armed)
    mine = [r for r in everything
            if str(r.get("narrator_id") or "") == narrator["id"]]
    if not mine:
        print(f"{len(everything)} traced turns in {armed}, NONE for "
              f"{narrator['display_name']}. Refusing to render a report "
              f"that would read like a silent session.", file=sys.stderr)
        return 1

    text = _render(mine, narrator, _extraction_by_turn_key(narrator["id"]))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}  ({len(mine)} turns)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
