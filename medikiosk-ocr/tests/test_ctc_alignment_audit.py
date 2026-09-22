import itertools
import json
from pathlib import Path

import numpy as np
import pytest
import tensorflow as tf

from app.ctc import greedy_decode
from app.ctc_alignment_audit import (
    collapse,
    forced_alignment,
    log_probabilities,
    projected_token,
)
from app.render_metadata import file_sha256


@pytest.mark.parametrize("text", ["A", "AA", "1-1-1", "1-0-0"])
def test_alignment_and_existing_decoder(text):
    vocabulary = list("A10-")
    mapping = {c: i + 1 for i, c in enumerate(vocabulary)}
    blank = len(vocabulary) + 1
    target = [mapping[c] for c in text]
    path = [blank]
    for label in target:
        path.extend([label, label, blank])
    logits = np.full((len(path), blank + 1), -8.0)
    logits[np.arange(len(path)), path] = 8
    before = logits.copy()
    aligned = forced_alignment(log_probabilities(logits), target, blank)
    np.testing.assert_array_equal(logits, before)
    assert collapse(aligned["label_path"], blank) == target
    assert len(aligned["characters"]) == len(text)
    assert greedy_decode(tf.constant(logits[None], dtype=tf.float32), vocabulary) == [
        text
    ]
    assert [c["adjacent_identical_previous"] for c in aligned["characters"]] == [
        i > 0 and text[i] == text[i - 1] for i in range(len(text))
    ]


def test_forward_probability_matches_exhaustive_paths():
    logp = log_probabilities(
        np.array([[0.0, 1.0, 2.0], [2.0, 0.0, 1.0], [1.0, 2.0, 0.0]])
    )
    paths = [
        p for p in itertools.product(range(3), repeat=3) if collapse(list(p), 2) == [1]
    ]
    values = [sum(logp[t, label] for t, label in enumerate(p)) for p in paths]
    aligned = forced_alignment(logp, [1], 2)
    assert aligned["target_total_log_probability"] == pytest.approx(
        np.logaddexp.reduce(values)
    )
    assert aligned["maximum_path_log_probability"] == pytest.approx(max(values))


def test_impossible_adjacent_repeat_rejected():
    with pytest.raises(ValueError, match="Insufficient"):
        forced_alignment(log_probabilities(np.zeros((2, 3))), [1, 1], 2)


def test_projection_digit_deletion():
    result = projected_token("for 5 days", "for days", 4, 5)
    assert result["prediction"] == ""
    assert result["edits"]["digit_deletion"] == 1


def test_raw_inference_preserves_weights():
    model = tf.keras.Sequential([tf.keras.Input((3,)), tf.keras.layers.Dense(4)])
    before = [w.numpy().copy() for w in model.weights]
    model(tf.ones((2, 3)), training=False)
    for old, weight in zip(before, model.weights, strict=True):
        np.testing.assert_array_equal(old, weight.numpy())


def test_frozen_checkpoint_dataset_and_vocabulary():
    root = Path(__file__).resolve().parents[1]
    checkpoint = root / "models/clean512_v2_controlled_flor.weights.h5"
    if not checkpoint.exists():
        pytest.skip("Frozen local benchmark assets unavailable")
    assert (
        file_sha256(checkpoint)
        == "c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b"
    )
    meta = json.loads(checkpoint.with_suffix(".json").read_text())
    mapping = {c: i + 1 for i, c in enumerate(meta["characters"])}
    assert {c: mapping.get(c) for c in "0123456789- "} == dict(
        zip("0123456789- ", [3, 4, 5, 6, 7, 8, 9, 10, None, None, 2, 1], strict=True)
    )
    assert meta["ctc_blank_index"] == 48
    frozen = json.loads(
        (root / "benchmarks/clean512_v2_controlled/immutability.json").read_text()
    )["after"]
    selected = {
        p: h
        for p, h in frozen.items()
        if "datasets/synthetic/clean512_v2/" in p.replace("\\", "/")
    }
    assert len(selected) == 1005
    assert all(file_sha256(root / p) == h for p, h in selected.items())
