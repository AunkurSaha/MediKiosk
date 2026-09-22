"""Measure local rendered repeat spans and retain raw paths for worst errors."""

from __future__ import annotations

import json
from itertools import groupby
from pathlib import Path

import numpy as np
from audit_recognition import CACHE, FONT_NAMES, OUTPUT, ROOT, distribution
from PIL import ImageFont


def repeated_spans(text: str, font, downsampling: float) -> list[dict]:
    spans = []
    position = 0
    for char, run in groupby(text):
        length = len(list(run))
        if length > 1:
            start = float(font.getlength(text[:position]))
            end = float(font.getlength(text[: position + length]))
            steps = (end - start) / downsampling
            spans.append(
                {
                    "text": char * length,
                    "start_character": position,
                    "glyph_advance_pixels": end - start,
                    "approx_local_steps": steps,
                    "run_ctc_minimum": 2 * length - 1,
                    "local_ratio": steps / (2 * length - 1),
                    "whitespace": char.isspace(),
                }
            )
        position += length
    return spans


def main() -> None:
    rows = json.loads((OUTPUT / "alignment_samples.json").read_text(encoding="utf-8"))
    metadata = json.loads(
        (ROOT / "models" / "generalization_continued_flor.weights.json").read_text(
            encoding="utf-8"
        )
    )
    characters = metadata["characters"]
    measurements = []
    for row in rows:
        index = int(row["id"].rsplit("_", 1)[1])
        font_name = next(
            name for name in FONT_NAMES if Path(name).stem == row["renderer"]
        )
        font = ImageFont.truetype(
            str(Path("C:/Windows/Fonts") / font_name), 22 + index % 3
        )
        measurements.append(
            {
                "id": row["id"],
                "renderer": row["renderer"],
                "truth": row["truth"],
                "repeat_spans": repeated_spans(
                    row["truth"], font, 512 / row["output_time_steps"]
                ),
            }
        )
    spans = [
        span
        for row in measurements
        for span in row["repeat_spans"]
        if not span["whitespace"]
    ]
    summary = {
        "nonspace_repeat_runs": len(spans),
        "local_ratio": distribution([span["local_ratio"] for span in spans]),
        "local_ratio_below_one": sum(span["local_ratio"] < 1 for span in spans),
        "interpretation": "Glyph-advance/output-grid estimate, not a hard CTC feasibility test; receptive fields and recurrent alignment can allocate neighboring frames.",
    }
    paths = []
    test_errors = sorted(
        [r for r in rows if r["split"] == "test" and r["cer"] > 0],
        key=lambda r: r["cer"],
        reverse=True,
    )[:25]
    for row in test_errors:
        logits = np.load(CACHE / f"w512_{row['id']}.npy").reshape(
            -1, len(characters) + 2
        )
        indices = np.argmax(logits, axis=-1)
        path = []
        frame = 0
        for index, run in groupby(indices):
            frames = len(list(run))
            token = (
                "<blank>"
                if index == len(characters) + 1
                else "<pad>"
                if index == 0
                else characters[index - 1]
            )
            path.append({"token": token, "start": frame, "frames": frames})
            frame += frames
        paths.append(
            {
                "id": row["id"],
                "truth": row["truth"],
                "prediction": row["prediction"],
                "argmax_runs": path,
            }
        )
    (OUTPUT / "local_repeat_alignment.json").write_text(
        json.dumps(
            {"summary": summary, "samples": measurements, "worst_greedy_paths": paths},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
