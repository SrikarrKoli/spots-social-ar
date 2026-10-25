# Conversational voice options for Spots

Status: optional proposal, not an adopted architecture or shipped feature

Prepared October 25, 2026. Based on main at `ce8da9db6d32607691f60d97a98f94842bdbae1c`.
This change publishes documentation only. It does not replace the current voice,
change the model, or enable a new service in the app.

## Why this exists

Spots lets someone use camera-equipped glasses to leave and discover notes on
physical objects. The intended experience stays on the glasses. The Instagram-style
phone UI is a mock used to show the experience, not a real Instagram integration.
The team reports that the spoken assistant sounds robotic. They want a more natural
voice and conversation without depending on a paid API quota or replacing working
recognition, transcription, or note-saving behavior.

A new teammate or coding assistant can use this document as a handoff. First check
the current code because main may have moved since this review. This proposal is
context for a future implementation, not evidence that its features already exist.

## What main does today

The conversation and audio are separate layers:

```text
Computer/glasses microphone
  -> browser MediaRecorder
  -> FastAPI transcription adapter (configured provider)
  -> intent/action handler OR local Ollama assistant
  -> text response
  -> browser speechSynthesis
```

| Existing code | Role and implication |
| --- | --- |
| [backend/app/assistant.py](../../backend/app/assistant.py) | Local Ollama conversation, default model selected in Settings. Requests have `stream: False`, so the complete reply arrives before speech starts. The prompt already asks for plain spoken language. |
| [backend/app/config.py](../../backend/app/config.py) | Defaults include `qwen3.5:4b`; transcription is configurable. Verify the team's actual environment rather than assuming defaults are active. |
| [backend/app/main.py](../../backend/app/main.py) | Assistant endpoint routes explicit actions separately from ordinary conversation. Preserve this separation. |
| [backend/app/memories.py](../../backend/app/memories.py), [comment_actions.py](../../backend/app/comment_actions.py), [note_actions.py](../../backend/app/note_actions.py), [note_deletion.py](../../backend/app/note_deletion.py) | Many prompts and confirmations are hard-coded here. Updating only the LLM prompt will not change their wording. |
| [frontend/src/speech.ts](../../frontend/src/speech.ts) | Shared assistant/thread speech uses the browser system voice without selecting a consistent voice. |
| [frontend/src/components/GlassesNote.tsx](../../frontend/src/components/GlassesNote.tsx) | Separate note playback chooses the first voice matching the language. It can sound different from the assistant. |
| [frontend/src/components/AssistantPanel.tsx](../../frontend/src/components/AssistantPanel.tsx) | Plays the response, keeps the mic closed during playback, then waits 650 ms before reopening in hands-free mode. Stop is available; automatic spoken interruption is not implemented. |
| [frontend/src/voiceActivity.ts](../../frontend/src/voiceActivity.ts) | Ends a spoken turn after more than 1,200 ms of silence following detected speech. This is pause detection, not semantic turn completion. |

There are three distinct problems: voice quality, wording, and turn timing. A new
TTS model addresses voice quality. It does not automatically fix the other two.

## Proposed first option: keep Ollama and add local Kokoro speech

[Kokoro](https://github.com/hexgrad/kokoro) is an open-weight text-to-speech option.
Its [model card](https://huggingface.co/hexgrad/Kokoro-82M) and
[library license](https://github.com/hexgrad/kokoro/blob/main/LICENSE) identify Apache
2.0 licensing. Local generation has no hosted character quota or per-request API
bill, but still uses the laptop's memory and CPU. Model and dependency downloads
need internet initially. Offline behavior must be tested after caching them.

This is a candidate, not a claim that its voice is better for our users. Compare it
with browser speech on the actual demo laptop. Use the official
[voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) and
[samples](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/SAMPLES.md).
`af_heart` is a starting audition voice, not a final product choice. The voice notes
flag weaknesses on very short utterances, so explicitly test short confirmations.
Do not pad confirmations with filler just to suit the model.

Kokoro and its dependencies have separate licenses. For example,
[eSpeak NG](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING) has its own
license. Preserve required notices and review the selected distribution's
obligations before packaging binaries. “Open source” does not mean no obligations.

### Why this fits the current code

The app already has reply text before playback. Keep the existing microphone,
transcription, Ollama, camera and action handlers. Substitute speech generation
and audio playback at that boundary:

```text
Existing assistant/action response text
  -> proposed FastAPI local speech endpoint
  -> Kokoro generates audio
  -> React plays that audio using the same voice for assistant and notes
```

The speech endpoint must only render text. It must not save notes, change object
identity, send messages, or turn a proposed action into a successful action.

## Implementation plan

### Stage 1: audition before integration

1. Use a separate development branch and database. Keep the existing app runnable.
2. Install Kokoro in the project environment and cache the model and chosen voice.
   Start from the official [Python usage example](https://github.com/hexgrad/kokoro#usage).
3. Compare identical text with the current system voice and at least two candidate
   Kokoro voices on the actual speakers. Include names, questions, short replies,
   a long note and an uncertain-object clarification.
4. Measure cold initialization separately from warmed generation. Repeat while
   camera recognition and transcription are running, not just in isolation.
5. Proceed only if the team prefers the sound and the real demo stays responsive.

A short local spike generated a 24 kHz WAV sample successfully on an Apple Silicon
Mac after fixing a phonemizer issue. Its first run took about 12.4 seconds,
including initialization, for one short sample. This is not a warmed-latency
benchmark, an end-to-end browser test, or proof of improved perceived quality.
No Kokoro implementation from that spike is included in this documentation change.
The spike also had an existing confirmation-text test assertion to update and a
TypeScript test typing issue; it should not be treated as merge-ready code.

macOS finding: the bundled eSpeak loader attempted to read a path from its build
machine. Installing Homebrew `espeak-ng` and selecting its actual library and data
paths through the phonemizer wrapper allowed the sample to generate. A future
implementation should make this a checked setup step with a clear error. It must
not assume a Homebrew prefix is identical on Intel and Apple Silicon machines.

### Stage 2: optional shared speech playback

Suggested new file: `backend/app/speech.py`. Keep one model instance per process,
load or warm it once, and run CPU inference off the async request loop. Bound input
length and concurrent generation; avoid an unbounded queue competing with Ollama,
Whisper and recognition. Start with one short reply at a time.

Suggested contract, not an existing main endpoint:

```http
POST /api/speech
Content-Type: application/json

{"text":"Saved your note on this poster."}
```

Return `audio/wav` with `Cache-Control: no-store`. Validate blank and oversized
input before generation. Return clear errors for unavailable speech or a busy
engine. Load-shedding must not be reported as successful playback.

Use an explicit provider setting such as `APP_SPEECH_PROVIDER=browser|kokoro` and
show which provider is active in the test settings. Keep browser speech available
as a deliberate fallback. Do not silently switch to a different voice during an
audition, because that would invalidate the comparison.

In React, route `speech.ts` and `GlassesNote.tsx` through one playback controller.
Preserve the promise contract used by `AssistantPanel`: it completes when playback
ends or is cancelled, and reports real failures. Manage audio URLs and release
them afterward. Respect browser autoplay restrictions and retain Test speakers.

Stop must abort the request where possible, stop audio, empty the playback queue
and invalidate late results. A cancelled request may not stop model inference
already executing; discard its eventual audio rather than playing it. Closing the
panel or switching targets must not allow an old reply to begin later.

Keep the microphone paused through playback initially to avoid transcribing the
assistant's own output. Retain the acoustic-tail protection until hardware testing
justifies changing it. Hands-free should resume only after playback finishes.

### Stage 3: improve wording without changing action semantics

Use everyday words and contractions. Answer the actual question directly, usually
in one or two short sentences. Ask a follow-up when it is needed to complete the
task, not as a habit. Avoid repeated greetings, canned excitement, fake laughs and
random filler. Preserve uncertainty about visual identity.

| Current style | Candidate wording |
| --- | --- |
| “Saved to [object] ... I’ll show it when I recognize this object again.” | “Saved your note on [object].” |
| “Which object? Say its saved name or point at one saved object.” | “Which one do you mean? Look at it or tell me its name.” |
| “There are no saved comments on [object].” | “No notes here yet. Want to leave one?” |

Use “poster” or another specific noun only when the app knows that target. Read
other people's note text faithfully, without having an LLM paraphrase it. Keep
confirmation and retry behavior attached to actual database results, including
existing request IDs, delete/undo state and immutable object targets. Update any
wording-sensitive tests while preserving their behavioral assertions.

### Stage 4: streaming and turn-taking only if time permits

First stabilize the voice replacement. Streaming model text into complete sentence
chunks and playing audio incrementally can reduce time to first speech, but needs
backend, transport and playback-queue changes. Generating a whole WAV before
returning it is not real-time audio streaming. Test sentence boundaries, ordering,
cancellation and partial failures. Do not send each token as an independent TTS job.

For a later pipeline redesign, [Pipecat](https://github.com/pipecat-ai/pipecat) and
[its examples](https://github.com/pipecat-ai/pipecat-examples) show interchangeable
speech/LLM services and web clients. [Smart Turn](https://github.com/pipecat-ai/smart-turn)
with [its prediction example](https://github.com/pipecat-ai/smart-turn/blob/main/predict.py)
is a reference for audio-based turn completion beyond a fixed pause timer.
These are larger follow-on changes, not prerequisites for trying Kokoro. Adding
natural interruption also requires echo handling and cancellation across all layers.

## Acceptance and rollback

Before adoption, demonstrate all of the following:

- People prefer the candidate voice in a same-text comparison; quality is a listening
  result, not an assumption from the model's marketing.
- A real mic -> transcription -> reply -> local speech turn works with camera sharing
  off, followed by a context-aware second question.
- Assistant replies and note read-aloud use the same configured voice. Note words
  and successful-action facts stay accurate.
- Stop works before generation finishes and during playback; a late result never plays.
  Closing/reopening the panel and repeated requests do not leak audio or overlap voices.
- A missing model, busy engine, denied audio permission and server failure have clear
  outcomes. Browser fallback is explicitly selected or disclosed.
- No assistant audio is recorded as a new user turn. Silence and natural mid-sentence
  pauses behave acceptably on the actual glasses microphone and laptop speakers.
- Cold/warm timing and memory use are measured under the full workload. Record results
  rather than claiming an unmeasured latency target.
- Existing note persistence, edit/delete/undo and recognition tests still pass. The
  frontend builds, and focused tests cover cancellation, validation and provider failure.

If voice quality or performance is worse, switch back to browser speech through
configuration. Do not couple rollback to reverting note or recognition changes.

## Useful primary references

- [Kokoro source and usage](https://github.com/hexgrad/kokoro)
- [Official model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [Library license](https://github.com/hexgrad/kokoro/blob/main/LICENSE)
- [Voice selection notes](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
- [eSpeak NG dependency license](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING)
- [Browser voice baseline](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance)
- [Ollama chat API and streaming](https://docs.ollama.com/api/chat)
- [Pipecat examples](https://github.com/pipecat-ai/pipecat-examples)
- [Smart Turn](https://github.com/pipecat-ai/smart-turn)

The team chose to investigate the local option to avoid reliance on a hosted free
quota. No ElevenLabs account, paid subscription, native Meta integration or new
voice architecture is required by this proposal. Recheck dependency versions and
current code before implementing it.
