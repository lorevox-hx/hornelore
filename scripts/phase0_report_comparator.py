#!/usr/bin/env python3
"""READ ONLY. Compare Phase 0 ownership-audit reports from different machines / roots.

WO-LOREVOX-PORTABLE-NARRATOR-01, between Phase 1 and Phase 2. Answers, per
narrator and per lane, WHERE the narrator's evidence lives: on which copy,
and whether a copy is unique. It reads the `ownership-audit.json` files the
Phase 0 audit wrote and touches nothing else -- no database, no data root.

Counts are what the audit measured. They tell you where to look; they do
NOT prove two copies hold the same rows (only an id comparison does that),
and a lane with equal counts on two machines may still differ. The report
says so on every page.

USAGE (any machine that has the report folders; Chris's whole part):

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/phase0_report_comparator.py \\
        .runtime/eval/phase0-ownership-audit-desktop-live-*/ownership-audit.json \\
        .runtime/eval/phase0-ownership-audit-laptop-live-*/ownership-audit.json \\
        .runtime/eval/phase0-ownership-audit-desktop-backup-0723-*/ownership-audit.json

Any number of reports; columns are their `--label`s. Output goes under
`.runtime/eval/phase0-report-comparison-<ts>/` (gitignored) and nowhere else.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def _refuse_unless_gitignored_out(out: Path, repo: Path) -> None:
    try:
        rel = out.resolve().relative_to(repo.resolve())
    except ValueError:
        return  # outside the repo entirely: allowed
    ok = bool(rel.parts) and (rel.parts[0] == ".runtime" or tuple(rel.parts[:2]) == ("docs", "reports"))
    if not ok:
        raise SystemExit(
            f"REFUSING: --out {out} is inside the repository but not under .runtime/ or "
            f"docs/reports/. This comparison carries real-family counts and ids.")


def _load(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        d = json.load(fh)
    for key in ("label", "machine", "people", "per_narrator", "table_rows"):
        if key not in d:
            raise SystemExit(f"REFUSING: {path} has no '{key}' — not a Phase 0 audit JSON "
                             f"written by scripts/phase0_narrator_ownership_audit.py with --label")
    return d


def _short(pid: str) -> str:
    return pid[:8]


_TEST_NAME_RX = None


def _classify_person(rows: List[Dict[str, Any]]) -> str:
    """Population class of ONE people id from every copy's row for it.

    `real`            live narrator_type, never testing_only, not deleted anywhere,
                      display name not a harness / smoke / fixture pattern
    `synthetic/test`  testing_only on any copy, narrator_type 'reference', or a
                      display name that names a harness, smoke test, fixture or
                      synthetic (Ada) narrator
    `deleted residue` is_deleted on every copy that knows it (rows may survive)
    `unnamed`         no display name anywhere — cannot be placed; listed, not counted as real

    This is a LABEL from the people row's own fields and name, so a reader can
    tell 107 population ids from 4 real narrators. It decides nothing.
    Graph persons, family-truth rows and photo people are NOT in this
    population at all: the audit keys per_narrator by people.id only.
    """
    import re
    global _TEST_NAME_RX
    if _TEST_NAME_RX is None:
        _TEST_NAME_RX = re.compile(
            r"harness|smoke|fixture|synthetic|probe|\bada\b|zz cohort|cohort|test\b|"
            r"\(harness|paste_|sample|demo|dummy", re.IGNORECASE)
    names = [str(r.get("display_name") or "").strip() for r in rows]
    if any(r.get("testing_only") for r in rows):
        return "synthetic/test"
    if any((r.get("narrator_type") or "") == "reference" for r in rows):
        return "synthetic/test"
    if any(_TEST_NAME_RX.search(n) for n in names if n):
        return "synthetic/test"
    if all(r.get("is_deleted") for r in rows):
        return "deleted residue"
    if not any(names) or all(n.lower() == "unnamed" for n in names if n):
        return "unnamed"
    return "real"


def _lane_key(k: str) -> str:
    """'trip_days (via trips)' -> 'trip_days'. The audit names one-level FK
    children by the parent they were reached through."""
    return k.split(" (via ")[0]


def build(reports: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    labels = [r["label"] for r in reports]
    if len(set(labels)) != len(labels):
        raise SystemExit(f"REFUSING: duplicate --label among reports: {labels}. "
                         f"Two reports with one label cannot be told apart.")

    # people: id -> {label: display_name}
    people: Dict[str, Dict[str, str]] = {}
    deleted: Dict[str, Set[str]] = {}
    people_rows: Dict[str, List[Dict[str, Any]]] = {}
    for r in reports:
        for p in r["people"]:
            people.setdefault(p["id"], {})[r["label"]] = p.get("display_name") or ""
            people_rows.setdefault(p["id"], []).append(p)
            if p.get("is_deleted"):
                deleted.setdefault(p["id"], set()).add(r["label"])
    klass: Dict[str, str] = {pid: _classify_person(rows) for pid, rows in people_rows.items()}

    # per narrator per lane per label
    counts: Dict[str, Dict[str, Dict[str, int]]] = {}
    # `_unmatched_person_ids`: rows whose person id matches NO people row,
    # as {table: {id: count}}. Orphans, not narrators; reported separately.
    orphans: Dict[str, Dict[str, Dict[str, int]]] = {}
    for r in reports:
        for pid, lanes in r["per_narrator"].items():
            if pid.startswith("_"):
                if pid == "_unmatched_person_ids":
                    for table, by_id in lanes.items():
                        for oid, n in by_id.items():
                            orphans.setdefault(oid, {}).setdefault(table, {})[r["label"]] = int(n)
                continue
            for k, n in lanes.items():
                counts.setdefault(pid, {}).setdefault(_lane_key(k), {})[r["label"]] = int(n)

    # table totals per label (for the whole-DB view), and which tables a
    # copy's schema era HAS and whether rows there can be attributed to a
    # person at all (a person column, or an FK chain that reaches people).
    totals: Dict[str, Dict[str, int]] = {}
    tables_present: Dict[str, Set[str]] = {}
    attributable: Dict[str, Set[str]] = {}
    for r in reports:
        for row in r["table_rows"]:
            totals.setdefault(row["table"], {})[r["label"]] = int(row.get("row_count") or 0)
            tables_present.setdefault(r["label"], set()).add(row["table"])
            if row.get("person_column") or row.get("fk_chain_to_people"):
                attributable.setdefault(r["label"], set()).add(row["table"])

    # Copies group by MACHINE. A lane on a machine's live AND its own backup
    # is one copy of the evidence, not two; "unique" means one machine.
    machine_of: Dict[str, str] = {r["label"]: str(r.get("machine") or "?") for r in reports}
    machines = sorted(set(machine_of.values()))
    ids_on_both_machines = [pid for pid, names in people.items()
                            if len({machine_of[l] for l in names}) > 1]

    L: List[str] = []
    w = L.append
    w("# Phase 0 — cross-copy comparison (READ ONLY, counts from audit JSONs)")
    w("")
    w("| column | machine | commit | database | run |")
    w("|---|---|---|---|---|")
    for r in reports:
        w(f"| `{r['label']}` | `{r.get('machine','?')}` | `{r.get('commit','?')}` | `{r.get('db','?')}` | {r.get('when','?')} |")
    w("")
    w("**Counts locate evidence; they do not prove equality.** Equal counts on two copies "
      "can still be different rows; only an id comparison settles that. **Copies are grouped "
      "by machine** (" + ", ".join(f"`{m}`" for m in machines) + "): a machine's live database "
      "and its own backups are one body of evidence, so `UNIQUE` means *one machine*, not one "
      "file. Every id in this report is a `people`-table row — a narrator identity, including "
      "deleted and test-harness rows — never a graph person or other entity.")
    w("")

    # ── narrators: which machines know this id ──────────────────────────
    w("## Population — what the `people` ids in these reports are")
    w("")
    w("Classified from each row's own fields (`testing_only`, `narrator_type`, `is_deleted`) "
      "and display name. A label, not a decision. **Graph persons, family-truth rows and "
      "photo people are not in this population** — the audit keys `per_narrator` by "
      "`people.id` only, so nothing here is a supporting entity.")
    w("")
    w("| class | ids | on both machines |")
    w("|---|---:|---:|")
    for c in ("real", "synthetic/test", "deleted residue", "unnamed"):
        ids = [p for p, k in klass.items() if k == c]
        both = [p for p in ids if p in ids_on_both_machines]
        w(f"| {c} | {len(ids)} | {len(both)} |")
    w("")
    reals = [p for p, k in klass.items() if k == "real"]
    w("**Real narrators:** " + (", ".join(f"`{_short(p)}` {next(iter(people[p].values()))}" for p in reals) or "_none_"))
    w("")
    w("## Narrator ids — which machines and copies know them")
    w("")
    w(f"* `people` ids seen in any report: **{len(people)}**")
    w(f"* ids present on **more than one machine** (the only ones a reconciliation has to "
      f"think about): **{len(ids_on_both_machines)}** — " +
      ", ".join(f"`{_short(p)}` {next(iter(people[p].values()))}" for p in ids_on_both_machines[:12]) +
      (" …" if len(ids_on_both_machines) > 12 else ""))
    w(f"* ids present on more than one *copy* (mostly a machine's live + its own backup): "
      f"**{sum(1 for n in people.values() if len(n) > 1)}** — not a reconciliation number")
    w("")
    w("| id | class | " + " | ".join(f"`{l}`" for l in labels) + " | note |")
    w("|---|---|" + "---|" * len(labels) + "---|")
    multi = ids_on_both_machines
    for pid, names in sorted(people.items(), key=lambda kv: (-len({machine_of[l] for l in kv[1]}), -len(kv[1]))):
        cells = [klass[pid]]
        for l in labels:
            if l in names:
                d = " (deleted)" if l in deleted.get(pid, set()) else ""
                cells.append(f"{names[l]}{d}")
            else:
                cells.append("—")
        on_machines = sorted({machine_of[l] for l in names})
        if len(on_machines) > 1:
            note = "**on BOTH machines — reconcile by lane below**"
        else:
            note = f"one machine: `{on_machines[0]}`"
        w(f"| `{_short(pid)}` | " + " | ".join(cells) + f" | {note} |")
    w("")

    # ── per-narrator lane matrix ─────────────────────────────────────────
    w("## Per-narrator lanes — where each lane's rows are")
    w("")
    w("Cells: a count · `0` = table exists and attributes rows to people, none are this "
      "narrator's · `unattrib.` = the table exists in that copy but its schema era cannot "
      "attribute rows to a person at all (e.g. `sessions` before migration 0044 added "
      "`person_id`) — rows may exist and are NOT counted · `n/a` = the table does not exist "
      "in that copy's schema · `—` = the narrator id is unknown to that copy. "
      "Verdicts: `UNIQUE:<machine>` = rows on one machine only, lost if that machine is not "
      "exported · `⚠ differs` = both machines have rows, counts differ, compare ids · "
      "`same count on both machines` = ids still unverified.")
    w("")
    unique_summary: Dict[str, Dict[str, List[str]]] = {}
    differs_summary: Dict[str, List[str]] = {}
    for pid in sorted(counts, key=lambda p: (-len({machine_of[l] for l in people.get(p, {})}), p)):
        names = people.get(pid, {})
        if not names:
            continue
        display = next(iter(names.values()))
        lanes = counts[pid]
        known_on = set(names)
        w(f"### `{_short(pid)}` {display} — *{klass[pid]}*")
        w("")
        w("| lane | " + " | ".join(f"`{l}`" for l in labels) + " | verdict |")
        w("|---|" + "---|" * len(labels) + "---|")
        for lane in sorted(lanes, key=lambda x: (-max(lanes[x].values()), x)):
            per = lanes[lane]
            cells = []
            present_on = []
            for l in labels:
                if lane not in tables_present.get(l, set()):
                    cells.append("n/a")
                elif l in per:
                    cells.append(str(per[l]))
                    present_on.append(l)
                elif lane not in attributable.get(l, set()):
                    cells.append("unattrib.")
                elif pid in known_on:
                    cells.append("0")
                else:
                    cells.append("—")
            machines_with_rows = sorted({machine_of[l] for l in present_on})
            live_counts = {machine_of[l]: per[l] for l in present_on}  # last copy per machine wins the label; counts compared below
            if len(machines_with_rows) == 1 and len(machines) > 1:
                if pid in multi:
                    verdict = f"**UNIQUE:`{machines_with_rows[0]}`**"
                    unique_summary.setdefault(pid, {}).setdefault(machines_with_rows[0], []).append(lane)
                else:
                    verdict = f"only machine that knows this id: `{machines_with_rows[0]}`"
            elif len(machines_with_rows) > 1:
                # compare the LIVE copies of each machine when both have one
                per_machine = {}
                for l in present_on:
                    m = machine_of[l]
                    if m not in per_machine or "live" in l:
                        per_machine[m] = per[l]
                if len(set(per_machine.values())) > 1:
                    verdict = "⚠ differs — compare ids"
                    differs_summary.setdefault(pid, []).append(lane)
                else:
                    verdict = "same count on both machines — ids unverified"
            else:
                verdict = ""
            w(f"| `{lane}` | " + " | ".join(cells) + f" | {verdict} |")
        w("")

    # ── summaries ───────────────────────────────────────────────────────
    w("## Summary — narrators on both machines, and what only one machine holds")
    w("")
    if not multi:
        w("_no narrator id appears on more than one machine_")
    for pid in multi:
        display = next(iter(people[pid].values()))
        w(f"* `{_short(pid)}` {display}:")
        for m, lanes in unique_summary.get(pid, {}).items():
            w(f"  * only on `{m}`: " + ", ".join(f"`{x}`" for x in lanes))
        if pid in differs_summary:
            w("  * on both, counts differ (compare ids): " + ", ".join(f"`{x}`" for x in differs_summary[pid]))
    w("")
    single_machine_with_rows = [p for p in counts if p in people and p not in multi]
    by_class = {}
    for p in single_machine_with_rows:
        by_class[klass[p]] = by_class.get(klass[p], 0) + 1
    w(f"Narrator ids on ONE machine only, with rows: **{len(single_machine_with_rows)}** "
      f"({', '.join(f'{k}: {n}' for k, n in sorted(by_class.items()))}) — not reconciliation "
      f"cases. A real one is exported from the machine that holds it; synthetic / test / "
      f"deleted ids are never swept into anyone's package — the exporter takes ONE selected "
      f"narrator id and follows the declaration from it.")
    w("")

    # ── whole-DB totals for lanes that matter ────────────────────────────
    w("## Whole-database totals (all owners) — selected lanes")
    w("")
    w("| table | " + " | ".join(f"`{l}`" for l in labels) + " |")
    w("|---|" + "---|" * len(labels))
    for t in ("people", "sessions", "turns", "photos", "trips", "trip_sources", "trip_days",
              "trip_photo_links", "trip_turn_links", "story_candidates", "bio_facts",
              "memory_archive_sessions", "memory_archive_turns", "media_archive_items",
              "import_batch", "import_candidate"):
        per = totals.get(t, {})
        w(f"| `{t}` | " + " | ".join(str(per[l]) if l in per else "n/a" for l in labels) + " |")
    w("")
    # ── orphans: rows whose owner id matches no people row on that copy ──
    w("## Orphan owner ids — rows whose person id matches NO people row on that copy")
    w("")
    w("An id here is a narrator that was deleted (or never existed) on that copy while rows "
      "kept naming it. If the SAME id is a live narrator on another copy, those rows are that "
      "narrator's and belong in the reconciliation, not in the orphan pile.")
    w("")
    w("| orphan id | table | " + " | ".join(f"`{l}`" for l in labels) + " | live narrator elsewhere? |")
    w("|---|---|" + "---|" * len(labels) + "---|")
    shown = 0
    for oid in sorted(orphans, key=lambda o: -sum(sum(v.values()) for v in orphans[o].values())):
        elsewhere = [l for l, name in people.get(oid, {}).items()]
        for table, per in sorted(orphans[oid].items()):
            w(f"| `{_short(oid)}` | `{table}` | " +
              " | ".join(str(per[l]) if l in per else "—" for l in labels) +
              f" | {('**YES: ' + ', '.join('`'+l+'`' for l in elsewhere) + '**') if elsewhere else 'no'} |")
            shown += 1
            if shown >= 60:
                break
        if shown >= 60:
            w(f"| … | … | " + " | ".join("…" for _ in labels) + " | truncated at 60 rows; full data in comparison.json |")
            break
    w("")
    w("## What this did NOT do")
    w("")
    w("* Did not open any database or data root; read only the audit JSONs named on the command line.")
    w("* Did not compare row ids or file hashes. A lane marked `equal counts` is NOT proven equal.")
    w("* Did not decide anything. Phase 6 exports from every copy that holds a UNIQUE lane.")
    return "\n".join(L) + "\n", {
        "labels": labels, "machines": machines, "machine_of_label": machine_of,
        "people_ids_seen": len(people),
        "population": {c: sum(1 for k in klass.values() if k == c) for c in set(klass.values())},
        "class_by_id": klass,
        "real_on_both_machines": sum(1 for p in multi if klass[p] == "real"),
        "ids_on_more_than_one_machine": multi,
        "ids_on_more_than_one_copy": sum(1 for n in people.values() if len(n) > 1),
        "people": people, "counts": counts, "totals": totals,
        "unique_by_machine": unique_summary, "differs_between_machines": differs_summary,
        "orphans": orphans,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+", type=Path, help="ownership-audit.json files (2 or more)")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if len(args.reports) < 2:
        raise SystemExit("REFUSING: a comparison needs at least two reports.")
    reports = [_load(p) for p in args.reports]
    when = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or (args.repo / ".runtime" / "eval" / f"phase0-report-comparison-{when}")
    _refuse_unless_gitignored_out(out, args.repo)
    md, data = build(reports)
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.md").write_text(md, encoding="utf-8")
    (out / "comparison.json").write_text(json.dumps(data, indent=2, default=sorted), encoding="utf-8")
    print(f"wrote {out / 'comparison.md'}")
    pop = data["population"]
    print(f"copies={len(reports)} machines={data['machines']} people_ids_seen={data['people_ids_seen']} "
          f"population=real:{pop.get('real',0)}/synthetic-test:{pop.get('synthetic/test',0)}/"
          f"deleted-residue:{pop.get('deleted residue',0)}/unnamed:{pop.get('unnamed',0)}")
    print(f"ids_on_both_machines={len(data['ids_on_more_than_one_machine'])} "
          f"(real:{data['real_on_both_machines']}) — the reconciliation set; "
          f"of those, with lanes only on one machine={len(data['unique_by_machine'])}, "
          f"with lanes differing between machines={len(data['differs_between_machines'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
