import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { LockedTarget, Profile } from "../types";

type Phase = "editing" | "recording" | "transcribing" | "saving";

interface Props {
  target: LockedTarget;
  profile: Profile;
  transcriptionConfigured: boolean;
  onCancel: () => void;
  onSaved: () => void;
}

function bestRecordingType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
}

export function Composer({
  target,
  profile,
  transcriptionConfigured,
  onCancel,
  onSaved,
}: Props) {
  const [body, setBody] = useState("");
  const [phase, setPhase] = useState<Phase>("editing");
  const [error, setError] = useState<string | null>(null);
  const [hasTranscript, setHasTranscript] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const requestIdRef = useRef(crypto.randomUUID());

  const refreshDevices = async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const allDevices = await navigator.mediaDevices.enumerateDevices();
    setDevices(allDevices.filter((device) => device.kind === "audioinput"));
  };

  useEffect(() => {
    void refreshDevices();
    return () => streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  const startRecording = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: deviceId ? { deviceId: { exact: deviceId } } : true,
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = bestRecordingType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.start();
      setPhase("recording");
      setHasTranscript(false);
      await refreshDevices();
    } catch (recordingError) {
      setError(
        recordingError instanceof DOMException && recordingError.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow access or type your message."
          : "The selected microphone could not be started.",
      );
    }
  };

  const stopAndTranscribe = async () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    setPhase("transcribing");
    setError(null);

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        const recording = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        resolve(recording);
      };
      recorder.stop();
    });

    try {
      const result = await api.transcribe(blob);
      setBody(result.text);
      setHasTranscript(true);
    } catch (transcriptionError) {
      setError(
        transcriptionError instanceof Error
          ? transcriptionError.message
          : "Transcription failed. Your message was not published.",
      );
    } finally {
      setPhase("editing");
    }
  };

  const publish = async () => {
    const cleaned = body.trim();
    if (!cleaned) {
      setError("Write or record a message before posting.");
      return;
    }
    setPhase("saving");
    setError(null);
    try {
      await api.createPost(target.object.id, {
        author_id: profile.id,
        body: cleaned,
        parent_post_id: target.parentPost?.id ?? null,
        client_request_id: requestIdRef.current,
      });
      onSaved();
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? `${saveError.message} Your draft is still here.`
          : "Could not save. Your draft is still here.",
      );
      setPhase("editing");
    }
  };

  const busy = phase === "saving" || phase === "transcribing";

  return (
    <div className="composer" role="dialog" aria-label="Message composer">
      <div className="composer__lock">
        <span aria-hidden="true">⌖</span>
        <div>
          <small>{target.parentPost ? "REPLY LOCKED TO" : "POSTING TO"}</small>
          <strong>{target.object.title}</strong>
          {target.parentPost && (
            <span>Replying to {target.parentPost.author.display_name}</span>
          )}
        </div>
      </div>

      {target.parentPost && (
        <blockquote>“{target.parentPost.body}”</blockquote>
      )}

      <label className="field-label" htmlFor="message-body">
        {hasTranscript ? "Review transcript" : "Your message"}
      </label>
      <textarea
        id="message-body"
        value={body}
        maxLength={500}
        disabled={busy || phase === "recording"}
        onChange={(event) => setBody(event.target.value)}
        placeholder="Say something worth finding…"
        autoFocus
      />
      <div className="character-count">{body.length}/500</div>

      <div className="audio-row">
        {devices.length > 0 && (
          <label className="device-select">
            <span>MIC</span>
            <select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
              <option value="">System default</option>
              {devices.map((device, index) => (
                <option key={device.deviceId || index} value={device.deviceId}>
                  {device.label || `Microphone ${index + 1}`}
                </option>
              ))}
            </select>
          </label>
        )}

        {phase === "recording" ? (
          <button className="record-button is-recording" onClick={stopAndTranscribe}>
            <span className="record-square" /> Stop & transcribe
          </button>
        ) : (
          <button
            className="record-button"
            onClick={startRecording}
            disabled={busy || !transcriptionConfigured}
            title={
              transcriptionConfigured
                ? "Record a message"
                : "Configure a transcription provider to record"
            }
          >
            <span className="mic-icon" aria-hidden="true">●</span>
            {hasTranscript ? "Retry recording" : "Record instead"}
          </button>
        )}
      </div>

      {!transcriptionConfigured && (
        <p className="inline-note">Speech transcription is unconfigured. Typed posting works normally.</p>
      )}
      {phase === "transcribing" && (
        <div className="progress-message"><span className="spinner" /> Transcribing your recording…</div>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="composer__actions">
        <button className="button button--ghost" onClick={onCancel} disabled={busy || phase === "recording"}>
          Cancel
        </button>
        <button className="button button--primary" onClick={publish} disabled={busy || phase === "recording" || !body.trim()}>
          {phase === "saving" ? "Posting…" : target.parentPost ? "Post reply" : "Post"}
        </button>
      </div>
    </div>
  );
}
