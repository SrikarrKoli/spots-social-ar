from __future__ import annotations

import cv2
import numpy as np

import time
from pathlib import Path

from backend.app.camera import CameraService, detect_markers, resolve_camera_index
from backend.app.objects import ObjectBox


def marker_frame(marker_id: int) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 360)
    frame = np.full((600, 800), 255, np.uint8)
    frame[120:480, 220:580] = marker
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)


def test_detects_real_aruco_marker_and_corners():
    detections = detect_markers(marker_frame(7))
    assert len(detections) == 1
    marker_id, corners = detections[0]
    assert marker_id == 7
    assert corners.shape == (4, 2)
    assert np.allclose(corners.mean(axis=0), [399.5, 299.5], atol=2)


def test_start_is_idempotent_for_disabled_source(tmp_path):
    service = CameraService(
        source="disabled",
        camera_index=0,
        fixture_path=tmp_path / "none.png",
        width=1280,
        height=720,
        detection_ttl_ms=750,
        dictionary_name="DICT_4X4_50",
    )
    service.start()
    service.start()
    assert service.snapshot()["status"] == "disabled"
    service.stop()


def test_resolves_camera_index_by_name_with_fallback():
    names = ["MacBook Pro Camera", "Brio 100", "iPhone Camera"]
    assert resolve_camera_index("brio", 0, names) == 1
    assert resolve_camera_index("Missing Cam", 3, names) == 3
    assert resolve_camera_index(None, 2, names) == 2


class FakeObjectDetector:
    name = "fake"

    def __init__(self) -> None:
        self.frames_seen = 0

    def load(self) -> None:
        pass

    def detect(self, frame):
        self.frames_seen += 1
        height, width = frame.shape[:2]
        return [ObjectBox("cup", 0.9, (0.0, 0.0, width / 2, height / 2))]


def test_object_detections_run_on_live_frames():
    detector = FakeObjectDetector()
    fixture = Path(__file__).resolve().parents[2] / "markers" / "demo-fixture.png"
    service = CameraService(
        source="fixture",
        camera_index=0,
        fixture_path=fixture,
        width=1280,
        height=720,
        detection_ttl_ms=750,
        dictionary_name="DICT_4X4_50",
        object_detector=detector,
        object_interval_ms=10,
    )
    service.start()
    try:
        deadline = time.monotonic() + 3
        snapshot = service.snapshot()
        while not snapshot["objects"] and time.monotonic() < deadline:
            time.sleep(0.05)
            snapshot = service.snapshot()
    finally:
        service.stop()
    assert snapshot["object_detection_status"] == "ready"
    assert snapshot["objects"][0]["label"] == "cup"
    assert len(snapshot["objects"][0]["box"]) == 4
    assert detector.frames_seen >= 1
