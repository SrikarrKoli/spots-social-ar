from __future__ import annotations

import threading
import time
import sys
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Callable

import cv2
import numpy as np

from .recognition import ArucoRecognizer, Recognizer, detect_markers, marker_dictionary

__all__ = ["CameraService", "EnrollmentCapture", "detect_markers", "marker_dictionary", "select_enrollment_views"]

# A high-tier sighting must repeat before it is published, and a
# provisional (medium-tier) sighting must repeat more — single-frame
# false positives never reach the UI.
CONFIRM_HITS_HIGH = 2
CONFIRM_HITS_PROVISIONAL = 3
# Self-improving view bank: only high-confidence, confirmed tracks bank
# new angles, at most one banked view per identity every few seconds and
# only when the viewpoint actually moved.
BANK_MIN_CONFIDENCE = 0.5
BANK_INTERVAL_SECONDS = 3.0
BANK_MIN_CORNER_SHIFT_PX = 25.0
BANK_PERSIST_QUEUE_SIZE = 4


@dataclass(slots=True)
class MarkerTrack:
    corners: np.ndarray
    confidence: float
    method: str
    seen_monotonic: float
    hits: int = 1
    tier: str = "high"

    @property
    def confirmed(self) -> bool:
        required = (
            CONFIRM_HITS_HIGH if self.tier == "high" else CONFIRM_HITS_PROVISIONAL
        )
        return self.hits >= required


def _centre_crop(frame: np.ndarray, margin: float = 0.15) -> np.ndarray:
    height, width = frame.shape[:2]
    x0, x1 = int(width * margin), int(width * (1 - margin))
    y0, y1 = int(height * margin), int(height * (1 - margin))
    return frame[y0:y1, x0:x1]


def _select_enrollment_views(
    frames: list[np.ndarray], *, max_views: int = 5
) -> tuple[list[np.ndarray], float]:
    scored: list[tuple[float, np.ndarray, np.ndarray]] = []
    for frame in frames:
        crop = _centre_crop(frame)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        thumb = cv2.resize(gray, (32, 32)).astype(np.float32)
        scored.append((sharpness, crop.copy(), thumb))
    if not scored:
        return [], 0.0
    best_sharpness = max(item[0] for item in scored)
    floor = max(25.0, 0.35 * best_sharpness)
    selected: list[tuple[float, np.ndarray, np.ndarray]] = []
    for sharpness, crop, thumb in sorted(scored, key=lambda item: -item[0]):
        if sharpness < floor:
            continue
        if any(
            float(np.mean(np.abs(thumb - kept_thumb))) < 5.0
            for _, _, kept_thumb in selected
        ):
            continue
        selected.append((sharpness, crop, thumb))
        if len(selected) >= max_views:
            break
    return [crop for _, crop, _ in selected], best_sharpness


def select_enrollment_views(
    frames: list[np.ndarray], *, max_views: int = 5
) -> list[np.ndarray]:
    views, _ = _select_enrollment_views(frames, max_views=max_views)
    return views


@dataclass(slots=True)
class EnrollmentCapture:
    """Result of a live enrolment burst, with diagnostics for the UI."""

    views: list[np.ndarray]
    frames_sampled: int
    best_sharpness: float


class CameraService:
    """Own one capture and publish latest-value recognition/video snapshots."""

    def __init__(
        self,
        *,
        source: str,
        camera_index: int,
        fixture_path: Path,
        width: int,
        height: int,
        detection_ttl_ms: int,
        dictionary_name: str,
        recognizer: Recognizer | None = None,
        recognition_max_width: int = 960,
        recognition_fps: float = 8.0,
        stream_fps: float = 15.0,
        jpeg_quality: int = 75,
        max_auto_banked_per_identity: int = 2,
    ) -> None:
        if source not in {"camera", "fixture", "disabled"}:
            raise ValueError("Camera source must be camera, fixture, or disabled")
        self.source = source
        self.camera_index = camera_index
        self.fixture_path = fixture_path
        self.requested_width = width
        self.requested_height = height
        self.detection_ttl_seconds = detection_ttl_ms / 1000
        self.dictionary_name = dictionary_name
        self.recognition_max_width = max(320, recognition_max_width)
        self.recognition_interval = 1.0 / max(0.5, recognition_fps)
        self.stream_interval = 1.0 / max(1.0, stream_fps)
        self.jpeg_quality = min(95, max(30, jpeg_quality))
        self.max_auto_banked_per_identity = max(0, max_auto_banked_per_identity)
        self.recognizer: Recognizer = recognizer or ArucoRecognizer(dictionary_name)
        # Set by the app layer: persists a banked crop (file + DB row).
        self.view_bank_sink: Callable[[str, np.ndarray], None] | None = None

        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._recognizer_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._capture: cv2.VideoCapture | None = None
        self._frame_jpeg: bytes | None = None
        self._latest_frame: np.ndarray | None = None
        self._view_samples = deque(maxlen=18)
        self._view_sample_at = 0.0
        self._latest_frame_sequence = 0
        self._encoded_frame_sequence = 0
        self._recognized_frame_sequence = 0
        self._capture_monotonic: float | None = None
        self._encoded_monotonic: float | None = None
        self._encoded_capture_monotonic: float | None = None
        self._frame_width = width
        self._frame_height = height
        self._captured_at: datetime | None = None
        self._tracks: dict[str, MarkerTrack] = {}
        self._user_confirmed: set[str] = set()
        self._bank_state: dict[str, tuple[float, np.ndarray, int]] = {}
        self._bank_persist_queue: Queue[tuple[str, np.ndarray]] = Queue(
            maxsize=BANK_PERSIST_QUEUE_SIZE
        )
        self._bank_persist_dropped = 0
        self._stream_clients = 0
        self._capture_events: deque[float] = deque()
        self._recognition_events: deque[float] = deque()
        self._stream_events: deque[float] = deque()
        self._recognition_durations_ms: deque[tuple[float, float]] = deque()
        self.load_shed_active: Callable[[], bool] = lambda: False
        self._burst_until: float | None = None
        self._burst_next_sample = 0.0
        self._burst_frames: list[np.ndarray] = []
        # Staged creation: scan results waiting for user review/save.
        # scan_id -> (expiry monotonic, accumulated capture)
        self._pending_scans: dict[str, tuple[float, EnrollmentCapture]] = {}
        self._status = "disabled" if source == "disabled" else "starting"
        self._message: str | None = (
            "Camera disabled by configuration" if source == "disabled" else None
        )

    def start(self) -> None:
        if self.source == "disabled":
            return
        if any(thread.is_alive() for thread in self._threads):
            return
        # macOS permission requests must run on the main thread's run loop.
        # Opening here also avoids OpenCV trying unrelated capture backends.
        if self.source == "camera" and sys.platform == "darwin":
            self._capture = cv2.VideoCapture(self.camera_index, cv2.CAP_AVFOUNDATION)
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=self._run_capture, name="locus-capture", daemon=True
            ),
            threading.Thread(
                target=self._run_recognition,
                name="locus-recognition",
                daemon=True,
            ),
            threading.Thread(
                target=self._run_encoder, name="locus-encoder", daemon=True
            ),
            threading.Thread(
                target=self._run_bank_persistence,
                name="locus-bank-persistence",
                daemon=True,
            ),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads = []
        capture = self._capture
        if capture is not None:
            capture.release()
            self._capture = None

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    def assistant_frame(self) -> tuple[bytes, datetime] | None:
        """Copy only a fresh capture; never reuse a stale image after disconnect."""
        with self._lock:
            if (self._status != "ready" or self._latest_frame is None
                    or time.monotonic() - self._capture_monotonic > 2):
                return None
            frame = self._latest_frame.copy()
            captured_at = self._captured_at
        height, width = frame.shape[:2]
        if width > 960:
            frame = cv2.resize(frame, (960, round(height * 960 / width)))
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return (jpeg.tobytes(), captured_at) if ok else None

    def memory_capture(self) -> tuple[np.ndarray, datetime, list] | None:
        """Recognize the exact saved frame, never a lingering overlay track."""
        with self._lock:
            if (self._status != "ready" or self._latest_frame is None
                    or time.monotonic() - self._capture_monotonic > 2):
                return None
            frame = self._latest_frame.copy()
            captured_at = self._captured_at
        with self._recognizer_lock:
            matches = self.recognizer.detect(frame)
        return frame, captured_at, matches

    def stable_view(self) -> tuple[np.ndarray, datetime] | None:
        """A recent, steady view is attention evidence, not an object identity."""
        with self._lock:
            now = time.monotonic()
            if self._status != "ready" or self._latest_frame is None or now - self._capture_monotonic > 2:
                return None
            samples = [entry for entry in self._view_samples if now - entry[0] <= 4]
            if len(samples) < 7 or samples[-1][0] - samples[0][0] < 2.5:
                return None
            current = samples[-1][1]
            # Require the current central view to resemble the entire dwell window.
            for _, previous in samples:
                difference = float(np.mean(np.abs(current.astype(np.float32) - previous)))
                if difference <= 14:
                    continue
                # Small head movements and exposure shifts should not reset attention.
                if float(current.std()) < 3 or float(previous.std()) < 3:
                    return None
                correlation = cv2.matchTemplate(previous, current[4:-4, 4:-4], cv2.TM_CCOEFF_NORMED)
                if float(correlation.max()) < .82:
                    return None
            return self._latest_frame.copy(), self._captured_at

    def load_reference_files(self, references: list[tuple[str, Path]]) -> None:
        loader = getattr(self.recognizer, "load_references", None)
        if loader is not None:
            with self._recognizer_lock:
                loader(references)

    def enroll_reference(
        self, identity_key: str, image: np.ndarray, *, min_keypoints: int = 8
    ) -> bool:
        add = getattr(self.recognizer, "add_reference", None)
        if add is None:
            return False
        with self._recognizer_lock:
            try:
                return bool(add(identity_key, image, min_keypoints=min_keypoints))
            except TypeError:
                return bool(add(identity_key, image))

    def remove_reference(self, identity_key: str) -> bool:
        remove = getattr(self.recognizer, "remove_reference", None)
        if remove is None:
            return False
        with self._recognizer_lock:
            return bool(remove(identity_key))

    # -- live-feed enrolment (Phase 2) -----------------------------------

    def capture_enrollment_views(
        self, duration_seconds: float = 4.0
    ) -> list[np.ndarray]:
        return self.capture_enrollment_capture(duration_seconds).views

    def capture_enrollment_capture(
        self, duration_seconds: float = 4.0
    ) -> EnrollmentCapture:
        """Burst-capture from the live feed and select enrolment views.

        Blocks the *calling* thread (run it via ``asyncio.to_thread``)
        while the camera thread keeps sampling frames. Returns sharp,
        centred, diverse centre crops plus diagnostics (frames sampled,
        best sharpness); empty if the camera is disabled or a burst is
        already running.

        Note there is no object tracking here: a not-yet-enrolled object
        cannot be tracked, so the centre crop *is* the targeting
        mechanism — the UI shows a centre guide while this runs.
        """
        if self.source == "disabled":
            return EnrollmentCapture([], 0, 0.0)
        with self._lock:
            if self._burst_until is not None:
                return EnrollmentCapture([], 0, 0.0)
            self._burst_frames = []
            self._burst_next_sample = 0.0
            self._burst_until = time.monotonic() + duration_seconds
        deadline = self._burst_until
        while time.monotonic() < deadline and not self._stop.is_set():
            time.sleep(0.05)
        with self._lock:
            frames = self._burst_frames
            self._burst_frames = []
            self._burst_until = None
        views, best_sharpness = _select_enrollment_views(frames)
        return EnrollmentCapture(views, len(frames), best_sharpness)

    # -- staged creation: scan -> review -> save ---------------------------

    PENDING_SCAN_TTL_SECONDS = 300.0
    MAX_PENDING_VIEWS = 8

    def create_pending_scan(
        self, duration_seconds: float = 4.0
    ) -> tuple[str | None, EnrollmentCapture]:
        """Capture a burst and stash it for review. Nothing is enrolled
        or persisted until the scan is confirmed via ``pop_pending_scan``
        by the create endpoint."""
        capture = self.capture_enrollment_capture(duration_seconds)
        if not capture.views:
            return None, capture
        scan_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._prune_pending_scans(time.monotonic())
            self._pending_scans[scan_id] = (
                time.monotonic() + self.PENDING_SCAN_TTL_SECONDS,
                capture,
            )
        return scan_id, capture

    def _prune_pending_scans(self, now: float) -> None:
        expired = [
            scan_id
            for scan_id, (expiry, _) in self._pending_scans.items()
            if expiry < now
        ]
        for scan_id in expired:
            del self._pending_scans[scan_id]

    def get_pending_scan(self, scan_id: str) -> EnrollmentCapture | None:
        with self._lock:
            self._prune_pending_scans(time.monotonic())
            entry = self._pending_scans.get(scan_id)
            return entry[1] if entry is not None else None

    def extend_pending_scan(
        self, scan_id: str, duration_seconds: float = 4.0
    ) -> EnrollmentCapture | None:
        """Run another burst and merge its diverse views into the scan."""
        if self.get_pending_scan(scan_id) is None:
            return None
        extra = self.capture_enrollment_capture(duration_seconds)
        with self._lock:
            entry = self._pending_scans.get(scan_id)
            if entry is None:
                return None
            expiry, current = entry
            merged = list(current.views)
            seen = [
                cv2.resize(
                    cv2.cvtColor(v, cv2.COLOR_BGR2GRAY) if v.ndim == 3 else v,
                    (32, 32),
                ).astype(np.float32)
                for v in merged
            ]
            for view in extra.views:
                if len(merged) >= self.MAX_PENDING_VIEWS:
                    break
                gray = (
                    cv2.cvtColor(view, cv2.COLOR_BGR2GRAY)
                    if view.ndim == 3
                    else view
                )
                thumb = cv2.resize(gray, (32, 32)).astype(np.float32)
                if any(
                    float(np.mean(np.abs(thumb - kept))) < 5.0 for kept in seen
                ):
                    continue
                merged.append(view)
                seen.append(thumb)
            combined = EnrollmentCapture(
                merged,
                current.frames_sampled + extra.frames_sampled,
                max(current.best_sharpness, extra.best_sharpness),
            )
            self._pending_scans[scan_id] = (expiry, combined)
            return combined

    def drop_pending_scan(self, scan_id: str) -> bool:
        with self._lock:
            return self._pending_scans.pop(scan_id, None) is not None

    def reference_count(self, identity_key: str) -> int:
        count = getattr(self.recognizer, "reference_count", None)
        if count is None:
            return 0
        with self._recognizer_lock:
            return int(count(identity_key))

    # -- provisional confirmation + view bank (Phase 3) ------------------

    def confirm_identity(self, identity_key: str) -> bool:
        """User-confirmed provisional match: promote it and bank its view.

        This is the only path besides a high-confidence match that may
        bank a view — identity here comes from the user, not a guess.
        """
        with self._lock:
            track = self._tracks.get(identity_key)
            frame = self._latest_frame
            if track is None or frame is None:
                return False
            corners = track.corners.copy()
            track.tier = "high"
            track.hits = max(track.hits, CONFIRM_HITS_HIGH)
            self._user_confirmed.add(identity_key)
            frame_copy = frame.copy()
        self._bank_view(identity_key, frame_copy, corners, force=True)
        return True

    def _bank_view(
        self, identity_key: str, frame: np.ndarray, corners: np.ndarray, *, force: bool = False
    ) -> None:
        bank = getattr(self.recognizer, "bank_view", None)
        if bank is None:
            return
        with self._lock:
            state = self._bank_state.get(identity_key)
            if (
                not force
                and state is not None
                and state[2] >= self.max_auto_banked_per_identity
            ):
                return
        with self._recognizer_lock:
            crop = bank(identity_key, frame, corners)
        if crop is None:
            return
        now = time.monotonic()
        with self._lock:
            _, _, count = self._bank_state.get(identity_key, (0.0, corners, 0))
            self._bank_state[identity_key] = (now, corners.copy(), count + 1)
        if self.view_bank_sink is None:
            return
        if not any(thread.is_alive() for thread in self._threads):
            # Direct unit-test/manual processing mode has no persistence worker.
            self.view_bank_sink(identity_key, crop)
            return
        try:
            self._bank_persist_queue.put_nowait((identity_key, crop))
        except Full:
            with self._lock:
                self._bank_persist_dropped += 1

    def _maybe_bank_view(
        self, identity_key: str, frame: np.ndarray, detection: object, now: float
    ) -> None:
        tier = getattr(detection, "tier", "high")
        confidence = float(getattr(detection, "confidence", 0.0))
        if tier != "high" or confidence < BANK_MIN_CONFIDENCE:
            return
        corners = np.asarray(detection.corners, dtype=float)
        with self._lock:
            track = self._tracks.get(identity_key)
            if track is None or not track.confirmed:
                return
            state = self._bank_state.get(identity_key)
            if state is not None:
                last_bank, last_corners, count = state
                if count >= self.max_auto_banked_per_identity:
                    return
                if now - last_bank < BANK_INTERVAL_SECONDS:
                    return
                shift = float(np.mean(np.linalg.norm(corners - last_corners, axis=1)))
                if shift < BANK_MIN_CORNER_SHIFT_PX:
                    return
        self._bank_view(identity_key, frame, corners)

    # -- latest-frame workers ---------------------------------------------

    def _run_capture(self) -> None:
        if self.source == "fixture":
            self._run_fixture_capture()
        else:
            self._run_camera_capture()

    def _run_fixture_capture(self) -> None:
        frame = cv2.imread(str(self.fixture_path))
        if frame is None:
            self._mark_unavailable(f"Fixture image not found: {self.fixture_path}")
            return
        while not self._stop.is_set():
            self._publish_captured_frame(frame.copy())
            self._stop.wait(1 / 30)

    def _run_camera_capture(self) -> None:
        capture = self._capture if self._capture is not None else cv2.VideoCapture(self.camera_index)
        self._capture = capture
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not capture.isOpened():
            self._mark_unavailable(
                f"Unable to open camera index {self.camera_index}"
            )
            capture.release()
            self._capture = None
            return

        try:
            while not self._stop.is_set():
                success, frame = capture.read()
                if not success:
                    self._mark_unavailable("Camera stopped returning frames")
                    break
                self._publish_captured_frame(frame)
        finally:
            capture.release()
            if self._capture is capture:
                self._capture = None

    def _publish_captured_frame(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        captured_at = datetime.now(UTC)
        with self._condition:
            self._latest_frame = frame
            if now - self._view_sample_at >= 0.35:
                gray = cv2.cvtColor(_centre_crop(frame), cv2.COLOR_BGR2GRAY)
                self._view_samples.append((now, cv2.resize(gray, (48, 36))))
                self._view_sample_at = now
            self._latest_frame_sequence += 1
            self._capture_monotonic = now
            self._captured_at = captured_at
            height, width = frame.shape[:2]
            self._frame_width = width
            self._frame_height = height
            self._status = "ready"
            self._message = (
                "Development fixture — real object recognition"
                if self.source == "fixture"
                else None
            )
            self._capture_events.append(now)
            if self._burst_until is not None and now >= self._burst_next_sample:
                self._burst_frames.append(frame.copy())
                self._burst_next_sample = now + 0.25
            self._condition.notify_all()

    def _run_recognition(self) -> None:
        last_sequence = 0
        next_due = 0.0
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stop.is_set()
                    or self._latest_frame_sequence != last_sequence,
                    timeout=0.25,
                )
                if self._stop.is_set():
                    return
                now = time.monotonic()
                interval = self.recognition_interval * (
                    2.0 if self.load_shed_active() else 1.0
                )
                if now < next_due:
                    wait_for = next_due - now
                    frame = None
                    sequence = last_sequence
                else:
                    frame = (
                        self._latest_frame.copy()
                        if self._latest_frame is not None
                        else None
                    )
                    sequence = self._latest_frame_sequence
                    wait_for = 0.0
            if wait_for > 0:
                self._stop.wait(wait_for)
                continue
            if frame is None:
                continue
            started = time.monotonic()
            self._process_frame(frame, encode=False)
            finished = time.monotonic()
            with self._lock:
                self._recognized_frame_sequence = sequence
                self._recognition_events.append(finished)
                self._recognition_durations_ms.append(
                    (finished, (finished - started) * 1000)
                )
            last_sequence = sequence
            next_due = started + interval

    def _run_encoder(self) -> None:
        last_sequence = 0
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stop.is_set()
                    or (
                        self._stream_clients > 0
                        and self._latest_frame_sequence != last_sequence
                    ),
                    timeout=0.5,
                )
                if self._stop.is_set():
                    return
                if self._stream_clients == 0 or self._latest_frame is None:
                    continue
                frame = self._latest_frame.copy()
                sequence = self._latest_frame_sequence
                capture_monotonic = self._capture_monotonic
            started = time.monotonic()
            success, encoded = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            )
            if success:
                with self._condition:
                    self._frame_jpeg = encoded.tobytes()
                    self._encoded_frame_sequence = sequence
                    self._encoded_monotonic = time.monotonic()
                    self._encoded_capture_monotonic = capture_monotonic
                    self._stream_events.append(self._encoded_monotonic)
                    self._condition.notify_all()
            last_sequence = sequence
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.0, self.stream_interval - elapsed))

    def _run_bank_persistence(self) -> None:
        while not self._stop.is_set() or not self._bank_persist_queue.empty():
            try:
                identity_key, crop = self._bank_persist_queue.get(timeout=0.2)
            except Empty:
                continue
            try:
                if self.view_bank_sink is not None:
                    self.view_bank_sink(identity_key, crop)
            except Exception:
                # Optional self-improvement must not take down live capture.
                pass
            finally:
                self._bank_persist_queue.task_done()

    def _mark_unavailable(self, message: str) -> None:
        with self._lock:
            self._status = "unavailable"
            self._message = message

    def _process_frame(self, frame: np.ndarray, *, encode: bool = True) -> None:
        now_monotonic = time.monotonic()
        height, width = frame.shape[:2]
        if width > self.recognition_max_width:
            scale = self.recognition_max_width / width
            analysis = cv2.resize(
                frame,
                (self.recognition_max_width, max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            scale = 1.0
            analysis = frame
        with self._recognizer_lock:
            detections = self.recognizer.detect(analysis)
        if scale != 1.0:
            for detection in detections:
                detection.corners = np.asarray(detection.corners, dtype=float) / scale

        with self._lock:
            if self._latest_frame is None:
                self._latest_frame = frame.copy()
                self._latest_frame_sequence += 1
                self._capture_monotonic = now_monotonic
                self._captured_at = datetime.now(UTC)
            for detection in detections:
                corners = np.asarray(detection.corners, dtype=float)
                tier = getattr(detection, "tier", "high")
                previous = self._tracks.get(detection.identity_key)
                if previous is not None:
                    smoothed = previous.corners * 0.6 + corners * 0.4
                    hits = previous.hits + 1
                    # Tier follows the current frame's measurement, so a
                    # track that drops to provisional stops attaching
                    # seamlessly — unless the user confirmed this identity,
                    # in which case it stays high until the track expires.
                    if detection.identity_key in self._user_confirmed:
                        tier = "high"
                    # Display the current frame's measured confidence —
                    # never a sticky/decaying max of past frames, which
                    # made the shown percentage lag and inflate.
                    confidence = detection.confidence
                else:
                    smoothed = corners
                    hits = 1
                    confidence = detection.confidence
                self._tracks[detection.identity_key] = MarkerTrack(
                    smoothed,
                    confidence,
                    detection.method,
                    now_monotonic,
                    hits=hits,
                    tier=tier,
                )

            self._expire_tracks(now_monotonic)
            self._frame_width = width
            self._frame_height = height
            self._status = "ready"
            self._message = (
                "Development fixture — real object recognition"
                if self.source == "fixture"
                else None
            )
            if encode:
                success, encoded = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                )
                if success:
                    self._frame_jpeg = encoded.tobytes()
                    self._encoded_frame_sequence = self._latest_frame_sequence
                    self._encoded_monotonic = now_monotonic

        for detection in detections:
            self._maybe_bank_view(detection.identity_key, frame, detection, now_monotonic)

    def _expire_tracks(self, now_monotonic: float) -> None:
        expired = [
            identity_key
            for identity_key, track in self._tracks.items()
            if now_monotonic - track.seen_monotonic > self.detection_ttl_seconds
        ]
        for identity_key in expired:
            del self._tracks[identity_key]
            self._user_confirmed.discard(identity_key)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            self._expire_tracks(time.monotonic())
            detections = []
            for identity_key, track in self._tracks.items():
                if not track.confirmed:
                    continue
                corners = track.corners.tolist()
                center = track.corners.mean(axis=0).tolist()
                detections.append(
                    {
                        "identity_key": identity_key,
                        "confidence": track.confidence,
                        "method": track.method,
                        "tier": track.tier,
                        "corners": corners,
                        "center": center,
                    }
                )
            frame_center = (self._frame_width / 2, self._frame_height / 2)
            detections.sort(
                key=lambda item: (
                    (item["center"][0] - frame_center[0]) ** 2
                    + (item["center"][1] - frame_center[1]) ** 2,
                    item["identity_key"],
                )
            )
            return {
                "status": self._status,
                "source": self.source,
                "message": self._message,
                "captured_at": self._captured_at,
                "frame_width": self._frame_width,
                "frame_height": self._frame_height,
                "detections": detections,
            }

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._frame_jpeg

    @staticmethod
    def _rate(events: deque[float], now: float, window: float = 5.0) -> float:
        while events and events[0] < now - window:
            events.popleft()
        return round(len(events) / window, 2)

    def performance_snapshot(self) -> dict[str, object]:
        now = time.monotonic()
        with self._lock:
            capture_fps = self._rate(self._capture_events, now)
            recognition_fps = self._rate(self._recognition_events, now)
            stream_fps = self._rate(self._stream_events, now)
            while (
                self._recognition_durations_ms
                and self._recognition_durations_ms[0][0] < now - 30
            ):
                self._recognition_durations_ms.popleft()
            durations = sorted(
                duration for _, duration in self._recognition_durations_ms
            )
            p50 = durations[len(durations) // 2] if durations else 0.0
            p95 = (
                durations[min(len(durations) - 1, int(len(durations) * 0.95))]
                if durations
                else 0.0
            )
            frame_age_ms = (
                max(0.0, (now - self._encoded_capture_monotonic) * 1000)
                if self._encoded_capture_monotonic is not None
                else None
            )
            result = {
                "capture_fps": capture_fps,
                "recognition_fps": recognition_fps,
                "stream_fps": stream_fps,
                "recognition_p50_ms": round(p50, 2),
                "recognition_p95_ms": round(p95, 2),
                "latest_frame_age_ms": (
                    round(frame_age_ms, 2) if frame_age_ms is not None else None
                ),
                "captured_sequence": self._latest_frame_sequence,
                "recognized_sequence": self._recognized_frame_sequence,
                "encoded_sequence": self._encoded_frame_sequence,
                "active_stream_clients": self._stream_clients,
                "bank_persist_queue_depth": self._bank_persist_queue.qsize(),
                "bank_persist_dropped": self._bank_persist_dropped,
            }
        total_references = 0
        count = getattr(self.recognizer, "reference_count", None)
        if count is not None:
            with self._recognizer_lock:
                keys = getattr(self.recognizer, "enrolled_keys", [])
                total_references = sum(int(count(key)) for key in keys)
        result["active_reference_variants"] = total_references
        return result

    def mjpeg_frames(self):
        last_sequence = 0
        with self._condition:
            self._stream_clients += 1
            self._condition.notify_all()
        try:
            while not self._stop.is_set():
                with self._condition:
                    self._condition.wait_for(
                        lambda: self._stop.is_set()
                        or self._encoded_frame_sequence != last_sequence,
                        timeout=0.5,
                    )
                    if self._stop.is_set():
                        return
                    frame = self._frame_jpeg
                    sequence = self._encoded_frame_sequence
                if frame is None or sequence == last_sequence:
                    continue
                last_sequence = sequence
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    + frame
                    + b"\r\n"
                )
        finally:
            with self._condition:
                self._stream_clients = max(0, self._stream_clients - 1)
                self._condition.notify_all()
