/* trainer-narrators.js — WO-11 Trainer Narrators
   WO-11 TRAINER MODE REPAIR:
     - Canonical style names: "structured" | "storyteller" (no more "story")
     - state.trainerNarrators is the single source of truth and now carries
       full trainer meta (style, title, promptHint, templateName)
     - start() accepts a meta object {style, title, promptHint, templateName}
       OR the legacy (personId, style) signature for back-compat
     - _steps() is style-aware: separate Shatner / Dolly example pairs
     - finish() captures meta locally BEFORE clearing active so the handoff
       receives the trainer flavor it needs
     - Exposes window.LorevoxTrainerNarrators

   WO-11B history kept: trainers remain UI-only launcher actions.
   They never create person records or bind narrator metadata via preload.
*/
(function () {
  "use strict";
  function _el(id) { return document.getElementById(id); }

  function _ensureTrainerState() {
    if (typeof state === "undefined") return null;
    if (!state.trainerNarrators) {
      state.trainerNarrators = {
        active: false,
        style: null,            // "structured" | "storyteller"
        title: null,
        promptHint: null,
        templateName: null,
        stepIndex: 0,
        completed: false,
        completedStyle: null
      };
    }
    return state.trainerNarrators;
  }

  function _normalizeStyle(s) {
    // Canonical pair: structured | storyteller.
    // Legacy "story" is mapped to "storyteller" so old call sites still work.
    if (s === "structured") return "structured";
    if (s === "storyteller" || s === "story") return "storyteller";
    return "structured";
  }

  function _reset() {
    var s = _ensureTrainerState();
    if (!s) return;
    s.active = false;
    s.style = null;
    s.title = null;
    s.promptHint = null;
    s.templateName = null;
    s.stepIndex = 0;
    s.completed = false;
    s.completedStyle = null;
    _renderPanel();
  }

  // WO-11: Style-aware step content. Both styles share the same three step
  // IDs (about_lorevox / how_lori_works / try_your_way) and the same visual
  // structure, but the simple/story example pairs are different so the
  // trainer actually demonstrates its style.
  function _steps(style) {
    var canonical = _normalizeStyle(style);
    if (canonical === "storyteller") {
      // Dolly trainer — warm, flowing storytelling examples
      return [
        {
          id: "about_lorevox",
          lori: [
            "Hi\u2026 I\u2019m Lori.",
            "I\u2019m here to help you tell your life story \u2014 the long way, with feeling and color.",
            "Lorevox is a place where memories can live, breathe, and turn into something whole.",
            "There are no right or wrong answers here \u2014 only the ones that matter to you.",
            "Even small moments can open into something much larger."
          ],
          question: "Let me show you what a storytelling answer can sound like.",
          simpleLabel: "Short answer",
          simple: "I was born in Locust Ridge, Tennessee.",
          storyLabel: "Storytelling answer",
          story: "I was born up in Locust Ridge, in a one-room cabin on the Little Pigeon River \u2014 my daddy paid the doctor with a sack of cornmeal, and the mountains that morning were blue and quiet, the way they always are when something new is just about to begin."
        },
        {
          id: "how_lori_works",
          lori: [
            "I usually ask one gentle question at a time.",
            "We move through your life slowly \u2014 and you\u2019re welcome to take the long way around.",
            "Tell me what you remember, the way you remember it. The wandering is where the gold is."
          ],
          question: "Here\u2019s how a name can become a story.",
          simpleLabel: "Short answer",
          simple: "My name is Dolly Rebecca Parton.",
          storyLabel: "Storytelling answer",
          story: "My name is Dolly Rebecca Parton \u2014 Dolly because Mama just liked the sound of it, Rebecca after one of the women in our family who held everybody together, and Parton from a long line of folks who could pick a guitar and tell you the truth in three verses or less."
        },
        {
          id: "try_your_way",
          lori: [
            "Both kinds of answers are welcome here.",
            "But if you can, lean into the telling.",
            "Let the colors and the people and the feelings come along.",
            "Now you give it a try \u2014 your own life, your own voice."
          ],
          question: "When you answer Lori, you can be brief, or you can really paint the scene.",
          simpleLabel: "Short answer",
          simple: "I remember playing outside behind our house.",
          storyLabel: "Storytelling answer",
          story: "I remember playing out behind the old house \u2014 the grass was tall enough that it whispered when the wind moved through it, my brother had a stick he called his sword, and the whole afternoon felt like it would never end and like every grown-up in the world had forgotten to come find us, which was just exactly right."
        }
      ];
    }
    // Default: structured (Shatner) trainer — short, anchored, factual
    return [
      {
        id: "about_lorevox",
        lori: [
          "Hi\u2026 I\u2019m Lori.",
          "I\u2019m here to help you tell your life story \u2014 clearly, one fact at a time.",
          "Lorevox is a place where your memories can be saved, organized, and turned into a story \u2014 in your own words.",
          "There\u2019s no test, and there are no right or wrong answers.",
          "Short and clear is welcome here. So is wandering, but you don\u2019t have to."
        ],
        question: "Let me show you two ways someone might answer.",
        simpleLabel: "Short answer",
        simple: "I was born in Bismarck, North Dakota, in 1947.",
        storyLabel: "Anchored answer",
        story: "I was born March 22, 1947, in Bismarck, North Dakota \u2014 my father was working at the rail yard at the time, and we lived two blocks from the river."
      },
      {
        id: "how_lori_works",
        lori: [
          "I usually ask gentle questions one at a time.",
          "We move through life step by step, starting at the beginning.",
          "An anchored answer gives me three things: the time, the place, and the people."
        ],
        question: "Here\u2019s a name example.",
        simpleLabel: "Short answer",
        simple: "My name is William Alan Shatner.",
        storyLabel: "Anchored answer",
        story: "My name is William Alan Shatner \u2014 William after my grandfather, Alan after my uncle, born March 1931 in Montreal, Quebec."
      },
      {
        id: "try_your_way",
        lori: [
          "Both ways are good.",
          "A short answer gives clear facts.",
          "An anchored answer adds the time, the place, and the people \u2014 enough to hold the moment.",
          "Now you can do it your way."
        ],
        question: "When you answer Lori, you can be brief, or you can anchor the moment with time, place, and people.",
        simpleLabel: "Short answer",
        simple: "I remember playing outside behind our house.",
        storyLabel: "Anchored answer",
        story: "When I was about six, around 1953, I used to play in the yard behind our house on Avenue Park \u2014 my brother was usually there, and the neighbors\u2019 dog would come over and watch us."
      }
    ];
  }

  function _getCurrentStep() {
    var s = _ensureTrainerState();
    if (!s) return null;
    var steps = _steps(s.style);
    return steps[s.stepIndex] || null;
  }

  function _renderPanel() {
    var root = _el("lv80TrainerPanel");
    if (!root) return;
    var s = _ensureTrainerState();
    if (!s || !s.active) {
      root.hidden = true;
      root.innerHTML = "";
      return;
    }
    var step = _getCurrentStep();
    if (!step) {
      root.hidden = true;
      root.innerHTML = "";
      return;
    }
    // Eyebrow label: prefer the trainer template title when available so the
    // user sees the same wording the template defines. Fall back to the
    // canonical hard-coded labels if no title was loaded.
    var templateTitle = (s.title || "").trim();
    var styleLabel;
    if (s.style === "structured") {
      styleLabel = "Shatner Trainer \u2014 " + (templateTitle || "Short, clear answers");
    } else {
      styleLabel = "Dolly Trainer \u2014 " + (templateTitle || "Warm, storytelling answers");
    }
    var loriHtml = step.lori.map(function (line) {
      return '<div class="lv80-trainer-lori-line">' + _esc(line) + '</div>';
    }).join("");
    var totalSteps = _steps(s.style).length;
    root.hidden = false;
    root.innerHTML =
      '<div class="lv80-trainer-shell">' +
        '<div class="lv80-trainer-eyebrow">' + _esc(styleLabel) + '</div>' +
        '<div class="lv80-trainer-title">Lori Trainer</div>' +
        '<div class="lv80-trainer-copy">' + loriHtml + '</div>' +
        '<div class="lv80-trainer-question">' + _esc(step.question) + '</div>' +
        '<div class="lv80-trainer-examples">' +
          '<div class="lv80-trainer-example-card">' +
            '<div class="lv80-trainer-example-label">' + _esc(step.simpleLabel) + '</div>' +
            '<div class="lv80-trainer-example-text">' + _esc(step.simple) + '</div>' +
          '</div>' +
          '<div class="lv80-trainer-example-card">' +
            '<div class="lv80-trainer-example-label">' + _esc(step.storyLabel) + '</div>' +
            '<div class="lv80-trainer-example-text">' + _esc(step.story) + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="lv80-trainer-actions">' +
          (s.stepIndex > 0 ? '<button class="lv80-trainer-btn secondary" onclick="LorevoxTrainerNarrators.prev()">Back</button>' : '') +
          '<button class="lv80-trainer-btn" onclick="LorevoxTrainerNarrators.next()">' +
            (s.stepIndex >= totalSteps - 1 ? 'Start Interview' : 'Next') +
          '</button>' +
          '<button class="lv80-trainer-btn secondary" onclick="LorevoxTrainerNarrators.skip()">Skip</button>' +
        '</div>' +
      '</div>';
    // WO-10J: Ensure trainer panel is visible after any re-render
    setTimeout(function() { root.scrollIntoView({behavior: "smooth", block: "start"}); }, 50);
  }

  function _esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // WO-11: meta-aware start. Accepts either:
  //   start({style, title, promptHint, templateName})    ← new canonical
  //   start(personId, style)                              ← legacy back-compat
  function start(metaOrPersonId, maybeStyle) {
    var s = _ensureTrainerState();
    if (!s) return;
    var meta;
    if (metaOrPersonId && typeof metaOrPersonId === "object") {
      meta = metaOrPersonId;
    } else {
      // Legacy signature: ignore personId, treat second arg as style
      meta = { style: maybeStyle };
    }
    s.active         = true;
    s.style          = _normalizeStyle(meta.style);
    s.title          = meta.title || null;
    s.promptHint     = meta.promptHint || null;
    s.templateName   = meta.templateName || null;
    s.stepIndex      = 0;
    s.completed      = false;
    s.completedStyle = null;
    _renderPanel();
  }

  function next() {
    var s = _ensureTrainerState();
    if (!s || !s.active) return;
    var total = _steps(s.style).length;
    if (s.stepIndex < total - 1) {
      s.stepIndex += 1;
      _renderPanel();
      return;
    }
    finish();
  }

  function prev() {
    var s = _ensureTrainerState();
    if (!s || !s.active) return;
    s.stepIndex = Math.max(0, s.stepIndex - 1);
    _renderPanel();
  }

  function skip() {
    finish();
  }

  // WO-11: capture meta locally BEFORE clearing active=false so the handoff
  // call still has the trainer flavor. The previous implementation set
  // style=null first and then called lv80StartTrainerInterview() with no
  // information, which is why both trainers collapsed identically.
  function finish() {
    var s = _ensureTrainerState();
    if (!s) return;

    var capturedMeta = {
      style:        s.style,
      title:        s.title,
      promptHint:   s.promptHint,
      templateName: s.templateName
    };

    s.active         = false;
    s.completed      = true;
    s.completedStyle = capturedMeta.style;
    // Note: style/title/promptHint are NOT cleared here. They persist on the
    // object until the next start() or reset() so any UI surface that wants
    // to show "you're in storyteller mode" can still read them.

    _renderPanel();

    // WO-11: trainer-aware handoff. Pass the captured meta so the start
    // function can flavor the intro bubble and inject a one-shot system hint.
    if (typeof window.lv80StartTrainerInterview === "function") {
      try {
        window.lv80StartTrainerInterview(capturedMeta);
      } catch (e) {
        console.warn("[WO-11] trainer handoff failed", e);
      }
    }
  }

  function isActive() {
    var s = _ensureTrainerState();
    return !!(s && s.active);
  }

  // WO-11B: removed bindNarratorMeta/getNarratorMeta — trainers are UI-only
  window.LorevoxTrainerNarrators = {
    start: start,
    next: next,
    prev: prev,
    skip: skip,
    finish: finish,
    isActive: isActive,
    render: _renderPanel,
    reset: _reset
  };
})();
