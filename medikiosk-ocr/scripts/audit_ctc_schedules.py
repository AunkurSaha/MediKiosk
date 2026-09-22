"""Frozen-checkpoint, train/validation-only numeric CTC audit (no training)."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
for directory in (
    ROOT,
    ROOT / "upstream/handwritten-text-recognition",
    ROOT / "scripts",
):
    sys.path.insert(0, str(directory))

from sarah.models.recognition.flor import RecognitionModel
from train_generalization import batches, image_tensor

from app.augmentation import augment, load_preset
from app.ctc import beam_decode, greedy_decode
from app.ctc_alignment_audit import (
    collapse,
    forced_alignment,
    log_probabilities,
    projected_token,
)
from app.dataset import load_manifest
from app.diagnostics import summarize
from app.render_metadata import file_sha256

OUT = ROOT / "benchmarks/clean512_v2_ctc_schedule_audit"
DATA = ROOT / "datasets/synthetic/clean512_v2"
CHECKPOINT = ROOT / "models/clean512_v2_controlled_flor.weights.h5"
EXPECTED = "c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b"
SCHEDULE = re.compile(r"(?<!\d)\d-\d-\d(?!\d)")
DURATION = re.compile(r"\bx\s+[357]d\b|\bfor\s+[357]\s+days\b")
ROLES = ["first_digit", "first_hyphen", "middle_digit", "second_hyphen", "final_digit"]


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


def stats(values):
    values = np.asarray(values, dtype=float)
    return (
        {
            "n": len(values),
            "mean": float(values.mean()),
            "median": float(np.median(values)),
            "p10": float(np.percentile(values, 10)),
            "p25": float(np.percentile(values, 25)),
        }
        if len(values)
        else {"n": 0}
    )


def weight_hash(model):
    digest = hashlib.sha256()
    for weight in model.weights:
        digest.update(weight.numpy().tobytes())
    return digest.hexdigest()


def snapshot():
    frozen = json.loads(
        (ROOT / "benchmarks/clean512_v2_controlled/immutability.json").read_text()
    )["after"]
    selected = {
        p: h
        for p, h in frozen.items()
        if "datasets/synthetic/clean512_v2/" in p.replace("\\", "/")
    }
    if len(selected) < 1000:
        raise AssertionError("Missing frozen dataset snapshot")
    actual = {p: file_sha256(ROOT / p) for p in selected}
    assert actual == selected, "Frozen corpus hash mismatch"
    assert file_sha256(CHECKPOINT) == EXPECTED
    return {
        **actual,
        str(CHECKPOINT.relative_to(ROOT)): EXPECTED,
        "models/clean512_v2_controlled_flor.weights.json": file_sha256(
            CHECKPOINT.with_suffix(".json")
        ),
    }


def token_geometry(metadata, text, start, end):
    font = ImageFont.truetype(metadata["font_path"], metadata["final_font_size"])
    x = metadata["text_position"][0]
    return {
        "approx_x_start": x + float(font.getlength(text[:start])),
        "approx_x_end": x + float(font.getlength(text[:end])),
        "method": "Pillow prefix advances; approximate glyph location, not CNN receptive field",
    }


def summarize_characters(rows):
    result = {}
    for key, selected in sorted(rows.items()):
        result[key] = {
            "occurrences": len(selected),
            "peak": stats([x["peak_probability"] for x in selected]),
            "span": stats([x["frame_span"] for x in selected]),
            "neighbor_blank": stats(
                [x["neighbor_blank_probability"] for x in selected]
            ),
            "weak_below_0_1": sum(x["peak_probability"] < 0.1 for x in selected)
            / len(selected),
            "non_argmax_rate": sum(
                x["peak_frame_argmax_label"] != x["label"] for x in selected
            )
            / len(selected),
        }
    return result


def main():
    before = snapshot()
    OUT.mkdir(exist_ok=False)
    metadata = {
        m["sample_id"]: m
        for line in (DATA / "render_metadata.jsonl").read_text().splitlines()
        if (m := json.loads(line))["split"] in ("train", "validation")
    }
    sidecar = json.loads(CHECKPOINT.with_suffix(".json").read_text())
    characters = sidecar["characters"]
    mapping = {c: i + 1 for i, c in enumerate(characters)}
    blank = len(characters) + 1
    assert (
        sidecar["image_shape"] == [64, 512, 1] and sidecar["ctc_blank_index"] == blank
    )
    config = {
        "version": 1,
        "scope": ["train", "validation"],
        "test": "not run; optional confirmation omitted",
        "checkpoint_sha256": EXPECTED,
        "vocabulary": mapping,
        "padding_index": 0,
        "blank_index": blank,
        "requested_digit_ids": {c: mapping.get(c) for c in "0123456789- "},
        "absent_vocabulary_symbols": [c for c in "0123456789" if c not in mapping],
        "input": [64, 512, 1],
        "output_steps": 128,
        "beam_width": 50,
        "top_paths": 5,
        "weak_threshold": 0.1,
        "strong_threshold": 0.5,
        "threshold_caution": "descriptive cutoffs, not calibrated confidence or causal tests",
        "alignment": "deterministic Viterbi, tie prefer stay, then advance1, then advance2; full target; separate exact forward probability",
        "token_projection": "deterministic full-line Levenshtein; duplicate symbols and boundaries may yield ambiguous token attribution",
        "augmentation_control_seed": 410000,
        "scripts": {
            p: file_sha256(ROOT / p)
            for p in [
                "scripts/audit_ctc_schedules.py",
                "app/ctc_alignment_audit.py",
                "app/augmentation.py",
                "app/ctc.py",
                "scripts/train_generalization.py",
                "configs/light_augmentation.json",
            ]
        },
        "hypotheses": "A weak posterior; B greedy collapse; C beam ranking; D separation; E geometry correlation; F augmentation plausibility; G multiple/no single mechanism",
    }
    write("audit_config.json", config)
    model = RecognitionModel(
        name="numeric_audit",
        image_shape=(64, 512, 1),
        lexical_shape=(1, sidecar["max_label_length"], len(characters) + 2),
        seed=41,
    ).recognition
    model.load_weights(CHECKPOINT)
    assert tuple(model.input_shape[1:]) == (64, 512, 1)
    weights_before = weight_hash(model)
    index, aligned_rows, paths, token_rows, all_lines = [], [], [], [], []
    char_groups = defaultdict(list)
    (OUT / "raw").mkdir()
    with (OUT / "posterior_traces.jsonl").open("w", encoding="utf-8") as traces:
        for split in ("train", "validation"):
            samples = load_manifest(DATA / f"{split}.csv")
            for batch_index, batch in enumerate(batches(samples, 32)):
                raw = model(
                    np.asarray([image_tensor(s, None, 0) for s in batch]),
                    training=False,
                )
                flat = tf.reshape(raw, (len(batch), 128, len(characters) + 2))
                greedy, locked = (
                    greedy_decode(raw, characters),
                    beam_decode(raw, characters, 50),
                )
                candidates, scores = tf.nn.ctc_beam_search_decoder(
                    tf.transpose(flat, (1, 0, 2)),
                    tf.fill([len(batch)], 128),
                    beam_width=50,
                    top_paths=5,
                )
                decoded = [
                    tf.sparse.to_dense(c, default_value=-1).numpy() for c in candidates
                ]
                for j, sample in enumerate(batch):
                    text, mid = sample.text, sample.sample_id
                    m = metadata[mid]
                    assert m["target_text"] == text
                    logits = flat[j].numpy()
                    assert logits.shape == (128, len(characters) + 2)
                    logp = log_probabilities(logits)
                    probs = np.exp(logp)
                    np.savez_compressed(
                        OUT / "raw" / f"{mid}.npz", logits=logits, probabilities=probs
                    )
                    forced = forced_alignment(logp, [mapping[c] for c in text], blank)
                    beam = [
                        {
                            "rank": k + 1,
                            "prediction": "".join(
                                characters[v - 1]
                                for v in decoded[k][j]
                                if 0 < v <= len(characters)
                            ),
                            "log_probability": float(scores[j, k]),
                        }
                        for k in range(5)
                    ]
                    assert beam[0]["prediction"] == locked[j]
                    argmax = logits.argmax(axis=1).tolist()
                    collapsed = "".join(
                        characters[v - 1]
                        for v in collapse(argmax, blank)
                        if 0 < v <= len(characters)
                    )
                    assert collapsed == greedy[j]
                    line = {
                        "sample_id": mid,
                        "split": split,
                        "truth": text,
                        "prediction": locked[j],
                        "greedy": greedy[j],
                    }
                    all_lines.append(line)
                    schedules, durations = (
                        list(SCHEDULE.finditer(text)),
                        list(DURATION.finditer(text)),
                    )
                    tokens = [("schedule", t) for t in schedules] + [
                        ("duration", t) for t in durations
                    ]
                    row = {
                        **line,
                        "renderer": m["renderer"],
                        "requested_font_size": m["original_requested_font_size"],
                        "final_font_size": m["final_font_size"],
                        "fitted": m["was_resized_or_fitted"],
                        "text_bbox": m["text_bbox"],
                        "text_width": m["rendered_text_width"],
                        "target_schedule": [t.group() for t in schedules],
                        "target_duration": [t.group() for t in durations],
                        "target_length": len(text),
                        "ctc_required_steps": len(text)
                        + sum(a == b for a, b in pairwise(text)),
                        "output_steps": 128,
                    }
                    contexts = {}
                    for kind, token in tokens:
                        projected = projected_token(
                            text, locked[j], token.start(), token.end()
                        )
                        greedy_projected = projected_token(
                            text, greedy[j], token.start(), token.end()
                        )
                        tokenrow = {
                            **row,
                            "kind": kind,
                            "token": token.group(),
                            "start": token.start(),
                            "end": token.end(),
                            "projected": projected,
                            "beam_correct": projected["prediction"] == token.group(),
                            "greedy_correct": greedy_projected["prediction"]
                            == token.group(),
                            "greedy_projected": greedy_projected,
                            **token_geometry(m, text, token.start(), token.end()),
                        }
                        token_chars = []
                        for offset, position in enumerate(
                            range(token.start(), token.end())
                        ):
                            char = {
                                **forced["characters"][position],
                                "character": text[position],
                                "role": ROLES[offset]
                                if kind == "schedule"
                                else "numeral"
                                if text[position].isdigit()
                                else "neighbor_word_or_space",
                            }
                            char["competing_probabilities_at_peak"] = {
                                c: float(probs[char["peak_frame"], mapping[c]])
                                for c in "01357- "
                            }
                            token_chars.append(char)
                            contexts[position] = (
                                "schedule"
                                if kind == "schedule"
                                else "duration_digit"
                                if text[position].isdigit()
                                else "duration_neighbor"
                            )
                        tokenrow["characters"] = token_chars
                        tokenrow["target_total_log_probability"] = forced[
                            "target_total_log_probability"
                        ]
                        tokenrow["maximum_path_log_probability"] = forced[
                            "maximum_path_log_probability"
                        ]
                        token_rows.append(tokenrow)
                    for i, char in enumerate(forced["characters"]):
                        char.update(
                            character=text[i],
                            context=contexts.get(
                                i, "dose_digit" if text[i].isdigit() else "other"
                            ),
                        )
                        for key in [
                            text[i],
                            f"{text[i]}|{char['context']}",
                            f"{text[i]}|{'correct_line' if locked[j] == text else 'incorrect_line'}",
                        ]:
                            char_groups[key].append(char)
                    if tokens:
                        index.append(row)
                        aligned_rows.append(
                            {"sample_id": mid, "split": split, "truth": text, **forced}
                        )
                        paths.append(
                            {
                                "sample_id": mid,
                                "split": split,
                                "truth": text,
                                "greedy_argmax_path": argmax,
                                "greedy_collapsed": collapsed,
                                "beam_candidates": beam,
                                "exact_target_rank_top5": next(
                                    (
                                        b["rank"]
                                        for b in beam
                                        if b["prediction"] == text
                                    ),
                                    None,
                                ),
                                "full_schedule_ranks_top5": {
                                    t.group(): [
                                        b["rank"]
                                        for b in beam
                                        if t.group() in b["prediction"]
                                    ]
                                    for t in schedules
                                },
                                "target_total_log_probability": forced[
                                    "target_total_log_probability"
                                ],
                                "beam_top1_log_probability": beam[0]["log_probability"],
                                "target_minus_beam_log_probability": forced[
                                    "target_total_log_probability"
                                ]
                                - beam[0]["log_probability"],
                            }
                        )
                        frames = []
                        for t in range(128):
                            top = np.argsort(probs[t])[-5:][::-1]
                            frames.append(
                                {
                                    "timestep": t,
                                    "top5": [
                                        {
                                            "id": int(k),
                                            "character": "<blank>"
                                            if k == blank
                                            else "<padding>"
                                            if k == 0
                                            else characters[k - 1],
                                            "probability": float(probs[t, k]),
                                        }
                                        for k in top
                                    ],
                                    "blank_probability": float(probs[t, blank]),
                                    "numeric_probabilities": {
                                        c: float(probs[t, mapping[c]])
                                        if c in mapping
                                        else None
                                        for c in "0123456789- "
                                    },
                                }
                            )
                        traces.write(
                            json.dumps({"sample_id": mid, "frames": frames}) + "\n"
                        )
                print(
                    f"{split} batch {batch_index + 1}: emissions and alignments captured",
                    flush=True,
                )
    assert weight_hash(model) == weights_before, "Inference changed in-memory weights"
    assert snapshot() == before, "Audit changed frozen artifacts"
    write(
        "immutability.json",
        {
            "before": before,
            "after": before,
            "unchanged": True,
            "in_memory_weights_before": weights_before,
            "in_memory_weights_after": weight_hash(model),
            "output_shape": list(raw.shape),
            "alignment_warnings": [
                {r["sample_id"]: r["ctc_required_steps"]}
                for r in index
                if 128 / r["ctc_required_steps"] < 1.5
            ],
        },
    )
    write("sample_index.json", index)
    with (OUT / "forced_alignments.jsonl").open("w", encoding="utf-8") as handle:
        for r in aligned_rows:
            handle.write(json.dumps(r) + "\n")
    write("decoder_path_comparison.json", paths)
    write("token_details.json", token_rows)
    write("character_statistics.json", summarize_characters(char_groups))
    posterior_groups = defaultdict(list)
    geometry_groups = defaultdict(list)
    for r in token_rows:
        state = "correct" if r["beam_correct"] else "incorrect"
        for c in r["characters"]:
            for key in [
                f"{r['kind']}|{r['token']}|{state}|{c['role']}",
                f"{r['kind']}|{r['split']}|{state}|{c['role']}",
            ]:
                posterior_groups[key].append(c)
        for key in [
            f"{r['kind']}|{r['split']}|{state}",
            f"{r['kind']}|renderer:{r['renderer']}|{state}",
            f"{r['kind']}|fitted:{r['fitted']}|{state}",
        ]:
            geometry_groups[key].append(r)
    write("posterior_summary.json", summarize_characters(posterior_groups))
    write(
        "geometry_correlations.json",
        {
            key: {
                "n": len(rows),
                "font_size": stats([r["final_font_size"] for r in rows]),
                "target_length": stats([r["target_length"] for r in rows]),
                "text_width": stats([r["text_width"] for r in rows]),
                "x_start": stats([r["approx_x_start"] for r in rows]),
                "x_end": stats([r["approx_x_end"] for r in rows]),
            }
            for key, rows in geometry_groups.items()
        },
    )
    for kind in ("schedule", "duration"):
        selected = [r for r in token_rows if r["kind"] == kind]
        matrix = {}
        for split in ("train", "validation"):
            group = [r for r in selected if r["split"] == split]
            transitions = Counter(
                (r["token"], r["projected"]["prediction"]) for r in group
            )
            matrix[split] = {
                "n": len(group),
                "beam_correct": sum(r["beam_correct"] for r in group),
                "greedy_correct": sum(r["greedy_correct"] for r in group),
                "transitions": [
                    {"truth": a, "prediction": b, "n": n}
                    for (a, b), n in sorted(
                        transitions.items(), key=lambda p: (-p[1], p[0])
                    )
                ],
                "edit_counts": dict(
                    sum((Counter(r["projected"]["edits"]) for r in group), Counter())
                ),
                "prefix_deleted": sum(r["projected"]["prefix_deleted"] for r in group),
                "suffix_deleted": sum(r["projected"]["suffix_deleted"] for r in group),
                "multi_character_deletion": sum(
                    r["projected"]["multi_character_deletion"] for r in group
                ),
            }
        write(f"{kind}_error_matrix.json", matrix)
    write(
        "line_metrics.json",
        {
            split: summarize([r for r in all_lines if r["split"] == split])
            for split in ("train", "validation")
        },
    )
    preset = load_preset(ROOT / "configs/light_augmentation.json")
    augmentation_rows = []
    for i, r in enumerate(
        t for t in token_rows if t["kind"] == "schedule" and t["split"] == "train"
    ):
        image = cv2.imread(str(DATA / f"{r['sample_id']}.png"), cv2.IMREAD_GRAYSCALE)
        transformed = augment(image, preset, 410000 + i)
        # Crop to approximate original schedule bounds before transforming a paired mask.
        mask = np.full_like(image, 255)
        left = max(0, int(np.floor(r["approx_x_start"])))
        right = min(512, int(np.ceil(r["approx_x_end"])))
        mask[:, left:right] = image[:, left:right]
        paired = augment(mask, preset, 410000 + i)

        def pixels(im):
            yy, xx = np.where(im < 220)
            return {
                "ink_pixels": len(xx),
                "bbox": [
                    int(xx.min()),
                    int(yy.min()),
                    int(xx.max() + 1),
                    int(yy.max() + 1),
                ]
                if len(xx)
                else None,
                "centroid_x": float(xx.mean()) if len(xx) else None,
                "edge_ink": int(
                    np.count_nonzero(im[[0, -1], :] < 220)
                    + np.count_nonzero(im[:, [0, -1]] < 220)
                ),
                "laplacian_variance": float(cv2.Laplacian(im, cv2.CV_64F).var()),
                "minimum_intensity": int(im.min()),
            }

        base, after = pixels(mask), pixels(paired)
        augmentation_rows.append(
            {
                "sample_id": r["sample_id"],
                "seed": 410000 + i,
                "base": base,
                "paired_schedule_after": after,
                "full_line_after": pixels(transformed),
                "schedule_width_ratio": (after["bbox"][2] - after["bbox"][0])
                / (base["bbox"][2] - base["bbox"][0])
                if base["bbox"] and after["bbox"]
                else None,
                "horizontal_shift": after["centroid_x"] - base["centroid_x"]
                if base["centroid_x"] is not None and after["centroid_x"] is not None
                else None,
            }
        )
    write(
        "augmentation_audit.json",
        {
            "preset": preset,
            "historical_replay_proven": False,
            "method": "controlled current-implementation examples, one declared seed per schedule-bearing train sample; paired crop mask is approximate, not a regenerated dataset or exact historical epoch replay",
            "visibility_caution": "Zero edge ink is not proof that every glyph remains fully visible. Paired mask cropping can exclude kerning spill and surrounding context; transformations are seeded identically but brightness/global background are contextual.",
            "rows": augmentation_rows,
            "width_ratio": stats(
                [
                    r["schedule_width_ratio"]
                    for r in augmentation_rows
                    if r["schedule_width_ratio"] is not None
                ]
            ),
            "horizontal_shift": stats(
                [
                    r["horizontal_shift"]
                    for r in augmentation_rows
                    if r["horizontal_shift"] is not None
                ]
            ),
            "edge_ink_cases": sum(
                r["paired_schedule_after"]["edge_ink"] > 0 for r in augmentation_rows
            ),
        },
    )
    assert snapshot() == before
    write(
        "test_confirmation.json",
        {
            "status": "not run",
            "reason": "Optional confirmation omitted; no test predictions inspected or test inference executed in this audit",
            "hypotheses_and_metrics_frozen_in": "audit_config.json",
        },
    )
    print("Audit artifacts complete; no training or test inference.", flush=True)


if __name__ == "__main__":
    main()
