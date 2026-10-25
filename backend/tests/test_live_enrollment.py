from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.app.camera import CameraService, select_enrollment_views
from backend.app.recognition import InstanceRecognizer, RecognizedInstance

ROOT = Path(__file__).resolve().parents[2]


def _generator():
    spec = importlib.util.spec_from_file_location(
        "generate_references", ROOT / "scripts" / "generate_references.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# -- Phase 1: corner plausibility -------------------------------------------


def test_corners_partially_out_of_frame_are_accepted():
    # Object close to the camera: projected quad extends well past the
    # frame edges (the old ±25% bound rejected 397-inlier matches here).
    corners = np.array(
        [[-400, 100], [1500, 100], [1500, 800], [-400, 800]], dtype=float
    )
    assert InstanceRecognizer._corners_plausible(corners, 1280, 720)


def test_degenerate_corners_are_still_rejected():
    bowtie = np.array([[0, 0], [100, 100], [0, 100], [100, 0]], dtype=float)
    assert not InstanceRecognizer._corners_plausible(bowtie, 1280, 720)
    off_frame = np.array(
        [[2000, 0], [2400, 0], [2400, 400], [2000, 400]], dtype=float
    )
    assert not InstanceRecognizer._corners_plausible(off_frame, 1280, 720)
    tiny = np.array([[10, 10], [14, 10], [14, 14], [10, 14]], dtype=float)
    assert not InstanceRecognizer._corners_plausible(tiny, 1280, 720)


def test_large_phone_photo_enrolment_still_recognised_at_webcam_scale():
    gen = _generator()
    poster = gen.concert_poster()
    large = cv2.resize(poster, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    recognizer = InstanceRecognizer()
    assert recognizer.add_reference("concert-poster", large)
    assert recognizer.reference_count("concert-poster") >= 2  # primary + half scale
    fixture = gen.make_fixture(gen.concert_poster(), gen.favorite_book())
    keys = {d.identity_key for d in recognizer.detect(fixture)}
    assert "concert-poster" in keys


# -- Phase 2: burst view selection ------------------------------------------


def _textured_frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    frame = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    return frame


def test_select_enrollment_views_dedupes_and_drops_blur():
    sharp_a = _textured_frame(1)
    sharp_b = _textured_frame(2)
    blurry = np.full((480, 640, 3), 128, np.uint8)
    views = select_enrollment_views([sharp_a, sharp_a.copy(), sharp_b, blurry])
    assert len(views) == 2
    # Views are centre crops (70% of frame), not whole frames.
    assert views[0].shape[1] == int(640 * 0.7) or views[0].shape[1] in (448, 449)


def test_capture_diagnostics_when_camera_disabled(tmp_path: Path):
    service = _service(tmp_path, _FakeRecognizer())
    capture = service.capture_enrollment_capture(0.5)
    assert capture.views == []
    assert capture.frames_sampled == 0
    assert capture.best_sharpness == 0.0


def test_live_scan_requires_camera_and_unknown_scan_is_404(client: TestClient):
    scan = client.post(
        "/api/objects/enroll-live/scan", json={"duration_seconds": 3}
    )
    assert scan.status_code == 503
    create = client.post(
        "/api/objects/enroll-live",
        json={"scan_id": "does-not-exist", "title": "Black bottle"},
    )
    assert create.status_code == 404


def test_staged_scan_review_create_and_add_views(tmp_path: Path):
    from dataclasses import replace

    from backend.app.main import create_app
    from backend.tests.conftest import make_test_settings

    settings = replace(
        make_test_settings(tmp_path / "fixture.db"),
        camera_source="fixture",
        camera_fixture=ROOT / "markers" / "markerless-fixture.png",
        enrolled_dir=tmp_path / "enrolled",
    )
    with TestClient(create_app(settings)) as fixture_client:
        before = {item["id"] for item in fixture_client.get("/api/objects").json()}

        scan = fixture_client.post(
            "/api/objects/enroll-live/scan", json={"duration_seconds": 3}
        )
        assert scan.status_code == 200, scan.text
        scan_body = scan.json()
        assert scan_body["captured_views"]
        assert scan_body["diagnostics"]["frames_sampled"] > 0
        # Review stage: scanning alone must persist nothing.
        after_scan = {item["id"] for item in fixture_client.get("/api/objects").json()}
        assert after_scan == before

        created = fixture_client.post(
            "/api/objects/enroll-live",
            json={"scan_id": scan_body["scan_id"], "title": "Fixture scan object"},
        )
        assert created.status_code == 201, created.text
        object_id = created.json()["id"]
        assert fixture_client.get(f"/api/objects/by-identity/{object_id}").status_code == 200
        # A scan is consumed by creation.
        again = fixture_client.post(
            "/api/objects/enroll-live",
            json={"scan_id": scan_body["scan_id"], "title": "Fixture scan object"},
        )
        assert again.status_code == 404

        added = fixture_client.post(
            f"/api/objects/{object_id}/add-views", json={"duration_seconds": 3}
        )
        assert added.status_code == 200, added.text
        assert added.json()["diagnostics"]["views_enrolled"] >= 1
        assert added.json()["reference_count"] >= 1
        assert fixture_client.get(f"/api/objects/{object_id}/posts").status_code == 200

        scan2 = fixture_client.post(
            "/api/objects/enroll-live/scan", json={"duration_seconds": 3}
        )
        scan2_id = scan2.json()["scan_id"]
        assert fixture_client.delete(
            f"/api/objects/enroll-live/scans/{scan2_id}"
        ).status_code == 200
        gone = fixture_client.post(
            "/api/objects/enroll-live",
            json={"scan_id": scan2_id, "title": "Should not exist"},
        )
        assert gone.status_code == 404


def test_discard_enrollment_removes_object_but_not_seeded(client: TestClient):
    import io

    rng = np.random.default_rng(7)
    image = np.full((240, 320, 3), (40, 60, 90), np.uint8)
    for _ in range(120):
        x, y = int(rng.integers(0, 300)), int(rng.integers(0, 220))
        cv2.circle(image, (x, y), 5, (200, 180, 60), -1)
    success, encoded = cv2.imencode(".png", image)
    assert success
    created = client.post(
        "/api/objects/enroll",
        data={"title": "Discard me"},
        files={"image": ("x.png", io.BytesIO(encoded.tobytes()), "image/png")},
    )
    assert created.status_code == 201, created.text
    object_id = created.json()["id"]

    assert client.delete(f"/api/objects/{object_id}").status_code == 200
    assert client.get(f"/api/objects/by-identity/{object_id}").status_code == 404

    # Seeded objects (and anything with posts) cannot be discarded.
    assert client.delete("/api/objects/concert-poster").status_code == 409
    assert client.get("/api/objects/by-identity/concert-poster").status_code == 200


def test_confirm_without_sighting_is_404(client: TestClient):
    response = client.post(
        "/api/recognition/confirm", json={"identity_key": "nope"}
    )
    assert response.status_code == 404


# -- Phase 1/3: temporal voting, tiers, banking ------------------------------


class _FakeRecognizer:
    method = "instance-features"

    def __init__(self, tier: str = "high", confidence: float = 0.9) -> None:
        self.tier = tier
        self.confidence = confidence
        self.banked: list[str] = []
        self.corners = np.array(
            [[100, 100], [300, 100], [300, 300], [100, 300]], dtype=float
        )

    def detect(self, frame: np.ndarray):
        return [
            RecognizedInstance(
                "thing-1", self.corners.copy(), self.confidence, self.method, self.tier
            )
        ]

    def bank_view(self, identity_key, frame, corners):
        self.banked.append(identity_key)
        return frame[:50, :50].copy()


def _service(tmp_path: Path, recognizer) -> CameraService:
    return CameraService(
        source="disabled",
        camera_index=0,
        fixture_path=tmp_path / "none.png",
        width=640,
        height=480,
        detection_ttl_ms=2000,
        dictionary_name="DICT_4X4_50",
        recognizer=recognizer,
    )


def test_high_tier_needs_two_hits_before_publishing(tmp_path: Path):
    service = _service(tmp_path, _FakeRecognizer())
    frame = np.zeros((480, 640, 3), np.uint8)
    service._process_frame(frame)
    assert service.snapshot()["detections"] == []
    service._process_frame(frame)
    detections = service.snapshot()["detections"]
    assert len(detections) == 1
    assert detections[0]["tier"] == "high"


def test_provisional_needs_three_hits_and_confirm_promotes_and_banks(
    tmp_path: Path,
):
    fake = _FakeRecognizer(tier="provisional", confidence=0.4)
    service = _service(tmp_path, fake)
    sink: list[str] = []
    service.view_bank_sink = lambda key, crop: sink.append(key)
    frame = np.zeros((480, 640, 3), np.uint8)
    for _ in range(2):
        service._process_frame(frame)
    assert service.snapshot()["detections"] == []
    service._process_frame(frame)
    detections = service.snapshot()["detections"]
    assert len(detections) == 1
    assert detections[0]["tier"] == "provisional"
    assert fake.banked == []  # never banked from a guess

    assert service.confirm_identity("thing-1") is True
    assert fake.banked == ["thing-1"]
    assert sink == ["thing-1"]
    assert service.snapshot()["detections"][0]["tier"] == "high"


def test_high_confidence_track_banks_only_after_viewpoint_moves(tmp_path: Path):
    fake = _FakeRecognizer(tier="high", confidence=0.9)
    service = _service(tmp_path, fake)
    frame = np.zeros((480, 640, 3), np.uint8)
    service._process_frame(frame)
    service._process_frame(frame)
    # First confirmed sighting banks once; identical viewpoint does not.
    assert fake.banked == ["thing-1"]
    service._process_frame(frame)
    assert fake.banked == ["thing-1"]


def test_strict_thresholds_are_the_default():
    recognizer = InstanceRecognizer()
    assert (recognizer.min_inliers, recognizer.min_confidence) == (15, 0.35)
    assert recognizer.ratio_test == 0.75
    assert (
        recognizer.provisional_min_inliers,
        recognizer.provisional_min_confidence,
    ) == (12, 0.28)


def test_displayed_confidence_is_current_frame_not_sticky_max(tmp_path: Path):
    fake = _FakeRecognizer(tier="high", confidence=0.9)
    service = _service(tmp_path, fake)
    frame = np.zeros((480, 640, 3), np.uint8)
    service._process_frame(frame)
    service._process_frame(frame)
    assert service.snapshot()["detections"][0]["confidence"] == 0.9
    fake.confidence = 0.4
    service._process_frame(frame)
    # Old behaviour would have shown max(0.4, 0.9 * 0.9) = 0.81.
    assert service.snapshot()["detections"][0]["confidence"] == 0.4


def test_bank_view_inherits_identity_and_rejects_unenrolled():
    gen = _generator()
    recognizer = InstanceRecognizer()
    assert recognizer.add_reference("concert-poster", gen.concert_poster())
    fixture = gen.make_fixture(gen.concert_poster(), gen.favorite_book())
    detection = next(
        d for d in recognizer.detect(fixture) if d.identity_key == "concert-poster"
    )
    before = recognizer.reference_count("concert-poster")
    crop = recognizer.bank_view("concert-poster", fixture, detection.corners)
    assert crop is not None
    assert recognizer.reference_count("concert-poster") > before
    assert recognizer.bank_view("never-enrolled", fixture, detection.corners) is None
