# Final verification and changes

This is a newly specified controlled clean512_v2 baseline, not an exact reproduction of the historical interrupted training run.

## Checks

- Full pytest after training: 36 passed. Repeated after renderer inference on continuation: **36 passed** in 11.84 seconds. Two existing warnings: Starlette/AnyIO deprecation and pytest cache permissions.
- Scoped Ruff check for all three newly created Python files: passed.
- Scoped Ruff format check: all three formatted.
- `python -m compileall -q app scripts tests`: passed.
- Repo-wide `ruff check app scripts tests`: 19 pre-existing findings in unrelated files (unused E402 suppressions, import order, broad exception). Not fixed.
- Repo-wide `ruff format --check app scripts tests`: 11 pre-existing files would need formatting. Not changed, including immutable historical generation code.
- Independent CLI dataset verification repeated after renderer inference: 1,000 samples; zero projected overflow, actual glyph loss, safe-region overflow and saved-image mismatch. Artifact: `../clean512_v2/pixel_verification_controlled_final_20260917.json`.
- After renderer inference, every file in the frozen immutable snapshot was rehashed: no mismatches. Resolved config and new checkpoint hashes also matched their recorded values.

Historical checkpoint before/after: `386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef`.

New selected checkpoint: `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b`.

Resolved config: `c4ccb9dd78d72456c14bbbe54cbbfe4197d0a14d99765637588f247ad32c8c0d`.

See `immutability.json` for the full historical/clean file hash inventory. The existing matched renderer images were independently reconstructed in memory from recorded text/font/size/position, not saved or regenerated; their before/after hashes are in `fixed_phrase_renderer_hashes.json`.

## Exact source changes for this experiment

Created only:

- `scripts/run_clean512_controlled.py`: freezes protocol, historical inference, one fresh controlled training run, validation-only decoder lock, complete metrics and immutable-reference checks.
- `scripts/report_clean512_controlled.py`: unchanged existing matched-renderer inference, A/B/C comparison, descriptive errors and report generation.
- `tests/test_controlled_baseline.py`: exclusive writes, validation-only decoder locking, greedy tie rule, whitespace/optional fields and non-mutating descriptive labels.

Created artifacts:

- `models/clean512_v2_controlled_flor.weights.h5` and `.weights.json`.
- `benchmarks/clean512_v2_old_checkpoint/`: both decoders' raw rows/metrics for every split, decoder lock and worst25 errors.
- `benchmarks/clean512_v2_controlled/`: resolved config; pre/post pixel verification; epoch01–20 records; training summary; evaluation rows/metrics/decoder lock/errors; B/C and A/B/C comparisons; renderer rows/metrics/hashes; immutable hashes; descriptive errors; REPORT.md and this CHECKS.md.
- Independent verification artifacts in `benchmarks/clean512_v2/`: `pixel_verification_controlled_20260917.json`, `pixel_verification_controlled_final_20260917.json`.

No historical reports, checkpoint, manifests, dataset, clean512_v2 dataset, augmentation config or model architecture source were edited. REPORT.md was supplemented with measured findings after generation.

## Git status

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```

The outside-scope modifications were pre-existing and untouched. The OCR directory remains untracked; ignored datasets/models exist locally. No commit or push. No integration, page OCR, data collection, width1024 training, architecture/downsampling change, dictionary/LM correction, or extra training run.
