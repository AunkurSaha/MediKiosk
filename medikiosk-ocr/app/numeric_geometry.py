"""Diagnostic-only raster-preserving local numeric interventions."""

from __future__ import annotations

import hashlib
from itertools import pairwise

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def pixel_hash(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def reconstruct(metadata):
    image = Image.new("L", (512, 64), 255)
    font = ImageFont.truetype(metadata["font_path"], metadata["final_font_size"])
    ImageDraw.Draw(image).text(
        tuple(metadata["text_position"]),
        metadata["target_text"],
        font=font,
        fill=0,
        anchor="la",
    )
    return np.asarray(image).copy()


def bbox(mask):
    y, x = np.where(mask)
    if not len(x):
        raise ValueError("Empty glyph ink")
    return [int(x.min()), int(y.min()), int(x.max() + 1), int(y.max() + 1)]


def intervene(original, metadata, start, end, kind):
    if original.shape != (64, 512):
        raise ValueError("Invalid canvas")
    font = ImageFont.truetype(metadata["font_path"], metadata["final_font_size"])
    text = metadata["target_text"]
    left = max(
        0, int(np.floor(metadata["text_position"][0] + font.getlength(text[:start])))
    )
    right = min(
        512, int(np.ceil(metadata["text_position"][0] + font.getlength(text[:end])))
    )
    columns = np.flatnonzero(np.any(original[:, left:right] < 255, axis=0)) + left
    if not len(columns):
        raise ValueError("No reliably located token ink")
    cuts = (
        [0]
        + [i for i, (a, b) in enumerate(pairwise(columns), 1) if b > a + 1]
        + [len(columns)]
    )
    bands = [(int(columns[a]), int(columns[b - 1] + 1)) for a, b in pairwise(cuts)]
    expected = 5 if kind == "schedule" else 1
    if len(bands) != expected:
        raise ValueError(
            f"Ambiguous token segmentation: {len(bands)} ink bands, expected {expected}"
        )
    # Ensure prefix-advance window has not split ink at either boundary.
    if (
        left > 0 and np.any((original[:, left - 1] < 255) & (original[:, left] < 255))
    ) or (
        right < 512
        and np.any((original[:, right - 1] < 255) & (original[:, right] < 255))
    ):
        raise ValueError("Token boundary intersects neighboring ink")
    source = np.zeros_like(original, dtype=bool)
    for a, b in bands:
        source[:, a:b] = original[:, a:b] < 255
    old_bbox = bbox(source)
    remaining = original.copy()
    remaining[source] = 255
    layer = np.full_like(original, 255)
    moves = []
    if kind == "schedule":
        for i, (a, b) in enumerate(bands):
            if b + i > 512:
                raise ValueError("Expanded schedule canvas overflow")
            layer[:, a + i : b + i] = original[:, a:b]
            moves.append(
                {
                    "symbol": text[start + i],
                    "original_x_range": [a, b],
                    "modified_x_range": [a + i, b + i],
                    "dx": i,
                    "dy": 0,
                    "bitmap_unchanged": True,
                }
            )
    elif kind == "duration":
        a, y, b, z = old_bbox
        width = b - a
        new_width = max(width + 1, int(np.floor(width * 1.10 + 0.5)))
        new_left = int(np.floor((a + b - new_width) / 2 + 0.5))
        if new_left < 0 or new_left + new_width > 512:
            raise ValueError("Widened numeral canvas overflow")
        layer[y:z, new_left : new_left + new_width] = cv2.resize(
            original[y:z, a:b], (new_width, z - y), interpolation=cv2.INTER_CUBIC
        )
        moves.append(
            {
                "symbol": text[start:end],
                "original_bbox": old_bbox,
                "modified_bbox": [new_left, y, new_left + new_width, z],
                "requested_scale": 1.10,
                "realized_scale": new_width / width,
                "interpolation": "OpenCV INTER_CUBIC",
                "center_shift": new_left + new_width / 2 - (a + b) / 2,
                "height_unchanged": True,
            }
        )
    else:
        raise ValueError("Unknown intervention")
    new_mask = layer < 255
    new_bbox = bbox(new_mask)
    sx, sy, ex, ey = metadata["safe_area_bounds"]
    if not (
        sx <= new_bbox[0] <= new_bbox[2] <= ex
        and sy <= new_bbox[1] <= new_bbox[3] <= ey
    ):
        raise ValueError("Counterfactual safe-area overflow")
    overlap = int(np.count_nonzero(new_mask & (remaining < 255)))
    if overlap:
        raise ValueError("Counterfactual overlaps neighboring ink")
    # Stronger horizontal whitespace requirement for expanded schedule.
    if kind == "schedule" and np.any(remaining[:, old_bbox[0] : new_bbox[2]] < 255):
        raise ValueError(
            "Expanded schedule intrudes into non-schedule horizontal region"
        )
    changed = np.minimum(remaining, layer)
    region = [
        min(old_bbox[0], new_bbox[0]),
        min(old_bbox[1], new_bbox[1]),
        max(old_bbox[2], new_bbox[2]),
        max(old_bbox[3], new_bbox[3]),
    ]
    diff = changed != original
    allowed = np.zeros_like(diff)
    a, y, b, z = region
    allowed[y:z, a:b] = True
    outside = int(np.count_nonzero(diff & ~allowed))
    assert outside == 0
    preserved = (~source) & (~new_mask)
    assert np.array_equal(changed[preserved], original[preserved])
    if not diff.any():
        raise ValueError("Intervention produces no changed pixels")
    return changed, {
        "target": text,
        "numeric_token": text[start:end],
        "original_token_bbox": old_bbox,
        "modified_token_bbox": new_bbox,
        "intervention_region": region,
        "coordinate_changes": moves,
        "changed_pixels": int(diff.sum()),
        "diff_bbox": bbox(diff),
        "outside_region_changed_pixels": outside,
        "overlap_pixels": overlap,
        "clipping": False,
        "safe_area_overflow": False,
        "original_pixel_sha256": pixel_hash(original),
        "counterfactual_pixel_sha256": pixel_hash(changed),
    }
