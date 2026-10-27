# Spots: Social AR for Meta Ray-Ban Display

Spots lets people leave notes on physical objects and discover what someone else
had to say about them. A concert poster could hold “Anyone going Friday?”; someone
who sees it later can reply and start a conversation.

This HackTX prototype uses a camera, a laptop and a browser to demonstrate the
experience we want to bring to **Meta Ray-Ban Display**. The browser has Phone and
Glasses views. The Instagram-style Phone interface is a demo mock, not a real
Instagram integration. Labels such as “Ask Meta AI” are part of that interface;
the conversational model actually runs locally through Ollama.

## Latest voice integration

The team has added **local Kokoro speech with the Heart voice** on
[`seamless-voice-notes`](https://github.com/arnavvalvekar/meta-glasses-notes/tree/seamless-voice-notes).
That integration is awaiting a merge into main. The setup below first describes
main, followed by the exact Kokoro branch setup. This README update does not
merge application code.

## Presentation and plans

- [Latest HackTX presentation](https://utexas-my.sharepoint.com/:p:/r/personal/sk62334_eid_utexas_edu/Documents/Spots-HackTX-2026.pptx?d=w6ec8edb0e7fe484fa7e131866ae70859&csf=1&web=1&e=TzDPEg)
- [Object identity and background-leakage findings](docs/architecture/object-identity.md)
- [Conversational voice design and evaluation plan](docs/plans/conversational-voice-options.md)
- [Performance design and tooling](specs/performance-optimization.md)
- [Earlier implementation handoff](HANDOFF.md) and [MVP specification](specs/hackathon-mvp.md)

The voice plan records the rationale and testing approach that preceded the
Kokoro branch. Its proposed status is historical context; use the branch code
and the Kokoro section below for the implemented speech path. SAM 2 and DINOv2
remain proposed recognition work. Main still uses browser speech until the
voice branch is merged.

## What works in the prototype

- Markerless matching against enrolled reference images using SIFT/ORB and homography.
- Short-lived optical-flow tracking to keep overlays aligned between identity checks.
- Persistent object notes and replies, typed or transcribed from recorded audio.
- Local camera-aware conversation using Qwen through Ollama.
- Local Kokoro Heart speech for assistant replies and note read-aloud on the voice branch, with browser speech available as a fallback.
- Spoken requests to create, read, rename, edit, delete and undo supported note actions.
- Live-camera enrollment and a staged scan/review API for adding object views.
- SQLite persistence and polling so separate browser clients can retrieve saved notes.
- Seeded profiles and restaurant examples for demonstrating the social interface.

Recognition is still being improved. References can include background features,
so a match is **not proof of reliable object-only identity**. See the
[reproduced background-leakage issue](docs/architecture/object-identity.md) before
relying on moved-object or different-background behavior. Low texture, occlusion,
large viewpoint changes and visually identical copies remain difficult cases.
The system has confidence tiers and unknown states, but false matches are possible.

## Quick start

### Requirements

- Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/).
- Node.js 24+ and npm, as required by the frontend package.
- A webcam for the live Glasses experience; set the correct camera index below.
- A browser with microphone recording and speech-synthesis support. Chrome is a
  practical demo choice; allow microphone access and check the computer's sound output.
- For AI conversation: [Ollama](https://ollama.com/download) and the configured
  vision-capable model. For spoken input: a configured transcription provider.

### 1. Configure the app

From the repository root, copy `.env.example` to `.env` **if you do not already
have a local `.env`**. Keep existing credentials and demo data.

```sh
cp -n .env.example .env
```

For the local voice demo, edit these values in `.env`:

```dotenv
APP_CAMERA_SOURCE=camera
APP_CAMERA_INDEX=0
APP_RECOGNIZER=instance
APP_TRANSCRIPTION_PROVIDER=faster-whisper
APP_WHISPER_MODEL=small.en
APP_WHISPER_DEVICE=cpu
APP_WHISPER_COMPUTE_TYPE=int8
APP_ASSISTANT_MODEL=qwen3.5:4b
APP_OLLAMA_URL=http://127.0.0.1:11434
APP_LLM_PARSER_ENABLED=true
```

`small.en` is an English-only option for quicker CPU turns. The code's local
Whisper default is `medium`. The checked-in `.env.example` defaults transcription
to `disabled`, so copying it alone does not enable voice input. Use a multilingual
Whisper model when needed. Camera index `0` is only a starting point; a connected
Brio or other external camera may use another index.

### 2. Start Ollama

If its app/service is not already running, start it in a separate terminal:

```sh
ollama serve
```

Download the configured model once:

```sh
ollama pull qwen3.5:4b
ollama list
```

Keep Ollama running while using conversation and the default LLM action parser.
A custom model must report vision support for the current readiness check, even
if a particular request does not attach a camera image.

### 3. Start Spots

```sh
./scripts/start_local.sh
```

The launcher installs project dependencies, builds the frontend and starts one
FastAPI process on `http://127.0.0.1:8000`. It creates `.env` only if missing.
Startup seeds demo records without resetting existing posts. The first local
Whisper run may download its model and delay server startup.

Open [Spots](http://127.0.0.1:8000). It starts in **Phone** view. Choose **Glasses**,
or open [Glasses view](http://127.0.0.1:8000/#glasses), for the camera and assistant.

For manual setup instead of the launcher:

```sh
uv sync --locked
npm --prefix frontend ci --include=dev
npm --prefix frontend run build
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

The reference artwork and fixture images are already checked in. Regenerate them
with `uv run python scripts/generate_references.py` only when you intend to update
those generated assets. A manual seed is optional because startup seeds the app.

## Phone, Glasses and voice interaction

**Phone** shows an Instagram-style inbox, object-note conversations and sample
social activity. Object posts and comments use the backend; illustrative friend
and group chats are frontend/session fixtures. There are no real Instagram
accounts, DMs, contact imports or autonomous group invitations.

**Glasses** displays the backend camera stream and recognized-object notes. The
current app mounts this view in live mode; it does not automatically substitute
the static restaurant image when a camera disconnects. The backend supports a
fixture source for testing, but fixture output is not a live-camera demonstration.

The bottom **Ask Meta AI** control opens the local assistant overlay and starts
hands-free capture when the services are ready. Allow the microphone, speak, and
pause to end a turn. Whisper transcribes the completed recording; the app routes
an action or asks Qwen for a response; the selected speech provider reads the answer aloud (browser on main; Kokoro Heart when ready on the voice branch).
Close or Stop ends capture/playback. “Stop listening” works during a listening
turn. Automatic spoken interruption while the assistant is speaking is not built.

The microphone is closed during playback, then waits 650 ms before reopening.
The current voice detector ends a turn after about 1.2 seconds of silence, pauses
hands-free after ten seconds with no detected speech, and caps a turn at 25 seconds.
Transcripts and responses arrive by turn, not word-by-word streaming.

Examples to rehearse against the current build:

| Request | Intended behavior |
| --- | --- |
| “Take a note” | Ask which object/content is needed before saving. |
| “Call it blue water bottle and add a note saying I bought it yesterday” | Resolve or enroll the target and save the dictated comment through the action handler. |
| “What other notes were left on this object?” | Retrieve stored notes and replies. |
| “Read past comments aloud” | Read stored comments, rather than inventing a summary of nonexistent notes. |
| “Change my last comment to say …” | Edit the current profile's matching comment; clarify when ambiguous. |
| “Delete that note” / “Undo” | Delete a resolved note or restore the tracked deletion. |
| “Rename this to Dinnie poster” | Rename the visible saved object after identity checks. |

A bare comment request gets an explicit prompt. A steady view can provide a
tentative object name, which the app asks the user to confirm. Naming, dictation
and ordinary questions are separate states. Pending content can be held while
the app asks for a name or selection. The parser checks action arguments against
speech or an existing draft before executing supported actions.

The two publishing paths differ: typed/recorded composer flows offer transcript
review and an explicit Post action; an explicit assistant command containing the
note content can save directly after its validation succeeds. Do not claim every
voice save requires a second “post it” command. Confirmations reflect actual
application/database results, not a free-form model claim.

Profiles are demo identities, not secure accounts. Author checks operate on the
selected local profile and are not production authentication or authorization.

## How the pieces fit together

```text
Camera -> OpenCV capture -> SIFT/ORB identity matching -> temporary motion tracking
                             |                                  |
                             +-> recognition JSON -> React overlays
Camera -> latest JPEG -> MJPEG stream -> Glasses view

Browser microphone -> MediaRecorder -> /api/transcriptions
                                       -> Faster Whisper / OpenAI / disabled
Transcript -> structured local intent parser -> validated application action
           -> local Qwen conversation with optional camera snapshot and thread
Response text -> speech playback -> computer sound output
                 main: browser voice
                 voice branch: local Kokoro Heart WAV when ready, browser otherwise

React <-> FastAPI <-> repositories/transactions <-> SQLite notes and object IDs
```

The backend owns one camera capture. Run one backend worker for the demo. Qwen
receives a fresh snapshot for a camera-enabled conversational turn, not continuous
video. The intent parser sees transcript/history/pending state and saved object
names, not the camera image. spaCy helps extract noun phrases for object names.
SIFT/ORB determines enrolled identity; a model's visual description is not itself
a trusted saved-object ID.

The matcher uses reference views, confidence thresholds and runner-up margins.
High-confidence detections can drive live overlays; the main live UI filters out
non-high detections. Lower-confidence confirmation is supported by the API and
older thread controls, not a promise that every confirmation control is exposed
in the current Glasses screen.

Optical flow can bridge a brief missed identity check after two high-confidence
sightings. Bridges expire after 0.7 seconds without verification. Flow positions
an overlay; it is not persistent 3D mapping or independent object re-identification.
Automatic reference banking is bounded but can reinforce a bad initial match.

SQLite stores profiles, objects, reference fingerprints, posts/replies, edit history
and deletion/undo records. Posts are 1–500 characters. Replies must belong to the
same object as their top-level parent. Request IDs protect supported retries from
duplicate writes. References and notes must both be retained for later recognition;
losing a live detection does not delete the stored conversation.

## Kokoro Heart: implemented on the voice branch

Kokoro turns the assistant's response text into speech locally. It does not replace
Qwen, Whisper, object matching or note actions. Assistant replies and saved-note
read-aloud share the selected voice. The backend loads and warms one model in a
background thread, then renders 24 kHz WAV audio. The frontend splits long text into
chunks of at most 600 characters and plays them sequentially; this is chunked
playback, not streaming LLM tokens or continuous speech-to-speech.

Implementation:
[backend speech provider](https://github.com/arnavvalvekar/meta-glasses-notes/blob/seamless-voice-notes/backend/app/speech.py),
[shared playback](https://github.com/arnavvalvekar/meta-glasses-notes/blob/seamless-voice-notes/frontend/src/speech.ts),
[optional dependencies](https://github.com/arnavvalvekar/meta-glasses-notes/blob/seamless-voice-notes/pyproject.toml).

To try it in a separate checkout before the merge:

```sh
git clone --branch seamless-voice-notes --single-branch https://github.com/arnavvalvekar/meta-glasses-notes.git spots-voice
cd spots-voice
cp -n .env.example .env
```

Configure the local transcription and Ollama values from Quick start, plus:

```dotenv
APP_SPEECH_PROVIDER=kokoro
APP_SPEECH_VOICE=af_heart
```

On macOS, install the phonemizer dependency and voice extra:

```sh
brew install espeak-ng
uv sync --locked --extra voice
```

Then use that branch's `./scripts/start_local.sh`. Its launcher installs the voice
extra and starts the app with it enabled. A manual server command must also retain
that extra:

```sh
npm --prefix frontend ci --include=dev
npm --prefix frontend run build
uv run --extra voice uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

The branch also adds `APP_CAMERA_NAME=Brio 100` for macOS camera selection. Set it
to the camera you actually have; it is not a main setting yet. The implementation
does not fall back to the built-in camera when the named external camera is missing.

`GET /api/health` adds `speech_provider`, `speech_status`, `speech_voice` and
`speech_message`. The UI uses Kokoro once the provider reports `ready`; during
loading/unavailability it can use browser speech. A request failure after server
speech was selected is reported as an error. Choose `APP_SPEECH_PROVIDER=browser`
and restart to deliberately use the system voice.

`POST /api/speech` accepts `{"text":"Hello"}` and returns `audio/wav` with
`Cache-Control: no-store`. Empty/oversized input is rejected; the server limit is
600 characters per request. It renders text only and does not perform actions.
Stop cancels browser playback and pending fetches and invalidates late results;
it does not guarantee cancellation of CPU inference already in progress.

The branch searches `/opt/homebrew/opt/espeak-ng` and `/usr/local/opt/espeak-ng`.
For a different installation, configure both `APP_ESPEAK_LIBRARY` and
`APP_ESPEAK_DATA` using the actual library and `espeak-ng-data` paths. The current
helper targets those macOS/Homebrew locations; don't assume Linux/Windows setup
is already handled. Download/cache the model and voice before offline use and
rehearse with recognition, Whisper and Ollama running together.

Kokoro source and weights are described in the official
[source repository](https://github.com/hexgrad/kokoro) and
[model card](https://huggingface.co/hexgrad/Kokoro-82M). Keep model/dependency license
notices when redistributing. Local generation avoids a hosted speech API quota;
it still consumes the demo computer's resources.

## Configuration and camera-free testing

[.env.example](.env.example) lists all environment variables;
[config.py](backend/app/config.py) defines runtime defaults. Relative data paths
are resolved from the repository root. Some package names, IDs and the default
`data/locus.db` filename retain the earlier Locus name for compatibility.

| Setting | Default | Notes |
| --- | --- | --- |
| `APP_DATABASE_PATH` | `./data/locus.db` | Keep this file for persistent notes. |
| `APP_ENROLLED_DIR` | `./data/enrolled` | Keep saved reference images too. |
| `APP_CAMERA_SOURCE` | `camera` | `camera`, `fixture` or `disabled`. |
| `APP_CAMERA_INDEX` | `0` | Check after connecting/changing cameras. |
| `APP_CAMERA_FIXTURE` | `./markers/markerless-fixture.png` | Backend test input containing enrolled references. |
| `APP_RECOGNIZER` | `instance` | `aruco` remains a legacy test path. |
| `APP_TRANSCRIPTION_PROVIDER` | `disabled` | `faster-whisper`, `openai` or `disabled`. |
| `APP_WHISPER_MODEL` | `medium` | CPU/int8 defaults; `small.en` is a local English alternative. |
| `APP_ASSISTANT_MODEL` | `qwen3.5:4b` | Must be installed in Ollama. |
| `APP_OLLAMA_URL` | `http://127.0.0.1:11434` | Trusted backend setting; loopback keeps requests local. |
| `APP_LLM_PARSER_ENABLED` | `true` | Structured action parsing; `false` selects the older rule-based path. |
| `APP_RESTAURANT_DEMO` | `true` | Seeds separate `demo-menu-*` objects; disabling it does not remove existing data. |

The optional `openai` transcription adapter uses backend-only `OPENAI_API_KEY`,
`OPENAI_TRANSCRIPTION_MODEL` (currently configured as `gpt-transcribe`) and
`OPENAI_TRANSCRIPTION_PROMPT`. Check provider/model availability for your account;
no cloud call is needed for the local Whisper/Ollama path.

Recognition/performance defaults are 1280×720 camera capture, analysis width 960,
8 recognition FPS, 15 stream FPS, JPEG quality 75 and three OpenCV threads. These
are configured targets, not guaranteed hardware throughput. Active references
are bounded by `APP_MAX_REFERENCE_FILES_PER_IDENTITY=4` and automatic views by
`APP_MAX_AUTO_BANKED_FILES_PER_IDENTITY=2`.

Without a camera, use `APP_CAMERA_SOURCE=fixture` for recognition/API tests, or
`disabled` for non-camera work. Check `/api/health` for the source; do not present
fixture output as live footage. A camera-free assistant request must explicitly
use `include_camera: false`:

```sh
curl http://127.0.0.1:8000/api/assistant \
  -H 'Content-Type: application/json' \
  --data '{"message":"Can we chat without a camera?","include_camera":false,"history":[]}'
```

The current main UI opens the compact glasses overlay with camera sharing enabled;
a dedicated camera-free preview page is a separate local experiment, not a main
feature. Switching off the backend camera alone does not turn that UI into a
camera-free conversational client. Backend-only text chat still requires Ollama;
voice also needs transcription and browser playback.

## Development and verification

For frontend hot reload, run FastAPI on port 8000 and Vite separately:

```sh
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

In another terminal:

```sh
npm --prefix frontend run dev
```

Vite serves on port 5173 and proxies `/api` to FastAPI. For a single-origin demo,
use the production build and launcher instead.

```sh
# Automated checks; no real camera or paid transcription account required
uv run pytest -m 'not performance'
npm --prefix frontend test
npm --prefix frontend run build

# Optional machine-dependent fixture benchmark
uv run pytest -m performance

# Optional real-model parsing checks (Ollama/model required)
uv run python -m scripts.evaluate_intent_parser --model qwen3.5:4b
```

The suites cover recognition fixtures, enrollment, optical flow, persistence,
action parsing, editing/deletion, microphone state and frontend integration.
Automated tests do not prove physical-camera accuracy, microphone quality or
successful native Meta hardware integration. Rehearse those separately.

For background leakage, follow the reproduction command in the
[object identity document](docs/architecture/object-identity.md). The
[performance scripts](scripts/benchmark_performance.py) measure local behavior;
reference pruning defaults to a report and only mutates data with `--apply`.

Startup preserves saved posts. This command deletes current posts, objects, profiles
and recognition records before reseeding the demo; back up your database and
reference images before using it:

```sh
uv run python -m backend.app.seed --reset
```

CLI helpers read their process environment; they do not automatically load `.env`
the way the server's `--env-file` does. Supply any custom `APP_DATABASE_PATH` or
other overrides to the command so it targets the intended database.

## API reference

The running server exposes schemas and request details at
[Swagger UI](http://127.0.0.1:8000/docs). Key endpoints:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Camera, transcription, assistant readiness and parser mode. |
| POST | `/api/assistant` | Conversation or supported note action with bounded history/pending state. |
| GET | `/api/profiles` | Seeded local demo identities. |
| GET | `/api/objects` | Saved objects, including enabled restaurant examples. |
| GET | `/api/objects/by-identity/{identity_key}` | Resolve an enrolled identity. |
| GET | `/api/objects/{object_id}/posts` | Read a thread and its replies. |
| POST | `/api/objects/{object_id}/posts` | Create a validated post/reply with a client request ID. |
| POST | `/api/transcriptions` | Transcribe a completed recording. |
| GET | `/api/recognition` | Current detection metadata and camera provenance. |
| GET | `/api/camera/stream` | Shared MJPEG stream. |
| GET | `/api/objects/{object_id}/reference` | Serve an allowed saved reference image. |
| POST | `/api/objects/enroll` | Photo-upload enrollment for development/testing. |
| POST | `/api/objects/enroll-live/scan` | Stage a live scan without creating an object. |
| POST | `/api/objects/enroll-live/scans/{scan_id}/more` | Capture another angle for a pending scan. |
| DELETE | `/api/objects/enroll-live/scans/{scan_id}` | Discard a pending scan. |
| POST | `/api/objects/enroll-live` | Create an object from a reviewed scan. |
| POST | `/api/objects/{object_id}/add-views` | Add live reference views to an existing identity. |
| POST | `/api/recognition/confirm` | Confirm a provisional sighting. |
| DELETE | `/api/objects/{object_id}` | Discard an eligible enrollment, not a posted/seeded object. |
| GET | `/api/diagnostics/performance` | Runtime performance diagnostics. |

The Kokoro voice branch additionally exposes `POST /api/speech`; it is not an
endpoint on main before the merge.

Direct post bodies require `author_id`, `body` and a unique `client_request_id`;
replies also supply `parent_post_id`. Follow the schema for assistant action state
rather than constructing a new pending-state protocol.

## Three-minute demo checklist

1. Start Ollama and the backend, allow camera/microphone access, verify health and
   sound, and rehearse against the actual reference object.
2. Open two browser sessions using the same backend and different demo profiles.
3. Explain that Phone is a mock display and Glasses uses the actual camera feed.
4. Find a saved invitation or note, then have someone create a real spoken reply
   using the implemented controls. Check the target and the actual saved text.
5. Show the second person retrieving that saved note. Keep the same database and
   reference files between panels; do not reset the demo to prove rediscovery.
6. If recognition or transcription fails, say what failed and use the supported
   typed path in Phone or a prepared recording of an earlier run labeled as such.
   Do not substitute sample notes for a claimed live save.

Before judging, also test moving/removing the target while leaving its background,
looking away during dictation, cancelling, retrying, and restarting with the same
saved conversation. Reliable object-only recognition is still a work item.

## What we want to build next

First, bring the experience onto **Meta Ray-Ban Display** so discovery and replies
can happen through the glasses without reaching for a phone. Native hardware
integration is not implemented by this browser prototype.

Then test with people in shared places, improve recognition across backgrounds
and viewpoints, and see whether notes lead to conversations or plans. Future
opt-in recommendations could use shared interests and places people choose to
share. App integrations, including an example such as Beli restaurant
recommendations, are ideas to investigate, not existing partnerships or APIs in use.

Real Instagram integration, a live social recommender, shared 3D anchors and
native in-lens rendering are not on main. The Kokoro integration already exists
on the voice branch and is awaiting its merge; see that section for setup rather
than treating it as future research.

## Code map

- `backend/app/camera.py`, `recognition.py`, `object_tracking.py`: capture, matching and tracking.
- `backend/app/assistant.py`, `intent_parser.py`, `intent_dispatch.py`: conversation and action interpretation.
- `backend/app/memories.py`, `note_actions.py`, `comment_actions.py`, `note_deletion.py`: note actions and pending states.
- `backend/app/database.py`, `repositories.py`: persistence, history and seed behavior.
- `backend/app/transcription.py`, `noun_phrases.py`: transcription and object naming.
- `frontend/src/App.tsx`, `components/MessagesView.tsx`: Phone/Glasses navigation and mock social interface.
- `frontend/src/components/CameraStage.tsx`, `GlassesNote.tsx`: camera overlays and note interaction.
- `frontend/src/components/AssistantPanel.tsx`, `speech.ts`, `hooks/useVoiceRecorder.ts`: assistant turns, system speech and microphone lifecycle.
- `backend/tests/`, `frontend/src/**/*.test.*`: automated checks.

This is a local hackathon prototype with simulated identities, not a deployed
multi-user service. Keep private recordings, credentials and local databases out
of commits.
