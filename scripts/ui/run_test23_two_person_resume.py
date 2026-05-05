"""
TEST-23 — Two-Person Single-Narrator Resume Canary.

Built 2026-05-04 per Chris's spec. This is NOT a stress test. It is a
product canary that exercises the real path a single narrator takes:
fresh onboarding → Life Map walk → memory recall → end session →
close UI → reopen UI → reload same narrator → resume recall → Today.

Two narrators run in sequence so we also see cross-person isolation:

  Person A — messy input
    Display name: Mary Holts
    Input name:   "mary Holts"           (lowercase first → normalize to Mary)
    DOB input:    "2/29 1940"            → 1940-02-29 (leap year)
    POB input:    "Minot ND"             → "Minot, North Dakota" (after correction)
    Status seed:  widow

  Person B — clean input
    Display name: Marvin Mann
    Input name:   "Marvin Mann"
    DOB input:    "December 6, 1949"     → 1949-12-06
    POB input:    "Fargo, North Dakota"
    Status seed:  widower

Each narrator walks all 7 Life Map eras (one seed turn per era), then runs
two Today cycles, asks "what day is it" (factual interruption), jumps back
to Earliest Years and asks "what do you know about me", asks Lori to guess
their age and where they live now (data points — Lori should compute age
from DOB if available; should admit not knowing residence). Then the test
ends the session, fully closes the browser context, opens a new context,
reloads the SAME narrator (by pid), and tests resume behavior:
"what do you know about me" again, then Today + "what day is it".

Output:
  docs/reports/test23_two_person_resume_<tag>.json
  docs/reports/test23_two_person_resume_<tag>.md
  docs/reports/test23_two_person_resume_<tag>_failures.csv
  docs/reports/test23_two_person_resume_<tag>.console.txt   (live tail mirror)

Clean-run rule: while this test runs, do NOT touch the browser via
Claude-in-Chrome or any other tool. No second tab, no operator polling,
no localhost inspection. The harness owns the only client.

Usage:
  cd /mnt/c/Users/chris/hornelore
  python -m scripts.ui.run_test23_two_person_resume --tag test23_v1
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_UI = _REPO_ROOT / "scripts" / "ui"
_REPORTS_DIR = _REPO_ROOT / "docs" / "reports"
_RUNTIME_DIR = _REPO_ROOT / ".runtime"
_API_LOG = _RUNTIME_DIR / "logs" / "api.log"

# Reuse harness infrastructure.
sys.path.insert(0, str(_SCRIPTS_UI))
from run_parent_session_readiness_harness import (  # noqa: E402
    UI,
    ConsoleCollector,
    DbLockCounter,
)
from run_parent_session_rehearsal_harness import (  # noqa: E402
    LIFE_MAP_ERAS_CANONICAL,
    TelemetryRecorder,
    click_era_button_data_attr,
    get_state_session,
)


# ──────────────────────────────────────────────────────────────────────
# Narrator plans — Mary (messy) + Marvin (clean)
# ──────────────────────────────────────────────────────────────────────


@dataclass
class NarratorPlan:
    key: str                         # 'mary' / 'marvin'
    display_name: str                # picker label, set at /api/people creation
    name_chat_input: str             # what the narrator types as fullName answer
    expected_first_name: str
    expected_last_name: str
    dob_chat_input: str
    expected_dob: str                # YYYY-MM-DD
    pob_chat_input: str              # initial POB answer (may be messy)
    pob_correction_input: Optional[str]   # follow-up correction, None if clean
    expected_pob: str                # canonical POB after correction
    status_seed: Optional[str]       # widow/widower seed (sent right after onboarding)
    era_seeds: Dict[str, str]        # era_id → narrator turn text
    era_extras: Dict[str, str] = field(default_factory=dict)  # era_id → follow-up turn text (mid-stream correction / ambiguity)
    expected_era_facts: Dict[str, List[str]] = field(default_factory=dict)   # era_id → ≥1 distinguishing token Lori should reflect
    spouse_memory_probe: Optional[str] = None  # late-stage probe ("What do you remember about my wife?")
    expected_spouse_tokens: List[str] = field(default_factory=list)  # tokens we expect Lori to recall about the spouse


MARY_PLAN = NarratorPlan(
    key="mary",
    display_name="Mary Holts (TEST-23)",
    name_chat_input="mary Holts",
    expected_first_name="Mary",
    expected_last_name="Holts",
    dob_chat_input="2/29 1940",
    expected_dob="1940-02-29",
    pob_chat_input="Minot ND",
    pob_correction_input="Actually it's Minot, North Dakota — not just ND",
    expected_pob="Minot, North Dakota",
    status_seed=None,    # Mary's widow signal surfaces inside later_years era seed
    era_seeds={
        "earliest_years":     "I was born during a storm — I think it was really cold that year.",
        "early_school_years": "We walked to school, me and my brother, through the snow most days.",
        "adolescence":        "I learned early on there were things you said in public and things you didn't.",
        "coming_of_age":      "I met my husband at a county fair. He kept coming back to talk.",
        "building_years":     "We had kids and moved around a bit for his work. Those years went fast.",
        "later_years":        "After he passed, the house got very quiet. I started spending more time outside.",
        "today":              "These days I take things slower. I like sitting by the window in the morning.",
    },
    era_extras={
        # Mid-stream correction during Building Years — overwrite-vs-contradiction test
        "building_years":     "Actually we only had two kids, not three.",
    },
    expected_era_facts={
        "earliest_years":     ["storm", "cold", "born"],
        "early_school_years": ["walked", "school", "brother", "snow"],
        "adolescence":        ["public", "private", "said"],
        "coming_of_age":      ["husband", "fair", "county"],
        "building_years":     ["kids", "moved", "work", "two"],
        "later_years":        ["passed", "quiet", "outside"],
        "today":              ["window", "morning", "slower"],
    },
    spouse_memory_probe=None,    # Mary's spouse is referenced; cross-check is implicit in recall
    expected_spouse_tokens=[],
)


MARVIN_PLAN = NarratorPlan(
    key="marvin",
    display_name="Marvin Mann (TEST-23)",
    name_chat_input="Marvin Mann",
    expected_first_name="Marvin",
    expected_last_name="Mann",
    dob_chat_input="December 6, 1949",
    expected_dob="1949-12-06",
    pob_chat_input="Fargo, North Dakota",
    pob_correction_input=None,
    expected_pob="Fargo, North Dakota",
    status_seed="I am a widower now, I still think about my wife every morning.",
    era_seeds={
        "earliest_years":     "I grew up in a small house where the kitchen was always warm in the winter.",
        "early_school_years": "I liked arithmetic in school, but I was shy about reading out loud.",
        "adolescence":        "As a teenager, I worked after school and saved money for an old pickup.",
        "coming_of_age":      "I left home for my first steady job and learned how much responsibility costs.",
        "building_years":     "My wife and I built a life slowly. We bought a house, raised children, and worked hard.",
        "later_years":        "After my wife died, I kept some of her letters in the top drawer of my desk.",
        "today":              "Today I keep a simple routine. Coffee, a short walk, and a little time reading.",
    },
    era_extras={
        # Ambiguity injection during Adolescence — uncertainty handling test
        "adolescence":        "I think that was around 1965… or maybe a little later.",
    },
    expected_era_facts={
        "earliest_years":     ["kitchen", "warm", "winter", "small"],
        "early_school_years": ["arithmetic", "shy", "reading"],
        "adolescence":        ["pickup", "saved", "after school", "1965"],
        "coming_of_age":      ["job", "responsibility", "left home"],
        "building_years":     ["wife", "children", "house", "raised"],
        "later_years":        ["letters", "drawer", "wife", "died"],
        "today":              ["coffee", "walk", "reading", "routine"],
    },
    spouse_memory_probe="What do you remember about my wife?",
    expected_spouse_tokens=["wife", "widower", "letters", "drawer", "morning"],
)


# ──────────────────────────────────────────────────────────────────────
# Result dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass
class StepResult:
    label: str
    narrator_input: str
    lori_reply: str = ""
    elapsed_ms: int = 0
    severity: str = "PASS"        # PASS / AMBER / RED
    notes: List[str] = field(default_factory=list)
    state_after: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EraStepResult:
    era_id: str
    era_label: str
    click_log_seen: bool = False
    prompt_log_seen: bool = False
    current_era_after: Optional[str] = None
    # v2: capture Lori's spontaneous era prompt BEFORE the seed turn.
    # The era click triggers sendSystemPrompt which produces a Lori
    # turn unprompted by the narrator — that's the era-anchored question
    # we actually want to evaluate. The seed_reply was misleading in v1
    # because it's Lori's response to narrator content, not her era prompt.
    era_prompt_reply: str = ""
    era_prompt_anchored: bool = False
    era_prompt_question_count: int = 0
    seed_text: str = ""
    seed_reply: str = ""
    era_anchored: bool = False        # OR of era_prompt_anchored OR seed_anchored (legacy compat)
    extra_text: str = ""               # mid-stream correction / ambiguity probe
    extra_reply: str = ""
    extra_handled_well: Optional[bool] = None    # True/False based on probe-specific check; None if no extra
    severity: str = "PASS"
    notes: List[str] = field(default_factory=list)


@dataclass
class RecallResult:
    label: str
    question: str
    reply: str = ""
    contains_name: bool = False
    contains_dob_or_year: bool = False
    contains_pob: bool = False
    era_stories_in_readback: int = 0
    era_stories_total: int = 0
    cross_contamination: bool = False
    onboarding_restart: bool = False
    severity: str = "PASS"
    notes: List[str] = field(default_factory=list)


@dataclass
class NarratorReport:
    plan_key: str
    display_name: str
    person_id: str = ""
    onboarding_steps: List[StepResult] = field(default_factory=list)
    early_inference_steps: List[StepResult] = field(default_factory=list)   # age + residence probes EARLY
    era_results: List[EraStepResult] = field(default_factory=list)
    today_cycles: List[StepResult] = field(default_factory=list)
    today_factual: Optional[StepResult] = None
    late_age_probe: Optional[StepResult] = None     # "How old do you think I am now?" after era walk
    pre_restart_recall: Optional[RecallResult] = None
    spouse_memory_probe: Optional[StepResult] = None    # Marvin only
    post_restart_recall: Optional[RecallResult] = None
    today_after_resume: Optional[StepResult] = None
    apilog_signals_per_phase: Dict[str, Dict[str, int]] = field(default_factory=dict)
    bb_state_after_onboard: Dict[str, Any] = field(default_factory=dict)
    bb_state_after_correction: Dict[str, Any] = field(default_factory=dict)   # v2: post-correction snapshot
    bb_state_after_status_seed: Dict[str, Any] = field(default_factory=dict)  # v2: post-widower-seed (Marvin)
    bb_state_after_session1: Dict[str, Any] = field(default_factory=dict)
    bb_state_after_resume: Dict[str, Any] = field(default_factory=dict)
    memoir_artifacts: List[Dict[str, Any]] = field(default_factory=list)      # v2: peek + export captures
    severity: str = "PASS"
    notes: List[str] = field(default_factory=list)


# v2: runtime-scoped config so phase functions can save artifacts without
# requiring tag/reports_dir to be threaded through every signature.
_RUNTIME_CONFIG: Dict[str, Any] = {"tag": "", "reports_dir": _REPORTS_DIR}


@dataclass
class RunReport:
    tag: str
    started_at: str
    finished_at: str = ""
    base_url: str = ""
    api_base: str = ""
    commit_sha: str = ""
    dirty_tree: bool = False
    mary: Optional[NarratorReport] = None
    marvin: Optional[NarratorReport] = None
    cross_isolation_check: Optional[RecallResult] = None
    final_severity: str = "PASS"
    final_failures: List[str] = field(default_factory=list)
    telemetry_path: str = ""    # path to companion .telemetry.json if emitted


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _git_sha_and_dirty(repo: Path) -> Tuple[str, bool]:
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            text=True, timeout=5,
        ).strip()
    except Exception:
        sha = "unknown"
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain"],
            text=True, timeout=5,
        ).strip()
        dirty = bool(out)
    except Exception:
        dirty = True
    return sha, dirty


def _wait_for_warm_stack(page: Page, console: ConsoleCollector, timeout_s: int = 90) -> bool:
    """Poll the page for app readiness."""
    try:
        if page.evaluate("window._llmReady === true"):
            return True
    except Exception:
        pass
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if page.evaluate("window._llmReady === true"):
                return True
        except Exception:
            pass
        if console.matches(r"\[readiness\] Model warm and ready"):
            return True
        page.wait_for_timeout(2000)
    return False


def _read_apilog_lines() -> List[str]:
    """Read the entire api.log if it exists; safe when file is missing."""
    if not _API_LOG.exists():
        return []
    try:
        with _API_LOG.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except Exception:
        return []


_APILOG_TS_RX = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})")


def _apilog_signal_counts(lines: List[str]) -> Dict[str, int]:
    """Count diagnostic signals in a slice of api.log lines."""
    sig = {
        "extract_attempts": 0,
        "extract_summary": 0,
        "life_map_era_click": 0,
        "life_map_lori_prompt": 0,
        "story_trigger": 0,
        "utterance_frame": 0,
        "era_normalize": 0,
        "phase_g_disconnect": 0,
        "ws_connected": 0,
        "fk_constraint": 0,
        "send_system_prompt_timeout": 0,
        "vram_guard": 0,
        "comm_control_trim": 0,
        "spantag_flag_on": 0,
        "value_coerce": 0,
        "memory_echo": 0,
        "safety_event": 0,
    }
    for ln in lines:
        if "[extract] Attempting" in ln: sig["extract_attempts"] += 1
        if "[extract][summary]" in ln: sig["extract_summary"] += 1
        if "[life-map][era-click] era=" in ln: sig["life_map_era_click"] += 1
        if "[life-map][era-click] Lori prompt dispatched" in ln: sig["life_map_lori_prompt"] += 1
        if "[story-trigger]" in ln: sig["story_trigger"] += 1
        if "[utterance-frame]" in ln: sig["utterance_frame"] += 1
        if "[extract][era-normalize]" in ln: sig["era_normalize"] += 1
        if "Phase G" in ln and "disconnect" in ln.lower(): sig["phase_g_disconnect"] += 1
        if "WebSocket" in ln and "connected" in ln.lower(): sig["ws_connected"] += 1
        if "FOREIGN KEY constraint" in ln: sig["fk_constraint"] += 1
        if "sendSystemPrompt" in ln and "timeout" in ln.lower(): sig["send_system_prompt_timeout"] += 1
        if "VRAM_GUARD" in ln or "[vram-guard]" in ln: sig["vram_guard"] += 1
        if "[comm-control] trim" in ln or "[comm-control] trimmed" in ln: sig["comm_control_trim"] += 1
        if "[extract][spantag] flag ON" in ln: sig["spantag_flag_on"] += 1
        if "[extract][value-coerce]" in ln: sig["value_coerce"] += 1
        if "[memory-echo]" in ln or "compose_memory_echo" in ln: sig["memory_echo"] += 1
        if "[safety]" in ln or "safety_event" in ln: sig["safety_event"] += 1
    return sig


def _apilog_window_signals(start_ts: float, end_ts: float) -> Dict[str, int]:
    """Filter api.log to lines whose ISO timestamp falls between start_ts and
    end_ts (epoch seconds), then count signals. Lines without parseable
    timestamps are included on a best-effort basis (they bracket recent
    activity)."""
    lines = _read_apilog_lines()
    if not lines:
        return _apilog_signal_counts([])
    keep: List[str] = []
    for ln in lines:
        m = _APILOG_TS_RX.match(ln)
        if not m:
            continue
        ts_str = m.group(1).replace(" ", "T")
        try:
            ts = dt.datetime.fromisoformat(ts_str).timestamp()
        except ValueError:
            continue
        if start_ts <= ts <= end_ts:
            keep.append(ln)
    return _apilog_signal_counts(keep)


def _print_signal_delta(label: str, signals: Dict[str, int]) -> None:
    interesting = {k: v for k, v in signals.items() if v > 0}
    if not interesting:
        print(f"  [{label}] api.log signals: (none)")
        return
    items = ", ".join(f"{k}={v}" for k, v in sorted(interesting.items()))
    print(f"  [{label}] api.log signals: {items}")


def _select_narrator_by_pid(page: Page, pid: str) -> bool:
    """Activate an existing narrator by person_id post-restart. Mirrors
    the lv80ConfirmNarratorSwitch path used by add_test_narrator."""
    result = page.evaluate(
        """
        async (pid) => {
          try {
            if (typeof refreshPeople === 'function') {
              try { await refreshPeople(); } catch (e) {}
            }
            if (typeof lv80RenderNarratorCards === 'function') {
              try { lv80RenderNarratorCards(); } catch (e) {}
            }
            if (typeof lv80ConfirmNarratorSwitch === 'function') {
              try { await lv80ConfirmNarratorSwitch(pid); return {ok: true, via: 'lv80'}; }
              catch (e) {
                if (typeof loadPerson === 'function') {
                  await loadPerson(pid); return {ok: true, via: 'loadPerson'};
                }
                return {ok: false, error: 'switch_threw: ' + (e && e.message)};
              }
            } else if (typeof loadPerson === 'function') {
              await loadPerson(pid);
              return {ok: true, via: 'loadPerson'};
            }
            return {ok: false, error: 'no_switch_function'};
          } catch (e) {
            return {ok: false, error: String(e && e.message || e)};
          }
        }
        """,
        pid,
    )
    return bool(result and result.get("ok"))


def _capture_memoir_peek(page: Page) -> str:
    """Read the Peek-at-Memoir popover/container's innerText. Returns '' on
    any failure. v2 capture so we can see what Lori thinks she has across
    the close+reopen boundary."""
    try:
        return page.evaluate(
            """
            () => {
              const sels = [
                '#lvMemoirContainer',
                '#lvMemoirPopover',
                '#lv80MemoirPeek',
                '.lv80-memoir-peek',
                '[data-memoir-peek]',
                '[data-purpose="memoir_peek"]',
              ];
              for (const sel of sels) {
                const el = document.querySelector(sel);
                if (el) {
                  return (el.innerText || el.textContent || '').trim();
                }
              }
              return '';
            }
            """,
        ) or ""
    except Exception:
        return ""


def _capture_memoir_export_text(page: Page) -> str:
    """Call the memoir TXT-export builder directly to get the export
    content as a string. Tries _memoirBuildTxtContent + a few aliases.
    Returns '' if no exposed builder. We capture this instead of clicking
    Save TXT + downloading because (a) it's stable across UI button
    label changes and (b) Playwright download handling is fragile across
    contexts."""
    try:
        return page.evaluate(
            """
            () => {
              const fns = [
                window._memoirBuildTxtContent,
                window.lv80BuildMemoirTxt,
                window.lv80MemoirToTxt,
                (typeof _memoirBuildTxtContent === 'function' ? _memoirBuildTxtContent : null),
              ];
              for (const fn of fns) {
                if (typeof fn === 'function') {
                  try {
                    const out = fn();
                    if (typeof out === 'string') return out;
                  } catch (_) {}
                }
              }
              return '';
            }
            """,
        ) or ""
    except Exception:
        return ""


def _save_memoir_artifact(
    page: Page,
    reports_dir: Path,
    tag: str,
    narrator_key: str,
    phase_label: str,
) -> Dict[str, Any]:
    """Capture both the Peek innerText and the TXT export content; write
    each to a sibling .txt file under docs/reports/. Returns metadata
    so the per-narrator report can link to the artifacts."""
    peek = _capture_memoir_peek(page)
    export = _capture_memoir_export_text(page)
    out: Dict[str, Any] = {"phase": phase_label, "peek_chars": len(peek), "export_chars": len(export)}
    if peek:
        peek_path = reports_dir / f"test23_{tag}_{narrator_key}_memoir_peek_{phase_label}.txt"
        try:
            peek_path.write_text(peek, encoding="utf-8")
            out["peek_path"] = str(peek_path)
        except Exception as e:
            out["peek_error"] = str(e)
    if export:
        export_path = reports_dir / f"test23_{tag}_{narrator_key}_memoir_export_{phase_label}.txt"
        try:
            export_path.write_text(export, encoding="utf-8")
            out["export_path"] = str(export_path)
        except Exception as e:
            out["export_error"] = str(e)
    return out


def _close_popovers(page: Page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
    except Exception:
        pass
    try:
        page.evaluate("""
            () => {
              for (const el of document.querySelectorAll('[popover]')) {
                try {
                  if (el.matches && el.matches(':popover-open') && el.hidePopover) {
                    el.hidePopover();
                  }
                } catch (_) {}
              }
            }
        """)
        page.wait_for_timeout(150)
    except Exception:
        pass


def _capture_bb_state(page: Page) -> Dict[str, Any]:
    """Snapshot Bio Builder identity fields. v2 (2026-05-04): tries
    multiple state paths because v1 read state.bioBuilder.personal and
    got back all None for both Mary and Marvin even though pre-restart
    recall proved Lori had the values. The values land somewhere; we
    just have to find where.

    Tries in order:
      1. state.bioBuilder.personal
      2. state.person.bioBuilder.personal
      3. window.bioBuilder.personal
      4. state.person.personal
      5. state.person (top-level firstName/lastName/dateOfBirth)
    First path with at least one non-null identity field wins. Always
    returns the discovered path label so we know where the data lives."""
    try:
        return page.evaluate(
            """
            () => {
              try {
                const out = {};
                // Define candidate paths in priority order. Each is a
                // function that returns {personal, family, label} or null.
                const candidates = [
                  () => {
                    const bb = window.state?.bioBuilder;
                    if (!bb) return null;
                    return {personal: bb.personal || {}, family: bb.family || {}, label: 'state.bioBuilder'};
                  },
                  () => {
                    const bb = window.state?.person?.bioBuilder;
                    if (!bb) return null;
                    return {personal: bb.personal || {}, family: bb.family || {}, label: 'state.person.bioBuilder'};
                  },
                  () => {
                    const bb = window.bioBuilder;
                    if (!bb) return null;
                    return {personal: bb.personal || {}, family: bb.family || {}, label: 'window.bioBuilder'};
                  },
                  () => {
                    const p = window.state?.person?.personal;
                    if (!p) return null;
                    return {personal: p, family: window.state?.person?.family || {}, label: 'state.person.personal'};
                  },
                  () => {
                    const p = window.state?.person;
                    if (!p) return null;
                    return {personal: p, family: p.family || {}, label: 'state.person (top-level)'};
                  },
                ];
                let chosen = null;
                let chosen_label = null;
                let probe_summary = [];
                for (const fn of candidates) {
                  let cand = null;
                  try { cand = fn(); } catch (_) { cand = null; }
                  if (!cand) { probe_summary.push(null); continue; }
                  const p = cand.personal || {};
                  const fields = [
                    p.fullName, p.firstName, p.lastName,
                    p.preferredName, p.dateOfBirth, p.placeOfBirth,
                  ];
                  const non_null = fields.filter(v => v !== null && v !== undefined && v !== '').length;
                  probe_summary.push({path: cand.label, non_null: non_null});
                  if (non_null > 0 && !chosen) {
                    chosen = cand;
                    chosen_label = cand.label;
                  }
                }
                // Fall back to first candidate (likely state.bioBuilder)
                // if no path had non-null values — preserves the
                // diagnostic "all None" signal the v1 capture produced.
                if (!chosen) {
                  for (const fn of candidates) {
                    let cand = null;
                    try { cand = fn(); } catch (_) {}
                    if (cand) { chosen = cand; chosen_label = cand.label; break; }
                  }
                }
                const personal = (chosen && chosen.personal) || {};
                const family = (chosen && chosen.family) || {};
                out.fullName = personal.fullName || null;
                out.firstName = personal.firstName || null;
                out.lastName = personal.lastName || null;
                out.preferredName = personal.preferredName || null;
                out.dateOfBirth = personal.dateOfBirth || null;
                out.placeOfBirth = personal.placeOfBirth || null;
                out.spouse = family.spouse || null;
                out.bb_path = chosen_label || 'none';
                out.bb_probe = probe_summary;
                out.identityPhase = window.state?.session?.identityPhase || null;
                out.basicsComplete = (typeof window.hasIdentityBasics74 === 'function')
                  ? !!window.hasIdentityBasics74() : null;
                out.person_id = window.state?.person_id || null;
                out.currentEra = window.state?.session?.currentEra || null;
                // Also dump top-level state.person keys so we can see
                // what shape the narrator object actually has.
                try {
                  out.state_person_keys = Object.keys(window.state?.person || {});
                } catch (_) { out.state_person_keys = []; }
                return out;
              } catch (e) { return {error: String(e && e.message || e)}; }
            }
            """,
        ) or {}
    except Exception as e:
        return {"error": f"capture_threw: {e}"}


# ──────────────────────────────────────────────────────────────────────
# Per-step send + capture + grade
# ──────────────────────────────────────────────────────────────────────


def _wait_for_lori_complete(
    ui: UI,
    since_ts: float,
    *,
    text_timeout_ms: int = 120_000,
    tts_timeout_ms: int = 60_000,
    settle_ms: int = 500,
) -> Dict[str, Any]:
    """v2 of wait_for_lori_turn — gates on BOTH text-streaming-complete
    AND TTS-playback-complete before returning. This eliminates the race
    we hit in test23_v1 where the harness fired the next narrator turn
    while Lori was still streaming.

    Two signals checked, both must be true:
      1. lori_reply event lands with non-empty, non-placeholder text
         (existing wait_for_lori_turn handles the placeholder filter)
      2. state.narratorTurn.ttsFinishedAt timestamp updates AFTER the
         text-done timestamp — same gate the lori-clock.js feature uses
         to decide when the narrator can speak again

    Returns dict:
      - reply: text reply (empty on text timeout)
      - tts_done: True if TTS confirmed finished, False if tts_timeout hit
      - text_elapsed_ms: time to text completion
      - tts_wait_ms: additional wait for TTS after text done
      - total_elapsed_ms: total time from send to ready-for-next-turn
    """
    t0 = time.time()
    out: Dict[str, Any] = {
        "reply": "",
        "tts_done": False,
        "text_elapsed_ms": 0,
        "tts_wait_ms": 0,
        "total_elapsed_ms": 0,
    }
    # Phase 1: wait for text reply.
    try:
        reply = ui.wait_for_lori_turn(since_ts, timeout_ms=text_timeout_ms) or ""
    except Exception as e:
        reply = ""
        out["error"] = f"wait_for_lori_turn threw: {e}"
    text_done_ts = time.time()
    out["reply"] = reply
    out["text_elapsed_ms"] = int((text_done_ts - t0) * 1000)
    if not reply:
        out["total_elapsed_ms"] = out["text_elapsed_ms"]
        return out
    # Capture JS-side timestamp of text completion. TTS finish on JS side
    # is recorded in milliseconds via Date.now(); compare apples-to-apples.
    try:
        text_done_js_ms = ui.page.evaluate("Date.now()")
    except Exception:
        text_done_js_ms = int(text_done_ts * 1000)
    # Phase 2: poll for TTS finished.
    deadline = text_done_ts + (tts_timeout_ms / 1000.0)
    while time.time() < deadline:
        try:
            tts_finished_ms = ui.page.evaluate(
                "((window.state && window.state.narratorTurn && "
                "  window.state.narratorTurn.ttsFinishedAt) || 0)"
            )
        except Exception:
            tts_finished_ms = 0
        if tts_finished_ms and tts_finished_ms >= text_done_js_ms:
            out["tts_done"] = True
            break
        ui.page.wait_for_timeout(300)
    out["tts_wait_ms"] = int((time.time() - text_done_ts) * 1000)
    # Phase 3: small settle so any state reconciliation completes before
    # the next user turn fires.
    if settle_ms > 0:
        ui.page.wait_for_timeout(settle_ms)
    out["total_elapsed_ms"] = int((time.time() - t0) * 1000)
    return out


def _send_chat_and_wait(
    ui: UI,
    label: str,
    text: str,
    *,
    timeout_ms: int = 120_000,
) -> StepResult:
    """Send a chat turn, wait for Lori's full completion (text + TTS),
    capture state, return StepResult.

    v2 (2026-05-04): replaced raw wait_for_lori_turn with
    _wait_for_lori_complete which gates on TTS finish. This kills the
    race that produced ~50% of the "no Lori reply" REDs in test23_v1."""
    sr = StepResult(label=label, narrator_input=text)
    t0 = time.time()
    try:
        since = ui.send_chat(text)
        complete = _wait_for_lori_complete(
            ui, since,
            text_timeout_ms=timeout_ms,
            tts_timeout_ms=60_000,
            settle_ms=500,
        )
        sr.lori_reply = complete.get("reply") or ""
        # Stash TTS gate metadata on the step for the report.
        if not complete.get("tts_done"):
            sr.notes.append(
                f"TTS not confirmed finished within "
                f"{60_000//1000}s of text completion"
            )
        sr.notes.append(
            f"text_elapsed={complete.get('text_elapsed_ms')}ms "
            f"tts_wait={complete.get('tts_wait_ms')}ms "
            f"tts_done={complete.get('tts_done')}"
        )
    except Exception as e:
        sr.lori_reply = ""
        sr.severity = "RED"
        sr.notes.append(f"send_chat threw: {e}")
    sr.elapsed_ms = int((time.time() - t0) * 1000)
    if not sr.lori_reply:
        sr.severity = "RED"
        sr.notes.append(f"no Lori reply within {int(timeout_ms / 1000)}s text-window")
    sr.state_after = _capture_bb_state(ui.page)
    return sr


def _click_era_canonical(ui: UI, era_label: str, era_id: str) -> Tuple[bool, bool, Optional[str]]:
    """Click an era in the Life Map. Returns (clicked, log_seen, current_era_after)."""
    before_click_count = len(ui.console.matches(r"\[life-map\]\[era-click\] era="))
    clicked = False
    try:
        clicked = ui.click_life_map_era(era_label)
    except Exception:
        clicked = False
    if not clicked:
        # Fallback: click by data-era-id selector
        clicked = click_era_button_data_attr(ui.page, era_id)
        if clicked:
            try:
                ui.confirm_era_popover()
            except Exception:
                pass
    ui.page.wait_for_timeout(700)
    after_click_count = len(ui.console.matches(r"\[life-map\]\[era-click\] era="))
    log_seen = after_click_count > before_click_count
    state = _capture_bb_state(ui.page)
    return clicked, log_seen, state.get("currentEra")


def _grade_recall(
    label: str,
    question: str,
    reply: str,
    plan: NarratorPlan,
    other_plan: Optional[NarratorPlan] = None,
) -> RecallResult:
    """Score a 'what do you know about me' style answer."""
    rr = RecallResult(label=label, question=question, reply=reply)
    rl = (reply or "").lower()
    # Name presence (firstName OR lastName OR fullName fragment)
    rr.contains_name = (
        plan.expected_first_name.lower() in rl
        or plan.expected_last_name.lower() in rl
    )
    # DOB presence (year fragment OR full date OR canonical form)
    year = plan.expected_dob[:4]
    rr.contains_dob_or_year = (year in reply) or (plan.expected_dob in reply)
    # POB presence
    pob_token = plan.expected_pob.split(",")[0].strip().lower()
    rr.contains_pob = pob_token in rl
    # Era fact recall
    facts_total = 0
    facts_hit = 0
    for era_id, fact_tokens in plan.expected_era_facts.items():
        for t in fact_tokens:
            facts_total += 1
            if t.lower() in rl:
                facts_hit += 1
                break  # one hit per era is enough; move on
    rr.era_stories_in_readback = facts_hit
    rr.era_stories_total = len(plan.expected_era_facts)  # 7 eras
    # Cross-contamination check — does THIS narrator's reply contain the
    # OTHER narrator's distinctive tokens?
    if other_plan is not None:
        other_tokens = [
            other_plan.expected_first_name.lower(),
            other_plan.expected_last_name.lower(),
            other_plan.expected_pob.split(",")[0].strip().lower(),
        ]
        if any(t in rl for t in other_tokens if len(t) >= 3):
            rr.cross_contamination = True
    # Onboarding-restart check (Lori shouldn't ask name/dob/pob again on resume)
    onboarding_phrases = (
        "what's your name",
        "what is your name",
        "your preferred name",
        "tell me your name",
        "when were you born",
        "what's your date of birth",
        "where were you born",
    )
    rr.onboarding_restart = any(p in rl for p in onboarding_phrases)
    # Severity grading — accept ≥3 era facts as PASS bar per Chris's spec
    issues: List[str] = []
    if not rr.contains_name:
        issues.append("name not recalled")
    if not rr.contains_pob:
        issues.append("place of birth not recalled")
    if rr.era_stories_in_readback < 3:
        issues.append(
            f"only {rr.era_stories_in_readback}/{rr.era_stories_total} "
            f"era stories surfaced in readback (<3) — this measures whether "
            f"'what do you know about me' includes era memories, NOT whether "
            f"era-click navigation works"
        )
    if rr.cross_contamination:
        issues.append("CROSS-CONTAMINATION: other narrator's data leaked")
    if rr.onboarding_restart:
        issues.append("onboarding restart (Lori asked for name/DOB/POB on resume)")
    if not issues:
        rr.severity = "PASS"
    elif rr.cross_contamination or rr.onboarding_restart or not rr.contains_name:
        rr.severity = "RED"
    else:
        rr.severity = "AMBER"
    rr.notes = issues
    return rr


# ──────────────────────────────────────────────────────────────────────
# Phases
# ──────────────────────────────────────────────────────────────────────


def _phase_onboard(ui: UI, plan: NarratorPlan, nr: NarratorReport) -> None:
    print(f"\n[{plan.key}/onboard] starting onboarding")
    phase_start = time.time()
    # Step 1: name
    sr = _send_chat_and_wait(ui, "onboard_name", plan.name_chat_input, timeout_ms=120_000)
    nr.onboarding_steps.append(sr)
    print(f"  [{plan.key}/onboard/name] sent='{plan.name_chat_input}' elapsed={sr.elapsed_ms}ms reply={len(sr.lori_reply.split())}w")
    # Step 2: DOB
    sr = _send_chat_and_wait(ui, "onboard_dob", plan.dob_chat_input, timeout_ms=90_000)
    nr.onboarding_steps.append(sr)
    print(f"  [{plan.key}/onboard/dob] sent='{plan.dob_chat_input}' elapsed={sr.elapsed_ms}ms")
    # Step 3: POB (initial messy / clean)
    sr = _send_chat_and_wait(ui, "onboard_pob", plan.pob_chat_input, timeout_ms=90_000)
    nr.onboarding_steps.append(sr)
    print(f"  [{plan.key}/onboard/pob] sent='{plan.pob_chat_input}' elapsed={sr.elapsed_ms}ms")
    # Step 4: optional correction (Mary only)
    if plan.pob_correction_input:
        sr = _send_chat_and_wait(ui, "onboard_pob_correction", plan.pob_correction_input, timeout_ms=120_000)
        nr.onboarding_steps.append(sr)
        print(f"  [{plan.key}/onboard/pob_correction] sent='{plan.pob_correction_input[:60]}...' elapsed={sr.elapsed_ms}ms")
        # v2 BUG-MARY-CORRECTION-PERSISTENCE diagnostic — capture BB state
        # IMMEDIATELY after the correction turn so we can compare it
        # against post-restart resume state. test23_v1 showed Mary lost
        # name+POB after restart but Marvin (no correction) retained
        # them. This snapshot lets us prove whether the correction wrote
        # successfully here, then was lost on restart, vs never wrote.
        nr.bb_state_after_correction = _capture_bb_state(ui.page)
        print(f"  [{plan.key}/onboard/post_correction_BB] "
              f"path={nr.bb_state_after_correction.get('bb_path')!r} "
              f"firstName={nr.bb_state_after_correction.get('firstName')!r} "
              f"lastName={nr.bb_state_after_correction.get('lastName')!r} "
              f"DOB={nr.bb_state_after_correction.get('dateOfBirth')!r} "
              f"POB={nr.bb_state_after_correction.get('placeOfBirth')!r}")
    # Capture identity state after onboarding
    nr.bb_state_after_onboard = _capture_bb_state(ui.page)
    print(f"  [{plan.key}/onboard] captured BB state: "
          f"path={nr.bb_state_after_onboard.get('bb_path')!r} "
          f"firstName={nr.bb_state_after_onboard.get('firstName')!r} "
          f"lastName={nr.bb_state_after_onboard.get('lastName')!r} "
          f"DOB={nr.bb_state_after_onboard.get('dateOfBirth')!r} "
          f"POB={nr.bb_state_after_onboard.get('placeOfBirth')!r} "
          f"basics={nr.bb_state_after_onboard.get('basicsComplete')}")
    print(f"  [{plan.key}/onboard] state.person keys: "
          f"{nr.bb_state_after_onboard.get('state_person_keys')}")
    # Status seed (Marvin only — Mary's widow signal surfaces in later_years era seed)
    if plan.status_seed:
        sr = _send_chat_and_wait(ui, "status_seed", plan.status_seed, timeout_ms=120_000)
        nr.onboarding_steps.append(sr)
        # v2 emotional-anchoring diagnostic — capture BB state and
        # specifically family.spouse so we can verify whether the
        # widower seed got extracted to the structured spouse field.
        # test23_v1 showed Marvin's spouse_memory_probe came back 0/5
        # — either extraction skipped this turn, binding failed, or
        # memory_echo doesn't surface family.spouse status. Snapshot
        # the immediate post-seed state to start the trace.
        nr.bb_state_after_status_seed = _capture_bb_state(ui.page)
        spouse_after = nr.bb_state_after_status_seed.get("spouse")
        print(f"  [{plan.key}/onboard/status] sent (widower seed) — "
              f"BB family.spouse={spouse_after!r}")
        if not spouse_after:
            print(f"    ⚠ family.spouse is empty after widower seed — "
                  f"extraction may not have written spouse status.")
    # Grade onboarding correctness
    bb = nr.bb_state_after_onboard
    if bb.get("firstName") != plan.expected_first_name:
        nr.notes.append(
            f"firstName mismatch: got {bb.get('firstName')!r}, expected {plan.expected_first_name!r}"
        )
    if bb.get("lastName") != plan.expected_last_name:
        nr.notes.append(
            f"lastName mismatch: got {bb.get('lastName')!r}, expected {plan.expected_last_name!r}"
        )
    if bb.get("dateOfBirth") != plan.expected_dob:
        nr.notes.append(
            f"DOB mismatch: got {bb.get('dateOfBirth')!r}, expected {plan.expected_dob!r}"
        )
    pob_actual = (bb.get("placeOfBirth") or "")
    if plan.expected_pob.lower() not in pob_actual.lower():
        # POB normalization is fuzzy; if state says "Minot, ND" instead of
        # "Minot, North Dakota", that's AMBER not RED — Lori still has the
        # city; the abbreviation expansion was the test target.
        nr.notes.append(
            f"POB partial: got {pob_actual!r}, expected {plan.expected_pob!r}"
        )
    nr.apilog_signals_per_phase["onboard"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/onboard", nr.apilog_signals_per_phase["onboard"])


def _phase_lifemap_walk(ui: UI, plan: NarratorPlan, nr: NarratorReport) -> None:
    print(f"\n[{plan.key}/lifemap] walking 7 eras (era-prompt FIRST, then seed)")
    phase_start = time.time()
    for label, era_id, _framing in LIFE_MAP_ERAS_CANONICAL:
        if era_id == "today":
            # Today gets handled by _phase_today_cycles
            continue
        er = EraStepResult(era_id=era_id, era_label=label)
        # ── Phase 1: click era and capture Lori's SPONTANEOUS era prompt ──
        # Note "since" timestamp BEFORE the click so we capture the prompt
        # that fires from sendSystemPrompt(era_directive).
        click_since = ui.console.now() - 0.1
        clicked, log_seen, current_era = _click_era_canonical(ui, label, era_id)
        er.click_log_seen = log_seen
        er.current_era_after = current_era
        if not clicked:
            er.severity = "RED"
            er.notes.append("era click failed (UI helper returned false)")
            nr.era_results.append(er)
            print(f"  [{plan.key}/lifemap/{era_id}] CLICK FAILED")
            continue
        # Wait for Lori's era prompt (with TTS gate)
        prompt_complete = _wait_for_lori_complete(
            ui, click_since,
            text_timeout_ms=90_000,
            tts_timeout_ms=60_000,
            settle_ms=500,
        )
        er.era_prompt_reply = prompt_complete.get("reply") or ""
        rl_prompt = er.era_prompt_reply.lower()
        anchors = plan.expected_era_facts.get(era_id, [])
        er.era_prompt_anchored = any(t.lower() in rl_prompt for t in anchors)
        er.era_prompt_question_count = er.era_prompt_reply.count("?")
        if not er.era_prompt_reply:
            er.notes.append("no Lori spontaneous prompt after era click within 90s")
        # ── Phase 2: send the era seed AFTER Lori finishes prompting ──
        seed_text = plan.era_seeds.get(era_id, "")
        er.seed_text = seed_text
        sr = _send_chat_and_wait(ui, f"era_seed_{era_id}", seed_text, timeout_ms=120_000)
        er.seed_reply = sr.lori_reply
        rl_seed = (sr.lori_reply or "").lower()
        seed_anchored = any(t.lower() in rl_seed for t in anchors)
        # Combined era_anchored — prompt OR seed contains anchor tokens.
        er.era_anchored = er.era_prompt_anchored or seed_anchored
        # Severity:
        if not er.era_prompt_reply and not sr.lori_reply:
            er.severity = "RED"
            er.notes.append("no Lori reply for either era prompt or seed")
        elif not sr.lori_reply:
            er.severity = "AMBER"
            er.notes.append("era prompt captured but no follow-up to seed")
        elif not er.era_anchored:
            er.severity = "AMBER"
            er.notes.append("Lori replied but didn't echo any era-fact token in prompt or seed")
        # Mid-stream extra (ChatGPT addition): correction or ambiguity probe
        extra_text = plan.era_extras.get(era_id)
        if extra_text:
            er.extra_text = extra_text
            esr = _send_chat_and_wait(ui, f"era_extra_{era_id}", extra_text, timeout_ms=90_000)
            er.extra_reply = esr.lori_reply
            elr = (esr.lori_reply or "").lower()
            # Probe-specific check
            if "actually" in extra_text.lower() and ("only" in extra_text.lower() or "not" in extra_text.lower()):
                # Mid-stream correction (Mary): Lori should ACK the correction
                # without restarting onboarding. Look for acknowledgment markers.
                ack_markers = (
                    "two", "correction", "got it", "thank you", "noted",
                    "i'll remember", "i hear you", "i understand",
                )
                er.extra_handled_well = any(m in elr for m in ack_markers)
                if not er.extra_handled_well:
                    er.notes.append("mid-stream correction not clearly acknowledged")
                    if er.severity == "PASS":
                        er.severity = "AMBER"
            elif "maybe" in extra_text.lower() or "or" in extra_text.lower() or "…" in extra_text:
                # Ambiguity probe (Marvin): Lori should NOT over-assert a date
                # she should instead reflect uncertainty / accept fuzzy framing
                over_assert_markers = (
                    "definitely 1965", "exactly 1965", "in 1965, when you",
                )
                er.extra_handled_well = not any(m in elr for m in over_assert_markers)
                if not er.extra_handled_well:
                    er.notes.append("Lori over-asserted ambiguous date as fact")
                    er.severity = "RED"
            print(f"  [{plan.key}/lifemap/{era_id}] EXTRA sent='{extra_text[:60]}' "
                  f"reply={len(esr.lori_reply.split())}w handled_well={er.extra_handled_well}")
        # Log marker check (informational, not load-bearing)
        prompt_logs = ui.console.matches(r"\[life-map\]\[era-click\] Lori prompt dispatched")
        er.prompt_log_seen = bool(prompt_logs)
        nr.era_results.append(er)
        prompt_w = len(er.era_prompt_reply.split()) if er.era_prompt_reply else 0
        seed_w = len(er.seed_reply.split()) if er.seed_reply else 0
        print(f"  [{plan.key}/lifemap/{era_id}] click_log={log_seen} era={current_era} "
              f"prompt={prompt_w}w (anchored={er.era_prompt_anchored} q={er.era_prompt_question_count}) "
              f"seed={seed_w}w anchored={er.era_anchored} {er.severity}")
    nr.apilog_signals_per_phase["lifemap"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/lifemap", nr.apilog_signals_per_phase["lifemap"])


def _phase_today_cycles(ui: UI, plan: NarratorPlan, nr: NarratorReport) -> None:
    print(f"\n[{plan.key}/today] 2 cycles + factual interruption")
    phase_start = time.time()
    # Click Today
    clicked, _log, cur = _click_era_canonical(ui, "Today", "today")
    if not clicked:
        nr.notes.append("today click failed; cycles aborted")
        return
    # Two Today cycles — re-use today seed text from era_seeds, plus a follow-up
    today_a = plan.era_seeds.get("today", "")
    today_b = (
        "I still think about everything that came before, but I try to stay in the day."
        if plan.key == "mary"
        else "I still miss my wife, but I try to notice small good things each day."
    )
    for i, txt in enumerate([today_a, today_b], 1):
        sr = _send_chat_and_wait(ui, f"today_cycle_{i}", txt, timeout_ms=90_000)
        nr.today_cycles.append(sr)
        # Soft check: present-tense markers
        rl = (sr.lori_reply or "").lower()
        if any(p in rl for p in ("today", "now", "right now", "these days", "currently")):
            sr.notes.append("present-tense marker present")
        else:
            sr.notes.append("no clear present-tense marker")
            if sr.severity == "PASS":
                sr.severity = "AMBER"
        print(f"  [{plan.key}/today/cycle{i}] elapsed={sr.elapsed_ms}ms severity={sr.severity}")
    # Factual interruption
    sr = _send_chat_and_wait(ui, "today_factual_what_day", "what day is it", timeout_ms=90_000)
    nr.today_factual = sr
    rl = (sr.lori_reply or "").lower()
    # Acceptable shapes: gives a date, asks gentle clarification, says "I don't have a calendar"
    onboarding_restart = any(p in rl for p in ("your name", "preferred name", "when were you born"))
    if onboarding_restart:
        sr.severity = "RED"
        sr.notes.append("FACTUAL INTERRUPTION restarted onboarding")
    elif not sr.lori_reply:
        sr.severity = "RED"
        sr.notes.append("no reply to factual question")
    print(f"  [{plan.key}/today/factual] reply={len(sr.lori_reply.split())}w severity={sr.severity}")
    nr.apilog_signals_per_phase["today"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/today", nr.apilog_signals_per_phase["today"])


def _expected_age_today(plan: NarratorPlan) -> int:
    today = dt.date.today()
    try:
        dob = dt.date.fromisoformat(plan.expected_dob)
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except ValueError:
        return -1


def _check_age_guess(reply: str, expected: int) -> Tuple[bool, List[int]]:
    """Return (hit, near_matches) where hit=True if reply contains a number
    within ±1 of expected. Wide-net check; the spec is 'reasonable
    approximation, not exact'."""
    if expected <= 0:
        return False, []
    rl = (reply or "").lower()
    hits: List[int] = []
    for offset in range(-2, 3):    # accept ±2 years as reasonable
        n = expected + offset
        if re.search(rf"\b{n}\b", rl):
            hits.append(n)
    return bool(hits), hits


def _phase_early_inference_probes(ui: UI, plan: NarratorPlan, nr: NarratorReport) -> None:
    """ChatGPT's hallucination test: right after onboarding, ask Lori to
    guess the narrator's age + where they live now. Age should be reasonable
    (±2 years from DOB-derived). Residence should be admit-or-ask, NOT a
    hallucinated location."""
    print(f"\n[{plan.key}/early_inference] age + residence probes (right after onboarding)")
    phase_start = time.time()
    expected_age = _expected_age_today(plan)
    # AGE probe
    sr_age = _send_chat_and_wait(ui, "early_age_guess", "How old do you think I am?", timeout_ms=90_000)
    nr.early_inference_steps.append(sr_age)
    age_hit, age_hits = _check_age_guess(sr_age.lori_reply, expected_age)
    if age_hit:
        sr_age.notes.append(f"age guess hit (expected={expected_age}, found={age_hits})")
    else:
        sr_age.notes.append(f"age guess miss (expected={expected_age})")
        if sr_age.severity == "PASS":
            sr_age.severity = "AMBER"
    # Hallucination check: does Lori give a wildly wrong number?
    rl_age = (sr_age.lori_reply or "").lower()
    wild_numbers = re.findall(r"\b(\d{2,3})\b", rl_age)
    wild_hits = [int(n) for n in wild_numbers if abs(int(n) - expected_age) > 10 and 10 < int(n) < 120]
    if wild_hits and not age_hit:
        sr_age.notes.append(f"WILD age guess: {wild_hits} (expected ~{expected_age})")
        sr_age.severity = "RED"
    print(f"  [{plan.key}/early_inference/age] expected={expected_age} hit={age_hit} severity={sr_age.severity}")
    # RESIDENCE probe
    sr_loc = _send_chat_and_wait(ui, "early_residence_guess", "Where do you think I live now?", timeout_ms=90_000)
    nr.early_inference_steps.append(sr_loc)
    rl_loc = (sr_loc.lori_reply or "").lower()
    admits_not_known = any(p in rl_loc for p in (
        "i don't know", "i'm not sure", "you haven't told me", "i don't have",
        "not on record", "not yet", "can you tell me", "haven't shared",
        "i wouldn't know", "haven't said",
    ))
    asks_directly = ("where do you live" in rl_loc
                     or "where are you now" in rl_loc
                     or "where you live" in rl_loc)
    # POB-echo is allowed ONLY if Lori explicitly frames it as POB ("you were born in...")
    pob_token = plan.expected_pob.split(",")[0].strip().lower()
    pob_echo = pob_token in rl_loc
    pob_framed = pob_echo and any(p in rl_loc for p in ("born in", "your birthplace", "where you were born"))
    if admits_not_known or asks_directly:
        sr_loc.notes.append("residence: admits-or-asks (good)")
    elif pob_framed:
        sr_loc.notes.append("residence: echoed POB with framing (acceptable)")
    elif pob_echo:
        sr_loc.notes.append("residence: name dropped POB without 'born in' framing (ambiguous)")
        if sr_loc.severity == "PASS":
            sr_loc.severity = "AMBER"
    else:
        # Did Lori name a city we never gave?
        wild_cities = ("seattle", "minneapolis", "denver", "phoenix", "chicago",
                       "florida", "california", "texas", "los angeles", "new york",
                       "boston", "portland")
        wild_hits = [c for c in wild_cities if c in rl_loc]
        if wild_hits:
            sr_loc.notes.append(f"HALLUCINATED RESIDENCE: {wild_hits}")
            sr_loc.severity = "RED"
        else:
            sr_loc.notes.append("residence: ambiguous response (review manually)")
            if sr_loc.severity == "PASS":
                sr_loc.severity = "AMBER"
    print(f"  [{plan.key}/early_inference/residence] reply={len(sr_loc.lori_reply.split())}w severity={sr_loc.severity}")
    nr.apilog_signals_per_phase["early_inference"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/early_inference", nr.apilog_signals_per_phase["early_inference"])


def _phase_late_age_probe(ui: UI, plan: NarratorPlan, nr: NarratorReport) -> None:
    """Late-stage age inference: 'How old do you think I am now?' AFTER full
    Life Map walk + Today cycles. Tests integrated memory recall with stored
    DOB. Compare consistency vs early inference probe."""
    print(f"\n[{plan.key}/late_age] late-stage age probe")
    phase_start = time.time()
    sr = _send_chat_and_wait(ui, "late_age_probe", "How old do you think I am now?", timeout_ms=90_000)
    nr.late_age_probe = sr
    expected_age = _expected_age_today(plan)
    age_hit, age_hits = _check_age_guess(sr.lori_reply, expected_age)
    if age_hit:
        sr.notes.append(f"late age hit (expected={expected_age}, found={age_hits})")
    else:
        sr.notes.append(f"late age miss (expected={expected_age})")
        if sr.severity == "PASS":
            sr.severity = "AMBER"
    # Compare to early probe — consistency check
    early_age_step = next((s for s in nr.early_inference_steps if s.label == "early_age_guess"), None)
    if early_age_step:
        early_hit, early_hits = _check_age_guess(early_age_step.lori_reply, expected_age)
        if early_hit and not age_hit:
            sr.notes.append("REGRESSION: early probe got age right; late probe missed")
            sr.severity = "RED"
        elif not early_hit and age_hit:
            sr.notes.append("IMPROVEMENT: early probe missed; late probe hit (memory consolidating)")
        elif early_hits and age_hits:
            if set(early_hits) & set(age_hits):
                sr.notes.append(f"consistent age across probes: {set(early_hits) & set(age_hits)}")
            else:
                sr.notes.append(f"INCONSISTENT: early={early_hits} late={age_hits}")
                if sr.severity == "PASS":
                    sr.severity = "AMBER"
    print(f"  [{plan.key}/late_age] expected={expected_age} hit={age_hit} severity={sr.severity}")
    nr.apilog_signals_per_phase["late_age"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/late_age", nr.apilog_signals_per_phase["late_age"])


def _phase_spouse_memory_probe(ui: UI, plan: NarratorPlan, nr: NarratorReport) -> None:
    """Marvin only: 'What do you remember about my wife?' AFTER recall.
    Tests emotional anchoring + correct attribution. Lori should reference
    widower status, letters/drawer detail from later_years, or the morning
    routine from status seed."""
    if not plan.spouse_memory_probe:
        return
    print(f"\n[{plan.key}/spouse_probe] emotional memory cross-check")
    phase_start = time.time()
    sr = _send_chat_and_wait(ui, "spouse_memory_probe", plan.spouse_memory_probe, timeout_ms=90_000)
    nr.spouse_memory_probe = sr
    rl = (sr.lori_reply or "").lower()
    hits = [t for t in plan.expected_spouse_tokens if t.lower() in rl]
    sr.notes.append(f"spouse tokens hit: {hits}/{plan.expected_spouse_tokens}")
    if len(hits) >= 2:
        sr.notes.append("emotional anchoring intact (≥2 spouse tokens recalled)")
    elif len(hits) == 1:
        sr.notes.append("partial recall (1 spouse token)")
        if sr.severity == "PASS":
            sr.severity = "AMBER"
    else:
        sr.notes.append("FAILED emotional anchoring (0 spouse tokens recalled)")
        sr.severity = "RED"
    # Hallucination check: does Lori mention the OTHER narrator's spouse details?
    if any(t in rl for t in ("husband", "county fair", "mary's")):
        sr.notes.append("CROSS-CONTAMINATION: Mary's spouse details leaked into Marvin's spouse recall")
        sr.severity = "RED"
    print(f"  [{plan.key}/spouse_probe] hits={len(hits)} severity={sr.severity}")
    nr.apilog_signals_per_phase["spouse_probe"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/spouse_probe", nr.apilog_signals_per_phase["spouse_probe"])


def _phase_earliest_recall(ui: UI, plan: NarratorPlan, nr: NarratorReport,
                           other_plan: Optional[NarratorPlan]) -> None:
    """Click Earliest Years, then ask 'what do you know about me'."""
    print(f"\n[{plan.key}/recall_pre] click Earliest Years + 'what do you know about me'")
    phase_start = time.time()
    clicked, _log, _cur = _click_era_canonical(ui, "Earliest Years", "earliest_years")
    if not clicked:
        nr.notes.append("Earliest Years click failed before pre-restart recall")
    sr = _send_chat_and_wait(ui, "pre_restart_what_do_you_know", "what do you know about me", timeout_ms=120_000)
    rr = _grade_recall(
        label="pre_restart_recall",
        question="what do you know about me",
        reply=sr.lori_reply,
        plan=plan,
        other_plan=other_plan,
    )
    nr.pre_restart_recall = rr
    nr.bb_state_after_session1 = _capture_bb_state(ui.page)
    print(f"  [{plan.key}/recall_pre] name={rr.contains_name} dob/yr={rr.contains_dob_or_year} "
          f"pob={rr.contains_pob} story_recall={rr.era_stories_in_readback}/{rr.era_stories_total} "
          f"contam={rr.cross_contamination} restart={rr.onboarding_restart} severity={rr.severity}")
    if rr.notes:
        for n in rr.notes:
            print(f"      • {n}")
    nr.apilog_signals_per_phase["recall_pre"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/recall_pre", nr.apilog_signals_per_phase["recall_pre"])


def _phase_resume(
    ui: UI,
    plan: NarratorPlan,
    nr: NarratorReport,
    other_plan: Optional[NarratorPlan],
) -> None:
    """Post-restart: ask 'what do you know about me', then Today + 'what day is it'."""
    print(f"\n[{plan.key}/resume] post-restart recall + Today")
    phase_start = time.time()
    sr_recall = _send_chat_and_wait(ui, "post_restart_what_do_you_know",
                                    "what do you know about me", timeout_ms=120_000)
    rr = _grade_recall(
        label="post_restart_recall",
        question="what do you know about me",
        reply=sr_recall.lori_reply,
        plan=plan,
        other_plan=other_plan,
    )
    nr.post_restart_recall = rr
    print(f"  [{plan.key}/resume/recall] name={rr.contains_name} pob={rr.contains_pob} "
          f"story_recall={rr.era_stories_in_readback}/{rr.era_stories_total} contam={rr.cross_contamination} "
          f"restart={rr.onboarding_restart} severity={rr.severity}")
    if rr.notes:
        for n in rr.notes:
            print(f"      • {n}")
    # Click Today, ask "what day is it"
    clicked, _log, _cur = _click_era_canonical(ui, "Today", "today")
    if not clicked:
        nr.notes.append("Today click failed post-restart")
    sr_today = _send_chat_and_wait(ui, "post_restart_today_what_day", "what day is it", timeout_ms=90_000)
    nr.today_after_resume = sr_today
    rl = (sr_today.lori_reply or "").lower()
    if any(p in rl for p in ("your name", "preferred name", "when were you born")):
        sr_today.severity = "RED"
        sr_today.notes.append("Today factual question RESTARTED ONBOARDING after resume")
    elif not sr_today.lori_reply:
        sr_today.severity = "RED"
        sr_today.notes.append("no reply post-restart")
    print(f"  [{plan.key}/resume/today_factual] reply={len(sr_today.lori_reply.split())}w severity={sr_today.severity}")
    nr.bb_state_after_resume = _capture_bb_state(ui.page)
    nr.apilog_signals_per_phase["resume"] = _apilog_window_signals(phase_start, time.time())
    _print_signal_delta(f"{plan.key}/resume", nr.apilog_signals_per_phase["resume"])


# ──────────────────────────────────────────────────────────────────────
# Per-narrator orchestrator
# ──────────────────────────────────────────────────────────────────────


def _run_narrator_session1(
    ui: UI,
    plan: NarratorPlan,
    other_plan: Optional[NarratorPlan],
    nr: NarratorReport,
    telemetry: Optional[TelemetryRecorder] = None,
) -> None:
    """Pre-restart phases: onboard → lifemap → today × 2 → bonus → recall."""
    # Add narrator (creates via API + switches via lv80ConfirmNarratorSwitch)
    print(f"\n=== {plan.key.upper()} — session 1 ===")
    print(f"  [{plan.key}] creating narrator '{plan.display_name}'")
    # Override the auto-generated Test_<id> name by patching display_name
    # post-creation isn't trivial via UI; use add_test_narrator and let the
    # captured fullName drive the display label downstream. We track the
    # person_id for re-selection.
    try:
        actual_display_name = ui.add_test_narrator("clear_direct")
        nr.display_name = actual_display_name  # may not match plan.display_name; track actual
    except Exception as e:
        nr.notes.append(f"add_test_narrator threw: {e}")
        nr.severity = "RED"
        return
    # Capture pid for re-selection post-restart
    state = _capture_bb_state(ui.page)
    nr.person_id = state.get("person_id") or ""
    print(f"  [{plan.key}] person_id={nr.person_id} actual_display={actual_display_name!r}")
    # session_start kicks off identityOnboarding
    try:
        ui.session_start()
    except Exception as e:
        nr.notes.append(f"session_start threw: {e}")
    ui.page.wait_for_timeout(2000)
    # Consume the askName intro (Lori prompts the narrator before T1)
    try:
        intro_since = ui.console.now() - 5.0
        intro = ui.wait_for_lori_turn(intro_since, timeout_ms=120_000) or ""
        print(f"  [{plan.key}] askName intro consumed ({len(intro.split())}w)")
    except Exception:
        pass
    # Phases — ChatGPT TEST-23 ordering:
    #   1. Onboarding (identity intake, with optional correction + status seed)
    #   2. Early inference probes (age + residence guess — hallucination test)
    #   3. Life Map walk (7 eras, with mid-stream correction/ambiguity extras)
    #   4. Today × 2 cycles + factual interruption
    #   5. Late-stage age probe (memory consolidation check)
    #   6. Earliest Years jump + memory recall
    #   7. (Marvin only) spouse memory probe — emotional anchoring + attribution
    if telemetry: telemetry.record_snapshot(f"{plan.key}/session1_start", {"plan_key": plan.key})
    _phase_onboard(ui, plan, nr)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/onboard_done")
    _phase_early_inference_probes(ui, plan, nr)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/early_inference_done")
    _phase_lifemap_walk(ui, plan, nr)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/lifemap_done")
    _phase_today_cycles(ui, plan, nr)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/today_done")
    _phase_late_age_probe(ui, plan, nr)
    _phase_earliest_recall(ui, plan, nr, other_plan)
    _phase_spouse_memory_probe(ui, plan, nr)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/session1_end")
    # v2: capture Memoir Peek + Save TXT export BEFORE wrap_session, while
    # the narrator is still loaded. Lets us compare what Lori thinks she
    # has at end-of-session-1 vs at post-restart-resume.
    try:
        artifact = _save_memoir_artifact(
            ui.page,
            _RUNTIME_CONFIG.get("reports_dir", _REPORTS_DIR),
            _RUNTIME_CONFIG.get("tag", "test23"),
            plan.key,
            "session1_end",
        )
        nr.memoir_artifacts.append(artifact)
        print(f"  [{plan.key}/session1_end] memoir captured: "
              f"peek={artifact.get('peek_chars')}c export={artifact.get('export_chars')}c "
              f"peek_path={artifact.get('peek_path', 'n/a')!s} "
              f"export_path={artifact.get('export_path', 'n/a')!s}")
    except Exception as e:
        print(f"  [{plan.key}/session1_end] memoir capture threw: {e}", file=sys.stderr)
    # Wrap session
    try:
        ui.wrap_session()
        print(f"  [{plan.key}] session wrapped")
    except Exception:
        pass


def _restart_browser_and_resume(
    pw_browser: Browser,
    plan: NarratorPlan,
    nr: NarratorReport,
    other_plan: Optional[NarratorPlan],
    base_url: str,
    reports_dir: Path,
    telemetry: Optional[TelemetryRecorder] = None,
) -> Tuple[BrowserContext, Page, UI, ConsoleCollector, DbLockCounter]:
    """Close current context, open a fresh one, navigate to UI, reload narrator
    by pid, and run resume phases. Returns the new context/page/ui for cleanup."""
    print(f"\n[{plan.key}/restart] cold restart — closing browser context")
    # Caller should have closed the previous context already
    # Open new context + page
    new_ctx = pw_browser.new_context(viewport={"width": 1400, "height": 900}, permissions=["camera", "microphone"])
    new_page = new_ctx.new_page()
    new_console = ConsoleCollector(new_page)
    new_dblock = DbLockCounter(_REPO_ROOT)
    new_ui = UI(new_page, new_console, reports_dir / "screenshots", reports_dir / "downloads")
    print(f"  [{plan.key}/restart] navigating to {base_url}")
    new_ui.boot(base_url)
    if not _wait_for_warm_stack(new_page, new_console, timeout_s=60):
        print(f"  [{plan.key}/restart] WARN — stack not warm within 60s")
    # Re-select the narrator we created earlier
    print(f"  [{plan.key}/restart] re-selecting narrator pid={nr.person_id}")
    ok = _select_narrator_by_pid(new_page, nr.person_id)
    if not ok:
        nr.notes.append(f"could not re-select narrator pid={nr.person_id} after restart")
    new_page.wait_for_timeout(2500)
    _close_popovers(new_page)
    # Capture state to confirm narrator loaded
    after_state = _capture_bb_state(new_page)
    print(f"  [{plan.key}/restart] post-reload state: "
          f"firstName={after_state.get('firstName')!r} "
          f"DOB={after_state.get('dateOfBirth')!r} "
          f"basics={after_state.get('basicsComplete')}")
    # Start session — narrator is loaded, identity should already be complete
    try:
        new_ui.session_start()
    except Exception as e:
        print(f"  [{plan.key}/restart] session_start threw: {e}")
    new_page.wait_for_timeout(2000)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/resume_started")
    # v2: capture Memoir Peek + Export at resume start, BEFORE we send
    # the recall question. Tells us what's persisted across the cold
    # close+reopen boundary independent of memory_echo.
    try:
        artifact = _save_memoir_artifact(
            new_page,
            _RUNTIME_CONFIG.get("reports_dir", reports_dir),
            _RUNTIME_CONFIG.get("tag", "test23"),
            plan.key,
            "resume_start",
        )
        nr.memoir_artifacts.append(artifact)
        print(f"  [{plan.key}/resume_start] memoir captured: "
              f"peek={artifact.get('peek_chars')}c export={artifact.get('export_chars')}c")
    except Exception as e:
        print(f"  [{plan.key}/resume_start] memoir capture threw: {e}", file=sys.stderr)
    # Run resume phase
    _phase_resume(new_ui, plan, nr, other_plan)
    if telemetry: telemetry.record_snapshot(f"{plan.key}/resume_done")
    return new_ctx, new_page, new_ui, new_console, new_dblock


# ──────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────


def _grade_narrator(nr: NarratorReport, plan: NarratorPlan) -> None:
    """Aggregate severity for a narrator from per-phase signals."""
    fails: List[str] = []
    ambers: List[str] = []
    # Onboarding correctness
    bb = nr.bb_state_after_onboard
    if bb.get("firstName") != plan.expected_first_name:
        fails.append(f"firstName != {plan.expected_first_name}")
    if bb.get("lastName") != plan.expected_last_name:
        fails.append(f"lastName != {plan.expected_last_name}")
    if bb.get("dateOfBirth") != plan.expected_dob:
        fails.append(f"DOB != {plan.expected_dob}")
    # Early inference probes
    for s in nr.early_inference_steps:
        if s.severity == "RED":
            fails.append(f"early_inference {s.label} RED ({'; '.join(s.notes)})")
        elif s.severity == "AMBER":
            ambers.append(f"early_inference {s.label} AMBER")
    # Era walk
    red_eras = [er.era_id for er in nr.era_results if er.severity == "RED"]
    if red_eras:
        fails.append(f"era walk RED: {red_eras}")
    amber_eras = [er.era_id for er in nr.era_results if er.severity == "AMBER"]
    if amber_eras:
        ambers.append(f"era walk AMBER: {amber_eras}")
    # Today cycles
    if any(s.severity == "RED" for s in nr.today_cycles):
        fails.append("today cycle RED")
    if nr.today_factual and nr.today_factual.severity == "RED":
        fails.append("today factual RED")
    # Late age probe
    if nr.late_age_probe and nr.late_age_probe.severity == "RED":
        fails.append("late age probe RED")
    elif nr.late_age_probe and nr.late_age_probe.severity == "AMBER":
        ambers.append("late age probe AMBER")
    # Recalls
    if nr.pre_restart_recall and nr.pre_restart_recall.severity == "RED":
        fails.append("pre-restart recall RED")
    elif nr.pre_restart_recall and nr.pre_restart_recall.severity == "AMBER":
        ambers.append("pre-restart recall AMBER")
    if nr.spouse_memory_probe and nr.spouse_memory_probe.severity == "RED":
        fails.append("spouse memory probe RED")
    elif nr.spouse_memory_probe and nr.spouse_memory_probe.severity == "AMBER":
        ambers.append("spouse memory probe AMBER")
    if nr.post_restart_recall and nr.post_restart_recall.severity == "RED":
        fails.append("post-restart recall RED")
    elif nr.post_restart_recall and nr.post_restart_recall.severity == "AMBER":
        ambers.append("post-restart recall AMBER")
    if nr.today_after_resume and nr.today_after_resume.severity == "RED":
        fails.append("today after resume RED")
    if fails:
        nr.severity = "RED"
        nr.notes.extend(fails)
    elif ambers:
        nr.severity = "AMBER"
        nr.notes.extend(ambers)
    else:
        nr.severity = "PASS"


def _build_md_report(report: RunReport, telemetry_summary: Optional[Dict[str, Any]] = None) -> str:
    lines: List[str] = []
    lines.append(f"# TEST-23 Two-Person Resume Canary — `{report.tag}`")
    lines.append("")
    lines.append(f"- started: {report.started_at}")
    lines.append(f"- finished: {report.finished_at}")
    lines.append(f"- commit: `{report.commit_sha}` dirty={report.dirty_tree}")
    lines.append(f"- base_url: {report.base_url}")
    lines.append(f"- api_base: {report.api_base}")
    lines.append("")
    lines.append(f"## Topline: **{report.final_severity}**")
    lines.append("")
    if report.mary:
        lines.append(f"- Mary Holts (messy): **{report.mary.severity}**")
    if report.marvin:
        lines.append(f"- Marvin Mann (clean): **{report.marvin.severity}**")
    if report.cross_isolation_check:
        lines.append(f"- Cross-narrator isolation: **{report.cross_isolation_check.severity}**")
    lines.append("")
    if report.final_failures:
        lines.append("### Final failures")
        for f in report.final_failures:
            lines.append(f"- {f}")
        lines.append("")
    for nr, plan in [(report.mary, MARY_PLAN), (report.marvin, MARVIN_PLAN)]:
        if not nr:
            continue
        lines.append(f"## {plan.display_name} (`{plan.key}`) — **{nr.severity}**")
        lines.append("")
        lines.append(f"- person_id: `{nr.person_id}`")
        lines.append("")
        lines.append("### Onboarding")
        lines.append("")
        lines.append("| Step | Sent | Reply (excerpt) | Severity | Elapsed |")
        lines.append("|---|---|---|---|---:|")
        for s in nr.onboarding_steps:
            lines.append(
                f"| {s.label} | `{s.narrator_input[:50]}` | "
                f"{(s.lori_reply[:80] + '…') if len(s.lori_reply) > 80 else s.lori_reply} | "
                f"{s.severity} | {s.elapsed_ms}ms |"
            )
        lines.append("")
        bb = nr.bb_state_after_onboard
        lines.append("**BB state after onboarding:**")
        lines.append("")
        lines.append(f"- firstName: `{bb.get('firstName')!r}` (expected `{plan.expected_first_name!r}`)")
        lines.append(f"- lastName: `{bb.get('lastName')!r}` (expected `{plan.expected_last_name!r}`)")
        lines.append(f"- DOB: `{bb.get('dateOfBirth')!r}` (expected `{plan.expected_dob!r}`)")
        lines.append(f"- POB: `{bb.get('placeOfBirth')!r}` (expected `{plan.expected_pob!r}`)")
        lines.append(f"- basics_complete: `{bb.get('basicsComplete')}`")
        lines.append("")
        lines.append("### Early inference probes (right after onboarding)")
        lines.append("")
        for s in nr.early_inference_steps:
            lines.append(
                f"**{s.label}:** sent=`{s.narrator_input}` reply=`"
                f"{(s.lori_reply[:200] + '…') if len(s.lori_reply) > 200 else s.lori_reply}"
                f"` severity={s.severity}"
            )
            for n in s.notes:
                lines.append(f"  - {n}")
            lines.append("")
        lines.append("### Life Map walk")
        lines.append("")
        lines.append("| Era | Click log | Era set | Reply (excerpt) | Anchored | Severity |")
        lines.append("|---|---|---|---|---|---|")
        for er in nr.era_results:
            lines.append(
                f"| {er.era_label} ({er.era_id}) | "
                f"{'✓' if er.click_log_seen else '✗'} | "
                f"{er.current_era_after or '?'} | "
                f"{(er.seed_reply[:70] + '…') if len(er.seed_reply) > 70 else er.seed_reply} | "
                f"{'✓' if er.era_anchored else '✗'} | "
                f"{er.severity} |"
            )
        lines.append("")
        # Render era extras (mid-stream corrections / ambiguity probes) separately
        extras_present = [er for er in nr.era_results if er.extra_text]
        if extras_present:
            lines.append("**Mid-stream extras (correction / ambiguity probes):**")
            lines.append("")
            for er in extras_present:
                lines.append(f"- **{er.era_label}** sent=`{er.extra_text}`")
                lines.append(f"  reply=`{(er.extra_reply[:200] + '…') if len(er.extra_reply) > 200 else er.extra_reply}`")
                lines.append(f"  handled_well={er.extra_handled_well}")
                lines.append("")
        lines.append("### Today cycles + factual interruption")
        lines.append("")
        for i, s in enumerate(nr.today_cycles, 1):
            lines.append(f"**Today cycle {i}:** sent=`{s.narrator_input[:60]}` "
                         f"reply=`{(s.lori_reply[:120] + '…') if len(s.lori_reply) > 120 else s.lori_reply}` "
                         f"severity={s.severity}")
            lines.append("")
        if nr.today_factual:
            lines.append(
                f"**Today factual ('what day is it'):** reply=`"
                f"{(nr.today_factual.lori_reply[:200] + '…') if len(nr.today_factual.lori_reply) > 200 else nr.today_factual.lori_reply}"
                f"` severity={nr.today_factual.severity}"
            )
            for n in nr.today_factual.notes:
                lines.append(f"  - {n}")
            lines.append("")
        if nr.late_age_probe:
            s = nr.late_age_probe
            lines.append("### Late-stage age probe (after Life Map walk + Today)")
            lines.append("")
            lines.append(
                f"sent=`{s.narrator_input}` reply=`"
                f"{(s.lori_reply[:200] + '…') if len(s.lori_reply) > 200 else s.lori_reply}"
                f"` severity={s.severity}"
            )
            for n in s.notes:
                lines.append(f"  - {n}")
            lines.append("")
        if nr.pre_restart_recall:
            rr = nr.pre_restart_recall
            lines.append("### Pre-restart memory recall (Earliest Years anchor + 'what do you know about me')")
            lines.append("")
            lines.append(f"- name recalled: {rr.contains_name}")
            lines.append(f"- DOB/year recalled: {rr.contains_dob_or_year}")
            lines.append(f"- POB recalled: {rr.contains_pob}")
            lines.append(
                f"- era stories in readback: {rr.era_stories_in_readback}/{rr.era_stories_total}  "
                f"(memory_echo readback content; NOT a measure of era-click navigation)"
            )
            lines.append(f"- cross-contamination: {rr.cross_contamination}")
            lines.append(f"- onboarding restart: {rr.onboarding_restart}")
            lines.append(f"- severity: **{rr.severity}**")
            lines.append("")
            lines.append(f"Reply excerpt: `{(rr.reply[:400] + '…') if len(rr.reply) > 400 else rr.reply}`")
            lines.append("")
        if nr.spouse_memory_probe:
            s = nr.spouse_memory_probe
            lines.append("### Spouse memory probe (Marvin only — emotional anchoring + attribution)")
            lines.append("")
            lines.append(
                f"sent=`{s.narrator_input}` reply=`"
                f"{(s.lori_reply[:300] + '…') if len(s.lori_reply) > 300 else s.lori_reply}"
                f"` severity={s.severity}"
            )
            for n in s.notes:
                lines.append(f"  - {n}")
            lines.append("")
        if nr.post_restart_recall:
            rr = nr.post_restart_recall
            lines.append("### Post-restart memory recall (after browser context reopen)")
            lines.append("")
            lines.append(f"- name recalled: {rr.contains_name}")
            lines.append(f"- DOB/year recalled: {rr.contains_dob_or_year}")
            lines.append(f"- POB recalled: {rr.contains_pob}")
            lines.append(
                f"- era stories in readback: {rr.era_stories_in_readback}/{rr.era_stories_total}  "
                f"(memory_echo readback content; NOT a measure of era-click navigation)"
            )
            lines.append(f"- cross-contamination: {rr.cross_contamination}")
            lines.append(f"- onboarding restart: {rr.onboarding_restart}")
            lines.append(f"- severity: **{rr.severity}**")
            lines.append("")
            lines.append(f"Reply excerpt: `{(rr.reply[:400] + '…') if len(rr.reply) > 400 else rr.reply}`")
            lines.append("")
        if nr.today_after_resume:
            s = nr.today_after_resume
            lines.append("### Today after resume ('what day is it')")
            lines.append("")
            lines.append(f"- reply: `{(s.lori_reply[:200] + '…') if len(s.lori_reply) > 200 else s.lori_reply}`")
            lines.append(f"- severity: **{s.severity}**")
            lines.append("")
        lines.append("### api.log signal counts per phase")
        lines.append("")
        lines.append("| Phase | Signals |")
        lines.append("|---|---|")
        for phase, sigs in nr.apilog_signals_per_phase.items():
            interesting = ", ".join(f"{k}={v}" for k, v in sorted(sigs.items()) if v > 0) or "(none)"
            lines.append(f"| {phase} | {interesting} |")
        lines.append("")
    # ── Stress Telemetry section (mirrors WO-OPS-STRESS-TELEMETRY-KV-01) ──
    if telemetry_summary:
        lines.append("## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)")
        lines.append("")
        snaps = telemetry_summary.get("snapshots") or []
        kvs = telemetry_summary.get("kv_clears") or []
        elapsed_s = telemetry_summary.get("elapsed_s")
        lines.append(f"- snapshots captured: **{len(snaps)}**")
        lines.append(f"- kv-clear calls: **{len(kvs)}**")
        if elapsed_s is not None:
            lines.append(f"- elapsed: **{elapsed_s:.1f}s**")
        lines.append("")
        api_signals = telemetry_summary.get("api_log_signals") or {}
        if api_signals:
            lines.append("### api.log signal counts (run window)")
            lines.append("")
            lines.append("| Signal | Count |")
            lines.append("|---|---:|")
            sig_rows = [
                ("FOREIGN KEY constraint failed", api_signals.get("fk_constraint_count", 0)),
                ("comm_control trims", api_signals.get("comm_control_trim_count", 0)),
                ("comm_control validate-only", api_signals.get("comm_control_validate_only_count", 0)),
                ("sendSystemPrompt timeouts", api_signals.get("send_system_prompt_timeouts", 0)),
                ("Phase G disconnects", api_signals.get("phase_g_disconnect_count", 0)),
                ("GPU OOM", api_signals.get("gpu_oom_count", 0)),
                ("VRAM_GUARD blocks", api_signals.get("vram_guard_block_count", 0)),
            ]
            for label, cnt in sig_rows:
                lines.append(f"| {label} | {cnt} |")
            lines.append("")
        prompt_summary = telemetry_summary.get("prompt_tokens_summary") or {}
        if prompt_summary and prompt_summary.get("n", 0) > 0:
            lines.append("### Prompt-tokens histogram")
            lines.append("")
            n = prompt_summary.get("n", 0)
            lines.append(
                f"- n={n} min={prompt_summary.get('min')} "
                f"p25={prompt_summary.get('p25')} median={prompt_summary.get('median')} "
                f"p75={prompt_summary.get('p75')} p95={prompt_summary.get('p95')} "
                f"max={prompt_summary.get('max')}"
            )
            growth = prompt_summary.get("avg_pct_growth_per_turn")
            if growth is not None:
                lines.append(f"- avg growth per turn: **{growth}%**")
            lines.append("")
            hist = prompt_summary.get("histogram") or {}
            if hist:
                lines.append("| Bucket | Count |")
                lines.append("|---|---:|")
                for bucket in ("0-1000", "1000-2000", "2000-3000", "3000-4000",
                               "4000-5000", "5000-6000", "6000-7000", "7000+"):
                    lines.append(f"| {bucket} | {hist.get(bucket, 0)} |")
                lines.append("")
        kv_summary = telemetry_summary.get("kv_clear_summary") or {}
        if kv_summary and kv_summary.get("n_calls", 0) > 0:
            lines.append("### KV-clear effectiveness")
            lines.append("")
            n_calls = kv_summary.get("n_calls", 0)
            n_ok = kv_summary.get("n", 0)
            lines.append(f"- calls: {n_calls}, successes: {n_ok}")
            if n_ok > 0:
                lines.append(f"- total freed: {kv_summary.get('total_freed_mb')} MB")
                lines.append(f"- avg freed per call: {kv_summary.get('avg_freed_mb')} MB")
                lines.append(
                    f"- min/max freed: {kv_summary.get('min_freed_mb')}/"
                    f"{kv_summary.get('max_freed_mb')} MB"
                )
            lines.append("")
    return "\n".join(lines)


def _build_failure_csv(report: RunReport) -> str:
    rows = [["test", "narrator", "step", "severity", "detail"]]
    for nr, plan in [(report.mary, MARY_PLAN), (report.marvin, MARVIN_PLAN)]:
        if not nr:
            continue
        for s in nr.onboarding_steps + nr.today_cycles + nr.early_inference_steps:
            if s.severity in ("RED", "AMBER"):
                rows.append(["test23", plan.key, s.label, s.severity, "; ".join(s.notes) or s.lori_reply[:200]])
        for er in nr.era_results:
            if er.severity in ("RED", "AMBER"):
                rows.append(["test23", plan.key, f"era_{er.era_id}", er.severity, "; ".join(er.notes)])
        if nr.today_factual and nr.today_factual.severity in ("RED", "AMBER"):
            rows.append(["test23", plan.key, "today_factual", nr.today_factual.severity, "; ".join(nr.today_factual.notes)])
        if nr.late_age_probe and nr.late_age_probe.severity in ("RED", "AMBER"):
            rows.append(["test23", plan.key, "late_age_probe", nr.late_age_probe.severity, "; ".join(nr.late_age_probe.notes)])
        if nr.pre_restart_recall and nr.pre_restart_recall.severity in ("RED", "AMBER"):
            rr = nr.pre_restart_recall
            rows.append(["test23", plan.key, "pre_restart_recall", rr.severity, "; ".join(rr.notes)])
        if nr.spouse_memory_probe and nr.spouse_memory_probe.severity in ("RED", "AMBER"):
            rows.append(["test23", plan.key, "spouse_memory_probe", nr.spouse_memory_probe.severity, "; ".join(nr.spouse_memory_probe.notes)])
        if nr.post_restart_recall and nr.post_restart_recall.severity in ("RED", "AMBER"):
            rr = nr.post_restart_recall
            rows.append(["test23", plan.key, "post_restart_recall", rr.severity, "; ".join(rr.notes)])
        if nr.today_after_resume and nr.today_after_resume.severity in ("RED", "AMBER"):
            rows.append(["test23", plan.key, "today_after_resume", nr.today_after_resume.severity, "; ".join(nr.today_after_resume.notes)])
    out = []
    for r in rows:
        out.append(",".join('"' + str(c).replace('"', '""') + '"' for c in r))
    return "\n".join(out) + "\n"


def _to_serializable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_serializable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(v) for v in obj]
    return obj


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="TEST-23 two-person single-narrator resume canary")
    ap.add_argument("--tag", required=True, help="Run tag (e.g. test23_v1)")
    ap.add_argument("--base-url", default="http://localhost:8082/ui/hornelore1.0.html")
    ap.add_argument("--api-base", default="http://localhost:8000")
    ap.add_argument("--headless", action="store_true", default=False,
                    help="Run Chromium headless (default visible).")
    ap.add_argument("--slow-mo-ms", type=int, default=0)
    ap.add_argument("--only", choices=["mary", "marvin", "both"], default="both")
    ap.add_argument("--emit-telemetry", action="store_true", default=True,
                    help="Capture VRAM snapshots, prompt-tokens histogram, "
                         "FK/Phase-G/OOM signal counts, run elapsed (default ON).")
    ap.add_argument("--no-emit-telemetry", dest="emit_telemetry",
                    action="store_false", help="Disable telemetry capture.")
    ap.add_argument("--clear-kv-between-narrators", action="store_true", default=False,
                    help="POST /clear-kv between Mary and Marvin. Off by default "
                         "since real users don't trigger this. Requires "
                         "HORNELORE_OPERATOR_STACK_DASHBOARD=1 + HORNELORE_OPERATOR_CLEAR_KV=1 "
                         "server-side.")
    args = ap.parse_args()

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sha, dirty = _git_sha_and_dirty(_REPO_ROOT)
    report = RunReport(
        tag=args.tag,
        started_at=_now_iso(),
        base_url=args.base_url,
        api_base=args.api_base,
        commit_sha=sha,
        dirty_tree=dirty,
    )
    _RUNTIME_CONFIG["tag"] = args.tag
    _RUNTIME_CONFIG["reports_dir"] = _REPORTS_DIR
    print(f"[test23] tag={args.tag} commit={sha} dirty={dirty}")
    print(f"[test23] base_url={args.base_url}")
    print(f"[test23] reports → {_REPORTS_DIR}")

    out_console = _REPORTS_DIR / f"test23_two_person_resume_{args.tag}.console.txt"
    out_json = _REPORTS_DIR / f"test23_two_person_resume_{args.tag}.json"
    out_md = _REPORTS_DIR / f"test23_two_person_resume_{args.tag}.md"
    out_csv = _REPORTS_DIR / f"test23_two_person_resume_{args.tag}_failures.csv"
    out_telemetry = _REPORTS_DIR / f"test23_two_person_resume_{args.tag}.telemetry.json"

    # Telemetry recorder — captures VRAM snapshots, kv-clear MB freed,
    # api.log signal counts (FK/comm_control/Phase G/OOM/VRAM_GUARD),
    # prompt_tokens histogram + growth-per-turn, run elapsed.
    telemetry = TelemetryRecorder(
        api_base=args.api_base,
        out_path=out_telemetry,
        api_log_path=_API_LOG,
        enabled=args.emit_telemetry,
    )
    telemetry.record_start()
    if args.emit_telemetry:
        report.telemetry_path = str(out_telemetry)
        print(f"[telemetry] enabled → {out_telemetry}")
    if args.clear_kv_between_narrators:
        print("[telemetry] --clear-kv-between-narrators ON (requires both "
              "HORNELORE_OPERATOR_STACK_DASHBOARD=1 and HORNELORE_OPERATOR_CLEAR_KV=1)")

    with sync_playwright() as p:
        # WO-HARNESS-V4-VISIBILITY-01 (2026-05-05): force the Chromium
        # window visible at screen origin. Without --start-maximized +
        # --window-position=0,0 the window can open minimized or
        # off-screen on WSL/Windows, and TEST-23 v4 hit exactly that —
        # session_start threw post-restart because the operator's manual
        # fallback click couldn't reach a window they couldn't see. The
        # viewport stays explicit (1400x900) so element selectors render
        # predictably, but the WINDOW chrome is maximized so the
        # operator can see and interact with it if a fallback is needed.
        browser = p.chromium.launch(
            headless=args.headless,
            slow_mo=args.slow_mo_ms,
            args=["--start-maximized", "--window-position=0,0"],
        )
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, permissions=["camera", "microphone"])
        page = ctx.new_page()
        console = ConsoleCollector(page)
        dblock = DbLockCounter(_REPO_ROOT)
        ui = UI(page, console, _REPORTS_DIR / "screenshots", _REPORTS_DIR / "downloads")
        ui.boot(args.base_url)
        if not _wait_for_warm_stack(page, console, timeout_s=90):
            print("[test23] WARN — stack not warm within 90s; proceeding")

        plans = []
        if args.only in ("mary", "both"):
            plans.append(("mary", MARY_PLAN, MARVIN_PLAN if args.only == "both" else None))
        if args.only in ("marvin", "both"):
            plans.append(("marvin", MARVIN_PLAN, MARY_PLAN if args.only == "both" else None))

        for idx, (key, plan, other_plan) in enumerate(plans):
            nr = NarratorReport(plan_key=key, display_name=plan.display_name)
            if key == "mary":
                report.mary = nr
            else:
                report.marvin = nr
            try:
                _run_narrator_session1(ui, plan, other_plan, nr, telemetry=telemetry)
            except Exception as e:
                print(f"  [{key}] session 1 threw: {e}")
                nr.notes.append(f"session 1 exception: {e}")
                nr.severity = "RED"
            # Restart browser context for resume phase
            try:
                ctx.close()
            except Exception:
                pass
            try:
                ctx, page, ui, console, dblock = _restart_browser_and_resume(
                    browser, plan, nr, other_plan, args.base_url, _REPORTS_DIR,
                    telemetry=telemetry,
                )
            except Exception as e:
                print(f"  [{key}/restart] failed: {e}")
                nr.notes.append(f"restart failed: {e}")
                nr.severity = "RED"
            # Grade narrator
            _grade_narrator(nr, plan)
            # Wrap final session before next narrator
            try:
                ui.wrap_session()
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass
            # Optional kv-clear between narrators (off by default — real
            # narrator sessions don't trigger this code path; opt-in only
            # when explicitly testing multi-narrator KV behavior).
            if args.clear_kv_between_narrators and idx < len(plans) - 1:
                kv_result = telemetry.clear_kv(f"between_narrators_after_{key}")
                freed = kv_result.get("freed_mb")
                wall = kv_result.get("wall_ms")
                print(f"[telemetry] kv-clear after {key} → freed {freed} MB in {wall} ms")
            # Open fresh context for next narrator OR for closing
            if (key, plan) != plans[-1][:2]:
                ctx = browser.new_context(viewport={"width": 1400, "height": 900}, permissions=["camera", "microphone"])
                page = ctx.new_page()
                console = ConsoleCollector(page)
                dblock = DbLockCounter(_REPO_ROOT)
                ui = UI(page, console, _REPORTS_DIR / "screenshots", _REPORTS_DIR / "downloads")
                ui.boot(args.base_url)
                if not _wait_for_warm_stack(page, console, timeout_s=60):
                    print("[test23] WARN — stack not warm before next narrator")

        try:
            browser.close()
        except Exception:
            pass

    # Final severity rollup
    fails: List[str] = []
    if report.mary and report.mary.severity == "RED":
        fails.append("Mary RED")
    if report.marvin and report.marvin.severity == "RED":
        fails.append("Marvin RED")
    if fails:
        report.final_severity = "RED"
        report.final_failures.extend(fails)
    elif (report.mary and report.mary.severity == "AMBER") or \
         (report.marvin and report.marvin.severity == "AMBER"):
        report.final_severity = "AMBER"
    else:
        report.final_severity = "PASS"
    report.finished_at = _now_iso()

    # Finalize telemetry — writes the .telemetry.json + computes derived
    # metrics (FK/comm_control/Phase G/OOM counts, prompt-tokens histogram,
    # KV-clear effectiveness, run elapsed). Stash a compact summary on the
    # report so the MD output can render the same Stress Telemetry section
    # the rehearsal harness produces.
    telemetry_summary: Dict[str, Any] = {}
    if args.emit_telemetry:
        try:
            telemetry.finalize()
            # Re-read the just-written telemetry JSON for the summary
            try:
                with open(out_telemetry, "r", encoding="utf-8") as fh:
                    telemetry_summary = json.load(fh)
            except Exception:
                pass
        except Exception as e:
            print(f"[telemetry] finalize threw: {e}", file=sys.stderr)

    # Write outputs
    out_json.write_text(
        json.dumps(_to_serializable(report), indent=2, default=str),
        encoding="utf-8",
    )
    out_md.write_text(_build_md_report(report, telemetry_summary), encoding="utf-8")
    out_csv.write_text(_build_failure_csv(report), encoding="utf-8")
    print(f"\n[test23] done — overall={report.final_severity}")
    print(f"  json:      {out_json}")
    print(f"  md:        {out_md}")
    print(f"  csv:       {out_csv}")
    if args.emit_telemetry:
        print(f"  telemetry: {out_telemetry}")
    return 0 if report.final_severity != "RED" else 1


if __name__ == "__main__":
    sys.exit(main())
