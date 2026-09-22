"""One frozen controlled baseline; never tunes from test or resumes weights."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import time
from itertools import pairwise

import numpy as np
import tensorflow as tf
from audit_recognition import lexicon
from train_generalization import (
    ROOT,
    UPSTREAM,
    CTCLoss,
    RecognitionModel,
    batches,
    encode,
    image_tensor,
    load_manifest,
    load_preset,
    metrics,
    predict,
)

from app.benchmark import _find, error_rates
from app.ctc import beam_decode, greedy_decode
from app.diagnostics import (
    alignment,
    assert_alignment,
    buckets,
    conditional_fields,
    summarize,
)
from app.render_metadata import file_sha256, verify_dataset

LABEL = "This is a newly specified controlled clean512_v2 baseline, not an exact reproduction of the historical interrupted training run."
OLD = ROOT / "models/generalization_continued_flor.weights.h5"
OLD_SHA = "386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef"
DATA = ROOT / "datasets/synthetic/clean512_v2"
REPORT = ROOT / "benchmarks/clean512_v2_controlled"
OLD_REPORT = ROOT / "benchmarks/clean512_v2_old_checkpoint"
CHECKPOINT = ROOT / "models/clean512_v2_controlled_flor.weights.h5"


def write(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)


def snapshot():
    paths = [OLD, OLD.with_suffix(".json")]
    for directory in (
        DATA,
        ROOT / "datasets/synthetic/generalization",
        ROOT / "benchmarks/ctc_audit",
    ):
        paths.extend(p for p in directory.rglob("*") if p.is_file())
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in sorted(paths)}


def describe(rows):
    if not rows:
        return {"samples": 0, "cer": None, "wer": None, "exact_line_accuracy": None}
    result = summarize(rows)
    normalized = [
        {
            "truth": " ".join(r["truth"].split()),
            "prediction": " ".join(r["prediction"].split()),
        }
        for r in rows
    ]
    result["whitespace_normalized"] = summarize(normalized)
    result["fields"] = conditional_fields(
        [r["truth"] for r in rows], [r["prediction"] for r in rows], lexicon()
    )
    result["buckets"] = {
        name: summarize([r for r in rows if name in r["buckets"]])
        for name in sorted({b for r in rows for b in r["buckets"]})
    }
    result["non_whitespace_adjacent_repeat"] = describe_basic(
        [
            r
            for r in rows
            if any(a == b and not a.isspace() for a, b in pairwise(r["truth"]))
        ]
    )
    result["special_exact"] = {}
    for value, field in (
        ("Amoxicillin", "medicines"),
        ("Cetirizine", "medicines"),
        ("Paracetamol", "medicines"),
        ("1-1-1", "frequencies"),
    ):
        subset = [
            r for r in rows if _find(r["truth"], getattr(lexicon(), field)) == value
        ]
        result["special_exact"][value] = {
            "N": len(subset),
            "accuracy": sum(
                _find(r["prediction"], getattr(lexicon(), field)) == value
                for r in subset
            )
            / len(subset)
            if subset
            else None,
        }
    result["fitted_subgroups"] = {
        str(flag): describe_basic([r for r in rows if r["fitted"] == flag])
        for flag in (False, True)
    }
    result["renderers"] = {
        name: describe_basic([r for r in rows if r["renderer"] == name])
        for name in sorted({r["renderer"] for r in rows})
    }
    result["font_bands"] = {
        name: describe_basic([r for r in rows if low <= r["final_font_size"] <= high])
        for name, low, high in (("14-17", 14, 17), ("18-21", 18, 21), ("22-24", 22, 24))
    }
    return result


def describe_basic(rows):
    return (
        summarize(rows)
        if rows
        else {"samples": 0, "cer": None, "wer": None, "exact_line_accuracy": None}
    )


def evaluate(model, characters, splits, metadata, output):
    output.mkdir(exist_ok=False)
    all_rows = {decoder: {} for decoder in ("greedy", "beam50")}
    # Both validation decoders are evaluated and the decision saved BEFORE test inference.
    for split in ("validation", "train", "test"):
        rows = {decoder: [] for decoder in all_rows}
        for batch in batches(splits[split], 32):
            logits = model(
                np.asarray([image_tensor(s, None, 0) for s in batch]), training=False
            )
            for decoder, predictions in (
                ("greedy", greedy_decode(logits, characters)),
                ("beam50", beam_decode(logits, characters, 50)),
            ):
                for sample, prediction in zip(batch, predictions):
                    m = metadata[sample.sample_id]
                    rows[decoder].append(
                        {
                            "id": sample.sample_id,
                            "renderer": m["renderer"],
                            "truth": sample.text,
                            "prediction": prediction,
                            "original_requested_font_size": m[
                                "original_requested_font_size"
                            ],
                            "final_font_size": m["final_font_size"],
                            "fitted": m["was_resized_or_fitted"],
                            "cer": error_rates([sample.text], [prediction])[0],
                            "buckets": buckets(sample.text, lexicon().medicines),
                            **alignment(sample.text, 128),
                        }
                    )
        for decoder, decoded_rows in rows.items():
            all_rows[decoder][split] = decoded_rows
            write(output / f"{decoder}_{split}_rows.json", decoded_rows)
            write(output / f"{decoder}_{split}_metrics.json", describe(decoded_rows))
        if split == "validation":
            cers = {decoder: summarize(rows[decoder])["cer"] for decoder in rows}
            preferred = "beam50" if cers["beam50"] < cers["greedy"] else "greedy"
            write(
                output / "decoder_lock.json",
                {
                    "validation_cer": cers,
                    "preferred": preferred,
                    "tie_rule": "greedy",
                    "test_inference_has_started": False,
                    "qualification": "validation-preferred under the renderer-conditioned validation split",
                },
            )
        print(
            json.dumps(
                {
                    "evaluation": str(output),
                    "split": split,
                    "metrics": {d: summarize(rows[d]) for d in rows},
                }
            ),
            flush=True,
        )
    worst = sorted(all_rows[preferred]["test"], key=lambda r: (-r["cer"], r["id"]))[:25]
    for row in worst:
        labels = []
        if _find(row["truth"], lexicon().medicines) != _find(
            row["prediction"], lexicon().medicines
        ):
            labels.append("medicine mismatch; inspect internal deletion")
        if "-" in row["truth"] and row["prediction"].count("-") < row["truth"].count(
            "-"
        ):
            labels.append("hyphen loss / possible schedule truncation")
        if _find(row["truth"], lexicon().instructions) != _find(
            row["prediction"], lexicon().instructions
        ):
            labels.append("instruction mismatch")
        row["descriptive_patterns"] = labels or [
            "other substitution/insertion/deletion"
        ]
    write(output / "worst25_validation_selected_test_errors.json", worst)
    return {d: {s: describe(r) for s, r in v.items()} for d, v in all_rows.items()}


def main():
    if any(
        p.exists()
        for p in (REPORT, OLD_REPORT, CHECKPOINT, CHECKPOINT.with_suffix(".json"))
    ):
        raise FileExistsError("Refusing existing controlled run destinations")
    if file_sha256(OLD) != OLD_SHA:
        raise ValueError("Historical checkpoint hash mismatch")
    before = snapshot()
    splits = {
        s: load_manifest(DATA / f"{s}.csv") for s in ("train", "validation", "test")
    }
    if {s: len(v) for s, v in splits.items()} != {
        "train": 700,
        "validation": 100,
        "test": 200,
    }:
        raise ValueError("Split counts changed")
    metadata = {
        r["sample_id"]: r
        for r in map(
            json.loads, (DATA / "render_metadata.jsonl").read_text().splitlines()
        )
    }
    characters = sorted({c for rows in splits.values() for s in rows for c in s.text})
    max_length = max(len(s.text) for rows in splits.values() for s in rows)
    preset_path = ROOT / "configs/light_augmentation.json"
    config = {
        "experiment_id": "clean512_v2 controlled baseline",
        "label": LABEL,
        "dataset_path": str(DATA),
        "immutable_hashes": before,
        "input_shape": [64, 512, 1],
        "architecture": "Flor unchanged",
        "architecture_hash": file_sha256(UPSTREAM / "sarah/models/recognition/flor.py"),
        "ctc": {
            "characters": characters,
            "padding": 0,
            "first_label": 1,
            "blank": len(characters) + 1,
            "max_label_length": max_length,
            "output_steps": 128,
            "image_normalization": "grayscale /127.5 -1, INTER_AREA resize",
        },
        "initialization": "from scratch; no restored weights or optimizer",
        "optimizer": {
            "name": "AdamW",
            "learning_rate": 0.001,
            "beta1": 0.5,
            "beta2": 0.99,
            "weight_decay": 0.01,
            "clipnorm": 5.0,
        },
        "batch_size": 32,
        "seed": 41,
        "dropout": "unchanged Flor: gated/CNN .1; directional LSTM input .5; final .6",
        "augmentation": {
            "train_only": True,
            "configuration": json.loads(preset_path.read_text()),
            "sha256": file_sha256(preset_path),
        },
        "maximum_epochs": 20,
        "early_stopping": {"patience": 5, "min_delta": 0.002},
        "shuffle": "numpy default_rng(41), permutation each epoch",
        "checkpoint_selection": {
            "metric": "validation greedy CER",
            "mode": "min",
            "save_on_any_strict_improvement": True,
        },
        "decoder_policy": "validation CER only: greedy vs ordinary beam50; ties greedy; lock before test inference",
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("tensorflow", "numpy", "pillow", "opencv-python-headless")
        },
        "python": __import__("sys").version,
        "git_status": subprocess.check_output(
            ["rtk", "proxy", "git", "status", "--short"], cwd=ROOT, text=True
        ),
        "git_commit": subprocess.check_output(
            ["rtk", "proxy", "git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }
    REPORT.mkdir()
    write(REPORT / "resolved_config.json", config)
    write(REPORT / "preflight_pixel_verification.json", verify_dataset(DATA))
    old_meta = json.loads(OLD.with_suffix(".json").read_text())
    old_model = RecognitionModel(
        name="historical_clean_evaluation",
        image_shape=(64, 512, 1),
        lexical_shape=(
            1,
            old_meta["max_label_length"],
            len(old_meta["characters"]) + 2,
        ),
        seed=41,
    )
    old_model.recognition.load_weights(OLD)
    historical = evaluate(
        old_model.recognition, old_meta["characters"], splits, metadata, OLD_REPORT
    )
    if snapshot() != before:
        raise ValueError("Immutable references changed during historical inference")
    del old_model
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(41)
    model = RecognitionModel(
        name="controlled_flor",
        image_shape=(64, 512, 1),
        lexical_shape=(1, max_length, len(characters) + 2),
        seed=41,
    )
    optimizer = tf.keras.optimizers.AdamW(
        learning_rate=0.001, beta_1=0.5, beta_2=0.99, weight_decay=0.01, clipnorm=5.0
    )
    loss_fn = CTCLoss()
    preset = load_preset(preset_path)
    mapping = {c: i + 1 for i, c in enumerate(characters)}
    rng = np.random.default_rng(41)
    best = patience_best = float("inf")
    counter = 0
    history = []
    started = time.perf_counter()
    for epoch in range(1, 21):
        losses = []
        training = [splits["train"][i] for i in rng.permutation(700)]
        for batch_index, batch in enumerate(batches(training, 32)):
            images = np.asarray(
                [
                    image_tensor(s, preset, 41 + epoch * 100000 + batch_index * 32 + i)
                    for i, s in enumerate(batch)
                ]
            )
            labels = encode(batch, mapping, max_length)
            with tf.GradientTape() as tape:
                logits = model.recognition(images, training=True)
                for s in batch:
                    assert_alignment(s.text, int(np.prod(logits.shape[1:-1])))
                loss = loss_fn(labels, logits)
            optimizer.apply_gradients(
                zip(
                    tape.gradient(loss, model.recognition.trainable_weights),
                    model.recognition.trainable_weights,
                )
            )
            losses.append(float(loss.numpy()))
        validation_losses = []
        for batch in batches(splits["validation"], 32):
            logits = model.recognition(
                np.asarray([image_tensor(s, None, 0) for s in batch]), training=False
            )
            validation_losses.append(
                float(loss_fn(encode(batch, mapping, max_length), logits).numpy())
            )
        validation = metrics(
            [s.text for s in splits["validation"]],
            predict(model.recognition, splits["validation"], characters, 32),
        )
        improved = validation["cer"] < best
        if improved:
            best = validation["cer"]
            best_epoch = epoch
            model.recognition.save_weights(CHECKPOINT)
        if validation["cer"] < patience_best - 0.002:
            patience_best = validation["cer"]
            counter = 0
        else:
            counter += 1
        row = {
            "epoch": epoch,
            "train_loss": float(np.mean(losses)),
            "validation_loss": float(np.mean(validation_losses)),
            "validation": validation,
            "learning_rate": float(optimizer.learning_rate.numpy()),
            "checkpoint_improved": improved,
            "early_stopping_counter": counter,
            "elapsed_seconds": time.perf_counter() - started,
        }
        history.append(row)
        write(REPORT / f"epoch_{epoch:02d}.json", row)
        print(json.dumps(row), flush=True)
        if counter >= 5:
            break
    model.recognition.load_weights(CHECKPOINT)
    write(
        CHECKPOINT.with_suffix(".json"),
        {**old_meta, "model_version": "clean512_v2-controlled", "label": LABEL},
    )
    write(
        REPORT / "training_summary.json",
        {
            "label": LABEL,
            "history": history,
            "best_epoch": best_epoch,
            "best_validation_cer": best,
            "stopping_epoch": epoch,
            "early_stopping_triggered": counter >= 5,
            "checkpoint_sha256": file_sha256(CHECKPOINT),
        },
    )
    new = evaluate(
        model.recognition, characters, splits, metadata, REPORT / "evaluation"
    )
    write(REPORT / "comparison_B_C.json", {"label": LABEL, "B": historical, "C": new})
    after = snapshot()
    write(
        REPORT / "immutability.json",
        {
            "unchanged": before == after,
            "historical_checkpoint_before": before[str(OLD.relative_to(ROOT))],
            "historical_checkpoint_after": file_sha256(OLD),
            "resolved_config_sha256": file_sha256(REPORT / "resolved_config.json"),
            "new_checkpoint_sha256": file_sha256(CHECKPOINT),
            "after": after,
        },
    )
    if before != after:
        raise ValueError("Immutable references changed")
    write(REPORT / "postflight_pixel_verification.json", verify_dataset(DATA))
    print("CONTROLLED_RUN_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
