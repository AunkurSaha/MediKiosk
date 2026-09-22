from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from app.rendering import (
    RenderBoundsError,
    RenderConfig,
    fit_font,
    fit_font_group,
    load_font,
    render_fitted,
    validate_render_bounds,
    verify_pixels,
)

ARIAL = Path("C:/Windows/Fonts/arial.ttf")
COURIER = Path("C:/Windows/Fonts/cour.ttf")


@pytest.fixture
def config():
    return RenderConfig()


def test_long_phrase_fits_by_font_reduction_without_resampling(config):
    text = "Tab Amoxicillin 650 mg 1-1-1 for 7 days before food"
    fit = fit_font(text, COURIER, 24, (8, 15), config)
    assert 14 <= fit.final_size < 24
    assert fit.retry_count == 24 - fit.final_size
    image = render_fitted(text, fit, (8, 15), config)
    assert image.size == (512, 64)
    assert (
        verify_pixels(
            text, load_font(str(COURIER), fit.final_size), (8, 15), config, image
        )["outside_safe_area_ink_pixels"]
        == 0
    )


@pytest.mark.parametrize("position", [(500, 15), (-20, 15), (8, -20), (8, 60)])
def test_all_edges_reject_overflow(config, position):
    with pytest.raises(RenderBoundsError) as error:
        validate_render_bounds(
            "PCM 650 mg", load_font(str(ARIAL), 24), position, config
        )
    assert not error.value.bounds.fits_safe_area
    pixels = verify_pixels("PCM 650 mg", load_font(str(ARIAL), 24), position, config)
    assert pixels["outside_safe_area_ink_pixels"] > 0


def test_minimum_font_failure_is_explicit_and_terminates(config):
    with pytest.raises(RenderBoundsError, match="minimum_font_size=14"):
        fit_font("Amoxicillin " * 80, ARIAL, 24, (8, 15), config)


def test_minimum_is_a_valid_last_attempt(config):
    fixed = replace(config, minimum_font_size=24)
    with pytest.raises(RenderBoundsError):
        fit_font("Amoxicillin " * 20, ARIAL, 24, (8, 15), fixed)


def test_normal_sample_retains_size_position_and_pixels(config):
    text = "PCM 500 mg BD"
    fit = fit_font(text, ARIAL, 23, (8, 15), config)
    assert fit.final_size == 23 and fit.retry_count == 0
    first = render_fitted(text, fit, (8, 15), config)
    second_fit = fit_font(text, ARIAL, 23, (8, 15), config)
    assert fit == second_fit
    assert np.array_equal(
        np.asarray(first), np.asarray(render_fitted(text, second_fit, (8, 15), config))
    )


def test_matched_renderers_use_a_common_size(config):
    fits = fit_font_group(
        "Tab Amoxicillin 650 mg for 7 days before food",
        [ARIAL, COURIER],
        24,
        (8, 15),
        config,
    )
    assert len({fit.final_size for fit in fits}) == 1
    assert all(fit.bounds.fits_safe_area for fit in fits)


def test_safe_margin_enforced_even_when_canvas_fits(config):
    bounds = validate_render_bounds(
        "PCM", load_font(str(ARIAL), 24), (0, 15), config, raise_on_error=False
    )
    assert bounds.fits_canvas and not bounds.fits_safe_area


def test_invalid_configuration_and_requested_size_fail(config):
    with pytest.raises(ValueError):
        RenderConfig(margin_left=512)
    with pytest.raises(ValueError):
        fit_font("PCM", ARIAL, 30, (8, 15), config)
