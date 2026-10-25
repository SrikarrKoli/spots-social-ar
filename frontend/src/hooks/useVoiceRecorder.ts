import { useCallback, useEffect, useRef, useState } from "react";

// Shared microphone recorder for the composer and the global voice control.
//
// The selected device persists across both (localStorage + a window event so
// live hook instances stay in sync): the wearer picks the webcam/glasses
// microphone once. Only audio is ever requested — the browser never opens
// the webcam's video here, so this does not compete with the backend's
// single OpenCV capture.

const DEVICE_KEY = "locus.micDeviceId";
const DEVICE_EVENT = "locus:mic-device";

function storedDeviceId(): string {
  try {
    return window.localStorage.getItem(DEVICE_KEY) ?? "";
  } catch {
    return "";
  }
}

function bestRecordingType(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
}

export interface VoiceRecorder {
  devices: MediaDeviceInfo[];
  deviceId: string;
  setDeviceId: (deviceId: string) => void;
  recording: boolean;
  start: () => Promise<void>;
  stop: () => Promise<Blob>;
  refreshDevices: () => Promise<void>;
}

export function useVoiceRecorder(): VoiceRecorder {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceIdState] = useState<string>(storedDeviceId);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const allDevices = await navigator.mediaDevices.enumerateDevices();
    setDevices(allDevices.filter((device) => device.kind === "audioinput"));
  }, []);

  useEffect(() => {
    void refreshDevices().catch(() => undefined);
    const sync = () => setDeviceIdState(storedDeviceId());
    window.addEventListener(DEVICE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(DEVICE_EVENT, sync);
      window.removeEventListener("storage", sync);
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [refreshDevices]);

  const setDeviceId = useCallback((next: string) => {
    setDeviceIdState(next);
    try {
      window.localStorage.setItem(DEVICE_KEY, next);
    } catch {
      // Private-mode storage failures still keep the in-memory choice.
    }
    window.dispatchEvent(new Event(DEVICE_EVENT));
  }, []);

  const start = useCallback(async () => {
    if (recorderRef.current?.state === "recording") return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: deviceId ? { deviceId: { exact: deviceId } } : true,
    });
    streamRef.current = stream;
    try {
      chunksRef.current = [];
      const mimeType = bestRecordingType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.start();
      setRecording(true);
      void refreshDevices().catch(() => undefined);
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
      throw error;
    }
  }, [deviceId, refreshDevices]);

  const stop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setRecording(false);
      return new Blob();
    }
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
    recorderRef.current = null;
    setRecording(false);
    return blob;
  }, []);

  return { devices, deviceId, setDeviceId, recording, start, stop, refreshDevices };
}

export function microphoneErrorMessage(error: unknown): string {
  return error instanceof DOMException && error.name === "NotAllowedError"
    ? "Microphone permission was denied. Allow access or type your message."
    : "The selected microphone could not be started.";
}
