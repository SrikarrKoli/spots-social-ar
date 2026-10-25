import { useEffect, useState, type ReactNode } from "react";
import { clockTime, dayAndTime } from "../format";
import type { ObjectSummary, Post } from "../types";
import { Icon } from "./Icons";

// A static, illustrative DM with Muse, the assistant concept. It uses the same
// chat pieces as every other conversation; nothing is generated or sent.

export const MUSE = "muse";

export function MuseAvatar({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`avatar avatar--${size} avatar--muse`} aria-hidden="true">
      <svg viewBox="0 0 100 100">
        <defs>
          <linearGradient id={`muse-ink-${size}`} x1="15" y1="25" x2="85" y2="72" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#1f52dc" />
            <stop offset="1" stopColor="#3b8ef6" />
          </linearGradient>
        </defs>
        <path
          d="M18 47C22 33 27 25 30 28C33 31 27 55 26 68C32 50 40 31 47 30C53 29 49 51 48 66C55 51 62 38 68 38C74 38 70 57 70 66C74 60 79 55 84 51"
          stroke={`url(#muse-ink-${size})`}
        />
      </svg>
    </span>
  );
}

export interface MuseHighlight {
  note: Post;
  object: ObjectSummary;
}

const FALLBACK: MuseHighlight = {
  object: { id: "favorite-book", title: "Favorite book", description: null } as ObjectSummary,
  note: {
    id: -1,
    object_id: "favorite-book",
    author: { id: "lina", display_name: "Lina Ortiz", initials: "LO", color: "#8B6F9E" },
    body: "The world-building is incredible. Start with chapter two if the opening feels slow.",
    created_at: new Date().toISOString(),
    parent_post_id: null,
    replies: [],
  },
};

const firstName = (highlight: MuseHighlight) => highlight.note.author.display_name.split(" ")[0];

export function musePreview(highlight: MuseHighlight | null) {
  const shown = highlight ?? FALLBACK;
  return `${firstName(shown)} left a note on the ${shown.object.title.toLowerCase()}. Want me to reply?`;
}

// Instagram-style suggested replies, and Muse's canned answer to each.
export function museSuggestions(highlight: MuseHighlight | null) {
  const shown = highlight ?? FALLBACK;
  const name = firstName(shown);
  return [
    { label: "Yes, say I'm in", answer: `Done. I replied “Count me in!” on ${name}'s note.` },
    { label: "Read me the note", answer: `${name} said: “${shown.note.body}”` },
    { label: "Not now", answer: "No problem. I'll save it for later." },
  ];
}

function MuseRow({ children, avatar }: { children: ReactNode; avatar: boolean }) {
  return (
    <div className="chat-row">
      {avatar ? <MuseAvatar size="sm" /> : <span className="chat-avatar-spacer" />}
      <div className="chat-bubble-wrap">{children}</div>
    </div>
  );
}

export function MuseChat({
  highlight,
  sent,
  onSend,
  onOpenLens,
}: {
  highlight: MuseHighlight | null;
  // What the viewer has said in this mock chat, typed or tapped, in order.
  sent: string[];
  onSend: (text: string) => void;
  onOpenLens: (object: ObjectSummary) => void;
}) {
  const shown = highlight ?? FALLBACK;
  const name = firstName(shown);
  const suggestions = museSuggestions(highlight);
  const answerFor = (text: string) =>
    suggestions.find((item) => item.label === text)?.answer ?? "I'm a preview in this demo, so I can't do that yet.";
  // Muse "types" for a moment before answering the newest message.
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    if (sent.length === 0) return;
    setTyping(true);
    const timer = window.setTimeout(() => setTyping(false), 1100);
    return () => window.clearTimeout(timer);
  }, [sent.length]);
  const opened = new Date(Date.now() - 4 * 60_000).toISOString();
  // Suggestions stay only while the viewer is choosing from them; typing your own message ends them.
  const typedOwn = sent.some((text) => !suggestions.some((item) => item.label === text));
  const remaining = typedOwn ? [] : suggestions.filter((item) => !sent.includes(item.label));

  return (
    <>
      <p className="chat-disclaimer">Illustrative demo chat · Muse is a concept, not a live assistant</p>
      <div className="chat-time">{dayAndTime(opened)}</div>
      <MuseRow avatar={false}>
        <p className="chat-bubble" title={clockTime(opened)}>{name} left a note on the {shown.object.title.toLowerCase()} you walked past</p>
      </MuseRow>
      <MuseRow avatar={false}>
        <button
          type="button"
          className="shared-note shared-note--button"
          onClick={() => highlight && onOpenLens(highlight.object)}
          disabled={!highlight}
        >
          <Icon name="glasses" />
          <span><strong>Spots note</strong><small>{shown.object.title} · {shown.note.author.display_name}</small></span>
        </button>
      </MuseRow>
      <MuseRow avatar={sent.length === 0}>
        <p className="chat-bubble">Want me to reply to {name}?</p>
      </MuseRow>
      {sent.map((text, index) => {
        const answering = typing && index === sent.length - 1;
        return (
          <div key={index}>
            <div className="chat-row chat-row--mine">
              <div className="chat-bubble-wrap"><p className="chat-bubble">{text}</p></div>
            </div>
            <MuseRow avatar={index === sent.length - 1}>
              {answering
                ? <span className="typing-bubble" role="status" aria-label="Muse is typing"><i /><i /><i /></span>
                : <p className="chat-bubble">{answerFor(text)}</p>}
            </MuseRow>
          </div>
        );
      })}
      {!typing && remaining.length > 0 && (
        <div className="quick-replies" aria-label="Suggested replies">
          {remaining.map((item) => (
            <button type="button" key={item.label} onClick={() => onSend(item.label)}>{item.label}</button>
          ))}
        </div>
      )}
    </>
  );
}
