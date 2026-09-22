"""Prescription-line manifest loading and writer-independent splitting."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

ALLOWED_SOURCE_TYPES = {"synthetic", "volunteer", "approved_deidentified"}
REQUIRED_COLUMNS = {"image", "text", "writer_id", "sample_id", "source_type"}


@dataclass(frozen=True)
class Sample:
    image: Path
    text: str
    writer_id: str
    sample_id: str
    source_type: str


def load_manifest(path: Path) -> list[Sample]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError(f"Manifest requires columns: {sorted(REQUIRED_COLUMNS)}")
        samples = []
        seen_ids: set[str] = set()
        for row in reader:
            if row["source_type"] not in ALLOWED_SOURCE_TYPES:
                raise ValueError(f"Unsupported source_type: {row['source_type']}")
            if row["sample_id"] in seen_ids:
                raise ValueError(f"Duplicate sample_id: {row['sample_id']}")
            seen_ids.add(row["sample_id"])
            image = (path.parent / row["image"]).resolve()
            if not image.is_file():
                raise ValueError(f"Missing image for {row['sample_id']}")
            samples.append(
                Sample(
                    image=image,
                    text=row["text"],
                    writer_id=row["writer_id"],
                    sample_id=row["sample_id"],
                    source_type=row["source_type"],
                )
            )
    return samples


def writer_independent_split(
    samples: list[Sample], seed: int = 17
) -> dict[str, list[Sample]]:
    writers = sorted({sample.writer_id for sample in samples})
    random.Random(seed).shuffle(writers)
    if len(writers) < 3:
        raise ValueError("At least three writers are required for writer-independent splits")
    train_end = max(1, round(len(writers) * 0.7))
    validation_end = max(train_end + 1, round(len(writers) * 0.85))
    writer_sets = {
        "train": set(writers[:train_end]),
        "validation": set(writers[train_end:validation_end]),
        "test": set(writers[validation_end:]),
    }
    return {
        name: [sample for sample in samples if sample.writer_id in selected]
        for name, selected in writer_sets.items()
    }


def as_upstream_partition(samples: list[Sample]) -> dict[str, list[dict]]:
    """Translate our manifest records to Sarah's documented source-item shape."""
    return {
        "training": [
            {
                "id": sample.sample_id,
                "image": str(sample.image),
                "bbox": [],
                "text": sample.text,
                "writer": sample.writer_id,
            }
            for sample in samples
        ],
        "validation": [],
        "test": [],
    }
