// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRecall } from "./MemoryRecall";
import { api } from "../api";
vi.mock("../api", () => ({ api: { thread: vi.fn() } }));
const object = { id: "tv", identity_key: "tv", title: "TV", identity_kind: "instance", description: null };
const post = { id: 3, object_id: "tv", author: { id: "guest", display_name: "Guest", initials: "G", color: "gray" }, body: "Great picture quality.", created_at: "2026-10-25T00:00:00Z", parent_post_id: null, replies: [] };
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it("hides when the object leaves and recalls the persisted note when it returns", async () => {
  vi.mocked(api.thread).mockResolvedValue({ object, posts: [post], updated_at: null });
  const view = render(<MemoryRecall object={object} revision={0} />);
  await screen.findByText("Great picture quality.");
  view.rerender(<MemoryRecall object={null} revision={0} />);
  expect(screen.queryByText("Great picture quality.")).toBeNull();
  view.rerender(<MemoryRecall object={object} revision={0} />);
  await screen.findByText("Great picture quality.");
  await waitFor(() => expect(api.thread).toHaveBeenCalledTimes(2));
});
