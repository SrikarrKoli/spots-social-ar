import { useEffect, useState } from "react";
import { countWord, relativeTime } from "../format";
import { anchorFor, DEMO_IMAGE, PLACE_LOCATION, PLACE_NAME } from "../scene";
import { lockTarget } from "../target";
import { latestPost, noteCount, participants } from "../threadUtils";
import type { LockedTarget, ObjectSummary, Post, Profile, ThreadResponse } from "../types";
import { Avatar } from "./Avatar";
import { Composer } from "./Composer";
import { Icon } from "./Icons";

interface Props {
  object: ObjectSummary | null;
  availableObjects: ObjectSummary[];
  threads: Record<string, ThreadResponse>;
  threadsError: string | null;
  onSelectObject: (object: ObjectSummary) => void;
  onPosted: () => void;
  profile: Profile | null;
  transcriptionConfigured: boolean;
  listening: boolean;
}

type Tab = "object" | "place";

export function ObjectThumb({ object, className = "" }: { object: ObjectSummary; className?: string }) {
  const anchor = anchorFor(object.marker_id);
  return (
    <span
      className={`object-thumb ${className}`}
      aria-hidden="true"
      style={{ backgroundImage: `url(${DEMO_IMAGE})`, backgroundPosition: `${anchor.x * 100}% ${anchor.y * 100}%` }}
    />
  );
}

function NoteItem({
  post,
  viewer,
  objectLabel,
  liked,
  onToggleLike,
  onReply,
  onOpenObject,
}: {
  post: Post;
  viewer: Profile | null;
  objectLabel?: string;
  liked: (post: Post) => boolean;
  onToggleLike: (post: Post) => void;
  onReply: (post: Post) => void;
  onOpenObject?: () => void;
}) {
  const renderPost = (item: Post, isReply: boolean) => (
    <article className={`note ${isReply ? "note--reply" : ""}`} key={item.id}>
      <Avatar profile={item.author} size={isReply ? "sm" : "md"} />
      <div className="note__content">
        <div className="note__meta">
          <strong>{item.author.id === viewer?.id ? "You" : item.author.display_name}</strong>
          <time dateTime={item.created_at}>{relativeTime(item.created_at)}</time>
        </div>
        {!isReply && objectLabel && (
          <button className="note__object" onClick={onOpenObject}>{objectLabel}</button>
        )}
        <p>{item.body}</p>
        <div className="note__actions">
          <button className={`like-button ${liked(item) ? "is-liked" : ""}`} onClick={() => onToggleLike(item)} aria-pressed={liked(item)} aria-label="Like">
            <Icon name="heart" filled={liked(item)} />
            {liked(item) && <span>1</span>}
          </button>
          <button className="text-button" onClick={() => onReply(post)}>Reply</button>
        </div>
      </div>
      <button className="icon-button note__more" aria-label="More options"><Icon name="more" /></button>
    </article>
  );

  return (
    <div className="note-group">
      {renderPost(post, false)}
      {post.replies.map((reply) => renderPost(reply, true))}
    </div>
  );
}

function AssistantCard({
  object,
  thread,
  viewer,
  listening,
  disabled,
  onTakeNote,
  onReplyByVoice,
}: {
  object: ObjectSummary;
  thread: ThreadResponse | undefined;
  viewer: Profile | null;
  listening: boolean;
  disabled: boolean;
  onTakeNote: () => void;
  onReplyByVoice: () => void;
}) {
  const [speaking, setSpeaking] = useState(false);
  const people = participants(thread?.posts ?? []);
  const others = people.filter((person) => person.id !== viewer?.id);
  const latest = latestPost(thread?.posts ?? []);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  useEffect(() => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, [object.id]);

  const readAloud = () => {
    if (!window.speechSynthesis || !latest) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(`${latest.author.display_name} says: ${latest.body}`);
    utterance.onend = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };

  const summary = people.length === 0
    ? `You're looking at the ${object.title}. Nobody has left a note here yet — want to be the first?`
    : others.length === 0
      ? `You're looking at the ${object.title}. Only you have left a note here so far. Want me to read it back or help you add another?`
      : `You're looking at the ${object.title}. ${countWord(others.length)} ${others.length === 1 ? "person" : "people"} left notes here. Want me to read the latest one, help you leave a note, or reply to someone?`;

  return (
    <section className="assistant-card" aria-label="Spots AI">
      <header>
        <span className="assistant-orb" aria-hidden="true" />
        <strong>Spots AI</strong>
        <span className={`assistant-status ${listening ? "is-listening" : ""}`}>
          <span className="waveform" aria-hidden="true"><i /><i /><i /><i /><i /></span>
          {speaking ? "Speaking…" : listening ? "Listening…" : "Ready"}
        </span>
      </header>
      <p>{summary}</p>
      <div className="assistant-actions">
        <button className="soft-button" onClick={onTakeNote} disabled={disabled}><Icon name="mic" /> Take note</button>
        <button className="soft-button" onClick={onReplyByVoice} disabled={disabled || !latest}><Icon name="notes" /> Reply by voice</button>
        <button className={`soft-button ${speaking ? "is-active" : ""}`} onClick={readAloud} disabled={!latest}><Icon name="speaker" /> {speaking ? "Stop" : "Read aloud"}</button>
      </div>
    </section>
  );
}

export function ThreadPanel({
  object,
  availableObjects,
  threads,
  threadsError,
  onSelectObject,
  onPosted,
  profile,
  transcriptionConfigured,
  listening,
}: Props) {
  const [tab, setTab] = useState<Tab>("object");
  const [composerTarget, setComposerTarget] = useState<LockedTarget | null>(null);
  const [recordOnOpen, setRecordOnOpen] = useState(false);
  const [likedIds, setLikedIds] = useState<Set<number>>(new Set());

  useEffect(() => setComposerTarget(null), [object?.id]);

  if (!object) {
    return (
      <aside className="lens-side">
        <section className="note-card note-card--empty">
          <span className="empty-mark"><Icon name="glasses" /></span>
          <h2>Nothing in view</h2>
          <p>Look at a menu item, or pick one below.</p>
          <div className="thread-picker">
            {availableObjects.map((availableObject) => (
              <button key={availableObject.id} onClick={() => onSelectObject(availableObject)}>
                {availableObject.title} <Icon name="chevronRight" />
              </button>
            ))}
          </div>
        </section>
      </aside>
    );
  }

  const thread = threads[object.id];
  const placePosts = availableObjects
    .flatMap((item) => (threads[item.id]?.posts ?? []).map((post) => ({ post, object: item })))
    .sort((a, b) => b.post.created_at.localeCompare(a.post.created_at));
  const placeCount = availableObjects.reduce((count, item) => count + noteCount(threads[item.id]), 0);

  const openComposer = (target: LockedTarget, record = false) => {
    setRecordOnOpen(record);
    setComposerTarget(target);
  };
  const liked = (post: Post) => likedIds.has(post.id);
  const toggleLike = (post: Post) =>
    setLikedIds((current) => {
      const next = new Set(current);
      if (!next.delete(post.id)) next.add(post.id);
      return next;
    });

  return (
    <aside className="lens-side">
      <section className="note-card">
        <header className="object-header">
          <ObjectThumb object={object} />
          <div>
            <h2>{object.title}</h2>
            <p><Icon name="pin" /> {PLACE_NAME} · {PLACE_LOCATION}</p>
          </div>
          <button className="icon-button" aria-label="More options"><Icon name="more" /></button>
        </header>

        <div className="note-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "object"} onClick={() => setTab("object")}>
            Object Notes ({noteCount(thread)})
          </button>
          <button role="tab" aria-selected={tab === "place"} onClick={() => setTab("place")}>
            Place Notes ({placeCount})
          </button>
        </div>

        <div className="note-list" aria-live="polite">
          {!thread && !threadsError && <div className="panel-state"><span className="spinner" /> Loading notes…</div>}
          {threadsError && <p className="panel-error">{threadsError}</p>}
          {tab === "object" && thread?.posts.map((post) => (
            <NoteItem
              key={post.id}
              post={post}
              viewer={profile}
              liked={liked}
              onToggleLike={toggleLike}
              onReply={(replyPost) => openComposer(lockTarget(object, replyPost))}
            />
          ))}
          {tab === "place" && placePosts.map(({ post, object: postObject }) => (
            <NoteItem
              key={post.id}
              post={post}
              viewer={profile}
              objectLabel={postObject.id === object.id ? undefined : postObject.title}
              liked={liked}
              onToggleLike={toggleLike}
              onReply={(replyPost) => openComposer(lockTarget(postObject, replyPost))}
              onOpenObject={() => {
                onSelectObject(postObject);
                setTab("object");
              }}
            />
          ))}
          {thread && tab === "object" && thread.posts.length === 0 && (
            <div className="panel-state">No notes yet. Be the first to leave one.</div>
          )}
        </div>

        {composerTarget && profile ? (
          <Composer
            key={`${composerTarget.object.id}:${composerTarget.parentPost?.id ?? "new"}:${recordOnOpen}`}
            target={composerTarget}
            profile={profile}
            transcriptionConfigured={transcriptionConfigured}
            startRecording={recordOnOpen}
            onCancel={() => setComposerTarget(null)}
            onSaved={() => {
              setComposerTarget(null);
              onPosted();
            }}
          />
        ) : (
          <button className="start-conversation" disabled={!profile} onClick={() => openComposer(lockTarget(object))}>
            <Icon name="notes" /> Start a conversation
          </button>
        )}
      </section>

      <AssistantCard
        object={object}
        thread={thread}
        viewer={profile}
        listening={listening}
        disabled={!profile}
        onTakeNote={() => openComposer(lockTarget(object), true)}
        onReplyByVoice={() => {
          const latest = thread?.posts.at(-1);
          if (latest) openComposer(lockTarget(object, latest), true);
        }}
      />
    </aside>
  );
}
