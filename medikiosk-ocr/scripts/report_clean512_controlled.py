"""Read frozen results and evaluate the unchanged existing renderer diagnostic."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from build_generalization_dataset import FONT_NAMES
from Levenshtein import editops
from PIL import Image, ImageDraw, ImageFont
from run_clean512_controlled import (
    CHECKPOINT,
    DATA,
    LABEL,
    REPORT,
    ROOT,
    describe,
    lexicon,
    write,
)
from train_generalization import RecognitionModel, batches, image_tensor

from app.benchmark import _find
from app.ctc import beam_decode, greedy_decode
from app.dataset import Sample
from app.diagnostics import buckets
from app.render_metadata import file_sha256


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def error_patterns(row):
    truth, prediction = row["truth"], row["prediction"]
    operations = editops(truth, prediction)
    result = []
    medicine = next(
        (name for name in lexicon().medicines if name.casefold() in truth.casefold()),
        None,
    )
    if medicine:
        start = truth.casefold().index(medicine.casefold())
        if any(
            op == "delete" and start < i < start + len(medicine) - 1
            for op, i, _ in operations
        ):
            result.append("medicine internal deletion")
    if any(
        op == "delete"
        and not truth[i].isspace()
        and (
            (i > 0 and truth[i] == truth[i - 1])
            or (i + 1 < len(truth) and truth[i] == truth[i + 1])
        )
        for op, i, _ in operations
    ):
        result.append("adjacent repeated glyph deletion")
    if any(
        op == "replace" and (truth[i].isdigit() or prediction[j].isdigit())
        for op, i, j in operations
    ):
        result.append("numeric substitution")
    if any(op == "delete" and truth[i] == "-" for op, i, _ in operations):
        result.append("hyphen loss")
    if "numeric_schedule" in row["buckets"] and _find(
        truth, lexicon().frequencies
    ) != _find(prediction, lexicon().frequencies):
        result.append("schedule mismatch/truncation")
    if _find(truth, lexicon().instructions) != _find(
        prediction, lexicon().instructions
    ):
        result.append("instruction mismatch/deletion")
    return result or ["other substitution/insertion/deletion"]


def table(headers, rows):
    return (
        "\n".join(
            [
                "|" + "|".join(headers) + "|",
                "|" + "|".join("---" for _ in headers) + "|",
            ]
            + [
                "|"
                + "|".join(str(v).replace("|", "\\|").replace("\n", " ") for v in row)
                + "|"
                for row in rows
            ]
        )
        + "\n"
    )


def renderer_diagnostic():
    source = ROOT / "benchmarks/ctc_audit/renderer_fit_samples.json"
    rows = load(source)
    directory = ROOT / "datasets/synthetic/renderer_diagnostic"
    fingerprints = {}
    # Validate the recorded matched-font protocol against every existing image.
    for row in rows:
        path = directory / (row["id"].removeprefix("renderer_") + ".png")
        if not path.is_file():
            raise FileNotFoundError(f"Historical diagnostic image unavailable: {path}")
        font_name = next(
            name for name in FONT_NAMES if Path(name).stem == row["renderer"]
        )
        font = ImageFont.truetype(
            str(Path("C:/Windows/Fonts") / font_name), row["font_size"]
        )
        expected = Image.new("L", (512, 64), 255)
        ImageDraw.Draw(expected).text((8, 15), row["truth"], fill=0, font=font)
        with Image.open(path) as actual:
            if not np.array_equal(np.asarray(expected), np.asarray(actual)):
                raise ValueError(
                    "Existing renderer image differs from historical protocol"
                )
        fingerprints[str(path.relative_to(ROOT))] = file_sha256(path)
        row["path"] = path
    meta = load(CHECKPOINT.with_suffix(".json"))
    model = RecognitionModel(
        name="controlled_renderer_diagnostic",
        image_shape=(64, 512, 1),
        lexical_shape=(1, meta["max_label_length"], len(meta["characters"]) + 2),
        seed=41,
    )
    model.recognition.load_weights(CHECKPOINT)
    result = {d: [] for d in ("greedy", "beam50")}
    for batch in batches(rows, 32):
        images = np.asarray(
            [
                image_tensor(
                    Sample(r["path"], r["truth"], r["renderer"], r["id"], "synthetic"),
                    None,
                    0,
                )
                for r in batch
            ]
        )
        logits = model.recognition(images, training=False)
        for decoder, predictions in (
            ("greedy", greedy_decode(logits, meta["characters"])),
            ("beam50", beam_decode(logits, meta["characters"], 50)),
        ):
            result[decoder].extend(
                {
                    "id": r["id"],
                    "renderer": r["renderer"],
                    "truth": r["truth"],
                    "prediction": p,
                    "final_font_size": r["font_size"],
                    "fitted": True,
                    "buckets": buckets(r["truth"], lexicon().medicines),
                }
                for r, p in zip(batch, predictions)
            )
    if any(file_sha256(ROOT / p) != h for p, h in fingerprints.items()):
        raise ValueError("Renderer diagnostics mutated")
    write(REPORT / "fixed_phrase_renderer_rows.json", result)
    write(
        REPORT / "fixed_phrase_renderer_metrics.json",
        {
            d: {
                renderer: describe([r for r in collection if r["renderer"] == renderer])
                for renderer in sorted({r["renderer"] for r in collection})
            }
            for d, collection in result.items()
        },
    )
    write(REPORT / "fixed_phrase_renderer_hashes.json", fingerprints)


def main():
    summary = load(REPORT / "training_summary.json")
    if not (REPORT / "fixed_phrase_renderer_metrics.json").exists():
        renderer_diagnostic()
    comparison = load(REPORT / "comparison_B_C.json")
    metadata = {
        r["sample_id"]: r
        for r in map(
            json.loads, (DATA / "render_metadata.jsonl").read_text().splitlines()
        )
    }
    historical = {}
    for decoder, file in (
        ("greedy", "alignment_samples.json"),
        ("beam50", "decoder_samples.json"),
    ):
        rows = load(ROOT / "benchmarks/ctc_audit" / file)
        enriched = [
            {
                **r,
                "fitted": False,
                "final_font_size": metadata[r["id"]]["original_requested_font_size"],
            }
            for r in rows
        ]
        historical[decoder] = {
            s: describe([r for r in enriched if r["split"] == s])
            for s in ("train", "validation", "test")
        }
    write(
        REPORT / "comparison_A_B_C.json",
        {"label": LABEL, "A": historical, **comparison},
    )
    lock = load(REPORT / "evaluation/decoder_lock.json")
    preferred = lock["preferred"]
    lines = [
        "# clean512_v2 controlled baseline\n",
        LABEL + "\n",
        "## Frozen protocol\n",
        "See [resolved_config.json](resolved_config.json) for complete settings, input/source/data hashes, vocabulary, environment and Git state. From scratch; unchanged Flor 64x512, output128; batch32; seed41; AdamW LR .001, betas .5/.99, decay .01, clipnorm5; unchanged dropout/light training-only augmentation; maximum20; stopping patience5/min_delta .002; best minimum validation greedy CER. No test-driven tuning.\n",
        "## Training and checkpoint\n",
        "Losses are arithmetic means of scalar batch losses, including the final partial batch; validation loss is diagnostic only and does not select checkpoints.\n",
        "Timing caution: measured elapsed time jumped from 4203.75 seconds at epoch13 to 17199.85 at epoch14. The original process remained alive (same PID); no optimizer/weights restart occurred. The cause of the wall-time gap was not established, so elapsed time is not presented as uninterrupted active CPU computation.\n",
        f"Best epoch {summary['best_epoch']}; best validation CER {summary['best_validation_cer']:.6f}; stopped epoch {summary['stopping_epoch']}; early stopping {summary['early_stopping_triggered']}. Checkpoint SHA-256 `{summary['checkpoint_sha256']}`.\n",
        table(
            [
                "Epoch",
                "Train loss",
                "Validation loss",
                "Validation CER",
                "LR",
                "Improved",
                "Patience counter",
            ],
            [
                [
                    h["epoch"],
                    round(h["train_loss"], 4),
                    round(h["validation_loss"], 4),
                    round(h["validation"]["cer"], 6),
                    h["learning_rate"],
                    h["checkpoint_improved"],
                    h["early_stopping_counter"],
                ]
                for h in summary["history"]
            ],
        ),
        "## Validation-only decoder lock\n",
        f"Greedy CER {lock['validation_cer']['greedy']:.6f}; beam50 CER {lock['validation_cer']['beam50']:.6f}. Selected **{preferred}**, with ties preferring greedy. Selection was written before test inference. This is validation-preferred under the renderer-conditioned validation split, not universally optimal.\n",
        "## Three-condition metrics\n",
        "A: historical weights + historical images. B: historical weights + clean images. C: controlled new weights + clean images.\n",
    ]
    conditions = {"A": historical, "B": comparison["B"], "C": comparison["C"]}
    lines.append(
        table(
            [
                "Condition",
                "Decoder",
                "Split",
                "N",
                "CER",
                "WER",
                "Exact",
                "WS CER",
                "WS WER",
                "WS exact",
            ],
            [
                [
                    name,
                    d,
                    s,
                    m["samples"],
                    round(m["cer"], 6),
                    round(m["wer"], 6),
                    round(m["exact_line_accuracy"], 4),
                    round(m["whitespace_normalized"]["cer"], 6),
                    round(m["whitespace_normalized"]["wer"], 6),
                    round(m["whitespace_normalized"]["exact_line_accuracy"], 4),
                ]
                for name, c in conditions.items()
                for d, v in c.items()
                for s, m in v.items()
            ],
        )
    )
    lines.append(
        table(
            [
                "Condition",
                "Decoder",
                "Split",
                "Medicine",
                "Dose",
                "Frequency",
                "1-1-1 N",
                "1-1-1 accuracy",
            ],
            [
                [
                    name,
                    d,
                    s,
                    m["fields"]["medicines"]["overall_accuracy"],
                    m["fields"]["doses"]["overall_accuracy"],
                    m["fields"]["frequencies"]["overall_accuracy"],
                    m["special_exact"]["1-1-1"]["N"],
                    m["special_exact"]["1-1-1"]["accuracy"],
                ]
                for name, condition in conditions.items()
                for d, splits in condition.items()
                for s, m in splits.items()
            ],
        )
    )
    lines.append(
        "Full machine-readable tables: [comparison_A_B_C.json](comparison_A_B_C.json).\n"
    )
    for name in ("B", "C"):
        lines.append(f"## {name}: bucket, field and special diagnostics\n")
        for d, v in conditions[name].items():
            for s, m in v.items():
                lines.append(f"### {d} / {s}\n")
                lines.append(
                    table(
                        ["Bucket", "N", "CER", "WER"],
                        [
                            [b, x["samples"], round(x["cer"], 6), round(x["wer"], 6)]
                            for b, x in m["buckets"].items()
                        ],
                    )
                )
                lines.append(
                    table(
                        ["Field", "Present N", "Absent N", "Overall", "Present only"],
                        [
                            [
                                f,
                                x["present_count"],
                                x["absent_count"],
                                x["overall_accuracy"],
                                x["present_accuracy"],
                            ]
                            for f, x in m["fields"].items()
                        ],
                    )
                )
                lines.append(
                    table(
                        ["Exact field", "N", "Accuracy"],
                        [
                            [f, x["N"], x["accuracy"]]
                            for f, x in m["special_exact"].items()
                        ],
                    )
                )
                lines.append(
                    "Non-whitespace adjacent repeat: "
                    + str(m["non_whitespace_adjacent_repeat"])
                    + "\n"
                )
    lines.append("## Primary fitted/renderer/font subgroups\n")
    for s in ("validation", "test"):
        m = conditions["C"][preferred][s]
        for key in ("fitted_subgroups", "renderers", "font_bands"):
            lines.append(f"### {s} / {key}\n")
            lines.append(
                table(
                    ["Group", "N", "CER", "WER", "Exact"],
                    [
                        [g, x["samples"], x["cer"], x["wer"], x["exact_line_accuracy"]]
                        for g, x in m[key].items()
                    ],
                )
            )
    lines.append(
        "Test fitted N=9 is very small. All fitted/font subgroups are observational, not causal comparisons. Validation renderer is Segoe Print only; test renderers are Times and Trebuchet.\n"
    )
    lines.append("## Existing matched 100-phrase × 10-renderer diagnostics\n")
    diag = load(REPORT / "fixed_phrase_renderer_metrics.json")
    lines.append(
        table(
            [
                "Decoder",
                "Renderer",
                "N",
                "CER",
                "WER",
                "Exact",
                "Medicine",
                "Dose",
                "Frequency",
                "Duration present",
            ],
            [
                [
                    d,
                    r,
                    m["samples"],
                    m["cer"],
                    m["wer"],
                    m["exact_line_accuracy"],
                    m["fields"]["medicines"]["overall_accuracy"],
                    m["fields"]["doses"]["overall_accuracy"],
                    m["fields"]["frequencies"]["overall_accuracy"],
                    m["fields"]["durations"]["present_accuracy"],
                ]
                for d, v in diag.items()
                for r, m in v.items()
            ],
        )
    )
    lines.append(
        "Existing images were reconstructed in memory against the historical matched font-size/position protocol and hashes checked before/after; no files regenerated. Diagnostic results did not select checkpoint or decoder.\n"
    )
    lines.append("## 25 worst locked-decoder test errors\n")
    worst = load(REPORT / "evaluation/worst25_validation_selected_test_errors.json")
    for row in worst:
        row["descriptive_patterns"] = error_patterns(row)
    write(REPORT / "worst25_descriptive_error_analysis.json", worst)
    lines.append(
        table(
            [
                "ID",
                "Renderer",
                "Original/final size",
                "Fitted",
                "Truth",
                "Prediction",
                "CER",
                "Length/repeats/required",
                "Buckets",
                "Descriptive patterns",
            ],
            [
                [
                    r["id"],
                    r["renderer"],
                    f"{r['original_requested_font_size']}/{r['final_font_size']}",
                    r["fitted"],
                    r["truth"],
                    r["prediction"],
                    round(r["cer"], 6),
                    f"{r['target_length']}/{r['adjacent_repeat_count']}/{r['minimum_ctc_steps']}",
                    ", ".join(r["buckets"]),
                    ", ".join(r["descriptive_patterns"]),
                ]
                for r in worst
            ],
        )
    )
    lines.extend(
        [
            "## Immutability\n",
            "See [immutability.json](immutability.json). Historical checkpoint before/after must be `386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef`; every historical and clean corpus file hash matches the frozen snapshot. New checkpoint and configuration hashes are recorded separately.\n",
            "## Interpretation and limitations\n",
            "A→B holds weights fixed and measures the immediate corrected-render corpus effect, including font fitting/scale changes. B→C holds clean evaluation images fixed, but changes initialization, optimization trajectory and training protocol; it cannot isolate only training with clipping repair. A→C is the combined system difference, not solely clipping repair.\n",
            "clean512_v2 fixes demonstrated clipping; clipping is not proven to have been the only OCR error source. Historical training recipe is incomplete. The new run is a newly specified controlled baseline. Validation contains only Segoe Print, so validation selection is renderer-conditioned and does not establish renderer-independent generalization. Test performance did not select checkpoint or decoder. No clinical deployment readiness is established. No width1024, architecture/downsampling changes, lexicons, dictionary/LM correction, integration, page OCR, collection, commit or push occurred.\n",
            "Recommended next experiment: review locked-decoder repeat/schedule/medicine errors and renderer-matched results, then propose a separately authorized balanced renderer validation protocol. Do not tune this test set or launch another run automatically.\n",
            "Checks and final Git status are recorded in CHECKS.md after execution.\n",
        ]
    )
    with (REPORT / "REPORT.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


if __name__ == "__main__":
    main()
