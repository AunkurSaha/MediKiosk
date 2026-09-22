"""Exactly one from-scratch schedule-context-balanced Flor run."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "upstream/handwritten-text-recognition"))
sys.path.insert(0, str(ROOT))
from sarah.models.components.losses import CTCLoss
from sarah.models.recognition.flor import RecognitionModel
from train_generalization import (
    batches,
    encode,
    image_tensor,
    load_preset,
    metrics,
    predict,
)

from app.dataset import Sample, load_manifest
from app.diagnostics import assert_alignment
from app.render_metadata import file_sha256

DATA = ROOT / "datasets/synthetic/clean512_v2"
POOL = ROOT / "datasets/synthetic/clean512_schedctx_v2"
REPORT = ROOT / "benchmarks/clean512_schedctx_v2_controlled"
CHECKPOINT = ROOT / "models/clean512_schedctx_v2_flor.weights.h5"
C = ROOT / "models/clean512_v2_controlled_flor.weights.h5"
C_SHA = "c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b"


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2)


def clean_snapshot():
    frozen = json.loads(
        (ROOT / "benchmarks/clean512_v2_controlled/immutability.json").read_text()
    )["after"]
    selected = {
        p: h
        for p, h in frozen.items()
        if "datasets/synthetic/clean512_v2/" in p.replace("\\", "/")
    }
    assert len(selected) == 1005 and all(
        file_sha256(ROOT / p) == h for p, h in selected.items()
    )
    return selected


def main():
    if (
        REPORT.exists()
        or CHECKPOINT.exists()
        or CHECKPOINT.with_suffix(".json").exists()
    ):
        raise FileExistsError("Refusing existing D destination")
    if file_sha256(C) != C_SHA:
        raise ValueError("C checkpoint changed")
    before = clean_snapshot()
    verification = json.loads((POOL / "independent_verification.json").read_text())
    assert (
        verification["status"] == "passed"
        and verification["contexts"] == 263
        and verification["variants"] == 1315
    )
    pool = json.loads((POOL / "pool.json").read_text())
    assert pool["status"] == "READY_FOR_CONTROLLED_TRAINING" and pool["verification"][
        "epoch_sizes"
    ] == [700]
    train_original = load_manifest(DATA / "train.csv")
    validation = load_manifest(DATA / "validation.csv")
    test_manifest_hash = file_sha256(DATA / "test.csv")
    non = {
        s.sample_id: s
        for s in train_original
        if not any(p in s.text for p in pool["patterns"])
    }
    assert len(non) == 437
    variants = {
        v["variant_sample_id"]: Sample(
            image=(POOL / v["image"]).resolve(),
            text=v["text"],
            writer_id=v["writer_id"],
            sample_id=v["variant_sample_id"],
            source_type="synthetic",
        )
        for v in pool["variants"]
    }
    all_text = [
        s.text for s in train_original + validation + load_manifest(DATA / "test.csv")
    ]
    characters = sorted(set("".join(all_text)))
    max_length = max(map(len, all_text))
    preset_path = ROOT / "configs/light_augmentation.json"
    config = {
        "experiment_id": "clean512_schedctx_v2 controlled intervention",
        "label": "Intervention D; not a replacement baseline",
        "initialization": "from scratch; no C weights or optimizer state",
        "references": {
            "C_checkpoint": str(C.relative_to(ROOT)),
            "C_sha256": C_SHA,
            "clean_snapshot": before,
            "pool_json_sha256": file_sha256(POOL / "pool.json"),
            "independent_verification_sha256": file_sha256(
                POOL / "independent_verification.json"
            ),
            "test_manifest_sha256": test_manifest_hash,
        },
        "pool": {
            "contexts": 263,
            "variants": 1315,
            "non_schedule": 437,
            "rotation_algorithm": pool["rotation_algorithm"],
            "epoch_pattern_counts": [e["pattern_counts"] for e in pool["epoch_plan"]],
            "first_cycle_exposure": pool["verification"]["first_cycle_exposure"],
            "epoch_sizes": pool["verification"]["epoch_sizes"],
        },
        "input_shape": [64, 512, 1],
        "output_steps": 128,
        "architecture": "Flor unchanged",
        "architecture_sha256": file_sha256(
            ROOT
            / "upstream/handwritten-text-recognition/sarah/models/recognition/flor.py"
        ),
        "vocabulary": {
            "characters": characters,
            "padding": 0,
            "blank": len(characters) + 1,
            "max_length": max_length,
        },
        "batch_size": 32,
        "seed": 41,
        "optimizer": {
            "name": "AdamW",
            "learning_rate": 0.001,
            "beta1": 0.5,
            "beta2": 0.99,
            "weight_decay": 0.01,
            "clipnorm": 5.0,
        },
        "dropout": "unchanged Flor",
        "augmentation": {
            "train_only": True,
            "sha256": file_sha256(preset_path),
            "configuration": json.loads(preset_path.read_text()),
        },
        "maximum_epochs": 20,
        "early_stopping": {"patience": 5, "min_delta": 0.002},
        "checkpoint_selection": "minimum validation greedy CER; strict improvement saves",
        "validation": "original clean512_v2 validation only",
        "test": "not loaded for inference during training; original manifest hash frozen",
        "shuffle": "numpy default_rng(41) permutation of each stored 700-example epoch view",
        "code_hashes": {
            p: file_sha256(ROOT / p)
            for p in [
                "scripts/train_schedule_context_controlled.py",
                "scripts/train_generalization.py",
                "app/augmentation.py",
                "app/ctc.py",
            ]
        },
        "packages": {
            p: importlib.metadata.version(p)
            for p in ["tensorflow", "numpy", "pillow", "opencv-python-headless"]
        },
        "python": sys.version,
        "git_status": subprocess.check_output(
            ["rtk", "proxy", "git", "status", "--short"], cwd=ROOT, text=True
        ),
    }
    REPORT.mkdir()
    write(REPORT / "resolved_config.json", config)
    write(
        REPORT / "preflight.json",
        {
            "clean_unchanged": True,
            "C_sha256": file_sha256(C),
            "pool_verification": verification,
            "pool_plan_verified": True,
            "test_inference": False,
        },
    )
    tf.keras.utils.set_random_seed(41)
    model = RecognitionModel(
        name="clean512_schedctx_v2_controlled",
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
        assignment = pool["epoch_plan"][epoch - 1]["assignments"]
        epoch_samples = list(non.values()) + [
            variants[a["variant_sample_id"]] for a in assignment
        ]
        assert len(epoch_samples) == 700
        epoch_samples = [epoch_samples[i] for i in rng.permutation(700)]
        losses = []
        for bi, batch in enumerate(batches(epoch_samples, 32)):
            images = np.asarray(
                [
                    image_tensor(s, preset, 41 + epoch * 100000 + bi * 32 + i)
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
        vloss = []
        for batch in batches(validation, 32):
            logits = model.recognition(
                np.asarray([image_tensor(s, None, 0) for s in batch]), training=False
            )
            vloss.append(
                float(loss_fn(encode(batch, mapping, max_length), logits).numpy())
            )
        vm = metrics(
            [s.text for s in validation],
            predict(model.recognition, validation, characters, 32),
        )
        improved = vm["cer"] < best
        if improved:
            best = vm["cer"]
            best_epoch = epoch
            model.recognition.save_weights(CHECKPOINT)
        if vm["cer"] < patience_best - 0.002:
            patience_best = vm["cer"]
            counter = 0
        else:
            counter += 1
        row = {
            "epoch": epoch,
            "train_loss": float(np.mean(losses)),
            "validation_loss": float(np.mean(vloss)),
            "validation": vm,
            "learning_rate": float(optimizer.learning_rate.numpy()),
            "checkpoint_improved": improved,
            "patience_counter": counter,
            "elapsed_seconds": time.perf_counter() - started,
            "pattern_counts": pool["epoch_plan"][epoch - 1]["pattern_counts"],
        }
        history.append(row)
        write(REPORT / f"epoch_{epoch:02d}.json", row)
        print(json.dumps(row), flush=True)
        if counter >= 5:
            break
    side = {
        "characters": characters,
        "max_label_length": max_length,
        "image_shape": [64, 512, 1],
        "seed": 41,
        "model_version": "clean512_schedctx_v2-controlled-D",
        "ctc_blank_index": len(characters) + 1,
        "label": "Intervention D",
    }
    write(CHECKPOINT.with_suffix(".json"), side)
    write(
        REPORT / "training_summary.json",
        {
            "history": history,
            "best_epoch": best_epoch,
            "best_validation_greedy_cer": best,
            "stop_epoch": epoch,
            "early_stopping": counter >= 5,
            "checkpoint_sha256": file_sha256(CHECKPOINT),
            "test_inference": False,
        },
    )
    assert (
        clean_snapshot() == before
        and file_sha256(C) == C_SHA
        and file_sha256(DATA / "test.csv") == test_manifest_hash
    )
    print("D_TRAINING_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
