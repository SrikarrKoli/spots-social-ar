import type { Post } from "./types";

// Read-aloud via the browser's speech synthesis — no backend, no dependency.
// One utterance per message so "stop reading" takes effect immediately.

export function speechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function stopSpeaking(): void {
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
