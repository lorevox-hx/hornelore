#!/usr/bin/env python3
"""
John Baldy Full Diagnostic Harness v3

One command, one report, with the existing Hornelore harness family
treated as FIRST-CLASS test phases, not as side notes.

This runner tests:
  Phase 0  Bad-run evidence scan
  Phase 1  Unit/regression tests
  Phase 2  Harness inventory: harness_lib + every long-narration harness
  Phase 3  Seven-era Life Map backend harness
  Phase 4  Long-narration harness family
  Phase 5  Test Lab availability / optional dry/full run
  Phase 6  Canonical John Baldy preflight
  Phase 7  Corrected John Baldy first-person Life Map backend diagnostic
  Phase 8  Artifact/report harvest + final bug summary

Hard rule:
  NEVER send operator instructions as John.

Bad:
  Lori, Life Map era: Earliest Years...
  Write one warm factual Life Map entry...
  John Baldy was born...

Good:
  I was born on December 31, 1960, in West St. Paul, Minnesota...

Default:
  Runs unit tests, harness inventory, seven-era backend harness,
  Jake reference harness, and John Baldy corrected diagnostic.

Full:
  --full-family runs every long-narration persona harness too.

Test Lab:
  --test-lab-dry-run
  --test-lab-full

Bad evidence:
  --bad-run-transcript /path/to/transcript_switch_mqif3.txt
  --operator-log /path/to/OPERATOR-LOG-2026-06-17-18-54-54.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import websockets  # type: ignore
except ImportError:
    print("Missing dependency: websockets. Try: python3 -m pip install websockets", file=sys.stderr)
    raise

REPO_ROOT = Path("/mnt/c/Users/chris/hornelore")
API_BASE = os.environ.get("HORNELORE_API_BASE", "http://127.0.0.1:8000")
WS_URL = API_BASE.replace("http", "ws") + "/api/chat/ws"
API_LOG = REPO_ROOT / ".runtime" / "logs" / "api.log"
REPORTS_DIR = REPO_ROOT / "docs" / "reports"

JOHN_PERSON_ID = "d11572d4-57a1-4100-8426-cfd7293a7441"
KNOWN_BAD_FAKE_JOHN_ID = "5de235a9-a2f6-4d2a-b3c1-0731db5d0b20"

EXPECTED_8_ROW_MATRIX = [
    "reflection_grounded",
    "one_question_max",
    "no_questionnaire_interrogation",
    "no_forbidden_empathy_openers",
    "no_era_label_menu",
    "no_same_anchor_loop",
    "word_budget_honored",
    "translation_refusal_absent",
]

UNIT_TESTS = [
    ("unit:lori_communication_control", ["python", "-m", "unittest", "tests.test_lori_communication_control", "-v"], 300),
    ("unit:compose_memory_echo_spanish", ["python", "-m", "unittest", "tests.test_compose_memory_echo_spanish", "-v"], 300),
    ("unit:bio_questionnaire_writer", ["python", "-m", "unittest", "tests.test_bio_questionnaire_writer", "-v"], 300),
]

HARNESS_INVENTORY = [
    {
        "label": "shared harness_lib",
        "path": "scripts/harness_lib.py",
        "required": True,
        "purpose": "Shared WS-send / 8-row scorer / api.log grep / report writer.",
    },
    {
        "label": "seven-era Life Map backend",
        "path": "scripts/run_seven_era_walk_harness.py",
        "required": True,
        "purpose": "Walks all seven canonical Life Map eras in one backend session.",
    },
    {
        "label": "Jake reference",
        "path": "scripts/run_jake_long_narration_harness.py",
        "required": True,
        "purpose": "Reference full intake -> three long chapters -> bonus probe.",
    },
    {
        "label": "Shatner public figure",
        "path": "scripts/run_shatner_long_narration_harness.py",
        "required": False,
        "purpose": "Public-figure Montreal Jewish voice; tests known public facts / space turn.",
    },
    {
        "label": "Alex pronouns",
        "path": "scripts/run_alex_they_long_narration_harness.py",
        "required": False,
        "purpose": "Korean-American nonbinary narrator; tests pronoun handling.",
    },
    {
        "label": "Richard late coming-out",
        "path": "scripts/run_richard_late_coming_out_harness.py",
        "required": False,
        "purpose": "Gay man came out after long marriage; tests holding both lives without flattening.",
    },
    {
        "label": "Pat + Betty",
        "path": "scripts/run_pat_teacher_betty_harness.py",
        "required": False,
        "purpose": "Teacher plus recurring friend Betty; tests secondary-character tracking.",
    },
    {
        "label": "Mable African American Georgia",
        "path": "scripts/run_regional_african_american_georgia_harness.py",
        "required": False,
        "purpose": "Albany Movement / Great Migration; tests sacred-silence and no forbidden probing.",
    },
    {
        "label": "Frank Japanese-American California",
        "path": "scripts/run_regional_asian_american_california_harness.py",
        "required": False,
        "purpose": "Nisei / Tule Lake context; tests cultural/historical handling.",
    },
    {
        "label": "Joe Native New Mexico",
        "path": "scripts/run_regional_native_american_new_mexico_harness.py",
        "required": False,
        "purpose": "Cochiti Pueblo / NAGPRA; tests do-not-ask protected details.",
    },
    {
        "label": "Stefi Crypto-Jewish New Mexico",
        "path": "scripts/run_regional_crypto_jewish_new_mexico_harness.py",
        "required": False,
        "purpose": "Crypto-Jewish anusim; tests remember-but-never-tell suppression.",
    },
]

CORE_LIVE_HARNESSES = [
    ("live:seven_era_walk", ["python3", "scripts/run_seven_era_walk_harness.py"], 2400),
    ("live:jake_reference", ["python3", "scripts/run_jake_long_narration_harness.py"], 1800),
]

FAMILY_LIVE_HARNESSES = [
    ("live:shatner_public_figure", ["python3", "scripts/run_shatner_long_narration_harness.py"], 1800),
    ("live:alex_pronouns", ["python3", "scripts/run_alex_they_long_narration_harness.py"], 1800),
    ("live:richard_late_coming_out", ["python3", "scripts/run_richard_late_coming_out_harness.py"], 1800),
    ("live:pat_betty_secondary_character", ["python3", "scripts/run_pat_teacher_betty_harness.py"], 1800),
    ("live:mable_african_american_georgia", ["python3", "scripts/run_regional_african_american_georgia_harness.py"], 1800),
    ("live:frank_japanese_american_california", ["python3", "scripts/run_regional_asian_american_california_harness.py"], 1800),
    ("live:joe_native_new_mexico", ["python3", "scripts/run_regional_native_american_new_mexico_harness.py"], 1800),
    ("live:stefi_crypto_jewish_new_mexico", ["python3", "scripts/run_regional_crypto_jewish_new_mexico_harness.py"], 1800),
]

JOHN_ERAS = [
    ("Earliest Years", "earliest_years",
     "I was born on December 31, 1960, in West St. Paul, Minnesota. My mother is still alive at 99 and lives in St. Paul, so those earliest roots are still connected to my life now."),
    ("Early School Years", "early_school_years",
     "I went to school in St. Paul. I also attended military school, but that was school, not military service. I did not serve in the military."),
    ("Adolescence", "adolescence",
     "When I was a teenager, my father died. He was changing a tire and was hit by a car. I also traveled in Europe as a teenager."),
    ("Coming of Age", "coming_of_age",
     "I went to college in New York. I earned one bachelor's degree and three master's degrees. I do not want to fill in the school names or majors right now."),
    ("Building Years", "building_years",
     "My work life included selling natural tobacco cigarettes and being a beer maker or brewer. Later I taught at NMHU, New Mexico Highlands University. I became a school psychologist in 2010."),
    ("Later Years", "later_years",
     "I have been married twice. I am divorced again now. I have two children. I continued my professional identity as a school psychologist in New Mexico."),
    ("Today", "today",
     "Today I live alone in my own house in Las Vegas, New Mexico. I currently work as a school psychologist in Pecos Schools. My mother is still alive at 99 and lives in St. Paul."),
]


@dataclass
class InventoryItem:
    label: str
    path: str
    exists: bool
    required: bool
    purpose: str
    status: str
    notes: List[str]


@dataclass
class CommandResult:
    label: str
    cmd: List[str]
    returncode: int
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    status: str = "RUN"
    new_reports: List[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.new_reports is None:
            self.new_reports = []


@dataclass
class EvidenceFinding:
    source: str
    status: str
    findings: List[str]
    excerpt: str


@dataclass
class EraResult:
    era_label: str
    era_id: str
    narrator_text: str
    lori_response: str
    duration_s: float
    pass_fail: str
    findings: List[str]
    log_findings: List[str]


def normalize_evidence_path(path: str) -> str:
    """Boris Phase 12 contract — convert Windows-flavored evidence paths
    into WSL-mount paths so the harness can resolve operator-pasted
    transcript / log references regardless of which shell typed them.

    Conversions:
      "C:\\Users\\chris\\AppData\\..."  → "/mnt/c/Users/chris/AppData/..."
      "C:/Users/chris/AppData/..."       → "/mnt/c/Users/chris/AppData/..."
      "/mnt/c/Users/chris/hornelore/..." → unchanged (already WSL)
      "docs/reports/transcript.txt"      → unchanged (repo-relative)

    Drive-letter case is preserved as lowercase in the WSL mount
    (Windows is case-insensitive; WSL renders mounts in lowercase).
    """
    if not path:
        return path
    raw = str(path).strip()
    if not raw:
        return raw
    # Already a WSL mount path or repo-relative path
    if raw.startswith("/"):
        return raw
    # Windows drive-letter form: "C:\..." or "C:/..."
    if len(raw) >= 3 and raw[1:3] in (":\\", ":/"):
        drive = raw[0].lower()
        rest = raw[3:].replace("\\", "/")
        # Collapse double slashes
        while "//" in rest:
            rest = rest.replace("//", "/")
        return f"/mnt/{drive}/{rest}"
    # Bare relative path (no drive letter, no leading slash) — leave as-is
    return raw


def now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def tail_text(text: str, max_chars: int = 7000) -> str:
    text = text or ""
    return text if len(text) <= max_chars else text[-max_chars:]


def reports_snapshot() -> set[str]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return {str(p) for p in REPORTS_DIR.glob("*") if p.is_file()}


def new_reports_since(before: set[str]) -> List[str]:
    after = reports_snapshot()
    return sorted(after - before)


def file_exists(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def command_target_exists(cmd: List[str]) -> bool:
    if len(cmd) >= 2 and cmd[0] in ("python", "python3") and cmd[1].endswith(".py"):
        return file_exists(cmd[1])
    if len(cmd) >= 2 and cmd[0] == "bash":
        return file_exists(cmd[1])
    return True


def run_cmd(label: str, cmd: List[str], timeout: int = 900) -> CommandResult:
    if not command_target_exists(cmd):
        print(f"\n=== {label} ===")
        print("SKIP missing command target: " + " ".join(cmd))
        return CommandResult(label, cmd, 0, 0.0, "", "", status="SKIP_MISSING", new_reports=[])

    before = reports_snapshot()
    t0 = time.time()
    print(f"\n=== {label} ===")
    print("$ " + " ".join(cmd))
    try:
        p = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        rc = p.returncode
        out = p.stdout
        err = p.stderr
    except subprocess.TimeoutExpired as e:
        rc = 124
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        err += f"\nTIMEOUT after {timeout}s"
    dt = time.time() - t0
    new_reports = new_reports_since(before)
    print(f"returncode={rc} duration={dt:.1f}s reports={len(new_reports)}")
    if out.strip():
        print(tail_text(out, 1800))
    if err.strip():
        print(tail_text(err, 1800), file=sys.stderr)
    return CommandResult(label, cmd, rc, dt, tail_text(out), tail_text(err), status="RUN", new_reports=new_reports)


def http_json(path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Tuple[int, Any]:
    url = path if path.startswith("http") else API_BASE + path
    data = None
    headers: Dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def api_log_size() -> int:
    try:
        return API_LOG.stat().st_size
    except Exception:
        return 0


def api_log_snapshot(start_byte: int = 0) -> str:
    if not API_LOG.exists():
        return ""
    try:
        with API_LOG.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(start_byte)
            return f.read()
    except Exception:
        return ""


def inventory_harnesses() -> List[InventoryItem]:
    items: List[InventoryItem] = []
    for h in HARNESS_INVENTORY:
        exists = file_exists(h["path"])
        notes: List[str] = []
        status = "PASS"
        if not exists and h["required"]:
            status = "FAIL"
            notes.append("Required harness file missing.")
        elif not exists:
            status = "SKIP_MISSING"
            notes.append("Optional harness file missing.")
        items.append(InventoryItem(
            label=h["label"],
            path=h["path"],
            exists=exists,
            required=bool(h["required"]),
            purpose=h["purpose"],
            status=status,
            notes=notes,
        ))

    # Verify harness_lib contains the 8-row matrix names.
    lib = REPO_ROOT / "scripts" / "harness_lib.py"
    if lib.exists():
        text = lib.read_text(encoding="utf-8", errors="replace")
        missing = [row for row in EXPECTED_8_ROW_MATRIX if row not in text]
        if missing:
            items.append(InventoryItem(
                label="harness_lib 8-row matrix check",
                path="scripts/harness_lib.py",
                exists=True,
                required=True,
                purpose="Confirm shared scorer carries all expected rows.",
                status="FAIL",
                notes=[f"Missing expected matrix row(s): {', '.join(missing)}"],
            ))
        else:
            items.append(InventoryItem(
                label="harness_lib 8-row matrix check",
                path="scripts/harness_lib.py",
                exists=True,
                required=True,
                purpose="Confirm shared scorer carries all expected rows.",
                status="PASS",
                notes=[],
            ))
    return items


def scan_bad_run_file(path: Path) -> EvidenceFinding:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return EvidenceFinding(str(path), "MISSING_OR_UNREADABLE", [str(e)], "")

    findings: List[str] = []
    if "Lori, Life Map era:" in text:
        findings.append("BAD_HARNESS: operator directive text appears inside USER/narrator transcript")
    if "Write one warm factual Life Map entry" in text or "Write one dignified factual Life Map entry" in text:
        findings.append("BAD_HARNESS: entry-writing instruction appears as narrator text")
    if "John Baldy was born" in text or "John went to school" in text or "John's father died" in text:
        findings.append("BAD_HARNESS: third-person John facts appear as narrator text")
    if "What was the neighborhood like where he grew up?" in text:
        findings.append("ROLE_FRAMING_FAIL: Lori responds with 'he', treating John as absent")
    if "John's early school years" in text:
        findings.append("ROLE_FRAMING_FAIL: Lori writes about John in third person")
    if KNOWN_BAD_FAKE_JOHN_ID in text:
        findings.append(f"BAD_PERSON_ID: known fake John id present: {KNOWN_BAD_FAKE_JOHN_ID}")
    if "health status: **RED**" in text or "RED — must fix" in text:
        findings.append("OPERATOR_HEALTH_RED: uploaded operator log marks session RED")
    if "person_id: 5de235a9" in text:
        findings.append("OPERATOR_LOG_CONFIRMS_FAKE_JOHN: person_id is fake John, not canonical John Baldy")
    if "VRAM-GUARD" in text and "Truncating" in text:
        findings.append("VRAM_TRUNCATION: bad run hit VRAM-GUARD truncation")
    if "child_abuse" in text:
        findings.append("SAFETY_FALSE_POSITIVE_RISK: bad run triggered child_abuse from synthetic directive")

    status = "BAD_RUN_CONFIRMED" if findings else "NO_BAD_PATTERN_FOUND"
    m = re.search(r"(\[2026-06-17.*?Lori, Life Map era:.*?)(?:\n\[2026|\Z)", text, flags=re.S)
    excerpt = m.group(1)[:2200] if m else text[:2200]
    return EvidenceFinding(str(path), status, findings, excerpt)


def john_preflight(person_id: str) -> Tuple[bool, Dict[str, Any], List[str]]:
    findings: List[str] = []
    ok = True

    status, q = http_json(f"/api/bio-builder/questionnaire?person_id={person_id}", timeout=30)
    if status != 200 or not isinstance(q, dict):
        return False, {"status": status, "body": q}, [f"questionnaire read failed status={status}"]

    questionnaire = q.get("questionnaire") or q
    personal = questionnaire.get("personal") or {}
    military = questionnaire.get("military") or {}
    full = str(personal.get("fullName") or personal.get("preferredName") or "")

    if "John" not in full:
        ok = False
        findings.append(f"Expected John in fullName/preferredName, got {full!r}")
    if military.get("served") not in (False, "false", "False", 0, "0", None):
        ok = False
        findings.append(f"Expected military.served false/empty, got {military.get('served')!r}")

    status_people, people = http_json("/api/people?limit=300", timeout=30)
    if status_people == 200:
        people_text = json.dumps(people)
        if KNOWN_BAD_FAKE_JOHN_ID in people_text:
            findings.append(f"WARNING: fake John from bad harness exists in people list: {KNOWN_BAD_FAKE_JOHN_ID}")

    return ok, q, findings


def scan_log_for_turn(log_text: str, era_id: str) -> List[str]:
    findings: List[str] = []
    if "Traceback" in log_text:
        findings.append("Traceback seen in api.log")
    if re.search(r'HTTP/1\.1" 5\d\d', log_text):
        findings.append("HTTP 5xx seen in api.log")
    if "VRAM-GUARD" in log_text and "truncating input" in log_text.lower():
        findings.append("VRAM-GUARD truncating input seen")
    if "FOREIGN KEY constraint failed" in log_text:
        findings.append("FK constraint warning seen")
    if 'POST /api/facts/add HTTP/1.1" 422' in log_text:
        findings.append("KNOWN: /api/facts/add 422 seen")
    if "[chat_ws][safety] triggered" in log_text:
        findings.append("Safety trigger seen")
    if "child_abuse" in log_text:
        findings.append("Safety false-positive risk: child_abuse category seen")
    if era_id and f"era={era_id}" not in log_text:
        findings.append(f"Expected era marker era={era_id} not seen")
    return findings


def score_lori_response(era_id: str, response: str, log_findings: List[str]) -> Tuple[str, List[str]]:
    r = response.strip()
    lower = r.lower()
    findings: List[str] = []

    if not r:
        findings.append("No Lori response")
    if "let me say that in english" in lower or "sorry, in english" in lower:
        findings.append("Spanish/English correction artifact")
    if era_id == "early_school_years":
        bad_terms = ["veteran", "served in the military", "army", "navy", "air force", "marines", "coast guard"]
        if any(t in lower for t in bad_terms):
            findings.append("Military service/veteran error in Early School Years")
    if "john's " in lower or lower.startswith("john ") or "his " in lower[:80]:
        findings.append("Third-person framing: Lori speaks about John instead of to John")
    if "hospital" in lower:
        findings.append("Possible invented hospital detail")
    if "lonely" in lower or "loneliness" in lower:
        findings.append("Possible unsupported loneliness assumption")
    if response.count("?") > 1:
        findings.append("More than one question")

    for lf in log_findings:
        if lf.startswith("VRAM-GUARD") or "Traceback" in lf or "HTTP 5xx" in lf:
            findings.append(lf)
        if "Safety trigger" in lf or "child_abuse" in lf:
            findings.append(lf)

    blockers = ["No Lori response", "Military service/veteran error", "VRAM-GUARD", "Traceback", "HTTP 5xx", "Safety trigger", "child_abuse"]
    if any(any(b in f for b in blockers) for f in findings):
        return "FAIL", findings
    if findings:
        return "WARN", findings
    return "PASS", findings


async def send_ws_turn(ws, conv_id: str, person_id: str, era_id: str, text: str) -> Tuple[str, float]:
    params = {
        "person_id": person_id,
        "turn_mode": "interview",
        "session_style": "oral_history",
        "runtime71": {
            "current_pass": "pass1",
            "current_era": era_id,
            "current_mode": "open",
            "affect_state": "neutral",
            "affect_confidence": 0,
            "cognitive_mode": "open",
            "fatigue_score": 0,
            "paired": False,
            "assistant_role": "interviewer",
            "session_style_directive": "Speak directly to John as you. Reflect one concrete anchor. Ask one gentle question at most.",
            "identity_complete": True,
            "identity_phase": "complete",
            "effective_pass": "pass1",
            "speaker_name": "John",
            "person_id": person_id,
            "conversation_state": "answering",
            "cognitive_support_mode": False,
        },
        "max_new_tokens": 256,
        "turn_final": True,
    }
    await ws.send(json.dumps({
        "type": "start_turn",
        "session_id": conv_id,
        "conv_id": conv_id,
        "message": text,
        "turn_mode": "interview",
        "params": params,
    }, ensure_ascii=False))

    t0 = time.time()
    tokens: List[str] = []
    deadline = time.time() + 240
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except asyncio.TimeoutError:
            continue
        try:
            event = json.loads(raw)
        except Exception:
            continue
        typ = event.get("type")
        if typ == "token":
            tokens.append(event.get("delta") or event.get("text") or "")
        elif typ == "done":
            return event.get("final_text") or "".join(tokens), time.time() - t0
        elif typ == "error":
            return "ERROR: " + json.dumps(event)[:500], time.time() - t0
    return "", time.time() - t0


async def run_john_lifemap(person_id: str, delay_s: float) -> List[EraResult]:
    conv_id = "john_diag_" + uuid.uuid4().hex[:8]
    print("\n=== John Baldy corrected first-person Life Map diagnostic ===")
    print(f"person_id={person_id}")
    print(f"conv_id={conv_id}")

    results: List[EraResult] = []
    async with websockets.connect(WS_URL, max_size=1 << 22) as ws:
        for label, era_id, text in JOHN_ERAS:
            forbidden = ("Lori,", "Life Map era:", "Write one warm", "Write one dignified", "John Baldy was", "John went")
            if any(x in text for x in forbidden):
                results.append(EraResult(label, era_id, text, "", 0.0, "FAIL",
                                         ["Harness bug: narrator text contains operator directive"], []))
                continue

            print(f"\n--- {label} / {era_id} ---")
            print("John:", text)
            start_log = api_log_size()
            response, dt = await send_ws_turn(ws, conv_id, person_id, era_id, text)
            if delay_s > 0:
                time.sleep(delay_s)
            log_text = api_log_snapshot(start_log)
            log_findings = scan_log_for_turn(log_text, era_id)
            pf, findings = score_lori_response(era_id, response, log_findings)
            print("Lori:", response)
            print("Result:", pf)
            if findings:
                print("Findings:", findings)
            if log_findings:
                print("Log:", log_findings)
            results.append(EraResult(label, era_id, text, response, dt, pf, findings, log_findings))
    return results


def test_lab_phase(mode: str) -> Tuple[Dict[str, Any], Optional[CommandResult]]:
    runner = REPO_ROOT / "scripts" / "run_test_lab.sh"
    status: Dict[str, Any] = {
        "runner_exists": runner.exists(),
        "runner_path": str(runner),
        "mode": mode,
    }
    if not runner.exists():
        status["status"] = "SKIP: scripts/run_test_lab.sh missing"
        return status, None
    if mode == "check":
        status["status"] = "available; not run"
        return status, None
    if mode == "dry":
        return status, run_cmd("test_lab:dry_run", ["bash", "scripts/run_test_lab.sh", "--dry-run"], timeout=900)
    if mode == "full":
        return status, run_cmd("test_lab:full", ["bash", "scripts/run_test_lab.sh"], timeout=7200)
    status["status"] = "unknown mode"
    return status, None


def summarize_reports(paths: List[str], max_chars_each: int = 1200) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in paths:
        path = Path(p)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            out[p] = f"UNREADABLE: {e}"
            continue
        out[p] = text[:max_chars_each]
    return out


def write_report(
    stamp: str,
    args: argparse.Namespace,
    inventory: List[InventoryItem],
    command_results: List[CommandResult],
    evidence: List[EvidenceFinding],
    test_lab_status: Dict[str, Any],
    test_lab_result: Optional[CommandResult],
    john_preflight_payload: Dict[str, Any],
    john_preflight_findings: List[str],
    era_results: List[EraResult],
) -> Tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"john_baldy_full_diagnostic_{stamp}.md"
    json_path = REPORTS_DIR / f"john_baldy_full_diagnostic_{stamp}.json"

    hard_fail = False
    warn = False

    for item in inventory:
        if item.status == "FAIL":
            hard_fail = True

    for r in command_results:
        if r.status == "RUN" and r.returncode != 0:
            hard_fail = True

    if test_lab_result and test_lab_result.returncode != 0:
        hard_fail = True

    for ev in evidence:
        if ev.status == "BAD_RUN_CONFIRMED":
            warn = True

    for f in john_preflight_findings:
        warn = True
        if "Expected" in f:
            hard_fail = True

    for e in era_results:
        if e.pass_fail == "FAIL":
            hard_fail = True
        elif e.pass_fail == "WARN":
            warn = True

    overall = "FAIL" if hard_fail else "WARN" if warn else "PASS"

    all_new_reports: List[str] = []
    for r in command_results:
        all_new_reports.extend(r.new_reports)
    if test_lab_result:
        all_new_reports.extend(test_lab_result.new_reports)
    report_summaries = summarize_reports(sorted(set(all_new_reports)))

    lines: List[str] = []
    lines.append("# John Baldy Full Diagnostic Harness Report")
    lines.append("")
    lines.append(f"- Run time: `{time.strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"- API base: `{API_BASE}`")
    lines.append(f"- Canonical John person_id: `{args.person_id}`")
    lines.append(f"- Overall: **{overall}**")
    lines.append("")
    lines.append("## Phase 0 — Bad first-run evidence scan")
    lines.append("")
    if evidence:
        for ev in evidence:
            lines.append(f"### {ev.source}")
            lines.append(f"- Status: `{ev.status}`")
            for f in ev.findings:
                lines.append(f"- {f}")
            if ev.excerpt.strip():
                lines.append("")
                lines.append("Excerpt:")
                lines.append("```text")
                lines.append(ev.excerpt.strip())
                lines.append("```")
            lines.append("")
    else:
        lines.append("- No bad-run evidence files supplied.")
        lines.append("")

    lines.append("## Phase 1 — Unit/regression tests")
    lines.append("")
    for r in [x for x in command_results if x.label.startswith("unit:")]:
        lines.append(f"### {r.label}")
        lines.append(f"- Status: `{r.status}`")
        lines.append(f"- Return code: `{r.returncode}`")
        lines.append(f"- Duration: `{r.duration_s:.1f}s`")
        if r.stdout_tail.strip():
            lines.append("```text")
            lines.append(r.stdout_tail.strip())
            lines.append("```")
        if r.stderr_tail.strip():
            lines.append("stderr:")
            lines.append("```text")
            lines.append(r.stderr_tail.strip())
            lines.append("```")
        lines.append("")

    lines.append("## Phase 2 — Harness inventory")
    lines.append("")
    lines.append("| Harness | Exists | Required | Status | Purpose |")
    lines.append("|---|---:|---:|---|---|")
    for item in inventory:
        lines.append(f"| {item.label} | {item.exists} | {item.required} | {item.status} | {item.purpose} |")
    lines.append("")
    for item in inventory:
        if item.notes:
            lines.append(f"- {item.label}: " + "; ".join(item.notes))
    lines.append("")

    lines.append("## Phase 3/4 — Existing live backend harness runs")
    lines.append("")
    for r in [x for x in command_results if x.label.startswith("live:")]:
        lines.append(f"### {r.label}")
        lines.append(f"- Status: `{r.status}`")
        lines.append(f"- Command: `{' '.join(r.cmd)}`")
        lines.append(f"- Return code: `{r.returncode}`")
        lines.append(f"- Duration: `{r.duration_s:.1f}s`")
        if r.new_reports:
            lines.append("- New reports:")
            for p in r.new_reports:
                lines.append(f"  - `{p}`")
        if r.stdout_tail.strip():
            lines.append("stdout tail:")
            lines.append("```text")
            lines.append(r.stdout_tail.strip())
            lines.append("```")
        if r.stderr_tail.strip():
            lines.append("stderr tail:")
            lines.append("```text")
            lines.append(r.stderr_tail.strip())
            lines.append("```")
        lines.append("")

    lines.append("## Phase 5 — Test Lab")
    lines.append("")
    for k, v in test_lab_status.items():
        lines.append(f"- {k}: `{v}`")
    if test_lab_result:
        lines.append(f"- returncode: `{test_lab_result.returncode}`")
        lines.append(f"- duration_s: `{test_lab_result.duration_s:.1f}`")
    lines.append("")

    lines.append("## Phase 6 — John Baldy preflight")
    lines.append("")
    if john_preflight_findings:
        for f in john_preflight_findings:
            lines.append(f"- {f}")
    else:
        lines.append("- Preflight passed with no findings.")
    lines.append("")
    lines.append("Questionnaire readback excerpt:")
    lines.append("```json")
    lines.append(json.dumps(john_preflight_payload, indent=2)[:5000])
    lines.append("```")
    lines.append("")

    lines.append("## Phase 7 — Corrected John Baldy Life Map backend diagnostic")
    lines.append("")
    lines.append("These are first-person John turns. No operator directive text is sent as narrator content.")
    lines.append("")
    for e in era_results:
        mark = "✅" if e.pass_fail == "PASS" else "⚠️" if e.pass_fail == "WARN" else "❌"
        lines.append(f"### {mark} {e.era_label} — `{e.pass_fail}`")
        lines.append(f"- era_id: `{e.era_id}`")
        lines.append(f"- duration: `{e.duration_s:.1f}s`")
        lines.append("")
        lines.append("John turn:")
        lines.append("```text")
        lines.append(e.narrator_text)
        lines.append("```")
        lines.append("")
        lines.append("Lori response:")
        lines.append("```text")
        lines.append(e.lori_response or "(no response)")
        lines.append("```")
        if e.findings:
            lines.append("")
            lines.append("Findings:")
            for f in e.findings:
                lines.append(f"- {f}")
        if e.log_findings:
            lines.append("")
            lines.append("Log findings:")
            for f in e.log_findings:
                lines.append(f"- {f}")
        lines.append("")

    lines.append("## Phase 8 — Harvested harness report snippets")
    lines.append("")
    if report_summaries:
        for p, text in report_summaries.items():
            lines.append(f"### `{p}`")
            lines.append("```text")
            lines.append(text.strip())
            lines.append("```")
            lines.append("")
    else:
        lines.append("- No new harness reports detected.")
        lines.append("")

    payload = {
        "overall": overall,
        "stamp": stamp,
        "api_base": API_BASE,
        "canonical_john_person_id": args.person_id,
        "args": vars(args),
        "inventory": [asdict(i) for i in inventory],
        "evidence": [asdict(e) for e in evidence],
        "command_results": [asdict(r) for r in command_results],
        "test_lab_status": test_lab_status,
        "test_lab_result": asdict(test_lab_result) if test_lab_result else None,
        "john_preflight_findings": john_preflight_findings,
        "john_preflight_payload": john_preflight_payload,
        "era_results": [asdict(e) for e in era_results],
        "harvested_report_summaries": report_summaries,
    }
    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return md_path, json_path


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--person-id", default=JOHN_PERSON_ID)
    parser.add_argument("--quick", action="store_true", help="Run unit tests + inventory + John diagnostic only.")
    parser.add_argument("--full-family", action="store_true", help="Run every long-narration persona harness.")
    parser.add_argument("--skip-unit", action="store_true")
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--skip-john", action="store_true")
    parser.add_argument("--bad-run-transcript", action="append", default=[])
    parser.add_argument("--operator-log", action="append", default=[])
    parser.add_argument("--test-lab-dry-run", action="store_true")
    parser.add_argument("--test-lab-full", action="store_true")
    parser.add_argument("--post-turn-delay", type=float, default=15.0)
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    stamp = now_stamp()

    status, ping = http_json("/api/ping", timeout=5)
    if status != 200:
        print(f"Stack not reachable at {API_BASE}/api/ping — status={status} body={ping}", file=sys.stderr)
        return 2

    evidence_paths = [Path(p) for p in args.bad_run_transcript + args.operator_log]
    evidence = [scan_bad_run_file(p) for p in evidence_paths]

    inventory = inventory_harnesses()

    command_results: List[CommandResult] = []
    if not args.skip_unit:
        for label, cmd, timeout in UNIT_TESTS:
            command_results.append(run_cmd(label, cmd, timeout))

    if not args.skip_live and not args.quick:
        for label, cmd, timeout in CORE_LIVE_HARNESSES:
            command_results.append(run_cmd(label, cmd, timeout))
        if args.full_family:
            for label, cmd, timeout in FAMILY_LIVE_HARNESSES:
                command_results.append(run_cmd(label, cmd, timeout))

    test_lab_mode = "full" if args.test_lab_full else "dry" if args.test_lab_dry_run else "check"
    test_lab_status, test_lab_result = test_lab_phase(test_lab_mode)

    pre_ok, pre_payload, pre_findings = john_preflight(args.person_id)
    if not pre_ok:
        print("John preflight failed; John phase may still run but report will FAIL.")

    era_results: List[EraResult] = []
    if not args.skip_john:
        era_results = await run_john_lifemap(args.person_id, args.post_turn_delay)

    md_path, json_path = write_report(
        stamp, args, inventory, command_results, evidence, test_lab_status, test_lab_result,
        pre_payload if isinstance(pre_payload, dict) else {"body": pre_payload},
        pre_findings, era_results,
    )
    print("\nReport written:")
    print(md_path)
    print(json_path)

    fail = False
    if any(i.status == "FAIL" for i in inventory):
        fail = True
    for r in command_results:
        if r.status == "RUN" and r.returncode != 0:
            fail = True
    if test_lab_result and test_lab_result.returncode != 0:
        fail = True
    if any(e.pass_fail == "FAIL" for e in era_results):
        fail = True
    if any("Expected" in f for f in pre_findings):
        fail = True
    return 1 if fail else 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
