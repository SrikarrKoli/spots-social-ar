import { useEffect, useState } from "react";
import { api } from "../api";
import { microphoneErrorMessage, useVoiceRecorder } from "../hooks/useVoiceRecorder";
import { speakThread, speechSupported, stopSpeaking } from "../speech";
import type { ObjectSummary, Post } from "../types";
import {
  parseVoiceInput,
  VOICE_COMMAND_EXAMPLES,
  type VoiceContext,
  type VoiceIntent,
  type VoiceMode,
} from "../voiceCommands";

interface Props {
  transcriptionConfigured: boolean;
  mode: VoiceMode;
  context: VoiceContext;
  threadObject: ObjectSummary | null;
  threadPosts: Post[];
  onDictationStart: () => void;
  onDictation: (text: string) => string;
  onIntent: (intent: VoiceIntent) => string;
}

// Global push-to-talk. This `activate` toggle is the single entry point a
// future wake-word trigger would call — v1 ships the button only, so the
// microphone is never hot unattended.
export function VoiceControl({
  transcriptionConfigured,
  mode,
  context,
  threadObject,
  threadPosts,
  onDictationStart,
  onDictation,
  onIntent,
}: Props) {
  const recorder = useVoiceRecorder();
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  // Changing threads (or unmounting) always silences read-aloud.
  useEffect(() => {
    stopSpeaking();
    setSpeaking(false);
  }, [threadObject?.id]);
  useEffect(() => () => stopSpeaking(), []);

  const handleIntent = (intent: VoiceIntent) => {
    if (intent.type === "read_thread") {
      if (!threadObject) {
        setStatus("Open a thread first, then say “read the thread”.");
        return;
      }
      const started = speakThread(threadObject.title, threadPosts, () => setSpeaking(false));
      setSpeaking(started);
      setStatus(
        started
          ? `Reading the ${threadObject.title} thread aloud… say “stop reading” or press stop.`
          : "Read-aloud is not supported in this browser.",
      );
      return;
    }
    if (intent.type === "stop_reading") {
      stopSpeaking();
      setSpeaking(false);
      setStatus("Stopped reading.");
      return;
    }
    setStatus(onIntent(intent));
  };

  const activate = async () => {
    if (busy) return;
    if (!recorder.recording) {
      stopSpeaking();
      setSpeaking(false);
      setStatus(null);
      try {
        if (mode === "dictate") onDictationStart();
        await recorder.start();
      } catch (error) {
        setStatus(microphoneErrorMessage(error));
      }
      return;
    }
    setBusy(true);
    try {
      const blob = await recorder.stop();
      const result = await api.transcribe(blob);
      if (mode === "dictate") {
        // An exact command phrase still acts as a command (handlers refuse
        // anything that would retarget the locked draft); everything else
        // is the dictated post text.
        const asCommand = parseVoiceInput(result.text, "command", context);
        if (asCommand.type !== "not_understood" && asCommand.type !== "dictation") {
          handleIntent(asCommand);
        } else {
          setStatus(onDictation(result.text));
        }
        return;
      }
      const intent = parseVoiceInput(result.text, mode, context);
      if (intent.type === "dictation") {
        setStatus(onDictation(intent.text));
      } else {
        handleIntent(intent);
      }
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Transcription failed. Nothing was posted.",
      );
    } finally {
      setBusy(false);
    }
  };

  const hint =
    mode === "review"
      ? "Say “post it”, “retry”, or “cancel”."
      : mode === "dictate"
        ? "Speak your post for the locked thread."
        : VOICE_COMMAND_EXAMPLES;

  return (
    <div className="voice-control" aria-label="Voice control">
      <div className="voice-control__row">
        <button
          className={`record-button voice-button${recorder.recording ? " is-recording" : ""}`}
          onClick={() => void activate()}
          disabled={busy || !transcriptionConfigured}
          title={
            transcriptionConfigured
              ? "Push to talk"
              : "Configure a transcription provider to use voice"
          }
        >
          <span className="mic-icon" aria-hidden="true">{recorder.recording ? "■" : "🎙"}</span>
          {busy
            ? "Transcribing…"
            : recorder.recording
              ? "Stop & process"
              : "Push to talk"}
        </button>
        {speaking && (
          <button
            className="record-button"
            onClick={() => {
              stopSpeaking();
              setSpeaking(false);
              setStatus("Stopped reading.");
            }}
          >
            Stop reading
          </button>
        )}
        {threadObject && !speaking && speechSupported() && (
          <button
            className="record-button"
            onClick={() =>
              handleIntent({ type: "read_thread" })
            }
          >
            Read thread aloud
          </button>
        )}
      </div>

      {recorder.devices.length > 0 && (
        <label className="device-select">
          <span>MIC</span>
          <select
            value={recorder.deviceId}
            onChange={(event) => recorder.setDeviceId(event.target.value)}
            aria-label="Microphone (choose the webcam or glasses microphone)"
          >
            <option value="">System default</option>
            {recorder.devices.map((device, index) => (
              <option key={device.deviceId || index} value={device.deviceId}>
                {device.label || `Microphone ${index + 1}`}
              </option>
            ))}
          </select>
        </label>
      )}
      <small className="voice-control__hint">
        For the glasses, pick the webcam microphone above. The browser only
        captures its audio — video stays with the backend camera.
      </small>

      {!transcriptionConfigured && (
        <p className="inline-note">Speech transcription is unconfigured. Typed posting works normally.</p>
      )}
      {status ? (
        <p className="inline-note" role="status">{status}</p>
      ) : (
        <p className="inline-note">{hint}</p>
      )}
    </div>
  );
}
