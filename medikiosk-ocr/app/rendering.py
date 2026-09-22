"""Measured, deterministic text fitting without cropping or image resampling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class RenderConfig:
    canvas_width: int = 512
    canvas_height: int = 64
    margin_left: int = 4
    margin_right: int = 8
    margin_top: int = 8
    margin_bottom: int = 8
    minimum_font_size: int = 14
    maximum_font_size: int = 24
    background: int = 255
    ink: int = 0
    anchor: str = "la"

    def __post_init__(self) -> None:
        if min(self.canvas_width, self.canvas_height, self.minimum_font_size) <= 0:
            raise ValueError("Canvas dimensions and minimum font size must be positive")
        if (
            min(
                self.margin_left, self.margin_right, self.margin_top, self.margin_bottom
            )
            < 0
        ):
            raise ValueError("Margins must be nonnegative")
        if (
            self.safe_area[0] >= self.safe_area[2]
            or self.safe_area[1] >= self.safe_area[3]
        ):
            raise ValueError("Margins leave no usable canvas")
        if self.minimum_font_size > self.maximum_font_size:
            raise ValueError("Minimum font size exceeds maximum")
        if (
            not 0 <= self.background <= 255
            or not 0 <= self.ink <= 255
            or self.background == self.ink
        ):
            raise ValueError(
                "Rendering requires distinct valid grayscale background and ink"
            )
        if self.anchor != "la":
            raise ValueError("Only explicit left-ascender anchor 'la' is supported")

    @property
    def safe_area(self) -> tuple[int, int, int, int]:
        return (
            self.margin_left,
            self.margin_top,
            self.canvas_width - self.margin_right,
            self.canvas_height - self.margin_bottom,
        )


@dataclass(frozen=True)
class RenderBounds:
    text_bbox: tuple[int, int, int, int]
    safe_area: tuple[int, int, int, int]
    canvas_bounds: tuple[int, int, int, int]
    fits_canvas: bool
    fits_safe_area: bool
    overflow: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


class RenderBoundsError(ValueError):
    def __init__(self, message: str, bounds: RenderBounds) -> None:
        self.bounds = bounds
        super().__init__(
            f"{message}; bbox={bounds.text_bbox}; safe={bounds.safe_area}; overflow={bounds.overflow}"
        )


@lru_cache(maxsize=512)
def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def validate_render_bounds(
    text: str,
    font: ImageFont.FreeTypeFont,
    position: tuple[int, int],
    config: RenderConfig,
    *,
    raise_on_error: bool = True,
) -> RenderBounds:
    if not text or not text.strip():
        raise ValueError("Empty/whitespace-only target cannot be rendered")
    probe = ImageDraw.Draw(Image.new("L", (1, 1), config.background))
    bbox = tuple(probe.textbbox(position, text, font=font, anchor=config.anchor))
    left, top, right, bottom = bbox
    safe_left, safe_top, safe_right, safe_bottom = config.safe_area
    fits_canvas = (
        0 <= left <= right <= config.canvas_width
        and 0 <= top <= bottom <= config.canvas_height
    )
    fits_safe = (
        safe_left <= left <= right <= safe_right
        and safe_top <= top <= bottom <= safe_bottom
    )
    bounds = RenderBounds(
        bbox,
        config.safe_area,
        (0, 0, config.canvas_width, config.canvas_height),
        fits_canvas,
        fits_safe,
        {
            "left": max(0, safe_left - left),
            "top": max(0, safe_top - top),
            "right": max(0, right - safe_right),
            "bottom": max(0, bottom - safe_bottom),
        },
    )
    if not fits_safe and raise_on_error:
        raise RenderBoundsError(
            "Visible text bounds do not fit the usable canvas", bounds
        )
    return bounds


@dataclass(frozen=True)
class FontFit:
    font_path: Path
    requested_size: int
    final_size: int
    retry_count: int
    bounds: RenderBounds


def fit_font_group(
    text: str,
    font_paths: list[Path],
    requested_size: int,
    position: tuple[int, int],
    config: RenderConfig,
) -> list[FontFit]:
    """Use one common final size for matched phrases across multiple renderers."""
    if not font_paths:
        raise ValueError("At least one renderer/font is required")
    if not config.minimum_font_size <= requested_size <= config.maximum_font_size:
        raise ValueError("Requested size must be within explicit minimum/maximum")
    last_bounds = None
    for size in range(requested_size, config.minimum_font_size - 1, -1):
        bounds = [
            validate_render_bounds(
                text, load_font(str(path), size), position, config, raise_on_error=False
            )
            for path in font_paths
        ]
        if all(item.fits_safe_area for item in bounds):
            return [
                FontFit(path, requested_size, size, requested_size - size, item)
                for path, item in zip(font_paths, bounds)
            ]
        last_bounds = next(item for item in bounds if not item.fits_safe_area)
    assert last_bounds is not None
    raise RenderBoundsError(
        f"Cannot fit target at minimum_font_size={config.minimum_font_size}; fonts={font_paths}; text={text!r}",
        last_bounds,
    )


def fit_font(
    text: str,
    font_path: Path,
    requested_size: int,
    position: tuple[int, int],
    config: RenderConfig,
) -> FontFit:
    return fit_font_group(text, [font_path], requested_size, position, config)[0]


def render_fitted(
    text: str, fit: FontFit, position: tuple[int, int], config: RenderConfig
) -> Image.Image:
    font = load_font(str(fit.font_path), fit.final_size)
    validate_render_bounds(
        text, font, position, config
    )  # Guard immediately before rendering/saving.
    image = Image.new(
        "L", (config.canvas_width, config.canvas_height), config.background
    )
    ImageDraw.Draw(image).text(
        position, text, fill=config.ink, font=font, anchor=config.anchor
    )
    return image


def verify_pixels(
    text: str,
    font: ImageFont.FreeTypeFont,
    position: tuple[int, int],
    config: RenderConfig,
    saved_image: Image.Image | None = None,
) -> dict:
    """Render on a padded scene and independently count ANY non-background ink."""
    bounds = validate_render_bounds(text, font, position, config, raise_on_error=False)
    left, top, right, bottom = bounds.text_bbox
    scene_left, scene_top = min(0, left) - 64, min(0, top) - 64
    scene_right = max(config.canvas_width, right) + 64
    scene_bottom = max(config.canvas_height, bottom) + 64
    scene = Image.new(
        "L", (scene_right - scene_left, scene_bottom - scene_top), config.background
    )
    ImageDraw.Draw(scene).text(
        (position[0] - scene_left, position[1] - scene_top),
        text,
        font=font,
        fill=config.ink,
        anchor=config.anchor,
    )
    pixels = np.asarray(scene)
    ink = pixels != config.background
    canvas = pixels[
        -scene_top : config.canvas_height - scene_top,
        -scene_left : config.canvas_width - scene_left,
    ]
    safe_left, safe_top, safe_right, safe_bottom = config.safe_area
    safe_ink = ink[
        safe_top - scene_top : safe_bottom - scene_top,
        safe_left - scene_left : safe_right - scene_left,
    ]
    canvas_ink = canvas != config.background
    return {
        "outside_canvas_ink_pixels": int(
            np.count_nonzero(ink) - np.count_nonzero(canvas_ink)
        ),
        "outside_safe_area_ink_pixels": int(
            np.count_nonzero(ink) - np.count_nonzero(safe_ink)
        ),
        "saved_image_matches": None
        if saved_image is None
        else bool(np.array_equal(canvas, np.asarray(saved_image))),
        "projected_bounds_fit": bounds.fits_safe_area,
        "strict_nonbackground_threshold": config.background,
    }
