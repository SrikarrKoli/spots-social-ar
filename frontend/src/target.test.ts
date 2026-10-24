import { describe, expect, it } from "vitest";
import { lockTarget } from "./target";
import type { ObjectSummary, Post } from "./types";

const concert: ObjectSummary = { id: "concert", marker_id: 7, title: "Concert", description: null };
const book: ObjectSummary = { id: "book", marker_id: 23, title: "Book", description: null };
const parent: Post = {
  id: 42,
  object_id: "concert",
  author: { id: "maya", display_name: "Maya", initials: "M", color: "#000" },
  body: "Friday?",
  created_at: "2026-10-24T00:00:00Z",
  parent_post_id: null,
  replies: [],
};

describe("composer target locking", () => {
  it("keeps an immutable object and parent snapshot", () => {
    const target = lockTarget(concert, parent);
    concert.id = book.id;
    parent.id = 99;
    expect(target.object.id).toBe("concert");
    expect(target.parentPost?.id).toBe(42);
  });
});
