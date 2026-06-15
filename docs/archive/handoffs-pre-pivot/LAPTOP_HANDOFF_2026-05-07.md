# Laptop Handoff — 2026-05-07

**For Claude on the laptop (Lorevox host).** Author: Claude on the dev computer (MAG-Chris host). Subject: bring the laptop in sync with all of today's parent-session-readiness work, then run the dry-run validation.

## TL;DR — what the laptop needs

1. **Pull 1 unpushed commit** from dev (Chris must push first if he hasn't)
2. **Add 4 env flags** to `.env`
3. **Delete 2 dead env vars** from `.env`
4. **Cycle stack** with full 4-min warmup
5. **Run dry-run** validation script (provided below)

After this completes, dev and laptop are at identical commit + parity-equivalent `.env` (minus laptop-specific tuning that should stay).

---

## Dev vs laptop state diff (as of 2026-05-07 ~09:10)

### Git history

| Commit | Dev (MAG-Chris) | Laptop (Lorevox) | On origin? |
|---|---|---|---|
| `0527f33` stories-captured FS mirror + chat_ws audio_id lift | ✅ HEAD | ❌ missing | **uncertain — Chris may need to `git push` from dev first** |
| `d9ddfea` Smoke 11 Melanie Carter Phase 1c report | ✅ | ✅ HEAD | ✅ |
| `988542e` cross-session identity + audio link + per-narrator camera consent + Phase 1d | ✅ | ✅ | ✅ |
| `38e21c2` six parent-session readiness bug fixes | ✅ | ✅ | ✅ |
| `8838cbe` parent-session readiness artifacts | ✅ | ✅ | ✅ |

**Action needed:** Chris pushes `0527f33` from dev (`git push origin main`). Then laptop runs `git fetch origin && git pull origin main`.

### `.env` state

| Variable | Dev (MAG-Chris) | Laptop (Lorevox) per audit | Action on laptop |
|---|---|---|---|
| `HORNELORE_MEMORY_ECHO_ERA_STORIES=1` | ✅ L215 | ❌ missing | **ADD** |
| `HORNELORE_CONTINUATION_PARAPHRASE=1` | ✅ L214 | ❌ missing | **ADD** |
| `HORNELORE_REFLECTION_SHAPING=1` | ✅ L218 | ❌ missing | **ADD** |
| `HORNELORE_STORIES_CAPTURED_FS=1` | ✅ L225 | ❌ missing | **ADD** |
| `LOREVOX_NARRATOR_LOCATION=Santa Fe/Las Vegas, NM` | ✅ L220 | ❌ missing | **ADD** |
| `DB_PATH=/mnt/c/hornelore_data/hornelore.sqlite3` | ❌ deleted (was at L75) | ⚠️ present (wrong path) | **DELETE** — see notes |
| `TRANSFORMERS_CACHE=/mnt/c/models/hornelore/hf_home` | ❌ deleted (was at L40) | ⚠️ present (deprecated) | **DELETE** — see notes |
| Laptop-specific tuning | ❌ none | ✅ `DEVICE_MAP=cuda:0`, `PYTORCH_ALLOC_CONF=...`, `PORT=8000`, `TTS_PORT=8001`, `UI_DIR=...` | **LEAVE — these are doing real work on the laptop** |

**Why delete `DB_PATH` instead of patching it:** runtime path is hardcoded as `$DATA_DIR/db/$DB_NAME` in `server/code/api/db.py` (L43-48). Nothing reads `DB_PATH` from env. Patching the value masks the fact that the variable is dead and tempts future drift. Deleting eliminates the category of confusion.

**Why delete `TRANSFORMERS_CACHE`:** transformers 4.55 deprecated this in favor of `HF_HOME` (the audit showed the deprecation FutureWarning). With `HF_HUB_OFFLINE=1` the whole cache lookup is short-circuited anyway — neither variable matters at runtime.

---

## Sync commands (run on laptop)

### Step 1 — pull `0527f33` from origin

```bash
cd /mnt/c/Users/chris/hornelore
git fetch origin
git status                          # confirm "behind by 1 commit"
git pull origin main                # fast-forward, no merge
git log --oneline -5                # confirm 0527f33 arrived at HEAD
```

If `git fetch` shows origin/main still at `d9ddfea` (laptop is current), Chris hasn't pushed yet. Tell Chris: **"`git push origin main` from dev first"**. Then retry.

### Step 2 — env adjustments

```bash
cd /mnt/c/Users/chris/hornelore
cp .env ".env.bak_$(date +%Y%m%d_%H%M%S)"

# Delete dead env vars
sed -i '/^DB_PATH=/d; /^TRANSFORMERS_CACHE=/d' .env

# Add the 4 missing flags + 1 location var
cat >> .env <<'EOF'

# Added 2026-05-07 — laptop sync from dev
HORNELORE_MEMORY_ECHO_ERA_STORIES=1
HORNELORE_CONTINUATION_PARAPHRASE=1
HORNELORE_REFLECTION_SHAPING=1
LOREVOX_NARRATOR_LOCATION=Santa Fe/Las Vegas, NM
# Stories-captured filesystem persistence — writes self-contained
# audio + transcript + metadata folder under DATA_DIR/stories-captured/
# whenever the story_trigger fires. Default-on; set to 0 to disable.
HORNELORE_STORIES_CAPTURED_FS=1
EOF

# Verify
echo "--- new flags present ---"
grep -E "^(HORNELORE_MEMORY_ECHO_ERA_STORIES|HORNELORE_CONTINUATION_PARAPHRASE|HORNELORE_REFLECTION_SHAPING|HORNELORE_STORIES_CAPTURED_FS|LOREVOX_NARRATOR_LOCATION)=" .env
echo "--- dead vars deleted ---"
grep -E "^(DB_PATH|TRANSFORMERS_CACHE)=" .env || echo "  (correctly absent)"
```

### Step 3 — start stack + warmup wait

Chris owns stack lifecycle. After `bash scripts/start_all.sh` (or his usual launcher), wait the **full 4 minutes** before sending the first chat turn. The HTTP listener comes up at ~60-70s but the LLM weights + extractor warmup continues for another 2-3 minutes.

A ready check that matters (NOT just a curl):

```bash
# Probe extractor warmup with a tiny extract — if round-trip < 30s, ready
time curl -s -X POST http://localhost:8000/api/extract-fields \
  -H "content-type: application/json" \
  -d '{"answer":"My name is Test","section":"personal","question":"What is your name?"}' | head -c 200
echo
```

If that takes <30s and returns a JSON shape, stack is hot.

---

## Step 4 — dry-run validation script

Open Chrome to `http://localhost:8000/ui/hornelore1.0.html`. Walk through this script and check each behavior. **Report PASS / FAIL with screenshots or text capture** for each step.

### Setup
- Click **+ Add Test Narrator** → narrator created with auto-name like "Smoke 12 Test"
- Pick session style **Clear & Direct** (default)
- Cognitive Support Mode: leave OFF for first run

### Step 1 — first-session intro fires (#63 verification)

Click **Enter Interview Mode**.

**Expected:** Lori says hello within ~10-15 seconds. Sample shape: *"Hello! I'm so glad you're here. My name is Lori, and I'll be helping you build a Life Archive. To get started, I just need three small pieces of information from you: your name, your date of birth, and where you were born."*

**Pass criterion:** Lori greets WITHOUT operator clicking "Complete profile basics". The intro flows automatically on Interview Mode entry. Console marker: `[onboarding] startIdentityOnboarding() — new user path, phase=askName`.

### Step 2 — identity capture

Type "Hi Lori, my name is Smoke Test User."

**Expected:** Lori asks for DOB next.

Type "I was born April 1, 1950."

**Expected:** Lori asks for POB next. Header should show `Apr 1, 1950 · age 76`.

Type "I was born in Phoenix, Arizona."

**Expected:** Lori warmly acknowledges all three; Active Narrator card shows full identity. Identity onboarding is COMPLETE.

### Step 3 — Life Map era click does NOT bypass identity (#53 verification — should be no-op since identity now complete)

Click **Today** on Life Map.

**Expected:** Confirm popover appears, Continue → Lori asks era-appropriate question framed in present tense. Console marker: `[life-map][era-click] Lori prompt dispatched for era=today`. **Should NOT see** `[life-map][era-click] BLOCKED Lori dispatch — identity incomplete`.

Type a 100-word story like:
*"These days I take things slowly. Mornings are for coffee on the back porch and watching the birds at the feeder. My grandkids visit on Sundays — three of them, all under ten — and they love hunting for the lizards that live in the rock garden. I read mystery novels in the afternoons. Tom and I have been married fifty-two years now, and we still hold hands when we walk to the mailbox."*

**Expected:** Lori reflects ONE concrete anchor from the story (porch / birds / grandkids / lizards / mystery novels / 52 years / mailbox) and asks ONE follow-up question. Reply is **≤90 words** (#62 adaptive cap — narrator gave 90+ words so Lori gets +35 word headroom). Reply ends cleanly with a `?` — no `…` mid-sentence (#60 verification).

### Step 4 — memory_echo with cross-session readback (#54 + #52 + #63 chain)

Type "Lori, what do you know about me so far?"

**Expected:** Memory echo shape:
```
What I know about Smoke Test User so far:

Identity
- Name: Smoke Test User
- Date of birth: 1950-04-01
- Place of birth: Phoenix, Arizona

Notes from our conversation
- Childhood home: Phoenix, Arizona
- Life stage: elder / retirement years

What you've shared so far                    ← #52 Phase 1d era-stories rendering
- Today: These days I take things slowly. Mornings are for coffee on...

What I'm less sure about
- Some parts are still blank, and that is completely fine.
...

(Based on: profile, interview projection, session notes.)
```

**Pass criterion:** "What you've shared so far" section renders with the era-tagged story stub. NO system-tone leakage ("era stories" / "transcript" / "based on" / etc. shouldn't appear except in the source footer).

### Step 5 — double-send while generating drops second send, NOT first (#61 verification)

Type "Tell me what you remember about Tom" → click Send.

**While Lori is still generating** (Thinking badge visible), type "Actually never mind" and click Send.

**Expected:** Console shows `[chat] sendUserMessage() BLOCKED — Lori is generating`. The second message is silently dropped. Lori responds to the FIRST message ("Tell me what you remember about Tom").

### Step 6 — exit + re-enter session (idempotent intro check, #63 + welcome-back)

Click **Exit** to leave Interview Mode. Click **Enter Interview Mode** again.

**Expected:** Lori says **welcome-back**, NOT cold-start "Hello! I'm Lori..." The narrator's name should be acknowledged. Console: `[lv-interview] identity already complete — skipping intro`.

### Step 7 — narrator switch + camera consent re-prompt (#57 verification)

Open the narrator dropdown → click **+ Add Test Narrator** to create a SECOND narrator. Open that narrator → Enter Interview Mode → click **Cam** toggle to enable camera.

**Expected:** Camera consent modal appears for THIS narrator (not inheriting first narrator's grant). Console: `[Lorevox] Facial consent: setNarrator(<new_pid_8chars>) stored=false`.

### Step 8 — stories-captured/ folder appears

After the 100-word story turn in Step 3 fired the story_trigger, check the filesystem:

```bash
ls -lh /mnt/c/hornelore_data/stories-captured/
ls -lh /mnt/c/hornelore_data/stories-captured/*/   # should show one timestamped folder
cat /mnt/c/hornelore_data/stories-captured/*/*/transcript.txt
cat /mnt/c/hornelore_data/stories-captured/*/*/metadata.json
ls /mnt/c/hornelore_data/stories-captured/*/*/audio.webm 2>&1 || echo "(audio.webm absent — expected: FE doesn't yet pass audio_id; tracked under #50/#58 Phase E)"
```

**Expected:** `transcript.txt` + `metadata.json` exist. `audio.webm` absent (FE wiring not done yet — that's the next priority work).

---

## What worked vs failed

After the dry-run, summarize each step PASS/FAIL with a one-line note. Anything FAIL gets escalated; anything PASS is locked in.

If everything PASSes, the laptop is parent-session-ready. Janice and Kent runs unblocked.

---

## Next priority work options (after dry-run is clean)

Three options for next code work, in order of leverage:

### Option A — Frontend audio_id wiring (~1-2 hrs)

Currently `narrator-audio-recorder.js` uploads webm files with a turn_id but does NOT pass that turn_id into the WebSocket `start_turn` payload. Backend wiring (#58) is complete and waiting. Once FE passes `turn_id` in the WS payload, the stories-captured/ folder will start populating audio.webm. Highest leverage because it makes the work I did this morning fully end-to-end.

**Files to touch:**
- `ui/js/app.js` — `sendUserMessage()` adds `turn_id: state.lastTurnId` to the WS payload around L4906
- `ui/js/narrator-audio-recorder.js` — exposes `_currentTurnId()` accessor or stores last turn_id on `state.lastTurnId` after each upload
- Possibly `ui/js/state.js` — add `lastTurnId` field

### Option B — #56 Correction-applied Phase 3 (~4-6 hrs)

Spec is at `BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01_Spec.md`. Needs `correction_parser.py` (regex-first, no LLM) + `projection_writer.apply_correction` + new composer that surfaces actual change ("Got it — I've changed that to two children. Apologies for the confusion."). High impact for ELL narrators. Currently corrections are detected but never applied to the data layer.

### Option C — #50 Mic modal Phase A only (~2-3 hrs)

Wire mic button to open existing FocusCanvas in listening mode. The full mic-modal spec is 5 phases / ~10-13 hrs total; Phase A alone is the smallest entry point. Spec at `BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01_Spec.md`.

**My recommendation:** Option A first (small, completes a half-finished feature). Then Option B (high-impact ELL improvement). Then Option C (substantial design work — chunk it).

---

## Process improvement: keep dev and laptop in sync

The reason this handoff was needed: code changes flow dev → origin → laptop via git, but `.env` changes are in `.gitignore` and don't propagate. Two options going forward:

### Option 1 — manual mirror with checklist

Whenever `.env` changes on dev, append the same lines on the laptop. Keep an `.env.shared` file (gitignored too) that lists the exact diff to apply. This handoff is one example of that approach.

### Option 2 — split `.env` into shared + machine-specific

Most flags (HORNELORE_*, LOREVOX_*) are identical between machines. Tuning (DEVICE_MAP, PYTORCH_ALLOC_CONF, PORT, TTS_PORT, UI_DIR) is machine-specific. Two files:

```
.env.shared    # checked into git — identical on every machine, sourced first
.env           # gitignored — machine-specific overrides, sourced second
```

`scripts/common.sh` would do `set -a; source .env.shared; source .env; set +a`. Whenever a `HORNELORE_*` flag changes, it commits to `.env.shared` and propagates via `git pull` automatically.

**Recommendation:** Option 2 long-term, Option 1 (this handoff format) for now. If we keep doing this manually we'll drift again.

---

## Files at the time of this handoff

### On dev (workspace mount, MAG-Chris)

- HEAD: `0527f33`
- Tree clean (after my commits)
- All 5 new env flags present in `.env`
- `DB_PATH` and `TRANSFORMERS_CACHE` deleted from `.env`
- `.env.bak_*` backup saved before deletions

### Spec files banked recently

- `BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01_Spec.md` (#56 spec, 117 lines)
- `BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01_Spec.md` (#50 spec, 110 lines)
- `BUG-STT-PHANTOM-PROPER-NOUNS-01_Spec.md` (#55 spec, 78 lines)

### Implementation files modified today

- `server/code/api/services/peek_at_memoir.py` (#52 cross-session)
- `server/code/api/prompt_composer.py` (#54 read-bridge)
- `server/code/api/archive.py` (#58 audio_id kwarg)
- `server/code/api/routers/chat_ws.py` (#54 + #58 + audio_id lift + stories-captured wiring)
- `server/code/api/services/lori_communication_control.py` (#60 + #62)
- `server/code/api/services/story_preservation.py` (stories-captured FS mirror)
- `ui/js/app.js` (#53 + #61 + #63 + #54 saveProfile + #57 setNarrator hook)
- `ui/js/focus-canvas.js` (#51 scroll fix)
- `ui/js/facial-consent.js` (#57 per-narrator keys)

---

## If anything goes wrong

- **Stack won't start after pull:** `cd /mnt/c/Users/chris/hornelore && git diff HEAD~5 HEAD -- server/code/api/` — review last 5 commits worth of server changes for anything out of place
- **Memory echo doesn't render era stories:** verify `HORNELORE_MEMORY_ECHO_ERA_STORIES=1` is in `.env` before stack started; `grep "HORNELORE_MEMORY_ECHO" .runtime/logs/api.log` for the flag-on log marker
- **Stories-captured folder not appearing:** verify `HORNELORE_STORIES_CAPTURED_FS=1` is in `.env`; check `.runtime/logs/api.log` for `[preserve][stories-captured-fs]` marker
- **Cross-session identity not persisted:** verify `0527f33` actually pulled (the people-row read fallback is in `_build_profile_seed`)
- **Camera consent prompts the wrong narrator:** check `localStorage` keys via DevTools — should see `lorevox_facial_consent:<person_id>`, NOT just the legacy `lorevox_facial_consent_granted`

When in doubt: dry-run script is the source of truth. If a step PASSes, the underlying chain works.
