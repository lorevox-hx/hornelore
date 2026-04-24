/* ═══════════════════════════════════════════════════════════════
   ui-health-check.js — Operator UI Health Check (WO-UI-TEST-LAB-01)

   Scripted in-browser preflight harness that lives inside the
   existing #lv10dBugPanel.  Ten categories of checks, each reporting
   PASS / WARN / FAIL / DISABLED / SKIP with a short detail string.

   Hard rules (locked at WO time):
     1. Tests are PURE OBSERVATIONS.  Never mutate state, never fire
        a real narrator switch, never POST a write to the archive.
        Operator running this mid-session must not break the session.
     2. Total runtime budget for runAll() < 3 seconds.  Async fetches
        use a 2s per-request timeout.
     3. DISABLED and SKIP are first-class statuses.  Photos disabled
        via flag → DISABLED, not FAIL.  Archive write checks with no
        active narrator → SKIP, not FAIL.
     4. No "Fix it" buttons.  Harness's job is to TELL the truth;
        fixing is human-in-the-loop.

   Load order: AFTER app.js (depends on state.* globals + lv80_/lv10d_
   functions + window.FacialConsent + window.lvShellShowTab).
═══════════════════════════════════════════════════════════════ */

window.lvUiHealthCheck = (function () {
  "use strict";

  // ── Status enums + categories ──────────────────────────────────
  const STATUS = Object.freeze({
    PASS:          "PASS",
    WARN:          "WARN",
    FAIL:          "FAIL",
    DISABLED:      "DISABLED",      // feature flag off
    NOT_INSTALLED: "NOT_INSTALLED", // route literally returns 404 (router not mounted)
    SKIP:          "SKIP",          // prerequisite missing (e.g. no narrator selected)
    INFO:          "INFO",          // recorded but doesn't count as pass/fail
  });

  // Map status → CSS class re-using existing .lv10d-bp-value classes.
  const _CSS = {
    PASS:          "ok",
    WARN:          "warn",
    FAIL:          "err",
    DISABLED:      "off",
    NOT_INSTALLED: "off",
    SKIP:          "off",
    INFO:          "off",
  };

  // Category keys + human-readable labels + check functions.
  // Order = display order.
  const _CATEGORIES = [
    { key: "startup",    label: "Startup",             fn: _check_startup        },
    { key: "operator",   label: "Operator Tab",        fn: _check_operator_tab   },
    { key: "switch",     label: "Narrator Switch",     fn: _check_narrator_switch},
    { key: "camera",     label: "Camera Consent",      fn: _check_camera_consent },
    { key: "mic",        label: "Mic / STT",           fn: _check_mic_stt        },
    { key: "scroll",     label: "Chat Scroll",         fn: _check_chat_scroll    },
    { key: "river",      label: "Memory River",        fn: _check_memory_river   },
    { key: "map",        label: "Life Map",            fn: _check_life_map       },
    { key: "memoir",     label: "Peek at Memoir",      fn: _check_peek_memoir    },
    { key: "media",      label: "Media Tab",           fn: _check_media_tab      },
    { key: "photos",     label: "Photos",              fn: _check_photos         },
    { key: "archive",    label: "Archive",             fn: _check_archive        },
    { key: "navigation", label: "Navigation Recovery", fn: _check_navigation     },
    { key: "self",       label: "Harness Self-Check",  fn: _check_self           },
  ];

  // ── Internal state ─────────────────────────────────────────────
  const _state = {
    running: false,
    results: [],     // [{ category, name, status, detail }]
    lastRunTs: null,
    lastDurationMs: null,
  };

  // ── Helpers ────────────────────────────────────────────────────
  function _push(category, name, status, detail) {
    _state.results.push({
      category,
      name,
      status,
      detail: detail || "",
    });
  }

  async function _fetchJSON(url, timeoutMs) {
    timeoutMs = timeoutMs || 2000;
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: ctl.signal });
      let body = null;
      try { body = await res.json(); } catch (_) { body = null; }
      return { ok: res.ok, status: res.status, body };
    } catch (e) {
      return { ok: false, status: 0, body: null, error: e && e.message || String(e) };
    } finally {
      clearTimeout(t);
    }
  }

  function _hasNarrator() {
    return !!(typeof state !== "undefined" && state && state.person_id);
  }

  function _hasConvId() {
    return !!(typeof state !== "undefined" && state && state.chat && state.chat.conv_id);
  }

  function _readGlobal(name) {
    try { return (typeof window[name] !== "undefined") ? window[name] : undefined; }
    catch (_) { return undefined; }
  }

  // ── Category: Startup ──────────────────────────────────────────
  async function _check_startup() {
    const cat = "startup";

    // Shell tabs initialized
    const activeTab = document.querySelector("#lvShellTabs .lv-shell-tab-active");
    if (activeTab) {
      const t = activeTab.dataset.tab;
      const ok = ["operator", "narrator", "media"].includes(t);
      _push(cat, "shell tabs initialized",
        ok ? STATUS.PASS : STATUS.FAIL,
        `data-tab=${t}`);
    } else {
      _push(cat, "shell tabs initialized", STATUS.FAIL,
        "#lvShellTabs missing — WO-UI-SHELL-01 not loaded");
    }

    // Warmup banner state aligns with LLM readiness
    const banner = document.getElementById("lv80WarmupBanner");
    const llmReady = (typeof isLlmReady === "function") ? isLlmReady() : null;
    if (banner) {
      const hidden = banner.classList.contains("hidden");
      if (llmReady === true && hidden) {
        _push(cat, "warmup banner hidden when ready", STATUS.PASS, "LLM ready");
      } else if (llmReady === true && !hidden) {
        _push(cat, "warmup banner hidden when ready", STATUS.WARN,
          "LLM ready but banner still showing");
      } else if (llmReady === false) {
        _push(cat, "warmup banner hidden when ready", STATUS.WARN,
          "LLM not yet ready — banner expected visible");
      } else {
        _push(cat, "warmup banner hidden when ready", STATUS.WARN,
          "isLlmReady() unavailable");
      }
    } else {
      _push(cat, "warmup banner element present", STATUS.FAIL,
        "#lv80WarmupBanner missing");
    }

    // Active narrator card present
    const card = document.getElementById("lv80ActiveNarratorCard");
    _push(cat, "active narrator card present in header",
      card ? STATUS.PASS : STATUS.FAIL,
      card ? "" : "#lv80ActiveNarratorCard missing");

    // Operator-tab session style picker present
    const radios = document.querySelectorAll('input[name="lvSessionStyle"]');
    _push(cat, "session style picker has 5 options",
      radios.length === 5 ? STATUS.PASS : STATUS.FAIL,
      `radio count=${radios.length}`);

    // No stale narrator pointer
    const saved = localStorage.getItem("lv_active_person_v55");
    const cache = (state && state.narratorUi && state.narratorUi.peopleCache) || [];
    if (saved) {
      const ids = cache.map(p => p.id || p.person_id);
      _push(cat, "active narrator pointer not stale",
        ids.includes(saved) ? STATUS.PASS : STATUS.WARN,
        ids.includes(saved) ? `saved=${saved.slice(0,8)}` : `saved=${saved.slice(0,8)} not in cache (${ids.length} narrators)`);
    } else {
      _push(cat, "active narrator pointer not stale", STATUS.PASS,
        "no saved pointer (clean state)");
    }
  }

  // ── Category: Operator Tab ─────────────────────────────────────
  // Verifies the Operator surface that gates every session: readiness card,
  // session-style picker (5 radios), Start button, Photo Session button,
  // and the launcher grid that was moved out of the header by WO-UI-SHELL-01.
  async function _check_operator_tab() {
    const cat = "operator";

    // Operator tab DOM exists
    const tab = document.getElementById("lvOperatorTab");
    _push(cat, "Operator tab panel present",
      tab ? STATUS.PASS : STATUS.FAIL,
      tab ? "" : "#lvOperatorTab missing — WO-UI-SHELL-01 broken");

    // Readiness card exists + is in a known state
    const ready = document.getElementById("lvOperatorReadiness");
    if (ready) {
      const ds = ready.getAttribute("data-ready") || "(none)";
      const known = ["ready","pending","error"].includes(ds);
      _push(cat, "Readiness card state is known",
        known ? STATUS.PASS : STATUS.WARN,
        `data-ready=${ds}`);
    } else {
      _push(cat, "Readiness card present", STATUS.FAIL,
        "#lvOperatorReadiness missing");
    }

    // Start Narrator Session button
    const startBtn = document.getElementById("lvOperatorStartBtn");
    if (startBtn) {
      const disabled = startBtn.disabled;
      _push(cat, "Start Narrator Session button present", STATUS.PASS,
        disabled ? "disabled (waiting for narrator + ready)" : "enabled");
    } else {
      _push(cat, "Start Narrator Session button present", STATUS.FAIL,
        "#lvOperatorStartBtn missing");
    }

    // Photo Session button
    const photoBtn = document.getElementById("lvOperatorPhotoBtn");
    _push(cat, "Start Photo Session button present",
      photoBtn ? STATUS.PASS : STATUS.FAIL,
      photoBtn ? "" : "#lvOperatorPhotoBtn missing");

    // 5 session style radios with the expected values
    const expectedStyles = ["questionnaire_first","clear_direct","warm_storytelling","memory_exercise","companion"];
    const radios = Array.from(document.querySelectorAll('input[name="lvSessionStyle"]'));
    if (radios.length === 5) {
      const present = radios.map(r => r.value).sort();
      const want = expectedStyles.slice().sort();
      const match = present.length === want.length && present.every((v,i) => v === want[i]);
      _push(cat, "Session style picker has all 5 expected styles",
        match ? STATUS.PASS : STATUS.WARN,
        match ? "" : `present=${present.join(",")}`);
    } else {
      _push(cat, "Session style picker has all 5 expected styles", STATUS.FAIL,
        `radio count=${radios.length} (expected 5)`);
    }

    // Operator launcher grid populated (popovers moved out of header)
    const launchers = [
      "lv80BioBuilderBtn", "lv80LifeMapBtn", "lv80RiverBtn", "lv80PeekBtn",
      "wo10TranscriptBtn", "wo13ReviewBtn", "lv10dBugBtn",
    ];
    const found = launchers.filter(id => document.getElementById(id));
    _push(cat, "Operator launcher grid populated",
      found.length === launchers.length ? STATUS.PASS : STATUS.WARN,
      `${found.length}/${launchers.length} launchers found`);
  }

  // ── Category: Narrator Switch ──────────────────────────────────
  async function _check_narrator_switch() {
    const cat = "switch";

    // Narrator switcher popover present
    const sw = document.getElementById("lv80NarratorSwitcher");
    _push(cat, "narrator switcher popover present",
      sw ? STATUS.PASS : STATUS.FAIL,
      sw ? "" : "#lv80NarratorSwitcher missing");

    // Narrator list populated
    const list = document.getElementById("lv80NarratorList");
    if (list) {
      const n = list.children.length;
      _push(cat, "narrator switcher list populated",
        n > 0 ? STATUS.PASS : STATUS.WARN,
        `${n} narrators`);
    } else {
      _push(cat, "narrator switcher list populated", STATUS.FAIL,
        "#lv80NarratorList missing");
    }

    // sessionStyle is one of 5 valid values
    const validStyles = [
      "questionnaire_first", "clear_direct", "warm_storytelling",
      "memory_exercise", "companion",
    ];
    const ss = state && state.session && state.session.sessionStyle;
    _push(cat, "state.session.sessionStyle is valid",
      validStyles.includes(ss) ? STATUS.PASS : STATUS.FAIL,
      `value=${JSON.stringify(ss)}`);

    // sessionStyle persistence (in-memory matches localStorage on load)
    const lsStyle = localStorage.getItem("hornelore_session_style_v1");
    if (lsStyle) {
      _push(cat, "sessionStyle in-memory matches localStorage",
        lsStyle === ss ? STATUS.PASS : STATUS.WARN,
        `localStorage=${lsStyle} vs state=${ss}`);
    } else {
      _push(cat, "sessionStyle in-memory matches localStorage", STATUS.PASS,
        "no localStorage value (default applied)");
    }

    // Active narrator (informational)
    if (_hasNarrator()) {
      const name = document.getElementById("lv80ActiveNarratorName");
      _push(cat, "active narrator selected", STATUS.INFO,
        `${(name && name.textContent) || "—"} (${state.person_id.slice(0,8)})`);
    } else {
      _push(cat, "active narrator selected", STATUS.INFO,
        "no narrator selected");
    }
  }

  // ── Category: Camera Consent ───────────────────────────────────
  async function _check_camera_consent() {
    const cat = "camera";

    // FacialConsent loaded
    if (typeof window.FacialConsent !== "object" || window.FacialConsent === null) {
      _push(cat, "FacialConsent global loaded", STATUS.FAIL,
        "facial-consent.js not loaded — camera consent flow broken");
      return;
    }
    _push(cat, "FacialConsent global loaded", STATUS.PASS, "");

    // Consent recorded (informational)
    const granted = window.FacialConsent.isGranted();
    const declined = window.FacialConsent.isDeclined();
    _push(cat, "FacialConsent state",
      STATUS.INFO,
      `isGranted=${granted} isDeclined=${declined}`);

    // localStorage matches in-memory
    const lsConsent = localStorage.getItem("lorevox_facial_consent_granted");
    const lsBool = lsConsent === "true";
    if (lsConsent === null) {
      _push(cat, "consent localStorage matches in-memory",
        granted ? STATUS.WARN : STATUS.PASS,
        granted ? "in-memory granted but no localStorage value" : "no stored consent (clean state)");
    } else {
      _push(cat, "consent localStorage matches in-memory",
        lsBool === granted ? STATUS.PASS : STATUS.WARN,
        `ls=${lsConsent} memory=${granted}`);
    }

    // cameraActive global aligned with state.inputState.cameraActive
    const camGlobal = (typeof cameraActive !== "undefined") ? !!cameraActive : null;
    const camState = !!(state && state.inputState && state.inputState.cameraActive);
    if (camGlobal === null) {
      _push(cat, "cameraActive global ↔ state.inputState alignment", STATUS.WARN,
        "cameraActive global undefined");
    } else {
      _push(cat, "cameraActive global ↔ state.inputState alignment",
        camGlobal === camState ? STATUS.PASS : STATUS.FAIL,
        `global=${camGlobal} state=${camState}`);
    }

    // Critical: if camera is on, preview must be live (catches #145/#175/#190)
    if (camGlobal === true) {
      const preview = document.getElementById("lv74-cam-preview");
      const video   = document.getElementById("lv74-cam-video");
      const tracksLive = (() => {
        if (!video || !video.srcObject) return 0;
        try {
          return video.srcObject.getTracks().filter(t => t.readyState === "live").length;
        } catch (_) { return 0; }
      })();
      if (!preview) {
        _push(cat, "camera on → preview present", STATUS.FAIL,
          "cameraActive=true but #lv74-cam-preview missing — call window.lv74.showCameraPreview()");
      } else if (tracksLive < 1) {
        _push(cat, "camera on → preview has live track", STATUS.FAIL,
          `preview present but tracksLive=${tracksLive} — stream died, call stopEmotionEngine() then re-toggle`);
      } else {
        _push(cat, "camera on → preview has live track", STATUS.PASS,
          `tracksLive=${tracksLive}`);
      }
    } else {
      _push(cat, "camera on → preview has live track", STATUS.SKIP,
        "camera off (nothing to verify)");
    }

    // Auto-start one-shot flag is sane
    const autoFlag = window._lv80CamAutoStartedThisPageSession;
    if (typeof autoFlag === "undefined") {
      _push(cat, "auto-start one-shot flag",
        STATUS.INFO,
        "undefined (no narrator load yet this session)");
    } else {
      _push(cat, "auto-start one-shot flag", STATUS.INFO,
        `_lv80CamAutoStartedThisPageSession=${autoFlag}`);
    }
  }

  // ── Category: Mic / STT ────────────────────────────────────────
  async function _check_mic_stt() {
    const cat = "mic";

    // Web Speech API availability
    const speechApi = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    if (speechApi) {
      _push(cat, "Web Speech API available", STATUS.PASS,
        "browser STT path enabled");
    } else {
      _push(cat, "Web Speech API available", STATUS.WARN,
        "browser doesn't support Web Speech — typed fallback only");
    }

    // recognition global initialized (only after first mic toggle, so OK to be null pre-toggle)
    const rec = (typeof recognition !== "undefined") ? recognition : undefined;
    if (rec === null) {
      _push(cat, "recognition object initialized", STATUS.PASS,
        "null (initializes on first mic toggle)");
    } else if (rec === undefined) {
      _push(cat, "recognition object initialized", STATUS.WARN,
        "global undefined — STT module not loaded");
    } else {
      _push(cat, "recognition object initialized", STATUS.PASS,
        "recognition instance present");
    }

    // Mic button visual matches state.inputState
    const micBtn = document.getElementById("lv10dMicBtn");
    const micState = !!(state && state.inputState && state.inputState.micActive);
    if (micBtn) {
      const visual = micBtn.getAttribute("data-on") === "true";
      _push(cat, "mic button visual ↔ state.inputState",
        visual === micState ? STATUS.PASS : STATUS.WARN,
        `visual=${visual} state=${micState}`);
    } else {
      _push(cat, "mic button visual ↔ state.inputState", STATUS.WARN,
        "#lv10dMicBtn not present");
    }

    // listeningPaused is bool
    const lp = (typeof listeningPaused !== "undefined") ? listeningPaused : null;
    _push(cat, "listeningPaused state",
      typeof lp === "boolean" ? STATUS.PASS : STATUS.WARN,
      `value=${lp}`);

    // Hands-free scaffolding (state fields from WO-NARRATOR-ROOM-01)
    const hfFields = state && state.session && {
      handsFree: state.session.handsFree,
      micAutoRearm: state.session.micAutoRearm,
      loriSpeaking: state.session.loriSpeaking,
    };
    if (hfFields) {
      const allBool = ["handsFree","micAutoRearm","loriSpeaking"]
        .every(k => typeof hfFields[k] === "boolean");
      _push(cat, "hands-free state fields scaffolded",
        allBool ? STATUS.PASS : STATUS.WARN,
        JSON.stringify(hfFields));
    }
  }

  // ── Category: Chat Scroll ──────────────────────────────────────
  async function _check_chat_scroll() {
    const cat = "scroll";

    const inner = document.getElementById("crChatInner");
    if (!inner) {
      _push(cat, "#crChatInner scroll container present", STATUS.FAIL,
        "missing — narrator-room conversation column broken");
    } else {
      _push(cat, "#crChatInner scroll container present", STATUS.PASS, "");
      const ov = getComputedStyle(inner).overflowY;
      _push(cat, "#crChatInner overflow-y=auto",
        ov === "auto" ? STATUS.PASS : STATUS.WARN,
        `overflow-y=${ov}`);
    }

    // FocusCanvas scroll plumbing exposed
    const sclGlobal = typeof window._scrollToLatest;
    _push(cat, "window._scrollToLatest defined",
      sclGlobal === "function" ? STATUS.PASS : STATUS.FAIL,
      `typeof=${sclGlobal} (FocusCanvas scroll plumbing)`);

    // See New Message button present
    const seeNew = document.getElementById("seeNewMsgBtn");
    _push(cat, "#seeNewMsgBtn present",
      seeNew ? STATUS.PASS : STATUS.FAIL,
      seeNew ? "" : "missing — narrators won't see scroll-up new-message indicator");

    // chatMessages padding-bottom keeps last message clear of footer
    const chat = document.getElementById("chatMessages");
    if (chat) {
      const pb = parseInt(getComputedStyle(chat).paddingBottom, 10) || 0;
      _push(cat, "#chatMessages padding-bottom ≥ 100px",
        pb >= 100 ? STATUS.PASS : STATUS.WARN,
        `padding-bottom=${pb}px (footer-clear guarantee)`);
    } else {
      _push(cat, "#chatMessages present", STATUS.FAIL,
        "missing — chat bubble append target gone");
    }

    // lvNarratorScroll wrappers from WO-NARRATOR-ROOM-01
    _push(cat, "lvNarratorScrollToBottom wrapper",
      typeof window.lvNarratorScrollToBottom === "function" ? STATUS.PASS : STATUS.WARN,
      `typeof=${typeof window.lvNarratorScrollToBottom}`);
  }

  // ── Category: Memory River ─────────────────────────────────────
  async function _check_memory_river() {
    const cat = "river";

    const pop = document.getElementById("kawaRiverPopover");
    _push(cat, "Memory River popover present",
      pop ? STATUS.PASS : STATUS.FAIL,
      pop ? "" : "#kawaRiverPopover missing");

    const tab = document.querySelector('.lv-narrator-view-tab[data-view="river"]');
    _push(cat, "narrator-room Memory River view tab present",
      tab ? STATUS.PASS : STATUS.FAIL,
      tab ? "" : "narrator room missing river tab — WO-NARRATOR-ROOM-01 broken");

    const showFn = typeof window.lvNarratorShowView;
    _push(cat, "lvNarratorShowView available",
      showFn === "function" ? STATUS.PASS : STATUS.FAIL,
      `typeof=${showFn}`);

    const kawa = state && state.kawa;
    _push(cat, "state.kawa.segmentList array present",
      kawa && Array.isArray(kawa.segmentList) ? STATUS.PASS : STATUS.WARN,
      kawa ? `count=${(kawa.segmentList || []).length}` : "state.kawa missing");
  }

  // ── Category: Life Map ─────────────────────────────────────────
  async function _check_life_map() {
    const cat = "map";

    const pop = document.getElementById("lifeMapPopover");
    _push(cat, "Life Map popover present",
      pop ? STATUS.PASS : STATUS.FAIL,
      pop ? "" : "#lifeMapPopover missing");

    const tab = document.querySelector('.lv-narrator-view-tab[data-view="map"]');
    _push(cat, "narrator-room Life Map view tab present",
      tab ? STATUS.PASS : STATUS.FAIL, "");

    const launcher = document.getElementById("lv80LifeMapBtn");
    _push(cat, "operator launcher #lv80LifeMapBtn present",
      launcher ? STATUS.PASS : STATUS.FAIL, "");
  }

  // ── Category: Peek at Memoir ───────────────────────────────────
  async function _check_peek_memoir() {
    const cat = "memoir";

    const pop = document.getElementById("memoirScrollPopover");
    _push(cat, "Peek at Memoir popover present",
      pop ? STATUS.PASS : STATUS.FAIL,
      pop ? "" : "#memoirScrollPopover missing");

    const tab = document.querySelector('.lv-narrator-view-tab[data-view="memoir"]');
    _push(cat, "narrator-room Peek view tab present",
      tab ? STATUS.PASS : STATUS.FAIL, "");

    const launcher = document.getElementById("lv80PeekBtn");
    _push(cat, "operator launcher #lv80PeekBtn present",
      launcher ? STATUS.PASS : STATUS.FAIL, "");
  }

  // ── Category: Media Tab ────────────────────────────────────────
  // Verifies the Media tab + 3 launcher cards + the disabled-note state
  // matches the actual /api/photos/health response (catches the WO-UI-SHELL-01
  // class of bug where the note shows "enabled" while the flag is off).
  async function _check_media_tab() {
    const cat = "media";

    const tab = document.getElementById("lvMediaTab");
    _push(cat, "Media tab panel present",
      tab ? STATUS.PASS : STATUS.FAIL,
      tab ? "" : "#lvMediaTab missing — WO-UI-SHELL-01 broken");

    const tabBtn = document.getElementById("lvShellTabMedia");
    _push(cat, "Media tab nav button present",
      tabBtn ? STATUS.PASS : STATUS.FAIL,
      tabBtn ? "" : "#lvShellTabMedia missing");

    const cards = document.querySelectorAll(".lv-media-launch-card");
    _push(cat, "Media launcher cards present (3)",
      cards.length === 3 ? STATUS.PASS : STATUS.FAIL,
      `count=${cards.length}`);

    // Disabled-note state matches the photo health flag.  This is exactly
    // the regression the WO-UI-SHELL-01 preflight had — note showing
    // "enabled" because /api/photos returned 422 (route registered but
    // narrator_id missing) instead of 404.
    const note = document.getElementById("lvMediaDisabledNote");
    if (note) {
      const noteHidden = note.hidden;
      const h = await _fetchJSON("/api/photos/health");
      if (h.ok && h.body) {
        const featureOn = !!h.body.enabled;
        const expectHidden = featureOn;
        if (expectHidden === noteHidden) {
          _push(cat, "Disabled note state matches photo flag", STATUS.PASS,
            `note hidden=${noteHidden} flag enabled=${featureOn}`);
        } else {
          _push(cat, "Disabled note state matches photo flag", STATUS.WARN,
            `note hidden=${noteHidden} but flag enabled=${featureOn} — preflight stale until Media tab opened`);
        }
      } else {
        _push(cat, "Disabled note state matches photo flag", STATUS.SKIP,
          "could not reach /api/photos/health");
      }
    } else {
      _push(cat, "Disabled note element present", STATUS.WARN,
        "#lvMediaDisabledNote missing");
    }
  }

  // ── Category: Photos ───────────────────────────────────────────
  async function _check_photos() {
    const cat = "photos";

    const h = await _fetchJSON("/api/photos/health");
    if (h.status === 404) {
      _push(cat, "/api/photos/health installed", STATUS.NOT_INSTALLED,
        "router not mounted in main.py");
      return;
    }
    if (!h.ok || !h.body) {
      _push(cat, "/api/photos/health reachable", STATUS.FAIL,
        `status=${h.status} ${h.error || ""}`);
      return;
    }
    _push(cat, "/api/photos/health reachable", STATUS.PASS,
      `enabled=${h.body.enabled}`);

    if (!h.body.enabled) {
      _push(cat, "photo feature enabled", STATUS.DISABLED,
        "set HORNELORE_PHOTO_ENABLED=1 in .env + restart stack to use photo features");
      return;
    }
    _push(cat, "photo feature enabled", STATUS.PASS, "");

    if (!_hasNarrator()) {
      _push(cat, "narrator photo list reachable", STATUS.SKIP,
        "no narrator selected");
      return;
    }
    const list = await _fetchJSON(`/api/photos?narrator_id=${encodeURIComponent(state.person_id)}`);
    if (list.ok && list.body) {
      const n = (list.body.photos || []).length;
      _push(cat, "narrator photo list reachable", STATUS.PASS,
        `${n} photo(s) for ${state.person_id.slice(0,8)}`);
    } else {
      _push(cat, "narrator photo list reachable", STATUS.WARN,
        `status=${list.status} ${list.error || ""}`);
    }
  }

  // ── Category: Archive ──────────────────────────────────────────
  // Pure observation only — read /health + read existing session if any.
  // Write tests live in scripts/run_memory_archive_smoke.py.
  async function _check_archive() {
    const cat = "archive";

    const h = await _fetchJSON("/api/memory-archive/health");
    if (h.status === 404) {
      _push(cat, "/api/memory-archive/health installed", STATUS.NOT_INSTALLED,
        "router not mounted — WO-ARCHIVE-AUDIO-01 not deployed on this stack");
      return;
    }
    if (!h.ok || !h.body) {
      _push(cat, "/api/memory-archive/health reachable", STATUS.FAIL,
        `status=${h.status} ${h.error || ""}`);
      return;
    }
    _push(cat, "/api/memory-archive/health reachable", STATUS.PASS,
      `enabled=${h.body.enabled} cap=${h.body.max_mb_per_person}MB`);

    if (!h.body.enabled) {
      _push(cat, "archive feature enabled", STATUS.DISABLED,
        "set HORNELORE_ARCHIVE_ENABLED=1 in .env + restart stack");
      return;
    }
    _push(cat, "archive feature enabled", STATUS.PASS, "");

    if (!_hasNarrator()) {
      _push(cat, "active narrator for archive session", STATUS.SKIP,
        "no narrator selected");
      return;
    }
    if (!_hasConvId()) {
      _push(cat, "conv_id available for archive session", STATUS.SKIP,
        "no chat conv_id yet (start a chat to materialize)");
      return;
    }
    _push(cat, "active narrator + conv_id present", STATUS.PASS,
      `pid=${state.person_id.slice(0,8)} conv=${state.chat.conv_id.slice(0,8)}`);

    // Read-only probe — 200 means archive exists, 404 means not yet created (both fine)
    const sess = await _fetchJSON(
      `/api/memory-archive/session/${encodeURIComponent(state.chat.conv_id)}` +
      `?person_id=${encodeURIComponent(state.person_id)}`,
    );
    if (sess.status === 200) {
      const turns = (sess.body && sess.body.turns) || [];
      const audioLost = turns.filter(t => t.audio_lost === true).length;
      _push(cat, "archive session readable",
        STATUS.PASS,
        `${turns.length} turn(s)${audioLost ? `, ${audioLost} audio_lost` : ""}`);
    } else if (sess.status === 404) {
      _push(cat, "archive session readable", STATUS.PASS,
        "no archive session yet (created lazily on first turn)");
    } else {
      _push(cat, "archive session readable", STATUS.WARN,
        `status=${sess.status} ${sess.error || ""}`);
    }
  }

  // ── Category: Navigation Recovery ──────────────────────────────
  // Catches stranded-UI bug class:
  //   - shell tab attribute drifted to an invalid value
  //   - app shell unmounted (operator stuck at blank page)
  //   - multiple popovers open simultaneously (light-dismiss broken)
  //   - lvShellShowTab function gone (no way out of any tab)
  async function _check_navigation() {
    const cat = "navigation";

    // App shell still mounted
    const shell = document.getElementById("lv80Shell");
    _push(cat, "App shell mounted",
      shell ? STATUS.PASS : STATUS.FAIL,
      shell ? "" : "#lv80Shell missing — operator is stranded on a blank page");

    // body[data-shell-tab] is a known value
    const bodyTab = document.body && document.body.getAttribute("data-shell-tab");
    const valid = ["operator", "narrator", "media"];
    _push(cat, "body[data-shell-tab] is valid",
      valid.includes(bodyTab) ? STATUS.PASS : STATUS.WARN,
      `value=${bodyTab || "(unset)"}`);

    // Tab switcher function present
    _push(cat, "lvShellShowTab() available for tab navigation",
      typeof window.lvShellShowTab === "function" ? STATUS.PASS : STATUS.FAIL,
      typeof window.lvShellShowTab === "function" ? "" :
        "no way to switch tabs — operator stranded on whichever panel is active");

    // Currently-open popovers count.  More than one open simultaneously
    // is suspicious — Hornelore uses popover="auto" with light-dismiss,
    // so usually only one is open at a time.
    let openPopovers = [];
    try {
      const all = document.querySelectorAll('[popover]');
      all.forEach(el => {
        if (el.matches && el.matches(":popover-open")) {
          openPopovers.push(el.id || el.tagName);
        }
      });
    } catch (_) { /* :popover-open unsupported in old browsers */ }
    if (openPopovers.length === 0) {
      _push(cat, "popover state clean (no stuck overlays)", STATUS.PASS, "0 open");
    } else if (openPopovers.length === 1) {
      _push(cat, "popover state clean (no stuck overlays)", STATUS.PASS,
        `1 open (${openPopovers[0]}) — fine, light-dismiss available`);
    } else {
      _push(cat, "popover state clean (no stuck overlays)", STATUS.WARN,
        `${openPopovers.length} popovers open simultaneously: ${openPopovers.join(", ")}`);
    }

    // Take-a-break overlay state.  If hidden=false but break isn't active,
    // operator is stranded.
    const breakOverlay = document.getElementById("lvNarratorBreakOverlay");
    const breakActive  = !!(state && state.session && state.session.breakActive);
    if (breakOverlay) {
      const overlayShown = breakOverlay.hidden === false;
      if (overlayShown && !breakActive) {
        _push(cat, "Take-a-break overlay state aligned", STATUS.FAIL,
          "overlay is shown but state.session.breakActive=false — narrator stranded behind overlay");
      } else if (!overlayShown && breakActive) {
        _push(cat, "Take-a-break overlay state aligned", STATUS.WARN,
          "state.session.breakActive=true but overlay hidden — break button visual will mislead operator");
      } else {
        _push(cat, "Take-a-break overlay state aligned", STATUS.PASS,
          `overlay shown=${overlayShown} breakActive=${breakActive}`);
      }
    } else {
      _push(cat, "Take-a-break overlay element present", STATUS.WARN,
        "#lvNarratorBreakOverlay missing — narrator can't take a break");
    }
  }

  // ── Category: Harness Self-Check ───────────────────────────────
  // Confirms the harness itself is meeting its own contract.  Runs LAST
  // so it can observe its own runtime.
  async function _check_self() {
    const cat = "self";

    _push(cat, "harness loaded", STATUS.PASS,
      `window.lvUiHealthCheck (${Object.keys(window.lvUiHealthCheck).length} methods)`);

    // Runtime budget — stamped at the moment this check runs (NOT the final
    // total).  We approximate via the elapsed time since runStartTs which
    // runAll/runCategory set on _state.  Final stamp is in the topline.
    if (_state.runStartTs != null) {
      const elapsed = Math.round(((typeof performance !== "undefined") ? performance.now() : Date.now()) - _state.runStartTs);
      _push(cat, "runtime budget so far",
        elapsed < 3000 ? STATUS.PASS : STATUS.WARN,
        `${elapsed}ms (budget 3000ms)`);
    } else {
      _push(cat, "runtime budget so far", STATUS.SKIP, "runStartTs unset");
    }

    // Status enum vocabulary completeness — defensive check that all
    // statuses we use have a CSS class mapped.
    const used = new Set(_state.results.map(r => r.status));
    const unmapped = Array.from(used).filter(s => !_CSS[s]);
    _push(cat, "status enum has CSS mapping for every emitted status",
      unmapped.length === 0 ? STATUS.PASS : STATUS.WARN,
      unmapped.length === 0 ? `${used.size} status values seen` :
        `unmapped: ${unmapped.join(",")}`);
  }

  // ── Public API ─────────────────────────────────────────────────

  async function runAll() {
    if (_state.running) return;
    _state.running = true;
    _state.results = [];
    const t0 = (typeof performance !== "undefined") ? performance.now() : Date.now();
    _state.runStartTs = t0;
    try {
      for (const c of _CATEGORIES) {
        try { await c.fn(); }
        catch (e) {
          _push(c.key, "category check threw", STATUS.FAIL,
            `${e && e.name}: ${e && e.message || e}`);
        }
      }
    } finally {
      const t1 = (typeof performance !== "undefined") ? performance.now() : Date.now();
      _state.lastDurationMs = Math.round(t1 - t0);
      _state.lastRunTs = new Date().toISOString();
      _state.running = false;
      _render();
    }
    return _state.results.slice();
  }

  async function runCategory(catKey) {
    if (_state.running) return;
    const c = _CATEGORIES.find(x => x.key === catKey);
    if (!c) {
      console.warn("[ui-health-check] unknown category:", catKey);
      return;
    }
    _state.running = true;
    _state.results = [];
    const t0 = (typeof performance !== "undefined") ? performance.now() : Date.now();
    _state.runStartTs = t0;
    try { await c.fn(); }
    catch (e) {
      _push(c.key, "category check threw", STATUS.FAIL,
        `${e && e.name}: ${e && e.message || e}`);
    } finally {
      const t1 = (typeof performance !== "undefined") ? performance.now() : Date.now();
      _state.lastDurationMs = Math.round(t1 - t0);
      _state.lastRunTs = new Date().toISOString();
      _state.running = false;
      _render();
    }
    return _state.results.slice();
  }

  function _summary() {
    const buckets = { PASS: 0, WARN: 0, FAIL: 0, DISABLED: 0, SKIP: 0, INFO: 0 };
    _state.results.forEach(r => { buckets[r.status] = (buckets[r.status] || 0) + 1; });
    return buckets;
  }

  function _render() {
    const host = document.getElementById("lv10dBpUiHealthResults");
    if (!host) return;
    if (!_state.results.length) {
      host.innerHTML = '<div class="lv10d-bp-test-empty">No results yet — click a Run button.</div>';
      return;
    }
    const sum = _summary();
    const lines = [];
    lines.push(
      `<div class="lv10d-bp-test-summary">` +
      `<span class="lv10d-bp-value ok">${sum.PASS} PASS</span> · ` +
      `<span class="lv10d-bp-value warn">${sum.WARN} WARN</span> · ` +
      `<span class="lv10d-bp-value err">${sum.FAIL} FAIL</span> · ` +
      `<span class="lv10d-bp-value off">${sum.DISABLED} DISABLED</span> · ` +
      `<span class="lv10d-bp-value off">${sum.SKIP} SKIP</span>` +
      (sum.INFO ? ` · <span class="lv10d-bp-value off">${sum.INFO} INFO</span>` : "") +
      ` · <span class="lv10d-bp-test-duration">${_state.lastDurationMs}ms</span>` +
      `</div>`
    );

    // Group by category in display order.
    for (const c of _CATEGORIES) {
      const rows = _state.results.filter(r => r.category === c.key);
      if (!rows.length) continue;
      lines.push(`<div class="lv10d-bp-test-group-title">${c.label}</div>`);
      for (const r of rows) {
        const cls = _CSS[r.status] || "off";
        lines.push(
          `<div class="lv10d-bp-test-row">` +
          `<span class="lv10d-bp-value ${cls} lv10d-bp-test-status">${_escape(r.status)}</span>` +
          `<span class="lv10d-bp-test-name">${_escape(r.name)}</span>` +
          (r.detail
            ? `<span class="lv10d-bp-test-detail">${_escape(r.detail)}</span>`
            : ``) +
          `</div>`
        );
      }
    }
    host.innerHTML = lines.join("");
  }

  function _escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function copyReport() {
    const sum = _summary();
    const lines = [];
    lines.push(`Hornelore UI Health Check  ·  ${_state.lastRunTs || "(never run)"}`);
    lines.push("");
    lines.push(
      `Topline:  ${sum.PASS} PASS · ${sum.WARN} WARN · ${sum.FAIL} FAIL · ` +
      `${sum.DISABLED} DISABLED · ${sum.SKIP} SKIP · ${_state.lastDurationMs}ms`
    );
    lines.push("");
    for (const c of _CATEGORIES) {
      const rows = _state.results.filter(r => r.category === c.key);
      if (!rows.length) continue;
      lines.push(`[${c.label}]`);
      for (const r of rows) {
        const status = r.status.padEnd(8);
        lines.push(`  ${status}  ${r.name}` + (r.detail ? `   (${r.detail})` : ""));
      }
      lines.push("");
    }
    const text = lines.join("\n");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => _flashCopyOk(true))
        .catch(() => _flashCopyOk(false, text));
    } else {
      _flashCopyOk(false, text);
    }
  }

  function _flashCopyOk(ok, fallbackText) {
    const host = document.getElementById("lv10dBpUiHealthResults");
    if (!host) return;
    const note = document.createElement("div");
    note.className = "lv10d-bp-test-copy-note";
    note.textContent = ok ? "Report copied to clipboard." :
      "Clipboard not available — see console for full text.";
    if (!ok && fallbackText) console.log("[ui-health-check] report:\n" + fallbackText);
    host.prepend(note);
    setTimeout(() => { try { note.remove(); } catch (_) {} }, 2200);
  }

  return {
    runAll: runAll,
    runCategory: runCategory,
    copyReport: copyReport,
    lastResults: () => _state.results.slice(),
    lastDurationMs: () => _state.lastDurationMs,
    lastRunTs: () => _state.lastRunTs,
  };
})();

console.log("[Hornelore] UI Health Check loaded — open Bug Panel to run.");
