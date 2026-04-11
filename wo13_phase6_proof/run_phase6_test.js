/* ═══════════════════════════════════════════════════════════════════════
   WO-13 Phase 6 — Review UI test harness
   Node-executed. Loads /ui/js/wo13-review.js in a lightweight sandbox
   that provides a fake `document`, `fetch`, and `API` so the pure
   helpers + network wrappers + DOM rendering can all be exercised
   without a browser.
═══════════════════════════════════════════════════════════════════════ */
"use strict";
const fs   = require("fs");
const path = require("path");
const vm   = require("vm");

const REPO_ROOT = path.resolve(__dirname, "..", "mnt", "hornelore");
const REVIEW_JS = path.join(REPO_ROOT, "ui", "js", "wo13-review.js");
const HTML_FILE = path.join(REPO_ROOT, "ui", "hornelore1.0.html");

let passed = 0, failed = 0;
function ok(label, cond, extra){
  if(cond){ passed++; console.log("  ✔ " + label); }
  else    { failed++; console.log("  ✘ " + label + (extra ? "  → " + extra : "")); }
}

// ── 1. Build a tiny fake DOM for the module to talk to ─────────────────
//    Nothing fancy: enough to verify rendering logic without jsdom.
function makeFakeElement(id){
  const el = {
    id,
    innerHTML: "",
    style: {},
    _attrs: {},
    _listeners: {},
    _children: [],
    disabled: false,
    _wo13Wired: false,
    getAttribute(k){ return this._attrs[k]; },
    setAttribute(k,v){ this._attrs[k] = v; },
    addEventListener(ev, fn){ (this._listeners[ev] ||= []).push(fn); },
    removeEventListener(){},
    matches(){ return false; },
    showPopover(){ this._attrs["data-popover-open"] = "1"; },
    hidePopover(){ delete this._attrs["data-popover-open"]; },
    querySelector(sel){
      return _queryFromHtml(this.innerHTML, sel, /*one*/true, this);
    },
    querySelectorAll(sel){
      return _queryFromHtml(this.innerHTML, sel, /*one*/false, this);
    },
  };
  return el;
}

// A crude selector matcher that returns synthetic child elements with
// .getAttribute/.addEventListener so click handlers can be simulated.
function _queryFromHtml(html, sel, one, parentEl){
  // Support: tag, [attr="value"], button[attr="value"], "button[data-wo13-filter]"
  const m = sel.match(/^([a-z]*)(?:\[([a-z\-0-9_]+)(?:="?([^"\]]*)"?)?\])?$/i);
  if(!m) return one ? null : [];
  const [_, tag, attr, val] = m;
  const rx = new RegExp(`<${tag || "[a-z]+"}[^>]*${attr ? attr+'="[^"]*"' : ""}[^>]*>`, "gi");
  const items = [];
  let mm;
  while((mm = rx.exec(html)) !== null){
    const open = mm[0];
    if(attr && val !== undefined && !open.includes(`${attr}="${val}"`)) continue;
    const getA = (name) => {
      const am = open.match(new RegExp(`${name}="([^"]*)"`));
      return am ? am[1] : null;
    };
    const synthetic = {
      _open: open,
      _listeners: {},
      disabled: false,
      getAttribute: getA,
      addEventListener(ev, fn){ (this._listeners[ev] ||= []).push(fn); },
      click(){
        const ls = this._listeners.click || [];
        for(const fn of ls){ fn.call(this, {}); }
      },
    };
    items.push(synthetic);
    if(one) break;
  }
  return one ? (items[0] || null) : items;
}

const fakeEls = {};
const WO13_IDS = [
  "wo13ReviewPopover", "wo13ReviewFilters", "wo13ReviewList",
  "wo13ContaminationBanner", "wo13ReadOnlyNotice",
  "wo13RowDetailModal", "wo13RowDetailBody",
  "wo13ReviewHelpPopover", "wo13BulkDismissBtn", "wo13PromoteBtn",
];
for(const id of WO13_IDS) fakeEls[id] = makeFakeElement(id);

const fakeDoc = {
  getElementById(id){ return fakeEls[id] || null; },
  addEventListener(){},
};

// ── 2. Fake fetch + API, configurable per test ─────────────────────────
const fetchLog = [];
let fetchHandler = async (url, opts) => {
  fetchLog.push({ url, method: (opts && opts.method) || "GET", body: opts && opts.body });
  return { ok: true, status: 200, json: async () => ({}) };
};
function resetFetchLog(){ fetchLog.length = 0; }

const API = {
  FT_ROWS_LIST:  (pid) => `http://local/api/family-truth/rows?person_id=${pid}`,
  FT_ROW_PATCH:  (rid) => `http://local/api/family-truth/row/${rid}`,
  FT_AUDIT:      (rid) => `http://local/api/family-truth/audit/${rid}`,
  FT_PROMOTE:     `http://local/api/family-truth/promote`,
  ROLLING_SUMMARY_GET:    (pid) => `http://local/api/transcript/rolling-summary?person_id=${pid}`,
  ROLLING_SUMMARY_CLEAN:  (pid) => `http://local/api/transcript/rolling-summary/clean?person_id=${pid}`,
};

// ── 3. Build sandbox and execute the module ────────────────────────────
const sandbox = {
  document: fakeDoc,
  fetch: async (url, opts) => fetchHandler(url, opts),
  API,
  state: { person_id: null },
  confirm: () => true,
  console,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

const src = fs.readFileSync(REVIEW_JS, "utf8");
vm.runInContext(src, sandbox, { filename: "wo13-review.js" });

// ── 4. Pure helper tests ───────────────────────────────────────────────
console.log("\n── Pure helpers ────────────────────────────────────");

{
  const norm = sandbox.wo13NormaliseRow({
    id: 42, subject_name: "  Kent James Horne ", field: "employment",
    source_says: "worked at the shipyard", status: "needs_verify",
    confidence: 0.6, extraction_method: "rules_fallback",
  });
  ok("normalise: id coerced to string", norm.id === "42");
  ok("normalise: subject trimmed", norm.subject_name === "Kent James Horne");
  ok("normalise: default confidence preserved", norm.confidence === 0.6);
  ok("normalise: provenance defaults to {}", typeof norm.provenance === "object");
  ok("normalise: meaning_tags defaults to []", Array.isArray(norm.meaning_tags));
}

{
  const rows = [
    { id: 1, field: "employment", status: "needs_verify" },
    { id: 2, field: "marriage",   status: "approve" },
    { id: 3, field: "personal.dateOfBirth", status: "source_only" },
    { id: 4, field: "employment", status: "reject" },
    { id: 5, field: "residence",  status: "approve_q" },
    { id: 6, field: "something",  status: "garbage_status" }, // should fall into needs_verify
  ];
  const counts = sandbox.wo13CountByStatus(rows);
  ok("counts: total all == 6", counts.all === 6);
  ok("counts: needs_verify == 2 (1 native + 1 coerced)", counts.needs_verify === 2);
  ok("counts: approve == 1", counts.approve === 1);
  ok("counts: approve_q == 1", counts.approve_q === 1);
  ok("counts: source_only == 1", counts.source_only === 1);
  ok("counts: reject == 1", counts.reject === 1);

  const groups = sandbox.wo13GroupByStatus(rows);
  ok("group: all 5 status buckets present",
    Object.keys(groups).length === 5);
  ok("group: garbage_status falls into needs_verify",
    groups.needs_verify.some(r => String(r.id) === "6"));
}

{
  ok("protected: personal.fullName is protected",
     sandbox.wo13IsProtectedIdentityField("personal.fullName"));
  ok("protected: personal.dateOfBirth is protected",
     sandbox.wo13IsProtectedIdentityField("personal.dateOfBirth"));
  ok("protected: employment is NOT protected",
     !sandbox.wo13IsProtectedIdentityField("employment"));

  const allowedFree = sandbox.wo13AllowedStatusesForRow({ field: "employment" });
  ok("allowed-statuses: free field has all 5", allowedFree.length === 5);

  const allowedProt = sandbox.wo13AllowedStatusesForRow({ field: "personal.fullName" });
  ok("allowed-statuses: protected field has only source_only + reject",
     allowedProt.length === 2
     && allowedProt.includes("source_only")
     && allowedProt.includes("reject"));
}

{
  // Promotability guard: protected field + rules_fallback never promotable.
  const blocked = sandbox.wo13IsPromotable({
    id: 99, subject_name: "Kent", field: "personal.dateOfBirth",
    status: "approve", extraction_method: "rules_fallback",
  });
  ok("promotable: protected rules_fallback blocked", blocked === false);

  const manualOverride = sandbox.wo13IsPromotable({
    id: 100, subject_name: "Kent", field: "personal.dateOfBirth",
    status: "approve", extraction_method: "manual",
  });
  ok("promotable: protected MANUAL allowed", manualOverride === true);

  const freeApproved = sandbox.wo13IsPromotable({
    id: 101, subject_name: "Kent", field: "marriage",
    status: "approve", extraction_method: "rules_fallback",
  });
  ok("promotable: free rules_fallback approved OK", freeApproved === true);

  const notApproved = sandbox.wo13IsPromotable({
    id: 102, subject_name: "Kent", field: "marriage",
    status: "needs_verify", extraction_method: "rules_fallback",
  });
  ok("promotable: needs_verify blocked", notApproved === false);
}

{
  // Banner state
  const off = sandbox.wo13ContaminationBannerState(null);
  ok("banner: null summary → hidden", off.show === false && off.total === 0);

  const clean = sandbox.wo13ContaminationBannerState({ scored_items: [] });
  ok("banner: no wo13_filtered → hidden", clean.show === false);

  const hit = sandbox.wo13ContaminationBannerState({
    wo13_filtered: {
      dropped_scored_items: 3,
      dropped_threads: 1,
      dropped_facts: 2,
      dropped_reasons: {
        "cross_narrator:williston_source": 2,
        "stress_test:stress_test": 2,
        "meta_command:ignore previous": 1,
        "truncation": 1,
      },
    },
  });
  ok("banner: dirty summary → show=true", hit.show === true);
  ok("banner: dirty summary → total counted", hit.total === 6);
  ok("banner: dirty summary → 4 reasons preserved",
     Object.keys(hit.reasons).length === 4);
}

{
  // Bulk-target IDs respect filter
  const rows = [
    { id: "A", status: "needs_verify" },
    { id: "B", status: "needs_verify" },
    { id: "C", status: "approve" },
    { id: "D", status: "reject" },
  ];
  const all = sandbox.wo13BulkTargetIds(rows, "all");
  ok("bulk-target: all → 4 IDs", all.length === 4);
  const nv = sandbox.wo13BulkTargetIds(rows, "needs_verify");
  ok("bulk-target: needs_verify → 2 IDs", nv.length === 2 && nv.includes("A") && nv.includes("B"));
  const none = sandbox.wo13BulkTargetIds(rows, "approve_q");
  ok("bulk-target: approve_q → 0 IDs", none.length === 0);
}

// ── 5. Network wrapper tests ───────────────────────────────────────────
console.log("\n── Network wrappers ────────────────────────────────");

(async () => {
  resetFetchLog();
  fetchHandler = async (url, opts) => {
    fetchLog.push({ url, method: (opts && opts.method) || "GET", body: opts && opts.body });
    return { ok: true, status: 200, json: async () => ({ rows: [
      { id: "r1", subject_name: "Kent James Horne", field: "employment",
        source_says: "worked at shipyard", status: "needs_verify",
        extraction_method: "rules_fallback", confidence: 0.6 },
      { id: "r2", subject_name: "Kent James Horne", field: "personal.dateOfBirth",
        source_says: "born 1943", status: "source_only",
        extraction_method: "rules_fallback", confidence: 0.45,
        provenance: { identity_conflict: true, protected_field: "personal.dateOfBirth" }},
    ]}) };
  };
  const rows = await sandbox.wo13FetchRows("pid-kent");
  ok("fetch-rows: returns 2 rows", rows.length === 2);
  ok("fetch-rows: URL contains person_id", fetchLog[0].url.includes("pid-kent"));

  // Patch
  resetFetchLog();
  fetchHandler = async (url, opts) => {
    fetchLog.push({ url, method: opts.method, body: opts.body });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  const p1 = await sandbox.wo13PatchRowStatus("r1", "reject");
  ok("patch: returns ok for valid status", p1.ok === true);
  ok("patch: method is PATCH", fetchLog[0].method === "PATCH");
  ok("patch: body includes {status:'reject'}", fetchLog[0].body.includes("reject"));

  const pBad = await sandbox.wo13PatchRowStatus("r1", "laser_beam");
  ok("patch: invalid status rejected", pBad.ok === false);

  // Promote
  resetFetchLog();
  fetchHandler = async (url, opts) => {
    fetchLog.push({ url, method: opts.method, body: opts.body });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  await sandbox.wo13PromoteApproved("pid-kent");
  ok("promote: POST to FT_PROMOTE",
     fetchLog[0].method === "POST" && fetchLog[0].url.endsWith("/api/family-truth/promote"));

  // Rolling summary clean
  resetFetchLog();
  await sandbox.wo13RunRollingSummaryClean("pid-kent");
  ok("rs-clean: POST to rolling-summary/clean",
     fetchLog[0].method === "POST"
     && fetchLog[0].url.includes("/api/transcript/rolling-summary/clean"));

  // ── 6. DOM rendering tests ────────────────────────────────────────────
  console.log("\n── DOM rendering ───────────────────────────────────");

  // Seed state and force a reload
  sandbox.state.person_id = "pid-kent";
  fetchHandler = async (url) => {
    if(url.includes("/family-truth/rows")){
      return { ok: true, status: 200, json: async () => ({ rows: [
        { id: "r1", subject_name: "Kent James Horne", field: "employment",
          source_says: "worked at shipyard", status: "needs_verify",
          extraction_method: "rules_fallback", confidence: 0.6 },
        { id: "r2", subject_name: "Kent James Horne", field: "personal.dateOfBirth",
          source_says: "born 1943", status: "source_only",
          extraction_method: "rules_fallback", confidence: 0.45,
          provenance: { identity_conflict: true, protected_field: "personal.dateOfBirth" }},
        { id: "r3", subject_name: "Janice Ann Horne", field: "marriage",
          source_says: "married Robert in 1968", status: "approve",
          extraction_method: "rules_fallback", confidence: 0.8 },
      ]}) };
    }
    if(url.includes("/rolling-summary")){
      return { ok: true, status: 200, json: async () => ({
        wo13_filtered: {
          dropped_scored_items: 2,
          dropped_threads: 1,
          dropped_facts: 0,
          dropped_reasons: {
            "stress_test:stress_test": 2,
            "cross_narrator:williston_source": 1,
          },
        },
      }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };
  await sandbox.wo13ReloadReviewQueue();

  const list = fakeEls.wo13ReviewList.innerHTML;
  ok("render: list mentions Kent", list.includes("Kent James Horne"));
  ok("render: list mentions Janice", list.includes("Janice Ann Horne"));
  ok("render: protected row shows identity badge",
     list.includes("wo13-protected"));
  ok("render: protected row includes only source_only+reject actions",
     list.includes('data-wo13-set="source_only"')
     && list.includes('data-wo13-set="reject"'));

  // Verify the protected row does NOT offer approve
  const protRowStart = list.indexOf('data-wo13-row-id="r2"');
  const protRowEnd   = list.indexOf('</div>', protRowStart + 10);
  const protRowChunk = list.slice(protRowStart, list.indexOf('wo13-row"', protRowEnd) || list.length);
  ok("render: protected row has NO approve/approve_q buttons",
     !protRowChunk.includes('data-wo13-set="approve"')
     && !protRowChunk.includes('data-wo13-set="approve_q"'));

  const filters = fakeEls.wo13ReviewFilters.innerHTML;
  ok("filters: All tab rendered",    filters.includes('data-wo13-filter="all"'));
  ok("filters: needs_verify tab",    filters.includes('data-wo13-filter="needs_verify"'));
  ok("filters: approve tab",         filters.includes('data-wo13-filter="approve"'));
  ok("filters: approve_q tab",       filters.includes('data-wo13-filter="approve_q"'));
  ok("filters: source_only tab",     filters.includes('data-wo13-filter="source_only"'));
  ok("filters: reject tab",          filters.includes('data-wo13-filter="reject"'));

  const banner = fakeEls.wo13ContaminationBanner.innerHTML;
  ok("banner: rendered when filter active", banner.length > 0);
  ok("banner: shows stress_test reason", banner.includes("stress_test"));
  ok("banner: shows williston reason", banner.includes("williston_source"));
  ok("banner: shows 3 dropped items total", banner.includes("3 item(s) dropped"));

  // ── 7. Reference narrator read-only guard ─────────────────────────────
  console.log("\n── Reference narrator guard ────────────────────────");

  sandbox._wo13IsReferenceNarrator = (pid) => pid === "pid-shatner";
  sandbox.state.person_id = "pid-shatner";
  fetchHandler = async (url) => {
    return { ok: true, status: 200, json: async () => ({ rows: [] }) };
  };
  await sandbox.wo13ReloadReviewQueue();
  const readOnlyHtml = fakeEls.wo13ReviewList.innerHTML;
  ok("read-only: reference narrator shows notice",
     readOnlyHtml.includes("Reference narrator"));
  ok("read-only: bulk dismiss disabled",
     fakeEls.wo13BulkDismissBtn.disabled === true);
  ok("read-only: promote disabled",
     fakeEls.wo13PromoteBtn.disabled === true);

  // Bulk dismiss refuses when read-only
  const bd = await sandbox.wo13BulkDismissVisible();
  ok("read-only: wo13BulkDismissVisible refuses", bd.ok === false && bd.reason === "read_only");

  // Promote refuses when read-only
  const pr = await sandbox.wo13PromoteClicked();
  ok("read-only: wo13PromoteClicked refuses", pr.ok === false && pr.reason === "read_only");

  // ── 8. Bulk dismiss happy path ────────────────────────────────────────
  console.log("\n── Bulk dismiss ────────────────────────────────────");

  sandbox._wo13IsReferenceNarrator = () => false;
  sandbox.state.person_id = "pid-kent";
  fetchHandler = async (url) => {
    if(url.includes("/family-truth/rows")){
      return { ok: true, status: 200, json: async () => ({ rows: [
        { id: "r1", subject_name: "Kent", field: "employment",
          source_says: "foo", status: "needs_verify",
          extraction_method: "rules_fallback", confidence: 0.6 },
        { id: "r2", subject_name: "Kent", field: "residence",
          source_says: "bar", status: "needs_verify",
          extraction_method: "rules_fallback", confidence: 0.6 },
        { id: "r3", subject_name: "Kent", field: "marriage",
          source_says: "baz", status: "approve",
          extraction_method: "rules_fallback", confidence: 0.8 },
      ]}) };
    }
    if(url.includes("/rolling-summary")) return { ok: true, status: 200, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => ({}) };
  };
  await sandbox.wo13ReloadReviewQueue();

  // Switch filter to needs_verify only
  sandbox._wo13State.filter = "needs_verify";
  resetFetchLog();
  fetchHandler = async (url, opts) => {
    fetchLog.push({ url, method: opts && opts.method, body: opts && opts.body });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  const result = await sandbox.wo13BulkDismissVisible();
  ok("bulk: dismissed 2 (needs_verify rows only)", result.dismissed === 2);
  ok("bulk: did NOT touch approved row r3",
     !fetchLog.some(f => f.url.includes("/row/r3")));
  ok("bulk: patched r1", fetchLog.some(f => f.url.includes("/row/r1") && f.body.includes("reject")));
  ok("bulk: patched r2", fetchLog.some(f => f.url.includes("/row/r2") && f.body.includes("reject")));

  // Verify in-memory state was flipped
  const r1 = sandbox._wo13State.rows.find(r => r.id === "r1");
  const r3 = sandbox._wo13State.rows.find(r => r.id === "r3");
  ok("bulk: r1 now status=reject", r1.status === "reject");
  ok("bulk: r3 still status=approve", r3.status === "approve");

  // ── 9. HTML scaffolding invariants ───────────────────────────────────
  console.log("\n── HTML scaffolding invariants ─────────────────────");
  const html = fs.readFileSync(HTML_FILE, "utf8");
  ok("html: wo13-review.js script tag present",
     html.includes('<script src="js/wo13-review.js"></script>'));
  ok("html: review drawer popover present",
     html.includes('id="wo13ReviewPopover"') && html.includes('popover="auto"'));
  ok("html: review drawer trigger button present",
     html.includes('id="wo13ReviewBtn"') && html.includes('popovertarget="wo13ReviewPopover"'));
  ok("html: row detail modal present",
     html.includes('id="wo13RowDetailModal"'));
  ok("html: help popover present",
     html.includes('id="wo13ReviewHelpPopover"'));
  ok("html: help popover explains 4 layers",
     html.includes("Shadow") && html.includes("Proposal") && html.includes("Promoted Truth"));
  ok("html: help popover explains 5 statuses",
     html.includes("needs_verify") && html.includes("approve") && html.includes("approve_q")
     && html.includes("source_only") && html.includes("reject"));
  ok("html: help popover names 5 protected identity fields",
     html.includes("personal.fullName") && html.includes("personal.preferredName")
     && html.includes("personal.dateOfBirth") && html.includes("personal.placeOfBirth")
     && html.includes("personal.birthOrder"));
  ok("html: reference-narrator read-only note mentioned",
     html.includes("Reference narrators") && html.includes("read-only"));
  ok("html: bulk dismiss button present",
     html.includes('id="wo13BulkDismissBtn"'));
  ok("html: promote button present",
     html.includes('id="wo13PromoteBtn"'));
  ok("html: contamination banner container present",
     html.includes('id="wo13ContaminationBanner"'));
  ok("html: CSS defines wo13-status-approve", html.includes(".wo13-status-approve"));
  ok("html: CSS defines wo13-status-reject",  html.includes(".wo13-status-reject"));
  ok("html: CSS defines wo13-status-source_only", html.includes(".wo13-status-source_only"));
  ok("html: CSS defines wo13-protected identity badge", html.includes(".wo13-protected"));
  ok("html: CSS defines wo13-readonly-notice style", html.includes(".wo13-readonly-notice"));

  // ── 10. Regression — wo13-review.js does not touch /api/facts/add ────
  ok("regression: wo13-review.js does not call legacy /api/facts/add",
     !src.includes("facts/add"));
  ok("regression: wo13-review.js routes through /api/family-truth/*",
     src.includes("FT_ROWS_LIST") && src.includes("FT_ROW_PATCH")
     && src.includes("FT_PROMOTE") && src.includes("FT_AUDIT"));

  // ── Summary ───────────────────────────────────────────────────────────
  console.log("\n────────────────────────────────────────────────────");
  console.log(`  ${passed} passed, ${failed} failed`);
  console.log("────────────────────────────────────────────────────");
  if(failed > 0) process.exit(1);
})();
