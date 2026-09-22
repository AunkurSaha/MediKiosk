"""One-time loading wrapper around the upstream Flor line recognizer."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream" / "handwritten-text-recognition"
if str(UPSTREAM) not in sys.path:
    sys.path.insert(0, str(UPSTREAM))

from app.ctc import greedy_decode  # noqa: E402
from sarah.models.recognition.flor import RecognitionModel  # noqa: E402

IMAGE_SHAPE = (64, 512, 1)


class FlorLineRecognizer:
    def __init__(self, checkpoint: Path, metadata_path: Path | None = None) -> None:
        metadata_path = metadata_path or checkpoint.with_suffix(".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.characters: list[str] = metadata["characters"]
        self.model_version: str = metadata["model_version"]
        self.model = RecognitionModel(
            name="recognition",
            image_shape=tuple(metadata.get("image_shape", IMAGE_SHAPE)),
            lexical_shape=(1, metadata["max_label_length"], len(self.characters) + 2),
            seed=metadata.get("seed", 29),
        )
        self.model.recognition.load_weights(checkpoint)
        self.image_shape = tuple(metadata.get("image_shape", IMAGE_SHAPE))
        self._warm()

    def _warm(self) -> None:
        self.model.recognition(np.ones((1, *self.image_shape), dtype=np.float32))

    def preprocess(self, content: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None or image.size < 16:
            raise ValueError("OCR_RECOGNITION_FAILED")
        target_height, target_width, _ = self.image_shape
        scale = min(target_width / image.shape[1], target_height / image.shape[0])
        resized = cv2.resize(
            image,
            (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
        canvas = np.full((target_height, target_width), 255, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        return ((canvas.astype(np.float32) / 127.5) - 1.0)[..., None]

    def recognize(self, content: bytes) -> tuple[str, float]:
        image = self.preprocess(content)
        started = time.perf_counter()
        logits = self.model.recognition(image[None, ...], training=False)
        text = greedy_decode(logits, self.characters)[0]
        return text, (time.perf_counter() - started) * 1000
