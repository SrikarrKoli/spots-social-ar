import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useVoiceRecorder } from "../hooks/useVoiceRecorder";
import type { LockedTarget, Profile } from "../types";
import { Avatar } from "./Avatar";
import { Icon } from "./Icons";

interface Props {
  target: LockedTarget;
  profile: Profile;
  transcriptionConfigured: boolean;
  startRecording?: boolean;
  onCancel: () => void;
  onSaved: () => void;
}

export function Composer({
  target,
  profile,
  transcriptionConfigured,
  startRecording = false,
  onCancel,
  onSaved,
}: Props) {
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasTranscript, setHasTranscript] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const recorder = useVoiceRecorder();
  const requestIdRef = useRef(crypto.randomUUID());

  const refreshDevices = async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const allDevices = await navigator.mediaDevices.enumerateDevices();
    setDevices(allDevices.filter((device) => device.kind === "audioinput"));
  };

  const record = async () => {
    setError(null);
    if (await recorder.start(deviceId)) {
      setHasTranscript(false);
      await refreshDevices();
    }
  };

  const stopAndTranscribe = async () => {
    const text = await recorder.stop();
    if (text !== null) {
      setBody(text);
      setHasTranscript(true);
    }
  };

  useEffect(() => {
    void refreshDevices();
    if (startRecording && transcriptionConfigured) void record();
  }, []);

  const publish = async () => {
    const cleaned = body.trim();
    if (!cleaned) {
      setError("Write or record a message before posting.");
      return;
    }
    setSaving(true);
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
      setSaving(false);
    }
  };

  const recording = recorder.state === "recording";
  const busy = saving || recorder.state === "transcribing";
  const shownError = error ?? recorder.error;

  return (
    <div className="composer" role="dialog" aria-label="Message composer">
      <div className="composer__target">
        <Avatar profile={profile} size="sm" />
        <span>
          {target.parentPost ? (
            <>Replying to <strong>{target.parentPost.author.display_name}</strong></>
          ) : (
            <>New note on <strong>{target.object.title}</strong></>
          )}
        </span>
        <button className="icon-button" onClick={onCancel} disabled={busy} aria-label="Cancel">
          <Icon name="close" />
        </button>
      </div>

      {target.parentPost && <blockquote>“{target.parentPost.body}”</blockquote>}

      <textarea
        id="message-body"
        value={body}
        maxLength={500}
        disabled={busy || recording}
        onChange={(event) => setBody(event.target.value)}
        placeholder={recording ? "Listening…" : hasTranscript ? "Review your transcript…" : "Add a note…"}
        aria-label={hasTranscript ? "Review transcript" : "Your message"}
        autoFocus
      />

      <div className="composer__bar">
        {recording ? (
          <button className="pill-button pill-button--recording" onClick={stopAndTranscribe}>
            <span className="record-square" /> Stop & transcribe
          </button>
        ) : (
          <button
            className="pill-button"
            onClick={record}
            disabled={busy || !transcriptionConfigured}
            title={transcriptionConfigured ? "Record a message" : "Configure a transcription provider to record"}
          >
            <Icon name="mic" /> {hasTranscript ? "Retry" : "Voice"}
          </button>
        )}
        {devices.length > 1 && (
          <select className="device-select" value={deviceId} onChange={(event) => setDeviceId(event.target.value)} aria-label="Microphone">
            <option value="">Default mic</option>
            {devices.map((device, index) => (
              <option key={device.deviceId || index} value={device.deviceId}>
                {device.label || `Microphone ${index + 1}`}
              </option>
            ))}
          </select>
        )}
        <span className="character-count">{body.length}/500</span>
        <button className="button button--primary" onClick={publish} disabled={busy || recording || !body.trim()}>
          {saving ? "Posting…" : target.parentPost ? "Reply" : "Post"}
        </button>
      </div>

      {!transcriptionConfigured && <p className="inline-note">Speech transcription is unconfigured. Typed posting works normally.</p>}
      {recorder.state === "transcribing" && (
        <div className="progress-message"><span className="spinner" /> Transcribing your recording…</div>
      )}
      {shownError && <p className="form-error" role="alert">{shownError}</p>}
    </div>
  );
}
