# HORNELORE HANDOFF

**Updated:** 2026-08-09  
**Repository:** `lorevox-hx/hornelore`  
**Branch:** `main`  
**Purpose:** Give the next agent a truthful starting point when repository code and older planning documents disagree.

**Supersedes:** the 2026-07-31 `WO-TRIP-NARRATOR-BRIDGE-01` handoff, archived unaltered at
[`docs/archive/handoffs/HANDOFF_2026-07-31_TRIP-NARRATOR-BRIDGE.md`](docs/archive/handoffs/HANDOFF_2026-07-31_TRIP-NARRATOR-BRIDGE.md).
It was a single-lane brief, not a project-state document; it is archived rather than
deleted so its trip-narrator-bridge detail stays reachable.

**Companion documentation-control commit, 2026-08-09.** The corrections this handoff calls
for in section 6 are applied: the `MASTER_WORK_ORDER_CHECKLIST.md` header, the Lean Lori R3
status line and its broken canonical pointer, and the current-work pointers in `CLAUDE.md`.
The system-directive work order named in section 5 is written and **not implemented** —
[`docs/wo/WO-SYSTEM-DIRECTIVE-PERSISTENCE-01_Spec.md`](docs/wo/WO-SYSTEM-DIRECTIVE-PERSISTENCE-01_Spec.md).

---

## 1. Read this first: the code is ahead of the management documents

Hornelore has moved faster than several files that still describe what is “active.”

Do **not** restart work simply because an older checklist, WO header, or execution-plan status line says it is still open.

The governing source-of-truth order is:

```text
current code
> current tests and live evidence
> accepted current reports / ADRs / closeout records
> MASTER_WORK_ORDER_CHECKLIST.md
> old WO status lines
> archived design history
```

Before changing product code:

1. Read recent commits on `main`.
2. Read the implementation and tests for the lane you are touching.
3. Check for a later live-acceptance or closeout commit.
4. Then reconcile the checklist/WO text.
5. Never reimplement already-landed work from a stale status line.

This handoff exists because, as of 2026-08-09, **the codebase is in substantially better and newer shape than the documents that are supposed to tell the next agent what is current.**

---

## 2. Current truthful project state

### Google Photos Picker — BANKED / GREEN

The current usable workflow is complete:

```text
Google Picker
→ ingest selected photos
→ hash + stage original bytes
→ import_candidate review row
→ promote from verified staged bytes
→ accept
→ choose an existing trip day
→ create/reuse trip_photo_link
→ photo appears on the day card
```

Important architecture already settled:

- Do not ask the operator to download a Google photo and upload it back into Hornelore.
- Promotion depends on **verified local bytes**, not on a provider-source allowlist.
- `UPLOAD_SOURCES` means only sources whose bytes legitimately arrive by operator upload.
- Picker originals stage under the shared `import_staging` convention.
- Promotion re-hashes staged bytes against `candidate.file_hash`.
- `person_id` and `photos.narrator_id` are the same destination identity expressed in different lanes.
- Google account identity must never infer Hornelore narrator identity.
- Day placement is chosen by the operator at placement time, not inferred silently from EXIF.
- The live Picker workflow has passed end-to-end acceptance.

Do not reopen the Picker lane for polish unless a real defect is demonstrated.

Deferred Picker work remains deferred, including orphan reconciliation before larger-volume imports and future multi-operator Google authentication.

---

## 3. Travel Document — CLOSED ON LIVE EVIDENCE

`WO-TRAVEL-DOC-CLOSEOUT-01` is closed.

The governing product rule is now:

> **The visible trip timeline is the editable source of truth. Export Travel Document produces a Word snapshot of that timeline.**

The previous approval-gated memoir interpretation is retired for this surface.

Current behavior:

- All projected trip days render chronologically.
- The DOCX uses the same timeline projection as the live timeline.
- A second export-side interpretation of a day is forbidden.
- Day `include_in_memoir` is dormant. Migration 0042 remains because it already ran, but runtime code does not use the field to decide export membership.
- Hidden material, rejected placements, and soft-deleted photos stay out.
- Photos assigned to days print under those days.
- Unplaced material prints under **Needs a day**.
- Each photo is embedded once.
- The old Part III photo appendix is retired.
- Conversation export includes narrator + Lori turns.
- Stored `[SYSTEM: ...]` directives are filtered so they are not printed as narrator speech.
- Machine-generated photo text is labeled as machine-written draft text when present.
- `Content-Disposition` is exposed through CORS so the browser can read the real filename.
- Browser download filename handling supports RFC 6266 `filename*=`.

### Live acceptance already passed

The restarted live stack exported the Bismarck trip successfully with:

- 6 chronological days
- 33 timeline items
- 4 photographs embedded exactly once
- 2 photos under their selected days
- 2 under `Needs a day`
- narrator and Lori labels present
- no `[SYSTEM:` directive attributed to Christopher
- no Part III duplication
- no traceback

The observed filename was:

```text
lorevox_trip_memoir_Bismarck Trip.docx
```

The space is expected: the browser used the UTF-8 `filename*=` value carrying the real trip title rather than the ASCII fallback.

Do not reopen Travel Document closeout from older checklist text.

---

## 4. Lean Lori — active technical line, but old headers are stale

Lean Lori has advanced substantially past the header text still present in the R3 WO.

Do not trust a header that says “Phase 0 not started.”

Already landed work includes:

### Phase 0
- Baseline review and measurement completed.
- Prompt overflow measured against real turns.
- Stale-pycache testing hazard documented.
- TTS-aware testing rules documented.

### Prompt restoration / compaction groundwork
- Prompt sections were named without changing rendered output.
- Current narrator text was removed from duplicated `PROFILE_JSON`.
- Chat and extraction token limits were separated.
- Prompt sections were classified as required vs droppable.
- Per-section diagnostic logging was moved out of routine INFO noise.

### Safety
- LLM safety classifier stopped carrying Lori’s full composed prompt.
- The runtime safety feature was explicitly **PARKED** after evidence showed unacceptable false positives and because Lean Lori is not an emergency-monitoring service.
- Parking is server-authoritative.
- Browser safety posture/latch is parked with the backend.
- Safety code, corpus, and tests remain preserved for a future explicit reactivation decision.
- Do not reactivate safety through a stale environment value.

### Phase 4A
The old chat budgeting defect was repaired.

Previously, over-window chat kept the tail of the token stream and silently removed the front — including Lori’s system identity and interview instructions.

Current policy:

```text
preserve system message
preserve current narrator turn
drop oldest completed conversation pairs first
never split a user/assistant pair
refuse if mandatory content alone cannot fit
do not silently slice Lori’s system instructions
```

This is landed work. Do not recreate it from an old prompt-architecture plan.

### Model lock

The current production model remains locked. Do not:

- swap models
- download alternatives
- change quantization
- change device map/offload
- change serving backend
- change chat template
- increase the 8,192-token operating window as a shortcut

Any work that appears to require a model change is a stop-and-report condition.

---

## 5. Known correctness issue that deserves a separate WO

### System directives are still persisted as `role='user'`

This is now the clearest known data-semantics problem.

Several readers defensively filter content beginning with:

```text
[SYSTEM:
```

That protects downstream surfaces, including the Travel Document, but it means the persistence model is still encoding an internal directive as if the narrator said it.

Do **not** solve this by adding a fourth/fifth reader-side filter.

Open a narrow work order that:

1. Finds the canonical write path that persists these directives.
2. Gives internal directives an explicit non-narrator representation.
3. Preserves existing historical rows unless a safe migration is separately approved.
4. Keeps genuine narrator `role='user'` turns unchanged.
5. Proves archives, timelines, exports, extraction, and transcript readers still behave correctly.
6. Adds a non-vacuous regression test at the persistence boundary.

Do not fold this into unrelated Lean Lori or Travel Document work.

---

## 6. Documentation/control-plane corrections needed

These are documentation defects, not reasons to reopen finished product lanes.

### `MASTER_WORK_ORDER_CHECKLIST.md`

The top “Active as of” block is stale. It still presents the 2026-07-29 Picker promotion lane as active and carries old “still owed” language even though later live evidence closed that lane.

Update it so that:

- the current active line reflects the real current work;
- the Picker workflow is listed as banked/closed;
- Travel Document closeout is listed as closed on live evidence;
- old owed items that were subsequently completed are corrected in place or moved to historical context;
- truly deferred items remain clearly marked deferred.

### `CLAUDE.md`

The “6 live WO specs for the next build sessions” list is stale and conflicts with later accepted decisions, especially the parked safety feature and Lean Lori work.

Because `CLAUDE.md` says it must be read first, this stale list is an operational bug.

Update only the current-work pointers; preserve durable doctrine such as:

- universal narrator framing
- no operator leakage
- no system-tone outputs
- no partial resets
- provisional truth persists
- Lori is the conversational interface, Lorevox is the memory system
- mechanical truth must visibly project
- operator-seeded facts are known facts
- Google Picker identity boundary
- local/private archive boundary

### Lean Lori R3 WO header

The R3 file still reports an early status that no longer matches the implementation.

Correct the header/status section to reflect the actual completed phases, but do not rewrite history. Quote/retain retired wording where repository doctrine requires it.

### Broken canonical pointer

The R3 document references `docs/wo/WO-LEAN-LORI-RUNTIME-01_Spec.md`, but that path is not the live canonical file at present.

Correct the pointer to the actual current Lean Lori document or create a deliberate canonical alias only if Chris explicitly chooses that structure.

---

## 7. Testing lessons that are now repository doctrine

Hornelore has repeatedly produced green tests while the real product was wrong. Keep the stronger testing style that recent work established.

### Prefer behavioral/artifact tests over source-shape tests when the defect is behavioral

Examples already learned:

- A route-source scan missed a runtime `NameError`; now the real route is called.
- Server filename tests missed CORS; now tests send an `Origin` header.
- Builder tests missed empty real documents; now tests build and reopen `.docx` artifacts.
- UI source scans missed race behavior; now controlled async ordering is tested.
- Raw substring guards matched comments/prose; AST or behavioral guards are preferred.

### A green sandbox run is evidence, not final verification

Use the real repository venv and, when required, live restarted-stack acceptance.

### Do not use whole-tree unittest discovery as if it were authoritative

The repo has known cross-suite state contamination when everything is forced through one process. Use the documented focused/per-module strategy unless the test architecture itself has been changed deliberately.

### Stale pycache hazard

For sandbox Python runs, use a safe external pycache prefix as documented. `-B` alone does not guarantee stale bytecode will not be read.

---

## 8. Current next-work order

Before broad feature work:

### A. Repair the project control documents
Documentation-only pass:

- `MASTER_WORK_ORDER_CHECKLIST.md`
- current-work portion of `CLAUDE.md`
- Lean Lori R3 status/canonical pointer

No server/UI behavior changes in this commit.

### B. Open the system-directive persistence WO
Treat it as one concern and one boundary fix.

### C. Resume Lean Lori from actual current state
Reconcile remaining R3 phases against landed commits before changing code.

Do not start from an old status line.

### D. Then return to parent-use product priorities
Prefer real narrator/family use over speculative infrastructure polishing.

---

## 9. Deferred — do not accidentally promote to active work

Keep these deferred unless Chris explicitly opens them:

- Picker orphan reconciliation utility
- multi-operator Google authentication
- generalized import destination framework
- three-source chooser
- safety reactivation
- model replacement
- context-window expansion
- broad inference coordinator
- framework rewrite
- mass cleanup of old migrations
- automatic historical rewrite of stored `[SYSTEM:]` rows

Deferred is not forgotten. Deferred means intentionally not active.

---

## 10. Repository operating rules

- Work on `main`.
- No feature branches unless Chris explicitly changes this rule.
- Chris runs git operations from:

```bash
cd /mnt/c/Users/chris/hornelore
```

- Stage explicit file paths only.
- Never use `git add -A` or `git add .`.
- Do not stage generated API-log snapshots containing narrator prose.
- Chris restarts the stack.
- Acceptance scripts do not restart services on their own.
- `.venv` is the test environment.
- `.venv-gpu` is the serving environment.
- Preserve unrelated local work.
- One concern per commit.
- Code and documentation may be separate logical commits when appropriate.
- Do not change the model while repairing prompt/runtime behavior.
- Do not silently turn deferred work into active work.

---

## 11. Fast orientation for the next agent

At session start:

```text
1. Read this HANDOFF.
2. Read CLAUDE.md for durable doctrine, but verify its active-WO list.
3. Read the newest commits on main.
4. Read MASTER_WORK_ORDER_CHECKLIST.md as history + coordination, not as higher authority than current code/live evidence.
5. Read the specific current WO only after checking whether its header/status is stale.
6. Inspect implementation + tests before proposing changes.
7. State what is already done, what is actually open, and what is intentionally deferred.
8. Only then write code.
```

### Current high-level state

```text
Google Picker       GREEN / banked
Travel Document     GREEN / closed on live evidence
Lean Lori           active technical line; advanced through Phase 4A
Safety              PARKED, preserved, not active
System-directive
persistence         known correctness issue; separate WO needed
Docs/checklist      stale and need reconciliation
Model               locked
```

The immediate goal is not to rebuild finished features. It is to make the repository’s control documents accurately describe the system that already exists, then continue from the real code state.
