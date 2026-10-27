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
    # "high" attaches seamlessly; "provisional" must be user-confirmed.
    tier: str = "high"


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


_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

# Enrolment photos (4032px phone shots) are normalised toward the 720p
# webcam domain: a primary view capped at this size plus one half-scale view.
MAX_REFERENCE_DIMENSION = 1280
MAX_REFERENCES_PER_IDENTITY = 8
VIEW_DUPLICATE_THRESHOLD = 5.0
REFERENCE_FEATURE_INSET = 0.125


def _prepare_gray(image: np.ndarray) -> np.ndarray:
    """Convert to grey and CLAHE-normalise so enrolment and live frames
    share one contrast domain (helps matte/low-texture surfaces)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return _CLAHE.apply(gray)


def _reference_feature_mask(gray: np.ndarray) -> np.ndarray:
    """Keep enrollment evidence near the centered target, not scene edges."""
    height, width = gray.shape[:2]
    x_inset = round(width * REFERENCE_FEATURE_INSET)
    y_inset = round(height * REFERENCE_FEATURE_INSET)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y_inset : height - y_inset, x_inset : width - x_inset] = 255
    return mask


def _scaled_variants(gray: np.ndarray, *, extra_scale: bool) -> list[np.ndarray]:
    height, width = gray.shape[:2]
    largest = max(height, width)
    variants = []
    if largest > MAX_REFERENCE_DIMENSION:
        scale = MAX_REFERENCE_DIMENSION / largest
        variants.append(
            cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        )
    else:
        variants.append(gray)
    if extra_scale:
        primary = variants[0]
        if min(primary.shape[:2]) >= 160:
            variants.append(
                cv2.resize(primary, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            )
    return variants


def _clip_polygon_to_rect(
    polygon: list[tuple[float, float]], width: float, height: float
) -> list[tuple[float, float]]:
    """Sutherland–Hodgman clip of a polygon to the frame rectangle."""

    def clip(points, inside, intersect):
        if not points:
            return points
        output: list[tuple[float, float]] = []
        previous = points[-1]
        previous_inside = inside(previous)
        for current in points:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(intersect(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersect(previous, current))
            previous, previous_inside = current, current_inside
        return output

    def cross_x(edge: float):
        def intersect(a, b):
            t = (edge - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
            return (edge, a[1] + t * (b[1] - a[1]))

        return intersect

    def cross_y(edge: float):
        def intersect(a, b):
            t = (edge - a[1]) / (b[1] - a[1]) if b[1] != a[1] else 0.0
            return (a[0] + t * (b[0] - a[0]), edge)

        return intersect

    clipped = clip(polygon, lambda p: p[0] >= 0.0, cross_x(0.0))
    clipped = clip(clipped, lambda p: p[0] <= width, cross_x(width))
    clipped = clip(clipped, lambda p: p[1] >= 0.0, cross_y(0.0))
    clipped = clip(clipped, lambda p: p[1] <= height, cross_y(height))
    return clipped


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1], strict=True):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


@dataclass(slots=True)
class _Candidate:
    identity_key: str
    corners: np.ndarray
    inliers: int
    good_matches: int
    # Set when geometry could not be homography-verified (non-planar
    # fallback): such a sighting is never allowed to look like a
    # confident, verified match.
    confidence_override: float | None = None

    @property
    def confidence(self) -> float:
        if self.confidence_override is not None:
            return self.confidence_override
        return self.inliers / self.good_matches if self.good_matches else 0.0


class InstanceRecognizer:
    method = "instance-features"

    def __init__(
        self,
        *,
        min_inliers: int = 15,
        min_confidence: float = 0.35,
        ratio_test: float = 0.75,
        min_margin_inliers: int = 4,
        provisional_min_inliers: int = 12,
        provisional_min_confidence: float = 0.28,
    ) -> None:
        self.min_inliers = min_inliers
        self.min_confidence = min_confidence
        self.ratio_test = ratio_test
        self.min_margin_inliers = min_margin_inliers
        self.provisional_min_inliers = provisional_min_inliers
        self.provisional_min_confidence = provisional_min_confidence
        self._extractor, self._norm = _make_extractor()
        self._matcher = cv2.BFMatcher(self._norm)
        self._references: dict[str, list[_Reference]] = {}
        self._view_thumbnails: dict[str, list[np.ndarray]] = {}

    # -- enrolment ------------------------------------------------------

    def add_reference(
        self,
        identity_key: str,
        image: np.ndarray,
        *,
        extra_scale: bool = True,
        min_keypoints: int = 8,
    ) -> bool:
        """Enrol one view of an object. Returns False if it has no texture.

        Large photos are downscaled toward webcam resolution and, by
        default, stored at one extra half scale so a 4032px phone photo
        and a 720p webcam frame meet in the middle. ``min_keypoints`` is
        the *enrolment* gate only — live enrolment passes a lower value
        for low-texture objects; the strict recognition thresholds that
        protect against false matches are unaffected.
        """
        gray = (
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        )
        added = False
        for variant in _scaled_variants(gray, extra_scale=extra_scale):
            if self.reference_count(identity_key) >= MAX_REFERENCES_PER_IDENTITY:
                break
            prepared = _CLAHE.apply(variant)
            keypoints, descriptors = self._extractor.detectAndCompute(
                prepared, _reference_feature_mask(prepared)
            )
            if descriptors is None or len(keypoints) < min_keypoints:
                continue
            height, width = prepared.shape[:2]
            self._references.setdefault(identity_key, []).append(
                _Reference(list(keypoints), descriptors, width, height)
            )
            added = True
        return added

    def reference_count(self, identity_key: str) -> int:
        return len(self._references.get(identity_key, []))

    def remove_reference(self, identity_key: str) -> bool:
        self._view_thumbnails.pop(identity_key, None)
        return self._references.pop(identity_key, None) is not None

    @staticmethod
    def _thumbnail(image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        return cv2.resize(gray, (32, 32)).astype(np.float32)

    def _remember_view(self, identity_key: str, image: np.ndarray) -> None:
        self._view_thumbnails.setdefault(identity_key, []).append(
            self._thumbnail(image)
        )

    def _is_duplicate_view(self, identity_key: str, image: np.ndarray) -> bool:
        thumbnail = self._thumbnail(image)
        return any(
            float(np.mean(np.abs(thumbnail - existing)))
            < VIEW_DUPLICATE_THRESHOLD
            for existing in self._view_thumbnails.get(identity_key, [])
        )

    @staticmethod
    def extract_view(frame: np.ndarray, corners: np.ndarray) -> np.ndarray | None:
        """Perspective-rectify the region inside ``corners`` (TL,TR,BR,BL)."""
        src = np.asarray(corners, dtype=np.float32).reshape(4, 2)
        width = int(max(np.linalg.norm(src[1] - src[0]), np.linalg.norm(src[2] - src[3])))
        height = int(
            max(np.linalg.norm(src[3] - src[0]), np.linalg.norm(src[2] - src[1]))
        )
        if width < 60 or height < 60:
            return None
        dst = np.float32(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
        )
        transform = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(frame, transform, (width, height))

    def bank_view(
        self, identity_key: str, frame: np.ndarray, corners: np.ndarray
    ) -> np.ndarray | None:
        """Bank a new-angle crop as an extra view of an enrolled identity.

        Identity is inherited from track continuity / user confirmation by
        the caller — this never matches, it only enrols the crop under the
        given key. Returns the banked crop, or None if it was unusable.
        """
        if identity_key not in self._references:
            return None
        if self.reference_count(identity_key) >= MAX_REFERENCES_PER_IDENTITY:
            return None
        crop = self.extract_view(frame, corners)
        if crop is None:
            return None
        if self._is_duplicate_view(identity_key, crop):
            return None
        if not self.add_reference(identity_key, crop, extra_scale=False):
            return None
        self._remember_view(identity_key, crop)
        return crop

    def load_reference(self, identity_key: str, path: Path) -> bool:
        image = cv2.imread(str(path))
        if image is None:
            return False
        is_live_sized = any(
            marker in path.name for marker in ("-banked-", "-live-", "-added-")
        )
        added = self.add_reference(
            identity_key, image, extra_scale=not is_live_sized
        )
        if added:
            self._remember_view(identity_key, image)
        return added

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
        gray = _prepare_gray(frame)
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
        # Tiered confidence: clearing the high bar attaches seamlessly;
        # clearing only the lower provisional bar is reported as
        # provisional (user-confirmable, never auto-attached); anything
        # below that is unknown. The margin only applies when two
        # identities claim the *same* region (overlapping corners) — two
        # different objects co-visible in a frame are both legitimate.
        ranked = sorted(
            best_per_identity.values(), key=lambda c: c.inliers, reverse=True
        )
        accepted: list[RecognizedInstance] = []
        kept: list[tuple[_Candidate, str]] = []
        for candidate in ranked:
            if (
                candidate.inliers >= self.min_inliers
                and candidate.confidence >= self.min_confidence
            ):
                tier = "high"
            elif (
                candidate.inliers >= self.provisional_min_inliers
                and candidate.confidence >= self.provisional_min_confidence
            ):
                tier = "provisional"
            else:
                continue
            rival = next(
                (k for k in kept if self._same_region(k[0], candidate)), None
            )
            if rival is not None:
                rival_candidate, rival_tier = rival
                if rival_tier == "high" and tier == "provisional":
                    continue  # A confident claim on this region wins.
                # Same region, rival already kept (higher inliers): a tie
                # within the margin drops both rather than guessing.
                if rival_candidate.inliers - candidate.inliers < self.min_margin_inliers:
                    kept.remove(rival)
                    accepted = [
                        a
                        for a in accepted
                        if a.identity_key != rival_candidate.identity_key
                    ]
                continue
            kept.append((candidate, tier))
            accepted.append(
                RecognizedInstance(
                    identity_key=candidate.identity_key,
                    corners=candidate.corners,
                    confidence=round(candidate.confidence, 3),
                    method=self.method,
                    tier=tier,
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
        if len(good) < self.provisional_min_inliers:
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
        # No homography verification (non-planar fallback): cap this at
        # provisional tier — it can be shown as a possible match for the
        # user to confirm, but never attaches seamlessly and never
        # displays as a fabricated 100%.
        return _Candidate(
            identity_key,
            corners,
            inliers,
            inliers,
            confidence_override=self.provisional_min_confidence,
        )

    @staticmethod
    def _corners_plausible(corners: np.ndarray, frame_w: int, frame_h: int) -> bool:
        """Accept objects close to / partially out of frame; reject only
        degenerate homographies.

        The old bound (every corner within ±25% of the frame) threw away
        excellent matches — e.g. 397 inliers at 0.94 confidence — whenever
        a near object projected past the edge. Instead: the quad must be
        finite and convex, and at least 20% of it must be visible inside
        the frame with a non-trivial visible area.
        """
        points = [(float(x), float(y)) for x, y in np.asarray(corners, dtype=float)]
        if len(points) != 4 or not all(
            np.isfinite(coord) for point in points for coord in point
        ):
            return False
        # A homography of a rectangle is convex; a bow-tie / folded quad
        # (cross products changing sign) is a degenerate projection.
        crosses = []
        for index in range(4):
            x0, y0 = points[index]
            x1, y1 = points[(index + 1) % 4]
            x2, y2 = points[(index + 2) % 4]
            crosses.append((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1))
        if not (all(c > 0 for c in crosses) or all(c < 0 for c in crosses)):
            return False
        area = _polygon_area(points)
        frame_area = float(frame_w * frame_h)
        if area < 0.002 * frame_area or area > 20.0 * frame_area:
            return False
        visible = _polygon_area(
            _clip_polygon_to_rect(points, float(frame_w), float(frame_h))
        )
        return visible >= 0.002 * frame_area and visible >= 0.20 * area


def build_recognizer(
    name: str, *, dictionary_name: str = "DICT_4X4_50"
) -> Recognizer:
    if name in {"instance", "planar", "embedding"}:
        return InstanceRecognizer()
    if name == "aruco":
        return ArucoRecognizer(dictionary_name)
    raise ValueError("Camera recognizer must be instance, planar, embedding, or aruco")
