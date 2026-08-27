# Hornelore

**Updated: 2026-08-17.** Current state lives in `HANDOFF.md`; this file describes what the
system *is*. When the two disagree, `HANDOFF.md` wins.

> **This README was rewritten on 2026-08-17.** The previous one had grown to 1,146 lines and
> was simultaneously a changelog, a status report, an architecture description, a setup guide
> and a product statement — and it contradicted itself: Coqui *and* Kokoro each named as the
> current TTS, narrators described as uncreatable in a document that also documented creating
> them, and status tables asserted as accurate whose newest entry was three weeks old.
> **It is not kept in the tree.** `git log -- README.md` is the archive; a verbatim current-tree
> copy would recreate both problems it was replaced for — the family identity data it carried,
> and a stale instruction sitting where someone can read it as current.

---

## 1. What this is

**Lorevox** is a privacy-first conversational memory system. It helps older adults preserve
their life stories, supports cognitive engagement, and produces structured legacy outputs for
their families. **Lori** is its conversational interface.

**Hornelore is the family R&D deployment of Lorevox** — the tenant-zero instance whose real
sessions harden the system. It shares architecture and code lineage with the public product
and has a different operating role: Hornelore is where behaviour is proven against a real
family before it graduates.

These are **not two labels for one thing**, and they are not a fork. Hornelore is the crucible;
Lorevox is what is distilled out of it.

### The north star

**The narrator is the author of their own story.** Not an interview subject, not a data
source, not a knowledge graph to populate. The system exists to help them tell it. When a
decision trades operational tidiness against narrator dignity, **narrator dignity wins** — and
that outranks any single work order.

### Framing

The design draws on occupational-therapy life review with older adults: recall supported
rather than tested, silence protected rather than filled, and the narrator's own vocabulary
preserved rather than normalised.

---

## 2. Durable principles

These are checked against every UI element, every data write, and every acceptance criterion.
The full statements live in [`CLAUDE.md`](CLAUDE.md).

1. **No dual metaphors.** **Life Map is the only navigation surface** by doctrine, and the
   river/Kawa metaphor is retired as system, UI and logic.
   **The code has not caught up, and the honest statement is not "retired".** As of 2026-08-17
   `ui/hornelore1.0.html` still renders the `#lv80RiverBtn` "🌊 Memory River" button, still
   defines the `#kawaRiverPopover` it targets, still offers `chronology_river` as a memoir
   mode, and still loads `js/lori-kawa.js`. `chronology_river` is also live in `ui/js/app.js`
   and `ui/js/state.js`.
   **Memory River / Kawa therefore contradicts current doctrine and remains mounted and
   reachable legacy UI. It is FROZEN and awaiting adjudication — do not extend it, and do not
   build anything on it.** *(An earlier revision of this file called it "not a live surface".
   That was wrong: the check had been made against `ui/js/` only, and never against the shell
   HTML that mounts it.)*
2. **No operator leakage.** Anything a narrator can see is designed for narrators. No
   diagnostic surfaces, no operator-only controls in the narrator flow.
3. **No system-tone outputs.** Narrator-facing text sounds like a person, not a query result.
   Source attribution is operator-side.
4. **No partial resets.** Reset Identity clears all narrator-scoped state atomically.
5. **Provisional truth persists; final truth waits for the operator; the interview never
   waits.** Extraction candidates become provisional truth immediately, with full provenance.
   Operator review is asynchronous and operator-side. Inline review widgets that interrupt an
   interview are retired.
6. **Lorevox is the memory system; Lori is the interface to it.** Memory, chronology and
   structure belong to the database and to server-owned projections — not in Lori's head.
7. **Mechanical truth must visibly project.** A value that exists in canonical or provisional
   truth must reach every surface that consumes it. Hidden state and "Lori remembers"
   pattern-completion are forbidden.
8. **The operator seeds known structure; Lori reflects what is there.** If the operator seeded
   it, Lori knows it — and does not ask for it as intake.

---

## 3. Current capabilities

| Area | State |
|---|---|
| Narrator intake | **Arbitrary narrators.** `POST /api/people/intake` with a real frontend flow (`lv80NewPerson()`, `ui/js/narrator-intake.js`). Not a fixed roster. |
| Narrator deletion | Soft delete with an undo window, hard delete, dependency inventory, restore, and an append-only audit trail. The tenant-zero UI may guard family narrators. |
| Interview default | **`oral_history`** — the narrator tells chapters; Lori listens and follows. Structured styles are operator-selectable overrides. `memory_exercise` is **removed from the picker**; legacy values redirect to `warm_storytelling`. Questionnaire-first's live path is **retired/redirected**; five style names remain accepted for compatibility and testing. |
| Life Map | The narrator's primary navigation surface: six historical eras **plus** the separate `today` current-life bucket. **Travels is a special shelf, not an era.** |
| Chronology | `GET /api/chronology-accordion` is the server projection of record *(extended in Phase 1, accepted 2026-08-17)*: world events, personal anchors, ghost cues, derived spine items, trip **days**, confirmed timeline events and story evidence with status. Each lane reports its own provenance and whether it could be read at all, so an outage is distinguishable from a narrator with nothing in that lane. |
| Travel Document | **Complete and accepted.** Operator workspace: editable itinerary, evidence review, multi-day photo placement, Photo Palette, DOCX export. Phase 2 connects it to the canonical chronology — the detailed day model stays the write authority and the projection stays the read authority; they are reconciled, never merged. |
| Story capture | Narrator turns that meet trigger criteria are preserved as `story_candidates` with provenance; operator review promotes them. |
| Runtime safety | **PARKED since 2026-08-04.** Code, corpus and tests are preserved. It is **not** active and must not be described as active. Reactivation takes an explicit decision, never an environment value. |
| Model + context window | **LOCKED.** A change request here is a stop-and-report condition. |

---

## 4. Architecture

```text
narrator speech / typing
        ↓
   STT (browser or local)
        ↓
   chat_ws  →  prompt composition  →  local LLM  →  response guards  →  TTS
        ↓                                                    ↓
   turns + sessions                                    narrator sees text
        ↓
   extraction → provisional truth → operator review → confirmed truth
        ↓
   server projections (profile, chronology, memoir) → Life Map, Lori, Travel Document
```

**Local-first is a rule, not a default.** STT, the LLM, facial/acoustic affect and TTS all run
on the narrator's own machine.

### Travel Doc Evidence + Web Context Rule

*(Restored 2026-08-17. The README rewrite earlier that day dropped this named rule while
keeping a paraphrase of it. The rule is permanent doctrine — it is stated in full in
`CLAUDE.md` — and `tests/test_travel_doc_doctrine.py` asserts it in both documents, so the
rewrite left that suite failing at HEAD. Reinstated rather than the test relaxed: the test
was right.)*

Travel Doc mode is the **operator** memoir-building workspace, not Narrator Room. Narrator
Room stays cautious. Travel Doc is evidence-rich: EXIF and filename dates, GPS with
reverse-geocoded broad place, OCR, draft image observations, captions, operator notes, trip
route hierarchy and public context, all carrying provenance wording.

**The rule is not "no web."** The local Hornelore LLM/API **may use web and public-context
tools in Travel Doc mode** — holidays, local events, museum and site background, food and
neighbourhood context, reverse geocoding. The boundary is that Hornelore must never
**outsource private narrator memory** archives, life-story profiles or raw memoir transcripts
to an uncontrolled cloud LLM as the reasoning engine. Local web-enabled evidence enrichment is
allowed; cloud life-story outsourcing is not. Web-derived context is labelled public context
or draft evidence until an operator or narrator confirms it, and public context is never
presented as personal memory.

**Services:** API on `:8000`, TTS on `:8001`, static UI on `:8082`. **TTS is Kokoro**
(Apache 2.0, English + Spanish); the Coqui adapter is retained only as a legacy option behind
`LORI_TTS_ENGINE`.

**Multilingual:** English and Spanish, including mid-conversation code-switching — language
detection, perspective and fragment guards, correction parsing, and Spanish deterministic
composers.

---

## 5. Development state

**`WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` is ACCEPTED AND COMPLETE (2026-08-20).**
The pipeline a narrator actually experiences now runs end to end: Lori asks a natural question,
the answer is preserved, the captured story is bound to both committed turn rows, extraction
evidence reaches operator review, the operator's approval and era placement land atomically,
the chronology and the Life Map agree, and the memoir preview, the TXT export and the DOCX
export each contain the story **exactly once**, carrying the same provenance digest. Story
chain **11/11**; deletion-integrity acceptance **10/10**; every claim verified against the
filesystem and direct SQL rather than a response body. Record:
[`docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md`](docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md).

**That lane's own cleanup step exposed a privacy defect, and closing it is part of the same
record.** `hard_delete_person` removed all active narrator/person-scoped content rows — the
deletion audit and the erasure job are retained on purpose and hold no narrator speech —
answered HTTP 200, and left eight files on disk — five of them verbatim narrator speech. Deletion now plans before it destroys
the database authority those paths are named by, persists that plan bound to the canonical
absolute data root, refuses every symlink beneath the root (including one pointing at another
narrator inside it), covers eleven storage locations, deletes narrator media rather than
detaching it, purges the translation cache, **reports shared backups and exports rather than
rewriting them**, and is retryable through the product API with an audit trail that reads
partial then success. **Do not describe a hard delete as complete unless the response says
so** — three outcomes are distinguished, and HTTP 207 is reserved for the one an operator can
act on.

**Acceptance state, stated so nothing here reads as broader than it is.** The synthetic narrators' people rows, active
content and filesystem residue were removed, with their audit and erasure-job metadata
intentionally retained and carrying no narrator speech; **the four family narrators and
the designated non-family narrator are all untouched**;
`PRAGMA integrity_check` returns **ok**; and the **six pre-existing
`harness-test-gate7p2` foreign-key violations in `interview_sessions` are unchanged — this
lane did not create them and does not close them**. Gate B stays **OPEN**. Lean Lori L2 stays
**PARTIAL** and closed by product-priority decision. The directive-family registry remains
**inert** — built, gated and deliberately not activated. Kawa / Memory River appears here only
as **reachable frozen legacy UI awaiting adjudication** — non-authoritative; do not extend
or build on it — plus one storage directory in the erasure inventory. Nothing in this lane
revived it.

**The current substantive lane is Profile Seed reachability —** [`WO-LORI-PROFILE-SEED-REACHABILITY-01`](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md). **Phase 0, the executable map, is complete and accepted (2026-08-26, `661aa95`, 46 tests, one expected failure, no product or schema change); Phase 1 — server authority — is ACCEPTED (`1288baa`): the walk has a durable server owner, enrollment is atomic with narrator creation, and a storage fault can no longer masquerade as "this narrator has answered nothing". Phase 2 — prompt and committed-turn wiring — is in implementation and is not accepted. Steps 1–3 have landed (`f23040b`, `5a1eb56`, `1875821`, `b069680`, `c6c9ae4`, `0335cd3`): refusal detection is characterized and shared, and the turn state machine — two durable events, exact `(topic, version)` tuples, classification and recovery — exists behind a reproducible mutation gate that refuses an unclean tree or a red baseline. Steps 4–7 are owed: the composer section, REST read authority, WebSocket wiring, then the suites. Nothing in production imports the turn service yet, so no narrator behaviour has changed.** *(This paragraph said the spec was "ready for implementation" until 2026-08-26, while the paragraph fifty lines below already said Phase 1 was current. Two paragraphs of one file disagreeing about the same lane is how a reader picks the wrong one.)* The ten-topic Profile Seed onboarding is preserved for
new Lorevox narrators **regardless of narrator type**; what is owed is that an ordinary new
narrator reaches it. Today they do not, and the cause is a race the intake itself starts:
intake requires name, date of birth and birthplace; those three anchors are exactly what the
chronology needs; the chronology promotes the session past `pass1`; and the ten-topic block is
emitted only for an identity-complete narrator still in `pass1`. The ordinary path closes its
own gate before the narrator's first normal turn. *(Several governing documents read
"Option A, live narrators only" until 2026-08-20. That wording was false in the harmful
direction — it read as licence to gate the onboarding on narrator type — and is corrected in
place.)*

**The previous lane, `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01` — canonical narrator
authority**, is COMPLETE: one server-owned answer for projection, session ownership and
chronology, so that Life Map, Lori, sessions and Travel Document stop disagreeing about who
the narrator is.

**Phase 1 is ACCEPTED (2026-08-17).** The ten-step live run passed on a non-family test
narrator. Step 9 — rapid A→B narrator switching — is accepted with a stated limitation: it was
exercised against a *synthetic* narrator B, so the mechanism is proven but not against a
second narrator carrying a full live history.

**Phase 2 is ACCEPTED (2026-08-17) — 8/8.** It connects the Travel Document to that chronology
authority, reconciles narrator selection across shell-launched surfaces behind one shared
contract, and completes the legacy session-owner backfill in migration 0045.
*(This paragraph read "is BUILT … and its focused live acceptance is owed … the eight-step
focused live run has not" until 2026-08-18. The run happened and passed.)*

**Phase 3 (Reviewed story authority) is ACCEPTED (2026-08-18), and its one owed item is now
CLOSED by Phase 4.** A captured
story now has one server-owned review state, and the surfaces read it from one projection:
approved stories reach the Life Map, the chronology and Lori; provisional ones are counted but
never asserted; discarded ones are absent rather than dimmed. The nine-step live run passed
8 of 9 on a synthetic narrator. **The owed item is the half of step 6 that says Lori SPEAKS an
approved story** — the run proved the bridge attaches it (`approved=1 provisional=1`) and
proved the more important negative (a provisional story is never asserted), but Lori did not
use it. *(This paragraph first blamed a missing `drop_order` on the prompt section. That claim
was withdrawn the same day: nothing in production reads the section classification, so nothing
was dropped and the story did reach the model. The ranking fix is kept as a latent defect.)*
The owed check is therefore a prompt-authority question and folds into Phase 4.

**Phase 4 (Section-aware prompt authority) is ACCEPTED (2026-08-18), and this work order is
COMPLETE.** The composer has classified the system prompt into named sections since Lean Lori
Phase 2A and nothing in production read that classification: the budget could drop whole
conversation turns and nothing else, so when the mandatory content alone exceeded the window
the only available answer was to refuse. Phase 4 built the reader, wired all three transports
(REST chat, REST streaming, WebSocket) to it, and made removal a rung BELOW history exhaustion
— so no prompt that fits today changes, and some turns that used to refuse now degrade
gracefully instead. **The owed Phase 3 check passed in the same live run:** asked what she
already knew, Lori answered from the approved story rather than saying she did not recall it.

**No Story Integration phases remain. The current lane is Profile Seed reachability — Phase 0
(the executable map) and Phase 1 (server authority) are both complete and accepted, and
Phase 2, prompt and committed-turn wiring, is IN IMPLEMENTATION and NOT accepted; finishing Lean Lori
follows the lane.** *(This read "The next lane is finishing Lean Lori" until 2026-08-20,
before `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` closed and named its successor, and
"Phase 1, server authority, is the current work" until Phase 1 was accepted on 2026-08-26.)* The Lean
Lori block itself is unchanged and still owed — section metadata, directive gating, the
history-versus-sections priority decision (from the measurements Phase 4's telemetry now
emits), passive diagnostics, a small live acceptance, and reconciling that work order's stale
status table.

*(This paragraph said Phase 1 was "BUILT and AWAITING LIVE ACCEPTANCE" until 2026-08-17, and
said "Phase 3 … is not opened" until 2026-08-18.)*

Read, in this order:

1. [`HANDOFF.md`](HANDOFF.md) — current state. **Outranks everything below.**
2. [`MASTER_WORK_ORDER_CHECKLIST.md`](MASTER_WORK_ORDER_CHECKLIST.md) — the critical path.
3. [`CLAUDE.md`](CLAUDE.md) — operating doctrine, environment facts and hazards.
4. [`docs/wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md`](docs/wo/WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01_Spec.md) — the active work order.
5. [`docs/architecture/`](docs/architecture/) — pivot strategy, runtime architecture, Travel
   Document doctrine.

**Truth order when documents disagree:** current code → current tests and live evidence →
accepted closeouts and ADRs → `HANDOFF.md` → the checklist → old work-order status lines →
archived history. **Never rebuild finished work from a stale status line.**

---

## 6. Quick start

Verify against `HANDOFF.md` before relying on any command here.

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/start_all.sh      # API :8000, TTS :8001, UI :8082
```

**Cold boot takes about four minutes.** The HTTP listener answers in ~70 s, but model weights
and extractor warmup continue for another 2–3 minutes; a `curl /` health check proves only
that a socket is listening.

Two virtualenvs, deliberately: **`.venv`** is the test environment, **`.venv-gpu`** serves.
Both carry the same pinned web stack (`requirements-test.txt` / `requirements-gpu.txt`), so a
green TestClient result in `.venv` is evidence about the framework that actually serves.
Model work belongs in `.venv-gpu`.

Feature flags live in `.env`, which is untracked — **a tracked README cannot truthfully state
which flags are on for your machine.** See `.env.example` for the full documented set.

---

## 7. Tests

`pytest` is **not** installed. Use `unittest`, per module, in separate processes — whole-tree
discovery cross-contaminates through `api.db.DB_PATH`.

**Run in `.venv` by default.** Reach for `.venv-gpu` only for the modules that actually need
model or `transformers` dependencies — not for the `chat_ws` family as a class, several of
which run fine in `.venv`.

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPATH=server/code .venv/bin/python -m unittest tests.<module>

# only if that module reports ModuleNotFoundError for a model dependency
PYTHONPATH=server/code .venv-gpu/bin/python -m unittest tests.<module>
```

---

## 8. Privacy and data location

- Narrator data lives **outside the repository**, under `DATA_DIR` (`C:\hornelore_data` on the
  tenant-zero machine): SQLite database, photo archive, transcripts, audio.
- **`docs/reports/` is gitignored and stays local.** Reports carry live narrator content —
  transcripts, family names, runtime captures. Agents write there freely; nothing under it is
  ever staged. Re-publishing requires the redaction plan in
  `docs/wo/WO-PRIVACY-CANON-EXTRACTION-01_Spec.md`, not a `.gitignore` edit.
- **This README deliberately does not reproduce tenant-zero family identity data** — full
  names, birth dates, birthplaces. The previous one did, in the first document every clone
  displays. Describing tenant zero does not require reproducing it.
- Narrator records, photos, documents, transcripts and memoir drafts are owned by the operator
  and narrator who created them.

---

## 9. License

Hornelore is governed by the **Lorevox Source-Available Proprietary License (Version 1.1 —
2026)**, the same license as the public Lorevox product. Hornelore is the family R&D
deployment, not a separate license surface.

Source-available for view and study. No commercial use, hosting for third parties,
redistribution or public forks; no use of prompts, schemas or outputs for ML training. Named
brands (Lorevox, Lori, Hornelore) and expressive implementations are reserved.

Commercial, institutional, research, nonprofit, educational, clinical, archival,
family-office, elder-care, SaaS, hosted, deployment, integration, white-label and third-party
use are available by separate written license — contact **dev@lorevox.com**.

Third-party dependencies remain subject to their own licenses. End-user data is owned by the
operator and narrator who created it; this license grants no claim over it.

See [LICENSE](LICENSE) for complete terms. Contributions are assignment-based and by
invitation; research, model and benchmark contributions do not require code commits.
