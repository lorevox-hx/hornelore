"""Life Record dates — the bounded EDTF profile (Batch C-4B).

THE CONTRACT (C-4A, decided 2026-09-24; checkpoint "C-4"):

    {text, value, precision}
      text       the wording as entered, after ordinary trimming — never rewritten
      value      a value in Hornelore's bounded EDTF profile, or None when the
                 wording cannot be converted without inference
      precision  calendar granularity of the representation only:
                 day | month | year | unknown

    Approximation / uncertainty live in `value` only: `~` approximate, `?`
    uncertain, `%` both. Precision is the granularity of the representation,
    NOT a claim that the value is exact — `192X` and `1989~` are both `year`.

THE EXECUTABLE CONTRACT is the shared fixture corpus
tests/fixtures/life_record_dates_v1.json; the browser parser
(ui/js/questionnaire-v2-model.js `parseDateText`) must reproduce it exactly too.

Three outcomes from `parse(text)`:
    ("value", value, precision)   the whole text is a recognised form
    ("text", None, "unknown")     not recognised — kept as words only
    ("refuse", reason)            date-shaped but not a real date (or a
                                  reversed range): never silently downgraded

`check(obj, allow_interval)` is what the WRITER uses on a date object a write
changes: the supplied value and precision must equal the parse of its text.
Valid EDTF alone is not enough — {text: "1987", value: "1989"} is refused.

Legacy reading (dates stored before C-4 — `precision: "approximate" /
"uncertain"`, C-3's `{value: None, precision: "unknown"}` for "about 1989") is
the caller's business: the writer never re-validates a date a write does not
change, and `qualifiers()` still honours the legacy precision words.
"""
from __future__ import annotations

import calendar
import re
from typing import Any, Dict, Optional, Tuple

PRECISIONS = ("day", "month", "year", "unknown")
LEGACY_VAGUE_PRECISIONS = ("approximate", "uncertain")
YEAR_MIN, YEAR_MAX = 1000, 2999

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_RX = r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_APPROX_WORDS = ("approximately", "around", "about", "circa", "ca.", "c.")
_UNCERTAIN_WORDS = ("probably", "possibly", "perhaps", "maybe")

_REFUSE = object()


def _norm(text: str) -> str:
    """Matching form only — lower case, whitespace collapsed. Never stored."""
    return re.sub(r"\s+", " ", str(text).strip()).lower()


def _year_ok(y: int) -> bool:
    return YEAR_MIN <= y <= YEAR_MAX


def _single(s: str):
    """One UNQUALIFIED calendar date. Returns (edtf, precision, (y, m, d)),
    _REFUSE for a date-shaped string that is not a real date, or None."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not _year_ok(y):
            return None
        if not (1 <= mo <= 12) or not (1 <= d <= calendar.monthrange(y, mo)[1]):
            return _REFUSE
        return (f"{y:04d}-{mo:02d}-{d:02d}", "day", (y, mo, d))
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if not _year_ok(y):
            return None
        if not (1 <= mo <= 12):
            return _REFUSE
        return (f"{y:04d}-{mo:02d}", "month", (y, mo, None))
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(m.group(1))
        return (f"{y:04d}", "year", (y, None, None)) if _year_ok(y) else None
    m = (re.fullmatch(_MONTH_RX + r" (\d{1,2}),? (\d{4})", s)
         or re.fullmatch(r"(\d{1,2}) " + _MONTH_RX + r",? (\d{4})", s))
    if m:
        g = m.groups()
        if g[0].isdigit():
            d, mo, y = int(g[0]), _MONTHS[g[1]], int(g[2])
        else:
            mo, d, y = _MONTHS[g[0]], int(g[1]), int(g[2])
        if not _year_ok(y):
            return None
        if not (1 <= d <= calendar.monthrange(y, mo)[1]):
            return _REFUSE
        return (f"{y:04d}-{mo:02d}-{d:02d}", "day", (y, mo, d))
    m = re.fullmatch(_MONTH_RX + r",? (\d{4})", s)
    if m:
        mo, y = _MONTHS[m.group(1)], int(m.group(2))
        if not _year_ok(y):
            return None
        return (f"{y:04d}-{mo:02d}", "month", (y, mo, None))
    return None


def _qualified(s: str):
    """A single date with optional approximate / uncertain qualifiers."""
    approx = uncertain = False
    for w in _UNCERTAIN_WORDS:
        if s.startswith(w + " "):
            uncertain, s = True, s[len(w) + 1:]
            break
    for w in _APPROX_WORDS:
        if s.startswith(w + " "):
            approx, s = True, s[len(w) + 1:]
            break
    if s.endswith("%"):
        approx = uncertain = True
        s = s[:-1]
    elif s.endswith("~"):
        approx, s = True, s[:-1]
    elif s.endswith("?"):
        uncertain, s = True, s[:-1]
    s = s.strip()
    r = _single(s)
    if r is None or r is _REFUSE:
        return r
    mark = "%" if (approx and uncertain) else "~" if approx else "?" if uncertain else ""
    return (r[0] + mark, r[1], r[2])


def _decade(s: str):
    m = re.fullmatch(r"(?:the )?(\d{3})0(?:s|'s)", s)
    if not m:
        return None
    y = int(m.group(1)) * 10
    if not _year_ok(y) or y % 100 == 0:        # "1900s": decade or century — ambiguous
        return None
    return (f"{m.group(1)}X", "year")


def _earliest(p):
    y, m, d = p
    return (y, m or 1, d or 1)


def _latest(p):
    y, m, d = p
    return (y, m or 12, d or (calendar.monthrange(y, m)[1] if m else 31))


def _interval(s: str):
    """Closed, explicitly ongoing, or explicitly unknown-endpoint ranges of
    UNQUALIFIED single dates."""
    end_words = r"(?:present|now)"
    for pat in (r"(.+?) (?:to) " + end_words, r"(.+?) ?[–—-] ?present",
                r"(.+?) \((?:ongoing|still)\)", r"(.+?)/\.\."):
        m = re.fullmatch(pat, s)
        if m:
            a = _single(m.group(1).strip())
            if a is _REFUSE:
                return _REFUSE
            if a:
                return (f"{a[0]}/..", "unknown")
    m = re.fullmatch(r"(.+?) to (?:unknown|\?)", s)
    if m:
        a = _single(m.group(1).strip())
        if a is _REFUSE:
            return _REFUSE
        if a:
            return (f"{a[0]}/", "unknown")
    m = re.fullmatch(r"(?:unknown|\?) to (.+)", s)
    if m:
        b = _single(m.group(1).strip())
        if b is _REFUSE:
            return _REFUSE
        if b:
            return (f"/{b[0]}", "unknown")
    for pat in (r"(?:from )?(.+?) (?:to|through|thru) (.+)", r"(.+?) ?[–—] ?(.+)",
                r"(\d{4})-(\d{4})", r"([^/]+)/([^/]+)"):
        m = re.fullmatch(pat, s)
        if not m:
            continue
        a, b = _single(m.group(1).strip()), _single(m.group(2).strip())
        if a is _REFUSE or b is _REFUSE:
            return _REFUSE
        if not a or not b:
            continue
        if _earliest(a[2]) > _latest(b[2]):
            return _REFUSE                              # a reversed range
        return (f"{a[0]}/{b[0]}", a[1] if a[1] == b[1] else "unknown")
    return None


def parse(text: Any) -> Tuple:
    """("value", value, precision) | ("text", None, "unknown") | ("refuse", reason)."""
    if not isinstance(text, str) or not text.strip():
        return ("refuse", "a date needs its text, as said")
    s = _norm(text)
    for fn in (_interval, _qualified):
        r = fn(s)
        if r is _REFUSE:
            return ("refuse", f"{text.strip()!r} is not a real date — correct it, or write it in words")
        if r:
            return ("value", r[0], r[1])
    r = _decade(s)
    if r:
        return ("value", r[0], r[1])
    return ("text", None, "unknown")


def check(obj: Any, allow_interval: bool) -> Optional[str]:
    """None if `obj` is a date object that agrees with the contract; else why not.

    For a date a write CHANGES. The writer never calls this on a date the
    write carries unchanged — legacy dates pass through as they are."""
    if not isinstance(obj, dict):
        return "a date is {text, value, precision}"
    extra = set(obj) - {"text", "value", "precision"}
    if extra:
        return f"a date carries only text, value and precision (not {sorted(extra)})"
    r = parse(obj.get("text"))
    if r[0] == "refuse":
        return r[1]
    want_value, want_precision = r[1], r[2]
    if want_value and "/" in want_value and not allow_interval:
        return f"{obj['text']!r} is a range; a single date is expected here"
    if obj.get("precision") not in PRECISIONS:
        return (f"precision must be one of {', '.join(PRECISIONS)} "
                f"(approximation and uncertainty go in the value)")
    if obj.get("value") != want_value or obj.get("precision") != want_precision:
        return (f"{obj['text']!r} means value {want_value!r}, precision {want_precision!r} — "
                f"not {obj.get('value')!r}, {obj.get('precision')!r}")
    return None


def qualifiers(obj: Dict[str, Any]) -> Dict[str, Any]:
    """What a CONSUMER must read from a stored date — the new contract AND the
    legacy vocabulary. A consumer that reads `precision` and ignores the marks
    in `value` is wrong: `1989~` is year precision and still approximate."""
    v = str((obj or {}).get("value") or "")
    p = (obj or {}).get("precision")
    return {
        "approximate": v.endswith("~") or v.endswith("%") or p == "approximate",
        "uncertain": v.endswith("?") or v.endswith("%") or p == "uncertain",
        "unspecified_digits": "X" in v,
        "interval": "/" in v,
        "has_value": bool(v),
    }


def calendar_parts(value: str):
    """(year, month, day) of a SINGLE date value with marks removed, or None
    for an interval, an unspecified-digit value or no value."""
    v = str(value or "").rstrip("~?%")
    if not v or "/" in v or "X" in v:
        return None
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", v)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else None,
            int(m.group(3)) if m.group(3) else None)
