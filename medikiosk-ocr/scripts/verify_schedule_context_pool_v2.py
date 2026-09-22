"""Independent stored-artifact validator; does not call pool construction code."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.render_metadata import file_sha256

POOL = ROOT / "datasets/synthetic/clean512_schedctx_v2"
SOURCE = ROOT / "datasets/synthetic/clean512_v2"


def main():
    data = json.loads((POOL / "pool.json").read_text())
    assert data["status"] == "READY_FOR_CONTROLLED_TRAINING"
    assert (
        data["schedule_contexts_compatible"] == 263
        and not data["rejected"]
        and data["variant_count"] == 1315
        and data["non_schedule_count"] == 437
    )
    by = defaultdict(list)
    original_exact = outside = overlap = 0
    for v in data["variants"]:
        by[v["source_sample_id"]].append(v)
        path = POOL / v["image"]
        assert (
            file_sha256(path) == v["variant_file_sha256"]
            and file_sha256(SOURCE / v["source_image"]) == v["source_image_sha256"]
            and file_sha256(Path(v["font_path"])) == v["font_sha256"]
        )
        src = np.asarray(Image.open(SOURCE / v["source_image"]).convert("L"))
        image = np.asarray(Image.open(path).convert("L"))
        assert src.shape == image.shape == (64, 512)
        assert v["text"] == next(
            c["source_text"][: c["schedule_start"]]
            + v["schedule"]
            + c["source_text"][c["schedule_start"] + 5 :]
            for c in data["contexts"]
            if c["source_sample_id"] == v["source_sample_id"]
        )
        region = v["record"]["authorized_region"]
        mask = np.ones((64, 512), bool)
        mask[region[1] : region[3], region[0] : region[2]] = False
        outside += int(np.count_nonzero(src[mask] != image[mask]))
        assert np.array_equal(src[mask], image[mask])
        assert 0 <= region[0] <= region[2] <= 512 and 0 <= region[1] <= region[3] <= 64
        overlap += v["record"]["overlap_pixels"]
        if v["schedule"] == v["original_schedule"]:
            original_exact += 1
            assert np.array_equal(src, image)
    assert len(by) == 263 and all(
        len(v) == 5 and {x["schedule"] for x in v} == set(data["patterns"])
        for v in by.values()
    )
    for epoch in data["epoch_plan"]:
        assert len(epoch["assignments"]) == 263
        counts = Counter(x["schedule"] for x in epoch["assignments"])
        assert max(counts.values()) - min(counts.values()) <= 1
    for start in range(0, 20, 5):
        seen = defaultdict(set)
        for epoch in data["epoch_plan"][start : start + 5]:
            for a in epoch["assignments"]:
                seen[a["source_sample_id"]].add(a["schedule"])
        assert len(seen) == 263 and all(
            v == set(data["patterns"]) for v in seen.values()
        )
    frozen = json.loads(
        (ROOT / "benchmarks/clean512_v2_controlled/immutability.json").read_text()
    )["after"]
    clean = {
        p: h
        for p, h in frozen.items()
        if "datasets/synthetic/clean512_v2/" in p.replace("\\", "/")
    }
    assert len(clean) == 1005 and all(
        file_sha256(ROOT / p) == h for p, h in clean.items()
    )
    result = {
        "status": "passed",
        "contexts": len(by),
        "variants": sum(map(len, by.values())),
        "original_identity_exact": original_exact,
        "outside_region_diff_total": outside,
        "stored_overlap_total": overlap,
        "rotation_epochs": 20,
        "clean_snapshot_files": len(clean),
    }
    (POOL / "independent_verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
