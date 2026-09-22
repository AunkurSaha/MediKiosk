"""Build immutable five-identity variants for clean512 TRAIN schedule contexts."""

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
from app.numeric_geometry import reconstruct
from app.render_metadata import file_sha256
from app.schedule_identity import substitute_schedule

SOURCE = ROOT / "datasets/synthetic/clean512_v2"
DEST = ROOT / "datasets/synthetic/clean512_schedctx_v1"
PATTERNS = ["1-1-1", "1-0-1", "1-0-0", "0-1-0", "0-0-1"]


def main():
    if DEST.exists():
        raise FileExistsError(DEST)
    DEST.mkdir()
    (DEST / "variants").mkdir()
    metadata = {
        m["sample_id"]: m
        for line in (SOURCE / "render_metadata.jsonl").read_text().splitlines()
        if (m := json.loads(line))["split"] == "train"
    }
    with (SOURCE / "train.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    contexts = []
    nonschedule = []
    rejected = []
    variant_rows = []
    for row in rows:
        matches = [p for p in PATTERNS if p in row["text"]]
        if not matches:
            nonschedule.append(row)
            continue
        if len(matches) != 1:
            rejected.append(
                {
                    "sample_id": row["sample_id"],
                    "reason": f"ambiguous schedule matches {matches}",
                }
            )
            continue
        pattern = matches[0]
        start = row["text"].index(pattern)
        m = metadata[row["sample_id"]]
        original = np.asarray(Image.open(SOURCE / row["image"]).convert("L"))
        rebuilt = reconstruct(m)
        if not np.array_equal(original, rebuilt):
            rejected.append(
                {"sample_id": row["sample_id"], "reason": "exact reconstruction failed"}
            )
            continue
        made = []
        try:
            for replacement in PATTERNS:
                if replacement == pattern:
                    changed = original.copy()
                    checks = {
                        "changed_pixels": 0,
                        "outside_region_changed_pixels": 0,
                        "overlap_pixels": 0,
                        "clipping": False,
                        "safe_area_overflow": False,
                    }
                else:
                    changed, checks = substitute_schedule(
                        original, m, start, start + 5, replacement
                    )
                target = row["text"][:start] + replacement + row["text"][start + 5 :]
                name = f"{row['sample_id']}__{replacement.replace('-', '')}.png"
                path = DEST / "variants" / name
                Image.fromarray(changed).save(path)
                made.append(
                    {
                        "source_sample_id": row["sample_id"],
                        "variant_sample_id": f"{row['sample_id']}__{replacement.replace('-', '')}",
                        "image": f"variants/{name}",
                        "text": target,
                        "writer_id": row["writer_id"],
                        "source_type": "synthetic",
                        "renderer": m["renderer"],
                        "font_path": m["font_path"],
                        "font_sha256": m["font_sha256"],
                        "font_size": m["final_font_size"],
                        "fitted": m["was_resized_or_fitted"],
                        "schedule_start": start,
                        "original_schedule": pattern,
                        "schedule": replacement,
                        "source_image_sha256": file_sha256(SOURCE / row["image"]),
                        "image_sha256": file_sha256(path),
                        "checks": checks,
                    }
                )
        except (ValueError, AssertionError, OSError) as e:
            for item in made:
                (DEST / item["image"]).unlink()
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
                "original_schedule": pattern,
                "renderer": m["renderer"],
                "font_path": m["font_path"],
                "font_sha256": m["font_sha256"],
                "font_size": m["final_font_size"],
                "fitted": m["was_resized_or_fitted"],
                "schedule_bbox": made[PATTERNS.index(pattern)]["checks"].get(
                    "source_bbox", m["text_bbox"]
                ),
                "image_sha256": file_sha256(SOURCE / row["image"]),
                "metadata": m,
            }
        )
        variant_rows.extend(made)
    plan = []
    for epoch in range(20):
        counts = Counter()
        assignments = []
        for context in contexts:
            pattern = PATTERNS[(context["context_index"] + epoch) % 5]
            counts[pattern] += 1
            assignments.append(
                {"source_sample_id": context["source_sample_id"], "schedule": pattern}
            )
        plan.append(
            {
                "epoch": epoch + 1,
                "pattern_counts": dict(counts),
                "assignments": assignments,
            }
        )
    cycle = {p: sum(e["pattern_counts"][p] for e in plan[:5]) for p in PATTERNS}
    output = {
        "version": "clean512_schedctx_v1",
        "source": "datasets/synthetic/clean512_v2/train.csv",
        "patterns": PATTERNS,
        "schedule_contexts_expected": 263,
        "schedule_contexts_compatible": len(contexts),
        "non_schedule": len(nonschedule),
        "rejected": rejected,
        "contexts": contexts,
        "variants": variant_rows,
        "variant_count": len(variant_rows),
        "rotation": "pattern[(context_index + zero_based_epoch) mod 5]",
        "epoch_plan": plan,
        "first_cycle_exposure": cycle,
        "verification": {
            "all_epoch_sizes": [len(nonschedule) + len(e["assignments"]) for e in plan],
            "max_pattern_count_spread": max(
                max(e["pattern_counts"].values()) - min(e["pattern_counts"].values())
                for e in plan
            ),
            "all_variants_zero_control_violations": all(
                v["checks"]["outside_region_changed_pixels"]
                == v["checks"]["overlap_pixels"]
                == 0
                and not v["checks"]["clipping"]
                and not v["checks"]["safe_area_overflow"]
                for v in variant_rows
            ),
        },
    }
    (DEST / "pool.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    with (DEST / "non_schedule.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(nonschedule)
    print(
        json.dumps(
            {
                k: output[k]
                for k in [
                    "schedule_contexts_compatible",
                    "non_schedule",
                    "variant_count",
                    "rejected",
                    "first_cycle_exposure",
                    "verification",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
