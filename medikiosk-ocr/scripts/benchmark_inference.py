"""Reload the tiny checkpoint and benchmark synthetic line inference."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dataset import load_manifest  # noqa: E402
from app.recognizer import FlorLineRecognizer  # noqa: E402


def main() -> None:
    checkpoint = ROOT / "models" / "tiny_flor.weights.h5"
    started = time.perf_counter()
    recognizer = FlorLineRecognizer(checkpoint)
    cold_start_ms = (time.perf_counter() - started) * 1000
    sample = load_manifest(ROOT / "datasets" / "synthetic" / "tiny" / "manifest.csv")[0]
    content = sample.image.read_bytes()
    values = []
    prediction = ""
    for _ in range(5):
        prediction, elapsed = recognizer.recognize(content)
        values.append(elapsed)
    result = {
        "device": "cpu",
        "cold_start_ms": cold_start_ms,
        "warm_median_ms": statistics.median(values),
        "warm_average_ms": statistics.mean(values),
        "runs": len(values),
        "truth": sample.text,
        "prediction": prediction,
        "model_version": recognizer.model_version,
    }
    (ROOT / "benchmarks" / "inference.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
