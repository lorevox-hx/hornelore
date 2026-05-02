# WO-EX-UTTERANCE-FRAME-SURVEY-01 — Dedicated Story Clause Map Survey Harness

**Status:** READY TO LAND  
**Lane:** Extractor architecture / instrumentation harness  
**Scope:** Harness-only. No runtime behavior change. No UI. No prompt changes. No extractor/Lori/validator/safety consumers wired.

---

## Mission

Create a dedicated survey harness for `WO-EX-UTTERANCE-FRAME-01` Phase 0–2 so we can study the Story Clause Map layer without manually comparing golfball JSON to `api.log` greps.

The current workflow:

1. Run golfball with `HORNELORE_UTTERANCE_FRAME_LOG=1`.
2. Grep `[utterance-frame]` from `.runtime/logs/api.log`.
3. Manually compare the log lines to `docs/reports/golfball-utterance-frame-log-v1.json`.

This WO replaces step 3 with a structured report.

---

## What this harness does

Adds:

```text
scripts/archive/run_utterance_frame_survey.py
```

The harness pairs:

```text
Golfball report turn input
→ direct build_frame(user_text) output
→ live [utterance-frame] log shape from api.log
→ findings / polish recommendations
```

It writes:

```text
docs/reports/utterance_frame_survey_v1.json
docs/reports/utterance_frame_survey_v1.console.txt
```

---

## What it does not do

```text
Does not call the LLM.
Does not call the extractor.
Does not write DB.
Does not modify chat_ws.
Does not wire Lori.
Does not wire validator.
Does not wire safety.
Does not touch UI.
Does not change prompt_composer.py.
```

This is a harness/readout layer only.

---

## Command

From repo root:

```bash
python3 scripts/archive/run_utterance_frame_survey.py \
  --golfball-report docs/reports/golfball-utterance-frame-log-v1.json \
  --api-log .runtime/logs/api.log \
  --output docs/reports/utterance_frame_survey_v1.json \
  --include-probes
```

Optional:

```bash
--conv-id golfball-1777758251
--strict
```

`--conv-id` is normally not needed; the harness auto-selects the most recent matching `conv=` for the report `person_id`.

`--strict` exits nonzero on RED. Normal survey mode exits 0 and records GREEN/AMBER/RED in the report.

---

## Inputs

### Required

```text
docs/reports/golfball-utterance-frame-log-v1.json
.runtime/logs/api.log
server/code/api/services/utterance_frame.py
```

### Optional probes

When `--include-probes` is passed, the harness runs direct `build_frame()` probes for the known misses from the first live survey:

```text
when i was young in spokane my dad worked nights at the aluminum plant
My dad worked nights at the aluminum plant.
I am still here. I just feel tired and scared.
my dad was born in stanley, and i was born in stanley too.
```

---

## Scoring

### GREEN

```text
All golfball turns have paired live [utterance-frame] logs.
No direct build_frame errors.
DB lock delta is 0.
No red/amber frame findings.
```

### GREEN_WITH_POLISH

```text
Frame layer is working, but log summary is too thin or a harmless polish note exists.
Example: object is present in direct frame but not visible in live log shape.
```

### AMBER_WITH_POLISH

```text
Logs exist and stack is stable, but the frame misses an obvious survey anchor.
Examples:
- lowercase spokane/stanley not captured as place
- aluminum plant not surfaced as object
- tired/scared not surfaced as stated feeling
```

### RED

```text
Missing frame logs while flag is on.
Direct build_frame exception.
DB lock delta != 0.
Negated clause emits candidate field hints.
Passive death wish fails to produce self/illness + negation.
```

---

## Known current findings from first live survey

The first live golfball survey showed:

```text
GOOD:
- all 8 golfball turns emitted [utterance-frame]
- DB locks stayed 25 → 25, delta 0
- T01 self/birth@Montreal with personal.placeOfBirth + personal.dateOfBirth
- T02 self/illness@Spokane + parent/work with parents.occupation
- T05 self/illness + neg=1 + hints=-

POLISH / AMBER:
- lowercase spokane missed in T03
- work location summarized as generic plant
- object/feeling not visible in [utterance-frame] log summary
- tired/scared stated feeling not visible in T07
```

This harness should reproduce those findings automatically.

---

## Acceptance

```text
[ ] Harness script lands at scripts/archive/run_utterance_frame_survey.py
[ ] Script py_compile passes
[ ] It reads the golfball report and api.log
[ ] It auto-detects the matching conv_id by person_id
[ ] It pairs all 8 golfball turns to live log lines
[ ] It calls build_frame() directly for each turn
[ ] It emits JSON + console report
[ ] It identifies the known current findings
[ ] It does not require GPU
[ ] It does not call the LLM
[ ] It does not write DB
[ ] It does not modify runtime behavior
```

---

## Next step after report

Use the report to decide the next Phase 0–2 polish patch:

```text
1. lowercase known-place fallback
2. richer log summary: obj=... and feel=...
3. aluminum plant object/place preference if direct frame is not enough
4. stated feeling support for tired/scared if values-aligned
```

Still do not wire consumers until the survey is stable.
