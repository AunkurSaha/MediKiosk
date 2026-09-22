"""Build complete layout-derived five-identity TRAIN schedule pool; never train."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.layout_schedule import PATTERNS, construct_variant
from app.numeric_geometry import reconstruct
from app.render_metadata import file_sha256

SRC = ROOT / "datasets/synthetic/clean512_v2"
DST = ROOT / "datasets/synthetic/clean512_schedctx_v2"


def main():
    if DST.exists():
        raise FileExistsError(DST)
    DST.mkdir()
    (DST / "variants").mkdir()
    meta = {
        m["sample_id"]: m
        for line in (SRC / "render_metadata.jsonl").read_text().splitlines()
        if (m := json.loads(line))["split"] == "train"
    }
    with (SRC / "train.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    contexts = []
    variants = []
    rejected = []
    non = []
    for row in rows:
        matches = [p for p in PATTERNS if p in row["text"]]
        if not matches:
            non.append(row)
            continue
        if len(matches) != 1:
            rejected.append(
                {
                    "sample_id": row["sample_id"],
                    "reason": f"ambiguous target schedule {matches}",
                }
            )
            continue
        source = matches[0]
        start = row["text"].index(source)
        m = meta[row["sample_id"]]
        frozen = np.asarray(Image.open(SRC / row["image"]).convert("L"))
        rebuilt = reconstruct(m)
        if not np.array_equal(frozen, rebuilt):
            rejected.append(
                {
                    "sample_id": row["sample_id"],
                    "reason": "full original reconstruction mismatch",
                }
            )
            continue
        made = []
        try:
            for pattern in PATTERNS:
                image, record = construct_variant(frozen, m, start, pattern)
                name = f"{row['sample_id']}__{pattern.replace('-', '')}.png"
                path = DST / "variants" / name
                Image.fromarray(image).save(path)
                made.append(
                    {
                        "source_sample_id": row["sample_id"],
                        "variant_sample_id": f"{row['sample_id']}__{pattern.replace('-', '')}",
                        "image": f"variants/{name}",
                        "text": record["target"],
                        "writer_id": row["writer_id"],
                        "source_type": "synthetic",
                        "schedule": pattern,
                        "original_schedule": source,
                        "schedule_start": start,
                        "renderer": m["renderer"],
                        "font_path": m["font_path"],
                        "font_sha256": m["font_sha256"],
                        "font_size": m["final_font_size"],
                        "fitted": m["was_resized_or_fitted"],
                        "source_image": row["image"],
                        "source_image_sha256": file_sha256(SRC / row["image"]),
                        "variant_file_sha256": file_sha256(path),
                        "record": record,
                    }
                )
        except (ValueError, AssertionError, OSError) as e:
            for v in made:
                (DST / v["image"]).unlink()
            rejected.append({"sample_id": row["sample_id"], "reason": str(e)})
            continue
        contexts.append(
            {
                "context_index": len(contexts),
                "source_sample_id": row["sample_id"],
                "source_text": row["text"],
                "complete_non_schedule_text": row["text"][:start]
                + "<SCHEDULE>"
                + row["text"][start + 5 :],
                "schedule_start": start,
                "original_schedule": source,
                "renderer": m["renderer"],
                "font_path": m["font_path"],
                "font_sha256": m["font_sha256"],
                "font_size": m["final_font_size"],
                "fitted": m["was_resized_or_fitted"],
                "source_image_sha256": file_sha256(SRC / row["image"]),
                "metadata": m,
            }
        )
        variants.extend(made)
    plan = []
    for epoch in range(20):
        counts = Counter()
        assign = []
        for c in contexts:
            pattern = PATTERNS[(c["context_index"] + epoch) % 5]
            counts[pattern] += 1
            assign.append(
                {
                    "source_sample_id": c["source_sample_id"],
                    "schedule": pattern,
                    "variant_sample_id": f"{c['source_sample_id']}__{pattern.replace('-', '')}",
                }
            )
        plan.append(
            {"epoch": epoch + 1, "pattern_counts": dict(counts), "assignments": assign}
        )
    result = {
        "version": "clean512_schedctx_v2",
        "status": "READY_FOR_CONTROLLED_TRAINING"
        if len(contexts) == 263
        else "STILL_BLOCKED",
        "construction": "Pillow layout-derived prefix/symbol advances; original symbol slots; no component segmentation",
        "source": "datasets/synthetic/clean512_v2",
        "patterns": list(PATTERNS),
        "schedule_contexts_expected": 263,
        "schedule_contexts_compatible": len(contexts),
        "non_schedule_count": len(non),
        "rejected": rejected,
        "contexts": contexts,
        "variants": variants,
        "variant_count": len(variants),
        "rotation_algorithm": "patterns[(context_index + zero_based_epoch) mod 5]",
        "epoch_plan": plan,
        "verification": {
            "original_identity_exact": sum(
                v["record"]["original_identity_pixel_exact"] is True for v in variants
            ),
            "outside_diff_total": sum(
                v["record"]["outside_region_changed_pixels"] for v in variants
            ),
            "overlap_total": sum(v["record"]["overlap_pixels"] for v in variants),
            "clipping_count": sum(v["record"]["clipping"] for v in variants),
            "safe_overflow_count": sum(
                v["record"]["safe_area_overflow"] for v in variants
            ),
            "epoch_sizes": sorted({len(non) + len(e["assignments"]) for e in plan}),
            "maximum_epoch_pattern_spread": max(
                max(e["pattern_counts"].values()) - min(e["pattern_counts"].values())
                for e in plan
            )
            if contexts
            else None,
            "first_cycle_exposure": {
                p: sum(e["pattern_counts"].get(p, 0) for e in plan[:5])
                for p in PATTERNS
            },
        },
    }
    (DST / "pool.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (DST / "non_schedule.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(non)
    (DST / "PROTOCOL.md").write_text(
        "# clean512_schedctx_v2 construction\n\nEach source is reconstructed exactly. Schedule origin equals line x plus Pillow getlength(prefix). Five symbol anchors equal line x plus getlength(prefix + original schedule prefix). Replacement symbols use the same font, size, anchor `la`, baseline and original symbol anchors. Original token ink is derived by isolated layout rendering and must match frozen pixels exactly; only that mask is cleared. Suffix/prefix remain stored source pixels. No spacing, scaling, OCR prediction or connected-component inference is used.\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "status",
                    "schedule_contexts_compatible",
                    "non_schedule_count",
                    "variant_count",
                    "rejected",
                    "verification",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
