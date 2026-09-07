#!/usr/bin/env python3
"""Print the Lori intervention catalog.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Part 10.

GENERATED FROM `lori_guard_registry`, never hand-maintained. A second
handwritten catalog would drift from the registry the first time
anything changed, and the drifting copy would be the one people read —
which is the exact failure CLAUDE.md records for its own stale
current-work lists.

Read-only. Prints; changes nothing.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/lori_guard_catalog.py
    PYTHONPATH=server/code .venv/bin/python scripts/lori_guard_catalog.py --summary
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "code"))

from api.services import lori_guard_registry as reg  # noqa: E402


def _wrap(text, width=72, indent=" " * 6):
    words, line, out = text.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(indent + line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(indent + line)
    return "\n".join(out)


def print_summary():
    items = reg.in_pipeline_order()
    counts = reg.policy_counts()
    print(f"Lori intervention registry — {len(items)} entries: "
          + ", ".join(f"{n} {p}" for p, n in sorted(counts.items())))
    if counts.get(reg.POLICY_PENDING_SEAM):
        print("  NOTE: 'All Switchable Off' does NOT disable PENDING_SEAM "
              "entries — they are not yet separable in code.")
    print()
    print(f"  {'ID':>3}  {'POS':>4}  {'CLASS':<12} {'CF':<16} "
          f"{'DEFAULT':<8} {'POLICY':<13} NAME")
    print("  " + "-" * 96)
    for i in items:
        print(f"  {i.id:>3}  {i.position:>4}  {i.cls:<12} "
              f"{i.counterfactual:<16} "
              f"{'on' if i.default_on else 'off':<8} {i.policy:<13} "
              f"{i.display}")
    print()
    for cls in sorted(reg.VALID_CLASSES):
        members = reg.by_class(cls)
        if members:
            print(f"  {cls:<14} {len(members):>2}  "
                  f"{', '.join(str(m.id) for m in members)}")


def print_full():
    for i in reg.in_pipeline_order():
        state = "on" if i.default_on else "off"
        print("=" * 78)
        print(f"{i.id:>3} — {i.display}")
        print(f"     class={i.cls}  position={i.position}  "
              f"canonical_default={state}  policy={i.policy}")
        print(f"     counterfactual={i.counterfactual}")
        print(f"     location: {i.location}")
        if i.trace_stage:
            print(f"     trace stage: {i.trace_stage}")
        print("\n     Purpose:")
        print(_wrap(i.purpose))
        print("\n     Motivating failure:")
        print(_wrap(i.motivating_failure))
        if i.known_harm:
            print("\n     Known harm / measured regression:")
            print(_wrap(i.known_harm))
        if i.policy_reason:
            label = ("Not separable yet:"
                     if i.policy == reg.POLICY_PENDING_SEAM
                     else "Protected because:")
            print(f"\n     {label}")
            print(_wrap(i.policy_reason))
        if i.tests:
            print("\n     Tests:")
            for t in i.tests:
                print(f"      {t}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", action="store_true",
                    help="one line per intervention")
    args = ap.parse_args()
    if args.summary:
        print_summary()
    else:
        print_full()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
