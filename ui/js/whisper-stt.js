/**
 * whisper-stt.js — Lorevox WO-ML-01 Phase 1B
 * ──────────────────────────────────────────
 * Whisper-backed Speech-to-Text engine that exposes the same
 * interface as the browser's `SpeechRecognition` API.
 *
 * Drop-in replacement: when `LV_USE_WHISPER_STT=1` (localStorage flag
 * OR runtime71 setting), `_ensureRecognition()` in app.js constructs
 * a `WhisperSTT` instance instead of `webkitSpeechRecognition`. The
 * rest of the codebase — including `recognition.onresult` in app.js,
 * the FocusCanvas mic-modal hook, the `isLoriSpeaking` self-hearing
 * guard, and the WO-STT-LIVE-02 fragile-fact transcript-guard —
 * works identically, because the synthetic events emitted by this
 * module match the shape of `SpeechRecognitionEvent`.
 *
 * Why this exists:
 *
 *   - Web Speech (Chrome's only STT engine) sends audio to Google's
 *     servers. Lorevox is a local-first product; that's a privacy
 *     posture mismatch the project shouldn't ship long-term.
 *   - Web Speech is English-only on most browsers. Lorevox needs to
 *     capture Spanish-speaking elders + code-switching narrators.
 *   - Web Speech's `recognition.onresult` only fires with FINAL
 *     segments; interim text gets dropped on mic-stop. This produced
 *     the 2026-05-07 "iii" capture bug — Chris's full utterance was
 *     in interim limbo when the mic stopped, only "iii" survived.
 *
 * Whisper-large-v3 already handles 99 languages with auto-detection
 * (per WO-ML-01 Phase 1A audit). The backend route at
 * /api/stt/transcribe was enriched in Phase 1A to return language,
 * confidence, and duration metadata. This module is the FE wrapper
 * that POSTs MediaRecorder audio chunks to that route and translates
 * the responses into Web-Speech-shaped recognition events.
 *
 * Architecture:
 *
 *   .start()          → getUserMedia + MediaRecorder, ~1.5s timeslice
 *   .stop()           → stop recorder, flush any pending audio
 *   .abort()          → alias for stop
 *   .onresult / .onend / .onerror / .onstart → standard SR callbacks
 *   .continuous / .interimResults / .lang     → standard SR properties
 *
 *   Each MediaRecorder `dataavailable` event enqueues a webm chunk.
 *   A single-flight worker drains the queue, POSTing each chunk to
 *   /api/stt/transcribe with `lang=auto` (or whatever `.lang` was
 *   set to). The response is wrapped in a Web-Speech-shaped event
 *   and dispatched via `.onresult`.
 *
 *   Each chunk produces an isFinal=true result. WhisperSTT does NOT
 *   emit interim events — Whisper's chunked-batch model doesn't
 *   produce them naturally. The mic modal's "..." indicator can
 *   substitute for the missing interim feedback.
 *
 * Feature flag: `LV_USE_WHISPER_STT` (localStorage key
 * `lv_use_whisper_stt` value "1" → on). Default OFF — Web Speech
 * remains the engine until smoke-validated.
 */
(function () {
  "use strict";

  // ── Internal helpers ─────────────────────────────────────────────

  // Pick a MediaRecorder mime type the browser supports. Order
  // matches Whisper-backend acceptance: webm/opus is best, mp4/aac
  // is the Safari fallback, ogg/opus is a third option.
  function _pickMimeType() {
    var candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
      ""
    ];
    if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) {
      return "";
    }
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i];
      if (!c) return "";
      try {
        if (MediaRecorder.isTypeSupported(c)) return c;
      } catch (_e) { /* ignore */ }
    }
    return "";
  }

  // Map browser-style locale ("en-US", "es-MX") to ISO-639-1 ("en",
  // "es") for the backend `lang` parameter. "auto" / empty pass
  // through so Phase 1A's auto-detect path triggers.
  function _normalizeLang(lang) {
    if (!lang) return "auto";
    var l = String(lang).trim().toLowerCase();
    if (l === "auto" || l === "") return "auto";
    if (l.indexOf("-") >= 0) l = l.split("-")[0];
    return l;
  }

  // ── WhisperSTT constructor ───────────────────────────────────────

  function WhisperSTT() {
    // SpeechRecognition-shaped public surface. App code (and the
    // FocusCanvas mic-modal hook) reads/sets these as if this were a
    // SpeechRecognition instance.
    this.continuous = false;
    this.interimResults = false;
    this.lang = "auto";
    this.maxAlternatives = 1;

    this.onstart = null;
    this.onresult = null;
    this.onend = null;
    this.onerror = null;
    this.onaudiostart = null;
    this.onaudioend = null;
    this.onsoundstart = null;
    this.onsoundend = null;
    this.onspeechstart = null;
    this.onspeechend = null;
    this.onnomatch = null;

    // Internal state
    this._mediaStream = null;
    this._mediaRecorder = null;
    this._chunkQueue = [];
    this._processing = false;
    this._stopped = true;
    this._resultCounter = 0;
    this._mimeType = _pickMimeType();

    // Tunables (kept on the instance so the operator can adjust if
    // needed via window.WhisperSTT.prototype._chunkSizeMs = ...)
    // 1500ms is a reasonable default: short enough that the modal
    // feels responsive, long enough that VAD has something to work
    // with (faster-whisper's vad_filter+min_silence_duration_ms=500
    // on the backend will trim leading/trailing silence per chunk).
    this._chunkSizeMs = 1500;
  }

  // ── start() ──────────────────────────────────────────────────────

  WhisperSTT.prototype.start = function () {
    var self = this;
    if (!self._stopped) {
      console.warn("[whisper-stt] start() called while already running");
      return;
    }
    self._stopped = false;
    self._chunkQueue = [];
    self._resultCounter = 0;

    // Browser feature gate
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.error("[whisper-stt] getUserMedia not supported");
      self._fireError("audio-capture", "getUserMedia not supported");
      self._stopped = true;
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      console.error("[whisper-stt] MediaRecorder not supported");
      self._fireError("audio-capture", "MediaRecorder not supported");
      self._stopped = true;
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then(function (stream) {
        if (self._stopped) {
          // stop() was called before getUserMedia resolved — clean up
          stream.getTracks().forEach(function (t) { t.stop(); });
          return;
        }
        self._mediaStream = stream;
        var opts = {};
        if (self._mimeType) opts.mimeType = self._mimeType;
        try {
          self._mediaRecorder = new MediaRecorder(stream, opts);
        } catch (mrErr) {
          console.error("[whisper-stt] MediaRecorder ctor failed:", mrErr);
          self._fireError("audio-capture", "MediaRecorder construction failed: " + mrErr.message);
          self._cleanupStream();
          self._stopped = true;
          return;
        }

        self._mediaRecorder.ondataavailable = function (ev) {
          if (!ev.data || ev.data.size === 0) return;
          // Self-hearing guard: drop chunks captured while Lori is
          // speaking through the speaker. The existing
          // `recognition.onresult` in app.js also has this guard,
          // but dropping at the source saves a round-trip to the
          // backend. Cheap network insurance.
          if (typeof window.isLoriSpeaking !== "undefined" && window.isLoriSpeaking) {
            console.log("[whisper-stt] chunk dropped (isLoriSpeaking=true)");
            return;
          }
          self._chunkQueue.push(ev.data);
          self._processQueue();
        };

        self._mediaRecorder.onerror = function (ev) {
          var msg = (ev && ev.error) ? String(ev.error) : "MediaRecorder error";
          console.warn("[whisper-stt] MediaRecorder error:", msg);
          self._fireError("audio-capture", msg);
        };

        self._mediaRecorder.onstop = function () {
          // MediaRecorder has fully stopped. Drain remaining queue
          // and fire onend after the worker completes.
          self._processQueue().then(function () {
            self._cleanupStream();
            if (typeof self.onend === "function") {
              try { self.onend({}); } catch (eEnd) { console.warn("[whisper-stt] onend threw:", eEnd); }
            }
          });
        };

        try {
          self._mediaRecorder.start(self._chunkSizeMs);
          console.log("[whisper-stt] started (mime=" + (self._mimeType || "default") +
                      ", chunk=" + self._chunkSizeMs + "ms, lang=" + self.lang + ")");
          if (typeof self.onstart === "function") {
            try { self.onstart({}); } catch (eStart) { console.warn("[whisper-stt] onstart threw:", eStart); }
          }
        } catch (startErr) {
          console.error("[whisper-stt] MediaRecorder.start threw:", startErr);
          self._fireError("audio-capture", "MediaRecorder.start: " + startErr.message);
          self._cleanupStream();
          self._stopped = true;
        }
      })
      .catch(function (err) {
        console.error("[whisper-stt] getUserMedia rejected:", err);
        var name = (err && err.name) || "audio-capture";
        var nameMap = {
          "NotAllowedError":   "not-allowed",
          "PermissionDeniedError": "not-allowed",
          "NotFoundError":     "audio-capture",
          "DevicesNotFoundError": "audio-capture",
          "NotReadableError":  "audio-capture",
          "OverconstrainedError": "audio-capture"
        };
        self._fireError(nameMap[name] || "audio-capture", err.message || String(err));
        self._stopped = true;
      });
  };

  // ── stop() / abort() ─────────────────────────────────────────────

  WhisperSTT.prototype.stop = function () {
    if (this._stopped && !this._mediaRecorder) return;
    this._stopped = true;
    if (this._mediaRecorder && this._mediaRecorder.state !== "inactive") {
      try { this._mediaRecorder.stop(); }
      catch (e) { console.warn("[whisper-stt] MediaRecorder.stop threw:", e); }
    } else {
      // No active recorder — fire onend now so callers don't wait
      this._cleanupStream();
      if (typeof this.onend === "function") {
        try { this.onend({}); } catch (eEnd) { console.warn("[whisper-stt] onend threw:", eEnd); }
      }
    }
  };

  WhisperSTT.prototype.abort = function () {
    // Same as stop for our purposes; SR.abort() in browsers also
    // discards in-flight buffers, which we approximate by clearing
    // the queue.
    this._chunkQueue = [];
    this.stop();
  };

  // ── Internal: queue worker ───────────────────────────────────────

  WhisperSTT.prototype._processQueue = async function () {
    if (this._processing) return;
    this._processing = true;
    while (this._chunkQueue.length > 0) {
      var blob = this._chunkQueue.shift();
      try {
        var result = await this._transcribeBlob(blob);
        if (result && typeof result.text === "string" && result.text.length > 0) {
          this._dispatchResult(result);
        }
      } catch (err) {
        console.warn("[whisper-stt] chunk transcribe failed:", err && err.message ? err.message : err);
        // Don't fire onerror for individual chunks — keeps the
        // recording continuing. Operator can grep [whisper-stt]
        // warnings if quality regresses.
      }
    }
    this._processing = false;
  };

  // ── Internal: POST chunk to /api/stt/transcribe ──────────────────

  WhisperSTT.prototype._transcribeBlob = async function (blob) {
    var fd = new FormData();
    var ext = "webm";
    if (this._mimeType.indexOf("mp4") >= 0) ext = "mp4";
    else if (this._mimeType.indexOf("ogg") >= 0) ext = "ogg";
    fd.append("file", blob, "chunk." + ext);
    fd.append("lang", _normalizeLang(this.lang));

    var resp;
    try {
      resp = await fetch("/api/stt/transcribe", { method: "POST", body: fd });
    } catch (netErr) {
      throw new Error("network: " + netErr.message);
    }
    if (!resp.ok) {
      throw new Error("HTTP " + resp.status);
    }
    var json;
    try {
      json = await resp.json();
    } catch (jsonErr) {
      throw new Error("invalid JSON: " + jsonErr.message);
    }
    if (!json || json.ok !== true) {
      throw new Error("not ok: " + (json && json.error ? json.error : "unknown"));
    }
    return json;
  };

  // ── Internal: dispatch SpeechRecognition-shaped result ───────────

  WhisperSTT.prototype._dispatchResult = function (result) {
    if (typeof this.onresult !== "function") return;

    var idx = this._resultCounter;
    this._resultCounter += 1;

    // Build a SpeechRecognitionResultList-shaped object. Existing
    // consumers iterate `for (var i = e.resultIndex; i < e.results.length; i++)`
    // so we expose `.length` and the indexed entry. We DO NOT pre-
    // fill earlier indices — consumers only read from `resultIndex`
    // upward, which matches how the browser delivers events.
    var resultEntry = {
      isFinal: true,
      length: 1,
      0: {
        transcript: result.text,
        confidence: (typeof result.confidence === "number") ? result.confidence : 0.9
      }
    };

    var resultList = { length: idx + 1 };
    resultList[idx] = resultEntry;

    var event = {
      resultIndex: idx,
      results: resultList,
      // WhisperSTT extension fields (consumers that read these get
      // the metadata; consumers that don't, ignore them safely):
      language: result.language || null,
      languageProbability: (typeof result.language_probability === "number") ? result.language_probability : null,
      duration: (typeof result.duration_sec === "number") ? result.duration_sec : null,
      engine: result.engine || "whisper_backend",
      _whisperRaw: result
    };

    console.log("[whisper-stt] result idx=" + idx +
                " lang=" + (event.language || "?") +
                " conf=" + (resultEntry[0].confidence || "?") +
                " text=" + JSON.stringify(result.text).slice(0, 80));

    try {
      this.onresult(event);
    } catch (e) {
      console.warn("[whisper-stt] onresult handler threw:", e);
    }
  };

  // ── Internal: cleanup + error helpers ────────────────────────────

  WhisperSTT.prototype._cleanupStream = function () {
    if (this._mediaStream) {
      try {
        this._mediaStream.getTracks().forEach(function (t) {
          try { t.stop(); } catch (_e) {}
        });
      } catch (_e) {}
      this._mediaStream = null;
    }
    this._mediaRecorder = null;
  };

  WhisperSTT.prototype._fireError = function (errCode, message) {
    if (typeof this.onerror === "function") {
      try {
        this.onerror({ error: errCode, message: message || errCode });
      } catch (e) { console.warn("[whisper-stt] onerror handler threw:", e); }
    }
  };

  // ── Public export ────────────────────────────────────────────────

  window.WhisperSTT = WhisperSTT;

  // Also expose a small helper so app.js / dev tools can probe
  // engine availability without poking at globals directly.
  window.WhisperSTTAvailable = function () {
    return typeof MediaRecorder !== "undefined" &&
           navigator.mediaDevices &&
           typeof navigator.mediaDevices.getUserMedia === "function";
  };

  console.log("[whisper-stt] module loaded");
})();
