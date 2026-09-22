"""Frozen 12-pair TRAIN-only schedule identity probe; no training."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "upstream/handwritten-text-recognition"):
    sys.path.insert(0, str(p))
from numeric_geometry_probe import CHECKPOINT, DATA, endpoint, frozen

from app.numeric_geometry import pixel_hash, reconstruct
from app.render_metadata import file_sha256
from app.schedule_identity import substitute_schedule

OUT = ROOT / "benchmarks/clean512_v2_schedule_identity_probe"


def write(name, value):
    p = OUT / name
    if p.exists():
        raise FileExistsError(p)
    p.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def weight_hash(model):
    h = hashlib.sha256()
    for w in model.weights:
        h.update(w.numpy().tobytes())
    return h.hexdigest()


def main():
    before = frozen()
    OUT.mkdir(exist_ok=False)
    protocol = """# Frozen schedule identity probe

TRAIN only; exactly6 prior 1-1-1 failures and6 1-0-0 failures. Retain the four prior selected 1-0-0 sources, then add exactly two frozen TRAIN failures in ascending sample-ID order under identical eligibility. This amendment exists because the previous selected source pool contained only four 1-0-0 lines. No posterior/error/renderer-based selection. Freeze selection before model creation/inference; stop if quotas fail.

One counterpart per source: 1-1-1↔1-0-0. Preserve isolated schedule slot centers, original rasters for unchanged symbols, and render changed digits alone using the same frozen font/font size/baseline. Center replacement ink on the original ink-band center with deterministic round-half-up integer placement. Do not rerender the line, intentionally alter spacing, move other pixels, or sweep placement. Require exact original reconstruction, five isolated source bands, no non-schedule overlap, safe bounds, and changes only within old/new schedule bbox union.

Evaluate original against its true full-line target and counterpart against the substituted synthetic counterfactual full-line target. Primary descriptive comparisons: five assigned peaks/local±3 peaks/argmax/frame spans, exact forward target logP, Viterbi score, locked projected schedule, exact schedule rank top5. Analyze directions separately; no validation/test/training/tuning.
"""
    (OUT / "PROTOCOL.md").write_text(protocol, encoding="utf-8")
    prior = json.loads(
        (ROOT / "benchmarks/clean512_v2_numeric_geometry/selection.json").read_text()
    )["selected"]
    tokens = json.loads(
        (
            ROOT / "benchmarks/clean512_v2_ctc_schedule_audit/token_details.json"
        ).read_text()
    )
    metadata = {
        m["sample_id"]: m
        for line in (DATA / "render_metadata.jsonl").read_text().splitlines()
        if (m := json.loads(line))["split"] == "train"
    }
    chosen = []
    rejected = []

    def eligible(t, origin):
        m = metadata[t["sample_id"]]
        original = np.asarray(Image.open(DATA / m["image"]).convert("L"))
        rebuilt = reconstruct(m)
        if not np.array_equal(original, rebuilt):
            raise ValueError("Reconstruction mismatch")
        replacement = "1-0-0" if t["token"] == "1-1-1" else "1-1-1"
        changed, checks = substitute_schedule(
            original, m, t["start"], t["end"], replacement
        )
        return {
            "sample_id": t["sample_id"],
            "source_schedule": t["token"],
            "counterfactual_schedule": replacement,
            "start": t["start"],
            "end": t["end"],
            "target": t["truth"],
            "counterfactual_target": t["truth"][: t["start"]]
            + replacement
            + t["truth"][t["end"] :],
            "renderer": m["renderer"],
            "font_path": m["font_path"],
            "font_sha256": m["font_sha256"],
            "font_size": m["final_font_size"],
            "selection_origin": origin,
            "original_png_sha256": file_sha256(DATA / m["image"]),
            "reconstructed_pixel_sha256": pixel_hash(rebuilt),
            "counterfactual_pixel_sha256": pixel_hash(changed),
            **checks,
        }

    byid = {
        t["sample_id"]: t
        for t in tokens
        if t["kind"] == "schedule" and t["split"] == "train" and not t["beam_correct"]
    }
    for pattern, quota in [("1-1-1", 6), ("1-0-0", 4)]:
        ids = sorted(r["sample_id"] for r in prior if r["pattern"] == pattern)[:quota]
        for mid in ids:
            try:
                chosen.append(eligible(byid[mid], "previous_geometry_experiment"))
            except (ValueError, AssertionError, OSError, KeyError) as e:
                rejected.append(
                    {
                        "sample_id": mid,
                        "reason": str(e),
                        "origin": "previous_geometry_experiment",
                    }
                )
    if (
        sum(x["source_schedule"] == "1-1-1" for x in chosen) != 6
        or sum(x["source_schedule"] == "1-0-0" for x in chosen) != 4
    ):
        raise RuntimeError("Prior-source quota unavailable; stop before inference")
    priorids = {r["sample_id"] for r in prior}
    for t in sorted(
        (
            x
            for x in tokens
            if x["kind"] == "schedule"
            and x["split"] == "train"
            and x["token"] == "1-0-0"
            and not x["beam_correct"]
            and x["sample_id"] not in priorids
        ),
        key=lambda x: x["sample_id"],
    ):
        if (
            sum(
                x["selection_origin"] == "expanded_frozen_train_eligibility"
                for x in chosen
            )
            == 2
        ):
            break
        try:
            chosen.append(eligible(t, "expanded_frozen_train_eligibility"))
        except (ValueError, AssertionError, OSError, KeyError) as e:
            rejected.append(
                {
                    "sample_id": t["sample_id"],
                    "reason": str(e),
                    "origin": "expanded_frozen_train_eligibility",
                }
            )
    if len(chosen) != 12:
        raise RuntimeError(
            "Fewer than two additional eligible samples; stop before inference"
        )
    selection = {
        "selected": chosen,
        "rejected": rejected,
        "protocol_amendment": "Previous geometry experiment contained only four selected 1-0-0 sources; two additional frozen TRAIN failures selected by ascending ID under identical predeclared eligibility.",
        "frozen_before_inference": True,
        "protocol_sha256": file_sha256(OUT / "PROTOCOL.md"),
    }
    write("selection.json", selection)
    (OUT / "images").mkdir()
    (OUT / "raw").mkdir()
    pairs = []
    inputs = []
    for r in chosen:
        original = reconstruct(metadata[r["sample_id"]])
        changed, checks = substitute_schedule(
            original,
            metadata[r["sample_id"]],
            r["start"],
            r["end"],
            r["counterfactual_schedule"],
        )
        assert checks["changed_pixels"] == r["changed_pixels"]
        for label, img in [("original", original), ("counterfactual", changed)]:
            Image.fromarray(img).save(OUT / "images" / f"{r['sample_id']}_{label}.png")
            inputs.append(img)
    write(
        "render_verification.json",
        {"all_originals_exact": True, "zero_control_violations": True, "pairs": chosen},
    )
    from sarah.models.recognition.flor import RecognitionModel

    side = json.loads(CHECKPOINT.with_suffix(".json").read_text())
    model = RecognitionModel(
        name="schedule_identity",
        image_shape=(64, 512, 1),
        lexical_shape=(1, side["max_label_length"], len(side["characters"]) + 2),
        seed=41,
    ).recognition
    model.load_weights(CHECKPOINT)
    wh = weight_hash(model)
    tensor = np.asarray(
        [((x.astype(np.float32) / 127.5) - 1)[..., None] for x in inputs]
    )
    raw = (
        model(tensor, training=False)
        .numpy()
        .reshape(24, 128, len(side["characters"]) + 2)
    )
    for i, r in enumerate(chosen):
        versions = {}
        for j, label in enumerate(["original", "counterfactual"]):
            target = r["target"] if label == "original" else r["counterfactual_target"]
            erow = {
                **r,
                "target": target,
                "pattern": r["source_schedule"]
                if label == "original"
                else r["counterfactual_schedule"],
                "glyph_start": r["start"],
                "glyph_end": r["end"],
                "token_start": r["start"],
                "token_end": r["end"],
                "kind": "schedule",
            }
            result, prob = endpoint(raw[2 * i + j], side, erow)
            versions[label] = result
            np.savez_compressed(
                OUT / "raw" / f"{r['sample_id']}_{label}.npz",
                logits=raw[2 * i + j],
                probabilities=prob,
            )
        pairs.append(
            {
                "sample_id": r["sample_id"],
                "direction": f"{r['source_schedule']}->{r['counterfactual_schedule']}",
                "original_target": r["target"],
                "counterfactual_target": r["counterfactual_target"],
                **versions,
                "middle_peak_delta": versions["counterfactual"]["emissions"][2][
                    "peak_probability"
                ]
                - versions["original"]["emissions"][2]["peak_probability"],
                "first_peak_delta": versions["counterfactual"]["emissions"][0][
                    "peak_probability"
                ]
                - versions["original"]["emissions"][0]["peak_probability"],
                "final_peak_delta": versions["counterfactual"]["emissions"][4][
                    "peak_probability"
                ]
                - versions["original"]["emissions"][4]["peak_probability"],
                "target_logp_delta": versions["counterfactual"][
                    "target_log_probability"
                ]
                - versions["original"]["target_log_probability"],
            }
        )
    assert weight_hash(model) == wh and frozen() == before
    with (OUT / "paired_samples.jsonl").open("w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")
    comparison = [
        {
            k: p[k]
            for k in [
                "sample_id",
                "direction",
                "middle_peak_delta",
                "first_peak_delta",
                "final_peak_delta",
                "target_logp_delta",
            ]
        }
        for p in pairs
    ]
    write("posterior_comparison.json", comparison)
    write(
        "beam_comparison.json",
        [
            {
                "sample_id": p["sample_id"],
                "direction": p["direction"],
                "original": {
                    k: p["original"][k]
                    for k in [
                        "beam50",
                        "projected_beam_token",
                        "token_correct",
                        "exact_token_rank_top5",
                        "beam_candidates",
                    ]
                },
                "counterfactual": {
                    k: p["counterfactual"][k]
                    for k in [
                        "beam50",
                        "projected_beam_token",
                        "token_correct",
                        "exact_token_rank_top5",
                        "beam_candidates",
                    ]
                },
            }
            for p in pairs
        ],
    )
    summary = {}
    for direction in ["1-1-1->1-0-0", "1-0-0->1-1-1"]:
        g = [p for p in pairs if p["direction"] == direction]

        def s(key, group=g):
            v = [x[key] for x in group]
            return {
                "mean": float(np.mean(v)),
                "median": float(np.median(v)),
                "min": min(v),
                "max": max(v),
            }

        summary[direction] = {
            "n": len(g),
            "middle_peak_delta": s("middle_peak_delta"),
            "first_peak_delta": s("first_peak_delta"),
            "final_peak_delta": s("final_peak_delta"),
            "target_logp_delta": s("target_logp_delta"),
            "original_exact_schedule": sum(x["original"]["token_correct"] for x in g),
            "counterfactual_exact_schedule": sum(
                x["counterfactual"]["token_correct"] for x in g
            ),
            "original_top5": sum(
                x["original"]["exact_token_rank_top5"] is not None for x in g
            ),
            "counterfactual_top5": sum(
                x["counterfactual"]["exact_token_rank_top5"] is not None for x in g
            ),
        }
    write("summary.json", summary)
    write(
        "immutability.json",
        {
            "frozen_before": before,
            "frozen_after": frozen(),
            "weights_before": wh,
            "weights_after": weight_hash(model),
            "unchanged": True,
        },
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
