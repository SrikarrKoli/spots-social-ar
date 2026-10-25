import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { MemoryRecall } from "./MemoryRecall";
import { microphoneErrorMessage, useVoiceRecorder } from "../hooks/useVoiceRecorder";
import { speakText, stopSpeaking } from "../speech";
import type { AssistantMessage, HealthResponse, ObjectSummary, Post } from "../types";

type Phase = "idle" | "starting" | "listening" | "transcribing" | "thinking" | "speaking";

export function AssistantPanel({ health, object, authorId, onSaved, lens = false, autoListen = false, initialInput = "", onPhaseChange, onClose }: { health: HealthResponse | null; object: ObjectSummary | null; authorId: string; onSaved: (object: ObjectSummary) => void; onClose?: () => void; lens?: boolean; autoListen?: boolean; initialInput?: string; onPhaseChange?: (phase: Phase) => void }) {
  const recorder = useVoiceRecorder();
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState(initialInput);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [handsFree, setHandsFree] = useState(false);
  const [camera, setCamera] = useState(true);
  const [speak, setSpeak] = useState(true);
  const [lastContext, setLastContext] = useState("");
  const [awaitingNote, setAwaitingNote] = useState(false);
  const awaitingNoteRef = useRef(false);
  const pendingMemory = useRef({ awaitingName: false, pendingTitle: "", pendingBody: "" });
  const deletion = useRef<{ pendingDeleteIds: number[]; lastNoteId?: number; deletionId?: string }>({ pendingDeleteIds: [] });
  const commentState = useRef({ awaitingDescription: false, pendingEditIds: [] as number[], pendingEditBody: "" });
  const [memoryRevision, setMemoryRevision] = useState(0);
  const [awaitingName, setAwaitingName] = useState(false);
  const [savedNote, setSavedNote] = useState<{ note: Post; object: ObjectSummary } | null>(null);
  const pendingRequest = useRef<{ text: string; id: string } | null>(null);
  const [retryText, setRetryText] = useState<string | null>(null);
  const history = useRef<AssistantMessage[]>([]);
  const running = useRef(false);
  const finishing = useRef(false);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const turn = useRef({ camera, speak, objectId: object?.id ?? null });
  const latestOptions = useRef({ camera, speak, objectId: object?.id ?? null });
  latestOptions.current = { camera, speak, objectId: object?.id ?? null };
  const finishRef = useRef<(heard: boolean) => Promise<void>>(async () => undefined);
  const listenRef = useRef<() => Promise<void>>(async () => undefined);
  const recorderRef = useRef(recorder);
  recorderRef.current = recorder;
  const messagesRef = useRef<HTMLDivElement>(null);
  const busy = phase !== "idle";
  const ready = health?.assistant_status === "ready";
  const voiceReady = ready && health?.transcription_status === "configured";

  const autoStarted = useRef(false);
  useEffect(() => { onPhaseChange?.(phase); }, [phase, onPhaseChange]);
  useEffect(() => {
    if (!autoListen || !voiceReady || autoStarted.current) return;
    autoStarted.current = true;
    generation.current += 1;
    running.current = true; setHandsFree(true);
    void listenRef.current();
  }, [autoListen, voiceReady]);
  useEffect(() => { if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight; }, [messages, phase]);
  useEffect(() => () => {
    running.current = false;
    generation.current += 1;
    controller.current?.abort();
    stopSpeaking();
    void recorderRef.current.stop();
  }, []);

  function stop() {
    running.current = false;
    generation.current += 1;
    controller.current?.abort();
    stopSpeaking();
    void recorderRef.current.stop();
    setHandsFree(false);
    setPhase("idle");
  }

  async function answer(text: string, token: number) {
    setPhase("thinking");
    controller.current = new AbortController();
    const options = turn.current;
    const previous = history.current;
    setMessages([...previous, { role: "user", content: text }]);
    if (pendingRequest.current?.text !== text) pendingRequest.current = { text, id: crypto.randomUUID() };
    setRetryText(text);
    const result = await api.askAssistant(text, previous, options.objectId, options.camera, controller.current.signal,
      { authorId, requestId: pendingRequest.current.id, awaitingNote: awaitingNoteRef.current, ...pendingMemory.current, ...deletion.current, ...commentState.current });
    if (generation.current !== token) return;
    pendingRequest.current = null;
    setRetryText(null);
    commentState.current = { awaitingDescription: result.awaiting_description, pendingEditIds: result.pending_edit_ids ?? [], pendingEditBody: result.pending_edit_body ?? "" };
    awaitingNoteRef.current = result.awaiting_note;
    setAwaitingNote(result.awaiting_note);
    setAwaitingName(result.awaiting_name);
    pendingMemory.current = { awaitingName: result.awaiting_name, pendingTitle: result.pending_title, pendingBody: result.pending_body };
    deletion.current.pendingDeleteIds = result.pending_delete_ids ?? [];
    if (result.deletion_id) deletion.current.deletionId = result.deletion_id;
    if (result.saved_note) deletion.current.lastNoteId = result.saved_note.id;
    if (result.memory_changed) {
      setMemoryRevision((current) => current + 1);
      setSavedNote((current) => current && result.deleted_note_ids?.includes(current.note.id) ? null : current);
    }
    if (result.saved_object) {
      onSaved(result.saved_object);
      const updated = result.saved_object;
      setSavedNote((current) => current?.object.id === updated.id ? { ...current, object: updated } : current);
    }
    if (result.saved_note && result.saved_object) {
      setSavedNote({ note: result.saved_note, object: result.saved_object });

    }
    const next: AssistantMessage[] = [...previous, { role: "user", content: text }, { role: "assistant", content: result.text }];
    history.current = next.slice(-12);
    setMessages(next.slice(-12));
    setLastContext(result.camera_used
      ? `${result.camera_source === "fixture" ? "Test image" : "Camera snapshot"} · ${result.captured_at ? new Date(result.captured_at).toLocaleTimeString() : "now"}`
      : "Answered without a camera image");
    if (options.speak || result.read_aloud) {
      setPhase("speaking");
      await speakText(result.text);
    }
    if (generation.current !== token) return;
    setPhase("idle");
    if (running.current) {
      // Keep the microphone closed through playback and its acoustic tail.
      await new Promise((resolve) => window.setTimeout(resolve, 650));
      if (running.current && generation.current === token) await listenRef.current();
    }
  }

  async function listen() {
    finishing.current = false;
    const token = generation.current;
    setError(null);
    setPhase("starting");
    turn.current = latestOptions.current;
    stopSpeaking();
    try {
      await recorderRef.current.start(running.current ? (heard) => { void finishRef.current(heard); } : undefined);
      if (generation.current !== token) { await recorderRef.current.stop(); return; }
      setPhase("listening");
    } catch (cause) {
      if (generation.current !== token) return;
      running.current = false; setHandsFree(false); setPhase("idle");
      setError(microphoneErrorMessage(cause));
    }
  }
  listenRef.current = listen;

  async function finish(heard: boolean) {
    if (finishing.current) return;
    finishing.current = true;
    const token = generation.current;
    setPhase("transcribing");
    try {
      const blob = await recorderRef.current.stop();
      if (generation.current !== token) return;
      if (!heard) {
        stop();
        setError("No speech heard. Check your microphone, then start again.");
        return;
      }
      controller.current = new AbortController();
      const result = await api.transcribe(blob, controller.current.signal);
      if (generation.current !== token) return;
      if (/^(stop|stop listening|end conversation|goodbye)[.!?]*$/i.test(result.text.trim())) {
        stop(); return;
      }
      await answer(result.text, token);
    } catch (cause) {
      if (generation.current !== token) return;
      running.current = false; setHandsFree(false); setPhase("idle");
      setError(cause instanceof Error ? cause.message : "Could not process that turn. Try again.");
    }
  }
  finishRef.current = finish;

  async function sendTyped() {
    if (!input.trim() || busy) return;
    const text = input.trim();
    setError(null);
    turn.current = latestOptions.current;
    const token = ++generation.current;
    try { await answer(text, token); if (generation.current === token) setInput(""); }
    catch (cause) {
      if (generation.current !== token) return;
      setPhase("idle");
      setError(cause instanceof Error ? cause.message : "Could not answer. Your question is still here.");
    }
  }

  if (lens) return <section className={`voice-hud voice-hud--${phase}`} aria-label="Meta AI conversation">
    <header className="voice-hud__header"><span className="voice-hud__orb" aria-hidden="true" /><strong>{phase === "listening" ? "Listening" : phase === "starting" ? "Opening microphone" : phase === "thinking" ? "Thinking" : phase === "transcribing" ? "Transcribing" : phase === "speaking" ? "Meta AI" : "Meta AI"}</strong><button aria-label="Close voice conversation" onClick={onClose}>×</button></header>
    <div className="voice-hud__captions" aria-live="polite" ref={messagesRef}>
      {!messages.length && !error && <p className="voice-hud__hint">{phase === "listening" ? "Go ahead. I’m listening…" : phase === "starting" ? "Getting ready…" : initialInput ? "Ask about this object." : "Ask about what you see, or say “take a note”."}</p>}
      {messages.slice(-2).map((message,index) => <p className={`voice-hud__caption voice-hud__caption--${message.role}`} key={index}><span>{message.role === "user" ? "You" : "Meta AI"}</span>{message.content}</p>)}
      {phase === "transcribing" && <p className="voice-hud__hint">Turning your words into text…</p>}
      {phase === "thinking" && <p className="voice-hud__hint">Thinking…</p>}
      {error && <p className="voice-hud__error" role="alert">{error}</p>}
    </div>
    <footer className="voice-hud__actions">
      {phase === "listening" && <button onClick={() => void finish(true)}>Finish speaking</button>}
      {busy && <button onClick={stop}>Stop</button>}
      {!busy && <button disabled={!voiceReady} onClick={() => { generation.current += 1; running.current = true; setHandsFree(true); void listen(); }}>Speak</button>}
      {error && retryText && !busy && <button onClick={() => { setError(null); const token = ++generation.current; void answer(retryText,token).catch((cause: Error) => { setPhase("idle"); setError(cause.message); }); }}>Retry</button>}
    </footer>
    {(!busy && (initialInput || error)) && <form className="voice-hud__input" onSubmit={event => { event.preventDefault(); void sendTyped(); }}><input aria-label="Ask Spots" placeholder="Type a message…" value={input} onChange={event => setInput(event.target.value)} maxLength={2000}/><button disabled={!ready || !input.trim()}>Ask</button></form>}
  </section>;

  return (
    <aside className={`thread-panel assistant-panel ${lens ? "assistant-panel--lens" : ""}`} aria-label={lens ? "Meta AI conversation" : "Talk to Spots"}>
      <header className="thread-header"><div><p className="eyebrow">{lens ? "SPOTS FOR GLASSES" : "YOUR CAMERA COMPANION"}</p><h2>{lens ? "Meta AI" : "Talk to Spots"}</h2>
        <p>Say “add a comment saying …”, “read past comments”, or “change my last comment to …”.</p></div></header>
      <details className="assistant-options" open={lens ? undefined : true}><summary>Voice & camera settings</summary><div className="assistant-settings">
        <span className="inline-note">{ready ? `Local AI · ${health.assistant_model}${health.llm_parser_enabled ? " · LLM speech parsing" : ""}` : health?.assistant_message ?? "Connecting to local AI…"}</span>
        {object && <span className="inline-note">Looking at: {object.title}</span>}
        <label><input type="checkbox" checked={camera} disabled={busy} onChange={(e) => setCamera(e.target.checked)} /> Include current camera view with each question</label>
        <label><input type="checkbox" checked={speak} disabled={busy} onChange={(e) => setSpeak(e.target.checked)} /> Speak answers through your Mac’s sound output</label>
        <label className="device-select"><span>MICROPHONE</span><select aria-label="Conversation microphone" value={recorder.deviceId} disabled={busy} onChange={(e) => recorder.setDeviceId(e.target.value)}>
          <option value="">System default microphone</option>
          {recorder.devices.filter((d) => d.deviceId).map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || "Microphone"}</option>)}
        </select></label>
        <button className="text-button" disabled={busy} onClick={() => { void speakText("Spots is ready. You should hear me through your MacBook speakers.").catch((e: Error) => setError(e.message)); }}>Test speakers</button>
      </div></details>
      <MemoryRecall object={object} revision={(savedNote?.note.id ?? 0) + memoryRevision} />
      {savedNote && <div className="memory-saved" role="status"><strong>Saved · {savedNote.object.title}</strong><p>{savedNote.note.body}</p><small>Stored on this Mac. Find it again in Saved objects & memories.</small></div>}
      <div className="thread-body assistant-messages" aria-live="polite" ref={messagesRef}>
        {messages.length === 0 && <div className="panel-state">Try “What am I looking at?” then ask a follow-up.<br />Say “take a note” to save a memory. Ordinary questions stay in this chat.</div>}
        {messages.map((message, index) => <article className={`assistant-message assistant-message--${message.role}`} key={index}><strong>{message.role === "user" ? "You" : lens ? "Meta AI" : "Spots"}</strong><p>{message.content}</p></article>)}
        {busy && <p className="assistant-phase" role="status">{({ idle: "", starting: "Opening microphone…", listening: handsFree ? "Listening… pause when you finish your question." : "Listening… press Finish question when ready.", transcribing: "Turning your speech into text…", thinking: "Looking and thinking…", speaking: "Spots is speaking…" })[phase]}</p>}

      </div>
      <div className="assistant-controls">
        {lastContext && !lens && <small>{lastContext}</small>}
        {awaitingName && <p className="inline-note">Your note is held for this conversation. Tell me the object’s name to finish saving.</p>}
        {awaitingNote && <p className="inline-note">Ready for your note. Keep the object centered and tell me what to remember.</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {error && retryText && !busy && <button className="text-button" onClick={() => {
          setError(null); const token = ++generation.current;
          void answer(retryText, token).catch((cause: Error) => { setPhase("idle"); setError(cause.message); });
        }}>Retry last request</button>}
        <div className="assistant-buttons">
          {phase === "listening" ? <button className="button button--primary" onClick={() => void finish(true)}>Finish question</button> :
            <button className="button button--primary" disabled={!voiceReady || busy} onClick={() => { generation.current += 1; void listen(); }}>Ask by voice</button>}
          {!handsFree && <button className="button button--ghost" disabled={!voiceReady || busy} onClick={() => { generation.current += 1; running.current = true; setHandsFree(true); void listen(); }}>Start hands-free</button>}
          {busy && <button className="button button--ghost" onClick={stop}>Stop</button>}
        </div>
        <small>Hands-free listens after each answer. Say “stop listening” during your turn, or press Stop. The mic pauses while Spots speaks.</small>
        <form onSubmit={(e) => { e.preventDefault(); void sendTyped(); }} className="assistant-input">
          <input aria-label="Ask Spots" placeholder="Or type a question…" value={input} maxLength={2000} disabled={busy} onChange={(e) => setInput(e.target.value)} />
          <button className="button button--primary" disabled={!ready || busy || !input.trim()}>Ask</button>
        </form>
        <button className="text-button" disabled={busy} onClick={() => { history.current = []; setMessages([]); setLastContext(""); awaitingNoteRef.current = false; setAwaitingNote(false); setAwaitingName(false); pendingMemory.current = { awaitingName: false, pendingTitle: "", pendingBody: "" }; pendingRequest.current = null; setRetryText(null); setSavedNote(null); deletion.current = { pendingDeleteIds: [] }; commentState.current = { awaitingDescription: false, pendingEditIds: [], pendingEditBody: "" }; }}>New conversation</button>
      </div>
    </aside>
  );
}
