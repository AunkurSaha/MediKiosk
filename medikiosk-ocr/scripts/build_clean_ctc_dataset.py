"""Build six fixed, clean samples for the CTC memorization diagnostic."""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXTS = ["PCM 650 SOS", "PCM 500 SOS", "Tab PCM 650", "Tab PCM 500", "PCM 650 HS", "PCM 500 HS"]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "datasets" / "synthetic" / "clean_ctc"
    output.mkdir(parents=True, exist_ok=True)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 26) if font_path.is_file() else ImageFont.load_default()
    rows = []
    for index, sample_text in enumerate(TEXTS):
        image_name = f"clean_{index:02d}.png"
        image = Image.new("L", (256, 64), 255)
        ImageDraw.Draw(image).text((8, 15), sample_text, fill=0, font=font)
        image.save(output / image_name)
        rows.append({
            "image": image_name,
            "text": sample_text,
            "writer_id": "fixed_arial",
            "sample_id": f"clean_{index:02d}",
            "source_type": "synthetic",
        })
    with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"created={len(rows)} manifest={output / 'manifest.csv'} augmentation=disabled")


if __name__ == "__main__":
    main()
