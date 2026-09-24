/* Questionnaire V2 — the READ model (Batch C-1, 2026-09-23).

   The questionnaire is an EDITOR OF THE LIFE RECORD. It is not another
   biography store. This module turns the canonical record, exactly as
   GET /api/life-record/{narrator_id} returns it (services/life_record/
   store.py `assemble`), into the eleven-topic form state the editor renders.

   IT IS PURE. No fetch, no storage, no DOM, no clock. It cannot write, so
   opening, hydrating, switching topics or switching narrators through it
   cannot write either. Everything it returns is derived from its input and
   carries the record's own ids, so an edit made on the form can be addressed
   back to the exact canonical path it came from (C-3 onward).

   What it will NOT do:
     * guess between competing accounts — two live assertions and no decision
       is `state: "unresolved"`, with both shown;
     * collapse answers — no assertion is `blank`; a stored 0, "no" or
       "unknown" is a VALUE, and stays one;
     * split a name, or pick a display name that hides a record's content —
       every name comes through whole, former names included (this is the
       operator's editor; disclosure rules are Batch D's);
     * copy a captured story's words — a captured story is its candidate id;
     * absorb trips — the trip domain owns them; they arrive as references.

   One person may appear in several topics (a grandmother who raised the
   narrator is family AND caregiver). Every appearance is the SAME person id;
   the view never duplicates a person, it references one. */

(function (root) {
  "use strict";

  var TOPICS = [
    { id: "narrator",       n: 1,  title: "The narrator" },
    { id: "family",         n: 2,  title: "Family and caregivers" },
    { id: "partners",       n: 3,  title: "Partners, unions and children" },
    { id: "wider",          n: 4,  title: "Wider people and animals" },
    { id: "homes",          n: 5,  title: "Homes and places" },
    { id: "learning_work",  n: 6,  title: "Learning and work" },
    { id: "service",        n: 7,  title: "Service and community" },
    { id: "heritage",       n: 8,  title: "Heritage, languages and beliefs" },
    { id: "experiences",    n: 9,  title: "Experiences and interests" },
    { id: "today",          n: 10, title: "Life today" },
    { id: "legacy",         n: 11, title: "Memories, lessons and legacy" },
  ];

  /* ONE vocabulary for epistemic answers, used by every control that asks
     yes/no-shaped questions. Blank is the ABSENCE of an assertion, never a
     stored value. (Chris, 2026-09-23.) */
  var ANSWER = { YES: "yes", NO: "no", UNKNOWN: "unknown", DECLINED: "declined" };

  /* The concept holding each event type's date — mirrors
     store.EVENT_DATE_CONCEPT. Types absent here carry no date yet. */
  var EVENT_DATE_CONCEPT = {
    birth: "person.birth.date", death: "person.death.date",
    union: "event.union.date", move: "event.residence.period",
    service: "event.service.period",
  };

  var TOPIC_OF_EVENT = {
    move: "homes", education: "learning_work", work: "learning_work",
    service: "service", milestone: "experiences", arrival: "experiences",
    loss: "experiences", other: "experiences",
    // union / separation live on the partner card (topic 3);
    // birth / death live on the person card.
  };

  var PERSON_TOPIC_CONCEPTS = {
    family:        [],
    learning_work: ["person.education", "person.occupation"],
    service:       ["person.military_service"],
    heritage:      ["person.heritage", "person.languages",
                    "person.faith.raised", "person.faith.current"],
    experiences:   ["person.interest"],
  };

  var LIVE = function (a) { return a.status !== "rejected" && a.status !== "superseded"; };

  /* ── one answer, from its assertion list ─────────────────────────── */
  function field(node, concept) {
    var list = (node && node[concept]) || [];
    var accepted = node ? node[concept + "AcceptedId"] : undefined;
    return answerOf(concept, list, accepted);
  }

  function answerOf(concept, list, acceptedId) {
    var live = list.filter(LIVE);
    var out = { concept: concept, history: list.slice() };
    if (acceptedId !== undefined && acceptedId !== null) {
      var a = live.filter(function (x) { return x.id === acceptedId; })[0];
      if (a) { out.state = "value"; out.assertionId = a.id; out.value = valueOf(a); out.accepted = true; return out; }
    }
    if (live.length === 0) { out.state = "blank"; return out; }
    if (live.length === 1) {
      out.state = "value"; out.assertionId = live[0].id; out.value = valueOf(live[0]);
      out.accepted = false; return out;
    }
    out.state = "unresolved";
    out.alternatives = live.map(function (x) { return { assertionId: x.id, value: valueOf(x) }; });
    return out;
  }

  /* A many-valued concept (pronouns, languages, heritage, interests): every
     live assertion is an item of its own, addressed by its id. */
  function items(node, concept) {
    return ((node && node[concept]) || []).filter(LIVE).map(function (a) {
      return { assertionId: a.id, value: valueOf(a), assertedBy: a.assertedBy, source: a.source };
    });
  }

  /* A date assertion is flat {text, value, precision}; every other one
     carries `value`. The text is what the person said — never rewritten. */
  function valueOf(a) {
    if (Object.prototype.hasOwnProperty.call(a, "text")) {
      return { text: a.text, value: a.value === undefined ? null : a.value,
               precision: a.precision === undefined ? null : a.precision };
    }
    return a.value;
  }

  function dateField(ev) {
    if (!ev) return null;
    var concept = EVENT_DATE_CONCEPT[ev.type];
    if (!concept) return null;
    return answerOf(concept, ev.dateAssertions || [], ev.acceptedAssertionId);
  }

  /* ── the view ────────────────────────────────────────────────────── */
  function fromRecord(record, opts) {
    opts = opts || {};
    var nid = record.narrator_person_id || record.narrator_id;
    var includeRemoved = !!opts.includeRemoved;
    var visible = function (x) { return includeRemoved || !x.removed; };

    var events = {}, places = {};
    (record.places || []).filter(visible).forEach(function (p) { places[p.id] = p; });
    (record.events || []).filter(visible).forEach(function (e) { events[e.id] = e; });
    var placeLabel = function (id) { return id && places[id] ? places[id].label : null; };

    // people
    var people = {};
    (record.people || []).filter(visible).forEach(function (p) {
      var birth = events[p.birthEventRef], death = events[p.deathEventRef];
      var lsList = p["person.life_status"] || [];
      people[p.id] = {
        id: p.id,
        isNarrator: p.id === nid,
        names: orderNames(p.names || [], p.preferredNameRef),
        preferredNameId: p.preferredNameRef || null,
        pronouns: items(p, "person.pronouns"),
        lifeStatus: answerOf("person.life_status", lsList, p["person.life_statusAcceptedId"]),
        birth: { eventId: birth ? birth.id : null, date: dateField(birth),
                 placeId: birth ? birth.place || null : null,
                 placeLabel: birth ? placeLabel(birth.place) : null,
                 time: field(p, "person.birth.time") },
        death: { eventId: death ? death.id : null, date: dateField(death),
                 placeId: death ? death.place || null : null,
                 placeLabel: death ? placeLabel(death.place) : null,
                 reportedAge: field(p, "person.death.reported_age") },
        birthOrder: field(p, "person.birth.order"),
        occupation: field(p, "person.occupation"),
        education: field(p, "person.education"),
        militaryService: field(p, "person.military_service"),
        reportedCounts: {
          siblings: field(p, "person.reported_count.siblings"),
          children: field(p, "person.reported_count.children"),
          grandchildren: field(p, "person.reported_count.grandchildren"),
        },
        heritage: items(p, "person.heritage"),
        languages: items(p, "person.languages"),
        faithRaised: field(p, "person.faith.raised"),
        faithCurrent: field(p, "person.faith.current"),
        interests: items(p, "person.interest"),
        stories: [],
      };
    });

    // A brand-new narrator has no Life Record yet (revision 0, no people):
    // GET writes nothing, by design, and the writer creates the narrator's
    // own person on the FIRST write. So the narrator must be editable
    // before they exist in the record, or that first write can never be
    // made (C-2 live smoke, 2026-09-24). This is a VIEW of an empty person
    // under the narrator's own id — nothing is stored by building it.
    if (nid && !people[nid]) {
      var none = function (c) { return answerOf(c, [], undefined); };
      people[nid] = {
        id: nid, isNarrator: true, names: [], preferredNameId: null, pronouns: [],
        lifeStatus: none("person.life_status"),
        birth: { eventId: null, date: null, placeId: null, placeLabel: null, time: none("person.birth.time") },
        death: { eventId: null, date: null, placeId: null, placeLabel: null, reportedAge: none("person.death.reported_age") },
        birthOrder: none("person.birth.order"), occupation: none("person.occupation"),
        education: none("person.education"), militaryService: none("person.military_service"),
        reportedCounts: { siblings: none("person.reported_count.siblings"),
                          children: none("person.reported_count.children"),
                          grandchildren: none("person.reported_count.grandchildren") },
        heritage: [], languages: [], faithRaised: none("person.faith.raised"),
        faithCurrent: none("person.faith.current"), interests: [], stories: [],
        notYetInRecord: true,
      };
    }

    // relationships, and each one's meaning relative to the narrator
    var relationships = (record.relationships || []).filter(visible).map(function (r) {
      return {
        id: r.id, subjectPersonId: r.subjectPersonId, otherPersonId: r.otherPersonId,
        kind: r.kind, describedAs: r.describedAs || null, narratorLabel: r.narratorLabel || null,
        qualifiers: r.qualifiers || null, period: r.period || null, basis: r.basis,
        role: roleForNarrator(r, nid),
        detailedRole: detailedRole(r, nid),
        withPersonId: r.subjectPersonId === nid ? r.otherPersonId
                    : r.otherPersonId === nid ? r.subjectPersonId : null,
        lineageSide: answerOf("relationship.qualifier.lineage_side",
                              r["relationship.qualifier.lineage_side"] || [],
                              r["relationship.qualifier.lineage_sideAcceptedId"]),
        // C-3: EXACTLY the writer's view of `relationships/<id>` — the value a
        // `set` must name as expectedPrevious. Built from the record's own
        // keys, never from the display fields above (which fill in nulls).
        raw: rawOf(r, REL_KEYS),
      };
    });

    // stories: captured ones are REFERENCES; the words stay in story_candidates
    var stories = (record.stories || []).filter(visible).map(function (s) {
      var v = { id: s.id, origin: s.origin, kind: s.kind, title: s.title || null,
                when: s.when || null, supersedes: s.supersedes || null,
                peopleRefs: s.peopleRefs || [], placeRefs: s.placeRefs || [],
                eventRefs: s.eventRefs || [], animalRefs: s.animalRefs || [],
                concept: s.concept || null };
      if (s.origin === "captured") v.candidateRef = s.candidateRef;
      else v.body = s.body;
      v.topic = storyTopic(v, events);
      v.peopleRefs.forEach(function (pid) { if (people[pid]) people[pid].stories.push(v.id); });
      return v;
    });

    var animals = (record.animals || []).filter(visible).map(function (a) {
      return { id: a.id, name: a.name || null, species: a.species || null,
               attributes: a.attributes || null,
               birthDate: field(a, "animal.birth.date"),
               breed: field(a, "animal.breed"),
               joinedHousehold: field(a, "animal.joined_household"),
               stories: stories.filter(function (s) { return s.animalRefs.indexOf(a.id) !== -1; })
                               .map(function (s) { return s.id; }) };
    });

    var eventViews = Object.keys(events).map(function (id) {
      var e = events[id];
      return { id: e.id, type: e.type, placeId: e.place || null, placeLabel: placeLabel(e.place),
               attributes: e.attributes || null,
               participants: (e.participants || []).map(function (x) { return { personId: x.person, role: x.role }; }),
               date: dateField(e),
               involvesNarrator: (e.participants || []).some(function (x) { return x.person === nid; }) };
    });

    var byRole = function (roles) {
      return relationships.filter(function (r) { return roles.indexOf(r.role) !== -1; });
    };
    var relatedIds = {};
    relationships.forEach(function (r) { if (r.withPersonId) relatedIds[r.withPersonId] = true; });

    var topics = {};
    TOPICS.forEach(function (t) { topics[t.id] = { id: t.id, n: t.n, title: t.title }; });

    topics.narrator.personId = nid;
    topics.narrator.currentHomes = eventViews.filter(function (e) {
      return e.type === "move" && e.involvesNarrator && e.attributes && e.attributes.current === true;
    }).map(function (e) { return e.id; });

    topics.family.relationships = byRole(["parent", "caregiver", "sibling", "grandparent"]).map(pick);

    topics.partners.relationships = byRole(["partner"]).map(pick);
    topics.partners.unions = eventViews.filter(function (e) {
      return (e.type === "union" || e.type === "separation") && e.involvesNarrator;
    }).map(function (e) { return e.id; });
    topics.partners.children = byRole(["child"]).map(pick);
    topics.partners.grandchildren = byRole(["grandchild"]).map(pick);

    topics.wider.relationships = byRole(["wider", "cared_for"]).map(pick);
    // people in the record with no relationship to the narrator at all
    // (a child's spouse, a friend of a parent): still shown, never lost
    topics.wider.otherPeople = Object.keys(people).filter(function (id) {
      return id !== nid && !relatedIds[id];
    });
    topics.wider.animals = animals.map(function (a) { return a.id; });

    ["homes", "learning_work", "service", "experiences"].forEach(function (t) {
      topics[t].events = eventViews.filter(function (e) { return TOPIC_OF_EVENT[e.type] === t; })
                                   .map(function (e) { return e.id; });
    });
    topics.homes.places = Object.keys(places);

    Object.keys(PERSON_TOPIC_CONCEPTS).forEach(function (t) {
      topics[t].narratorConcepts = PERSON_TOPIC_CONCEPTS[t].slice();
    });
    topics.experiences.trips = (opts.trips || []).map(function (tr) {
      return { tripId: tr.id, label: tr.label || tr.title || null };   // a reference, never a copy
    });

    TOPICS.forEach(function (t) {
      topics[t.id].stories = stories.filter(function (s) { return s.topic === t.id; })
                                    .map(function (s) { return s.id; });
    });

    return {
      narratorId: record.narrator_id,
      narratorPersonId: nid,
      revision: record.revision,
      topicOrder: TOPICS.map(function (t) { return t.id; }),
      topics: topics,
      people: people,
      relationships: index(relationships),
      events: index(eventViews),
      places: index(Object.keys(places).map(function (id) {
        return { id: id, label: places[id].label, parts: places[id].parts || null };
      })),
      animals: index(animals),
      stories: index(stories),
      reportedCounts: record.reportedCounts || {},
    };
  }

  /* Preferred name first, then current names, then everything else — each
     group in record order. Presentation only: every name is kept, whole. */
  function orderNames(names, preferredId) {
    var rank = function (n) { return n.id === preferredId ? 0 : (n.kind || "current") === "current" ? 1 : 2; };
    return names.map(function (n, i) { return { n: n, i: i }; })
      .sort(function (a, b) { return rank(a.n) - rank(b.n) || a.i - b.i; })
      .map(function (x) { return Object.assign({}, x.n); });
  }

  function pick(r) { return r.id; }

  /* C-3 — the writer's own view of an entity path (writer.py _REL_FIELDS /
     _NAME_FIELDS): only the keys the record carries, nulls omitted. */
  var REL_KEYS = ["subjectPersonId", "otherPersonId", "kind", "describedAs", "qualifiers",
                  "narratorLabel", "period", "basis", "derivedFromEventId"];
  var NAME_KEYS = ["fullText", "kind", "givenParts", "family", "birthFamily", "prefixes",
                   "suffixes", "use", "period", "pronunciation", "originStory"];
  function rawOf(x, keys) {
    var o = {};
    keys.forEach(function (k) { if (x[k] !== undefined && x[k] !== null) o[k] = x[k]; });
    return o;
  }
  function rawName(n) { return rawOf(n, NAME_KEYS); }

  /* C-3 — how the editor states a relationship. "subject is <kind> of
     other": `narratorIs` says which end the narrator is. Nothing here is
     preselected; the operator chooses. */
  var ROLES = {
    parent:        { kind: "parent_of",        narratorIs: "other",   label: "Parent",      topic: "family" },
    sibling:       { kind: "sibling_of",       narratorIs: "other",   label: "Sibling",     topic: "family" },
    grandparent:   { kind: "grandparent_of",   narratorIs: "other",   label: "Grandparent", topic: "family" },
    caregiver:     { kind: "caregiver_of",     narratorIs: "other",   label: "Raised or cared for the narrator", topic: "family" },
    spouse:        { kind: "spouse_of",        narratorIs: "other",   label: "Spouse",      topic: "partners" },
    partner:       { kind: "partner_of",       narratorIs: "other",   label: "Partner",     topic: "partners" },
    child:         { kind: "parent_of",        narratorIs: "subject", label: "Child",       topic: "partners" },
    grandchild:    { kind: "grandparent_of",   narratorIs: "subject", label: "Grandchild",  topic: "partners" },
    chosen_family: { kind: "chosen_family_of", narratorIs: "other",   label: "Chosen family", topic: "wider" },
    friend:        { kind: "friend_of",        narratorIs: "other",   label: "Friend",      topic: "wider" },
    mentor:        { kind: "mentor_of",        narratorIs: "other",   label: "Mentor",      topic: "wider" },
    mentee:        { kind: "mentor_of",        narratorIs: "subject", label: "Someone the narrator mentored", topic: "wider", notOffered: true },
    cared_for:     { kind: "caregiver_of",     narratorIs: "subject", label: "Someone the narrator cared for", topic: "wider" },
    other:         { kind: "other",            narratorIs: "other",   label: "Other (describe)", topic: "wider" },
  };
  /* Offered qualifiers. None is preselected; several may apply. Lineage side
     (maternal / paternal) is NOT here: it is its own catalog concept,
     relationship.qualifier.lineage_side, recorded as an assertion. */
  var QUALIFIERS = [
    ["biological", "biological"], ["adoptive", "adoptive"], ["step", "step"], ["foster", "foster"],
    ["half", "half"], ["in_law", "in-law"], ["twin", "twin"], ["older", "older"], ["younger", "younger"],
    ["former", "former"],
  ];

  function detailedRole(r, nid) {
    var subj = r.subjectPersonId === nid, other = r.otherPersonId === nid;
    if (!subj && !other) return "indirect";
    for (var k in ROLES) {
      var d = ROLES[k];
      if (d.kind !== r.kind) continue;
      if (r.kind === "sibling_of" || r.kind === "spouse_of" || r.kind === "partner_of" ||
          r.kind === "friend_of" || r.kind === "chosen_family_of" || r.kind === "other") return k;
      if ((d.narratorIs === "other" && other) || (d.narratorIs === "subject" && subj)) return k;
    }
    return "other";
  }

  /* C-3 — a date as said. The text is kept exactly; a value is filled only
     when the text IS that value (2024-05-01 → day, 2024-05 → month, 1962 →
     year). Anything else — "about 1962", "spring 1970", "before the war" —
     keeps its text with value null and precision "unknown" (the same
     convention identity.py uses at narrator creation). C-4 widens this. */
  function parseDateText(text) {
    var t = String(text == null ? "" : text).trim();
    if (!t) return null;
    if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return { text: t, value: t, precision: "day" };
    if (/^\d{4}-\d{2}$/.test(t)) return { text: t, value: t, precision: "month" };
    if (/^\d{4}$/.test(t)) return { text: t, value: t, precision: "year" };
    return { text: t, value: null, precision: "unknown" };
  }
  function index(list) { var o = {}; list.forEach(function (x) { o[x.id] = x; }); return o; }

  /* What a relationship means FOR THE NARRATOR. One direction is stored
     (rules: no stored inverse), so both directions are read here. */
  function roleForNarrator(r, nid) {
    var subj = r.subjectPersonId === nid, other = r.otherPersonId === nid;
    if (!subj && !other) return "indirect";
    switch (r.kind) {
      case "parent_of":      return other ? "parent" : "child";
      case "child_of":       return subj ? "parent" : "child";
      case "grandparent_of": return other ? "grandparent" : "grandchild";
      case "caregiver_of":   return other ? "caregiver" : "cared_for";
      case "sibling_of":     return "sibling";
      case "spouse_of":
      case "partner_of":     return "partner";
      default:               return "wider";   // chosen family, friend, mentor, other
    }
  }

  /* Where a story is shown. An explicit catalog concept wins when the record
     carries one; otherwise the story's kind and what it is about decide. */
  var CONCEPT_TOPIC = {
    "story.home": "homes", "story.tradition": "heritage", "story.faith": "heritage",
    "story.service": "service", "story.union": "partners", "story.about_animal": "wider",
    "story.life_today.routine": "today", "story.health.reflection": "today",
    "story.lesson": "legacy", "story.message": "legacy", "story.memory": "legacy",
    "story.reflection": "legacy", "story.desired": "legacy", "story.name_origin": "narrator",
    "story.reading": "experiences", "story.about_person": "family",
  };
  function storyTopic(s, events) {
    if (s.concept && CONCEPT_TOPIC[s.concept]) return CONCEPT_TOPIC[s.concept];
    if (s.kind === "tradition") return "heritage";
    if (s.kind === "lesson" || s.kind === "message") return "legacy";
    if (s.placeRefs.length) return "homes";
    for (var i = 0; i < s.eventRefs.length; i++) {
      var e = events[s.eventRefs[i]];
      if (e && TOPIC_OF_EVENT[e.type]) return TOPIC_OF_EVENT[e.type];
    }
    if (s.animalRefs.length) return "wider";
    return "legacy";
  }

  var api = { TOPICS: TOPICS, ANSWER: ANSWER, fromRecord: fromRecord,
              roleForNarrator: roleForNarrator, detailedRole: detailedRole,
              ROLES: ROLES, QUALIFIERS: QUALIFIERS, parseDateText: parseDateText,
              rawName: rawName, answerOf: answerOf };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.LorevoxQuestionnaireV2Model = api;
})(typeof window !== "undefined" ? window : null);
