from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "markers"
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
OBJECTS = (
    ("concert-poster", 7, "CHICKEN TIKKA MASALA", "Zareen's menu connection"),
    ("favorite-book", 23, "MADRAS CHICKEN CURRY", "Zareen's menu connection"),
)


def raw_marker(marker_id: int, size: int = 500) -> np.ndarray:
    return cv2.aruco.generateImageMarker(DICTIONARY, marker_id, size)


def labeled_marker(marker_id: int, title: str, description: str) -> np.ndarray:
    canvas = np.full((760, 660, 3), 255, np.uint8)
    marker = raw_marker(marker_id)
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    canvas[62:562, 80:580] = marker_bgr
    cv2.rectangle(canvas, (8, 8), (651, 751), (27, 32, 29), 3)
    cv2.putText(
        canvas,
        title,
        (80, 625),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.86,
        (24, 29, 26),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        description,
        (80, 663),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (94, 103, 96),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        f"SPOTS MENU  /  MARKER #{marker_id}",
        (80, 712),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (218, 82, 50),
        1,
        cv2.LINE_AA,
    )
    return canvas


def make_fixture() -> np.ndarray:
    canvas = np.full((900, 1600, 3), (216, 219, 209), np.uint8)
    cv2.rectangle(canvas, (0, 0), (1600, 120), (21, 27, 23), -1)
    cv2.putText(
        canvas,
        "SPOTS  /  ZAREEN'S MENU",
        (70, 74),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.05,
        (241, 242, 234),
        2,
        cv2.LINE_AA,
    )

    cards = [((90, 180), OBJECTS[0]), ((880, 245), OBJECTS[1])]
    for (x, y), (_, marker_id, title, description) in cards:
        cv2.rectangle(canvas, (x, y), (x + 620, y + 590), (247, 247, 241), -1)
        cv2.rectangle(canvas, (x, y), (x + 620, y + 590), (176, 181, 173), 2)
        marker = raw_marker(marker_id, 380)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        canvas[y + 45 : y + 425, x + 120 : x + 500] = marker_bgr
        cv2.putText(
            canvas,
            title,
            (x + 55, y + 490),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (26, 32, 28),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            description,
            (x + 55, y + 530),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (89, 98, 91),
            1,
            cv2.LINE_AA,
        )
    return canvas


def png_data_uri(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Could not encode marker")
    return "data:image/png;base64," + base64.b64encode(encoded).decode("ascii")


def printable_svg(images: list[np.ndarray]) -> str:
    page_width = 210
    page_height = 297
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{page_width}mm" height="{page_height}mm" viewBox="0 0 {page_width} {page_height}">',
        '<rect width="210" height="297" fill="white"/>',
        '<text x="14" y="14" font-family="monospace" font-size="4" font-weight="bold">SPOTS MENU · PRINT AT 100% SCALE</text>',
    ]
    for index, image in enumerate(images):
        x = 14 + index * 93
        parts.append(
            f'<image x="{x}" y="22" width="82" height="94" preserveAspectRatio="xMidYMid meet" xlink:href="{png_data_uri(image)}"/>'
        )
    parts.extend(
        [
            '<text x="14" y="132" font-family="sans-serif" font-size="3.2">Cut out a card or attach the full sheet to the prepared object.</text>',
            '<text x="14" y="139" font-family="sans-serif" font-size="3.2">Keep the entire black border visible and avoid glare.</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated: list[np.ndarray] = []
    for slug, marker_id, title, description in OBJECTS:
        image = labeled_marker(marker_id, title, description)
        generated.append(image)
        path = OUTPUT / f"{slug}-marker-{marker_id}.png"
        cv2.imwrite(str(path), image)
        print(f"Generated {path.relative_to(ROOT)}")

    svg_path = OUTPUT / "printable-markers.svg"
    svg_path.write_text(printable_svg(generated), encoding="utf-8")
    print(f"Generated {svg_path.relative_to(ROOT)}")

    fixture_path = OUTPUT / "demo-fixture.png"
    cv2.imwrite(str(fixture_path), make_fixture())
    print(f"Generated {fixture_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
