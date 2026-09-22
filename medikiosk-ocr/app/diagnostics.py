"""Deterministic CTC measurements and descriptive, non-causal error buckets."""

from __future__ import annotations

import re
import warnings
from itertools import pairwise

from app.benchmark import PrescriptionLexicon, _find, error_rates

SCHEDULE = re.compile(r"(?<!\d)\d(?:-\d){2}(?!\d)")


def alignment(text: str, time_steps: int, danger_ratio: float = 1.5) -> dict:
    repeats = sum(a == b for a, b in pairwise(text))
    required = len(text) + repeats
    ratio = time_steps / max(1, required)
    status = (
        "insufficient"
        if time_steps < required
        else "low_margin"
        if ratio < danger_ratio
        else "adequate"
    )
    return {
        "target_length": len(text),
        "adjacent_repeat_count": repeats,
        "minimum_ctc_steps": required,
        "output_time_steps": time_steps,
        "alignment_ratio": ratio,
        "alignment_status": status,
    }


def assert_alignment(text: str, time_steps: int) -> None:
    measurement = alignment(text, time_steps)
    if measurement["alignment_status"] == "insufficient":
        raise ValueError(
            f"CTC requires {measurement['minimum_ctc_steps']} steps, received {time_steps}"
        )
    if measurement["alignment_status"] == "low_margin":
        warnings.warn(
            "CTC alignment ratio below diagnostic threshold 1.5",
            RuntimeWarning,
            stacklevel=2,
        )


def buckets(text: str, medicine_names: frozenset[str]) -> list[str]:
    result = []
    if any(a == b for a, b in pairwise(text)):
        result.append("repeated_character")
    if SCHEDULE.search(text):
        result.append("numeric_schedule")
    if _find(text, medicine_names):
        result.append("medication")
    if "-" in text:
        result.append("punctuation_hyphen")
    if any(char.isspace() for char in text):
        result.append("spacing")
    if len(text) <= 25:
        result.append("short_line")
    elif len(text) >= 40:
        result.append("long_line")
    else:
        result.append("medium_line")
    return result


def conditional_fields(
    truths: list[str], predictions: list[str], lexicon: PrescriptionLexicon
) -> dict:
    result = {}
    for name, values in vars(lexicon).items():
        expected = [_find(text, values) for text in truths]
        actual = [_find(text, values) for text in predictions]
        present = [index for index, value in enumerate(expected) if value is not None]
        result[name] = {
            "overall_accuracy": sum(a == b for a, b in zip(expected, actual))
            / len(truths),
            "present_count": len(present),
            "absent_count": len(truths) - len(present),
            "present_accuracy": sum(expected[i] == actual[i] for i in present)
            / len(present)
            if present
            else None,
        }
    return result


def schedule_accuracy(truths: list[str], predictions: list[str]) -> dict:
    indices = [i for i, text in enumerate(truths) if SCHEDULE.search(text)]
    correct = sum(
        SCHEDULE.findall(truths[i]) == SCHEDULE.findall(predictions[i]) for i in indices
    )
    return {
        "present_count": len(indices),
        "accuracy": correct / len(indices) if indices else None,
    }


def summarize(rows: list[dict]) -> dict:
    truths = [row["truth"] for row in rows]
    predictions = [row["prediction"] for row in rows]
    cer, wer = error_rates(truths, predictions)
    return {
        "samples": len(rows),
        "cer": cer,
        "wer": wer,
        "exact_line_accuracy": sum(a == b for a, b in zip(truths, predictions))
        / len(rows),
    }
