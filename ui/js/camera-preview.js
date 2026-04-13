/* ═══════════════════════════════════════════════════════════════
   camera-preview.js — Draggable camera preview mirror
   Hornelore 1.0 (ported from Lorevox 8.0 lori8.0.html §4527-4611)
   Load order: after emotion-ui.js, before app.js

   Purpose:
   - Creates a small draggable video preview so the narrator can see
     themselves on screen (mirror effect via CSS scaleX(-1) in lori80.css).
   - Called by beginCameraConsent74() in app.js after the emotion engine
     starts and cameraActive is true.
   - Preview can be hidden (camera keeps running) and reopened.
   - Stream is attached from the existing getUserMedia grant — does not
     request a second camera permission.

   Privacy:
   - Video element is local display only — no frames leave the browser.
   - srcObject is never captured, recorded, or transmitted.
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  /**
   * Attach the camera stream to the preview video element.
   * Reuses an existing srcObject if present; otherwise requests
   * a new stream (camera permission should already be granted
   * by the emotion engine's earlier getUserMedia call).
   */
  function _attachPreviewStream() {
    var video = document.getElementById("lv74-cam-video");
    if (!video) return;
    if (video.srcObject) return;

    // Try to reuse the emotion engine's existing stream first
    var emotionVideo = document.querySelector("video[playsinline]");
    if (emotionVideo && emotionVideo.srcObject) {
      video.srcObject = emotionVideo.srcObject;
      return;
    }

    // Fallback: request own stream (permission already granted)
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      .then(function (stream) { video.srcObject = stream; })
      .catch(function (err) {
        console.warn("[lv74] Camera preview stream error:", err.message);
      });
  }

  /**
   * Show (or create) the draggable camera preview overlay.
   * Called from beginCameraConsent74() via window.lv74.showCameraPreview().
   */
  function showCameraPreview() {
    // If preview already exists, just unhide it
    if (document.getElementById("lv74-cam-preview")) {
      document.getElementById("lv74-cam-preview").classList.remove("lv74-preview-hidden");
      var reopenEl = document.getElementById("lv74-cam-reopen");
      if (reopenEl) reopenEl.classList.remove("lv74-reopen-visible");
      _attachPreviewStream();
      return;
    }

    // ── Create preview DOM ──────────────────────────────────────
    var preview = document.createElement("div");
    preview.id = "lv74-cam-preview";
    preview.innerHTML =
      '<div id="lv74-cam-preview-bar">' +
        '<span>Camera preview</span>' +
        '<button id="lv74-cam-close" title="Hide preview (camera keeps running)">&#10005;</button>' +
      '</div>' +
      '<video id="lv74-cam-video" autoplay playsinline muted></video>';
    document.body.appendChild(preview);

    // ── Create reopen pill ──────────────────────────────────────
    var reopen = document.createElement("div");
    reopen.id = "lv74-cam-reopen";
    reopen.title = "Show camera preview";
    reopen.innerHTML = "<span>Camera</span>";
    document.body.appendChild(reopen);

    // ── Close / reopen handlers ─────────────────────────────────
    document.getElementById("lv74-cam-close").addEventListener("click", function (e) {
      e.stopPropagation();
      preview.classList.add("lv74-preview-hidden");
      reopen.classList.add("lv74-reopen-visible");
    });

    reopen.addEventListener("click", function () {
      preview.classList.remove("lv74-preview-hidden");
      reopen.classList.remove("lv74-reopen-visible");
    });

    // ── Drag support ────────────────────────────────────────────
    var dragging = false, ox = 0, oy = 0;

    preview.addEventListener("mousedown", function (e) {
      if (e.target.id === "lv74-cam-close") return;
      dragging = true;
      var r = preview.getBoundingClientRect();
      preview.style.left = r.left + "px";
      preview.style.top = r.top + "px";
      preview.style.transform = "none";
      ox = e.clientX - r.left;
      oy = e.clientY - r.top;
      e.preventDefault();
    });

    document.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      preview.style.left = (e.clientX - ox) + "px";
      preview.style.top = (e.clientY - oy) + "px";
    });

    document.addEventListener("mouseup", function () { dragging = false; });

    // ── Attach camera stream ────────────────────────────────────
    _attachPreviewStream();
  }

  // ── Expose on window.lv74 ───────────────────────────────────
  window.lv74 = window.lv74 || {};
  window.lv74.showCameraPreview = showCameraPreview;

})();
