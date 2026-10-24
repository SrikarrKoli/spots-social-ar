import { useEffect, useMemo, useRef, useState } from "react";
import { mapFrameBox, mapFramePoint } from "../geometry";
import type { Detection, RecognitionResponse } from "../types";

interface Props {
  recognition: RecognitionResponse | null;
  recognitionError: string | null;
  manualMarkerId: number | null;
  onManualMarker: (markerId: number) => void;
  onOpenObject: (detection: Detection) => void;
}

export function CameraStage({
  recognition,
  recognitionError,
  manualMarkerId,
  onManualMarker,
  onOpenObject,
}: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!stageRef.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setStageSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(stageRef.current);
    return () => observer.disconnect();
  }, []);

  const registered = useMemo(
    () => recognition?.detections.filter((item) => item.object) ?? [],
    [recognition],
  );
  const active =
    registered.find((item) => item.marker_id === manualMarkerId) ?? registered[0];
  const activePosition =
    active && recognition
      ? mapFramePoint(active.center, stageSize, {
          width: recognition.frame_width,
          height: recognition.frame_height,
        })
      : null;
  const frameSize = recognition
    ? { width: recognition.frame_width, height: recognition.frame_height }
    : null;
  const objectStatus = recognition?.object_detection_status;
  const cameraMissing =
    recognition?.status === "unavailable" || recognition?.status === "disabled";

  return (
    <section className="camera-shell" aria-label="Live object view">
      <div className="camera-toolbar">
        <div className="eyebrow-group">
          <span className={`live-dot ${cameraMissing ? "live-dot--off" : ""}`} />
          <span>{recognition?.source === "fixture" ? "Fixture view" : "Live view"}</span>
        </div>
        {objectStatus && objectStatus !== "disabled" && (
          <span
            className={`objects-badge objects-badge--${objectStatus}`}
            title={recognition?.object_detection_message ?? undefined}
          >
            {objectStatus === "ready"
              ? `OBJECTS · ${recognition?.objects.length ?? 0}`
              : objectStatus === "loading"
                ? "OBJECTS · LOADING MODEL"
                : "OBJECTS · UNAVAILABLE"}
          </span>
        )}
        {recognition?.source === "fixture" && (
          <span className="fixture-badge">DEVELOPMENT FIXTURE · REAL DETECTION</span>
        )}
      </div>

      <div className="camera-stage" ref={stageRef}>
        {!cameraMissing && (
          <img
            className="camera-feed"
            src="/api/camera/stream"
            alt="Live camera view used to recognize prepared markers"
          />
        )}

        {!cameraMissing && frameSize && (
          <div className="object-boxes" aria-label="Detected objects">
            {recognition?.objects.map((item, index) => {
              const rect = mapFrameBox(item.box, stageSize, frameSize);
              return (
                <div
                  key={`${item.label}-${index}`}
                  className="object-box"
                  style={{
                    left: rect.x,
                    top: rect.y,
                    width: rect.width,
                    height: rect.height,
                  }}
                >
                  <span className="object-box__label">
                    {item.label} {Math.round(item.confidence * 100)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {(cameraMissing || recognitionError) && (
          <div className="camera-empty">
            <span className="empty-icon">◌</span>
            <h2>Camera view unavailable</h2>
            <p>
              {recognitionError ?? recognition?.message ?? "Waiting for camera status."}
            </p>
            <small>Threads and typed posting are still available.</small>
          </div>
        )}

        {!cameraMissing && recognition?.status === "starting" && (
          <div className="camera-hint">Starting camera…</div>
        )}

        {!cameraMissing && recognition?.status === "ready" && registered.length === 0 && (
          <div className="camera-hint">
            <span className="scan-glyph">⌗</span>
            Look at a prepared object marker
          </div>
        )}

        {active?.object && activePosition && (
          <button
            className="object-peek"
            style={{ left: activePosition[0], top: activePosition[1] }}
            onClick={() => onOpenObject(active)}
          >
            <span className="object-peek__pin" />
            <span className="object-peek__label">NEARBY CONVERSATION</span>
            <strong>{active.object.title}</strong>
            {active.preview ? (
              <>
                <span className="object-peek__meta">
                  {active.preview.author_name} · {active.preview.reply_count} {active.preview.reply_count === 1 ? "reply" : "replies"}
                </span>
                <span>“{active.preview.body}”</span>
              </>
            ) : (
              <span>No posts yet</span>
            )}
            <b>Open thread <span aria-hidden="true">↗</span></b>
          </button>
        )}

        {registered.length > 1 && (
          <div className="visible-objects" aria-label="Visible objects">
            {registered.map((detection) => (
              <button
                key={detection.marker_id}
                className={active?.marker_id === detection.marker_id ? "is-active" : ""}
                onClick={() => onManualMarker(detection.marker_id)}
              >
                {detection.object?.title}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
