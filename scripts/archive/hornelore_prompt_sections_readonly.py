#!/usr/bin/env python3
"""Hornelore per-block prompt measurement — READ ONLY.

Successor to `hornelore_prompt_measure_readonly.py`. That instrument
established the totals: every narrator, every condition, over the 8,192
window, with 944-1,939 real tokens cut off the FRONT of every turn. It
did not say WHERE the ~5,100 tokens of runtime growth live, and it did
not say WHICH instruction the front-cut reaches.

This one answers both, in real tokens.

WHY THIS EXISTS AND NOT A PATCH
-------------------------------
The Phase 4 outage happened because a budgeter was calibrated on
synthetic fixtures whose largest system message was a few hundred
tokens, against a production floor of 9,100. The architectural study
then repeated the mistake in miniature: it claimed the front-cut spares
the ACUTE SAFETY RULE, on the strength of dividing a character count by
four. Both claims were guesses wearing the clothes of measurements.

So: no character estimates anywhere in this instrument. Every number is
`len(tokenizer.encode(...))` against the same Llama-3.1-8B tokenizer the
stack serves with.

WHAT IT WILL NOT DO
-------------------
  * load the model, call generate(), or touch CUDA;
  * write to the family database (source opened `mode=ro`; the composer
    is pointed at a disposable /tmp copy, because compose_system_prompt
    calls ensure_session() while building);
  * modify .env, the real DATA_DIR, or any other process. It DOES make
    two process-local env writes and says so in the report -- DATA_DIR
    is repointed at the disposable copy, and .env values are
    setdefault-ed so the composer sees the stack's configuration;
  * emit narrator prose, family facts, or prompt text. Counts, section
    ids, marker positions, hashes and configuration only.

STANDALONE VS CUMULATIVE, AND WHY BOTH
--------------------------------------
Tokenizer counts are NOT additive across a join: `encode(a) + encode(b)`
is frequently not `encode(a + b)`, because merges happen across the
boundary. Reporting only standalone sizes would let a redesign budget
sections that do not add up in production. Reporting only cumulative
sizes would hide which section is fat. So both are reported, plus the
drift between them.

Usage:
    .venv/bin/python scripts/archive/hornelore_prompt_sections_readonly.py \\
        --output /mnt/c/Users/chris/Downloads/hornelore_prompt_sections.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASELINE = "66d51c9"

# The four narrators, by id. Names are carried only so the report is
# readable by a human; no other narrator text enters the output.
PERSON_IDS = {
    "Christopher Todd Horne": "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
    "Janice": "93479171-0b97-4072-bcf0-d44c7f9078ba",
    "Kent": "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
    "Melanie Zollner": "d56900b5-3dda-4f44-b419-4891e1683007",
}

# ── section anchors ──────────────────────────────────────────────────
# Located in the PRODUCED string rather than reconstructed from the
# builders, so this instrument measures what compose_system_prompt
# actually emitted and cannot drift from it. Anything between two
# anchors that no anchor claims is reported as `unattributed` -- an
# honest gap is more useful than a confident mis-attribution.
#
# Order matters: anchors must appear in this order, and any that appears
# out of order is reported rather than silently reordered.
SECTION_ANCHORS: List[Tuple[str, str]] = [
    ("default_core", r"^You are Lorevox \(\"Lori\"\)"),
    ("ui_base_or_profile_json", r"^PROFILE_JSON: "),
    ("rag_oral_history", r"^\[ORAL_HISTORY_GUIDELINES\]"),
    ("rag_golden_mock", r"^\[GOLDEN_MOCK\]"),
    ("known_identity_facts", r"^KNOWN IDENTITY FACTS:"),
    ("identity_grounding_rules", r"^IDENTITY GROUNDING RULES:"),
    ("english_first_rule", r"^\[ENGLISH_FIRST_RULE\]"),
    ("factual_chain_directive", r"^\[FACTUAL_CHAIN_DIRECTIVE\]"),
    ("lori_runtime_directives", r"^LORI_RUNTIME:"),
    ("conversation_memory", r"^CONVERSATION MEMORY"),
]

# Markers INSIDE default_core. The front-cut question is which of these
# survives, so each needs a real-token offset, not a character one.
CORE_MARKERS: List[Tuple[str, str]] = [
    ("core_start", "You are Lorevox"),
    ("identity_name_origin", "'Lore' means stories and oral tradition"),
    ("purpose_life_archive", "help people build a Life Archive"),
    ("boundary_you_are_not", "You are NOT"),
    ("acute_safety_rule", "ACUTE SAFETY RULE"),
    ("crisis_number_988", "988"),
]

ENV_KEYS_REPORTED = [
    "MODEL_PATH", "MAX_CONTEXT_WINDOW",
    "STT_MODEL", "STT_GPU", "STT_DEVICE", "STT_COMPUTE",
    "LORI_TTS_ENGINE", "TTS_DEVICE", "TTS_GPU", "TTS_MODEL",
    "HORNELORE_EXTRACTION_BOUNDED", "HORNELORE_SPANTAG",
]


def git_value(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=root, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unavailable"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_env(root: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    f = root / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ── tokenizer helpers. No estimates anywhere. ────────────────────────
def n_tokens(tok: Any, text: str) -> int:
    if not text:
        return 0
    enc = tok(text, add_special_tokens=False)
    ids = enc["input_ids"] if isinstance(enc, dict) else enc.input_ids
    return len(ids)


def token_index_of_char(tok: Any, text: str, char_offset: int) -> int:
    """Real-token index at a character offset. Prefix encode, exact."""
    return n_tokens(tok, text[:char_offset])


def char_offset_of_token(tok: Any, text: str, token_index: int) -> int:
    """Inverse, by binary search over prefixes.

    Backend-agnostic on purpose: `return_offsets_mapping` exists only on
    fast tokenizers, and an instrument that silently degrades on a slow
    one would report a different answer than the stack experiences.
    """
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if n_tokens(tok, text[:mid]) < token_index:
            lo = mid + 1
        else:
            hi = mid
    return lo


def apply_template(tok: Any, messages: List[Dict[str, str]]) -> str:
    if hasattr(tok, "apply_chat_template"):
        return tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True)
    return "\n".join(f"{m['role'].upper()}:\n{m['content']}"
                     for m in messages) + "\nASSISTANT:\n"


# ── section splitting ────────────────────────────────────────────────
def locate_sections(system: str) -> List[Dict[str, Any]]:
    """Find each anchor's char span in the produced system string."""
    found: List[Tuple[int, str]] = []
    for sid, pattern in SECTION_ANCHORS:
        m = re.search(pattern, system, re.M)
        if m:
            found.append((m.start(), sid))
    found.sort()

    out: List[Dict[str, Any]] = []
    # Anything before the first anchor is unattributed head.
    if found and found[0][0] > 0:
        out.append({"section_id": "unattributed_head",
                    "char_start": 0, "char_end": found[0][0]})
    for i, (start, sid) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(system)
        out.append({"section_id": sid, "char_start": start, "char_end": end})
    if not found:
        out.append({"section_id": "unattributed_whole",
                    "char_start": 0, "char_end": len(system)})
    return out


def measure_sections(tok: Any, system: str) -> Dict[str, Any]:
    spans = locate_sections(system)
    rows: List[Dict[str, Any]] = []
    standalone_sum = 0
    for sp in spans:
        text = system[sp["char_start"]:sp["char_end"]]
        standalone = n_tokens(tok, text)
        cumulative = token_index_of_char(tok, system, sp["char_end"])
        standalone_sum += standalone
        rows.append({
            "section_id": sp["section_id"],
            "chars": len(text),
            "standalone_tokens": standalone,
            "cumulative_tokens_after": cumulative,
            "token_start": token_index_of_char(tok, system, sp["char_start"]),
        })
    total = n_tokens(tok, system)
    return {
        "sections": rows,
        "system_total_tokens": total,
        "sum_of_standalone_tokens": standalone_sum,
        # The whole reason both are reported. A non-zero drift means a
        # redesign that budgets sections independently will be wrong by
        # this much.
        "additivity_drift_tokens": standalone_sum - total,
    }


def measure_core_markers(tok: Any, system: str, final_prompt: str,
                         window: int) -> Dict[str, Any]:
    """Real-token offsets of the markers inside DEFAULT_CORE, and which
    one is the first to survive the current front-cut."""
    final_total = n_tokens(tok, final_prompt)
    drop = max(0, final_total - window)

    markers: List[Dict[str, Any]] = []
    for name, needle in CORE_MARKERS:
        c = final_prompt.find(needle)
        markers.append({
            "marker": name,
            "present": c >= 0,
            "char_offset_in_final": c if c >= 0 else None,
            "token_offset_in_final": (token_index_of_char(tok, final_prompt, c)
                                      if c >= 0 else None),
        })

    survivor: Optional[str] = None
    first_surviving_char = None
    if drop > 0:
        first_surviving_char = char_offset_of_token(tok, final_prompt, drop)
        # Which named marker most recently preceded the surviving point.
        preceding = [m for m in markers
                     if m["char_offset_in_final"] is not None
                     and m["char_offset_in_final"] <= first_surviving_char]
        survivor = preceding[-1]["marker"] if preceding else "before_first_marker"

    cut_reaches = {
        m["marker"]: (bool(drop) and m["token_offset_in_final"] is not None
                      and m["token_offset_in_final"] < drop)
        for m in markers
    }

    return {
        "final_total_tokens": final_total,
        "window": window,
        "tokens_dropped_from_front": drop,
        "first_surviving_char_offset": first_surviving_char,
        "section_or_marker_containing_first_surviving_token": survivor,
        "markers": markers,
        "front_cut_removes_marker": cut_reaches,
    }


# ── scenarios ────────────────────────────────────────────────────────
def base_runtime(person: Dict[str, Any], seed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "current_pass": "pass2a", "current_era": None, "current_mode": "open",
        "active_trip_id": None, "active_trip_stop_id": None,
        "active_photo_link_id": None, "travels_shelf_open": False,
        "trip_style": None, "affect_state": "neutral", "affect_confidence": 0,
        "cognitive_mode": "open", "fatigue_score": 0, "paired": False,
        "paired_speaker": None, "visual_signals": None,
        "assistant_role": "interviewer", "session_style": "clear_direct",
        "identity_complete": True, "identity_phase": "complete",
        "effective_pass": "pass2a",
        "speaker_name": (person.get("display_name") or "").split()[0]
        if person.get("display_name") else "",
        "dob": person.get("date_of_birth") or "",
        "pob": person.get("place_of_birth") or "",
        "profile_seed": seed, "media_count": 0,
        "person_id": person.get("id"), "conversation_state": "answering",
        "cognitive_support_mode": False, "chronology_context": None,
    }


def scenarios(base: Dict[str, Any], history: List[Dict[str, str]]):
    def rt(**kw):
        r = json.loads(json.dumps(base))
        r.update(kw)
        return r
    chron = {"visible": True, "focus_year": None, "focus_era": "building_years",
             "personal_items": [], "world_items": [
                 {"label": "World Wide Web opens to broad public use",
                  "year": 1993, "source": "historical_json"}],
             "ghost_items": []}
    return [
        # plain_hi is the REQUIRED baseline: smallest possible narrator
        # turn, so anything over the window is the system's own doing.
        ("plain_hi", rt(), [], "hi"),
        ("building_years", rt(current_era="building_years",
                              chronology_context=chron), [], "Tell me about those years."),
        ("active_bismarck_trip", rt(active_trip_id="e4a7a5aa-82e0-4d20-b8df-b8996f37ffd7",
                                    travels_shelf_open=True), [],
         "I want to continue with the Bismarck Trip."),
        ("recent_history", rt(), history, "What happened next?"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/mnt/c/Users/chris/hornelore")
    ap.add_argument("--db", default="")
    ap.add_argument("--window", type=int, default=8192)
    ap.add_argument("--reserve", type=int, default=512)
    ap.add_argument("--output", default="")
    ap.add_argument("--allow-nonbaseline", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    head_short = git_value(root, "rev-parse", "--short", "HEAD")
    porcelain = [x for x in git_value(root, "status", "--porcelain").splitlines()
                 if x.strip()]

    # Two things cannot change what compose_system_prompt produces: a
    # markdown file under docs/, and THIS FILE. The first cut of this
    # guard tolerated only the former and therefore refused to run
    # because of its own presence -- a guard that blocks its own
    # instrument is not strict, it is broken.
    #
    # Deliberately the exact path, not all of scripts/: a different
    # untracked script could import into the composer's path and must
    # still block.
    _self = "?? " + str(Path(__file__).resolve().relative_to(root)).replace("\\", "/")
    tolerated = [x for x in porcelain
                 if (x.startswith("?? docs/") and x.endswith(".md"))
                 or x.strip() == _self]
    blocking = [x for x in porcelain if x not in tolerated]

    if not args.allow_nonbaseline:
        problems = []
        if not head_short.startswith(BASELINE):
            problems.append(f"HEAD is {head_short}, expected {BASELINE}")
        if blocking:
            problems.append(f"working tree has {len(blocking)} blocking "
                            f"entries: {blocking[:5]}")
        if problems:
            raise SystemExit("REFUSED: " + "; ".join(problems))

    env = read_env(root)
    for k, v in env.items():
        os.environ.setdefault(k, v)

    src_db = Path(args.db) if args.db else Path(
        env.get("DATA_DIR", "/mnt/c/hornelore_data")) / "db" / "hornelore.sqlite3"
    if not src_db.exists():
        raise SystemExit(f"REFUSED: database not found at {src_db}")

    tmp = Path(tempfile.mkdtemp(prefix="hornelore_sections_"))
    copy_db = tmp / "data" / "db" / "hornelore.sqlite3"
    copy_db.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    d = sqlite3.connect(str(copy_db))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    os.environ["DATA_DIR"] = str(tmp / "data")

    sys.path.insert(0, str(root / "server" / "code"))
    from api import prompt_composer as pc          # noqa: E402
    from api import db as _db                      # noqa: E402
    _db.DB_PATH = copy_db

    model_src = (env.get("MODEL_PATH") or env.get("MODEL_ID") or "").strip()
    if not model_src:
        raise SystemExit("REFUSED: MODEL_PATH is not set in .env")
    from transformers import AutoTokenizer         # noqa: E402
    tok = AutoTokenizer.from_pretrained(
        model_src, trust_remote_code=True, local_files_only=True,
        cache_dir=(env.get("HF_HOME") or None))

    con = sqlite3.connect(str(copy_db))
    con.row_factory = sqlite3.Row

    out: Dict[str, Any] = {
        "instrument": "hornelore_prompt_sections_readonly_v1",
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": {"head_short": head_short,
                 "branch": git_value(root, "branch", "--show-current"),
                 "porcelain_blocking": len(blocking),
                 "porcelain_tolerated_docs": tolerated},
        "safety": {
            "source_db_opened_read_only": True,
            "composer_db_is_disposable_copy": True,
            "composer_db": str(copy_db),
            "model_loaded": False, "generation_called": False,
            "cuda_used": False,
            # HONEST: two process-local environment writes DO happen, and
            # claiming otherwise would be the same kind of unchecked
            # assertion this instrument exists to replace.
            #   * DATA_DIR is repointed at the disposable copy, because
            #     compose_system_prompt calls ensure_session() and would
            #     otherwise write to the family database;
            #   * .env values are setdefault-ed so the composer sees the
            #     same configuration the stack does.
            # Neither touches the .env file, the real DATA_DIR, or any
            # other process.
            "process_env_writes": ["DATA_DIR (repointed to the copy)",
                                   ".env values via setdefault"],
            "env_file_modified": False,
            "real_data_dir_modified": False,
            "report_contains_prompt_or_narrator_text": False,
            "all_token_counts_from_real_tokenizer": True,
            "character_estimates_used": False,
        },
        "tokenizer": {"model_source": model_src,
                      "class": tok.__class__.__name__,
                      "chat_template_present": bool(getattr(tok, "chat_template", None))},
        "budget": {"window_tokens": args.window,
                   "output_reserve_tokens": args.reserve,
                   "prompt_ceiling_with_reserve": args.window - args.reserve},
        # Reported, never modified.
        # Read from the .env FILE, so these are the configured
        # values regardless of what this process set locally.
        "environment_as_configured": {k: env.get(k, "(unset)")
                                      for k in ENV_KEYS_REPORTED},
        "narrators": [],
    }

    for name, pid in PERSON_IDS.items():
        row = con.execute("SELECT * FROM people WHERE id=?", (pid,)).fetchone()
        person = dict(row) if row else {"id": pid, "display_name": name}
        person.setdefault("id", pid)
        try:
            seed = pc._build_profile_seed(pid) or {}
        except Exception:
            seed = {}
        base = base_runtime(person, seed)
        ui_system = "You are Lori.\n\nPROFILE_JSON: " + json.dumps(
            {"person_id": pid, "display_name": person.get("display_name"),
             "date_of_birth": person.get("date_of_birth"),
             "place_of_birth": person.get("place_of_birth"),
             "profile_seed": seed}, ensure_ascii=False, separators=(",", ":"))

        nrow: Dict[str, Any] = {"person_id": pid, "display_name": name,
                                "profile_seed_populated_fields":
                                    sum(1 for v in seed.values()
                                        if v not in (None, "", [], {})),
                                "conditions": []}

        for cname, runtime, hist, user_text in scenarios(base, []):
            system = pc.compose_system_prompt(
                f"measure-sections-{cname}-{pid}", ui_system=ui_system,
                user_text=user_text, runtime71=runtime)
            msgs = ([{"role": "system", "content": system}] + hist
                    + [{"role": "user", "content": user_text}])
            final_prompt = apply_template(tok, msgs)

            sec = measure_sections(tok, system)
            core = measure_core_markers(tok, system, final_prompt, args.window)
            final_total = core["final_total_tokens"]

            nrow["conditions"].append({
                "condition": cname,
                "history_message_count": len(hist),
                "current_turn_tokens": n_tokens(tok, user_text),
                "chat_template_overhead_tokens":
                    final_total - n_tokens(tok, system) - n_tokens(tok, user_text),
                "system_total_tokens": sec["system_total_tokens"],
                "sum_of_standalone_tokens": sec["sum_of_standalone_tokens"],
                "additivity_drift_tokens": sec["additivity_drift_tokens"],
                "final_after_chat_template_tokens": final_total,
                "headroom_vs_window": args.window - final_total,
                "headroom_after_output_reserve":
                    (args.window - args.reserve) - final_total,
                "fits_window": final_total <= args.window,
                "sections": sec["sections"],
                "front_cut": core,
                "hashes": {"system_sha256": sha256_text(system),
                           "final_sha256": sha256_text(final_prompt)},
            })
        out["narrators"].append(nrow)

    con.close()

    # ── console summary ──────────────────────────────────────────────
    print("=" * 78)
    print("Hornelore per-block prompt measurement — read only")
    print("=" * 78)
    print(f"HEAD {head_short}  blocking-dirty={len(blocking)}  "
          f"tolerated-docs={len(tolerated)}")
    print(f"tokenizer {tok.__class__.__name__}  model loaded: NO  CUDA: NO")
    print()
    print("environment as configured (NOT modified):")
    for k in ENV_KEYS_REPORTED:
        print(f"  {k:32} {env.get(k, '(unset)')}")
    print()
    for nrow in out["narrators"]:
        print(f"{nrow['display_name']}")
        for c in nrow["conditions"]:
            print(f"  {c['condition']:<22} final={c['final_after_chat_template_tokens']:>6} "
                  f"headroom={c['headroom_vs_window']:>6} "
                  f"drift={c['additivity_drift_tokens']:>4} "
                  f"cut={c['front_cut']['tokens_dropped_from_front']:>5} "
                  f"first_survivor={c['front_cut']['section_or_marker_containing_first_surviving_token']}")
            if c["condition"] == "plain_hi":
                for s in c["sections"]:
                    print(f"      {s['section_id']:<28} standalone={s['standalone_tokens']:>6} "
                          f"cumulative={s['cumulative_tokens_after']:>6}")
                for m, removed in c["front_cut"]["front_cut_removes_marker"].items():
                    print(f"      marker {m:<24} removed_by_front_cut={removed}")
        print()

    if args.output:
        Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"report: {args.output}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
