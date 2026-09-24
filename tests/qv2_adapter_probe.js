/* Probe for tests/test_qv2_adapter.py (Batch C-1).

   Loads the SHIPPED ui/js/questionnaire-v2-model.js into a sandbox whose IO
   globals — fetch, XMLHttpRequest, localStorage, sessionStorage, indexedDB,
   document, navigator.sendBeacon — record every access. Runs fromRecord on a
   record the Python side produced through the shipped writer and assembler,
   and prints {view, touched} as JSON.

   usage: node tests/qv2_adapter_probe.js <record.json> [trips.json] */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const record = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const trips = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], "utf8")) : undefined;
const SRC = fs.readFileSync(path.join(__dirname, "..", "ui", "js", "questionnaire-v2-model.js"), "utf8");

const touched = [];
const trap = (name) => ({ get() { touched.push(name); return undefined; }, configurable: true });
const win = {};
["fetch", "XMLHttpRequest", "localStorage", "sessionStorage", "indexedDB", "document",
 "navigator", "WebSocket", "EventSource"].forEach((n) => Object.defineProperty(win, n, trap(n)));
const ctx = { window: win, console };
["fetch", "XMLHttpRequest", "localStorage", "sessionStorage", "indexedDB", "document",
 "navigator", "WebSocket", "EventSource"].forEach((n) => Object.defineProperty(ctx, n, trap(n)));
vm.createContext(ctx);
vm.runInContext(SRC, ctx, { filename: "questionnaire-v2-model.js" });

const api = win.LorevoxQuestionnaireV2Model;
if (!api) { console.error("the shipped module did not register itself"); process.exit(2); }
const view = api.fromRecord(record, trips ? { trips } : undefined);
const again = api.fromRecord(record, trips ? { trips } : undefined);
process.stdout.write(JSON.stringify({
  view, touched,
  deterministic: JSON.stringify(view) === JSON.stringify(again),
  topics: api.TOPICS, answer: api.ANSWER,
}));
