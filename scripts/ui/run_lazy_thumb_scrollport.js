#!/usr/bin/env node
/**
 * Deferred thumbnails must load inside a NESTED scrollport.
 *
 * THE DEFECT THIS EXISTS TO PREVENT COMING BACK. Until 2026-08-14 the
 * trip gallery used the browser's native `loading="lazy"` hint. Native
 * lazy loading is evaluated against the DOCUMENT's scrollport, and in
 * this app the document does not scroll at all — measured live,
 * documentElement.scrollHeight 729 === clientHeight 729 — while
 * `.tdl-main`, which contains the gallery, is a real scrollport at
 * scrollHeight 471 against clientHeight 219. A probe image placed fully
 * inside the visible band AND fully inside the viewport was never
 * requested: complete=false, naturalWidth=0, no network entry, after
 * four seconds.
 *
 * WHY THIS FILE AND NOT A SOURCE SCAN. `tests/test_travel_doc_lab.py`
 * pins the shape of the fix — one decision point, root resolved by
 * walking up, disconnect on teardown, arm after the scroll restore. It
 * cannot judge whether the mechanism actually loads a picture, and that
 * is precisely the thing that was wrong before: the source LOOKED right
 * for sixteen days. So this executes the real shipped functions,
 * lifted out of ui/js/travel-doc-lab.js by name, against a DOM double
 * whose IntersectionObserver behaves the way the browser's does — it
 * intersects against the ROOT IT WAS GIVEN, and against nothing else.
 *
 * The control is the load-bearing row: a "native" observer rooted on
 * the document reports the deep tile as NOT intersecting, exactly as
 * Chrome did, so a green run cannot be produced by a double that simply
 * says yes to everything.
 *
 * Usage:  node scripts/ui/run_lazy_thumb_scrollport.js
 * Exit 0 all green, 1 otherwise. No server, no browser, no arguments.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SRC = path.resolve(__dirname, "..", "..",
  "ui", "js", "travel-doc-lab.js");
const src = fs.readFileSync(SRC, "utf8");

function extract(name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error("cannot find function " + name);
  let depth = 0;
  const open = src.indexOf("{", start);
  for (let i = open; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error("unterminated " + name);
}

function stringConst(name) {
  const m = new RegExp('var ' + name + ' = "([^"]+)";').exec(src);
  if (!m) throw new Error("cannot find " + name);
  return m[1];
}
const LAZY_ATTR = stringConst("LAZY_THUMB_ATTR");

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

// ── the DOM double ────────────────────────────────────────────────────
//
// Only what the lifted functions touch. Elements carry a `top`/`height`
// in an imaginary column so "is it inside this box" is answerable.

function makeEl(tag, opts) {
  opts = opts || {};
  const e = {
    tagName: tag.toUpperCase(),
    parentElement: null,
    children: [],
    attrs: {},
    style: { overflowY: opts.overflowY || "visible",
             overflowX: opts.overflowX || "visible" },
    top: opts.top || 0,
    height: opts.height === undefined ? 100 : opts.height,
    scrollTop: 0,
    clientHeight: opts.clientHeight === undefined ? opts.height : opts.clientHeight,
    src: "",
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    appendChild(c) { c.parentElement = this; this.children.push(c); return c; }
  };
  return e;
}

function descendants(node, out) {
  out = out || [];
  node.children.forEach(function (c) { out.push(c); descendants(c, out); });
  return out;
}

// A stand-in for the browser's own rule, and the reason this harness is
// worth anything: an element is "intersecting" a root when it lies
// within that root's VISIBLE band — the band the root actually shows,
// given its own scrollTop. A root of null means the document, which in
// this app shows everything because the document never scrolls.
function intersects(target, rootEl, rootMarginPx) {
  const m = rootMarginPx || 0;
  if (!rootEl) {
    // The document viewport. In this app it is 729 tall and does not
    // scroll, so anything laid out below it is simply never revealed.
    return target.top < DOC_VIEWPORT + m
      && target.top + target.height > 0 - m;
  }
  const bandTop = rootEl.scrollTop;
  const bandBottom = rootEl.scrollTop + rootEl.clientHeight;
  return target.top < bandBottom + m && target.top + target.height > bandTop - m;
}
const DOC_VIEWPORT = 729;

function FakeIntersectionObserver(cb, opts) {
  this._cb = cb;
  this._root = (opts && opts.root) || null;
  this._margin = parseInt((opts && opts.rootMargin) || "0", 10) || 0;
  this._targets = [];
  this.disconnected = false;
  FakeIntersectionObserver.live.push(this);
}
FakeIntersectionObserver.live = [];
FakeIntersectionObserver.prototype.observe = function (t) {
  this._targets.push(t);
  this._fire();
};
FakeIntersectionObserver.prototype.unobserve = function (t) {
  this._targets = this._targets.filter(function (x) { return x !== t; });
};
FakeIntersectionObserver.prototype.disconnect = function () {
  this.disconnected = true;
  this._targets = [];
};
// The browser re-evaluates on scroll; so do we, on demand.
FakeIntersectionObserver.prototype._fire = function () {
  if (this.disconnected) return;
  const self = this;
  const entries = this._targets.map(function (t) {
    return { target: t, isIntersecting: intersects(t, self._root, self._margin) };
  });
  if (entries.length) this._cb(entries, this);
};
function fireAll() {
  FakeIntersectionObserver.live.forEach(function (o) { o._fire(); });
}

// ── build the real page shape ─────────────────────────────────────────
//
// .tdl-root > .tdl-app > .tdl-layout > .tdl-main(scrolls) > … > .tdl-gallery
// The numbers are the ones measured on the running stack.

function buildPage(tileCount) {
  const root = makeEl("div");
  const app = makeEl("div");
  const layout = makeEl("section");
  const main = makeEl("section", {
    overflowY: "auto", height: 219, clientHeight: 219
  });
  const ws = makeEl("div");
  const gallery = makeEl("div");
  root.appendChild(app); app.appendChild(layout);
  layout.appendChild(main); main.appendChild(ws); ws.appendChild(gallery);

  const imgs = [];
  for (let i = 0; i < tileCount; i++) {
    const im = makeEl("img", { top: i * 150, height: 140 });
    im.setAttribute(LAZY_ATTR, "http://x/api/photos/p" + i + "/thumb");
    gallery.appendChild(im);
    imgs.push(im);
  }
  root.querySelectorAll = function (sel) {
    // Only the one selector armLazyThumbs uses.
    if (sel !== "img[" + LAZY_ATTR + "]") throw new Error("unexpected selector " + sel);
    return descendants(root).filter(function (n) {
      return n.tagName === "IMG" && n.getAttribute(LAZY_ATTR) !== null;
    });
  };
  return { root, main, gallery, imgs };
}

// ── lift the shipped code ─────────────────────────────────────────────

function loadModule() {
  FakeIntersectionObserver.live = [];
  const body = [
    'var destroyed = false;',
    'var root = null;',
    'var LAZY_THUMB_ATTR = ' + JSON.stringify(LAZY_ATTR) + ';',
    'var lazyThumbObservers = [];',
    extract("lazyThumbsDisconnect"),
    extract("lazyThumbLoad"),
    extract("lazyThumbScrollport"),
    extract("armLazyThumbs"),
    'return {',
    '  arm: armLazyThumbs,',
    '  disconnect: lazyThumbsDisconnect,',
    '  observers: function () { return lazyThumbObservers; },',
    '  setRoot: function (r) { root = r; },',
    '  setDestroyed: function (v) { destroyed = v; }',
    '};'
  ].join("\n");
  // getComputedStyle + IntersectionObserver + document are injected, so
  // the lifted source runs unmodified.
  const f = new Function("getComputedStyle", "IntersectionObserver", "document", body);
  return f(
    function (e) { return e.style; },
    FakeIntersectionObserver,
    { body: null, documentElement: null }
  );
}

// ── 1. the defect, reproduced against the OLD rule ────────────────────
//
// A tile deep inside .tdl-main, evaluated against the DOCUMENT, is not
// intersecting — which is why the native hint never fetched it.

(function nativeRuleControl() {
  const page = buildPage(40);
  const deep = page.imgs[30];              // top 4500, far below 729
  check("CONTROL: the old rule (document scrollport) reports a deep " +
        "tile as NOT visible — this is the bug",
        !intersects(deep, null, 0),
        "tile top=" + deep.top + " vs document viewport " + DOC_VIEWPORT);

  // …and it stays invisible however far .tdl-main is scrolled, because
  // the document never moves. That is what made it permanent.
  page.main.scrollTop = 4500;
  check("CONTROL: scrolling the nested scrollport does not rescue it " +
        "under the old rule",
        !intersects(deep, null, 0),
        "main.scrollTop=" + page.main.scrollTop);
})();

// ── 2. the fix ────────────────────────────────────────────────────────

(function armsAgainstTheRealScrollport() {
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  const obs = m.observers();
  check("one observer is created", obs.length === 1, "got " + obs.length);
  check("its root is the element that actually scrolls (.tdl-main), " +
        "not the document",
        obs.length === 1 && obs[0]._root === page.main,
        obs.length ? String(obs[0]._root === page.main) : "no observer");
})();

(function visibleTilesLoadImmediately() {
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  check("a tile inside the visible band is given a real src at once",
        page.imgs[0].src.indexOf("/thumb") > 0, page.imgs[0].src);
  check("…and its deferral attribute is cleared, so it is not fetched twice",
        page.imgs[0].getAttribute(LAZY_ATTR) === null);
})();

(function deepTilesWaitAndThenLoad() {
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  const deep = page.imgs[30];
  check("a tile far down the scrollport is NOT fetched while unseen",
        deep.src === "" && deep.getAttribute(LAZY_ATTR) !== null,
        "src=" + JSON.stringify(deep.src));

  // THE ROW THAT MATTERS. Scroll the nested scrollport to it. Under the
  // native hint this changed nothing at all.
  page.main.scrollTop = deep.top - 40;
  fireAll();
  check("scrolling .tdl-main to it DOES fetch it — the behaviour the " +
        "native hint could never produce",
        deep.src.indexOf("/thumb") > 0, deep.src || "(still empty)");
})();

(function eachTileIsFetchedOnce() {
  // SPLIT 2026-08-14. This was one check named "an already-loaded tile
  // is unobserved and never re-fetched", and it did not earn the first
  // half of that name: mutation-testing showed that DELETING the
  // unobserve call left it green. Idempotence is really guaranteed by
  // lazyThumbLoad's own early return once the attribute is gone, so the
  // sentinel survived either way. A check that passes on the defect it
  // is named for is decoration. Two claims, two checks.
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  const first = page.imgs[0];
  first.src = "SENTINEL";          // if it were re-loaded this is overwritten
  page.main.scrollTop = 900; fireAll();
  page.main.scrollTop = 0;   fireAll();
  check("an already-loaded tile is never re-fetched",
        first.src === "SENTINEL", first.src);
})();

(function loadedTilesAreUnobserved() {
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  const obs = m.observers()[0];
  const watchedAtStart = obs._targets.length;
  const loaded = page.imgs.filter(function (i) { return i.src !== ""; }).length;
  check("tiles that have loaded are dropped from the observer, so it " +
        "stops doing work and stops holding them",
        obs._targets.length === watchedAtStart && loaded > 0
          && obs._targets.length === page.imgs.length - loaded,
        "watching " + obs._targets.length + " of " + page.imgs.length +
        ", " + loaded + " loaded");
})();

(function teardownReleasesEverything() {
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  const obs = m.observers()[0];
  m.disconnect();
  check("teardown disconnects the observer", obs.disconnected === true);
  check("…and drops its own handles, so a torn-down mount holds no " +
        "reference to the detached workspace",
        m.observers().length === 0, "held " + m.observers().length);
})();

(function reArmingDropsThePreviousObservers() {
  const page = buildPage(40);
  const m = loadModule();
  m.setRoot(page.root);
  m.arm();
  const firstObs = m.observers()[0];
  // renderAll() rebuilds the DOM and re-arms; the old observer is
  // watching elements that no longer exist.
  const page2 = buildPage(40);
  m.setRoot(page2.root);
  m.arm();
  check("re-arming disconnects the previous observer",
        firstObs.disconnected === true);
  check("…and leaves exactly one live observer, not two",
        m.observers().length === 1, "held " + m.observers().length);
})();

(function noObserverMeansLoadEverything() {
  const page = buildPage(12);
  FakeIntersectionObserver.live = [];
  const body = [
    'var destroyed = false;',
    'var root = null;',
    'var LAZY_THUMB_ATTR = ' + JSON.stringify(LAZY_ATTR) + ';',
    'var lazyThumbObservers = [];',
    extract("lazyThumbsDisconnect"),
    extract("lazyThumbLoad"),
    extract("lazyThumbScrollport"),
    extract("armLazyThumbs"),
    'return { arm: armLazyThumbs, setRoot: function (r) { root = r; } };'
  ].join("\n");
  const mod = new Function("getComputedStyle", "IntersectionObserver", "document", body)(
    function (e) { return e.style; },
    undefined,                       // engine without IntersectionObserver
    { body: null, documentElement: null }
  );
  mod.setRoot(page.root);
  mod.arm();
  const unloaded = page.imgs.filter(function (i) { return i.src === ""; });
  check("without IntersectionObserver every tile loads eagerly — a " +
        "slower grid, never a blank one",
        unloaded.length === 0, unloaded.length + " left unloaded");
})();

(function aTornDownMountDoesNotArm() {
  const page = buildPage(12);
  const m = loadModule();
  m.setRoot(page.root);
  m.setDestroyed(true);
  m.arm();
  check("a destroyed mount arms nothing",
        m.observers().length === 0 && page.imgs[0].src === "");
})();

// ── report ────────────────────────────────────────────────────────────

let failed = 0;
R.forEach(function (r) {
  if (!r.ok) failed++;
  console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
    (r.detail ? "  [" + r.detail + "]" : ""));
});
console.log("");
console.log(R.length - failed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
