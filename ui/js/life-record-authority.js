/* Life Record authority guard (Batch C-2b, 2026-09-24).

   RULE (Batch C exit gate): no normal operator action may establish or alter
   biography anywhere except through the Life Record writer.

   Several review actions still write biography into the EARLIER system —
   the old questionnaire document, the interview projection, or family-truth
   promotion:
     * Shadow Review → Correct / Correct + Follow-up   (projection + old questionnaire)
     * Conflicts     → Replace / Merge                 (projection + old questionnaire)
     * Suggestions   → Accept / Save this as my value  (old questionnaire + projection)
     * WO-13 Review  → Promote approved                (family-truth promoted rows)
   Until they are rebuilt to write the Life Record (Batch D-3), those actions
   are HELD: they refuse, say so, and change nothing. Decisions that only
   record review state — Reject, Decline, Source Only, Keep, row status —
   are not affected.

   Every guarded site asks `LorevoxAuthority.legacyWritesHeld()`, and treats a
   missing module as HELD (fail closed): losing this file must never quietly
   re-open a second authority. */
(function (root) {
  "use strict";
  var MESSAGE = "Not changed: this action wrote to the earlier biography system, which is being " +
    "retired. Make the change in Bio Builder → Questionnaire, which writes the Life Record.";
  var api = {
    legacyWritesHeld: function () { return true; },
    MESSAGE: MESSAGE,
    held: function (where) {
      try { console.warn("[life-record-authority] HELD: " + where + " — " + MESSAGE); } catch (_) {}
      return { held: true, where: where, message: MESSAGE };
    },
  };
  root.LorevoxAuthority = api;
})(typeof window !== "undefined" ? window : this);

/* The one-line check every guarded site uses (fail closed if this file is absent):
     var a = window.LorevoxAuthority; if (!a || a.legacyWritesHeld()) { ... refuse ... } */
