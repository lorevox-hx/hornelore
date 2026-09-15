# WO-KINSHIP-RESOLVER-04 — derive extended kinship, store none of it

**Status: PLANNED. NOTHING IMPLEMENTED.** Filed 2026-09-14.

Governed by [`WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00`](WO-LOREVOX-FAMILY-KNOWLEDGE-MASTER-00_Spec.md),
which owns the invariants and requirements. **This document owns only scope and evidence.**

**Blocked behind the portability lane, WO-01, WO-02 and WO-03.**

---

## Mission alignment

Families are described in relationships nobody writes down directly — *my mother's
cousin*, *Kent's paternal grandfather*. Lorevox should be able to answer those from what
the narrator and operator actually asserted, without inventing edges the family never
stated. **Store direct asserted relationships. Derive extended kinship.**

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity; introduce `must_not_write` violations or
system-tone outputs; regress the locked extractor baseline; expand operator surfaces into
narrator UI; add detectors that duplicate existing signals; **write derived kinship back
into the graph as stored edges** (INV-06); or introduce a dependency before the native
implementation has proven insufficient (DRIFT-06, DRIFT-07).

## In scope

Derivation from direct canonical topology of: parent · child · sibling · grandparent ·
great-grandparent · aunt/uncle · niece/nephew · first cousin · farther cousin degree where
it is mathematically reliable · maternal versus paternal path where known.

Answers to questions of the shape: *How is Clara related to Kent?* · *Who are
Christopher's first cousins?* · *Is George Kent's paternal or maternal grandfather?* ·
*Was George Janice's father-in-law?*

**Unresolvable is an answer.** Where the topology does not support a determination, the
resolver says so. It does not invent a path.

## Implementation rules

SQLite remains durable truth. Start with ordinary Python, recursive SQL or bounded
in-memory traversal — **all three are already available and none of them is a new
dependency.** NetworkX is not approved and must not be introduced unless measured
complexity proves it beneficial; if it ever is, it answers the master's ten-item
dependency gate first and **never becomes the canonical store**.

## Out of scope

GEDCOM · publishing · charts · changes to how relationships are entered or stored.

## Required tests

Derivation, each against a synthetic graph whose expected answers are constructed by hand
and asserted exactly: parent · sibling · grandparent · great-grandparent · aunt · uncle ·
first cousin.

Edge semantics: half relationship · adoptive relationship · step relationship — each must
keep its distinction rather than collapsing into the biological case (R-26).

Refusals and safety: **no path** between two people · ambiguous or corrupt topology ·
**cycle protection** · deterministic answer across runs.

And the invariant this WO exists to protect: **no redundant transitive edge is inserted as
a side effect** — measured against the graph after the resolver has run, not asserted in a
comment.

## Acceptance gate

Derived kinship is reproducible and correct **without storing redundant transitive edges**,
and an unresolvable relationship is reported rather than invented. Evidence packet per the
master's §6.
