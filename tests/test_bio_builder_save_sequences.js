/* Behavioural sequence tests for the real Bio Builder save path.

   WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01.

   These drive the SHIPPING _saveSection / _addRepeatEntry /
   _restoreQuestionnaire against a rendered form and a controllable server.
   They assert on collected values, PUT payloads, the resulting document and
   the visible save status — never on source text.

   The first regression is the missing father. On 2026-09-18 an operator
   entered a mother, saved, added a father, saved, and only the mother
   reached the database. 45 source-pattern checks and two days of live
   testing had passed clean, because every one of them used a single entry.

   Run:  node tests/test_bio_builder_save_sequences.js
*/

"use strict";

const { createHarness } = require("./harness/bio-builder-harness");

let failures = 0;
let current = "";
function check(name, cond, detail) {
  if (cond) console.log(`    ok    ${name}`);
  else { failures++; console.log(`    FAIL  ${name}\n          ${detail || ""}`); }
}
function scenario(name) { current = name; console.log(`\n  ${name}`); }

const PID = "b580c695-2893-4fe2-a359-cea6967725df";

const MOTHER = {
  relation: "Mother", firstName: "Ingrid ", lastName: "Lindqvist",
  birthDate: "1908-03-02", birthPlace: "Duluth, Minnesota",
  occupation: "schoolteacher", deceased: "Yes",
  notableLifeEvents: "walked the Bong Bridge the day it opened",
  notes: "the icebox smelled of smelt and cedar shavings",
};
const FATHER = {
  relation: "Father", firstName: "Bertil", lastName: "Lindqvist",
  birthDate: "1904-11-19", birthPlace: "Gävle, Sweden",
  occupation: "ore dock foreman", deceased: "Yes",
  notableLifeEvents: "lost two fingers to a winch in 1951",
  notes: "kept a pocket watch that never ran",
};

function fillEntry(h, idx, person) {
  Object.keys(person).forEach((f) => {
    if (h.window.document.getElementById("bbQ_" + idx + "_" + f)) {
      h.typeEntry(idx, f, person[f]);
    }
  });
}

function parentsOf(doc) {
  return (doc && doc.parents) || [];
}

async function run() {
  console.log("\nbio builder save sequences (behavioural)");

  /* ═══ 1. THE MISSING FATHER ════════════════════════════════════════════
     The reproduction, exactly as the operator performed it. */
  {
    scenario("1. enter a mother, save, add a father, save");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.save("parents");
    await h.settle();

    check("the mother reached the server",
      parentsOf(h.server.stored(PID)).length === 1,
      "first save of a repeatable section did not store one entry");

    // Add the second entry the way the form does it, then fill and save.
    h.addEntry("parents");
    await h.settle();
    h.render("parents");

    check("the form now renders two entries",
      h.entryCount() === 2,
      "rendered " + h.entryCount() + " — the operator cannot type a father " +
      "into a form that shows one parent");

    fillEntry(h, 1, FATHER);
    h.save("parents");
    await h.settle();

    const put = h.server.lastPut();
    const sentParents = parentsOf(put && put.questionnaire);

    check("the PUT payload carries BOTH parents",
      sentParents.length === 2,
      "payload had " + sentParents.length + " — THE 2026-09-18 DEFECT: " +
      "_saveSection mapped over stored entries and read the DOM by index, so " +
      "an entry beyond storage's length was never looked at");

    check("the father's name is in the payload",
      sentParents.length === 2 && sentParents[1].firstName === "Bertil",
      "the entry exists but its typed values were not collected");

    const stored = parentsOf(h.server.stored(PID));
    check("both parents are in the stored document",
      stored.length === 2 && stored[0].firstName === "Ingrid " &&
      stored[1].firstName === "Bertil");

    check("the mother's nine fields survived the second save",
      stored.length === 2 &&
      Object.keys(MOTHER).every((f) => stored[0][f] === MOTHER[f]),
      "a later save of the same section must not disturb an earlier entry");

    check("the trailing space in 'Ingrid ' is preserved",
      stored.length > 0 && stored[0].firstName === "Ingrid ",
      "silent normalisation is data mutation nobody asked for");

    check("the non-ASCII birthplace survived",
      stored.length === 2 && stored[1].birthPlace === "Gävle, Sweden");

    check("the canary phrase is byte-identical",
      stored.length > 0 && stored[0].notes === MOTHER.notes);
  }

  /* ═══ 1b. THE SAME DEFECT, WITH THE MASK REMOVED ══════════════════════
     Scenario 1 passes even with the count bug restored, because the dirty
     flag keeps both entries in memory and `existing.length` is already 2.
     The two repairs mask each other, and a regression test that only passes
     because of a DIFFERENT fix is not protecting the thing it names.

     The original conditions need storage and the DOM to DISAGREE. That
     happens after a confirmed save clears the dirty flag: the blank entry
     pushed by Add carries no populated leaves, so the server stores N while
     memory holds N+1 — and the next restore adopts the server's N over the
     top. The form then shows an entry that storage has never heard of, which
     is exactly the state the operator was in when the father vanished. */
  {
    scenario("1b. save, add, save the blank, then fill the new entry");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.save("parents");
    await h.settle();

    h.addEntry("parents");           // pushes a blank entry into memory
    await h.settle();
    h.render("parents");
    h.save("parents");               // a no-op save: the blank contributes nothing
    await h.settle();                // ...and a confirmed save clears dirty

    /* FINDING, 2026-09-18, from this harness: the blank entry IS stored.
       `deceased` is a select defaulting to "No", which is a populated leaf,
       so adding an entry and saving files a parent whose only recorded fact
       is that they are not dead. In a biography that is a phantom family
       member, and it will render in the family tree. Recorded in
       WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01 rather than fixed here — it
       wants a decision about what makes an entry real, not a quick patch. */
    check("the blank entry is stored — phantom family member (known finding)",
      parentsOf(h.server.stored(PID)).length === 2 &&
      parentsOf(h.server.stored(PID))[1].deceased === "No" &&
      !parentsOf(h.server.stored(PID))[1].firstName,
      "if this now passes differently the phantom-entry behaviour changed — " +
      "update WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01 rather than the assertion");

    h.render("parents");
    check("the form still shows two entries",
      h.entryCount() === 2,
      "rendered " + h.entryCount() + " — the operator needs somewhere to type");

    fillEntry(h, 1, FATHER);
    h.save("parents");
    await h.settle();

    const stored = parentsOf(h.server.stored(PID));
    check("the father reached the server despite storage holding fewer entries",
      stored.length === 2 && stored[1].firstName === "Bertil",
      "stored " + stored.length + " — THE 2026-09-18 DEFECT. The save read " +
      "the DOM by index while iterating the STORED array, so an entry the " +
      "form showed and storage did not was never looked at");

    check("the mother is undisturbed",
      stored.length === 2 && stored[0].firstName === "Ingrid ");
  }

  /* ═══ 1c. THE COUNT INVARIANT, DIRECTLY ═══════════════════════════════
     WHITE-BOX, and labelled as such. This does not reproduce an operator
     sequence; it constructs the state one used to arrive at.

     WHY IT IS NOT AN END-TO-END SEQUENCE. Chasing that established something
     worth writing down: with the dirty flag in place, `rendered > stored` may
     no longer be reachable through the UI at all. _renderSectionDetail
     renders from memory, so rendered always equals memory; the only thing
     that shrank memory below the form was the adopt branch, and _qqDirty now
     blocks it. The two repairs mask each other, and the honest reading is
     that the DIRTY FIX closes the hole while the COUNT FIX is defence in
     depth.

     That is a reason to keep the count fix and test it directly — not a
     reason to build a contrived sequence so it looks load-bearing. If a
     future change re-opens any path that replaces memory mid-edit, this
     assertion is what stops the entry being dropped silently a second time.

     Memory is shrunk here exactly as an adopt would shrink it. */
  {
    scenario("1c. the save collects every RENDERED entry (white-box invariant)");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.addEntry("parents");
    await h.settle();
    h.render("parents");
    fillEntry(h, 1, FATHER);

    check("two entries are on the form", h.entryCount() === 2);

    /* Simulate the adopt: canonical comes back holding only the first entry.
       The DRAFT must shrink too. _saveSection restores before it collects,
       and the restore re-reads localStorage — so shrinking memory alone is
       undone before the code under test sees it, and the first version of
       this check passed against the reintroduced bug for that reason. */
    const mem = h.memory();
    const shrunk = JSON.parse(JSON.stringify(mem));
    shrunk.parents = [shrunk.parents[0]];
    mem.parents = [mem.parents[0]];
    h.setDraft(PID, shrunk);

    check("memory now holds fewer entries than the form shows",
      mem.parents.length === 1 && h.entryCount() === 2);

    h.save("parents");
    await h.settle();

    const put = h.server.lastPut();
    const sent = parentsOf(put && put.questionnaire);
    check("the save still collected both rendered entries",
      sent.length === 2 && sent[1].firstName === "Bertil",
      "payload had " + sent.length + " — the save iterated the stored array " +
      "and never looked at the entry the form was showing");
  }

  /* ═══ 2. A THIRD ENTRY ═════════════════════════════════════════════════
     Two worked; the bug was an off-by-storage, so prove it generalises. */
  {
    scenario("2. add a third entry to a section that already stores two");
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [Object.assign({}, MOTHER), Object.assign({}, FATHER)] }, 2);
    h.restore(PID);
    await h.settle();

    h.addEntry("parents");
    await h.settle();
    h.render("parents");

    check("the form renders three entries", h.entryCount() === 3,
      "rendered " + h.entryCount());

    fillEntry(h, 2, { relation: "Stepmother", firstName: "Solveig", lastName: "Aune" });
    h.save("parents");
    await h.settle();

    const stored = parentsOf(h.server.stored(PID));
    check("all three entries are stored", stored.length === 3,
      "stored " + stored.length);
    check("the third entry's values were collected",
      stored.length === 3 && stored[2].firstName === "Solveig");
    check("the first two are untouched",
      stored.length === 3 && stored[0].firstName === "Ingrid " &&
      stored[1].firstName === "Bertil");
  }

  /* ═══ 3. AN UNCHANGED SAVE IS NOT A WRITE ══════════════════════════════ */
  {
    scenario("3. save a section without changing anything");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    /* Establish the document through a REAL save rather than by seeding.
       A seeded document lacks the identity migration's _legacy* markers, so
       the first save legitimately writes them and the "unchanged" save is
       not unchanged at all. That is correct behaviour and a broken test —
       the harness was comparing against a document the application would
       never have produced. Save first, then re-save, exactly as the operator
       did on 2026-09-18. */
    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.save("parents");
    await h.settle();

    h.render("parents");
    const revBefore = h.server.revision(PID);
    const historyBefore = h.server.history(PID).length;

    h.save("parents");
    await h.settle();

    check("the revision did not move",
      h.server.revision(PID) === revBefore,
      "a save that changes nothing is not a write");
    check("no history row was added",
      h.server.history(PID).length === historyBefore);
    check("the mother's values are still exactly as typed",
      JSON.stringify(parentsOf(h.server.stored(PID))[0] || {}).length > 0 &&
      Object.keys(MOTHER).every((f) => parentsOf(h.server.stored(PID))[0][f] === MOTHER[f]),
      "the unchanged save altered a stored value");

    const b = h.banner();
    check("the banner distinguishes a no-op from a write",
      b !== null && /no changes/i.test(b.text),
      b ? ("banner said: " + b.text) :
      "no banner at all — the operator cannot tell whether the edit landed");
  }

  /* ═══ 4. A FAILED SAVE MUST NOT LOOK LIKE A SAVE ═══════════════════════ */
  {
    scenario("4. the server rejects the write");
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [Object.assign({}, MOTHER)] }, 1);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    h.typeEntry(0, "occupation", "headmistress");
    h.failNextPut(500);
    h.save("parents");
    await h.settle();

    const b = h.banner();
    check("a banner is shown at all", b !== null,
      "silence is what the operator reads as success");
    check("it says NOT SAVED", b !== null && /NOT SAVED/.test(b.text),
      b ? ("banner said: " + b.text) : "");
    check("it does not claim a revision",
      b !== null && !/revision/i.test(b.text));
    check("the typed value is still on the form",
      h.valueOf("bbQ_0_occupation") === "headmistress",
      "a failed save must never clear the form");
    check("the draft still holds the typed value",
      (parentsOf(h.draft(PID))[0] || {}).occupation === "headmistress",
      "refusing to transmit must not also discard what was typed");
    check("the server document was NOT changed",
      parentsOf(h.server.stored(PID))[0].occupation === "schoolteacher");
  }

  /* ═══ 5. A NETWORK FAILURE IS REPORTED AS ONE ══════════════════════════ */
  {
    scenario("5. the server cannot be reached");
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [Object.assign({}, MOTHER)] }, 1);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    h.typeEntry(0, "occupation", "headmistress");
    h.failNextPut("network");
    h.save("parents");
    await h.settle();

    const b = h.banner();
    check("the failure is reported", b !== null && /NOT SAVED/.test(b.text));
    check("it is distinguishable from a rejection",
      b !== null && /reach the server/i.test(b.text),
      b ? ("banner said: " + b.text) : "");
    check("the typed value survives", h.valueOf("bbQ_0_occupation") === "headmistress");
  }

  /* ═══ 6. A 409 IS A CONFLICT, NOT A GENERIC FAILURE ════════════════════ */
  {
    scenario("6. the server answers 409");
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [Object.assign({}, MOTHER)] }, 1);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    h.typeEntry(0, "occupation", "headmistress");
    h.failNextPut(409, { conflicting_paths: ["parents[0].occupation"] });
    h.save("parents");
    await h.settle();

    const b = h.banner();
    check("the conflict is reported", b !== null && /NOT SAVED/.test(b.text));
    check("it names newer answers rather than a generic error",
      b !== null && /newer answers/i.test(b.text),
      b ? ("banner said: " + b.text) : "");
    check("the typed value survives", h.valueOf("bbQ_0_occupation") === "headmistress");
  }

  /* ═══ 7. A GET LANDING MID-EDIT MUST NOT REPLACE TYPING ════════════════
     BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01. Only reachable on records
     that ALREADY have a server document — every real narrator. */
  {
    scenario("7. a server read lands while the operator is typing");
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [Object.assign({}, MOTHER)] }, 1);
    h.restore(PID);
    await h.settle();
    h.render("parents");

    h.pauseGets();
    h.addEntry("parents");           // starts a restore; its GET is parked
    h.render("parents");
    fillEntry(h, 1, FATHER);         // the operator types while it is in flight
    h.save("parents");               // commits the DOM into memory
    h.releaseGet();                  // the stale document arrives now
    await h.settle();

    const mem = parentsOf(h.memory());
    check("the in-memory document still holds the typed entry",
      mem.length >= 2 && mem[1] && mem[1].firstName === "Bertil",
      "the arriving server document replaced work that was on screen");

    const stored = parentsOf(h.server.stored(PID));
    check("the typed entry reached the server",
      stored.length === 2 && stored[1].firstName === "Bertil",
      "stored " + stored.length + " entries");
  }

  /* ═══ 8. NARRATOR SWITCH MUST NOT CROSS-WRITE ══════════════════════════ */
  {
    scenario("8. the narrator changes while a save is in flight");
    const OTHER = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2";
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [Object.assign({}, MOTHER)] }, 1);
    h.server.seed(OTHER, { parents: [{ relation: "Mother", firstName: "Janice" }] }, 1);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    h.typeEntry(0, "occupation", "headmistress");
    h.setNarrator(OTHER);            // switch before the save is issued
    h.save("parents");
    await h.settle();

    const other = parentsOf(h.server.stored(OTHER));
    check("the other narrator's document was not overwritten",
      other.length === 1 && other[0].firstName === "Janice",
      "a save must never land under a different narrator's id — narrator A's " +
      "mother was stored under narrator B until the rendered-for stamp was added");

    check("nothing at all was written for the other narrator",
      h.server.puts.every((p) => p.person_id !== OTHER),
      "the form must be refused before it is harvested, not merged afterwards");

    const b = h.banner();
    check("the refusal is visible to the operator",
      b !== null && /NOT SAVED/.test(b.text) && /different narrator/i.test(b.text),
      b ? ("banner said: " + b.text) :
      "a silent refusal leaves a form that looks saved — the original defect");
  }

  console.log(failures === 0
    ? `\n  all sequences passed\n`
    : `\n  ${failures} FAILED\n`);
  process.exit(failures === 0 ? 0 : 1);
}

run().catch((e) => {
  console.error("\n  harness error:", e && e.stack || e);
  process.exit(1);
});
