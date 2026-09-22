import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.numeric_geometry import reconstruct
from app.schedule_identity import substitute_schedule

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks/clean512_v2_schedule_identity_probe"
DATA = ROOT / "datasets/synthetic/clean512_v2"


@pytest.fixture(scope="module")
def data():
    if not (OUT / "selection.json").exists():
        pytest.skip("local artifacts unavailable")
    selected = json.loads((OUT / "selection.json").read_text())["selected"]
    metadata = {
        m["sample_id"]: m
        for line in (DATA / "render_metadata.jsonl").read_text().splitlines()
        if (m := json.loads(line))["split"] == "train"
    }
    return selected, metadata


def test_exact_reconstruction_and_deterministic_controlled_substitution(data):
    selected, metadata = data
    for row in selected:
        m = metadata[row["sample_id"]]
        frozen = np.asarray(Image.open(DATA / m["image"]).convert("L"))
        original = reconstruct(m)
        np.testing.assert_array_equal(original, frozen)
        first, a = substitute_schedule(
            original, m, row["start"], row["end"], row["counterfactual_schedule"]
        )
        second, b = substitute_schedule(
            original, m, row["start"], row["end"], row["counterfactual_schedule"]
        )
        np.testing.assert_array_equal(first, second)
        assert a == b
        assert (
            first.shape == (64, 512)
            and a["outside_region_changed_pixels"] == a["overlap_pixels"] == 0
        )
        assert not a["clipping"] and not a["safe_area_overflow"]
        x1, y1, x2, y2 = a["intervention_region"]
        outside = np.ones((64, 512), bool)
        outside[y1:y2, x1:x2] = False
        np.testing.assert_array_equal(first[outside], original[outside])
        assert (
            row["target"][: row["start"]]
            + row["counterfactual_schedule"]
            + row["target"][row["end"] :]
            == row["counterfactual_target"]
        )


def test_selection_amendment_is_exact_and_deterministic(data):
    selected, _ = data
    assert (
        len(selected) == 12
        and [r["source_schedule"] for r in selected].count("1-1-1") == 6
    )
    assert [r["source_schedule"] for r in selected].count("1-0-0") == 6
    additions = [
        r["sample_id"]
        for r in selected
        if r["selection_origin"] == "expanded_frozen_train_eligibility"
    ]
    assert additions == sorted(additions) and len(additions) == 2
    assert all(r["sample_id"].startswith("train_") for r in selected)


def test_frozen_state_and_inference_weights_unchanged():
    state = json.loads((OUT / "immutability.json").read_text())
    assert state["unchanged"] and state["frozen_before"] == state["frozen_after"]
    assert state["weights_before"] == state["weights_after"]


def test_invalid_substitution_rejected(data):
    row = data[0][0]
    m = data[1][row["sample_id"]]
    with pytest.raises(ValueError, match="five-pattern"):
        substitute_schedule(reconstruct(m), m, row["start"], row["end"], "0-0-0")
