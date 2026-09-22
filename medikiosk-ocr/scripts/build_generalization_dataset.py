"""Create phrase- and renderer-disjoint synthetic prescription splits."""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from generate_prescription_text import generate  # noqa: E402

FONT_NAMES = [
    "arial.ttf", "calibri.ttf", "cambria.ttc", "comic.ttf", "consola.ttf",
    "cour.ttf", "georgia.ttf", "segoepr.ttf", "times.ttf", "trebuc.ttf",
]
SPLIT_WRITERS = {"train": 7, "validation": 1, "test": 2}


def unique_phrases(count: int, seed: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    batch_seed = seed
    while len(result) < count:
        for value in generate(count * 2, batch_seed, ROOT / "configs"):
            if value not in seen:
                seen.add(value)
                result.append(value)
                if len(result) == count:
                    break
        batch_seed += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=41)
    args = parser.parse_args()
    if args.count < 50:
        raise ValueError("Use at least 50 samples for a generalization split")
    output = ROOT / "datasets" / "synthetic" / "generalization"
    output.mkdir(parents=True, exist_ok=True)
    fonts = [Path("C:/Windows/Fonts") / name for name in FONT_NAMES]
    missing = [str(path) for path in fonts if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required renderer fonts missing: {missing}")
    phrases = unique_phrases(args.count, args.seed)
    rng = random.Random(args.seed)
    rng.shuffle(phrases)
    boundaries = {"train": round(args.count * 0.7), "validation": round(args.count * 0.8)}
    split_phrases = {
        "train": phrases[: boundaries["train"]],
        "validation": phrases[boundaries["train"] : boundaries["validation"]],
        "test": phrases[boundaries["validation"] :],
    }
    font_offset = 0
    summary = {}
    for split, split_count in SPLIT_WRITERS.items():
        split_fonts = fonts[font_offset : font_offset + split_count]
        font_offset += split_count
        rows = []
        for index, sample_text in enumerate(split_phrases[split]):
            font_index = index % len(split_fonts)
            font_path = split_fonts[font_index]
            font = ImageFont.truetype(str(font_path), 22 + (index % 3))
            image_name = f"{split}_{index:05d}.png"
            image = Image.new("L", (512, 64), 255)
            ImageDraw.Draw(image).text((7 + index % 4, 14 + index % 3), sample_text, fill=0, font=font)
            image.save(output / image_name)
            rows.append({
                "image": image_name,
                "text": sample_text,
                "writer_id": f"synthetic_renderer_{font_path.stem}",
                "sample_id": f"{split}_{index:05d}",
                "source_type": "synthetic",
            })
        manifest = output / f"{split}.csv"
        with manifest.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        summary[split] = {"samples": len(rows), "writers": sorted({row["writer_id"] for row in rows})}
    print({"count": args.count, "phrase_overlap": 0, "splits": summary})


if __name__ == "__main__":
    main()
