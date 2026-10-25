# Session Handoff

Last updated: 2026-10-24

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
- Added disabled and OpenAI completed-file transcription adapters using
  `gpt-transcribe` by default; secrets remain backend-only.
- Built the React/TypeScript desktop UI with letterbox-aware overlays, real post
  previews, profile switching, camera-free thread browsing, polling, locked
  reply targets, microphone selection, recording, editable transcript review,
  draft retention, and explicit error states.
- Generated enrolment reference artwork (`objects/`), a markerless two-object
  fixture, and documented the demo-vs-pitch (native AR) split in the README.
- Documented setup, environment variables, reset, and the demo flow.

## Current State

- Completed: working source, fixture demo, persistence, post/reply flow,
  multi-client update path, enrolment references, automated checks, and docs.
  Markerless instance recognition implemented (pending live re-verification).
- In progress: none.
- Blocked: no implementation blockers.

## Next Actions

- [ ] On the demo laptop, set the correct `APP_CAMERA_INDEX` and confirm both
  enrolled objects are recognised by appearance under venue lighting.
- [ ] Select the glasses microphone in the UI and verify permission/recording.
- [ ] If speech is required, set `APP_TRANSCRIPTION_PROVIDER=openai` and a valid
  `OPENAI_API_KEY`, then make one live transcription before judging.
- [ ] Open two browser windows and rehearse the three-minute script.

## Unresolved Decisions or Defects

- Meta Muse transcription was intentionally not implemented because no verified
  official endpoint/authentication example was supplied.
- Browser visual inspection was unavailable in this coding session. Layout was
  type-checked and production-built, but should be visually checked on the demo
  laptop at its actual resolution.
- The physical webcam, microphone, and live OpenAI provider were not available
  here; fixture recognition and disabled-provider behavior were verified.
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

## Verification (markerless change, 2026-10-25)

- `.venv/bin/python -m pytest -q` — 12 passed (incl. 3 new recognition tests:
  fixture identity, swapped-position identity, unknown scene).
- `npm test` — 4 passed; `npm run build` — strict TypeScript + Vite passed.
- Live fixture server (`APP_CAMERA_SOURCE=fixture`, markerless fixture) —
  both objects recognised by appearance with real corners and resolved
  previews: `favorite-book` confidence 0.571, `concert-poster` 0.785.
- Not run: physical webcam/glasses hardware, live transcription.
