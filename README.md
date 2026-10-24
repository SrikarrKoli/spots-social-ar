# Locus — AR Conversations on Physical Objects

Locus is a hackathon MVP for attaching social conversations to real-world
objects. A glasses-mounted webcam sends video to a laptop, the backend detects
printed ArUco markers, and the browser places a compact conversation preview
beside the recognized object. People can open the thread, record or type a
message, review it, and publish it for another browser session to see.

This repository is currently in the planning stage. The implementation plan
below prioritizes the complete three-minute demo over additional features.

## Demo outcome

The MVP is successful when this flow works end to end:

1. A judge looks at a prepared concert poster carrying a printed marker.
2. The laptop camera view recognizes the marker and shows the poster's thread.
3. The seeded post “Anyone want to go Friday?” is visible.
4. The judge records a spoken reply and stops the recording.
5. The transcript is shown in an editable confirmation step.
6. The judge confirms the message.
7. The reply persists in SQLite and appears in a second browser session without
   a manual refresh.

Typed messages remain fully functional when transcription credentials are not
configured. The UI must never substitute canned text for a real transcript.

## Product boundaries

### In scope

- One shared backend webcam capture with configurable camera index.
- Real ArUco marker detection and timestamped marker coordinates.
- Registered markers mapped one-to-one to seeded physical objects.
- Predictable active-marker selection with manual switching when several are
  visible.
- A floating preview positioned correctly over scaled, letterboxed video.
- A persistent side-panel thread with top-level posts and one reply level.
- Seeded demo identities plus Guest; these are simulated profiles, not auth.
- Typed posts and replies with review, validation, and failure recovery.
- Browser audio recording from a selectable microphone.
- Backend transcription through a narrow, configurable provider adapter.
- Short polling so other browser sessions receive conversation updates.
- A clearly labeled fixture mode that still runs real marker detection.
- Printable marker sheets, repeatable seeding, and an explicit demo reset.

### Deliberately out of scope

- Follows, likes, direct messages, signup, or production authentication.
- Arbitrary object registration or general visual object recognition.
- 3D mapping, spatial persistence, native mobile clients, or glasses displays.
- Real-time streaming transcription and unconstrained AI-generated messages.
- More than one reply nesting level.

## Proposed architecture

```text
glasses webcam ──> CameraService (single OpenCV capture loop)
                         │
                         ├── latest JPEG frame ──> MJPEG endpoint ──> <img>
                         └── marker snapshots ──> JSON polling ─────> overlays

browser microphone ──> MediaRecorder ──> /api/transcriptions
                                             │
                                             └── TranscriptionProvider
                                                  └── OpenAI or disabled

React client ──> FastAPI JSON API ──> service/repository layer ──> SQLite
```

The backend owns exactly one camera capture. Browser clients consume the same
MJPEG stream and poll the latest recognition snapshot, avoiding per-client
camera handles and unnecessary streaming infrastructure. Camera resources are
opened during application startup and released during shutdown.

The frontend uses the frame's intrinsic width and height together with the
rendered container dimensions to calculate `object-fit: contain` letterboxing.
Marker corner coordinates are transformed through the same scale and offset.
Detections are smoothed over a short window and expire after a small timeout.
Video is not mirrored.

When multiple registered markers are visible, the default active object is the
marker whose center is closest to the frame center. The user can choose another
visible object. Opening a thread or beginning composition captures an immutable
object ID and optional parent-post ID so later recognition changes cannot alter
the publish target.

## Repository layout

The implementation will use this structure:

```text
backend/
  app/
    api/                 # FastAPI route modules
    camera.py            # shared capture, detection, fixture mode
    config.py            # environment-backed settings
    database.py          # SQLite connection and migrations/schema setup
    main.py              # app lifecycle and static frontend serving
    models.py            # typed request/response models
    repositories.py      # database queries and integrity checks
    seed.py              # idempotent seed and explicit reset
    transcription.py     # provider protocol and implementations
  tests/
frontend/
  src/
    components/          # camera stage, overlay, thread, composer, profiles
    hooks/               # polling, recording, device enumeration
    api.ts               # typed API client
    geometry.ts          # letterbox and marker transforms
    types.ts
    App.tsx
  tests/
markers/                 # generated printable PNG/PDF marker assets
scripts/                 # marker generation and demo helpers
specs/                   # implementation spec and completion checklist
.env.example
README.md
HANDOFF.md
```

## Data model

SQLite stores three core entities:

| Entity | Fields and invariants |
| --- | --- |
| User | `id`, unique `display_name`, initials/avatar presentation |
| Object | `id`, unique `marker_id`, `title`, optional `description` |
| Post | `id`, `object_id`, `author_id`, trimmed `body`, server timestamp, nullable `parent_post_id` |

A reply must point to a top-level post belonging to the same object. This is
validated in the service transaction, not trusted from the browser. Message
bodies will have a small minimum and a reasonable maximum length. The API will
return posts in stable server order with replies grouped under their parent.

## Planned API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Service, camera, and transcription readiness |
| `GET` | `/api/profiles` | List seeded demo identities and Guest |
| `GET` | `/api/recognition` | Latest frame metadata and timestamped detections |
| `GET` | `/api/camera/stream` | Shared MJPEG camera stream |
| `GET` | `/api/objects/by-marker/{marker_id}` | Resolve a registered marker |
| `GET` | `/api/objects/{object_id}/posts` | Fetch a thread with replies and revision timestamp |
| `POST` | `/api/objects/{object_id}/posts` | Create a top-level post or validated reply |
| `POST` | `/api/transcriptions` | Transcribe a completed browser audio recording |

The frontend will poll recognition frequently enough for responsive overlays
and poll an open thread at a lower frequency for cross-session updates. Requests
will be cancelled or ignored when their owning view is replaced.

## Transcription plan

The UI and route depend on a small `TranscriptionProvider` interface. Planned
providers are:

- `disabled`: returns an explicit “transcription is not configured” error while
  typed composition continues to work.
- `openai`: sends the browser's completed WebM recording to the official audio
  transcription endpoint using a backend-only API key and configurable model.

The default proposed OpenAI model is `gpt-4o-mini-transcribe`. The current
[official OpenAI Audio API reference](https://developers.openai.com/api/reference/resources/audio)
documents WebM input, `POST /audio/transcriptions`, and a text response. Exact
SDK usage will be pinned and verified during implementation.

No Meta Muse endpoint will be implemented unless official documentation or a
provided integration example verifies its URL, authentication, and request
shape. Provider secrets remain on the backend.

## User experience and states

The desktop layout has a large camera stage and a narrower persistent thread
panel. A small profile selector sits in the top bar. The visual direction is
warm, high-contrast, and minimal: dark camera framing, light content surfaces,
one coral accent, readable type, and restrained transitions.

The UI explicitly represents:

- starting camera, ready camera, unavailable camera, and labeled fixture mode;
- no registered object recognized and one or several objects visible;
- open thread locked to a named object even after the marker leaves view;
- idle, recording, transcribing, transcript review, saving, and save failure;
- microphone permission denied or no input devices;
- retry and cancel without losing an editable draft;
- disabled submit controls while a save is pending.

React renders message bodies as plain text. No untrusted HTML is accepted.

## Seeded demo content

The idempotent seed will create:

- Concert poster: top-level post “Anyone want to go Friday?” and a sample reply.
- Book: a short recommendation and a sample response.
- Named profiles such as Maya, Theo, and Lina, plus Guest.
- A distinct marker ID for every object.

Marker generation will produce labeled, printable assets containing the object
title and numeric marker ID. `reset-demo` will recreate the known seed state;
normal application startup will never delete user-created posts.

## Implementation sequence

### Phase 0 — project foundation

- Record the feature spec and verification checklist.
- Scaffold FastAPI, React, TypeScript, Vite, SQLite, and test tooling.
- Pin compatible versions, add `.env.example`, and expose one development start
  command per process.

### Phase 1 — camera and recognition

- Implement the one-owner capture loop and clean lifecycle shutdown.
- Detect ArUco markers with OpenCV and publish timestamped frame metadata.
- Add MJPEG transport and fixture input using the same detection path.
- Generate labeled printable markers.
- Verify real detections against generated fixture imagery.

### Phase 2 — persistence and conversations

- Create the schema, seed/reset commands, repositories, and API models.
- Resolve markers to objects and show the seeded conversation.
- Implement typed top-level posts and replies.
- Enforce object/parent consistency, message limits, and server timestamps.
- Verify persistence across restart and polling across two clients.

### Phase 3 — recording and transcription

- Enumerate microphone inputs and record click-to-start/click-to-stop audio.
- Capture the object and reply target when composition starts.
- Send completed audio to the provider adapter.
- Add editable transcript review with Post, Retry, and Cancel.
- Keep typed composition available in disabled-provider mode.

### Phase 4 — overlay correctness and polish

- Implement letterbox-aware coordinate transforms and jitter smoothing.
- Expire stale previews, support multiple visible objects, and retain open
  threads when recognition disappears.
- Add all loading/error/empty states and responsive desktop styling.
- Inspect the complete flow in a browser and correct accessibility issues.

### Phase 5 — verification and handoff

- Run backend tests, frontend tests/type checks, and a production build.
- Exercise the API with a temporary database.
- Test two browser sessions and the full typed flow.
- Test browser recording and the disabled-provider experience.
- Record which camera, microphone, and provider checks were run on hardware.
- Update `HANDOFF.md` and add the final three-minute demo script below.

## Verification matrix

| Area | Required evidence |
| --- | --- |
| Recognition | Generated markers are detected with IDs/corners and stale results expire |
| Camera ownership | Multiple stream clients do not create multiple capture handles |
| Overlay | Known frame points map correctly under wide and tall letterboxing |
| Persistence | A created post survives application restart |
| Reply integrity | Cross-object and reply-to-reply attempts are rejected |
| Target lock | Marker changes during recording cannot change object or parent IDs |
| Multi-client | A second client receives a new message through polling |
| Audio | Real browser audio reaches the backend as a supported file type |
| Transcription | Configured provider returns actual text; disabled mode is explicit |
| Resilience | Failed saves retain the draft and duplicate submits are prevented |
| Build quality | Backend tests, frontend tests, type checking, and production build pass |

Hardware-dependent results will be reported separately from fixture and
automated checks.

## Planned local commands

The precise commands will be finalized after scaffolding and dependency
installation. The intended interface is:

```bash
# Backend setup and development server
uv sync
uv run python -m backend.app.seed
uv run uvicorn backend.app.main:app --reload

# Frontend development server
cd frontend
npm install
npm run dev

# Verification
uv run pytest
cd frontend && npm test && npm run build

# Restore the known hackathon demo state (explicit and destructive)
uv run python -m backend.app.seed --reset
```

The production-shaped development path will build the frontend and let FastAPI
serve the static assets from the same origin.

## Planned environment variables

```dotenv
# Core
APP_DATABASE_PATH=./data/locus.db
APP_CAMERA_INDEX=0
APP_CAMERA_SOURCE=camera
APP_CAMERA_FIXTURE=
APP_MARKER_DICTIONARY=DICT_4X4_50
APP_DETECTION_TTL_MS=750

# Transcription
APP_TRANSCRIPTION_PROVIDER=disabled
OPENAI_API_KEY=
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

`APP_CAMERA_SOURCE=fixture` will require `APP_CAMERA_FIXTURE` to point to an
image or video containing a real generated marker. It will be visibly labeled
in the UI and will not fabricate recognition results.

## Risks and mitigations

- **Camera backend differences:** isolate OpenCV capture setup, expose camera
  readiness, and retain fixture mode for development.
- **ArUco availability:** use the OpenCV contrib build and test the exact marker
  APIs after pinning the package.
- **Browser recording formats:** accept the browser-provided MIME type and use
  a documented transcription-supported container such as WebM.
- **Head movement changes targets:** freeze object and parent IDs at composer
  creation and display the locked object throughout review.
- **Recognition jitter:** smooth marker centers/corners briefly and expire by
  server timestamp instead of keeping a ghost overlay.
- **Provider credentials unavailable:** make typed posting demo-complete and
  label transcription as unconfigured rather than simulating it.
- **Concurrent demo writes:** keep each post creation in one SQLite transaction,
  enable foreign keys, and use a short busy timeout/WAL where appropriate.

## Three-minute demo script (target)

1. Open Locus in two browser windows and select different demo profiles.
2. Put on the camera glasses and face the concert poster.
3. Point out the anchored preview and open the “Concert poster” thread.
4. Show Maya's “Anyone want to go Friday?” post and choose Reply.
5. Record “I’m in — doors open at seven,” then stop.
6. Edit or approve the real transcript and press Post.
7. Show the reply appear in the first window and then in the second window via
   polling, demonstrating that the conversation is attached to the physical
   marker and persisted for another person.

## Current status

- [x] Product brief translated into an implementation plan.
- [ ] Project scaffolded.
- [ ] Camera and real marker recognition implemented.
- [ ] Seeded conversations and typed posting implemented.
- [ ] Multi-client updates verified.
- [ ] Recording, transcription review, and publishing implemented.
- [ ] Browser and hardware verification completed.

