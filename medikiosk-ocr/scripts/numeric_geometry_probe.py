"""One locked 20-pair train-only numeric geometry sensitivity experiment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "upstream/handwritten-text-recognition"):
    sys.path.insert(0, str(p))

from app.ctc_alignment_audit import forced_alignment, log_probabilities, projected_token
from app.numeric_geometry import intervene, pixel_hash, reconstruct
from app.render_metadata import file_sha256

OUT = ROOT / "benchmarks/clean512_v2_numeric_geometry"
DATA = ROOT / "datasets/synthetic/clean512_v2"
PATTERNS = {"1-1-1": 8, "1-0-0": 4, "for 5 days": 4, "for 7 days": 4}
EXPECTED = "c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b"
CHECKPOINT = ROOT / "models/clean512_v2_controlled_flor.weights.h5"


def write(name, value):
    dest = OUT / name
    if dest.exists():
        raise FileExistsError(dest)
    dest.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def frozen():
    old = json.loads(
        (ROOT / "benchmarks/clean512_v2_controlled/immutability.json").read_text()
    )["after"]
    selected = {
        p: h
        for p, h in old.items()
        if "datasets/synthetic/clean512_v2/" in p.replace("\\", "/")
    }
    assert len(selected) == 1005
    assert all(file_sha256(ROOT / p) == h for p, h in selected.items())
    assert file_sha256(CHECKPOINT) == EXPECTED
    return {**selected, "models/clean512_v2_controlled_flor.weights.h5": EXPECTED}


def select(tokens, metadata):
    selected, rejected, used = [], [], set()
    for pattern, count in PATTERNS.items():
        candidates = sorted(
            [
                t
                for t in tokens
                if t["split"] == "train"
                and t["token"] == pattern
                and not t["beam_correct"]
            ],
            key=lambda t: t["sample_id"],
        )
        eligible = 0
        for t in candidates:
            if eligible == count:
                break
            mid = t["sample_id"]
            if mid in used:
                rejected.append(
                    {
                        "sample_id": mid,
                        "pattern": pattern,
                        "reason": "Already selected; require20 unique source samples",
                    }
                )
                continue
            try:
                m = metadata[mid]
                assert file_sha256(Path(m["font_path"])) == m["font_sha256"], (
                    "Font hash mismatch"
                )
                original = np.asarray(Image.open(DATA / m["image"]).convert("L"))
                rendered = reconstruct(m)
                if not np.array_equal(original, rendered):
                    raise ValueError("Original reconstruction is not pixel-identical")
                start = t["start"] if t["kind"] == "schedule" else t["start"] + 4
                end = t["end"] if t["kind"] == "schedule" else start + 1
                _changed, checks = intervene(original, m, start, end, t["kind"])
            except (ValueError, AssertionError, OSError, KeyError) as error:
                rejected.append(
                    {"sample_id": mid, "pattern": pattern, "reason": str(error)}
                )
                continue
            selected.append(
                {
                    "sample_id": mid,
                    "pattern": pattern,
                    "kind": t["kind"],
                    "token_start": t["start"],
                    "token_end": t["end"],
                    "glyph_start": start,
                    "glyph_end": end,
                    "renderer": m["renderer"],
                    "font_path": m["font_path"],
                    "font_sha256": m["font_sha256"],
                    "font_size": m["final_font_size"],
                    "text_position": m["text_position"],
                    "safe_area": m["safe_area_bounds"],
                    "target": t["truth"],
                    "prior_beam_prediction": t["prediction"],
                    "original_png_sha256": file_sha256(DATA / m["image"]),
                    "reconstructed_pixel_sha256": pixel_hash(rendered),
                    **checks,
                }
            )
            used.add(mid)
            eligible += 1
        if eligible != count:
            raise ValueError(
                f"Insufficient eligible {pattern}: {eligible}/{count}; stop before inference rather than unplanned substitution"
            )
    return selected, rejected


def endpoint(logits, sidecar, row):
    import tensorflow as tf

    from app.ctc import beam_decode, greedy_decode

    chars = sidecar["characters"]
    mapping = {c: i + 1 for i, c in enumerate(chars)}
    blank = len(chars) + 1
    logp = log_probabilities(logits)
    prob = np.exp(logp)
    forced = forced_alignment(logp, [mapping[c] for c in row["target"]], blank)
    tensor = tf.constant(logits[None], dtype=tf.float32)
    greedy = greedy_decode(tensor, chars)[0]
    locked = beam_decode(tensor, chars, 50)[0]
    paths, scores = tf.nn.ctc_beam_search_decoder(
        tf.transpose(tensor, (1, 0, 2)), tf.constant([128]), beam_width=50, top_paths=5
    )
    candidates = [
        {
            "rank": i + 1,
            "prediction": "".join(
                chars[v - 1]
                for v in tf.sparse.to_dense(path, default_value=-1).numpy()[0]
                if 0 < v <= len(chars)
            ),
            "log_probability": float(scores[0, i]),
        }
        for i, path in enumerate(paths)
    ]
    assert candidates[0]["prediction"] == locked
    span = range(row["glyph_start"], row["glyph_end"])
    emissions = []
    for position in span:
        c = {**forced["characters"][position], "character": row["target"][position]}
        frames = np.arange(max(0, c["start"] - 3), min(128, c["end"] + 4))
        local = int(frames[np.argmax(prob[frames, c["label"]])])
        competition = prob[c["peak_frame"]].copy()
        competition[c["label"]] = -1
        other = int(competition.argmax())
        c.update(
            local_peak=float(prob[local, c["label"]]),
            local_peak_frame=local,
            assigned_argmax=c["peak_frame_argmax_label"] == c["label"],
            space_probability=float(prob[c["peak_frame"], mapping[" "]]),
            strongest_competitor_id=other,
            strongest_competitor="<blank>"
            if other == blank
            else "<padding>"
            if other == 0
            else chars[other - 1],
            strongest_competitor_probability=float(prob[c["peak_frame"], other]),
        )
        emissions.append(c)
    token = projected_token(
        row["target"], locked, row["token_start"], row["token_end"]
    )["prediction"]
    targettoken = row["pattern"]
    primary = emissions[2] if row["kind"] == "schedule" else emissions[0]
    return {
        "greedy": greedy,
        "beam50": locked,
        "beam_candidates": candidates,
        "projected_beam_token": token,
        "token_correct": token == targettoken,
        "full_line_correct": locked == row["target"],
        "exact_token_rank_top5": next(
            (
                c["rank"]
                for c in candidates
                if projected_token(
                    row["target"], c["prediction"], row["token_start"], row["token_end"]
                )["prediction"]
                == targettoken
            ),
            None,
        ),
        "exact_target_rank_top5": next(
            (c["rank"] for c in candidates if c["prediction"] == row["target"]), None
        ),
        "primary_peak": primary["peak_probability"],
        "primary_local_peak": primary["local_peak"],
        "primary_argmax": primary["assigned_argmax"],
        "primary_space_probability": primary["space_probability"],
        "emissions": emissions,
        "target_log_probability": forced["target_total_log_probability"],
        "viterbi_log_probability": forced["maximum_path_log_probability"],
        "forced": forced,
        "argmax_path": logits.argmax(axis=1).tolist(),
    }, prob


def main():
    before = frozen()
    OUT.mkdir(exist_ok=False)
    protocol = """# Locked train-only local numeric geometry probe

Exactly20 unique failing TRAIN sources, ascending IDs after eligibility filtering:8 1-1-1,4 1-0-0,4 for5days,4 for7days. No validation/test selection/inference. No training or magnitude tuning. Freeze selection before counterfactual files or model inference. Eligibility includes exact original reconstruction, reliable isolated horizontal ink-band segmentation, same frozen font, safe bounds and no overlap. If quota cannot be met, stop before inference; substitutions require a new recorded protocol.

Schedules: preserve original raster glyph bitmaps and anchor; translate symbols by0,1,2,3,4 pixels respectively (exactly+1 per internal gap). All remaining original pixels stay fixed. Numeral-width: resize only tight numeral ink bitmap with OpenCV INTER_CUBIC, unchanged height, width round-half-up(1.10*w), minimumw+1; center placement round-half-up with integer tie towardpositive x. Record realized width/center error. Other glyph positions/spaces/other digits unchanged. Canvas64x512; require no overlap with other ink, zero safe-region overflow, and zero pixel differences outside old/new intervention-bbox union. Segmentation ambiguity rejects candidates rather than altering renderer.

Primary schedule endpoint: delta target-constrained middle-digit assigned peak. Primary duration endpoint: delta target-constrained numeral assigned peak. Secondary: exact full-target forward logP delta and locked token-correctness transition. Also retain other token symbol peaks/local±3-frame maxima/argmax status, assignments, space/strongest competition, Viterbi score, full-line correctness and exact token/full-target ranks in returned top5. Local maxima may borrow neighboring occurrence evidence. Token scoring uses the previous deterministic whole-line Levenshtein projection, including boundary insertions; this can be ambiguous.

Aggregate separately by four target patterns: N, mean/median/min/max delta, improved/worsened/unchanged, false→true and true→false. Changes within±1e-8 count unchanged for the peak endpoint;±1e-6 for logP. These are numerical tolerance rules, not confidence intervals. No combined causal estimate across intervention types. Descriptive extremes:3 highest/3 lowest schedule primary deltas and2 highest/2 lowest duration primary deltas, ties ascending sourceID. Report full traces for both versions.

Frozen Flor64x512, output128, unchanged preprocessing (grayscale, resizeINTER_AREA, float32/127.5−1), inference training=False. Greedy and ordinary beam50 unchanged; return top5 with same width50 and assert top1 equality. Verify checkpoint SHA c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b, all1005 clean-corpus snapshot hashes and all in-memory weights before/after. No augmentation. Limit40 inference images, no follow-up interventions; expected runtime a few minutes including startup. Interpret only selected-failure local sensitivity, not historical training cause or clinical readiness.
"""
    (OUT / "PROTOCOL.md").write_text(protocol, encoding="utf-8")
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
    selected, rejected = select(tokens, metadata)
    write(
        "selection.json",
        {
            "selected": selected,
            "rejected": rejected,
            "substitutions": [],
            "selection_frozen_before_inference": True,
            "source_audit_sha256": file_sha256(
                ROOT / "benchmarks/clean512_v2_ctc_schedule_audit/token_details.json"
            ),
            "protocol_sha256": file_sha256(OUT / "PROTOCOL.md"),
            "source_sha256": {
                p: file_sha256(ROOT / p)
                for p in [
                    "app/numeric_geometry.py",
                    "scripts/numeric_geometry_probe.py",
                    "app/ctc_alignment_audit.py",
                    "app/ctc.py",
                ]
            },
        },
    )
    (OUT / "images").mkdir()
    (OUT / "raw").mkdir()
    imagepairs = []
    for row in selected:
        original = reconstruct(metadata[row["sample_id"]])
        changed, checks = intervene(
            original,
            metadata[row["sample_id"]],
            row["glyph_start"],
            row["glyph_end"],
            row["kind"],
        )
        assert (
            checks["counterfactual_pixel_sha256"] == row["counterfactual_pixel_sha256"]
        )
        for label, image in [("original", original), ("counterfactual", changed)]:
            Image.fromarray(image).save(
                OUT / "images" / f"{row['sample_id']}_{label}.png"
            )
        imagepairs.extend([original, changed])
    write(
        "render_verification.json",
        {
            "all_reconstructed_exact": True,
            "pairs": selected,
            "frozen_artifacts_unchanged": frozen() == before,
        },
    )
    from audit_ctc_schedules import weight_hash
    from sarah.models.recognition.flor import RecognitionModel

    sidecar = json.loads(CHECKPOINT.with_suffix(".json").read_text())
    model = RecognitionModel(
        name="numeric_geometry",
        image_shape=(64, 512, 1),
        lexical_shape=(1, sidecar["max_label_length"], len(sidecar["characters"]) + 2),
        seed=41,
    ).recognition
    model.load_weights(CHECKPOINT)
    memory_before = weight_hash(model)
    inputs = np.asarray(
        [((im.astype(np.float32) / 127.5) - 1)[..., None] for im in imagepairs]
    )
    raw = np.concatenate(
        [
            model(inputs[i : i + 16], training=False)
            .numpy()
            .reshape(-1, 128, len(sidecar["characters"]) + 2)
            for i in range(0, 40, 16)
        ]
    )
    results = []
    for i, row in enumerate(selected):
        pair = {
            "sample_id": row["sample_id"],
            "pattern": row["pattern"],
            "kind": row["kind"],
            "target": row["target"],
        }
        for j, label in enumerate(["original", "counterfactual"]):
            result, prob = endpoint(raw[2 * i + j], sidecar, row)
            pair[label] = result
            np.savez_compressed(
                OUT / "raw" / f"{row['sample_id']}_{label}.npz",
                logits=raw[2 * i + j],
                probabilities=prob,
            )
        a, b = pair["original"], pair["counterfactual"]
        assert not a["token_correct"], (
            "Frozen source failure disagrees with original inference; stop, do not reselect"
        )
        pair["deltas"] = {
            k: b[k] - a[k]
            for k in [
                "primary_peak",
                "primary_local_peak",
                "primary_space_probability",
                "target_log_probability",
                "viterbi_log_probability",
            ]
        }
        results.append(pair)
        print(
            row["sample_id"],
            row["pattern"],
            pair["deltas"]["primary_peak"],
            a["token_correct"],
            b["token_correct"],
            flush=True,
        )
    assert weight_hash(model) == memory_before and frozen() == before
    with (OUT / "paired_samples.jsonl").open("w", encoding="utf-8") as f:
        for pair in results:
            f.write(json.dumps(pair) + "\n")
    write(
        "posterior_deltas.json",
        [
            {"sample_id": p["sample_id"], "pattern": p["pattern"], **p["deltas"]}
            for p in results
        ],
    )
    write(
        "beam_comparison.json",
        [
            {
                "sample_id": p["sample_id"],
                **{
                    s: {
                        k: p[s][k]
                        for k in [
                            "beam50",
                            "beam_candidates",
                            "exact_token_rank_top5",
                            "exact_target_rank_top5",
                        ]
                    }
                    for s in ["original", "counterfactual"]
                },
            }
            for p in results
        ],
    )
    summary = {}
    for pattern in PATTERNS:
        pairs = [p for p in results if p["pattern"] == pattern]
        groups = {}
        for key, tolerance in [
            ("primary_peak", 1e-8),
            ("target_log_probability", 1e-6),
        ]:
            values = [p["deltas"][key] for p in pairs]
            groups[key] = {
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "min": min(values),
                "max": max(values),
                "improved": sum(v > tolerance for v in values),
                "worsened": sum(v < -tolerance for v in values),
                "unchanged": sum(abs(v) <= tolerance for v in values),
            }
        summary[pattern] = {
            "n": len(pairs),
            "deltas": groups,
            "incorrect_to_correct": sum(
                not p["original"]["token_correct"]
                and p["counterfactual"]["token_correct"]
                for p in pairs
            ),
            "correct_to_incorrect": sum(
                p["original"]["token_correct"]
                and not p["counterfactual"]["token_correct"]
                for p in pairs
            ),
        }
    write("summary.json", summary)
    write(
        "immutability.json",
        {
            "before": before,
            "after": frozen(),
            "in_memory_weights_before": memory_before,
            "in_memory_weights_after": weight_hash(model),
            "unchanged": True,
        },
    )
    extremes = {}
    for kind, count in [("schedule", 3), ("duration", 2)]:
        pairs = sorted(
            [p for p in results if p["kind"] == kind],
            key=lambda p: (p["deltas"]["primary_peak"], p["sample_id"]),
        )
        extremes[kind] = {
            "lowest": [p["sample_id"] for p in pairs[:count]],
            "highest": [
                p["sample_id"]
                for p in sorted(
                    pairs, key=lambda p: (-p["deltas"]["primary_peak"], p["sample_id"])
                )[:count]
            ],
        }
    write(
        "frame_examples.json",
        {
            "selection": extremes,
            "pairs": [
                p
                for p in results
                if any(
                    p["sample_id"] in ids
                    for kind in extremes.values()
                    for ids in kind.values()
                )
            ],
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
