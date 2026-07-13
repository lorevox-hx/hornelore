"""Test package marker.

Without this file, `python -m unittest discover -s tests -t .` fails with
"Start directory is not importable" — the canonical full-suite command did not
run at all, which is a large part of why the repo had no trustworthy all-green
signal. Module-style invocation (`python -m unittest tests.test_x`) worked via
implicit namespace packages, which masked the breakage.
"""
