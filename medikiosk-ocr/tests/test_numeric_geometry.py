import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.numeric_geometry import intervene, reconstruct
from app.render_metadata import file_sha256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks/clean512_v2_numeric_geometry"
DATA = ROOT / "datasets/synthetic/clean512_v2"


@pytest.fixture(scope="module")
def probe():
    if not (OUT / "selection.json").exists():
        pytest.skip("Frozen local geometry experiment artifacts unavailable")
    selection = json.loads((OUT / "selection.json").read_text())
    metadata = {
        m["sample_id"]: m
        for line in (DATA / "render_metadata.jsonl").read_text().splitlines()
        if (m := json.loads(line))["split"] == "train"
    }
    return selection, metadata


def test_original_reconstruction_and_deterministic_interventions(probe):
    selection, metadata = probe
    for row in selection["selected"]:
        m = metadata[row["sample_id"]]
        original = np.asarray(Image.open(DATA / m["image"]))
        np.testing.assert_array_equal(reconstruct(m), original)
        a, checks = intervene(
            original, m, row["glyph_start"], row["glyph_end"], row["kind"]
        )
        b, again = intervene(
            original, m, row["glyph_start"], row["glyph_end"], row["kind"]
        )
        np.testing.assert_array_equal(a, b)
        assert checks == again
        assert checks["target"] == row["target"]
        assert a.shape == original.shape == (64, 512)
        assert checks["overlap_pixels"] == checks["outside_region_changed_pixels"] == 0
        assert not checks["clipping"] and not checks["safe_area_overflow"]
        x, y, z, w = checks["intervention_region"]
        outside = np.ones_like(original, dtype=bool)
        outside[y:w, x:z] = False
        np.testing.assert_array_equal(a[outside], original[outside])
        if row["kind"] == "schedule":
            for change in checks["coordinate_changes"]:
                left, right = change["original_x_range"]
                new_left, new_right = change["modified_x_range"]
                np.testing.assert_array_equal(
                    original[:, left:right], a[:, new_left:new_right]
                )
            assert [c["dx"] for c in checks["coordinate_changes"]] == [0, 1, 2, 3, 4]
        else:
            move = checks["coordinate_changes"][0]
            assert move["height_unchanged"]
            assert abs(move["center_shift"]) <= 0.5
            assert move["realized_scale"] > 1


def test_deterministic_selection(probe):
    from scripts.numeric_geometry_probe import PATTERNS, select

    selection, metadata = probe
    tokens = json.loads(
        (
            ROOT / "benchmarks/clean512_v2_ctc_schedule_audit/token_details.json"
        ).read_text()
    )
    first, rejected = select(tokens, metadata)
    second, rejected_again = select(list(reversed(tokens)), metadata)
    assert first == second == selection["selected"]
    assert rejected == rejected_again == selection["rejected"]
    assert len({r["sample_id"] for r in first}) == 20
    assert all(r["sample_id"].startswith("train_") for r in first)
    assert {
        pattern: sum(r["pattern"] == pattern for r in first) for pattern in PATTERNS
    } == PATTERNS


def test_actual_frozen_model_and_corpus_unchanged(probe):
    state = json.loads((OUT / "immutability.json").read_text())
    assert state["before"] == state["after"]
    assert state["in_memory_weights_before"] == state["in_memory_weights_after"]
    assert all(file_sha256(ROOT / path) == sha for path, sha in state["after"].items())


def test_invalid_canvas_rejected(probe):
    row = probe[0]["selected"][0]
    with pytest.raises(ValueError, match="canvas"):
        intervene(
            np.full((63, 512), 255, dtype=np.uint8),
            probe[1][row["sample_id"]],
            row["glyph_start"],
            row["glyph_end"],
            row["kind"],
        )


def test_insufficient_safe_region_rejected(probe):
    row = probe[0]["selected"][0]
    m = dict(probe[1][row["sample_id"]])
    m["safe_area_bounds"] = [0, 0, 2, 64]
    with pytest.raises(ValueError, match="safe-area"):
        intervene(reconstruct(m), m, row["glyph_start"], row["glyph_end"], row["kind"])
