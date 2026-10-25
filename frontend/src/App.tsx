import { useEffect, useMemo, useState } from "react";
import { AssistantPanel } from "./components/AssistantPanel";
import { ThreadPanel } from "./components/ThreadPanel";
import { decorateObjects } from "./scene";
import { api } from "./api";
import { CameraStage, type SceneMode } from "./components/CameraStage";
import { Icon, type IconName } from "./components/Icons";
import { MessagesView } from "./components/MessagesView";
import { usePolling } from "./hooks/usePolling";
import { useThreads } from "./hooks/useThreads";
import type { HealthResponse, ObjectSummary, Profile, RecognitionResponse } from "./types";

type View = "ar" | "instagram";

const VIEWS: { id: View; icon: IconName; label: string; hint: string }[] = [
  { id: "instagram", icon: "instagram", label: "Phone", hint: "How friends see it in their DMs" },
  { id: "ar", icon: "glasses", label: "Glasses", hint: "What you see through the glasses" },
];

const INSTAGRAM_RAIL: IconName[] = ["home", "search", "explore", "reels", "messages", "heart", "create"];

function viewFromHash(): View {
  return window.location.hash === "#instagram" || window.location.hash === "#messages" ? "instagram" : window.location.hash === "#glasses" ? "ar" : "instagram";
}

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [objects, setObjects] = useState<ObjectSummary[]>([]);
  // The seeded restaurant notes belong to Vishal (maya), so the demo opens as
  // Aneesh (theo). Replies then read as a real exchange instead of a self-reply.
  const [profileId, setProfileId] = useState("maya");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recognition, setRecognition] = useState<RecognitionResponse | null>(null);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);
  const [selectedObject, setSelectedObject] = useState<ObjectSummary | null>(null);
  const [view, setView] = useState<View>(viewFromHash);
  const { threads, reload: reloadThreads } = useThreads(objects);
  const [sceneMode, setSceneMode] = useState<SceneMode>("live");
  const [overlaysVisible, setOverlaysVisible] = useState(true);
  const [tools, setTools] = useState<"assistant" | "thread" | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // ?demo=open opens the featured note on load, so judges see the idea straight away.
  const [demoOpenSignal, setDemoOpenSignal] = useState(() => (new URLSearchParams(window.location.search).get("demo") === "open" ? 1 : 0));

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.profiles(controller.signal), api.objects(controller.signal), api.health(controller.signal)])
      .then(([loadedProfiles, loadedObjects, loadedHealth]) => {
        const demoProfiles = loadedProfiles;
        loadedObjects = decorateObjects(loadedObjects);
        setProfiles(demoProfiles);
        setObjects(loadedObjects);
        setHealth(loadedHealth);
        setSelectedObject(
          () => loadedObjects.find((object) => object.marker_id === 7) ?? loadedObjects[0] ?? null,
        );
        if (!demoProfiles.some((profile) => profile.id === profileId)) {
          setProfileId(demoProfiles[0]?.id ?? "");
        }
      })
      .catch(() => setRecognitionError("The Spots demo server is not reachable."));
    return () => controller.abort();
  }, []);

  usePolling(async (signal) => {
    try {
      const snapshot = await api.recognition(signal);
      setRecognition(snapshot);
      setRecognitionError(null);
      const firstObject = snapshot.detections.find((detection) => detection.object)?.object;
      if (firstObject) setSelectedObject((current) => current ?? firstObject);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setRecognitionError(error instanceof Error ? error.message : "Recognition updates stopped.");
      }
    }
  }, 250);

  usePolling(async signal => {
    const [loaded, status] = await Promise.all([api.objects(signal), api.health(signal)]);
    const decorated = decorateObjects(loaded);
    setObjects(decorated); setHealth(status);
    setSelectedObject(current => decorated.find(item => item.id === current?.id) ?? decorated[0] ?? null);
  }, 5000);
  const visibleObject = recognition?.detections.find(item => item.tier === "high" && item.object)?.object ?? null;
  const onSaved = (object: ObjectSummary) => {
    setObjects(current => decorateObjects([...current.filter(item => item.id !== object.id), object]));
    setSelectedObject(object); void reloadThreads();
  };
  const currentProfile = useMemo(
    () => profiles.find((profile) => profile.id === profileId) ?? profiles[0] ?? null,
    [profileId, profiles],
  );

  useEffect(() => {
    // Keep the query string (e.g. ?demo=open) when switching views.
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${view === "instagram" ? "#instagram" : "#glasses"}`);
  }, [view]);

  // Switching people keeps the current view, so Aneesh can see Vishal's notes in AR straight away.
  const switchProfile = (nextProfileId: string) => {
    setProfileId(nextProfileId);
    setSelectedObject(objects.find((object) => object.marker_id === 7) ?? objects[0] ?? null);
  };

  const openLens = (object: ObjectSummary) => {
    setSelectedObject(object);
    setView("ar");
    setSceneMode(object.identity_kind === "demo" ? "demo" : "live");
    setDemoOpenSignal((count) => count + 1);
  };

  const cameraReady = health?.camera_status === "ready" && recognition?.status === "ready";
  const transcriptionConfigured = health?.transcription_status === "configured";

  return (
    <main className={`app-shell app-shell--${view}`}>
      {view === "instagram" ? (
        <section className="instagram-frame" aria-label="Instagram view">
          <nav className="instagram-rail" aria-label="Instagram (illustrative)">
            <Icon name="instagram" className="instagram-rail__logo" />
            {INSTAGRAM_RAIL.map((icon) => (
              <span key={icon} className={`instagram-rail__item ${icon === "messages" ? "is-active" : ""}`}>
                <Icon name={icon} filled={icon === "messages"} />
              </span>
            ))}
          </nav>
          <MessagesView
            profile={currentProfile}
            profiles={profiles}
            onSwitchProfile={switchProfile}
            objects={objects}
            threads={threads}
            selectedObject={selectedObject}
            transcriptionConfigured={transcriptionConfigured}
            onOpenLens={openLens}
            onPosted={() => void reloadThreads()}
          />
        </section>
      ) : (
        <section className="ar-layout">
          <CameraStage
            onAskAssistant={() => setTools("assistant")}
            recognition={recognition}
            recognitionError={recognitionError}
            objects={objects}
            threads={threads}
            selectedObject={selectedObject}
            onSelectObject={setSelectedObject}
            viewer={currentProfile}
            listening={cameraReady}
            transcriptionConfigured={transcriptionConfigured}
            onPosted={() => void reloadThreads()}
            mode={sceneMode}
            onModeChange={setSceneMode}
            overlaysVisible={overlaysVisible}
            demoOpenSignal={demoOpenSignal}
          />
        </section>
      )}
      {tools && <aside className="tools-drawer" aria-label="Spots tools">
        <div className="tools-toolbar">
          <button onClick={() => setTools("assistant")}>Talk to Spots</button>
          <button onClick={() => setTools("thread")}>Saved memories</button>
          <button aria-label="Close Spots tools" onClick={() => setTools(null)}>×</button>
        </div>
        {tools === "assistant" ? <AssistantPanel health={health} object={visibleObject} authorId={profileId} onSaved={onSaved} /> :
          <ThreadPanel object={selectedObject} availableObjects={objects} onSelectObject={setSelectedObject} onObjectEnrolled={onSaved} profile={currentProfile} transcriptionConfigured={transcriptionConfigured} provisionalDetections={recognition?.detections.filter(item => item.tier === "provisional")} onConfirmProvisional={key => { void api.confirmIdentity(key); }} />}
      </aside>}
      {/* Presenter controls: one small floating switch, so both views run edge to edge. */}
      <div className="proto-switch">
        <button className="spots-tools-trigger" onClick={() => setTools("assistant")}>Talk to Spots</button>
        <select className="object-library-select" aria-label="Choose saved object" value={selectedObject?.id ?? ""} onChange={event => setSelectedObject(objects.find(item => item.id === event.target.value) ?? null)}>
          {objects.map(object => <option key={object.id} value={object.id}>{object.identity_kind === "demo" ? "Demo · " : ""}{object.title}</option>)}
        </select>
        {view === "ar" && (
          <div className="demo-menu">
            <button className="demo-menu__trigger" aria-label="Demo options" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
              <Icon name="settings" />
            </button>
            {menuOpen && (
              <div className="demo-menu__panel" role="menu">
                <label className="demo-menu__persona">
                  <span>Viewing as</span>
                  <strong>{currentProfile?.display_name ?? "…"}</strong>
                  <Icon name="chevronDown" />
                  <select aria-label="Switch demo person" value={profileId} onChange={(event) => switchProfile(event.target.value)}>
                    {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}
                  </select>
                </label>
                <button role="menuitemradio" aria-checked={sceneMode === "demo"} onClick={() => setSceneMode("demo")}>Restaurant demo scene</button>
                <button role="menuitemradio" aria-checked={sceneMode === "live"} onClick={() => setSceneMode("live")}>Live camera</button>
                <button role="menuitem" onClick={() => {
                  const featured = objects.find((object) => object.marker_id === 7);
                  if (featured) setSelectedObject(featured);
                  setSceneMode("demo");
                  setOverlaysVisible(true);
                  setDemoOpenSignal((count) => count + 1);
                  setMenuOpen(false);
                }}>Open featured note</button>
                <button role="menuitem" onClick={() => setOverlaysVisible((visible) => !visible)}>{overlaysVisible ? "Hide notes" : "Show notes"}</button>
                <button role="menuitem" onClick={() => { setMenuOpen(false); void document.querySelector(".camera-stage")?.requestFullscreen?.(); }}>Full screen</button>
              </div>
            )}
          </div>
        )}
        <div className="view-switch" role="tablist" aria-label="Choose view">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              role="tab"
              aria-selected={view === item.id}
              className="view-switch__option"
              onClick={() => { setView(item.id); setMenuOpen(false); }}
              title={item.hint}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
