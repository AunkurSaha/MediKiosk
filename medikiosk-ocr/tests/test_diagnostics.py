import pytest

from app.benchmark import PrescriptionLexicon
from app.diagnostics import (
    alignment,
    assert_alignment,
    buckets,
    conditional_fields,
    schedule_accuracy,
)


def test_minimum_ctc_length_counts_adjacent_repeats_not_all_duplicates():
    assert alignment("food", 5)["minimum_ctc_steps"] == 5
    assert alignment("1-1-1", 5)["minimum_ctc_steps"] == 5
    assert alignment("bookkeeper", 20)["adjacent_repeat_count"] == 3
    with pytest.raises(ValueError):
        assert_alignment("food", 4)
    with pytest.warns(RuntimeWarning):
        assert_alignment("food", 6)


def test_buckets_are_overlapping_descriptors():
    result = buckets("Amoxicillin 500 mg 1-1-1", frozenset({"Amoxicillin"}))
    assert {
        "repeated_character",
        "numeric_schedule",
        "medication",
        "punctuation_hyphen",
    } <= set(result)


def test_present_accuracy_excludes_correct_absence():
    lexicon = PrescriptionLexicon(
        frozenset(), frozenset(), frozenset(), frozenset({"x 3d"})
    )
    result = conditional_fields(["PCM", "PCM x 3d"], ["PCM", "PCM"], lexicon)
    assert result["durations"]["overall_accuracy"] == 0.5
    assert result["durations"]["present_accuracy"] == 0.0
    assert schedule_accuracy(["PCM 1-1-1"], ["PCM 1"])["accuracy"] == 0.0
