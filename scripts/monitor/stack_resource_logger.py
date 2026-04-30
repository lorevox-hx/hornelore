#!/usr/bin/env python3
"""WO-OPERATOR-RESOURCE-DASHBOARD-01 — standalone resource logger.

Run alongside the stack to write a JSONL row every `--interval` seconds.
Output goes to:

    .runtime/monitor/stack-resource-YYYYMMDD-HHMMSS.jsonl
    .runtime/monitor/latest.jsonl   (symlink/copy — pointer to current run)

Each row is a snapshot of CPU/RAM/disk/GPU/service-pings/file-freshness.
The Bug Panel dashboard reads `latest.jsonl` for sparkline history.

Run:
    cd /mnt/c/Users/chris/hornelore
    python scripts/monitor/stack_resource_logger.py --interval 5

With an eval marker (helps correlate failures after the fact):
    python scripts/monitor/stack_resource_logger.py --interval 5 --tag r5h-place-guard

Bounded run (smoke / acceptance test):
    python scripts/monitor/stack_resource_logger.py --interval 2 --duration 10 --tag smoke

This script imports from `server/code/api/services/stack_monitor.py`,
which is the same module the live router uses — so the logger sees
exactly what the dashboard sees.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Resolve repo root from this script's location: scripts/monitor/<this>.py
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent  # scripts/monitor/.. = scripts/.. = repo
_SERVER_CODE = _REPO_ROOT / "server" / "code"

# Add server/code/ to sys.path so `api.services.stack_monitor` imports cleanly.
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

try:
    from api.services import stack_monitor  # type: ignore
except ImportError as e:
    print(f"[stack-resource-logger] import failed: {e}", file=sys.stderr)
    print(f"[stack-resource-logger] sys.path[0]={sys.path[0]}", file=sys.stderr)
    sys.exit(2)

_OUT_DIR = _REPO_ROOT / ".runtime" / "monitor"
_LATEST_LINK = _OUT_DIR / "latest.jsonl"

_running = True


def _signal_handler(_signum, _frame):
    global _running
    _running = False


def _utc_stamp_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _build_row(tag: str | None) -> dict:
    """Compose a single JSONL row from the live collectors. Slim shape
    (not the full summary block) — sparklines need a few numbers, not
    the whole dashboard."""
    sys_block = stack_monitor.collect_system()
    gpu = stack_monitor.collect_gpu()
    services = stack_monitor.collect_services()
    archive = stack_monitor.collect_archive()
    eval_block = stack_monitor.collect_eval()
    log_scan = stack_monitor._scan_api_log()

    row = {
        "ts": stack_monitor._utc_now(),
        "tag": tag,
        "cpu_percent": sys_block.get("cpu_percent"),
        "memory_percent": sys_block.get("memory_percent"),
        "memory_used_gb": sys_block.get("memory_used_gb"),
        "disk_percent": sys_block.get("disk_percent"),
        "disk_free_gb": sys_block.get("disk_free_gb"),
        "gpu": {
            "status": gpu.get("status"),
            "vram_used_mb": gpu.get("vram_used_mb"),
            "vram_free_mb": gpu.get("vram_free_mb"),
            "util_percent": gpu.get("util_percent"),
            "temperature_c": gpu.get("temperature_c"),
        },
        "services": {
            "api_ping": (services.get("api") or {}).get("status") == "ok",
            "ui_ping": (services.get("ui") or {}).get("status") == "ok",
            "tts_ping": (services.get("tts") or {}).get("status") == "ok",
            "api_latency_ms": (services.get("api") or {}).get("latency_ms"),
        },
        "files": {
            "memory_archive_latest_age_sec": archive.get("latest_jsonl_age_sec")
            or archive.get("latest_txt_age_sec"),
            "audio_latest_age_sec": (eval_block.get("latest_report") or {}).get("age_sec"),
        },
        "eval": {
            "status": eval_block.get("status"),
            "tag": eval_block.get("tag"),
            "connection_refused_count": eval_block.get(
                "connection_refused_count_rolling"
            ),
        },
        "api_log": {
            "oom_count": log_scan.get("oom_count"),
            "connection_refused_count": log_scan.get("connection_refused_count"),
        },
    }
    return row


def _update_latest_pointer(target: Path) -> None:
    """Maintain `latest.jsonl` as a symlink (or copy on platforms that
    can't symlink, e.g., NTFS without privilege). The dashboard reads
    `latest.jsonl` so it doesn't have to know the timestamped name."""
    try:
        if _LATEST_LINK.exists() or _LATEST_LINK.is_symlink():
            _LATEST_LINK.unlink()
        try:
            _LATEST_LINK.symlink_to(target.name)  # relative — survives moves of _OUT_DIR
        except (OSError, NotImplementedError):
            # Fallback: copy on every rotation. Cheap because the file
            # is appended to in place — we copy after each row.
            import shutil
            shutil.copy2(target, _LATEST_LINK)
    except Exception as e:
        print(f"[stack-resource-logger] could not update latest pointer: {e}",
              file=sys.stderr)


def _copy_to_latest(target: Path) -> None:
    """Maintain `latest.jsonl` as a copy of `target` for platforms
    where symlinks aren't reliable (Windows/NTFS without privilege).
    Only used if the symlink path failed during initial setup."""
    try:
        import shutil
        shutil.copy2(target, _LATEST_LINK)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Live stack/resource logger — JSONL output for the dashboard."
    )
    ap.add_argument("--interval", type=float, default=5.0,
                    help="Seconds between samples (default 5.0)")
    ap.add_argument("--duration", type=float, default=None,
                    help="Stop after this many seconds (default: run until SIGINT/SIGTERM)")
    ap.add_argument("--tag", type=str, default=None,
                    help="Optional run tag (e.g., eval suffix). Stamped on every row.")
    ap.add_argument("--out-dir", type=str, default=None,
                    help=f"Override output dir (default {_OUT_DIR})")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else _OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"stack-resource-{_utc_stamp_filename()}.jsonl"

    print(f"[stack-resource-logger] writing to {target}")
    print(f"[stack-resource-logger] interval={args.interval}s duration={args.duration} tag={args.tag}")
    print(f"[stack-resource-logger] press Ctrl+C to stop")

    # Symlink-or-copy the latest pointer once up front; we'll re-copy on
    # platforms that don't support symlinks.
    use_symlink = True
    try:
        if (out_dir / "latest.jsonl").exists() or (out_dir / "latest.jsonl").is_symlink():
            (out_dir / "latest.jsonl").unlink()
        (out_dir / "latest.jsonl").symlink_to(target.name)
    except (OSError, NotImplementedError):
        use_symlink = False
        # First copy will happen after the first row is written.

    signal.signal(signal.SIGINT, _signal_handler)
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
    except (AttributeError, ValueError):
        # SIGTERM not available on Windows or in non-main threads.
        pass

    started = time.time()
    samples = 0
    with open(target, "a", encoding="utf-8") as f:
        while _running:
            try:
                row = _build_row(args.tag)
            except Exception as e:
                row = {"ts": stack_monitor._utc_now(), "_error": str(e)[:200]}
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

            if not use_symlink:
                _copy_to_latest(target)

            samples += 1
            if args.duration is not None and (time.time() - started) >= args.duration:
                break
            # Sleep in 0.1s chunks so SIGINT is responsive.
            slept = 0.0
            while _running and slept < args.interval:
                time.sleep(min(0.1, args.interval - slept))
                slept += 0.1

    print(f"[stack-resource-logger] stopped after {samples} samples; output: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
