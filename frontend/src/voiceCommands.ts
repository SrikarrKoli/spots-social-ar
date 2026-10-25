// Deterministic voice-command parsing for Locus.
//
// Speech becomes a comment only through an explicit "post it" (or the Post
// button) — transcription alone never publishes. Commands are matched
// exactly after normalisation, must resolve uniquely, and anything
// ambiguous is reported back rather than guessed, mirroring the
// recognizer's "ambiguous = unknown, never force-match" rule.

export type VoiceMode = "command" | "dictate" | "review";

export interface VoiceObjectOption {
  id: string;
  title: string;
}

export interface VoiceAuthorOption {
  postId: number;
  authorName: string;
}

export interface VoiceContext {
  objects: VoiceObjectOption[];
  authorPosts: VoiceAuthorOption[];
  provisionalTitles: string[];
}

export type VoiceIntent =
  | { type: "post_draft" }
  | { type: "cancel_draft" }
  | { type: "retry_dictation" }
  | { type: "confirm_provisional" }
  | { type: "enrol_live"; title: string }
  | { type: "open_object"; objectId: string; title: string }
  | { type: "reply_to"; postId: number; authorName: string }
  | { type: "read_thread" }
  | { type: "stop_reading" }
  | { type: "dictation"; text: string }
  | { type: "ambiguous"; candidates: string[] }
  | { type: "not_understood"; heard: string };

export function voiceModeForState(
  hasThread: boolean,
  hasComposer: boolean,
  reviewing: boolean,
): VoiceMode {
  if (hasComposer) return reviewing ? "review" : "dictate";
  return hasThread ? "dictate" : "command";
}

export function normalizeVoiceText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[’‘]/g, "'")
    .replace(/'/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

const POST_PHRASES = new Set([
  "post it",
  "send it",
  "post",
  "send",
  "publish",
  "publish it",
]);

const CANCEL_PHRASES = new Set([
  "cancel",
  "discard that",
  "discard it",
  "never mind",
  "nevermind",
]);

const RETRY_PHRASES = new Set(["retry", "record again", "try again", "redo"]);

const CONFIRM_PHRASES = new Set([
  "yes thats it",
  "yes that is it",
  "thats it",
  "that is it",
  "confirm",
  "confirm it",
  "yes confirm",
  "yes it is",
]);

const READ_PHRASES = new Set([
  "read the thread",
  "read thread",
  "read the posts",
  "read posts",
  "read it aloud",
  "read aloud",
  "read the comments",
  "read comments",
]);

const STOP_PHRASES = new Set(["stop reading", "stop", "be quiet", "stop talking"]);

function matchesTitle(query: string, title: string): boolean {
  const normalizedTitle = normalizeVoiceText(title);
  return (
    normalizedTitle === query ||
    normalizedTitle.includes(query) ||
    query.includes(normalizedTitle)
  );
}

function matchObjects(
  query: string,
  objects: VoiceObjectOption[],
): VoiceIntent | null {
  const matches = objects.filter((object) => matchesTitle(query, object.title));
  if (matches.length === 1) {
    return { type: "open_object", objectId: matches[0].id, title: matches[0].title };
  }
  if (matches.length > 1) {
    return { type: "ambiguous", candidates: matches.map((object) => object.title) };
  }
  return null;
}

function extractEnrolTitle(rawText: string): string | null {
  // Keep the speaker's casing for the object name; only strip trailing
  // sentence punctuation.
  const match = rawText.match(
    /\benro(?:l|ll)(?:\s+this)?(?:\s+(?:as|called|named))?\s+(.+)$/i,
  );
  if (!match) return null;
  const title = match[1].trim().replace(/[.!?]+$/, "").trim();
  return title.length > 0 ? title : null;
}

export function parseVoiceInput(
  rawText: string,
  mode: VoiceMode,
  context: VoiceContext,
): VoiceIntent {
  const heard = rawText.trim();
  const text = normalizeVoiceText(rawText);
  if (!text) return { type: "not_understood", heard };

  if (STOP_PHRASES.has(text)) return { type: "stop_reading" };

  if (mode === "dictate") {
    return { type: "dictation", text: heard };
  }

  if (mode === "review") {
    if (POST_PHRASES.has(text)) return { type: "post_draft" };
    if (CANCEL_PHRASES.has(text)) return { type: "cancel_draft" };
    if (RETRY_PHRASES.has(text)) return { type: "retry_dictation" };
    return { type: "not_understood", heard };
  }

  // Command mode ------------------------------------------------------------
  if (CONFIRM_PHRASES.has(text)) {
    if (context.provisionalTitles.length === 1) {
      return { type: "confirm_provisional" };
    }
    if (context.provisionalTitles.length > 1) {
      return { type: "ambiguous", candidates: context.provisionalTitles };
    }
    return { type: "not_understood", heard };
  }

  if (READ_PHRASES.has(text)) return { type: "read_thread" };

  const enrolTitle = extractEnrolTitle(heard);
  if (enrolTitle) return { type: "enrol_live", title: enrolTitle };
  if (/^enro(?:l|ll)\b/.test(text)) return { type: "not_understood", heard };

  const replyMatch = text.match(/^reply to (.+)$/);
  if (replyMatch) {
    const query = replyMatch[1];
    const matches = context.authorPosts.filter((option) =>
      matchesTitle(query, option.authorName),
    );
    const uniquePostIds = [...new Set(matches.map((option) => option.postId))];
    if (uniquePostIds.length === 1) {
      const match = matches[0];
      return { type: "reply_to", postId: match.postId, authorName: match.authorName };
    }
    if (uniquePostIds.length > 1) {
      return {
        type: "ambiguous",
        candidates: matches.map(
          (option) => `${option.authorName}'s post`,
        ),
      };
    }
    return { type: "not_understood", heard };
  }

  const openMatch = text.match(
    /^(?:open|show|switch to|go to)(?: the)? (.+?)(?: thread)?$/,
  );
  if (openMatch) {
    return matchObjects(openMatch[1], context.objects) ?? { type: "not_understood", heard };
  }

  return { type: "not_understood", heard };
}

export const VOICE_COMMAND_EXAMPLES =
  "Try: “open the book”, “reply to Maya”, “enrol this as my mug”, “read the thread”, or hold the button and dictate a post in an open thread.";
