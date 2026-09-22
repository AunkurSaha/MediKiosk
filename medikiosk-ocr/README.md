# MediKiosk prescription handwriting OCR workspace

Prescription-specific handwritten text recognition built on and adapted from
an open-source HTR framework. This workspace is isolated from the clinical
backend and never treats patient uploads as training data automatically.

## Upstream provenance

- Repository: `https://github.com/arthurflor23/handwritten-text-recognition.git`
- Local path: `upstream/handwritten-text-recognition`
- Branch: `master`
- Commit: `fc8515f9aa9dc54a93a75366ca8d8ac4adaf35c8`
- License: MIT; see `LICENSES/handwritten-text-recognition-MIT.txt`

The upstream dependency file requests `tensorflow[and-cuda]` on Windows. This
Intel-only machine cannot satisfy its NVIDIA NCCL dependency. The documented
`requirements-medikiosk.txt` preserves every upstream pin but uses plain
CPU-only `tensorflow==2.19.0`, and adds only the isolated service/test tools.

## Environment

```powershell
cd C:\MEDIKIOSK\medikiosk-ocr
.\.venv\Scripts\Activate.ps1
.\scripts\setup-ocr.ps1
```

Python 3.11.16 and TensorFlow 2.19.0 are used. TensorFlow sees CPU only.

## Safe synthetic data

The manifest schema is:

```csv
image,text,writer_id,sample_id,source_type
```

Allowed sources are `synthetic`, `volunteer`, and `approved_deidentified`.
Real patient uploads are excluded from this workflow by design.

```powershell
python scripts\generate_prescription_text.py --count 20 --seed 17
python scripts\build_tiny_dataset.py
python scripts\tiny_overfit.py --epochs 12
```

### CTC blank-collapse acceptance check

Flor uses label `0` only as dense-label padding. Its legacy CTC loss reserves
the final output class as the blank token, so decoding must use that final
class too. Treating class `0` as blank caused the apparent blank collapse.

The bounded memorization diagnostic uses six fixed 256x64 clean images. It
does not call the augmentation pipeline and runs Flor in inference mode during
gradient calculation to disable its 50-60% dropout. This is intentionally an
overfit check, not a generalization or production-quality claim.

```powershell
python scripts\build_clean_ctc_dataset.py
python scripts\clean_ctc_overfit.py --max-epochs 250 --target-cer 0.01 --learning-rate 0.001
```

The accepted run reached mean CER `0.0` on all six samples at epoch 175 after
checkpoint reload. Its machine-readable report is
`benchmarks/clean_ctc_overfit.json`. Do not start broader training or connect
this recognizer to MediKiosk based on this memorization result alone.

## Renderer-independent synthetic generalization

Build the 700/100/200 phrase- and renderer-disjoint synthetic benchmark:

```powershell
python scripts\build_generalization_dataset.py --count 1000
```

Run the complete experiment only when the expected CPU runtime is acceptable:

```powershell
python scripts\train_generalization.py --epochs 20 --batch-size 8
```

Flor dropout is enabled during training. The light augmentation preset applies
only to training images; validation and test inputs remain clean. Results
include CER, WER, medicine, dose, frequency, and duration accuracy in
`benchmarks/generalization.json`.

For a quick wiring check rather than an accuracy claim:

```powershell
python scripts\train_generalization.py --epochs 1 --batch-size 8 `
  --max-train-samples 32 --max-eval-samples 8
```

See `docs/GENERALIZATION_PROTOCOL.md` before collecting volunteer handwriting.

## Evaluation-only alignment and renderer diagnostics

The current measured report is `benchmarks/ctc_audit/REPORT.md`. Diagnostic
renderer images are stored separately and never enter training manifests or
checkpoint selection. The width-1024 probe reuses the existing checkpoint;
it is not a retrained architecture experiment.

```powershell
python scripts\audit_recognition.py --phase geometry
python scripts\audit_recognition.py --phase renderer_fit
python scripts\inspect_ctc_paths.py
python scripts\verify_render_bounds.py
python scripts\audit_recognition.py --phase decoder
python scripts\report_ctc_audit.py
```

Logits are cached under ignored `outputs/ctc_audit` and bound to the checkpoint
SHA-256. Ordinary beam search uses width 50, the final CTC class as blank, and
no dictionary or medication correction. Vocabulary lists are used only to
score field accuracy. Optional duration, form and instruction metrics include
both overall and present-only accuracy.

Do not silently repair or overwrite the original synthetic baseline images.
The audit demonstrates clipped target pixels in that corpus; any repaired
corpus must be separately versioned before further controlled training.

The vocabulary is training/post-processing material only. It is not clinical
truth and must never be used to verify or prescribe medication.

## Checks and inference

```powershell
.\scripts\check-ocr.ps1
python scripts\benchmark_inference.py
```

The tiny checkpoint deliberately proves the pipeline and is not accurate
enough for clinical use. It must not be selected as a production recognizer.

For an approved MediKiosk-format manifest, start a fresh random-initialized run
without any checkpoint input:

```powershell
python scripts\tiny_overfit.py --manifest datasets\volunteer\manifest.csv --checkpoint models\prescription_flor.weights.h5 --epochs 12
```

Twelve epochs remains a pipeline check. Increase training duration only after
reviewing writer-independent splits and explicitly approving a longer run.

## Local service

The model loads once during service startup and binds only to localhost:

```powershell
.\scripts\start-ocr.ps1
```

- `GET http://127.0.0.1:8020/health`
- `POST http://127.0.0.1:8020/recognize-line` with multipart field `image`

Empty output is reported as `OCR_EMPTY_RESULT`; it is never fabricated. The
full-page endpoint is intentionally absent until segmentation is validated.

## Optional IAM baseline

Do not download IAM automatically. After confirming its terms and obtaining
the dataset, place the upstream-expected `iam/` content under an explicit
input directory and inspect it first:

```powershell
cd upstream\handwritten-text-recognition
python sarah --source iam --text-level line --input-path <approved-dataset-root> --check
```

The upstream `--check` opens GUI windows and is unsuitable for headless CI.

## Integration boundary

No MediKiosk backend provider has been added yet. Integration remains gated on
a useful recognition checkpoint and standalone endpoint acceptance. When that
gate passes, the backend should call `http://127.0.0.1:8020` while retaining
its upload validation, raw extraction persistence, provenance, unverified
facts, doctor review, audit history, and existing OCR providers.
