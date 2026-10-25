"""Controlled background leakage check; never changes the app or its database.

uv run python -m scripts.evaluate_object_background --reference PHOTO.png --bbox X0 Y0 X1 Y1
The supplied bounding box is a test annotation, not automatic segmentation.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from backend.app.recognition import InstanceRecognizer


def evaluate(reference, bbox):
    x0, y0, x1, y1 = bbox
    height, width = reference.shape[:2]
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError('Bounding box must be inside the reference image')
    foreground = reference[y0:y1, x0:x1].copy()
    without_object = reference.copy()
    without_object[y0:y1, x0:x1] = (125, 125, 125)
    moved = np.full_like(reference, (65, 95, 125))
    moved[:foreground.shape[0], :foreground.shape[1]] = foreground
    scenes = {'original': reference, 'object_on_new_background': moved,
              'original_scene_without_target_region': without_object}
    report = {}
    for name, enrollment in [('scene_reference', reference), ('object_crop_reference', foreground)]:
        recognizer = InstanceRecognizer()
        if not recognizer.add_reference('test-object', enrollment):
            raise ValueError('The annotated region has insufficient features for this test')
        report[name] = {name: [{'tier': item.tier, 'matcher_score': item.confidence}
                            for item in recognizer.detect(frame)] for name, frame in scenes.items()}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--bbox', type=int, nargs=4, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    reference = cv2.imread(str(args.reference))
    if reference is None:
        parser.error('Reference is not a readable image')
    result = json.dumps(evaluate(reference, args.bbox), indent=2)
    if args.output:
        args.output.write_text(result + '\n')
    print(result)


if __name__ == '__main__':
    main()
