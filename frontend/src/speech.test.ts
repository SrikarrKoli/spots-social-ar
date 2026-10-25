import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setServerVoice, speakText, stopSpeaking } from "./speech";

class FakeAudio {
  static played: FakeAudio[] = [];
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly src: string) {}
  play() { FakeAudio.played.push(this); return Promise.resolve(); }
  pause() {}
  removeAttribute() {}
}

describe("server voice playback", () => {
  beforeEach(() => {
    FakeAudio.played = [];
    vi.stubGlobal("Audio", FakeAudio);
    vi.stubGlobal("URL", { createObjectURL: () => "blob:voice", revokeObjectURL: vi.fn() });
    setServerVoice(true);
  });
  afterEach(() => {
    stopSpeaking();
    setServerVoice(false);
    vi.unstubAllGlobals();
  });

  it("renders text through the Kokoro endpoint and resolves when playback ends", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(["wav"]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const done = speakText("Saved your note on the water bottle.");
    await vi.waitFor(() => expect(FakeAudio.played).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/speech", expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ text: "Saved your note on the water bottle." });
    FakeAudio.played[0].onended?.();
    await expect(done).resolves.toBeUndefined();
  });

  it("never plays a reply that arrives after Stop", async () => {
    let respond: (response: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { respond = resolve; })));
    const done = speakText("This reply was cancelled.");
    stopSpeaking();
    respond(new Response(new Blob(["wav"]), { status: 200 }));
    await expect(done).resolves.toBeUndefined();
    expect(FakeAudio.played).toHaveLength(0);
  });

  it("reports a busy or unavailable voice instead of pretending it spoke", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "The assistant voice is busy. Try again in a moment." }), { status: 503 })));
    await expect(speakText("Hello")).rejects.toThrow("busy");
    expect(FakeAudio.played).toHaveLength(0);
  });

  it("splits long text into pieces the server accepts and plays them in order", async () => {
    const fetchMock = vi.fn((_url: string, _init: RequestInit) => Promise.resolve(new Response(new Blob(["wav"]), { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    const sentence = "This sentence is part of a long note. ";
    const done = speakText(sentence.repeat(30));
    for (let index = 0; index < 2; index += 1) {
      await vi.waitFor(() => expect(FakeAudio.played).toHaveLength(index + 1));
      FakeAudio.played[index].onended?.();
    }
    await done;
    const sent = fetchMock.mock.calls.map((call) => JSON.parse(call[1].body as string).text as string);
    expect(sent).toHaveLength(2);
    expect(sent.every((text) => text.length <= 600)).toBe(true);
    expect(sent.join(" ")).toBe(sentence.repeat(30).trim());
  });
});
