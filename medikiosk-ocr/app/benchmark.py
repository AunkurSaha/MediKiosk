"""Recognition metrics for prescription-line experiments."""

from __future__ import annotations

from dataclasses import dataclass

from Levenshtein import distance


@dataclass(frozen=True)
class PrescriptionLexicon:
    medicines: frozenset[str]
    doses: frozenset[str]
    frequencies: frozenset[str]
    durations: frozenset[str]
    forms: frozenset[str] = frozenset()
    instructions: frozenset[str] = frozenset()


def error_rates(truths: list[str], predictions: list[str]) -> tuple[float, float]:
    character_errors = sum(distance(a, b) for a, b in zip(truths, predictions))
    character_total = sum(max(1, len(value)) for value in truths)
    word_errors = sum(
        distance(a.split(), b.split()) for a, b in zip(truths, predictions)
    )
    word_total = sum(max(1, len(value.split())) for value in truths)
    return character_errors / character_total, word_errors / word_total


def _find(text: str, values: frozenset[str]) -> str | None:
    normalized = f" {' '.join(text.casefold().split())} "
    matches = [
        value
        for value in values
        if f" {' '.join(value.casefold().split())} " in normalized
    ]
    return max(matches, key=len, default=None)


def prescription_field_accuracy(
    truths: list[str], predictions: list[str], lexicon: PrescriptionLexicon
) -> dict[str, float]:
    fields = {
        "medicine": lexicon.medicines,
        "dose": lexicon.doses,
        "frequency": lexicon.frequencies,
        "duration": lexicon.durations,
    }
    return {
        name: sum(
            _find(a, values) == _find(b, values) for a, b in zip(truths, predictions)
        )
        / len(truths)
        for name, values in fields.items()
    }


def exact_line_accuracy(truths: list[str], predictions: list[str]) -> float:
    return sum(
        truth == prediction for truth, prediction in zip(truths, predictions)
    ) / len(truths)


def classify_error(truth: str, prediction: str) -> str:
    if truth == prediction:
        return "exact"
    if "".join(truth.split()) == "".join(prediction.split()):
        return "spacing"
    truth_digits = "".join(char for char in truth if char.isdigit())
    prediction_digits = "".join(char for char in prediction if char.isdigit())
    if truth_digits != prediction_digits:
        return "number"
    if len(truth) >= 30:
        return "long_line"
    return "character_confusion_or_omission"
