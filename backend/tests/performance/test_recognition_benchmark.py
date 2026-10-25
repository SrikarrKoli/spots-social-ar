from __future__ import annotations

import importlib.util
import statistics
import time
from pathlib import Path

import pytest

from backend.app.recognition import InstanceRecognizer


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.performance
def test_fixture_recognition_benchmark(request: pytest.FixtureRequest):
    spec = importlib.util.spec_from_file_location(
        "generate_references", ROOT / "scripts" / "generate_references.py"
    )
    generator = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(generator)

    recognizer = InstanceRecognizer()
    poster = generator.concert_poster()
    book = generator.favorite_book()
    assert recognizer.add_reference("concert-poster", poster)
    assert recognizer.add_reference("favorite-book", book)
    frame = generator.make_fixture(poster, book)

    recognizer.detect(frame)  # warm-up
    samples: list[float] = []
    for _ in range(30):
        started = time.perf_counter()
        recognizer.detect(frame)
        samples.append((time.perf_counter() - started) * 1000)

    samples.sort()
    median = statistics.median(samples)
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    request.node.user_properties.extend(
        [("median_ms", round(median, 2)), ("p95_ms", round(p95, 2))]
    )
    assert median > 0
    assert p95 >= median
