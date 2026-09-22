from app.benchmark import (
    PrescriptionLexicon,
    classify_error,
    error_rates,
    exact_line_accuracy,
    prescription_field_accuracy,
)


def test_error_rates_are_corpus_weighted():
    cer, wer = error_rates(["ABC", "D E"], ["ABC", "D X"])
    assert cer == 1 / 6
    assert wer == 1 / 3


def test_prescription_field_metrics():
    lexicon = PrescriptionLexicon(
        medicines=frozenset({"PCM"}),
        doses=frozenset({"650 mg"}),
        frequencies=frozenset({"SOS"}),
        durations=frozenset({"5 days"}),
    )
    result = prescription_field_accuracy(
        ["PCM 650 mg SOS 5 days"], ["PCM 650 mg SOS 5 days"], lexicon
    )
    assert result == {"medicine": 1.0, "dose": 1.0, "frequency": 1.0, "duration": 1.0}
    spaced_result = prescription_field_accuracy(
        ["PCM  650  mg  SOS  5 days"], ["PCM 650 mg SOS 5 days"], lexicon
    )
    assert spaced_result["dose"] == 1.0


def test_line_accuracy_and_error_classification():
    assert exact_line_accuracy(["PCM 500", "BD"], ["PCM 500", "OD"]) == 0.5
    assert classify_error("PCM  500", "PCM 500") == "spacing"
    assert classify_error("PCM 500", "PCM 650") == "number"
