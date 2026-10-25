from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


@dataclass(slots=True)
class RecognizedInstance:
    """One individually identified object instance in a frame.

    Identity is the specific enrolled object (e.g. "favorite-book"), never a
    class label (e.g. "book"). Corners locate it for the 2D overlay.
    """

    identity_key: str
    corners: np.ndarray  # shape (4, 2), frame pixel coordinates
    confidence: float
    method: str  # "aruco" | "instance-features"


class Recognizer(Protocol):
    def detect(self, frame: np.ndarray) -> list[RecognizedInstance]: ...


# ---------------------------------------------------------------------------
# Legacy ArUco recognizer (dev/test fixture only — not used in the demo path)
# ---------------------------------------------------------------------------


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
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return []
    return [
        (int(marker_id), marker_corners.reshape(4, 2).astype(float))
        for marker_id, marker_corners in zip(ids.flatten(), corners, strict=True)
    ]


class ArucoRecognizer:
    method = "aruco"

    def __init__(self, dictionary_name: str = "DICT_4X4_50") -> None:
        self.dictionary_name = dictionary_name

    def detect(self, frame: np.ndarray) -> list[RecognizedInstance]:
        return [
            RecognizedInstance(
                identity_key=str(marker_id),
                corners=corners,
                confidence=1.0,
                method=self.method,
            )
            for marker_id, corners in detect_markers(frame, self.dictionary_name)
        ]


# ---------------------------------------------------------------------------
# Markerless instance recognizer
#
# Each enrolled object is stored as one or more reference views. A frame is
# matched by local features (SIFT when available, ORB otherwise) against every
# enrolled view; a homography (for planar objects such as posters and book
# covers) or the matched-point bounding box (for non-planar views) locates the
# instance. This is instance recognition, not classification: two objects of
# the same class with different appearance produce different matches, and an
# object that does not clear the threshold/margin is reported as unknown
# (no detection) rather than force-matched.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Reference:
    keypoints: list
    descriptors: np.ndarray
    width: int
    height: int


def _make_extractor() -> tuple[object, int]:
    if hasattr(cv2, "SIFT_create"):
        return cv2.SIFT_create(nfeatures=1200), cv2.NORM_L2
    return cv2.ORB_create(nfeatures=1200), cv2.NORM_HAMMING


@dataclass(slots=True)
class _Candidate:
    identity_key: str
    corners: np.ndarray
    inliers: int
    good_matches: int

    @property
    def confidence(self) -> float:
        return self.inliers / self.good_matches if self.good_matches else 0.0


class InstanceRecognizer:
    method = "instance-features"

    def __init__(
        self,
        *,
        min_inliers: int = 12,
        min_confidence: float = 0.30,
        ratio_test: float = 0.75,
        min_margin_inliers: int = 4,
    ) -> None:
        self.min_inliers = min_inliers
        self.min_confidence = min_confidence
        self.ratio_test = ratio_test
        self.min_margin_inliers = min_margin_inliers
        self._extractor, self._norm = _make_extractor()
        self._matcher = cv2.BFMatcher(self._norm)
        self._references: dict[str, list[_Reference]] = {}

    # -- enrolment ------------------------------------------------------

    def add_reference(self, identity_key: str, image: np.ndarray) -> bool:
        """Enrol one view of an object. Returns False if it has no texture."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        keypoints, descriptors = self._extractor.detectAndCompute(gray, None)
        if descriptors is None or len(keypoints) < 8:
            return False
        height, width = gray.shape[:2]
        self._references.setdefault(identity_key, []).append(
            _Reference(list(keypoints), descriptors, width, height)
        )
        return True

    def load_reference(self, identity_key: str, path: Path) -> bool:
        image = cv2.imread(str(path))
        return image is not None and self.add_reference(identity_key, image)

    def load_references(self, references: list[tuple[str, Path]]) -> None:
        for identity_key, path in references:
            self.load_reference(identity_key, path)

    @property
    def enrolled_keys(self) -> list[str]:
        return sorted(self._references)

    # -- detection ------------------------------------------------------

    def detect(self, frame: np.ndarray) -> list[RecognizedInstance]:
        if not self._references:
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        frame_kp, frame_des = self._extractor.detectAndCompute(gray, None)
        if frame_des is None or len(frame_kp) < 8:
            return []

        best_per_identity: dict[str, _Candidate] = {}
        for identity_key, references in self._references.items():
            for reference in references:
                candidate = self._match_reference(
                    identity_key, reference, frame_kp, frame_des, frame.shape
                )
                if candidate is None:
                    continue
                current = best_per_identity.get(identity_key)
                if current is None or candidate.inliers > current.inliers:
                    best_per_identity[identity_key] = candidate

        if not best_per_identity:
            return []

        # Distinguish, don't guess: a sighting must clear the absolute bar.
        # The margin only applies when two identities claim the *same* region
        # (overlapping corners) — two different objects co-visible in a frame
        # are both legitimate and must both be reported.
        ranked = sorted(
            best_per_identity.values(), key=lambda c: c.inliers, reverse=True
        )
        accepted: list[RecognizedInstance] = []
        kept: list[_Candidate] = []
        for candidate in ranked:
            if (
                candidate.inliers < self.min_inliers
                or candidate.confidence < self.min_confidence
            ):
                continue
            rival = next(
                (k for k in kept if self._same_region(k, candidate)), None
            )
            if rival is not None:
                # Same region, rival already kept (higher inliers): only keep
                # this one if it is clearly stronger — impossible by ordering,
                # so ambiguous claims collapse to the stronger match; a tie
                # within the margin drops both.
                if rival.inliers - candidate.inliers < self.min_margin_inliers:
                    kept.remove(rival)
                    accepted = [
                        a for a in accepted if a.identity_key != rival.identity_key
                    ]
                continue
            kept.append(candidate)
            accepted.append(
                RecognizedInstance(
                    identity_key=candidate.identity_key,
                    corners=candidate.corners,
                    confidence=round(candidate.confidence, 3),
                    method=self.method,
                )
            )
        return accepted

    @staticmethod
    def _same_region(a: _Candidate, b: _Candidate) -> bool:
        def bbox(corners: np.ndarray) -> tuple[float, float, float, float]:
            return (
                float(corners[:, 0].min()),
                float(corners[:, 1].min()),
                float(corners[:, 0].max()),
                float(corners[:, 1].max()),
            )

        ax0, ay0, ax1, ay1 = bbox(a.corners)
        bx0, by0, bx1, by1 = bbox(b.corners)
        ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
        iy = max(0.0, min(ay1, by1) - max(ay0, by0))
        intersection = ix * iy
        if intersection == 0:
            return False
        area_a = max(1.0, (ax1 - ax0) * (ay1 - ay0))
        area_b = max(1.0, (bx1 - bx0) * (by1 - by0))
        return intersection / min(area_a, area_b) > 0.5

    def _match_reference(
        self,
        identity_key: str,
        reference: _Reference,
        frame_kp: list,
        frame_des: np.ndarray,
        frame_shape: tuple[int, ...],
    ) -> _Candidate | None:
        if len(reference.keypoints) < 2 or frame_des.shape[0] < 2:
            return None
        pairs = self._matcher.knnMatch(reference.descriptors, frame_des, k=2)
        good = []
        for pair in pairs:
            if len(pair) != 2:
                continue
            best, second = pair
            if best.distance < self.ratio_test * second.distance:
                good.append(best)
        if len(good) < self.min_inliers:
            return None

        src = np.float32([reference.keypoints[m.queryIdx].pt for m in good]).reshape(
            -1, 1, 2
        )
        dst = np.float32([frame_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        homography, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        frame_h, frame_w = frame_shape[:2]

        if homography is not None and mask is not None:
            inliers = int(mask.sum())
            ref_corners = np.float32(
                [
                    [0, 0],
                    [reference.width - 1, 0],
                    [reference.width - 1, reference.height - 1],
                    [0, reference.height - 1],
                ]
            ).reshape(-1, 1, 2)
            corners = cv2.perspectiveTransform(ref_corners, homography).reshape(4, 2)
            if not self._corners_plausible(corners, frame_w, frame_h):
                return None
            return _Candidate(identity_key, corners.astype(float), inliers, len(good))

        inliers = len(good)
        points = dst.reshape(-1, 2)
        x0, y0 = points.min(axis=0)
        x1, y1 = points.max(axis=0)
        corners = np.array(
            [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float
        )
        if not self._corners_plausible(corners, frame_w, frame_h):
            return None
        return _Candidate(identity_key, corners, inliers, inliers)

    @staticmethod
    def _corners_plausible(corners: np.ndarray, frame_w: int, frame_h: int) -> bool:
        area = cv2.contourArea(corners.astype(np.float32))
        if area < 0.002 * frame_w * frame_h:
            return False
        return bool(
            np.all(corners[:, 0] >= -0.25 * frame_w)
            and np.all(corners[:, 0] <= 1.25 * frame_w)
            and np.all(corners[:, 1] >= -0.25 * frame_h)
            and np.all(corners[:, 1] <= 1.25 * frame_h)
        )


def build_recognizer(
    name: str, *, dictionary_name: str = "DICT_4X4_50"
) -> Recognizer:
    if name in {"instance", "planar", "embedding"}:
        return InstanceRecognizer()
    if name == "aruco":
        return ArucoRecognizer(dictionary_name)
    raise ValueError("Camera recognizer must be instance, planar, embedding, or aruco")
