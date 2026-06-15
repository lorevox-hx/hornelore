# BUG-UI-API-BASE-RESET-01 — Frontend loses API base URL on clean-start reload, calls land on UI server (port 8082) instead of API server (port 8000)

**Status:** **DOWNGRADED 2026-05-05 — likely harness/bootstrap artifact, NOT production root cause.** The 404s on port 8082 came from the UI server log during Playwright cold-restart runs; the manual switch transcripts show the API working correctly in real browser sessions (Lori successfully reads identity / DOB / POB / wife memory — none of which would land if API calls were 404'ing in production). Most likely cause: Playwright fires page-load health checks before frontend bootstrap completes, those checks hit the static server before the API client config is set. Real-user reload doesn't have that race because there's no automation racing past load. Spec retained for the production-side hardening question (should the API base have a hard-coded fallback regardless?), but should NOT be treated as the root cause of v7 post-restart RED.
**Severity:** LOW (production hardening, not blocker)
**Surfaced by:** TEST-23 v7 (2026-05-05) — initially overfit as root cause; downgraded same day after Chris pointed out the 404s appear only in Playwright runs, not in production traffic
**Author:** Chris + Claude (2026-05-05)
**Lane:** parallel cleanup — does NOT supersede BUG-UI-POSTRESTART-SESSION-START-01 (which reopens with refined hypothesis space)

---

## Problem

After cold-restart browser context, the frontend calls `/api/...` endpoints relative to the UI static server (port 8082) instead of the API server (port 8000). Every API call returns 404 silently. The narrator-room never hydrates state, BB UI mirror stays empty, conditional UI buttons (Start Narrator Session / Enter Interview Mode) never render, and `session_start()` throws "neither button visible" — exactly what the harness sees in v7.

**This is not Lori's fault.** This is not a memory architecture bug. The browser is calling the wrong server. Once that's fixed, most of the post-restart RED in v7 should resolve in a single fix.

## Evidence

UI server stdlib http log (port 8082) during v7:

```
127.0.0.1 - - [05/May/2026 08:54:35] code 404, message File not found
127.0.0.1 - - [05/May/2026 08:54:35] "GET /api/photos/health HTTP/1.1" 404 -
127.0.0.1 - - [05/May/2026 08:54:35] code 404, message File not found
127.0.0.1 - - [05/May/2026 08:54:35] "GET /api/media-archive/health HTTP/1.1" 404 -
127.0.0.1 - - [05/May/2026 08:54:35] code 404, message File not found
127.0.0.1 - - [05/May/2026 08:54:35] "GET /api/memory-archive/health HTTP/1.1" 404 -
127.0.0.1 - - [05/May/2026 08:54:35] code 404, message File not found
127.0.0.1 - - [05/May/2026 08:54:35] "GET /api/bio-builder/questionnaire?person_id=aa4992e8-... HTTP/1.1" 404 -
```

The log header format `127.0.0.1 - - [DD/Mon/YYYY HH:MM:SS]` is the Python `http.server` stdlib format — that's the UI server (uvicorn uses `INFO: 127.0.0.1:port - "..."`). The API server's log shows the SAME endpoints returning 200 when called correctly:

```
INFO:     127.0.0.1:38366 - "GET /api/memory-archive/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:38366 - "GET /api/memory-archive/people/d1ecf805-.../export HTTP/1.1" 200 OK
```

So the routers ARE mounted on port 8000. The frontend is just calling the wrong port after restart.

## Confirms operator log AMBERs

The operator-log AMBERs across both Mary and Marvin reports — `/api/photos/health installed (router not mounted in main.py)`, same for media-archive, memory-archive, bio-builder — are not actually router mount issues. The health check itself is hitting port 8082 instead of 8000, and the 404s come from the static file server's path not the FastAPI router. The check looks like a router-mount failure but is the same API-base-URL bug.

## Why the startup log matters

```
[startup] Clean-start flag detected — browser will auto-clear state.
```

The clean-start flag clears localStorage / sessionStorage. If the API base URL is stored there (and not also hard-coded as a fallback), every reload after clean-start loses it. The frontend then defaults to relative paths, which resolve against whatever origin the page was loaded from — and the UI is loaded from `http://127.0.0.1:8082/ui/hornelore1.0.html`, so `/api/foo` becomes `http://127.0.0.1:8082/api/foo`.

## Reproduction

Trivial. Open browser dev tools network tab, navigate to `http://127.0.0.1:8082/ui/hornelore1.0.html`, watch any narrator-load API call. If the request goes to `127.0.0.1:8082/api/...`, this bug fires. If it goes to `127.0.0.1:8000/api/...`, it doesn't.

## Diagnosis

The frontend's API base URL is determined dynamically in some module (likely `ui/js/config.js`, `ui/js/api-client.js`, `ui/js/state.js`, or inline in `hornelore1.0.html`). Need to read the actual code to find the exact site.

Likely current shape:

```javascript
const API_BASE = localStorage.getItem("LV_API_BASE") || window.LV_API_BASE || "/";
```

When `LV_API_BASE` localStorage is cleared by clean-start AND `window.LV_API_BASE` isn't set, it falls back to `/` which resolves against the UI server origin.

## Fix

Make the API base deterministic with a hard-coded fallback that points at the API server, NOT a relative path:

```javascript
const API_BASE =
  window.HORNELORE_API_BASE ||
  window.LV_API_BASE ||
  localStorage.getItem("LV_API_BASE") ||
  "http://127.0.0.1:8000";
```

The hard-coded fallback ensures clean-start can't break routing. Operator override paths (window globals, localStorage) still work for dev / testing.

**Locked rule:** clean-start must NEVER erase the API base fallback. Either the fallback is hard-coded in the JS file (the simplest answer), or the clean-start logic preserves API_BASE specifically while clearing other state.

## Acceptance gate

Post-restart in v8:

- All `/api/...` calls hit port 8000 (API server), not port 8082 (UI server)
- Health checks `/api/photos/health` / `/api/media-archive/health` / `/api/memory-archive/health` / `/api/bio-builder/questionnaire` return 200 from the API server
- Operator log AMBERs about "router not mounted" disappear
- Post-restart `session_start()` finds Start Narrator Session OR Enter Interview Mode button (because BB state hydrates correctly via working API calls)
- Cold-restart resume phase reaches scoring (PASS/AMBER/RED on actual Lori behavior, not on missing buttons)
- TEST-23 v8 post-restart RED → PASS or AMBER for both narrators on identity recall (because the API can actually serve profile data)

## Files (planned, after diagnostic read)

**Likely modified:**
- `ui/js/config.js` OR `ui/js/api-client.js` OR equivalent — wherever API_BASE is currently determined
- `ui/hornelore1.0.html` — possibly the inline window-globals setup
- `ui/js/clean-start.js` OR equivalent — preserve API_BASE during state clear

**Possibly modified:**
- `scripts/launchers/hornelore_run_visible.sh` (or equivalent) — surface API_BASE as an explicit env var that the UI server templates into the page

**Zero touch:**
- API server code (the API is fine; only the frontend routing is broken)
- Lori behavior services
- Extract router
- Memory composer

## Risks & rollback

**Risk 1: hard-coded URL doesn't match production.** If the API runs on a different port in production (e.g., `8001` or behind a reverse proxy), hard-coding `127.0.0.1:8000` breaks production. Mitigation: hard-code the dev fallback and surface a server-side templating step that injects production URL at build/deploy time. For Hornelore's local-only deployment, `127.0.0.1:8000` is correct.

**Risk 2: existing dev workflows that override LV_API_BASE break.** Mitigation: keep the override chain — window globals + localStorage still take precedence over the hard-coded fallback. Only behavior change is when ALL overrides are absent (post-clean-start, post-restart).

**Risk 3: bugs masked by the API base bug surface as new failures.** When the routing fix lands, other bugs that were silently 404'd may surface visibly. That's a feature, not a regression — it tells us what was actually broken vs. what was just routing. Run TEST-23 v8 immediately after the fix to surface whatever's underneath.

**Rollback:** revert the JS change. Frontend goes back to relying on localStorage / window globals only. Cold-restart resume goes back to broken-by-default. No regression on the (working) pre-restart flow.

## Sequencing

This is THE first item in Phase 0 / Track 1, ahead of the broader BUG-UI-POSTRESTART-SESSION-START-01 spec. Likely a 1-2 line JS fix once the right module is identified. Half a session including the diagnostic read + fix + v8 verification.

After this lands, BUG-UI-POSTRESTART-SESSION-START-01 may close-via-diagnosis (the broader spec was capturing the symptom; this spec is the actual root cause). If post-restart still fails after the API base fix, the broader spec stays open with revised hypotheses.

Same downstream beneficiaries as BUG-UI-POSTRESTART-SESSION-START-01: every other parent-session-blocker fix needs working cold-restart resume to verify. This bug being the real root cause means the verification surface unblocks for all of them in one fix.

## Cross-references

- **BUG-UI-POSTRESTART-SESSION-START-01** — broader spec; this WO supersedes Hypothesis E (the most likely from that spec's diagnostic plan). When this lands, the broader spec gets re-evaluated; likely close-via-diagnosis.
- **WO-PROVISIONAL-TRUTH-01 Phase E** — BB state mirror gap. Some of the v6/v7 BB state firstName=None evidence could be downstream of this bug (API calls to load profile data 404 silently → BB never gets profile to mirror). Re-test after this lands; Phase E may need narrower scope.
- **Operator log AMBERs** ("router not mounted" for photos / media-archive / memory-archive / bio-builder) — all explained by this bug; will disappear when fixed.

## Changelog

- 2026-05-05: Spec authored after UI log analysis revealed 404s coming from port 8082 (UI server stdlib http log) not port 8000 (API server uvicorn log). Single root cause likely behind most v7 post-restart RED.
