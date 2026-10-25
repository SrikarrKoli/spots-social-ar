import { memo, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { lockTarget } from "../target";
import type { Detection, LiveScan, LockedTarget, ObjectSummary, Post, Profile, ThreadResponse } from "../types";
import { voiceModeForState, type VoiceIntent } from "../voiceCommands";
import { stopSpeaking } from "../speech";
import { usePolling } from "../hooks/usePolling";
import { Avatar } from "./Avatar";
import { Composer, type ExternalTranscript, type VoiceDraftAction } from "./Composer";
import { VoiceControl } from "./VoiceControl";

interface Props {
  assistantDraft?: { text: string; nonce: number } | null;
  onAssistantDraftHandled?: () => void;
  object: ObjectSummary | null;
  availableObjects: ObjectSummary[];
  onSelectObject: (object: ObjectSummary) => void;
  onObjectEnrolled?: (object: ObjectSummary) => void;
  onEnrollmentActiveChange?: (active: boolean) => void;
  showImproveHint?: boolean;
  provisionalDetections?: Detection[];
  onConfirmProvisional?: (identityKey: string) => void;
  profile: Profile | null;
  transcriptionConfigured: boolean;
}

export interface EnrolVoiceRequest {
  title: string;
  nonce: number;
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

function EnrollObject({
  onEnrolled,
  onEnrollmentActiveChange,
  enrolRequest = null,
  onEnrolRequestHandled,
}: {
  onEnrolled: (object: ObjectSummary) => void;
  onEnrollmentActiveChange?: (active: boolean) => void;
  enrolRequest?: EnrolVoiceRequest | null;
  onEnrolRequestHandled?: () => void;
}) {
  const [title, setTitle] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [state, setState] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [scan, setScan] = useState<LiveScan | null>(null);

  // Scanning *and* reviewing both suppress recognition auto-open and
  // keep the centre guide visible.
  useEffect(() => {
    onEnrollmentActiveChange?.(busy || scan !== null);
  }, [busy, scan, onEnrollmentActiveChange]);
  useEffect(
    () => () => onEnrollmentActiveChange?.(false),
    [onEnrollmentActiveChange],
  );

  async function runCountdown<T>(action: () => Promise<T>): Promise<T> {
    setBusy(true);
    const endsAt = Date.now() + 4000;
    setSecondsLeft(4);
    const timer = window.setInterval(() => {
      setSecondsLeft(Math.max(0, (endsAt - Date.now()) / 1000));
    }, 100);
    try {
      return await action();
    } finally {
      window.clearInterval(timer);
      setSecondsLeft(null);
      setBusy(false);
    }
  }

  async function startScan() {
    setState("Look at the object — keep it inside the guide box and slowly turn it…");
    try {
      const result = await runCountdown(() => api.scanLive());
      setScan(result);
      setState(
        `Captured ${result.captured_views.length} view(s) from ${result.diagnostics.frames_sampled} frames. ` +
          "Check the crops are your object — scan more angles or save.",
      );
    } catch (error) {
      setState(error instanceof Error ? error.message : "Scan failed.");
    }
  }

  // Voice enrolment: "enrol this as <name>" prefills the spoken name and
  // starts the same 4s scan. Saving still needs the crops review + Save.
  const lastEnrolNonce = useRef(0);
  useEffect(() => {
    if (!enrolRequest || enrolRequest.nonce === lastEnrolNonce.current) return;
    lastEnrolNonce.current = enrolRequest.nonce;
    setTitle(enrolRequest.title);
    onEnrolRequestHandled?.();
    void startScan();
    // startScan is stable enough for this trigger; nonce guards re-runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enrolRequest]);

  async function scanMore() {
    if (!scan) return;
    setState("Turn the object to a new angle and keep it in the guide box…");
    try {
      const result = await runCountdown(() => api.scanMore(scan.scan_id));
      setScan(result);
      setState(
        `Now ${result.captured_views.length} view(s) total (${result.diagnostics.frames_sampled} frames sampled).`,
      );
    } catch (error) {
      setState(error instanceof Error ? error.message : "Scan failed.");
    }
  }

  async function saveScan() {
    if (!scan || !title.trim()) return;
    setBusy(true);
    try {
      const created = await api.enrollLive(scan.scan_id, title.trim(), "");
      setScan(null);
      setTitle("");
      setState(null);
      onEnrolled(created);
    } catch (error) {
      setState(error instanceof Error ? error.message : "Could not save this object.");
    } finally {
      setBusy(false);
    }
  }

  async function discardScan() {
    if (!scan) return;
    try {
      await api.discardScan(scan.scan_id);
      setState("Scan discarded — nothing was saved.");
    } catch {
      setState("Scan discarded locally — nothing was saved.");
    }
    setScan(null);
  }

  async function submitUpload() {
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
      <span>CREATE A NEW OBJECT — BY LOOKING (NO MARKER)</span>
      <input
        aria-label="Object name"
        placeholder="e.g. My black bottle"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      {!scan ? (
        <button disabled={busy} onClick={() => void startScan()}>
          {busy
            ? `Scanning — keep looking… ${secondsLeft !== null ? secondsLeft.toFixed(1) : ""}s`
            : "Scan the object (4s)"}
        </button>
      ) : (
        <>
          <button disabled={busy || !title.trim()} onClick={() => void saveScan()}>
            {busy ? "Saving…" : `Save “${title.trim() || "object"}” and open its thread`}
          </button>
          <button disabled={busy} onClick={() => void scanMore()}>
            {busy
              ? `Scanning — keep looking… ${secondsLeft !== null ? secondsLeft.toFixed(1) : ""}s`
              : "Scan more views (new angle)"}
          </button>
          <button disabled={busy} onClick={() => void discardScan()}>
            Discard scan
          </button>
        </>
      )}
      <small>Just look at the object through the glasses and slowly turn it.</small>
      {state && <small className="enroll-state" role="status">{state}</small>}
      {scan && (
        <div className="enrolled-views">
          <span>CAPTURED VIEWS — IS THIS YOUR OBJECT?</span>
          <div className="enrolled-views__grid">
            {scan.captured_views.map((view, index) => (
              <img
                key={index}
                src={`data:image/jpeg;base64,${view}`}
                alt={`Captured view ${index + 1} of the new object`}
              />
            ))}
          </div>
        </div>
      )}
      <details>
        <summary>Dev/test only: enrol from a photo file</summary>
        <input
          aria-label="Photo of the object"
          type="file"
          accept="image/*"
          onChange={(event) => setImage(event.target.files?.[0] ?? null)}
        />
        <button disabled={busy || !title.trim() || !image} onClick={() => void submitUpload()}>
          Enrol from this photo
        </button>
      </details>
    </div>
  );
}

export const ThreadPanel = memo(function ThreadPanel({ assistantDraft = null, onAssistantDraftHandled, object, availableObjects, onSelectObject, onObjectEnrolled, onEnrollmentActiveChange, showImproveHint = false, provisionalDetections = [], onConfirmProvisional, profile, transcriptionConfigured }: Props) {
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [draftReviewing, setDraftReviewing] = useState(false);
  const [pendingTranscript, setPendingTranscript] = useState<ExternalTranscript | null>(null);
  const [voiceAction, setVoiceAction] = useState<VoiceDraftAction | null>(null);
  const [enrolRequest, setEnrolRequest] = useState<EnrolVoiceRequest | null>(null);
  const nonceRef = useRef(0);
  const nextNonce = () => ++nonceRef.current;
  const [improveState, setImproveState] = useState<string | null>(null);
  const [improveBusy, setImproveBusy] = useState(false);

  async function addViewsToCurrent() {
    if (!object) return;
    setImproveBusy(true);
    setImproveState("Look at the object inside the guide box and slowly turn it…");
    onEnrollmentActiveChange?.(true);
    try {
      const result = await api.addViews(object.id);
      setImproveState(
        `Added views from ${result.diagnostics.frames_sampled} frames — ` +
          `${result.reference_count} reference view(s) now enrolled. Keep looking at it.`,
      );
    } catch (error) {
      setImproveState(error instanceof Error ? error.message : "Could not add views.");
    } finally {
      setImproveBusy(false);
      onEnrollmentActiveChange?.(false);
    }
  }
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composerTarget, setComposerTarget] = useState<LockedTarget | null>(null);

  const recordingTargetRef = useRef<LockedTarget | null>(null);

  // -- voice ---------------------------------------------------------------
  const voiceMode = voiceModeForState(Boolean(object), Boolean(composerTarget), draftReviewing);
  const confirmableProvisional =
    provisionalDetections.length === 1 ? provisionalDetections[0] : null;
  const voiceContext = {
    objects: availableObjects.map((item) => ({ id: item.id, title: item.title })),
    authorPosts: (thread?.posts ?? []).map((post) => ({
      postId: post.id,
      authorName: post.author.display_name,
    })),
    provisionalTitles: provisionalDetections.map(
      (detection) => detection.object?.title ?? "Unknown object",
    ),
  };

  function handleDictation(text: string): string {
    const target = composerTarget ?? recordingTargetRef.current ?? (object ? lockTarget(object) : null);
    recordingTargetRef.current = null;
    if (!target) return "Open a thread first, or say “open the book”.";
    setComposerTarget(target);
    setPendingTranscript({ text, nonce: nextNonce() });
    return `Draft for “${target.object.title}” — review it, then say “post it” or press Post.`;
  }

  function handleVoiceIntent(intent: VoiceIntent): string {
    switch (intent.type) {
      case "start_note":
        if (!object) return "Look at an enrolled object or open a thread first.";
        if (!composerTarget) setComposerTarget(lockTarget(object));
        return "Ready for your note. Push to talk, dictate, then review before posting.";
      case "read_draft":
        setVoiceAction({ type: "read", nonce: nextNonce() });
        return "Reading your draft. Say post it only when you are ready to publish.";
      case "post_draft":
        setVoiceAction({ type: "post", nonce: nextNonce() });
        return "Posting your reviewed draft…";
      case "cancel_draft":
        setVoiceAction({ type: "cancel", nonce: nextNonce() });
        return "Draft cancelled — nothing was posted.";
      case "retry_dictation":
        setVoiceAction({ type: "retry", nonce: nextNonce() });
        return "Draft cleared. Push to talk to record again.";
      case "confirm_provisional":
        if (!confirmableProvisional) return "No single possible match is visible to confirm.";
        onConfirmProvisional?.(confirmableProvisional.identity_key);
        return `Confirmed “${confirmableProvisional.object?.title ?? "object"}” — that view is banked.`;
      case "open_object": {
        if (composerTarget) return "Post or cancel the current draft first.";
        const found = availableObjects.find((item) => item.id === intent.objectId);
        if (!found) return "That object is no longer enrolled.";
        onSelectObject(found);
        return `Opened the “${found.title}” thread.`;
      }
      case "reply_to": {
        if (!object) return "Open a thread first.";
        if (composerTarget) return "Post or cancel the current draft first.";
        const post = thread?.posts.find((item) => item.id === intent.postId);
        if (!post) return "That post is no longer in this thread.";
        setComposerTarget(lockTarget(object, post));
        return `Replying to ${post.author.display_name} — dictate your reply.`;
      }
      case "enrol_live":
        if (composerTarget) return "Post or cancel the current draft first.";
        setCreatorOpen(true);
        setEnrolRequest({ title: intent.title, nonce: nextNonce() });
        return `Enrolling “${intent.title}” — look at it in the guide box and slowly turn it. Review the crops, then Save.`;
      case "ambiguous":
        return `That could be ${intent.candidates.join(" or ")} — be more specific; nothing was changed.`;
      case "not_understood":
        return `Heard “${intent.heard}” — that is not a command I can act on; nothing was changed.`;
      case "dictation":
        return handleDictation(intent.text);
      default:
        return "Nothing was changed.";
    }
  }

  const voiceControl = (
    <VoiceControl
      transcriptionConfigured={transcriptionConfigured}
      mode={voiceMode}
      context={voiceContext}
      threadObject={object}
      threadPosts={thread?.posts ?? []}
      onDictationStart={() => {
        recordingTargetRef.current = composerTarget ?? (object ? lockTarget(object) : null);
        if (!composerTarget) {
          setPendingTranscript(null);
          setVoiceAction(null);
        }
      }}
      onDictation={handleDictation}
      onIntent={handleVoiceIntent}
    />
  );

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
    stopSpeaking();
    setThread(null);
    setComposerTarget(null);
    setDraftReviewing(false);
    if (object) {
      setLoading(true);
    }
  }, [object]);

  const consumedDraft = useRef(0);
  useEffect(() => {
    if (!assistantDraft || !object || consumedDraft.current === assistantDraft.nonce) return;
    consumedDraft.current = assistantDraft.nonce;
    setComposerTarget(lockTarget(object));
    setPendingTranscript({ text: assistantDraft.text, nonce: nextNonce() });
    setVoiceAction(null);
    onAssistantDraftHandled?.();
  }, [assistantDraft, object, onAssistantDraftHandled]);

  usePolling(async (signal) => loadThread(signal), 1500, Boolean(object));

  if (!object) {
    return (
      <aside className="thread-panel thread-panel--empty">
        <div className="empty-thread-mark">⌖</div>
        <p className="eyebrow">OBJECT THREAD</p>
        <h2>No conversation open</h2>
        {assistantDraft && <p className="inline-note">Your AI draft is waiting. Select an enrolled object below, or scan and save a new object, then review the note before posting.</p>}
        <p>Look at an enrolled object, then open its nearby conversation.</p>
        <div className="thread-picker">
          <span>OR BROWSE A DEMO THREAD</span>
          {availableObjects.map((availableObject) => (
            <button key={availableObject.id} onClick={() => onSelectObject(availableObject)}>
              {availableObject.title} <small>Enrolled object</small>
            </button>
          ))}
        </div>
        {voiceControl}
        <EnrollObject
          enrolRequest={enrolRequest}
          onEnrolRequestHandled={() => setEnrolRequest(null)}
          onEnrollmentActiveChange={onEnrollmentActiveChange}
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

      {showImproveHint && (
        <div className="panel-error" role="status">
          <p>New object saved, but Locus hasn’t recognised it in view yet.</p>
          <button disabled={improveBusy} onClick={() => void addViewsToCurrent()}>
            {improveBusy ? "Scanning — keep looking…" : "Look at it & add more views (4s)"}
          </button>
          {improveState && <p>{improveState}</p>}
        </div>
      )}

      <div className="thread-creator-toggle">
        <button className="text-button" onClick={() => setCreatorOpen((open) => !open)}>
          {creatorOpen ? "✕ Close new-object creator" : "＋ Create a new object"}
        </button>
      </div>
      {creatorOpen && (
        <EnrollObject
          enrolRequest={enrolRequest}
          onEnrolRequestHandled={() => setEnrolRequest(null)}
          onEnrollmentActiveChange={onEnrollmentActiveChange}
          onEnrolled={(created) => {
            setCreatorOpen(false);
            onObjectEnrolled?.(created);
            onSelectObject(created);
          }}
        />
      )}

      <div className="thread-body" aria-live="polite">
        {loading && !thread && <div className="panel-state"><span className="spinner" /> Loading conversation…</div>}
        {error && <p className="panel-error">{error}</p>}
        {thread?.posts.map((post) => (
          <Message
            key={post.id}
            post={post}
            onReply={(replyPost) => {
              setPendingTranscript(null);
              setVoiceAction(null);
              setComposerTarget(lockTarget(object, replyPost));
            }}
          />
        ))}
        {thread && thread.posts.length === 0 && (
          <div className="panel-state">No posts yet. Leave the first one.</div>
        )}
      </div>

      {voiceControl}

      {composerTarget && profile ? (
        <Composer
          key={`${composerTarget.object.id}:${composerTarget.parentPost?.id ?? "new"}`}
          target={composerTarget}
          profile={profile}
          transcriptionConfigured={transcriptionConfigured}
          externalTranscript={pendingTranscript}
          voiceAction={voiceAction}
          onReviewChange={setDraftReviewing}
          onCancel={() => {
            setComposerTarget(null);
            setPendingTranscript(null);
            setVoiceAction(null);
          }}
          onSaved={() => {
            setComposerTarget(null);
            setPendingTranscript(null);
            setVoiceAction(null);
            void loadThread();
          }}
        />
      ) : (
        <div className="thread-footer">
          <button
            className="button button--primary button--wide"
            disabled={!profile}
            onClick={() => {
              setPendingTranscript(null);
              setVoiceAction(null);
              setComposerTarget(lockTarget(object));
            }}
          >
            <span aria-hidden="true">＋</span> Leave a post
          </button>
          <span>Thread stays open if the object leaves view.</span>
        </div>
      )}
    </aside>
  );
});
