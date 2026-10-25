import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { relativeTime } from "../format";
import { browserSpeechSupported, useBrowserSpeech } from "../hooks/useBrowserSpeech";
import { useTranscribedRecorder } from "../hooks/useTranscribedRecorder";
import { PLACE_NAME } from "../scene";
import { flattenPosts, noteCount } from "../threadUtils";
import type { ObjectSummary, Post, Profile, ThreadResponse } from "../types";
import { Avatar } from "./Avatar";
import { Icon } from "./Icons";

export type AssistantState = "idle" | "listening" | "thinking" | "speaking" | "error";

// An original ribbon mark for the in-lens assistant. It is intentionally not an
// official Meta or Muse logo; the two uneven loops suggest listening and reply.
export function MuseEmblem({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 52 30" aria-hidden="true">
      <path d="M4.5 16.2C8.8 5.1 16.8 4.1 25.8 14.7c8.8 10.4 16.3 10 21.7-1.1" />
      <path d="M4.5 16.2c5.7 10.6 13.8 9.8 22.2-.8C35.3 4.6 43 5.1 47.5 13.6" />
    </svg>
  );
}

// Pieces of the Spots glasses UI. Styling follows Meta's display guidelines (dark-gray surfaces,
// white type, 16/14/12 type scale, focus-driven input); the layouts themselves are Spots proposals.

// The note the wearer should hear about first: the newest one someone else left.
export function featuredNote(thread: ThreadResponse | undefined, viewer: Profile | null) {
  const posts = flattenPosts(thread?.posts ?? []);
  return posts.filter((post) => post.author.id !== viewer?.id).at(-1) ?? posts.at(-1) ?? null;
}

function firstName(profile: Profile) {
  return profile.display_name.split(" ")[0];
}

// A small, consistent indicator that a menu item has notes. It sits just before the printed
// dish name so the name itself stays readable.
export function NoteMarker({
  object,
  thread,
  position,
  open,
  focused = false,
  onOpen,
}: {
  object: ObjectSummary;
  thread: ThreadResponse | undefined;
  position: [number, number];
  open: boolean;
  // The item the wearer has moved to with the arrow keys.
  focused?: boolean;
  onOpen: () => void;
}) {
  const count = noteCount(thread);
  return (
    <button
      className={`g-marker ${open ? "is-open" : ""} ${focused ? "is-focused" : ""}`}
      style={{ left: position[0], top: position[1] }}
      onClick={onOpen}
      aria-label={`${object.title}: ${count} ${count === 1 ? "note" : "notes"}. Open`}
      aria-expanded={open}
    >
      <span className="g-marker__dot" aria-hidden="true">
        <Icon name="notes" />
      </span>
      {count > 1 && <span className="g-marker__count">{count}</span>}
    </button>
  );
}

// Brief feedback at the top of the view; it dismisses itself.
export function GlassesToast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const words = message.split(/\s+/).length;
    const timer = window.setTimeout(onDone, Math.min(8000, 3500 + Math.max(0, words - 2) * 300));
    return () => window.clearTimeout(timer);
  }, [message]);
  return <div className="g-toast" role="status">{message}</div>;
}

type Step = "note" | "thread" | "command" | "listening" | "transcribing" | "typing" | "confirm" | "sending";

// The selected-note card, with the reply flow: speak (or type) → review → confirm → saved.
// Nothing is posted until the wearer confirms.
export function NoteCard({
  object,
  thread,
  viewer,
  transcriptionConfigured,
  onClose,
  onPosted,
  assistantSignal = 0,
  onAssistantStateChange,
  onAskAssistant,
}: {
  object: ObjectSummary;
  thread: ThreadResponse | undefined;
  viewer: Profile | null;
  transcriptionConfigured: boolean;
  onClose: () => void;
  onPosted: (confirmation: string) => void;
  assistantSignal?: number;
  onAssistantStateChange?: (state: AssistantState) => void;
  onAskAssistant?: (prompt: string) => void;
}) {
  const note = featuredNote(thread, viewer);
  const root = note ? thread?.posts.find((post) => post.id === (note.parent_post_id ?? note.id)) ?? null : null;
  const replyingTo = note && root ? note.author : null;
  const [step, setStep] = useState<Step>("note");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const recorder = useTranscribedRecorder();
  const speech = useBrowserSpeech();
  const commandSpeech = useBrowserSpeech();
  const voiceSource = transcriptionConfigured ? "backend" : browserSpeechSupported() ? "browser" : null;
  const requestIdRef = useRef(crypto.randomUUID());
  const firstActionRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const handledAssistantSignal = useRef(0);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const speechStartTimerRef = useRef<number | null>(null);
  const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;
  const threadReplies = root?.replies ?? [];
  const replyCount = threadReplies.length;
  const displayedNote = step === "thread" ? root ?? note : note;

  const authorContext = (post: Post) => {
    if (post.parent_post_id === null || !root) return post.author.display_name;
    if (post.author.id === viewer?.id) return `You replied to ${firstName(root.author)}`;
    if (root.author.id === viewer?.id) return `${post.author.display_name} replied to you`;
    return `${post.author.display_name} replied to ${firstName(root.author)}`;
  };

  useEffect(() => () => {
    if (speechStartTimerRef.current !== null) window.clearTimeout(speechStartTimerRef.current);
    utteranceRef.current = null;
    window.speechSynthesis?.cancel();
  }, []);
  useEffect(() => {
    if (step === "typing") inputRef.current?.focus();
    else firstActionRef.current?.focus();
  }, [step]);
  useEffect(() => {
    if (recorder.error) setError(recorder.error);
  }, [recorder.error]);
  useEffect(() => {
    if (!speech.error) return;
    setError(speech.error);
    setStep((current) => (current === "listening" ? "typing" : current));
  }, [speech.error]);
  useEffect(() => {
    if (!commandSpeech.error) return;
    setError(commandSpeech.error);
    setStep("note");
  }, [commandSpeech.error]);

  const reset = () => {
    setStep("note");
    setDraft("");
    setError(null);
    requestIdRef.current = crypto.randomUUID();
  };

  const readAloud = () => {
    if (!canSpeak || !note) {
      setError(note ? "Read aloud isn't supported by this browser." : "There isn't a note to read yet.");
      return;
    }
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      if (speechStartTimerRef.current !== null) window.clearTimeout(speechStartTimerRef.current);
      speechStartTimerRef.current = null;
      utteranceRef.current = null;
      setSpeaking(false);
      return;
    }
    setError(null);
    const utterance = new SpeechSynthesisUtterance(`${note.author.display_name} says: ${note.body}`);
    utteranceRef.current = utterance;
    utterance.lang = navigator.language || "en-US";
    const language = utterance.lang.toLowerCase().split("-")[0];
    utterance.voice = synth.getVoices().find((voice) => voice.lang.toLowerCase().startsWith(language)) ?? null;
    utterance.onstart = () => {
      if (speechStartTimerRef.current !== null) window.clearTimeout(speechStartTimerRef.current);
      speechStartTimerRef.current = null;
      setSpeaking(true);
    };
    utterance.onend = () => {
      if (speechStartTimerRef.current !== null) window.clearTimeout(speechStartTimerRef.current);
      speechStartTimerRef.current = null;
      utteranceRef.current = null;
      setSpeaking(false);
    };
    utterance.onerror = (event) => {
      if (speechStartTimerRef.current !== null) window.clearTimeout(speechStartTimerRef.current);
      speechStartTimerRef.current = null;
      utteranceRef.current = null;
      setSpeaking(false);
      if (event.error !== "canceled" && event.error !== "interrupted") {
        setError(
          event.error === "not-allowed"
            ? "Audio playback is blocked for this site. Allow sound or autoplay in browser settings, then try again."
            : event.error === "voice-unavailable" || event.error === "language-unavailable"
              ? "No compatible system voice is available for this note. Install or enable a system voice, then try again."
              : "The browser couldn't play this note aloud. Check system audio and try again.",
        );
      }
    };
    // Chrome can drop an utterance queued in the same tick as cancel(), and can be left paused.
    const speak = () => {
      synth.resume();
      synth.speak(utterance);
    };
    if (synth.speaking || synth.pending) {
      synth.cancel();
      window.setTimeout(speak, 60);
    } else {
      speak();
    }
    speechStartTimerRef.current = window.setTimeout(() => {
      if (utteranceRef.current === utterance && !synth.speaking) {
        utteranceRef.current = null;
        setSpeaking(false);
        setError("Read aloud didn't start. Check browser and system audio permissions, then try again.");
      }
    }, 1800);
  };

  const startReply = async () => {
    setError(null);
    window.speechSynthesis?.cancel();
    setSpeaking(false);
    if (voiceSource === "backend" && (await recorder.start())) {
      setStep("listening");
      return;
    }
    if (voiceSource === "browser" && speech.start()) {
      setStep("listening");
      return;
    }
    setStep("typing");
  };

  const handleCommand = (spoken: string) => {
    const command = spoken.trim().toLowerCase();
    setStep("note");
    if (/\b(read|hear|play)\b/.test(command)) {
      if (note && canSpeak) readAloud();
      else setError("Reading aloud isn't available in this browser.");
      return;
    }
    if (/\b(reply|respond|answer)\b/.test(command)) {
      void startReply();
      return;
    }
    setError(command ? "Try “read this note” or “reply to this note.”" : "I didn't catch that. Try again.");
  };

  // The emblem opens the real contextual voice controller. Its visual state is
  // derived from speech recognition, transcription, saving, and playback.
  useEffect(() => {
    if (!assistantSignal || assistantSignal === handledAssistantSignal.current) return;
    handledAssistantSignal.current = assistantSignal;
    setError(null);
    if (browserSpeechSupported()) {
      setStep("command");
      if (!commandSpeech.start({ continuous: false, onEnd: handleCommand })) {
        setStep("note");
        setError("Voice commands aren't available. Use the note actions instead.");
      }
    } else {
      void startReply();
    }
  }, [assistantSignal]);

  useEffect(() => {
    const next: AssistantState = error
      ? "error"
      : speaking
        ? "speaking"
        : step === "command" || step === "listening"
          ? "listening"
          : step === "transcribing" || step === "sending"
            ? "thinking"
            : "idle";
    onAssistantStateChange?.(next);
  }, [error, speaking, step, onAssistantStateChange]);

  const finishListening = async () => {
    setStep("transcribing");
    const text = voiceSource === "browser" ? (await speech.stop()) || speech.transcript : await recorder.stop();
    if (text && text.trim()) {
      setDraft(text.trim());
      setStep("confirm");
    } else {
      setStep("typing");
    }
  };

  const send = async () => {
    const body = draft.trim();
    if (!body || !viewer) return;
    setStep("sending");
    setError(null);
    try {
      await api.createPost(object.id, {
        author_id: viewer.id,
        body,
        parent_post_id: root?.id ?? null,
        client_request_id: requestIdRef.current,
      });
      onPosted(replyingTo ? `Reply sent to ${firstName(replyingTo)}` : `Note left on ${object.title}`);
      reset();
    } catch (sendError) {
      setError(sendError instanceof Error ? `${sendError.message} Your reply wasn't sent.` : "Your reply wasn't sent.");
      setStep("confirm");
    }
  };

  const actionLabel = replyingTo ? `Reply to ${firstName(replyingTo)}` : "Leave a note";

  return (
    <section
      className="g-card"
      role="dialog"
      aria-label={`${object.title} note`}
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        if (step === "note") onClose();
        else if (step !== "sending" && step !== "transcribing") {
          if (step === "command") commandSpeech.cancel();
          if (step === "listening") {
            if (voiceSource === "browser") speech.cancel();
            else void recorder.stop();
          }
          reset();
        }
      }}
    >
      <header className="g-card__header">
        <span className="g-card__place">{object.identity_kind === "demo" ? PLACE_NAME : "Spots"}</span>
        <button className="g-card__close" onClick={onClose} aria-label="Close note">
          <Icon name="close" />
        </button>
      </header>

      <div className="g-card__body">
        <span className="g-label">{object.title}</span>

        {displayedNote ? (
          <div className="g-note">
            <Avatar profile={displayedNote.author} size="sm" fallback="initials" />
            <div>
              <span className="g-author">{authorContext(displayedNote)}</span>
              <p className="g-note__text">{displayedNote.body}</p>
              <span className="g-meta">
                {relativeTime(displayedNote.created_at)} ago
                {displayedNote.parent_post_id === null && replyCount > 0 && <> · {replyCount} {replyCount === 1 ? "reply" : "replies"}</>}
              </span>
            </div>
          </div>
        ) : (
          <p className="g-note__text">No notes here yet.</p>
        )}

        {step === "thread" && (
          <div className="g-thread" aria-label={`${replyCount} ${replyCount === 1 ? "reply" : "replies"}`}>
            <div className="g-thread__heading">
              <span>Conversation</span>
              <span>{replyCount} {replyCount === 1 ? "reply" : "replies"}</span>
            </div>
            {threadReplies.map((reply) => (
              <div className={`g-thread__reply ${reply.author.id === viewer?.id ? "is-mine" : ""}`} key={reply.id}>
                <Avatar profile={reply.author} size="sm" fallback="initials" />
                <div>
                  <span className="g-thread__author">{authorContext(reply)}</span>
                  <p>{reply.body}</p>
                  <span className="g-meta">{relativeTime(reply.created_at)} ago</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {step === "command" && (
          <div className="g-listening" role="status">
            <p className="g-status"><span className="g-wave" aria-hidden="true"><i /><i /><i /><i /></span> Listening for a command…</p>
            {commandSpeech.transcript && <p className="g-live">{commandSpeech.transcript}</p>}
          </div>
        )}
        {step === "listening" && (
          <div className="g-listening" role="status">
            <p className="g-status"><span className="g-wave" aria-hidden="true"><i /><i /><i /><i /></span> Listening… speak your reply</p>
            {speech.transcript && <p className="g-live">{speech.transcript}</p>}
          </div>
        )}
        {step === "transcribing" && <p className="g-status" role="status"><span className="spinner" /> Transcribing…</p>}
        {step === "typing" && (
          <form className="g-input" onSubmit={(event) => { event.preventDefault(); if (draft.trim()) setStep("confirm"); }}>
            {!voiceSource && <span className="g-meta">Voice isn't available in this browser. Type your reply instead.</span>}
            <input
              ref={inputRef}
              value={draft}
              maxLength={500}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={replyingTo ? `Reply to ${firstName(replyingTo)}` : "Your note"}
              aria-label={actionLabel}
            />
          </form>
        )}
        {(step === "confirm" || step === "sending") && (
          <div className="g-confirm">
            <span className="g-meta">{replyingTo ? `Send to ${firstName(replyingTo)}?` : "Post this note?"}</span>
            <q className="g-confirm__text">{draft}</q>
          </div>
        )}
        {error && <p className="g-error" role="alert">{error}</p>}
      </div>

      <div className="g-actions">
        {step === "note" && (
          <>
            {onAskAssistant && <button className="g-action" onClick={() => onAskAssistant(`Read all past comments about ${object.title}`)}><Icon name="notes" /><span>Ask about past notes</span><Icon name="chevronRight" /></button>}

            {replyCount > 0 && (
              <button ref={firstActionRef} className="g-action" onClick={() => setStep("thread")}>
                <Icon name="notes" /> <span>View {replyCount} {replyCount === 1 ? "reply" : "replies"}</span> <Icon name="chevronRight" />
              </button>
            )}
            <button ref={replyCount === 0 ? firstActionRef : undefined} className="g-action" onClick={() => void startReply()} disabled={!viewer}>
              <Icon name="mic" /> <span>{replyingTo ? "Reply by voice" : "Leave a note by voice"}</span> <Icon name="chevronRight" />
            </button>
            {note && (
              <button className="g-action" onClick={readAloud} disabled={!canSpeak} title={canSpeak ? undefined : "Text-to-speech isn't available in this browser"}>
                <Icon name="speaker" /> <span>{speaking ? "Stop reading" : "Read aloud"}</span>
              </button>
            )}
          </>
        )}
        {step === "thread" && (
          <button ref={firstActionRef} className="g-action" onClick={() => setStep("note")}>
            <Icon name="chevronRight" className="g-icon-back" /> <span>Back to recommendation</span>
          </button>
        )}
        {step === "listening" && (
          <button ref={firstActionRef} className="g-action" onClick={() => void finishListening()}>
            <span className="record-square" /> <span>Done speaking</span>
          </button>
        )}
        {step === "typing" && (
          <>
            <button ref={firstActionRef} className="g-action" onClick={() => draft.trim() && setStep("confirm")} disabled={!draft.trim()}>
              <Icon name="chevronRight" /> <span>Review</span>
            </button>
            {voiceSource && (
              <button className="g-action" onClick={() => void startReply()}>
                <Icon name="mic" /> <span>Try microphone again</span>
              </button>
            )}
          </>
        )}
        {(step === "confirm" || step === "sending") && (
          <>
            <button ref={firstActionRef} className="g-action g-action--primary" onClick={() => void send()} disabled={step === "sending"}>
              <Icon name="chevronRight" /> <span>{step === "sending" ? "Sending…" : replyingTo ? `Send to ${firstName(replyingTo)}` : "Post note"}</span>
            </button>
            <button className="g-action" onClick={() => setStep("typing")} disabled={step === "sending"}>
              <Icon name="notes" /> <span>Edit</span>
            </button>
            <button className="g-action" onClick={reset} disabled={step === "sending"}>
              <Icon name="close" /> <span>Cancel</span>
            </button>
          </>
        )}
      </div>

      <p className="g-hint">{step === "note" ? "Esc to close" : step === "thread" ? "Esc to go back" : "Esc to cancel"}</p>
    </section>
  );
}
