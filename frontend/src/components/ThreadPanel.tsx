import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { lockTarget } from "../target";
import type { LockedTarget, ObjectSummary, Post, Profile, ThreadResponse } from "../types";
import { usePolling } from "../hooks/usePolling";
import { Avatar } from "./Avatar";
import { Composer } from "./Composer";

interface Props {
  object: ObjectSummary | null;
  availableObjects: ObjectSummary[];
  onSelectObject: (object: ObjectSummary) => void;
  onObjectEnrolled?: (object: ObjectSummary) => void;
  profile: Profile | null;
  transcriptionConfigured: boolean;
}

function timeLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function Message({ post, onReply }: { post: Post; onReply: (post: Post) => void }) {
  return (
    <article className="message">
      <Avatar profile={post.author} />
      <div className="message__content">
        <div className="message__meta">
          <strong>{post.author.display_name}</strong>
          <time dateTime={post.created_at}>{timeLabel(post.created_at)}</time>
        </div>
        <p>{post.body}</p>
        <button className="text-button" onClick={() => onReply(post)}>Reply</button>
        {post.replies.length > 0 && (
          <div className="replies">
            {post.replies.map((reply) => (
              <div className="reply" key={reply.id}>
                <Avatar profile={reply.author} small />
                <div>
                  <div className="message__meta">
                    <strong>{reply.author.display_name}</strong>
                    <time dateTime={reply.created_at}>{timeLabel(reply.created_at)}</time>
                  </div>
                  <p>{reply.body}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function EnrollObject({ onEnrolled }: { onEnrolled: (object: ObjectSummary) => void }) {
  const [title, setTitle] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [state, setState] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!title.trim() || !image) return;
    setBusy(true);
    setState(null);
    try {
      const created = await api.enrollObject(title.trim(), "", image);
      onEnrolled(created);
      setState(`Enrolled “${created.title}” — point the camera at it.`);
      setTitle("");
      setImage(null);
    } catch (error) {
      setState(error instanceof Error ? error.message : "Enrolment failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="thread-picker">
      <span>ENROL A NEW OBJECT (NO MARKER)</span>
      <input
        aria-label="Object name"
        placeholder="e.g. Blue mug"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <input
        aria-label="Photo of the object"
        type="file"
        accept="image/*"
        onChange={(event) => setImage(event.target.files?.[0] ?? null)}
      />
      <button disabled={busy || !title.trim() || !image} onClick={() => void submit()}>
        {busy ? "Enrolling…" : "Enrol from this photo"}
      </button>
      {state && <small>{state}</small>}
    </div>
  );
}

export function ThreadPanel({ object, availableObjects, onSelectObject, onObjectEnrolled, profile, transcriptionConfigured }: Props) {
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composerTarget, setComposerTarget] = useState<LockedTarget | null>(null);

  const loadThread = useCallback(
    async (signal?: AbortSignal) => {
      if (!object) return;
      try {
        const result = await api.thread(object.id, signal);
        setThread(result);
        setError(null);
      } catch (loadError) {
        if (!(loadError instanceof DOMException && loadError.name === "AbortError")) {
          setError(loadError instanceof Error ? loadError.message : "Could not load this thread.");
        }
      } finally {
        setLoading(false);
      }
    },
    [object],
  );

  useEffect(() => {
    setThread(null);
    setComposerTarget(null);
    if (object) {
      setLoading(true);
      const controller = new AbortController();
      void loadThread(controller.signal);
      return () => controller.abort();
    }
  }, [object, loadThread]);

  usePolling(async (signal) => loadThread(signal), 1500, Boolean(object));

  if (!object) {
    return (
      <aside className="thread-panel thread-panel--empty">
        <div className="empty-thread-mark">⌖</div>
        <p className="eyebrow">OBJECT THREAD</p>
        <h2>No conversation open</h2>
        <p>Look at an enrolled object, then open its nearby conversation.</p>
        <div className="thread-picker">
          <span>OR BROWSE A DEMO THREAD</span>
          {availableObjects.map((availableObject) => (
            <button key={availableObject.id} onClick={() => onSelectObject(availableObject)}>
              {availableObject.title} <small>Enrolled object</small>
            </button>
          ))}
        </div>
        <EnrollObject
          onEnrolled={(created) => {
            onObjectEnrolled?.(created);
            onSelectObject(created);
          }}
        />
      </aside>
    );
  }

  const replyCount = thread?.posts.reduce((count, post) => count + post.replies.length, 0) ?? 0;

  return (
    <aside className="thread-panel">
      <header className="thread-header">
        <div className="thread-header__marker">⌖</div>
        <div>
          <p className="eyebrow">THREAD OPEN · OBJECT LOCKED</p>
          <h2>{object.title}</h2>
          <p>{object.description}</p>
        </div>
      </header>

      <div className="thread-summary">
        <span>{thread?.posts.length ?? 0} posts</span>
        <span>{replyCount} replies</span>
        <span>Attached to this object, not its category</span>
      </div>

      <div className="thread-body" aria-live="polite">
        {loading && !thread && <div className="panel-state"><span className="spinner" /> Loading conversation…</div>}
        {error && <p className="panel-error">{error}</p>}
        {thread?.posts.map((post) => (
          <Message
            key={post.id}
            post={post}
            onReply={(replyPost) => setComposerTarget(lockTarget(object, replyPost))}
          />
        ))}
        {thread && thread.posts.length === 0 && (
          <div className="panel-state">No posts yet. Leave the first one.</div>
        )}
      </div>

      {composerTarget && profile ? (
        <Composer
          key={`${composerTarget.object.id}:${composerTarget.parentPost?.id ?? "new"}`}
          target={composerTarget}
          profile={profile}
          transcriptionConfigured={transcriptionConfigured}
          onCancel={() => setComposerTarget(null)}
          onSaved={() => {
            setComposerTarget(null);
            void loadThread();
          }}
        />
      ) : (
        <div className="thread-footer">
          <button
            className="button button--primary button--wide"
            disabled={!profile}
            onClick={() => setComposerTarget(lockTarget(object))}
          >
            <span aria-hidden="true">＋</span> Leave a post
          </button>
          <span>Thread stays open if the object leaves view.</span>
        </div>
      )}
    </aside>
  );
}
