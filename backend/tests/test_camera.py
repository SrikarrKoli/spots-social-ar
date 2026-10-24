from __future__ import annotations

import cv2
import numpy as np

from backend.app.camera import CameraService, detect_markers


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
