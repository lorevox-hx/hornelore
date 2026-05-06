#!/usr/bin/env python3
"""WO-PARENT-READINESS-HARNESS-01 — Playwright readiness gate.

Automates docs/test-packs/PARENT-SESSION-READINESS-V1.md (10 tests) against
the running Hornelore stack. Creates disposable TEST narrators only — never
touches Kent / Janice / Christopher / any FAMILY narrator.

Usage (stack must already be warm):

  cd /mnt/c/Users/chris/hornelore
  python scripts/ui/run_parent_session_readiness_harness.py \
    --base-url http://localhost:8082/ui/hornelore1.0.html \
    --api http://localhost:8000 \
    --output docs/reports/parent_session_readiness_v1.json

Phase coverage (per WO):
  Phase 1 — skeleton + console collector + report writer
  Phase 2 — narrator creation + session helpers
  Phase 3 — TEST-07 / TEST-08 / TEST-09 (Life Map + Today)
  Phase 4 — TEST-01 / TEST-02 / TEST-03 / TEST-04 (validator)
  Phase 5 — TEST-05 / TEST-06 (reset + cross-narrator isolation)
  Phase 6 — TEST-10 (Peek = TXT export)

Dependencies:
  python -m pip install playwright
  python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from playwright.sync_api import (
        sync_playwright,
        Browser,
        BrowserContext,
        Page,
        ConsoleMessage,
        Download,
        Error as PWError,
        TimeoutError as PWTimeout,
    )
except ImportError:
    print("FATAL: playwright is not installed.", file=sys.stderr)
    print("Run: python -m pip install playwright && python -m playwright install chromium", file=sys.stderr)
    sys.exit(2)


# ─────────────────────────────────────────────────────────────────────
# SELECTORS — visible labels first, fall back to ids only when needed.
# Verified against ui/hornelore1.0.html (live UI, 2026-05-01).
# ─────────────────────────────────────────────────────────────────────
SEL = {
    # Shell tabs (header)
    "tab_operator":      'role=tab[name="Operator"]',
    "tab_narrator":      'role=tab[name="Narrator Session"]',
    "tab_media":         'role=tab[name="Media"]',

    # Top-center posture pills
    "pill_life_story":   'role=button[name="Life Story"]',

    # Operator panel
    "btn_ready_session":    'role=button[name="Ready for Session"]',
    "btn_wrap_session":     'role=button[name="Wrap Up Session"]',
    "btn_open_bug_panel":   'role=button[name="Open Full Bug Panel"]',
    "btn_enter_interview":  'role=button[name="Enter Interview Mode"]',
    "btn_start_narrator":   'role=button[name="Start Narrator Session"]',

    # Narrator switcher entry point (active narrator chip in header).
    # Verified live 2026-05-01: actual element is #lv80ActiveNarratorCard
    # with onclick="lv80ToggleNarratorSwitcher()". Earlier guesses
    # (#lvActiveNarratorChip / .lv-active-narrator-chip) returned 0 hits.
    "active_narrator_chip": '#lv80ActiveNarratorCard, .lv80-active-narrator',

    # Narrators popover & trainer-seed buttons
    "narrator_switcher_popover":  '#lv80NarratorSwitcher, [role=dialog][aria-label*="Narrators" i]',
    "trainer_seed_qf":            'role=button[name="Questionnaire First"]',
    "trainer_seed_cd":            'role=button[name="Clear & Direct"]',
    "trainer_seed_ws":            'role=button[name="Warm Storytelling"]',

    # Bio Builder
    "btn_bio_builder":     'role=button[name="Bio Builder"]',
    "tab_questionnaire":   'role=tab[name="Questionnaire"]',
    "tab_candidates":      'role=tab[name="Candidates"]',
    "btn_reset_identity":  'role=button[name="Reset Identity"]',

    # Peek at Memoir
    "btn_peek_memoir":     'role=button[name="Peek at Memoir"]',

    # Life Map
    "lifemap_host":        '#lvInterviewLifeMap',
    "lifemap_era_btn":     '.lv-interview-lifemap-era-btn',
    "lifemap_peek_card":   '.lv-interview-peek-inline',

    # Memory River (must be ABSENT)
    "memory_river_any":    'text=/memory.river/i',

    # Chat input
    "chat_input":          '#chatInput, textarea[name="chat"], input[name="chat"]',
    "chat_send":           'role=button[name="Send"]',
}

ERA_LABELS = [
    "Earliest Years", "Early School Years", "Adolescence",
    "Coming of Age", "Building Years", "Later Years", "Today",
]

# ─────────────────────────────────────────────────────────────────────
# NARRATION SAMPLES — verbatim from ui/js/test-harness.js SAMPLES dict.
# Christopher Horne canonical biography in 4 sizes:
#   clean      ~1000 words, full prose
#   messy      ~150 words, hedged casual
#   emotional  ~200 words, feeling-led
#   fragmented  ~80 words, telegraphic
# Used by TEST-11A/B/C/D to verify Lori responds to narration of varied
# sizes, grounds follow-up answers in the just-shared content, and
# answers time/date questions using device_context.
# Expected ground truth (used to score follow-up replies):
#   name        = "Christopher" or "Chris" (any name surface counts)
#   birthplace  = "Williston" or "North Dakota"
#   birth year  = "1962"
#   birthday    = "December 24"
# ─────────────────────────────────────────────────────────────────────
SAMPLES = {
    "clean": (
        "My name is Christopher Todd Horne. I was born on December 24, 1962, in Williston, North Dakota, "
        "early in the morning around 5:30 AM. I was the third child in my family and the youngest son. "
        "My parents were Kent James Horne and Janice Josephine Zarr Horne. My father was born in Stanley, "
        "North Dakota, and worked in construction and heavy equipment operations for much of his life. My "
        "mother was born in Spokane, Washington, and was very focused on family, music, and creating a "
        "stable home environment. They were married in 1959 in Bismarck, North Dakota, and built their "
        "life around family and hard work. I have two older brothers, Vince and Jay. Vince was born in "
        "1960 in Germany when my father was stationed there, and Jay was born in 1961 in Bismarck, North "
        "Dakota. Growing up, the three of us spent a lot of time together, especially outdoors. I "
        "remember long winters, playing in the snow, and summers where we were constantly outside riding "
        "bikes or exploring. We lived primarily in North Dakota during my early childhood, and those "
        "early years were shaped by a strong sense of community. Neighbors knew each other, and family "
        "gatherings were common. One of my earliest memories is sitting in church listening to my mother "
        "play the organ. Music was always present in our home. I attended school in Bismarck and "
        "eventually graduated from Bismarck High School in May of 1981. I was not always the most "
        "academically focused student, but I valued relationships and the experiences I had during those "
        "years. After high school, I moved into adulthood and began working various jobs while figuring "
        "out what I wanted to do long-term. Over time, I found my path in occupational therapy. I "
        "eventually became a licensed occupational therapist and worked primarily in school settings in "
        "Las Vegas, New Mexico. On April 13, 1991, I married Louise LaPlante. Louise and I had three "
        "children together: Gretchen, Amelia, and Cole. Each of them was born in Las Vegas, New Mexico. "
        "Louise and I were married until 2008, when we divorced. After some time, I met Melanie Zollner, "
        "who would later become my second wife. Melanie was born in Peru on December 20, 1973, and "
        "became a college professor. Melanie and I were married on December 22, 2010. Travel has also "
        "been a meaningful part of my life. One of the most memorable trips I took was to France in July "
        "of 2025. We spent time in Pau and the surrounding region. As I approached retirement, I began "
        "to reflect more on the arc of my life. I officially retired on January 1, 2026, after many "
        "years of working in occupational therapy. Looking back, I see a life shaped by family, work, "
        "relationships, and growth through both positive and difficult experiences. If I were to share "
        "something with future generations, it would be to value relationships, stay resilient through "
        "challenges, and remain open to learning at every stage of life."
    ),
    "messy": (
        "My name is Chris Horne, well Christopher Todd Horne technically. I was born in North Dakota, "
        "Williston I think, yeah December 24th 1962. I'm the youngest, third kid, two older brothers "
        "Vince and Jay. My dad Kent worked construction, heavy equipment kind of stuff, and my mom "
        "Janice was more focused on home and music. We lived in Bismarck mostly. Winters were brutal. "
        "School wise I graduated Bismarck High, I think 1981. I didn't love school but I got through it. "
        "Career took a while to figure out, I ended up in occupational therapy working in schools in "
        "Las Vegas, New Mexico. I married Louise in 1991, we had three kids Gretchen, Amelia, Cole. "
        "That ended in 2008. Then later I married Melanie in 2010, she's a professor, different life "
        "phase. Family stuff hasn't always been easy especially with Gretchen. I traveled to France in "
        "2025 which was a highlight. Retired January 2026. Main thing I'd say is relationships matter, "
        "even when they're complicated."
    ),
    "emotional": (
        "I guess if I start at the beginning, I was born December 24th 1962 in Williston North Dakota. "
        "My name is Christopher Todd Horne. Family was everything, sometimes in good ways and sometimes "
        "really hard ways. My parents Kent and Janice built a life around us. I always remember the "
        "music, my mom playing, that feeling of being safe. My brothers Vince and Jay were there "
        "through everything growing up. I didn't always know what I wanted to do, but eventually I "
        "found occupational therapy. Working with kids felt meaningful. I married Louise in 1991, and "
        "we had Gretchen, Amelia, and Cole. Being a father shaped everything. But things didn't stay "
        "stable. The marriage ended in 2008. That was one of the hardest times in my life. Later I met "
        "Melanie. We married in 2010. She brought a different energy, a new phase. Some relationships "
        "are still hard. Especially with Gretchen. That hasn't been easy. I retired in 2026 and now I "
        "spend more time thinking about what it all meant. If I could say anything, it's that "
        "relationships matter, even when they're painful."
    ),
    "fragmented": (
        "Christopher Todd Horne. Born 1962, December 24. Williston North Dakota. Third child. Two "
        "brothers. Vince, Jay. Parents Kent Horne, Janice Zarr Horne. Bismarck. Cold winters. School. "
        "Bismarck High. 1981. Work. Took time. Occupational therapist. Schools. Las Vegas NM. Marriage. "
        "Louise 1991. Kids: Gretchen, Amelia, Cole. Divorce 2008. Melanie 2010. Professor. France 2025. "
        "Retired 2026. Relationships. Complicated. Important thing. Stay connected."
    ),
}

# Word counts for observability (computed once at module load).
SAMPLE_WORD_COUNTS = {k: len(v.split()) for k, v in SAMPLES.items()}

# Lori "I can't tell the date" patterns — TEST-09 fail conditions.
# Negative phrases must be matched as substrings (case-insensitive).
TEST09_FAIL_PATTERNS = [
    r"i\s+can'?t\s+tell\s+(?:you\s+)?the\s+date",
    r"i\s+don'?t\s+know\s+(?:what\s+)?today",
    r"i'?m\s+in\s+a\s+conversation\s+mode\s+that\s+doesn'?t\s+allow",
    r"i\s+do\s+not\s+have\s+access\s+to\s+the\s+current\s+date",
    r"i\s+don'?t\s+have\s+access\s+to\s+the\s+(?:current\s+)?date",
    r"i\s+can'?t\s+(?:tell|know|determine)\s+(?:what|the)\s+(?:day|date)",
]

# Hard-stop conditions (per WO § Hard stop conditions). Each maps to a
# stable string label that the harness records verbatim if it fires.
HARD_STOP_LABELS = {
    "place_truth_pollution":   "Bad birthplace value writes into personal.placeOfBirth as truth.",
    "order_truth_pollution":   "Bad birthOrder value writes into personal.birthOrder as truth.",
    "memoir_pollution":        "Rejected text appears in Peek at Memoir as a confirmed fact.",
    "lifemap_missing":         "Life Map is missing on cold start.",
    "lifemap_dead_buttons":    "Life Map era buttons go visually-active-but-behaviorally-dead.",
    "today_no_date":           "Lori claims she cannot tell the date.",
    "operator_leak":           "Operator controls appear in narrator flow.",
    "cross_narrator_leak":     "Cross-narrator data appears under the wrong narrator.",
    "db_lock":                 "DB lock events increment during a normal session turn.",
    "leap_year_correction":    "Lori treats a valid leap-year DOB as invalid / corrects the narrator.",
    "leap_year_dob_lost":      "Leap-year DOB does not persist correctly in BB after intake.",
}

# TEST-12 leap-year DOB defensive-language patterns. Lori must not respond
# with any of these to a valid leap-year birthday — that's a WO-10C
# violation (no correction) AND a date-validity error (Feb 29 1940 IS
# a real date; 1940 was a leap year).
LEAP_YEAR_FAIL_PATTERNS = [
    r"that'?s\s+not\s+a\s+(?:real\s+|valid\s+|possible\s+)?date",
    r"isn'?t\s+a\s+(?:real\s+|valid\s+|possible\s+)?date",
    r"doesn'?t\s+(?:seem|appear)\s+to\s+be\s+(?:a\s+)?(?:real\s+|valid\s+)?date",
    r"i\s+don'?t\s+recognize\s+(?:that|this)\s+(?:as\s+a\s+)?date",
    r"are\s+you\s+sure\s+(?:about\s+)?that\s+(?:date|year|birthday)",
    r"(?:can|could)\s+you\s+(?:double[-\s]?check|verify|confirm)\s+(?:that|the)\s+(?:date|year|birthday)",
    r"that\s+date\s+(?:doesn'?t|does\s+not)\s+exist",
    r"february\s+29\s+(?:doesn'?t|does\s+not)\s+exist\s+in\s+1940",
    r"1940\s+(?:wasn'?t|was\s+not)\s+a\s+leap\s+year",
    r"i'?m\s+not\s+sure\s+(?:that'?s|about)\s+(?:right|correct|a\s+real)",
    r"let\s+me\s+(?:verify|check|confirm)\s+(?:that|this)",
]


# ─────────────────────────────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────────────────────────────
@dataclass
class TestResult:
    id: str
    name: str
    status: str = "PENDING"  # PASS / AMBER / FAIL / SKIP
    narrator_name: str = ""
    hard_stop: bool = False
    hard_stop_label: str = ""
    observations: Dict[str, Any] = field(default_factory=dict)
    console_matches: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    downloads: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    elapsed_ms: int = 0


@dataclass
class HarnessReport:
    started_at: str = ""
    finished_at: str = ""
    base_url: str = ""
    api: str = ""
    test_pack: str = "docs/test-packs/PARENT-SESSION-READINESS-V1.md"
    overall: str = "PENDING"   # GREEN / AMBER / RED
    hard_stops: List[str] = field(default_factory=list)
    db_lock_delta: int = 0
    tests: List[TestResult] = field(default_factory=list)
    # Set by main() based on --narration-only CLI flag. write_report
    # uses this to render absent static tests as "SKIP" (filtered out
    # deliberately) instead of "MISSING" (silent regression). Keeps
    # the operator from chasing ghost regressions on intentional
    # narration-only runs.
    narration_only: bool = False


# ─────────────────────────────────────────────────────────────────────
# CONSOLE COLLECTOR
# ─────────────────────────────────────────────────────────────────────
class ConsoleCollector:
    """Captures all console output, page errors, and request failures.
    Each entry is a dict so JSON serialization is trivial. The harness
    queries via .matches(pattern) to confirm specific log markers fired
    (e.g. [bb-drift] qf_walk validation REJECTED ...)."""

    def __init__(self, page: Page) -> None:
        self.entries: List[Dict[str, Any]] = []
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)
        page.on("requestfailed", self._on_requestfailed)

    def _on_console(self, msg: ConsoleMessage) -> None:
        # Capture both msg.text (Playwright's formatted output) AND
        # the structured args. Critical for `[lv80-turn-debug]` lines
        # which the app emits as `console.log("[tag]", {event: 'lori_reply',
        # reply_text: '...'})` — msg.text serializes the object arg as
        # "[object Object]", losing the payload. We read msg.args, call
        # json_value() per arg, and concat into a single search-friendly
        # string. matches() searches across both .text and .args_json so
        # plain string console.log lines still work and structured
        # console.log object lines become greppable.
        try:
            text = msg.text
        except Exception:
            text = ""
        args_pieces: List[str] = []
        try:
            for arg in (msg.args or []):
                try:
                    val = arg.json_value()
                except Exception:
                    val = None
                if isinstance(val, (dict, list)):
                    try:
                        args_pieces.append(json.dumps(val, default=str))
                    except Exception:
                        args_pieces.append(str(val))
                elif val is not None:
                    args_pieces.append(str(val))
        except Exception:
            pass
        args_json = " ".join(args_pieces).strip()
        self.entries.append({
            "ts": time.time(),
            "type": "console." + msg.type,
            "text": text,
            "args_json": args_json,
        })

    def _on_pageerror(self, exc: Any) -> None:
        self.entries.append({
            "ts": time.time(),
            "type": "pageerror",
            "text": str(exc),
        })

    def _on_requestfailed(self, request: Any) -> None:
        try:
            failure = request.failure
        except Exception:
            failure = ""
        self.entries.append({
            "ts": time.time(),
            "type": "requestfailed",
            "text": f"{request.method} {request.url} — {failure}",
        })

    def matches(self, pattern: str, since_ts: Optional[float] = None) -> List[str]:
        """Return all entries whose text OR args_json matches the regex
        (case-insensitive). Searches both surfaces so plain-string
        console.log lines (e.g. '[bb-drift] qf_walk validation REJECTED ...')
        and structured-object console.log lines (e.g. '[lv80-turn-debug]'
        with object arg containing event/reply_text) both match.

        Returns the matching surface (text or args_json) so callers can
        re-parse if needed."""
        rx = re.compile(pattern, re.I)
        out = []
        for e in self.entries:
            if since_ts is not None and e["ts"] < since_ts:
                continue
            text = e.get("text") or ""
            args_json = e.get("args_json") or ""
            if rx.search(text):
                out.append(text)
            elif rx.search(args_json):
                out.append(args_json)
        return out

    def now(self) -> float:
        return time.time()


# ─────────────────────────────────────────────────────────────────────
# DB LOCK COUNTER (reads .runtime/logs/api.log)
# ─────────────────────────────────────────────────────────────────────
class DbLockCounter:
    """Counts 'database is locked' / 'OperationalError' / 'sqlite.*locked'
    occurrences in the api.log between two snapshots. Returns 0 if the
    log file isn't readable (logs path may differ by environment)."""

    LOG_CANDIDATES = [
        Path(".runtime/logs/api.log"),
        Path("/mnt/c/hornelore_data/logs/api.log"),
    ]
    PATTERN = re.compile(
        r"database is locked|OperationalError|sqlite.*locked",
        re.I,
    )

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._log_path: Optional[Path] = None
        for c in self.LOG_CANDIDATES:
            full = repo_root / c if not c.is_absolute() else c
            if full.exists():
                self._log_path = full
                break
        self._baseline: int = self._count()

    def _count(self) -> int:
        if not self._log_path or not self._log_path.exists():
            return 0
        try:
            text = self._log_path.read_text(errors="ignore")
        except Exception:
            return 0
        return len(self.PATTERN.findall(text))

    def delta(self) -> int:
        return max(0, self._count() - self._baseline)

    def reset(self) -> None:
        self._baseline = self._count()


# ─────────────────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────────────────
class UI:
    """Centralized UI interactions. Each helper wraps Playwright calls
    with the verified visible labels from PARENT-SESSION-READINESS-V1.md."""

    def __init__(self, page: Page, console: ConsoleCollector,
                 screenshots_dir: Path, downloads_dir: Path) -> None:
        self.page = page
        self.console = console
        self.screenshots_dir = screenshots_dir
        self.downloads_dir = downloads_dir

    # — Popover dismissal (defense-in-depth) —
    def dismiss_popovers(self) -> None:
        """Close any open [popover] / dialog that could intercept clicks.
        Must be called before any operator-panel button click — the
        v9-gate startup logic auto-opens the narrator switcher, and the
        narrator switch path can re-open it during a session.

        Two-prong: Escape keypress (handles native dialogs + popovers
        responding to ESC) AND a JS sweep over every `[popover]` element
        that's `:popover-open` (handles popovers opened programmatically
        without ESC bindings). Per ChatGPT's 2026-05-01 reading, this
        belongs as a reusable helper rather than inlined per call."""
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(120)
        except Exception:
            pass
        try:
            self.page.evaluate("""
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
            self.page.wait_for_timeout(150)
        except Exception:
            pass

    def _active_narrator_name(self) -> str:
        """Read the active-narrator chip's display text. The chip
        (#lv80ActiveNarratorCard) renders multi-line markup like:
            "CA
             ACTIVE NARRATOR
             Christopher Todd Horne
             Christopher Todd Horne
             ▾"
        The narrator name is the last non-empty / non-arrow line.
        Returns empty string on any failure so callers can treat
        absence as "no narrator selected"."""
        try:
            raw = self.page.evaluate("""
                () => {
                  const el = document.querySelector(
                    '#lv80ActiveNarratorCard, .lv80-active-narrator'
                  );
                  return (el && (el.innerText || el.textContent) || '').trim();
                }
            """)
        except Exception:
            raw = ""
        # Filter out the static "ACTIVE NARRATOR" label, "Choose a
        # narrator" placeholder, the avatar initials line, and the
        # caret arrow. The chip's name line is the LAST line that
        # isn't one of those sentinel values.
        lines = [
            x.strip() for x in (raw or "").splitlines()
            if x.strip() and x.strip() not in ("ACTIVE NARRATOR", "▾", "▼")
            and not x.strip().startswith("Choose a narrator")
        ]
        # Avatar initials are usually 2-3 uppercase letters; skip them.
        lines = [x for x in lines if not (len(x) <= 3 and x.isupper())]
        return lines[-1] if lines else ""

    # — Boot / posture / readiness —
    def boot(self, base_url: str) -> None:
        self.page.goto(base_url, wait_until="domcontentloaded")
        # WO-HARNESS-V4-VISIBILITY-01 (2026-05-05): force the browser
        # window to the foreground after navigation. Playwright on
        # WSL/Windows occasionally opens Chromium minimized or behind
        # other windows; without bring_to_front() the operator can't see
        # the page and any manual-fallback clicks (popover dismissal,
        # affect-consent, post-restart Start-Session) silently fail.
        # Wrapped in try/except because bring_to_front() raises on
        # headless contexts, which is fine — there's nothing to bring.
        try:
            self.page.bring_to_front()
        except Exception:
            pass
        # Hard reload to clear any cached state.
        self.page.reload(wait_until="domcontentloaded")
        try:
            self.page.bring_to_front()
        except Exception:
            pass
        # Wait for app boot — readiness module logs "[readiness] Model warm"
        # but we don't block on that; just give the shell time to mount.
        try:
            self.page.wait_for_selector(SEL["tab_operator"], timeout=15_000)
        except PWTimeout:
            pass
        self.page.wait_for_timeout(800)
        # v9-gate auto-opens the narrator switcher popover on startup
        # (`[readiness] v9 — startup neutral. Opening narrator selector`).
        # The popover overlays operator-panel controls; clicks against
        # Ready for Session / Life Story pill / Operator tab fail with
        # "subtree intercepts pointer events" until it's dismissed.
        self.dismiss_popovers()

    def ensure_operator_tab(self) -> None:
        # Defensive: kill any popover that might be on top of the tab bar.
        self.dismiss_popovers()
        try:
            self.page.locator(SEL["tab_operator"]).click(timeout=3_000)
        except (PWTimeout, PWError):
            pass

    def ensure_life_story_posture(self) -> None:
        self.dismiss_popovers()
        try:
            self.page.locator(SEL["pill_life_story"]).click(timeout=3_000)
        except (PWTimeout, PWError):
            pass

    def ready_for_session(self) -> None:
        # Defensive: the narrator switcher popover frequently re-opens
        # mid-session. Ready for Session click must not be blocked by it.
        self.dismiss_popovers()
        try:
            self.page.locator(SEL["btn_ready_session"]).click(timeout=5_000)
            self.page.wait_for_timeout(600)
        except (PWTimeout, PWError) as e:
            print(f"  [warn] Ready for Session click failed: {e}", file=sys.stderr)

    def open_full_bug_panel(self) -> None:
        try:
            self.page.locator(SEL["btn_open_bug_panel"]).click(timeout=3_000)
        except (PWTimeout, PWError):
            pass

    def close_bug_panel(self) -> None:
        # Press Escape to close any open popover.
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass

    # — Narrator creation via API direct (bypass trainer flow) —
    def add_test_narrator(self, style: str) -> str:
        """Create a new TEST narrator and switch to it.

        IMPORTANT (2026-05-01 audit): the trainer-seed buttons inside the
        narrator switcher popover (`Questionnaire First` / `Clear & Direct`
        / `Warm Storytelling`) call `lv80RunTrainerNarrator(seed)` which
        runs an ISOLATED trainer flow — NOT a real new-narrator creation.
        The trainer flow suspends the current narrator, creates a synthetic
        `trainer_<ts>` conv_id, and loads a trainer template. Driving it
        through to actually persist a narrator requires walking the full
        trainer dialogue, which is brittle and dialog-dependent.

        The real new-narrator path is `lv80NewPerson()` which uses a
        `prompt()` dialog. Even cleaner: POST directly to `/api/people`
        with the same payload `lv80NewPerson()` posts, then set the
        session-style localStorage key, then call `loadPerson(pid)` to
        switch to it. That's what this method does.

        Returns the display name of the created narrator. The pid is
        retrievable via `state.person_id` after the call returns.
        Style: 'questionnaire_first' / 'clear_direct' / 'warm_storytelling'.
        """
        valid_styles = {"questionnaire_first", "clear_direct", "warm_storytelling"}
        if style not in valid_styles:
            raise ValueError(f"Unknown style: {style}")

        # Generate a unique TEST display name. Six-digit ms suffix is
        # enough collision-resistance for a single harness run.
        display_name = f"Test_{int(time.time() * 1000) % 1_000_000:06d}"

        # The hornelore_session_style_v1 localStorage key is read by
        # the session-style-router on narrator load. Set it BEFORE the
        # loadPerson() call so the QF/CD/WS style is in effect when
        # the session-loop initializes.
        result = self.page.evaluate(
            """
            async ({name, style}) => {
              try {
                // 1. Resolve the API endpoint the way the app does. The
                //    UI is served from :8082 but the API lives on :8000;
                //    a relative '/api/people' fetch goes to the UI server
                //    which doesn't proxy /api/* and returns HTML. The
                //    app exposes the absolute URL via window.API.PEOPLE
                //    (resolves to 'http://localhost:8000/api/people').
                //    Live-verified 2026-05-01.
                if (typeof API === 'undefined' || !API.PEOPLE) {
                  return {ok: false, error: 'window.API unavailable'};
                }

                // 2. Create narrator via the same endpoint lv80NewPerson uses.
                const r = await fetch(API.PEOPLE, {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({
                    display_name: name,
                    role: '',
                    narrator_type: 'live'
                  }),
                });
                if (!r.ok) {
                  const txt = await r.text().catch(() => '');
                  return {ok: false, error: 'create_failed_' + r.status + ': ' + txt.slice(0, 120)};
                }
                const j = await r.json();
                const pid = j.person_id || (j.person && j.person.id) || j.id;
                if (!pid) return {ok: false, error: 'no_pid_in_response: ' + JSON.stringify(j).slice(0, 200)};

                // 3. Pin session style BEFORE loadPerson so the
                //    session-style-router initializes correctly.
                try {
                  localStorage.setItem('hornelore_session_style_v1', style);
                } catch (e) {}

                // 4. Refresh the people cache + render the narrator
                //    cards so the new narrator is selectable via UI.
                if (typeof refreshPeople === 'function') {
                  try { await refreshPeople(); } catch (e) {}
                }
                if (typeof lv80RenderNarratorCards === 'function') {
                  try { lv80RenderNarratorCards(); } catch (e) {}
                }

                // 5. Switch to the new narrator. lv80ConfirmNarratorSwitch
                //    is the canonical UI-side switch path (mirrors what
                //    lv80NewPerson calls after creation). Falls back to
                //    loadPerson(pid) if the wrapper isn't exposed.
                if (typeof lv80ConfirmNarratorSwitch === 'function') {
                  try { await lv80ConfirmNarratorSwitch(pid); }
                  catch (e) { if (typeof loadPerson === 'function') await loadPerson(pid); }
                } else if (typeof loadPerson === 'function') {
                  await loadPerson(pid);
                }

                return {ok: true, pid: pid, name: name};
              } catch (e) {
                return {ok: false, error: String(e && e.message || e)};
              }
            }
            """,
            {"name": display_name, "style": style},
        )
        if not (result and result.get("ok")):
            err = (result or {}).get("error", "unknown")
            raise RuntimeError(f"add_test_narrator({style}) failed: {err}")

        # Wait for the switch to settle — narrator load fires several
        # async ops (BB blob fetch, projection restore, header repaint).
        self.page.wait_for_timeout(2_000)

        # Dismiss the narrator switcher popover if it auto-opened during
        # the switch (v9-gate may re-open it on narrator change).
        try:
            self.page.evaluate("""
                () => {
                  try {
                    var pop = document.getElementById('lv80NarratorSwitcher');
                    if (pop && typeof pop.hidePopover === 'function' && pop.matches(':popover-open')) {
                      pop.hidePopover();
                    }
                  } catch (_) {}
                }
            """)
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(150)
        except Exception:
            pass

        return display_name

    def session_start(self) -> None:
        # Either button reaches the same destination per the manual pack.
        # Prefer Start Narrator Session since it's the bottom-of-style-picker
        # button the manual run uses.
        for sel in (SEL["btn_start_narrator"], SEL["btn_enter_interview"]):
            try:
                self.page.locator(sel).first.click(timeout=3_000)
                self.page.wait_for_timeout(1_500)
                break
            except (PWTimeout, PWError):
                continue
        else:
            # BUG-HARNESS-SESSION-START-VISIBILITY-01 (2026-05-06):
            # Post-restart resume case — narrator is already loaded + active
            # (state.person_id set + chat input visible) so neither
            # "Start Narrator Session" nor "Enter Interview Mode" button
            # is rendered. The harness shouldn't error out; the session is
            # already in the state we wanted session_start to produce.
            # Detect via window.state.person_id (set by lv80SwitchPerson)
            # OR window.state.narratorOpen.openStatus === 'ready' (the
            # post-narrator-card-open ready state).
            try:
                already_active = self.page.evaluate(
                    "!!(window.state && (window.state.person_id || "
                    "(window.state.narratorOpen && "
                    "window.state.narratorOpen.openStatus === 'ready')))"
                )
            except Exception:
                already_active = False
            if already_active:
                # Session already active (typical post-restart state) — no
                # button to click; emit a marker for harness observability.
                try:
                    self.page.evaluate(
                        "console.log('[harness][session-start] tolerated: narrator already active')"
                    )
                except Exception:
                    pass
                self.page.wait_for_timeout(500)
                return
            raise RuntimeError("session_start: neither Start Narrator Session nor Enter Interview Mode visible")

        # ── Handle v9-gate "Narrator record incomplete" interstitial ──
        # When the narrator is missing name/DOB (every newly-created TEST
        # narrator from add_test_narrator), v9-gate shows a card with
        # "Complete profile basics" + "Back to narrators" buttons before
        # routing into the QF walk. Live-observed 2026-05-01: harness
        # gets stuck on this card if not handled.
        # Click "Complete profile basics" to proceed into the identity
        # onboarding flow — that IS the flow TEST-01/02/03/04 want to
        # exercise (Lori asks name → DOB → place → order in sequence).
        # Best-effort: if the card isn't present (narrator already has
        # complete identity), this is a no-op.
        try:
            cb = self.page.get_by_role("button", name="Complete profile basics")
            if cb.count() > 0 and cb.first.is_visible():
                cb.first.click(timeout=3_000)
                self.page.wait_for_timeout(1_500)
        except (PWTimeout, PWError):
            pass

    def wrap_session(self) -> None:
        # Wrap Up Session lives in the operator panel.
        self.ensure_operator_tab()
        try:
            self.page.locator(SEL["btn_wrap_session"]).click(timeout=3_000)
            self.page.wait_for_timeout(600)
        except (PWTimeout, PWError):
            pass

    # — Chat —
    def send_chat(self, text: str) -> float:
        """Type into chat input + click Send. Returns the timestamp the
        send fired so the caller can filter console matches to that turn."""
        ts = self.console.now()
        try:
            inp = self.page.locator(SEL["chat_input"]).first
            inp.click(timeout=3_000)
            inp.fill(text)
            self.page.locator(SEL["chat_send"]).first.click(timeout=3_000)
        except (PWTimeout, PWError):
            # Fallback: keyboard Enter.
            try:
                self.page.keyboard.press("Enter")
            except Exception:
                pass
        return ts

    def wait_for_lori_turn(self, since_ts: float, timeout_ms: int = 30_000) -> str:
        """Block until Lori's reply lands or timeout. The app emits a
        `[lv80-turn-debug]` console line as `console.log("[lv80-turn-debug]",
        {event: 'lori_reply', reply_text: '...', ...})`. Playwright's
        msg.text stringifies the object arg as '[object Object]', so we
        read from console.args_json (populated by ConsoleCollector via
        arg.json_value()).

        2026-05-04 BUG-HARNESS-ELLIPSIS-CAPTURE: filter out the streaming
        placeholder bubble. sendSystemPrompt and chat-send both call
        appendBubble("ai","…") at app.js:4482/4524 BEFORE streaming
        starts. If a `[lv80-turn-debug] {event:'lori_reply'}` event fires
        when that placeholder mounts, this loop captures "…" instead of
        Lori's actual reply. Live evidence: rehearsal_quick_v7 captured
        "…" for Coming of Age era click and T1+T2 voice loop. Fix: skip
        any event whose reply_text is empty, the literal "…" placeholder,
        or contains only whitespace/dots — keep waiting for the real
        completed reply text. This is a no-op when the placeholder event
        either doesn't fire or arrives after the real reply.

        Returns the reply_text payload, or empty string on timeout."""
        deadline = time.time() + (timeout_ms / 1000.0)
        # Track which entries we've seen but skipped, so we don't re-walk
        # them every poll iteration (cheap optimization for long waits).
        seen_skipped = set()
        while time.time() < deadline:
            for e in self.console.entries:
                if e["ts"] < since_ts:
                    continue
                # The text channel is "[lv80-turn-debug] [object Object]"
                # — no payload. The args_json channel contains the
                # JSON-stringified object arg.
                args_json = e.get("args_json") or ""
                text = e.get("text") or ""
                # Pre-filter on the tag in either surface to limit the
                # JSON parse to relevant lines.
                if "lv80-turn-debug" not in (text + args_json):
                    continue
                if "lori_reply" not in args_json:
                    continue
                # Pull reply_text out of the JSON. The collector emits
                # JSON.stringify(val), so reply_text is "..." quoted.
                m = re.search(r'"reply_text"\s*:\s*"((?:[^"\\]|\\.)*?)"',
                              args_json, re.S)
                reply_text = ""
                if m:
                    # Unescape JSON string escapes.
                    reply_text = m.group(1).encode().decode("unicode_escape", errors="replace")
                else:
                    reply_text = args_json

                # Skip placeholder + empty events — wait for the real reply.
                # "…" is U+2026 (ellipsis); also catch the 3-dot ASCII form
                # and pure whitespace/dot strings that might leak from the
                # streaming bubble before tokens arrive.
                #
                # 2026-05-04 stress_v1 evidence: field T1 captured
                # "…What's your full name?" (4 words, leading "…" prefix).
                # That's a mid-stream capture where the bubble started at
                # placeholder, then the lori_reply event fired before
                # streaming had time to accumulate the full intro reply.
                # Tighten: also reject events whose reply_text starts with
                # "…" AND has ≤5 trailing words (very short tail = mid-stream
                # capture, not a complete reply).
                stripped = reply_text.strip()
                if (not stripped
                        or stripped == "…"
                        or stripped == "..."
                        or stripped == "…"
                        or set(stripped) <= {".", "…", " ", "\t", "\n"}):
                    # Mark as seen so we don't re-check this exact event,
                    # but keep polling for a later real-reply event.
                    seen_skipped.add(id(e))
                    continue

                # 2026-05-04 mid-stream-capture filter: reject leading-"…"
                # replies with very short tails (placeholder + first sentence
                # only — reply hasn't finished streaming yet).
                if stripped.startswith("…") or stripped.startswith("..."):
                    # Strip the leading ellipsis + whitespace, count the rest
                    tail = stripped.lstrip("…. \t\n")
                    tail_words = tail.split()
                    if len(tail_words) <= 5:
                        seen_skipped.add(id(e))
                        continue

                return reply_text
            self.page.wait_for_timeout(400)
        return ""

    # — Bio Builder reads —
    def open_bio_builder(self) -> None:
        try:
            self.page.locator(SEL["btn_bio_builder"]).first.click(timeout=3_000)
            self.page.wait_for_timeout(500)
        except (PWTimeout, PWError):
            pass

    def read_bb_questionnaire(self) -> Dict[str, Any]:
        """Read the BB Questionnaire blob via API call from the browser
        (avoids brittle DOM scraping). Returns the personal.* dict."""
        try:
            blob = self.page.evaluate("""
                async () => {
                  const pid = (typeof state !== 'undefined' && state && state.person_id) || null;
                  if (!pid) return { _error: 'no_person_id' };
                  const url = (typeof API !== 'undefined' && API.BB_QQ_GET)
                    ? API.BB_QQ_GET(pid)
                    : '/api/bio-builder/questionnaire?person_id=' + encodeURIComponent(pid);
                  const r = await fetch(url);
                  if (!r.ok) return { _error: 'http_' + r.status };
                  const j = await r.json();
                  return (j && (j.questionnaire || j.payload || j)) || {};
                }
            """)
        except Exception as e:
            blob = {"_error": str(e)}
        return blob or {}

    def read_bb_field(self, dotted_path: str) -> str:
        blob = self.read_bb_questionnaire()
        cur: Any = blob
        for part in dotted_path.split("."):
            if not isinstance(cur, dict):
                return ""
            cur = cur.get(part)
            if cur is None:
                return ""
        return str(cur) if cur is not None else ""

    # — Peek at Memoir —
    def open_peek_memoir(self) -> None:
        try:
            self.page.locator(SEL["btn_peek_memoir"]).first.click(timeout=3_000)
            self.page.wait_for_timeout(800)
        except (PWTimeout, PWError):
            pass

    def read_peek_memoir_text(self) -> str:
        """Read the visible memoir popover content."""
        try:
            return self.page.evaluate("""
                () => {
                  var el = document.getElementById('memoirScrollPopover')
                       || document.querySelector('[data-peek-memoir]')
                       || document.querySelector('.lv-peek-memoir-popover');
                  return (el && (el.innerText || el.textContent) || '').trim();
                }
            """) or ""
        except Exception:
            return ""

    def download_memoir_txt(self, save_path: Path) -> Optional[Path]:
        """Trigger the TXT export inside the Peek popover and capture
        the download. Returns the saved path, or None if the export
        button wasn't found."""
        try:
            with self.page.expect_download(timeout=10_000) as dl_info:
                # Try a few label patterns since the export button text
                # has varied in past iterations.
                for pattern in (
                    re.compile(r"download.*txt|export.*txt|save.*txt|txt", re.I),
                    re.compile(r"download|export|save", re.I),
                ):
                    try:
                        self.page.get_by_role("button", name=pattern).first.click(timeout=3_000)
                        break
                    except (PWTimeout, PWError):
                        continue
                else:
                    return None
            dl = dl_info.value
            target = save_path / dl.suggested_filename
            dl.save_as(str(target))
            return target
        except (PWTimeout, PWError):
            return None

    # — Life Map —
    def assert_life_map_visible(self) -> Tuple[bool, int]:
        """Return (visible, era_count). Era count includes Today."""
        try:
            host = self.page.locator(SEL["lifemap_host"]).first
            if host.count() == 0:
                return (False, 0)
            visible = host.is_visible()
            count = self.page.locator(SEL["lifemap_era_btn"]).count()
            return (visible, count)
        except Exception:
            return (False, 0)

    def assert_no_memory_river(self) -> bool:
        """Return True if no VISIBLE Memory River UI is present.

        2026-05-01: original `text=/memory.river/i` selector matched any
        DOM text including hidden legacy strings, JS code constants, and
        retired-comment annotations — which fired a false positive on
        TEST-07 even though the manual UI inspection showed no visible
        Memory River. This visible-only check (per ChatGPT's read of the
        run-2 console) walks every body element, filters by computed
        style + bounding rect, and returns the visible matches with
        diagnostic detail to stderr."""
        try:
            visible = self.page.evaluate("""
                () => {
                  const out = [];
                  const all = document.querySelectorAll('body *');
                  for (const el of all) {
                    const txt = (el.innerText || '').trim();
                    if (!/memory\\s*river/i.test(txt)) continue;
                    const cs = window.getComputedStyle(el);
                    if (cs.display === 'none') continue;
                    if (cs.visibility === 'hidden') continue;
                    if (parseFloat(cs.opacity || '1') <= 0) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    out.push({
                      tag: el.tagName,
                      id: el.id || '',
                      cls: (typeof el.className === 'string' ? el.className : ''),
                      text: txt.slice(0, 120),
                    });
                  }
                  return out;
                }
            """) or []
            if visible:
                print("[memory-river-visible]", visible, file=sys.stderr)
            return len(visible) == 0
        except Exception:
            return True

    def confirm_era_popover(self) -> bool:
        """If the era-confirmation popover (Step 7 of canonical life
        spine — _lvInterviewConfirmEra opens .lv-interview-confirm-overlay
        with a Continue button) is open, click Continue. Returns True
        if a popover was found and dismissed.

        Each era-button click goes through _lvInterviewConfirmEra which
        creates a modal overlay (NOT a [popover] element — it's a div
        appended to body). Without confirming, the overlay intercepts
        all subsequent clicks. Run-2 evidence: era_click_marker_delta=0
        across 9 era clicks because _lvInterviewSelectEra (which fires
        the [life-map][era-click] log) only runs when Continue is
        clicked, not when the era button is clicked."""
        try:
            cont = self.page.locator(".lv-interview-confirm-continue").first
            if cont.count() > 0 and cont.is_visible():
                cont.click(timeout=2_000)
                self.page.wait_for_timeout(250)
                return True
        except (PWTimeout, PWError):
            pass
        return False

    def click_life_map_era(self, label: str) -> bool:
        """Click an era button by visible label, then confirm the
        era-confirmation popover. Returns True if the click landed AND
        the era was successfully confirmed (i.e. _lvInterviewSelectEra
        actually fired)."""
        try:
            self.page.get_by_role("button", name=label, exact=True).first.click(timeout=3_000)
            self.page.wait_for_timeout(250)
        except (PWTimeout, PWError):
            try:
                self.page.locator(
                    f'{SEL["lifemap_era_btn"]}:has-text("{label}")'
                ).first.click(timeout=3_000)
                self.page.wait_for_timeout(250)
            except (PWTimeout, PWError):
                return False
        # Confirm the era-confirmation popover (always opened by
        # _lvInterviewConfirmEra). If no popover appears, that itself
        # is unexpected (regression?) — return False so the test can
        # report it.
        return self.confirm_era_popover()

    # — Reset Identity —
    def click_reset_identity(self) -> Tuple[bool, str]:
        """Click Reset Identity, capture the confirm dialog text, accept it.
        Returns (clicked_ok, dialog_text)."""
        dialog_text = ""

        def _on_dialog(d):
            nonlocal dialog_text
            dialog_text = d.message or ""
            try:
                d.accept()
            except Exception:
                pass

        self.page.once("dialog", _on_dialog)
        try:
            self.page.locator(SEL["btn_reset_identity"]).first.click(timeout=5_000)
            self.page.wait_for_timeout(1_500)
            return (True, dialog_text)
        except (PWTimeout, PWError):
            return (False, dialog_text)

    # — Screenshot helper —
    def screenshot(self, name: str) -> str:
        path = self.screenshots_dir / f"{name}.png"
        try:
            self.page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            return ""


# ─────────────────────────────────────────────────────────────────────
# THE TESTS
# ─────────────────────────────────────────────────────────────────────
class Harness:
    def __init__(self, ui: UI, console: ConsoleCollector, dblock: DbLockCounter) -> None:
        self.ui = ui
        self.console = console
        self.dblock = dblock
        self.report = HarnessReport()

    # ── individual tests ─────────────────────────────────────────────
    def test_07_lifemap_cold_start(self) -> TestResult:
        r = TestResult(id="TEST-07", name="Life Map cold-start")
        t0 = time.time()
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            since = self.console.now()
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            visible, count = self.ui.assert_life_map_visible()
            no_river = self.ui.assert_no_memory_river()
            r.observations["lifemap_visible"] = visible
            r.observations["era_button_count"] = count
            r.observations["memory_river_absent"] = no_river

            marker = self.console.matches(
                r"\[life-map\] rendered:\s*\d+\s*eras", since_ts=since)
            r.console_matches.extend(marker[:3])

            if not visible or count < 6:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["lifemap_missing"]
            elif not no_river:
                r.status = "FAIL"
                r.notes.append("Memory River UI present — should be retired.")
            elif not marker:
                r.status = "AMBER"
                r.notes.append("Life Map visible but [life-map] rendered console marker missing.")
            else:
                r.status = "PASS"
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test07_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def test_08_lifemap_era_cycle(self) -> TestResult:
        r = TestResult(id="TEST-08", name="Life Map era cycle")
        t0 = time.time()
        click_sequence = [
            "Earliest Years", "Today", "Earliest Years",
            "Early School Years", "Adolescence", "Coming of Age",
            "Building Years", "Later Years", "Today",
        ]
        try:
            r.narrator_name = self.ui.add_test_narrator("clear_direct")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)

            # Per MANUAL-PARENT-READINESS-V1 (Manual TEST-08A): the
            # historical-era buttons (Earliest Years, Early School
            # Years, Adolescence, Coming of Age, Building Years, Later
            # Years) require identity_complete to activate. Today is
            # special-cased as the present-day anchor and always
            # clickable. Prior runs (2026-05-01) showed only the two
            # Today clicks succeeding while all 7 historical-era
            # clicks failed silently — exactly the "buttons rendered
            # but not bound to handler" pattern the manual pack flagged.
            # Complete identity first so the eras unlock, then exercise
            # the cycle. This is the realistic post-intake narrator
            # state — nobody clicks era buttons before they've told Lori
            # their name.
            self._complete_identity_for_test_narrator()
            r.observations["identity_completed"] = True

            click_results = []
            era_click_markers_before = len(self.console.matches(r"\[life-map\]\[era-click\]"))
            for label in click_sequence:
                ok = self.ui.click_life_map_era(label)
                click_results.append({"label": label, "ok": ok})
            r.observations["era_clicks"] = click_results

            era_click_markers_after = len(self.console.matches(r"\[life-map\]\[era-click\]"))
            r.observations["era_click_marker_delta"] = (
                era_click_markers_after - era_click_markers_before)

            # Send a Today-context message, watch for response.
            since = self.console.now()
            self.ui.send_chat("Tell me about Today")
            reply = self.ui.wait_for_lori_turn(since, timeout_ms=45_000)
            r.observations["lori_today_reply"] = reply[:300]

            db_delta = self.dblock.delta()
            r.observations["db_lock_delta"] = db_delta

            stuck = sum(1 for c in click_results if not c["ok"])
            if stuck > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["lifemap_dead_buttons"]
                r.notes.append(f"{stuck}/{len(click_sequence)} era clicks failed")
                # Capture screenshot + DOM diagnostics so we can tell
                # whether buttons are truly dead or something is over
                # them (per ChatGPT's run-2 read).
                r.screenshots.append(self.ui.screenshot("test08_era_cycle_dead_state"))
                try:
                    r.observations["active_element"] = self.ui.page.evaluate("""
                        () => {
                          const a = document.activeElement;
                          return a ? {
                            tag: a.tagName,
                            id: a.id || '',
                            cls: (typeof a.className === 'string' ? a.className : ''),
                            text: (a.innerText || a.value || '').slice(0, 120)
                          } : null;
                        }
                    """)
                    r.observations["visible_popovers"] = self.ui.page.evaluate("""
                        () => Array.from(document.querySelectorAll('[popover]'))
                          .filter(el => {
                            try { return el.matches(':popover-open'); }
                            catch (_) { return false; }
                          })
                          .map(el => ({
                            id: el.id || '',
                            cls: (typeof el.className === 'string' ? el.className : ''),
                            text: (el.innerText || '').slice(0, 120)
                          }))
                    """)
                    r.observations["era_overlays"] = self.ui.page.evaluate("""
                        () => Array.from(document.querySelectorAll('.lv-interview-confirm-overlay'))
                          .map(el => ({
                            visible: el.offsetParent !== null,
                            text: (el.innerText || '').slice(0, 200)
                          }))
                    """)
                except Exception:
                    pass
            elif db_delta > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            elif not reply:
                r.status = "AMBER"
                r.notes.append("No Lori reply captured within 45s; chat may be functional but slow.")
            else:
                r.status = "PASS"
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test08_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def test_09_today_date_awareness(self) -> TestResult:
        r = TestResult(id="TEST-09", name="Today mode date awareness")
        t0 = time.time()
        # Local-machine date for matcher (per WO §TEST-09).
        today = dt.date.today()
        weekday = today.strftime("%A")          # Friday
        month_name = today.strftime("%B")       # May
        day_num = today.day                      # 1
        year = today.year                        # 2026
        # Acceptable patterns: weekday OR month+day (with or without year).
        positive_patterns = [
            re.compile(rf"\b{re.escape(weekday)}\b", re.I),
            re.compile(rf"\b{re.escape(month_name)}\s+{day_num}(?:st|nd|rd|th)?\b", re.I),
            re.compile(rf"\b{day_num}(?:st|nd|rd|th)?\s+(?:of\s+)?{re.escape(month_name)}\b", re.I),
            re.compile(rf"\b{year}\b"),
        ]
        negative_patterns = [re.compile(p, re.I) for p in TEST09_FAIL_PATTERNS]

        try:
            r.narrator_name = self.ui.add_test_narrator("clear_direct")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            self.ui.click_life_map_era("Today")
            since = self.console.now()
            self.ui.send_chat("What day is it?")
            reply = self.ui.wait_for_lori_turn(since, timeout_ms=45_000)
            r.observations["lori_reply"] = reply

            has_positive = any(p.search(reply) for p in positive_patterns)
            has_negative = any(p.search(reply) for p in negative_patterns)
            r.observations["matched_positive"] = has_positive
            r.observations["matched_negative"] = has_negative
            r.observations["expected_weekday"] = weekday
            r.observations["expected_date"] = f"{month_name} {day_num}, {year}"

            if has_negative:
                # Real product hard-stop: Lori actually said one of the
                # capability-denial phrases. This is the today_no_date bug.
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["today_no_date"]
                r.screenshots.append(self.ui.screenshot("test09_bad_date_reply"))
            elif has_positive:
                r.status = "PASS"
            elif not (reply or "").strip():
                # No reply captured at all. Could be: wait_for_lori_turn
                # timeout, console scrape regex miss (Playwright doesn't
                # auto-serialize object args in console.log), or the chat
                # send didn't fire. NOT a today_no_date hard-stop — that
                # specifically means Lori gave a capability-denial reply.
                r.status = "FAIL"
                r.notes.append(
                    "No Lori reply captured after 'What day is it?'. Could be "
                    "console-scrape regex miss (Playwright stringifies object "
                    "args as JSHandle@object), wait_for_lori_turn timeout, or "
                    "chat send didn't fire. Inspect screenshot to triage."
                )
                r.screenshots.append(self.ui.screenshot("test09_no_lori_reply"))
            else:
                # Reply present but neither positive nor negative phrase
                # matched. Likely a date-adjacent answer that doesn't
                # contain weekday/month/year. Still a fail — but not the
                # today_no_date hard-stop unless we see a denial phrase.
                r.status = "FAIL"
                r.notes.append(
                    "Lori replied but did not include today's date or day-of-week."
                )
                r.screenshots.append(self.ui.screenshot("test09_bad_date_reply"))
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test09_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    # ── shared intake helper for TEST-01/02/03/04/05/06/10 ─────────
    def _intake(self, name: str, dob: str, place: str, order: str,
                stop_after_field: Optional[str] = None) -> List[float]:
        """Walk the QF intake by typing each field's value when Lori asks.
        stop_after_field: one of 'name'/'dob'/'place'/'order' to stop early.
        Returns the list of send timestamps (one per field sent)."""
        sends = []
        # We rely on the QF walk's natural progression: each Send fires
        # the next [SYSTEM_QF: ...] directive. Wait for Lori's reply
        # between sends so the next field is asked.
        for field_id, value in [
                ("name", name), ("dob", dob), ("place", place), ("order", order)]:
            since = self.console.now()
            sends.append(self.ui.send_chat(value))
            self.ui.wait_for_lori_turn(since, timeout_ms=45_000)
            if stop_after_field == field_id:
                break
        return sends

    def _complete_identity_for_test_narrator(
        self,
        name: str = "Era Cycle Test",
        dob: str = "March 22, 1931",
        place: str = "Montreal, Quebec, Canada",
        order: str = "youngest",
    ) -> None:
        """Complete narrator identity onboarding so post-onboarding
        product behaviors become available.

        Used by tests that need a post-identity narrator state — TEST-08
        Life Map era cycle is the canonical example, since the
        historical-era buttons (Earliest Years through Later Years)
        require identity_complete to activate. Today is special-cased
        and clickable any time, but the rest only unlock after the
        narrator has at minimum a name + DOB.

        Per MANUAL-PARENT-READINESS-V1 → Manual TEST-08A. ChatGPT's
        ground-truth name "Era Cycle Test" defaults match the manual
        pack so the harness and manual run produce comparable narrator
        states. Callers can override any field for tests that need
        specific identity values.

        The QF walk fires for any incomplete narrator regardless of
        session_style — clear_direct narrators still get the identity
        intake when they're missing name/DOB. So this helper works for
        any style we created the narrator with. After all 4 fields are
        saved, we wait briefly for the QF walk to settle (handoff to
        non-identity phase, identity_complete fires, Life Map historical
        eras unlock)."""
        self._intake(name, dob, place, order)
        # Settle: QF walk emits handoff prompt + Life Map state updates;
        # ~2s gives identity_complete propagation time without being
        # gratuitously slow.
        self.ui.page.wait_for_timeout(2_000)

    def test_01_clean_control(self) -> TestResult:
        r = TestResult(id="TEST-01", name="Clean Control")
        t0 = time.time()
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            since = self.console.now()
            self._intake("Mary Test", "March 22, 1931",
                         "Montreal, Quebec, Canada", "youngest")
            rejections = self.console.matches(
                r"\[bb-drift\]\s*qf_walk\s*validation\s*REJECTED", since_ts=since)
            r.console_matches.extend(rejections[:3])
            full = self.ui.read_bb_field("personal.fullName")
            dob = self.ui.read_bb_field("personal.dateOfBirth")
            place = self.ui.read_bb_field("personal.placeOfBirth")
            order = self.ui.read_bb_field("personal.birthOrder")
            self.ui.open_peek_memoir()
            peek = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()  # reuses Esc to close popover
            r.observations.update({
                "personal.fullName": full,
                "personal.dateOfBirth": dob,
                "personal.placeOfBirth": place,
                "personal.birthOrder": order,
                "peek_contains_name": "Mary Test" in peek,
                "peek_len": len(peek),
                "rejection_count": len(rejections),
                "db_lock_delta": self.dblock.delta(),
            })

            ok = (
                len(rejections) == 0 and
                "Mary Test" in (full or "") and
                "1931" in (dob or "") and
                ("Montreal" in (place or "")) and
                ("youngest" in (order or "").lower()) and
                "Mary Test" in peek and
                self.dblock.delta() == 0
            )
            r.status = "PASS" if ok else "FAIL"
            if not ok:
                if self.dblock.delta() > 0:
                    r.hard_stop = True
                    r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
                if rejections:
                    r.notes.append("Clean values were rejected — validator over-fires.")
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test01_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def _validator_test(self, test_id: str, name: str,
                        intake_args: List[str],
                        rejected_field: str,
                        rejected_phrase: str,
                        hard_stop_label_key: str,
                        stop_after_field: str) -> TestResult:
        """Shared body for TEST-02/03/04. Performs intake, asserts the
        target field shows the rejection log, BB field is empty, and
        Peek doesn't show the rejected phrase as truth."""
        r = TestResult(id=test_id, name=name)
        t0 = time.time()
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            since = self.console.now()
            self._intake(*intake_args, stop_after_field=stop_after_field)

            # Look for the rejection log on the target field.
            field_path = f"personal.{rejected_field}"
            rx = re.escape(field_path)
            rejection_logs = self.console.matches(
                rf"\[bb-drift\]\s*qf_walk\s*validation\s*REJECTED\s*{rx}",
                since_ts=since,
            )
            r.console_matches.extend(rejection_logs[:3])

            actual = self.ui.read_bb_field(field_path)
            self.ui.open_peek_memoir()
            peek = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()

            # Pollution check: bad phrase must NOT appear as a confirmed
            # fact in Peek. We use a substring check; if the phrase shows
            # up at all in Peek that's a hard stop (the manual pack also
            # treats this as RED).
            peek_polluted = rejected_phrase.lower() in (peek or "").lower()
            r.observations.update({
                field_path: actual,
                "rejection_log_seen": len(rejection_logs) > 0,
                "rejection_count": len(rejection_logs),
                "peek_contains_phrase": peek_polluted,
                "db_lock_delta": self.dblock.delta(),
            })

            truth_polluted = rejected_phrase.lower() in (actual or "").lower()
            if truth_polluted:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS[hard_stop_label_key]
            elif peek_polluted:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["memoir_pollution"]
            elif len(rejection_logs) == 0:
                r.status = "FAIL"
                r.notes.append("No rejection log for the target field — validator silent.")
            elif self.dblock.delta() > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            else:
                r.status = "PASS"
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot(f"{test_id}_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def test_02_reject_place_narrative(self) -> TestResult:
        return self._validator_test(
            test_id="TEST-02",
            name="Reject placeOfBirth Narrative",
            intake_args=["BadPlace Test", "March 22, 1931",
                         "My dad worked nights at the aluminum plant.",
                         "youngest"],
            rejected_field="placeOfBirth",
            rejected_phrase="My dad worked nights at the aluminum plant",
            hard_stop_label_key="place_truth_pollution",
            stop_after_field="place",
        )

    def test_03_reject_order_complaint(self) -> TestResult:
        return self._validator_test(
            test_id="TEST-03",
            name="Reject birthOrder Complaint",
            intake_args=["BadOrder Test", "March 22, 1931",
                         "Montreal, Quebec, Canada",
                         "I just told you something you ignored."],
            rejected_field="birthOrder",
            rejected_phrase="I just told you something you ignored",
            hard_stop_label_key="order_truth_pollution",
            stop_after_field="order",
        )

    def test_04_reject_name_first_person(self) -> TestResult:
        # Special case — only the name field is exercised.
        r = TestResult(id="TEST-04", name="Reject fullName First-Person")
        t0 = time.time()
        bad_name = "I think my name is whatever you say it is."
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            since = self.console.now()
            self.ui.send_chat(bad_name)
            self.ui.wait_for_lori_turn(since, timeout_ms=45_000)

            rejection_logs = self.console.matches(
                r"\[bb-drift\]\s*qf_walk\s*validation\s*REJECTED\s*personal\.fullName",
                since_ts=since,
            )
            r.console_matches.extend(rejection_logs[:3])
            actual = self.ui.read_bb_field("personal.fullName")
            self.ui.open_peek_memoir()
            peek = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()

            peek_polluted = bad_name.lower() in (peek or "").lower()
            truth_polluted = bad_name.lower() in (actual or "").lower()
            r.observations.update({
                "personal.fullName": actual,
                "rejection_log_seen": len(rejection_logs) > 0,
                "peek_contains_phrase": peek_polluted,
                "db_lock_delta": self.dblock.delta(),
            })

            if truth_polluted:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["memoir_pollution"]
            elif peek_polluted:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["memoir_pollution"]
            elif len(rejection_logs) == 0:
                r.status = "FAIL"
                r.notes.append("No rejection log for personal.fullName — validator silent.")
            elif self.dblock.delta() > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            else:
                r.status = "PASS"
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test04_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def test_05_reset_identity_clears_all(self) -> TestResult:
        r = TestResult(id="TEST-05", name="Reset Identity clears all identity surfaces")
        t0 = time.time()
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            self._intake("Reset Test", "April 5, 1945", "Boise, Idaho", "oldest")

            # Confirm the 4 fields filled.
            pre = {
                "fullName": self.ui.read_bb_field("personal.fullName"),
                "dateOfBirth": self.ui.read_bb_field("personal.dateOfBirth"),
                "placeOfBirth": self.ui.read_bb_field("personal.placeOfBirth"),
                "birthOrder": self.ui.read_bb_field("personal.birthOrder"),
            }
            r.observations["pre_reset"] = pre

            # Open Bio Builder + click Reset Identity.
            since = self.console.now()
            self.ui.open_bio_builder()
            clicked, dialog_text = self.ui.click_reset_identity()
            r.observations["dialog_text"] = dialog_text
            r.observations["dialog_clicked"] = clicked
            self.ui.page.wait_for_timeout(1_500)

            # Required console markers (5 of them per Appendix A).
            required = [
                r"\[bb-reset-identity\]\s*starting reset for pid=",
                r"\[bb-reset-identity\]\s*projection cleared:",
                r"\[bb-reset-identity\]\s*cleared localStorage",
                r"\[bb-reset-identity\]\s*PATCH person cleared DOB\+POB",
                r"\[bb-reset-identity\]\s*complete",
            ]
            marker_seen = {}
            for pat in required:
                hits = self.console.matches(pat, since_ts=since)
                marker_seen[pat] = len(hits) > 0
                r.console_matches.extend(hits[:1])
            r.observations["markers"] = marker_seen
            all_markers = all(marker_seen.values())

            # Post-reset: BB fields cleared.
            post = {
                "fullName": self.ui.read_bb_field("personal.fullName"),
                "dateOfBirth": self.ui.read_bb_field("personal.dateOfBirth"),
                "placeOfBirth": self.ui.read_bb_field("personal.placeOfBirth"),
                "birthOrder": self.ui.read_bb_field("personal.birthOrder"),
            }
            r.observations["post_reset"] = post
            all_cleared = all(not (v or "").strip() for v in post.values())

            # Peek must not contain Reset Test or Boise.
            self.ui.open_peek_memoir()
            peek = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()
            r.observations["peek_contains_reset_test"] = "Reset Test" in peek
            r.observations["peek_contains_boise"] = "Boise" in peek

            ok = (
                all_markers and all_cleared and
                "Reset Test" not in peek and "Boise" not in peek
            )
            r.status = "PASS" if ok else "FAIL"
            if not all_markers:
                missing = [p for p, seen in marker_seen.items() if not seen]
                r.notes.append(f"Missing markers: {missing}")
            if not all_cleared:
                r.notes.append(f"Fields not cleared: {post}")
            if "Reset Test" in peek or "Boise" in peek:
                r.notes.append("Peek still contains pre-reset identity values.")
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test05_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def test_06_cross_narrator_isolation(self) -> TestResult:
        r = TestResult(id="TEST-06", name="Cross-narrator state isolation")
        t0 = time.time()
        try:
            name_a = self.ui.add_test_narrator("questionnaire_first")
            r.observations["narrator_a"] = name_a
            name_b = self.ui.add_test_narrator("clear_direct")
            r.observations["narrator_b"] = name_b
            r.narrator_name = f"A={name_a} | B={name_b}"

            # Switch back to A.
            self._switch_to_narrator(name_a)
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            self._intake("Janice Like", "August 30, 1939",
                         "Spokane, Washington", "youngest")
            a_full = self.ui.read_bb_field("personal.fullName")
            self.ui.open_peek_memoir()
            a_peek = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()
            self.ui.wrap_session()
            r.observations["a_full"] = a_full
            r.observations["a_peek_has_janice"] = "Janice Like" in a_peek

            # Switch to B.
            self._switch_to_narrator(name_b)
            self.ui.page.wait_for_timeout(1_500)
            b_full_before = self.ui.read_bb_field("personal.fullName")
            self.ui.open_peek_memoir()
            b_peek_before = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()
            r.observations["b_full_before"] = b_full_before
            r.observations["b_peek_before_has_janice"] = "Janice Like" in b_peek_before
            r.observations["b_peek_before_has_spokane"] = "Spokane" in b_peek_before

            # B intake.
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            self._intake("Kent Like", "April 4, 1936", "Stanley, North Dakota", "oldest")
            b_full_after = self.ui.read_bb_field("personal.fullName")
            self.ui.open_peek_memoir()
            b_peek_after = self.ui.read_peek_memoir_text()
            self.ui.close_bug_panel()
            r.observations["b_full_after"] = b_full_after
            r.observations["b_peek_after_has_kent"] = "Kent Like" in b_peek_after
            r.observations["b_peek_after_has_janice"] = "Janice Like" in b_peek_after
            r.observations["b_peek_after_has_spokane"] = "Spokane" in b_peek_after
            r.observations["db_lock_delta"] = self.dblock.delta()

            leaked = (
                "Janice Like" in b_peek_before or "Spokane" in b_peek_before or
                "Janice Like" in b_peek_after or "Spokane" in b_peek_after or
                (b_full_before or "").strip() != ""
            )
            if leaked:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["cross_narrator_leak"]
            elif self.dblock.delta() > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            elif "Kent Like" not in b_peek_after:
                r.status = "AMBER"
                r.notes.append("B's intake didn't visibly reach Peek (memoir render lag?).")
            else:
                r.status = "PASS"
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test06_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def _switch_to_narrator(self, name: str) -> None:
        """Open switcher, click the existing narrator card by visible name."""
        try:
            self.ui.page.locator(SEL["active_narrator_chip"]).first.click(timeout=3_000)
            self.ui.page.wait_for_timeout(500)
            # Click the FIRST card whose visible label matches the name.
            self.ui.page.get_by_text(name, exact=False).first.click(timeout=3_000)
            self.ui.page.wait_for_timeout(1_500)
        except (PWTimeout, PWError) as e:
            print(f"  [warn] switch_to_narrator({name}) failed: {e}", file=sys.stderr)

    def test_12_leap_year_dob_awareness(self) -> TestResult:
        """Verify Lori handles a valid leap-year DOB cleanly.

        Feb 29 1940 is the gnarliest birthday edge case. It exercises:
          - DOB normalizer (must keep 1940-02-29, not coerce to 03-01
            or drop the day per BUG-210 history)
          - Lori's verbal response (must NOT say "that's not a real
            date" / "are you sure" / "let me check" — those are both
            wrong (1940 WAS a leap year) and a WO-10C correction
            violation against an older narrator)
          - BB persistence (date must round-trip through PUT
            /api/bio-builder/questionnaire)

        Christopher noted on 2026-05-01 that Lori handled this case
        well in his manual run; this test is the regression guard.
        """
        r = TestResult(id="TEST-12", name="Leap-year DOB awareness")
        t0 = time.time()
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            since = self.console.now()
            # Walk the QF intake — name then leap-year DOB. We stop
            # there; the date is the test surface.
            sends = []
            for field, value in [
                ("name", "Margaret Leap"),
                ("dob",  "February 29, 1940"),
            ]:
                ts = self.console.now()
                sends.append(self.ui.send_chat(value))
                self.ui.wait_for_lori_turn(ts, timeout_ms=45_000)

            # Capture Lori's reply to the DOB turn (the second send's
            # subsequent reply).
            dob_send_ts = sends[-1]
            dob_reply = self.ui.wait_for_lori_turn(dob_send_ts, timeout_ms=10_000)
            r.observations["lori_dob_reply"] = dob_reply

            # BB persistence check.
            bb_dob = self.ui.read_bb_field("personal.dateOfBirth")
            r.observations["personal.dateOfBirth"] = bb_dob

            # Defensive-language check.
            negative_hits = []
            for pat in LEAP_YEAR_FAIL_PATTERNS:
                if re.search(pat, dob_reply, re.I):
                    negative_hits.append(pat)
            r.observations["matched_defensive_phrases"] = negative_hits

            # Acknowledgement check — Lori SHOULD reflect the date back
            # at least minimally (mention 1940 OR Feb 29 OR "leap" OR
            # acknowledge with continuation). An empty reply is also a
            # fail (we already lost the turn).
            ack_patterns = [
                r"\b(?:february\s*29|feb\s*29|29(?:th)?\s+of\s+february)\b",
                r"\b1940\b",
                r"\bleap\b",
            ]
            ack_hits = []
            for pat in ack_patterns:
                if re.search(pat, dob_reply, re.I):
                    ack_hits.append(pat)
            r.observations["matched_ack_patterns"] = ack_hits

            # DOB persistence check — must contain "1940" AND ("02-29"
            # OR "Feb 29" OR "February 29"). Empty value or year-only
            # ("1940-01-01") = FAIL.
            dob_lower = (bb_dob or "").lower()
            dob_persisted = (
                "1940" in dob_lower and
                ("02-29" in dob_lower or "2-29" in dob_lower or
                 "feb 29" in dob_lower or "february 29" in dob_lower)
            )
            r.observations["dob_persisted_correctly"] = dob_persisted

            r.observations["db_lock_delta"] = self.dblock.delta()

            if negative_hits:
                # Lori said something defensive / corrective. WO-10C
                # violation + factual error (1940 was a leap year).
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["leap_year_correction"]
                r.notes.append(
                    f"Lori's reply matched defensive pattern(s): {negative_hits}"
                )
                r.screenshots.append(self.ui.screenshot("test12_leap_year_correction"))
            elif not dob_persisted:
                # Lori was warm but the date didn't make it to BB.
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["leap_year_dob_lost"]
                r.notes.append(
                    f"Reply OK but BB.dateOfBirth='{bb_dob}' lost the leap day."
                )
                r.screenshots.append(self.ui.screenshot("test12_leap_year_dob_lost"))
            elif self.dblock.delta() > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            elif not (dob_reply or "").strip():
                r.status = "FAIL"
                r.notes.append("No Lori reply captured for DOB turn.")
                r.screenshots.append(self.ui.screenshot("test12_no_reply"))
            elif not ack_hits:
                # Reply present, no defensive language, BB persisted —
                # but Lori didn't acknowledge the date specifically.
                # AMBER (clarity could be better) but not a hard-stop.
                r.status = "AMBER"
                r.notes.append(
                    "Lori didn't echo back the date (no '1940' / 'Feb 29' / "
                    "'leap' in reply). Clarity could be stronger but no "
                    "correction or persistence error."
                )
            else:
                r.status = "PASS"
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test12_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    def test_10_memoir_peek_equals_export(self) -> TestResult:
        r = TestResult(id="TEST-10", name="Memoir Peek = Export")
        t0 = time.time()
        try:
            r.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)
            self._intake("Memoir Test", "June 14, 1942",
                         "Cleveland, Ohio", "middle child")

            self.ui.open_peek_memoir()
            self.ui.page.wait_for_timeout(800)
            peek_text = self.ui.read_peek_memoir_text()
            r.observations["peek_text_len"] = len(peek_text)

            txt_path = self.ui.download_memoir_txt(self.ui.downloads_dir)
            if not txt_path:
                r.status = "FAIL"
                r.notes.append("Could not trigger TXT download from Peek.")
                return r
            r.downloads.append(str(txt_path))
            try:
                txt_content = txt_path.read_text(errors="ignore")
            except Exception as e:
                r.status = "FAIL"
                r.notes.append(f"Could not read TXT: {e}")
                return r

            # Compare modulo whitespace.
            peek_norm = re.sub(r"\s+", " ", peek_text).strip()
            txt_norm = re.sub(r"\s+", " ", txt_content).strip()
            r.observations["peek_norm_len"] = len(peek_norm)
            r.observations["txt_norm_len"] = len(txt_norm)

            # Section sentinel: each surface should mention these eras.
            required_eras = ["Earliest Years", "Building Years", "Today"]
            era_in_peek = {e: e in peek_text for e in required_eras}
            era_in_txt = {e: e in txt_content for e in required_eras}
            r.observations["era_in_peek"] = era_in_peek
            r.observations["era_in_txt"] = era_in_txt

            # Identity content should appear in both.
            id_in_peek = "Memoir Test" in peek_text
            id_in_txt = "Memoir Test" in txt_content
            r.observations["identity_in_peek"] = id_in_peek
            r.observations["identity_in_txt"] = id_in_txt
            r.observations["db_lock_delta"] = self.dblock.delta()

            content_equal = peek_norm == txt_norm
            substantive_match = id_in_peek and id_in_txt and all(
                era_in_peek[e] == era_in_txt[e] for e in required_eras)

            if self.dblock.delta() > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            elif content_equal:
                r.status = "PASS"
            elif substantive_match:
                r.status = "AMBER"
                r.notes.append("Substantive content matches; whitespace/markup differs.")
            else:
                r.status = "FAIL"
                r.notes.append("Peek text and TXT export diverge on identity or era sections.")
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot("test10_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    # ── TEST-11 narration sample dispatch (parameterized) ──────────
    def _run_narration_sample(self, narrator_spec: Dict[str, Any],
                               size: str) -> TestResult:
        """Run one (narrator × sample-size) pair: send the narration as
        one chat message, wait for Lori's reply, then send each follow-up
        question and score the reply against the matchers.

        Per docs/test-packs/NARRATION_SAMPLES_AUTHORING_SPEC.md:
          - PASS  = Lori responded to narration AND every follow-up matched
          - AMBER = Lori responded but ≥1 follow-up missed
          - FAIL  = no response OR multiple follow-ups missed
        """
        narrator_id = narrator_spec.get("narrator_id", "unknown")
        test_id = f"TEST-NARR-{narrator_id}-{size}"
        label = narrator_spec.get("label", narrator_id)
        r = TestResult(id=test_id, name=f"Narration {size}: {label}")
        t0 = time.time()

        sample_text = (narrator_spec.get("samples") or {}).get(size, "")
        if not sample_text:
            r.status = "FAIL"
            r.notes.append(f"No '{size}' sample in narrator spec.")
            r.elapsed_ms = int((time.time() - t0) * 1000)
            return r
        r.observations["sample_word_count"] = len(sample_text.split())

        try:
            r.narrator_name = self.ui.add_test_narrator("clear_direct")
            self.ui.session_start()
            self.ui.page.wait_for_timeout(1_500)

            # 1. Send the narration as one big chat message.
            since = self.console.now()
            self.ui.send_chat(sample_text)
            narration_reply = self.ui.wait_for_lori_turn(since, timeout_ms=90_000)
            r.observations["narration_reply"] = (narration_reply or "")[:400]
            if not (narration_reply or "").strip():
                r.status = "FAIL"
                r.notes.append("Lori didn't respond to the narration within 90s.")
                r.screenshots.append(self.ui.screenshot(f"{test_id}_no_narration_reply"))
                return r

            # 2. Run each follow-up.
            today = dt.date.today()
            weekday = today.strftime("%A")
            month_name = today.strftime("%B")
            day_num = today.day
            year = today.year
            local_clock_patterns = [
                re.compile(rf"\b{re.escape(weekday)}\b", re.I),
                re.compile(rf"\b{re.escape(month_name)}\s+{day_num}(?:st|nd|rd|th)?\b", re.I),
                re.compile(rf"\b{day_num}(?:st|nd|rd|th)?\s+(?:of\s+)?{re.escape(month_name)}\b", re.I),
                re.compile(rf"\b{year}\b"),
                re.compile(r"\b\d{1,2}:\d{2}\b"),
                re.compile(r"\b\d{1,2}\s*(?:AM|PM|a\.m\.|p\.m\.)\b", re.I),
            ]

            follow_results: List[Dict[str, Any]] = []
            for fu in (narrator_spec.get("follow_ups") or []):
                ask = fu.get("ask", "")
                must_any = fu.get("must_match_any") or []
                must_clock = bool(fu.get("must_match_local_clock"))
                fu_since = self.console.now()
                self.ui.send_chat(ask)
                fu_reply = self.ui.wait_for_lori_turn(fu_since, timeout_ms=45_000)

                matched = False
                if must_clock:
                    matched = any(p.search(fu_reply or "") for p in local_clock_patterns)
                if not matched and must_any:
                    matched = any(
                        s.lower() in (fu_reply or "").lower() for s in must_any
                    )
                follow_results.append({
                    "ask": ask,
                    "matched": matched,
                    "reply": (fu_reply or "")[:240],
                    "must_any": must_any,
                    "must_clock": must_clock,
                })
            r.observations["follow_ups"] = follow_results
            r.observations["db_lock_delta"] = self.dblock.delta()

            misses = sum(1 for f in follow_results if not f["matched"])
            total = len(follow_results)
            r.observations["follow_up_misses"] = misses
            r.observations["follow_up_total"] = total

            if self.dblock.delta() > 0:
                r.status = "FAIL"
                r.hard_stop = True
                r.hard_stop_label = HARD_STOP_LABELS["db_lock"]
            elif misses == 0:
                r.status = "PASS"
            elif misses == 1:
                r.status = "AMBER"
                r.notes.append(
                    f"1/{total} follow-up missed: "
                    + str(next((f["ask"] for f in follow_results if not f["matched"]), ""))
                )
            else:
                r.status = "FAIL"
                missed_qs = [f["ask"] for f in follow_results if not f["matched"]]
                r.notes.append(f"{misses}/{total} follow-ups missed: {missed_qs}")
                r.screenshots.append(self.ui.screenshot(f"{test_id}_follow_up_misses"))
        except Exception as e:
            r.status = "FAIL"
            r.notes.append(f"exception: {e}")
            r.screenshots.append(self.ui.screenshot(f"{test_id}_fail"))
        finally:
            try: self.ui.wrap_session()
            except Exception: pass
            r.elapsed_ms = int((time.time() - t0) * 1000)
        return r

    # ── Run all ──────────────────────────────────────────────────────
    def run_all(self, test_filter: Optional[List[str]] = None,
                stop_on_red: bool = False,
                narration_specs: Optional[List[Dict[str, Any]]] = None,
                narration_sizes: Optional[List[str]] = None,
                narration_only: bool = False) -> HarnessReport:
        # Order — Life Map / Today first (cold path), then validator, then
        # reset / isolation, then memoir export, then leap-year DOB, then
        # narration sample matrix. Mirrors the manual pack's recommended
        # cold-priority order, with narration tests last because they're
        # the slowest (~3-5 min per pair).
        steps: List[Tuple[str, Any]] = [
            ("TEST-07", self.test_07_lifemap_cold_start),
            ("TEST-08", self.test_08_lifemap_era_cycle),
            ("TEST-09", self.test_09_today_date_awareness),
            ("TEST-01", self.test_01_clean_control),
            ("TEST-02", self.test_02_reject_place_narrative),
            ("TEST-03", self.test_03_reject_order_complaint),
            ("TEST-04", self.test_04_reject_name_first_person),
            ("TEST-05", self.test_05_reset_identity_clears_all),
            ("TEST-06", self.test_06_cross_narrator_isolation),
            ("TEST-10", self.test_10_memoir_peek_equals_export),
            ("TEST-12", self.test_12_leap_year_dob_awareness),
        ]
        # Narration matrix — register one entry per (narrator × size).
        if narration_specs:
            sizes = narration_sizes or ["clean", "messy", "emotional", "fragmented"]
            for spec in narration_specs:
                nid = spec.get("narrator_id", "unknown")
                for size in sizes:
                    tid = f"TEST-NARR-{nid}-{size}"
                    # Bind spec/size into a closure so each test
                    # invocation gets its own (narrator, size) pair.
                    def _make_runner(s=spec, sz=size):
                        return lambda: self._run_narration_sample(s, sz)
                    steps.append((tid, _make_runner()))
        # narration_only: skip everything that isn't a NARR test.
        if narration_only:
            steps = [(tid, fn) for tid, fn in steps if tid.startswith("TEST-NARR-")]
        for tid, fn in steps:
            if test_filter and tid not in test_filter:
                self.report.tests.append(TestResult(
                    id=tid, name=fn.__name__.replace("_", " "),
                    status="SKIP", notes=["filtered out via --only"]))
                continue
            print(f"  ▸ {tid} {fn.__name__} ...", flush=True)
            try:
                result = fn()
            except Exception as e:
                result = TestResult(id=tid, name=fn.__name__, status="FAIL")
                result.notes.append(f"top-level exception: {e}")
            self.report.tests.append(result)
            print(f"    {tid}: {result.status}"
                  + (f"  [HARD-STOP: {result.hard_stop_label}]" if result.hard_stop else ""),
                  flush=True)
            if stop_on_red and result.hard_stop:
                print(f"  [stop-on-red] aborting after {tid}", flush=True)
                break

        self.report.db_lock_delta = self.dblock.delta()
        self.report.hard_stops = sorted({
            t.hard_stop_label for t in self.report.tests if t.hard_stop and t.hard_stop_label
        })
        # Aggregate verdict per WO acceptance gate.
        statuses = [t.status for t in self.report.tests if t.status != "SKIP"]
        if any(t.hard_stop for t in self.report.tests) or "FAIL" in statuses:
            self.report.overall = "RED"
        elif "AMBER" in statuses:
            self.report.overall = "AMBER"
        elif statuses and all(s == "PASS" for s in statuses):
            self.report.overall = "GREEN"
        else:
            self.report.overall = "AMBER"
        return self.report


# ─────────────────────────────────────────────────────────────────────
# REPORT WRITER
# ─────────────────────────────────────────────────────────────────────
def write_report(report: HarnessReport, output_path: Path,
                 console_path: Path, raw_console: List[Dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # JSON.
    payload = {
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "base_url": report.base_url,
        "api": report.api,
        "test_pack": report.test_pack,
        "overall": report.overall,
        "hard_stops": report.hard_stops,
        "db_lock_delta": report.db_lock_delta,
        "tests": [asdict(t) for t in report.tests],
    }
    output_path.write_text(json.dumps(payload, indent=2, default=str))

    # Console + summary block.
    lines = []
    lines.append("PARENT-SESSION-READINESS-V1 HARNESS")
    lines.append("")
    lines.append(f"  base_url: {report.base_url}")
    lines.append(f"  api:      {report.api}")
    lines.append(f"  started:  {report.started_at}")
    lines.append(f"  finished: {report.finished_at}")
    lines.append("")
    name_map = {
        "TEST-01": "Clean Control",
        "TEST-02": "Reject placeOfBirth narrative",
        "TEST-03": "Reject birthOrder complaint",
        "TEST-04": "Reject fullName first-person",
        "TEST-05": "Reset Identity clears all",
        "TEST-06": "Cross-narrator state isolation",
        "TEST-07": "Life Map cold-start",
        "TEST-08": "Life Map era cycle",
        "TEST-09": "Today mode date awareness",
        "TEST-10": "Memoir Peek = Export",
        "TEST-12": "Leap-year DOB awareness",
    }
    # Render in two sections: the static pack first, then the narration
    # matrix (TEST-NARR-*) — variable size depending on samples file.
    by_id = {t.id: t for t in report.tests}
    static_ids = ["TEST-01", "TEST-02", "TEST-03", "TEST-04", "TEST-05",
                  "TEST-06", "TEST-07", "TEST-08", "TEST-09", "TEST-10",
                  "TEST-12"]
    # Static tests absent from the report fall into two cases:
    #   (a) deliberately filtered out by --narration-only → render as
    #       SKIP so the run summary doesn't look like a silent regression
    #   (b) genuinely missing (run aborted before they got a chance) →
    #       render as MISSING so the operator notices
    # The narration_only flag distinguishes them.
    absent_label = "SKIP" if report.narration_only else "MISSING"
    for tid in static_ids:
        t = by_id.get(tid)
        status = (t.status if t else absent_label).ljust(7)
        label = name_map.get(tid, tid)
        lines.append(f"  {tid:<10} {label:<35}  {status}")

    narration_tests = sorted(
        [t for t in report.tests if t.id.startswith("TEST-NARR-")],
        key=lambda t: t.id,
    )
    if narration_tests:
        lines.append("")
        lines.append("  Narration matrix:")
        for t in narration_tests:
            # ID is TEST-NARR-<narrator_id>-<size>; trim a bit for layout.
            short = t.id.replace("TEST-NARR-", "")
            label = (t.name or "")[:50]
            lines.append(f"    {short:<48} {t.status}")
    lines.append("")
    lines.append(f"  OVERALL: {report.overall}")
    lines.append(f"  Hard stops fired: {', '.join(report.hard_stops) if report.hard_stops else '(none)'}")
    lines.append(f"  DB lock delta: {report.db_lock_delta}")
    lines.append("")

    # Per-test detail.
    for t in report.tests:
        lines.append("─" * 70)
        lines.append(f"{t.id} {t.name}  ({t.status})  [{t.elapsed_ms} ms]")
        if t.narrator_name:
            lines.append(f"  narrator: {t.narrator_name}")
        if t.hard_stop:
            lines.append(f"  HARD STOP: {t.hard_stop_label}")
        for k, v in (t.observations or {}).items():
            lines.append(f"  obs.{k}: {v}")
        for m in t.console_matches:
            lines.append(f"  console: {m[:200]}")
        for n in t.notes:
            lines.append(f"  note: {n}")
        for s in t.screenshots:
            lines.append(f"  screenshot: {s}")
        for d in t.downloads:
            lines.append(f"  download: {d}")
    lines.append("─" * 70)
    lines.append("")
    lines.append(f"Console entries captured: {len(raw_console)}")

    console_path.parent.mkdir(parents=True, exist_ok=True)
    console_path.write_text("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="WO-PARENT-READINESS-HARNESS-01 Playwright harness",
    )
    ap.add_argument("--base-url", required=True,
                    help="Hornelore UI URL (e.g. http://localhost:8082/ui/hornelore1.0.html)")
    ap.add_argument("--api", required=True,
                    help="Hornelore API URL (e.g. http://localhost:8000)")
    ap.add_argument("--test-pack",
                    default="docs/test-packs/PARENT-SESSION-READINESS-V1.md",
                    help="Path to the manual test pack (record-keeping only)")
    ap.add_argument("--output", required=True,
                    help="Path to write the JSON report (timestamp suffix added)")
    ap.add_argument("--only", default="",
                    help="Comma-separated test IDs to run (e.g. TEST-07,TEST-09)")
    ap.add_argument("--stop-on-red", action="store_true",
                    help="Abort on first hard-stop")
    ap.add_argument("--headless", action="store_true",
                    help="Run Chromium headless (default: headed)")
    ap.add_argument("--slow-mo-ms", type=int, default=0,
                    help="Playwright slow_mo in milliseconds")
    ap.add_argument("--samples-file",
                    default="docs/test-data/narration_samples.json",
                    help="Path to narration samples JSON (per "
                         "docs/test-packs/NARRATION_SAMPLES_AUTHORING_SPEC.md). "
                         "Default: docs/test-data/narration_samples.json")
    ap.add_argument("--narration-sizes",
                    default="clean,messy,emotional,fragmented",
                    help="Comma-separated sample sizes to run from the "
                         "samples file (default: all four)")
    ap.add_argument("--narration-only", action="store_true",
                    help="Run ONLY the narration tests (skip TEST-01..TEST-12)")
    args = ap.parse_args()

    repo_root = Path.cwd()
    out_arg = Path(args.output)
    if not out_arg.is_absolute():
        out_arg = repo_root / out_arg

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = out_arg.stem
    out_dir = out_arg.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}_{timestamp}.json"
    console_path = out_dir / f"{stem}_{timestamp}.console.txt"
    screenshots_dir = out_dir / f"{stem}_{timestamp}.screenshots"
    downloads_dir = out_dir / f"{stem}_{timestamp}.downloads"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    test_filter = [s.strip() for s in args.only.split(",") if s.strip()] or None

    # Load narration samples file if present. Failure is non-fatal —
    # the harness still runs the static TEST suite without narration.
    narration_specs: List[Dict[str, Any]] = []
    samples_path = Path(args.samples_file)
    if not samples_path.is_absolute():
        samples_path = repo_root / samples_path
    if samples_path.exists():
        try:
            data = json.loads(samples_path.read_text())
            if isinstance(data, list):
                narration_specs = [d for d in data if isinstance(d, dict)]
        except Exception as e:
            print(f"  [warn] could not load samples file {samples_path}: {e}",
                  file=sys.stderr)
    narration_sizes = [s.strip() for s in args.narration_sizes.split(",") if s.strip()]

    print("WO-PARENT-READINESS-HARNESS-01")
    print(f"  base_url:  {args.base_url}")
    print(f"  api:       {args.api}")
    print(f"  output:    {json_path}")
    print(f"  console:   {console_path}")
    print(f"  filter:    {test_filter or '(all)'}")
    print(f"  samples:   {samples_path if narration_specs else '(none)'}")
    if narration_specs:
        print(f"  narrators: {len(narration_specs)} × sizes "
              f"{narration_sizes} = {len(narration_specs) * len(narration_sizes)} pairs")
    print(f"  narration_only: {args.narration_only}")
    print()

    report = HarnessReport(
        started_at=dt.datetime.now().isoformat(),
        base_url=args.base_url,
        api=args.api,
        test_pack=args.test_pack,
        narration_only=args.narration_only,
    )

    with sync_playwright() as pw:
        # WO-HARNESS-V4-VISIBILITY-01 (2026-05-05): --start-maximized
        # forces the Chromium window to open at full screen size; combined
        # with --window-position=0,0 the window is guaranteed visible at
        # screen origin. Without these, Playwright on WSL/Windows can
        # open the window minimized or off-screen, and no_viewport=True
        # below lets the page render at the full window size so the
        # operator can see and click manually.
        browser: Browser = pw.chromium.launch(
            headless=args.headless,
            slow_mo=args.slow_mo_ms,
            args=["--start-maximized", "--window-position=0,0"],
        )
        context: BrowserContext = browser.new_context(
            accept_downloads=True,
            no_viewport=True,
        )
        page: Page = context.new_page()

        console = ConsoleCollector(page)
        ui = UI(page, console, screenshots_dir, downloads_dir)
        dblock = DbLockCounter(repo_root)

        # ── Phase 1 boot acceptance ──
        try:
            ui.boot(args.base_url)
            ui.ensure_operator_tab()
            ui.ensure_life_story_posture()
            ui.ready_for_session()
        except Exception as e:
            print(f"FATAL: boot phase failed: {e}", file=sys.stderr)
            report.overall = "RED"
            report.hard_stops.append("Boot failed before tests could run.")
            report.finished_at = dt.datetime.now().isoformat()
            write_report(report, json_path, console_path, console.entries)
            browser.close()
            return 2

        # ── Run tests ──
        harness = Harness(ui, console, dblock)
        harness.report = report
        harness.run_all(
            test_filter=test_filter,
            stop_on_red=args.stop_on_red,
            narration_specs=narration_specs,
            narration_sizes=narration_sizes,
            narration_only=args.narration_only,
        )

        report.finished_at = dt.datetime.now().isoformat()
        write_report(report, json_path, console_path, console.entries)

        try:
            browser.close()
        except Exception:
            pass

    # ── Print console-style summary to stdout ──
    print()
    print(console_path.read_text())

    return 0 if report.overall in ("GREEN", "AMBER") else 1


if __name__ == "__main__":
    sys.exit(main())
