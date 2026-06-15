# WO-PARENT-KIOSK-01 — Parent-facing kiosk deployment

**Title:** Parent-facing kiosk deployment for Kent and Janice
**Status:** SCOPED — PARKED until pre-flight gates GREEN
**Date:** 2026-05-01
**Lane:** Parent-session readiness / deployment / UX hardening
**Source:** Chris's "kiosk mode" design memo (2026-05-01)
**Blocks:** Parent narrator sessions on a dedicated laptop until GREEN

## Browser decision

**Chrome kiosk first. Edge Assigned Access only if Chrome kiosk cannot be
locked down enough.**

Rationale: the entire WO-PARENT-SESSION-HARDENING-01 lane has been tested
in Chrome. Mic permission, camera consent, MediaPipe FaceMesh, WebSocket
reconnect, audio-output device pinning via `setSinkId()`, the Web Speech
API STT path — all proven against Chrome's behavior. Switching to Edge
for the kiosk would mean re-validating every one of those surfaces in a
browser that has subtly different mic/permission/audio handling. That's
risk we don't need at deployment time.

Chrome kiosk gives us:
- Full-screen lock (`--kiosk` flag)
- No tabs, no address bar, no back button (with `--no-first-run --no-default-browser-check --disable-features=...`)
- The same mic/camera/audio behavior the readiness pack has been validated against
- The same WebSocket / `setSinkId()` path Phase 4–5 of this WO depend on

Chrome's kiosk weakness vs Edge Assigned Access is OS-level lockdown:
Edge + Windows Assigned Access creates a true single-app session at the
user-account level, while Chrome kiosk runs inside a regular Windows
session. We compensate by:
- Removing the taskbar via Local Group Policy (`gpedit.msc`)
- Disabling Win+Tab, Alt+Tab, Win+E, Win+R via registry policy
- Hiding the desktop / start menu via shell replacement (Chrome itself becomes the shell on the `lori` user)

If that's still not tight enough during Phase 9 acceptance testing — i.e.
a parent could feasibly tab out by accident — we fall back to Edge
Assigned Access AND re-run the readiness pack against Edge to confirm
no behavioral regressions. That's the only condition that triggers the
Edge fallback.

---

## Mission

When Kent or Janice opens the laptop, the device behaves like a
single-purpose appliance: Lori, nothing else. No browser chrome, no
desktop, no narrator picker, no operator screens, no settings, no
choices. They open the lid, Lori is there, they talk.

This is not a feature. It's deployment discipline. The product can be
correct in development and unusable in their hands if the surrounding
OS and network bleed through.

The narrator-dignity-wins principle in CLAUDE.md applies directly:

> When a decision trades operational tidiness against narrator dignity,
> narrator dignity wins.

A kiosk that works 99% of the time and panics them 1% of the time has
already failed.

---

## Core rule

The kiosk is one-laptop-per-narrator. Kent has his laptop. Janice has
hers. Neither laptop has any other narrator's data on it. Neither
laptop has a narrator picker. The default narrator is hardcoded to the
laptop owner; the only way to change it is the operator escape hatch
(Chris, Tailscale, SSH).

Trying to share one laptop across two narrators reintroduces a
selection surface, and selection surfaces are a failure mode for
elderly users with possible cognitive decline. Solved by buying the
second laptop, not by adding a "who are you?" prompt.

---

## What changes vs the current developer environment

| Surface | Dev | Kiosk |
|---|---|---|
| OS visible | Yes (Windows desktop, taskbar, start menu) | No (Chrome full-screen kiosk only) |
| Browser chrome | Yes (tabs, address bar) | No |
| Browser engine | Chrome (dev) | Chrome (kiosk) — same engine, no behavioral re-validation needed |
| Login | Password | Auto-login, no password |
| Stack startup | Manual `./scripts/start_all.sh` | Auto-start on user login |
| First UI screen | Operator tab | Cold-boot warmup screen → narrator session |
| Narrator selection | Picker popover | Hardcoded to laptop owner |
| Operator controls | Visible | Hidden behind escape hatch |
| Camera | On (FaceMesh affect) | Off in v1 |
| Audio output | OS default (drifts) | Pinned to laptop speakers |
| Mic | First-grant only | Preflight every session start |
| Updates | On | Deferred to maintenance window |
| Sleep | Default | Disabled during the day |
| Network | Any WiFi | Pinned to home WiFi + Tailscale |

---

## Hard stop conditions (RED — block deployment)

- Cold boot exceeds 5 minutes from lid-open to first Lori turn.
- Lid-cycle (close → wait 30s → open) doesn't recover the WS connection.
- Bluetooth headphone connect mid-session causes Lori's audio to silently route to the headphones.
- Mic disconnect mid-session leaves the UI in an indeterminate state with no operator-visible recovery path.
- Lori hangs for >30 min during an active session with no watchdog soft-restart.
- Parent sees ANY browser chrome, OS chrome, or operator surface during a normal session.
- Parent can navigate OUT of Lori (back button, address bar, alt-tab, start menu, system tray) by any single common gesture.
- Reset Identity / cross-narrator-leak / protected-identity bugs are still open per the parent-session-readiness pack.
- Watchdog beacon to Chris's monitoring endpoint is silent for >24h with no operator notification.

If any of these fire during the acceptance test: stop the deployment,
write the symptom, and treat the laptop as non-deployable until fixed.

---

## Pre-flight gates (must be GREEN before this WO starts)

These are upstream dependencies in other lanes. Don't open this WO's
implementation until each is closed:

1. **Parent-session-readiness pack GREEN** — TEST-01 through TEST-12 all PASS or AMBER, no FAIL, no hard-stop. Per `docs/test-packs/PARENT-SESSION-READINESS-V1.md`.
2. **Live re-test of "what do you know about me?"** — task #319, after `compose_memory_echo` Phase 1a is exercised end-to-end.
3. **Reset Identity for Kent + Janice** — task #318, run via UI clicks per narrator, confirm BB / projection / localStorage / person row / memoir all clear.
4. **BUG-DBLOCK-01 closed** — task #344, the long-held SQLite write lock that breaks chat turns during safety hooks.
5. **WO-LORI-SAFETY-INTEGRATION-01 Phase 2 landed** — LLM second-layer classifier; the deterministic Phase 1 hook is not enough by itself.
6. **WO-LORI-SESSION-AWARENESS-01 Phase 2 landed** — composer-side discipline guard for word/question caps. Already complete (task #285).
7. **Narration sample matrix shows no Lori-text-leakage regressions** — `--narration-only` run on the parent-session-readiness harness, confirming protected-identity values stay clean across all 4 sample sizes per the 3 fictional narrators.

---

## One-laptop-per-narrator decision

Buy two refurbished laptops. Reasonable spec floor:

- Intel i5 or Ryzen 5 equivalent
- 16 GB RAM (8 GB is too tight for the LLM)
- 256 GB SSD
- Built-in microphone + speakers (avoid external dongles)
- Camera (even though disabled in v1, hardware presence simplifies later opt-in)
- Windows 11 Home or Pro (Pro for Assigned Access)

Estimated cost at time of writing: $400–$600 each refurbished.

If you balk at two laptops: the alternative ("Hi, who am I talking to?") requires speaker-ID infrastructure that doesn't exist and would take weeks to build correctly. Cheaper to buy hardware.

---

## Implementation surface

```
launchers/
  kiosk/
    setup_kiosk.ps1                  # one-shot Windows setup script
    start_kiosk.cmd                  # called by the kiosk shell on login
    chrome_kiosk_args.txt            # canonical Chrome launch flags
    watchdog.ps1                     # stuck-state watchdog daemon
    health_beacon.ps1                # periodic heartbeat to Chris
docs/
  deploy/
    KIOSK-SETUP.md                   # operator-facing setup runbook
    KIOSK-RUNBOOK.md                 # what to do when something breaks
    KIOSK-NARRATOR-LOCK.md           # how the per-laptop narrator lock works
ui/
  kiosk/
    boot.html                        # cold-boot warmup screen
    boot.js
    boot.css
    audio-selftest.html              # post-boot mic + speaker check
    audio-selftest.js
server/code/api/routers/
  operator_kiosk_health.py           # health endpoint for watchdog beacon
.env.example                         # add HORNELORE_KIOSK_MODE flag
```

---

## Phase plan

### Phase 1 — OS setup (per-laptop checklist)

Deliver `docs/deploy/KIOSK-SETUP.md` and `launchers/kiosk/setup_kiosk.ps1`.

Per laptop:

1. Fresh Windows install. Skip Microsoft account; create local user `lori`.
2. Configure auto-login for `lori` (no password prompt at boot).
3. Install WSL2 + Ubuntu 22.04 + Hornelore stack per existing repo setup.
4. Install Google Chrome (NOT Edge — see "Browser decision" above).
5. Configure Chrome kiosk launch on the `lori` user:
   - `chrome.exe --kiosk --no-first-run --no-default-browser-check --disable-features=Translate,InfobarComponent --start-fullscreen <warmup-url>`
   - Disable taskbar / Win+Tab / Alt+Tab / Win+R via Local Group Policy (`gpedit.msc` → User Configuration → Administrative Templates → Windows Components → File Explorer + Start Menu and Taskbar).
   - Optional: replace the Windows shell for the `lori` user with `chrome.exe` so the desktop never renders. Registry: `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Shell` per-user override.
6. Pin audio output to built-in speakers (control panel → sound → set as default → check "exclusive use" off).
7. Disable sleep, hibernate, screen timeout (settings → system → power & battery).
8. Defer Windows updates by 365 days; set active hours 6 AM – 11 PM.
9. Disable Cortana, news widget, lock-screen tips, taskbar everything.
10. Install Tailscale, log in to Chris's tailnet, enable subnet routing if needed.

**Acceptance:** Power-on the laptop, observe direct boot into Edge full-screen with no intervening UI, no taskbar, no notifications.

### Phase 2 — Stack auto-start + cold-boot warmup screen

Deliver `launchers/kiosk/start_kiosk.cmd` and `ui/kiosk/boot.html` + `boot.js`.

`start_kiosk.cmd` runs on login (Task Scheduler):
1. Launch WSL → `start_all.sh` in detached mode (existing script).
2. Open Chrome in kiosk mode at `http://localhost:8082/ui/kiosk/boot.html` (per `chrome_kiosk_args.txt`).
3. The boot page polls `/api/ping` and `/api/operator/stack-dashboard/system-status` every 3s; renders progress copy:
   - 0–60s: "Lori is waking up..."
   - 60–120s: "Lori is getting her voice ready..."
   - 120–240s: "Lori is finding her thoughts..."
   - >240s: "Lori is taking longer than usual. We'll wait."
4. When the API responds AND the LLM warmup probe responds in <30s, redirect to the narrator session URL with the laptop's hardcoded narrator pre-selected.

The warmup screen never says "loading" or "starting" — narrator-friendly copy throughout. No technical errors visible. If the stack fails to come up after 8 minutes, the screen shows: "Lori is having trouble waking up today. Chris has been notified." (silent beacon to Chris).

**Acceptance:** Cold boot from lid-open to first Lori turn ≤ 5 minutes, with a continuously-updating warmth-friendly screen the entire time. Never blank, never an error.

### Phase 3 — Per-laptop narrator lock

Deliver `docs/deploy/KIOSK-NARRATOR-LOCK.md` and a small UI glue layer.

The kiosk URL embeds the narrator's person_id. On boot.html → narrator-session redirect:

1. The redirect URL is `http://localhost:8082/ui/hornelore1.0.html?kiosk=1&narrator=<KENT_PID>`.
2. `app.js` already supports `?narrator=` URL parameter. The `kiosk=1` flag triggers a new code path:
   - Suppress the narrator switcher chip (set CSS `display:none`).
   - Suppress the operator tab.
   - Suppress the Memory Exercise / Companion posture pills (lock to Life Story).
   - Suppress the Bug Panel UI button.
   - Suppress all session-style picker tiles (lock to a sensible default — Warm Storytelling is the recommendation for older narrators).
3. The narrator's display name is rendered in a soft warm header ("Hi Kent"), not a chip.
4. Reset Identity is hidden in the BB popover (kiosk doesn't expose Bio Builder at all).

**Acceptance:** Walk-the-flow test: every clickable surface in the kiosk view is either Lori's chat input, mic, camera (off in v1), or pause/break. No operator-side surface is reachable through any single gesture.

### Phase 4 — Audio + mic resilience

Deliver `ui/kiosk/audio-selftest.html` and `audio-selftest.js`.

Wraps the existing WO-AUDIO-READY-CHECK-01 preflight with kiosk-tuned UX:

1. Before each session opens (NOT just first-launch), run a 5-second self-test:
   - Lori says: "Tap once if you can hear me."
   - If the narrator taps → continue.
   - If 30s pass with no tap → loop the test once.
   - If still no tap → escalate to "Let me know if you'd like to skip this — just tap." If skipped, log a warning to the health beacon.
2. Mic preflight: continuous level meter visible during the 5s. If RMS is below 5% threshold, surface a friendly "I'm having trouble hearing you. Let me try again."
3. Audio output device pin: query `navigator.mediaDevices.enumerateDevices()` on boot, log all devices to the beacon, and use `setSinkId()` to pin output to the built-in speakers. Re-pin on every session start (defends against Bluetooth swap).

**Acceptance:** Bluetooth headphones connected mid-session do NOT silently steal Lori's audio. Audio output stays on built-in speakers throughout. Mic preflight catches a muted/disconnected mic before Lori starts talking into the void.

### Phase 5 — Lid-cycle + WS reconnect resilience

Deliver hardened reconnect logic in the chat WS layer.

When the laptop sleeps (lid close) and wakes (lid open), the WebSocket connection drops. The current dev-mode behavior is undefined. Kiosk-mode:

1. Detect WS close events; immediately render a soft "Lori paused while you closed the laptop. Just a moment..." overlay.
2. Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s).
3. On reconnect, fetch the most recent transcript turn timestamp from `/api/memory-archive/turn?narrator_id=...&limit=1`.
4. Render a warm continuation: "Welcome back. We were talking about [last thread anchor]." Use the existing thread_anchor logic from WO-9.
5. If reconnect fails after 5 attempts, escalate to the watchdog (Phase 6).

**Acceptance:** Open lid, start session, send 3 turns. Close lid for 30 seconds. Open lid. Continue conversation. Lori responds within 5 seconds without operator intervention.

### Phase 6 — Stuck-state watchdog + soft-restart

Deliver `launchers/kiosk/watchdog.ps1`.

A separate Windows process that monitors:
- `/api/ping` returns 200 in <5s
- API process is alive (PID check)
- TTS process is alive
- Last narrator turn timestamp from the archive

Trigger conditions for soft-restart:
- API ping fails 3 times in a row
- TTS process is dead
- No narrator turn in 30 minutes during an "active session" (active = last operator beacon shows session_started=true)
- LLM warmup probe takes >60s on a hot stack

On trigger:
1. Show the warmup screen (kiosk navigates Edge to boot.html via remote command).
2. Soft-kill the relevant subprocess (NOT the LLM — restarting the model takes 4 minutes).
3. Restart it.
4. When healthy, navigate back to the narrator session.

The watchdog NEVER disturbs the parent for diagnostic reasons. They see the warmup screen ("Lori needed a moment, we're back!") and the conversation resumes if the watchdog can recover, or the screen says "Chris has been notified" if not.

**Acceptance:** Manually `kill` the API process during an active session. Within 60 seconds, the kiosk shows the soft-restart UI, the API restarts, and the narrator can continue talking.

### Phase 7 — Tailscale + remote health visibility

Deliver `server/code/api/routers/operator_kiosk_health.py` and `launchers/kiosk/health_beacon.ps1`.

Two layers:

1. **Tailscale mesh** — install Tailscale on each kiosk and on Chris's phone/laptop. No code change required; this gives Chris private SSH and HTTP access to each kiosk from anywhere.
2. **Periodic beacon** — `health_beacon.ps1` runs every hour and POSTs a small JSON payload to a Chris-controlled endpoint over Tailscale. Payload: `{narrator_id, last_session_ts, llm_warm, tts_warm, last_error_class, audio_devices_count, watchdog_triggers_24h}`. Zero transcript content. Zero conversation data. Just liveness.
3. **Operator dashboard** — `operator_kiosk_health.py` exposes a `/api/operator/kiosk-health/summary` endpoint that aggregates beacons from every kiosk and renders a card in the existing Bug Panel dashboard (gated behind `HORNELORE_OPERATOR_KIOSK_HEALTH=0` default-off, same pattern as the other operator surfaces).

**Acceptance:** From Chris's phone, over Tailscale, open the operator dashboard and see both kiosks (Kent's, Janice's) with last-session timestamps and warmth state. If a kiosk goes silent for >2 hours during the day, an alert badge appears.

### Phase 8 — First-launch supervised onboarding

Each parent's first session is supervised by Chris in person.

Walkthrough script (Chris-facing, in `KIOSK-RUNBOOK.md`):

1. Hand the laptop to the parent.
2. Open the lid. Watch the warmup screen progress.
3. When Lori greets, sit beside them and let her introduce herself.
4. The parent taps the audio self-test. Confirm they can hear Lori clearly.
5. Lori asks what they'd like to start with — let them pick.
6. After ~5 minutes, Chris quietly excuses himself.
7. Chris monitors via the operator dashboard from another room.

This phase is procedural, not code. The deliverable is the runbook and a 30-minute scheduled session per parent.

**Acceptance:** Each parent has had a successful 15-minute first session, ended with them not panicked, ideally pleasantly surprised. Chris records observations in a `docs/deploy/parent_first_launch_<date>.md` file (NOT the transcript — observations only).

### Phase 9 — Acceptance gate

Run the full kiosk acceptance test pack (deliver `docs/test-packs/KIOSK-DEPLOYMENT-V1.md`):

1. Cold-boot test: lid-open to first Lori turn ≤ 5 minutes
2. Warmth-screen test: every progression message visible, no error language
3. Lid-cycle test: close 30s, reopen, conversation resumes <5s
4. Audio drift test: connect Bluetooth headphones mid-session, audio stays on built-in speakers
5. Mic preflight test: muted mic detected before session start
6. Stuck-state test: kill API mid-session, watchdog recovers within 60s
7. No operator leakage test: walk every reachable surface, confirm no operator UI visible
8. Narrator lock test: cannot navigate to a different narrator by any single gesture
9. Tailscale test: from phone, open dashboard, see kiosk health
10. Privacy test: confirm no transcript content in any beacon payload

GREEN on all 10 = parent-session-ready. Any FAIL = block deployment.

---

## Safety / dignity constraints

The kiosk MUST enforce:

- Never expose a narrator to an OS error message. Wrap every error in narrator-friendly copy or hide it.
- Never expose a narrator to a "loading..." with no progress. Always a warmth-friendly progressive message.
- Never let a narrator navigate out of Lori. Single-purpose appliance, period.
- Never silently lose audio (Bluetooth swap, device drift). Pin the device, re-pin on session start, alert if it slips.
- Never silently fail. Watchdog escalates to beacon, beacon notifies Chris.
- Never collect content data (transcripts, identity, conversation) in the health beacon. Liveness only.
- Never expose Reset Identity, Bio Builder, Bug Panel, or any operator surface in kiosk mode.
- Never allow the parent to switch to another narrator. The laptop IS the narrator's laptop.
- Never run a Windows feature update during a session. Active hours respected.
- Never re-prompt for camera or mic permission mid-session. Pre-grant during setup.
- Never display a "Lori is broken" message. Display "Lori is having trouble waking up today" or similar warmth-preserving copy.

---

## Acceptance gate for this WO

This WO is complete when:

1. Two laptops are physically deployed (Kent's and Janice's), each with the kiosk environment.
2. Each laptop passes the Phase 9 acceptance test pack (10/10 GREEN).
3. The pre-flight gates (TEST-01–12 GREEN, #318/#319 closed, BUG-DBLOCK-01 closed, etc.) are all GREEN.
4. Chris's operator dashboard shows both kiosks reporting healthy.
5. Both parents have had their supervised first session (Phase 8).
6. The runbook (`docs/deploy/KIOSK-RUNBOOK.md`) exists and Chris has used it once to recover from at least one simulated failure.

---

## Scope explicitly NOT in this WO

- Photo upload from kiosk (parents can't curate photos in kiosk mode in v1; Chris pre-loads)
- Video recording (still off per privacy commitment)
- Voice-ID routing (one laptop per narrator instead)
- Multi-narrator support on one device
- iOS / Android equivalents (Windows kiosk only)
- Cloud sync of transcripts (local-first commitment from README)
- Camera-on affect detection (off in v1, deferred to opt-in)

---

## Dependencies

- **Hardware:** 2× refurbished Windows laptops, ~$1000 total budget
- **Software:** Existing Hornelore stack, Microsoft Edge, Windows 11 Pro, Tailscale (free tier)
- **Network:** Home WiFi, Tailscale tailnet
- **Time:** ~1–2 weeks of focused implementation after pre-flight gates close

---

## Suggested commit sequence

```
feat(kiosk): WO-PARENT-KIOSK-01 Phase 1 — OS setup runbook + PowerShell setup script
feat(kiosk): WO-PARENT-KIOSK-01 Phase 2 — cold-boot warmup screen (boot.html/js/css)
feat(kiosk): WO-PARENT-KIOSK-01 Phase 3 — per-laptop narrator lock (?kiosk=1 URL param + suppress operator surfaces)
feat(kiosk): WO-PARENT-KIOSK-01 Phase 4 — audio self-test + output device pin
feat(kiosk): WO-PARENT-KIOSK-01 Phase 5 — WS reconnect resilience for lid-cycle
feat(kiosk): WO-PARENT-KIOSK-01 Phase 6 — stuck-state watchdog + soft-restart
feat(kiosk): WO-PARENT-KIOSK-01 Phase 7 — Tailscale + health beacon endpoint
docs(kiosk): WO-PARENT-KIOSK-01 Phase 8/9 — runbook + acceptance test pack
```

---

## Revision history

- v1, 2026-05-01 — initial scope. Authored after Chris's design memo
  laying out the kiosk concept. 9 phases covering OS setup through
  acceptance test pack. Pre-flight gates explicitly listed so
  deployment doesn't start until parent-session-readiness GREEN.
