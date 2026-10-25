import { describe, expect, it } from "vitest";
import {
  normalizeVoiceText,
  parseVoiceInput,
  voiceModeForState,
  type VoiceContext,
} from "./voiceCommands";

const context: VoiceContext = {
  objects: [
    { id: "concert-poster", title: "Concert poster" },
    { id: "favorite-book", title: "Favorite book" },
    { id: "black-bottle", title: "Black bottle" },
    { id: "blue-bottle", title: "Blue bottle" },
  ],
  authorPosts: [
    { postId: 1, authorName: "Maya" },
    { postId: 2, authorName: "Theo" },
  ],
  provisionalTitles: [],
};

describe("voice mode routing", () => {
  it("dictates into an open thread even before the composer exists", () => {
    expect(voiceModeForState(true, false, false)).toBe("dictate");
    expect(voiceModeForState(false, false, false)).toBe("command");
  });

  it("switches a composer from dictation to explicit review commands", () => {
    expect(voiceModeForState(true, true, false)).toBe("dictate");
    expect(voiceModeForState(true, true, true)).toBe("review");
  });
});

describe("normalizeVoiceText", () => {
  it("lowercases, strips punctuation and curly apostrophes", () => {
    expect(normalizeVoiceText("  Yes, that’s IT! ")).toBe("yes thats it");
  });
});

describe("review mode safety", () => {
  it("only exact confirm phrases post the draft", () => {
    expect(parseVoiceInput("Post it.", "review", context)).toEqual({ type: "post_draft" });
    expect(parseVoiceInput("please post it now", "review", context).type).toBe("not_understood");
  });

  it("cancel and retry are recognised", () => {
    expect(parseVoiceInput("cancel", "review", context)).toEqual({ type: "cancel_draft" });
    expect(parseVoiceInput("record again", "review", context)).toEqual({ type: "retry_dictation" });
  });

  it("never treats review speech as a new object command", () => {
    expect(parseVoiceInput("open the book", "review", context).type).toBe("not_understood");
  });
});

describe("dictate mode", () => {
  it("passes speech through as the draft, even command-like words", () => {
    expect(parseVoiceInput("Post it on Friday!", "dictate", context)).toEqual({
      type: "dictation",
      text: "Post it on Friday!",
    });
  });

  it("still honours stop reading", () => {
    expect(parseVoiceInput("stop reading", "dictate", context)).toEqual({ type: "stop_reading" });
  });
});

describe("command mode", () => {
  it("opens a uniquely matched enrolled object", () => {
    expect(parseVoiceInput("Open the favorite book thread", "command", context)).toEqual({
      type: "open_object",
      objectId: "favorite-book",
      title: "Favorite book",
    });
  });

  it("refuses ambiguous object matches instead of guessing", () => {
    const result = parseVoiceInput("open the bottle", "command", context);
    expect(result.type).toBe("ambiguous");
    if (result.type === "ambiguous") {
      expect(result.candidates).toContain("Black bottle");
      expect(result.candidates).toContain("Blue bottle");
    }
  });

  it("unknown objects are not understood, never force-matched", () => {
    expect(parseVoiceInput("open the toaster", "command", context).type).toBe("not_understood");
  });

  it("enrol keeps the spoken name's casing", () => {
    expect(parseVoiceInput("Enrol this as My Black Bottle.", "command", context)).toEqual({
      type: "enrol_live",
      title: "My Black Bottle",
    });
    expect(parseVoiceInput("enroll this as desk mug", "command", context)).toEqual({
      type: "enrol_live",
      title: "desk mug",
    });
  });

  it("confirm only fires when a provisional sighting exists", () => {
    expect(parseVoiceInput("yes that's it", "command", context).type).toBe("not_understood");
    expect(
      parseVoiceInput("yes that's it", "command", {
        ...context,
        provisionalTitles: ["Black bottle"],
      }),
    ).toEqual({ type: "confirm_provisional" });
  });

  it("refuses to choose between several provisional sightings", () => {
    expect(
      parseVoiceInput("yes that's it", "command", {
        ...context,
        provisionalTitles: ["Black bottle", "Blue bottle"],
      }),
    ).toEqual({
      type: "ambiguous",
      candidates: ["Black bottle", "Blue bottle"],
    });
  });

  it("reply targets a unique author post", () => {
    expect(parseVoiceInput("reply to Maya", "command", context)).toEqual({
      type: "reply_to",
      postId: 1,
      authorName: "Maya",
    });
  });

  it("reply to an author with several posts is ambiguous", () => {
    const multi: VoiceContext = {
      ...context,
      authorPosts: [
        { postId: 1, authorName: "Maya" },
        { postId: 5, authorName: "Maya" },
      ],
    };
    expect(parseVoiceInput("reply to Maya", "command", multi).type).toBe("ambiguous");
  });

  it("read and stop commands parse", () => {
    expect(parseVoiceInput("read the thread", "command", context)).toEqual({ type: "read_thread" });
    expect(parseVoiceInput("stop reading", "command", context)).toEqual({ type: "stop_reading" });
  });
});
