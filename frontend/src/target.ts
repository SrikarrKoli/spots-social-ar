import type { LockedTarget, ObjectSummary, Post } from "./types";

export function lockTarget(
  object: ObjectSummary,
  parentPost: Post | null = null,
): LockedTarget {
  return {
    object: { ...object },
    parentPost: parentPost
      ? { ...parentPost, author: { ...parentPost.author }, replies: [] }
      : null,
  };
}
