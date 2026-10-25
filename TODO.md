# Latest local-demo status

The Brio 100 / MacBook demo is running with local transcription, local visual
AI conversation, spoken answers, hands-free turn-taking, direct voice note
saving, object renaming, persistent memory recall and optional reviewed drafts. The user confirmed speech capture and MacBook speaker audio. See the
latest HANDOFF.md entry and README's Brio setup section for verified behavior.

Remaining acceptance: rehearse actual enrolled objects at venue distance and
lighting; check a saved social reply in a second browser; test reconnecting the
Brio if its device index changes. Native glasses display, 3D anchors and social
recommendations remain future work. The older checklist below is historical
and does not supersede the verified latest status.

# MVP Remaining Work

The software MVP is implemented and automated checks pass. The remaining work
is primarily hardware validation, live-service configuration, and demo
rehearsal.

## Required before the demo

- [ ] Run `.venv/bin/python scripts/generate_references.py` to (re)generate the
  enrolment artwork in `objects/` and `markers/markerless-fixture.png`.
- [ ] Use the concert-poster artwork itself as the poster (printed or on screen)
  — **no marker is attached to anything**.
- [ ] Use the book-cover artwork in `objects/favorite-book.png` as the book cover.
- [ ] Confirm the glasses webcam appears on the laptop and determine its OpenCV
  index (`0`, `1`, and so on).
- [ ] Set `APP_CAMERA_INDEX` in `.env` to the glasses webcam index.
- [ ] Grant camera access to the terminal application used to run Locus.
- [ ] Start Locus in camera mode and verify both physical objects are recognised
  by appearance at the intended demo distance and lighting.
- [ ] Confirm the overlay remains positioned beside the object while moving the
  camera naturally.
- [ ] Confirm the preview disappears shortly after an object leaves the frame.
- [ ] Confirm the correct object is selected when both objects are visible.
- [ ] Swap the poster/book positions and confirm each thread follows its object.
- [ ] Hold up an unenrolled lookalike and confirm Locus reports unknown rather
  than attaching the wrong thread.
- [ ] (Stretch) Enrol two visually distinct mugs from photos and show they keep
  separate threads.

## Microphone and transcription

- [ ] Connect the glasses microphone or confirm the laptop microphone fallback.
- [ ] Grant microphone permission to the demo browser.
- [ ] Confirm the desired microphone appears in the in-app microphone selector.
- [ ] Configure local transcription in `.env` (no API key required):

  ```dotenv
  APP_TRANSCRIPTION_PROVIDER=faster-whisper
  APP_WHISPER_MODEL=medium
  APP_WHISPER_DEVICE=cpu
  APP_WHISPER_COMPUTE_TYPE=int8
  ```

- [ ] (Optional cloud alternative) Set `APP_TRANSCRIPTION_PROVIDER=openai`,
  `OPENAI_API_KEY`, and `OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe`.

- [ ] Restart the backend after changing `.env`.
- [ ] Record a real spoken reply, stop recording, and confirm an actual transcript
  appears in the editable review step.
- [ ] Select the **webcam/glasses microphone** in the 🎙 mic picker (the choice
  persists) and confirm the backend camera keeps streaming at the same time —
  the browser captures only the webcam's audio, never its video.
- [ ] Voice flow: push-to-talk to dictate in an open thread, review, then
  push-to-talk and say “post it”; confirm nothing publishes on transcription
  alone. Test voice Retry/Cancel, transcript editing, and the Post button.
- [ ] Voice commands: “open the book”, “reply to Maya”, “enrol this as …”
  (scan → review crops → Save), “yes that's it” on a possible match, and
  “read the thread” / “stop reading”. Say an unknown object name and confirm
  Locus does nothing rather than guessing.
- [ ] Test Retry, Cancel, transcript editing, and Post.
- [ ] Confirm no message is published before the Post button or an explicit
  voice “post it” confirmation.
- [ ] Test the microphone-denied and provider-error states once.

If neither local nor cloud transcription can be used, keep
`APP_TRANSCRIPTION_PROVIDER=disabled`. Typed posting remains demo-ready, but
speech-to-text should be described as unconfigured rather than demonstrated.

## Browser flow validation

- [ ] Open two browser windows at `http://127.0.0.1:8000`.
- [ ] Choose a different demo profile in each window.
- [ ] In the first window, recognise the concert poster and open the concert thread.
- [ ] Reply to “Anyone want to go Friday?” using the final input method.
- [ ] Turn the camera away while composing and confirm the composer remains
  locked to the concert poster and the intended parent post.
- [ ] Publish the reply and confirm it appears in the second window within the
  polling interval without refreshing.
- [ ] Restart the backend and confirm the new reply still exists.
- [ ] Verify a camera-free second window can browse a demo thread directly.
- [ ] Check the layout at the laptop resolution used during judging.
- [ ] Confirm message text wraps cleanly and every button remains visible.

## Demo preparation

- [ ] Run the explicit reset immediately before the presentation:

  ```bash
  uv run python -m backend.app.seed --reset
  ```

- [ ] Start the production build and confirm `/api/health` reports the expected
  camera and transcription states.
- [ ] Disable screen sleep and automatic system updates for the demo window.
- [ ] Close applications that may claim the webcam or microphone.
- [ ] Arrange the poster, book, camera cable, and laptop to avoid glare and cable
  strain.
- [ ] Rehearse the three-minute script in [README.md](README.md#three-minute-demo-script-target).
- [ ] Prepare fixture mode as the fallback by knowing how to set:

  ```dotenv
  APP_CAMERA_SOURCE=fixture
  ```

- [ ] Keep typed posting as the fallback if live transcription fails.
- [ ] Perform one complete rehearsal after resetting the database.

## Nice to have only after the required checklist

- [ ] Add a short first-run hint explaining how to enrol/position an object.
- [ ] Add an unobtrusive recording timer.
- [ ] Capture a backup screen recording of the successful demo flow.
- [x] Add bounded, deterministic voice-command parsing with no guessed actions.

## Completion gate

The MVP is ready to present when one physical concert poster is recognised by
its own artwork (no marker), a real typed or transcribed reply can be reviewed
and published, the message is visible in a second browser, and the known demo
state can be restored reliably.
