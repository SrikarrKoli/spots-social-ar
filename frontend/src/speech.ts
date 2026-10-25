import type { Post } from "./types";

// Read-aloud via the browser's speech synthesis — no backend, no dependency.
// One utterance per message so "stop reading" takes effect immediately.

export function speechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

let finishPending: (() => void) | null = null;

export function stopSpeaking(): void {
  finishPending?.();
  finishPending = null;
  if (speechSupported()) window.speechSynthesis.cancel();
}

export function speakThread(
  objectTitle: string,
  posts: Post[],
  onDone?: () => void,
): boolean {
  if (!speechSupported()) return false;
  stopSpeaking();
  const lines: string[] = [`Thread for ${objectTitle}. ${posts.length} posts.`];
  for (const post of posts) {
    lines.push(`${post.author.display_name}: ${post.body}`);
    for (const reply of post.replies) {
      lines.push(`Reply by ${reply.author.display_name}: ${reply.body}`);
    }
  }
  if (posts.length === 0) lines.push("No posts yet.");
  lines.forEach((line, index) => {
    const utterance = new SpeechSynthesisUtterance(line);
    if (index === lines.length - 1) {
      utterance.onend = () => onDone?.();
      utterance.onerror = () => onDone?.();
    }
    window.speechSynthesis.speak(utterance);
  });
  return true;
}

export function speakText(text: string): Promise<void> {
  stopSpeaking();
  if (!speechSupported()) return Promise.reject(new Error("Speech playback is unavailable in this browser."));
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
