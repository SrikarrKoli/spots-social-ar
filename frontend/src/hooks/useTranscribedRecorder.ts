import { useState } from "react";
import { api } from "../api";
import { microphoneErrorMessage, useVoiceRecorder } from "./useVoiceRecorder";
// Adapt the Instagram recording controls to the shared microphone and local Whisper.
export function useTranscribedRecorder() {
  const recorder = useVoiceRecorder();
  const [state, setState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [error, setError] = useState<string | null>(null);
  return { state, error, async start() {
    setError(null);
    try { await recorder.start(); setState("recording"); return true; }
    catch (err) { setError(microphoneErrorMessage(err)); return false; }
  }, async stop() {
    setState("transcribing");
    try { const audio = await recorder.stop(); if (!audio.size) return null; return (await api.transcribe(audio)).text; }
    catch (err) { setError(err instanceof Error ? err.message : "Transcription failed. Try again."); return null; }
    finally { setState("idle"); }
  } };
}
