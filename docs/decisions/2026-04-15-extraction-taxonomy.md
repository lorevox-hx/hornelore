# Extraction Failure Taxonomy — 2026-04-15 Live Sessions

Compiled from live sessions with Janice (86), Kent (86), and Chris (63) on
2026-04-15. Purpose: classify what the extractor did and did not capture, so
WO-EX-CLAIMS-01 can be scoped against real evidence rather than assumption.

---

## 🔴 CRITICAL FINDING — Field schema mismatch

The question bank's `extract_priority` arrays reference field paths that
**do not exist in `EXTRACTABLE_FIELDS`**. The LLM extraction prompt is built
from `EXTRACTABLE_FIELDS`, so the model literally cannot output these paths
even when the narrator's answer is a textbook instance.

### Missing field paths that the question bank promises but the extractor can't produce

| Question bank `extract_priority` entry | In EXTRACTABLE_FIELDS? |
|----------------------------------------|------------------------|
| `family.children`                      | ❌ missing              |
| `family.spouse`                        | ❌ missing              |
| `family.marriage_date`                 | ❌ missing              |
| `family.grandchildren`                 | ❌ missing              |
| `residence.place`                      | ❌ missing              |
| `residence.period`                     | ❌ missing              |

### What exists today

Only: `personal.*`, `parents.*` (repeatable), `siblings.*` (repeatable),
`education.*`, `earlyMemories.*`, `laterYears.*`, `hobbies.*`,
`additionalNotes.*`.

### Implication

Every compound-loss failure today where the narrator mentioned a **child**,
**spouse**, **grandchild**, **marriage**, or **residence** was doomed
before the LLM even saw the prompt. These aren't fragment-parsing failures.
They're **schema-coverage failures**. Adding family and residence fields
to `EXTRACTABLE_FIELDS` is a prerequisite to any CLAIMS-01 work —
otherwise the claims layer has nowhere to put the claims.

This WO should land BEFORE CLAIMS-01. Call it **WO-EX-SCHEMA-01 — extend
EXTRACTABLE_FIELDS to match question_bank promises**.

---

## Category 1 — Compound-loss failures (multi-fact, zero or partial extract)

**Pattern:** narrator packs multiple structured facts into one answer.
Extractor returns nothing, or captures only one fragment.

### Exhibit A (Janice, children)
> "My oldest, vince was born in Germany in 1960, my middle son Jay or Jason
> was born in Bismarck in 1961 and my youngest Chris or christopher was born
> on his dads birhday in december 24 1962."

- **Contains:** 3 children, 3 birth years, 2 birthplaces, 3 nicknames
- **Extracted:** *nothing shown in shadow review panel*
- **Root cause:** `family.children` field does not exist (see critical
  finding above). LLM has nowhere to put the data.
- **Severity:** **CATASTROPHIC** — richest narrator answer of the session,
  completely dropped.

### Exhibit B (Kent, siblings)
> "my sisters linda and sharon got treated better than i did"

- **Contains:** 2 siblings by name, relation type
- **Extracted:** *nothing shown in shadow review panel*
- **Root cause:** `siblings.firstName` *is* repeatable, so schema is
  adequate. LLM failed to split "linda and sharon" into two entities.
  Pure compound parsing failure.
- **Severity:** **HIGH** — two people lost from the record entirely.
- **WO target:** CLAIMS-01 (requires semantic splitting of coordinated
  proper nouns).

### Exhibit C (Chris, parents x2)
> "My dad Kent Horne was born Dec 24 1939 in Stanley, North Dakota. My mom
> Janice Zarr was born in Spokane Washington."

- **Contains:** 2 parents, 2 first names, 2 last names/maiden, 1 DOB,
  2 birthplaces
- **Extracted:** *nothing shown (Chris pasted twice, both times no panel)*
- **Root cause:** likely Phase G protected-identity suppression — Kent
  Horne is canonical. Extractions that match or conflict with canonical
  get downgraded to suggest_only or stripped. But Janice Zarr should have
  extracted.
- **Severity:** **HIGH** — visible as a UX break (narrator thinks system
  didn't hear them, pastes again, still nothing).
- **WO target:** needs investigation — may be Phase G + compound parse,
  may be LLM output silenced entirely. See §Investigation Needed below.

### Exhibit D (Chris, career compound)
> "I worked a bit after that ended up at und in grand forks and got a degree
> in OT in Decemeber 89 and worked as an ot until i retired decemember
> 2026. I actual got my first ot license the day my son was born April 10
> but in 1989."

- **Contains:** higher education (UND, OT degree, Dec 1989), career
  (OT profession), retirement date (Dec 2026), coincidence fact (license
  date = son's birthday but 1989)
- **Extracted:** *nothing shown in shadow review panel*
- **Root cause:** unclear — all these fields DO exist (`education.higherEducation`,
  `laterYears.retirement`). LLM may have been overwhelmed by the length
  or failed to segment cleanly.
- **Severity:** **HIGH** — five separate extractable facts lost.

---

## Category 2 — Clean single-person / single-fact extractions (success mode)

**Pattern:** narrator gives one clear structured fact in one sentence.
Extractor captures it correctly.

### Exhibit A (Kent, father)
> "my dad was a farmer, he is Ervin Horne he is from Ross ND."

- **Extracted:**
  - `parents.firstName = Ervin` ✓
  - `parents.lastName = Horne` ✓ (not "ND" — WO-EX-01D blacklist would
    have caught it but didn't need to here, LLM got it right)
  - `parents.occupation = farmer` ✓
  - `parents.birthPlace = Ross ND` ✓
- **Severity:** **SUCCESS** — textbook clean extraction.

### Exhibit B (Janice, sister name)
> "Verene is my older sister"

- **Extracted:**
  - `siblings.relation = older sibling` ✓
  - `siblings.firstName = Verene` ✓
- **Severity:** **SUCCESS**

### Exhibit C (Chris, education with negation)
> "didn't go to a four-year college. I took some classes at Bismarck Junior
> College but didn't get a degree."

- **Extracted:**
  - `education.higherEducation = did not attend a four-year college` ✓
  - `education.higherEducation = took classes at Bismarck Junior College` ✓
- **Severity:** **SUCCESS** — negation preserved, specific institution
  captured. Two items on the same field is unusual but not wrong — both
  are true statements about Chris's higher education.

**Takeaway:** the LLM performs well on single-fact sentences. Compound
sentences are where it breaks.

---

## Category 3 — Token-fragment failures (pre-WO-EX-01D regression cases)

**Pattern:** LLM outputs field values that are word fragments, pronouns,
connectives, or state abbreviations.

### Exhibit A (Chris morning session, pre-fix)
- `parents.firstName = and` (from "mother and dad")
- `parents.lastName = dad` (from "mother and dad")
- `parents.firstName = Stanley` (from "my dad Stanley ND")
- `parents.lastName = ND` (from "my dad Stanley ND")

### Status after WO-EX-01D
- `lastName = ND` → DROPPED ✓
- `firstName = and` → DROPPED ✓
- `lastName = dad` → still passes (stopword guard is firstName-only — known
  limit flagged in the WO-EX-01D test)
- `firstName = Stanley` → still passes (Stanley is a real name; context
  disambiguates but the filter can't. CLAIMS-01 semantic reasoning would
  catch this.)

**Severity:** **MEDIUM** — worst cases now blocked; semantic residue
remains.

---

## Category 4 — Typo-preserved fragments

**Pattern:** narrator typos survive through extraction into field values.

### Exhibit A (Janice)
> "i went to schools thre and finished at st marys in bismarck"

- `education.schooling = schools thre` (typo of "there")
- `education.schooling = st marys in bismarck` (OK partial)

**Severity:** **LOW** — minor. Human operator can correct via the
Correct button in shadow review. Not blocking.

**WO target:** not worth a dedicated WO. CLAIMS-01's value normalization
step can address.

---

## Category 5 — Protected-identity suppression (likely-correct, visibly invisible)

**Pattern:** narrator restates already-canonical identity info. Extractor
produces items. Phase G downgrades to suggest_only or strips entirely.
Operator sees either nothing or a low-signal suggestion.

### Exhibit A (Chris repeating parent info)
> "My dad Kent Horne was born Dec 24 1939..."

- Canonical Kent Horne already promoted (profile_json)
- Extraction happens → Phase G sees conflict/match → suppresses
- Operator sees empty panel → assumes system didn't hear them
- Operator pastes again → same silence → UX frustration

**Severity:** **MEDIUM as UX, LOW as data** — the system is correctly
protecting canonical truth, but the silence is confusing.

**WO target:** **WO-UI-SHADOWREVIEW-01** (separate from CLAIMS-01) —
show "we already have this confirmed" when Phase G suppresses. Give the
operator feedback so they don't re-paste.

---

## Category 6 — Missing field coverage (answered correctly by LLM but discarded)

**Pattern:** LLM outputs a field path that the validation rejects because
the path isn't in `EXTRACTABLE_FIELDS`. Logged as rejected but not shown
to operator.

### Likely instances (inferred from logs)
- Children: "my son Cole was born April 10 2002"
- Grandchildren: unlikely tested today but will occur
- Marriage: untested today
- Residences during life: "we moved to Minot when I was 1"

This overlaps with Category 1 root cause but deserves its own entry
because the fix is schema extension, not parsing logic.

**Severity:** **CATASTROPHIC** when narrator is in a life phase that
naturally produces these (parenthood, marriage, residence moves).

**WO target:** **WO-EX-SCHEMA-01** (see Critical Finding above).

---

## Category 7 — LLM silent-drop on long inputs

**Pattern:** narrator's answer exceeds some threshold (length, complexity).
LLM returns nothing parseable. No error surfaced to operator.

### Suspected instances today
- Chris's 5-fact career compound (Exhibit D above)
- Janice's 3-children compound (Exhibit A above)

### Investigation needed
Check server logs for these turn timestamps. If `[extract-parse]` shows
"Parsed 0 raw items" but `Raw LLM output` has content, the LLM produced
something but it didn't parse. If `Raw LLM output` is empty, model
timeout or truncation.

**Severity:** **HIGH** — silent failures erode operator trust.

**WO target:** **WO-EX-DIAG-01** — surface extraction failure reason in
response envelope so UI can show "I wasn't able to process that — try
saying it in shorter pieces?"

---

## Summary — WO map based on today's evidence

| WO | Priority | Why |
|----|----------|-----|
| **WO-EX-SCHEMA-01** — add family/residence fields to EXTRACTABLE_FIELDS | **P0 — BLOCKER** | Nothing else about children/spouse/residence can work until this lands |
| **WO-EX-CLAIMS-01** — fragment → claim assembly | P1 | After P0, addresses compound-parse failures like Linda/Sharon split |
| **WO-UI-SHADOWREVIEW-01** — show Phase G suppression reason in UI | P2 | Prevents operator re-paste frustration |
| **WO-EX-DIAG-01** — surface LLM-silence diagnostics | P2 | Debug visibility for failures like Chris's career compound |
| **WO-EX-01E** — extended sanity filters (numeric firstName, single-char names) | P3 | Already planned, small |

---

## Investigation queue for tomorrow

1. **Server log trace for Chris's parent-compound turn** — what did the LLM
   actually return? Did Phase G strip everything? Did the extractor not fire?
   Without this log, Exhibit C is ambiguous between Category 1 and Category 5.

2. **Server log trace for Janice's 3-children turn** — was
   `[extract-parse] Parsed N raw items` nonzero? That would prove the LLM
   tried but couldn't use `family.children` (confirms schema gap).

3. **Verify `current_section` is being sent by client** — already on the
   C2 investigation list; affects how reliably Category 5 fires.

---

## Observations on what's working

Against all of the above, note what's clearly working in production:

- WO-EX-01C **west Fargo fix** — holding in live session ✓
- WO-EX-01C **child DOB fix** — holding in live session ✓
- WO-EX-01D **state-abbreviation blacklist** — validated (Ross ND
  correctly slotted as birthPlace) ✓
- Single-fact extractions on Kent (Ervin Horne, occupation, birthPlace) ✓
- Negation preservation (Chris "didn't go to college") ✓
- Narrator direct correction (Chris "I was not a teenager in Minot") ✓

**The extractor isn't broken. It's under-resourced (missing fields) and
over-tasked (compound sentences). Both are addressable.**
