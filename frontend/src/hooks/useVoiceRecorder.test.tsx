// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useVoiceRecorder } from "./useVoiceRecorder";

const stopTrack = vi.fn();
const stream = { getTracks: () => [{ stop: stopTrack }] };
const getUserMedia = vi.fn();
class Recorder {
  static isTypeSupported() { return true; }
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable?: (event: { data: Blob }) => void;
  onstop?: () => void;
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    queueMicrotask(() => { this.ondataavailable?.({ data: new Blob(["audio"]) }); this.onstop?.(); });
  }
}
beforeEach(() => {
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn() });
  vi.stubGlobal("MediaRecorder", Recorder);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
    getUserMedia, enumerateDevices: vi.fn().mockResolvedValue([]), addEventListener: vi.fn(), removeEventListener: vi.fn(),
  } });
  getUserMedia.mockReset().mockResolvedValue(stream);
  stopTrack.mockClear();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("allows only one recording owner across composer and assistant", async () => {
  const first = renderHook(() => useVoiceRecorder());
  const second = renderHook(() => useVoiceRecorder());
  await act(async () => { await first.result.current.start(); });
  await expect(second.result.current.start()).rejects.toThrow("Finish the current");
  await act(async () => { await first.result.current.stop(); await second.result.current.start(); });
  expect(second.result.current.recording).toBe(true);
  await act(async () => { await second.result.current.stop(); });
  expect(getUserMedia).toHaveBeenCalledTimes(2);
  expect(getUserMedia.mock.calls[0][0].audio.echoCancellation).toBe(true);
});

it("releases a permission result arriving after the recorder unmounts", async () => {
  let permit!: (value: typeof stream) => void;
  getUserMedia.mockImplementation(() => new Promise((resolve) => { permit = resolve; }));
  const hook = renderHook(() => useVoiceRecorder());
  let pending!: Promise<void>;
  act(() => { pending = hook.result.current.start(); });
  hook.unmount();
  await act(async () => { permit(stream); await pending; });
  expect(stopTrack).toHaveBeenCalledTimes(1);
});

it("deduplicates simultaneous stop calls and returns the recorded audio", async () => {
  const hook = renderHook(() => useVoiceRecorder());
  await act(async () => { await hook.result.current.start(); });
  await act(async () => {
    const results = await Promise.all([hook.result.current.stop(), hook.result.current.stop()]);
    expect(results[0].size).toBeGreaterThan(0);
    expect(results[0]).toBe(results[1]);
  });
  expect(stopTrack).toHaveBeenCalledTimes(1);
});

it("reports a pending permission prompt and releases a stream granted after timeout", async () => {
  vi.useFakeTimers();
  let permit!: (value: typeof stream) => void;
  getUserMedia.mockImplementation(() => new Promise(resolve => { permit = resolve; }));
  const hook = renderHook(() => useVoiceRecorder());
  let pending!: Promise<void>;
  act(() => { pending = hook.result.current.start(); });
  const rejected = expect(pending).rejects.toThrow("Microphone access is waiting");
  await act(async () => { await vi.advanceTimersByTimeAsync(12000); });
  await rejected;
  await act(async () => { permit(stream); await Promise.resolve(); });
  expect(stopTrack).toHaveBeenCalledTimes(1);
  expect(hook.result.current.recording).toBe(false);
  vi.useRealTimers();
});
