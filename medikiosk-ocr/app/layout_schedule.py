"""Layout-derived schedule raster substitution without component segmentation."""

from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PATTERNS = ("1-1-1", "1-0-1", "1-0-0", "0-1-0", "0-0-1")


def _render(text, font, position):
    image = Image.new("L", (512, 64), 255)
    ImageDraw.Draw(image).text(position, text, font=font, fill=0, anchor="la")
    return np.asarray(image).copy()


def _box(mask):
    y, x = np.where(mask)
    if not len(x):
        raise ValueError("Empty rendered mask")
    return [int(x.min()), int(y.min()), int(x.max() + 1), int(y.max() + 1)]


def pixel_hash(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def layout_slots(metadata, start):
    text = metadata["target_text"]
    source = text[start : start + 5]
    if source not in PATTERNS:
        raise ValueError("Schedule token not at declared indices")
    font = ImageFont.truetype(metadata["font_path"], metadata["final_font_size"])
    x, y = metadata["text_position"]
    prefix = text[:start]
    prefix_advance = float(font.getlength(prefix))
    token_advance = float(font.getlength(source))
    anchors = [x + float(font.getlength(prefix + source[:i])) for i in range(5)]
    advances = [float(font.getlength(c)) for c in source]
    return {
        "full_line_origin": [x, y],
        "prefix": prefix,
        "prefix_advance": prefix_advance,
        "schedule_anchor": [x + prefix_advance, y],
        "token_advance": token_advance,
        "suffix_start": [x + float(font.getlength(prefix + source)), y],
        "symbol_anchors_x": anchors,
        "source_symbol_advances": advances,
    }


def construct_variant(original, metadata, start, replacement):
    text = metadata["target_text"]
    source = text[start : start + 5]
    if source not in PATTERNS or replacement not in PATTERNS:
        raise ValueError("Unsupported schedule")
    font = ImageFont.truetype(metadata["font_path"], metadata["final_font_size"])
    slots = layout_slots(metadata, start)
    baseline = metadata["text_position"][1]
    original_token = np.full_like(original, 255)
    replacement_layer = np.full_like(original, 255)
    symbols = []
    for i, (old, new) in enumerate(zip(source, replacement, strict=True)):
        anchor = slots["symbol_anchors_x"][i]
        old_layer = _render(old, font, (anchor, baseline))
        new_layer = _render(new, font, (anchor, baseline))
        original_token = np.minimum(original_token, old_layer)
        replacement_layer = np.minimum(replacement_layer, new_layer)
        symbols.append(
            {
                "index": i,
                "source": old,
                "replacement": new,
                "anchor_x": anchor,
                "source_advance": float(font.getlength(old)),
                "replacement_advance": float(font.getlength(new)),
                "source_bbox": _box(old_layer < 255),
                "replacement_bbox": _box(new_layer < 255),
            }
        )
    token_mask = original_token < 255
    new_mask = replacement_layer < 255
    token_box = _box(token_mask)
    new_box = _box(new_mask)
    region = [
        min(token_box[0], new_box[0]),
        min(token_box[1], new_box[1]),
        max(token_box[2], new_box[2]),
        max(token_box[3], new_box[3]),
    ]
    if not np.array_equal(original[token_mask], original_token[token_mask]):
        raise ValueError(
            "Layout-derived original token raster differs from frozen source"
        )
    remaining = original.copy()
    remaining[token_mask] = 255
    overlap = int(np.count_nonzero(new_mask & (remaining < 255)))
    if overlap:
        raise ValueError("Replacement overlaps non-schedule ink")
    output = np.minimum(remaining, replacement_layer)
    diff = output != original
    allowed = np.zeros_like(diff)
    allowed[region[1] : region[3], region[0] : region[2]] = True
    outside = int(np.count_nonzero(diff & ~allowed))
    sx, sy, ex, ey = metadata["safe_area_bounds"]
    if not (sx <= region[0] <= region[2] <= ex and sy <= region[1] <= region[3] <= ey):
        raise ValueError("Schedule safe-area overflow")
    if outside:
        raise AssertionError("Pixels changed outside authorized schedule region")
    target = text[:start] + replacement + text[start + 5 :]
    return output, {
        "source_schedule": source,
        "replacement_schedule": replacement,
        "target": target,
        "layout": slots,
        "symbols": symbols,
        "source_token_bbox": token_box,
        "replacement_token_bbox": new_box,
        "authorized_region": region,
        "changed_pixels": int(diff.sum()),
        "outside_region_changed_pixels": outside,
        "overlap_pixels": overlap,
        "clipping": False,
        "safe_area_overflow": False,
        "source_pixel_sha256": pixel_hash(original),
        "variant_pixel_sha256": pixel_hash(output),
        "original_identity_pixel_exact": bool(np.array_equal(output, original))
        if replacement == source
        else None,
    }
