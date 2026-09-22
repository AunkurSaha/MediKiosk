"""TRAIN/validation C-vs-D analysis and validation-only decoder lock before TEST."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "upstream/handwritten-text-recognition"):
    sys.path.insert(0, str(p))
from audit_recognition import lexicon
from sarah.models.recognition.flor import RecognitionModel
from train_generalization import batches, image_tensor

from app.benchmark import error_rates
from app.ctc import beam_decode, greedy_decode
from app.ctc_alignment_audit import forced_alignment, log_probabilities, projected_token
from app.dataset import load_manifest
from app.diagnostics import buckets, conditional_fields, summarize
from app.render_metadata import file_sha256

REPORT = ROOT / "benchmarks/clean512_schedctx_v2_controlled"
DATA = ROOT / "datasets/synthetic/clean512_v2"
C = ROOT / "models/clean512_v2_controlled_flor.weights.h5"
D = ROOT / "models/clean512_schedctx_v2_flor.weights.h5"
PATTERNS = ["1-1-1", "1-0-1", "1-0-0", "0-1-0", "0-0-1"]


def write(name, value):
    with (REPORT / name).open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2)


def model(path, name):
    meta = json.loads(path.with_suffix(".json").read_text())
    m = RecognitionModel(
        name=name,
        image_shape=(64, 512, 1),
        lexical_shape=(1, meta["max_label_length"], len(meta["characters"]) + 2),
        seed=41,
    ).recognition
    m.load_weights(path)
    return m, meta


def metrics(rows):
    base = summarize(rows)
    base["fields"] = conditional_fields(
        [r["truth"] for r in rows], [r["prediction"] for r in rows], lexicon()
    )
    base["buckets"] = {
        b: summarize([r for r in rows if b in r["buckets"]])
        for b in ["numeric_schedule", "punctuation_hyphen", "repeated_character"]
    }
    sched = {}
    for p in PATTERNS:
        g = [r for r in rows if p in r["truth"]]
        sched[p] = {
            "N": len(g),
            "exact": sum(
                projected_token(
                    r["truth"],
                    r["prediction"],
                    r["truth"].index(p),
                    r["truth"].index(p) + 5,
                )["prediction"]
                == p
                for r in g
            ),
            "accuracy": sum(
                projected_token(
                    r["truth"],
                    r["prediction"],
                    r["truth"].index(p),
                    r["truth"].index(p) + 5,
                )["prediction"]
                == p
                for r in g
            )
            / len(g)
            if g
            else None,
        }
    base["schedules"] = sched
    base["schedule_macro_accuracy"] = float(
        np.mean([v["accuracy"] for v in sched.values() if v["accuracy"] is not None])
    )
    return base


def evaluate(m, meta, samples):
    rows = {"greedy": [], "beam50": []}
    diagnostics = []
    chars = meta["characters"]
    mapping = {c: i + 1 for i, c in enumerate(chars)}
    blank = len(chars) + 1
    for batch in batches(samples, 32):
        logits = m(
            np.asarray([image_tensor(s, None, 0) for s in batch]), training=False
        )
        flat = tf.reshape(logits, (len(batch), 128, len(chars) + 2))
        decoded = {
            "greedy": greedy_decode(logits, chars),
            "beam50": beam_decode(logits, chars, 50),
        }
        paths, _ = tf.nn.ctc_beam_search_decoder(
            tf.transpose(flat, (1, 0, 2)),
            tf.fill([len(batch)], 128),
            beam_width=50,
            top_paths=5,
        )
        dense = [tf.sparse.to_dense(p, default_value=-1).numpy() for p in paths]
        for i, s in enumerate(batch):
            for decoder, decoder_rows in rows.items():
                pred = decoded[decoder][i]
                decoder_rows.append(
                    {
                        "id": s.sample_id,
                        "truth": s.text,
                        "prediction": pred,
                        "cer": error_rates([s.text], [pred])[0],
                        "buckets": buckets(s.text, lexicon().medicines),
                    }
                )
            pattern = next((p for p in PATTERNS if p in s.text), None)
            if pattern in ("1-1-1", "1-0-0"):
                lp = log_probabilities(flat[i].numpy())
                forced = forced_alignment(lp, [mapping[c] for c in s.text], blank)
                start = s.text.index(pattern)
                cs = forced["characters"][start : start + 5]
                candidates = [
                    "".join(chars[v - 1] for v in dense[k][i] if 0 < v <= len(chars))
                    for k in range(5)
                ]
                diagnostics.append(
                    {
                        "id": s.sample_id,
                        "truth": s.text,
                        "pattern": pattern,
                        "beam_prediction": decoded["beam50"][i],
                        "beam_schedule_correct": projected_token(
                            s.text, decoded["beam50"][i], start, start + 5
                        )["prediction"]
                        == pattern,
                        "top5_schedule_present": any(
                            projected_token(s.text, p, start, start + 5)["prediction"]
                            == pattern
                            for p in candidates
                        ),
                        "first_digit_peak": cs[0]["peak_probability"],
                        "first_hyphen_peak": cs[1]["peak_probability"],
                        "middle_digit_peak": cs[2]["peak_probability"],
                        "second_hyphen_peak": cs[3]["peak_probability"],
                        "final_digit_peak": cs[4]["peak_probability"],
                        "middle_non_argmax": cs[2]["peak_frame_argmax_label"]
                        != cs[2]["label"],
                    }
                )
    return {
        d: {"rows": rows[d], "metrics": metrics(rows[d])} for d in rows
    }, diagnostics


def diag_summary(rows):
    out = {}
    for p in ("1-1-1", "1-0-0"):
        g = [r for r in rows if r["pattern"] == p]
        out[p] = {
            "N": len(g),
            "exact": sum(r["beam_schedule_correct"] for r in g),
            "accuracy": sum(r["beam_schedule_correct"] for r in g) / len(g),
            "middle_peak_mean": float(np.mean([r["middle_digit_peak"] for r in g])),
            "middle_peak_median": float(np.median([r["middle_digit_peak"] for r in g])),
            "middle_non_argmax_rate": sum(r["middle_non_argmax"] for r in g) / len(g),
            "top5_presence": sum(r["top5_schedule_present"] for r in g) / len(g),
            **{
                k: float(np.mean([r[k] for r in g]))
                for k in [
                    "first_digit_peak",
                    "first_hyphen_peak",
                    "second_hyphen_peak",
                    "final_digit_peak",
                ]
            },
        }
    return out


def main():
    if (REPORT / "analysis_freeze.json").exists():
        raise FileExistsError("Pre-test freeze already exists")
    cm, cmta = model(C, "C_pretest")
    dm, dmta = model(D, "D_pretest")
    result = {}
    diagnostic = {}
    for split in ["train", "validation"]:
        samples = load_manifest(DATA / f"{split}.csv")
        for label, m, meta in [("C", cm, cmta), ("D", dm, dmta)]:
            ev, di = evaluate(m, meta, samples)
            result.setdefault(label, {})[split] = {
                d: v["metrics"] for d, v in ev.items()
            }
            diagnostic.setdefault(label, {})[split] = diag_summary(di)
            write(
                f"pretest_{label}_{split}_rows.json",
                {d: v["rows"] for d, v in ev.items()},
            )
    write(
        "pretest_comparison.json",
        {"metrics": result, "middle_symbol_diagnostics": diagnostic},
    )
    vc = {d: result["D"]["validation"][d]["cer"] for d in ["greedy", "beam50"]}
    preferred = "beam50" if vc["beam50"] < vc["greedy"] else "greedy"
    lock = {
        "validation_cer": vc,
        "preferred": preferred,
        "tie_rule": "greedy",
        "qualification": "validation-preferred under renderer-conditioned validation",
        "test_inference_started": False,
    }
    write("decoder_lock.json", lock)
    cval = result["C"]["validation"]["beam50"]
    dval = result["D"]["validation"][preferred]
    c111 = diagnostic["C"]["validation"]["1-1-1"]
    d111 = diagnostic["D"]["validation"]["1-1-1"]
    classification = (
        "T4"
        if dval["cer"] > cval["cer"] * 1.25
        else "T1"
        if d111["accuracy"] > c111["accuracy"]
        and dval["schedule_macro_accuracy"] >= cval["schedule_macro_accuracy"]
        else "T2"
        if d111["accuracy"] > c111["accuracy"]
        else "T3"
    )
    summary = json.loads((REPORT / "training_summary.json").read_text())
    freeze = {
        "checkpoint": str(D.relative_to(ROOT)),
        "checkpoint_sha256": file_sha256(D),
        "best_epoch": summary["best_epoch"],
        "selected_decoder": preferred,
        "decoder_lock": lock,
        "classification": classification,
        "metric_definitions": {
            "CER_WER": "micro Levenshtein from app.benchmark",
            "schedule_exact": "full-line Levenshtein projection to exact five-character target; boundary ambiguity retained",
            "macro": "unweighted mean of five pattern accuracies",
            "middle": "target-constrained Viterbi assigned peak; non-argmax compares peak-frame argmax",
        },
        "patterns": PATTERNS,
        "train_validation_comparison": result,
        "middle_symbol_diagnostics": diagnostic,
        "test_plan": "one untouched clean512_v2 TEST inference using selected D checkpoint and locked decoder only",
        "no_further_configuration_changes": True,
        "test_inference_started": False,
    }
    write("analysis_freeze.json", freeze)
    print(
        json.dumps(
            {
                "decoder": lock,
                "classification": classification,
                "C_validation": cval,
                "D_validation": dval,
                "diagnostics": diagnostic,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
