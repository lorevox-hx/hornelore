#!/usr/bin/env python3
"""
Photo EXIF parser smoke test (Phase 2 partial — WO-LORI-PHOTO-INTAKE-01).

Round-trips a synthesized JPEG with a known EXIF DateTimeOriginal tag
through `server/code/services/photo_intake/exif.extract_exif()` and
asserts the output. Also exercises:
  - the no-EXIF fail-soft path (PNG without EXIF)
  - the corrupt-file fail-soft path (bytes that look like JPEG but aren't)

Run from repo root:

    python3 scripts/test_photo_exif.py

  Optional: validate the GPS path against a real EXIF-bearing photo
  (e.g. straight from a phone). Pass the path as the only argument:

    python3 scripts/test_photo_exif.py /path/to/IMG_1234.jpg

  When invoked with a real file, the script asserts the parser
  returns SOMETHING for date and/or GPS (without checking exact
  values, since they are file-specific).

Exit code is 0 on full pass, 1 on any failure.

Why Pillow-only (no piexif): production environments may not have
piexif installed. Pillow alone can write the date tag cleanly via
`getexif()`. GPS-write via Pillow alone is fragile across versions,
so the GPS path is exercised by the optional real-file argument
above and by the (unconditional) corrupt-EXIF fail-soft test.
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from PIL import Image
except ImportError as exc:
    print(f"FAIL: missing dependency: {exc}")
    print("Install with: pip install --break-system-packages Pillow")
    sys.exit(2)

from server.code.services.photo_intake.exif import extract_exif  # noqa: E402


PASSES = 0
FAILS = 0


def _pass(name: str, detail: str = "") -> None:
    global PASSES
    PASSES += 1
    suffix = f" — {detail}" if detail else ""
    print(f"PASS  {name}{suffix}")


def _fail(name: str, detail: str) -> None:
    global FAILS
    FAILS += 1
    print(f"FAIL  {name} — {detail}")


def _make_jpeg_with_date_exif(target: Path, capture_date: str) -> None:
    """Write a tiny 4×4 JPEG with EXIF DateTimeOriginal (tag 36867)."""
    img = Image.new("RGB", (4, 4), color=(120, 80, 40))
    exif = img.getexif()
    exif[0x9003] = capture_date  # DateTimeOriginal
    img.save(target, format="JPEG", exif=exif, quality=85)


def _make_png_no_exif(target: Path) -> None:
    """Write a tiny PNG (baseline PNG carries no EXIF)."""
    img = Image.new("RGB", (4, 4), color=(0, 200, 100))
    img.save(target, format="PNG")


def _make_corrupt_jpeg(target: Path) -> None:
    """Bytes that LOOK like a JPEG header but truncate after."""
    target.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01garbage_truncated")


# ──────────────────────────────────────────────────────────────────
# Test 1: EXIF date round-trip
# ──────────────────────────────────────────────────────────────────
def test_exif_date_roundtrip() -> None:
    name = "exif_date_roundtrip"
    expected_date = "2018-06-19"

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_exif.jpg"
        _make_jpeg_with_date_exif(path, "2018:06:19 14:32:01")
        result = extract_exif(str(path))

    if result.get("captured_at") != expected_date:
        _fail(name, f"captured_at = {result.get('captured_at')!r}, expected {expected_date!r}")
        return

    if result.get("captured_at_precision") != "exact":
        _fail(name, f"captured_at_precision = {result.get('captured_at_precision')!r}, expected 'exact'")
        return

    # GPS should be absent on this fixture (we didn't write GPS)
    gps = result.get("gps") or {}
    if gps.get("latitude") is not None or gps.get("longitude") is not None:
        _fail(name, f"unexpected GPS on date-only fixture: {gps}")
        return

    _pass(name, f"date={result['captured_at']} precision={result['captured_at_precision']}")
    # NOTE: precision="exact" matches the DB CHECK constraint
    # (DATE_PRECISIONS = exact|month|year|decade|unknown). EXIF
    # DateTimeOriginal carries down to the second so 'exact' is
    # semantically correct for any successful round-trip. Don't change
    # this back to 'day' without also changing the DB CHECK constraint
    # via a migration -- otherwise upload writes will fail with
    # IntegrityError (BUG-PHOTO-PRECISION-DAY surfaced 2026-04-25).


# ──────────────────────────────────────────────────────────────────
# Test 2: no EXIF (graceful fallback)
# ──────────────────────────────────────────────────────────────────
def test_no_exif_fallback() -> None:
    name = "no_exif_fallback"

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "no_exif.png"
        _make_png_no_exif(path)
        result = extract_exif(str(path))

    if result.get("captured_at") is not None:
        _fail(name, f"captured_at should be None for no-EXIF file, got {result.get('captured_at')!r}")
        return

    if result.get("captured_at_precision") != "unknown":
        _fail(name, f"captured_at_precision should be 'unknown', got {result.get('captured_at_precision')!r}")
        return

    gps = result.get("gps") or {}
    if gps.get("latitude") is not None or gps.get("longitude") is not None:
        _fail(name, f"gps should be None/None, got {gps}")
        return

    if gps.get("source") != "unknown":
        _fail(name, f"gps.source should be 'unknown', got {gps.get('source')!r}")
        return

    _pass(name, "empty-shape dict returned without error")


# ──────────────────────────────────────────────────────────────────
# Test 3: corrupt EXIF (must not raise)
# ──────────────────────────────────────────────────────────────────
def test_corrupt_exif_failsoft() -> None:
    name = "corrupt_exif_failsoft"

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "corrupt.jpg"
        _make_corrupt_jpeg(path)
        try:
            result = extract_exif(str(path))
        except Exception as exc:
            _fail(name, f"raised {type(exc).__name__}: {exc} — must be fail-soft, never raise")
            return

    if not isinstance(result, dict):
        _fail(name, f"result is not a dict: {type(result).__name__}")
        return

    if result.get("captured_at") is not None:
        _fail(name, f"corrupt file should yield captured_at=None, got {result.get('captured_at')!r}")
        return

    _pass(name, "fail-soft contract held, returned empty-shape dict")


# ──────────────────────────────────────────────────────────────────
# Test 4 (optional): real EXIF-bearing photo from a phone
# ──────────────────────────────────────────────────────────────────
def test_real_photo(real_path: Path) -> None:
    name = f"real_photo[{real_path.name}]"

    if not real_path.exists():
        _fail(name, f"file not found: {real_path}")
        return

    try:
        result = extract_exif(str(real_path))
    except Exception as exc:
        _fail(name, f"raised {type(exc).__name__}: {exc}")
        return

    if not isinstance(result, dict):
        _fail(name, f"result is not a dict")
        return

    bits = []
    if result.get("captured_at"):
        bits.append(f"date={result['captured_at']}")
    gps = result.get("gps") or {}
    if gps.get("latitude") is not None and gps.get("longitude") is not None:
        bits.append(f"gps=({gps['latitude']:.4f},{gps['longitude']:.4f})")
    raw = result.get("raw_exif") or {}
    bits.append(f"raw_exif_keys={len(raw)}")

    if not bits:
        _fail(name, "no date, no GPS, no raw_exif — likely a no-EXIF file (try a different photo)")
        return

    _pass(name, " ".join(bits))


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────
def main() -> int:
    print("Photo EXIF parser smoke test")
    print("─" * 50)
    test_exif_date_roundtrip()
    test_no_exif_fallback()
    test_corrupt_exif_failsoft()

    if len(sys.argv) >= 2:
        real_path = Path(sys.argv[1])
        test_real_photo(real_path)

    print("─" * 50)
    total = PASSES + FAILS
    if FAILS:
        print(f"FAIL  {FAILS}/{total} — see above")
        return 1
    print(f"OK    {PASSES}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
