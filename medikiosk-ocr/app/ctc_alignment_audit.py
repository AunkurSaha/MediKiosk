"""Diagnostic-only forced CTC alignment; never corrects recognition output."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
from Levenshtein import opcodes


def collapse(path: list[int], blank: int) -> list[int]:
    return [
        value
        for i, value in enumerate(path)
        if value != blank and (i == 0 or value != path[i - 1])
    ]


def log_probabilities(logits: np.ndarray) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float64).copy()
    values -= np.max(values, axis=-1, keepdims=True)
    return values - np.log(np.exp(values).sum(axis=-1, keepdims=True))


def forced_alignment(logp: np.ndarray, target: list[int], blank: int) -> dict:
    if (
        logp.ndim != 2
        or not target
        or blank in target
        or min(target) < 0
        or max(target + [blank]) >= logp.shape[1]
    ):
        raise ValueError("Invalid forced-alignment shape/target/blank")
    required = len(target) + sum(a == b for a, b in pairwise(target))
    if len(logp) < required:
        raise ValueError("Insufficient CTC timesteps")
    states = np.full(2 * len(target) + 1, blank, dtype=int)
    states[1::2] = target
    skip = np.zeros(len(states), dtype=bool)
    skip[2:] = (states[2:] != blank) & (states[2:] != states[:-2])
    score = np.full(len(states), -np.inf)
    score[:2] = logp[0, states[:2]]
    total = score.copy()
    parents = np.zeros((len(logp), len(states)), dtype=np.int8)
    for t in range(1, len(logp)):
        options = np.stack(
            [score, np.r_[-np.inf, score[:-1]], np.r_[-np.inf, -np.inf, score[:-2]]]
        )
        options[2, ~skip] = -np.inf
        parents[t] = np.argmax(options, axis=0)
        score = np.max(options, axis=0) + logp[t, states]
        sums = np.stack(
            [total, np.r_[-np.inf, total[:-1]], np.r_[-np.inf, -np.inf, total[:-2]]]
        )
        sums[2, ~skip] = -np.inf
        total = np.logaddexp.reduce(sums, axis=0) + logp[t, states]
    state = len(states) - 2 + int(score[-1] > score[-2])
    maximum = float(score[state])
    path = np.empty(len(logp), dtype=int)
    for t in range(len(logp) - 1, -1, -1):
        path[t] = state
        state -= int(parents[t, state])
    emissions = states[path].tolist()
    if collapse(emissions, blank) != target:
        raise AssertionError("Forced path failed exact CTC collapse")
    probability = np.exp(logp)
    characters = []
    previous_end = None
    for i, label in enumerate(target):
        frames = np.flatnonzero(path == 2 * i + 1)
        start, end = int(frames[0]), int(frames[-1])
        peak_frame = int(frames[np.argmax(probability[frames, label])])
        gap = (
            np.arange(previous_end + 1, start)
            if previous_end is not None
            else np.asarray([], dtype=int)
        )
        neighbor = [t for t in (start - 1, end + 1) if 0 <= t < len(logp)]
        characters.append(
            {
                "target_index": i,
                "label": label,
                "start": start,
                "end": end,
                "frame_span": end - start + 1,
                "peak_frame": peak_frame,
                "peak_probability": float(probability[peak_frame, label]),
                "probability_sum_assigned": float(probability[frames, label].sum()),
                "global_peak_probability": float(probability[:, label].max()),
                "peak_frame_argmax_label": int(probability[peak_frame].argmax()),
                "neighbor_blank_probability": float(probability[neighbor, blank].mean())
                if neighbor
                else None,
                "gap_from_previous_end": start - previous_end
                if previous_end is not None
                else None,
                "blank_dominant_frames_before": int(
                    sum(probability[gap].argmax(axis=1) == blank)
                )
                if len(gap)
                else 0,
                "peak_blank_between": float(probability[gap, blank].max())
                if len(gap)
                else None,
                "adjacent_identical_previous": i > 0 and target[i - 1] == label,
            }
        )
        previous_end = end
    return {
        "maximum_path_log_probability": maximum,
        "target_total_log_probability": float(np.logaddexp(total[-1], total[-2])),
        "state_path": path.tolist(),
        "label_path": emissions,
        "characters": characters,
    }


def projected_token(truth: str, prediction: str, start: int, end: int) -> dict:
    """Project full-line edit alignment onto a target span; not lexical correction."""
    pieces = []
    edits = {
        "digit_deletion": 0,
        "digit_substitution": 0,
        "hyphen_deletion": 0,
        "other_deletion": 0,
        "insertion": 0,
    }
    deleted = []
    for op, a, b, c, d in opcodes(truth, prediction):
        left, right = max(a, start), min(b, end)
        if op == "insert" and start <= a < end:
            pieces.append(prediction[c:d])
            edits["insertion"] += d - c
        elif left < right:
            if op == "equal":
                pieces.append(prediction[c + left - a : c + right - a])
            elif op == "delete":
                deleted.extend(range(left, right))
                for char in truth[left:right]:
                    key = (
                        "digit_deletion"
                        if char.isdigit()
                        else "hyphen_deletion"
                        if char == "-"
                        else "other_deletion"
                    )
                    edits[key] += 1
            else:
                pieces.append(prediction[c + left - a : c + right - a])
                edits["digit_substitution"] += sum(
                    x.isdigit() for x in truth[left:right]
                )
    return {
        "prediction": "".join(pieces),
        "edits": edits,
        "deleted_target_indices": deleted,
        "prefix_deleted": start in deleted,
        "suffix_deleted": end - 1 in deleted,
        "multi_character_deletion": len(deleted) >= 2,
        "method": "full-line Levenshtein opcode projection; boundary/duplicate-symbol alignment can be ambiguous",
    }
