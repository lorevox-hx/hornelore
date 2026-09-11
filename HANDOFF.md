# HORNELORE HANDOFF

**Repository:** `lorevox-hx/hornelore` · **Branch:** `main`
**Reduced 2026-08-28** by `WO-REPOSITORY-HYGIENE-01` Step 2. Superseded narrative and
retirement notes were removed, not lost — they are in Git history and in the work orders
this file points to. **No new obligation was introduced** — the reduction removed
superseded narrative, not owed work. *(This said "nothing was added", which was literally
false: the reduction rewrote and restructured, and a later correction added the hard-delete
rule back. The claim that matters is the one about obligations.)*

---

> # ▶ CURRENT ACTION — `WO-LOREVOX-PORTABLE-NARRATOR-01`, PHASE 5 (operator jobs + UI, designed against §16.1). **Phases 2–4 landed: exporter (§32, corrected on review), dry-run + Restore v1 with crash-truthful recovery (§33, §33.1), semantic round-trip (§34). Combined portability bank under `.venv`: restore 18 · round-trip 9 · export 24 · parity 15 = 66.** **Phase 0 landed** (`20260910T015024Z`, 0 unexplained lanes) and **Phase 1 landed 2026-09-10** — ownership declaration `narrator_data_inventory.py`, three erasure repairs in `db.py::_PARENT_OWNED_CHILDREN`, gap suite 4/4 + parity 15/15 under `.venv`; closeout in the WO §31. **Phase 2 is governed by WO §30 — generic travel domain + referential-integrity invariant; no narrator-specific export logic.** Both machines audited 2026-09-10: travel lives on the laptop, conversations/bio facts/audio on the desktop; neither is "the copy" (§31 data-location finding).
>
> **TWO-MACHINE AUDIT — CLOSED 2026-09-10.** Eleven labelled Phase 0 reports plus `scripts/phase0_report_comparator.py` run `phase0-report-comparison-20260910T234004Z`, all under `.runtime/eval/` (never staged). Result in WO §31: the family ids are identical on both machines; each narrator has lanes on only one of them (Chris: conversations / bio facts / audio on the desktop, the entire travel domain on the laptop); Melanie is laptop-only. **Neither machine is "the copy"; Phase 6 exports from both into separate clean roots.** Laptop handoff `docs/handoffs/HANDOFF_2026-09-10_LAPTOP-NARRATOR-AUDIT.md` is done and closed. No further audit questions unless a generic package invariant needs one.
>
> **PHASE 2 LANDED 2026-09-10 — WO §32.** `server/code/api/services/narrator_package.py` (one service, §28.5) + `scripts/narrator_package.py` CLI + `bagit==1.8.1` in both requirements files. Consumes `narrator_data_inventory.py` only; names no table but `people`/`sessions` (test-pinned). **Evidence under `.venv`: exporter 18/18; ownership parity 15/15 + erasure gaps 4/4 in the combined run before it.** Synthetic Ada with the full travel domain (all 15 `trip_*` lanes, source files, turn links) exports as a valid BagIt package; nothing of a second narrator leaks; nine refusal classes proven by reason code incl. dangling references and tampered-package detection.
>
> **PHASE 3 LANDED 2026-09-11 — WO §33.** `dry_run_restore()` / `restore_narrator()` in the same service; migration `0054_narrator_package_jobs` (installation-owned); `_safe_extract` §11 member inspection; files first with `O_EXCL`, one deferred-FK transaction, ids verbatim, `path_column_basis` rewrite, rollback removes the job's own files. **Review corrections to Phase 2 folded in the same block (§32): §29.3 staged originals verified against `import_candidate.file_hash`, source→copy byte binding, nested symlinks refuse, repo-root discovery, `db_outside_data_dir`, `unsafe_package_id`.**
>
> **PHASE 3 RECOVERY CORRECTED + PHASE 4 LANDED 2026-09-11 — WO §33.1, §34.** `db_committed` written inside the narrator transaction; `0055` gives the job a durable path→SHA-256 manifest before the first byte; `recover_restore_jobs()` deletes only hash-matching bytes below `db_committed`, refuses in every pre-commit state when the narrator is already published (`cleanup_required` included), and verifies without the package at `db_committed`; six recovery cases pinned, restore 19/19. `compare_packages_semantically()` proves export→restore→export equivalence, catches one changed value and one changed byte, sentinel narrator and installation state untouched. **Phase 4 finding — the installation-local integer-id boundary:** `turns.id` and the two extraction ledgers are AUTOINCREMENT surrogates; same-origin packages coexist, multi-origin packages may collide and V1 refuses, never remaps. Phase 6 unchanged (each package into its own clean root); Phase 7 amended; a Multi-Origin Merge/Remap WO is owed before any one-root family cutover.
>
> **NOW: Phase 5 — operator jobs and UI against §16.1:** two verdicts (integrity vs readiness), plain language with Advanced detail, export preflight from the declaration, asynchronous jobs with artifacts on disk outside `DATA_DIR`, uploads to controlled staging, export jobs in their own table or a deliberate generalisation in a NEW migration (`0056`+; `0054` and `0055` are landed and immutable — decided in Phase 5), one service. No real narrator is exported before Phase 6. **Lori conversational Phase 6 (Block D) STAYS PAUSED for portability** — verdict recorded, `docs/handoffs/HANDOFF_2026-09-09_PHASE6_C-BLOCK-AND-LEAN-QUALITY.md`.
>
> *(This header read "PHASE 6 — LORI'S CONVERSATIONAL QUALITY — IS NEXT" from 2026-09-08 to 2026-09-09, through four runs, a cohort, Block C and the Lean verdict. Decided 2026-09-09: portability lands before the compact prompt is written, so the family can leave Hornelore before more is built on top of it.)*
>
> | | |
> |---|---|
> | **Lori lane — its own sequence, PAUSED behind portability (this row is NOT the current action; the header above is)** | **THE INSTRUMENT IS BUILT AND HAS PAID FOR ITSELF. Stop treating "finish every Guard Lab acceptance clause" as a prerequisite for product work.** Active sequence: **Block A Operator control integration → Block B Phase 5C meaning disposition → Block C response-trace closer → Block D Phase 6 conversational quality → Block E Phase 7 review/memoir workflow → close Guard Lab acceptance debt → Phase 8.** The four remaining Guard Lab live checks are required evidence before FINAL acceptance and block none of it. **The switches are an instrument; they are not the product.** The product is a natural conversation backed by strict traceable memory and a usable memoir workflow |
> | **Blocks A, B, C — DONE** | **A** the Operator Guard Lab card · **B** Phase 5C meaning disposition, corrected and audited to a truthful exit gate · **C** the response-trace lifecycle. Phase 5's memory-integrity gate is closed for current scope; era/event review grouping is TRANSFERRED to Phase 7, measured rather than ticked |
> | **Block D — PHASE 6, VERDICT RECORDED 2026-09-09, PAUSED for portability** | **Block C DONE** — `cb38600` + `7d5d040`, both local extractors punctuation-aware, 0 splits / 0 lost anchors / 0 id-40 eligibility flips on the stored cohort-C replay; repairing the inputs does NOT vindicate id 40 or 48. **Lean SCORED by Chris on the frozen ten: Listening 3 · Warmth 4 · Dignity 4 · Continuity 2.** Best measured configuration and still generation-weak: backward redirects on 3 of 10, invented causality and significance, one turn with no question. **Arm B (Lean + prompt ids 1,3,5,6,7) REJECTED** — ten of ten collapsed to 1–7-word echoes, `eos`, `raw_equals_delivered=true`, prompt 5.2–5.7K vs Lean's 1–2K; **the prompt set induces the stub collapse id 39 was built to repair.** Single-factor screen: `1` and `3` keep their *intent* (not their 1.6K / 2.3K implementations); `5`, `6`, `7` rejected — `6` leaks *"weave that into the story"* into Lori's voice, `7` is the redirect tic. **Retention QUARANTINED:** LLM extraction hit `PROMPT_TOO_LARGE` (~9,830 vs 8,192) on every turn, independent of any arm; health stayed `0 RED` throughout. **Seven `testing_only` Ada fixtures exist; do not clean them.** Next for Phase 6, after portability: a compact Lori prompt written from `1`+`3`'s intent, Lean-sized, not stacked. Record: `docs/handoffs/HANDOFF_2026-09-09_PHASE6_C-BLOCK-AND-LEAN-QUALITY.md`. **A–F; no Block G.** |
> | **The cohort result — measured, monotonic** | Lean **38/38** raw-equals-delivered, **0 words removed**; Defaults 4/36; All-on **0/36 and 1,890 words removed**. The narrator receives **100% / 48% / 33%** of Lori's words. Two turns never reached the model at all in both guarded arms. Damage ranking by turns-changed-of-38: `witness_receipt_fallback` 27 · `reflection_shaper` 27 · `chain_anchor_opener` 16. **Every authority added made the model write more and the narrator receive less.** No further broad cohort runs are recommended |
> | **Lean is not the answer either — and this is the real Phase 6 question** | Under Lean nothing is removed and Lori is still weak: a father's-death disclosure drew 15 generic words, named relations were never generated, causal structure flattened to *"a cozy family dinner"*, and significance invented as *"likely played a significant role"*. **`raw_equals_delivered` is TRUE on those turns, so nothing removed them — they are GENERATION-level.** Investigation order: prompt/context composition → model behaviour → smallest supported change. **Do not add a deterministic guard to repair Lean blandness** |
> | **Malformed anchors — attribution CORRECTED 2026-09-08** | The record said Guard Lab **id 40** caused `"West St and Paul"`, `"For and They"` and `"From Saint Patrick to Day to 1950"`. The cohort-C trace says **two** authorities: `witness_receipt_fallback` (**id 48**) introduces `"X and Y — there's a lot held in that."` on 17 of 38 turns and was the **only** stage to change text on the `"West St and Paul"` turn — **id 40 never fired there** — while **id 40** introduces the different `"From A to B to C —"` opener on 16 of 38. Id 40's own registry entry already called that example "downstream" and was right. **The defect is upstream of both:** punctuation-blind proper-noun regexes at `factual_chain_capture.py:74` and `lori_structured_narrative_fallback.py:44`, mirrored deliberately and kept local for independent audit. **Repair authorized 2026-09-08 — fix BOTH local extractors, no shared-helper refactor. Repairing them does NOT establish that id 40 or id 48 should stay enabled**; that is a separate Phase 6 judgement on measured benefit against harm |
> | **Block C — what it actually was** | **NOT "the browser path has no trace closer".** That was carried forward from the frozen Walt/John tree and asserted without re-measuring; I was wrong and said so before writing code. Measured against the two live Guard Lab turns: both reached `_complete_claim -> _finalize_extraction_trace -> attach -> close`, **`swept` is ABSENT on both**, ledger rows `turnrow:2259` / `turnrow:2261` are `succeeded`, and the trace file was written 19:47:48Z for a turn that ended 19:47:39Z — a sweep could not fire before 19:50:39Z. **The normal funnel already works and was not touched.** What WAS broken: five pre-schedule early returns in `_run_completed_turn_extraction` touched the trace not at all, leaving every one parked for the full 180 seconds. Each now terminalizes through ONE seam — `not_applicable` / `not_measured` / `measurement_failed`, never `measured_absent`, because nothing was queried — and closes. An AST guard fails on any sixth early return that skips it |
> | **Block A — DONE** | The compact **Lori Configuration** card on the ordinary Operator tab: configuration (Defaults / Lean / Custom), revision, armed + recording, and **whether the narrator being interviewed can receive the selection** — with the plain sentence when they cannot. **Both verdicts are SERVER-DERIVED**: `GET /state?narrator_id=` resolves the durable people row, and the browser supplies identity only. Deciding eligibility in JavaScript by looking for an id in a list would put an authority decision where a stale page could arrange it. **The 43-row table is NOT duplicated** — it stays in the Bug Panel. `All Switchable Off` / `Restore Defaults` call the existing atomic endpoints; a 409 is adopted, not argued with. Closes the one usability gap the live run exposed: the panel knew an eligible narrator EXISTED, never whether you were talking to them |
> | **What the measurement detour bought** | The evidence said the dominant cause of what narrators received was the post-generation control layer, and there was no way to test 43 accumulated interventions one at a time. There is now. Spec: `docs/wo/WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01_Spec.md` |
> | **The diagnostic's four items — where they actually stand** | (1) **John's `META_FEEDBACK/correction` misroute — DONE**, pushed `8fa2e4e`. The last un-narrowed `not X but Y` pattern; two independent discriminators; `api.log` shows the misroute happened **three** times, including once on 2026-08-31 in an unrelated session. (2) **Response-trace closer — DONE (Block C), and the finding was RESTATED because the original was wrong.** `close()` is still reachable only from `turn_extraction.py`, and that is CORRECT for the browser path: measured 2026-09-07, both live turns closed through it promptly with `swept` absent. The harness path parks and sweeps because it never invokes that module — a different lane, not a broken closer. What was genuinely broken were five post-park early returns that touched the trace not at all; each now terminalizes and closes. (3) **The control layer — IN PROGRESS**, as the Guard Lab. (4) **Prompt budget — unchanged**, still second-order |
> | **Guard Lab — what is BUILT** | **43 numbered intervention authorities**, derived from the tree then numbered: 10 PROMPT, 7 ROUTE, 11 TRANSFORM, 6 VALIDATE, 3 REPLACE, 1 FINAL_WRITER, 5 LOCKED. Population **37 SWITCHABLE / 6 PROTECTED / 0 PENDING_SEAM**, derived. Three-state resolution, two fingerprints plus a revision, migration `0053`, and **one frozen snapshot acquired once per turn that governs all four runtime surfaces** — prompt composition, routing (clamped at the DETECTOR, not just the finalizer), communication control ids 32-42 individually, and the post-generation and final-writer authorities including the id 54 seam. **Legacy env authority retired**: four flags governed EIGHT registered authorities (6,7,8,30,31,36,41,42) and are now deployment defaults an operator override outranks. **Distinct attribution** for the ten comm-control identities, `selected` never conflated with `fired`. Isolation contracts **IC-1..IC-12** are defined in the spec and pinned by test — earlier drafts cited an undefined "V1-V12", which collided with the unrelated pre-pivot SECTION-EFFECT matrix |
> | **Guard Lab — the invariants that must not be re-broken** | **One acquisition per turn**, at the top of `_generate_and_stream_inner`, which dominates witness detection, the browser's proposed `turn_mode` and every route gate — "before prompt composition" is already too late for routes. **Client proposes, server resolves**: id 26's classifier is `lvRouteTurn` in `ui/js/app.js`, so a stale browser can propose `correction` regardless. **Fail-closed on all four gate conditions** — real person, durably `testing_only`, armed eval marker, trace actually recording. **Nothing downstream re-reads** the store, the marker or the eligibility flag. Safety precedence and id 20 floor hold survive `All Switchable Off` |
> | **Guard Lab — the operator control surface** | **BUILT.** `routers/operator_guard_lab.py` (`HORNELORE_OPERATOR_GUARD_LAB=1`, 404 when off) serves all 43 rows with **canonical default, deployment default, operator override and effective state as four separate fields** plus the reason that decided each, the revision and both fingerprints, the pending-seam list, and the gate's four eligibility conditions **by name** — without which a selection that cannot reach any turn looks identical to one that can. `All Switchable Off` and `Restore Defaults` are ONE request and ONE revision each, never 37 writes. Every mutation echoes the revision the operator was looking at and returns the WHOLE new state, so the panel adopts rather than re-derives and needs no reload; a stale view gets **409 carrying the live configuration**. The panel is a section of the existing Bug Panel (`ui/js/bug-panel-guard-lab.js`, `#lv10dBpGuardLab`), **not a second application**. `/narrators` shows testing-only eligibility and has **no write partner** — this surface may show eligibility and never confer it |
> | **Guard Lab — LIVE ACCEPTANCE, PARTIAL 2026-09-07** | Run `guard-lab-20260907_124346`, laptop `.venv-gpu`, real model and live database. **6 passed / 0 failed / 3 unverified — banked deliberately, NOT waved through.** Proven live: the narrator created through the product path PERSISTED `testing_only` (the defect this lane opened with); `All Switchable Off` moved the revision **exactly once** while writing 37 overrides, `switchableStillRunning: []`, the six protected rows byte-identical either side; id 37 On changed **one** authority, `onlyIdsChanged: [37]`; and **two turns consumed revisions 1 and 2 in ONE running process with no restart** — read from the trace, with the consumed selection fingerprints `55a52f0cb045` / `dfcbfc2e8904` matching the operator snapshots byte for byte. **Extraction fired** (`RESIDENCE > PLACE — Lowell`), which the Walt/John turns never did. Record: `docs/reports/GUARD-LAB-LIVE-ACCEPTANCE-20260907.md` (local-only) |
> | **The measurement that closes the diagnostic's converse** | Under `All Switchable Off`, **`raw_equals_delivered` is TRUE on both turns** — 56 words in, 56 delivered; 26 in, 26 delivered. **Zero removed.** Against Walt's 579 -> 182 (69% removed) and false on 13 of 15. The claim that the dominant cause of what narrators read was the post-generation control layer now has its converse measured on a live stack. Generation was 4.3s and 4.6s; the ~32s wall clock was TTS and UI and **must never be reported as model latency** |
> | **Guard Lab — the four checks STILL OPEN** | **UNVERIFIED is not a soft pass and `verify` exits 2.** (1) the mid-turn freeze OBSERVED — needs `--toggle-at`, and the trace alone cannot decide it; (2) restart persistence — needs a `before-restart` / `after-restart` snapshot pair, which the corrected verifier selects BY LABEL; (3) an ordinary narrator refused BY NAME with `not_testing_only`, using a synthetic `ZZ COHORT` narrator, not a family one; (4) the stale second-tab 409 on a real browser. **These are acceptance evidence, not prerequisites** — they finish at the next live session and do not block the work below |
> | **Lean-baseline observations — EVIDENCE, NOT A VERDICT** | Two turns on an EMPTY profile. Lori paraphrased over-generally ("a cozy family dinner" for a turn whose structure was *father worked evenings, therefore weekday dinner was three people*), dropped the aunt, the cousin and the walk to school, and offered an unsupported "likely played a significant role". **Nothing deleted them — `raw_equals_delivered` is true; they were never generated.** That is the OPPOSITE failure mode from Walt's, and a prompt/model question rather than a control-layer one. Two consecutive identity questions are **CONFOUNDED** by the empty record (Profile Seed 0/10, id 54 OFF, so Lori chose them). **DO NOT ADD A GUARD IN RESPONSE.** The instrument exists so an intervention earns its way back by measured benefit |
> | **Guard Lab — what is NOT built yet** | ~~The compact Operator card~~ — **BUILT (Block A).** What remains: the lean baseline prompt and a **separate populated** synthetic narrator — the empty one stays the instrumentation narrator — and the owed §5 short-natural run. Both belong to Phase 6 |
> | **`testing_only` — a pre-existing gap, now closed** | It was accepted by both narrator-creation paths, used to bypass consent, returned in the response, and **stored nowhere** — `create_person()` had no such parameter and `db.py` no such field, so a test narrator was durably indistinguishable from a real one. Now a `people` column owned by `init_db()`'s PRAGMA-guarded block. **Deliberately NOT a migration**: migration `0013`'s header records the incident where a people-column ALTER re-ran every boot and "knock[ed] out every endpoint that consulted the schema". Existing rows are `false`, fail-closed; consent attestations must never be used to infer test status |
> | **What the diagnostic MEASURED, 2026-09-06/07** | Run `.runtime/eval/walt-john-20260906_200514`, instrumentation frozen at `f8eeea7`. **The framing was wrong and the evidence says so.** The 256 cap **never bound** — all 15 traced turns ended `eos`, zero `max_new`, zero `eos_at_limit`. **VRAM was never close** — 7.2–9.4 GB free against a guard asking 1.5–1.8 GB, `pass` every turn. **The prompt budget is real**: Walt's prompt grew 6,506 → 10,671, shedding 2,958 tokens by era seven, with **`kept_turns=0` on five of eight turns**. **But the dominant cause is the post-generation control layer: 69% of Walt's words removed** (579 → 182), 34% of John's. Era 5 generated 199 words at `eos` and delivered 29 — cut for `too_long`, then failed by the validator for `too_short`, then replaced with a template that appears on five of fifteen turns |
> | **Two instrument findings** | (a) **The response trace has no closer on the harness path.** `close()` is reachable only from `turn_extraction.py`, which this client never invokes; records survive only via the 180-second parked sweep, which a 60-second run never trips for its own turns. Walt's evidence existed only because John ran afterwards; John 2's did not survive. (b) **The deterministic witness path produced no trace — TRUE AT THE FROZEN CHECKPOINT, CLOSED SINCE.** At the frozen Walt/John diagnostic tree those turns returned before tracing opened and therefore produced no response trace, which is why John 1's era 01 is absent from the dataset. **Guard Lab has since closed that gap**: the turn trace opens at authority acquisition, ahead of witness detection and every route gate, and deterministic responses complete through the shared finalizer. The dataset row below still reflects the frozen tree and is not restated by this — a report on those runs must still name which turns are absent and why |
> | **Dataset — frozen, do not extend** | Walt `9d96e1db-8f8` **8/8 traced** (primary) · John 1 `da567099-505` **7/8** (era 01 diverted to the witness path, never traced) · John 2 `8bd4ae81-1ec` **0/8** (accidental repeat, parked at shutdown; behavioural replication only, via `api.log`) · GPU 4,230 samples · **`api.log` is the fallback for every untraced turn.** `…_200124` is a stray from an abandoned arming — ignore it, delete nothing |
> | **What it does NOT establish** | **Nothing about conversational quality or listening.** These are the dense-narration harnesses, authorised by §9 for context pressure and explicitly barred from answering the §8 turn-shape questions. **The short-natural-turn Walt run in §5 remains OWED and UNRUN.** No refusal, cancellation or `measurement_failed` path occurred, so the terminal-trace machinery is untested live. Nothing was tuned |
> | **Why before 5C** | Two of Phase 5C's three open destinations — what consumes `STATE_DECEASED`, and where the `adult`/`older`/`younger` qualifiers belong — are questions about what the memoir needs. Walt+John is the first measurement that speaks to them. Deciding them first would design a destination before seeing the traffic |
> | **Phase 5C** | ✅ **DONE 2026-09-07 as Block B** — one disposition contract for "understood, no destination", corrected and audited to a truthful Phase 5 exit gate. `WO-LORI-ARCHIVE-TO-MEMOIR-02` §B and §5C. *(This row said "QUEUED, not active" until 2026-09-08, contradicting the Blocks A/B/C row four lines above it.)* **The prohibitions it carried still bind:** `siblings.birthOrder` is not the answer for `older` — mapping it would manufacture a fact; and **do not disable `HORNELORE_CLAIMS_VALIDATORS` as a product fix**, since it gates several safeguards while leaving the parse-time whitelist active |
> | **Mutation gate** | ✅ **85/85 caught, 0 MISSED, 0 BROKEN, 180.0 min** — 2026-09-06, `.venv/bin/python`, clean tree, journal absent, product tree restored. 35 of the 85 are designs a lane actually carried. **Baseline: 12 unique commands, all green — and `test_profile_seed_rest_read_authority` ran 48 with 6 SKIPPED**, which is stated because `OK` with skips is not a pass and eleven `S` mutations depend on that suite. **This is the accepted Phase 5B/tooling baseline, and the gate is now ACCEPTANCE-ONLY.** Three suites are 80% of the three hours (`docs/BACKLOG.md` §6c); day to day run the focused tests plus the family that protects the changed file, per the map in `scripts/run_mutation_gate.py`. **The rule is "follow a moved invariant", not "run nearby families"** — `C8` survived a full gate because a refactor moved `identity_complete` into a reader its tests did not watch |
> | **Phase 5A + 5B** | ✅ **ACCEPTED 2026-09-06** on the 85/85 gate. 5A bound bio-fact provenance to the committed-turn `_Claim`. 5B built `relationship_interpreter.py` — one vocabulary, derived rather than duplicated — added `family.priorPartners.relation`, and made **the narrator's wording decide the lane**: the deliberately crossed passage is corrected, `ex-wife` stores relation `wife` with the phrase in provenance, `partner` binds without manufacturing a marriage, `late wife` keeps the word `late` under a third state `deceased`, an ex-wife's occupation goes to review rather than to the current spouse, person association is re-derived after a lane change, and the Family Tree draws `partnership` / `former_marriage` / `marriage` instead of `marriage` for everything. **74 tests in the two lane suites (0 skips); 156 with the Phase 4/5A suites; mutation gate `L1`–`L9` 9/9 caught, 7 of them designs this lane actually carried.** Sandbox `python3` only — `.venv` is Chris's run |
> | **Phase 5B — the four boundary defects** | All four were invisible to helper-level tests: (1) `getattr(req, "conv_id")` — not a field on the request, so production wrote null provenance while `session_id` sat unused; (2) `ExtractedItem(...)` names its kwargs, so the recorded narrator phrase was dropped one call before the pass that needed it; (3) the lane was chosen by the CANONICALIZED value, and `wife` occurs twice in the mixed passage, Mary's first; (4) grouping runs BEFORE the lane pass, so moved items reached callers with no person association while a comment claimed they were regrouped |
> | **Phase 5B — what it does NOT claim** | **No live turn was run.** `STATE_DECEASED` is recorded, not consumed. The qualifiers are read, not carried. The 114/14 banks were **not** rerun |
> | **Phase 4** | ✅ **ACCEPTED 2026-09-05.** The story-capture decision is durable on the source narrator turn, **including declined turns that create no candidate**. Implementation `24c7130` (clean tree); live probe `20260905-151658` on `.venv-gpu` — **11 passed / 0 failed / 0 unverified**; offline `.venv` **241 tests, ZERO skips**; **8/8 mutations caught**. Nominated turn bound candidate `8a159445`; declined turn carried a full eight-field diagnostic and no story row |
> | **Phase 4 — what it did NOT change** | No threshold, anchor regex, chain classifier, source unit, review rule, memoir behaviour, migration or new table. The 114/14 banks were deliberately **not** rerun — Phase 4 changed observability, not extraction |
> | **Phase 4 — one honest gap** | **Ten of eleven acceptance clauses were proven LIVE.** `measurement_failed` is covered offline and by mutations 3 and 6 but has never been seen on a live turn. Also: a trigger firing with **no `person_id`** fits none of the three closed outcomes and deliberately records nothing — opening the vocabulary is Chris's call |
> | **Phase 3** | ✅ **ACCEPTED 2026-09-05.** Group-local kinship guard; per-value grounding (`spoken`/`derived`/`unsupported`); review-only results end to end; browser authority enforcement (the server's downgrade now binds the browser — it previously did not, which also silently affected shipped transcript safety); empty-correction fallthrough resetting BOTH copies of `turn_mode`. Live gate: Stefi `20260905-021741`, **9/9** over the production WebSocket |
> | **Phase 3 — last box closed** | *Jim binds as Pat's husband* — **CLOSED 2026-09-05.** `Jim` had no test anywhere while `Otis` had five and `Domingo` two. `TheJimCase` drives the shipped `run_field_extraction` with Pat's own wording: parent language elsewhere keeps `Walter` and quarantines Jim; the spouse field still reaches him. **The guard was already correct — nobody had written the test** |
> | **Extraction baseline** | **NOT comparable.** `r5h`/`r5j`/`r5k` span **three scorers** and two dirty trees over one case bank. `r5k`'s **0 `must_not_write` at `5afead5`** is solid current evidence; the `2 → 0` delta is **not established** — `must_not_write` is itself a scorer judgment. Nonblocking debt: [`docs/BACKLOG.md`](docs/BACKLOG.md) §6a |
> | **Testing doctrine** | **A fixture may not supply the property being proven.** The maintained table in [`docs/TESTING-DOCTRINE.md`](docs/TESTING-DOCTRINE.md) **owns the count** — no other document restates it. Every helper assertion needs a production-boundary companion, and every mutation must make that companion fail |
> | **Phase 2** | ✅ **CLOSED 2026-09-04** — read-only mechanism audit, cohort not rerun, nothing curated. Archival 38/38 · candidates 35/38 · transcripts 35/35 byte-exact · zero over-capture |
> | **Phase 1** | ✅ **ACCEPTED 2026-09-04.** `20260904T123556Z` performed the only two authorized mutations; `20260904T130525Z` carried that proof forward at **zero mutations** |
> | **Mutations — ALL SPENT** | `447eee18` is `promoted`, `building_years`/`operator_set`, `review_version: 3`. **No further mutation is authorized** |
> | **Do NOT** | curate the synthetic queue, promote the 35, adjust the classifier, rerun the cohort, or repair `turn_extraction_ledger` for a harness that never requested extraction |
>
> **A refusal is a result.** A run that stops before mutating, names the failing link and
> exits non-zero has done its job. It is not a failed attempt to be retried until it passes.
>
> **Profile Seed Phase 3 is OWED, not current.** It was a previous current action and is
> **IN IMPLEMENTATION with ACCEPTANCE OPEN**; it is not cancelled and not superseded — see
> §2. **Repository hygiene is COMPLETE** — `WO-REPOSITORY-HYGIENE-01` closed 2026-09-08 at
> `e0fde84`, its deferred remainder resumed and discharged across `93a8f85`, `9e1db2a` and
> `e0fde84`. *(These lines said "Phase A ACCEPTED, remainder PAUSED, work order INCOMPLETE"
> until 2026-09-08. That was true when written and is now false; the residual obligations
> the closeout registered rather than fixed are in `docs/BACKLOG.md`, and completing the
> work order did not discharge them.)* **No priority change ever converts owed work into
> finished work**, and no document may say otherwise.
>
> **Still frozen:** runtime safety, the model and its 8,192-token window, the directive
> registry and Kawa are governed by `CLAUDE.md`, which no priority decision touches.

---

## 1. Read this first

When documents disagree:

```text
current code
> current tests and live evidence
> accepted closeout records and ADRs
> this handoff
> MASTER_WORK_ORDER_CHECKLIST.md
> old work-order status lines
> archived history
```

**Do not restart work from an old status line.** Read the implementation, its tests and its
latest live evidence first.

**Derive the live head. Never read it from a document:**

```bash
git rev-parse origin/main      # the live head, always
git status --porcelain         # must be empty before any gate
```

Fixed acceptance checkpoints stay written down, because they describe trees that have
stopped moving:

| Hash | What it is |
|---|---|
| `9127adb` | Profile Seed Step 5 accepted |
| `d0e5294` | Pre-Step-6 correction checkpoint accepted; tagged `archive/pre-hygiene-2026-08-28` |
| `ea3ab27` | Tree inspected by the repository audit; tagged `audit/repository-baseline-2026-08-28`. **Not** the rollback point |
| `5f6b01b` | Repository hygiene **Step 1** (indexes) accepted |
| `db0c5e7` | Repository hygiene **Step 2** (control authority) accepted |
| `ff1ff4f` | Repository hygiene **Step 2b** (changelog preservation) accepted |
| `5086490` | Repository hygiene **Step 3, first cohort** — the four root dated artifacts, moved byte-for-byte. **Phase A ends here** |
| `93a8f85` · `9e1db2a` · `e0fde84` | Repository hygiene **Blocks 1–3, resumed and accepted 2026-09-08**. `e0fde84` is the closeout and **the last hygiene commit; `WO-REPOSITORY-HYGIENE-01` is COMPLETE** |
| `12221e0`…`58dfc40` | Profile Seed **Phase 2 Step 6** — implementation and correction block. **ACCEPTED 2026-08-29**, 16/16 live through the production WebSocket |
| `525a43f` | The Step 6 live probe, committed. Run 2's provenance rests on this |
| `6885bb2` | Profile Seed **Phase 2 Step 7** — consolidated closure and control reconciliation |

Where everything else lives: [`docs/INDEX.md`](docs/INDEX.md) ·
[`docs/BACKLOG.md`](docs/BACKLOG.md) · [`scripts/INDEX.md`](scripts/INDEX.md) ·
[`docs/archive/INDEX.md`](docs/archive/INDEX.md).

## 1a. Phase 2 acceptance evidence — by checkpoint and changed target

**Recorded this way deliberately.** A single "69/69 in one invocation" figure was NOT
produced and must not be claimed: the one full-gate attempt was interrupted, and stitching
its partial results onto earlier runs would manufacture an aggregate no invocation ever
reported. What follows is what was actually run, against what.

| Evidence | Scope | Result |
|---|---|---|
| Last complete clean-tree gate | all mutations at that checkpoint | **63/63 CAUGHT** |
| Step 6 changed-file mutations | WebSocket, runtime, REST — `D1`–`D4`, `S1`–`S6`, `S11`, `X1`–`X6` | **17/17 CAUGHT** |
| Follow-up-ruling composer mutations | `prompt_composer.py` after `8cc51b4` | **14/14 CAUGHT** |
| `C3` after its anchor repair | the instrument itself | **CAUGHT** (reported `BROKEN` first — the runner refusing to score a mutation it could not apply) |
| `C8`, `H4`, `H5`, `C16` at `291197a` | remaining composer guards | **4/4 CAUGHT** |
| Consolidated Phase 2 suites | eleven modules, derived from the tree | **436 ran, 6 skipped, 0 failed** on `python3` |
| Route coverage, zero skips | `.venv-gpu`, REST authority + strict version | **70/70, 0 skipped** |
| Guard Lab runtime wiring, `.venv-gpu` | safety precedence · fail-closed guard path · session identity · turn cancellation — **the four suites the agent sandbox cannot run** (`transformers` absent, identical at HEAD) | **48/48, 0 skipped, 2026-09-07.** Safety route still outranks the clamped detectors on all six distress conversations; the fail-closed wrapper still suppresses unguarded LLM text, at a post-edit line number; `scan_answer` failure still forces interview on both the echo and meta paths |
| Live production WebSocket | two probe runs, real model | **16/16 each** |

**The untouched Phase 1 and reducer mutations were deliberately NOT re-run.** Documentation
changed; that code did not. Re-testing unchanged code to raise a count is ceremony, and
the count it produces is not evidence about this change.

---

## 2. Current state

| Lane | State |
|---|---|
| **`WO-LORI-ARCHIVE-TO-MEMOIR-02`** | 🔵 **ACTIVE AND CURRENT — Phases 0–4, 5A/5B and 5C ACCEPTED; Blocks A, B and C DONE. PHASE 6 (Block D, conversational quality) IS THE CURRENT WORK.** `WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01` built the instrument and is no longer the blocking action; its four open live checks are acceptance evidence and block nothing. §9. *(This row said "5C QUEUED, NOT the current action" until 2026-09-08.)* **Phase 1** proved the memoir chain (`20260904T123556Z` mutations, `20260904T130525Z` proof at zero mutations, exit 0, agreement 1/1/1). **Phase 2** closed the mechanism audit read-only: archival 38/38, candidates 35/38, transcripts 35/35 byte-exact, zero over-capture. **Its findings were CORRECTED 2026-09-04 after reading `.runtime/logs/api.log`, which the original audit never opened:** the capture decision is recorded for all 38 turns and agrees exactly with the recomputed split (18/17/3), so the defect is durability not absence; the three misses share one cause (no relative time phrasing in a present-day life inventory); and the zero ledger rows are a **harness** gap, not a product defect. **Phase 3:** correction-route bypass + spouse-under-`parents.*`, both now cited to their reading lines — the browser regex at `app.js:2599` fires on *"not the"* in Stefi's clarification, and `chat_ws.py:965` passes `assistant_text=None` so the extractor reads the narrator. Capture-decision persistence is **Phase 4**. Reproduce: `python3 scripts/phase2_verify_ledger.py` |
| **Memory Integrity Layer / guardrail audit** | 🟡 **DESIGN THREAD — no work order yet.** Response-guard audit done; `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md` (repo root) is **ACTIVE / NEXT**. Nothing here is scheduled. §10 |
| **Repository hygiene** | ✅ **COMPLETE 2026-09-08 — `WO-REPOSITORY-HYGIENE-01` is CLOSED at `e0fde84`. Do not reopen it.** Phase A: Steps 0, 1 `5f6b01b`, 2 `db0c5e7`, 2b `ff1ff4f`, first Step 3 cohort `5086490`. The remainder, deferred 2026-08-28 by product-priority decision, was resumed and discharged 2026-09-08 across `93a8f85` (root spec pile emptied, 30 specs reconciled and rehomed, **root WO/BUG count 0**), `9e1db2a` (one test root, shadow archived, docs by ownership) and `e0fde84` (index lifecycle, entry surfaces, closeout). **Completion is not a claim the repository is "fully clean":** ten scripts remain explicitly `unknown` and are retained, and the product and test obligations the pass discovered were **registered in [`docs/BACKLOG.md`](docs/BACKLOG.md), not fixed** — closing the work order did not discharge them. *(This row read "PHASE A ACCEPTED, REMAINDER PAUSED — INCOMPLETE" until 2026-09-08.)* |
| **Profile Seed reachability** | ⏸️ **OWED — Phase 3 IN IMPLEMENTATION with ACCEPTANCE OPEN, and no longer the current action.** *(It was, until `WO-LORI-ARCHIVE-TO-MEMOIR-02` took priority. Owed work does not become finished work when the lane changes.)* Phase 0 `661aa95` · Phase 1 `1288baa` · **Phase 2 ACCEPTED 2026-08-29, steps 1–7 complete** (step 4 `b269184`, step 5 `9127adb`, pre-Step-6 corrections `d0e5294`, step 6 `12221e0`…`58dfc40` live, step 7 `6885bb2`) · Phase 3 implementation landed through `2b7e634`; its six acceptance conditions remain open. Phases 4–5 are partially run and not accepted. See the Profile Seed spec's reconciled status block |
| `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01` | **COMPLETE** — Phases 1–4 accepted. Closes the three L2 integration defects |
| `WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01` | **ACCEPTED AND COMPLETE 2026-08-20** — story-to-memoir 11/11, deletion integrity 10/10, verified against filesystem and SQL |
| Deletion / erasure integrity | **CLOSED 2026-08-20.** Erasure planned before the DB authority is destroyed, persisted (0049), bound to the canonical absolute root (0050); refuses every symlink below the root; eleven stores; deletes media; purges the translation cache; reports backups rather than rewriting them; fails closed; retryable with a truthful audit trail |
| Multi-day trip-photo placement | **COMPLETE**, Gate 3 accepted 2026-08-14. §4 |
| Photo Palette | **COMPLETE**, P4/P5 accepted 2026-08-14. Do not reopen for polish. §4 |
| Travel Document core/export | **CLOSED on live evidence.** Preserve the editable timeline → DOCX projection rule |
| Google Photos Picker | **BANKED.** Reopen only for a demonstrated defect |
| Lean Lori | **L1 COMPLETE. L2 PARTIAL and CLOSED by product-priority decision — DO NOT RESUME.** Eleven commits already landed; do not rebuild. **Gate B stays OPEN**, Phase 10 open |
| Legacy photo-day scalar retirement (Phase 6) | **DEFERRED — reopening requires Chris's explicit authorization. Not approved, not scheduled, not a decision currently on the table.** Palette and multi-day acceptance do not imply it. The scalar is frozen, unwritten, ignored for authoritative decisions and correctly derived on read; dropping it buys nothing and costs a risky SQLite rebuild. [`docs/BACKLOG.md`](docs/BACKLOG.md) §3b |
| Test-artifact **cleanup** | **DEFERRED — needs Chris's authorization.** The 22 harness narrators were deliberately not deleted |
| Kawa / Memory River | ✅ **REMOVED 2026-09-08 — `WO-KAWA-REMOVAL-01` COMPLETE.** `3481d1a` compatibility half, `0a16c88` removal half. **Not the current lane; nothing is owed.** Life Map is the only navigation surface — do not rebuild it. *(This row has now said three different things: "removal is NOT decided", then "removal debt", now removed. Each was true when written.)* Preserved by design: narrator-erasure support, the historical `kawa_segment` media type, migration 0003, the retired-language eval, research and archived specs. `DATA_DIR/kawa/` narrator data was NOT deleted |
| Runtime safety | **PARKED**, server-authoritative. Never reactivate through an environment value |
| Model / 8,192-token window | **LOCKED.** Any proposed change is stop-and-report |
| Directive-family registry | **INERT** — built, gated, deliberately not activated |
| Privacy canon extraction / history purge | **PARKED work order.** The authority for any history rewrite |

**Profile Seed, why it exists:** the ten-topic workflow is preserved and ordinarily
unreachable, because the intake supplies exactly what closes its own gate. Intake requires
name, DOB and birthplace; those three anchors are what chronology needs; chronology
promotes `pass1 → pass2a`; and the composer emits the ten-topic block only for an
identity-complete narrator **still in `pass1`**. The onboarding is **preserved for new
Lorevox narrators regardless of narrator type**; what is owed is reachability.

**Narrators are untouched.** The four family narrators and the designated non-family
narrator are all untouched. Six pre-existing `harness-test-gate7p2` FK violations in
`interview_sessions` are unchanged and are **not** closed by any current lane.

## 3. Step 6 — ACCEPTED: the boundary it honoured, and the result

**Preserved as the accepted record, not as a plan.** *(This section spoke about Step 6 in
the future tense — "Step 6 is the fix", "what it must not touch". Step 6 landed and was
accepted on live evidence; a section that still describes it as upcoming is the exact
stale-status defect this file has twice been reduced to remove. The boundaries below were
honoured and are kept because they still bind Phase 3.)*

**Result:** the walk reaches a narrator through the production WebSocket. Two probe runs,
16/16 each, real model. Presentation and response events commit on the assistant row;
advancement happens only after that commit; recovery runs before composition; the nine
deterministic paths stamp nothing.

### What it inherited and did not touch

**REST reads authority and DOES NOT ADVANCE**, and that is still true — Option B is
unchanged. The defect it caused: a narrator answered a topic and the durable row still
read `active=childhood_home · remaining=10 · version=2`, so across a session boundary Lori
asked for something she had already been told. **Step 6 fixed that on the WebSocket path**,
which is the path the narrator UI actually uses.

**WebSocket is the production narrator transport.** `ui/js/api.js` drives `/api/chat/ws`;
a complete narrator turn produces **zero HTTP requests matching "chat"**. `/api/chat` has
no UI caller; `/api/chat/stream` is reachable only behind the dev-only
`window.LV_ALLOW_SSE_FALLBACK`. **A narrator using the production UI reaches the walk at
Step 6.** The walk is already live over REST.

**No historical-narrator auto-enrollment.** Enrollment happens only inside
`create_person()`. All five existing narrators are `enrolled: false`. Extending it to
family narrators is a **backfill decision**, not a code change.

**Step 6 inherits, and must not undo** — from the accepted correction checkpoint:

* the **nine** deterministic persist paths, and the test that fails if a tenth appears;
* `HOLD` for every ineligible turn on an active walk — Step 6 supplies `eligible`, it does
  not re-decide what ineligibility means;
* one conversation-control vocabulary, in `services/conversation_control.py`;
* `expected_version` strict at **both** layers — the WebSocket path calls the accessor
  directly and inherits the second one, not the first.

`tests/test_profile_seed_deterministic_paths.py::Step6TripwireTests` fails the moment Step
6 adds Profile Seed metadata to `chat_ws.py`. That is deliberate: narrow it to the model
path, leave the nine covered.

**Step 6 must NOT touch:** REST persistence · UI promotion sites (Phase 3) · schema or
migrations · chronology · Life Map · memoir · story authority · safety (PARKED) · model /
8,192-token window (LOCKED) · directive-family registry (INERT) · Kawa (**REMOVED 2026-09-08
by its own bounded work order — nothing left for Step 6 to touch, and nothing to rebuild**).
**Stop after focused implementation and tests, before Step 7.**

Detail: [`docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md`](docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md)
§6, §6b, §16, §16a.

## 4. Product boundaries that bind

**Multi-day placement.** The authoritative model is a set of rows in
`trip_photo_day_placements`, not one nullable day on `trip_photo_links`. One photo and one
trip membership may have zero, one or many placements; one day may hold many photos; **Add
to this day**, **Remove from this day** and **Move** are distinct; removing one occurrence
preserves every other placement, membership, original, thumbnail, caption, approval and
context; explicit placements and taken-date suggestions are counted separately; shared
captions project across placements and **do not grant Lori approval**.

**The compatibility scalar is `null` for zero OR multiple placements and must never be
used to decide whether a photo is unplaced.** The authoritative unplaced rule is:

```text
zero trip_photo_day_placements
```

Never `trip_day_id IS NULL`.

**Hard-delete truthfulness.** **A deletion is complete only when the erasure result says
complete.** Three outcomes are distinguished and must stay distinguished; **HTTP 207 is the
operator-actionable partial** — something was removed, something was not, and the operator
can act on the difference. Never describe a hard delete as complete because the call
returned without raising. Retained audit and erasure-job metadata is kept on purpose and
**must contain no narrator speech**.

This is here, not only in its work order, because it is a rule a reader needs at the moment
they are looking at deletion behaviour. The defect it exists for was real:
`hard_delete_person` removed every active narrator-scoped row, answered **200**, and left
eight files on disk — five of them verbatim narrator speech. Detail:
[`docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md`](docs/wo/WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01_Spec.md).

**Photo Palette** is a mode inside the existing Travel Document workspace — not a second
product, not a nested modal. It reuses the landed inventory, thumbnails, placement APIs,
bounded-window helpers and trip/day state. It does **not** include destructive deletion,
face recognition, AI photo interpretation, duplicate originals or a schema rewrite.

Rulings: [`docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md`](docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md) 1.16.

## 5. Live-review artifacts — PRESERVE, NO DELETION AUTHORIZED

**Erasure of any narrator listed below takes Chris's
explicit authorization and must go through the product erasure path, with the result
reported truthfully. **No family narrator appears here and none was touched:** only the
three `ZZ` probes are enrolled in a Profile Seed walk, verified against the live database
on 2026-08-29.

| What | Exact IDs |
|---|---|
| **Del** (`6ad678ee-b295-49de-8578-da00200848ba`) | turns **1712–1717** on `switch_mtbn3x4a_ifo9`; **22 turns total** across all sessions |
| **`ZZ Step5 Probe (delete me)`** (`6e606ace-2a72-439a-8474-04140409098b`) | owns `zz-probe-seed-1`, turns **1718–1721** |
| **`ZZ Step6 WebSocket Probe (delete me)`** (`7d64b8be-8bbb-48a1-98cc-9ab1ce09421a`) | owns `step6-ws-probe-2026-08-28`, turns **1722–1731**; onboarding `active/siblings/v3`; `memory/archive/people/<id>` exists. **Step 6 live acceptance run 1** |
| **`ZZ Step6 WebSocket Probe 2 (delete me)`** (`9ae02617-6c6d-41f0-832d-41e82caba976`) | owns `step6-ws-probe-2-2026-08-28`, turns **1732–1741**; onboarding `active/siblings/v3`. **Step 6 live acceptance run 2 — the clean-tree, committed-instrument run** |
| `zz-probe-contradiction` | **no session, no turns** — the 409 fired before anything was written |

**Nothing has been deleted and no deletion is authorized.** The synthetic probe may be
hard-deleted through the product erasure path **only on Chris's explicit instruction**. Del
and all of his data are to be left alone.

## 6. Working and verification policy

* Work in coherent product blocks, not one-line review cycles.
* Focused tests while coding; one consolidated regression run at the end of the block.
* Mutation and non-vacuity tests only for load-bearing behaviour.
* Do not restart for documentation, tests, or harness-only changes.
* Keep the stack down through an implementation block. Start once for live acceptance,
  restart once for final persistence proof.
* Stop early only for schema risk, destructive live-data action, a security boundary, a
  model/configuration change, or a real design decision.
* **Report skip counts.** `OK (skipped=N)` is not a pass. Name the interpreter a result
  came from.
* **Claude prepares copy-paste `git add` + `git commit` blocks; Chris runs them and pushes
  from GitHub Desktop.** Agents do not run git here. A sandbox git command that hits the
  agent timeout on the `/mnt/c` 9p mount leaves `.git/index.lock` behind and silently
  blocks GitHub Desktop and Chris's own WSL git — presenting as "add succeeded, commit says
  nothing to commit, Desktop still shows N changed files". Read-only git is fine.

## 7. Known separate issues — not the current lane

Full register with evidence: [`docs/BACKLOG.md`](docs/BACKLOG.md).

* **Test Lab returns a 500.** `scripts/run_test_lab.sh` was archived by `c4ca24e`.
  **Repointing the constant is NOT the fix** — tried at `8e93262`, reverted at `b61f4a8`.
  The archived harness is not location-aware, so repointing returns `{"ok": true}` and the
  child dies in a log. Worse than the loud failure. A bounded task of its own.
* **Narrator composer collapses on a narrow viewport.** `#chatInput` is `flex: 1` with
  default `min-width: auto`; measured 39 px wide × 240 px tall at a 697 px viewport. Needs
  ~500 px of row width. A `min-width` fix was written and **withdrawn unverified** — it may
  clip Send. Open.
* **Test 23 parses and has run; the run came back RED and nobody has adjudicated it.**
  *(This entry said the script "does not parse" — false since `66197c3`, 2026-08-30.
  Corrected 2026-09-08 during the resumed repository-hygiene pass.)* The parse repair and
  the compile gate (`tests/test_scripts_compile.py`, which pins the harness by name) are
  both done. The live run executed 2026-09-04 at `5afead5` on a clean tree and reported
  **RED** for both narrators. Evidence:
  `docs/reports/test23_two_person_resume_test23_v12.md` **(local working copy only —
  `docs/reports/` is gitignored, so this is deliberately not a link)**.
  **Measured:** the run was RED. **Inferred:** its empty `person_id`, empty step tables and
  all-`None` BB state are consistent with the session never establishing. **Unknown:** the
  cause. It is neither a proven product regression nor a proven harness defect.
  Spec: [`docs/wo/BUG-HARNESS-TEST23-INDENTATION-01_Spec.md`](docs/wo/BUG-HARNESS-TEST23-INDENTATION-01_Spec.md).
  **Do not repair or re-run it inside a product lane** — adjudication needs a live stack and
  is its own bounded follow-up.
* Six pre-existing `interview_sessions → people` FK violations from old harness narrators.
* Hard-delete filesystem residue root cause · legacy-column retirement · privacy canon
  extraction and public-history purge · broad `ws_chat`/extract-router decomposition ·
  model, prompt-window, STT, TTS and runtime-safety changes.
* **Bug Panel narrator label** — `_narratorLabel()` read three keys that do not exist on
  `state.session`, rendering `(unnamed)` for every narrator. Fixed `23cbdec`, covered at
  `5e7571c`. Recorded separately and deliberately not counted as lane evidence.

## 8. Required document set

| Document | Purpose |
|---|---|
| `HANDOFF.md` | Current state and next action. Nothing else |
| `MASTER_WORK_ORDER_CHECKLIST.md` | Active / next / deferred coordination |
| `CLAUDE.md` | Durable doctrine and prohibitions |
| `docs/INDEX.md` | Where documentation authority lives |
| `docs/BACKLOG.md` | Unresolved obligations, with evidence |
| `docs/wo/WO-REPOSITORY-HYGIENE-01_Spec.md` | The **closed** repository lane — COMPLETE 2026-09-08 at `e0fde84`. Read for its closeout and its registered residuals only. **Do not reopen repository hygiene** |
| `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md` + `..._PHASE2_TRANSPORT_MAP.md` | The owed Profile Seed lane — Phase 3 implementation landed, acceptance open |
| `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Binding Travel Document rulings |

Historical handoffs and long status narratives live in Git history and `docs/archive/`.
**They must not be appended back into this operational brief.**

## 9. `WO-LORI-ARCHIVE-TO-MEMOIR-02` — Phases 1–4, 5A/5B **and 5C CLOSED**; **Phase 6 (Block D) UNDERWAY** (updated 2026-09-08)

**Phase 3 ACCEPTED 2026-09-05.** Its exit gate is met: Stefi follows the normal turn path,
the three spouse fixtures bind, no false parent field is written, and uncertain
relationships stay reviewable.

The last open clause was proven live rather than argued from source — the Stefi
correction-fallthrough gate `20260905-021741`, **9/9 over the production WebSocket**
(`scripts/stefi_correction_fallthrough_probe.py`). The turn routes as `correction` by the
shipped `app.js` regex, the parser finds nothing actionable, `[correction-fallthrough]`
fires, **no `correction_payload` frame and no `correction-apply`**, an ordinary response is
committed, both turns persist, and a story candidate is **preserved and bound** —
`bf8f41e6`, `user_row=2202`, `assistant_row=2203` — which a deterministic correction turn
never does. That candidate carries no placement, as it must.

**Clean final evaluations, at their recorded SHAs:** `r5k-guard-v2` 71/114 at `5afead5` on a
clean tree, 0 `must_not_write`; `r5k-generational` 7/14 at `4ab00fc`, clean, 0
`must_not_write`.

**What is NOT claimed.** The extraction baseline is not comparable: `r5h`, `r5j` and `r5k`
used **three different scorers** and two of the three ran on dirty trees. The r5h→r5k −7
measures scorer and extractor together. `r5k`'s **0 `must_not_write` is solid current
evidence**; the `2 → 0` delta is **not established** — `must_not_write` is a scorer
judgment. Registered as nonblocking measurement debt in
[`docs/BACKLOG.md`](docs/BACKLOG.md) §6a. **No further Phase 3 evaluation is needed.**

**PHASE 4 ACCEPTED 2026-09-05.** The capture decision is durable on the source narrator
turn, including the declined turns that create no candidate.

| | |
|---|---|
| Implementation SHA | `24c71309aa3dd3d73e58811cfec7b1359b670167`, clean tree |
| Live probe | `20260905-151658` — `scripts/story_capture_decision_probe.py` |
| Interpreter (live) | `.venv-gpu/bin/python`, the serving venv |
| Interpreter (offline) | `.venv/bin/python` — **241 tests, `OK`, ZERO skips** |
| Live result | **11 passed, 0 failed, 0 unverified** |
| Mutations | **8/8 caught**, product restored byte-exact |

Nominated turn: `borderline_scene_anchor`, candidate `8a159445`, bound to the same source
conversation. Declined turn: `below_all_capture_paths`, `candidate_id: null`, full eight-field
diagnostic, **no `story_candidates` row at all**. No narrator or assistant prose in either
record; nothing written to an assistant row.

**Ten of eleven acceptance clauses were proven LIVE. One was not** — `measurement_failed` is
covered by the offline suite and by mutations 3 and 6, but has never been seen on a live
turn, and the record says so.

**Nothing about capture changed.** No threshold, anchor regex, chain classifier, source unit,
review rule, memoir behaviour, migration or new table. The 114/14 extractor banks were
deliberately not rerun — Phase 4 changed observability, not extraction.

**One branch records nothing deliberately:** a trigger firing with no `person_id` fits none of
the three closed outcomes, so it stays an existing exclusion with the log line as its record,
pinned by a test. Opening the vocabulary is Chris's call.

**PHASE 5A AND 5B ARE COMPLETE 2026-09-05, review open.** Kinship normalization now retains
the narrator's own word: `ExtractedItem` carries `source_phrase` and `normalized_from`, and
one vocabulary — `server/code/api/services/relationship_interpreter.py` — decides every
relationship reading, with the kinship guard's per-role patterns DERIVED from it rather than
maintained beside it. That duplication is what let `mama` bind while `daddy` did not.

**The governing rule this phase installed:** *the model proposes an interpretation; the
NARRATOR'S WORDING decides which lane is legal.* The deliberately crossed passage — the
current wife proposed as prior partner, the ex-wife as current spouse — is corrected rather
than obeyed.

| Measured at the production boundary | |
|---|---|
| `tests.test_spouse_state_characterization` + `tests.test_kinship_qualifier_binding` | **74 tests, ZERO skips** |
| with the Phase 4 / 5A suites and the gate classifier | **156 tests, ZERO skips** |
| mutation gate `L1`–`L9` (checked in, reproducible) | **9/9 caught behaviourally**, 7 marked `was_real` |
| `node tests/test_family_tree_spouse_edge_types.js` | 26 checks, 2 call sites wired |
| 19 extraction-adjacent modules, 600 tests | failure set **byte-identical to the same modules at `HEAD` product code** |
| Interpreter | **agent sandbox `python3` only.** `.venv` is the verification and it is Chris's run |

**Four defects were found at the production boundary, and every one was invisible to a
helper-level test:** `getattr(req, "conv_id")` on a request that has no such field, so
production wrote null provenance while the real `session_id` sat unused; an `ExtractedItem`
constructor that names its kwargs, silently dropping the recorded narrator phrase one call
before the pass that needed it; a lane chosen by the *canonicalized* value, where `wife`
occurs twice and Mary's comes first; and grouping that runs before the lane pass, so moved
items reached callers with no person association while a comment claimed otherwise.

**What 5B does NOT claim.** No live turn was run — everything is offline against the shipped
path. `STATE_DECEASED` is recorded and consumed by nothing but the Family Tree edge. The
`adult` / `older` / `younger` qualifiers are read correctly and carried to no field; mapping
`older` onto `siblings.birthOrder` would manufacture a fact and was deliberately not done.
The 114/14 banks were not rerun.

**PHASE 5C IS DONE — 2026-09-07, as Block B.** One disposition contract for meaning with no
schema destination, corrected and audited to a truthful Phase 5 exit gate; detail in
`WO-LORI-ARCHIVE-TO-MEMOIR-02` §5C. *(This paragraph read "Phase 5C is QUEUED, not current"
until 2026-09-08. It was written while the measurement block ran first — which it did, and
which is why the "Why before 5C" row in the current-action box is still an accurate
historical rationale — but the
measurement finished, 5C landed, and the queued status did not follow.)* **The prohibition
it carried is unchanged and still binds: do not disable
`HORNELORE_CLAIMS_VALIDATORS` as a product fix** — it gates several safeguards while leaving
the parse-time whitelist active, and two of the three arity-crash paths found in 5B were that
flag's own branches.

**Phase 3's last open box is CLOSED (`a62bfeb`).** *Jim binds as Pat's husband* — `Jim`
had no test anywhere while `Otis` had five and `Domingo` two. `TheJimCase` now drives the
shipped `run_field_extraction` with Pat's own wording, with a positive spouse control.
**The guard was already correct; the coverage was missing.**

## 9a. Phase 1 and Phase 2 — the earlier record (2026-09-04)

> **The working detail that used to live here has been REMOVED, not lost.** It described a
> target that was unplaced at `review_version: 1`, preview and export unproven, and a "fresh
> run, no `--resume`" instruction — every one of which became false when the mutations
> landed, and one of which would have driven a fresh run against a promoted candidate.
> **A current-state document must not carry executable orders that have expired.** The full
> record, including all seven defects found while proving the chain, is in
> [`docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md`](docs/wo/WO-LORI-ARCHIVE-TO-MEMOIR-02.md);
> the runs themselves are under `.runtime/eval/phase1-memoir-chain/`; Git holds the rest.

**Accepted on two runs, and the split is the claim:**

| Run | What it did | Mutations |
|---|---|---|
| `20260904T123556Z` | performed the **only two authorized mutations** — placement `v1→v2`, then promotion `v2→v3` | **2** |
| `20260904T130525Z` | **carried that proof forward** and completed preview and export | **0** |

Exit **0**, `Phase 1: PASS — full chain proven`. Agreement canonical **1** / preview **1** /
DOCX **1**. Control `5a56f942` **item identical — the changing `fetched_at` envelope
excluded by design**. `containsSourceId: false`; `forbidden: []`.

**Current target state:** `447eee18` is `promoted`, `building_years`/`operator_set`,
`review_version: 3`. **No further mutation is authorized.** There is no pending live run.

**Gates at acceptance:** 141 Python tests (zero skips on `.venv`) and **four** DOM suites —
launcher, memoir popover, placement workflow, row selection.

## 10. Memory Integrity Layer — design thread, nothing scheduled

A guardrail audit ran alongside Phase 1. **No work order exists and nothing here is
approved.** Recorded so the thread is not lost or mistaken for a plan.

**What is real in the tree today:** `lori_response_guards.py` is 1,294 lines exposing
**7 `detect_` / 7 `repair_` pairs** — every detector has a repair partner. It contains **no
environment gate: the response guards are unconditional.** Do not assume they behave like
runtime safety, which is PARKED behind a decision.

**Known gaps, both with specs or diagnoses, neither scheduled:**

- **Stub collapse** — detection and `compose_stub_collapse_repair()` both exist in
  `lori_communication_control.py`, outside the unconditional detect/repair family. The
  repair runs only with the enclosing communication-control layer. The open work is to
  evaluate its benefit and false-positive rate, reconcile the stale root spec, and decide
  whether it belongs in the common response-guard architecture — not to build a missing
  repair.
- **Few-shot exemplar leakage** — `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md` **at the repo
  root**. Its own status line reads **`ACTIVE / NEXT (deferred until after stub-collapse +
  harness G4 ports land)`** — so the repo already sequences stub-collapse first, and that
  dependency is the spec's, not a preference. Proposes placeholder examples plus
  `detect_exemplar_leak()`.
  *(A search scoped to `docs/wo/` misses it. Legacy `BUG-*_Spec.md` files still sit at the
  root awaiting the archive cohort — see `CLAUDE.md`.)*

**The design position reached, for whoever writes the work order:**

> We do not want a weaker Lori. We want a knowledgeable Lori with a disciplined boundary
> between *what I know about the world* and *what I know about you*.

The constraint is on **attribution, not on knowing**. World knowledge predicated of the
world is allowed and is one of Lori's main assets for cueing recall; an ungrounded specific
predicated of *the narrator* is not. The proposed guard is
`detect_ungrounded_personal_claim`, and its acceptance pair is: *"Bismarck was a much
smaller city then"* must PASS, *"You stopped in Flagstaff"* must FAIL. **A guard that cannot
separate those two is not ready** — and over-applying this rule produces the intake-clerk
failure `CLAUDE.md` principle 8 exists to prevent.

**Still unmeasured, and the next evidence task:** the first complete raw-vs-delivered Walt
trace has already shown post-generation damage, but the nine layers still lack per-guard
false-positive rates across a broader cohort. Use the trace for per-guard fire rates plus a
judged sample. The guards were tuned against **synthetic** narrators, so any synthetic
cohort number is a floor, not an estimate.
