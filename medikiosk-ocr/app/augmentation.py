"""Moderate deterministic phone-photo augmentation for line images."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream" / "handwritten-text-recognition"
if str(UPSTREAM) not in sys.path:
    sys.path.insert(0, str(UPSTREAM))

from sarah.data.augmentor import Augmentor  # noqa: E402


def load_preset(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def augment(image: np.ndarray, preset: dict, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    original_shape = image.shape[:2]
    upstream = Augmentor(
        perspective=[1.0, preset["perspective_fraction"]],
        rotate=[1.0, preset["rotation_degrees"]],
        gaussian_noise=[preset["gaussian_noise_probability"], 0.08],
        gaussian_blur=[
            preset["gaussian_blur_probability"],
            preset["gaussian_blur_kernel"],
            1,
        ],
        seed=seed,
    )
    result = upstream.augmentation(image.copy())
    if result.shape[:2] != original_shape:
        result = cv2.resize(result, (original_shape[1], original_shape[0]), interpolation=cv2.INTER_AREA)

    if rng.random() < preset["brightness_probability"]:
        factor = rng.uniform(*preset["brightness_range"])
        result = np.clip(result.astype(np.float32) * factor, 0, 255).astype(np.uint8)
    if rng.random() < preset["jpeg_probability"]:
        quality = int(rng.integers(*preset["jpeg_quality_range"], endpoint=True))
        ok, encoded = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            result = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    return result
