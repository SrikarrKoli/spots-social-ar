import { useEffect, useState } from "react";
import { api } from "../api";
import { usePolling } from "../hooks/usePolling";
import type { ObjectSummary, ThreadResponse } from "../types";

export function MemoryRecall({ object, revision }: { object: ObjectSummary | null; revision: number }) {
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  useEffect(() => { setThread(null); }, [object?.id, revision]);
  usePolling(async (signal) => {
    if (!object) return;
    const result = await api.thread(object.id, signal);
    if (!signal.aborted) setThread(result);
  }, 1500, Boolean(object));
  if (!object || thread?.object.id !== object.id || !thread.posts.length) return null;
  return <section className="memory-recall" aria-label="Memories for the object in view" aria-live="polite">
    <strong>Remembered · {object.title}</strong>
    {thread.posts.slice(-3).map((post) => {
      const reply = post.replies.at(-1);
      return <div key={post.id} className="memory-recall__note">
        <p>{post.body}</p>
        {reply && <p className="memory-recall__reply">↳ {reply.author.display_name.split(" ")[0]}: {reply.body}{post.replies.length > 1 && <small> · {post.replies.length} replies</small>}</p>}
      </div>;
    })}
    <small>{thread.posts.length} saved note{thread.posts.length === 1 ? "" : "s"}. All remain available in Saved objects &amp; memories.</small>
  </section>;
}
