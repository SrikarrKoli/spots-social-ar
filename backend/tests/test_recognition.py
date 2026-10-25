from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.app.recognition import InstanceRecognizer

ROOT = Path(__file__).resolve().parents[2]


def _generator():
    spec = importlib.util.spec_from_file_location(
        "generate_references", ROOT / "scripts" / "generate_references.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recognizer() -> InstanceRecognizer:
    gen = _generator()
    instance = InstanceRecognizer()
    assert instance.add_reference("concert-poster", gen.concert_poster())
    assert instance.add_reference("favorite-book", gen.favorite_book())
    return instance


def test_fixture_recognises_each_object_individually(recognizer: InstanceRecognizer):
    gen = _generator()
    fixture = gen.make_fixture(gen.concert_poster(), gen.favorite_book())
    detections = recognizer.detect(fixture)
    by_key = {d.identity_key: d for d in detections}
    assert set(by_key) == {"concert-poster", "favorite-book"}
    # Poster is placed on the left, book on the right.
    assert by_key["concert-poster"].corners.mean(axis=0)[0] < by_key["favorite-book"].corners.mean(axis=0)[0]
    assert all(d.confidence >= 0.30 for d in detections)


def test_identity_follows_the_object_not_its_position(recognizer: InstanceRecognizer):
    gen = _generator()
    poster, book = gen.concert_poster(), gen.favorite_book()
    canvas = np.full((900, 1600, 3), (216, 219, 209), np.uint8)
    # Swapped layout: book left, poster right.
    gen._warp(book, np.array([[110, 170], [690, 220], [660, 820], [140, 780]]), canvas)
    gen._warp(poster, np.array([[900, 210], [1430, 170], [1460, 760], [920, 810]]), canvas)
    by_key = {d.identity_key: d for d in recognizer.detect(canvas)}
    assert set(by_key) == {"concert-poster", "favorite-book"}
    assert by_key["favorite-book"].corners.mean(axis=0)[0] < by_key["concert-poster"].corners.mean(axis=0)[0]


def test_unknown_scene_is_not_force_matched(recognizer: InstanceRecognizer):
    blank = np.full((480, 640, 3), 200, np.uint8)
    assert recognizer.detect(blank) == []
