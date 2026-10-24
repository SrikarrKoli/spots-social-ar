from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from .objects import ObjectBox, ObjectDetector


@dataclass(slots=True)
class MarkerTrack:
    corners: np.ndarray
    seen_monotonic: float


def marker_dictionary(name: str) -> cv2.aruco.Dictionary:
    dictionary_id = getattr(cv2.aruco, name, None)
    if dictionary_id is None:
        raise ValueError(f"Unsupported ArUco dictionary: {name}")
    return cv2.aruco.getPredefinedDictionary(dictionary_id)


def detect_markers(
    frame: np.ndarray, dictionary_name: str = "DICT_4X4_50"
) -> list[tuple[int, np.ndarray]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dictionary = marker_dictionary(dictionary_name)
    detector = cv2.aruco.ArucoDetector(
        dictionary, cv2.aruco.DetectorParameters()
    )
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return []
    return [
        (int(marker_id), marker_corners.reshape(4, 2).astype(float))
        for marker_id, marker_corners in zip(ids.flatten(), corners, strict=True)
    ]


def video_device_names() -> list[str]:
    """Video devices in the order OpenCV's AVFoundation backend indexes them."""
    try:
        import AVFoundation
    except ImportError:
        return []
    devices = AVFoundation.AVCaptureDevice.devicesWithMediaType_(
        AVFoundation.AVMediaTypeVideo
    )
    # AVFoundation's own order is not stable; OpenCV sorts by uniqueID.
    devices = sorted(devices, key=lambda device: str(device.uniqueID()))
    return [str(device.localizedName()) for device in devices]


def resolve_camera_index(
    name: str | None, fallback_index: int, device_names: list[str] | None = None
) -> int:
    """Return the index of the first device whose name contains `name`."""
    if not name:
        return fallback_index
    names = video_device_names() if device_names is None else device_names
    needle = name.casefold()
    for index, device_name in enumerate(names):
        if needle in device_name.casefold():
            return index
    return fallback_index


class CameraService:
    """Owns one capture loop and shares its latest frame with every client."""

    def __init__(
        self,
        *,
        source: str,
        camera_index: int,
        camera_name: str | None = None,
        fixture_path: Path,
        width: int,
        height: int,
        detection_ttl_ms: int,
        dictionary_name: str,
        object_detector: ObjectDetector | None = None,
        object_interval_ms: int = 150,
    ) -> None:
        if source not in {"camera", "fixture", "disabled"}:
            raise ValueError("Camera source must be camera, fixture, or disabled")
        self.source = source
        self.camera_index = camera_index
        self.camera_name = camera_name
        self.fixture_path = fixture_path
        self.requested_width = width
        self.requested_height = height
        self.detection_ttl_seconds = detection_ttl_ms / 1000
        self.dictionary_name = dictionary_name
        self.object_detector = object_detector
        self.object_interval_seconds = object_interval_ms / 1000

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._object_thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_frame_id = 0
        self._objects: list[ObjectBox] = []
        self._objects_seen_monotonic = 0.0
        self._object_status = "disabled" if object_detector is None else "loading"
        self._object_message: str | None = None
        self._capture: cv2.VideoCapture | None = None
        self._frame_jpeg: bytes | None = None
        self._frame_width = width
        self._frame_height = height
        self._captured_at: datetime | None = None
        self._tracks: dict[int, MarkerTrack] = {}
        self._status = "disabled" if source == "disabled" else "starting"
        self._message: str | None = (
            "Camera disabled by configuration" if source == "disabled" else None
        )

    def start(self) -> None:
        if self.source == "disabled":
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="locus-camera", daemon=True
        )
        self._thread.start()
        if self.object_detector is not None:
            self._object_thread = threading.Thread(
                target=self._run_objects, name="locus-objects", daemon=True
            )
            self._object_thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in (self._thread, self._object_thread):
            if thread is not None:
                thread.join(timeout=2)
        capture = self._capture
        if capture is not None:
            capture.release()
            self._capture = None
        self._thread = None
        self._object_thread = None

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    def _run(self) -> None:
        if self.source == "fixture":
            self._run_fixture()
        else:
            self._run_camera()

    def _run_fixture(self) -> None:
        frame = cv2.imread(str(self.fixture_path))
        if frame is None:
            self._mark_unavailable(
                f"Fixture image not found: {self.fixture_path}"
            )
            return
        while not self._stop.is_set():
            self._process_frame(frame.copy())
            self._stop.wait(0.1)

    def _run_camera(self) -> None:
        self.camera_index = resolve_camera_index(
            self.camera_name, self.camera_index
        )
        capture = cv2.VideoCapture(self.camera_index)
        self._capture = capture
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)
        if not capture.isOpened():
            self._mark_unavailable(
                f"Unable to open camera index {self.camera_index}"
            )
            capture.release()
            self._capture = None
            return

        while not self._stop.is_set():
            success, frame = capture.read()
            if not success:
                self._mark_unavailable("Camera stopped returning frames")
                break
            self._process_frame(frame)

        capture.release()
        self._capture = None

    def _run_objects(self) -> None:
        detector = self.object_detector
        assert detector is not None
        try:
            detector.load()
        except Exception as error:  # noqa: BLE001 - surfaced to the UI
            with self._lock:
                self._object_status = "unavailable"
                self._object_message = f"Object detection failed to load: {error}"
            return
        with self._lock:
            self._object_status = "ready"

        last_frame_id = 0
        while not self._stop.is_set():
            with self._lock:
                frame = self._latest_frame
                frame_id = self._latest_frame_id
            if frame is None or frame_id == last_frame_id:
                self._stop.wait(0.02)
                continue
            last_frame_id = frame_id
            started = time.monotonic()
            try:
                objects = detector.detect(frame)
            except Exception as error:  # noqa: BLE001 - keep the loop alive
                with self._lock:
                    self._object_message = f"Object detection error: {error}"
                objects = []
            with self._lock:
                self._objects = objects
                self._objects_seen_monotonic = time.monotonic()
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.0, self.object_interval_seconds - elapsed))

    def _mark_unavailable(self, message: str) -> None:
        with self._lock:
            self._status = "unavailable"
            self._message = message

    def _process_frame(self, frame: np.ndarray) -> None:
        now_monotonic = time.monotonic()
        detections = detect_markers(frame, self.dictionary_name)

        with self._lock:
            for marker_id, corners in detections:
                previous = self._tracks.get(marker_id)
                smoothed = (
                    previous.corners * 0.6 + corners * 0.4
                    if previous is not None
                    else corners
                )
                self._tracks[marker_id] = MarkerTrack(smoothed, now_monotonic)

            self._expire_tracks(now_monotonic)
            height, width = frame.shape[:2]
            self._frame_width = width
            self._frame_height = height
            self._captured_at = datetime.now(UTC)
            self._latest_frame = frame
            self._latest_frame_id += 1
            self._status = "ready"
            self._message = (
                "Development fixture — real marker detection"
                if self.source == "fixture"
                else None
            )
            success, encoded = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 84]
            )
            if success:
                self._frame_jpeg = encoded.tobytes()

    def _expire_tracks(self, now_monotonic: float) -> None:
        expired = [
            marker_id
            for marker_id, track in self._tracks.items()
            if now_monotonic - track.seen_monotonic > self.detection_ttl_seconds
        ]
        for marker_id in expired:
            del self._tracks[marker_id]

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            self._expire_tracks(time.monotonic())
            detections = []
            for marker_id, track in self._tracks.items():
                corners = track.corners.tolist()
                center = track.corners.mean(axis=0).tolist()
                detections.append(
                    {
                        "marker_id": marker_id,
                        "corners": corners,
                        "center": center,
                    }
                )
            frame_center = (self._frame_width / 2, self._frame_height / 2)
            detections.sort(
                key=lambda item: (
                    (item["center"][0] - frame_center[0]) ** 2
                    + (item["center"][1] - frame_center[1]) ** 2,
                    item["marker_id"],
                )
            )
            objects = (
                [
                    {
                        "label": item.label,
                        "confidence": item.confidence,
                        "box": list(item.box),
                    }
                    for item in self._objects
                ]
                if time.monotonic() - self._objects_seen_monotonic
                <= self.detection_ttl_seconds
                else []
            )
            return {
                "status": self._status,
                "source": self.source,
                "message": self._message,
                "captured_at": self._captured_at,
                "frame_width": self._frame_width,
                "frame_height": self._frame_height,
                "detections": detections,
                "objects": objects,
                "object_detection_status": self._object_status,
                "object_detection_message": self._object_message,
            }

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._frame_jpeg

    def mjpeg_frames(self):
        last_frame: bytes | None = None
        while not self._stop.is_set():
            frame = self.latest_jpeg()
            if frame is not None and frame is not last_frame:
                last_frame = frame
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    + frame
                    + b"\r\n"
                )
            else:
                time.sleep(0.05)
