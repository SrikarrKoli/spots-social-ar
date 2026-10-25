import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export type RecorderState = "idle" | "recording" | "transcribing";

function bestRecordingType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
}

export function useVoiceRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);

  const start = async (deviceId = "") => {
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
      setState("recording");
      return true;
    } catch (recordingError) {
      setError(
        recordingError instanceof DOMException && recordingError.name === "NotAllowedError"
          ? "Microphone is blocked for this site. Allow it in browser site settings, then try the microphone again."
          : "The selected microphone could not be started.",
      );
      return false;
    }
  };

  // Resolves with the transcript, or null when transcription failed.
  const stop = async () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return null;
    setState("transcribing");
    setError(null);

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        const recording = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        resolve(recording);
      };
      recorder.stop();
    });

    try {
      const result = await api.transcribe(blob);
      return result.text;
    } catch (transcriptionError) {
      setError(
        transcriptionError instanceof Error
          ? transcriptionError.message
          : "Transcription failed. Your message was not published.",
      );
      return null;
    } finally {
      setState("idle");
    }
  };

  return { state, error, start, stop };
}
