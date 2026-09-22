from pathlib import Path

import cv2
import numpy as np

from app.augmentation import augment, load_preset
from app.dataset import load_manifest, writer_independent_split
from scripts.generate_prescription_text import generate

ROOT = Path(__file__).resolve().parents[1]


def test_generator_is_deterministic():
    first = generate(8, 17, ROOT / "configs")
    second = generate(8, 17, ROOT / "configs")
    assert first == second
    assert len(first) == 8
    assert all(line.strip() for line in first)


def test_manifest_and_writer_independent_split():
    manifest = ROOT / "datasets" / "synthetic" / "tiny" / "manifest.csv"
    samples = load_manifest(manifest)
    split = writer_independent_split(samples, seed=17)
    writers = [{sample.writer_id for sample in split[name]} for name in split]
    assert len(samples) == 24
    assert not (writers[0] & writers[1] or writers[0] & writers[2] or writers[1] & writers[2])


def test_augmentation_is_deterministic_and_preserves_shape():
    preset = load_preset(ROOT / "configs" / "prescription_augmentation.json")
    image = np.full((64, 512), 255, dtype=np.uint8)
    cv2.putText(image, "OCR", (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
    first = augment(image, preset, seed=3)
    second = augment(image, preset, seed=3)
    assert first.shape == image.shape
    assert np.array_equal(first, second)
    assert not np.array_equal(first, image)
