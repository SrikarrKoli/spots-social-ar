import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { CameraStage } from "./components/CameraStage";
import { ThreadPanel } from "./components/ThreadPanel";
import { Avatar } from "./components/Avatar";
import { usePolling } from "./hooks/usePolling";
import type { Detection, HealthResponse, ObjectSummary, Profile, RecognitionResponse } from "./types";

const NO_DETECTIONS: Detection[] = [];

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [objects, setObjects] = useState<ObjectSummary[]>([]);
  const [profileId, setProfileId] = useState("maya");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recognition, setRecognition] = useState<RecognitionResponse | null>(null);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);
  const [manualIdentityKey, setManualIdentityKey] = useState<string | null>(null);
  const [enrollmentActive, setEnrollmentActive] = useState(false);
  const [newlyCreatedId, setNewlyCreatedId] = useState<string | null>(null);
  const [selectedObject, setSelectedObject] = useState<ObjectSummary | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([api.profiles(controller.signal), api.objects(controller.signal), api.health(controller.signal)])
      .then(([loadedProfiles, loadedObjects, loadedHealth]) => {
        setProfiles(loadedProfiles);
        setObjects(loadedObjects);
        setHealth(loadedHealth);
        if (!loadedProfiles.some((profile) => profile.id === profileId)) {
          setProfileId(loadedProfiles[0]?.id ?? "");
        }
      })
      .catch(() => setRecognitionError("The Locus backend is not reachable."));
    return () => controller.abort();
  }, []);

  usePolling(async (signal) => {
    try {
      const snapshot = await api.recognition(signal);
      setRecognition(snapshot);
      setRecognitionError(null);
      const firstObject = snapshot.detections.find(
        (detection) => detection.object && detection.tier !== "provisional",
      )?.object;
      // A freshly created object clears its improve hint once it is
      // actually recognised at high tier.
      if (
        newlyCreatedId &&
        snapshot.detections.some(
          (detection) =>
            detection.object?.id === newlyCreatedId && detection.tier === "high",
        )
      ) {
        setNewlyCreatedId(null);
      }
      // Never let recognition hijack the screen mid-creation.
      if (firstObject && !enrollmentActive) {
        setSelectedObject((current) => current ?? firstObject);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setRecognitionError(error instanceof Error ? error.message : "Recognition updates stopped.");
      }
    }
  }, 250);

  const currentProfile = useMemo(
    () => profiles.find((profile) => profile.id === profileId) ?? profiles[0] ?? null,
    [profileId, profiles],
  );
  const provisionalDetections = useMemo(() => {
    const detections = recognition?.detections.filter(
      (detection) => detection.object && detection.tier === "provisional",
    );
    return detections?.length ? detections : NO_DETECTIONS;
  }, [recognition]);
  const handleObjectEnrolled = useCallback((created: ObjectSummary) => {
    setObjects((current) => [
      ...current.filter((item) => item.id !== created.id),
      created,
    ]);
    setNewlyCreatedId(created.id);
  }, []);
  const handleConfirmProvisional = useCallback((identityKey: string) => {
    void api.confirmIdentity(identityKey).catch(() => undefined);
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <strong>LOCUS</strong>
            <small>CONVERSATIONS, FOUND</small>
          </div>
        </div>

        <div className="topbar__center">
          <span className="status-pill">
            <i className={health?.camera_status === "ready" ? "is-ready" : ""} />
            {health?.camera_source === "fixture" ? "FIXTURE ONLINE" : health?.camera_status === "ready" ? "GLASSES ONLINE" : "CAMERA OFFLINE"}
          </span>
        </div>

        <label className="profile-switcher">
          <span className="profile-switcher__label">Browsing as</span>
          {currentProfile && <Avatar profile={currentProfile} small />}
          <select value={profileId} onChange={(event) => setProfileId(event.target.value)}>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>{profile.display_name}</option>
            ))}
          </select>
        </label>
      </header>

      <div className="workspace">
        <CameraStage
          recognition={recognition}
          recognitionError={recognitionError}
          manualIdentityKey={manualIdentityKey}
          onManualIdentity={setManualIdentityKey}
          onOpenObject={(detection) => detection.object && setSelectedObject(detection.object)}
          onConfirmIdentity={(detection) => {
            void api.confirmIdentity(detection.identity_key).catch(() => undefined);
          }}
          enrollmentActive={enrollmentActive}
        />
        <ThreadPanel
          object={selectedObject}
          availableObjects={objects}
          onSelectObject={setSelectedObject}
          onObjectEnrolled={handleObjectEnrolled}
          onEnrollmentActiveChange={setEnrollmentActive}
          showImproveHint={Boolean(selectedObject && selectedObject.id === newlyCreatedId)}
          provisionalDetections={provisionalDetections}
          onConfirmProvisional={handleConfirmProvisional}
          profile={currentProfile}
          transcriptionConfigured={health?.transcription_status === "configured"}
        />
      </div>

      <footer className="app-footer">
        <span><i /> Recognition expires when an enrolled object leaves view</span>
        <span>LOCUS PROTOTYPE · LOCAL DEMO</span>
      </footer>
    </main>
  );
}
