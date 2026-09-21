#!/usr/bin/env python3
"""Export every narrator as a portable BagIt package. READ ONLY.

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/export_all_narrators.py --preflight
    .venv-gpu/bin/python scripts/export_all_narrators.py --export

WHY A SCRIPT AND NOT THE PANEL
==============================
The Operator panel exports one narrator at a time, and a machine move
needs all of them with a record of what each one contained. This drives
the SAME routes the panel drives — preflight, export, poll, download —
so nothing here is a second implementation of packaging. It creates no
package itself; `narrator_package.py` does, exactly as it does for the
panel.

WHAT A PACKAGE HOLDS, MEASURED
==============================
Not just transcripts. `Janice_aca0cdfd9c13.lorevox.zip` (2026-09-12)
carries 65 `data/records/*.jsonl` tables — including
`bio_builder_questionnaires`, `profiles`, `interview_projections`,
`turns`, `sessions` and `people` — beside the file archive, under
sha256 manifests for both payload and tags.

THE PACKAGES ON DISK ARE STALE
==============================
`C:\\lorevox_packages` holds bags dated 2026-09-12 and 09-14. Every
biography change since — the questionnaire Lori now reads, the
suggestion queue, this month's sessions — postdates them. Restoring
from those would silently roll a narrator back. Re-export first; that
is what this script is for.

IT REFUSES TO GUESS
===================
No narrator id is hardcoded. It reads the live `/api/people` list, and
prints what it found before doing anything. `--preflight` builds
nothing at all: it reports what an export WOULD contain, per lane, so
a surprising count is visible before a 128 MB package exists rather
than after.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
BASE = "/api/operator/narrator-package"


def _get(path):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read().decode() or "{}")


def _post(path, payload=None):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(API + path, method="POST", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode() or "{}")


def _people():
    raw = _get("/api/people?limit=200")
    rows = raw.get("people") if isinstance(raw, dict) else raw
    return [(p.get("id"), str(p.get("display_name") or ""),
             bool(p.get("testing_only"))) for p in (rows or []) if p.get("id")]


def cmd_preflight(args):
    people = _people()
    print("narrators on this machine: %d\n" % len(people))
    for pid, name, testing in people:
        if args.real_only and testing:
            print("  %-34s SKIPPED (testing_only)" % name[:34])
            continue
        try:
            rep = _get("%s/preflight/%s" % (BASE, pid))
        except urllib.error.HTTPError as e:
            print("  %-34s PREFLIGHT FAILED %s: %s"
                  % (name[:34], e.code, e.read().decode()[:120]))
            continue
        s = rep.get("summary") or {}
        print("  %-34s %-10s records=%-6s files=%-5s %s"
              % (name[:34], "(test)" if testing else "",
                 s.get("records"), s.get("files"), s.get("size_human")))
    print("\nNothing was built. `--export` creates the packages.")
    return 0


def cmd_export(args):
    people = _people()
    todo = [(p, n) for p, n, t in people if not (args.real_only and t)]
    print("exporting %d narrator(s). One at a time — the server holds a "
          "single export lock.\n" % len(todo))
    done = []
    for pid, name in todo:
        try:
            job = _post("%s/export/%s" % (BASE, pid))
        except urllib.error.HTTPError as e:
            print("  %-34s START FAILED %s: %s"
                  % (name[:34], e.code, e.read().decode()[:140]))
            continue
        jid = job.get("job_id")
        print("  %-34s job %s" % (name[:34], (jid or "")[:8]), end="", flush=True)
        state, last = "queued", None
        for _ in range(args.timeout):
            time.sleep(2)
            try:
                row = _get("%s/export/jobs/%s" % (BASE, jid))
            except Exception:
                continue
            state = row.get("state") or state
            if state != last:
                print(" -> %s" % state, end="", flush=True)
                last = state
            if state in ("complete", "failed", "refused"):
                break
        print()
        if state == "complete":
            done.append((name, jid))
        else:
            print("      ended in state=%r — not downloaded" % state)
    print()
    if done:
        print("Download each with:")
        for name, jid in done:
            print("  curl -OJ %s%s/export/jobs/%s/download" % (API, BASE, jid))
        print("\nOr use the Operator panel's download button — same route.")
    print("\nThe server keeps its own copy until you remove it:")
    print("  POST %s/export/jobs/<job_id>/remove-server-copy" % BASE)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preflight", action="store_true",
                    help="report what each export would contain; build nothing")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--real-only", action="store_true",
                    help="skip testing_only narrators (ZZ fixtures)")
    ap.add_argument("--timeout", type=int, default=300,
                    help="poll iterations per job, 2s apart")
    ap.add_argument("--api", default=API)
    args = ap.parse_args()
    globals()["API"] = args.api
    if args.preflight:
        return cmd_preflight(args)
    if args.export:
        return cmd_export(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
