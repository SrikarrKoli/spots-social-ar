from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from backend.app.camera import CameraService
from backend.app.database import Database, seed_demo
from backend.app.recognition import InstanceRecognizer, RecognizedInstance
from backend.app.repositories import Repository


class RecordingRecognizer:
    method = "instance-features"

    def __init__(self) -> None:
        self.shapes: list[tuple[int, ...]] = []

    def detect(self, frame: np.ndarray):
        self.shapes.append(frame.shape)
        return [
            RecognizedInstance(
                "object",
                np.array([[10, 10], [20, 10], [20, 20], [10, 20]], dtype=float),
                0.9,
                self.method,
            )
        ]


def make_service(tmp_path: Path, recognizer=None, **overrides) -> CameraService:
    options = {
        "source": "disabled",
        "camera_index": 0,
        "fixture_path": tmp_path / "missing.png",
        "width": 1280,
        "height": 720,
        "detection_ttl_ms": 100,
        "dictionary_name": "DICT_4X4_50",
        "recognizer": recognizer,
    }
    options.update(overrides)
    return CameraService(**options)


def test_latest_capture_slot_overwrites_instead_of_queueing(tmp_path: Path):
    service = make_service(tmp_path)
    for value in range(10):
        service._publish_captured_frame(
            np.full((12, 16, 3), value, dtype=np.uint8)
        )

    diagnostics = service.performance_snapshot()
    assert diagnostics["captured_sequence"] == 10
    assert service._latest_frame is not None
    assert int(service._latest_frame[0, 0, 0]) == 9


def test_analysis_downscale_restores_source_coordinates(tmp_path: Path):
    recognizer = RecordingRecognizer()
    service = make_service(
        tmp_path,
        recognizer,
        recognition_max_width=640,
    )
    service._process_frame(np.zeros((720, 1280, 3), dtype=np.uint8))
    service._process_frame(np.zeros((720, 1280, 3), dtype=np.uint8))

    assert recognizer.shapes == [(360, 640, 3), (360, 640, 3)]
    corners = service.snapshot()["detections"][0]["corners"]
    assert corners == [[20.0, 20.0], [40.0, 20.0], [40.0, 40.0], [20.0, 40.0]]


def test_expiring_track_does_not_reset_lifetime_bank_count(tmp_path: Path):
    service = make_service(tmp_path)
    corners = np.zeros((4, 2), dtype=float)
    service._bank_state["object"] = (time.monotonic() - 10, corners, 2)
    service._tracks["object"] = type(
        "Track",
        (),
        {"seen_monotonic": time.monotonic() - 10},
    )()

    service._expire_tracks(time.monotonic())

    assert "object" not in service._tracks
    assert service._bank_state["object"][2] == 2


def test_reference_variants_are_hard_bounded(tmp_path: Path):
    recognizer = InstanceRecognizer()
    rng = np.random.default_rng(7)
    references: list[tuple[str, Path]] = []
    for index in range(10):
        image = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
        path = tmp_path / f"object-live-{index}.png"
        assert cv2.imwrite(str(path), image)
        references.append(("object", path))

    recognizer.load_references(references)

    assert recognizer.reference_count("object") == 8


def test_repository_selects_bounded_deliberate_then_banked_views(tmp_path: Path):
    database = Database(tmp_path / "locus.db")
    seed_demo(database)
    repository = Repository(database)
    for index in range(6):
        repository.add_reference_path(
            "concert-poster", f"data/enrolled/concert-poster-banked-{index}.png"
        )

    selected = [
        path
        for identity, path in repository.object_references(max_per_identity=4)
        if identity == "concert-poster"
    ]

    assert len(selected) == 4
    assert selected[0] == "objects/concert-poster.png"
    assert sum("-banked-" in path for path in selected) == 3


def test_recognition_context_returns_preview_without_full_thread(tmp_path: Path):
    database = Database(tmp_path / "locus.db")
    seed_demo(database)
    context = Repository(database).recognition_context(["concert-poster"])

    record, preview = context["concert-poster"]
    assert record.title == "Concert poster"
    assert preview is not None
    assert preview.body == "Anyone want to go Friday?"
    assert preview.reply_count == 1
