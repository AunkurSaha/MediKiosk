"""Train Flor with dropout and light augmentation; evaluate unseen renderers."""

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

from sarah.models.components.losses import CTCLoss
from sarah.models.recognition.flor import RecognitionModel

from app.augmentation import augment, load_preset
from app.benchmark import (
    PrescriptionLexicon,
    classify_error,
    error_rates,
    exact_line_accuracy,
    prescription_field_accuracy,
)
from app.ctc import greedy_decode
from app.dataset import Sample, load_manifest
from app.diagnostics import assert_alignment

IMAGE_SHAPE = (64, 512, 1)


def values(name: str) -> list[str]:
    return [
        line.strip()
        for line in (ROOT / "configs" / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def image_tensor(sample: Sample, preset: dict | None, seed: int) -> np.ndarray:
    image = cv2.imread(str(sample.image), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Cannot read {sample.image}")
    if preset is not None:
        image = augment(image, preset, seed)
    image = cv2.resize(
        image, (IMAGE_SHAPE[1], IMAGE_SHAPE[0]), interpolation=cv2.INTER_AREA
    )
    return ((image.astype(np.float32) / 127.5) - 1.0)[..., None]


def encode(samples: list[Sample], mapping: dict[str, int], length: int) -> np.ndarray:
    return np.asarray(
        [
            [mapping[char] for char in sample.text] + [0] * (length - len(sample.text))
            for sample in samples
        ],
        dtype=np.int32,
    )


def batches(samples: list[Sample], batch_size: int):
    for start in range(0, len(samples), batch_size):
        yield samples[start : start + batch_size]


def predict(
    model, samples: list[Sample], characters: list[str], batch_size: int
) -> list[str]:
    result = []
    for batch in batches(samples, batch_size):
        images = np.asarray([image_tensor(sample, None, 0) for sample in batch])
        result.extend(greedy_decode(model(images, training=False), characters))
    return result


def metrics(truths: list[str], predictions: list[str]) -> dict:
    strengths = ["5", "10", "20", "40", "250", "500", "625", "650"]
    doses = frozenset(
        f"{strength} {unit}" for strength in strengths for unit in values("units.txt")
    )
    lexicon = PrescriptionLexicon(
        medicines=frozenset(values("medicines.txt")),
        doses=doses,
        frequencies=frozenset(values("frequencies.txt")),
        durations=frozenset(values("durations.txt")),
    )
    cer, wer = error_rates(truths, predictions)
    return {
        "cer": cer,
        "wer": wer,
        "exact_line_accuracy": exact_line_accuracy(truths, predictions),
        **prescription_field_accuracy(truths, predictions, lexicon),
    }


def worst_errors(
    truths: list[str], predictions: list[str], limit: int = 25
) -> list[dict]:
    rows = []
    for truth, prediction in zip(truths, predictions):
        sample_cer = error_rates([truth], [prediction])[0]
        if sample_cer:
            rows.append(
                {
                    "ground_truth": truth,
                    "prediction": prediction,
                    "cer": sample_cer,
                    "error_type": classify_error(truth, prediction),
                }
            )
    return sorted(rows, key=lambda row: row["cer"], reverse=True)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--early-stopping-patience", type=int, default=5)
    parser.add_argument("--early-stopping-min-delta", type=float, default=0.002)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-eval-samples", type=int)
    parser.add_argument("--dataset-dir", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--resume-weights", type=Path)
    parser.add_argument("--start-epoch", type=int, default=1)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "models" / "generalization_flor.weights.h5",
    )
    args = parser.parse_args()
    tf.keras.utils.set_random_seed(args.seed)
    data_dir = (
        args.dataset_dir or ROOT / "datasets/synthetic/generalization"
    ).resolve()
    report_dir = (args.report_dir or ROOT / "benchmarks").resolve()
    if args.dataset_dir and data_dir != ROOT / "datasets/synthetic/generalization":
        if not args.report_dir:
            raise ValueError("Versioned datasets require a separate --report-dir")
        if report_dir.exists() or args.checkpoint.exists():
            raise FileExistsError(
                "Versioned training refuses existing report/checkpoint destinations"
            )
        if (
            not report_dir.is_relative_to(ROOT / "benchmarks")
            or report_dir == ROOT / "benchmarks"
        ):
            raise ValueError(
                "Versioned reports must have their own OCR benchmark subdirectory"
            )
        if not args.checkpoint.resolve().is_relative_to(ROOT / "models"):
            raise ValueError(
                "Versioned checkpoints must be inside the isolated OCR models directory"
            )
    report_dir.mkdir(parents=True, exist_ok=True)
    splits = {
        name: load_manifest(data_dir / f"{name}.csv")
        for name in ("train", "validation", "test")
    }
    if args.max_train_samples:
        splits["train"] = splits["train"][: args.max_train_samples]
    if args.max_eval_samples:
        splits["validation"] = splits["validation"][: args.max_eval_samples]
        splits["test"] = splits["test"][: args.max_eval_samples]
    all_samples = [sample for split in splits.values() for sample in split]
    characters = sorted({char for sample in all_samples for char in sample.text})
    mapping = {char: index + 1 for index, char in enumerate(characters)}
    max_length = max(len(sample.text) for sample in all_samples)
    model = RecognitionModel(
        name="recognition",
        image_shape=IMAGE_SHAPE,
        lexical_shape=(1, max_length, len(characters) + 2),
        seed=args.seed,
    )
    optimizer = tf.keras.optimizers.AdamW(
        learning_rate=args.learning_rate,
        beta_1=0.5,
        beta_2=0.99,
        weight_decay=0.01,
        clipnorm=5.0,
    )
    loss_fn = CTCLoss()
    preset = load_preset(ROOT / "configs" / "light_augmentation.json")
    checkpoint = args.checkpoint.resolve()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    best_validation_cer = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0
    history = []
    started = time.perf_counter()
    rng = np.random.default_rng(args.seed)
    if args.resume_weights:
        model.recognition.load_weights(args.resume_weights.resolve())
        recovered_predictions = predict(
            model.recognition, splits["validation"], characters, args.batch_size
        )
        recovered_metrics = metrics(
            [sample.text for sample in splits["validation"]], recovered_predictions
        )
        best_validation_cer = recovered_metrics["cer"]
        best_epoch = None  # A weights-only checkpoint does not prove its source epoch.
        model.recognition.save_weights(checkpoint)
        print(
            json.dumps({"recovered_epoch": None, "validation": recovered_metrics}),
            flush=True,
        )
    patience_best_cer = best_validation_cer
    for epoch in range(args.start_epoch, args.start_epoch + args.epochs):
        order = rng.permutation(len(splits["train"]))
        train_samples = [splits["train"][index] for index in order]
        losses = []
        for batch_index, batch in enumerate(batches(train_samples, args.batch_size)):
            images = np.asarray(
                [
                    image_tensor(
                        sample,
                        preset,
                        args.seed
                        + epoch * 100_000
                        + batch_index * args.batch_size
                        + index,
                    )
                    for index, sample in enumerate(batch)
                ]
            )
            labels = encode(batch, mapping, max_length)
            with tf.GradientTape() as tape:
                logits = model.recognition(
                    images, training=True
                )  # Flor dropout restored.
                time_steps = int(np.prod(logits.shape[1:-1]))
                for sample in batch:
                    assert_alignment(sample.text, time_steps)
                loss = loss_fn(labels, logits)
            gradients = tape.gradient(loss, model.recognition.trainable_weights)
            optimizer.apply_gradients(
                zip(gradients, model.recognition.trainable_weights)
            )
            losses.append(float(loss.numpy()))
        validation_predictions = predict(
            model.recognition, splits["validation"], characters, args.batch_size
        )
        validation = metrics(
            [sample.text for sample in splits["validation"]], validation_predictions
        )
        history.append(
            {
                "epoch": epoch,
                "loss": sum(losses) / len(losses),
                "validation": validation,
            }
        )
        print(json.dumps(history[-1]), flush=True)
        if validation["cer"] < best_validation_cer:
            best_validation_cer = validation["cer"]
            best_epoch = epoch
            model.recognition.save_weights(checkpoint)
        if validation["cer"] < patience_best_cer - args.early_stopping_min_delta:
            patience_best_cer = validation["cer"]
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        progress = {
            "status": "training",
            "history": history,
            "best_epoch": best_epoch,
            "best_validation_cer": best_validation_cer,
            "warm_restart": bool(args.resume_weights),
            "batch_size": args.batch_size,
        }
        (report_dir / "generalization_progress.json").write_text(
            json.dumps(progress, indent=2), encoding="utf-8"
        )
        if epochs_without_improvement >= args.early_stopping_patience:
            print(f"early_stopping epoch={epoch} best_epoch={best_epoch}", flush=True)
            break
    model.recognition.load_weights(checkpoint)
    train_predictions = predict(
        model.recognition, splits["train"], characters, args.batch_size
    )
    validation_predictions = predict(
        model.recognition, splits["validation"], characters, args.batch_size
    )
    test_predictions = predict(
        model.recognition, splits["test"], characters, args.batch_size
    )
    train_truths = [sample.text for sample in splits["train"]]
    validation_truths = [sample.text for sample in splits["validation"]]
    test_truths = [sample.text for sample in splits["test"]]
    report = {
        "scope": "bounded_smoke"
        if args.max_train_samples or args.max_eval_samples
        else "full_synthetic",
        "dropout_enabled": True,
        "augmentation_preset": "light_augmentation.json",
        "split_counts": {name: len(samples) for name, samples in splits.items()},
        "renderer_overlap": False,
        "phrase_overlap": False,
        "best_epoch": best_epoch,
        "best_validation_cer": best_validation_cer,
        "train": metrics(train_truths, train_predictions),
        "validation": metrics(validation_truths, validation_predictions),
        "test": metrics(test_truths, test_predictions),
        "worst_test_errors": worst_errors(test_truths, test_predictions),
        "epochs_requested": args.epochs,
        "epochs_completed": len(history),
        "start_epoch": args.start_epoch,
        "warm_restart": bool(args.resume_weights),
        "optimizer_state_restored": False,
        "source_checkpoint_epoch": None,
        "epoch_labels_are_continuation_labels": bool(args.resume_weights),
        "batch_size": args.batch_size,
        "elapsed_seconds": time.perf_counter() - started,
        "history": history,
        "dataset_dir": str(data_dir),
    }
    output = report_dir / "generalization.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    checkpoint.with_suffix(".json").write_text(
        json.dumps(
            {
                "characters": characters,
                "max_label_length": max_length,
                "image_shape": IMAGE_SHAPE,
                "seed": args.seed,
                "model_version": "flor-synthetic-generalization-v1",
                "ctc_blank_index": len(characters) + 1,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
