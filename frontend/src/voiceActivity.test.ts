import { describe, expect, it } from "vitest";
import { VoiceActivity } from "./voiceActivity";
import { parseVoiceInput } from "./voiceCommands";

describe("hands-free voice turns", () => {
  it("does not submit silence as a question", () => {
    const activity = new VoiceActivity(0);
    expect(activity.update(0.001, 5000)).toBeNull();
    expect(activity.update(0.001, 10001)).toBe("no_speech");
  });
  it("waits for speech and a pause before finishing", () => {
    const activity = new VoiceActivity(0);
    for (let t = 50; t <= 400; t += 50) expect(activity.update(0.05, t)).toBeNull();
    expect(activity.update(0, 1000)).toBeNull();
    expect(activity.update(0, 1650)).toBe("speech_end");
  });
  it("ignores a brief click as speech", () => {
    const activity = new VoiceActivity(0);
    activity.update(0.05, 50);
    expect(activity.update(0, 1600)).toBeNull();
    expect(activity.update(0, 10001)).toBe("no_speech");
  });
  it("bounds a long speech turn", () => {
    const activity = new VoiceActivity(0);
    for (let t = 50; t < 25000; t += 50) activity.update(0.05, t);
    expect(activity.update(0.05, 25050)).toBe("speech_end");
  });
});

it("post note begins a draft, while post it publishes only during review", () => {
  const context = { objects: [], authorPosts: [], provisionalTitles: [] };
  expect(parseVoiceInput("Post note.", "command", context).type).toBe("start_note");
  expect(parseVoiceInput("post it", "command", context).type).toBe("not_understood");
  expect(parseVoiceInput("post it", "review", context).type).toBe("post_draft");
  expect(parseVoiceInput("read my note", "review", context).type).toBe("read_draft");
});
