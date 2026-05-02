/* WO-OPERATOR-RESOURCE-DASHBOARD-01 — Commit 4: UI → backend heartbeat.
 *
 * The backend can't see browser camera/mic/TTS state directly. This
 * bridge reads from the well-known globals the diag panel already
 * inspects (window.lv10dBp*, window.cameraActive, window.lvLastTtsState,
 * etc.) and POSTs a compact snapshot to
 *   POST /api/operator/stack-dashboard/ui-heartbeat
 * every 5 seconds. The backend caches with a TTL — so a closed tab or
 * a stale state surfaces as `unknown` automatically (no special
 * cleanup needed here).
 *
 * Pre-work review note #4: this is sender-trusted. Fields are filtered
 * so a malformed page can't pivot to RCE; everything is plain bool /
 * number / short string.
 *
 * Sends are skipped when:
 *   - dashboard backend gate is OFF (we discover that via a 404 on the
 *     first POST, then back off for 60s before retrying)
 *   - document is hidden AND the last successful send was <30s ago
 *
 * No narrator UI side-effects. This file should be near-zero cost
 * when the dashboard isn't open.
 */
(function () {
  "use strict";

  // BUG-224 fix (2026-05-01): see bug-panel-dashboard.js comment.
  // Bare relative URL hits port 8082 (UI), not 8000 (API).
  const _O = (typeof ORIGIN !== "undefined" && ORIGIN) || "http://localhost:8000";
  const ENDPOINT = _O + "/api/operator/stack-dashboard/ui-heartbeat";
  const SEND_INTERVAL_FOREGROUND_MS = 5 * 1000;
  const SEND_INTERVAL_BACKGROUND_MS = 30 * 1000;
  const BACKOFF_AFTER_404_MS = 60 * 1000;

  let _timer = null;
  let _gateOffUntil = 0;
  let _inflight = false;
  let _lastSentAt = 0;

  function _readCameraState() {
    // Multiple sources: state.js exposes a module-local cameraActive
    // that emotion-pipeline.js mirrors. We pick whichever is truthy.
    // Defensive: never throw — return shape with `active=false` if we
    // can't read anything.
    try {
      const s = window.state || {};
      const inputState = (s.inputState || {});
      const camActive =
        !!(window.cameraActive ||
           inputState.cameraActive ||
           (window.lv10dBpCamPreview && window.lv10dBpCamPreview === "active") ||
           (window.lvCamera && window.lvCamera.active));
      const out = { active: camActive };

      // Try to read width/height from a hidden video element if one
      // exists (camera-preview.js exposes lvCamera.video).
      const v = (window.lvCamera && window.lvCamera.video)
        || document.getElementById("lvCameraPreviewVideo")
        || document.querySelector("video.lv-camera-preview");
      if (v && typeof v.videoWidth === "number" && v.videoWidth > 0) {
        out.width = v.videoWidth;
        out.height = v.videoHeight;
        out.track_state = (v.srcObject && v.srcObject.active === false)
          ? "ended" : "live";
      }
      return out;
    } catch (_) {
      return { active: false };
    }
  }

  function _readMicState() {
    try {
      const inputState = (window.state && window.state.inputState) || {};
      const micActive =
        !!(window.micActive ||
           inputState.micActive ||
           (window.lvMic && window.lvMic.active));
      const out = { active: micActive };

      // Try to read RMS from a known analyser. Most likely sources:
      //   window.lvMic.lastRms, window.lvAudioMeter.rms, etc.
      const rms = (window.lvMic && typeof window.lvMic.lastRms === "number")
        ? window.lvMic.lastRms
        : (window.lvAudioMeter && typeof window.lvAudioMeter.rms === "number")
          ? window.lvAudioMeter.rms
          : null;
      if (typeof rms === "number" && !isNaN(rms)) {
        // Normalize to 0..1; tolerate either float-RMS or 0..100 scale.
        out.rms_level = rms > 1 ? Math.min(1, rms / 100) : Math.max(0, rms);
      }
      out.track_state = micActive ? "live" : "off";
      return out;
    } catch (_) {
      return { active: false };
    }
  }

  function _readTtsState() {
    try {
      // Several TTS subsystems set a global flag during playback.
      const speaking = !!(window.isLoriSpeaking ||
                          (window.lv10dBpTts && window.lv10dBpTts === "speaking") ||
                          (window.lvTts && window.lvTts.speaking));
      const out = { speaking };
      const q = (window.lvTts && typeof window.lvTts.queueLength === "number")
        ? window.lvTts.queueLength : null;
      if (typeof q === "number") out.queue_length = q;
      return out;
    } catch (_) {
      return { speaking: false };
    }
  }

  function _readPersonId() {
    try {
      const s = window.state || {};
      const sess = s.session || {};
      return sess.personId
        || sess.activeNarratorId
        || (window.lvActiveNarratorId)
        || null;
    } catch (_) {
      return null;
    }
  }

  function _readSessionId() {
    try {
      const s = window.state || {};
      return (s.session && s.session.sessionId) || null;
    } catch (_) {
      return null;
    }
  }

  async function _send() {
    if (_inflight) return;
    if (Date.now() < _gateOffUntil) return;
    // If the tab is hidden and we sent recently, skip.
    if (document.hidden && (Date.now() - _lastSentAt) < SEND_INTERVAL_BACKGROUND_MS) {
      return;
    }
    _inflight = true;
    const payload = {
      person_id: _readPersonId(),
      session_id: _readSessionId(),
      camera: _readCameraState(),
      microphone: _readMicState(),
      tts: _readTtsState(),
    };
    try {
      const resp = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
        // Don't keep the page alive on unload for this request.
        keepalive: false,
      });
      if (resp.status === 404) {
        // Backend gate OFF — back off for a minute before trying again.
        _gateOffUntil = Date.now() + BACKOFF_AFTER_404_MS;
        return;
      }
      if (resp.ok) {
        _lastSentAt = Date.now();
      }
    } catch (_) {
      // Network blip — let the next interval retry.
    } finally {
      _inflight = false;
    }
  }

  function _scheduleNext() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    const interval = document.hidden
      ? SEND_INTERVAL_BACKGROUND_MS
      : SEND_INTERVAL_FOREGROUND_MS;
    _timer = setInterval(_send, interval);
  }

  function _start() {
    _send();  // initial probe
    _scheduleNext();
    document.addEventListener("visibilitychange", () => {
      _scheduleNext();
      if (!document.hidden) _send();
    }, false);
  }

  // Manual hook so other scripts can force a heartbeat (e.g., right
  // after the operator toggles a permission).
  window.lvDashboardHeartbeat = _send;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _start, { once: true });
  } else {
    _start();
  }
})();
