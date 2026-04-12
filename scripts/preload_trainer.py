#!/usr/bin/env python3
"""
WO-13 Phase A — Preload a trainer narrator via the existing UI helper.

Reuses the `import_kent_james_horne.py` pattern: drives a headless Chromium
with Playwright, waits for the UI's `lv80PreloadNarrator` function to exist,
and calls it directly with a template JSON. This bypasses the onboarding
flow entirely — no clicks, no resume prompts, no user typing.

Usage:
    python3 scripts/preload_trainer.py william-shatner
    python3 scripts/preload_trainer.py dolly-parton
    python3 scripts/preload_trainer.py --all   # loads both trainers
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Standalone Hornelore repo layout (matches import_kent_james_horne.py).
REPO_DIR = Path("/mnt/c/Users/chris/hornelore")
UI_URL = "http://127.0.0.1:8082/ui/hornelore1.0.html"
HEADLESS = True  # no UI needed; script-only path

TRAINERS = ["william-shatner", "dolly-parton"]


def fail(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def resolve_template(slug: str) -> Path:
    """DATA_DIR/templates/{slug}.json first, then repo ui/templates/."""
    data_dir = os.environ.get("DATA_DIR", "/mnt/c/hornelore_data")
    data_tpl = Path(data_dir) / "templates" / f"{slug}.json"
    repo_tpl = REPO_DIR / "ui" / "templates" / f"{slug}.json"
    return data_tpl if data_tpl.exists() else repo_tpl


def preload_one(page, slug: str) -> dict:
    tpl_path = resolve_template(slug)
    if not tpl_path.exists():
        fail(f"Template not found: {tpl_path}")

    try:
        tpl = json.loads(tpl_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Failed to parse JSON template {tpl_path}: {exc}")

    narrator = (
        tpl.get("_narrator")
        or tpl.get("personal", {}).get("fullName")
        or slug
    )

    print(f"[preload_trainer] ---- {narrator} ({slug}) ----")
    print(f"[preload_trainer] Template: {tpl_path}")
    print(f"[preload_trainer] Trainer:  {tpl.get('_trainer')}  Style: {tpl.get('_trainerStyle')}")

    result = page.evaluate(
        """async (tpl) => {
            const out = await window.lv80PreloadNarrator(tpl);
            const pid =
              (typeof out === "string" ? out : null) ||
              (out && (out.person_id || out.pid || out.id || null));
            const qqKey = pid ? ("lorevox_qq_draft_" + pid) : null;
            const qqRaw = qqKey ? localStorage.getItem(qqKey) : null;
            return {
              out,
              pid,
              qqKey,
              hasQuestionnaire: !!qqRaw
            };
        }""",
        tpl,
    )

    pid = result.get("pid")
    if not pid:
        fail(f"Preload did not return a person id for {slug}. Raw: {result.get('out')}")

    print(f"[preload_trainer] Person ID: {pid}")
    print(f"[preload_trainer] Questionnaire stored: {result.get('hasQuestionnaire')}")
    return {"slug": slug, "narrator": narrator, "pid": pid, **result}


def main() -> None:
    ap = argparse.ArgumentParser(description="Preload a trainer narrator into Hornelore.")
    ap.add_argument("slug", nargs="?", help="Template slug, e.g. william-shatner")
    ap.add_argument("--all", action="store_true", help="Preload all known trainers")
    args = ap.parse_args()

    if not args.slug and not args.all:
        ap.error("Provide a slug or --all")

    slugs = TRAINERS if args.all else [args.slug]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()
        page.set_default_timeout(45000)

        try:
            print(f"[preload_trainer] Opening UI: {UI_URL}")
            page.goto(UI_URL, wait_until="domcontentloaded")

            page.wait_for_function(
                "() => typeof window.lv80PreloadNarrator === 'function'",
                timeout=45000,
            )

            page.wait_for_function(
                """async () => {
                    try {
                      const r = await fetch((window.API && window.API.PING) || 'http://localhost:8000/api/ping');
                      return !!r.ok;
                    } catch (_) { return false; }
                }""",
                timeout=45000,
            )

            results = []
            for slug in slugs:
                try:
                    results.append(preload_one(page, slug))
                except SystemExit:
                    raise
                except Exception as exc:
                    print(f"[preload_trainer] FAILED {slug}: {exc}", file=sys.stderr)
                    raise

            print("")
            print("[preload_trainer] Summary:")
            for r in results:
                print(f"  {r['slug']:<20} pid={r['pid']}  qq={r['hasQuestionnaire']}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
