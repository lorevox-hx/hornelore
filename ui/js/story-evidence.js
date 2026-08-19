/*
   story-evidence.js — the browser's ONE reader of canonical story evidence.
   WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit B (2026-08-17).

   Both Life Map renderers need the same three answers:

     how many stories are APPROVED for this era
     how many are PROVISIONAL
     which stories are UNPLACED

   They must not each work that out for themselves, and they must not
   keep their own copy of it. This module derives everything from the
   server payload already sitting in `state.chronologyProjection`, on
   every call. There is NO browser-owned story state here: nothing is
   cached, nothing is written back, and clearing the projection clears
   this with it.

   ── THE RULES IT ENFORCES FOR ITS CALLERS ─────────────────────────────

   * **Approved and provisional are counted separately, never summed.**
     A renderer that shows one number cannot tell the operator whether
     the narrator's chronology rests on reviewed material or on things
     nobody has confirmed.

   * **A story is placed ONLY where the server says.** The era comes from
     the payload. This module never derives one from a year, a
     confidence, or anything else.

   * **UNPLACED IS ITS OWN GROUP, AND IT IS NOT TODAY.** `today` is the
     current-life bucket. Dropping undated stories into it would assert a
     placement nobody made — and would put a childhood memory in the
     narrator's present.

   * **Discarded stories never arrive.** The server projection has
     already removed them; this module does not filter for them, because
     it must never be the thing standing between a discarded story and a
     renderer.
*/
(function () {
  "use strict";

  var UNPLACED = "__unplaced__";

  function _projection() {
    try {
      var st = (typeof state !== "undefined" && state) ? state : null;
      var proj = st && st.chronologyProjection;
      return (proj && typeof proj === "object") ? proj : null;
    } catch (e) {
      return null;
    }
  }

  /* Whether the story lane could be read at all.
     "unavailable" is NOT "this narrator has no stories" -- the caller
     must be able to tell an outage from an empty narrator. */
  function laneStatus() {
    var proj = _projection();
    if (!proj) return "not_loaded";
    var sources = proj.sources || {};
    var lane = sources.story_evidence || {};
    return lane.status || "not_loaded";
  }

  /* Can this lane's numbers be believed?

     Added 2026-08-19. Consumers were testing `status === "unavailable"`
     and treating EVERYTHING else as an answer -- so "not_loaded" (the
     projection has not arrived, or the fetch was dropped) and
     "not_attempted" (the server never queried the lane, which is what a
     narrator with no date of birth gets) both rendered as a confident
     zero. A narrator with fifty captured stories and no DOB therefore
     showed nothing at all, indistinguishable from one who has never told
     a story.

     Only "read" is an answer. Everything else means we cannot say. */
  function laneReadable() {
    return laneStatus() === "read";
  }

  function items() {
    var proj = _projection();
    if (!proj) return [];
    var rows = proj.story_evidence;
    return Array.isArray(rows) ? rows : [];
  }

  /* Group by era, with the unplaced ones kept apart under their own key.

     A story counts as placed only when the SERVER gave it an era. A year
     alone does not place it on the Life Map -- the map is drawn in eras,
     and inventing one from a year is the derivation this lane exists to
     stop. */
  function byEra() {
    var out = {};
    items().forEach(function (row) {
      /* CORRECTED 2026-08-19 (WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01
         Commit 2). This read `row.era_candidates[0]` -- the machine's
         shortlist -- and decided placement here. The server decides it
         now, in `story_projection._placement_for`, and nulls `era` when
         a story is unplaced. Reading the server's answer is what makes
         "unplaced" mean ONE thing: the review panel's count and this
         grouping can no longer disagree, which they did.

         The retired line was:
             var eras = row && row.era_candidates;
             if (Array.isArray(eras) && eras.length) era = String(eras[0] || "").trim(); */
      var era = String((row && row.era) || "").trim();
      var placed = !!era && row.placement && row.placement !== "unplaced";
      var key = placed ? era : UNPLACED;
      if (!out[key]) out[key] = { approved: [], provisional: [] };
      if (row.status === "approved") out[key].approved.push(row);
      else out[key].provisional.push(row);
    });
    return out;
  }

  function countsForEra(eraId) {
    var group = byEra()[eraId];
    if (!group) return { approved: 0, provisional: 0, total: 0 };
    return {
      approved: group.approved.length,
      provisional: group.provisional.length,
      total: group.approved.length + group.provisional.length,
    };
  }

  function unplaced() {
    var group = byEra()[UNPLACED];
    if (!group) return { approved: [], provisional: [], total: 0 };
    return {
      approved: group.approved,
      provisional: group.provisional,
      total: group.approved.length + group.provisional.length,
    };
  }

  function totals() {
    var approved = 0, provisional = 0;
    items().forEach(function (row) {
      if (row.status === "approved") approved += 1;
      else provisional += 1;
    });
    var un = unplaced();
    return {
      approved: approved,
      provisional: provisional,
      unplaced: un.total,
      total: approved + provisional,
      status: laneStatus(),
    };
  }

  /* A short, honest label. Never collapses the two numbers into one. */
  function summaryLabel() {
    var t = totals();
    if (t.status === "unavailable") return "stories unavailable";
    if (!t.total) return "";
    var parts = [];
    if (t.approved) parts.push(t.approved + " approved");
    if (t.provisional) parts.push(t.provisional + " provisional");
    if (t.unplaced) parts.push(t.unplaced + " unplaced");
    return parts.join(" · ");
  }

  window.LorevoxStoryEvidence = {
    UNPLACED_KEY: UNPLACED,
    laneStatus: laneStatus,
    laneReadable: laneReadable,
    items: items,
    byEra: byEra,
    countsForEra: countsForEra,
    unplaced: unplaced,
    totals: totals,
    summaryLabel: summaryLabel,
  };
})();
