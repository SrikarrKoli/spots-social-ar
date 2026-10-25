import type { Post, Profile, ThreadResponse } from "./types";

export function flattenPosts(posts: Post[]) {
  return posts
    .flatMap((post) => [post, ...post.replies])
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function noteCount(thread: ThreadResponse | undefined) {
  return thread?.posts.reduce((count, post) => count + 1 + post.replies.length, 0) ?? 0;
}

export function participants(posts: Post[]) {
  const people = new Map<string, Profile>();
  for (const post of flattenPosts(posts)) people.set(post.author.id, post.author);
  return [...people.values()];
}

export function latestPost(posts: Post[]) {
  return flattenPosts(posts).at(-1) ?? null;
}
