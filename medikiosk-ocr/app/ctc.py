"""CTC vocabulary conventions shared by training and inference."""

from __future__ import annotations

import tensorflow as tf


def greedy_decode(logits: tf.Tensor, characters: list[str]) -> list[str]:
    """Decode logits whose labels are 1..N, padding is 0, and blank is N+1."""
    expected_classes = len(characters) + 2
    if logits.shape[-1] != expected_classes:
        raise ValueError(
            f"Expected {expected_classes} CTC classes, received {logits.shape[-1]}"
        )
    flattened = tf.reshape(logits, (tf.shape(logits)[0], -1, expected_classes))
    sequence_lengths = tf.fill([tf.shape(flattened)[0]], tf.shape(flattened)[1])
    decoded, _ = tf.keras.ops.ctc_decode(
        flattened,
        sequence_lengths=sequence_lengths,
        strategy="greedy",
        mask_index=expected_classes - 1,
    )
    results = []
    for row in decoded[0].numpy():
        results.append(
            "".join(
                characters[index - 1] for index in row if 0 < index <= len(characters)
            )
        )
    return results


def blank_probability(logits: tf.Tensor, characters: list[str]) -> float:
    """Return mean posterior probability assigned to the final CTC blank class."""
    expected_classes = len(characters) + 2
    return float(
        tf.reduce_mean(tf.nn.softmax(logits, axis=-1)[..., expected_classes - 1])
    )


def beam_decode(
    logits: tf.Tensor, characters: list[str], beam_width: int = 50
) -> list[str]:
    """Ordinary CTC beam search: final-class blank, no dictionary or correction."""
    classes = len(characters) + 2
    if logits.shape[-1] != classes:
        raise ValueError("CTC vocabulary/logit class mismatch")
    flattened = tf.reshape(logits, (tf.shape(logits)[0], -1, classes))
    lengths = tf.fill([tf.shape(flattened)[0]], tf.shape(flattened)[1])
    decoded, _ = tf.nn.ctc_beam_search_decoder(
        tf.transpose(flattened, (1, 0, 2)),
        sequence_length=lengths,
        beam_width=beam_width,
        top_paths=1,
    )
    dense = tf.sparse.to_dense(decoded[0], default_value=-1).numpy()
    return [
        "".join(characters[i - 1] for i in row if 0 < i <= len(characters))
        for row in dense
    ]
