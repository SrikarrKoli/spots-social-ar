import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { AssistantPanel } from "./components/AssistantPanel";
import { CameraStage } from "./components/CameraStage";
import type { AssistantState } from "./components/GlassesNote";
import { Icon, type IconName } from "./components/Icons";
import { MessagesView } from "./components/MessagesView";
import { usePolling } from "./hooks/usePolling";
import { useThreads } from "./hooks/useThreads";
import { decorateObjects } from "./scene";
import type { HealthResponse, ObjectSummary, Profile, RecognitionResponse } from "./types";

type View = "ar" | "instagram";
const RAIL: IconName[] = ["home", "search", "explore", "reels", "messages", "heart", "create"];

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [objects, setObjects] = useState<ObjectSummary[]>([]);
  const [profileId, setProfileId] = useState("maya");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recognition, setRecognition] = useState<RecognitionResponse | null>(null);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);
  const [selectedObject, setSelectedObject] = useState<ObjectSummary | null>(null);
  const [view, setView] = useState<View>(() => window.location.hash === "#glasses" ? "ar" : "instagram");
  const [assistant, setAssistant] = useState<{target: ObjectSummary | null; prompt: string} | null>(null);
  const [assistantState, setAssistantState] = useState<AssistantState>("idle");
  const { threads, reload: reloadThreads } = useThreads(objects);

  useEffect(() => {
    const controller = new AbortController();
    void api.profiles(controller.signal).then(setProfiles).catch(() => undefined);
    return () => controller.abort();
  }, []);
  usePolling(async signal => {
    const [loaded, status] = await Promise.all([api.objects(signal), api.health(signal)]);
    const decorated = decorateObjects(loaded);
    setObjects(decorated); setHealth(status);
    setSelectedObject(current => decorated.find(item => item.id === current?.id) ?? decorated.find(item => item.marker_id === 7) ?? decorated[0] ?? null);
  }, 5000);
  usePolling(async signal => {
    try { setRecognition(await api.recognition(signal)); setRecognitionError(null); }
    catch (error) { if (!signal.aborted) setRecognitionError(error instanceof Error ? error.message : "Camera updates stopped."); }
  }, 250);
  useEffect(() => {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${view === "ar" ? "#glasses" : "#instagram"}`);
  }, [view]);
  const visibleObject = recognition?.detections.find(item => item.tier === "high" && item.object)?.object ?? null;
  const viewer = useMemo(() => profiles.find(profile => profile.id === profileId) ?? profiles[0] ?? null, [profiles, profileId]);
  const closeAssistant = () => { setAssistant(null); setAssistantState("idle"); };
  const saved = (object: ObjectSummary) => {
    setObjects(current => decorateObjects([...current.filter(item => item.id !== object.id), object]));
    setSelectedObject(object); void reloadThreads();
  };
  return <main className={`app-shell app-shell--${view}`}>
    {view === "instagram" ? <section className="instagram-frame" aria-label="Instagram view">
      <nav className="instagram-rail" aria-label="Instagram (illustrative)">
        <Icon name="instagram" className="instagram-rail__logo" />
        {RAIL.map(icon => <span key={icon} className={`instagram-rail__item ${icon === "messages" ? "is-active" : ""}`}><Icon name={icon} filled={icon === "messages"} /></span>)}
      </nav>
      <MessagesView profile={viewer} profiles={profiles} onSwitchProfile={setProfileId} objects={objects} threads={threads} selectedObject={selectedObject} transcriptionConfigured={health?.transcription_status === "configured"}
        onOpenLens={object => { setSelectedObject(object); setView("ar"); closeAssistant(); }} onPosted={() => void reloadThreads()} />
    </section> : <section className="ar-layout">
      <CameraStage recognition={recognition} recognitionError={recognitionError} objects={objects} threads={threads} selectedObject={selectedObject} onSelectObject={setSelectedObject} viewer={viewer}
        listening={health?.camera_status === "ready"} transcriptionConfigured={health?.transcription_status === "configured"} onPosted={() => void reloadThreads()}
        mode="live" onModeChange={() => undefined} overlaysVisible demoOpenSignal={0} assistantOpen={assistant !== null} assistantPhase={assistantState}
        onAskAssistant={(target, prompt = "") => { if (assistant) { closeAssistant(); return; } setAssistant({target: target ?? visibleObject, prompt}); }} />
    </section>}
    {assistant && view === "ar" && <AssistantPanel key={`${profileId}:${assistant.prompt}`} lens autoListen={!assistant.prompt} initialInput={assistant.prompt} onClose={closeAssistant}
      onPhaseChange={phase => setAssistantState(phase === "starting" ? "listening" : phase === "transcribing" ? "thinking" : phase)}
      health={health} object={assistant.target ?? visibleObject} authorId={profileId} onSaved={saved} />}
    <div className="proto-switch"><div className="view-switch" role="tablist" aria-label="Choose view">
      {([['instagram','Phone'],['ar','Glasses']] as const).map(([id,label]) => <button key={id} role="tab" aria-selected={view === id} className="view-switch__option" onClick={() => { setView(id); closeAssistant(); }}>{label}</button>)}
    </div></div>
  </main>;
}
