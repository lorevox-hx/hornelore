/* Drive the REAL review surface against the REAL server's refusals.

   WO-04 addendum. The reviewer's objection was exact:

     "Claude reports successfully testing a corrected acceptance on a
      database copy. That establishes something about the reported test,
      but it does not demonstrate that a person can complete the same
      operation in the actual interface."

   Correct, and a fetch double answering whatever this file invents would
   not fix it — it would test this file's guess at the server's replies.

   SO THE 422 BODIES ARE NOT INVENTED HERE. `verify_review_ui_contract.py`
   calls the real `accept_suggestion_route` against a real SQLite database
   holding real legacy suggestions, captures the HTTPException details it
   raises, and writes them to a fixture. This harness replays those exact
   bodies into ui/js/suggestion-review.js, loaded unmodified, and records
   the request bodies the module sends back. The Python side then feeds
   THOSE bodies to the real route and asserts they are accepted.

   So the assertion is a round trip:

       real server refusal -> real UI -> real request -> real server

   WHAT IS REAL: ui/js/suggestion-review.js and
   ui/js/bio-builder-questionnaire.js (for SECTIONS), executed in jsdom.
   The DOM the operator clicks. The bodies the module builds.

   WHAT IS NOT: the network. `fetch` is a recorder that replays fixture
   responses. It asserts nothing about HTTP itself.
*/

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const FIXTURES = process.argv[2];
const OUT = process.argv[3];

let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch (e) {
  console.error("\n  jsdom is not installed.  npm install\n");
  process.exit(2);
}

const fixtures = JSON.parse(fs.readFileSync(FIXTURES, "utf8"));

let failures = 0;
function check(ok, msg, detail) {
  if (ok) { console.log("    PASS  " + msg); return; }
  failures++;
  console.log("    FAIL  " + msg);
  if (detail !== undefined) console.log("          " + JSON.stringify(detail));
}

function boot() {
  const dom = new JSDOM(
    '<!doctype html><html><body><div id="root"></div></body></html>',
    { url: "http://localhost:8082/", runScripts: "outside-only" }
  );
  const win = dom.window;
  const sandbox = win;

  sandbox.API = {
    IV_PROJ_GET: (pid) => "/api/interview/projection/" + pid,
    IV_PROJ_SUGGEST_ACCEPT: (sid) => "/api/interview/projection/suggestion/" + sid + "/accept",
    IV_PROJ_SUGGEST_DECLINE: (sid) => "/api/interview/projection/suggestion/" + sid + "/decline",
  };

  // SECTIONS, read out of the file that renders the form.
  //
  // The questionnaire MODULE cannot be executed on its own — it pulls
  // two dozen aliases off bio-builder-core and throws without it. What
  // the review surface actually reads is the SECTIONS literal, so that
  // literal is extracted and evaluated, exactly as
  // `server/code/api/services/questionnaire_schema.py` does on the
  // Python side. The DATA is real and comes from the shipping file; the
  // module wrapper is what is skipped.
  const qsrc = fs.readFileSync(
    path.join(ROOT, "ui", "js", "bio-builder-questionnaire.js"), "utf8");
  // The SECTIONS literal references option constants declared above it
  // in the same IIFE, so it cannot be lifted out on its own. The module
  // is run whole, with a permissive stub standing in for
  // bio-builder-core: every alias it pulls is read as a property, and a
  // Proxy answers each one with a no-op function. Nothing in this
  // harness clicks the form, so those aliases are never called — but if
  // one ever is, it returns rather than crashing.
  sandbox.LorevoxBioBuilderModules = {
    core: new Proxy({}, {
      get: (_t, k) => (k === "then" ? undefined : function () { return undefined; }),
      has: () => true,
    }),
  };
  vm.runInContext(qsrc, vm.createContext(sandbox));
  const SECTIONS = ((sandbox.LorevoxBioBuilderModules || {}).questionnaire || {}).SECTIONS;
  if (!Array.isArray(SECTIONS) || SECTIONS.length < 20) {
    throw new Error("SECTIONS loaded as " + ((SECTIONS || []).length) +
                    " sections; expected 20+ — the real form did not load");
  }

  const sent = [];
  let queue = fixtures.queue.slice();
  let step = 0;

  sandbox.fetch = function (url, opts) {
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    if (String(url).indexOf("/accept") !== -1 || String(url).indexOf("/decline") !== -1) {
      sent.push({ url: String(url), body: body });
      const reply = fixtures.replies[step++] || { status: 200, json: { revision: 1 } };
      return Promise.resolve({
        ok: reply.status >= 200 && reply.status < 300,
        status: reply.status,
        text: () => Promise.resolve(JSON.stringify(reply.json)),
        json: () => Promise.resolve(reply.json),
      });
    }
    // the queue re-read
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ projection: { pendingSuggestions: queue } }),
      text: () => Promise.resolve(JSON.stringify({ projection: { pendingSuggestions: queue } })),
    });
  };

  const src = fs.readFileSync(path.join(ROOT, "ui", "js", "suggestion-review.js"), "utf8");
  vm.runInContext(src, vm.createContext(sandbox));
  return { win, sandbox, sent, setQueue: (q) => { queue = q; } };
}

function flush(win, n) {
  // Let the promise chains in _accept settle.
  let p = Promise.resolve();
  for (let i = 0; i < (n || 6); i++) p = p.then(() => {});
  return p;
}

async function run() {
  console.log("\n======================================================================");
  console.log("  REVIEW SURFACE — real module, real server refusals");
  console.log("======================================================================\n");

  for (const scenario of fixtures.scenarios) {
    console.log("  " + scenario.name);
    const { win, sandbox, sent } = boot();
    sandbox.HorneloreSuggestionReview.init("root", fixtures.person_id);
    await flush(win, 8);

    const root = win.document.getElementById("root");
    const sid = scenario.suggestion_id;

    // 1. The card exists and offers Accept.
    const acceptBtn = root.querySelector('[data-accept="' + sid + '"]');
    check(!!acceptBtn, "the card offers an Accept button");
    if (!acceptBtn) { failures++; continue; }
    check(!acceptBtn.disabled || scenario.needs_entry,
          "Accept is enabled (or gated on choosing an entry)");

    // If the destination is repeatable the surface must make us choose.
    if (scenario.needs_entry) {
      const sel = root.querySelector('[data-choose="' + sid + '"]');
      check(!!sel, "a repeatable destination renders the entry picker");
      if (sel) {
        sel.value = "__new__";
        sel.dispatchEvent(new win.Event("change", { bubbles: true }));
        await flush(win, 4);
      }
    }

    // 2. Click Accept -> the server refuses -> the card shows WHY.
    root.querySelector('[data-accept="' + sid + '"]').click();
    await flush(win, 10);

    const note = root.querySelector('[data-refusal="' + sid + '"]');
    check(!!note, "the server's refusal is shown on the card");
    const text = note ? note.textContent : "";
    check(text.indexOf(scenario.expect_reason) !== -1,
          "it shows the server's actual reason (" + scenario.expect_reason + ")",
          text.slice(0, 160));
    check(text.indexOf(scenario.expect_detail_fragment) !== -1,
          "it shows the server's own explanation",
          text.slice(0, 200));

    if (scenario.tier === "acknowledge") {
      check(!!root.querySelector('[data-ack="' + sid + '"]'),
            "an acknowledge card offers 'I have read it'");
      check(!/needs changing|is wrong|incorrect/i.test(text),
            "and does NOT claim the value is wrong", text.slice(0, 160));
      root.querySelector('[data-ack="' + sid + '"]').click();
    } else {
      check(!root.querySelector('[data-ack="' + sid + '"]'),
            "a flagged card offers NO acknowledge button");
      const input = root.querySelector('[data-fixval="' + sid + '"]');
      check(!!input, "a flagged card offers a correction input");
      check(input && input.value === scenario.proposed_value,
            "pre-filled with what Lori proposed, so the person edits rather than retypes",
            input && input.value);
      input.value = scenario.type_instead;
      input.dispatchEvent(new win.Event("input", { bubbles: true }));
      root.querySelector('[data-fix="' + sid + '"]').click();
    }
    await flush(win, 10);

    // 3. What did the module actually send?
    const last = sent[sent.length - 1];
    check(!!last, "a second request was sent");
    if (last) {
      console.log("      -> " + JSON.stringify(last.body));
      if (scenario.tier === "acknowledge") {
        check(last.body.acknowledge_legacy === true, "it sent acknowledge_legacy: true");
        check(last.body.corrected_value == null,
              "and did NOT invent a corrected_value", last.body.corrected_value);
      } else {
        check(last.body.corrected_value === scenario.type_instead,
              "it sent the person's typed value", last.body.corrected_value);
        check(last.body.acknowledge_legacy !== true,
              "and did NOT send acknowledge_legacy for a flagged value");
      }
      check(last.body.person_id === fixtures.person_id, "it sent the person_id");
    }
    scenario.captured = last ? last.body : null;
    console.log("");
  }

  fs.writeFileSync(OUT, JSON.stringify(fixtures.scenarios, null, 2));
  if (failures) {
    console.log("  " + failures + " checks failed.\n");
    process.exit(1);
  }
  console.log("  Every UI check passed. Captured bodies written for replay.\n");
}

run().catch((e) => { console.error(e); process.exit(1); });
