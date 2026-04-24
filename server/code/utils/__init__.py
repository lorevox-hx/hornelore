"""Shared utility helpers for the Hornelore server.

This package holds small, side-effect-free helpers that multiple routers
or services use.  Kept intentionally lean — if a helper needs DB access
or business logic it belongs under ``server/code/services`` instead.
"""
