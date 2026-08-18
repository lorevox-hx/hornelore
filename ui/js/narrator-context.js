/*
   narrator-context.js — ONE narrator-context contract for every
   narrator-scoped browser surface.
   WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part B (2026-08-17).

   ── THE PROBLEM ────────────────────────────────────────────────────
   Five browser surfaces each decided independently who the narrator
   was, and none of them asked the shell:

     shell            state.person_id  +  lv_active_person_v55
     Trip Tab         ?narrator_id  ->  trip_tab_narrator_id_v1
     Photo Intake     pi_narrator_id_v1
     Photo Timeline   pi_narrator_id_v1   (deliberately shared with Intake)
     Media Archive    ma_narrator_id_v1
     Travel Doc       opts.person_id from the shell (the one that was right)

   Three of the shell's launchers passed no narrator at all, so opening
   Photo Intake from a session with narrator A could land on narrator B
   — whoever that surface happened to be looking at last week — with
   nothing on screen to say so. Uploads are stamped with the narrator
   the surface believes in, so this is a cross-narrator write, not a
   cosmetic mismatch.

   ── WHAT THIS MODULE DECIDES, AND WHAT IT DOES NOT ─────────────────
   It decides which narrator a surface STARTS on. It does not take away
   the pickers, it does not remove the legacy keys, and it does not
   reach into the shell.

     1. An explicit `?narrator_id=` is the initial handoff authority.
     2. It is VALIDATED against /api/people before it is selected.
     3. An explicit id that does not validate FAILS CLOSED — no narrator
        is selected. It must NEVER fall through to a legacy cache,
        because "the id you asked for is wrong, so here is a different
        narrator's library" is the worst possible answer.
     4. Only a direct standalone load with NO query parameter may fall
        back to that surface's own legacy key — and only after the same
        validation.
     5. A narrator chosen inside a standalone surface updates THAT
        surface's cache. It never writes lv_active_person_v55.

   Rule 5 is enforced structurally: SHELL_KEY is compared against on
   every remember() call and the write is refused. A surface cannot
   silently become the shell's authority by passing the wrong constant.

   Loaded by the standalone pages and by the shell. No dependencies, no
   build step, no framework — the same plain-script idiom as the pages
   that consume it.
*/
(function () {
  "use strict";

  // The shell's authority. Named here so remember() can refuse to write
  // it, NOT so that anything here reads it: a standalone page has no
  // business inheriting the shell's selection through localStorage. The
  // shell hands its narrator over explicitly, in the URL, or not at all.
  var SHELL_KEY = "lv_active_person_v55";

  // Accepted in this order. `narrator_id` is the contract; `person_id`
  // is accepted because Travel Doc and the standalone Documenter have
  // always used that spelling and links in the wild carry it.
  var QUERY_KEYS = ["narrator_id", "person_id"];

  function _origin(apiBase) {
    var base = apiBase || window.LOREVOX_API || "http://localhost:8000";
    return String(base).replace(/\/+$/, "");
  }

  function readQuery(search) {
    var qs;
    try {
      qs = new URLSearchParams(
        search === undefined ? window.location.search : search
      );
    } catch (e) {
      return "";
    }
    for (var i = 0; i < QUERY_KEYS.length; i++) {
      var v = (qs.get(QUERY_KEYS[i]) || "").trim();
      if (v) return v;
    }
    return "";
  }

  // /api/people has been read four different ways across four surfaces
  // (bare array, {people:[...]}, {items:[...]}), and the id has been
  // read with three different precedences. One reader, one precedence.
  function normalizePeople(payload) {
    var list = [];
    if (Array.isArray(payload)) list = payload;
    else if (payload && Array.isArray(payload.people)) list = payload.people;
    else if (payload && Array.isArray(payload.items)) list = payload.items;
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var p = list[i] || {};
      var id = String(p.id || p.person_id || "").trim();
      if (!id) continue;
      out.push({
        id: id,
        display_name: String(p.display_name || p.name || id),
        narrator_type: p.narrator_type || "",
        raw: p,
      });
    }
    return out;
  }

  function fetchPeople(apiBase) {
    return fetch(_origin(apiBase) + "/api/people")
      .then(function (r) {
        if (!r.ok) throw new Error("/api/people -> " + r.status);
        return r.json();
      })
      .then(normalizePeople);
  }

  function readCache(legacyKey) {
    if (!legacyKey || legacyKey === SHELL_KEY) return "";
    try {
      return (localStorage.getItem(legacyKey) || "").trim();
    } catch (e) {
      return "";
    }
  }

  /* Write a surface's OWN cache. Refuses the shell key — see rule 5. */
  function remember(legacyKey, personId) {
    if (!legacyKey) return false;
    if (legacyKey === SHELL_KEY) {
      try {
        console.warn(
          "[narrator-context] refusing to write the shell key '" +
            SHELL_KEY +
            "' from a surface cache. The shell owns its own selection."
        );
      } catch (e) {}
      return false;
    }
    try {
      if (personId) localStorage.setItem(legacyKey, String(personId));
      else localStorage.removeItem(legacyKey);
      return true;
    } catch (e) {
      return false;
    }
  }

  /*
     Resolve the narrator this surface should start on.

     opts: { apiBase, legacyKey, search }
     ->   { personId, source, people, peopleOk, error, requested }

     source:
       "query"           explicit id, validated, selected
       "query_invalid"   explicit id given and REJECTED — personId is ""
                         and no cache was consulted (rule 3)
       "cache"           no explicit id; legacy cache validated, selected
       "cache_invalid"   cache held a stale id; dropped, nothing selected
       "none"            nothing to select — a legitimate empty state
       "unvalidated"     /api/people could not be read, so nothing could
                         be validated and therefore nothing is selected
  */
  function resolve(opts) {
    opts = opts || {};
    var requested = readQuery(opts.search);
    var cached = requested ? "" : readCache(opts.legacyKey);

    return fetchPeople(opts.apiBase).then(
      function (people) {
        var ids = {};
        for (var i = 0; i < people.length; i++) ids[people[i].id] = true;

        if (requested) {
          if (ids[requested]) {
            return {
              personId: requested,
              source: "query",
              people: people,
              peopleOk: true,
              error: "",
              requested: requested,
            };
          }
          // FAIL CLOSED. Deliberately does not look at the cache.
          return {
            personId: "",
            source: "query_invalid",
            people: people,
            peopleOk: true,
            error:
              "This link named a narrator that does not exist here. " +
              "No narrator has been selected — choose one below.",
            requested: requested,
          };
        }

        if (cached) {
          if (ids[cached]) {
            return {
              personId: cached,
              source: "cache",
              people: people,
              peopleOk: true,
              error: "",
              requested: "",
            };
          }
          remember(opts.legacyKey, "");
          return {
            personId: "",
            source: "cache_invalid",
            people: people,
            peopleOk: true,
            error: "",
            requested: "",
          };
        }

        return {
          personId: "",
          source: "none",
          people: people,
          peopleOk: true,
          error: "",
          requested: "",
        };
      },
      function (err) {
        // Nothing could be validated, so nothing is selected. A failed
        // lookup is not permission to trust an unvalidated id.
        return {
          personId: "",
          source: "unvalidated",
          people: [],
          peopleOk: false,
          error: "Could not read the narrator list: " + (err && err.message),
          requested: requested,
        };
      }
    );
  }

  /* Append the narrator to a same-origin tool URL. */
  function withNarrator(page, personId) {
    var pid = String(personId || "").trim();
    if (!pid) return page;
    var sep = page.indexOf("?") >= 0 ? "&" : "?";
    return page + sep + "narrator_id=" + encodeURIComponent(pid);
  }

  /* The one launcher. Every shell tool button and every cross-page link
     goes through here so "does this carry the narrator?" has one answer
     instead of nine. */
  function openTool(page, personId, target) {
    return window.open(withNarrator(page, personId), target || "_blank", "noopener");
  }

  window.LorevoxNarratorContext = {
    SHELL_KEY: SHELL_KEY,
    QUERY_KEYS: QUERY_KEYS.slice(),
    readQuery: readQuery,
    readCache: readCache,
    remember: remember,
    normalizePeople: normalizePeople,
    fetchPeople: fetchPeople,
    resolve: resolve,
    withNarrator: withNarrator,
    openTool: openTool,
  };
})();
