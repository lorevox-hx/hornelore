#!/usr/bin/env python3
"""READ ONLY. Settle the strong-correction routing question from a trace.

Phase 6 B2. The question is NOT whether the browser regex matches
"it wasn't the same after that" — it does, and that was measured
offline. The question is what happens to the turn AFTER the browser
proposes `correction`:

    browser proposes  ->  server receives  ->  parser finds an
    actionable correction, or does not  ->  effective turn mode  ->
    model generated or bypassed  ->  completed-turn disposition

If the server resets the turn to `interview` and the model runs
normally, the question is closed and the browser regex needs no change:
a broad proposal that the server boundary safely resolves is not a
defect. If instead the turn reaches a deterministic branch and never
reaches the model, then an ordinary sentence about loss is being
answered by a template, and that is a Phase 6 defect.

WHY THIS SCRIPT EXISTS RATHER THAN A GREP. Three facts are written at
three different points in the turn and none may be inferred from
another (protocol §4a):

    requested_turn_mode   what the browser asked for
    effective_turn_mode   what survived routing and the fallthrough
    generation_attempted  whether prompt composition was reached

Reading only `effective_turn_mode: interview` and concluding the
browser asked for `interview` is the exact inference this script
refuses to let anyone make by eye.

This script writes nothing, mutates nothing, and never starts a stack.
"""

import argparse
import glob
import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PHRASE = "it wasn't the same after that"

# The Lean arm, as measured on Phase 6 Run 4 — revision 3, 4/43 selected
# (ids 20, 49, 52, 53), which is `All Switchable Off`: every switchable
# conversational intervention down, protected/fail-closed infrastructure
# untouched. B2 must be read under this arm and no other.
#
# WHY THIS IS A REFUSAL RATHER THAN A NOTE. The routing question is about
# what the SERVER decided, and a post-generation authority that rewrites
# the reply afterwards makes the delivered text unreadable as evidence of
# that decision. A turn taken under Defaults or All-on would still print
# a plausible-looking verdict, and nothing on the page would say it came
# from the wrong arm.
_LEAN_SELECTION_FP = (
    "55a52f0cb0450ba4e4547cf2ab1c625a3b4a6ce5fcc19f461bdfbcb813d25226")
_LEAN_SELECTED_IDS = [20, 49, 52, 53]


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _resolve_run_dir(explicit):
    """Prefer an explicit dir, then the armed marker, then the last one.

    Printing WHICH pointer was used is the point: reading the wrong run
    silently is the failure this avoids.
    """
    if explicit:
        return explicit, "--run (explicit)"
    for marker, label in (
        (os.path.join(_REPO, ".runtime/eval/current_eval_dir"),
         "current_eval_dir (armed)"),
        (os.path.join(_REPO, ".runtime/eval/last_eval_dir"),
         "last_eval_dir (stack stopped)"),
    ):
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8") as fh:
                p = fh.read().strip()
            if p:
                return p, label
    return None, "none"


def _load(run_dir):
    recs = []
    pat = os.path.join(run_dir, "response-trace", "*.jsonl")
    for path in sorted(glob.glob(pat)):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    continue
    return recs


def _parser_evidence(conv_id):
    """What the SERVER's parser did on this conversation.

    The trace records the turn's outcome; only the server log records
    whether `parse_correction_rule_based` was consulted and what it
    returned. Without this, `effective_turn_mode: interview` has two
    causes — the parser rescuing an unactionable correction, or the
    route-clamp resetting it before the parser was reached — and the
    first version of this probe confused exactly those two.
    """
    log = os.path.join(_REPO, ".runtime/logs/api.log")
    out = {"clamped": None, "parsed": None, "fallthrough": None,
           "deterministic": None, "lines": []}
    if not conv_id or not os.path.isfile(log):
        return out
    try:
        with open(log, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if conv_id not in line:
                    continue
                s = line.rstrip()
                if "route-clamp" in s:
                    out["clamped"] = s[-200:]
                    out["lines"].append(s[:260])
                elif "correction turn for conv" in s and "parsed=" in s:
                    out["parsed"] = s.split("parsed=", 1)[1].strip()
                    out["lines"].append(s[:260])
                elif "correction-fallthrough" in s:
                    out["fallthrough"] = True
                    out["lines"].append(s[:260])
                elif "[witness][deterministic]" in s:
                    out["deterministic"] = s[:200]
                    out["lines"].append(s[:260])
    except OSError:
        pass
    out["lines"] = out["lines"][-6:]
    return out


def _fallthrough_lines(phrase):
    """The server's own log line for the rescue, if it is there."""
    log = os.path.join(_REPO, ".runtime/logs/api.log")
    if not os.path.isfile(log):
        return ["(no .runtime/logs/api.log on this host)"]
    out = []
    try:
        with open(log, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "correction-fallthrough" in line or (
                        "correction" in line and _norm(phrase)[:24] in _norm(line)):
                    out.append(line.rstrip()[:300])
    except OSError as exc:
        return [f"(could not read api.log: {exc})"]
    return out[-8:] or ["(no correction-fallthrough line found)"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default=None,
                    help="evidence directory; defaults to the armed marker")
    ap.add_argument("--phrase", default=_DEFAULT_PHRASE,
                    help="narrator utterance to locate")
    ap.add_argument("--arm", default="lean+26",
                    choices=("lean", "lean+26", "any"),
                    help="required Guard Lab arm. 'lean+26' is the B2 arm: "
                         "Lean plus the correction ROUTE, which is the only "
                         "configuration in which the server's parser gets "
                         "jurisdiction. 'lean' cannot answer B2 and says so. "
                         "'any' records the arm but does not refuse.")
    args = ap.parse_args()

    run_dir, how = _resolve_run_dir(args.run)
    print(f"run directory : {run_dir}")
    print(f"resolved via  : {how}")
    if not run_dir or not os.path.isdir(run_dir):
        print("\nREFUSED: no readable evidence directory.")
        return 2

    recs = _load(run_dir)
    print(f"traced turns  : {len(recs)}")

    want = _norm(args.phrase)
    hits = [r for r in recs
            if want in _norm((r.get("context") or {}).get("narrator_input"))]
    if not hits:
        print(f"\nREFUSED: no traced turn contains {args.phrase!r}.")
        print("Turns present:")
        for r in recs:
            ni = (r.get("context") or {}).get("narrator_input")
            print("  -", (str(ni or "")[:88] or "(none)"))
        return 3

    if len(hits) > 1:
        print(f"\nNOTE: {len(hits)} turns match; all are shown. A retried "
              f"turn means the run is contaminated — arm a new one.")

    # ── The arm check, before any verdict is printed ──────────────────
    wrong_arm = []
    for r in hits:
        c = r.get("context") or {}
        sel = sorted(c.get("authority_selected") or [])
        fp = c.get("authority_selection_fingerprint")
        applied = c.get("authority_experiment_applied")
        print("\n" + "-" * 68)
        print(f"turn_key                : {r.get('turn_key')}")
        print(f"authority_revision      : {c.get('authority_revision')}")
        print(f"selection_fingerprint   : {fp}")
        print(f"selected ({len(sel)})           : {sel}")
        print(f"experiment_applied      : {applied}")
        print(f"gate_reason             : {c.get('authority_gate_reason')}")
        if args.arm in ("lean", "lean+26"):
            want = (_LEAN_SELECTED_IDS if args.arm == "lean"
                    else sorted(_LEAN_SELECTED_IDS + [26]))
            why = []
            if sel != want:
                why.append(
                    f"selected ids are {sel} — the {args.arm} arm is "
                    f"{want}")
            if args.arm == "lean" and fp != _LEAN_SELECTION_FP:
                why.append(
                    f"selection fingerprint is {fp} — Lean is "
                    f"{_LEAN_SELECTION_FP}")
            if not applied:
                why.append(
                    "experiment_applied is false — the turn ran on "
                    "production defaults, not the selected configuration")
            if why:
                wrong_arm.append((r.get("turn_key"), why))

    # A run directory legitimately holds turns from more than one arm —
    # the B2 sequence deliberately took the same sentence under Lean and
    # then under Lean+26. Refusing the whole run would throw away the
    # second measurement because the first exists. Each turn is judged
    # under its own arm instead, and only turns matching --arm can close
    # the question.
    wrong = {tk: why for tk, why in wrong_arm}

    verdicts = []
    for r in hits:
        c = r.get("context") or {}
        tk = r.get("turn_key")
        if tk in wrong:
            print("\n" + "=" * 68)
            print(f"turn_key            : {tk}")
            print(f"SKIPPED — not the {args.arm} arm:")
            for w in wrong[tk]:
                print(f"    - {w}")
            continue
        req = c.get("requested_turn_mode")
        eff = c.get("effective_turn_mode")
        gen = c.get("generation_attempted")
        print("\n" + "=" * 68)
        print(f"turn_key            : {r.get('turn_key')}")
        print(f"narrator said       : {c.get('narrator_input')}")
        print(f"requested_turn_mode : {req}")
        print(f"effective_turn_mode : {eff}")
        print(f"generation_attempted: {gen}")
        print(f"generation_end      : {c.get('generation_end_reason')}")
        print(f"raw == delivered    : {r.get('raw_equals_delivered')}")
        print(f"words raw/delivered : {r.get('raw_words')}/"
              f"{r.get('delivered_words')}")
        print(f"delivered           : {r.get('delivered_text')}")
        stages = [s for s in (r.get("stages") or []) if s.get("changed")]
        print(f"stages that changed : "
              f"{[s.get('stage') for s in stages] or 'none'}")

        # ── FOURTH FACT, added 2026-09-08 after this probe got it wrong ──
        # `requested=correction, effective=interview, generated=True` has
        # TWO possible causes and they are not the same finding:
        #
        #   (a) the server parsed the turn, found no actionable target or
        #       value, and rescued it to `interview` — the boundary the
        #       question is about; or
        #   (b) Guard Lab id 26 (the correction ROUTE) was EXCLUDED, so
        #       the route-clamp reset both turn_mode copies before the
        #       parser was ever consulted.
        #
        # Under the LEAN arm every switchable authority is off, INCLUDING
        # id 26 — so Lean removes the very route being measured, and (b)
        # is guaranteed. The first run of this probe reported (a) on a
        # Lean turn whose api.log said plainly it was (b). Read the
        # exclusion list; do not infer the cause from the outcome.
        excluded = set(c.get("authority_excluded") or [])
        route_clamped = 26 in excluded

        if route_clamped and req == "correction":
            v = ("INCONCLUSIVE — id 26, the correction ROUTE, was "
                 "EXCLUDED on this turn, so the clamp reset the mode "
                 "before the parser could be consulted. This measures "
                 "the Guard Lab clamp, NOT the server's correction "
                 "boundary. Re-run with id 26 SELECTED — everything "
                 "else may stay Lean — or the question stays open.")
            print("\nVERDICT: " + v)
            verdicts.append(v)
            continue

        # Fifth fact: what the server's parser actually did.
        ev = _parser_evidence(r.get("conversation_id"))
        print(f"parser consulted    : "
              f"{'yes, parsed=' + ev['parsed'] if ev['parsed'] is not None else 'NO RECORD'}")
        print(f"correction-fallthru : {bool(ev['fallthrough'])}")
        # CONVERSATION-scoped, not turn-scoped: api.log lines are matched
        # by conv_id, and the B2 sequence took two turns in one
        # conversation. A clamp line here may belong to an EARLIER turn
        # under a different revision — compare the timestamps below
        # before attributing it to this turn.
        print(f"route-clamp seen in conv (may be an earlier turn): "
              f"{bool(ev['clamped'])}")
        for ln in ev["lines"]:
            print("   log| " + ln)

        # The verdict is stated from the five facts, never from one.
        if req == "correction" and eff == "interview" and gen:
            if ev["parsed"] is None:
                v = ("INCONCLUSIVE — id 26 was selected, so the route was "
                     "not clamped, but the server log carries NO record of "
                     "the parser being consulted for this conversation. "
                     "Do not assume the fallthrough ran; find the log or "
                     "take the turn again with logging in place.")
            elif ev["parsed"] in ("{}", "{ }") and ev["fallthrough"]:
                v = ("CLOSED — the browser proposed `correction`; the "
                     "correction ROUTE was live (id 26 selected), so the "
                     "server's parser had jurisdiction and was consulted; "
                     "it returned parsed={} — no actionable target or "
                     "value; the correction-fallthrough reset BOTH "
                     "turn_mode copies to `interview` and the model ran. "
                     "THE SERVER BOUNDARY SAFELY RESCUES THIS "
                     "FALSE-POSITIVE BROWSER PROPOSAL. A broad browser "
                     "regex that the server resolves is not a defect, so "
                     "the regex needs no change on this evidence.")
            else:
                v = (f"REVIEW — parser returned {ev['parsed']!r}, which is "
                     f"not the empty result. The turn still generated, but "
                     f"a non-empty parse reaching the ordinary pipeline is "
                     f"worth reading before drawing a conclusion.")
        elif req == "correction" and not gen:
            v = ("DEFECT — the turn was claimed by a deterministic "
                 "correction branch and NEVER REACHED THE MODEL. An "
                 "ordinary sentence about loss was answered by a "
                 "template. This is a Phase 6 defect.")
        elif req != "correction":
            v = (f"INCONCLUSIVE — the browser proposed {req!r}, not "
                 f"`correction`, so this turn does not exercise the "
                 f"question. Check the utterance was sent verbatim.")
        else:
            v = (f"INCONCLUSIVE — requested={req!r} effective={eff!r} "
                 f"generated={gen!r} is a combination this probe does not "
                 f"have a rule for. Do not guess; report it.")
        print("\nVERDICT: " + v)
        verdicts.append(v)

    print("\n" + "=" * 68)
    print("server-side correction-fallthrough evidence from api.log:")
    for line in _fallthrough_lines(args.phrase):
        print("  " + line)

    return 0 if all(v.startswith("CLOSED") for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
