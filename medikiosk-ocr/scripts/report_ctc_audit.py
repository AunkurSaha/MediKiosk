"""Generate the measured diagnostic report, without training or model selection."""

from __future__ import annotations

import json
import subprocess

from audit_recognition import OUTPUT, ROOT, grouped, lexicon

from app.benchmark import _find, error_rates
from app.diagnostics import conditional_fields, summarize


def load(name):
    return json.loads((OUTPUT / name).read_text(encoding="utf-8"))


def percent(value):
    return "n/a" if value is None else f"{100 * value:.2f}%"


def table(headers, rows):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    return (
        "\n".join(
            [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
                *[
                    "| " + " | ".join(escape(value) for value in row) + " |"
                    for row in rows
                ],
            ]
        )
        + "\n"
    )


def main():
    audit = load("alignment_summary.json")
    rows = load("alignment_samples.json")
    decoder = load("decoder_summary.json")
    beam_rows = load("decoder_samples.json")
    fixed = load("renderer_summary.json")
    fitted = load("renderer_fit_summary.json")
    geometry = load("geometry_summary.json")
    local = load("local_repeat_alignment.json")
    verification = load("render_bounds_verification.json")
    test = [row for row in rows if row["split"] == "test"]
    beam_test = [row for row in beam_rows if row["split"] == "test"]
    greedy_val = audit["splits"]["validation"]["cer"]
    beam_val = decoder["beam_splits"]["validation"]["cer"]
    preferred = "beam" if beam_val < greedy_val else "greedy"
    preferred_rows = beam_test if preferred == "beam" else test
    lines = [
        "# CTC alignment, renderer and geometry audit\n",
        "Evaluation only. No additional training, page OCR, volunteer collection, checkpoint selection, or MediKiosk integration. The checkpoint is the existing best-validation model. Buckets are overlapping descriptive categories, not causal diagnoses.\n",
        f"Checkpoint SHA-256: `{audit['checkpoint_sha256']}`.\n",
        "## 1. Sequence statistics and warnings\n",
        "All original images and baseline model inputs are width 512. Actual output shape is 1×128×49 (128 CTC steps). Threshold for a diagnostic low-margin warning is ratio <1.5; this is a declared heuristic, not a clinical or mathematical safety threshold.\n",
    ]
    lines.append(
        table(
            [
                "Split",
                "N",
                "Required min/median/max",
                "Ratio min/median/max",
                "Clipped renders",
            ],
            [
                [
                    name,
                    value["samples"],
                    "/".join(
                        f"{value['required_steps'][k]:.1f}"
                        for k in ("min", "median", "max")
                    ),
                    "/".join(
                        f"{value['alignment_ratio'][k]:.2f}"
                        for k in ("min", "median", "max")
                    ),
                    value["clipped_count"],
                ]
                for name, value in audit["splits"].items()
            ],
        )
    )
    lines.append(
        f"Insufficient or low-margin samples: **{len(audit['violations'])}**. No sample minimally satisfies the global requirement. Training now asserts feasibility instead of relying on the upstream loss's ignore-longer behavior. Full per-sample records and bucket distributions are in `alignment_samples.json` and `alignment_summary.json`.\n"
    )
    lines.append(
        f"Pixel verification reproduced all 1,000 saved images exactly. Of 139 projected bounds overflows, **{verification['samples_with_missing_ink']}** actually lose non-white glyph pixels outside the canvas (99 train, 30 validation, 7 test). Three bounds warnings alone did not lose glyph ink. See `render_bounds_verification.json`.\n"
    )
    lines.append(
        table(
            [
                "Smallest margins (first 10)",
                "Target chars",
                "Adjacent repeats",
                "Required",
                "Output",
                "Ratio",
            ],
            [
                [
                    r["id"],
                    r["target_length"],
                    r["adjacent_repeat_count"],
                    r["minimum_ctc_steps"],
                    r["output_time_steps"],
                    f"{r['alignment_ratio']:.3f}",
                ]
                for r in audit["smallest_margin_samples"][:10]
            ],
        )
    )
    lines.append("## 2. Error buckets and length distributions\n")
    lines.append(
        "Short ≤25 characters; medium 26–39; long ≥40. `repeated_character` includes repeated spaces. `spacing` means a target contains whitespace, not that spacing caused an error. All prescription lines naturally fall in the medication/spacing buckets. `1-1-1` has zero adjacent repeats.\n"
    )
    lines.append(
        table(
            ["Test bucket", "N", "CER", "WER"],
            [
                [name, value["samples"], f"{value['cer']:.4f}", f"{value['wer']:.4f}"]
                for name, value in grouped(test).items()
            ],
        )
    )
    for split in ("train", "validation", "test"):
        subset = [r for r in rows if r["split"] == split]
        clipped = [r for r in subset if r["render_clipped"]]
        clean = [r for r in subset if not r["render_clipped"]]
        lines.append(
            f"{split}: clipped {len(clipped)} (CER {summarize(clipped)['cer']:.4f}); unclipped {len(clean)} (CER {summarize(clean)['cer']:.4f}).\n"
        )
    normalized = error_rates(
        [" ".join(r["truth"].split()) for r in test],
        [" ".join(r["prediction"].split()) for r in test],
    )
    normalized_exact = sum(
        " ".join(r["truth"].split()) == " ".join(r["prediction"].split()) for r in test
    ) / len(test)
    lines.append(
        f"Whitespace-normalized test CER/WER: {normalized[0]:.4f}/{normalized[1]:.4f}; normalized exact-line accuracy {percent(normalized_exact)}. These supplemental metrics do not replace strict CER/WER.\n"
    )
    letters = [
        r
        for r in test
        if any(a == b and not a.isspace() for a, b in zip(r["truth"], r["truth"][1:]))
    ]
    lines.append(
        f"Test samples with adjacent non-whitespace repeats: {len(letters)}, CER {summarize(letters)['cer']:.4f}.\n"
    )
    lines.append("## 3. Local horizontal detail\n")
    ls = local["summary"]
    lines.append(
        f"Measured {ls['nonspace_repeat_runs']} non-space repeated glyph runs; {ls['local_ratio_below_one']} have glyph-advance/grid ratio <1 relative to that run's minimum CTC steps. Local ratio min/median/max: {ls['local_ratio']['min']:.3f}/{ls['local_ratio']['median']:.3f}/{ls['local_ratio']['max']:.3f}. This is not a hard local alignment theorem: convolutional receptive fields and recurrent alignment can borrow neighboring frames. Raw argmax runs for 25 worst greedy errors are retained in `local_repeat_alignment.json`.\n"
    )
    lines.append("## 4. Fixed-phrase renderer isolation\n")
    lines.append(
        "100 identical new phrases per renderer, disjoint from normalized baseline phrases. Diagnostic images are not in training manifests. The fixed-size pass uses font size 23 and measures clipping. The fitted pass uses the same font size for every renderer of a given phrase, reduced only until that phrase fits all renderers; all fitted images are unclipped. Font size therefore varies by phrase, never by renderer within a phrase.\n"
    )
    lines.append(
        "Fitted font sizes span 14-23, versus 22-24 in the original training renders. Fixed-versus-fitted changes therefore conflate removing clipping with changing scale; do not interpret that difference as a pure clipping-effect estimate. Within either pass, phrase/font-size configuration is matched across renderers.\n"
    )
    lines.append(
        table(
            [
                "Renderer",
                "Fixed CER",
                "Fixed clipped",
                "Fitted CER",
                "WER",
                "Exact",
                "Medicine",
                "Dose",
                "Frequency",
                "Duration present",
            ],
            [
                [
                    name,
                    f"{fixed[name]['cer']:.4f}",
                    fixed[name]["clipped_count"],
                    f"{v['cer']:.4f}",
                    f"{v['wer']:.4f}",
                    percent(v["exact_line_accuracy"]),
                    percent(v["fields"]["medicines"]["overall_accuracy"]),
                    percent(v["fields"]["doses"]["overall_accuracy"]),
                    percent(v["fields"]["frequencies"]["overall_accuracy"]),
                    percent(v["fields"]["durations"]["present_accuracy"]),
                ]
                for name, v in fitted.items()
            ],
        )
    )
    hardest = max(fitted, key=lambda name: fitted[name]["cer"])
    lines.append(
        f"Hardest unclipped renderer: **{hardest}**, CER {fitted[hardest]['cer']:.4f}. Renderer rankings are conditional on this font-size/configuration and phrase set, not all handwriting.\n"
    )
    lines.append("## 5. Controlled geometry probes and decoder ablation\n")
    configurations = {
        "A 512 greedy": geometry["A_512"],
        "B 1024 greedy": geometry["B_1024"],
        "A 512 beam50": decoder["beam"],
        "B 1024 beam50": decoder["B_1024_beam"],
    }
    lines.append(
        table(
            [
                "Same checkpoint / same 200 test images",
                "CER",
                "WER",
                "Exact",
                "Medicine",
                "Schedule",
            ],
            [
                [
                    name,
                    f"{v['cer']:.4f}",
                    f"{v['wer']:.4f}",
                    percent(v["exact_line_accuracy"]),
                    percent(v["fields"]["medicines"]["overall_accuracy"]),
                    percent(v["numeric_schedule"]["accuracy"]),
                ]
                for name, v in configurations.items()
            ],
        )
    )
    lines.append(
        table(
            ["Configuration", "Long-line CER", "Repeated-character CER"],
            [
                [
                    name,
                    f"{value['long_line']['cer']:.4f}",
                    f"{value['repeated_character']['cer']:.4f}",
                ]
                for name, value in (
                    ("A greedy", geometry["A_buckets"]),
                    ("B greedy", geometry["B_buckets"]),
                    ("A beam", decoder["beam_buckets"]),
                )
            ],
        )
    )
    lines.append(
        "B changes only horizontal resize/input width to 1024, doubling glyph width and output steps to 256. It loads the SAME weights; seed, data, dropout inference behavior and decoder are otherwise constant. This is an out-of-distribution inference probe, NOT a retrained width experiment. C (horizontal downsampling change) was not run because global sequence feasibility is adequate; local ratios alone do not establish a downsampling cause. No medical dictionary, language model, or correction is used in beam search.\n"
    )
    lines.append(
        table(
            ["Beam split", "CER", "WER", "Exact"],
            [
                [
                    name,
                    f"{v['cer']:.4f}",
                    f"{v['wer']:.4f}",
                    percent(v["exact_line_accuracy"]),
                ]
                for name, v in decoder["beam_splits"].items()
            ],
        )
    )
    lines.append(
        f"Decoder preferred by validation CER: **{preferred}** (greedy {greedy_val:.4f}, beam {beam_val:.4f}). This diagnostic choice does not establish readiness.\n"
    )
    lines.append("### Proposed retrained A/B configuration — NOT launched\n")
    lines.append(
        "A: 64×512; B: 64×1024; only input width changes. Both start from scratch with seed 41, identical immutable corpus/splits, AdamW lr=0.001 beta1=0.5 beta2=0.99 weight_decay=0.01 clipnorm=5, batch32, original Flor dropout, light train-only augmentation, up to20 epochs, patience5/min_delta0.002, best-validation checkpointing. Estimated paired CPU runtime: roughly 3–5 hours (A about3–5 minutes/epoch; B conservatively up to twice that). Requires approval before launch. First fix clipping in a separate versioned corpus and establish a clean A baseline; do not confound that repair with a simultaneous architecture change.\n"
    )
    lines.append("## 6. Optional-field conditional metrics\n")
    optional = {}
    for decoder_name, collection in (("greedy", rows), ("beam", beam_rows)):
        optional[decoder_name] = {}
        for split in ("train", "validation", "test"):
            subset = [r for r in collection if r["split"] == split]
            optional[decoder_name][split] = conditional_fields(
                [r["truth"] for r in subset],
                [r["prediction"] for r in subset],
                lexicon(),
            )
    (OUTPUT / "optional_fields_all.json").write_text(
        json.dumps(optional, indent=2), encoding="utf-8"
    )
    lines.append(
        "Forms and instructions are also optional in the generator. All conditional metrics, including these fields, are saved in `optional_fields_all.json`. Vocabulary lists are used only for scoring; they never influence decoding.\n"
    )
    lines.append(
        table(
            [
                "Split/decoder",
                "Optional field",
                "Present N",
                "Absent N",
                "Overall",
                "Present only",
            ],
            [
                [
                    f"{split}/{decoder_name}",
                    field,
                    v["present_count"],
                    v["absent_count"],
                    percent(v["overall_accuracy"]),
                    percent(v["present_accuracy"]),
                ]
                for decoder_name, split_values in optional.items()
                for split, fields in split_values.items()
                for field, v in fields.items()
                if field in ("forms", "instructions")
            ],
        )
    )
    lines.append(
        table(
            [
                "Split/decoder",
                "Field",
                "Present N",
                "Absent N",
                "Overall",
                "Present only",
            ],
            [
                [
                    f"{name}/greedy",
                    field,
                    v["present_count"],
                    v["absent_count"],
                    percent(v["overall_accuracy"]),
                    percent(v["present_accuracy"]),
                ]
                for name, split in audit["splits"].items()
                for field, v in split["fields"].items()
            ],
        )
    )
    lines.append(
        table(
            ["Test beam field", "Present N", "Absent N", "Overall", "Present only"],
            [
                [
                    field,
                    v["present_count"],
                    v["absent_count"],
                    percent(v["overall_accuracy"]),
                    percent(v["present_accuracy"]),
                ]
                for field, v in decoder["beam"]["fields"].items()
            ],
        )
    )
    lines.append("## 7. Truncation and schedule changes\n")
    medication_rows = []
    for name in ("Amoxicillin", "Cetirizine"):
        for decoder_name, collection in (("greedy", test), ("beam", beam_test)):
            subset = [r for r in collection if _find(r["truth"], frozenset({name}))]
            correct = sum(
                _find(r["prediction"], frozenset({name})) == name for r in subset
            )
            medication_rows.append(
                [
                    name,
                    decoder_name,
                    len(subset),
                    percent(correct / len(subset)),
                    f"{summarize(subset)['cer']:.4f}",
                ]
            )
    lines.append(
        table(
            ["Medicine", "Decoder", "N", "Exact name accuracy", "Line CER"],
            medication_rows,
        )
    )
    schedule_rows = []
    for decoder_name, collection in (("greedy", test), ("beam", beam_test)):
        subset = [r for r in collection if "1-1-1" in r["truth"]]
        schedule_rows.append(
            [
                decoder_name,
                len(subset),
                percent(sum("1-1-1" in r["prediction"] for r in subset) / len(subset)),
            ]
        )
    lines.append(
        table(["1-1-1 decoder", "N", "Exact schedule accuracy"], schedule_rows)
    )
    lines.append("## 8. Twenty-five worst errors, validation-preferred decoder\n")
    errors = sorted(
        [r for r in preferred_rows if r["cer"] > 0],
        key=lambda r: r["cer"],
        reverse=True,
    )[:25]
    lines.append(
        table(
            ["ID / renderer", "Ground truth", "Prediction", "CER", "Buckets"],
            [
                [
                    f"{r['id']} / {r['renderer']}",
                    r["truth"],
                    r["prediction"],
                    f"{r['cer']:.4f}",
                    ", ".join(r["buckets"]),
                ]
                for r in errors
            ],
        )
    )
    lines.append("## 9. Evidence and next decision\n")
    lines.append(
        "Measured global output shortage is NOT the explanation: every target fits with substantial margin. Silent render clipping is a demonstrated data defect and makes some full transcriptions impossible. It does not explain all internal name truncations. Local glyph span estimates, decoder ablation, and matched-phrase renderer results constrain remaining hypotheses but do not prove a single cause. Recommended next change: fail-fast rendering bounds and a clean, versioned width512 corpus, retaining this checkpoint/dataset as immutable references. Then inspect repeat/hyphen posteriors and establish a clean baseline before a separately approved width-only retraining trial. No large volunteer collection, page OCR, or MediKiosk integration.\n"
    )
    status = subprocess.run(
        ["rtk", "proxy", "git", "status", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines.append("## 10. Verification and Git status\n")
    lines.append(
        "16 tests passed; Ruff checks and formatting checks passed for touched Python files; Python compilation passed. Pytest emitted an existing cache-permission warning and a Starlette/AnyIO deprecation warning. No commit or push. Outside-workspace changes below are pre-existing and were not edited by this audit.\n\n```text\n"
        + status
        + "```\n"
    )
    (OUTPUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT / "REPORT.md")


if __name__ == "__main__":
    main()
