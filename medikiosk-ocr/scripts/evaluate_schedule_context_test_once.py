"""One locked TEST evaluation after immutable analysis_freeze.json exists."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "upstream/handwritten-text-recognition"):
    sys.path.insert(0, str(p))
from audit_recognition import lexicon
from sarah.models.recognition.flor import RecognitionModel
from train_generalization import batches, image_tensor

from app.ctc import beam_decode
from app.ctc_alignment_audit import projected_token
from app.dataset import load_manifest
from app.diagnostics import buckets, conditional_fields, summarize

REPORT = ROOT / "benchmarks/clean512_schedctx_v2_controlled"
DATA = ROOT / "datasets/synthetic/clean512_v2"
D = ROOT / "models/clean512_schedctx_v2_flor.weights.h5"
PATTERNS = ["1-1-1", "1-0-1", "1-0-0", "0-1-0", "0-0-1"]


def main():
    output = REPORT / "locked_test.json"
    if output.exists():
        raise FileExistsError("TEST already evaluated")
    freeze = json.loads((REPORT / "analysis_freeze.json").read_text())
    assert (
        freeze["selected_decoder"] == "beam50"
        and freeze["no_further_configuration_changes"]
        and not freeze["test_inference_started"]
    )
    side = json.loads(D.with_suffix(".json").read_text())
    model = RecognitionModel(
        name="D_locked_test_once",
        image_shape=(64, 512, 1),
        lexical_shape=(1, side["max_label_length"], len(side["characters"]) + 2),
        seed=41,
    ).recognition
    model.load_weights(D)
    samples = load_manifest(DATA / "test.csv")
    rows = []
    for batch in batches(samples, 32):
        logits = model(
            np.asarray([image_tensor(s, None, 0) for s in batch]), training=False
        )
        predictions = beam_decode(logits, side["characters"], 50)
        for s, pred in zip(batch, predictions, strict=True):
            rows.append(
                {
                    "id": s.sample_id,
                    "truth": s.text,
                    "prediction": pred,
                    "buckets": buckets(s.text, lexicon().medicines),
                }
            )
    base = summarize(rows)
    normalized = [
        {
            "truth": " ".join(r["truth"].split()),
            "prediction": " ".join(r["prediction"].split()),
        }
        for r in rows
    ]
    base["whitespace_normalized"] = summarize(normalized)
    base["fields"] = conditional_fields(
        [r["truth"] for r in rows], [r["prediction"] for r in rows], lexicon()
    )
    base["buckets"] = {
        b: summarize([r for r in rows if b in r["buckets"]])
        for b in ["numeric_schedule", "punctuation_hyphen", "repeated_character"]
    }
    base["schedules"] = {}
    for pattern in PATTERNS:
        g = [r for r in rows if pattern in r["truth"]]
        exact = sum(
            projected_token(
                r["truth"],
                r["prediction"],
                r["truth"].index(pattern),
                r["truth"].index(pattern) + 5,
            )["prediction"]
            == pattern
            for r in g
        )
        base["schedules"][pattern] = {
            "N": len(g),
            "exact": exact,
            "accuracy": exact / len(g),
        }
    base["schedule_macro_accuracy"] = float(
        np.mean([v["accuracy"] for v in base["schedules"].values()])
    )
    result = {
        "checkpoint": str(D.relative_to(ROOT)),
        "checkpoint_sha256": freeze["checkpoint_sha256"],
        "decoder": "beam50",
        "decoder_locked_before_test": True,
        "test_inference_count": 1,
        "metrics": base,
        "rows": rows,
    }
    with output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    freeze["test_inference_started"] = True
    freeze["test_inference_completed_once"] = True
    (REPORT / "analysis_freeze.json").write_text(
        json.dumps(freeze, indent=2), encoding="utf-8"
    )
    print(json.dumps(base, indent=2))


if __name__ == "__main__":
    main()
