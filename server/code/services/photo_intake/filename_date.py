"""Filename-date guessing — WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Ph1.

Pure stdlib, no PIL, no I/O. A date parsed from a FILENAME is a LOW-
CONFIDENCE guess: cameras rename, messengers re-stamp, exports mangle.
It is stored in photos.taken_at_filename_guess for operator review and
NEVER auto-fills the canonical date_value.

Recognized shapes (all validated as real calendar dates, 1900-2100):
  PXL_20260514_123456.jpg      (Pixel)
  IMG_20260514_123456.jpg      (Android/others)
  IMG-20260514-WA0001.jpg      (WhatsApp)
  20260514_123456.jpg          (Samsung)
  Screenshot_20260514-...      (screenshots)
  2026-05-14 ... / 2026_05_14  (dashed/underscored)
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, Optional

_COMPACT_RX = re.compile(r"(?:^|[^0-9])((?:19|20)\d{2})(\d{2})(\d{2})(?:[^0-9]|$)")
_DASHED_RX = re.compile(r"(?:^|[^0-9])((?:19|20)\d{2})[-_.]([01]\d)[-_.]([0-3]\d)(?:[^0-9]|$)")


def parse_filename_date(filename: Optional[str]) -> Optional[str]:
    """Return an ISO date (YYYY-MM-DD) guessed from the filename, or None.
    Conservative: the digits must form a real calendar date."""
    name = str(filename or "")
    if not name:
        return None
    for rx in (_COMPACT_RX, _DASHED_RX):
        m = rx.search(name)
        if not m:
            continue
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat()
        except ValueError:
            continue
    return None


def derive_date_fields(
    exif_captured_at: Optional[str],
    original_filename: Optional[str],
    suspect: bool = False,
) -> Dict[str, Any]:
    """Ph1 date-review derivation used by the intake pipeline.

    - EXIF date present (and not a suspect scan date) → source 'exif',
      date_value = EXIF date.
    - Otherwise a filename guess is source 'filename_guess' but date_value
      stays None (LOW CONFIDENCE — operator confirms before it becomes
      canonical).
    - Nothing at all → source 'missing' ("No embedded EXIF found").
    """
    guess = parse_filename_date(original_filename)
    if exif_captured_at and not suspect:
        return {"date_value": exif_captured_at, "date_source": "exif",
                "taken_at_filename_guess": guess}
    if guess:
        return {"date_value": None, "date_source": "filename_guess",
                "taken_at_filename_guess": guess}
    return {"date_value": None, "date_source": "missing",
            "taken_at_filename_guess": None}


__all__ = ["parse_filename_date", "derive_date_fields"]
