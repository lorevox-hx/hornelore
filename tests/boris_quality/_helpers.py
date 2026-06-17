from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Tuple

# Ensure repo root is importable when tests are copied under tests/boris_quality.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def require_callable(candidates: Iterable[Tuple[str, str]]) -> Callable[..., Any]:
    """Return the first importable callable from a list of (module, name).

    If no callable exists, fail with a direct message. This is intentional:
    Boris tests are patch-grade red tests, so missing production helpers should
    fail loudly instead of silently skipping.
    """
    attempted = []
    for module_name, attr_name in candidates:
        attempted.append(f"{module_name}.{attr_name}")
        try:
            mod = importlib.import_module(module_name)
        except Exception:
            continue
        obj = getattr(mod, attr_name, None)
        if callable(obj):
            return obj
    raise AssertionError(
        "Required production callable not found. Implement one of: "
        + ", ".join(attempted)
    )


def get_source(module_name: str) -> str:
    mod = importlib.import_module(module_name)
    try:
        return inspect.getsource(mod)
    except Exception as exc:
        raise AssertionError(f"Could not inspect source for {module_name}: {exc}")


def normalize_rows(score: dict) -> dict:
    rows = score.get("rows", {})
    if not isinstance(rows, dict):
        raise AssertionError(f"score['rows'] is not a dict: {score!r}")
    return rows


def status_is_failish(value: str) -> bool:
    return str(value).upper() in {"FAIL", "PARTIAL", "WARN", "WARNING"}


def assert_row_fails(testcase, score: dict, row_name: str) -> None:
    rows = normalize_rows(score)
    testcase.assertIn(
        row_name,
        rows,
        f"Missing scorer row {row_name!r}. Add it to scripts/harness_lib.py::score_chapter().",
    )
    testcase.assertEqual(
        rows[row_name],
        "FAIL",
        f"Expected row {row_name!r} to FAIL, got {rows[row_name]!r}. Full rows: {rows}",
    )


def assert_row_passes(testcase, score: dict, row_name: str) -> None:
    rows = normalize_rows(score)
    testcase.assertIn(row_name, rows, f"Missing scorer row {row_name!r}.")
    testcase.assertEqual(
        rows[row_name],
        "PASS",
        f"Expected row {row_name!r} to PASS, got {rows[row_name]!r}. Full rows: {rows}",
    )
