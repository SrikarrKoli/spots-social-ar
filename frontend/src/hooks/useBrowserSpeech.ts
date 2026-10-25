import { useEffect, useRef, useState } from "react";

// The browser's own speech recognition (Chrome, Edge, Safari), used when the backend has no
// transcription provider. Chrome sends the audio to Google's speech service to transcribe it.

interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}

interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}

interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  const scope = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export function browserSpeechSupported() {
  return typeof window !== "undefined" && recognitionConstructor() !== null;
}

export function useBrowserSpeech() {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<Recognition | null>(null);
  const finalRef = useRef("");
  const resolveRef = useRef<((text: string) => void) | null>(null);
  const onEndRef = useRef<((text: string) => void) | null>(null);

  useEffect(() => () => recognitionRef.current?.abort(), []);

  // `continuous: false` ends by itself after one phrase (good for commands); `onEnd` then gets the text.
  const start = ({ continuous = true, onEnd }: { continuous?: boolean; onEnd?: (text: string) => void } = {}) => {
    const Constructor = recognitionConstructor();
    if (!Constructor) return false;
    onEndRef.current = onEnd ?? null;
    setError(null);
    setTranscript("");
    finalRef.current = "";
    const recognition = new Constructor();
    recognition.lang = navigator.language || "en-US";
    recognition.continuous = continuous;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal) finalRef.current += result[0].transcript;
        else interim += result[0].transcript;
      }
      setTranscript(`${finalRef.current}${interim}`.trim());
    };
    recognition.onerror = (event) => {
      if (event.error === "aborted") return;
      setError(
        event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "Microphone is blocked for this site. Allow it in browser site settings, then try the microphone again."
          : event.error === "no-speech"
            ? "Didn't catch that. Try again or type your reply."
            : "Speech recognition stopped. Try again or type your reply.",
      );
    };
    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
      const text = finalRef.current.trim();
      if (resolveRef.current) resolveRef.current(text);
      else onEndRef.current?.(text);
      resolveRef.current = null;
      onEndRef.current = null;
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      onEndRef.current = null;
      setError("Speech recognition couldn't start. Type your reply instead.");
      return false;
    }
    setListening(true);
    return true;
  };

  // Resolves with everything recognised once the browser has finished.
  const stop = () =>
    new Promise<string>((resolve) => {
      const recognition = recognitionRef.current;
      if (!recognition) {
        resolve(finalRef.current.trim());
        return;
      }
      resolveRef.current = resolve;
      recognition.stop();
    });

  const cancel = () => {
    resolveRef.current = null;
    onEndRef.current = null;
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    recognition?.abort();
    setListening(false);
  };

  return { listening, transcript, error, start, stop, cancel };
}
