"""OAuth access-token minting for the Google Photos Picker lane.

WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 1.

Why this is twenty lines of ``requests`` and not ``google-auth``: the
whole job is one form POST to Google's token endpoint. Pulling in
``google-auth`` / ``google-api-python-client`` would be an environment
change -- new pins in two venvs -- to buy a wrapper around a request we
can write plainly. ``requests`` is already installed in both venvs.

THE CREDENTIAL RULE, stated once so it is not re-derived later:

  * The client id, client secret and refresh token are read from the
    process environment and nowhere else.
  * They are never written to the database. ``external_ref`` on
    ``import_batch`` holds the Picker session id, which is an opaque
    provider handle, and ``import_repository._assert_no_secret()``
    independently refuses anything token-shaped that reaches it.
  * They are never returned in a response body. ``GET /health`` reports
    PRESENCE as a boolean and nothing else -- not a prefix, not a
    length, not a masked tail.
  * They are never logged. Failures from Google are surfaced by their
    ``error`` / ``error_description`` fields, not by echoing the raw
    response body, because a raw body is a place a secret could
    reappear by accident.

The minted access token is short-lived (Google issues ~3600s) and is
cached in module state with its expiry. It is deliberately not cached on
disk: a process restart mints a new one, which costs one HTTP round
trip and removes a file that would otherwise hold a live credential.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("code.services.google_picker.oauth")

TOKEN_URL = "https://oauth2.googleapis.com/token"

# The only scope this lane needs. Google's Picker docs describe it as
# covering session create/get/delete plus listing that session's media
# items -- nothing else, and no access to the wider library.
PICKER_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"

ENV_CLIENT_ID = "GOOGLE_PICKER_CLIENT_ID"
ENV_CLIENT_SECRET = "GOOGLE_PICKER_CLIENT_SECRET"
ENV_REFRESH_TOKEN = "GOOGLE_PICKER_REFRESH_TOKEN"

CREDENTIAL_ENV_KEYS = (ENV_CLIENT_ID, ENV_CLIENT_SECRET, ENV_REFRESH_TOKEN)

# Mint a new token this many seconds before the old one actually dies,
# so a long call cannot start with three seconds of validity left.
_EXPIRY_SKEW_SECONDS = 120

_TOKEN_TIMEOUT = (10, 30)   # (connect, read)

_lock = threading.Lock()
_cached_token: Optional[str] = None
_cached_expires_at: float = 0.0


class PickerAuthError(RuntimeError):
    """Credentials are missing, or Google refused to mint a token.

    Carries ``reason`` -- a short machine-ish string -- so the router can
    map it to a status code without string-matching the message.
    """

    def __init__(self, message: str, reason: str = "auth_failed") -> None:
        super().__init__(message)
        self.reason = reason


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def credentials_present() -> Dict[str, bool]:
    """Which credential env keys are set, as booleans ONLY.

    This is what ``GET /health`` reports. It returns presence, never
    content: no prefixes, no lengths, no masked tails. A length is a
    small leak and a prefix is a larger one, and neither helps diagnose
    anything that a boolean does not.
    """
    return {key: bool(_env(key)) for key in CREDENTIAL_ENV_KEYS}


def credentials_complete() -> bool:
    return all(credentials_present().values())


def _missing_keys() -> list:
    return [k for k, present in credentials_present().items() if not present]


def reset_cache() -> None:
    """Drop the cached access token. Used by tests and by the router
    when Google reports the refresh token itself is dead."""
    global _cached_token, _cached_expires_at
    with _lock:
        _cached_token = None
        _cached_expires_at = 0.0


def _describe_token_error(resp: "requests.Response") -> str:
    """Build a message from Google's structured error fields.

    Never returns ``resp.text``. Google's token endpoint answers errors
    as ``{"error": ..., "error_description": ...}``; if it ever answers
    with something else, we say so rather than pasting the body, because
    the body is exactly where a credential could reappear.
    """
    try:
        payload = resp.json()
    except ValueError:
        return ("Google's token endpoint returned HTTP %d with a "
                "non-JSON body (body withheld)." % resp.status_code)
    if not isinstance(payload, dict):
        return ("Google's token endpoint returned HTTP %d with an "
                "unexpected JSON shape (body withheld)." % resp.status_code)
    err = payload.get("error")
    desc = payload.get("error_description")
    parts = [p for p in (err, desc) if isinstance(p, str) and p]
    if not parts:
        return ("Google's token endpoint returned HTTP %d with no error "
                "field (body withheld)." % resp.status_code)
    return "Google refused the token exchange (HTTP %d): %s" % (
        resp.status_code, " -- ".join(parts))


def _is_dead_refresh_token(resp: "requests.Response") -> bool:
    """``invalid_grant`` is what Google says when the refresh token has
    expired or been revoked. In a Google Cloud project whose consent
    screen is external-type with publishing status 'Testing', refresh
    tokens for a non-basic scope expire after SEVEN DAYS -- so this is
    not an exotic failure here, it is the expected weekly one. It gets
    its own reason string so the operator is told to re-authorize
    instead of going looking for a broken route.
    """
    try:
        payload = resp.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("error") == "invalid_grant"


def get_access_token(force_refresh: bool = False) -> str:
    """Return a valid access token, minting one if the cache is cold or
    close to expiry. Raises ``PickerAuthError`` on any failure."""
    global _cached_token, _cached_expires_at

    missing = _missing_keys()
    if missing:
        raise PickerAuthError(
            "Google Picker credentials are not configured: %s not set in the "
            "environment. Set them in .env (they are gitignored) and restart "
            "the stack." % ", ".join(missing),
            reason="credentials_missing",
        )

    with _lock:
        now = time.time()
        if (not force_refresh and _cached_token
                and now < _cached_expires_at - _EXPIRY_SKEW_SECONDS):
            return _cached_token

        try:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "client_id": _env(ENV_CLIENT_ID),
                    "client_secret": _env(ENV_CLIENT_SECRET),
                    "refresh_token": _env(ENV_REFRESH_TOKEN),
                    "grant_type": "refresh_token",
                },
                timeout=_TOKEN_TIMEOUT,
            )
        except requests.RequestException as exc:
            # str(exc) on a requests error carries the URL, not the form
            # body, so this cannot echo the secret.
            raise PickerAuthError(
                "could not reach Google's token endpoint: %s" % exc,
                reason="network",
            ) from None

        if resp.status_code != 200:
            reason = ("refresh_token_expired"
                      if _is_dead_refresh_token(resp) else "auth_failed")
            if reason == "refresh_token_expired":
                _cached_token = None
                _cached_expires_at = 0.0
                raise PickerAuthError(
                    "Google rejected the stored refresh token (invalid_grant). "
                    "A project in 'Testing' publishing status expires refresh "
                    "tokens every 7 days for this scope -- re-authorize and "
                    "put the new GOOGLE_PICKER_REFRESH_TOKEN in .env.",
                    reason=reason,
                )
            raise PickerAuthError(_describe_token_error(resp), reason=reason)

        try:
            payload = resp.json()
        except ValueError:
            raise PickerAuthError(
                "Google's token endpoint returned HTTP 200 with a non-JSON "
                "body (body withheld).",
                reason="auth_failed",
            ) from None

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise PickerAuthError(
                "Google's token response carried no access_token.",
                reason="auth_failed",
            )

        try:
            expires_in = int(payload.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        # Treat a missing/absurd expires_in as a short life rather than a
        # long one. Being wrong short costs one extra round trip; being
        # wrong long means calls fail with a dead token.
        if expires_in <= 0 or expires_in > 24 * 3600:
            expires_in = 600

        _cached_token = token
        _cached_expires_at = time.time() + expires_in
        logger.info("google_picker: minted access token, expires_in=%ds",
                    expires_in)
        return token


def cache_state() -> Dict[str, Any]:
    """Non-secret view of the token cache, for ``GET /health``.

    Reports WHETHER a token is cached and how many seconds are left --
    never the token.
    """
    with _lock:
        if not _cached_token:
            return {"access_token_cached": False, "expires_in_seconds": None}
        remaining = int(max(0, _cached_expires_at - time.time()))
        return {"access_token_cached": True, "expires_in_seconds": remaining}
