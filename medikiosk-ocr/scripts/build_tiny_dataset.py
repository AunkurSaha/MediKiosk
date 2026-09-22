"""Build a safe 24-line synthetic manifest using a local Windows font."""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from generate_prescription_text import generate


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "datasets" / "synthetic" / "tiny"
    output.mkdir(parents=True, exist_ok=True)
    lines = generate(24, 29, root / "configs")
    font_path = Path("C:/Windows/Fonts/segoepr.ttf")
    font = ImageFont.truetype(str(font_path), 22) if font_path.is_file() else ImageFont.load_default()
    rows = []
    for index, text in enumerate(lines):
        image_name = f"rx_{index:06d}.png"
        image = Image.new("L", (512, 64), 255)
        ImageDraw.Draw(image).text((8, 16), text, fill=0, font=font)
        image.save(output / image_name)
        rows.append(
            {
                "image": image_name,
                "text": text,
                "writer_id": f"synthetic_font_{index % 4}",
                "sample_id": f"sample_{index:06d}",
                "source_type": "synthetic",
            }
        )
    with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"created={len(rows)} manifest={output / 'manifest.csv'}")


if __name__ == "__main__":
    main()
