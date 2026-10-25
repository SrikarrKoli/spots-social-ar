from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample Locus performance diagnostics")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--seconds", type=int, default=1200)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    samples: list[dict[str, object]] = []
    deadline = time.monotonic() + arguments.seconds
    while time.monotonic() < deadline:
        started = time.perf_counter()
        with urllib.request.urlopen(
            f"{arguments.base_url}/api/diagnostics/performance", timeout=5
        ) as response:
            sample = json.load(response)
        sample["sampled_at"] = time.time()
        sample["request_ms"] = round((time.perf_counter() - started) * 1000, 2)
        samples.append(sample)
        print(json.dumps(sample), flush=True)
        time.sleep(max(0.0, 1 - (time.perf_counter() - started)))

    ages = sorted(
        float(sample["latest_frame_age_ms"])
        for sample in samples
        if sample["latest_frame_age_ms"] is not None
    )
    summary = {
        "samples": len(samples),
        "capture_fps_median": statistics.median(
            float(sample["capture_fps"]) for sample in samples
        ),
        "recognition_fps_median": statistics.median(
            float(sample["recognition_fps"]) for sample in samples
        ),
        "stream_fps_median": statistics.median(
            float(sample["stream_fps"]) for sample in samples
        ),
        "frame_age_p95_ms": ages[min(len(ages) - 1, int(len(ages) * 0.95))]
        if ages
        else None,
        "reference_variants_max": max(
            int(sample["active_reference_variants"]) for sample in samples
        ),
        "bank_drops": max(int(sample["bank_persist_dropped"]) for sample in samples),
    }
    output = {"summary": summary, "samples": samples}
    if arguments.output:
        arguments.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
