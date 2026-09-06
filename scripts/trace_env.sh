#!/usr/bin/env bash
# ── THE ONE PLACE THE RESPONSE-TRACE ENVIRONMENT IS DECIDED ──────────
#
# `WO-LORI-LISTEN-AND-RETAIN-01` — VRAM/prompt-budget diagnostic.
#
# ── WHY A SEPARATE FILE, 2026-09-06 ─────────────────────────────────
#
# Two shells decide this flag, and until now the second silently undid
# the first:
#
#   scripts/common.sh                     loads .env, resolves the flag
#     └─ start_named_process → nohup bash -lc "$API_CMD"
#          └─ launchers/hornelore_run_gpu_8000.sh
#                                          loads .env AGAIN  ← clobber
#
# `.env` pins `HORNELORE_RESPONSE_TRACE=0`, so the launcher's own `.env`
# load reset the wrapper's resolved value to 0 in the very process that
# writes the traces. Measured, not theorised:
#
#   after common.sh (the wrapper):   TRACE=1
#   after the launcher sources .env: TRACE=0
#
# The launcher cannot simply source `common.sh` instead: that file runs
# `set -euo pipefail`, creates pid/log directories and defines ports and
# process helpers, none of which belongs in a production launcher whose
# own contract is `set -e`. So the RULE moves here, and both shells call
# it. **One definition, two call sites — not two copies.** A second
# precedence algorithm is how the last one drifted.
#
# ── HOW TO USE IT ───────────────────────────────────────────────────
#
#   source "<dir>/trace_env.sh"
#   hornelore_trace_capture      # BEFORE this shell loads .env
#   ... load .env ...
#   hornelore_trace_resolve      # AFTER
#
# The capture/resolve split is load-bearing. `.env` is sourced with
# `set -a`, so after it runs there is no way to tell a value the caller
# exported from one `.env` supplied — and the caller's must win.
#
# ── PRECEDENCE, MOST SPECIFIC FIRST ─────────────────────────────────
#
#   1. what the caller exported for THIS invocation
#      (for the launcher, that includes the wrapper's already-resolved
#      answer, which is why the chain composes instead of fighting)
#   2. the experiment marker, `.runtime/eval/current_eval_dir`
#   3. `.env`
#   4. off
#
# `.env` keeping `HORNELORE_RESPONSE_TRACE=0` is deliberate and must
# stay: ordinary Hornelore use records nothing.

#: Snapshot what the caller asked for. Call BEFORE this shell loads
#: `.env`. Uses `${VAR-}` rather than `${VAR:-}` so an intentional empty
#: string is distinguishable from unset under `set -u`.
hornelore_trace_capture() {
  _HL_TRACE_CAPTURED="${HORNELORE_RESPONSE_TRACE-}"
  _HL_TRACE_DIR_CAPTURED="${HORNELORE_TRACE_DIR-}"
}

#: Apply the precedence above. Call AFTER this shell has loaded `.env`.
#: `repo_root` defaults to the parent of this script's directory.
hornelore_trace_resolve() {
  local repo_root="${1:-}"
  if [ -z "$repo_root" ]; then
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi

  local marker="$repo_root/.runtime/eval/current_eval_dir"
  local eval_dir=""
  if [ -r "$marker" ]; then
    # `$(<file)` strips trailing newlines, so a marker written with
    # `printf '%s\n'` yields the path and not path-plus-newline.
    eval_dir="$(<"$marker")"
  fi

  if [ -n "${_HL_TRACE_CAPTURED-}" ]; then
    export HORNELORE_RESPONSE_TRACE="$_HL_TRACE_CAPTURED"
  elif [ -n "$eval_dir" ]; then
    export HORNELORE_RESPONSE_TRACE=1
  else
    export HORNELORE_RESPONSE_TRACE="${HORNELORE_RESPONSE_TRACE:-0}"
  fi

  if [ -n "${_HL_TRACE_DIR_CAPTURED-}" ]; then
    export HORNELORE_TRACE_DIR="$_HL_TRACE_DIR_CAPTURED"
  elif [ -n "$eval_dir" ]; then
    # A blank or deleted marker must not resolve to the repo root.
    # `lori_response_trace._out_dir()` tests truthiness, so an empty
    # value falls through to the module default rather than writing
    # traces into the working directory.
    export HORNELORE_TRACE_DIR="$eval_dir/response-trace"
  else
    export HORNELORE_TRACE_DIR="${HORNELORE_TRACE_DIR:-}"
  fi
}

#: Say plainly whether tracing is on AND where it is writing.
#:
#: The destination is printed because the previous banner hard-coded
#: `.runtime/eval/response-trace/`, which becomes a false statement the
#: moment a run-scoped directory is in use — and a banner that lies
#: about the destination is worse than no banner, because it is read as
#: confirmation.
#:
#: The OFF text deliberately does NOT suggest putting the flag in
#: `.env`. That would leave tracing permanently on and record every
#: ordinary narrator turn from then on, which is exactly what the
#: self-limiting marker exists to prevent: the marker is written when an
#: experiment starts and removed by `stop_all.sh` when it ends, so
#: arming and disarming are the same gesture as starting and stopping
#: the measurement.
hornelore_trace_banner() {
  if [ "${HORNELORE_RESPONSE_TRACE:-0}" = "1" ]; then
    printf 'Response trace: ENABLED (observation only)\n'
    printf '  writing to: %s\n\n' \
      "${HORNELORE_TRACE_DIR:-<default> .runtime/eval/response-trace}"
  else
    printf 'Response trace: OFF.\n'
    printf '  To record an evaluation run, ARM it before starting the stack:\n'
    printf '    mkdir -p .runtime/eval/<run-id>\n'
    printf '    printf %%s\\\\n "$PWD/.runtime/eval/<run-id>" \\\n'
    printf '      > .runtime/eval/current_eval_dir\n'
    printf '  `stop_all.sh` disarms it again. Do NOT set the flag in .env —\n'
    printf '  that records every ordinary narrator turn from then on.\n\n'
  fi
}
