# WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01

**Status:** PHASES C1–C3 LANDED 2026-07-05 (same session as authoring; C4 review-polish + scale pass remains open, sized after live test)

**Landing summary (2026-07-05):**
- C1 — `services/photo_intake/metadata_trust.py` (classifier + Takeout sidecar parse; trust enum grew a fifth level `gps_only` during implementation), migration `0016_photos_metadata_trust.sql`, trust threaded into intake preview + upload (suspect scan dates never auto-fill `date_value`), clustering quarantines `suspect_scan`/`none` dates (`_photo_taken_dt` in `trip_photo_clustering.py`), intake UI trust badge + sidecar pairing in `photo-intake.js`.
- C2 — `services/photo_intake/ingest.py` (shared pipeline: dedupe → store → EXIF → sidecar → trust → row; `routers/photos.py` still carries its inline copy, consolidation deferred deliberately), `POST /api/trips/stops/{stop_id}/photos` (operator-truth link; EXIF cross-check per §3.2 — GPS >200 km or trusted date outside window ±3d keeps placement + method=operator but writes confidence 0.45 so it surfaces in the existing review queue), per-stop "+ photos" button in trip-tab.js with sidecar pairing + per-file trust readout. `stop_get` accessor added.
- C3 — migration `0017_photo_sessions_trip_scope.sql` (trip_id/trip_stop_id on photo_sessions, pre-0017 fallback in repo), selector allowlist param, `show_next` scopes to trip/stop links + grounds "place" with the operator-placed stop name, `template_prompt` MEDIUM tier now grounds on known place/date ("This one is from Prague.") instead of the generic line — never invents, entry buttons in Trip Tab (per-stop + per-trip) and narrator trips popover ("Look at photos from this trip together", shown only when linked photos exist). trip_story_links deferred to Phase D (chat-lane story_candidates, couples to WO-MEMOIR-STORY-CANDIDATES-WIRE-01) — trip↔memory traversal already works via photo links.
- Tests: `test_metadata_trust.py` (18), `test_trip_stop_upload.py` (9), `test_trip_photo_session.py` (9); 117 green across the trip+photo packs. Import-fallback fixes for the offline test env in `routers/trips.py` + `services/photos/repository.py`.
**Lane:** Trips Phase C (parent: `docs/wo/WO-TRIP-IMPORT-AND-CLUSTER-01_Spec.md`)
**Severity:** HIGH — this is the lane that turns the trip feature from "operator files photos" into "narrator tells the story of the photo," which is the point of the whole system.
**Related landed work:** photo intake EXIF pipeline (`routers/photos.py` + `services/photo_intake/`), photo elicitation lane (WO-LORI-PHOTO-SHARED-01 — `photo-elicit.html`, selector + template_prompt services, WO-10C silence ladder), trip photo links (migration 0015), EXIF clustering (`trip_photo_clustering.py`).

---

## 1. Motivation (Chris, 2026-07-05, paraphrased from the design conversation)

Going to the Media tab to upload, mark ready, come back, and cluster is operator-tolerable but wrong-shaped for the real workflows. The operator is looking at **Czechia → Prague 1** in the Trip Tab and holding a photo that belongs there. The upload should happen *at the stop*, and Lori should then be able to ask the narrator about it.

External validation gathered 2026-07-05:
- **Polarsteps** (dominant consumer travel-journal app): each "Step" is a canvas pinned to time+place; photos are added directly at the step. Nobody routes through a central library.
- **GoodTimes** (JMIR Aging 2024, AI multimodal photo album, older adults): AI asks Who-What-When-Where questions per photo; 92% positive experience, 85% found it aided recollection. Validates the "Lori asks about the photo" loop in exactly Lorevox's population.

## 2. The three photo-provenance classes (LOCKED — design must handle all three)

Chris's framing, verbatim intent: photos arrive with wildly different metadata trust depending on how they were captured and how they traveled to the machine.

| Class | Capture path | What the file actually carries | Trust posture |
|---|---|---|---|
| **P1 — Scanned film** | Old camera → print → scanner → upload | EXIF datetime = **scan date** (wrong decade), no GPS, no camera model or scanner model. Everything real is in the narrator's memory. | Metadata UNTRUSTED. Date/place come from operator placement + narrator memory via Lori. |
| **P2 — Digital camera era** | Camera → computer → (often Google Photos or similar) → upload | EXIF datetime usually present but suspect (camera clock drift, wrong timezone, never set after battery change). GPS almost never. Photo-manager round-trips may rewrite or strip tags. | Datetime PROVISIONAL. Good for ordering within a trip, weak for absolute placement. No GPS ⇒ time-only clustering cap already applies (0.8). |
| **P3 — Modern phone** | Android → Google Photos → **zip/individual download** → share; or iPhone (Melanie) → Apple ecosystem → **email/share** → download | At capture: rich EXIF + GPS. But the *export path* decides what survives: Google Takeout zips keep EXIF but put some metadata in **sidecar JSON**; messaging apps and email attachments frequently **strip EXIF entirely**; iPhone exports arrive as **HEIC** (already accepted by intake) or as stripped JPEG conversions. | Metadata trust depends on the export path, not the phone. Same photo can arrive pristine or naked. |

**Design consequence (the core insight):** metadata trust is a **per-file property that must be detected and recorded at intake, and consumed by clustering and by Lori** — not assumed from the upload surface. The existing `date_precision` + `location_source` columns are the right home; this WO adds detection + a `metadata_trust` classification and threads it through.

## 3. Locked design choices

1. **Stop-scoped upload = operator truth.** A photo uploaded at Czechia → Prague 1 gets its `trip_photo_links` row written immediately with `assignment_method='operator'`, `cluster_confidence=1.0`. No clustering pass needed for these. (Principle 8: the operator seeded it.)
2. **EXIF still runs on stop-scoped uploads — as a cross-check, not an authority.** If the file carries GPS/datetime that *contradicts* the stop (GPS >200 km from stop coords, or datetime outside trip window ±3 days), the UI shows a non-blocking mismatch flag ("EXIF says Vienna, 2026-06-02 — keep at Prague?"). Operator decision wins either way. Silent trust of either signal is forbidden.
3. **Scan-date detection (P1):** EXIF datetime is flagged `suspect_scan_date` when ANY of: (a) datetime within 30 days of upload date while the target trip is older than 1 year; (b) EXIF `Software`/`Make` matches known scanner/photo-manager strings; (c) datetime present but no camera `Make`/`Model` and no GPS and image dimensions match common scanner output. Suspect dates are **excluded from clustering time-score** (photo falls to GPS-only or operator placement) and stored with `date_precision='unknown'` unless the operator supplies one.
4. **EXIF-stripped detection (P3-degraded):** zero EXIF keys on a JPEG ⇒ `metadata_trust='none'`, same handling as P1 minus the scan flags.
5. **Google Takeout sidecar JSON:** when a `<name>.json` / `<name>.supplemental-metadata.json` file accompanies an uploaded photo (multi-file drop), parse `photoTakenTime` + `geoData` and use them at P3 trust when the image's own EXIF is absent. Sidecar parse is best-effort; never blocks upload.
6. **Narrator memory becomes the date/place source for P1 — via the elicitation lane, as provisional truth.** When Lori's photo conversation surfaces a when/where ("that was the summer before your father died, at Lake Chelan"), it flows through the existing extraction → provisional → operator review path (principle 5). It NEVER silently overwrites `photos.date_value`; it lands as a review-queue suggestion attached to the photo. The narrator is the author; the operator promotes.
7. **Lori's photo questions are grounded in what is known and silent about what isn't.** For a stop-scoped photo: "This one's from Prague." For a P1 scan with nothing: "Tell me about this one" — never a fake "This looks like the 1970s." (Principle: no system-tone, no invented context — ANTI-CONFABULATION RULE applies.)
8. **Narrator-ready stays the gate for narrator-facing surfaces** (BUG-238). Stop-scoped upload defaults `narrator_ready=1` — the operator is deliberately placing it into the narrator's trip — with a per-upload untick available.
9. **Both paths coexist.** Stop-scoped upload for deliberate placement; bulk intake + EXIF clustering for the 2,500-photo dump. Neither replaces the other.

## 4. Phases

### Phase C1 — provenance classification at intake (~0.5 day)
- `services/photo_intake/provenance.py` (pure): `classify_metadata_trust(exif, upload_context) → {trust: 'full'|'time_only'|'suspect_scan'|'none', reasons: [...]}` per §3.3–3.4.
- Persist `metadata_trust` (new column, migration 0016) + surface in intake preview UI ("48 EXIF tags, GPS ✓" / "⚠ date looks like a scan date" / "no metadata — placement is manual").
- Clustering consumes it: `suspect_scan`/`none` ⇒ time score 0 (photo routes to review or operator placement instead of confidently mis-clustering).
- Sidecar JSON parse (§3.5).
- Offline tests: scanner EXIF fixture, stripped JPEG, Takeout pair, pristine phone photo.

### Phase C2 — upload-at-the-stop (~0.5 day)
- `POST /api/trips/stops/{stop_id}/photos` (gated by HORNELORE_TRIPS): multipart upload → existing intake pipeline (dedupe by file_hash, EXIF, provenance) → photo row + operator-truth link → mismatch cross-check (§3.2) in response.
- Trip Tab UI: "+ Add photos" per stop; drop-zone accepts multi-file; per-file result row (thumb, trust badge, mismatch flag with keep/move buttons).
- Re-running bulk clustering never touches operator links (already guaranteed — lock-in test anyway).

### Phase C3 — trip-scoped Lori photo session (~1 day)
- Extend photo-elicit session create with optional `trip_id` / `trip_stop_id` filter; selector draws only linked, narrator-ready photos (cooldowns unchanged).
- `template_prompt` gains trip grounding: stop name + trip title + (trusted) date woven into tier-1 prompt; P1/none-trust photos get the ungrounded warm open (§3.7).
- Entry points: "Talk about these with Lori" per stop + per trip in Trip Tab; same button in the narrator room trips popover (narrator-safe wording).
- Memories land as story_candidates with `trip_story_links` row (table exists, unused until now) + photo linkage.
- When/where mentions → photo date/place suggestions in review queue (§3.6) — Phase C3 ships the capture; the review-surface polish may trail into C4.

### Phase C4 — review polish + scale pass (sized after C1–C3 live test)
- Bulk review queue improvements for the 2,500-photo set (pagination, keyboard confirm).
- Photo date/place suggestion review surface (promote → photos.date_value/location with provenance note).

## 5. Acceptance
1. Offline: provenance fixtures classify correctly; suspect-scan photo does NOT cluster on time; stop-upload writes operator link + survives re-cluster; trip-scoped session selects only that stop's photos; 0 regressions in existing photo + trip test packs.
2. Live (Chris): upload a real scanned print at a Spring 2026 stop → trust badge shows suspect/none, placement sticks; upload a phone photo at the wrong stop → mismatch flag fires; run a Lori photo session on Prague → grounded opener, story lands linked to trip + photo; Melanie iPhone HEIC via email → accepted, trust reflects the strip.
3. Principle sweep: no narrator-visible operator controls, no invented photo context from Lori, all memory-derived date/place goes through review — audited before close.

## 6. Stop conditions
- Any surface where Lori asserts unverified photo metadata as fact → hard stop (confabulation class).
- Elicitation-derived dates writing directly to photos truth without review → hard stop (principle 5 violation).

## Revision history
- 2026-07-05 — Authored from design conversation + web research (Polarsteps step model; GoodTimes JMIR Aging 2024). Three provenance classes locked per Chris's capture-path walkthrough (scanned film / digital-camera era / phone-with-lossy-export).
