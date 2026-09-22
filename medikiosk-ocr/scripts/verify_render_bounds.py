"""Reconstruct original renderings to verify missing pixels, not just bounds."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from build_generalization_dataset import FONT_NAMES
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks" / "ctc_audit"


def main() -> None:
    rows = json.loads((OUTPUT / "alignment_samples.json").read_text(encoding="utf-8"))
    verification = []
    for row in rows:
        index = int(row["id"].rsplit("_", 1)[1])
        font_name = next(
            name for name in FONT_NAMES if Path(name).stem == row["renderer"]
        )
        font = ImageFont.truetype(
            str(Path("C:/Windows/Fonts") / font_name), 22 + index % 3
        )
        right = 7 + index % 4 + font.getbbox(row["truth"])[2]
        reconstructed = Image.new("L", (max(512, right + 10), 64), 255)
        ImageDraw.Draw(reconstructed).text(
            (7 + index % 4, 14 + index % 3), row["truth"], fill=0, font=font
        )
        pixels = np.asarray(reconstructed)
        original = np.asarray(
            Image.open(
                ROOT / "datasets" / "synthetic" / "generalization" / f"{row['id']}.png"
            )
        )
        matches = bool(np.array_equal(pixels[:, :512], original))
        if not matches:
            raise ValueError(
                f"Rendering reconstruction differs from saved image: {row['id']}"
            )
        verification.append(
            {
                "id": row["id"],
                "renderer": row["renderer"],
                "split": row["split"],
                "saved_pixels_match": matches,
                "missing_ink_pixels": int(np.count_nonzero(pixels[:, 512:] < 220)),
            }
        )
    report = {
        "all_saved_images_reproduced_exactly": True,
        "samples_with_missing_ink": sum(
            row["missing_ink_pixels"] > 0 for row in verification
        ),
        "samples": verification,
    }
    (OUTPUT / "render_bounds_verification.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print({key: value for key, value in report.items() if key != "samples"})


if __name__ == "__main__":
    main()
