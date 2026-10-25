"""Generate markerless enrolment references + fixture.

The poster's artwork and the book's cover *are* the identity — no printed
ArUco tag is attached. Run: .venv/bin/python scripts/generate_references.py
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OBJECTS_DIR = ROOT / "objects"
MARKERS_DIR = ROOT / "markers"


def _texture(rng: np.random.Generator, canvas: np.ndarray, n: int = 260) -> None:
    h, w = canvas.shape[:2]
    for _ in range(n):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        color = tuple(int(c) for c in rng.integers(60, 255, size=3))
        if rng.random() < 0.5:
            cv2.circle(canvas, (x, y), int(rng.integers(3, 16)), color, -1, cv2.LINE_AA)
        else:
            cv2.rectangle(
                canvas, (x, y),
                (x + int(rng.integers(6, 42)), y + int(rng.integers(4, 18))),
                color, -1,
            )


def concert_poster() -> np.ndarray:
    rng = np.random.default_rng(7)
    canvas = np.full((1000, 760, 3), (24, 22, 48), np.uint8)
    for i in range(9):
        cv2.circle(canvas, (380, 340), 60 + i * 34, (240, 120 + i * 10, 60), 5, cv2.LINE_AA)
    cv2.circle(canvas, (380, 340), 52, (255, 205, 80), -1, cv2.LINE_AA)
    for x in range(60, 720, 46):
        cv2.line(canvas, (x, 620), (x + 120, 760), (80, 200, 220), 3, cv2.LINE_AA)
    _texture(rng, canvas)
    cv2.putText(canvas, "NEON HARBOR", (58, 850), cv2.FONT_HERSHEY_SIMPLEX, 1.7, (255, 255, 255), 4, cv2.LINE_AA)
    cv2.putText(canvas, "THE LANTERN - FRIDAY", (60, 905), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 205, 80), 3, cv2.LINE_AA)
    cv2.putText(canvas, "LOCUS LIVE 07", (60, 955), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 220, 255), 2, cv2.LINE_AA)
    return canvas


def favorite_book() -> np.ndarray:
    rng = np.random.default_rng(23)
    canvas = np.full((1000, 700, 3), (38, 74, 62), np.uint8)
    cv2.circle(canvas, (460, 300), 150, (235, 225, 175), -1, cv2.LINE_AA)
    cv2.circle(canvas, (515, 265), 132, (38, 74, 62), -1, cv2.LINE_AA)
    for i in range(6):
        cv2.rectangle(canvas, (60 + i * 18, 560 + i * 22), (420, 578 + i * 22), (220, 190, 90), -1)
    _texture(rng, canvas)
    cv2.putText(canvas, "THE LEFT HAND", (52, 800), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (255, 255, 255), 4, cv2.LINE_AA)
    cv2.putText(canvas, "OF DARKNESS", (52, 862), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (255, 255, 255), 4, cv2.LINE_AA)
    cv2.putText(canvas, "URSULA K. LE GUIN", (54, 922), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 190, 90), 2, cv2.LINE_AA)
    return canvas


def _warp(image: np.ndarray, dst: np.ndarray, canvas: np.ndarray) -> None:
    h, w = image.shape[:2]
    src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    homography = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    warped = cv2.warpPerspective(image, homography, (canvas.shape[1], canvas.shape[0]))
    mask = cv2.warpPerspective(
        np.full((h, w), 255, np.uint8), homography, (canvas.shape[1], canvas.shape[0])
    )
    canvas[mask > 0] = warped[mask > 0]


def make_fixture(poster: np.ndarray, book: np.ndarray) -> np.ndarray:
    canvas = np.full((900, 1600, 3), (216, 219, 209), np.uint8)
    cv2.rectangle(canvas, (0, 0), (1600, 110), (21, 27, 23), -1)
    cv2.putText(canvas, "LOCUS / MARKERLESS FIXTURE", (60, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (241, 242, 234), 2, cv2.LINE_AA)
    _warp(poster, np.array([[110, 170], [690, 220], [660, 820], [140, 780]]), canvas)
    _warp(book, np.array([[900, 210], [1430, 170], [1460, 760], [920, 810]]), canvas)
    return canvas


def main() -> None:
    OBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    MARKERS_DIR.mkdir(parents=True, exist_ok=True)
    poster, book = concert_poster(), favorite_book()
    for name, image in (("concert-poster", poster), ("favorite-book", book)):
        path = OBJECTS_DIR / f"{name}.png"
        cv2.imwrite(str(path), image)
        print(f"Generated {path.relative_to(ROOT)}")
    fixture = MARKERS_DIR / "markerless-fixture.png"
    cv2.imwrite(str(fixture), make_fixture(poster, book))
    print(f"Generated {fixture.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
