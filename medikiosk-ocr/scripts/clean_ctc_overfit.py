"""Prove Flor can memorize six clean lines without augmentation or dropout."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf
from Levenshtein import distance

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream" / "handwritten-text-recognition"
for path in (ROOT, UPSTREAM):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.ctc import blank_probability, greedy_decode  # noqa: E402
from app.dataset import load_manifest  # noqa: E402
from sarah.models.components.losses import CTCLoss  # noqa: E402
from sarah.models.recognition.flor import RecognitionModel  # noqa: E402

IMAGE_SHAPE = (64, 256, 1)


def prepare(manifest: Path):
    samples = load_manifest(manifest)
    if not 5 <= len(samples) <= 10:
        raise ValueError("The clean CTC diagnostic requires 5-10 samples")
    characters = sorted({char for sample in samples for char in sample.text})
    char_to_index = {char: index + 1 for index, char in enumerate(characters)}
    max_length = max(len(sample.text) for sample in samples)
    images, labels = [], []
    for sample in samples:
        image = cv2.imread(str(sample.image), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Cannot read {sample.image}")
        image = cv2.resize(image, (IMAGE_SHAPE[1], IMAGE_SHAPE[0]), interpolation=cv2.INTER_AREA)
        images.append(((image.astype(np.float32) / 127.5) - 1.0)[..., None])
        encoded = [char_to_index[char] for char in sample.text]
        labels.append(encoded + [0] * (max_length - len(encoded)))
    return samples, characters, np.asarray(images), np.asarray(labels, dtype=np.int32)


def mean_cer(truths: list[str], predictions: list[str]) -> float:
    return sum(distance(a, b) / max(1, len(a)) for a, b in zip(truths, predictions)) / len(truths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-epochs", type=int, default=150)
    parser.add_argument("--target-cer", type=float, default=0.01)
    parser.add_argument("--report-every", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "synthetic" / "clean_ctc" / "manifest.csv",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "models" / "clean_ctc_flor.weights.h5",
    )
    args = parser.parse_args()
    tf.keras.utils.set_random_seed(args.seed)
    samples, characters, images, labels = prepare(args.manifest.resolve())
    truths = [sample.text for sample in samples]
    model = RecognitionModel(
        name="recognition",
        image_shape=IMAGE_SHAPE,
        lexical_shape=(1, labels.shape[1], len(characters) + 2),
        seed=args.seed,
    )
    optimizer = tf.keras.optimizers.Adam(learning_rate=args.learning_rate, clipnorm=5.0)
    loss_fn = CTCLoss()
    initial_loss = final_loss = 0.0
    achieved_cer = 1.0
    predictions: list[str] = []
    best_cer = float("inf")
    checkpoint = args.checkpoint.resolve()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    for epoch in range(1, args.max_epochs + 1):
        with tf.GradientTape() as tape:
            # Inference mode intentionally disables Flor's 50-60% dropout during
            # this deterministic memorization test. Input augmentation is absent.
            logits = model.recognition(images, training=False)
            loss = loss_fn(labels, logits)
        gradients = tape.gradient(loss, model.recognition.trainable_weights)
        optimizer.apply_gradients(zip(gradients, model.recognition.trainable_weights))
        final_loss = float(loss.numpy())
        initial_loss = initial_loss or final_loss
        if epoch == 1 or epoch % args.report_every == 0:
            eval_logits = model.recognition(images, training=False)
            predictions = greedy_decode(eval_logits, characters)
            achieved_cer = mean_cer(truths, predictions)
            blank = blank_probability(eval_logits, characters)
            print(
                f"epoch={epoch} loss={final_loss:.6f} mean_cer={achieved_cer:.6f} "
                f"blank_probability={blank:.6f}",
                flush=True,
            )
            if achieved_cer < best_cer:
                best_cer = achieved_cer
                model.recognition.save_weights(checkpoint)
            if achieved_cer <= args.target_cer:
                break

    metadata = {
        "characters": characters,
        "max_label_length": labels.shape[1],
        "image_shape": IMAGE_SHAPE,
        "seed": args.seed,
        "model_version": "flor-clean-ctc-overfit-v1",
        "ctc_blank_index": len(characters) + 1,
        "augmentation": False,
        "model_dropout_during_training": False,
        "learning_rate": args.learning_rate,
    }
    checkpoint.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Rebuild and reload so success cannot depend on in-memory weights.
    reloaded = RecognitionModel(
        name="recognition_reload",
        image_shape=IMAGE_SHAPE,
        lexical_shape=(1, labels.shape[1], len(characters) + 2),
        seed=args.seed,
    )
    reloaded.recognition.load_weights(checkpoint)
    reload_logits = reloaded.recognition(images, training=False)
    reload_predictions = greedy_decode(reload_logits, characters)
    reload_cer = mean_cer(truths, reload_predictions)
    result = {
        "samples": len(samples),
        "epochs": epoch,
        "initial_loss": initial_loss,
        "final_loss": final_loss,
        "mean_cer": reload_cer,
        "target_cer": args.target_cer,
        "passed": reload_cer <= args.target_cer,
        "augmentation": False,
        "model_dropout_during_training": False,
        "ctc_blank_index": len(characters) + 1,
        "blank_probability": blank_probability(reload_logits, characters),
        "predictions": [
            {"truth": truth, "prediction": prediction, "cer": distance(truth, prediction) / len(truth)}
            for truth, prediction in zip(truths, reload_predictions)
        ],
        "elapsed_seconds": time.perf_counter() - started,
        "checkpoint": str(checkpoint.relative_to(ROOT)),
    }
    (ROOT / "benchmarks" / "clean_ctc_overfit.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
