import { describe, expect, it } from "vitest";
import type { Post, Profile } from "../types";
import { replyLabel } from "./MessagesView";

const person = (id: string, display_name: string): Profile => ({ id, display_name, initials: display_name[0], color: "#000" });
const vishal = person("maya", "Vishal Rajkumar");
const aneesh = person("theo", "Aneesh Dhulipalla");
const lina = person("lina", "Lina Ortiz");
const post = (id: number, author: Profile, parent: number | null = null): Post =>
  ({ id, object_id: "chair", author, body: "", created_at: "2026-10-25T12:00:00Z", parent_post_id: parent, replies: [] });

describe("reply labels read from the viewer's side", () => {
  const note = post(1, vishal);
  it.each([
    [post(2, aneesh, 1), vishal, "Aneesh replied to you"],
    [post(2, vishal, 1), vishal, "You added to your note"],
    [post(2, aneesh, 1), aneesh, "You replied to Vishal"],
    [post(2, aneesh, 1), lina, "Aneesh replied to Vishal"],
    [post(2, vishal, 1), lina, "Vishal added to their note"],
  ])("%#", (reply, viewer, label) => {
    expect(replyLabel(reply, note, viewer)).toBe(label);
  });

  it("names who the author answers when they reply in their own thread", () => {
    const aneeshReply = { ...post(2, aneesh, 1), created_at: "2026-10-25T12:01:00Z" };
    const vishalAnswer = { ...post(3, vishal, 1), created_at: "2026-10-25T12:02:00Z" };
    const thread = { ...note, replies: [aneeshReply, vishalAnswer] };
    expect(replyLabel(vishalAnswer, thread, vishal)).toBe("You replied to Aneesh");
    expect(replyLabel(vishalAnswer, thread, aneesh)).toBe("Vishal replied to you");
  });
});
