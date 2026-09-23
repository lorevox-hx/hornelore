# BUG-LORI-UNAWARE-OF-DEATH-01

**Lori is not told when a narrator's relative has died.**

Filed 2026-09-22 from the questionnaire field audit
([`docs/BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md`](../BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md) §11.3).
**Nothing has been changed.** This document records a measurement and a
proposed correction.

---

## Mission alignment

The Mission puts narrator dignity above operational tidiness, and the
narrator is "the author of their own story", frequently an older adult
recalling a life in which people have died. A companion that does not know
a parent is dead can speak of them in the present tense, or ask what they
are doing now. That is the failure this defect makes possible, and it is a
dignity failure before it is a data failure.

## Non-regression requirements

This work MUST NOT:

- reduce narrator dignity
- introduce new `must_not_write` violations or system-tone outputs — a
  living/deceased status must reach the prompt as something a person would
  say, never as `deceased: true`
- regress the CURRENT locked baseline without explicit justification (name
  the baseline and its scorer; a pass-count delta across a scorer change
  measures the scorer)
- expand operator surfaces into narrator UI
- add detectors that duplicate existing signals

## Lori impact (Tier 3)

- **Response length / questions per turn:** unchanged. This adds at most a
  short clause per relative to an existing block.
- **Tone and pacing:** the point of the change. It governs tense and
  phrasing when Lori speaks about a relative.
- **Narrator-vs-operator boundary:** unchanged; the status is operator-
  entered biography, already visible in Bio Builder.

## Narrator dignity check

Walked against the locked design principles:

- **No system-tone outputs.** `deceased: Yes` must never surface. The prompt
  should carry something a person would say, and must not instruct Lori to
  raise a death unprompted — only to speak accurately when the subject
  arises.
- **Operator seeds known structure; Lori reflects what is there.** The status
  is already seeded. This defect is Lori failing to reflect it.
- **Mechanical truth must visibly project.** A value held in the
  questionnaire, in `profile_json` and in the family graph that reaches no
  narrator-facing surface is precisely the hidden-state failure this
  principle forbids.

---

## 1. What was measured

Narrator: a real family narrator, both of whose parents are recorded
`deceased: "Yes"` in the questionnaire. Measured against the live product
root on 2026-09-22.

### Confirmed — the status is stored, in three places

| store | value |
|---|---|
| questionnaire | `parents[0].deceased = "Yes"`, `parents[1].deceased = "Yes"` |
| `profile_json` | `kinship[0].deceased = True`, `kinship[1].deceased = True` |
| `graph_persons` | 2 of 14 rows flagged `deceased = 1` |

### Confirmed — it reaches no narrator-facing surface on the paths examined

| path | measurement |
|---|---|
| `questionnaire_for_lori.load_facts` | **0 of 98** facts carry the field `deceased` — `_SKIP_FIELDS = {"_entryId", "deceased"}` removes it before any fact is built |
| the rendered biography block | contains no `deceased`, `died`, `passed` or `late ` |
| `questionnaire_for_lori.detail_for` | on-demand retrieval about the mother returns no death wording — structurally it cannot, since it filters the same fact list |
| `interview_projections` | 18 fields, none mentioning deceased |
| `bio_facts` | **0 rows** for this narrator |
| `bio_schema` canonical vocabulary | **no key exists** for death, deceased, surviving or living status — 84 fields, none of them this |
| `prompt_composer.py` | reads `kinship` from `profile_json` at line 1369, where the flag is `True`; the file contains **no reference to `deceased` anywhere** |
| `graph_persons` → prompt | `prompt_composer.py` contains no reference to `graph_persons` |

**The sharpest statement the evidence supports:** the flag arrives in the
prompt composer's own input and is discarded there, and the canonical bio
vocabulary has no concept of it at all.

### NOT examined — do not cite this document as clearing them

- memoir export and memoir generation
- `story_candidates` and the story-review surface
- Life Map / timeline render
- the family-tree bridge (`bio-builder-family-tree.js`)
- extraction prompts (`routers/extract.py`) — whether a stated death is
  extracted at all is a separate question
- any narrator-room client-side rendering
- spoken output specifically, beyond the text handed to synthesis

## 2. Why it happens

`server/code/api/services/questionnaire_for_lori.py`:

```python
# Bookkeeping that is not biography.
_SKIP_FIELDS = {"_entryId", "deceased"}
```

`_entryId` genuinely is bookkeeping. `deceased` is not — it is the single
most important piece of context for how to speak about a relative. The
grouping is the defect.

The second half is independent: even with the classification corrected, the
canonical `bio_schema` has no field for living/deceased status, so Profile
Seed and any consumer reading canonical truth would remain blind.

## 3. The risk, stated plainly

Lori holds a deceased mother's birth date, birthplace, occupation and life
stories, and nothing indicating she has died. The narrator is her daughter,
in her late eighties. Present-tense phrasing, or a question about what her
mother is doing now, is available to the model and nothing prevents it.

No such incident is recorded. **This is a reachable state, not an observed
one**, and it is filed that way deliberately.

## 4. Proposed correction

Not implemented. Presented for approval.

1. **Remove `deceased` from `_SKIP_FIELDS`** and give it a rendering that
   reads as a person speaking — the status governing tense, not a field
   printed as `deceased: Yes`.
2. **Add a living/deceased concept to `bio_schema`**, so canonical truth can
   hold it and Profile Seed can see it. Today no such key exists.
3. **Do not instruct Lori to raise a death.** The correction is about
   accuracy when the subject arises, never about introducing it. A prompt
   line that tells her someone has died is not a licence to mention it.
4. **Handle "unknown" honestly.** A blank must stay unknown. The form's own
   rule — *leave blank if unknown, do not guess* — applies: absent status
   means Lori has not been told, and she should not infer from a birth year.
5. **Acceptance:** a narrator with a deceased parent and a living spouse
   produces a prompt in which the deceased parent is referred to in the past
   tense and the living spouse is not; a narrator with blank status produces
   neither claim.

## 5. Sequencing

Independent of the wider vocabulary reconciliation in the audit's §12 and
proposed as item 1 there: it is small, self-contained, and it is the highest
dignity risk the audit found. It does **not** require the crosswalk, the name
model, or the Profile Seed authoritative-store decision to land first —
though item 2 above will want revisiting once that decision is made.
