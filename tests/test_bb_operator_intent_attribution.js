/* WO-BIO-VIEW-SAFETY-01 — human authority is claimed only where the
   server's change list and the operator's own hand agree.

   WHAT THIS GUARDS, and why it is not a source-text check.

   `markHumanEdit` sets source="human_edit", confidence 1.0 and
   locked=true, and projection-sync.js refuses every later write to a
   locked field from any source that is not itself a human edit. So a
   field wrongly marked here is a fact the narrator can never correct by
   speaking. That is the cost of being wrong, and it is why attribution
   must be measured rather than assumed.

   The defect this replaces: `_afterConfirmedSave` walked EVERY populated
   field in the saved section and marked each one. Measured on a real
   narrator — Janice 93479171 carries ten such marks on her parents, all
   ten written inside a TWO MILLISECOND window on 2026-09-15. Nobody types
   ten fields about two people in two milliseconds; that spread is a
   loop's signature.

   Two witnesses are required and neither is sufficient alone:
     the server  — this path's stored value actually changed
     the screen  — a person altered this field's value by hand
   The server cannot see intent. The browser cannot see the stored
   document. Their intersection can.

   Case 4 is the one external review asked for and the one a naive
   implementation fails: comparing a field against its rendered value
   proves it changed ON SCREEN, not that a PERSON changed it.
   `_tryAutoZodiac` writes the zodiac field when the date of birth is
   blurred, so typing a birth date would otherwise credit the operator
   with the machine's derivation — and lock it. */

"use strict";

const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "ui", "js", "bio-builder-questionnaire.js"), "utf8");

let pass = 0, fail = 0;
function check(name, ok, why) {
  if (ok) { console.log("  ok    " + name); pass++; }
  else { console.log("  FAIL  " + name + "\n        " + why); fail++; }
}

/* ── the production functions, lifted and executed ──────────────────
   Extracted from the shipped source rather than retyped, so a change to
   the real implementation reaches this test instead of passing a copy
   that has drifted away from it. If an extraction fails the suite
   refuses loudly — a fixture that silently supplies the property it is
   meant to prove is the failure mode this repository has named. */
function lift(signature) {
  const start = SRC.indexOf(signature);
  if (start === -1) throw new Error("could not find in shipped source: " + signature);
  let i = SRC.indexOf("{", start), depth = 0, end = -1;
  for (let j = i; j < SRC.length; j++) {
    if (SRC[j] === "{") depth++;
    else if (SRC[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
  }
  if (end === -1) throw new Error("unbalanced braces reading: " + signature);
  return SRC.slice(start, end);
}

const sandbox = {
  _renderedFieldValues: {},
  _dom: {},
  _el(id) { return Object.prototype.hasOwnProperty.call(this._dom, id) ? this._dom[id] : null; },
};
// eslint-disable-next-line no-new-func
new Function("ctx", `
  const _el = (id) => ctx._el(id);
  let _renderedFieldValues = ctx._renderedFieldValues;
  ${lift("function _rebaseRenderedValue(")}
  ${lift("function _operatorTouched(")}
  ${lift("function _collectOperatorTouchedPaths(")}
  ctx._rebaseRenderedValue = _rebaseRenderedValue;
  ctx._operatorTouched = _operatorTouched;
  ctx._collectOperatorTouchedPaths = _collectOperatorTouchedPaths;
`)(sandbox);

check("the three production functions were lifted, not retyped",
  typeof sandbox._operatorTouched === "function" &&
  typeof sandbox._collectOperatorTouchedPaths === "function" &&
  typeof sandbox._rebaseRenderedValue === "function",
  "the suite must exercise shipped code; a retyped copy proves nothing about the product");

/* Stand up a rendered form: DOM nodes plus the snapshot taken at render. */
function render(fields) {
  sandbox._dom = {};
  sandbox._renderedFieldValues = {};
  for (const [id, v] of Object.entries(fields)) {
    sandbox._dom[id] = { value: v };
    sandbox._renderedFieldValues[id] = v;
  }
  // rebind the closure's view of the snapshot object
  // eslint-disable-next-line no-new-func
  new Function("ctx", `
    const _el = (id) => ctx._el(id);
    let _renderedFieldValues = ctx._renderedFieldValues;
    ${lift("function deriveZodiacFromDob(")}
    ${lift("function _rebaseRenderedValue(")}
    ${lift("function _tryAutoZodiac(")}
    ${lift("function _operatorTouched(")}
    ${lift("function _collectOperatorTouchedPaths(")}
    ctx._rebaseRenderedValue = _rebaseRenderedValue;
    ctx._tryAutoZodiac = _tryAutoZodiac;
    ctx._operatorTouched = _operatorTouched;
    ctx._collectOperatorTouchedPaths = _collectOperatorTouchedPaths;
  `)(sandbox);
}

const personal = {
  id: "personal", repeatable: false,
  fields: [{ id: "fullName" }, { id: "dateOfBirth" }, { id: "zodiacSign" }, { id: "placeOfBirth" }],
};
const parents = {
  id: "parents", repeatable: true,
  fields: [{ id: "firstName" }, { id: "lastName" }, { id: "occupation" }],
};

/* ── 1. an untouched form attributes nothing ─────────────────────── */
render({ bbQ_fullName: "Janice Josephine Horne", bbQ_dateOfBirth: "1939-08-30",
         bbQ_zodiacSign: "", bbQ_placeOfBirth: "Spokane, Washington" });
let touched = sandbox._collectOperatorTouchedPaths(personal, "personal", { questionnaire: {} });
check("an untouched form yields no operator-touched paths",
  Object.keys(touched).length === 0,
  "opening a section and saving it unchanged must claim no authorship at all");

/* ── 2. one typed field is the only one attributed ───────────────── */
render({ bbQ_fullName: "Janice", bbQ_dateOfBirth: "1939-08-30",
         bbQ_zodiacSign: "Libra", bbQ_placeOfBirth: "Spokane, Washington" });
sandbox._dom.bbQ_fullName.value = "Janice Josephine Horne";   // the operator types
touched = sandbox._collectOperatorTouchedPaths(personal, "personal", { questionnaire: {} });
check("exactly the typed field is attributed",
  touched["personal.fullName"] === true && Object.keys(touched).length === 1,
  "a section save must not claim the fields that merely sat on the form beside the edit");

/* ── 3. the repeatable case — one parent, one field ──────────────── */
render({ bbQ_0_firstName: "Josephine", bbQ_0_lastName: "Zarr", bbQ_0_occupation: "Housewife",
         bbQ_1_firstName: "Peter",     bbQ_1_lastName: "Zarr", bbQ_1_occupation: "carpenter" });
sandbox._dom.bbQ_1_occupation.value = "Steam boiler operator, carpenter";
touched = sandbox._collectOperatorTouchedPaths(parents, "parents",
  { questionnaire: { parents: [{}, {}] } });
check("in a repeatable section only the edited entry's field is attributed",
  touched["parents[1].occupation"] === true && Object.keys(touched).length === 1,
  "this is the shape that produced ten marks in two milliseconds: entries x fields, " +
  "marking everything populated");

/* ── 4. THE REVIEW CASE: a machine write must not read as a person's ── */
render({ bbQ_fullName: "Janice Josephine Horne", bbQ_dateOfBirth: "",
         bbQ_zodiacSign: "", bbQ_placeOfBirth: "Spokane, Washington" });
sandbox._dom.bbQ_dateOfBirth.value = "1939-08-30";      // the operator types a DOB
/* The SHIPPED derivation runs — not a stand-in for it. An earlier version
   of this test wrote the zodiac and called _rebaseRenderedValue by hand,
   which meant deleting that call from _tryAutoZodiac left the test green:
   the fixture was supplying the property it claimed to prove. Calling the
   real function is what makes the mutation fail here. */
sandbox._tryAutoZodiac("1939-08-30");
check("the shipped derivation actually wrote the zodiac field",
  sandbox._dom.bbQ_zodiacSign.value === "Virgo",
  "if this is blank the rest of case 4 proves nothing — no machine write happened " +
  "for the attribution check to ignore (and 1939-08-30 is Virgo, not Libra)");
touched = sandbox._collectOperatorTouchedPaths(personal, "personal", { questionnaire: {} });
check("a machine-written field is NOT attributed to the operator",
  touched["personal.dateOfBirth"] === true &&
  touched["personal.zodiacSign"] === undefined &&
  Object.keys(touched).length === 1,
  "comparing against the rendered value proves a field changed ON SCREEN, not that a " +
  "PERSON changed it. _tryAutoZodiac writes the zodiac when the date of birth is " +
  "blurred; without the rebase, typing a birth date locks the machine's derivation " +
  "and the narrator can never correct it by speaking");

/* ── 5. ...but the operator can still overrule the machine ───────── */
sandbox._dom.bbQ_zodiacSign.value = "Libra";            // the operator disagrees, by hand
touched = sandbox._collectOperatorTouchedPaths(personal, "personal", { questionnaire: {} });
check("an operator correcting the machine's value IS attributed",
  touched["personal.zodiacSign"] === true,
  "rebasing must not become a blacklist: a person overruling a derived value is a real " +
  "human edit and has to be recorded as one, or their correction is silently discarded");

/* ── 6. a field absent from the snapshot is never attributed ─────── */
render({ bbQ_fullName: "Janice" });
sandbox._dom.bbQ_surprise = { value: "appeared from nowhere" };
check("a field with no rendered baseline is not attributed",
  sandbox._operatorTouched("bbQ_surprise") === false,
  "unknown provenance attributes nothing — silence is recoverable, a false lock is not");

console.log("");
if (fail) { console.log("  " + fail + " FAILED"); process.exit(1); }
console.log("  all " + pass + " checks passed");
