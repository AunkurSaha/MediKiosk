"""Independently verify a new fitted corpus without changing its files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.render_metadata import verify_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir", type=Path, default=ROOT / "datasets/synthetic/clean512_v2"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks/clean512_v2/pixel_verification_independent.json",
    )
    args = parser.parse_args()
    dataset = args.dataset_dir.resolve()
    output = args.output.resolve()
    if not dataset.is_relative_to(
        ROOT / "datasets/synthetic"
    ) or not output.is_relative_to(ROOT / "benchmarks/clean512_v2"):
        raise ValueError(
            "Verification is confined to the OCR versioned dataset/new report"
        )
    if dataset == ROOT / "datasets/synthetic/generalization":
        raise ValueError("This utility must not target the historical corpus")
    result = verify_dataset(dataset)
    if any(
        result[key]
        for key in (
            "projected_bounds_overflow_count",
            "actual_glyph_loss_count",
            "safe_region_ink_overflow_count",
            "saved_image_mismatch_count",
        )
    ):
        raise ValueError("Independent generated-corpus verification failed")
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2))
    print({key: value for key, value in result.items() if key != "samples_verified"})


if __name__ == "__main__":
    main()
