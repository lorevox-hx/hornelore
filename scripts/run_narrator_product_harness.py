#!/usr/bin/env python3
"""Four-persona Hornelore product and extraction harness.

The runner deliberately separates capability classes:

* Shatner and Dolly are existing ``reference`` narrators.  They may be read
  and sent through direct extraction, but the harness never mutates them.
* Tomasita and Alex are fictional writable fixtures.  Live runs create a
  unique ``testing_only`` narrator through the normal intake API and hard
  delete only the exact returned UUID after verifying its harness-only name.

The default action is ``plan`` and performs no network or database work.
Reports are local evidence under ``docs/reports/`` by default.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.harness.extraction_scoring import score_case, summarize  # noqa: E402

PERSONAS_PATH = REPO_ROOT / "data" / "qa" / "narrator_product_personas_v1.json"
CORE_PATH = REPO_ROOT / "data" / "qa" / "extraction_core_v1.json"
CHALLENGE_PATH = REPO_ROOT / "data" / "qa" / "extraction_challenge_v1.json"
REPORT_DIR = REPO_ROOT / "docs" / "reports"
HARNESS_NAME_PREFIX = "HARNESS PRODUCT DELME"


class HarnessError(RuntimeError):
    """A controlled harness precondition or runtime failure."""


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise HarnessError(f"expected an object in {path}")
    return value


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _http_json(
    api_base: str,
    method: str,
    path: str,
    *,
    payload: Optional[Mapping[str, Any]] = None,
    timeout: float = 30.0,
) -> Tuple[int, Any]:
    url = api_base.rstrip("/") + path
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except urllib.error.URLError as exc:
        raise HarnessError(f"{method} {url} failed: {exc.reason}") from exc


def _people(api_base: str) -> List[Dict[str, Any]]:
    status, body = _http_json(api_base, "GET", "/api/people?limit=500", timeout=20)
    if status != 200 or not isinstance(body, dict):
        raise HarnessError(f"people list failed: HTTP {status}")
    return [dict(row) for row in body.get("people", []) if isinstance(row, dict)]


def _find_reference(
    persona: Mapping[str, Any], people: Sequence[Mapping[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Resolve a reference persona to `(row, status)`.

    THREE OUTCOMES, and the distinction between them is the point.

    * **resolved** — exactly one active match, and it really is a
      `reference` narrator.
    * **not_applicable** — NO active match. The narrator is absent from
      this database, or it is soft-deleted (`/api/people` excludes
      soft-deleted rows, so the two look identical from here, and they
      mean the same thing for a harness: not available). This is a STATE,
      not a failure. It must not stop the writable synthetic personas
      from running, and it must never tempt anyone into recreating the
      reference narrator — **soft deletion is a decision and this harness
      respects it.**
    * **HarnessError** — the two cases where continuing would be
      dishonest rather than merely limited:
        - two or more ACTIVE matches, because the harness would then be
          guessing which narrator it is reading;
        - exactly one match that is NOT a reference narrator, because
          reading it would silently exercise a live narrator through a
          read-only persona's contract.

    Returning a status instead of raising on absence is the whole of this
    correction. Raising made an unrelated data-state decision — somebody
    soft-deleting a reference narrator months ago — look like a harness
    failure, and it took the writable coverage down with it.
    """
    names = {str(name).strip().casefold() for name in persona.get("lookup_names", [])}
    matches = [
        dict(row) for row in people
        if str(row.get("display_name") or "").strip().casefold() in names
    ]
    if not matches:
        return None, "not_applicable"
    if len(matches) > 1:
        raise HarnessError(
            f"reference {persona['key']} matched {len(matches)} active narrators; "
            "refusing to guess which one to read"
        )
    row = matches[0]
    if str(row.get("narrator_type") or "live").lower() != "reference":
        raise HarnessError(
            f"{persona['key']} matched an active narrator whose narrator_type is "
            f"{row.get('narrator_type')!r}, not 'reference'"
        )
    return row, "resolved"


def _create_synthetic(
    api_base: str,
    persona: Mapping[str, Any],
    run_id: str,
    created_sink: List[Dict[str, Any]],
) -> Dict[str, Any]:
    intake = copy.deepcopy(persona.get("intake") or {})
    if not intake or not intake.get("testing_only"):
        raise HarnessError(f"{persona['key']} lacks a testing_only intake fixture")
    display = f"{HARNESS_NAME_PREFIX} {run_id} {persona['display_name']}"
    intake["preferred_name"] = display
    intake["consent_checked_by_operator"] = f"harness:product-v1:{run_id}"
    status, body = _http_json(api_base, "POST", "/api/people/intake", payload=intake, timeout=60)
    if status != 200 or not isinstance(body, dict) or not body.get("person_id"):
        raise HarnessError(f"intake failed for {persona['key']}: HTTP {status} {body!r}")
    pid = str(body["person_id"])
    # Record the cleanup target immediately. Any later GET, reference lookup,
    # scenario, report, or model failure still leaves main() holding the exact
    # UUID and exact expected name needed for guarded cleanup.
    cleanup_row = {"id": pid, "display_name": display, "narrator_type": "live"}
    created_sink.append(cleanup_row)
    check_status, check = _http_json(api_base, "GET", f"/api/people/{urllib.parse.quote(pid)}", timeout=20)
    person = (check or {}).get("person") if isinstance(check, dict) else None
    if check_status != 200 or not isinstance(person, dict) or person.get("display_name") != display:
        raise HarnessError(f"created narrator {pid} failed exact identity verification")
    cleanup_row["narrator_type"] = person.get("narrator_type", "live")
    return cleanup_row


def _delete_exact_synthetic(api_base: str, row: Mapping[str, Any]) -> Dict[str, Any]:
    pid = str(row.get("id") or "")
    expected_name = str(row.get("display_name") or "")
    if not pid or not expected_name.startswith(HARNESS_NAME_PREFIX + " "):
        raise HarnessError("refusing cleanup: target is not an exact harness-created narrator")
    status, body = _http_json(api_base, "GET", f"/api/people/{urllib.parse.quote(pid)}", timeout=20)
    person = (body or {}).get("person") if isinstance(body, dict) else None
    if status != 200 or not isinstance(person, dict) or person.get("display_name") != expected_name:
        raise HarnessError(f"refusing cleanup for {pid}: server identity no longer matches")
    inv_status, inventory = _http_json(
        api_base, "GET", f"/api/people/{urllib.parse.quote(pid)}/delete-inventory", timeout=30
    )
    if inv_status != 200:
        raise HarnessError(f"refusing cleanup for {pid}: inventory unavailable")
    query = urllib.parse.urlencode({"mode": "hard", "reason": "four-persona-harness-cleanup"})
    del_status, result = _http_json(
        api_base, "DELETE", f"/api/people/{urllib.parse.quote(pid)}?{query}", timeout=90
    )
    if del_status != 200:
        raise HarnessError(f"cleanup failed for {pid}: HTTP {del_status} {result!r}")
    return {"person_id": pid, "inventory": inventory, "result": result}


def _validate_manifest(document: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = document.get("personas") or []
    result: Dict[str, Dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise HarnessError("persona manifest contains a non-object row")
        key = str(raw.get("key") or "").strip()
        kind = str(raw.get("kind") or "").strip()
        if not key or key in result or kind not in {"reference", "synthetic_writable"}:
            raise HarnessError(f"invalid persona manifest row: {raw!r}")
        if kind == "reference" and "product_mutation" not in set(raw.get("forbidden_capabilities") or []):
            raise HarnessError(f"reference persona {key} lacks product_mutation refusal")
        result[key] = dict(raw)
    if set(result) != {"shatner", "dolly", "tomasita", "alex"}:
        raise HarnessError(f"expected the four locked personas, got {sorted(result)}")
    return result


def _select_cases(
    document: Mapping[str, Any],
    selected_personas: set[str],
    case_ids: Optional[set[str]],
    max_cases: Optional[int],
) -> List[Dict[str, Any]]:
    cases = [dict(case) for case in document.get("cases", []) if isinstance(case, dict)]
    cases = [case for case in cases if case.get("persona") in selected_personas]
    if case_ids is not None:
        cases = [case for case in cases if case.get("id") in case_ids]
    if max_cases is not None:
        cases = cases[:max_cases]
    unknown = sorted({str(case.get("persona")) for case in cases} - selected_personas)
    if unknown:
        raise HarnessError(f"case pack contains unselected/unknown personas: {unknown}")
    if not cases:
        raise HarnessError("case selection is empty")
    return cases


def _context_payload(case: Mapping[str, Any], person_id: str) -> Dict[str, Any]:
    context = dict(case.get("context") or {})
    targets = list(context.get("current_target_paths") or [])
    return {
        "person_id": person_id,
        "session_id": f"harness_extract_{case['id']}",
        "answer": case.get("answer") or "",
        "current_section": context.get("current_section"),
        "current_target_path": targets[0] if targets else None,
        "current_target_paths": targets or None,
        "current_era": context.get("current_era"),
        "current_pass": context.get("current_pass") or "pass1",
        "current_mode": context.get("current_mode") or "open",
        "transcript_source": "typed",
    }


def _run_extraction_cases(
    cases: Sequence[Mapping[str, Any]],
    person_rows: Mapping[str, Mapping[str, Any]],
    *,
    mode: str,
    api_base: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        started = time.monotonic()
        method = "offline_mock"
        error = ""
        if mode == "offline":
            items = list(case.get("mockItems") or [])
            status = 200
        else:
            person = person_rows.get(str(case.get("persona")))
            if not person or not person.get("id"):
                # The persona is unavailable in this database (see
                # _find_reference). The case is NOT run and is NOT counted
                # as passing -- it is reported as not applicable, so a gate
                # can never read "all passed" from cases nobody executed.
                results.append({
                    "id": case.get("id"), "persona": case.get("persona"),
                    "applicable": False, "pass": False, "score": None,
                    "method": "not_applicable",
                    "error": "persona unavailable in this database",
                })
                print(f"N/A   {case.get('id')} {case.get('persona')} "
                      "(persona unavailable)")
                continue
            status, body = _http_json(
                api_base, "POST", "/api/extract-fields",
                payload=_context_payload(case, str(person["id"])), timeout=320,
            )
            if status == 200 and isinstance(body, dict):
                items = list(body.get("items") or [])
                method = str(body.get("method") or "unknown")
            else:
                items = []
                method = f"http_{status}"
                error = repr(body)[:300]
        scored = score_case(case, items)
        scored.update({
            "persona": case.get("persona"),
            "cluster": case.get("cluster"),
            "tags": list(case.get("tags") or []),
            "method": method,
            "http_status": status,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error": error,
            "items": [
                {
                    "fieldPath": item.get("fieldPath"),
                    "value": item.get("value"),
                    "confidence": item.get("confidence"),
                    "extractionMethod": item.get("extractionMethod"),
                }
                for item in items if isinstance(item, dict)
            ],
        })
        results.append(scored)
        mark = "PASS" if scored["pass"] else "FAIL"
        print(f"[{index:02d}/{len(cases):02d}] {mark:4s} {case['id']} {case['persona']} "
              f"score={scored['overall_score']:.3f} method={method}")
    return results


def _run_product_reads(
    selected: Sequence[str],
    personas: Mapping[str, Mapping[str, Any]],
    person_rows: Mapping[str, Mapping[str, Any]],
    api_base: str,
    unavailable: Mapping[str, str],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for key in selected:
        row = person_rows.get(key)
        if row is None:
            # An unavailable reference is N/A, not a failure, and the run
            # carries on with the writable synthetic personas.
            results.append({
                "persona": key,
                "kind": personas[key]["kind"],
                "applicable": False,
                "pass": True,
                "reason": unavailable.get(
                    key, "persona not resolved in this database"),
            })
            print(f"N/A   product-read {key} ({personas[key]['kind']})")
            continue
        pid = str(row["id"])
        checks: Dict[str, Any] = {}
        for name, path in (
            ("projection", f"/api/projection?person_id={urllib.parse.quote(pid)}"),
            ("chronology", f"/api/chronology-accordion?person_id={urllib.parse.quote(pid)}"),
            ("sessions", f"/api/sessions/list?person_id={urllib.parse.quote(pid)}"),
        ):
            status, body = _http_json(api_base, "GET", path, timeout=45)
            body_pid = body.get("person_id") if isinstance(body, dict) else None
            checks[name] = {
                "status": status,
                "person_id_match": body_pid in (None, pid),
            }
        passed = all(v["status"] == 200 and v["person_id_match"] for v in checks.values())
        kind = personas[key]["kind"]
        result = {"persona": key, "kind": kind, "applicable": True,
                  "pass": passed, "checks": checks}
        results.append(result)
        print(f"{'PASS' if passed else 'FAIL'} product-read {key} ({kind})")
    return results


def _run_completed_turns(
    selected: Sequence[str],
    personas: Mapping[str, Mapping[str, Any]],
    person_rows: Mapping[str, Mapping[str, Any]],
    api_base: str,
) -> List[Dict[str, Any]]:
    """Exercise the real chat→turn→extraction-result path for writable fixtures.

    The existing operator harness is the stable adapter over chat_ws, so this
    runner does not duplicate the WebSocket protocol.  Reference personas are
    recorded as not-applicable rather than coerced into writable narrators.
    """
    health_status, health = _http_json(
        api_base, "GET", "/api/operator/harness/health", timeout=20
    )
    if health_status != 200:
        raise HarnessError(
            "completed-turn requires HORNELORE_OPERATOR_HARNESS=1 and a restarted stack"
        )
    core = _load_json(CORE_PATH)
    preferred_case = {"tomasita": "xcore_019", "alex": "xcore_030"}
    by_id = {str(case.get("id")): case for case in core.get("cases", [])}
    results: List[Dict[str, Any]] = []
    for key in selected:
        if personas[key]["kind"] == "reference":
            results.append({
                "persona": key,
                "kind": "reference",
                "applicable": False,
                "pass": True,
                "reason": "reference narrators are never used for completed-turn writes",
            })
            print(f"N/A  completed-turn {key} (reference write boundary)")
            continue
        case = by_id[preferred_case[key]]
        pid = str(person_rows[key]["id"])
        session_id = f"product-harness-{uuid.uuid4().hex[:12]}"
        turn_id = f"product-harness-turn-{uuid.uuid4().hex}"
        status, body = _http_json(
            api_base,
            "POST",
            "/api/operator/harness/interview-turn",
            payload={
                "person_id": pid,
                "text": case["answer"],
                "session_style": "oral_history",
                "turn_mode": "interview",
                "turn_id": turn_id,
                "session_id": session_id,
                "timeout_seconds": 240,
            },
            timeout=270,
        )
        turn_ok = status == 200 and isinstance(body, dict) and bool(body.get("ok"))

        pending: List[Dict[str, Any]] = []
        deadline = time.monotonic() + 100.0
        while turn_ok and time.monotonic() < deadline:
            query = urllib.parse.urlencode({"person_id": pid, "session_id": session_id, "limit": 20})
            p_status, p_body = _http_json(
                api_base, "GET", f"/api/extraction-results/pending?{query}", timeout=20
            )
            if p_status == 200 and isinstance(p_body, dict):
                pending = [
                    dict(row) for row in p_body.get("pending", [])
                    if isinstance(row, dict) and row.get("turn_id") == turn_id
                ]
                if pending:
                    break
            time.sleep(0.5)

        extracted_items = list(pending[0].get("items") or []) if len(pending) == 1 else []
        extraction_score = score_case(case, extracted_items)
        session_query = urllib.parse.urlencode({"person_id": pid})
        s_status, s_body = _http_json(
            api_base, "GET", f"/api/sessions/list?{session_query}", timeout=30
        )
        session_rows = []
        if s_status == 200 and isinstance(s_body, dict):
            session_rows = [
                row for row in s_body.get("sessions", [])
                if isinstance(row, dict)
                and str(row.get("id") or row.get("conv_id") or "") == session_id
            ]
        owner_ok = bool(session_rows) and all(
            str(row.get("person_id") or "") == pid for row in session_rows
        )
        truth = body.get("truth_pipeline") if isinstance(body, dict) else None
        truth_called = None if truth is None else bool(truth.get("extract_fields_called"))
        passed = turn_ok and len(pending) == 1 and extraction_score["pass"] and owner_ok
        results.append({
            "persona": key,
            "kind": "synthetic_writable",
            "applicable": True,
            "pass": passed,
            "case_id": case["id"],
            "turn_http_status": status,
            "turn_ok": turn_ok,
            "assistant_reply_present": bool((body or {}).get("assistant_text")) if isinstance(body, dict) else False,
            "question_count": (body or {}).get("question_count") if isinstance(body, dict) else None,
            "db_locked": (body or {}).get("db_locked") if isinstance(body, dict) else None,
            "truth_pipeline_observed": truth is not None,
            "truth_pipeline_extract_called": truth_called,
            "pending_result_count": len(pending),
            "extraction_score": extraction_score,
            "owned_session_found": owner_ok,
            "session_id": session_id,
            "turn_id": turn_id,
        })
        print(f"{'PASS' if passed else 'FAIL'} completed-turn {key} "
              f"pending={len(pending)} extraction={extraction_score['overall_score']:.3f} owner={owner_ok}")
    return results


def _resolve_live_people(
    api_base: str,
    selected: Sequence[str],
    personas: Mapping[str, Mapping[str, Any]],
    run_id: str,
    created_sink: List[Dict[str, Any]],
    unavailable_sink: Dict[str, str],
) -> Dict[str, Dict[str, Any]]:
    listed = _people(api_base)
    resolved: Dict[str, Dict[str, Any]] = {}
    # Resolve every read-only dependency before creating anything. A
    # MISCLASSIFIED or AMBIGUOUS reference still raises here, and it raises
    # before any synthetic row exists -- so a genuine contract violation
    # cannot leave a writable narrator behind.
    #
    # An ABSENT reference no longer raises. It is recorded as unavailable
    # and the run continues with the writable personas, because "this
    # database does not have that reference narrator" is a fact about the
    # database, not a fault in the harness.
    for key in selected:
        persona = personas[key]
        if persona["kind"] == "reference":
            row, status = _find_reference(persona, listed)
            if row is not None:
                resolved[key] = row
            else:
                unavailable_sink[key] = (
                    "reference narrator not present in this database "
                    "(absent or soft-deleted); soft deletion is respected and "
                    "the narrator is NOT recreated"
                )
    for key in selected:
        persona = personas[key]
        if persona["kind"] == "synthetic_writable":
            row = _create_synthetic(api_base, persona, run_id, created_sink)
            resolved[key] = row
    return resolved


def _write_report(report: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(output)


def _print_plan(personas: Mapping[str, Mapping[str, Any]]) -> None:
    print("Four-persona harness plan (no network or writes):")
    for key in ("shatner", "dolly", "tomasita", "alex"):
        row = personas[key]
        print(f"  {key:9s} {row['kind']:19s} capabilities={','.join(row.get('capabilities') or [])}")
    print("\nScenarios:")
    print("  extraction-core       32-case gate; every case must pass")
    print("  extraction-challenge  16-case research pack; failures are findings")
    print("  product-read          projection/chronology/session isolation reads")
    print("  completed-turn        writable chat→ledger→result→owned-session path")
    print("\nLive synthetic narrators are exact-ID cleanup targets; references are never mutated.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=(
            "plan", "extraction-core", "extraction-challenge", "product-read", "completed-turn",
        ),
        default="plan",
    )
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--api", default=os.getenv("HORNELORE_API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--personas", default="shatner,dolly,tomasita,alex")
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--keep-run", action="store_true", help="retain exact synthetic run rows for inspection")
    parser.add_argument("--strict-challenge", action="store_true", help="make challenge failures nonzero")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    personas = _validate_manifest(_load_json(PERSONAS_PATH))
    selected = [part.strip() for part in args.personas.split(",") if part.strip()]
    unknown = sorted(set(selected) - set(personas))
    if unknown:
        raise HarnessError(f"unknown personas: {unknown}")
    if args.scenario == "plan":
        _print_plan(personas)
        return 0

    if args.scenario in {"product-read", "completed-turn"} and args.mode != "live":
        raise HarnessError(f"{args.scenario} requires --mode live")

    run_id = uuid.uuid4().hex[:10]
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    person_rows: Dict[str, Dict[str, Any]] = {}
    created: List[Dict[str, Any]] = []
    cleanup: List[Dict[str, Any]] = []
    cleanup_errors: List[str] = []
    diag: Any = None
    unavailable: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    runtime_error = ""

    try:
        if args.mode == "live":
            ping_status, _ = _http_json(args.api, "GET", "/api/ping", timeout=10)
            if ping_status != 200:
                raise HarnessError(f"stack ping failed: HTTP {ping_status}")
            resolve_selected = selected
            if args.scenario == "completed-turn":
                # References are deliberately N/A for this write-path scenario;
                # their absence from a developer DB must not block writable
                # synthetic coverage or tempt anyone to create a writable copy.
                resolve_selected = [
                    key for key in selected
                    if personas[key]["kind"] == "synthetic_writable"
                ]
            person_rows = _resolve_live_people(
                args.api, resolve_selected, personas, run_id, created,
                unavailable,
            )
            diag_status, diag_body = _http_json(args.api, "GET", "/api/extract-diag", timeout=20)
            diag = diag_body if diag_status == 200 else {"http_status": diag_status}

        if args.scenario == "product-read":
            results = _run_product_reads(
                selected, personas, person_rows, args.api, unavailable,
            )
            # Three states, counted apart. `total` is the APPLICABLE total,
            # so a run whose references are unavailable reports what it
            # actually exercised instead of quietly shrinking its own
            # denominator to look complete.
            applicable = [row for row in results if row.get("applicable")]
            summary = {
                "total": len(applicable),
                "passed": sum(1 for row in applicable if row["pass"]),
                "failed": sum(1 for row in applicable if not row["pass"]),
                "not_applicable": len(results) - len(applicable),
            }
        elif args.scenario == "completed-turn":
            results = _run_completed_turns(selected, personas, person_rows, args.api)
            applicable = [row for row in results if row.get("applicable")]
            summary = {
                "total": len(applicable),
                "passed": sum(1 for row in applicable if row["pass"]),
                "failed": sum(1 for row in applicable if not row["pass"]),
                "not_applicable": len(results) - len(applicable),
            }
        else:
            pack_path = CORE_PATH if args.scenario == "extraction-core" else CHALLENGE_PATH
            pack = _load_json(pack_path)
            cases = _select_cases(
                pack, set(selected),
                {part.strip() for part in args.case_ids.split(",") if part.strip()} or None,
                args.max_cases,
            )
            results = _run_extraction_cases(
                cases, person_rows, mode=args.mode, api_base=args.api,
            )
            applicable = [row for row in results if row.get("applicable", True)]
            summary = summarize(applicable)
            summary["not_applicable"] = len(results) - len(applicable)
            summary["gate"] = bool(pack.get("gate"))
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
    finally:
        if args.mode == "live" and created and not args.keep_run:
            for row in reversed(created):
                try:
                    cleanup.append(_delete_exact_synthetic(args.api, row))
                except Exception as exc:
                    cleanup_errors.append(f"{row.get('id')}: {type(exc).__name__}: {exc}")

    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "scenario": args.scenario,
        "mode": args.mode,
        "selected_personas": selected,
        "resolved_people": {
            key: {
                "person_id": row.get("id"),
                "display_name": row.get("display_name"),
                "kind": personas[key]["kind"],
            }
            for key, row in person_rows.items()
        },
        "server_extract_diag": diag,
        "summary": summary,
        "results": results,
        "reference_personas_unavailable": dict(unavailable),
        "synthetic_rows_created": [row.get("id") for row in created],
        "synthetic_cleanup": cleanup,
        "synthetic_cleanup_errors": cleanup_errors,
        "kept_for_inspection": bool(args.keep_run and created),
        "runtime_error": runtime_error,
    }
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or REPORT_DIR / f"narrator_product_harness_{args.scenario}_{run_id}_{stamp}.json"
    _write_report(report, output)
    print(f"\nReport: {output}")
    if summary:
        line = f"Summary: {summary.get('passed', 0)}/{summary.get('total', 0)} passed"
        if summary.get("not_applicable"):
            line += f", {summary['not_applicable']} not applicable"
        print(line)
    for key, reason in unavailable.items():
        print(f"N/A   persona {key}: {reason}")
    if runtime_error:
        print(f"RUNTIME ERROR: {runtime_error}", file=sys.stderr)
    if cleanup_errors:
        print("CLEANUP ERROR: exact synthetic run rows remain; see report", file=sys.stderr)
    if runtime_error or cleanup_errors:
        return 2
    failed = int(summary.get("failed", 0))
    if args.scenario == "extraction-core" and failed:
        return 1
    if args.scenario == "extraction-challenge" and args.strict_challenge and failed:
        return 1
    if args.scenario in {"product-read", "completed-turn"} and failed:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
