# Session Handoff

Last updated: 2026-10-25

## Changes

- Built the FastAPI/SQLite backend with idempotent seeding and explicit reset.
- Added one-owner OpenCV capture, **markerless instance recognition**
  (`backend/app/recognition.py`: enrolled reference views matched with
  SIFT/ORB + homography, confidence threshold + runner-up margin + explicit
  unknown state), timestamped/smoothed object data, MJPEG streaming, fixture
  mode, and clean shutdown. The legacy ArUco recognizer remains only as a
  dev/test fixture (`APP_RECOGNIZER=aruco`).
- Added identity/object resolution (`identity_key`, replacing `marker_id` in
  the API), object enrolment from a photo (`POST /api/objects/enroll`),
  object listing, nested thread reads, validated
  one-level replies, message limits, idempotency keys, and server timestamps.
- Added disabled, OpenAI, and local Faster Whisper completed-file
  transcription adapters. Cloud secrets remain backend-only; the local path
  needs no API key.
- Built the React/TypeScript desktop UI with letterbox-aware overlays, real post
  previews, profile switching, camera-free thread browsing, polling, locked
  reply targets, microphone selection, recording, editable transcript review,
  draft retention, and explicit error states.
- Generated enrolment reference artwork (`objects/`), a markerless two-object
  fixture, and documented the demo-vs-pitch (native AR) split in the README.
- Documented setup, environment variables, reset, and the demo flow.
- Added a frontend voice-command layer on top of the transcription path:
  shared `useVoiceRecorder` hook with the
  mic choice persisted (`locus.micDeviceId`, pick the webcam/glasses mic —
  browser captures audio only, never the webcam's video); a global
  push-to-talk `VoiceControl`; a deterministic intent parser
  (`frontend/src/voiceCommands.ts`) for "post it / retry / cancel" in draft
  review, "open <object>", "reply to <author>", "enrol this as <name>"
  (starts the scan→review→Save flow), "yes that's it" (confirms the visible
  provisional sighting), and read-aloud via `speechSynthesis`
  (`frontend/src/speech.ts`). Speech alone never publishes: a post still
  needs "post it" or the Post button against the locked target, and
  ambiguous/unknown commands change nothing. Wake word is designed-for
  (single `activate()` entry point) but not built.
- Resumed the interrupted voice pass and fixed four integration edges: an open
  thread now routes global push-to-talk into a comment draft even before the
  composer exists; the target is locked when recording starts; voice
  confirmation refuses multiple provisional sightings; and a consumed
  voice-enrolment request cannot restart after reopening the creator. Recorder
  setup now also releases the microphone on partial startup failures.

## Current State

- Completed: working source, fixture demo, persistence, post/reply flow,
  multi-client update path, enrolment references, automated checks, and docs.
  **Creating new objects by looking (scan → review → save, plus add-views)
  is DONE** — verified by 32 backend tests, frontend tests/build, and a
  live fixture-server run (new object recognised high-tier at 0.944).
  Markerless instance recognition implemented (pending live re-verification).
- In progress: none.
- Blocked: no implementation blockers.

## Next Actions

- [ ] On the demo laptop, set the correct `APP_CAMERA_INDEX` and confirm both
  enrolled objects are recognised by appearance under venue lighting.
- [ ] Select the glasses microphone in the UI and verify permission/recording.
- [ ] With `APP_TRANSCRIPTION_PROVIDER=faster-whisper`, make one live microphone
  transcription before judging. The cached `medium` model and WebM API path
  are verified; OpenAI remains an optional cloud alternative.
- [ ] Open two browser windows and rehearse the three-minute script.

## Unresolved Decisions or Defects

- Meta Muse transcription was intentionally not implemented because no verified
  official endpoint/authentication example was supplied.
- Browser visual inspection was unavailable in this coding session. Layout was
  type-checked and production-built, but should be visually checked on the demo
  laptop at its actual resolution.
- The physical webcam and microphone were not available here; fixture
  recognition, disabled-provider behavior, and local WebM transcription were
  verified.
- Markerless change: new real-pixel tests live in
  `backend/tests/test_recognition.py` (fixture identity, swapped-position
  identity, unknown scene).

## Verification

- `.venv/bin/python -m pytest` — 8 passed. One upstream Starlette/AnyIO
  deprecation warning remains.
- `npm run test` — 4 passed across geometry and target-lock suites.
- `npm run build` — strict TypeScript and Vite production build passed.
- `npm audit` — 0 vulnerabilities.
- Live fixture server — both marker IDs detected with real corners; objects and
  actual seeded post previews resolved; built frontend returned HTTP 200.
- Live write/read — a Guest reply was created and observed by a separate API
  client, then `seed --reset` restored the known demo state.
- Not run: physical hardware and live provider transcription.

## Verification (matcher fixes + live enrolment, 2026-10-25)

- Phase 1: `_corners_plausible` now accepts partially-out-of-frame quads
  (convex + ≥20% visible) instead of the ±25% bound that rejected a
  397-inlier/0.94 match; CLAHE in enrol + detect; enrolment refs downscaled
  to ≤1280px + half-scale view; thresholds relaxed modestly (ratio 0.78,
  min inliers 10, min confidence 0.25); TTL 750→2000ms; temporal voting
  (high needs 2 hits, provisional 3) in `CameraService`.
- Phase 2: `POST /api/objects/enroll-live` burst-captures from the live
  feed (sharp/centred/diverse centre crops); UI enrols "by looking" —
  photo upload demoted to a dev/test `<details>` harness.
- Phase 3: tiered confidence end-to-end (`tier` on detections; provisional
  never auto-attaches, confirm via `POST /api/recognition/confirm`);
  high-confidence confirmed tracks bank new-angle crops (persisted to
  `APP_ENROLLED_DIR` + `object_fingerprints`), capped/cooldowned.
- `.venv/bin/python -m pytest` — **23 passed** (10 new in
  `test_live_enrollment.py`). `npm test` — 4 passed; `npm run build` clean.
- Live fixture server: poster 0.838 / book 0.786 high-tier (was 0.785 /
  0.571); `enroll-live` against the fixture feed created a new identity
  recognised at 0.928; banked-view PNGs persisted.
- Synthetic rotate/background test: single-view enrolment recognised at
  rotated (0.915), moved/new-background (0.909), and close/partial
  (0.863) viewpoints; unenrolled book-only scene and blank scene → `[]`.
- **Not run:** physical webcam + real ThermoFlask bottle (rotate 360°,
  leave/return, unenrolled similar bottle). Phase 4 (embedding spike)
  stays gated on that test failing. No new dependencies added.
- Stricter pass (later 2026-10-25, after live use showed recognition was
  too broad): high tier 15 inliers / 0.35 / ratio 0.75, provisional
  12 / 0.28; displayed confidence is now the current frame's raw value
  (was a sticky decaying max); non-homography fallback matches are
  capped at provisional (was a fabricated 1.0); track tier follows the
  current frame unless the user confirmed that identity. 25 pytest
  passed; live fixture still high-tier: poster 0.901, book 0.832.
- Enrolment UX fix (later 2026-10-25): live enrolment now shows a 4s
  countdown, a centre guide overlay on the camera (matching the centre
  70% crop that is actually captured), thumbnails of the exact enrolled
  crops with an explicit "open its thread" step, and capture diagnostics
  (frames sampled / views selected+enrolled / best sharpness) in both
  success and 422 responses. Enrolment keypoint gate loosened to 5
  (live only); recognition thresholds unchanged. 26 pytest passed;
  live fixture enrol-live returned 1 view from 8 sampled frames and the
  new identity recognised at 0.944.
- Real-bottle result (2026-10-25, user-tested): the matte-black bottle —
  enrolled from a phone photo, **never live-scanned** — is recognised
  roughly half the time. Accepted as-is for now; live-feed enrolment of
  the bottle is the expected improvement and remains untested. Phase 4
  (embedding spike) not triggered.
- Discard enrolment added: `DELETE /api/objects/{object_id}` (409 if the
  object has posts or is a seeded object; removes in-memory references,
  enrolled files, fingerprint rows) with a "No — discard enrolment"
  action in the captured-views preview.
- Staged object creation (later 2026-10-25, approved plan): creating a
  new object by looking is now scan → review → save. `POST
  /api/objects/enroll-live/scan` stashes a burst in a 5-min pending scan
  (no persistence), `.../scans/{id}/more` merges more angles, `POST
  /api/objects/enroll-live` now takes `{scan_id, title}` and only then
  enrols/persists, `DELETE .../scans/{id}` drops a scan. `POST
  /api/objects/{object_id}/add-views` banks another burst under an
  existing identity (thread untouched). UI: creation is available while
  a thread is open, auto-open is suppressed during scan/review, and a
  just-created object that isn't yet recognised shows an "add more
  views" hint that clears on its first high-tier sighting.
  Verification: `.venv/bin/python -m pytest` — **28 passed** (incl.
  `test_staged_scan_review_create_and_add_views`: scan persists nothing,
  create persists once and consumes the scan, add-views grows the
  reference count with the thread intact, discarded scan → 404 on
  create; disabled-camera scan → 503); `npm test` — 4 passed;
  `npm run build` — clean. Live fixture server (disposable DB): scan
  returned 1 view from 8 frames and persisted nothing until save,
  the created object was then recognised high-tier at 0.944, and
  add-views grew it to 5 reference views with its thread intact.
  Real-hardware acceptance (live-scan the black bottle, rotate 360°)
  still pending — see Next Actions.

## Verification (voice controls, 2026-10-25)

- `.venv/bin/python -m pytest` — **28 passed**, with one upstream
  Starlette/AnyIO deprecation warning.
- `npm test -- --run` — **21 passed** across geometry, target locking, and
  17 deterministic voice-routing/parser cases.
- `npm run build` — strict TypeScript and Vite production build passed.
- Disposable fixture server — `/api/health` returned 200 with camera ready and
  `/` returned 200; the server was shut down cleanly afterward.
- Browser visual interaction was attempted, but no controllable browser was
  connected to this session. Physical microphone selection, permission,
  completed live transcription, speech synthesis, and real glasses/camera
  coexistence remain manual acceptance items in `TODO.md`.

## Verification (local Faster Whisper, 2026-10-25)

- Added `faster-whisper 1.2.1`, configurable model/device/compute settings, one
  backend-owned model instance, serialized worker-thread inference, explicit
  empty/error handling, and provider/API regression coverage.
- `.venv/bin/python -m pytest` — **32 passed**, with one upstream
  Starlette/AnyIO deprecation warning.
- `npm test -- --run` — **21 passed**; `npm run build` — clean.
- Real cached-model check: `medium` + CPU `int8` loaded successfully and
  transcribed a generated 1.2-second browser-compatible WebM phrase through
  `POST /api/transcriptions` as “Open the book thread.” Response: HTTP 200,
  provider `faster-whisper`.
- Not run: physical browser microphone capture. The real-model check emitted
  non-fatal ONNX Runtime telemetry and NumPy feature-extraction warnings; the
  transcript was correct.

## Verification (markerless change, 2026-10-25)

- `.venv/bin/python -m pytest -q` — 12 passed (incl. 3 new recognition tests:
  fixture identity, swapped-position identity, unknown scene).
- `npm test` — 4 passed; `npm run build` — strict TypeScript + Vite passed.
- Live fixture server (`APP_CAMERA_SOURCE=fixture`, markerless fixture) —
  both objects recognised by appearance with real corners and resolved
  previews: `favorite-book` confidence 0.571, `concert-poster` 0.785.
- Not run: physical webcam/glasses hardware, live transcription.
