"""Bridge for the Questionnaire V2 DOM harness (Batch C).

The jsdom harness's fake `fetch` sends every /api/life-record request here,
so the browser code under test talks to the SHIPPED writer and assembler on
real SQLite — not to a JavaScript imitation of them. Status mapping mirrors
routers/life_record.py (200 / 404 / 409 conflict / 422).

ONE long-lived process (C-2R6, 2026-09-24). The first version spawned a new
Python per request; importing `api.db` on the /mnt/c mount under .venv made
the 25-check shell run exceed 170 s. Now the harness starts this once:

    python tests/qv2_bridge.py <db_path> --serve

and writes one JSON request per line {"id", "method", "pid", "body"?}; each
reply is one JSON line {"id", "status", "body"}.
"""
import contextlib
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

with contextlib.redirect_stdout(io.StringIO()):   # import chatter must not corrupt the replies
    from api import db as _db  # noqa: E402
    from api.services.life_record import writer as W  # noqa: E402


def handle(method: str, pid: str, body):
    with contextlib.redirect_stdout(io.StringIO()):
        if not _db.get_person(pid):
            return 404, {"detail": "Narrator not found"}
        if method == "GET":
            return 200, W.read_record(pid)
        if method == "PATCH":
            b = json.loads(body) if isinstance(body, str) else (body or {})
            r = W.apply_changes(pid, b.get("baseRevision"), b.get("changes") or [], b.get("actor"))
            if r.get("ok"):
                return 200, r
            return (409 if "conflict" in r else 422), {"detail": r}
        return 405, {"detail": method}


def main():
    _db.DB_PATH = Path(sys.argv[1])
    out = sys.stdout
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        try:
            status, body = handle(req["method"], req["pid"], req.get("body"))
        except Exception as exc:  # a crash is a 500, reported — never a hang
            status, body = 500, {"detail": f"{type(exc).__name__}: {exc}"}
        out.write(json.dumps({"id": req["id"], "status": status, "body": body}, default=str) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
