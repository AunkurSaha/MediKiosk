# Clean width-512 dataset, version clean512_v2

No training or recognition inference was performed. Architecture, downsampling and input shape remain unchanged. Historical checkpoint SHA-256 remains `386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef`. Historical datasets, manifests, generator and audit artifacts passed before/after SHA-256 equality checks.

## Root cause and correction

`scripts/build_generalization_dataset.py` drew directly onto a 512x64 canvas using font sizes 22–24 and fixed positions without checking text bounds. Pillow discarded ink outside the canvas. The historical audit measured 136 actual clipped images; 139 bounding-box warnings were not equivalent to actual clipping.

The separate versioned builder retains seed 41, target strings, IDs, splits, renderer assignments and positions. Before drawing, reusable `validate_render_bounds` measures the explicit `la` anchored bounding box against safe area (4,8,504,56). Font size decreases deterministically from the original requested size to minimum 14. Failure at minimum raises a structured exception. No image is stretched, compressed or cropped to fit. A common-font-size group fitting API supports matched diagnostic phrases. All candidates are preflighted before dataset creation, and existing destinations are refused.

Independent verification renders onto a padded canvas, checks every non-background pixel outside the intended canvas and safe area, and compares the saved image with the corresponding canvas region. Font and image hashes, positions, bounds and configuration are retained in companion metadata; five-column CSV compatibility is preserved.

## Dataset results

- Historical dataset: `datasets/synthetic/generalization` (unchanged).
- New dataset: `datasets/synthetic/clean512_v2`.
- Counts: 700 train / 100 validation / 200 test.
- Target text, split and renderer equality by sample ID: all 1,000.
- Projected overflow: **0**; actual glyph loss: **0**; safe-region ink overflow: **0**; saved-image mismatches: **0**.
- Font reductions: **152** (111 train, 32 validation, 9 test).
- Changed rendered pixels: **152 / 1,000 = 15.2%**. Safe margins explain why this exceeds the old actual-clipping count.
- Historical actual clipping: 136 at the historical audit threshold of 220. New verification uses the stricter any-non-background threshold and finds zero.

| Font size | Old count | New count |
|---|---:|---:|
|14|0|2|
|15|0|8|
|16|0|1|
|17|0|16|
|18|0|7|
|19|0|24|
|20|0|34|
|21|0|15|
|22|335|334|
|23|333|288|
|24|332|271|

All text-based old/new distributions are identical: target lengths, medications, schedules, optional fields and length buckets. Renderer counts remain 100 for each of ten fonts. Complete distributions, including each split's font sizes and individual medication/field values, are in [generation_report.json](generation_report.json).

## CTC feasibility (known output length 128, no model execution)

Required steps = target characters + adjacent repeated characters. Ratios are output steps / required steps.

| Split | Required min / median / max | Ratio min / median / max | Below 1.5 | Infeasible |
|---|---|---|---:|---:|
|All|14 / 36 / 67|1.9104 / 3.5556 / 9.1429|0|0|
|Train|14 / 36 / 67|1.9104 / 3.5556 / 9.1429|0|0|
|Validation|17 / 36 / 65|1.9692 / 3.5556 / 7.5294|0|0|
|Test|16 / 37 / 64|2.0000 / 3.4595 / 8.0000|0|0|

Per-target records: [ctc_alignment_samples.json](ctc_alignment_samples.json).

## Validation versus test

| Attribute | Validation (100) | Test (200) |
|---|---|---|
|Renderer|segoepr only|times 100, trebuc 100|
|Target length min / median / max|17 / 34 / 59|16 / 34 / 57|
|Short / medium / long|18% / 54% / 28%|16% / 54.5% / 29.5%|
|Font adjusted|32%|4.5%|
|Minimum final font size|15|21|
|Numeric schedule present|35%|33%|
|Duration present|60%|72%|
|Form present|78%|74%|
|Instruction present|41%|37%|

Medication counts (validation / test): Amoxicillin 13/38; Cetirizine 13/25; Metformin 21/32; PCM 17/39; Pantoprazole 17/32; Paracetamol 19/34. Schedule counts (validation / test): 0-0-1 5/10; 0-1-0 11/9; 1-0-0 9/14; 1-0-1 4/15; 1-1-1 6/18; absent 65/134. Instructions: after food 7/11; as needed 6/16; at bedtime 10/12; before food 10/20; with water 8/15; absent 59/126.

Renderer assignment differs materially. Font fitting also changes the glyph scale more frequently in validation. These distributions do NOT establish the cause of validation's higher historical CER, and fixing clipping does NOT establish that clipping was the only recognition problem. No new recognition metrics or checkpoint selection took place.

## Exact files and artifacts

Created source/config/test files:

- `app/rendering.py`
- `app/render_metadata.py`
- `configs/clean512_v2.json`
- `scripts/build_clean512_dataset.py`
- `scripts/verify_clean512_dataset.py`
- `tests/test_rendering.py`
- `tests/test_clean512_dataset.py`

Modified files:

- `.gitignore`: ignore generated new dataset.
- `scripts/train_generalization.py`: explicit dataset/report directory options and new-run overwrite protection only; model/training policy unchanged.
- `scripts/evaluate_generalization.py`: explicit dataset/output/training-report options and greedy/ordinary beam selection; no lexical correction.

Generated dataset: 1,000 PNGs, `train.csv`, `validation.csv`, `test.csv`, `render_metadata.jsonl`, `generation_config.json` under the new dataset directory. Each metadata record includes original/final font size, retries, fitted status, canvas, margins, bbox, safe area, text, renderer, seed, image/font hashes and pixel checks.

Generated reports in this directory: `REPORT.md`, `generation_report.json`, `pixel_verification.json`, `pixel_verification_independent.json`, `ctc_alignment_samples.json`, `reproducibility.json`. The latter records source code, configuration, fonts, dataset and immutable-reference hashes.

## Checks and Git status

- Full pytest suite: **31 passed**, including generated-dataset acceptance and historical immutability checks. Two existing warnings: Starlette/AnyIO deprecation and pytest cache permissions.
- Ruff check: passed for all eight touched Python files.
- Ruff formatting check: eight files already formatted.
- `python -m compileall -q app scripts tests`: passed.
- Independent verifier: 1,000 samples, all four failure counts zero.
- Git status: entire `medikiosk-ocr/` remains untracked. Pre-existing modifications outside scope: `backend/.env.example`, `backend/app/services/paddleocr_ocr.py`, `frontend/src/api/client.ts`. These were not touched. No commit or push.

## Future commands — NOT executed

Run from `C:\MEDIKIOSK\medikiosk-ocr`. These use a fresh, separate checkpoint and report location, unchanged width 512, dropout and training-only augmentation from the existing baseline. The best-validation checkpoint, not final-epoch weights, is subsequently evaluated. Batch size 8 preserves the current baseline default.

```powershell
rtk proxy .\.venv\Scripts\python.exe scripts\train_generalization.py --dataset-dir datasets\synthetic\clean512_v2 --report-dir benchmarks\clean512_v2_training --checkpoint models\clean512_v2_flor.weights.h5 --epochs 20 --batch-size 8 --seed 41 --learning-rate 0.001 --early-stopping-patience 5 --early-stopping-min-delta 0.002

rtk proxy .\.venv\Scripts\python.exe scripts\evaluate_generalization.py --dataset-dir datasets\synthetic\clean512_v2 --checkpoint models\clean512_v2_flor.weights.h5 --training-report benchmarks\clean512_v2_training\generalization.json --output benchmarks\clean512_v2_training\greedy.json --decoder greedy --batch-size 8

rtk proxy .\.venv\Scripts\python.exe scripts\evaluate_generalization.py --dataset-dir datasets\synthetic\clean512_v2 --checkpoint models\clean512_v2_flor.weights.h5 --training-report benchmarks\clean512_v2_training\generalization.json --output benchmarks\clean512_v2_training\beam50.json --decoder beam --beam-width 50 --batch-size 8
```

Stop here: training requires a subsequent user request. No width-1024 experiment, architecture change, dictionary correction, page OCR or MediKiosk integration was performed.
