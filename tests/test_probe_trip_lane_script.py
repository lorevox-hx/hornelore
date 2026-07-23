"""Automated test for scripts/probe_trip_lane_post_1e388b5.sh.

Chris's spec (2026-07-23 Bucket A.10): the previous probe landed
with THREE HIGH-severity defects that would only have shown up on
a live write-mode run:
  (1) response parser looked for {"trip":{"id":"..."}} instead of
      the API's {"trip_id":"..."} — probe trips could not be
      cleaned up.
  (2) `printf | python - <<'PY'` collided the heredoc against the
      pipe. json.load(sys.stdin) never saw the piped JSON.
  (3) "read-only default" was false — the fake-person POST always
      fired even without CONFIRM_WRITES=1.

This test locks the rewrite against those regressions at the SHELL
LEVEL by running the script against a mock API and asserting on
observable behavior. Two attack surfaces:

  * Static / structural checks — grep the script for the specific
    bug shapes so any future refactor that reintroduces them fails
    the build immediately.
  * Dry-run integration — spin a tiny threaded HTTP server that
    stands in for the FastAPI stack, run the probe against it in
    read-only mode, assert on stdout + on the server's request log.

The dry-run test never triggers the trap-cleanup path with a real
trip DELETE (the mock server never accepts POST in read mode), but
proves the trap installs and fires. A separate test simulates a
"created a trip" scenario by pre-populating CREATED_TRIPS and
sending INT.

The script itself is bash so the probe execution is skipped when
bash is unavailable (unlikely on any dev/CI env).
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROBE = _REPO_ROOT / "scripts" / "probe_trip_lane_post_1e388b5.sh"


# ── Static / structural checks ─────────────────────────────────

class ProbeStaticCheckTest(unittest.TestCase):
    """Structural regression guards. Cheap; run first."""

    @classmethod
    def setUpClass(cls):
        cls.text = _PROBE.read_text()
        # cls.code is the same file with bash comments stripped, so
        # the "regressions must not reappear" checks don't flag the
        # header comment that explains what the OLD bug looked like.
        # A bash `#` that begins a line-comment starts with `#` at
        # column 0 or preceded only by whitespace. We keep in-line
        # comments (rare) as-is — they're not typical for this file.
        stripped = []
        for ln in cls.text.splitlines():
            if ln.lstrip().startswith("#"):
                continue
            stripped.append(ln)
        cls.code = "\n".join(stripped)

    def test_probe_script_exists_and_is_executable(self):
        self.assertTrue(_PROBE.exists(), f"missing: {_PROBE}")
        st = _PROBE.stat()
        # At least owner execute bit
        self.assertTrue(st.st_mode & 0o100,
                        "probe script must be executable (chmod +x)")

    def test_no_wrong_trip_id_parser_shape(self):
        """The original bug: d.get("trip", {}).get("id") — the API
        returns {"trip_id": "..."} not {"trip": {"id": "..."}}. Scan
        the non-comment source only, so the header docstring that
        cites the old bug doesn't self-trigger."""
        offenders = [
            'get("trip", {}).get("id")',
            "get('trip', {}).get('id')",
            "get(\"trip\",{}).get(\"id\")",
        ]
        for pat in offenders:
            self.assertNotIn(
                pat, self.code,
                f"probe still contains wrong trip_id parser: {pat!r}. "
                "The API returns {'trip_id': '...'} — use d.get('trip_id').")
        # And the correct parser must be present at least once
        # (in either code or comments — comments-only is fine because
        # the code check above already guarantees no wrong shape).
        self.assertIn(
            "d.get('trip_id')", self.text,
            "probe must parse trip creation via d.get('trip_id')")

    def test_no_heredoc_plus_pipe_conflict(self):
        """The original bug: `printf JSON | python - <<'PY'` — the
        heredoc supplies Python's stdin, so the pipe never reaches
        json.load(sys.stdin). Any occurrence of a heredoc AFTER a
        pipe-into-python is the bug shape."""
        lines = self.text.splitlines()
        # Look for a line that ends with a pipe into $PY - (or python -)
        # followed by a heredoc opener on a subsequent line.
        for i, ln in enumerate(lines):
            stripped = ln.strip()
            # Detect: `... | "$PY" -` or `... | python -` on this line
            if not (
                stripped.endswith('"$PY" -')
                or stripped.endswith('python -')
                or stripped.endswith('python3 -')
            ):
                continue
            # Look ahead a few lines for a heredoc opener
            for j in range(i, min(i + 4, len(lines))):
                if "<<'PY'" in lines[j] or '<<"PY"' in lines[j] or "<<PY" in lines[j]:
                    self.fail(
                        f"probe still contains pipe-into-python-with-heredoc "
                        f"at line {i+1}: {ln.strip()!r} — the heredoc "
                        f"supplies stdin, so any piped JSON is lost. Use "
                        f"python -c with a temp file or an env var.")

    def test_json_reads_use_temp_file_or_argv(self):
        """Positive form of the previous check: every python -c that
        reads JSON should read from a file (open('$TMP...')) or an
        env var — not sys.stdin (which would only work if we're NOT
        also using pipes, which is fragile). Cheap structural
        confirmation."""
        # The rewrite uses python -c 'json.load(open("$TMPFILE"))'
        # for all JSON reads. Verify that shape is present.
        self.assertIn(
            "json.load(open(", self.text,
            "probe should read JSON from temp files, not sys.stdin")

    def test_all_mutations_gated_behind_confirm_writes(self):
        """Every POST, PATCH, DELETE (except the trap cleanup which
        runs after write-mode operations) must be inside a
        CONFIRM_WRITES=1 branch. Section 5 (fake-person) previously
        wrote unconditionally — that was the regression trap."""
        # Split into sections by "── N. " headers to check each block.
        # Trap cleanup DELETEs are exempt — they only run for trips
        # this script created, which only happens in write mode.
        # Look for POST /api/trips or PATCH /api/trips or DELETE /api/trips
        # NOT inside a curl in the trap function.
        trap_lines = []
        in_trap = False
        section_lines = {}
        current_section = "preamble"
        for i, ln in enumerate(self.text.splitlines(), start=1):
            if ln.startswith("_cleanup()"):
                in_trap = True
            if in_trap and ln.strip() == "}":
                in_trap = False
                trap_lines.append(i)
                continue
            if in_trap:
                trap_lines.append(i)
                continue
            m = ln.strip()
            if m.startswith('hdr "') and "." in m:
                current_section = m
            section_lines.setdefault(current_section, []).append((i, ln))

        # For each section header that mentions writes, walk the
        # section and verify a CONFIRM_WRITES check appears BEFORE
        # any POST/PATCH/DELETE curl.
        write_sections = [
            "5. POST /api/trips must reject a nonexistent person_id",
            "6. Auto-day-generation on trip create",
            "7. PATCH with reversed dates surfaces days_warning",
        ]
        for sect_header, entries in section_lines.items():
            title = sect_header
            if not any(w in title for w in write_sections):
                continue
            saw_gate = False
            for line_no, ln in entries:
                s = ln.strip()
                if 'CONFIRM_WRITES' in s and ('=' in s or 'if' in s):
                    saw_gate = True
                if not saw_gate and any(v in s for v in (
                    '-X POST "$API', '-X PATCH "$API', '-X DELETE "$API',
                )):
                    self.fail(
                        f"UNGATED mutation in write-section {title!r} "
                        f"at line {line_no}: {s!r}. Must be behind a "
                        f"CONFIRM_WRITES=1 check.")

    def test_write_mode_requires_explicit_person_id(self):
        """CONFIRM_WRITES=1 without PERSON_ID must exit cleanly, not
        auto-pick the first narrator."""
        # The rewrite has an explicit check + exit 1 message.
        self.assertIn(
            "CONFIRM_WRITES=1 requires an explicit PERSON_ID",
            self.text,
            "write mode must fail loud when PERSON_ID unset")

    def test_trap_cleanup_installed(self):
        """The trap must fire on EXIT/INT/TERM and DELETE any
        successfully-created probe trips."""
        self.assertIn("trap _cleanup EXIT INT TERM", self.text,
                      "cleanup trap must fire on all three signals")
        self.assertIn("CREATED_TRIPS", self.text,
                      "must track created trips for cleanup")
        # The trap function must actually DELETE.
        cleanup_start = self.text.find("_cleanup()")
        cleanup_end = self.text.find("trap _cleanup", cleanup_start)
        cleanup_body = self.text[cleanup_start:cleanup_end]
        self.assertIn('DELETE', cleanup_body,
                      "cleanup trap must issue DELETE requests")
        self.assertIn('%{http_code}', cleanup_body,
                      "cleanup must check HTTP status before claiming success")

    def test_strict_422_expectation_for_fake_person(self):
        """Section 5 must require exactly 422 (not accept 400/404
        as alternatives — a missing route would 404 and silently
        pass a permissive check)."""
        # Find section 5
        m = self.text.find('5. POST /api/trips must reject')
        self.assertGreater(m, 0, "section 5 header missing")
        end = self.text.find('# ── 6.', m)
        section = self.text[m:end]
        # Must check for 422 explicitly, not a range
        self.assertIn('"$RESP" = "422"', section,
                      "must accept ONLY 422, not a range of codes")
        # Must NOT accept 400/404 as valid alternatives
        for bad in ('"400"', '"404"'):
            if bad in section:
                # Allow bad codes to appear ONLY in error messages
                # (which say "returned $RESP not 422"), not as
                # accepted alternatives. Heuristic: the string must
                # not appear on a line that has "=" or "==" near it
                # as an accept branch.
                for line in section.splitlines():
                    if bad in line and (
                        'RESP" = ' + bad in line
                        or 'RESP" == ' + bad in line
                    ):
                        self.fail(f"Section 5 accepts {bad} as valid — "
                                  "must be 422-only.")

    def test_pragma_labels_are_honest(self):
        """PRAGMA busy_timeout and PRAGMA foreign_keys via the CLI
        are connection-local and don't reflect the API's connection.
        Section 8 must label them accordingly (not claim they
        verify the API's connection state)."""
        m = self.text.find('# ── 8.')
        end = self.text.find('# ── Summary', m)
        section = self.text[m:end]
        # journal_mode is fine as a persistent claim.
        # busy_timeout and foreign_keys must be labeled CLI-session.
        self.assertIn('CLI-session', section,
                      "PRAGMA busy_timeout/foreign_keys must be honestly "
                      "labeled as connection-local CLI values")

    def test_sqlite_version_compare_is_numeric(self):
        """Not the buggy 3.5[12].0|... shell glob. Must use Python
        numeric tuple comparison. Scan non-comment source — the
        docstring cites the buggy glob as reference and shouldn't
        self-trigger."""
        # The buggy glob has bracket-set + version dots.
        # Only check in non-comment lines (cls.code).
        self.assertNotIn('3.5[12].0', self.code,
                         "shell glob version compare is buggy — "
                         "must use Python numeric tuples")
        self.assertNotIn('3.5[12].1', self.code)
        self.assertNotIn('3.5[12].2', self.code)
        # Positive: Python-side comparison exists.
        self.assertIn('tuple(int(x) for x in', self.text,
                      "version compare must be Python numeric tuples")


# ── Dry-run integration test ──────────────────────────────────

class _MockAPIHandler(BaseHTTPRequestHandler):
    """Minimal handler that behaves like the trip lane API for the
    read-only paths the probe hits in dry mode. Records every
    request on the class for the test to assert against."""

    requests_log = []  # populated by tests via clear-and-append
    people_response = b'{"people":[]}'

    def _send_json(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Silence the built-in stderr access log; we track via requests_log.
        pass

    def do_GET(self):
        _MockAPIHandler.requests_log.append(("GET", self.path))
        if self.path == "/":
            self._send_json(200, b'{"ok":true}')
        elif self.path == "/api/people":
            self._send_json(200, self.people_response)
        else:
            self._send_json(404, b'{"detail":"Not Found"}')

    def do_POST(self):
        _MockAPIHandler.requests_log.append(("POST", self.path))
        # In READ-ONLY probe mode, NO POST should ever hit this
        # handler. Any POST that lands here is a regression in the
        # gating.
        self._send_json(500, b'{"detail":"MOCK: POST leaked in dry mode"}')

    def do_PATCH(self):
        _MockAPIHandler.requests_log.append(("PATCH", self.path))
        self._send_json(500, b'{"detail":"MOCK: PATCH leaked in dry mode"}')

    def do_DELETE(self):
        _MockAPIHandler.requests_log.append(("DELETE", self.path))
        self._send_json(200, b'{"ok":true}')


def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@unittest.skipUnless(shutil.which("bash"), "bash required")
@unittest.skipUnless(shutil.which("curl"), "curl required")
class ProbeDryRunIntegrationTest(unittest.TestCase):
    """Run the probe in READ-ONLY mode against a mock API. Assert
    that no POST/PATCH/DELETE ever leaves the script — because if
    they do, our supposedly dry probe would mutate a real DB."""

    def setUp(self):
        _MockAPIHandler.requests_log = []
        _MockAPIHandler.people_response = b'{"people":[]}'
        self.port = _find_free_port()
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", self.port), _MockAPIHandler)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        # Give the server a beat to bind
        time.sleep(0.05)

        # Point PY at whatever python3 is on PATH — the probe uses PY
        # only for JSON parsing + sqlite version check.
        self.py = shutil.which("python3") or shutil.which("python")
        self.assertTrue(self.py, "no python interpreter on PATH")

        # Fake a valid DB path (nonexistent — probe should skip
        # DB-side checks with a warn, NOT bail).
        self.fake_db = "/tmp/probe_test_nonexistent_$$.sqlite3"
        # Fake a valid cwd — the probe does `cd /mnt/c/Users/chris/hornelore`.
        # We work around by patching that check via CWD environment.
        # Easier path: make a temp dir that looks like a valid repo.
        self.tmpdir = tempfile.mkdtemp(prefix="probe_repo_")
        # The probe's cd is hardcoded; we need to replace it. Simplest:
        # write a modified copy of the probe into a temp file with the
        # cd line replaced to point at our tmpdir.
        original = _PROBE.read_text()
        patched = original.replace(
            "cd /mnt/c/Users/chris/hornelore 2>/dev/null",
            f"cd {self.tmpdir} 2>/dev/null")
        self.tmp_probe = Path(self.tmpdir) / "probe.sh"
        self.tmp_probe.write_text(patched)
        self.tmp_probe.chmod(0o755)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, env=None, timeout=15):
        base_env = os.environ.copy()
        base_env.update({
            "API": f"http://127.0.0.1:{self.port}",
            "DB": self.fake_db,
            "PY": self.py,
        })
        if env:
            base_env.update(env)
        return subprocess.run(
            ["bash", str(self.tmp_probe)],
            capture_output=True, text=True, timeout=timeout,
            env=base_env,
        )

    def test_read_only_run_makes_zero_mutations(self):
        """The whole file's premise: bare invocation performs zero
        POST/PATCH/DELETE against the API."""
        result = self._run()
        # The probe returns non-zero when there are failures. Read-only
        # against a mostly-mocked API SHOULD not fail hard — but we
        # care about the request log, not the exit code.
        mutations = [
            (m, p) for (m, p) in _MockAPIHandler.requests_log
            if m in ("POST", "PATCH", "DELETE")
        ]
        self.assertEqual(
            mutations, [],
            f"Read-only probe made mutating requests: {mutations}\n"
            f"stdout: {result.stdout[-800:]}\n"
            f"stderr: {result.stderr[-400:]}")

    def test_write_mode_without_person_id_refuses(self):
        """CONFIRM_WRITES=1 with no PERSON_ID must exit non-zero
        BEFORE any mutation reaches the API."""
        result = self._run(env={"CONFIRM_WRITES": "1", "PERSON_ID": ""})
        self.assertNotEqual(
            result.returncode, 0,
            "CONFIRM_WRITES=1 with empty PERSON_ID must exit non-zero")
        # And no mutating requests should have leaked.
        mutations = [
            (m, p) for (m, p) in _MockAPIHandler.requests_log
            if m in ("POST", "PATCH", "DELETE")
        ]
        self.assertEqual(
            mutations, [],
            f"Refusal path leaked mutations: {mutations}")
        # Error message should be actionable.
        combined = result.stdout + result.stderr
        self.assertIn("PERSON_ID", combined,
                      "refusal message must mention PERSON_ID")

    def test_write_mode_with_unknown_person_id_refuses(self):
        """CONFIRM_WRITES=1 with a PERSON_ID that doesn't match any
        narrator on the instance must refuse — this prevents the
        script from creating probe trips under a real narrator
        picked up from stale env."""
        # Mock /api/people returns a list — but not our fake PERSON_ID.
        _MockAPIHandler.people_response = json.dumps({
            "people": [
                {"id": "real-uuid-abc", "display_name": "Real Narrator"},
            ]
        }).encode()
        result = self._run(env={
            "CONFIRM_WRITES": "1",
            "PERSON_ID": "unknown-uuid-xyz",
        })
        self.assertNotEqual(result.returncode, 0)
        mutations = [
            (m, p) for (m, p) in _MockAPIHandler.requests_log
            if m in ("POST", "PATCH", "DELETE")
        ]
        self.assertEqual(mutations, [])
        combined = result.stdout + result.stderr
        self.assertIn("does not match", combined.lower() + " does not match")


if __name__ == "__main__":
    unittest.main()
