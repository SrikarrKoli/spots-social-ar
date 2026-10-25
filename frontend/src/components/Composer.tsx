import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { microphoneErrorMessage, useVoiceRecorder } from "../hooks/useVoiceRecorder";
import { stopSpeaking } from "../speech";
import type { LockedTarget, Profile } from "../types";

type Phase = "editing" | "recording" | "transcribing" | "saving";

export interface ExternalTranscript {
  text: string;
  nonce: number;
}

export interface VoiceDraftAction {
  type: "post" | "cancel" | "retry";
  nonce: number;
}

interface Props {
  target: LockedTarget;
  profile: Profile;
  transcriptionConfigured: boolean;
  externalTranscript?: ExternalTranscript | null;
  voiceAction?: VoiceDraftAction | null;
  onReviewChange?: (reviewing: boolean) => void;
  onCancel: () => void;
  onSaved: () => void;
}

export function Composer({
  target,
  profile,
  transcriptionConfigured,
  externalTranscript = null,
  voiceAction = null,
  onReviewChange,
  onCancel,
  onSaved,
}: Props) {
  const [body, setBody] = useState("");
  const [phase, setPhase] = useState<Phase>("editing");
  const [error, setError] = useState<string | null>(null);
  const [hasTranscript, setHasTranscript] = useState(false);
  const recorder = useVoiceRecorder();
  const requestIdRef = useRef(crypto.randomUUID());
  const lastTranscriptNonce = useRef(0);
  const lastActionNonce = useRef(0);

  // A transcript dictated through the global push-to-talk control lands in
  // this composer, locked to the target captured when it was opened.
  useEffect(() => {
    if (!externalTranscript || externalTranscript.nonce === lastTranscriptNonce.current) return;
    lastTranscriptNonce.current = externalTranscript.nonce;
    setBody(externalTranscript.text);
    setHasTranscript(true);
    setError(null);
  }, [externalTranscript]);

  const publishRef = useRef<() => Promise<void>>(async () => undefined);

  // Voice-confirm: "post it" / "cancel" / "retry" from the global control
  // act on this draft. They can never change the locked target.
  useEffect(() => {
    if (!voiceAction || voiceAction.nonce === lastActionNonce.current) return;
    lastActionNonce.current = voiceAction.nonce;
    if (voiceAction.type === "post") {
      void publishRef.current();
    } else if (voiceAction.type === "cancel") {
      onCancel();
    } else {
      setBody("");
      setHasTranscript(false);
      setError(null);
    }
  }, [voiceAction, onCancel]);

  const reviewing = hasTranscript && phase === "editing" && body.trim().length > 0;
  useEffect(() => {
    onReviewChange?.(reviewing);
  }, [reviewing, onReviewChange]);
  useEffect(() => () => onReviewChange?.(false), [onReviewChange]);

  const startRecording = async () => {
    setError(null);
    stopSpeaking();
    try {
      await recorder.start();
      setPhase("recording");
      setHasTranscript(false);
    } catch (recordingError) {
      setError(microphoneErrorMessage(recordingError));
    }
  };

  const stopAndTranscribe = async () => {
    if (!recorder.recording) return;
    setPhase("transcribing");
    setError(null);
    try {
      const blob = await recorder.stop();
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
  publishRef.current = publish;

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
        {recorder.devices.length > 0 && (
          <label className="device-select">
            <span>MIC</span>
            <select value={recorder.deviceId} onChange={(event) => recorder.setDeviceId(event.target.value)}>
              <option value="">System default</option>
              {recorder.devices.map((device, index) => (
                <option key={device.deviceId || index} value={device.deviceId}>
                  {device.label || `Microphone ${index + 1}`}
                </option>
              ))}
            </select>
          </label>
        )}

        {phase === "recording" ? (
          <button className="record-button is-recording" onClick={() => void stopAndTranscribe()}>
            <span className="record-square" /> Stop & transcribe
          </button>
        ) : (
          <button
            className="record-button"
            onClick={() => void startRecording()}
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
      {reviewing && (
        <p className="inline-note">
          Review it, then press Post — or push-to-talk and say “post it”, “retry”, or “cancel”.
        </p>
      )}
      {phase === "transcribing" && (
        <div className="progress-message"><span className="spinner" /> Transcribing your recording…</div>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="composer__actions">
        <button className="button button--ghost" onClick={onCancel} disabled={busy || phase === "recording"}>
          Cancel
        </button>
        <button className="button button--primary" onClick={() => void publish()} disabled={busy || phase === "recording" || !body.trim()}>
          {phase === "saving" ? "Posting…" : target.parentPost ? "Post reply" : "Post"}
        </button>
      </div>
    </div>
  );
}
