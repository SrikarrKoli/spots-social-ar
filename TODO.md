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
- [ ] Create or obtain an OpenAI API key with transcription access.
- [ ] Configure these values in `.env`:

  ```dotenv
  APP_TRANSCRIPTION_PROVIDER=openai
  OPENAI_API_KEY=your_key_here
  OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe
  ```

- [ ] Restart the backend after changing `.env`.
- [ ] Record a real spoken reply, stop recording, and confirm an actual transcript
  appears in the editable review step.
- [ ] Test Retry, Cancel, transcript editing, and Post.
- [ ] Confirm no message is published before Post is pressed.
- [ ] Test the microphone-denied and provider-error states once.

If live transcription credentials are unavailable, keep
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
- [ ] Add bounded voice-command intent parsing only if the core demo is already
  reliable; this is not required for the MVP.

## Completion gate

The MVP is ready to present when one physical concert poster is recognised by
its own artwork (no marker), a real typed or transcribed reply can be reviewed
and published, the message is visible in a second browser, and the known demo
state can be restored reliably.
