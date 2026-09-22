"""Raster-local schedule identity substitution for frozen diagnostics."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.numeric_geometry import bbox


def substitute_schedule(original, metadata, start, end, replacement):
    source = metadata["target_text"][start:end]
    allowed = {"1-1-1", "1-0-1", "1-0-0", "0-1-0", "0-0-1"}
    if source not in allowed or replacement not in allowed or source == replacement:
        raise ValueError(
            "Only distinct predeclared five-pattern substitutions are allowed"
        )
    font = ImageFont.truetype(metadata["font_path"], metadata["final_font_size"])
    x0, baseline = metadata["text_position"]
    left = int(np.floor(x0 + font.getlength(metadata["target_text"][:start])))
    right = int(np.ceil(x0 + font.getlength(metadata["target_text"][:end])))
    columns = np.flatnonzero(np.any(original[:, left:right] < 255, axis=0)) + left
    cuts = (
        [0]
        + [i for i, (a, b) in enumerate(pairwise(columns), 1) if b > a + 1]
        + [len(columns)]
    )
    bands = [(int(columns[a]), int(columns[b - 1] + 1)) for a, b in pairwise(cuts)]
    if len(bands) != 5:
        raise ValueError(f"Ambiguous schedule segmentation: {len(bands)} bands")
    source_mask = np.zeros_like(original, dtype=bool)
    for a, b in bands:
        source_mask[:, a:b] = original[:, a:b] < 255
    remaining = original.copy()
    remaining[source_mask] = 255
    layer = np.full_like(original, 255)
    placements = []
    for i, ((a, b), char) in enumerate(zip(bands, replacement, strict=True)):
        if char == source[i]:
            layer[:, a:b] = original[:, a:b]
            new_box = bbox(original[:, a:b] < 255)
            new_box = [new_box[0] + a, new_box[1], new_box[2] + a, new_box[3]]
            method = "copied source glyph bitmap"
        else:
            isolated = Image.new("L", (128, 64), 255)
            ImageDraw.Draw(isolated).text(
                (32, baseline), char, font=font, fill=0, anchor="la"
            )
            raster = np.asarray(isolated)
            gx1, gy1, gx2, gy2 = bbox(raster < 255)
            glyph = raster[gy1:gy2, gx1:gx2]
            center = (a + b) / 2
            new_left = int(np.floor(center - glyph.shape[1] / 2 + 0.5))
            new_box = [new_left, gy1, new_left + glyph.shape[1], gy2]
            if new_left < 0 or new_box[2] > 512:
                raise ValueError("Replacement glyph canvas overflow")
            layer[gy1:gy2, new_left : new_box[2]] = glyph
            method = "same-font isolated raster centered on original ink-band center"
        placements.append(
            {
                "index": i,
                "source": source[i],
                "replacement": char,
                "source_bbox": [
                    a,
                    bbox(original[:, a:b] < 255)[1],
                    b,
                    bbox(original[:, a:b] < 255)[3],
                ],
                "replacement_bbox": new_box,
                "source_center_x": (a + b) / 2,
                "replacement_center_x": (new_box[0] + new_box[2]) / 2,
                "method": method,
            }
        )
    replacement_mask = layer < 255
    overlap = int(np.count_nonzero(replacement_mask & (remaining < 255)))
    if overlap:
        raise ValueError("Replacement overlaps non-schedule ink")
    output = np.minimum(remaining, layer)
    old_box, new_box = bbox(source_mask), bbox(replacement_mask)
    region = [
        min(old_box[0], new_box[0]),
        min(old_box[1], new_box[1]),
        max(old_box[2], new_box[2]),
        max(old_box[3], new_box[3]),
    ]
    sx, sy, ex, ey = metadata["safe_area_bounds"]
    if not (
        sx <= region[0] and region[2] <= ex and sy <= region[1] and region[3] <= ey
    ):
        raise ValueError("Replacement safe-area overflow")
    diff = output != original
    allowed = np.zeros_like(diff)
    allowed[region[1] : region[3], region[0] : region[2]] = True
    outside = int(np.count_nonzero(diff & ~allowed))
    if outside:
        raise AssertionError("Unintended outside-region change")
    return output, {
        "source_schedule": source,
        "counterfactual_schedule": replacement,
        "source_bbox": old_box,
        "replacement_bbox": new_box,
        "intervention_region": region,
        "placements": placements,
        "changed_pixels": int(diff.sum()),
        "diff_bbox": bbox(diff),
        "outside_region_changed_pixels": outside,
        "overlap_pixels": overlap,
        "clipping": False,
        "safe_area_overflow": False,
    }
