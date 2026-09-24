"""Bridge for the Questionnaire V2 DOM harness (Batch C).

The jsdom harness's fake `fetch` calls this for every /api/life-record
request, so the browser code under test talks to the SHIPPED writer and
assembler on real SQLite — not to a JavaScript imitation of them. Status
mapping mirrors routers/life_record.py (200 / 404 / 409 conflict / 422).

    python tests/qv2_bridge.py <db_path> GET   <narrator_id>
    python tests/qv2_bridge.py <db_path> PATCH <narrator_id> <body.json>

Prints {"status": int, "body": ...}.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

import io, contextlib  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):   # db import chatter must not corrupt the reply
    from api import db as _db  # noqa: E402
    from api.services.life_record import writer as W  # noqa: E402


def main():
    db_path, method, pid = sys.argv[1], sys.argv[2], sys.argv[3]
    _db.DB_PATH = Path(db_path)
    with contextlib.redirect_stdout(io.StringIO()):
        exists = _db.get_person(pid)
        if not exists:
            out = {"status": 404, "body": {"detail": "Narrator not found"}}
        elif method == "GET":
            out = {"status": 200, "body": W.read_record(pid)}
        elif method == "PATCH":
            body = json.loads(Path(sys.argv[4]).read_text())
            r = W.apply_changes(pid, body.get("baseRevision"), body.get("changes") or [], body.get("actor"))
            out = ({"status": 200, "body": r} if r.get("ok") else
                   {"status": 409 if "conflict" in r else 422, "body": {"detail": r}})
        else:
            out = {"status": 405, "body": {"detail": method}}
    sys.stdout.write(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
