/* WO-BIO-VIEW-SAFETY-01 — Operator Intake must not duplicate writes, and
   must not paint one narrator's answers into another's form.

   TWO DEFECTS, BOTH SOURCE-CONFIRMED BEFORE REPAIR, BOTH REPRODUCED HERE.

   1. ACCUMULATING HANDLERS. `_attachHandlers` binds an "input" and a
      "click" listener to the CONTAINER — delegated, not per-field.
      `_renderAll` replaces `container.innerHTML`, which destroys the
      children and leaves the container and its listeners in place. Every
      render therefore added another pair and removed none, so after N
      renders one click on Save ran the handler N times: N PUTs for one
      deliberate action. Renders are frequent — refresh, save, array add,
      array remove all call _renderAll — so N grows through ordinary use.

   2. OUT-OF-ORDER RESPONSES. `refresh()` awaited the questionnaire fetch
      and assigned the result to shared `_state` with no check that it
      still belonged to the narrator on screen. `onNarratorSwitch()` calls
      `refresh()` again, so switching from A to B leaves A's request in
      flight; if A's response lands second it overwrites B's questionnaire,
      meta and source. The form then shows A's answers under B's name, and
      a Save from that screen writes one family's history into another's
      record. That is the failure this repository's first design principle
      exists to prevent.

   WHY A HARNESS AND NOT A SOURCE-TEXT CHECK. Both defects are about
   ORDERING and ACCUMULATION, which no amount of grepping observes. The
   repository has already paid for that lesson: a source-string assertion
   passed against a mutant that ran derived work on a failed save. So this
   drives the real functions against a fake DOM and a fake network whose
   responses resolve in an order the test chooses. */

"use strict";

const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "ui", "js", "operator-intake.js"), "utf8");

let pass = 0, fail = 0;
function check(name, ok, why) {
  if (ok) { console.log("  ok    " + name); pass++; }
  else { console.log("  FAIL  " + name + "\n        " + why); fail++; }
}

/* ── a container that records its listeners ─────────────────────────
   Deliberately faithful on the one point that matters: setting innerHTML
   clears children and does NOT remove listeners bound to the element. */
function makeContainer() {
  return {
    id: "lvIntakeContainer",
    _listeners: { input: [], click: [] },
    _html: "",
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; },          // listeners survive, as in a browser
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    querySelectorAll() { return []; },
    querySelector() { return null; },
  };
}

/* ── 1. handlers bind once, however many times we render ──────────── */
(function handlerAccumulation() {
  const attach = (() => {
    const start = SRC.indexOf("function _attachHandlers(");
    if (start === -1) throw new Error("could not find _attachHandlers in the shipped source");
    let depth = 0, end = -1;
    for (let j = SRC.indexOf("{", start); j < SRC.length; j++) {
      if (SRC[j] === "{") depth++;
      else if (SRC[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
    }
    return SRC.slice(start, end);
  })();

  const ctx = { _state: { dirtySections: {} }, calls: 0 };
  // eslint-disable-next-line no-new-func
  const run = new Function("container", "ctx", `
    const _state = ctx._state;
    const _saveSection = async () => { ctx.calls++; };
    const _addArrayEntry = () => {};
    const _removeArrayEntry = () => {};
    const _renderAll = () => {};
    ${attach}
    _attachHandlers(container);
  `);

  const container = makeContainer();
  for (let i = 0; i < 5; i++) { container.innerHTML = "<div>render " + i + "</div>"; run(container, ctx); }

  check("five renders leave exactly one click handler",
    container._listeners.click.length === 1,
    "got " + container._listeners.click.length + ". Delegated listeners survive an " +
    "innerHTML replacement, so binding on every render stacks them — and one click " +
    "on Save then issues one PUT per accumulated handler");

  check("five renders leave exactly one input handler",
    container._listeners.input.length === 1,
    "got " + container._listeners.input.length + "; same mechanism, marking a section " +
    "dirty repeatedly per keystroke");
})();

/* ── 2. a late response for the previous narrator is discarded ────── */
(async function outOfOrderResponse() {
  const lift = (sig) => {
    const start = SRC.indexOf(sig);
    if (start === -1) throw new Error("could not find in shipped source: " + sig);
    let depth = 0, end = -1;
    for (let j = SRC.indexOf("{", start); j < SRC.length; j++) {
      if (SRC[j] === "{") depth++;
      else if (SRC[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
    }
    return SRC.slice(start, end);
  };

  const container = makeContainer();
  const ctx = {
    _state: { personId: null, questionnaire: {}, meta: {}, source: null,
              dirtySections: {}, loading: false, refreshGen: 0 },
    current: null,
    pending: {},        // pid -> resolve fn, so the test chooses the order
  };

  // eslint-disable-next-line no-new-func
  const api = new Function("ctx", "container", `
    const _state = ctx._state;
    const document = { getElementById: () => container };
    const _getCurrentPersonId = () => ctx.current;
    const _renderEmpty = () => {};
    const _renderAll = () => {};
    const _esc = (s) => String(s);
    const _fetchQuestionnaire = (pid) => new Promise((res) => { ctx.pending[pid] = res; });
    ${lift("async function refresh(")}
    ${lift("function onNarratorSwitch(")}
    return { refresh, onNarratorSwitch };
  `)(ctx, container);

  const A = "aaaaaaaa-1111-1111-1111-111111111111";
  const B = "bbbbbbbb-2222-2222-2222-222222222222";

  ctx.current = A;
  const refreshA = api.refresh();              // A's fetch is now in flight
  ctx.current = B;
  api.onNarratorSwitch(B);                     // switch; B's fetch goes in flight too

  // B answers first, then A's stale response arrives late.
  ctx.pending[B]({ questionnaire: { personal: { fullName: "Narrator B" } },
                   _meta: {}, source: "ui_save" });
  await new Promise((r) => setTimeout(r, 0));
  ctx.pending[A]({ questionnaire: { personal: { fullName: "Narrator A" } },
                   _meta: {}, source: "ui_save" });
  await refreshA.catch(() => {});
  await new Promise((r) => setTimeout(r, 0));

  const shown = (ctx._state.questionnaire.personal || {}).fullName;
  check("a late response for the previous narrator does not overwrite the current one",
    shown === "Narrator B",
    "the form is showing " + JSON.stringify(shown) + " while narrator B is loaded. " +
    "A save from this screen would write one narrator's answers into another's " +
    "record — the cross-narrator failure the design principles forbid outright");

  check("the active narrator is still the one that was switched to",
    ctx._state.personId === B,
    "a late response must not move _state.personId either");

  /* ── 3. Batch C: this tab is read-only — Save sends nothing ─────────
     Lifted from the shipped source (READ_ONLY and _saveSection together)
     and run with a network that records any attempt. */
  {
    const flagAt = SRC.indexOf("var READ_ONLY = ");
    const start = SRC.indexOf("async function _saveSection(");
    if (flagAt === -1 || start === -1) throw new Error("read-only guard not found in shipped source");
    let depth = 0, end = -1;
    for (let j = SRC.indexOf("{", start); j < SRC.length; j++) {
      if (SRC[j] === "{") depth++;
      else if (SRC[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
    }
    const flag = SRC.slice(flagAt, SRC.indexOf(";", flagAt) + 1);
    const c = { puts: 0, toasts: [] };
    // eslint-disable-next-line no-new-func
    const save = new Function("c", `
      const _state = { personId: "p1", questionnaire: {}, dirtySections: {} };
      const _readSectionFromForm = () => {};
      const _putSection = async () => { c.puts++; return {}; };
      const _fetchQuestionnaire = async () => ({});
      const _renderAll = () => {};
      const _toast = (m) => c.toasts.push(m);
      ${flag}
      ${SRC.slice(start, end)}
      return _saveSection;`)(c);
    await save("personal", { querySelector: () => null });
    check("Operator Intake Save sends nothing: the earlier questionnaire is read-only",
      c.puts === 0 && /read-only/i.test(c.toasts.join(" ")),
      c.puts + " PUT(s); toasts " + JSON.stringify(c.toasts) + ". A second editor of the legacy " +
      "questionnaire beside Questionnaire V2 is a second authority");
  }

  console.log("");
  if (fail) { console.log("  " + fail + " FAILED"); process.exit(1); }
  console.log("  all " + pass + " checks passed");
})();
