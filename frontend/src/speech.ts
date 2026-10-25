import type { Post } from "./types";

// Assistant and note read-aloud share one voice. When the server's Kokoro voice is
// ready, text is rendered by /api/speech and played as audio; otherwise the
// browser's system voice speaks it. Stop always cancels both.

const MAX_SPEECH_CHARS = 600;

let serverVoice = false;
let generation = 0;
let finishPending: (() => void) | null = null;
let request: AbortController | null = null;
let audio: HTMLAudioElement | null = null;
let audioUrl: string | null = null;

function browserSpeech(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

// Set from /api/health: true once the server reports the Kokoro voice is ready.
export function setServerVoice(enabled: boolean): void {
  if (enabled !== serverVoice) stopSpeaking();
  serverVoice = enabled;
}

export function speechSupported(): boolean {
  return serverVoice || browserSpeech();
}

function releaseAudio(): void {
  if (audio) {
    audio.onended = null;
    audio.onerror = null;
    audio.pause();
    audio.removeAttribute("src");
    audio = null;
  }
  if (audioUrl) {
    URL.revokeObjectURL(audioUrl);
    audioUrl = null;
  }
}

export function stopSpeaking(): void {
  // Any reply still being rendered is discarded when it arrives.
  generation += 1;
  finishPending?.();
  finishPending = null;
  request?.abort();
  request = null;
  releaseAudio();
  if (browserSpeech()) window.speechSynthesis.cancel();
}

// Sentence-sized pieces under the server limit, so long notes still play in full.
function speechChunks(text: string): string[] {
  const sentences = text.replace(/\s+/g, " ").trim().match(/[^.!?]+[.!?]*\s*/g) ?? [];
  const chunks: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    for (let start = 0; start < sentence.length; start += MAX_SPEECH_CHARS) {
      const piece = sentence.slice(start, start + MAX_SPEECH_CHARS);
      if ((current + piece).length > MAX_SPEECH_CHARS && current) {
        chunks.push(current.trim());
        current = "";
      }
      current += piece;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

async function playServerChunk(text: string, token: number): Promise<void> {
  request = new AbortController();
  let response: Response;
  try {
    response = await fetch("/api/speech", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: request.signal,
    });
  } catch {
    if (token !== generation) return;
    throw new Error("Couldn't reach the assistant voice. Check that Spots is still running.");
  }
  if (token !== generation) return;
  if (!response.ok) {
    let detail = "The assistant voice couldn't speak that. Try again.";
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // Keep the general message when the error body isn't JSON.
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  if (token !== generation) return;
  audioUrl = URL.createObjectURL(blob);
  const player = new Audio(audioUrl);
  audio = player;
  await new Promise<void>((resolve, reject) => {
    finishPending = () => { finishPending = null; resolve(); };
    player.onended = () => { finishPending = null; resolve(); };
    player.onerror = () => { finishPending = null; reject(new Error("Could not play speech. Check browser audio and your Mac output.")); };
    player.play().catch((error: unknown) => {
      finishPending = null;
      reject(new Error(error instanceof DOMException && error.name === "NotAllowedError"
        ? "Audio playback is blocked. Click anywhere on the page, then try again."
        : "Could not play speech. Check browser audio and your Mac output."));
    });
  });
  if (audio === player) releaseAudio();
}

async function speakWithServer(text: string, token: number): Promise<void> {
  for (const chunk of speechChunks(text)) {
    if (token !== generation) return;
    await playServerChunk(chunk, token);
  }
}

function speakWithBrowser(text: string): Promise<void> {
  if (!browserSpeech()) return Promise.reject(new Error("Speech playback is unavailable in this browser."));
  return new Promise((resolve, reject) => {
    const utterance = new SpeechSynthesisUtterance(text);
    const timer = window.setTimeout(() => {
      finishPending = null;
      window.speechSynthesis.cancel();
      reject(new Error("Speech playback timed out. Use Stop and try again."));
    }, 90000);
    const finish = () => { window.clearTimeout(timer); finishPending = null; resolve(); };
    finishPending = finish;
    utterance.onend = finish;
    utterance.onerror = (event) => {
      window.clearTimeout(timer); finishPending = null;
      if (event.error === "canceled" || event.error === "interrupted") resolve();
      else reject(new Error("Could not play speech. Check browser audio and your Mac output."));
    };
    window.speechSynthesis.speak(utterance);
  });
}

// Resolves when playback ends or is stopped; rejects only on a real failure.
export function speakText(text: string): Promise<void> {
  stopSpeaking();
  const token = generation;
  return serverVoice ? speakWithServer(text, token) : speakWithBrowser(text);
}

export function speakThread(
  objectTitle: string,
  posts: Post[],
  onDone?: () => void,
): boolean {
  if (!speechSupported()) return false;
  const lines: string[] = [`Thread for ${objectTitle}. ${posts.length} posts.`];
  for (const post of posts) {
    lines.push(`${post.author.display_name}: ${post.body}`);
    for (const reply of post.replies) {
      lines.push(`Reply by ${reply.author.display_name}: ${reply.body}`);
    }
  }
  if (posts.length === 0) lines.push("No posts yet.");
  void speakText(lines.join(" ")).catch(() => undefined).finally(() => onDone?.());
  return true;
}
