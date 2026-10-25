// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ThreadPanel } from "./ThreadPanel";
import { api } from "../api";
import { speakText } from "../speech";

vi.mock("../api", () => ({ api: { thread: vi.fn(), transcribe: vi.fn(), createPost: vi.fn() } }));
vi.mock("../speech", () => ({ stopSpeaking: vi.fn(), speakText: vi.fn().mockResolvedValue(undefined), speechSupported: () => true, speakThread: vi.fn() }));
vi.mock("../hooks/useVoiceRecorder", () => ({
  microphoneErrorMessage: () => "microphone error",
  useVoiceRecorder: () => {
    const [recording, setRecording] = useState(false);
    return { devices: [], deviceId: "", recording, setDeviceId: vi.fn(), refreshDevices: vi.fn(),
      start: async () => setRecording(true), stop: async () => { setRecording(false); return new Blob(["audio"]); } };
  },
}));
const profile = { id: "maya", display_name: "Maya", initials: "M", color: "red" };
const object = { id: "poster", identity_key: "poster", title: "Poster", identity_kind: "instance", description: null };
const post = { id: 1, object_id: "poster", author: profile, body: "Anyone going Friday?", created_at: "2026-10-25T00:00:00Z", parent_post_id: null, replies: [] };
afterEach(() => { cleanup(); vi.clearAllMocks(); });
async function mount() {
  vi.mocked(api.thread).mockResolvedValue({ object, posts: [post], updated_at: null });
  render(<ThreadPanel object={object} availableObjects={[object]} onSelectObject={vi.fn()} profile={profile} transcriptionConfigured />);
  await screen.findByText("Anyone going Friday?");
}
async function say(text: string) {
  vi.mocked(api.transcribe).mockResolvedValueOnce({ text, provider: "test" });
  fireEvent.click(screen.getByRole("button", { name: /Push to talk/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Stop & process/ }));
}
it("reply command works before a draft exists and keeps the parent target", async () => {
  await mount();
  await say("reply to Maya");
  await screen.findByText("REPLY LOCKED TO");
  expect(screen.getByText("Replying to Maya")).toBeTruthy();
  expect(api.createPost).not.toHaveBeenCalled();
});
it("post note, dictate, and read draft never publish without confirmation", async () => {
  await mount();
  await say("post note");
  await screen.findByRole("textbox", { name: "Your message" });
  await say("See you Friday at seven");
  await screen.findByRole("textbox", { name: "Review transcript" });
  await say("read my note");
  await waitFor(() => expect(speakText).toHaveBeenCalledWith(expect.stringContaining("See you Friday at seven")));
  expect(api.createPost).not.toHaveBeenCalled();
});

it("an assistant handoff remains an editable draft and does not publish", async () => {
  vi.mocked(api.thread).mockResolvedValue({ object, posts: [post], updated_at: null });
  const handled = vi.fn();
  render(<ThreadPanel object={object} availableObjects={[object]} onSelectObject={vi.fn()} profile={profile} transcriptionConfigured assistantDraft={{ text: "This TV has great picture quality.", nonce: 100 }} onAssistantDraftHandled={handled} />);
  const draft = await screen.findByRole("textbox", { name: "Review transcript" });
  expect((draft as HTMLTextAreaElement).value).toBe("This TV has great picture quality.");
  expect(handled).toHaveBeenCalledTimes(1);
  expect(api.createPost).not.toHaveBeenCalled();
});
