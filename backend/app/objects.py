from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np


@dataclass(slots=True)
class ObjectBox:
    label: str
    confidence: float
    box: tuple[float, float, float, float]


class ObjectDetector(Protocol):
    name: str

    def load(self) -> None: ...

    def detect(self, frame: np.ndarray) -> list[ObjectBox]: ...


class YoloObjectDetector:
    """General-purpose COCO object detection (80 classes) via Ultralytics YOLO."""

    name = "yolo"

    def __init__(
        self, *, model_path: Path, confidence: float, device: str | None = None
    ) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self.device = device
        self._model = None

    def load(self) -> None:
        # Imported lazily so the API starts quickly and tests never load torch.
        import torch
        from ultralytics import YOLO

        if self.device is None:
            self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        # A known model name (e.g. yolo11n.pt) is downloaded on first use.
        self._model = YOLO(str(self.model_path))

    def detect(self, frame: np.ndarray) -> list[ObjectBox]:
        if self._model is None:
            raise RuntimeError("Object detector has not been loaded")
        result = self._model.predict(
            frame, conf=self.confidence, device=self.device, verbose=False
        )[0]
        names = result.names
        boxes = result.boxes
        return [
            ObjectBox(
                label=str(names[int(class_id)]),
                confidence=float(score),
                box=tuple(float(value) for value in xyxy),
            )
            for xyxy, score, class_id in zip(
                boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()
            )
        ]


def build_object_detector(
    *, provider: str, model_path: Path, confidence: float
) -> ObjectDetector | None:
    if provider == "disabled":
        return None
    if provider == "yolo":
        return YoloObjectDetector(model_path=model_path, confidence=confidence)
    raise ValueError("Object detection provider must be yolo or disabled")
