"""Re-evaluate every split from the selected checkpoint, independent of training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from train_generalization import (
    ROOT,
    RecognitionModel,
    batches,
    image_tensor,
    load_manifest,
    metrics,
    predict,
    worst_errors,
)

from app.ctc import beam_decode
from app.render_metadata import file_sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dataset-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--training-report", type=Path)
    parser.add_argument("--decoder", choices=("greedy", "beam"), default="greedy")
    parser.add_argument("--beam-width", type=int, default=50)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    metadata = json.loads(checkpoint.with_suffix(".json").read_text(encoding="utf-8"))
    data_dir = (
        args.dataset_dir or ROOT / "datasets/synthetic/generalization"
    ).resolve()
    if args.dataset_dir and not args.output:
        raise ValueError(
            "Versioned evaluation requires a separate --output; historical reports are immutable"
        )
    report_path = (
        args.output.resolve()
        if args.output
        else ROOT / "benchmarks/generalization.json"
    )
    if args.output and report_path.exists():
        raise FileExistsError("Refusing to overwrite an evaluation artifact")
    if args.output and (
        not report_path.is_relative_to(ROOT / "benchmarks")
        or report_path.is_relative_to(ROOT / "benchmarks/ctc_audit")
    ):
        raise ValueError("Evaluation output must be in a new OCR benchmark location")
    if tuple(metadata["image_shape"]) != (64, 512, 1):
        raise ValueError("This baseline evaluator requires unchanged 64x512x1 geometry")
    characters = metadata["characters"]
    model = RecognitionModel(
        name="recognition_evaluation",
        image_shape=tuple(metadata["image_shape"]),
        lexical_shape=(1, metadata["max_label_length"], len(characters) + 2),
        seed=metadata["seed"],
    )
    model.recognition.load_weights(checkpoint)
    source_report = args.training_report or (report_path if not args.output else None)
    report = (
        json.loads(source_report.read_text(encoding="utf-8")) if source_report else {}
    )
    report["checkpoint_sha256"] = file_sha256(checkpoint)
    report["decoder"] = args.decoder
    report["beam_width"] = args.beam_width if args.decoder == "beam" else None
    report["dataset_dir"] = str(data_dir)
    report["checkpoint"] = str(checkpoint.relative_to(ROOT))
    report["field_matching_whitespace_normalized"] = True
    for split in ("train", "validation", "test"):
        samples = load_manifest(data_dir / f"{split}.csv")
        truths = [sample.text for sample in samples]
        if args.decoder == "greedy":
            predictions = predict(
                model.recognition, samples, characters, args.batch_size
            )
        else:
            predictions = []
            for batch in batches(samples, args.batch_size):
                images = np.asarray([image_tensor(sample, None, 0) for sample in batch])
                logits = model.recognition(images, training=False)
                predictions.extend(beam_decode(logits, characters, args.beam_width))
        report[split] = metrics(truths, predictions)
        if split == "test":
            report["worst_test_errors"] = worst_errors(truths, predictions)
        print(json.dumps({"split": split, "metrics": report[split]}), flush=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if args.output:
        with report_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2))
    else:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
