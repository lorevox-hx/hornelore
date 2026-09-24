/* WO-BIO-VIEW-SAFETY-01 — a partial questionnaire must not delete family
   from the persisted graph.

   THE DEFECT, AND WHY IT IS THE 2026-09-15 DEFECT ONE LAYER OUT.

   `merge_whole_document` repaired the questionnaire's persistence with one
   rule: a key the caller omitted is left standing, not deleted. The family
   graph never had that rule. A graph rebuild was a clear-then-recreate:
   `_clearBySource(g, "questionnaire")` removed every questionnaire-sourced
   record, the rebuild recreated whatever the in-memory document mentioned,
   and `persistToBackend()` sent the result as a FULL REPLACEMENT.

   Measured 2026-09-21: under HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1 the
   hydrating GET returns a three-leaf projection rather than the record, so
   one deliberate save put four of a real narrator's grandparents and four
   relationships one step from deletion.

   THE FIRST FIX WAS ALSO WRONG, AND THAT IS WHY THIS SUITE IS SHAPED THIS
   WAY. It cleared only sections the document could rebuild — which still
   deleted a father when the document carried the mother alone, since both
   are `questionnaire:parents`. Section granularity against person-level
   records is the same omission-as-deletion defect at a smaller radius, and
   an entry id with no name counted as "content". It passed twelve checks
   of its own because none of them exercised one missing record WITHIN a
   present section. Case 3 below is that case.

   WHY THIS DRIVES THE REAL PIPELINE. The previous suite lifted three guard
   functions and asserted against a payload the TEST built. That
   establishes guard behaviour and not the claim that matters — what goes
   over the wire and replaces the stored graph. This loads the shipped
   module whole, runs the real `syncFromQuestionnaire` and
   `persistToBackend`, and asserts on the captured PUT body.

   FICTIONAL RECORDS THROUGHOUT. The real narrator whose grandparents sat
   in the blast radius is not a fixture. */

"use strict";

const fs = require("fs");
const path = require("path");

let pass = 0, fail = 0;
function check(name, ok, why) {
  if (ok) { console.log("  ok    " + name); pass++; }
  else { console.log("  FAIL  " + name + "\n        " + why); fail++; }
}

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "ui", "js", "bio-builder-graph.js"), "utf8");

/* ── load the shipped module against a fake browser ────────────────── */
function loadGraphModule() {
  const captured = { puts: [], gets: [], refused: [] };
  /* A FAKE SERVER THAT ENFORCES THE REVISION, as the real one does since
     Batch B-4 (db.graph_replace_full): a PUT without a revision is 428, a
     PUT from a stale revision is 409, an accepted PUT bumps it. `puts`
     holds ACCEPTED replacements only — what actually reached storage. */
  const server = { rev: 0 };
  /* Pending GETs are held PER REQUEST, keyed by the person_id in the url.
     A single shared resolver was the first version, and narrator B's GET
     then overwrote narrator A's — so A's promise never settled and the
     late-response case could not be exercised at all. The test must be
     able to choose which in-flight request answers, and when. */
  const pendingGets = [];

  const bb = { personId: null, questionnaire: {}, graph: null };
  const hooks = [];
  const win = {
    LorevoxBioBuilderModules: {
      core: {
        _bb: () => bb,
        _uid: (() => { let n = 0; return () => "uid_" + (++n); })(),
        /* Captured, not discarded. The module registers its narrator-switch
           handler here rather than exporting it, so a no-op stub makes that
           handler unreachable and its test unwritable. */
        _registerPostSwitchHook: (fn) => hooks.push(fn),
      },
    },
  };
  const API = {
    GRAPH_GET: (pid) => "/api/bio-builder/graph?person_id=" + pid,
    GRAPH_PUT: (pid) => "/api/bio-builder/graph?person_id=" + pid,
  };
  const fetchImpl = (url, opts) => {
    if (opts && opts.method === "PUT") {
      const body = JSON.parse(opts.body);
      const code = typeof body.revision !== "number" ? 428
                 : body.revision !== server.rev ? 409 : 200;
      if (code !== 200) {
        captured.refused.push({ url, body, status: code });
        return Promise.resolve({ ok: false, status: code, text: () => Promise.resolve("") });
      }
      server.rev += 1;
      captured.puts.push({ url, body });
      return Promise.resolve({ ok: true, status: 200,
                               json: () => Promise.resolve({ revision: server.rev }) });
    }
    captured.gets.push(url);
    return new Promise((res) => { pendingGets.push({ url: url, resolve: res }); });
  };

  // eslint-disable-next-line no-new-func
  new Function("window", "API", "fetch", "console", "state", SRC)(
    win, API, fetchImpl, console, undefined);

  const mod = win.LorevoxBioBuilderModules.graph;
  if (!mod) throw new Error("the shipped module did not export its graph API");
  return {
    mod, bb, captured, hooks, server,
    pendingCount: () => pendingGets.length,
    onNarratorSwitch: (b) => hooks.forEach((fn) => fn(b)),
    /* Release one in-flight GET. `match` selects by url substring (a
       narrator id) or, when a NUMBER, by position in flight — needed when
       two requests carry the SAME narrator, where a substring match cannot
       tell them apart and picking the wrong one deadlocks the test. */
    releaseGet: (payload, match, status) => {
      const i = typeof match === "number"
        ? match
        : (match ? pendingGets.findIndex((g) => g.url.indexOf(match) !== -1) : 0);
      if (i < 0) throw new Error("no in-flight GET matching " + match +
        " (in flight: " + JSON.stringify(pendingGets.map((g) => g.url)) + ")");
      const g = pendingGets.splice(i, 1)[0];
      const code = status || 200;
      const withRev = payload && typeof payload === "object" && !("revision" in payload)
        ? Object.assign({ revision: server.rev }, payload) : payload;
      g.resolve({ ok: code >= 200 && code < 300, status: code,
                  json: () => Promise.resolve(withRev) });
    },
  };
}

/* Hydrate as production does before any save: the switch hook's GET, here
   answered with `payload` (an empty family by default). A PUT from a graph
   that never hydrated is refused client-side — there is no revision to send. */
async function hydrate(h, payload) {
  const restoring = h.mod.restoreFromBackend(h.bb.personId);
  h.releaseGet(payload || { persons: [], relationships: [] });
  await restoring;
}
const tick = () => new Promise((r) => setTimeout(r, 0));
/* Bounded wait: a mutant that leaves a request hanging must FAIL a check,
   not hang the suite until an outer timeout kills it without a message. */
const settle = (p, ms) => Promise.race([p, new Promise((r) => setTimeout(r, ms || 50))]);

const h0 = loadGraphModule();
check("the shipped graph module loads and exports its API",
  typeof h0.mod.fullSync === "function" &&
  typeof h0.mod.syncFromQuestionnaire === "function" &&
  typeof h0.mod.persistToBackend === "function",
  "this suite must exercise product code through its real entry points, not lifted helpers");

const NARRATOR = "aaaaaaaa-1111-1111-1111-111111111111";

/* The complete record: a fictional narrator with two parents and two
   grandparents. Nothing about a real family. */
const FULL_QUESTIONNAIRE = {
  personal: { fullName: "Mireia Vasquez", dateOfBirth: "1941-03-02", placeOfBirth: "Girona" },
  parents: [
    { relation: "Mother", firstName: "Alba",  lastName: "Vasquez", occupation: "Cartographer" },
    { relation: "Father", firstName: "Tomas", lastName: "Vasquez", occupation: "Boatwright" },
  ],
  grandparents: [
    { side: "Maternal", firstName: "Sigrid",  lastName: "Lindqvist" },
    { side: "Maternal", firstName: "Halvard", lastName: "Lindqvist" },
  ],
};

/* THE STORED GRAPH IS DERIVED, NOT DECLARED.
   Built by running the SHIPPED sync over the complete questionnaire and
   capturing what it persists. An earlier version of this suite hand-wrote
   the stored records with invented ids ("gp_m"), but production mints ids
   from `_stablePersonId(narrator, name)` — so the rebuild did not recognise
   the fixture's rows and created DUPLICATES instead of updating them. The
   preservation checks passed while the graph silently doubled, which is the
   fixture-supplies-the-property failure this repository has named. Deriving
   it means the ids are whatever production actually uses. */
async function deriveStoredGraph() {
  const h = loadGraphModule();
  h.bb.personId = NARRATOR;
  h.bb.graph = { persons: {}, relationships: {} };
  await hydrate(h);
  h.bb.questionnaire = FULL_QUESTIONNAIRE;
  h.mod.syncFromQuestionnaire();
  await h.mod.persistToBackend();
  if (!h.captured.puts.length) throw new Error("could not derive a stored graph");
  const body = JSON.parse(JSON.stringify(h.captured.puts[0].body));
  delete body.revision;   // a PUT body's baseline is not the stored graph's revision
  // One profile-sourced record, which no questionnaire sync may ever touch.
  body.persons.push({ id: "gp_prof", display_name: "Nuria Vasquez", source: "profile",
                      provenance: "profile:kinship" });
  body.relationships.push({ id: "r_prof", from_person_id: body.persons[0].id,
                            to_person_id: "gp_prof", relationship_type: "sibling",
                            source: "profile", provenance: "profile:kinship" });
  return body;
}

let STORED_GRAPH = null;

(async function run() {
  STORED_GRAPH = await deriveStoredGraph();

check("the derived fixture holds the whole family before any partial view",
  ["Alba Vasquez", "Tomas Vasquez", "Sigrid Lindqvist", "Halvard Lindqvist", "Nuria Vasquez"]
    .every((n) => STORED_GRAPH.persons.some((p) => p.display_name === n)),
  "the fixture must start complete or the preservation checks prove nothing: " +
  JSON.stringify(STORED_GRAPH.persons.map((p) => p.display_name)));

/* Restore the stored graph, set a questionnaire, run the REAL sync +
   persist, and hand back the body that actually went over the wire. */
const names = (body) => body.persons.map((p) => p.display_name).filter(Boolean).sort();
const relIds = (body) => body.relationships.map((r) => r.id).sort();

async function persistAfterSync(questionnaire) {
  const h = loadGraphModule();
  h.bb.personId = NARRATOR;
  const restoring = h.mod.restoreFromBackend(NARRATOR);
  h.releaseGet(STORED_GRAPH);
  await restoring;

  h.bb.questionnaire = questionnaire;
  h.mod.syncFromQuestionnaire();
  h.mod.persistToBackend();
  await new Promise((r) => setTimeout(r, 0));

  if (!h.captured.puts.length) throw new Error("persistToBackend sent nothing");
  return h.captured.puts[h.captured.puts.length - 1].body;
}



  /* ── 1. THE MEASURED INCIDENT: a three-leaf projection ───────────── */
  {
    const body = await persistAfterSync({
      personal: { fullName: "Mireia Vasquez", dateOfBirth: "1941-03-02", placeOfBirth: "Girona" },
    });
    check("a three-leaf view persists every established relative",
      ["Alba Vasquez", "Halvard Lindqvist", "Nuria Vasquez", "Sigrid Lindqvist", "Tomas Vasquez"]
        .every((n) => names(body).includes(n)),
      "the PUT carried " + JSON.stringify(names(body)) + ". This is the request that " +
      "REPLACES the stored graph — anything missing here is deleted for good");
    /* Derived from the fixture, not hand-written: the stored relationship
       ids are whatever _stableRelId minted. Asserting invented ids here
       failed against a correct product, which is the same drift the
       fixture comment above describes. */
    const storedRelIds = STORED_GRAPH.relationships.map((r) => r.id).sort();
    check("...and every relationship that was stored",
      storedRelIds.every((r) => relIds(body).includes(r)),
      "missing from the PUT: " +
      JSON.stringify(storedRelIds.filter((r) => !relIds(body).includes(r))));
  }

  /* ── 2. a failed hydration is not a deletion instruction ─────────── */
  {
    const body = await persistAfterSync({});
    check("an empty questionnaire persists every established relative",
      ["Alba Vasquez", "Tomas Vasquez", "Sigrid Lindqvist", "Halvard Lindqvist"]
        .every((n) => names(body).includes(n)),
      "the case READ=0 does NOT protect against: a truncated or failed hydration");
  }

  /* ── 3. THE REVIEW CASE — one record missing WITHIN a present section ─
     A document carrying the mother and not the father. The section is
     populated, so a section-scoped guard authorises clearing it, and the
     rebuild can only recreate the mother. This is the case that failed on
     the first fix, and the reason routine sync no longer deletes at all. */
  {
    const body = await persistAfterSync({
      personal: { fullName: "Mireia Vasquez" },
      parents: [{ relation: "Mother", firstName: "Alba", lastName: "Vasquez" }],
    });
    check("a section carrying only the mother does NOT delete the father",
      names(body).includes("Tomas Vasquez"),
      "the PUT carried " + JSON.stringify(names(body)) + ". A populated section is not " +
      "authorisation to replace every record in it — the rebuild can recreate only what " +
      "the document mentions, so clearing the section deletes the rest");
    check("...and still persists the mother",
      names(body).includes("Alba Vasquez"),
      "the record the document does carry must survive too");
    check("...exactly once — the rebuild updates her, it does not duplicate her",
      names(body).filter((n) => n === "Alba Vasquez").length === 1,
      "got " + names(body).filter((n) => n === "Alba Vasquez").length + " Alba Vasquez rows. " +
      "A pure upsert must recognise the stored record by its stable id; a duplicate means " +
      "the graph grows a second copy of a person on every save");
    check("...and the grandparents it says nothing about",
      names(body).includes("Sigrid Lindqvist") && names(body).includes("Halvard Lindqvist"),
      "got " + JSON.stringify(names(body)));
  }

  /* ── 4. a section holding only bookkeeping ───────────────────────── */
  {
    const body = await persistAfterSync({
      personal: { fullName: "Mireia Vasquez" },
      parents: [{ _entryId: "e_abc" }],
    });
    check("an entry id with no name deletes nobody",
      names(body).includes("Alba Vasquez") && names(body).includes("Tomas Vasquez"),
      "an id is not an answer; it cannot rebuild a person and must not authorise " +
      "removing one");
  }

  /* ── 5. profile-sourced records are never touched ────────────────── */
  {
    const body = await persistAfterSync({
      personal: { fullName: "Mireia Vasquez" },
      parents: [{ relation: "Mother", firstName: "Alba", lastName: "Vasquez" },
                { relation: "Father", firstName: "Tomas", lastName: "Vasquez" }],
      grandparents: [{ side: "Maternal", firstName: "Sigrid", lastName: "Lindqvist" }],
    });
    check("the questionnaire lane never reaches into the profile lane",
      names(body).includes("Nuria Vasquez") && relIds(body).includes("r_prof"),
      "profile:kinship records must survive any questionnaire sync");
  }

  /* ── 6. a late graph response must not land on another narrator ───── */
  {
    const h = loadGraphModule();
    const A = NARRATOR;
    const B = "bbbbbbbb-2222-2222-2222-222222222222";
    h.bb.personId = A;
    const restoringA = h.mod.restoreFromBackend(A);      // A's GET in flight
    h.bb.personId = B;
    h.onNarratorSwitch(h.bb);                            // switch; bumps the generation
    h.releaseGet(STORED_GRAPH, A);                       // A's response arrives LATE
    await restoringA;
    await new Promise((r) => setTimeout(r, 0));

    const inMemory = Object.values((h.bb.graph && h.bb.graph.persons) || {})
      .map((p) => p.displayName).filter(Boolean);
    check("a late graph response is not merged into the new narrator's graph",
      !inMemory.includes("Alba Vasquez") && !inMemory.includes("Tomas Vasquez"),
      "narrator B's graph holds " + JSON.stringify(inMemory) + " — one narrator's " +
      "relatives in another's graph, which the next fullSync would persist under B's id");
  }

  /* ── 7. a STALE response for the SAME narrator must not win ───────
     The pid clause cannot catch this: nobody switched narrator. Two
     refreshes of one narrator, the older answering last. Without the
     generation counter the stale graph overwrites the fresh one, and the
     next fullSync persists it. This case exists because mutation testing
     showed cases 1-6 passing with EITHER half of the guard removed — so
     neither half was pinned. */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    const first  = h.mod.restoreFromBackend(NARRATOR);   // stale request
    const second = h.mod.restoreFromBackend(NARRATOR);   // fresh request

    const FRESH = JSON.parse(JSON.stringify(STORED_GRAPH));
    FRESH.persons = FRESH.persons.map((p) => p.display_name === "Alba Vasquez"
      ? Object.assign({}, p, { occupation: "Harbourmaster" }) : p);

    /* Positional release: both urls name the same narrator. Index 1 is the
       SECOND (fresh) request, index 0 the first (stale). The fresh answer
       lands first; the stale one arrives after it. */
    h.releaseGet(FRESH, 1);
    await second;
    h.releaseGet(STORED_GRAPH, 0);
    await first;
    await new Promise((r) => setTimeout(r, 0));

    const alba = Object.values((h.bb.graph && h.bb.graph.persons) || {})
      .find((p) => p.displayName === "Alba Vasquez");
    check("a stale response for the same narrator does not overwrite a fresher one",
      !!alba && alba.occupation === "Harbourmaster",
      "in-memory Alba shows occupation " + JSON.stringify(alba && alba.occupation) +
      " — the older request won, so the graph reverted to an earlier state and the " +
      "next fullSync would persist that");
  }

  /* ── 8. the narrator changes WITHOUT the graph's switch hook ───────
     Pins the pid clause, which mutation testing showed cases 1-7 did not:
     removing it failed nothing, because the generation counter caught
     every case. This is the one it cannot catch. core's _personChanged
     assigns bb.personId directly and the graph hook is a separate
     registration, so a pid can move with no restore started and no
     generation bump. Without the pid clause the in-flight response for the
     old narrator merges into the new one's graph. */
  {
    const h = loadGraphModule();
    const A = NARRATOR;
    const B = "bbbbbbbb-2222-2222-2222-222222222222";
    h.bb.personId = A;
    const restoringA = h.mod.restoreFromBackend(A);   // A's GET in flight
    h.bb.personId = B;                                // pid moves, no hook, no bump
    h.bb.graph = { persons: {}, relationships: {} };
    h.releaseGet(STORED_GRAPH, 0);                    // A's response arrives
    await restoringA;
    await new Promise((r) => setTimeout(r, 0));

    const inMemory = Object.values((h.bb.graph && h.bb.graph.persons) || {})
      .map((p) => p.displayName).filter(Boolean);
    check("a response is refused when the narrator moved without a switch hook",
      !inMemory.includes("Alba Vasquez") && !inMemory.includes("Tomas Vasquez"),
      "narrator B's graph holds " + JSON.stringify(inMemory) + " — the generation " +
      "counter cannot see a pid assigned outside the switch hook, which is why the " +
      "response must also be checked against who is actually loaded");
  }

  /* ══ IDENTITY: a name can change, a person cannot ══════════════════
     `_stablePersonId` hashes the NAME, so a corrected spelling used to
     mint a new id. While the sync still cleared and rebuilt, that was
     invisible — the old record was deleted. With deletion gone, the same
     correction left the misspelling standing and added a second person:
     measured as "Sigrid Lindquist" AND "Sigrid Lindqvist". Identity now
     resolves through the questionnaire's stable `_entryId`, and existing
     graph ids are PRESERVED so relationships survive untouched. */

  /* Establish a graph from a questionnaire, then re-sync a second document
     over it. Returns the outgoing PUT plus the graph that produced it. */
  async function establishThenSync(first, second) {
    let h = loadGraphModule();
    h.bb.personId = NARRATOR;
    h.bb.graph = { persons: {}, relationships: {} };
    await hydrate(h);
    h.bb.questionnaire = first;
    h.mod.syncFromQuestionnaire();
    await h.mod.persistToBackend();
    const stored = JSON.parse(JSON.stringify(h.captured.puts[0].body));

    h = loadGraphModule();
    h.bb.personId = NARRATOR;
    const restoring = h.mod.restoreFromBackend(NARRATOR);
    h.releaseGet(stored, 0);
    await restoring;
    h.bb.questionnaire = second;
    h.mod.syncFromQuestionnaire();
    h.mod.persistToBackend();
    await new Promise((r) => setTimeout(r, 0));
    return { stored: stored, body: h.captured.puts[h.captured.puts.length - 1].body };
  }

  const qq = (gps) => ({ personal: { fullName: "Mireia Vasquez" }, grandparents: gps });

  /* ── 9. adoption: a legacy record gains the entry id, keeps its id ── */
  {
    const legacy = qq([{ side: "Maternal", firstName: "Sigrid", lastName: "Lindqvist" }]);
    const withId = qq([{ _entryId: "e_sig", side: "Maternal",
                         firstName: "Sigrid", lastName: "Lindqvist" }]);
    const { stored, body } = await establishThenSync(legacy, withId);
    const before = stored.persons.find((p) => p.display_name === "Sigrid Lindqvist");
    const sig = body.persons.filter((p) => p.display_name === "Sigrid Lindqvist");
    check("an entry id is adopted onto the existing record, not a new one",
      sig.length === 1,
      "found " + sig.length + " Sigrid rows — adoption must update in place");
    check("...and the existing graph id is preserved",
      sig.length === 1 && sig[0].id === before.id,
      "id moved from " + (before && before.id) + " to " + (sig[0] && sig[0].id) +
      " — relationship ids are built from person ids, so moving one orphans edges");
    check("...and the entry id is recorded for future resolution",
      sig.length === 1 && sig[0].meta && sig[0].meta.entryId === "e_sig",
      "meta.entryId is the resolution key; without it the next rename duplicates again");
  }

  /* ── 10. THE OBJECTIVE: a rename corrects the record ──────────────── */
  {
    const withId = qq([{ _entryId: "e_sig", side: "Maternal",
                         firstName: "Sigrid", lastName: "Lindquist" }]);
    const renamed = qq([{ _entryId: "e_sig", side: "Maternal",
                          firstName: "Sigrid", lastName: "Lindqvist" }]);
    const { stored, body } = await establishThenSync(withId, renamed);
    const all = body.persons.filter((p) => (p.display_name || "").indexOf("Sigrid") === 0);
    check("correcting a spelling corrects the person, it does not add one",
      all.length === 1 && all[0].display_name === "Sigrid Lindqvist",
      "graph now holds " + JSON.stringify(all.map((p) => p.display_name)));
    const before = stored.persons.find((p) => p.display_name === "Sigrid Lindquist");
    check("...keeping the same graph id through the rename",
      all.length === 1 && all[0].id === before.id,
      "a renamed person must not change identity");
  }

  /* ── 11. relationships survive a rename ──────────────────────────── */
  {
    const withId = qq([{ _entryId: "e_sig", side: "Maternal",
                         firstName: "Sigrid", lastName: "Lindquist" }]);
    const renamed = qq([{ _entryId: "e_sig", side: "Maternal",
                          firstName: "Sigrid", lastName: "Lindqvist" }]);
    const { stored, body } = await establishThenSync(withId, renamed);
    const beforeRels = stored.relationships.map((r) => r.id).sort();
    const afterRels = body.relationships.map((r) => r.id).sort();
    check("a rename leaves every relationship id unchanged",
      JSON.stringify(beforeRels) === JSON.stringify(afterRels),
      "before " + JSON.stringify(beforeRels) + " after " + JSON.stringify(afterRels));
  }

  /* ── 12. THE UNMATCHABLE CASE: legacy entry renamed on first save ──
     No stored entry id, and the name changed in the same save. Both
     records are kept. Not merged, not deleted, not guessed by position. */
  {
    const legacy = qq([{ side: "Maternal", firstName: "Sigrid", lastName: "Lindquist" }]);
    const renamedFirstSave = qq([{ _entryId: "e_new", side: "Maternal",
                                   firstName: "Sigrid", lastName: "Lindqvist" }]);
    const { body } = await establishThenSync(legacy, renamedFirstSave);
    const all = body.persons.filter((p) => (p.display_name || "").indexOf("Sigrid") === 0)
                            .map((p) => p.display_name).sort();
    check("a legacy entry renamed on its first save keeps BOTH records",
      all.length === 2 && all[0] === "Sigrid Lindquist" && all[1] === "Sigrid Lindqvist",
      "got " + JSON.stringify(all) + ". Neither may be deleted and neither may be " +
      "merged by guesswork — the link between them is genuinely absent");
  }

  /* ── 13. reordering does not swap identities ─────────────────────── */
  {
    const two = qq([
      { _entryId: "e_a", side: "Maternal", firstName: "Sigrid",  lastName: "Lindqvist" },
      { _entryId: "e_b", side: "Paternal", firstName: "Halvard", lastName: "Lindqvist" },
    ]);
    const swapped = qq([
      { _entryId: "e_b", side: "Paternal", firstName: "Halvard", lastName: "Lindqvist" },
      { _entryId: "e_a", side: "Maternal", firstName: "Sigrid",  lastName: "Lindqvist" },
    ]);
    const { stored, body } = await establishThenSync(two, swapped);
    const idOf = (set, n) => (set.find((p) => p.display_name === n) || {}).id;
    check("reordering the entries does not move either person's identity",
      idOf(body.persons, "Sigrid Lindqvist") === idOf(stored.persons, "Sigrid Lindqvist") &&
      idOf(body.persons, "Halvard Lindqvist") === idOf(stored.persons, "Halvard Lindqvist"),
      "identity must follow the entry id, never the position");
    check("...and does not duplicate anyone",
      body.persons.filter((p) => (p.display_name || "").indexOf("Lindqvist") > 0).length === 2,
      "got " + JSON.stringify(body.persons.map((p) => p.display_name)));
  }

  /* ── 14. two entries with the SAME name get two records ──────────── */
  {
    const twoSame = qq([
      { _entryId: "e_1", side: "Maternal", firstName: "Sigrid", lastName: "Lindqvist" },
      { _entryId: "e_2", side: "Paternal", firstName: "Sigrid", lastName: "Lindqvist" },
    ]);
    const { body } = await establishThenSync(qq([]), twoSame);
    const sig = body.persons.filter((p) => p.display_name === "Sigrid Lindqvist");
    check("two entries sharing a name resolve to two distinct people",
      sig.length === 2 && sig[0].id !== sig[1].id,
      "got " + sig.length + " record(s). Adoption must not hand one record to two " +
      "entries — grandmothers can share a name");
    check("...each carrying its own entry id",
      sig.length === 2 &&
      new Set(sig.map((p) => p.meta && p.meta.entryId)).size === 2,
      "entry ids: " + JSON.stringify(sig.map((p) => p.meta && p.meta.entryId)));
  }

  /* ── EXPLICIT REMOVAL — the other half of the trade ─────────────────
     Removing _clearBySource made a routine sync unable to delete. That was
     the point. It also removed the only (accidental) way a person ever left
     the graph, and the work order requires that an intentional removal is
     still possible, scoped to that entity, and not resurrected by a later
     sync or a stale draft. These drive the real fullSync with the real
     removal signal and assert the body that goes over the wire. */
  {
    const parents = (list) => ({
      personal: { fullName: "Mireia Vasquez" },
      parents: list,
    });
    const both = parents([
      { _entryId: "p_mother", relation: "Mother", firstName: "Alba",  lastName: "Vasquez" },
      { _entryId: "p_father", relation: "Father", firstName: "Tomas", lastName: "Vasquez" },
    ]);

    // establish both parents
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    h.bb.graph = { persons: {}, relationships: {} };
    await hydrate(h);
    h.bb.questionnaire = both;
    h.mod.fullSync();
    await new Promise((r) => setTimeout(r, 0));
    const before = h.captured.puts[h.captured.puts.length - 1].body;
    const fatherId = (before.persons.find((p) => p.display_name === "Tomas Vasquez") || {}).id;
    const fatherEdges = before.relationships.filter(
      (r) => r.from_person_id === fatherId || r.to_person_id === fatherId).length;

    // the operator removes the father's entry; the mother's card is what is saved
    h.bb.questionnaire = parents([
      { _entryId: "p_mother", relation: "Mother", firstName: "Alba", lastName: "Vasquez" },
    ]);
    h.mod.fullSync({ removedEntryIds: ["p_father"] });
    await new Promise((r) => setTimeout(r, 0));
    const after = h.captured.puts[h.captured.puts.length - 1].body;

    check("an explicit removal takes the father out of the persisted graph",
      !!fatherId && !after.persons.some((p) => p.id === fatherId),
      "father id " + fatherId + " still present: " + JSON.stringify(names(after)));
    check("...and every edge that touched him",
      fatherEdges > 0 && !after.relationships.some(
        (r) => r.from_person_id === fatherId || r.to_person_id === fatherId),
      "before: " + fatherEdges + " edge(s); after: " +
      after.relationships.filter((r) => r.from_person_id === fatherId ||
                                        r.to_person_id === fatherId).length);
    check("...while the mother, who was not removed, is untouched",
      after.persons.some((p) => p.display_name === "Alba Vasquez"),
      "the removal was not scoped to the selected entity");

    // a STALE DRAFT still carrying the father is synced afterwards
    h.bb.questionnaire = both;
    h.mod.fullSync();
    await new Promise((r) => setTimeout(r, 0));
    const stale = h.captured.puts[h.captured.puts.length - 1].body;
    check("a later sync from a stale draft does not resurrect a removed entry",
      !stale.persons.some((p) => p.id === fatherId) &&
      !stale.persons.some((p) => p.display_name === "Tomas Vasquez"),
      "the removed father came back: " + JSON.stringify(names(stale)));
    check("...and the stale draft creates no edge to the removed person",
      !stale.relationships.some((r) => String(r.from_person_id).indexOf("tombstoned:") === 0 ||
                                       String(r.to_person_id).indexOf("tombstoned:") === 0 ||
                                       r.from_person_id === fatherId || r.to_person_id === fatherId),
      "an edge references the removed or tombstoned person");

    /* An entry removed BEFORE it was ever synced — then a stale draft
       carrying it arrives. The only thing standing in the way is the
       tombstone removeByEntryId writes when it finds nobody to remove.

       (Ordering fixed 2026-09-22 on external review: this block was first
       inserted between the stale-draft person check and its "...and no
       edge" follow-on, so that edge check read as belonging HERE while
       inspecting `stale`, and this case had no edge check of its own.) */
    h.mod.fullSync({ removedEntryIds: ["p_uncle_never_synced"] });
    await new Promise((r) => setTimeout(r, 0));
    h.bb.questionnaire = parents([
      { _entryId: "p_mother", relation: "Mother", firstName: "Alba", lastName: "Vasquez" },
      { _entryId: "p_uncle_never_synced", relation: "Guardian", firstName: "Pere", lastName: "Vasquez" },
    ]);
    h.mod.fullSync();
    await new Promise((r) => setTimeout(r, 0));
    const never = h.captured.puts[h.captured.puts.length - 1].body;
    check("an entry removed before it was ever synced stays out when a stale draft brings it",
      !never.persons.some((p) => p.display_name === "Pere Vasquez"),
      "the never-synced-then-removed entry was created by the stale draft: " +
      JSON.stringify(names(never)));
    check("...and that draft creates no edge to the never-synced removed entry",
      !never.relationships.some((r) => String(r.from_person_id).indexOf("tombstoned:") === 0 ||
                                       String(r.to_person_id).indexOf("tombstoned:") === 0),
      "an edge in the never-synced case references a tombstoned person: " +
      JSON.stringify(never.relationships.map((r) => [r.from_person_id, r.to_person_id])));
  }

  /* ── PUT DURING RESTORE — the race the server makes destructive ─────
     The graph PUT is an unconditional full replacement (db.py:7958). A
     persist that fires while the hydrating GET is still in flight used to
     send the partial in-memory graph, and the server replaced the stored
     graph with it. The generation counter did not cover this case. */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    h.bb.graph = { persons: {}, relationships: {} };
    const restoring = h.mod.restoreFromBackend(NARRATOR);       // GET in flight
    h.bb.questionnaire = {
      personal: { fullName: "Mireia Vasquez" },
      parents: [{ relation: "Mother", firstName: "Alba", lastName: "Vasquez" }],
    };
    const persisting = h.mod.fullSync();                          // save DURING restore
    await new Promise((r) => setTimeout(r, 0));
    check("a save during an in-flight restore does not PUT the partial graph",
      h.captured.puts.length === 0,
      h.captured.puts.length + " PUT(s) went out before the restore settled; the first " +
      "would have replaced the stored family with " +
      (h.captured.puts[0] ? JSON.stringify(names(h.captured.puts[0].body)) : "?"));

    h.releaseGet(STORED_GRAPH);                                   // restore arrives
    await restoring; await persisting;
    await new Promise((r) => setTimeout(r, 0));
    const body = h.captured.puts[h.captured.puts.length - 1] && h.captured.puts[h.captured.puts.length - 1].body;
    check("...the queued PUT goes out once the restore has settled",
      h.captured.puts.length === 1, h.captured.puts.length + " PUT(s)");
    check("...and it carries the restored father as well as the saved mother",
      !!body && body.persons.some((p) => p.display_name === "Tomas Vasquez") &&
      body.persons.some((p) => p.display_name === "Alba Vasquez"),
      "persisted: " + (body ? JSON.stringify(names(body)) : "nothing"));
  }

  /* a save queued behind narrator A's restore is DROPPED if the operator
     switches to B before A's restore settles — A is no longer loaded */
  {
    const A = NARRATOR, B = "bbbbbbbb-2222-2222-2222-222222222222";
    const h = loadGraphModule();
    h.bb.personId = A;
    h.bb.graph = { persons: {}, relationships: {} };
    const restoringA = h.mod.restoreFromBackend(A);
    h.bb.questionnaire = { personal: { fullName: "Mireia Vasquez" } };
    const persistingA = h.mod.fullSync();                          // queued behind A's GET
    h.bb.personId = B;
    h.onNarratorSwitch(h.bb);                                       // switch bumps the generation
    h.releaseGet(STORED_GRAPH, A);                                 // A's restore now settles
    await restoringA; await persistingA;
    await new Promise((r) => setTimeout(r, 0));
    check("a persist queued behind A's restore is dropped after a switch to B",
      !h.captured.puts.some((p) => p.url.indexOf(A) !== -1),
      "a PUT went out for the narrator who was switched away from: " +
      JSON.stringify(h.captured.puts.map((p) => p.url)));
  }

  /* ── THE SAME BOUNDARY, THREE MORE WAYS (external review, 2026-09-22) ──
     Each was reproduced against the exported functions before the fix. */

  /* 1. an edit made while the restore is pending must survive the restore */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    h.bb.graph = { persons: {}, relationships: {} };
    const restoring = h.mod.restoreFromBackend(NARRATOR);            // GET pending
    h.bb.questionnaire = {
      personal: { fullName: "Mireia Vasquez" },
      parents: [{ relation: "Mother", firstName: "Alba", lastName: "Vasquez",
                  occupation: "Lighthouse keeper" }],                // NEW value
    };
    const persisting = h.mod.fullSync();
    h.releaseGet(STORED_GRAPH);                                       // OLD: "Cartographer"
    await restoring; await persisting;
    await new Promise((r) => setTimeout(r, 0));
    const body = h.captured.puts[h.captured.puts.length - 1].body;
    const alba = body.persons.find((p) => p.display_name === "Alba Vasquez") || {};
    check("an edit made while the restore was pending survives the restore",
      alba.occupation === "Lighthouse keeper",
      "the queued PUT sent " + JSON.stringify(alba.occupation) +
      " — the older server copy overwrote the operator's edit");
    check("...while untouched records still come from the server",
      body.persons.some((p) => p.display_name === "Tomas Vasquez"),
      "the father, never touched locally, should have been restored");
  }

  /* 1b. YES / NO / NOT SAID must survive a restore as three different things.
     External review (2026-09-22) found an operator's deliberate "No" to
     deceased lost to an older server `true`: the merge skipped any local
     value that was `false`. The obvious fix — let every local false win —
     is also wrong, because the mapping then produced `false` for an ABSENT
     field, which would mark every relative nobody has asked about as living.
     These three cases pin all of it. */
  {
    const storedDeceased = JSON.parse(JSON.stringify(STORED_GRAPH));
    storedDeceased.persons.forEach((p) => { if (p.display_name === "Alba Vasquez") p.deceased = true; });

    async function restoreWhileEditing(motherFields) {
      const h = loadGraphModule();
      h.bb.personId = NARRATOR;
      h.bb.graph = { persons: {}, relationships: {} };
      const restoring = h.mod.restoreFromBackend(NARRATOR);
      h.bb.questionnaire = {
        personal: { fullName: "Mireia Vasquez" },
        parents: [Object.assign({ relation: "Mother", firstName: "Alba", lastName: "Vasquez" },
                                motherFields)],
      };
      const persisting = h.mod.fullSync();
      h.releaseGet(storedDeceased);                       // server says: deceased = true
      await restoring; await persisting;
      await new Promise((r) => setTimeout(r, 0));
      const body = h.captured.puts[h.captured.puts.length - 1].body;
      return (body.persons.find((p) => p.display_name === "Alba Vasquez") || {}).deceased;
    }

    const saidNo = await restoreWhileEditing({ deceased: "No" });
    check("an explicit No made during a pending restore survives it",
      saidNo === false,
      "the operator answered No; the older server copy's `true` was sent instead (" +
      JSON.stringify(saidNo) + ")");

    const notSaid = await restoreWhileEditing({});
    check("...while a field nobody answered does not overwrite the server's value",
      notSaid === true,
      "an ABSENT deceased field was sent as " + JSON.stringify(notSaid) +
      " — omission must not mark someone living");

    const saidYes = await restoreWhileEditing({ deceased: "Yes" });
    check("...and an explicit Yes survives as Yes",
      saidYes === true, "got " + JSON.stringify(saidYes));
  }

  /* 2. a FAILED restore must not release a partial full-replacement */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    h.bb.graph = { persons: {}, relationships: {} };
    const restoring = h.mod.restoreFromBackend(NARRATOR);
    h.bb.questionnaire = { personal: { fullName: "Mireia Vasquez" },
      parents: [{ relation: "Mother", firstName: "Alba", lastName: "Vasquez" }] };
    const persisting = h.mod.fullSync();                              // queued
    h.releaseGet(null, 0, 503);                                       // restore FAILS
    await restoring; await persisting;
    await new Promise((r) => setTimeout(r, 0));
    check("a save queued behind a FAILED restore sends nothing",
      h.captured.puts.length === 0,
      h.captured.puts.length + " PUT(s) went out after a 503 — a partial graph as a " +
      "full replacement is the original data-loss mechanism");

    h.mod.fullSync();                                                 // a later, plain save
    await new Promise((r) => setTimeout(r, 0));
    check("...and a later plain save still refuses while the graph never hydrated",
      h.captured.puts.length === 0,
      h.captured.puts.length + " PUT(s) — the failed hydration was forgotten");

    const again = h.mod.restoreFromBackend(NARRATOR);                 // a restore succeeds
    h.releaseGet(STORED_GRAPH);
    await again;
    h.mod.fullSync();
    await new Promise((r) => setTimeout(r, 0));
    check("...until a restore succeeds, after which saving resumes with the full family",
      h.captured.puts.length === 1 &&
      h.captured.puts[0].body.persons.some((p) => p.display_name === "Tomas Vasquez"),
      h.captured.puts.length + " PUT(s); persisted: " +
      (h.captured.puts[0] ? JSON.stringify(names(h.captured.puts[0].body)) : "nothing"));
  }

  /* 3. narrator changes WITHOUT the switch hook (generation unmoved) */
  {
    const A = NARRATOR, B = "bbbbbbbb-2222-2222-2222-222222222222";
    const h = loadGraphModule();
    h.bb.personId = A;
    h.bb.graph = { persons: {}, relationships: {} };
    const restoringA = h.mod.restoreFromBackend(A);
    /* The narrow window: A's restore SUCCEEDS (narrator still A when the
       response lands), and only then — before the queued PUT continuation
       runs — does the active narrator move, with no switch hook and so no
       generation bump. Registered BEFORE fullSync so it runs first. If the
       id moved before the response instead, the restore would discard
       itself as stale and the outcome guard would catch it; that is the
       other case, already covered above. */
    restoringA.then(() => {
      h.bb.personId = B;
      h.bb.graph = { persons: { gp_b: { id: "gp_b", displayName: "Someone Of B" } }, relationships: {} };
    });
    h.bb.questionnaire = { personal: { fullName: "Mireia Vasquez" } };
    const persistingA = h.mod.fullSync();                              // queued behind A's GET
    h.releaseGet(STORED_GRAPH, A);
    await restoringA; await persistingA;
    await new Promise((r) => setTimeout(r, 0));
    check("a queued PUT is dropped when the narrator id moved without the switch hook",
      !h.captured.puts.some((p) => p.url.indexOf(A) !== -1),
      "narrator B's graph was sent to narrator A's endpoint: " +
      JSON.stringify(h.captured.puts.map((p) => [p.url, names(p.body)])));
  }

  /* ══ THE SERVER REVISION (Batch B-4, 2026-09-23) ═══════════════════
     The browser's guards above are local; the server now refuses a full
     replacement that is not based on the graph's current revision. These
     drive the real module against a fake server that enforces it. */

  /* R1. a graph that never hydrated sends no replacement at all */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    h.bb.graph = { persons: {}, relationships: {} };
    h.bb.questionnaire = FULL_QUESTIONNAIRE;
    await h.mod.fullSync();
    await tick();
    check("a graph with no known server revision sends no full replacement",
      h.captured.puts.length === 0 && h.captured.refused.length === 0,
      h.captured.puts.length + " accepted, " + h.captured.refused.length + " refused — a " +
      "PUT with no baseline cannot know what it would erase");
  }

  /* R2. consecutive saves carry the revision the previous save returned */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    await hydrate(h, STORED_GRAPH);
    h.bb.questionnaire = FULL_QUESTIONNAIRE;
    const first = h.mod.fullSync();
    const second = h.mod.fullSync();                    // fired before the first answers
    await settle(Promise.all([first, second]));
    check("two saves in a row are both accepted, each on the revision before it",
      h.captured.puts.length === 2 && h.captured.refused.length === 0 &&
      h.captured.puts[0].body.revision === 0 && h.captured.puts[1].body.revision === 1,
      "accepted revisions " + JSON.stringify(h.captured.puts.map((p) => p.body.revision)) +
      ", refused " + h.captured.refused.length + " — saves must be serialized on the " +
      "server's revision, not race it");
  }

  /* R3. THE CASE THE GUARD EXISTS FOR: another tab saved first */
  {
    const h = loadGraphModule();
    h.bb.personId = NARRATOR;
    await hydrate(h, STORED_GRAPH);                     // this tab reads revision 0
    h.server.rev = 1;                                   // another tab saves a cousin
    const NEWER = JSON.parse(JSON.stringify(STORED_GRAPH));
    NEWER.persons.push({ id: "gp_cousin", display_name: "Joana Vasquez", source: "manual" });
    h.bb.questionnaire = FULL_QUESTIONNAIRE;
    const saving = h.mod.fullSync();                    // stale: based on revision 0
    await tick();
    check("a save based on a stale revision is refused by the server",
      h.captured.refused.length === 1 && h.captured.refused[0].status === 409 &&
      h.captured.puts.length === 0,
      "refused " + JSON.stringify(h.captured.refused.map((r) => r.status)) +
      ", accepted " + h.captured.puts.length);
    check("...and the client re-reads the graph instead of giving up or overwriting",
      h.pendingCount() === 1,
      h.pendingCount() + " GET(s) in flight after the 409 — without a re-read the edit is " +
      "either lost or, worse, retried blind");
    if (h.pendingCount()) h.releaseGet(NEWER);         // the re-read answers
    await settle(saving);
    const body = h.captured.puts.length ? h.captured.puts[0].body : null;
    check("...the client re-reads and saves ONCE more on the fresh revision",
      h.captured.puts.length === 1 && body.revision === 1,
      h.captured.puts.length + " accepted; revision " + (body && body.revision));
    check("...and the other tab's relative survives the retry",
      !!body && body.persons.some((p) => p.display_name === "Joana Vasquez"),
      "the retried replacement erased the newer edit: " + (body ? JSON.stringify(names(body)) : ""));
  }

  /* the file must be text — a literal control character in a string once
     made grep and git diff treat this module as binary */
  check("the module source contains no NUL bytes",
    SRC.indexOf(String.fromCharCode(0)) === -1,
    "a raw NUL is in the source; use an escape such as \\u001f");

  console.log("");
  if (fail) { console.log("  " + fail + " FAILED"); process.exit(1); }
  console.log("  all " + pass + " checks passed");
})().catch((e) => { console.error("  HARNESS ERROR:", e && e.message); process.exit(1); });
