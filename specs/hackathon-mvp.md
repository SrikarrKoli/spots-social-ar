# Feature Spec: Locus Hackathon MVP

Status: Approved for uninterrupted implementation
Last updated: 2026-10-24

> **Amendment (markerless):** Recognition no longer uses printed ArUco markers.
> Enrolled objects are recognised by their own appearance (instance
> recognition, not classification) via `backend/app/recognition.py`; identity
> is keyed by `identity_key`, enrolment is by photo, and ambiguous sightings
> report unknown. ArUco remains only as a legacy dev/test fixture. The pitch
> (scalable) version targets native glasses AR — see "Demo vs. the scalable
> (pitch) version" in the README. The original marker-based spec follows as
> historical context.

> **Amendment (voice controls):** Browser push-to-talk now uses the selected
> webcam/glasses audio input and the existing completed-file transcription
> endpoint. A deterministic frontend command layer supports reviewed comment
> posting, thread navigation/replies, live enrolment, provisional confirmation,
> and browser read-aloud. Speech never publishes without an explicit “post it”
> or Post-button confirmation; ambiguous object/author/recognition matches do
> nothing. Wake-word listening remains a dependency-gated stretch goal.

> **Amendment (local transcription):** `faster-whisper` is an approved
> alternative to the cloud transcription adapter. It loads one configurable
> Whisper model for the backend process, performs CPU inference away from the
> async event loop, and preserves the existing text-only transcription API.
> The demo default is the already-cached `medium` model with CPU `int8`.

## Context

Build the smallest reliable social network attached to physical objects. A
shared glasses-mounted webcam recognizes prepared ArUco markers, and a desktop
browser lets demo users read and leave persistent typed or spoken messages.

The user explicitly requested end-to-end implementation without an approval
pause after reviewing the repository README plan.

## Objectives and Success Criteria

- A real marker resolves to the seeded object and anchors a conversation card.
- Typed top-level posts and one-level replies persist in SQLite.
- A second browser sees updates through polling without reloading.
- Browser audio is recorded, transcribed by a configured backend provider,
  reviewed, and only then published.
- Object and parent targets are frozen when composition starts.
- Fixture mode exercises the actual OpenCV detection path.

## Scope

### Included

- FastAPI, OpenCV ArUco, SQLite, React, TypeScript, and Vite.
- One backend camera capture thread shared by every client.
- MJPEG video plus timestamped recognition JSON.
- Letterbox-aware overlays, smoothing, expiry, deterministic selection.
- Profiles, object threads, typed/audio composer, errors, and empty states.
- Push-to-talk voice commands, shared microphone selection, and browser TTS.
- OpenAI completed-file transcription adapter plus explicit disabled mode.
- Local Faster Whisper completed-file transcription with no API key.
- Idempotent seed, explicit reset, generated markers, tests, and demo docs.

### Excluded

- Authentication, follows, likes, DMs, signup, general object recognition,
  arbitrary registration, 3D mapping, native apps, or nested replies.
- Unverified Meta Muse APIs and simulated/canned transcription.
- Always-listening wake words and AI/free-form intent interpretation.

## Proposed Design and File Changes

- `backend/app/camera.py` — one-owner capture and marker recognition service.
- `backend/app/database.py` — schema, transactions, seed, and reset.
- `backend/app/repositories.py` — object/thread reads and validated writes.
- `backend/app/transcription.py` — disabled and OpenAI provider adapters.
- `backend/app/main.py` — lifecycle, JSON/MJPEG routes, static serving.
- `frontend/src/` — typed API, geometry, polling, recorder, and UI.
- `scripts/generate_markers.py` — labeled marker and fixture generation.
- `backend/tests/`, `frontend/src/*.test.ts` — regression coverage.
- `.env.example`, `README.md`, `HANDOFF.md` — setup and verification record.

## Implementation Checklist

- [x] Shared camera capture and real ArUco recognition
- [x] SQLite schema, seed/reset, object/thread APIs
- [x] Validated/idempotent typed posts and replies
- [x] React camera, overlays, profiles, thread, and polling
- [x] Locked-target typed/audio composer and transcript review
- [x] Deterministic voice commands, explicit voice-post confirmation, and TTS
- [x] OpenAI/disabled transcription provider adapter
- [x] Faster Whisper provider, configuration, regression tests, and docs
- [x] Printable marker assets and real-detection fixture
- [x] Backend and frontend automated checks
- [x] Live fixture and multi-client API verification
- [x] Documentation and handoff

Interactive browser inspection was attempted but the local browser-control
surface was unavailable in this session. Physical camera and microphone
permission remain environment-dependent verification items.

## Edge Cases and Risks

- Camera unavailable must not prevent the app or typed threads from loading.
- Marker coordinates must match `object-fit: contain` letterboxing.
- Detection timestamps expire rather than leaving a ghost overlay.
- Cross-object replies and replies-to-replies must be rejected transactionally.
- Save failures retain the draft; repeated client requests are idempotent.
- Provider errors are explicit and never represented as successful transcript.
- Local model load/inference failures must be explicit; empty output must never
  be treated as a successful transcript, and CPU work must not block FastAPI.

## Verification Plan

- Unit-test marker detection, geometry transforms, and target locking.
- API-test seed idempotency, persistence, reply invariants, duplicate requests,
  validation, and disabled transcription.
- Run backend pytest, frontend Vitest, TypeScript, and production build.
- Start fixture mode, inspect the UI, exercise typed posts/replies, and verify a
  second page observes polling updates.
- Report webcam, microphone, and live-provider checks separately.

## Open Questions

- Physical webcam index and glasses microphone device are environment-specific.
- Live transcription requires a valid backend `OPENAI_API_KEY`.

## Approval

- [x] User approved this scope for implementation.
- Approval date/reference: 2026-10-24, “nice, work on the rest now” following
  review of the README plan.
