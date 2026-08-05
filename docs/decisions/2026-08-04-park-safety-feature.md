# Decision: park the runtime safety feature in Lean Lori

**Date:** 2026-08-04
**Decided by:** Chris
**Status:** ACTIVE — parked, reversible, preserved
**Work order:** WO-LEAN-LORI-RUNTIME-01 Phase 3B

---

## The decision

The entire runtime safety feature is **parked** in Lean Lori. Parked means
inactive at runtime and fully preserved in the repository — the way
Companion mode is parked. Nothing is deleted.

In the parked state:

- the LLM safety classifier performs **zero generations**;
- the detailed safety protocol contributes **zero prompt tokens**;
- deterministic safety scanning and the operator cascade are inactive on
  the WebSocket chat path **and on the legacy `POST /api/interview/answer`
  REST path**;
- browser safety detection, the keyword latch and the safety posture are
  inactive;
- softened mode and safety notifications are inactive — including
  **reads of softened rows written before parking**, on both paths.

### The gate sits at the entrance, not at the call sites

`safety.scan_answer()` and `safety.set_softened()` consult the state
themselves. The first pass gated them at the call sites, which was the
wrong shape twice over: it missed the legacy REST interview route
entirely, and even once that was fixed, a call-site gate only protects
the call sites somebody remembered. A caller written next month
inherits the gate now.

`scan_answer()` returns `None` while parked rather than raising. `None`
already means "nothing triggered", every caller handles it, and a parked
feature should be quiet rather than a new source of exceptions on a
narrator's turn. The patterns, `detect_crisis` and every threshold are
untouched — parking suppresses the answer, not the detector, because
reactivation and any future red-team run against the preserved corpus
depend on the detector still working.

Softened mode is refused at three depths, deliberately redundantly: the
read is suppressed on both paths, the `runtime71` handoff refuses on its
own terms, and the composer refuses the directive even if a caller hands
it stale state. The composer is the last thing between a stale row and
Lori's prompt, and *"the caller will have checked"* is exactly the
assumption that let the REST route run a full safety cascade on a parked
deployment.

### Two seams found on review, after the first pass

The first pass followed the chat path and left two doors open. Recording
them because the shape is the lesson: a *feature*-level park has to close
every entrance, and the ones that get missed are the paths nobody was
looking at.

**The legacy REST interview route.** `POST /api/interview/answer` called
`scan_answer()`, wrote a segment flag, set softened mode and returned
crisis resources without consulting the state. A deployment that was
parked everywhere else was still fully armed here.

**Stored softened state does not expire.** Softened rows written before
parking would still have been read afterwards, so a narrator who
triggered softened mode last week would have met a softened Lori today —
produced by a switched-off feature, from a prompt that no longer carries
the protocol softened mode was written to accompany. Both paths now
suppress the **read**.

The rows are deliberately **not** deleted, cleared or expired. They are
preserved evidence, and reactivation must find each session exactly as it
was left. **Parking is not a data migration.**

The operator surface (`GET /api/safety-events/softened/{conv_id}`) still
reports the stored value, because an operator asking what is in the
database deserves the answer. But it now returns the *effective* value in
the field the banner keys on, plus `safety_parked` and
`stored_interview_softened` alongside. A true row under an untrue caption
— "softened mode is on for N more turns", when no softened directive can
reach Lori — is still a lie to the reader.

One server-authoritative setting governs all of it:
`HORNELORE_SAFETY_STATE`, defaulting to `parked`.

---

## Why

**Lean Lori is a family oral-history system. It is not monitored
emergency support.** Nobody is watching it, nobody is on call, and it
makes no promise of response. An always-on emergency apparatus in that
context bought a real cost and a false impression at the same time — and
the false impression is the more serious half. A system that produces
crisis-line scripts can read, to the person using it, as a system that is
watching over them. This one is not, and it should not imply that it is.

The costs were measured, not estimated.

| what | cost |
|---|---|
| Safety protocol in **every** prompt | 7,933 chars — **44% of `DEFAULT_CORE`**, ~1,800 tokens |
| Extra classifier generation on most eligible turns | 1,392 tokens, ~1.52 s, ~0.55 GB transient VRAM |
| Classifier before the raw-ephemeral repair | 5,508 tokens, 3.37 s, 1.46 GB |

Those tokens competed directly with Lori's identity and instructions for
a context window that was already overrunning on **60.6% of turns** (630
real turns: p50 8,861 tokens against a 8,192 window). The front of the
prompt — identity, purpose, interview discipline — is what the truncation
discarded.

**It also leaked.** Lori recited part of the 988 instruction during an
ordinary conversation about a cemetery, because the script was sitting in
her prompt on a turn where nobody was in danger. A model under context
pressure reproduces scripts it has been handed.

**And its behaviour is not yet good enough to justify the cost.** The
192-generation measurement of 2026-08-04 found real value — 24
reproducible acute catches the deterministic patterns missed — alongside
real harm: mortality reflection escalated to a crisis line. The clearest
example is deterministic, not model-driven:

> `"I've had a good run. I'm not afraid of the ending."`
> → pattern layer classifies **domestic_abuse** → routed acute.

The LLM read that correctly as mortality reflection and was overruled by
the layer we had been treating as the trustworthy baseline.

---

## What is preserved

Everything, and it is expected to still pass its own tests:

- `server/code/api/safety.py` — deterministic scanner and patterns
- `server/code/api/safety_classifier.py` — including the Phase 3A
  raw-ephemeral repair, so reactivation lands on the cheap stateless
  call rather than the composed one
- `prompt_composer.LORI_SAFETY_PROTOCOL` — the protocol verbatim, split
  out of `DEFAULT_CORE` at a marker rather than retyped, with a test
  proving the two halves reconstitute the original
- `DEFAULT_CORE` itself, still exported — parking a feature must not make
  its source unfindable
- the browser detection, latch and posture code
- `docs/reports/lean_lori_safety_corpus_2026-08-04.json` — the 48-phrase
  corpus
- `docs/reports/lean_lori_safety_gate.json` — the 192-generation
  measurement
- every safety test suite, which opts back into
  `HORNELORE_SAFETY_STATE=active` and still passes

---

## Why a state, and not `LV_ENABLE_SAFETY=0`

`LV_ENABLE_SAFETY=0` disables the backend cascade only. With it set, the
1,800-token manual would still ship inside `DEFAULT_CORE` on every turn,
and the browser latch would still arm on a keyword. Three separate
mechanisms — prompt, server, browser — need **one** authority, and the
server is it. The browser is *told* the state rather than trusted to
agree with it.

Concretely: the browser asks `GET /api/runtime-posture` once at load and
gates detection at `_lv80ScanSafety`, which is its single entry point.
One gate there closes detection, the latch, the posture badge, idle
suppression and the outgoing `[SAFETY MODE: ACTIVE]` directive together;
gating each consumer separately would have been five chances to miss
one. A second, deliberately redundant gate sits on the outgoing
directive, for a future path that sets the posture some other way.

An unanswered or failed fetch resolves to **parked**, and that direction
is chosen rather than defaulted into. Server parked with the browser
believing otherwise gives the narrator a safety posture with nothing
behind it and sends an emergency directive to a model whose parked
prompt has no emergency instructions to anchor it — an unanchored
directive is worse than none. Server active with the browser believing
otherwise loses a posture hint and idle suppression; the backend
deterministic scan is untouched and still fires. The browser has always
been a hint on top of the server, never the detector, which is what
makes that direction affordable.

`LV_ENABLE_SAFETY` and `HORNELORE_SAFETY_LLM_LAYER` are now
**subordinate**: when the state is parked they are not consulted at all,
so no combination of stale values in someone's `.env` can bring one piece
of a parked feature back on its own.

An unrecognised value for `HORNELORE_SAFETY_STATE` resolves to `parked`.
A typo must not switch an entire feature family on.

---

## Reactivation

Reactivation is **Chris's decision**, not a configuration convenience.

```bash
HORNELORE_SAFETY_STATE=active
```

That is mechanically sufficient and deliberately not sufficient on its
own. Before safety runs against a real narrator again it needs a focused
**efficacy and specificity acceptance** — because the measured behaviour
today includes routing ordinary older-adult mortality talk to a crisis
line. The three known defects to resolve first:

1. the deterministic `domestic_abuse` false positive quoted above;
2. mortality-reflection escalation, which the Phase 3A guidance
   addresses but which has not been re-measured;
3. `"It will be a relief when I go, honestly."` — escalated by both call
   modes, and the shape `WO-LORI-SAFETY-PASSIVE-DEATH-WISH-01` was
   parked for. Passive death wish is not acute ideation, and the right
   response is softened presence plus an operator flag, not 988 and not
   silence.

---

## What this does not claim

This does not claim safety is unnecessary in general, or that Lorevox
should ship without it. It records that **for the present family
oral-history use, on this machine, the runtime cost and the false
impression outweigh a benefit that has not yet been made reliable.**

If Lean Lori is ever put in front of narrators outside the family, or if
anyone comes to rely on it as support, this decision must be revisited
before that happens — not after.
