import json
from collections import Counter
from pathlib import Path

from app.render_metadata import file_sha256

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "datasets/synthetic/clean512_schedctx_v1"


def test_partial_pool_is_internally_verified_and_training_must_stop():
    data = json.loads((POOL / "pool.json").read_text())
    assert data["schedule_contexts_expected"] == 263
    assert data["schedule_contexts_compatible"] == 179
    assert len(data["rejected"]) == 84
    assert data["variant_count"] == 179 * 5
    assert data["non_schedule"] == 437
    assert data["verification"]["all_variants_zero_control_violations"]
    assert data["verification"]["max_pattern_count_spread"] <= 1
    assert set(data["verification"]["all_epoch_sizes"]) == {616}
    assert set(data["first_cycle_exposure"].values()) == {179}
    assert all(
        file_sha256(POOL / v["image"]) == v["image_sha256"] for v in data["variants"]
    )


def test_every_compatible_context_has_exact_five_pattern_pool():
    data = json.loads((POOL / "pool.json").read_text())
    counts = Counter(v["source_sample_id"] for v in data["variants"])
    assert set(counts.values()) == {5}
    for context in data["contexts"]:
        patterns = {
            v["schedule"]
            for v in data["variants"]
            if v["source_sample_id"] == context["source_sample_id"]
        }
        assert patterns == set(data["patterns"])
