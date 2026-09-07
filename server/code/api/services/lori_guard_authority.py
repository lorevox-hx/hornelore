"""Resolve what the next narrator turn will actually receive.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, sections D and E.

`lori_guard_registry` says what the 43 authorities ARE. This module says
what they are DOING right now, which is a different question and needs
three pieces of state rather than one flag:

    canonical default   what the registry defines with no override
    operator override   what the operator deliberately selected
    effective state     what this turn actually gets, after protected
                        and system state are applied — with a reason

Collapsing those into one ON/OFF label produces a panel that lies. The
clearest case is authority 2, the acute safety protocol: it is
canonically ON, the operator can never override it, and
`flags.safety_parked()` defaults to parked — so the truthful row reads

    Acute Safety Protocol — PROTECTED — canonical ON — effective PARKED

and a panel showing a green "ON" toggle would be wrong three ways at
once.

THREE IDENTIFIERS, NOT ONE HASH. A turn is attributable to
`registry_fingerprint + revision + selection_fingerprint`, and each
answers a question the others cannot:

    registry_fingerprint   which authority MAP was this code using?
    revision               which persisted configuration generation?
    selection_fingerprint  which effective selection did the turn use?

The registry fingerprint deliberately covers behavioural fields ONLY.
Editing a `known_harm` paragraph must not make it look like the
behaviour contract moved, or the fingerprint stops meaning anything and
every transcript comparison becomes noise.

THIS MODULE IS PURE. No database, no environment reads of its own, no
global mutable state. Persistence (section F) supplies overrides and the
revision; the system-state probe is injected. That is what makes a
snapshot reproducible after the fact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, Mapping, Optional, Tuple

from . import lori_guard_registry as registry


# ── Effective-state reasons ───────────────────────────────────────────

REASON_CANONICAL_DEFAULT = "canonical_default"
"""No override; the registry's canonical default applies."""

REASON_OPERATOR_OVERRIDE = "operator_override"
"""An operator deliberately selected this state."""

REASON_PROTECTED = "protected"
"""Safety, provenance, floor ownership, fail-closed or memory integrity.
Any override is refused, not silently honoured."""

REASON_PENDING_SEAM = "pending_seam"
"""Would be switchable; not yet separable in code. `All Switchable Off`
leaves it RUNNING, and the panel must say so rather than implying it was
turned off."""

REASON_SYSTEM_PARKED = "system_parked"
"""A separate server-authoritative feature state overrides both the
canonical default and any operator intent. The parked safety family is
the live example."""

VALID_REASONS = frozenset({
    REASON_CANONICAL_DEFAULT, REASON_OPERATOR_OVERRIDE, REASON_PROTECTED,
    REASON_PENDING_SEAM, REASON_SYSTEM_PARKED,
})


# ── Fingerprints ──────────────────────────────────────────────────────
#
# The behavioural contract. Anything NOT in this tuple is documentation
# and must not move the fingerprint: `purpose`, `motivating_failure`,
# `known_harm`, `policy_reason`, `location`, `display`, `tests`.
_BEHAVIOURAL_FIELDS: Tuple[str, ...] = (
    "id", "name", "cls", "position", "policy", "default_on",
    "counterfactual",
)


def registry_fingerprint(entries=None) -> str:
    """Identify the authority map, not the prose describing it.

    `entries` is injectable so a test can fingerprint a deliberately
    prose-edited copy of the registry and prove the digest did not move.
    Patching the module global would have proven the same thing far more
    fragilely.
    """
    payload = [
        [getattr(item, field) for field in _BEHAVIOURAL_FIELDS]
        for item in sorted(entries or registry.REGISTRY, key=lambda i: i.id)
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def selection_fingerprint(selected_ids) -> str:
    """Identify an effective selection, independent of how it was typed.

    `{33, 40}` and `{40, 33}` are the same experiment and must hash the
    same; two genuinely different selections must not collide.
    """
    canonical = sorted(set(int(i) for i in selected_ids))
    blob = json.dumps(canonical, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ── Resolved state ────────────────────────────────────────────────────

@dataclass(frozen=True)
class AuthorityState:
    """One authority's three-part truth for one turn."""

    id: int
    name: str
    display: str
    cls: str
    policy: str
    position: int
    counterfactual: str
    canonical_default: bool
    operator_override: Optional[bool]   # None when unset
    effective: bool
    reason: str

    @property
    def differs_from_canonical(self) -> bool:
        """Whether the panel must show an explanation on this row."""
        return self.effective != self.canonical_default


@dataclass(frozen=True)
class AuthoritySnapshot:
    """One immutable configuration, resolved once and threaded whole.

    A turn takes exactly one of these before the first authority can
    act, and keeps it to the end. An operator toggling a switch while
    Lori is mid-sentence changes the NEXT turn — never this one — so a
    transcript can always be attributed to a configuration that actually
    existed.
    """

    registry_fingerprint: str
    revision: int
    selection_fingerprint: str
    states: Tuple[AuthorityState, ...]
    selected: FrozenSet[int]
    excluded: FrozenSet[int]

    def is_selected(self, intervention_id: int) -> bool:
        """The single question every runtime consumer asks."""
        return intervention_id in self.selected

    def state(self, intervention_id: int) -> Optional[AuthorityState]:
        for item in self.states:
            if item.id == intervention_id:
                return item
        return None

    def overrides(self) -> Dict[int, bool]:
        return {s.id: s.operator_override for s in self.states
                if s.operator_override is not None}

    def trace_identity(self) -> Dict[str, object]:
        """What every traced turn carries.

        Three identifiers plus both sides of the selection, so a
        transcript can never be separated from the configuration that
        produced it.
        """
        return {
            "registry_fingerprint": self.registry_fingerprint,
            "revision": self.revision,
            "selection_fingerprint": self.selection_fingerprint,
            "selected": sorted(self.selected),
            "excluded": sorted(self.excluded),
        }


# ── Resolution ────────────────────────────────────────────────────────

def _system_state_reason(item, safety_parked: bool) -> Optional[str]:
    """A server-authoritative feature state that outranks everything.

    Currently only the parked safety family. Returning a reason here
    means neither the canonical default nor an operator override decides
    this row.
    """
    if safety_parked and item.name in ("prompt_safety_protocol",
                                       "cc_safety_path"):
        return REASON_SYSTEM_PARKED
    return None


def resolve(
    overrides: Optional[Mapping[int, bool]] = None,
    *,
    revision: int = 0,
    safety_parked_probe: Optional[Callable[[], bool]] = None,
) -> AuthoritySnapshot:
    """Produce the immutable snapshot for a turn.

    `overrides` comes from persistence (section F) and contains ONLY
    deliberately overridden authorities — an absent id means "no
    override", which is not the same as "overridden to the default".
    Resetting an authority deletes its row rather than writing the
    default in, so the canonical default stays live in code.

    `safety_parked_probe` is injected rather than imported so this stays
    pure and a test can resolve both states without touching the
    environment.
    """
    overrides = dict(overrides or {})
    if safety_parked_probe is None:
        from .. import flags as _flags
        safety_parked_probe = _flags.safety_parked
    parked = bool(safety_parked_probe())

    states = []
    for item in registry.in_pipeline_order():
        override = overrides.get(item.id)

        system_reason = _system_state_reason(item, parked)
        if system_reason is not None:
            effective, reason = False, system_reason
        elif item.policy == registry.POLICY_PROTECTED:
            # An override on a protected authority is refused, never
            # quietly applied. The API rejects it too; this is the
            # second line of defence.
            effective, reason = item.default_on, REASON_PROTECTED
        elif item.policy == registry.POLICY_PENDING_SEAM:
            effective, reason = item.default_on, REASON_PENDING_SEAM
        elif override is not None:
            effective, reason = bool(override), REASON_OPERATOR_OVERRIDE
        else:
            effective, reason = item.default_on, REASON_CANONICAL_DEFAULT

        states.append(AuthorityState(
            id=item.id,
            name=item.name,
            display=item.display,
            cls=item.cls,
            policy=item.policy,
            position=item.position,
            counterfactual=item.counterfactual,
            canonical_default=item.default_on,
            operator_override=override,
            effective=effective,
            reason=reason,
        ))

    selected = frozenset(s.id for s in states if s.effective)
    excluded = frozenset(s.id for s in states if not s.effective)
    return AuthoritySnapshot(
        registry_fingerprint=registry_fingerprint(),
        revision=int(revision),
        selection_fingerprint=selection_fingerprint(selected),
        states=tuple(states),
        selected=selected,
        excluded=excluded,
    )


def all_switchable_off_overrides() -> Dict[int, bool]:
    """The override map for the lean baseline.

    Only SWITCHABLE authorities appear. PROTECTED rows are governed by
    their protected state, and a PENDING_SEAM row would stay RUNNING —
    which is exactly why that population has to be empty before the
    preset can be described as `All Switchable Off` without qualification.
    """
    return {item.id: False for item in registry.switchable()}


def canonical_defaults_snapshot(**kwargs) -> AuthoritySnapshot:
    """Production: no overrides at all."""
    return resolve({}, **kwargs)
