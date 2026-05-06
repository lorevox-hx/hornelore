# Memory Appliance Frontier — Forward-Looking Scoping Memo (2026-05-05)

**Status:** RESEARCH MEMO. Not a WO yet. Forward-looking scoping doc to capture the post-parent-session frontier so the work is named, surveyed, and ready when its time comes.

**Authored:** 2026-05-05 night shift, by Chris + Claude.

**Reading audience:** Chris, future agents (so the next agent doesn't re-derive this from scratch), eventual operator-onboarding documentation.

**Trigger:** Chris's 2026-05-05 message naming the post-parent-session roadmap shift:

> *"from: 'Can Lori hold continuity?' → to: 'Can Lorevox become a stable memory appliance?'"*

This memo names the seven concrete problem surfaces that compose "memory appliance" and surveys the existing infrastructure each one builds on.

---

## What "memory appliance" means

A memory appliance is not a chatbot. It's a device the narrator can sit down at, log in (if at all), and carry on a memoir conversation that survives:

- Lid-close mid-sentence
- Network drops mid-Lori-response
- Power loss + reboot
- Multi-day gaps between sessions
- The narrator forgetting how to start
- The narrator forgetting they're mid-session
- The operator being unavailable for support during the session

The narrator doesn't think of it as software. They think of it as the place they go to tell their story. The appliance carries the continuity, not them.

This is a different posture than "a chatbot that remembers things." A chatbot can fail open; a memory appliance must fail closed AND fail calm.

## Seven concrete problem surfaces

Each surface gets named, scoped, and mapped to what already exists vs. what needs building. None of these are pre-parent-session blockers — they're the next frontier after Lane 2 (parent-session readiness) is closed.

### 1. Kiosk mode

**The problem.** Janice or Kent sits down at the laptop; the laptop is already pointed at the right narrator's session, no operator setup needed, no "click here to start." The browser is in a posture where the only thing on screen is the narrator chat. They can talk; they can read; they cannot accidentally browse to gmail, click into a settings menu, lock themselves out of audio permissions, or close the tab and lose the session.

**Existing infrastructure.**
- Hornelore is a single SPA at `ui/hornelore1.0.html` — load it, narrator is in.
- `LV_INLINE_OPERATOR_BUBBLES=0` already gates operator-side debug strings out of narrator view.
- Operator picker for session style + facial consent + voice recording controls is already separable from the narrator surface.
- A `state.role` check (operator vs narrator) exists at most UI mount points.

**What needs building.**
- A `/narrator-room/<person_id>` URL pattern that loads a chrome-stripped view: no Bug Panel, no operator tabs, no session-style picker, no facial-consent banner (operator pre-set), no STT toggle (operator pre-set). Just chat + microphone status indicator + clock + the timeline render (when WO-TIMELINE-RENDER-01 lands).
- Browser kiosk-mode launch wrapper. On Windows: a `.bat` that launches Chrome with `--kiosk --app=http://localhost:8000/narrator-room/<person_id>` — disables address bar, full-screen, can't be exited without alt-F4 or a hidden gesture.
- Operator gesture to exit kiosk (corner-tap × 5 in 3 seconds, hidden affordance) so a non-technical narrator can't trip it.
- Pre-session checklist: operator opens BB, confirms basics + region + heritage tags, picks session style, hits "Start Narrator Room" → `.bat` fires, narrator can sit down.

**Scope sizing.** Medium. ~2-3 days. Most of the substrate exists; the URL routing + the chrome-stripped view + the launch wrapper are the work. No model changes, no DB changes.

**Cross-references.** Composes with WO-PARENT-SESSION-LONG-LIFE-HARNESS-01 spec (parked) which already scoped a long-running session loop.

### 2. Lid-close recovery

**The problem.** Narrator closes the laptop mid-conversation (intentionally — they need to step away — or unintentionally — they bumped it). When they re-open, the session must resume cleanly. Lori must NOT cold-start; the narrator must NOT see "your session expired"; their last 30 seconds of audio (if STT was mid-stream) must NOT vanish.

**Existing infrastructure.**
- Backend SQLite is durable; turns committed up to lid-close persist.
- `archive.add_turn()` writes are atomic per-turn (single SQLite INSERT + COMMIT).
- WO-PROVISIONAL-TRUTH-01 Phase A read-bridge (landed 2026-05-04) means Lori reads from canonical + provisional truth on every turn, including the first turn after restart.
- Story preservation (WO-LORI-STORY-CAPTURE-01 Phase 1A, landed 2026-04-30) writes story_candidate rows persistently per turn; lid-close doesn't lose preserved stories.

**What needs building.**
- **Heartbeat write to a `narrator_session_state` table every N seconds** (probably 5s) with the most recent turn_id, the current era, the audio chunk index (if STT mid-stream), the turn-mode the dispatcher was in. Persists across lid-close.
- **Resume detector on session_start.** When a narrator card opens AND the heartbeat row is < 1 hour old, treat this as a resume rather than a new session. Hand off to the continuation paraphrase composer (BUG-LORI-SWITCH-FRESH-GREETING-01 Phase 2) with the saved era + last narrator turn.
- **STT chunk-level recovery.** This is the harder one. If STT was mid-utterance when the lid closed, the partial transcript needs to either land as a turn OR be discarded cleanly. Probably: on lid-close-detect (visibility API event in the browser), force-finalize the current STT chunk and submit; if the submit fails, drop it (rather than carrying it across the gap and producing weird half-turns).
- **Turn-grouping continuity.** Multi-utterance narrator turns (narrator says one thing, pauses, says another, all before Lori responds) need a session_id that survives lid-close. Current `session_id` lives in browser state.
- **Audio-recording continuity.** Per-turn .webm captures (from WO-AUDIO-NARRATOR-ONLY-01) need a folder-rotate strategy that survives lid-close. The clip mid-recording at lid-close is lost; that's acceptable. Subsequent clips post-restart land in the same session folder.

**Scope sizing.** Medium-large. ~4-5 days. The heartbeat + resume detection are smaller; STT mid-stream recovery is the time-sink because browser audio capture state is fragile under tab/lid lifecycle events. Probably worth a separate WO that scopes only the STT-survival piece.

### 3. Session resurrection (cold backend restart)

**The problem.** Backend goes down (operator restarted the stack to apply a patch; power loss; OS update). Browser is still open on the narrator chat. Backend comes back up. Browser refreshes (manually or auto). Lori picks up where she was — same era, same turn, same continuation paraphrase, same identity.

**Existing infrastructure.**
- Same persistence story as lid-close — SQLite is durable.
- `_build_profile_seed` reads canonical + provisional truth on every turn — so Lori's identity awareness is rebuilt from the DB, not from in-memory state.
- WebSocket reconnection logic in `chat_ws.py` already handles transient drops.

**What needs building.**
- **Backend-up detection in the frontend.** Browser polls `/api/healthz` on intervals; when it goes from down to up, fire a "session resurrection" path: re-fetch narrator state via `/api/narrator/state-snapshot`, re-fetch the welcome-back/opener (continuation paraphrase Phase 2 path), present a small narrator-friendly notification ("Lori was paused — she's back now" — visual only, no auto-text).
- **Auto-refresh option.** Operator pre-flag enables auto-refresh on backend-up. For the kiosk-mode case, operator wants this on by default. For dev testing, operator wants it off.
- **WebSocket re-establishment with idempotency.** When the WS reconnects, the chat_ws server needs to know which turns have been durably committed AND which the client thinks are committed. The current per-turn turn_id provides idempotency for `archive.add_turn` (verified 2026-04-30 polish patch). Extend the same pattern to STT chunks + Lori response delivery.
- **Backend startup health gate.** Per CLAUDE.md "cold boot ~4 minutes" — narrator-facing healthz must not return 200 until LLM is warm AND extractor can serve a real request. Already partially in place (warmup probe); needs to be gated explicitly so the resurrection-detect doesn't fire prematurely.

**Scope sizing.** Medium. ~3 days. Most infrastructure exists; the work is wiring the resurrection-detect + warm-gated healthz + the visual-only "Lori was paused" indicator (must follow design principle 2 — narrator-facing language, not "backend reconnected").

### 4. Narrator-only startup

**The problem.** A narrator who isn't tech-comfortable can sit down at the appliance and start talking without help. No login dialogs, no dropdown of narrators, no "click here." If multiple narrators share the appliance (Kent and Janice both use the same laptop in different rooms), there's a single visual identity affordance ("Are you Kent or Janice?") at start; otherwise auto-launch.

**Existing infrastructure.**
- `lv80SwitchPerson()` already handles narrator switching via UI.
- Active narrator state persists in localStorage (`lv_active_person_id`).
- `/api/interview/opener` already differentiates first_time vs welcome_back.

**What needs building.**
- **Single-narrator default mode.** When `data/active_narrator.txt` (or a similar config file) names exactly one person_id, the appliance launches into that narrator's room directly. Operator changes narrators by editing the config file (not a UI flow).
- **Multi-narrator picker (only when needed).** When more than one person_id is in `data/narrators/`, show a SHORT visual picker on launch: large narrator names, large faces (if photos exist), tap to enter. No login, no password, no operator credentials.
- **Picker visual discipline.** Narrator names rendered narrator-side (in their preferred form, not formal). Photos sized large. Tap targets at least 80px × 80px (older-adult fingers, possible vision/dexterity decline). Same posture as Lori-clock variant B (operator-tested visual scale for older narrators).
- **Sleep / wake gesture.** Tap-to-wake on the appliance. Long-press-to-sleep (for narrators who want to step away mid-session without lid-close). Sleep mode keeps the heartbeat alive but stops STT and stops Lori responses.

**Scope sizing.** Small-medium. ~2-3 days. Most of the work is UI + config-file conventions. No backend changes.

### 5. Timeline visible artifacts

**The problem.** The narrator can SEE their own timeline accumulating. Photos pinned to years. Stories anchored to eras. Their own quoted words ("you said: 'we used to walk the elbow Woods'") rendered next to the year they happened. The accumulating artifact is a visible reward — they're not just talking into the void; they're building something they can look at, share with grandkids, print out at the end.

**Existing infrastructure.**
- WO-TIMELINE-RENDER-01 spec landed; render endpoint scoped.
- WO-TIMELINE-CONTEXT-EVENTS-01 Phase A scaffolding banked tonight (this session).
- `story_candidates` table (migration 0004) already accumulates narrator-quoted stories with era + year metadata.
- `photos` table (migration 0001) holds photos with EXIF + GPS + provenance.
- WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c (spec) groups recent turns by era.

**What needs building.**
- **WO-TIMELINE-RENDER-01 implementation.** Read-only render endpoint behind `HORNELORE_TIMELINE_RENDER_V1=0`, narrator-visible from v1, decade-precision rendered with uncertainty preserved.
- **Frontend timeline view.** A new tab in the narrator room (or maybe the always-visible right column) that shows the timeline as it grows. Era-grouped accordion; current era expanded; photos + stories + facts + quoted excerpts all rendered as small visual artifacts.
- **Real-time artifact updates.** When narrator says something that gets preserved as a story_candidate (or extracted as a profile fact), the timeline updates within the next turn. Visible feedback: "you just added something."
- **Print / export view.** A narrator-presentable export that's not the operator's memoir.docx but a cleaner, narrator-side "your story so far" PDF. Possibly the same memoir export with narrator-friendly framing.

**Scope sizing.** Large. ~5-7 days for v1. Most infrastructure exists in scaffolding; the rendering + the real-time update wiring + the narrator-presentable export are net-new work. WO-TIMELINE-RENDER-01 is the umbrella; the timeline-context Phase A scaffolding (banked tonight) is a substrate.

### 6. Memoir continuity

**The problem.** A narrator who has had 30 conversations with Lori across 6 months has a coherent memoir, not a list of session transcripts. Eras are filled with their own words. Names appear consistently. Dates resolve to actual years. The same story isn't re-asked across sessions. The grandkids reading it don't see "session 4 turn 12 — Mary said..." they see "Earliest Years — Mary was born in Minot in 1940 and grew up walking three blocks to the brick schoolhouse..."

**Existing infrastructure.**
- WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c spec covers the per-session readback.
- Memoir export already exists (TXT + DOCX paths).
- Story preservation already captures era-anchored stories.
- Promoted truth pipeline already promotes provisional → confirmed identity facts.

**What needs building.**
- **Cross-session memoir aggregator.** A new service that pulls the full archive — every session, every story_candidate, every promoted truth, every photo — and produces a coherent narrative grouped by era. Deterministic; no LLM rewrite. The narrator's words stay the narrator's words.
- **Conflict resolution for cross-session contradictions.** Narrator said "I had two children" in session 4 and "three children" in session 18. The aggregator surfaces both as a flagged ambiguity for operator review, doesn't silently pick one.
- **Repetition suppression.** When the same story appears across multiple sessions, the aggregator picks one canonical version (most-recent? longest? operator-promoted?) and notes the others as "also told in session N."
- **Session-boundary-free reading experience.** The export reads as one continuous memoir, not a series of dated chats. Date metadata is operator-side; the narrator-facing export is era-grouped, not session-grouped.

**Scope sizing.** Large. ~5-7 days. The aggregator is the substantive work; conflict resolution + repetition suppression are tricky because they require some judgment about which version to keep. Probably an operator-review-queue pattern: aggregator surfaces ambiguities; operator picks; aggregator regenerates the export.

### 7. Calm failure handling

**The problem.** When something goes wrong — backend down, microphone permission denied, STT garbled, LLM produces an error response, photo upload fails — the narrator does NOT see "Error 500: WebSocket connection refused at chat_ws.py:227." They see calm narrator-side language that doesn't blame them, doesn't ask them to do something technical, and doesn't break their flow.

**Existing infrastructure.**
- Safety overlay (`safety-ui.js`) already has narrator-friendly "I'm hearing something I want to make sure I get right" language for distress turns.
- WO-LORI-SAFETY-INTEGRATION-01 Phase 1+2 already routes safety-triggered turns through warm composers.
- `default-safe fallback` (chat_ws.py L206-228, landed 2026-04-29) already routes scan_answer failures to a safe interview turn-mode.
- `LV_INLINE_OPERATOR_BUBBLES=0` already retired operator-tone bubbles from narrator view.

**What needs building.**
- **Calm-error vocabulary library.** A `data/narrator_calm_errors/` JSON pack with narrator-friendly text for every failure mode. Examples:
  - LLM error → "Lori is thinking. Give her a moment, then try again."
  - WebSocket drop → "We lost the line for a second. Reading what you said again..."
  - STT permission denied → "I'd love to hear your voice. If you'd like, you can tap the microphone icon to allow it — or you can keep typing, that works too."
  - Photo upload failed → "That photo didn't make it across. We can try again whenever you're ready."
  - Backend cold-starting → "Lori is just waking up. Give her a minute."
  - Disk-full / capture failure → operator-side notification only; narrator sees nothing or a generic "give me a moment" delay.
- **Failure-mode dispatcher.** Frontend catches every error category (network / STT / camera / upload / backend / LLM-error / safety-classifier-failure) and routes to the calm vocabulary, NOT a `console.error`-shaped message.
- **Operator notification surface.** Errors that the narrator gets a calm version of ALSO get a real-detail version in the Bug Panel for operator visibility. Two channels, one event.
- **Auto-retry with calm waiting.** Many failures are transient. Backend WS drop → reconnect within 5s → never tell the narrator at all. Backend dropped > 5s → narrator-friendly notice. Backend dropped > 30s → narrator-friendly "let's pause for a moment, your story is saved" + heartbeat-resume path.
- **Sleep + retry instead of hard-error.** When in doubt, the narrator-side appliance sleeps gracefully ("give me a moment") rather than displaying an error. The system attempts recovery in the background.

**Scope sizing.** Medium. ~3-4 days. The calm-error vocabulary is small (15-20 errors × 2-3 sentence variants each = a JSON file). The dispatcher wiring is the substantive work; the operator notification surface is a small additive feature on the existing Bug Panel.

---

## Sequencing recommendation

Each surface stands alone, but they compose. A possible six-month roadmap (after parent-session readiness lands):

1. **Calm failure handling** — small, valuable, foundation for everything else. ~3-4 days.
2. **Session resurrection (backend restart)** — medium; adds visible resilience. ~3 days.
3. **Lid-close recovery** — medium-large; STT survival is the time-sink. ~4-5 days.
4. **Narrator-only startup** — small-medium; UI work. ~2-3 days.
5. **Kiosk mode** — medium; URL routing + chrome-strip + launch wrapper. ~2-3 days.
6. **Timeline visible artifacts** — large; biggest visible reward for narrators; depends on WO-TIMELINE-RENDER-01 + WO-TIMELINE-CONTEXT-EVENTS-01 + WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1c. ~5-7 days.
7. **Memoir continuity** — large; cross-session aggregator with conflict resolution. ~5-7 days.

Total: ~25-32 days of focused work spread across ~3 months in parallel with other lanes. Most surfaces have 1-2 day skeleton phases that can ship before full implementation.

## What does NOT belong in this frontier

Out of scope for "memory appliance," even though the question might come up:

- **Voice cloning / Lori speaking in family voices.** Lorevox does NOT do this. Audio captures the narrator's voice for archive purposes only; Lori's voice is its own.
- **Generative photo restoration / image enhancement.** Photos go in as the narrator provides them. No AI upscaling, no auto-colorization. Authentic over polished.
- **Auto-publishing to social networks / family blog plugins.** The export is local and operator-controlled. Sharing is a deliberate operator gesture, not an automatic feature.
- **Scheduled reminders / push notifications.** A memory appliance is opt-in by sit-down, not push-notified. The narrator chooses when.
- **Multi-user concurrent sessions.** One narrator at a time per appliance. No session multi-tenancy.
- **Cloud sync / multi-device continuity.** Local-first. The data lives where the appliance lives. Backup is the operator's job (backup script already exists per `scripts/archive/backup_lorevox_data.sh`).
- **Voice-print authentication.** "Sign in by speaking" — no. Operator sets up the appliance for a specific narrator; narrator just sits down and talks.

## Cross-references

- **CLAUDE.md design principle 2** ("No operator leakage") — every surface above honors this. Calm failure language is narrator-side; operator details go through Bug Panel.
- **CLAUDE.md design principle 6** ("Lorevox is the memory system; Lori is the conversational interface to it") — kiosk mode + timeline + memoir continuity are SYSTEM affordances, not Lori-side. Lori doesn't display the timeline; the appliance does.
- **CLAUDE.md design principle 8** ("Operator seeds known structure; Lori reflects what is there") — narrator-only startup, photo + timeline rendering, all rest on operator-seeded structure.
- **WO-PARENT-SESSION-LONG-LIFE-HARNESS-01** (parked) — already scoped a long-running session loop; aspects of lid-close + resurrection compose.
- **WO-TIMELINE-RENDER-01** — direct dependency for surface 6 (timeline visible artifacts).
- **WO-LORI-STORY-CAPTURE-01 Phase 1A** (landed) — dependency for surfaces 3 + 6 + 7.
- **WO-LORI-SAFETY-INTEGRATION-01 Phases 1+2** (landed) — dependency for surface 7.

## Status of this memo

This is a forward-looking research memo, not a WO. It does not propose code changes for tonight, this week, or this month.

When parent sessions are running cleanly with Janice and Kent and Lori is holding continuity reliably, this memo becomes the input to the next planning session — at which point Chris picks one surface, scopes a real WO, and the work begins.

Until then: this memo sits in `docs/specs/` as the canonical reference for "what comes after parent-session readiness."
