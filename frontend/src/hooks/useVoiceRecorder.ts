import { VoiceActivity } from "../voiceActivity";
import { useCallback, useEffect, useRef, useState } from "react";

const DEVICE_KEY = "locus.micDeviceId";
const DEVICE_EVENT = "locus:mic-device";
// All voice surfaces share one microphone owner, including during permission prompts.
let microphoneOwner: symbol | null = null;

function storedDeviceId(): string {
  try { return window.localStorage.getItem(DEVICE_KEY) ?? ""; } catch { return ""; }
}
function bestRecordingType(): string {
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}
export interface VoiceRecorder {
  devices: MediaDeviceInfo[];
  deviceId: string;
  setDeviceId: (deviceId: string) => void;
  recording: boolean;
  start: (onEnd?: (speechDetected: boolean) => void) => Promise<void>;
  stop: () => Promise<Blob>;
  refreshDevices: () => Promise<void>;
}
export function useVoiceRecorder(): VoiceRecorder {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceIdState] = useState<string>(storedDeviceId);
  const [recording, setRecording] = useState(false);
  const owner = useRef(Symbol("microphone"));
  const attempt = useRef(0);
  const mounted = useRef(true);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const monitorCleanup = useRef<() => void>(() => undefined);
  const stopping = useRef<Promise<Blob> | null>(null);

  const release = useCallback(() => {
    monitorCleanup.current();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (microphoneOwner === owner.current) microphoneOwner = null;
  }, []);
  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const all = await navigator.mediaDevices.enumerateDevices();
    if (mounted.current) setDevices(all.filter((device) => device.kind === "audioinput"));
  }, []);
  useEffect(() => {
    mounted.current = true;
    void refreshDevices().catch(() => undefined);
    const sync = () => setDeviceIdState(storedDeviceId());
    const changed = () => { void refreshDevices().catch(() => undefined); };
    window.addEventListener(DEVICE_EVENT, sync);
    window.addEventListener("storage", sync);
    navigator.mediaDevices?.addEventListener("devicechange", changed);
    return () => {
      mounted.current = false; attempt.current += 1;
      window.removeEventListener(DEVICE_EVENT, sync);
      window.removeEventListener("storage", sync);
      navigator.mediaDevices?.removeEventListener("devicechange", changed);
      release();
    };
  }, [refreshDevices, release]);
  const setDeviceId = useCallback((next: string) => {
    setDeviceIdState(next);
    try { window.localStorage.setItem(DEVICE_KEY, next); } catch { /* Keep session choice. */ }
    window.dispatchEvent(new Event(DEVICE_EVENT));
  }, []);

  const start = useCallback(async (onEnd?: (speechDetected: boolean) => void) => {
    if (microphoneOwner !== null || stopping.current) throw new Error("Finish the current recording before starting another.");
    microphoneOwner = owner.current;
    const token = ++attempt.current;
    try {
      let permissionTimer: number | undefined;
      let permissionTimedOut = false;
      const requestedStream = navigator.mediaDevices.getUserMedia({
        audio: { ...(deviceId ? { deviceId: { exact: deviceId } } : {}), echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }).then(stream => {
        if (permissionTimedOut) stream.getTracks().forEach(track => track.stop());
        return stream;
      });
      let stream: MediaStream;
      try {
        stream = await Promise.race([requestedStream, new Promise<never>((_, reject) => {
          permissionTimer = window.setTimeout(() => {
            permissionTimedOut = true;
            reject(new Error("Microphone access is waiting for browser permission. Allow the microphone for this page, then tap Speak."));
          }, 12000);
        })]);
      } finally { window.clearTimeout(permissionTimer); }
      if (!mounted.current || token !== attempt.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = bestRecordingType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      if (onEnd) {
        const context = new AudioContext();
        monitorCleanup.current = () => { void context.close(); monitorCleanup.current = () => undefined; };
        let resumeTimer: number | undefined;
        try {
          await Promise.race([context.resume(), new Promise<never>((_, reject) => {
            resumeTimer = window.setTimeout(() => reject(new Error("Audio is paused by the browser. Tap Speak to activate the microphone and audio.")), 4000);
          })]);
        } finally { window.clearTimeout(resumeTimer); }
        if (!mounted.current || token !== attempt.current) return;
        const source = context.createMediaStreamSource(stream);
        const analyser = context.createAnalyser();
        analyser.fftSize = 1024;
        source.connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        const activity = new VoiceActivity(performance.now());
        const timer = window.setInterval(() => {
          analyser.getFloatTimeDomainData(samples);
          const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
          const result = activity.update(rms, performance.now());
          if (result) { monitorCleanup.current(); onEnd(result === "speech_end"); }
        }, 50);
        monitorCleanup.current = () => {
          window.clearInterval(timer); source.disconnect(); void context.close();
          monitorCleanup.current = () => undefined;
        };
      }
      recorder.start();
      setRecording(true);
      void refreshDevices().catch(() => undefined);
    } catch (error) {
      if (token === attempt.current) { release(); recorderRef.current = null; }
      throw error;
    }
  }, [deviceId, refreshDevices, release]);

  const stop = useCallback(async () => {
    if (stopping.current) return stopping.current;
    attempt.current += 1;
    monitorCleanup.current();
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      release(); recorderRef.current = null;
      if (mounted.current) setRecording(false);
      return new Blob();
    }
    stopping.current = new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        release(); recorderRef.current = null;
        if (mounted.current) setRecording(false);
        resolve(blob);
      };
      recorder.stop();
    });
    try { return await stopping.current; } finally { stopping.current = null; }
  }, [release]);
  return { devices, deviceId, setDeviceId, recording, start, stop, refreshDevices };
}
export function microphoneErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") return "Microphone permission was denied. Allow microphone access for this site and try again.";
  if (error instanceof Error && /^(Finish the current|Microphone access is waiting|Audio is paused)/.test(error.message)) return error.message;
  return "The selected microphone could not be started. Reconnect it or choose System default.";
}
