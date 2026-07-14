"""WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1 — OCR provider interface.

Reads visible text from a LOCAL photo file (signs, menus, tickets,
museum labels) and returns a draft result. Pure provider layer: no DB,
no router imports, no network. The image path is handed only to a LOCAL
provider; nothing leaves the machine here.

Providers (HORNELORE_OCR_PROVIDER): off | tesseract | command
  * off       — feature not configured; returns ok=False (no fake text).
  * tesseract — local pytesseract (lazy import; if unavailable -> ok=False).
  * command   — HORNELORE_OCR_CMD receives the image path and returns
                JSON {"text": "...", "summary": "..."} on stdout.

Master gate HORNELORE_PHOTO_OCR must be truthy for the feature to run.
Nothing here fabricates results when a provider is missing.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Any, Dict

_TRUTHY = {"1", "true", "yes", "on"}
_OCR_TIMEOUT_SEC = 60
_SUMMARY_CHARS = 240


def ocr_enabled() -> bool:
    return os.getenv("HORNELORE_PHOTO_OCR", "0").strip().lower() in _TRUTHY


def ocr_provider() -> str:
    return (os.getenv("HORNELORE_OCR_PROVIDER", "off") or "off").strip().lower()


def _summarize(text: str) -> str:
    """A concise, single-line readable excerpt of the OCR text."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= _SUMMARY_CHARS:
        return collapsed
    return collapsed[:_SUMMARY_CHARS].rstrip() + "…"


def _result(ok: bool, engine: str, raw_text: str = "", summary: str = "",
            error: str = "") -> Dict[str, Any]:
    return {"ok": ok, "engine": engine, "raw_text": raw_text,
            "summary": summary, "error": error or None}


def ocr_langs() -> str:
    return (os.getenv("HORNELORE_OCR_LANGS", "eng") or "eng").strip() or "eng"


# LIVE-TEST FIX (2026-07-13): Tesseract's DEFAULT page-segmentation mode is
# tuned for scanned DOCUMENTS, and it fails badly on SCENE text (a museum sign
# on a building, a beer coaster on a table). Live evidence: the Augustiner
# coaster, which plainly reads "Augustiner Brau Munchen 1328", came back as
# "VAMI i all, N STIVA RTAS INIT fart 1404 MI", and the Munich fish photo's
# museum sign returned no_text_found — on FULL-RES 3072x4080 originals, so it
# was never a resolution problem.
#
# So: light preprocessing (honour EXIF rotation, grayscale, autocontrast) and
# try several page-segmentation modes, keeping the best result. PSM 11 =
# "sparse text: find as much text as possible in no particular order", which is
# the right mode for signs/labels. This is the cheap win; PaddleOCR remains the
# stronger scene-text path the provider interface was built to accept.
_DEFAULT_PSMS = ("11", "6", "3")   # sparse scene text -> single block -> auto

_WORDLIKE_RX = re.compile(r"\S+")


def ocr_psms():
    raw = (os.getenv("HORNELORE_OCR_PSM", "") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return _DEFAULT_PSMS


def ocr_max_dim() -> int:
    """Cap the long edge before OCR. LIVE (2026-07-13): three PSM passes over a
    full-res 3072x4080 phone photo took 7s (coaster) to 19s (dense menu) — far
    too slow for an operator clicking a button. Downscaling the long edge keeps
    sign/menu text well above tesseract's ~20px-per-character floor while
    cutting the pixel count several-fold. 0 disables the cap."""
    try:
        return int(os.getenv("HORNELORE_OCR_MAX_DIM", "2400"))
    except ValueError:
        return 2400


# A candidate this strong is certainly a real reading — stop trying more PSMs.
def ocr_early_exit_score() -> int:
    try:
        return int(os.getenv("HORNELORE_OCR_EARLY_EXIT", "1200"))
    except ValueError:
        return 1200


def _preprocess(img):
    """Honour camera rotation, cap size, grayscale, stretch contrast."""
    from PIL import Image, ImageOps  # type: ignore
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    cap = ocr_max_dim()
    try:
        if cap and max(img.size) > cap:
            ratio = cap / float(max(img.size))
            img = img.resize(
                (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                Image.LANCZOS)
    except Exception:
        pass
    try:
        img = img.convert("L")
        img = ImageOps.autocontrast(img)
    except Exception:
        pass
    return img


def _wordlike_score(text: str) -> int:
    """Rank OCR candidates by how much REAL-looking text they contain.
    Tesseract noise ('N STIVA RTAS') scores far lower than a true reading."""
    # Length-WEIGHTED: real words are long ("Augustiner", "Fischereimuseum"),
    # tesseract noise is short ("VAMI", "RTAS"). A flat char count scores the
    # garbage coaster reading exactly the same as the true one (both 25), so
    # square the token length to let genuine words dominate.
    score = 0
    for tok in _WORDLIKE_RX.findall(text or ""):
        if len(tok) < 3:
            continue
        alpha = sum(1 for c in tok if c.isalpha())
        if alpha >= 0.7 * len(tok):
            score += len(tok) * len(tok)
    return score


def ocr_min_ratio() -> float:
    """LIVE (2026-07-13): a photo of FOOD (no text at all) produced confident
    tesseract noise — '# : 9 #4 - s 4 \\ | | di i s k EJ s? ...' — which was
    stored as a draft row, so the panel offered "Lori will say: the OCR draft
    appears to read '# : 9 #4...'". Junk like that must never become evidence.

    A raw score cannot separate it: the noise scored 86 and a REAL short sign
    ("GRAND CAFE ORIENT MENU") scores 93. What DOES separate them is the
    proportion of word-like characters — noise is mostly symbols, digits and
    single letters (ratio 0.17) while every genuine reading measured 0.89-1.00.
    """
    try:
        return float(os.getenv("HORNELORE_OCR_MIN_RATIO", "0.40"))
    except ValueError:
        return 0.40


def _wordlike_ratio(text: str) -> float:
    """Share of characters living in real-looking words. See ocr_min_ratio()."""
    toks = _WORDLIKE_RX.findall(text or "")
    total = sum(len(t) for t in toks)
    if not total:
        return 0.0
    good = 0
    for tok in toks:
        if len(tok) < 3:
            continue
        alpha = sum(1 for c in tok if c.isalpha())
        if alpha >= 0.7 * len(tok):
            good += len(tok)
    return good / float(total)


def _run_tesseract(image_path: str) -> Dict[str, Any]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - env dependent
        return _result(False, "tesseract",
                       error="tesseract/pillow not installed: %s" % exc)
    try:
        img = _preprocess(Image.open(image_path))
    except Exception as exc:
        return _result(False, "tesseract", error="cannot open image: %s" % exc)

    best_text, best_score = "", -1
    last_error = ""
    min_ratio = ocr_min_ratio()
    for psm in ocr_psms():
        try:
            cand = pytesseract.image_to_string(
                img, lang=ocr_langs(), config="--psm %s" % psm)
        except Exception as exc:      # a bad PSM must not kill the whole run
            last_error = str(exc)
            continue
        cand = (cand or "").strip()
        if _wordlike_ratio(cand) < min_ratio:
            continue                  # tesseract noise, not a reading
        score = _wordlike_score(cand)
        if score > best_score:
            best_text, best_score = cand, score
        if best_score >= ocr_early_exit_score():
            break      # clearly a real reading — don't pay for more passes

    if not best_text or best_score <= 0:
        # Honest: no row is written. A photo with no text (a plate of food)
        # must NOT produce evidence Lori would then read back.
        return _result(False, "tesseract",
                       error=last_error or "no_text_found")
    return _result(True, "tesseract", raw_text=best_text,
                   summary=_summarize(best_text))


def _run_command(image_path: str) -> Dict[str, Any]:
    cmd = (os.getenv("HORNELORE_OCR_CMD", "") or "").strip()
    if not cmd:
        return _result(False, "command", error="HORNELORE_OCR_CMD not set")
    try:
        proc = subprocess.run(
            shlex.split(cmd) + [image_path],
            capture_output=True, text=True, timeout=_OCR_TIMEOUT_SEC,
        )
    except Exception as exc:
        return _result(False, "command", error="command failed: %s" % exc)
    if proc.returncode != 0:
        return _result(False, "command",
                       error="command exit %d: %s"
                       % (proc.returncode, (proc.stderr or "")[:200]))
    try:
        data = json.loads(proc.stdout or "{}")
    except Exception as exc:
        return _result(False, "command", error="bad JSON from command: %s" % exc)
    text = (data.get("text") or "").strip()
    summary = (data.get("summary") or "").strip() or _summarize(text)
    if not text and not summary:
        return _result(False, "command", error="no_text_found")
    return _result(True, "command", raw_text=text, summary=summary)


def run_ocr(image_path: str) -> Dict[str, Any]:
    """Run the configured OCR provider on a LOCAL image path.

    Returns {ok, engine, raw_text, summary, error}. ok=False whenever the
    feature is off, no provider is configured, the provider is unavailable,
    or no text was found — the caller must NOT write a row on ok=False."""
    if not ocr_enabled():
        return _result(False, "off", error="HORNELORE_PHOTO_OCR is off")
    if not image_path or not os.path.exists(image_path):
        return _result(False, ocr_provider(), error="image file not found")
    prov = ocr_provider()
    if prov == "tesseract":
        return _run_tesseract(image_path)
    if prov == "command":
        return _run_command(image_path)
    return _result(False, prov or "off", error="no OCR provider configured")


__all__ = ["run_ocr", "ocr_enabled", "ocr_provider", "ocr_langs",
           "ocr_psms", "ocr_max_dim", "ocr_early_exit_score",
           "ocr_min_ratio"]
