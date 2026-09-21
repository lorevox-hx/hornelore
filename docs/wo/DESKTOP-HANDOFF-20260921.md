# Desktop handoff — 2026-09-21

Written for whoever picks this up on the desktop. It assumes nothing
about what the laptop session remembers.

This is a development deployment. Tenant zero is the operator's own
family, by convenience, and the repository holding that is not the
privacy model. The privacy model is the portable narrator package: a
narrator's story lives in their own record, travels as their own bag,
and goes with them.

---

## 1. What arrived on the USB, and what to do with it

`D:\hornelore_move\packages\` holds freshly exported `.lorevox.zip`
BagIt packages for **three narrators: the operator's own, one parent
narrator, and a ZZ test fixture.** The second parent narrator was not
exported.

Each package carries 65 `data/records/*.jsonl` tables — including
`bio_builder_questionnaires`, `profiles`, `interview_projections`,
`turns`, `sessions` and `people` — plus the file archive, under sha256
manifests over both payload and tags.

**Restore each through the product's own route, not by hand:**

```
POST /api/operator/narrator-package/import/upload
GET  /api/operator/narrator-package/import/{upload_id}     <- READ THIS
POST /api/operator/narrator-package/import/{upload_id}/restore
```

The Operator panel drives exactly those three. **Step two is the
report saying what the restore would change.** Do not skip it: if the
desktop already holds rows for these narrators, this is a merge
decision — which machine has the newer biography, per narrator — and
the report is the only thing that will tell you.

`HORNELORE_OPERATOR_PORTABLE_NARRATOR=1` must be set for those routes
to exist; they 404 rather than 403 when it is not.

The remaining parent narrator is still only on the laptop. If the
desktop becomes the home, export that one too before the laptop's
`hornelore_data` is retired.

**The rich test fixture does not need the USB.** It is committed at
`tests/harness/rich_narrator.py` and
`scripts/make_rich_synthetic_narrator.py --create` rebuilds it against
a running stack in about a second.

---

## 2. Where the work actually stands

The last session repaired four things with focused evidence, and
**located four more without repairing them.** The located ones are the
work.

### Repaired, with evidence

| what | evidence |
|---|---|
| `#33 cc_question_atomicity` deleted answers | same-input regression; 45 tests |
| the rules-fallback kinship guard | live log: `'siblings'` dropped before normalisation |
| one narrator's material reachable in 12 shared prompt constants | denylist regression; assembled-prompt sweep across 5 modes |
| retrieval: plurals, multi-subject, field priority | 20 tests on a rich fictional record |
| authority observation on unchanged turns | 12 tests |

### Located, NOT repaired — this is the queue

**(a) The pronoun lookup passes `None`.**
`prompt_composer.py:4574`:

```python
_arc.load_recent_archive_turns(None, session_id=conv_id, limit=4)
```

`session_root()` needs the person id to build the path, so this
returns zero rows and `recent_text` is empty on every production turn.
Pronoun follow-ups ("her notable life events") have never resolved
live. Measured:

```
person_id=None  ->  0 turns
person_id=REAL  ->  4 turns
```

Two-part fix. Pass the id — then resolve the pronoun to the **most
recently named person**, not every person in the window. Passing the
id alone retrieves 2,723 chars naming three different relatives for a
question about one.

**(b) `#54 profile_seed_delivery` overwrites answers.**
Fired on five of twelve turns in the rich capture, and every time it
deleted the sentence that answered the question and substituted an
onboarding question. Once it replaced a question about a narrator's
mother with *"Did you ever serve in the military?"* — six turns after
he had described his service.

The registry already calls it *"THE LARGEST SINGLE SOURCE OF DAMAGE
MEASURED."*

Narrow it the way `#33` and `#44` were narrowed: it may not replace a
reply that answers the question just asked, and may not ask for a
field already on record or already said this session. Onboarding a
genuinely blank narrator is untouched. **Care is needed** — #54 exists
because the model claimed topics were presented when its visible words
were something else, so weakening it has its own failure mode.

**(c) Per-section accounting still misses fitting turns.**
The *recording* is unconditional now; the budget only *populates*
`BudgetOutcome.sections` when it trims. So the renderer prints
`NOT RECORDED` on a turn that fitted — honest, but not yet the
measurement that was asked for.

**(d) `#24 route_memory_echo` intercepts "what did I tell you
earlier".** It answers deterministically without reaching the model:
`generation_attempted: False`, no stages. So a question about earlier
conversation gets a fixed reply rather than a recall attempt. This sits
next to the separate fact that older turns get shed by the budget.

**(e) Siblings go unaddressed even when supplied.** In the rich
capture every sibling's name was in every prompt and the detail block
was present, and the answer covered the father alone. Retrieval is
fixed; this is model selection and the retrieval repair must not be
credited for it.

---

## 3. Two proposals awaiting review

Both on the laptop's `C:\Users\chris\Desktop\Horne-privacy-review\`.
Not in the repo, because they quote text that was being removed.

- **Interview directives, bounded.** The finding: there is no shape in
  the directive for a turn that answers and stops — the last line
  instructs her to ask a question. Proposes adding that shape, deleting
  no rule. Needs one revision before applying: the source-attribution
  branch must vary by actual source, and must include "I don't have
  that" as a legitimate ending.
- **Prompt substitutions.** Applied and pushed; the document remains as
  the record of what was changed and why.

---

## 4. How to run things

**Restart without clearing browser state:**
```
bash scripts/restart_no_clean.sh
```
Cold boot is about four minutes. A socket answering proves nothing;
wait for `warmup OK` in `.runtime/logs/api.log`.

**Response tracing is opt-in and resolves at PROCESS START.** Setting
it on a running stack does nothing.

```
# on
sed -i 's|^export HORNELORE_RESPONSE_TRACE=0|export HORNELORE_RESPONSE_TRACE=1|' .env
printf '\nexport HORNELORE_TRACE_DIR=<repo>/.runtime/eval/<run>/response-trace\n' >> .env
bash scripts/restart_no_clean.sh

# verify from the LIVE PROCESS, never from the file
curl http://localhost:8000/api/health/response-trace
```

Turn it off and restart when finished, then verify the same way.
**Keep real-narrator sessions closed while tracing is on** — raw
pre-guard text is captured, and it has never been approved for
ordinary family conversations.

**Read a captured conversation:**
```
PYTHONPATH=server/code python3 scripts/paired_transcript.py --list
PYTHONPATH=server/code python3 scripts/paired_transcript.py \
    --trace-dir .runtime/eval/<run> --latest --export <file>.md
```

It shows the narrator's message, what the model generated, what was
delivered, and every authority that ran — including the ones that ran
and declined. Non-`cc_` stages are named by authority id and quote
their registry known-harm.

**Tests** — per module, `unittest`, not pytest; whole-tree discovery
cross-contaminates through `api.db.DB_PATH`:
```
PYTHONPATH=server/code python3 -m unittest tests.<module>
```
532 passing at handoff.

---

## 5. Standing constraints

- Never `git push` from a script. The operator pushes from GitHub Desktop.
- Never `--amend` a pushed commit.
- Claude must not run `git` from its sandbox — it leaves an
  `index.lock` WSL cannot clear. Hand the operator a read-only status script,
  reconcile, then hand him the add list.
- Real family records are never experimental fixtures, and are never
  altered to make a test pass.
- Stored-data schema changes are presented for approval before
  implementation.
- Keep `HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE=0`.
- `.runtime/` and `.env` are gitignored and must stay so.
- **The invariant is not "keep names out of the repository."** It is:
  *no narrator's material may be reachable by Lori for a different
  narrator.* A narrator's own record, their own prompt, their own bag.
  The 2026-09-21 defect was one narrator's life reaching a different
  narrator through SHARED example data — a correctness and dignity
  failure that would have been exactly as wrong in a private repo.

---

## 6. Lessons that cost real time

Written down because each was rediscovered the hard way.

**Test in production's conditions, not the function's.** The pronoun
bug survived because the unit test handed `detail_for` a `recent_text`
string while production derives it from an archive lookup that returns
nothing. The test proved the function and not the path. The same shape
was repeated hours later: a sandbox without `DATA_DIR` made the
archive look empty, and that produced a confidently wrong diagnosis.

**Use the narrator's actual string.** A retrieval fix was verified
against `"what can you tell me about my mom"` — typed by hand, without
the question mark a person uses. The real one returned nothing.

**A small fixture proves nothing about a mature record.** A 1,444-byte
synthetic narrator passed with 650–900 tokens of headroom; the failure
under investigation had five. The note warning about this was already
in `questionnaire_for_lori.py`, and the mistake was made again anyway
against a record 157 bytes larger.

**Absence is not evidence.** An empty authority table meant "the emit
was gated", not "no guard ran". A missing log line meant "the logger is
conditional", not "nothing happened". Both were read the wrong way
first.

**`fits=True` is true AFTER shedding.** Read `reason`, and read
section survival from `SectionPlan.kept`.

**A prompt is not a changelog.** Explaining a rule's history inside the
prompt puts the old instruction back in front of the model.

**Guards assume the text they edit is expendable.** That assumption
was wrong in `#33`, wrong in `#44`, and is wrong in `#54`. Each repair
is the same shape: find what the rule assumed, narrow it, keep it.
Do not disable guards wholesale.

---

## 7. Two things the desktop will not have

**`.runtime/privacy/family_phrases.txt`** is gitignored, so it does not
travel. Without it `tests/test_prompt_has_no_family_material.py` prints
`[UNVERIFIED]` and skips the known-phrase assertions; the committed
fictional-fixture and assembled-prompt checks still run.

**It is in the wrong place, and the test is the wrong shape.** Both were
built on the assumption that the point was keeping names out of a public
repository. It is not. This is a development deployment, the list is
development data, and it should simply live in the repo — which also
deletes the `[UNVERIFIED]` branch and the skip logic.

The deeper correction is what the test asserts. A hand-maintained list
catches only what someone remembered to add. The invariant is
checkable directly:

    no narrator's material may be reachable by Lori for a DIFFERENT
    narrator

so the primary assertion should be that no *stored* narrator's
distinctive content appears in any shared prompt constant, for any
narrator on the machine — the `people`-table check currently demoted to
assertion four. The phrase list stays only as a supplement for
historical material no longer in any record, which is the one case the
database check cannot see.

Better still, the real test is a RUNTIME one: an assembled prompt for
narrator A should contain A's material and nothing from B's record.
That is assertable on the captured prompt, and it is what would have
caught the 2026-09-21 defect on the day it shipped rather than five
months later.

**The two proposals awaiting review** are on the laptop at
`Desktop\Horne-privacy-review\`, with the three paired transcripts
they refer to. About 53 KB, outside the repository because they quote
text that was being removed. Copy them across if the reviews are still
open.
