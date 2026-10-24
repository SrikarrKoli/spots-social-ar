# Feature Spec: Locus Hackathon MVP

Status: Approved for uninterrupted implementation
Last updated: 2026-10-24

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
- OpenAI completed-file transcription adapter plus explicit disabled mode.
- Idempotent seed, explicit reset, generated markers, tests, and demo docs.

### Excluded

- Authentication, follows, likes, DMs, signup, general object recognition,
  arbitrary registration, 3D mapping, native apps, or nested replies.
- Unverified Meta Muse APIs and simulated/canned transcription.
- Optional natural-language intent parsing unless all core work is complete.

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
- [x] OpenAI/disabled transcription provider adapter
- [x] Printable marker assets and real-detection fixture
- [x] Backend and frontend automated checks
- [x] Live fixture and multi-client API verification
- [x] Documentation and handoff

Interactive browser inspection was attempted but the local browser-control
surface was unavailable in this session. Physical camera, microphone permission,
and live provider credentials remain environment-dependent verification items.

## Edge Cases and Risks

- Camera unavailable must not prevent the app or typed threads from loading.
- Marker coordinates must match `object-fit: contain` letterboxing.
- Detection timestamps expire rather than leaving a ghost overlay.
- Cross-object replies and replies-to-replies must be rejected transactionally.
- Save failures retain the draft; repeated client requests are idempotent.
- Provider errors are explicit and never represented as successful transcript.

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
