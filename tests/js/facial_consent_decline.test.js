// Minimal DOM/localStorage shim, then load the real module.
const store = {};
global.localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; },
  key: i => Object.keys(store)[i],
  get length() { return Object.keys(store).length; },
};
global.document = {
  getElementById: () => null,
  createElement: () => ({ style:{}, classList:{add(){},remove(){}}, appendChild(){}, querySelector: () => null, addEventListener(){} }),
  body: { appendChild(){}, classList:{add(){},remove(){}} },
  querySelector: () => null,
  addEventListener(){},
};
global.window = global;
global.navigator = { mediaDevices: {} };

const fs = require('fs');
eval(fs.readFileSync('ui/js/facial-consent.js', 'utf8'));
const FC = global.FacialConsent;

let fail = 0;
const ck = (name, cond) => { console.log((cond ? '  ok  ' : '  FAIL') + '  ' + name); if (!cond) fail++; };

const A = 'aaaa-1111', B = 'bbbb-2222';

// --- a DECLINE must persist ---------------------------------------------
FC.setNarrator(A);
FC._decline();
ck('decline writes a record', localStorage.getItem('lorevox_facial_consent:' + A) === 'false');
ck('decline is reflected in isDeclined()', FC.isDeclined() === true);

// simulate a page reload: re-eval the module against the SAME localStorage
eval(fs.readFileSync('ui/js/facial-consent.js', 'utf8'));
const FC2 = global.FacialConsent;
FC2.setNarrator(A);
ck('AFTER RELOAD the narrator is still declined (not re-asked)', FC2.isDeclined() === true);
ck('...and not silently granted', FC2.isGranted() === false);

// --- decline is PER NARRATOR --------------------------------------------
FC2.setNarrator(B);
ck('a different narrator is NOT inheriting the decline', FC2.isDeclined() === false);
ck('...and has no stored record yet', localStorage.getItem('lorevox_facial_consent:' + B) === null);

// --- a legacy global grant must NOT overwrite a stored decline ----------
localStorage.setItem('lorevox_facial_consent_granted', 'true');   // legacy global
eval(fs.readFileSync('ui/js/facial-consent.js', 'utf8'));
const FC3 = global.FacialConsent;
FC3.setNarrator(A);   // A previously DECLINED
ck('legacy grant does NOT opt a declining narrator back in', FC3.isGranted() === false);
ck('...their stored NO survives migration', localStorage.getItem('lorevox_facial_consent:' + A) === 'false');

// ...but a narrator with NO record still inherits the legacy grant
FC3.setNarrator(B);
ck('a never-asked narrator still inherits the legacy grant', FC3.isGranted() === true);

// --- the operator can still re-open the question ------------------------
FC3.setNarrator(A);
FC3.revokeStored();
ck('revokeStored clears the record so the narrator can be asked again',
   localStorage.getItem('lorevox_facial_consent:' + A) === null);
ck('...and they are no longer marked declined', FC3.isDeclined() === false);

process.exit(fail ? 1 : 0);
