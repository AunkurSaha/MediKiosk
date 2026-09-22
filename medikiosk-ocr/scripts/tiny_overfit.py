"""Run a bounded CPU overfit test with upstream Flor + upstream CTC loss."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream" / "handwritten-text-recognition"
for path in (ROOT, UPSTREAM):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.dataset import load_manifest  # noqa: E402
from app.ctc import greedy_decode  # noqa: E402
from sarah.models.components.losses import CTCLoss  # noqa: E402
from sarah.models.recognition.flor import RecognitionModel  # noqa: E402

IMAGE_SHAPE = (64, 512, 1)


def prepare(manifest: Path):
    samples = load_manifest(manifest)
    characters = sorted({char for sample in samples for char in sample.text})
    char_to_index = {char: index + 1 for index, char in enumerate(characters)}
    max_length = max(len(sample.text) for sample in samples)
    images, labels = [], []
    for sample in samples:
        image = cv2.imread(str(sample.image), cv2.IMREAD_GRAYSCALE)
        image = cv2.resize(image, (IMAGE_SHAPE[1], IMAGE_SHAPE[0]), interpolation=cv2.INTER_AREA)
        images.append(((image.astype(np.float32) / 127.5) - 1.0)[..., None])
        encoded = [char_to_index[char] for char in sample.text]
        labels.append(encoded + [0] * (max_length - len(encoded)))
    return samples, characters, np.asarray(images), np.asarray(labels, dtype=np.int32)


def cer(truth: str, prediction: str) -> float:
    import Levenshtein

    return Levenshtein.distance(truth, prediction) / max(1, len(truth))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "synthetic" / "tiny" / "manifest.csv",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "models" / "tiny_flor.weights.h5",
    )
    args = parser.parse_args()
    tf.keras.utils.set_random_seed(args.seed)
    samples, characters, images, labels = prepare(args.manifest.resolve())
    model = RecognitionModel(
        name="recognition",
        image_shape=IMAGE_SHAPE,
        lexical_shape=(1, labels.shape[1], len(characters) + 2),
        seed=args.seed,
    )
    optimizer = tf.keras.optimizers.Adam(learning_rate=2e-3)
    loss_fn = CTCLoss()
    losses = []
    started = time.perf_counter()
    for epoch in range(args.epochs):
        with tf.GradientTape() as tape:
            logits = model.recognition(images, training=True)
            loss = loss_fn(labels, logits)
        gradients = tape.gradient(loss, model.recognition.trainable_weights)
        optimizer.apply_gradients(zip(gradients, model.recognition.trainable_weights))
        losses.append(float(loss.numpy()))
        print(f"epoch={epoch + 1} loss={losses[-1]:.6f}", flush=True)

    checkpoint = args.checkpoint.resolve()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    model.recognition.save_weights(checkpoint)
    predictions = greedy_decode(model.recognition(images[:1], training=False), characters)
    result = {
        "samples": len(samples),
        "device": "cpu",
        "epochs": args.epochs,
        "initial_loss": losses[0],
        "final_loss": losses[-1],
        "truth": samples[0].text,
        "prediction": predictions[0],
        "cer": cer(samples[0].text, predictions[0]),
        "elapsed_seconds": time.perf_counter() - started,
        "checkpoint": (
            str(checkpoint.relative_to(ROOT)) if checkpoint.is_relative_to(ROOT) else str(checkpoint)
        ),
        "model_version": "flor-tiny-synthetic-v0",
    }
    metadata = {
        "characters": characters,
        "max_label_length": labels.shape[1],
        "image_shape": IMAGE_SHAPE,
        "seed": args.seed,
        "model_version": result["model_version"],
    }
    checkpoint.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    benchmark = ROOT / "benchmarks" / "tiny_overfit.json"
    benchmark.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
