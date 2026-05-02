#!/usr/bin/env python3
"""WO-EX-UTTERANCE-FRAME-SURVEY-01 — dedicated Story Clause Map survey harness.

Purpose
-------
Evaluate WO-EX-UTTERANCE-FRAME-01 Phase 0-2 without wiring any consumers.
This harness pairs three things:

  1. A traffic-generator report, usually golfball JSON.
  2. The direct deterministic build_frame(user_text) output.
  3. The live [utterance-frame] log lines emitted by chat_ws when
     HORNELORE_UTTERANCE_FRAME_LOG=1.

It scores the frame layer only. It does NOT judge Lori pass/fail, does NOT
call the LLM, does NOT write DB, does NOT alter runtime behavior, and does
NOT wire extractor/Lori/validator/safety/UI consumers.

Typical use from repo root:

    python3 scripts/archive/run_utterance_frame_survey.py \
      --golfball-report docs/reports/golfball-utterance-frame-log-v1.json \
      --api-log .runtime/logs/api.log \
      --output docs/reports/utterance_frame_survey_v1.json \
      --include-probes

Exit codes:
  0 = report generated; GREEN/AMBER findings are survey information
  1 = RED status if --strict is passed
  2 = bad inputs / unable to import frame builder / malformed report
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


LOG_RX = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+)\s+"
    r"\[[^\]]+\]\s+INFO:\s+\[utterance-frame\]\s+"
    r"conv=(?P<conv>\S+)\s+"
    r"narrator=(?P<narrator>\S+)\s+"
    r"conf=(?P<conf>\S+)\s+"
    r"clauses=(?P<clauses>\d+)\s+"
    r"unbound=(?P<unbound>\S+)\s+"
    r"shape=(?P<shape>.*)$"
)


@dataclass
class SurveyFinding:
    severity: str  # info | polish | amber | red
    code: str
    message: str
    turn_name: Optional[str] = None
    recommended_patch: Optional[str] = None


@dataclass
class ParsedLogEntry:
    line_number: int
    timestamp: str
    conv_id: str
    narrator_id: str
    parse_confidence: str
    clause_count: int
    unbound: str
    shape_raw: str
    clauses: List[Dict[str, Any]]
    raw_line: str


def repo_root_from_script() -> Path:
    """Assume this file lives at scripts/archive/<this>.py.
    Fallback to cwd when run from elsewhere."""
    here = Path(__file__).resolve()
    try:
        if here.parent.name == "archive" and here.parent.parent.name == "scripts":
            return here.parents[2]
    except IndexError:
        pass
    return Path.cwd().resolve()


def add_server_code_to_path(repo_root: Path) -> None:
    server_code = repo_root / "server" / "code"
    if str(server_code) not in sys.path:
        sys.path.insert(0, str(server_code))


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def parse_shape(shape: str) -> List[Dict[str, Any]]:
    clauses: List[Dict[str, Any]] = []
    if not shape or shape.strip() == "-":
        return clauses
    for raw_seg in shape.split(";"):
        seg = raw_seg.strip()
        if not seg:
            continue
        parts = seg.split("|")
        base = parts[0]
        m = re.match(r"(?P<subject>[^/]+)/(?P<event>[^@]+)@(?P<place>.*)", base)
        clause: Dict[str, Any] = {"raw_shape": seg}
        if m:
            clause.update(
                subject_class=m.group("subject"),
                event_class=m.group("event"),
                place=None if m.group("place") in ("", "-") else m.group("place"),
            )
        else:
            clause.update(subject_class=None, event_class=None, place=None)
        for field in parts[1:]:
            if "=" not in field:
                continue
            k, v = field.split("=", 1)
            v = v.strip()
            if k in ("neg", "unc"):
                clause[k] = v in ("1", "true", "True")
            elif k == "hints":
                clause[k] = [] if v in ("", "-") else [x for x in v.split(",") if x]
            else:
                clause[k] = None if v in ("", "-") else v
        clause.setdefault("neg", False)
        clause.setdefault("unc", False)
        clause.setdefault("hints", [])
        clauses.append(clause)
    return clauses


def parse_utterance_frame_logs(api_log: Path) -> List[ParsedLogEntry]:
    entries: List[ParsedLogEntry] = []
    if not api_log.is_file():
        return entries
    with api_log.open(encoding="utf-8", errors="replace") as fp:
        for idx, line in enumerate(fp, start=1):
            m = LOG_RX.search(line.rstrip("\n"))
            if not m:
                continue
            entries.append(
                ParsedLogEntry(
                    line_number=idx,
                    timestamp=m.group("ts"),
                    conv_id=m.group("conv"),
                    narrator_id=m.group("narrator"),
                    parse_confidence=m.group("conf"),
                    clause_count=int(m.group("clauses")),
                    unbound=m.group("unbound"),
                    shape_raw=m.group("shape"),
                    clauses=parse_shape(m.group("shape")),
                    raw_line=line.rstrip("\n"),
                )
            )
    return entries


def select_conv_id(
    entries: List[ParsedLogEntry],
    *,
    person_id: Optional[str],
    requested_conv_id: Optional[str],
    expected_turn_count: int,
) -> Optional[str]:
    if requested_conv_id:
        return requested_conv_id
    filtered = [e for e in entries if (not person_id or e.narrator_id == person_id)]
    if not filtered:
        return None
    grouped: Dict[str, List[ParsedLogEntry]] = defaultdict(list)
    for e in filtered:
        grouped[e.conv_id].append(e)
    candidates = sorted(
        grouped.items(),
        key=lambda kv: (len(kv[1]) >= expected_turn_count, len(kv[1]), kv[1][-1].line_number),
        reverse=True,
    )
    return candidates[0][0] if candidates else None


def norm(s: Any) -> str:
    return str(s or "").strip().lower()


def direct_clauses(frame_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(frame_dict.get("clauses") or [])


def live_to_common_clause(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "who_subject_class": c.get("subject_class"),
        "event_class": c.get("event_class"),
        "place": c.get("place"),
        "negation": bool(c.get("neg")),
        "uncertainty": bool(c.get("unc")),
        "candidate_fieldPaths": list(c.get("hints") or []),
        "object": c.get("obj"),
        "feeling": c.get("feel"),
        "raw_shape": c.get("raw_shape"),
    }


def frame_has_clause(
    clauses: Iterable[Dict[str, Any]],
    *,
    subject: Optional[str] = None,
    event: Optional[str] = None,
    place: Optional[str] = None,
    hint: Optional[str] = None,
    negation: Optional[bool] = None,
    any_feeling_in: Optional[List[str]] = None,
) -> bool:
    for c in clauses:
        if subject is not None and norm(c.get("who_subject_class")) != norm(subject):
            continue
        if event is not None and norm(c.get("event_class")) != norm(event):
            continue
        if place is not None and norm(c.get("place")) != norm(place):
            continue
        if hint is not None and hint not in (c.get("candidate_fieldPaths") or []):
            continue
        if negation is not None and bool(c.get("negation")) != negation:
            continue
        if any_feeling_in is not None:
            feeling = norm(c.get("feeling"))
            if feeling not in [norm(x) for x in any_feeling_in]:
                continue
        return True
    return False


def any_clause_place(clauses: Iterable[Dict[str, Any]], place: str) -> bool:
    return any(norm(c.get("place")) == norm(place) for c in clauses)


def any_clause_object(clauses: Iterable[Dict[str, Any]], obj: str) -> bool:
    return any(norm(c.get("object")) == norm(obj) for c in clauses)


def any_clause_feeling(clauses: Iterable[Dict[str, Any]], feelings: List[str]) -> bool:
    wanted = {norm(f) for f in feelings}
    return any(norm(c.get("feeling")) in wanted for c in clauses)


def hints_empty_for_negated(clauses: Iterable[Dict[str, Any]]) -> bool:
    for c in clauses:
        if bool(c.get("negation")) and (c.get("candidate_fieldPaths") or []):
            return False
    return True


def evaluate_known_turn(
    turn_name: str,
    user_text: str,
    direct: Dict[str, Any],
    live_entry: Optional[ParsedLogEntry],
) -> Tuple[str, List[SurveyFinding], List[str]]:
    """Return result, findings, notes for known golfball turns."""
    findings: List[SurveyFinding] = []
    notes: List[str] = []
    dclauses = direct_clauses(direct)
    lclauses = [live_to_common_clause(c) for c in live_entry.clauses] if live_entry else []
    result = "PASS"

    def add(sev: str, code: str, msg: str, patch: Optional[str] = None) -> None:
        nonlocal result
        findings.append(SurveyFinding(sev, code, msg, turn_name, patch))
        if sev == "red":
            result = "FAIL_RED"
        elif sev in ("amber", "polish") and result == "PASS":
            result = "PASS_WITH_NOTE" if sev == "polish" else "AMBER"

    if live_entry is None:
        add("red", "missing_live_frame_log", "No [utterance-frame] log paired to this turn.")
        return result, findings, notes

    if turn_name == "01_identity_dob_place":
        if frame_has_clause(dclauses, subject="self", event="birth", place="Montreal", hint="personal.placeOfBirth"):
            notes.append("Direct frame captured self/birth@Montreal with place-of-birth hint.")
        else:
            add("amber", "identity_birth_frame_miss", "Direct frame did not capture self/birth@Montreal + personal.placeOfBirth.")
        if not frame_has_clause(dclauses, subject="self", event="birth", hint="personal.dateOfBirth"):
            add("polish", "date_hint_miss", "Birthdate hint personal.dateOfBirth missing for identity DOB turn.")

    elif turn_name == "02_story_scene_anchor_canonical":
        if frame_has_clause(dclauses, subject="self", event="illness", place="Spokane"):
            notes.append("Direct frame split self illness in Spokane.")
        else:
            add("amber", "self_illness_spokane_miss", "Direct frame missed self/illness@Spokane.")
        if frame_has_clause(dclauses, subject="parent", event="work", hint="parents.occupation"):
            notes.append("Direct frame split parent work with parents.occupation hint.")
        else:
            add("amber", "parent_work_hint_miss", "Direct frame missed parent/work with parents.occupation hint.")
        if any(norm(c.get("place")) == "plant" for c in dclauses + lclauses):
            add("polish", "generic_work_place_plant", "Work clause shows place=plant; survey should prefer object=aluminum plant or expose object in log.", "Prefer object/feeling in log first; parser polish later if needed.")
        if any_clause_object(dclauses, "aluminum plant") and "obj=" not in live_entry.shape_raw:
            add("polish", "object_not_visible_in_log_summary", "Direct frame has object=aluminum plant but live log summary does not expose object.", "Add obj=... to [utterance-frame] shape summary.")

    elif turn_name == "03_story_scene_anchor_lowercase":
        if "spokane" in user_text.lower() and not any_clause_place(dclauses, "Spokane"):
            add("amber", "lowercase_place_miss", "Lowercase spokane appears in narrator text but direct frame did not capture place=Spokane.", "Add known-place lowercase alias fallback for Spokane/Stanley/Mandan/Bismarck/etc.")
        if frame_has_clause(dclauses, subject="parent", event="work", hint="parents.occupation"):
            notes.append("Direct frame captured parent/work despite lowercase STT-style input.")
        else:
            add("amber", "lowercase_parent_work_miss", "Lowercase STT-style dad/work sentence did not map to parent/work + parents.occupation.")
        if any(norm(c.get("place")) == "plant" for c in dclauses + lclauses):
            add("polish", "generic_work_place_plant", "Lowercase work turn shows place=plant; likely should surface object=aluminum plant.", "Add obj=... to log and consider place/object preference.")

    elif turn_name == "04_career_role_no_anchor":
        if frame_has_clause(dclauses, subject="self", event="work", hint="education.earlyCareer"):
            notes.append("Direct frame captured self/work career-role hint.")
        else:
            add("amber", "career_work_hint_miss", "Career-role turn did not capture self/work + education.earlyCareer.")
        if len(dclauses) > 1:
            notes.append("Multiple clauses/unknown clauses are acceptable for role lists in Phase 0-2.")

    elif turn_name == "05_safety_soft_trigger":
        if frame_has_clause(dclauses, subject="self", event="illness", negation=True):
            notes.append("Direct frame captured self/illness with negation flag.")
        else:
            add("red", "passive_death_wish_signal_miss", "Passive-death-wish turn did not capture self/illness + negation.")
        if not hints_empty_for_negated(dclauses):
            add("red", "negated_clause_emitted_field_hints", "Negated clause emitted candidate field hints; should be empty.")
        if any(c.get("candidate_fieldPaths") for c in dclauses if c.get("negation")):
            add("red", "negation_hint_leak", "Negated clause leaked field hints.")

    elif turn_name == "07_post_safety_recovery":
        if "tired" in user_text.lower() or "scared" in user_text.lower():
            if any_clause_feeling(dclauses, ["tired", "scared"]):
                notes.append("Direct frame captured stated feeling tired/scared.")
            else:
                add("amber", "stated_feeling_miss_tired_scared", "Narrator stated tired/scared, but direct frame did not expose feeling.", "Extend affect canon or frame feeling pattern for tired/scared if values-aligned.")
            if live_entry and "feel=" not in live_entry.shape_raw:
                add("polish", "feeling_not_visible_in_log_summary", "Live log shape does not include feel=..., so survey cannot see feelings from logs.", "Add feel=... to [utterance-frame] shape summary.")

    elif turn_name == "08_softened_persistence":
        notes.append("Thank-you turn is low-signal; no frame finding unless it fails to log.")

    else:
        notes.append("No hard-coded expected shape for this turn; direct/live frames recorded for survey.")

    return result, findings, notes


PROBES: List[Dict[str, Any]] = [
    {
        "name": "probe_lowercase_spokane_dad_work",
        "user_text": "when i was young in spokane my dad worked nights at the aluminum plant",
        "purpose": "Missed in golfball T03: lowercase place + parent work + aluminum plant.",
    },
    {
        "name": "probe_aluminum_plant_object",
        "user_text": "My dad worked nights at the aluminum plant.",
        "purpose": "Check whether aluminum plant is available as object/anchor rather than generic plant.",
    },
    {
        "name": "probe_tired_scared_feeling",
        "user_text": "I am still here. I just feel tired and scared.",
        "purpose": "Missed in golfball T07: stated feelings should be visible to later softened/HITL consumers.",
    },
    {
        "name": "probe_lowercase_birth_stanley",
        "user_text": "my dad was born in stanley, and i was born in stanley too.",
        "purpose": "Lowercase STT-style version of case_111.",
    },
]


def evaluate_probe(name: str, user_text: str, direct: Dict[str, Any]) -> Tuple[str, List[SurveyFinding], List[str]]:
    findings: List[SurveyFinding] = []
    notes: List[str] = []
    dclauses = direct_clauses(direct)
    result = "PASS"

    def add(sev: str, code: str, msg: str, patch: Optional[str] = None) -> None:
        nonlocal result
        findings.append(SurveyFinding(sev, code, msg, name, patch))
        if sev == "red":
            result = "FAIL_RED"
        elif sev in ("amber", "polish") and result == "PASS":
            result = "AMBER" if sev == "amber" else "PASS_WITH_NOTE"

    lower = user_text.lower()
    if "spokane" in lower and not any_clause_place(dclauses, "Spokane"):
        add("amber", "lowercase_place_miss", "Probe contains lowercase spokane but frame did not capture place=Spokane.", "Known-place lowercase alias fallback.")
    if "stanley" in lower and not any_clause_place(dclauses, "Stanley"):
        add("amber", "lowercase_place_miss", "Probe contains lowercase stanley but frame did not capture place=Stanley.", "Known-place lowercase alias fallback.")
    if "aluminum plant" in lower:
        if any_clause_object(dclauses, "aluminum plant"):
            notes.append("Direct frame exposes object=aluminum plant.")
        else:
            add("amber", "aluminum_plant_object_miss", "Probe contains aluminum plant but object slot did not expose it.", "Add/verify aluminum plant object pattern.")
        if any(norm(c.get("place")) == "plant" for c in dclauses):
            add("polish", "generic_work_place_plant", "Probe frame uses generic place=plant.", "Prefer object=aluminum plant in log; consider place preference later.")
    if "tired" in lower or "scared" in lower:
        if any_clause_feeling(dclauses, ["tired", "scared"]):
            notes.append("Direct frame exposes stated feeling.")
        else:
            add("amber", "stated_feeling_miss_tired_scared", "Probe contains tired/scared but frame did not expose feeling.", "Extend stated-feeling detection if consistent with no-therapy rule.")
    if "do not want to be alive" in lower:
        if not frame_has_clause(dclauses, subject="self", event="illness", negation=True):
            add("red", "passive_death_wish_signal_miss", "Passive death wish probe missed self/illness + negation.")
    return result, findings, notes


def write_console(console_path: Path, lines: List[str]) -> None:
    console_path.parent.mkdir(parents=True, exist_ok=True)
    console_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Survey WO-EX-UTTERANCE-FRAME-01 Phase 0-2 output.")
    parser.add_argument("--golfball-report", default="docs/reports/golfball-utterance-frame-log-v1.json")
    parser.add_argument("--api-log", default=".runtime/logs/api.log")
    parser.add_argument("--conv-id", default=None, help="Optional conv id; auto-detected by person_id when omitted.")
    parser.add_argument("--output", default="docs/reports/utterance_frame_survey_v1.json")
    parser.add_argument("--console-output", default=None)
    parser.add_argument("--include-probes", action="store_true", help="Run targeted direct build_frame probes for known misses.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on RED status.")
    args = parser.parse_args(argv)

    repo_root = repo_root_from_script()
    add_server_code_to_path(repo_root)

    try:
        from api.services.utterance_frame import build_frame  # type: ignore
    except Exception as exc:
        print(f"ERROR: could not import api.services.utterance_frame.build_frame: {exc}", file=sys.stderr)
        return 2

    report_path = (repo_root / args.golfball_report).resolve() if not Path(args.golfball_report).is_absolute() else Path(args.golfball_report)
    api_log_path = (repo_root / args.api_log).resolve() if not Path(args.api_log).is_absolute() else Path(args.api_log)
    output_path = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    console_path = Path(args.console_output) if args.console_output else output_path.with_suffix(".console.txt")
    if not console_path.is_absolute():
        console_path = (repo_root / console_path).resolve()

    try:
        golf = load_json(report_path)
    except Exception as exc:
        print(f"ERROR: could not read golfball report {report_path}: {exc}", file=sys.stderr)
        return 2

    turns = list(golf.get("turns") or [])
    person_id = golf.get("person_id")
    log_entries_all = parse_utterance_frame_logs(api_log_path)
    selected_conv = select_conv_id(
        log_entries_all,
        person_id=person_id,
        requested_conv_id=args.conv_id,
        expected_turn_count=len(turns),
    )
    log_entries = [e for e in log_entries_all if e.conv_id == selected_conv] if selected_conv else []
    if person_id:
        log_entries = [e for e in log_entries if e.narrator_id == person_id]

    all_findings: List[SurveyFinding] = []
    turn_reports: List[Dict[str, Any]] = []

    for idx, turn in enumerate(turns):
        user_text = turn.get("user_text") or ""
        turn_name = turn.get("name") or f"turn_{idx+1:02d}"
        try:
            frame = build_frame(user_text).to_dict()
            builder_error = None
        except Exception as exc:  # should never happen; report RED if it does
            frame = {}
            builder_error = repr(exc)
        live = log_entries[idx] if idx < len(log_entries) else None
        if builder_error:
            findings = [SurveyFinding("red", "direct_builder_error", builder_error, turn_name)]
            result = "FAIL_RED"
            notes: List[str] = []
        else:
            result, findings, notes = evaluate_known_turn(turn_name, user_text, frame, live)
        all_findings.extend(findings)
        turn_reports.append({
            "turn_index": idx + 1,
            "turn_name": turn_name,
            "user_text": user_text,
            "direct_frame": frame,
            "live_log": asdict(live) if live else None,
            "result": result,
            "findings": [asdict(f) for f in findings],
            "notes": notes,
            "lori_harness_passed": turn.get("passed"),
            "lori_harness_failures": turn.get("failures", []),
        })

    probe_reports: List[Dict[str, Any]] = []
    if args.include_probes:
        for probe in PROBES:
            try:
                frame = build_frame(probe["user_text"]).to_dict()
                builder_error = None
            except Exception as exc:
                frame = {}
                builder_error = repr(exc)
            if builder_error:
                findings = [SurveyFinding("red", "direct_builder_error", builder_error, probe["name"])]
                result = "FAIL_RED"
                notes = []
            else:
                result, findings, notes = evaluate_probe(probe["name"], probe["user_text"], frame)
            all_findings.extend(findings)
            probe_reports.append({
                "name": probe["name"],
                "purpose": probe["purpose"],
                "user_text": probe["user_text"],
                "direct_frame": frame,
                "result": result,
                "findings": [asdict(f) for f in findings],
                "notes": notes,
            })

    red_count = sum(1 for f in all_findings if f.severity == "red")
    amber_count = sum(1 for f in all_findings if f.severity == "amber")
    polish_count = sum(1 for f in all_findings if f.severity == "polish")
    missing_logs = max(0, len(turns) - len(log_entries))
    live_logs_found = min(len(turns), len(log_entries))
    if missing_logs:
        red_count += missing_logs
        all_findings.append(SurveyFinding("red", "missing_frame_logs", f"Missing {missing_logs} live frame logs for paired golfball turns."))

    db_lock_delta = None
    if golf.get("db_lock_events_baseline") is not None and golf.get("db_lock_events_final") is not None:
        db_lock_delta = int(golf["db_lock_events_final"]) - int(golf["db_lock_events_baseline"])
        if db_lock_delta != 0:
            all_findings.append(SurveyFinding("red", "db_lock_delta_nonzero", f"DB lock delta was {db_lock_delta}; expected 0."))
            red_count += 1

    if red_count:
        status = "RED"
    elif amber_count:
        status = "AMBER_WITH_POLISH"
    elif polish_count:
        status = "GREEN_WITH_POLISH"
    else:
        status = "GREEN"

    finding_counts: Dict[str, int] = defaultdict(int)
    for f in all_findings:
        finding_counts[f.code] += 1

    payload = {
        "run_id": "utterance-frame-survey-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "source_report": str(report_path),
        "api_log": str(api_log_path),
        "person_id": person_id,
        "conv_id": selected_conv,
        "summary": {
            "status": status,
            "turns_seen": len(turns),
            "live_frame_logs_found": live_logs_found,
            "missing_frame_logs": missing_logs,
            "direct_builder_errors": sum(1 for t in turn_reports if t["result"] == "FAIL_RED" and any(f["code"] == "direct_builder_error" for f in t["findings"])),
            "db_lock_delta": db_lock_delta,
            "finding_counts": dict(sorted(finding_counts.items())),
            "red_count": red_count,
            "amber_count": amber_count,
            "polish_count": polish_count,
        },
        "findings": [asdict(f) for f in all_findings],
        "turns": turn_reports,
        "probes": probe_reports,
        "rules": {
            "green": "all turns have live logs, no build errors, db_lock_delta=0, no frame red/amber findings",
            "amber": "logs exist but frame misses survey anchors such as lowercase places or stated feelings",
            "red": "missing frame logs, build exceptions, invented/negated field hints, or db_lock_delta != 0",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    console: List[str] = []
    console.append("=" * 72)
    console.append("Utterance Frame Survey Harness")
    console.append("=" * 72)
    console.append(f"status:              {status}")
    console.append(f"source_report:       {report_path}")
    console.append(f"api_log:             {api_log_path}")
    console.append(f"person_id:           {person_id}")
    console.append(f"conv_id:             {selected_conv}")
    console.append(f"turns_seen:          {len(turns)}")
    console.append(f"live_frame_logs:     {live_logs_found}/{len(turns)}")
    console.append(f"db_lock_delta:       {db_lock_delta}")
    console.append("")
    console.append("Findings:")
    if not finding_counts:
        console.append("  none")
    else:
        for code, count in sorted(finding_counts.items()):
            console.append(f"  {code}: {count}")
    console.append("")
    console.append("Per-turn results:")
    for tr in turn_reports:
        console.append(f"  {tr['result']:<15} {tr['turn_name']}")
        for f in tr["findings"]:
            console.append(f"    - {f['severity']}:{f['code']} — {f['message']}")
    if probe_reports:
        console.append("")
        console.append("Probe results:")
        for pr in probe_reports:
            console.append(f"  {pr['result']:<15} {pr['name']}")
            for f in pr["findings"]:
                console.append(f"    - {f['severity']}:{f['code']} — {f['message']}")
    console.append("")
    console.append(f"report written:      {output_path}")
    console.append(f"console written:     {console_path}")

    write_console(console_path, console)
    print("\n".join(console))

    if args.strict and status == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
