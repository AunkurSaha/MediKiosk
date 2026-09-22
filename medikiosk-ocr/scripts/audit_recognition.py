"""Evaluation-only CTC/renderer/width audit. Never trains or selects checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf
from build_generalization_dataset import FONT_NAMES, unique_phrases
from PIL import Image, ImageDraw, ImageFont
from train_generalization import (
    ROOT,
    RecognitionModel,
    load_manifest,
    metrics,
    values,
    worst_errors,
)

from app.benchmark import PrescriptionLexicon
from app.ctc import beam_decode, greedy_decode
from app.diagnostics import (
    alignment,
    assert_alignment,
    buckets,
    conditional_fields,
    schedule_accuracy,
    summarize,
)

OUTPUT = ROOT / "benchmarks" / "ctc_audit"
CACHE = ROOT / "outputs" / "ctc_audit"


def lexicon() -> PrescriptionLexicon:
    doses = frozenset(
        f"{strength} {unit}"
        for strength in (5, 10, 20, 40, 250, 500, 625, 650)
        for unit in values("units.txt")
    )
    return PrescriptionLexicon(
        frozenset(values("medicines.txt")),
        doses,
        frozenset(values("frequencies.txt")),
        frozenset(values("durations.txt")),
        forms=frozenset(values("forms.txt")),
        instructions=frozenset(values("instructions.txt")),
    )


def distribution(numbers: list[float]) -> dict:
    return {
        "min": float(np.min(numbers)),
        "p10": float(np.percentile(numbers, 10)),
        "median": float(np.median(numbers)),
        "p90": float(np.percentile(numbers, 90)),
        "max": float(np.max(numbers)),
    }


def aggregate(rows: list[dict]) -> dict:
    result = summarize(rows)
    result["fields"] = conditional_fields(
        [r["truth"] for r in rows], [r["prediction"] for r in rows], lexicon()
    )
    result["numeric_schedule"] = schedule_accuracy(
        [r["truth"] for r in rows], [r["prediction"] for r in rows]
    )
    result["alignment_ratio"] = distribution([r["alignment_ratio"] for r in rows])
    result["required_steps"] = distribution([r["minimum_ctc_steps"] for r in rows])
    result["ink_steps_ratio"] = distribution([r["ink_steps_ratio"] for r in rows])
    result["target_length"] = distribution([r["target_length"] for r in rows])
    result["adjacent_repeat_count"] = distribution(
        [r["adjacent_repeat_count"] for r in rows]
    )
    result["prediction_length"] = distribution([r["prediction_length"] for r in rows])
    result["output_time_steps"] = distribution([r["output_time_steps"] for r in rows])
    result["clipped_count"] = sum(r["render_clipped"] for r in rows)
    return result


def grouped(rows: list[dict]) -> dict:
    names = sorted({name for row in rows for name in row["buckets"]})
    return {
        name: aggregate([row for row in rows if name in row["buckets"]])
        for name in names
    }


def baseline_samples() -> list[dict]:
    result = []
    for split in ("train", "validation", "test"):
        samples = load_manifest(
            ROOT / "datasets" / "synthetic" / "generalization" / f"{split}.csv"
        )
        for index, sample in enumerate(samples):
            renderer = sample.writer_id.removeprefix("synthetic_renderer_")
            font_name = next(name for name in FONT_NAMES if Path(name).stem == renderer)
            font = ImageFont.truetype(
                str(Path("C:/Windows/Fonts") / font_name), 22 + index % 3
            )
            bbox = font.getbbox(sample.text)
            result.append(
                {
                    "id": sample.sample_id,
                    "split": split,
                    "renderer": renderer,
                    "truth": sample.text,
                    "path": str(sample.image),
                    "rendered_right_edge": 7 + index % 4 + bbox[2],
                }
            )
    return result


def renderer_samples(fit: bool = False) -> list[dict]:
    data_dir = ROOT / "datasets" / "synthetic" / "renderer_diagnostic"
    data_dir.mkdir(parents=True, exist_ok=True)
    used = {" ".join(row["truth"].split()) for row in baseline_samples()}
    phrases = [
        text for text in unique_phrases(1500, 917) if " ".join(text.split()) not in used
    ][:100]
    assert len(phrases) == 100
    sizes = []
    for text in phrases:
        size = 23
        if fit:
            while any(
                ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size).getbbox(
                    text
                )[2]
                > 496
                for name in FONT_NAMES
            ):
                size -= 1
        sizes.append(size)
    (data_dir / "phrases.json").write_text(
        json.dumps(phrases, indent=2), encoding="utf-8"
    )
    result = []
    for font_name in FONT_NAMES:
        renderer = Path(font_name).stem
        for index, text in enumerate(phrases):
            font = ImageFont.truetype(
                str(Path("C:/Windows/Fonts") / font_name), sizes[index]
            )
            prefix = "fit" if fit else "fixed"
            image_path = data_dir / f"{prefix}_{renderer}_{index:03d}.png"
            image = Image.new("L", (512, 64), 255)
            ImageDraw.Draw(image).text((8, 15), text, fill=0, font=font)
            image.save(image_path)
            result.append(
                {
                    "id": f"renderer_{prefix}_{renderer}_{index:03d}",
                    "split": "diagnostic_only",
                    "renderer": renderer,
                    "truth": text,
                    "path": str(image_path),
                    "font_size": sizes[index],
                    "rendered_right_edge": 8 + font.getbbox(text)[2],
                }
            )
    (data_dir / "NOT_FOR_TRAINING.txt").write_text(
        "Fixed-phrase renderer isolation. Evaluation only; never training or checkpoint selection.\n",
        encoding="utf-8",
    )
    return result


def evaluate(
    samples: list[dict], width: int, metadata: dict, checkpoint: Path, batch_size: int
) -> list[dict]:
    model = RecognitionModel(
        name=f"audit_{width}",
        image_shape=(64, width, 1),
        lexical_shape=(
            1,
            metadata["max_label_length"],
            len(metadata["characters"]) + 2,
        ),
        seed=metadata["seed"],
    )
    model.recognition.load_weights(checkpoint)
    rows = []
    for start in range(0, len(samples), batch_size):
        batch = samples[start : start + batch_size]
        tensors = []
        images = []
        for sample in batch:
            original = cv2.imread(sample["path"], cv2.IMREAD_GRAYSCALE)
            images.append(original)
            resized = cv2.resize(original, (width, 64), interpolation=cv2.INTER_LINEAR)
            tensors.append(((resized.astype(np.float32) / 127.5) - 1)[..., None])
        cache_paths = [CACHE / f"w{width}_{sample['id']}.npy" for sample in batch]
        if all(path.is_file() for path in cache_paths):
            logits = np.stack([np.load(path) for path in cache_paths])
        else:
            logits = model.recognition(np.asarray(tensors), training=False).numpy()
            for path, sample_logits in zip(cache_paths, logits):
                np.save(path, sample_logits)
        predictions = greedy_decode(
            tf.convert_to_tensor(logits), metadata["characters"]
        )
        for sample, prediction, original, sample_logits in zip(
            batch, predictions, images, logits
        ):
            steps = int(np.prod(sample_logits.shape[:-1]))
            measurement = alignment(sample["truth"], steps)
            assert_alignment(sample["truth"], steps)
            columns = np.where(np.any(original < 220, axis=0))[0]
            ink_width = int(columns[-1] - columns[0] + 1) if len(columns) else 0
            sample_metrics = metrics([sample["truth"]], [prediction])
            rows.append(
                {
                    **{key: value for key, value in sample.items() if key != "path"},
                    **measurement,
                    "original_image_width": original.shape[1],
                    "model_input_width": width,
                    "model_output_shape": list(sample_logits.shape),
                    "prediction": prediction,
                    "prediction_length": len(prediction),
                    "cer": sample_metrics["cer"],
                    "wer": sample_metrics["wer"],
                    "buckets": buckets(sample["truth"], lexicon().medicines),
                    "ink_width_pixels": ink_width,
                    "ink_steps_ratio": (ink_width / original.shape[1] * steps)
                    / measurement["minimum_ctc_steps"],
                    "render_clipped": sample["rendered_right_edge"] > original.shape[1],
                }
            )
        print(
            f"width={width} completed={min(start + batch_size, len(samples))}/{len(samples)}",
            flush=True,
        )
    return rows


def beam_predictions(
    samples: list[dict], width: int, characters: list[str]
) -> list[str]:
    result = []
    for sample in samples:
        logits = np.load(CACHE / f"w{width}_{sample['id']}.npy")
        result.extend(beam_decode(tf.convert_to_tensor(logits[None, ...]), characters))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "models" / "generalization_continued_flor.weights.h5",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--phase", choices=["geometry", "decoder", "renderer_fit"], default="geometry"
    )
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    checkpoint = args.checkpoint.resolve()
    metadata = json.loads(checkpoint.with_suffix(".json").read_text(encoding="utf-8"))
    checkpoint_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    cache_identity = CACHE / "checkpoint.sha256"
    if cache_identity.exists() and cache_identity.read_text() != checkpoint_hash:
        raise ValueError(
            "Logit cache belongs to a different checkpoint; use a separate cache directory"
        )
    cache_identity.write_text(checkpoint_hash, encoding="utf-8")
    if args.phase == "geometry":
        baseline = baseline_samples()
        rows = evaluate(baseline, 512, metadata, checkpoint, args.batch_size)
        (OUTPUT / "alignment_samples.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8"
        )
        summary = {
            "checkpoint_sha256": checkpoint_hash,
            "danger_margin_ratio": 1.5,
            "splits": {
                name: aggregate([r for r in rows if r["split"] == name])
                for name in ("train", "validation", "test")
            },
            "buckets": grouped(rows),
            "violations": [r for r in rows if r["alignment_status"] != "adequate"],
            "smallest_margin_samples": sorted(
                rows, key=lambda row: row["alignment_ratio"]
            )[:25],
            "clipped_count": sum(r["render_clipped"] for r in rows),
        }
        (OUTPUT / "alignment_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print("Alignment audit complete", flush=True)
        render_samples = renderer_samples()
        renderer_rows = evaluate(
            render_samples, 512, metadata, checkpoint, args.batch_size
        )
        (OUTPUT / "renderer_samples.json").write_text(
            json.dumps(renderer_rows, indent=2), encoding="utf-8"
        )
        renderer_summary = {
            name: aggregate([r for r in renderer_rows if r["renderer"] == name])
            for name in sorted({r["renderer"] for r in renderer_rows})
        }
        (OUTPUT / "renderer_summary.json").write_text(
            json.dumps(renderer_summary, indent=2), encoding="utf-8"
        )
        test_samples = [s for s in baseline if s["split"] == "test"]
        width_rows = evaluate(test_samples, 1024, metadata, checkpoint, args.batch_size)
        comparison = {
            "scope": "same_checkpoint_inference_only_not_retrained",
            "A_512": aggregate([r for r in rows if r["split"] == "test"]),
            "B_1024": aggregate(width_rows),
            "A_buckets": grouped([r for r in rows if r["split"] == "test"]),
            "B_buckets": grouped(width_rows),
            "C": "not_run_unless_sequence_diagnostics_support_it",
        }
        (OUTPUT / "geometry_samples.json").write_text(
            json.dumps(width_rows, indent=2), encoding="utf-8"
        )
        (OUTPUT / "geometry_summary.json").write_text(
            json.dumps(comparison, indent=2), encoding="utf-8"
        )
    elif args.phase == "renderer_fit":
        samples = renderer_samples(fit=True)
        rows = evaluate(samples, 512, metadata, checkpoint, args.batch_size)
        assert not any(row["render_clipped"] for row in rows)
        (OUTPUT / "renderer_fit_samples.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8"
        )
        report = {
            name: aggregate([r for r in rows if r["renderer"] == name])
            for name in sorted({r["renderer"] for r in rows})
        }
        (OUTPUT / "renderer_fit_summary.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    else:
        rows = json.loads(
            (OUTPUT / "alignment_samples.json").read_text(encoding="utf-8")
        )
        predictions = beam_predictions(rows, 512, metadata["characters"])
        beam_rows = [
            {**row, "prediction": prediction, "prediction_length": len(prediction)}
            for row, prediction in zip(rows, predictions)
        ]
        for row in beam_rows:
            row.update(
                {
                    key: value
                    for key, value in metrics(
                        [row["truth"]], [row["prediction"]]
                    ).items()
                    if key in ("cer", "wer")
                }
            )
        test_rows = [r for r in rows if r["split"] == "test"]
        beam_test_rows = [r for r in beam_rows if r["split"] == "test"]
        width_rows = json.loads(
            (OUTPUT / "geometry_samples.json").read_text(encoding="utf-8")
        )
        width_predictions = beam_predictions(width_rows, 1024, metadata["characters"])
        beam_width_rows = [
            {**row, "prediction": prediction, "prediction_length": len(prediction)}
            for row, prediction in zip(width_rows, width_predictions)
        ]
        report = {
            "beam_width": 50,
            "lexical_correction": False,
            "greedy": aggregate(test_rows),
            "beam": aggregate(beam_test_rows),
            "greedy_buckets": grouped(test_rows),
            "beam_buckets": grouped(beam_test_rows),
            "beam_splits": {
                name: aggregate([r for r in beam_rows if r["split"] == name])
                for name in ("train", "validation", "test")
            },
            "B_1024_beam": aggregate(beam_width_rows),
            "beam_worst_25": worst_errors(
                [r["truth"] for r in beam_test_rows],
                [r["prediction"] for r in beam_test_rows],
            ),
        }
        (OUTPUT / "decoder_samples.json").write_text(
            json.dumps(beam_rows, indent=2), encoding="utf-8"
        )
        (OUTPUT / "decoder_geometry_samples.json").write_text(
            json.dumps(beam_width_rows, indent=2), encoding="utf-8"
        )
        (OUTPUT / "decoder_summary.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(
            {
                "decoder_report": str(OUTPUT / "decoder_summary.json"),
                "beam_test_cer": report["beam"]["cer"],
            }
        )


if __name__ == "__main__":
    main()
