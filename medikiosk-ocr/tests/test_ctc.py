import tensorflow as tf

from app.ctc import beam_decode, greedy_decode


def test_decoder_uses_final_class_as_blank_and_preserves_label_one():
    # Classes: padding=0 (not emitted), A=1, B=2, blank=3.
    indices = [3, 1, 1, 3, 2, 3]
    logits = tf.one_hot([indices], depth=4, on_value=12.0, off_value=-12.0)

    assert greedy_decode(logits, ["A", "B"]) == ["AB"]


def test_both_decoders_preserve_blank_separated_repeats():
    logits = tf.one_hot([[1, 1, 3, 1, 3]], depth=4, on_value=12.0, off_value=-12.0)
    assert greedy_decode(logits, ["A", "B"]) == ["AA"]
    assert beam_decode(logits, ["A", "B"]) == ["AA"]


def test_schedule_digits_are_separated_by_hyphens_not_ctc_blanks():
    logits = tf.one_hot([[1, 2, 1, 2, 1]], depth=4, on_value=12.0, off_value=-12.0)
    assert greedy_decode(logits, ["1", "-"]) == ["1-1-1"]
    assert beam_decode(logits, ["1", "-"]) == ["1-1-1"]
