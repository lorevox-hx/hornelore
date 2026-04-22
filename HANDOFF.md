# Hornelore — Laptop Handoff

This document is a step-by-step bring-up so you can clone Hornelore on a fresh laptop, run it, and share changes back. It assumes Windows + WSL2 + an NVIDIA GPU (preferably RTX 50-series Blackwell to match the production setup).

> **TL;DR if everything is already set up:** `cd /mnt/c/Users/chris/hornelore && bash scripts/start_all.sh`

---

## Current state (as of 2026-04-22 afternoon, r5f ADOPTED)

**Authoritative for current-day state:** `CLAUDE.md` (agent env + standard blocks + changelog) and `docs/reports/LOOP-01_R5.5_WEEKLY_CHECKLIST_20260421.md` (phase 1 week plan, decision gates). Read those first. This section is a compact delta pointer.

### Active phase — LOOP-01 R5.5 Pillar 1, r5f locked as floor

**r5f ADOPTED, new active baseline.** 69/104, v3=41/62, v2=35/62, mnw=2. WO-EX-SILENT-OUTPUT-01 Phase 1 (instrumentation-only) + Phase 2 (parser preamble-tolerance one-liner) landed today; composite blew through the three-agent prediction of 61–63 by +6, zero newly-failed cases, zero scorer drift on any of the 10 pass-flips. Prior floor r5e1 (59/104) retired.

### Active baseline

**r5f: 69/104 · v3=41/62 · v2=35/62 · mnw=2.** Known offenders (pre-existing r5e1 carryover, unchanged): `case_035` (faith turn, narrator `education.schooling` leak) and `case_093` (spouse-detail, `education.higherEducation` leak). Both fall squarely in the WO-LORI-CONFIRM-01 target class. Parked as known cost. Method distribution: 97 llm / 6 fallback / 1 rules_fallback. parse_success_rate=93.3%, parse_failure_rate=0.0%, truncation_rate=0.0%. Stubborn-pack primary sub-pack: 4/4 passed (100%). The ATTRIBUTION-BOUNDARY flag + NARRATIVE + PROMPTSHRINK flags all remain in-tree default-off; live behavior is the r5f composite only.

### Today's landed work (2026-04-22)

**Phase 1 — silent-output instrumentation** (`extract.py` L6609–6927):

- Five counters + terminal `[extract][silent-root]` log classifying silent events into `llm_empty` / `parse_drop` / `validator_drop` / `fallback_miss` / `rules_filter_drop`.
- Raw-output dump gated behind default-off `HORNELORE_SILENT_DEBUG=1`.
- `scripts/run_silent_output_probe.py` + 5-case diagnostic pack (case_005/045/065/077/081) = `probe_01`. Characterization: **`parse_drop` dominant, 4 of 5 silent events** — LLM was returning text, parser was rejecting it.
- Code-review finding (not gating): `fallback_miss` branch in the cause cascade is logically subsumed by branches 1–3; residual always falls to `rules_filter_drop`. Naming is aspirational. Worth a TODO to tighten later if the classifier ever needs to distinguish "validator dropped everything AND fallback produced nothing" from "rules filter subsequently dropped surviving items."
- Zero extractor-behavior change.

**Phase 2 — parser preamble-tolerance salvage patch** (`extract.py` L3481–3485):

- One-line tolerance fix in `_parse_llm_json`: replaces strict `if not text.startswith("["): return []` with `text = raw.lstrip(); bracket_idx = text.find("["); if bracket_idx == -1: return []; text = text[bracket_idx:]`.
- Handles LLM preamble-wrapped truncated JSON (e.g., `"Here is the extracted JSON array:\n\`\`\`\n[\n  {..."`). Byte-identical when `raw` starts with `[` or contains no `[`. Existing brace-balanced `_salvage_truncated_array` walker does the rest.
- `probe_02` (same 5-case pack): **0/5 → 2/5 pass, avg 0.140 → 0.620**. 4 of 5 silent events flipped `parse_drop` → successful parse. New `validator_drop` signal on case_077 `great_grandparents.*` + case_081 `grandparents.ancestry` — maps exactly to pending **#119 turnscope `allowed_branches` fix for greatGrandparents subtree**, which now has fresh evidence.

**r5f master eval — ADOPTED** (`docs/reports/master_loop01_r5f.{json,console.txt}`):

- **Topline:** 59→69/104 (+10), v3 38→41/62 (+3), v2 32→35/62 (+3), mnw 2→2 (unchanged, same offenders).
- **Newly passed (10):** `case_005, 023, 025, 064, 072, 077, 082, 085, 086, 103` — all with `r5e1_cats ∈ {schema_gap, field_path_mismatch, llm_hallucination}` → `r5f_cats=[]`.
- **Newly failed (0).**
- **Score up (still same bucket):** `case_045, 046, 065, 066, 080, 084` (0.00 → 0.33–0.60).
- **Score down:** `case_091` 1.00→0.80 (v3 still pass, v2 flipped via `noise_leakage` — patch-attributable, acceptable cost of recovering salvaged items); `case_068` 0.53→0.00 (LLM stochasticity, not patch-attributable — r5e1 already parsed cleanly, preamble-tolerance path never fired).
- **Scorer-drift audit on all 10 flips: zero drift.** Truth-zone totals identical r5e1↔r5f on every flip; only `hit` counts rose and `miss` counts fell.
- **Method dist:** 97 llm / 6 fallback / 1 rules_fallback. parse_success 93.3%, parse_failure 0.0%, truncation 0.0%.
- **Stubborn primary:** 4/4 (`case_008, 009, 018, 082`).
- **Invalid-fieldpath hallucinations top-10** concentrated on greatGrandparents/parents/grandparents schema_gap cluster (`case_028` 8 offenders, `case_033` 5, `case_039` 3) — exactly #119's target class.

**Git hygiene gate codified in CLAUDE.md** — new top-level section between "Stack ownership" and "Standard eval command". Tree must be clean before any code-changing work begins; agent flags dirty tree and produces copy-paste commit plan before touching code. Code commits isolated from docs; specific-path `git add` (never `-A`); `.runtime/` exception. Trigger: today's 13-item uncommitted pile-up (overnight WO batch + r5e1 reports + Phase 1 instrumentation + tagging audit all tangled into one `git status`).

### Next sequence (reordered 2026-04-22 afternoon after r5f ADOPT)

1. **#119 turnscope `allowed_branches` fix** — promoted to top of queue. Now has **both** probe_02 evidence (validator_drop on `great_grandparents.*` / `grandparents.ancestry`) **and** r5f master evidence (hallucination top-10 is `case_028` 8 offenders / `case_033` 5 / `case_039` 3, all in the greatGrandparents/parents/grandparents schema_gap cluster).
2. **SECTION-EFFECT Phase 3** (#95) — causal matrix, WO already written.
3. **SPANTAG** (#90) — full WO already written, implementation unblocks after Phase 3.
4. **WO-LORI-CONFIRM-01** — v1 scope = 3-field confirm pass (`personal.birthOrder`, `siblings.birthOrder`, `parents.relation`); date-range descoped to v1.1 conditional on #111 corpus expansion.
5. **WO-INTAKE-IDENTITY-01** (Chris's lane) — v3 spec ready. Execution-order note: grep-for-partial-DOB-consumers must precede endpoint implementation; new `normalize_dob_intake` function must be isolated from existing `_normalize_date_value` (Patch H / Fix C reference it).

### Today's commits (2026-04-22)

| SHA | What |
|---|---|
| Phase 1 | WO-EX-SILENT-OUTPUT-01 Phase 1 instrumentation + probe_01 artifacts |
| Overnight | WO batch — SECTION-EFFECT Phase 3 WO + SPANTAG full WO + MULTITURN spec + LORI prep pack + multiturn pilot JSON |
| Corpus | r5e1 corpus analysis — tagging audit + failure clusters |
| Docs | NARRATIVE-FIELD Phase 4 + CLAUDE.md Git hygiene gate |
| Phase 2 | WO-EX-SILENT-OUTPUT-01 Phase 2 salvage-preamble-tolerance patch + probe_02 artifacts |
| r5f ADOPT | `docs/reports/master_loop01_r5f.{json,console.txt}` + baseline lock commit |
| (pending) | HANDOFF + CLAUDE.md changelog updates reflecting r5f ADOPT (this commit) |

Yesterday (2026-04-21): `ad52e4a` (r5e1 eval), `bfefe8b` (NARRATIVE-FIELD Phase 4 r5e2), `c24efa9` (r5e2b tighten), `d2cfb31` (revert NARRATOR-IDENTITY), `74f7b0d` (date-range preference), `291cbb8` (CLAIMS-02 role-exempt), `9706a87` (SCALAR CO-EMISSION + NARRATOR-IDENTITY), `3fec639` (narrative Phase 2 tighten), plus r5e2 REJECT + ATTRIB_BOUNDARY flag.

### Where to pick up on laptop

1. Pull latest `main` once desktop pushes.
2. Read `CLAUDE.md` → operational env, standard eval block, full changelog (most recent: 2026-04-22 afternoon r5f ADOPT).
3. Read `docs/reports/master_loop01_r5f.json` + `.console.txt` for the r5f audit numbers; compare to `master_loop01_r5e1.*` for the flip diff.
4. Read `docs/reports/LOOP-01_R5.5_WEEKLY_CHECKLIST_20260421.md` → week plan + updated decision records.
5. Read `docs/reports/FAILING_CASES_r5e1_RUNDOWN.md` for the 45-case Q/A/era/issue rundown (still relevant; most of the 35 remaining r5f failures are a subset of this).
6. Read `docs/reports/question_bank_tagging_audit.md` + `docs/reports/silent_probe_01.json` + `docs/reports/silent_probe_02.json` for the silent-output lane context.
7. Read `WO-LORI-CONFIRM-01_PREP_PACK.md` + `WO-EX-SECTION-EFFECT-01_PHASE3_WO.md` + `WO-EX-SPANTAG-01_FULL_WO.md` for the three queued lanes.
8. Next extractor-lane work is **#119 turnscope greatGrandparents fix** — smallest surgical patch on the strongest-evidence target.

### Known carryover (unchanged)

- **`parents.education` schema contradiction** — path IS in schema table at `server/code/api/routers/extract.py` L327 (`writeMode: suggest_only`); alias at L3711 maps it to `parents.notableLifeEvents`. Prompt warnings claiming "that path does not exist" are literally false. Fix options for later: (1) hard-delete schema entry, (2) ensure alias fires before scoring, (3) extractor-layer attribution filter. Deferred.
- **`faith.significantMoment` thematic routing** — doesn't trigger from `target=faith.denomination` on case_035. Turn-purpose signal too weak to override "mother" subject binding. A SPANTAG / WO-LORI-CONFIRM-01 class of fix, not a prompt fix.
- **`family.children.*` misroute on sister** — case_035 sister Verene still routes to `family.children.*`. Pre-existing relation-router bug.
- **`fallback_miss` cause-cascade branch** (new today) — logically unreachable under current counter logic; residual falls to `rules_filter_drop`. Not a correctness bug; naming tightening can wait until it matters.

### Stack ownership reminder

Chris owns start/stop of the stack (`scripts/start_all.sh` / `scripts/stop_all.sh`). Cold boot is ~4 minutes (HTTP listener ~60–70s, then 2–3 min model warmup). Do NOT include restart commands in agent-issued eval blocks. API is assumed running at `localhost:8000` when evals are requested.

### Git hygiene gate reminder (new today)

Before any code-changing work starts, the tree must be clean (`git status` shows nothing uncommitted). If dirty when new code work is requested, agent's first action is to flag it and produce a copy-paste commit plan — not start the code work. Group commits with code isolated from docs; use specific file paths (never `git add -A` / `git add .`); exception only for `.runtime/` throwaways. Full rule in `CLAUDE.md`.

---

## Rolling summary (as of 2026-04-18)

This section is a rolling summary of what's been shipped recently and what's still in-flight. If you're coming back after time away, read this first. For the full work order checklist with statuses, baselines, and priority sequence, see `docs/Hornelore-WO-Checklist.md`.

### Recently shipped (committed)

| # | Work order | What it is | State |
|---|---|---|---|
| 1 | **WO-EX-01C** | Narrator-identity subject guard + strict section-only birth-context filter | Live-proven; closed "west Fargo → placeOfBirth" and "Cole's DOB → narrator DOB" bugs |
| 2 | **WO-EX-01D** | Field-value sanity blacklists (US state abbr for lastName, stopwords for firstName) | Live-proven; closed "Stanley/ND" and "and/dad" token-fragment bugs |
| 3 | **WO-LIFE-SPINE-05** | Phase-aware question composer over `data/prompts/question_bank.json` | Shipped, flag OFF, content ready |
| 4 | **WO-EX-VALIDATE-01** | Age-math plausibility validator | Shipped, flag OFF |
| 5 | **WO-EX-SCHEMA-01** | `family.*` + `residence.*` field families + repeatable entity support | Live-proven; unblocked CLAIMS-01 |
| 6 | **WO-EX-SCHEMA-02** | 35 new fields (7 families), ~50 aliases, 7 prompt examples | Live-proven; 104-case eval |
| 7 | **WO-EX-CLAIMS-01** | Dynamic token cap (128→384), position-aware grouping, 20 aliases | Live-proven; 22/30 (73.3%) |
| 8 | **WO-EX-CLAIMS-02** | Quick-win validators + refusal guard + community denial | Live-proven; 114 unit tests, flag ON |
| 9 | **WO-EX-REROUTE-01** | Semantic rerouter: 4 high-precision paths | Live-proven; 104-case eval |
| 10 | **WO-GREETING-01** | Backend endpoint + frontend. Memory echo triggers (5→14 phrases). | Live-tested 2026-04-16 — all 3 narrators |
| 11 | **WO-QB-MASTER-EVAL-01** | 62→104 cases, v2/v3 scoring, filters, atomic writer | Live-tested; baseline 56/104 |
| 12 | **WO-EX-GUARD-REFUSAL-01** | Topic-refusal guard + community denial patterns | Live-tested; 0 must_not_write. Fixes 094/096/097/100 |
| 13 | **WO-QB-GENERATIONAL-01** (content) | 4 decade packs, present_life_realities, 5 new fields, 14 eval cases | Live-tested; baseline 5/14 |
| 14 | **WO-QB-GENERATIONAL-01B** (Part 1+3) | 6 extraction prompt examples, 2 rerouter rules, scorer collision fix | Live-tested; moved generational 2/14→5/14 |
| 15 | **WO-KAWA-UI-01A** | River View UI | Implementation complete, needs live test |
| 16 | **WO-KAWA-02A** | 3 interview modes, 3 memoir modes, plain-language toggle | Implementation complete, needs live test |

### Regressed / shelved

| Work order | What | Why |
|---|---|---|
| **WO-EX-TWOPASS-01** | Two-pass extraction: span tagger + classifier | Regressed 16/62 vs 32/62 baseline. Token starvation + context loss. Flag OFF. See "Mistakes and lessons" below. |
| **WO-EX-FIELDPATH-NORMALIZE-01A** | Confusion-table-driven field-path normalization | Regressed 32/62→14/62. Answer vs value text mismatch. Reverted. |

### In-flight / ready to implement

| Work order | State | Next action |
|---|---|---|
| **WO-QB-GENERATIONAL-01B** (Part 2) | Specced | Code `_pick_generational_question()` in phase_aware_composer.py — runtime composer wiring, interleave overlays at 1:4 ratio |
| **WO-INTENT-01** | Not specced | **#1 felt bug from live sessions.** Narrator says "let's talk about X" → composer ignores. Spec it next. |
| **WO-EX-DENSE-01** | Not specced | **#1 extraction frontier.** Dense-truth 1/8, large chunk 0/4, good-garbage 5/14. |
| **WO-KAWA-01** | Fully specced, 10 phases | Parallel Kawa river layer. Next: wire LLM into `kawa_projection.py`. |
| **WO-KAWA-02** (remaining) | Phases 4-9 | Storage promotion, chapter weighting, deeper memoir. Depends on KAWA-01. |
| **WO-PHENO-01** | Fully specced | Phenomenology layer: lived experience + wisdom extraction. 3-4 sessions. |

### Backlog (not specced)

| Work order | What | Priority |
|---|---|---|
| **WO-REPETITION-01** | Narrator repeats same content 2-3×, Lori keeps responding | Medium |
| **WO-MODE-01/02** | Session Intent Profiles after narrator Open | Low |
| **WO-UI-SHADOWREVIEW-01** | Show Phase G suppression reason instead of silent drop | Low |
| **WO-EX-DIAG-01** | Surface extraction failure reason in response envelope | Low |

### Priority sequence (updated 2026-04-18)

```
EX-GUARD-REFUSAL-01 (done)
  → QB-GENERATIONAL-01 content (done)
    → QB-GENERATIONAL-01B Part 1+3 (done)
      → INTENT-01 (next — #1 felt bug)
        → EX-DENSE-01 (extraction frontier)
          → QB-GENERATIONAL-01B Part 2 (runtime wiring)
            → KAWA-01 Phase 1
```

### Extraction eval baselines (2026-04-18)

| Suite | Cases | Score | Safety |
|---|---|---|---|
| Master suite | 104 | 56/104 (53.8%) | 1 must_not_write (case_094, known cross-family bug) |
| Contract subset (v3) | 62 | 35/62 (56.5%) | — |
| Contract subset (v2) | 62 | 32/62 (51.6%) | — |
| Generational pack | 14 | 5/14 (35.7%) | 0 must_not_write |
| null_clarify | 7+2 | 9/9 (100%) | Refusal guard healthy |

**Expected after eval case fix (cases 211, 214):** generational should move to ~7/14. Those cases were written before `health.cognitiveChange` and `laterYears.desiredStory` existed; the LLM correctly routes to the new fields but the old case expectations pointed at workaround paths.

### New extractable fields (2026-04-18)

5 fields added by WO-QB-GENERATIONAL-01:

- `cultural.touchstoneMemory` (repeatable) — era-defining events witnessed firsthand
- `health.currentMedications` — medication lists, pill management
- `health.cognitiveChange` — self-reported cognitive changes ("I forget things")
- `laterYears.dailyRoutine` — daily structure and rhythms
- `laterYears.desiredStory` (repeatable) — stories they want told, legacy priorities

### Extraction pipeline order (active)

```
LLM generate
  → JSON parse
    → semantic rerouter (4 rules + touchstone dup + story-priority)
      → birth-context filter
        → month-name sanity
          → field-value sanity
            → claims validators:
                refusal guard → shape → relation → confidence → negation guard
```

### Env flag state

| Flag | Default | Purpose |
|---|---|---|
| `HORNELORE_TRUTH_V2` | 1 | Facts write freeze |
| `HORNELORE_TRUTH_V2_PROFILE` | 1 | Profile reads from promoted truth |
| `HORNELORE_PHASE_AWARE_QUESTIONS` | 0 | Phase-aware question composer |
| `HORNELORE_AGE_VALIDATOR` | 0 | Age-math plausibility filter |
| `HORNELORE_CLAIMS_VALIDATORS` | 1 | Value-shape, relation, confidence validators |
| `HORNELORE_TWOPASS_EXTRACT` | 0 | Two-pass extraction (**REGRESSED — keep OFF**) |

---

## Development history and lessons (2026-04-17 → 2026-04-18)

This section documents what was tried, what failed, what worked, and why — so the next person doesn't repeat mistakes. This covers two intensive sessions with Claude (Anthropic) and ChatGPT (OpenAI) working in parallel.

### The two-AI workflow

Development used two AI assistants simultaneously:

- **Claude** — primary implementation partner. Wrote code, ran tests, committed changes, created specs. Has direct repo access.
- **ChatGPT** — strategic advisor and second opinion. Reviewed eval results, suggested approaches, caught bugs Claude missed. Operates on copy-pasted code and results; no repo access.

This worked well. ChatGPT identified the scorer collision bug (case_203, `hobbies.hobbies` in two truth zones) as a "mechanical harness issue" that Claude then fixed. Claude pushed back on ChatGPT's recommendation to rewrite eval case expectations (cases 201-208) because those cases were *deliberately* written with `currentExtractorExpected: false` — they're future targets, not current failures.

**Lesson:** Two AIs are better than one when they have different roles. The advisor catches things the implementer is too deep to see. The implementer catches things the advisor gets wrong without code access.

### Mistake 1: Two-pass extraction (WO-EX-TWOPASS-01)

**What happened:** Built a two-pass extraction pipeline — Pass 1 tags spans schema-blind, Pass 2 classifies spans into field paths. The idea was to separate "what's a fact" from "where does it go."

**Result:** Regressed from 32/62 to 16/62 (50% worse). Root cause was token starvation — Pass 1 consumed most of the context window tagging spans, leaving Pass 2 with insufficient context to classify accurately. The schema-blind span tagger also lost the extraction prompt's field-path examples, which turned out to be critical for routing accuracy.

**Compounding error:** The `HORNELORE_TWOPASS_EXTRACT=1` flag was accidentally left ON in `.env` during the 04-17 eval run. This meant the baseline numbers from that eval were artificially low (the two-pass pipeline was running instead of single-pass). The flag was discovered and set to 0 on 04-18.

**Lesson:** Flags that regress must be immediately set to 0 in `.env.example` AND the local `.env`. A regressed feature running silently behind a flag you forgot about will poison all subsequent measurements.

### Mistake 2: Field-path normalization (WO-EX-FIELDPATH-NORMALIZE-01A)

**What happened:** Built a confusion-table-driven normalizer that would remap commonly-misrouted field paths to their correct destinations. For example, if the LLM routes "we moved to Bismarck" to `laterYears.significantEvent`, the normalizer would check the *answer text* for location cues and reroute to `residence.place`.

**Result:** Regressed from 32/62 to 14/62 (56% worse). The normalizer checked the LLM's `value` field, not the original `answer` text. But the LLM's value is a cleaned extraction (e.g., "Bismarck" not "we moved to Bismarck"), so the cue phrases that the confusion table depended on were absent.

**Lesson:** Rerouter rules must check the narrator's original answer text (`answer` field), not the extracted value. This insight directly informed the successful semantic rerouter (WO-EX-REROUTE-01) which always operates on `answer_lower`.

### Mistake 3: Stale eval cases (211, 214)

**What happened:** Eval cases 211 and 214 were written before `health.cognitiveChange` and `laterYears.desiredStory` existed as extractable fields. The LLM was correctly routing narrator answers to these new fields, but the eval cases expected the old workaround paths (`hobbies.personalChallenges` and `additionalNotes.unfinishedDreams`).

**Result:** These cases showed as failures even though the extractor was doing the right thing. The fix was to update the cases to expect the correct new fields and move the old paths to `may_extract`.

**Lesson:** When you add new extractable fields, audit existing eval cases that cover similar narrator content. The LLM will discover the new fields before your test expectations do.

### What worked: Extraction prompt tuning (01B Part 1)

Added 6 few-shot examples to the extraction prompt teaching the LLM how to handle generational-era answer styles:

1. Moon landing touchstone → `cultural.touchstoneMemory` + `laterYears.significantEvent`
2. Gas lines with place → `laterYears.significantEvent` + `residence.place`
3. Medications list → `health.currentMedications`
4. Cognitive self-report → `health.cognitiveChange`
5. Elder frustrations → `laterYears.dailyRoutine`
6. Desired story list → `laterYears.desiredStory` (multiple items)

Each example includes routing notes explaining *why* the field path is correct. This moved the generational pack from 2/14 to 5/14.

### What worked: Semantic rerouter rules (01B Part 3)

Two new rerouter rules with pattern-based gating:

**Rule 5 — Story-priority reroute:** When the narrator uses language like "want my family to hear" or "before it's too late," reroutes `additionalNotes.unfinishedDreams` or `laterYears.lifeLessons` → `laterYears.desiredStory`.

**Rule 6 — Touchstone duplicate:** When the answer contains both a touchstone event keyword (moon landing, Vietnam, 9/11, etc.) AND a witness-memory cue ("I remember," "we watched," "sitting in the living room"), ADDS a `cultural.touchstoneMemory` duplicate alongside the existing `laterYears.significantEvent`. This is an ADD, not a replace — both field paths are populated.

**Witness-memory cue gate (3-signal requirement):** ChatGPT recommended gating the touchstone rerouter to prevent false positives on personal events that mention historical periods ("my son was born during COVID"). The gate requires all three: touchstone event keyword + `laterYears.significantEvent` route + witness-memory cue in the answer text. Tested against all 14 generational cases — zero false positives.

### What worked: Scorer collision fix

**Bug:** Case 203 has `hobbies.hobbies` in both `must_extract` and `should_ignore` truth zones (intentionally — the same field path can be a valid extraction AND have noise that should be ignored). The scorer's flat dict used `fieldPath` as key, so the `should_ignore` entry overwrote the `must_extract` entry.

**Fix:** Changed the truthZones builder to use a `_multi` wrapper pattern. When a fieldPath appears in multiple zones, it stores `{"_multi": [{zone, expected}, ...]}` instead of a single entry. The scoring loop unpacks these and scores each zone entry independently.

### Known remaining failures (generational pack)

| Case | Narrator text | What happens | Root cause |
|---|---|---|---|
| 202 | Vietnam era + cousin | LLM hallucinates non-existent field paths | Schema gap — no military/draft field |
| 203 | Drive-in memories | Routes everything to significantEvent | Misses hobbies.hobbies and residence.place |
| 205 | First computers | Routes to education.earlyCareer | Should hit laterYears.significantEvent |
| 206-208 | Various era content | Missing secondary extractions | personalChallenges, lifeLessons not triggered |

These are targets for WO-EX-DENSE-01 (dense-truth extraction frontier).

---

## Testing methodology — 3-terminal standard

This is the standard method for running extraction evals. A separate detailed guide is in the `Workorders and Updates` desktop folder (`Testing-Procedure-3-Terminal.md`).

### Terminal setup

**Tab 1 — Filtered API log** (leave running entire session):
```bash
tail -f /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | grep --line-buffered -E "\[extract\]|\[extract-parse\]|CLAIMS|rerouter|refusal-guard|negation|validator|fallback"
```

**Tab 2 — Eval runner** (run generational first, then master suite):
```bash
cd /mnt/c/Users/chris/hornelore

echo "=== Generational pack ==="
python scripts/run_question_bank_extraction_eval.py \
  --mode live \
  --api http://localhost:8000 \
  --cases data/qa/question_bank_generational_cases.json

echo "=== Full 104-case master suite ==="
python scripts/run_question_bank_extraction_eval.py \
  --mode live \
  --api http://localhost:8000
```

**Tab 3 — General purpose** (git, file inspection, targeted runs):
```bash
cd /mnt/c/Users/chris/hornelore

# Guard cases only
python scripts/run_question_bank_extraction_eval.py \
  --mode live --api http://localhost:8000 \
  --case-ids case_094,case_096,case_097,case_100

# Single narrator
python scripts/run_question_bank_extraction_eval.py \
  --mode live --api http://localhost:8000 \
  --narrator kent-james-horne

# Failed cases from last report
python scripts/run_question_bank_extraction_eval.py \
  --mode live --api http://localhost:8000 \
  --failed-only docs/reports/question_bank_extraction_eval_report.json
```

### What to collect

When a run finishes, save three things:
1. **Tab 2 output** — eval summary with pass/fail counts, truth zone metrics, failed case list
2. **Tab 1 output** — filtered log showing what the extractor actually did
3. **The JSON report** — written automatically to `docs/reports/question_bank_extraction_eval_report.json`

### Key log lines

| Log line | What it tells you |
|---|---|
| `[extract] Attempting LLM extraction for person=..., section=...` | Which narrator and section |
| `[CLAIMS-01] Compound answer detected` | Token cap bumped to 384 |
| `[extract-parse] Raw LLM output (N chars): [...]` | Raw LLM JSON |
| `[extract-validate] REJECT: fieldPath '...' not in EXTRACTABLE_FIELDS` | LLM hallucinated a field |
| `[rerouter] touchstone-dup:` | Touchstone rerouter fired |
| `[rerouter] story-priority:` | Story-priority rerouter fired |
| `[refusal-guard] topic refusal detected` | Refusal guard stripped all items |
| `[negation-guard] denial detected: stripping {...}` | Negation guard stripped items |
| `rules-fallback` | LLM returned nothing valid, fell back to regex |

### Interpreting results

Two scoring layers:
- **v3 (truth zones):** must_extract recall ≥ 0.7 with must_not_write gate. Primary metric.
- **v2 (field avg):** Average field match score ≥ 0.7. Backward-compatible baseline.

Safety gates (must always hold):
- **must_not_write violations: must be 0.** Any violation is a safety regression.
- **null_clarify: must be 7/7 (master) or 2/2 (generational).** Refusal guard health check.
- **Contract subset v2: must be ≥ 32/62.** Regression floor.

---

## Reference docs

| File | What it is |
|---|---|
| `docs/Hornelore-WO-Checklist.md` | Master work order checklist with all statuses and baselines |
| `docs/WO-QB-GENERATIONAL.md` | Generational era-overlay spec |
| `docs/WO-QB-GENERATIONAL-01B.md` | Extraction prompt tuning + runtime wiring spec |
| `docs/CLAIMS-02_failure_taxonomy.md` | Failure root cause analysis + fix priorities |
| `docs/reports/WO-KAWA-UI-01A_REPORT.md` | River View implementation report |
| `docs/reports/WO-KAWA-02A_REPORT.md` | Kawa questioning + memoir integration report |
| `hornelore/WO-KAWA-01_Spec.md` | Full 10-phase Kawa data/engine work order |
| `hornelore/WO-KAWA-UI-01_Spec.md` | Full River View UI work order |
| `hornelore/WO-PHENO-01_Spec.md` | Full phenomenology layer work order |
| `hornelore/WO-SCHEMA-02_Gap-Analysis.md` | Life map coverage expansion |
| `hornelore/Memoir-Upgrade-Phased-Plan.md` | 7-phase memoir system roadmap |
| `docs/references/` | 4 Kawa/OT reference papers + 6 extraction papers + 5 architecture papers |

---

## Test state

114 unit tests across 6 suites, all passing:

```bash
cd /mnt/c/Users/chris/hornelore
source .venv-gpu/bin/activate
python -m unittest tests.test_extract_subject_filters \
                   tests.test_extract_claims_validators \
                   tests.test_life_spine_validator \
                   tests.test_phase_aware_composer \
                   tests.test_interview_opener -v
# Plus integration tests:
python -m unittest tests.test_extract_api_subject_filters -v  # requires FastAPI
```

---

## Known issues from live observation

- ~~**Critical:** question bank references field paths that don't exist in `EXTRACTABLE_FIELDS`.~~ **FIXED** by WO-EX-SCHEMA-01.
- **High:** Lori ignores narrator-stated topic pivots ("let's talk about my parents"). Fix = WO-INTENT-01.
- **High:** Compound sentences produce partial extractions (~8 of 30 eval cases still fail). Fix = WO-EX-CLAIMS-02. Root causes in `docs/CLAIMS-02_failure_taxonomy.md`.
- ~~**High:** Life map coverage gaps — 16 of 37 interview sections have no extraction fields.~~ **FIXED** by WO-SCHEMA-02.
- **Medium:** Narrator repeats same content 2-3×, Lori keeps asking similar follow-ups. Fix = WO-REPETITION-01.
- ~~**Medium:** Lori doesn't introduce herself on session open.~~ **FIXED** — WO-GREETING-01.
- **Low:** Accordion shows DOB year only when canonical has full date.

### Recommended next steps

1. Push outstanding commits and re-run generational pack to verify 7/14 target (case_211/214 fix)
2. Spec WO-INTENT-01 — the #1 felt bug
3. Spec WO-EX-DENSE-01 — the #1 extraction frontier
4. Wire 01B Part 2 — runtime generational question composer
5. Begin KAWA-01 Phase 1

---

## 0. What "Hornelore on the laptop" means

Hornelore is a **single-machine local-LLM** application. There's no cloud component. Everything that matters runs in WSL2 against the Windows-side NVIDIA driver. Three services come up in sequence:

| Port | Service | Process |
|---|---|---|
| 8000 | LLM API (FastAPI + Llama-3.1-8B INT4) | `launchers/hornelore_run_gpu_8000.sh` |
| 8001 | TTS server (Coqui VITS) | `launchers/hornelore_run_tts_8001.sh` |
| 8082 | UI static server | `python3 hornelore-serve.py` |

You open the UI in Chrome at `http://localhost:8082/ui/hornelore1.0.html`.

---

## 1. Prerequisites (one-time per laptop)

### Hardware
- NVIDIA GPU with at least **16 GB VRAM** (RTX 5080 / 4090 / equivalent)
- **128 GB system RAM** is what the production rig has; 64 GB will work; 32 GB is tight
- ≥ 200 GB free SSD space (model weights, HF cache, hornelore_data)

### Drivers
- **NVIDIA driver R570+** (Blackwell GPUs require this; check `nvidia-smi` shows it)
- WSL2 GPU passthrough enabled (run `nvidia-smi` inside WSL — should show the same GPU)

### Software
- Windows 11 with **WSL2** + Ubuntu 24.04 (or current LTS)
- **Python 3.12** inside WSL (Ubuntu 24.04 default)
- **git** + **bash** + **curl** + **sqlite3**
- **Chrome** on Windows side (UI runs in browser)
- A real **HuggingFace token** with access to `meta-llama/Llama-3.1-8B-Instruct` (the model is gated)

### One-time WSL setup
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git curl sqlite3 build-essential
```

---

## 2. Get the code

```bash
mkdir -p /mnt/c/Users/<you>
cd /mnt/c/Users/<you>
git clone <hornelore-remote-url> hornelore
cd hornelore
```

The expected layout:
```
/mnt/c/Users/<you>/hornelore/      ← code (this is the repo)
/mnt/c/hornelore_data/             ← runtime data (DB, uploads, media, test_lab) — created on first run
/mnt/c/Llama-3.1-8B/hf/...         ← model weights cache (downloaded on first API start)
/mnt/c/models/hornelore/hf_home/   ← HF transformers cache
```

Everything under `/mnt/c/hornelore_data/` is **gitignored** and machine-local. It's where your DB and chat archive live; never commit it.

---

## 3. Configure `.env`

The repo has `.env.example` as a template. Copy and edit:

```bash
cp .env.example .env
```

Edit `.env` and set:

| Key | What to set |
|---|---|
| `HUGGINGFACE_HUB_TOKEN` | your real HF token (Llama is gated) |
| `MODEL_PATH` | usually `/mnt/c/Llama-3.1-8B/hf/Meta-Llama-3.1-8B-Instruct` |
| `DATA_DIR` | `/mnt/c/hornelore_data` (or wherever you want runtime data) |
| `MAX_NEW_TOKENS_CHAT_HARD` | `2048` (required for the Quality Harness) |
| `REPETITION_PENALTY_DEFAULT` | `1.1` (production default) |

**Critical:** Make sure `HORNELORE_TWOPASS_EXTRACT` is **0** (or absent). The two-pass pipeline regressed and must stay off. See "Mistakes and lessons" above.

Leave the others at their defaults unless you know why you're changing them.

`.env` is **gitignored** — your changes never leave this laptop. `.env.example` is the tracked template; if you add a new env var, document it there.

---

## 4. Install Python deps

There are two virtualenvs (one for the GPU LLM stack, one for TTS). The launchers in `launchers/` already point at them, but you have to create them first.

```bash
# GPU env (FastAPI, transformers, bitsandbytes, torch)
python3 -m venv .venv-gpu
source .venv-gpu/bin/activate
pip install -r requirements-gpu.txt
deactivate

# TTS env (Coqui VITS, scipy, etc.)
python3 -m venv .venv-tts
source .venv-tts/bin/activate
pip install -r requirements-tts.txt
deactivate
```

If `requirements-gpu.txt` or `requirements-tts.txt` aren't in the repo, see `scripts/requirements.txt` and the launchers for hints.

---

## 5. First start — bring up the stack

```bash
cd /mnt/c/Users/<you>/hornelore
bash scripts/start_all.sh
```

This:
1. Kills any stale Hornelore processes
2. Shows current VRAM
3. Starts the API (waits up to 90s for `/api/ping` health)
4. Waits up to 3 min for the LLM to load and warm
5. Starts TTS (waits for `/api/tts/voices`)
6. Starts the UI server on 8082
7. Opens `http://localhost:8082/ui/hornelore1.0.html` in your default browser

Logs land in `logs/api.log`, `logs/tts.log`, `logs/ui.log`. To tail:
```bash
bash scripts/logs_visible.sh
```

To stop everything:
```bash
bash scripts/stop_all.sh
```

To restart just the API (e.g., after a `.env` or code change):
```bash
bash scripts/restart_api.sh
```

---

## 6. First load — narrators auto-seed

The first time the API starts, `_horneloreEnsureNarrators()` checks the `people` table. If Chris, Kent, or Janice are missing, they're seeded from `ui/templates/`. Reference narrators (Shatner, Dolly) seed via `scripts/preload_trainer.py`:

```bash
python3 -m pip install -r scripts/requirements.txt --break-system-packages
python3 -m playwright install chromium
python3 scripts/preload_trainer.py --all
```

Synthetic test narrators for the Quality Harness seed via:

```bash
python3 scripts/seed_test_narrators.py
```

---

## 7. Running the Quality Harness on the laptop

After the stack is up:

**From the UI** (operator-only):
1. Open Chrome → Hornelore tab
2. F12 → Console → paste: `document.getElementById("testLabPopover").showPopover()`
3. Optionally tick **Dry run**
4. Optionally pick a baseline from the dropdown
5. Click **Run Harness**
6. Watch the Live Console pane
7. Budget 45–90 minutes for a full matrix
8. When status flips to `finished`, pick the new run from "Select run to load"

**From WSL:**
```bash
bash scripts/run_test_lab.sh                              # full matrix
bash scripts/run_test_lab.sh --dry-run                    # plumbing check
bash scripts/run_test_lab.sh --compare-to <prior_run_id>  # regression vs baseline
bash scripts/test_lab_doctor.sh                           # one-shot health check
bash scripts/test_lab_watch.sh                            # terminal live monitor
```

Run artifacts land in `/mnt/c/hornelore_data/test_lab/runs/<run_id>/`.

---

## 8. Running the extraction eval suite

This is separate from the Quality Harness. The extraction eval tests the field-extraction pipeline against known narrator statements with expected field paths.

```bash
# Full 104-case suite
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000

# Generational pack (14 cases, separate file)
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000 --cases data/qa/question_bank_generational_cases.json

# Guard cases only
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000 --case-ids case_094,case_096,case_097,case_100

# Kent only
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000 --narrator kent-james-horne

# Failed cases from prior report
python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:8000 --failed-only docs/reports/question_bank_extraction_eval_report.json
```

Always use the 3-terminal methodology described above when running evals.

---

## 9. Sharing changes back

This repo is the only thing that needs to sync between machines. **Runtime data does not sync.**

### What syncs (via git)
- All code under `server/`, `ui/`, `scripts/`, `data/narrator_templates/`, `data/test_lab/`, `docs/`
- `.env.example`, `requirements*.txt`, launcher scripts
- README + HANDOFF + WO docs

### What does NOT sync (gitignored)
- `.env` (contains your HF token)
- `/mnt/c/hornelore_data/` (DB, uploads, media, test_lab runs)
- `/mnt/c/Llama-3.1-8B/` (model weights)
- `.venv-gpu/`, `.venv-tts/`
- `logs/`

### Push from the laptop
```bash
git add -p                                  # review changes piece by piece
git commit -m "<short-but-specific>"
git push origin main
```

### Pull from the desktop later
```bash
cd /mnt/c/Users/chris/hornelore
git pull origin main
```

If the pull touched `chat_ws.py`, any router, or anything in `server/`, restart the API: `bash scripts/restart_api.sh`. If it touched UI files, hard-reload Chrome (Ctrl+Shift+R). If it touched `.env.example`, manually merge any new keys into your local `.env`.

---

## 10. Common bring-up snags

| Symptom | Likely cause | Fix |
|---|---|---|
| `nvidia-smi` works in PowerShell but not in WSL | WSL GPU passthrough not enabled | Update WSL: `wsl --update` (PowerShell as admin) |
| API hangs on "Waiting for LLM model to become ready" | First-time model download from HF | Watch `tail -f logs/api.log` — should show progress |
| 401/403 from HF | Token missing or doesn't accept Llama license | Get token from huggingface.co, accept Llama-3.1 license |
| Test Lab button missing | Dev mode off | Console: `toggleDevMode()` |
| `Status: failed` after Test Lab run | Stuck status from a previous run | `curl -X POST http://localhost:8000/api/test-lab/reset` |
| 404 on `/api/test-lab/*` | API wasn't restarted after pulling new code | `bash scripts/restart_api.sh` |
| Browser gets 404 on `/api/...` | Cached old `api.js` | Hard-reload (Ctrl+Shift+R) |
| Harness preflight fails with "only N tokens streamed" | `MAX_NEW_TOKENS_CHAT_HARD` not raised | Edit `.env`, restart API |
| PowerShell chokes on multi-line scripts with backslashes | PowerShell doesn't support backslash line continuation | Run in WSL instead |

---

## 11. Quick reference

```bash
# Start everything
bash scripts/start_all.sh

# Stop everything
bash scripts/stop_all.sh

# Restart just the API (after code/env changes)
bash scripts/restart_api.sh

# Tail all logs in separate windows
bash scripts/logs_visible.sh

# Check stack health
bash scripts/test_stack_health.sh
bash scripts/status_all.sh

# Run the Quality Harness (full matrix)
bash scripts/run_test_lab.sh --compare-to <last-baseline>

# Diagnose a stuck Test Lab run
bash scripts/test_lab_doctor.sh

# Open Hornelore
# → http://localhost:8082/ui/hornelore1.0.html
```

For the architecture context behind any of this, see `README.md` for the product surface and file inventory, `docs/wo-qa/WO-QA-01.md` and `WO-QA-02.md` for Quality Harness specs, and the individual WO docs in `docs/` and `hornelore/` for specific work orders.

Welcome to the laptop. Push your changes when you're done; the desktop will pick them up on the next pull.
