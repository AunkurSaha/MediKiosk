"""Summarize captured train/validation emissions without training or test inference."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "benchmarks/clean512_v2_ctc_schedule_audit"

from app.render_metadata import file_sha256


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write(name, value):
    destination = OUT / name
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(
        json.dumps(value, indent=2, allow_nan=False), encoding="utf-8"
    )


def stats(values):
    return (
        {
            "n": len(values),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "p10": float(np.percentile(values, 10)),
        }
        if values
        else {"n": 0}
    )


def table(headers, rows):
    return (
        "|"
        + "|".join(headers)
        + "|\n|"
        + "|".join(["---"] * len(headers))
        + "|\n"
        + "\n".join(
            "|"
            + "|".join(str(v).replace("|", "/").replace("\n", " ") for v in row)
            + "|"
            for row in rows
        )
        + "\n"
    )


def main():
    tokens = read("token_details.json")
    config = read("audit_config.json")
    index = read("sample_index.json")
    paths = read("decoder_path_comparison.json")
    chars = read("character_statistics.json")
    augmentation = read("augmentation_audit.json")
    metrics = read("line_metrics.json")
    blank = config["blank_index"]
    repeat_rows = []
    emission_groups = defaultdict(list)
    for token in tokens:
        raw = np.load(OUT / "raw" / f"{token['sample_id']}.npz")
        p = raw["probabilities"]
        for char in token["characters"]:
            if char["character"].isdigit() or char["character"] == "-":
                window = np.arange(max(0, char["start"] - 3), min(128, char["end"] + 4))
                localpeak = int(window[np.argmax(p[window, char["label"]])])
                row = {
                    "sample_id": token["sample_id"],
                    "split": token["split"],
                    "token": token["token"],
                    "kind": token["kind"],
                    "beam_correct": token["beam_correct"],
                    "character": char["character"],
                    "role": char["role"],
                    "target_index": char["target_index"],
                    "assigned_peak": char["peak_probability"],
                    "local_window_peak": float(p[localpeak, char["label"]]),
                    "local_peak_frame": localpeak,
                    "local_peak_argmax": int(p[localpeak].argmax()),
                    "local_peak_blank": float(p[localpeak, blank]),
                    "deleted_in_edit_projection": char["target_index"]
                    in token["projected"]["deleted_target_indices"],
                    "frame_x_proxy": 4 * char["peak_frame"],
                    "warning": "Target-constrained frame window; weak support is not globally absent character evidence; x proxy is not receptive-field registration",
                }
                key = f"{token['kind']}|{token['split']}|{'correct' if token['beam_correct'] else 'incorrect'}|{char['role']}"
                emission_groups[key].append(row)
        if token["kind"] == "schedule":
            for a, b in [(0, 2), (2, 4), (0, 4)]:
                first, last = token["characters"][a], token["characters"][b]
                if first["character"] != last["character"]:
                    continue
                gap = np.arange(first["end"] + 1, last["start"])
                repeat_rows.append(
                    {
                        "sample_id": token["sample_id"],
                        "split": token["split"],
                        "schedule": token["token"],
                        "beam_correct": token["beam_correct"],
                        "first_role": first["role"],
                        "later_role": last["role"],
                        "adjacent_ctc_repeat": False,
                        "intervening_target_symbols": b - a - 1,
                        "peak_frame_distance": last["peak_frame"] - first["peak_frame"],
                        "blank_dominant_between": int(
                            sum(p[gap].argmax(axis=1) == blank)
                        )
                        if len(gap)
                        else 0,
                        "peak_blank_between": float(p[gap, blank].max())
                        if len(gap)
                        else None,
                        "first_peak": first["peak_probability"],
                        "later_peak": last["peak_probability"],
                    }
                )
    emission_summary = {
        k: {
            "n": len(v),
            "assigned_peak": stats([r["assigned_peak"] for r in v]),
            "local_peak": stats([r["local_window_peak"] for r in v]),
            "local_non_argmax_rate": sum(
                r["local_peak_argmax"] != config["vocabulary"][r["character"]]
                for r in v
            )
            / len(v),
            "local_weak_below_0_1": sum(r["local_window_peak"] < 0.1 for r in v)
            / len(v),
            "assigned_weak_below_0_1": sum(r["assigned_peak"] < 0.1 for r in v)
            / len(v),
        }
        for k, v in emission_groups.items()
    }
    write(
        "local_emission_analysis.json",
        {
            "groups": emission_summary,
            "rows": [r for v in emission_groups.values() for r in v],
        },
    )
    write("repeated_symbol_analysis.json", repeat_rows)
    write(
        "analysis_freeze.json",
        {
            "report_script_sha256": file_sha256(Path(__file__)),
            "audit_config_sha256": file_sha256(OUT / "audit_config.json"),
            "scope": "train/validation only; no test confirmation",
            "cutoffs": {"weak": 0.1, "strong": 0.5, "local_window_margin_frames": 3},
            "hypotheses": config["hypotheses"],
        },
    )
    sections = [
        "# Frozen clean512_v2 numeric CTC diagnostic audit\n",
        "Evaluation only, using **train + validation**. No training, fine-tuning, frozen-artifact modifications, decoder tuning, test inference, integration, commit or push. This is descriptive evidence, not clinical readiness or a proven training-regression cause.\n",
        "## Verification and protocol\n",
        f"Checkpoint SHA-256 `{config['checkpoint_sha256']}` verified before and after inference. All 1,005 clean-corpus files match the frozen snapshot; corpus/checkpoint/sidecar hashes remain unchanged. Every in-memory model weight is byte-identical before/after inference (including batch-normalization state). Input64×512×1; logits128×49; padding0; blank48; labels1–47. Softmax is across classes per frame. Both production greedy and locked ordinary beam50 are unchanged; diagnostic top5 uses the same width50 and top1 equality is asserted.\n",
        "**Vocabulary limitation:** digits8 and9 are absent from the frozen vocabulary. Their trace probabilities/IDs are null, not remapped. No conclusions about recognizing them are possible.\n",
        table(
            ["Symbol", "ID"], [[repr(c), i] for c, i in config["vocabulary"].items()]
        ),
        "Deterministic full-target Viterbi alignment and exact forward target-sequence probability are diagnostics only. They never alter predictions. Assigned peaks are target-constrained, not calibrated character confidence; a forced path can assign a very improbable frame. Probability sums across assigned frames are not sequence probabilities. Full-line Levenshtein projection can ambiguously allocate identical symbols/spaces at token boundaries. Tables retain this caveat.\n",
        "## Train and validation findings\n",
        table(
            ["Split", "N", "CER", "WER", "Exact line"],
            [
                [
                    s,
                    m["samples"],
                    round(m["cer"], 6),
                    round(m["wer"], 6),
                    round(m["exact_line_accuracy"], 6),
                ]
                for s, m in metrics.items()
            ],
        ),
        f"All800 train/validation lines were inferred for character-conditioned statistics and saved as raw logits + full normalized posteriors. Detailed cohort: {len(index)} unique lines; schedules {sum(t['kind'] == 'schedule' for t in tokens)}, durations {sum(t['kind'] == 'duration' for t in tokens)}. Every cohort row retains renderer/font/fitting/bounds/target/decoder/alignment lengths.\n",
    ]
    for kind in ("schedule", "duration"):
        matrix = read(f"{kind}_error_matrix.json")
        sections.append(f"## {kind.title()} error matrix\n")
        sections.append(
            table(
                [
                    "Split",
                    "N",
                    "Beam correct",
                    "Greedy correct",
                    "Digit deleted",
                    "Digit substituted",
                    "Hyphen deleted",
                    "Prefix deleted",
                    "Suffix deleted",
                    "Multiple deletions",
                ],
                [
                    [
                        s,
                        m["n"],
                        m["beam_correct"],
                        m["greedy_correct"],
                        m["edit_counts"].get("digit_deletion", 0),
                        m["edit_counts"].get("digit_substitution", 0),
                        m["edit_counts"].get("hyphen_deletion", 0),
                        m["prefix_deleted"],
                        m["suffix_deleted"],
                        m["multi_character_deletion"],
                    ]
                    for s, m in matrix.items()
                ],
            )
        )
        sections.append(
            table(
                ["Split", "Target", "Projected beam token", "Count"],
                [
                    [s, r["truth"], repr(r["prediction"]), r["n"]]
                    for s, m in matrix.items()
                    for r in m["transitions"]
                ],
            )
        )
    sections.extend(
        [
            "## Forced alignment, digit/hyphen posteriors and position\n",
            table(
                [
                    "Group",
                    "N",
                    "Assigned peak mean",
                    "Median",
                    "Local peak mean",
                    "Assigned weak<.1",
                    "Local weak<.1",
                    "Local nonargmax",
                ],
                [
                    [
                        k,
                        m["n"],
                        round(m["assigned_peak"]["mean"], 4),
                        round(m["assigned_peak"]["median"], 4),
                        round(m["local_peak"]["mean"], 4),
                        round(m["assigned_weak_below_0_1"], 3),
                        round(m["local_weak_below_0_1"], 3),
                        round(m["local_non_argmax_rate"], 3),
                    ]
                    for k, m in sorted(emission_summary.items())
                ],
            ),
            "The ±3-frame local window is a declared sensitivity check around forced assignment; it can include another occurrence of the same symbol. Nonargmax measures direct competition, not decoder culpability. Each duration character includes simultaneous digit/hyphen/space probabilities at its assigned peak, neighboring blanks, word emissions and full target-sequence log probability in token_details.json. Full traces/raw arrays allow independent inspection.\n",
            "## Repeated symbols and blank separation\n",
            "The three digits of1-1-1 are separated by hyphens: **none is an adjacent identical CTC repeat**. Likewise the zeros in1-0-0 are not adjacent CTC repeats. No blank is mathematically required between a digit and hyphen or hyphen and digit. Actual adjacent identical labels elsewhere in a line do require a separating blank and are handled by the alignment algorithm. A zero-frame blank gap inside a schedule is not automatically an error.\n",
        ]
    )
    repeated = defaultdict(list)
    for r in repeat_rows:
        repeated[
            f"{r['schedule']}|{'correct' if r['beam_correct'] else 'incorrect'}|{r['first_role']}→{r['later_role']}"
        ].append(r)
    sections.append(
        table(
            [
                "Pattern/group",
                "Pairs",
                "Mean first peak",
                "Mean later peak",
                "Mean distance",
                "Mean blank-dominant frames",
                "Mean peak blank",
            ],
            [
                [
                    k,
                    len(v),
                    round(np.mean([r["first_peak"] for r in v]), 4),
                    round(np.mean([r["later_peak"] for r in v]), 4),
                    round(np.mean([r["peak_frame_distance"] for r in v]), 2),
                    round(np.mean([r["blank_dominant_between"] for r in v]), 2),
                    round(np.mean([r["peak_blank_between"] or 0 for r in v]), 4),
                ]
                for k, v in sorted(repeated.items())
            ],
        )
    )
    sections.append("## Character-conditioned statistics\n")
    sections.append(
        table(
            [
                "Character/context/line",
                "N",
                "Peak mean",
                "Median",
                "p10",
                "p25",
                "Mean span",
                "Weak<.1",
                "Nonargmax",
            ],
            [
                [
                    repr(k),
                    v["occurrences"],
                    round(v["peak"]["mean"], 4),
                    round(v["peak"]["median"], 4),
                    round(v["peak"]["p10"], 4),
                    round(v["peak"]["p25"], 4),
                    round(v["span"]["mean"], 3),
                    round(v["weak_below_0_1"], 3),
                    round(v["non_argmax_rate"], 3),
                ]
                for k, v in sorted(chars.items())
                if k[0] in "01357-aeor"
            ],
        )
    )
    sections.append(
        "All target occurrences and all characters are retained in character_statistics.json. Non-schedule/non-duration numerals are dose-context under this fixed prescription grammar, not a general clinical parser. Correct/incorrect-line strata refer to exact beam50 full-line equality, not token correctness.\n"
    )
    sections.append("## Greedy versus beam50 paths\n")
    sections.append(
        table(
            [
                "Split",
                "Cohort N",
                "Exact target in top5",
                "Correct schedule appears in top5",
                "Median target minus top1 logP",
            ],
            [
                [
                    s,
                    len(v),
                    sum(r["exact_target_rank_top5"] is not None for r in v),
                    sum(
                        any(ranks for ranks in r["full_schedule_ranks_top5"].values())
                        for r in v
                    ),
                    round(
                        float(
                            np.median(
                                [r["target_minus_beam_log_probability"] for r in v]
                            )
                        ),
                        3,
                    ),
                ]
                for s in ("train", "validation")
                if (v := [r for r in paths if r["split"] == s])
            ],
        )
    )
    sections.append(
        "Exact target absent from top5 means absent only from the returned hypotheses, not from all explored beam states. Beam scores are pruned sequence log probabilities; the exact forward target score includes all valid target paths, while Viterbi is only the single best constrained path. These are not interchangeable. Class0 is filtered by the existing decoder; no padding-filter behavior was changed. Raw argmax paths, collapsed output and top5 scores are retained.\n"
    )
    geometry = read("geometry_correlations.json")
    sections.append("## Observational geometry correlations\n")
    sections.append(
        table(
            [
                "Group",
                "N",
                "Mean font size",
                "Mean line length",
                "Mean text width",
                "Mean token x-start",
                "Mean token x-end",
            ],
            [
                [
                    k,
                    v["n"],
                    round(v["font_size"]["mean"], 2),
                    round(v["target_length"]["mean"], 2),
                    round(v["text_width"]["mean"], 2),
                    round(v["x_start"]["mean"], 2),
                    round(v["x_end"]["mean"], 2),
                ]
                for k, v in sorted(geometry.items())
            ],
        )
    )
    sections.append(
        "Renderer, phrase, length, font fitting and token location are confounded. Validation is Segoe Print only. These summaries cannot identify geometry or renderer as a causal mechanism. Prefix advances approximate glyph location; frame×4 is only a coordinate proxy, not registered receptive-field alignment. No image was regenerated.\n"
    )
    sections.append("## Augmentation implementation audit\n")
    sections.append(
        "Current light augmentation applies perspective then expanded-canvas rotation, optional Gaussian blur, resizing to64×512, then brightness. Noise/JPEG, explicit scale/shift/shear/elastic transforms are disabled. Perspective radius .012 at64×512 yields ceil(64×.012×8/9)=1: each integer corner range contains only the original corner, so this configured perspective is effectively identity (not a6-pixel horizontal displacement). Rotation radius1.5° is multiplied by8/9, giving at most1.3333°; its expanded height can reach75 before resizing to64, introducing **vertical scaling**, interpolation and centering shifts. Expanded width can reach513, giving slight horizontal scaling. Blur probability.12 yields one3×3 Gaussian pass; brightness probability.2, range.92–1.08 affects local contrast and clips high intensities.\n"
    )
    sections.append(
        f"Controlled seeded in-memory examples: {len(augmentation['rows'])} schedule-bearing training lines; paired approximate token masks edge-ink cases {augmentation['edge_ink_cases']}. Width ratio {augmentation['width_ratio']}; horizontal centroid shift {augmentation['horizontal_shift']}. Full per-example bounds, ink counts, contrast proxy and Laplacian variance are retained. These are **not proven historical epoch replays**: current source/seed reproducibility does not prove the source/random state used during completed training. No glyph-completeness claim follows from zero edge ink; approximate masks may exclude kerning spill. Geometry effects are plausible exposure, not an established cause of the frozen errors.\n"
    )
    sections.append("## Clearest alignment examples\n")
    example_rows = []
    for kind in ("schedule", "duration"):
        for state in (True, False):
            chosen = [
                t for t in tokens if t["kind"] == kind and t["beam_correct"] == state
            ]
            chosen.sort(
                key=lambda t: (
                    np.mean(
                        [
                            c["peak_probability"]
                            for c in t["characters"]
                            if c["character"].isdigit()
                        ]
                    ),
                    t["sample_id"],
                ),
                reverse=state,
            )
            for t in chosen[:3]:
                example_rows.append(
                    [
                        t["sample_id"],
                        t["split"],
                        t["token"],
                        repr(t["projected"]["prediction"]),
                        t["greedy"],
                        t["prediction"],
                        "; ".join(
                            f"{c['role']}:{c['character']}@{c['start']}-{c['end']} p={c['peak_probability']:.4f} argmax={c['peak_frame_argmax_label']}"
                            for c in t["characters"]
                            if c["character"].isdigit() or c["character"] == "-"
                        ),
                    ]
                )
    sections.append(
        table(
            [
                "ID",
                "Split",
                "Target token",
                "Beam token",
                "Greedy line",
                "Beam line",
                "Assigned emissions",
            ],
            example_rows,
        )
    )
    sections.append(
        "## Evidence classification and smallest next experiment\n\nSee FINDINGS.md for the evidence-based interpretation of these measurements. Categories A–G are descriptive possibilities, not established causes of the training regression. No experiment is launched by this report.\n"
    )
    sections.append(
        "## Freeze, optional test confirmation and artifacts\n\nHypotheses, .1/.5 descriptive emission cutoffs, forced-alignment/projection rules, ±3-frame window and source/configuration hashes are recorded in audit_config.json and analysis_freeze.json. **Test confirmation was not run**; test_confirmation.json records that choice. No test predictions were inspected in this audit.\n\nCreated source files: app/ctc_alignment_audit.py, scripts/audit_ctc_schedules.py, scripts/report_ctc_schedules.py, tests/test_ctc_alignment_audit.py. New artifacts are confined to this versioned benchmark directory; no previous report is overwritten. Raw arrays cover all800 train/validation lines; full per-frame JSON traces and forced paths cover the diagnostic cohort. Final tests/checks and Git status: CHECKS.md.\n"
    )
    destination = OUT / "REPORT.md"
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text("\n".join(sections), encoding="utf-8")
    print(
        json.dumps(
            {
                "cohort": len(index),
                "tokens": len(tokens),
                "emission_groups": emission_summary,
                "line_metrics": metrics,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
