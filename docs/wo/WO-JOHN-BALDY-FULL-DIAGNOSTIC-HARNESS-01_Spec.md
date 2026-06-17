# WO-JOHN-BALDY-FULL-DIAGNOSTIC-HARNESS-01 — Expanded v3

## Correction

The earlier small spec was not enough. The long-narration harness family and the seven-era backend harness must be part of the John Baldy diagnostic itself, not merely mentioned as separate commands.

This WO defines a single expanded runner:

```text
scripts/run_john_baldy_full_diagnostic_harness.py
```

It produces:

```text
docs/reports/john_baldy_full_diagnostic_<timestamp>.md
docs/reports/john_baldy_full_diagnostic_<timestamp>.json
```

## Why this exists

The first John run was invalid because the harness put operator instructions into John’s mouth:

```text
John:
Lori, Life Map era: Earliest Years.
John Baldy was born...
Write one warm factual Life Map entry...
```

That is not a narrator turn. It caused Lori to speak about John in third person, polluted transcript/extraction, and made the run invalid.

The corrected harness must test the system without contaminating the transcript.

## Phase 0 — Bad-run evidence scan

Inputs:

```bash
--bad-run-transcript <path>
--operator-log <path>
```

Detects:

- `Lori, Life Map era:` inside narrator/user transcript
- `Write one warm factual Life Map entry`
- third-person facts sent as narrator text
- fake John person id
- operator health RED
- VRAM truncation
- safety false-positive hints

## Phase 1 — Unit/regression tests

Runs:

```bash
python -m unittest tests.test_lori_communication_control -v
python -m unittest tests.test_compose_memory_echo_spanish -v
python -m unittest tests.test_bio_questionnaire_writer -v
```

These are required because the John run depends on:

- communication control
- Spanish/English locale behavior
- questionnaire truth write/read behavior

## Phase 2 — Harness inventory

Verifies the repo has the expected harness surface:

```text
scripts/harness_lib.py
scripts/run_seven_era_walk_harness.py
scripts/run_jake_long_narration_harness.py
scripts/run_shatner_long_narration_harness.py
scripts/run_alex_they_long_narration_harness.py
scripts/run_richard_late_coming_out_harness.py
scripts/run_pat_teacher_betty_harness.py
scripts/run_regional_african_american_georgia_harness.py
scripts/run_regional_asian_american_california_harness.py
scripts/run_regional_native_american_new_mexico_harness.py
scripts/run_regional_crypto_jewish_new_mexico_harness.py
```

Also verifies `scripts/harness_lib.py` contains the 8-row scoring matrix:

```text
reflection_grounded
one_question_max
no_questionnaire_interrogation
no_forbidden_empathy_openers
no_era_label_menu
no_same_anchor_loop
word_budget_honored
translation_refusal_absent
```

## Phase 3 — Seven-era Life Map backend harness

Runs by default:

```bash
python3 scripts/run_seven_era_walk_harness.py
```

Purpose:

- exercise all canonical era ids
- prove runtime71 era handoff works independent of Chrome UI
- expose era-specific Lori behavior
- collect its own report into the final John diagnostic report

Canonical eras:

```text
earliest_years
early_school_years
adolescence
coming_of_age
building_years
later_years
today
```

## Phase 4 — Long-narration harness family

Default runs the Jake reference harness:

```bash
python3 scripts/run_jake_long_narration_harness.py
```

With `--full-family`, run every available persona harness:

```bash
python3 scripts/run_shatner_long_narration_harness.py
python3 scripts/run_alex_they_long_narration_harness.py
python3 scripts/run_richard_late_coming_out_harness.py
python3 scripts/run_pat_teacher_betty_harness.py
python3 scripts/run_regional_african_american_georgia_harness.py
python3 scripts/run_regional_asian_american_california_harness.py
python3 scripts/run_regional_native_american_new_mexico_harness.py
python3 scripts/run_regional_crypto_jewish_new_mexico_harness.py
```

These are not side tasks. Their return codes and generated reports are harvested into the John report.

## Phase 5 — Test Lab

Default:

- verify `scripts/run_test_lab.sh` exists
- do not run full matrix unless explicitly requested

Optional:

```bash
--test-lab-dry-run
--test-lab-full
```

## Phase 6 — Canonical John Baldy preflight

Reads:

```text
GET /api/bio-builder/questionnaire?person_id=d11572d4-57a1-4100-8426-cfd7293a7441
```

Verifies:

- John identity present
- `military.served` is false/empty
- warns if bad fake John id exists

Canonical John:

```text
d11572d4-57a1-4100-8426-cfd7293a7441
```

Known bad fake John from first bad run:

```text
5de235a9-a2f6-4d2a-b3c1-0731db5d0b20
```

## Phase 7 — Corrected John Baldy Life Map backend diagnostic

Sends first-person John turns over `/api/chat/ws` with `runtime71.current_era`.

Never sends operator directives as narrator.

Bad:

```text
Lori, Life Map era...
Write one warm factual Life Map entry...
John Baldy was born...
```

Good:

```text
I was born on December 31, 1960, in West St. Paul, Minnesota...
```

Checks each era for:

- Lori response present
- no third-person John/he framing
- no invented details
- no veteran/military-service error
- no VRAM truncation
- no Traceback / 500
- no safety false positive
- no Spanish/English misfire

## Phase 8 — Report harvest

After every external harness run, the runner checks `docs/reports/` for newly written reports and embeds report paths/snippets into the John Baldy report.

## Commands

Quick:

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/run_john_baldy_full_diagnostic_harness.py --quick
```

Default useful run:

```bash
python3 scripts/run_john_baldy_full_diagnostic_harness.py \
  --bad-run-transcript docs/reports/transcript_switch_mqif3.txt \
  --operator-log docs/reports/OPERATOR-LOG-2026-06-17-18-54-54.md
```

Full family run:

```bash
python3 scripts/run_john_baldy_full_diagnostic_harness.py \
  --full-family \
  --bad-run-transcript docs/reports/transcript_switch_mqif3.txt \
  --operator-log docs/reports/OPERATOR-LOG-2026-06-17-18-54-54.md
```

With Test Lab dry run:

```bash
python3 scripts/run_john_baldy_full_diagnostic_harness.py \
  --full-family \
  --test-lab-dry-run \
  --bad-run-transcript docs/reports/transcript_switch_mqif3.txt \
  --operator-log docs/reports/OPERATOR-LOG-2026-06-17-18-54-54.md
```

## Commit

```bash
cd /mnt/c/Users/chris/hornelore

git add scripts/run_john_baldy_full_diagnostic_harness.py docs/wo/WO-JOHN-BALDY-FULL-DIAGNOSTIC-HARNESS-01_Spec.md

git commit -m "$(cat <<'EOF'
harness: expand John Baldy diagnostic across live harness family

Adds one full diagnostic runner for John Baldy that treats the existing
long-narration harness family and the seven-era Life Map backend harness
as first-class phases, not side notes.

The runner inventories harness_lib.py, verifies the shared 8-row scoring
matrix, runs unit/regression tests, runs the seven-era backend harness,
runs Jake by default and the full persona family with --full-family,
checks Test Lab availability, scans bad-run evidence files, verifies
canonical John Baldy, then runs a corrected first-person John Life Map
diagnostic.

The John phase forbids the bad first-run pattern where operator
directives like "Lori, Life Map era..." were sent as John, contaminating
the transcript and causing Lori to speak about John as if absent.

Outputs one Markdown report and one JSON artifact under docs/reports/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```
