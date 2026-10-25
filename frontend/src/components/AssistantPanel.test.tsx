// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AssistantPanel } from "./AssistantPanel";
import { api } from "../api";
import { speakText } from "../speech";
import type { AssistantResponse, HealthResponse } from "../types";
vi.mock("../api", () => ({ api: { askAssistant: vi.fn() } }));
vi.mock("./MemoryRecall", () => ({ MemoryRecall: () => null }));
vi.mock("../speech", () => ({ speakText: vi.fn().mockResolvedValue(undefined), stopSpeaking: vi.fn() }));
vi.mock("../hooks/useVoiceRecorder", () => ({ microphoneErrorMessage: () => "Error", useVoiceRecorder: () => ({ devices: [], deviceId: "", setDeviceId: vi.fn(), stop: vi.fn() }) }));
const health = { assistant_status: "ready", assistant_model: "local", transcription_status: "configured" } as HealthResponse;
const base: AssistantResponse = { text: "What should I remember?", model: "local", camera_used: true, camera_source: "camera", captured_at: null, awaiting_description: false, pending_edit_ids: [], pending_edit_body: "", read_aloud: false, awaiting_note: false, awaiting_name: false, awaiting_reply: false, pending_reply_to: null, pending_title: "", pending_body: "", pending_delete_ids: [], deletion_id: null, deleted_note_ids: [], memory_changed: false, saved_note: null, saved_object: null };
afterEach(() => { cleanup(); vi.clearAllMocks(); });
async function submit(text: string) {
  await waitFor(() => expect((screen.getByRole("textbox", { name: "Ask Spots" }) as HTMLInputElement).disabled).toBe(false));
  fireEvent.change(screen.getByRole("textbox", { name: "Ask Spots" }), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /^Ask$/ }));
}
it("carries the spoken object name into the following note turn", async () => {
  vi.mocked(api.askAssistant).mockResolvedValueOnce({ ...base, awaiting_note: true, pending_title: "Blue water bottle" }).mockResolvedValueOnce({ ...base, text: "Saved." });
  render(<AssistantPanel health={health} object={null} authorId="guest" onSaved={vi.fn()} />);
  await submit("Call it blue water bottle and take a note");
  await screen.findByText("What should I remember?");
  await submit("It looks really nice.");
  await waitFor(() => expect(api.askAssistant).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.askAssistant).mock.calls[1][5]).toMatchObject({ awaitingNote: true, pendingTitle: "Blue water bottle" });
});
it("carries a held note into the naming turn and clears it for a new conversation", async () => {
  vi.mocked(api.askAssistant).mockResolvedValueOnce({ ...base, text: "What should I call it?", awaiting_name: true, pending_body: "It looks really nice." }).mockResolvedValue({ ...base, text: "Saved." });
  render(<AssistantPanel health={health} object={null} authorId="guest" onSaved={vi.fn()} />);
  await submit("Take a note: it looks really nice.");
  await screen.findByText("What should I call it?");
  await submit("Blue water bottle");
  await waitFor(() => expect(api.askAssistant).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.askAssistant).mock.calls[1][5]).toMatchObject({ awaitingName: true, pendingBody: "It looks really nice." });
  await waitFor(() => expect((screen.getByRole("button", { name: "New conversation" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
  await submit("Hello");
  await waitFor(() => expect(api.askAssistant).toHaveBeenCalledTimes(3));
  expect(vi.mocked(api.askAssistant).mock.calls[2][5]).toMatchObject({ awaitingName: false, pendingBody: "", pendingTitle: "" });
});

it("keeps deletion choices bound to the follow-up and passes the undo ID", async () => {
  vi.mocked(api.askAssistant)
    .mockResolvedValueOnce({ ...base, text: "Which note?", pending_delete_ids: [11, 12] })
    .mockResolvedValueOnce({ ...base, text: "Deleted.", deleted_note_ids: [12], memory_changed: true, deletion_id: "delete:chosen-note" })
    .mockResolvedValueOnce({ ...base, text: "Restored.", memory_changed: true });
  render(<AssistantPanel health={health} object={null} authorId="guest" onSaved={vi.fn()} />);
  await submit("Delete a note");
  await screen.findByText("Which note?");
  await submit("the second one");
  await screen.findByText("Deleted.");
  expect(vi.mocked(api.askAssistant).mock.calls[1][5]).toMatchObject({ pendingDeleteIds: [11, 12] });
  await submit("undo");
  await screen.findByText("Restored.");
  expect(vi.mocked(api.askAssistant).mock.calls[2][5]).toMatchObject({ pendingDeleteIds: [], deletionId: "delete:chosen-note" });
});


it("explicit read-aloud requests speak saved comments even when automatic speech is off", async () => {
  vi.mocked(api.askAssistant).mockResolvedValueOnce({ ...base, text: 'Maya: Bought it yesterday.', read_aloud: true });
  render(<AssistantPanel health={health} object={null} authorId="guest" onSaved={vi.fn()} />);
  fireEvent.click(screen.getByRole('checkbox', { name: /Speak answers/ }));
  await submit('Read past comments aloud');
  await waitFor(() => expect(speakText).toHaveBeenCalledWith('Maya: Bought it yesterday.'));
});

it("retains the replacement while selecting a comment to edit", async () => {
  vi.mocked(api.askAssistant)
    .mockResolvedValueOnce({ ...base, text: 'Which comment?', pending_edit_ids: [11, 12], pending_edit_body: 'Bought it yesterday.' })
    .mockResolvedValueOnce({ ...base, text: 'Updated.', memory_changed: true });
  render(<AssistantPanel health={health} object={null} authorId="guest" onSaved={vi.fn()} />);
  await submit('Change my comment to Bought it yesterday.');
  await screen.findByText('Which comment?');
  await submit('second one');
  await screen.findByText('Updated.');
  expect(vi.mocked(api.askAssistant).mock.calls[1][5]).toMatchObject({ pendingEditIds: [11, 12], pendingEditBody: 'Bought it yesterday.' });
});
