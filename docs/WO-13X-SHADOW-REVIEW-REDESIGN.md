WO-13X — Shadow Review + Inline Claim Resolution (Pre-WO-14 Execution)
MODE
STRICT IMPERATIVE READ → PLAN → PATCH → TEST → REPORT
OBJECTIVE
Replace candidate-centric review with:

1. Source-centric Shadow Review UI
2. Inline post-chat claim resolution panel
Do NOT change backend truth rules. Do NOT break existing flows.
READ (MANDATORY — NO PATCHING BEFORE THIS)
Read full files:

* `bio-builder.js`
* `bio-builder-core.js`
* `bio-builder-candidates.js`
* `bio-builder-qc-pipeline.js`
* `bio-builder-questionnaire.js`
* `projection-map.js`
* `projection-sync.js`
* `interview.js`
* `app.js`
* `lori9.0.html`
* `bio-review.css`
* `bio-control-center.css`
Identify:

* how sourceCards are stored
* how candidates are rendered
* how approval/promotion works
* where chat → extraction happens
* where UI can hook post-chat
PLAN
You MUST confirm:

1. Current review flow = candidate list + detail
2. SourceCards exist and contain extracted items
3. Candidate → downstream mapping exists (projection or equivalent)
4. Chat extraction trigger location
Define:

* adapter: `sourceCard → grouped claims`
* destination mapping: `candidate → destination label`
* inline hook: post-chat extraction
PATCH
1. CREATE MODULE
Create:

```
shadow-review.js
```

Responsibilities:

*  render source list (left pane) 
*  render source excerpt (center top) 
*  group claims by meaning: 
   *  identity 
   *  people 
   *  events 
   *  places 
   *  memories 
   *  follow-up 
*  cluster duplicates 
*  manage inline resolution state 
*  render right-pane outcomes 
*  commit resolutions 
2. STATE (UI ONLY)
Add:

```
state.shadowReview = {
  activeSourceId: null,
  resolutions: {
    claimId: "approve" | "follow_up" | "source_only" | "reject"
  }
}
```

NO backend schema changes.
3. CENTER PANE REQUIREMENTS
For EACH claim:
Render:

*  claim text 
*  supporting snippet 
*  confidence 
* destination label (REQUIRED) 
*  actions: 
   *  Approve 
   *  Approve + Follow-up 
   *  Source Only 
   *  Reject 
NO modal dependency.
4. DUPLICATE CLUSTERING
Before render:

*  merge overlapping claims 
*  show as one cluster 
*  expandable variants 
5. RIGHT PANE
Live update:

*  Approved (group by destination) 
*  Follow-up 
*  Source Only 
*  Rejected 
6. COMMIT
Button:

```
Commit Resolutions
```

Wire to existing:

*  approve → promotion 
*  source_only → retain only 
*  reject → remove 
*  follow_up → flag or closest equivalent 
7. INLINE POST-CHAT PANEL
Hook into chat flow:
AFTER extraction from user message:
Render inline panel:

```
From this message:
- claim 1
- claim 2
```

Each claim has:

*  Approve 
*  Hold 
*  Source Only 
*  Reject 
Plus:

```
Open in Shadow Review
```

Rules:

*  only show when claims exist 
*  dismissible 
*  must not block chat flow 
8. UI INTEGRATION
Add entry:

*  new tab or replace Candidates → Shadow Review 
Do NOT remove old system unless replaced cleanly.
TEST (MANDATORY)
Run ALL:
T1 — Source-first view

*  source loads 
*  excerpt visible first  PASS/FAIL 
T2 — Grouping

*  claims grouped by meaning  PASS/FAIL 
T3 — Destination visibility

*  every claim shows destination  PASS/FAIL 
T4 — Inline actions

*  all 4 actions present  PASS/FAIL 
T5 — Duplicate clustering

*  duplicates merged  PASS/FAIL 
T6 — Right pane

*  updates live  PASS/FAIL 
T7 — Commit

*  approve → downstream 
*  source_only → not promoted 
*  reject → removed  PASS/FAIL 
T8 — Inline post-chat

*  appears after valid message 
*  actions work 
*  open full review works  PASS/FAIL 
T9 — Regression
Verify:

*  narrator switching 
*  chat loop 
*  no console errors  PASS/FAIL 
T10 — UX JUDGMENT (REQUIRED)
Answer:

*  Is review clearer than candidate cards? 
*  Is destination obvious before approval? 
*  Is it faster? 
REPORT (STRICT FORMAT)

```
WO-13X REPORT

READ
- files inspected
- current flow summary

PLAN
- mapping old → new

PATCH
- files created
- files modified
- key logic added

TEST
T1:
T2:
T3:
T4:
T5:
T6:
T7:
T8:
T9:
T10:

IMPROVEMENTS
- what is clearer
- what is faster

BUGS
- confirmed
- suspected

ADDITIONAL NEEDS
- UI gaps
- follow-on work

REGRESSION
- what broke / didn’t

FINAL
- improvement: YES/NO
- ready for WO-14: YES/NO
```

RULES

*  DO NOT skip READ 
*  DO NOT skip TEST 
*  DO NOT stop at patch 
*  DO NOT hide bugs 
*  DO NOT weaken identity protection 
*  DO NOT break chat 
SUCCESS CRITERIA

*  review is source-first 
*  claims grouped 
*  destination visible before approval 
*  inline actions (no modal dependency) 
*  duplicates clustered 
*  inline post-chat review exists 
*  no regression in core flow 
END WO-13XI read the pasted test log. It’s actually useful because it shows the live UI is getting more stable, while the Shadow/candidate review flow still looks like the part most likely to feel confusing in practice.
Thought for 13s
The pasted log actually helps clarify the problem.
What it shows is that the live UI path is getting healthier, but the approval experience is still shaped like a developer queue instead of a human review workflow.
The good news first: narrator loading, trainer isolation, resume suppression, and rapid switching all look substantially improved in the test log. Kent, Janice, Christopher, Shatner, and Dolly all loaded with the correct identities, and the switch cycle completed without stale data or console errors.
The key clue is later in the log, when the tester tries to do “Chat Extraction → Shadow Archive.” Instead of a clean “say something, then review what was extracted” flow, the interaction detours through the Companion-style input modal, then “Save to My Story,” then a “See New Message” indicator, and only after that does the tester try to inspect shadow notes and proposal rows. That means the capture path itself is already one layer more indirect than it should be before review even starts.
Then look at the current review surface. The review queue is literally described as a drawer with status filters, row list, row-detail modal, and bottom controls like “Bulk dismiss visible” and “Promote approved.” The help text explains the pipeline correctly — Shadow Note → Proposal → Review → Promoted Truth — and the five statuses are well thought out. But that is still system language, not reviewer language.
That is why it feels confusing.
You are being asked to review proposals as rows in a queue, when the thing you actually care about is: “Here is what the narrator said. What parts of it should become structured truth?”
Those are not the same mental model.
The current Bio Review layout reinforces that queue mindset. It is a left-side queue of cards plus a right-side detail pane. The cards are generic candidate cards with title, type, snippet, chips, and confidence. That is okay for browsing, but not ideal for approving archive-derived claims.
So yes, I think there is a better way.
My recommendation is to shift from candidate review to source resolution.
Instead of reviewing one candidate card at a time, the UI should review one Shadow source at a time.
Better approval model
At the top: show the exact Shadow source or transcript excerpt.
Under that: show grouped extracted claims from that source.
For each claim: offer one clear resolution:

* approve as truth
* keep as source only
* approve but mark follow-up needed
* reject
This matches your existing status model exactly, but it presents it in a way a human can understand faster. The current system already supports `approve`, `approve_q`, `source_only`, and `reject`; the problem is mostly the presentation.
What I would change specifically
First, make the source snippet the main object on screen, not the proposal row.
Second, group the extracted claims by meaning:

* identity conflicts
* people
* relationships
* events
* places
* memories
Third, show the destination before approval:

* Family Tree
* Timeline
* Questionnaire
* Memoir context
* source-only, nowhere downstream
Fourth, collapse duplicates into one cluster before the human sees them.
Fifth, separate two jobs that are currently mixed together:

* cleanup of junk/noise/contamination
* truth adjudication
Right now the drawer mixes both, and the “Bulk dismiss visible” control makes that obvious.
The shape I think would work best is:
Shadow Review

* left: source list
* center: source excerpt + extracted claim groups
* right: resolved outcomes / downstream destinations
That would be much clearer than the current “row list plus detail modal” model.
One other thing the log suggests: the review flow should start immediately after a meaningful chat turn. In the log, the tester says something structured and useful: “I grew up in Williston and my dad worked at the oil refinery there. My son Vincent was born in 1990.”
That kind of turn should generate a clean post-turn review block like:
From this message, I found:

* Place: Williston
* Parent employment fact: father worked at oil refinery
* Family claim: son Vincent
* Event/date claim: Vincent born in 1990
Then the user should be able to approve those right there, or send them to Shadow Review. That would feel much more natural than making them hunt through a separate queue.
So my conclusion is:

* the core UI is stabilizing
* the Shadow approval logic is probably fine
* the confusing part is the unit of review
* the better unit is one source and its extracted claims, not one candidate card
That is the redesign I would do next.WO — Shadow Review Redesign (Source-Centric Approval System)
OBJECTIVE
Replace the current candidate-centric review UI with a source-centric “Shadow Review” system that allows the user to:

* Review one Shadow source at a time
* See grouped extracted claims
* Resolve each claim with clear outcomes
* Understand where approved data goes
* Reduce cognitive load and eliminate ambiguity
This is a UI + interaction redesign only. No changes to truth rules, backend schema, or promotion pipeline.
CURRENT PROBLEM
The current system:

* Treats extracted data as independent candidate cards
* Forces user to interpret:
   * source → extraction → type → destination → action
* Mixes:
   * truth adjudication
   * bulk cleanup
* Hides downstream effects of approval
Result:

* Confusing mental model
* Slower review
* Increased risk of incorrect approvals
TARGET MODEL
Core Shift
From:

```
Candidate Card → Review → Approve
```

To:

```
Shadow Source → Extracted Claims → Resolve Each Claim
```

Unit of Review
One Shadow source (transcript snippet or note)  → contains  Grouped claims  → each resolved independently
UI LAYOUT (REQUIRED)
New Surface: “Shadow Review”
Three-pane layout:

```
[ LEFT ]        [ CENTER ]                    [ RIGHT ]
Sources         Source + Claims               Resolved Outcomes
```

LEFT PANE — SOURCE LIST
Each row:

*  Timestamp 
*  Short excerpt (first 80 chars) 
*  Claim count 
*  Status badge: 
   *  Unreviewed 
   *  Partial 
   *  Resolved 
*  Contamination flag (if applicable) 
Click → loads source into center pane
CENTER PANE — SOURCE + CLAIMS (PRIMARY WORK AREA)
Section 1 — SOURCE (TOP)
Display:

*  Full transcript excerpt (read-only) 
*  Speaker label 
*  Timestamp 
Section 2 — EXTRACTED CLAIM GROUPS
Group by meaning (NOT type enum order):

1. Identity (protected) 
2. People / Relationships 
3. Events 
4. Places 
5. Memories / Narrative 
6. Needs Follow-Up 
Each group:

*  Collapsible 
*  Shows count 
CLAIM ROW STRUCTURE
Each claim row MUST show:

*  Extracted claim (clean text) 
*  Supporting snippet (highlighted in source) 
*  Confidence (small badge) 
* Destination preview (REQUIRED): 
   *  e.g. “→ Family Tree” 
   *  “→ Timeline” 
   *  “→ Questionnaire” 
   *  “→ Memoir Context Only” 
   *  “→ Source Only” 
CLAIM ACTIONS (INLINE, REQUIRED)
Each claim must have EXACTLY these options:

* Approve 
* Approve + Follow-up 
* Keep Source Only 
* Reject 
No modal required. Inline buttons only.
DUPLICATE CLUSTERING (REQUIRED)
If multiple candidates represent same meaning:

*  Show as ONE cluster 
*  Expand to show variants 
*  Approve applies to cluster 
RIGHT PANE — RESOLVED OUTCOMES
Live-updating list:

*  Approved → grouped by destination 
*  Source-only 
*  Follow-up required 
*  Rejected (collapsed) 
Purpose:

*  Show immediate effect of decisions 
*  Reduce uncertainty 
INTERACTION MODEL
FLOW

1.  User selects source 
2.  System displays extracted claims grouped 
3.  User resolves each claim inline 
4.  Right pane updates live 
5.  User clicks: 
   * “Commit Resolutions” 
COMMIT ACTION (REQUIRED)
On commit:

*  Approved → existing promotion pipeline 
*  Source-only → saved as Shadow only 
*  Follow-up → flagged for Lori question generation 
*  Reject → discarded 
NO change to backend logic
STRICT RULES (MUST FOLLOW)

*  DO NOT change: 
   *  extraction pipeline 
   *  candidate schema 
   *  promotion logic 
*  DO NOT remove existing candidate system 
   *  This is a new UI layer over it 
*  DO NOT allow approval without showing destination 
*  DO NOT show raw JSON to user 
FILE TARGETS
Claude MUST read before patching:

* `bio-builder-candidates.js` 
* `bio-builder.js` 
* `bio-builder-qc-pipeline.js` 
* `bio-review.js` (if present) 
* `lori9.0.html` 
*  relevant CSS: 
   * `bio-review.css` 
   * `bio-control-center.css` 
IMPLEMENTATION PLAN
STEP 1 — READ & MAP

*  Identify: 
   *  current candidate rendering 
   *  sourceCards structure 
   *  candidate grouping logic 
   *  review actions 
STEP 2 — BUILD SHADOW REVIEW COMPONENT
Create new module:

```
shadow-review.js
```

Responsibilities:

*  render source list 
*  render claim groups 
*  manage resolution state 
*  handle commit 
STEP 3 — DATA ADAPTER LAYER
Map existing data:

```
sourceCard → claim groups
candidate → claim row
```

No schema changes.
STEP 4 — INLINE RESOLUTION STATE
Add temporary UI state:

```
state.shadowReview = {
  activeSourceId,
  resolutions: {
    claimId: "approve" | "follow_up" | "source_only" | "reject"
  }
}
```

STEP 5 — DESTINATION MAPPING
Use existing projection / candidate type logic to derive:

```
candidate → destination label
```

STEP 6 — COMMIT HOOK
Wire to existing:

*  candidate promotion 
*  source-only persistence 
*  follow-up flagging 
STEP 7 — UI INTEGRATION
Add entry point:

*  Replace or supplement:  “Candidates” tab → “Shadow Review” 
ACCEPTANCE TESTS
TEST 1 — SOURCE-FIRST VIEW

*  Select source 
*  Source text appears at top 
*  PASS if visible before claims 
TEST 2 — GROUPED CLAIMS

*  Claims grouped correctly 
*  PASS if no flat list 
TEST 3 — DESTINATION VISIBILITY

*  Every claim shows destination 
*  PASS if none missing 
TEST 4 — INLINE ACTIONS

*  All 4 actions present per claim 
*  PASS if no modal required 
TEST 5 — DUPLICATE CLUSTER

*  Duplicate claims grouped 
*  PASS if merged 
TEST 6 — RIGHT PANE UPDATE

*  Resolve claim → right pane updates instantly 
*  PASS if real-time 
TEST 7 — COMMIT

*  Approve → appears in downstream system 
*  Source-only → not promoted 
*  Reject → removed 
*  PASS if all correct 
TEST 8 — NO BREAKAGE

*  Existing Bio Builder still works 
*  PASS if no regression 
REPORT FORMAT (REQUIRED)
Claude must output:

```
WO — Shadow Review Redesign REPORT

READ:
- Files inspected
- Key structures identified

PLAN:
- Mapping of old → new UI

PATCH:
- Files created
- Files modified

TEST:
- Test 1–8 results (PASS/FAIL)

RESULT:
- Summary of behavior change

NOTES:
- Any limitations or follow-ups
```

SUCCESS CRITERIA

*  User reviews sources, not candidates 
*  Each decision is clear and fast 
*  Destination is visible before approval 
*  Cognitive load is reduced significantly 
*  System behavior remains unchanged underneath Shadow Review Redesign + Inline Claim Resolution + UI Audit
OBJECTIVE
Redesign approval of extracted data from Shadow Archive so it is:
   * source-centric instead of candidate-centric
   * easier to understand
   * faster to review correctly
   * clearer about what approval does
   * instrumented for UI evaluation
This work order includes:
   1. Shadow Review Redesign
   2. Inline Post-Chat Claim Resolution
   3. Structured UI testing plan
   4. Required Claude audit/report output for improvements, bugs, and additional needs
Do all four in one pass unless blocked by code reality.
PART A — SHADOW REVIEW REDESIGN
PROBLEM
The current approval flow is confusing because it makes the user review extracted data as generic candidate rows/cards instead of resolving claims from a specific source.
This creates unnecessary cognitive work:
   * what did the narrator say
   * what did the extractor pull out
   * what kind of item is it
   * where will it go
   * should I approve it
The UI is doing queue review, but the user needs source resolution.
TARGET MODEL
Change the mental model from:

```
Candidate Card → Review → Approve
```

to:

```
Source Excerpt → Proposed Claims → Resolve Each Claim
```

The unit of review must become:
   *  one Shadow source / transcript excerpt 
   *  with grouped extracted claims beneath it 
REQUIRED UI SURFACE
Create or refactor into a new primary review surface called:

```
Shadow Review
```

LAYOUT
Use a 3-pane layout:

```
[ LEFT ]        [ CENTER ]                     [ RIGHT ]
Sources         Source + Proposed Claims       Resolved Outcomes
```

LEFT PANE — SOURCE LIST
Each row must show:
   *  timestamp 
   *  speaker label if available 
   *  short excerpt preview 
   *  extracted-claim count 
   *  status badge: 
      *  Unreviewed 
      *  Partial 
      *  Resolved 
   *  contamination/noise warning if applicable 
Behavior:
   *  clicking a source loads it into the center pane 
   *  selected source is visually obvious 
   *  list supports keyboard and mouse selection 
CENTER PANE — MAIN REVIEW AREA
SECTION 1 — SOURCE BLOCK
At top, prominently show:
   *  full excerpt or source text 
   *  timestamp 
   *  narrator/speaker label 
   *  source type if available 
This must visually read as:  “This is what the narrator actually said.”
SECTION 2 — CLAIM GROUPS
Group extracted claims by meaning, not raw type order.
Required groups:
   1. Protected Identity 
   2. People / Relationships 
   3. Events 
   4. Places 
   5. Memories / Narrative 
   6. Needs Follow-Up 
Requirements:
   *  each group is collapsible 
   *  group header shows count 
   *  empty groups are hidden 
CLAIM ROW CONTENT
Each claim row must show:
   *  normalized claim text 
   *  supporting snippet / evidence fragment 
   *  confidence badge 
   *  duplicate indicator if clustered 
   *  destination preview 
DESTINATION PREVIEW IS REQUIRED
Each claim must show where approval sends it, such as:
   *  → Questionnaire 
   *  → Family Tree 
   *  → Timeline 
   *  → Life Map 
   *  → Memoir Context Only 
   *  → Source Only 
No claim may be approvable without destination visibility.
INLINE ACTIONS
Each claim must have these four actions inline:
   * Approve 
   * Approve + Follow-up 
   * Keep Source Only 
   * Reject 
Rules:
   *  no modal required for normal use 
   *  action state must be immediately visible 
   *  user can change a decision before commit 
DUPLICATE CLUSTERING
If multiple extracted rows mean the same thing:
   *  cluster into one review block 
   *  allow expand/collapse to inspect variants 
   *  approving cluster resolves all linked duplicates correctly 
RIGHT PANE — RESOLVED OUTCOMES
Live-updating summary grouped into:
   *  Approved 
   *  Follow-up 
   *  Source Only 
   *  Rejected 
Approved items should also be grouped by destination.
Purpose:
   *  make the effect of decisions obvious 
   *  reduce uncertainty before commit 
   *  act as a live “review cart” 
COMMIT ACTION
Provide a single commit action:

```
Commit Resolutions
```

On commit:
   *  Approved → existing promotion path 
   *  Approve + Follow-up → promotion/flag path already supported or nearest equivalent 
   *  Source Only → retained without downstream promotion 
   *  Reject → dismissed from review queue 
Do not redesign backend truth rules unless necessary for compatibility.
STRICT CONSTRAINTS
Do not:
   *  change truth architecture 
   *  weaken protected identity safeguards 
   *  bypass review 
   *  expose raw system JSON to end users 
   *  destroy the current candidate pipeline unless replacement is fully wired 
Prefer:
   *  adapter layer 
   *  new UI composition 
   *  reuse of existing review/promotion actions 
FILES TO READ FIRST
Claude must read before patching:
   * `bio-builder.js` 
   * `bio-builder-core.js` 
   * `bio-builder-candidates.js` 
   * `bio-builder-qc-pipeline.js` 
   * `bio-builder-questionnaire.js` 
   * `projection-map.js` 
   * `projection-sync.js` 
   * `lori9.0.html` or active shell equivalent 
   * `bio-review.css` 
   * `bio-control-center.css` 
Also inspect any existing review module if present.
IMPLEMENTATION TARGET
Preferred new module:
   * `shadow-review.js` 
Allowed alternatives:
   *  refactor current review module if cleaner and less risky 
Responsibilities:
   *  source list rendering 
   *  source → grouped claim adapter 
   *  inline resolution state 
   *  destination labeling 
   *  duplicate clustering 
   *  commit wiring 
PART B — INLINE POST-CHAT CLAIM RESOLUTION
OBJECTIVE
After a meaningful user turn, give the operator a small, immediate, optional review layer without requiring a full jump into Shadow Review.
This should make approval faster and more natural.
TARGET BEHAVIOR
After a user message generates extractable claims, show a compact inline panel in the chat flow:

```
From this message, I found:
- Place: Williston
- Relationship: father
- Work fact: father worked at oil refinery
- Family claim: son Vincent
- Date claim: born in 1990
```

Each claim gets quick actions:
   *  Approve 
   *  Hold for Review 
   *  Source Only 
   *  Reject 
And one utility action:
   * Open in Shadow Review 
RULES
   *  this is not a replacement for full review 
   *  this is a convenience surface 
   *  it must respect protected identity rules 
   *  unresolved or complex claims should route cleanly to Shadow Review 
   *  do not make chat feel cluttered 
INLINE PANEL REQUIREMENTS
The panel must:
   *  appear only when claims exist 
   *  appear below the relevant user turn or nearby in a clear review zone 
   *  be dismissible 
   *  support batched quick approval 
   *  include “Open in Shadow Review” for full context 
WHEN TO USE INLINE REVIEW
Use inline review only for:
   *  clear, compact extractions 
   *  obvious people/places/events/facts 
   *  low ambiguity items 
Send to full Shadow Review when:
   *  multiple related claims 
   *  conflicting identity 
   *  duplicate collision 
   *  unclear relationship 
   *  high ambiguity 
   *  long transcript-derived cluster 
FILES TO TOUCH
Likely:
   *  active chat/interview rendering JS 
   *  extraction result handling JS 
   *  any Shadow note generation hook 
   *  active HTML shell 
   *  CSS for inline review panel 
Claude must determine the correct files after reading.
PART C — UI TESTING PLAN
OBJECTIVE
Claude must test not only whether the new UI works, but whether it is actually better.
Testing must document:
   *  improvements 
   *  bugs 
   *  confusing interactions 
   *  incomplete behaviors 
   *  additional UI needs 
TEST STRATEGY
Testing must be divided into five sections:
1. Structural UI tests
Verify:
   *  Shadow Review renders 
   *  all three panes render 
   *  source selection works 
   *  claim grouping works 
   *  right-pane live summary works 
   *  inline post-chat review panel appears when expected 
2. Interaction tests
Verify:
   *  every action button works 
   *  changing decisions before commit works 
   *  duplicate clusters open/close correctly 
   *  “Open in Shadow Review” from inline panel works 
   *  commit performs correct downstream behavior 
3. Truth-path tests
Verify:
   *  Approve sends to expected destination 
   *  Source Only does not promote 
   *  Reject does not leak downstream 
   *  Protected identity remains guarded 
   *  Follow-up state is preserved or routed appropriately 
4. Regression tests
Verify no breakage to:
   *  narrator switching 
   *  normal chat 
   *  Focus Canvas if active 
   *  Bio Builder navigation 
   *  existing review queue logic 
   *  Timeline / Family Tree / Questionnaire integrations 
5. UX quality tests
Claude must explicitly assess:
   *  Is the unit of review now clearer 
   *  Is the destination clearer before approval 
   *  Is the flow faster with fewer clicks 
   *  Is the interface less confusing than candidate cards 
   *  Does inline review feel helpful or intrusive 
   *  What still feels awkward or overloaded 
REQUIRED TEST SCENARIOS
SCENARIO 1 — Single clean source
Input with one obvious place and one obvious relationship.  Expected:
   *  grouped correctly 
   *  easy approval 
   *  correct destination labels 
SCENARIO 2 — Multi-claim source
Input with people, event, place, and memory fragment.  Expected:
   *  grouped by meaning 
   *  no flat undifferentiated list 
SCENARIO 3 — Protected identity conflict
Input proposing a conflicting DOB or birthplace.  Expected:
   *  visually separated 
   *  not silently approvable as normal fact 
   *  routed safely 
SCENARIO 4 — Duplicate cluster
Input produces overlapping claims.  Expected:
   *  clustered 
   *  not shown as noisy repetition 
SCENARIO 5 — Inline quick approval
Send a simple chat turn with extractable facts.  Expected:
   *  inline panel appears 
   *  quick approval works 
   *  full review link works 
SCENARIO 6 — Source only path
Mark a claim as Source Only.  Expected:
   *  remains archived 
   *  does not enter downstream truth surfaces 
SCENARIO 7 — Reject path
Reject claim.  Expected:
   *  removed from active review outcome 
   *  no downstream leakage 
SCENARIO 8 — Regression
Do normal narrator/chat workflow after new UI is added.  Expected:
   *  no breakage 
   *  no console errors 
   *  no stuck state 
SCENARIO 9 — Stress test
Rapidly review multiple sources in sequence.  Expected:
   *  no stale selection state 
   *  no cross-source bleed 
   *  right-pane state updates correctly 
SCENARIO 10 — UX judgment
Claude must state whether the redesign actually feels better and why.
PART D — CLAUDE REQUIRED REPORTING
Claude must not stop at “patch applied.”
Claude must produce a full report in this exact structure:
REPORT — Shadow Review + Inline Claim Resolution + UI Audit
READ

* files inspected
* relevant existing architecture found
* current review flow summary
* current chat-to-shadow flow summary
PLAN

* old review model
* new review model
* mapping of existing data to new UI
* risk areas before patching
PATCH

* files created
* files modified
* key behavioral changes
* adapter logic added
* CSS/layout changes added
TEST
For each required scenario:

* PASS / FAIL
* what was tested
* actual observed behavior
* any console/API errors
* screenshots or logs if available
IMPROVEMENTS OBSERVED
Claude must explicitly list:

* what is clearer now
* what takes fewer clicks now
* what confusion was removed
* what became more obvious for the human reviewer
BUGS FOUND
Claude must explicitly list:

* confirmed bugs
* suspected bugs
* intermittent UI issues
* state sync issues
* visual/layout issues
* performance issues
ADDITIONAL UI NEEDS
Claude must explicitly list:

* improvements still needed
* places where the UI still feels too dense
* actions that still need simplification
* follow-on work orders recommended
REGRESSION STATUS

* what remained working
* what broke
* what needs follow-up verification
FINAL JUDGMENT
Claude must answer plainly:

* Did the redesign materially improve review clarity: Yes/No
* Did the inline review improve speed without adding clutter: Yes/No
* Is the UI ready for further live testing: Yes/No
EXECUTION INSTRUCTIONS TO CLAUDE
Use this execution structure:

```
READ
PLAN
PATCH
TEST
REPORT
```

Detailed rules:

1. READ FIRST  Read all relevant files before editing anything. 
2. DO NOT GUESS  Inspect actual rendering paths, state objects, and action handlers. 
3. PATCH MINIMALLY BUT COMPLETELY  Prefer adapter-driven refactor over backend rewrite. 
4. TEST AFTER PATCH  Run UI-level verification, not just static code edits. 
5. DOCUMENT HONESTLY  If something is incomplete or broken, say so directly. 
6. DO NOT STOP AT GREEN PATHS  Also document confusing edge cases, awkward flows, and next UI needs. 
ACCEPTANCE CRITERIA
This work order is complete only if all of the following are true:

*  review is source-first, not card-first 
*  claims are grouped by meaning 
*  every claim shows destination before approval 
*  inline actions are available without modal dependence 
*  duplicate claims are clustered 
*  resolved outcomes are visible before commit 
*  post-chat inline claim review exists 
*  full testing was performed 
*  Claude documents improvements, bugs, and additional UI needs 
*  no major regression is introduced into core narrator/chat flow Shadow Review Redesign + Inline Claim Resolution + UI AuditREAD these files first and understand the current review and chat-to-shadow flow before editing:- bio-builder.js- bio-builder-core.js- bio-builder-candidates.js- bio-builder-qc-pipeline.js- bio-builder-questionnaire.js- projection-map.js- projection-sync.js- lori9.0.html or active shell equivalent- bio-review.css- bio-control-center.css- any existing review UI moduleOBJECTIVERedesign the approval flow for Shadow Archive so the unit of review is a source excerpt with grouped proposed claims, not generic candidate cards. Also add a compact inline post-chat claim resolution panel for fast approval after simple extractable user messages. Then test the result and document improvements, bugs, and additional UI needs.REQUIREDPART A — SHADOW REVIEWCreate or refactor a source-centric Shadow Review UI with 3 panes:- left: source list- center: source excerpt + grouped claims- right: resolved outcomesEach source row must show:- timestamp- excerpt preview- claim count- status- contamination warning if applicableCenter pane must show:- source excerpt prominently first- grouped claims under headings: 1. Protected Identity 2. People / Relationships 3. Events 4. Places 5. Memories / Narrative 6. Needs Follow-UpEach claim row must show:- normalized claim text- supporting snippet- confidence- destination preview- inline actions: - Approve - Approve + Follow-up - Keep Source Only - RejectDuplicate or overlapping claims must be clustered into one review unit.Right pane must live-update with:- Approved- Follow-up- Source Only- RejectedProvide a single commit action:- Commit ResolutionsReuse the existing truth pipeline wherever possible. Do not weaken protected identity rules or bypass review.PART B — INLINE POST-CHAT CLAIM RESOLUTIONAfter a simple extractable user turn, show a compact inline panel near the relevant chat turn:- list of extracted claims- actions: - Approve - Hold for Review - Source Only - Reject - Open in Shadow ReviewThis must be optional, dismissible, and only appear when meaningful claims exist. It must not clutter the main conversation flow.PART C — TESTINGTest all of the following:1. Single clean source2. Multi-claim source3. Protected identity conflict4. Duplicate cluster5. Inline quick approval6. Source only path7. Reject path8. Regression of narrator/chat flow9. Stress test with multiple sources10. UX judgment on whether it is truly clearerFor each scenario, provide PASS/FAIL and observed behavior.PART D — REPORTReturn a full report with exactly these sections:WO-14 REPORT — Shadow Review + Inline Claim Resolution + UI AuditREADPLANPATCHTESTIMPROVEMENTS OBSERVEDBUGS FOUNDADDITIONAL UI NEEDSREGRESSION STATUSFINAL JUDGMENTBe explicit about:- what improved- what still feels confusing- what bugs remain- what further UI work is neededDo not stop at “patch applied.” Read, patch, test, and report.  does this all makes sense it is pre wo14 and working on the laptop tomorrow