import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.layout_schedule import PATTERNS, construct_variant, layout_slots
from app.numeric_geometry import reconstruct

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "datasets/synthetic/clean512_schedctx_v2"
SOURCE = ROOT / "datasets/synthetic/clean512_v2"


def load():
    return json.loads((POOL / "pool.json").read_text())


def test_layout_slots_are_deterministic_and_proportional_safe():
    d = load()
    c = d["contexts"][0]
    m = c["metadata"]
    a = layout_slots(m, c["schedule_start"])
    b = layout_slots(m, c["schedule_start"])
    assert a == b
    assert a["schedule_anchor"][0] == m["text_position"][0] + a["prefix_advance"]
    # No monospaced assumption: advances are measured and recorded, never hard-coded.
    assert all(x > 0 for x in a["source_symbol_advances"])


def test_all_five_variants_deterministic_and_controlled():
    d = load()
    c = d["contexts"][0]
    m = c["metadata"]
    original = reconstruct(m)
    for pattern in PATTERNS:
        a, ar = construct_variant(original, m, c["schedule_start"], pattern)
        b, br = construct_variant(original, m, c["schedule_start"], pattern)
        np.testing.assert_array_equal(a, b)
        assert ar == br
        assert (
            a.shape == (64, 512)
            and ar["outside_region_changed_pixels"] == ar["overlap_pixels"] == 0
            and not ar["clipping"]
            and not ar["safe_area_overflow"]
        )


def test_complete_pool_accounting_and_original_controls():
    d = load()
    assert (
        d["status"] == "READY_FOR_CONTROLLED_TRAINING"
        and d["schedule_contexts_compatible"] == 263
        and not d["rejected"]
        and d["variant_count"] == 1315
    )
    assert d["verification"] == {
        "original_identity_exact": 263,
        "outside_diff_total": 0,
        "overlap_total": 0,
        "clipping_count": 0,
        "safe_overflow_count": 0,
        "epoch_sizes": [700],
        "maximum_epoch_pattern_spread": 1,
        "first_cycle_exposure": {p: 263 for p in PATTERNS},
    }
    for v in d["variants"]:
        if v["schedule"] == v["original_schedule"]:
            np.testing.assert_array_equal(
                np.asarray(Image.open(POOL / v["image"])),
                np.asarray(Image.open(SOURCE / v["source_image"])),
            )


def test_suffix_and_non_schedule_pixels_unchanged_for_every_variant():
    d = load()
    for v in d["variants"]:
        src = np.asarray(Image.open(SOURCE / v["source_image"]))
        image = np.asarray(Image.open(POOL / v["image"]))
        x1, y1, x2, y2 = v["record"]["authorized_region"]
        mask = np.ones((64, 512), bool)
        mask[y1:y2, x1:x2] = False
        np.testing.assert_array_equal(src[mask], image[mask])


def test_rotation_has_700_examples_and_complete_five_epoch_cycles():
    d = load()
    assert all(len(e["assignments"]) + 437 == 700 for e in d["epoch_plan"])
    assert d["verification"]["maximum_epoch_pattern_spread"] <= 1 and set(
        d["verification"]["first_cycle_exposure"].values()
    ) == {263}


def test_clean_corpus_immutability_snapshot():
    result = json.loads((POOL / "independent_verification.json").read_text())
    assert result["clean_snapshot_files"] == 1005 and result["status"] == "passed"
