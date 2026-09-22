"""Regression tests for decoder locking and immutable controlled outputs."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_clean512_controlled as controlled
from report_clean512_controlled import error_patterns

from app.dataset import Sample


def test_exclusive_artifact_write(tmp_path):
    path = tmp_path / "artifact.json"
    controlled.write(path, {"frozen": True})
    with pytest.raises(FileExistsError):
        controlled.write(path, {"frozen": False})
    assert json.loads(path.read_text()) == {"frozen": True}


@pytest.mark.parametrize("tie", [False, True])
def test_decoder_locked_from_validation_before_test(tmp_path, monkeypatch, tie):
    truth = "PCM 5 mg BD"
    splits = {
        s: [Sample(tmp_path / "unused.png", truth, "arial", s, "synthetic")]
        for s in ("validation", "train", "test")
    }
    metadata = {
        s: {
            "renderer": "arial",
            "original_requested_font_size": 22,
            "final_font_size": 22,
            "was_resized_or_fitted": False,
        }
        for s in splits
    }
    monkeypatch.setattr(
        controlled, "image_tensor", lambda *args: np.zeros((64, 512, 1))
    )
    monkeypatch.setattr(
        controlled, "greedy_decode", lambda *args: [truth if tie else "wrong"]
    )
    monkeypatch.setattr(controlled, "beam_decode", lambda *args: [truth])
    calls = []
    output = tmp_path / "evaluation"

    def model(*args, **kwargs):
        if calls:
            lock = json.loads((output / "decoder_lock.json").read_text())
            assert lock["preferred"] == ("greedy" if tie else "beam50")
            assert lock["test_inference_has_started"] is False
        calls.append(True)

    result = controlled.evaluate(model, [], splits, metadata, output)
    assert len(calls) == 3
    assert result["beam50"]["test"]["cer"] == 0


def test_whitespace_and_optional_metrics():
    rows = [
        {
            "truth": "PCM  5 mg BD",
            "prediction": "PCM 5 mg BD",
            "fitted": False,
            "renderer": "arial",
            "final_font_size": 22,
            "buckets": ["spacing"],
        }
    ]
    result = controlled.describe(rows)
    assert result["cer"] > 0
    assert result["whitespace_normalized"]["cer"] == 0
    assert result["fields"]["durations"]["absent_count"] == 1
    assert result["fields"]["durations"]["present_accuracy"] is None


def test_descriptive_errors_do_not_modify_prediction():
    row = {
        "truth": "Amoxicillin 5 mg 1-1-1 before food",
        "prediction": "Amoxilin 6 mg 1 before fod",
        "buckets": ["numeric_schedule"],
    }
    original = row.copy()
    result = error_patterns(row)
    assert "medicine internal deletion" in result
    assert "adjacent repeated glyph deletion" in result
    assert "numeric substitution" in result
    assert "hyphen loss" in result
    assert row == original
