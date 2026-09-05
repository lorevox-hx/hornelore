"""Run source mutations with a restore that cannot be skipped.

`WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 5B item 8.

── WHY THIS EXISTS ───────────────────────────────────────────────────

Mutation batches in this repository have twice left a live mutation in
product source. Once during the Profile Seed lane — three interrupted
runs, one of which disabled a version-conflict guard in `db.py` with no
journal entry — and again during Phase 5B, when a batch hit the agent's
command timeout mid-run and left `extract.py` mutated.

Both times the mutation was found by a checksum afterwards rather than
prevented, and the second time the tree was reported clean before the
checksum was read.

**The restore must not depend on the runner finishing.** `finally` runs
on exception, on `KeyboardInterrupt`, and on `SystemExit`. It does not
run if the process is `SIGKILL`ed, which is why `verify()` exists and
why the pristine digests are written to disk before anything is touched.

── HOW TO USE IT ─────────────────────────────────────────────────────

    from tests.mutation_runner import MutationRunner

    with MutationRunner({"extract": Path("server/.../extract.py")}) as mr:
        mr.mutate("drop the guard", "extract", "if x:", "if False:")
        mr.run(["tests.test_something"])          # restores afterwards
    # sources are byte-identical here, whatever happened above

`verify()` raises if any file differs from its recorded digest, so a run
that was killed outright still fails loudly the next time rather than
silently testing mutated product code.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class MutationNotApplied(RuntimeError):
    """The anchor text was not found, so the mutation proves nothing.

    A mutation that silently fails to apply reports CAUGHT or MISSED on
    unmutated source — which is worse than not running it, because the
    result looks like evidence.
    """


class MutationRunner:
    """Guaranteed-restore mutation harness."""

    def __init__(self, sources: Dict[str, Path], *,
                 pythonpath: str = "server/code",
                 pycache: str = "/tmp/pyc-mutation"):
        self.sources = {k: Path(v) for k, v in sources.items()}
        self.pythonpath = pythonpath
        self.pycache = pycache
        self._backup_dir: Optional[Path] = None
        self._digests: Dict[str, str] = {}
        self.results: List[Tuple[str, str, str]] = []

    # ── lifecycle ────────────────────────────────────────────────────
    def __enter__(self) -> "MutationRunner":
        self._backup_dir = Path(tempfile.mkdtemp(prefix="mutation-backup-"))
        for key, path in self.sources.items():
            shutil.copy2(path, self._backup_dir / key)
            self._digests[key] = self._digest(path)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # ALWAYS restore. Never swallow the exception -- a caller that
        # crashed still needs to see why, it just must not leave mutated
        # product source behind while it does.
        self.restore()
        self.verify()
        return False

    def _digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def restore(self) -> None:
        if not self._backup_dir:
            return
        for key, path in self.sources.items():
            src = self._backup_dir / key
            if src.is_file():
                shutil.copy2(src, path)

    def verify(self) -> None:
        """Raise if any source differs from its pristine digest."""
        drifted = [k for k, p in self.sources.items()
                   if self._digest(p) != self._digests[k]]
        if drifted:
            raise RuntimeError(
                "MUTATED SOURCE SURVIVED THE RUN: "
                + ", ".join(str(self.sources[k]) for k in drifted)
                + f" -- pristine copies are in {self._backup_dir}")

    # ── mutating ─────────────────────────────────────────────────────
    def mutate(self, key: str, old: str, new: str) -> None:
        path = self.sources[key]
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise MutationNotApplied(
                f"anchor not found in {path}: {old[:70]!r}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def run_suites(self, suites: List[str], timeout: int = 300) -> int:
        """Run suites against the CURRENT (possibly mutated) source."""
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", *suites],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONPATH": self.pythonpath,
                 "PYTHONPYCACHEPREFIX": self.pycache})
        return proc.stderr.count("FAIL:") + proc.stderr.count("ERROR:")

    def check(self, label: str, key: str, old: str, new: str,
              suites: List[str], timeout: int = 300) -> str:
        """Apply one mutation, run, restore, and record the verdict."""
        try:
            self.mutate(key, old, new)
        except MutationNotApplied as exc:
            self.results.append((label, "NOT APPLIED", str(exc)[:70]))
            return "NOT APPLIED"
        try:
            failing = self.run_suites(suites, timeout=timeout)
            verdict = "CAUGHT" if failing else "*** MISSED ***"
            self.results.append((label, verdict, f"{failing} failing"))
            return verdict
        finally:
            # Restore after EVERY mutation, not once at the end, so a
            # timeout on the next one cannot compound.
            self.restore()

    def report(self) -> bool:
        width = max((len(r[0]) for r in self.results), default=10)
        for label, verdict, detail in self.results:
            print(f"  {label:<{width}}  {verdict:<14} {detail}")
        missed = [r for r in self.results if r[1] != "CAUGHT"]
        print(f"\n  {len(self.results) - len(missed)}/{len(self.results)} caught")
        return not missed
