# Narration Samples Authoring Spec — Hand to ChatGPT

**Purpose:** Generate additional canned narrator-sample sets for the
parent-session-readiness Playwright harness (TEST-11). The harness uses
each sample to verify Lori responds appropriately to narration of varied
sizes AND grounds follow-up answers in what the narrator just shared.

**Hand this whole document to ChatGPT.** It's self-contained.

---

## What you're authoring

For each fictional test narrator you create, output **one JSON object**
with four sample-size variants of the same biography PLUS ground-truth
metadata used to score Lori's follow-up answers.

The harness already includes Christopher Horne as the canonical
baseline. Author **2–4 additional fictional narrators** with diverse
backgrounds (ages, regions, careers, family structures). These run as
test cases; **none of these narrators are Chris's real family** — Kent,
Janice, and Christopher Horne are FAMILY narrators and must never be
generated as test fixtures.

## Output format

A single JSON file, an array of narrator entries:

```json
[
  {
    "narrator_id": "test_narrator_002",
    "label": "Mary Sullivan, 81, Boston schoolteacher",
    "ground_truth": {
      "name_full": "Mary Catherine Sullivan",
      "name_first": "Mary",
      "name_aliases": ["Mary", "Cathy", "Mary Cathy"],
      "dob": "1944-03-15",
      "birth_year": 1944,
      "birth_month_day": "March 15",
      "birthplace": "Boston, Massachusetts",
      "birthplace_aliases": ["Boston", "Massachusetts"]
    },
    "samples": {
      "clean":      "...",
      "messy":      "...",
      "emotional":  "...",
      "fragmented": "..."
    },
    "follow_ups": [
      { "ask": "What's my name?",        "must_match_any": ["Mary", "Cathy"] },
      { "ask": "What year was I born?",  "must_match_any": ["1944"] },
      { "ask": "Where am I from?",       "must_match_any": ["Boston", "Massachusetts"] },
      { "ask": "What time is it?",       "must_match_local_clock": true },
      { "ask": "What day is it?",        "must_match_local_clock": true }
    ]
  },
  { /* next narrator */ }
]
```

Save the array to `docs/test-data/narration_samples.json`. The harness
will read that path automatically when `--samples-file` is set.

## Sample size targets (word counts)

Each narrator's `samples` object MUST contain these four variants of the
**same biographical facts**, retold in different registers:

| Key | Words | Voice / register |
|---|---|---|
| `clean`      | 800–1100 | Full prose, paragraphed, polished. Reads like a memoir excerpt. Names, dates, places, relationships, career arc, life lessons. Multiple paragraphs. |
| `messy`      | 130–180  | One block. Casual hedged speech: "I think", "yeah", "sort of". Jumps around. Gaps and asides. Like someone telling their story off-the-cuff to a stranger. |
| `emotional`  | 180–240  | One block, paragraphed. Feeling-led not chronological. "I always remember…" / "That was one of the hardest times…" / "What I carry with me is…". Same facts but the narrator is emotionally present, not just listing. |
| `fragmented` | 60–100   | Telegraphic. Two-to-five-word sentences. Like someone with limited stamina or a memory-care cadence. Just the bones: name, year, place, key relationships, career, retirement, key reflection. **Period-separated short phrases**, not full sentences. |

All four variants of one narrator MUST contain the same canonical facts:
the same name, birth year, birthplace, parent names, sibling names,
spouse name(s), children names, career, retirement detail, life lesson.

## Required ground-truth coverage

Each narrator's biography MUST include these surfaces (across all four
samples; later samples can be terser but the facts must be present):

- Full legal name + any nicknames
- Date of birth (month + day + year)
- Birthplace (city + state/country)
- Birth-order context (oldest / middle / youngest / only child)
- One or both parents' names + at least one parent's occupation
- At least one sibling name (or "only child" if applicable)
- Education: school name + graduation year (or period of schooling)
- Career: profession + setting (city/state)
- At least one spouse's name + marriage year (or "never married")
- At least one child's name (or "no children" if applicable)
- One memorable trip / event / milestone with a year
- Retirement year (or current life stage if pre-retirement)
- One reflective life lesson at the end of `clean` and `emotional`

## Diversity requirements

Across the 2–4 narrators you author:

- **Ages**: range 65–95. Don't put them all at the same life stage.
- **Regions**: don't make them all American. Include at least one
  narrator whose birthplace is outside the US (Canada, UK, Mexico,
  Philippines, India — anywhere with English-speaking diaspora is fine).
- **Careers**: don't repeat occupational therapy (Christopher's career).
  Mix: schoolteacher, nurse, mechanic, farmer, librarian, factory
  worker, small-business owner, postal worker, etc.
- **Family structures**: include at least one narrator who never
  married or had no children, AND at least one with a stepfamily /
  blended family.
- **Genders**: include at least one woman, at least one man.
- **Cultural backgrounds**: vary surnames (don't all be Anglo-Saxon).

## What the harness will do with each sample

For each (narrator × sample-size) combination, the harness will:

1. Create a fresh disposable test narrator named `Test_<6-digit-ms>`.
2. Click through to the narrator session room.
3. Send the entire `<sample>` text as one chat message to Lori.
4. Wait for Lori's reply (any non-empty response counts as "she
   responded to the narration").
5. Send each `follow_ups[i].ask` query in sequence; wait for Lori's
   reply per query.
6. Score each follow-up reply:
   - For `must_match_any: [...]` — PASS if the reply contains any of
     the listed strings (case-insensitive).
   - For `must_match_local_clock: true` — PASS if the reply contains
     today's weekday name OR month-name + day OR a `HH:MM` time OR
     "AM"/"PM".
7. Score the overall (narrator × sample) test:
   - **PASS** = Lori responded to the narration AND every follow-up
     scored PASS.
   - **AMBER** = Lori responded but at least one follow-up missed.
   - **FAIL** = Lori didn't respond at all OR multiple follow-ups missed.

## Hard constraints

- **No real living public figures.** Don't author "Sandra Day
  O'Connor" or "Jimmy Carter" — fictional only.
- **No Kent / Janice / Christopher Horne** — those are FAMILY
  narrators and must never appear as test fixtures.
- **No content that could harm a narrator with cognitive decline** if
  read aloud — keep tone respectful, the narration is from the
  narrator's voice, not satirical or dismissive.
- **No religion or politics as central themes.** Faith / beliefs can
  appear as background detail (church choir, military service, etc.)
  but the narrator's identity should not hinge on a contested topic.
- **Period-appropriate language.** A narrator born in 1944 sounds
  different from one born in 1958. Vary vocabulary and references.
- **No content involving minors as victims** of any kind.
- **No financial advice / medical advice** in the life lessons.
- **Realistic but not over-detailed.** Include enough specifics to
  make the follow-up questions answerable, but don't make it so dense
  that no reasonable narrator could recall the whole biography in one
  sitting.

## Validation checklist (for you to self-check before output)

For each narrator entry:

- [ ] All four sample sizes meet the target word-count range
- [ ] Same canonical facts (name, dob, birthplace, etc.) appear in
      all four samples — no fact in `clean` that's contradicted in
      `messy`/`emotional`/`fragmented`
- [ ] `ground_truth.name_aliases` covers every way the narrator's
      name appears across the four samples
- [ ] `ground_truth.birthplace_aliases` covers every short form
      (e.g. just "Boston" in `fragmented`, full "Boston, Massachusetts"
      in `clean`)
- [ ] `follow_ups[*].must_match_any` strings actually appear in the
      narrator's identity / biography
- [ ] No real public figure
- [ ] No Kent / Janice / Christopher Horne
- [ ] Diversity check: across all narrators, at least 2 ages, 2
      careers, 2 regions

## Output

Just the JSON array, ready to drop into
`docs/test-data/narration_samples.json`. No prose around it.

If you want to label each narrator briefly for human review, use the
`label` field — it's metadata only, the harness ignores it.
