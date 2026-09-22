"""Create a new fitted corpus; preserve the historical seed/splits/targets."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image
from PIL import __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.benchmark import PrescriptionLexicon, _find
from app.dataset import load_manifest
from app.diagnostics import SCHEDULE, alignment
from app.render_metadata import file_sha256, verify_dataset
from app.rendering import (
    RenderConfig,
    fit_font,
    load_font,
    render_fitted,
    verify_pixels,
)
from scripts.build_generalization_dataset import (
    FONT_NAMES,
    SPLIT_WRITERS,
    unique_phrases,
)

EXPECTED_CHECKPOINT_SHA256 = (
    "386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef"
)
SPLITS = ("train", "validation", "test")


def snapshot_paths(paths: list[Path]) -> dict[str, str]:
    return {
        str(file.resolve()): file_sha256(file)
        for path in paths
        for file in (sorted(path.rglob("*")) if path.is_dir() else [path])
        if file.is_file()
    }


def historical_references() -> list[Path]:
    return [
        ROOT / "datasets/synthetic/generalization",
        ROOT / "benchmarks/ctc_audit",
        ROOT / "benchmarks/SYNTHETIC_BASELINE.md",
        ROOT / "benchmarks/generalization.json",
        ROOT / "benchmarks/generalization_progress.json",
        ROOT / "models/generalization_continued_flor.weights.h5",
        ROOT / "models/generalization_continued_flor.weights.json",
        ROOT / "scripts/build_generalization_dataset.py",
    ]


def stat(values: list[float]) -> dict:
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def counts(values) -> dict:
    return dict(sorted(Counter(str(value) for value in values).items()))


def read_values(name: str) -> frozenset[str]:
    return frozenset(
        line.strip()
        for line in (ROOT / "configs" / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def field_lexicon() -> PrescriptionLexicon:
    return PrescriptionLexicon(
        read_values("medicines.txt"),
        frozenset(
            f"{strength} {unit}"
            for strength in (5, 10, 20, 40, 250, 500, 625, 650)
            for unit in read_values("units.txt")
        ),
        read_values("frequencies.txt"),
        read_values("durations.txt"),
        forms=read_values("forms.txt"),
        instructions=read_values("instructions.txt"),
    )


def distributions(records: list[dict]) -> dict:
    texts = [row["target_text"] for row in records]
    lexicon = field_lexicon()
    result = {
        "samples": len(records),
        "target_length": stat([len(text) for text in texts]),
        "target_length_histogram": counts(len(text) for text in texts),
        "renderer": counts(row["renderer"] for row in records),
        "font_size": counts(row["final_font_size"] for row in records),
        "length_bucket": counts(
            "short" if len(text) <= 25 else "long" if len(text) >= 40 else "medium"
            for text in texts
        ),
        "schedule": counts(
            "|".join(SCHEDULE.findall(text)) or "<absent>" for text in texts
        ),
        "font_fitted": sum(row["was_resized_or_fitted"] for row in records),
        "fields": {
            name: counts(_find(text, choices) or "<absent>" for text in texts)
            for name, choices in vars(lexicon).items()
        },
    }
    measurements = [alignment(text, 128) for text in texts]
    result["ctc"] = {
        "required_steps": stat([row["minimum_ctc_steps"] for row in measurements]),
        "ratio": stat([row["alignment_ratio"] for row in measurements]),
        "below_1_5": sum(row["alignment_ratio"] < 1.5 for row in measurements),
        "infeasible": sum(row["minimum_ctc_steps"] > 128 for row in measurements),
    }
    return result


def protect_new_destination(path: Path, allowed_parent: Path, source: Path) -> None:
    resolved = path.resolve()
    if (
        not resolved.is_relative_to(allowed_parent.resolve())
        or resolved == allowed_parent.resolve()
    ):
        raise ValueError(f"New version must be strictly inside {allowed_parent}")
    if (
        resolved == source.resolve()
        or resolved.is_relative_to(source.resolve())
        or source.resolve().is_relative_to(resolved)
    ):
        raise ValueError("Cannot write into/over a historical corpus")
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing version/report directory: {path}"
        )


def source_records(
    source: Path, seed: int, *, validate_seed_policy: bool = True
) -> list[dict]:
    records = []
    font_offset = 0
    for split in SPLITS:
        samples = load_manifest(source / f"{split}.csv")
        font_names = FONT_NAMES[font_offset : font_offset + SPLIT_WRITERS[split]]
        font_offset += SPLIT_WRITERS[split]
        for index, sample in enumerate(samples):
            font_path = Path("C:/Windows/Fonts") / font_names[index % len(font_names)]
            if sample.writer_id != f"synthetic_renderer_{font_path.stem}":
                raise ValueError(
                    f"Historical renderer assignment differs for {sample.sample_id}"
                )
            records.append(
                {
                    "sample_id": sample.sample_id,
                    "split": split,
                    "target_text": sample.text,
                    "renderer": font_path.stem,
                    "writer_id": sample.writer_id,
                    "source_type": sample.source_type,
                    "image": sample.image.name,
                    "font_path": str(font_path),
                    "text_position": [7 + index % 4, 14 + index % 3],
                    "original_requested_font_size": 22 + index % 3,
                    "final_font_size": 22 + index % 3,
                    "was_resized_or_fitted": False,
                    "generation_seed": seed,
                }
            )
    if len({row["sample_id"] for row in records}) != len(records):
        raise ValueError("Sample IDs must be unique across splits")
    if validate_seed_policy:
        phrases = unique_phrases(len(records), seed)
        random.Random(seed).shuffle(phrases)
        if [row["target_text"] for row in records] != phrases:
            raise ValueError(
                "Source targets do not reproduce from original generation seed/configs"
            )
        if counts(row["split"] for row in records) != {
            "test": 200,
            "train": 700,
            "validation": 100,
        }:
            raise ValueError("Expected historical 700/100/200 split")
    return records


def build_version(
    source: Path,
    output: Path,
    report_dir: Path,
    config_data: dict,
    references: list[Path],
    *,
    validate_seed_policy: bool = True,
) -> dict:
    version = config_data["version"]
    seed = config_data["generation_seed"]
    config = RenderConfig(
        **{
            key: value
            for key, value in config_data.items()
            if key not in ("version", "generation_seed")
        }
    )
    if (config.canvas_width, config.canvas_height) != (512, 64):
        raise ValueError(
            "The clean corpus is fixed at width512/height64; no geometry change allowed"
        )
    protect_new_destination(output, ROOT / "datasets/synthetic", source)
    protect_new_destination(
        report_dir, ROOT / "benchmarks", ROOT / "benchmarks/ctc_audit"
    )
    before = snapshot_paths(references)
    old_records = source_records(
        source, seed, validate_seed_policy=validate_seed_policy
    )
    planned = []
    font_hashes = {}
    # Preflight the COMPLETE corpus before creating output directories.
    for record in old_records:
        font_path = Path(record["font_path"])
        if font_path not in font_hashes:
            font_hashes[font_path] = file_sha256(font_path)
        position = tuple(record["text_position"])
        fit = fit_font(
            record["target_text"],
            font_path,
            record["original_requested_font_size"],
            position,
            config,
        )
        image = render_fitted(record["target_text"], fit, position, config)
        pixel_check = verify_pixels(
            record["target_text"],
            load_font(str(font_path), fit.final_size),
            position,
            config,
            image,
        )
        if (
            any(
                pixel_check[key]
                for key in ("outside_canvas_ink_pixels", "outside_safe_area_ink_pixels")
            )
            or not pixel_check["saved_image_matches"]
        ):
            raise ValueError(
                f"Independent pixel preflight failed: {record['sample_id']}"
            )
        old_image_path = source / record["image"]
        with Image.open(old_image_path) as old_image:
            pixels_changed = not np.array_equal(
                np.asarray(old_image), np.asarray(image)
            )
        metadata = {
            **record,
            "dataset_version": version,
            "render_schema_version": 1,
            "font_sha256": font_hashes[font_path],
            "final_font_size": fit.final_size,
            "font_size": fit.final_size,
            "retry_count": fit.retry_count,
            "was_resized_or_fitted": fit.retry_count > 0,
            "image_resized": False,
            "canvas_width": config.canvas_width,
            "canvas_height": config.canvas_height,
            "text_bbox": list(fit.bounds.text_bbox),
            "safe_area_bounds": list(config.safe_area),
            "rendered_text_width": fit.bounds.text_bbox[2] - fit.bounds.text_bbox[0],
            "rendered_text_height": fit.bounds.text_bbox[3] - fit.bounds.text_bbox[1],
            "left_margin": config.margin_left,
            "right_margin": config.margin_right,
            "top_margin": config.margin_top,
            "bottom_margin": config.margin_bottom,
            "clipped": False,
            "render_config": asdict(config),
            "pixel_check": pixel_check,
            "source_image_sha256": file_sha256(old_image_path),
            "rendered_pixels_changed": pixels_changed,
        }
        planned.append((metadata, image))
    output.mkdir(parents=True, exist_ok=False)
    report_dir.mkdir(parents=True, exist_ok=False)
    new_records = []
    for metadata, image in planned:
        image_path = output / metadata["image"]
        image.save(image_path)
        metadata["image_sha256"] = file_sha256(image_path)
        new_records.append(metadata)
    for split in SPLITS:
        with (output / f"{split}.csv").open(
            "x", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["image", "text", "writer_id", "sample_id", "source_type"],
            )
            writer.writeheader()
            writer.writerows(
                {
                    "image": row["image"],
                    "text": row["target_text"],
                    "writer_id": row["writer_id"],
                    "sample_id": row["sample_id"],
                    "source_type": row["source_type"],
                }
                for row in new_records
                if row["split"] == split
            )
    (output / "render_metadata.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in new_records),
        encoding="utf-8",
    )
    (output / "generation_config.json").write_text(
        json.dumps(config_data, indent=2, sort_keys=True), encoding="utf-8"
    )
    verification = verify_dataset(output)
    for key in (
        "projected_bounds_overflow_count",
        "actual_glyph_loss_count",
        "safe_region_ink_overflow_count",
        "saved_image_mismatch_count",
    ):
        if verification[key] != 0:
            raise ValueError(
                f"Saved corpus verification failed: {key}={verification[key]}"
            )
    (report_dir / "pixel_verification.json").write_text(
        json.dumps(verification, indent=2), encoding="utf-8"
    )
    after = snapshot_paths(references)
    if before != after:
        raise ValueError("Historical reference changed during generation")
    alignment_rows = [
        {
            "sample_id": row["sample_id"],
            "split": row["split"],
            **alignment(row["target_text"], 128),
        }
        for row in new_records
    ]
    (report_dir / "ctc_alignment_samples.json").write_text(
        json.dumps(alignment_rows, indent=2), encoding="utf-8"
    )
    old_verification_path = (
        ROOT / "benchmarks/ctc_audit/render_bounds_verification.json"
    )
    old_clipping = (
        json.loads(old_verification_path.read_text(encoding="utf-8"))[
            "samples_with_missing_ink"
        ]
        if old_verification_path.is_file()
        else None
    )
    report = {
        "dataset_version": version,
        "source_dataset": str(source.resolve()),
        "new_dataset": str(output.resolve()),
        "config": config_data,
        "historical_references_unchanged": before == after,
        "historical_checkpoint_sha256": file_sha256(
            ROOT / "models/generalization_continued_flor.weights.h5"
        ),
        "target_text_split_renderer_equal_by_id": True,
        "samples": len(new_records),
        "old_clipping_count_at_audit_threshold_220": old_clipping,
        "new_clipping_count_strict_nonbackground": verification[
            "actual_glyph_loss_count"
        ],
        "projected_bounds_overflow_count": verification[
            "projected_bounds_overflow_count"
        ],
        "safe_region_ink_overflow_count": verification[
            "safe_region_ink_overflow_count"
        ],
        "font_adjusted_samples": sum(
            row["was_resized_or_fitted"] for row in new_records
        ),
        "rendered_pixels_changed_samples": sum(
            row["rendered_pixels_changed"] for row in new_records
        ),
        "rendered_pixels_changed_percentage": 100
        * sum(row["rendered_pixels_changed"] for row in new_records)
        / len(new_records),
        "old": {
            name: distributions(
                [row for row in old_records if name == "global" or row["split"] == name]
            )
            for name in (*SPLITS, "global")
        },
        "new": {
            name: distributions(
                [row for row in new_records if name == "global" or row["split"] == name]
            )
            for name in (*SPLITS, "global")
        },
        "environment": {
            "python": sys.version,
            "pillow": pillow_version,
            "numpy": np.__version__,
        },
    }
    (report_dir / "generation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    reproducibility = {
        "historical_files_before": before,
        "historical_files_after": after,
        "new_dataset_files": snapshot_paths([output]),
        "renderer_fonts": {str(path): sha for path, sha in font_hashes.items()},
        "generator_sources": snapshot_paths(
            [Path(__file__), ROOT / "app/rendering.py", ROOT / "app/render_metadata.py"]
        ),
    }
    (report_dir / "reproducibility.json").write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs/clean512_v2.json"
    )
    args = parser.parse_args()
    config_data = json.loads(args.config.read_text(encoding="utf-8"))
    version = config_data["version"]
    if Path(version).name != version or version in (".", "..", ""):
        raise ValueError("Dataset version must be a single directory name")
    checkpoint = ROOT / "models/generalization_continued_flor.weights.h5"
    if file_sha256(checkpoint) != EXPECTED_CHECKPOINT_SHA256:
        raise ValueError(
            "Historical checkpoint does not match expected immutable SHA256"
        )
    report = build_version(
        ROOT / "datasets/synthetic/generalization",
        ROOT / "datasets/synthetic" / version,
        ROOT / "benchmarks" / version,
        config_data,
        historical_references(),
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in ("old", "new", "environment")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
