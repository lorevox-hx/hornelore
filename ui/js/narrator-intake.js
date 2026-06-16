// WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 1 intake form module.
//
// Replaces the bare prompt("name?") fallback with a structured modal
// that captures the required identity floor (6 fields) plus consent
// before a narrator row is created. Saves via POST /api/people with
// the extended payload, then either lands the operator in Interview
// Mode or hands off to the Bio Builder lane.
//
// Public API exposed on window:
//   lvOpenNarratorIntake()           — open the modal
//   lvCloseNarratorIntake()          — close it
//   lvNarratorIntakeSubmit()         — wired to the Save buttons
//   lvNarratorIntakeSkipTesting()    — the testing-only escape hatch
//
// Phase 1 covered the required block + consent. Phase 2C ships the
// optional sections (family of origin / marriage / children /
// education / military / faith / today) and POSTs the consolidated
// payload to the Phase 2B orchestrator at /api/people/intake — which
// fans out to people row + consent_attestations + profile_json merge +
// bio_facts inserts so Lori sees the data on the very first turn.

(function () {
  'use strict';

  const ENDPOINT_PEOPLE = (typeof API !== 'undefined' && API.PEOPLE)
    ? API.PEOPLE
    : ((typeof ORIGIN !== 'undefined' && ORIGIN)
      ? ORIGIN + '/api/people'
      : 'http://localhost:8000/api/people');

  // Phase 2B orchestrator — fans out the full 9-section payload across
  // people + consent_attestations + profile_json + bio_facts.
  const ENDPOINT_INTAKE = (typeof ORIGIN !== 'undefined' && ORIGIN)
    ? ORIGIN + '/api/people/intake'
    : 'http://localhost:8000/api/people/intake';

  // Modal element ids (kept in sync with hornelore1.0.html mount block)
  const MODAL_ID = 'lvNarratorIntakeModal';
  const FORM_ID = 'lvNarratorIntakeForm';
  const ERROR_BAR_ID = 'lvNarratorIntakeErrorBar';
  const DOB_HELPER_ID = 'lvNarratorIntakeDobHelper';

  // Field ids
  const F = {
    fullName: 'lvIntakeFullName',
    preferredName: 'lvIntakePreferredName',
    dob: 'lvIntakeDob',
    pob: 'lvIntakePob',
    currentResidence: 'lvIntakeCurrentResidence',
    pronouns: 'lvIntakePronouns',
    pronounsOther: 'lvIntakePronounsOther',
    consentRecording: 'lvIntakeConsentRecording',
    consentDisclosure: 'lvIntakeConsentDisclosure',
  };

  function $(id) { return document.getElementById(id); }

  // ── DOB live helper ──────────────────────────────────────────────
  //
  // As the operator types a DOB, compute age + a brief historical
  // orientation phrase. Pure client-side. Never persisted.

  function _isValidDateString(s) {
    if (!s) return false;
    // YYYY-MM-DD or YYYY-M-D after html5 date input normalizes
    const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s);
    if (!m) return false;
    const y = +m[1], mo = +m[2], d = +m[3];
    if (y < 1850 || y > new Date().getFullYear()) return false;
    if (mo < 1 || mo > 12) return false;
    if (d < 1 || d > 31) return false;
    const dt = new Date(y, mo - 1, d);
    return dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === d;
  }

  function _computeAge(dobStr) {
    const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(dobStr);
    if (!m) return null;
    const y = +m[1], mo = +m[2], d = +m[3];
    const today = new Date();
    let age = today.getFullYear() - y;
    const beforeBirthday =
      today.getMonth() < mo - 1 ||
      (today.getMonth() === mo - 1 && today.getDate() < d);
    if (beforeBirthday) age -= 1;
    return age;
  }

  function _formatPrettyDate(dobStr) {
    const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(dobStr);
    if (!m) return dobStr;
    const y = +m[1], mo = +m[2], d = +m[3];
    const months = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    return months[mo - 1] + ' ' + d + ', ' + y;
  }

  // Coarse historical orientation. Picks one phrase based on the
  // year a school-age narrator would have been growing up. Not a
  // history book; just a friendly nudge so the operator can sanity-
  // check the DOB at a glance.
  function _historicalOrientation(birthYear) {
    if (birthYear == null) return '';
    if (birthYear <= 1900) return 'born in the late 19th century';
    if (birthYear <= 1915) return 'born just before the First World War';
    if (birthYear <= 1929) return 'born just before the Great Depression';
    if (birthYear <= 1939) return 'born in the Depression years';
    if (birthYear <= 1945) return 'born during the Second World War';
    if (birthYear <= 1955) return 'born in the postwar years';
    if (birthYear <= 1965) return 'born in the early Cold War';
    if (birthYear <= 1975) return 'born during the Vietnam era';
    if (birthYear <= 1985) return 'born in the late Cold War / early personal-computer years';
    if (birthYear <= 1995) return 'born at the end of the Cold War';
    if (birthYear <= 2005) return 'born around the turn of the millennium';
    return 'born in the 21st century';
  }

  function _updateDobHelper() {
    const helper = $(DOB_HELPER_ID);
    if (!helper) return;
    const raw = ($(F.dob) || {}).value || '';
    if (!raw) {
      helper.textContent = '';
      helper.style.display = 'none';
      return;
    }
    if (!_isValidDateString(raw)) {
      helper.textContent = '(not a valid date)';
      helper.style.display = 'block';
      helper.classList.add('lv-intake-helper-error');
      return;
    }
    helper.classList.remove('lv-intake-helper-error');
    const pretty = _formatPrettyDate(raw);
    const age = _computeAge(raw);
    const yearMatch = /^(\d{4})/.exec(raw);
    const orient = yearMatch ? _historicalOrientation(+yearMatch[1]) : '';
    helper.textContent =
      'born ' + pretty +
      (age != null ? ' — ' + age + ' years old' : '') +
      (orient ? ' — ' + orient : '');
    helper.style.display = 'block';
  }

  // ── Validation ───────────────────────────────────────────────────

  function _val(id) {
    var el = $(id);
    if (!el) return '';
    return (el.value || '').trim();
  }
  function _intOrNull(s) {
    if (!s) return null;
    var n = parseInt(s, 10);
    return isNaN(n) ? null : n;
  }

  function _collectRepeater(nameCls, secondCls, thirdCls) {
    // Walk the rows by index — each row has a name input + 1-2 sidekick
    // inputs (date / year / status). A row counts only if its name is
    // non-empty.
    var nameEls = document.querySelectorAll('.' + nameCls);
    var secondEls = secondCls ? document.querySelectorAll('.' + secondCls) : [];
    var thirdEls = thirdCls ? document.querySelectorAll('.' + thirdCls) : [];
    var rows = [];
    for (var i = 0; i < nameEls.length; i++) {
      var name = (nameEls[i].value || '').trim();
      if (!name) continue;
      var row = { name: name };
      if (secondEls[i]) {
        var s = (secondEls[i].value || '').trim();
        if (s) row._second = s;
      }
      if (thirdEls[i]) {
        var t = (thirdEls[i].value || '').trim();
        if (t) row._third = t;
      }
      rows.push(row);
    }
    return rows;
  }

  function _readForm() {
    // Identity + consent block (Phase 1)
    var base = {
      preferred_name: _val(F.preferredName),
      full_legal_name: _val(F.fullName),
      date_of_birth: _val(F.dob),
      place_of_birth: _val(F.pob),
      current_residence: _val(F.currentResidence),
      pronouns: (
        (document.querySelector('input[name="lvIntakePronouns"]:checked') || {}).value
      ) || '',
      pronouns_other: _val(F.pronounsOther),
      consent_recording_agreement: !!($(F.consentRecording) || {}).checked,
      consent_disclosure_reviewed: !!($(F.consentDisclosure) || {}).checked,
    };

    // Family of origin
    var sibRows = _collectRepeater('lv-intake-sibling-name', 'lv-intake-sibling-dob');
    var siblings = sibRows.map(function (r, idx) {
      return {
        name: r.name,
        birth_date: r._second || null,
        birth_order: idx + 1,
      };
    });
    base.family_of_origin = {
      father_name: _val('lvIntakeFatherName'),
      father_birth_date: _val('lvIntakeFatherDob') || null,
      mother_name: _val('lvIntakeMotherName'),
      mother_maiden_name: _val('lvIntakeMotherMaiden'),
      mother_birth_date: _val('lvIntakeMotherDob') || null,
      siblings: siblings,
    };

    // Marriage and partners
    var spouseRows = _collectRepeater(
      'lv-intake-spouse-name',
      'lv-intake-spouse-year',
      'lv-intake-spouse-status'
    );
    var spouses = spouseRows.map(function (r) {
      return {
        name: r.name,
        year_married: _intOrNull(r._second),
        status: r._third || null,
      };
    });
    base.marriage = {
      marital_status: _val('lvIntakeMaritalStatus') || null,
      number_of_marriages: _intOrNull(_val('lvIntakeNumMarriages')),
      spouses: spouses,
    };

    // Children
    var childRows = _collectRepeater('lv-intake-child-name', 'lv-intake-child-dob');
    base.children = childRows.map(function (r) {
      return { name: r.name, birth_date: r._second || null };
    });

    // Education + work
    base.education_work = {
      highest_education_level: _val('lvIntakeEduLevel') || null,
      primary_career: _val('lvIntakeCareer') || null,
      years_working: _val('lvIntakeWorkYears') || null,
    };

    // Military
    var milServed = (
      (document.querySelector('input[name="lvIntakeMilServed"]:checked') || {}).value
    ) === 'yes';
    base.military = {
      served: milServed,
      branch: milServed ? (_val('lvIntakeMilBranch') || null) : null,
      service_dates: milServed ? (_val('lvIntakeMilDates') || null) : null,
      rank: milServed ? (_val('lvIntakeMilRank') || null) : null,
      units: milServed ? (_val('lvIntakeMilUnits') || null) : null,
      locations: milServed ? (_val('lvIntakeMilLocations') || null) : null,
      wars_conflicts: milServed ? (_val('lvIntakeMilWars') || null) : null,
      decorations: milServed ? (_val('lvIntakeMilDecor') || null) : null,
      experience_notes: milServed ? (_val('lvIntakeMilNotes') || null) : null,
    };

    // Faith and heritage
    base.faith = {
      religion_raised: _val('lvIntakeFaithRaised') || null,
      current_faith: _val('lvIntakeFaithCurrent') || null,
      ethnicity_heritage: _val('lvIntakeEthnicity') || null,
      languages_at_home: _val('lvIntakeLanguages') || null,
    };

    // Today
    base.today = {
      living_situation: _val('lvIntakeLivingSituation') || null,
      health_considerations: _val('lvIntakeHealthNotes') || null,
    };

    return base;
  }

  function _validate(v) {
    const errors = [];
    if (!v.full_legal_name) errors.push('Full legal name is required.');
    if (!v.preferred_name) errors.push('Preferred name is required.');
    if (!v.date_of_birth) errors.push('Date of birth is required.');
    else if (!_isValidDateString(v.date_of_birth)) errors.push('Date of birth is not a valid date.');
    if (!v.place_of_birth) errors.push('Place of birth is required.');
    if (!v.current_residence) errors.push('Current residence is required.');
    if (!v.pronouns) errors.push('Pronouns are required.');
    if (v.pronouns === 'other' && !v.pronouns_other) {
      errors.push('Please write in the pronoun when "other" is selected.');
    }
    if (!v.consent_recording_agreement) {
      errors.push('Recording-consent checkbox must be ticked.');
    }
    if (!v.consent_disclosure_reviewed) {
      errors.push('Disclosure-reviewed checkbox must be ticked.');
    }
    return errors;
  }

  function _showErrors(errors) {
    const bar = $(ERROR_BAR_ID);
    if (!bar) return;
    if (!errors.length) {
      bar.style.display = 'none';
      bar.innerHTML = '';
      return;
    }
    bar.innerHTML =
      '<strong>Please fix the following before saving:</strong><ul>' +
      errors.map(function (e) { return '<li>' + _escape(e) + '</li>'; }).join('') +
      '</ul>';
    bar.style.display = 'block';
  }

  function _escape(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Submit ───────────────────────────────────────────────────────

  async function lvNarratorIntakeSubmit(opts) {
    const v = _readForm();
    const errors = _validate(v);
    if (errors.length) {
      _showErrors(errors);
      return;
    }
    _showErrors([]);

    // Build the full Phase 2B orchestrator payload — identity + 7
    // optional sections in one shot. Empty sections (e.g. military.served
    // = false, children = []) are still sent so the server applies its
    // own "skip if empty" rules per section.
    const payload = Object.assign({}, v, {
      pronouns_other: v.pronouns === 'other' ? v.pronouns_other : '',
      consent_checked_by_operator: '',
      testing_only: false,
    });

    let pid = null;
    try {
      const resp = await fetch(ENDPOINT_INTAKE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        let detail = 'HTTP ' + resp.status;
        try {
          const j = await resp.json();
          if (j && j.detail) detail = j.detail;
        } catch (_) { /* ignore */ }
        _showErrors(['Save failed: ' + detail]);
        return;
      }
      const data = await resp.json();
      pid = data.person_id || (data.person && data.person.id);
      if (!pid) {
        _showErrors(['Server returned no narrator id. Saved record may be incomplete.']);
        return;
      }
    } catch (e) {
      _showErrors(['Network error: ' + (e.message || e)]);
      return;
    }

    // Defensive: wipe the persisted facial-consent flag so the next
    // Cam click for this brand-new narrator shows the full overlay.
    try {
      if (window.FacialConsent && typeof window.FacialConsent.revokeStored === 'function') {
        window.FacialConsent.revokeStored();
      }
    } catch (_) { /* ignore */ }

    lvCloseNarratorIntake();

    // Refresh the people cache so the new narrator appears in the
    // switcher list immediately.
    try {
      if (typeof refreshPeople === 'function') await refreshPeople();
      if (typeof lv80RenderNarratorCards === 'function') lv80RenderNarratorCards();
    } catch (_) { /* ignore */ }

    if (opts && opts.target === 'bio_builder') {
      // Phase 1 doesn't have a dedicated Bio Builder landing flow yet;
      // make the new narrator active and let the operator navigate to
      // the bio editor section via the Bug Panel surface.
      if (typeof lv80ConfirmNarratorSwitch === 'function') {
        lv80ConfirmNarratorSwitch(pid);
      }
      return;
    }

    // Default: Save and start session
    if (typeof lv80ConfirmNarratorSwitch === 'function') {
      lv80ConfirmNarratorSwitch(pid);
    }
  }

  // ── Skip — testing only ──────────────────────────────────────────
  //
  // The legacy zero-field create path preserved for stress-test
  // narrators (Walter, Jake). Uses prompt() for the name and POSTs
  // with testing_only=true so the consent gate is bypassed
  // server-side.

  async function lvNarratorIntakeSkipTesting() {
    const name = (window.prompt('New test narrator name:') || '').trim();
    if (!name) return;
    try {
      const resp = await fetch(ENDPOINT_PEOPLE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: name,
          role: '',
          narrator_type: 'live',
          testing_only: true,
        }),
      });
      if (!resp.ok) {
        window.alert('Failed to create test narrator: ' + resp.status);
        return;
      }
      const data = await resp.json();
      const pid = data.person_id || (data.person && data.person.id);
      lvCloseNarratorIntake();
      try { if (window.FacialConsent && window.FacialConsent.revokeStored) window.FacialConsent.revokeStored(); } catch (_) {}
      if (typeof refreshPeople === 'function') await refreshPeople();
      if (typeof lv80RenderNarratorCards === 'function') lv80RenderNarratorCards();
      if (pid && typeof lv80ConfirmNarratorSwitch === 'function') {
        lv80ConfirmNarratorSwitch(pid);
      }
    } catch (e) {
      window.alert('Network error creating test narrator: ' + (e.message || e));
    }
  }

  // ── Modal open / close ───────────────────────────────────────────

  function lvOpenNarratorIntake() {
    const modal = $(MODAL_ID);
    if (!modal) {
      // Fall back to the legacy prompt if the modal mount is missing
      console.warn('[narrator-intake] modal not mounted; using skip path');
      lvNarratorIntakeSkipTesting();
      return;
    }
    _resetForm();
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    // Focus the first field for keyboard-driven workflow
    try { ($(F.fullName) || {}).focus(); } catch (_) { /* ignore */ }
  }

  function lvCloseNarratorIntake() {
    const modal = $(MODAL_ID);
    if (!modal) return;
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
  }

  function _resetForm() {
    _showErrors([]);
    const inputs = [
      F.fullName, F.preferredName, F.dob, F.pob,
      F.currentResidence, F.pronounsOther,
      // Phase 2C optional-section inputs
      'lvIntakeFatherName', 'lvIntakeFatherDob',
      'lvIntakeMotherName', 'lvIntakeMotherMaiden', 'lvIntakeMotherDob',
      'lvIntakeMaritalStatus', 'lvIntakeNumMarriages',
      'lvIntakeEduLevel', 'lvIntakeCareer', 'lvIntakeWorkYears',
      'lvIntakeMilBranch', 'lvIntakeMilDates', 'lvIntakeMilRank',
      'lvIntakeMilUnits', 'lvIntakeMilLocations', 'lvIntakeMilWars',
      'lvIntakeMilDecor', 'lvIntakeMilNotes',
      'lvIntakeFaithRaised', 'lvIntakeFaithCurrent',
      'lvIntakeEthnicity', 'lvIntakeLanguages',
      'lvIntakeLivingSituation', 'lvIntakeHealthNotes',
    ];
    inputs.forEach(function (id) {
      const el = $(id);
      if (el) el.value = '';
    });
    // Clear repeater rows (siblings / spouses / children)
    const repeaterClasses = [
      'lv-intake-sibling-name', 'lv-intake-sibling-dob',
      'lv-intake-spouse-name', 'lv-intake-spouse-year', 'lv-intake-spouse-status',
      'lv-intake-child-name', 'lv-intake-child-dob',
    ];
    repeaterClasses.forEach(function (cls) {
      document.querySelectorAll('.' + cls).forEach(function (el) {
        el.value = '';
      });
    });
    document.querySelectorAll('input[name="lvIntakePronouns"]').forEach(function (r) {
      r.checked = false;
    });
    // Military default: No, details collapsed
    document.querySelectorAll('input[name="lvIntakeMilServed"]').forEach(function (r) {
      r.checked = (r.value === 'no');
    });
    const milDetails = $('lvIntakeMilDetails');
    if (milDetails) milDetails.style.display = 'none';
    // Re-collapse all the optional <details> sections so the operator
    // sees the form in its calm starting shape on each open.
    document.querySelectorAll(
      '#lvNarratorIntakeModal details.lv-intake-collapsible'
    ).forEach(function (d) { d.open = false; });
    const r1 = $(F.consentRecording);
    const r2 = $(F.consentDisclosure);
    if (r1) r1.checked = false;
    if (r2) r2.checked = false;
    _updateDobHelper();
  }

  // ── Wire up ──────────────────────────────────────────────────────

  function _wire() {
    const dob = $(F.dob);
    if (dob && !dob._lvIntakeBound) {
      dob.addEventListener('input', _updateDobHelper);
      dob.addEventListener('change', _updateDobHelper);
      dob._lvIntakeBound = true;
    }
    const modal = $(MODAL_ID);
    if (modal && !modal._lvIntakeBound) {
      // Esc to close
      modal.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') lvCloseNarratorIntake();
      });
      // Click on backdrop to close (but not inside the form card)
      modal.addEventListener('click', function (e) {
        if (e.target === modal) lvCloseNarratorIntake();
      });
      modal._lvIntakeBound = true;
    }
  }

  // Public surface
  window.lvOpenNarratorIntake = lvOpenNarratorIntake;
  window.lvCloseNarratorIntake = lvCloseNarratorIntake;
  window.lvNarratorIntakeSubmit = lvNarratorIntakeSubmit;
  window.lvNarratorIntakeSkipTesting = lvNarratorIntakeSkipTesting;

  document.addEventListener('DOMContentLoaded', _wire);
})();
