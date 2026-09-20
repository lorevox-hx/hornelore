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

    /* BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-ASSERTION-01, now fixed.
       `deceased` defaulted to "No" — a populated leaf — so adding an entry
       and saving filed a parent whose only recorded fact was that they were
       alive. A phantom family member, rendered by the family tree. */
    check("a blank added entry is NOT stored as a family member",
      parentsOf(h.server.stored(PID)).length === 1,
      "stored " + parentsOf(h.server.stored(PID)).length + " — an untouched " +
      "select must not make a person exist");

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

  /* ═══ 4b. A FAILED SAVE MUST PRODUCE NO DOWNSTREAM FACTS ═══════════════
     WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01, section 1. Candidate extraction,
     markHumanEdit and the family-graph sync used to run immediately after
     _persistDrafts without awaiting it. A refused write therefore left
     candidates, human-edit marks and graph nodes derived from answers the
     database never accepted — which is how an unsaved answer becomes an
     apparent established fact, and how a narrator ends up speaking with
     confidence about something nobody saved. */
  {
    scenario("4b. a rejected write marks nothing downstream");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    const marks = [];
    const syncs = [];
    const candidatesBefore = () => {
      const bb = h.core._bb() || {};
      return JSON.stringify(bb.candidates || bb.questionnaireCandidates || []);
    };
    const candBefore = candidatesBefore();
    h.window.LorevoxProjectionMap = {
      buildRepeatablePath: (s, i, f) => s + "[" + i + "]." + f,
    };
    h.window.LorevoxProjectionSync = {
      markHumanEdit: (p, v) => marks.push(p + "=" + v),
    };
    h.window.LorevoxBioBuilderModules.graph = { fullSync: () => syncs.push(1) };

    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.failNextPut(500);
    h.save("parents");
    await h.settle();

    check("nothing was marked human-edited",
      marks.length === 0,
      "marked " + marks.length + " field(s) from a write the server refused");
    check("the family graph was not resynced",
      syncs.length === 0,
      "a relative must not appear in the graph because of a failed save");

    /* Candidate extraction is the third downstream effect, and the one with
       the longest reach: a candidate that later reads as established
       biography is how an unsaved answer becomes an apparent fact that Lori
       would then state with confidence. */
    check("no candidates were extracted from the refused write",
      candidatesBefore() === candBefore,
      "a suggestion derived from answers the database rejected can later be " +
      "promoted into biography nobody ever saved");

    // And the same save, succeeding, must still do the work.
    h.save("parents");
    await h.settle();

    check("a confirmed save DOES mark its fields",
      marks.length > 0,
      "the boundary must gate the work, not delete it");
    check("a confirmed save DOES resync the graph", syncs.length > 0);
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

  /* ═══ 8c. REMOVAL — CURRENT BEHAVIOUR, PINNED ═════════════════════════
     WO-BIO-QUESTIONNAIRE-DELETE-ENTRY-01.

     A family member cannot be removed. There is no Remove control, and
     clearing every field is a silent no-op because merge_whole_document
     applies populated leaves as mutations with NO removals.

     That merge behaviour is deliberate and must not be "fixed": omission-as-
     deletion is exactly what destroyed ten of Janice's values on 2026-09-15.
     The gap is that no EXPLICIT removal path was built alongside it.

     These assertions pin what happens today so the gap is visible in a test
     run rather than only in a document, and so that when removal is built
     the change shows up here rather than passing unnoticed. They are not an
     endorsement — read the work order. */
  {
    scenario("8c. clearing an entry does not remove it (known gap, pinned)");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.save("parents");
    await h.settle();
    h.addEntry("parents");
    await h.settle();
    h.render("parents");
    fillEntry(h, 1, FATHER);
    h.save("parents");
    await h.settle();

    check("two parents are stored", parentsOf(h.server.stored(PID)).length === 2);

    h.render("parents");
    for (const f of Object.keys(FATHER)) {
      const el = h.window.document.getElementById("bbQ_1_" + f);
      if (el) el.value = "";
    }
    h.save("parents");
    await h.settle();

    const after = parentsOf(h.server.stored(PID));
    check("clearing every field leaves the entry fully intact",
      after.length === 2 && after[1].firstName === "Bertil",
      "if this now fails, removal behaviour changed — check it was built " +
      "deliberately (WO-BIO-QUESTIONNAIRE-DELETE-ENTRY-01) and not by " +
      "re-enabling omission-as-deletion, which would reopen the 2026-09-15 " +
      "data loss for every other field");

    check("the first parent is untouched by the attempt",
      after[0] && after[0].firstName === "Ingrid ");
  }

  /* ═══ 8b. NO SELECT MAY ANSWER ITSELF ══════════════════════════════════
     BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-ASSERTION-01.

     A select whose option list has no empty first entry is answered the
     moment it is drawn. `parents.deceased` defaulted to "No" and
     `grandparents.side` to "Paternal" — so an untouched form asserted that a
     parent was alive and that every grandparent was on the father's side.
     Both are populated leaves, both persist, both render in the family tree,
     and neither was ever said by anyone.

     Enumerated from the shipping SECTIONS rather than listed here, so a
     select added later cannot reintroduce the class unnoticed. An operator
     deliberately choosing "No" is still recorded; what changes is that
     silence is no longer mistaken for an answer. */
  {
    scenario("8b. no select's untouched default is a stored assertion");
    const h = createHarness();
    const offenders = [];
    for (const s of h.qq.SECTIONS) {
      for (const f of (s.fields || [])) {
        if (f.type === "select" && Array.isArray(f.options) && f.options[0] !== "") {
          offenders.push(s.id + "." + f.id + " defaults to " + JSON.stringify(f.options[0]));
        }
      }
    }
    check("every select offers an unanswered state",
      offenders.length === 0,
      offenders.join("; ") + " — a default the interface DISPLAYS must not " +
      "become a fact the record HOLDS");
  }

  /* ═══ 9. EVERY REPEATABLE SECTION, NOT JUST PARENTS ════════════════════
     The sections do not each have a save path — they share one. That is why
     the missing father was never a Parents bug: the mechanism served every
     repeatable section, and Parents is simply where somebody happened to
     enter two people.

     So the repair is shared and the TEST must not be. The list is read from
     the shipping SECTIONS rather than written here, because a list written
     here would not grow when a section is added — and "it works for Parents"
     is exactly the reasoning that let this ship. */
  {
    const h0 = createHarness();
    const repeatables = h0.qq.SECTIONS.filter((s) => s.repeatable);
    scenario(`9. two entries in each of the ${repeatables.length} repeatable sections`);

    check("there is more than one repeatable section to cover",
      repeatables.length > 1,
      "if this drops to one, the enumeration has broken, not the form");

    for (const section of repeatables) {
      const h = createHarness().setNarrator(PID);
      h.restore(PID);
      await h.settle();

      const textFields = section.fields.filter((f) => f.type === "text" || f.type === "textarea");
      if (textFields.length < 1) {
        check(`${section.id}: has a free-text field to test with`, false,
          "cannot drive this section without one; needs a bespoke case");
        continue;
      }
      const probe = textFields[0].id;

      h.render(section.id);
      h.typeEntry(0, probe, "FIRST-" + section.id);
      h.save(section.id);
      await h.settle();

      h.addEntry(section.id);
      await h.settle();
      h.render(section.id);
      h.typeEntry(1, probe, "SECOND-" + section.id);
      h.save(section.id);
      await h.settle();

      const stored = (h.server.stored(PID) || {})[section.id] || [];
      const values = (Array.isArray(stored) ? stored : [stored]).map((e) => e && e[probe]);

      check(`${section.id}: both entries stored (${probe})`,
        values.indexOf("FIRST-" + section.id) !== -1 &&
        values.indexOf("SECOND-" + section.id) !== -1,
        "stored " + JSON.stringify(values) + " — a second entry in this " +
        "section is discarded, the same defect the operator hit in Parents");
    }
  }

  /* ═══ 10. WO-01 — ONE QUESTIONNAIRE, ONE HOME PER ANSWER ═══════════════
     The three-section form, its flag, and the migration that moved six
     sections under `_legacyRemovedSections` on every restore and save are
     gone. These are the work order's acceptance criteria, run against the
     shipping code rather than read from it. */
  {
    scenario("10. WO-01: every section renders, and no save emits a legacy key");
    const h = createHarness().setNarrator(PID);
    h.restore(PID);
    await h.settle();

    check("SECTIONS has sixteen entries and no second definition",
      h.qq.SECTIONS.length === 16 && h.qq.FULL_SECTIONS === undefined && h.qq.MINIMAL_SECTIONS === undefined,
      "found " + h.qq.SECTIONS.length);

    let rendered = 0;
    for (const s of h.qq.SECTIONS) {
      h.render(s.id);
      if (h.fields().length > 0) rendered++;
    }
    check("all sixteen sections render editable fields", rendered === 16, rendered + " rendered");

    // Save something in one of the six formerly-migrated sections, then in
    // an unrelated one. Before WO-01 the second save carried grandparents
    // under the legacy key and the server kept both copies.
    h.render("grandparents");
    h.typeEntry(0, "firstName", "Ervin"); h.typeEntry(0, "lastName", "Horne");
    h.save("grandparents"); await h.settle();
    h.render("personal");
    h.type("bbQ_fullName", "Kent Horne");
    h.save("personal"); await h.settle();

    const legacyPuts = h.server.puts.filter((p) =>
      p.questionnaire && (p.questionnaire._legacyRemovedSections !== undefined ||
                          p.questionnaire._legacyMigrationVersion !== undefined));
    check("no PUT carried _legacyRemovedSections or _legacyMigrationVersion",
      legacyPuts.length === 0, legacyPuts.length + " of " + h.server.puts.length + " did");

    const stored = h.server.stored(PID) || {};
    check("grandparents live at the top level only",
      Array.isArray(stored.grandparents) && stored.grandparents[0].firstName === "Ervin" &&
      stored._legacyRemovedSections === undefined,
      JSON.stringify(Object.keys(stored)));

    check("the migration function is not exported",
      h.qq._migrateRemovedSectionsToLegacy === undefined);
  }

  {
    scenario("10b. WO-01: a two-entry section survives a narrator switch and return");
    const OTHER = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2";
    const h = createHarness().setNarrator(PID);
    h.restore(PID); await h.settle();
    h.render("parents"); fillEntry(h, 0, MOTHER); h.save("parents"); await h.settle();
    h.addEntry("parents"); await h.settle(); h.render("parents"); fillEntry(h, 1, FATHER);
    h.save("parents"); await h.settle();

    h.setNarrator(OTHER); h.restore(OTHER); await h.settle();
    h.setNarrator(PID);   h.restore(PID);   await h.settle();
    h.render("parents");

    check("both parents are still on the form after switching away and back",
      h.entryCount() === 2 && h.valueOf("bbQ_1_firstName") === "Bertil",
      "entries=" + h.entryCount());
    check("both are still stored", parentsOf(h.server.stored(PID)).length === 2);
    check("nothing leaked into the other narrator",
      (h.server.stored(OTHER) || {}).parents === undefined);
  }

  /* ═══ 11. WO-02 — STABLE ENTRY IDS ════════════════════════════════════
     Enables: a correction can be applied to the person it was made against.
     That is the foundation provenance (WO-03) and deletion (WO-04) stand on,
     and the reason a later correction can reach Lori attached to the right
     relative rather than to whoever now occupies index 1. */
  {
    scenario("11. an id is minted on save, only for an entry with an answer");
    const h = createHarness().setNarrator(PID);
    h.restore(PID); await h.settle();

    h.render("parents");
    fillEntry(h, 0, MOTHER);
    h.save("parents"); await h.settle();

    const p0 = parentsOf(h.server.stored(PID))[0];
    check("a saved entry carries an id", !!(p0 && p0._entryId), JSON.stringify(p0 && Object.keys(p0)));
    check("the id is not the index", p0 && !/^\d+$/.test(String(p0._entryId)));

    const firstId = p0._entryId;
    h.render("parents");
    h.typeEntry(0, "occupation", "headmistress");
    h.save("parents"); await h.settle();
    check("the id is NOT regenerated on a later save",
      parentsOf(h.server.stored(PID))[0]._entryId === firstId,
      "an id that changes every save identifies nothing");
    check("the edit landed", parentsOf(h.server.stored(PID))[0].occupation === "headmistress");

    h.addEntry("parents"); await h.settle();
    h.render("parents");
    h.save("parents"); await h.settle();
    const after = parentsOf(h.server.stored(PID));
    check("a blank added entry gets NO id and is not stored as a person",
      after.length === 1,
      "stored " + after.length + " — an id alone must not make a person exist");
    check("the blank row is still on the form", h.entryCount() === 2,
      "the operator clicked add; the row must not vanish from under them");
  }

  {
    scenario("11b. THE REORDER TEST — a correction reaches the person it was made against");
    const h = createHarness().setNarrator(PID);
    h.restore(PID); await h.settle();

    h.render("parents"); fillEntry(h, 0, MOTHER); h.save("parents"); await h.settle();
    h.addEntry("parents"); await h.settle();
    h.render("parents"); fillEntry(h, 1, FATHER); h.save("parents"); await h.settle();

    let stored = parentsOf(h.server.stored(PID));
    check("both parents stored with distinct ids",
      stored.length === 2 && stored[0]._entryId && stored[1]._entryId &&
      stored[0]._entryId !== stored[1]._entryId);
    const ingridId = stored[0]._entryId, bertilId = stored[1]._entryId;

    // The form is open, showing Ingrid at 0 and Bertil at 1.
    h.render("parents");
    check("the form carries each entry's id",
      h.valueOf("bbQ_0__entryId") === ingridId && h.valueOf("bbQ_1__entryId") === bertilId);

    /* Now the stored order changes underneath the open form — another tab, a
       restore, any future reorder control. The DOM still shows Ingrid first;
       storage now holds Bertil first. Before WO-02 the save merged DOM index
       0 onto stored index 0, and Ingrid's correction would have been written
       onto Bertil. */
    const mem = h.memory();
    mem.parents = [mem.parents[1], mem.parents[0]];
    h.setDraft(PID, JSON.parse(JSON.stringify(mem)));
    h.server.docs[PID].doc.parents = [h.server.docs[PID].doc.parents[1], h.server.docs[PID].doc.parents[0]];

    // The operator corrects the entry they are looking at — Ingrid's, at index 0.
    h.typeEntry(0, "occupation", "headmistress");
    h.save("parents"); await h.settle();

    stored = parentsOf(h.server.stored(PID));
    const ingrid = stored.find((p) => p._entryId === ingridId);
    const bertil = stored.find((p) => p._entryId === bertilId);

    check("both people still exist after the reorder", !!ingrid && !!bertil,
      "ids: " + JSON.stringify(stored.map((p) => p._entryId)));
    check("the correction reached INGRID — the person it was made against",
      ingrid && ingrid.occupation === "headmistress",
      "Ingrid.occupation = " + (ingrid && ingrid.occupation));
    check("BERTIL was not touched by a correction meant for someone else",
      bertil && bertil.occupation === FATHER.occupation,
      "Bertil.occupation = " + (bertil && bertil.occupation) +
      " — this is the failure the ids exist to prevent");
    check("neither person's other answers were disturbed",
      ingrid && ingrid.firstName === "Ingrid " && bertil && bertil.firstName === "Bertil");
  }

  {
    /* The save is not the only path that commits DOM values onto stored
       entries — _addRepeatEntry does it too, before appending a blank row,
       so the operator's in-progress typing is not lost when they click "add
       another". It carries the identical risk and needs the identical proof.
       Without this, reverting _addRepeatEntry to ordinal matching broke
       nothing in the suite: the reorder test above only exercises save. */
    scenario("11b-add. the same, when the operator clicks 'add another' mid-edit");
    const h = createHarness().setNarrator(PID);
    h.restore(PID); await h.settle();
    h.render("parents"); fillEntry(h, 0, MOTHER); h.save("parents"); await h.settle();
    h.addEntry("parents"); await h.settle();
    h.render("parents"); fillEntry(h, 1, FATHER); h.save("parents"); await h.settle();

    let stored = parentsOf(h.server.stored(PID));
    const ingridId = stored[0]._entryId, bertilId = stored[1]._entryId;

    h.render("parents");
    // Typing, not yet saved.
    h.typeEntry(0, "occupation", "headmistress");

    // Storage reorders underneath the open form.
    const doc = h.server.docs[PID].doc;
    doc.parents = [doc.parents[1], doc.parents[0]];
    h.setDraft(PID, JSON.parse(JSON.stringify(doc)));

    // The operator clicks "add another" — which commits what they typed.
    h.addEntry("parents"); await h.settle();

    /* Inspect MEMORY here, before saving. A save afterwards is itself
       id-aware and re-reads the same DOM, so it would repair whatever the
       add path got wrong — which is exactly why the first version of this
       check could not fail. The defect has to be caught where it happens. */
    const mem = parentsOf(h.memory());
    const ingrid = mem.find((p) => p && p._entryId === ingridId);
    const bertil = mem.find((p) => p && p._entryId === bertilId);
    check("the in-progress edit reached Ingrid",
      ingrid && ingrid.occupation === "headmistress",
      "Ingrid.occupation = " + (ingrid && ingrid.occupation));
    check("Bertil's occupation is untouched by it",
      bertil && bertil.occupation === FATHER.occupation,
      "Bertil.occupation = " + (bertil && bertil.occupation) +
      " — the add path wrote one person's typing onto another");
    check("Bertil's name was not overwritten either",
      bertil && bertil.firstName === "Bertil",
      "the commit loop writes EVERY field from the DOM row, not just the edited one");
  }

  {
    scenario("11c. a pre-WO-02 entry keeps its answers and gains one id");
    const h = createHarness().setNarrator(PID);
    // A document written before this work order: no ids anywhere.
    h.server.seed(PID, { parents: [
      { relation: "Mother", firstName: "Ingrid ", occupation: "schoolteacher" },
      { relation: "Father", firstName: "Bertil", occupation: "ore dock foreman" },
    ] }, 3);
    h.setNarrator(PID);
    h.restore(PID); await h.settle();
    h.render("parents");

    check("the legacy entries render", h.entryCount() === 2);
    check("the form shows no id for them",
      h.valueOf("bbQ_0__entryId") === "" && h.valueOf("bbQ_1__entryId") === "");

    h.save("parents"); await h.settle();
    const stored = parentsOf(h.server.stored(PID));

    check("each legacy entry gained exactly one id",
      stored.length === 2 && stored[0]._entryId && stored[1]._entryId &&
      stored[0]._entryId !== stored[1]._entryId);
    check("every existing answer is unchanged",
      stored[0].firstName === "Ingrid " && stored[0].occupation === "schoolteacher" &&
      stored[1].firstName === "Bertil" && stored[1].occupation === "ore dock foreman");
    check("order is preserved",
      stored[0].relation === "Mother" && stored[1].relation === "Father",
      "order carries meaning in bio_questionnaire_writer's first-father-wins");

    const ids = stored.map((p) => p._entryId);
    h.render("parents");
    h.save("parents"); await h.settle();
    check("a second save does not re-mint",
      JSON.stringify(parentsOf(h.server.stored(PID)).map((p) => p._entryId)) === JSON.stringify(ids));
  }

  {
    /* CONSTRUCTED, not reached through the UI — labelled as such.

       Nothing in the current code produces two entries with the same id, so
       this state is built directly.

       The first version of this scenario asserted that the second row did
       not inherit a stored-only field from the first. That passed with the
       guard AND without it — every field in a section is rendered and read
       back, so `prev` contributes nothing the DOM does not already carry.
       An assertion that cannot fail is not a test, and running it both ways
       is what exposed that.

       A second version HEALED the collision — first row keeps the id, second
       is minted a fresh one. Review rejected that, correctly: it is the
       system deciding on its own initiative that one of two real people is
       now somebody else, and if a correction had already been made against
       that id it would silently attach to whichever row came first.

       What it does now: an id appearing twice is unusable for matching.
       Those rows fall back to their ordinal — what the operator is looking
       at — both entries keep every answer, NEITHER id is changed, nothing is
       merged, and the collision is reported for a person to resolve. */
    scenario("11c-dup. a duplicated id is preserved and reported, never guessed (constructed)");
    const h = createHarness().setNarrator(PID);
    h.server.seed(PID, { parents: [
      { _entryId: "e_dup", relation: "Mother", firstName: "Ingrid " },
      { _entryId: "e_dup", relation: "Father", firstName: "Bertil" },
    ] }, 3);
    h.setNarrator(PID);
    h.restore(PID); await h.settle();
    h.render("parents");

    check("both rows render and both carry the duplicated id",
      h.entryCount() === 2 &&
      h.valueOf("bbQ_0__entryId") === "e_dup" && h.valueOf("bbQ_1__entryId") === "e_dup");

    // Distinguish the two people by a field only one of them has, so the
    // assertions below are about the STORED result and not about the DOM
    // echoing back what it was given.
    h.typeEntry(0, "occupation", "schoolteacher");
    h.save("parents"); await h.settle();
    const stored = parentsOf(h.server.stored(PID));

    check("two entries remain — neither row collapsed into the other",
      stored.length === 2, "stored " + stored.length);
    check("BOTH ids are unchanged — neither person was renamed by the system",
      stored[0] && stored[1] &&
      stored[0]._entryId === "e_dup" && stored[1]._entryId === "e_dup",
      "ids: " + JSON.stringify(stored.map((p) => p && p._entryId)) +
      " — reassigning one is the system deciding who somebody is");
    check("each person kept their own answers",
      stored[0] && stored[0].firstName === "Ingrid " &&
      stored[1] && stored[1].firstName === "Bertil");
    check("the edit landed on the row it was typed into, and only there",
      stored[0] && stored[0].occupation === "schoolteacher" &&
      stored[1] && !stored[1].occupation,
      "Bertil.occupation = " + (stored[1] && stored[1].occupation));
    check("the collision is reported to the operator, not swallowed",
      (() => {
        const b = h.banner();
        return b !== null && /sharing one identity/i.test(b.text) && /e_dup/.test(b.text);
      })(),
      "an ambiguous record that says nothing is how a correction reaches the " +
      "wrong person later");
  }

  {
    scenario("11d. ids survive a narrator switch and a reload");
    const OTHER = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2";
    const h = createHarness().setNarrator(PID);
    h.restore(PID); await h.settle();
    h.render("parents"); fillEntry(h, 0, MOTHER); h.save("parents"); await h.settle();
    const id0 = parentsOf(h.server.stored(PID))[0]._entryId;

    h.setNarrator(OTHER); h.restore(OTHER); await h.settle();
    h.setNarrator(PID); h.restore(PID); await h.settle();
    h.render("parents");
    check("the id is the same after switching away and back",
      h.valueOf("bbQ_0__entryId") === id0);

    // A fresh harness against the same server row = a reload in a new browser.
    const h2 = createHarness().setNarrator(PID);
    h2.server.seed(PID, h.server.stored(PID), 9);
    h2.setNarrator(PID); h2.restore(PID); await h2.settle();
    h2.render("parents");
    check("and the same after a reload in a different browser",
      h2.valueOf("bbQ_0__entryId") === id0);
  }

  {
    scenario("11e. every repeatable section mints ids");
    const h0 = createHarness();
    for (const section of h0.qq.SECTIONS.filter((s) => s.repeatable)) {
      const h = createHarness().setNarrator(PID);
      h.restore(PID); await h.settle();
      const probe = (section.fields.find((f) => f.type === "text" || f.type === "textarea") || {}).id;
      if (!probe) { check(`${section.id}: has a text field`, false); continue; }
      h.render(section.id);
      h.typeEntry(0, probe, "X-" + section.id);
      h.save(section.id); await h.settle();
      const arr = (h.server.stored(PID) || {})[section.id] || [];
      check(`${section.id}: entry carries an id`,
        Array.isArray(arr) && arr[0] && !!arr[0]._entryId);
    }
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
