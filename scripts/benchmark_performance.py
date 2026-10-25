from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2

from backend.app.config import ROOT, Settings
from backend.app.database import Database
from backend.app.recognition import InstanceRecognizer
from backend.app.repositories import Repository


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Locus performance benchmark")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--max-regression-percent", type=float)
    arguments = parser.parse_args()

    settings = Settings.from_env()
    repository = Repository(Database(settings.database_path))
    references = [
        (identity, ROOT / path)
        for identity, path in repository.object_references(
            max_per_identity=settings.max_reference_files_per_identity
        )
    ]
    if not references:
        raise SystemExit("No enrolled references are available")
    frame = cv2.imread(str(references[0][1]))
    if frame is None:
        raise SystemExit(f"Could not read benchmark frame {references[0][1]}")
    if frame.shape[1] != settings.camera_width or frame.shape[0] != settings.camera_height:
        frame = cv2.resize(frame, (settings.camera_width, settings.camera_height))
    source_size = [frame.shape[1], frame.shape[0]]
    if frame.shape[1] > settings.recognition_max_width:
        scale = settings.recognition_max_width / frame.shape[1]
        frame = cv2.resize(
            frame,
            (settings.recognition_max_width, round(frame.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )

    recognizer = InstanceRecognizer()
    load_started = time.perf_counter()
    recognizer.load_references(references)
    load_ms = (time.perf_counter() - load_started) * 1000
    recognizer.detect(frame)
    samples: list[float] = []
    for _ in range(max(1, arguments.iterations)):
        started = time.perf_counter()
        recognizer.detect(frame)
        samples.append((time.perf_counter() - started) * 1000)

    median = statistics.median(samples)
    result = {
        "physical_reference_files": len(references),
        "active_reference_variants": sum(
            recognizer.reference_count(key) for key in recognizer.enrolled_keys
        ),
        "load_ms": round(load_ms, 2),
        "iterations": len(samples),
        "median_ms": round(median, 2),
        "p95_ms": round(percentile(samples, 0.95), 2),
        "estimated_fps": round(1000 / median, 2),
        "source_frame_size": source_size,
        "analysis_frame_size": [frame.shape[1], frame.shape[0]],
    }
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if arguments.output:
        arguments.output.write_text(rendered + "\n")

    if arguments.compare:
        baseline = json.loads(arguments.compare.read_text())
        regression = (result["median_ms"] / baseline["median_ms"] - 1) * 100
        print(f"median change: {regression:+.1f}%")
        if (
            arguments.max_regression_percent is not None
            and regression > arguments.max_regression_percent
        ):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
