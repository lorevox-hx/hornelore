# `current_section` Client→Server Audit — 2026-04-15

## Question

The 2026-04-15 morning server logs showed:

```
[extract] Attempting LLM extraction for person=a4b2f07a, section=None, target=None
```

Is the client actually sending `current_section` to `/api/extract-fields`?
If not, that's a silent gap that weakens our WO-EX-01C birth-context filter
by forcing it to default to the safe-section-empty gate.

## Finding — the client DOES send it, but it's often null by design

### Where the client reads and sends it

`ui/js/interview.js` line 1189:
```javascript
var payload = {
  person_id: state.person_id,
  session_id: state.interview.session_id || null,
  answer: chunk,
  current_section: targetSection || null,
  current_target_path: targetPath || null
};
```

Where `targetSection` comes from line 1173:
```javascript
var targetSection = state.interviewProjection._lastTargetSection || null;
```

And `_lastTargetSection` is copied from `_currentTargetSection` on every
user turn in `_projectAnswerToField()` (line 1012).

### When `_currentTargetSection` is set

Only ONE code path writes it (line 653, inside `_getNextRepeatableQuestion()`):

```javascript
if (!hasEntries && !explored) {
  state.interviewProjection._currentTargetSection = section;
  state.interviewProjection._currentTargetPath = null;
  return tpl.entryPrompt;
}
```

That means `current_section` is only populated when the current interview
turn was driven by a **repeatable-section entry prompt** (parents,
grandparents, siblings). In practice, that's a narrow slice of turns.

### When `_currentTargetSection` is NULL

- Free-form chat mode (chat_ws path, narrator typing freely)
- Projection-field questions (`_getNextProjectionQuestion()` — these set
  `_currentTargetPath` but NOT `_currentTargetSection`; the section is
  inferred from the field path)
- First turn of a session, before any projection prompt has fired
- Phase-aware composer turns (WO-LIFE-SPINE-05, flag-gated — composer
  uses its own routing and doesn't integrate with `_currentTargetSection`)
- Any turn after the previous turn cleared `_currentTargetSection` in
  `_projectAnswerToField()` and no new prompt has set it

### What this means for WO-EX-01C

My strict `_is_birth_context` (section-only, no phase escape, None
treated as strict) correctly handles this:

```python
def _is_birth_context(current_section, current_phase=None):
    if not current_section:
        return False  # strict default — no section means no birth context
    return current_section.lower() in _BIRTH_CONTEXT_SECTIONS
```

When the client sends `null`, `_is_birth_context` returns False,
birth-field items are stripped unless the answer has an explicit "born"
phrase AND the subject is the narrator. That's the safer behavior.

If my implementation had kept the pre-WO-EX-01C behavior (None →
permissive), every null-section request would leak birth fields. The
morning's west-Fargo bug was partially this exact hole.

**Conclusion: the current client behavior is acceptable because the
server-side strict default compensates for it.**

## Is there a fix worth making?

Yes, but small and low priority.

### Option A — minimal: populate `_currentTargetSection` in more paths

For the projection-field path (`_getNextProjectionQuestion()`), the
field path (`personal.placeOfBirth`) already implies the section
(`personal`). A small code change could:

```javascript
// In _getNextProjectionQuestion, after picking a target path
var targetPath = ...;
state.interviewProjection._currentTargetPath = targetPath;
state.interviewProjection._currentTargetSection = targetPath.split(".")[0];
```

This would populate section on far more turns, letting the server's
birth-context gate make better decisions. Especially valuable when
the narrator is in the middle of answering a `personal.*` field
question — server could correctly recognize the birth-context section.

**Risk:** low. Section inference from fieldPath is deterministic.
**Size:** ~3 lines. One-test.

### Option B — inclusive: also populate from phase-aware composer

When `HORNELORE_PHASE_AWARE_QUESTIONS=1` and the composer selects a
sub-topic (e.g. `origin_point` in phase `developmental_foundations`),
the composer's picked question doesn't update `_currentTargetSection`
at all. Phase-aware turns reach the extractor with section=None.

Fix: when `phase_aware_composer.pick_next_question()` returns a
question, the frontend should set `_currentTargetSection` to the
phase's equivalent canonical section. That mapping already exists in
the bank's `spine_phase_mapping` field.

This is a WO-LIFE-SPINE-05 follow-on — formally "composer should
populate client interview state with the phase context." Medium size
(~15 minutes UI change + integration).

### Option C — no change

Accept the null-section-is-frequent reality. Strict server-side
default already compensates. Move on.

## Recommendation

**Ship Option A as a drive-by tightening when someone is next in
interview.js for other work.** Don't spin a dedicated WO — it's too
small. Add a comment noting that the single-line `.split(".")[0]` fix
helps the server gate birth-context correctly.

**Queue Option B as a WO-LIFE-SPINE-05 follow-on.** Relevant once
phase-aware is actually flipped on and being tested. The composer's
output already carries `_meta.phase_id` and `_meta.sub_topic_id`; just
need to wire a canonical section hint through.

## Related observation — `current_phase` is ALSO often null

Looking at the same extraction request model:

```python
class ExtractFieldsRequest(BaseModel):
    current_section: Optional[str] = None
    current_phase: Optional[str] = None
```

The client never populates `current_phase` today. It was added for
WO-LIFE-SPINE-04 but the UI doesn't send it. My rewrite of
`_is_birth_context` made `current_phase` inert — so this is not
currently causing bugs, but it's dead data flowing through the API.

Either wire it in (option B above) or eventually drop it from the
request model. Harmless either way today.

## Verdict

- Client sending null for current_section is **common and by design**.
- Server strict-default compensates correctly.
- No immediate fix required.
- Option A is a nice-to-have drive-by (~3 lines, ~5 min test).
- Option B is a real follow-on for phase-aware activation.

**Status: AUDIT COMPLETE. No code change required today.** Drive-by
Option A can be added whenever someone is next editing `interview.js`.
