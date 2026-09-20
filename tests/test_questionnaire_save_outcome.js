/* Content detection, conflict scope, and honest save reporting.

   BUG-BIO-QUESTIONNAIRE-NEW-NARRATOR-SAVE-LOCK-01
   BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01

   WHAT HAPPENED, 2026-09-17, in a live browser

     A disposable narrator was created to rehearse entering a real person's
     biography. Hydration reached "server" correctly at 16:40:16. Two seconds
     later a second restore moved it to "conflict" — four minutes before the
     operator typed anything. Every save from then on was refused, and the UI
     said nothing at all. Six typed values lived only in localStorage.

   THE FIRST DEFECT — detection

     The conflict branch asked _hasAnyValue(bb.questionnaire), a SHALLOW
     helper:

         Object.keys(obj).some(k => obj[k] && String(obj[k]).trim() !== "")

     String({}) is "[object Object]", a non-empty string. So any section key
     counted as operator content, and hydration itself creates section keys:

         {}                             -> false
         { personal: {} }               -> TRUE
         { personal: { fullName: "" } } -> TRUE

     Every narrator with no server questionnaire was therefore holding "a
     draft with content" before a keystroke, and was locked out of saving.

     The identity migration's bookkeeping compounded it: _legacyMigrationVersion
     is a plain string, so it too read as biography.

   THE SECOND DEFECT — reporting, independent of the first

     The PUT was fire-and-forget. Nothing returned to the caller on success,
     refusal, 409, or a dead server. _saveSection re-rendered regardless, and
     silence read as success.

   WHAT IS NOT WEAKENED

     The conflict guard exists because on 2026-09-15 a draft outlived a full
     database erasure and restore — narrator ids survive export verbatim, so
     the key lorevox_qq_draft_<pid> came back pointing at erased data. That
     draft held REAL ANSWERS. It still trips the guard. Check 4 below is the
     one that must never be "fixed" into passing by loosening the rule.

   WHAT THIS SUITE IS, AND WHAT IT IS NOT

     56 checks. ELEVEN execute code — they lift _hasOperatorContent and
     _isBookkeepingKey out of the module and call them with real documents.
     The other FORTY-FIVE read source text and assert control flow.

     There is no DOM here, no jsdom, no HTTP, no fake server. Nothing in this
     file enters two entries and saves, fails a PUT, lands a GET mid-edit,
     switches narrator with a write in flight, or reloads. It cannot express
     a SEQUENCE, and every defect that reached a real operator on 17-18
     September was a sequence.

     The proof is in this file's own history. BUG-BIO-QUESTIONNAIRE-SECOND-
     ENTRY-DROPPED-01 — a repeatable section silently discarding a second
     family member — survived 45 of these checks and two days of live
     testing. It needed two entries and two saves. What caught it was the
     operator typing a name into a form and asking why it was gone.

     So: call this a SOURCE-CONTRACT suite. It is good at "is the guard
     present and wired to the right thing", and blind to "does the guard
     fire". It stops silent regression of decisions that were expensive to
     reach. It is not evidence that Bio Builder saves correctly.

     That evidence comes from two other places, and both are required:
       - the behavioural harness (WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01),
         which drives the real functions through real sequences
       - a live disposable-narrator walkthrough verified in SQLite

   Run:  node tests/test_questionnaire_save_outcome.js
*/

"use strict";

const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

const CORE_PATH = process.env.LV_BBCORE_JS || path.join(ROOT, "ui/js/bio-builder-core.js");
const QQ_PATH   = process.env.LV_BBQQ_JS   || path.join(ROOT, "ui/js/bio-builder-questionnaire.js");
const CORE = fs.readFileSync(CORE_PATH, "utf8");
const QQ   = fs.readFileSync(QQ_PATH, "utf8");

let failures = 0;
const check = (name, cond, detail) => {
  if (cond) console.log(`  ok    ${name}`);
  else { failures++; console.log(`  FAIL  ${name}\n        ${detail || ""}`); }
};

/* Take a whole function by matching braces.

   Third time in this work that a proximity-based source slice has reported
   failures against CORRECT code. Brace matching, once, reused. A test that
   fails on working code invites someone to break the code to satisfy it. */
function fnBody(src, decl) {
  const i = src.indexOf(decl);
  if (i === -1) return "";
  let depth = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") { depth++; started = true; }
    else if (src[j] === "}") { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
  }
  return "";
}

/* Lift _hasOperatorContent + _isBookkeepingKey out of the module and run
   them for real. Asserting on source text would only prove the words are
   present; these four cases are the actual behaviour that broke. */
function loadContentFns() {
  const a = fnBody(CORE, "function _isBookkeepingKey(");
  const b = fnBody(CORE, "function _hasOperatorContent(");
  if (!a || !b) return null;
  // eslint-disable-next-line no-new-func
  return new Function(`${a}\n${b}\nreturn { _isBookkeepingKey, _hasOperatorContent };`)();
}

console.log("\nquestionnaire save outcome + content detection\n");

const C = loadContentFns();
check("_hasOperatorContent and _isBookkeepingKey are defined", !!C,
  "the conflict branch has nothing correct to ask");

if (C) {
  const has = C._hasOperatorContent;

  const MARKERS = {
    _legacyMigrationVersion: "WO-INTAKE-IDENTITY-01",
    _legacyRemovedSections: { _version: "WO-INTAKE-IDENTITY-01", _capturedAt: "2026-09-17T21:44:19.738Z" }
  };
  const BLANK = { personal: { fullName: "", preferredName: "", dateOfBirth: "", placeOfBirth: "" } };
  const REAL  = { personal: { fullName: "Thorvald Lindqvist", dateOfBirth: "1934-06-15" } };

  /* ── the four cases named in the repair order ───────────────────────── */

  check("1. a blank form is NOT content",
    has(BLANK) === false,
    "this is the shape hydration creates; calling it content locks every " +
    "new narrator out of saving");

  check("2. a blank form PLUS migration markers is NOT content",
    has(Object.assign({}, BLANK, MARKERS)) === false,
    "_legacyMigrationVersion is the program's own bookkeeping, not biography");

  check("3. markers PLUS one real answer IS content",
    has(Object.assign({}, BLANK, MARKERS, REAL)) === true,
    "ignoring bookkeeping must not make real answers invisible");

  check("4. a draft of REAL answers is still content (erasure guard intact)",
    has(REAL) === true,
    "THE 2026-09-15 CASE. A draft that outlived a database erasure holds " +
    "real answers; it must still refuse to save silently over an empty " +
    "server. Never loosen this to make another check pass.");

  /* ── the specific shapes observed live ──────────────────────────────── */

  check("an empty section object alone is not content",
    has({ personal: {} }) === false);

  check("the bare migration marker string is not content",
    has({ _legacyMigrationVersion: "WO-INTAKE-IDENTITY-01" }) === false);

  check("nested real answers are found",
    has({ parents: [{ name: "" }, { name: "Ingrid" }] }) === true);

  check("nested blanks are not content",
    has({ parents: [{ name: "", birthPlace: "" }] }) === false);

  check("a repeated-entry array of empty objects is not content",
    has({ parents: [{}, {}] }) === false);

  check("zero and false are content, not emptiness",
    has({ facts: { siblings: 0 } }) === true && has({ facts: { living: false } }) === true,
    "a numeric answer of 0 is an answer");

  check("bookkeeping keys are identified by a leading underscore AND a scalar value",
    C._isBookkeepingKey("_legacyMigrationVersion", "WO-INTAKE-IDENTITY-01") === true &&
    C._isBookkeepingKey("personal", {}) === false);

  /* BUG-BIO-QUESTIONNAIRE-LEGACY-SECTIONS-INVISIBLE-01.
     _migrateRemovedSectionsToLegacy moves grandparents, auntsUncles,
     childhoodPlaces, schools, trips and memoryNotes under
     `_legacyRemovedSections` on every restore and save. The first bookkeeping
     rule skipped every `_`-prefixed key, so a narrator whose only content was
     grandparents was classified as EMPTY the moment the migration ran, and
     _persistDrafts refused to save them. A family's grandparents, treated as
     a version stamp. */
  check("real sections under _legacyRemovedSections ARE content",
    has({ _legacyRemovedSections: {
            _version: "WO-INTAKE-IDENTITY-01", _capturedAt: "2026-09-18T00:00:00Z",
            grandparents: [{ firstName: "Ervin", lastName: "Horne" }] },
          _legacyMigrationVersion: "WO-INTAKE-IDENTITY-01" }) === true,
    "the blank-PUT guard would refuse to save a narrator whose grandparents " +
    "were the only thing entered");

  check("a `_` container holding only bookkeeping scalars is still not content",
    has({ _legacyRemovedSections: { _version: "x", _capturedAt: "y" } }) === false);

  check("a `_` container is descended into, not named",
    C._isBookkeepingKey("_anyFutureContainer", { grandparents: [] }) === false &&
    C._isBookkeepingKey("_anyFutureStamp", "v2") === true,
    "the rule is about the VALUE's shape, so the next migration that invents " +
    "a container does not reopen this");
}

/* ── the conflict branch asks the DEEP function ───────────────────────── */

const backend = fnBody(CORE, "function _restoreQuestionnaireFromBackend(");
check("the conflict branch calls _hasOperatorContent, not _hasAnyValue",
  /_hasOperatorContent\(cur\)/.test(backend) && !/_hasAnyValue\(cur\)/.test(backend),
  "_hasAnyValue is shallow; String({}) is truthy; that is the whole bug");

check("the conflict state still exists and can still be entered",
  /_setQqHydration\(\s*"conflict"/.test(backend),
  "the erasure guard must survive this repair");

/* ── the first save must be POSSIBLE ──────────────────────────────────────
   BUG-BIO-QUESTIONNAIRE-FIRST-SAVE-IMPOSSIBLE-01.

   With detection fixed the guard still deadlocked: to save you must have
   typed something; typed content plus an empty server was a conflict;
   conflict refused. _saveSection re-restores before saving, so the first save
   on any narrator without a server questionnaire could never succeed. Seen
   live on ZZ WALKTHROUGH 20260917 — a correct red banner on a save that had
   no reachable success path.

   The discriminator is ORDER, and we already hold it. Erasure: the page
   loaded holding content and only then learned the server was empty, so the
   content predates the knowledge. First save: we confirmed empty while
   holding nothing, and the content arrived afterwards by hand. */

check("a confirmed-empty read while holding nothing is remembered",
  /_qqServerConfirmedEmpty\[stampedPid\] = true/.test(backend),
  "without this the first save on a new narrator is logically impossible");

check("that memory is only set on the branch that held NOTHING",
  (() => {
    const i = backend.indexOf("_qqServerConfirmedEmpty[stampedPid] = true");
    if (i === -1) return false;
    // It must sit in the else-branch, i.e. AFTER the conflict branch's warn.
    const conflictWarn = backend.indexOf("questionnaire CONFLICT for");
    return conflictWarn !== -1 && i > conflictWarn;
  })(),
  "setting it while local content existed would vouch for data we never read");

check("an empty server is re-accepted only when we confirmed it earlier",
  /localHas && _qqServerConfirmedEmpty\[stampedPid\]/.test(backend),
  "the exemption must require BOTH, or it is just the guard switched off");

check("the erasure path is still reachable when we did NOT confirm first",
  /\} else if \(localHas\) \{/.test(backend),
  "a page that arrives already holding content must still conflict — that is " +
  "the 2026-09-15 case and it must not be collateral damage of this fix");

/* ── a server read must not eat unsaved edits ─────────────────────────────
   BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01. The adopt branch assigned the
   server document straight over bb.questionnaire. _saveSection restores
   immediately before saving, so a GET landing between the two dropped the
   edit silently. It only ever fires for records that ALREADY have a server
   questionnaire — every real narrator — which is why two days of testing on
   an empty record never showed it. */

check("the adopt branch is guarded by a dirty check",
  /if \(_qqDirty\[stampedPid\] && _hasOperatorContent\(bb\.questionnaire\)\) \{/.test(backend) &&
  /\} else \{\s*\n\s*bb\.questionnaire = sections;/.test(backend),
  "an unconditional bb.questionnaire = sections discards typing that was in " +
  "flight when the GET landed");

/* Scoped to _saveSection, not to the whole file.

   This grepped QQ entire. _addRepeatEntry ALSO calls _markQuestionnaireEdited,
   so deleting the call from the save path left the check passing while the
   save was unprotected — mutation m16 scored zero failures. A test that
   cannot tell which function holds the guard is not testing the guard, and
   this one said "the form declares its edits" while meaning "somebody,
   somewhere, in 1,800 lines". Ask each function separately. */
check("dirty is set by the form, not inferred from content",
  /function _markQuestionnaireEdited\(pid\)/.test(CORE) &&
  /_core\._markQuestionnaireEdited\(pid\)/.test(fnBody(QQ, "function _saveSection(")),
  "'there is content in memory' is also true of a stale localStorage draft, " +
  "and a stale draft must NOT override a newer server document");

check("the save path declares its edits BEFORE persisting",
  (() => {
    const b = fnBody(QQ, "function _saveSection(");
    const iMark = b.indexOf("_markQuestionnaireEdited(pid)");
    // Match the CALL, not its argument list. WO-03A added a second
    // argument (the human-entry hint) and this check failed against
    // correct code — the ordering property it guards was untouched. The
    // repeated lesson from WO-02: assert on structure, never on an exact
    // line, or the test breaks every time the code legitimately changes
    // and teaches nothing when it does.
    const iPersist = b.search(/_persistDrafts\(pid[,)]/);
    return iMark !== -1 && iPersist !== -1 && iMark < iPersist;
  })(),
  "declaring after the async work has started leaves the window open");

check("dirty is cleared only on a CONFIRMED save",
  (() => {
    const pq = fnBody(CORE, "function _persistQuestionnaire(");
    const i = pq.indexOf("delete _qqDirty[pid];");
    if (i === -1) return false;
    // must sit after the !r.ok bail-out, i.e. on the success branch only
    return i > pq.indexOf("if (!r.ok)");
  })(),
  "clearing it on an ATTEMPT would drop the protection at exactly the moment " +
  "a failed save needs it");

/* ── a stale read must not release a newer gate ───────────────────────────
   BUG-BIO-QUESTIONNAIRE-STALE-SETTLE-01. The gate settled by narrator id
   alone. Restores overlap routinely — _sectionFillCount restores during
   render, _saveSection restores again before saving — so the first response
   released the second read's gate and a save proceeded on the older answer. */

check("each gate carries the token of the read that opened it",
  /var gate = \{ token: token/.test(CORE) && /_qqReadToken/.test(CORE));

check("a settle quoting the wrong token is refused",
  /if \(token !== undefined && gate\.token !== token\)/.test(fnBody(CORE, "function _qqMarkSettled(")),
  "otherwise a superseded response can authorise a save on a stale read");

/* Count, don't pattern-match-with-lookahead.

   The first version of this check used a negative lookahead to assert "no
   settle call lacks readToken" and failed against code where all twelve
   carried it. Sixth time in this work that a clever match has reported a
   failure that was not there. Count both sets and compare. */
const allSettles   = (backend.match(/_qqMarkSettled\(/g) || []).length;
const tokenSettles = (backend.match(/_qqMarkSettled\([^;]*?readToken\)/g) || []).length;

check(`every settle in the response handler quotes its token (${tokenSettles}/${allSettles})`,
  /function _restoreQuestionnaireFromBackend\(pid, readToken\)/.test(CORE) &&
  allSettles > 0 && tokenSettles === allSettles,
  "a settle that omits the token can release a newer read's gate");

check("the confirmed-empty memory is cleared when the server HAS content",
  /delete _qqServerConfirmedEmpty\[stampedPid\];/.test(backend),
  "left set, it would vouch for a localStorage draft after a later " +
  "server-side erasure — the 2026-09-15 case reopened by a stale flag");

check("the confirmed-empty memory is NOT written to localStorage",
  !/localStorage[^\n]*_qqServerConfirmedEmpty/.test(CORE) &&
  /var _qqServerConfirmedEmpty = Object\.create\(null\)/.test(CORE),
  "persisting it would let it outlive an erasure — exactly the property that " +
  "made the draft dangerous in the first place");

/* ── hydration settle: the save must not race the read it started ─────── */

check("a hydration settle gate exists",
  /function _qqHydrationSettled\(/.test(CORE) && /function _qqMarkSettled\(/.test(CORE));

check("a new restore opens a FRESH settle gate",
  /_qqResetSettle\(pid\)/.test(fnBody(CORE, "function _restoreQuestionnaire(")),
  "otherwise a save waits on a stale resolved promise from an earlier read");

/* Every exit from the backend restore must release the gate, or a save that
   awaits it hangs forever with the operator's work unsaved and no message. */
const settleCount = (backend.match(/_qqMarkSettled\(/g) || []).length;
check(`every exit from the backend restore settles the gate (${settleCount} call sites)`,
  settleCount >= 7,
  "an unreleased gate turns a refusal into a silent hang, which is worse");

check("the GET failure path settles too",
  /\.catch\(function \(e\) \{[\s\S]*?_qqMarkSettled/.test(backend),
  "a dead server must produce a refusal message, not a hang");

/* ── the save reports a real outcome ──────────────────────────────────── */

const persistQq = fnBody(CORE, "function _persistQuestionnaire(");
check("_persistQuestionnaire exists and awaits hydration before deciding",
  persistQq && /_qqHydrationSettled\(pid\)\.then/.test(persistQq),
  "reading hydration synchronously races the GET _saveSection just started — " +
  "that is why the first save on a new narrator was always refused");

check("the PUT response is inspected rather than discarded",
  /r\.status === 409/.test(persistQq) && /if \(!r\.ok\)/.test(persistQq),
  "the old code was fetch(...).catch(log) — a 409 or a 500 was indistinguishable " +
  "from success");

check("a 409 is reported as a conflict, distinctly",
  /outcome: "conflict"/.test(persistQq));

check("a network failure is reported, distinctly",
  /outcome: "network"/.test(persistQq));

/* A no-op is a success, but not the same event as a write. The server
   already distinguishes them — merge_whole_document returns
   write_applied:false and burns neither a revision nor an audit row — and
   the UI was discarding that, reporting both as "Saved". An operator could
   not tell whether an edit went in or whether the form resubmitted what was
   already there. Proven live 2026-09-18: an unchanged re-save left rev=4,
   3 history rows and sha d5eec46ce6510a40 untouched, and said "Saved". */
check("a no-op save is reported as such, not as a write",
  /j\.write_applied === false/.test(persistQq) && /outcome: applied \? "saved" : "nochange"/.test(persistQq),
  "reporting an unchanged resubmit identically to a real write hides whether " +
  "the operator's edit actually landed");

/* Exactly one branch may claim a save, and it must sit AFTER the 409 and
   !r.ok bail-outs. Asserted on position rather than on the literal field
   order, which changed when write_applied was added and broke this check
   against correct code — the seventh such false failure in this work. */
check("only an ok response yields saved:true",
  (() => {
    const claims = (persistQq.match(/saved: true/g) || []).length;
    const iClaim = persistQq.indexOf("saved: true");
    const iNotOk = persistQq.indexOf("if (!r.ok)");
    const i409   = persistQq.indexOf("r.status === 409");
    return claims === 1 && iNotOk !== -1 && i409 !== -1 &&
           iClaim > iNotOk && iClaim > i409;
  })(),
  "exactly one branch may claim a save, and it is the one after the 409 and " +
  "!r.ok bail-outs have returned");

check("the draft is written before the PUT is attempted",
  /_writeQqDraft\(pid, qq\)/.test(fnBody(CORE, "function _persistDrafts(")),
  "the operator's typing must survive every failure path");

/* ── a repeatable section must save every entry it SHOWS ──────────────────
   BUG-BIO-QUESTIONNAIRE-SECOND-ENTRY-DROPPED-01 (2026-09-18).

   _saveSection mapped over the STORED entries and read the DOM by index, so
   it could only ever see as many entries as storage already held. Enter a
   mother, save, add a father, save: the father's fields are on screen and
   filled, existing.length is 1, and index 1 is never visited. Nothing is
   rejected and nothing is reported — the entry is simply never looked at.

   Reported by the operator mid-walkthrough: "why is the dad missing i did
   mom and then dad and then save parents only one is there". Neither the
   45 checks in this file nor two days of live testing had caught it, because
   every earlier test used a single-entry section.

   A form can only edit what it shows. It must also SAVE what it shows. */

const saveBody = fnBody(QQ, "function _saveSection(");
const addBody  = fnBody(QQ, "function _addRepeatEntry(");

check("the repeatable save counts the entries RENDERED, not the ones stored",
  /while \(_el\("bbQ_" \+ rendered \+ "_" \+ probe\)\) rendered\+\+/.test(saveBody) &&
  /Math\.max\(existing\.length, rendered\)/.test(saveBody),
  "existing.map(...) can never reach an entry the operator just added");

check("the repeatable save no longer maps over the stored array",
  !/existing\.map\(function \(prev, idx\)/.test(saveBody),
  "that is the exact construct that dropped the father");

check("adding an entry also counts what is rendered",
  /Math\.max\(entries\.length, renderedN\)/.test(addBody),
  "same shape: typing into entry 2 and clicking add would drop it");

check("adding an entry declares the edits before the GET can land",
  /_core\._markQuestionnaireEdited\(pid\)/.test(addBody),
  "_addRepeatEntry restores first, and a successful save has just cleared " +
  "_qqDirty — so without this the adopt branch replaces a half-typed entry " +
  "with the server's copy while it is still on screen");

/* ── the UI surfaces it ───────────────────────────────────────────────── */

const report = fnBody(QQ, "function _reportSaveOutcome(");
check("_reportSaveOutcome exists", !!report);

check("the save path calls it",
  /_reportSaveOutcome\(section, pid/.test(fnBody(QQ, "function _saveSection(")),
  "a save that cannot fail visibly is not a save");

/* WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01 section 1. Candidate extraction,
   markHumanEdit and the family-graph sync ran immediately after
   _persistDrafts without awaiting it, so a refused write still produced
   derived state — candidates and human-edit marks standing on answers the
   database never accepted. That is how an unsaved answer becomes an apparent
   established fact, and it is the direct path from this defect to Lori. */
/* Assert the STRUCTURE, not the presence of two strings.

   The first version required `_afterConfirmedSave(...)` somewhere in
   _saveSection and the gate somewhere in the reporter. Splitting the call
   into two statements — reporter, then downstream, ungated — left both
   strings in place and the check passed against a mutant that ran derived
   work on a failed save. Require the downstream call to be INSIDE the
   reporter's callback, which is the thing that actually gates it. */
check("derived state waits for a confirmed save",
  /function _afterConfirmedSave\(/.test(QQ) &&
  /_reportSaveOutcome\(\s*section,\s*pid,\s*function onConfirmed\(\)\s*\{\s*_afterConfirmedSave\(/
    .test(fnBody(QQ, "function _saveSection(")) &&
  /res\.ok && typeof onConfirmed === "function"/.test(report),
  "nothing that writes derived or authoritative state may run before the " +
  "server has accepted the answers it is derived from — and it must be " +
  "gated BY the outcome, not merely called after it");

check("the confirmation gate wraps the downstream work, not the reverse",
  (() => {
    const after = fnBody(QQ, "function _afterConfirmedSave(");
    return /_extractQuestionnaireCandidates\(sectionId\)/.test(after) &&
           /markHumanEdit/.test(after) &&
           /fullSync\(\)/.test(after);
  })(),
  "all three effects must live behind the boundary; leaving one outside " +
  "means a failed save still produces that one");

check("success is shown only when the outcome says ok",
  /if \(res\.ok\)/.test(report),
  "never render 'saved' without server confirmation");

check("the banner styles a no-op differently from a write",
  /res\.outcome !== "nochange"/.test(report),
  "same words and same colour for both is the same problem one layer up: the " +
  "operator cannot tell whether their edit landed or the form resubmitted");

check("the success banner stays long enough to be read",
  /\}, 8000\)/.test(report),
  "the operator missed a confirmation entirely at 4s — 'i did not get a " +
  "chance to see the banner it was too quickly gone'. A confirmation nobody " +
  "reads confirms nothing");

check("the failure banner does NOT auto-dismiss",
  (() => {
    const i = report.indexOf("} else {");
    return i !== -1 && !/setTimeout/.test(report.slice(i));
  })(),
  "a banner that disappears can be missed, and being missed IS the defect");

check("the failure banner tells the operator where their work is",
  /held in this browser only/.test(report) && /NOT backed up/.test(report),
  "'not saved' without 'and here is where it went' invites retyping from memory");

/* The banner must not promise durability localStorage does not provide.
   The first wording said unsaved answers "will reappear if you reload". A
   refused save left six values in localStorage on 2026-09-17; the machine was
   shut down overnight and they were gone by morning. */
check("the failure banner does NOT promise the draft will survive",
  !/will reappear if you reload/.test(report),
  "localStorage is flushed lazily and can be cleared on exit — telling an " +
  "operator their unsaved work is safe is how an afternoon of a parent's " +
  "history gets closed with the laptop");

/* ── the reporting channel must actually resolve ──────────────────────────
   _reportSaveOutcome first read window.LorevoxBioBuilderCore, which does not
   exist — the namespace is window.LorevoxBioBuilderModules.core, aliased as
   `_core` at the top of the module. The guard then returned silently, so the
   banner never rendered and a failed save was invisible AGAIN: the exact
   defect this function exists to end, reintroduced by its own fix. It was
   caught only because the operator typed the namespace into a console.

   A reporting channel that fails quietly is worse than none, because silence
   is what the operator already reads as success. */
/* Strip comments first. The check below asserts the WRONG namespace does not
   appear — and the comment explaining the bug names it, so matching raw source
   failed against correct code. Fifth time in this work that a text match has
   reported a failure that was not there. Assert on code, not prose. */
const reportCode = report
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");

/* ── a banner must report ITS OWN save ────────────────────────────────────
   Raised in review 2026-09-18. `_qqLastOutcome` is a single shared slot, so
   two overlapping saves mean the second replaces the first and a plain read
   returns a verdict belonging to a different operation. Not observed in
   Chrome — but the justification written above it was a convenience argument,
   not a safety one. Outcomes now carry pid + ticket. */

check("every save outcome is stamped with the operation it belongs to",
  /var _stamp = function \(o\) \{ o\.pid = pid; o\.ticket = ticket; return o; \};/.test(CORE) &&
  // Trailing arguments are allowed: WO-03A passes the entry hint fourth.
  // The property is that a ticket is minted and handed to the persist
  // call, which is what the outcome is stamped with.
  /_persistQuestionnaire\(pid, qq, \+\+_qqSaveTicket[,)]/.test(CORE),
  "an unstamped outcome cannot be matched to the save that asked");

check("a superseded outcome is refused, not reported",
  /outcome: "superseded"/.test(fnBody(CORE, "function _qqSaveOutcomeFor(")),
  "handing back a newer save's verdict is worse than saying nothing");

check("the banner asks for its own ticket",
  /_qqSaveOutcomeFor\(pid, _ticket\)/.test(report) &&
  /res\.outcome === "superseded"/.test(report),
  "reading the shared slot directly is what allows a banner to describe " +
  "somebody else's save");

check("_reportSaveOutcome resolves the core module through _core",
  /_core\._qqSaveOutcome\(\)/.test(reportCode) &&
  !/window\.LorevoxBioBuilderCore\b/.test(reportCode),
  "window.LorevoxBioBuilderCore is undefined; the real handle is " +
  "window.LorevoxBioBuilderModules.core, aliased as _core in this module");

check("an unavailable reporting channel is LOUD, not a silent return",
  (() => {
    const i = report.indexOf("_qqSaveOutcome !== \"function\"");
    if (i === -1) return false;
    const guard = report.slice(i, i + 500);
    return /console\.error/.test(guard) && /alert/.test(guard);
  })(),
  "if the outcome cannot be read, the operator must be told the save is " +
  "UNCONFIRMED — returning quietly recreates the original bug");

check("_core is aliased in this module",
  /var _core\s*=\s*window\.LorevoxBioBuilderModules/.test(QQ));

/* ── MUTATIONS THAT MUST BREAK THIS SUITE ───────────────────────────────
   All 25 regenerated from the CURRENT source and re-run 2026-09-18. Counts
   are observed, never predicted, and every run was checked for completion —
   an earlier pass scored three mutations "0 failures" when node had in fact
   crashed on a missing file and grep counted nothing. A dead run reading as
   a survived mutation is the same silent-failure-as-success this whole repair
   is about.

     1. content detection back to shallow stringify        -> 6
     2. the bookkeeping skip removed                       -> 2
     3. conflict branch back to _hasAnyValue(cur)          -> 1
     4. the gate reading a racing state, not the settled   -> 1
     5. the PUT back to fire-and-forget                    -> 8
     6. the failure banner given an auto-dismiss           -> 1
     7. the GET catch no longer settling the gate          -> 1
     8. the banner reading window.LorevoxBioBuilderCore
        (undefined) and returning quietly                  -> 1
     9. the banner promising the draft "will reappear"     -> 2
    10. the empty-server exemption dropping its
        "we confirmed it earlier" half                     -> 1
    11. the confirmed-empty memory never set, so the first
        save on a new narrator is impossible again         -> 2
    12. that memory persisted to localStorage              -> 1
    13. the adopt branch unconditional, eating edits        -> 1
    14. dirty cleared on the attempt, not the confirmation -> 1
    15. the stale-token check removed                      -> 1
    16. _saveSection no longer declaring its edits         -> 2
    17. confirmed-empty not cleared when the server has
        content                                            -> 1
    18. the save iterating stored entries again            -> 1
    19. _addRepeatEntry ignoring rendered entries          -> 1
    20. _addRepeatEntry not declaring its edits            -> 1
    21. a no-op reported as a write                        -> 1
    22. the banner styling a no-op as a write              -> 1
    23. the success banner back to a 4s dismiss            -> 1
    24. save outcomes no longer stamped with pid+ticket    -> 1
    25. the banner reading the shared slot directly        -> 1

   HOW SEVERAL OF THESE WERE FOUND, because it bears on how much a green run
   here is worth:

     18  the operator, by hand, mid-walkthrough — "why is the dad missing i
         did mom and then dad and then save parents only one is there". 45
         checks and two days of live testing had passed clean. Every test
         used a single-entry section, so the whole class was invisible.
      8  the operator typing a namespace into a console. The fix for a silent
         failure was itself failing silently.
      9  a machine shut down overnight, disproving a reassurance this file
         had asserted.
  13,15,17,24,25  code review of the pushed file, not reproduction.

   And 16 scored ZERO here until 2026-09-18: the check grepped the whole
   module, and _addRepeatEntry also calls _markQuestionnaireEdited, so
   deleting it from the save path left the assertion passing. A test that
   cannot say WHICH function holds a guard is not testing that guard.

   Mutation 3 remains the one that matters most: it is the exact line that
   locked a live narrator out of saving, and a suite that still passes with
   it reverted is not protecting anything. */

console.log(failures === 0 ? "\n  all checks passed\n" : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
