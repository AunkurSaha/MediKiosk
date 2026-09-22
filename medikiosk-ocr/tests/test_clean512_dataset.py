import csv
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.dataset import load_manifest
from app.render_metadata import verify_dataset
from scripts import build_clean512_dataset as builder

WORKSPACE = Path(__file__).resolve().parents[1]


def fixture_source(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    source = tmp_path / "datasets/synthetic/generalization"
    source.mkdir(parents=True)
    (tmp_path / "configs").mkdir()
    for path in (WORKSPACE / "configs").glob("*.txt"):
        (tmp_path / "configs" / path.name).write_bytes(path.read_bytes())
    (tmp_path / "models").mkdir()
    (tmp_path / "models/generalization_continued_flor.weights.h5").write_bytes(
        b"immutable-test-reference"
    )
    offset = 0
    for split, count in (("train", 3), ("validation", 1), ("test", 2)):
        fonts = builder.FONT_NAMES[offset : offset + builder.SPLIT_WRITERS[split]]
        offset += builder.SPLIT_WRITERS[split]
        rows = []
        for index in range(count):
            sample_id = f"{split}_{index:05d}"
            font_path = Path("C:/Windows/Fonts") / fonts[index % len(fonts)]
            text = "Tab PCM 500 mg BD x 3d"
            image = Image.new("L", (512, 64), 255)
            ImageDraw.Draw(image).text(
                (7 + index % 4, 14 + index % 3),
                text,
                fill=0,
                font=ImageFont.truetype(str(font_path), 22 + index % 3),
            )
            image.save(source / f"{sample_id}.png")
            rows.append(
                {
                    "image": f"{sample_id}.png",
                    "text": text,
                    "sample_id": sample_id,
                    "writer_id": f"synthetic_renderer_{font_path.stem}",
                    "source_type": "synthetic",
                }
            )
        with (source / f"{split}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    config = json.loads((WORKSPACE / "configs/clean512_v2.json").read_text())
    return source, config


def test_generation_determinism_metadata_and_historical_immutability(
    tmp_path, monkeypatch
):
    source, config = fixture_source(tmp_path, monkeypatch)
    references = [source, tmp_path / "models"]
    before = builder.snapshot_paths(references)
    output = tmp_path / "datasets/synthetic/clean512_v2"
    report = builder.build_version(
        source,
        output,
        tmp_path / "benchmarks/clean512_v2",
        config,
        references,
        validate_seed_policy=False,
    )
    assert report["samples"] == 6
    assert report["new_clipping_count_strict_nonbackground"] == 0
    assert builder.snapshot_paths(references) == before
    records = [
        json.loads(line)
        for line in (output / "render_metadata.jsonl").read_text().splitlines()
    ]
    required = {
        "sample_id",
        "split",
        "target_text",
        "renderer",
        "font_size",
        "canvas_width",
        "canvas_height",
        "text_bbox",
        "safe_area_bounds",
        "retry_count",
        "clipped",
        "generation_seed",
        "font_sha256",
        "original_requested_font_size",
        "final_font_size",
    }
    assert all(required <= row.keys() for row in records)
    assert all(row["canvas_width"] == 512 and not row["clipped"] for row in records)
    assert len(load_manifest(output / "train.csv")) == 3
    verification = verify_dataset(output)
    assert (
        verification["actual_glyph_loss_count"]
        == verification["safe_region_ink_overflow_count"]
        == 0
    )
    output2 = tmp_path / "datasets/synthetic/clean512_v2_reproduction"
    builder.build_version(
        source,
        output2,
        tmp_path / "benchmarks/reproduction",
        config,
        references,
        validate_seed_policy=False,
    )
    assert {p.name: p.read_bytes() for p in output.glob("*.png")} == {
        p.name: p.read_bytes() for p in output2.glob("*.png")
    }
    with pytest.raises(FileExistsError):
        builder.build_version(
            source,
            output,
            tmp_path / "benchmarks/unused",
            config,
            references,
            validate_seed_policy=False,
        )
    assert builder.snapshot_paths(references) == before


def test_source_target_or_destination_failures_do_not_create_a_version(
    tmp_path, monkeypatch
):
    source, config = fixture_source(tmp_path, monkeypatch)
    before = builder.snapshot_paths([source])
    with pytest.raises(ValueError, match="historical"):
        builder.build_version(
            source,
            source,
            tmp_path / "benchmarks/new",
            config,
            [source],
            validate_seed_policy=False,
        )
    failing_config = {**config, "minimum_font_size": 24, "maximum_font_size": 24}
    with pytest.raises(ValueError, match="Requested size"):
        builder.build_version(
            source,
            tmp_path / "datasets/synthetic/failure",
            tmp_path / "benchmarks/failure",
            failing_config,
            [source],
            validate_seed_policy=False,
        )
    assert not (tmp_path / "datasets/synthetic/failure").exists()
    assert not (tmp_path / "benchmarks/failure").exists()
    assert builder.snapshot_paths([source]) == before


def test_full_generated_version_has_zero_clipping_and_unchanged_references():
    report_path = WORKSPACE / "benchmarks/clean512_v2/generation_report.json"
    if not report_path.exists():
        pytest.skip("Generate clean512_v2 before the full-corpus acceptance check")
    report = json.loads(report_path.read_text())
    assert report["new_clipping_count_strict_nonbackground"] == 0
    assert report["projected_bounds_overflow_count"] == 0
    assert report["historical_references_unchanged"]
    assert report["samples"] == 1000
    reproducibility = json.loads(
        (report_path.parent / "reproducibility.json").read_text()
    )
    current = {
        path: builder.file_sha256(Path(path))
        for path in reproducibility["historical_files_before"]
    }
    assert current == reproducibility["historical_files_before"]
    for split, expected in (("train", 700), ("validation", 100), ("test", 200)):
        old = load_manifest(
            WORKSPACE / f"datasets/synthetic/generalization/{split}.csv"
        )
        new = load_manifest(WORKSPACE / f"datasets/synthetic/clean512_v2/{split}.csv")
        assert len(new) == expected
        assert [(x.sample_id, x.text, x.writer_id) for x in old] == [
            (x.sample_id, x.text, x.writer_id) for x in new
        ]


def test_manifest_tampering_is_detected(tmp_path, monkeypatch):
    source, config = fixture_source(tmp_path, monkeypatch)
    output = tmp_path / "datasets/synthetic/test_integrity"
    builder.build_version(
        source,
        output,
        tmp_path / "benchmarks/integrity",
        config,
        [source],
        validate_seed_policy=False,
    )
    metadata_path = output / "render_metadata.jsonl"
    records = [json.loads(line) for line in metadata_path.read_text().splitlines()]
    records[0]["text_bbox"] = [0, 0, 512, 64]
    metadata_path.write_text("\n".join(json.dumps(row) for row in records))
    with pytest.raises(ValueError, match="geometry"):
        verify_dataset(output)
