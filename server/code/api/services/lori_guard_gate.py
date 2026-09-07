"""Decide whether an experimental Guard Lab configuration may govern a turn.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, sections G/H/I.

`lori_guard_registry` says what the 43 authorities are, `lori_guard_store`
persists operator overrides, `lori_guard_authority` resolves them into an
immutable snapshot. This module answers the question that has to be
settled BEFORE any of that is allowed to matter:

    is this particular turn, for this particular narrator, permitted to
    run a configuration somebody is experimenting with?

FAIL-CLOSED, EVERYWHERE, WITHOUT EXCEPTION. Every uncertain answer is
"no, use canonical production". The asymmetry is not stylistic: the cost
of a false negative is an experiment that quietly refuses to apply and
gets noticed in the trace; the cost of a false positive is an older
adult with possible cognitive decline talking to a deliberately degraded
Lori, in a system whose north star is narrator dignity.

FOUR CONDITIONS, ALL REQUIRED

  1. a person id resolves to a real person
  2. that person is durably `testing_only`
  3. an evaluation is armed, by the same marker the shell uses
  4. the response trace is actually recording

The fourth is the one that is easy to leave out and worth stating
plainly. `trace_env.sh` resolves the marker into `HORNELORE_RESPONSE_TRACE`
only when a process is STARTED, so a marker can appear while the API is
already running and tracing stays off. An experimental turn that nobody
recorded is worse than no experiment at all — it changes what a narrator
receives and produces no evidence to judge it by, which is precisely the
situation the Walt/John diagnostic existed to escape. So an armed marker
without tracing is refused, loudly, with its own reason.

WHAT THIS MODULE MAY NOT DO. It reads server-side state only: the
people table, the marker file, the trace module, the override store. It
never consults `runtime71`, request `params`, or anything else a browser
can set. A client cannot nominate itself for an experiment.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import lori_guard_authority as authority
from . import lori_guard_store as store

logger = logging.getLogger(__name__)


# ── Gate outcomes ─────────────────────────────────────────────────────

GATE_EXPERIMENT_APPLIED = "experiment_applied"
"""All four conditions met. Operator overrides govern this turn."""

GATE_NO_PERSON = "no_person"
"""No person id, or it does not resolve. Canonical production."""

GATE_NOT_TESTING_ONLY = "not_testing_only"
"""A real narrator. Experiments never reach them, whatever is armed."""

GATE_NO_EVAL_MARKER = "no_eval_marker"
"""No evaluation is armed. This is the ordinary resting state."""

GATE_TRACE_NOT_ENABLED = "trace_not_enabled"
"""Armed, but nothing is recording. Refused rather than run blind."""

GATE_STORE_UNAVAILABLE = "store_unavailable"
"""The override store could not be read. Canonical production."""

VALID_GATE_REASONS = frozenset({
    GATE_EXPERIMENT_APPLIED, GATE_NO_PERSON, GATE_NOT_TESTING_ONLY,
    GATE_NO_EVAL_MARKER, GATE_TRACE_NOT_ENABLED, GATE_STORE_UNAVAILABLE,
})


# ── The evaluation marker ─────────────────────────────────────────────
#
# Mirrors `scripts/trace_env.sh:hornelore_trace_resolve`, which is the
# authority for this file's meaning:
#
#     marker="$repo_root/.runtime/eval/current_eval_dir"
#     if [ -r "$marker" ]; then eval_dir="$(<"$marker")"; fi
#
# `$(<file)` strips trailing newlines, and the shell's own comment says
# "A blank or deleted marker must not resolve to the repo root". Same
# three rules here: unreadable is unarmed, blank is unarmed, trailing
# whitespace is not part of the path.
#
# Deliberately NOT a second convention. The marker is written when an
# experiment starts and removed by `stop_all.sh` when it ends; that
# self-limiting property is the reason experiments cannot silently
# outlive their run, and a Python-side variant with different rules
# would quietly break it.

_MARKER_RELATIVE = Path(".runtime") / "eval" / "current_eval_dir"


def _repo_root() -> Path:
    """server/code/api/services/ -> repo root."""
    return Path(__file__).resolve().parents[4]


def eval_marker_path(repo_root: Optional[Path] = None) -> Path:
    return (Path(repo_root) if repo_root else _repo_root()) / _MARKER_RELATIVE


def armed_eval_dir(repo_root: Optional[Path] = None) -> Optional[str]:
    """The armed run directory, or None when no evaluation is armed."""
    marker = eval_marker_path(repo_root)
    try:
        if not marker.is_file() or not os.access(marker, os.R_OK):
            return None
        raw = marker.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        # Unreadable is unarmed. A permissions problem or a half-written
        # marker must not arm an experiment.
        logger.warning(
            "[guard-lab][gate] eval marker unreadable at %s (%s) — "
            "treating as unarmed", marker, exc)
        return None
    value = raw.strip()
    return value or None


def experiment_is_armed(repo_root: Optional[Path] = None) -> bool:
    return armed_eval_dir(repo_root) is not None


# ── Acquisition ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class TurnAuthorityAcquisition:
    """One turn's authority decision, taken once and never revisited.

    `snapshot` always exists — canonical production when the gate is
    closed — so no consumer ever has to handle "no configuration". The
    difference is visible in `experiment_applied` and `gate_reason`,
    which are what the trace records so a transcript can say not only
    which configuration ran but why it was allowed to.
    """

    snapshot: authority.AuthoritySnapshot
    gate_reason: str
    experiment_applied: bool
    eval_dir: Optional[str] = None

    def trace_identity(self) -> dict:
        identity = dict(self.snapshot.trace_identity())
        identity["gate_reason"] = self.gate_reason
        identity["experiment_applied"] = self.experiment_applied
        if self.eval_dir:
            identity["eval_dir"] = self.eval_dir
        return identity

    def log_line(self) -> str:
        return (
            "[guard-lab][gate] experiment_applied=%s reason=%s revision=%s "
            "selected=%d excluded=%d registry=%s selection=%s" % (
                self.experiment_applied, self.gate_reason,
                self.snapshot.revision,
                len(self.snapshot.selected), len(self.snapshot.excluded),
                self.snapshot.registry_fingerprint[:12],
                self.snapshot.selection_fingerprint[:12],
            )
        )


def canonical_acquisition(
        reason: str = GATE_STORE_UNAVAILABLE,
        revision: int = 0) -> TurnAuthorityAcquisition:
    """Production defaults, with a reason.

    PUBLIC so the router has exactly one door to this subsystem. Its
    fail-closed fallback needs a canonical acquisition when acquisition
    itself raises, and importing `lori_guard_authority` to build one
    would give the response path a second way to obtain a
    configuration — which is how a turn ends up half on one revision and
    half on another.
    """
    return TurnAuthorityAcquisition(
        snapshot=authority.canonical_defaults_snapshot(revision=revision),
        gate_reason=reason,
        experiment_applied=False,
    )


def _canonical(reason: str, revision: int = 0) -> TurnAuthorityAcquisition:
    return canonical_acquisition(reason, revision)


def acquire_turn_authority(
    person_id: Optional[str],
    *,
    connection_factory: Optional[Callable[[], object]] = None,
    testing_only_probe: Optional[Callable[[Optional[str]], bool]] = None,
    trace_enabled_probe: Optional[Callable[[], bool]] = None,
    repo_root: Optional[Path] = None,
) -> TurnAuthorityAcquisition:
    """Resolve this turn's authority exactly once.

    Called near the top of the turn, before any registered authority can
    act — before witness detection, before the browser's proposed
    `turn_mode` is consulted, before a prompt is composed. Everything
    downstream reads the returned snapshot and nothing else.

    Every probe is injectable so the whole decision table can be tested
    without a database, a marker file or an environment.
    """
    # 1. A person, or nothing doing.
    if not person_id or not str(person_id).strip():
        return _canonical(GATE_NO_PERSON)

    # 2. Durably testing-only. Not a request field, not profile
    #    biography — a people-table column, resolved fail-closed.
    if testing_only_probe is None:
        from .. import db as _db
        testing_only_probe = _db.person_is_testing_only
    try:
        is_testing = bool(testing_only_probe(person_id))
    except Exception:
        logger.exception(
            "[guard-lab][gate] testing_only probe failed for %r — "
            "canonical production", person_id)
        return _canonical(GATE_NO_PERSON)
    if not is_testing:
        return _canonical(GATE_NOT_TESTING_ONLY)

    # 3. An armed evaluation, by the shell's own marker.
    eval_dir = armed_eval_dir(repo_root)
    if not eval_dir:
        return _canonical(GATE_NO_EVAL_MARKER)

    # 4. Something is recording. An unmeasured experimental turn changes
    #    what a narrator receives and produces no evidence to judge it
    #    by — the exact situation the Walt/John diagnostic existed to
    #    escape.
    if trace_enabled_probe is None:
        from . import lori_response_trace as _rt
        trace_enabled_probe = _rt.enabled
    try:
        recording = bool(trace_enabled_probe())
    except Exception:
        recording = False
    if not recording:
        logger.warning(
            "[guard-lab][gate] evaluation armed at %s but the response "
            "trace is NOT enabled — refusing the experimental "
            "configuration and running canonical Lori. The marker only "
            "resolves into HORNELORE_RESPONSE_TRACE when a process "
            "starts, so arming mid-run leaves tracing off.", eval_dir)
        return _canonical(GATE_TRACE_NOT_ENABLED)

    # All four met. One coherent read of the store, one resolution.
    try:
        if connection_factory is None:
            from .. import db as _db
            connection_factory = _db._connect
        con = connection_factory()
    except Exception:
        logger.exception(
            "[guard-lab][gate] could not open the override store — "
            "canonical production")
        return _canonical(GATE_STORE_UNAVAILABLE)

    try:
        overrides, revision = store.read_state(con)
    except Exception:
        logger.exception(
            "[guard-lab][gate] override store unreadable — canonical "
            "production")
        return _canonical(GATE_STORE_UNAVAILABLE)
    finally:
        try:
            con.close()
        except Exception:
            pass

    return TurnAuthorityAcquisition(
        snapshot=authority.resolve(overrides, revision=revision),
        gate_reason=GATE_EXPERIMENT_APPLIED,
        experiment_applied=True,
        eval_dir=eval_dir,
    )
