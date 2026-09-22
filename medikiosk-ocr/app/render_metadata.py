"""Read-only independent pixel/provenance verification of a versioned corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from app.rendering import RenderConfig, load_font, validate_render_bounds, verify_pixels


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_dataset(dataset_dir: Path) -> dict:
    dataset_dir = dataset_dir.resolve()
    records = [
        json.loads(line)
        for line in (dataset_dir / "render_metadata.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError("Render metadata contains no samples")
    ids: set[str] = set()
    checks = []
    font_hashes: dict[Path, str] = {}
    for record in records:
        sample_id = record["sample_id"]
        if sample_id in ids:
            raise ValueError(f"Duplicate render metadata ID: {sample_id}")
        ids.add(sample_id)
        config = RenderConfig(**record["render_config"])
        if (config.canvas_width, config.canvas_height) != (512, 64):
            raise ValueError("Versioned clean512 corpus must remain 512x64")
        image_path = (dataset_dir / record["image"]).resolve()
        if not image_path.is_relative_to(dataset_dir):
            raise ValueError("Image path escapes corpus directory")
        font_path = Path(record["font_path"])
        if font_path not in font_hashes:
            font_hashes[font_path] = file_sha256(font_path)
        if font_hashes[font_path] != record["font_sha256"]:
            raise ValueError(f"Font version changed for {sample_id}")
        if file_sha256(image_path) != record["image_sha256"]:
            raise ValueError(f"Saved image changed for {sample_id}")
        font = load_font(str(font_path), record["final_font_size"])
        position = tuple(record["text_position"])
        bounds = validate_render_bounds(
            record["target_text"], font, position, config, raise_on_error=False
        )
        if (
            list(bounds.text_bbox) != record["text_bbox"]
            or list(bounds.safe_area) != record["safe_area_bounds"]
        ):
            raise ValueError(
                f"Stored rendering geometry does not reproduce for {sample_id}"
            )
        with Image.open(image_path) as image:
            if image.mode != "L" or image.size != (512, 64):
                raise ValueError(f"Invalid image mode/geometry for {sample_id}")
            pixel_check = verify_pixels(
                record["target_text"], font, position, config, image
            )
        checks.append({"sample_id": sample_id, "split": record["split"], **pixel_check})
    return {
        "samples": len(checks),
        "projected_bounds_overflow_count": sum(
            not row["projected_bounds_fit"] for row in checks
        ),
        "actual_glyph_loss_count": sum(
            row["outside_canvas_ink_pixels"] > 0 for row in checks
        ),
        "safe_region_ink_overflow_count": sum(
            row["outside_safe_area_ink_pixels"] > 0 for row in checks
        ),
        "saved_image_mismatch_count": sum(
            not row["saved_image_matches"] for row in checks
        ),
        "samples_verified": checks,
    }
