import { useEffect, useMemo, useRef, useState } from "react";
import { mapFramePoint, zoomedRect } from "../geometry";
import { anchorFor, DEMO_FOCUS, DEMO_IMAGE, DEMO_IMAGE_SIZE, DEMO_ZOOM, FEATURED_MARKER, PINNED_MARKERS, PLACE_NAME } from "../scene";
import { noteCount } from "../threadUtils";
import type { ObjectSummary, Profile, RecognitionResponse, ThreadResponse } from "../types";
import { GlassesToast, MuseEmblem, NoteCard, NoteMarker, type AssistantState } from "./GlassesNote";
import { Icon } from "./Icons";

interface Props {
  recognition: RecognitionResponse | null;
  recognitionError: string | null;
  objects: ObjectSummary[];
  threads: Record<string, ThreadResponse>;
  selectedObject: ObjectSummary | null;
  onSelectObject: (object: ObjectSummary) => void;
  viewer: Profile | null;
  listening: boolean;
  transcriptionConfigured: boolean;
  onPosted: () => void;
  mode: SceneMode;
  onModeChange: (mode: SceneMode) => void;
  overlaysVisible: boolean;
  // Bumped by the demo menu (or ?demo=open) to open the featured note on purpose.
  demoOpenSignal: number;
  onAskAssistant: () => void;
}

export type SceneMode = "demo" | "live";

// The POV card is 240–300px wide: as wide as the margin beside the menu allows.
const CARD_WIDTH = 300;
const MIN_CARD_WIDTH = 240;
const CARD_GAP = 24;

// Keys typed into a field shouldn't move focus between notes.
function typingInField(target: EventTarget | null) {
  return target instanceof HTMLElement && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
}

export function CameraStage({
  recognition,
  recognitionError,
  objects,
  threads,
  selectedObject,
  onSelectObject,
  viewer,
  transcriptionConfigured,
  onPosted,
  mode,
  onModeChange,
  overlaysVisible,
  demoOpenSignal,
  onAskAssistant,
}: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const liveError = mode === "live" && recognition?.status === "unavailable" ? recognition.message : null;
  const [cardOpen, setCardOpen] = useState(() => demoOpenSignal > 0);
  const [toast, setToast] = useState<string | null>(null);
  const [assistantSignal] = useState(0);
  const [assistantState, setAssistantState] = useState<AssistantState>("idle");
  // Which item the wearer is looking at; only their input changes it (default: the featured dish).
  const [focusId, setFocusId] = useState<string | null>(() => selectedObject?.id ?? null);


  useEffect(() => {
    if (!stageRef.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setStageSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(stageRef.current);
    return () => observer.disconnect();
  }, []);

  const registered = useMemo(
    () => recognition?.detections.filter((item) => item.object && item.tier === "high") ?? [],
    [recognition],
  );
  const activeDetection = registered.find((item) => item.object?.id === selectedObject?.id) ?? registered[0];
  useEffect(() => {
    if (mode === "live" && activeDetection?.object) setCardOpen(true);
  }, [mode, activeDetection?.object?.id]);
  const frameSize = recognition ? { width: recognition.frame_width, height: recognition.frame_height } : null;
  const activePosition =
    activeDetection && frameSize ? mapFramePoint(activeDetection.center, stageSize, frameSize) : null;
  const demoRect = zoomedRect(stageSize, DEMO_IMAGE_SIZE, DEMO_ZOOM, DEMO_FOCUS);
  // Notes are pinned with calibrated anchors (fractions of the photo), so they stay aligned as the view resizes.
  const toStage = (object: ObjectSummary): [number, number] => {
    const anchor = anchorFor(object.marker_id);
    return [demoRect.x + anchor.x * demoRect.width, demoRect.y + anchor.y * demoRect.height];
  };
  const withNotes = objects.filter((object) => object.identity_kind === "demo" && noteCount(threads[object.id]) > 0);
  const focused =
    withNotes.find((object) => object.id === focusId) ??
    withNotes.find((object) => object.marker_id === FEATURED_MARKER) ??
    withNotes[0] ??
    null;
  const liveObject = activeDetection?.object ?? null;
  const cardObject = mode === "live" ? liveObject : focused;
  // Pinned dishes always show a marker; the focused one does too, wherever the arrows landed.
  const shownMarkers = mode === "live"
    ? (liveObject && activePosition ? [{ object: liveObject, position: activePosition }] : [])
    : withNotes
        .filter((object) => PINNED_MARKERS.includes(object.marker_id ?? -1) || object.id === focused?.id)
        .map((object) => ({ object, position: toStage(object) }));

  // Demo action: open the requested phone selection, or the featured dish when
  // no selected object with notes is available.
  useEffect(() => {
    if (!demoOpenSignal || mode !== "demo") return;
    const target = withNotes.find((object) => object.id === selectedObject?.id)
      ?? withNotes.find((object) => object.marker_id === FEATURED_MARKER);
    if (!target) return;
    setFocusId(target.id);
    setCardOpen(true);
  }, [demoOpenSignal, withNotes.length > 0, selectedObject?.id]);


  // D-pad style input: arrows move between items, Enter opens, Esc closes.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!overlaysVisible || typingInField(event.target) || mode !== "demo") return;
      if ((event.key === "ArrowRight" || event.key === "ArrowLeft") && withNotes.length > 1 && focused) {
        event.preventDefault();
        const step = event.key === "ArrowRight" ? 1 : -1;
        const index = withNotes.findIndex((object) => object.id === focused.id);
        const next = withNotes[(index + step + withNotes.length) % withNotes.length];
        setFocusId(next.id);
        setCardOpen(false);
        onSelectObject(next);
      } else if ((event.key === "Enter" || event.key === " ") && !cardOpen && document.activeElement === document.body) {
        event.preventDefault();
        setCardOpen(true);
      } else if (event.key === "Escape" && cardOpen) {
        setCardOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overlaysVisible, mode, withNotes, focused, cardOpen, onSelectObject]);

  // Opening a note from the phone ("View through glasses") focuses that item here.
  useEffect(() => {
    if (selectedObject && selectedObject.marker_id === FEATURED_MARKER) setFocusId(selectedObject.id);
  }, [selectedObject?.id]);

  const markerPoint = mode === "live" ? activePosition : focused ? toStage(focused) : null;
  // In the POV demo the card opens in the margin beside the menu on the dish's side, otherwise beside the marker.
  const cardStyle = (() => {
    if (!markerPoint) return undefined;
    const side = mode === "demo" && focused ? anchorFor(focused.marker_id).cardSide ?? "left" : "left";
    const menuRight = demoRect.x + demoRect.width;
    // Leave room for the tallest step (the reply confirmation). A right-side card lines up with its dish.
    const maxTop = Math.max(64, stageSize.height - 440);
    const top = Math.min(Math.max(markerPoint[1] - (side === "right" ? 48 : 120), 64), maxTop);
    const room = mode !== "demo" ? 0 : side === "right" ? stageSize.width - menuRight - CARD_GAP - 16 : demoRect.x - CARD_GAP - 16;
    if (room >= MIN_CARD_WIDTH) {
      const width = Math.min(CARD_WIDTH, room);
      return side === "right" ? { left: menuRight + CARD_GAP, top, width } : { left: 16 + room - width, top, width };
    }
    const left = markerPoint[0] + CARD_GAP + CARD_WIDTH <= stageSize.width - 16 ? markerPoint[0] + CARD_GAP : Math.max(16, markerPoint[0] - CARD_GAP - CARD_WIDTH);
    return { left, top, width: CARD_WIDTH };
  })();

  const card = cardObject && (
    <NoteCard
      key={cardObject.id}
      object={cardObject}
      thread={threads[cardObject.id]}
      viewer={viewer}
      transcriptionConfigured={transcriptionConfigured}
      onClose={() => {
        setCardOpen(false);
        setAssistantState("idle");
      }}
      onPosted={(confirmation) => {
        setToast(confirmation);
        onPosted();
      }}
      assistantSignal={assistantSignal}
      onAssistantStateChange={setAssistantState}
    />
  );

  const activateAssistant = onAskAssistant;

  return (
    <section className="camera-shell" aria-label="Spots glasses prototype">
      <div className={`camera-stage camera-stage--${mode}`} ref={stageRef}>
        {mode === "demo" && <span className="scene-demo-label">Restaurant demo · sample scene and notes</span>}
        {mode === "demo" ? (
          <>
            <img
              className="pov-image pov-image--menu"
              src={DEMO_IMAGE}
              style={{ left: demoRect.x, top: demoRect.y, width: demoRect.width, height: demoRect.height }}
              alt={`First-person view of a ${PLACE_NAME} menu on a wooden restaurant table`}
            />
          </>
        ) : (
          <img className="pov-image pov-image--live" src="/api/camera/stream" alt="Live Brio camera view" />
        )}


        {overlaysVisible && shownMarkers.length > 0 && (
          <div className="ar-annotations" aria-label="Notes in view">
            {shownMarkers.map(({ object, position }) => (
              <NoteMarker
                key={object.id}
                object={object}
                thread={threads[object.id]}
                position={position}
                open={cardOpen && object.id === cardObject?.id}
                focused={!cardOpen && object.id === cardObject?.id}
                onOpen={() => {
                  onSelectObject(object);
                  if (object.id === cardObject?.id) {
                    setCardOpen((open) => !open);
                  } else {
                    setFocusId(object.id);
                    setCardOpen(true);
                  }
                }}
              />
            ))}
            {cardOpen && <div className="g-card-slot" style={cardStyle}>{card}</div>}
          </div>
        )}

        {toast && <GlassesToast message={toast} onDone={() => setToast(null)} />}

        {overlaysVisible && (
          <div className={`muse-control muse-control--${assistantState}`}>
            <button
              className="muse-control__button"
              onClick={activateAssistant}
              aria-label={assistantState === "idle" ? "Talk to Spots" : `Spots: ${assistantState}`}
              title="Voice assistant"
            >
              <span className="muse-control__ring" aria-hidden="true" />
              <MuseEmblem />
              <span className="muse-control__status" role="status" aria-live="polite">
                {assistantState === "listening" ? "Listening…" : assistantState === "thinking" ? "Thinking…" : assistantState === "speaking" ? "Speaking…" : assistantState === "error" ? "Try again" : "Talk to Spots"}
              </span>
              <span className="muse-control__wave" aria-hidden="true"><i /><i /><i /><i /></span>
            </button>
          </div>
        )}

        {mode === "live" && (liveError || recognitionError) && (
          <div className="camera-empty">
            <span className="empty-icon"><Icon name="camera" /></span>
            <h2>Live camera unavailable</h2>
            <p>{liveError ?? recognitionError}</p>
            <button onClick={() => onModeChange("demo")}>Return to restaurant demo</button>
          </div>
        )}
      </div>
    </section>
  );
}
