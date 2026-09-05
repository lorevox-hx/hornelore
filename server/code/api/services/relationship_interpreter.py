"""One deterministic reading of the narrator's relationship language.

`WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 5B (2026-09-05).

=======================================================================
  THE GOVERNING RULE

    The model proposes an interpretation.
    The NARRATOR'S WORDING decides which relationship lane is legal.
=======================================================================

── WHY THIS MODULE EXISTS ────────────────────────────────────────────

Phase 5B measured the shipped path and found three failures of one
shape, and one that was worse:

  * `daddy` was quarantined `relationship_unstated` while `mama` bound
    normally — the parent vocabulary had `mama` and `papa` but not
    `daddy`;
  * `partner` was quarantined the same way, even though the schema, the
    relation field, the role mapper and the QA bank all support it. All
    of that sits UPSTREAM of the binding decision and never reached it;
  * `ex-wife`, `ex-husband`, `former wife` and `previous wife` all bound
    to the CURRENT spouse field, unquarantined;
  * and a deliberately CROSSED mixed passage — the current wife proposed
    as prior partner, the ex-wife as current spouse — survived untouched.

That last one is the decisive measurement. The old guard could only ask
*"is this person plausibly a spouse?"*. It had no way to ask *"what
relationship did the narrator actually state, and therefore which lane
is legal?"* — so a lookbehind on `ex-` would have stopped one spelling,
left the meaning nowhere to go, and not touched the crossed case at all.

── WHAT THIS RETURNS ─────────────────────────────────────────────────

    group         the destination lane        `family.priorPartners`
    relation      the canonical kind          `wife`
    state         current / former / ""       `former`
    qualifier     older / younger / adult     ""
    source_phrase what the narrator said      `ex-wife`

**`ex-wife` is never a canonical relation.** The relation is `wife`; the
`priorPartners` lane carries the former state; the narrator's own phrase
lives in provenance. Three separate facts, none standing in for another.

── ORDERING IS LOAD-BEARING ──────────────────────────────────────────

Former patterns are matched BEFORE current ones. `-` is a word boundary,
so `\\bwife\\b` matches inside `ex-wife`; testing `ex-wife` first is what
stops that, and it is why this table is ordered rather than a dict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ── The lanes ────────────────────────────────────────────────────────
GROUP_PARENTS = "parents"
GROUP_SPOUSE = "family.spouse"
GROUP_PRIOR_PARTNERS = "family.priorPartners"
GROUP_CHILDREN = "family.children"
GROUP_SIBLINGS = "siblings"
GROUP_GRANDPARENTS = "grandparents"
GROUP_GREAT_GRANDPARENTS = "greatGrandparents"

STATE_CURRENT = "current"
STATE_FORMER = "former"

#: Canonical relations for the spouse/prior-partner lanes. `ex-wife` is
#: NOT here on purpose — it is a phrase, not a relation.
SPOUSE_RELATIONS = ("wife", "husband", "spouse", "partner")


@dataclass(frozen=True)
class RelationshipReading:
    """One relationship the narrator stated, in their own words."""
    group: str
    relation: str
    state: str = ""
    qualifier: str = ""
    source_phrase: str = ""

    @property
    def normalized(self) -> bool:
        """True when the canonical relation differs from what was said.

        `daddy → father` normalized. `father → father` did NOT, and
        claiming otherwise would invent a transformation that never
        happened.
        """
        return self.source_phrase.strip().lower() != self.relation.lower()


# ── `late wife` IS NOT IN THIS TABLE, AND THAT IS THE POINT ──────────
#
# REMOVED 2026-09-05, after review. The first draft grouped
# `late wife|late husband` with `former|previous|first`, which reads as a
# tidy alternation and is a semantic collapse:
#
#   "my ex-wife Susan"    — a marriage that ENDED, and she is living
#   "my late wife Susan"  — a marriage that did NOT end that way, and
#                           she has died
#
# Filing a widower's wife under `priorPartners` — and, downstream,
# `former_marriage` — tells the family the marriage was dissolved. For a
# memoir that is not a mislabelled row; it is the system contradicting
# the narrator about the most significant relationship of their life.
#
# `ex`, `former` and `previous` were MEASURED against the shipped path.
# `late` was not: it was added by pattern-matching on the shape of the
# other words. It stays out until its destination is designed
# deliberately — most likely canonical relation `wife` on the CURRENT
# lane with a death/status marker, not a former-partner lane.
#
# Pinned by `LateSpouseIsNotAFormerSpouse` in
# `tests/test_spouse_state_characterization.py`.

# ── The vocabulary, in ONE place ─────────────────────────────────────
#
# (pattern, group, relation, state, qualifier)
#
# FORMER FORMS COME FIRST. See the ordering note in the module docstring.
_TABLE: Tuple[Tuple[str, str, str, str, str], ...] = (
    # ── former spouse ────────────────────────────────────────────────
    (r"ex[-\s]?wife", GROUP_PRIOR_PARTNERS, "wife", STATE_FORMER, ""),
    (r"ex[-\s]?husband", GROUP_PRIOR_PARTNERS, "husband", STATE_FORMER, ""),
    (r"ex[-\s]?spouse", GROUP_PRIOR_PARTNERS, "spouse", STATE_FORMER, ""),
    (r"ex[-\s]?partner", GROUP_PRIOR_PARTNERS, "partner", STATE_FORMER, ""),
    # `late` is DELIBERATELY ABSENT here. See the note below.
    (r"(?:former|previous|first)\s+wife",
     GROUP_PRIOR_PARTNERS, "wife", STATE_FORMER, ""),
    (r"(?:former|previous|first)\s+husband",
     GROUP_PRIOR_PARTNERS, "husband", STATE_FORMER, ""),
    (r"(?:former|previous|first)\s+spouse",
     GROUP_PRIOR_PARTNERS, "spouse", STATE_FORMER, ""),
    (r"(?:former|previous)\s+partner",
     GROUP_PRIOR_PARTNERS, "partner", STATE_FORMER, ""),

    # ── current spouse / partner ─────────────────────────────────────
    (r"wife", GROUP_SPOUSE, "wife", STATE_CURRENT, ""),
    (r"husband", GROUP_SPOUSE, "husband", STATE_CURRENT, ""),
    (r"spouse", GROUP_SPOUSE, "spouse", STATE_CURRENT, ""),
    # THE PARTNER FIX. Measured as quarantined `relationship_unstated`
    # before Phase 5B. Binding it must never imply a marriage — the
    # relation is `partner`, and no marriage field is derived from it.
    (r"partner", GROUP_SPOUSE, "partner", STATE_CURRENT, ""),

    # ── parents ──────────────────────────────────────────────────────
    # `daddy` FIRST so it is not consumed by `dad`.
    (r"daddy", GROUP_PARENTS, "father", "", ""),
    (r"stepfather", GROUP_PARENTS, "stepfather", "", ""),
    (r"stepmother", GROUP_PARENTS, "stepmother", "", ""),
    (r"father", GROUP_PARENTS, "father", "", ""),
    (r"papa", GROUP_PARENTS, "father", "", ""),
    (r"pop", GROUP_PARENTS, "father", "", ""),
    (r"dad", GROUP_PARENTS, "father", "", ""),
    (r"mommy", GROUP_PARENTS, "mother", "", ""),
    (r"mother", GROUP_PARENTS, "mother", "", ""),
    (r"mama", GROUP_PARENTS, "mother", "", ""),
    (r"momma", GROUP_PARENTS, "mother", "", ""),
    (r"mom", GROUP_PARENTS, "mother", "", ""),
    (r"mum", GROUP_PARENTS, "mother", "", ""),
    (r"ma", GROUP_PARENTS, "mother", "", ""),
    (r"parents?", GROUP_PARENTS, "parent", "", ""),

    # ── siblings, with the qualifier preserved ───────────────────────
    (r"(older|elder|big)\s+brother", GROUP_SIBLINGS, "brother", "", "older"),
    (r"(younger|little|kid)\s+brother", GROUP_SIBLINGS, "brother", "", "younger"),
    (r"(older|elder|big)\s+sister", GROUP_SIBLINGS, "sister", "", "older"),
    (r"(younger|little|kid)\s+sister", GROUP_SIBLINGS, "sister", "", "younger"),
    (r"half[-\s]?brother", GROUP_SIBLINGS, "brother", "", "half"),
    (r"half[-\s]?sister", GROUP_SIBLINGS, "sister", "", "half"),
    (r"step[-\s]?brother", GROUP_SIBLINGS, "brother", "", "step"),
    (r"step[-\s]?sister", GROUP_SIBLINGS, "sister", "", "step"),
    (r"brother", GROUP_SIBLINGS, "brother", "", ""),
    (r"sister", GROUP_SIBLINGS, "sister", "", ""),
    (r"siblings?", GROUP_SIBLINGS, "sibling", "", ""),
    (r"twin", GROUP_SIBLINGS, "twin", "", ""),

    # ── children, with the `adult` qualifier preserved ───────────────
    #
    # `adult daughter` is a daughter described as adult. It is NOT a
    # separate kinship type, and no numeric age is invented from it.
    (r"adult\s+daughter", GROUP_CHILDREN, "daughter", "", "adult"),
    (r"adult\s+son", GROUP_CHILDREN, "son", "", "adult"),
    (r"adult\s+child", GROUP_CHILDREN, "child", "", "adult"),
    (r"grown\s+daughter", GROUP_CHILDREN, "daughter", "", "adult"),
    (r"grown\s+son", GROUP_CHILDREN, "son", "", "adult"),
    (r"daughter", GROUP_CHILDREN, "daughter", "", ""),
    (r"son", GROUP_CHILDREN, "son", "", ""),
    (r"children", GROUP_CHILDREN, "child", "", ""),
    (r"child", GROUP_CHILDREN, "child", "", ""),
    (r"kids?", GROUP_CHILDREN, "child", "", ""),

    # ── grandparents ─────────────────────────────────────────────────
    (r"great[-\s]?grand\s?mother", GROUP_GREAT_GRANDPARENTS, "greatGrandmother", "", ""),
    (r"great[-\s]?grand\s?father", GROUP_GREAT_GRANDPARENTS, "greatGrandfather", "", ""),
    (r"great[-\s]?grand\s?parents?", GROUP_GREAT_GRANDPARENTS, "greatGrandparent", "", ""),
    (r"grand\s?mother", GROUP_GRANDPARENTS, "grandmother", "", ""),
    (r"grand\s?father", GROUP_GRANDPARENTS, "grandfather", "", ""),
    (r"grandma", GROUP_GRANDPARENTS, "grandmother", "", ""),
    (r"granny", GROUP_GRANDPARENTS, "grandmother", "", ""),
    (r"nana", GROUP_GRANDPARENTS, "grandmother", "", ""),
    (r"grandpa", GROUP_GRANDPARENTS, "grandfather", "", ""),
    (r"grand\s?parents?", GROUP_GRANDPARENTS, "grandparent", "", ""),
)

_COMPILED = tuple(
    (re.compile(r"\b" + pat + r"\b", re.IGNORECASE), grp, rel, st, qual)
    for pat, grp, rel, st, qual in _TABLE
)


def interpret_phrase(phrase: str) -> Optional[RelationshipReading]:
    """Read ONE relationship phrase. `None` when it names no relationship."""
    if not phrase:
        return None
    text = phrase.strip()
    for rx, grp, rel, st, qual in _COMPILED:
        m = rx.search(text)
        if m:
            return RelationshipReading(
                group=grp, relation=rel, state=st, qualifier=qual,
                source_phrase=m.group(0))
    return None


def readings_in(text: str) -> List[RelationshipReading]:
    """Every relationship the narrator stated, left to right, no overlaps.

    Overlap suppression is what keeps `ex-wife` from ALSO yielding a
    current `wife` at the same offsets — the single most important
    behaviour in this module.
    """
    if not text:
        return []
    hits = []
    for rx, grp, rel, st, qual in _COMPILED:
        for m in rx.finditer(text):
            hits.append((m.start(), m.end(), grp, rel, st, qual, m.group(0)))
    # Table order is precedence; earlier entries win an overlap.
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out: List[RelationshipReading] = []
    claimed: List[Tuple[int, int]] = []
    for start, end, grp, rel, st, qual, phrase in hits:
        if any(start < c_end and end > c_start for c_start, c_end in claimed):
            continue
        claimed.append((start, end))
        out.append(RelationshipReading(group=grp, relation=rel, state=st,
                                       qualifier=qual, source_phrase=phrase))
    return out


def group_pattern(group: str):
    """A compiled alternation of every phrase that names this group.

    The kinship guard's per-role vocabulary is derived from here rather
    than maintained beside it — that duplication is what let `mama` bind
    while `daddy` did not.
    """
    alts = [pat for pat, grp, _r, _s, _q in _TABLE if grp == group]
    if not alts:
        return None
    return re.compile(r"\b(?:my\s+|our\s+)?(?:" + "|".join(alts) + r")\b",
                      re.IGNORECASE)


def lane_for(text: str, name: Optional[str] = None) -> Optional[RelationshipReading]:
    """The lane the narrator's wording makes legal for `name`.

    When a name is given, the reading NEAREST that name wins — a passage
    saying "My wife Mary is a nurse. My ex-wife Susan was a teacher."
    must give Mary the current lane and Susan the former one, and a
    whole-answer reading cannot do that.
    """
    found = readings_in(text)
    if not found:
        return None
    if not name:
        return found[0]
    idx = text.lower().find(name.lower())
    if idx < 0:
        return found[0]
    best, best_dist = None, None
    for reading in found:
        pos = text.lower().find(reading.source_phrase.lower())
        if pos < 0:
            continue
        dist = abs(idx - pos)
        # A relationship stated BEFORE the name is the ordinary form
        # ("my ex-wife Susan"), so ties break toward the earlier phrase.
        if best_dist is None or dist < best_dist:
            best, best_dist = reading, dist
    return best or found[0]


__all__ = [
    "RelationshipReading", "interpret_phrase", "readings_in", "group_pattern",
    "lane_for", "SPOUSE_RELATIONS", "STATE_CURRENT", "STATE_FORMER",
    "GROUP_PARENTS", "GROUP_SPOUSE", "GROUP_PRIOR_PARTNERS", "GROUP_CHILDREN",
    "GROUP_SIBLINGS", "GROUP_GRANDPARENTS", "GROUP_GREAT_GRANDPARENTS",
]
