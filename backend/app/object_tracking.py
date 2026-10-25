"""Short-lived object motion between independent identity measurements.

Optical flow never enrolls an identity, confirms a provisional match, or supplies
reference images. New identity measurements remain the source of truth.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .recognition import RecognizedInstance


@dataclass
class _Motion:
    corners: np.ndarray
    points: np.ndarray
    verified_at: float
    verified_hits: int
    confidence: float
    method: str


class ObjectMotionTracker:
    MAX_BRIDGE_SECONDS = .7

    def __init__(self):
        self.previous = None
        self.previous_at = 0.0
        self.tracks: dict[str, _Motion] = {}

    def remove(self, identity):
        self.tracks.pop(identity, None)

    @staticmethod
    def _features(gray, corners):
        mask = np.zeros(gray.shape, np.uint8)
        # Favour the object interior over background along its boundary.
        inner = corners.mean(axis=0) + .8 * (corners - corners.mean(axis=0))
        cv2.fillConvexPoly(mask, np.round(inner).astype(np.int32), 255)
        return cv2.goodFeaturesToTrack(gray, 90, .02, 5, mask=mask, blockSize=5)

    def _follow(self, state, gray):
        if self.previous is None or self.previous.shape != gray.shape or len(state.points) < 8:
            return None
        params = dict(winSize=(25, 25), maxLevel=3,
                      criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, .02))
        new, forward, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, state.points, None, **params)
        if new is None or forward is None:
            return None
        back, backward, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, new, None, **params)
        if back is None or backward is None:
            return None
        keep = (forward.ravel() == 1) & (backward.ravel() == 1)
        keep &= np.linalg.norm(back.reshape(-1, 2) - state.points.reshape(-1, 2), axis=1) < 1.25
        src, dst = state.points.reshape(-1, 2)[keep], new.reshape(-1, 2)[keep]
        if len(src) < 8 or len(src) / len(state.points) < .5:
            return None
        matrix, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0)
        if matrix is None or mask is None or float(mask.mean()) < .7:
            return None
        points = dst[mask.ravel() == 1]
        corners = cv2.transform(state.corners.reshape(-1, 1, 2), matrix).reshape(4, 2)
        scale = float(np.hypot(matrix[0, 0], matrix[0, 1]))
        if not np.isfinite(corners).all() or not .75 <= scale <= 1.3:
            return None
        height, width = gray.shape
        center = corners.mean(axis=0)
        if not (0 <= center[0] < width and 0 <= center[1] < height):
            return None
        # A small surviving background patch must not drag a whole object box.
        spread = cv2.contourArea(cv2.convexHull(points.astype(np.float32)))
        area = abs(cv2.contourArea(corners.astype(np.float32)))
        if spread < max(25, area * .04):
            return None
        return corners, points.reshape(-1, 1, 2).astype(np.float32)

    def update(self, frame, measurements, now):
        height, width = frame.shape[:2]
        scale = min(1., 640 / width)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if scale != 1:
            gray = cv2.resize(gray, (round(width * scale), round(height * scale)))
        fresh = {item.identity_key: item for item in measurements}
        following = {}
        if 0 <= now - self.previous_at <= .4:
            for identity, state in self.tracks.items():
                if now - state.verified_at <= self.MAX_BRIDGE_SECONDS:
                    result = self._follow(state, gray)
                    if result is not None:
                        following[identity] = result
        updated = {}
        output = []
        for identity, measurement in fresh.items():
            if measurement.tier != 'high':
                output.append(measurement)
                continue
            corners = np.asarray(measurement.corners, np.float32) * scale
            state = self.tracks.get(identity)
            flow = following.get(identity)
            # Use motion to remove small localization jitter, never the previous location.
            if flow is not None:
                distance = float(np.linalg.norm(corners.mean(axis=0) - flow[0].mean(axis=0)))
                size = float(np.linalg.norm(corners[2] - corners[0]))
                if distance <= max(12, .15 * size):
                    corners = .7 * corners + .3 * flow[0]
            points = self._features(gray, corners)
            if points is not None and len(points) >= 8:
                hits = state.verified_hits + 1 if state and flow is not None else 1
                updated[identity] = _Motion(corners, points, now, hits, measurement.confidence, measurement.method)
            output.append(RecognizedInstance(identity, corners / scale, measurement.confidence, measurement.method, measurement.tier))
        for identity, (corners, points) in following.items():
            if identity in fresh:
                continue
            state = self.tracks[identity]
            if state.verified_hits < 2:
                continue
            updated[identity] = _Motion(corners, points, state.verified_at, state.verified_hits, state.confidence, state.method)
            output.append(RecognizedInstance(identity, corners / scale,
                round(state.confidence * .9, 3), state.method + '+optical-flow', 'high'))
        self.previous, self.previous_at, self.tracks = gray, now, updated
        return output
