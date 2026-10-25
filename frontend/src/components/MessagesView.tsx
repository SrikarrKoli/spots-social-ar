import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { clockTime, dayAndTime, relativeTime, username } from "../format";
import { useTranscribedRecorder } from "../hooks/useTranscribedRecorder";
import {
  DEMO_CONVERSATIONS,
  DEMO_FRIEND_MESSAGES,
  DEMO_PEOPLE,
  DEMO_SPOTS_AFTER,
  DEMO_SPOTS_BEFORE,
  DEMO_STORY_NOTES,
  type DemoConversation,
  type DemoMessage,
  type SpotsUpdate,
} from "../instagramDemo";
import { anchorFor, DEMO_IMAGE, DEMO_IMAGE_SIZE, FEATURED_MARKER, PLACE_LOCATION, PLACE_NAME } from "../scene";
import { flattenPosts, latestPost, noteCount, participants } from "../threadUtils";
import type { ObjectSummary, Post, Profile, ThreadResponse } from "../types";
import { Avatar, SpotsAvatar } from "./Avatar";
import { Icon } from "./Icons";
import { MUSE, MuseAvatar, MuseChat, musePreview, type MuseHighlight } from "./MuseChat";

interface Props {
  profile: Profile | null;
  profiles: Profile[];
  onSwitchProfile: (profileId: string) => void;
  objects: ObjectSummary[];
  threads: Record<string, ThreadResponse>;
  selectedObject: ObjectSummary | null;
  transcriptionConfigured: boolean;
  onOpenLens: (object: ObjectSummary) => void;
  onPosted: () => void;
}

const SPOTS = "spots";

interface ChatEntry {
  post: Post;
  object: ObjectSummary;
  // The top-level post a reply from this chat should attach to.
  root: Post;
}

const firstName = (person: Profile) => person.display_name.split(" ")[0];

// Who a reply answers: the note's author, or, when the author answers in their own
// thread, the last other person who replied there before them.
function replyTarget(reply: Post, root: Post): Profile | null {
  if (root.author.id !== reply.author.id) return root.author;
  return root.replies
    .filter((item) => item.created_at < reply.created_at && item.author.id !== reply.author.id)
    .at(-1)?.author ?? null;
}

// "Vishal replied to you", "You replied to Aneesh", told from the viewer's side.
export function replyLabel(reply: Post, root: Post, viewer: Profile | null) {
  const mine = reply.author.id === viewer?.id;
  const replier = mine ? "You" : firstName(reply.author);
  const target = replyTarget(reply, root);
  if (!target) return `${replier} added to ${mine ? "your" : "their"} note`;
  return `${replier} replied to ${target.id === viewer?.id ? "you" : firstName(target)}`;
}

function ChatLog({
  entries,
  viewer,
  showObject,
  newIds,
  after,
}: {
  entries: ChatEntry[];
  viewer: Profile | null;
  showObject: boolean;
  // Messages that just arrived, briefly highlighted as they land.
  newIds: Set<number>;
  after?: string;
}) {
  return (
    <>
      {entries.map(({ post, object, root }, index) => {
        const previousEntry = entries[index - 1];
        const previous = previousEntry?.post;
        const mine = post.author.id === viewer?.id;
        const previousTime = previous?.created_at ?? after;
        const showTime = !previousTime || new Date(post.created_at).getTime() - new Date(previousTime).getTime() > 5 * 60_000;
        const isReply = post.parent_post_id !== null;
        // A run of replies to the same note quotes it once, like a DM reply thread.
        const continuesThread = isReply && previous?.parent_post_id !== null && previousEntry?.root.id === root.id && previous?.author.id === post.author.id && !showTime;
        const showName = !mine && !isReply && (showTime || previous?.author.id !== post.author.id);
        const nextSameAuthor = entries[index + 1]?.post.author.id === post.author.id;
        return (
          <div key={post.id}>
            {showTime && <div className="chat-time">{dayAndTime(post.created_at)}</div>}
            <div className={`chat-row ${mine ? "chat-row--mine" : ""} ${newIds.has(post.id) ? "is-new" : ""}`}>
              {!mine && (nextSameAuthor ? <span className="chat-avatar-spacer" /> : <Avatar profile={post.author} size="sm" />)}
              <div className="chat-bubble-wrap">
                {showName && <span className="chat-sender">{post.author.display_name}</span>}
                {isReply && !continuesThread && (
                  <div className="chat-reply">
                    <span className="chat-reply__label">
                      <Icon name="reply" />
                      {replyLabel(post, root, viewer)}
                      {showObject && <> · {object.title}</>}
                    </span>
                    <p className="chat-reply__quote">{root.body}</p>
                  </div>
                )}
                <p className="chat-bubble" title={clockTime(post.created_at)}>{post.body}</p>
                {showObject && post.parent_post_id === null && <span className="chat-context">Note on {object.title}</span>}
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}

const DEMO_PREFIX = "demo:";

function minutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function ConversationAvatar({ conversation, size }: { conversation: DemoConversation; size: "md" | "lg" }) {
  if (conversation.people.length === 1) return <Avatar profile={conversation.people[0]} size={size} />;
  return (
    <span className={`avatar-stack avatar-stack--${size}`}>
      <Avatar profile={conversation.people[0]} size="sm" />
      <Avatar profile={conversation.people[1]} size="sm" />
    </span>
  );
}

function DemoLog({ conversation, messages }: { conversation: DemoConversation; messages: DemoMessage[] }) {
  const byId = new Map(conversation.people.map((item) => [item.id, item]));
  const group = conversation.people.length > 1;
  return (
    <>
      {messages.map((message, index) => {
        const previous = messages[index - 1];
        const mine = message.from === "me";
        const author = byId.get(message.from);
        const showTime = !previous || previous.minutesAgo - message.minutesAgo > 5;
        const showName = group && !mine && (showTime || previous?.from !== message.from);
        const nextSameAuthor = messages[index + 1]?.from === message.from;
        const created = minutesAgo(message.minutesAgo);
        return (
          <div key={index}>
            {showTime && <div className="chat-time">{dayAndTime(created)}</div>}
            <div className={`chat-row ${mine ? "chat-row--mine" : ""}`}>
              {!mine && author && (nextSameAuthor ? <span className="chat-avatar-spacer" /> : <Avatar profile={author} size="sm" />)}
              <div className="chat-bubble-wrap">
                {showName && author && <span className="chat-sender">{author.display_name}</span>}
                {message.sharedNote && (
                  <span className="shared-note">
                    <Icon name="glasses" />
                    <span><strong>Spots note</strong><small>{message.sharedNote} · {PLACE_NAME}</small></span>
                  </span>
                )}
                <p className="chat-bubble" title={clockTime(created)}>{message.body}</p>
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}

// A friend who hasn't traded notes yet gets a short demo chat instead of an empty thread.
function friendChat(person: Profile): DemoConversation {
  return {
    id: person.id,
    title: person.display_name,
    people: [person],
    subtitle: "Active today",
    messages: DEMO_FRIEND_MESSAGES.map((message) => (message.from === "them" ? { ...message, from: person.id } : message)),
  };
}

function SpotsUpdates({ updates, after }: { updates: SpotsUpdate[]; after?: string }) {
  return (
    <>
      {updates.map((update, index) => {
        const created = minutesAgo(update.minutesAgo);
        const previous = updates[index - 1];
        const previousTime = previous ? minutesAgo(previous.minutesAgo) : after;
        const showTime = !previousTime || new Date(created).getTime() - new Date(previousTime).getTime() > 5 * 60_000;
        return (
          <div key={index}>
            {showTime && <div className="chat-time">{dayAndTime(created)}</div>}
            <div className="chat-row">
              {index === updates.length - 1 ? <SpotsAvatar size="sm" /> : <span className="chat-avatar-spacer" />}
              <div className="chat-bubble-wrap">
                <div className="spots-update" title={clockTime(created)}>
                  {update.person && <Avatar profile={update.person} size="xs" />}
                  <span>
                    {update.body}
                    {update.quote && <q>{update.quote}</q>}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}

// A phone-sized crop of the same photographed scene and calibrated anchor used
// by Glasses Mode. Its marker and note treatment mirror the current AR view.
const CROP = { width: 360, height: 450, zoom: 2.6 };

function SceneCrop({ markerId, objectId, title, note }: { markerId?: number; objectId: string; title: string; note: Post | null }) {
  const anchor = anchorFor(markerId);
  const width = CROP.width * CROP.zoom;
  const height = width * (DEMO_IMAGE_SIZE.height / DEMO_IMAGE_SIZE.width);
  const clamp = (value: number, min: number) => Math.min(0, Math.max(min, value));
  const x = clamp(CROP.width / 2 - anchor.x * width, CROP.width - width);
  const y = clamp(CROP.height / 2 - anchor.y * height, CROP.height - height);
  return (
    <span
      className="scene-crop"
      style={{ backgroundImage: `url(${markerId ? DEMO_IMAGE : `/api/objects/${encodeURIComponent(objectId)}/reference`})`, backgroundSize: markerId ? `${width}px ${height}px` : "cover", backgroundPosition: markerId ? `${x}px ${y}px` : "center" }}
    >
      <span className="scene-crop__marker" style={{ left: x + anchor.x * width, top: y + anchor.y * height }} aria-hidden="true">
        <Icon name="notes" />
      </span>
      <span className="scene-crop__note">
        <span className="scene-crop__note-copy">
          <b>{title}</b>
          {note && <strong>{note.author.display_name}</strong>}
          {note && <span>{note.body}</span>}
          {note && <small>{relativeTime(note.created_at)} ago</small>}
        </span>
      </span>
    </span>
  );
}

export function MessagesView({
  profile,
  profiles,
  onSwitchProfile,
  objects,
  threads,
  selectedObject,
  transcriptionConfigured,
  onOpenLens,
  onPosted,
}: Props) {
  const [activeId, setActiveId] = useState(SPOTS);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [fromVoice, setFromVoice] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [seenSpots, setSeenSpots] = useState(false);
  const [seenDemo, setSeenDemo] = useState<Set<string>>(new Set());
  const [demoSent, setDemoSent] = useState<Record<string, DemoMessage[]>>({});
  const recorder = useTranscribedRecorder();
  const inputRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  // Posts already on screen; anything new that arrives is announced and highlighted.
  const knownPosts = useRef<Set<number> | null>(null);
  const [newIds, setNewIds] = useState<Set<number>>(new Set());
  const [banner, setBanner] = useState<ChatEntry | null>(null);
  const [unreadFrom, setUnreadFrom] = useState<Set<string>>(new Set());

  const allPosts = useMemo(
    () => objects.flatMap((object) => (threads[object.id]?.posts ?? []).map((post) => ({ post, object }))),
    [objects, threads],
  );

  // Story bubbles show a person's latest note, not their replies.
  const latestBy = (personId: string) =>
    latestPost(allPosts.map(({ post }) => post).filter((post) => post.author.id === personId));

  const people = useMemo(() => {
    const known = new Map(profiles.map((person) => [person.id, person]));
    for (const { post } of allPosts) for (const item of flattenPosts([post])) known.set(item.author.id, item.author);
    known.delete(profile?.id ?? "");
    return [...known.values()];
  }, [allPosts, profiles, profile]);

  const entriesFor = (personId: string): ChatEntry[] => {
    const entries: ChatEntry[] = [];
    for (const { post, object } of allPosts) {
      const thread = [post, ...post.replies];
      if (!thread.some((item) => item.author.id === personId)) continue;
      for (const item of thread) {
        if (item.author.id === personId || item.author.id === profile?.id) entries.push({ post: item, object, root: post });
      }
    }
    return entries.sort((a, b) => a.post.created_at.localeCompare(b.post.created_at));
  };

  // Spots surfaces the note pinned in the demo scene.
  const nearbyObject = selectedObject ?? objects.find((object) => object.marker_id === FEATURED_MARKER) ?? null;
  const nearbyThread = nearbyObject ? threads[nearbyObject.id] : undefined;
  const nearbyPeople = participants(nearbyThread?.posts ?? []).filter((person) => person.id !== profile?.id);
  const nearbyLatest = latestPost(nearbyThread?.posts ?? []);
  // Keep the recommendation and its replies together as one visible thread. Prefer a note
  // from someone else so the signed-in demo viewer sees the exchange from their perspective.
  const cardNote = nearbyThread
    ? [...nearbyThread.posts].reverse().find((post) => post.author.id !== profile?.id) ?? nearbyThread.posts.at(-1) ?? null
    : null;
  const spotsEntries: ChatEntry[] = nearbyObject && cardNote
    ? flattenPosts(nearbyThread?.posts ?? []).filter(post => post.id !== cardNote.id).map((post) => ({
        post,
        object: nearbyObject,
        root: nearbyThread?.posts.find(root => root.id === post.id || root.replies.some(reply => reply.id === post.id)) ?? cardNote,
      }))
    : [];
  const dish = nearbyObject?.title ?? "menu";
  const nearbyRoot = nearbyLatest?.parent_post_id != null ? nearbyThread?.posts.find((post) => post.id === nearbyLatest.parent_post_id) : undefined;
  const spotsPreview = nearbyLatest && nearbyRoot
    ? `${replyLabel(nearbyLatest, nearbyRoot, profile)}: “${nearbyLatest.body}”`
    : nearbyPeople.length === 0
    ? "Sent a post"
    : nearbyPeople.length === 1
      ? `${nearbyPeople[0].display_name.split(" ")[0]} left a note on the ${dish}`
      : `${nearbyPeople.length} people left notes on the ${dish}`;

  const museHighlight: MuseHighlight | null = allPosts
    .filter(({ post }) => post.author.id !== profile?.id)
    .sort((a, b) => a.post.created_at.localeCompare(b.post.created_at))
    .map(({ post, object }) => ({ note: post, object }))
    .at(-1) ?? null;
  const [seenMuse, setSeenMuse] = useState(false);

  const activePerson = people.find((person) => person.id === activeId) ?? null;
  const activeDemo = DEMO_CONVERSATIONS.find((conversation) => DEMO_PREFIX + conversation.id === activeId) ?? null;
  const demoMessages = (conversation: DemoConversation) => [...conversation.messages, ...(demoSent[conversation.id] ?? [])];
  const entries = activeId === SPOTS ? spotsEntries : activeDemo || activeId === MUSE ? [] : entriesFor(activeId);
  const activeFriendChat = activePerson && !profiles.some(person => person.id === activePerson.id) && entries.length === 0 ? friendChat(activePerson) : null;
  const shownDemo = activeDemo ?? activeFriendChat;
  const cardTime = nearbyLatest?.created_at;
  const updatesAfter = (nearbyObject?.identity_kind === "demo" ? DEMO_SPOTS_AFTER : []).filter((update) => !cardTime || minutesAgo(update.minutesAgo) > cardTime);
  const latestUpdate = updatesAfter.at(-1);
  const logLength = activeId === MUSE ? (demoSent[MUSE]?.length ?? 0) : shownDemo ? demoMessages(shownDemo).length : entries.length;

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [activeId, logLength, cardNote?.id]);

  useEffect(() => {
    const everything = allPosts.flatMap(({ post, object }) => [post, ...post.replies].map((item) => ({ post: item, object, root: post })));
    if (everything.length === 0) return;
    if (knownPosts.current === null) {
      knownPosts.current = new Set(everything.map((entry) => entry.post.id));
      return;
    }
    const known = knownPosts.current;
    const fresh = everything.filter((entry) => !known.has(entry.post.id));
    if (fresh.length === 0) return;
    fresh.forEach((entry) => known.add(entry.post.id));
    setNewIds((ids) => new Set([...ids, ...fresh.map((entry) => entry.post.id)]));
    const reply = fresh
      .filter((entry) => entry.post.parent_post_id !== null && entry.post.author.id !== profile?.id)
      .sort((a, b) => a.post.created_at.localeCompare(b.post.created_at))
      .at(-1);
    if (!reply) return;
    const alreadyOpen = activeId === reply.post.author.id || (activeId === SPOTS && reply.object.id === nearbyObject?.id);
    if (!alreadyOpen) {
      setBanner(reply);
      setUnreadFrom((people) => new Set(people).add(reply.post.author.id));
    }
  }, [allPosts]);

  useEffect(() => {
    if (!banner) return;
    const timer = window.setTimeout(() => setBanner(null), 7000);
    return () => window.clearTimeout(timer);
  }, [banner]);

  useEffect(() => {
    if (newIds.size === 0) return;
    const timer = window.setTimeout(() => setNewIds(new Set()), 4000);
    return () => window.clearTimeout(timer);
  }, [newIds]);

  useEffect(() => {
    if (activeId === SPOTS) setSeenSpots(true);
    if (activeId === MUSE) setSeenMuse(true);
    if (activeId.startsWith(DEMO_PREFIX)) setSeenDemo((seen) => new Set(seen).add(activeId));
    setUnreadFrom((people) => {
      if (!people.has(activeId)) return people;
      const next = new Set(people);
      next.delete(activeId);
      return next;
    });
    if (banner && (banner.post.author.id === activeId || (activeId === SPOTS && banner.object.id === nearbyObject?.id))) setBanner(null);
    setDraft("");
    setFromVoice(false);
    setSendError(null);
  }, [activeId]);

  const matches = (name: string) => name.toLowerCase().includes(query.trim().toLowerCase());

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const body = draft.trim();
    if (!body || !profile) return;
    if (activeId === MUSE) {
      setDemoSent((sent) => ({ ...sent, [MUSE]: [...(sent[MUSE] ?? []), { from: "me", body, minutesAgo: 0 }] }));
      setDraft("");
      setFromVoice(false);
      return;
    }
    if (shownDemo) {
      setDemoSent((sent) => ({ ...sent, [shownDemo.id]: [...(sent[shownDemo.id] ?? []), { from: "me", body, minutesAgo: 0 }] }));
      setDraft("");
      setFromVoice(false);
      return;
    }
    const lastEntry = entries.at(-1);
    const object = activeId === SPOTS ? nearbyObject : lastEntry?.object ?? nearbyObject;
    if (!object) return;
    setSending(true);
    setSendError(null);
    try {
      await api.createPost(object.id, {
        author_id: profile.id,
        body,
        // In a person's chat, messages reply to the note you're talking about.
        parent_post_id: activeId === SPOTS ? null : lastEntry?.root.id ?? null,
        client_request_id: crypto.randomUUID(),
      });
      setDraft("");
      setFromVoice(false);
      onPosted();
    } catch (error) {
      setSendError(error instanceof Error ? `${error.message} Your message is still here.` : "Could not send.");
    } finally {
      setSending(false);
    }
  };

  const toggleVoice = async () => {
    if (recorder.state === "recording") {
      const text = await recorder.stop();
      if (text !== null) {
        setDraft(text);
        setFromVoice(true);
      }
    } else if (recorder.state === "idle") {
      await recorder.start();
    }
  };

  const recording = recorder.state === "recording";
  const shownError = sendError ?? recorder.error;

  return (
    <section className="messages-page">
      {shownDemo && <span className="illustrative-chat-label">Illustrative demo chat · messages stay in this browser session</span>}
      <aside className="inbox">
        <header className="inbox__header">
          <label className="account-switch">
            <strong>{profile ? username(profile.display_name) : "…"}</strong>
            <Icon name="chevronDown" />
            <select aria-label="Switch demo person" value={profile?.id ?? ""} onChange={(event) => onSwitchProfile(event.target.value)}>
              {profiles.map((person) => <option key={person.id} value={person.id}>{person.display_name}</option>)}
            </select>
          </label>
          <button className="icon-button" aria-label="New message"><Icon name="compose" /></button>
        </header>

        <label className="inbox-search">
          <Icon name="search" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" />
        </label>

        <div className="notes-row">
          {profile && (
            <div className="story-note">
              <span className="story-note__bubble story-note__bubble--empty"><span>Note…</span></span>
              <Avatar profile={profile} size="xl" />
              <small>Your note</small>
            </div>
          )}
          {people.map((person) => ({ person, note: latestBy(person.id) })).filter(({ note }) => note && note.body.length <= 40).map(({ person, note }) => {
            return (
              <button className="story-note" key={person.id} onClick={() => setActiveId(person.id)}>
                <span className="story-note__bubble"><span>{note!.body}</span></span>
                <Avatar profile={person} size="xl" />
                <small>{person.display_name.split(" ")[0]}</small>
              </button>
            );
          })}
          {DEMO_PEOPLE.slice(0, 3).map((person) => (
            <button
              className="story-note"
              key={person.id}
              onClick={() => DEMO_CONVERSATIONS.some((conversation) => conversation.id === person.id) && setActiveId(DEMO_PREFIX + person.id)}
            >
              <span className="story-note__bubble"><span>{DEMO_STORY_NOTES[person.id]}</span></span>
              <Avatar profile={person} size="xl" />
              <small>{person.display_name.split(" ")[0]}</small>
            </button>
          ))}
        </div>

        <div className="inbox__section"><strong>Messages</strong><button className="text-button">Requests</button></div>

        <div className="conversation-list">
          {matches("Spots") && (
            <button className={`conversation ${activeId === SPOTS ? "is-active" : ""}`} onClick={() => setActiveId(SPOTS)}>
              <SpotsAvatar size="lg" />
              <span className="conversation__text">
                <strong>Spots</strong>
                <small className={seenSpots ? "" : "is-unread"}>
                  {latestUpdate
                    ? <>{latestUpdate.body} · {relativeTime(minutesAgo(latestUpdate.minutesAgo))}</>
                    : <>{spotsPreview}{nearbyLatest && <> · {relativeTime(nearbyLatest.created_at)}</>}</>}
                </small>
              </span>
              {!seenSpots && <i className="unread-indicator" />}
            </button>
          )}
          {matches("Muse") && (
            <button className={`conversation ${activeId === MUSE ? "is-active" : ""}`} onClick={() => setActiveId(MUSE)}>
              <MuseAvatar size="lg" />
              <span className="conversation__text">
                <strong>Muse</strong>
                <small className={seenMuse ? "" : "is-unread"}>{musePreview(museHighlight)}</small>
              </span>
              {!seenMuse && <i className="unread-indicator" />}
            </button>
          )}
          {people.filter((person) => matches(person.display_name)).map((person) => {
            const last = entriesFor(person.id).at(-1);
            const mine = last?.post.author.id === profile?.id;
            const demoLast = last ? null : demoMessages(friendChat(person)).at(-1);
            const unread = unreadFrom.has(person.id);
            // In their own row, drop the person's name: "Replied to you: …", "You replied to Theo: …".
            const label = last && last.post.parent_post_id !== null ? replyLabel(last.post, last.root, profile) : "";
            const lastPrefix = !last ? "" : label
              ? mine
                ? `${label.endsWith(` to ${firstName(person)}`) ? "You replied" : label}: `
                : `${label.slice(label.indexOf(" ") + 1).replace(/^\w/, (letter) => letter.toUpperCase())}: `
              : mine ? "You: " : "";
            return (
              <button key={person.id} className={`conversation ${activeId === person.id ? "is-active" : ""}`} onClick={() => setActiveId(person.id)}>
                <Avatar profile={person} size="lg" />
                <span className="conversation__text">
                  <strong>{person.display_name}</strong>
                  <small className={unread ? "is-unread" : ""}>
                    {last
                      ? <>{lastPrefix}{last.post.body} · {relativeTime(last.post.created_at)}</>
                      : demoLast && <>{demoLast.from === "me" ? "You: " : ""}{demoLast.body} · {relativeTime(minutesAgo(demoLast.minutesAgo))}</>}
                  </small>
                </span>
                {unread && <i className="unread-indicator" />}
              </button>
            );
          })}
          {DEMO_CONVERSATIONS.filter((conversation) => matches(conversation.title)).map((conversation) => {
            const id = DEMO_PREFIX + conversation.id;
            const last = demoMessages(conversation).at(-1);
            const unread = conversation.unread && !seenDemo.has(id);
            const sender = last?.from === "me" ? "You: " : conversation.people.length > 1 ? `${conversation.people.find((item) => item.id === last?.from)?.display_name.split(" ")[0]}: ` : "";
            return (
              <button key={id} className={`conversation ${activeId === id ? "is-active" : ""}`} onClick={() => setActiveId(id)}>
                <ConversationAvatar conversation={conversation} size="lg" />
                <span className="conversation__text">
                  <strong>{conversation.title}</strong>
                  <small className={unread ? "is-unread" : ""}>
                    {last && <>{sender}{last.body} · {relativeTime(minutesAgo(last.minutesAgo))}</>}
                  </small>
                </span>
                {unread && <i className="unread-indicator" />}
              </button>
            );
          })}
        </div>
      </aside>

      <section className="chat">
        {banner && (
          <button
            className="reply-banner"
            role="status"
            onClick={() => { setActiveId(banner.post.author.id); setBanner(null); }}
            aria-label={`${replyLabel(banner.post, banner.root, profile)}: ${banner.post.body}. Open conversation`}
          >
            <Avatar profile={banner.post.author} size="md" />
            <span className="reply-banner__text">
              <strong>{firstName(banner.post.author)} replied to {banner.root.author.id === profile?.id ? "your note" : `${firstName(banner.root.author)}'s note`}</strong>
              <span className="reply-banner__body">{banner.post.body}</span>
              <span className="reply-banner__original">“{banner.root.body}”</span>
              <small>on {banner.object.title} · now</small>
            </span>
            <Icon name="reply" className="reply-banner__icon" />
          </button>
        )}
        <header className="chat__header">
          {activeId === MUSE
            ? <MuseAvatar size="md" />
            : activeDemo
            ? <ConversationAvatar conversation={activeDemo} size="md" />
            : activePerson ? <Avatar profile={activePerson} size="md" /> : <SpotsAvatar size="md" />}
          <div>
            <strong>{activeId === MUSE ? "Muse" : activeDemo?.title ?? activePerson?.display_name ?? "Spots"}</strong>
            <small>{activeId === MUSE ? "AI" : activeDemo?.subtitle ?? (activePerson ? "Active today" : "spots")}</small>
          </div>
          <div className="chat__tools">
            {activeId !== SPOTS && activeId !== MUSE && <button className="icon-button" aria-label="Audio call"><Icon name="phone" /></button>}
            {activeId !== SPOTS && activeId !== MUSE && <button className="icon-button" aria-label="Video call"><Icon name="video" /></button>}
            <button className="icon-button" aria-label="Conversation details"><Icon name="info" /></button>
          </div>
        </header>

        <div className="chat__log" ref={logRef} aria-live="polite">
          {activeId === SPOTS && nearbyObject?.identity_kind === "demo" && <SpotsUpdates updates={DEMO_SPOTS_BEFORE} />}
          {activeId === SPOTS && nearbyObject && (
            <>
              {nearbyLatest && <div className="chat-time">{dayAndTime(nearbyLatest.created_at)}</div>}
              <div className="chat-row">
                {updatesAfter.length > 0 ? <span className="chat-avatar-spacer" /> : <SpotsAvatar size="sm" />}
                <div className="chat-bubble-wrap">
                  <button className="nearby-card" onClick={() => onOpenLens(nearbyObject)}>
                    <span className="nearby-card__head">
                      <SpotsAvatar size="xs" />
                      <span>
                        <strong>spots</strong>
                        <small>{nearbyObject.identity_kind === "demo" ? `Demo · ${PLACE_NAME}, ${PLACE_LOCATION}` : "Saved object memory"}</small>
                      </span>
                    </span>
                    <SceneCrop
                      markerId={nearbyObject.marker_id}
                      objectId={nearbyObject.id}
                      title={nearbyObject.title}
                      note={cardNote}
                    />
                    <span className="nearby-card__action">View through glasses</span>
                  </button>
                </div>
              </div>
            </>
          )}
          {activeId === SPOTS && <SpotsUpdates updates={updatesAfter} after={cardTime} />}
          {activeId === SPOTS && cardNote && spotsEntries.length > 0 && (
            <div className="chat-thread-label">
              <span>{spotsEntries.length === 1 ? "1 reply" : `${spotsEntries.length} replies`} on {cardNote.author.id === profile?.id ? "your" : `${firstName(cardNote.author)}'s`} note</span>
            </div>
          )}
          {activeId === MUSE
            ? <MuseChat
                highlight={museHighlight}
                sent={(demoSent[MUSE] ?? []).map((message) => message.body)}
                onSend={(text) => setDemoSent((sent) => ({ ...sent, [MUSE]: [...(sent[MUSE] ?? []), { from: "me", body: text, minutesAgo: 0 }] }))}
                onOpenLens={onOpenLens}
              />
            : shownDemo
            ? <DemoLog conversation={shownDemo} messages={demoMessages(shownDemo)} />
            : <ChatLog
                entries={entries}
                viewer={profile}
                showObject={activeId !== SPOTS}
                newIds={newIds}
                after={activeId === SPOTS ? nearbyLatest?.created_at : undefined}
              />}
        </div>

        {shownError && <p className="form-error chat-error" role="alert">{shownError}</p>}

        <form className="chat-bar" onSubmit={send}>
          <button type="button" className="icon-button" aria-label="Add emoji" onClick={() => setDraft((text) => `${text}🙂`)}><Icon name="smile" /></button>
          {(fromVoice || recording || recorder.state === "transcribing") && (
            <span className={`voice-pill ${recording ? "is-recording" : ""}`} aria-hidden="true">
              <i /><i /><i /><i /><i /><i /><i />
            </span>
          )}
          <input
            ref={inputRef}
            value={draft}
            maxLength={500}
            disabled={sending || recording}
            onChange={(event) => {
              setDraft(event.target.value);
              if (!event.target.value) setFromVoice(false);
            }}
            placeholder={recording ? "Listening…" : recorder.state === "transcribing" ? "Transcribing…" : activeId === MUSE ? "Message Muse…" : "Message…"}
            aria-label="Message"
          />
          {draft && (
            <button type="button" className="icon-button" aria-label="Clear message" onClick={() => { setDraft(""); setFromVoice(false); }}>
              <Icon name="close" />
            </button>
          )}
          <button
            type="button"
            className={`icon-button ${recording ? "is-recording" : ""}`}
            aria-label={recording ? "Stop recording" : "Record voice message"}
            disabled={!transcriptionConfigured || recorder.state === "transcribing"}
            onClick={toggleVoice}
          >
            <Icon name="mic" />
          </button>
          {draft.trim() ? (
            <button type="submit" className="send-button" disabled={sending || !profile}>{sending ? "Sending…" : "Send"}</button>
          ) : (
            <>
              <button type="button" className="icon-button" aria-label="Add photo"><Icon name="image" /></button>
              <button type="button" className="icon-button" aria-label="Add sticker"><Icon name="sticker" /></button>
            </>
          )}
        </form>
      </section>
    </section>
  );
}
